# Plan de mise en route et de tests

But : **valider le système avec de fausses données, puis avec 10 vrais dossiers, avant de saisir les 150**.
Si quelque chose ne convient pas (un champ manque, un formulaire est lourd), on l'ajuste maintenant, quand ça
coûte 10 minutes, pas après 150 fiches.

| Phase | Durée | Données | Résultat attendu |
|---|---|---|---|
| 0. Installation | 30 min | aucune | les tests automatiques passent chez toi |
| 1. Essai à blanc | 1 h | **fausses** (`data/test.db`) | tu sais tout faire dans l'interface |
| 2. Pilote | 2 h | **10 vrais dossiers** (`data/pilote.db`, jetable) | temps par fiche mesuré, champs manquants listés |
| 3. Semaine en parallèle | 1 semaine | **vraies**, papier + numérique | aucun écart entre les deux |
| 4. Décision | 30 min | — | feu vert pour la saisie complète, ou ajustements |

---

## Phase 0 — Installation (30 min)

1. **Python 3** : https://www.python.org/downloads/ (Windows : cocher « Add python.exe to PATH »).
   Vérifier dans un terminal : `python --version` (Windows) ou `python3 --version` (Mac) → « Python 3.… ».
2. **Le projet** : sur GitHub, bouton vert **Code → Download ZIP**, puis décompresser dans un dossier **hors OneDrive**
   (par exemple `C:\SylvainCulteur`). (Pas besoin de Git.)
3. **Vérifier l'installation** : dans un terminal ouvert dans ce dossier,
   `python3 -m unittest discover -s tests` → doit finir par **`OK`**.
4. *(Facultatif)* Installer **DB Browser for SQLite** (https://sqlitebrowser.org/) pour regarder dans la base.

> Windows : remplace `python3` par `python` (ou `py`) dans toutes les commandes.
> Les lanceurs à double-clic `lancer_interface.bat` (Windows) et `lancer_interface.command` (Mac) existent
> mais n'ont pas encore été testés sur ces systèmes : s'ils échouent, utilise les commandes du terminal.

✅ **Réussi si** : les tests affichent `OK` et `python3 outils/interface.py --sans-navigateur` écrit une adresse
`http://localhost:8765/` sans erreur (Ctrl+C pour arrêter).

## Phase 1 — Essai à blanc sur de fausses données (1 h)

```bash
python3 outils/interface.py --essai               # crée data/test.db (~40 chantiers fictifs) au besoin et l'ouvre
```

Le bandeau orange **« BASE D’ESSAI : test.db »** en haut à droite confirme que tu es sur les fausses données ; sur ta
vraie base, il affiche simplement « Base : sylvainculteur.db ».

Fais chacun de ces scénarios et coche ce qui fonctionne comme attendu :

| # | Scénario | Résultat attendu |
|---|---|---|
| 1 | Page d'accueil : cliquer la puce « à facturer » | seuls les chantiers faits et non facturés s'affichent, avec leur solde |
| 2 | Chercher un client par nom **sans accent** (ex. « cote » pour Côté), puis par téléphone | le bon client apparaît |
| 3 | **Nouveau chantier**, client neuf : nom, adresse, ville, au moins un type coché, statut « Soumission » | « Chantier créé » ; le chantier apparaît dans la liste |
| 4 | **Client qui revient** : « Nouveau chantier » → chercher son nom → cliquer sa fiche → choisir un type | adresse et téléphone déjà remplis ; **aucun nouveau client** créé |
| 5 | Passer le chantier de 3 à « Planifié » **sans** date | l'enregistrement est refusé, avec un message clair |
| 6 | Mettre une date + une heure + une durée estimée (ex. `2,5`) | enregistré ; `2,5` est compris comme 2 h 30 |
| 7 | Changer la date du chantier (« il est déplacé à jeudi »), puis le passer à « Terminé » | **une seule date** : elle se met à jour ; statut « À facturer » (si prix saisi) |
| 7b | **Plusieurs types** : cocher « Élagage » et « Taille de haie » et écrire une précision pour chacun | la page du chantier affiche « Élagage : … ; Taille de haie : … » |
| 8 | Saisir le prix + cocher « Calculer TPS et TVQ » + n° et date de facture | total = prix + 5 % + 9,975 % ; statut « Facturé, à recevoir » |
| 9 | Ajouter un **acompte**, puis le **solde** | « Partiel » puis « Payé » ; solde à 0 |
| 10 | Se tromper exprès : téléphone `123`, code postal `ZZZ`, prix `12,345` | chaque erreur est expliquée, **rien n'est perdu** dans le formulaire |
| 11 | Modifier l'adresse d'un client, puis supprimer un paiement et un chantier de test | tout se passe sans erreur |
| 12 | Fermer l'interface (Ctrl+C), la relancer | les données sont toujours là |
| 13 | **Tableau de bord**, onglet « À planifier » | chantiers regroupés « Urgent (> 30 j) », « À surveiller », « Normal (< 7 j) », avec pastilles rouge / jaune / verte |
| 14 | Filtrer par **délai** (« Urgents »), par **secteur**, puis trier par secteur | seuls les chantiers voulus ; avec le tri secteur, regroupés par ville |
| 15 | Cliquer sur une **adresse** | Google Maps s'ouvre sur cette adresse dans un nouvel onglet |
| 16 | Dans une ligne « À planifier » : statut « Planifié » + une date + `2,5` + OK | le chantier quitte l'onglet et apparaît dans « Planifiés » (2 h 30) |
| 17 | Onglet « À facturer » : **Facturer** ; puis dans « À recevoir » : **Encaisser** un acompte, puis le solde | passe à « Facturé », « Partiel », puis « Payé » sans ouvrir de fiche |
| 18 | **Clients** → un client → **+ Nouveau chantier** | nom et adresse **affichés mais non modifiables** ; seulement travaux, prix, modalité de paiement, notes ; le chantier arrive « À planifier » |
| 19 | **Tournées** : choisir demain, filtrer par secteur, cocher 3 chantiers, ajuster une durée, « Ajouter à la journée » | le total d'heures se met à jour en cochant ; la journée affiche les 3 chantiers et ce qu'il reste de place sur 8 h |
| 20 | Dans la journée : **Retirer** un chantier | il redevient « À planifier » (sans date) |

**Test de lecture par Python** (prépare l'étape 2 : itinéraires). Dans un terminal :

```bash
python3 - <<'EOF'
import sqlite3
c = sqlite3.connect("data/test.db")
c.row_factory = sqlite3.Row
for r in c.execute("SELECT client_nom_complet, adresse_maps, duree_estimee_h, date_prevue FROM v_chantiers "
                   "WHERE statut = 'planifie' ORDER BY date_prevue"):
    print(dict(r))
EOF
```

✅ **Réussi si** : les 12 scénarios se passent comme prévu et le test de lecture affiche les chantiers planifiés
avec une adresse complète.

## Phase 2 — Pilote avec 10 vrais dossiers (2 h)

La base pilote est **jetable** : on la supprime après, sans conséquence.

```bash
python3 outils/interface.py --db data/pilote.db
```

1. Choisis **10 dossiers variés** : 2 haies, 3 émondages, 1 abattage, 1 facture impayée, 1 client sans
   téléphone, 1 client avec deux propriétés, 1 entreprise (syndicat…).
2. **Chronomètre** chaque fiche, de la feuille papier à « Enregistrer ».
3. Remplis ce tableau au fur et à mesure :

| # | Minutes | Information du papier qui **ne rentre nulle part** | Champ rempli **à contrecœur** / inutile | Autre irritant |
|---|---|---|---|---|
| 1 | | | | |
| … | | | | |

4. Bilan, à la fin :
   - temps moyen d'une fiche **complète** (pile A) et d'une fiche **minimale** (pile B) ;
   - la liste des informations papier sans place → candidates à de nouvelles colonnes ;
   - les champs jamais utilisés → candidats à disparaître ;
   - les pages ou boutons qui t'ont fait hésiter.

✅ **Réussi si** : fiche complète en **≤ 6 min**, fiche minimale en **≤ 3 min** (après les 3 premières, qui
servent d'apprentissage), et aucune information essentielle sans place.

## Phase 3 — Une semaine en parallèle (vraie vie)

1. Tu pars de la vraie base (`data/sylvainculteur.db`, créée automatiquement au premier lancement).
2. Pendant **une semaine**, chaque nouvelle demande, soumission, travail fait et paiement va dans l'interface
   **en plus** du papier (pas à la place : c'est un essai).
3. Chaque soir, **5 minutes de vérification** : pour chaque chantier du jour, la fiche papier et la fiche
   numérique disent-elles la même chose (date, prix, statut, paiement) ? Note les écarts.
4. **Test de restauration de la sauvegarde** (indispensable : une sauvegarde jamais restaurée n'est pas une
   sauvegarde) :
   1. copier tout le dossier `data/` ailleurs (clé USB) ;
   2. renommer `data/sylvainculteur.db` en `data/ancienne.db` ;
   3. y remettre la copie de la clé ; relancer l'interface → les chantiers sont là.

✅ **Réussi si** : zéro écart non expliqué entre papier et numérique, restauration réussie, et tu as ouvert
l'interface sans l'avoir « évitée » un seul jour.

## Phase 4 — Décision (30 min)

| Critère | Seuil | Résultat |
|---|---|---|
| Fiche complète | ≤ 6 min | |
| Fiche minimale | ≤ 3 min | |
| Information essentielle sans place | aucune | |
| Écarts papier / numérique en semaine 3 | 0 non expliqué | |
| Sauvegarde restaurée avec succès | oui | |
| Tu utilises l'interface sans aide | oui | |

- **Tous verts** → on lance la saisie de la pile A (voir `docs/transition_papier.md`), puis B.
- **Un critère rouge** → on ajuste (colonne ajoutée, formulaire simplifié) et on refait la phase concernée.
  Rien de ce qui est déjà saisi n'est perdu : ajouter une colonne ne demande aucune retranscription.

Quand c'est validé, on enchaîne sur l'étape 2 (géocodage, itinéraire, feuille de route).

---

## Dépannage rapide

| Symptôme | Cause probable | Quoi faire |
|---|---|---|
| `python3 : commande introuvable` | Python absent ou nom différent | Windows : essayer `py` ou `python` ; sinon réinstaller en cochant « Add to PATH » |
| « Le port 8765 est déjà utilisé » | l'interface est déjà ouverte | l'utiliser, ou ajouter `--port 8766` |
| « La base est occupée » | DB Browser a la base ouverte en écriture | fermer DB Browser (ou « Écrire les modifications ») |
| Les accents s'affichent mal dans un CSV | encodage du tableur | enregistrer en UTF-8 ; l'import lit aussi le Windows-1252 |
| Une date est refusée | format | l'interface utilise un sélecteur de date ; dans un CSV, `AAAA-MM-JJ` seulement |
| L'interface ouvre toujours `sylvainculteur.db` et jamais la base d'essai | `interface.py` lancé sans option (bouton « Exécuter » de VS Code compris) | ouvrir et exécuter **`lancer_essai.py`** (ou `lancer_essai.bat`, ou `python outils/interface.py --essai`) ; l'étiquette en haut à droite indique la base ouverte |
| Avertissement « dossier synchronisé par OneDrive » | le projet est dans OneDrive / Dropbox… | déplacer **tout le dossier du projet** hors du service (ex. `C:\SylvainCulteur`) : tes données clients ne doivent pas partir dans le nuage |
| « La base utilise un ancien format (v1 ou v2) » | base créée avant une mise à jour | `python outils/migrer.py data/sylvainculteur.db` : convertit sans rien perdre (sauvegarde faite avant) |
