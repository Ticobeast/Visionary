"""Tests de l'interface de saisie (outils/interface.py).

    python3 -m unittest discover -s tests -v
"""
import datetime
import re
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import importer_saisie  # noqa: E402
import interface  # noqa: E402

EXEMPLES = RACINE / "modeles" / "saisie_papier_exemples.csv"


def fiche(**perso):
    base = dict(client_nom="Roy", client_prenom="Sylvie", client_telephone="450-555-0111", client_sms_ok="1",
                adresse="22 Rue des Pins", ville="Mirabel", province="QC", type_emondage="1", statut="soumission", duree_estimee_h="2")
    base.update(perso)
    return base


class BaseInterface(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        importer_saisie.importer(EXEMPLES, self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def get(self, chemin):
        u = urllib.parse.urlsplit(chemin)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        statut, en_tetes, corps = interface.repondre(self.db, "GET", u.path, q)
        return statut, corps.decode("utf-8")

    def post(self, chemin, form):
        statut, en_tetes, corps = interface.repondre(self.db, "POST", chemin, {}, form)
        return statut, dict(en_tetes), corps.decode("utf-8")

    def sql(self, requete, args=()):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(requete, args).fetchall()
        finally:
            c.close()


class TestPages(BaseInterface):
    def test_liste_actifs_et_archives(self):
        statut, page = self.get("/chantiers")
        self.assertTrue(statut.startswith("200"))
        for nom in ("Pierre Lavoie", "Luc Boucher"):
            self.assertIn(nom, page)
        self.assertNotIn("Marie Gagnon", page)                  # terminé ET payé : archivé automatiquement
        self.assertIn("Actifs (2)", page)
        self.assertIn("Archives (1)", page)
        self.assertIn("à facturer", page)
        self.assertIn("1 437,19 $", page)                       # Lavoie : 1250 + taxes, non facturé
        archives = self.get("/chantiers?vue=archives")[1]
        self.assertIn("Marie Gagnon", archives)
        self.assertNotIn("Pierre Lavoie", archives)
        self.assertNotIn("Luc Boucher", archives)

    def test_un_chantier_termine_et_paye_rejoint_les_archives_tout_seul(self):
        self.assertIn("Pierre Lavoie", self.get("/chantiers")[1])
        self.post("/chantier/2/facturer", {"date_facture": "2026-10-02"})
        self.assertIn("Pierre Lavoie", self.get("/chantiers")[1])               # facturé, pas encore payé : reste actif
        self.post("/chantier/2/paiement", {"paiement_date": "2026-10-03", "paiement_montant": "1437,19", "paiement_mode": "cheque"})
        self.assertNotIn("Pierre Lavoie", self.get("/chantiers")[1])
        self.assertIn("Pierre Lavoie", self.get("/chantiers?vue=archives")[1])
        self.assertIn("Archivé", self.get("/chantier/2")[1])
        # un chantier payé mais pas terminé n'est PAS archivé
        self.post("/chantier/3/paiement", {"paiement_date": "2026-10-03", "paiement_montant": "2029,45", "paiement_mode": "cheque"})
        self.assertIn("Luc Boucher", self.get("/chantiers")[1])

    def test_filtres_et_recherche_sans_accent(self):
        self.assertNotIn("Luc Boucher", self.get("/chantiers?paiement=non_facture")[1])
        self.assertIn("Pierre Lavoie", self.get("/chantiers?paiement=non_facture")[1])
        self.assertIn("Luc Boucher", self.get("/chantiers?statut=planifie")[1])
        self.assertNotIn("Pierre Lavoie", self.get("/chantiers?statut=planifie")[1])
        self.assertIn("Marie Gagnon", self.get("/chantiers?vue=archives&q=erables")[1])    # « Érables » trouvé sans accent
        self.assertIn("Marie Gagnon", self.get("/chantiers?vue=archives&q=450-555-0142")[1])
        self.assertNotIn("Pierre Lavoie", self.get("/chantiers?q=boucher")[1])

    def test_pages_de_detail_et_introuvable(self):
        statut, page = self.get("/chantier/1")
        self.assertIn("123 Rue des Érables, Saint-Jérôme, QC J7Z 1A1", page)
        self.assertIn("google.com/maps/search", page)
        self.assertIn("551,88 $", page)
        self.assertTrue(self.get("/chantier/999")[0].startswith("404"))
        self.assertTrue(self.get("/nimporte")[0].startswith("404"))

    def test_recherche_de_client_existant(self):
        self.assertIn('href="/client/2"', self.get("/nouveau?q=lavoie")[1])           # on passe par la fiche du client
        self.assertIn("Aucun client trouvé", self.get("/nouveau?q=zzz")[1])
        statut, en_tetes, _ = interface.repondre(self.db, "GET", "/nouveau", {"client_id": "2"})
        self.assertEqual((statut[:3], dict(en_tetes)["Location"]), ("303", "/client/2"))

    def test_html_est_echappe(self):
        self.post("/nouveau", fiche(client_nom="<script>alert(1)</script>", description="<img src=x onerror=alert(2)>"))
        for chemin in ("/chantiers", "/chantier/4", "/nouveau?q=script", "/clients", "/client/4", "/"):
            page = self.get(chemin)[1]
            self.assertNotIn("<script>alert", page, chemin)
            self.assertNotIn("<img src=x", page, chemin)
        self.assertIn("&lt;script&gt;", self.get("/chantiers")[1])
        self.assertIn("&lt;script&gt;", self.get("/clients")[1])


class TestCreation(BaseInterface):
    def test_creation_complete(self):
        statut, en_tetes, _ = self.post("/nouveau", fiche(
            date_prevue="2026-10-20", statut="planifie", duree_estimee_h="2,5",
            prix_ht="300,00", taxes_auto="1", code_postal="j7j1a1", dossier_photos="photos/2026/2026-10-20_roy",
            paiement_date="2026-10-01", paiement_montant="100", paiement_mode="interac"))
        self.assertTrue(statut.startswith("303"))
        self.assertEqual(en_tetes["Location"], "/chantier/4?ok=cree")
        self.assertEqual(self.sql("SELECT telephone, code_postal, geocode_statut FROM clients WHERE nom = 'Roy'"),
                         [("+14505550111", "J7J 1A1", "a_faire")])
        self.assertEqual(self.sql("SELECT statut, date_prevue, ordre_jour, duree_estimee_h, prix_ht, tps, tvq FROM chantiers WHERE id = 4"),
                         [("planifie", "2026-10-20", 1, 2.5, 300.0, 15.0, 29.93)])
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = 4"), [("partiel", 244.93)])
        self.assertIn("Chantier créé", self.get("/chantier/4?ok=cree")[1])

    def test_erreurs_gardent_les_valeurs_et_n_ecrivent_rien(self):
        statut, _, page = self.post("/nouveau", fiche(date_prevue="14/06/2026", client_telephone="123",
                                                      client_nom="Nom gardé", statut="planifie"))
        self.assertTrue(statut.startswith("200"))
        self.assertIn("À corriger", page)
        self.assertIn("AAAA-MM-JJ", page)
        self.assertIn('value="Nom gardé"', page)
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_refus_de_la_base_est_affiche(self):
        _, _, page = self.post("/nouveau", fiche(date_facture="2026-06-14"))   # facture sans prix
        self.assertIn("Refusé par la base", page)
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])      # transaction annulée : pas de client orphelin

    def test_meme_adresse_reutilise_le_client(self):
        _, en_tetes, _ = self.post("/nouveau", fiche(client_nom="Gagnon", client_prenom="Marie", adresse="123 rue des erables",
                                                     ville="Saint-Jerome", type_emondage="", type_elagage="1"))
        self.assertEqual(en_tetes["Location"], "/chantier/4?ok=cree_reutilise")
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id = 4"), [(1,)])


class TestModification(BaseInterface):
    """Chantier 3 (Boucher) : planifié, donc modifiable. Les chantiers 1 et 2 sont terminés : verrouillés."""

    def formulaire_de(self, chantier_id):
        """Valeurs du formulaire d'édition, telles que le navigateur les renverrait."""
        conn, _ = interface.ouvrir_base(self.db)
        try:
            valeurs, _ = interface.valeurs_chantier(conn, chantier_id)
        finally:
            conn.close()
        valeurs.pop("client_id", None)
        return valeurs

    def tout(self):
        return self.sql("SELECT * FROM clients ORDER BY id") + self.sql("SELECT * FROM chantiers ORDER BY id")

    def test_edition_sans_changement_ne_change_rien(self):
        avant = self.tout()
        statut, en_tetes, _ = self.post("/chantier/3", self.formulaire_de(3))
        self.assertEqual(en_tetes["Location"], "/chantier/3?ok=maj")
        self.assertEqual(self.tout(), avant)

    def test_le_client_est_en_lecture_seule_sur_la_page_du_chantier(self):
        page = self.get("/chantier/3")[1]
        formulaire = page[page.index('<form method="post" action="/chantier/3">'):page.index("</form>", page.index('<form method="post" action="/chantier/3">'))]
        for interdit in ("client_nom", "client_prenom", "client_telephone", "client_courriel", "adresse", "ville", "code_postal", "client_sms_ok"):
            self.assertNotIn(f'name="{interdit}"', formulaire)
        self.assertIn("Lecture seule", page)
        self.assertIn("850 Boulevard du Lac", page)                                   # mais le client est bien affiché
        self.assertIn('href="/client/3/modifier"', page)                              # seul point d'entrée : la fiche client

    def test_le_serveur_ignore_toute_modification_du_client_envoyee_au_chantier(self):
        avant = self.sql("SELECT * FROM clients ORDER BY id")
        self.post("/chantier/3", {**self.formulaire_de(3), "client_nom": "PIRATE", "client_prenom": "X", "adresse": "1 Rue Fausse",
                                  "ville": "Ailleurs", "client_telephone": "514-555-0199", "code_postal": "H0H 0H0",
                                  "client_sms_ok": "0", "latitude": "45.5", "longitude": "-73.5", "client_id": "1"})
        self.assertEqual(self.sql("SELECT * FROM clients ORDER BY id"), avant)
        self.assertEqual(self.sql("SELECT client_id FROM chantiers WHERE id = 3"), [(3,)])

    def test_le_recap_apres_enregistrement_montre_le_client_verrouille(self):
        _, en_tetes, _ = self.post("/nouveau", fiche())
        page = self.get(en_tetes["Location"])[1]
        self.assertIn("Lecture seule", page)
        self.assertNotIn('name="client_nom"', page)
        self.assertIn("Sylvie Roy", page)
        self.assertIn("22 Rue des Pins", page)

    def test_le_client_se_modifie_depuis_sa_fiche_seulement(self):
        self.post("/client/3/modifier", {"client_nom": "Boucher", "client_prenom": "Luc", "client_entreprise": "Syndicat Les Jardins du Lac",
                                         "client_telephone": "+14505550163", "adresse": "99 Chemin Neuf", "ville": "Blainville",
                                         "province": "QC", "code_postal": "J7C 2X1"})
        self.assertIn("99 Chemin Neuf", self.get("/chantier/3")[1])
        self.assertEqual(self.sql("SELECT latitude, longitude, geocode_statut FROM clients WHERE id = 3"), [(None, None, "a_faire")])

    def test_passer_a_termine_exige_la_date(self):
        self.post("/nouveau", fiche(statut="a_planifier"))                        # chantier #4, sans date
        f = {**self.formulaire_de(4), "statut": "termine"}
        _, _, page = self.post("/chantier/4", f)
        self.assertIn("date_prevue est obligatoire", page)
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = 4"), [("a_planifier",)])
        self.post("/chantier/4", {**f, "date_prevue": "2026-10-14", "duree_reelle_h": "6,5"})
        self.assertEqual(self.sql("SELECT statut, date_prevue, duree_reelle_h FROM chantiers WHERE id = 4"),
                         [("termine", "2026-10-14", 6.5)])

    def test_duree_reelle_reprend_la_duree_estimee_a_la_cloture(self):
        self.post("/nouveau", fiche(statut="a_planifier", duree_estimee_h="3,5"))
        self.post("/chantier/4", {**self.formulaire_de(4), "statut": "termine", "date_prevue": "2026-10-14"})   # durée réelle laissée vide
        self.assertEqual(self.sql("SELECT statut, duree_estimee_h, duree_reelle_h FROM chantiers WHERE id = 4"), [("termine", 3.5, 3.5)])

    def test_duree_reelle_cachee_a_la_creation(self):
        self.assertNotIn('name="duree_reelle_h"', self.get("/nouveau")[1])
        self.assertIn('name="duree_estimee_h"', self.get("/nouveau")[1])
        self.assertIn(f'name="date_soumission" type="date" value="{datetime.date.today().isoformat()}"', self.get("/nouveau")[1])

    def test_duree_estimee_obligatoire(self):
        for duree in ("", "0", "25"):
            _, _, page = self.post("/nouveau", fiche(duree_estimee_h=duree))
            self.assertIn("duree_estimee_h", page, duree)
        _, _, page = self.post("/chantier/3", {**self.formulaire_de(3), "duree_estimee_h": ""})
        self.assertIn("duree_estimee_h", page)
        self.assertEqual(self.sql("SELECT duree_estimee_h FROM chantiers WHERE id = 3"), [(6.0,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_une_seule_date_changer_le_jour_met_a_jour_la_date_prevue(self):
        f = self.formulaire_de(3)
        self.post("/chantier/3", {**f, "date_prevue": "2026-10-16"})          # le chantier est déplacé
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = 3"), [("planifie", "2026-10-16")])
        self.post("/chantier/3", {**f, "date_prevue": "2026-10-16", "statut": "termine"})   # puis il est fait ce jour-là
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = 3"), [("termine", "2026-10-16")])
        self.assertNotIn("Date réalisée", self.get("/chantier/3")[1])

    def test_plusieurs_types_avec_precision_et_une_seule_description(self):
        self.post("/chantier/3", {**self.formulaire_de(3), "type_elagage": "1", "precision_elagage": "érable côté garage",
                                  "precision_taille_haie": "cèdres, 35 m", "precision_abattage": "frêne mort"})   # précision seule : type coché d'office
        types = dict(self.sql("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 3"))
        self.assertEqual(types["elagage"], "érable côté garage")
        self.assertEqual(types["taille_haie"], "cèdres, 35 m")
        self.assertEqual(types["abattage"], "frêne mort")
        detail = self.get("/chantier/3")[1]
        self.assertIn("Élagage : érable côté garage", detail)
        self.assertIn('name="precision_elagage" value="érable côté garage"', detail)
        self.assertIn('name="type_elagage" value="1" checked', detail)
        self.assertEqual(detail.count('name="description"'), 1)           # une seule description
        self.assertNotIn('name="notes"', detail)                          # plus de notes de chantier

    def test_au_moins_un_type_de_travaux(self):
        _, _, page = self.post("/nouveau", fiche(type_emondage=""))
        self.assertIn("au moins un type de travaux", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_la_base_ouverte_est_toujours_affichee(self):
        self.assertIn("BASE D’ESSAI : t.db", self.get("/")[1])       # t.db n'est pas la vraie base

    def test_modalite_unique_parmi_cinq(self):
        page = self.get("/nouveau")[1]
        options = re.findall(r'<option value="([a-z]*)"', page[page.index('name="modalite_paiement"'):])[:6]
        self.assertEqual(options, ["", "comptant", "cheque", "interac", "carte", "autre"])
        _, _, page = self.post("/nouveau", fiche(modalite_paiement="3 versements"))
        self.assertIn("modalite_paiement", page)
        _, en_tetes, _ = self.post("/nouveau", fiche(modalite_paiement="carte"))
        self.assertIn("ok=cree", en_tetes["Location"])


class TestTermineVerrouille(BaseInterface):
    """Un chantier Terminé est définitivement en lecture seule (interface ET base de données)."""

    def test_page_en_lecture_seule(self):
        page = self.get("/chantier/2")[1]
        self.assertIn("verrouillé en lecture seule", page)
        self.assertNotIn('<form method="post" action="/chantier/2">', page)
        self.assertNotIn("Supprimer ce chantier", page)
        self.assertNotIn('name="statut"', page)
        self.assertIn("Dupliquer le chantier", page)
        self.assertIn("Marquer comme facturé", page)                       # la facturation reste possible
        self.assertIn("Ajouter le paiement", page)                         # et l'encaissement

    def test_toute_modification_par_le_serveur_est_refusee(self):
        avant = self.sql("SELECT * FROM chantiers WHERE id = 2")
        conn, _ = interface.ouvrir_base(self.db)
        valeurs, _ = interface.valeurs_chantier(conn, 2)
        conn.close()
        valeurs.update(prix_ht="1.00", description="piraté", statut="planifie", date_prevue="2026-11-01", client_sms_ok="1")
        _, _, page = self.post("/chantier/2", valeurs)
        self.assertIn("verrouillé", page)
        self.assertEqual(self.sql("SELECT * FROM chantiers WHERE id = 2"), avant)
        self.assertEqual(self.post("/chantier/2/supprimer", {})[0][:3], "200")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE id = 2"), [(1,)])

    def test_actions_rapides_ne_rouvrent_pas_un_termine(self):
        for statut in ("planifie", "a_planifier", "annule", "soumission"):
            _, en_tetes, _ = self.post("/action/statut", {"chantier_id": "2", "statut": statut, "date_prevue": "2026-11-01", "retour": "/"})
            self.assertIn("err=", en_tetes["Location"], statut)
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = 2"), [("termine",)])

    def test_la_base_elle_meme_refuse(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        for requete in ("UPDATE chantiers SET statut = 'planifie' WHERE id = 2", "UPDATE chantiers SET prix_ht = 1 WHERE id = 2",
                        "UPDATE chantiers SET description = 'x' WHERE id = 2", "UPDATE chantiers SET duree_reelle_h = 9 WHERE id = 2",
                        "DELETE FROM chantiers WHERE id = 2", "DELETE FROM chantier_travaux WHERE chantier_id = 2",
                        "UPDATE chantier_travaux SET precision = 'x' WHERE chantier_id = 2"):
            with self.assertRaises(sqlite3.IntegrityError, msg=requete):
                c.execute(requete)
        c.execute("UPDATE chantiers SET numero_facture = '2026-099', date_facture = '2026-10-02' WHERE id = 2")   # facturer : permis
        c.close()


class TestPaiementsEtSuppression(BaseInterface):
    def test_ajouter_et_supprimer_un_paiement(self):
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 2"), [("non_facture",)])
        statut, en_tetes, _ = self.post("/chantier/2/paiement", {"paiement_date": "2026-10-02", "paiement_montant": "1 437,19",
                                                                  "paiement_mode": "cheque", "paiement_reference": "#0418"})
        self.assertEqual(en_tetes["Location"], "/chantier/2?ok=paiement")
        self.assertEqual(self.sql("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = 2"), [("paye", 0.0)])
        pid = self.sql("SELECT max(id) FROM paiements")[0][0]
        self.post(f"/paiement/{pid}/supprimer", {})
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = 2"), [("non_facture",)])

    def test_paiement_invalide(self):
        for form in ({"paiement_date": "2026-10-02", "paiement_montant": "", "paiement_mode": "interac"},
                     {"paiement_date": "14/10/2026", "paiement_montant": "50", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "0", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "-5", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "12,345", "paiement_mode": "interac"},
                     {"paiement_date": "2026-10-02", "paiement_montant": "50", "paiement_mode": "bitcoin"}):
            statut, _, page = self.post("/chantier/2/paiement", form)
            self.assertTrue(statut.startswith("200"), form)
            self.assertIn("erreurs", page)
        self.assertEqual(self.sql("SELECT count(*) FROM paiements"), [(2,)])

    def test_jamais_de_solde_negatif(self):
        # Lavoie doit 1 437,19 $ : un paiement de 1 437,20 $ est refusé, 1 437,19 $ est accepté
        statut, _, page = self.post("/chantier/2/paiement", {"paiement_date": "2026-10-02", "paiement_montant": "1437,20", "paiement_mode": "cheque"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("erreurs", page)
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 2"), [(0,)])
        self.post("/chantier/2/paiement", {"paiement_date": "2026-10-02", "paiement_montant": "1437,19", "paiement_mode": "cheque"})
        self.assertEqual(self.sql("SELECT solde FROM v_chantiers WHERE chantier_id = 2"), [(0.0,)])
        _, _, page = self.post("/chantier/2/paiement", {"paiement_date": "2026-10-03", "paiement_montant": "0,01", "paiement_mode": "cheque"})
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 2"), [(1,)])
        self.assertEqual(self.sql("SELECT min(solde) FROM v_chantiers"), [(0.0,)])

    def test_action_rapide_encaisser_ne_depasse_pas_le_solde(self):
        _, en_tetes, _ = self.post("/action/encaisser", {"chantier_id": "3", "montant": "2100", "mode": "interac", "retour": "/"})
        self.assertIn("err=", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 3"), [(1,)])

    def test_la_base_refuse_un_solde_negatif(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (3, '2026-10-02', 2100, 'interac')")
        with self.assertRaises(sqlite3.IntegrityError):                       # augmenter un paiement existant
            c.execute("UPDATE paiements SET montant = 9999 WHERE chantier_id = 3")
        with self.assertRaises(sqlite3.IntegrityError):                       # baisser le prix sous ce qui est déjà payé
            c.execute("UPDATE chantiers SET prix_ht = 100, tps = 0, tvq = 0 WHERE id = 3")
        c.close()

    def test_supprimer_un_chantier_et_son_client_orphelin(self):
        _, _, page = self.post("/chantier/3/supprimer", {})                 # a un paiement : refusé
        self.assertIn("a des paiements", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        self.post("/nouveau", fiche())                                      # #4 : aucun paiement, non terminé
        statut, en_tetes, _ = self.post("/chantier/4/supprimer", {})
        self.assertEqual(en_tetes["Location"], "/chantiers?ok=supprime")
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE nom = 'Roy'"), [(0,)])

    def test_client_avec_autre_chantier_n_est_pas_supprime(self):
        self.post("/client/3/chantier/nouveau", {"type_emondage": "1", "duree_estimee_h": "2"})      # #4 sur le client de Boucher
        self.post("/chantier/4/supprimer", {})
        self.assertEqual(self.sql("SELECT count(*) FROM clients WHERE id = 3"), [(1,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])


class TestDuplication(BaseInterface):
    def test_dupliquer_un_chantier_termine(self):
        page = self.get("/chantier/1/dupliquer")[1]
        self.assertIn('name="prix_ht" type="text" value="480.00"', page)
        self.assertIn('name="duree_estimee_h"', page)
        statut, en_tetes, _ = self.post("/chantier/1/dupliquer", {"prix_ht": "520,00", "avec_taxes": "1", "duree_estimee_h": "3,5", "description": "Taille annuelle"})
        self.assertEqual(en_tetes["Location"], "/chantier/4?ok=duplique")
        aujourdhui = datetime.date.today().isoformat()
        self.assertEqual(self.sql("SELECT client_id, statut, date_soumission, date_prevue, ordre_jour, duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq,"
                                  " modalite_paiement, numero_facture, date_facture, description FROM chantiers WHERE id = 4"),
                         [(1, "soumission", aujourdhui, None, None, 3.5, None, 520.0, 26.0, 51.87, "interac", None, None, "Taille annuelle")])
        self.assertEqual(self.sql("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 4"), [("taille_haie", "cèdres côté rue et côté voisin, environ 35 m, hauteur 2 m")])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = 4"), [(0,)])
        self.assertEqual(self.sql("SELECT statut, prix_ht FROM chantiers WHERE id = 1"), [("termine", 480.0)])      # l'original n'a pas bougé
        self.assertIn("Dupliquer le chantier", self.get("/chantier/4")[1])

    def test_la_duree_est_obligatoire_et_le_prix_valide(self):
        for form in ({"prix_ht": "520", "duree_estimee_h": "0"}, {"prix_ht": "520", "duree_estimee_h": "25"}, {"prix_ht": "abc", "duree_estimee_h": "2"}, {"prix_ht": "-5", "duree_estimee_h": "2"}):
            statut, _, page = self.post("/chantier/1/dupliquer", form)
            self.assertTrue(statut.startswith("200"), form)
            self.assertIn("erreurs", page)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_duree_vide_reprend_celle_du_chantier_d_origine(self):
        self.post("/chantier/1/dupliquer", {"prix_ht": "", "duree_estimee_h": ""})
        self.assertEqual(self.sql("SELECT duree_estimee_h, prix_ht FROM chantiers WHERE id = 4"), [(3.0, 480.0)])

    def test_dupliquer_chantier_inconnu(self):
        self.assertTrue(self.get("/chantier/99/dupliquer")[0].startswith("404"))
        self.assertTrue(self.post("/chantier/99/dupliquer", {"duree_estimee_h": "2"})[0].startswith("404"))


class TestServeurReel(BaseInterface):
    def setUp(self):
        super().setUp()
        self.serveur = interface.creer_serveur(self.db, 0)       # port libre choisi par le système
        self.port = self.serveur.server_address[1]
        self.serveur.RequestHandlerClass.hotes_autorises = (f"127.0.0.1:{self.port}", f"localhost:{self.port}")
        threading.Thread(target=self.serveur.serve_forever, daemon=True).start()

    def tearDown(self):
        self.serveur.shutdown()
        self.serveur.server_close()
        super().tearDown()

    def requete(self, chemin, donnees=None, en_tetes=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{chemin}", method="POST" if donnees is not None else "GET",
                                     data=urllib.parse.urlencode(donnees).encode() if donnees is not None else None,
                                     headers=en_tetes or {})

        class PasDeRedirection(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        try:
            r = urllib.request.build_opener(PasDeRedirection).open(req)
            return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    def test_get_et_post_legitimes(self):
        statut, _, page = self.requete("/chantiers")
        self.assertEqual(statut, 200)
        self.assertIn("Luc Boucher", page)
        statut, entetes, _ = self.requete("/nouveau", fiche(), {"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(statut, 303)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(4,)])

    def test_post_venant_d_un_autre_site_est_refuse(self):
        statut, _, _ = self.requete("/nouveau", fiche(), {"Origin": "https://site-malveillant.example"})
        self.assertEqual(statut, 403)
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers"), [(3,)])

    def test_hote_inattendu_est_refuse(self):                     # protection « DNS rebinding »
        statut, _, _ = self.requete("/", en_tetes={"Host": "pirate.example"})
        self.assertEqual(statut, 403)


if __name__ == "__main__":
    unittest.main()
