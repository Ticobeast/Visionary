"""Tests du générateur de données d'essai (outils/donnees_test.py)."""
import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import donnees_test  # noqa: E402
import noyau  # noqa: E402


class TestDonneesTest(unittest.TestCase):
    def test_base_coherente_et_variee(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            res = donnees_test.generer(db, nombre=60)
            self.assertEqual(res.chantiers, 60)
            c = sqlite3.connect(db)
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            statuts = {r[0] for r in c.execute("SELECT statut_paiement FROM v_chantiers")}
            self.assertTrue({"paye", "a_payer", "partiel", "a_venir"} <= statuts, statuts)
            self.assertGreater(c.execute("SELECT count(*) FROM v_chantiers WHERE statut = 'planifie' AND date_prevue > date('now')").fetchone()[0], 0)
            c.close()

    def test_le_conseil_affiche_ne_contient_pas_de_chemin_a_copier(self):
        # Un chemin Windows avec espaces et « (2) » cassait la commande copiée : on affiche une commande sans chemin.
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as sortie:
            donnees_test.main(["--db", str(Path(tmp) / "dossier (2)" / "test.db"), "--nombre", "5"])
        self.assertIn("--essai", sortie.getvalue())
        self.assertNotIn("--db", sortie.getvalue().split("L'essayer")[1])

    def test_detection_des_dossiers_synchronises(self):
        for chemin in ("C:/Users/x/OneDrive/Documents/SylvainCulteur/data/a.db", "/home/x/Dropbox/projet/a.db",
                       "/Users/x/Library/Mobile Documents/iCloud Drive/a.db".replace("iCloud Drive", "iCloud")):
            self.assertIsNotNone(noyau.service_nuage(chemin), chemin)
        self.assertIsNone(noyau.service_nuage("/home/x/SylvainCulteur/data/a.db"))

    def test_refuse_la_vraie_base(self):
        with self.assertRaises(SystemExit):
            donnees_test.main(["--db", str(Path(tempfile.gettempdir()) / "sylvainculteur.db")])


if __name__ == "__main__":
    unittest.main()
