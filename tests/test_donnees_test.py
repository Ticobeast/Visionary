"""Tests du générateur de données d'essai (outils/donnees_test.py)."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import donnees_test  # noqa: E402


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
            self.assertTrue({"paye", "non_facture", "a_payer", "partiel", "a_venir"} <= statuts, statuts)
            self.assertGreater(c.execute("SELECT count(*) FROM v_chantiers WHERE statut = 'planifie' AND date_prevue > date('now')").fetchone()[0], 0)
            c.close()

    def test_refuse_la_vraie_base(self):
        with self.assertRaises(SystemExit):
            donnees_test.main(["--db", str(Path(tempfile.gettempdir()) / "sylvainculteur.db")])


if __name__ == "__main__":
    unittest.main()
