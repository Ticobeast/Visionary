"""Tests des textos et courriels préremplis (outils/messages.py) : contenu, liens, droits, affichage."""
import datetime
import sys
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import messages  # noqa: E402
import noyau  # noqa: E402
from test_auth import BaseAuth  # noqa: E402
from test_tableau import AUJOURDHUI, BaseTableau  # noqa: E402

TEL = "+14505550101"


class TestTextes(unittest.TestCase):
    def test_travaux_avec_elision(self):
        self.assertEqual(messages._travaux("Taille de haie"), "les travaux de taille de haie")
        self.assertEqual(messages._travaux("Émondage"), "les travaux d'émondage")
        self.assertEqual(messages._travaux("Essouchement + Taille de haie"), "les travaux d'essouchement et de taille de haie")
        self.assertEqual(messages._travaux("Émondage + Abattage + Élagage"), "les travaux d'émondage, d'abattage et d'élagage")
        self.assertEqual(messages._travaux(None), "vos travaux")

    def test_date(self):
        lundi = datetime.date(2026, 11, 16)
        self.assertEqual(messages._date_texte("2026-11-16", lundi), "aujourd'hui")
        self.assertEqual(messages._date_texte("2026-11-17", lundi), "demain, mardi 17 novembre")
        self.assertEqual(messages._date_texte("2026-11-19", lundi), "le jeudi 19 novembre")
        self.assertEqual(messages._date_texte("2026-12-01", lundi), "le mardi 1er décembre")

    def test_lien_texto(self):
        url = messages.url_texto(TEL, "Bonjour Luc, à demain & merci ?")
        self.assertTrue(url.startswith(f"sms:{TEL}?&body="))
        corps = url.split("body=", 1)[1]
        self.assertNotIn(" ", corps)
        self.assertNotIn("&", corps)                       # un « & » du texte couperait le message
        self.assertEqual(urllib.parse.unquote(corps), "Bonjour Luc, à demain & merci ?")

    def test_lien_courriel(self):
        url = messages.url_courriel("luc@example.com", "Rappel - X", "Bonjour Luc,", "Petit rappel.")
        self.assertTrue(url.startswith("mailto:luc@example.com?subject=Rappel%20-%20X&body="))
        corps = urllib.parse.unquote(url.split("body=", 1)[1])
        self.assertTrue(corps.startswith("Bonjour Luc,\n\nPetit rappel.\n\nMerci !"))


class TestMessages(BaseTableau):
    def conn(self):
        return noyau.ouvrir_base(self.db)[0]

    def client_de(self, nom, **valeurs):
        c = self.conn()
        for k, v in valeurs.items():
            c.execute(f"UPDATE clients SET {k} = ? WHERE nom = ?", (v, nom))
        c.close()

    def test_suivi_de_soumission(self):
        self.client_de("Devis", telephone=TEL)
        c = self.conn()
        m = messages.message(c, self.ids["Devis"])
        c.close()
        self.assertEqual(m["sorte"], "suivi")
        self.assertTrue(m["texte"].startswith("Bonjour, ici Sylvainculteur."))      # pas de prénom : « Bonjour, »
        self.assertIn("suivi de notre soumission pour les travaux d'abattage (500,00 $ taxes incluses)", m["texte"])
        self.assertTrue(m["texto_ok"])

    def test_rappel_de_la_visite(self):
        self.client_de("Demain", telephone=TEL, prenom="Luc")
        c = self.conn()
        m = messages.message(c, self.ids["Demain"])
        c.close()
        d = AUJOURDHUI + datetime.timedelta(days=1)
        self.assertEqual(m["sorte"], "rappel")
        self.assertIn(f"nous passerons chez vous {messages._date_texte(d.isoformat(), AUJOURDHUI)}, en avant-midi, "
                      "pour les travaux d'émondage", m["texte"])
        self.assertTrue(m["texte"].startswith("Bonjour Luc, ici Sylvainculteur."))

    def test_rappel_en_apres_midi(self):
        """Deuxième de la journée, après un chantier de 5 h (7 h 30 - 13 h) : après-midi."""
        self.client_de("Demain", telephone=TEL)
        c = self.conn()
        c.execute("UPDATE chantiers SET statut = 'planifie', date_prevue = ?, duree_estimee_h = 5, ordre_jour = 1 WHERE id = ?",
                  ((AUJOURDHUI + datetime.timedelta(days=1)).isoformat(), self.ids["Urgent"]))
        c.execute("UPDATE chantiers SET ordre_jour = 2 WHERE id = ?", (self.ids["Demain"],))
        self.assertIn("en après-midi", messages.message(c, self.ids["Demain"])["texte"])
        self.assertIn("en avant-midi", messages.message(c, self.ids["Urgent"])["texte"])
        c.close()

    def test_rappel_de_paiement_reserve_aux_finances(self):
        self.client_de("Fait", telephone=TEL)
        c = self.conn()
        self.assertIsNone(messages.message(c, self.ids["Fait"]))
        m = messages.message(c, self.ids["Fait"], finances=True)
        c.close()
        self.assertEqual(m["sorte"], "paiement")
        self.assertIn("un solde de 919,80 $ reste à payer", m["texte"])
        self.assertNotIn("Interac", m["texte"])                       # mode de règlement inconnu : pas d'adresse Interac

    def test_interac_donne_l_adresse(self):
        chid = self.terminer_sans_toucher("Virement", 200, "interac")
        c = self.conn()
        m = messages.message(c, chid, finances=True)
        c.close()
        self.assertIn("Le virement Interac peut être envoyé à sylvainculteur@gmail.com.", m["texte"])

    def test_rien_a_proposer(self):
        c = self.conn()
        for nom in ("Urgent", "Normal"):                                 # à planifier
            self.assertIsNone(messages.message(c, self.ids[nom], finances=True), nom)
        c.execute("UPDATE chantiers SET date_prevue = ? WHERE id = ?", ((AUJOURDHUI - datetime.timedelta(days=2)).isoformat(), self.ids["Demain"]))
        self.assertIsNone(messages.message(c, self.ids["Demain"]))      # visite déjà passée (pas encore terminée) : plus de rappel
        self.assertEqual(messages.carte(c, self.ids["Urgent"]), "")
        c.close()

    def test_textos_refuses_par_le_client(self):
        self.client_de("Demain", telephone=TEL, sms_ok=0)
        c = self.conn()
        m = messages.message(c, self.ids["Demain"])
        self.assertFalse(m["texto_ok"])
        carte = messages.carte(c, self.ids["Demain"])
        c.close()
        self.assertNotIn("sms:", carte)
        self.assertIn("Le client a refusé les textos et n'a pas de courriel.", carte)
        self.client_de("Demain", courriel="demain@example.com")
        c = self.conn()
        carte = messages.carte(c, self.ids["Demain"])
        c.close()
        self.assertIn("mailto:demain@example.com", carte)
        self.assertIn("pas de textos (refusés par le client)", carte)

    def test_sans_telephone_ni_courriel(self):
        c = self.conn()
        carte = messages.carte(c, self.ids["Demain"])
        c.close()
        self.assertIn("Ajoute un téléphone ou un courriel", carte)

    def test_page_du_chantier(self):
        self.client_de("Demain", telephone=TEL)
        statut, page = self.get(f"/chantier/{self.ids['Demain']}")
        self.assertTrue(statut.startswith("200"))
        self.assertIn("<h2>Message au client</h2>", page)
        self.assertIn("Rappel de la visite", page)
        self.assertIn(f'href="sms:{TEL}?&amp;body=Bonjour%2C%20ici%20Sylvainculteur.', page)
        _, page = self.get(f"/chantier/{self.ids['Fait']}")              # sans contrôle d'accès : administrateur
        self.assertIn("Rappel de paiement", page)

    def test_bulle_texto_dans_la_journee(self):
        demain = (AUJOURDHUI + datetime.timedelta(days=1)).isoformat()
        _, page = self.get("/", {"date": demain})
        self.assertNotIn('class="bouton secondaire texto-jour"', page)                              # pas de téléphone
        self.client_de("Demain", telephone=TEL)
        _, page = self.get("/", {"date": demain})
        self.assertIn('class="bouton secondaire texto-jour" href="sms:', page)
        self.client_de("Demain", sms_ok=0)
        _, page = self.get("/", {"date": demain})
        self.assertNotIn('class="bouton secondaire texto-jour"', page)


class TestDroitsMessages(BaseAuth):
    def test_soumission_ne_voit_pas_le_rappel_de_paiement(self):
        """Fiche 2 (Pierre Lavoie) : terminée, rien payé. Le compte « soumission » n'a pas les finances."""
        self.comptes()
        admin = self.ouvrir("Admin", "motdepasse-admin")
        soum = self.ouvrir("Soumission", "motdepasse-soum")
        self.assertIn("Rappel de paiement", self.req("GET", "/chantier/2", cookie=admin)[2])
        statut, _, page = self.req("GET", "/chantier/2", cookie=soum)
        self.assertTrue(statut.startswith("200"))
        self.assertNotIn("Rappel de paiement", page)
        self.assertNotIn("Message au client", page)


if __name__ == "__main__":
    unittest.main()
