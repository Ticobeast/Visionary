"""Tests des secteurs desservis (liste fermée) et des options de la job (nacelle, bois)."""
import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
import importer_saisie  # noqa: E402
import interface  # noqa: E402
import noyau  # noqa: E402

EXEMPLES = RACINE / "modeles" / "saisie_papier_exemples.csv"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        importer_saisie.importer(EXEMPLES, self.db)

    def tearDown(self):
        self._tmp.cleanup()

    def get(self, chemin, query=None):
        statut, _, corps = interface.repondre(self.db, "GET", chemin, query or {})
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


class TestListeDeSecteurs(Base):
    def conn(self):
        conn, _ = noyau.ouvrir_base(self.db)
        return conn

    def test_liste_de_depart_adaptee_a_trois_rivieres(self):
        libelles = [l for _, l, _ in noyau.lister_secteurs(self.conn())]
        for attendu in ("Centre-ville", "Trois-Rivières-Ouest", "Cap-de-la-Madeleine"):
            self.assertIn(attendu, libelles)
        villes = {v for _, _, v in noyau.lister_secteurs(self.conn())}
        self.assertIn("Trois-Rivières", villes)

    def test_aucun_doublon_d_ecriture(self):
        conn = self.conn()
        for variante in ("Cap de la Madeleine", "cap-de-la-madeleine", "CAP-DE-LA-MADELEINE", "Cap-de-la-Madeléine", " Centre  ville "):
            code, erreurs = noyau.ajouter_secteur(conn, variante)
            self.assertIsNone(code, variante)
            self.assertTrue(erreurs, variante)
        self.assertEqual(noyau.ajouter_secteur(conn, "   ")[1], ["donne un nom au secteur"])

    def test_ajout_avec_ville_a_l_ecriture_officielle(self):
        conn = self.conn()
        code, erreurs = noyau.ajouter_secteur(conn, "Trois-Rivières-Nord", "trois rivieres")      # variante d'une ville déjà connue
        self.assertEqual((code, erreurs), ("trois_rivieres_nord", []))
        self.assertEqual(conn.execute("SELECT ville FROM secteurs WHERE code = ?", (code,)).fetchone(), ("Trois-Rivières",))
        code, _ = noyau.ajouter_secteur(conn, "Saint-Maurice")                                    # sans ville : le nom sert de ville
        self.assertEqual(conn.execute("SELECT ville FROM secteurs WHERE code = ?", (code,)).fetchone(), ("Saint-Maurice",))

    def test_la_base_refuse_un_secteur_en_double_et_un_secteur_inconnu(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO secteurs (code, libelle, ville) VALUES ('autre_code', 'CENTRE-VILLE', 'X')")      # même libellé, casse près
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("UPDATE clients SET secteur = 'nimporte_quoi' WHERE id = 1")                                    # clé étrangère
        c.close()

    def test_suppression_refusee_si_utilise(self):
        conn = self.conn()
        conn.execute("UPDATE clients SET secteur = 'centre_ville' WHERE id = 1")
        self.assertTrue(noyau.supprimer_secteur(conn, "centre_ville"))
        self.assertEqual(noyau.supprimer_secteur(conn, "nicolet"), [])
        self.assertEqual(conn.execute("SELECT count(*) FROM secteurs WHERE code = 'nicolet'").fetchone(), (0,))

    def test_renommer(self):
        conn = self.conn()
        self.assertEqual(noyau.renommer_secteur(conn, "centre_ville", "Centre-ville (Trois-Rivières)"), [])
        self.assertTrue(noyau.renommer_secteur(conn, "centre_ville", "Cap-de-la-Madeleine"))        # déjà pris par un autre
        self.assertTrue(noyau.renommer_secteur(conn, "inconnu", "X"))


class TestPageSecteurs(Base):
    def test_page_et_actions(self):
        page = self.get("/secteurs")[1]
        self.assertIn("Cap-de-la-Madeleine", page)
        self.assertIn('action="/secteurs/ajouter"', page)
        _, en_tetes, _ = self.post("/secteurs/ajouter", {"libelle": "Saint-Maurice", "ville": ""})
        self.assertEqual(en_tetes["Location"], "/secteurs?ok=secteur_ajoute")
        self.assertIn("Saint-Maurice", self.get("/secteurs")[1])
        statut, _, page = self.post("/secteurs/ajouter", {"libelle": "saint maurice"})            # doublon
        self.assertTrue(statut.startswith("200"))
        self.assertIn("existe déjà", page)
        self.post("/secteurs/saint_maurice/renommer", {"libelle": "Saint-Maurice (village)"})
        self.assertEqual(self.sql("SELECT libelle FROM secteurs WHERE code = 'saint_maurice'"), [("Saint-Maurice (village)",)])
        self.post("/secteurs/saint_maurice/supprimer", {})
        self.assertEqual(self.sql("SELECT count(*) FROM secteurs WHERE code = 'saint_maurice'"), [(0,)])

    def test_secteur_utilise_non_supprimable(self):
        self.post("/client/1/modifier", {"client_nom": "Gagnon", "client_prenom": "Marie", "client_telephone": "+14505550142", "adresse": "1 Rue A",
                                         "client_secteur": "nicolet"})
        _, _, page = self.post("/secteurs/nicolet/supprimer", {})
        self.assertIn("utilise ce secteur", page)
        self.assertEqual(self.sql("SELECT count(*) FROM secteurs WHERE code = 'nicolet'"), [(1,)])

    def test_route_protegee_contre_les_codes_etranges(self):
        self.assertTrue(self.post("/secteurs/../supprimer", {})[0].startswith("404"))
        self.assertTrue(self.post("/secteurs/A'; DROP TABLE clients;--/supprimer", {})[0].startswith("404"))
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])

    def test_html_echappe(self):
        self.post("/secteurs/ajouter", {"libelle": "<script>alert(1)</script>"})
        self.assertNotIn("<script>alert", self.get("/secteurs")[1])
        self.assertNotIn("<script>alert", self.get("/nouveau")[1])


class TestFiltrerParSecteur(Base):
    def test_chantiers_filtres_par_secteur(self):
        self.post("/client/3/modifier", {"client_nom": "Boucher", "client_prenom": "Luc", "client_telephone": "+14505550163", "adresse": "850 Boulevard du Lac",
                                         "client_secteur": "pointe_du_lac"})
        page = self.get("/chantiers", {"secteur": "pointe_du_lac"})[1]
        self.assertIn("Luc Boucher", page)
        self.assertNotIn("Pierre Lavoie", page)
        self.assertIn("Pointe-du-Lac", page)                           # le secteur est écrit sous l'adresse
        self.assertIn('<option value="pointe_du_lac" selected>', page)


class TestImportAvecSecteur(Base):
    def importer(self, lignes):
        chemin = Path(self._tmp.name) / "s.csv"
        entete = ["client_nom", "client_prenom", "client_telephone", "adresse", "ville", "client_secteur", "type_travaux", "statut", "duree_estimee_h"]
        with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(entete)
            w.writerows(lignes)
        return importer_saisie.importer(chemin, self.db)

    def test_secteur_par_code_ou_libelle_et_ville_deduite(self):
        res = self.importer([["Aubry", "Jo", "819-555-0101", "1 Rue Un", "Trois Rivieres", "Cap de la Madeleine", "emondage", "soumission", "2"],
                             ["Bibeau", "Jo", "819-555-0102", "2 Rue Deux", "", "centre_ville", "emondage", "soumission", "2"]])
        self.assertEqual(res.erreurs, [])
        self.assertEqual(self.sql("SELECT nom, secteur, ville FROM clients WHERE nom IN ('Aubry', 'Bibeau') ORDER BY nom"),
                         [("Aubry", "cap_de_la_madeleine", "Trois-Rivières"), ("Bibeau", "centre_ville", "Trois-Rivières")])

    def test_secteur_inconnu_refuse_et_rien_n_est_importe(self):
        res = self.importer([["Aubry", "Jo", "819-555-0101", "1 Rue Un", "X", "Atlantide", "emondage", "soumission", "2"]])
        self.assertTrue(any("client_secteur" in m for _, ms in res.erreurs for m in ms))
        self.assertEqual(self.sql("SELECT count(*) FROM clients"), [(3,)])

    def test_secteur_facultatif_a_l_import(self):                       # vieilles feuilles : la ville libre est gardée
        res = self.importer([["Aubry", "Jo", "819-555-0101", "1 Rue Un", "Ailleurs", "", "emondage", "soumission", "2"]])
        self.assertEqual(res.erreurs, [])
        self.assertEqual(self.sql("SELECT secteur, ville FROM clients WHERE nom = 'Aubry'"), [(None, "Ailleurs")])


class TestOptionsDuTravail(Base):
    def ligne(self, **perso):
        base = {"client_nom": "X", "adresse": "1 A", "ville": "V", "type_travaux": "abattage", "statut": "soumission", "duree_estimee_h": "2"}
        base.update(perso)
        return noyau.lire_ligne(base, {"abattage": "abattage"}, False)

    def test_lecture_csv(self):
        v, erreurs = self.ligne(nacelle="oui", debarrasser_bois="non", bois_format="16 pouces")
        self.assertEqual((erreurs, v["nacelle"], v["debarrasser_bois"], v["bois_format"]), ([], 1, 0, "16_pouces"))
        v, _ = self.ligne(bois_format="4 pieds")
        self.assertEqual((v["nacelle"], v["debarrasser_bois"], v["bois_format"]), (0, 0, "4_pieds"))       # défauts : pas de nacelle
        v, _ = self.ligne(debarrasser_bois="oui")
        self.assertEqual((v["debarrasser_bois"], v["bois_format"]), (1, None))

    def test_incoherences_refusees(self):
        _, erreurs = self.ligne(debarrasser_bois="oui", bois_format="4 pieds")
        self.assertTrue(any("bois_format" in e for e in erreurs))
        _, erreurs = self.ligne(bois_format="8 pieds")
        self.assertTrue(any("bois_format" in e for e in erreurs))
        _, erreurs = self.ligne(nacelle="peut-être")
        self.assertTrue(any("nacelle" in e for e in erreurs))

    def test_la_base_refuse_un_format_avec_bois_debarrasse_ou_inconnu(self):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        for requete in ("UPDATE chantiers SET debarrasser_bois = 1, bois_format = '4_pieds' WHERE id = 3",
                        "UPDATE chantiers SET bois_format = '8_pieds' WHERE id = 3", "UPDATE chantiers SET nacelle = 2 WHERE id = 3",
                        "UPDATE chantiers SET debarrasser_bois = 'oui' WHERE id = 3"):
            with self.assertRaises(sqlite3.IntegrityError, msg=requete):
                c.execute(requete)
        c.close()

    def test_options_verrouillees_avec_un_chantier_termine(self):
        c = sqlite3.connect(self.db)
        for requete in ("UPDATE chantiers SET nacelle = 1 WHERE id = 2", "UPDATE chantiers SET debarrasser_bois = 1 WHERE id = 2",
                        "UPDATE chantiers SET bois_format = '4_pieds' WHERE id = 2"):
            with self.assertRaises(sqlite3.IntegrityError, msg=requete):
                c.execute(requete)
        c.close()

    def test_visibles_dans_les_listes_et_les_journees(self):
        page = self.get("/chantier/3")[1]                              # Boucher : nacelle, bois débarrassé
        self.assertIn("Nacelle requise", page)
        self.assertIn("Bois débarrassé", page)
        self.assertIn("Bois laissé sur place : 16 pouces", self.get("/chantier/2")[1])             # Lavoie : bois laissé en 16 pouces
        chantiers = self.get("/chantiers")[1]
        self.assertIn("🏗 Nacelle requise", chantiers)
        self.assertIn("🪵 Bois laissé sur place : 16 pouces", chantiers)
        jour = self.sql("SELECT date_prevue FROM chantiers WHERE id = 3")[0][0]
        for chemin in ("/", "/journee"):
            self.assertIn("🏗 Nacelle requise", self.get(chemin, {"date": jour})[1], chemin)

    def test_duplication_copie_les_options(self):
        conn, _ = noyau.ouvrir_base(self.db)
        nouveau, erreurs = noyau.dupliquer_chantier(conn, 2)
        self.assertEqual(erreurs, [])
        self.assertEqual(conn.execute("SELECT nacelle, debarrasser_bois, bois_format FROM chantiers WHERE id = ?", (nouveau,)).fetchone(), (0, 0, "16_pouces"))
        conn.close()


if __name__ == "__main__":
    unittest.main()
