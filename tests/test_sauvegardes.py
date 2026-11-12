"""Tests des sauvegardes : sauvegarde du jour, purge, copie externe, vérification et restauration.

    python3 -m unittest discover -s tests -v
"""
import datetime
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import fixtures  # noqa: E402
import noyau  # noqa: E402
import sauvegardes  # noqa: E402

AUJOURDHUI = datetime.date(2026, 11, 11)


def nb_clients(db):
    c = sqlite3.connect(db)
    try:
        return c.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    finally:
        c.close()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.racine = Path(self._tmp.name)
        self.db = self.racine / "data" / "t.db"
        fixtures.creer_exemples(self.db)
        self.dossier = self.db.parent / "sauvegardes"

    def fichier(self, nom, contenu=b"x"):
        self.dossier.mkdir(exist_ok=True)
        f = self.dossier / nom
        f.write_bytes(contenu)
        return f

    def externe(self, ecrire=True):
        ext = self.racine / "externe"
        ext.mkdir(exist_ok=True)
        if ecrire:
            (self.db.parent / "copie_externe.txt").write_text(str(ext) + "\n", encoding="utf-8")
        return ext


class TestSauvegardeDuJour(Base):
    def test_creee_une_seule_fois(self):
        jour = datetime.date.today()                  # noyau.sauvegarder nomme le fichier avec la vraie date
        premiere = sauvegardes.sauvegarde_du_jour(self.db, jour)
        self.assertIsNotNone(premiere)
        self.assertTrue(premiere.exists())
        self.assertIsNone(sauvegardes.sauvegarde_du_jour(self.db, jour))

    def test_une_sauvegarde_du_jour_existante_suffit(self):
        self.fichier(f"{AUJOURDHUI:%Y-%m-%d}_080000_demarrage.db")
        self.assertIsNone(sauvegardes.sauvegarde_du_jour(self.db, AUJOURDHUI))

    def test_base_absente_ou_vide(self):
        self.assertIsNone(sauvegardes.sauvegarde_du_jour(self.racine / "data" / "absente.db", AUJOURDHUI))
        vide = self.racine / "data" / "vide.db"
        vide.write_bytes(b"")
        self.assertIsNone(sauvegardes.sauvegarde_du_jour(vide, AUJOURDHUI))

    def test_copie_externe_et_purge_appelees(self):
        ext = self.externe()
        ancienne = self.fichier("2026-01-05_080000_x.db")
        self.fichier("2026-01-20_080000_x.db")
        chemin = sauvegardes.sauvegarde_du_jour(self.db, AUJOURDHUI)
        self.assertIsNotNone(chemin)
        self.assertTrue(ancienne.exists())
        self.assertFalse((self.dossier / "2026-01-20_080000_x.db").exists())
        self.assertTrue((ext / "sauvegardes" / chemin.name).exists())

    def test_fil_survit_aux_erreurs(self):
        with mock.patch.object(sauvegardes, "sauvegarde_du_jour", side_effect=RuntimeError("boum")) as m, \
                mock.patch("builtins.print"):
            fil = sauvegardes.demarrer_sauvegarde_quotidienne(self.db, intervalle_s=0.01)
            fin = time.time() + 5
            while m.call_count < 3 and time.time() < fin:
                time.sleep(0.01)
            vivant = fil.is_alive()
            fil.arret.set()
            fil.join(2)
        self.assertTrue(fil.daemon)
        self.assertTrue(vivant)
        self.assertGreaterEqual(m.call_count, 3)

    def test_fil_rattrape_une_cle_rebranchee(self):
        ext = self.racine / "cle"                                   # clé débranchée au départ
        (self.db.parent / "copie_externe.txt").write_text(str(ext), encoding="utf-8")
        photo = self.db.parent / "photos" / "chantier-1" / "a.jpg"
        photo.parent.mkdir(parents=True)
        photo.write_bytes(b"photo")
        with mock.patch("builtins.print") as affiche:
            fil = sauvegardes.demarrer_sauvegarde_quotidienne(self.db, intervalle_s=0.01)
            fin = time.time() + 5
            while len(list(self.dossier.glob("*.db"))) < 1 and time.time() < fin:
                time.sleep(0.01)
            time.sleep(0.1)                                         # plusieurs passages sans la clé
            messages = [str(a.args[0]) for a in affiche.call_args_list if "introuvable" in str(a.args[0])]
            ext.mkdir()                                             # clé rebranchée
            while not (ext / "photos" / "chantier-1" / "a.jpg").exists() and time.time() < fin:
                time.sleep(0.01)
            fil.arret.set()
            fil.join(2)
        self.assertEqual(len(messages), 1)                          # le message n'est pas répété à chaque passage
        self.assertEqual(len(list((ext / "sauvegardes").glob("*.db"))), 1)
        self.assertTrue((ext / "photos" / "chantier-1" / "a.jpg").exists())


class TestPurge(Base):
    def noms(self):
        return sorted(f.name for f in self.dossier.iterdir())

    def test_trente_jours_gardes_puis_une_par_mois(self):
        recents = ["2026-11-10_080000_a.db", "2026-10-13_080000_a.db"]      # 29 jours : gardé
        for n in recents + ["2026-10-12_080000_a.db"]:                       # 30 jours : encore gardé
            self.fichier(n)
        for n in ["2026-09-03_080000_a.db", "2026-09-15_080000_a.db", "2026-09-28_080000_a.db",
                  "2026-08-30_080000_a.db", "2026-08-02_090000_a.db"]:
            self.fichier(n)
        supprimes = sauvegardes.purger(self.dossier, AUJOURDHUI)
        self.assertEqual(sorted(f.name for f in supprimes),
                         ["2026-08-30_080000_a.db", "2026-09-15_080000_a.db", "2026-09-28_080000_a.db"])
        self.assertEqual(self.noms(), ["2026-08-02_090000_a.db", "2026-09-03_080000_a.db", "2026-10-12_080000_a.db",
                                       "2026-10-13_080000_a.db", "2026-11-10_080000_a.db"])

    def test_fichiers_proteges_et_noms_sans_date(self):
        proteges = ["2025-03-01_080000_avant_migration_v10.db", "2025-03-02_080000_avant_restauration.db"]
        autres = ["notes.txt", "2025-13-45_080000_x.db", "sauvegarde_2025-03-01.db"]
        for n in proteges + autres:
            self.fichier(n)
        self.fichier("2025-03-03_080000_x.db")
        self.fichier("2025-03-04_080000_x.db")
        supprimes = sauvegardes.purger(self.dossier, AUJOURDHUI)
        self.assertEqual([f.name for f in supprimes], ["2025-03-04_080000_x.db"])
        for n in proteges + autres:
            self.assertTrue((self.dossier / n).exists(), n)

    def test_dossier_absent(self):
        self.assertEqual(sauvegardes.purger(self.racine / "rien", AUJOURDHUI), [])


class TestCopieExterne(Base):
    def test_configuration_absente_ou_vide(self):
        self.assertIsNone(sauvegardes.dossier_externe(self.db))
        r = sauvegardes.copier_vers_externe(self.db)
        self.assertEqual((r["copies"], r["erreur"]), (0, None))
        (self.db.parent / "copie_externe.txt").write_text("\n  \n", encoding="utf-8")
        self.assertIsNone(sauvegardes.dossier_externe(self.db))
        self.assertIn("copie_externe.txt", sauvegardes.message_copie_externe(self.db))

    def test_sauvegardes_et_photos_incremental_sans_suppression(self):
        ext = self.externe()
        self.fichier("2026-11-10_080000_a.db", b"abc")
        photo = self.db.parent / "photos" / "2026" / "p1.jpg"
        photo.parent.mkdir(parents=True)
        photo.write_bytes(b"photo1")
        r = sauvegardes.copier_vers_externe(self.db)
        self.assertEqual((r["copies"], r["erreur"]), (2, None))
        self.assertEqual((ext / "sauvegardes" / "2026-11-10_080000_a.db").read_bytes(), b"abc")
        self.assertEqual((ext / "photos" / "2026" / "p1.jpg").read_bytes(), b"photo1")
        self.assertEqual(sauvegardes.copier_vers_externe(self.db)["copies"], 0)
        photo.write_bytes(b"photo1 modifiee")                       # taille différente : recopiée
        self.assertEqual(sauvegardes.copier_vers_externe(self.db)["copies"], 1)
        self.assertEqual((ext / "photos" / "2026" / "p1.jpg").read_bytes(), b"photo1 modifiee")
        os.utime(photo, (1000, 1000))                              # date différente : recopiée
        self.assertEqual(sauvegardes.copier_vers_externe(self.db)["copies"], 1)
        photo.unlink()
        (self.dossier / "2026-11-10_080000_a.db").unlink()
        sauvegardes.copier_vers_externe(self.db)
        self.assertTrue((ext / "photos" / "2026" / "p1.jpg").exists())
        self.assertTrue((ext / "sauvegardes" / "2026-11-10_080000_a.db").exists())

    def test_dossier_introuvable_sans_exception(self):
        (self.db.parent / "copie_externe.txt").write_text(str(self.racine / "debranche"), encoding="utf-8")
        r = sauvegardes.copier_vers_externe(self.db)
        self.assertEqual(r["copies"], 0)
        self.assertIn("introuvable", r["erreur"])

    def test_dossier_de_nuage_refuse(self):
        nuage = self.racine / "OneDrive" / "copie"
        nuage.mkdir(parents=True)
        (self.db.parent / "copie_externe.txt").write_text(str(nuage), encoding="utf-8")
        self.fichier("2026-11-10_080000_a.db")
        r = sauvegardes.copier_vers_externe(self.db)
        self.assertEqual(r["copies"], 0)
        self.assertIn("onedrive", r["erreur"].lower())
        self.assertEqual(list(nuage.iterdir()), [])

    def test_dossier_dans_data_refuse(self):
        interne = self.db.parent / "interne"
        interne.mkdir()
        (self.db.parent / "copie_externe.txt").write_text(str(interne), encoding="utf-8")
        self.assertIn("data/", sauvegardes.copier_vers_externe(self.db)["erreur"])


class TestVerifierEtRestaurer(Base):
    def setUp(self):
        super().setUp()
        self.copie = noyau.sauvegarder(self.db, "bonne")
        self.avant = nb_clients(self.db)
        c = sqlite3.connect(self.db)
        c.execute("DELETE FROM clients")
        c.commit()
        c.close()

    def corrompu(self):
        f = self.dossier / "2026-11-01_080000_corrompu.db"
        f.write_bytes(b"ceci n'est pas une base de donnees " * 50)
        return f

    def test_verifier(self):
        ok, msg = sauvegardes.verifier(self.copie)
        self.assertTrue(ok, msg)
        self.assertIn(str(noyau.VERSION_SCHEMA), msg)
        self.assertFalse(sauvegardes.verifier(self.corrompu())[0])
        self.assertFalse(sauvegardes.verifier(self.racine / "absent.db")[0])

    def test_restaurer(self):
        self.assertEqual(nb_clients(self.db), 0)
        avant = sauvegardes.restaurer(self.db, self.copie)
        self.assertEqual(nb_clients(self.db), self.avant)
        self.assertIn("avant_restauration", avant.name)
        self.assertTrue(avant.exists())
        self.assertEqual(nb_clients(avant), 0)

    def test_fichier_invalide_refuse_sans_toucher(self):
        with self.assertRaises(ValueError):
            sauvegardes.restaurer(self.db, self.corrompu())
        self.assertEqual(nb_clients(self.db), 0)
        self.assertEqual(list(self.dossier.glob("*avant_restauration*")), [])

    def test_lister(self):
        a = self.fichier("2026-11-01_080000_a.db", b"1")
        b = self.fichier("2026-11-09_080000_b.db", b"22")
        noms = [t[0].name for t in sauvegardes.lister(self.db)]
        self.assertEqual(len(noms), 3)
        self.assertEqual(noms, sorted(noms, reverse=True))
        self.assertEqual(sauvegardes.lister(self.racine / "x" / "y.db"), [])


class TestMain(Base):
    def setUp(self):
        super().setUp()
        self.copie = noyau.sauvegarder(self.db, "bonne")
        c = sqlite3.connect(self.db)
        c.execute("DELETE FROM clients")
        c.commit()
        c.close()

    def lancer(self, reponses):
        with mock.patch("builtins.input", side_effect=reponses), mock.patch("builtins.print"):
            return sauvegardes.main(self.db)

    def test_annulation(self):
        self.assertEqual(self.lancer([""]), 0)
        self.assertEqual(self.lancer(["1", "non"]), 0)
        self.assertEqual(nb_clients(self.db), 0)
        self.assertEqual(list(self.dossier.glob("*avant_restauration*")), [])

    def test_numero_invalide(self):
        self.assertEqual(self.lancer(["99"]), 1)
        self.assertEqual(nb_clients(self.db), 0)

    def test_restauration(self):
        self.assertEqual(self.lancer(["1", "oui"]), 0)
        self.assertGreater(nb_clients(self.db), 0)
        self.assertEqual(len(list(self.dossier.glob("*avant_restauration*"))), 1)

    def test_aucune_sauvegarde(self):
        vide = self.racine / "autre" / "t.db"
        vide.parent.mkdir()
        with mock.patch("builtins.print"):
            self.assertEqual(sauvegardes.main(vide), 1)


if __name__ == "__main__":
    unittest.main()
