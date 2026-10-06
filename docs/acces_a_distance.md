# Accès à distance : téléphones et iPads (soumissionneurs, chefs d'équipe)

Les soumissionneurs remplissent les soumissions et les chefs d'équipe ajustent leur journée et terminent les chantiers **depuis leur
téléphone ou leur iPad**, partout où il y a du réseau cellulaire. Les données restent sur **l'ordinateur de l'atelier** (qui reste allumé) :
aucun nuage, aucun abonnement.

## Comment ça marche

- L'application est déjà une page web : le téléphone l'ouvre dans son navigateur (Safari, Chrome). Rien à installer d'autre qu'**une
  application gratuite, Tailscale**.
- **Tailscale** crée un réseau privé et chiffré entre ton ordinateur et les appareils que **tu** invites. Aucun port n'est ouvert sur ton
  routeur ; l'application n'est **pas** visible sur Internet.
- Il n'y a pas de comptes dans l'application (pour l'instant) : **la porte d'entrée, c'est Tailscale**. Seuls les appareils de ton Tailscale
  (adresses 100.64.x.x à 100.127.x.x) sont acceptés. Le Wi-Fi de l'atelier et Internet sont refusés, même si quelqu'un trouvait le port.

## Installation (une seule fois, environ 20 minutes)

### 1. Sur l'ordinateur de l'atelier
1. Installer Tailscale : <https://tailscale.com/download> (Windows), puis ouvrir une session (compte Google ou Microsoft au nom de l'entreprise).
2. Double-cliquer **`lancer_reseau.bat`** (au lieu de `lancer_interface.bat`). La fenêtre affiche :
   `Sur les téléphones / iPads :  http://100.x.y.z:8765/`. **Note cette adresse.**
3. Si Windows demande d'autoriser le pare-feu : accepter. Si les téléphones n'arrivent pas à se connecter, ouvre **Invite de commandes en
   administrateur** et tape (une seule ligne ; elle n'autorise que le réseau Tailscale) :
   ```
   netsh advfirewall firewall add rule name="SylvainCulteur Tailscale" dir=in action=allow protocol=TCP localport=8765 remoteip=100.64.0.0/10
   ```

### 2. L'ordinateur reste allumé
- **Paramètres > Système > Alimentation** : mise en veille « Jamais » (branché).
- Pour que l'application redémarre seule après une coupure de courant ou une mise à jour : appuie sur `Windows + R`, tape `shell:startup`,
  et glisse-y un **raccourci** vers `lancer_reseau.bat` (clic droit > Créer un raccourci). L'ouverture de session Windows doit se faire
  automatiquement (ou quelqu'un se connecte le matin).
- La sauvegarde du jour se fait toute seule au démarrage (`data/sauvegardes`).

### 3. Sur chaque téléphone / iPad
1. Installer l'application **Tailscale** (App Store ou Google Play) et ouvrir une session. Pour que l'appareil rejoigne **ton** réseau : sur
   <https://login.tailscale.com/admin/users>, **Invite** chaque personne (courriel), ou connecte-toi toi-même sur l'appareil.
   Vérifie sur tailscale.com/pricing le nombre d'utilisateurs inclus dans le plan gratuit.
2. Laisser Tailscale activé (le commutateur en haut doit être allumé).
3. Ouvrir Safari (ou Chrome) et aller à `http://100.x.y.z:8765/` (l'adresse notée plus haut). Le navigateur peut dire « non sécurisé » :
   c'est normal, la connexion est chiffrée par Tailscale.
4. **Ajouter à l'écran d'accueil** : iPhone / iPad : bouton Partager > « Sur l'écran d'accueil » ; Android : menu > « Ajouter à l'écran
   d'accueil ». L'icône ouvre l'application comme une vraie app.

## Utilisation au quotidien
- **Soumissionneur** : Clients > **+ Nouveau client** (nom, adresse, secteur, travaux, durée, prix). Sur un client existant : **+ Nouveau chantier**.
- **Chef d'équipe** : **Journée** (ordre des chantiers, Retirer, Terminer avec « payé ou pas ») ; **Tableau de bord** pour voir la journée et
  **télécharger le PDF** (toutes les infos, adresses cliquables vers Google Maps).
- L'affichage s'adapte au téléphone : une carte par chantier, gros boutons.
- **Deux personnes sur la même fiche** : la deuxième à enregistrer reçoit « Cette fiche vient d'être modifiée par quelqu'un d'autre » ; ses
  changements ne sont pas enregistrés, la fiche à jour s'affiche, et elle refait sa modification au besoin. Rien n'est écrasé en silence.

## Sécurité : à savoir
- **Sans comptes, toute personne de ton Tailscale peut tout faire** (y compris supprimer un client). N'invite que des personnes de confiance.
- **Téléphone perdu ou employé parti** : <https://login.tailscale.com/admin/machines> > les trois points de l'appareil > **Delete** (et
  retire la personne dans *Users*). Son accès est coupé immédiatement.
- N'active **jamais** « Tailscale Funnel » : ce serait rendre l'application publique.
- Ne pas copier le dossier du projet dans OneDrive / Dropbox (voir README).

## Dépannage

| Problème | Cause probable | Solution |
|---|---|---|
| Le téléphone n'ouvre pas la page | Tailscale éteint sur le téléphone, ou `lancer_reseau.bat` pas lancé | allumer Tailscale ; vérifier la fenêtre sur l'ordinateur |
| « Accès refusé » | adresse ou port incorrect, ou l'appareil n'est pas dans ton Tailscale | recopier l'adresse affichée par `lancer_reseau.bat` ; vérifier la liste des appareils |
| Ça marchait, plus rien le matin | ordinateur en veille, redémarré par Windows Update | désactiver la veille ; raccourci dans `shell:startup` |
| La fenêtre dit « Tailscale n'a pas été trouvé » | Tailscale pas installé / pas ouvert sur l'ordinateur | l'installer, ouvrir une session, relancer |
| « Cette fiche vient d'être modifiée… » | quelqu'un d'autre a enregistré avant toi | relire les valeurs à jour, refaire la modification |

## Pas encore là (étapes suivantes possibles)
- Prise de **photos avec l'appareil** directement dans la soumission (pour l'instant les photos se rangent dans le dossier du chantier).
- **Comptes** et rôles (soumissionneur / chef d'équipe / administrateur) et **équipes** séparées : à ajouter quand l'entreprise grandira.
- Mode **hors-ligne** (sans réseau) : non prévu ; l'enregistrement exige du réseau.
