"""Tests des comptes, de la connexion et des droits (outils/auth.py).

    python3 -m unittest discover -s tests -v
"""
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import auth  # noqa: E402
import fixtures  # noqa: E402
import interface  # noqa: E402
import noyau  # noqa: E402

BUREAU = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
TELEPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148 Safari/604.1"


class BaseAuth(unittest.TestCase):
    def setUp(self):
        self.ancien = auth.ITERATIONS
        auth.ITERATIONS = 1000                       # calcul rapide dans les tests
        auth.reinitialiser_blocages()
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(lambda: setattr(auth, "ITERATIONS", self.ancien))

    def conn(self):
        c, _ = noyau.ouvrir_base(self.db)
        return c

    def sql(self, requete, args=()):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(requete, args).fetchall()
        finally:
            c.close()

    def creer(self, nom, mdp, role="soumission"):
        c = self.conn()
        try:
            self.assertEqual(auth.creer_utilisateur(c, nom, mdp, role), [])
        finally:
            c.close()

    def comptes(self):
        self.creer("Admin", "motdepasse-admin", "admin")
        self.creer("Soumission", "motdepasse-soum")

    def req(self, methode, chemin, form=None, cookie="", ip="100.64.1.2", agent=BUREAU, query=None):
        statut, en_tetes, corps = interface.repondre(self.db, methode, chemin, query or {}, form or {},
                                                     {"cookie": cookie, "ip": ip, "agent": agent, "https": False})
        return statut, dict(en_tetes), corps.decode("utf-8", "replace")

    def ouvrir(self, nom, mdp, ip="100.64.1.2"):
        statut, en_tetes, _ = self.req("POST", "/connexion", {"nom": nom, "mot_de_passe": mdp}, ip=ip)
        self.assertTrue(statut.startswith("303"), statut)
        return en_tetes["Set-Cookie"].split(";")[0]


class TestMotsDePasse(BaseAuth):
    def test_hacher_et_verifier(self):
        h = auth.hacher("secret1234")
        self.assertTrue(h.startswith("pbkdf2_sha256$1000$"))
        self.assertNotIn("secret1234", h)
        self.assertTrue(auth.verifier("secret1234", h))
        self.assertFalse(auth.verifier("secret1235", h))
        self.assertNotEqual(auth.hacher("secret1234"), h)                    # sel différent à chaque fois
        for abime in ("", "x", "a$b$c$d", "pbkdf2_sha256$x$zz$zz", None):
            self.assertFalse(auth.verifier("secret1234", abime))

    def test_validation_des_comptes(self):
        c = self.conn()
        self.assertTrue(auth.creer_utilisateur(c, "A", "motdepasse"))                # nom trop court
        self.assertTrue(auth.creer_utilisateur(c, "Alice", "abc"))                   # mot de passe trop court
        self.assertTrue(auth.creer_utilisateur(c, "Alice", "motdepasse", "dieu"))    # rôle inconnu
        self.assertEqual(auth.creer_utilisateur(c, "Alice", "1211"), [])             # 4 caractères acceptés
        self.assertTrue(auth.creer_utilisateur(c, "ALICE", "motdepasse"))            # doublon sans égard à la casse
        c.close()

    def test_le_mot_de_passe_n_est_jamais_en_clair_dans_la_base(self):
        self.creer("Admin", "tres-secret-2008", "admin")
        brut = self.db.read_bytes()
        self.assertNotIn(b"tres-secret-2008", brut)


class TestSessions(BaseAuth):
    def test_session_et_jeton_non_stocke(self):
        self.comptes()
        c = self.conn()
        uid = c.execute("SELECT id FROM utilisateurs WHERE nom = 'Admin'").fetchone()[0]
        jeton = auth.ouvrir_session(c, uid)
        self.assertEqual(auth.utilisateur_de_session(c, jeton), {"id": uid, "nom": "Admin", "role": "admin"})
        self.assertIsNone(auth.utilisateur_de_session(c, jeton + "x"))
        self.assertIsNone(auth.utilisateur_de_session(c, ""))
        c.close()
        self.assertNotIn(jeton.encode(), self.db.read_bytes())                          # seule l'empreinte est gardée

    def test_session_expiree(self):
        self.comptes()
        c = self.conn()
        uid = c.execute("SELECT id FROM utilisateurs WHERE nom = 'Admin'").fetchone()[0]
        jeton = auth.ouvrir_session(c, uid)
        c.execute("UPDATE sessions SET expire_le = '2000-01-01 00:00:00'")
        self.assertIsNone(auth.utilisateur_de_session(c, jeton))
        c.close()

    def test_compte_desactive_ou_mot_de_passe_change_coupe_les_sessions(self):
        self.comptes()
        c = self.conn()
        uid = c.execute("SELECT id FROM utilisateurs WHERE nom = 'Soumission'").fetchone()[0]
        j1, j2 = auth.ouvrir_session(c, uid), auth.ouvrir_session(c, uid)
        self.assertEqual(auth.changer_mot_de_passe(c, "Soumission", "nouveau-mdp"), [])
        self.assertIsNone(auth.utilisateur_de_session(c, j1))
        j3 = auth.ouvrir_session(c, uid)
        self.assertEqual(auth.definir_actif(c, uid, False), [])
        self.assertIsNone(auth.utilisateur_de_session(c, j3))
        self.assertIsNone(auth.utilisateur_de_session(c, j2))
        c.close()

    def test_le_dernier_administrateur_ne_peut_pas_etre_retire(self):
        self.comptes()
        c = self.conn()
        self.assertTrue(auth.definir_actif(c, "Admin", False))
        self.assertTrue(auth.changer_role(c, "Admin", "soumission"))
        self.assertEqual(auth.creer_utilisateur(c, "Deuxieme", "motdepasse", "admin"), [])
        self.assertEqual(auth.definir_actif(c, "Admin", False), [])                  # il en reste un autre
        self.assertTrue(auth.definir_actif(c, "Deuxieme", False))                    # mais pas le dernier
        c.close()


class TestBlocage(BaseAuth):
    def test_cinq_essais_rates_bloquent_puis_se_debloquent(self):
        self.comptes()
        heure = [1000.0]
        ancienne, auth._horloge = auth._horloge, lambda: heure[0]
        self.addCleanup(lambda: setattr(auth, "_horloge", ancienne))
        c = self.conn()
        for _ in range(5):
            utilisateur, message = auth.connexion(c, "Admin", "faux", "100.64.1.2")
            self.assertIsNone(utilisateur)
            self.assertIn("incorrect", message)
        utilisateur, message = auth.connexion(c, "Admin", "motdepasse-admin", "100.64.1.2")      # même le bon mot de passe est refusé
        self.assertIsNone(utilisateur)
        self.assertIn("Trop d'essais", message)
        heure[0] += auth.FENETRE_S + 5
        utilisateur, _ = auth.connexion(c, "Admin", "motdepasse-admin", "100.64.1.2")
        self.assertEqual(utilisateur["nom"], "Admin")
        c.close()

    def test_un_bon_mot_de_passe_efface_les_echecs(self):
        self.comptes()
        c = self.conn()
        for _ in range(4):
            auth.connexion(c, "Admin", "faux", "100.64.1.2")
        self.assertIsNotNone(auth.connexion(c, "Admin", "motdepasse-admin", "100.64.1.2")[0])
        for _ in range(4):
            auth.connexion(c, "Admin", "faux", "100.64.1.2")
        self.assertIsNotNone(auth.connexion(c, "Admin", "motdepasse-admin", "100.64.1.2")[0])
        c.close()

    def test_compte_inexistant_meme_message(self):
        self.comptes()
        c = self.conn()
        self.assertEqual(auth.connexion(c, "Personne", "x", "100.64.1.2")[1], auth.connexion(c, "Admin", "x", "100.64.1.3")[1])
        c.close()


class TestPorte(BaseAuth):
    def test_sans_compte_seul_cet_ordinateur_entre(self):
        self.assertTrue(self.req("GET", "/chantiers", ip="127.0.0.1")[0].startswith("200"))
        statut, _, corps = self.req("GET", "/chantiers", ip="100.64.1.2")
        self.assertTrue(statut.startswith("403"))
        self.assertIn("gerer_utilisateurs.py", corps)
        self.assertNotIn("Boucher", corps)

    def test_avec_comptes_tout_exige_la_connexion_meme_depuis_cet_ordinateur(self):
        self.comptes()
        for ip in ("127.0.0.1", "100.64.1.2"):
            for chemin in ("/", "/chantiers", "/clients", "/client/1", "/chantier/3", "/journee", "/journee.pdf", "/nouveau", "/utilisateurs"):
                statut, en_tetes, corps = self.req("GET", chemin, ip=ip)
                self.assertTrue(statut.startswith("303"), (chemin, statut))
                self.assertTrue(en_tetes["Location"].startswith("/connexion"), chemin)
                self.assertNotIn("Boucher", corps)
        avant = self.sql("SELECT count(*) FROM chantiers")
        for chemin, form in (("/nouveau", {"client_nom": "X", "adresse": "1 Rue A", "client_secteur": "centre_ville", "type_emondage": "1", "duree_estimee_h": "2"}),
                             ("/client/1/supprimer", {}), ("/chantier/3/supprimer", {}), ("/action/terminer", {"chantier_id": "3"}),
                             ("/utilisateurs/ajouter", {"nom": "Pirate", "mot_de_passe": "pirate", "role": "admin"})):
            statut, en_tetes, _ = self.req("POST", chemin, form)
            self.assertTrue(statut.startswith("303") and en_tetes["Location"].startswith("/connexion"), chemin)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), avant)
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 1"), [(1,)])
        self.assertEqual(self.sql("SELECT count(*) FROM utilisateurs WHERE nom = 'Pirate'"), [(0,)])

    def test_la_page_de_connexion_ne_montre_aucune_donnee(self):
        self.comptes()
        statut, _, corps = self.req("GET", "/connexion")
        self.assertTrue(statut.startswith("200"))
        for secret in ("Boucher", "Gagnon", "Lavoie"):
            self.assertNotIn(secret, corps)
        for present in ("Nom d'utilisateur", "Mot de passe", "Se connecter"):
            self.assertIn(present, corps)
        self.assertIn('type="password"', corps)
        self.assertNotIn("Journée", corps)                                              # pas de menu avant la connexion

    def test_suite_apres_connexion_et_pas_de_redirection_externe(self):
        self.comptes()
        statut, en_tetes, _ = self.req("POST", "/connexion", {"nom": "Admin", "mot_de_passe": "motdepasse-admin", "suite": "/clients"})
        self.assertEqual(en_tetes["Location"], "/clients")
        for mauvais in ("//evil.example.com", "https://evil.example.com", "\\\\evil"):
            _, en_tetes, _ = self.req("POST", "/connexion", {"nom": "Admin", "mot_de_passe": "motdepasse-admin", "suite": mauvais})
            self.assertEqual(en_tetes["Location"], "/", mauvais)
        statut, en_tetes, _ = self.req("GET", "/chantiers", query={"q": "lac"})
        self.assertEqual(en_tetes["Location"], "/connexion?suite=%2Fchantiers%3Fq%3Dlac")

    def test_connexion_cookie_et_deconnexion(self):
        self.comptes()
        statut, en_tetes, corps = self.req("POST", "/connexion", {"nom": "Admin", "mot_de_passe": "faux"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("incorrect", corps)
        self.assertNotIn("Set-Cookie", en_tetes)
        statut, en_tetes, _ = self.req("POST", "/connexion", {"nom": "admin", "mot_de_passe": "motdepasse-admin"})     # nom sans égard à la casse
        cookie_complet = en_tetes["Set-Cookie"]
        for attribut in ("HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=2592000"):
            self.assertIn(attribut, cookie_complet)
        cookie = cookie_complet.split(";")[0]
        self.assertTrue(self.req("GET", "/chantiers", cookie=cookie)[0].startswith("200"))
        self.assertTrue(self.req("GET", "/chantiers", cookie=cookie, ip="127.0.0.1")[0].startswith("200"))
        statut, en_tetes, _ = self.req("POST", "/deconnexion", cookie=cookie)
        self.assertIn("Max-Age=0", en_tetes["Set-Cookie"])
        self.assertTrue(self.req("GET", "/chantiers", cookie=cookie)[0].startswith("303"))                           # la session est détruite côté serveur
        self.assertEqual(self.sql("SELECT count(*) FROM sessions"), [(0,)])

    def test_cookie_bidon_ou_illisible(self):
        self.comptes()
        for cookie in ("sc_session=n-importe-quoi", "sc_session=", "n'importe quoi;;;", "\x00"):
            self.assertTrue(self.req("GET", "/chantiers", cookie=cookie)[0].startswith("303"), cookie)

    def test_compte_desactive_pendant_une_session(self):
        self.comptes()
        cookie = self.ouvrir("Soumission", "motdepasse-soum")
        c = self.conn()
        auth.definir_actif(c, "Soumission", False)
        c.close()
        self.assertTrue(self.req("GET", "/chantiers", cookie=cookie)[0].startswith("303"))
        self.assertIn("incorrect", self.req("POST", "/connexion", {"nom": "Soumission", "mot_de_passe": "motdepasse-soum"})[2])


class TestDroits(BaseAuth):
    def setUp(self):
        super().setUp()
        self.comptes()
        self.admin = self.ouvrir("Admin", "motdepasse-admin")
        self.soum = self.ouvrir("Soumission", "motdepasse-soum")

    def test_administrateur_voit_tout(self):
        for chemin in ("/", "/journee", "/chantiers", "/clients", "/client/1", "/chantier/3", "/nouveau", "/utilisateurs"):
            self.assertTrue(self.req("GET", chemin, cookie=self.admin)[0].startswith("200"), chemin)
        self.assertTrue(self.req("GET", "/journee.pdf", cookie=self.admin, query={"date": "2026-10-14"})[0].startswith("200"))
        page = self.req("GET", "/chantiers", cookie=self.admin)[2]
        for lien in ("Tableau de bord", "Journée", "Chantiers", "Clients", "Utilisateurs", "Se déconnecter"):
            self.assertIn(lien, page)

    def test_soumission_pages_permises(self):
        for chemin in ("/chantiers", "/soumissions", "/clients", "/client/1", "/chantier/3", "/nouveau", "/client/1/soumission/nouveau",
                       "/client/1/modifier", "/raccourcis"):
            self.assertTrue(self.req("GET", chemin, cookie=self.soum)[0].startswith("200"), chemin)
        page = self.req("GET", "/chantiers", cookie=self.soum)[2]
        entete = page[page.index("<header"):page.index("</header>")]
        self.assertIn('href="/chantiers"', entete)
        self.assertIn('href="/soumissions"', entete)
        self.assertIn('href="/clients"', entete)
        for absent in ('href="/journee"', 'href="/utilisateurs"', "Tableau de bord"):
            self.assertNotIn(absent, entete)
        self.assertIn("Soumission", entete)

    def test_soumission_pages_refusees(self):
        for chemin in ("/journee", "/journee.pdf", "/utilisateurs", "/tournee", "/suivi"):
            statut, _, corps = self.req("GET", chemin, cookie=self.soum)
            self.assertTrue(statut.startswith("403"), chemin)
            self.assertNotIn("Boucher", corps)
        avant = self.sql("SELECT statut FROM chantiers ORDER BY id")
        for chemin, form in (("/action/terminer", {"chantier_id": "3", "paye": "non"}), ("/action/annuler", {"chantier_id": "3"}),
                             ("/action/retirer", {"chantier_id": "3"}), ("/journee/planifier", {"date": "2026-10-20"}),
                             ("/chantier/3/paiement", {"paiement_date": "2026-10-10", "paiement_montant": "10", "paiement_mode": "interac"}),
                             ("/paiement/1/supprimer", {}), ("/chantier/3/supprimer", {}), ("/client/3/supprimer", {}),
                             ("/utilisateurs/ajouter", {"nom": "Pirate", "mot_de_passe": "pirate", "role": "admin"}),
                             ("/utilisateurs/1/actif", {"actif": "0"})):
            self.assertTrue(self.req("POST", chemin, form, cookie=self.soum)[0].startswith("403"), chemin)
        self.assertEqual(self.sql("SELECT statut FROM chantiers ORDER BY id"), avant)
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 3"), [(1,)])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(2,)])
        self.assertEqual(self.sql("SELECT count(*) FROM utilisateurs WHERE role = 'admin'"), [(1,)])

    def test_soumission_ne_voit_ni_finances_ni_boutons_dangereux(self):
        chantier = self.req("GET", "/chantier/3", cookie=self.soum)[2]
        for absent in ("Paiements", "Supprimer ce chantier", "Annuler le chantier", ">Terminer<", "Ajouter un paiement"):
            self.assertNotIn(absent, chantier, absent)
        self.assertIn("Enregistrer les modifications", chantier)
        client = self.req("GET", "/client/1", cookie=self.soum)[2]
        self.assertNotIn("Supprimer ce client", client)
        admin = self.req("GET", "/chantier/3", cookie=self.admin)[2]
        for present in ("Paiements", "Supprimer ce chantier", "Terminer"):
            self.assertIn(present, admin, present)
        self.assertIn("Supprimer ce client", self.req("GET", "/client/1", cookie=self.admin)[2])

    def test_soumission_cree_et_modifie_une_soumission(self):
        form = {"client_nom": "Tremblay", "client_prenom": "Jean", "client_telephone": "450-555-0123", "adresse": "9 Rue des Lilas",
                "client_secteur": "centre_ville", "province": "QC", "type_emondage": "1", "statut": "soumission", "duree_estimee_h": "2", "prix_ht": "300"}
        statut, en_tetes, _ = self.req("POST", "/nouveau", form, cookie=self.soum)
        self.assertTrue(statut.startswith("303"))
        self.assertRegex(en_tetes["Location"], r"^/client/\d+\?ok=soumission_creee$")
        nouveau = self.sql("SELECT max(id) FROM chantiers")[0][0]
        self.assertEqual(self.sql("SELECT statut, cree_par FROM chantiers WHERE id = ?", (nouveau,)), [("soumission", "Soumission")])   # qui l'a ouverte
        page = self.req("GET", f"/soumission/{nouveau}", cookie=self.soum)[2]
        self.assertIn("Enregistrer les modifications", page)
        self.assertIn("Accepter", page)
        statut, en_tetes, _ = self.req("POST", f"/soumission/{nouveau}/accepter", {"retour": "/soumissions"}, cookie=self.soum)    # complète : acceptée
        self.assertEqual(en_tetes["Location"], "/soumissions?ok=soumission_acceptee")
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (nouveau,)), [("a_planifier",)])

    def test_accueil_redirige_le_telephone_et_le_compte_soumission(self):
        statut, en_tetes, _ = self.req("GET", "/", cookie=self.soum)
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/soumissions"))               # le soumissionneur arrive sur ses soumissions
        self.assertTrue(self.req("GET", "/", cookie=self.admin, agent=TELEPHONE)[0].startswith("200"))     # l'administrateur a le tableau de bord sur téléphone
        self.assertTrue(self.req("GET", "/", cookie=self.admin, agent=BUREAU)[0].startswith("200"))

    def test_connecte_va_directement_a_l_accueil(self):
        statut, en_tetes, _ = self.req("GET", "/connexion", cookie=self.admin)
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/"))

    def test_page_utilisateurs(self):
        statut, en_tetes, _ = self.req("POST", "/utilisateurs/ajouter", {"nom": "Marc", "mot_de_passe": "1234", "role": "soumission"}, cookie=self.admin)
        self.assertEqual(en_tetes["Location"], "/utilisateurs?ok=utilisateur_cree")
        self.assertIn("Marc", self.req("GET", "/utilisateurs", cookie=self.admin)[2])
        statut, en_tetes, _ = self.req("POST", "/utilisateurs/ajouter", {"nom": "Marc", "mot_de_passe": "1234", "role": "soumission"}, cookie=self.admin)
        self.assertIn("err=", en_tetes["Location"])                                                      # doublon
        uid = self.sql("SELECT id FROM utilisateurs WHERE nom = 'Marc'")[0][0]
        self.req("POST", f"/utilisateurs/{uid}/mot-de-passe", {"mot_de_passe": "9999"}, cookie=self.admin)
        self.ouvrir("Marc", "9999")
        self.req("POST", f"/utilisateurs/{uid}/actif", {"actif": "0"}, cookie=self.admin)
        self.assertIn("incorrect", self.req("POST", "/connexion", {"nom": "Marc", "mot_de_passe": "9999"})[2])
        admin_id = self.sql("SELECT id FROM utilisateurs WHERE nom = 'Admin'")[0][0]
        _, en_tetes, _ = self.req("POST", f"/utilisateurs/{admin_id}/actif", {"actif": "0"}, cookie=self.admin)
        self.assertIn("dernier", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT actif FROM utilisateurs WHERE nom = 'Admin'"), [(1,)])

    def test_aucun_mot_de_passe_dans_la_page_des_utilisateurs(self):
        page = self.req("GET", "/utilisateurs", cookie=self.admin)[2]
        self.assertNotIn("pbkdf2", page)
        self.assertNotIn("motdepasse-admin", page)


class TestServeurReel(BaseAuth):
    """Parcours complet par une vraie connexion HTTP, comme un navigateur sur un téléphone (en-tête Host de Tailscale)."""

    def test_connexion_puis_acces(self):
        import http.client
        import threading
        self.comptes()
        serveur = interface.creer_serveur(self.db, 0, True)
        port = serveur.server_address[1]
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (serveur.shutdown(), serveur.server_close()))
        hote = f"ticotower.tailbb6d3b.ts.net:{port}"

        def appel(methode, chemin, corps=None, cookie=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            en_tetes = {"Host": hote, "Origin": f"http://{hote}", "User-Agent": TELEPHONE}
            if cookie:
                en_tetes["Cookie"] = cookie
            if corps is not None:
                en_tetes["Content-Type"] = "application/x-www-form-urlencoded"
            c.request(methode, chemin, body=corps, headers=en_tetes)
            r = c.getresponse()
            donnees = (r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace"))
            c.close()
            return donnees

        statut, en_tetes, _ = appel("GET", "/chantiers")
        self.assertEqual((statut, en_tetes["Location"]), (303, "/connexion?suite=%2Fchantiers"))
        statut, en_tetes, _ = appel("POST", "/connexion", "nom=Soumission&mot_de_passe=faux&suite=%2Fchantiers")
        self.assertEqual(statut, 200)
        self.assertNotIn("Set-Cookie", en_tetes)
        statut, en_tetes, _ = appel("POST", "/connexion", "nom=Soumission&mot_de_passe=motdepasse-soum&suite=%2Fchantiers")
        self.assertEqual((statut, en_tetes["Location"]), (303, "/chantiers"))
        cookie = en_tetes["Set-Cookie"].split(";")[0]
        statut, _, page = appel("GET", "/chantiers", cookie=cookie)
        self.assertEqual(statut, 200)
        self.assertIn("Boucher", page)
        self.assertIn('class="barre-mobile"', page)
        self.assertEqual(appel("GET", "/journee", cookie=cookie)[0], 403)
        self.assertEqual(appel("GET", "/", cookie=cookie)[0], 303)                                   # accueil -> Chantiers
        # un site étranger ne peut pas écrire à la place d'une personne connectée
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("POST", "/nouveau", body="client_nom=Pirate", headers={"Host": hote, "Origin": "http://evil.example.com", "Cookie": cookie})
        self.assertEqual(c.getresponse().status, 403)
        c.close()


class TestMigration(BaseAuth):
    """La migration v8 -> v9 (comptes) ; la suite v9 -> v10 est testée dans test_soumissions.py."""

    def test_la_migration_8_9_est_identique_au_schema_v9(self):
        def definitions(c):
            rows = c.execute("SELECT name, sql FROM sqlite_master WHERE name IN ('utilisateurs', 'sessions', 'idx_sessions_utilisateur')").fetchall()
            return {n: re.sub(r"\s+", " ", sql.replace("IF NOT EXISTS ", "")) for n, sql in rows}
        schema_v9 = (RACINE / "tests" / "schema_v9.sql").read_text(encoding="utf-8")
        neuve = sqlite3.connect(":memory:")
        neuve.executescript(schema_v9)
        migree = sqlite3.connect(":memory:", isolation_level=None)
        migree.executescript(schema_v9)
        migree.executescript("DROP TABLE sessions; DROP TABLE utilisateurs;")
        migree.executescript(noyau.MIGRATION_8_9.read_text(encoding="utf-8"))
        self.assertEqual(len(definitions(neuve)), 3)
        self.assertEqual(definitions(migree), definitions(neuve))
        self.assertEqual(migree.execute("PRAGMA user_version").fetchone()[0], 9)

    def test_les_versions_plus_anciennes_restent_refusees(self):
        ancien = Path(self._tmp.name) / "data" / "v7.db"
        ancien.parent.mkdir(exist_ok=True)
        c = sqlite3.connect(ancien)
        c.execute("CREATE TABLE x (a)")
        c.execute("PRAGMA user_version = 7")
        c.close()
        with self.assertRaises(SystemExit):
            noyau.ouvrir_base(ancien)


if __name__ == "__main__":
    unittest.main()
