# Style de l'interface

Les règles à suivre pour toute page, nouvelle ou modifiée, sur iPhone et sur PC. Le but : une interface minimaliste, complète,
et pareille partout. Si une règle ne convient plus, on la change ici d'abord, puis partout.

## Couleurs et formes

- Celles du site de l'entreprise : vert principal #4a7a28, vert foncé #0e341d, fond #fbfbf9, bordures #dbe2d6 et #ecefe9.
- Cartes blanches arrondies, à fine bordure.
- Bouton principal : vert plein. Boutons secondaires : blancs à bordure grise (jamais vert pâle).
- Aucun emoji. Seules exceptions : les flèches ▲ ▼ pour l'ordre de la journée.

## Une page

1. **Le titre est le nom de la chose** : le nom du client sur sa fiche, sur un chantier, sur une soumission. Le numéro
   (« Chantier n° 8 ») est écrit en petit dans la première carte.
2. **Une flèche de retour en haut de chaque fiche** (« ‹ Chantiers », « ‹ Accueil », « ‹ Client ») : elle ramène à la page
   d'où l'on vient. Les pages principales n'en ont pas : la barre du bas (iPhone) ou le menu du haut (PC) suffit.
3. **Une seule action principale par page**, en vert plein (Accepter, Terminer, + Nouvelle soumission). Les autres actions sont
   des boutons blancs.
4. **Ce qui change la fiche est replié sous « Modifier »**, en bas : le formulaire, et les gestes rares ou dangereux
   (nouvelle adresse, fusionner, annuler, supprimer).
5. **Sur iPhone, l'action principale est bien visible, les autres sont derrière « ··· »**, juste à côté
   (ex. Accepter, puis « ··· » : En attente, Refuser, Dupliquer ; + Nouvelle soumission, puis « ··· » : Modifier le client,
   Nouvelle adresse). S'il n'y a pas d'action principale, rien n'est caché : un « ··· » tout seul ne dit pas quoi faire.
   Sur PC, les boutons restent côte à côte.
6. **Aucun texte d'aide.** Si un bouton a besoin d'une explication, c'est le bouton qu'il faut changer.
7. **Rien en double.** Un même lien ou bouton ne paraît qu'une fois sur une page (ex. le PDF de la soumission : seulement dans
   « Documents pour le client ») ; une pastille ne répète pas ce qui est écrit à côté ; un surtitre ne répète pas le titre.
   Le test automatique `tests/test_doublons.py` le vérifie sur les fiches, pour l'ordinateur et pour le téléphone.

## Une fiche (chantier, soumission ou client)

Toujours dans cet ordre :

1. Le résumé (chantier, soumission) : numéro, statut, travaux, date, prix.
2. **La carte de contact**, la même partout :
   - l'adresse courte (rue, ville), le téléphone et le courriel en gris, l'accès : du texte à lire, sans lien ;
   - les boutons ronds **Appeler, Texto, Courriel, Itinéraire** : la seule façon d'agir. Un bouton qui n'a pas de sens
     n'apparaît pas (pas de courriel, textos refusés, pas d'adresse) ;
   - sur un chantier ou une soumission, un petit lien « Fiche client ».
3. L'action principale (et « ··· » sur iPhone), puis les sections (Documents, Photos, Paiements ; l'historique sur un client).
   Sur la fiche d'un client, sur PC, « + Nouvelle soumission » est dans la carte de contact, à gauche d'Appeler.
4. « Modifier », replié.

## Une liste

- **Toute la carte (ou la ligne, sur PC) s'ouvre d'un toucher.** Pas de boutons sur la carte.
- **Les actions rapides** (Accepter, En attente, Refuser, PDF) sont derrière le petit bouton **« ··· »** de la carte,
  sur iPhone comme sur PC : on agit sans quitter la liste.
- **Dans une liste, le numéro de téléphone se touche pour appeler.** Sur une fiche, il se lit : on appelle par le bouton rond.
- Par défaut, on montre ce qui est en cours. Le reste (terminés, archives) se voit avec une pastille ou une recherche.

## Les mots et les nombres

- Dates : « ven. 4 déc. » ; une autre année : « 12 avril 2025 » ; dans une phrase : « prévu demain », « reprise le lun. 1er juin ».
- Prix : le total en gros, puis « 470,00 $ + tx » en petit. Le détail des taxes est sur le PDF.
- Téléphone : « 819-555-0107 ». Adresse : « 1650 Rue des Érables, Bécancour ».
- Tutoiement dans l'interface ; vouvoiement dans ce qui part au client (textos, courriels, PDF).

## Téléphone et PC

- Le style du téléphone est dans `outils/telephone.py`, dans un seul bloc. Une demande « pour le téléphone » ne change pas le PC.
- Barre du bas de l'iPhone : Accueil, Soumissions, Chantiers, Clients, puis le menu (Journée, Archives, Utilisateurs).
- Sur PC, les listes gardent leurs colonnes. Les fiches suivent les mêmes règles que sur le téléphone.
- Tableau de bord sur PC : le grand calendrier (nombre de chantiers, temps total, montant total dans chaque case), puis la
  journée choisie dessous. Validé par l'utilisateur : ne pas le changer sans son accord.
