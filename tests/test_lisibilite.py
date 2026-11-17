"""Tests de lisibilité : dates écrites pour un humain, téléphone lisible dans les champs, titre au nom du client, pastilles utiles."""
import datetime
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import vue  # noqa: E402
from test_tableau import BaseTableau  # noqa: E402

LUNDI = datetime.date(2026, 11, 16)


class TestDates(unittest.TestCase):
    def test_date_lisible(self):
        self.assertEqual(vue.date_lisible("2026-12-04", LUNDI), "ven. 4 déc.")
        self.assertEqual(vue.date_lisible("2026-12-01", LUNDI), "mar. 1er déc.")
        self.assertEqual(vue.date_lisible("2025-04-12", LUNDI), "12 avril 2025")           # autre année : l'année, pas le jour
        self.assertEqual(vue.date_lisible("2026-11-16 08:30:00", LUNDI), "lun. 16 nov.")
        self.assertEqual(vue.date_lisible("", LUNDI), "")
        self.assertEqual(vue.date_lisible(None, LUNDI), "")
        self.assertEqual(vue.date_lisible("bientôt", LUNDI), "bientôt")                     # illisible : rendu tel quel

    def test_le_date(self):
        self.assertEqual(vue.le_date("2026-11-16", LUNDI), "aujourd'hui")
        self.assertEqual(vue.le_date("2026-11-17", LUNDI), "demain")
        self.assertEqual(vue.le_date("2026-11-15", LUNDI), "hier")
        self.assertEqual(vue.le_date("2026-11-19", LUNDI), "le jeu. 19 nov.")
        self.assertEqual(vue.le_date("2027-02-18", LUNDI), "le 18 févr. 2027")

    def test_telephone_lisible_dans_le_champ(self):
        self.assertEqual(vue._tel_lisible({"client_telephone": "+18195550107"}, "client_telephone")["client_telephone"], "819-555-0107")
        for brut in ("", None, "819 555", "+33123456789"):
            self.assertEqual(vue._tel_lisible({"client_telephone": brut}, "client_telephone")["client_telephone"], brut)


class TestPages(BaseTableau):
    def test_fiche_au_nom_du_client(self):
        i = self.ids["Demain"]
        _, page = self.get(f"/chantier/{i}")
        self.assertIn("<h1>Demain</h1>", page)
        self.assertIn(f'<span class="no-fiche">Chantier n° {i}</span>', page)
        self.assertIn("Prévu demain", page)
        self.assertNotIn(f"Chantier #{i}", page)
        self.assertNotIn("À venir", page)                                   # la pastille de paiement ne paraît que lorsqu'elle sert
        _, page = self.get(f"/soumission/{self.ids['Devis']}")
        self.assertIn("<h1>Devis</h1>", page)
        self.assertIn(f"Soumission n° {self.ids['Devis']}", page)

    def test_liste_des_chantiers(self):
        _, page = self.get("/chantiers")
        self.assertIn("prévu demain", page)
        self.assertNotIn('class="badge b-a_venir"', page)
        self.assertIn(">À recevoir<", page)                                 # terminé non payé : la pastille reste

    def test_le_telephone_enregistre_garde_la_forme_de_la_base(self):
        """Le champ affiche 450-555-0100 ; réenregistré tel quel, la base garde +14505550100."""
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (self.ids["Urgent"],))[0][0]
        _, page = self.get(f"/client/{cid}/modifier")
        self.assertIn('name="client_telephone" type="tel" value="450-555-0100"', page)
        statut, _, _ = self.post(f"/client/{cid}/modifier", {"client_nom": "Urgent", "client_telephone": "450-555-0100", "adresse": "1 Rue Urgent",
                                                             "client_secteur": "cap_de_la_madeleine", "client_sms_ok": "1",
                                                             "empreinte": re.search(r'name="empreinte" value="([^"]*)"', page).group(1)})
        self.assertTrue(statut.startswith("303"), statut)
        self.assertEqual(self.sql("SELECT telephone FROM clients WHERE id = ?", (cid,)), [("+14505550100",)])


class TestPrix(BaseTableau):
    def test_prix_plus_tx(self):
        """Le résumé d'une fiche : le total en gros, « 300,00 $ + tx » dessous ; le détail des taxes est sur le PDF."""
        _, page = self.get(f"/chantier/{self.ids['Demain']}")
        resume = page[page.index('class="carte resume-chantier"'):page.index('class="carte contact"')]
        self.assertIn("<small>300,00 $ + tx</small>", resume)
        self.assertNotIn("TPS", resume)
        self.assertNotIn("reçu", resume)                                    # rien reçu : le solde serait le total, on ne le répète pas
        self.post(f"/chantier/{self.ids['Demain']}/paiement", {"paiement_date": "2026-11-01", "paiement_montant": "100", "paiement_mode": "cheque"})
        _, page = self.get(f"/chantier/{self.ids['Demain']}")
        self.assertIn("reçu 100,00 $ · solde <b>", page)

    def test_sans_taxes_pas_de_tx(self):
        _, page = self.get(f"/soumission/{self.ids['Devis']}")              # 500 $ sans taxes
        resume = page[page.index('class="carte resume-chantier"'):page.index('class="carte contact"')]
        self.assertIn("500,00 $", resume)
        self.assertNotIn("+ tx", resume)


class TestNavigation(BaseTableau):
    def test_fleche_de_retour_en_haut_des_fiches(self):
        """« ‹ Chantiers » en haut d'une fiche ; le navigateur la fait pointer vers la page d'où l'on vient vraiment."""
        _, page = self.get(f"/chantier/{self.ids['Demain']}")
        self.assertIn('<a class="fermer retour-haut" href="/chantiers"><span>Chantiers</span></a><h1>Demain</h1>', page)
        _, page = self.get(f"/soumission/{self.ids['Devis']}")
        self.assertIn('<a class="fermer retour-haut" href="/soumissions"><span>Soumissions</span></a>', page)
        cid = self.sql("SELECT client_id FROM chantiers WHERE id = ?", (self.ids["Devis"],))[0][0]
        _, page = self.get(f"/client/{cid}")
        self.assertIn('<a class="fermer retour-haut" href="/clients"><span>Clients</span></a><h1>Devis</h1>', page)
        _, page = self.get("/chantiers")
        self.assertNotIn('class="fermer retour-haut"', page)               # une page principale n'en a pas : la barre du bas suffit

    def test_libelle_de_retour(self):
        self.assertEqual([vue.libelle_retour(c) for c in ("/", "/chantiers?statut=planifie", "/client/4", "/soumission/2", "/journee", "/x")],
                         ["Accueil", "Chantiers", "Client", "Soumission", "Journée", "Retour"])

    def test_listes_du_telephone(self):
        """Soumissions : la carte entière ouvre la fiche (les boutons sont sur la fiche) ; Chantiers : les terminés se cachent sur
        téléphone tant qu'on ne cherche rien (la pastille « À recevoir » les montre)."""
        _, page = self.get("/soumissions")
        devis = self.ids["Devis"]
        self.assertIn(f'<a class="lien-carte" href="/soumission/{devis}">', page)
        _, page = self.get("/chantiers")
        self.assertIn('<table class="liste chantiers sans-finis">', page)
        self.assertIn("<tr class=fini>", page)
        _, page = self.get("/chantiers", {"paiement": "a_recevoir"})
        self.assertIn('<table class="liste chantiers">', page)                 # on cherche quelque chose : tout est montré


class TestMenuRapide(BaseTableau):
    def test_menu_des_cartes_de_soumission(self):
        """Téléphone : Accepter, En attente, Refuser et le PDF restent à portée, derrière le petit bouton « ··· » de la carte."""
        _, page = self.get("/soumissions")
        devis = self.ids["Devis"]
        ligne = page[page.index(f'<a class="lien-carte" href="/soumission/{devis}">'):]
        ligne = ligne[:ligne.index("</tr>")]
        menu = ligne[ligne.index('<details class="menu-rapide">'):]
        for attendu in (f'action="/soumission/{devis}/accepter"', f'href="/soumission/{devis}/attente', f'action="/soumission/{devis}/refuser"',
                        f'href="/soumission/{devis}/pdf"'):
            self.assertIn(attendu, menu)
        self.assertIn('<summary aria-label="Actions" title="Actions"></summary>', menu)
        self.assertIn('details.menu-rapide[open]', page)                   # un toucher ailleurs ferme le menu


if __name__ == "__main__":
    unittest.main()
