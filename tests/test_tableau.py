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
SECTEURS = {"Blainville": "cap_de_la_madeleine", "Mirabel": "trois_rivieres_ouest", "Saint-Jérôme": "shawinigan"}    # ville -> secteur
LIBELLES_SECTEURS = {"Blainville": "Cap-de-la-Madeleine", "Mirabel": "Trois-Rivières-Ouest"}


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
            conn.execute("INSERT INTO clients (nom, adresse, ville, secteur, code_postal, telephone) VALUES (?, ?, ?, ?, ?, ?)",
                         (nom, f"1 Rue {nom}", ville, SECTEURS[ville], cp, "+14505550100"))
            cid = conn.execute("SELECT max(id) FROM clients").fetchone()[0]
            conn.execute("INSERT INTO chantiers (client_id, statut, date_soumission, duree_estimee_h, prix_ht, modalite_paiement) VALUES (?,?,?,?,?,?)",
                         (cid, statut, soumission, duree, prix, "cheque" if nom == "Urgent" else None))
            chid = conn.execute("SELECT max(id) FROM chantiers").fetchone()[0]
            for code, precision in types:
                conn.execute("INSERT INTO chantier_travaux VALUES (?,?,?)", (chid, code, precision))
            self.ids[nom] = chid
        # un chantier planifié demain (Mirabel) et un terminé non facturé
        for nom, statut, date, ville, prix in (("Demain", "planifie", dans(1), "Mirabel", 300), ("Fait", "termine", il_y_a(40), "Mirabel", 800)):
            conn.execute("INSERT INTO clients (nom, adresse, ville, secteur, code_postal) VALUES (?, ?, ?, ?, 'J7J 4D4')", (nom, f"2 Rue {nom}", ville, SECTEURS[ville]))
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
        conn.execute("INSERT INTO clients (nom, adresse, ville, secteur, code_postal) VALUES (?, '9 Rue X', 'Mirabel', 'trois_rivieres_ouest', 'J7J 4D4')", (nom,))
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
        entete = page[page.index("<header"):page.index("</header>")]
        self.assertEqual(re.findall(r'<a href="([^"]+)">([^<]+)</a>', entete),
                         [("/", "Tableau de bord"), ("/journee", "Journée"), ("/chantiers", "Chantiers"), ("/clients", "Clients")])
        self.assertNotIn("+ Nouveau</a>", entete)                                # le bouton est dans la page Clients
        self.assertIn('<a class="bouton" href="/nouveau">+ Nouveau client</a>', self.get("/clients")[1])


class TestChantiersListe(BaseTableau):
    """Ce que le Suivi montrait se retrouve dans Chantiers : délai d'attente, durée, montant, à facturer / à recevoir."""

    def test_attente_duree_et_montant(self):
        page = self.get("/chantiers")[1]
        self.assertIn(">45 j<", page)                                      # Urgent : 45 jours d'attente
        self.assertIn("a-urgente", page)
        self.assertIn("Durée 2 h 30", page)
        self.assertIn('class="montant"', page)
        self.assertIn("400,00 $", page)                                    # Urgent : 400 $, pas de taxes saisies
        self.assertIn("919,80 $", page)                                    # Fait : 800 + TPS + TVQ

    def test_a_recevoir(self):
        page = self.get("/chantiers", {"paiement": "a_recevoir"})[1]
        self.assertIn("Fait", page)
        self.assertNotIn("Urgent", page[page.index("<table"):])

    def test_html_est_echappe(self):
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE clients SET nom = '<script>alert(1)</script>' WHERE id = 1")
        conn.close()
        for chemin in ("/chantiers", "/journee", "/"):
            self.assertNotIn("<script>alert", self.get(chemin)[1], chemin)


class TestActionsRapides(BaseTableau):
    """Le statut n'est jamais choisi à la main : Planifié (ajout à une journée), À planifier (Retirer), Annulé (Annuler), Terminé (Terminer)."""

    def test_aucune_action_ne_choisit_un_statut(self):
        for chemin in ("/action/statut", "/action/facturer", "/action/encaisser"):
            self.assertTrue(self.post(chemin, {"chantier_id": str(self.ids["Demain"]), "statut": "termine", "retour": "/"})[0].startswith("404"), chemin)
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (self.ids["Demain"],)), [("planifie",)])

    def test_ajouter_a_une_journee_planifie_et_retirer_remet_a_planifier(self):
        i = self.ids["Urgent"]
        self.post("/journee/planifier", {"date": dans(3), f"sel_{i}": "1", "retour": "/journee"})
        self.assertEqual(self.sql("SELECT statut, date_prevue, ordre_jour FROM chantiers WHERE id = ?", (i,)), [("planifie", dans(3), 1)])
        _, en_tetes, _ = self.post("/action/retirer", {"chantier_id": str(i), "retour": "/"})
        self.assertIn("ok=retire", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut, date_prevue, ordre_jour FROM chantiers WHERE id = ?", (i,)), [("a_planifier", None, None)])

    def test_annuler_fait_disparaitre_de_la_journee_et_archive(self):
        i = self.ids["Demain"]
        self.assertIn("Demain", self.get("/journee", {"date": dans(1)})[1])
        _, en_tetes, _ = self.post("/action/annuler", {"chantier_id": str(i), "retour": f"/journee?date={dans(1)}"})
        self.assertEqual(en_tetes["Location"], f"/journee?date={dans(1)}&ok=annule")
        self.assertEqual(self.sql("SELECT statut, ordre_jour, archive FROM v_chantiers WHERE chantier_id = ?", (i,)), [("annule", None, 1)])
        self.assertNotIn("Demain", self.noms_dans(self.get("/journee", {"date": dans(1)})[1]))
        self.assertNotIn("Demain", self.noms_dans(self.get("/", {"date": dans(1)})[1]))
        chantiers = self.get("/chantiers")[1]
        self.assertNotIn("Demain", chantiers[:chantiers.index('id="archives"')])
        self.assertIn("Demain", chantiers[chantiers.index('id="archives"'):])

    def test_un_chantier_termine_ne_s_annule_pas_et_un_annule_se_rouvre(self):
        _, en_tetes, _ = self.post("/action/annuler", {"chantier_id": str(self.ids["Fait"]), "retour": "/"})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (self.ids["Fait"],)), [("termine",)])
        i = self.ids["Demain"]
        self.post("/action/annuler", {"chantier_id": str(i), "retour": "/"})
        _, en_tetes, _ = self.post("/action/rouvrir", {"chantier_id": str(i), "retour": "/"})
        self.assertIn("ok=rouvert", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut, date_prevue, archive FROM v_chantiers WHERE chantier_id = ?", (i,)), [("a_planifier", None, 0)])
        _, en_tetes, _ = self.post("/action/rouvrir", {"chantier_id": str(self.ids["Urgent"]), "retour": "/"})     # pas annulé
        self.assertIn("err=", en_tetes["Location"])

    def test_terminer_garde_la_date_et_reprend_la_duree(self):
        i = self.ids["Demain"]
        self.post("/action/terminer", {"chantier_id": str(i), "retour": "/"})
        self.assertEqual(self.sql("SELECT statut, date_prevue, duree_reelle_h FROM chantiers WHERE id = ?", (i,)), [("termine", dans(1), 3.0)])
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = ?", (i,)), [("a_payer",)])      # client facturé d'office
        _, en_tetes, _ = self.post("/action/terminer", {"chantier_id": str(self.ids["Urgent"]), "retour": "/"})     # pas planifié
        self.assertIn("err=", en_tetes["Location"])
        _, en_tetes, _ = self.post("/action/terminer", {"chantier_id": "9999", "retour": "/"})
        self.assertIn("err=", en_tetes["Location"])

    def test_plus_de_systeme_de_facture(self):
        i = self.ids["Fait"]
        self.assertTrue(self.post(f"/chantier/{i}/facturer", {})[0].startswith("404"))
        page = self.get(f"/chantier/{i}")[1]
        for absent in ("acturation", "acturer", "N° de facture", "date_facture"):
            self.assertNotIn(absent, page, absent)
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = ?", (i,)), [("a_payer",)])    # terminé = facturé d'office

    def test_le_bouton_terminer_ouvre_la_fenetre(self):
        i = self.ids["Demain"]
        for chemin in ("/", "/journee"):
            page = self.get(chemin, {"date": dans(1)})[1]
            self.assertIn(f"terminer={i}", page)
            self.assertIn(">Terminer</a>", page)
            self.assertNotIn("Terminer ce chantier", page)                   # la fenêtre n'est ouverte que sur demande
        fenetre = self.get("/", {"date": dans(1), "terminer": str(i)})[1]
        self.assertIn("Terminer ce chantier", fenetre)
        self.assertIn("Confirmes-tu que ce chantier est terminé ?", fenetre)
        self.assertIn("Le client a-t-il payé ?", fenetre)
        self.assertIn('name="paye" value="oui"', fenetre)
        self.assertIn("Pas encore payé", fenetre)
        self.assertIn("Oui, il est terminé", fenetre)
        self.assertRegex(fenetre, r'name="duree_reelle_h" value="3"')       # durée réelle préremplie avec l'estimée

    def test_la_fenetre_propose_le_mode_de_reglement_prevu(self):
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE chantiers SET modalite_paiement = 'cheque' WHERE id = ?", (self.ids["Demain"],))
        conn.close()
        fenetre = self.get("/journee", {"date": dans(1), "terminer": str(self.ids["Demain"])})[1]
        self.assertIn('<option value="cheque" selected>', fenetre)

    def test_terminer_pas_encore_paye(self):
        i = self.ids["Demain"]
        _, en_tetes, _ = self.post("/action/terminer", {"chantier_id": str(i), "paye": "non", "retour": f"/?date={dans(1)}&terminer={i}"})
        self.assertEqual(en_tetes["Location"], f"/?date={dans(1)}&ok=termine")
        self.assertEqual(self.sql("SELECT statut, archive, statut_paiement FROM v_chantiers WHERE chantier_id = ?", (i,)), [("termine", 0, "a_payer")])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(0,)])

    def test_terminer_et_paye_va_aux_archives(self):
        i = self.ids["Demain"]                                                # 300 $ + taxes = 344,93 $
        _, en_tetes, _ = self.post("/action/terminer", {"chantier_id": str(i), "paye": "oui", "mode": "carte", "montant": "1", "retour": "/"})
        self.assertIn("ok=termine_paye", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut, archive, statut_paiement, solde FROM v_chantiers WHERE chantier_id = ?", (i,)), [("termine", 1, "paye", 0.0)])
        self.assertEqual(self.sql("SELECT mode, date_paiement FROM paiements WHERE chantier_id = ?", (i,)), [("carte", AUJOURDHUI.isoformat())])
        chantiers = self.get("/chantiers")[1]
        self.assertIn("Demain", chantiers[chantiers.index('id="archives"'):])

    def test_terminer_refus(self):
        for chantier, extra in ((self.ids["Urgent"], {}), (self.ids["Fait"], {}), (9999, {}), (self.ids["Demain"], {"paye": "oui", "mode": "bitcoin"})):
            _, en_tetes, _ = self.post("/action/terminer", {"chantier_id": str(chantier), "retour": "/", **extra})
            self.assertIn("err=", en_tetes["Location"], (chantier, extra))
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (self.ids["Demain"],)), [("planifie",)])    # tout ou rien
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(0,)])

    def test_un_chantier_termine_n_a_plus_de_bouton_terminer(self):
        page = self.get("/journee", {"date": il_y_a(40)})[1]
        self.assertNotIn("terminer=", page)
        self.assertIn("Terminé", page)

    def test_aucun_paiement_ni_statut_sur_le_tableau_de_bord(self):
        for chemin in ("/", "/journee"):
            page = self.get(chemin, {"date": dans(1)})[1]
            self.assertNotIn("Encaisser", page, chemin)
            self.assertNotIn("Paiement</th>", page, chemin)
            self.assertNotIn("Statut</th>", page, chemin)
            self.assertNotIn('class="badge', page, chemin)

    def test_le_retour_ne_peut_pas_etre_une_adresse_externe(self):
        for retour in ("https://pirate.example/", "//pirate.example", "pirate", "/\\pirate.example", ""):
            _, en_tetes, _ = self.post("/action/retirer", {"chantier_id": str(self.ids["Demain"]), "retour": retour})
            self.assertTrue(en_tetes["Location"].startswith("/"), retour)
            self.assertFalse(en_tetes["Location"].startswith("//"), retour)
        self.assertTrue(en_tetes["Location"].startswith("/?"))

    def test_message_et_erreur_affiches(self):
        self.assertIn("Chantier annulé", self.get("/journee", {"ok": "annule"})[1])
        page = self.get("/journee", {"err": "<b>boom</b>"})[1]
        self.assertIn("Action refusée", page)
        self.assertNotIn("<b>boom</b>", page)


class TestJournee(BaseTableau):
    def test_page_de_la_journee(self):
        statut, page = self.get("/journee", {"date": dans(1)})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("1 chantier", page)
        self.assertIn("3 h", page)
        self.assertIn("7 h 30 à 10 h 30", page)                              # début 7 h 30, 3 h de travail
        self.assertEqual(self.noms_dans(page)[0], "Demain")
        self.assertIn('action="/action/retirer"', page)
        self.assertIn("Chantiers à placer", page)

    def test_candidats_filtres_et_tries(self):
        page = self.get("/journee", {"date": dans(2), "secteur": "Trois-Rivières-Ouest", "attente": "surveiller", "tri": "attente"})[1]
        candidats = page[page.index('id="lot"'):]
        self.assertEqual(self.noms_dans(candidats), ["Surveiller", "Limite7"])
        tous = self.get("/journee", {"date": dans(2), "tri": "secteur"})[1]
        self.assertIn("Secteur : Cap-de-la-Madeleine", tous)
        self.assertLess(tous.index("Secteur : Cap-de-la-Madeleine"), tous.index("Secteur : Trois-Rivières-Ouest"))
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
