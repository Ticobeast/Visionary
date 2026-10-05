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
- **Tout se fait dans une interface locale** (`outils/interface.py`) qui s'ouvre dans le navigateur : un **calendrier**
  des journées planifiées (en lecture seule), une page **Journée** pour créer et gérer une journée complète (heures de passage calculées, ordre modifiable), la liste des **chantiers** (actifs, puis archives), les fiches clients, la saisie avec validation immédiate. L'interface est simple par défaut : les options rarement utilisées sont dans « Paramètres avancés ». Elle écoute
  uniquement sur l'ordinateur (`127.0.0.1`) : rien n'est exposé sur le réseau.
- Un **import CSV** reste disponible pour saisir en rafale dans un tableur (de préférence LibreOffice Calc).

## Modèle

```
clients (personne ou entreprise + son adresse)  1 ─── N  chantiers  1 ─── N  paiements
                                                              └── N  types de travaux (avec précision)
```

Un client = une personne **et** son adresse. Un client qui revient = un nouveau chantier sur sa fiche. Un
chantier dure en moyenne 2 h : plusieurs par journée ; il peut combiner plusieurs types de travaux, et il n'a
qu'**une seule date** (prévue, puis réalisée : si le chantier est déplacé, on la modifie). Détails : [`docs/dictionnaire_donnees.md`](docs/dictionnaire_donnees.md).

Règles appliquées par l'application **et** par la base : le client ne se modifie que depuis sa fiche ; un chantier **Terminé** est
verrouillé en lecture seule (on peut seulement le facturer, l'encaisser et le dupliquer) ; **jamais de solde négatif** ; un seul mode
de règlement parmi cinq ; durée estimée obligatoire ; un chantier terminé **et payé** passe seul dans les *Archives*.

## Contenu

```
schema/schema.sql                       schéma SQLite prêt à exécuter (tables, règles, vue v_chantiers)
outils/interface.py                     serveur local + saisie complète (nouveau client, modification d'un chantier)
outils/calendrier.py                    accueil : calendrier du mois + déroulement de la journée choisie (lecture seule)
outils/tableau.py                       page Journée (créer / gérer une journée) et actions rapides (statut, ordre, encaissement)
outils/composants.py                    cellules (client, adresse, travaux, montant, paiement) et formulaires rapides partagés, fenêtre « Terminé ? »
outils/pages_clients.py                 liste des clients, fiche client, formulaire simplifié de nouveau chantier
outils/pages_chantier.py                page d'un chantier (client en lecture seule, verrou « Terminé », paiements, duplication)
outils/vue.py                           composants d'affichage partagés
outils/importer_saisie.py               import d'une feuille CSV (validation, tout ou rien, sauvegarde)
outils/noyau.py                         règles de validation et d'écriture partagées par les deux
outils/donnees_test.py                  crée une base d'ESSAI avec de fausses données
outils/migrer.py                        convertit une base de l'ancien format (v1 à v4) sans rien perdre
modeles/saisie_papier_*.csv             feuille de saisie CSV : vide + 3 exemples fictifs
lancer_interface.bat / .command         double-clic : ouvre l'interface sur la VRAIE base (Windows / Mac)
lancer_essai.bat / .command / .py       double-clic (ou bouton « Exécuter » de VS Code) : base d'ESSAI (fausses données)
lancer_interface.py                     idem, sur la VRAIE base
docs/tableau_de_bord.md                 guide : tableau de bord, journée, chantiers et archives, fiche client
docs/dictionnaire_donnees.md            toutes les colonnes : type, format, règle, exemple
docs/transition_papier.md               méthode pour numériser les dossiers papier
docs/plan_de_tests.md                   plan de mise en route et de tests, phase par phase
tests/                                  tests automatiques (schéma, import, interface, données d'essai)
data/                                   TES données (exclu de Git) : base, photos/, papier/, saisie/
```

## Démarrage rapide

```bash
python3 -m unittest discover -s tests                  # vérifier l'installation : doit finir par OK
python3 outils/interface.py --essai                    # base d'ESSAI (fausses données) : data/test.db
python3 outils/interface.py                            # la VRAIE base (créée au premier lancement)
python3 outils/migrer.py data/sylvainculteur.db        # seulement si une base créée avant une mise à jour refuse de s'ouvrir (v1 à v4 -> v5)
```

**Bouton « Exécuter » de VS Code** : ouvre `lancer_essai.py` (essai) ou `lancer_interface.py` (vraie base) ; ne lance pas
`interface.py` directement, il ouvrirait toujours la vraie base. Les chemins contenant des espaces doivent être entre guillemets.

Le coin supérieur droit de l'interface indique toujours la base ouverte : **« BASE D’ESSAI »** en orange pour
les fausses données, « Base : sylvainculteur.db » pour la vraie.

Pas à pas : [`docs/plan_de_tests.md`](docs/plan_de_tests.md). Sous Windows, remplacer `python3` par `python`
ou `py`. Outil graphique gratuit pour consulter la base : [DB Browser for SQLite](https://sqlitebrowser.org/).

Les chemins de photos et de scans sont **relatifs au dossier `data/`** : si tu déplaces `data/` (disque,
autre ordinateur), tout reste valide.

## Confidentialité

**Ne place pas le projet dans un dossier synchronisé (OneDrive, Dropbox, iCloud, Google Drive)** : les données de tes
clients seraient copiées sur des serveurs externes, et SQLite peut y avoir des problèmes. Mets le dossier du projet
ailleurs, par exemple `C:\SylvainCulteur`. L'interface affiche un avertissement au démarrage si elle détecte ce cas.

`data/` et tous les fichiers `*.db` sont dans le `.gitignore` : les vraies données de tes clients ne doivent
jamais être envoyées sur GitHub. Le dépôt ne contient que des exemples fictifs (téléphones en `555-01xx`,
courriels `@example.com`). Une sauvegarde de la base est faite chaque jour au démarrage de l'interface, et
avant chaque import CSV (`data/sauvegardes/`).

## Prérequis

Python 3.9 ou plus récent (testé avec 3.11 ; la suite de tests a aussi été exécutée par l'utilisateur sous Windows
avec Python 3.9.13 ; l'interface est couverte par des tests automatiques). Bibliothèque standard seulement : rien à installer. La suite de tests passe avec SQLite 3.40, 3.43,
3.45 et 3.51. Le schéma évite volontairement `STRICT`, les colonnes générées et les autres nouveautés récentes de
SQLite, pour qu'un outil plus ancien (DB Browser…) puisse ouvrir le fichier. Les lanceurs `.bat` et `.command`
n'ont pas été testés sur Mac ; sous Windows, ils n'ont pas été confirmés.
