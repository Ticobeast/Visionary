"""Noyau partagé : validation d'une fiche et écriture dans la base SQLite.

Utilisé par l'import CSV (importer_saisie.py) et par l'interface de saisie
(interface.py), pour que les deux appliquent exactement les mêmes règles.
Bibliothèque standard seulement (Python 3.8+).
"""
import datetime
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCHEMA = RACINE / "schema" / "schema.sql"
DB_DEFAUT = RACINE / "data" / "sylvainculteur.db"
VERSION_SCHEMA = 5
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
    "date_soumission", "date_prevue",
    "duree_estimee_h", "duree_reelle_h",
    "prix_ht", "tps", "tvq", "modalite_paiement", "numero_facture", "date_facture",
    "paiement_date", "paiement_montant", "paiement_mode",
    "notes_acces", "ref_papier", "fichier_papier", "dossier_photos",
    "client_telephone_2", "client_courriel", "client_sms_ok", "client_notes",
    "province", "latitude", "longitude",
]
COLONNES_REQUISES = ("adresse", "ville", "type_travaux", "statut")

# Statuts officiels, dans l'ordre du parcours d'un chantier.
STATUTS = ("soumission", "en_attente", "a_planifier", "planifie", "termine", "annule")
LIBELLES_STATUT = {"soumission": "Soumission", "en_attente": "En attente", "a_planifier": "À planifier",
                   "planifie": "Planifié", "termine": "Terminé", "annule": "Annulé"}
# Statuts sans date : le chantier n'est pas (encore) placé dans une journée.
STATUTS_SANS_DATE = ("soumission", "en_attente", "a_planifier")
# Anciens noms toujours compris (vieilles feuilles CSV) : Accepté -> À planifier, Refusé -> Annulé.
ALIAS_ANCIENS_STATUTS = {"accepte": "a_planifier", "refuse": "annule"}
MODES = ("comptant", "cheque", "interac", "carte", "autre")
LIBELLES_MODE = {"comptant": "Comptant", "cheque": "Chèque", "interac": "Interac", "carte": "Carte", "autre": "Autre"}

RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_CODE_POSTAL = re.compile(r"^[A-Z]\d[A-Z]\d[A-Z]\d$")



def taxes_pour(prix_ht):
    """(TPS, TVQ) d'un prix avant taxes, arrondies au cent."""
    cent = Decimal("0.01")
    return ((prix_ht * TAUX_TPS).quantize(cent, ROUND_HALF_UP), (prix_ht * TAUX_TVQ).quantize(cent, ROUND_HALF_UP))


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


def _lire_client(L, v):
    """Champs du client et de son adresse (communs à la fiche chantier et à la fiche client)."""
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


def lire_client(brut):
    """Valide la fiche d'un client seule. Retourne (valeurs, erreurs)."""
    L = Ligne(brut)
    v = {}
    _lire_client(L, v)
    return v, L.erreurs


def lire_ligne(brut, alias_types, taxes_auto):
    """Retourne (valeurs, erreurs) pour une ligne brute (CSV ou formulaire) : client + chantier."""
    L = Ligne(brut)
    v = {}
    _lire_client(L, v)

    v["travaux"] = L.travaux("type_travaux", alias_types)
    alias_statuts = {**{cle(c): c for c in STATUTS}, **{cle(l): c for c, l in LIBELLES_STATUT.items()}, **ALIAS_ANCIENS_STATUTS}
    v["statut"] = L.choix("statut", STATUTS, alias_statuts, obligatoire=True)
    v["description"] = L.texte("description", multiligne=True)
    v["date_soumission"] = L.jour("date_soumission")
    v["date_prevue"] = L.jour("date_prevue")
    v["duree_estimee_h"] = L.duree("duree_estimee_h")
    if v["duree_estimee_h"] is None and not any("duree_estimee_h" in e for e in L.erreurs):
        L.erreurs.append("duree_estimee_h est obligatoire (durée estimée en heures, ex. 2,5 pour 2 h 30)")
    v["duree_reelle_h"] = L.duree("duree_reelle_h")
    if v["statut"] == "termine" and v["duree_reelle_h"] is None:   # à la clôture, la durée réelle reprend l'estimée
        v["duree_reelle_h"] = v["duree_estimee_h"]

    v["prix_ht"] = L.montant("prix_ht")
    v["tps"] = L.montant("tps")
    v["tvq"] = L.montant("tvq")
    if taxes_auto and v["prix_ht"] is not None and v["tps"] is None and v["tvq"] is None:
        v["tps"], v["tvq"] = taxes_pour(v["prix_ht"])
    v["modalite_paiement"] = L.choix("modalite_paiement", MODES, {**{cle(c): c for c in MODES}, **{cle(l): c for c, l in LIBELLES_MODE.items()}})
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
        if version in (1, 2, 3, 4):
            raise SystemExit(f"La base {db_path} utilise un ancien format (v{version}).\n"
                             f"Convertis-la d'abord (une sauvegarde est faite) :  python outils/migrer.py \"{db_path}\"")
        if version != VERSION_SCHEMA:
            raise SystemExit(f"Version de schéma inattendue ({version}, attendu : {VERSION_SCHEMA}).")
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


def trouver_ou_creer_client(conn, idx, v, res, avertir, enrichir=True):
    """Retourne l'id du client de la fiche v : le client existant ou un nouveau.

    enrichir=True (import CSV) : les champs vides du client existant sont complétés. enrichir=False (formulaires) :
    la fiche d'un client existant n'est JAMAIS modifiée (seule la fiche client le permet).
    """
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
        if enrichir:
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
    colonnes = ["statut", "duree_estimee_h", "duree_reelle_h", "tps", "tvq", "modalite_paiement", "numero_facture",
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
    return (v["description"], v["statut"], v["date_soumission"], v["date_prevue"],
            _num(v["duree_estimee_h"]), _num(v["duree_reelle_h"]), _num(v["prix_ht"]), _num(v["tps"]) or 0,
            _num(v["tvq"]) or 0, v["modalite_paiement"], v["numero_facture"], v["date_facture"], v["dossier_photos"],
            v["fichier_papier"], v["ref_papier"])


COLONNES_CHANTIER = ["description", "statut", "date_soumission", "date_prevue",
                     "duree_estimee_h", "duree_reelle_h", "prix_ht", "tps", "tvq", "modalite_paiement", "numero_facture",
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
    ajuster_ordre(conn, cur.lastrowid)
    res.chantiers += 1
    if v["paiement_montant"] is not None:
        conn.execute(
            "INSERT INTO paiements (chantier_id, date_paiement, montant, mode) VALUES (?,?,?,?)",
            (cur.lastrowid, v["paiement_date"], float(v["paiement_montant"]), v["paiement_mode"]))
        res.paiements += 1
    return cur.lastrowid


VERROU = "Chantier terminé : verrouillé en lecture seule"


def mettre_a_jour_fiche(conn, chantier_id, v):
    """Corrige un chantier (jamais la fiche de son client : seule la fiche client la modifie).

    Retourne la liste des erreurs ; un chantier « Terminé » est verrouillé et refuse toute modification.
    """
    r = conn.execute("SELECT date_prevue, statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"chantier #{chantier_id} introuvable"]
    ancienne_date, statut = r
    if statut == "termine":
        return [VERROU]
    _ecrire_travaux(conn, chantier_id, v["travaux"])      # avant l'UPDATE : une fois « Terminé », les travaux sont verrouillés
    conn.execute(f"UPDATE chantiers SET {', '.join(c + ' = ?' for c in COLONNES_CHANTIER)} WHERE id = ?",
                 (*_valeurs_chantier(v), chantier_id))
    ajuster_ordre(conn, chantier_id, ancienne_date)
    return []


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


# ---------------------------------------------------------------------------
# Transactions, valeurs de formulaire
# ---------------------------------------------------------------------------
@contextmanager
def transaction(conn):
    """BEGIN ... COMMIT, ou ROLLBACK si une exception survient."""
    conn.execute("BEGIN")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _txt(x, fmt=None):
    return "" if x is None else (fmt(x) if fmt else str(x))


def valeurs_client(conn, client_id):
    """Fiche d'un client sous forme de textes (clés de la feuille de saisie), ou None."""
    r = conn.execute("SELECT prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, adresse, ville,"
                     " province, code_postal, latitude, longitude, notes_acces, notes FROM clients WHERE id = ?",
                     (client_id,)).fetchone()
    if r is None:
        return None
    cols = ["client_prenom", "client_nom", "client_entreprise", "client_telephone", "client_telephone_2",
            "client_courriel", "client_sms_ok", "adresse", "ville", "province", "code_postal", "latitude",
            "longitude", "notes_acces", "client_notes"]
    return {c: _txt(x, repr if c in ("latitude", "longitude") else None) for c, x in zip(cols, r)}


def travaux_depuis_formulaire(conn, form):
    """Types cochés + précisions d'un formulaire. Retourne (liste [(code, précision)], valeurs à réafficher).

    Une précision saisie sans case cochée coche le type d'office.
    """
    travaux, valeurs = [], {}
    for (code,) in conn.execute("SELECT code FROM types_travaux ORDER BY code"):
        precision = form.get(f"precision_{code}", "").strip()
        valeurs[f"precision_{code}"] = precision
        if form.get(f"type_{code}") or precision:
            valeurs[f"type_{code}"] = "1"
            travaux.append((code, precision))
    return travaux, valeurs


# ---------------------------------------------------------------------------
# Délai d'attente (tableau de bord) : < 7 jours normal, 7 à 30 jours à surveiller, > 30 jours urgent
# ---------------------------------------------------------------------------
SEUIL_SURVEILLER = 7
SEUIL_URGENT = 30


def jours_attente(attente_depuis, aujourdhui=None):
    """Nombre de jours écoulés depuis la date (AAAA-MM-JJ) à laquelle le client attend."""
    if not attente_depuis:
        return 0
    aujourdhui = aujourdhui or datetime.date.today()
    return max(0, (aujourdhui - datetime.date.fromisoformat(attente_depuis)).days)


def priorite(jours):
    if jours > SEUIL_URGENT:
        return "urgente"
    return "surveiller" if jours >= SEUIL_SURVEILLER else "normale"


# ---------------------------------------------------------------------------
# Actions rapides (tableau de bord, tournées). Chacune retourne la liste des erreurs
# (vide = fait). À appeler dans une transaction.
# ---------------------------------------------------------------------------
def changer_statut(conn, chantier_id, statut, date_prevue=None, duree=None, duree_reelle=None):
    """Change le statut d'un chantier.

    « soumission » / « en_attente » / « a_planifier » : pas encore placé dans une journée, la date est effacée.
    « planifie » / « termine » : une date ET une durée estimée sont obligatoires (celles déjà en base si rien n'est fourni).
    « termine » : la durée réelle se préremplit avec la durée estimée si elle n'est pas fournie ; le chantier est ensuite
    VERROUILLÉ (impossible à modifier ou à rouvrir).
    « annule » : la date n'est pas touchée.
    La durée fournie est la durée ESTIMÉE (heures).
    """
    L = Ligne({"date_prevue": date_prevue or "", "duree_estimee_h": duree or "", "duree_reelle_h": duree_reelle or ""})
    d, h, hr = L.jour("date_prevue"), L.duree("duree_estimee_h"), L.duree("duree_reelle_h")
    if statut not in STATUTS:
        L.erreurs.append(f"statut « {statut} » inconnu")
    actuel = conn.execute("SELECT date_prevue, statut, duree_estimee_h, duree_reelle_h FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if actuel is None:
        L.erreurs.append(f"chantier #{chantier_id} introuvable")
    if L.erreurs:
        return L.erreurs
    ancienne_date, ancien_statut, duree_actuelle, reelle_actuelle = actuel
    if ancien_statut == "termine":
        return [VERROU]
    duree_finale = float(h) if h is not None else duree_actuelle
    if statut in ("planifie", "termine"):
        d = d or ancienne_date
        if not d:
            return [f"la date des travaux est obligatoire pour le statut « {LIBELLES_STATUT[statut]} »"]
        if not duree_finale:
            return [f"la durée estimée est obligatoire pour le statut « {LIBELLES_STATUT[statut]} » (en heures, ex. 2,5)"]
    elif statut in STATUTS_SANS_DATE:
        d = None
    else:
        d = ancienne_date
    colonnes = {"statut": statut, "date_prevue": d}
    if h is not None:
        colonnes["duree_estimee_h"] = float(h)
    if statut == "termine":
        colonnes["duree_reelle_h"] = float(hr) if hr is not None else (reelle_actuelle if reelle_actuelle is not None else duree_finale)
    conn.execute(f"UPDATE chantiers SET {', '.join(c + ' = ?' for c in colonnes)} WHERE id = ?",
                 (*colonnes.values(), chantier_id))
    ajuster_ordre(conn, chantier_id, ancienne_date)
    return []


def facturer(conn, chantier_id, date_facture=None, numero_facture=None):
    """Marque un chantier terminé comme facturé (date de la facture = aujourd'hui par défaut)."""
    r = conn.execute("SELECT statut, prix_ht, date_facture FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"chantier #{chantier_id} introuvable"]
    statut, prix, deja = r
    if deja:
        return [f"déjà facturé le {deja}"]
    if statut != "termine":
        return ["seul un chantier terminé peut être facturé"]
    if prix is None:
        return ["le prix est manquant : complète la fiche du chantier avant de facturer"]
    L = Ligne({"date_facture": date_facture or ""})
    d = L.jour("date_facture")
    if L.erreurs:
        return L.erreurs
    conn.execute("UPDATE chantiers SET date_facture = ?, numero_facture = COALESCE(?, numero_facture) WHERE id = ?",
                 (d or datetime.date.today().isoformat(), (numero_facture or "").strip() or None, chantier_id))
    return []


def argent_texte(x):
    return f"{x:,.2f} $".replace(",", " ").replace(".", ",")


def encaisser(conn, chantier_id, montant, mode, date_paiement=None, reference=None):
    """Enregistre un paiement reçu (montant taxes incluses ; date = aujourd'hui par défaut).

    Règle : jamais de solde négatif. Le paiement est refusé s'il dépasse ce qu'il reste à payer.
    """
    L = Ligne({"paiement_montant": montant or "", "paiement_date": date_paiement or "", "paiement_mode": mode or ""})
    m, d, mo = L.montant("paiement_montant"), L.jour("paiement_date"), L.choix("paiement_mode", MODES)
    if m is None and not any("paiement_montant" in e for e in L.erreurs):
        L.erreurs.append("le montant est obligatoire")
    if m is not None and m == 0:
        L.erreurs.append("le montant doit être supérieur à 0")
    if mo is None and not any("paiement_mode" in e for e in L.erreurs):
        L.erreurs.append("le mode de paiement est obligatoire")
    r = conn.execute("SELECT prix_ht, tps, tvq FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        L.erreurs.append(f"chantier #{chantier_id} introuvable")
    elif r[0] is None:
        L.erreurs.append("le prix du chantier est manquant : saisis-le avant d'enregistrer un paiement")
    elif m is not None and m > 0:
        total = round(r[0] + r[1] + r[2], 2)
        deja = round(conn.execute("SELECT COALESCE(SUM(montant), 0) FROM paiements WHERE chantier_id = ?", (chantier_id,)).fetchone()[0], 2)
        solde = round(total - deja, 2)
        if solde <= 0:
            L.erreurs.append("ce chantier est déjà entièrement payé : un solde négatif est interdit")
        elif float(m) > solde + 0.001:
            L.erreurs.append(f"le montant ({argent_texte(float(m))}) dépasse le solde restant ({argent_texte(solde)}) : "
                             "un solde négatif est interdit")
    if L.erreurs:
        return L.erreurs
    conn.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode, reference) VALUES (?,?,?,?,?)",
                 (chantier_id, d or datetime.date.today().isoformat(), float(m), mo, (reference or "").strip() or None))
    return []


def planifier_lot(conn, ids, date_prevue, durees=None):
    """Planifie plusieurs chantiers le même jour. Tout ou rien : s'il y a une erreur, rien n'est modifié.

    durees : {id: texte} facultatif, durées estimées (heures) saisies pendant la planification.
    Retourne la liste des erreurs.
    """
    durees = durees or {}
    L = Ligne({"date_prevue": date_prevue or ""})
    d = L.jour("date_prevue")
    if d is None and not L.erreurs:
        L.erreurs.append("choisis la date de la journée")
    if not ids:
        L.erreurs.append("aucun chantier sélectionné")
    a_ecrire = []
    for i in ids:
        r = conn.execute("SELECT statut, duree_estimee_h FROM chantiers WHERE id = ?", (i,)).fetchone()
        if r is None or r[0] not in ("soumission", "en_attente", "a_planifier", "planifie"):
            L.erreurs.append(f"chantier #{i} : ne peut pas être planifié (statut {r[0] if r else 'introuvable'})")
            continue
        Lh = Ligne({"duree_estimee_h": durees.get(i, "")})
        h = Lh.duree("duree_estimee_h")
        L.erreurs.extend(f"chantier #{i} : {e}" for e in Lh.erreurs)
        if h is None and not r[1] and not Lh.erreurs:
            L.erreurs.append(f"chantier #{i} : la durée estimée est obligatoire (en heures, ex. 2,5)")
        a_ecrire.append((i, h))
    if L.erreurs:
        return L.erreurs
    for i, h in a_ecrire:      # dans l'ordre reçu : les chantiers sont ajoutés à la fin de la journée dans cet ordre
        ancienne_date = conn.execute("SELECT date_prevue FROM chantiers WHERE id = ?", (i,)).fetchone()[0]
        if h is None:
            conn.execute("UPDATE chantiers SET statut = 'planifie', date_prevue = ? WHERE id = ?", (d, i))
        else:
            conn.execute("UPDATE chantiers SET statut = 'planifie', date_prevue = ?, duree_estimee_h = ? WHERE id = ?",
                         (d, float(h), i))
        ajuster_ordre(conn, i, ancienne_date)
    return []


# ---------------------------------------------------------------------------
# Ordre de passage dans une journée et heures calculées
# ---------------------------------------------------------------------------
DEBUT_JOURNEE = 7 * 60 + 30            # 7 h 30 : début de la première intervention (minutes depuis minuit)
DINER_DEBUT, DINER_FIN = 12 * 60, 12 * 60 + 30   # pause dîner fixe, 12 h 00 - 12 h 30


def heure_texte(minutes):
    """450 -> « 7 h 30 »."""
    return f"{minutes // 60} h {minutes % 60:02d}"


# Un chantier « planifié » ou « terminé » a sa place dans la journée de sa date (un chantier terminé garde son rang).
def ids_de_la_journee(conn, jour):
    """Identifiants des chantiers de ce jour-là (planifiés ou terminés), dans leur ordre de passage."""
    return [r[0] for r in conn.execute(
        "SELECT id FROM chantiers WHERE statut IN ('planifie', 'termine') AND date_prevue = ?"
        " ORDER BY COALESCE(ordre_jour, 1000000), id", (jour,))]


def ajuster_ordre(conn, chantier_id, ancienne_date=None):
    """Garde ordre_jour cohérent : NULL hors « planifié » / « terminé », sinon rang dans la journée (ajouté à la fin
    si nouveau ou si le chantier vient de changer de jour)."""
    statut, jour, ordre = conn.execute("SELECT statut, date_prevue, ordre_jour FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if statut not in ("planifie", "termine"):
        if ordre is not None:
            conn.execute("UPDATE chantiers SET ordre_jour = NULL WHERE id = ?", (chantier_id,))
        return
    if ordre is None or (ancienne_date is not None and ancienne_date != jour):
        suivant = conn.execute("SELECT COALESCE(MAX(ordre_jour), 0) + 1 FROM chantiers WHERE statut IN ('planifie', 'termine') "
                               "AND date_prevue = ? AND id <> ?", (jour, chantier_id)).fetchone()[0]
        conn.execute("UPDATE chantiers SET ordre_jour = ? WHERE id = ?", (suivant, chantier_id))


def deplacer(conn, chantier_id, sens):
    """Monte (« haut ») ou descend (« bas ») un chantier dans l'ordre de passage de sa journée.

    Les rangs de la journée sont renumérotés 1, 2, 3... Au début ou à la fin de la liste, rien ne bouge.
    """
    if sens not in ("haut", "bas"):
        return [f"sens « {sens} » inconnu"]
    r = conn.execute("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"chantier #{chantier_id} introuvable"]
    if r[0] not in ("planifie", "termine"):
        return ["seul un chantier planifié ou terminé a un ordre de passage"]
    ids = ids_de_la_journee(conn, r[1])
    i = ids.index(chantier_id)
    j = i - 1 if sens == "haut" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    for rang, x in enumerate(ids, 1):
        conn.execute("UPDATE chantiers SET ordre_jour = ? WHERE id = ? AND ordre_jour IS NOT ?", (rang, x, rang))
    return []


def calculer_horaire(durees_h):
    """Heures de passage d'une journée, d'après l'ordre et les durées estimées (en heures, None si inconnue).

    Début à 7 h 30, dîner fixe de 12 h 00 à 12 h 30 : un chantier qui commencerait pendant le dîner commence à
    12 h 30 ; un chantier qui chevauche 12 h 00 est prolongé de 30 minutes (le dîner est pris au milieu).
    Les trajets ne sont pas comptés. Retourne une liste de dicts : debut, fin (minutes depuis minuit),
    diner_dans (le dîner tombe pendant ce chantier), diner_avant (le dîner a eu lieu juste avant ce chantier),
    duree_inconnue.
    """
    t, precedent_fin, resultat = DEBUT_JOURNEE, None, []
    for h in durees_h:
        minutes = round(h * 60) if h else 0
        if DINER_DEBUT <= t < DINER_FIN:
            t = DINER_FIN
        debut, fin, diner_dans = t, t + minutes, False
        if debut < DINER_DEBUT < fin:
            fin += DINER_FIN - DINER_DEBUT
            diner_dans = True
        diner_avant = precedent_fin is not None and precedent_fin <= DINER_DEBUT and debut >= DINER_FIN
        resultat.append({"debut": debut, "fin": fin, "diner_dans": diner_dans, "diner_avant": diner_avant,
                         "duree_inconnue": not h})
        t = precedent_fin = fin
    return resultat


# ---------------------------------------------------------------------------
# Duplication (travaux récurrents)
# ---------------------------------------------------------------------------
def dupliquer_chantier(conn, chantier_id, prix_ht=None, avec_taxes=None, duree=None, description=None):
    """Crée une nouvelle SOUMISSION d'après un chantier existant (de n'importe quel statut).

    Copie : client, types de travaux et précisions, description, durée estimée, prix, modalité de paiement.
    Réinitialise : dates (demande = aujourd'hui, pas de date de travaux), paiements, facture, durée réelle, fichiers.
    Le prix peut être ajusté ; les taxes sont alors recalculées (avec_taxes=None : reprend le choix de l'original).
    Retourne (id du nouveau chantier ou None, erreurs).
    """
    src = conn.execute("SELECT client_id, description, duree_estimee_h, prix_ht, tps, tvq, modalite_paiement FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if src is None:
        return None, [f"chantier #{chantier_id} introuvable"]
    client_id, desc, duree_src, prix_src, tps_src, tvq_src, modalite = src
    L = Ligne({"prix_ht": prix_ht if prix_ht is not None else "", "duree_estimee_h": duree if duree is not None else ""})
    prix, h = L.montant("prix_ht"), L.duree("duree_estimee_h")
    if L.erreurs:
        return None, L.erreurs
    prix = prix if prix is not None else (Decimal(str(prix_src)) if prix_src is not None else None)
    duree_finale = float(h) if h is not None else duree_src
    if not duree_finale:
        return None, ["la durée estimée est obligatoire (en heures, ex. 2,5)"]
    if avec_taxes is None:
        avec_taxes = (tps_src or 0) + (tvq_src or 0) > 0
    tps, tvq = taxes_pour(prix) if (avec_taxes and prix is not None) else (Decimal("0"), Decimal("0"))
    cur = conn.execute(
        "INSERT INTO chantiers (client_id, description, statut, date_soumission, duree_estimee_h, prix_ht, tps, tvq, modalite_paiement)"
        " VALUES (?, ?, 'soumission', ?, ?, ?, ?, ?, ?)",
        (client_id, (description if description is not None else desc), datetime.date.today().isoformat(), duree_finale,
         _num(prix), float(tps), float(tvq), modalite))
    conn.execute("INSERT INTO chantier_travaux (chantier_id, type_travaux, precision) "
                 "SELECT ?, type_travaux, precision FROM chantier_travaux WHERE chantier_id = ?", (cur.lastrowid, chantier_id))
    return cur.lastrowid, []


def supprimer_chantier(conn, chantier_id):
    """Supprime un chantier (et le client s'il n'en a plus). Un chantier terminé est verrouillé : jamais supprimé."""
    r = conn.execute("SELECT client_id, statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"chantier #{chantier_id} introuvable"]
    if r[1] == "termine":
        return ["Chantier terminé : verrouillé, il ne peut pas être supprimé"]
    if conn.execute("SELECT 1 FROM paiements WHERE chantier_id = ?", (chantier_id,)).fetchone():
        return ["Impossible de supprimer : ce chantier a des paiements. Supprime-les d'abord."]
    conn.execute("DELETE FROM chantiers WHERE id = ?", (chantier_id,))
    if not conn.execute("SELECT 1 FROM chantiers WHERE client_id = ?", (r[0],)).fetchone():
        conn.execute("DELETE FROM clients WHERE id = ?", (r[0],))
    return []
