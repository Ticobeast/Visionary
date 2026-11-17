"""Tests des pages plus légères : la feuille de style servie à part (gardée en mémoire par le navigateur) et la compression."""
import gzip
import http.client
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import interface  # noqa: E402
import noyau  # noqa: E402
import vue  # noqa: E402
from test_auth import BaseAuth  # noqa: E402


class TestFeuilleDeStyle(BaseAuth):
    def test_la_page_appelle_la_feuille_sans_la_recopier(self):
        page = vue.gabarit("t", "<h1>Titre</h1>")
        self.assertIn(f'<link rel="stylesheet" href="{vue.URL_STYLE}">', page)
        self.assertNotIn(":root{--vert-fonce", page)                         # le style n'est plus dans la page
        self.assertLess(len(page.encode("utf-8")), 12_000)                   # avant : plus de 60 000 octets à chaque page
        self.assertRegex(vue.URL_STYLE, r"^/style-[0-9a-f]{12}\.css$")

    def test_la_feuille_est_gardee_en_memoire(self):
        statut, en_tetes, corps = interface.repondre(self.db, "GET", vue.URL_STYLE)
        en_tetes = dict(en_tetes)
        self.assertTrue(statut.startswith("200"))
        self.assertEqual(en_tetes["Content-Type"], "text/css; charset=utf-8")
        self.assertEqual(en_tetes["Cache-Control"], "private, max-age=31536000, immutable")
        texte = corps.decode("utf-8")
        self.assertIn(":root{--vert-fonce", texte)                           # le style de l'ordinateur...
        self.assertIn("@media (max-width:700px){", texte)                    # ... et celui du téléphone

    def test_l_adresse_change_avec_le_style(self):
        """L'empreinte vient du contenu : un style modifié a une autre adresse, donc le navigateur prend la nouvelle feuille."""
        import hashlib
        self.assertEqual(vue.VERSION_STYLE, hashlib.sha256(vue.FEUILLE_DE_STYLE).hexdigest()[:12])

    def test_accessible_avant_la_connexion_et_au_role_soumission(self):
        """La page de connexion a besoin du style : la feuille se lit sans compte (elle ne contient aucune donnée)."""
        self.comptes()
        self.assertTrue(self.req("GET", vue.URL_STYLE)[0].startswith("200"))                         # pas connecté
        soum = self.ouvrir("Soumission", "motdepasse-soum")
        self.assertTrue(self.req("GET", vue.URL_STYLE, cookie=soum)[0].startswith("200"))
        self.assertFalse(self.req("GET", "/style-zzzzzzzzzzzz.css")[0].startswith("200"))             # autre adresse : rien n'est servi


class TestCompression(unittest.TestCase):
    """Sur le vrai serveur : pages et feuille de style compressées quand le navigateur l'accepte."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "data" / "t.db"
        noyau.ouvrir_base(db)[0].close()
        gestionnaire = type("G", (interface.Gestionnaire,), {"db_path": db, "hotes_autorises": ()})
        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), gestionnaire)
        gestionnaire.port = self.serveur.server_address[1]
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        self._tmp.cleanup()

    def get(self, chemin, en_tetes=None):
        port = self.serveur.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", chemin, headers={"Host": f"127.0.0.1:{port}", **(en_tetes or {})})
        r = c.getresponse()
        corps = r.read()
        c.close()
        return r, corps

    def test_feuille_compressee(self):
        r, corps = self.get(vue.URL_STYLE, {"Accept-Encoding": "gzip, deflate"})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("Content-Encoding"), "gzip")
        self.assertEqual(r.getheader("Vary"), "Accept-Encoding")
        self.assertEqual(gzip.decompress(corps), vue.FEUILLE_DE_STYLE)
        self.assertLess(len(corps), len(vue.FEUILLE_DE_STYLE) / 3)            # au moins trois fois plus légère
        self.assertEqual(r.getheader("Cache-Control"), "private, max-age=31536000, immutable")

    def test_page_compressee_et_jamais_gardee(self):
        r, corps = self.get("/chantiers", {"Accept-Encoding": "gzip"})
        self.assertEqual(r.getheader("Content-Encoding"), "gzip")
        self.assertEqual(r.getheader("Cache-Control"), "no-store")            # une page (données) n'est jamais gardée en mémoire
        self.assertIn("<h1>Chantiers", gzip.decompress(corps).decode("utf-8"))

    def test_sans_gzip_rien_ne_change(self):
        r, corps = self.get("/chantiers")
        self.assertIsNone(r.getheader("Content-Encoding"))
        self.assertIn("<h1>Chantiers", corps.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
