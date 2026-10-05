# SylvainCulteur — noyau de données (étape 1)

Base de données **locale, privée et sans abonnement** pour les dossiers clients et les chantiers
d'émondage, d'élagage et de taille de haies. Cette étape pose uniquement le noyau de données et la méthode de
saisie ; les itinéraires, les feuilles de route PDF, l'iPad, les finances et les textos viendront ensuite
sur cette base, sans retranscription.

## Le choix : SQLite, avec le CSV comme feuille de saisie

- **SQLite = la source de vérité.** Un seul fichier (`data/sylvainculteur.db`), aucun serveur, aucun abonnement.
  Python le lit sans rien installer (`import sqlite3`).
- **Pourquoi pas un CSV unique comme base ?** Les données sont reliées (client → adresse → chantier →
  paiements). Un CSV répète le client à chaque ligne (fautes de frappe, doublons), ne vérifie rien (un tableur
  réécrit silencieusement les dates et les virgules) et ne peut pas répondre à « qu'est-ce qui reste à
  facturer ? » sans code. SQLite refuse les données invalides **à la saisie**.
- **Le CSV reste l'outil de saisie** : un tableur est ce qu'il y a de plus rapide pour retranscrire des
  fiches. Une ligne = une fiche papier ; `outils/importer_saisie.py` la valide et la range dans les bonnes
  tables.

## Contenu

```
schema/schema.sql                       schéma SQLite prêt à exécuter (tables, règles, vue v_chantiers)
modeles/saisie_papier_exemples.csv      feuille de saisie avec 3 exemples fictifs
modeles/saisie_papier_vide.csv          feuille de saisie vide (en-têtes seulement)
outils/importer_saisie.py               validation + import du CSV dans la base
docs/dictionnaire_donnees.md            toutes les colonnes : type, format, règle, exemple
docs/transition_papier.md               méthode pour numériser les dossiers papier
tests/test_noyau.py                     tests automatiques (schéma + import)
data/                                   TES données (exclu de Git) : base, photos/, papier/, saisie/
```

## Démarrage rapide

```bash
# 1. Essayer avec les exemples fictifs (rien n'est écrit)
python3 outils/importer_saisie.py modeles/saisie_papier_exemples.csv --simulation

# 2. Créer ta vraie base et importer un lot (la base est créée automatiquement)
mkdir -p data/saisie
cp modeles/saisie_papier_vide.csv data/saisie/lot_01.csv
#    ... saisir les fiches dans le tableur ...
python3 outils/importer_saisie.py data/saisie/lot_01.csv --simulation
python3 outils/importer_saisie.py data/saisie/lot_01.csv

# Créer la base vide à la main, sans importer :
sqlite3 data/sylvainculteur.db < schema/schema.sql
```

Outil graphique gratuit pour consulter et corriger la base : [DB Browser for SQLite](https://sqlitebrowser.org/).
Tests : `python3 -m unittest discover -s tests -v`.

Les chemins de photos et de scans sont **relatifs au dossier `data/`** : si tu déplaces `data/` (disque,
autre ordinateur), tout reste valide.

## Confidentialité

`data/` et tous les fichiers `*.db` sont dans le `.gitignore` : les vraies données de tes clients ne doivent
jamais être envoyées sur GitHub. Le dépôt ne contient que des exemples fictifs (téléphones en `555-01xx`,
courriels `@example.com`).

## Prérequis

Python 3 (testé avec 3.11, bibliothèque standard seulement). Testé avec SQLite 3.45. Le schéma évite
volontairement `STRICT`, les colonnes générées et les autres nouveautés récentes de SQLite, pour qu'un outil
plus ancien (DB Browser…) puisse ouvrir le fichier ; ce point n'a pas été testé sur d'anciennes
versions.
