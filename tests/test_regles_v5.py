"""Tests des règles v5 au niveau du noyau et du schéma : durées, statut Terminé verrouillé, solde jamais négatif, archives."""
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import interface  # noqa: E402
import noyau  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        self.conn, _ = noyau.ouvrir_base(self.db)
        self.conn.execute("INSERT INTO clients (nom, adresse, ville) VALUES ('Roy', '1 Rue A', 'Mirabel')")

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def chantier(self, statut="a_planifier", duree=2.0, prix=None, tps=0, tvq=0, date=None):
        cur = self.conn.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, prix_ht, tps, tvq) VALUES (1,?,?,?,?,?,?)",
                                (statut, date, duree, prix, tps, tvq))
        self.conn.execute("INSERT INTO chantier_travaux VALUES (?, 'emondage', NULL)", (cur.lastrowid,))
        return cur.lastrowid

    def refuse(self, requete, args=()):
        with self.assertRaises(sqlite3.IntegrityError, msg=requete):
            self.conn.execute(requete, args)


class TestDureeEstimeeObligatoire(Base):
    def ligne(self, **perso):
        base = {"client_nom": "X", "adresse": "1 A", "ville": "V", "type_travaux": "emondage", "statut": "soumission"}
        base.update(perso)
        return noyau.lire_ligne(base, {"emondage": "emondage"}, False)

    def test_lire_ligne(self):
        for vide in ("", None, "0", "-1", "24,5"):
            _, erreurs = self.ligne(duree_estimee_h=vide)
            self.assertTrue(any("duree_estimee_h" in e for e in erreurs), repr(vide))
        v, erreurs = self.ligne(duree_estimee_h="2,5")
        self.assertEqual((erreurs, v["duree_estimee_h"]), ([], 2.5))

    def test_changer_statut_vers_planifie_ou_termine(self):
        i = self.chantier(duree=None)
        for statut in ("planifie", "termine"):
            erreurs = noyau.changer_statut(self.conn, i, statut, "2026-10-20")
            self.assertTrue(any("durée estimée" in e for e in erreurs), statut)
        self.assertEqual(noyau.changer_statut(self.conn, i, "planifie", "2026-10-20", duree="1,5"), [])

    def test_planifier_lot_exige_une_duree(self):
        a, b = self.chantier(duree=None), self.chantier(duree=3.0)
        erreurs = noyau.planifier_lot(self.conn, [a, b], "2026-10-20")
        self.assertTrue(any(f"chantier #{a}" in e and "durée" in e for e in erreurs))
        self.assertEqual(self.conn.execute("SELECT count(*) FROM chantiers WHERE statut = 'planifie'").fetchone()[0], 0)   # tout ou rien
        self.assertEqual(noyau.planifier_lot(self.conn, [a, b], "2026-10-20", {a: "1"}), [])


class TestDureeReelle(Base):
    def test_prerempli_avec_l_estimee_a_la_cloture(self):
        i = self.chantier(statut="planifie", duree=3.5, date="2026-10-20")
        self.assertEqual(noyau.changer_statut(self.conn, i, "termine"), [])
        self.assertEqual(self.conn.execute("SELECT duree_estimee_h, duree_reelle_h FROM chantiers WHERE id = ?", (i,)).fetchone(), (3.5, 3.5))

    def test_une_duree_reelle_saisie_est_conservee(self):
        i = self.chantier(statut="planifie", duree=3.5, date="2026-10-20")
        noyau.changer_statut(self.conn, i, "termine", duree_reelle="5")
        self.assertEqual(self.conn.execute("SELECT duree_reelle_h FROM chantiers WHERE id = ?", (i,)).fetchone(), (5.0,))

    def test_aucune_duree_reelle_avant_la_cloture(self):
        i = self.chantier(statut="planifie", duree=3.5, date="2026-10-20")
        self.assertIsNone(self.conn.execute("SELECT duree_reelle_h FROM chantiers WHERE id = ?", (i,)).fetchone()[0])

    def test_la_fenetre_terminer_propose_la_duree_estimee(self):
        i = self.chantier(statut="planifie", duree=3.5, prix=100, date="2026-10-20")
        self.conn.close()
        _, _, corps = interface.repondre(self.db, "GET", "/", {"terminer": str(i)})
        page = corps.decode()
        self.assertRegex(page, r'name="duree_reelle_h"[^>]*value="3[.,]5"')
        self.conn, _ = noyau.ouvrir_base(self.db)


class TestTermineVerrouille(Base):
    def termine(self):
        return self.chantier(statut="termine", duree=2, prix=100, tps=5, tvq=9.98, date="2026-10-01")

    def test_noyau_refuse_toute_modification_et_suppression(self):
        i = self.termine()
        for statut in ("planifie", "a_planifier", "soumission", "en_attente", "annule"):
            self.assertEqual(noyau.changer_statut(self.conn, i, statut, "2026-11-01"), [noyau.VERROU], statut)
        self.assertEqual(noyau.planifier_lot(self.conn, [i], "2026-11-01"), [f"chantier #{i} : ne peut pas être planifié (statut termine)"])
        self.assertTrue(noyau.supprimer_chantier(self.conn, i))
        self.assertEqual(self.conn.execute("SELECT statut FROM chantiers WHERE id = ?", (i,)).fetchone(), ("termine",))

    def test_le_schema_refuse_chaque_colonne_verrouillee(self):
        i = self.termine()
        self.conn.execute("INSERT INTO clients (nom, adresse, ville) VALUES ('Autre', '2 Rue B', 'Mirabel')")
        for colonne, valeur in (("statut", "'planifie'"), ("client_id", "2"), ("description", "'x'"), ("date_soumission", "'2026-01-01'"),
                                ("date_prevue", "'2026-11-01'"), ("duree_estimee_h", "9"), ("duree_reelle_h", "9"), ("prix_ht", "1"),
                                ("tps", "1"), ("tvq", "1"), ("modalite_paiement", "'carte'"), ("dossier_photos", "'photos/x'"),
                                ("fichier_papier", "'papier/x.pdf'"), ("ref_papier", "'x'")):
            self.refuse(f"UPDATE chantiers SET {colonne} = {valeur} WHERE id = {i}")
        self.refuse(f"DELETE FROM chantiers WHERE id = {i}")
        self.refuse(f"DELETE FROM chantier_travaux WHERE chantier_id = {i}")
        self.refuse(f"UPDATE chantier_travaux SET precision = 'x' WHERE chantier_id = {i}")

    def test_facturer_et_encaisser_restent_possibles(self):
        i = self.termine()
        self.assertEqual(noyau.facturer(self.conn, i, "2026-10-02", "2026-001"), [])
        self.assertEqual(noyau.encaisser(self.conn, i, "114,98", "interac", "2026-10-03"), [])
        self.assertEqual(self.conn.execute("SELECT statut_paiement, archive FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone(), ("paye", 1))

    def test_un_chantier_non_termine_se_modifie_et_se_supprime(self):
        i = self.chantier(prix=100)
        self.conn.execute("UPDATE chantiers SET description = 'ok' WHERE id = ?", (i,))
        self.assertEqual(noyau.supprimer_chantier(self.conn, i), [])


class TestSoldeJamaisNegatif(Base):
    def test_encaisser_ne_peut_pas_depasser_le_solde(self):
        i = self.chantier(prix=100, tps=5, tvq=9.98)                     # total 114,98 $
        for montant in ("114,99", "200", "0", "-1"):
            self.assertTrue(noyau.encaisser(self.conn, i, montant, "interac", "2026-10-03"), montant)
        self.assertEqual(noyau.encaisser(self.conn, i, "100", "interac", "2026-10-03"), [])
        self.assertTrue(noyau.encaisser(self.conn, i, "14,99", "interac", "2026-10-04"))
        self.assertEqual(noyau.encaisser(self.conn, i, "14,98", "interac", "2026-10-04"), [])
        self.assertEqual(self.conn.execute("SELECT solde FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone(), (0.0,))

    def test_triggers_du_schema(self):
        i = self.chantier(prix=100, tps=5, tvq=9.98)
        self.refuse("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?, '2026-10-03', 114.99, 'interac')", (i,))
        self.conn.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?, '2026-10-03', 50, 'interac')", (i,))
        self.refuse("UPDATE paiements SET montant = 120 WHERE chantier_id = ?", (i,))
        self.refuse("UPDATE chantiers SET prix_ht = 10, tps = 0, tvq = 0 WHERE id = ?", (i,))          # sous ce qui est déjà payé
        self.conn.execute("UPDATE chantiers SET prix_ht = 50, tps = 0, tvq = 0 WHERE id = ?", (i,))     # exactement ce qui est payé : permis
        j = self.chantier(prix=None)
        self.refuse("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?, '2026-10-03', 1, 'interac')", (j,))   # sans prix

    def test_un_seul_mode_de_paiement(self):
        i = self.chantier(prix=100)
        for mode in ("comptant", "cheque", "interac", "carte", "autre"):
            self.conn.execute("UPDATE chantiers SET modalite_paiement = ? WHERE id = ?", (mode, i))
        for refuse in ("Chèque + comptant", "3 versements", "cheque,interac", ""):
            self.refuse("UPDATE chantiers SET modalite_paiement = ? WHERE id = ?", (refuse, i))


class TestArchive(Base):
    def archive(self, i):
        return self.conn.execute("SELECT archive FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone()[0]

    def test_terminé_et_payé_seulement(self):
        termine_paye = self.chantier(statut="termine", prix=100, date="2026-10-01")
        termine_du = self.chantier(statut="termine", prix=100, date="2026-10-01")
        planifie_paye = self.chantier(statut="planifie", prix=100, date="2026-12-01")
        sans_prix = self.chantier(statut="termine", prix=None, date="2026-10-01")
        for i in (termine_paye, planifie_paye):
            self.conn.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?, '2026-10-03', 100, 'interac')", (i,))
        self.assertEqual([self.archive(i) for i in (termine_paye, termine_du, planifie_paye, sans_prix)], [1, 0, 0, 0])

    def test_une_fois_paye_l_archivage_est_automatique(self):
        i = self.chantier(statut="termine", prix=100, date="2026-10-01")
        self.assertEqual(self.archive(i), 0)
        noyau.encaisser(self.conn, i, "100", "carte", "2026-10-03")
        self.assertEqual(self.archive(i), 1)

    def test_annule_n_est_pas_archive(self):
        i = self.chantier(statut="annule", prix=100)
        self.assertEqual(self.archive(i), 0)


class TestDuplication(Base):
    def test_noyau(self):
        i = self.chantier(statut="termine", duree=3, prix=480, tps=24, tvq=47.88, date="2026-06-14")
        self.conn.execute("PRAGMA foreign_keys = ON")
        nouveau, erreurs = noyau.dupliquer_chantier(self.conn, i, prix_ht="500", avec_taxes=True, duree="4")
        self.assertEqual(erreurs, [])
        ligne = self.conn.execute("SELECT statut, date_prevue, ordre_jour, duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq, date_facture"
                                  " FROM chantiers WHERE id = ?", (nouveau,)).fetchone()
        self.assertEqual(ligne, ("soumission", None, None, 4.0, None, 500.0, 25.0, 49.88, None))
        self.assertEqual(self.conn.execute("SELECT date_soumission FROM chantiers WHERE id = ?", (nouveau,)).fetchone()[0],
                         noyau.datetime.date.today().isoformat())
        self.assertEqual(self.conn.execute("SELECT statut, prix_ht FROM chantiers WHERE id = ?", (i,)).fetchone(), ("termine", 480.0))

    def test_prix_et_taxes_repris_par_defaut(self):
        i = self.chantier(statut="termine", duree=3, prix=480, tps=24, tvq=47.88, date="2026-06-14")
        nouveau, _ = noyau.dupliquer_chantier(self.conn, i)
        self.assertEqual(self.conn.execute("SELECT prix_ht, tps, tvq, duree_estimee_h FROM chantiers WHERE id = ?", (nouveau,)).fetchone(), (480.0, 24.0, 47.88, 3.0))

    def test_donnees_invalides(self):
        i = self.chantier(duree=3, prix=480)
        for prix, duree in (("abc", "2"), ("-5", "2"), ("100", "0"), ("100", "30")):
            nouveau, erreurs = noyau.dupliquer_chantier(self.conn, i, prix_ht=prix, duree=duree)
            self.assertIsNone(nouveau)
            self.assertTrue(erreurs, (prix, duree))
        self.assertEqual(noyau.dupliquer_chantier(self.conn, 999)[1], ["chantier #999 introuvable"])


class TestOuvertureAncienneBase(unittest.TestCase):
    def test_v4_refusee_avec_instruction(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t) / "data" / "s.db"
            db.parent.mkdir()
            c = sqlite3.connect(db)
            c.executescript((RACINE / "tests" / "schema_v4.sql").read_text(encoding="utf-8"))
            c.close()
            with self.assertRaises(SystemExit) as e:
                noyau.ouvrir_base(db)
            self.assertIn("migrer.py", str(e.exception))
            self.assertIn("v4", str(e.exception))


if __name__ == "__main__":
    unittest.main()
