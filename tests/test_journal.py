"""Tests du journal des modifications (outils/journal.py) : qui a fait quoi, et quand.

    python3 -m unittest tests.test_journal -v
"""
import contextlib
import io
import re
import sqlite3
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import auth  # noqa: E402
import interface  # noqa: E402
import journal  # noqa: E402
from test_auth import BUREAU, TELEPHONE, BaseAuth  # noqa: E402

NOUVEAU = {"client_nom": "Tremblay", "adresse": "1 Rue A", "client_secteur": "centre_ville", "type_emondage": "1", "duree_estimee_h": "2"}
ADRESSE = {"adresse": "45 Rue du Lac", "client_secteur": "shawinigan"}


class BaseJournal(BaseAuth):
    def lignes(self, ou=""):
        return self.sql("SELECT utilisateur, action, cible, adresse FROM journal " + ou + " ORDER BY id")

    def tout_le_journal(self):
        return " | ".join(" ".join(str(x) for x in r) for r in self.sql("SELECT * FROM journal"))


class TestEcriture(BaseJournal):
    def setUp(self):
        super().setUp()
        self.comptes()
        self.admin = self.ouvrir("Admin", "motdepasse-admin")
        self.soum = self.ouvrir("Soumission", "motdepasse-soum")
        self.depart = self.sql("SELECT max(id) FROM journal")[0][0]   # les deux connexions ci-dessus sont déjà écrites : on les ignore

    def lignes(self, ou=""):
        return self.sql(f"SELECT utilisateur, action, cible, adresse FROM journal WHERE id > {self.depart} ORDER BY id")

    def sql_ecrire(self, requete):
        c = sqlite3.connect(self.db)
        c.execute(requete)
        c.commit()
        c.close()

    def test_une_action_reussie_ecrit_une_ligne(self):
        statut, en_tetes, _ = self.req("POST", "/client/1/nouvelle-adresse", ADRESSE, cookie=self.admin)
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/client/4?ok=nouvelle_adresse"))
        self.assertEqual(self.lignes(), [("Admin", "Nouvelle adresse du client", "client 1", "/client/1/nouvelle-adresse")])
        self.assertRegex(self.sql("SELECT quand FROM journal")[0][0], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")

    def test_le_compte_est_celui_qui_agit(self):
        self.req("POST", "/nouveau", NOUVEAU, cookie=self.soum)
        self.req("POST", "/action/annuler", {"chantier_id": "3"}, cookie=self.admin)
        self.assertEqual(self.lignes(), [("Soumission", "Nouvelle soumission (nouveau client)", "client 4", "/nouveau"),
                                         ("Admin", "Chantier annulé", "chantier 3", "/action/annuler")])

    def test_libelles_et_cibles_de_quelques_routes(self):
        self.req("POST", "/nouveau", NOUVEAU, cookie=self.admin)                           # soumission 4 (client 4)
        self.req("POST", "/soumission/4/refuser", {}, cookie=self.admin)
        self.req("POST", "/soumission/4/rouvrir", {}, cookie=self.admin)
        self.req("POST", "/soumission/4/supprimer", {}, cookie=self.admin)
        self.req("POST", "/utilisateurs/2/actif", {"actif": "0"}, cookie=self.admin)
        self.req("POST", "/utilisateurs/2/actif", {"actif": "1"}, cookie=self.admin)
        self.req("POST", "/deconnexion", {}, cookie=self.admin)
        self.assertEqual([r[:3] for r in self.lignes()], [
            ("Admin", "Nouvelle soumission (nouveau client)", "client 4"), ("Admin", "Soumission refusée", "soumission 4"),
            ("Admin", "Soumission rouverte", "soumission 4"), ("Admin", "Soumission supprimée", "soumission 4"),
            ("Admin", "Compte désactivé", "compte 2"), ("Admin", "Compte réactivé", "compte 2"), ("Admin", "Déconnexion", None)])

    def test_une_action_refusee_n_ecrit_rien(self):
        self.req("POST", "/client/1/supprimer", {}, cookie=self.admin)                      # le client a des chantiers : refusé (adresse avec err=)
        self.req("POST", "/action/annuler", {"chantier_id": "1"}, cookie=self.admin)       # chantier terminé : verrouillé
        self.req("POST", "/soumission/1/refuser", {}, cookie=self.admin)                    # pas une soumission
        statut = self.req("POST", "/client/1/supprimer", {}, cookie=self.soum)[0]           # droits : refusé avant d'agir
        self.assertTrue(statut.startswith("403"), statut)
        self.assertEqual(self.lignes(), [])

    def test_une_erreur_de_saisie_n_ecrit_rien(self):
        statut, _, corps = self.req("POST", "/nouveau", {**NOUVEAU, "prix_ht": "abc"}, cookie=self.admin)        # formulaire réaffiché
        self.assertTrue(statut.startswith("200"), statut)
        self.assertIn("erreurs", corps)
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.lignes(), [])

    def test_les_pages_en_lecture_n_ecrivent_rien(self):
        for chemin in ("/", "/chantiers", "/soumissions", "/clients", "/client/1", "/chantier/3", "/journee", "/archives", "/utilisateurs",
                       "/journal", "/client/1/nouvelle-adresse", "/raccourcis", "/nouveau"):
            self.assertTrue(self.req("GET", chemin, cookie=self.admin)[0][:3] in ("200", "303"), chemin)
        self.assertEqual(self.lignes(), [])

    def test_aucune_valeur_de_formulaire_n_est_enregistree(self):
        secret = "VALEUR-SECRETE-9137"
        self.req("POST", "/client/1/nouvelle-adresse", {**ADRESSE, "adresse": secret, "notes": secret}, cookie=self.admin)
        self.req("POST", "/nouveau", {**NOUVEAU, "client_nom": secret, "description": secret}, cookie=self.admin)
        self.req("POST", "/utilisateurs/ajouter", {"nom": "Nouvelle", "mot_de_passe": secret, "role": "soumission"}, cookie=self.admin)
        self.req("POST", "/utilisateurs/2/mot-de-passe", {"mot_de_passe": secret}, cookie=self.admin)
        self.assertEqual(len(self.lignes()), 4)
        self.assertNotIn(secret, self.tout_le_journal())
        self.assertNotIn("motdepasse", self.tout_le_journal())
        self.assertEqual(self.lignes()[2], ("Admin", "Compte créé", None, "/utilisateurs/ajouter"))

    def test_le_journal_ne_se_modifie_pas(self):
        self.req("POST", "/client/1/nouvelle-adresse", ADRESSE, cookie=self.admin)
        c = self.conn()
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("UPDATE journal SET action = 'autre'")
        with self.assertRaises(sqlite3.DatabaseError):
            c.execute("DELETE FROM journal")
        c.close()
        self.assertEqual(len(self.lignes()), 1)
        self.assertEqual(self.sql("SELECT count(*) FROM journal")[0][0], self.depart + 1)

    def test_le_nom_du_compte_survit_a_la_suppression_du_compte(self):
        self.req("POST", "/client/1/nouvelle-adresse", ADRESSE, cookie=self.soum)
        c = self.conn()
        c.execute("DELETE FROM utilisateurs WHERE nom = 'Soumission'")
        c.close()
        self.assertEqual(self.lignes()[0][0], "Soumission")

    def test_une_panne_du_journal_ne_casse_pas_l_action(self):
        self.sql_ecrire("DROP TABLE journal")                                               # le journal est inutilisable
        erreur = io.StringIO()
        with contextlib.redirect_stderr(erreur):
            statut, en_tetes, _ = self.req("POST", "/client/1/nouvelle-adresse", ADRESSE, cookie=self.admin)
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/client/4?ok=nouvelle_adresse"))
        self.assertEqual(self.sql("SELECT remplace_par FROM clients WHERE id = 1"), [(4,)])   # l'action a bien eu lieu
        self.assertIn("Journal : ligne non écrite", erreur.getvalue())

    def test_pas_d_ecriture_dans_une_transaction_ouverte(self):
        c = self.conn()
        c.execute("BEGIN")
        with contextlib.redirect_stderr(io.StringIO()) as erreur:
            self.assertFalse(journal.noter(c, "Admin", "Test", None, "/x"))
        self.assertIn("transaction", erreur.getvalue())
        c.execute("ROLLBACK")
        self.assertTrue(journal.noter(c, "Admin", "Test", None, "/x"))
        c.close()

    def test_textes_nettoyes_et_limites(self):
        c = self.conn()
        journal.noter(c, "Nom\navec\x00controle" + "x" * 100, "A" * 500, "client 1\n", "/x" * 500)
        c.close()
        nom, action, cible, adresse = self.lignes()[0]
        self.assertTrue(len(nom) <= 40 and "\n" not in nom and "\x00" not in nom)
        self.assertEqual((len(action), cible, len(adresse)), (200, "client 1", 300))


class TestConnexion(BaseJournal):
    def test_connexion_reussie_refusee_et_deconnexion(self):
        self.comptes()
        self.req("POST", "/connexion", {"nom": "Admin", "mot_de_passe": "MOT-DE-PASSE-FAUX"})
        cookie = self.ouvrir("Admin", "motdepasse-admin")
        self.req("POST", "/connexion", {"nom": "Inconnu", "mot_de_passe": "motdepasse-admin"})
        self.req("POST", "/deconnexion", {}, cookie=cookie)
        self.assertEqual(self.lignes(), [("Admin", "Connexion refusée", None, "/connexion"), ("Admin", "Connexion", None, "/connexion"),
                                         ("(nom inconnu)", "Connexion refusée", None, "/connexion"), ("Admin", "Déconnexion", None, "/deconnexion")])
        tout = self.tout_le_journal()
        for mot_de_passe in ("MOT-DE-PASSE-FAUX", "motdepasse-admin"):
            self.assertNotIn(mot_de_passe, tout)

    def test_un_mot_de_passe_tape_dans_le_champ_du_nom_n_est_pas_enregistre(self):
        self.comptes()
        self.req("POST", "/connexion", {"nom": "SECRET-TAPE-AU-MAUVAIS-ENDROIT", "mot_de_passe": ""})
        self.req("POST", "/connexion", {"nom": "admin", "mot_de_passe": "faux"})            # compte existant, autre casse : le nom du compte
        self.assertEqual([r[0] for r in self.lignes()], ["(nom inconnu)", "Admin"])
        self.assertNotIn("SECRET-TAPE", self.tout_le_journal())

    def test_trop_d_essais_est_une_connexion_refusee(self):
        self.comptes()
        for _ in range(auth.MAX_ECHECS_NOM + 1):
            self.req("POST", "/connexion", {"nom": "Admin", "mot_de_passe": "faux"})
        self.assertEqual({r[1] for r in self.lignes()}, {"Connexion refusée"})
        self.assertEqual(len(self.lignes()), auth.MAX_ECHECS_NOM + 1)

    def test_sans_comptes_le_journal_fonctionne(self):
        statut, _, _ = self.req("POST", "/client/1/nouvelle-adresse", ADRESSE, ip="127.0.0.1")
        self.assertTrue(statut.startswith("303"), statut)
        self.assertEqual(self.sql("SELECT utilisateur, action FROM journal"), [(None, "Nouvelle adresse du client")])
        page = self.req("GET", "/journal", ip="127.0.0.1")[2]
        self.assertIn("Nouvelle adresse du client", page)
        self.assertIn("<td>—</td>", page)
        entete = self.req("GET", "/chantiers", ip="127.0.0.1")[2]
        self.assertNotIn("/journal", entete[entete.index("<header"):entete.index("</header>")])       # la barre du haut n'a pas de lien Journal


class TestPage(BaseJournal):
    def setUp(self):
        super().setUp()
        self.comptes()
        self.admin = self.ouvrir("Admin", "motdepasse-admin")
        self.soum = self.ouvrir("Soumission", "motdepasse-soum")

    def remplir(self, n):
        c = self.conn()
        for i in range(n):
            c.execute("INSERT INTO journal (quand, utilisateur, action, cible, adresse) VALUES (?, ?, ?, ?, '/x')",
                      (f"2026-10-{1 + i // 100:02d} 08:{i % 100 // 2:02d}:{i % 2 * 30:02d}", "Admin" if i % 2 else "Soumission",
                       f"Action {i:03d}", f"client {1 + i % 3}"))
        c.close()

    def test_reservee_a_l_administrateur(self):
        self.assertTrue(self.req("GET", "/journal", cookie=self.admin)[0].startswith("200"))
        statut, _, corps = self.req("GET", "/journal", cookie=self.soum)
        self.assertTrue(statut.startswith("403"), statut)
        self.assertNotIn("Connexion", corps)
        self.assertTrue(self.req("GET", "/journal")[0].startswith("303"))                    # sans connexion : page de connexion
        page = self.req("GET", "/chantiers", cookie=self.soum)[2]
        self.assertNotIn("/journal", page)

    def test_aucun_lien_journal_dans_la_barre_du_haut_ni_dans_le_menu_du_telephone(self):
        for cookie in (self.admin, self.soum):
            page = self.req("GET", "/chantiers", cookie=cookie)[2]
            self.assertNotIn("/journal", page[page.index("<header"):page.index("</header>")])      # la barre du haut ne bouge pas
        telephone = self.req("GET", "/chantiers", cookie=self.admin, agent=TELEPHONE)[2]
        mobile = telephone[telephone.index('<nav class="barre-mobile">'):telephone.index("</div></div>", telephone.index('class="menu-feuille"'))]
        self.assertIn("/utilisateurs", mobile)                                               # le menu du téléphone est bien celui-là
        self.assertNotIn("/journal", mobile)
        self.assertNotIn("Journal", mobile)

    def test_bouton_journal_sur_la_page_utilisateurs_pour_l_ordinateur_seulement(self):
        page = self.req("GET", "/utilisateurs", cookie=self.admin)[2]
        self.assertIn('<div class="barre pc-seul" style="margin-bottom:16px"><a class="bouton secondaire" href="/journal">Journal des modifications</a></div>', page)
        self.assertLess(page.index("<h1>Utilisateurs</h1>"), page.index('href="/journal"'))
        self.assertEqual(page.count('href="/journal"'), 1)
        self.assertEqual(self.req("GET", "/utilisateurs", cookie=self.soum)[0][:3], "403")        # le compte soumission n'a ni la page ni le bouton

    def test_retour_vers_utilisateurs_sur_la_page_du_journal(self):
        page = self.req("GET", "/journal", cookie=self.admin)[2]
        self.assertIn('<span class="pc-seul"><a class="doux" href="/utilisateurs">Utilisateurs</a></span>', page)

    def test_la_page_s_ouvre_sur_telephone(self):
        statut, _, corps = self.req("GET", "/journal", cookie=self.admin, agent=TELEPHONE)
        self.assertTrue(statut.startswith("200"), statut)
        self.assertIn("Journal des modifications", corps)

    def test_tableau_du_plus_recent_au_plus_ancien_avec_liens(self):
        self.req("POST", "/client/1/nouvelle-adresse", ADRESSE, cookie=self.admin)
        self.req("POST", "/action/annuler", {"chantier_id": "3"}, cookie=self.admin)
        c = self.conn()
        journal.noter(c, "Admin", "Fiche disparue", "client 99", "/x")
        journal.noter(c, "Admin", "Paiement supprimé", "paiement 7", "/x")
        c.close()
        page = self.req("GET", "/journal", cookie=self.admin)[2]
        for titre in ("Date et heure", "Compte", "Action", "Cible"):
            self.assertIn(f"<th>{titre}</th>", page)
        self.assertLess(page.index("Paiement supprimé"), page.index("Chantier annulé"))
        self.assertLess(page.index("Chantier annulé"), page.index("Nouvelle adresse du client"))
        self.assertIn('<a href="/client/1">client 1</a>', page)
        self.assertIn('<a href="/chantier/3">chantier 3</a>', page)
        self.assertNotIn('href="/client/99"', page)                                          # la fiche n'existe plus : texte simple
        self.assertIn("client 99", page)
        self.assertNotIn('href="/paiement/7"', page)
        self.assertIn("paiement 7", page)

    def test_pagination_par_cent_lignes(self):
        self.remplir(230)
        total = self.sql("SELECT count(*) FROM journal")[0][0]
        page1 = self.req("GET", "/journal", cookie=self.admin)[2]
        self.assertEqual(page1.count("<tr><td>"), 100)
        self.assertIn("Plus anciens", page1)
        self.assertNotIn("Plus récents", page1)
        page2 = self.req("GET", "/journal", cookie=self.admin, query={"p": "2"})[2]
        self.assertEqual(page2.count("<tr><td>"), 100)
        self.assertIn("Plus anciens", page2)
        self.assertIn("Plus récents", page2)
        page3 = self.req("GET", "/journal", cookie=self.admin, query={"p": "3"})[2]
        self.assertEqual(page3.count("<tr><td>"), total - 200)
        self.assertNotIn("Plus anciens", page3)
        self.assertIn('href="/journal?p=2"', page3)
        self.assertIn('href="/journal"', page2)                                              # retour à la première page : sans paramètre
        tous = re.findall(r"<td>(Action \d{3})</td>", page1 + page2 + page3)
        self.assertEqual(len(tous), len(set(tous)))                                          # aucune ligne en double d'une page à l'autre
        self.assertEqual(self.req("GET", "/journal", cookie=self.admin, query={"p": "abc"})[2].count("<tr><td>"), 100)

    def test_filtre_par_compte_et_par_texte(self):
        self.remplir(20)
        c = self.conn()
        journal.noter(c, None, "Action sans compte", "client 1", "/x")
        journal.noter(c, "Admin", "Remise a 100% pour l'ami", "client 2", "/x")
        c.close()
        page = self.req("GET", "/journal", cookie=self.admin)[2]
        self.assertIn('<option value="Soumission">Soumission</option>', page)
        self.assertIn('<option value="-">—</option>', page)
        pour_admin = self.req("GET", "/journal", cookie=self.admin, query={"compte": "Admin"})[2]
        self.assertIn('<option value="Admin" selected>', pour_admin)
        self.assertEqual(set(re.findall(r"<tr><td>[^<]*</td><td>([^<]*)</td>", pour_admin)), {"Admin"})
        sans = self.req("GET", "/journal", cookie=self.admin, query={"compte": "-"})[2]
        self.assertEqual(sans.count("<tr><td>"), 1)
        self.assertIn("Action sans compte", sans)
        texte = self.req("GET", "/journal", cookie=self.admin, query={"q": "action 01"})[2]
        self.assertEqual(sorted(set(re.findall(r"<td>(Action \d{3})</td>", texte))), [f"Action 01{i}" for i in range(10)])
        cible = self.req("GET", "/journal", cookie=self.admin, query={"q": "client 2", "compte": "Soumission"})[2]
        for action in re.findall(r"<td>(Action \d{3})</td>", cible):
            self.assertEqual(int(action[-3:]) % 3, 1)
            self.assertEqual(int(action[-3:]) % 2, 0)
        pourcent = self.req("GET", "/journal", cookie=self.admin, query={"q": "100%"})[2]       # % et _ cherchés tels quels
        self.assertEqual(pourcent.count("<tr><td>"), 1)
        self.assertEqual(self.req("GET", "/journal", cookie=self.admin, query={"q": "_"})[2].count("<tr><td>"), 0)
        rien = self.req("GET", "/journal", cookie=self.admin, query={"q": "zzz"})[2]
        self.assertIn("Rien à afficher", rien)

    def test_les_filtres_suivent_la_pagination(self):
        self.remplir(230)
        page = self.req("GET", "/journal", cookie=self.admin, query={"compte": "Admin", "q": "Action"})[2]
        self.assertIn('href="/journal?compte=Admin&amp;q=Action&amp;p=2"', page.replace("&p=", "&amp;p=").replace("&q=", "&amp;q="))

    def test_le_texte_du_journal_est_echappe(self):
        c = self.conn()
        journal.noter(c, "<b>Nom</b>", "<script>alert(1)</script>", "client 1", "/x")
        c.close()
        page = self.req("GET", "/journal", cookie=self.admin)[2]
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


class TestClassement(unittest.TestCase):
    def test_chaque_route_post_est_journalisee_ou_listee_comme_non_journalisee(self):
        posts = {motif for methode, motif, _ in interface.ROUTES if methode == "POST"}
        journalisees = {motif for motif, _, _ in journal.LIBELLES}
        non = set(journal.NON_JOURNALISE)
        self.assertFalse(journalisees & non, "une route ne peut pas être à la fois journalisée et non journalisée")
        for motif in sorted(posts):
            self.assertTrue(motif in journalisees or motif in non,
                            f"Route POST sans libellé de journal : {motif}. Ajoute-la à LIBELLES (outils/journal.py) avec son libellé, "
                            "ou à NON_JOURNALISE avec la raison.")
        for motif in sorted(journalisees | non):
            self.assertIn(motif, posts, f"{motif} est dans journal.py mais n'existe plus dans interface.ROUTES")
        for motif, raison in journal.NON_JOURNALISE.items():
            self.assertTrue(len(raison) > 10, motif)
        self.assertEqual(len(journal.LIBELLES), len(journalisees), "motif en double dans LIBELLES")

    def test_les_libelles_sont_en_francais_simple_sans_emoji(self):
        for motif, libelle, _ in journal.LIBELLES:
            for texte in ([libelle] if isinstance(libelle, str) else [libelle({"actif": "0"}), libelle({"actif": "1"})]):
                self.assertTrue(texte and texte[0].isupper() and len(texte) <= 60, texte)
                self.assertTrue(all(ord(c) < 0x2190 or c in "’" for c in texte), texte)

    def test_la_page_journal_est_reservee_a_l_administrateur(self):
        self.assertIn(("GET", r"^/journal$"), auth.RESERVE_ADMIN)
        self.assertFalse(auth.permis("soumission", "GET", "/journal"))
        self.assertTrue(auth.permis("admin", "GET", "/journal"))

    def test_definition_de_reussite(self):
        photo = r"^/(?:soumission|chantier)/(\d+)/photos$"
        redirection = lambda adresse: ("303 See Other", [("Location", adresse)], b"")
        self.assertTrue(journal.a_reussi(r"^/nouveau$", redirection("/client/1?ok=soumission_creee")))
        self.assertFalse(journal.a_reussi(r"^/nouveau$", redirection("/client/1?err=Refus%C3%A9")))
        self.assertFalse(journal.a_reussi(r"^/nouveau$", redirection("/client/1")))                       # redirection sans ok : rien n'a été fait
        self.assertFalse(journal.a_reussi(r"^/nouveau$", "<html>formulaire</html>"))
        self.assertFalse(journal.a_reussi(r"^/nouveau$", ("<html>introuvable</html>", 404)))
        self.assertTrue(journal.a_reussi(r"^/deconnexion$", redirection("/connexion")))
        self.assertTrue(journal.a_reussi(photo, ("200 OK", [], b'{"nom": "a.jpg"}')))
        self.assertFalse(journal.a_reussi(photo, ("409 Conflict", [], b'{"erreur": "trop"}')))
        self.assertFalse(journal.a_reussi(photo, ("200 OK", [], b'{"erreur": "x"}')))
        self.assertFalse(journal.a_reussi(r"^/nouveau$", ("200 OK", [], b'{"nom": "a.jpg"}')))


if __name__ == "__main__":
    unittest.main()
