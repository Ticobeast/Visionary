-- Migration du format v8 vers v9 : ajoute les comptes et les sessions (aucune donnée existante n'est touchée).
-- Appliquée automatiquement à l'ouverture de la base. Doit rester identique aux définitions de schema.sql
-- (un test le vérifie).

-- -----------------------------------------------------------------------------
-- Comptes de l'équipe : nom + mot de passe (jamais en clair : seulement une empreinte PBKDF2 salée).
--   admin       = tout (journée, finances, suppressions, comptes)
--   soumission  = clients et chantiers : liste, consultation, création et modification des soumissions
-- Les sessions (connexions ouvertes sur un téléphone) ne gardent que l'empreinte du jeton, pas le jeton.
-- Tant qu'aucun compte n'existe, l'interface reste ouverte sur cet ordinateur (comme avant) ; dès qu'il y en a un,
-- la connexion est exigée partout. Gérer les comptes : python gerer_utilisateurs.py
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS utilisateurs (
    id           INTEGER PRIMARY KEY,
    nom          TEXT NOT NULL UNIQUE COLLATE NOCASE
                 CONSTRAINT ck_utilisateurs_nom CHECK (trim(nom) <> ''),
    role         TEXT NOT NULL DEFAULT 'soumission'
                 CONSTRAINT ck_utilisateurs_role CHECK (role IN ('admin', 'soumission')),
    mot_de_passe TEXT NOT NULL,
    actif        INTEGER NOT NULL DEFAULT 1
                 CONSTRAINT ck_utilisateurs_actif CHECK (typeof(actif) = 'integer' AND actif IN (0, 1)),
    cree_le      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS sessions (
    jeton_hash     TEXT PRIMARY KEY,
    utilisateur_id INTEGER NOT NULL REFERENCES utilisateurs(id) ON DELETE CASCADE,
    expire_le      TEXT NOT NULL,
    cree_le        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_utilisateur ON sessions(utilisateur_id);

PRAGMA user_version = 9;
