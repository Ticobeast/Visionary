"""Tests de l'interface de saisie (outils/interface.py).

    python3 -m unittest discover -s tests -v
"""
import datetime
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import fixtures  # noqa: E402
import interface  # noqa: E402



def fiche(**perso):
    base = dict(client_nom="Roy", client_prenom="Sylvie", client_telephone="450-555-0111", client_sms_ok="1",
                adresse="22 Rue des Pins", client_secteur="trois_rivieres_ouest", province="QC", type_emondage="1", statut="soumission", duree_estimee_h="2")
    base.update(perso)
    return base


class BaseInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def get(self, chemin):
        u = urllib.parse.urlsplit(chemin)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        statut, en_tetes, corps = interface.repondre(self.db, "GET", u.path, q)
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

    def creer_accepte(self, **perso):
        """Ouvre une fiche COMPLÈTE puis l'accepte : elle devient un chantier « À planifier ». Retourne son id."""
        self.post("/nouveau", fiche(prix_ht="300", **perso))
        i = self.sql("SELECT max(id) FROM chantiers")[0][0]
        self.post(f"/soumission/{i}/accepter", {"retour": "/soumissions"})
        assert self.sql("SELECT statut FROM chantiers WHERE id = ?", (i,)) == [("a_planifier",)], "la fiche aurait dû être acceptée"
        return i


class TestPages(BaseInterface):
    @staticmethod
    def partie_active(page):
        return page[:page.index('id="archives"')]

    @staticmethod
    def partie_archives(page):
        return page[page.index('id="archives"'):]

    def test_une_seule_page_chantiers_avec_les_archives_plus_bas(self):
        statut, page = self.get("/chantiers")
        self.assertTrue(statut.startswith("200"))
        actifs, archives = self.partie_active(page), self.partie_archives(page)
        for nom in ("Pierre Lavoie", "Luc Boucher"):
            self.assertIn(nom, actifs)
            self.assertNotIn(nom, archives)
        self.assertNotIn("Marie Gagnon", actifs)                 # terminé ET payé : archivé automatiquement
        self.assertIn("Marie Gagnon", archives)
        self.assertIn("Archives (1)", page)
        self.assertIn("À recevoir", page)                       # raccourci (pastille) par défaut de l'administrateur
        self.assertNotIn("à facturer", page)
        self.assertIn("1 437,19 $", actifs)                      # Lavoie : 1250 + taxes, non facturé
        self.assertNotIn('class="onglet', page)                        # plus d'onglets : une seule section principale
        entete = page[page.index("<header"):page.index("</header>")]
        self.assertIn('href="/archives"', entete)                # l'onglet Archives (historique complet, recherches, statistiques) est dans le menu
        self.assertIn('href="/archives">onglet Archives</a>', page)     # et la petite section d'archives de cette page y mène

    def test_un_chantier_termine_et_paye_rejoint_les_archives_tout_seul(self):
        self.assertIn("Pierre Lavoie", self.partie_active(self.get("/chantiers")[1]))
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 2"), [("a_payer",)])      # terminé = facturé d'office
        self.post("/chantier/2/paiement", {"paiement_date": "2026-10-03", "paiement_montant": "1437,19", "paiement_mode": "cheque"})
        page = self.get("/chantiers")[1]
        self.assertNotIn("Pierre Lavoie", self.partie_active(page))
        self.assertIn("Pierre Lavoie", self.partie_archives(page))
        self.assertIn("Archivé", self.get("/chantier/2")[1])
        # un chantier payé mais pas terminé n'est PAS archivé
        self.post("/chantier/3/paiement", {"paiement_date": "2026-10-03", "paiement_montant": "2029,45", "paiement_mode": "cheque"})
        self.assertIn("Luc Boucher", self.partie_active(self.get("/chantiers")[1]))

    def test_filtres_et_recherche_sans_accent(self):
        self.assertNotIn("Luc Boucher", self.partie_active(self.get("/chantiers?paiement=a_payer")[1]))
        self.assertIn("Pierre Lavoie", self.partie_active(self.get("/chantiers?paiement=a_payer")[1]))
        self.assertIn("Luc Boucher", self.partie_active(self.get("/chantiers?statut=planifie")[1]))
        self.assertNotIn("Pierre Lavoie", self.partie_active(self.get("/chantiers?statut=planifie")[1]))
        self.assertIn("Marie Gagnon", self.partie_archives(self.get("/chantiers?q=erables")[1]))    # « Érables » trouvé sans accent
        self.assertIn("Marie Gagnon", self.partie_archives(self.get("/chantiers?q=450-555-0142")[1]))
        self.assertNotIn("Pierre Lavoie", self.get("/chantiers?q=boucher")[1])                    # la recherche couvre actifs ET archives

    def test_les_archives_sont_limitees_mais_toujours_retrouvables(self):
        conn, _ = interface.ouvrir_base(self.db)
        modele = conn.execute("SELECT client_id FROM chantiers WHERE id = 1").fetchone()[0]
        for i in range(60):
            cur = conn.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, duree_reelle_h, prix_ht) VALUES (?, 'termine', ?, 2, 2, 0)",
                               (modele, f"2020-01-{i % 28 + 1:02d}"))
            conn.execute("INSERT INTO chantier_travaux VALUES (?, 'emondage', ?)", (cur.lastrowid, f"zzz{i}"))
        conn.close()
        archives = self.partie_archives(self.get("/chantiers")[1])
        self.assertEqual(archives.count('<a href="/chantier/'), interface.LIMITE_ARCHIVES)
        self.assertIn("utilise la recherche", archives)
        self.assertIn("zzz59", self.get("/chantiers?q=zzz59")[1])

    def test_pages_de_detail_et_introuvable(self):
        statut, page = self.get("/chantier/1")
        self.assertIn("123 Rue des Érables, Saint-Jérôme, QC J7Z 1A1", page)
        self.assertIn("google.com/maps/search", page)
        self.assertIn("551,88 $", page)
        self.assertTrue(self.get("/chantier/999")[0].startswith("404"))
        self.assertTrue(self.get("/nimporte")[0].startswith("404"))

    def test_recherche_de_client_existant(self):
        self.assertIn('href="/client/2"', self.get("/nouveau?q=lavoie")[1])           # on passe par la fiche du client
        self.assertIn("Aucun client trouvé", self.get("/nouveau?q=zzz")[1])
        statut, en_tetes, _ = interface.repondre(self.db, "GET", "/nouveau", {"client_id": "2"})
        self.assertEqual((statut[:3], dict(en_tetes)["Location"]), ("303", "/client/2"))

    def test_html_est_echappe(self):
        self.post("/nouveau", fiche(client_nom="<script>alert(1)</script>", description="<img src=x onerror=alert(2)>"))
        for chemin in ("/soumissions", "/soumission/4", "/soumission/4/completer", "/nouveau?q=script", "/clients", "/client/4", "/"):
            page = self.get(chemin)[1]
            self.assertNotIn("<script>alert", page, chemin)
            self.assertNotIn("<img src=x", page, chemin)
        self.assertIn("&lt;script&gt;", self.get("/soumissions")[1])
        self.assertIn("&lt;script&gt;", self.get("/clients")[1])


class TestSuppressionDeClient(BaseInterface):
    """Un client peut toujours être effacé, avec tout ce qui le concerne (archives comprises)."""

    def creer(self, **perso):
        """Ouvre une soumission et retourne son id (la redirection mène à la fiche du client)."""
        self.post("/nouveau", fiche(**perso))
        return self.sql("SELECT max(id) FROM chantiers")[0][0]

    def test_bouton_et_suppression_d_un_client_avec_son_chantier(self):
        chantier = self.creer()
        client = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (chantier,))[0][0]
        page = self.get(f"/client/{client}")[1]
        self.assertIn(f'action="/client/{client}/supprimer"', page)
        self.assertIn("1 soumission", page)
        self.assertIn("confirm(", page)                                          # confirmation avant d'effacer
        statut, en_tetes, _ = self.post(f"/client/{client}/supprimer", {})
        self.assertEqual(en_tetes["Location"], "/clients?ok=client_supprime")
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = ?", (client,)), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE id = ?", (chantier,)), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantier_travaux WHERE chantier_id = ?", (chantier,)), [(0,)])
        self.assertIn("Client supprimé", self.get("/clients?ok=client_supprime")[1])
        self.assertTrue(self.get(f"/client/{client}")[0].startswith("404"))

    def test_client_sans_chantier(self):
        client = self.creer()
        self.post(f"/soumission/{self.sql('SELECT max(id) FROM chantiers')[0][0]}/supprimer", {})        # supprime la soumission (et le client orphelin)
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = ?", (client,)), [(0,)])

    def test_un_client_peut_toujours_etre_supprime_avec_tout_son_historique(self):
        triggers = self.sql("SELECT name FROM sqlite_master WHERE type = 'trigger' ORDER BY name")
        for client in (1, 2, 3):                                                  # exemples : 1 et 2 terminés ; 3 planifié avec acompte
            page = self.get(f"/client/{client}")[1]
            self.assertIn(f'action="/client/{client}/supprimer"', page)
            self.assertIn("confirm(", page)
        client = self.sql("SELECT client_id FROM chantiers WHERE id = 1")[0][0]
        self.assertEqual(self.sql("SELECT count(*) FROM paiements p JOIN chantiers c ON c.id = p.chantier_id WHERE c.client_id = ?", (client,)), [(1,)])
        statut, en_tetes, _ = self.post(f"/client/{client}/supprimer", {})
        self.assertEqual(en_tetes["Location"], "/clients?ok=client_supprime")
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = ?", (client,)), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE client_id = ?", (client,)), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(1,)])      # seul l'acompte de l'autre client reste
        self.assertEqual(self.sql("SELECT count(*) FROM chantier_travaux WHERE chantier_id = 1"), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(2,)])
        self.assertEqual(self.sql("SELECT name FROM sqlite_master WHERE type = 'trigger' ORDER BY name"), triggers)   # protections rétablies
        self.assertNotIn("Marie Gagnon", self.get("/chantiers")[1])               # disparu des archives aussi

    def test_client_avec_un_chantier_termine_et_un_annule(self):
        self.post("/action/terminer", {"chantier_id": "3", "paye": "non", "retour": "/"})        # client 3 : terminé (avec acompte)
        self.post("/client/3/soumission/nouveau", {"type_emondage": "1", "duree_estimee_h": "2"})
        nouveau = self.sql("SELECT max(id) FROM chantiers")[0][0]
        self.post("/action/annuler", {"chantier_id": str(nouveau), "retour": "/"})
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE client_id = 3 ORDER BY id"), [("termine",), ("annule",)])
        self.post("/client/3/supprimer", {})
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 3"), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE client_id = 3"), [(0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 3"), [(0,)])

    def test_un_chantier_termine_seul_reste_non_supprimable(self):
        _, en_tetes, _ = self.post("/chantier/1/supprimer", {})
        self.assertNotIn("Location", en_tetes)                                    # page d'erreur, pas de redirection
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE id = 1"), [(1,)])

    def test_un_chantier_annule_sans_paiement_ne_retient_pas_le_client(self):
        chantier = self.creer()
        client = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (chantier,))[0][0]
        self.post("/action/annuler", {"chantier_id": str(chantier), "retour": "/"})
        self.post(f"/client/{client}/supprimer", {})
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = ?", (client,)), [(0,)])

    def test_les_autres_clients_ne_sont_pas_touches(self):
        avant = self.sql("SELECT count(*) FROM clients")[0][0]
        self.creer()
        client = self.sql("SELECT max(id) FROM clients")[0][0]
        self.post(f"/client/{client}/supprimer", {})
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(avant,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_client_inconnu(self):
        self.assertTrue(self.post("/client/999/supprimer", {})[0].startswith("404"))


class TestAucunEmoji(BaseInterface):
    """Aucun emoji (ni symbole pictural) dans l'interface."""

    MOTIF = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u25A0-\u25FF\u23E0-\u23FF\uFE0F\u2190-\u21FF]")

    def test_toutes_les_pages(self):
        jour = self.sql("SELECT date_prevue FROM chantiers WHERE id = 3")[0][0]
        self.post("/nouveau", {})                                                        # une soumission entièrement vide (#4)
        pages = [("/", {}), ("/", {"date": jour, "terminer": "3"}), ("/journee", {"date": jour}), ("/journee", {"date": jour, "terminer": "3"}),
                 ("/chantiers", {}), ("/soumissions", {}), ("/clients", {}), ("/nouveau", {}), ("/client/1", {}), ("/client/4", {}),
                 ("/client/1/modifier", {}), ("/client/1/soumission/nouveau", {}), ("/soumission/4", {}), ("/soumission/4/completer", {}),
                 ("/raccourcis", {"page": "chantiers"}), ("/raccourcis", {"page": "soumissions"}),
                 ("/chantier/1", {}), ("/chantier/2", {}), ("/chantier/3", {}), ("/chantier/3/dupliquer", {}), ("/utilisateurs", {})]
        for chemin, query in pages:
            page = interface.repondre(self.db, "GET", chemin, query)[2].decode("utf-8")
            trouves = [c for c in self.MOTIF.findall(page.split("</style>", 1)[-1]) if c not in ("\u25b2", "\u25bc")]   # sauf les flèches de l'ordre
            self.assertEqual(trouves, [], f"{chemin} {query}")


class TestCreation(BaseInterface):
    """On ouvre une SOUMISSION (jamais un chantier) : rien n'est obligatoire, et on revient à la fiche du client."""

    def test_creation_complete(self):
        statut, en_tetes, _ = self.post("/nouveau", fiche(
            statut="a_planifier", duree_estimee_h="2,5", nacelle="1", debarrasser_bois="1",
            prix_ht="300,00", taxes_auto="1", code_postal="j7j1a1", dossier_photos="photos/2026/2026-10-20_roy",
            paiement_date="2026-10-01", paiement_montant="100", paiement_mode="interac"))
        self.assertTrue(statut.startswith("303"))
        self.assertEqual(en_tetes["Location"], "/client/4?ok=soumission_creee")             # retour à la fiche du client
        self.assertEqual(self.sql("SELECT telephone, code_postal, geocode_statut, secteur, ville FROM clients WHERE nom = 'Roy'"),
                         [("+14505550111", "J7J 1A1", "a_faire", "trois_rivieres_ouest", "Trois-Rivières")])     # la ville vient du secteur
        self.assertEqual(self.sql("SELECT statut, date_prevue, ordre_jour, duree_estimee_h, prix_ht, tps, tvq, nacelle, debarrasser_bois, bois_format, accepte_le FROM chantiers WHERE id = 4"),
                         [("soumission", None, None, 2.5, 300.0, 15.0, 29.93, 1, 1, None, None)])     # le statut envoyé est ignoré
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(2,)])                           # jamais de paiement à l'ouverture d'une soumission
        self.assertEqual(self.sql("SELECT statut_paiement, genre FROM v_chantiers WHERE chantier_id = 4"), [("sans_objet", "soumission")])
        self.assertIn("Soumission créée", self.get("/client/4?ok=soumission_creee")[1])
        self.assertIn("Nacelle requise", self.get("/soumission/4")[1])
        self.assertNotIn("Roy", self.get("/chantiers")[1])                                              # aucune soumission dans Chantiers
        self.assertIn("Roy", self.get("/soumissions")[1])

    def test_rien_n_est_obligatoire(self):
        statut, en_tetes, _ = self.post("/nouveau", {})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/client/4?ok=soumission_creee"))
        self.assertEqual(self.sql("SELECT statut, duree_estimee_h, prix_ht FROM chantiers WHERE id = 4"), [("soumission", None, None)])
        self.assertEqual(self.sql("SELECT nom, adresse, ville, secteur FROM clients WHERE id = 4"), [(None, "", "", None)])
        for chemin in ("/client/4", "/soumission/4", "/soumissions", "/soumission/4/completer"):          # aucune page ne plante
            self.assertTrue(self.get(chemin + ("?retour=%2Fsoumissions" if "completer" in chemin else ""))[0].startswith("200"), chemin)
        page = self.get("/soumissions")[1]
        self.assertIn("(client à identifier)", page)
        self.assertIn("Il manque : nom, téléphone, adresse, secteur, travaux, durée, prix", page)

    def test_sans_aucun_champ_obligatoire_dans_le_formulaire(self):
        page = self.get("/nouveau")[1]
        formulaire = page[page.index('<form method="post" action="/nouveau">'):page.index("</form>", page.index('<form method="post" action="/nouveau">'))]
        self.assertNotRegex(formulaire, r'<(?:input|select|textarea)[^>]*\brequired\b')
        self.assertNotIn('class="requis"', formulaire)                                                   # pas d'étoile non plus
        self.assertIn("Créer la soumission", formulaire)
        self.assertNotIn("Statut au départ", page)                                                       # le statut ne se choisit pas
        self.assertNotIn('name="statut"', page)
        self.assertNotIn('name="paiement_montant"', page)

    def test_erreurs_gardent_les_valeurs_et_n_ecrivent_rien(self):
        statut, _, page = self.post("/nouveau", fiche(date_soumission="14/06/2026", client_telephone="123",
                                                      client_nom="Nom gardé"))
        self.assertTrue(statut.startswith("200"))
        self.assertIn("À corriger", page)
        self.assertIn("AAAA-MM-JJ", page)
        self.assertIn('value="Nom gardé"', page)
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_les_champs_de_paiement_envoyes_sont_ignores(self):
        statut, en_tetes, _ = self.post("/nouveau", fiche(paiement_date="2026-06-14", paiement_montant="50", paiement_mode="interac"))
        self.assertEqual(statut[:3], "303")
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(2,)])

    def test_meme_adresse_reutilise_le_client(self):
        self.post("/nouveau", fiche())                                                       # #4 : Sylvie Roy, 22 Rue des Pins, Trois-Rivières-Ouest
        clients = self.sql("SELECT count(*) FROM clients")
        _, en_tetes, _ = self.post("/nouveau", fiche(client_nom="Roy", client_prenom="Sylvie", adresse="22 rue des pins",
                                                     type_emondage="", type_elagage="1", debarrasser_bois="1"))
        self.assertEqual(en_tetes["Location"], "/client/4?ok=soumission_reutilisee")
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), clients)
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id = 5"), self.sql("SELECT client_id FROM chantiers WHERE id = 4"))

    def test_deux_soumissions_vides_ne_partagent_pas_le_meme_client(self):
        self.post("/nouveau", {})
        self.post("/nouveau", {})
        self.assertEqual(self.sql("SELECT count(DISTINCT client_id) FROM chantiers WHERE id > 3"), [(2,)])

    def test_le_secteur_est_facultatif_mais_choisi_dans_la_liste(self):
        for secteur in ("n_importe_quoi", "Trois Rivieres"):                                 # un secteur écrit doit exister
            _, _, page = self.post("/nouveau", fiche(client_secteur=secteur))
            self.assertIn("client_secteur", page, secteur)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        self.post("/nouveau", fiche(client_secteur=""))                                      # vide : permis dans une soumission
        self.assertEqual(self.sql("SELECT secteur FROM clients ORDER BY id DESC LIMIT 1"), [(None,)])
        for saisi, attendu in (("cap_de_la_madeleine", "Cap-de-la-Madeleine"), ("Cap de la Madeleine", "Cap-de-la-Madeleine"),
                               ("TROIS-RIVIERES-OUEST", "Trois-Rivières-Ouest")):          # code ou libellé, sans accent ni casse
            self.post("/nouveau", fiche(client_secteur=saisi, adresse=f"{saisi[:3]} 1 Rue Test"))
            self.assertEqual(self.sql("SELECT s.libelle FROM clients c JOIN secteurs s ON s.code = c.secteur ORDER BY c.id DESC LIMIT 1"), [(attendu,)])
        self.assertEqual(self.sql("SELECT DISTINCT ville FROM clients WHERE secteur IS NOT NULL"), [("Trois-Rivières",)])    # une seule écriture possible

    def test_la_liste_deroulante_remplace_le_champ_ville(self):
        page = self.get("/nouveau")[1]
        self.assertNotIn('name="ville"', page)
        liste = page[page.index('name="client_secteur"'):]
        liste = liste[:liste.index("</select>")]
        for libelle in ("Centre-ville", "Trois-Rivières-Ouest", "Cap-de-la-Madeleine"):
            self.assertIn(libelle, liste)
        self.assertIn("<optgroup", liste)


class TestModification(BaseInterface):
    """Chantier 3 (Boucher) : planifié, donc modifiable. Les chantiers 1 et 2 sont terminés : verrouillés."""

    def formulaire_de(self, chantier_id):
        """Valeurs du formulaire d'édition, telles que le navigateur les renverrait."""
        conn, _ = interface.ouvrir_base(self.db)
        try:
            valeurs, _ = interface.valeurs_chantier(conn, chantier_id)
        finally:
            conn.close()
        valeurs.pop("client_id", None)
        return valeurs

    def tout(self):
        return self.sql("SELECT * FROM clients ORDER BY id") + self.sql("SELECT * FROM chantiers ORDER BY id")

    def test_edition_sans_changement_ne_change_rien(self):
        avant = self.tout()
        statut, en_tetes, _ = self.post("/chantier/3", self.formulaire_de(3))
        self.assertEqual(en_tetes["Location"], "/chantier/3?ok=maj")
        self.assertEqual(self.tout(), avant)

    def test_la_case_taxes_reflete_la_fiche_et_la_decocher_remet_les_taxes_a_zero(self):
        self.assertIn('name="taxes_auto" value="1" checked', self.get("/chantier/3")[1])             # la fiche a des taxes : case cochée
        f = self.formulaire_de(3)
        self.assertEqual(f["taxes_auto"], "1")
        f.pop("taxes_auto")                                                                          # décochée, TPS/TVQ non retouchées
        self.assertEqual(self.post("/chantier/3", f)[1]["Location"], "/chantier/3?ok=maj")
        self.assertEqual(self.sql("SELECT tps, tvq FROM chantiers WHERE id = 3"), [(0.0, 0.0)])
        self.assertNotIn('name="taxes_auto" value="1" checked', self.get("/chantier/3")[1])
        g = self.formulaire_de(3)                                                                    # on la recoche : les taxes sont recalculées
        g["taxes_auto"] = "1"
        self.post("/chantier/3", g)
        tps, tvq = self.sql("SELECT tps, tvq FROM chantiers WHERE id = 3")[0]
        self.assertTrue(tps > 0 and tvq > 0)

    def test_taxes_retouchees_a_la_main_sont_gardees_meme_case_decochee(self):
        f = self.formulaire_de(3)
        f.pop("taxes_auto")
        f["tps"] = "12.00"
        self.post("/chantier/3", f)
        self.assertEqual(self.sql("SELECT tps FROM chantiers WHERE id = 3"), [(12.0,)])

    def test_le_client_est_en_lecture_seule_sur_la_page_du_chantier(self):
        page = self.get("/chantier/3")[1]
        formulaire = page[page.index('<form method="post" action="/chantier/3">'):page.index("</form>", page.index('<form method="post" action="/chantier/3">'))]
        for interdit in ("client_nom", "client_prenom", "client_telephone", "client_courriel", "adresse", "ville", "client_secteur", "code_postal", "client_sms_ok"):
            self.assertNotIn(f'name="{interdit}"', formulaire)
        self.assertIn("Lecture seule", page)
        self.assertIn("850 Boulevard du Lac", page)                                   # mais le client est bien affiché
        self.assertIn('href="/client/3/modifier?retour=%2Fchantier%2F3"', page)       # seul point d'entrée : la fiche client (puis retour ici)

    def test_le_serveur_ignore_toute_modification_du_client_envoyee_au_chantier(self):
        avant = self.sql("SELECT * FROM clients ORDER BY id")
        self.post("/chantier/3", {**self.formulaire_de(3), "client_nom": "PIRATE", "client_prenom": "X", "adresse": "1 Rue Fausse",
                                  "ville": "Ailleurs", "client_telephone": "514-555-0199", "code_postal": "H0H 0H0",
                                  "client_sms_ok": "0", "client_secteur": "centre_ville", "latitude": "45.5", "longitude": "-73.5", "client_id": "1"})
        self.assertEqual(self.sql("SELECT * FROM clients ORDER BY id"), avant)
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id = 3"), [(3,)])

    def test_le_recap_apres_enregistrement_montre_le_client_verrouille(self):
        self.post("/nouveau", fiche())
        page = self.get("/soumission/4")[1]
        self.assertIn("Lecture seule", page)
        self.assertNotIn('name="client_nom"', page)
        self.assertIn("Sylvie Roy", page)
        self.assertIn("22 Rue des Pins", page)

    def test_le_client_se_modifie_depuis_sa_fiche_seulement(self):
        self.post("/client/3/modifier", {"client_nom": "Boucher", "client_prenom": "Luc", "client_entreprise": "Syndicat Les Jardins du Lac",
                                         "client_telephone": "+14505550163", "adresse": "99 Chemin Neuf", "client_secteur": "centre_ville",
                                         "province": "QC", "code_postal": "G8Z 1A1"})
        self.assertIn("99 Chemin Neuf", self.get("/chantier/3")[1])
        self.assertEqual(self.sql("SELECT latitude, longitude, geocode_statut FROM clients WHERE id = 3"), [(None, None, "a_faire")])

    def test_le_formulaire_ne_peut_jamais_changer_le_statut(self):
        i = self.creer_accepte()                                                   # chantier #4 « À planifier », sans date
        for statut in ("planifie", "termine", "annule", "soumission", "en_attente", "bidon"):
            self.post(f"/chantier/{i}", {**self.formulaire_de(i), "statut": statut, "date_prevue": "2026-10-14"})
            self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (i,)), [("a_planifier", None)], statut)
        self.post("/nouveau", fiche())                                             # une soumission : pareil
        j = self.sql("SELECT max(id) FROM chantiers")[0][0]
        for statut in ("planifie", "a_planifier", "termine", "annule"):
            self.post(f"/soumission/{j}", {**self.formulaire_de(j), "statut": statut, "date_prevue": "2026-10-14"})
            self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (j,)), [("soumission", None)], statut)

    def test_un_chantier_planifie_garde_son_statut_et_sa_date_quoi_que_le_formulaire_envoie(self):
        f = self.formulaire_de(3)
        self.post("/chantier/3", {**f, "statut": "a_planifier", "date_prevue": "2026-12-25"})
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = 3"), [("planifie", "2026-10-14")])

    def test_duree_reelle_reprend_la_duree_estimee_a_la_cloture(self):
        self.creer_accepte(duree_estimee_h="3,5")
        self.post("/journee/planifier", {"date": "2026-10-14", "sel_4": "1", "retour": "/journee"})
        self.post("/action/terminer", {"chantier_id": "4", "retour": "/"})
        self.assertEqual(self.sql("SELECT statut, duree_estimee_h, duree_reelle_h FROM chantiers WHERE id = 4"), [("termine", 3.5, 3.5)])

    def test_duree_reelle_cachee_a_la_creation(self):
        self.assertNotIn('name="duree_reelle_h"', self.get("/nouveau")[1])
        self.assertIn('name="duree_estimee_h"', self.get("/nouveau")[1])
        self.assertIn(f'name="date_soumission" type="date" value="{datetime.date.today().isoformat()}"', self.get("/nouveau")[1])

    def test_duree_estimee_obligatoire_pour_un_chantier_pas_pour_une_soumission(self):
        for duree in ("0", "25"):                                                  # une durée écrite doit être valable
            _, _, page = self.post("/nouveau", fiche(duree_estimee_h=duree))
            self.assertIn("duree_estimee_h", page, duree)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        self.assertTrue(self.post("/nouveau", fiche(duree_estimee_h=""))[0].startswith("303"))      # soumission : facultative
        _, _, page = self.post("/chantier/3", {**self.formulaire_de(3), "duree_estimee_h": ""})     # chantier : obligatoire
        self.assertIn("duree_estimee_h", page)
        self.assertEqual(self.sql("SELECT duree_estimee_h FROM chantiers WHERE id = 3"), [(6.0,)])

    def test_la_date_des_travaux_se_change_dans_la_journee(self):
        page = self.get("/chantier/3")[1]
        self.assertNotIn('name="date_prevue"', page)                           # pas de champ date sur le chantier
        self.assertNotIn("se change dans la page Journée", page)               # la date est déjà dans le résumé du haut
        self.post("/journee/planifier", {"date": "2026-10-16", "sel_3": "1", "retour": "/journee"})      # le chantier est déplacé
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = 3"), [("planifie", "2026-10-16")])
        self.post("/action/terminer", {"chantier_id": "3", "retour": "/"})                               # puis il est fait ce jour-là
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = 3"), [("termine", "2026-10-16")])

    def test_plusieurs_types_avec_precision_et_une_seule_description(self):
        self.post("/chantier/3", {**self.formulaire_de(3), "type_elagage": "1", "precision_elagage": "érable côté garage",
                                  "precision_taille_haie": "cèdres, 35 m", "precision_abattage": "frêne mort"})   # précision seule : type coché d'office
        types = dict(self.sql("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 3"))
        self.assertEqual(types["elagage"], "érable côté garage")
        self.assertEqual(types["taille_haie"], "cèdres, 35 m")
        self.assertEqual(types["abattage"], "frêne mort")
        detail = self.get("/chantier/3")[1]
        self.assertIn("Élagage : érable côté garage", detail)
        self.assertIn('name="precision_elagage" value="érable côté garage"', detail)
        self.assertIn('name="type_elagage" value="1" checked', detail)
        self.assertEqual(detail.count('name="description"'), 1)           # une seule description
        self.assertNotIn('name="notes"', detail)                          # plus de notes de chantier

    def test_au_moins_un_type_de_travaux_pour_un_chantier(self):
        self.assertTrue(self.post("/nouveau", fiche(type_emondage=""))[0].startswith("303"))         # soumission : facultatif
        formulaire = {c: v for c, v in self.formulaire_de(3).items() if not c.startswith(("type_", "precision_"))}
        _, _, page = self.post("/chantier/3", formulaire)                                            # chantier : au moins un type
        self.assertIn("au moins un type de travaux", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantier_travaux WHERE chantier_id = 3"), [(1,)])

    def test_la_base_ouverte_est_toujours_affichee(self):
        self.assertIn("BASE D’ESSAI : t.db", self.get("/")[1])       # t.db n'est pas la vraie base

    def test_modalite_unique_parmi_cinq(self):
        page = self.get("/nouveau")[1]
        options = re.findall(r'<option value="([a-z]*)"', page[page.index('name="modalite_paiement"'):])[:6]
        self.assertEqual(options, ["", "comptant", "cheque", "interac", "carte", "autre"])
        _, _, page = self.post("/nouveau", fiche(modalite_paiement="3 versements"))
        self.assertIn("modalite_paiement", page)
        _, en_tetes, _ = self.post("/nouveau", fiche(modalite_paiement="carte"))
        self.assertIn("ok=soumission_creee", en_tetes["Location"])


class TestSimpleParDefaut(BaseInterface):
    """Simple par défaut : l'essentiel en clair, le reste dans « Paramètres avancés » (repliés, mais envoyés avec le formulaire)."""

    @staticmethod
    def noms(html):
        return set(re.findall(r'<(?:input|select|textarea)(?![^>]*type="hidden")[^>]*\bname="([^"]+)"', html))

    def separer(self, page, debut):
        """(partie visible, partie « Paramètres avancés ») du premier formulaire commençant par `debut`."""
        formulaire = page[page.index(debut):]
        formulaire = formulaire[:formulaire.index("</form>")]
        visible, _, reste = formulaire.partition('<details class="avance"')
        return visible, reste

    def test_nouvelle_soumission_client_et_travaux(self):
        page = self.get("/nouveau")[1]
        visible, cache = self.separer(page, '<form method="post" action="/nouveau">')
        champs = {c for c in self.noms(visible) if not c.startswith(("type_", "precision_"))}
        # essentiel : le client (avec son secteur dans une liste), les travaux et leurs options (nacelle, bois), durée, prix, description
        self.assertEqual(champs, {"client_nom", "client_prenom", "client_telephone", "adresse", "client_secteur", "nacelle", "debarrasser_bois",
                                  "bois_format", "duree_estimee_h", "prix_ht", "taxes_auto", "description"})
        self.assertIn("Paramètres avancés", page)
        self.assertNotIn("date_prevue", self.noms(cache))                      # la date des travaux vient de la Journée
        for avance in ("client_entreprise", "client_courriel", "code_postal", "notes_acces", "latitude", "date_soumission",
                       "tps", "tvq", "modalite_paiement", "dossier_photos"):
            self.assertIn(avance, self.noms(cache), avance)
            self.assertNotIn(avance, self.noms(visible), avance)
        for jamais in ("statut", "paiement_montant", "paiement_date", "date_prevue"):                  # ni statut ni paiement à l'ouverture
            self.assertNotIn(jamais, self.noms(visible) | self.noms(cache), jamais)
        self.assertNotIn(" open", page[page.index('<details class="avance"'):][:30])     # replié par défaut

    def test_creation_avec_l_essentiel_seulement(self):
        _, en_tetes, _ = self.post("/nouveau", {"client_nom": "Simon", "client_telephone": "450-555-0188", "adresse": "5 Rue Courte", "client_secteur": "pointe_du_lac",
                                                "type_elagage": "1", "debarrasser_bois": "1", "duree_estimee_h": "2", "prix_ht": "300"})
        self.assertIn("ok=soumission_creee", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut, duree_estimee_h, prix_ht, date_soumission FROM chantiers WHERE id = 4"),
                         [("soumission", 2.0, 300.0, datetime.date.today().isoformat())])

    def test_les_parametres_avances_sont_pris_en_compte(self):
        self.post("/nouveau", fiche(modalite_paiement="carte", client_courriel="s@example.com", code_postal="j7j1a1"))
        self.assertEqual(self.sql("SELECT modalite_paiement FROM chantiers WHERE id = 4"), [("carte",)])
        self.assertEqual(self.sql("SELECT courriel, code_postal FROM clients WHERE nom = 'Roy'"), [("s@example.com", "J7J 1A1")])

    def test_une_erreur_dans_les_avances_les_ouvre(self):
        _, _, page = self.post("/nouveau", fiche(date_soumission="14/06/2026"))
        self.assertIn('<details class="avance" open>', page)
        self.assertIn("AAAA-MM-JJ", page)

    def test_page_d_un_chantier(self):
        page = self.get("/chantier/3")[1]
        visible, cache = self.separer(page, '<form method="post" action="/chantier/3">')
        champs = {c for c in self.noms(visible) if not c.startswith(("type_", "precision_"))}
        # planifié : le statut et la date sont affichés (gérés par la Journée), pas des champs
        self.assertEqual(champs, {"nacelle", "debarrasser_bois", "bois_format", "duree_estimee_h", "prix_ht", "taxes_auto", "description"})
        for avance in ("date_soumission", "duree_reelle_h", "tps", "tvq", "modalite_paiement", "dossier_photos"):
            self.assertIn(avance, self.noms(cache), avance)
        self.assertIn("Autres soumissions et chantiers de ce client", cache)
        self.assertIn("Supprimer ce chantier", cache)
        self.assertNotIn("Supprimer ce chantier", visible)

    def test_le_bouton_supprimer_n_est_jamais_le_bouton_par_defaut_du_formulaire(self):
        """La touche Entrée soumet le premier bouton du formulaire : ce doit être « Enregistrer », jamais « Supprimer »."""
        page = self.get("/chantier/3")[1]
        formulaire = page[page.index('<form method="post" action="/chantier/3">'):]
        formulaire = formulaire[:formulaire.index("</form>")]
        boutons = re.findall(r'<button([^>]*)>([^<]*)</button>', formulaire)
        self.assertEqual(boutons[0][1], "Enregistrer les modifications")
        suppression = [attrs for attrs, texte in boutons if texte == "Supprimer ce chantier"]
        self.assertEqual(len(suppression), 1)
        self.assertIn('form="supprimer-chantier"', suppression[0])                 # rattaché à son propre formulaire
        self.assertIn('<form id="supprimer-chantier" method="post" action="/chantier/3/supprimer"></form>', page)

    def test_chantier_termine_details_dans_les_parametres_avances(self):
        page = self.get("/chantier/2")[1]
        visible, _, cache = page.partition('<details class="avance"')
        self.assertIn("verrouillé en lecture seule", visible)
        self.assertIn("Ajouter un paiement", visible)
        self.assertNotIn("Fiche papier", page)                                     # plus de fiche papier nulle part
        self.assertNotIn("Scan de la fiche", page)
        self.assertNotIn("Mode de règlement", visible)
        self.assertIn("Mode de règlement", cache)                                       # le détail complet est replié
        self.assertIn("Autres soumissions et chantiers de ce client", cache)
        self.assertIn('class="montant">1 437,19 $', visible)                       # mais le montant est bien en vue

    def test_formulaire_client_simplifie_et_fiche_client(self):
        page = self.get("/client/3/soumission/nouveau")[1]
        visible, cache = self.separer(page, '<form method="post" action="/client/3/soumission/nouveau">')
        self.assertEqual({c for c in self.noms(visible) if not c.startswith(("type_", "precision_"))},
                         {"nacelle", "debarrasser_bois", "bois_format", "duree_estimee_h", "prix_ht", "taxes_auto", "description"})
        self.assertEqual(self.noms(cache), {"date_soumission", "modalite_paiement"})
        page = self.get("/client/3/modifier")[1]
        visible, cache = self.separer(page, '<form method="post" action="/client/3/modifier">')
        self.assertEqual(self.noms(visible), {"client_nom", "client_prenom", "client_telephone", "adresse", "client_secteur"})
        self.assertIn("client_courriel", self.noms(cache))


class TestTermineVerrouille(BaseInterface):
    """Un chantier Terminé est définitivement en lecture seule (interface ET base de données)."""

    def test_page_en_lecture_seule(self):
        page = self.get("/chantier/2")[1]
        self.assertIn("verrouillé en lecture seule", page)
        self.assertNotIn('<form method="post" action="/chantier/2">', page)
        self.assertNotIn("Supprimer ce chantier", page)
        self.assertNotIn('name="statut"', page)
        self.assertIn(">Dupliquer<", page)
        self.assertNotIn("acturer", page)                                  # plus de système de facture
        self.assertIn("Ajouter un paiement", page)                         # l'encaissement reste possible

    def test_toute_modification_par_le_serveur_est_refusee(self):
        avant = self.sql("SELECT * FROM chantiers WHERE id = 2")
        conn, _ = interface.ouvrir_base(self.db)
        valeurs, _ = interface.valeurs_chantier(conn, 2)
        conn.close()
        valeurs.update(prix_ht="1.00", description="piraté", statut="planifie", date_prevue="2026-11-01", client_sms_ok="1")
        _, _, page = self.post("/chantier/2", valeurs)
        self.assertIn("verrouillé", page)
        self.assertEqual(self.sql("SELECT * FROM chantiers WHERE id = 2"), avant)
        self.assertEqual(self.post("/chantier/2/supprimer", {})[0][:3], "200")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE id = 2"), [(1,)])

    def test_actions_rapides_ne_rouvrent_pas_un_termine(self):
        for action in ("retirer", "annuler", "rouvrir", "terminer"):
            _, en_tetes, _ = self.post(f"/action/{action}", {"chantier_id": "2", "retour": "/"})
            self.assertIn("err=", en_tetes["Location"], action)
        _, en_tetes, _ = self.post("/journee/planifier", {"date": "2026-11-01", "sel_2": "1", "retour": "/journee"})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = 2"), [("termine",)])

    def test_la_base_elle_meme_refuse(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        for requete in ("UPDATE chantiers SET statut = 'planifie' WHERE id = 2", "UPDATE chantiers SET prix_ht = 1 WHERE id = 2",
                        "UPDATE chantiers SET description = 'x' WHERE id = 2", "UPDATE chantiers SET duree_reelle_h = 9 WHERE id = 2",
                        "DELETE FROM chantiers WHERE id = 2", "DELETE FROM chantier_travaux WHERE chantier_id = 2",
                        "UPDATE chantier_travaux SET precision = 'x' WHERE chantier_id = 2"):
            with self.assertRaises(sqlite3.IntegrityError, msg=requete):
                c.execute(requete)
        c.close()


class TestPaiementsEtSuppression(BaseInterface):
    def test_ajouter_et_supprimer_un_paiement(self):
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 2"), [("a_payer",)])
        statut, en_tetes, _ = self.post("/chantier/2/paiement", {"paiement_date": "2026-10-02", "paiement_montant": "1 437,19",
                                                                  "paiement_mode": "cheque", "paiement_reference": "#0418"})
        self.assertEqual(en_tetes["Location"], "/chantier/2?ok=paiement")
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = 2"), [("paye", 0.0)])
        pid = self.sql("SELECT max(id) FROM paiements")[0][0]
        self.post(f"/paiement/{pid}/supprimer", {})
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 2"), [("a_payer",)])

    def test_paiement_invalide(self):
        for form in ({"paiement_date": "2026-10-02", "paiement_montant": "", "paiement_mode": "interac"},
                     {"paiement_date": "14/10/2026", "paiement_montant": "50", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "0", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "-5", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "12,345", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "50", "paiement_mode": "bitcoin"}):
            statut, _, page = self.post("/chantier/2/paiement", form)
            self.assertTrue(statut.startswith("200"), form)
            self.assertIn("erreurs", page)
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(2,)])

    def test_jamais_de_solde_negatif(self):
        # Lavoie doit 1 437,19 $ : un paiement de 1 437,20 $ est refusé, 1 437,19 $ est accepté
        statut, _, page = self.post("/chantier/2/paiement", {"paiement_date": "2026-10-02", "paiement_montant": "1437,20", "paiement_mode": "cheque"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("erreurs", page)
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 2"), [(0,)])
        self.post("/chantier/2/paiement", {"paiement_date": "2026-10-02", "paiement_montant": "1437,19", "paiement_mode": "cheque"})
        self.assertEqual(self.sql("SELECT solde FROM v_chantiers WHERE chantier_id = 2"), [(0.0,)])
        _, _, page = self.post("/chantier/2/paiement", {"paiement_date": "2026-10-03", "paiement_montant": "0,01", "paiement_mode": "cheque"})
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 2"), [(1,)])
        self.assertEqual(self.sql("SELECT min(solde) FROM v_chantiers"), [(0.0,)])

    def test_terminer_et_payer_encaisse_exactement_le_solde(self):
        # chantier 3 : planifié, solde 2 029,45 $ ; le montant n'est jamais saisi, quoi que le navigateur envoie
        self.post("/action/terminer", {"chantier_id": "3", "paye": "oui", "mode": "interac", "montant": "9999", "retour": "/"})
        self.assertEqual(self.sql("SELECT sum(montant) FROM paiements WHERE chantier_id = 3"), [(2529.45,)])
        self.assertEqual(self.sql("SELECT statut, solde, archive FROM v_chantiers WHERE chantier_id = 3"), [("termine", 0.0, 1)])

    def test_la_base_refuse_un_solde_negatif(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (3, '2026-10-02', 2100, 'interac')")
        with self.assertRaises(sqlite3.IntegrityError):                       # augmenter un paiement existant
            c.execute("UPDATE paiements SET montant = 9999 WHERE chantier_id = 3")
        with self.assertRaises(sqlite3.IntegrityError):                       # baisser le prix sous ce qui est déjà payé
            c.execute("UPDATE chantiers SET prix_ht = 100, tps = 0, tvq = 0 WHERE id = 3")
        c.close()

    def test_supprimer_un_chantier_et_son_client_orphelin(self):
        _, _, page = self.post("/chantier/3/supprimer", {})                 # a un paiement : refusé
        self.assertIn("a des paiements", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        self.post("/nouveau", fiche())                                      # #4 : une soumission, aucun paiement
        statut, en_tetes, _ = self.post("/soumission/4/supprimer", {})
        self.assertEqual(en_tetes["Location"], "/soumissions?ok=soumission_supprimee")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE nom = 'Roy'"), [(0,)])
        i = self.creer_accepte()                                            # un chantier accepté : retour à la liste des chantiers
        statut, en_tetes, _ = self.post(f"/chantier/{i}/supprimer", {})
        self.assertEqual(en_tetes["Location"], "/chantiers?ok=supprime")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_client_avec_autre_chantier_n_est_pas_supprime(self):
        self.post("/client/3/chantier/nouveau", {"type_emondage": "1", "duree_estimee_h": "2"})      # #4 sur le client de Boucher
        self.post("/chantier/4/supprimer", {})
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 3"), [(1,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])


class TestDuplication(BaseInterface):
    def test_dupliquer_un_chantier_termine(self):
        page = self.get("/chantier/1/dupliquer")[1]
        self.assertIn('name="prix_ht" type="text" value="480.00"', page)
        self.assertIn('name="duree_estimee_h"', page)
        statut, en_tetes, _ = self.post("/chantier/1/dupliquer", {"prix_ht": "520,00", "avec_taxes": "1", "duree_estimee_h": "3,5", "description": "Taille annuelle"})
        self.assertEqual(en_tetes["Location"], "/soumission/4?ok=duplique")               # une nouvelle SOUMISSION
        aujourdhui = datetime.date.today().isoformat()
        self.assertEqual(self.sql("SELECT client_id, statut, date_soumission, date_prevue, ordre_jour, duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq,"
                                  " modalite_paiement, description FROM chantiers WHERE id = 4"),
                         [(1, "soumission", aujourdhui, None, None, 3.5, None, 520.0, 26.0, 51.87, "interac", "Taille annuelle")])
        self.assertEqual(self.sql("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 4"), [("taille_haie", "cèdres côté rue et côté voisin, environ 35 m, hauteur 2 m")])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 4"), [(0,)])
        self.assertEqual(self.sql("SELECT statut, prix_ht FROM chantiers WHERE id = 1"), [("termine", 480.0)])      # l'original n'a pas bougé
        self.assertIn(">Dupliquer<", self.get("/soumission/4")[1])
        self.assertEqual(self.sql("SELECT cree_par, accepte_le FROM chantiers WHERE id = 4"), [(None, None)])

    def test_la_duree_et_le_prix_ecrits_doivent_etre_valables(self):
        for form in ({"prix_ht": "520", "duree_estimee_h": "0"}, {"prix_ht": "520", "duree_estimee_h": "25"}, {"prix_ht": "abc", "duree_estimee_h": "2"}, {"prix_ht": "-5", "duree_estimee_h": "2"}):
            statut, _, page = self.post("/chantier/1/dupliquer", form)
            self.assertTrue(statut.startswith("200"), form)
            self.assertIn("erreurs", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_duree_vide_reprend_celle_du_chantier_d_origine(self):
        self.post("/chantier/1/dupliquer", {"prix_ht": "", "duree_estimee_h": ""})
        self.assertEqual(self.sql("SELECT duree_estimee_h, prix_ht FROM chantiers WHERE id = 4"), [(3.0, 480.0)])

    def test_dupliquer_chantier_inconnu(self):
        self.assertTrue(self.get("/chantier/99/dupliquer")[0].startswith("404"))
        self.assertTrue(self.post("/chantier/99/dupliquer", {"duree_estimee_h": "2"})[0].startswith("404"))


class TestServeurReel(BaseInterface):
    def setUp(self):
        super().setUp()
        self.serveur = interface.creer_serveur(self.db, 0)       # port libre choisi par le système
        self.port = self.serveur.server_address[1]
        self.serveur.RequestHandlerClass.hotes_autorises = (f"127.0.0.1:{self.port}", f"localhost:{self.port}")
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        super().tearDown()

    def requete(self, chemin, donnees=None, en_tetes=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{chemin}", method="POST" if donnees is not None else "GET",
                                     data=urllib.parse.urlencode(donnees).encode() if donnees is not None else None,
                                     headers=en_tetes or {})

        class PasDeRedirection(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        try:
            r = urllib.request.build_opener(PasDeRedirection).open(req)
            return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def test_get_et_post_legitimes(self):
        statut, _, page = self.requete("/chantiers")
        self.assertEqual(statut, 200)
        self.assertIn("Luc Boucher", page)
        statut, entetes, _ = self.requete("/nouveau", fiche(), {"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(statut, 303)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(4,)])

    def test_post_venant_d_un_autre_site_est_refuse(self):
        statut, _, _ = self.requete("/nouveau", fiche(), {"Origin": "https://site-malveillant.example"})
        self.assertEqual(statut, 403)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_hote_inattendu_est_refuse(self):                     # protection « DNS rebinding »
        statut, _, _ = self.requete("/", en_tetes={"Host": "pirate.example"})
        self.assertEqual(statut, 403)


if __name__ == "__main__":
    unittest.main()
