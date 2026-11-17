"""Tests des pages clients et du formulaire simplifié de nouvelle soumission (outils/pages_clients.py)."""
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
import noyau  # noqa: E402
from test_documents import texte_pdf  # noqa: E402



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
        self.assertIn('href="/client/1/soumission/nouveau"', page)
        self.assertIn("+ Nouvelle soumission", page)
        self.assertIn('href="/chantier/1"', page)                          # historique
        historique = page[page.index("<table"):]
        self.assertNotIn("$", historique)                                  # pas de montants dans la fiche client
        self.assertNotIn("Solde", historique)
        self.assertTrue(self.get("/client/99")[0].startswith("404"))


class TestFormulaireSimplifie(BaseClients):
    """Nouvelle SOUMISSION depuis la fiche d'un client : nom et adresse verrouillés, rien d'obligatoire."""
    NOUVELLE = "/client/1/soumission/nouveau"

    def noms_des_champs(self, page):
        formulaire = page[page.index(f'<form method="post" action="{self.NOUVELLE}">'):]
        return set(re.findall(r'<(?:input|select|textarea)[^>]*\bname="([^"]+)"', formulaire.split("</form>")[0]))

    def test_nom_et_adresse_verrouilles_et_champs_limites(self):
        statut, page = self.get(self.NOUVELLE)
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
        self.assertNotRegex(page, r'name="duree_estimee_h"[^>]*required')                                       # rien d'obligatoire
        self.assertNotIn("Rien n'est obligatoire", page)                                                        # plus de paragraphe d'aide
        self.assertEqual(re.findall(r'<option value="([a-z]*)"', page[page.index('name="modalite_paiement"'):]),
                         ["", "comptant", "cheque", "interac", "carte", "autre"])
        self.assertTrue({"type_elagage", "precision_elagage", "type_taille_haie"} <= champs)
        for interdit in ("client_nom", "client_prenom", "client_telephone", "adresse", "ville", "code_postal", "statut",
                         "date_prevue", "duree_reelle_h", "client_id"):
            self.assertNotIn(interdit, champs)

    def test_creation_simple(self):
        statut, en_tetes, _ = self.post(self.NOUVELLE, {
            "type_elagage": "1", "precision_elagage": "érable côté garage", "precision_taille_haie": "cèdres, 35 m",
            "nacelle": "1", "bois_format": "4_pieds",
            "prix_ht": "600,00", "taxes_auto": "1", "modalite_paiement": "interac", "duree_estimee_h": "2,5",
            "date_soumission": "2026-10-01",
            "description": "Appeler avant de venir."})
        self.assertEqual(en_tetes["Location"], "/soumission/4?ok=soumission_creee")                 # on arrive sur la soumission créée
        self.assertEqual(self.sql("SELECT client_id, statut, date_prevue, prix_ht, tps, tvq, modalite_paiement, description, date_soumission, duree_estimee_h, duree_reelle_h, accepte_le FROM chantiers WHERE id = 4"),
                         [(1, "soumission", None, 600.0, 30.0, 59.85, "interac", "Appeler avant de venir.", "2026-10-01", 2.5, None, None)])
        self.assertEqual(self.sql("SELECT nacelle, debarrasser_bois, bois_format FROM chantiers WHERE id = 4"), [(1, 0, "4_pieds")])
        self.assertEqual(self.sql("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 4 ORDER BY 1"),
                         [("elagage", "érable côté garage"), ("taille_haie", "cèdres, 35 m")])
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])                # aucun doublon
        self.assertEqual(self.sql("SELECT statut_paiement, genre FROM v_chantiers WHERE chantier_id = 4")[0], ("sans_objet", "soumission"))
        self.assertIn('<option value="interac" selected>', self.get("/soumission/4")[1])
        self.assertIn("Soumission créée", self.get("/client/1", {"ok": "soumission_creee"})[1])
        self.assertIn("/soumission/4", self.get("/client/1")[1])                           # elle apparaît dans la fiche du client

    def test_rien_n_est_obligatoire(self):
        statut, en_tetes, _ = self.post(self.NOUVELLE, {})
        self.assertEqual(en_tetes["Location"], "/soumission/4?ok=soumission_creee")
        self.assertEqual(self.sql("SELECT statut, duree_estimee_h, prix_ht FROM chantiers WHERE id = 4"), [("soumission", None, None)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantier_travaux WHERE chantier_id = 4"), [(0,)])

    def test_le_serveur_ignore_toute_tentative_de_modifier_nom_et_adresse(self):
        avant = self.sql("SELECT * FROM clients ORDER BY id")
        self.post(self.NOUVELLE, {
            "type_emondage": "1", "duree_estimee_h": "2", "client_nom": "PIRATE", "client_prenom": "X", "adresse": "1 Rue Fausse", "ville": "Ailleurs",
            "client_telephone": "514-555-0199", "code_postal": "H0H 0H0", "latitude": "45.5", "longitude": "-73.5",
            "statut": "termine", "date_prevue": "2020-01-01", "client_id": "2"})
        self.assertEqual(self.sql("SELECT * FROM clients ORDER BY id"), avant)             # client intact
        self.assertEqual(self.sql("SELECT client_id, statut, date_prevue FROM chantiers WHERE id = 4"), [(1, "soumission", None)])

    def test_erreurs_gardent_les_valeurs(self):
        statut, _, page = self.post(self.NOUVELLE, {"prix_ht": "12,345", "modalite_paiement": "cheque", "description": "Mon texte"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("prix_ht", page)
        self.assertNotIn("au moins un type de travaux", page)                              # facultatif dans une soumission
        self.assertNotIn("duree_estimee_h est obligatoire", page)
        self.assertIn('<option value="cheque" selected>', page)
        self.assertIn("Mon texte", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_options_du_travail_nacelle_et_bois(self):
        # dans une soumission, le sort du bois n'est pas obligatoire (il l'est pour accepter) ; un format inconnu reste refusé
        statut, en_tetes, _ = self.post(self.NOUVELLE, {"type_abattage": "1", "duree_estimee_h": "2"})
        self.assertTrue(statut.startswith("303"))
        for coche in ({"debarrasser_bois": "1"}, {"bois_format": "16_pouces"}):
            self.post(self.NOUVELLE, {"type_abattage": "1", "duree_estimee_h": "2", **coche})
        self.assertEqual(self.sql("SELECT nacelle, debarrasser_bois, bois_format FROM chantiers WHERE id > 3 ORDER BY id"),
                         [(0, 0, None), (0, 1, None), (0, 0, "16_pouces")])
        # un format envoyé avec « débarrasser » est ignoré
        self.post(self.NOUVELLE, {"type_abattage": "1", "duree_estimee_h": "2", "debarrasser_bois": "1", "bois_format": "4_pieds"})
        self.assertEqual(self.sql("SELECT debarrasser_bois, bois_format FROM chantiers WHERE id = 7"), [(1, None)])
        statut, _, page = self.post(self.NOUVELLE, {"type_taille_haie": "1", "duree_estimee_h": "2", "bois_format": "10_pouces"})
        self.assertIn("bois_format", page)

    def test_options_visibles_sans_ouvrir_les_parametres_avances(self):
        page = self.get(self.NOUVELLE)[1]
        visible = page[:page.index('<details class="avance"')]
        for option in ("Nacelle requise", "Débarrasser le bois", "16 pouces", "4 pieds"):
            self.assertIn(option, visible)

    def test_duree_facultative_mais_valable_si_ecrite(self):
        for duree in ("0", "30"):
            statut, _, page = self.post(self.NOUVELLE, {"type_emondage": "1", "duree_estimee_h": duree})
            self.assertTrue(statut.startswith("200"), duree)
            self.assertIn("duree_estimee_h", page, duree)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        self.assertTrue(self.post(self.NOUVELLE, {"type_emondage": "1", "duree_estimee_h": ""})[0].startswith("303"))

    def test_modalite_inconnue_refusee(self):
        statut, _, page = self.post(self.NOUVELLE, {"type_emondage": "1", "duree_estimee_h": "2", "modalite_paiement": "Acompte puis chèque"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("modalite_paiement", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_client_inconnu(self):
        self.assertTrue(self.get("/client/99/soumission/nouveau")[0].startswith("404"))
        self.assertTrue(self.post("/client/99/soumission/nouveau", {"type_emondage": "1"})[0].startswith("404"))

    def test_l_ancien_lien_chantier_nouveau_mene_a_la_soumission(self):
        statut, en_tetes, _ = interface.repondre(self.db, "GET", "/client/1/chantier/nouveau", {})
        self.assertEqual((statut[:3], dict(en_tetes)["Location"]), ("303", "/client/1/soumission/nouveau"))


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


class TestNouvelleAdresse(BaseClients):
    """Un client qui déménage : nouvelle fiche, l'ancienne garde son historique (format v14, clients.remplace_par)."""
    FORM = {"adresse": "45 Rue du Lac", "client_secteur": "shawinigan", "code_postal": "g9n 2b2", "notes_acces": "Porte arrière"}

    def deplacer(self, client_id=1, **perso):
        return self.post(f"/client/{client_id}/nouvelle-adresse", {**self.FORM, **perso})

    def sans_historique(self):
        """Un client qui n'a qu'une soumission : supprimable (les trois clients d'exemple ont tous un historique)."""
        self.post("/nouveau", {"client_nom": "Roy", "client_prenom": "Sylvie", "client_telephone": "450-555-0111", "adresse": "22 Rue des Pins",
                               "client_secteur": "centre_ville", "type_emondage": "1", "duree_estimee_h": "2"})
        return self.sql("SELECT max(id) FROM clients")[0][0]

    def test_creation_de_la_nouvelle_fiche_et_copie_des_coordonnees(self):
        statut, en_tetes, _ = self.deplacer()
        self.assertTrue(statut.startswith("303"))
        self.assertEqual(en_tetes["Location"], "/client/4?ok=nouvelle_adresse")                    # on arrive sur la NOUVELLE fiche
        self.assertEqual(self.sql("SELECT prenom, nom, telephone, courriel, sms_ok, notes FROM clients WHERE id = 4"),
                         self.sql("SELECT prenom, nom, telephone, courriel, sms_ok, notes FROM clients WHERE id = 1"))
        self.assertEqual(self.sql("SELECT adresse, ville, secteur, code_postal, notes_acces, latitude, longitude, geocode_statut, remplace_par FROM clients WHERE id = 4"),
                         [("45 Rue du Lac", "Shawinigan", "shawinigan", "G9N 2B2", "Porte arrière", None, None, "a_faire", None)])
        self.assertEqual(self.sql("SELECT remplace_par, adresse FROM clients WHERE id = 1"), [(4, "123 Rue des Érables")])   # l'ancienne fiche ne change pas d'adresse

    def test_l_historique_et_les_paiements_restent_sur_l_ancienne_fiche(self):
        avant = self.sql("SELECT id, client_id, statut, prix_ht FROM chantiers ORDER BY id")
        paiements = self.sql("SELECT p.id, c.client_id FROM paiements p JOIN chantiers c ON c.id = p.chantier_id ORDER BY p.id")
        self.deplacer()
        self.assertEqual(self.sql("SELECT id, client_id, statut, prix_ht FROM chantiers ORDER BY id"), avant)
        self.assertEqual(self.sql("SELECT p.id, c.client_id FROM paiements p JOIN chantiers c ON c.id = p.chantier_id ORDER BY p.id"), paiements)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE client_id = 4"), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE client_id = 1"), [(1,)])

    def test_un_ancien_chantier_garde_l_ancienne_adresse_dans_la_page_et_la_facture(self):
        self.deplacer()
        page = self.get("/chantier/1")[1]
        self.assertIn("123 Rue des Érables", page)
        self.assertNotIn("45 Rue du Lac", page)
        statut, _, corps = interface.repondre(self.db, "GET", "/facture/1/pdf", {})
        self.assertEqual(statut, "200 OK")
        texte = texte_pdf(corps)
        self.assertIn("123 Rue des Érables", texte)
        self.assertNotIn("45 Rue du Lac", texte)

    def test_refus(self):
        c, _ = noyau.ouvrir_base(self.db)
        try:
            self.assertEqual(noyau.nouvelle_adresse_client(c, 99, self.FORM)[0], None)
            self.assertIn("introuvable", noyau.nouvelle_adresse_client(c, 99, self.FORM)[1][0])
            self.assertIn("Écris la nouvelle adresse", noyau.nouvelle_adresse_client(c, 1, {**self.FORM, "adresse": "   "})[1][0])
            self.assertIn("secteur", noyau.nouvelle_adresse_client(c, 1, {**self.FORM, "client_secteur": ""})[1][0])
            self.assertIn("client_secteur", noyau.nouvelle_adresse_client(c, 1, {**self.FORM, "client_secteur": "nulle_part"})[1][0])
            self.assertIn("code_postal", noyau.nouvelle_adresse_client(c, 1, {**self.FORM, "code_postal": "zzz"})[1][0])
            # la même adresse (casse et espaces ignorés) : la fiche 3 est à Blainville
            c.execute("UPDATE clients SET adresse = '850 Boulevard du Lac', ville = 'Shawinigan', secteur = 'shawinigan' WHERE id = 3")
            nid, erreurs = noyau.nouvelle_adresse_client(c, 3, {**self.FORM, "adresse": "  850  boulevard DU lac "})
            self.assertIsNone(nid)
            self.assertIn("même adresse", erreurs[0])
            self.assertEqual(c.execute("SELECT count(*) FROM clients").fetchone()[0], 3)               # rien n'a été créé
            self.assertEqual(c.execute("SELECT count(*) FROM clients WHERE remplace_par IS NOT NULL").fetchone()[0], 0)
            # une fiche déjà remplacée ne peut pas l'être une deuxième fois
            nouveau, erreurs = noyau.nouvelle_adresse_client(c, 1, self.FORM)
            self.assertEqual(erreurs, [])
            nid, erreurs = noyau.nouvelle_adresse_client(c, 1, {**self.FORM, "adresse": "1 Rue Ailleurs"})
            self.assertIsNone(nid)
            self.assertIn("déjà une ancienne adresse", erreurs[0])
            self.assertEqual(c.execute("SELECT count(*) FROM clients").fetchone()[0], 4)
        finally:
            c.close()

    def test_erreur_dans_le_formulaire_ne_perd_rien(self):
        statut, _, page = self.deplacer(client_secteur="")
        self.assertTrue(statut.startswith("200"))
        self.assertIn("À corriger", page)
        for valeur in ("45 Rue du Lac", "g9n 2b2", "Porte arrière"):
            self.assertIn(valeur, page)
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        statut, _, page = self.deplacer(client_id=99)
        self.assertTrue(statut.startswith("404"))

    def test_le_formulaire_est_court(self):
        statut, page = self.get("/client/1/nouvelle-adresse")
        self.assertTrue(statut.startswith("200"))
        self.assertIn("Les anciens chantiers et factures gardent l'ancienne adresse.", page)
        corps = page[page.index("<form"):]
        self.assertEqual(sorted(set(re.findall(r'name="([^"]+)"', corps))), ["adresse", "client_secteur", "code_postal", "notes_acces"])
        self.assertIn("Enregistrer la nouvelle adresse", page)
        self.assertRegex(page, r'<a class="bouton secondaire annuler" href="/client/1">Annuler</a>')
        self.assertNotIn("Paramètres avancés", page)
        self.assertTrue(self.get("/client/99/nouvelle-adresse")[0].startswith("404"))

    def test_le_bouton_depend_de_l_historique(self):
        page = self.get("/client/1")[1]                                                 # historique (chantier terminé) : le bouton est là
        self.assertRegex(page, r'<a class="bouton secondaire" href="/client/1/nouvelle-adresse">Nouvelle adresse</a>')
        libre = self.sans_historique()
        page = self.get(f"/client/{libre}")[1]                                          # sans historique : « Modifier le client » suffit
        self.assertNotIn("nouvelle-adresse", page)
        self.assertIn("Modifier le client", page)
        self.deplacer()
        self.assertNotIn("/client/1/nouvelle-adresse", self.get("/client/1")[1])       # déjà une ancienne adresse
        self.assertNotIn("nouvelle-adresse", self.get("/client/4")[1])                  # la nouvelle fiche n'a pas encore d'historique

    def test_fiches_ancienne_et_nouvelle(self):
        self.deplacer()
        ancienne = self.get("/client/1")[1]
        self.assertIn("Ancienne adresse</span>", ancienne)                                # pastille près du nom
        self.assertIn('<b>Nouvelle adresse :</b> <a href="/client/4">45 Rue du Lac</a>', ancienne)
        self.assertNotIn("+ Nouvelle soumission", ancienne)
        self.assertNotIn("/client/1/nouvelle-adresse", ancienne)
        self.assertIn("Modifier le client", ancienne)
        self.assertIn("123 Rue des Érables", ancienne)
        nouvelle = self.get("/client/4")[1]
        self.assertIn('<b>Ancienne adresse :</b> <a href="/client/1">123 Rue des Érables</a>', nouvelle)
        self.assertIn("+ Nouvelle soumission", nouvelle)
        self.assertNotIn("Nouvelle adresse :", nouvelle)

    def test_nouvelle_soumission_redirigee_vers_la_nouvelle_fiche(self):
        self.deplacer()
        statut, page = self.get("/client/1/soumission/nouveau")
        self.assertTrue(statut.startswith("303") or statut.startswith("302"), statut)
        statut, en_tetes, _ = self.post("/client/1/soumission/nouveau", {"type_emondage": "1"})
        self.assertEqual(en_tetes["Location"], "/client/4/soumission/nouveau")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])               # rien n'a été créé sur l'ancienne fiche
        self.assertTrue(self.get("/client/4/soumission/nouveau")[0].startswith("200"))
        # la chaîne est suivie : la nouvelle fiche déménage à son tour
        self.deplacer(client_id=4, adresse="7 Rue Finale")
        _, en_tetes, _ = self.post("/client/1/soumission/nouveau", {})
        self.assertEqual(en_tetes["Location"], "/client/5/soumission/nouveau")
        # une boucle (impossible avec les règles, mais pas impossible à la main) ne fait pas tourner le serveur
        c = sqlite3.connect(self.db)
        c.execute("UPDATE clients SET remplace_par = 1 WHERE id = 5")
        c.commit()
        c.close()
        c = sqlite3.connect(self.db)
        try:
            self.assertEqual(noyau.client_remplacant(c, 1), 5)
        finally:
            c.close()

    def test_la_liste_garde_les_anciennes_fiches_avec_une_mention(self):
        self.deplacer()
        page = self.get("/clients")[1]
        self.assertEqual(page.count("Marie Gagnon"), 2)                                   # l'ancienne et la nouvelle
        self.assertEqual(page.count("ancienne adresse"), 1)
        ligne = page[page.index('href="/client/1"'):]
        self.assertIn("ancienne adresse</div>", ligne[:ligne.index("</tr>")])
        nouvelle = page[page.index('href="/client/4"'):]
        self.assertNotIn("ancienne adresse", nouvelle[:nouvelle.index("</tr>")])

    def test_le_choix_d_un_client_et_les_doublons_ignorent_l_ancienne_fiche(self):
        self.deplacer()
        page = self.get("/nouveau", {"q": "Gagnon"})[1]
        self.assertIn('href="/client/4"', page)
        self.assertNotIn('href="/client/1"', page)
        c, _ = noyau.ouvrir_base(self.db)
        try:
            idx = noyau.Index(c)
            self.assertNotIn(1, idx.infos)
            self.assertIn(4, idx.infos)
            self.assertIsNone(idx.ailleurs({"client_telephone": "+14505550999", "client_telephone_2": None}))
            self.assertEqual(idx.ailleurs({"client_telephone": "+14505550142", "client_telephone_2": None}), 4)      # le téléphone mène à la fiche actuelle
            v = {"adresse": "123 Rue des Érables", "ville": "Saint-Jérôme", "client_prenom": "Marie", "client_nom": "Gagnon",
                 "client_entreprise": None, "client_telephone": "+14505550142", "client_telephone_2": None}
            self.assertEqual(idx.trouver(v), (None, None))                                  # la vieille adresse n'est plus réutilisée
        finally:
            c.close()

    def test_supprimer_la_nouvelle_fiche_rend_l_ancienne_normale(self):
        self.deplacer()
        self.assertEqual(self.sql("SELECT remplace_par FROM clients WHERE id = 1"), [(4,)])
        c, _ = noyau.ouvrir_base(self.db)
        try:
            with noyau.transaction(c):
                self.assertEqual(noyau.supprimer_client(c, 4), [])
        finally:
            c.close()
        self.assertEqual(self.sql("SELECT remplace_par FROM clients WHERE id = 1"), [(None,)])
        page = self.get("/client/1")[1]
        self.assertIn("+ Nouvelle soumission", page)
        self.assertNotIn("Ancienne adresse", page)
        self.assertNotIn("ancienne adresse", self.get("/clients")[1])

    def test_une_fiche_ne_peut_pas_se_remplacer_elle_meme(self):
        c = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("UPDATE clients SET remplace_par = id WHERE id = 1")
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()


class TestFusion(BaseClients):
    """Deux fiches du même client : la fiche en double est cachée (clients.fusionne_dans), jamais supprimée (format v15).
    Fiches d'exemple : 1 Marie Gagnon (chantier 1, terminé et payé). Le doublon est la fiche 4, créée ici avec un chantier de chaque sorte."""

    def doublon(self):
        c = sqlite3.connect(self.db, isolation_level=None)
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("UPDATE clients SET telephone_2 = NULL, courriel = NULL, notes = NULL WHERE id = 1")
        c.execute("INSERT INTO clients (prenom, nom, telephone, telephone_2, courriel, adresse, ville, secteur, code_postal, notes_acces, notes)"
                  " VALUES ('Marie', 'Gagnon', '+14505550199', '+14505550188', 'marie.autre@example.com', '5 Rue Voisine', 'Saint-Jérôme',"
                  " 'centre_ville', 'J7Z 2B2', 'Barrière verte', 'Aime les cèdres')")
        for statut, accepte, prevue in (("soumission", None, None), ("a_planifier", "2026-09-04", None), ("planifie", "2026-09-04", "2026-12-01"),
                                        ("annule", "2026-07-02", None), ("annule", None, None), ("termine", "2026-08-03", "2026-08-10")):
            c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, accepte_le, date_prevue, duree_estimee_h, prix_ht, tps, tvq)"
                      " VALUES (4, ?, '2026-08-01', ?, ?, 2, 200, 10, 19.95)", (statut, accepte, prevue))
        c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (9, '2026-08-11', 100, 'interac')")
        c.close()
        return 4

    def fusionner(self, garde=1, doublon=4):
        return self.post(f"/client/{garde}/fusionner", {"avec": str(doublon)})

    def conn(self):
        c, _ = noyau.ouvrir_base(self.db)
        return c

    def test_fusion_simple_par_la_page(self):
        self.doublon()
        statut, en_tetes, _ = self.fusionner()
        self.assertTrue(statut.startswith("303"))
        self.assertEqual(en_tetes["Location"], "/client/1?ok=fusion")
        self.assertEqual(self.sql("SELECT id, fusionne_dans FROM clients ORDER BY id"), [(1, None), (2, None), (3, None), (4, 1)])
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(4,)])                                  # rien n'est supprimé
        self.assertIn("Les deux fiches sont fusionnées", self.get("/client/1", {"ok": "fusion"})[1])
        self.assertEqual(self.sql("SELECT nom, prenom, adresse, ville FROM clients WHERE id = 1"),
                         [("Gagnon", "Marie", "123 Rue des Érables", "Saint-Jérôme")])                      # nom et adresse de la fiche gardée : intacts

    def test_les_fiches_non_terminees_sont_deplacees_les_terminees_restent(self):
        self.doublon()
        self.fusionner()
        self.assertEqual(self.sql("SELECT id, client_id, statut FROM chantiers WHERE id >= 4 ORDER BY id"),
                         [(4, 1, "soumission"), (5, 1, "a_planifier"), (6, 1, "planifie"), (7, 1, "annule"), (8, 1, "annule"), (9, 4, "termine")])
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id IN (1, 2, 3) ORDER BY id"), [(1,), (2,), (3,)])

    def test_les_paiements_ne_bougent_pas(self):
        self.doublon()
        avant = self.sql("SELECT p.id, p.chantier_id, p.montant, c.client_id FROM paiements p JOIN chantiers c ON c.id = p.chantier_id ORDER BY p.id")
        self.fusionner()
        apres = self.sql("SELECT p.id, p.chantier_id, p.montant, c.client_id FROM paiements p JOIN chantiers c ON c.id = p.chantier_id ORDER BY p.id")
        self.assertEqual(apres, avant)
        self.assertIn((9, 4), [(a[1], a[3]) for a in apres])

    def test_l_historique_de_la_fiche_gardee_inclut_le_chantier_termine_du_doublon(self):
        self.doublon()
        avant = self.get("/client/1")[1]
        self.assertNotIn('href="/chantier/9"', avant)
        self.fusionner()
        page = self.get("/client/1")[1]
        historique = page[page.index('<table class="historique"'):]
        for i in (1, 4, 5, 6, 7, 8, 9):
            self.assertRegex(historique, rf'href="/(chantier|soumission)/{i}"', i)                            # tous sur la fiche gardée
        self.assertNotIn("fusionn", historique.lower().split("</table>")[0])                                   # sans mention spéciale
        self.assertNotIn("5 Rue Voisine", historique)

    def test_facture_du_chantier_termine_du_doublon_inchangee(self):
        self.doublon()
        _, _, avant = interface.repondre(self.db, "GET", "/facture/9/pdf", {})
        texte = texte_pdf(avant)
        self.assertIn("5 Rue Voisine", texte)
        self.fusionner()
        statut, _, apres = interface.repondre(self.db, "GET", "/facture/9/pdf", {})
        self.assertEqual(statut, "200 OK")
        self.assertEqual(texte_pdf(apres), texte)                                                           # même nom, même adresse d'origine
        page = self.get("/chantier/9")[1]
        self.assertIn("5 Rue Voisine", page)                                                                # la carte du client : coordonnées d'origine
        self.assertIn('href="/client/4"', page)                                                             # « Fiche client » : le lien passe par la redirection
        statut, en_tetes, _ = self.post("/client/4/supprimer", {})
        self.assertEqual(en_tetes["Location"], "/client/1")

    def test_champs_vides_recopies_et_second_telephone(self):
        self.doublon()
        c = self.conn()
        try:
            c.execute("UPDATE clients SET code_postal = NULL, notes = NULL WHERE id = 1")
            c.commit()
            self.assertEqual(noyau.fusionner_clients(c, 1, 4), [])
            c.commit()
        finally:
            c.close()
        self.assertEqual(self.sql("SELECT telephone, telephone_2, courriel, code_postal, notes_acces, notes FROM clients WHERE id = 1"),
                         [("+14505550142", "+14505550199", "marie.autre@example.com", "J7Z 2B2", "Barrière verte", "Aime les cèdres")])

    def test_un_champ_rempli_n_est_jamais_ecrase(self):
        self.doublon()
        c = self.conn()
        try:
            c.execute("UPDATE clients SET telephone_2 = '+14505550111', courriel = 'garde@example.com', notes = 'Ma note' WHERE id = 1")
            c.commit()
            self.assertEqual(noyau.fusionner_clients(c, 1, 4), [])
            c.commit()
            self.assertEqual(c.execute("SELECT telephone, telephone_2, courriel, notes FROM clients WHERE id = 1").fetchone(),
                             ("+14505550142", "+14505550111", "garde@example.com", "Ma note"))
        finally:
            c.close()

    def test_meme_telephone_pas_de_second_numero_en_double(self):
        self.doublon()
        c = self.conn()
        try:
            c.execute("UPDATE clients SET telephone = '+14505550142', telephone_2 = NULL WHERE id IN (1, 4)")
            c.execute("UPDATE clients SET telephone_2 = '+14505550142' WHERE id = 4")
            c.commit()
            self.assertEqual(noyau.fusionner_clients(c, 1, 4), [])
            c.commit()
            self.assertEqual(c.execute("SELECT telephone, telephone_2 FROM clients WHERE id = 1").fetchone(), ("+14505550142", None))
        finally:
            c.close()

    def test_refus(self):
        self.doublon()
        c = self.conn()
        try:
            self.assertIn("deux fiches différentes", noyau.fusionner_clients(c, 1, 1)[0])
            self.assertIn("n'existe pas", noyau.fusionner_clients(c, 1, 99)[0])
            self.assertIn("n'existe pas", noyau.fusionner_clients(c, 99, 1)[0])
            # une ancienne adresse (d'un côté ou de l'autre)
            nouveau, _ = noyau.nouvelle_adresse_client(c, 2, {"adresse": "1 Rue Neuve", "client_secteur": "shawinigan"})
            for garde, doublon in ((2, 1), (1, 2)):
                self.assertIn("ancienne adresse", noyau.fusionner_clients(c, garde, doublon)[0])
            # une autre fiche pointe vers le doublon : par remplace_par (la fiche 2 pointe vers `nouveau`), puis par fusionne_dans
            erreurs = noyau.fusionner_clients(c, 1, nouveau)
            self.assertIn(f"n° {2}", erreurs[0])
            self.assertIn("dans l'autre sens", erreurs[0])
            self.assertEqual(noyau.fusionner_clients(c, 1, 4), [])
            self.assertIn("déjà fusionnée", noyau.fusionner_clients(c, 3, 4)[0])
            self.assertIn("déjà fusionnée", noyau.fusionner_clients(c, 4, 3)[0])
            erreurs = noyau.fusionner_clients(c, 3, 1)                                                     # la fiche 1 a un doublon fusionné dedans
            self.assertIn("n° 4", erreurs[0])
            self.assertEqual(noyau.fusionner_clients(c, 1, 3), [])                                         # mais elle peut garder un deuxième doublon
            self.assertEqual(c.execute("SELECT id, fusionne_dans FROM clients ORDER BY id").fetchall(),
                             [(1, None), (2, None), (4, 1), (5, None)])           # la fiche 3 n'avait pas de chantier terminé : supprimée
        finally:
            c.close()

    def test_un_refus_ne_change_rien(self):
        self.doublon()
        avant = self.sql("SELECT id, client_id, statut FROM chantiers ORDER BY id")
        statut, _, page = self.fusionner(1, 1)
        self.assertTrue(statut.startswith("200"))
        self.assertIn("deux fiches différentes", page)
        self.assertEqual(self.sql("SELECT id, client_id, statut FROM chantiers ORDER BY id"), avant)
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE fusionne_dans IS NOT NULL"), [(0,)])
        statut, _, page = self.post("/client/1/fusionner", {})
        self.assertIn("Choisis d", page)

    def test_la_fiche_cachee_redirige_vers_la_fiche_gardee(self):
        self.doublon()
        self.fusionner()
        for chemin, attendu in (("/client/4", "/client/1"), ("/client/4/modifier", "/client/1/modifier"),
                                ("/client/4/nouvelle-adresse", "/client/1/nouvelle-adresse"), ("/client/4/fusionner", "/client/1/fusionner"),
                                ("/client/4/soumission/nouveau", "/client/1/soumission/nouveau")):
            statut, en_tetes, _ = interface.repondre(self.db, "GET", chemin, {})
            self.assertTrue(statut.startswith("303"), chemin)
            self.assertEqual(dict(en_tetes)["Location"], attendu, chemin)
        statut, en_tetes, _ = interface.repondre(self.db, "GET", "/client/4/modifier", {"retour": "/chantier/9"})
        self.assertEqual(dict(en_tetes)["Location"], "/client/1/modifier?retour=%2Fchantier%2F9")
        avant = self.sql("SELECT * FROM clients ORDER BY id")
        for chemin, form in (("/client/4/modifier", {"client_nom": "Pirate", "client_prenom": "X", "adresse": "1 Rue Z", "client_secteur": "shawinigan"}),
                             ("/client/4/nouvelle-adresse", {"adresse": "9 Rue Neuve", "client_secteur": "shawinigan"}),
                             ("/client/4/fusionner", {"avec": "3"}), ("/client/4/supprimer", {}),
                             ("/client/4/soumission/nouveau", {"duree_estimee_h": "2"}), ("/client/4/chantier/nouveau", {"duree_estimee_h": "2"})):
            statut, en_tetes, _ = self.post(chemin, form)
            self.assertTrue(statut.startswith("303"), chemin)
            self.assertTrue(en_tetes["Location"].startswith("/client/1"), (chemin, en_tetes["Location"]))
        self.assertEqual(self.sql("SELECT * FROM clients ORDER BY id"), avant)                              # aucune modification possible
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(9,)])
        self.assertTrue(self.get("/client/99")[0].startswith("404"))

    def test_la_fiche_cachee_est_absente_des_listes_et_des_choix(self):
        self.doublon()
        self.assertIn('href="/client/4"', self.get("/clients")[1])
        self.assertIn('href="/client/4"', self.get("/nouveau", {"q": "voisine"})[1])
        self.fusionner()
        page = self.get("/clients")[1]
        self.assertNotIn('href="/client/4"', page)
        self.assertNotIn("5 Rue Voisine", page)
        self.assertEqual(page.count("Marie Gagnon"), 1)
        self.assertNotIn("5 Rue Voisine", self.get("/clients", {"q": "voisine"})[1])
        self.assertNotIn("5 Rue Voisine", self.get("/clients", {"secteur": "centre_ville"})[1])
        nouveau = self.get("/nouveau", {"q": "gagnon"})[1]
        self.assertIn('href="/client/1"', nouveau)
        self.assertNotIn('href="/client/4"', nouveau)
        c = self.conn()
        try:
            idx = noyau.Index(c)
            self.assertNotIn(4, idx.infos)
            self.assertNotIn(4, [i for ids in idx.par_adresse.values() for i in ids])
            self.assertEqual(idx.par_telephone["+14505550199"], 1)                                          # son téléphone est maintenant (2e numéro) sur la fiche gardée
            v = {"client_prenom": "Marie", "client_nom": "Gagnon", "client_entreprise": "", "client_telephone": "+14505550199",
                 "client_telephone_2": "", "adresse": "5 Rue Voisine", "ville": "Saint-Jérôme"}
            self.assertEqual(idx.trouver(v), (None, None))                                                  # le doublon caché n'est jamais réutilisé
            self.assertEqual(idx.ailleurs(v), 1)
        finally:
            c.close()

    def test_fiche_cachee_non_supprimable_et_fiche_gardee_non_plus(self):
        self.doublon()
        c = self.conn()
        try:
            c.execute("INSERT INTO clients (nom) VALUES ('Roy')")
            c.execute("INSERT INTO clients (nom) VALUES ('Roy')")
            c.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, prix_ht) VALUES (6, 'termine', '2026-01-01', 1, 10)")                                                                                 # le doublon (6) a un chantier terminé : il sera caché
            c.commit()
            self.assertTrue(noyau.client_supprimable(c, 6) is False)
            self.assertTrue(noyau.client_supprimable(c, 5))                                                 # sans historique : supprimable
            self.assertEqual(noyau.fusionner_clients(c, 5, 6), [])                                          # 6 reste cachée (chantier terminé)
            c.commit()
            self.assertFalse(noyau.client_supprimable(c, 5))                                                # a un doublon fusionné dedans
            self.assertFalse(noyau.client_supprimable(c, 6))                                                # est cachée
            self.assertIn("fusionnée", noyau.supprimer_client(c, 6)[0])
            self.assertIn("fusionnée dans celle-ci", noyau.supprimer_client(c, 5)[0])
            self.assertEqual(c.execute("SELECT count(*) FROM clients").fetchone()[0], 6)
            self.assertEqual(noyau.fusionner_clients(c, 1, 4), [])
            c.commit()
            n, termines, paiements = noyau.resume_suppression_client(c, 1)
            self.assertEqual((n, termines, paiements), (7, 2, 2))                                           # compte les chantiers restés sur le doublon
            self.assertFalse(noyau.client_supprimable(c, 1))
            with self.assertRaises(sqlite3.IntegrityError):                                                 # la base refuse aussi (RESTRICT)
                c.execute("DELETE FROM clients WHERE id = 5")
        finally:
            c.close()
        page = self.get("/client/5")[1]
        self.assertNotIn("Supprimer le client", page)
        statut, en_tetes, _ = self.post("/client/5/supprimer", {})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 5"), [(1,)])

    def test_supprimer_le_dernier_chantier_ne_supprime_pas_une_fiche_gardee(self):
        c = self.conn()
        try:
            c.execute("INSERT INTO clients (nom) VALUES ('Roy')")
            c.execute("INSERT INTO clients (nom) VALUES ('Roy')")
            c.execute("INSERT INTO chantiers (client_id, statut) VALUES (4, 'soumission')")
            c.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, prix_ht) VALUES (5, 'termine', '2026-01-01', 1, 10)")
            c.commit()
            self.assertEqual(noyau.fusionner_clients(c, 4, 5), [])
            c.commit()
            self.assertEqual(noyau.supprimer_chantier(c, 4), [])
            c.commit()
            self.assertEqual(c.execute("SELECT count(*) FROM clients WHERE id = 4").fetchone()[0], 1)      # pas d'erreur, la fiche reste
        finally:
            c.close()

    def test_dupliquer_un_chantier_termine_du_doublon_va_a_la_fiche_gardee(self):
        self.doublon()
        self.fusionner()
        c = self.conn()
        try:
            nouveau, erreurs = noyau.dupliquer_chantier(c, 9)
            c.commit()
            self.assertEqual(erreurs, [])
            self.assertEqual(c.execute("SELECT client_id FROM chantiers WHERE id = ?", (nouveau,)).fetchone(), (1,))
        finally:
            c.close()

    def test_doublon_sans_chantier_termine_est_supprime(self):
        c = self.conn()
        try:
            c.execute("INSERT INTO clients (prenom, nom, telephone, adresse, ville) VALUES ('Paul', 'Roy', '+14505550123', '1 Rue A', 'Mirabel')")
            c.execute("INSERT INTO clients (prenom, nom, telephone, adresse, ville) VALUES ('Paul', 'Roy', '+14505550124', '2 Rue B', 'Mirabel')")
            c.execute("INSERT INTO chantiers (client_id, statut) VALUES (5, 'soumission')")
            c.execute("INSERT INTO chantiers (client_id, statut, accepte_le) VALUES (5, 'a_planifier', '2026-09-04')")
            c.commit()
        finally:
            c.close()
        statut, en_tetes, _ = self.fusionner(4, 5)
        self.assertEqual(en_tetes["Location"], "/client/4?ok=fusion")
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 5"), [(0,)])                    # plus aucune ligne
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE fusionne_dans IS NOT NULL"), [(0,)])
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id IN (4, 5) ORDER BY id"), [(4,), (4,)])   # ses soumissions sont sur la fiche gardée
        self.assertEqual(self.get("/client/5")[0][:3], "404")
        page = self.get("/client/4", {"ok": "fusion"})[1]
        self.assertIn("Les deux fiches sont fusionnées", page)
        self.assertEqual(page.count('href="/soumission/') + page.count('href="/chantier/'), 2)
        self.assertIn("Supprimer le client", page)                                                          # sans historique : reste supprimable
        c = self.conn()
        try:
            self.assertTrue(noyau.client_supprimable(c, 4))
            self.assertEqual(noyau.supprimer_client(c, 4), [])
            c.commit()
        finally:
            c.close()
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id IN (4, 5)"), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE client_id IN (4, 5)"), [(0,)])

    def test_les_secteurs_utilises_par_un_doublon_cache(self):
        self.doublon()
        self.fusionner()
        c = self.conn()
        try:
            c.execute("UPDATE clients SET secteur = 'shawinigan' WHERE id = 4")
            c.commit()
            self.assertIn("cachées", noyau.supprimer_secteur(c, "shawinigan")[0])
        finally:
            c.close()

    def test_les_declencheurs_ne_changent_pas(self):
        self.doublon()
        liste = lambda: self.sql("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name")
        avant = liste()
        self.assertEqual(len(avant), 9)
        self.fusionner()
        self.assertEqual(liste(), avant)
        c = self.conn()
        try:
            with self.assertRaises(sqlite3.DatabaseError):                                                 # le chantier terminé reste verrouillé
                c.execute("UPDATE chantiers SET client_id = 1 WHERE id = 9")
        finally:
            c.close()

    def test_bouton_sur_la_fiche(self):
        page = self.get("/client/1")[1]
        self.assertRegex(page, r'<a class="bouton secondaire" href="/client/1/fusionner">Fusionner avec un autre client</a>')
        self.assertLess(page.index("Soumissions et chantiers"), page.index("Fusionner avec un autre client"))      # tout en bas
        self.assertRegex(page, r'<div class="barre pc-seul"[^>]*><a class="bouton secondaire" href="/client/1/fusionner">')   # ordinateur seulement
        self.deplacer = TestNouvelleAdresse.deplacer.__get__(self)
        self.post("/client/1/nouvelle-adresse", {"adresse": "45 Rue du Lac", "client_secteur": "shawinigan"})
        self.assertNotIn("Fusionner avec un autre client", self.get("/client/1")[1])                         # ancienne adresse : pas de bouton
        statut, en_tetes, _ = interface.repondre(self.db, "GET", "/client/1/fusionner", {})
        self.assertTrue(statut.startswith("303"))
        self.assertIn("err=", dict(en_tetes)["Location"])

    def test_page_de_choix_propose_les_fiches_qui_se_ressemblent(self):
        self.doublon()
        c = self.conn()
        try:
            c.execute("INSERT INTO clients (prenom, nom, telephone, adresse, ville) VALUES ('Paul', 'Gagnon', '+14505550133', '9 Rue X', 'Mirabel')")
            c.execute("INSERT INTO clients (prenom, nom, telephone, adresse, ville) VALUES ('Zoe', 'Tremblay', '+14505550188', '8 Rue Y', 'Mirabel')")
            c.execute("INSERT INTO clients (nom) VALUES ('Sans rapport')")
            c.commit()
        finally:
            c.close()
        statut, page = self.get("/client/1/fusionner")
        self.assertTrue(statut.startswith("200"))
        self.assertIn("/client/1/fusionner?avec=4", page)                                                   # même nom de famille
        self.assertIn("/client/1/fusionner?avec=5", page)
        self.assertNotIn("avec=7", page)                                                                    # sans rapport
        self.assertNotIn("avec=2", page)
        self.assertNotIn('avec=1"', page)                                                                   # jamais elle-même
        self.assertIn('<input type="search" name="q"', page)
        statut, page = self.get("/client/1/fusionner", {"q": "tremblay"})
        self.assertIn("avec=6", page)
        self.assertNotIn("avec=4", page)
        self.assertIn("Aucune fiche trouvée", self.get("/client/1/fusionner", {"q": "zzzzz"})[1])
        self.fusionner(1, 4)
        self.assertNotIn("avec=4", self.get("/client/1/fusionner", {"q": "gagnon"})[1])                      # une fiche déjà fusionnée n'est plus proposée
        self.assertNotIn('avec=1"', self.get("/client/1/fusionner", {"q": "gagnon"})[1])

    def test_meme_telephone_propose(self):
        self.doublon()
        c = self.conn()
        try:
            c.execute("INSERT INTO clients (prenom, nom, telephone, adresse, ville) VALUES ('M.', 'Autrenom', '+14505550142', '9 Rue X', 'Mirabel')")
            c.commit()
        finally:
            c.close()
        self.assertIn("avec=5", self.get("/client/1/fusionner")[1])

    def test_page_de_confirmation(self):
        self.doublon()
        statut, page = self.get("/client/1/fusionner", {"avec": "4"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("Tout l'historique sera visible sur la fiche gardée. Les factures déjà faites ne changent pas.", page)
        self.assertLess(page.index("Fiche gardée"), page.index("Sera cachée"))
        gardee, cachee = page[page.index("Fiche gardée"):page.index("Sera cachée")], page[page.index("Sera cachée"):]
        self.assertIn("123 Rue des Érables", page.split("Sera cachée")[0])
        self.assertIn("5 Rue Voisine", cachee)
        self.assertIn("450-555-0199", cachee)
        self.assertIn("marie.autre@example.com", cachee)
        self.assertIn('<div class="grille">', page)                                                          # la grille existante : les fiches l'une sous l'autre sur téléphone
        self.assertIn('<button type="submit">Fusionner</button>', page)
        self.assertRegex(page, r'<a class="bouton secondaire annuler" href="/client/1">Annuler</a>')
        self.assertIn('<a href="/client/4/fusionner?avec=1">Garder plutôt l\'autre fiche</a>', page)
        self.assertIn('name="avec" value="4"', page)
        statut, inverse = self.get("/client/4/fusionner", {"avec": "1"})                                    # l'inverse : la fiche 4 est gardée
        self.assertLess(inverse.index("Fiche gardée"), inverse.index("5 Rue Voisine"))
        self.assertLess(inverse.index("5 Rue Voisine"), inverse.index("Sera cachée"))
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE fusionne_dans IS NOT NULL"), [(0,)])      # voir ne change rien
        statut, erreur = self.get("/client/1/fusionner", {"avec": "99"})
        self.assertIn("existe pas", erreur)
        self.assertNotIn('<button type="submit">Fusionner</button>', erreur)
        self.assertIn("deux fiches différentes", self.get("/client/1/fusionner", {"avec": "1"})[1])

    def test_fusion_dans_l_autre_sens(self):
        self.doublon()
        self.fusionner(4, 1)
        self.assertEqual(self.sql("SELECT id, fusionne_dans FROM clients ORDER BY id"), [(1, 4), (2, None), (3, None), (4, None)])
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id = 1"), [(1,)])                  # le terminé de la fiche 1 reste sur la fiche 1
        page = self.get("/client/4")[1]
        self.assertRegex(page, r'href="/chantier/1"')
        self.assertEqual(self.get("/client/1")[0][:3], "303")
