"""Sauvegardes de la base : une par jour, purge, copie hors du disque et restauration.

- Une sauvegarde par jour dans data/sauvegardes/ (au démarrage, puis une vérification toutes les heures).
- Purge : toutes les sauvegardes des 30 derniers jours, ensuite la plus ancienne de chaque mois.
  Les copies « avant_migration » et « avant_restauration » ne sont jamais supprimées.
- Copie externe : si data/copie_externe.txt contient un dossier (clé USB, disque externe), les sauvegardes et les photos y sont copiées.
- Restauration : python restaurer_sauvegarde.py (ou restaurer_sauvegarde.bat), programme fermé.
"""
import datetime
import re
import shutil
import sqlite3
import sys
import threading
from pathlib import Path

import noyau

JOURS_COMPLETS = 30
PROTEGES = ("avant_migration", "avant_restauration")
FICHIER_COPIE_EXTERNE = "copie_externe.txt"
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")


def dossier_sauvegardes(db):
    return Path(db).parent / "sauvegardes"


def _date_du_nom(nom):
    """Date (datetime.date) au début du nom de fichier, ou None si le nom ne commence pas par une date valide."""
    m = _DATE.match(nom)
    if not m:
        return None
    try:
        return datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _base_non_vide(db):
    db = Path(db)
    return db.exists() and db.stat().st_size > 0


# ---------------------------------------------------------------------------
# Sauvegarde du jour
# ---------------------------------------------------------------------------
def sauvegarde_du_jour(db, aujourdhui=None, silencieux=False):
    """Crée la sauvegarde du jour s'il n'y en a pas encore, puis purge et copie. Retourne le chemin créé ou None."""
    db = Path(db)
    if not _base_non_vide(db):
        return None
    aujourdhui = aujourdhui or datetime.date.today()
    dossier = dossier_sauvegardes(db)
    if list(dossier.glob(f"{aujourdhui:%Y-%m-%d}_*")):
        return None
    chemin = noyau.sauvegarder(db, "quotidienne")
    purger(dossier, aujourdhui)
    copier_vers_externe(db, silencieux)
    return chemin


def demarrer_sauvegarde_quotidienne(db, intervalle_s=3600):
    """Lance un fil (daemon) qui sauvegarde au démarrage puis vérifie toutes les `intervalle_s` secondes.

    Le fil expose `arret` (threading.Event) pour l'arrêter. Aucune erreur ne l'arrête : elle est seulement affichée.
    """
    arret = threading.Event()
    derniere_erreur = [None]

    def boucle():
        while not arret.is_set():
            try:
                chemin = sauvegarde_du_jour(db, silencieux=True)
                if chemin:
                    print(f"Sauvegarde du jour : {chemin}")
                # à chaque passage : les photos de la journée suivent, et une clé rebranchée est rattrapée
                erreur = copier_vers_externe(db, silencieux=True)["erreur"]
                if erreur and erreur != derniere_erreur[0]:                    # le même message n'est pas répété toutes les heures
                    print(erreur)
                derniere_erreur[0] = erreur
            except Exception as e:  # noqa: BLE001 - rien ne doit tuer le fil
                print(f"Sauvegarde du jour impossible : {e}")
            arret.wait(intervalle_s)

    fil = threading.Thread(target=boucle, name="sauvegarde-quotidienne", daemon=True)
    fil.arret = arret
    fil.start()
    return fil


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------
def purger(dossier, aujourdhui=None):
    """Garde tout ce qui a moins de 30 jours, puis la plus ancienne sauvegarde de chaque mois. Retourne les fichiers supprimés."""
    dossier = Path(dossier)
    aujourdhui = aujourdhui or datetime.date.today()
    limite = aujourdhui - datetime.timedelta(days=JOURS_COMPLETS)
    if not dossier.is_dir():
        return []
    anciens = {}                                   # (année, mois) -> [(nom, chemin)]
    for f in dossier.iterdir():
        if not f.is_file() or any(p in f.name for p in PROTEGES):
            continue
        d = _date_du_nom(f.name)
        if d is None or d > limite:
            continue
        anciens.setdefault((d.year, d.month), []).append((f.name, f))
    supprimes = []
    for fichiers in anciens.values():
        fichiers.sort()
        for _, f in fichiers[1:]:                  # la plus ancienne du mois est gardée
            try:
                f.unlink()
                supprimes.append(f)
            except OSError:
                pass
    return supprimes


# ---------------------------------------------------------------------------
# Copie externe
# ---------------------------------------------------------------------------
def dossier_externe(db):
    """Dossier de la copie externe (première ligne de data/copie_externe.txt) ou None."""
    fichier = Path(db).parent / FICHIER_COPIE_EXTERNE
    try:
        texte = fichier.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    for ligne in texte.splitlines():
        ligne = ligne.strip().strip('"').strip()
        if ligne:
            return Path(ligne)
    return None


def message_copie_externe(db):
    """Ligne d'information affichée au démarrage de la vraie base."""
    dossier = dossier_externe(db)
    if dossier:
        return f"Copie externe des sauvegardes et des photos : {dossier}"
    return ("Aucune copie externe configurée : pour copier les sauvegardes et les photos sur une clé USB ou un disque externe, "
            f"crée le fichier {Path(db).parent / FICHIER_COPIE_EXTERNE} avec, sur une seule ligne, le dossier voulu (ex. E:\\SylvainCulteur).")


def _a_copier(source, cible):
    if not cible.exists():
        return True
    a, b = source.stat(), cible.stat()
    return a.st_size != b.st_size or abs(a.st_mtime - b.st_mtime) > 2


def _copier_arbre(source, cible, nom_seulement=False):
    copies = 0
    if not source.is_dir():
        return 0
    for f in sorted(source.rglob("*")):
        if not f.is_file():
            continue
        dest = cible / f.relative_to(source)
        if nom_seulement:
            if dest.exists():
                continue
        elif not _a_copier(f, dest):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        copies += 1
    return copies


def copier_vers_externe(db, silencieux=False):
    """Copie les sauvegardes et les photos manquantes vers le dossier externe. Ne supprime rien, ne lève jamais d'exception.

    Retourne {"copies": nombre de fichiers copiés, "erreur": message ou None, "dossier": Path ou None}.
    """
    compte = {"copies": 0, "erreur": None, "dossier": None}
    try:
        dossier = dossier_externe(db)
        compte["dossier"] = dossier
        if dossier is None:
            return compte
        nuage = noyau.service_nuage(dossier)
        if nuage:
            compte["erreur"] = f"Copie externe refusée : le dossier {dossier} est synchronisé par {nuage}."
            return compte
        data = Path(db).parent.resolve()
        cible = dossier.resolve()
        if cible == data or data in cible.parents:
            compte["erreur"] = "Copie externe refusée : le dossier doit être en dehors du dossier data/."
            return compte
        if not dossier.is_dir():
            compte["erreur"] = f"Copie externe impossible : le dossier {dossier} est introuvable (clé ou disque débranché ?)."
            return compte
        compte["copies"] += _copier_arbre(dossier_sauvegardes(db), dossier / "sauvegardes", nom_seulement=True)
        compte["copies"] += _copier_arbre(Path(db).parent / "photos", dossier / "photos")
    except Exception as e:  # noqa: BLE001
        compte["erreur"] = f"Copie externe impossible : {e}"
    if compte["erreur"] and not silencieux:
        print(compte["erreur"])
    return compte


# ---------------------------------------------------------------------------
# Restauration
# ---------------------------------------------------------------------------
def lister(db):
    """[(chemin, date et heure, taille en octets)] des sauvegardes, les plus récentes d'abord."""
    dossier = dossier_sauvegardes(db)
    if not dossier.is_dir():
        return []
    res = []
    for f in dossier.glob("*.db"):
        if f.is_file():
            st = f.stat()
            res.append((f, datetime.datetime.fromtimestamp(st.st_mtime), st.st_size))
    res.sort(key=lambda t: t[0].name, reverse=True)
    return res


def verifier(fichier):
    """Ouvre la sauvegarde en lecture seule et la contrôle. Retourne (ok, message)."""
    fichier = Path(fichier)
    if not fichier.is_file() or fichier.stat().st_size == 0:
        return False, "Fichier introuvable ou vide."
    conn = None
    try:
        conn = sqlite3.connect(f"{fichier.resolve().as_uri()}?mode=ro", uri=True)
        resultat = conn.execute("PRAGMA integrity_check").fetchone()[0]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error as e:
        return False, f"Sauvegarde illisible : {e}"
    finally:
        if conn is not None:
            conn.close()
    if resultat != "ok":
        return False, f"Sauvegarde abîmée : {resultat}"
    if not 8 <= version <= noyau.VERSION_SCHEMA:
        return False, f"Format de base non reconnu (version {version})."
    return True, f"Sauvegarde en bon état (format {version})."


def restaurer(db, fichier):
    """Remplace la base par la sauvegarde. Retourne le chemin de la copie « avant_restauration » de la base actuelle."""
    db = Path(db)
    fichier = Path(fichier)
    ok, message = verifier(fichier)
    if not ok:
        raise ValueError(message)
    avant = None
    if _base_non_vide(db):
        avant = noyau.sauvegarder(db, "avant_restauration")
    src = sqlite3.connect(f"{fichier.resolve().as_uri()}?mode=ro", uri=True)
    dst = sqlite3.connect(db)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return avant


def _taille(octets):
    return f"{octets / 1024:.0f} Ko" if octets < 1024 * 1024 else f"{octets / 1024 / 1024:.1f} Mo"


def main(db=None):
    db = Path(db) if db else noyau.DB_DEFAUT
    print(f"Restaurer une sauvegarde de : {db}")
    print("IMPORTANT : ferme d'abord le programme (la fenêtre noire de l'interface) avant de restaurer.")
    sauvegardes = lister(db)
    if not sauvegardes:
        print("Aucune sauvegarde trouvée dans", dossier_sauvegardes(db))
        return 1
    print("\nSauvegardes disponibles (les plus récentes d'abord) :")
    for i, (f, quand, taille) in enumerate(sauvegardes, 1):
        print(f"  {i:>3}. {f.name}   {quand:%Y-%m-%d %H:%M}   {_taille(taille)}")
    choix = input("\nNuméro de la sauvegarde à restaurer (Entrée pour annuler) : ").strip()
    if not choix:
        print("Annulé : rien n'a été changé.")
        return 0
    if not choix.isdigit() or not 1 <= int(choix) <= len(sauvegardes):
        print("Numéro invalide : rien n'a été changé.")
        return 1
    fichier = sauvegardes[int(choix) - 1][0]
    ok, message = verifier(fichier)
    print(message)
    if not ok:
        print("Cette sauvegarde ne peut pas être restaurée : rien n'a été changé.")
        return 1
    print(f"\nTes données actuelles seront remplacées par celles de {fichier.name}.")
    print("Une copie des données actuelles sera gardée (avant_restauration).")
    if input("Tape « oui » pour continuer : ").strip().lower() != "oui":
        print("Annulé : rien n'a été changé.")
        return 0
    try:
        avant = restaurer(db, fichier)
    except (ValueError, sqlite3.Error) as e:
        print(f"Restauration impossible : {e}")
        return 1
    if avant:
        print(f"Copie des données d'avant : {avant}")
    print("Restauration terminée. Tu peux relancer le programme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
