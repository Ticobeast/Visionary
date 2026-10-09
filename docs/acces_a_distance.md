# Accès à distance : téléphones et iPads (soumissionneurs, chefs d'équipe)

Les soumissionneurs remplissent les soumissions **depuis leur téléphone ou leur iPad**. Les données restent sur **l'ordinateur de
l'atelier**, qui reste allumé : aucun nuage, aucun abonnement.

## Comment ça marche

- L'application est une page web : le téléphone l'ouvre dans son navigateur (Safari, Chrome).
- **Tailscale** (gratuit) crée un réseau privé et chiffré entre l'ordinateur et les appareils que **tu** invites. Aucun port n'est ouvert sur
  le routeur ; rien n'est visible sur Internet. Seuls les appareils de ton Tailscale (adresses 100.64.x.x à 100.127.x.x) sont acceptés.
- Une **connexion** (nom + mot de passe) est exigée ensuite, sur tous les appareils, **même sur l'ordinateur de l'atelier**.
- Aucune donnée n'est « cachée » dans une page : tant qu'on n'est pas connecté, le programme ne répond que la page de connexion.

## Adresse à utiliser

Sur le téléphone, avec Tailscale allumé : `http://ticotower.tailbb6d3b.ts.net:8765/`
(ou l'adresse `http://100.x.y.z:8765/` affichée par `lancer_reseau.bat`). Le `:8765` à la fin est obligatoire. Le navigateur peut dire
« non sécurisé » : c'est normal, la connexion est chiffrée par Tailscale.

## Installation (une seule fois)

### 1. Sur l'ordinateur de l'atelier
1. Installer Tailscale (<https://tailscale.com/download>) et ouvrir une session.
2. **Créer les comptes** : double-clic sur **`gerer_utilisateurs.bat`** (ou `python gerer_utilisateurs.py`). Choisir `A` (ajouter), taper le nom,
   répondre `o` pour un administrateur (ou `n`), puis le mot de passe (invisible pendant la saisie, à taper deux fois).
   - **Administrateur** : tout (tableau de bord, journée, PDF, finances, suppressions, comptes, **archives et statistiques**).
   - **Soumission** : soumissions, chantiers et clients : ouvrir, remplir, **accepter**, **mettre en attente** et **refuser** des soumissions, consulter les chantiers
     et les clients, **voir et télécharger le PDF d'une soumission** pour l'envoyer au client. Ni finances (donc **pas la facture** en PDF, qui montre les paiements),
     ni Terminer, ni suppression, ni journée, ni archives.
3. Double-cliquer **`lancer_reseau.bat`** (au lieu de `lancer_interface.bat`) et laisser la fenêtre ouverte.
4. Si Windows demande d'autoriser le pare-feu : accepter. Si les téléphones n'arrivent pas à se connecter, ouvrir l'**Invite de commandes en
   administrateur** et taper (une ligne ; elle n'autorise que le réseau Tailscale) :
   ```
   netsh advfirewall firewall add rule name="SylvainCulteur Tailscale" dir=in action=allow protocol=TCP localport=8765 remoteip=100.64.0.0/10
   ```

### 2. L'ordinateur reste allumé
- **Paramètres > Système > Alimentation** : mise en veille « Jamais » (branché).
- Pour un redémarrage automatique : `Windows + R`, taper `shell:startup`, y glisser un **raccourci** vers `lancer_reseau.bat`.
- La sauvegarde du jour se fait toute seule au démarrage (`data/sauvegardes`). Garder aussi une copie sur un disque externe.

### 3. Sur chaque téléphone / iPad
1. Installer **Tailscale** (App Store ou Google Play), se connecter au même compte ou y être invité
   (<https://login.tailscale.com/admin/users>). Laisser Tailscale activé.
2. Ouvrir Safari / Chrome, aller à l'adresse ci-dessus, se connecter. La session reste ouverte 30 jours.
3. **Ajouter à l'écran d'accueil** : iPhone / iPad : bouton Partager > « Sur l'écran d'accueil » ; Android : menu > « Ajouter à l'écran d'accueil ».

## Version téléphone : légère, façon application
Sur un téléphone (écran de 700 px et moins), le même programme s'affiche **autrement** : un grand titre, des cartes blanches arrondies, des champs gris
clair, des boutons faciles à toucher (44 px), des **flèches plutôt que des mots** (mois, jour) et des **icônes** (recherche, menu). L'ordinateur ne change pas.
Les couleurs et les formes suivent le site de l'entreprise : fond clair, cartes blanches à fine bordure, boutons secondaires **blancs** à bordure grise, bouton principal vert, champs blancs. La mise en forme est dans `outils/telephone.py`.

**Barre du bas** (administrateur) : **Tableau de bord**, **Clients** et le bouton **Menu** (trois barres) qui ouvre une feuille avec **Chantiers**,
**Soumissions**, **Journée**, **Archives**, **Utilisateurs** et **Se déconnecter**. Le compte « Soumission » a **Soumissions**, **Clients** et le Menu (Chantiers).
- **Tableau de bord** : un calendrier comme celui d'Apple (un point sous les jours chargés ; le fond vert pâle des fins de semaine ; le jour courant en
  gras (et en cercle vert seulement quand il est choisi), un autre jour choisi en cercle vert foncé), et dessous la journée choisie avec **Terminer** et un lien discret **Facture** en haut à droite de chaque chantier.
- **Journée** : une flèche de chaque côté de la date pour changer de jour (ou toucher la date), un seul bouton **Aujourd'hui** (en haut à droite du titre, absent quand on est déjà aujourd'hui), les quatre filtres des chantiers à placer regroupés sous un seul bouton **Filtres**, et la gestion de la journée (ordre, retirer, ajouter).
- **Chantiers** : une carte par chantier (client, statut, adresse, travaux, montant, pastille d'attente, paiement), les raccourcis en pastilles à faire défiler,
  la recherche avec la loupe à droite.
- **Soumissions** : le bouton rond **+** (en haut à droite) ouvre une nouvelle soumission ; une carte par soumission avec **Accepter**, **En attente**, **Refuser** ; le PDF est un lien discret « Soumission » en haut à droite de la carte. Les raccourcis sont des bulles qu'on fait défiler, et la dernière, **Modifier**, ouvre leur gestion (Chantiers aussi).
  Si on appuie sur Accepter (ou En attente) alors qu'il manque des renseignements, le programme demande seulement ceux qui manquent.
- **Clients** : une liste « contacts » (nom, numéro, adresse) ; **toucher un numéro lance l'appel** ; le bouton rond **+** ouvre un nouveau client.
- **Archives** : la recherche, un bouton **Filtres** qui déplie les critères, les idées de recherche et les chiffres en pastilles qu'on fait défiler, puis une carte par résultat.
- **Annuler / Fermer** : ramènent toujours à la page d'où tu viens (la liste filtrée, la fiche), même après une erreur de saisie.
- **Fiche client** : l'historique avec le statut à droite de chaque ligne, et un petit bouton **Supprimer le client** (la mise en garde s'affiche dans la fenêtre de confirmation).
- **Fiches et formulaires** : les types de travaux et les options sont des **tuiles** à cocher ; le bouton principal prend toute la largeur ; « Terminer » monte
  du bas de l'écran comme une feuille.
Le compte « Soumission » arrive directement sur **Soumissions** et n'a de toute façon jamais accès au tableau de bord, aux paiements ni aux factures.

## Deux personnes sur la même fiche
La deuxième à enregistrer reçoit « Cette fiche vient d'être modifiée par quelqu'un d'autre » ; ses changements ne sont pas enregistrés, la fiche
à jour s'affiche, et elle refait sa modification au besoin. Rien n'est écrasé en silence.

## Mots de passe et sécurité
- Les mots de passe ne sont **jamais** stockés en clair (empreinte PBKDF2 salée). Après **5 essais ratés**, le compte est bloqué 15 minutes.
- Un mot de passe de **4 chiffres est acceptable** tant que l'accès passe par ton réseau privé Tailscale (il faut d'abord être dans ton
  Tailscale, ensuite connaître le mot de passe). **Il ne l'est pas** si l'application devient accessible sur Internet : il faudra alors des
  mots de passe longs (8 caractères et plus). Éviter une année évidente comme celle de la fondation.
- **Changer un mot de passe** ou **désactiver un compte** (page « Utilisateurs » de l'administrateur, ou `gerer_utilisateurs.py`) déconnecte
  immédiatement les appareils de cette personne.
- **Téléphone perdu ou employé parti** : <https://login.tailscale.com/admin/machines> > les trois points de l'appareil > **Delete**, et
  désactiver son compte.
- N'active **jamais** « Tailscale Funnel » : ce serait rendre l'application publique.
- Ne pas copier le dossier du projet dans OneDrive / Dropbox (voir README).

## Logo
Pour afficher le logo du site dans l'application, copier `logo.svg` (ou `logo.png`) du dossier `images` du site dans **`outils/static/`**
(créer le dossier au besoin). Sans fichier, le nom « Sylvainculteur » s'affiche en lettres vertes.

## Dépannage

| Problème | Cause probable | Solution |
|---|---|---|
| Le téléphone n'ouvre pas la page | Tailscale éteint sur le téléphone, ou `lancer_reseau.bat` pas lancé | allumer Tailscale ; vérifier la fenêtre sur l'ordinateur |
| « Accès refusé » | adresse ou port incorrect, ou appareil hors de ton Tailscale | recopier l'adresse (avec `:8765`) ; vérifier la liste des appareils |
| « Aucun compte n'est encore créé » | aucun compte, l'accès à distance reste fermé | lancer `gerer_utilisateurs.bat` sur l'ordinateur |
| « Trop d'essais » | 5 mots de passe faux de suite | attendre 15 minutes (ou relancer le programme) |
| Ça marchait, plus rien le matin | ordinateur en veille, redémarré par Windows Update | désactiver la veille ; raccourci dans `shell:startup` |
| « Tailscale n'a pas été trouvé » dans la fenêtre | Tailscale pas installé / pas ouvert sur l'ordinateur | l'installer, ouvrir une session, relancer |

## Pas encore là
- Prise de **photos avec l'appareil** directement dans la soumission.
- Rôle **chef d'équipe** (Journée et Terminer sur téléphone) et **équipes** séparées.
- Mode **hors-ligne** (non prévu : l'enregistrement exige du réseau).
- Accès par un simple URL public (sans Tailscale sur les téléphones) : demande des mots de passe longs et un tunnel sécurisé.
