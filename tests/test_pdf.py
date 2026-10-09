"""Tests du PDF de la journée (outils/pdf.py) et de son bouton sur le tableau de bord.

    python3 -m unittest discover -s tests -v
"""
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import fixtures  # noqa: E402
import interface  # noqa: E402
import pdf  # noqa: E402


def png_minimal(couleur=(200, 100, 50)):
    """PNG RVB 4 x 4, 8 bits, non entrelacé (fabriqué à la main : aucune bibliothèque requise)."""
    def bloc(genre, corps):
        return struct.pack(">I", len(corps)) + genre + corps + struct.pack(">I", zlib.crc32(genre + corps) & 0xFFFFFFFF)
    brut = b"".join(b"\x00" + bytes(couleur) * 4 for _ in range(4))
    return (b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(brut)) + bloc(b"IEND", b""))


def jpeg_minimal(largeur=40, hauteur=30, remplissage=0):
    """En-têtes JPEG valides (SOI, SOF0, EOI) : suffisent pour tester la lecture des dimensions et l'intégration."""
    sof = struct.pack(">BHHB", 8, hauteur, largeur, 3) + b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    return b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\x00" * remplissage + b"\xff\xd9"


def textes(corps):
    """Tout le texte écrit dans les pages du PDF (flux décompressés, chaînes entre parenthèses, Windows-1252)."""
    sortie = []
    for flux in re.findall(rb"stream\n(.*?)\nendstream", corps, re.S):
        try:
            contenu = zlib.decompress(flux)
        except zlib.error:
            continue
        for chaine in re.findall(rb"\((.*?)(?<!\\)\) Tj", contenu):
            sortie.append(chaine.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\").decode("cp1252"))
    return "\n".join(sortie)


class BasePdf(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)
        c = sqlite3.connect(self.db)
        self.jour, self.dossier = c.execute("SELECT date_prevue, dossier_photos FROM chantiers WHERE id = 3").fetchone()
        c.close()

    def tearDown(self):
        self._tmp.cleanup()

    def pdf(self, jour=None):
        return interface.repondre(self.db, "GET", "/journee.pdf", {"date": jour or self.jour})

    def sql(self, requete, args=()):
        c = sqlite3.connect(self.db)
        try:
            c.execute(requete, args)
            c.commit()
        finally:
            c.close()

    def photos(self):
        dossier = self.db.parent / self.dossier
        dossier.mkdir(parents=True, exist_ok=True)
        return dossier


class TestFichierPdf(BasePdf):
    def test_telechargement(self):
        statut, en_tetes, corps = self.pdf()
        en_tetes = dict(en_tetes)
        self.assertEqual(statut, "200 OK")
        self.assertEqual(en_tetes["Content-Type"], "application/pdf")
        self.assertIn(f'attachment; filename="journee-{self.jour}.pdf"', en_tetes["Content-Disposition"])
        self.assertTrue(corps.startswith(b"%PDF-1.4"))
        self.assertTrue(corps.rstrip().endswith(b"%%EOF"))

    def test_table_des_references_correcte(self):
        corps = self.pdf()[2]
        debut = int(re.search(rb"startxref\n(\d+)\n", corps).group(1))
        self.assertTrue(corps[debut:].startswith(b"xref\n"))
        nb = int(re.search(rb"xref\n0 (\d+)\n", corps[debut:]).group(1))
        entrees = re.findall(rb"(\d{10}) 00000 n \n", corps[debut:])
        self.assertEqual(len(entrees), nb - 1)
        for numero, position in enumerate(entrees, 1):
            self.assertTrue(corps[int(position):].startswith(b"%d 0 obj" % numero), numero)

    def test_contenu_de_toutes_les_donnees_du_chantier(self):
        texte = textes(self.pdf()[2])
        for attendu in ("Luc Boucher", "Syndicat Les Jardins du Lac", "450-555-0163", "850 Boulevard du Lac", "J7C 2X1",
                        "Entrée par le stationnement arrière", "Émondage", "12 arbres matures", "Prévenir le gardien",
                        "Nacelle requise", "Débarrasser le bois", "6 h", "2 200,00 $", "2 529,45 $", "Chèque",
                        "500,00 $", "2 029,45 $", "Planifié", "2026-09-25", self.dossier, "Journée de travail"):
            self.assertIn(attendu, texte)

    def test_adresse_avec_lien_google_maps(self):
        corps = self.pdf()[2]
        self.assertIn(b"/URI (https://www.google.com/maps/search/?api=1&query=850%20Boulevard%20du%20Lac%2C%20Blainville%2C%20QC%20J7C%202X1%2C%20Canada)", corps)
        self.assertIn(b"/Subtype /Link", corps)
        self.assertIn(b"/Annots [", corps)
        self.assertIn("Les adresses en bleu ouvrent Google Maps", textes(corps))

    def test_plus_de_fiche_papier(self):
        texte = textes(self.pdf()[2])
        self.assertNotIn("papier", texte.lower())
        self.assertNotIn("Scan de la fiche", texte)

    def test_date_invalide_ou_jour_vide(self):
        self.assertIn("Aucun chantier planifié", textes(self.pdf("2030-01-01")[2]))
        statut, en_tetes, corps = interface.repondre(self.db, "GET", "/journee.pdf", {"date": "n'importe quoi"})
        self.assertEqual(statut, "200 OK")                                     # retombe sur aujourd'hui
        self.assertTrue(corps.startswith(b"%PDF"))

    def test_ne_modifie_rien(self):
        avant = sqlite3.connect(self.db).execute("SELECT count(*), sum(prix_ht) FROM chantiers").fetchone()
        self.pdf()
        self.assertEqual(sqlite3.connect(self.db).execute("SELECT count(*), sum(prix_ht) FROM chantiers").fetchone(), avant)

    def test_texte_long_sur_plusieurs_pages(self):
        self.sql("UPDATE chantiers SET description = ? WHERE id = 3", (" ".join(["Branche difficile à atteindre."] * 400),))
        corps = self.pdf()[2]
        pages = len(re.findall(rb"/Type /Page /", corps))
        self.assertGreater(pages, 1)
        self.assertIn(f"Page 1 / {pages}", textes(corps))
        self.assertIn(f"Page {pages} / {pages}", textes(corps))

    def test_caracteres_speciaux(self):
        self.sql("UPDATE chantiers SET description = ? WHERE id = 3", ("Chêne (rouge) \\ côté 100 % « à l'ouest » 😀",))
        texte = textes(self.pdf()[2])
        self.assertIn("Chêne (rouge) \\ côté 100 % « à l'ouest »", texte)
        self.assertNotIn("😀", texte)                                          # ni emoji, ni plantage

    @unittest.skipUnless(shutil.which("pdftotext"), "pdftotext absent")
    def test_lisible_par_un_vrai_lecteur(self):
        chemin = Path(self._tmp.name) / "j.pdf"
        chemin.write_bytes(self.pdf()[2])
        sortie = subprocess.run(["pdftotext", "-layout", str(chemin), "-"], capture_output=True, text=True, check=True).stdout
        self.assertIn("Luc Boucher", sortie)
        self.assertIn("2 529,45 $", sortie)


class TestMiseEnPage(unittest.TestCase):
    def test_les_lignes_tiennent_dans_la_largeur(self):
        texte = "Très long texte avec des mots " * 30 + "x" * 200
        for gras in (False, True):
            for ligne in pdf.decouper(texte, 10, gras, 200):
                self.assertLessEqual(pdf.largeur(ligne, 10, gras), 200 + 0.01)
        self.assertEqual(pdf.decouper("a\nb", 10, False, 200), ["a", "b"])

    def test_largeur_helvetica_connue(self):
        self.assertAlmostEqual(pdf.largeur("Hello", 10), (722 + 556 + 222 + 222 + 556) / 100.0)
        self.assertAlmostEqual(pdf.largeur("é", 10), pdf.largeur("e", 10))      # accent : même largeur que la lettre


class TestBoutons(BasePdf):
    def get(self, chemin, query):
        return interface.repondre(self.db, "GET", chemin, query)[2].decode("utf-8")

    def test_bouton_pdf_en_bas_du_tableau_de_bord(self):
        page = self.get("/", {"date": self.jour})
        self.assertIn(f'href="/journee.pdf?date={self.jour}"', page)
        self.assertIn("Télécharger la journée<span class=\"pc-seul\"> (PDF)</span>", page)
        self.assertGreater(page.index("Télécharger la journée<"), page.index("</table>"))        # sous la table
        self.assertNotIn("/journee.pdf", self.get("/journee", {"date": self.jour}))

    def test_pas_de_bouton_si_la_journee_est_vide(self):
        self.assertNotIn("/journee.pdf", self.get("/", {"date": "2030-01-01"}))

    def test_terminer_et_retirer_cote_a_cote_dans_la_journee(self):
        page = self.get("/journee", {"date": self.jour})
        m = re.search(r'<div class="actions-ligne">(.*?)</div></td>', page, re.S)
        self.assertIsNotNone(m)
        self.assertIn(">Terminer</a>", m.group(1))
        self.assertIn(">Retirer</button>", m.group(1))
        self.assertIn(".actions-ligne{display:flex", page)                     # rangée horizontale


class TestPhotos(BasePdf):
    def ecrire(self, nom, octets):
        (self.photos() / nom).write_bytes(octets)

    def test_png_et_jpeg_sans_pillow(self):
        self.ecrire("a.png", png_minimal())
        self.ecrire("b.jpg", jpeg_minimal(40, 30))
        self.ecrire("notes.txt", b"x")                                          # ignoré
        ancien, pdf.Image = pdf.Image, None
        try:
            corps = self.pdf()[2]
        finally:
            pdf.Image = ancien
        self.assertEqual(len(re.findall(rb"/Subtype /Image", corps)), 2)
        self.assertIn(b"/Filter /DCTDecode", corps)
        self.assertIn(b"/Predictor 15", corps)
        self.assertIn("Photos (2)", textes(corps))
        self.assertIn("a.png", textes(corps))
        self.assertNotIn("notes.txt", textes(corps))

    def test_photo_trop_lourde_sans_pillow_est_listee_pas_integree(self):
        self.ecrire("grosse.jpg", jpeg_minimal(remplissage=pdf.LIMITE_SANS_PILLOW + 10))
        ancien, pdf.Image = pdf.Image, None
        try:
            corps = self.pdf()[2]
        finally:
            pdf.Image = ancien
        self.assertEqual(len(re.findall(rb"/Subtype /Image", corps)), 0)
        self.assertIn("grosse.jpg", textes(corps))
        self.assertIn("Non incluses", textes(corps))

    def test_fichier_image_corrompu_ne_plante_pas(self):
        self.ecrire("cassee.jpg", b"pas une image")
        corps = self.pdf()[2]
        self.assertTrue(corps.startswith(b"%PDF"))
        self.assertIn("cassee.jpg", textes(corps))

    def test_orientation_exif_lue(self):
        donnees = bytearray(jpeg_minimal())
        exif = b"Exif\x00\x00" + b"MM\x00\x2a\x00\x00\x00\x08" + b"\x00\x01" + struct.pack(">HHI", 0x0112, 3, 1) + struct.pack(">HH", 6, 0) + b"\x00\x00\x00\x00"
        app1 = b"\xff\xe1" + struct.pack(">H", len(exif) + 2) + exif
        donnees = bytes(donnees[:2]) + app1 + bytes(donnees[2:])
        self.assertEqual(pdf._orientation_exif(donnees), 6)
        self.assertEqual(pdf._jpeg(donnees)[:2], (40, 30))
        self.assertEqual(pdf._orientation_exif(jpeg_minimal()), 1)

    def test_le_dossier_ne_peut_pas_sortir_de_la_base(self):
        base = self.db.parent
        (base.parent / "secret").mkdir()
        (base.parent / "secret" / "x.png").write_bytes(png_minimal())
        self.assertEqual(pdf.photos_du_chantier(base, "../secret"), [])
        self.assertEqual(pdf.photos_du_chantier(base, "inexistant"), [])
        self.assertEqual(pdf.photos_du_chantier(base, None), [])

    def test_limite_du_nombre_de_photos(self):
        for i in range(pdf.MAX_PHOTOS + 3):
            self.ecrire(f"p{i:02d}.png", png_minimal())
        texte = textes(self.pdf()[2])
        self.assertIn(f"Photos ({pdf.MAX_PHOTOS + 3})", texte)
        self.assertIn("3 autre(s) photo(s)", texte)

    @unittest.skipIf(pdf.Image is None, "Pillow absent")
    def test_avec_pillow_les_grandes_photos_sont_reduites(self):
        from PIL import Image
        Image.new("RGB", (4000, 3000), (10, 120, 30)).save(self.photos() / "grande.jpg", quality=95)
        corps = self.pdf()[2]
        self.assertEqual(len(re.findall(rb"/Subtype /Image", corps)), 1)
        self.assertLess(len(corps), 120_000)
        m = re.search(rb"/Width (\d+) /Height (\d+)", corps)
        self.assertLessEqual(max(int(m.group(1)), int(m.group(2))), pdf.COTE_VIGNETTE_PX)


if __name__ == "__main__":
    unittest.main()
