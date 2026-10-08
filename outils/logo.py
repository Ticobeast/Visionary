"""Logo de l'entreprise pour les PDF : un fichier SVG converti en dessin vectoriel (net à toutes les tailles, léger).

Aucune dépendance : seuls les éléments <path> sont lus (remplissage `fill`, règle `fill-rule`), avec les commandes de tracé
M L H V C S Q Z (majuscules : coordonnées absolues, minuscules : relatives). C'est ce que produisent les logos « vectorisés »
(Illustrator, Inkscape, Figma, Canva : texte converti en courbes). Un SVG qui contient autre chose (texte, dégradé, transformation,
image, arcs...) est refusé : le PDF se contente alors d'écrire le nom de l'entreprise, rien ne plante.

Le dessin est gardé tel quel (coordonnées du SVG, l'axe y descend) ; `Document.logo` le place à l'échelle voulue.
"""
import re
import threading
from pathlib import Path
from xml.etree import ElementTree

_JETON = re.compile(r"[MmLlHhVvCcSsQqZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_PERMIS = re.compile(r"[\sMmLlHhVvCcSsQqZz0-9eE+.,\-]*")
_ARGUMENTS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "Z": 0}
LIMITE_OCTETS = 5_000_000          # un logo plus gros n'est pas un logo : on ne le lit pas


class LogoIllisible(ValueError):
    """Le fichier n'est pas un SVG de tracés simples (voir l'en-tête du module)."""


class Logo:
    """Dessin vectoriel : `operateurs` (texte PDF, coordonnées du SVG) et sa boîte (x0, y0, largeur, hauteur)."""

    def __init__(self, operateurs, x0, y0, largeur, hauteur):
        self.operateurs, self.x0, self.y0, self.largeur, self.hauteur = operateurs, x0, y0, largeur, hauteur


def _n(x, decimales=2):
    return (f"%.{decimales}f" % x).rstrip("0").rstrip(".") or "0"


def _couleur(valeur):
    """(r, g, b) entre 0 et 1 pour « #rrggbb » ou « #rgb » ; None pour « none » ; noir si absent (règle du SVG)."""
    if valeur is None:
        return (0.0, 0.0, 0.0)
    v = valeur.strip().lower()
    if v == "none":
        return None
    m = re.fullmatch(r"#([0-9a-f]{6}|[0-9a-f]{3})", v)
    if not m:
        raise LogoIllisible(f"couleur non prise en charge : {valeur}")
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


class _Trace:
    """Lit les données `d` d'un tracé SVG et produit les opérateurs PDF m, l, c, h ; `boite` [xmin, ymin, xmax, ymax] s'agrandit."""

    def __init__(self, boite):
        self.boite, self.sortie = boite, []
        self.x = self.y = 0.0
        self.debut = (0.0, 0.0)
        self.dernier_controle = None            # pour la commande S (courbe lisse)

    def _point(self, p):
        b = self.boite
        b[0], b[1], b[2], b[3] = min(b[0], p[0]), min(b[1], p[1]), max(b[2], p[0]), max(b[3], p[1])
        return f"{_n(p[0])} {_n(p[1])}"

    def _absolus(self, v, relatif):
        """Les couples de `v` en coordonnées absolues."""
        if not relatif:
            return [(v[i], v[i + 1]) for i in range(0, len(v), 2)]
        return [(self.x + v[i], self.y + v[i + 1]) for i in range(0, len(v), 2)]

    def commande(self, c, v):
        relatif, majuscule = c.islower(), c.upper()
        if majuscule == "Z":
            self.x, self.y = self.debut
            self.dernier_controle = None
            self.sortie.append("h")
            return
        if majuscule == "H":
            p = (self.x + v[0] if relatif else v[0], self.y)
        elif majuscule == "V":
            p = (self.x, self.y + v[0] if relatif else v[0])
        elif majuscule in "ML":
            p = self._absolus(v, relatif)[0]
        if majuscule in "MLHV":
            self.x, self.y = p
            self.dernier_controle = None
            if majuscule == "M":
                self.debut = p
            self.sortie.append(self._point(p) + (" m" if majuscule == "M" else " l"))
            return
        if majuscule == "C":
            p1, p2, p3 = self._absolus(v, relatif)
        elif majuscule == "S":                  # premier point de contrôle : le symétrique du précédent (ou le point courant)
            p1 = (2 * self.x - self.dernier_controle[0], 2 * self.y - self.dernier_controle[1]) if self.dernier_controle else (self.x, self.y)
            p2, p3 = self._absolus(v, relatif)
        else:                                   # Q : courbe quadratique -> cubique équivalente
            q, p3 = self._absolus(v, relatif)
            p1 = (self.x + 2 / 3 * (q[0] - self.x), self.y + 2 / 3 * (q[1] - self.y))
            p2 = (p3[0] + 2 / 3 * (q[0] - p3[0]), p3[1] + 2 / 3 * (q[1] - p3[1]))
        self.sortie.append(" ".join(self._point(p) for p in (p1, p2, p3)) + " c")
        self.dernier_controle, (self.x, self.y) = p2, p3

    def lire(self, d):
        if not _PERMIS.fullmatch(d):
            raise LogoIllisible("commande de tracé non prise en charge (arcs, etc.)")
        jetons, i, c = _JETON.findall(d), 0, None
        while i < len(jetons):
            if jetons[i][0].isalpha():
                c, i = jetons[i], i + 1
                if c.upper() == "Z":
                    self.commande(c, [])
                    c = None
                    continue
            if c is None:
                raise LogoIllisible("tracé mal formé (nombre sans commande)")
            n = _ARGUMENTS[c.upper()]
            lot = jetons[i:i + n]
            if len(lot) < n or any(t[0].isalpha() for t in lot):
                raise LogoIllisible("tracé mal formé (arguments manquants)")
            self.commande(c, [float(t) for t in lot])
            i += n
            if c in "Mm":                       # les couples suivants d'un M sont des traits droits (règle du SVG)
                c = "l" if c == "m" else "L"
        return self.sortie


def lire_svg(donnees):
    """Logo (voir la classe) d'un SVG donné en octets ; LogoIllisible si le dessin n'est pas fait de tracés simples."""
    if len(donnees) > LIMITE_OCTETS or b"<!ENTITY" in donnees:
        raise LogoIllisible("fichier trop gros ou suspect")
    try:
        racine = ElementTree.fromstring(donnees)
    except ElementTree.ParseError as e:
        raise LogoIllisible(f"SVG illisible : {e}") from e
    operateurs, boite, nb = [], [float("inf"), float("inf"), float("-inf"), float("-inf")], 0
    for element in racine.iter():
        nom = element.tag.rsplit("}", 1)[-1]
        if element.get("transform") or element.get("style") or nom in ("text", "image", "use", "linearGradient", "radialGradient",
                                                                       "clipPath", "mask", "pattern", "filter"):
            raise LogoIllisible(f"élément ou attribut non pris en charge : {nom}")
        if nom != "path":
            continue
        rvb = _couleur(element.get("fill"))
        regle = element.get("fill-rule", "nonzero")
        if regle not in ("evenodd", "nonzero"):
            raise LogoIllisible(f"règle de remplissage inconnue : {regle}")
        trace = _Trace(boite).lire(element.get("d", ""))
        if rvb is None or not trace:
            continue
        operateurs.append("%s %s %s rg" % tuple(_n(c, 3) for c in rvb))
        operateurs.extend(trace)
        operateurs.append("f*" if regle == "evenodd" else "f")
        nb += 1
    if not nb or boite[2] <= boite[0] or boite[3] <= boite[1]:
        raise LogoIllisible("aucun tracé visible")
    return Logo("\n".join(operateurs), boite[0], boite[1], boite[2] - boite[0], boite[3] - boite[1])


_CACHE = {}
_VERROU = threading.Lock()          # le serveur traite plusieurs requêtes à la fois


def charger(chemin):
    """Logo du fichier SVG `chemin`, ou None s'il manque ou n'est pas utilisable (le PDF écrit alors le nom en toutes lettres).
    Lu une seule fois tant que le fichier ne change pas."""
    chemin = Path(chemin)
    try:
        st = chemin.stat()
    except OSError:
        return None
    signature = (str(chemin), st.st_mtime_ns, st.st_size)
    with _VERROU:
        if signature not in _CACHE:
            _CACHE.clear()
            try:
                _CACHE[signature] = lire_svg(chemin.read_bytes())
            except (OSError, LogoIllisible, ValueError, RecursionError):
                _CACHE[signature] = None
        return _CACHE[signature]
