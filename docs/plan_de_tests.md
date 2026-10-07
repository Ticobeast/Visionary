# Plan de mise en route et de tests

But : **valider le système avec de fausses données**, puis le mettre en service sur ta vraie base. Il n'y a pas de données anciennes à reprendre
pour l'instant : on part à neuf.

| Phase | Durée | Données | Résultat attendu |
|---|---|---|---|
| 0. Installation | 30 min | aucune | les tests automatiques passent chez toi |
| 1. Essai à blanc | 1 h | **fausses** (`data/test.db`) | tu sais tout faire dans l'interface |
| 2. Mise en service | 1 semaine | **vraies** (`data/sylvainculteur.db`) | tu utilises l'interface tous les jours, sauvegarde restaurée avec succès |

---

## Phase 0 : installation (30 min)

1. **Python 3** : https://www.python.org/downloads/ (Windows : cocher « Add python.exe to PATH »).
   Vérifier dans un terminal : `python --version` (Windows) ou `python3 --version` (Mac) : « Python 3.... ».
2. **Le projet** : sur GitHub, bouton vert **Code, Download ZIP**, puis décompresser dans un dossier **hors OneDrive**
   (par exemple `C:\SylvainCulteur`). (Pas besoin de Git.)
3. **Vérifier l'installation** : dans un terminal ouvert dans ce dossier,
   `python3 -m unittest discover -s tests` : doit finir par **`OK`**.
4. *(Facultatif)* Installer **DB Browser for SQLite** (https://sqlitebrowser.org/) pour regarder dans la base.

> Windows : remplace `python3` par `python` (ou `py`) dans toutes les commandes.
> Les lanceurs à double-clic `lancer_interface.bat` (Windows) et `lancer_interface.command` (Mac) existent
> mais n'ont pas encore été testés sur ces systèmes : s'ils échouent, utilise les commandes du terminal.

**Réussi si** : les tests affichent `OK` et `python3 outils/interface.py --sans-navigateur` écrit une adresse
`http://localhost:8765/` sans erreur (Ctrl+C pour arrêter).

## Phase 1 : essai à blanc sur de fausses données (1 h)

```bash
python3 outils/interface.py --essai               # crée data/test.db (~40 chantiers fictifs) au besoin et l'ouvre
```

Le bandeau orange **« BASE D'ESSAI : test.db »** en haut à droite confirme que tu es sur les fausses données ; sur ta
vraie base, il affiche simplement « Base : sylvainculteur.db ». (Si la base d'essai date d'une version précédente du programme, elle est
recréée toute seule.)

Fais chacun de ces scénarios et coche ce qui fonctionne comme attendu :

| # | Scénario | Résultat attendu |
|---|---|---|
| 1 | Regarder le menu du haut | seulement : Tableau de bord, Journée, Chantiers, **Soumissions**, Clients, **Archives** ; **aucun emoji** nulle part |
| 2 | **Tableau de bord** | un calendrier du mois ; **dans chaque case** d'un jour planifié : « N chantiers », « Temps total : X h », « Montant total : XXX $ » ; les jours de plus de 8 h sont en rouge |
| 3 | Cliquer sur une **date** du calendrier | la journée s'affiche dessous : durée totale, montant total, chantiers dans l'ordre avec heures, temps, options (nacelle, bois) et **montant à droite** ; **aucun statut ni paiement** ; un seul bouton **Terminer**, en bas de chaque chantier |
| 4 | Dîner : un chantier de plus de 2 h qui commence à 10 h 30 | il est prolongé de 30 min (« dîner inclus ») ; un chantier qui finit à 12 h 00 pile est suivi d'une ligne « Dîner 12 h 00 - 12 h 30 » |
| 5 | **Terminer** un chantier planifié, répondre « Pas encore payé » | fenêtre « Terminer ce chantier » ; après « Oui, il est terminé » : le chantier est verrouillé, **à recevoir** (dans Chantiers, pas dans les archives) |
| 6 | **Terminer** un autre chantier, répondre « Oui, payé en totalité » | le paiement du solde est enregistré avec le mode choisi ; le chantier va **dans les archives** |
| 7 | Fenêtre « Terminer » : cliquer « Annuler » | rien ne change |
| 8 | Page **Journée** : chercher où changer le statut ou la durée d'un chantier | il n'y en a **pas** ; une flèche vers le haut et une vers le bas (sans texte), boutons Terminer et Retirer ; pas d'Annuler |
| 9 | Journée : flèche vers le haut / vers le bas | l'ordre change et **toutes les heures sont recalculées** tout de suite ; aux extrémités le bouton est grisé |
| 10 | Journée : **Retirer** un chantier | il redevient « À planifier » (sans date) et disparaît de la journée |
| 11 | Page d'un chantier planifié, « Paramètres avancés », « Annuler le chantier » (confirmation) | il disparaît de la journée et apparaît dans les **archives** (bas de la page Chantiers) |
| 12 | Journée : choisir demain, filtrer par secteur, cocher 3 chantiers, « Ajouter à la journée » | ils s'ajoutent **à la fin** de la journée, dans l'ordre affiché, et deviennent planifiés ; le total d'heures et de dollars se met à jour en cochant ; un chantier sans durée ne peut pas être coché |
| 13 | **Chantiers** | une seule page : **raccourcis** (pastilles) en haut, chantiers actifs (date d'attente, pastille de délai, temps, **montant à droite**), « Archives » plus bas ; filtres statut / paiement / secteur ; **aucune soumission** |
| 14 | **Clients > + Nouveau client**, client neuf : nom, adresse, secteur (liste), un type, durée, prix | « Soumission créée » et on **revient à la fiche du client** ; « Paramètres avancés » reste replié ; la date de la demande est celle d'aujourd'hui |
| 15 | Même formulaire : ville / secteur | **liste déroulante** (pas de champ texte), jamais obligatoire à l'ouverture d'une soumission ; la ville de l'adresse en découle |
| 16 | Cocher « Nacelle requise » ; cocher un abattage **sans** « Débarrasser le bois » | la soumission s'enregistre ; mais **Accepter** demande le format du bois (16 pouces / 4 pieds) ; ces options sont visibles **sans** ouvrir « Paramètres avancés » |
| 17 | Ouvrir la soumission créée (onglet Soumissions) | résumé avec la **valeur à droite**, boutons **Accepter / Refuser / Dupliquer**, ce qui manque encore pour accepter, client en lecture seule ; **aucune liste « Statut »** nulle part |
| 18 | Page d'un chantier : chercher un champ pour changer le nom ou l'adresse du client | il n'y en a pas : le client est en lecture seule ; « Modifier le client » mène à sa fiche |
| 19 | **Clients** : la liste | seulement Nom, Téléphone, Adresse (le secteur sous l'adresse) ; filtre par secteur ; la fiche d'un client n'affiche aucun montant |
| 20 | **Clients**, « Gérer les secteurs desservis » : ajouter « Cap de la Madeleine » ; ajouter un vrai nouveau secteur ; renommer ; supprimer un secteur utilisé | le doublon (accent, tiret ou casse près) est refusé ; un secteur utilisé ne se supprime pas ; la liste déroulante suit |
| 21 | Ajouter un **acompte** (page d'un chantier, « + Ajouter un paiement »), puis un paiement plus grand que le solde | acompte accepté (« Partiel ») ; le dépassement est **refusé** (jamais de solde négatif) |
| 22 | Ouvrir un chantier **terminé** | page en **lecture seule** ; ni formulaire, ni « Supprimer » ; ni facture ni bouton « Facturer » (terminé = client facturé) ; il reste « + Ajouter un paiement » et « Dupliquer » |
| 23 | **Dupliquer le chantier** sur un chantier terminé : changer le prix, valider | nouvelle **soumission** du même client : mêmes travaux et options, date de demande = aujourd'hui, aucun paiement ; l'original est intact |
| 24 | Se tromper exprès : téléphone `123`, prix `12,345` | chaque erreur est expliquée, **rien n'est perdu** dans le formulaire |
| 25 | Cliquer une **adresse** | Google Maps s'ouvre sur cette adresse dans un nouvel onglet |
| 26 | Fermer l'interface (Ctrl+C), la relancer | les données sont toujours là |
| 27 | **Clients** : ouvrir la fiche d'un client qui a un chantier annulé, un chantier terminé (avec paiement), « Supprimer le client » (confirmation) | le client est **toujours** supprimable ; la confirmation annonce les chantiers et paiements ; ensuite il n'apparaît plus nulle part (Clients, Chantiers, archives, calendrier) |
| 28 | **Chantiers** : regarder une ligne et la page d'un chantier | pas de pastille « Nacelle requise » ni « Bois ... » (elles restent dans le tableau de bord et la Journée) |
| 29 | **Tableau de bord** : choisir un jour avec des chantiers, « Télécharger la journée (PDF) » (en bas) | un fichier `journee-AAAA-MM-JJ.pdf` se télécharge ; il contient, pour chaque chantier : heures, client, téléphone, adresse, accès, travaux avec précisions, description, options, durée, prix et taxes, paiements, reste à encaisser et, si le dossier de photos existe, les photos en vignettes |
| 30 | **Journée** : regarder les boutons d'un chantier planifié | **Terminer** et **Retirer** sont côte à côte, sur une même ligne |
| 31 | **Téléphone** (après l'installation de `docs/acces_a_distance.md`) : ouvrir l'adresse sur un téléphone, parcourir Tableau de bord, Journée, Chantiers, Clients | aucune barre de défilement horizontale ; une carte par chantier ; boutons faciles à toucher ; « Terminer » et « Retirer » côte à côte |
| 32 | **Deux appareils** : ouvrir le même chantier sur deux appareils, modifier la description sur le 1er et enregistrer, puis modifier sur le 2e et enregistrer | le 2e voit « Cette fiche vient d'être modifiée par quelqu'un d'autre », ses changements ne sont pas enregistrés, la fiche à jour s'affiche |
| 33 | **Refus** : depuis un appareil qui n'est PAS dans ton Tailscale (ex. un ordinateur du Wi-Fi), ouvrir `http://adresse-de-l'atelier:8765` | la page ne s'ouvre pas (« Accès refusé » ou aucune réponse) |
| 34 | **Comptes** : `gerer_utilisateurs.bat`, créer un administrateur et un compte « Soumission » ; relancer l'application | la page de connexion s'affiche partout (même sur l'ordinateur) ; un mauvais mot de passe est refusé ; 5 essais ratés bloquent 15 minutes |
| 35 | **Compte Soumission** sur un téléphone | arrive sur les **Soumissions** ; barre du bas : Chantiers, Soumissions, Clients, + Soumission ; pas de Journée, de PDF, de paiements, de bouton Terminer ni Supprimer ; peut créer, modifier, accepter et refuser une soumission |
| 36 | **Administrateur** : page Utilisateurs : changer le mot de passe du compte Soumission | l'appareil de cette personne est déconnecté ; elle se reconnecte avec le nouveau mot de passe |
| 37 | **Soumissions > + Nouvelle soumission**, ne **rien remplir**, « Créer la soumission » | acceptée (rien n'est obligatoire) ; retour à la fiche du client ; dans Soumissions elle s'affiche « (client à identifier) » avec en rouge « Il manque : nom, téléphone, adresse, ... » |
| 38 | Soumission à moitié remplie (nom, téléphone, un type de travaux), bouton **Accepter** | le programme **ne l'accepte pas** : il ouvre « Accepter la soumission » avec **seulement les champs manquants** (adresse, secteur, durée, prix) ; « Enregistrer et accepter » la place dans **Chantiers, À planifier** et elle quitte Soumissions |
| 39 | Soumission complète, bouton **Accepter** (liste ou page de la fiche) | elle devient tout de suite un chantier « À planifier » (message « Soumission acceptée ») ; dans la page du chantier : « Remettre en soumission » la ramène dans Soumissions |
| 40 | **Refuser** une soumission (confirmation) | elle disparaît de la liste et va dans la section **Refusées** (bas de la page) ; elle n'est ni dans Chantiers ni dans ses archives ; « Rouvrir » la remet en cours |
| 41 | Regarder Chantiers, Journée et le tableau de bord après avoir ouvert 3 soumissions | **aucune soumission** n'y apparaît ; les compteurs et les journées sont inchangés |
| 42 | Chantiers : cliquer une **pastille** (par ex. « Planifiés »), puis la même pastille | le premier clic filtre la liste (pastille surlignée), le second retire le filtre |
| 43 | **Modifier les raccourcis** (lien à côté des pastilles) : ajouter « Terminés », créer « Planifiés du centre-ville » (statut + secteur), monter / descendre, retirer, « Rétablir ceux du départ » | chaque action se voit tout de suite dans les pastilles ; on peut tout retirer (ceux du départ ne reviennent pas seuls) ; un doublon est refusé |
| 44 | Deux comptes : ajouter un raccourci avec un compte, regarder avec l'autre | chacun garde **ses** raccourcis ; « Mes soumissions » ne compte que celles que le compte a ouvertes ; le compte Soumission **ne voit aucune pastille de paiement** |
| 45 | Fiche d'un client créé par une soumission vide : « Modifier le client » sans rien remplir | accepté tant que le client n'a que des soumissions ; avec un chantier, le nom, l'adresse et le secteur redeviennent obligatoires ; depuis une soumission, « Modifier le client » **ramène à la soumission** |
| 46 | *(si tu as déjà une base d'une version précédente)* Lancer la nouvelle version | une copie « avant_migration » apparaît dans `data/sauvegardes` ; tes chantiers sont toujours là |
| 47 | Soumissions : une soumission **complète**, bouton **En attente** | une petite page demande « Jusqu'au [date] » (raccourcis dans 1, 2, 3, 6 mois) ou « Jusqu'à nouvel ordre » ; après « Mettre en attente », elle a quitté Soumissions et est dans **Chantiers**, statut « En attente », avec « reprise le … » |
| 48 | Même bouton sur une soumission **incomplète** | le programme demande d'abord ce qui manque (« Mettre en attente la soumission »), puis passe à la page de la date : **pour mettre en attente, la soumission doit être complète** |
| 49 | Chantiers : lien « En attente (N) » en haut ; page d'un chantier en attente | le lien montre seulement les chantiers en attente ; la fiche indique « En attente : reprise le … » et offre **Sortir de l'attente**, **Changer la date**, **Remettre en soumission** ; ce chantier **n'est pas proposé dans la Journée** |
| 50 | Mettre en attente un chantier « À planifier » (bouton de sa fiche), choisir une date de reprise **demain** ; le lendemain, ouvrir Chantiers | il est redevenu « À planifier » **tout seul**, avec un délai d'attente à 0 jour, et il est de nouveau dans la Journée |
| 51 | « Jusqu'à nouvel ordre », puis **Sortir de l'attente** | il reste en attente jusqu'au clic ; le bouton le remet « À planifier » tout de suite |
| 52 | **Archives** (administrateur) : filtres Type « Taille de haie », texte « cèdre », « Fait il y a plus de 1 an », cocher « Un seul résultat par client », tri « Plus ancien d'abord » | la liste des clients à relancer : un par ligne, avec la date et les travaux de leur dernier chantier ; le bouton **Relancer** ouvre une nouvelle soumission à leur nom |
| 53 | Archives : regarder les chiffres clés et les statistiques (par type de travaux, par secteur, par année, selon le mois de l'année, que deviennent les soumissions) | des nombres cohérents avec les chantiers terminés ; les barres suivent le chiffre d'affaires ; le taux d'acceptation compte les soumissions acceptées et refusées |
| 54 | Archives : « Exporter (Excel) », ouvrir le fichier dans Excel | un fichier `archives-AAAA-MM-JJ.csv` : accents corrects, montants avec la virgule, mêmes résultats que la page (et tous, pas seulement les 200 premiers) |
| 55 | Compte « Soumission » : chercher « Archives » dans le menu, ouvrir `/archives` à la main | pas d'entrée Archives, et la page est refusée (réservée à l'administrateur) |

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

**Réussi si** : les 55 scénarios se passent comme prévu et le test de lecture affiche les chantiers planifiés
avec une adresse complète.

## Phase 2 : mise en service (1 semaine)

1. Tu pars de la vraie base (`data/sylvainculteur.db`, créée automatiquement au premier lancement).
2. Chaque nouvelle demande, soumission, travail fait et paiement va dans l'interface. Note ce qui manque ou ce qui t'agace : un champ absent,
   un formulaire lourd. C'est le bon moment pour ajuster.
3. **Test de restauration de la sauvegarde** (indispensable : une sauvegarde jamais restaurée n'est pas une sauvegarde) :
   1. copier tout le dossier `data/` ailleurs (clé USB) ;
   2. renommer `data/sylvainculteur.db` en `data/ancienne.db` ;
   3. y remettre la copie de la clé ; relancer l'interface : les chantiers sont là.

**Réussi si** : tu utilises l'interface tous les jours sans aide et la restauration a réussi. Alors on enchaîne sur l'étape 2 (géocodage,
itinéraire, feuille de route).

---

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| « La base ... a été créée par une version précédente du programme » | le format de la base a changé | pas de vraies données : supprimer le fichier indiqué (il est recréé) |
| Le port 8765 est utilisé | l'interface est déjà ouverte | ajouter `--port 8766` |
| Un message « La base est occupée » | un autre programme (DB Browser) a la base ouverte | le fermer, recharger la page |
| Une date est refusée | format | l'interface utilise un sélecteur de date |
