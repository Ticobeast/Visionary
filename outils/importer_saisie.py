#!/usr/bin/env python3
"""Importe une feuille de saisie (CSV « à plat », une ligne = un chantier)
dans la base SQLite de SylvainCulteur.

    python3 outils/importer_saisie.py data/saisie/lot_2026-10-05.csv --simulation
    python3 outils/importer_saisie.py data/saisie/lot_2026-10-05.csv

Ce que fait le script :
  * valide chaque ligne (dates AAAA-MM-JJ, téléphone, code postal, montants...)
    et affiche TOUTES les erreurs avec leur numéro de ligne (celui du tableur)
  * regroupe les lignes d'un même client (même adresse + même nom ou téléphone)
  * ignore les lignes déjà importées : on peut relancer le même fichier
  * est « tout ou rien » : une seule erreur et rien n'est écrit
  * sauvegarde la base avant d'écrire (data/sauvegardes/)

Les corrections de fiches déjà importées se font dans l'interface (outils/interface.py)
ou dans la base, pas en réimportant une ligne modifiée.

Bibliothèque standard seulement (Python 3.8+).
"""
import argparse
import csv
import io
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from noyau import (COLONNES, COLONNES_REQUISES, appliquer_secteur, DB_DEFAUT, Index, Resultat, alias_types_travaux,  # noqa: E402
                   creer_chantier, lire_ligne, ouvrir_base, sauvegarder, trouver_ou_creer_client)


def _lire_csv(chemin):
    """Retourne (lignes, remarques). Gère UTF-8 (avec/sans BOM), Windows-1252, « , » ou « ; »."""
    octets = Path(chemin).read_bytes()
    remarques = []
    try:
        texte = octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = octets.decode("cp1252")
        remarques.append("fichier lu en Windows-1252 (export « CSV » d'Excel) ; l'UTF-8 est préférable")
    premiere = texte.split("\n", 1)[0]
    delim = max((",", ";", "\t"), key=premiere.count)
    lignes = list(csv.reader(io.StringIO(texte, newline=""), delimiter=delim))
    if not lignes:
        raise SystemExit("Fichier vide.")
    entete = [h.strip().lower() for h in lignes[0]]
    inconnues = [h for h in entete if h and h not in COLONNES]
    if inconnues:
        raise SystemExit(
            "Colonne(s) inconnue(s) dans l'en-tête : " + ", ".join(inconnues)
            + "\nColonnes permises : " + ", ".join(COLONNES))
    manquantes = [c for c in COLONNES_REQUISES if c not in entete]
    if not {"client_nom", "client_entreprise"} & set(entete):
        manquantes.append("client_nom")
    if manquantes:
        raise SystemExit("Colonne(s) obligatoire(s) absente(s) de l'en-tête : " + ", ".join(manquantes))
    return entete, lignes[1:], remarques




def importer(csv_path, db_path=DB_DEFAUT, simulation=False, taxes_auto=False):
    db_path = Path(db_path)
    res = Resultat()
    entete, lignes, remarques = _lire_csv(csv_path)
    res.avertissements.extend(remarques)

    existait = db_path.exists() and db_path.stat().st_size > 0
    if not simulation and existait:
        res.sauvegarde = sauvegarder(db_path)
    conn, _ = ouvrir_base(db_path, en_memoire_si_absente=simulation)
    alias_types = alias_types_travaux(conn)

    idx = Index(conn)
    changements_avant = conn.total_changes
    conn.execute("BEGIN")
    for no, cellules in enumerate(lignes, start=2):
        if not any(c.strip() for c in cellules):
            continue
        if len(cellules) > len(entete):
            res.erreurs.append((no, ["plus de cellules que de colonnes (une virgule dans un texte non entouré de guillemets ?)"]))
            continue
        brut = dict(zip(entete, cellules))
        erreurs_secteur = appliquer_secteur(conn, brut, requis=False)       # la ville vient du secteur choisi
        v, erreurs = lire_ligne(brut, alias_types, taxes_auto)
        erreurs = erreurs_secteur + erreurs
        if erreurs:
            res.erreurs.append((no, erreurs))
            continue
        avertir = lambda msg, no=no: res.avertissements.append(f"ligne {no} : {msg}")  # noqa: E731
        conn.execute("SAVEPOINT ligne")
        try:
            client_id = trouver_ou_creer_client(conn, idx, v, res, avertir)
            creer_chantier(conn, client_id, v, res, avertir)
            conn.execute("RELEASE ligne")
        except sqlite3.IntegrityError as e:
            conn.execute("ROLLBACK TO ligne")
            conn.execute("RELEASE ligne")
            idx.recharger(conn)
            res.erreurs.append((no, [f"refusé par la base : {e}"]))

    if res.erreurs or simulation:
        conn.execute("ROLLBACK")
        if res.sauvegarde:
            res.sauvegarde.unlink()
            res.sauvegarde = None
    else:
        conn.execute("COMMIT")
        if res.sauvegarde and conn.total_changes == changements_avant:  # rien d'écrit : sauvegarde inutile
            res.sauvegarde.unlink()
            res.sauvegarde = None
    conn.close()
    return res


def afficher(res, simulation, sortie=print):
    for msg in res.avertissements:
        sortie(f"  avertissement : {msg}")
    if res.erreurs:
        sortie(f"\n{len(res.erreurs)} ligne(s) en erreur — RIEN n'a été importé :")
        for no, messages in res.erreurs:
            sortie(f"  ligne {no} :")
            for m in messages:
                sortie(f"    - {m}")
        return
    verbe = "seraient importés (simulation, rien n'est écrit)" if simulation else "importés"
    sortie(f"\n{res.chantiers} chantier(s) {verbe} : "
           f"{res.clients_crees} client(s) créé(s), {res.clients_reutilises} client(s) réutilisé(s), "
           f"{res.paiements} paiement(s).")
    if res.doublons:
        sortie(f"{res.doublons} ligne(s) déjà présente(s) dans la base : ignorée(s).")
    if res.sauvegarde:
        sortie(f"Sauvegarde avant import : {res.sauvegarde}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Importe une feuille de saisie CSV dans la base SQLite.")
    p.add_argument("csv", help="fichier CSV à importer")
    p.add_argument("--db", default=str(DB_DEFAUT), help=f"fichier de base (défaut : {DB_DEFAUT})")
    p.add_argument("--simulation", action="store_true", help="valide et résume sans rien écrire")
    p.add_argument("--taxes-auto", action="store_true",
                   help="calcule TPS (5 %%) et TVQ (9,975 %%) quand tps et tvq sont vides")
    a = p.parse_args(argv)
    res = importer(a.csv, a.db, simulation=a.simulation, taxes_auto=a.taxes_auto)
    afficher(res, a.simulation)
    return 1 if res.erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
