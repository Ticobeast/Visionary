"""Tests de l'interface de saisie (outils/interface.py).

    python3 -m unittest discover -s tests -v
"""
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
import importer_saisie  # noqa: E402
import interface  # noqa: E402

EXEMPLES = RACINE / "modeles" / "saisie_papier_exemples.csv"


def fiche(**perso):
    base = dict(client_nom="Roy", client_prenom="Sylvie", client_telephone="450-555-0111", client_sms_ok="1",
                adresse="22 Rue des Pins", ville="Mirabel", province="QC", type_travaux="emondage", statut="soumission")
    base.update(perso)
    return base


class BaseInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        importer_saisie.importer(EXEMPLES, self.db)

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


class TestPages(BaseInterface):
    def test_liste_et_puces(self):
        statut, page = self.get("/")
        self.assertTrue(statut.startswith("200"))
        for nom in ("Marie Gagnon", "Pierre Lavoie", "Luc Boucher"):
            self.assertIn(nom, page)
        self.assertIn("à facturer", page)
        self.assertIn("1 437,19 $", page)       # Lavoie : 1250 + taxes, non facturé

    def test_filtres_et_recherche_sans_accent(self):
        self.assertNotIn("Marie Gagnon", self.get("/?paiement=non_facture")[1])
        self.assertIn("Pierre Lavoie", self.get("/?paiement=non_facture")[1])
        self.assertIn("Luc Boucher", self.get("/?statut=planifie")[1])
        self.assertNotIn("Pierre Lavoie", self.get("/?statut=planifie")[1])
        self.assertIn("Marie Gagnon", self.get("/?q=erables")[1])             # « Érables » trouvé sans accent
        self.assertIn("Marie Gagnon", self.get("/?q=450-555-0142")[1])
        self.assertNotIn("Pierre Lavoie", self.get("/?q=gagnon")[1])

    def test_pages_de_detail_et_introuvable(self):
        statut, page = self.get("/chantier/1")
        self.assertIn("123 Rue des Érables, Saint-Jérôme, QC J7Z 1A1, Canada", page)
        self.assertIn("google.com/maps/search", page)
        self.assertIn("551,88 $", page)
        self.assertTrue(self.get("/chantier/999")[0].startswith("404"))
        self.assertTrue(self.get("/nimporte")[0].startswith("404"))

    def test_recherche_de_client_existant(self):
        self.assertIn("/nouveau?client_id=2", self.get("/nouveau?q=lavoie")[1])
        self.assertIn("Aucun client trouvé", self.get("/nouveau?q=zzz")[1])
        self.assertIn("Nouveau chantier pour", self.get("/nouveau?client_id=2")[1])

    def test_html_est_echappe(self):
        self.post("/nouveau", fiche(client_nom="<script>alert(1)</script>", description="<img src=x onerror=alert(2)>"))
        for chemin in ("/", "/chantier/4", "/nouveau?q=script"):
            page = self.get(chemin)[1]
            self.assertNotIn("<script>alert", page, chemin)
            self.assertNotIn("<img src=x", page, chemin)
        self.assertIn("&lt;script&gt;", self.get("/")[1])


class TestCreation(BaseInterface):
    def test_creation_complete(self):
        statut, en_tetes, _ = self.post("/nouveau", fiche(
            date_prevue="2026-10-20", statut="planifie", heure_prevue="08:30", duree_estimee_h="2,5",
            prix_ht="300,00", taxes_auto="1", code_postal="j7j1a1", dossier_photos="photos/2026/2026-10-20_roy",
            paiement_date="2026-10-01", paiement_montant="100", paiement_mode="interac"))
        self.assertTrue(statut.startswith("303"))
        self.assertEqual(en_tetes["Location"], "/chantier/4?ok=cree")
        self.assertEqual(self.sql("SELECT telephone, code_postal, geocode_statut FROM clients WHERE nom = 'Roy'"),
                         [("+14505550111", "J7J 1A1", "a_faire")])
        self.assertEqual(self.sql("SELECT statut, date_prevue, heure_prevue, duree_estimee_h, prix_ht, tps, tvq FROM chantiers WHERE id = 4"),
                         [("planifie", "2026-10-20", "08:30", 2.5, 300.0, 15.0, 29.93)])
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = 4"), [("partiel", 244.93)])
        self.assertIn("Chantier créé", self.get("/chantier/4?ok=cree")[1])

    def test_erreurs_gardent_les_valeurs_et_n_ecrivent_rien(self):
        statut, _, page = self.post("/nouveau", fiche(date_prevue="14/06/2026", client_telephone="123",
                                                      client_nom="Nom gardé", statut="planifie"))
        self.assertTrue(statut.startswith("200"))
        self.assertIn("À corriger", page)
        self.assertIn("AAAA-MM-JJ", page)
        self.assertIn('value="Nom gardé"', page)
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_refus_de_la_base_est_affiche(self):
        _, _, page = self.post("/nouveau", fiche(date_facture="2026-06-14"))   # facture sans prix
        self.assertIn("Refusé par la base", page)
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])      # transaction annulée : pas de client orphelin

    def test_meme_adresse_reutilise_le_client(self):
        _, en_tetes, _ = self.post("/nouveau", fiche(client_nom="Gagnon", client_prenom="Marie", adresse="123 rue des erables",
                                                     ville="Saint-Jerome", type_travaux="elagage"))
        self.assertEqual(en_tetes["Location"], "/chantier/4?ok=cree_reutilise")
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id = 4"), [(1,)])

    def test_nouveau_chantier_pour_client_existant(self):
        _, en_tetes, _ = self.post("/nouveau", fiche(client_id="2", client_nom="Lavoie", client_prenom="Pierre",
                                                     adresse="Lot 12-4, Rang du Ruisseau", ville="Mirabel",
                                                     client_telephone="+14505550177", latitude="45.6480", longitude="-74.0920",
                                                     type_travaux="taille_haie"))
        self.assertTrue(en_tetes["Location"].startswith("/chantier/4"))
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE client_id = 2"), [(2,)])
        self.assertEqual(self.sql("SELECT geocode_statut FROM clients WHERE id = 2"), [("manuel",)])


class TestModification(BaseInterface):
    def formulaire_de(self, chantier_id):
        """Valeurs du formulaire d'édition, telles que le navigateur les renverrait."""
        conn, _ = interface.ouvrir_base(self.db)
        try:
            valeurs, _ = interface.valeurs_chantier(conn, chantier_id)
        finally:
            conn.close()
        valeurs.pop("client_id", None)
        return valeurs

    def test_edition_sans_changement_ne_change_rien(self):
        avant = self.sql("SELECT * FROM clients ORDER BY id") + self.sql("SELECT * FROM chantiers ORDER BY id")
        for i in (1, 2, 3):
            statut, en_tetes, _ = self.post(f"/chantier/{i}", {**self.formulaire_de(i), "client_sms_ok": "1"})
            self.assertEqual(en_tetes["Location"], f"/chantier/{i}?ok=maj")
        self.assertEqual(self.sql("SELECT * FROM clients ORDER BY id") + self.sql("SELECT * FROM chantiers ORDER BY id"), avant)

    def test_passer_a_termine_exige_la_date(self):
        f = {**self.formulaire_de(3), "statut": "termine", "client_sms_ok": "1"}
        _, _, page = self.post("/chantier/3", f)
        self.assertIn("date_realisee est obligatoire", page)
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = 3"), [("planifie",)])
        self.post("/chantier/3", {**f, "date_realisee": "2026-10-14", "duree_reelle_h": "6,5"})
        self.assertEqual(self.sql("SELECT statut, date_realisee, duree_reelle_h FROM chantiers WHERE id = 3"),
                         [("termine", "2026-10-14", 6.5)])
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 3"), [("partiel",)])

    def test_changer_l_adresse_efface_les_coordonnees_perimees(self):
        f = {**self.formulaire_de(2), "client_sms_ok": "1"}
        self.assertEqual(self.sql("SELECT latitude, geocode_statut FROM clients WHERE id = 2"), [(45.648, "manuel")])
        self.post("/chantier/2", {**f, "description": "autre texte"})      # autre champ : coordonnées conservées
        self.assertEqual(self.sql("SELECT latitude, geocode_statut FROM clients WHERE id = 2"), [(45.648, "manuel")])
        self.post("/chantier/2", {**f, "adresse": "99 Chemin Neuf"})        # adresse changée : coordonnées périmées
        self.assertEqual(self.sql("SELECT latitude, longitude, geocode_statut FROM clients WHERE id = 2"), [(None, None, "a_faire")])

    def test_decocher_sms_est_pris_en_compte(self):
        f = self.formulaire_de(1)
        f.pop("client_sms_ok", None)                                         # case décochée : absente du POST
        self.post("/chantier/1", f)
        self.assertEqual(self.sql("SELECT sms_ok FROM clients WHERE id = 1"), [(0,)])


class TestPaiementsEtSuppression(BaseInterface):
    def test_ajouter_et_supprimer_un_paiement(self):
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 2"), [("non_facture",)])
        statut, en_tetes, _ = self.post("/chantier/2/paiement", {"paiement_date": "2026-10-02", "paiement_montant": "1 437,19",
                                                                  "paiement_mode": "cheque", "paiement_reference": "#0418"})
        self.assertEqual(en_tetes["Location"], "/chantier/2?ok=paiement")
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = 2"), [("paye", 0.0)])
        pid = self.sql("SELECT max(id) FROM paiements")[0][0]
        self.post(f"/paiement/{pid}/supprimer", {})
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 2"), [("non_facture",)])

    def test_paiement_invalide(self):
        for form in ({"paiement_date": "", "paiement_montant": "50", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "0", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "12,345", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "50", "paiement_mode": "bitcoin"}):
            statut, _, page = self.post("/chantier/2/paiement", form)
            self.assertTrue(statut.startswith("200"), form)
            self.assertIn("erreurs", page)
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(2,)])

    def test_supprimer_un_chantier_et_son_client_orphelin(self):
        _, _, page = self.post("/chantier/1/supprimer", {})                 # a un paiement : refusé
        self.assertIn("a des paiements", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        statut, en_tetes, _ = self.post("/chantier/2/supprimer", {})        # aucun paiement
        self.assertEqual(en_tetes["Location"], "/?ok=supprime")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(2,)])
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 2"), [(0,)])

    def test_client_avec_autre_chantier_n_est_pas_supprime(self):
        self.post("/nouveau", fiche(client_id="2", client_nom="Lavoie", adresse="Lot 12-4, Rang du Ruisseau", ville="Mirabel"))
        self.post("/chantier/2/supprimer", {})
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 2"), [(1,)])


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
        statut, _, page = self.requete("/")
        self.assertEqual(statut, 200)
        self.assertIn("Marie Gagnon", page)
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
