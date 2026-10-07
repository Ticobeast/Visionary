"""Tests des pages : onglet Soumissions, acceptation / refus / complétion, fiche client sans renseignements, raccourcis, droits des comptes.

    python3 -m unittest discover -s tests -v
"""
import datetime
import html
import re
import sqlite3
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import auth  # noqa: E402
import fixtures  # noqa: E402
import interface  # noqa: E402
import noyau  # noqa: E402
import raccourcis  # noqa: E402
import vue  # noqa: E402

AUJOURDHUI = datetime.date.today()
BUREAU = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
COMPLETE = dict(client_nom="Roy", client_prenom="Sylvie", client_telephone="450-555-0111", client_sms_ok="1", adresse="22 Rue des Pins",
                client_secteur="trois_rivieres_ouest", province="QC", type_emondage="1", statut="soumission", duree_estimee_h="2", prix_ht="300")
PUCE = re.compile(r'<a class="puce( actif)?" href="([^"]*)"><b>(\d+)</b><span>([^<]*)</span></a>')


class BasePages(unittest.TestCase):
    """Base d'essai (3 dossiers) ; sans `cookie`, aucun contrôle d'accès (comme l'ordinateur du bureau sans comptes)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)

    def req(self, methode, chemin, form=None, cookie=None, agent=BUREAU):
        u = urllib.parse.urlsplit(chemin)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        requete = None if cookie is None else {"cookie": cookie, "ip": "100.64.1.2", "agent": agent, "https": False}
        statut, en_tetes, corps = interface.repondre(self.db, methode, u.path, query, form or {}, requete)
        return statut, dict(en_tetes), corps.decode("utf-8", "replace")

    def get(self, chemin, cookie=None, agent=BUREAU):
        return self.req("GET", chemin, cookie=cookie, agent=agent)[2]

    def texte(self, chemin, cookie=None):
        """La page telle que la lit l'utilisateur (apostrophes et accents décodés)."""
        return html.unescape(self.get(chemin, cookie=cookie))

    def post(self, chemin, form=None, cookie=None):
        return self.req("POST", chemin, form, cookie=cookie)

    def sql(self, requete, args=()):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(requete, args).fetchall()
        finally:
            c.close()

    def dernier_id(self):
        return self.sql("SELECT max(id) FROM chantiers")[0][0]

    def etat(self, i):
        return self.sql("SELECT statut, accepte_le FROM chantiers WHERE id = ?", (i,))[0]

    # --- fabriques de soumissions (par le formulaire, comme dans le navigateur)
    def ouvrir(self, cookie=None, **perso):
        base = {"statut": "soumission", "province": "QC"}
        base.update(perso)
        statut, en_tetes, _ = self.post("/nouveau", base, cookie=cookie)
        self.assertTrue(statut.startswith("303"), statut)
        return self.dernier_id()

    def vide(self, **kw):
        return self.ouvrir(**kw)

    def partielle(self, **kw):
        return self.ouvrir(client_nom="Tremblay", client_prenom="Jean", client_telephone="450-555-0123", type_emondage="1", **kw)

    def complete(self, cookie=None, **perso):
        return self.ouvrir(cookie=cookie, **{**COMPLETE, **perso})

    def puces(self, page):
        return [(html.unescape(nom), int(n), bool(actif), html.unescape(href)) for actif, href, n, nom in PUCE.findall(page)]


class TestListeEtCreation(BasePages):
    def test_une_soumission_se_cree_sans_rien_remplir(self):
        statut, en_tetes, _ = self.post("/nouveau", {"statut": "soumission", "province": "QC"})
        self.assertEqual(statut[:3], "303")
        i = self.dernier_id()
        self.assertEqual(en_tetes["Location"], f"/client/{self.sql('SELECT client_id FROM chantiers WHERE id = ?', (i,))[0][0]}?ok=soumission_creee")
        self.assertEqual(self.etat(i), ("soumission", None))

    def test_le_formulaire_n_exige_rien(self):
        page = self.get("/nouveau")
        self.assertNotIn('class="requis"', page)
        self.assertNotIn(" required", page)
        self.assertIn("Créer la soumission", page)
        self.assertIn("Rien n'est obligatoire", page)

    def test_la_liste_ne_montre_que_des_soumissions(self):
        self.complete()
        soumissions = self.get("/soumissions")
        self.assertIn("Roy", soumissions)
        for chantier in ("Boucher", "Lavoie", "Gagnon"):
            self.assertNotIn(chantier, soumissions)
        chantiers = self.get("/chantiers")
        self.assertNotIn("Roy", chantiers)
        self.assertIn("Boucher", chantiers)

    def test_une_soumission_vide_est_listee_avec_ce_qui_manque(self):
        self.vide()
        page = self.get("/soumissions")
        self.assertIn("(client à identifier)", page)
        self.assertIn("Il manque : nom, téléphone, adresse, secteur, travaux, durée, prix", page)
        self.assertIn("prix à saisir", page)
        self.assertIn(">Accepter<", page)
        self.assertIn(">Refuser<", page)

    def test_une_soumission_complete_n_affiche_aucun_manque(self):
        self.complete()
        self.assertNotIn("Il manque", self.get("/soumissions"))

    def test_l_onglet_soumissions_est_a_droite_de_chantiers(self):
        page = self.get("/soumissions")
        entete = page[page.index("<header"):page.index("</header>")]
        self.assertLess(entete.index('href="/chantiers"'), entete.index('href="/soumissions"'))
        self.assertLess(entete.index('href="/soumissions"'), entete.index('href="/clients"'))
        self.assertIn('.nav-bureau a[href="/soumissions"]{', page)                       # l'onglet de la page courante est surligné
        self.assertNotIn('.nav-bureau a[href="/chantiers"]{', page)
        self.assertIn('.nav-bureau a[href="/chantiers"]{', self.get("/chantiers"))

    def test_recherche_et_delai(self):
        ancienne = (AUJOURDHUI - datetime.timedelta(days=12)).isoformat()
        self.complete(client_nom="Ancienne", adresse="1 Rue Vieille", date_soumission=ancienne)
        self.complete(client_nom="Fraiche", adresse="2 Rue Neuve")
        page = self.get("/soumissions?q=ancienne")
        self.assertIn("Ancienne", page)
        self.assertNotIn("Fraiche", page)
        relance = self.get("/soumissions?attente=relance")
        self.assertIn("Ancienne", relance)
        self.assertNotIn("Fraiche", relance)
        self.assertIn("12 j", self.get("/soumissions"))
        self.assertIn("Aucune soumission en cours ne correspond", self.get("/soumissions?q=zzzz"))

    def test_la_plus_recente_est_en_haut(self):
        self.complete(client_nom="Vieille", adresse="2 Rue B", date_soumission=(AUJOURDHUI - datetime.timedelta(days=20)).isoformat())
        self.complete(client_nom="Recente", adresse="1 Rue A", date_soumission=AUJOURDHUI.isoformat())
        page = self.get("/soumissions")
        self.assertLess(page.index("Recente"), page.index("Vieille"))                    # les anciennes se retrouvent avec « À relancer »
        relance = self.get("/soumissions?attente=relance")
        self.assertIn("Vieille", relance)
        self.assertNotIn("Recente", relance)

    def test_les_deux_adresses_d_une_fiche_menent_a_la_bonne_page(self):
        i = self.complete()
        statut, en_tetes, _ = self.req("GET", f"/chantier/{i}")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}"))
        statut, en_tetes, _ = self.req("GET", "/soumission/3")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/chantier/3"))
        self.assertTrue(self.req("GET", f"/soumission/{i}")[0].startswith("200"))
        self.assertTrue(self.req("GET", "/chantier/3")[0].startswith("200"))
        self.assertTrue(self.req("GET", "/soumission/999")[0].startswith("404"))
        self.assertTrue(self.req("GET", "/chantier/999")[0].startswith("404"))

    def test_une_soumission_vide_se_modifie_sans_rien_exiger(self):
        i = self.vide()
        statut, en_tetes, _ = self.post(f"/soumission/{i}", {"description": "Appeler demain", "statut": "soumission"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}?ok=maj"))
        self.assertIn("Appeler demain", self.get(f"/soumission/{i}"))

    def test_la_page_d_une_soumission_montre_ce_qui_manque_et_les_boutons_rapides(self):
        i = self.partielle()
        page = self.texte(f"/soumission/{i}")
        self.assertIn("Pour accepter, il manque encore : l'adresse des travaux, le secteur (ville), la durée estimée, le prix.", page)
        for bouton in (">Accepter<", ">Refuser<", ">Dupliquer<", "Enregistrer les modifications"):
            self.assertIn(bouton, page)
        self.assertNotIn("Annuler le chantier", page)
        self.assertNotIn(">Terminer<", page)

    def test_les_soumissions_ne_sont_ni_dans_la_journee_ni_dans_le_tableau_de_bord(self):
        avant = (self.get("/"), self.get("/journee"))
        self.complete(client_nom="Fantome")
        self.vide()
        apres = (self.get("/"), self.get("/journee"))
        self.assertEqual(avant, apres)
        self.assertNotIn("Fantome", apres[1])

    def test_supprimer_une_soumission_vide_supprime_aussi_son_client_vide(self):
        i = self.vide()
        clients = self.sql("SELECT count(*) FROM clients")[0][0]
        statut, en_tetes, _ = self.post(f"/soumission/{i}/supprimer")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/soumissions?ok=soumission_supprimee"))
        self.assertEqual(self.sql("SELECT count(*) FROM clients")[0][0], clients - 1)
        self.assertIn("Soumission supprimée.", self.get(en_tetes["Location"]))

    def test_dupliquer_un_chantier_cree_une_soumission(self):
        statut, en_tetes, _ = self.post("/chantier/3/dupliquer", {"prix_ht": "400", "duree_estimee_h": "3"})
        nouveau = self.dernier_id()
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{nouveau}?ok=duplique"))
        self.assertEqual(self.etat(nouveau), ("soumission", None))
        self.assertEqual(self.etat(3)[0], "planifie")                                  # l'original n'a pas bougé
        self.assertIn("Boucher", self.get("/soumissions"))

    def test_les_messages_de_succes_existent_tous(self):
        i = self.complete()
        for cible, texte in ((f"/soumission/{i}?ok=maj", "Modifications enregistrées."), ("/soumissions?ok=soumission_acceptee", "Soumission acceptée"),
                             ("/soumissions?ok=soumission_refusee", "Soumission refusée"), ("/soumissions?ok=soumission_rouverte", "Soumission rouverte"),
                             ("/soumissions?ok=soumission_supprimee", "Soumission supprimée"), ("/client/1?ok=soumission_creee", "Soumission créée."),
                             ("/soumission/4?ok=remise_soumission", "Chantier remis en soumission"), ("/soumission/4?ok=duplique", "Nouvelle soumission créée")):
            self.assertIn(texte, self.get(cible), cible)


class TestAccepterRefuser(BasePages):
    def test_accepter_une_soumission_complete(self):
        i = self.complete()
        statut, en_tetes, _ = self.post(f"/soumission/{i}/accepter", {"retour": "/soumissions"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/soumissions?ok=soumission_acceptee"))
        self.assertEqual(self.etat(i), ("a_planifier", AUJOURDHUI.isoformat()))
        self.assertNotIn("Roy", self.get("/soumissions"))
        chantiers = self.get("/chantiers")
        self.assertIn("Roy", chantiers)
        self.assertIn("Remettre en soumission", self.get(f"/chantier/{i}"))
        self.assertIn("Soumission acceptée : elle est maintenant dans Chantiers", self.get(en_tetes["Location"]))

    def test_accepter_une_soumission_incomplete_demande_de_completer(self):
        i = self.partielle()
        statut, en_tetes, _ = self.post(f"/soumission/{i}/accepter", {"retour": "/soumissions"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}/completer?retour=%2Fsoumissions"))
        self.assertEqual(self.etat(i), ("soumission", None))                              # rien n'a changé tant que ce n'est pas complété

    def test_depuis_la_fiche_accepter_mene_au_chantier_et_refuser_reste_sur_la_fiche(self):
        i = self.complete()
        page = self.get(f"/soumission/{i}")
        self.assertIn(f'action="/soumission/{i}/accepter"><input type="hidden" name="retour" value="/chantier/{i}">', page)
        self.assertIn(f'action="/soumission/{i}/refuser" onsubmit', page)
        self.assertIn(f'<input type="hidden" name="retour" value="/soumission/{i}"><button type="submit" class="secondaire">Refuser', page)
        statut, en_tetes, _ = self.post(f"/soumission/{i}/accepter", {"retour": f"/chantier/{i}"})
        self.assertEqual(en_tetes["Location"], f"/chantier/{i}?ok=soumission_acceptee")
        self.assertIn("Soumission acceptée", self.get(en_tetes["Location"]))              # la page du chantier affiche le message
        j = self.complete(adresse="2 Rue B")
        statut, en_tetes, _ = self.post(f"/soumission/{j}/refuser", {"retour": f"/soumission/{j}"})
        self.assertEqual(en_tetes["Location"], f"/soumission/{j}?ok=soumission_refusee")
        page = self.get(en_tetes["Location"])
        self.assertIn("Soumission refusée", page)
        self.assertIn("Rouvrir la soumission", page)

    def test_accepter_une_soumission_incomplete_depuis_la_fiche_revient_au_chantier(self):
        i = self.partielle()
        statut, en_tetes, _ = self.post(f"/soumission/{i}/accepter", {"retour": f"/chantier/{i}"})
        self.assertEqual(en_tetes["Location"], f"/soumission/{i}/completer?retour=%2Fchantier%2F{i}")
        form = {"retour": f"/chantier/{i}", "adresse": "9 Rue des Lilas", "client_secteur": "centre_ville", "duree_estimee_h": "2", "prix_ht": "100"}
        statut, en_tetes, _ = self.post(f"/soumission/{i}/completer", form)
        self.assertEqual(en_tetes["Location"], f"/chantier/{i}?ok=soumission_acceptee")
        self.assertTrue(self.req("GET", en_tetes["Location"])[0].startswith("200"))

    def test_accepter_deux_fois_ou_accepter_un_chantier(self):
        i = self.complete()
        self.post(f"/soumission/{i}/accepter", {})
        statut, en_tetes, _ = self.post(f"/soumission/{i}/accepter", {"retour": "/soumissions"})
        self.assertIn("err=", en_tetes["Location"])
        statut, en_tetes, _ = self.post("/soumission/3/accepter", {})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.etat(3)[0], "planifie")
        self.assertTrue(self.post("/soumission/999/accepter", {})[0].startswith("404"))

    def test_refuser_puis_rouvrir(self):
        i = self.complete()
        statut, en_tetes, _ = self.post(f"/soumission/{i}/refuser", {"retour": "/soumissions"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/soumissions?ok=soumission_refusee"))
        self.assertEqual(self.etat(i), ("annule", None))
        page = self.get("/soumissions")
        self.assertIn("Refusées", page)
        self.assertLess(page.index('id="refusees"'), page.index("Roy"))                    # elle est dans la section du bas
        self.assertNotIn("Roy", self.get("/chantiers"))                                    # ni dans les chantiers, ni dans leurs archives
        fiche = self.get(f"/soumission/{i}")
        self.assertIn("Rouvrir la soumission", fiche)
        self.assertNotIn("Enregistrer les modifications", fiche)                          # refusée : en lecture seule
        statut, en_tetes, _ = self.post(f"/soumission/{i}/rouvrir", {"retour": f"/soumission/{i}"})
        self.assertEqual(en_tetes["Location"], f"/soumission/{i}?ok=soumission_rouverte")
        self.assertEqual(self.etat(i), ("soumission", None))
        self.assertIn("Roy", self.get("/soumissions"))

    def test_une_soumission_refusee_ne_se_modifie_pas(self):
        i = self.complete()
        self.post(f"/soumission/{i}/refuser", {})
        statut, _, page = self.post(f"/soumission/{i}", {"description": "Je triche", "statut": "soumission"})
        self.assertIn("rouvre-la d'abord", html.unescape(page))
        self.assertEqual(self.sql("SELECT description FROM chantiers WHERE id = ?", (i,)), [(None,)])

    def test_on_ne_refuse_pas_un_chantier_et_on_ne_rouvre_pas_une_soumission_en_cours(self):
        statut, en_tetes, _ = self.post("/soumission/3/refuser", {})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.etat(3)[0], "planifie")
        i = self.complete()
        statut, en_tetes, _ = self.post(f"/soumission/{i}/rouvrir", {})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.etat(i)[0], "soumission")

    def test_le_retour_ne_peut_pas_etre_une_adresse_externe(self):
        i = self.complete()
        statut, en_tetes, _ = self.post(f"/soumission/{i}/refuser", {"retour": "https://pirate.example/"})
        self.assertEqual(en_tetes["Location"], "/soumissions?ok=soumission_refusee")
        j = self.vide()
        statut, en_tetes, _ = self.post(f"/soumission/{j}/accepter", {"retour": "//pirate.example"})
        self.assertTrue(en_tetes["Location"].startswith(f"/soumission/{j}/completer?retour=%2Fsoumissions"))

    def test_les_actions_de_la_journee_ne_contournent_pas_accepter(self):
        i = self.complete()
        for chemin in ("/action/retirer", "/action/terminer"):
            statut, en_tetes, _ = self.post(chemin, {"chantier_id": str(i), "retour": "/soumissions"})
            self.assertIn("err=", en_tetes["Location"], chemin)
            self.assertEqual(self.etat(i), ("soumission", None), chemin)

    def test_remettre_un_chantier_a_planifier_en_soumission(self):
        i = self.complete()
        self.post(f"/soumission/{i}/accepter", {})
        statut, en_tetes, _ = self.post(f"/chantier/{i}/remettre-soumission")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}?ok=remise_soumission"))
        self.assertEqual(self.etat(i), ("soumission", None))
        self.assertIn("Roy", self.get("/soumissions"))
        self.assertNotIn("Roy", self.get("/chantiers"))
        # un chantier planifié ou terminé ne revient pas en soumission
        for chantier in (3, 2):
            statut, _, page = self.post(f"/chantier/{chantier}/remettre-soumission")
            self.assertIn("soumission", page.lower())
            self.assertNotEqual(self.etat(chantier)[0], "soumission")

    def test_un_chantier_accepte_garde_sa_date_d_acceptation_meme_annule(self):
        i = self.complete()
        self.post(f"/soumission/{i}/accepter", {})
        self.post("/action/annuler", {"chantier_id": str(i), "retour": "/chantiers"})
        self.assertEqual(self.etat(i), ("annule", AUJOURDHUI.isoformat()))
        self.assertIn("Annulé", self.get("/chantiers"))                                    # un chantier annulé reste un chantier (archives)
        self.assertNotIn("Roy", self.get("/soumissions"))                                  # et il ne redevient pas une « soumission refusée »


class TestCompleter(BasePages):
    def test_la_page_ne_demande_que_ce_qui_manque(self):
        i = self.partielle()
        page = self.texte(f"/soumission/{i}/completer")
        for present in ('name="adresse"', 'name="client_secteur"', 'name="duree_estimee_h"', 'name="prix_ht"', "Enregistrer et accepter"):
            self.assertIn(present, page, present)
        for absent in ('name="client_nom"', 'name="client_telephone"', 'name="type_emondage"', 'name="nacelle"'):
            self.assertNotIn(absent, page, absent)
        for ligne in ("l'adresse des travaux", "le secteur (ville)", "la durée estimée", "le prix"):
            self.assertIn(f"<li>{ligne}</li>", page)

    def test_une_soumission_vide_demande_tout(self):
        i = self.vide()
        page = self.texte(f"/soumission/{i}/completer")
        for champ in ("client_nom", "client_prenom", "client_entreprise", "client_telephone", "adresse", "client_secteur", "duree_estimee_h", "prix_ht",
                      "type_emondage", "type_abattage"):
            self.assertIn(f'name="{champ}"', page, champ)
        self.assertIn("Un nom, ou le nom d'une entreprise, suffit.", page)

    def test_le_bois_n_est_demande_que_pour_abattage_ou_elagage(self):
        i = self.complete(type_emondage="", type_abattage="1")
        self.assertEqual(self.sql("SELECT count(*) FROM chantier_travaux WHERE chantier_id = ? AND type_travaux = 'abattage'", (i,)), [(1,)])
        page = self.texte(f"/soumission/{i}/completer")
        self.assertIn('name="bois_format"', page)
        self.assertIn("<li>ce qu'on fait du bois", page)
        self.assertNotIn('name="adresse"', page)

    def test_completer_enregistre_puis_accepte(self):
        i = self.partielle()
        form = {"retour": "/soumissions", "adresse": "9 Rue des Lilas", "client_secteur": "centre_ville", "duree_estimee_h": "2,5", "prix_ht": "480"}
        statut, en_tetes, _ = self.post(f"/soumission/{i}/completer", form)
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/soumissions?ok=soumission_acceptee"))
        self.assertEqual(self.etat(i), ("a_planifier", AUJOURDHUI.isoformat()))
        adresse, ville, secteur = self.sql("SELECT adresse, ville, secteur FROM clients WHERE id = (SELECT client_id FROM chantiers WHERE id = ?)", (i,))[0]
        self.assertEqual((adresse, secteur), ("9 Rue des Lilas", "centre_ville"))
        self.assertTrue(ville)                                                              # la ville vient du secteur choisi
        self.assertEqual(self.sql("SELECT duree_estimee_h, prix_ht FROM chantiers WHERE id = ?", (i,)), [(2.5, 480.0)])
        self.assertIn("Tremblay", self.get("/chantiers"))

    def test_completer_une_soumission_vide_en_une_fois(self):
        i = self.vide()
        form = {"retour": "/soumissions", "client_nom": "Dubé", "client_telephone": "819-555-0144", "adresse": "88 Boul. des Forges",
                "client_secteur": "centre_ville", "duree_estimee_h": "3", "prix_ht": "850", "type_abattage": "1", "debarrasser_bois": "1"}
        statut, en_tetes, _ = self.post(f"/soumission/{i}/completer", form)
        self.assertEqual(en_tetes["Location"], "/soumissions?ok=soumission_acceptee")
        self.assertEqual(self.etat(i)[0], "a_planifier")
        self.assertEqual(self.sql("SELECT count(*) FROM chantier_travaux WHERE chantier_id = ?", (i,)), [(1,)])
        self.assertEqual(self.sql("SELECT debarrasser_bois FROM chantiers WHERE id = ?", (i,)), [(1,)])

    def test_un_complement_partiel_est_garde_et_le_reste_redemande(self):
        i = self.partielle()
        statut, _, page = self.post(f"/soumission/{i}/completer", {"retour": "/soumissions", "adresse": "9 Rue des Lilas"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("Ce qui a été saisi est enregistré, mais il manque encore : le secteur (ville), la durée estimée, le prix", html.unescape(page))
        self.assertNotIn('name="adresse"', page)                                          # l'adresse est maintenant connue
        self.assertEqual(self.etat(i)[0], "soumission")
        self.assertEqual(self.sql("SELECT adresse FROM clients WHERE id = (SELECT client_id FROM chantiers WHERE id = ?)", (i,)), [("9 Rue des Lilas",)])

    def test_une_valeur_invalide_n_accepte_rien(self):
        i = self.partielle()
        form = {"retour": "/soumissions", "adresse": "9 Rue des Lilas", "client_secteur": "centre_ville", "duree_estimee_h": "abc", "prix_ht": "480"}
        statut, _, page = self.post(f"/soumission/{i}/completer", form)
        self.assertTrue(statut.startswith("200"))
        self.assertIn('class="erreurs"', page)
        self.assertEqual(self.etat(i)[0], "soumission")
        self.assertEqual(self.sql("SELECT adresse FROM clients WHERE id = (SELECT client_id FROM chantiers WHERE id = ?)", (i,)), [("",)])   # rien d'enregistré

    def test_ce_qui_est_deja_connu_ne_peut_pas_etre_ecrase(self):
        i = self.partielle()
        form = {"retour": "/soumissions", "client_nom": "Pirate", "client_telephone": "000-000-0000", "adresse": "9 Rue des Lilas",
                "client_secteur": "centre_ville", "duree_estimee_h": "2", "prix_ht": "100"}
        self.post(f"/soumission/{i}/completer", form)
        self.assertEqual(self.sql("SELECT nom, telephone FROM clients WHERE id = (SELECT client_id FROM chantiers WHERE id = ?)", (i,)),
                         [("Tremblay", "+14505550123")])

    def test_rien_a_completer_ou_deja_accepte_renvoie_a_la_fiche(self):
        i = self.complete()
        statut, en_tetes, _ = self.req("GET", f"/soumission/{i}/completer")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}"))
        statut, en_tetes, _ = self.req("GET", "/soumission/3/completer")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/chantier/3"))
        statut, en_tetes, _ = self.post("/soumission/3/completer", {"adresse": "x"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/chantier/3"))
        self.assertTrue(self.req("GET", "/soumission/999/completer")[0].startswith("404"))
        self.assertTrue(self.post("/soumission/999/completer", {})[0].startswith("404"))

    def test_une_soumission_refusee_se_rouvre_avant_d_etre_completee(self):
        i = self.partielle()
        self.post(f"/soumission/{i}/refuser", {})
        statut, en_tetes, _ = self.req("GET", f"/soumission/{i}/completer")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}"))
        statut, en_tetes, _ = self.post(f"/soumission/{i}/completer", {"adresse": "9 Rue des Lilas"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}"))
        self.assertEqual(self.etat(i)[0], "annule")
        self.assertIn("Rouvrir la soumission", self.get(f"/soumission/{i}"))


def jour_dans(n):
    return (AUJOURDHUI + datetime.timedelta(days=n)).isoformat()


class TestEnAttentePages(BasePages):
    """Le troisième bouton « En attente » et tout ce qui l'entoure : page de la date, Chantiers, fiche, retour automatique."""

    def en_attente(self, i=None, reprise=None, **perso):
        """Met en attente (par la page, comme le navigateur) une soumission complète ; retourne son id."""
        i = i or self.complete(**perso)
        form = {"retour": "/soumissions", "choix": "date" if reprise else "indefini", "reprise_le": reprise or ""}
        statut, en_tetes, _ = self.post(f"/soumission/{i}/attente", form)
        self.assertEqual(statut[:3], "303", (statut, en_tetes))
        return i

    def test_la_liste_offre_trois_boutons_dans_l_ordre(self):
        i = self.complete()
        page = self.get("/soumissions")
        accepter = page.index(f'action="/soumission/{i}/accepter"')
        attente = page.index(f'href="/soumission/{i}/attente?retour=%2Fsoumissions">En attente</a>')
        refuser = page.index(f'action="/soumission/{i}/refuser"')
        self.assertLess(accepter, attente)
        self.assertLess(attente, refuser)

    def test_la_page_de_la_date(self):
        i = self.complete()
        page = self.texte(f"/soumission/{i}/attente?retour=%2Fsoumissions")
        self.assertIn("<h1>Mettre en attente</h1>", page)
        for texte in ('type="radio" name="choix" value="date" id="choix-date" checked', 'type="radio" name="choix" value="indefini"', 'type="date" name="reprise_le"',
                      'name="retour" value="/soumissions"', "Jusqu'au", "Jusqu'à nouvel ordre", "Dans 1 mois", "Dans 6 mois"):
            self.assertIn(texte, page, texte)
        self.assertIn("pas de taille de haie en avril", page)                               # l'exemple du client qui accepte pour plus tard
        prochain = noyau.decaler_mois(AUJOURDHUI, 2).isoformat()
        self.assertIn(f"&amp;reprise_le={prochain}", self.get(f"/soumission/{i}/attente?retour=%2Fsoumissions"))   # raccourci « Dans 2 mois »
        self.assertIn(f'name="reprise_le" value="{prochain}"', self.get(f"/soumission/{i}/attente?reprise_le={prochain}"))   # …et il préremplit la date

    def test_mise_en_attente_avec_une_date(self):
        i = self.complete(client_nom="Hamel", adresse="5 Rue de la Haie")
        form = {"retour": "/soumissions", "choix": "date", "reprise_le": jour_dans(60)}
        statut, en_tetes, _ = self.post(f"/soumission/{i}/attente", form)
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/soumissions?ok=mis_en_attente"))
        self.assertEqual(self.sql("SELECT statut, accepte_le, reprise_le FROM chantiers WHERE id = ?", (i,)), [("en_attente", AUJOURDHUI.isoformat(), jour_dans(60))])
        self.assertIn("Mis en attente", self.get(en_tetes["Location"]))
        self.assertNotIn("Hamel", self.get("/soumissions").split('id="refusees"')[0].split("<tbody>", 1)[-1])      # elle a quitté la liste des soumissions
        chantiers = self.get("/chantiers")
        ligne = chantiers[chantiers.rindex("<tr>", 0, chantiers.index("Hamel")):chantiers.index("</tr>", chantiers.index("Hamel"))]
        self.assertIn("En attente", ligne)
        self.assertIn(f"reprise le {jour_dans(60)}", ligne)

    def test_jusqu_a_nouvel_ordre(self):
        i = self.en_attente()
        self.assertEqual(self.sql("SELECT statut, reprise_le FROM chantiers WHERE id = ?", (i,)), [("en_attente", None)])
        self.assertIn("jusqu'à nouvel ordre", html.unescape(self.get("/chantiers")))
        fiche = self.texte(f"/chantier/{i}")
        self.assertIn("En attente : jusqu'à nouvel ordre", fiche)
        self.assertIn("Il reste en attente jusqu'à ce que tu l'en sortes", fiche)

    def test_les_chantiers_en_attente_sont_faciles_a_retrouver(self):
        self.en_attente(reprise=jour_dans(30), client_nom="Hamel")
        chantiers = self.get("/chantiers")
        self.assertIn('href="/chantiers?statut=en_attente">En attente (1)</a>', chantiers)       # lien dans le titre
        self.assertIn('<option value="en_attente">En attente</option>', chantiers)               # et dans les filtres
        filtre = self.get("/chantiers?statut=en_attente")
        self.assertIn("Hamel", filtre.split('id="archives"')[0])
        self.assertNotIn("Boucher", filtre.split('id="archives"')[0])
        self.assertIn('href="/chantiers?statut=en_attente">En attente (1)</a>', self.get("/soumissions"))    # aussi depuis Soumissions
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE statut = 'en_attente'"), [(1,)])

    def test_un_chantier_en_attente_n_est_pas_propose_dans_la_journee(self):
        i = self.en_attente(reprise=jour_dans(30), client_nom="Hamel")
        lot = self.get(f"/journee?date={jour_dans(1)}")
        self.assertNotIn("Hamel", lot)
        self.post(f"/chantier/{i}/reprendre", {})
        self.assertIn("Hamel", self.get(f"/journee?date={jour_dans(1)}"))                     # sorti de l'attente : il est de nouveau à placer

    def test_une_soumission_incomplete_demande_d_abord_de_completer(self):
        i = self.partielle()
        statut, en_tetes, _ = self.req("GET", f"/soumission/{i}/attente?retour=%2Fsoumissions")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}/completer?pour=attente&retour=%2Fsoumissions"))
        statut, en_tetes, _ = self.post(f"/soumission/{i}/attente", {"retour": "/soumissions", "choix": "indefini"})
        self.assertEqual(en_tetes["Location"], f"/soumission/{i}/completer?pour=attente&retour=%2Fsoumissions")
        self.assertEqual(self.etat(i)[0], "soumission")
        page = self.texte(f"/soumission/{i}/completer?pour=attente&retour=%2Fsoumissions")
        self.assertIn("<h1>Mettre en attente la soumission #", page)
        self.assertIn('name="pour" value="attente"', page)
        self.assertIn("Enregistrer et continuer", page)
        self.assertIn("elle doit être complète, comme pour l'accepter", page)
        # on complète : on passe à la page de la date, SANS accepter la soumission
        form = {"retour": "/soumissions", "pour": "attente", "adresse": "9 Rue des Lilas", "client_secteur": "centre_ville", "duree_estimee_h": "2", "prix_ht": "100"}
        statut, en_tetes, _ = self.post(f"/soumission/{i}/completer", form)
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}/attente?retour=%2Fsoumissions"))
        self.assertEqual(self.etat(i), ("soumission", None))
        self.en_attente(i, reprise=jour_dans(45))
        self.assertEqual(self.etat(i)[0], "en_attente")

    def test_un_complement_partiel_garde_le_cap_vers_l_attente(self):
        i = self.partielle()
        statut, _, page = self.post(f"/soumission/{i}/completer", {"retour": "/soumissions", "pour": "attente", "adresse": "9 Rue des Lilas"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn('name="pour" value="attente"', page)
        self.assertIn("Enregistrer et continuer", page)
        self.assertEqual(self.etat(i)[0], "soumission")

    def test_dates_et_choix_invalides(self):
        i = self.complete()
        for form in ({"choix": "date", "reprise_le": ""}, {"choix": "date", "reprise_le": AUJOURDHUI.isoformat()}, {"choix": "date", "reprise_le": jour_dans(-3)},
                     {"choix": "date", "reprise_le": "2026-13-45"}, {"choix": "peut-etre"}):
            statut, _, page = self.post(f"/soumission/{i}/attente", {"retour": "/soumissions", **form})
            self.assertTrue(statut.startswith("200"), form)
            self.assertIn('class="erreurs"', page, form)
            self.assertEqual(self.etat(i)[0], "soumission", form)

    def test_depuis_la_fiche_on_arrive_sur_le_chantier_en_attente(self):
        i = self.complete()
        fiche = self.get(f"/soumission/{i}")
        self.assertIn(f'href="/soumission/{i}/attente?retour=%2Fchantier%2F{i}">En attente</a>', fiche)
        statut, en_tetes, _ = self.post(f"/soumission/{i}/attente", {"retour": f"/chantier/{i}", "choix": "date", "reprise_le": jour_dans(70)})
        self.assertEqual(en_tetes["Location"], f"/chantier/{i}?ok=mis_en_attente")
        page = self.texte(en_tetes["Location"])
        self.assertIn("Mis en attente", page)
        self.assertIn(f"En attente : reprise le {jour_dans(70)}", page)
        self.assertIn(f"Il redevient « À planifier » le <b>{jour_dans(70)}</b>", page)
        for bouton in ("Sortir de l'attente", "Changer la date", "Remettre en soumission", "Dupliquer"):
            self.assertIn(bouton, page, bouton)
        self.assertNotIn(">Terminer<", page)
        self.assertNotIn("Mettre en attente", page.split("<h1>")[1].split("</main>")[0].replace("Chantier en attente", ""))

    def test_un_chantier_a_planifier_se_met_en_attente_depuis_sa_fiche(self):
        i = self.complete()
        self.post(f"/soumission/{i}/accepter", {})
        fiche = self.get(f"/chantier/{i}")
        self.assertIn(f'href="/chantier/{i}/attente?retour=%2Fchantier%2F{i}">Mettre en attente</a>', fiche)
        page = self.texte(f"/chantier/{i}/attente?retour=%2Fchantier%2F{i}")
        self.assertIn("Un chantier en attente n'est plus proposé dans la Journée.", page)
        self.assertIn(f'action="/chantier/{i}/attente"', page)
        statut, en_tetes, _ = self.post(f"/chantier/{i}/attente", {"retour": f"/chantier/{i}", "choix": "date", "reprise_le": jour_dans(20)})
        self.assertEqual(en_tetes["Location"], f"/chantier/{i}?ok=mis_en_attente")
        self.assertEqual(self.etat(i), ("en_attente", AUJOURDHUI.isoformat()))

    def test_changer_la_date_puis_sortir_de_l_attente(self):
        i = self.en_attente(reprise=jour_dans(30))
        page = self.texte(f"/chantier/{i}/attente")
        self.assertIn("<h1>Changer l'attente</h1>", page)
        self.assertIn(f'name="reprise_le" value="{jour_dans(30)}"', page)
        self.assertIn("Sortir de l'attente maintenant", page)
        statut, en_tetes, _ = self.post(f"/chantier/{i}/attente", {"retour": f"/chantier/{i}", "choix": "date", "reprise_le": jour_dans(90)})
        self.assertEqual(en_tetes["Location"], f"/chantier/{i}?ok=attente_modifiee")
        self.assertEqual(self.sql("SELECT reprise_le FROM chantiers WHERE id = ?", (i,)), [(jour_dans(90),)])
        statut, en_tetes, _ = self.post(f"/chantier/{i}/attente", {"retour": f"/chantier/{i}", "choix": "indefini"})
        self.assertEqual(self.sql("SELECT reprise_le FROM chantiers WHERE id = ?", (i,)), [(None,)])
        self.assertIn("jusqu'à nouvel ordre", self.texte(f"/chantier/{i}/attente"))
        statut, en_tetes, _ = self.post(f"/chantier/{i}/reprendre", {"retour": f"/chantier/{i}"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/chantier/{i}?ok=sorti_attente"))
        self.assertEqual(self.etat(i)[0], "a_planifier")
        self.assertIn("Sorti de l'attente", self.texte(en_tetes["Location"]))
        statut, en_tetes, _ = self.post(f"/chantier/{i}/reprendre", {})
        self.assertIn("err=", en_tetes["Location"])                                         # déjà sorti

    def test_le_retour_automatique_se_fait_a_l_ouverture_d_une_page(self):
        i = self.en_attente(reprise=jour_dans(5), client_nom="Hamel")
        c = sqlite3.connect(self.db)                                                         # le temps a passé : la date de reprise est hier
        c.execute("UPDATE chantiers SET reprise_le = ? WHERE id = ?", (jour_dans(-1), i))
        c.commit()
        c.close()
        page = self.get("/chantiers")
        self.assertEqual(self.etat(i)[0], "a_planifier")
        ligne = page[page.rindex("<tr>", 0, page.index("Hamel")):page.index("</tr>", page.index("Hamel"))]
        self.assertIn("À planifier", ligne)
        self.assertIn("1 j", ligne)                                                          # son délai d'attente compte depuis la date de reprise
        self.assertNotIn("En attente (", page.split("</h1>")[0])

    def test_un_chantier_planifie_ou_termine_ne_se_met_pas_en_attente(self):
        for i in (3, 2):
            statut, en_tetes, _ = self.req("GET", f"/chantier/{i}/attente")
            self.assertEqual(statut[:3], "303")
            self.assertTrue(en_tetes["Location"].startswith(f"/chantier/{i}?err="), en_tetes["Location"])
            statut, en_tetes, _ = self.post(f"/chantier/{i}/attente", {"choix": "indefini"})
            self.assertTrue(en_tetes["Location"].startswith(f"/chantier/{i}?err="))
        self.assertEqual(self.etat(3)[0], "planifie")
        self.assertIn("retire-le d'abord", urllib.parse.unquote_plus(self.req("GET", "/chantier/3/attente")[1]["Location"]))
        self.assertTrue(self.req("GET", "/chantier/999/attente")[0].startswith("404"))
        self.assertTrue(self.post("/soumission/999/attente", {"choix": "indefini"})[0].startswith("404"))
        self.assertTrue(self.post("/chantier/999/reprendre", {})[0].startswith("404"))

    def test_une_fiche_en_attente_se_modifie_sans_changer_d_etat(self):
        i = self.en_attente(reprise=jour_dans(30))
        statut, en_tetes, _ = self.post(f"/chantier/{i}", {**COMPLETE, "description": "Cèdres au fond du terrain"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/chantier/{i}?ok=maj"))
        self.assertEqual(self.sql("SELECT statut, reprise_le, description FROM chantiers WHERE id = ?", (i,)), [("en_attente", jour_dans(30), "Cèdres au fond du terrain")])

    def test_le_raccourci_en_attente(self):
        self.en_attente(reprise=jour_dans(30))
        self.assertIn("+ En attente", self.get("/raccourcis?page=chantiers"))
        statut, en_tetes, _ = self.post("/raccourcis/ajouter", {"page": "chantiers", "code": "en_attente"})
        self.assertEqual(en_tetes["Location"], "/raccourcis?page=chantiers&ok=raccourci_ajoute")
        puces = {n: (c, h) for n, c, a, h in self.puces(self.get("/chantiers"))}
        self.assertEqual(puces["En attente"], (1, "/chantiers?statut=en_attente"))
        self.assertIn("Statut : En attente", self.texte("/raccourcis?page=chantiers"))
        statut, en_tetes, _ = self.post("/raccourcis/ajouter", {"page": "chantiers", "statut": "en_attente", "secteur": "centre_ville"})
        self.assertEqual(en_tetes["Location"], "/raccourcis?page=chantiers&ok=raccourci_ajoute")

    def test_le_texte_de_la_date_est_echappe(self):
        i = self.complete()
        page = self.get(f"/soumission/{i}/attente?reprise_le=%22%3E%3Cscript%3Ealert(1)%3C/script%3E")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&quot;&gt;&lt;script&gt;", page)

    def test_les_messages_existent(self):
        for ok, texte in (("mis_en_attente", "Mis en attente"), ("attente_modifiee", "Attente modifiée"), ("sorti_attente", "Sorti de l'attente")):
            self.assertIn(texte, self.texte(f"/chantiers?ok={ok}"))


class TestClientsSansRenseignements(BasePages):
    def test_la_fiche_d_un_client_vide_est_lisible(self):
        i = self.vide()
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (i,))[0][0]
        page = self.get(f"/client/{cid}")
        self.assertIn("(client à identifier)", page)
        self.assertIn("à saisir", page)
        self.assertIn("à choisir", page)
        self.assertNotIn(", ,", page)
        self.assertIn("+ Nouvelle soumission", page)
        self.assertIn(f'href="/soumission/{i}"', page)

    def test_la_fiche_client_liste_soumissions_et_chantiers_avec_le_bon_lien(self):
        i = self.complete()
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (i,))[0][0]
        self.post(f"/client/{cid}/soumission/nouveau", {"duree_estimee_h": "1", "prix_ht": "100", "type_emondage": "1"})
        j = self.dernier_id()
        self.post(f"/soumission/{i}/accepter", {})
        page = self.get(f"/client/{cid}")
        self.assertIn(f'href="/chantier/{i}"', page)
        self.assertIn(f'href="/soumission/{j}"', page)
        self.assertIn("Soumissions et chantiers", page)

    def test_une_nouvelle_soumission_depuis_la_fiche_ramene_a_la_fiche(self):
        statut, en_tetes, _ = self.post("/client/3/soumission/nouveau", {})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/client/3?ok=soumission_creee"))
        self.assertEqual(self.etat(self.dernier_id())[0], "soumission")
        self.assertIn("Soumission créée.", self.get(en_tetes["Location"]))

    def test_creer_depuis_le_formulaire_ramene_a_la_fiche_du_client(self):
        statut, en_tetes, _ = self.post("/nouveau", {**COMPLETE, "statut": "soumission"})
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (self.dernier_id(),))[0][0]
        self.assertEqual(en_tetes["Location"], f"/client/{cid}?ok=soumission_creee")

    def test_modifier_le_client_revient_ou_on_etait(self):
        i = self.partielle()
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (i,))[0][0]
        page = self.get(f"/client/{cid}/modifier?retour=/soumission/{i}")
        self.assertIn(f'href="/soumission/{i}">Annuler', page)
        self.assertIn(f'name="retour" value="/soumission/{i}"', page)
        form = {"client_nom": "Tremblay", "client_prenom": "Jean", "client_telephone": "450-555-0123", "retour": f"/soumission/{i}"}
        statut, en_tetes, _ = self.post(f"/client/{cid}/modifier", form)
        self.assertEqual(statut[:3], "303")
        self.assertTrue(en_tetes["Location"].startswith(f"/soumission/{i}"), en_tetes["Location"])
        form["retour"] = "https://pirate.example/"
        statut, en_tetes, _ = self.post(f"/client/{cid}/modifier", form)
        self.assertTrue(en_tetes["Location"].startswith(f"/client/{cid}"), en_tetes["Location"])

    def test_un_client_sans_chantier_se_modifie_sans_rien_exiger_mais_pas_avec_un_chantier(self):
        i = self.partielle()
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (i,))[0][0]
        self.assertNotIn('class="requis"', self.get(f"/client/{cid}/modifier"))
        statut, en_tetes, _ = self.post(f"/client/{cid}/modifier", {"client_nom": "Tremblay"})
        self.assertEqual(statut[:3], "303")
        self.assertIn('class="requis"', self.get("/client/3/modifier"))                   # Boucher a un chantier : nom, adresse et secteur obligatoires
        statut, _, page = self.post("/client/3/modifier", {"client_nom": "", "client_prenom": "", "adresse": ""})
        self.assertTrue(statut.startswith("200"))
        self.assertIn('class="erreurs"', page)
        self.assertEqual(self.sql("SELECT nom FROM clients WHERE id = 3"), [("Boucher",)])

    def test_la_recherche_de_client_lit_aussi_les_clients_vides(self):
        i = self.ouvrir(client_telephone="450-555-0199")
        page = self.get("/nouveau?q=555-0199")
        self.assertIn("(client à identifier)", page)
        self.assertNotIn("— ,", page)
        self.assertIn("450-555-0199", page)
        self.assertEqual(self.etat(i)[0], "soumission")

    def test_les_pages_se_rendent_avec_un_client_vide(self):
        self.vide()
        for chemin in ("/", "/clients", "/soumissions", "/chantiers", "/nouveau?q=a", "/journee", "/raccourcis"):
            statut, _, page = self.req("GET", chemin)
            self.assertTrue(statut.startswith("200"), chemin)
            self.assertNotIn("Traceback", page)
            self.assertNotIn(", ,", page, chemin)

    def test_pdf_d_une_journee_avec_un_client_sans_adresse(self):
        """Défense en profondeur : même un chantier planifié dont le client n'a plus d'adresse ne fait pas planter le PDF."""
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        cid = c.execute("INSERT INTO clients (nom) VALUES ('Sansadresse')").lastrowid
        c.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, prix_ht, accepte_le) VALUES (?, 'planifie', '2026-11-03', 2, 100, '2026-10-01')", (cid,))
        c.commit()
        c.close()
        statut, en_tetes, corps = interface.repondre(self.db, "GET", "/journee.pdf", {"date": "2026-11-03"})
        self.assertTrue(statut.startswith("200"), statut)
        self.assertTrue(corps.startswith(b"%PDF"))


class TestRaccourcis(BasePages):
    def chips(self, page_url="/chantiers"):
        return self.puces(self.get(page_url))

    def noms(self, page_url="/chantiers"):
        return [n for n, *_ in self.chips(page_url)]

    def test_raccourcis_de_depart_et_comptes(self):
        puces = self.chips()
        self.assertEqual([n.split(" · ")[0] for n, *_ in puces], ["À recevoir", "Planifiés", "À planifier"])
        par_nom = {n.split(" · ")[0]: (c, h) for n, c, a, h in puces}
        self.assertEqual(par_nom["À recevoir"][0], 2)                                      # Lavoie (terminé, rien payé) et Boucher (acompte)
        self.assertEqual(par_nom["Planifiés"][0], 1)
        self.assertEqual(par_nom["À planifier"][0], 0)
        self.assertIn(vue.argent(3466.64), self.get("/chantiers"))                         # le solde total figure dans la pastille
        self.assertEqual(par_nom["Planifiés"][1], "/chantiers?statut=planifie")

    def test_un_clic_applique_le_filtre_un_deuxieme_le_retire(self):
        page = self.get("/chantiers?statut=planifie")
        actives = [(n, h) for n, c, a, h in self.puces(page) if a]
        self.assertEqual(actives, [("Planifiés", "/chantiers")])                           # active : son lien retire le filtre
        self.assertNotIn("Lavoie", page.split('id="archives"')[0])
        self.assertEqual([a for n, c, a, h in self.chips() if a], [])

    def test_une_pastille_compte_les_soumissions_en_attente(self):
        self.complete(date_soumission=(AUJOURDHUI - datetime.timedelta(days=9)).isoformat())
        self.complete(adresse="2 Rue B")
        puces = {n: (c, h) for n, c, a, h in self.chips("/soumissions")}
        self.assertEqual(puces["À relancer (7 jours et plus)"][0], 1)
        self.assertEqual(puces["À relancer (7 jours et plus)"][1], "/soumissions?attente=relance")

    def test_sans_comptes_pas_de_pastille_mes_soumissions(self):
        self.assertEqual(self.noms("/soumissions"), ["À relancer (7 jours et plus)"])
        page = self.get("/raccourcis?page=soumissions")
        self.assertNotIn("Mes soumissions", page)
        self.assertNotIn('name="par"', page)

    def test_ajouter_un_raccourci_propose(self):
        statut, en_tetes, _ = self.post("/raccourcis/ajouter", {"page": "chantiers", "code": "termine"})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/raccourcis?page=chantiers&ok=raccourci_ajoute"))
        self.assertEqual([n.split(" · ")[0] for n in self.noms()], ["À recevoir", "Planifiés", "À planifier", "Terminés"])
        self.assertNotIn("+ Terminés", self.get("/raccourcis?page=chantiers"))              # il n'est plus proposé : il est déjà là
        statut, en_tetes, _ = self.post("/raccourcis/ajouter", {"page": "chantiers", "code": "termine"})
        self.assertIn("err=", en_tetes["Location"])                                          # pas deux fois le même
        self.assertEqual(len(self.noms()), 4)

    def test_creer_un_raccourci_personnalise(self):
        form = {"page": "chantiers", "statut": "planifie", "secteur": "centre_ville", "libelle": "Planifiés du centre"}
        statut, en_tetes, _ = self.post("/raccourcis/ajouter", form)
        self.assertEqual(en_tetes["Location"], "/raccourcis?page=chantiers&ok=raccourci_ajoute")
        derniere = self.chips()[-1]
        self.assertEqual((derniere[0], derniere[3]), ("Planifiés du centre", "/chantiers?secteur=centre_ville&statut=planifie"))
        self.assertEqual(self.sql("SELECT filtre FROM raccourcis WHERE libelle = 'Planifiés du centre'"), [("secteur=centre_ville&statut=planifie",)])
        # sans nom : le nom est la description des critères
        self.post("/raccourcis/ajouter", {"page": "chantiers", "statut": "termine", "attente": ""})
        self.assertIn("Statut : Terminé", self.sql("SELECT libelle FROM raccourcis ORDER BY id DESC LIMIT 1")[0][0])

    def test_un_raccourci_sans_critere_ou_inconnu_est_refuse(self):
        for form in ({"page": "chantiers"}, {"page": "chantiers", "libelle": "Rien"}, {"page": "chantiers", "code": "inexistant"},
                     {"page": "chantiers", "statut": "nimporte"}):
            avant = self.sql("SELECT count(*) FROM raccourcis")[0][0]
            statut, en_tetes, _ = self.post("/raccourcis/ajouter", form)
            self.assertIn("err=", en_tetes["Location"], form)
            self.assertEqual(self.sql("SELECT count(*) FROM raccourcis")[0][0], avant)

    def test_retirer_et_ne_rien_garder(self):
        self.get("/chantiers")
        ids = [r[0] for r in self.sql("SELECT id FROM raccourcis WHERE page = 'chantiers' ORDER BY ordre")]
        statut, en_tetes, _ = self.post(f"/raccourcis/{ids[0]}/retirer", {"page": "chantiers"})
        self.assertEqual(en_tetes["Location"], "/raccourcis?page=chantiers&ok=raccourci_retire")
        self.assertEqual([n.split(" · ")[0] for n in self.noms()], ["Planifiés", "À planifier"])
        for i in ids[1:]:
            self.post(f"/raccourcis/{i}/retirer", {"page": "chantiers"})
        page = self.get("/chantiers")
        self.assertEqual(self.puces(page), [])                                                # plus aucune pastille...
        self.assertIn("Modifier les raccourcis", page)                                       # ...mais le lien pour en remettre reste
        self.assertEqual(self.noms(), [])                                                     # et ceux du départ ne reviennent pas tout seuls
        self.assertIn("Aucun raccourci", self.get("/raccourcis?page=chantiers"))
        statut, en_tetes, _ = self.post(f"/raccourcis/{ids[0]}/retirer", {"page": "chantiers"})
        self.assertIn("err=", en_tetes["Location"])                                          # déjà retiré

    def test_remettre_ceux_du_depart(self):
        self.post("/raccourcis/ajouter", {"page": "chantiers", "code": "termine"})
        for (i,) in self.sql("SELECT id FROM raccourcis WHERE page = 'chantiers' AND filtre <> '__vide__' AND libelle <> 'Terminés'"):
            self.post(f"/raccourcis/{i}/retirer", {"page": "chantiers"})
        statut, en_tetes, _ = self.post("/raccourcis/reinitialiser", {"page": "chantiers"})
        self.assertEqual(en_tetes["Location"], "/raccourcis?page=chantiers&ok=raccourcis_reinitialises")
        self.assertEqual([n.split(" · ")[0] for n in self.noms()], ["À recevoir", "Planifiés", "À planifier"])

    def test_deplacer_un_raccourci(self):
        self.get("/chantiers")
        ids = [r[0] for r in self.sql("SELECT id FROM raccourcis WHERE page = 'chantiers' ORDER BY ordre")]
        self.post(f"/raccourcis/{ids[2]}/deplacer", {"page": "chantiers", "sens": "haut"})
        self.assertEqual([n.split(" · ")[0] for n in self.noms()], ["À recevoir", "À planifier", "Planifiés"])
        self.post(f"/raccourcis/{ids[0]}/deplacer", {"page": "chantiers", "sens": "bas"})
        self.assertEqual([n.split(" · ")[0] for n in self.noms()], ["À planifier", "À recevoir", "Planifiés"])
        self.post(f"/raccourcis/{ids[0]}/deplacer", {"page": "chantiers", "sens": "bas"})
        self.post(f"/raccourcis/{ids[0]}/deplacer", {"page": "chantiers", "sens": "bas"})          # déjà en bas : rien ne bouge
        self.assertEqual([n.split(" · ")[0] for n in self.noms()], ["À planifier", "Planifiés", "À recevoir"])
        statut, en_tetes, _ = self.post(f"/raccourcis/{ids[0]}/deplacer", {"page": "chantiers", "sens": "diagonale"})
        self.assertIn("err=", en_tetes["Location"])

    def test_la_page_de_modification_et_les_pages_inconnues(self):
        page = self.get("/raccourcis?page=chantiers")
        for texte in ("Mes raccourcis", "Ajouter un raccourci proposé", "Créer un raccourci personnalisé", "Rétablir ceux du départ", "Retour à Chantiers"):
            self.assertIn(texte, page)
        self.assertIn("Retour à Soumissions", self.get("/raccourcis?page=soumissions"))
        self.assertIn("Retour à Chantiers", self.get("/raccourcis?page=nimporte"))          # page inconnue : Chantiers
        self.assertIn("Raccourcis", self.get("/raccourcis"))

    def test_les_pages_chantiers_et_soumissions_ont_chacune_leurs_raccourcis(self):
        self.post("/raccourcis/ajouter", {"page": "soumissions", "attente": "urgente", "libelle": "Sans nouvelles"})
        self.assertIn("Sans nouvelles", self.noms("/soumissions"))
        self.assertNotIn("Sans nouvelles", self.noms("/chantiers"))

    def test_canonique(self):
        self.assertEqual(raccourcis.canonique("statut=planifie&secteur=centre_ville"), "secteur=centre_ville&statut=planifie")
        self.assertEqual(raccourcis.canonique("zzz=1&statut=planifie&q="), "statut=planifie")                 # inconnu et vide : ignorés
        self.assertEqual(raccourcis.canonique(""), "")
        self.assertEqual(raccourcis.canonique(None), "")
        self.assertEqual(len(dict(urllib.parse.parse_qsl(raccourcis.canonique("q=" + "x" * 200)))["q"]), 60)   # texte borné


class BaseComptes(BasePages):
    def setUp(self):
        super().setUp()
        self.ancien = auth.ITERATIONS
        auth.ITERATIONS = 1000
        auth.reinitialiser_blocages()
        self.addCleanup(lambda: setattr(auth, "ITERATIONS", self.ancien))
        c, _ = noyau.ouvrir_base(self.db)
        for nom, role in (("Admin", "admin"), ("Alice", "soumission"), ("Marc", "soumission")):
            self.assertEqual(auth.creer_utilisateur(c, nom, "motdepasse-" + nom.lower(), role), [])
        c.close()
        self.admin = self.connecter("Admin")
        self.alice = self.connecter("Alice")
        self.marc = self.connecter("Marc")

    def connecter(self, nom):
        statut, en_tetes, _ = self.req("POST", "/connexion", {"nom": nom, "mot_de_passe": "motdepasse-" + nom.lower()}, cookie="")
        self.assertTrue(statut.startswith("303"), statut)
        return en_tetes["Set-Cookie"].split(";")[0]


class TestComptesEtSoumissions(BaseComptes):
    def test_la_soumission_garde_le_nom_de_qui_l_a_ouverte(self):
        i = self.complete(cookie=self.alice)
        self.assertEqual(self.sql("SELECT cree_par FROM chantiers WHERE id = ?", (i,)), [("Alice",)])
        self.assertIn("par Alice", self.get("/soumissions", cookie=self.marc))
        self.assertIn("Ouverte par Alice", self.get(f"/soumission/{i}", cookie=self.marc))

    def test_mes_soumissions(self):
        self.complete(cookie=self.alice, client_nom="DeAlice", adresse="1 Rue A")
        self.complete(cookie=self.marc, client_nom="DeMarc", adresse="2 Rue B")
        puces = {n: (c, h) for n, c, a, h in self.puces(self.get("/soumissions", cookie=self.marc))}
        self.assertEqual(puces["Mes soumissions"], (1, "/soumissions?par=moi"))
        page = self.get("/soumissions?par=moi", cookie=self.marc)
        self.assertIn("DeMarc", page)
        self.assertNotIn("DeAlice", page)
        page = self.get("/soumissions?par=Alice", cookie=self.admin)                         # l'administrateur filtre par nom
        self.assertIn("DeAlice", page)
        self.assertNotIn("DeMarc", page)
        self.assertIn("Ouvertes par Alice", self.get("/soumissions", cookie=self.admin))

    def test_chacun_ses_raccourcis(self):
        self.get("/chantiers", cookie=self.alice)
        self.get("/chantiers", cookie=self.marc)
        self.post("/raccourcis/ajouter", {"page": "chantiers", "code": "termine"}, cookie=self.alice)
        noms = lambda cookie: [n.split(" · ")[0] for n, *_ in self.puces(self.get("/chantiers", cookie=cookie))]
        self.assertEqual(noms(self.alice), ["À planifier", "Planifiés", "Terminés"])
        self.assertEqual(noms(self.marc), ["À planifier", "Planifiés"])
        self.assertEqual(noms(self.admin), ["À recevoir", "Planifiés", "À planifier"])
        # Marc ne peut pas retirer ni déplacer un raccourci d'Alice
        id_alice = self.sql("SELECT id FROM raccourcis WHERE libelle = 'Terminés'")[0][0]
        statut, en_tetes, _ = self.post(f"/raccourcis/{id_alice}/retirer", {"page": "chantiers"}, cookie=self.marc)
        self.assertIn("err=", en_tetes["Location"])
        statut, en_tetes, _ = self.post(f"/raccourcis/{id_alice}/deplacer", {"page": "chantiers", "sens": "haut"}, cookie=self.marc)
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(noms(self.alice), ["À planifier", "Planifiés", "Terminés"])

    def test_pas_de_finances_pour_le_compte_soumission(self):
        for cookie in (self.alice, self.marc):
            page = self.get("/chantiers", cookie=cookie)
            self.assertNotIn("À recevoir", page)
            self.assertNotIn("Paiement", page)
            page = self.get("/raccourcis?page=chantiers", cookie=cookie)
            self.assertNotIn("À recevoir", page)
            self.assertNotIn("Payés en partie", page)
            self.assertNotIn('name="paiement"', page)
        statut, en_tetes, _ = self.post("/raccourcis/ajouter", {"page": "chantiers", "code": "a_recevoir"}, cookie=self.alice)
        self.assertIn("err=", en_tetes["Location"])
        statut, en_tetes, _ = self.post("/raccourcis/ajouter", {"page": "chantiers", "paiement": "partiel"}, cookie=self.alice)
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT count(*) FROM raccourcis WHERE filtre LIKE '%paiement%'"), [(0,)])

    def test_le_filtre_de_paiement_par_adresse_est_ignore_pour_le_compte_soumission(self):
        i = self.complete(cookie=self.alice, client_nom="Nouveau", adresse="5 Rue C")
        self.post(f"/soumission/{i}/accepter", {}, cookie=self.alice)                      # chantier « À planifier » : rien à recevoir
        avec_filtre = self.get("/chantiers?paiement=a_recevoir", cookie=self.alice)
        self.assertIn("Nouveau", avec_filtre)                                                # le filtre n'agit pas : aucune fuite sur les paiements
        self.assertIn("Boucher", avec_filtre)
        admin = self.get("/chantiers?paiement=a_recevoir", cookie=self.admin)
        self.assertNotIn("Nouveau", admin.split('id="archives"')[0])
        self.assertIn("Boucher", admin)

    def test_pastilles_de_depart_selon_le_role(self):
        self.assertEqual([n.split(" · ")[0] for n, *_ in self.puces(self.get("/soumissions", cookie=self.alice))], ["Mes soumissions", "À relancer (7 jours et plus)"])
        self.assertEqual([n.split(" · ")[0] for n, *_ in self.puces(self.get("/soumissions", cookie=self.admin))], ["Mes soumissions", "À relancer (7 jours et plus)"])

    def test_droits_du_compte_soumission_sur_les_nouvelles_routes(self):
        i = self.complete(cookie=self.alice)
        j = self.vide(cookie=self.alice)
        self.assertTrue(self.req("GET", "/soumissions", cookie=self.alice)[0].startswith("200"))
        self.assertTrue(self.req("GET", f"/soumission/{j}/completer", cookie=self.alice)[0].startswith("200"))
        self.assertTrue(self.req("GET", "/raccourcis", cookie=self.alice)[0].startswith("200"))
        self.assertTrue(self.post(f"/soumission/{i}/accepter", {}, cookie=self.alice)[0].startswith("303"))
        self.assertEqual(self.etat(i)[0], "a_planifier")
        self.assertTrue(self.post(f"/soumission/{j}/refuser", {}, cookie=self.alice)[0].startswith("303"))
        self.assertEqual(self.etat(j)[0], "annule")
        self.assertTrue(self.post(f"/soumission/{j}/rouvrir", {}, cookie=self.alice)[0].startswith("303"))
        self.assertEqual(self.etat(j)[0], "soumission")
        self.assertEqual(self.post(f"/soumission/{j}/supprimer", {}, cookie=self.alice)[0][:3], "403")        # supprimer : administrateur seulement
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE id = ?", (j,)), [(1,)])
        page = self.get(f"/soumission/{j}", cookie=self.alice)
        self.assertNotIn("Supprimer cette soumission", page)
        self.assertIn("Supprimer cette soumission", self.get(f"/soumission/{j}", cookie=self.admin))
        self.assertTrue(self.post(f"/soumission/{j}/supprimer", {}, cookie=self.admin)[0].startswith("303"))

    def test_le_compte_soumission_met_en_attente_et_sort_de_l_attente(self):
        i = self.complete(cookie=self.alice)
        statut, en_tetes, _ = self.post(f"/soumission/{i}/attente", {"retour": "/soumissions", "choix": "date", "reprise_le": jour_dans(60)}, cookie=self.alice)
        self.assertEqual(en_tetes["Location"], "/soumissions?ok=mis_en_attente")
        self.assertEqual(self.sql("SELECT statut, reprise_le FROM chantiers WHERE id = ?", (i,)), [("en_attente", jour_dans(60))])
        self.assertIn('href="/chantiers?statut=en_attente">En attente (1)</a>', self.get("/soumissions", cookie=self.marc))
        page = self.get("/chantiers?statut=en_attente", cookie=self.marc)                       # la liste, sans finances, pour tout le monde
        self.assertIn("Roy", page)
        self.assertNotIn("Paiement", page)
        self.assertTrue(self.req("GET", f"/chantier/{i}/attente", cookie=self.marc)[0].startswith("200"))
        statut, en_tetes, _ = self.post(f"/chantier/{i}/reprendre", {}, cookie=self.marc)
        self.assertEqual(en_tetes["Location"], f"/chantier/{i}?ok=sorti_attente")
        self.assertEqual(self.etat(i)[0], "a_planifier")

    def test_l_administrateur_peut_supprimer_une_soumission_refusee(self):
        i = self.vide(cookie=self.alice)
        self.post(f"/soumission/{i}/refuser", {}, cookie=self.alice)
        self.assertNotIn("Supprimer cette soumission", self.get(f"/soumission/{i}", cookie=self.alice))
        self.assertIn("Supprimer cette soumission", self.get(f"/soumission/{i}", cookie=self.admin))
        self.assertEqual(self.post(f"/soumission/{i}/supprimer", {}, cookie=self.alice)[0][:3], "403")
        statut, en_tetes, _ = self.post(f"/soumission/{i}/supprimer", {}, cookie=self.admin)
        self.assertEqual(en_tetes["Location"], "/soumissions?ok=soumission_supprimee")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE id = ?", (i,)), [(0,)])

    def test_sans_connexion_les_nouvelles_pages_exigent_un_compte(self):
        for methode, chemin in (("GET", "/soumissions"), ("GET", "/soumission/1"), ("GET", "/raccourcis"), ("POST", "/soumission/1/accepter"),
                                ("POST", "/raccourcis/ajouter")):
            statut, en_tetes, corps = self.req(methode, chemin, {}, cookie="")
            self.assertTrue(statut.startswith("303"), (chemin, statut))
            self.assertTrue(en_tetes["Location"].startswith("/connexion"))
            self.assertNotIn("Boucher", corps)

    def test_le_telephone_garde_chantiers_soumissions_clients_et_nouvelle_soumission(self):
        telephone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148 Safari/604.1"
        page = self.get("/soumissions", cookie=self.alice, agent=telephone)
        barre = page[page.index('class="barre-mobile"'):]
        for lien in ('href="/chantiers"', 'href="/soumissions"', 'href="/clients"', 'href="/nouveau"'):
            self.assertIn(lien, barre)
        self.assertIn("+ Soumission", barre)
        self.assertLess(barre.index('href="/chantiers"'), barre.index('href="/soumissions"'))


class TestAides(unittest.TestCase):
    def test_adresses_sans_virgule_en_trop(self):
        self.assertEqual(noyau.adresses("9 Rue des Lilas", "", "QC", ""), ("9 Rue des Lilas, QC", "9 Rue des Lilas, QC, Canada"))
        self.assertEqual(noyau.adresses("123 Rue des Érables", "Saint-Jérôme", "QC", "J7Z 1A1"),
                         ("123 Rue des Érables, Saint-Jérôme, QC J7Z 1A1", "123 Rue des Érables, Saint-Jérôme, QC J7Z 1A1, Canada"))
        self.assertEqual(noyau.adresses("", "Mirabel", "QC", "J7J 1A1"), ("", ""))
        self.assertEqual(noyau.adresses(None, None, None, None), ("", ""))

    def test_adresse_de_la_vue_et_aide_python_concordent(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(db)
        conn, _ = noyau.ouvrir_base(db)
        self.addCleanup(conn.close)
        for adresse, ville, province, cp, maps in conn.execute(
                "SELECT cl.adresse, cl.ville, cl.province, cl.code_postal, v.adresse_maps FROM v_chantiers v JOIN clients cl ON cl.id = v.client_id"):
            self.assertEqual(noyau.adresses(adresse, ville, province, cp)[1], maps)

    def test_lien_maps_et_case_taxes(self):
        self.assertIn("google.com/maps/search", vue.lien_maps("1 Rue A, QC, Canada", "1 Rue A"))
        self.assertIn("adresse à saisir", vue.lien_maps("", ""))
        case = vue.case_taxes("taxes_auto", " checked")
        self.assertIn('name="taxes_auto"', case)
        self.assertIn(" checked", case)
        self.assertNotIn(" checked", vue.case_taxes("taxes_auto", ""))
        self.assertIn("TPS 5 % et TVQ 9,975 %", case)

    def test_aucun_emoji_dans_les_nouvelles_pages(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(db)
        for chemin in ("/soumissions", "/raccourcis", "/raccourcis?page=soumissions", "/nouveau", "/chantiers"):
            page = interface.repondre(db, "GET", chemin, {})[2].decode("utf-8")
            interdits = [c for c in page if ord(c) > 0x2000 and c not in "–—‘’“”…•▲▼→€"]
            self.assertEqual(interdits, [], chemin)


if __name__ == "__main__":
    unittest.main()
