"""Tests du noyau de données : schéma SQLite, validation d'une fiche, regroupement des clients.

    python3 -m unittest discover -s tests -v
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import fixtures  # noqa: E402
import noyau  # noqa: E402


def ligne_valide(**perso):
    base = dict(client_nom="Tremblay", client_prenom="Jean", client_telephone="450-555-0101",
                adresse="10 Rue Test", ville="Trois-Rivières", type_travaux="emondage", statut="soumission", duree_estimee_h="2")
    base.update(perso)
    return base


ALIAS = {"emondage": "emondage", "elagage": "elagage", "abattage": "abattage", "taille haie": "taille_haie"}


class TestSchema(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        self.c.executescript((RACINE / "schema" / "schema.sql").read_text(encoding="utf-8"))
        self.c.execute("PRAGMA foreign_keys = ON")
        self.c.execute("INSERT INTO clients (nom, adresse, ville) VALUES ('Test', '1 Rue A', 'Ville')")

    def refuse(self, sql, args=()):
        with self.assertRaises(sqlite3.IntegrityError, msg=sql):
            self.c.execute(sql, args)

    def test_version_et_integrite(self):
        self.assertEqual(self.c.execute("PRAGMA user_version").fetchone()[0], noyau.VERSION_SCHEMA)
        self.assertEqual(noyau.VERSION_SCHEMA, 10)
        self.assertEqual(self.c.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_dates_invalides_refusees(self):
        for d in ("2026-02-30", "2026-02-29", "2026-04-31", "2026-13-01", "14/06/2026", "2026-6-1", "2026-06-14 10:00"):
            self.refuse("INSERT INTO chantiers (client_id, statut, date_prevue) VALUES (1,'a_planifier',?)", (d,))

    def test_dates_valides_acceptees(self):
        for d in ("2028-02-29", "2026-02-28", "2026-12-31", "2026-04-30"):   # 2028 est bissextile
            self.c.execute("INSERT INTO chantiers (client_id, statut, date_prevue) VALUES (1,'a_planifier',?)", (d,))

    def test_coherence_statut(self):
        self.refuse("INSERT INTO chantiers (client_id, statut) VALUES (1,'planifie')")
        self.refuse("INSERT INTO chantiers (client_id, statut) VALUES (1,'termine')")
        self.refuse("INSERT INTO chantiers (client_id, statut) VALUES (1,'fini')")
        # anciens statuts supprimés : « Refusé » n'existe plus (on utilise « Annulé »), « Accepté » devient « À planifier »
        self.refuse("INSERT INTO chantiers (client_id, statut) VALUES (1,'refuse')")
        self.refuse("INSERT INTO chantiers (client_id, statut) VALUES (1,'accepte')")
        for statut in ("soumission", "en_attente", "a_planifier", "annule"):
            self.c.execute("INSERT INTO chantiers (client_id, statut) VALUES (1, ?)", (statut,))
        self.refuse("INSERT INTO chantiers (client_id, statut, ordre_jour) VALUES (1, 'soumission', 0)")

    def test_argent_et_durees(self):
        for prix in (450.123, -1, "abc"):
            self.refuse("INSERT INTO chantiers (client_id, prix_ht) VALUES (1,?)", (prix,))
        for duree in (0, 25, "2h"):
            self.refuse("INSERT INTO chantiers (client_id, duree_estimee_h) VALUES (1,?)", (duree,))

    def test_chemins_relatifs_stricts(self):
        for chemin in ("/abs/photos", "photos/", "photos\\2026", "photos/../x", "C:photos"):
            self.refuse("INSERT INTO chantiers (client_id, dossier_photos) VALUES (1,?)", (chemin,))
        self.c.execute("INSERT INTO chantiers (client_id, dossier_photos) VALUES (1,'photos/2026/x_y')")

    def test_clients(self):
        # rien n'est obligatoire : une soumission s'ouvre avec ce qu'on sait (l'application exige l'essentiel à l'acceptation)
        self.c.execute("INSERT INTO clients (prenom, adresse, ville) VALUES ('SansNom', '1 A', 'V')")
        self.c.execute("INSERT INTO clients (nom, adresse, ville) VALUES ('X', '', 'V')")
        self.c.execute("INSERT INTO clients (nom) VALUES ('SansAdresse')")
        self.c.execute("INSERT INTO clients (nom) VALUES (NULL)")                                     # même un client entièrement vide
        self.assertEqual(self.c.execute("SELECT adresse, ville FROM clients WHERE nom = 'SansAdresse'").fetchone(), ("", ""))
        self.refuse("INSERT INTO clients (nom, adresse, ville, telephone) VALUES ('X', '1 A', 'V', '4505550142')")
        self.refuse("INSERT INTO clients (nom, adresse, ville, courriel) VALUES ('X', '1 A', 'V', 'pas un courriel')")
        self.refuse("INSERT INTO clients (nom, adresse, ville, code_postal) VALUES ('X', '2 A', 'V', 'j7z 1a1')")
        self.refuse("INSERT INTO clients (nom, adresse, ville, latitude, longitude, geocode_statut) VALUES ('X', '3 A', 'V', 45.7, 73.9, 'manuel')")
        self.refuse("INSERT INTO clients (nom, adresse, ville, latitude, geocode_statut) VALUES ('X', '3 A', 'V', 45.7, 'manuel')")
        self.refuse("INSERT INTO clients (nom, adresse, ville, latitude, longitude) VALUES ('X', '4 A', 'V', 45.7, -73.9)")
        self.c.execute("INSERT INTO clients (nom, adresse, ville, latitude, longitude, geocode_statut) VALUES ('X', 'Lot 3', 'V', 45.65, -74.08, 'manuel')")

    def test_integrite_referentielle(self):
        self.c.execute("INSERT INTO chantiers (client_id) VALUES (1)")
        self.refuse("INSERT INTO chantier_travaux (chantier_id, type_travaux) VALUES (1, 'pizza')")
        self.refuse("INSERT INTO chantier_travaux (chantier_id, type_travaux) VALUES (99, 'emondage')")
        self.c.execute("INSERT INTO chantier_travaux (chantier_id, type_travaux, precision) VALUES (1, 'emondage', 'érable')")
        self.refuse("INSERT INTO chantier_travaux (chantier_id, type_travaux) VALUES (1, 'emondage')")   # même type deux fois
        self.refuse("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (99,'2026-06-14',5,'interac')")
        self.c.execute("INSERT INTO chantiers (client_id) VALUES (1)")
        self.refuse("DELETE FROM clients WHERE id = 1")
        self.refuse("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (1,'2026-06-14',0,'interac')")
        self.refuse("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (1,'2026-06-14',5,'bitcoin')")

    def statut(self, **chantier):
        cols = ", ".join(chantier)
        self.c.execute(f"INSERT INTO chantiers (client_id, {cols}) VALUES (1,{', '.join('?' * len(chantier))})",
                       tuple(chantier.values()))
        return self.c.execute("SELECT statut_paiement, total_ttc, paye, solde FROM v_chantiers ORDER BY chantier_id DESC LIMIT 1").fetchone()

    def test_statuts_de_paiement_calcules(self):
        self.assertEqual(self.statut(statut="soumission", prix_ht=100)[0], "sans_objet")
        self.assertEqual(self.statut(statut="a_planifier", prix_ht=100)[0], "a_venir")
        self.assertEqual(self.statut(statut="termine", date_prevue="2026-06-01")[0], "prix_manquant")
        # terminé : le client est facturé d'office, il reste à recevoir
        r = self.statut(statut="termine", date_prevue="2026-06-01", prix_ht=100, tps=5, tvq=9.98)
        self.assertEqual(r, ("a_payer", 114.98, 0, 114.98))
        cid = self.c.execute("SELECT max(id) FROM chantiers").fetchone()[0]
        self.c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?, '2026-06-05', 50.10, 'cheque')", (cid,))
        self.assertEqual(self.c.execute("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = ?", (cid,)).fetchone(), ("partiel", 64.88))
        self.c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?, '2026-06-09', 64.88, 'interac')", (cid,))
        self.assertEqual(self.c.execute("SELECT statut_paiement, solde FROM v_chantiers WHERE chantier_id = ?", (cid,)).fetchone(), ("paye", 0))

    def test_adresse_maps(self):
        self.c.execute("UPDATE clients SET adresse = '123 Rue des Érables', ville = 'Saint-Jérôme', code_postal = 'J7Z 1A1' WHERE id = 1")
        self.c.execute("INSERT INTO chantiers (client_id) VALUES (1)")
        self.assertEqual(self.c.execute("SELECT adresse_maps FROM v_chantiers").fetchone()[0],
                         "123 Rue des Érables, Saint-Jérôme, QC J7Z 1A1, Canada")
        self.c.execute("UPDATE clients SET code_postal = NULL WHERE id = 1")
        self.assertEqual(self.c.execute("SELECT adresse_maps FROM v_chantiers").fetchone()[0],
                         "123 Rue des Érables, Saint-Jérôme, QC, Canada")


class TestLecture(unittest.TestCase):
    """Validation d'une fiche (mêmes règles pour tous les formulaires)."""

    def lire(self, taxes_auto=False, **perso):
        return noyau.lire_ligne(ligne_valide(**perso), ALIAS, taxes_auto)

    def test_fiche_valide_et_formats_stricts(self):
        v, erreurs = self.lire(client_telephone="(450) 555-0142", code_postal="g8t1a1", prix_ht="1 250,00 $", duree_estimee_h="2,5")
        self.assertEqual(erreurs, [])
        self.assertEqual((v["client_telephone"], v["code_postal"], str(v["prix_ht"]), str(v["duree_estimee_h"])),
                         ("+14505550142", "G8T 1A1", "1250.00", "2.5"))

    def test_toutes_les_erreurs_sont_listees(self):
        _, erreurs = self.lire(client_telephone="12345", code_postal="ZZZ", date_soumission="14/06/2026", prix_ht="450.123",
                               dossier_photos="/etc/passwd", latitude="45.6", longitude="74.1", type_travaux="pizza",
                               statut="fini")
        for attendu in ("client_telephone", "code_postal", "date_soumission", "prix_ht", "dossier_photos",
                        "longitude", "type_travaux", "statut"):
            self.assertTrue(any(attendu in e for e in erreurs), attendu)

    def test_duree_estimee_obligatoire_apres_la_soumission(self):
        for vide in ("", None, "0", "-1", "24,5"):
            _, erreurs = self.lire(statut="a_planifier", duree_estimee_h=vide)
            self.assertTrue(any("duree_estimee_h" in e for e in erreurs), repr(vide))
        for vide in ("", None):                                        # une soumission n'exige rien
            self.assertEqual(self.lire(duree_estimee_h=vide)[1], [], repr(vide))
        for invalide in ("0", "-1", "24,5"):                           # mais une valeur écrite doit être valable
            self.assertTrue(any("duree_estimee_h" in e for e in self.lire(duree_estimee_h=invalide)[1]), invalide)

    def test_une_soumission_peut_etre_entierement_vide(self):
        v, erreurs = noyau.lire_ligne({"statut": "soumission"}, ALIAS, False)
        self.assertEqual(erreurs, [])
        self.assertEqual((v["adresse"], v["ville"], v["travaux"], v["duree_estimee_h"], v["client_nom"]), ("", "", [], None, None))
        for statut in ("en_attente", "Soumission"):
            self.assertEqual(noyau.lire_ligne({"statut": statut}, ALIAS, False)[1], [], statut)

    def test_un_chantier_exige_l_essentiel(self):
        _, erreurs = noyau.lire_ligne({"statut": "a_planifier"}, ALIAS, False)
        for attendu in ("client_nom ou client_entreprise", "adresse", "ville", "type_travaux", "duree_estimee_h"):
            self.assertTrue(any(attendu in e for e in erreurs), attendu)

    def test_les_formats_restent_verifies_dans_une_soumission(self):
        _, erreurs = noyau.lire_ligne({"statut": "soumission", "client_telephone": "123", "prix_ht": "abc"}, ALIAS, False)
        self.assertEqual(len(erreurs), 2)

    def test_modalite_un_seul_choix_parmi_cinq(self):
        for saisi, attendu in (("Comptant", "comptant"), ("chèque", "cheque"), ("INTERAC", "interac"), ("carte", "carte"), ("Autre", "autre")):
            v, erreurs = self.lire(modalite_paiement=saisi)
            self.assertEqual((erreurs, v["modalite_paiement"]), ([], attendu), saisi)
        for refuse in ("Acompte puis chèque", "chèque + comptant", "3 versements"):
            _, erreurs = self.lire(modalite_paiement=refuse)
            self.assertTrue(any("modalite_paiement" in e for e in erreurs), refuse)

    def test_taxes_auto(self):
        v, _ = self.lire(taxes_auto=True, prix_ht="2200.00")
        self.assertEqual((str(v["tps"]), str(v["tvq"])), ("110.00", "219.45"))
        v, _ = self.lire(taxes_auto=True, prix_ht="480.00", tps="0", tvq="0")           # des taxes saisies à la main sont respectées
        self.assertEqual((str(v["tps"]), str(v["tvq"])), ("0", "0"))

    def test_plusieurs_types_avec_precisions(self):
        v, erreurs = self.lire(type_travaux="Élagage: érable argenté, côté garage + taille_haie : cèdres, 35 m + abattage")
        self.assertEqual(erreurs, [])
        self.assertEqual(v["travaux"], [("elagage", "érable argenté, côté garage"), ("taille_haie", "cèdres, 35 m"), ("abattage", None)])
        for invalide in ("elagage + pizza", "elagage + élagage"):
            _, erreurs = self.lire(type_travaux=invalide)
            self.assertTrue(erreurs, invalide)
        for vide in ("", "+"):                       # aucun type : permis dans une soumission, pas dans un chantier
            self.assertEqual(self.lire(type_travaux=vide)[1], [], vide)
            self.assertTrue(self.lire(statut="a_planifier", type_travaux=vide)[1], vide)

    def test_statut_et_date(self):
        for statut in ("planifie", "termine"):
            _, erreurs = self.lire(statut=statut)
            self.assertTrue(any("date_prevue est obligatoire" in e for e in erreurs), statut)
        v, erreurs = self.lire(statut="Terminé", date_prevue="2026-06-14")
        self.assertEqual((erreurs, v["statut"], str(v["duree_reelle_h"])), ([], "termine", "2"))     # durée réelle reprise de l'estimée

    def test_les_anciens_statuts_ne_sont_plus_compris(self):
        for statut in ("accepte", "refuse"):
            self.assertTrue(self.lire(statut=statut)[1], statut)

    def test_options_du_travail(self):
        v, erreurs = self.lire(type_travaux="abattage", nacelle="oui", debarrasser_bois="non", bois_format="16 pouces")
        self.assertEqual((erreurs, v["nacelle"], v["debarrasser_bois"], v["bois_format"]), ([], 1, 0, "16_pouces"))
        _, erreurs = self.lire(debarrasser_bois="oui", bois_format="4 pieds")
        self.assertTrue(any("bois_format" in e for e in erreurs))
        _, erreurs = self.lire(bois_format="8 pieds")
        self.assertTrue(any("bois_format" in e for e in erreurs))


class TestClients(unittest.TestCase):
    """Regroupement des clients : même adresse + même nom (ou même téléphone) = même client."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        self.conn, _ = noyau.ouvrir_base(self.db)

    def tearDown(self):
        self.conn.close()
        self._tmp.cleanup()

    def client(self, **perso):
        v, erreurs = noyau.lire_ligne(ligne_valide(**perso), ALIAS, False)
        self.assertEqual(erreurs, [])
        res = noyau.Resultat()
        return noyau.trouver_ou_creer_client(self.conn, noyau.Index(self.conn), v, res), res

    def test_regroupement(self):
        a, res = self.client()
        self.assertEqual((res.clients_crees, res.clients_reutilises), (1, 0))
        b, res = self.client(adresse="10, rue TEST")                                   # même client (casse / ponctuation)
        self.assertEqual((b, res.clients_reutilises), (a, 1))
        c, _ = self.client(adresse="99 Autre Rue")                                      # autre propriété = autre fiche
        self.assertNotEqual(c, a)
        d, _ = self.client(client_nom="Tremblay-Roy", client_prenom="Lise")             # même adresse + même téléphone : même client
        self.assertEqual(d, a)
        e, _ = self.client(client_telephone="", client_nom="Dupont", client_prenom="Paul")       # autre personne, même adresse
        self.assertNotEqual(e, a)

    def test_deux_clients_sans_adresse_ne_sont_jamais_regroupes(self):
        a, _ = self.client(adresse="", ville="", client_nom="", client_prenom="", client_telephone="")
        b, res = self.client(adresse="", ville="", client_nom="", client_prenom="", client_telephone="")
        self.assertNotEqual(a, b)
        self.assertEqual(res.clients_reutilises, 0)

    def test_un_client_existant_n_est_jamais_modifie(self):
        a, _ = self.client(client_notes="Original")
        self.client(client_notes="Autre texte", client_courriel="x@example.com")
        self.assertEqual(self.conn.execute("SELECT notes, courriel FROM clients WHERE id = ?", (a,)).fetchone(), ("Original", None))

    def test_creation_d_un_chantier_avec_paiement(self):
        v, _ = noyau.lire_ligne(ligne_valide(statut="termine", date_prevue="2026-06-14", prix_ht="100", tps="5", tvq="9.98",
                                             paiement_date="2026-06-14", paiement_montant="114.98", paiement_mode="interac"), ALIAS, False)
        res = noyau.Resultat()
        client_id = noyau.trouver_ou_creer_client(self.conn, noyau.Index(self.conn), v, res)
        noyau.creer_chantier(self.conn, client_id, v, res)
        self.assertEqual((res.chantiers, res.paiements), (1, 1))
        self.assertEqual(self.conn.execute("SELECT statut_paiement, archive FROM v_chantiers").fetchone(), ("paye", 1))


class TestBaseEtVersions(unittest.TestCase):
    def test_base_d_une_version_precedente_refusee_avec_instruction(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t) / "data" / "s.db"
            db.parent.mkdir()
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE x (a)")
            c.execute("PRAGMA user_version = 6")
            c.close()
            with self.assertRaises(SystemExit) as e:
                noyau.ouvrir_base(db)
            self.assertIn("supprime simplement ce fichier", str(e.exception))

    def test_les_exemples_de_depart(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t) / "data" / "t.db"
            self.assertEqual(fixtures.creer_exemples(db), 3)
            c = sqlite3.connect(db)
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
            c.close()


if __name__ == "__main__":
    unittest.main()
