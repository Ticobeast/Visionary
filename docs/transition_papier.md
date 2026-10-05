# Transition papier → numérique

Objectif : que la base soit **utile en quelques heures** (pas en un mois), sans y passer tes soirées.

Trois leviers, dans cet ordre :

1. **Arrêter d'ajouter du papier** — sinon la pile grossit pendant que tu la vides.
2. **Trier par valeur** — ce qui rapporte ou coûte de l'argent maintenant passe en premier ; les archives ne
   sont pas retranscrites.
3. **Saisir le strict minimum**, puis enrichir la fiche quand le client rappelle.

---

## Étape 0 — Mise en place (30 min, une seule fois)

1. Créer le dossier `data/` à la racine du projet, avec dedans `saisie/`, `photos/` et `papier/`.
   (`data/` est exclu de Git : tes vraies données ne partent jamais vers GitHub.)
2. Copier `modeles/saisie_papier_vide.csv` vers `data/saisie/lot_01.csv` et l'ouvrir dans ton tableur.
3. **Formater en « Texte » les colonnes de dates** (`date_*`, `paiement_date`) *avant* de saisir. Sinon le
   tableur transforme `2026-06-14` en `14/06/2026` et l'import le refusera.
4. Facultatif mais rentable : listes déroulantes (validation de données) sur `type_travaux`, `statut` et
   `paiement_mode`, et ligne 1 figée.
5. Vérifier que tout fonctionne avec les exemples :
   `python3 outils/importer_saisie.py modeles/saisie_papier_exemples.csv --simulation`

## Étape 1 — Trier le classeur en 3 piles (≈ 1 h pour tout)

| Pile | Critère | Traitement | Temps / fiche |
|---|---|---|---|
| **A — Vivant** | soumission en attente, travaux acceptés pas faits, **travaux faits non facturés**, factures impayées | fiche **complète**, en premier | 5–6 min |
| **B — Actif** | clients servis dans les ~24 derniers mois, surtout les récurrents (haies annuelles) | fiche **minimale** | ≈ 2 min |
| **C — Archive** | anciens, ponctuels, peu de chances de rappeler | **pas de saisie** : numériser en lot (ou garder en boîte), noter où c'est dans `ref_papier` si un jour tu saisis | 0 |

La pile A a un retour immédiat : c'est de l'argent à facturer ou à récupérer. Commence par elle.
Une fiche de la pile C se retranscrit **à la demande**, en 2 minutes, le jour où le client rappelle.

## Étape 2 — La fiche minimale

Obligatoire pour que l'import l'accepte :
`client_nom` (ou `client_entreprise`), `adresse`, `ville`, `type_travaux`, `statut`
— et `date_realisee` si le statut est `termine`.

Recommandé : `client_telephone` (rappels futurs), `prix_ht`, et le trio `paiement_date` / `paiement_montant` /
`paiement_mode` si c'est payé. Tout le reste reste vide : `latitude`/`longitude` seront remplies par le
script de géocodage, les photos s'ajouteront aux prochains chantiers.

Exemple d'une fiche minimale de la pile B (ancien chantier déjà payé) :

```csv
client_nom,client_telephone,adresse,ville,type_travaux,statut,date_realisee,prix_ht,paiement_date,paiement_montant,paiement_mode
Roy,450-555-0111,22 Rue des Pins,Mirabel,taille_haie,termine,2025-06-14,350.00,2025-06-14,350.00,autre
```

Pour l'**historique déjà réglé et déjà comptabilisé ailleurs**, saisis le montant réellement payé comme
`prix_ht` *et* comme `paiement_montant` (taxes à 0), mode `autre` si tu ne te souviens plus : ça donne `paye`
sans retranscrire les taxes. Contrepartie : les bilans d'avant la base seront en montants taxes incluses.
Pour les chantiers **vivants** (pile A), saisis le vrai prix avant taxes et laisse `--taxes-auto` calculer
TPS/TVQ (ou remplis `tps` et `tvq`).

## Étape 3 — Le rythme

- **Blocs de 25 minutes**, jamais plus de 30 min par jour. Les journées de pluie et les semaines creuses
  sont idéales ; 2 blocs de 2 h valent mieux que 30 soirées de lassitude.
- **Un fichier par lot de ~20 fiches** (`lot_01.csv`, `lot_02.csv`…). À la fin du lot :
  1. `python3 outils/importer_saisie.py data/saisie/lot_01.csv --simulation` → toutes les erreurs s'affichent
     d'un coup, avec le numéro de ligne du tableur ;
  2. corriger dans le tableur, relancer jusqu'à zéro erreur ;
  3. même commande **sans** `--simulation` → importé (une sauvegarde de la base est faite avant).
  Détecter une erreur sur 20 fiches coûte 2 minutes ; sur 200, une soirée.
- Relancer le même fichier ne crée pas de doublons. **Corriger une fiche déjà importée se fait dans la base**
  (DB Browser for SQLite), pas en modifiant la ligne et en réimportant.
- Après chaque lot, trois requêtes de contrôle (voir `docs/dictionnaire_donnees.md`) : travaux `non_facture`,
  fiches `prix_manquant`, adresses `a_faire`.

## Étape 4 — Dès maintenant : plus de nouveau papier

Choisis une date (ex. lundi prochain). À partir de là, **toute nouvelle demande est saisie dans la feuille
le soir même** (2–3 minutes), pas sur une nouvelle fiche papier. Notes prises sur le terrain : OK sur papier,
mais elles sont transférées le soir même. Sans cette règle, le tri de l'étape 1 ne sert à rien.

## Numériser les archives (pile C)

- Scan par lot avec le numériseur de documents de ton téléphone/iPad : **un PDF par section du classeur**
  suffit, dans `data/papier/AAAA/`. Ne renomme pas 200 fichiers un par un.
- `fichier_papier` n'est à remplir que pour les fiches que tu numérises individuellement.
- N'attends pas de l'OCR sur de l'écriture manuscrite : c'est peu fiable, et un service OCR/IA en ligne enverrait
  les noms et adresses de tes clients à un tiers, ce que tu veux justement éviter.

## Estimation (à recalibrer avec tes vrais chiffres)

Exemple pour 150 dossiers : 30 en pile A × 6 min = 3 h ; 50 en pile B × 2 min = 1 h 40 ; 70 en pile C = 0 min
de saisie + ≈ 1 h de numérisation → **≈ 6 h au total, soit ~14 blocs de 25 minutes**. Chronomètre les 10
premières fiches pour affiner.

## Sauvegarde et confidentialité

- `data/` ne va **jamais** sur GitHub ni dans un nuage (le `.gitignore` y veille). Seuls le schéma, les outils
  et les exemples fictifs sont dans le dépôt.
- Copie de `data/` chaque semaine sur une clé USB ou un disque externe ; idéalement deux copies, dont une hors
  du bureau. Active le chiffrement du disque de l'ordinateur (FileVault / BitLocker).
- Ne colle pas de vraies données clients dans une conversation avec une IA, ni dans un ticket GitHub.
