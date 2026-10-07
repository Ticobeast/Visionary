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
  des journées planifiées (en lecture seule), une page **Journée** pour créer et gérer une journée complète (heures de passage calculées, ordre modifiable), la liste des **chantiers** (actifs, puis archives), l'onglet **Soumissions** (boutons Accepter / En attente / Refuser), des **raccourcis** à ton goût en haut des listes, les fiches clients, l'onglet **Archives** (tout l'historique, recherches, statistiques, export Excel), la saisie avec validation immédiate. L'interface est simple par défaut : les options rarement utilisées sont dans « Paramètres avancés ». Elle écoute
  uniquement sur l'ordinateur (`127.0.0.1`) : rien n'est exposé sur le réseau.

**Sur téléphone et iPad (équipe sur le terrain).** `lancer_reseau.bat` ouvre l'interface aux appareils de ton réseau privé Tailscale
(gratuit, chiffré, rien d'ouvert sur Internet) : voir **docs/acces_a_distance.md**. Connexion par nom et mot de passe (`gerer_utilisateurs.bat`), droits « administrateur » et « soumission », affichage simplifié sur téléphone (Chantiers, Soumissions, Clients, + Soumission).

## Modèle

```
clients (personne ou entreprise + son adresse)  1 ─── N  chantiers  1 ─── N  paiements
                                                              └── N  types de travaux (avec précision)
```

Un client = une personne **et** son adresse. Un client qui revient = une nouvelle soumission sur son dossier. **Une soumission est un chantier pas encore
accepté** (même fiche, autre nom) : on l'ouvre dès que le client appelle, **sans rien d'obligatoire** ; le bouton **Accepter** la place dans les chantiers
(« À planifier ») seulement si tout ce qu'il faut est rempli (nom, téléphone, adresse, secteur, travaux, durée, prix : sinon le programme demande ce qui
manque), **En attente** la met de côté (le client accepte, mais pas tout de suite : à une date de reprise, ou à nouvel ordre), **Refuser** la range dans les soumissions refusées. Un
chantier dure en moyenne 2 h : plusieurs par journée ; il peut combiner plusieurs types de travaux, et il n'a
qu'**une seule date** de travaux (prévue, puis réalisée ; elle se change dans la page Journée). Détails : [`docs/dictionnaire_donnees.md`](docs/dictionnaire_donnees.md).

Règles appliquées par l'application **et** par la base : le client ne se modifie que depuis sa fiche ; un chantier **Terminé** est
verrouillé en lecture seule (on peut seulement l'encaisser et le dupliquer ; **le client est alors considéré comme facturé** : il n'y a pas de système de facture) ; **jamais de solde négatif** ; un seul mode
de règlement parmi cinq ; durée estimée obligatoire pour accepter une soumission ; le statut est **automatique** (Accepter = À planifier, Refuser = Refusée, Journée = Planifié, Retirer = À planifier, Annuler = archivé, Terminer = Terminé avec « payé ou pas ») ; un
chantier annulé, ou terminé **et payé**, passe seul dans les *Archives* ; la ville d'un client se choisit dans une **liste de secteurs** (pas de doublons
d'écriture) ; nacelle et sort du bois sont des options du travail.

## Contenu

```
schema/schema.sql                       schéma SQLite prêt à exécuter (tables, règles, vue v_chantiers) ; schema/migration_v*.sql : migrations automatiques
outils/interface.py                     serveur local, page Chantiers, nouvelle soumission
outils/pages_soumissions.py             onglet Soumissions : liste, boutons Accepter / En attente / Refuser, page « Accepter » qui ne demande que ce qui manque
outils/pages_attente.py                 « Mettre en attente » (date de reprise ou à nouvel ordre) et « Sortir de l'attente »
outils/archives.py                      onglet Archives : recherche, relance par client, statistiques, export CSV (administrateur)
outils/raccourcis.py                    pastilles de raccourcis en haut de Chantiers et Soumissions (chaque compte garde les siennes)
outils/listes.py                        sélections des listes Chantiers et Soumissions (filtres, recherche, délais)
outils/calendrier.py                    accueil : calendrier du mois + déroulement de la journée choisie (lecture seule)
outils/tableau.py                       page Journée (créer / gérer une journée) et actions rapides (terminer, retirer, annuler, ordre)
outils/composants.py                    cellules (client, adresse, travaux, montant) partagées, bouton Terminer et sa fenêtre de confirmation
outils/pages_clients.py                 liste des clients, fiche client, secteurs desservis, nouvelle soumission pour un client
outils/pages_chantier.py                page d'une soumission ou d'un chantier (client en lecture seule, verrou « Terminé », paiements, duplication)
outils/pdf.py                           PDF de la journée (feuilles de route, sans rien installer)
outils/auth.py, outils/reseau.py        comptes et connexion ; accès par téléphone / iPad (Tailscale)
outils/vue.py                           composants d'affichage partagés
outils/noyau.py                         règles de validation et d'écriture partagées, migrations
outils/donnees_test.py                  crée une base d'ESSAI avec de fausses données
gerer_utilisateurs.bat / .py            créer les comptes (administrateur, soumission) ; lancer_reseau.bat / .py : accès à distance
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

**Mises à jour du programme.** Une base des formats v8, v9 et v10 est **migrée automatiquement** au premier lancement de la nouvelle version, après une **copie de sécurité** (`data/sauvegardes/…avant_migration…`) : rien n'est perdu, et si la migration échoue la base reste intacte. Un format plus ancien est refusé : tant qu'il n'y a pas de vraies données, il suffit de supprimer le fichier de base (`data/sylvainculteur.db`). La base d'essai (`data/test.db`, fausses données) est simplement recréée toute seule par `--essai` quand son format est périmé.

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
