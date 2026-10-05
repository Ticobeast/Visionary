"""Tests de la migration d'une base v1 vers v2 (outils/migrer.py)."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import migrer  # noqa: E402
import noyau  # noqa: E402


def base_v1(chemin):
    c = sqlite3.connect(chemin)
    c.executescript((RACINE / "tests" / "schema_v1.sql").read_text(encoding="utf-8"))
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("INSERT INTO types_travaux VALUES ('haubanage', 'Haubanage')")
    c.execute("INSERT INTO clients (id, prenom, nom, telephone, adresse, ville, notes, latitude, longitude, geocode_statut)"
              " VALUES (7, 'Marie', 'Gagnon', '+14505550142', '1 Rue A', 'Blainville', 'Préfère le matin', 45.7, -73.9, 'manuel')")
    c.execute("INSERT INTO clients (id, nom, adresse, ville) VALUES (8, 'Roy', '2 Rue B', 'Mirabel')")
    # fait un autre jour que prévu : la date réalisée doit gagner ; description + notes à fusionner
    c.execute("INSERT INTO chantiers (id, client_id, type_travaux, description, notes, statut, date_prevue, date_realisee, prix_ht, tps, tvq, date_facture)"
              " VALUES (11, 7, 'taille_haie', 'Haie de cèdres', 'Chien dans la cour', 'termine', '2026-06-10', '2026-06-14', 480, 24, 47.88, '2026-06-14')")
    c.execute("INSERT INTO chantiers (id, client_id, type_travaux, notes, statut, date_prevue) VALUES (12, 8, 'haubanage', 'Appeler avant', 'planifie', '2026-10-20')")
    c.execute("INSERT INTO chantiers (id, client_id, type_travaux, statut) VALUES (13, 8, 'emondage', 'soumission')")
    c.execute("INSERT INTO paiements (id, chantier_id, date_paiement, montant, mode, reference) VALUES (5, 11, '2026-06-14', 551.88, 'interac', 'ref1')")
    c.commit()
    c.close()


class TestMigration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "s.db"
        self.db.parent.mkdir()
        base_v1(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def sql(self, requete):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(requete).fetchall()
        finally:
            c.close()

    def test_migration_complete(self):
        r = migrer.migrer(self.db)
        self.assertEqual((r["clients"], r["chantiers"], r["paiements"]), (2, 3, 1))
        self.assertEqual(self.sql("PRAGMA user_version"), [(3,)])
        self.assertEqual(self.sql("PRAGMA integrity_check"), [("ok",)])
        self.assertEqual(self.sql("PRAGMA foreign_key_check"), [])
        # clients : identifiants, coordonnées et notes conservés
        self.assertEqual(self.sql("SELECT id, telephone, latitude, geocode_statut, notes FROM clients WHERE id = 7"),
                         [(7, "+14505550142", 45.7, "manuel", "Préfère le matin")])
        # une seule date : la date réalisée l'emporte ; notes fusionnées dans la description
        self.assertEqual(self.sql("SELECT id, statut, date_prevue, description FROM chantiers ORDER BY id"),
                         [(11, "termine", "2026-06-14", "Haie de cèdres\nChien dans la cour"),
                          (12, "planifie", "2026-10-20", "Appeler avant"),
                          (13, "soumission", None, None)])
        # l'ancien type devient un type sans précision (y compris un type ajouté par l'utilisateur)
        self.assertEqual(self.sql("SELECT chantier_id, type_travaux, precision FROM chantier_travaux ORDER BY chantier_id"),
                         [(11, "taille_haie", None), (12, "haubanage", None), (13, "emondage", None)])
        self.assertEqual(self.sql("SELECT libelle FROM types_travaux WHERE code = 'haubanage'"), [("Haubanage",)])
        # finances intactes
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = 11"), [("paye", 0.0)])
        # l'ancienne base est conservée, intacte
        copie = sqlite3.connect(r["sauvegarde"])
        self.assertEqual(copie.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(copie.execute("SELECT date_realisee FROM chantiers WHERE id = 11").fetchone()[0], "2026-06-14")
        copie.close()

    def test_deuxieme_passage_ne_fait_rien(self):
        migrer.migrer(self.db)
        self.assertIsNone(migrer.migrer(self.db))

    def test_ancienne_base_est_refusee_avec_instruction(self):
        with self.assertRaises(SystemExit) as e:
            noyau.ouvrir_base(self.db)
        self.assertIn("migrer.py", str(e.exception))
        self.assertIn("v1", str(e.exception))

    def test_base_avec_table_sites_non_prise_en_charge(self):
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE sites (id INTEGER PRIMARY KEY)")
        c.commit()
        c.close()
        with self.assertRaises(SystemExit):
            migrer.migrer(self.db)
        self.assertEqual(self.sql("PRAGMA user_version"), [(1,)])      # rien n'a été touché


def base_v2(chemin):
    c = sqlite3.connect(chemin)
    c.executescript((RACINE / "tests" / "schema_v2.sql").read_text(encoding="utf-8"))
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("INSERT INTO clients (id, nom, adresse, ville) VALUES (1, 'Roy', '2 Rue B', 'Mirabel')")
    c.execute("INSERT INTO chantiers (id, client_id, description, statut, date_soumission, date_prevue, prix_ht)"
              " VALUES (5, 1, 'Haie', 'termine', '2026-05-01', '2026-05-10', 300)")
    c.execute("INSERT INTO chantiers (id, client_id, statut) VALUES (6, 1, 'accepte')")
    c.execute("INSERT INTO chantier_travaux VALUES (5, 'taille_haie', 'cèdres')")
    c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (5, '2026-05-10', 300, 'comptant')")
    c.commit()
    c.close()


class TestMigrationV2(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "s.db"
        self.db.parent.mkdir()
        base_v2(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def sql(self, requete):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(requete).fetchall()
        finally:
            c.close()

    def test_v2_vers_v3_conserve_tout(self):
        r = migrer.migrer(self.db)
        self.assertEqual((r["clients"], r["chantiers"], r["paiements"]), (1, 2, 1))
        self.assertEqual(self.sql("PRAGMA user_version"), [(3,)])
        self.assertEqual(self.sql("PRAGMA integrity_check"), [("ok",)])
        self.assertEqual(self.sql("SELECT id, description, date_prevue, modalite_paiement FROM chantiers ORDER BY id"),
                         [(5, "Haie", "2026-05-10", None), (6, None, None, None)])
        self.assertEqual(self.sql("SELECT type_travaux, precision FROM chantier_travaux"), [("taille_haie", "cèdres")])
        # la nouvelle vue fonctionne : attente depuis la soumission, sinon depuis la création de la fiche
        vue = dict(self.sql("SELECT chantier_id, attente_depuis FROM v_chantiers"))
        self.assertEqual(vue[5], "2026-05-01")
        self.assertRegex(vue[6], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 5"), [("paye",)])
        copie = sqlite3.connect(r["sauvegarde"])
        self.assertEqual(copie.execute("PRAGMA user_version").fetchone()[0], 2)
        copie.close()
        self.assertIsNone(migrer.migrer(self.db))            # deuxième passage : rien à faire

    def test_la_base_migree_est_identique_a_une_base_neuve(self):
        migrer.migrer(self.db)
        neuve = sqlite3.connect(":memory:")
        neuve.executescript((RACINE / "schema" / "schema.sql").read_text(encoding="utf-8"))
        colonnes = lambda c: [(r[1], r[2], r[3]) for r in c.execute("PRAGMA table_info(chantiers)")]
        migree = sqlite3.connect(self.db)
        self.assertEqual(sorted(colonnes(migree)), sorted(colonnes(neuve)))
        self.assertEqual([r[1] for r in migree.execute("PRAGMA table_info(v_chantiers)")],
                         [r[1] for r in neuve.execute("PRAGMA table_info(v_chantiers)")])
        migree.close()

    def test_ancienne_base_v2_refusee_avec_instruction(self):
        with self.assertRaises(SystemExit) as e:
            noyau.ouvrir_base(self.db)
        self.assertIn("migrer.py", str(e.exception))


if __name__ == "__main__":
    unittest.main()
