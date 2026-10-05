# Tableau de bord, fiche client et tournées

Trois outils pour piloter le travail au quotidien, sans ouvrir la fiche complète d'un chantier.

## 1. Tableau de bord (page d'accueil)

Cinq onglets, avec le nombre de chantiers (et d'urgents) dans chacun :

| Onglet | Contenu | Classement par défaut |
|---|---|---|
| **À planifier** | chantiers acceptés, sans date | par délai d'attente (le plus long d'abord) |
| **Soumissions** | estimés donnés, réponse du client attendue | par délai d'attente |
| **Planifiés** | chantiers avec une date, regroupés par jour (nombre de chantiers et heures totales) | par jour, puis heure |
| **À facturer** | travaux terminés, pas encore facturés | par ancienneté |
| **À recevoir** | facturés ou partiellement payés | par délai |

### Délai d'attente et priorité

Le délai d'attente = nombre de jours depuis la **date de la demande ou de la soumission** (à défaut, depuis la
création de la fiche). Pour « À facturer » et « À recevoir », on compte depuis la date des travaux, puis depuis
la facture.

| Délai | Priorité | Affichage |
|---|---|---|
| moins de 7 jours | normale | pastille verte |
| 7 à 30 jours | à surveiller | pastille jaune, barre jaune à gauche |
| plus de 30 jours | **urgente** | pastille rouge, barre rouge à gauche |

Les seuils sont `SEUIL_SURVEILLER` et `SEUIL_URGENT` dans `outils/noyau.py`.

### Filtrer et trier

Barre de filtres : recherche texte, **délai** (urgents / à surveiller / normaux), **secteur** (la ville) et **tri**
(délai d'attente, secteur = ville puis code postal, durée). Avec le tri « secteur », les chantiers sont regroupés par
ville : c'est la façon la plus rapide de repérer ceux qui se font dans le même coin.

### Ce qui est visible sur chaque ligne

- le **délai d'attente** et depuis quelle date ;
- le client (lien vers sa fiche) et son téléphone ;
- l'**adresse cliquable** : un clic ouvre Google Maps (nouvel onglet) ;
- les travaux avec leurs précisions et la **durée planifiée** (⏱ 2 h 30) ;
- le prix total, ce qui est déjà reçu, le solde et la modalité de paiement.

### Actions rapides (sans ouvrir la fiche)

| Action | Ce qu'elle fait |
|---|---|
| **Statut** + date + durée + OK | change le statut. Voir les règles ci-dessous. |
| **Facturer** | marque un chantier *terminé* comme facturé (date de la facture = aujourd'hui). Refusé si le prix est manquant. |
| **Encaisser** | enregistre un paiement (le montant proposé est le solde ; le mode proposé suit la modalité de paiement). Un montant plus petit = acompte. |

Règles du changement de statut :

- **Planifié** et **Terminé** exigent une date (celle déjà inscrite est conservée si tu n'en donnes pas).
- **Soumission** et **Accepté** = « à planifier » : la date est effacée.
- **Refusé** et **Annulé** ne touchent pas à la date.
- La durée saisie est la durée **estimée**, en heures décimales (`2,5` = 2 h 30).

L'**état du paiement** n'est pas un champ qu'on modifie : il est calculé (*à facturer*, *facturé*, *partiel*, *payé*…).
« Facturer » et « Encaisser » créent les données qui le font changer ; une fois la page rechargée, la ligne passe
d'elle-même dans le bon onglet. Après chaque action, tu reviens à la même page, avec les mêmes filtres.

## 2. Fiche client et nouveau chantier simplifié

`Clients` → un client → fiche avec ses coordonnées, l'adresse cliquable et tout son historique.

**+ Nouveau chantier** (depuis la fiche) ouvre un formulaire réduit à l'essentiel :

1. **Travaux à faire** : un ou plusieurs types, chacun avec sa précision ;
2. **Prix** avant taxes (case pour ajouter TPS/TVQ) et **modalité de paiement** (« Interac à la fin », « 50 % d'acompte »…
   des suggestions sont proposées ; le texte est libre) ;
3. **Notes** : la description du chantier, imprimée plus tard sur la feuille de route.

Le **nom et l'adresse sont verrouillés** : affichés, mais non modifiables. Même un navigateur qui enverrait d'autres valeurs
n'y change rien (le serveur relit toujours la fiche du client). Pour corriger un nom ou une adresse : *Modifier le client*
(la modification vaut pour tous les chantiers du client).

Le chantier est créé **« Accepté »** (à planifier) : il apparaît aussitôt dans l'onglet « À planifier » du tableau de bord, où
l'on fixe la date et la durée.

## 3. Tournées (organiser les journées)

Page **Tournées** : on bâtit une journée en quelques clics.

1. Choisis la **journée** (◀ ▶, calendrier, bouton « Demain »). En haut : ce qui est déjà planifié ce jour-là, la durée totale
   et **ce qu'il reste de place** sur une journée de 8 h (`JOURNEE_H` dans `outils/tableau.py`). Un chantier planifié se
   retire d'un clic (il redevient « à planifier »).
2. **Filtre** les chantiers à placer : statut (à planifier / soumissions / planifiés un autre jour pour les déplacer),
   **délai d'attente**, **secteur** (ville), **tri** (délai, secteur, durée). Avec le tri par secteur, ils sont regroupés
   par ville avec les heures de chaque secteur.
3. **Coche** les chantiers voulus, ajuste leur **durée** au besoin (le total de la journée se met à jour en direct), puis
   « Ajouter à la journée ». Tout est planifié d'un coup, ou rien (si un chantier ne peut pas l'être, l'erreur est affichée et
   rien n'est modifié).

L'ordre de passage optimal et le trajet sur la carte viendront avec l'étape 2 (itinéraire) ; ici, on choisit *quoi* faire
*quel jour*, en regroupant par secteur.
