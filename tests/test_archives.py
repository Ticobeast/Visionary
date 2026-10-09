"""Tests de l'onglet Archives : recherche, relance par client, statistiques, export CSV, accès réservé à l'administrateur.

    python3 -m unittest discover -s tests -v
"""
import csv
import datetime
import html
import io
import re
import sqlite3
import sys
import unittest
import urllib.parse
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import archives  # noqa: E402
import interface  # noqa: E402
import noyau  # noqa: E402
import vue  # noqa: E402
from test_pages_soumissions import BaseComptes, BasePages  # noqa: E402

AUJOURDHUI = datetime.date.today()


def il_y_a(jours):
    return (AUJOURDHUI - datetime.timedelta(days=jours)).isoformat()


class BaseArchives(BasePages):
    """Les trois dossiers d'essai plus un historique à nous. Toutes les dates sont calculées par rapport à aujourd'hui : les tests ne
    vieillissent pas. Chantiers terminés : Hamel (haie de cèdres il y a 400 jours, émondage il y a 40), Pelletier (haie de cèdres, 100 jours,
    rien payé), Gosselin (haie de thuyas, 600 jours), Dubois (abattage, 30 jours, acompte), Gagnon (130 jours), Lavoie (20 jours).
    Puis : Lemay (soumission refusée), Roy (chantier annulé), Fortin (soumission en cours)."""

    def setUp(self):
        super().setUp()
        self.n_clients = 0
        self.sql_exec("DROP TRIGGER trg_chantiers_termine_verrouille")           # pour dater à notre façon les chantiers terminés d'essai
        self.sql_exec("UPDATE chantiers SET date_prevue = ?, date_soumission = ? WHERE id = 1", (il_y_a(130), il_y_a(140)))     # Gagnon
        self.sql_exec("UPDATE chantiers SET date_prevue = ?, date_soumission = ? WHERE id = 2", (il_y_a(20), il_y_a(30)))       # Lavoie
        hamel = self.client("Hamel", "1 Rue des Haies", "centre_ville")
        self.fiche(hamel, "termine", "taille_haie", "cèdres, environ 40 m", il_y_a(400), 800, paye=800, reelle=4)
        self.fiche(hamel, "termine", "emondage", "2 érables", il_y_a(40), 300, paye=300, reelle=1.5)
        pelletier = self.client("Pelletier", "2 Chemin des Cèdres", "trois_rivieres_ouest")
        self.fiche(pelletier, "termine", "taille_haie", "haie de cèdres, 60 m", il_y_a(100), 1000, reelle=5)
        gosselin = self.client("Gosselin", "3 Rue Neuve", "centre_ville")
        self.fiche(gosselin, "termine", "taille_haie", "haie de thuyas", il_y_a(600), 500, paye=500, reelle=2.5)
        dubois = self.client("Dubois", "4 Rue Courte", "cap_de_la_madeleine")
        self.fiche(dubois, "termine", "abattage", "frêne mort", il_y_a(30), 1500, paye=500, reelle=6)
        lemay = self.client("Lemay", "5 Rue Longue", "centre_ville")
        self.fiche(lemay, "annule", "taille_haie", "haie de cèdres", None, 700, soumission=il_y_a(60), accepte=None)             # soumission refusée
        roy = self.client("Roy", "6 Rue du Parc", "centre_ville")
        self.fiche(roy, "annule", "elagage", "chêne", None, 900, soumission=il_y_a(25), accepte=il_y_a(20))                       # chantier annulé
        fortin = self.client("Fortin", "7 Rue Haute", "centre_ville")
        self.fiche(fortin, "soumission", "emondage", "pommier", None, 250, soumission=il_y_a(3), accepte=None)                   # encore en cours

    def sql_exec(self, requete, args=()):
        c = sqlite3.connect(self.db)
        c.execute("PRAGMA foreign_keys = ON")
        try:
            cur = c.execute(requete, args)
            c.commit()
            return cur.lastrowid
        finally:
            c.close()

    def client(self, nom, adresse, secteur):
        self.n_clients += 1
        return self.sql_exec("INSERT INTO clients (nom, telephone, adresse, ville, secteur) VALUES (?, ?, ?, 'Trois-Rivières', ?)",
                             (nom, f"+1819555{99 + self.n_clients:04d}", adresse, secteur))

    def fiche(self, client_id, statut, type_, precision, date_prevue, prix, soumission=None, accepte="auto", paye=0, reelle=None, duree=2):
        demande = soumission or (date_prevue or il_y_a(10))
        if accepte == "auto":
            accepte = demande
        i = self.sql_exec("INSERT INTO chantiers (client_id, statut, date_soumission, date_prevue, duree_estimee_h, duree_reelle_h, prix_ht, accepte_le)"
                          " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (client_id, statut, demande, date_prevue, duree, reelle, prix, accepte))
        self.sql_exec("INSERT INTO chantier_travaux VALUES (?, ?, ?)", (i, type_, precision))
        if paye:
            self.sql_exec("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?, ?, ?, 'interac')", (i, date_prevue, paye))
        return i

    def noms(self, chemin):
        """Les noms de famille des clients des résultats, dans l'ordre de la page (un nom par ligne de résultat)."""
        page = self.get(chemin)
        if '<h2 class="groupe">Résultats' in page:
            page = page[page.index('<h2 class="groupe">Résultats'):].split('id="statistiques"')[0]
        trouves = re.findall(r'<a href="/(?:client|chantier|soumission)/\d+">([^<]+)</a><div class="doux">', page)
        return [t.split()[-1] for t in trouves]

    def csv(self, chemin):
        u = urllib.parse.urlsplit(chemin)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        statut, en_tetes, corps = interface.repondre(self.db, "GET", u.path, query)
        return statut, dict(en_tetes), corps

    def selection(self, **criteres):
        conn, _ = noyau.ouvrir_base(self.db)
        self.addCleanup(conn.close)
        f = archives.lire_filtres(conn, criteres)
        return conn, f, archives.selectionner(conn, f)


class TestRecherche(BaseArchives):
    def test_par_defaut_les_chantiers_termines_seulement(self):
        self.assertEqual(set(self.noms("/archives")), {"Hamel", "Pelletier", "Gosselin", "Dubois", "Gagnon", "Lavoie"})        # payés ou non
        page = self.get("/archives")
        for absent in ("Lemay", "Roy", "Fortin", "Boucher"):                                           # refusée, annulé, en cours, planifié
            self.assertNotIn(absent, page)

    def test_refusees_annules_et_tout(self):
        self.assertEqual(set(self.noms("/archives?resultat=refusee")), {"Lemay"})
        self.assertEqual(set(self.noms("/archives?resultat=annule")), {"Roy"})
        self.assertEqual(set(self.noms("/archives?resultat=tout")), {"Hamel", "Pelletier", "Gosselin", "Dubois", "Gagnon", "Lavoie", "Lemay", "Roy"})
        page = self.get("/archives?resultat=tout")
        self.assertIn("Refusée", page)
        self.assertIn("Annulé", page)

    def test_recherche_de_texte_sans_accent_dans_les_precisions(self):
        self.assertEqual(set(self.noms("/archives?q=cedre")), {"Hamel", "Pelletier", "Gagnon"})        # « cèdres » trouvé sans l'accent ; pas les thuyas
        self.assertEqual(set(self.noms("/archives?q=CÈDRES+haie")), {"Hamel", "Pelletier", "Gagnon"})
        self.assertEqual(set(self.noms("/archives?q=thuyas")), {"Gosselin"})
        self.assertEqual(set(self.noms("/archives?q=555-0100")), {"Hamel"})                              # le téléphone, comme on l'écrit
        self.assertEqual(set(self.noms("/archives?q=rue+courte")), {"Dubois"})                           # l'adresse

    def test_type_de_travaux_et_secteur(self):
        self.assertEqual(set(self.noms("/archives?type=taille_haie")), {"Hamel", "Pelletier", "Gosselin", "Gagnon"})
        self.assertEqual(set(self.noms("/archives?type=abattage")), {"Dubois", "Lavoie"})                # Lavoie combine élagage et abattage
        self.assertEqual(set(self.noms("/archives?secteur=cap_de_la_madeleine")), {"Dubois"})
        self.assertEqual(set(self.noms("/archives?type=taille_haie&secteur=centre_ville")), {"Hamel", "Gosselin"})

    def test_il_y_a_plus_ou_moins_de_n_mois(self):
        self.assertEqual(set(self.noms("/archives?plus_de=12")), {"Hamel", "Gosselin"})                  # faits il y a plus d'un an
        self.assertEqual(set(self.noms("/archives?moins_de=3")), {"Hamel", "Dubois", "Lavoie"})          # Pelletier : il y a 100 jours, plus de 3 mois
        self.assertEqual(set(self.noms("/archives?plus_de=3&moins_de=6")), {"Pelletier", "Gagnon"})
        self.assertEqual(set(self.noms("/archives?plus_de=12&moins_de=18")), {"Hamel"})                  # il y a 400 jours ; Gosselin : près de 20 mois

    def test_dates_precises(self):
        self.assertEqual(set(self.noms(f"/archives?du={il_y_a(120)}&au={il_y_a(35)}")), {"Pelletier", "Hamel"})        # 100 jours et 40 jours
        self.assertEqual(set(self.noms(f"/archives?du={il_y_a(35)}")), {"Dubois", "Lavoie"})
        self.assertEqual(set(self.noms(f"/archives?au={il_y_a(450)}")), {"Gosselin"})

    def test_montant_minimum(self):
        self.assertEqual(set(self.noms("/archives?montant_min=1000")), {"Pelletier", "Dubois", "Lavoie"})
        self.assertEqual(set(self.noms("/archives?montant_min=1+250,50")), {"Dubois"})                    # « 1 250,50 » : espace et virgule passent

    def test_le_cas_de_la_haie_de_cedre_a_relancer(self):
        """Qui relancer : haies de cèdre faites il y a plus d'un an, un résultat par client, les plus anciennes d'abord."""
        chemin = "/archives?type=taille_haie&q=cedre&plus_de=12&par_client=1&tri=ancien"
        self.assertEqual(self.noms(chemin), ["Hamel"])
        page = self.get(chemin)
        self.assertIn("1 client", page)
        self.assertIn(il_y_a(400), page)
        self.assertIn('href="/client/', page)
        self.assertIn("Relancer", page)

    def test_un_seul_resultat_par_client(self):
        self.assertEqual(self.noms("/archives?q=hamel"), ["Hamel", "Hamel"])                              # deux chantiers
        self.assertEqual(self.noms("/archives?q=hamel&par_client=1"), ["Hamel"])
        page = self.get("/archives?q=hamel&par_client=1")
        self.assertIn("1 client", page)
        self.assertIn(il_y_a(40), page)                                                                   # son DERNIER chantier
        self.assertNotIn(il_y_a(400), page)
        self.assertIn(vue.argent(1100), page)                                                             # 800 + 300

    def test_tris(self):
        ordre = lambda tri: self.noms(f"/archives?tri={tri}")
        self.assertEqual(ordre("recent")[0], "Lavoie")                                                    # il y a 20 jours
        self.assertEqual(ordre("ancien")[0], "Gosselin")                                                  # il y a 600 jours
        montant = ordre("montant")
        self.assertEqual(montant[:3], ["Dubois", "Lavoie", "Pelletier"])                                  # 1 500 $, 1 250 $, 1 000 $
        alphabetique = [n for n in ordre("client") if n in ("Dubois", "Gosselin", "Hamel", "Pelletier")]
        self.assertEqual(alphabetique, ["Dubois", "Gosselin", "Hamel", "Hamel", "Pelletier"])

    def test_criteres_invalides_ignores(self):
        defaut = self.noms("/archives")
        pourri = "/archives?type=zzz&secteur=zzz&resultat=zzz&du=pasunedate&au=2026-13-01&plus_de=abc&moins_de=-4&montant_min=abc&tri=zzz&par_client=peut-etre"
        self.assertEqual(self.noms(pourri), defaut)
        self.assertTrue(self.req("GET", "/archives?q=" + "x" * 5000)[0].startswith("200"))

    def test_rien_ne_correspond(self):
        self.assertIn("Rien ne correspond", self.get("/archives?q=zzzzzz"))

    def test_pas_encore_d_historique(self):
        vide = Path(self._tmp.name) / "data" / "vide.db"
        noyau.ouvrir_base(vide)[0].close()
        page = interface.repondre(vide, "GET", "/archives", {})[2].decode("utf-8")
        self.assertIn("Pas encore d'historique", html.unescape(page))
        self.assertNotIn("Rien ne correspond", page)

    def test_le_formulaire_garde_les_criteres(self):
        page = self.get("/archives?q=cedre&type=taille_haie&secteur=centre_ville&plus_de=12&moins_de=24&resultat=tout&tri=montant&montant_min=500&par_client=1")
        for attendu in ('value="cedre"', '<option value="taille_haie" selected>', '<option value="centre_ville" selected>', '<option value="12" selected>',
                        '<option value="24" selected>', '<option value="tout" selected>', '<option value="montant" selected>', 'value="500"', "checked"):
            self.assertIn(attendu, page, attendu)

    def test_les_idees_de_recherche_fonctionnent(self):
        page = self.get("/archives")
        liens = re.findall(r'<a href="(/archives\?[^"]+)">', page.split("Idées de recherche")[1].split("</p>")[0])
        self.assertGreaterEqual(len(liens), 4)
        for lien in liens:
            self.assertTrue(self.req("GET", lien.replace("&amp;", "&"))[0].startswith("200"), lien)
        self.assertEqual(self.noms(liens[0].replace("&amp;", "&")), ["Hamel"])                           # la haie de cèdres d'il y a plus d'un an

    def test_le_texte_cherche_est_echappe(self):
        page = self.get("/archives?q=%22%3E%3Cscript%3Ealert(1)%3C/script%3E")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&quot;&gt;&lt;script&gt;", page)
        self.sql_exec("UPDATE clients SET nom = '<b>Gras</b>' WHERE nom = 'Dubois'")
        page = self.get("/archives")
        self.assertNotIn("<b>Gras</b>", page)
        self.assertIn("&lt;b&gt;Gras&lt;/b&gt;", page)

    def test_la_relance_ouvre_une_soumission_pour_le_client(self):
        page = self.get("/archives?q=hamel&par_client=1")
        lien = re.search(r'href="(/client/\d+/soumission/nouveau)" title="Ouvrir une nouvelle soumission pour ce client">Relancer', page).group(1)
        self.assertTrue(self.req("GET", lien)[0].startswith("200"))
        self.assertIn("Hamel", self.get(lien))


class TestStatistiques(BaseArchives):
    def test_chiffres_cles(self):
        conn, f, lignes = self.selection()
        st = archives.statistiques(lignes)
        attendu_ca = round(sum(r[0] for r in conn.execute("SELECT prix_ht FROM v_chantiers WHERE statut = 'termine'")), 2)
        self.assertEqual(st["n_termines"], 7)
        self.assertEqual(st["ca_ht"], attendu_ca)
        self.assertAlmostEqual(st["prix_moyen"], attendu_ca / 7, places=2)
        self.assertEqual(st["clients"], 6)                                                                # Hamel compte pour un seul client
        self.assertEqual(st["n_annules"] + st["n_refusees"], 0)
        self.assertGreater(st["par_heure"], 0)
        self.assertEqual(st["a_recevoir"], round(sum(r[0] for r in conn.execute(
            "SELECT solde FROM v_chantiers WHERE statut = 'termine' AND statut_paiement IN ('a_payer', 'partiel')")), 2))
        self.assertEqual(st["recu"], round(sum(r[0] for r in conn.execute("SELECT paye FROM v_chantiers WHERE statut = 'termine'")), 2))

    def test_les_refusees_et_annules_ne_rapportent_rien(self):
        _, _, lignes = self.selection(resultat="tout")
        st = archives.statistiques(lignes)
        self.assertEqual((st["n_termines"], st["n_annules"], st["n_refusees"], st["n_total"]), (7, 1, 1, 9))
        _, _, seulement = self.selection(resultat="refusee")
        refusees = archives.statistiques(seulement)
        self.assertEqual((refusees["n_termines"], refusees["ca_ht"], refusees["prix_moyen"]), (0, 0.0, None))

    def test_revenu_par_heure(self):
        """Prix avant taxes divisé par les heures passées sur place (durée réelle, sinon estimée)."""
        _, _, lignes = self.selection(type="emondage")
        st = archives.statistiques(lignes)
        self.assertEqual(st["n_termines"], 1)
        self.assertAlmostEqual(st["par_heure"], 300 / 1.5)                                                # l'émondage de Hamel : 300 $ en 1 h 30
        _, _, lignes = self.selection(q="thuyas")
        self.assertAlmostEqual(archives.statistiques(lignes)["par_heure"], 500 / 2.5)

    def test_ventilations(self):
        conn, _, lignes = self.selection()
        st = archives.statistiques(lignes)
        self.assertEqual(st["par_type"]["Taille de haie"]["n"], 4)                                       # Hamel, Pelletier, Gosselin, Gagnon
        self.assertEqual(st["par_type"]["Taille de haie"]["ca"], 800 + 1000 + 500 + 480)
        self.assertEqual(st["par_type"]["Abattage + Élagage"]["n"], 1)                                   # un chantier qui combine deux types a sa propre ligne
        self.assertEqual(st["par_type"]["Abattage"]["ca"], 1500)
        self.assertEqual(sum(g["n"] for g in st["par_type"].values()), st["n_termines"])
        cap = conn.execute("SELECT libelle FROM secteurs WHERE code = 'cap_de_la_madeleine'").fetchone()[0]
        self.assertEqual(st["par_secteur"][cap]["n"], 1)
        self.assertEqual(st["par_secteur"]["(sans secteur)"]["n"], 2)                                    # les deux dossiers d'essai sans secteur
        self.assertEqual(sum(g["n"] for g in st["par_secteur"].values()), st["n_termines"])
        self.assertEqual(sum(g["n"] for g in st["par_annee"].values()), st["n_termines"])
        self.assertEqual(sorted(st["par_mois"]), list(range(1, 13)))                                      # les douze mois, même vides
        self.assertEqual(sum(g["n"] for g in st["par_mois"].values()), st["n_termines"])
        self.assertGreaterEqual(st["par_mois"][int(il_y_a(40)[5:7])]["n"], 1)

    def test_statistiques_vides(self):
        _, _, lignes = self.selection(q="zzzz")
        st = archives.statistiques(lignes)
        self.assertEqual((st["n_termines"], st["ca_ht"], st["prix_moyen"], st["par_heure"], st["clients"]), (0, 0.0, None, None, 0))
        page = self.get("/archives?q=zzzz")
        self.assertNotIn("Par type de travaux", page)
        self.assertIn("0</b><span>chantiers terminés", page)

    def test_la_page_montre_les_tableaux_et_les_tuiles(self):
        page = html.unescape(self.get("/archives"))
        for titre in ("Par type de travaux", "Par secteur", "Par année", "Selon le mois de l'année", "Que deviennent les soumissions ?"):
            self.assertIn(titre, page, titre)
        self.assertIn('id="statistiques"', page)
        for tuile in ("chantiers terminés", "chiffre d'affaires avant taxes", "prix moyen par chantier", "durée moyenne", "revenu par heure", "clients différents"):
            self.assertIn(tuile, page, tuile)
        self.assertIn("encore à recevoir", page)                                                          # Pelletier n'a rien payé
        self.assertIn(vue.argent(5830), page)                                                             # le chiffre d'affaires total

    def test_taux_d_acceptation_des_soumissions(self):
        conn, f, _ = self.selection()
        g = archives.statistiques_soumissions(conn, f)["global"]
        self.assertEqual(g["refusees"], 1)                                                                # Lemay
        self.assertEqual(g["en_cours"], 1)                                                                # Fortin
        self.assertEqual(g["acceptees"], 9)                                                               # tous les chantiers : 3 dossiers d'essai + 6 à nous
        self.assertEqual(g["total"], g["acceptees"] + g["refusees"] + g["en_cours"])
        self.assertAlmostEqual(g["taux"], 9 / 10)
        _, f2, _ = self.selection(q="lemay")
        self.assertEqual(archives.statistiques_soumissions(conn, f2)["global"]["taux"], 0.0)
        _, f3, _ = self.selection(q="zzzz")
        self.assertEqual(archives.statistiques_soumissions(conn, f3)["global"]["total"], 0)
        self.assertIn("Taux d'acceptation", html.unescape(self.get("/archives")))

    def test_les_chantiers_en_attente_comptent_comme_acceptes(self):
        i = self.sql("SELECT id FROM chantiers WHERE statut = 'soumission' LIMIT 1")[0][0]                # Fortin
        self.sql_exec("UPDATE chantiers SET statut = 'en_attente', accepte_le = ? WHERE id = ?", (il_y_a(1), i))
        conn, f, _ = self.selection()
        g = archives.statistiques_soumissions(conn, f)["global"]
        self.assertEqual((g["acceptees"], g["en_cours"]), (10, 0))

    def test_taux_par_personne_et_delai_de_reponse(self):
        dubois = self.sql("SELECT c.id FROM chantiers c JOIN clients cl ON cl.id = c.client_id WHERE cl.nom = 'Dubois'")[0][0]
        self.sql_exec("UPDATE chantiers SET cree_par = 'Marc', date_soumission = ?, accepte_le = ? WHERE id = ?", (il_y_a(40), il_y_a(30), dubois))
        self.sql_exec("UPDATE chantiers SET cree_par = 'Marc' WHERE statut = 'annule' AND accepte_le IS NULL")
        self.sql_exec("UPDATE chantiers SET cree_par = 'Alice' WHERE statut = 'soumission'")
        conn, f, _ = self.selection()
        ss = archives.statistiques_soumissions(conn, f)
        self.assertEqual(sorted(ss["par_personne"]), ["Alice", "Marc"])
        marc = ss["par_personne"]["Marc"]
        self.assertEqual((marc["acceptees"], marc["refusees"]), (1, 1))
        self.assertAlmostEqual(marc["taux"], 0.5)
        self.assertEqual(marc["delai"], 10)                                                               # demande le jour -40, acceptée le jour -30
        self.assertEqual((ss["par_personne"]["Alice"]["en_cours"], ss["par_personne"]["Alice"]["taux"]), (1, None))
        self.assertIn("Marc", html.unescape(self.get("/archives")).split("Que deviennent les soumissions")[1])

    def test_date_de_reference(self):
        _, _, lignes = self.selection(resultat="tout")
        par_client = {l["client_nom_complet"]: l for l in lignes}
        self.assertEqual(par_client["Dubois"]["date_ref"], il_y_a(30))                                    # terminé : la date des travaux
        self.assertEqual(par_client["Lemay"]["date_ref"], il_y_a(60))                                     # refusée : la date de la demande
        self.assertEqual(par_client["Roy"]["date_ref"], il_y_a(20))                                       # annulé : l'acceptation


class TestRegroupement(BaseArchives):
    def test_regrouper_par_client(self):
        _, _, lignes = self.selection()
        groupes = archives.regrouper_par_client(lignes, "ancien")
        self.assertEqual(len(groupes), len({l["client_id"] for l in lignes}))
        hamel = next(g for g in groupes if g["client_nom_complet"] == "Hamel")
        self.assertEqual((hamel["nb"], hamel["total"], hamel["date_ref"]), (2, 1100.0, il_y_a(40)))
        self.assertEqual(hamel["type_libelle"], "Émondage")                                                # son dernier chantier
        self.assertEqual([g["date_ref"] for g in groupes], sorted(g["date_ref"] for g in groupes))
        self.assertEqual(archives.regrouper_par_client(lignes, "montant")[0]["client_nom_complet"], "Dubois")      # 1 500 $, devant Lavoie (1 250 $)
        self.assertEqual(archives.regrouper_par_client(lignes, "recent")[0]["client_nom_complet"], "Pierre Lavoie")
        noms = [g["client_nom_complet"] for g in archives.regrouper_par_client(lignes, "client")]
        self.assertEqual(noms, sorted(noms, key=noyau.cle))
        self.assertEqual(archives.regrouper_par_client([], "recent"), [])


class TestExport(BaseArchives):
    def lire(self, chemin):
        statut, en_tetes, corps = self.csv(chemin)
        self.assertTrue(statut.startswith("200"), statut)
        self.assertTrue(corps.startswith("﻿".encode("utf-8")))                                       # BOM : Excel lit les accents
        lignes = list(csv.reader(io.StringIO(corps.decode("utf-8-sig")), delimiter=";"))
        return en_tetes, lignes

    def test_entetes_et_colonnes(self):
        en_tetes, lignes = self.lire("/archives.csv")
        self.assertEqual(en_tetes["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual(en_tetes["Content-Disposition"], f'attachment; filename="archives-{AUJOURDHUI.isoformat()}.csv"')
        self.assertEqual(lignes[0], ["Date", "Client", "Téléphone", "Courriel", "Adresse", "Secteur", "Travaux", "Résultat", "Prix avant taxes",
                                     "Total taxes incluses", "Durée estimée (h)", "Durée réelle (h)", "Reçu", "À recevoir"])
        self.assertEqual(len(lignes) - 1, 7)                                                              # les sept chantiers terminés
        hamel = next(l for l in lignes[1:] if l[1] == "Hamel" and l[0] == il_y_a(400))
        self.assertEqual(hamel[2], "819-555-0100")
        self.assertEqual(hamel[6], "Taille de haie : cèdres, environ 40 m")
        self.assertEqual(hamel[7], "Terminé")
        self.assertEqual(hamel[8:10], ["800,00", "800,00"])                                                  # virgule décimale : Excel en fait des nombres
        self.assertEqual(hamel[10:12], ["2", "4"])
        self.assertEqual(hamel[12:14], ["800,00", ""])                                                    # reçu, à recevoir

    def test_a_recevoir_et_resultats(self):
        _, lignes = self.lire("/archives.csv?resultat=tout")
        ligne = {l[1]: l for l in lignes[1:]}
        self.assertEqual(ligne["Pelletier"][13], "1000,00")                                               # rien reçu : tout est à recevoir
        self.assertEqual(ligne["Dubois"][12:14], ["500,00", "1000,00"])
        self.assertEqual(ligne["Lemay"][7], "Refusée")
        self.assertEqual(ligne["Roy"][7], "Annulé")

    def test_memes_criteres_que_la_page(self):
        _, lignes = self.lire("/archives.csv?type=taille_haie&q=cedre&plus_de=12&par_client=1&tri=ancien")
        self.assertEqual(lignes[0][:8], ["Client", "Téléphone", "Courriel", "Adresse", "Secteur", "Dernier chantier", "Nombre de chantiers", "Total avant taxes"])
        self.assertEqual([l[0] for l in lignes[1:]], ["Hamel"])
        self.assertEqual(lignes[1][5:8], [il_y_a(400), "1", "800,00"])
        _, lignes = self.lire("/archives.csv?q=hamel&par_client=1")
        self.assertEqual(lignes[1][5:8], [il_y_a(40), "2", "1100,00"])

    def test_le_lien_d_export_reprend_les_criteres(self):
        page = self.get("/archives?q=cedre&type=taille_haie&plus_de=12")
        lien = re.search(r'href="(/archives\.csv\?[^"]+)"', page).group(1).replace("&amp;", "&")
        _, par_le_lien = self.lire(lien)
        _, direct = self.lire("/archives.csv?q=cedre&type=taille_haie&plus_de=12")
        self.assertEqual(par_le_lien[1:], direct[1:])
        self.assertEqual(len(par_le_lien) - 1, len(self.noms("/archives?q=cedre&type=taille_haie&plus_de=12")))

    def test_une_cellule_ne_peut_pas_etre_une_formule(self):
        self.sql_exec("UPDATE clients SET nom = '=HYPERLINK(\"http://pirate.example\")' WHERE nom = 'Dubois'")
        self.sql_exec("UPDATE clients SET adresse = '@SUM(A1)' WHERE nom = 'Hamel'")
        _, lignes = self.lire("/archives.csv")
        clients = [l[1] for l in lignes[1:]]
        self.assertIn("'=HYPERLINK(\"http://pirate.example\")", clients)
        self.assertNotIn('=HYPERLINK("http://pirate.example")', clients)
        self.assertTrue(all(l[4].startswith("'@SUM") for l in lignes[1:] if l[1] == "Hamel"))
        self.assertEqual(archives._cellule("-5"), "'-5")
        self.assertEqual(archives._cellule("Normal"), "Normal")
        self.assertEqual(archives._cellule(None), "")

    def test_l_export_n_est_pas_limite_comme_la_page(self):
        modele = self.sql("SELECT client_id FROM chantiers WHERE statut = 'termine' LIMIT 1")[0][0]
        c = sqlite3.connect(self.db)
        for k in range(230):
            c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, date_prevue, duree_estimee_h, prix_ht, accepte_le)"
                      " VALUES (?, 'termine', '2020-01-01', ?, 1, 10, '2020-01-01')", (modele, f"2020-{k % 12 + 1:02d}-{k % 28 + 1:02d}"))
        c.commit()
        c.close()
        page = self.get("/archives")
        self.assertIn(f"Les {archives.LIMITE_RESULTATS} premiers sur 237", page)
        self.assertEqual(len(re.findall(r'<td class="col-actions">', page)), archives.LIMITE_RESULTATS)
        self.assertEqual(len(self.lire("/archives.csv")[1]) - 1, 237)


class TestPresentationTelephone(BaseArchives):
    """Ce que le téléphone utilise (la mise en forme elle-même est dans outils/telephone.py) : filtres repliables, pastilles, classes des cellules,
    numéros qui lancent l'appel. L'ordinateur voit la même chose qu'avant."""

    def test_les_filtres_sont_repliables_et_s_ouvrent_quand_on_en_utilise(self):
        page = self.get("/archives")
        self.assertIn('<details class="filtres-det" id="filtres-det"><summary>Filtres</summary>', page)
        self.assertIn("window.innerWidth>700", page)                                   # ordinateur : toujours ouverts
        self.assertIn('<details class="filtres-det" id="filtres-det" open>', self.get("/archives?type=taille_haie"))
        self.assertIn('<details class="filtres-det" id="filtres-det" open>', self.get("/archives?resultat=tout"))
        self.assertIn('<details class="filtres-det" id="filtres-det" open>', self.get("/archives?par_client=1"))
        self.assertNotIn(" open>", self.get("/archives?q=hamel").split("<summary>")[0].split("<details")[-1])        # le texte seul ne les ouvre pas

    def test_les_idees_sont_des_liens_separes_a_faire_defiler(self):
        page = self.get("/archives")
        idees = page.split('<span class="idees-liens">')[1].split("</p>")[0]
        self.assertGreaterEqual(idees.count('<span class="sep">'), 3)
        self.assertIn("Idées de recherche", page)

    def test_les_cellules_ont_leur_classe(self):
        for chemin in ("/archives", "/archives?par_client=1"):
            ligne = self.get(chemin).split("<tbody>")[1].split("</tr>")[0]
            for classe in ("c-date", "c-client", "c-adresse", "c-travaux", "c-statut", "c-montant", "col-actions"):
                self.assertIn(classe, ligne, (chemin, classe))
        self.assertRegex(self.get("/archives?par_client=1&resultat=tout"), r'c-statut">\d+<span class="tel-seul"> chantiers?</span>')

    def test_les_numeros_lancent_l_appel(self):
        self.sql_exec("UPDATE clients SET telephone = '+18195550106' WHERE nom = 'Hamel'")
        lien = '<a class="tel" href="tel:+18195550106">819-555-0106</a>'
        self.assertIn(lien, self.get("/archives?resultat=tout"))
        self.assertIn(lien, self.get("/clients"))
        self.assertIn(lien, self.get("/client/%d" % self.sql("SELECT id FROM clients WHERE nom = 'Hamel'")[0][0]))

    def test_lien_tel(self):
        self.assertEqual(vue.lien_tel("+18195550106"), '<a class="tel" href="tel:+18195550106">819-555-0106</a>')
        self.assertEqual(vue.lien_tel(""), "")
        self.assertEqual(vue.lien_tel(None), "")
        self.assertEqual(vue.lien_tel("poste 12"), '<a class="tel" href="tel:12">poste 12</a>')
        mauvais = vue.lien_tel('"><script>alert(1)</script>')
        self.assertNotIn("<script>", mauvais)
        self.assertTrue(mauvais.startswith('<a class="tel" href="tel:1">'))              # seuls les chiffres (et un + au début) vont dans le lien


class TestAcces(BaseComptes):
    def test_reserve_a_l_administrateur(self):
        for chemin in ("/archives", "/archives?q=cedre", "/archives.csv"):
            self.assertTrue(self.req("GET", chemin, cookie=self.admin)[0].startswith("200"), chemin)
            for cookie in (self.alice, self.marc):
                statut, _, corps = self.req("GET", chemin, cookie=cookie)
                self.assertTrue(statut.startswith("403"), chemin)
                self.assertNotIn("Boucher", corps)
                self.assertNotIn("Gagnon", corps)
        statut, en_tetes, _ = self.req("GET", "/archives", cookie="")
        self.assertTrue(statut.startswith("303") and en_tetes["Location"].startswith("/connexion"))       # sans compte connecté : à la connexion

    def test_le_menu(self):
        def menu(cookie):
            page = self.get("/chantiers", cookie=cookie)
            return page[page.index("<header"):page.index("</header>")]
        self.assertIn('<a href="/archives">Archives</a>', menu(self.admin))
        self.assertNotIn("/archives", menu(self.alice))
        self.assertIn('href="/archives">onglet Archives</a>', self.get("/chantiers", cookie=self.admin))           # lien depuis Chantiers
        self.assertNotIn("onglet Archives", self.get("/chantiers", cookie=self.alice))
        page = self.get("/archives", cookie=self.admin)
        self.assertIn('.nav-bureau a[href="/archives"]{', page)                                                 # l'onglet courant est surligné
        self.assertIn('<span class="tag-badge">Archives</span>', page)

    def test_pas_d_archives_dans_la_barre_du_telephone(self):
        telephone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148 Safari/604.1"
        page = self.get("/chantiers", cookie=self.admin, agent=telephone)
        bas = page[page.index('class="barre-mobile"'):page.index("</nav>", page.index('class="barre-mobile"'))]
        self.assertNotIn("/archives", bas)                                                                      # la barre du bas reste simple : Archives est dans le menu
        self.assertIn('href="/archives"', page[page.index('class="menu-feuille"'):])


if __name__ == "__main__":
    unittest.main()
