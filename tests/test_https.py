"""Tests de l'accès en HTTPS par « tailscale serve » : la requête arrive de 127.0.0.1 mais vient d'un téléphone.

Le point de sécurité : une requête relayée n'est JAMAIS prise pour « cet ordinateur » (qui, sans compte, n'a pas à se connecter).
"""
import http.client
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import interface  # noqa: E402
import reseau  # noqa: E402
from test_auth import BaseAuth, TELEPHONE  # noqa: E402

NOM = "ticotower.tailbb6d3b.ts.net"
PORT = 8765


class TestReconnaitreLeRelais(unittest.TestCase):
    def relais(self, en_tetes, adresse="127.0.0.1"):
        return reseau.relais_tailscale(en_tetes, adresse, PORT)

    def test_acces_direct(self):
        self.assertIsNone(self.relais({"Host": f"127.0.0.1:{PORT}"}))                       # l'ordinateur lui-même
        self.assertIsNone(self.relais({"Host": f"localhost:{PORT}"}))
        self.assertIsNone(self.relais({"Host": f"{NOM}:{PORT}"}))                           # adresse http habituelle des téléphones
        self.assertIsNone(self.relais({"Host": f"100.101.102.103:{PORT}"}))

    def test_relais_https(self):
        r = self.relais({"Host": NOM, "X-Forwarded-For": "100.101.102.103", "X-Forwarded-Proto": "https", "Tailscale-User-Login": "x@example.com"})
        self.assertEqual(r, {"ip": "100.101.102.103", "https": True, "hote": NOM})
        self.assertEqual(self.relais({"Host": NOM + ":443"})["hote"], NOM)                   # même sans autre en-tête : un nom sans le port du programme
        r = self.relais({"Host": f"127.0.0.1:{PORT}", "X-Forwarded-Host": NOM, "X-Forwarded-For": "100.70.1.1"})
        self.assertEqual((r["ip"], r["hote"], r["https"]), ("100.70.1.1", NOM, False))      # relais qui réécrit l'hôte

    def test_adresse_de_l_appareil(self):
        self.assertEqual(self.relais({"Host": NOM, "X-Forwarded-For": "8.8.8.8, 100.70.1.1"})["ip"], "100.70.1.1")     # le dernier, ajouté par le relais
        self.assertEqual(self.relais({"Host": NOM, "X-Forwarded-For": "fd7a:115c:a1e0::1234"})["ip"], "fd7a:115c:a1e0::1234")
        for illisible in ("", "8.8.8.8", "127.0.0.1", "n'importe quoi", "::1"):
            ip = self.relais({"Host": NOM, "X-Forwarded-For": illisible})["ip"]
            self.assertEqual(ip, reseau.ADRESSE_RELAIS_INCONNUE, illisible)                 # jamais 127.0.0.1
            self.assertFalse(__import__("auth")._est_local(ip))

    def test_relais_suspect_refuse(self):
        self.assertIs(self.relais({"Host": "exemple.com", "X-Forwarded-For": "100.70.1.1"}), False)
        self.assertIs(self.relais({"Host": f"127.0.0.1:{PORT}", "X-Forwarded-Host": "exemple.com"}), False)
        self.assertIs(self.relais({"Host": f"{NOM}:{PORT}", "X-Forwarded-For": "100.70.1.1"}), False)
        self.assertIs(self.relais({"Host": "ts.net", "X-Forwarded-Proto": "https"}), False)

    def test_en_tetes_ignores_s_ils_ne_viennent_pas_de_cet_ordinateur(self):
        """Un appareil du réseau ne peut pas se faire passer pour le relais : ses en-têtes ne comptent pas."""
        self.assertIsNone(self.relais({"Host": NOM, "X-Forwarded-For": "127.0.0.1", "X-Forwarded-Proto": "https"}, adresse="100.64.1.2"))

    def test_origine(self):
        r = {"ip": "100.70.1.1", "https": True, "hote": NOM}
        self.assertTrue(reseau.origine_relais_ok(NOM, r))
        self.assertTrue(reseau.origine_relais_ok(NOM + ":443", r))
        self.assertFalse(reseau.origine_relais_ok("autre.tailbb6d3b.ts.net", r))
        self.assertFalse(reseau.origine_relais_ok("exemple.com", r))
        self.assertTrue(reseau.origine_relais_ok("autre.tailbb6d3b.ts.net", {**r, "hote": None}))    # nom non transmis : un nom *.ts.net suffit
        self.assertFalse(reseau.origine_relais_ok("exemple.com", {**r, "hote": None}))


class TestServeurDerriereLeRelais(BaseAuth):
    def serveur(self, reseau_actif=True):
        s = interface.creer_serveur(self.db, 0, reseau_actif)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (s.shutdown(), s.server_close()))
        return s.server_address[1]

    def appel(self, port, methode, chemin, corps=None, cookie=None, en_tetes=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        h = {"Host": NOM, "X-Forwarded-For": "100.101.102.103", "X-Forwarded-Proto": "https", "User-Agent": TELEPHONE}
        if cookie:
            h["Cookie"] = cookie
        if corps is not None:
            h.update({"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://" + NOM})
        h.update(en_tetes or {})
        c.request(methode, chemin, body=corps, headers=h)
        r = c.getresponse()
        donnees = (r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace"))
        c.close()
        return donnees

    def test_sans_compte_le_relais_reste_ferme(self):
        """Sans aucun compte, l'ordinateur entre sans se connecter ; un téléphone relayé (qui arrive pourtant de 127.0.0.1) non."""
        port = self.serveur()
        statut, _, page = self.appel(port, "GET", "/chantiers")
        self.assertEqual(statut, 403)
        self.assertIn("Aucun compte", page)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)                       # l'ordinateur lui-même : toujours ouvert
        c.request("GET", "/chantiers", headers={"Host": f"127.0.0.1:{port}"})
        self.assertEqual(c.getresponse().status, 200)
        c.close()

    def test_connexion_par_https(self):
        self.comptes()
        port = self.serveur()
        statut, en_tetes, _ = self.appel(port, "GET", "/chantiers")
        self.assertEqual((statut, en_tetes["Location"]), (303, "/connexion?suite=%2Fchantiers"))
        statut, en_tetes, _ = self.appel(port, "POST", "/connexion", "nom=Soumission&mot_de_passe=motdepasse-soum&suite=%2Fchantiers")
        self.assertEqual((statut, en_tetes["Location"]), (303, "/chantiers"))
        self.assertIn("Secure", en_tetes["Set-Cookie"])                                     # en HTTPS, le témoin de session ne voyage qu'en HTTPS
        cookie = en_tetes["Set-Cookie"].split(";")[0]
        statut, _, page = self.appel(port, "GET", "/chantiers", cookie=cookie)
        self.assertEqual(statut, 200)
        self.assertIn("<h1>Chantiers", page)

    def test_origine_etrangere_refusee(self):
        self.comptes()
        port = self.serveur()
        statut, _, _ = self.appel(port, "POST", "/connexion", "nom=Soumission&mot_de_passe=motdepasse-soum", en_tetes={"Origin": "https://exemple.com"})
        self.assertEqual(statut, 403)

    def test_relais_refuse_hors_du_mode_reseau(self):
        """Programme lancé pour l'ordinateur seulement (pas d'accès à distance) : un relais n'ouvre rien."""
        self.comptes()
        port = self.serveur(reseau_actif=False)
        self.assertEqual(self.appel(port, "GET", "/chantiers")[0], 403)

    def test_blocage_par_appareil(self):
        """Les essais ratés sont comptés pour l'adresse du téléphone, pas pour 127.0.0.1 (sinon un appareil bloquerait tout le monde)."""
        import auth
        self.comptes()
        port = self.serveur()
        auth.reinitialiser_blocages()
        for k in range(auth.MAX_ECHECS_IP):                                                  # des noms différents : seul le compteur par appareil monte
            self.appel(port, "POST", "/connexion", f"nom=inconnu{k}&mot_de_passe=faux")
        _, _, page = self.appel(port, "POST", "/connexion", "nom=Admin&mot_de_passe=motdepasse-admin")
        self.assertIn("Trop d", page)                                                        # cet appareil est bloqué...
        statut, _, _ = self.appel(port, "POST", "/connexion", "nom=Admin&mot_de_passe=motdepasse-admin", en_tetes={"X-Forwarded-For": "100.99.1.1"})
        self.assertEqual(statut, 303)                                                        # ... pas les autres
        auth.reinitialiser_blocages()


class TestBoutonPartager(BaseAuth):
    def test_le_script_ne_change_rien_sans_https(self):
        """Le bouton Partager n'apparaît que si le navigateur offre le partage de fichiers (HTTPS) ; sinon l'icône télécharge, comme avant."""
        import vue
        script = vue.SCRIPT_PARTAGE
        self.assertIn("if(!navigator.share||!navigator.canShare||!window.isSecureContext)return;", script)
        self.assertIn("a.lien-dl", script)
        self.assertIn("navigator.share({files:[fichier]})", script)
        self.assertIn("location.href=a.href", script)                              # secours : le téléchargement
        page = interface.repondre(self.db, "GET", "/chantier/3")[2].decode("utf-8")
        self.assertIn(script, page)
        self.assertIn('class="bouton secondaire lien-dl" href="/soumission/3/pdf?telecharger=1" download', page)     # sans JavaScript : télécharger

    def test_le_pdf_porte_un_nom_lisible(self):
        """La feuille de partage montre le nom du fichier : il vient de l'en-tête de la réponse."""
        statut, en_tetes, corps = interface.repondre(self.db, "GET", "/soumission/3/pdf", {"telecharger": "1"})
        en_tetes = dict(en_tetes)
        self.assertEqual(en_tetes["Content-Type"], "application/pdf")
        self.assertRegex(en_tetes["Content-Disposition"], r'^attachment; filename="Soumission-0003-[^"]+\.pdf"$')
        self.assertTrue(corps.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
