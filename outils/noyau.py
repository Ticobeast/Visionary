"""Noyau partagé : validation d'une fiche et écriture dans la base SQLite.

Utilisé par l'interface (interface.py) et par le générateur de données d'essai (donnees_test.py), pour que tout
passe par les mêmes règles. Bibliothèque standard seulement (Python 3.9+).
"""
import datetime
import hashlib
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCHEMA = RACINE / "schema" / "schema.sql"
MIGRATION_8_9 = RACINE / "schema" / "migration_v8_v9.sql"     # ajout des comptes
MIGRATION_9_10 = RACINE / "schema" / "migration_v9_v10.sql"   # tables figées créées par l'étape 9 -> 10 (clients assouplis, raccourcis)
# Migrations conservées parce que des données réelles peuvent exister : 8 -> 9 (comptes), 9 -> 10 (soumissions), 10 -> 11 (en attente),
# 11 -> 12 (numéros jamais réutilisés), 12 -> 13 (date de la facture), 13 -> 14 (nouvelle adresse d'un client), 14 -> 15 (fusion de deux fiches), 15 -> 16 (journal des modifications) ; les sept dernières s'enchaînent en une seule transaction (voir _migrer_vers_courant).
DB_DEFAUT = RACINE / "data" / "sylvainculteur.db"
VERSION_SCHEMA = 16
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
    "adresse", "ville", "client_secteur", "code_postal",
    "type_travaux", "nacelle", "debarrasser_bois", "bois_format", "statut", "description",
    "date_soumission", "date_prevue",
    "duree_estimee_h", "duree_reelle_h",
    "prix_ht", "tps", "tvq", "modalite_paiement",
    "paiement_date", "paiement_montant", "paiement_mode",
    "notes_acces", "dossier_photos",
    "client_telephone_2", "client_courriel", "client_sms_ok", "client_notes",
    "province", "latitude", "longitude",
]

# Statuts officiels, dans l'ordre du parcours d'un chantier.
STATUTS = ("soumission", "en_attente", "a_planifier", "planifie", "termine", "annule")
LIBELLES_STATUT = {"soumission": "Soumission", "en_attente": "En attente", "a_planifier": "À planifier",
                   "planifie": "Planifié", "termine": "Terminé", "annule": "Annulé"}
# Statuts sans date : le chantier n'est pas (encore) placé dans une journée.
STATUTS_SANS_DATE = ("soumission", "en_attente", "a_planifier")
# Une SOUMISSION est un chantier pas encore accepté (même fiche, autre nom) : onglet « Soumissions », rien d'obligatoire.
# « en_attente » n'en est plus une : c'est un chantier ACCEPTÉ mis de côté jusqu'à une date (reprise_le) ou à nouvel ordre.
STATUTS_SOUMISSION = ("soumission",)
# Ce qu'il faut pour ACCEPTER une soumission (elle devient alors un chantier « À planifier »). Pour changer la règle,
# modifier cette liste et manques_pour_accepter().
CONDITIONS_ACCEPTATION = (
    ("nom", "le nom du client (ou son entreprise)"),
    ("telephone", "un numéro de téléphone"),
    ("adresse", "l'adresse des travaux"),
    ("secteur", "le secteur (ville)"),
    ("travaux", "au moins un type de travaux"),
    ("bois", "ce qu'on fait du bois (le débarrasser, ou son format : 16 pouces / 4 pieds)"),   # seulement pour un abattage ou un élagage
    ("duree", "la durée estimée"),
    ("prix", "le prix"),
)
MODES = ("comptant", "cheque", "interac", "carte", "autre")
LIBELLES_MODE = {"comptant": "Comptant", "cheque": "Chèque", "interac": "Interac", "carte": "Carte", "autre": "Autre"}
# Bois qui reste sur place (abattage / élagage) : format des morceaux.
FORMATS_BOIS = ("16_pouces", "4_pieds")
LIBELLES_BOIS = {"16_pouces": "16 pouces", "4_pieds": "4 pieds"}
TYPES_AVEC_BOIS = ("abattage", "elagage")        # types de travaux où le sort du bois doit être précisé
# Plus aucun statut ne se choisit à la main : Soumission (création) -> Accepter -> À planifier -> Journée -> Planifié ->
# Terminer -> Terminé ; Refuser / Annuler -> Annulé (archives).


def libelle_statut(statut, genre=None):
    """« Refusée » pour une soumission refusée (annulée sans avoir été acceptée), sinon le libellé du statut."""
    if statut == "annule" and genre == "soumission":
        return "Refusée"
    return LIBELLES_STATUT.get(statut, statut)


def adresses(adresse, ville, province, code_postal):
    """(texte affiché, texte pour Google Maps) ; deux textes vides tant que l'adresse n'est pas connue.
    Les morceaux vides sont sautés : jamais « 9 Rue des Lilas, , QC »."""
    if not adresse:
        return "", ""
    texte = ", ".join(x for x in (adresse, ville, province) if x) + (f" {code_postal}" if code_postal else "")
    return texte, texte + ", Canada"

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

    def travaux(self, col, alias, obligatoire=True):
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
        if not morceaux and obligatoire:
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


def _lire_client(L, v, exige=True):
    """Champs du client et de son adresse (communs à la fiche chantier et à la fiche client).

    exige=False (soumission) : rien n'est obligatoire, seuls les formats sont vérifiés ; adresse et ville vides = « ».
    """
    v["client_nom"] = L.texte("client_nom")
    v["client_prenom"] = L.texte("client_prenom")
    v["client_entreprise"] = L.texte("client_entreprise")
    if exige and not (v["client_nom"] or v["client_entreprise"]):
        L.erreurs.append("client_nom ou client_entreprise est obligatoire")
    v["client_telephone"] = L.telephone("client_telephone")
    v["client_telephone_2"] = L.telephone("client_telephone_2")
    v["client_courriel"] = L.texte("client_courriel")
    if v["client_courriel"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v["client_courriel"]):
        L.erreurs.append(f"client_courriel « {v['client_courriel']} » invalide")
        v["client_courriel"] = None
    v["client_sms_ok"] = L.booleen("client_sms_ok")
    v["client_notes"] = L.texte("client_notes", multiligne=True)

    v["adresse"] = (L.requis("adresse") if exige else L.texte("adresse")) or ""
    v["ville"] = (L.requis("ville") if exige else L.texte("ville")) or ""
    v["secteur"] = L.texte("client_secteur")        # code du secteur (résolu par appliquer_secteur)
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


def lire_client(brut, exige=True):
    """Valide la fiche d'un client seule. Retourne (valeurs, erreurs). exige=False : rien d'obligatoire (client d'une soumission)."""
    L = Ligne(brut)
    v = {}
    _lire_client(L, v, exige)
    return v, L.erreurs


def lire_ligne(brut, alias_types, taxes_auto):
    """Retourne (valeurs, erreurs) pour une ligne brute (CSV ou formulaire) : client + chantier."""
    L = Ligne(brut)
    v = {}
    alias_statuts = {**{cle(c): c for c in STATUTS}, **{cle(l): c for c, l in LIBELLES_STATUT.items()}}
    v["statut"] = L.choix("statut", STATUTS, alias_statuts, obligatoire=True)
    exige = v["statut"] not in STATUTS_SOUMISSION        # une soumission se remplit comme on veut ; la suite exige l'essentiel
    _lire_client(L, v, exige)

    v["travaux"] = L.travaux("type_travaux", alias_types, obligatoire=exige)
    v["nacelle"] = L.booleen("nacelle") or 0
    v["debarrasser_bois"] = L.booleen("debarrasser_bois") or 0
    alias_bois = {**{cle(c): c for c in FORMATS_BOIS}, **{cle(l): c for c, l in LIBELLES_BOIS.items()}}
    v["bois_format"] = L.choix("bois_format", FORMATS_BOIS, alias_bois)
    if v["bois_format"] and v["debarrasser_bois"]:
        L.erreurs.append("bois_format n'a de sens que si le bois n'est pas débarrassé (debarrasser_bois = non)")
    v["description"] = L.texte("description", multiligne=True)
    v["date_soumission"] = L.jour("date_soumission")
    v["date_prevue"] = L.jour("date_prevue")
    v["duree_estimee_h"] = L.duree("duree_estimee_h")
    if exige and v["duree_estimee_h"] is None and not any("duree_estimee_h" in e for e in L.erreurs):
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

    v["paiement_date"] = L.jour("paiement_date")
    v["paiement_montant"] = L.montant("paiement_montant")
    v["paiement_mode"] = L.choix("paiement_mode", MODES)
    trio = (v["paiement_date"], v["paiement_montant"], v["paiement_mode"])
    if any(c is not None for c in trio) and not all(c is not None for c in trio):
        if not L.erreurs:  # évite le doublon avec une erreur de format déjà signalée
            L.erreurs.append("paiement_date, paiement_montant et paiement_mode vont ensemble (les trois ou aucun)")
    if v["paiement_montant"] is not None and v["paiement_montant"] == 0:
        L.erreurs.append("paiement_montant doit être supérieur à 0")

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
        if version in (8, 9, 10, 11, 12, 13, 14, 15):                 # migrations automatiques, précédées d'une copie de sécurité
            try:
                sauvegarder(db_path, f"avant_migration_v{version}")
                if version == 8:                            # v8 -> v9 : seulement deux nouvelles tables, rien n'est modifié
                    conn.executescript(MIGRATION_8_9.read_text(encoding="utf-8"))
                    conn.execute("PRAGMA foreign_keys = ON")
                    version = 9
                if version in (9, 10, 11, 12, 13, 14, 15):  # v9 -> v10 -> ... -> v16 : en UNE transaction, tout ou rien
                    _migrer_vers_courant(conn, version)
                    version = VERSION_SCHEMA
            except BaseException:
                conn.close()
                raise
        if version != VERSION_SCHEMA:
            conn.close()
            if version > VERSION_SCHEMA:
                raise SystemExit(f"La base {db_path} a été écrite par une version plus récente du programme (format v{version}, ici v{VERSION_SCHEMA}).\n"
                                 "Mets le programme à jour, puis relance. Ne supprime pas ce fichier : il contient tes données.")
            raise SystemExit(f"La base {db_path} est d'un format trop ancien pour être mise à jour toute seule (format v{version}, attendu v{VERSION_SCHEMA}).\n"
                             "Ne supprime pas ce fichier : il contient peut-être des données. Mets-le de côté et demande de l'aide "
                             "(pour la base d'essai, relance simplement lancer_essai : elle est refaite).")
    return conn, existait


def _instructions(texte):
    """Les instructions SQL complètes d'un texte, une à une (executescript validerait la transaction en cours)."""
    courante = ""
    for ligne in texte.splitlines(keepends=True):
        courante += ligne
        if sqlite3.complete_statement(courante):
            if courante.strip().rstrip(";").strip():
                yield courante
            courante = ""


def _etapes_9_10(conn):
    """Format v9 -> v10 (à l'intérieur de la transaction de _migrer_vers_courant) :

      * table `clients` reconstruite sans les champs obligatoires (nom, adresse) : une soumission s'ouvre avec ce qu'on sait ;
      * `chantiers` reçoit `accepte_le` et `cree_par` ; les chantiers existants sont considérés comme déjà acceptés ;
        l'ancien statut « en attente » (soumission remise) devient « soumission » ;
      * table `raccourcis`.
    Les tables viennent de schema/migration_v9_v10.sql (définitions figées : schema.sql peut évoluer sans les changer).
    """
    colonnes = ("id, prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, adresse, ville, secteur, province, code_postal,"
                " latitude, longitude, geocode_statut, notes_acces, notes, cree_le")
    definitions = list(_instructions(MIGRATION_9_10.read_text(encoding="utf-8")))
    conn.execute(definitions[0])                                        # CREATE TABLE clients_nouveau
    conn.execute(f"INSERT INTO clients_nouveau ({colonnes}) SELECT {colonnes} FROM clients")
    conn.execute("DROP TABLE clients")
    conn.execute("ALTER TABLE clients_nouveau RENAME TO clients")
    conn.execute("ALTER TABLE chantiers ADD COLUMN accepte_le TEXT CONSTRAINT ck_chantiers_accepte_le "
                 "CHECK (accepte_le IS NULL OR date(accepte_le, '+0 days') IS accepte_le)")
    conn.execute("ALTER TABLE chantiers ADD COLUMN cree_par TEXT")
    conn.execute("UPDATE chantiers SET statut = 'soumission' WHERE statut = 'en_attente'")
    conn.execute("UPDATE chantiers SET accepte_le = COALESCE(date_soumission, date(cree_le)) WHERE statut <> 'soumission'")
    for instruction in definitions[1:]:                                 # raccourcis et son index
        conn.execute(instruction)


def _etapes_10_11(conn):
    """Format v10 -> v11 : `chantiers.reprise_le` (mise en attente d'un chantier accepté, avec date de retour facultative).
    Au format v10, « en attente » n'était qu'un vieux nom de « soumission » : ces fiches deviennent des soumissions."""
    conn.execute("ALTER TABLE chantiers ADD COLUMN reprise_le TEXT CONSTRAINT ck_chantiers_reprise_le "
                 "CHECK (reprise_le IS NULL OR date(reprise_le, '+0 days') IS reprise_le)")
    conn.execute("UPDATE chantiers SET statut = 'soumission' WHERE statut = 'en_attente'")


TABLES_NUMEROTEES = ("clients", "chantiers", "paiements", "utilisateurs", "raccourcis")   # numéro AUTOINCREMENT depuis le format v12


def _definitions_du_schema():
    """[(type, nom, table, sql)] de chaque CREATE de schema.sql (table, index, trigger, vue), dans l'ordre du fichier.
    `table` est la table visée par un index ou un déclencheur (sinon le nom lui-même)."""
    resultat = []
    for sql in _instructions(SCHEMA.read_text(encoding="utf-8")):
        lignes = sql.splitlines()
        while lignes and (not lignes[0].strip() or lignes[0].lstrip().startswith("--")):
            lignes.pop(0)                                               # commentaires AVANT le CREATE : SQLite ne les garde pas ; ceux du corps, oui
        sans_commentaires = "\n".join(lignes)
        m = re.match(r"\s*CREATE\s+(TABLE|INDEX|TRIGGER|VIEW)\s+(\w+)", sans_commentaires, re.IGNORECASE)
        if not m:
            continue
        genre, nom = m.group(1).upper(), m.group(2)
        cible = re.search(r"\bON\s+(\w+)", sans_commentaires)
        resultat.append((genre, nom, cible.group(1) if genre in ("INDEX", "TRIGGER") and cible else nom, sans_commentaires.strip().rstrip(";")))
    return resultat


def _reconstruire_tables(conn, tables):
    """Reconstruit chaque table de `tables` d'après sa définition dans schema.sql : nouvelle table, copie des lignes avec leurs numéros,
    suppression de l'ancienne, renommage, puis ses index sont recréés. Le compteur AUTOINCREMENT (sqlite_sequence) est conservé tel quel :
    un numéro déjà donné n'est jamais repris, même si la dernière fiche a été supprimée.
    Les définitions viennent de schema.sql (pas de copie figée : ce sont celles d'une base neuve, la base migrée leur est donc identique).
    Les déclencheurs et la vue, supprimés avant d'arriver ici, sont recréés par _migrer_vers_courant. Pas de ALTER TABLE ... RENAME
    d'une ancienne table : cela réécrirait les clés étrangères des autres tables pour les faire pointer vers elle."""
    definitions = _definitions_du_schema()
    for table in tables:
        compteur = None
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'sqlite_sequence'").fetchone():
            compteur = conn.execute("SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)).fetchone()
        creation = next(sql for genre, nom, _, sql in definitions if genre == "TABLE" and nom == table)
        conn.execute(re.sub(r"(CREATE\s+TABLE\s+)" + table + r"\b", r"\1" + table + "_nouveau", creation, count=1, flags=re.IGNORECASE))
        anciennes = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        colonnes = ", ".join(r[1] for r in conn.execute(f"PRAGMA table_info({table}_nouveau)") if r[1] in anciennes)   # une colonne neuve reste à sa valeur par défaut
        conn.execute(f"INSERT INTO {table}_nouveau ({colonnes}) SELECT {colonnes} FROM {table}")
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {table}_nouveau RENAME TO {table}")
        for genre, nom, cible, sql in definitions:
            if genre == "INDEX" and cible == table:
                conn.execute(sql)
        if compteur is not None:
            conn.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (compteur[0], table))


def _etapes_11_12(conn):
    """Format v11 -> v12 : un numéro de fiche n'est plus jamais réutilisé (INTEGER PRIMARY KEY AUTOINCREMENT).
    SQLite ne sait pas ajouter AUTOINCREMENT à une table existante : chaque table de TABLES_NUMEROTEES est reconstruite.
    (Au format v11, aucune table n'avait de compteur : il vaut alors le plus grand numéro copié ; un test le vérifie.)"""
    _reconstruire_tables(conn, TABLES_NUMEROTEES)


def _etapes_12_13(conn):
    """Format v12 -> v13 : `chantiers.facture_le` (date de la facture, figée quand le chantier est terminé). Les chantiers déjà terminés
    n'ont pas de date enregistrée : ils recevront une fois pour toutes le jour des travaux, à la prochaine ouverture de la facture. `chantiers` est reconstruite (et non ALTER TABLE
    ADD COLUMN) pour que sa définition soit identique à celle d'une base neuve ; le compteur de numéros est conservé."""
    _reconstruire_tables(conn, ("chantiers",))


def _etapes_14_15(conn):
    """Format v14 -> v15 : `clients.fusionne_dans` (fiche en double -> fiche gardée), vide partout au départ. Cette étape sert aussi
    de v13 -> v14 (`clients.remplace_par`) : schema.sql contient les deux colonnes, donc UNE seule reconstruction de `clients` suffit.
    `clients` est reconstruite (et non ALTER TABLE ADD COLUMN, qui ne pose pas toutes les règles) pour que sa définition soit identique
    à celle d'une base neuve ; ses lignes, ses numéros et son compteur de numéros sont conservés."""
    _reconstruire_tables(conn, ("clients",))


def _etapes_15_16(conn):
    """Format v15 -> v16 : table `journal` (neuve : rien à copier) et son index, d'après schema.sql. Ses deux déclencheurs (journal
    en lecture seule) sont recréés avec les autres à la fin de _migrer_vers_courant. S'applique aussi aux bases venues de v9 à v14."""
    for genre, nom, _, sql in _definitions_du_schema():
        if (genre == "TABLE" and nom == "journal") or (genre == "INDEX" and nom == "idx_journal_quand"):
            conn.execute(sql)


def _migrer_vers_courant(conn, version):
    """Formats v9 à v15 -> format courant, en UNE seule transaction (tout ou rien). Les déclencheurs et la vue sont supprimés au
    début puis recréés à la fin, tels que dans schema.sql : la base migrée est identique à une base neuve (un test le vérifie)."""
    definitions = _definitions_du_schema()
    conn.execute("PRAGMA foreign_keys = OFF")                           # sans effet à l'intérieur d'une transaction : à faire avant
    try:
        conn.execute("BEGIN")
        for (nom,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
            conn.execute(f"DROP TRIGGER {nom}")
        conn.execute("DROP VIEW IF EXISTS v_chantiers")
        if version == 9:
            _etapes_9_10(conn)
        if version in (9, 10):
            _etapes_10_11(conn)
        if version in (9, 10, 11):
            _etapes_11_12(conn)         # reconstruit déjà `clients` et `chantiers` d'après le schéma courant (facture_le, remplace_par, fusionne_dans)
        else:
            if version == 12:
                _etapes_12_13(conn)
            if version < 15:
                _etapes_14_15(conn)     # v12, v13 et v14 : `clients` reconstruite une seule fois
        _etapes_15_16(conn)             # toutes les versions : la table `journal` est neuve
        for genre, nom, _, sql in definitions:
            if genre in ("TRIGGER", "VIEW"):
                conn.execute(sql)
        problemes = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problemes:
            raise sqlite3.IntegrityError(f"la migration laisserait des liens brisés : {problemes[:3]}")
        conn.execute(f"PRAGMA user_version = {VERSION_SCHEMA}")
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def alias_types_travaux(conn):
    """{forme comparable du code ou du libellé: code}"""
    alias = {}
    for code, libelle in conn.execute("SELECT code, libelle FROM types_travaux"):
        alias[cle(code)] = code
        alias[cle(libelle)] = code
    return alias


def sauvegarder(db, etiquette="sauvegarde"):
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
                "SELECT id, prenom, nom, entreprise, telephone, telephone_2, adresse, ville FROM clients"
                " WHERE remplace_par IS NULL AND fusionne_dans IS NULL"):     # une ancienne adresse ou un doublon fusionné n'est jamais proposé ni réutilisé
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
        if not cle(v["adresse"]):                    # adresse inconnue (soumission) : jamais regroupé avec un autre client
            return None, None
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


def _num(d):
    return None if d is None else float(d)


def trouver_ou_creer_client(conn, idx, v, res):
    """Retourne l'id du client de la fiche v : le client déjà présent à cette adresse, ou un nouveau.

    La fiche d'un client existant n'est JAMAIS modifiée ici (seule la fiche client le permet).
    """
    client_id, _ = idx.trouver(v)
    if client_id is None:
        cur = conn.execute(
            "INSERT INTO clients (prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok,"
            " adresse, ville, secteur, province, code_postal, latitude, longitude, geocode_statut, notes_acces, notes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (v["client_prenom"], v["client_nom"], v["client_entreprise"], v["client_telephone"],
             v["client_telephone_2"], v["client_courriel"],
             1 if v["client_sms_ok"] is None else v["client_sms_ok"],
             v["adresse"], v["ville"], v["secteur"], v["province"], v["code_postal"], v["latitude"], v["longitude"],
             "manuel" if v["latitude"] is not None else "a_faire", v["notes_acces"], v["client_notes"]))
        client_id = cur.lastrowid
        res.clients_crees += 1
    else:
        res.clients_reutilises += 1
    ligne = conn.execute(
        "SELECT id, prenom, nom, entreprise, telephone, telephone_2, adresse, ville FROM clients WHERE id = ?",
        (client_id,)).fetchone()
    idx.ajouter(*ligne)
    return client_id


def _valeurs_chantier(v):
    return (v["description"], v["statut"], v["date_soumission"], v["date_prevue"], v["nacelle"], v["debarrasser_bois"], v["bois_format"],
            _num(v["duree_estimee_h"]), _num(v["duree_reelle_h"]), _num(v["prix_ht"]), _num(v["tps"]) or 0,
            _num(v["tvq"]) or 0, v["modalite_paiement"], v["dossier_photos"])


COLONNES_CHANTIER = ["description", "statut", "date_soumission", "date_prevue", "nacelle", "debarrasser_bois", "bois_format",
                     "duree_estimee_h", "duree_reelle_h", "prix_ht", "tps", "tvq", "modalite_paiement",
                     "dossier_photos"]


def _ecrire_travaux(conn, chantier_id, travaux):
    conn.execute("DELETE FROM chantier_travaux WHERE chantier_id = ?", (chantier_id,))
    conn.executemany("INSERT INTO chantier_travaux (chantier_id, type_travaux, precision) VALUES (?,?,?)",
                     [(chantier_id, code, precision) for code, precision in travaux])


def creer_chantier(conn, client_id, v, res, cree_par=None):
    """Crée la fiche (soumission, ou chantier déjà accepté pour un import) et son paiement éventuel. Retourne son id.

    cree_par : nom du compte qui l'ouvre. Une fiche créée directement « acceptée » reçoit sa date d'acceptation.
    """
    accepte_le = None if v["statut"] in STATUTS_SOUMISSION else (v["date_soumission"] or datetime.date.today().isoformat())
    colonnes = COLONNES_CHANTIER + ["accepte_le", "cree_par"]
    cur = conn.execute(
        f"INSERT INTO chantiers (client_id, {', '.join(colonnes)}) VALUES (?{',?' * len(colonnes)})",
        (client_id, *_valeurs_chantier(v), accepte_le, cree_par))
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
    a_ecrire = [(c, val) for c, val in zip(COLONNES_CHANTIER, _valeurs_chantier(v)) if c not in ("statut", "date_prevue")]
    conn.execute(f"UPDATE chantiers SET {', '.join(c + ' = ?' for c, _ in a_ecrire)} WHERE id = ?",
                 (*(val for _, val in a_ecrire), chantier_id))      # statut et date : seulement par les boutons (accepter, Journée...)
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
        "adresse": v["adresse"], "ville": v["ville"], "secteur": v["secteur"], "province": v["province"],
        "code_postal": v["code_postal"], "notes_acces": v["notes_acces"], "notes": v["client_notes"],
        **coords,
    }
    conn.execute(f"UPDATE clients SET {', '.join(f'{c} = ?' for c in champs)} WHERE id = ?",
                 (*champs.values(), client_id))


def client_remplacant(conn, client_id):
    """Fiche à utiliser pour une NOUVELLE soumission : si le client a déménagé, la fiche à la nouvelle adresse ; si la fiche est un
    doublon fusionné, la fiche gardée (on suit la chaîne, avec une protection contre une boucle). Retourne client_id lui-même
    si la fiche n'a été ni remplacée ni fusionnée."""
    vus = {client_id}
    courant = client_id
    while True:
        r = conn.execute("SELECT COALESCE(fusionne_dans, remplace_par) FROM clients WHERE id = ?", (courant,)).fetchone()
        if r is None or r[0] is None or r[0] in vus:
            return courant
        courant = r[0]
        vus.add(courant)


def fiche_gardee(conn, client_id):
    """Fiche à ouvrir à la place d'un doublon fusionné : la fiche gardée. Retourne client_id lui-même si la fiche n'est pas fusionnée.
    (Contrairement à client_remplacant, ne suit pas une nouvelle adresse : l'ancienne adresse d'un client reste consultable.)"""
    r = conn.execute("SELECT fusionne_dans FROM clients WHERE id = ?", (client_id,)).fetchone()
    return r[0] if r and r[0] is not None else client_id


def doublons_fusionnes(conn, client_id):
    """Numéros des fiches en double fusionnées dans cette fiche (cachées, avec leurs chantiers terminés)."""
    return [r[0] for r in conn.execute("SELECT id FROM clients WHERE fusionne_dans = ? ORDER BY id", (client_id,))]


MSG_FUSION_LIEN = ("Une autre fiche (n° {autre}) est liée à la fiche à cacher (n° {doublon}) : fusionne plutôt dans l'autre sens, "
                   "ou règle d'abord l'autre fiche.")
CHAMPS_FUSION = ("telephone", "telephone_2", "courriel", "code_postal", "notes_acces", "notes")


def erreurs_fusion(conn, garde_id, doublon_id):
    """Pourquoi la fusion est refusée (liste vide : elle est possible). Ne modifie rien."""
    if garde_id == doublon_id:
        return ["Choisis deux fiches différentes : une fiche ne peut pas être fusionnée avec elle-même."]
    for i in (garde_id, doublon_id):
        r = conn.execute("SELECT remplace_par, fusionne_dans FROM clients WHERE id = ?", (i,)).fetchone()
        if r is None:
            return [f"La fiche n° {i} n'existe pas."]
        if r[1] is not None:
            return [f"La fiche n° {i} est déjà fusionnée avec une autre : on ne peut plus la fusionner."]
        if r[0] is not None:
            return [f"La fiche n° {i} est une ancienne adresse du client : ouvre plutôt sa fiche à la nouvelle adresse."]
    lie = conn.execute("SELECT id FROM clients WHERE remplace_par = ? OR fusionne_dans = ? ORDER BY id", (doublon_id, doublon_id)).fetchone()
    if lie is not None:
        return [MSG_FUSION_LIEN.format(autre=lie[0], doublon=doublon_id)]
    return []


def fusionner_clients(conn, garde_id, doublon_id):
    """Deux fiches sont le même client : le doublon est fusionné dans la fiche gardée. S'il a des chantiers terminés (verrouillés par
    la base, ils restent sur lui avec leurs factures), il n'est PAS supprimé : il est marqué `fusionne_dans = garde_id` et n'apparaît
    plus nulle part. S'il n'en a aucun, il ne lui reste rien après le déplacement : il est simplement supprimé.
    Ses fiches NON terminées (soumissions, chantiers à planifier, planifiés, en attente, refusés, annulés) passent à la fiche gardée.
    Les champs vides de la fiche gardée sont complétés avec ceux du doublon ; son nom et son adresse ne changent jamais.
    À appeler dans une transaction. Retourne la liste des erreurs (vide si la fusion est faite)."""
    erreurs = erreurs_fusion(conn, garde_id, doublon_id)
    if erreurs:
        return erreurs
    lire = f"SELECT {', '.join(CHAMPS_FUSION)} FROM clients WHERE id = ?"
    g = dict(zip(CHAMPS_FUSION, conn.execute(lire, (garde_id,)).fetchone()))
    d = dict(zip(CHAMPS_FUSION, conn.execute(lire, (doublon_id,)).fetchone()))
    nouveau = dict(g)
    for champ in CHAMPS_FUSION:
        if not nouveau[champ] and d[champ]:
            nouveau[champ] = d[champ]
    if not g["telephone_2"] and g["telephone"] and d["telephone"] and d["telephone"] != g["telephone"]:
        nouveau["telephone_2"] = d["telephone"]                        # deux numéros différents : le second est gardé, pas perdu
    if nouveau["telephone_2"] and nouveau["telephone_2"] == nouveau["telephone"]:
        nouveau["telephone_2"] = None
    changes = {c: v for c, v in nouveau.items() if v != g[c]}
    if changes:
        conn.execute(f"UPDATE clients SET {', '.join(c + ' = ?' for c in changes)} WHERE id = ?", (*changes.values(), garde_id))
    conn.execute("UPDATE chantiers SET client_id = ? WHERE client_id = ? AND statut <> 'termine'", (garde_id, doublon_id))
    if conn.execute("SELECT 1 FROM chantiers WHERE client_id = ?", (doublon_id,)).fetchone() is None:
        conn.execute("DELETE FROM clients WHERE id = ?", (doublon_id,))     # plus rien dessus (aucun chantier terminé) : inutile de le garder caché
    else:
        conn.execute("UPDATE clients SET fusionne_dans = ? WHERE id = ?", (garde_id, doublon_id))
    return []


def nouvelle_adresse_client(conn, client_id, valeurs):
    """Le client déménage : crée une NOUVELLE fiche (mêmes coordonnées, nouvelle adresse) et marque l'ancienne comme « ancienne adresse »
    (remplace_par = la nouvelle). Aucun chantier, soumission ni paiement n'est déplacé : l'historique reste sur l'ancienne fiche.
    `valeurs` : adresse, client_secteur (code ou libellé), code_postal, notes_acces (clés de la feuille de saisie).
    À appeler dans une transaction. Retourne (nouvel_id, erreurs)."""
    ancien = conn.execute("SELECT prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, notes, adresse, ville, province, remplace_par"
                          " FROM clients WHERE id = ?", (client_id,)).fetchone()
    if ancien is None:
        return None, [f"Client #{client_id} introuvable."]
    prenom, nom, entreprise, tel, tel2, courriel, sms_ok, notes, adresse_ancienne, ville_ancienne, province, remplace_par = ancien
    if conn.execute("SELECT fusionne_dans FROM clients WHERE id = ?", (client_id,)).fetchone()[0] is not None:
        return None, ["Cette fiche a été fusionnée avec une autre : ouvre la fiche gardée pour changer l'adresse."]
    if remplace_par is not None:
        return None, ["Cette fiche est déjà une ancienne adresse : ouvre la fiche à la nouvelle adresse pour en faire une autre."]
    brut = {c: "" for c in COLONNES}
    brut.update({c: valeurs.get(c, "") or "" for c in ("adresse", "client_secteur", "code_postal", "notes_acces")})
    brut["province"] = province
    if not brut["adresse"].strip():
        return None, ["Écris la nouvelle adresse."]
    erreurs = appliquer_secteur(conn, brut, requis=True)             # la ville vient du secteur choisi
    if erreurs:
        return None, erreurs
    v, erreurs = lire_client(brut, exige=False)                      # on ne valide que l'adresse : le nom et le téléphone viennent de la fiche existante
    if erreurs:
        return None, erreurs
    if (cle(v["adresse"]), cle(v["ville"])) == (cle(adresse_ancienne), cle(ville_ancienne)):
        return None, ["C'est la même adresse que l'actuelle : rien à changer."]
    cur = conn.execute(
        "INSERT INTO clients (prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, adresse, ville, secteur, province,"
        " code_postal, geocode_statut, notes_acces, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'a_faire',?,?)",
        (prenom, nom, entreprise, tel, tel2, courriel, sms_ok, v["adresse"], v["ville"], v["secteur"], province,
         v["code_postal"], v["notes_acces"], notes))
    nouveau = cur.lastrowid
    conn.execute("UPDATE clients SET remplace_par = ? WHERE id = ?", (nouveau, client_id))
    return nouveau, []


# ---------------------------------------------------------------------------
# Transactions, valeurs de formulaire
# ---------------------------------------------------------------------------
@contextmanager
def transaction(conn):
    """BEGIN IMMEDIATE ... COMMIT, ou ROLLBACK si une exception survient.

    IMMEDIATE : le droit d'écrire est pris dès le début. Si quelqu'un d'autre écrit au même moment, on attend son tour (quelques
    secondes au plus) au lieu d'échouer tout de suite avec « database is locked » au milieu de la transaction."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _txt(x, fmt=None):
    return "" if x is None else (fmt(x) if fmt else str(x))


def empreinte(valeurs):
    """Signature courte d'une fiche (valeurs sous forme de textes) : sert à voir si quelqu'un d'autre l'a modifiée entre-temps."""
    return hashlib.sha1(repr(sorted(valeurs.items())).encode("utf-8")).hexdigest()[:16]


MSG_MODIFIE_ENTRE_TEMPS = ("Cette fiche vient d'être modifiée par quelqu'un d'autre : tes changements n'ont PAS été enregistrés. "
                           "Voici les valeurs à jour ; vérifie-les, puis refais ta modification si elle est encore nécessaire.")


def valeurs_client(conn, client_id):
    """Fiche d'un client sous forme de textes (clés de la feuille de saisie), ou None."""
    r = conn.execute("SELECT prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, adresse, ville, secteur,"
                     " province, code_postal, latitude, longitude, notes_acces, notes FROM clients WHERE id = ?",
                     (client_id,)).fetchone()
    if r is None:
        return None
    cols = ["client_prenom", "client_nom", "client_entreprise", "client_telephone", "client_telephone_2",
            "client_courriel", "client_sms_ok", "adresse", "ville", "client_secteur", "province", "code_postal", "latitude",
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


def decaler_mois(jour, n):
    """La même date n mois plus tard (n < 0 : plus tôt) ; le 31 devient le dernier jour d'un mois plus court."""
    rang = jour.year * 12 + jour.month - 1 + n
    annee, mois = divmod(rang, 12)
    mois += 1
    suivant = datetime.date(annee + (mois == 12), mois % 12 + 1, 1)
    return datetime.date(annee, mois, min(jour.day, (suivant - datetime.timedelta(days=1)).day))


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
    actuel = conn.execute("SELECT date_prevue, statut, duree_estimee_h, duree_reelle_h, accepte_le, date_soumission FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if actuel is None:
        L.erreurs.append(f"chantier #{chantier_id} introuvable")
    if L.erreurs:
        return L.erreurs
    ancienne_date, ancien_statut, duree_actuelle, reelle_actuelle, accepte_actuel, demande = actuel
    if ancien_statut == "termine":
        return [VERROU]
    if statut == "en_attente":
        return ["pour mettre un chantier en attente, utilise « Mettre en attente » : il demande la date de reprise"]
    if ancien_statut in STATUTS_SOUMISSION and statut in ("a_planifier", "planifie", "termine"):
        return ["une soumission doit d'abord être acceptée (bouton Accepter) : le programme vérifie alors que tout ce qu'il faut est rempli"]
    if ancien_statut == "en_attente" and statut in ("planifie", "termine"):
        return ["ce chantier est en attente : sors-le d'abord de l'attente (il redevient « À planifier »)"]
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
    if statut in STATUTS_SOUMISSION:                      # redevenue une soumission : plus acceptée, plus en attente
        colonnes["accepte_le"] = None
        colonnes["reprise_le"] = None
    elif not accepte_actuel and (statut in ("a_planifier", "planifie", "termine") or (statut == "annule" and ancien_statut in ("a_planifier", "planifie"))):
        colonnes["accepte_le"] = demande or datetime.date.today().isoformat()      # un chantier a toujours été accepté
    if statut == "a_planifier" and ancien_statut in ("en_attente", "annule"):
        colonnes["reprise_le"] = datetime.date.today().isoformat()     # de retour dans la file : le délai d'attente repart d'aujourd'hui
    if h is not None:
        colonnes["duree_estimee_h"] = float(h)
    if statut == "termine":
        colonnes["duree_reelle_h"] = float(hr) if hr is not None else (reelle_actuelle if reelle_actuelle is not None else duree_finale)
    marques = [c + " = ?" for c in colonnes]
    if statut == "termine":             # la date de la facture se fige : la dernière fois qu'elle a été ouverte, sinon aujourd'hui (jour de la fermeture)
        marques.append("facture_le = COALESCE(facture_le, ?)")
        colonnes["facture_le"] = datetime.date.today().isoformat()
    conn.execute(f"UPDATE chantiers SET {', '.join(marques)} WHERE id = ?",
                 (*colonnes.values(), chantier_id))
    ajuster_ordre(conn, chantier_id, ancienne_date)
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
        if r is None or r[0] not in ("a_planifier", "planifie"):
            L.erreurs.append(f"chantier #{i} : ne peut pas être planifié (statut {r[0] if r else 'introuvable'})")
            continue
        Lh = Ligne({"duree_estimee_h": durees.get(i, "")})
        h = Lh.duree("duree_estimee_h")
        L.erreurs.extend(f"chantier #{i} : {e}" for e in Lh.erreurs)
        if h is None and not r[1] and not Lh.erreurs:
            L.erreurs.append(f"chantier #{i} : la durée estimée est obligatoire (ouvre le chantier pour la saisir)")
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
def dupliquer_chantier(conn, chantier_id, prix_ht=None, avec_taxes=None, duree=None, description=None, cree_par=None):
    """Crée une nouvelle SOUMISSION d'après un chantier existant (de n'importe quel statut).

    Copie : client, types de travaux et précisions, description, durée estimée, prix, modalité de paiement.
    Réinitialise : dates (demande = aujourd'hui, pas de date de travaux), paiements, durée réelle, fichiers.
    Le prix peut être ajusté ; les taxes sont alors recalculées (avec_taxes=None : reprend le choix de l'original).
    Retourne (id du nouveau chantier ou None, erreurs).
    """
    src = conn.execute("SELECT client_id, description, duree_estimee_h, prix_ht, tps, tvq, modalite_paiement, nacelle, debarrasser_bois, bois_format"
                       " FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if src is None:
        return None, [f"chantier #{chantier_id} introuvable"]
    client_id, desc, duree_src, prix_src, tps_src, tvq_src, modalite, nacelle, bois, format_bois = src
    client_id = fiche_gardee(conn, client_id)       # un chantier terminé resté sur un doublon fusionné : la copie va à la fiche gardée
    L = Ligne({"prix_ht": prix_ht if prix_ht is not None else "", "duree_estimee_h": duree if duree is not None else ""})
    prix, h = L.montant("prix_ht"), L.duree("duree_estimee_h")
    if L.erreurs:
        return None, L.erreurs
    prix = prix if prix is not None else (Decimal(str(prix_src)) if prix_src is not None else None)
    duree_finale = float(h) if h is not None else duree_src       # facultative : c'est une soumission
    if avec_taxes is None:
        avec_taxes = (tps_src or 0) + (tvq_src or 0) > 0
    tps, tvq = taxes_pour(prix) if (avec_taxes and prix is not None) else (Decimal("0"), Decimal("0"))
    cur = conn.execute(
        "INSERT INTO chantiers (client_id, description, statut, date_soumission, duree_estimee_h, prix_ht, tps, tvq, modalite_paiement,"
        " nacelle, debarrasser_bois, bois_format, cree_par) VALUES (?, ?, 'soumission', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (client_id, (description if description is not None else desc), datetime.date.today().isoformat(), duree_finale,
         _num(prix), float(tps), float(tvq), modalite, nacelle, bois, format_bois, cree_par))
    conn.execute("INSERT INTO chantier_travaux (chantier_id, type_travaux, precision) "
                 "SELECT ?, type_travaux, precision FROM chantier_travaux WHERE chantier_id = ?", (cur.lastrowid, chantier_id))
    return cur.lastrowid, []


# ---------------------------------------------------------------------------
# Statuts automatiques : la Journée n'offre aucun choix de statut. Planifier = ajouter à une journée (planifier_lot) ;
# Retirer = retour à « À planifier » ; Annuler = « Annulé » (sort de la journée, va aux archives) ; Terminer = « Terminé ».
# ---------------------------------------------------------------------------
def annuler_chantier(conn, chantier_id):
    """Annule un chantier (il disparaît de sa journée et est archivé). Un chantier terminé ne s'annule pas."""
    return changer_statut(conn, chantier_id, "annule")


def rouvrir_chantier(conn, chantier_id):
    """Une fiche annulée par erreur est rouverte : un chantier annulé redevient « À planifier », une soumission refusée
    redevient une soumission en cours."""
    r = conn.execute("SELECT statut, accepte_le FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"chantier #{chantier_id} introuvable"]
    if r[0] != "annule":
        return ["seul un chantier annulé (ou une soumission refusée) peut être rouvert"]
    return changer_statut(conn, chantier_id, "a_planifier" if r[1] else "soumission")


def manques_pour_accepter(conn, chantier_id):
    """Ce qui manque encore pour accepter la soumission : liste de codes de CONDITIONS_ACCEPTATION (vide : tout est là)."""
    r = conn.execute("SELECT cl.nom, cl.entreprise, cl.telephone, cl.adresse, cl.secteur, c.duree_estimee_h, c.prix_ht,"
                     " (SELECT count(*) FROM chantier_travaux WHERE chantier_id = c.id),"
                     " (SELECT count(*) FROM chantier_travaux WHERE chantier_id = c.id AND type_travaux IN ('abattage', 'elagage')),"
                     " c.debarrasser_bois, c.bois_format"
                     " FROM chantiers c JOIN clients cl ON cl.id = c.client_id WHERE c.id = ?", (chantier_id,)).fetchone()
    if r is None:
        return []
    nom, entreprise, tel, adresse, secteur, duree, prix, n_travaux, n_bois, debarrasse, format_bois = r
    presents = {"nom": bool((nom or "").strip() or (entreprise or "").strip()), "telephone": bool(tel), "adresse": bool((adresse or "").strip()),
                "secteur": bool(secteur), "travaux": n_travaux > 0, "bois": not n_bois or bool(debarrasse) or bool(format_bois),
                "duree": bool(duree), "prix": prix is not None}
    return [code for code, _ in CONDITIONS_ACCEPTATION if not presents[code]]


def libelles_manques(codes):
    noms = dict(CONDITIONS_ACCEPTATION)
    return [noms[c] for c in codes]


def accepter_soumission(conn, chantier_id):
    """Soumission acceptée : elle devient un chantier « À planifier », à condition que tout ce qu'il faut soit rempli
    (CONDITIONS_ACCEPTATION). Retourne la liste des erreurs ; vide = acceptée. À appeler dans une transaction."""
    r = conn.execute("SELECT statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"fiche #{chantier_id} introuvable"]
    if r[0] not in STATUTS_SOUMISSION:
        return ["seule une soumission en cours peut être acceptée"]
    manques = manques_pour_accepter(conn, chantier_id)
    if manques:
        return ["il manque encore : " + ", ".join(libelles_manques(manques))]
    conn.execute("UPDATE chantiers SET statut = 'a_planifier', date_prevue = NULL, accepte_le = ? WHERE id = ?",
                 (datetime.date.today().isoformat(), chantier_id))
    ajuster_ordre(conn, chantier_id)
    return []


def refuser_soumission(conn, chantier_id):
    """Soumission refusée par le client : « Annulé » (sans date d'acceptation : elle reste dans les soumissions, section Refusées)."""
    r = conn.execute("SELECT statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"fiche #{chantier_id} introuvable"]
    if r[0] not in STATUTS_SOUMISSION:
        return ["seule une soumission en cours peut être refusée (un chantier se règle avec « Annuler »)"]
    return changer_statut(conn, chantier_id, "annule")


def remettre_en_soumission(conn, chantier_id):
    """Un chantier accepté par erreur (« À planifier » ou « En attente », pas encore placé dans une journée) redevient une soumission."""
    r = conn.execute("SELECT statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"fiche #{chantier_id} introuvable"]
    if r[0] not in ("a_planifier", "en_attente"):
        return ["seul un chantier « À planifier » ou « En attente » peut être remis en soumission (retire-le d'abord de sa journée)"]
    conn.execute("UPDATE chantiers SET statut = 'soumission', accepte_le = NULL, reprise_le = NULL, date_prevue = NULL WHERE id = ?", (chantier_id,))
    ajuster_ordre(conn, chantier_id)
    return []


def mettre_en_attente(conn, chantier_id, reprise=None):
    """Met de côté un chantier ACCEPTÉ : il n'est plus proposé dans la Journée. `reprise` (AAAA-MM-JJ, dans le futur) : le jour où il
    redevient « À planifier » tout seul ; vide : jusqu'à nouvel ordre. Valable pour :
      * un chantier « À planifier » (ou déjà « En attente » : on change alors la date) ;
      * une soumission COMPLÈTE (mêmes conditions que pour l'accepter) : le client a dit oui, mais pas tout de suite. Elle devient
        un chantier accepté aujourd'hui, en attente.
    Retourne la liste des erreurs ; vide = fait. À appeler dans une transaction."""
    r = conn.execute("SELECT statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"fiche #{chantier_id} introuvable"]
    jour = None
    if (reprise or "").strip():
        try:
            jour = datetime.date.fromisoformat(reprise.strip())
        except ValueError:
            return ["la date de reprise n'est pas valide (format AAAA-MM-JJ)"]
        if jour <= datetime.date.today():
            return ["la date de reprise doit être à venir : c'est le jour où le chantier redevient « À planifier » "
                    "(pour « jusqu'à nouvel ordre », ne choisis pas de date)"]
        jour = jour.isoformat()
    statut = r[0]
    if statut == "soumission":
        manques = manques_pour_accepter(conn, chantier_id)
        if manques:
            return ["pour mettre une soumission en attente, il faut qu'elle soit complète : il manque encore " + ", ".join(libelles_manques(manques))]
        conn.execute("UPDATE chantiers SET statut = 'en_attente', accepte_le = ?, reprise_le = ?, date_prevue = NULL WHERE id = ?",
                     (datetime.date.today().isoformat(), jour, chantier_id))
    elif statut in ("a_planifier", "en_attente"):
        conn.execute("UPDATE chantiers SET statut = 'en_attente', reprise_le = ?, date_prevue = NULL WHERE id = ?", (jour, chantier_id))
    elif statut == "planifie":
        return ["ce chantier est placé dans une journée : retire-le d'abord de sa journée (page Journée), puis mets-le en attente"]
    else:
        return ["seul un chantier « À planifier » ou une soumission complète peut être mis en attente"]
    ajuster_ordre(conn, chantier_id)
    return []


def sortir_de_l_attente(conn, chantier_id):
    """Un chantier « En attente » redevient « À planifier » tout de suite (son délai d'attente repart d'aujourd'hui)."""
    r = conn.execute("SELECT statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"fiche #{chantier_id} introuvable"]
    if r[0] != "en_attente":
        return ["ce chantier n'est pas en attente"]
    conn.execute("UPDATE chantiers SET statut = 'a_planifier', reprise_le = ? WHERE id = ?", (datetime.date.today().isoformat(), chantier_id))
    return []


def reprendre_les_attentes(conn, aujourdhui=None):
    """Les chantiers « En attente » dont la date de reprise est arrivée redeviennent « À planifier » (leur délai d'attente compte
    à partir de cette date). Appelée à chaque requête : une simple lecture tant qu'il n'y a rien à faire. Retourne le nombre repris."""
    jour = (aujourdhui or datetime.date.today()).isoformat()
    echus = "statut = 'en_attente' AND reprise_le IS NOT NULL AND reprise_le <= ?"
    if conn.execute(f"SELECT 1 FROM chantiers WHERE {echus} LIMIT 1", (jour,)).fetchone() is None:
        return 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        n = conn.execute(f"UPDATE chantiers SET statut = 'a_planifier' WHERE {echus}", (jour,)).rowcount
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
    return n


def terminer_chantier(conn, chantier_id, duree_reelle=None, paye=False, mode=None):
    """Passe un chantier « Planifié » à « Terminé », puis le verrouille. Le client est alors considéré comme facturé.

    La durée réelle reprend la durée estimée si elle n'est pas fournie. paye=True enregistre en plus l'encaissement du
    solde complet (aujourd'hui, avec le mode donné ou, à défaut, le mode de règlement prévu ou Interac) : le chantier
    est alors terminé ET payé, donc archivé. Tout ou rien (à appeler dans une transaction).
    """
    r = conn.execute("SELECT statut, modalite_paiement FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return [f"chantier #{chantier_id} introuvable"]
    if r[0] == "termine":
        return [VERROU]
    if r[0] != "planifie":
        return ["seul un chantier planifié (placé dans une journée) peut être terminé"]
    erreurs = changer_statut(conn, chantier_id, "termine", duree_reelle=duree_reelle)
    if erreurs or not paye:
        return erreurs
    solde = conn.execute("SELECT solde, prix_ht FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    if solde[1] is None:
        return ["le prix du chantier est manquant : saisis-le avant d'indiquer qu'il est payé"]
    if solde[0] > 0:
        return encaisser(conn, chantier_id, f"{solde[0]:.2f}", mode or r[1] or "interac")
    return []


# ---------------------------------------------------------------------------
# Secteurs desservis (liste fermée : jamais de ville écrite à la main)
# ---------------------------------------------------------------------------
def lister_secteurs(conn):
    """[(code, libellé, ville)] dans l'ordre d'affichage."""
    return conn.execute("SELECT code, libelle, ville FROM secteurs ORDER BY ordre, libelle COLLATE NOCASE").fetchall()


def appliquer_secteur(conn, brut, requis):
    """Résout `client_secteur` (code ou libellé, sans tenir compte des accents ni de la casse) dans une ligne brute.

    La ville de l'adresse est celle du secteur : elle remplace toute ville saisie (aucune variante d'écriture possible).
    Retourne la liste des erreurs ; requis=False (import CSV) accepte un secteur vide.
    """
    valeur = (brut.get("client_secteur") or "").strip()
    if not valeur:
        return ["client_secteur est obligatoire (choisis le secteur dans la liste)"] if requis else []
    for code, libelle, ville in lister_secteurs(conn):
        if cle(valeur) in (cle(code), cle(libelle)):
            brut["client_secteur"], brut["ville"] = code, ville
            return []
    return [f"client_secteur « {valeur} » inconnu (secteurs : {', '.join(l for _, l, _ in lister_secteurs(conn))})"]


def _code_secteur(libelle):
    return re.sub(r"\s+", "_", cle(libelle))


def ajouter_secteur(conn, libelle, ville=None):
    """Ajoute un secteur. Refuse un doublon (même nom à l'accent, au tiret ou à la casse près). Retourne (code, erreurs)."""
    libelle = re.sub(r"\s+", " ", (libelle or "").strip())
    ville = re.sub(r"\s+", " ", (ville or "").strip()) or libelle
    if not libelle:
        return None, ["donne un nom au secteur"]
    existants = lister_secteurs(conn)
    for code, lib, _ in existants:
        if cle(lib) == cle(libelle):
            return None, [f"le secteur « {lib} » existe déjà"]
    for _, _, vil in existants:           # une ville déjà connue garde son écriture officielle
        if cle(vil) == cle(ville):
            ville = vil
            break
    code = _code_secteur(libelle)
    if not code:
        return None, ["nom de secteur invalide"]
    base, n = code, 1
    codes = {c for c, _, _ in existants}
    while code in codes:
        n += 1
        code = f"{base}_{n}"
    ordre = (conn.execute("SELECT COALESCE(MAX(ordre), 0) FROM secteurs").fetchone()[0] // 10 + 1) * 10
    conn.execute("INSERT INTO secteurs (code, libelle, ville, ordre) VALUES (?,?,?,?)", (code, libelle, ville, ordre))
    return code, []


def renommer_secteur(conn, code, libelle):
    libelle = re.sub(r"\s+", " ", (libelle or "").strip())
    if not libelle:
        return ["donne un nom au secteur"]
    if not conn.execute("SELECT 1 FROM secteurs WHERE code = ?", (code,)).fetchone():
        return ["secteur introuvable"]
    for c, lib, _ in lister_secteurs(conn):
        if c != code and cle(lib) == cle(libelle):
            return [f"le secteur « {lib} » existe déjà"]
    conn.execute("UPDATE secteurs SET libelle = ? WHERE code = ?", (libelle, code))
    return []


def supprimer_secteur(conn, code):
    n = conn.execute("SELECT count(*) FROM clients WHERE secteur = ? AND fusionne_dans IS NULL", (code,)).fetchone()[0]
    if n:
        return [f"{n} client{'s' if n > 1 else ''} utilise{'nt' if n > 1 else ''} ce secteur : change d'abord leur secteur"]
    if conn.execute("SELECT 1 FROM clients WHERE secteur = ? AND fusionne_dans IS NOT NULL", (code,)).fetchone():
        return ["des fiches fusionnées (cachées, on ne les modifie plus) utilisent ce secteur : il ne peut pas être supprimé"]
    conn.execute("DELETE FROM secteurs WHERE code = ?", (code,))
    return []


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
    if (not conn.execute("SELECT 1 FROM chantiers WHERE client_id = ?", (r[0],)).fetchone()
            and not doublons_fusionnes(conn, r[0])):            # une fiche gardée par une fusion n'est jamais supprimée
        conn.execute("DELETE FROM clients WHERE id = ?", (r[0],))
    return []


def resume_suppression_client(conn, client_id):
    """Ce qui disparaîtrait avec le client : (fiches, dont chantiers terminés, paiements). Les fiches des doublons fusionnés dans ce
    client (leurs chantiers terminés sont restés sur eux) comptent aussi."""
    fiches = "client_id IN (SELECT id FROM clients WHERE id = ? OR fusionne_dans = ?)"
    n = conn.execute(f"SELECT count(*) FROM chantiers WHERE {fiches}", (client_id, client_id)).fetchone()[0]
    termines = conn.execute(f"SELECT count(*) FROM chantiers WHERE statut = 'termine' AND {fiches}", (client_id, client_id)).fetchone()[0]
    paiements = conn.execute(f"SELECT count(*) FROM paiements p JOIN chantiers c ON c.id = p.chantier_id WHERE c.{fiches}", (client_id, client_id)).fetchone()[0]
    return n, termines, paiements


MSG_CLIENT_HISTORIQUE = "Ce client a des chantiers terminés ou des paiements : il fait partie de ton historique et ne peut pas être supprimé."
MSG_CLIENT_FUSIONNE = "Cette fiche a été fusionnée dans une autre : elle fait partie de ton historique et ne peut pas être supprimée."
MSG_CLIENT_GARDE = "Une fiche en double a été fusionnée dans celle-ci : elle fait partie de ton historique et ne peut pas être supprimée."


def client_supprimable(conn, client_id):
    """Vrai si le client n'a aucun chantier terminé et aucun paiement (sur n'importe laquelle de ses fiches), n'est pas un doublon
    fusionné (fiche cachée) et n'a pas de doublon fusionné dedans."""
    r = conn.execute("SELECT fusionne_dans FROM clients WHERE id = ?", (client_id,)).fetchone()
    if (r is not None and r[0] is not None) or doublons_fusionnes(conn, client_id):
        return False
    _, termines, paiements = resume_suppression_client(conn, client_id)
    return termines == 0 and paiements == 0


def supprimer_client(conn, client_id):
    """Supprime un client et ses fiches (soumissions, chantiers annulés ou pas encore terminés, avec leurs types de
    travaux). Refusé s'il a un chantier terminé ou un paiement : c'est de l'historique d'argent. À appeler dans une
    transaction (tout ou rien). Les déclencheurs de protection de la base ne sont jamais touchés.
    """
    if conn.execute("SELECT 1 FROM clients WHERE id = ?", (client_id,)).fetchone() is None:
        return [f"client #{client_id} introuvable"]
    if fiche_gardee(conn, client_id) != client_id:
        return [MSG_CLIENT_FUSIONNE]
    if doublons_fusionnes(conn, client_id):
        return [MSG_CLIENT_GARDE]
    if not client_supprimable(conn, client_id):
        return [MSG_CLIENT_HISTORIQUE]
    ids = "SELECT id FROM chantiers WHERE client_id = ?"
    conn.execute(f"DELETE FROM chantier_travaux WHERE chantier_id IN ({ids})", (client_id,))
    conn.execute("DELETE FROM chantiers WHERE client_id = ?", (client_id,))
    conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    return []
