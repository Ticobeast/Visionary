# Dictionnaire de données (schéma v1)

Source de vérité : [`schema/schema.sql`](../schema/schema.sql). Ce document l'explique ; en cas de
désaccord, c'est le fichier SQL qui a raison (la base applique ses règles elle-même).

```
clients (personne/entreprise + adresse) 1 ─── N chantiers 1 ─── N paiements
                                                  │
                                                  └── type_travaux → types_travaux (table de référence)
```

| Table | Une ligne = | Pourquoi une table à part |
|---|---|---|
| `clients` | une personne ou une entreprise, **avec son adresse** | un client revient : on ne retape ni son téléphone ni son adresse ; l'adresse est géocodée une seule fois |
| `chantiers` | un travail pour un client (environ 2 h : plusieurs par journée) | c'est l'unité que l'itinéraire, la feuille de route et la facturation manipulent ; garder les chantiers séparés conserve l'historique d'un client récurrent |
| `paiements` | une somme reçue | acompte + solde, chèque en deux versements… |
| `types_travaux` | un type de travaux | on ajoute un type avec un `INSERT`, sans modifier le schéma |

Un client qui possède deux propriétés = **deux fiches clients** (une par adresse), simplement.

## Formats stricts (valables partout)

| Donnée | Format | Exemple | Refusé |
|---|---|---|---|
| Date | `AAAA-MM-JJ` | `2026-06-14` | `14/06/2026`, `2026-6-1`, `2026-02-30` |
| Heure | `HH:MM` (24 h) | `08:30` | `8:30`, `24:00` |
| Durée | heures décimales, temps **écoulé sur place** (pas heures-personne), 0 < d ≤ 24 | `2.5` (= 2 h 30) | `2h30`, `0` |
| Argent | dollars CAD, 2 décimales max, sans `$` | `480.00` | `480.123`, `-5` |
| Téléphone | `+1` + 10 chiffres (E.164) | `+14505550142` | `450-555-0142` en base (l'import le convertit pour toi) |
| Code postal | `A1A 1A1` majuscules, une espace | `J7Z 1A1` | `j7z1a1` en base (l'import le corrige) |
| Chemin de fichier | relatif au dossier `data/`, séparateur `/`, pas de `/` au début ni à la fin, pas de `..` | `photos/2026/2026-06-14_gagnon` | `/home/…`, `C:\…`, `photos/` |
| Coordonnées | degrés décimaux, **longitude négative** au Québec | `45.6480`, `-74.0920` | `45.6480`, `74.0920` |

## `clients` (la personne et son adresse)

| Colonne | Type | Oblig. | Règle | Exemple |
|---|---|---|---|---|
| `id` | entier | auto | clé primaire | `1` |
| `prenom` | texte | non | | `Marie` |
| `nom` | texte | **nom ou entreprise** | | `Gagnon` |
| `entreprise` | texte | **nom ou entreprise** | syndicat, ferme, commerce | `Syndicat Les Jardins du Lac` |
| `telephone` | texte | non (recommandé) | E.164 ; sert aux textos (étape 4) | `+14505550142` |
| `telephone_2` | texte | non | idem | |
| `courriel` | texte | non | forme `x@y.z`, sans espace | `marie.gagnon@example.com` |
| `sms_ok` | 0/1 | oui, défaut `1` | `0` = ne jamais envoyer de texto à ce client | `1` |
| `adresse` | texte | **oui** | numéro + type + nom de rue, comme sur une enveloppe | `123 Rue des Érables` |
| `ville` | texte | **oui** | nom officiel | `Saint-Jérôme` |
| `province` | texte | oui, défaut `QC` | 2 lettres majuscules | `QC` |
| `code_postal` | texte | non (recommandé) | `A1A 1A1` | `J7Z 1A1` |
| `latitude`, `longitude` | réel | non | les deux ou aucune ; remplies par le script de géocodage (étape 2) ou à la main | `45.6480`, `-74.0920` |
| `geocode_statut` | texte | oui, défaut `a_faire` | `a_faire`, `ok`, `approximatif`, `echec`, `manuel` ; **cohérent avec les coordonnées** (`a_faire`/`echec` ⇒ pas de coordonnées ; les autres ⇒ coordonnées présentes) | `manuel` |
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

## `chantiers`

| Colonne | Type | Oblig. | Règle | Exemple |
|---|---|---|---|---|
| `id` | entier | auto | | |
| `client_id` | entier | oui | → `clients.id` ; un client ne peut pas être supprimé s'il a des chantiers | `1` |
| `type_travaux` | texte | oui | un `code` de `types_travaux` : `emondage`, `elagage`, `taille_haie`, `abattage`, `essouchement`, `autre` | `taille_haie` |
| `description` | texte | non | ce qu'il y a à faire — **sera imprimé sur la feuille de route** | `Haie de cèdres, 35 m, hauteur 2 m` |
| `notes` | texte | non | remarques propres à ce chantier | `Prévenir le gardien la veille` |
| `statut` | texte | oui, défaut `soumission` | voir ci-dessous | `planifie` |
| `date_soumission` | date | non | quand l'estimé a été donné | `2026-05-28` |
| `date_prevue` | date | **si `planifie`** | jour prévu (c'est elle que le script d'itinéraire filtre) | `2026-10-14` |
| `heure_prevue` | heure | non | seulement pour un rendez-vous fixe | `08:00` |
| `date_realisee` | date | **si, et seulement si, `termine`** | | `2026-06-14` |
| `duree_estimee_h` | réel | non | pour l'itinéraire et la feuille de route | `3.0` |
| `duree_reelle_h` | réel | non | mesurée après coup, pour affiner les estimés | `3.5` |
| `prix_ht` | réel | non | avant taxes ; estimé tant que non facturé, puis final | `480.00` |
| `tps` | réel | oui, défaut `0` | montant de TPS (laisser `0` si non inscrit aux taxes) | `24.00` |
| `tvq` | réel | oui, défaut `0` | montant de TVQ (idem) | `47.88` |
| `numero_facture` | texte | non | le numéro de ta facture papier ; exige `date_facture` | `2026-031` |
| `date_facture` | date | non | date de la facture ou du reçu remis ; exige `prix_ht` | `2026-06-14` |
| `dossier_photos` | chemin | non | **un dossier par chantier** ; les photos qu'il contient seront lues par le script (miniatures) | `photos/2026/2026-06-14_gagnon` |
| `fichier_papier` | chemin | non | scan de la fiche papier d'origine | `papier/2026/2026-06-14_gagnon.pdf` |
| `ref_papier` | texte | non | où retrouver l'original en attendant le scan | `Classeur A, fiche 12` |
| `cree_le` | texte | auto | | |

### Statuts des travaux

| `statut` | Signification | Contrainte |
|---|---|---|
| `soumission` | estimé donné, réponse du client attendue | |
| `refuse` | le client a dit non | |
| `accepte` | accepté, pas encore de date | |
| `planifie` | date fixée | `date_prevue` obligatoire |
| `termine` | travaux faits | `date_realisee` obligatoire (et réciproquement) |
| `annule` | annulé après acceptation | |

Un travail de plusieurs jours = un chantier par journée.

### Statuts de paiement — calculés, jamais saisis

Le statut de paiement n'est **pas une colonne** : la vue `v_chantiers` le calcule à partir du statut des
travaux, de `date_facture` et de la somme des `paiements`. Il ne peut donc jamais contredire les montants.

| `statut_paiement` | Condition | Action |
|---|---|---|
| `prix_manquant` | travaux faits mais `prix_ht` vide | compléter la fiche |
| `non_facture` | `termine`, aucune facture émise | **à facturer** |
| `a_payer` | facture émise, rien reçu | **à relancer** |
| `partiel` | une partie reçue (acompte…), solde > 0 | |
| `paye` | somme reçue ≥ total | |
| `a_venir` | `accepte` / `planifie`, pas encore fait | |
| `sans_objet` | `soumission`, `refuse`, `annule`, ou travail gratuit | |

Colonnes calculées : `total_ttc = prix_ht + tps + tvq`, `paye = somme des paiements`, `solde = total_ttc − paye`.

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

## `types_travaux`

| Colonne | Exemple |
|---|---|
| `code` (minuscules et `_`) | `taille_haie` |
| `libelle` | `Taille de haie` |

Ajouter un type : `INSERT INTO types_travaux (code, libelle) VALUES ('haubanage', 'Haubanage');`

## La vue `v_chantiers` (ce que les scripts Python liront)

Une ligne par chantier, tout déjà joint : client (`client_nom_complet`, `telephone`, `sms_ok`), adresse
(`adresse_maps`, `latitude`, `longitude`, `notes_acces`), travaux (`type_libelle`, `description`,
`date_prevue`, `duree_estimee_h`, `dossier_photos`…) et finances (`total_ttc`, `paye`, `solde`,
`statut_paiement`). Exemple — le travail de la journée pour l'étape 2 :

```sql
SELECT client_nom_complet, adresse_maps, latitude, longitude, duree_estimee_h, notes, dossier_photos
FROM v_chantiers
WHERE date_prevue = '2026-10-14' AND statut = 'planifie';
```

Autres requêtes utiles :

```sql
-- Travaux faits, à facturer
SELECT date_realisee, client_nom_complet, total_ttc FROM v_chantiers WHERE statut_paiement = 'non_facture';
-- Argent à recevoir
SELECT client_nom_complet, solde FROM v_chantiers WHERE statut_paiement IN ('a_payer', 'partiel');
-- Adresses à géocoder
SELECT id, adresse, ville FROM clients WHERE geocode_statut = 'a_faire';
```

## Les deux façons de saisir

- **L'interface** (`python3 outils/interface.py`) : formulaire dans le navigateur, sélecteurs de date,
  listes déroulantes, recherche d'un client existant, validation immédiate. **Méthode recommandée.**
- **La feuille CSV** (`modeles/saisie_papier_*.csv` + `outils/importer_saisie.py`) : pour importer en lot
  depuis un tableur (LibreOffice Calc…) ou pour reprendre des données déjà en tableau.

Les deux appliquent exactement les mêmes règles (`outils/noyau.py`). La feuille CSV est « à plat » (une ligne =
une fiche = un chantier) ; l'import range chaque colonne dans la bonne table :

| Colonnes de la feuille | Destination |
|---|---|
| `client_nom`, `client_prenom`, `client_entreprise`, `client_telephone`, `client_telephone_2`, `client_courriel`, `client_sms_ok`, `client_notes`, `adresse`, `ville`, `province`, `code_postal`, `latitude`, `longitude`, `notes_acces` | `clients` |
| `type_travaux`, `statut`, `description`, `notes`, `date_*`, `heure_prevue`, `duree_*`, `prix_ht`, `tps`, `tvq`, `numero_facture`, `ref_papier`, `fichier_papier`, `dossier_photos` | `chantiers` |
| `paiement_date`, `paiement_montant`, `paiement_mode` | `paiements` (un paiement par ligne ; les acomptes supplémentaires se saisissent dans l'interface) |

L'import est plus souple que la base, puis écrit toujours le format strict :

- téléphone `450-555-0142` ou `(450) 555-0142` → `+14505550142` ; code postal `j7z1a1` → `J7Z 1A1`
- `1 250,00 $` ou `1250,00` → `1250.00` ; heure `8h30` → `08:30`
- `type_travaux` accepte le code ou le libellé (`taille_haie`, `Taille de haie`) ; `statut` et `paiement_mode`
  acceptent accents et majuscules (`Terminé`, `Chèque`)
- séparateur `,` ou `;`, encodage UTF-8 ou Windows-1252 (export d'Excel) : détectés automatiquement
- les **dates** restent strictes (`AAAA-MM-JJ`), parce que c'est là qu'un tableur fait des dégâts :
  formater ces colonnes en « Texte » avant de saisir
- **un même client** = même adresse + même nom (ou même téléphone) : ses chantiers s'ajoutent à sa fiche ;
  même téléphone mais autre adresse = nouvelle fiche (2e propriété), avec un avertissement ;
  la première saisie gagne, les champs vides se complètent, les contradictions sont signalées
- `--taxes-auto` calcule TPS 5 % et TVQ 9,975 % pour les lignes dont `tps` et `tvq` sont vides

## Volontairement absent (ajoutable plus tard sans refaire la saisie)

`ALTER TABLE … ADD COLUMN` suffit pour : ordre de tournée, équipe/équipement requis, date d'envoi du
rappel par texto, prochain suivi d'un client récurrent. Rien de ce qui est saisi aujourd'hui n'aura à être
retranscrit.
