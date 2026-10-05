#!/usr/bin/env python3
"""Convertit une base d'un ancien format (v1 à v5) vers le format actuel (v6).

    python outils/migrer.py data/sylvainculteur.db

Changements v5 -> v6 :
  * secteurs desservis : liste fermée (table secteurs) ; chaque client gagne un secteur (vide au départ : rempli
    automatiquement quand sa ville correspond à un seul secteur, sinon à choisir dans la fiche client) ;
  * options de la job : nacelle requise, bois débarrassé ou laissé en 16 pouces / 4 pieds (valeurs par défaut : non) ;
  * un chantier annulé est archivé.

Changements v4 -> v5 :
  * la modalité de paiement devient un choix unique (comptant, chèque, Interac, carte, autre) : l'ancien texte libre est
    converti d'après les mots qu'il contient (« Interac à la fin » -> Interac ; un texte sans mode, comme un
    acompte, -> Autre) ;
  * nouvelles protections dans la base : jamais de solde négatif, chantier « Terminé » verrouillé ;
  * la vue gagne la colonne archive (chantier terminé et réglé).

Changements v3 -> v4 :
  * nouveaux statuts : « Accepté » devient « À planifier », « Refusé » devient « Annulé » ;
    « En attente » est nouveau (soumission remise, réponse du client attendue) ;
  * l'heure prévue saisie à la main disparaît : les heures de passage sont calculées d'après l'ordre
    de la journée (nouvelle colonne ordre_jour, déduite de l'ancien ordre des heures).

Changements v2 -> v3 : colonne modalite_paiement ; la vue gagne attente_depuis.
Changements v1 -> v2 : plusieurs types de travaux par chantier (table chantier_travaux), une seule date
des travaux (date_realisee prime sur date_prevue), notes de chantier ajoutées à la description.

Rien n'est perdu : l'ancienne base est conservée dans data/sauvegardes/ avant tout changement,
et la nouvelle est vérifiée (nombre de lignes, intégrité) avant de la mettre en place.
Fermer l'interface avant de lancer ce script. Bibliothèque standard seulement.
"""
import argparse
import datetime
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCHEMA = RACINE / "schema" / "schema.sql"
TABLES = ("clients", "chantiers", "paiements")
VERSION_SCHEMA = 6


def _sql_chantiers(version):
    """INSERT ... SELECT des chantiers de l'ancienne base (schéma v<version>) vers le schéma actuel."""
    if version == 1:
        description = ("NULLIF(trim(COALESCE(description, '') || CASE WHEN trim(COALESCE(notes, '')) <> '' "
                       "THEN char(10) || notes ELSE '' END, char(10) || ' '), '')")
        date = "COALESCE(date_realisee, date_prevue)"
    else:
        description, date = "description", "date_prevue"
    if version >= 3:     # texte libre -> mode de paiement à choix unique
        m = "lower(modalite_paiement)"
        modalite = ("CASE WHEN modalite_paiement IS NULL OR trim(modalite_paiement) = '' THEN NULL"
                    f" WHEN {m} IN ('comptant', 'cheque', 'interac', 'carte', 'autre') THEN {m}"
                    f" WHEN {m} LIKE '%interac%' THEN 'interac'"
                    f" WHEN {m} LIKE '%cheque%' OR {m} LIKE '%chèque%' OR modalite_paiement LIKE '%CHÈQUE%' THEN 'cheque'"
                    f" WHEN {m} LIKE '%comptant%' THEN 'comptant' WHEN {m} LIKE '%carte%' THEN 'carte' ELSE 'autre' END")
    else:
        modalite = "NULL"
    statut = "CASE statut WHEN 'accepte' THEN 'a_planifier' WHEN 'refuse' THEN 'annule' ELSE statut END"
    if version >= 4:
        ordre = "ordre_jour"
    else:                # l'ordre de la journée se déduit des anciennes heures prévues
        ordre = ("CASE WHEN statut2 IN ('planifie', 'termine') THEN ROW_NUMBER() OVER "
                 "(PARTITION BY date2 ORDER BY COALESCE(heure_prevue, '99:99'), id) END")
    return (
        "INSERT INTO chantiers (id, client_id, description, statut, date_soumission, date_prevue, ordre_jour,"
        " duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq, modalite_paiement, numero_facture, date_facture,"
        " dossier_photos, fichier_papier, ref_papier, cree_le)"
        " SELECT id, client_id, description_, statut2, date_soumission, date2,"
        f"  {ordre},"
        "  duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq, modalite, numero_facture, date_facture,"
        "  dossier_photos, fichier_papier, ref_papier, cree_le"
        f" FROM (SELECT *, {description} AS description_, {statut} AS statut2, {date} AS date2, {modalite} AS modalite"
        "       FROM v1.chantiers)"
    )


def _cle(texte):
    sans_accents = "".join(c for c in unicodedata.normalize("NFKD", str(texte or "")) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.casefold()).strip()


def _attribuer_secteurs(conn):
    """Rattache chaque client à un secteur quand sa ville désigne UN SEUL secteur ; retourne le nombre de clients sans secteur."""
    secteurs = conn.execute("SELECT code, libelle, ville FROM secteurs").fetchall()
    for client_id, ville in conn.execute("SELECT id, ville FROM clients").fetchall():
        par_nom = [s for s in secteurs if _cle(s[1]) == _cle(ville)]
        par_ville = [s for s in secteurs if _cle(s[2]) == _cle(ville)]
        choix = par_nom if len(par_nom) == 1 else (par_ville if len(par_ville) == 1 else [])
        if choix:
            conn.execute("UPDATE clients SET secteur = ?, ville = ? WHERE id = ?", (choix[0][0], choix[0][2], client_id))
    return conn.execute("SELECT count(*) FROM clients WHERE secteur IS NULL").fetchone()[0]


def migrer(db_path):
    """Convertit la base. Retourne None si elle est déjà à jour, sinon un dict (sauvegarde, comptes)."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise SystemExit(f"Base introuvable : {db_path}")
    ancien = sqlite3.connect(db_path)
    version = ancien.execute("PRAGMA user_version").fetchone()[0]
    tables = {r[0] for r in ancien.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    ancien.close()
    if version == VERSION_SCHEMA:
        return None
    if version not in (1, 2, 3, 4, 5) or "sites" in tables:
        raise SystemExit("Format de base non pris en charge (version %s%s). Garde ce fichier et demande de l'aide."
                         % (version, ", avec une table sites" if "sites" in tables else ""))

    dossier_tmp = Path(tempfile.mkdtemp(prefix="migration_", dir=db_path.parent))
    try:
        conn = sqlite3.connect(dossier_tmp / "nouvelle.db", isolation_level=None)
        schema = SCHEMA.read_text(encoding="utf-8")
        conn.executescript(schema)
        # Les protections (solde négatif, verrou « Terminé ») sont retirées pendant la copie, puis remises : une
        # donnée ancienne qui les enfreint (trop-payé...) est copiée telle quelle et signalée, jamais perdue.
        declencheurs = re.findall(r"CREATE TRIGGER .*?\nEND;", schema, re.S)
        for (nom,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
            conn.execute(f"DROP TRIGGER {nom}")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("ATTACH DATABASE ? AS v1", (str(db_path),))
        conn.execute("BEGIN")
        conn.execute("INSERT OR IGNORE INTO types_travaux (code, libelle) SELECT code, libelle FROM v1.types_travaux")
        colonnes_client = ("id, prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, adresse, ville, province,"
                           " code_postal, latitude, longitude, geocode_statut, notes_acces, notes, cree_le")
        conn.execute(f"INSERT INTO clients ({colonnes_client}) SELECT {colonnes_client} FROM v1.clients")
        conn.execute(_sql_chantiers(version))
        if version == 1:
            conn.execute("INSERT INTO chantier_travaux (chantier_id, type_travaux, precision)"
                         " SELECT id, type_travaux, NULL FROM v1.chantiers")
        else:
            conn.execute("INSERT INTO chantier_travaux SELECT chantier_id, type_travaux, precision FROM v1.chantier_travaux")
        conn.execute("INSERT INTO paiements SELECT id, chantier_id, date_paiement, montant, mode, reference, notes, cree_le"
                     " FROM v1.paiements")
        conn.execute("COMMIT")
        for sql in declencheurs:
            conn.execute(sql)
        for t in TABLES:
            avant = conn.execute(f"SELECT count(*) FROM v1.{t}").fetchone()[0]
            apres = conn.execute(f"SELECT count(*) FROM main.{t}").fetchone()[0]
            if avant != apres:
                raise SystemExit(f"Vérification échouée : {t} avait {avant} lignes, la nouvelle base en a {apres}.")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchall():
            raise SystemExit("Vérification échouée : la nouvelle base est incohérente. Rien n'a été modifié.")
        compte = {t: conn.execute(f"SELECT count(*) FROM main.{t}").fetchone()[0] for t in TABLES}
        compte["sans_secteur"] = _attribuer_secteurs(conn)
        compte["soldes_negatifs"] = conn.execute("SELECT count(*) FROM v_chantiers WHERE solde < 0").fetchone()[0]
        conn.execute("DETACH DATABASE v1")
        conn.close()

        sauvegardes = db_path.parent / "sauvegardes"
        sauvegardes.mkdir(exist_ok=True)
        copie = sauvegardes / f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_avant_migration_v{version}.db"
        shutil.copy2(db_path, copie)
        try:
            os.replace(dossier_tmp / "nouvelle.db", db_path)
        except PermissionError:
            raise SystemExit("Impossible de remplacer la base : un autre programme l'utilise. "
                             "Ferme l'interface (et DB Browser) puis relance.")
        return {"sauvegarde": copie, **compte}
    finally:
        shutil.rmtree(dossier_tmp, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Convertit une base v1 à v5 vers le format actuel (v6).")
    p.add_argument("db", help="fichier de base à convertir (ex. data/sylvainculteur.db)")
    a = p.parse_args(argv)
    r = migrer(a.db)
    if r is None:
        print("Cette base est déjà au format actuel : rien à faire.")
        return 0
    print(f"Base convertie : {r['clients']} clients, {r['chantiers']} chantiers, {r['paiements']} paiements.\n"
          f"Ancienne version conservée : {r['sauvegarde']}")
    if r["sans_secteur"]:
        print(f"{r['sans_secteur']} client(s) n'ont pas encore de secteur (leur ville ne correspond pas à un seul secteur de la liste) : "
              "choisis-le dans leur fiche (« Modifier le client »), ou ajoute les secteurs manquants (page Secteurs).")
    if r["soldes_negatifs"]:
        print(f"ATTENTION : {r['soldes_negatifs']} chantier(s) ont un solde négatif hérité de l'ancienne base (payé plus que le total). "
              "Ils ont été copiés tels quels ; corrige leur prix ou leurs paiements (la règle interdit d'en créer de nouveaux).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
