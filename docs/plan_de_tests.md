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
| 1 | **Chantiers** → raccourci « à facturer » | seuls les chantiers faits et non facturés s'affichent, avec leur montant ; les anciens chantiers (terminés et payés) sont plus bas, sous « Archives » |
| 2 | Chercher un client par nom **sans accent** (ex. « cote » pour Côté), puis par téléphone | le bon client apparaît |
| 3 | **+ Nouveau**, client neuf : nom, adresse, ville, au moins un type coché, **durée estimée** (« Paramètres avancés » reste replié : statut « Soumission » et date de la demande = aujourd'hui par défaut) | « Chantier créé » ; le chantier apparaît dans la liste |
| 4 | **Client qui revient** : « Nouveau chantier » → chercher son nom → cliquer sa fiche → choisir un type | adresse et téléphone déjà remplis ; **aucun nouveau client** créé |
| 5 | Passer le chantier de 3 à « Planifié » **sans** date | l'enregistrement est refusé, avec un message clair |
| 6 | Mettre une date + une durée estimée (ex. `2,5`) ; essayer de la laisser vide | `2,5` est compris comme 2 h 30 ; durée vide = refusé (« obligatoire ») |
| 7 | Changer la date du chantier (« il est déplacé à jeudi »), puis le passer à « Terminé » | **une seule date** : elle se met à jour ; statut « À facturer » (si prix saisi) ; **la durée réelle reprend la durée estimée** |
| 7b | **Plusieurs types** : cocher « Élagage » et « Taille de haie » et écrire une précision pour chacun | la page du chantier affiche « Élagage : … ; Taille de haie : … » |
| 8 | Saisir le prix + cocher « Calculer TPS et TVQ » + n° et date de facture | total = prix + 5 % + 9,975 % ; statut « Facturé, à recevoir » |
| 9 | Ajouter un **acompte**, puis le **solde** | « Partiel » puis « Payé » ; solde à 0 |
| 10 | Se tromper exprès : téléphone `123`, code postal `ZZZ`, prix `12,345` | chaque erreur est expliquée, **rien n'est perdu** dans le formulaire |
| 11 | Modifier l'adresse d'un client, puis supprimer un paiement et un chantier de test | tout se passe sans erreur |
| 12 | Fermer l'interface (Ctrl+C), la relancer | les données sont toujours là |
| 13 | **Tableau de bord** (accueil) | **seulement** un calendrier du mois ; **dans chaque case** d'un jour planifié : « N chantiers », « ⏱ Temps total : X h », « 💰 Montant total : XXX $ » ; les jours trop chargés (> 8 h) sont en rouge |
| 14 | Cliquer sur une **date** du calendrier | le déroulement de la journée s'affiche dessous : durée totale, **total en $** (taxes incluses), chantiers dans l'ordre avec heures, temps de chacun, options (🏗 nacelle, 🪵 bois), statut, paiements et **montant à droite** ; ni flèches, ni statut, ni durée modifiables ; seulement « Retirer » et « Encaisser » (montant prévu **non modifiable**, on confirme) |
| 15 | Repérer le **dîner** : un chantier de plus de 2 h qui commence à 10 h 30 | il est prolongé de 30 min (« dîner inclus ») ; un chantier qui finit à 12 h 00 pile est suivi d'une ligne « Dîner 12 h 00 - 12 h 30 » |
| 16 | Page **Journée** : cliquer **▼** sur le 1er chantier, puis **▲** sur le 3e | l'ordre change et **toutes les heures sont recalculées** tout de suite ; aux extrémités la flèche est grisée |
| 17 | Sur la page **Journée**, chercher où modifier la **durée** d'un chantier ; l'ouvrir (lien du chantier), changer « Durée estimée » (ex. `1`), enregistrer | aucun champ de durée dans la Journée ni sur le tableau de bord ; sur le chantier, les heures des suivants se décalent |
| 18 | Page **Journée** : chercher où changer le **statut** d'un chantier | il n'y a **aucun** choix de statut : ajouter à la journée = Planifié ; **Retirer** = À planifier ; **Annuler** (confirmation) = disparaît de la journée et va dans les **Archives** |
| 19 | **Encaisser** (tableau de bord ou Journée) sur un chantier « Planifié » | le montant prévu est affiché sans pouvoir le modifier ; après confirmation le paiement est enregistré, puis une fenêtre demande : *Voulez-vous passer ce chantier au statut "Terminé" ?* — « Oui » le passe à Terminé, « Non » le laisse Planifié |
| 20 | Même encaissement sur un chantier « Terminé » ou « À planifier » | **aucune** fenêtre |
| 21 | **Chantiers** : regarder la liste active | délai d'attente en pastille (rouge > 30 j, jaune 7 à 30 j, vert < 7 j) sur les chantiers à planifier ; temps de chaque chantier ; **montant à droite** ; filtres statut / paiement |
| 22 | Cliquer une **adresse** | Google Maps s'ouvre sur cette adresse dans un nouvel onglet |
| 23 | **Facturer** (page du chantier terminé), puis **Encaisser** un acompte et le solde | « Facturé », « Partiel », « Payé » ; à « Payé », le chantier descend dans les **Archives** |
| 24 | **Clients** → un client → **+ Nouveau chantier** | nom et adresse **verrouillés** ; travaux, date de la demande (aujourd'hui), durée estimée obligatoire, prix, mode de règlement (un seul choix), notes ; le chantier arrive « À planifier » |
| 25 | **Journée** : choisir demain, filtrer par secteur, cocher 3 chantiers, « Ajouter à la journée » | ils s'ajoutent **à la fin** de la journée, dans l'ordre affiché ; le total d'heures **et de dollars** se met à jour en cochant ; un chantier sans durée ne peut pas être coché |
| 26 | Dans la journée : **Retirer** un chantier | il redevient « À planifier » (sans date) |
| 27 | **Clients** (liste) | seulement 3 colonnes : Nom, Téléphone, Adresse ; la fiche d'un client n'affiche aucun montant |
| 28 | Ouvrir un chantier existant : chercher un champ pour changer le nom ou l'adresse du client | il n'y en a pas : le client est en lecture seule (🔒) ; le bouton **Modifier le client** mène à sa fiche ; même chose après « Enregistrer » |
| 29 | Chantier « Planifié » avec un solde de 100 $ : encaisser **150 $** | refusé (« solde négatif interdit ») ; 100 $ passe ; plus aucun paiement possible ensuite |
| 30 | Mode de règlement | une seule liste : Comptant, Chèque, Interac, Carte, Autre |
| 31 | Passer un chantier à « Terminé » (fenêtre de confirmation) | la durée réelle est préremplie avec l'estimée |
| 32 | Ouvrir ce chantier terminé | page en **lecture seule** (🔒) ; ni formulaire, ni « Supprimer » ; il reste « Facturer », « Encaisser », « Dupliquer » |
| 33 | Facturer puis encaisser **tout** le solde du chantier terminé | il quitte *Chantiers* et apparaît dans **Archives** tout seul |
| 34 | **Dupliquer le chantier** sur un chantier terminé : changer le prix, valider | nouvelle **soumission** du même client : mêmes travaux, date de demande = aujourd'hui, aucun paiement ni facture ; l'original est intact |
| 35 | Menu du haut | seulement : Tableau de bord, Journée, Chantiers, Clients, + Nouveau (ni Suivi, ni Tournées, ni Archives) ; les archives sont en bas de la page Chantiers |
| 36 | Ouvrir un chantier existant | résumé + valeur à droite, client en lecture seule, paiements ; le reste (dates, taxes, facture, fichiers, suppression) est dans « Paramètres avancés » (replié) |
| 37 | **Chantiers** : regarder la colonne de date | c'est la **date de la demande / soumission** (pas la date planifiée, qui n'apparaît que comme « prévu le … ») ; classement du plus récent au plus ancien |
| 38 | Annuler un chantier (page du chantier, « Paramètres avancés » → « Annuler le chantier », ou « Annuler » dans la Journée) | il quitte les chantiers actifs et la journée, et apparaît dans les **Archives** ; « ↩ Rouvrir » le remet « À planifier » |
| 39 | Page d'un chantier planifié | le statut et la date sont affichés (« géré automatiquement », « se change dans la page Journée ») ; « ✔ Marquer comme terminé » le termine (durée réelle reprise de l'estimée) |
| 40 | **+ Nouveau** : regarder « Ville / secteur » | **liste déroulante** obligatoire (pas de champ texte) ; la ville de l'adresse (Google Maps) vient du secteur ; impossible d'écrire « Trois Rivieres » |
| 41 | **Clients** → « Gérer les secteurs desservis » : ajouter « Cap de la Madeleine » ; ajouter « Nouveau secteur » ; renommer ; supprimer un secteur utilisé | le doublon (accent / tiret / casse près) est refusé ; un secteur utilisé ne se supprime pas ; la liste déroulante suit |
| 42 | **Clients** et **Chantiers** : filtrer par secteur | seuls les clients / chantiers de ce secteur ; le secteur est écrit sous l'adresse |
| 43 | Nouveau chantier : cocher « 🏗 Nacelle requise », puis un abattage **sans** cocher « Débarrasser le bois » | refusé tant que le format du bois (16 pouces / 4 pieds) n'est pas précisé ; ces options sont visibles **sans** ouvrir « Paramètres avancés » |
| 44 | Ouvrir le chantier, la liste *Chantiers*, le tableau de bord, la Journée | 🏗 « Nacelle requise » et 🪵 « Bois débarrassé » / « Bois laissé sur place : 16 pouces » s'affichent partout où le travail apparaît |

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
