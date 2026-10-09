"""Tests de l'accès à distance (outils/reseau.py et mode --reseau du serveur) : seuls cet ordinateur et les appareils
Tailscale (100.64.0.0/10) sont acceptés, jamais le Wi-Fi de l'atelier ni Internet.

    python3 -m unittest discover -s tests -v
"""
import http.client
import sys
import tempfile
import threading
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import fixtures  # noqa: E402
import interface  # noqa: E402
import reseau  # noqa: E402


class TestClientAutorise(unittest.TestCase):
    def test_cet_ordinateur_toujours(self):
        for reseau_actif in (False, True):
            self.assertTrue(reseau.client_autorise("127.0.0.1", reseau_actif))
            self.assertTrue(reseau.client_autorise("::1", reseau_actif))

    def test_tailscale_seulement_en_mode_reseau(self):
        for ip in ("100.64.0.1", "100.101.102.103", "100.127.255.254"):
            self.assertTrue(reseau.client_autorise(ip, True), ip)
            self.assertFalse(reseau.client_autorise(ip, False), ip)

    def test_le_reste_du_monde_est_refuse(self):
        for ip in ("192.168.1.20", "10.0.0.5", "172.16.0.9", "8.8.8.8", "100.63.255.255", "100.128.0.1", "0.0.0.0", "n'importe quoi", ""):
            self.assertFalse(reseau.client_autorise(ip, True), ip)


class TestHoteAutorise(unittest.TestCase):
    def test_local(self):
        for h in ("localhost:8765", "127.0.0.1:8765", "LOCALHOST:8765"):
            self.assertTrue(reseau.hote_autorise(h, 8765, False), h)
        self.assertFalse(reseau.hote_autorise("localhost:9999", 8765, False))        # mauvais port
        self.assertFalse(reseau.hote_autorise("localhost", 8765, False))             # port absent

    def test_noms_et_adresses_tailscale(self):
        ok = ("100.101.102.103:8765", "atelier.tail1234.ts.net:8765", "atelier:8765", "ATELIER:8765")
        for h in ok:
            self.assertTrue(reseau.hote_autorise(h, 8765, True, nom_machine="Atelier"), h)
            self.assertFalse(reseau.hote_autorise(h, 8765, False, nom_machine="Atelier"), h)   # mode local : refusé

    def test_sites_web_et_adresses_etrangeres_refuses(self):
        for h in ("evil.example.com:8765", "192.168.1.20:8765", "8.8.8.8:8765", "evil.ts.net.example.com:8765", "[::1]:8765", "", None):
            self.assertFalse(reseau.hote_autorise(h, 8765, True, nom_machine="atelier"), h)


class TestServeur(unittest.TestCase):
    """Vrai serveur (connexions depuis 127.0.0.1 : l'appareil est local, l'en-tête Host varie)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def demarrer(self, mode_reseau):
        self.serveur = interface.creer_serveur(self.db, 0, mode_reseau)
        self.port = self.serveur.server_address[1]
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.serveur.shutdown(), self.serveur.server_close()))

    def statut(self, hote, chemin="/", methode="GET", en_tetes=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.putrequest(methode, chemin, skip_host=True)
        c.putheader("Host", hote)
        for k, v in (en_tetes or {}).items():
            c.putheader(k, v)
        c.putheader("Content-Length", "0")
        c.endheaders()
        code = c.getresponse().status
        c.close()
        return code

    def test_mode_local_refuse_un_nom_tailscale(self):
        self.demarrer(False)
        self.assertEqual(self.statut(f"localhost:{self.port}"), 200)
        self.assertEqual(self.statut(f"100.100.100.100:{self.port}"), 403)
        self.assertEqual(self.serveur.server_address[0], "127.0.0.1")

    def test_mode_reseau_accepte_les_adresses_tailscale(self):
        self.demarrer(True)
        self.assertEqual(self.serveur.server_address[0], "0.0.0.0")
        self.assertEqual(self.statut(f"localhost:{self.port}"), 200)
        self.assertEqual(self.statut(f"100.100.100.100:{self.port}"), 200)
        self.assertEqual(self.statut(f"atelier.tail1234.ts.net:{self.port}"), 200)
        self.assertEqual(self.statut(f"evil.example.com:{self.port}"), 403)
        self.assertEqual(self.statut(f"192.168.1.20:{self.port}"), 403)

    def test_origine_etrangere_refusee_pour_les_ecritures(self):
        self.demarrer(True)
        self.assertEqual(self.statut(f"100.100.100.100:{self.port}", "/clients", "GET", {"Origin": "http://evil.example.com"}), 403)
        self.assertEqual(self.statut(f"100.100.100.100:{self.port}", "/clients", "GET", {"Origin": f"http://100.100.100.100:{self.port}"}), 200)

    def test_appareil_hors_tailscale_refuse_meme_avec_un_bon_en_tete(self):
        """Un appareil du Wi-Fi de l'atelier (192.168...) qui atteint le port est refusé, même avec un en-tête Host valide."""
        class Faux(interface.Gestionnaire):
            def __init__(self, ip, port):                      # pas de vraie connexion
                self.client_address = (ip, 50000)
                self.headers = {"Host": f"100.100.100.100:{port}"}
                self.path = "/"
                self.reponse = None
                self.db_path = Path(self_db)

            def _envoyer(self, statut, en_tetes, corps):
                self.reponse = statut
        self_db = str(self.db)
        # (« Aucun compte » : un appareil Tailscale passe la porte du réseau mais l'application reste fermée tant qu'aucun
        # compte n'existe ; voir test_auth pour la suite)
        for ip, attendu in (("192.168.1.50", "403 Forbidden"), ("8.8.8.8", "403 Forbidden"), ("100.90.80.70", "403 Forbidden")):
            Faux.reseau, Faux.port = True, 8765
            f = Faux(ip, 8765)
            f._traiter("GET")
            self.assertEqual(f.reponse, attendu, ip)


class TestModificationsSimultanees(unittest.TestCase):
    """Deux personnes ouvrent la même fiche : la deuxième à enregistrer est prévenue au lieu d'écraser la première."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)
        self.addCleanup(self._tmp.cleanup)

    def get(self, chemin):
        return interface.repondre(self.db, "GET", chemin, {})[2].decode("utf-8")

    def post(self, chemin, form):
        statut, en_tetes, corps = interface.repondre(self.db, "POST", chemin, {}, form)
        return statut, dict(en_tetes), corps.decode("utf-8")

    @staticmethod
    def empreinte(page, action):
        morceau = page[page.index(f'action="{action}"'):]
        return morceau.split('name="empreinte" value="', 1)[1].split('"', 1)[0]

    def formulaire(self, chantier_id, **plus):
        conn, _ = interface.ouvrir_base(self.db)
        try:
            valeurs, _ = interface.valeurs_chantier(conn, chantier_id)
        finally:
            conn.close()
        valeurs.pop("client_id", None)
        valeurs.update(plus)
        return valeurs

    def test_chantier_deuxieme_enregistrement_refuse(self):
        page = self.get("/chantier/3")
        empreinte = self.empreinte(page, "/chantier/3")
        un = self.formulaire(3, description="Version de la personne 1", empreinte=empreinte)
        deux = self.formulaire(3, description="Version de la personne 2", empreinte=empreinte)
        self.assertTrue(self.post("/chantier/3", un)[0].startswith("303"))                # la première enregistre
        statut, _, corps = self.post("/chantier/3", deux)
        self.assertTrue(statut.startswith("200"))                                          # la deuxième est refusée avec explication
        self.assertIn("modifiée par quelqu", corps)
        self.assertIn("Version de la personne 1", corps)                                   # elle voit les valeurs à jour
        c = interface.ouvrir_base(self.db)[0]
        self.assertEqual(c.execute("SELECT description FROM chantiers WHERE id = 3").fetchone()[0], "Version de la personne 1")
        c.close()
        # après rechargement de la page, l'enregistrement redevient possible
        neuf = self.empreinte(self.get("/chantier/3"), "/chantier/3")
        self.assertTrue(self.post("/chantier/3", self.formulaire(3, description="Version 3", empreinte=neuf))[0].startswith("303"))

    def test_changement_de_la_journee_pendant_la_modification(self):
        empreinte = self.empreinte(self.get("/chantier/3"), "/chantier/3")
        self.post("/action/retirer", {"chantier_id": "3", "retour": "/"})                  # quelqu'un d'autre le retire de la journée
        statut, _, corps = self.post("/chantier/3", self.formulaire(3, description="x", empreinte=empreinte))
        self.assertIn("modifiée par quelqu", corps)

    def test_client(self):
        page = self.get("/client/1/modifier")
        empreinte = self.empreinte(page, "/client/1/modifier")
        base = {"client_nom": "Gagnon", "client_prenom": "Marie", "adresse": "123 Rue des Érables", "client_secteur": "centre_ville",
                "province": "QC", "client_sms_ok": "1", "empreinte": empreinte}
        self.assertTrue(self.post("/client/1/modifier", {**base, "client_telephone": "450-555-0100"})[0].startswith("303"))
        statut, _, corps = self.post("/client/1/modifier", {**base, "client_telephone": "450-555-0199"})
        self.assertIn("modifiée par quelqu", corps)
        c = interface.ouvrir_base(self.db)[0]
        self.assertEqual(c.execute("SELECT telephone FROM clients WHERE id = 1").fetchone()[0], "+14505550100")
        c.close()

    def test_sans_empreinte_comportement_inchange(self):                                    # anciens formulaires / autres outils
        self.assertTrue(self.post("/chantier/3", self.formulaire(3, description="Sans empreinte"))[0].startswith("303"))


class TestTelephone(unittest.TestCase):
    def test_feuille_de_style_pour_petits_ecrans(self):
        import vue
        self.assertIn('name="viewport" content="width=device-width,initial-scale=1"', vue.gabarit("t", "x"))
        from telephone import CSS_TELEPHONE as mobile
        self.assertTrue(mobile.lstrip().startswith("@media (max-width:700px)"))               # rien de tout cela sur ordinateur
        for attendu in ("min-height:44px", "font-size:16px", "table:not(.stat) tr{display:block", ".barre-mobile", "env(safe-area-inset-bottom)",
                        ".filtres-det", "table.archive", "table.clients", ".actions-sou", ".types", ".barre-ajout", ".modale{align-items:flex-end;padding:0;z-index:1100}",
                        "a.nj-prec", ".photos-grille", ".photo-prendre", "table.paiements", ".modifier-puce", ".filtres-bascule", "table.historique", ".carte.suppression"):
            self.assertIn(attendu, mobile)
        self.assertIn(".cal-jour.aujourdhui .cal-n{font-weight:800}", mobile)         # aujourd'hui : en gras, sans cercle tant qu'il n'est pas choisi
        self.assertNotIn("background:var(--vert)!important", mobile)
        self.assertNotIn("--teinte", mobile)                                           # boutons secondaires : blancs, comme sur le site
        self.assertIn("button.secondaire,.bouton.secondaire{background:#fff;border:1px solid var(--trait)", mobile)
        self.assertIn(mobile, vue.gabarit("t", "x"))


if __name__ == "__main__":
    unittest.main()
