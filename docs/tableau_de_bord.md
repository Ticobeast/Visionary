# Tableau de bord, Journée, Chantiers, Soumissions et clients

Principe : **simple par défaut**. Chaque écran montre d'abord l'important ; les options rarement utiles sont dans « Paramètres
avancés » (repliés). Chaque chose a **un seul endroit** :

| Section | Rôle |
|---|---|
| **Tableau de bord** | voir le calendrier et le déroulement de la journée choisie ; terminer un chantier |
| **Journée** | créer et gérer une journée complète : placer des chantiers, ordre, terminer, retirer, annuler |
| **Chantiers** | les jobs **acceptés** : liste des chantiers actifs ; plus bas, les archives (anciens chantiers) |
| **Soumissions** | les demandes de soumission, du premier appel à la réponse du client : boutons **Accepter** / **Refuser** |
| **Clients** | les fiches clients (seul endroit où l'on modifie un client) et la liste des secteurs desservis |

L'interface ne contient **aucun emoji**.

## Soumission, puis chantier : une seule fiche, deux noms

Une **soumission** est un chantier qui n'est pas encore accepté : c'est la **même fiche**, qui change de nom et d'onglet quand le client dit oui.
**Aucune soumission n'apparaît dans Chantiers** (ni dans la Journée, ni dans le calendrier) : elles vivent dans l'onglet **Soumissions**, à droite de
Chantiers, jusqu'à leur acceptation.

## Les statuts : automatiques

| Statut | Où on le voit | Signification |
|---|---|---|
| **Soumission** | onglet Soumissions | demande ouverte, soumission à faire, remise ou en attente de la réponse du client |
| **Refusée** | Soumissions, section « Refusées » | le client a dit non (la soumission n'est pas supprimée) |
| **À planifier** | Chantiers | soumission acceptée, pas encore de date |
| **Planifié** | Chantiers, Journée | placé dans une journée |
| **Terminé** | Chantiers | travaux faits (puis verrouillé) |
| **Annulé** | Chantiers, archives | chantier accepté puis abandonné |

**Le statut ne se choisit jamais à la main** : il n'y a plus de liste « Statut » dans les formulaires. Il suit les boutons :

| Action | Statut qui en résulte |
|---|---|
| **Créer** (nouvelle soumission) | **Soumission** |
| **Accepter** la soumission (si tout est rempli : voir plus bas) | **À planifier** (la date d'acceptation est notée) |
| **Refuser** la soumission | **Refusée** |
| **Rouvrir** une soumission refusée | retour à **Soumission** |
| **Remettre en soumission** (chantier « À planifier » seulement) | retour à **Soumission** |
| Ajouter le chantier à une journée (page *Journée*) | **Planifié** |
| **Retirer** le chantier de la journée | retour à **À planifier** |
| **Annuler** le chantier (administrateur) | **Annulé** : il disparaît de la journée et va **automatiquement dans les archives** |
| **Rouvrir** un chantier annulé | retour à **À planifier** |
| **Terminer** le chantier (bouton, puis confirmation) | **Terminé** (verrouillé) |

L'annulation d'un chantier se fait sur sa page (« Paramètres avancés », « Annuler le chantier »).

## Pas de système de facture

Dès qu'un chantier est **Terminé**, le client est considéré comme **facturé** : il n'y a ni numéro de facture, ni date de facture, ni bouton
« Facturer ». Un chantier terminé qui n'est pas payé est simplement « **À recevoir** ».

## 1. Tableau de bord

Un **calendrier du mois**. Dans **chaque case** d'un jour planifié : le **nombre de chantiers**, le **temps total** et le **montant total**
(arrondi au dollar). Un jour de plus de 8 h est en rouge ; un jour passé avec des chantiers encore planifiés est signalé « à clôturer ».

**Un clic sur une date** affiche, juste en dessous, la journée :

- les **chantiers dans l'ordre de passage**, avec leurs **heures de début à fin** et le **temps de chacun** ;
- la **durée totale** et, juste dessous, le **montant total** de la journée (taxes incluses) ;
- à **droite de chaque chantier, sa valeur** (total taxes incluses, prix avant taxes en petit) ;
- les **options** de la job (« Nacelle requise », « Bois débarrassé » ou « Bois laissé sur place : 16 pouces »), seulement dans le tableau de bord et la Journée, où elles servent à préparer la job ;
- un seul bouton, **Terminer**, placé **en bas** de chaque chantier (pas de bouton Retirer ici : cela se fait dans la page *Journée*, où **Terminer** et **Retirer** sont côte à côte) ;
- en bas du panneau : **Gérer cette journée** et **Télécharger la journée (PDF)**.

Il n'y a **ni statut, ni paiement** sur cet écran : seulement le montant du chantier. Rien ne se modifie (ni durée, ni ordre). Le bouton
**Gérer cette journée** ouvre la page *Journée* sur la même date.

### Télécharger la journée en PDF

Sous le tableau de la journée choisie, le bouton **Télécharger la journée (PDF)** télécharge un fichier `journee-AAAA-MM-JJ.pdf`
(à imprimer ou à ouvrir sur l'iPad). Première page : le résumé de la journée (nombre de chantiers, heures de début et de fin, total en dollars)
et une ligne par chantier. Ensuite, **chaque chantier avec tous ses détails** : heures de passage, client (téléphones, courriel, rappels par texto),
adresse complète (**en bleu et cliquable : elle ouvre Google Maps**) et secteur, accès et notes, travaux avec leurs précisions, description, options (nacelle, bois), durées, prix avant taxes, TPS/TVQ,
total, mode de règlement prévu, paiements déjà reçus et **reste à encaisser**, et les **photos** du dossier de photos
du chantier (JPEG et PNG, 12 au maximum par chantier, en vignettes avec leur nom de fichier).

Photos : le programme ne demande rien d'installer. Si une photo de téléphone est lourde (plus de 1,5 Mo), elle n'est incluse que si **Pillow** est installé
(`pip install pillow`, facultatif) : il réduit et redresse les photos, et le PDF reste léger (quelques centaines de Ko). Sans Pillow, les photos trop
lourdes sont seulement **listées par leur nom** dans le PDF (« Non incluses »), rien ne plante. Le PDF ne modifie rien dans la base.

### Le bouton Terminer et sa fenêtre

Un clic sur **Terminer** ouvre une fenêtre :

> **Terminer ce chantier**
> Confirmes-tu que ce chantier est terminé ?
> Le client a-t-il payé ?  ( ) Oui, payé en totalité : 575,00 $   (•) Pas encore payé
> Mode de paiement (si payé) : [ Interac v ]      Durée réelle (heures) : [ 2 ]
> [ Oui, il est terminé ]   [ Annuler ]

- **Pas encore payé** : le chantier est terminé et reste « À recevoir ».
- **Payé** : le paiement du solde complet est enregistré (aujourd'hui, avec le mode choisi, proposé d'après le mode de règlement prévu) ; le
  chantier est alors terminé **et payé**, donc déplacé **dans les archives**.
- La **durée réelle** reprend la durée estimée (modifiable ici, pas après).
- « Annuler » ferme la fenêtre sans rien changer. Une fois terminé, le chantier est **verrouillé** en lecture seule.

Le même bouton existe dans la page *Journée* et sur la page du chantier. Les acomptes et les montants partiels se saisissent sur la page du
chantier (« + Ajouter un paiement »).

### Heures calculées

- la première intervention commence à **7 h 30** ;
- une **pause dîner fixe de 12 h 00 à 12 h 30** est intégrée : un chantier qui chevauche midi est prolongé de 30 minutes
  (« dîner inclus »), et un chantier qui se terminerait à 12 h 00 pile est suivi d'une ligne « Dîner » ;
- chaque heure de fin vient de la **durée estimée** du chantier. Les trajets ne sont pas comptés (étape 2).

Exemple : 2 h, 2 h, 1 h, 1 h 30 : 7 h 30 à 9 h 30, 9 h 30 à 11 h 30, 11 h 30 à **13 h 00** (dîner inclus), 13 h 00 à 14 h 30.

## 2. Journée : créer et gérer une journée complète

Menu **Journée** : on choisit la date (Précédent, Suivant, calendrier, « Demain »). On y voit le même déroulement que sur le tableau de bord, avec
en plus :

| Action | Ce qu'elle fait |
|---|---|
| **Flèche vers le haut / vers le bas** | déplace un chantier dans l'ordre de passage (une flèche seulement, sans texte) ; toutes les heures sont recalculées aussitôt |
| **Terminer** | ouvre la fenêtre de confirmation (payé ou pas) |
| **Retirer** | remet le chantier dans « À planifier » |

**Le temps et le prix d'un travail ne se modifient jamais ici** : ce sont ceux du chantier (page du chantier, « Durée estimée »).

En dessous, les **chantiers à placer** : filtres statut (À planifier / Planifiés un autre jour pour les déplacer),
**délai d'attente**, **secteur**, tri. Chaque ligne montre le délai d'attente, le travail, son **temps**, ses options et sa **valeur à droite**. On **coche**
des chantiers (le total d'heures **et de dollars** de la journée se met à jour en direct), puis **Ajouter à la journée** : ils sont ajoutés
**à la fin**, dans l'ordre affiché, et deviennent « Planifié ». Un chantier sans durée estimée ne peut pas être coché : un lien mène à sa page pour la
saisir. Tout est planifié d'un coup, ou rien. **Une soumission n'apparaît jamais ici** : elle doit d'abord être acceptée. L'ordre optimal et le trajet sur la carte viendront avec l'étape 2.

## 3. Chantiers et archives

Menu **Chantiers** : une seule page, qui ne contient **que des chantiers acceptés**.

- **En haut : les raccourcis** (pastilles que tu choisis : voir plus bas), puis la recherche (nom sans accent, téléphone, adresse, secteur) et les
  filtres statut / paiement / **secteur**.
- **Les chantiers actifs**, classés du plus récent au plus ancien d'après leur **date d'attente** (pour un chantier : depuis son **acceptation**), avec le
  **délai d'attente** des chantiers « À planifier » (pastille verte moins de 7 jours, jaune 7 à 30, rouge plus de 30), le temps, le statut, le paiement
  et le **montant à droite** (écran minimal : ni nacelle ni bois affichés ici).
- **Plus bas : « Archives »** : les chantiers **annulés** et les chantiers **terminés et payés**. Ils y vont **automatiquement**, sans rien cliquer.
  Les 50 plus récents s'affichent ; la recherche couvre tout. Un lien « Archives (N) » en haut de page y descend.

Seuils d'attente : `SEUIL_SURVEILLER` et `SEUIL_URGENT` dans `outils/noyau.py`.

## 4. Soumissions

Menu **Soumissions** (à droite de Chantiers ; sur téléphone, dans la barre du bas). C'est ici que vit une demande, **du premier appel du client
jusqu'à sa réponse**.

### Ouvrir une soumission : rien n'est obligatoire

Un client appelle et demande qu'on vienne faire une soumission : on **ouvre une soumission**. Boutons **+ Nouvelle soumission** (en haut de la page
Soumissions, et sur la fiche d'un client déjà connu), **+ Nouveau client** (page Clients) et « + Soumission » (barre du bas du téléphone) : les trois
ouvrent le même formulaire. Il ne demande **rien d'obligatoire** : on remplit ce qu'on sait (on peut même ouvrir une soumission vide et la remplir
plus tard, après la visite). Une soumission sans nom s'affiche « (client à identifier) ».

Le formulaire reprend l'essentiel : client (nom, prénom, téléphone, adresse, ville / secteur), types de travaux (avec précisions), options du
travail (**nacelle**, **débarrasser le bois** ou **format du bois laissé sur place : 16 pouces / 4 pieds**), durée estimée, prix, description.
Tout le reste est dans **« Paramètres avancés »** (replié) : entreprise, courriel, code postal, accès, GPS, date de la demande, TPS/TVQ saisies à la
main, mode de règlement. **Après la création, on revient à la fiche du client.** Le programme note aussi **qui a ouvert la soumission** (le nom du compte).

### La liste

Les soumissions en cours, **la plus récente en haut** ; chaque ligne montre la date de la demande avec la **pastille d'attente** (verte moins de
7 jours, jaune 7 à 30, rouge plus de 30) et « par » le compte qui l'a ouverte, le client, l'adresse, les travaux, le montant, et **ce qui manque encore
pour l'accepter** (en rouge). À droite : les deux **boutons rapides Accepter et Refuser**.

Au-dessus : les **raccourcis** (par défaut « Mes soumissions » et « À relancer (7 jours et plus) »), une recherche (nom, téléphone, adresse,
travaux), un filtre par **délai** et un filtre « **ouvertes par** ». En bas : la section **Refusées**.

### Accepter : le programme vérifie

Le bouton **Accepter** place la soumission dans **Chantiers, À planifier**, **mais seulement si tout ce qu'il faut est rempli**. Les conditions :

| Condition | Précision |
|---|---|
| le **nom** du client | ou le nom d'une **entreprise** |
| un **téléphone** | |
| l'**adresse** des travaux | |
| le **secteur** (ville) | liste des secteurs desservis |
| au moins un **type de travaux** | |
| **ce qu'on fait du bois** | seulement pour un **abattage** ou un **élagage** : le débarrasser, ou préciser son format (16 pouces / 4 pieds) |
| la **durée estimée** | elle sert à calculer les heures de la journée |
| le **prix** | 0 $ est un prix (travail gratuit) |

Si tout est là : la soumission devient un chantier « À planifier ». Sinon, le programme **ouvre la page « Accepter la soumission »**, qui ne montre que
**les champs manquants** : le soumissionneur les remplit, puis **Enregistrer et accepter**. Ce qui a été saisi est **gardé** même si tout n'est pas
complété (la page redemande seulement le reste). Ce que le client a déjà dans sa fiche n'est jamais écrasé. Aucune de ces vérifications n'est
demandée tant qu'on ne cherche pas à accepter.

### Refuser, rouvrir, remettre en soumission

- **Refuser** (après confirmation) : la soumission va dans la section **Refusées** en bas de la page Soumissions. Elle n'est **pas supprimée** (on garde
  la trace) et n'apparaît nulle part ailleurs. Une soumission refusée est en lecture seule ; **Rouvrir** la remet en cours. L'administrateur peut la
  supprimer (« Paramètres avancés »).
- Depuis la **liste**, les deux boutons ramènent à la liste. Depuis la **page de la fiche**, **Accepter** t'amène sur le **nouveau chantier** et **Refuser**
  reste sur la fiche, où le bouton **Rouvrir** est tout de suite là en cas d'erreur de clic.
- **Remettre en soumission** : sur la page d'un chantier « À planifier » (accepté par erreur, ou le client veut revoir le prix) : il retourne dans Soumissions.
  Un chantier déjà placé dans une journée doit d'abord en être **retiré**.
- Le **délai d'attente** d'une soumission part de la date de la demande ; une fois acceptée, celui du chantier part de **l'acceptation**.
- **Dupliquer** (page d'une soumission ou d'un chantier) : nouvelle soumission pour le même client, d'après la fiche (voir les règles plus bas).

## 5. Raccourcis : les pastilles du haut

En haut des pages **Chantiers** et **Soumissions**, des **pastilles** : un nombre et un nom (par exemple « 2 · À recevoir · 3 466,64 $ », « 1 · Planifiés »).
Un clic **applique le filtre** ; un second clic sur la pastille active le **retire**. Chaque pastille compte les fiches qui correspondent
(et le montant à recevoir pour les raccourcis de paiement).

Le lien **Modifier les raccourcis** (à côté des pastilles) ouvre la page de réglage :

- **Mes raccourcis** : la liste, avec les flèches pour **monter / descendre** et le bouton **Retirer** (on peut tout retirer : les raccourcis de départ ne
  reviennent pas tout seuls) ;
- **Ajouter un raccourci proposé** : « Terminés », « Payés en partie », « Prix manquants », « À planifier depuis 7 jours et plus »... ;
- **Créer un raccourci personnalisé** : on combine un **statut**, un **paiement**, un **secteur**, un **délai d'attente** et un **texte contenu**, avec un nom
  (facultatif : sinon le nom décrit les critères) ;
- **Rétablir ceux du départ**.

**Chaque personne garde ses raccourcis** (par compte ; sans comptes, ils sont communs). Au départ : l'administrateur voit « À recevoir », « Planifiés » et
« À planifier » ; le compte Soumission voit « À planifier » et « Planifiés ». **Les raccourcis qui touchent aux paiements sont réservés à l'administrateur**
(le compte Soumission ne les voit pas et ne peut pas en créer). Sur la page Soumissions : « Mes soumissions » (celles que **j'ai ouvertes**, seulement avec
des comptes) et « À relancer (7 jours et plus) ».

## 6. Créer une soumission, voir une fiche : l'essentiel d'abord

**Après l'enregistrement d'une modification**, on reste sur la fiche. **Fermer** ramène à la liste de son genre (Soumissions ou Chantiers).

La **page d'une soumission** montre, de haut en bas :

1. le résumé : client, étiquette « Soumission », travaux, date de la demande, qui l'a ouverte, et **la valeur à droite** ;
2. les **boutons Accepter, Refuser, Dupliquer**, et en rouge ce qu'il **manque encore pour accepter** ;
3. le client en **lecture seule** (avec « Modifier le client » et « Fiche client ») ;
4. les champs à modifier : travaux, options, durée estimée, prix, description (rien d'obligatoire) ;
5. **« Paramètres avancés »** (replié) : date de la demande, taxes, mode de règlement, fichiers, autres fiches du client, suppression (administrateur).

La **page d'un chantier** (accepté) ajoute les **paiements** (administrateur : liste, « + Ajouter un paiement ») et les boutons **Terminer** (chantier
planifié), **Remettre en soumission** (chantier « À planifier »), **Rouvrir** (chantier annulé) et **Dupliquer**. Un chantier **Terminé** n'a pas de
formulaire : résumé, client et paiements en clair ; le détail complet est dans « Paramètres avancés ».

## 7. Clients

`Clients` : une liste épurée avec **seulement Nom, Téléphone et Adresse** (le secteur est écrit sous l'adresse), filtrable par **secteur**. La fiche
d'un client montre ses coordonnées et **toutes ses fiches : soumissions et chantiers** (date, travaux, statut ; un clic mène à la bonne page).
**+ Nouvelle soumission** ouvre un formulaire réduit à l'essentiel : travaux avec précisions, options, durée, prix, notes ; la **date de la demande**
(aujourd'hui) et le **mode de règlement** sont dans « Paramètres avancés ». Après l'enregistrement, on revient à la fiche du client.

Un client dont on ne sait presque rien (soumission vide) s'affiche « (client à identifier) », avec « à saisir » à la place de l'adresse et du secteur.

**Supprimer un client** : toujours possible. Au bas de sa fiche, le bouton « Supprimer le client » demande une confirmation (qui indique ce qui va disparaître : nombre de soumissions, de chantiers, dont terminés, et de paiements) puis efface le client **et tout ce qui le concerne** : toutes ses fiches (soumissions, chantiers actifs, annulés, terminés, archivés), leurs types de travaux et leurs paiements. Il n'en reste aucune trace, même dans les archives. C'est **définitif** (aucun retour en arrière ; la copie de sauvegarde du jour reste dans `data/sauvegardes`). Le verrou « Terminé » protège toujours un chantier pris seul (il n'a pas de bouton Supprimer) : seule la suppression du client le contourne, volontairement.

**Le client n'est modifiable qu'à un seul endroit : sa fiche** (bouton *Modifier le client*, même principe : l'essentiel d'abord, le reste dans
« Paramètres avancés »). Partout ailleurs son nom, son adresse et ses coordonnées sont **affichés en lecture seule** : le serveur relit
toujours le client dans la base et ignore tout ce que le navigateur enverrait. Depuis la page d'une soumission, « Modifier le client » **ramène à la
soumission** une fois la fiche enregistrée.

**Qu'est-ce qui est obligatoire ?** Tant qu'un client n'a que des **soumissions**, rien (ni nom, ni adresse, ni secteur). Dès qu'il a au moins un **chantier**
(une soumission acceptée), son **nom (ou entreprise), son adresse et son secteur** le sont, comme avant.

### Ville / secteur : une liste déroulante, jamais de texte libre

Chaque client a un **secteur**, choisi dans une **liste fermée** (obligatoire pour accepter une soumission). La **ville inscrite sur
l'adresse** (pour Google Maps) **vient du secteur** choisi : plus de « Trois Rivieres », « Trois-Riviere »... Un même secteur s'écrit toujours pareil, ce
qui permet de **classer et filtrer** par secteur (clients, soumissions, chantiers, Journée).

La liste de départ est celle de la région de Trois-Rivières (Centre-ville, Trois-Rivières-Ouest, Cap-de-la-Madeleine, Sainte-Marthe-du-Cap,
Pointe-du-Lac, Saint-Louis-de-France, Bécancour, Champlain, Yamachiche, Saint-Étienne-des-Grès, Shawinigan, Louiseville, Nicolet) : **à adapter
aux secteurs réellement desservis** dans la page **Secteurs** (lien au bas de la liste des clients) : ajouter, renommer, supprimer un secteur
inutilisé. Un nom déjà présent (à l'accent, au tiret ou à la casse près) est refusé : pas de doublons.

## 8. Règles d'une fiche

- **Date de la demande** : préremplie avec aujourd'hui (modifiable). Pour une soumission, c'est le début du **délai d'attente**.
- **Mode de règlement** : un seul choix parmi Comptant, Chèque, Interac, Carte, Autre.
- **Jamais de solde négatif** : un paiement (ou un acompte) ne peut pas dépasser ce qu'il reste à payer ; le formulaire indique « au plus ... $ ».
- **Durée estimée** : facultative pour une soumission, **obligatoire pour l'accepter** (et pour planifier). La **durée réelle** n'apparaît pas à la
  création ; quand le chantier est terminé, elle reprend la durée estimée (modifiable dans la fenêtre « Terminer »).
- **Terminé = verrouillé et facturé** : lecture seule, impossible à rouvrir, modifier ou supprimer. Restent possibles : encaisser, dupliquer.
  (Une erreur de saisie sur un chantier terminé se corrige donc en amont : relis avant de terminer.)
- **Archives** : un chantier **annulé**, ou **terminé et payé**, quitte la liste active et va dans les archives (bas de la page *Chantiers*). Une
  soumission **refusée** n'est pas dans ces archives : elle est dans « Refusées » (bas de la page *Soumissions*).
- **Dupliquer** (page d'une soumission ou d'un chantier) : nouvelle **soumission** pour le même client (travaux, options, durée, prix, mode repris ; dates
  repartent d'aujourd'hui ; prix et durée ajustables), pratique pour un travail récurrent.
- **Une même personne ne voit que ce que son rôle permet** : le compte « Soumission » n'a ni finances, ni Journée, ni suppression (voir
  `docs/acces_a_distance.md`).
