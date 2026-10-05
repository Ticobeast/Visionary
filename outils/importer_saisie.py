#!/usr/bin/env python3
"""Importe une feuille de saisie (CSV « à plat », une ligne = un chantier)
dans la base SQLite de SylvainCulteur.

    python3 outils/importer_saisie.py data/saisie/lot_2026-10-05.csv --simulation
    python3 outils/importer_saisie.py data/saisie/lot_2026-10-05.csv

Ce que fait le script :
  * valide chaque ligne (dates AAAA-MM-JJ, téléphone, code postal, montants...)
    et affiche TOUTES les erreurs avec leur numéro de ligne (celui du tableur)
  * regroupe les lignes d'un même client / d'une même adresse (pas de doublons)
  * ignore les lignes déjà importées : on peut relancer le même fichier
  * est « tout ou rien » : une seule erreur et rien n'est écrit
  * sauvegarde la base avant d'écrire (data/sauvegardes/)

Les corrections de fiches déjà importées se font dans la base (DB Browser),
pas en réimportant une ligne modifiée.

Bibliothèque standard seulement (Python 3.8+).
"""
import argparse
import csv
import datetime
import io
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCHEMA = RACINE / "schema" / "schema.sql"
DB_DEFAUT = RACINE / "data" / "sylvainculteur.db"

# Taux utilisés seulement avec --taxes-auto (pour les lignes sans tps/tvq).
# Les montants importés sont ensuite stockés tels quels : un changement de taux
# futur ne modifie jamais les anciens chantiers.
TAUX_TPS = Decimal("0.05")
TAUX_TVQ = Decimal("0.09975")

# Ordre des colonnes de la feuille de saisie : les plus utilisées d'abord.
COLONNES = [
    "client_nom", "client_prenom", "client_entreprise", "client_telephone",
    "adresse", "ville", "code_postal",
    "type_travaux", "statut", "description",
    "date_soumission", "date_prevue", "heure_prevue", "date_realisee",
    "duree_estimee_h", "duree_reelle_h",
    "prix_ht", "tps", "tvq", "numero_facture", "date_facture",
    "paiement_date", "paiement_montant", "paiement_mode",
    "notes", "notes_acces", "ref_papier", "fichier_papier", "dossier_photos",
    "client_telephone_2", "client_courriel", "client_sms_ok", "client_notes",
    "province", "latitude", "longitude",
]
COLONNES_REQUISES = ("adresse", "ville", "type_travaux", "statut")

STATUTS = ("soumission", "refuse", "accepte", "planifie", "termine", "annule")
MODES = ("comptant", "cheque", "interac", "carte", "autre")

RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_HEURE = re.compile(r"^(\d{1,2})[:hH](\d{2})(?::\d{2})?$")
RE_CODE_POSTAL = re.compile(r"^[A-Z]\d[A-Z]\d[A-Z]\d$")


def cle(texte):
    """Forme comparable : sans accents, minuscules, ponctuation = une espace."""
    if not texte:
        return ""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", str(texte)) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", sans_accents.casefold()).strip()


# ---------------------------------------------------------------------------
# Lecture et validation d'une ligne
# ---------------------------------------------------------------------------
class Ligne:
    """Convertit les cellules d'une ligne en valeurs strictes, en accumulant les erreurs."""

    def __init__(self, brut):
        self.brut = brut
        self.erreurs = []

    def _cellule(self, col):
        v = self.brut.get(col)
        if v is None:
            return None
        v = v.strip()
        return v or None

    def texte(self, col, multiligne=False):
        v = self._cellule(col)
        if v is None or multiligne:
            return v
        return re.sub(r"\s+", " ", v)

    def requis(self, col):
        v = self.texte(col)
        if v is None:
            self.erreurs.append(f"{col} est obligatoire")
        return v

    def jour(self, col):
        v = self._cellule(col)
        if v is None:
            return None
        if RE_DATE.match(v):
            try:
                datetime.date.fromisoformat(v)
                return v
            except ValueError:
                pass
        self.erreurs.append(
            f"{col} « {v} » invalide (format attendu AAAA-MM-JJ, ex. 2026-06-14 ; "
            "dans le tableur, formater la colonne en « Texte »)"
        )
        return None

    def heure(self, col):
        v = self._cellule(col)
        if v is None:
            return None
        m = RE_HEURE.match(v)
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
        self.erreurs.append(f"{col} « {v} » invalide (format attendu HH:MM, ex. 08:30)")
        return None

    def decimal(self, col):
        """Nombre à 2 décimales max ; accepte la virgule décimale, « 1 250,00 $ »."""
        v = self._cellule(col)
        if v is None:
            return None
        s = re.sub(r"[\s $]", "", v).replace(",", ".")
        try:
            d = Decimal(s)
            ok = d.is_finite() and d == d.quantize(Decimal("0.01"))
        except InvalidOperation:
            ok = False
        if not ok:
            self.erreurs.append(f"{col} « {v} » invalide (nombre avec 2 décimales max, ex. 450.00)")
            return None
        return d

    def montant(self, col):
        d = self.decimal(col)
        if d is not None and d < 0:
            self.erreurs.append(f"{col} ne peut pas être négatif")
            return None
        return d

    def duree(self, col):
        d = self.decimal(col)
        if d is not None and not (0 < d <= 24):
            self.erreurs.append(f"{col} « {d} » hors limites (entre 0 et 24 heures, ex. 2.5 pour 2 h 30)")
            return None
        return d

    def coordonnee(self, col, minimum, maximum, exemple):
        v = self._cellule(col)
        if v is None:
            return None
        if re.fullmatch(r"-?\d+([.,]\d+)?", v) and minimum <= float(v.replace(",", ".")) <= maximum:
            return float(v.replace(",", "."))
        self.erreurs.append(f"{col} « {v} » invalide (degrés décimaux entre {minimum} et {maximum}, ex. {exemple})")
        return None

    def telephone(self, col):
        v = self._cellule(col)
        if v is None:
            return None
        chiffres = re.sub(r"\D", "", v)
        if len(chiffres) == 11 and chiffres.startswith("1"):
            chiffres = chiffres[1:]
        if len(chiffres) == 10 and re.fullmatch(r"[2-9]\d\d[2-9]\d{6}", chiffres):
            return "+1" + chiffres
        self.erreurs.append(f"{col} « {v} » invalide (10 chiffres, ex. 450-555-0142)")
        return None

    def code_postal(self, col):
        v = self._cellule(col)
        if v is None:
            return None
        compact = re.sub(r"\s+", "", v).upper()
        if RE_CODE_POSTAL.match(compact):
            return f"{compact[:3]} {compact[3:]}"
        self.erreurs.append(f"{col} « {v} » invalide (format A1A 1A1)")
        return None

    def booleen(self, col):
        v = self._cellule(col)
        if v is None:
            return None
        if cle(v) in ("1", "oui", "o", "true", "vrai", "x"):
            return 1
        if cle(v) in ("0", "non", "n", "false", "faux"):
            return 0
        self.erreurs.append(f"{col} « {v} » invalide (1/0 ou oui/non)")
        return None

    def choix(self, col, valides, alias=None, obligatoire=False):
        v = self._cellule(col)
        if v is None:
            if obligatoire:
                self.erreurs.append(f"{col} est obligatoire")
            return None
        trouve = (alias or {}).get(cle(v))
        if trouve is None and cle(v) in valides:
            trouve = cle(v)
        if trouve is None:
            self.erreurs.append(f"{col} « {v} » inconnu (valeurs permises : {', '.join(sorted(set(valides)))})")
        return trouve

    def chemin(self, col):
        v = self.texte(col)
        if v is None:
            return None
        if (v.startswith("/") or v.endswith("/") or "\\" in v or ".." in v
                or re.match(r"^[A-Za-z]:", v)):
            self.erreurs.append(
                f"{col} « {v} » invalide (chemin relatif à data/, avec des « / », "
                "sans « / » au début ni à la fin, sans « .. »)"
            )
            return None
        return v


def lire_ligne(brut, alias_types, taxes_auto):
    """Retourne (valeurs, erreurs) pour une ligne brute du CSV."""
    L = Ligne(brut)
    v = {}
    v["client_nom"] = L.texte("client_nom")
    v["client_prenom"] = L.texte("client_prenom")
    v["client_entreprise"] = L.texte("client_entreprise")
    if not (v["client_nom"] or v["client_entreprise"]):
        L.erreurs.append("client_nom ou client_entreprise est obligatoire")
    v["client_telephone"] = L.telephone("client_telephone")
    v["client_telephone_2"] = L.telephone("client_telephone_2")
    v["client_courriel"] = L.texte("client_courriel")
    if v["client_courriel"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v["client_courriel"]):
        L.erreurs.append(f"client_courriel « {v['client_courriel']} » invalide")
        v["client_courriel"] = None
    v["client_sms_ok"] = L.booleen("client_sms_ok")
    v["client_notes"] = L.texte("client_notes", multiligne=True)

    v["adresse"] = L.requis("adresse")
    v["ville"] = L.requis("ville")
    prov = L.texte("province")
    v["province"] = prov.upper() if prov else "QC"
    if not re.fullmatch(r"[A-Z]{2}", v["province"]):
        L.erreurs.append(f"province « {prov} » invalide (2 lettres, ex. QC)")
    v["code_postal"] = L.code_postal("code_postal")
    v["latitude"] = L.coordonnee("latitude", 40, 65, "45.6480")
    v["longitude"] = L.coordonnee("longitude", -90, -50, "-74.0920 (le signe « - » est obligatoire)")
    if (v["latitude"] is None) != (v["longitude"] is None):
        L.erreurs.append("latitude et longitude vont ensemble (remplir les deux ou aucune)")
    v["notes_acces"] = L.texte("notes_acces", multiligne=True)

    v["type_travaux"] = L.choix("type_travaux", set(alias_types.values()), alias_types, obligatoire=True)
    v["statut"] = L.choix("statut", STATUTS, obligatoire=True)
    v["description"] = L.texte("description", multiligne=True)
    v["notes"] = L.texte("notes", multiligne=True)
    v["date_soumission"] = L.jour("date_soumission")
    v["date_prevue"] = L.jour("date_prevue")
    v["heure_prevue"] = L.heure("heure_prevue")
    v["date_realisee"] = L.jour("date_realisee")
    v["duree_estimee_h"] = L.duree("duree_estimee_h")
    v["duree_reelle_h"] = L.duree("duree_reelle_h")

    v["prix_ht"] = L.montant("prix_ht")
    v["tps"] = L.montant("tps")
    v["tvq"] = L.montant("tvq")
    if taxes_auto and v["prix_ht"] is not None and v["tps"] is None and v["tvq"] is None:
        cent = Decimal("0.01")
        v["tps"] = (v["prix_ht"] * TAUX_TPS).quantize(cent, ROUND_HALF_UP)
        v["tvq"] = (v["prix_ht"] * TAUX_TVQ).quantize(cent, ROUND_HALF_UP)
    v["numero_facture"] = L.texte("numero_facture")
    v["date_facture"] = L.jour("date_facture")

    v["paiement_date"] = L.jour("paiement_date")
    v["paiement_montant"] = L.montant("paiement_montant")
    v["paiement_mode"] = L.choix("paiement_mode", MODES)
    trio = (v["paiement_date"], v["paiement_montant"], v["paiement_mode"])
    if any(c is not None for c in trio) and not all(c is not None for c in trio):
        if not L.erreurs:  # évite le doublon avec une erreur de format déjà signalée
            L.erreurs.append("paiement_date, paiement_montant et paiement_mode vont ensemble (les trois ou aucun)")
    if v["paiement_montant"] is not None and v["paiement_montant"] == 0:
        L.erreurs.append("paiement_montant doit être supérieur à 0")

    v["ref_papier"] = L.texte("ref_papier")
    v["fichier_papier"] = L.chemin("fichier_papier")
    v["dossier_photos"] = L.chemin("dossier_photos")

    # Cohérence statut / dates (les mêmes règles existent dans la base).
    if v["statut"] == "termine" and not v["date_realisee"] and not any("date_realisee" in e for e in L.erreurs):
        L.erreurs.append("statut « termine » : date_realisee est obligatoire")
    if v["statut"] == "planifie" and not v["date_prevue"] and not any("date_prevue" in e for e in L.erreurs):
        L.erreurs.append("statut « planifie » : date_prevue est obligatoire")
    if v["date_realisee"] and v["statut"] and v["statut"] != "termine":
        L.erreurs.append("date_realisee remplie mais statut n'est pas « termine »")
    return v, L.erreurs


# ---------------------------------------------------------------------------
# Index en mémoire pour regrouper clients et sites
# ---------------------------------------------------------------------------
class Index:
    def __init__(self, conn):
        self.recharger(conn)

    def recharger(self, conn):
        self.par_telephone = {}
        self.par_nom = {}
        self.sites = {}
        for id_, prenom, nom, entreprise, tel, tel2 in conn.execute(
                "SELECT id, prenom, nom, entreprise, telephone, telephone_2 FROM clients"):
            for t in (tel, tel2):
                if t:
                    self.par_telephone.setdefault(t, id_)
            self.par_nom.setdefault((cle(prenom), cle(nom), cle(entreprise)), id_)
        for id_, client_id, adresse, ville in conn.execute("SELECT id, client_id, adresse, ville FROM sites"):
            self.sites[(client_id, cle(adresse), cle(ville))] = id_

    def client(self, v):
        for t in (v["client_telephone"], v["client_telephone_2"]):
            if t and t in self.par_telephone:
                return self.par_telephone[t], "telephone"
        k = (cle(v["client_prenom"]), cle(v["client_nom"]), cle(v["client_entreprise"]))
        if k in self.par_nom:
            return self.par_nom[k], "nom"
        return None, None

    def ajouter_client(self, id_, v):
        for t in (v["client_telephone"], v["client_telephone_2"]):
            if t:
                self.par_telephone.setdefault(t, id_)
        self.par_nom.setdefault((cle(v["client_prenom"]), cle(v["client_nom"]), cle(v["client_entreprise"])), id_)


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------
@dataclass
class Resultat:
    chantiers: int = 0
    clients_crees: int = 0
    clients_reutilises: int = 0
    sites_crees: int = 0
    paiements: int = 0
    doublons: int = 0
    erreurs: list = field(default_factory=list)        # [(no_ligne, [messages])]
    avertissements: list = field(default_factory=list)  # [texte]
    sauvegarde: object = None


def _num(d):
    return None if d is None else float(d)


def _enrichir(conn, table, id_, nouvelles, texte_libre, avertir):
    """Complète les champs vides d'une fiche existante ; signale les contradictions."""
    cols = [c for c, val in nouvelles.items() if val is not None]
    if not cols:
        return
    actuel = dict(zip(cols, conn.execute(
        f"SELECT {', '.join(cols)} FROM {table} WHERE id = ?", (id_,)).fetchone()))
    maj = {}
    for c in cols:
        ancien, nouveau = actuel[c], nouvelles[c]
        if ancien is None:
            maj[c] = nouveau
        elif cle(ancien) == cle(nouveau):
            continue
        elif c in texte_libre:
            maj[c] = f"{ancien}\n{nouveau}"
        else:
            avertir(f"{table} #{id_} : {c} déjà « {ancien} », « {nouveau} » ignoré")
    if maj:
        conn.execute(
            f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in maj)} WHERE id = ?",
            (*maj.values(), id_))


def _champs_differents(conn, chantier_id, v):
    """Champs de la ligne qui contredisent un chantier déjà présent (pour avertir, jamais pour écrire)."""
    colonnes = ["statut", "heure_prevue", "duree_estimee_h", "duree_reelle_h", "tps", "tvq", "numero_facture",
                "date_facture", "dossier_photos", "fichier_papier", "ref_papier", "notes"]
    actuel = dict(zip(colonnes, conn.execute(
        f"SELECT {', '.join(colonnes)} FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()))
    nouveau = {c: (_num(v[c]) if isinstance(v[c], Decimal) else v[c]) for c in colonnes}
    nouveau["tps"] = nouveau["tps"] or 0.0
    nouveau["tvq"] = nouveau["tvq"] or 0.0
    diffs = [c for c in colonnes if nouveau[c] != actuel[c] and not (nouveau[c] is None and c not in ("statut",))]
    if v["paiement_montant"] is not None and not conn.execute(
            "SELECT 1 FROM paiements WHERE chantier_id = ? AND date_paiement = ? AND montant = ? AND mode = ?",
            (chantier_id, v["paiement_date"], float(v["paiement_montant"]), v["paiement_mode"])).fetchone():
        diffs.append("paiement")
    return diffs


def _ecrire_ligne(conn, idx, v, res, avertir):
    # --- client
    client_id, via = idx.client(v)
    if client_id is None:
        cur = conn.execute(
            "INSERT INTO clients (prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, notes)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (v["client_prenom"], v["client_nom"], v["client_entreprise"], v["client_telephone"],
             v["client_telephone_2"], v["client_courriel"],
             1 if v["client_sms_ok"] is None else v["client_sms_ok"], v["client_notes"]))
        client_id = cur.lastrowid
        idx.ajouter_client(client_id, v)
        res.clients_crees += 1
    else:
        res.clients_reutilises += 1
        if via == "telephone":
            nom_actuel = conn.execute("SELECT prenom, nom, entreprise FROM clients WHERE id = ?", (client_id,)).fetchone()
            if (cle(nom_actuel[0]), cle(nom_actuel[1]), cle(nom_actuel[2])) != (
                    cle(v["client_prenom"]), cle(v["client_nom"]), cle(v["client_entreprise"])):
                avertir(f"même téléphone que le client #{client_id} "
                        f"({' '.join(x for x in nom_actuel if x)}) : traité comme le même client")
        _enrichir(conn, "clients", client_id, {
            "prenom": v["client_prenom"], "nom": v["client_nom"], "entreprise": v["client_entreprise"],
            "telephone": v["client_telephone"], "telephone_2": v["client_telephone_2"],
            "courriel": v["client_courriel"], "notes": v["client_notes"],
        }, {"notes"}, avertir)
        if v["client_sms_ok"] == 0:  # un refus de textos l'emporte toujours
            conn.execute("UPDATE clients SET sms_ok = 0 WHERE id = ?", (client_id,))
        idx.ajouter_client(client_id, v)

    # --- site
    site_cle = (client_id, cle(v["adresse"]), cle(v["ville"]))
    site_id = idx.sites.get(site_cle)
    a_coords = v["latitude"] is not None
    if site_id is None:
        cur = conn.execute(
            "INSERT INTO sites (client_id, adresse, ville, province, code_postal, latitude, longitude,"
            " geocode_statut, notes_acces) VALUES (?,?,?,?,?,?,?,?,?)",
            (client_id, v["adresse"], v["ville"], v["province"], v["code_postal"], v["latitude"],
             v["longitude"], "manuel" if a_coords else "a_faire", v["notes_acces"]))
        site_id = cur.lastrowid
        idx.sites[site_cle] = site_id
        res.sites_crees += 1
    else:
        _enrichir(conn, "sites", site_id, {"code_postal": v["code_postal"], "notes_acces": v["notes_acces"]},
                  {"notes_acces"}, avertir)
        if a_coords:
            lat, lon = conn.execute("SELECT latitude, longitude FROM sites WHERE id = ?", (site_id,)).fetchone()
            if lat is None:
                conn.execute("UPDATE sites SET latitude = ?, longitude = ?, geocode_statut = 'manuel' WHERE id = ?",
                             (v["latitude"], v["longitude"], site_id))
            elif (lat, lon) != (v["latitude"], v["longitude"]):
                avertir(f"sites #{site_id} : coordonnées déjà ({lat}, {lon}), ({v['latitude']}, {v['longitude']}) ignorées")

    # --- chantier (ignoré s'il existe déjà : permet de relancer le même fichier)
    prix = _num(v["prix_ht"])
    existant = conn.execute(
        "SELECT id FROM chantiers WHERE site_id = ? AND type_travaux = ? AND description IS ?"
        " AND date_soumission IS ? AND date_prevue IS ? AND date_realisee IS ? AND prix_ht IS ?",
        (site_id, v["type_travaux"], v["description"], v["date_soumission"], v["date_prevue"],
         v["date_realisee"], prix)).fetchone()
    if existant:
        res.doublons += 1
        differences = _champs_differents(conn, existant[0], v)
        if differences:
            avertir(f"chantier #{existant[0]} déjà présent : {', '.join(differences)} diffère(nt) "
                    "dans la ligne, qui est ignorée (corriger dans la base, pas par réimportation)")
        return
    cur = conn.execute(
        "INSERT INTO chantiers (site_id, type_travaux, description, notes, statut, date_soumission,"
        " date_prevue, heure_prevue, date_realisee, duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq,"
        " numero_facture, date_facture, dossier_photos, fichier_papier, ref_papier)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (site_id, v["type_travaux"], v["description"], v["notes"], v["statut"], v["date_soumission"],
         v["date_prevue"], v["heure_prevue"], v["date_realisee"], _num(v["duree_estimee_h"]),
         _num(v["duree_reelle_h"]), prix, _num(v["tps"]) or 0, _num(v["tvq"]) or 0,
         v["numero_facture"], v["date_facture"], v["dossier_photos"], v["fichier_papier"], v["ref_papier"]))
    res.chantiers += 1
    if v["paiement_montant"] is not None:
        conn.execute(
            "INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?,?,?,?)",
            (cur.lastrowid, v["paiement_date"], float(v["paiement_montant"]), v["paiement_mode"]))
        res.paiements += 1


# ---------------------------------------------------------------------------
# Fichier CSV
# ---------------------------------------------------------------------------
def _lire_csv(chemin):
    """Retourne (lignes, remarques). Gère UTF-8 (avec/sans BOM), Windows-1252, « , » ou « ; »."""
    octets = Path(chemin).read_bytes()
    remarques = []
    try:
        texte = octets.decode("utf-8-sig")
    except UnicodeDecodeError:
        texte = octets.decode("cp1252")
        remarques.append("fichier lu en Windows-1252 (export « CSV » d'Excel) ; l'UTF-8 est préférable")
    premiere = texte.split("\n", 1)[0]
    delim = max((",", ";", "\t"), key=premiere.count)
    lignes = list(csv.reader(io.StringIO(texte, newline=""), delimiter=delim))
    if not lignes:
        raise SystemExit("Fichier vide.")
    entete = [h.strip().lower() for h in lignes[0]]
    inconnues = [h for h in entete if h and h not in COLONNES]
    if inconnues:
        raise SystemExit(
            "Colonne(s) inconnue(s) dans l'en-tête : " + ", ".join(inconnues)
            + "\nColonnes permises : " + ", ".join(COLONNES))
    manquantes = [c for c in COLONNES_REQUISES if c not in entete]
    if not {"client_nom", "client_entreprise"} & set(entete):
        manquantes.append("client_nom")
    if manquantes:
        raise SystemExit("Colonne(s) obligatoire(s) absente(s) de l'en-tête : " + ", ".join(manquantes))
    return entete, lignes[1:], remarques


def _sauvegarder(db):
    dossier = db.parent / "sauvegardes"
    dossier.mkdir(exist_ok=True)
    base = f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_avant_import"
    cible = dossier / f"{base}.db"
    n = 1
    while cible.exists():  # jamais écraser une sauvegarde existante
        n += 1
        cible = dossier / f"{base}_{n}.db"
    src = sqlite3.connect(db)
    dst = sqlite3.connect(cible)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return cible


def importer(csv_path, db_path=DB_DEFAUT, simulation=False, taxes_auto=False):
    db_path = Path(db_path)
    res = Resultat()
    entete, lignes, remarques = _lire_csv(csv_path)
    res.avertissements.extend(remarques)

    existait = db_path.exists() and db_path.stat().st_size > 0
    if existait or not simulation:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, isolation_level=None)
    else:
        conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    if not existait:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("PRAGMA foreign_keys = ON")
    elif conn.execute("PRAGMA user_version").fetchone()[0] != 1:
        raise SystemExit("Version de schéma inattendue (attendu : 1).")

    alias_types = {}
    for code, libelle in conn.execute("SELECT code, libelle FROM types_travaux"):
        alias_types[cle(code)] = code
        alias_types[cle(libelle)] = code

    if not simulation and existait:
        res.sauvegarde = _sauvegarder(db_path)

    idx = Index(conn)
    changements_avant = conn.total_changes
    conn.execute("BEGIN")
    for no, cellules in enumerate(lignes, start=2):
        if not any(c.strip() for c in cellules):
            continue
        if len(cellules) > len(entete):
            res.erreurs.append((no, ["plus de cellules que de colonnes (une virgule dans un texte non entouré de guillemets ?)"]))
            continue
        brut = dict(zip(entete, cellules))
        v, erreurs = lire_ligne(brut, alias_types, taxes_auto)
        if erreurs:
            res.erreurs.append((no, erreurs))
            continue
        conn.execute("SAVEPOINT ligne")
        try:
            _ecrire_ligne(conn, idx, v, res, lambda msg, no=no: res.avertissements.append(f"ligne {no} : {msg}"))
            conn.execute("RELEASE ligne")
        except sqlite3.IntegrityError as e:
            conn.execute("ROLLBACK TO ligne")
            conn.execute("RELEASE ligne")
            idx.recharger(conn)
            res.erreurs.append((no, [f"refusé par la base : {e}"]))

    if res.erreurs or simulation:
        conn.execute("ROLLBACK")
        if res.sauvegarde:
            res.sauvegarde.unlink()
            res.sauvegarde = None
    else:
        conn.execute("COMMIT")
        if res.sauvegarde and conn.total_changes == changements_avant:  # rien d'écrit : sauvegarde inutile
            res.sauvegarde.unlink()
            res.sauvegarde = None
    conn.close()
    return res


def afficher(res, simulation, sortie=print):
    for msg in res.avertissements:
        sortie(f"  avertissement : {msg}")
    if res.erreurs:
        sortie(f"\n{len(res.erreurs)} ligne(s) en erreur — RIEN n'a été importé :")
        for no, messages in res.erreurs:
            sortie(f"  ligne {no} :")
            for m in messages:
                sortie(f"    - {m}")
        return
    verbe = "seraient importés (simulation, rien n'est écrit)" if simulation else "importés"
    sortie(f"\n{res.chantiers} chantier(s) {verbe} : "
           f"{res.clients_crees} client(s) créé(s), {res.clients_reutilises} client(s) réutilisé(s), "
           f"{res.sites_crees} adresse(s) créée(s), {res.paiements} paiement(s).")
    if res.doublons:
        sortie(f"{res.doublons} ligne(s) déjà présente(s) dans la base : ignorée(s).")
    if res.sauvegarde:
        sortie(f"Sauvegarde avant import : {res.sauvegarde}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Importe une feuille de saisie CSV dans la base SQLite.")
    p.add_argument("csv", help="fichier CSV à importer")
    p.add_argument("--db", default=str(DB_DEFAUT), help=f"fichier de base (défaut : {DB_DEFAUT})")
    p.add_argument("--simulation", action="store_true", help="valide et résume sans rien écrire")
    p.add_argument("--taxes-auto", action="store_true",
                   help="calcule TPS (5 %%) et TVQ (9,975 %%) quand tps et tvq sont vides")
    a = p.parse_args(argv)
    res = importer(a.csv, a.db, simulation=a.simulation, taxes_auto=a.taxes_auto)
    afficher(res, a.simulation)
    return 1 if res.erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
