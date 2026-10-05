"""Tests des nouveaux statuts, du calcul des heures, de l'ordre de passage, du calendrier et de la confirmation « Terminé »."""
import datetime
import re
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

AUJOURDHUI = datetime.date.today()
MODALE = 'Voulez-vous passer ce chantier au statut &quot;Terminé&quot; ?'


def dans(jours):
    return (AUJOURDHUI + datetime.timedelta(days=jours)).isoformat()


def h(minutes):
    return noyau.heure_texte(minutes)


class TestHoraire(unittest.TestCase):
    def horaire(self, durees):
        return [(h(x["debut"]), h(x["fin"])) for x in noyau.calculer_horaire(durees)]

    def test_debut_a_7h30_et_enchainement(self):
        self.assertEqual(self.horaire([2, 1.5]), [("7 h 30", "9 h 30"), ("9 h 30", "11 h 00")])
        self.assertEqual(self.horaire([]), [])

    def test_le_diner_est_insere_dans_un_chantier_qui_chevauche_midi(self):
        r = noyau.calculer_horaire([2, 2, 1, 1.5])
        self.assertEqual([(h(x["debut"]), h(x["fin"])) for x in r],
                         [("7 h 30", "9 h 30"), ("9 h 30", "11 h 30"), ("11 h 30", "13 h 00"), ("13 h 00", "14 h 30")])
        self.assertEqual([x["diner_dans"] for x in r], [False, False, True, False])      # 11 h 30 + 1 h + 30 min de dîner

    def test_un_chantier_qui_finit_a_midi_pile_le_suivant_commence_apres_le_diner(self):
        r = noyau.calculer_horaire([4.5, 1])
        self.assertEqual([(h(x["debut"]), h(x["fin"])) for x in r], [("7 h 30", "12 h 00"), ("12 h 30", "13 h 30")])
        self.assertEqual([x["diner_avant"] for x in r], [False, True])

    def test_chantier_qui_commencerait_pendant_le_diner(self):
        r = noyau.calculer_horaire([3, 1.5, 1])                 # 7 h 30-10 h 30 ; 10 h 30-12 h 00 ; 12 h 30-13 h 30
        self.assertEqual(h(r[2]["debut"]), "12 h 30")

    def test_duree_inconnue_signalee(self):
        r = noyau.calculer_horaire([None, 2])
        self.assertEqual([x["duree_inconnue"] for x in r], [True, False])
        self.assertEqual(h(r[1]["debut"]), "7 h 30")


class BaseJour(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        conn, _ = noyau.ouvrir_base(self.db)
        self.ids = {}
        for nom, ville, statut, jour, duree in [
            ("Alpha", "Blainville", "planifie", dans(1), 2.0), ("Bravo", "Mirabel", "planifie", dans(1), 3.0),
            ("Charlie", "Mirabel", "planifie", dans(1), 1.5), ("Delta", "Blainville", "a_planifier", None, 2.0),
            ("Echo", "Blainville", "en_attente", None, 1.0), ("Fox", "Mirabel", "termine", dans(-3), 2.0)]:
            conn.execute("INSERT INTO clients (nom, adresse, ville, telephone) VALUES (?, ?, ?, '+14505550100')", (nom, f"1 Rue {nom}", ville))
            cid = conn.execute("SELECT max(id) FROM clients").fetchone()[0]
            conn.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, prix_ht) VALUES (?,?,?,?,300)", (cid, statut, jour, duree))
            chid = conn.execute("SELECT max(id) FROM chantiers").fetchone()[0]
            conn.execute("INSERT INTO chantier_travaux VALUES (?, 'emondage', NULL)", (chid,))
            self.ids[nom] = chid
        conn.execute("BEGIN")
        for nom in ("Alpha", "Bravo", "Charlie", "Fox"):           # ordres 1, 2, 3 le jour J+1 ; Fox seul son jour
            noyau.ajuster_ordre(conn, self.ids[nom])
        conn.execute("COMMIT")
        conn.close()

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

    def ordre(self, jour=None):
        jour = jour or dans(1)
        return [r[0] for r in self.sql("SELECT c.nom FROM chantiers ch JOIN clients c ON c.id = ch.client_id WHERE ch.date_prevue = ? "
                                       "ORDER BY ch.ordre_jour", (jour,))]


class TestStatuts(BaseJour):
    def test_statuts_officiels(self):
        self.assertEqual(noyau.STATUTS, ("soumission", "en_attente", "a_planifier", "planifie", "termine", "annule"))
        self.assertEqual([noyau.LIBELLES_STATUT[s] for s in noyau.STATUTS],
                         ["Soumission", "En attente", "À planifier", "Planifié", "Terminé", "Annulé"])
        page = self.get("/chantier/%d" % self.ids["Alpha"])[1]
        options = re.findall(r'<option value="([a-z_]+)"[^>]*>([^<]+)</option>', page[page.index('name="statut"'):page.index('name="statut"') + 700])
        self.assertEqual([c for c, _ in options], list(noyau.STATUTS))
        self.assertNotIn("Refusé", page)

    def test_anciens_noms_toujours_compris_a_l_import(self):
        base = {"client_nom": "X", "adresse": "1 A", "ville": "V", "type_travaux": "emondage"}
        for saisi, attendu in (("Accepté", "a_planifier"), ("accepte", "a_planifier"), ("Refusé", "annule"), ("À planifier", "a_planifier"),
                               ("En attente", "en_attente"), ("en_attente", "en_attente"), ("Terminé", "termine"), ("Annulé", "annule")):
            v, erreurs = noyau.lire_ligne({**base, "statut": saisi, "date_prevue": "2026-06-01", "duree_estimee_h": "2"}, {"emondage": "emondage"}, False)
            self.assertEqual((erreurs, v["statut"]), ([], attendu), saisi)

    def test_en_attente_et_a_planifier_n_ont_pas_de_date(self):
        conn, _ = noyau.ouvrir_base(self.db)
        for statut in ("en_attente", "a_planifier", "soumission"):
            self.assertEqual(noyau.changer_statut(conn, self.ids["Alpha"], statut), [])
            self.assertEqual(conn.execute("SELECT statut, date_prevue, ordre_jour FROM chantiers WHERE id = ?", (self.ids["Alpha"],)).fetchone(), (statut, None, None))
            noyau.changer_statut(conn, self.ids["Alpha"], "planifie", dans(1))
        conn.close()

    def test_en_attente_peut_etre_planifie_en_lot_mais_pas_un_chantier_termine(self):
        conn, _ = noyau.ouvrir_base(self.db)
        self.assertEqual(noyau.planifier_lot(conn, [self.ids["Echo"]], dans(2)), [])
        self.assertTrue(noyau.planifier_lot(conn, [self.ids["Fox"]], dans(2)))
        conn.close()

    def test_paiement_sans_objet_pour_en_attente(self):
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = ?", (self.ids["Echo"],)), [("sans_objet",)])
        self.assertEqual(self.sql("SELECT statut_paiement FROM v_chantiers WHERE chantier_id = ?", (self.ids["Delta"],)), [("a_venir",)])

    def test_onglet_en_attente_du_suivi(self):
        page = self.get("/suivi", {"vue": "enattente"})[1]
        self.assertEqual(re.findall(r'<a href="/client/\d+">([^<]+)</a>', page), ["Echo"])
        self.assertIn("En attente (1)", page)


class TestOrdreDeLaJournee(BaseJour):
    def test_ordre_attribue_a_la_planification(self):
        self.assertEqual(self.ordre(), ["Alpha", "Bravo", "Charlie"])
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("BEGIN")
        noyau.planifier_lot(conn, [self.ids["Echo"], self.ids["Delta"]], dans(1))     # ajoutés à la fin, dans cet ordre
        conn.execute("COMMIT")
        conn.close()
        self.assertEqual(self.ordre(), ["Alpha", "Bravo", "Charlie", "Echo", "Delta"])

    def test_monter_et_descendre(self):
        _, en_tetes, _ = self.post("/action/deplacer", {"chantier_id": str(self.ids["Charlie"]), "sens": "haut", "retour": "/"})
        self.assertEqual(en_tetes["Location"], "/?ok=deplace")
        self.assertEqual(self.ordre(), ["Alpha", "Charlie", "Bravo"])
        self.post("/action/deplacer", {"chantier_id": str(self.ids["Alpha"]), "sens": "bas", "retour": "/"})
        self.assertEqual(self.ordre(), ["Charlie", "Alpha", "Bravo"])
        self.assertEqual(self.sql("SELECT ordre_jour FROM chantiers WHERE date_prevue = ? ORDER BY ordre_jour", (dans(1),)), [(1,), (2,), (3,)])

    def test_aux_extremites_rien_ne_bouge_et_pas_d_erreur(self):
        for nom, sens in (("Alpha", "haut"), ("Charlie", "bas")):
            _, en_tetes, _ = self.post("/action/deplacer", {"chantier_id": str(self.ids[nom]), "sens": sens, "retour": "/"})
            self.assertIn("ok=deplace", en_tetes["Location"])
        self.assertEqual(self.ordre(), ["Alpha", "Bravo", "Charlie"])

    def test_deplacer_refuse_hors_journee_ou_sens_invalide(self):
        for form in ({"chantier_id": str(self.ids["Delta"]), "sens": "haut"}, {"chantier_id": str(self.ids["Alpha"]), "sens": "diagonale"},
                     {"chantier_id": "9999", "sens": "haut"}):
            _, en_tetes, _ = self.post("/action/deplacer", {"retour": "/", **form})
            self.assertIn("err=", en_tetes["Location"], form)

    def test_les_heures_sont_recalculees_quand_l_ordre_change(self):
        page = self.get("/", {"date": dans(1)})[1]
        self.assertEqual(re.findall(r"(\d+ h \d\d) → (\d+ h \d\d)", page), [("7 h 30", "9 h 30"), ("9 h 30", "13 h 00"), ("13 h 00", "14 h 30")])
        self.assertIn("dîner inclus", page)                      # Bravo (3 h) chevauche midi
        self.post("/action/deplacer", {"chantier_id": str(self.ids["Charlie"]), "sens": "haut", "retour": "/"})
        self.post("/action/deplacer", {"chantier_id": str(self.ids["Charlie"]), "sens": "haut", "retour": "/"})
        # Charlie (1 h 30), Alpha (2 h), Bravo (3 h)
        page = self.get("/", {"date": dans(1)})[1]
        self.assertEqual(re.findall(r"(\d+ h \d\d) → (\d+ h \d\d)", page), [("7 h 30", "9 h 00"), ("9 h 00", "11 h 00"), ("11 h 00", "14 h 30")])
        self.assertIn("fin prévue <b>14 h 30</b>", page)

    def test_changer_la_duree_recalcule(self):
        self.post("/action/statut", {"chantier_id": str(self.ids["Alpha"]), "statut": "planifie", "date_prevue": dans(1), "duree_estimee_h": "1", "retour": "/"})
        page = self.get("/", {"date": dans(1)})[1]
        self.assertEqual(re.findall(r"(\d+ h \d\d) → (\d+ h \d\d)", page)[:2], [("7 h 30", "8 h 30"), ("8 h 30", "11 h 30")])

    def test_changer_de_jour_replace_a_la_fin_et_sortir_efface_l_ordre(self):
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("BEGIN")
        noyau.changer_statut(conn, self.ids["Alpha"], "planifie", dans(3))               # nouveau jour, seul : rang 1
        noyau.changer_statut(conn, self.ids["Bravo"], "planifie", dans(3))               # derrière Alpha : rang 2
        noyau.changer_statut(conn, self.ids["Charlie"], "a_planifier")
        conn.execute("COMMIT")
        conn.close()
        self.assertEqual(self.ordre(dans(3)), ["Alpha", "Bravo"])
        self.assertEqual(self.sql("SELECT ordre_jour FROM chantiers WHERE id = ?", (self.ids["Charlie"],)), [(None,)])
        self.assertEqual(self.sql("SELECT count(*) FROM chantiers WHERE date_prevue = ?", (dans(1),)), [(0,)])

    def test_terminer_garde_le_rang(self):
        self.post("/action/statut", {"chantier_id": str(self.ids["Bravo"]), "statut": "termine", "retour": "/"})
        self.assertEqual(self.ordre(), ["Alpha", "Bravo", "Charlie"])
        self.assertIn("Bravo", self.get("/", {"date": dans(1)})[1])           # il reste visible dans la journée

    def test_retirer_remet_a_planifier(self):
        self.post("/action/retirer", {"chantier_id": str(self.ids["Bravo"]), "retour": "/"})
        self.assertEqual(self.sql("SELECT statut, date_prevue, ordre_jour FROM chantiers WHERE id = ?", (self.ids["Bravo"],)), [("a_planifier", None, None)])

    def test_creation_depuis_le_formulaire_complet_obtient_un_rang(self):
        form = {"client_nom": "Nouveau", "adresse": "9 Rue N", "ville": "Mirabel", "client_sms_ok": "1", "type_emondage": "1",
                "statut": "planifie", "date_prevue": dans(1), "duree_estimee_h": "1"}
        self.post("/nouveau", form)
        self.assertEqual(self.ordre()[-1], "Nouveau")


class TestCalendrier(BaseJour):
    def test_grille_du_mois_avec_chantiers_et_heures(self):
        demain = datetime.date.fromisoformat(dans(1))
        statut, page = self.get("/", {"mois": f"{demain.year}-{demain.month:02d}"})
        self.assertTrue(statut.startswith("200"))
        self.assertIn("cal-grille", page)
        for jour in ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."):
            self.assertIn(jour, page)
        # le jour J+1 : 3 chantiers, 6 h 30 ; cliquable vers le déroulement de la journée
        lien = re.search(rf'<a class="([^"]*)" href="(/\?date={dans(1)}[^"]*)"[^>]*>(.*?)</a>', page)
        self.assertIsNotNone(lien)
        self.assertIn("occupe", lien.group(1))
        self.assertIn("<b>3</b> chantiers", lien.group(3))
        self.assertIn("6 h 30", lien.group(3))

    def test_cliquer_une_date_affiche_le_deroulement(self):
        page = self.get("/", {"date": dans(1)})[1]
        self.assertIn("selection", page)
        for nom in ("Alpha", "Bravo", "Charlie"):
            self.assertIn(nom, page)
        self.assertNotIn("Delta", page)                                  # « À planifier » n'est pas dans la journée
        self.assertIn("début <b>7 h 30</b>", page)
        self.assertIn("dîner 12 h 00 - 12 h 30", page)
        self.assertIn('action="/action/deplacer"', page)
        self.assertIn('action="/action/statut"', page)
        self.assertIn('action="/action/encaisser"', page)
        self.assertIn(f'href="/tournee?date={dans(1)}"', page)

    def test_jour_sans_chantier(self):
        self.assertIn("Aucun chantier planifié ce jour-là", self.get("/", {"date": dans(9)})[1])

    def test_navigation_entre_les_mois(self):
        page = self.get("/", {"mois": "2026-12", "date": "2026-12-15"})[1]
        self.assertIn("Décembre 2026", page)
        self.assertIn("mois=2026-11", page)
        self.assertIn("mois=2027-01", page)
        self.assertIn("Mardi 15 décembre 2026", page)

    def test_parametres_invalides_retombent_sur_aujourdhui(self):
        page = self.get("/", {"date": "n'importe quoi", "mois": "2026-99"})[1]
        self.assertIn(f"{AUJOURDHUI.day} ", page)
        self.assertTrue(self.get("/", {"date": "2026-02-30"})[0].startswith("200"))

    def test_journee_chargee_et_a_cloturer(self):
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE chantiers SET duree_estimee_h = 4 WHERE id = ?", (self.ids["Alpha"],))          # 4 + 3 + 1,5 = 8,5 h
        conn.execute("UPDATE chantiers SET date_prevue = ?, statut = 'planifie', ordre_jour = 1 WHERE id = ?", (dans(-2), self.ids["Delta"]))
        conn.close()
        demain = datetime.date.fromisoformat(dans(1))
        mois = f"{demain.year}-{demain.month:02d}"
        page = self.get("/", {"mois": mois, "date": dans(1)})[1]
        self.assertIn("chargee", page)
        self.assertIn("journée chargée", page)
        passe = datetime.date.fromisoformat(dans(-2))
        page = self.get("/", {"mois": f"{passe.year}-{passe.month:02d}"})[1]
        self.assertIn("a-cloturer", page)
        self.assertIn("à clôturer", page)

    def test_tableau_de_bord_epure_sans_tuiles(self):
        page = self.get("/")[1]
        for absent in ('class="puce"', "/suivi?vue=aplanifier", "/suivi?vue=afacturer", "À planifier</span>", "En attente</span>"):
            self.assertNotIn(absent, page)
        self.assertIn("cal-grille", page)                                  # le calendrier interactif est là
        self.assertIn("Aucun chantier planifié", page)                     # et la planification de la journée sélectionnée

    def test_total_monetaire_de_la_journee_sous_le_cumul_du_temps(self):
        # Alpha 300 $, Bravo 300 $, Charlie 300 $ avant taxes, sans tps/tvq saisies : total du jour = 900 $
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE chantiers SET tps = 15, tvq = 29.93 WHERE id = ?", (self.ids["Alpha"],))
        conn.close()
        page = self.get("/", {"date": dans(1)})[1]
        self.assertIn("Total de la journée", page)
        self.assertIn("944,93 $", page)                                    # 300 + 15 + 29,93 + 300 + 300
        self.assertIn("taxes incluses", page)
        self.assertLess(page.index("durée totale"), page.index("Total de la journée"))
        self.assertLess(page.index("Total de la journée"), page.index("Heures calculées"))

    def test_navigation_principale(self):
        page = self.get("/")[1]
        for lien in ("/", "/tournee", "/chantiers", "/clients", "/nouveau"):
            self.assertIn(f'<a href="{lien}">', page)


class TestConfirmationTermine(BaseJour):
    def encaisser(self, nom, montant="100", retour="/?date=X"):
        return self.post("/action/encaisser", {"chantier_id": str(self.ids[nom]), "montant": montant, "mode": "interac", "retour": retour})

    def test_un_encaissement_sur_un_chantier_planifie_propose_terminer(self):
        _, en_tetes, _ = self.encaisser("Alpha", retour=f"/?date={dans(1)}")
        self.assertIn("ok=encaisse", en_tetes["Location"])
        self.assertIn(f"terminer={self.ids['Alpha']}", en_tetes["Location"])
        self.assertEqual(self.sql("SELECT count(*) FROM paiements WHERE chantier_id = ?", (self.ids["Alpha"],)), [(1,)])      # le paiement est enregistré
        page = self.get(en_tetes["Location"].split("?")[0], dict(p.split("=") for p in en_tetes["Location"].split("?")[1].split("&")))[1]
        self.assertIn(MODALE, page)
        self.assertIn("Oui, passer à Terminé", page)
        self.assertIn("Non, laisser Planifié", page)
        self.assertIn('role="dialog"', page)
        self.assertIn("Alpha", page[page.index('role="dialog"'):])

    def test_pas_de_fenetre_pour_les_autres_statuts(self):
        for nom in ("Delta", "Fox"):
            conn, _ = noyau.ouvrir_base(self.db)
            conn.execute("UPDATE chantiers SET statut = ?, date_prevue = ? WHERE id = ?", ("termine" if nom == "Fox" else "a_planifier", dans(-3) if nom == "Fox" else None, self.ids[nom]))
            conn.close()
        _, en_tetes, _ = self.encaisser("Fox")
        self.assertNotIn("terminer=", en_tetes["Location"])
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE chantiers SET statut = 'termine', date_prevue = ? WHERE id = ?", (dans(-1), self.ids["Delta"]))
        conn.close()
        _, en_tetes, _ = self.encaisser("Delta")
        self.assertNotIn("terminer=", en_tetes["Location"])

    def test_oui_passe_le_chantier_a_termine(self):
        self.encaisser("Bravo")
        page = self.get("/", {"date": dans(1), "terminer": str(self.ids["Bravo"])})[1]
        formulaire = page[page.index('class="modale"'):]
        self.assertIn('name="statut" value="termine"', formulaire)
        _, en_tetes, _ = self.post("/action/statut", {"chantier_id": str(self.ids["Bravo"]), "statut": "termine", "retour": f"/?date={dans(1)}&terminer={self.ids['Bravo']}"})
        self.assertEqual(self.sql("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (self.ids["Bravo"],)), [("termine", dans(1))])
        self.assertNotIn("terminer=", en_tetes["Location"])                     # la fenêtre ne revient pas

    def test_non_laisse_planifie_et_ferme_la_fenetre(self):
        page = self.get("/", {"date": dans(1), "terminer": str(self.ids["Bravo"]), "ok": "encaisse"})[1]
        lien = re.search(r'<a class="bouton secondaire" href="([^"]+)">Non, laisser Planifié</a>', page).group(1)
        self.assertNotIn("terminer", lien)
        self.assertNotIn("ok=", lien)
        self.assertEqual(self.sql("SELECT statut FROM chantiers WHERE id = ?", (self.ids["Bravo"],)), [("planifie",)])

    def test_lien_perime_ou_invalide_n_affiche_rien(self):
        for valeur in (str(self.ids["Delta"]), "99999", "abc", ""):
            self.assertNotIn("Voulez-vous", self.get("/", {"terminer": valeur})[1], valeur)

    def test_aussi_depuis_la_page_du_chantier_et_depuis_les_tournees(self):
        _, en_tetes, _ = self.post(f"/chantier/{self.ids['Alpha']}/paiement", {"paiement_date": AUJOURDHUI.isoformat(), "paiement_montant": "50", "paiement_mode": "cheque"})
        self.assertIn(f"terminer={self.ids['Alpha']}", en_tetes["Location"])
        page = self.get(f"/chantier/{self.ids['Alpha']}", {"ok": "paiement", "terminer": str(self.ids["Alpha"])})[1]
        self.assertIn(MODALE, page)
        self.assertIn(MODALE, self.get("/tournee", {"date": dans(1), "terminer": str(self.ids["Alpha"])})[1])
        self.assertIn(MODALE, self.get("/suivi", {"terminer": str(self.ids["Alpha"])})[1])


class TestSecurite(BaseJour):
    def test_html_echappe_dans_le_calendrier(self):
        conn, _ = noyau.ouvrir_base(self.db)
        conn.execute("UPDATE clients SET nom = '<script>alert(1)</script>' WHERE id = 1")
        conn.close()
        self.assertNotIn("<script>alert", self.get("/", {"date": dans(1)})[1])


if __name__ == "__main__":
    unittest.main()
