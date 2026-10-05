"""Tests de la migration d'une ancienne base (v1 à v4) vers le format actuel (v6) : outils/migrer.py."""
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
    c.execute("INSERT INTO chantiers (id, client_id, type_travaux, statut) VALUES (14, 8, 'emondage', 'accepte')")
    c.execute("INSERT INTO chantiers (id, client_id, type_travaux, statut) VALUES (15, 8, 'emondage', 'refuse')")
    c.execute("INSERT INTO paiements (id, chantier_id, date_paiement, montant, mode, reference) VALUES (5, 11, '2026-06-14', 551.88, 'interac', 'ref1')")
    c.commit()
    c.close()


def base_v2_ou_v3(chemin, fixture):
    c = sqlite3.connect(chemin)
    c.executescript((RACINE / "tests" / fixture).read_text(encoding="utf-8"))
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("INSERT INTO clients (id, nom, adresse, ville) VALUES (1, 'Roy', '2 Rue B', 'Mirabel')")
    c.execute("INSERT INTO chantiers (id, client_id, description, statut, date_soumission, date_prevue, prix_ht)"
              " VALUES (5, 1, 'Haie', 'termine', '2026-05-01', '2026-05-10', 300)")
    # trois chantiers le même jour, avec des heures prévues dans le désordre : l'ordre doit suivre les heures
    for i, heure in ((6, "13:00"), (7, "08:00"), (8, None)):
        c.execute("INSERT INTO chantiers (id, client_id, statut, date_prevue, heure_prevue) VALUES (?, 1, 'planifie', '2026-10-20', ?)", (i, heure))
    c.execute("INSERT INTO chantiers (id, client_id, statut) VALUES (9, 1, 'accepte')")
    c.execute("INSERT INTO chantiers (id, client_id, statut) VALUES (10, 1, 'refuse')")
    for i in range(5, 11):
        c.execute("INSERT INTO chantier_travaux VALUES (?, 'taille_haie', ?)", (i, "cèdres" if i == 5 else None))
    c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (5, '2026-05-10', 300, 'comptant')")
    if fixture == "schema_v3.sql":
        c.execute("UPDATE chantiers SET modalite_paiement = 'Interac à la fin' WHERE id = 5")
    c.commit()
    c.close()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "s.db"
        self.db.parent.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def sql(self, requete):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(requete).fetchall()
        finally:
            c.close()

    def verifier_base_valide(self):
        self.assertEqual(self.sql("PRAGMA user_version"), [(6,)])
        self.assertEqual(self.sql("PRAGMA integrity_check"), [("ok",)])
        self.assertEqual(self.sql("PRAGMA foreign_key_check"), [])


class TestMigrationV1(Base):
    def test_migration_complete(self):
        base_v1(self.db)
        r = migrer.migrer(self.db)
        self.assertEqual((r["clients"], r["chantiers"], r["paiements"]), (2, 5, 1))
        self.verifier_base_valide()
        self.assertEqual(self.sql("SELECT id, telephone, latitude, geocode_statut, notes FROM clients WHERE id = 7"),
                         [(7, "+14505550142", 45.7, "manuel", "Préfère le matin")])
        # une seule date (la réalisée l'emporte), notes fusionnées, statuts convertis, ordre du jour attribué
        self.assertEqual(self.sql("SELECT id, statut, date_prevue, ordre_jour, description FROM chantiers ORDER BY id"),
                         [(11, "termine", "2026-06-14", 1, "Haie de cèdres\nChien dans la cour"),
                          (12, "planifie", "2026-10-20", 1, "Appeler avant"),
                          (13, "soumission", None, None, None),
                          (14, "a_planifier", None, None, None),      # Accepté -> À planifier
                          (15, "annule", None, None, None)])          # Refusé -> Annulé
        self.assertEqual(self.sql("SELECT chantier_id, type_travaux, precision FROM chantier_travaux ORDER BY chantier_id"),
                         [(11, "taille_haie", None), (12, "haubanage", None), (13, "emondage", None), (14, "emondage", None), (15, "emondage", None)])
        self.assertEqual(self.sql("SELECT libelle FROM types_travaux WHERE code = 'haubanage'"), [("Haubanage",)])
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = 11"), [("paye", 0.0)])
        copie = sqlite3.connect(r["sauvegarde"])
        self.assertEqual(copie.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(copie.execute("SELECT date_realisee FROM chantiers WHERE id = 11").fetchone()[0], "2026-06-14")
        copie.close()

    def test_base_avec_table_sites_non_prise_en_charge(self):
        base_v1(self.db)
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE sites (id INTEGER PRIMARY KEY)")
        c.commit()
        c.close()
        with self.assertRaises(SystemExit):
            migrer.migrer(self.db)
        self.assertEqual(self.sql("PRAGMA user_version"), [(1,)])      # rien n'a été touché


class TestMigrationV2V3(Base):
    def verifier(self, fixture, version):
        base_v2_ou_v3(self.db, fixture)
        r = migrer.migrer(self.db)
        self.assertEqual((r["clients"], r["chantiers"], r["paiements"]), (1, 6, 1))
        self.verifier_base_valide()
        self.assertEqual(self.sql("SELECT id, statut, date_prevue, ordre_jour FROM chantiers ORDER BY id"),
                         [(5, "termine", "2026-05-10", 1),
                          (6, "planifie", "2026-10-20", 2),            # 13:00 : après 08:00
                          (7, "planifie", "2026-10-20", 1),            # 08:00 : premier
                          (8, "planifie", "2026-10-20", 3),            # sans heure : à la fin
                          (9, "a_planifier", None, None),
                          (10, "annule", None, None)])
        self.assertEqual(self.sql("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 5"), [("taille_haie", "cèdres")])
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 5"), [("paye",)])
        copie = sqlite3.connect(r["sauvegarde"])
        self.assertEqual(copie.execute("PRAGMA user_version").fetchone()[0], version)
        copie.close()
        self.assertIsNone(migrer.migrer(self.db))            # deuxième passage : rien à faire

    def test_v2_vers_v6(self):
        self.verifier("schema_v2.sql", 2)

    def test_v3_vers_v6_convertit_la_modalite_en_choix_unique(self):
        self.verifier("schema_v3.sql", 3)
        self.assertEqual(self.sql("SELECT modalite_paiement FROM chantiers WHERE id = 5"), [("interac",)])

    def test_modalites_libres_converties_ou_rangees_dans_autre(self):
        base_v2_ou_v3(self.db, "schema_v3.sql")
        c = sqlite3.connect(self.db)
        for i, texte in ((6, "Chèque à la réception"), (7, "Acompte 500 $ puis solde comptant"), (8, "Virement"), (9, "  "), (10, "CARTE")):
            c.execute("UPDATE chantiers SET modalite_paiement = ? WHERE id = ?", (texte, i))
        c.commit()
        c.close()
        migrer.migrer(self.db)
        self.assertEqual(self.sql("SELECT id, modalite_paiement FROM chantiers WHERE id BETWEEN 6 AND 10 ORDER BY id"),
                         [(6, "cheque"), (7, "comptant"), (8, "autre"), (9, None), (10, "carte")])

    def test_v4_vers_v6(self):
        c = sqlite3.connect(self.db)
        c.executescript((RACINE / "tests" / "schema_v4.sql").read_text(encoding="utf-8"))
        c.execute("INSERT INTO clients (id, nom, adresse, ville) VALUES (1, 'Roy', '2 Rue B', 'Mirabel')")
        c.execute("INSERT INTO chantiers (id, client_id, statut, date_prevue, ordre_jour, duree_estimee_h, prix_ht, tps, tvq, modalite_paiement)"
                  " VALUES (1, 1, 'termine', '2026-05-10', 1, 2, 300, 15, 29.93, 'Chèque')")
        c.execute("INSERT INTO chantiers (id, client_id, statut, date_prevue, ordre_jour, duree_estimee_h) VALUES (2, 1, 'planifie', '2026-10-20', 1, 2)")
        c.execute("INSERT INTO chantier_travaux VALUES (1, 'taille_haie', 'cèdres')")
        c.execute("INSERT INTO chantier_travaux VALUES (2, 'emondage', NULL)")
        c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (1, '2026-05-10', 344.93, 'cheque')")
        c.commit()
        c.close()
        r = migrer.migrer(self.db)
        self.verifier_base_valide()
        self.assertEqual((r["clients"], r["chantiers"], r["paiements"], r["soldes_negatifs"]), (1, 2, 1, 0))
        self.assertEqual(self.sql("SELECT modalite_paiement, archive FROM v_chantiers ORDER BY chantier_id"), [("cheque", 1), (None, 0)])
        # les nouvelles protections sont en place après la migration
        c = sqlite3.connect(self.db)
        for requete in ("UPDATE chantiers SET prix_ht = 1 WHERE id = 1", "DELETE FROM chantiers WHERE id = 1",
                        "UPDATE chantiers SET modalite_paiement = 'Virement' WHERE id = 2",
                        "INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (1, '2026-10-01', 0.01, 'interac')"):
            with self.assertRaises(sqlite3.IntegrityError, msg=requete):
                c.execute(requete)
        c.close()

    def test_v5_vers_v6_secteurs_options_et_archive(self):
        c = sqlite3.connect(self.db)
        c.executescript((RACINE / "tests" / "schema_v5.sql").read_text(encoding="utf-8"))
        for i, ville in ((1, "Bécancour"), (2, "Trois Rivieres"), (3, "Blainville"), (4, "centre-ville"), (5, "Trois-Rivières")):
            c.execute("INSERT INTO clients (id, nom, adresse, ville) VALUES (?, ?, '1 Rue A', ?)", (i, f"C{i}", ville))
        c.execute("INSERT INTO chantiers (id, client_id, statut, duree_estimee_h, prix_ht) VALUES (1, 1, 'annule', 2, 100)")
        c.execute("INSERT INTO chantiers (id, client_id, statut, duree_estimee_h, prix_ht) VALUES (2, 2, 'a_planifier', 2, 100)")
        c.execute("INSERT INTO chantier_travaux VALUES (1, 'abattage', NULL)")
        c.execute("INSERT INTO chantier_travaux VALUES (2, 'emondage', NULL)")
        c.commit()
        c.close()
        r = migrer.migrer(self.db)
        self.verifier_base_valide()
        self.assertEqual((r["clients"], r["chantiers"]), (5, 2))
        # un secteur est attribué seulement quand la ville désigne UN SEUL secteur ; « Trois-Rivières » en a plusieurs
        self.assertEqual(self.sql("SELECT id, secteur, ville FROM clients ORDER BY id"),
                         [(1, "becancour", "Bécancour"), (2, None, "Trois Rivieres"), (3, None, "Blainville"),
                          (4, "centre_ville", "Trois-Rivières"), (5, None, "Trois-Rivières")])
        self.assertEqual(r["sans_secteur"], 3)
        self.assertEqual(self.sql("SELECT nacelle, debarrasser_bois, bois_format FROM chantiers ORDER BY id"), [(0, 0, None), (0, 0, None)])
        self.assertEqual(self.sql("SELECT chantier_id, archive FROM v_chantiers ORDER BY chantier_id"), [(1, 1), (2, 0)])      # l'annulé est archivé
        self.assertGreaterEqual(self.sql("SELECT count(*) FROM secteurs")[0][0], 10)

    def test_paiement_en_trop_herite_est_signale_sans_perte(self):
        c = sqlite3.connect(self.db)
        c.executescript((RACINE / "tests" / "schema_v4.sql").read_text(encoding="utf-8"))
        c.execute("INSERT INTO clients (id, nom, adresse, ville) VALUES (1, 'Roy', '2 Rue B', 'Mirabel')")
        c.execute("INSERT INTO chantiers (id, client_id, statut, prix_ht) VALUES (1, 1, 'a_planifier', 100)")
        c.execute("INSERT INTO chantier_travaux VALUES (1, 'emondage', NULL)")
        c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (1, '2026-05-10', 150, 'cheque')")
        c.commit()
        c.close()
        r = migrer.migrer(self.db)
        self.assertEqual(r["soldes_negatifs"], 1)                                      # signalé à l'utilisateur
        self.assertEqual(self.sql("SELECT montant FROM paiements"), [(150.0,)])        # rien n'est perdu ni modifié

    def test_la_base_migree_est_identique_a_une_base_neuve(self):
        base_v2_ou_v3(self.db, "schema_v3.sql")
        migrer.migrer(self.db)
        neuve = sqlite3.connect(":memory:")
        neuve.executescript((RACINE / "schema" / "schema.sql").read_text(encoding="utf-8"))
        migree = sqlite3.connect(self.db)
        for table in ("clients", "chantiers", "paiements", "chantier_travaux", "types_travaux", "v_chantiers"):
            colonnes = lambda c: [(r[1], r[2], r[3]) for r in c.execute(f"PRAGMA table_info({table})")]
            self.assertEqual(colonnes(migree), colonnes(neuve), table)
        migree.close()


class TestAncienneBaseRefusee(Base):
    def test_refus_avec_instruction(self):
        for fixture, version in (("schema_v2.sql", "v2"), ("schema_v3.sql", "v3"), ("schema_v4.sql", "v4"), ("schema_v5.sql", "v5")):
            if self.db.exists():
                self.db.unlink()
            if fixture in ("schema_v4.sql", "schema_v5.sql"):
                c = sqlite3.connect(self.db)
                c.executescript((RACINE / "tests" / fixture).read_text(encoding="utf-8"))
                c.close()
            else:
                base_v2_ou_v3(self.db, fixture)
            with self.assertRaises(SystemExit) as e:
                noyau.ouvrir_base(self.db)
            self.assertIn("migrer.py", str(e.exception))
            self.assertIn(version, str(e.exception))


if __name__ == "__main__":
    unittest.main()
