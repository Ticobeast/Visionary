#!/usr/bin/env python3
"""Convertit une base de l'ancien format (v1) vers le format actuel (v2).

    python outils/migrer.py data/sylvainculteur.db

Changements v1 -> v2 :
  * un chantier peut avoir plusieurs types de travaux, chacun avec sa précision
    (table chantier_travaux) : l'ancien type devient un type sans précision ;
  * une seule date des travaux : date_prevue reprend date_realisee quand elle existe ;
  * les notes de chantier sont ajoutées à la fin de la description.

Rien n'est perdu : l'ancienne base est conservée dans data/sauvegardes/ avant tout
changement, et la nouvelle est vérifiée (nombre de lignes, intégrité) avant de la
mettre en place. Fermer l'interface avant de lancer ce script.
Bibliothèque standard seulement.
"""
import argparse
import datetime
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCHEMA = RACINE / "schema" / "schema.sql"
TABLES = ("clients", "chantiers", "paiements")


def migrer(db_path):
    db_path = Path(db_path)
    if not db_path.exists():
        raise SystemExit(f"Base introuvable : {db_path}")
    ancien = sqlite3.connect(db_path)
    version = ancien.execute("PRAGMA user_version").fetchone()[0]
    tables = {r[0] for r in ancien.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    ancien.close()
    if version == 2:
        return None  # déjà à jour
    if version != 1 or "sites" in tables:
        raise SystemExit("Format de base non pris en charge (version %s%s). Garde ce fichier et demande de l'aide."
                         % (version, ", avec une table sites" if "sites" in tables else ""))

    dossier_tmp = Path(tempfile.mkdtemp(prefix="migration_", dir=db_path.parent))
    nouveau_chemin = dossier_tmp / "nouvelle.db"
    try:
        conn = sqlite3.connect(nouveau_chemin, isolation_level=None)
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("ATTACH DATABASE ? AS v1", (str(db_path),))
        conn.execute("BEGIN")
        conn.execute("INSERT OR IGNORE INTO types_travaux (code, libelle) SELECT code, libelle FROM v1.types_travaux")
        conn.execute("INSERT INTO clients SELECT id, prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok,"
                     " adresse, ville, province, code_postal, latitude, longitude, geocode_statut, notes_acces, notes, cree_le"
                     " FROM v1.clients")
        conn.execute(
            "INSERT INTO chantiers (id, client_id, description, statut, date_soumission, date_prevue, heure_prevue,"
            " duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq, numero_facture, date_facture, dossier_photos,"
            " fichier_papier, ref_papier, cree_le)"
            " SELECT id, client_id,"
            "  NULLIF(trim(COALESCE(description, '') || CASE WHEN trim(COALESCE(notes, '')) <> '' THEN char(10) || notes ELSE '' END, char(10) || ' '), ''),"
            "  statut, date_soumission, COALESCE(date_realisee, date_prevue), heure_prevue, duree_estimee_h, duree_reelle_h,"
            "  prix_ht, tps, tvq, numero_facture, date_facture, dossier_photos, fichier_papier, ref_papier, cree_le"
            " FROM v1.chantiers")
        conn.execute("INSERT INTO chantier_travaux (chantier_id, type_travaux, precision)"
                     " SELECT id, type_travaux, NULL FROM v1.chantiers")
        conn.execute("INSERT INTO paiements SELECT id, chantier_id, date_paiement, montant, mode, reference, notes, cree_le"
                     " FROM v1.paiements")
        conn.execute("COMMIT")
        for t in TABLES:
            avant = conn.execute(f"SELECT count(*) FROM v1.{t}").fetchone()[0]
            apres = conn.execute(f"SELECT count(*) FROM main.{t}").fetchone()[0]
            if avant != apres:
                raise SystemExit(f"Vérification échouée : {t} avait {avant} lignes, la nouvelle base en a {apres}.")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Vérification échouée : la nouvelle base est incohérente. Rien n'a été modifié.")
        compte = {t: conn.execute(f"SELECT count(*) FROM main.{t}").fetchone()[0] for t in TABLES}
        conn.execute("DETACH DATABASE v1")
        conn.close()

        sauvegardes = db_path.parent / "sauvegardes"
        sauvegardes.mkdir(exist_ok=True)
        copie = sauvegardes / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_avant_migration_v1.db"
        shutil.copy2(db_path, copie)
        try:
            os.replace(nouveau_chemin, db_path)
        except PermissionError:
            raise SystemExit("Impossible de remplacer la base : un autre programme l'utilise. "
                             "Ferme l'interface (et DB Browser) puis relance.")
        return {"sauvegarde": copie, **compte}
    finally:
        shutil.rmtree(dossier_tmp, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Convertit une base v1 vers le format actuel (v2).")
    p.add_argument("db", help="fichier de base à convertir (ex. data/sylvainculteur.db)")
    a = p.parse_args(argv)
    r = migrer(a.db)
    if r is None:
        print("Cette base est déjà au format actuel : rien à faire.")
        return 0
    print(f"Base convertie : {r['clients']} clients, {r['chantiers']} chantiers, {r['paiements']} paiements.\n"
          f"Ancienne version conservée : {r['sauvegarde']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
