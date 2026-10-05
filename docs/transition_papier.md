# Transition papier → numérique

Objectif : que la base soit **utile en quelques heures** (pas en un mois), sans y passer tes soirées.

Trois leviers, dans cet ordre :

1. **Arrêter d'ajouter du papier** — sinon la pile grossit pendant que tu la vides.
2. **Trier par valeur** — ce qui rapporte ou coûte de l'argent maintenant passe en premier ; les archives ne
   sont pas retranscrites.
3. **Saisir le strict minimum**, puis enrichir la fiche quand le client rappelle.

La saisie se fait dans l'**interface** (`python3 outils/interface.py`, ou double-clic sur
`lancer_interface.bat` / `lancer_interface.command`). Avant de t'y mettre pour de vrai, suis le
[plan de mise en route et de tests](plan_de_tests.md).

---

## Étape 1 — Trier le classeur en 3 piles (≈ 1 h pour tout)

| Pile | Critère | Traitement | Temps / fiche |
|---|---|---|---|
| **A — Vivant** | soumission en attente, travaux acceptés pas faits, **travaux faits non facturés**, factures impayées | fiche **complète**, en premier | 4–6 min |
| **B — Actif** | clients servis dans les ~24 derniers mois, surtout les récurrents (haies annuelles) | fiche **minimale** | ≈ 2 min |
| **C — Archive** | anciens, ponctuels, peu de chances de rappeler | **pas de saisie** : numériser en lot (ou garder en boîte) | 0 |

La pile A a un retour immédiat : c'est de l'argent à facturer ou à récupérer. Commence par elle.
Une fiche de la pile C se retranscrit **à la demande**, en 2 minutes, le jour où le client rappelle.

## Étape 2 — La fiche minimale

Obligatoire (l'interface refuse d'enregistrer sans) :
**nom** (ou entreprise), **adresse**, **ville**, **au moins un type de travaux**, **durée estimée**, **statut**
— et la **date des travaux** si le statut est « Planifié » ou « Terminé ».

> Attention : un chantier **Terminé** est ensuite verrouillé (lecture seule). Pour des fiches papier déjà faites, relis-les avant de les saisir « Terminé ».

Recommandé : **téléphone** (rappels futurs), **prix avant taxes**, et le paiement reçu s'il y en a un.
Tout le reste reste vide : les coordonnées GPS seront remplies par le script de géocodage, les photos
s'ajouteront aux prochains chantiers.

**Client qui revient** : tape son nom dans la barre de recherche de la page « Nouveau chantier » et clique sur
sa fiche — son adresse et son téléphone sont déjà remplis, il ne reste que le travail à décrire.

**Historique déjà réglé et déjà comptabilisé ailleurs** : saisis le montant réellement payé comme « prix avant
taxes » *et* comme montant du paiement (mode « Autre » si tu ne te souviens plus), sans cocher le calcul des
taxes : le chantier sort « Payé » sans retranscrire les taxes. Contrepartie : les bilans d'avant la base seront en
montants taxes incluses. Pour les chantiers **vivants** (pile A), saisis le vrai prix avant taxes et coche
« Calculer TPS et TVQ ».

## Étape 3 — Le rythme

- **Blocs de 25 minutes**, jamais plus de 30 min par jour. Les journées de pluie et les semaines creuses
  sont idéales ; 2 blocs de 2 h valent mieux que 30 soirées de lassitude.
- L'interface valide chaque fiche **tout de suite** (dates, téléphone, code postal, montants) : une erreur se
  corrige à l'écran, pas trois semaines plus tard.
- Ordre : pile A en entier, puis pile B par ordre de récurrence.
- Après chaque bloc, regarde les **puces de la page Chantiers** : « à facturer », « à recevoir », « prix
  manquants ». Ce sont tes contrôles de qualité *et* ta liste de choses à faire.
- Une **sauvegarde automatique** de la base est faite une fois par jour au démarrage de l'interface
  (`data/sauvegardes/`).

### Option : saisir dans un tableur puis importer

Utile si tu préfères taper en rafale ou si tu reprends une liste existante. Évite Excel (il réécrit les dates
et les décimales à la sauvegarde) ; **LibreOffice Calc** (gratuit) est plus sûr : à l'ouverture du CSV, choisir
l'encodage UTF-8, le séparateur « virgule » et mettre les colonnes de dates en « Texte ». Puis :
`python3 outils/importer_saisie.py data/saisie/lot_01.csv --simulation`, corriger, puis relancer sans
`--simulation`. Voir `docs/dictionnaire_donnees.md` pour le détail des colonnes.

## Étape 4 — Dès maintenant : plus de nouveau papier

Choisis une date (ex. lundi prochain). À partir de là, **toute nouvelle demande est saisie dans l'interface
le soir même** (2–3 minutes), pas sur une nouvelle fiche papier. Notes prises sur le terrain : OK sur papier,
mais elles sont transférées le soir même. Sans cette règle, le tri de l'étape 1 ne sert à rien.

## Numériser les archives (pile C)

- Scan par lot avec le numériseur de documents de ton téléphone/iPad : **un PDF par section du classeur**
  suffit, dans `data/papier/AAAA/`. Ne renomme pas 200 fichiers un par un.
- Le champ « Scan de la fiche » n'est à remplir que pour les fiches que tu numérises individuellement.
- N'attends pas de l'OCR sur de l'écriture manuscrite : c'est peu fiable, et un service OCR/IA en ligne enverrait
  les noms et adresses de tes clients à un tiers, ce que tu veux justement éviter.

## Estimation (à recalibrer avec tes vrais chiffres)

Exemple pour 150 dossiers : 30 en pile A × 5 min = 2 h 30 ; 50 en pile B × 2 min = 1 h 40 ; 70 en pile C = 0 min
de saisie + ≈ 1 h de numérisation → **≈ 5 h au total, soit ~12 blocs de 25 minutes**. Chronomètre les 10
premières fiches (phase 2 du plan de tests) pour affiner.

## Sauvegarde et confidentialité

- `data/` ne va **jamais** sur GitHub ni dans un nuage (le `.gitignore` y veille). Seuls le schéma, les outils
  et les exemples fictifs sont dans le dépôt.
- Copie de `data/` chaque semaine sur une clé USB ou un disque externe ; idéalement deux copies, dont une hors
  du bureau. Active le chiffrement du disque de l'ordinateur (FileVault / BitLocker).
- Ne colle pas de vraies données clients dans une conversation avec une IA, ni dans un ticket GitHub.
