"""Tests du tableau de bord, des actions rapides et des tournées (outils/tableau.py)."""
import datetime
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

AUJOURDHUI = datetime.date.today()


def il_y_a(jours):
    return (AUJOURDHUI - datetime.timedelta(days=jours)).isoformat()


def dans(jours):
    return (AUJOURDHUI + datetime.timedelta(days=jours)).isoformat()


class BaseTableau(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        conn, _ = noyau.ouvrir_base(self.db)
        self.ids = {}
        # nom, ville, code postal, statut, date_soumission, durée, prix
        for nom, ville, cp, statut, soumission, duree, prix, types in [
            ("Urgent", "Blainville", "J7C 1A1", "a_planifier", il_y_a(45), 2.5, 400, [("elagage", "érable")]),
            ("Surveiller", "Mirabel", "J7J 1A1", "a_planifier", il_y_a(15), 1.0, 250, [("taille_haie", None)]),
            ("Normal", "Blainville", "J7C 2B2", "a_planifier", il_y_a(3), None, 300, [("emondage", None)]),
            ("Limite7", "Mirabel", "J7J 2B2", "a_planifier", il_y_a(7), 2.0, 100, [("emondage", None)]),
            ("Limite31", "Mirabel", "J7J 3C3", "a_planifier", il_y_a(31), 2.0, 100, [("emondage", None)]),
            ("Devis", "Saint-Jérôme", "J7Z 1A1", "soumission", il_y_a(10), None, 500, [("abattage", None)]),
        ]:
            conn.execute("INSERT INTO clients (nom, adresse, ville, code_postal, telephone) VALUES (?, ?, ?, ?, ?)",
                         (nom, f"1 Rue {nom}", ville, cp, "+14505550100"))
            cid = conn.execute("SELECT max(id) FROM clients").fetchone()[0]
            conn.execute("INSERT INTO chantiers (client_id, statut, date_soumission, duree_estimee_h, prix_ht, modalite_paiement) VALUES (?,?,?,?,?,?)",
                         (cid, statut, soumission, duree, prix, "cheque" if nom == "Urgent" else None))
            chid = conn.execute("SELECT max(id) FROM chantiers").fetchone()[0]
            for code, precision in types:
                conn.execute("INSERT INTO chantier_travaux VALUES (?,?,?)", (chid, code, precision))
            self.ids[nom] = chid
        # un chantier planifié demain (Mirabel) et un terminé non facturé
        for nom, statut, date, ville, prix in (("Demain", "planifie", dans(1), "Mirabel", 300), ("Fait", "termine", il_y_a(40), "Mirabel", 800)):
            conn.execute("INSERT INTO clients (nom, adresse, ville, code_postal) VALUES (?, ?, ?, 'J7J 4D4')", (nom, f"2 Rue {nom}", ville))
            cid = conn.execute("SELECT max(id) FROM clients").fetchone()[0]
            conn.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, prix_ht, tps, tvq) VALUES (?,?,?,?,?,?,?)",
                         (cid, statut, date, 3.0 if nom == "Demain" else 2.0, prix, prix * 0.05, round(prix * 0.09975, 2)))
            chid = conn.execute("SELECT max(id) FROM chantiers").fetchone()[0]
            conn.execute("INSERT INTO chantier_travaux VALUES (?,'emondage',NULL)", (chid,))
            self.ids[nom] = chid
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    def terminer_sans_toucher(self, nom, prix, modalite=None):
        """Insère un chantier DÉJÀ terminé (non facturé) : une fois terminé, on ne peut plus le modifier."""
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("INSERT INTO clients (nom, adresse, ville, code_postal) VALUES (?, '9 Rue X', 'Mirabel', 'J7J 4D4')", (nom,))
        cid = conn.execute("SELECT max(id) FROM clients").fetchone()[0]
        conn.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, duree_reelle_h, prix_ht, modalite_paiement)"
                     " VALUES (?, 'termine', ?, 2, 2, ?, ?)", (cid, il_y_a(20), prix, modalite))
        chid = conn.execute("SELECT max(id) FROM chantiers").fetchone()[0]
        conn.execute("INSERT INTO chantier_travaux VALUES (?,'emondage',NULL)", (chid,))
        conn.close()
        return chid

    def get(self, chemin, query=None):
        statut, _, corps = interface.repondre(self.db, "GET", chemin, query or {})
        return statut, corps.decode("utf-8")

    def post(self, chemin, form):
        statut, en_tetes, corps = interface.repondre(self.db, "POST", chemin, {}, form)
        return statut, dict(en_tetes), corps.decode("utf-8")

    def sql(self, requete, args=()):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(requete, args).fetchall()
        finally:
            c.close()

    def noms_dans(self, page):
        return re.findall(r'<a href="/client/\d+">([^<]+)</a>', page)


class TestAttente(unittest.TestCase):
    def test_seuils(self):
        self.assertEqual([noyau.priorite(j) for j in (0, 6, 7, 30, 31, 400)],
                         ["normale", "normale", "surveiller", "surveiller", "urgente", "urgente"])
        self.assertEqual(noyau.jours_attente(il_y_a(12)), 12)
        self.assertEqual(noyau.jours_attente(dans(5)), 0)                 # jamais négatif
        self.assertEqual(noyau.jours_attente(None), 0)


class TestSuiviSupprime(BaseTableau):
    """Le Suivi n'existe plus (la Journée et Chantiers couvrent ses informations) ; les anciens liens ne cassent pas."""

    def test_anciens_liens_redirigent(self):
        statut, en_tetes, _ = interface.repondre(self.db, "GET", "/suivi", {"vue": "afacturer"})
        self.assertEqual((statut[:3], dict(en_tetes)["Location"]), ("303", "/chantiers"))
        statut, en_tetes, _ = interface.repondre(self.db, "GET", "/tournee", {"date": dans(2)})
        self.assertEqual((statut[:3], dict(en_tetes)["Location"]), ("303", f"/journee?date={dans(2)}"))

    def test_navigation_sans_suivi_ni_tournee_ni_archives(self):
        page = self.get("/")[1]
        entete = page[page.index("<header>"):page.index("</header>")]
        self.assertEqual(re.findall(r'<a href="([^"]+)">([^<]+)</a>', entete),
                         [("/", "Tableau de bord"), ("/journee", "Journée"), ("/chantiers", "Chantiers"), ("/clients", "Clients"), ("/nouveau", "+ Nouveau")])


class TestChantiersListe(BaseTableau):
    """Ce que le Suivi montrait se retrouve dans Chantiers : délai d'attente, durée, montant, à facturer / à recevoir."""

    def test_attente_duree_et_montant(self):
        page = self.get("/chantiers")[1]
        self.assertIn(">45 j<", page)                                      # Urgent : 45 jours d'attente
        self.assertIn("a-urgente", page)
        self.assertIn("⏱ 2 h 30", page)
        self.assertIn('class="montant"', page)
        self.assertIn("400,00 $", page)                                    # Urgent : 400 $, pas de taxes saisies
        self.assertIn("919,80 $", page)                                    # Fait : 800 + TPS + TVQ

    def test_a_facturer_a_recevoir(self):
        page = self.get("/chantiers", {"paiement": "non_facture"})[1]
        self.assertIn("Fait", page)
        self.assertNotIn("Urgent", page[page.index("<table"):])

    def test_html_est_echappe(self):
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE clients SET nom = '<script>alert(1)</script>' WHERE id = 1")
        conn.close()
        for chemin in ("/chantiers", "/journee", "/"):
            self.assertNotIn("<script>alert", self.get(chemin)[1], chemin)


class TestActionsRapides(BaseTableau):
    def test_changer_statut_vers_planifie_exige_une_date(self):
        i = self.ids["Normal"]
        _, en_tetes, _ = self.post("/action/statut", {"chantier_id": str(i), "statut": "planifie", "retour": "/journee?statut=a_planifier"})
        self.assertIn("err=", en_tetes["Location"])
        self.assertIn("date", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (i,)), [("a_planifier",)])
        # « Normal » n'a pas de durée estimée : refusé, et la durée envoyée par le formulaire est ignorée (elle se règle sur le chantier)
        _, en_tetes, _ = self.post("/action/statut", {"chantier_id": str(i), "statut": "planifie", "date_prevue": dans(3), "duree_estimee_h": "2,5",
                                                      "retour": "/journee?statut=a_planifier&tri=secteur"})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut, duree_estimee_h FROM chantiers WHERE id = ?", (i,)), [("a_planifier", None)])
        j = self.ids["Urgent"]
        _, en_tetes, _ = self.post("/action/statut", {"chantier_id": str(j), "statut": "planifie", "date_prevue": dans(3),
                                                      "retour": "/journee?statut=a_planifier&tri=secteur"})
        self.assertEqual(en_tetes["Location"], "/journee?statut=a_planifier&tri=secteur&ok=statut_change")   # on revient au même endroit
        self.assertEqual(self.sql("SELECT statut, date_prevue, duree_estimee_h FROM chantiers WHERE id = ?", (j,)), [("planifie", dans(3), 2.5)])

    def test_remettre_a_planifier_efface_la_date(self):
        i = self.ids["Demain"]
        self.post("/action/statut", {"chantier_id": str(i), "statut": "a_planifier", "date_prevue": dans(1), "retour": "/"})
        self.assertEqual(self.sql("SELECT statut, date_prevue, ordre_jour FROM chantiers WHERE id = ?", (i,)), [("a_planifier", None, None)])

    def test_terminer_garde_la_date(self):
        i = self.ids["Demain"]
        self.post("/action/statut", {"chantier_id": str(i), "statut": "termine", "retour": "/"})
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (i,)), [("termine", dans(1))])
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = ?", (i,)), [("non_facture",)])

    def test_statut_inconnu_ou_chantier_inexistant(self):
        _, en_tetes, _ = self.post("/action/statut", {"chantier_id": "9999", "statut": "a_planifier", "retour": "/"})
        self.assertIn("err=", en_tetes["Location"])
        _, en_tetes, _ = self.post("/action/statut", {"chantier_id": str(self.ids["Normal"]), "statut": "bidon", "retour": "/"})
        self.assertIn("err=", en_tetes["Location"])

    def test_facturer(self):
        i = self.ids["Fait"]
        _, en_tetes, _ = self.post("/action/facturer", {"chantier_id": str(i), "retour": "/chantiers?paiement=non_facture"})
        self.assertEqual(en_tetes["Location"], "/chantiers?paiement=non_facture&ok=facture")
        self.assertEqual(self.sql("SELECT date_facture FROM chantiers WHERE id = ?", (i,)), [(AUJOURDHUI.isoformat(),)])
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = ?", (i,)), [("a_payer",)])
        _, en_tetes, _ = self.post("/action/facturer", {"chantier_id": str(i), "retour": "/"})          # déjà facturé
        self.assertIn("err=", en_tetes["Location"])
        _, en_tetes, _ = self.post("/action/facturer", {"chantier_id": str(self.ids["Normal"]), "retour": "/"})   # pas terminé
        self.assertIn("err=", en_tetes["Location"])

    def test_facturer_sans_prix_refuse(self):
        i = self.terminer_sans_toucher("SansPrix", prix=None)           # un terminé est verrouillé : on l'insère tel quel
        _, en_tetes, _ = self.post("/action/facturer", {"chantier_id": str(i), "retour": "/"})
        self.assertIn("prix", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT date_facture FROM chantiers WHERE id = ?", (i,)), [(None,)])

    def test_encaisser_partiel_puis_solde(self):
        i = self.ids["Fait"]                                                 # 800 + 40 + 79,80 = 919,80 $
        page = self.get("/journee", {"date": il_y_a(40)})[1]
        self.assertIn('value="919.80"', page)                                # le formulaire propose le solde complet
        self.post("/action/encaisser", {"chantier_id": str(i), "montant": "400", "mode": "cheque", "retour": "/"})
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = ?", (i,)), [("partiel", 519.8)])
        _, en_tetes, _ = self.post("/action/encaisser", {"chantier_id": str(i), "montant": "519,80", "mode": "interac", "retour": "/journee?date=x"})
        self.assertEqual(en_tetes["Location"], "/journee?date=x&ok=encaisse")
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = ?", (i,)), [("paye", 0.0)])
        self.assertEqual(self.sql("SELECT date_paiement, mode FROM paiements WHERE chantier_id = ? ORDER BY id", (i,)),
                         [(AUJOURDHUI.isoformat(), "cheque"), (AUJOURDHUI.isoformat(), "interac")])

    def test_encaisser_invalide(self):
        i = self.ids["Fait"]
        for form in ({"montant": "", "mode": "interac"}, {"montant": "0", "mode": "interac"}, {"montant": "12,345", "mode": "interac"},
                     {"montant": "50", "mode": "bitcoin"}, {"montant": "50", "mode": ""}, {"montant": "abc", "mode": "interac"}):
            _, en_tetes, _ = self.post("/action/encaisser", {"chantier_id": str(i), "retour": "/", **form})
            self.assertIn("err=", en_tetes["Location"], form)
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(0,)])

    def test_le_mode_propose_suit_la_modalite(self):
        self.terminer_sans_toucher("ParCheque", prix=100, modalite="cheque")           # terminé il y a 20 jours
        page = self.get("/journee", {"date": il_y_a(20)})[1]
        self.assertIn('<option value="cheque" selected>', page)

    def test_le_retour_ne_peut_pas_etre_une_adresse_externe(self):
        for retour in ("https://pirate.example/", "//pirate.example", "pirate", "/\\pirate.example", ""):
            _, en_tetes, _ = self.post("/action/facturer", {"chantier_id": str(self.ids["Fait"]), "retour": retour})
            self.assertTrue(en_tetes["Location"].startswith("/"), retour)
            self.assertFalse(en_tetes["Location"].startswith("//"), retour)
        self.assertTrue(en_tetes["Location"].startswith("/?"))

    def test_message_et_erreur_affiches(self):
        self.assertIn("Statut mis à jour", self.get("/journee", {"ok": "statut_change"})[1])
        page = self.get("/journee", {"err": "<b>boom</b>"})[1]
        self.assertIn("Action refusée", page)
        self.assertNotIn("<b>boom</b>", page)


class TestJournee(BaseTableau):
    def test_page_de_la_journee(self):
        statut, page = self.get("/journee", {"date": dans(1)})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("1 chantier", page)
        self.assertIn("3 h", page)
        self.assertIn("7 h 30 → 10 h 30", page)                              # début 7 h 30, 3 h de travail
        self.assertEqual(self.noms_dans(page)[0], "Demain")
        self.assertIn('action="/action/retirer"', page)
        self.assertIn("Chantiers à placer", page)

    def test_candidats_filtres_et_tries(self):
        page = self.get("/journee", {"date": dans(2), "secteur": "Mirabel", "attente": "surveiller", "tri": "attente"})[1]
        candidats = page[page.index('id="lot"'):]
        self.assertEqual(self.noms_dans(candidats), ["Surveiller", "Limite7"])
        tous = self.get("/journee", {"date": dans(2), "tri": "secteur"})[1]
        self.assertIn("Secteur : Blainville", tous)
        self.assertLess(tous.index("Secteur : Blainville"), tous.index("Secteur : Mirabel"))
        self.assertNotIn('name="duree_', tous)                              # la durée ne se modifie pas ici : c'est celle du chantier
        self.assertIn("durée à estimer : ouvrir le chantier", tous)         # « Normal » n'a pas de durée : impossible à cocher
        self.assertIn('class="montant"', tous)
        self.assertIn('name="sel_', tous)
        soumissions = self.get("/journee", {"date": dans(2), "statut": "soumission"})[1]
        self.assertEqual(self.noms_dans(soumissions[soumissions.index('id="lot"'):]), ["Devis"])

    def test_planifier_plusieurs_chantiers_en_un_clic(self):
        a, b = self.ids["Urgent"], self.ids["Surveiller"]                     # 2,5 h et 1 h
        _, en_tetes, _ = self.post("/journee/planifier", {"date": dans(2), f"sel_{a}": "1", f"sel_{b}": "1", "retour": f"/journee?date={dans(2)}"})
        self.assertEqual(en_tetes["Location"], f"/journee?date={dans(2)}&ok=planifie_lot")
        self.assertEqual(self.sql("SELECT statut, date_prevue, duree_estimee_h FROM chantiers WHERE id IN (?, ?) ORDER BY id", (a, b)),
                         [("planifie", dans(2), 2.5), ("planifie", dans(2), 1.0)])
        page = self.get("/journee", {"date": dans(2)})[1]
        self.assertIn("2 chantiers", page)
        self.assertIn("3 h 30", page)                                          # durée totale
        self.assertIn("Total de la journée", page)
        self.assertIn("650,00 $", page)                                        # 400 $ + 250 $

    def test_la_duree_ne_se_saisit_pas_ici(self):
        n = self.ids["Normal"]                                                 # sans durée estimée
        _, en_tetes, _ = self.post("/journee/planifier", {"date": dans(2), f"sel_{n}": "1", f"duree_{n}": "2", "retour": "/journee"})
        self.assertIn("err=", en_tetes["Location"])                            # une durée envoyée quand même est ignorée
        self.assertEqual(self.sql("SELECT statut, duree_estimee_h FROM chantiers WHERE id = ?", (n,)), [("a_planifier", None)])

    def test_journee_trop_chargee(self):
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE chantiers SET duree_estimee_h = 9 WHERE id = ?", (self.ids["Demain"],))
        conn.close()
        self.assertIn("journée chargée", self.get("/journee", {"date": dans(1)})[1])

    def test_planification_tout_ou_rien(self):
        a, fait = self.ids["Urgent"], self.ids["Fait"]
        _, en_tetes, _ = self.post("/journee/planifier", {"date": dans(2), f"sel_{a}": "1", f"sel_{fait}": "1", "retour": "/journee"})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (a,)), [("a_planifier",)])      # rien n'a bougé
        for form in ({"date": dans(2)}, {"date": "", f"sel_{a}": "1"}, {"date": "2026-13-45", f"sel_{a}": "1"},
                     {"date": dans(2), f"sel_{self.ids['Normal']}": "1"}):
            _, en_tetes, _ = self.post("/journee/planifier", {"retour": "/journee", **form})
            self.assertIn("err=", en_tetes["Location"], form)
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (a,)), [("a_planifier",)])

    def test_deplacer_un_chantier_planifie_et_le_retirer(self):
        d = self.ids["Demain"]
        self.post("/journee/planifier", {"date": dans(4), f"sel_{d}": "1", "retour": "/journee"})
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (d,)), [("planifie", dans(4))])
        _, en_tetes, _ = self.post("/action/retirer", {"chantier_id": str(d), "retour": f"/journee?date={dans(4)}"})
        self.assertEqual(en_tetes["Location"], f"/journee?date={dans(4)}&ok=retire")
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (d,)), [("a_planifier", None)])

    def test_date_invalide_retombe_sur_demain(self):
        self.assertIn(dans(1), self.get("/journee", {"date": "pas une date"})[1])


if __name__ == "__main__":
    unittest.main()
