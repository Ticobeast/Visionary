---
name: design-sylvainculteur
description: Comment concevoir et modifier l'interface de SylvainCulteur (iPhone et PC) pour qu'elle soit belle, claire et agréable pour l'utilisateur. À suivre AVANT tout changement visible (page, bouton, disposition, style, animation), et pour toute revue de l'interface.
---

# Concevoir l'interface de SylvainCulteur

L'interface sert une petite entreprise d'émondage au Québec : le propriétaire au bureau (PC) et ses chefs d'équipe sur la route
(iPhone, souvent d'une main, dehors, pressés). Elle doit être claire au premier coup d'œil, familière, et agréable.

Ce skill existe parce qu'un assistant a déjà changé des écrans que l'utilisateur aimait, sur la seule foi de règles générales.
L'œil de l'utilisateur est la référence. Les règles ci-dessous aident à proposer ; c'est lui qui décide.

## 1. Façon de travailler (obligatoire)

1. **Ce qui est validé ne bouge pas sans accord.** Liste plus bas. Pour y toucher : proposer d'abord, en image.
2. **Montrer, et faire valider.** Tout changement visible : captures AVANT / APRÈS (iPhone 390 px, et PC si touché), envoyées à
   l'utilisateur, avec la mention « à valider ». L'espace de travail est temporaire : le travail doit être enregistré et poussé
   sur la branche de travail à la fin de chaque tour, sinon il peut être perdu. Donc : on pousse, mais un changement visible
   reste « à valider » tant que l'utilisateur n'a pas dit oui ; on ne bâtit rien par-dessus, et s'il refuse, on le retire tout
   de suite (un commit par changement visible, pour pouvoir le retirer proprement). Rien ne va dans `main` sans son accord.
3. **Quand il dit « ça me gosse » sans savoir quoi** : nommer 2 ou 3 causes possibles, et proposer 2 ou 3 variantes en image.
   Il choisit. Ne pas tout refaire d'un coup selon une seule idée.
4. **Une chose à la fois.** Un changement visible par proposition ; pas de refonte de plusieurs écrans en même temps.
5. **Se relire sur capture avant de montrer** : texte coupé ou qui déborde, mot coupé en deux, bouton seul sur sa ligne,
   éléments qui se chevauchent, doublons (`tests/test_doublons.py`), règle du PC qui déborde sur l'iPhone (et l'inverse).
   Regarder chaque capture pour de vrai, à la taille réelle.
6. **Garder la trace** : un essai refusé est noté dans `docs/projet_claude/2_contexte_et_historique.md` (pour ne pas le reproposer).

## 2. Écrans validés par l'utilisateur (ne pas changer sans son accord)

- Tableau de bord du PC : le GRAND calendrier (dans chaque case : nombre de chantiers, temps total, montant total), puis la
  journée choisie dessous. Essai refusé : calendrier compact à gauche et journée à droite (« l'original utilisait mieux l'espace »).
- Fiche d'un chantier ou d'une soumission : le nom en titre, la carte du travail (numéro, travaux, date, prix « + tx »), puis la
  carte de contact (adresse, téléphone, boutons ronds Appeler, Texto, Courriel, Itinéraire, lien « Fiche client »), puis le bouton
  vert et « ··· » (iPhone). Essai refusé : en-tête façon fiche Contacts avec des tuiles, placé avant le travail.
- Calendrier de l'iPhone (façon Calendrier d'Apple, points sous les jours).
- Barre du bas de l'iPhone : Accueil, Soumissions, Chantiers, Clients, puis le menu.
- Listes : numéro de téléphone cliquable ; actions rapides derrière « ··· ».
- Style du site de l'entreprise (couleurs, boutons blancs à bordure grise, cartes blanches) : voir CLAUDE.md.
- Toutes les autres règles écrites dans `docs/style_interface.md`.

## 3. Ce qui fait une bonne interface pour un humain

Références : les 10 règles de Nielsen Norman Group (skill `nielsen-usability-heuristics`, à relire pour toute revue), la loi de
Jakob (lawsofux.com), les principes d'Apple (hiérarchie, harmonie, cohérence).

- **Familiarité d'abord (loi de Jakob).** Les gens passent leur journée dans d'autres applications (Calendrier, Contacts,
  Messages) et dans celle-ci telle qu'ils la connaissent. Ce qui est connu gagne sur ce qui est « mieux » en théorie.
  Ne pas déplacer ce qui fonctionne.
- **Utiliser l'espace.** Sur PC, l'écran est grand : montrer l'information d'un coup d'œil (ex. les heures et les montants dans
  les cases du calendrier) plutôt que la cacher pour faire « épuré ». Minimaliste ne veut pas dire cacher l'utile
  (Nielsen 6 : reconnaître plutôt que se souvenir ; Nielsen 8 : enlever le superflu, pas l'essentiel).
- **Hiérarchie.** Sur chaque écran, une chose qu'on voit en premier : l'action principale (vert plein), puis le reste en plus discret.
- **Cohérence.** La même action a le même nom, la même place et la même allure partout (Nielsen 4).
- **Toujours savoir ce qui se passe** (Nielsen 1) : chaque action donne un retour visible en moins d'une seconde (message,
  changement d'état, animation courte).
- **Toujours pouvoir revenir** (Nielsen 3) : flèche de retour, Annuler, confirmation avant ce qui est définitif.
- **Les mots de l'utilisateur** (Nielsen 2) : « soumission », « chantier », « journée », jamais un terme technique.
- **Doigt et soleil** (iPhone) : zones à toucher d'au moins 44 px, contraste franc, rien d'important dans un coin minuscule.

## 4. Animations

Une animation répond à un geste de la personne et montre ce qui a changé ; elle ne décore pas.

- Durées (Nielsen Norman Group) : 100 ms pour un petit retour (case, bouton), 200 à 300 ms pour ce qui apparaît (menu « ··· »,
  fenêtre Terminer, section « Modifier » qui s'ouvre), 400 ms au plus pour un grand déplacement. L'entrée un peu plus longue que la sortie.
- Plus une animation revient souvent, plus elle est courte et discrète.
- Pas d'apparition en cascade de chaque carte au chargement de la page, pas d'effet sur chaque survol : ça fait gadget.
- Toujours respecter le réglage « Réduire les animations » du téléphone (`@media (prefers-reduced-motion: reduce)`).
- Uniquement en CSS (transition, @keyframes) ou quelques lignes de JavaScript : pas de bibliothèque (CLAUDE.md).

## 5. Contraintes techniques à ne pas oublier

- Le style du téléphone est dans `outils/telephone.py` (un seul bloc `@media (max-width:700px)`). Une règle du PC plus précise
  qu'une règle du téléphone l'emporte sur le téléphone aussi : vérifier la précision des sélecteurs (bogue déjà arrivé avec
  le menu « ··· »).
- Captures : Chromium et Playwright sont installés ; base d'essai : `python3 outils/donnees_test.py --db <fichier>` puis
  `python3 outils/interface.py --db <fichier> --sans-navigateur --port 8799`.
