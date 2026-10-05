"""Noyau partagé : validation d'une fiche et écriture dans la base SQLite.

Utilisé par l'import CSV (importer_saisie.py) et par l'interface de saisie
(interface.py), pour que les deux appliquent exactement les mêmes règles.
Bibliothèque standard seulement (Python 3.8+).
"""
import datetime
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCHEMA = RACINE / "schema" / "schema.sql"
DB_DEFAUT = RACINE / "data" / "sylvainculteur.db"
SERVICES_NUAGE = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "box sync")


def service_nuage(chemin):
    """Nom du service de synchronisation (OneDrive, Dropbox...) si le chemin est dans un dossier synchronisé."""
    partie = str(Path(chemin).resolve()).lower()
    return next((n for n in SERVICES_NUAGE if n in partie), None)

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
    "date_soumission", "date_prevue", "heure_prevue",
    "duree_estimee_h", "duree_reelle_h",
    "prix_ht", "tps", "tvq", "numero_facture", "date_facture",
    "paiement_date", "paiement_montant", "paiement_mode",
    "notes_acces", "ref_papier", "fichier_papier", "dossier_photos",
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

    def travaux(self, col, alias):
        """Liste [(code, précision ou None)].

        Reçoit soit une liste déjà prête (interface), soit un texte (CSV) du genre
        « taille_haie: cèdres côté rue + elagage: érable » : types séparés par « + »,
        précision facultative après « : ».
        """
        brut = self.brut.get(col)
        if isinstance(brut, (list, tuple)):
            morceaux = list(brut)
        else:
            texte = self._cellule(col)
            morceaux = [tuple(part.partition(":")[::2]) for part in re.split(r"\s*\+\s*", texte) if part.strip()] if texte else []
        resultat, vus = [], set()
        for code_brut, precision in morceaux:
            code = alias.get(cle(code_brut))
            if code is None:
                self.erreurs.append(f"{col} « {code_brut.strip()} » inconnu (valeurs permises : {', '.join(sorted(set(alias.values())))})")
            elif code in vus:
                self.erreurs.append(f"{col} « {code} » est indiqué deux fois")
            else:
                vus.add(code)
                resultat.append((code, re.sub(r"\s+", " ", (precision or "").strip()) or None))
        if not morceaux:
            self.erreurs.append(f"{col} est obligatoire (au moins un type de travaux)")
        return resultat

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

    v["travaux"] = L.travaux("type_travaux", alias_types)
    v["statut"] = L.choix("statut", STATUTS, obligatoire=True)
    v["description"] = L.texte("description", multiligne=True)
    v["date_soumission"] = L.jour("date_soumission")
    v["date_prevue"] = L.jour("date_prevue")
    v["heure_prevue"] = L.heure("heure_prevue")
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

    # Cohérence statut / date (la même règle existe dans la base).
    for statut_exige in ("planifie", "termine"):
        if v["statut"] == statut_exige and not v["date_prevue"] and not any("date_prevue" in e for e in L.erreurs):
            L.erreurs.append(f"statut « {statut_exige} » : date_prevue est obligatoire")
    return v, L.erreurs



# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------
def ouvrir_base(db_path, en_memoire_si_absente=False):
    """Ouvre (et crée au besoin) la base. Retourne (connexion, existait).

    Connexion en autocommit : les transactions se font explicitement (BEGIN / COMMIT).
    """
    db_path = Path(db_path)
    existait = db_path.exists() and db_path.stat().st_size > 0
    if existait or not en_memoire_si_absente:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, isolation_level=None)
    else:
        conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    if not existait:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        conn.execute("PRAGMA foreign_keys = ON")
    else:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            raise SystemExit(f"La base {db_path} utilise l'ancien format (v1).\n"
                             f"Convertis-la d'abord (une sauvegarde est faite) :  python outils/migrer.py \"{db_path}\"")
        if version != 2:
            raise SystemExit(f"Version de schéma inattendue ({version}, attendu : 2).")
    return conn, existait


def alias_types_travaux(conn):
    """{forme comparable du code ou du libellé: code}"""
    alias = {}
    for code, libelle in conn.execute("SELECT code, libelle FROM types_travaux"):
        alias[cle(code)] = code
        alias[cle(libelle)] = code
    return alias


def sauvegarder(db, etiquette="avant_import"):
    """Copie cohérente de la base dans data/sauvegardes/. Ne remplace jamais une sauvegarde existante."""
    db = Path(db)
    dossier = db.parent / "sauvegardes"
    dossier.mkdir(exist_ok=True)
    base = f"{datetime.datetime.now():%Y-%m-%d_%H%M%S}_{etiquette}"
    cible = dossier / f"{base}.db"
    n = 1
    while cible.exists():
        n += 1
        cible = dossier / f"{base}_{n}.db"
    src = sqlite3.connect(db)
    dst = sqlite3.connect(cible)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return cible


# ---------------------------------------------------------------------------
# Regroupement des clients : même adresse + même nom ou même téléphone
# ---------------------------------------------------------------------------
class Index:
    def __init__(self, conn):
        self.recharger(conn)

    def recharger(self, conn):
        self.infos = {}          # id -> (téléphones, clé du nom)
        self.par_adresse = {}    # (adresse, ville) comparables -> [id]
        self.par_telephone = {}  # téléphone -> id
        for ligne in conn.execute(
                "SELECT id, prenom, nom, entreprise, telephone, telephone_2, adresse, ville FROM clients"):
            self.ajouter(*ligne)

    def ajouter(self, id_, prenom, nom, entreprise, tel, tel2, adresse, ville):
        tels = {t for t in (tel, tel2) if t}
        self.infos[id_] = (tels, (cle(prenom), cle(nom), cle(entreprise)))
        liste = self.par_adresse.setdefault((cle(adresse), cle(ville)), [])
        if id_ not in liste:
            liste.append(id_)
        for t in tels:
            self.par_telephone.setdefault(t, id_)

    def trouver(self, v):
        """(id, "nom"|"telephone") d'un client déjà présent à cette adresse, sinon (None, None)."""
        tels = {t for t in (v["client_telephone"], v["client_telephone_2"]) if t}
        nom = (cle(v["client_prenom"]), cle(v["client_nom"]), cle(v["client_entreprise"]))
        for id_ in self.par_adresse.get((cle(v["adresse"]), cle(v["ville"])), []):
            tels_existants, nom_existant = self.infos[id_]
            if nom == nom_existant:
                return id_, "nom"
            if tels & tels_existants:
                return id_, "telephone"
        return None, None

    def ailleurs(self, v):
        """Id d'un client de même téléphone mais à une autre adresse (2e propriété ?), sinon None."""
        for t in (v["client_telephone"], v["client_telephone_2"]):
            if t and t in self.par_telephone:
                return self.par_telephone[t]
        return None


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------
@dataclass
class Resultat:
    chantiers: int = 0
    clients_crees: int = 0
    clients_reutilises: int = 0
    paiements: int = 0
    doublons: int = 0
    erreurs: list = field(default_factory=list)        # [(no_ligne, [messages])]
    avertissements: list = field(default_factory=list)  # [texte]
    sauvegarde: object = None


def _num(d):
    return None if d is None else float(d)


def _enrichir(conn, id_, nouvelles, texte_libre, avertir):
    """Complète les champs vides d'un client existant ; signale les contradictions."""
    cols = [c for c, val in nouvelles.items() if val is not None]
    if not cols:
        return
    actuel = dict(zip(cols, conn.execute(
        f"SELECT {', '.join(cols)} FROM clients WHERE id = ?", (id_,)).fetchone()))
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
            avertir(f"client #{id_} : {c} déjà « {ancien} », « {nouveau} » ignoré")
    if maj:
        conn.execute(
            f"UPDATE clients SET {', '.join(f'{c} = ?' for c in maj)} WHERE id = ?",
            (*maj.values(), id_))


def trouver_ou_creer_client(conn, idx, v, res, avertir):
    """Retourne l'id du client de la fiche v : le client existant (complété) ou un nouveau."""
    client_id, via = idx.trouver(v)
    a_coords = v["latitude"] is not None
    if client_id is None:
        autre = idx.ailleurs(v)
        if autre is not None:
            avertir(f"même téléphone que le client #{autre} mais à une autre adresse : "
                    "nouvelle fiche client (2e propriété ?)")
        cur = conn.execute(
            "INSERT INTO clients (prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok,"
            " adresse, ville, province, code_postal, latitude, longitude, geocode_statut, notes_acces, notes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (v["client_prenom"], v["client_nom"], v["client_entreprise"], v["client_telephone"],
             v["client_telephone_2"], v["client_courriel"],
             1 if v["client_sms_ok"] is None else v["client_sms_ok"],
             v["adresse"], v["ville"], v["province"], v["code_postal"], v["latitude"], v["longitude"],
             "manuel" if a_coords else "a_faire", v["notes_acces"], v["client_notes"]))
        client_id = cur.lastrowid
        res.clients_crees += 1
    else:
        res.clients_reutilises += 1
        if via == "telephone":
            nom_actuel = conn.execute(
                "SELECT prenom, nom, entreprise FROM clients WHERE id = ?", (client_id,)).fetchone()
            avertir(f"même adresse et même téléphone que le client #{client_id} "
                    f"({' '.join(x for x in nom_actuel if x)}) : traité comme le même client")
        _enrichir(conn, client_id, {
            "prenom": v["client_prenom"], "nom": v["client_nom"], "entreprise": v["client_entreprise"],
            "telephone": v["client_telephone"], "telephone_2": v["client_telephone_2"],
            "courriel": v["client_courriel"], "code_postal": v["code_postal"],
            "notes": v["client_notes"], "notes_acces": v["notes_acces"],
        }, {"notes", "notes_acces"}, avertir)
        if v["client_sms_ok"] == 0:  # un refus de textos l'emporte toujours
            conn.execute("UPDATE clients SET sms_ok = 0 WHERE id = ?", (client_id,))
        if a_coords:
            lat, lon = conn.execute("SELECT latitude, longitude FROM clients WHERE id = ?", (client_id,)).fetchone()
            if lat is None:
                conn.execute("UPDATE clients SET latitude = ?, longitude = ?, geocode_statut = 'manuel' WHERE id = ?",
                             (v["latitude"], v["longitude"], client_id))
            elif (lat, lon) != (v["latitude"], v["longitude"]):
                avertir(f"client #{client_id} : coordonnées déjà ({lat}, {lon}), "
                        f"({v['latitude']}, {v['longitude']}) ignorées")
    ligne = conn.execute(
        "SELECT id, prenom, nom, entreprise, telephone, telephone_2, adresse, ville FROM clients WHERE id = ?",
        (client_id,)).fetchone()
    idx.ajouter(*ligne)
    return client_id


def _champs_differents(conn, chantier_id, v):
    """Champs de la ligne qui contredisent un chantier déjà présent (pour avertir, jamais pour écrire)."""
    colonnes = ["statut", "heure_prevue", "duree_estimee_h", "duree_reelle_h", "tps", "tvq", "numero_facture",
                "date_facture", "dossier_photos", "fichier_papier", "ref_papier"]
    actuel = dict(zip(colonnes, conn.execute(
        f"SELECT {', '.join(colonnes)} FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()))
    nouveau = {c: (_num(v[c]) if isinstance(v[c], Decimal) else v[c]) for c in colonnes}
    nouveau["tps"] = nouveau["tps"] or 0.0
    nouveau["tvq"] = nouveau["tvq"] or 0.0
    diffs = [c for c in colonnes if nouveau[c] != actuel[c] and not (nouveau[c] is None and c != "statut")]
    precisions = {code: (precision or None) for code, precision in conn.execute(
        "SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = ?", (chantier_id,))}
    if precisions != {code: precision for code, precision in v["travaux"]}:
        diffs.append("précisions des travaux")
    if v["paiement_montant"] is not None and not conn.execute(
            "SELECT 1 FROM paiements WHERE chantier_id = ? AND date_paiement = ? AND montant = ? AND mode = ?",
            (chantier_id, v["paiement_date"], float(v["paiement_montant"]), v["paiement_mode"])).fetchone():
        diffs.append("paiement")
    return diffs


def _valeurs_chantier(v):
    return (v["description"], v["statut"], v["date_soumission"], v["date_prevue"], v["heure_prevue"],
            _num(v["duree_estimee_h"]), _num(v["duree_reelle_h"]), _num(v["prix_ht"]), _num(v["tps"]) or 0,
            _num(v["tvq"]) or 0, v["numero_facture"], v["date_facture"], v["dossier_photos"],
            v["fichier_papier"], v["ref_papier"])


COLONNES_CHANTIER = ["description", "statut", "date_soumission", "date_prevue", "heure_prevue",
                     "duree_estimee_h", "duree_reelle_h", "prix_ht", "tps", "tvq", "numero_facture",
                     "date_facture", "dossier_photos", "fichier_papier", "ref_papier"]


def _ecrire_travaux(conn, chantier_id, travaux):
    conn.execute("DELETE FROM chantier_travaux WHERE chantier_id = ?", (chantier_id,))
    conn.executemany("INSERT INTO chantier_travaux (chantier_id, type_travaux, precision) VALUES (?,?,?)",
                     [(chantier_id, code, precision) for code, precision in travaux])


def creer_chantier(conn, client_id, v, res, avertir, verifier_doublon=True):
    """Crée le chantier (et son paiement éventuel). Retourne son id, ou None si déjà présent."""
    if verifier_doublon:
        codes = {code for code, _ in v["travaux"]}
        candidats = conn.execute(
            "SELECT id FROM chantiers WHERE client_id = ? AND description IS ? AND date_soumission IS ?"
            " AND date_prevue IS ? AND prix_ht IS ?",
            (client_id, v["description"], v["date_soumission"], v["date_prevue"], _num(v["prix_ht"]))).fetchall()
        for (existant,) in candidats:
            actuels = {r[0] for r in conn.execute("SELECT type_travaux FROM chantier_travaux WHERE chantier_id = ?", (existant,))}
            if actuels != codes:
                continue
            res.doublons += 1
            differences = _champs_differents(conn, existant, v)
            if differences:
                avertir(f"chantier #{existant} déjà présent : {', '.join(differences)} diffère(nt) "
                        "dans la ligne, qui est ignorée (corriger dans la base, pas par réimportation)")
            return None
    cur = conn.execute(
        f"INSERT INTO chantiers (client_id, {', '.join(COLONNES_CHANTIER)}) VALUES (?{',?' * len(COLONNES_CHANTIER)})",
        (client_id, *_valeurs_chantier(v)))
    _ecrire_travaux(conn, cur.lastrowid, v["travaux"])
    res.chantiers += 1
    if v["paiement_montant"] is not None:
        conn.execute(
            "INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?,?,?,?)",
            (cur.lastrowid, v["paiement_date"], float(v["paiement_montant"]), v["paiement_mode"]))
        res.paiements += 1
    return cur.lastrowid


def mettre_a_jour_fiche(conn, chantier_id, v):
    """Corrige un chantier ET la fiche de son client avec les valeurs de v (les champs vides effacent)."""
    client_id, = conn.execute("SELECT client_id FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    mettre_a_jour_client(conn, client_id, v)
    conn.execute(f"UPDATE chantiers SET {', '.join(c + ' = ?' for c in COLONNES_CHANTIER)} WHERE id = ?",
                 (*_valeurs_chantier(v), chantier_id))
    _ecrire_travaux(conn, chantier_id, v["travaux"])


def mettre_a_jour_client(conn, client_id, v):
    """Remplace les informations du client. Les coordonnées périmées (adresse changée) sont effacées."""
    adresse, ville, lat, lon = conn.execute(
        "SELECT adresse, ville, latitude, longitude FROM clients WHERE id = ?", (client_id,)).fetchone()
    adresse_changee = (cle(adresse), cle(ville)) != (cle(v["adresse"]), cle(v["ville"]))
    coords = {}
    if (v["latitude"], v["longitude"]) == (lat, lon):
        if adresse_changee and lat is not None:
            coords = {"latitude": None, "longitude": None, "geocode_statut": "a_faire"}
    elif v["latitude"] is None:
        coords = {"latitude": None, "longitude": None, "geocode_statut": "a_faire"}
    else:
        coords = {"latitude": v["latitude"], "longitude": v["longitude"], "geocode_statut": "manuel"}
    if adresse_changee and not coords and lat is None:
        coords = {"geocode_statut": "a_faire"}  # un ancien « echec » ne vaut plus pour la nouvelle adresse
    champs = {
        "prenom": v["client_prenom"], "nom": v["client_nom"], "entreprise": v["client_entreprise"],
        "telephone": v["client_telephone"], "telephone_2": v["client_telephone_2"],
        "courriel": v["client_courriel"], "sms_ok": 1 if v["client_sms_ok"] is None else v["client_sms_ok"],
        "adresse": v["adresse"], "ville": v["ville"], "province": v["province"],
        "code_postal": v["code_postal"], "notes_acces": v["notes_acces"], "notes": v["client_notes"],
        **coords,
    }
    conn.execute(f"UPDATE clients SET {', '.join(f'{c} = ?' for c in champs)} WHERE id = ?",
                 (*champs.values(), client_id))
