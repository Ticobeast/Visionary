# Tableau de bord, Journée, Chantiers et clients

Principe : **simple par défaut**. Chaque écran montre d'abord l'important ; les options rarement utiles sont dans « Paramètres
avancés » (repliés). Chaque chose a **un seul endroit** :

| Section | Rôle |
|---|---|
| **Tableau de bord** | *voir* : le calendrier et le déroulement de la journée choisie (lecture seule) |
| **Journée** | *gérer une journée* : y placer des chantiers, ordre, statut, encaissement, retrait |
| **Chantiers** | *gérer les jobs* : liste des chantiers actifs ; **plus bas, les archives** (anciens chantiers) |
| **Clients** | les fiches clients (seul endroit où l'on modifie un client) et la liste des **secteurs desservis** |

Il n'y a plus de section « Suivi » ni « Tournées » (les anciens liens redirigent vers *Journée* et *Chantiers*) ni d'entrée
« Archives » dans le menu.

## Les statuts d'un chantier : automatiques

**Le statut ne se choisit jamais à la main dans la Journée ni sur le tableau de bord.** Il suit ce qu'on fait :

| Action | Statut qui en résulte |
|---|---|
| Ajouter le chantier à une journée (page *Journée*) | **Planifié** |
| **Retirer** le chantier de la journée | retour à **À planifier** |
| **Annuler** le chantier | **Annulé** : il disparaît de la journée et va **automatiquement dans les archives** |
| **Marquer comme terminé** (page du chantier) ou « Oui » après un encaissement | **Terminé** (verrouillé) |

Seuls les statuts d'**avant** la planification se choisissent, sur la page du chantier : *Soumission → En attente → À planifier*.
Un chantier annulé par erreur se **rouvre** (bouton sur sa page) : il redevient « À planifier ».

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

Dans **chaque case**, directement : le **nombre de chantiers**, le **temps total** (⏱) et le **montant total** (💰, arrondi au dollar).
D'un coup d'œil : combien de chantiers, combien d'heures, combien d'argent pour cette journée.

**Un clic sur une date** affiche, juste en dessous, la journée :

- les **chantiers dans l'ordre de passage**, avec leurs **heures de début → fin** et le **temps de chacun** (⏱) ;
- la **durée totale** de la journée et, juste dessous, le **montant total** de la journée (taxes incluses) ;
- à **droite de chaque chantier, sa valeur** (total taxes incluses, prix avant taxes en petit) pour juger d'un coup d'œil la rentabilité ;
- les **options** de la job (🏗 nacelle, 🪵 sort du bois), bien visibles ;
- le **statut** et l'**état des paiements** (reçu, solde) de chaque chantier.

Rien ne se modifie ici : ni statut, ni durée, ni ordre. Deux actions seulement :
- **Retirer** un chantier de la journée (il redevient « À planifier ») ;
- **Encaisser** : le **montant prévu** (le solde) est affiché, **non modifiable** ; on choisit le mode (proposé d'après le mode de règlement
  prévu), on **confirme**, et le paiement est enregistré. Pour un acompte ou un autre montant : page du chantier.

Le bouton **Gérer cette journée** ouvre la page *Journée* sur la même date.

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
| **Encaisser** | encaisse le montant prévu (le solde, non modifiable) après confirmation |
| **Retirer** | remet le chantier dans « À planifier » |
| **Annuler** | annule le chantier (confirmation) : il disparaît de la journée et est archivé |

Il n'y a **aucun choix de statut** ici : ajouter à la journée = Planifié, Retirer = À planifier, Annuler = Annulé.

**Le temps et le prix d'un travail ne se modifient jamais ici** : ce sont ceux du chantier (page du chantier, « Durée estimée »).

En dessous, les **chantiers à placer** : filtres statut (À planifier / En attente / Soumissions / Planifiés un autre jour pour les déplacer),
**délai d'attente**, **secteur**, tri. Chaque ligne montre le délai d'attente, le travail, son **temps** et sa **valeur à droite**. On **coche**
des chantiers (le total d'heures **et de dollars** de la journée se met à jour en direct), puis **Ajouter à la journée** : ils sont ajoutés
**à la fin**, dans l'ordre affiché. Un chantier sans durée estimée ne peut pas être coché : un lien mène à sa page pour la saisir.
Tout est planifié d'un coup, ou rien.

### Encaissement sur un chantier « Planifié » : confirmation

Quand tu encaisses sur un chantier **Planifié** (tableau de bord, Journée ou page du chantier), le paiement est enregistré, puis une fenêtre demande :

> Voulez-vous passer ce chantier au statut "Terminé" ?  —  **Oui, passer à Terminé** / **Non, laisser Planifié**

La **durée réelle** y est préremplie avec la durée estimée. « Oui » change le statut ; « Non » ferme la fenêtre. Elle n'apparaît **pas** pour un
chantier déjà Terminé ou À planifier. Elle fonctionne partout où l'on encaisse : Journée et page du chantier.

L'ordre optimal et le trajet sur la carte viendront avec l'étape 2.

## 3. Chantiers et archives

Menu **Chantiers** : une seule page.

- **En haut : les chantiers actifs**, classés par **date de la demande / soumission** (c'est la date principale ; la date planifiée n'est
  qu'une mention « prévu le … »), avec le **délai d'attente** des soumissions / en attente / à planifier (pastille verte < 7 jours,
  jaune 7 à 30, rouge > 30), le temps, le statut, le paiement et le **montant à droite**. Des raccourcis : à facturer, à recevoir, planifiés,
  prix manquants ; une recherche (nom sans accent, téléphone, adresse, secteur) et des filtres statut / paiement / **secteur**.
- **Plus bas : « 📦 Archives »** : les anciens chantiers, c'est-à-dire **annulés** et **terminés et payés** (ils y vont **automatiquement**,
  sans rien cliquer ; un chantier annulé ne figure donc plus parmi les actifs).
  Les 50 plus récents s'affichent ; la recherche couvre tout. Un lien « Archives (N) ↓ » en haut de page y descend.

Seuils d'attente : `SEUIL_SURVEILLER` et `SEUIL_URGENT` dans `outils/noyau.py`.

## 4. Créer un chantier, voir un chantier : l'essentiel d'abord

**+ Nouveau** (client neuf) : le formulaire ne demande que l'essentiel — **nom, prénom, téléphone, adresse, ville / secteur (liste) ;
types de travaux (avec précisions), options du travail (🏗 nacelle requise ; 🪵 débarrasser le bois, sinon son format), durée estimée
(obligatoire), prix, description**. Les **options du travail sont toujours visibles** (elles servent à préparer la job). Tout le reste est
dans **« Paramètres avancés »** (replié) : entreprise, courriel, code postal, accès, GPS, statut de départ (Soumission / En attente / À
planifier), date de la demande, TPS/TVQ saisies à la main, mode de règlement, facture, paiement déjà reçu, fichiers.
Les champs repliés sont envoyés avec le formulaire (valeurs par défaut : statut Soumission, date de la demande = aujourd'hui) ; une erreur
dans un champ avancé ouvre automatiquement la section. Un chantier ne se planifie pas à la création : on l'ajoute ensuite à une journée.

**Options du travail**
- **Nacelle requise** : oui / non.
- **Débarrasser le bois** : si la case est cochée, rien d'autre. Sinon, pour un **abattage ou un élagage**, on précise le format du bois laissé sur
  place : **16 pouces** ou **4 pieds** (obligatoire pour ces deux types ; les autres travaux n'ont pas à le préciser).
- Elles s'affichent en pastilles partout où le travail apparaît : page du chantier, liste *Chantiers*, tableau de bord, *Journée*.

**Après la création**, on arrive sur la **page du chantier**, pensée pour une consultation rapide (90 % des cas) :

1. le résumé : client, statut, travaux, options (nacelle, bois), date et durée, et **la valeur à droite** (total, reçu, solde) ;
2. le client en **lecture seule** (🔒) ;
3. les **paiements** (liste ; « + Ajouter un paiement » à un clic) ;
4. les champs essentiels à modifier : travaux, options, durée estimée, prix, description ; le **statut** (à choisir seulement avant la
   planification) et la **date des travaux** sont **affichés** (« géré automatiquement », « se change dans la page Journée ») ;
5. **« Paramètres avancés »** (replié) : date de la demande, durée réelle, taxes, mode de règlement, facture, fichiers, autres chantiers du client,
   **annuler** ou supprimer le chantier.

Boutons : **✔ Marquer comme terminé** (chantier planifié), **↩ Rouvrir** (chantier annulé), **Dupliquer**.

Un chantier **Terminé** n'a pas de formulaire : résumé, client, facturation et paiements en clair ; le détail complet est dans « Paramètres avancés ».

## 5. Clients

`Clients` : une liste épurée avec **seulement Nom, Téléphone et Adresse** (le secteur est écrit sous l'adresse), filtrable par **secteur**. La fiche d'un client montre ses coordonnées et l'historique de ses
chantiers (date, travaux, statut — sans montants). **+ Nouveau chantier** ouvre un formulaire réduit à l'essentiel : travaux avec précisions,
**durée estimée (obligatoire)**, prix, notes ; la **date de la demande** (aujourd'hui) et le **mode de règlement** sont dans « Paramètres
avancés ». Le chantier est créé « À planifier ».

**Le client n'est modifiable qu'à un seul endroit : sa fiche** (bouton *Modifier le client*, même principe : l'essentiel d'abord, le reste dans
« Paramètres avancés »). Partout ailleurs son nom, son adresse et ses coordonnées sont **affichés en lecture seule** (🔒) : le serveur relit
toujours le client dans la base et ignore tout ce que le navigateur enverrait.

### Ville / secteur : une liste déroulante, jamais de texte libre

Chaque client a un **secteur**, choisi dans une **liste fermée** (obligatoire à la création et à la modification d'un client). La **ville inscrite sur
l'adresse** (pour Google Maps) **vient du secteur** choisi : plus de « Trois Rivieres », « Trois-Riviere »… Un même secteur s'écrit toujours pareil, ce
qui permet de **classer et filtrer** par secteur (clients, chantiers, Journée).

La liste de départ est celle de la région de Trois-Rivières (Centre-ville, Trois-Rivières-Ouest, Cap-de-la-Madeleine, Sainte-Marthe-du-Cap,
Pointe-du-Lac, Saint-Louis-de-France, Bécancour, Champlain, Yamachiche, Saint-Étienne-des-Grès, Shawinigan, Louiseville, Nicolet) : **à adapter
aux secteurs réellement desservis** dans la page **Secteurs** (lien au bas de la liste des clients) : ajouter, renommer, supprimer un secteur
inutilisé. Un nom déjà présent (à l'accent, au tiret ou à la casse près) est refusé : pas de doublons.

## 6. Règles d'un chantier

- **Date de la demande** : préremplie avec aujourd'hui (modifiable).
- **Mode de règlement** : un seul choix parmi Comptant, Chèque, Interac, Carte, Autre.
- **Jamais de solde négatif** : un paiement (ou un acompte) ne peut pas dépasser ce qu'il reste à payer ; le formulaire indique « au plus … $ ».
- **Durée estimée obligatoire** à la création, à l'import et à la planification. La **durée réelle** n'apparaît pas à la création ;
  quand le chantier passe à **Terminé**, elle est préremplie avec la durée estimée (modifiable dans la fenêtre de confirmation).
- **Terminé = verrouillé** : lecture seule, impossible à rouvrir, modifier ou supprimer. Restent possibles : facturer, encaisser, dupliquer.
  (Une erreur de saisie sur un chantier terminé se corrige donc en amont : relis avant de passer à « Terminé ».)
- **Archives** : un chantier **annulé**, ou **terminé et payé**, quitte la liste active et va dans les archives (bas de la page *Chantiers*), automatiquement.
- **Date principale** : la date de la demande / soumission, pas la date planifiée.
- **Dupliquer le chantier** (page d'un chantier) : nouvelle soumission pour le même client (travaux, durée, prix, mode repris ; dates
  repartent d'aujourd'hui ; prix et durée ajustables).

