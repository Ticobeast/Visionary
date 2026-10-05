"""Tests des pages clients et du formulaire simplifié de nouveau chantier (outils/pages_clients.py)."""
import datetime
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import fixtures  # noqa: E402
import interface  # noqa: E402



class BaseClients(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def get(self, chemin, query=None):
        statut, en_tetes, corps = interface.repondre(self.db, "GET", chemin, query or {})
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


class TestFicheClient(BaseClients):
    def test_liste_et_recherche(self):
        statut, page = self.get("/clients")
        for nom in ("Marie Gagnon", "Pierre Lavoie", "Luc Boucher"):
            self.assertIn(nom, page)
        self.assertIn("<th>Nom</th><th>Téléphone</th><th>Adresse</th></tr>", page)   # seulement ces trois colonnes
        for absent in ("Chantiers</th>", "recevoir", "2 029,45", "551,88", "$"):                   # ni compte, ni montants
            self.assertNotIn(absent, page[page.index("<table"):])
        self.assertIn("Marie Gagnon", self.get("/clients", {"q": "erables"})[1])
        self.assertNotIn("Pierre Lavoie", self.get("/clients", {"q": "erables"})[1])

    def test_fiche_client(self):
        statut, page = self.get("/client/1")
        self.assertTrue(statut.startswith("200"))
        self.assertIn("Marie Gagnon", page)
        self.assertIn("450-555-0142", page)
        self.assertIn("google.com/maps/search", page)
        self.assertIn("123%20Rue%20des%20%C3%89rables", page)              # adresse encodée dans le lien Maps
        self.assertIn('href="/client/1/chantier/nouveau"', page)
        self.assertIn('href="/chantier/1"', page)                          # historique
        historique = page[page.index("<table"):]
        self.assertNotIn("$", historique)                                  # pas de montants dans la fiche client
        self.assertNotIn("Solde", historique)
        self.assertTrue(self.get("/client/99")[0].startswith("404"))


class TestFormulaireSimplifie(BaseClients):
    def noms_des_champs(self, page):
        formulaire = page[page.index('<form method="post" action="/client/1/chantier/nouveau">'):]
        return set(re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', formulaire.split("</form>")[0]))

    def test_nom_et_adresse_verrouilles_et_champs_limites(self):
        statut, page = self.get("/client/1/chantier/nouveau")
        self.assertTrue(statut.startswith("200"))
        self.assertIn("Nom et adresse verrouillés", page)
        self.assertIn("Marie Gagnon", page)
        self.assertIn("123 Rue des Érables", page)
        champs = self.noms_des_champs(page)
        # seulement l'essentiel : travaux, date de la demande, durée estimée, prix, modalité de paiement, notes
        self.assertEqual({c for c in champs if not c.startswith(("type_", "precision_"))},
                         {"date_soumission", "duree_estimee_h", "prix_ht", "taxes_auto", "modalite_paiement", "description",
                          "nacelle", "debarrasser_bois", "bois_format"})
        self.assertIn(f'name="date_soumission" type="date" value="{datetime.date.today().isoformat()}"', page)   # aujourd'hui
        self.assertRegex(page, r'name="duree_estimee_h"[^>]*required')                                          # obligatoire
        self.assertEqual(re.findall(r'<option value="([a-z]*)"', page[page.index('name="modalite_paiement"'):]),
                         ["", "comptant", "cheque", "interac", "carte", "autre"])
        self.assertTrue({"type_elagage", "precision_elagage", "type_taille_haie"} <= champs)
        for interdit in ("client_nom", "client_prenom", "client_telephone", "adresse", "ville", "code_postal", "statut",
                         "date_prevue", "duree_reelle_h", "client_id"):
            self.assertNotIn(interdit, champs)

    def test_creation_simple(self):
        statut, en_tetes, _ = self.post("/client/1/chantier/nouveau", {
            "type_elagage": "1", "precision_elagage": "érable côté garage", "precision_taille_haie": "cèdres, 35 m",
            "nacelle": "1", "bois_format": "4_pieds",
            "prix_ht": "600,00", "taxes_auto": "1", "modalite_paiement": "interac", "duree_estimee_h": "2,5",
            "date_soumission": "2026-10-01",
            "description": "Appeler avant de venir."})
        self.assertEqual(en_tetes["Location"], "/chantier/4?ok=client_cree")
        self.assertEqual(self.sql("SELECT client_id, statut, date_prevue, prix_ht, tps, tvq, modalite_paiement, description, date_soumission, duree_estimee_h, duree_reelle_h FROM chantiers WHERE id = 4"),
                         [(1, "a_planifier", None, 600.0, 30.0, 59.85, "interac", "Appeler avant de venir.", "2026-10-01", 2.5, None)])
        self.assertEqual(self.sql("SELECT nacelle, debarrasser_bois, bois_format FROM chantiers WHERE id = 4"), [(1, 0, "4_pieds")])
        self.assertEqual(self.sql("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 4 ORDER BY 1"),
                         [("elagage", "érable côté garage"), ("taille_haie", "cèdres, 35 m")])
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])                # aucun doublon
        self.assertEqual(self.sql("SELECT statut_paiement, attente_depuis FROM v_chantiers WHERE chantier_id = 4")[0][0], "a_venir")
        self.assertIn('<option value="interac" selected>', self.get("/chantier/4")[1])
        self.assertIn("Chantier créé pour ce client", self.get("/chantier/4", {"ok": "client_cree"})[1])

    def test_le_serveur_ignore_toute_tentative_de_modifier_nom_et_adresse(self):
        avant = self.sql("SELECT * FROM clients ORDER BY id")
        self.post("/client/1/chantier/nouveau", {
            "type_emondage": "1", "duree_estimee_h": "2", "client_nom": "PIRATE", "client_prenom": "X", "adresse": "1 Rue Fausse", "ville": "Ailleurs",
            "client_telephone": "514-555-0199", "code_postal": "H0H 0H0", "latitude": "45.5", "longitude": "-73.5",
            "statut": "termine", "date_prevue": "2020-01-01", "client_id": "2"})
        self.assertEqual(self.sql("SELECT * FROM clients ORDER BY id"), avant)             # client intact
        self.assertEqual(self.sql("SELECT client_id, statut, date_prevue FROM chantiers WHERE id = 4"), [(1, "a_planifier", None)])

    def test_erreurs_gardent_les_valeurs(self):
        statut, _, page = self.post("/client/1/chantier/nouveau", {"prix_ht": "12,345", "modalite_paiement": "cheque", "description": "Mon texte"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("au moins un type de travaux", page)
        self.assertIn("prix_ht", page)
        self.assertIn('<option value="cheque" selected>', page)
        self.assertIn("duree_estimee_h est obligatoire", page)
        self.assertIn("Mon texte", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_options_du_travail_nacelle_et_bois(self):
        # abattage / élagage : débarrasser le bois OU préciser le format du bois laissé sur place
        statut, _, page = self.post("/client/1/chantier/nouveau", {"type_abattage": "1", "duree_estimee_h": "2"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("bois_format", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        for coche in ({"debarrasser_bois": "1"}, {"bois_format": "16_pouces"}):
            self.post("/client/1/chantier/nouveau", {"type_abattage": "1", "duree_estimee_h": "2", **coche})
        self.assertEqual(self.sql("SELECT nacelle, debarrasser_bois, bois_format FROM chantiers WHERE id > 3 ORDER BY id"), [(0, 1, None), (0, 0, "16_pouces")])
        # un format envoyé avec « débarrasser » est ignoré ; pour un autre type de travail, rien n'est exigé
        self.post("/client/1/chantier/nouveau", {"type_abattage": "1", "duree_estimee_h": "2", "debarrasser_bois": "1", "bois_format": "4_pieds"})
        self.post("/client/1/chantier/nouveau", {"type_taille_haie": "1", "duree_estimee_h": "2"})
        self.assertEqual(self.sql("SELECT debarrasser_bois, bois_format FROM chantiers WHERE id > 5 ORDER BY id"), [(1, None), (0, None)])
        statut, _, page = self.post("/client/1/chantier/nouveau", {"type_taille_haie": "1", "duree_estimee_h": "2", "bois_format": "10_pouces"})
        self.assertIn("bois_format", page)

    def test_options_visibles_sans_ouvrir_les_parametres_avances(self):
        page = self.get("/client/1/chantier/nouveau")[1]
        visible = page[:page.index('<details class="avance"')]
        for option in ("Nacelle requise", "Débarrasser le bois", "16 pouces", "4 pieds"):
            self.assertIn(option, visible)

    def test_duree_estimee_obligatoire(self):
        for duree in ("", "0", "30"):
            statut, _, page = self.post("/client/1/chantier/nouveau", {"type_emondage": "1", "duree_estimee_h": duree})
            self.assertTrue(statut.startswith("200"), duree)
            self.assertIn("duree_estimee_h", page, duree)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_modalite_inconnue_refusee(self):
        statut, _, page = self.post("/client/1/chantier/nouveau", {"type_emondage": "1", "duree_estimee_h": "2", "modalite_paiement": "Acompte puis chèque"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("modalite_paiement", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_client_inconnu(self):
        self.assertTrue(self.get("/client/99/chantier/nouveau")[0].startswith("404"))
        self.assertTrue(self.post("/client/99/chantier/nouveau", {"type_emondage": "1"})[0].startswith("404"))


class TestModifierClient(BaseClients):
    def formulaire(self):
        return {"client_nom": "Gagnon", "client_prenom": "Marie", "client_telephone": "+14505550142", "client_sms_ok": "1",
                "adresse": "123 Rue des Érables", "client_secteur": "shawinigan", "province": "QC", "code_postal": "G9N 1A1"}

    def test_modifier_telephone_et_notes(self):
        _, en_tetes, _ = self.post("/client/1/modifier", {**self.formulaire(), "client_telephone": "514-555-0123", "client_notes": "Préfère le matin"})
        self.assertEqual(en_tetes["Location"], "/client/1?ok=client_maj")
        self.assertEqual(self.sql("SELECT telephone, notes FROM clients WHERE id = 1"), [("+15145550123", "Préfère le matin")])

    def test_changer_l_adresse_efface_les_coordonnees(self):
        self.post("/client/2/modifier", {"client_nom": "Lavoie", "client_prenom": "Pierre", "client_telephone": "+14505550177",
                                         "client_sms_ok": "1", "adresse": "99 Chemin Neuf", "client_secteur": "nicolet", "province": "QC",
                                         "latitude": "45.648", "longitude": "-74.092"})
        self.assertEqual(self.sql("SELECT latitude, geocode_statut FROM clients WHERE id = 2"), [(None, "a_faire")])

    def test_le_secteur_donne_la_ville_et_est_obligatoire(self):
        self.post("/client/1/modifier", {**self.formulaire(), "client_secteur": "Cap de la Madeleine", "ville": "Trois Rivieres"})
        self.assertEqual(self.sql("SELECT secteur, ville FROM clients WHERE id = 1"), [("cap_de_la_madeleine", "Trois-Rivières")])   # la ville écrite à la main est ignorée
        for secteur in ("", "inconnu"):
            statut, _, page = self.post("/client/1/modifier", {**self.formulaire(), "client_secteur": secteur})
            self.assertTrue(statut.startswith("200"), secteur)
            self.assertIn("client_secteur", page)
        self.assertEqual(self.sql("SELECT secteur FROM clients WHERE id = 1"), [("cap_de_la_madeleine",)])

    def test_liste_filtree_par_secteur(self):
        self.post("/client/1/modifier", {**self.formulaire(), "client_secteur": "shawinigan"})
        page = self.get("/clients", {"secteur": "shawinigan"})[1]
        self.assertIn("Marie Gagnon", page)
        self.assertNotIn("Pierre Lavoie", page)
        self.assertIn("Shawinigan", page)                                  # le secteur est écrit sous l'adresse
        self.assertIn('<option value="shawinigan" selected>', page)
        self.assertIn("Aucun client", self.get("/clients", {"secteur": "nicolet"})[1])

    def test_erreur_de_validation(self):
        statut, _, page = self.post("/client/1/modifier", {**self.formulaire(), "client_telephone": "123"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("client_telephone", page)
        self.assertEqual(self.sql("SELECT telephone FROM clients WHERE id = 1"), [("+14505550142",)])


if __name__ == "__main__":
    unittest.main()
