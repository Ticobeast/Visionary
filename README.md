# SylvainCulteur — noyau de données (étape 1)

Base de données **locale, privée et sans abonnement** pour les dossiers clients et les chantiers
d'émondage, d'élagage et de taille de haies. Cette étape pose le noyau de données et l'outil de saisie ; les
itinéraires, les feuilles de route PDF, l'iPad, les finances et les textos viendront ensuite sur cette base,
sans retranscription.

## Le choix : SQLite + une interface de saisie locale

- **SQLite = la source de vérité.** Un seul fichier (`data/sylvainculteur.db`), aucun serveur, aucun abonnement.
  Python le lit sans rien installer (`import sqlite3`).
- **La base refuse les données invalides à la saisie** (dates, téléphones, montants, statuts incohérents) : un
  tableur, lui, réécrit silencieusement les dates et les décimales.
- **La saisie se fait dans une interface locale** (`outils/interface.py`) qui s'ouvre dans le navigateur :
  sélecteurs de date, listes déroulantes, recherche d'un client existant, validation immédiate. Elle écoute
  uniquement sur l'ordinateur (`127.0.0.1`) : rien n'est exposé sur le réseau.
- Un **import CSV** reste disponible pour saisir en rafale dans un tableur (de préférence LibreOffice Calc).

## Modèle

```
clients (personne ou entreprise + son adresse)  1 ─── N  chantiers  1 ─── N  paiements
```

Un client = une personne **et** son adresse. Un client qui revient = un nouveau chantier sur sa fiche. Un
chantier dure en moyenne 2 h : plusieurs par journée. Détails : [`docs/dictionnaire_donnees.md`](docs/dictionnaire_donnees.md).

## Contenu

```
schema/schema.sql                       schéma SQLite prêt à exécuter (tables, règles, vue v_chantiers)
outils/interface.py                     interface de saisie dans le navigateur
outils/importer_saisie.py               import d'une feuille CSV (validation, tout ou rien, sauvegarde)
outils/noyau.py                         règles de validation et d'écriture partagées par les deux
outils/donnees_test.py                  crée une base d'ESSAI avec de fausses données
modeles/saisie_papier_*.csv             feuille de saisie CSV : vide + 3 exemples fictifs
lancer_interface.bat / .command         double-clic pour ouvrir l'interface (Windows / Mac)
docs/dictionnaire_donnees.md            toutes les colonnes : type, format, règle, exemple
docs/transition_papier.md               méthode pour numériser les dossiers papier
docs/plan_de_tests.md                   plan de mise en route et de tests, phase par phase
tests/                                  tests automatiques (schéma, import, interface, données d'essai)
data/                                   TES données (exclu de Git) : base, photos/, papier/, saisie/
```

## Démarrage rapide

```bash
python3 -m unittest discover -s tests                  # vérifier l'installation : doit finir par OK
python3 outils/donnees_test.py                         # base d'essai fictive : data/test.db
python3 outils/interface.py --db data/test.db          # l'essayer (s'ouvre dans le navigateur)

python3 outils/interface.py                            # la vraie base (créée au premier lancement)
```

Pas à pas : [`docs/plan_de_tests.md`](docs/plan_de_tests.md). Sous Windows, remplacer `python3` par `python`
ou `py`. Outil graphique gratuit pour consulter la base : [DB Browser for SQLite](https://sqlitebrowser.org/).

Les chemins de photos et de scans sont **relatifs au dossier `data/`** : si tu déplaces `data/` (disque,
autre ordinateur), tout reste valide.

## Confidentialité

`data/` et tous les fichiers `*.db` sont dans le `.gitignore` : les vraies données de tes clients ne doivent
jamais être envoyées sur GitHub. Le dépôt ne contient que des exemples fictifs (téléphones en `555-01xx`,
courriels `@example.com`). Une sauvegarde de la base est faite chaque jour au démarrage de l'interface, et
avant chaque import CSV (`data/sauvegardes/`).

## Prérequis

Python 3 (testé avec 3.11, bibliothèque standard seulement : rien à installer). Testé avec SQLite 3.45. Le
schéma évite volontairement `STRICT`, les colonnes générées et les autres nouveautés récentes de SQLite, pour
qu'un outil plus ancien (DB Browser…) puisse ouvrir le fichier ; ce point n'a pas été testé sur d'anciennes
versions. Les lanceurs `.bat` et `.command` n'ont pas été testés sur Windows ni sur Mac.
