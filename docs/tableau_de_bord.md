# Tableau de bord, Journée, Chantiers et clients

Principe : **simple par défaut**. Chaque écran montre d'abord l'important ; les options rarement utiles sont dans « Paramètres
avancés » (repliés). Chaque chose a **un seul endroit** :

| Section | Rôle |
|---|---|
| **Tableau de bord** | voir le calendrier et le déroulement de la journée choisie ; terminer un chantier |
| **Journée** | créer et gérer une journée complète : placer des chantiers, ordre, terminer, retirer, annuler |
| **Chantiers** | gérer les jobs : liste des chantiers actifs ; plus bas, les archives (anciens chantiers) |
| **Clients** | les fiches clients (seul endroit où l'on modifie un client) et la liste des secteurs desservis |

L'interface ne contient **aucun emoji**.

## Les statuts d'un chantier : automatiques

| Statut | Signification |
|---|---|
| **Soumission** | estimé à donner ou en préparation |
| **En attente** | soumission remise, on attend la réponse du client |
| **À planifier** | accepté, pas encore de date |
| **Planifié** | placé dans une journée |
| **Terminé** | travaux faits (puis verrouillé) |
| **Annulé** | abandonné (refus du client, annulation) |

**Le statut ne se choisit jamais à la main dans la Journée ni sur le tableau de bord, et il n'y est même pas affiché.** Il suit ce qu'on fait :

| Action | Statut qui en résulte |
|---|---|
| Ajouter le chantier à une journée (page *Journée*) | **Planifié** |
| **Retirer** le chantier de la journée | retour à **À planifier** |
| **Annuler** le chantier | **Annulé** : il disparaît de la journée et va **automatiquement dans les archives** |
| **Terminer** le chantier (bouton, puis confirmation) | **Terminé** (verrouillé) |

L'annulation d'un chantier se fait sur sa page (« Paramètres avancés », « Annuler le chantier »). Seuls les statuts d'**avant** la planification se choisissent, sur la page du chantier : *Soumission, En attente, À planifier*.
Un chantier annulé par erreur se **rouvre** (bouton sur sa page) : il redevient « À planifier ».

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
adresse complète et secteur, accès et notes, travaux avec leurs précisions, description, options (nacelle, bois), durées, prix avant taxes, TPS/TVQ,
total, mode de règlement prévu, paiements déjà reçus et **reste à encaisser**, références du dossier papier, et les **photos** du dossier de photos
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

En dessous, les **chantiers à placer** : filtres statut (À planifier / En attente / Soumissions / Planifiés un autre jour pour les déplacer),
**délai d'attente**, **secteur**, tri. Chaque ligne montre le délai d'attente, le travail, son **temps**, ses options et sa **valeur à droite**. On **coche**
des chantiers (le total d'heures **et de dollars** de la journée se met à jour en direct), puis **Ajouter à la journée** : ils sont ajoutés
**à la fin**, dans l'ordre affiché, et deviennent « Planifié ». Un chantier sans durée estimée ne peut pas être coché : un lien mène à sa page pour la
saisir. Tout est planifié d'un coup, ou rien. L'ordre optimal et le trajet sur la carte viendront avec l'étape 2.

## 3. Chantiers et archives

Menu **Chantiers** : une seule page.

- **En haut : les chantiers actifs**, classés par **date de la demande / soumission** (c'est la date principale ; la date planifiée n'est
  qu'une mention « prévu le … »), avec le **délai d'attente** des soumissions / en attente / à planifier (pastille verte moins de 7 jours,
  jaune 7 à 30, rouge plus de 30), le temps, le statut, le paiement et le **montant à droite** (écran minimal : ni nacelle ni bois affichés ici). Des raccourcis : à recevoir, planifiés,
  prix manquants ; une recherche (nom sans accent, téléphone, adresse, secteur) et des filtres statut / paiement / **secteur**.
- **Plus bas : « Archives »** : les chantiers **annulés** et les chantiers **terminés et payés**. Ils y vont **automatiquement**, sans rien cliquer.
  Les 50 plus récents s'affichent ; la recherche couvre tout. Un lien « Archives (N) » en haut de page y descend.

Seuils d'attente : `SEUIL_SURVEILLER` et `SEUIL_URGENT` dans `outils/noyau.py`.

## 4. Créer un chantier, voir un chantier : l'essentiel d'abord

**+ Nouveau** (client neuf) : le formulaire ne demande que l'essentiel : **nom, prénom, téléphone, adresse, ville / secteur (liste) ;
types de travaux (avec précisions), options du travail, durée estimée (obligatoire), prix, description**. Les **options du travail sont toujours
visibles** (elles servent à préparer la job) :

- **Nacelle requise** : oui / non ;
- **Débarrasser le bois** : si la case est cochée, rien d'autre. Sinon, pour un **abattage ou un élagage**, on précise le format du bois laissé sur
  place : **16 pouces** ou **4 pieds** (obligatoire pour ces deux types).

Tout le reste est dans **« Paramètres avancés »** (replié) : entreprise, courriel, code postal, accès, GPS, statut de départ (Soumission / En attente /
À planifier), date de la demande, TPS/TVQ saisies à la main, mode de règlement, paiement déjà reçu, fichiers. Les champs repliés sont envoyés avec le
formulaire (valeurs par défaut : statut Soumission, date de la demande = aujourd'hui) ; une erreur dans un champ avancé ouvre automatiquement la section.
Un chantier ne se planifie pas à la création : on l'ajoute ensuite à une journée.

**Après la création**, on arrive sur la **page du chantier**, pensée pour une consultation rapide :

1. le résumé : client, statut, travaux, date et durée (sans les pastilles nacelle / bois : les cases sont dans le formulaire), et **la valeur à droite** (total, reçu, solde) ;
2. le client en **lecture seule** ;
3. les **paiements** (liste ; « + Ajouter un paiement » à un clic) ;
4. les champs essentiels à modifier : travaux, options, durée estimée, prix, description ; le **statut** (à choisir seulement avant la planification)
   et la **date des travaux** sont **affichés** (« géré automatiquement », « se change dans la page Journée ») ;
5. **« Paramètres avancés »** (replié) : date de la demande, durée réelle, taxes, mode de règlement, fichiers, autres chantiers du client,
   **annuler** ou supprimer le chantier.

Boutons : **Terminer** (chantier planifié), **Rouvrir** (chantier annulé), **Dupliquer**.
Un chantier **Terminé** n'a pas de formulaire : résumé, client et paiements en clair ; le détail complet est dans « Paramètres avancés ».

## 5. Clients

`Clients` : une liste épurée avec **seulement Nom, Téléphone et Adresse** (le secteur est écrit sous l'adresse), filtrable par **secteur**. La fiche
d'un client montre ses coordonnées et l'historique de ses chantiers (date, travaux, statut, sans montants). **+ Nouveau chantier** ouvre un
formulaire réduit à l'essentiel : travaux avec précisions, options, **durée estimée (obligatoire)**, prix, notes ; la **date de la demande**
(aujourd'hui) et le **mode de règlement** sont dans « Paramètres avancés ». Le chantier est créé « À planifier ».

**Supprimer un client** : toujours possible. Au bas de sa fiche, le bouton « Supprimer le client » demande une confirmation (qui indique ce qui va disparaître : nombre de chantiers, dont terminés, et de paiements) puis efface le client **et tout ce qui le concerne** : tous ses chantiers (actifs, annulés, terminés, archivés), leurs types de travaux et leurs paiements. Il n'en reste aucune trace, même dans les archives. C'est **définitif** (aucun retour en arrière ; la copie de sauvegarde du jour reste dans `data/sauvegardes`). Le verrou « Terminé » protège toujours un chantier pris seul (il n'a pas de bouton Supprimer) : seule la suppression du client le contourne, volontairement.

**Le client n'est modifiable qu'à un seul endroit : sa fiche** (bouton *Modifier le client*, même principe : l'essentiel d'abord, le reste dans
« Paramètres avancés »). Partout ailleurs son nom, son adresse et ses coordonnées sont **affichés en lecture seule** : le serveur relit
toujours le client dans la base et ignore tout ce que le navigateur enverrait.

### Ville / secteur : une liste déroulante, jamais de texte libre

Chaque client a un **secteur**, choisi dans une **liste fermée** (obligatoire à la création et à la modification d'un client). La **ville inscrite sur
l'adresse** (pour Google Maps) **vient du secteur** choisi : plus de « Trois Rivieres », « Trois-Riviere »... Un même secteur s'écrit toujours pareil, ce
qui permet de **classer et filtrer** par secteur (clients, chantiers, Journée).

La liste de départ est celle de la région de Trois-Rivières (Centre-ville, Trois-Rivières-Ouest, Cap-de-la-Madeleine, Sainte-Marthe-du-Cap,
Pointe-du-Lac, Saint-Louis-de-France, Bécancour, Champlain, Yamachiche, Saint-Étienne-des-Grès, Shawinigan, Louiseville, Nicolet) : **à adapter
aux secteurs réellement desservis** dans la page **Secteurs** (lien au bas de la liste des clients) : ajouter, renommer, supprimer un secteur
inutilisé. Un nom déjà présent (à l'accent, au tiret ou à la casse près) est refusé : pas de doublons.

## 6. Règles d'un chantier

- **Date de la demande** : préremplie avec aujourd'hui (modifiable). C'est la date principale du chantier.
- **Mode de règlement** : un seul choix parmi Comptant, Chèque, Interac, Carte, Autre.
- **Jamais de solde négatif** : un paiement (ou un acompte) ne peut pas dépasser ce qu'il reste à payer ; le formulaire indique « au plus ... $ ».
- **Durée estimée obligatoire** à la création et à la planification. La **durée réelle** n'apparaît pas à la création ; quand le chantier est terminé,
  elle reprend la durée estimée (modifiable dans la fenêtre « Terminer »).
- **Terminé = verrouillé et facturé** : lecture seule, impossible à rouvrir, modifier ou supprimer. Restent possibles : encaisser, dupliquer.
  (Une erreur de saisie sur un chantier terminé se corrige donc en amont : relis avant de terminer.)
- **Archives** : un chantier **annulé**, ou **terminé et payé**, quitte la liste active et va dans les archives (bas de la page *Chantiers*).
- **Dupliquer le chantier** (page d'un chantier) : nouvelle soumission pour le même client (travaux, options, durée, prix, mode repris ; dates
  repartent d'aujourd'hui ; prix et durée ajustables).
