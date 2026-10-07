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


class TestMigrationV10(unittest.TestCase):
    """Une base du format v9 (avec des données) est migrée sans perte, après une copie de sécurité."""

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

    def test_migration_complete(self):
        db = self.base_v9()
        conn, existait = noyau.ouvrir_base(db)
        self.assertTrue(existait)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 10)
        self.assertEqual(conn.execute("SELECT id, statut, accepte_le, cree_par FROM chantiers ORDER BY id").fetchall(),
                         [(1, "soumission", None, None), (2, "a_planifier", "2026-09-02", None), (3, "soumission", None, None),
                          (4, "termine", "2026-08-02", None), (5, "annule", "2026-07-01", None)])      # en attente -> soumission ; le reste est déjà accepté
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

    def test_les_protections_survivent_a_la_migration(self):
        conn, _ = noyau.ouvrir_base(self.base_v9())
        noms = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        self.assertEqual(len(noms), 7)
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("UPDATE chantiers SET prix_ht = 1 WHERE id = 4")                            # chantier terminé : verrouillé
        with self.assertRaises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM chantiers WHERE id = 4")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO chantiers (client_id, statut, accepte_le) VALUES (1, 'a_planifier', '2026-02-30')")
        conn.close()

    def test_la_base_migree_est_identique_a_une_base_neuve(self):
        migree, _ = noyau.ouvrir_base(self.base_v9())
        neuve, _ = noyau.ouvrir_base(self.dossier / "neuve.db")

        def structure(c):
            colonnes = {t: [tuple(r[1:]) for r in c.execute(f"PRAGMA table_info({t})")] for (t,) in
                        c.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
            sql = {n: " ".join(s.replace('"', "").replace("IF NOT EXISTS ", "").split())
                   for n, s in c.execute("SELECT name, sql FROM sqlite_master WHERE type IN ('view', 'trigger', 'index') AND sql IS NOT NULL")}
            return colonnes, sql
        (col_m, sql_m), (col_n, sql_n) = structure(migree), structure(neuve)
        self.assertEqual(col_m, col_n)
        self.assertEqual(sql_m, sql_n)
        sql_tables = lambda c, t: " ".join(c.execute("SELECT sql FROM sqlite_master WHERE name = ?", (t,)).fetchone()[0].replace('"', "").split())
        self.assertEqual(sql_tables(migree, "clients"), sql_tables(neuve, "clients"))
        self.assertEqual(sql_tables(migree, "raccourcis"), sql_tables(neuve, "raccourcis"))
        migree.close()
        neuve.close()

    def test_migration_depuis_v8(self):
        db = self.base_v9("v8.db")
        c = sqlite3.connect(db, isolation_level=None)
        c.executescript("DROP TABLE sessions; DROP TABLE utilisateurs;")
        c.execute("PRAGMA user_version = 8")
        c.close()
        conn, _ = noyau.ouvrir_base(db)
        self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 10)
        self.assertEqual(conn.execute("SELECT count(*) FROM chantiers").fetchone()[0], 5)
        self.assertEqual(conn.execute("SELECT count(*) FROM utilisateurs").fetchone()[0], 0)
        conn.close()

    def test_une_migration_qui_echoue_ne_change_rien(self):
        db = self.base_v9()
        c = sqlite3.connect(db, isolation_level=None)
        c.execute("PRAGMA foreign_keys = OFF")
        c.execute("INSERT INTO chantiers (client_id, statut) VALUES (99, 'soumission')")                # lien brisé : la migration doit refuser
        c.close()
        with self.assertRaises(sqlite3.IntegrityError):
            noyau.ouvrir_base(db)
        c = sqlite3.connect(db)
        self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 9)
        self.assertEqual(c.execute("SELECT count(*) FROM clients").fetchone()[0], 2)
        self.assertIsNotNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'v_chantiers'").fetchone() or None)
        c.close()


if __name__ == "__main__":
    unittest.main()
