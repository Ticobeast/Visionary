"""Tests de l'itinéraire de la journée : un lien Google Maps avec les arrêts qu'il reste à faire, dans l'ordre de passage."""
import datetime
import html
import re
import sys
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import composants  # noqa: E402
import noyau  # noqa: E402
from test_tableau import AUJOURDHUI, BaseTableau  # noqa: E402

DEMAIN = (AUJOURDHUI + datetime.timedelta(days=1)).isoformat()


class TestAdresse(unittest.TestCase):
    def test_un_seul_arret(self):
        self.assertEqual(composants.url_itineraire(["1 Rue A, Mirabel, QC, Canada"]),
                         "https://www.google.com/maps/dir/?api=1&travelmode=driving&destination=1%20Rue%20A%2C%20Mirabel%2C%20QC%2C%20Canada")

    def test_plusieurs_arrets_dans_l_ordre(self):
        url = composants.url_itineraire(["A & B", "", "C", None, "D"])              # les adresses vides sont sautées
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(q["destination"], ["D"])                                     # le dernier arrêt
        self.assertEqual(q["waypoints"], ["A & B|C"])                                 # les autres, dans l'ordre ; « & » bien encodé
        self.assertNotIn(" ", url)

    def test_aucune_adresse(self):
        self.assertEqual(composants.url_itineraire([]), "")
        self.assertEqual(composants.url_itineraire(["", None]), "")

    def test_dix_arrets_au_plus(self):
        url = composants.url_itineraire([f"Arret {i}" for i in range(1, 15)])
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(q["destination"], ["Arret 10"])
        self.assertEqual(len(q["waypoints"][0].split("|")), 9)                        # limite de Google Maps


class TestJournee(BaseTableau):
    def lien(self, page):
        m = re.search(r'<a class="bouton secondaire" href="(https://www\.google\.com/maps/dir/[^"]+)"[^>]*>Itinéraire</a>', page)
        return html.unescape(m.group(1)) if m else None

    def planifier(self, nom, ordre):
        c = noyau.ouvrir_base(self.db)[0]
        c.execute("UPDATE chantiers SET statut = 'planifie', date_prevue = ?, ordre_jour = ?, duree_estimee_h = COALESCE(duree_estimee_h, 1) WHERE id = ?",
                  (DEMAIN, ordre, self.ids[nom]))
        c.close()

    def test_bouton_dans_le_tableau_de_bord(self):
        self.planifier("Urgent", 1)                                                    # Urgent d'abord, puis Demain
        c = noyau.ouvrir_base(self.db)[0]
        c.execute("UPDATE chantiers SET ordre_jour = 2 WHERE id = ?", (self.ids["Demain"],))
        c.close()
        _, page = self.get("/", {"date": DEMAIN})
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.lien(page)).query)
        self.assertTrue(q["waypoints"][0].startswith("1 Rue Urgent"))                  # dans l'ordre de passage
        self.assertTrue(q["destination"][0].startswith("2 Rue Demain"))
        pied = page[page.index('class="barre pied-jour"'):]
        self.assertLess(pied.index("Gérer cette journée"), pied.index(">Itinéraire<"))
        self.assertLess(pied.index(">Itinéraire<"), pied.index("Télécharger la journée"))

    def test_seulement_ce_qu_il_reste_a_faire(self):
        """Un chantier terminé sort de l'itinéraire ; tout terminé (ou aucune adresse) : pas de bouton."""
        self.planifier("Urgent", 1)
        self.post("/action/terminer", {"chantier_id": str(self.ids["Urgent"]), "retour": "/", "paye": "non"})
        _, page = self.get("/", {"date": DEMAIN})
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.lien(page)).query)
        self.assertNotIn("waypoints", q)
        self.assertTrue(q["destination"][0].startswith("2 Rue Demain"))
        self.post("/action/terminer", {"chantier_id": str(self.ids["Demain"]), "retour": "/", "paye": "non"})
        _, page = self.get("/", {"date": DEMAIN})
        self.assertIsNone(self.lien(page))

    def test_journee_vide(self):
        _, page = self.get("/", {"date": (AUJOURDHUI + datetime.timedelta(days=9)).isoformat()})
        self.assertIsNone(self.lien(page))


if __name__ == "__main__":
    unittest.main()
