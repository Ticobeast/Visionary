-- Migration du format v9 vers v10 : définitions FIGÉES des tables que cette étape crée (copie de schema.sql au format v10).
-- Elles ne doivent plus changer : schema.sql évolue (v11, v12...), pas ce fichier. Le programme les exécute une à une,
-- à l'intérieur de sa propre transaction (voir noyau._etapes_9_10).
--   * clients : nom, adresse et ville ne sont plus obligatoires (une soumission s'ouvre avec ce qu'on sait) ;
--   * raccourcis : les pastilles en haut des pages Chantiers et Soumissions.

CREATE TABLE clients_nouveau (
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
    adresse        TEXT NOT NULL DEFAULT '',  -- ex. 123 Rue des Érables ; vide tant qu'on ne la connaît pas (soumission)
    ville          TEXT NOT NULL DEFAULT '',  -- ex. Trois-Rivières (déduite du secteur choisi dans l'interface)
    secteur        TEXT REFERENCES secteurs(code) ON UPDATE CASCADE ON DELETE RESTRICT,
                                              -- secteur desservi (liste fermée) ; vide pour d'anciens clients
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
    CONSTRAINT ck_clients_adresse CHECK (typeof(adresse) = 'text' AND typeof(ville) = 'text'),
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

CREATE TABLE raccourcis (
    id             INTEGER PRIMARY KEY,
    utilisateur_id INTEGER REFERENCES utilisateurs(id) ON DELETE CASCADE,
    page           TEXT NOT NULL CONSTRAINT ck_raccourcis_page CHECK (page IN ('chantiers', 'soumissions')),
    libelle        TEXT NOT NULL CONSTRAINT ck_raccourcis_libelle CHECK (trim(libelle) <> ''),
    filtre         TEXT NOT NULL DEFAULT '',
    ordre          INTEGER NOT NULL DEFAULT 100
);

CREATE INDEX idx_raccourcis_utilisateur ON raccourcis(utilisateur_id, page);
