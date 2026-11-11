# Règles du projet SylvainCulteur (à lire avant toute modification)

Programme de gestion local et privé de SylvainCulteur (émondage, élagage, taille de haies, Québec) :
clients, soumissions, chantiers, journées, paiements, PDF, photos. Voir README.md et docs/.

## Avec l'utilisateur
- Toujours en français, en le tutoyant. Phrases simples, pas de jargon.
- Aucun emoji nulle part (code, interface, PDF, docs, commits). Seules exceptions : les flèches ▲ ▼ de l'interface.
- L'utilisateur n'a souvent pas accès à son PC : pour tout changement visible, envoyer des captures (téléphone 390 px, et PC si touché).
- « Simple par défaut » : les options rares vont dans « Paramètres avancés ».
- La version PC est jugée bonne : ne pas la modifier sans le dire. Le style du téléphone est dans outils/telephone.py
  (un seul bloc @media (max-width:700px)) ; une demande « pour téléphone » ne doit pas changer l'ordinateur.
- Style : celui du site de l'entreprise. Vert principal #4a7a28, vert foncé #0e341d, fond #fbfbf9, bordures #dbe2d6 / #ecefe9.
  Bouton principal vert plein ; boutons secondaires BLANCS à bordure grise (jamais vert pâle) ; cartes blanches arrondies à fine bordure.

## Contraintes techniques
- Python 3.9+ (le PC a 3.9.13), bibliothèque standard SEULEMENT (Pillow facultatif pour les photos du PDF). Pas de framework.
- Compatible 3.9 : pas de barre oblique inverse ni de guillemets identiques imbriqués dans les expressions d'une f-string.
- Windows + bouton « Exécuter » de VS Code ; lanceurs .bat / .command / .py à la racine.
- 100 % local : SQLite (data/), serveur sur 127.0.0.1 ; accès à distance seulement par Tailscale (outils/reseau.py).
- Le dossier du projet ne doit pas être dans OneDrive ou Dropbox.

## Données et secrets
- Jamais de vraies données de clients dans Git (data/ et *.db sont ignorés). Exemples fictifs seulement (téléphones 555-01xx).
- Jamais de mot de passe réel dans le dépôt, la doc ou les commits. Le seul mot de passe écrit est celui du compte d'ESSAI
  (base de fausses données) : essai / essai1234.

## Avant de livrer
- Tests : `python3 -m unittest discover -s tests` (tous doivent passer ; idéalement aussi avec Python 3.10 et 3.9).
- Mettre à jour la doc touchée (README.md, docs/*.md, docs/plan_de_tests.md pour les scénarios à vérifier à la main).
- Commits : sujet en français SANS accents (ex. « Telephone : ... »), corps en liste ; pas de nom de modèle dans les fichiers.
- Ne pas créer de pull request sans qu'on la demande.
