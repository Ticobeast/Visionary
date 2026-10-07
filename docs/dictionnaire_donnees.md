# Dictionnaire de données (schéma v11)

Source de vérité : [`schema/schema.sql`](../schema/schema.sql). Ce document l'explique ; en cas de
désaccord, c'est le fichier SQL qui a raison (la base applique ses règles elle-même).

```
secteurs 1 ─── N clients (personne/entreprise + adresse) 1 ─── N chantiers 1 ─── N paiements
                                                  │
                                                  └── N chantier_travaux → types_travaux (types + précision)
```

| Table | Une ligne = | Pourquoi une table à part |
|---|---|---|
| `clients` | une personne ou une entreprise, **avec son adresse** | un client revient : on ne retape ni son téléphone ni son adresse ; l'adresse est géocodée une seule fois |
| `chantiers` | un travail pour un client (environ 2 h : plusieurs par journée) **ou une soumission** (un chantier pas encore accepté : même fiche, autre nom) | c'est l'unité que l'itinéraire, la feuille de route et le suivi des paiements manipulent ; garder les chantiers séparés conserve l'historique d'un client récurrent |
| `chantier_travaux` | un type de travaux d'un chantier, avec sa précision | un chantier peut combiner plusieurs types (élagage + taille de haie) |
| `paiements` | une somme reçue | acompte + solde, chèque en deux versements… |
| `utilisateurs`, `sessions` | les comptes de l'équipe et leurs connexions ouvertes | accès par mot de passe (voir ci-dessous) ; absents du reste du modèle |
| `raccourcis` | une pastille en haut de la page Chantiers ou Soumissions, pour une personne | chaque compte choisit ses raccourcis (voir ci-dessous) |
| `types_travaux` | un type de travaux | on ajoute un type avec un `INSERT`, sans modifier le schéma |
| `secteurs` | un secteur desservi (liste fermée) : `code`, `libelle`, `ville` (inscrite sur l'adresse), `ordre` | une ville s'écrit toujours de la même façon (liste déroulante) ; sert à classer / filtrer les clients. Se gère dans la page *Secteurs* |

Un client qui possède deux propriétés = **deux fiches clients** (une par adresse), simplement.

## Formats stricts (valables partout)

| Donnée | Format | Exemple | Refusé |
|---|---|---|---|
| Date | `AAAA-MM-JJ` | `2026-06-14` | `14/06/2026`, `2026-6-1`, `2026-02-30` |
| Durée | heures décimales, temps **écoulé sur place** (pas heures-personne), 0 < d ≤ 24 | `2.5` (= 2 h 30) | `2h30`, `0` |
| Argent | dollars CAD, 2 décimales max, sans `$` | `480.00` | `480.123`, `-5` |
| Téléphone | `+1` + 10 chiffres (E.164) | `+14505550142` | `450-555-0142` en base (l'interface le convertit pour toi) |
| Code postal | `A1A 1A1` majuscules, une espace | `J7Z 1A1` | `j7z1a1` en base (l'interface le corrige) |
| Chemin de fichier | relatif au dossier `data/`, séparateur `/`, pas de `/` au début ni à la fin, pas de `..` | `photos/2026/2026-06-14_gagnon` | `/home/…`, `C:\…`, `photos/` |
| Coordonnées | degrés décimaux, **longitude négative** au Québec | `45.6480`, `-74.0920` | `45.6480`, `74.0920` |

## `clients` (la personne et son adresse)

| Colonne | Type | Oblig. | Règle | Exemple |
|---|---|---|---|---|
| `id` | entier | auto | clé primaire | `1` |
| `prenom` | texte | non | | `Marie` |
| `nom` | texte | non en base ; **nom ou entreprise exigé pour accepter une soumission** | | `Gagnon` |
| `entreprise` | texte | non en base ; idem | syndicat, ferme, commerce | `Syndicat Les Jardins du Lac` |
| `telephone` | texte | non (recommandé) | E.164 ; sert aux textos (étape 4) | `+14505550142` |
| `telephone_2` | texte | non | idem | |
| `courriel` | texte | non | forme `x@y.z`, sans espace | `marie.gagnon@example.com` |
| `sms_ok` | 0/1 | oui, défaut `1` | `0` = ne jamais envoyer de texto à ce client | `1` |
| `adresse` | texte | oui en base (`''` tant qu'elle est inconnue) ; **exigée pour accepter** | numéro + type + nom de rue, comme sur une enveloppe ; **texte vide, jamais `NULL`** | `123 Rue des Érables` |
| `ville` | texte | idem (`''` tant que le secteur est inconnu) | nom officiel ; **dans l'interface elle vient du secteur choisi** (jamais saisie à la main) | `Trois-Rivières` |
| `secteur` | texte | non en base ; **exigé pour accepter une soumission** | → `secteurs.code` (liste fermée) ; vide pour d'anciens clients ou une soumission en préparation (à choisir dans la fiche). Importé via la colonne `client_secteur` (code ou libellé) | `cap_de_la_madeleine` |
| `province` | texte | oui, défaut `QC` | 2 lettres majuscules | `QC` |
| `code_postal` | texte | non (recommandé) | `A1A 1A1` | `J7Z 1A1` |
| `latitude`, `longitude` | réel | non | les deux ou aucune ; remplies par le script de géocodage (étape 2) ou à la main | `45.6480`, `-74.0920` |
| `geocode_statut` | texte | oui, défaut `a_faire` | `a_faire`, `ok`, `approximatif`, `echec`, `manuel` ; **cohérent avec les coordonnées** (`a_faire`/`echec`  pas de coordonnées ; les autres  coordonnées présentes) | `manuel` |
| `notes_acces` | texte | non | barrière, chien, où stationner, où est l'arbre | `Stationner près de la grange` |
| `notes` | texte | non | préférences, historique utile | `Préfère être appelé après 17 h` |
| `cree_le` | texte | auto | date-heure locale de création | `2026-10-05 14:02:11` |

**Écrire une adresse que Google Maps comprend.** Le format ci-dessus suffit : la vue `v_chantiers`
fabrique la chaîne `123 Rue des Érables, Saint-Jérôme, QC J7Z 1A1, Canada` (colonne `adresse_maps`),
prête pour le géocodage ou un lien Maps. Pour un lot sans numéro civique (« Lot 12-4, Rang du
Ruisseau »), Google risque de ne pas le trouver : dans Google Maps, clic droit sur l'emplacement →
copier les coordonnées → les mettre dans `latitude`/`longitude` (statut `manuel`).

**Changer l'adresse d'un client** (dans l'interface) efface ses coordonnées si elles étaient celles de
l'ancienne adresse : elles seront recalculées au prochain géocodage.

**Un client sans renseignements** (soumission ouverte dès le premier appel) est permis : la base n'exige ni nom, ni adresse. Les vues le montrent
comme `(client à identifier)` et `adresse_maps` est alors vide. L'application, elle, exige un nom (ou une entreprise), un téléphone, une adresse et un
secteur **au moment d'accepter** la soumission, et pour modifier un client qui a au moins un chantier (accepté).

## `chantiers`

| Colonne | Type | Oblig. | Règle | Exemple |
|---|---|---|---|---|
| `id` | entier | auto | | |
| `client_id` | entier | oui | → `clients.id` ; la base refuse de supprimer un client qui a encore des chantiers (l'interface le supprime avec tout son historique, dans une seule transaction) | `1` |
| `description` | texte | non | **la** description du chantier (une seule), imprimée sur la feuille de route ; le détail par type est dans `chantier_travaux` | `Résidus ramassés. Prévenir le gardien la veille.` |
| `statut` | texte | oui, défaut `soumission` | voir ci-dessous ; **ne se choisit jamais à la main** | `planifie` |
| `date_soumission` | date | non | date de la **demande ou de la soumission** : sert à calculer le délai d'attente (à défaut, la date de création de la fiche) | `2026-05-28` |
| `date_prevue` | date | **si `planifie` ou `termine`** | **la** date des travaux : prévue d'abord, puis réalisée. Si le chantier change de jour, on la met simplement à jour. C'est elle que le script d'itinéraire filtre | `2026-10-14` |
| `ordre_jour` | entier | auto | rang du chantier dans sa journée (1, 2, 3…), géré par l'application (boutons Monter / Descendre) ; vide si le chantier n'est ni planifié ni terminé. **Les heures de passage n'y sont pas stockées : elles sont calculées** (début 7 h 30, dîner 12 h - 12 h 30, d'après l'ordre et `duree_estimee_h`) | `2` |
| `duree_estimee_h` | réel | **oui (dans l'interface)** | durée sur place en heures, 0 < d ≤ 24 ; calcule les heures de la journée. Exigée par l'application (formulaires, import CSV, planification) ; la base elle-même accepte `NULL` pour pouvoir lire d'anciennes données | `3.0` |
| `duree_reelle_h` | réel | non | n'existe pas à la création d'une soumission ; **préremplie avec la durée estimée au passage à « Terminé »** (modifiable à ce moment-là seulement) | `3.5` |
| `nacelle` | 0/1 | oui, défaut `0` | nacelle requise | `1` |
| `debarrasser_bois` | 0/1 | oui, défaut `0` | `1` = on débarrasse le bois | `0` |
| `bois_format` | texte | non | si le bois reste sur place : `16_pouces` ou `4_pieds` (jamais avec `debarrasser_bois = 1`) ; exigé par l'interface pour un abattage / élagage non débarrassé | `16_pouces` |
| `prix_ht` | réel | non | avant taxes ; estimé tant que le chantier n'est pas terminé, puis final | `480.00` |
| `tps` | réel | oui, défaut `0` | montant de TPS (laisser `0` si non inscrit aux taxes) | `24.00` |
| `tvq` | réel | oui, défaut `0` | montant de TVQ (idem) | `47.88` |
| `modalite_paiement` | texte | non | **un seul choix** : `comptant`, `cheque`, `interac`, `carte`, `autre` (CHECK) ; imprimée sur la feuille de route pour savoir quoi encaisser sur place. Pas de paiement en plusieurs versements : les acomptes se saisissent comme paiements | `interac` |
| `dossier_photos` | chemin | non | **un dossier par chantier** ; les photos qu'il contient seront lues par le script (miniatures) | `photos/2026/2026-06-14_gagnon` |
| `cree_le` | texte | auto | | |
| `accepte_le` | date | non | `AAAA-MM-JJ` : **jour où la soumission a été acceptée** (posé par le bouton Accepter). Vide : soumission en cours ou refusée. Rempli : c'est un chantier (même annulé plus tard). C'est ce qui distingue une soumission refusée d'un chantier annulé | `2026-10-07` |
| `cree_par` | texte | non | **nom du compte** qui a ouvert la soumission (pour « Mes soumissions »). Vide : interface ouverte sans comptes, ou fiche d'avant les comptes | `Marc` |
| `reprise_le` | date | non | `AAAA-MM-JJ` : tant que le chantier est `en_attente`, **le jour où il redevient `a_planifier` tout seul** (vide : jusqu'à nouvel ordre). Une fois revenu (à la date ou à la main), **le jour du retour** : son délai d'attente repart de là | `2026-06-01` |

### Types de travaux d'un chantier : `chantier_travaux`

Un chantier peut combiner plusieurs types (par exemple un élagage et une taille de haie chez le même client le
même jour). Chaque type coché a sa **précision** libre (« érable argenté côté garage », « cèdres, 35 m »).

| Colonne | Type | Oblig. | Règle | Exemple |
|---|---|---|---|---|
| `chantier_id` | entier | oui | → `chantiers.id` (supprimé avec le chantier) | `11` |
| `type_travaux` | texte | oui | un `code` de `types_travaux` : `emondage`, `elagage`, `taille_haie`, `abattage`, `essouchement`, `autre` ; un type par chantier au maximum | `elagage` |
| `precision` | texte | non | ce qu'il y a à faire pour ce type | `érable argenté côté garage` |

Au moins un type est exigé par l'interface. Dans `v_chantiers` : `attente_depuis` (date à partir de laquelle le client attend : la demande pour une soumission ; l'acceptation pour un chantier, ou son retour d'attente `reprise_le`), `modalite_paiement`, `types_codes`
(`elagage+taille_haie`), `type_libelle` (`Élagage + Taille de haie`) et `travaux_detail`
(`Élagage : érable argenté côté garage ; Taille de haie : cèdres, 35 m`).

### Statuts des travaux

| `statut` | Signification | Contrainte |
|---|---|---|
| `soumission` | **soumission en cours** : demande ouverte, estimé à donner, remis ou en attente de la réponse du client (onglet *Soumissions*) | `accepte_le` vide |
| `en_attente` | **chantier accepté mis de côté** (saison, client pas prêt...) : pas dans la Journée ; revient à `a_planifier` à la date `reprise_le`, ou quand on l'en sort | date effacée ; `accepte_le` rempli |
| `a_planifier` | **soumission acceptée** (renseignements complets), pas encore de date (file d'attente classée par délai) | date effacée ; `accepte_le` rempli |
| `planifie` | date fixée, rang dans la journée | `date_prevue` obligatoire |
| `termine` | travaux faits | `date_prevue` obligatoire (le jour où ça a été fait) ; garde son rang dans la journée |
| `annule` | **soumission refusée** (`accepte_le` vide) ou **chantier annulé** (`accepte_le` rempli) | |

**Genre** (colonne `genre` de la vue `v_chantiers`, calculée) : `soumission` pour `soumission` et pour `annule` quand `accepte_le` est vide ;
`chantier` pour tout le reste. Les pages Chantiers, Journée et le tableau de bord ne lisent que le genre `chantier` ; la page Soumissions, que le genre
`soumission` (les refusées dans leur section du bas).

**Terminé = définitivement verrouillé** : des déclencheurs de la base (`trg_chantiers_termine_verrouille`, `trg_chantiers_termine_non_supprimable`, `trg_travaux_termine_*`) refusent toute modification du chantier terminé (statut, client, description, dates, durées, prix, taxes, modalité, fichiers), de ses types de travaux et sa suppression. Restent permis : les **paiements** et la **duplication**. Le verrou est donc garanti même pour un autre outil (DB Browser…). Limite connue : l'ajout d'un type de travaux à un chantier déjà terminé n'est pas bloqué par la base (nécessaire à la création d'un chantier directement terminé, par import) ; l'interface ne l'offre pas.

Parcours normal : *Soumission, (En attente,) À planifier, Planifié, Terminé* ; *Refusée* (soumission) ou *Annulé* (chantier) à tout moment (sauf après Terminé).
**Le statut est automatique** : Créer = `soumission` ; **Accepter** = `a_planifier` (si les conditions sont remplies : `noyau.CONDITIONS_ACCEPTATION`, et `accepte_le` = aujourd'hui) ;
**Refuser** = `annule` (sans `accepte_le`) ; ajouter à une journée = `planifie` ; Retirer = `a_planifier` ; Annuler = `annule` ; Terminer = `termine`.
**Rouvrir** une soumission refusée = `soumission` ; **Remettre en soumission** (chantier `a_planifier` ou `en_attente`) = `soumission`, `accepte_le` et `reprise_le` effacées.

**Mettre en attente** (`noyau.mettre_en_attente`) : un chantier `a_planifier` (ou déjà `en_attente` : on change la date), ou une soumission **complète** (mêmes conditions que pour l'accepter ; elle est alors
acceptée aujourd'hui : `accepte_le` = aujourd'hui) devient `en_attente`, avec `reprise_le` (une date à venir) ou vide. **Sortir de l'attente** (`noyau.sortir_de_l_attente`) = `a_planifier`, `reprise_le` = aujourd'hui.
**Retour automatique** (`noyau.reprendre_les_attentes`, appelé à chaque requête) : les `en_attente` dont `reprise_le` est arrivée (ou passée) deviennent `a_planifier` ; `reprise_le` garde la date prévue, qui
devient le début du délai d'attente. Un chantier `planifie` doit d'abord être retiré de sa journée ; un `en_attente` ne peut être planifié ni terminé sans en être sorti ; on ne choisit jamais `en_attente`
par un simple changement de statut (la date de reprise est demandée).

Conditions pour **accepter** (vérifiées par l'application, pas par la base : une soumission se remplit librement) : nom ou entreprise, téléphone, adresse,
secteur, au moins un type de travaux, sort du bois (abattage ou élagage seulement : débarrassé, ou format précisé), durée estimée, prix (0 est un prix).

Un travail de plusieurs jours = un chantier par journée.

### Statuts de paiement — calculés, jamais saisis

Il n'y a **pas de système de facture** : dès qu'un chantier est `termine`, le client est considéré comme facturé. Le statut de paiement n'est pas une
colonne : la vue `v_chantiers` le calcule à partir du statut des travaux et de la somme des `paiements`. Il ne peut donc jamais contredire les montants.

| `statut_paiement` | Condition | Action |
|---|---|---|
| `prix_manquant` | travaux faits mais `prix_ht` vide | compléter la fiche |
| `a_payer` | `termine`, rien reçu | **à recevoir** |
| `partiel` | une partie reçue (acompte...), solde > 0 | |
| `paye` | somme reçue >= total | |
| `a_venir` | `en_attente` / `a_planifier` / `planifie`, pas encore fait | |
| `sans_objet` | soumission (`soumission`), `annule`, ou travail gratuit | |

Colonnes calculées : `total_ttc = prix_ht + tps + tvq`, `paye = somme des paiements`, `solde = total_ttc − paye`.

**Jamais de solde négatif** : l'interface refuse un paiement supérieur au solde, et la base aussi (`trg_paiements_pas_de_solde_negatif_ajout` / `_modif`, `trg_chantiers_prix_sous_les_paiements` : on ne peut pas non plus baisser le prix sous ce qui est déjà payé ; un paiement sans prix saisi est refusé).

### Archives — calculées, jamais saisies

`v_chantiers.archive = 1` quand la fiche est **Annulée** (archivée aussitôt), ou **Terminée ET payée** (`statut_paiement` = `paye`, ou `sans_objet` pour un travail gratuit). Un chantier passe tout seul des « Actifs » aux « Archives » (section en bas de la page *Chantiers*) au moment du dernier paiement ; rien à cliquer. Les archives restent en lecture seule et se **dupliquent** pour un travail récurrent. Une **soumission refusée** a aussi `archive = 1`, mais elle est présentée dans la section « Refusées » de la page *Soumissions* (genre `soumission`), pas dans les archives des chantiers.

### Dupliquer une fiche

Crée une **nouvelle soumission** pour le même client : travaux (avec précisions), description, durée estimée, prix, taxes et modalité sont repris ; la date de la demande repart d'aujourd'hui ; pas de date de travaux, ni de paiement, ni de facture, ni de durée réelle, ni de fichiers. Le prix et la durée sont ajustables dans le formulaire.

## `paiements`

| Colonne | Type | Oblig. | Règle | Exemple |
|---|---|---|---|---|
| `id` | entier | auto | | |
| `chantier_id` | entier | oui | → `chantiers.id` | `1` |
| `date_paiement` | date | oui | | `2026-06-14` |
| `montant` | réel | oui | > 0, taxes incluses | `551.88` |
| `mode` | texte | oui | `comptant`, `cheque`, `interac`, `carte`, `autre` | `interac` |
| `reference` | texte | non | n° de chèque, référence Interac | `#0418` |
| `notes` | texte | non | | |

## `utilisateurs` et `sessions` (accès par mot de passe)

| Colonne | Type | Rôle |
|---|---|---|
| `utilisateurs.nom` | texte unique (sans égard à la casse) | nom de connexion |
| `utilisateurs.role` | `admin` ou `soumission` | `admin` : tout ; `soumission` : soumissions, chantiers et clients (ni finances, ni journée, ni suppressions) |
| `utilisateurs.mot_de_passe` | texte | `pbkdf2_sha256$itérations$sel$empreinte` : jamais le mot de passe lui-même |
| `utilisateurs.actif` | 0 ou 1 | 0 : connexion impossible, sessions coupées |
| `sessions.jeton_hash` | texte | empreinte SHA-256 du jeton du cookie (le jeton n'est jamais stocké) |
| `sessions.expire_le` | date-heure | 30 jours, prolongée à l'usage |

Tant qu'aucun compte actif n'existe, l'interface reste ouverte sur l'ordinateur seulement ; dès qu'il y en a un, la connexion est exigée partout.
Le format v9 a été ajouté à un format v8 par une migration automatique (`schema/migration_v8_v9.sql`), sans toucher aux données.

## `raccourcis` (les pastilles du haut)

| Colonne | Type | Règle |
|---|---|---|
| `utilisateur_id` | entier | → `utilisateurs.id` (supprimé avec le compte) ; **vide** : interface ouverte sans comptes (raccourcis communs) |
| `page` | texte | `chantiers` ou `soumissions` |
| `libelle` | texte | le nom de la pastille, jamais vide |
| `filtre` | texte | les critères sous forme de requête, dans un ordre stable : `statut`, `paiement`, `secteur`, `attente`, `par`, `q` (ex. `secteur=centre_ville&statut=planifie`) |
| `ordre` | entier | rang d'affichage |

Au premier passage d'une personne sur une page, ses raccourcis de départ sont enregistrés (l'administrateur : À recevoir, Planifiés, À planifier ; le compte
Soumission : À planifier, Planifiés ; Soumissions : Mes soumissions, À relancer). Une ligne spéciale (`filtre` = `__vide__`, invisible) retient qu'une
personne a **retiré tous** ses raccourcis : sans elle, ceux du départ reviendraient.

## Migrations automatiques (v8, v9 et v10 vers v11)

Au premier démarrage avec la nouvelle version, le programme **copie d'abord la base** (`data/sauvegardes/…avant_migration_v10…`, ou `_v9`, `_v8`), puis
migre. De v9 ou v10 au format courant, **tout se fait dans une seule transaction** (tout ou rien, avec vérification des liens `PRAGMA foreign_key_check`) ; la
vue `v_chantiers` est recréée à la fin, telle que dans `schema.sql`.

### Étape v10 vers v11 : « En attente » devient un statut de chantier

Ajoute `chantiers.reprise_le` et recrée la vue (colonnes `reprise_le`, `genre` et `attente_depuis` revues ; `en_attente` n'est plus une soumission). Au format v10, `en_attente`
n'était qu'un vieux nom de `soumission` : ces rares fiches (il n'y en a pas si la base vient d'être migrée de v9) deviennent des soumissions. Les données ne changent pas autrement.

### Étape v9 vers v10 (soumissions)

Dans la même transaction : assouplit la table `clients` (nom, adresse et ville ne sont
plus obligatoires en base ; adresse et ville vides deviennent `''`), ajoute `chantiers.accepte_le` et `chantiers.cree_par`, crée la table `raccourcis`,
recrée la vue `v_chantiers` (colonnes `genre`, `accepte_le`, `cree_par`) et reprend les données : les anciens statuts `en_attente` deviennent
`soumission` ; les autres fiches (`a_planifier`, `planifie`, `termine`, `annule`) sont des **chantiers acceptés** (`accepte_le` = leur date de demande, à défaut leur
date de création) : d'anciennes fiches « Annulé » restent donc dans les archives des chantiers, pas dans les soumissions refusées. Rien n'est
perdu ; en cas d'échec, la base reste telle quelle (v9 ou v10). Les tables de cette étape sont dans `schema/migration_v9_v10.sql` (définitions **figées** : `schema.sql` peut
évoluer sans les changer). Un test automatique vérifie que la base migrée (de v9 comme de v10) est identique à une base neuve.

## `types_travaux`

| Colonne | Exemple |
|---|---|
| `code` (minuscules et `_`) | `taille_haie` |
| `libelle` | `Taille de haie` |

Ajouter un type : `INSERT INTO types_travaux (code, libelle) VALUES ('haubanage', 'Haubanage');`

## La vue `v_chantiers` (ce que les scripts Python liront)

Une ligne par fiche (soumission ou chantier), tout déjà joint : `genre` (`soumission` ou `chantier`), `accepte_le`, `cree_par`, `reprise_le`, client (`client_nom_complet`, `telephone`, `sms_ok`), adresse
(`adresse_maps`, `latitude`, `longitude`, `notes_acces`), travaux (`type_libelle`, `travaux_detail`,
`description`, `date_prevue`, `duree_estimee_h`, `dossier_photos`…) et finances (`total_ttc`, `paye`, `solde`,
`statut_paiement`). Exemple — le travail de la journée pour l'étape 2 :

```sql
SELECT client_nom_complet, adresse_maps, latitude, longitude, duree_estimee_h, travaux_detail, description, dossier_photos
FROM v_chantiers
WHERE date_prevue = '2026-10-14' AND statut = 'planifie';
```

Autres requêtes utiles :

```sql
-- Argent à recevoir
SELECT client_nom_complet, solde FROM v_chantiers WHERE statut_paiement IN ('a_payer', 'partiel');
-- Adresses à géocoder
SELECT id, adresse, ville FROM clients WHERE geocode_statut = 'a_faire';
```

## Saisie

Tout se saisit dans l'interface (`python3 outils/interface.py`) : formulaires, sélecteurs de date, listes déroulantes, validation immédiate. Les
règles de validation (formats stricts ci-dessus : téléphone `450-555-0142` converti en `+14505550142`, code postal `j7z1a1` converti en `J7Z 1A1`,
`1 250,00 $` converti en `1250.00`...) sont dans `outils/noyau.py`. Il n'y a pas d'import CSV (pas de données à reprendre pour l'instant ; l'ancien
import est dans l'historique Git).

**Un même client** = même adresse + même nom (ou même téléphone) : ses chantiers s'ajoutent à sa fiche, qui n'est jamais modifiée par un
formulaire de chantier.

## Volontairement absent (ajoutable plus tard sans refaire la saisie)

`ALTER TABLE … ADD COLUMN` suffit pour : ordre de tournée, équipe/équipement requis, date d'envoi du
rappel par texto, prochain suivi d'un client récurrent. 
