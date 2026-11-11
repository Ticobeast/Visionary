# Passer au Projet « SylvainCulteur » dans l'app Claude

Ce dossier contient ce qu'il faut pour qu'une conversation dans le Projet reparte exactement où on en est.

## Créer le Projet (une seule fois, environ 5 minutes)
1. Dans l'app Claude (ou claude.ai) : **Projets** > **Créer un projet**. Nom : `SylvainCulteur`.
   Description : « Programme de gestion local : soumissions, chantiers, journées, téléphone. »
2. **Instructions du projet** : copie tout le texte de `1_instructions_du_projet.md` (à partir de la ligne de tirets) et colle-le.
3. **Connaissances du projet** (Project knowledge) : ajoute
   - le fichier `2_contexte_et_historique.md` (où en est le programme, décisions, idées en attente) ;
   - si ton compte le permet, le dépôt GitHub `ticobeast/visionary` (bouton GitHub dans les connaissances : choisis
     README.md, CLAUDE.md, docs/ et outils/). Sinon, téléverse README.md, CLAUDE.md et les fichiers de docs/.
   Attention : la synchronisation GitHub lit la branche principale (`main`). Tant que le travail récent n'est pas
   fusionné dans `main`, ajoute plutôt les fichiers à la main, ou fais fusionner la branche d'abord.
4. Pour CODER (modifier le programme), ouvre une session Claude Code sur le dépôt : le fichier CLAUDE.md à la racine
   lui donne les mêmes règles. Les conversations du Projet servent à discuter, préparer et décider.

## Garder le Projet à jour
- Après un gros changement, remplace `2_contexte_et_historique.md` dans les connaissances par la nouvelle version du dépôt.
- Si GitHub est connecté : bouton « Synchroniser » dans les connaissances.
