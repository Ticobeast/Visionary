"""Tests des photos d'une fiche (outils/photos.py) : téléversement, vignettes, affichage, suppression, sécurité, droits, PDF de la journée.

    python3 -m unittest discover -s tests -v
"""
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import interface  # noqa: E402
import pdf  # noqa: E402
import photos  # noqa: E402
from test_auth import BaseAuth  # noqa: E402
from test_pages_soumissions import BasePages  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


class BasePhotos(BasePages):
    def televerser(self, i, octets, chemin=None, cookie=None):
        requete = None if cookie is None else {"cookie": cookie, "ip": "100.64.1.2", "agent": "x", "https": False}
        statut, en_tetes, corps = interface.repondre(self.db, "POST", chemin or f"/soumission/{i}/photos", {}, {"_octets": octets}, requete)
        return statut, dict(en_tetes), corps.decode("utf-8", "replace")

    def dossier(self, i, relatif=None):
        return self.db.parent / (relatif or f"photos/chantier-{i}")

    def ajouter(self, i, octets=JPEG):
        statut, _, corps = self.televerser(i, octets)
        self.assertTrue(statut.startswith("200"), (statut, corps))
        return json.loads(corps)["nom"]


class TestTeleversement(BasePhotos):
    def test_un_jpeg_et_un_png_sont_ranges_dans_le_dossier_de_la_fiche(self):
        i = self.complete()
        n1, n2 = self.ajouter(i, JPEG), self.ajouter(i, PNG)
        self.assertTrue(n1.endswith(".jpg") and n2.endswith(".png") and n1 != n2)
        self.assertEqual(sorted(p.name for p in self.dossier(i).iterdir()), sorted([n1, n2]))
        self.assertEqual((self.dossier(i) / n1).read_bytes(), JPEG)

    def test_rien_n_est_ecrit_dans_la_base(self):
        i = self.complete()
        avant = self.sql("SELECT dossier_photos FROM chantiers WHERE id = ?", (i,))
        self.ajouter(i)
        self.assertEqual(self.sql("SELECT dossier_photos FROM chantiers WHERE id = ?", (i,)), avant)

    def test_le_dossier_inscrit_dans_la_fiche_est_utilise(self):
        i = self.complete()
        import sqlite3
        c = sqlite3.connect(self.db)
        c.execute("UPDATE chantiers SET dossier_photos = 'photos/perso' WHERE id = ?", (i,))
        c.commit()
        c.close()
        nom = self.ajouter(i)
        self.assertTrue((self.dossier(i, "photos/perso") / nom).is_file())
        self.assertFalse(self.dossier(i).exists())

    def test_ce_qui_n_est_pas_une_image_est_refuse(self):
        i = self.complete()
        for octets, attendu in ((b"", "400"), (b"<html><script>alert(1)</script></html>", "415"), (b"GIF89a" + b"\x00" * 50, "415"),
                                (b"%PDF-1.4 " + b"\x00" * 50, "415")):
            self.assertTrue(self.televerser(i, octets)[0].startswith(attendu), octets[:10])
        self.assertFalse(self.dossier(i).exists())

    def test_trop_lourde_ou_trop_nombreuses(self):
        i = self.complete()
        ancienne, ancien_max = photos.LIMITE_OCTETS, photos.MAX_PHOTOS
        self.addCleanup(lambda: (setattr(photos, "LIMITE_OCTETS", ancienne), setattr(photos, "MAX_PHOTOS", ancien_max)))
        photos.LIMITE_OCTETS = 100
        self.assertTrue(self.televerser(i, JPEG)[0].startswith("413"))
        photos.LIMITE_OCTETS = ancienne
        photos.MAX_PHOTOS = 2
        self.ajouter(i)
        self.ajouter(i)
        self.assertTrue(self.televerser(i, JPEG)[0].startswith("409"))

    def test_fiche_inconnue(self):
        self.assertTrue(self.televerser(9999, JPEG)[0].startswith("404"))

    def test_le_nom_vient_du_serveur_et_chantier_ou_soumission_c_est_la_meme_fiche(self):
        i = self.complete()
        statut, _, corps = self.televerser(i, JPEG, chemin=f"/chantier/{i}/photos")
        self.assertTrue(statut.startswith("200"))
        self.assertRegex(json.loads(corps)["nom"], r"^\d{8}-\d{6}-[0-9a-f]{4}\.jpg$")


class TestVignetteAffichageSuppression(BasePhotos):
    def test_vignette_affichage_et_suppression(self):
        i = self.complete()
        nom = self.ajouter(i)
        petite = b"\xff\xd8\xff" + b"\x01" * 50
        self.assertTrue(self.televerser(i, petite, chemin=f"/soumission/{i}/photos/{nom}/vignette")[0].startswith("200"))
        statut, en_tetes, _ = self.req("GET", f"/soumission/{i}/photos/{nom}")
        self.assertEqual((statut[:3], en_tetes["Content-Type"]), ("200", "image/jpeg"))
        self.assertIn("max-age", en_tetes["Cache-Control"])
        self.assertEqual(interface.repondre(self.db, "GET", f"/soumission/{i}/photos/{nom}", {}, {}, None)[2], JPEG)
        self.assertEqual(interface.repondre(self.db, "GET", f"/soumission/{i}/photos/{nom}", {"v": "1"}, {}, None)[2], petite)
        page = self.get(f"/soumission/{i}")
        self.assertIn('id="photos"', page)
        self.assertIn(f'href="/soumission/{i}/photos/{nom}"', page)
        self.assertIn("Photos (1)", page)
        statut, en_tetes, _ = self.post(f"/soumission/{i}/photos/{nom}/supprimer")
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", f"/soumission/{i}?ok=photo_supprimee#photos"))
        self.assertFalse((self.dossier(i) / nom).exists())
        self.assertFalse((self.dossier(i) / photos.VIGNETTES / (nom + ".jpg")).exists())
        self.assertIn("Photo supprimée.", self.get(f"/soumission/{i}?ok=photo_supprimee"))
        self.assertIn("Aucune photo", self.get(f"/soumission/{i}"))

    def test_la_vignette_doit_etre_un_petit_jpeg_d_une_photo_qui_existe(self):
        i = self.complete()
        nom = self.ajouter(i)
        self.assertTrue(self.televerser(i, PNG, chemin=f"/soumission/{i}/photos/{nom}/vignette")[0].startswith("400"))
        self.assertTrue(self.televerser(i, JPEG + b"\x00" * photos.LIMITE_VIGNETTE, chemin=f"/soumission/{i}/photos/{nom}/vignette")[0].startswith("400"))
        self.assertTrue(self.televerser(i, JPEG, chemin=f"/soumission/{i}/photos/inconnue.jpg/vignette")[0].startswith("404"))

    def test_sans_vignette_la_photo_elle_meme_est_servie(self):
        i = self.complete()
        nom = self.ajouter(i)
        self.assertEqual(interface.repondre(self.db, "GET", f"/soumission/{i}/photos/{nom}", {"v": "1"}, {}, None)[2], JPEG)

    def test_les_fiches_chantier_et_soumission_montrent_la_carte(self):
        i = self.complete()
        self.assertIn('class="carte photos"', self.get(f"/soumission/{i}"))
        self.post(f"/soumission/{i}/accepter", {"retour": "/soumissions"})
        self.assertIn('class="carte photos"', self.get(f"/chantier/{i}"))
        self.assertIn('class="carte photos"', self.get("/chantier/1"))                      # y compris un chantier terminé

    def test_le_nom_est_verifie_aucune_sortie_du_dossier(self):
        i = self.complete()
        self.ajouter(i)
        (self.db.parent / "secret.jpg").write_bytes(JPEG)
        for nom in ("..", "...jpg", ".cache.jpg", "a%2f..%2fsecret.jpg", "secret.txt", "x.jpg%00", "a b.jpg", "..%5csecret.jpg"):
            self.assertTrue(self.req("GET", f"/soumission/{i}/photos/{nom}")[0].startswith("404"), nom)
            self.assertTrue(self.post(f"/soumission/{i}/photos/{nom}/supprimer")[0].startswith("404"), nom)
        self.assertTrue((self.db.parent / "secret.jpg").exists())
        self.assertTrue(self.req("GET", "/soumission/9999/photos/a.jpg")[0].startswith("404"))

    def test_les_noms_sont_echappes_dans_la_page(self):
        i = self.complete()
        (self.dossier(i)).mkdir(parents=True)
        (self.dossier(i) / "a.jpg").write_bytes(JPEG)
        self.assertNotIn("<script", self.get(f"/soumission/{i}").split('id="photos"')[1].split("</div>")[0])


class TestPdfDeLaJournee(BasePhotos):
    def test_les_photos_du_dossier_par_defaut_sont_trouvees(self):
        i = self.complete()
        self.assertEqual(pdf.photos_du_chantier(self.db.parent, None, i), [])
        nom = self.ajouter(i)
        trouvees = pdf.photos_du_chantier(self.db.parent, None, i)
        self.assertEqual([p.name for p in trouvees], [nom])
        self.assertEqual(pdf.photos_du_chantier(self.db.parent, None), [])                 # sans numéro : comme avant


class TestServeurEtDroits(BaseAuth):
    """Par une vraie connexion HTTP : le corps de la requête est l'image ; le compte « soumission » peut ajouter des photos."""

    def serveur(self):
        serveur = interface.creer_serveur(self.db, 0, True)
        port = serveur.server_address[1]
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (serveur.shutdown(), serveur.server_close()))
        return port

    def appel(self, port, methode, chemin, corps=None, type_=None, cookie=None, origine=True, longueur=None):
        hote = f"ticotower.tailbb6d3b.ts.net:{port}"
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        en_tetes = {"Host": hote}
        if origine:
            en_tetes["Origin"] = f"http://{hote}"
        if cookie:
            en_tetes["Cookie"] = cookie
        if type_:
            en_tetes["Content-Type"] = type_
        if longueur is not None:
            en_tetes["Content-Length"] = str(longueur)
        c.request(methode, chemin, body=corps, headers=en_tetes)
        r = c.getresponse()
        donnees = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return donnees

    def connecte(self, port, nom, mdp):
        statut, en_tetes, _ = self.appel(port, "POST", "/connexion", f"nom={nom}&mot_de_passe={mdp}".encode(), "application/x-www-form-urlencoded")
        return en_tetes["Set-Cookie"].split(";")[0]

    def test_televersement_par_le_compte_soumission(self):
        self.comptes()
        port = self.serveur()
        cookie = self.connecte(port, "Soumission", "motdepasse-soum")
        chantier = self.sql("SELECT id FROM chantiers LIMIT 1")[0][0]
        statut, en_tetes, corps = self.appel(port, "POST", f"/soumission/{chantier}/photos", JPEG, "image/jpeg", cookie)
        self.assertEqual(statut, 200)
        self.assertIn("application/json", en_tetes["Content-Type"])
        nom = json.loads(corps)["nom"]
        statut, en_tetes, octets = self.appel(port, "GET", f"/soumission/{chantier}/photos/{nom}", cookie=cookie)
        self.assertEqual((statut, octets, en_tetes["Cache-Control"].count("max-age")), (200, JPEG, 1))
        self.assertEqual(en_tetes["Cache-Control"], "private, max-age=3600")                 # pas de « no-store » en double

    def test_sans_connexion_depuis_un_autre_site_ou_trop_lourd(self):
        self.comptes()
        port = self.serveur()
        cookie = self.connecte(port, "Soumission", "motdepasse-soum")
        chantier = self.sql("SELECT id FROM chantiers LIMIT 1")[0][0]
        chemin = f"/soumission/{chantier}/photos"
        self.assertEqual(self.appel(port, "POST", chemin, JPEG, "image/jpeg")[0], 303)                       # pas connecté
        self.assertEqual(self.appel(port, "GET", f"{chemin}/a.jpg")[0], 303)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("POST", chemin, body=JPEG, headers={"Host": f"ticotower.tailbb6d3b.ts.net:{port}", "Origin": "http://evil.example.com",
                                                      "Content-Type": "image/jpeg", "Cookie": cookie})
        self.assertEqual(c.getresponse().status, 403)                                                          # un autre site ne peut pas écrire
        c.close()
        statut, _, corps = self.appel(port, "POST", chemin, b"", "image/jpeg", cookie, longueur=photos.LIMITE_OCTETS + 1)
        self.assertEqual(statut, 413)                                                                         # refusée sans être lue
        self.assertFalse((self.db.parent / "photos").exists())


if __name__ == "__main__":
    unittest.main()
