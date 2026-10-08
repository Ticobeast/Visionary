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

## Version téléphone : volontairement simple
Sur un téléphone, il n'y a que ce qu'il faut pour une soumission, avec une barre en bas : **Chantiers**, **Soumissions**, **Clients** et **+ Soumission**.
- **Chantiers** : la liste (une carte par chantier accepté), avec les pastilles de raccourcis et la recherche.
- **Soumissions** : la liste des soumissions en cours (une carte chacune) avec, sur chaque carte, les boutons **Accepter**, **En attente** et **Refuser**, puis
  **Voir PDF** et **Télécharger PDF** (la soumission à envoyer au client : sur téléphone, le PDF s'ouvre et se partage avec les boutons de l'appareil) ; en bas, les refusées.
  Si on appuie sur Accepter (ou En attente) alors qu'il manque des renseignements, le programme demande seulement ceux qui manquent.
- **Clients** : la liste, avec recherche ; la fiche d'un client permet d'ouvrir une nouvelle soumission.
- **+ Soumission** : on ouvre une soumission dès que le client appelle (rien n'est obligatoire : on remplit ce qu'on sait ; le formulaire propose d'abord de
  chercher si le client existe déjà).
Le tableau de bord et la Journée n'apparaissent pas sur téléphone ; ils restent sur l'ordinateur (administrateur).
Le compte « Soumission » arrive directement sur **Soumissions** et n'a de toute façon jamais accès à ces pages.

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
