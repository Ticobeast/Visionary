"""Pas de doublon : sur une fiche, un même lien (ou bouton) ne paraît qu'une fois, et une même information n'est pas répétée.

Règle de docs/style_interface.md. Certains blocs existent en deux versions, une pour l'ordinateur et une pour le téléphone
(boutons côte à côte ou menu « ··· », « Modifier » replié ou menu) : une seule est visible à la fois, on n'en garde qu'une ici.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_tableau import BaseTableau  # noqa: E402


def _sans_bloc(html, debut, balise):
    """Retire chaque élément qui commence par `debut` (jusqu'à sa balise fermante, en comptant l'imbrication)."""
    while debut in html:
        i = html.index(debut)
        profondeur, j = 0, i
        for m in re.finditer(rf"<(/?){balise}\b", html[i:]):
            profondeur += -1 if m.group(1) else 1
            if profondeur == 0:
                j = i + m.end()
                j = html.index(">", j) + 1
                break
        html = html[:i] + html[j:]
    return html


def version_ordinateur(page):
    """Le contenu de la page tel que l'ordinateur l'affiche (sans le menu « ··· » ni les blocs du téléphone)."""
    main = page[page.index("<main"):page.index("</main>")]
    main = _sans_bloc(main, '<details class="menu-rapide', "details")
    main = _sans_bloc(main, '<div class="actions-bloc tel-bloc">', "div")
    return re.sub(r"<tbody>.*?</tbody>", "", main, flags=re.S)                 # une liste : chaque ligne a ses propres liens


def version_telephone(page):
    """... et tel que le téléphone l'affiche (sans les blocs « pc-seul » ni les boutons doublés par le menu)."""
    main = page[page.index("<main"):page.index("</main>")]
    main = _sans_bloc(main, '<span class="actions-sec">', "span")
    main = _sans_bloc(main, '<span class="pc-seul', "span")
    main = _sans_bloc(main, '<details class="avance modifier-fiche pc-seul"', "details")
    return re.sub(r"<tbody>.*?</tbody>", "", main, flags=re.S)


def cibles(html):
    liens = [h for h in re.findall(r'<a [^>]*href="([^"#][^"]*)"', html)]
    formulaires = re.findall(r'<form [^>]*action="([^"]+)"', html)
    return [re.sub(r"[?&](retour|ok|err)=[^&]*", "", c) for c in liens + formulaires]


class TestPasDeDoublon(BaseTableau):
    def fiches(self):
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (self.ids["Demain"],))[0][0]
        return ([f"/chantier/{self.ids[n]}" for n in ("Demain", "Fait", "Urgent")] + [f"/soumission/{self.ids['Devis']}", f"/client/{cid}"])

    def test_un_lien_une_seule_fois(self):
        for chemin in self.fiches():
            _, page = self.get(chemin)
            for nom, version in (("ordinateur", version_ordinateur(page)), ("téléphone", version_telephone(page))):
                vus = cibles(version)
                doubles = sorted({c for c in vus if vus.count(c) > 1})
                self.assertEqual(doubles, [], f"{chemin} ({nom}) : lien en double {doubles}")

    def test_pas_de_pastille_qui_repete_le_numero(self):
        _, page = self.get(f"/soumission/{self.ids['Devis']}")
        resume = page[page.index('class="carte resume-chantier"'):page.index('class="actions-bloc"')]
        self.assertIn("Soumission n° ", resume)
        self.assertNotIn("b-soumission", resume)                              # pas de pastille « SOUMISSION » à côté

    def test_pas_de_surtitre_qui_repete_le_titre(self):
        for chemin in ("/", "/chantiers", "/soumissions", "/clients", "/journee"):
            _, page = self.get(chemin)
            bandeau = page[page.index('class="bandeau-page"'):page.index("</section>", page.index('class="bandeau-page"'))]
            self.assertNotIn("tag-badge", bandeau, chemin)


if __name__ == "__main__":
    unittest.main()
