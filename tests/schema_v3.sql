-- =============================================================================
-- SylvainCulteur — noyau de données local (v1)
-- Base : SQLite (compatible SQLite >= 3.8.3, donc tous les outils courants)
--
-- Création :   sqlite3 data/sylvainculteur.db < schema/schema.sql
--          ou  python3 outils/importer_saisie.py ...   (crée la base si absente)
--
-- Modèle :  clients 1─N chantiers 1─N paiements
--                         └─N chantier_travaux (un ou plusieurs types de travaux, avec précision)
--   clients    = la personne / l'entreprise ET son adresse (géocodée UNE fois)
--   chantiers  = un travail pour un client (statut, date, durée, prix) :
--                un client qui revient = un nouveau chantier, jamais une nouvelle fiche
--   paiements  = chaque somme reçue (acompte, solde...)
--   Un client avec deux propriétés = deux fiches clients (une par adresse).
--
-- Conventions strictes (toutes vérifiées par la base elle-même) :
--   dates          AAAA-MM-JJ        heures        HH:MM (24 h)
--   durées         heures décimales  (2.5 = 2 h 30), temps écoulé sur place
--   argent         dollars CAD, 2 décimales max (450.00), jamais de symbole $
--   téléphone      +1XXXXXXXXXX (E.164)
--   code postal    A1A 1A1 (majuscules, une espace)
--   chemins        relatifs au dossier de la base (data/), "/" seulement,
--                  sans "/" au début ni à la fin, sans ".."
-- =============================================================================

-- À réactiver à CHAQUE connexion (SQLite ne le garde pas dans le fichier).
-- DB Browser le fait par défaut ; en Python : conn.execute("PRAGMA foreign_keys = ON").
PRAGMA foreign_keys = ON;

-- Numéro de version du schéma (sert aux migrations futures).
PRAGMA user_version = 3;


-- -----------------------------------------------------------------------------
-- Types de travaux : table de référence (on peut en ajouter avec un simple
-- INSERT, sans toucher au schéma).
-- -----------------------------------------------------------------------------
CREATE TABLE types_travaux (
    code    TEXT PRIMARY KEY
            CONSTRAINT ck_types_code CHECK (code NOT GLOB '*[^a-z_]*' AND code <> ''),
    libelle TEXT NOT NULL
);

INSERT INTO types_travaux (code, libelle) VALUES
    ('emondage',     'Émondage'),
    ('elagage',      'Élagage'),
    ('taille_haie',  'Taille de haie'),
    ('abattage',     'Abattage'),
    ('essouchement', 'Essouchement'),
    ('autre',        'Autre');


-- -----------------------------------------------------------------------------
-- Clients : une personne ou une entreprise, directement reliée à son adresse.
-- -----------------------------------------------------------------------------
CREATE TABLE clients (
    id          INTEGER PRIMARY KEY,
    prenom      TEXT,
    nom         TEXT,
    entreprise  TEXT,
    telephone   TEXT,
    telephone_2 TEXT,
    courriel    TEXT,
    sms_ok      INTEGER NOT NULL DEFAULT 1,   -- 1 = rappels par texto acceptés

    -- Adresse "à la Postes Canada" : numéro + type + nom de rue, ville officielle.
    -- Google Maps l'accepte telle quelle : voir adresse_maps dans v_chantiers.
    adresse        TEXT NOT NULL,             -- ex. 123 Rue des Érables
    ville          TEXT NOT NULL,             -- ex. Saint-Jérôme
    province       TEXT NOT NULL DEFAULT 'QC',
    code_postal    TEXT,                      -- ex. J7Z 1A1 (facultatif mais recommandé)

    -- Remplis plus tard par le script de géocodage (étape 2), ou à la main
    -- (clic droit dans Google Maps > copier les coordonnées) pour les lots
    -- sans numéro civique.
    latitude       REAL,
    longitude      REAL,
    geocode_statut TEXT NOT NULL DEFAULT 'a_faire',

    notes_acces TEXT,                         -- barrière, chien, où stationner, où est l'arbre
    notes       TEXT,                         -- préférences, historique utile
    cree_le     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),

    CONSTRAINT ck_clients_identite
        CHECK ((nom IS NOT NULL AND trim(nom) <> '') OR (entreprise IS NOT NULL AND trim(entreprise) <> '')),
    CONSTRAINT ck_clients_telephone
        CHECK (telephone IS NULL
               OR telephone GLOB '+1[2-9][0-9][0-9][2-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CONSTRAINT ck_clients_telephone_2
        CHECK (telephone_2 IS NULL
               OR telephone_2 GLOB '+1[2-9][0-9][0-9][2-9][0-9][0-9][0-9][0-9][0-9][0-9]'),
    CONSTRAINT ck_clients_courriel
        CHECK (courriel IS NULL OR (courriel LIKE '_%@_%._%' AND courriel NOT LIKE '% %')),
    CONSTRAINT ck_clients_sms_ok
        CHECK (typeof(sms_ok) = 'integer' AND sms_ok IN (0, 1)),
    CONSTRAINT ck_clients_adresse CHECK (trim(adresse) <> '' AND trim(ville) <> ''),
    CONSTRAINT ck_clients_province CHECK (province GLOB '[A-Z][A-Z]'),
    CONSTRAINT ck_clients_code_postal
        CHECK (code_postal IS NULL OR code_postal GLOB '[A-Z][0-9][A-Z] [0-9][A-Z][0-9]'),
    -- Boîte large Est du Canada / Nord-Est US : attrape surtout la longitude sans signe "-".
    CONSTRAINT ck_clients_latitude
        CHECK (latitude IS NULL OR (typeof(latitude) IN ('real','integer') AND latitude BETWEEN 40 AND 65)),
    CONSTRAINT ck_clients_longitude
        CHECK (longitude IS NULL OR (typeof(longitude) IN ('real','integer') AND longitude BETWEEN -90 AND -50)),
    CONSTRAINT ck_clients_geocode_statut
        CHECK (geocode_statut IN ('a_faire','ok','approximatif','echec','manuel')),
    -- Cohérence : coordonnées <=> statut qui en suppose.
    CONSTRAINT ck_clients_coordonnees
        CHECK ((latitude IS NULL) = (longitude IS NULL)
               AND (geocode_statut IN ('a_faire','echec')) = (latitude IS NULL))
);


-- -----------------------------------------------------------------------------
-- Chantiers : un travail pour un client (en moyenne ~2 h : plusieurs par journée).
-- Un travail de plusieurs jours = un chantier par journée (durée <= 24 h).
-- -----------------------------------------------------------------------------
CREATE TABLE chantiers (
    id              INTEGER PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,

    description     TEXT,     -- description générale (imprimée sur la feuille de route) ;
                              -- le détail par type de travaux est dans chantier_travaux

    -- soumission = estimé donné, réponse attendue     refuse  = client a dit non
    -- accepte    = accepté, pas encore de date         planifie = date fixée
    -- termine    = fait                                annule  = annulé après acceptation
    statut          TEXT NOT NULL DEFAULT 'soumission',

    date_soumission TEXT,     -- AAAA-MM-JJ
    date_prevue     TEXT,     -- AAAA-MM-JJ : UNE seule date des travaux. Prévue tant que non fait ;
                              -- si le chantier change de jour, on met simplement cette date à jour.
                              -- Obligatoire si statut = planifie ou termine.
    heure_prevue    TEXT,     -- HH:MM       (facultatif : rendez-vous fixe)

    duree_estimee_h REAL,     -- heures décimales, temps écoulé sur place
    duree_reelle_h  REAL,     -- idem, mesuré après coup (sert à améliorer les estimés)

    prix_ht         REAL,     -- $ CAD avant taxes (estimé tant que non facturé, puis final)
    tps             REAL NOT NULL DEFAULT 0,   -- $ TPS (0 si non inscrit aux taxes)
    tvq             REAL NOT NULL DEFAULT 0,   -- $ TVQ (0 si non inscrit aux taxes)
    modalite_paiement TEXT,   -- comment le client paiera (« Interac à la fin », « 50 % d'acompte »...) ;
                              -- imprimée sur la feuille de route pour savoir quoi encaisser sur place
    numero_facture  TEXT,
    date_facture    TEXT,     -- AAAA-MM-JJ : date de la facture / du reçu remis

    -- Chemins relatifs au dossier de la base (data/)
    dossier_photos  TEXT,     -- ex. photos/2026/2026-06-14_gagnon
    fichier_papier  TEXT,     -- ex. papier/2026/2026-06-14_gagnon.pdf (scan de la fiche)
    ref_papier      TEXT,     -- ex. "Classeur B, fiche 34" (retrouver l'original)

    cree_le         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),

    CONSTRAINT ck_chantiers_statut
        CHECK (statut IN ('soumission','refuse','accepte','planifie','termine','annule')),

    -- Dates : `date(x, '+0 days') IS x` rejette 2026-02-30, 2026-13-01, 14/06/2026, "2026-06-14 10:00".
    CONSTRAINT ck_chantiers_date_soumission CHECK (date_soumission IS NULL OR date(date_soumission, '+0 days') IS date_soumission),
    CONSTRAINT ck_chantiers_date_prevue     CHECK (date_prevue     IS NULL OR date(date_prevue, '+0 days')     IS date_prevue),
    CONSTRAINT ck_chantiers_date_facture    CHECK (date_facture    IS NULL OR date(date_facture, '+0 days')    IS date_facture),
    CONSTRAINT ck_chantiers_heure_prevue
        CHECK (heure_prevue IS NULL OR (time(heure_prevue) IS heure_prevue || ':00' AND heure_prevue < '24:00')),

    CONSTRAINT ck_chantiers_duree_estimee
        CHECK (duree_estimee_h IS NULL OR (typeof(duree_estimee_h) IN ('real','integer')
               AND duree_estimee_h > 0 AND duree_estimee_h <= 24)),
    CONSTRAINT ck_chantiers_duree_reelle
        CHECK (duree_reelle_h IS NULL OR (typeof(duree_reelle_h) IN ('real','integer')
               AND duree_reelle_h > 0 AND duree_reelle_h <= 24)),

    CONSTRAINT ck_chantiers_prix_ht
        CHECK (prix_ht IS NULL OR (typeof(prix_ht) IN ('real','integer') AND prix_ht >= 0 AND prix_ht = ROUND(prix_ht, 2))),
    CONSTRAINT ck_chantiers_tps
        CHECK (typeof(tps) IN ('real','integer') AND tps >= 0 AND tps = ROUND(tps, 2)),
    CONSTRAINT ck_chantiers_tvq
        CHECK (typeof(tvq) IN ('real','integer') AND tvq >= 0 AND tvq = ROUND(tvq, 2)),

    -- Cohérence statut ⇔ dates / prix
    CONSTRAINT ck_chantiers_planifie_a_une_date
        CHECK (statut <> 'planifie' OR date_prevue IS NOT NULL),
    CONSTRAINT ck_chantiers_termine_a_une_date
        CHECK (statut <> 'termine' OR date_prevue IS NOT NULL),
    CONSTRAINT ck_chantiers_facture_a_un_prix
        CHECK (date_facture IS NULL OR prix_ht IS NOT NULL),
    CONSTRAINT ck_chantiers_numero_facture
        CHECK (numero_facture IS NULL OR date_facture IS NOT NULL),

    -- Chemins relatifs stricts : pas de "/" initial ou final, pas de "\", pas de "..", pas de "C:".
    CONSTRAINT ck_chantiers_dossier_photos
        CHECK (dossier_photos IS NULL OR (trim(dossier_photos) <> ''
               AND dossier_photos NOT GLOB '/*' AND dossier_photos NOT GLOB '*/'
               AND dossier_photos NOT GLOB '*\*' AND dossier_photos NOT GLOB '*..*'
               AND dossier_photos NOT GLOB '[A-Za-z]:*')),
    CONSTRAINT ck_chantiers_fichier_papier
        CHECK (fichier_papier IS NULL OR (trim(fichier_papier) <> ''
               AND fichier_papier NOT GLOB '/*' AND fichier_papier NOT GLOB '*/'
               AND fichier_papier NOT GLOB '*\*' AND fichier_papier NOT GLOB '*..*'
               AND fichier_papier NOT GLOB '[A-Za-z]:*'))
);

-- -----------------------------------------------------------------------------
-- Travaux d'un chantier : un chantier peut combiner plusieurs types (élagage +
-- taille de haie...), chacun avec sa précision (« érable argenté côté garage »).
-- -----------------------------------------------------------------------------
CREATE TABLE chantier_travaux (
    chantier_id  INTEGER NOT NULL REFERENCES chantiers(id) ON DELETE CASCADE,
    type_travaux TEXT NOT NULL REFERENCES types_travaux(code),
    precision    TEXT,
    PRIMARY KEY (chantier_id, type_travaux)
);

CREATE INDEX idx_chantiers_client     ON chantiers(client_id);
CREATE INDEX idx_chantiers_date_prevue ON chantiers(date_prevue);   -- requête de la journée
CREATE INDEX idx_chantiers_statut     ON chantiers(statut);


-- -----------------------------------------------------------------------------
-- Paiements : une ligne par somme reçue (acompte, solde...). Le statut de
-- paiement d'un chantier est CALCULÉ à partir d'ici (voir v_chantiers), jamais
-- saisi : il ne peut donc pas se contredire avec les montants.
-- -----------------------------------------------------------------------------
CREATE TABLE paiements (
    id            INTEGER PRIMARY KEY,
    chantier_id   INTEGER NOT NULL REFERENCES chantiers(id) ON DELETE RESTRICT,
    date_paiement TEXT NOT NULL,              -- AAAA-MM-JJ
    montant       REAL NOT NULL,              -- $ CAD, taxes incluses
    mode          TEXT NOT NULL,
    reference     TEXT,                       -- n° de chèque, référence Interac...
    notes         TEXT,
    cree_le       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),

    CONSTRAINT ck_paiements_date    CHECK (date(date_paiement, '+0 days') IS date_paiement),
    CONSTRAINT ck_paiements_montant CHECK (typeof(montant) IN ('real','integer') AND montant > 0 AND montant = ROUND(montant, 2)),
    CONSTRAINT ck_paiements_mode    CHECK (mode IN ('comptant','cheque','interac','carte','autre'))
);

CREATE INDEX idx_paiements_chantier ON paiements(chantier_id);


-- -----------------------------------------------------------------------------
-- Vue de lecture pour les scripts Python (itinéraire, feuille de route,
-- finances) : tout est déjà joint et calculé.
--
-- statut_paiement :
--   prix_manquant  travaux faits mais prix_ht vide (fiche à compléter)
--   paye           somme reçue >= total
--   partiel        une partie reçue (acompte...), solde > 0
--   sans_objet     soumission / refusé / annulé, ou travail gratuit
--   non_facture    travaux faits, aucune facture émise   ← à facturer
--   a_payer        facture émise, rien reçu              ← à relancer
--   a_venir        accepté / planifié, pas encore fait
-- -----------------------------------------------------------------------------
CREATE VIEW v_chantiers AS
WITH recu AS (
    SELECT chantier_id, ROUND(SUM(montant), 2) AS paye
    FROM paiements
    GROUP BY chantier_id
),
base AS (
    SELECT
        c.id AS chantier_id,
        c.statut,
        (SELECT group_concat(code, '+') FROM (SELECT ct.type_travaux AS code FROM chantier_travaux ct
            WHERE ct.chantier_id = c.id ORDER BY ct.type_travaux)) AS types_codes,
        (SELECT group_concat(libelle, ' + ') FROM (SELECT t.libelle FROM chantier_travaux ct
            JOIN types_travaux t ON t.code = ct.type_travaux
            WHERE ct.chantier_id = c.id ORDER BY ct.type_travaux)) AS type_libelle,
        (SELECT group_concat(detail, ' ; ') FROM (SELECT t.libelle || COALESCE(' : ' || ct.precision, '') AS detail
            FROM chantier_travaux ct JOIN types_travaux t ON t.code = ct.type_travaux
            WHERE ct.chantier_id = c.id ORDER BY ct.type_travaux)) AS travaux_detail,
        c.description,
        c.date_soumission, c.date_prevue, c.heure_prevue,
        -- Depuis quand le client attend : date de la demande/soumission, à défaut date de création de la fiche
        COALESCE(c.date_soumission, date(c.cree_le)) AS attente_depuis,
        c.duree_estimee_h, c.duree_reelle_h,

        cl.id AS client_id, cl.prenom, cl.nom, cl.entreprise,
        COALESCE(NULLIF(trim(COALESCE(cl.prenom, '') || ' ' || COALESCE(cl.nom, '')), ''), cl.entreprise) AS client_nom_complet,
        cl.telephone, cl.telephone_2, cl.courriel, cl.sms_ok,
        cl.adresse, cl.ville, cl.province, cl.code_postal,
        cl.adresse || ', ' || cl.ville || ', ' || cl.province
            || COALESCE(' ' || cl.code_postal, '') || ', Canada' AS adresse_maps,
        cl.latitude, cl.longitude, cl.geocode_statut, cl.notes_acces,

        c.prix_ht, c.tps, c.tvq,
        ROUND(COALESCE(c.prix_ht, 0) + c.tps + c.tvq, 2) AS total_ttc,
        COALESCE(r.paye, 0) AS paye,
        c.modalite_paiement, c.numero_facture, c.date_facture,

        c.dossier_photos, c.fichier_papier, c.ref_papier
    FROM chantiers c
    JOIN clients cl       ON cl.id = c.client_id
    LEFT JOIN recu r      ON r.chantier_id = c.id
),
calcul AS (
    SELECT base.*, ROUND(total_ttc - paye, 2) AS solde FROM base
)
SELECT
    calcul.*,
    CASE
        WHEN statut = 'termine' AND prix_ht IS NULL        THEN 'prix_manquant'
        WHEN paye > 0 AND solde <= 0                        THEN 'paye'
        WHEN paye > 0                                       THEN 'partiel'
        WHEN statut IN ('soumission', 'refuse', 'annule')   THEN 'sans_objet'
        WHEN statut = 'termine' AND total_ttc = 0           THEN 'sans_objet'
        WHEN statut = 'termine' AND date_facture IS NULL    THEN 'non_facture'
        WHEN date_facture IS NOT NULL                       THEN 'a_payer'
        ELSE 'a_venir'
    END AS statut_paiement
FROM calcul;
