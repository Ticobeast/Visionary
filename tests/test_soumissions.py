"""Tests des soumissions : cycle de vie (noyau), puis pages (onglet Soumissions, acceptation, refus, raccourcis).

    python3 -m unittest discover -s tests -v
"""
import datetime
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

AUJOURDHUI = datetime.date.today().isoformat()
ALIAS = {"emondage": "emondage", "elagage": "elagage", "abattage": "abattage", "taille haie": "taille_haie"}


class BaseNoyau(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "data" / "t.db"
        fixtures.creer_exemples(self.db)
        self.conn, _ = noyau.ouvrir_base(self.db)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.conn.close)

    def soumission(self, cree_par="Alice", **brut):
        """Crée une soumission avec ce qui est donné (par défaut : rien du tout)."""
        brut = {"statut": "soumission", **brut}
        v, erreurs = noyau.lire_ligne(brut, ALIAS, False)
        self.assertEqual(erreurs, [])
        res = noyau.Resultat()
        client_id = noyau.trouver_ou_creer_client(self.conn, noyau.Index(self.conn), v, res)
        return noyau.creer_chantier(self.conn, client_id, v, res, cree_par=cree_par)

    def complete(self, **perso):
        base = dict(client_nom="Tremblay", client_telephone="450-555-0101", adresse="10 Rue Test", client_secteur="centre_ville",
                    ville="Trois-Rivières", type_travaux="emondage", duree_estimee_h="2", prix_ht="300")
        base.update(perso)
        return self.soumission(**base)

    def ligne(self, i):
        return self.conn.execute("SELECT statut, accepte_le, genre, archive, cree_par, attente_depuis FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone()


class TestCycleDeVie(BaseNoyau):
    def test_une_soumission_vide_existe(self):
        i = self.soumission()
        self.assertEqual(self.ligne(i)[:5], ("soumission", None, "soumission", 0, "Alice"))
        r = self.conn.execute("SELECT client_nom_complet, adresse_maps FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone()
        self.assertEqual(r, ("(client à identifier)", ""))

    def test_les_dossiers_existants_sont_des_chantiers_acceptes(self):
        for i in (1, 2, 3):
            statut, accepte, genre, *_ = self.ligne(i)
            self.assertEqual((genre, accepte is not None), ("chantier", True), (i, statut))

    def test_ce_qui_manque_pour_accepter(self):
        i = self.soumission()
        self.assertEqual(noyau.manques_pour_accepter(self.conn, i), ["nom", "telephone", "adresse", "secteur", "travaux", "duree", "prix"])
        j = self.soumission(client_nom="Roy", client_telephone="450-555-0102", type_travaux="emondage")
        self.assertEqual(noyau.manques_pour_accepter(self.conn, j), ["adresse", "secteur", "duree", "prix"])
        k = self.soumission(client_entreprise="Syndicat X")                                    # l'entreprise tient lieu de nom
        self.assertNotIn("nom", noyau.manques_pour_accepter(self.conn, k))
        self.assertEqual(noyau.manques_pour_accepter(self.conn, self.complete()), [])
        self.assertEqual(noyau.manques_pour_accepter(self.conn, 999), [])
        self.assertEqual(len(noyau.CONDITIONS_ACCEPTATION), 8)
        self.assertEqual(noyau.libelles_manques(["prix"]), ["le prix"])

    def test_le_sort_du_bois_est_exige_seulement_pour_un_abattage_ou_un_elagage(self):
        i = self.complete(type_travaux="abattage")
        self.assertEqual(noyau.manques_pour_accepter(self.conn, i), ["bois"])
        j = self.complete(type_travaux="elagage", debarrasser_bois="oui")
        self.assertEqual(noyau.manques_pour_accepter(self.conn, j), [])
        k = self.complete(type_travaux="abattage", bois_format="4 pieds")
        self.assertEqual(noyau.manques_pour_accepter(self.conn, k), [])
        self.assertEqual(noyau.manques_pour_accepter(self.conn, self.complete(type_travaux="emondage")), [])

    def test_prix_zero_est_un_prix(self):
        i = self.complete(prix_ht="0")
        self.assertEqual(noyau.manques_pour_accepter(self.conn, i), [])

    def test_accepter_refuse_tant_que_c_est_incomplet(self):
        i = self.soumission(client_nom="Roy")
        erreurs = noyau.accepter_soumission(self.conn, i)
        self.assertEqual(len(erreurs), 1)
        for mot in ("téléphone", "adresse", "secteur", "type de travaux", "durée", "prix"):
            self.assertIn(mot, erreurs[0])
        self.assertEqual(self.ligne(i)[:3], ("soumission", None, "soumission"))

    def test_accepter(self):
        i = self.complete()
        self.assertEqual(noyau.accepter_soumission(self.conn, i), [])
        self.assertEqual(self.ligne(i)[:4], ("a_planifier", AUJOURDHUI, "chantier", 0))
        self.assertTrue(noyau.accepter_soumission(self.conn, i))                          # déjà acceptée
        self.assertTrue(noyau.accepter_soumission(self.conn, 999))

    def test_le_delai_d_attente_d_un_chantier_part_de_l_acceptation(self):
        i = self.complete(date_soumission="2026-01-01")
        self.assertEqual(self.ligne(i)[5], "2026-01-01")                                   # soumission : depuis la demande
        noyau.accepter_soumission(self.conn, i)
        self.assertEqual(self.ligne(i)[5], AUJOURDHUI)                                    # chantier : depuis l'acceptation

    def test_refuser_puis_rouvrir(self):
        i = self.soumission(client_nom="Roy")
        self.assertEqual(noyau.refuser_soumission(self.conn, i), [])
        self.assertEqual(self.ligne(i)[:4], ("annule", None, "soumission", 1))             # refusée : reste une soumission, archivée
        self.assertTrue(noyau.refuser_soumission(self.conn, i))                            # déjà refusée
        self.assertTrue(noyau.accepter_soumission(self.conn, i))                           # il faut d'abord la rouvrir
        self.assertEqual(noyau.rouvrir_chantier(self.conn, i), [])
        self.assertEqual(self.ligne(i)[:4], ("soumission", None, "soumission", 0))

    def test_un_chantier_annule_reste_un_chantier(self):
        i = self.complete()
        noyau.accepter_soumission(self.conn, i)
        self.assertEqual(noyau.annuler_chantier(self.conn, i), [])
        self.assertEqual(self.ligne(i)[:4], ("annule", AUJOURDHUI, "chantier", 1))
        self.assertEqual(noyau.rouvrir_chantier(self.conn, i), [])
        self.assertEqual(self.ligne(i)[:3], ("a_planifier", AUJOURDHUI, "chantier"))

    def test_on_ne_refuse_pas_un_chantier(self):
        self.assertTrue(noyau.refuser_soumission(self.conn, 3))                            # chantier planifié
        self.assertEqual(self.ligne(3)[0], "planifie")

    def test_remettre_en_soumission(self):
        i = self.complete()
        noyau.accepter_soumission(self.conn, i)
        self.assertEqual(noyau.remettre_en_soumission(self.conn, i), [])
        self.assertEqual(self.ligne(i)[:3], ("soumission", None, "soumission"))
        self.assertTrue(noyau.remettre_en_soumission(self.conn, 3))                        # planifié : à retirer d'abord de sa journée
        self.assertTrue(noyau.remettre_en_soumission(self.conn, 2))                        # terminé

    def test_une_soumission_ne_devient_pas_chantier_sans_passer_par_accepter(self):
        i = self.complete()
        for statut in ("a_planifier", "planifie", "termine"):
            erreurs = noyau.changer_statut(self.conn, i, statut, date_prevue="2026-12-01", duree="2")
            self.assertTrue(erreurs, statut)
            self.assertIn("Accepter", erreurs[0])
        self.assertEqual(self.ligne(i)[:3], ("soumission", None, "soumission"))
        self.assertTrue(noyau.terminer_chantier(self.conn, i))
        self.assertEqual(noyau.annuler_chantier(self.conn, i), [])                       # annuler une soumission = la refuser
        self.assertEqual(self.ligne(i)[:4], ("annule", None, "soumission", 1))

    def test_une_soumission_ne_se_planifie_pas(self):
        i = self.complete()
        self.assertTrue(noyau.planifier_lot(self.conn, [i], "2026-12-01"))
        noyau.accepter_soumission(self.conn, i)
        self.assertEqual(noyau.planifier_lot(self.conn, [i], "2026-12-01"), [])
        self.assertEqual(self.ligne(i)[0], "planifie")

    def test_le_formulaire_ne_change_ni_le_statut_ni_la_date(self):
        i = self.complete()
        v, _ = noyau.lire_ligne({"statut": "planifie", "date_prevue": "2026-12-01", "client_nom": "T", "adresse": "1", "ville": "V",
                                 "type_travaux": "emondage", "duree_estimee_h": "3"}, ALIAS, False)
        self.assertEqual(noyau.mettre_a_jour_fiche(self.conn, i, v), [])
        self.assertEqual(self.conn.execute("SELECT statut, date_prevue, duree_estimee_h FROM chantiers WHERE id = ?", (i,)).fetchone(),
                         ("soumission", None, 3.0))

    def test_dupliquer_cree_une_soumission_sans_exiger_la_duree(self):
        nouveau, erreurs = noyau.dupliquer_chantier(self.conn, 3, cree_par="Alice")
        self.assertEqual(erreurs, [])
        self.assertEqual(self.ligne(nouveau)[:5], ("soumission", None, "soumission", 0, "Alice"))
        i = self.soumission()
        nouveau, erreurs = noyau.dupliquer_chantier(self.conn, i)                          # une soumission vide se duplique aussi
        self.assertEqual(erreurs, [])

    def test_supprimer_une_soumission_vide_supprime_aussi_son_client_vide(self):
        i = self.soumission()
        n = self.conn.execute("SELECT count(*) FROM clients").fetchone()[0]
        self.assertEqual(noyau.supprimer_chantier(self.conn, i), [])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM clients").fetchone()[0], n - 1)

    def test_libelle_statut(self):
        self.assertEqual(noyau.libelle_statut("annule", "soumission"), "Refusée")
        self.assertEqual(noyau.libelle_statut("annule", "chantier"), "Annulé")
        self.assertEqual(noyau.libelle_statut("soumission", "soumission"), "Soumission")
        self.assertEqual(noyau.libelle_statut("a_planifier"), "À planifier")


def jour_dans(n):
    return (datetime.date.today() + datetime.timedelta(days=n)).isoformat()


class TestEnAttente(BaseNoyau):
    """Un chantier accepté qu'on ne peut pas faire tout de suite (pas de taille de haie en avril) : en attente, avec une date de
    reprise (retour automatique à « À planifier ») ou jusqu'à nouvel ordre."""

    def accepte(self, **perso):
        i = self.complete(**perso)
        self.assertEqual(noyau.accepter_soumission(self.conn, i), [])
        return i

    def etat(self, i):
        return self.conn.execute("SELECT statut, accepte_le, reprise_le, genre, statut_paiement, attente_depuis FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone()

    def test_un_chantier_a_planifier_se_met_en_attente_avec_une_date(self):
        i = self.accepte()
        self.assertEqual(noyau.mettre_en_attente(self.conn, i, jour_dans(60)), [])
        self.assertEqual(self.etat(i)[:5], ("en_attente", AUJOURDHUI, jour_dans(60), "chantier", "a_venir"))      # reste un chantier accepté

    def test_jusqu_a_nouvel_ordre(self):
        i = self.accepte()
        self.assertEqual(noyau.mettre_en_attente(self.conn, i), [])
        self.assertEqual(self.etat(i)[:3], ("en_attente", AUJOURDHUI, None))
        self.assertEqual(noyau.mettre_en_attente(self.conn, i, "  "), [])                  # une date vide = jusqu'à nouvel ordre

    def test_une_soumission_complete_va_directement_en_attente(self):
        i = self.complete()
        self.assertEqual(noyau.mettre_en_attente(self.conn, i, jour_dans(90)), [])
        self.assertEqual(self.etat(i)[:4], ("en_attente", AUJOURDHUI, jour_dans(90), "chantier"))     # acceptée aujourd'hui, mais en attente

    def test_une_soumission_incomplete_ne_se_met_pas_en_attente(self):
        i = self.soumission(client_nom="Roy")
        erreurs = noyau.mettre_en_attente(self.conn, i, jour_dans(30))
        self.assertEqual(len(erreurs), 1)
        self.assertIn("complète", erreurs[0])
        for mot in ("téléphone", "adresse", "secteur", "type de travaux", "durée", "prix"):
            self.assertIn(mot, erreurs[0])
        self.assertEqual(self.etat(i)[:3], ("soumission", None, None))

    def test_la_date_de_reprise_doit_etre_a_venir(self):
        i = self.accepte()
        for date in (AUJOURDHUI, jour_dans(-5), "demain", "2026-02-30"):
            self.assertTrue(noyau.mettre_en_attente(self.conn, i, date), date)
        self.assertEqual(self.etat(i)[0], "a_planifier")

    def test_seuls_un_chantier_a_planifier_ou_une_soumission_se_mettent_en_attente(self):
        planifie = noyau.mettre_en_attente(self.conn, 3, jour_dans(30))                    # chantier planifié dans une journée
        self.assertTrue(planifie)
        self.assertIn("retire-le d'abord", planifie[0])
        self.assertTrue(noyau.mettre_en_attente(self.conn, 2, jour_dans(30)))              # terminé
        i = self.accepte()
        noyau.annuler_chantier(self.conn, i)
        self.assertTrue(noyau.mettre_en_attente(self.conn, i, jour_dans(30)))              # annulé
        refusee = self.complete(adresse="2 Rue B")
        noyau.refuser_soumission(self.conn, refusee)
        self.assertTrue(noyau.mettre_en_attente(self.conn, refusee, jour_dans(30)))        # refusée
        self.assertTrue(noyau.mettre_en_attente(self.conn, 999, jour_dans(30)))
        self.assertEqual(self.etat(3)[0], "planifie")

    def test_changer_la_date_d_un_chantier_deja_en_attente(self):
        i = self.accepte()
        noyau.mettre_en_attente(self.conn, i, jour_dans(30))
        self.assertEqual(noyau.mettre_en_attente(self.conn, i, jour_dans(120)), [])
        self.assertEqual(self.etat(i)[:3], ("en_attente", AUJOURDHUI, jour_dans(120)))
        self.assertEqual(noyau.mettre_en_attente(self.conn, i), [])
        self.assertEqual(self.etat(i)[:3], ("en_attente", AUJOURDHUI, None))

    def test_sortir_de_l_attente(self):
        i = self.accepte()
        self.assertTrue(noyau.sortir_de_l_attente(self.conn, i))                           # il n'est pas en attente
        noyau.mettre_en_attente(self.conn, i, jour_dans(30))
        self.assertEqual(noyau.sortir_de_l_attente(self.conn, i), [])
        statut, _, reprise, genre, _, depuis = self.etat(i)
        self.assertEqual((statut, reprise, depuis), ("a_planifier", AUJOURDHUI, AUJOURDHUI))    # le délai d'attente repart d'aujourd'hui
        self.assertTrue(noyau.sortir_de_l_attente(self.conn, 999))

    def test_le_retour_automatique_a_la_date_de_reprise(self):
        i = self.accepte()
        j = self.accepte(adresse="2 Rue B")
        k = self.accepte(adresse="3 Rue C")
        noyau.mettre_en_attente(self.conn, i, jour_dans(10))
        noyau.mettre_en_attente(self.conn, j, jour_dans(40))
        noyau.mettre_en_attente(self.conn, k)                                              # jusqu'à nouvel ordre : ne revient jamais tout seul
        today = datetime.date.today()
        self.assertEqual(noyau.reprendre_les_attentes(self.conn), 0)
        self.assertEqual(noyau.reprendre_les_attentes(self.conn, today + datetime.timedelta(days=9)), 0)
        self.assertEqual(noyau.reprendre_les_attentes(self.conn, today + datetime.timedelta(days=10)), 1)        # le jour dit
        self.assertEqual(self.etat(i)[:3], ("a_planifier", AUJOURDHUI, jour_dans(10)))
        self.assertEqual(self.etat(i)[5], jour_dans(10))                                   # son délai d'attente compte depuis la date de reprise
        self.assertEqual(self.etat(j)[0], "en_attente")
        self.assertEqual(noyau.reprendre_les_attentes(self.conn, today + datetime.timedelta(days=500)), 1)       # j revient, pas k
        self.assertEqual((self.etat(j)[0], self.etat(k)[0]), ("a_planifier", "en_attente"))
        self.assertEqual(noyau.reprendre_les_attentes(self.conn, today + datetime.timedelta(days=500)), 0)

    def test_un_chantier_en_attente_ne_passe_pas_devant_les_autres(self):
        i = self.accepte()
        noyau.mettre_en_attente(self.conn, i, jour_dans(200))
        self.assertEqual(self.etat(i)[5], AUJOURDHUI)                                      # son rang vient de l'acceptation, pas de la date de reprise

    def test_remettre_en_soumission_depuis_l_attente(self):
        i = self.accepte()
        noyau.mettre_en_attente(self.conn, i, jour_dans(30))
        self.assertEqual(noyau.remettre_en_soumission(self.conn, i), [])
        self.assertEqual(self.etat(i)[:4], ("soumission", None, None, "soumission"))

    def test_les_autres_chemins_ne_contournent_pas_l_attente(self):
        i = self.accepte()
        self.assertTrue(noyau.changer_statut(self.conn, i, "en_attente"))                  # « En attente » demande sa date : action dédiée
        noyau.mettre_en_attente(self.conn, i, jour_dans(30))
        self.assertTrue(noyau.changer_statut(self.conn, i, "planifie", date_prevue=jour_dans(5), duree="2"))
        self.assertTrue(noyau.changer_statut(self.conn, i, "termine"))
        self.assertTrue(noyau.planifier_lot(self.conn, [i], jour_dans(5)))
        self.assertTrue(noyau.terminer_chantier(self.conn, i))
        self.assertEqual(self.etat(i)[0], "en_attente")
        self.assertEqual(noyau.changer_statut(self.conn, i, "a_planifier"), [])           # « Retirer » = sortir de l'attente
        self.assertEqual(self.etat(i)[:3], ("a_planifier", AUJOURDHUI, AUJOURDHUI))

    def test_annuler_puis_rouvrir_un_chantier_en_attente(self):
        i = self.accepte()
        noyau.mettre_en_attente(self.conn, i, jour_dans(30))
        self.assertEqual(noyau.annuler_chantier(self.conn, i), [])
        self.assertEqual(self.etat(i)[:4], ("annule", AUJOURDHUI, jour_dans(30), "chantier"))      # un chantier annulé reste un chantier
        self.assertEqual(noyau.rouvrir_chantier(self.conn, i), [])
        self.assertEqual(self.etat(i)[:3], ("a_planifier", AUJOURDHUI, AUJOURDHUI))                # il revient dans la file, délai remis à zéro

    def test_en_attente_n_est_plus_une_soumission(self):
        self.assertEqual(noyau.STATUTS_SOUMISSION, ("soumission",))
        i = self.accepte()
        noyau.mettre_en_attente(self.conn, i)
        self.assertTrue(noyau.accepter_soumission(self.conn, i))                           # déjà accepté
        self.assertTrue(noyau.refuser_soumission(self.conn, i))
        v, erreurs = noyau.lire_ligne({"statut": "en_attente", "client_nom": "Roy"}, ALIAS, False)   # une fiche en attente est un chantier : strict
        self.assertTrue(erreurs)

    def test_decaler_mois(self):
        d = datetime.date
        for jour, n, attendu in ((d(2026, 1, 31), 1, d(2026, 2, 28)), (d(2024, 1, 31), 1, d(2024, 2, 29)), (d(2026, 10, 7), -12, d(2025, 10, 7)),
                                 (d(2026, 12, 15), 1, d(2027, 1, 15)), (d(2026, 1, 15), -1, d(2025, 12, 15)), (d(2026, 5, 31), 6, d(2026, 11, 30))):
            self.assertEqual(noyau.decaler_mois(jour, n), attendu)


class TestMigrations(unittest.TestCase):
    """Une base d'un format précédent (v8, v9 ou v10, avec des données) est migrée sans perte, après une copie de sécurité."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dossier = Path(self._tmp.name) / "data"
        self.dossier.mkdir()

    def base_v9(self, nom="v9.db"):
        db = self.dossier / nom
        c = sqlite3.connect(db, isolation_level=None)
        c.executescript((RACINE / "tests" / "schema_v9.sql").read_text(encoding="utf-8"))
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("INSERT INTO clients (nom, prenom, telephone, adresse, ville) VALUES ('Gagnon', 'Marie', '+14505550142', '1 Rue A', 'Mirabel')")
        c.execute("INSERT INTO clients (entreprise, adresse, ville, secteur) VALUES ('Syndicat X', '2 Rue B', 'Blainville', 'centre_ville')")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, duree_estimee_h, prix_ht) VALUES (1, 'en_attente', '2026-09-01', 2, 100)")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, duree_estimee_h, prix_ht) VALUES (1, 'a_planifier', '2026-09-02', 2, 100)")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, duree_estimee_h, prix_ht) VALUES (2, 'soumission', '2026-09-03', 2, 100)")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, date_prevue, duree_estimee_h, prix_ht) VALUES (2, 'termine', '2026-08-02', '2026-08-10', 2, 100)")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission) VALUES (2, 'annule', '2026-07-01')")
        c.execute("INSERT INTO chantier_travaux VALUES (4, 'emondage', 'x')")
        c.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (4, '2026-08-10', 50, 'interac')")
        c.close()
        return db

    def base_v10(self, nom="v10.db"):
        """Une base du format précédent (frais sorti du programme précédent) : « En attente » y est un vieux nom de « soumission »."""
        db = self.dossier / nom
        c = sqlite3.connect(db, isolation_level=None)
        c.executescript((RACINE / "tests" / "schema_v10.sql").read_text(encoding="utf-8"))
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("INSERT INTO clients (nom, prenom, telephone, adresse, ville) VALUES ('Gagnon', 'Marie', '+14505550142', '1 Rue A', 'Mirabel')")
        c.execute("INSERT INTO clients (entreprise) VALUES ('Syndicat X')")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, duree_estimee_h, prix_ht) VALUES (1, 'en_attente', '2026-09-01', 2, 100)")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, accepte_le, duree_estimee_h, prix_ht, cree_par)"
                  " VALUES (1, 'a_planifier', '2026-09-02', '2026-09-04', 2, 100, 'Marc')")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, cree_par) VALUES (2, 'soumission', '2026-09-03', 'Alice')")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission, accepte_le) VALUES (2, 'annule', '2026-07-01', '2026-07-02')")
        c.execute("INSERT INTO chantiers (client_id, statut, date_soumission) VALUES (2, 'annule', '2026-07-05')")
        c.execute("INSERT INTO raccourcis (utilisateur_id, page, libelle, filtre, ordre) VALUES (NULL, 'chantiers', 'Planifiés', 'statut=planifie', 10)")
        c.close()
        return db

    def test_migration_complete_depuis_v9(self):
        db = self.base_v9()
        conn, existait = noyau.ouvrir_base(db)
        self.assertTrue(existait)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], noyau.VERSION_SCHEMA)
        self.assertEqual(conn.execute("SELECT id, statut, accepte_le, cree_par, reprise_le FROM chantiers ORDER BY id").fetchall(),
                         [(1, "soumission", None, None, None), (2, "a_planifier", "2026-09-02", None, None), (3, "soumission", None, None, None),
                          (4, "termine", "2026-08-02", None, None), (5, "annule", "2026-07-01", None, None)])      # en attente -> soumission ; le reste est déjà accepté
        self.assertEqual(conn.execute("SELECT id, nom, entreprise, adresse, ville, secteur FROM clients ORDER BY id").fetchall(),
                         [(1, "Gagnon", None, "1 Rue A", "Mirabel", None), (2, None, "Syndicat X", "2 Rue B", "Blainville", "centre_ville")])
        self.assertEqual(conn.execute("SELECT genre FROM v_chantiers ORDER BY chantier_id").fetchall(),
                         [("soumission",), ("chantier",), ("soumission",), ("chantier",), ("chantier",)])
        self.assertEqual(conn.execute("SELECT count(*), sum(montant) FROM paiements").fetchone(), (1, 50.0))
        self.assertEqual(conn.execute("SELECT type_travaux FROM chantier_travaux").fetchall(), [("emondage",)])
        self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        conn.execute("INSERT INTO clients (nom) VALUES (NULL)")                                        # les nouvelles règles sont en place
        conn.close()
        copies = list((self.dossier / "sauvegardes").glob("*avant_migration_v9*.db"))
        self.assertEqual(len(copies), 1)                                                             # copie de sécurité faite avant
        ancienne = sqlite3.connect(copies[0])
        self.assertEqual(ancienne.execute("PRAGMA user_version").fetchone()[0], 9)
        ancienne.close()

    def test_migration_depuis_v10(self):
        db = self.base_v10()
        conn, _ = noyau.ouvrir_base(db)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], noyau.VERSION_SCHEMA)
        self.assertEqual(conn.execute("SELECT id, statut, accepte_le, cree_par, reprise_le FROM chantiers ORDER BY id").fetchall(),
                         [(1, "soumission", None, None, None),                       # l'ancien « En attente » (soumission remise) redevient une soumission
                          (2, "a_planifier", "2026-09-04", "Marc", None), (3, "soumission", None, "Alice", None),
                          (4, "annule", "2026-07-02", None, None), (5, "annule", None, None, None)])
        self.assertEqual(conn.execute("SELECT chantier_id, genre, statut_paiement FROM v_chantiers ORDER BY chantier_id").fetchall(),
                         [(1, "soumission", "sans_objet"), (2, "chantier", "a_venir"), (3, "soumission", "sans_objet"),
                          (4, "chantier", "sans_objet"), (5, "soumission", "sans_objet")])
        self.assertEqual(conn.execute("SELECT libelle, filtre FROM raccourcis").fetchall(), [("Planifiés", "statut=planifie")])    # les raccourcis restent
        self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        # la nouvelle fonction est là : un chantier se met en attente, avec une date de retour
        self.assertEqual(noyau.mettre_en_attente(conn, 2, (datetime.date.today() + datetime.timedelta(days=30)).isoformat()), [])
        self.assertEqual(conn.execute("SELECT statut FROM chantiers WHERE id = 2").fetchone(), ("en_attente",))
        conn.close()
        copies = list((self.dossier / "sauvegardes").glob("*avant_migration_v10*.db"))
        self.assertEqual(len(copies), 1)
        ancienne = sqlite3.connect(copies[0])
        self.assertEqual(ancienne.execute("PRAGMA user_version").fetchone()[0], 10)
        ancienne.close()

    def test_les_protections_survivent_a_la_migration(self):
        for base in (self.base_v9("a.db"), self.base_v10("b.db")):
            conn, _ = noyau.ouvrir_base(base)
            noms = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
            self.assertEqual(len(noms), 7)
            conn.execute("INSERT INTO chantiers (client_id, statut, date_prevue, duree_estimee_h, prix_ht) VALUES (1, 'termine', '2026-01-01', 1, 10)")
            termine = conn.execute("SELECT max(id) FROM chantiers").fetchone()[0]
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("UPDATE chantiers SET prix_ht = 1 WHERE id = ?", (termine,))             # chantier terminé : verrouillé
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute("DELETE FROM chantiers WHERE id = ?", (termine,))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO chantiers (client_id, statut, accepte_le) VALUES (1, 'a_planifier', '2026-02-30')")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO chantiers (client_id, statut, reprise_le) VALUES (1, 'en_attente', '2026-13-01')")
            conn.close()

    def test_la_base_migree_est_identique_a_une_base_neuve(self):
        neuve, _ = noyau.ouvrir_base(self.dossier / "neuve.db")

        def structure(c):
            colonnes = {t: [tuple(r[1:]) for r in c.execute(f"PRAGMA table_info({t})")] for (t,) in
                        c.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
            sql = {n: " ".join(s.replace('"', "").replace("IF NOT EXISTS ", "").split())
                   for n, s in c.execute("SELECT name, sql FROM sqlite_master WHERE type IN ('view', 'trigger', 'index') AND sql IS NOT NULL")}
            return colonnes, sql
        sql_tables = lambda c, t: " ".join(c.execute("SELECT sql FROM sqlite_master WHERE name = ?", (t,)).fetchone()[0].replace('"', "").split())
        (col_n, sql_n) = structure(neuve)
        for depart in (self.base_v9("a.db"), self.base_v10("b.db")):
            migree, _ = noyau.ouvrir_base(depart)
            col_m, sql_m = structure(migree)
            self.assertEqual(col_m, col_n, depart.name)
            self.assertEqual(sql_m, sql_n, depart.name)
            for table in ("clients", "raccourcis"):
                self.assertEqual(sql_tables(migree, table), sql_tables(neuve, table), (depart.name, table))
            migree.close()
        neuve.close()

    def test_migration_depuis_v8(self):
        db = self.base_v9("v8.db")
        c = sqlite3.connect(db, isolation_level=None)
        c.executescript("DROP TABLE sessions; DROP TABLE utilisateurs;")
        c.execute("PRAGMA user_version = 8")
        c.close()
        conn, _ = noyau.ouvrir_base(db)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], noyau.VERSION_SCHEMA)
        self.assertEqual(conn.execute("SELECT count(*) FROM chantiers").fetchone()[0], 5)
        self.assertEqual(conn.execute("SELECT count(*) FROM utilisateurs").fetchone()[0], 0)
        conn.close()

    def test_une_migration_qui_echoue_ne_change_rien(self):
        for fabrique, version in ((self.base_v9, 9), (self.base_v10, 10)):
            db = fabrique(f"echec{version}.db")
            c = sqlite3.connect(db, isolation_level=None)
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("INSERT INTO chantiers (client_id, statut) VALUES (99, 'soumission')")            # lien brisé : la migration doit refuser
            c.close()
            with self.assertRaises(sqlite3.IntegrityError):
                noyau.ouvrir_base(db)
            c = sqlite3.connect(db)
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], version)
            self.assertEqual(c.execute("SELECT count(*) FROM clients").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT count(*) FROM pragma_table_info('chantiers') WHERE name = 'reprise_le'").fetchone()[0], 0)
            self.assertIsNotNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'v_chantiers'").fetchone())
            c.close()

    def test_les_definitions_figees_ne_dependent_pas_du_schema_courant(self):
        """La migration 9 -> 10 lit ses tables dans son propre fichier : le schéma courant peut changer sans la casser."""
        instructions = list(noyau._instructions((RACINE / "schema" / "migration_v9_v10.sql").read_text(encoding="utf-8")))
        self.assertEqual(len(instructions), 3)
        self.assertIn("CREATE TABLE clients_nouveau", instructions[0])
        self.assertIn("CREATE TABLE raccourcis", instructions[1])
        self.assertIn("CREATE INDEX idx_raccourcis_utilisateur", instructions[2])


if __name__ == "__main__":
    unittest.main()
