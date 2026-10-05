# Calendrier, journée, suivi, tournées et fiche client

## Les statuts d'un chantier

Liste officielle, dans l'ordre du parcours :

| # | Statut | Signification |
|---|---|---|
| 1 | **Soumission** | estimé à donner ou en préparation |
| 2 | **En attente** | soumission remise, on attend la réponse du client |
| 3 | **À planifier** | accepté, pas encore de date |
| 4 | **Planifié** | date fixée, place dans une journée |
| 5 | **Terminé** | travaux faits |
| 6 | **Annulé** | abandonné (refus du client, annulation…) |

Il n'y a plus de statut « Refusé » : un client qui refuse = *Annulé*. Les anciens « Accepté » deviennent « À planifier »
(la migration le fait toute seule).

## 1. Le tableau de bord : un calendrier

La page d'accueil montre un **calendrier du mois**. Chaque jour planifié indique le nombre de chantiers et les heures
prévues ; un jour de plus de 8 h est en rouge, un jour passé avec des chantiers encore « Planifiés » est signalé
« à clôturer ». Au-dessus, des pastilles mènent aux files d'attente (À planifier, En attente, À facturer, À recevoir) avec
le nombre d'urgents.

**Un clic sur une date** affiche le **déroulement de la journée**, juste en dessous, sans changer de page.

### Déroulement d'une journée

Les chantiers sont dans leur **ordre de passage**, avec leurs **heures de début et de fin calculées automatiquement** :

- la première intervention commence à **7 h 30** ;
- une **pause dîner fixe de 12 h 00 à 12 h 30** est intégrée : un chantier qui chevauche midi est prolongé de 30 minutes
  (« dîner inclus »), et un chantier qui se terminerait à 12 h 00 pile est suivi d'une ligne « Dîner » ;
- chaque heure de fin vient de la **durée estimée** du chantier. Les trajets ne sont pas comptés (étape 2). Un chantier sans
  durée est signalé : les heures sont alors approximatives.

Exemple : 2 h, 2 h, 1 h, 1 h 30 → 7 h 30-9 h 30, 9 h 30-11 h 30, 11 h 30-**13 h 00** (dîner inclus), 13 h 00-14 h 30.

**Réorganiser** : les boutons **▲ / ▼** montent ou descendent un chantier ; toutes les heures sont recalculées aussitôt. La
flèche est grisée au début et à la fin de la liste. (Le glisser-déposer n'est pas offert : les flèches suffisent et fonctionnent
partout, y compris sur tablette.)

**Sans quitter la journée** :

| Action | Ce qu'elle fait |
|---|---|
| **Statut** + durée + OK | change le statut ; la durée modifiée recalcule les heures. « À planifier », « En attente » et « Soumission » retirent le chantier de la journée. « Terminé » le garde dans la journée. |
| **Encaisser** | enregistre un paiement (montant proposé = le solde, mode proposé d'après la modalité de paiement). Un montant plus petit = acompte. |
| **Retirer** | remet le chantier dans « À planifier ». |

### Encaissement sur un chantier « Planifié » : confirmation

Quand tu encaisses un paiement sur un chantier **Planifié**, le paiement est enregistré, puis une fenêtre demande :

> Voulez-vous passer ce chantier au statut "Terminé" ?  —  **Oui, passer à Terminé** / **Non, laisser Planifié**

« Oui » change le statut ; « Non » ferme la fenêtre. Elle n'apparaît **pas** pour un chantier déjà Terminé ou À planifier.
Elle fonctionne partout où l'on encaisse : calendrier, suivi, tournées et page du chantier.

## 2. Suivi (files d'attente)

Menu **Suivi** (ou les pastilles de l'accueil) : une liste par statut — À planifier, En attente, Soumissions, Planifiés, À facturer,
À recevoir — avec le **délai d'attente** (nombre de jours depuis la demande ou la soumission, à défaut depuis la création de la
fiche) :

| Délai | Priorité | Affichage |
|---|---|---|
| moins de 7 jours | normale | pastille verte |
| 7 à 30 jours | à surveiller | pastille jaune, barre jaune |
| plus de 30 jours | **urgente** | pastille rouge, barre rouge |

Filtres : texte, délai, **secteur** (ville) ; tris : délai, secteur (ville puis code postal), durée. Chaque ligne a ses actions rapides
(statut, **Facturer**, **Encaisser**) et une adresse cliquable vers Google Maps. Seuils : `SEUIL_SURVEILLER` et `SEUIL_URGENT` dans
`outils/noyau.py`.

## 3. Tournées (bâtir une journée)

Menu **Tournées** : on choisit la journée (◀ ▶, calendrier, « Demain ») et on voit son déroulement (comme ci-dessus). En dessous, les
**chantiers à placer** : filtres statut (À planifier / En attente / Soumissions / Planifiés un autre jour pour les déplacer),
délai, secteur, tri. On **coche** des chantiers, on ajuste leur durée (le total d'heures de la journée se met à jour en direct), puis
**Ajouter à la journée** : ils sont ajoutés **à la fin**, dans l'ordre où ils sont affichés (avec le tri « secteur », les chantiers du
même coin se suivent). Ensuite, ▲ / ▼ pour ajuster. Tout est planifié d'un coup, ou rien.

L'ordre optimal et le trajet sur la carte viendront avec l'étape 2.

## 4. Fiche client et nouveau chantier simplifié

`Clients` → un client : coordonnées, adresse cliquable, historique. **+ Nouveau chantier** ouvre un formulaire réduit à l'essentiel
(travaux avec précisions, prix, modalité de paiement, notes). **Nom et adresse sont verrouillés** : le serveur relit toujours la fiche du
client. Le chantier est créé « À planifier ». Pour corriger un nom ou une adresse : *Modifier le client*.
