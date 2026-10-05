"""Tests du noyau de données : schéma SQLite + import de la feuille de saisie.

    python3 -m unittest discover -s tests -v
"""
import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import importer_saisie as imp  # noqa: E402

EXEMPLES = RACINE / "modeles" / "saisie_papier_exemples.csv"
VIDE = RACINE / "modeles" / "saisie_papier_vide.csv"


def ligne_valide(**perso):
    base = dict(client_nom="Tremblay", client_prenom="Jean", client_telephone="450-555-0101",
                adresse="10 Rue Test", ville="Blainville", type_travaux="emondage", statut="soumission")
    base.update(perso)
    return base


class BaseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self._tmp.name)
        self.db = self.dossier / "data" / "test.db"

    def tearDown(self):
        self._tmp.cleanup()

    def ecrire_csv(self, lignes, nom="lot.csv", delimiteur=",", encodage="utf-8-sig", colonnes=None):
        chemin = self.dossier / nom
        colonnes = colonnes or imp.COLONNES
        with open(chemin, "w", encoding=encodage, newline="") as f:
            w = csv.DictWriter(f, fieldnames=colonnes, delimiter=delimiteur, lineterminator="\n")
            w.writeheader()
            for l in lignes:
                w.writerow(l)
        return chemin

    def requete(self, sql, args=()):
        c = sqlite3.connect(self.db)
        try:
            return c.execute(sql, args).fetchall()
        finally:
            c.close()


class TestGabarits(unittest.TestCase):
    def test_en_tetes_synchronises_avec_le_script(self):
        for fichier in (EXEMPLES, VIDE):
            with open(fichier, encoding="utf-8-sig", newline="") as f:
                self.assertEqual(next(csv.reader(f)), imp.COLONNES, fichier.name)


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
        self.assertEqual(self.c.execute("PRAGMA user_version").fetchone()[0], 4)
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
        self.refuse("INSERT INTO chantiers (client_id, date_facture) VALUES (1,'2026-06-14')")

    def test_chemins_relatifs_stricts(self):
        for chemin in ("/abs/photos", "photos/", "photos\\2026", "photos/../x", "C:photos"):
            self.refuse("INSERT INTO chantiers (client_id, dossier_photos) VALUES (1,?)", (chemin,))
        self.c.execute("INSERT INTO chantiers (client_id, dossier_photos) VALUES (1,'photos/2026/x_y')")

    def test_clients(self):
        self.refuse("INSERT INTO clients (prenom, adresse, ville) VALUES ('SansNom', '1 A', 'V')")
        self.refuse("INSERT INTO clients (nom, adresse, ville) VALUES ('X', '', 'V')")
        self.refuse("INSERT INTO clients (nom, ville) VALUES ('X', 'V')")  # adresse obligatoire
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
        r = self.statut(statut="termine", date_prevue="2026-06-01", prix_ht=100, tps=5, tvq=9.98)
        self.assertEqual(r, ("non_facture", 114.98, 0, 114.98))
        cid = self.c.execute("SELECT max(id) FROM chantiers").fetchone()[0]
        self.c.execute("UPDATE chantiers SET date_facture = '2026-06-02' WHERE id = ?", (cid,))
        self.assertEqual(self.c.execute("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = ?", (cid,)).fetchone()[0], "a_payer")
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


class TestImportExemples(BaseTest):
    def test_import_des_exemples(self):
        res = imp.importer(EXEMPLES, self.db)
        self.assertEqual(res.erreurs, [])
        self.assertEqual((res.chantiers, res.clients_crees, res.paiements), (3, 3, 2))
        statuts = dict(self.requete("SELECT nom, statut_paiement FROM v_chantiers"))
        self.assertEqual(statuts, {"Gagnon": "paye", "Lavoie": "non_facture", "Boucher": "partiel"})
        self.assertEqual(self.requete("SELECT solde FROM v_chantiers WHERE nom = 'Boucher'"), [(2029.45,)])
        self.assertEqual(self.requete("SELECT geocode_statut FROM clients ORDER BY id"), [("a_faire",), ("manuel",), ("a_faire",)])
        # La requête que le script d'itinéraire (étape 2) fera :
        jour = self.requete("SELECT client_nom_complet, adresse_maps, duree_estimee_h, dossier_photos FROM v_chantiers"
                            " WHERE date_prevue = '2026-10-14' AND statut = 'planifie'")
        self.assertEqual(jour, [("Luc Boucher", "850 Boulevard du Lac, Blainville, QC J7C 2X1, Canada", 6.0,
                                 "photos/2026/2026-10-14_jardins-du-lac")])
        c = sqlite3.connect(self.db)
        self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
        c.close()

    def test_relancer_le_meme_fichier_ne_duplique_rien(self):
        imp.importer(EXEMPLES, self.db)
        res = imp.importer(EXEMPLES, self.db)
        self.assertEqual((res.chantiers, res.doublons, res.paiements), (0, 3, 0))
        self.assertEqual(self.requete("SELECT count(*) FROM chantiers"), [(3,)])
        self.assertEqual(self.requete("SELECT count(*) FROM clients"), [(3,)])
        self.assertEqual(self.requete("SELECT count(*) FROM paiements"), [(2,)])
        self.assertIsNone(res.sauvegarde)  # rien d'écrit -> pas de sauvegarde inutile

    def test_sauvegarde_avant_ecriture_et_jamais_ecrasee(self):
        imp.importer(EXEMPLES, self.db)
        dossier = self.db.parent / "sauvegardes"
        for i in range(3):  # trois imports réels dans la même seconde
            res = imp.importer(self.ecrire_csv([ligne_valide(adresse=f"{i} Rue Sauvegarde")], nom=f"l{i}.csv"), self.db)
            self.assertTrue(res.sauvegarde.exists())
        self.assertEqual(len(list(dossier.glob("*_avant_import*.db"))), 3)
        c = sqlite3.connect(sorted(dossier.glob("*_avant_import*.db"))[0])  # la plus ancienne = état avant le 1er lot
        self.assertEqual(c.execute("SELECT count(*) FROM chantiers").fetchone()[0], 3)
        c.close()

    def test_ligne_modifiee_deja_importee_est_signalee_pas_avalee(self):
        imp.importer(self.ecrire_csv([ligne_valide(prix_ht="100.00")]), self.db)
        modifiee = ligne_valide(prix_ht="100.00", statut="a_planifier", date_facture="2026-06-14",
                                paiement_date="2026-06-14", paiement_montant="50", paiement_mode="interac")
        res = imp.importer(self.ecrire_csv([modifiee]), self.db)
        self.assertEqual((res.chantiers, res.doublons, res.erreurs), (0, 1, []))
        message = " ".join(res.avertissements)
        for champ in ("statut", "date_facture", "paiement"):
            self.assertIn(champ, message)
        self.assertEqual(self.requete("SELECT count(*) FROM paiements"), [(0,)])

    def test_simulation_n_ecrit_rien(self):
        res = imp.importer(EXEMPLES, self.db, simulation=True)
        self.assertEqual(res.chantiers, 3)
        self.assertFalse(self.db.exists())
        imp.importer(EXEMPLES, self.db)
        imp.importer(self.ecrire_csv([ligne_valide()]), self.db, simulation=True)
        self.assertEqual(self.requete("SELECT count(*) FROM chantiers"), [(3,)])

    def test_gabarit_vide_importe_zero(self):
        res = imp.importer(VIDE, self.db)
        self.assertEqual((res.chantiers, res.erreurs), (0, []))


class TestImportSouple(BaseTest):
    def test_export_excel_francais(self):
        """Point-virgule, Windows-1252, virgule décimale, « 1 250,00 $ », téléphone et code postal libres."""
        chemin = self.ecrire_csv([ligne_valide(
            client_nom="Côté", client_telephone="(450) 555-0142", code_postal="j7z1a1", adresse="5 Rue Éléonore",
            type_travaux="Taille de haie", statut="Terminé", prix_ht="1 250,00 $",
            tps="62,50", tvq="124,69", duree_estimee_h="2,5", date_prevue="2026-06-14",
            paiement_date="2026-06-14", paiement_montant="1437,19", paiement_mode="Chèque")],
            delimiteur=";", encodage="cp1252")
        res = imp.importer(chemin, self.db)
        self.assertEqual(res.erreurs, [])
        self.assertIn("Windows-1252", " ".join(res.avertissements))
        self.assertEqual(self.requete("SELECT nom, telephone FROM clients"), [("Côté", "+14505550142")])
        self.assertEqual(self.requete("SELECT code_postal FROM clients"), [("J7Z 1A1",)])
        self.assertEqual(self.requete("SELECT statut, prix_ht, duree_estimee_h FROM chantiers"),
                         [("termine", 1250.0, 2.5)])
        self.assertEqual(self.requete("SELECT type_travaux, precision FROM chantier_travaux"), [("taille_haie", None)])
        self.assertEqual(self.requete("SELECT statut_paiement FROM v_chantiers"), [("paye",)])

    def test_colonnes_inutiles_peuvent_etre_supprimees(self):
        colonnes = ["client_nom", "adresse", "ville", "type_travaux", "statut"]
        chemin = self.ecrire_csv([{c: ligne_valide()[c] for c in colonnes}], colonnes=colonnes)
        self.assertEqual(imp.importer(chemin, self.db).chantiers, 1)

    def test_regroupement_des_clients(self):
        chemin = self.ecrire_csv([
            ligne_valide(),
            ligne_valide(adresse="10, rue TEST", type_travaux="elagage"),                      # même client (casse/ponctuation)
            ligne_valide(adresse="99 Autre Rue"),                                              # même nom/tél, autre adresse = 2e propriété
            ligne_valide(client_nom="Tremblay-Roy", client_prenom="Lise"),                     # même adresse + même téléphone -> même client
            ligne_valide(client_telephone="", client_nom="Gagnon", client_prenom="Marie", client_sms_ok="non"),
            ligne_valide(client_telephone="514-555-0199", client_nom="Gagnon", client_prenom="Marie",
                         code_postal="J7Z 1A1"),                                              # complète le client existant
            ligne_valide(client_telephone="", client_nom="Dupont", client_prenom="Paul"),      # autre personne, même adresse = autre client
        ])
        res = imp.importer(chemin, self.db)
        self.assertEqual(res.erreurs, [])
        self.assertEqual(self.requete("SELECT count(*) FROM clients"), [(4,)])   # Tremblay, Tremblay@99, Gagnon, Dupont
        # 7 lignes, mais celles de Tremblay-Roy et du 2e Gagnon répètent un chantier identique : ignorées
        self.assertEqual((res.chantiers, res.doublons), (5, 2))
        self.assertEqual(self.requete("SELECT telephone, sms_ok, code_postal FROM clients WHERE nom = 'Gagnon'"),
                         [("+15145550199", 0, "J7Z 1A1")])
        messages = " ".join(res.avertissements)
        self.assertIn("même adresse et même téléphone", messages)
        self.assertIn("mais à une autre adresse", messages)

    def test_plusieurs_types_de_travaux_avec_precisions(self):
        chemin = self.ecrire_csv([
            ligne_valide(type_travaux="Élagage: érable argenté, côté garage + taille_haie : cèdres, 35 m + abattage"),
            ligne_valide(adresse="2 Rue B", type_travaux="emondage"),
        ])
        res = imp.importer(chemin, self.db)
        self.assertEqual((res.erreurs, res.chantiers), ([], 2))
        self.assertEqual(self.requete("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = 1 ORDER BY type_travaux"),
                         [("abattage", None), ("elagage", "érable argenté, côté garage"), ("taille_haie", "cèdres, 35 m")])
        self.assertEqual(self.requete("SELECT types_codes, travaux_detail FROM v_chantiers WHERE chantier_id = 1"),
                         [("abattage+elagage+taille_haie", "Abattage ; Élagage : érable argenté, côté garage ; Taille de haie : cèdres, 35 m")])
        # le même fichier relancé : doublons reconnus (mêmes types), pas de nouveau chantier
        res = imp.importer(chemin, self.db)
        self.assertEqual((res.chantiers, res.doublons), (0, 2))
        # mêmes champs mais autre combinaison de types : c'est un autre chantier
        res = imp.importer(self.ecrire_csv([ligne_valide(type_travaux="elagage + abattage")], nom="b.csv"), self.db)
        self.assertEqual((res.chantiers, res.doublons), (1, 0))

    def test_types_de_travaux_invalides(self):
        chemin = self.ecrire_csv([
            ligne_valide(type_travaux="elagage + pizza"),
            ligne_valide(adresse="2 B", type_travaux="elagage + élagage"),
            ligne_valide(adresse="3 C", type_travaux=""),
            ligne_valide(adresse="4 D", type_travaux="+"),
        ])
        res = imp.importer(chemin, self.db)
        self.assertEqual([no for no, _ in res.erreurs], [2, 3, 4, 5])
        self.assertIn("pizza", res.erreurs[0][1][0])
        self.assertIn("deux fois", res.erreurs[1][1][0])

    def test_taxes_auto(self):
        chemin = self.ecrire_csv([ligne_valide(prix_ht="2200.00"), ligne_valide(adresse="2 B", prix_ht="480.00", tps="0", tvq="0")])
        imp.importer(chemin, self.db, taxes_auto=True)
        self.assertEqual(self.requete("SELECT prix_ht, tps, tvq, total_ttc FROM v_chantiers ORDER BY chantier_id"),
                         [(2200.0, 110.0, 219.45, 2529.45), (480.0, 0.0, 0.0, 480.0)])


class TestErreurs(BaseTest):
    def test_toutes_les_erreurs_sont_listees_et_rien_n_est_ecrit(self):
        chemin = self.ecrire_csv([
            ligne_valide(),                                                                   # ligne 2 : bonne
            ligne_valide(date_prevue="14/06/2026", statut="termine"),                          # ligne 3 : date
            ligne_valide(client_telephone="12345", code_postal="ZZZ"),                        # ligne 4 : tél + code postal
            ligne_valide(type_travaux="pizza", statut="fini"),                                # ligne 5 : listes
            ligne_valide(statut="termine"),                                                   # ligne 6 : date des travaux manquante
            ligne_valide(adresse="7 Rue Sept", date_facture="2026-06-14"),                    # ligne 7 : refusée par la base
            ligne_valide(paiement_montant="50"),                                              # ligne 8 : paiement incomplet
            ligne_valide(latitude="45.6", longitude="74.1"),                                  # ligne 9 : longitude sans « - »
            ligne_valide(prix_ht="450.123", fichier_papier="/etc/passwd", dossier_photos="a/../b"),  # ligne 10
        ])
        res = imp.importer(chemin, self.db)
        lignes_en_erreur = [no for no, _ in res.erreurs]
        self.assertEqual(lignes_en_erreur, [3, 4, 5, 6, 7, 8, 9, 10])
        self.assertTrue(any("refusé par la base" in m for no, ms in res.erreurs if no == 7 for m in ms))
        for table in ("clients", "chantiers", "paiements"):
            self.assertEqual(self.requete(f"SELECT count(*) FROM {table}"), [(0,)], table)

    def test_en_tete_incorrect(self):
        chemin = self.ecrire_csv([], colonnes=["client_nom", "adress", "ville", "type_travaux", "statut"])
        with self.assertRaises(SystemExit) as e:
            imp.importer(chemin, self.db)
        self.assertIn("adress", str(e.exception))
        chemin = self.ecrire_csv([], colonnes=["client_nom", "ville", "type_travaux", "statut"])
        with self.assertRaises(SystemExit) as e:
            imp.importer(chemin, self.db)
        self.assertIn("adresse", str(e.exception))

    def test_echec_ne_laisse_pas_de_sauvegarde_inutile(self):
        imp.importer(EXEMPLES, self.db)
        imp.importer(self.ecrire_csv([ligne_valide(statut="fini")]), self.db)
        self.assertEqual(list((self.db.parent / "sauvegardes").glob("*")), [])
        self.assertEqual(self.requete("SELECT count(*) FROM chantiers"), [(3,)])


if __name__ == "__main__":
    unittest.main()
