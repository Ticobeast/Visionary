# SylvainCulteur : où en est le programme (contexte pour le Projet Claude)

Mis à jour : novembre 2026. Dépôt GitHub : `ticobeast/visionary` (privé), branche de travail `claude/kind-knuth-824c6c`
(pas encore fusionnée dans `main`). Base de données : format v11. 553 tests automatiques, tous verts.

## 1. Ce que fait le programme
- **Clients** : une fiche = une personne (ou entreprise) + son adresse ; secteur choisi dans une liste fermée (pas de doublons).
  Liste « contacts » sur téléphone ; toucher un numéro lance l'appel.
- **Soumissions** : ouvertes dès l'appel du client, rien d'obligatoire. Boutons Accepter / En attente / Refuser.
  Accepter (ou En attente) demande seulement ce qui manque (nom, téléphone, adresse, secteur, travaux, durée, prix).
  Pastille d'attente (jours depuis la demande). Refusées : en bas, « Rouvrir » possible. PDF de la soumission pour le client.
- **Chantiers** : soumission acceptée. Statuts : À planifier, En attente (avec date de reprise automatique ou « jusqu'à nouvel
  ordre »), Planifié, Terminé (verrouillé en lecture seule), Annulé. Remettre en soumission, Dupliquer (travail récurrent).
  Pastilles d'attente de paiement pour les terminés non payés.
- **Tableau de bord** : calendrier du mois (sur téléphone façon calendrier Apple : point sous les jours chargés, fins de semaine
  en vert pâle, aujourd'hui en gras, cercle seulement sur le jour choisi) et la journée choisie en dessous. Une loupe en haut à
  droite de la journée donne le détail (nombre, durée, début, fin, total) : survol sur PC, toucher sur téléphone. Terminer
  (fenêtre : payé ou pas, mode, durée réelle), lien Facture, « Télécharger la journée » (PDF feuille de route avec photos).
- **Journée** : gestion d'une journée (ordre, heures calculées avec le dîner, retirer, ajouter des chantiers à placer filtrés).
- **Paiements** : sur la fiche du chantier ; jamais de solde négatif. Ajouter un paiement ne propose plus de terminer.
- **Taxes** : case « Ajouter TPS 5 % et TVQ 9,975 % ». Elle reflète la fiche (cochée si la fiche a des taxes) ; décochée puis
  enregistrée, TPS et TVQ passent à 0 (sauf retouche manuelle).
  Case cochée et prix changé : TPS et TVQ sont recalculées sur le nouveau prix (sauf retouche manuelle).
- **Documents** : PDF de soumission et de facture (logo vectoriel, NEQ, coordonnées dans outils/entreprise.py ; TPS/TVQ :
  numéros à remplir quand l'entreprise sera inscrite). Facture : administrateur seulement.
- **Photos** : carte Photos sur chaque fiche. Prendre une photo (appareil), Ajouter des photos (galerie ou ordinateur).
  Réduites par le navigateur avant l'envoi. Rangées dans data/photos/chantier-N (ou le « dossier de photos » de la fiche).
  Reprises dans le PDF de la journée. Rien dans la base.
- **Raccourcis** : pastilles personnalisables en haut de Chantiers et Soumissions ; bulle « Modifier » au bout de la rangée.
- **Archives** : historique, recherche, statistiques, regroupement par client (qui relancer), export Excel (PC seulement).
- **Comptes** : administrateur et « soumission » (pas de finances, pas de Journée). Mots de passe hachés, blocage après
  5 essais. Sans compte, l'accès à distance reste fermé.
- **Annuler / Fermer** ramènent toujours à la page d'où l'on vient.

## 2. Accès et lancement
- PC : `lancer_interface.bat` (vraie base), `lancer_essai.bat` (fausses données, data/test.db).
- Téléphones : `lancer_reseau.bat` ; adresse Tailscale `http://ticotower.tailbb6d3b.ts.net:8765/`.
- Essai sur téléphone avec les fausses données : `lancer_essai_reseau.bat` ; crée le compte d'essai `essai` / `essai1234`
  (seulement dans la base d'essai).
- Comptes réels : `gerer_utilisateurs.bat` (jamais de mot de passe réel écrit dans le dépôt ou une conversation).
- Le dossier doit être hors OneDrive/Dropbox (ex. C:\SylvainCulteur). Sauvegarde automatique quotidienne dans data/sauvegardes/.

## 3. Organisation du code (outils/)
interface.py (serveur, routes) · vue.py (gabarit, CSS PC, composants) · telephone.py (tout le style téléphone) ·
noyau.py (règles, validation, migrations) · pages_chantier.py, pages_soumissions.py, pages_clients.py, pages_attente.py ·
tableau.py (Journée), calendrier.py (tableau de bord) · raccourcis.py · archives.py · photos.py · documents.py, pdf.py, logo.py,
entreprise.py, pages_documents.py · auth.py, reseau.py · donnees_test.py. Schéma : schema/. Tests : tests/.

## 4. Mes préférences (apprises au fil des échanges)
- Français, tutoiement, aucun emoji. Captures d'écran pour valider (souvent sans accès au PC).
- PC : stable, ne pas toucher sans le dire. Téléphone : léger, Apple, flèches et icônes plutôt que des mots, cartes
  compactes, rien de répété (ex. la date prévue n'est plus répétée dans le formulaire), textes d'aide retirés.
- Style du site : boutons secondaires blancs à bordure grise (j'ai refusé le vert pâle), bouton principal vert.
- Sur téléphone, retirés volontairement : export Excel, lien « En attente » sous le titre de Chantiers, Dossier de photos,
  « Autres soumissions et chantiers » dans Paramètres avancés, textes d'aide des taxes et du statut.
- Boutons d'ajout : un « + » rond en haut à droite du titre (Clients, Soumissions).

## 5. Idées et points en attente (rien n'est commencé)
- **Croquis des haies** (en réflexion, « ne rien faire pour l'instant ») : on dessine une vue de haut de la cour et on note
  pour chaque section 1, 2 ou 3 côtés à tailler. Idée retenue comme première étape : photographier le croquis papier,
  numéroter les sections, et une liste « section, endroit, nombre de côtés » dans la fiche, reprise dans le PDF de la journée.
  Plus tard peut-être : dessin au doigt dans l'app, ou tracé par-dessus une photo de la cour.
- PDF dans l'app de l'écran d'accueil : la petite flèche « Télécharger » n'a pas été testée sur iPhone ; au besoin, ouvrir
  dans Safari. Le vrai bouton « Partager » d'iOS demanderait un accès HTTPS (possible avec Tailscale ; chantier à part).
- À vérifier sur un vrai iPhone : « Prendre une photo », largeur des champs de date.
- Pas encore là : rôle chef d'équipe (Journée et Terminer sur téléphone), équipes séparées, itinéraires.
- Numéros de TPS et TVQ à inscrire dans outils/entreprise.py quand ils existeront.
