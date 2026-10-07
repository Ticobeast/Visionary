# SylvainCulteur — noyau de données et interface locale (étape 1)

Base de données **locale, privée et sans abonnement** pour les dossiers clients et les chantiers
d'émondage, d'élagage et de taille de haies. Cette étape pose le noyau de données et l'outil de saisie ; les
itinéraires, les feuilles de route PDF, l'iPad, les finances et les textos viendront ensuite sur cette base,
sans retranscription.

## Le choix : SQLite + une interface de saisie locale

- **SQLite = la source de vérité.** Un seul fichier (`data/sylvainculteur.db`), aucun serveur, aucun abonnement.
  Python le lit sans rien installer (`import sqlite3`). Le PDF de la journée est lui aussi fabriqué sans rien installer ;
  Pillow (`pip install pillow`) est **facultatif** : il sert seulement à réduire les grosses photos dans ce PDF.
- **La base refuse les données invalides à la saisie** (dates, téléphones, montants, statuts incohérents) : un
  tableur, lui, réécrit silencieusement les dates et les décimales.
- **Tout se fait dans une interface locale** (`outils/interface.py`) qui s'ouvre dans le navigateur : un **calendrier**
  des journées planifiées (en lecture seule), une page **Journée** pour créer et gérer une journée complète (heures de passage calculées, ordre modifiable), la liste des **chantiers** (actifs, puis archives), les fiches clients, la saisie avec validation immédiate. L'interface est simple par défaut : les options rarement utilisées sont dans « Paramètres avancés ». Elle écoute
  uniquement sur l'ordinateur (`127.0.0.1`) : rien n'est exposé sur le réseau.

**Sur téléphone et iPad (équipe sur le terrain).** `lancer_reseau.bat` ouvre l'interface aux appareils de ton réseau privé Tailscale
(gratuit, chiffré, rien d'ouvert sur Internet) : voir **docs/acces_a_distance.md**. Connexion par nom et mot de passe (`gerer_utilisateurs.bat`), droits « administrateur » et « soumission », affichage simplifié sur téléphone (Chantiers, Clients, + Chantier).

## Modèle

```
clients (personne ou entreprise + son adresse)  1 ─── N  chantiers  1 ─── N  paiements
                                                              └── N  types de travaux (avec précision)
```

Un client = une personne **et** son adresse. Un client qui revient = un nouveau chantier sur sa fiche. Un
chantier dure en moyenne 2 h : plusieurs par journée ; il peut combiner plusieurs types de travaux, et il n'a
qu'**une seule date** de travaux (prévue, puis réalisée ; elle se change dans la page Journée). Détails : [`docs/dictionnaire_donnees.md`](docs/dictionnaire_donnees.md).

Règles appliquées par l'application **et** par la base : le client ne se modifie que depuis sa fiche ; un chantier **Terminé** est
verrouillé en lecture seule (on peut seulement l'encaisser et le dupliquer ; **le client est alors considéré comme facturé** : il n'y a pas de système de facture) ; **jamais de solde négatif** ; un seul mode
de règlement parmi cinq ; durée estimée obligatoire ; le statut est **automatique** (Journée = Planifié, Retirer = À planifier, Annuler = archivé, Terminer = Terminé avec « payé ou pas ») ; un
chantier annulé, ou terminé **et payé**, passe seul dans les *Archives* ; la ville d'un client se choisit dans une **liste de secteurs** (pas de doublons
d'écriture) ; nacelle et sort du bois sont des options du travail.

## Contenu

```
schema/schema.sql                       schéma SQLite prêt à exécuter (tables, règles, vue v_chantiers)
outils/interface.py                     serveur local + saisie complète (nouveau client, modification d'un chantier)
outils/calendrier.py                    accueil : calendrier du mois + déroulement de la journée choisie (lecture seule)
outils/tableau.py                       page Journée (créer / gérer une journée) et actions rapides (terminer, retirer, annuler, ordre)
outils/composants.py                    cellules (client, adresse, travaux, montant) partagées, bouton Terminer et sa fenêtre de confirmation
outils/pages_clients.py                 liste des clients, fiche client, secteurs desservis, formulaire simplifié de nouveau chantier
outils/pages_chantier.py                page d'un chantier (client en lecture seule, verrou « Terminé », paiements, duplication)
outils/vue.py                           composants d'affichage partagés
outils/noyau.py                         règles de validation et d'écriture partagées
outils/donnees_test.py                  crée une base d'ESSAI avec de fausses données
lancer_interface.bat / .command         double-clic : ouvre l'interface sur la VRAIE base (Windows / Mac)
lancer_essai.bat / .command / .py       double-clic (ou bouton « Exécuter » de VS Code) : base d'ESSAI (fausses données)
lancer_interface.py                     idem, sur la VRAIE base
docs/tableau_de_bord.md                 guide : tableau de bord, journée, chantiers et archives, fiche client
docs/dictionnaire_donnees.md            toutes les colonnes : type, format, règle, exemple
docs/plan_de_tests.md                   plan de mise en route et de tests, phase par phase
tests/                                  tests automatiques (schéma, règles, interface, données d'essai)
data/                                   TES données (exclu de Git) : base, sauvegardes/, photos/
```

## Démarrage rapide

```bash
python3 -m unittest discover -s tests                  # vérifier l'installation : doit finir par OK
python3 outils/interface.py --essai                    # base d'ESSAI (fausses données) : data/test.db
python3 outils/interface.py                            # la VRAIE base (créée au premier lancement)
```

**Bouton « Exécuter » de VS Code** : ouvre `lancer_essai.py` (essai) ou `lancer_interface.py` (vraie base) ; ne lance pas
`interface.py` directement, il ouvrirait toujours la vraie base. Les chemins contenant des espaces doivent être entre guillemets.

Le coin supérieur droit de l'interface indique toujours la base ouverte : **« BASE D’ESSAI »** en orange pour
les fausses données, « Base : sylvainculteur.db » pour la vraie.

**Mises à jour du programme.** Tant qu'il n'y a pas de vraies données, il n'y a aucun outil de conversion : si une nouvelle version change le format de la base, le programme le dit et il suffit de supprimer le fichier de base (`data/sylvainculteur.db`, ou `data/test.db`, qui est recréée toute seule par `--essai`). Dès que tes vraies données existeront, un changement de format devra être accompagné d’un outil de migration (l’ancien est dans l’historique Git).

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
courriels `@example.com`). Une sauvegarde de la base est faite chaque jour au démarrage de l'interface (`data/sauvegardes/`).

## Prérequis

Python 3.9 ou plus récent (testé avec 3.11 ; la suite de tests a aussi été exécutée par l'utilisateur sous Windows
avec Python 3.9.13 ; l'interface est couverte par des tests automatiques). Bibliothèque standard seulement : rien à installer. La suite de tests passe avec SQLite 3.40, 3.43
et 3.46. Le schéma évite volontairement `STRICT`, les colonnes générées et les autres nouveautés récentes de
SQLite, pour qu'un outil plus ancien (DB Browser…) puisse ouvrir le fichier. Les lanceurs `.bat` et `.command`
n'ont pas été testés sur Mac ; sous Windows, ils n'ont pas été confirmés.
