# Tableau de bord, Journée, Chantiers et clients

Principe : **simple par défaut**. Chaque écran montre d'abord l'important ; les options rarement utiles sont dans « Paramètres
avancés » (repliés). Chaque chose a **un seul endroit** :

| Section | Rôle |
|---|---|
| **Tableau de bord** | *voir* : le calendrier et le déroulement de la journée choisie (lecture seule) |
| **Journée** | *gérer une journée* : y placer des chantiers, ordre, statut, encaissement, retrait |
| **Chantiers** | *gérer les jobs* : liste des chantiers actifs ; **plus bas, les archives** (anciens chantiers) |
| **Clients** | les fiches clients (seul endroit où l'on modifie un client) |

Il n'y a plus de section « Suivi » ni « Tournées » (les anciens liens redirigent vers *Journée* et *Chantiers*) ni d'entrée
« Archives » dans le menu.

## Les statuts d'un chantier

| # | Statut | Signification |
|---|---|---|
| 1 | **Soumission** | estimé à donner ou en préparation |
| 2 | **En attente** | soumission remise, on attend la réponse du client |
| 3 | **À planifier** | accepté, pas encore de date |
| 4 | **Planifié** | date fixée, place dans une journée |
| 5 | **Terminé** | travaux faits (puis verrouillé) |
| 6 | **Annulé** | abandonné (refus du client, annulation…) |

Il n'y a pas de statut « Refusé » : un client qui refuse = *Annulé*. Les anciens « Accepté » deviennent « À planifier » (la migration le fait toute seule).

## 1. Tableau de bord : voir la journée

La page d'accueil sert à **visualiser**, pas à modifier. Un **calendrier du mois** : chaque jour planifié indique le nombre de chantiers
et les heures prévues ; un jour de plus de 8 h est en rouge, un jour passé avec des chantiers encore « Planifiés » est signalé « à clôturer ».

**Un clic sur une date** affiche, juste en dessous, la journée :

- les **chantiers dans l'ordre de passage**, avec leurs **heures de début → fin** et le **temps de chacun** (⏱) ;
- la **durée totale** de la journée et, juste dessous, le **montant total** de la journée (taxes incluses) ;
- à **droite de chaque chantier, sa valeur** (total taxes incluses, prix avant taxes en petit) pour juger d'un coup d'œil la rentabilité ;
- le **statut** et l'**état des paiements** (reçu, solde) de chaque chantier — **visibles, sans formulaire**.

Rien d'autre ne se modifie ici : ni statut, ni durée, ni ordre. Seule action : **Retirer** un chantier de la journée (il redevient
« À planifier »). Le bouton **Gérer cette journée** ouvre la page *Journée* sur la même date.

### Heures calculées

- la première intervention commence à **7 h 30** ;
- une **pause dîner fixe de 12 h 00 à 12 h 30** est intégrée : un chantier qui chevauche midi est prolongé de 30 minutes
  (« dîner inclus »), et un chantier qui se terminerait à 12 h 00 pile est suivi d'une ligne « Dîner » ;
- chaque heure de fin vient de la **durée estimée** du chantier. Les trajets ne sont pas comptés (étape 2). Un chantier sans
  durée est signalé : les heures sont alors approximatives.

Exemple : 2 h, 2 h, 1 h, 1 h 30 → 7 h 30-9 h 30, 9 h 30-11 h 30, 11 h 30-**13 h 00** (dîner inclus), 13 h 00-14 h 30.

## 2. Journée : créer et gérer une journée complète

Menu **Journée** : on choisit la date (◀ ▶, calendrier, « Demain »). On y voit le même déroulement que sur le tableau de bord, avec les outils :

| Action | Ce qu'elle fait |
|---|---|
| **▲ / ▼** | monte ou descend un chantier ; toutes les heures sont recalculées aussitôt |
| **Statut** + OK | change le statut (« À planifier », « En attente » et « Soumission » retirent le chantier de la journée) |
| **Encaisser** | enregistre un paiement (montant proposé = le solde ; mode proposé d'après le mode de règlement prévu) |
| **Retirer** | remet le chantier dans « À planifier » |

**Le temps et le prix d'un travail ne se modifient jamais ici** : ce sont ceux du chantier (page du chantier, « Durée estimée »).

En dessous, les **chantiers à placer** : filtres statut (À planifier / En attente / Soumissions / Planifiés un autre jour pour les déplacer),
**délai d'attente**, **secteur**, tri. Chaque ligne montre le délai d'attente, le travail, son **temps** et sa **valeur à droite**. On **coche**
des chantiers (le total d'heures **et de dollars** de la journée se met à jour en direct), puis **Ajouter à la journée** : ils sont ajoutés
**à la fin**, dans l'ordre affiché. Un chantier sans durée estimée ne peut pas être coché : un lien mène à sa page pour la saisir.
Tout est planifié d'un coup, ou rien.

### Encaissement sur un chantier « Planifié » : confirmation

Quand tu encaisses un paiement sur un chantier **Planifié**, le paiement est enregistré, puis une fenêtre demande :

> Voulez-vous passer ce chantier au statut "Terminé" ?  —  **Oui, passer à Terminé** / **Non, laisser Planifié**

La **durée réelle** y est préremplie avec la durée estimée. « Oui » change le statut ; « Non » ferme la fenêtre. Elle n'apparaît **pas** pour un
chantier déjà Terminé ou À planifier. Elle fonctionne partout où l'on encaisse : Journée et page du chantier.

L'ordre optimal et le trajet sur la carte viendront avec l'étape 2.

## 3. Chantiers et archives

Menu **Chantiers** : une seule page.

- **En haut : les chantiers actifs**, avec le **délai d'attente** des soumissions / en attente / à planifier (pastille verte < 7 jours,
  jaune 7 à 30, rouge > 30), le temps, le statut, le paiement et le **montant à droite**. Des raccourcis : à facturer, à recevoir, planifiés,
  prix manquants ; une recherche (nom sans accent, téléphone, adresse) et des filtres statut / paiement.
- **Plus bas : « 📦 Archives »** : les anciens chantiers, c'est-à-dire **terminés et payés** (ils y vont **automatiquement**, sans rien cliquer).
  Les 50 plus récents s'affichent ; la recherche couvre tout. Un lien « Archives (N) ↓ » en haut de page y descend.

Seuils d'attente : `SEUIL_SURVEILLER` et `SEUIL_URGENT` dans `outils/noyau.py`.

## 4. Créer un chantier, voir un chantier : l'essentiel d'abord

**+ Nouveau** (client neuf) : le formulaire ne demande que l'essentiel — **nom, prénom, téléphone, adresse, ville ; types de travaux
(avec précisions), durée estimée (obligatoire), prix, description**. Tout le reste est dans **« Paramètres avancés »** (replié) : entreprise,
courriel, code postal, accès, GPS, statut, dates, TPS/TVQ saisies à la main, mode de règlement, facture, paiement déjà reçu, fichiers.
Les champs repliés sont envoyés avec le formulaire (valeurs par défaut : statut Soumission, date de la demande = aujourd'hui) ; une erreur
dans un champ avancé ouvre automatiquement la section.

**Après la création**, on arrive sur la **page du chantier**, pensée pour une consultation rapide (90 % des cas) :

1. le résumé : client, statut, travaux, date et durée, et **la valeur à droite** (total, reçu, solde) ;
2. le client en **lecture seule** (🔒) ;
3. les **paiements** (liste ; « + Ajouter un paiement » à un clic) ;
4. les champs essentiels à modifier : travaux, statut, date des travaux, durée estimée, prix, description ;
5. **« Paramètres avancés »** (replié) : date de la demande, durée réelle, taxes, mode de règlement, facture, fichiers, autres chantiers du client,
   suppression.

Un chantier **Terminé** n'a pas de formulaire : résumé, client, facturation et paiements en clair ; le détail complet est dans « Paramètres avancés ».

## 5. Clients

`Clients` : une liste épurée avec **seulement Nom, Téléphone et Adresse**. La fiche d'un client montre ses coordonnées et l'historique de ses
chantiers (date, travaux, statut — sans montants). **+ Nouveau chantier** ouvre un formulaire réduit à l'essentiel : travaux avec précisions,
**durée estimée (obligatoire)**, prix, notes ; la **date de la demande** (aujourd'hui) et le **mode de règlement** sont dans « Paramètres
avancés ». Le chantier est créé « À planifier ».

**Le client n'est modifiable qu'à un seul endroit : sa fiche** (bouton *Modifier le client*, même principe : l'essentiel d'abord, le reste dans
« Paramètres avancés »). Partout ailleurs son nom, son adresse et ses coordonnées sont **affichés en lecture seule** (🔒) : le serveur relit
toujours le client dans la base et ignore tout ce que le navigateur enverrait.

## 6. Règles d'un chantier

- **Date de la demande** : préremplie avec aujourd'hui (modifiable).
- **Mode de règlement** : un seul choix parmi Comptant, Chèque, Interac, Carte, Autre.
- **Jamais de solde négatif** : un paiement (ou un acompte) ne peut pas dépasser ce qu'il reste à payer ; le formulaire indique « au plus … $ ».
- **Durée estimée obligatoire** à la création, à l'import et à la planification. La **durée réelle** n'apparaît pas à la création ;
  quand le chantier passe à **Terminé**, elle est préremplie avec la durée estimée (modifiable dans la fenêtre de confirmation).
- **Terminé = verrouillé** : lecture seule, impossible à rouvrir, modifier ou supprimer. Restent possibles : facturer, encaisser, dupliquer.
  (Une erreur de saisie sur un chantier terminé se corrige donc en amont : relis avant de passer à « Terminé ».)
- **Archives** : un chantier **Terminé et payé** quitte la liste *Chantiers* et va dans *Archives*, automatiquement.
- **Dupliquer le chantier** (page d'un chantier) : nouvelle soumission pour le même client (travaux, durée, prix, mode repris ; dates
  repartent d'aujourd'hui ; prix et durée ajustables).

