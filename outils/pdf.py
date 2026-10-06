"""PDF de la journée : une feuille de route complète, avec tous les détails de chaque chantier (et les photos).

Aucune dépendance : le PDF est écrit à la main (polices standard Helvetica, présentes dans tout lecteur PDF).
Photos : les JPEG et PNG du dossier de photos du chantier sont intégrés en vignettes. Avec Pillow (facultatif,
`pip install pillow`) elles sont réduites et redressées : le PDF reste léger quelle que soit la taille des photos.
Sans Pillow, une photo JPEG/PNG est intégrée telle quelle si elle pèse moins de LIMITE_SANS_PILLOW octets ; sinon
elle est simplement listée par son nom (rien ne plante).
"""
import datetime
import io
import re
import struct
import unicodedata
import zlib
from pathlib import Path
from urllib.parse import quote

from noyau import (DEBUT_JOURNEE, DINER_DEBUT, DINER_FIN, LIBELLES_BOIS, LIBELLES_MODE, LIBELLES_STATUT, calculer_horaire,
                   heure_texte, ids_de_la_journee)
from vue import argent, heures

try:  # facultatif
    from PIL import Image, ImageOps
except Exception:  # noqa: BLE001 : absent ou inutilisable -> on s'en passe
    Image = ImageOps = None

LARGEUR, HAUTEUR = 595.28, 841.89          # A4, en points (1 pt = 1/72 po)
MARGE = 42.0
HAUT_ENTETE = 34.0
BAS_PIED = 34.0
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

EXTENSIONS_PHOTO = (".jpg", ".jpeg", ".png")
MAX_PHOTOS = 12                            # par chantier (les autres sont comptées, pas intégrées)
LIMITE_SANS_PILLOW = 1_500_000             # octets : au-delà, sans Pillow, la photo est seulement listée
COTE_VIGNETTE_PX = 640                     # côté maximal des vignettes (avec Pillow)

# Largeurs Helvetica (milliemes d'em) des caractères 32 à 126.
_CARS = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
_L_NORMAL = ([278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10
             + [278, 278, 584, 584, 584, 556, 1015]
             + [667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611]
             + [278, 278, 278, 469, 556, 333]
             + [556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500]
             + [334, 260, 334, 584])
_L_GRAS = ([278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10
           + [333, 333, 584, 584, 584, 611, 975]
           + [722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611]
           + [333, 278, 333, 584, 556, 333]
           + [556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500]
           + [389, 280, 389, 584])
_TABLES = {False: dict(zip(_CARS, _L_NORMAL)), True: dict(zip(_CARS, _L_GRAS))}
assert len(_CARS) == len(_L_NORMAL) == len(_L_GRAS) == 95

_GRIS, _VERT, _NOIR, _LIEN = 0.40, (0.18, 0.42, 0.25), 0.0, (0.07, 0.30, 0.65)


def _nettoyer(texte):
    """Texte sûr pour la police standard : espaces spéciales, retours à la ligne et caractères hors Windows-1252."""
    texte = "" if texte is None else str(texte)
    texte = texte.replace(" ", " ").replace(" ", " ").replace("\t", " ")
    return texte.encode("cp1252", "replace").decode("cp1252")


def largeur(texte, taille, gras=False):
    table = _TABLES[gras]
    total = 0
    for c in texte:
        if c in table:
            total += table[c]
        else:
            base = unicodedata.normalize("NFD", c)[0]
            total += table.get(base, 1000 if c in "—…" else 556)
    return total * taille / 1000.0


def decouper(texte, taille, gras, largeur_max):
    """Coupe un texte en lignes qui tiennent dans la largeur donnée (respecte les retours à la ligne)."""
    lignes = []
    for paragraphe in _nettoyer(texte).replace("\r", "").split("\n"):
        courante = ""
        for mot in paragraphe.split(" "):
            essai = mot if not courante else courante + " " + mot
            if largeur(essai, taille, gras) <= largeur_max:
                courante = essai
                continue
            if courante:
                lignes.append(courante)
            while largeur(mot, taille, gras) > largeur_max and len(mot) > 1:   # mot plus large que la ligne : on le casse
                n = len(mot)
                while n > 1 and largeur(mot[:n], taille, gras) > largeur_max:
                    n -= 1
                lignes.append(mot[:n])
                mot = mot[n:]
            courante = mot
        lignes.append(courante)
    return lignes


def _litteral(texte):
    """Chaîne PDF entre parenthèses, en Windows-1252."""
    octets = _nettoyer(texte).encode("cp1252", "replace")
    return b"(" + octets.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _nombre(x):
    return ("%.2f" % x).rstrip("0").rstrip(".") or "0"


# ---------------------------------------------------------------------------
# Images : JPEG et PNG, directement ou via Pillow
# ---------------------------------------------------------------------------
def _orientation_exif(donnees):
    """Orientation EXIF d'un JPEG (1 à 8), 1 si absente."""
    try:
        i = 2
        while i + 4 <= len(donnees) and donnees[i] == 0xFF:
            marqueur, longueur = donnees[i + 1], struct.unpack(">H", donnees[i + 2:i + 4])[0]
            if marqueur == 0xE1 and donnees[i + 4:i + 10] == b"Exif\x00\x00":
                tiff = donnees[i + 10:i + 2 + longueur]
                ordre = "<" if tiff[:2] == b"II" else ">"
                debut = struct.unpack(ordre + "I", tiff[4:8])[0]
                n = struct.unpack(ordre + "H", tiff[debut:debut + 2])[0]
                for k in range(n):
                    entree = tiff[debut + 2 + 12 * k:debut + 14 + 12 * k]
                    if struct.unpack(ordre + "H", entree[:2])[0] == 0x0112:
                        return struct.unpack(ordre + "H", entree[8:10])[0]
                return 1
            if marqueur == 0xDA:
                break
            i += 2 + longueur
    except (struct.error, IndexError):
        pass
    return 1


def _jpeg(donnees):
    """Dimensions d'un JPEG (SOF) : (largeur, hauteur, composantes) ou None."""
    if donnees[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(donnees):
        if donnees[i] != 0xFF:
            return None
        marqueur = donnees[i + 1]
        if marqueur in (0xD8, 0x01) or 0xD0 <= marqueur <= 0xD7 or marqueur == 0xFF:
            i += 1 if marqueur == 0xFF else 2
            continue
        longueur = struct.unpack(">H", donnees[i + 2:i + 4])[0]
        if marqueur in (0xC0, 0xC1, 0xC2):
            precision, hauteur, larg, composantes = struct.unpack(">BHHB", donnees[i + 4:i + 10])
            return (larg, hauteur, composantes) if precision == 8 else None
        i += 2 + longueur
    return None


def _png(donnees):
    """PNG 8 bits, gris ou RVB, non entrelacé : image PDF directe (Flate + prédicteur PNG), sinon None."""
    if donnees[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    i, ihdr, idat = 8, None, []
    while i + 8 <= len(donnees):
        longueur, genre = struct.unpack(">I4s", donnees[i:i + 8])
        corps = donnees[i + 8:i + 8 + longueur]
        if genre == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corps)
        elif genre == b"IDAT":
            idat.append(corps)
        elif genre == b"IEND":
            break
        i += 12 + longueur
    if not ihdr or not idat:
        return None
    larg, hauteur, profondeur, genre_couleur, _, _, entrelace = ihdr
    if profondeur != 8 or genre_couleur not in (0, 2) or entrelace:
        return None
    couleurs = 1 if genre_couleur == 0 else 3
    return {"largeur": larg, "hauteur": hauteur, "donnees": b"".join(idat), "filtre": "FlateDecode",
            "espace": "DeviceGray" if couleurs == 1 else "DeviceRGB",
            "parms": f"/DecodeParms << /Predictor 15 /Colors {couleurs} /BitsPerComponent 8 /Columns {larg} >>", "orientation": 1}


def charger_image(chemin):
    """Image prête pour le PDF ({largeur, hauteur, donnees, filtre, espace, parms, orientation}) ou (None, raison)."""
    try:
        taille = Path(chemin).stat().st_size
    except OSError:
        return None, "introuvable"
    if Image is not None:
        try:
            with Image.open(chemin) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((COTE_VIGNETTE_PX, COTE_VIGNETTE_PX))
                tampon = io.BytesIO()
                im.save(tampon, "JPEG", quality=78)
                return {"largeur": im.width, "hauteur": im.height, "donnees": tampon.getvalue(), "filtre": "DCTDecode",
                        "espace": "DeviceRGB", "parms": "", "orientation": 1}, None
        except Exception:  # noqa: BLE001 : fichier illisible : on essaie sans Pillow
            pass
    if taille > LIMITE_SANS_PILLOW:
        return None, "trop lourde (installer Pillow pour l'inclure)"
    try:
        donnees = Path(chemin).read_bytes()
    except OSError:
        return None, "illisible"
    jpeg = _jpeg(donnees)
    if jpeg and jpeg[2] in (1, 3):
        larg, hauteur, composantes = jpeg
        return {"largeur": larg, "hauteur": hauteur, "donnees": donnees, "filtre": "DCTDecode",
                "espace": "DeviceGray" if composantes == 1 else "DeviceRGB", "parms": "",
                "orientation": _orientation_exif(donnees)}, None
    png = _png(donnees)
    if png:
        return png, None
    return None, "format non pris en charge sans Pillow"


def _matrice(orientation, x, y, dw, dh):
    """Matrice (a b c d e f) qui place l'image dans le cadre d'affichage (x, y, dw, dh) selon son orientation EXIF."""
    if orientation == 3:
        return (-dw, 0, 0, -dh, x + dw, y + dh)
    if orientation == 2:
        return (-dw, 0, 0, dh, x + dw, y)
    if orientation == 4:
        return (dw, 0, 0, -dh, x, y + dh)
    if orientation == 6:
        return (0, -dh, dw, 0, x, y + dh)
    if orientation == 8:
        return (0, dh, -dw, 0, x + dw, y)
    return (dw, 0, 0, dh, x, y)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------
class Document:
    """Mise en page au fil de l'eau : on écrit de haut en bas, une nouvelle page s'ouvre quand il n'y a plus de place."""

    def __init__(self, titre_courant):
        self.titre_courant = titre_courant
        self.pages = []                 # chaque page : {"ops": [bytes], "images": [indices]}
        self.images = []
        self.y = 0.0
        self._ouvrir_page()

    # --- pages ----------------------------------------------------------
    def _ouvrir_page(self):
        self.pages.append({"ops": [], "images": [], "liens": []})
        self.y = HAUTEUR - MARGE - HAUT_ENTETE

    def _op(self, texte):
        self.pages[-1]["ops"].append(texte.encode("latin-1"))

    def besoin(self, hauteur):
        if self.y - hauteur < MARGE + BAS_PIED:
            self._ouvrir_page()

    # --- primitives -------------------------------------------------------
    def _texte(self, x, y, texte, taille, gras=False, couleur=_NOIR):
        rvb = couleur if isinstance(couleur, tuple) else (couleur,) * 3
        self.pages[-1]["ops"].append(
            ("%s %s %s rg BT /F%d %s Tf %s %s Td " % (_nombre(rvb[0]), _nombre(rvb[1]), _nombre(rvb[2]), 2 if gras else 1,
                                                    _nombre(taille), _nombre(x), _nombre(y))).encode("latin-1")
            + _litteral(texte) + b" Tj ET")

    def _trait(self, x1, y1, x2, y2, epaisseur=0.6, gris=0.75):
        self._op("%s G %s w %s %s m %s %s l S" % (_nombre(gris), _nombre(epaisseur), _nombre(x1), _nombre(y1), _nombre(x2), _nombre(y2)))

    def _rect(self, x, y, w, h, gris):
        self._op("%s g %s %s %s %s re f" % (_nombre(gris), _nombre(x), _nombre(y), _nombre(w), _nombre(h)))

    # --- éléments de mise en page -------------------------------------------
    def espace(self, h=6.0):
        self.y -= h

    def separateur(self):
        self.besoin(10)
        self.y -= 4
        self._trait(MARGE, self.y, LARGEUR - MARGE, self.y)
        self.y -= 8

    def titre(self, texte, taille=15, couleur=_NOIR):
        lignes = decouper(texte, taille, True, LARGEUR - 2 * MARGE)
        self.besoin(len(lignes) * (taille + 3) + 4)
        for ligne in lignes:
            self.y -= taille + 1
            self._texte(MARGE, self.y, ligne, taille, True, couleur)
            self.y -= 2

    def paragraphe(self, texte, taille=10, gras=False, retrait=0.0, couleur=_NOIR):
        interligne = taille * 1.3
        for ligne in decouper(texte, taille, gras, LARGEUR - 2 * MARGE - retrait):
            self.besoin(interligne)
            self.y -= interligne
            self._texte(MARGE + retrait, self.y, ligne, taille, gras, couleur)

    def champ(self, etiquette, valeur, taille=9.5, colonne=118.0, lien=None):
        """Ligne « Étiquette : valeur » (valeur sur plusieurs lignes au besoin). Rien si la valeur est vide.
        Avec `lien` (adresse web), la valeur est en bleu et cliquable."""
        if valeur is None or str(valeur).strip() == "":
            return
        lignes = decouper(valeur, taille, False, LARGEUR - 2 * MARGE - colonne)
        interligne = taille * 1.3
        self.besoin(interligne * min(len(lignes), 2))
        for i, ligne in enumerate(lignes):
            self.besoin(interligne)
            self.y -= interligne
            if i == 0:
                self._texte(MARGE, self.y, etiquette, taille, True, _GRIS)
            self._texte(MARGE + colonne, self.y, ligne, taille, False, _LIEN if lien else _NOIR)
            if lien:
                self.pages[-1]["liens"].append((MARGE + colonne, self.y - 2, MARGE + colonne + largeur(ligne, taille), self.y + taille, lien))

    def bandeau(self, texte, taille=12):
        """Titre d'un chantier sur fond gris clair."""
        lignes = decouper(texte, taille, True, LARGEUR - 2 * MARGE - 12)
        hauteur = len(lignes) * (taille * 1.3) + 10
        self.besoin(hauteur + 60)
        self._rect(MARGE, self.y - hauteur, LARGEUR - 2 * MARGE, hauteur, 0.92)
        y = self.y - 6
        for ligne in lignes:
            y -= taille * 1.15
            self._texte(MARGE + 6, y, ligne, taille, True)
            y -= taille * 0.15
        self.y -= hauteur + 6

    def vignettes(self, images, legende_taille=7.5):
        """Rangée(s) de vignettes (3 par ligne) avec le nom du fichier dessous."""
        par_ligne, ecart = 3, 10.0
        largeur_case = (LARGEUR - 2 * MARGE - ecart * (par_ligne - 1)) / par_ligne
        hauteur_case = largeur_case * 0.75
        for debut in range(0, len(images), par_ligne):
            self.besoin(hauteur_case + 22)
            self.y -= hauteur_case
            for k, (nom, image) in enumerate(images[debut:debut + par_ligne]):
                x0 = MARGE + k * (largeur_case + ecart)
                self._rect(x0, self.y, largeur_case, hauteur_case, 0.95)
                larg_i, haut_i = image["largeur"], image["hauteur"]
                if image["orientation"] in (6, 8):
                    larg_i, haut_i = haut_i, larg_i
                echelle = min(largeur_case / larg_i, hauteur_case / haut_i)
                dw, dh = larg_i * echelle, haut_i * echelle
                a, b, c, d, e, f = _matrice(image["orientation"], x0 + (largeur_case - dw) / 2, self.y + (hauteur_case - dh) / 2, dw, dh)
                indice = self._enregistrer(image)
                self._op("q %s %s %s %s %s %s cm /Im%d Do Q" % (_nombre(a), _nombre(b), _nombre(c), _nombre(d), _nombre(e), _nombre(f), indice))
                legende = decouper(nom, legende_taille, False, largeur_case)[0]
                self._texte(x0, self.y - 9, legende, legende_taille, False, _GRIS)
            self.y -= 16

    def _enregistrer(self, image):
        for i, existante in enumerate(self.images):
            if existante is image:
                break
        else:
            self.images.append(image)
            i = len(self.images) - 1
        if i not in self.pages[-1]["images"]:
            self.pages[-1]["images"].append(i)
        return i

    # --- fabrication du fichier -------------------------------------------------
    def octets(self):
        n = len(self.pages)
        for numero, page in enumerate(self.pages, 1):                       # en-tête et pied de page de chaque feuille
            ops = page["ops"]
            en_tete = _litteral(self.titre_courant)
            ops.append(b"0.4 0.4 0.4 rg BT /F1 8.5 Tf %s %s Td " % (_nombre(MARGE).encode(), _nombre(HAUTEUR - MARGE + 6).encode()) + en_tete + b" Tj ET")
            ops.append(("0.75 G 0.6 w %s %s m %s %s l S" % (_nombre(MARGE), _nombre(HAUTEUR - MARGE), _nombre(LARGEUR - MARGE), _nombre(HAUTEUR - MARGE))).encode())
            pied = "Page %d / %d" % (numero, n)
            ops.append(b"0.4 0.4 0.4 rg BT /F1 8.5 Tf %s %s Td " % (_nombre(LARGEUR - MARGE - largeur(pied, 8.5)).encode(), _nombre(MARGE - 6).encode())
                       + _litteral(pied) + b" Tj ET")
        objets = [None] * 4                                                  # 1 catalogue, 2 pages, 3 et 4 polices
        objets[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        objets[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
        numeros_images = []
        for image in self.images:
            numeros_images.append(len(objets) + 1)
            entete = ("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /%s /BitsPerComponent 8 /Filter /%s %s /Length %d >>\nstream\n"
                      % (image["largeur"], image["hauteur"], image["espace"], image["filtre"], image["parms"], len(image["donnees"])))
            objets.append(entete.encode("latin-1") + image["donnees"] + b"\nendstream")
        numeros_pages = []
        for page in self.pages:
            contenu = zlib.compress(b"\n".join(page["ops"]))
            objets.append(b"<< /Filter /FlateDecode /Length %d >>\nstream\n" % len(contenu) + contenu + b"\nendstream")
            numero_contenu = len(objets)
            annots = []
            for x1, y1, x2, y2, url in page["liens"]:
                objets.append(("<< /Type /Annot /Subtype /Link /Rect [%s %s %s %s] /Border [0 0 0] /A << /S /URI /URI "
                               % (_nombre(x1), _nombre(y1), _nombre(x2), _nombre(y2))).encode("latin-1") + _litteral(url) + b" >> >>")
                annots.append("%d 0 R" % len(objets))
            xobjets = " ".join("/Im%d %d 0 R" % (i, numeros_images[i]) for i in page["images"])
            objets.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] /Contents %d 0 R "
                           "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> /XObject << %s >> >> /Annots [%s] >>"
                           % (_nombre(LARGEUR), _nombre(HAUTEUR), numero_contenu, xobjets, " ".join(annots))).encode("latin-1"))
            numeros_pages.append(len(objets))
        objets[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        objets[1] = ("<< /Type /Pages /Count %d /Kids [%s] >>" % (len(numeros_pages), " ".join("%d 0 R" % p for p in numeros_pages))).encode("latin-1")
        sortie = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        positions = []
        for numero, corps in enumerate(objets, 1):
            positions.append(len(sortie))
            sortie += b"%d 0 obj\n" % numero + corps + b"\nendobj\n"
        debut_xref = len(sortie)
        sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
        for p in positions:
            sortie += b"%010d 00000 n \n" % p
        sortie += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, debut_xref)
        return bytes(sortie)


# ---------------------------------------------------------------------------
# Contenu : la journée
# ---------------------------------------------------------------------------
def _telephone(t):
    m = re.fullmatch(r"\+1(\d{3})(\d{3})(\d{4})", t or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else (t or "")


def _oui_non(x):
    return "oui" if x else "non"


def _titre_jour(jour):
    d = datetime.date.fromisoformat(jour)
    return f"{JOURS[d.weekday()].capitalize()} {d.day} {MOIS[d.month - 1]} {d.year}"


def _dict(cur):
    noms = [c[0] for c in cur.description]
    return [dict(zip(noms, r)) for r in cur.fetchall()]


def photos_du_chantier(dossier_base, dossier_photos):
    """Fichiers photo (JPEG/PNG) du dossier de photos du chantier, triés par nom. Jamais en dehors du dossier de la base."""
    if not dossier_photos or dossier_base is None:
        return []
    base = Path(dossier_base).resolve()
    dossier = (base / dossier_photos).resolve()
    try:
        dossier.relative_to(base)
    except ValueError:
        return []
    if not dossier.is_dir():
        return []
    return sorted((p for p in dossier.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS_PHOTO), key=lambda p: p.name.lower())


def _chantier(doc, rang, chantier, heure, travaux, paiements, client, dossier_base):
    c = chantier
    nom = c["client_nom_complet"]
    horaire = f"{heure_texte(heure['debut'])} à {heure_texte(heure['fin'])}"
    doc.bandeau(f"{rang}. {horaire}  -  {nom}")
    doc.champ("Statut", LIBELLES_STATUT.get(c["statut"], c["statut"]))
    tel = " / ".join(t for t in (_telephone(c["telephone"]), _telephone(c["telephone_2"])) if t)
    doc.champ("Client", nom + (f" ({client['entreprise']})" if client["entreprise"] and client["entreprise"] != nom else ""))
    doc.champ("Téléphone", tel)
    doc.champ("Rappels par texto", _oui_non(c["sms_ok"]) if tel else "")
    doc.champ("Courriel", c["courriel"])
    adresse = f"{c['adresse']}, {c['ville']}, {c['province']}" + (f" {c['code_postal']}" if c["code_postal"] else "")
    doc.champ("Adresse", adresse, lien="https://www.google.com/maps/search/?api=1&query=" + quote(c["adresse_maps"]))
    doc.champ("Secteur", c["secteur"])
    doc.champ("Accès / à savoir", c["notes_acces"])
    doc.champ("Notes sur le client", client["notes"])
    doc.espace(3)
    if travaux:
        for k, (libelle, precision) in enumerate(travaux):
            doc.champ("Travaux" if k == 0 else "", libelle + (f" : {precision}" if precision else ""))
    else:
        doc.champ("Travaux", "(aucun type indiqué)")
    doc.champ("Description", c["description"])
    options = []
    if c["nacelle"]:
        options.append("Nacelle requise")
    if c["debarrasser_bois"]:
        options.append("Débarrasser le bois")
    elif c["bois_format"]:
        options.append("Bois laissé sur place, format " + LIBELLES_BOIS.get(c["bois_format"], c["bois_format"]))
    doc.champ("Options", " ; ".join(options) if options else "Aucune")
    duree = heures(c["duree_estimee_h"]) if c["duree_estimee_h"] else "à estimer"
    doc.champ("Durée estimée", duree)
    if c["duree_reelle_h"]:
        doc.champ("Durée réelle", heures(c["duree_reelle_h"]))
    doc.champ("Demande reçue le", c["date_soumission"])
    doc.espace(3)
    if c["prix_ht"] is None:
        doc.champ("Prix", "à confirmer")
    else:
        doc.champ("Prix avant taxes", argent(c["prix_ht"]))
        if c["tps"] or c["tvq"]:
            doc.champ("TPS / TVQ", f"{argent(c['tps'])} / {argent(c['tvq'])}")
        doc.champ("Total (taxes incluses)", argent(c["total_ttc"]))
    doc.champ("Règlement prévu", LIBELLES_MODE.get(c["modalite_paiement"], "") if c["modalite_paiement"] else "")
    for p in paiements:
        detail = f"{p['date_paiement']} : {argent(p['montant'])} ({LIBELLES_MODE.get(p['mode'], p['mode'])})"
        if p["reference"]:
            detail += f", réf. {p['reference']}"
        if p["notes"]:
            detail += f" - {p['notes']}"
        doc.champ("Paiement reçu", detail)
    if c["prix_ht"] is not None:
        doc.champ("Déjà payé", argent(c["paye"]))
        doc.champ("Reste à encaisser", argent(max(c["solde"], 0)) if c["solde"] > 0 else "Rien (payé)")
    doc.espace(3)
    doc.champ("Dossier de photos", c["dossier_photos"])
    _photos(doc, dossier_base, c["dossier_photos"])
    doc.espace(8)


def _photos(doc, dossier_base, dossier_photos):
    fichiers = photos_du_chantier(dossier_base, dossier_photos)
    if not fichiers:
        return
    prises, omises = [], []
    for chemin in fichiers[:MAX_PHOTOS]:
        image, raison = charger_image(chemin)
        if image is None:
            omises.append(f"{chemin.name} ({raison})")
        else:
            prises.append((chemin.name, image))
    doc.espace(4)
    doc.paragraphe(f"Photos ({len(fichiers)})", 9.5, True, 0, _GRIS)
    if prises:
        doc.vignettes(prises)
    if omises:
        doc.paragraphe("Non incluses : " + " ; ".join(omises), 8, False, 0, _GRIS)
    if len(fichiers) > MAX_PHOTOS:
        doc.paragraphe(f"... et {len(fichiers) - MAX_PHOTOS} autre(s) photo(s) dans le dossier (seules les {MAX_PHOTOS} premières sont incluses).", 8, False, 0, _GRIS)


def journee_pdf(conn, jour, dossier_base=None):
    """Octets du PDF de la journée `jour` (AAAA-MM-JJ) : résumé, puis tous les détails de chaque chantier."""
    doc = Document(f"SylvainCulteur  -  Journée du {_titre_jour(jour)}")
    ids = ids_de_la_journee(conn, jour)
    chantiers = []
    for i in ids:
        lignes = _dict(conn.execute("SELECT * FROM v_chantiers WHERE chantier_id = ?", (i,)))
        if lignes:
            chantiers.append(lignes[0])
    doc.titre(f"Journée de travail : {_titre_jour(jour)}", 17)
    if not chantiers:
        doc.espace(6)
        doc.paragraphe("Aucun chantier planifié ce jour-là.", 11)
        return doc.octets()
    horaire = calculer_horaire([c["duree_estimee_h"] for c in chantiers])
    total_h = sum(c["duree_estimee_h"] or 0 for c in chantiers)
    total = round(sum(c["total_ttc"] or 0 for c in chantiers), 2)
    doc.paragraphe(f"{len(chantiers)} chantier{'s' if len(chantiers) > 1 else ''}  -  durée totale {heures(total_h) if total_h else 'inconnue'}"
                   f"  -  début {heure_texte(DEBUT_JOURNEE)}  -  fin prévue {heure_texte(horaire[-1]['fin'])}", 10.5, True)
    doc.paragraphe(f"Total de la journée : {argent(total)} (taxes incluses)", 10.5)
    doc.paragraphe("Les adresses en bleu ouvrent Google Maps (itinéraire et carte).", 8.5, False, 0, _GRIS)
    doc.paragraphe(f"Dîner {heure_texte(DINER_DEBUT)} - {heure_texte(DINER_FIN)} ; trajets non comptés ; heures calculées d'après l'ordre et les durées estimées.", 8.5, False, 0, _GRIS)
    doc.espace(8)
    # aperçu : une ligne par chantier
    for rang, (c, h) in enumerate(zip(chantiers, horaire), 1):
        doc.paragraphe(f"{rang}.  {heure_texte(h['debut'])} - {heure_texte(h['fin'])}   {c['client_nom_complet']}   -   {c['adresse']}, {c['ville']}"
                       f"   -   {argent(c['total_ttc']) if c['prix_ht'] is not None else 'prix à confirmer'}", 9.5)
    doc.espace(6)
    doc.separateur()
    for rang, (c, h) in enumerate(zip(chantiers, horaire), 1):
        client = _dict(conn.execute("SELECT entreprise, notes FROM clients WHERE id = ?", (c["client_id"],)))[0]
        travaux = conn.execute("SELECT t.libelle, ct.precision FROM chantier_travaux ct JOIN types_travaux t ON t.code = ct.type_travaux "
                               "WHERE ct.chantier_id = ? ORDER BY ct.type_travaux", (c["chantier_id"],)).fetchall()
        paiements = _dict(conn.execute("SELECT date_paiement, montant, mode, reference, notes FROM paiements WHERE chantier_id = ? "
                                       "ORDER BY date_paiement, id", (c["chantier_id"],)))
        doc.besoin(150)
        _chantier(doc, rang, c, h, travaux, paiements, client, dossier_base)
    return doc.octets()
