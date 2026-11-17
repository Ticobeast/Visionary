"""Éléments d'affichage partagés par toutes les pages : styles, gabarit, composants de formulaire."""
import datetime
import hashlib
import html
import json
import re
import threading
from pathlib import Path
from urllib.parse import quote

from telephone import CSS_TELEPHONE  # noqa: F401  (feuille de style du téléphone)
from noyau import DB_DEFAUT, LIBELLES_MODE, LIBELLES_STATUT, MODES, adresses, libelle_statut  # noqa: F401  (réexportés pour les pages)

LIBELLES_PAIEMENT = {"a_payer": "À recevoir", "partiel": "Partiel",
                     "paye": "Payé", "a_venir": "À venir", "sans_objet": "—", "prix_manquant": "Prix manquant"}
MESSAGES = {
    "cree": "Chantier créé.",
    "cree_reutilise": "Chantier créé pour un client déjà dans la base (même adresse) : sa fiche a été réutilisée.",
    "maj": "Modifications enregistrées.",
    "paiement": "Paiement ajouté.",
    "photo_supprimee": "Photo supprimée.",
    "paiement_supprime": "Paiement supprimé.",
    "supprime": "Chantier supprimé.",
    "statut_change": "Statut mis à jour.",
    "annule": "Chantier annulé : il a disparu de la journée et il est dans les archives.",
    "rouvert": "Chantier rouvert : il redevient « À planifier ».",
    "termine": "Chantier terminé : il est maintenant verrouillé (le client est considéré comme facturé).",
    "termine_paye": "Chantier terminé et payé : il est verrouillé et déplacé dans les archives.",
    "secteur_ajoute": "Secteur ajouté.",
    "secteur_maj": "Secteur renommé.",
    "secteur_supprime": "Secteur supprimé.",
    "encaisse": "Paiement enregistré.",
    "planifie_lot": "Chantiers planifiés pour la journée.",
    "retire": "Chantier retiré de la journée : il redevient « À planifier ».",
    "deplace": "Ordre de passage mis à jour : les heures sont recalculées.",
    "client_maj": "Fiche client enregistrée.",
    "client_supprime": "Client supprimé.",
    "nouvelle_adresse": "Nouvelle fiche créée à la nouvelle adresse. L'ancienne fiche garde son historique.",
    "fusion": "Les deux fiches sont fusionnées. Tout l'historique est visible sur cette fiche.",
    "soumission_creee": "Soumission créée.",
    "soumission_reutilisee": "Soumission créée pour un client déjà dans la base (même adresse) : sa fiche a été réutilisée.",
    "soumission_acceptee": "Soumission acceptée : elle est maintenant dans Chantiers, à planifier.",
    "soumission_refusee": "Soumission refusée : elle est dans les soumissions refusées (en bas de la liste).",
    "soumission_rouverte": "Soumission rouverte : elle redevient une soumission en cours.",
    "soumission_supprimee": "Soumission supprimée.",
    "remise_soumission": "Chantier remis en soumission.",
    "mis_en_attente": "Mis en attente : il est dans Chantiers (statut « En attente ») et n'est plus proposé dans la Journée. Sa date de reprise est sur sa fiche.",
    "attente_modifiee": "Attente modifiée.",
    "sorti_attente": "Sorti de l'attente : il est de nouveau « À planifier ».",
    "raccourci_ajoute": "Raccourci ajouté.",
    "raccourci_retire": "Raccourci retiré.",
    "raccourcis_reinitialises": "Raccourcis rétablis comme au départ.",
    "utilisateur_cree": "Compte créé.",
    "mdp_change": "Mot de passe changé : l'appareil de cette personne devra se reconnecter.",
    "utilisateur_maj": "Compte mis à jour.",
    "client_cree": "Chantier créé pour ce client.",
    "duplique": "Nouvelle soumission créée d'après le chantier précédent : ajuste le prix si besoin.",
}

CSS = """
:root{--vert-fonce:#0e341d;--vert:#4a7a28;--vert-doux:#f4f8f2;--vert-bord:#d4e8cb;
--fond:#fbfbf9;--carte:#fff;--texte:#0e341d;--doux:#64748b;--para:#334155;--trait:#dbe2d6;--trait-leger:#ecefe9;--puce:#f3f5f1;
--accent:#4a7a28;--accent-fonce:#0e341d;--alerte:#b42318;--alerte-fond:#fef3f2;--alerte-bord:#fecdca;--ok-fond:#f4f8f2;
--ombre-sm:0 2px 8px rgba(15,23,42,.04);--ombre-md:0 12px 24px rgba(15,23,42,.07);--ombre-btn:0 4px 14px rgba(74,122,40,.25);
--ease:cubic-bezier(.16,1,.3,1)}
*{box-sizing:border-box}body{margin:0;background:var(--fond);color:var(--texte);font:16px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main a{color:var(--accent-fonce)}main{max-width:1100px;margin:0 auto;padding:16px}h1{font-size:22px;margin:8px 0 16px}h2{font-size:17px;margin:0 0 12px}
.carte{background:var(--carte);border:1px solid var(--trait);border-radius:10px;padding:16px;margin-bottom:16px}
.grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
label{display:block;font-size:14px;color:var(--doux);margin-bottom:2px}
input,select,textarea{width:100%;padding:9px 10px;border:1px solid var(--trait);border-radius:8px;background:var(--carte);color:var(--texte);font:inherit}
input[type=checkbox]{width:auto;margin-right:6px}textarea{min-height:70px}
.large{grid-column:1/-1}
button,.bouton{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 16px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
button.secondaire,.bouton.secondaire{background:transparent;color:var(--accent-fonce);border:1px solid var(--accent)}
button.danger{background:transparent;color:var(--alerte);border:1px solid var(--alerte)}
.puces{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
.puce{background:var(--carte);border:1px solid var(--trait);border-radius:10px;padding:10px 14px;text-decoration:none;color:var(--texte);min-width:150px}
.puce b{display:block;font-size:20px}.puce span{color:var(--doux);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--carte);border:1px solid var(--trait);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--trait);vertical-align:top;font-size:15px}
td:first-child,td.droite{white-space:nowrap}th{font-size:13px;color:var(--doux);font-weight:600}tr:last-child td{border-bottom:0}td a{color:var(--accent-fonce);font-weight:600;text-decoration:none}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:13px;border:1px solid var(--trait);white-space:nowrap}
.b-prix_manquant{background:#fff1d6;color:#7a4b00;border-color:#e8c675}.b-a_payer{background:var(--alerte-fond);color:var(--alerte);border-color:var(--alerte)}
.b-partiel{background:#e3eefb;color:#1e4d86;border-color:#9cbbe3}.b-paye,.b-termine{background:var(--ok-fond);color:var(--accent-fonce);border-color:var(--accent)}
.erreurs{background:var(--alerte-fond);border:1px solid var(--alerte);color:var(--alerte);border-radius:10px;padding:12px 16px;margin-bottom:16px}
.erreurs ul{margin:6px 0 0 18px;padding:0}.message{background:var(--ok-fond);border:1px solid var(--accent);border-radius:10px;padding:10px 16px;margin-bottom:16px}
.doux{color:var(--doux);font-size:14px}.droite{text-align:right}.barre{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.recherche{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}.recherche input{flex:1 1 260px;min-width:180px}.recherche select{width:auto;max-width:210px;flex:0 1 auto}.recherche button{flex:0 0 auto}
.type{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:10px;align-items:center;margin-bottom:8px}
.type label.coche{display:flex;align-items:center;margin:0;color:var(--texte);font-size:16px}
.base{font-size:13px;color:var(--doux)}.base.essai{background:#fff1d6;color:#7a4b00;border:1px solid #e8c675;border-radius:99px;padding:2px 10px;font-weight:600}
@media (max-width:600px){.type{grid-template-columns:1fr}}
main.large{max-width:1500px}.liste-defile{overflow-x:auto}table.tableau .mini{flex-wrap:nowrap}table.tableau td.col-actions{min-width:200px}.actions-ligne{display:flex;gap:8px;align-items:center;flex-wrap:nowrap}.actions-ligne form{margin:0}.actions-ligne .bouton,.actions-ligne button{padding:7px 14px;font-size:14px;white-space:nowrap}table.tableau th,table.tableau td{font-size:14px;padding:8px}table.tableau td:first-child{white-space:normal}
.attente{display:inline-block;border-radius:6px;padding:2px 8px;font-weight:700;font-size:13px;white-space:nowrap;border:1px solid var(--trait)}
.a-normale{background:var(--ok-fond);color:var(--accent-fonce);border-color:var(--accent)}
.a-surveiller{background:#fff1d6;color:#7a4b00;border-color:#e8c675}
.a-urgente{background:var(--alerte-fond);color:var(--alerte);border-color:var(--alerte)}
tr.ligne-urgente td:first-child{box-shadow:inset 4px 0 0 var(--alerte)}tr.ligne-surveiller td:first-child{box-shadow:inset 4px 0 0 #e8c675}
h2.groupe{margin:20px 0 8px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}h2.groupe small{color:var(--doux);font-weight:400;font-size:14px}
.mini{display:flex;gap:4px;flex-wrap:wrap;align-items:center;margin:0 0 4px}.mini select,.mini input{width:auto;padding:5px 6px;font-size:13px;min-width:0}
.mini input[type=date]{width:128px}.mini input.court{width:64px}.mini button{padding:5px 10px;font-size:13px}
.onglets{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}.onglet{padding:7px 14px;border:1px solid var(--trait);border-radius:99px;text-decoration:none;color:var(--texte);background:var(--carte)}
.onglet.actif{background:var(--accent);color:#fff;border-color:var(--accent)}
.verrou{background:var(--fond);border:1px dashed var(--doux);border-radius:10px;padding:12px 16px;margin-bottom:16px}.verrou b{font-size:17px}
.total{font-weight:700}.barre-filtres .chercher-filtres{display:none}.filtres:has(.filtres-det[open]) .barre-filtres .chercher-filtres{display:inline-flex}
.actions-sec{display:contents}.tel-bloc{display:none}
.menu-rapide{position:relative;display:inline-block}.menu-rapide.menu-fiche{display:none}.menu-rapide[open]{z-index:6}
.menu-rapide>summary{list-style:none;width:40px;height:34px;border-radius:10px;cursor:pointer;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%230e341d'%3E%3Ccircle cx='5' cy='12' r='2'/%3E%3Ccircle cx='12' cy='12' r='2'/%3E%3Ccircle cx='19' cy='12' r='2'/%3E%3C/svg%3E") center/20px no-repeat}
.menu-rapide>summary::-webkit-details-marker{display:none}.menu-rapide>summary:hover,.menu-rapide[open]>summary{background-color:var(--puce)}
.menu-rapide-liste{position:absolute;right:0;top:40px;z-index:6;min-width:210px;display:flex;flex-direction:column;gap:6px;padding:8px;background:#fff;border:1px solid var(--trait-leger);border-radius:16px;box-shadow:0 12px 32px rgba(14,52,29,.2)}
.menu-rapide-liste .mini{display:block;margin:0}.menu-rapide-liste .bouton,.menu-rapide-liste button{width:100%;justify-content:center}
.menu-rapide-liste .lien-pdf{position:static!important;padding:8px 12px!important;border:1px solid var(--trait)!important;background:#fff!important;font-size:14px!important;color:var(--texte)!important;text-decoration:none;text-align:center}
table.soumissions tbody tr,table.chantiers tbody tr,table.clients tbody tr{position:relative}@media (hover:hover){table.soumissions tbody tr:hover,table.chantiers tbody tr:hover,table.clients tbody tr:hover{background:var(--vert-doux)}}
table.chantiers td.c-client a::after,table.clients td.c-client a::after,table.soumissions a.lien-carte::after{content:"";position:absolute;inset:0;z-index:0}
table.soumissions a.tel,table.clients a.tel,table.chantiers a.tel{position:relative;z-index:1}table.soumissions td.col-actions{text-align:right;width:56px}table.soumissions .menu-rapide{z-index:2}table.soumissions .menu-rapide[open]{z-index:7}
table.soumissions,.liste-defile:has(table.soumissions){overflow:visible}.menu-rapide-liste{text-align:center}
.menu-rapide-liste .bouton,.menu-rapide-liste button{min-height:40px;padding:8px 12px;font-size:14px}
.sel-total[hidden]{display:none}
.choix-paye{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:12px}.mode-paye{display:none;margin-bottom:12px}.modale-carte:has(input[value=oui]:checked) .mode-paye{display:block}.duree-reelle{margin-bottom:14px}.lien-facture-modale{margin:12px 0 0;font-size:.9rem}.modale-carte h2+.doux{margin-top:-4px}.sel-total .charge{color:#b42318}
.sel-total{position:sticky;bottom:0;background:var(--carte);border:1px solid var(--accent);border-radius:10px;padding:10px 16px;margin-top:12px}
.cal-nav{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}.cal-nav h2{margin:0;flex:1;text-align:center;font-size:20px;min-width:140px}
.cal-grille{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}
.cal-tete{font-size:13px;color:var(--doux);text-align:center;font-weight:600;padding:4px 0;text-transform:capitalize}
.cal-jour{min-height:124px;padding:6px 8px;border:1px solid var(--trait);border-radius:8px;text-decoration:none;color:var(--texte);display:flex;flex-direction:column;gap:2px;background:var(--carte)}
.cal-jour:hover{border-color:var(--accent-fonce)}.cal-jour.autre-mois{opacity:.45}.cal-jour.weekend{background:var(--fond)}
.cal-jour .cal-n{font-weight:700}.cal-jour.aujourdhui .cal-n{background:var(--accent);color:#fff;border-radius:99px;padding:0 7px;align-self:flex-start}
.cal-jour.occupe{border-color:var(--accent);background:var(--ok-fond)}.cal-jour.chargee{border-color:var(--alerte);background:var(--alerte-fond)}
.cal-jour.selection{outline:3px solid var(--accent-fonce);outline-offset:-1px}.cal-info{font-size:12px;line-height:1.35}.cal-ligne{display:block}
form.encaisser{display:flex;flex-direction:column;align-items:flex-start;gap:6px;margin-top:8px}form.encaisser select{width:auto;max-width:130px}.cal-alerte{font-size:11px;color:var(--alerte);font-weight:700}
.col-ordre{white-space:nowrap}.col-ordre .fleches{display:flex;gap:4px;margin-bottom:4px}.col-ordre form{margin:0}button.fleche{padding:3px 9px;font-size:13px;line-height:1}
tr.sans-bas td{border-bottom:none}tr.ligne-actions td{text-align:right;padding-top:0}
button:disabled{opacity:.3;cursor:default}
.heures{font-size:16px;white-space:nowrap}tr.diner td{background:var(--fond);color:var(--doux);font-size:13px;text-align:center}
.modale{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:50;padding:16px}
.modale-carte{background:var(--carte);border-radius:14px;padding:24px;max-width:480px;width:100%;box-shadow:0 10px 40px rgba(0,0,0,.35)}
.modale .question{font-size:19px;font-weight:700;margin:12px 0 18px}
@media (max-width:700px){.cal-jour{min-height:96px;padding:4px}.cal-info{font-size:10px}}
.requis{color:var(--alerte);font-weight:700}
.verrou-termine{background:var(--ok-fond);border:1px solid var(--accent);border-radius:10px;padding:12px 16px;margin-bottom:16px}
dl.lecture{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:6px 14px;margin:0}dl.lecture dt{color:var(--doux);font-size:14px}dl.lecture dd{margin:0}
@media (max-width:600px){dl.lecture{grid-template-columns:1fr}}
.lecture-seule{background:var(--fond);border:1px dashed var(--doux);border-radius:10px;padding:12px 16px;margin-bottom:16px}
details summary{cursor:pointer;color:var(--accent-fonce);font-weight:600;margin-bottom:10px}
details.avance{background:var(--carte);border:1px solid var(--trait);border-radius:12px;padding:12px 16px;margin-bottom:16px}
details.avance>summary{margin-bottom:0}details.avance[open]>summary{margin-bottom:14px}
details.avance .carte{box-shadow:none;border:1px solid var(--trait)}
.col-travaux{min-width:200px}.nw{white-space:nowrap}
input[type=radio],input[type=checkbox]{width:auto;margin:0}
.modale p{margin:6px 0}.modale label.coche{font-size:17px}
label.coche,span.coche{display:inline-flex;align-items:center;gap:6px;color:var(--texte);font-size:16px;margin:0}.options-travaux .barre{gap:8px 22px}
.puce-opt{display:inline-block;background:var(--ok-fond);border:1px solid var(--trait);border-radius:999px;padding:1px 9px;font-size:13px;margin:2px 6px 0 0;white-space:nowrap}
.resume-chantier{display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap;align-items:flex-start}.resume-chantier>div:first-child{flex:1 1 320px}.resume-chantier .montant{margin-left:auto}
.montant{font-size:18px;font-weight:700;text-align:right;white-space:nowrap}.montant small{display:block;font-size:12px;font-weight:400;color:var(--doux)}
.total-jour .total,.resume-jour .total{font-weight:700}

/* Style de sylvainculteur.ca : vert forêt et vert signature, cartes blanches arrondies, titres lourds, étiquettes en capitales */
*{-webkit-font-smoothing:antialiased}
body{font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--fond);color:var(--texte)}
.navbar{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.96);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--trait-leger)}
.nav-contenu{max-width:1500px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:22px;flex-wrap:wrap}
.marque{display:inline-flex;align-items:center;text-decoration:none;color:var(--vert-fonce)}.marque img{height:40px;width:auto;display:block}
.logotype{font-size:1.3rem;font-weight:800;letter-spacing:-.02em;color:var(--vert-fonce)}.logotype span{color:var(--vert)}
.nav-bureau{display:flex;align-items:center;gap:6px;flex:1}.nav-bureau a{padding:8px 12px;border-radius:8px;text-decoration:none;color:var(--vert-fonce);font-weight:600;font-size:.92rem;transition:color .2s,background-color .2s}
.nav-bureau a.actif{background:var(--vert-doux);color:var(--vert)}
.nav-droite{display:flex;align-items:center;gap:12px;margin-left:auto;font-size:.88rem}.nav-droite a{color:var(--vert-fonce);font-weight:600;text-decoration:none}
.nav-droite .qui{color:var(--doux);font-weight:600}.nav-droite form{margin:0}
button.lien{background:none;border:0;box-shadow:none;color:var(--doux);padding:4px 6px;min-height:0;font-weight:600;font-size:.88rem;text-decoration:underline;cursor:pointer}
@media (hover:hover) and (pointer:fine){.nav-bureau a:hover{color:var(--vert)}.nav-droite a:hover{color:var(--vert)}}
.bandeau-page{background:var(--vert-doux);border-bottom:1px solid var(--vert-bord);padding:30px 0 24px}
.conteneur{max-width:1100px;margin:0 auto;padding:0 20px}.conteneur.large{max-width:1500px}main.conteneur{padding:24px 20px 44px}
.tag-badge{display:inline-flex;align-items:center;gap:8px;font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--vert);margin-bottom:6px}
.retour-haut{display:inline-flex;align-items:center;gap:4px;margin-bottom:6px;font-size:.9rem;font-weight:600;color:var(--vert);text-decoration:none}.retour-haut::before{content:"";width:8px;height:8px;border-left:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(45deg);margin-right:2px}.retour-haut:hover{text-decoration:underline}
.tag-badge::before{content:"";display:inline-block;width:24px;height:1.8px;background:var(--vert);border-radius:2px}
h1{font-size:clamp(1.6rem,4.5vw,2.3rem);font-weight:800;line-height:1.15;letter-spacing:-.02em;color:var(--vert-fonce);margin:0}
.bandeau-page h1 a{font-size:.9rem;font-weight:600;letter-spacing:0}
main{padding:22px 20px 40px}main>h1{margin:6px 0 18px}
h2{font-size:1.1rem;font-weight:800;letter-spacing:-.01em;color:var(--vert-fonce);margin:0 0 12px}
main a{color:var(--vert);font-weight:600}
.carte{border:1px solid var(--trait-leger);border-radius:18px;padding:22px;box-shadow:var(--ombre-sm)}
label{font-size:.88rem;font-weight:700;color:var(--texte);margin-bottom:6px}
input,select,textarea{border:1px solid var(--trait);border-radius:8px;padding:11px 14px;outline:none;transition:border-color .2s}
input:focus,select:focus,textarea:focus{border-color:var(--vert)}
button,.bouton{background:var(--vert);color:#fff;border-radius:10px;padding:12px 20px;font-weight:700;font-size:.95rem;box-shadow:var(--ombre-btn);transition:transform .2s,box-shadow .2s,background-color .2s}
@media (hover:hover) and (pointer:fine){button:hover,.bouton:hover{background:var(--vert-fonce);transform:translateY(-1px)}}
button.secondaire,.bouton.secondaire{background:#fff;color:var(--vert-fonce);border:1px solid var(--trait);box-shadow:var(--ombre-sm)}
@media (hover:hover) and (pointer:fine){button.secondaire:hover,.bouton.secondaire:hover{background:#fff;box-shadow:var(--ombre-md)}}
button.danger{background:#fff;color:var(--alerte);border:1px solid var(--alerte-bord);box-shadow:none}
@media (hover:hover) and (pointer:fine){button.danger:hover{background:var(--alerte-fond)}}
button.plein{width:100%;padding:15px 20px;font-size:1.02rem;border-radius:12px;margin-top:6px}
button.lien{background:none;box-shadow:none;color:var(--doux)}
@media (hover:hover) and (pointer:fine){button.lien:hover{background:none;transform:none;color:var(--vert)}}
button:disabled{box-shadow:none}
table{border:1px solid var(--trait-leger);border-radius:14px;box-shadow:var(--ombre-sm)}
th{font-size:.72rem;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:var(--doux);background:var(--fond)}
th,td{border-bottom:1px solid var(--trait-leger)}
td a{color:var(--vert-fonce)}
.badge{font-size:.7rem;font-weight:800;text-transform:uppercase;letter-spacing:.05em;padding:3px 10px;border-radius:12px;background:var(--fond);border:1px solid var(--trait-leger);color:var(--vert)}
.b-prix_manquant{background:#fff7e6;color:#92400e;border-color:#fcd9a0}.b-a_payer{background:var(--alerte-fond);color:var(--alerte);border-color:var(--alerte-bord)}
.b-partiel{background:#eff6ff;color:#1e40af;border-color:#bfdbfe}.b-paye,.b-termine{background:var(--vert-doux);color:var(--vert);border-color:var(--vert-bord)}
.b-soumission{background:#eff6ff;color:#1e40af;border-color:#bfdbfe}.b-a_planifier{background:#fff7e6;color:#92400e;border-color:#fcd9a0}
.b-en_attente{background:#f1f5f9;color:#475569;border-color:#cbd5e1}
.b-planifie{background:var(--vert-doux);color:var(--vert);border-color:var(--vert-bord)}.b-annule,.b-refusee{background:var(--alerte-fond);color:var(--alerte);border-color:var(--alerte-bord)}
.raccourcis-bloc{display:flex;gap:10px 14px;flex-wrap:wrap;align-items:center;margin-bottom:16px}.raccourcis{display:flex;gap:10px;flex-wrap:wrap;align-items:stretch}.raccourcis .puce{min-width:130px}
.puce.actif{border-color:var(--vert);background:var(--vert-doux)}.puce.actif b{color:var(--vert)}.raccourcis-bloc .modifier{font-size:.88rem}
.actions-bloc{margin-bottom:16px}.actions-page{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.actions-page form{margin:0}
.actions-page .bouton,.actions-page button{padding:11px 20px;font-size:.95rem;white-space:nowrap}.actions-bloc .manque{margin:8px 0 0;font-size:.9rem}
.actions-soumission .bouton,.actions-soumission button{padding:7px 14px;font-size:14px;line-height:1.3;white-space:nowrap}
.actions-ligne.actions-soumission{flex-wrap:wrap}.groupe-actions{display:inline-flex;gap:8px;align-items:center}
.lien-pdf-coin{display:none;position:absolute;top:10px;right:14px;font-size:.78rem;font-weight:600;color:var(--doux)!important;text-decoration:underline}.carte.documents h2{margin:0 0 8px}.ligne-document{display:inline-flex;align-items:center;gap:14px;flex-wrap:wrap;padding:6px 8px 6px 0}.ligne-document b{min-width:112px}.ligne-document .actions-page .bouton{padding:8px 16px;font-size:.9rem}
.tuiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}
.tuile{background:#fff;border:1px solid var(--trait-leger);border-radius:14px;box-shadow:var(--ombre-sm);padding:12px 16px}
.tuile b{display:block;font-size:1.35rem;font-weight:800;color:var(--vert-fonce);line-height:1.2}.tuile span{color:var(--doux);font-size:.78rem;font-weight:700}
.grille-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(400px,100%),1fr));gap:16px}.grille-stats .carte{margin-bottom:0}
table.stat{box-shadow:none;border:0}table.stat th,table.stat td{padding:7px 8px;font-size:14px;white-space:normal}table.stat td:first-child{white-space:normal}
.cellule-barre{width:24%}.stat-barre{display:block;height:8px;border-radius:4px;background:var(--vert)}.stat-defile{overflow-x:auto}
table.tableau.archive td:first-child{white-space:nowrap}
table.liste td .depuis{margin-top:3px;white-space:nowrap}table.liste td .depuis .doux{font-size:12px;margin-left:2px}
form.filtres{margin-bottom:12px}form.filtres .recherche{margin-bottom:12px}
.manque{font-size:.82rem;color:var(--alerte);margin-top:4px}.attente{border-radius:8px}.a-normale{background:var(--vert-doux);color:var(--vert);border-color:var(--vert-bord)}
.a-surveiller{background:#fff7e6;color:#92400e;border-color:#fcd9a0}.a-urgente{background:var(--alerte-fond);color:var(--alerte);border-color:var(--alerte-bord)}
.erreurs{background:var(--alerte-fond);border:1px solid var(--alerte-bord);border-radius:12px}.message,.verrou-termine{background:var(--vert-doux);border:1px solid var(--vert-bord);border-radius:12px}
.verrou,.lecture-seule{background:var(--fond);border:1px dashed var(--trait);border-radius:12px}
.puce{border:1px solid var(--trait-leger);border-radius:14px;box-shadow:var(--ombre-sm);padding:12px 16px}.puce b{font-size:1.4rem;font-weight:800;color:var(--vert-fonce)}
.onglet{border-color:var(--trait);font-weight:600}.onglet.actif{background:var(--vert);border-color:var(--vert)}
.puce-opt{background:var(--vert-doux);border-color:var(--vert-bord);color:var(--vert-fonce);font-weight:600}
.cal-jour{border-radius:12px;border-color:var(--trait-leger)}.cal-jour.occupe{border-color:var(--vert);background:var(--vert-doux)}.cal-jour.chargee{border-color:var(--alerte);background:var(--alerte-fond)}
.cal-jour.selection{outline:3px solid var(--vert);outline-offset:-1px}.cal-jour.aujourdhui .cal-n{background:var(--vert)}
.modale{background:rgba(14,52,29,.65);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.modale-carte{border-radius:20px;padding:30px;box-shadow:0 20px 45px rgba(0,0,0,.25)}
details.avance{border:1px solid var(--trait-leger);border-radius:18px;box-shadow:var(--ombre-sm)}details summary{color:var(--vert);font-weight:700}
.montant{color:var(--vert-fonce);font-weight:800}
.base.essai{background:#fff7e6;color:#92400e;border:1px solid #fcd9a0;border-radius:12px;padding:2px 10px;font-weight:700;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em}
.connexion{max-width:420px;margin:48px auto;padding:0 16px}.connexion .carte{padding:30px 26px;text-align:left}
.connexion .logotype{display:block;font-size:1.6rem;margin-bottom:16px}.connexion img{height:54px;margin-bottom:12px}.connexion h1{font-size:1.7rem;margin:0 0 16px}
.champ{margin-bottom:16px}
.pied{background:var(--vert-fonce);color:var(--fond);font-size:.8rem;text-align:center;padding:18px 20px}.pied b{font-weight:700}
.barre-mobile,.menu-tel,.tel-seul,.filtres-det>summary,.modifier-puce,.filtres-bascule,.resume-min,.info-pop,.lien-dl,.texto-jour,.note-heures,.resume-jour,.total-jour{display:none}
.carte.contact{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px 24px}
.contact-infos p{margin:0 0 2px}.contact-adresse{font-weight:600}.contact-liens{font-size:.85rem;margin-top:6px!important}.contact-liens a{color:var(--doux)}
.contact-actions{display:flex;gap:18px;align-items:center}.nouvelle-pc{margin-right:10px}.contact-note{flex-basis:100%;margin:0;font-size:.85rem}
a.rond{display:flex;flex-direction:column;align-items:center;gap:4px;font-size:12px;font-weight:600;color:var(--texte);text-decoration:none}
.rond-icone{display:flex;align-items:center;justify-content:center;width:46px;height:46px;border-radius:50%;background:#fff;border:1px solid var(--trait)}
a.rond:hover .rond-icone{background:var(--vert-doux);border-color:var(--vert-bord)}
.rond-icone svg{width:22px;height:22px;fill:none;stroke:var(--vert-fonce);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
details.modifier-fiche>summary{font-weight:700}
/* Animations : elles répondent à un geste et montrent ce qui a changé ; courtes (0,1 à 0,3 s). Voir le skill design-sylvainculteur. */
@keyframes apparait{from{opacity:0;transform:translateY(-6px) scale(.97)}to{opacity:1;transform:none}}
@keyframes fondu{from{opacity:0}to{opacity:1}}
@keyframes monte{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}
@keyframes descend{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
.menu-rapide[open]>.menu-rapide-liste{animation:apparait .18s ease-out;transform-origin:top right}
.modale{animation:fondu .2s ease-out}.modale-carte{animation:monte .25s cubic-bezier(.2,.8,.2,1)}
details.avance[open]>:not(summary),details.filtres-det[open]>:not(summary){animation:descend .2s ease-out}
.message,.erreurs{animation:descend .25s ease-out}
button:active,.bouton:active{transform:scale(.97);transition-duration:.1s}
.rond-icone{transition:transform .1s,background-color .15s,border-color .15s}a.rond:active .rond-icone{transform:scale(.92)}
.menu-rapide>summary{transition:background-color .15s}
table.soumissions tbody tr,table.chantiers tbody tr,table.clients tbody tr{transition:background-color .12s}
a.lien-discret{font-weight:inherit;color:inherit;text-decoration:none}a.lien-discret:hover{text-decoration:underline}
.poignee{display:none}.glisser-pret .fleches{display:none!important}
.glisser-pret .poignee{display:inline-block;width:22px;height:22px;vertical-align:middle;opacity:.55;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%230e341d'%3E%3Ccircle cx='9' cy='6' r='1.7'/%3E%3Ccircle cx='15' cy='6' r='1.7'/%3E%3Ccircle cx='9' cy='12' r='1.7'/%3E%3Ccircle cx='15' cy='12' r='1.7'/%3E%3Ccircle cx='9' cy='18' r='1.7'/%3E%3Ccircle cx='15' cy='18' r='1.7'/%3E%3C/svg%3E") center/20px no-repeat}
body.glisse,body.glisse *{overflow-anchor:none}.glisser-pret>[data-id]{cursor:grab;position:relative}.glisser-pret>[data-id].leve{z-index:30;cursor:grabbing;outline:2px solid var(--vert);outline-offset:-1px;box-shadow:0 16px 36px rgba(14,52,29,.28)}
@media (min-width:701px){.glisser-pret>tr.leve>td{background:#fff}}body.glisse{cursor:grabbing;user-select:none;-webkit-user-select:none}
table.historique tbody tr{position:relative}table.historique td.c-date a::after{content:"";position:absolute;inset:0}
tr.touche{outline:2px solid var(--vert);outline-offset:-2px}@media (hover:hover){table.historique tbody tr:hover{background:var(--vert-doux)}}
@view-transition{navigation:auto}::view-transition-old(root),::view-transition-new(root){animation-duration:.16s}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}@view-transition{navigation:none}}
.no-fiche{font-weight:700;color:var(--doux);font-size:.9rem}

.carte-jour{position:relative}.carte-jour h2{padding-right:48px}
.info-btn{--loupe:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%230e341d' stroke-width='2.2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='6.5'/%3E%3Cpath d='M16 16l4.5 4.5'/%3E%3C/svg%3E");position:absolute;top:12px;right:14px;width:36px;height:36px;min-height:0;padding:0;border:1px solid var(--trait);border-radius:50%;box-shadow:none;cursor:pointer}
.info-btn,.info-btn:hover,.info-btn:focus{background:#fff var(--loupe) center/18px no-repeat}.info-btn:hover{background-color:var(--vert-doux);border-color:var(--vert-bord)}
.info-btn.info-alerte::after{content:"";position:absolute;top:-2px;right:-2px;width:10px;height:10px;border-radius:50%;background:var(--alerte);border:2px solid #fff}
.info-pop{position:absolute;z-index:20;top:48px;right:14px;width:min(380px,calc(100% - 28px));padding:14px 16px;border:1px solid var(--trait-leger);border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(15,23,42,.18);font-size:14px;line-height:1.7}
.carte-jour.info-ouverte .info-pop{display:block}
@media (hover:hover){.info-btn:hover+.info-pop,.info-pop:hover{display:block}}
.carte-jour.info-ferme .info-pop{display:none!important}
main a.tel{color:inherit;font-weight:inherit;text-decoration:none}
.photos-grille{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-bottom:12px}
.photos .photo{display:block;padding:0;font-weight:400}.photos .photo img{display:block;width:100%;aspect-ratio:1/1;object-fit:cover;border:1px solid var(--trait-leger);border-radius:10px;background:var(--puce)}
.photos label.bouton{cursor:pointer}.photo-prendre{display:none!important}.photo-etat{margin:8px 0 0}.photo-etat:empty{display:none}
.visionneuse{position:fixed;inset:0;z-index:2000;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:16px;background:rgba(14,52,29,.94)}
.visionneuse[hidden]{display:none}.visionneuse img{max-width:100%;max-height:78vh;object-fit:contain;border-radius:8px}
.visionneuse .barre{margin:0;justify-content:center}.visionneuse form{margin:0}
"""


_BASE = {"db": None}   # base ouverte par ce serveur (affichée dans l'en-tête pour ne jamais s'y tromper)


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def argent_entier(x):
    """Montant arrondi au dollar (« 2 564 $ ») : pour les petits espaces, comme les cases du calendrier."""
    return f"{round(x):,} $".replace(",", " ")


def argent(x):
    return "" if x is None else f"{x:,.2f} $".replace(",", " ").replace(".", ",")


def etiquette_base():
    if not _BASE["db"]:
        return ""
    nom = Path(_BASE["db"]).name
    if nom == DB_DEFAUT.name:
        return f'<span class="base">Base : {esc(nom)}</span>'
    return f'<span class="base essai" title="{esc(_BASE["db"])}">BASE D’ESSAI : {esc(nom)}</span>'


# Qui fait la requête (rempli par interface.repondre pour chaque requête ; vide dans les tests qui appellent les pages directement)
CONTEXTE = threading.local()
STATIC = Path(__file__).resolve().parent / "static"       # logo.svg ou logo.png facultatif : voir docs/acces_a_distance.md

SECTIONS = [(r"^/$", "tableau"), (r"^/(?:journee|tournee)", "journee"), (r"^/(?:client|secteurs)", "clients"),
            (r"^/(?:soumission|nouveau)", "soumissions"), (r"^/chantier", "chantiers"), (r"^/archives", "archives"), (r"^/utilisateurs", "admin")]
NOMS_SECTIONS = {"tableau": "Tableau de bord", "journee": "Journée", "chantiers": "Chantiers", "soumissions": "Soumissions",
                 "clients": "Clients", "archives": "Archives", "admin": "Administration"}


def utilisateur_courant():
    return getattr(CONTEXTE, "utilisateur", None)


def est_admin():
    """Vrai pour l'administrateur, et aussi quand il n'y a pas de comptes (accès local ouvert, tests)."""
    u = utilisateur_courant()
    return u is None or u.get("role") == "admin"


def section_de(chemin):
    for motif, nom in SECTIONS:
        if re.match(motif, chemin or ""):
            return nom
    return ""


def logo_html():
    for ext in ("svg", "png"):
        if (STATIC / f"logo.{ext}").exists():
            return f'<img src="/logo.{ext}" alt="Sylvainculteur">'
    return '<span class="logotype">Sylvain<span>culteur</span></span>'


def _navigation(section):
    admin = est_admin()
    liens = ([("/", "Tableau de bord"), ("/journee", "Journée")] if admin else []) + [("/chantiers", "Chantiers"), ("/soumissions", "Soumissions"),
                                                                                       ("/clients", "Clients")] + ([("/archives", "Archives")] if admin else [])
    nav = "".join(f'<a href="{h}">{t}</a>' for h, t in liens)
    actif = {"tableau": "/", "journee": "/journee", "chantiers": "/chantiers", "soumissions": "/soumissions", "clients": "/clients",
             "archives": "/archives"}.get(section, "")
    surlignage = f'<style>.nav-bureau a[href="{actif}"]{{background:var(--vert-doux);color:var(--vert)}}</style>' if actif else ""
    u = utilisateur_courant()
    droite = etiquette_base()
    if u:
        droite += (f'<span class="qui">{esc(u["nom"])}</span>'
                   + ('<a class="admin-seul" href="/utilisateurs">Utilisateurs</a>' if u["role"] == "admin" else "")
                   + '<form method="post" action="/deconnexion"><button class="lien" type="submit">Se déconnecter</button></form>')
    return (f'<header class="navbar"><div class="nav-contenu"><a class="marque" href="{"/" if admin else "/soumissions"}">{logo_html()}</a>'
            f'<nav class="nav-bureau">{nav}</nav><div class="nav-droite">{droite}</div></div></header>{surlignage}')


_ICONES = {
    "tableau": '<rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "clients": '<circle cx="9" cy="8.5" r="3.2"/><path d="M3 19c.6-3.3 3-5 6-5s5.4 1.7 6 5"/><circle cx="17" cy="9.5" r="2.4"/><path d="M17.5 14.2c2 .3 3.2 1.8 3.5 4.3"/>',
    "soumissions": '<path d="M7 3.5h7l4 4V20a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20V5a1.5 1.5 0 0 1 1-1.5z"/><path d="M14 3.5V8h4M9 13h6M9 16.5h4"/>',
    "chantiers": '<path d="M12 3l5 7h-3l4 6h-5v5h-2v-5H6l4-6H7z"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
}


def _icone(nom):
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{_ICONES[nom]}</svg>'


def _barre_mobile(section):
    """Téléphone : en bas, des onglets (icône + nom) : Accueil (le tableau de bord), Soumissions, Chantiers et Clients (administrateur) ;
    Soumissions, Chantiers et Clients (compte « soumission ») ; puis l'icône du menu : le reste (Journée, Archives, Utilisateurs,
    déconnexion) est dans la feuille « Menu »."""
    admin = est_admin()

    def lien(href, texte, actif, icone):
        return f'<a href="{href}" class="{"actif" if actif else ""}">{_icone(icone)}<span>{texte}</span></a>'
    if admin:
        principaux = [("/", "Accueil", "tableau"), ("/soumissions", "Soumissions", "soumissions"), ("/chantiers", "Chantiers", "chantiers"),
                      ("/clients", "Clients", "clients")]
        reste = [("/journee", "Journée", "journee"), ("/archives", "Archives", "archives")]
    else:
        principaux = [("/soumissions", "Soumissions", "soumissions"), ("/chantiers", "Chantiers", "chantiers"), ("/clients", "Clients", "clients")]
        reste = []
    u = utilisateur_courant()
    if u and u["role"] == "admin":
        reste.append(("/utilisateurs", "Utilisateurs", "utilisateurs"))
    sortie = '<form method="post" action="/deconnexion"><button type="submit">Se déconnecter</button></form>' if u else ""
    qui = f'<div class="menu-qui">{esc(u["nom"])}</div>' if u else ""
    menu_actif = any(section == code for _, _, code in reste)
    bas = "".join(lien(h, t, section == c, c) for h, t, c in principaux)
    bas += (f'<button type="button" class="menu-bouton{" actif" if menu_actif else ""}" onclick="document.body.classList.toggle(\'menu-ouvert\')" '
            f'aria-label="Menu" title="Menu">{_icone("menu")}</button>')
    feuille = "".join(f'<a href="{h}" class="{"actif" if section == c else ""}">{t}</a>' for h, t, c in reste)
    return (f'<nav class="barre-mobile">{bas}</nav><div class="menu-tel"><div class="menu-fond" onclick="document.body.classList.remove(\'menu-ouvert\')"></div>'
            f'<div class="menu-feuille">{qui}{feuille}{sortie}</div></div>')


# La feuille de style (ordinateur + téléphone) n'est plus recopiée dans chaque page : elle est servie à part, à une adresse qui
# porte son empreinte (/style-<empreinte>.css). Le navigateur la garde en mémoire (un an) et ne la redemande plus ; dès que le
# style change, l'empreinte change, donc l'adresse aussi, et la nouvelle feuille est prise tout de suite. Rien à vider à la main.
FEUILLE_DE_STYLE = (CSS + CSS_TELEPHONE).encode("utf-8")
VERSION_STYLE = hashlib.sha256(FEUILLE_DE_STYLE).hexdigest()[:12]
URL_STYLE = f"/style-{VERSION_STYLE}.css"


def feuille_de_style():
    """Réponse de /style-<empreinte>.css : la feuille actuelle, à garder en mémoire (l'adresse change quand le style change)."""
    return ("200 OK", [("Content-Type", "text/css; charset=utf-8"), ("Cache-Control", "private, max-age=31536000, immutable")],
            FEUILLE_DE_STYLE)


LIBELLES_RETOUR = {"/": "Accueil", "/chantiers": "Chantiers", "/soumissions": "Soumissions", "/clients": "Clients", "/journee": "Journée",
                   "/archives": "Archives", "/utilisateurs": "Utilisateurs"}


def libelle_retour(chemin):
    """« ‹ Chantiers » : le nom de la page où l'on revient (la même règle est reprise par SCRIPT_RETOUR, dans le navigateur)."""
    chemin = (chemin or "").split("?")[0]
    if chemin in LIBELLES_RETOUR:
        return LIBELLES_RETOUR[chemin]
    m = re.match(r"^/(client|chantier|soumission)/\d+$", chemin)
    return {"client": "Client", "chantier": "Chantier", "soumission": "Soumission"}[m.group(1)] if m else "Retour"


def gabarit(titre, contenu, message=None, erreur=None, large=False, public=False, section=None, retour=None):
    """`retour` : sur une page de détail (fiche), le lien « ‹ Chantiers » en haut, à la place du petit surtitre. Son adresse est
    celle d'où l'on vient vraiment (pile des pages, SCRIPT_RETOUR) ; `retour` ne sert que si on arrive directement sur la fiche."""
    msg = f'<div class="message">{esc(MESSAGES[message])}</div>' if message in MESSAGES else ""
    if erreur:
        msg += f'<div class="erreurs"><strong>Action refusée :</strong> {esc(erreur)}</div>'
    section = section or section_de(getattr(CONTEXTE, "chemin", ""))
    tete = f'<link rel="stylesheet" href="{URL_STYLE}"></head><body>'
    entete = ('<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">'
              f'<meta name="theme-color" content="#0e341d"><title>{esc(titre)} — SylvainCulteur</title>')
    if public:           # page de connexion et refus : pas de menu
        return f'<!doctype html><html lang="fr-CA"><head>{entete}{tete}<main class="connexion-page">{msg}{contenu}</main></body></html>'
    classe_large = " large" if large else ""
    bandeau = ""
    m = re.match(r"\s*(<h1[^>]*>.*?</h1>)", contenu, re.S)
    if m:              # le titre de la page va dans un bandeau vert pâle, comme le haut du site
        surtitre = NOMS_SECTIONS.get(section, "Sylvainculteur")
        titre_h1 = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if retour:
            haut = f'<a class="fermer retour-haut" href="{esc(retour)}"><span>{esc(libelle_retour(retour))}</span></a>'
        elif titre_h1.lower().startswith(surtitre.lower()):
            haut = ""                    # le surtitre répéterait le titre (« TABLEAU DE BORD » au-dessus de « Tableau de bord »)
        else:
            haut = f'<span class="tag-badge">{esc(surtitre)}</span>'
        bandeau = f'<section class="bandeau-page"><div class="conteneur{classe_large}">{haut}{m.group(1)}</div></section>'
        contenu = contenu[m.end():]
    return (f'<!doctype html><html lang="fr-CA"><head>{entete}{tete}{_navigation(section)}{bandeau}'
            f'<main class="conteneur{classe_large}">{msg}{contenu}</main>'
            '<footer class="pied"><b>Sylvainculteur</b> · Depuis 2008 · Gestion interne</footer>'
            f'{_barre_mobile(section)}{SCRIPT_POSITION}{SCRIPT_RETOUR}{SCRIPT_MENU}{SCRIPT_GLISSER}{SCRIPT_TOUCHE}{SCRIPT_PARTAGE}</body></html>')


# Changer de jour, de mois ou de filtre sur la même page : on reste à la même hauteur au lieu de remonter en haut.
SCRIPT_POSITION = (
    '<script>(function(){var k="pos:"+location.pathname;try{var v=sessionStorage.getItem(k);'
    'if(v!==null){sessionStorage.removeItem(k);window.scrollTo(0,parseInt(v,10)||0);}}catch(e){}'
    'function g(){try{sessionStorage.setItem(k,String(window.pageYOffset));}catch(e){}}'
    'document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a[href]");'
    'if(a&&!a.target&&a.pathname===location.pathname&&a.origin===location.origin&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey)g();});'
    'document.addEventListener("submit",function(e){var f=e.target;if(f.method&&f.method.toLowerCase()==="get"&&'
    'new URL(f.action||location.href,location.href).pathname===location.pathname)g();});})();</script>')

# « Annuler » et « Fermer » ramènent à la page d'où l'on vient (pas à une page fixe) : le navigateur garde la pile des pages visitées pendant la session.
# Un formulaire (liens a.annuler) ne se met pas dans la pile ; une page normale s'y met (revenir en arrière la dépile) ; « Fermer » (a.fermer) va à la page d'avant.
# Glisser-déposer pour réordonner (Journée, Raccourcis) : on maintient le doigt sur une tuile (0,35 s), elle se soulève, on la
# déplace, on relâche ; avec une souris : on clique et on tire. Les voisines s'écartent en douceur. Au relâchement, l'ordre complet
# est envoyé (formulaire caché `data-glisser="<id du formulaire>"` sur le conteneur ; chaque tuile porte `data-id`).
# Sans JavaScript, les flèches ▲ ▼ restent : la classe « glisser-pret », posée ici, les remplace par une poignée.
SCRIPT_GLISSER = r"""<script>(function(){
Array.prototype.forEach.call(document.querySelectorAll('[data-glisser]'),function(c){
var form=document.getElementById(c.getAttribute('data-glisser'));if(!form)return;
c.classList.add('glisser-pret');
var el=null,actif=false,minuteur=null,depart='',startY=0,x0=0,y0=0,dernier=0,tactile=0,vient=false,boucle=0;
function items(){return Array.prototype.filter.call(c.children,function(x){return x.hasAttribute('data-id');});}
function ordre(){return items().map(function(x){return x.getAttribute('data-id');}).join(',');}
function fige(t){return t.closest&&t.closest('button,input,select,textarea,summary,label,.menu-rapide');}
function milieu(x){return x.offsetTop+x.offsetHeight/2;}
function lever(){if(!el)return;actif=true;el.classList.add('leve');document.body.classList.add('glisse');
if(navigator.vibrate){try{navigator.vibrate(8);}catch(e){}}boucle=requestAnimationFrame(defile);}
function voisin(v,avant){var a=el.offsetTop,b=v.offsetTop;
if(avant){c.insertBefore(el,v);}else{c.insertBefore(el,v.nextSibling);}
startY+=el.offsetTop-a;
v.style.transition='none';v.style.transform='translateY('+(b-v.offsetTop)+'px)';v.offsetHeight;
v.style.transition='transform .16s ease-out';v.style.transform='';}
function placer(clientY){dernier=clientY;var y=clientY+window.pageYOffset,li,i,m;
for(;;){li=items();i=li.indexOf(el);
var d=y-startY,haut=li[0].offsetTop-el.offsetTop,bas=li[li.length-1].offsetTop+li[li.length-1].offsetHeight-el.offsetTop-el.offsetHeight;
d=Math.max(haut,Math.min(bas,d));el.style.transform='translateY('+d+'px)';m=el.offsetTop+d;
if(i>0&&m<milieu(li[i-1])){voisin(li[i-1],true);}
else if(i<li.length-1&&m+el.offsetHeight>milieu(li[i+1])){voisin(li[i+1],false);}
else break;}}
function defile(){if(!actif)return;var h=window.innerHeight,v=0;
if(dernier<90)v=-Math.ceil((90-dernier)/6);else if(dernier>h-150)v=Math.ceil((dernier-(h-150))/6);
if(v){window.scrollBy(0,v);placer(dernier);}boucle=requestAnimationFrame(defile);}
function fin(annule){clearTimeout(minuteur);if(!el)return;var e=el,a=actif;el=null;actif=false;cancelAnimationFrame(boucle);
if(!a)return;vient=true;setTimeout(function(){vient=false;},400);
e.style.transition='transform .16s ease-out';e.style.transform='';document.body.classList.remove('glisse');
setTimeout(function(){e.classList.remove('leve');e.style.transition='';},170);
var o=ordre();if(o===depart)return;
if(annule){location.reload();return;}
form.elements.ordre.value=o;setTimeout(function(){form.submit();},170);}
c.addEventListener('touchstart',function(e){if(el||e.touches.length!==1||fige(e.target))return;
var x=e.target.closest('[data-id]');if(!x||x.parentNode!==c)return;tactile=Date.now();
var t=e.touches[0];el=x;x0=t.clientX;y0=t.clientY;dernier=t.clientY;startY=t.clientY+window.pageYOffset;depart=ordre();
minuteur=setTimeout(lever,350);},{passive:true});
c.addEventListener('touchmove',function(e){if(!el)return;var t=e.touches[0];
if(!actif){if(Math.abs(t.clientX-x0)>10||Math.abs(t.clientY-y0)>10){clearTimeout(minuteur);el=null;}return;}
e.preventDefault();placer(t.clientY);},{passive:false});
c.addEventListener('touchend',function(){tactile=Date.now();fin(false);});
c.addEventListener('touchcancel',function(){fin(true);});
c.addEventListener('contextmenu',function(e){if(el)e.preventDefault();});
c.addEventListener('dragstart',function(e){e.preventDefault();});
c.addEventListener('mousedown',function(e){if(el||e.button!==0||Date.now()-tactile<800||fige(e.target))return;
var x=e.target.closest('[data-id]');if(!x||x.parentNode!==c)return;
el=x;x0=e.clientX;y0=e.clientY;dernier=e.clientY;startY=e.clientY+window.pageYOffset;depart=ordre();});
document.addEventListener('mousemove',function(e){if(!el||Date.now()-tactile<800)return;
if(!actif){if(Math.abs(e.clientY-y0)<6&&Math.abs(e.clientX-x0)<6)return;lever();}
e.preventDefault();if(window.getSelection)window.getSelection().removeAllRanges();placer(e.clientY);});
document.addEventListener('mouseup',function(){if(el&&Date.now()-tactile>=800)fin(false);});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&el)fin(true);});
c.addEventListener('click',function(e){if(vient){e.preventDefault();e.stopPropagation();vient=false;}},true);
});})();</script>"""

# Partager un PDF (soumission, facture) avec la feuille de partage de l'iPhone : Messages, Courriel, AirDrop, Fichiers...
# Le navigateur ne l'offre qu'en HTTPS (voir docs/acces_a_distance.md, « Accès en HTTPS ») : là, la petite icône « Télécharger »
# du téléphone devient « Partager ». En http, rien ne change : elle télécharge, comme avant.
# Le PDF est demandé dès que le doigt se pose, pour que la feuille s'ouvre au toucher même (l'iPhone exige un geste « frais ») ;
# s'il n'est pas prêt à temps, l'icône s'entoure de vert : un deuxième toucher partage aussitôt.
SCRIPT_PARTAGE = r"""<script>(function(){
if(!navigator.share||!navigator.canShare||!window.isSecureContext)return;
try{if(!navigator.canShare({files:[new File([''],'a.pdf',{type:'application/pdf'})]}))return;}catch(e){return;}
Array.prototype.forEach.call(document.querySelectorAll('a.lien-dl'),function(a){
var fichier=null,enCours=null;
a.classList.add('partage');a.removeAttribute('download');a.title='Partager le PDF';
a.setAttribute('aria-label',(a.getAttribute('aria-label')||'').replace('Télécharger','Partager'));
function charger(){if(!enCours){enCours=fetch(a.href,{credentials:'same-origin'}).then(function(r){
if(!r.ok||(r.headers.get('Content-Type')||'').indexOf('pdf')<0)throw new Error('pdf');
var n=((r.headers.get('Content-Disposition')||'').split('filename=')[1]||'document.pdf').replace(/[";]/g,'').trim();
return r.blob().then(function(b){fichier=new File([b],n,{type:'application/pdf'});});
}).catch(function(e){enCours=null;throw e;});}return enCours;}
a.addEventListener('touchstart',function(){charger().catch(function(){});},{passive:true});
a.addEventListener('click',function(e){e.preventDefault();a.classList.remove('pret');
if(fichier){navigator.share({files:[fichier]}).catch(function(){});return;}
a.classList.add('attente');
charger().then(function(){a.classList.remove('attente');return navigator.share({files:[fichier]});})
.catch(function(err){a.classList.remove('attente');
if(err&&err.name==='AbortError')return;
if(fichier){a.classList.add('pret');return;}
location.href=a.href;});});});})();</script>"""

# Un seul menu « ··· » ouvert à la fois ; un toucher ailleurs le ferme.
SCRIPT_MENU = ('<script>document.addEventListener("click",function(e){document.querySelectorAll("details.menu-rapide[open]").forEach('
               'function(d){if(!d.contains(e.target))d.removeAttribute("open");});});</script>')

# Une tuile de liste qu'on touche (n'importe où) garde un contour vert jusqu'à ce que la page suivante s'affiche : on voit que
# le toucher a été pris. `touchstart` vide : sans lui, l'iPhone n'applique pas l'état « :active » aux tuiles.
SCRIPT_TOUCHE = ('<script>document.addEventListener("touchstart",function(){},{passive:true});'
                 'document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a");if(!a||a.target)return;'
                 'var t=a.closest("table.chantiers tbody tr,table.soumissions tbody tr,table.clients tbody tr,table.historique tbody tr");'
                 'if(t&&!e.defaultPrevented)t.classList.add("touche");});'
                 'window.addEventListener("pageshow",function(){Array.prototype.forEach.call(document.querySelectorAll("tr.touche"),'
                 'function(t){t.classList.remove("touche");});});</script>')

SCRIPT_RETOUR = (
    '<script>(function(){try{var s=JSON.parse(sessionStorage.getItem("pile")||"[]"),q=document.querySelectorAll("a.annuler"),'
    'f=document.querySelectorAll("a.fermer"),l=new URL(location.href),i,p,t;["ok","err","terminer"].forEach(function(k){l.searchParams.delete(k);});'
    'var u=l.pathname+l.search;if(q.length){t=s[s.length-1];if(t){for(i=0;i<q.length;i++){q[i].href=t;}}}'
    'else{i=s.lastIndexOf(u);if(i>=0){s.length=i+1;}else{s.push(u);}if(s.length>30){s.shift();}'
    'sessionStorage.setItem("pile",JSON.stringify(s));p=s[s.length-2];if(p){for(i=0;i<f.length;i++){f[i].href=p;}'
    'var r=document.querySelector("a.retour-haut span"),c=p.split("?")[0],n=' + json.dumps(LIBELLES_RETOUR) + '[c],'
    'k=c.split("/");if(r){r.textContent=n||(k.length===3&&/^\\d+/.test(k[2])&&{client:"Client",chantier:"Chantier",soumission:"Soumission"}[k[1]])||"Retour";}}}'
    '}catch(e){}})();</script>')


def heures(h):
    """2.5 -> « 2 h 30 » ; 3.0 -> « 3 h » ; None -> « — »."""
    if h is None:
        return "—"
    minutes = round(h * 60)
    return f"{minutes // 60} h" + (f" {minutes % 60:02d}" if minutes % 60 else "")


JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS_COURTS = ["janv.", "févr.", "mars", "avril", "mai", "juin", "juill.", "août", "sept.", "oct.", "nov.", "déc."]


def date_lisible(iso, aujourdhui=None):
    """« 2026-12-04 » -> « ven. 4 déc. » (cette année) ; « 2025-04-12 » -> « 12 avril 2025 » (une autre année).
    Vide ou illisible : rendu tel quel. La base, les formulaires et les adresses gardent le format AAAA-MM-JJ."""
    try:
        d = datetime.date.fromisoformat((iso or "")[:10])
    except ValueError:
        return iso or ""
    jour = f"{d.day}{'er' if d.day == 1 else ''} {MOIS_COURTS[d.month - 1]}"
    if d.year != (aujourdhui or datetime.date.today()).year:
        return f"{jour} {d.year}"
    return f"{JOURS_COURTS[d.weekday()]} {jour}"


def le_date(iso, aujourdhui=None):
    """Dans une phrase : « aujourd'hui », « demain », « hier », sinon « le ven. 4 déc. » (« prévu demain », « prévu le ven. 4 déc. »)."""
    aujourdhui = aujourdhui or datetime.date.today()
    try:
        ecart = (datetime.date.fromisoformat((iso or "")[:10]) - aujourdhui).days
    except ValueError:
        return iso or ""
    if ecart in (-1, 0, 1):
        return ("hier", "aujourd'hui", "demain")[ecart + 1]
    return "le " + date_lisible(iso, aujourdhui)


def menu_points(contenu, classe=""):
    """Le petit bouton « ··· » qui ouvre un menu (téléphone seulement : sur PC, il est caché). Un seul ouvert à la fois."""
    return (f'<details class="menu-rapide{" " + classe if classe else ""}"><summary aria-label="Plus d\'actions" title="Plus d\'actions"></summary>'
            f'<div class="menu-rapide-liste">{contenu}</div></details>')


def rangee_actions(principal, secondaires, classe=""):
    """Les actions d'une fiche. PC : tous les boutons à la suite. Téléphone : l'action principale (verte) bien visible,
    les autres derrière « ··· ». Sans action principale, rien n'est caché : un « ··· » tout seul ne dit pas quoi faire."""
    secondaires = [b for b in secondaires if b]
    if not principal or not secondaires:
        return f'<div class="actions-page{" " + classe if classe else ""}">{principal}{"".join(secondaires)}</div>'
    tous = "".join(secondaires)
    return (f'<div class="actions-page avec-menu{" " + classe if classe else ""}">{principal}<span class="actions-sec">{tous}</span>'
            f'{menu_points(tous, "menu-fiche")}</div>')


def case_taxes(nom, cochee):
    """« Ajouter TPS et TVQ » : sur sa propre ligne de la grille (le libellé est trop long pour une colonne)."""
    return (f'<div class="large"><label class="coche"><input type="checkbox" name="{nom}" value="1"{" checked" if cochee else ""}>'
            'Ajouter TPS 5 % et TVQ 9,975 %</label></div>')


def lien_tel(t):
    """Numéro cliquable des LISTES (Soumissions, Clients, Archives) : un toucher lance l'appel."""
    if not t:
        return ""
    texte = f"{t[2:5]}-{t[5:8]}-{t[8:]}" if len(t) == 12 else t
    chiffres = "+" * t.startswith("+") + "".join(c for c in t if c.isdigit())
    return f'<a class="tel" href="tel:{esc(chiffres)}">{esc(texte)}</a>'


def tel_texte(t):
    """Numéro à LIRE : « 819-555-0106 », en texte (pas de lien). Pour appeler : le bouton rond Appeler de la fiche,
    ou « Appeler » dans le menu « ··· » d'une carte (docs/style_interface.md : on agit par les boutons)."""
    if not t:
        return ""
    return esc(f"{t[2:5]}-{t[5:8]}-{t[8:]}" if len(t) == 12 else t)


def lien_maps(adresse_maps, texte):
    """Lien vers Google Maps (ouvre l'itinéraire / la carte de l'adresse). Sans adresse (soumission), le texte seul."""
    if not adresse_maps:
        return esc(texte) if texte else '<span class="doux">adresse à saisir</span>'
    url = "https://www.google.com/maps/search/?api=1&query=" + quote(adresse_maps)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener" title="Ouvrir dans Google Maps">{esc(texte)}</a>'


def badge_attente(jours, priorite):
    libelle = {"normale": "normal", "surveiller": "à surveiller", "urgente": "URGENT"}[priorite]
    return f'<span class="attente a-{priorite}" title="{libelle}">{jours} j</span>'


def texte_jours(jours):
    return "1 jour" if jours == 1 else f"{jours} jours"


def badge_depuis(jours, priorite, depuis, titre):
    """Pastille « N j » suivie, en toutes lettres, de ce qu'elle compte (« depuis l'acceptation », « depuis la fin des travaux ») :
    un nombre seul ne dit pas de quelle date on part. `titre` : l'explication complète, au survol."""
    return (f'<div class="depuis"><span class="attente a-{priorite}" title="{esc(titre)}">{jours} j</span> '
            f'<span class="doux">{esc(depuis)}</span></div>')


def champ_modalite(valeurs):
    """Mode de règlement prévu : UN seul choix (comptant, chèque, Interac, carte, autre)."""
    return liste("modalite_paiement", "Mode de règlement", [(m, LIBELLES_MODE[m]) for m in MODES], valeurs, vide="Non précisé")


def redirection(url):
    return ("303 See Other", [("Location", url)], b"")


def badge(code, libelle):
    return f'<span class="badge b-{esc(code)}">{esc(libelle)}</span>'


def texte_attente(reprise):
    """« reprise le lun. 1er juin » ou « jusqu'à nouvel ordre » : la fin de l'attente d'un chantier mis de côté."""
    return f"reprise {le_date(reprise)}" if reprise else "jusqu'à nouvel ordre"


def url_fiche(chantier_id, genre):
    """Adresse de la fiche : « soumission » (onglet Soumissions) ou « chantier » : même fiche, autre nom."""
    return f"/{'soumission' if genre == 'soumission' else 'chantier'}/{chantier_id}"


def badge_statut(statut, genre=None):
    """Pastille du statut ; « Refusée » (rouge) pour une soumission refusée."""
    refusee = statut == "annule" and genre == "soumission"
    return badge("refusee" if refusee else statut, libelle_statut(statut, genre))


def champ(nom, libelle, valeurs, type_="text", large=False, **attrs):
    extra = "".join(f' {k.replace("_", "-")}="{esc(v)}"' if v is not True else f' {k}' for k, v in attrs.items())
    classe = ' class="large"' if large else ""
    etoile = ' <span class="requis" title="obligatoire">*</span>' if attrs.get("required") else ""
    return (f'<div{classe}><label for="{nom}">{esc(libelle)}{etoile}</label>'
            f'<input id="{nom}" name="{nom}" type="{type_}" value="{esc(valeurs.get(nom, ""))}"{extra}></div>')


def zone(nom, libelle, valeurs, large=True):
    classe = ' class="large"' if large else ""
    return (f'<div{classe}><label for="{nom}">{esc(libelle)}</label>'
            f'<textarea id="{nom}" name="{nom}">{esc(valeurs.get(nom, ""))}</textarea></div>')


def liste(nom, libelle, options, valeurs, vide=None, **attrs):
    extra = "".join(f" {k}" for k, v in attrs.items() if v is True)
    choix = f'<option value="">{esc(vide)}</option>' if vide is not None else ""
    for code, lib in options:
        sel = " selected" if valeurs.get(nom) == code else ""
        choix += f'<option value="{esc(code)}"{sel}>{esc(lib)}</option>'
    etoile = ' <span class="requis" title="obligatoire">*</span>' if attrs.get("required") else ""
    return f'<div><label for="{nom}">{esc(libelle)}{etoile}</label><select id="{nom}" name="{nom}"{extra}>{choix}</select></div>'


def bloc_types(types, valeurs):
    lignes = ""
    for code, libelle in types:
        coche = " checked" if valeurs.get(f"type_{code}") else ""
        lignes += (f'<div class="type"><label class="coche"><input type="checkbox" name="type_{esc(code)}" value="1"{coche}>{esc(libelle)}</label>'
                   f'<input type="text" name="precision_{esc(code)}" value="{esc(valeurs.get("precision_" + code, ""))}" '
                   f'placeholder="Précision (facultatif) : quel arbre, quelle haie, combien…" aria-label="Précision pour {esc(libelle)}"></div>')
    return f'<div class="large types"><label>Types de travaux : coche un ou plusieurs</label>{lignes}</div>'


def select_secteur(secteurs, valeurs, nom="client_secteur", requis=True, tout=None):
    """Liste déroulante des secteurs desservis, groupés par ville (jamais de ville écrite à la main : pas de doublons)."""
    choisi = valeurs.get(nom, "")
    choix = f'<option value="">{esc(tout if tout is not None else "— choisir —")}</option>'
    groupes = {}
    for code, libelle, ville in secteurs:
        groupes.setdefault(ville, []).append((code, libelle))
    for ville, membres in groupes.items():
        options = "".join(f'<option value="{esc(c)}"{" selected" if c == choisi else ""}>{esc(l)}</option>' for c, l in membres)
        choix += f'<optgroup label="{esc(ville)}">{options}</optgroup>' if len(groupes) > 1 else options
    etoile = ' <span class="requis" title="obligatoire">*</span>' if requis else ""
    return f'<select id="{nom}" name="{nom}"{" required" if requis else ""}>{choix}</select>', etoile


def champ_secteur(secteurs, valeurs, requis=True):
    """Ville / secteur du client (liste déroulante ; obligatoire sauf dans une soumission)."""
    select, etoile = select_secteur(secteurs, valeurs, requis=requis)
    ancienne = valeurs.get("ville") if not valeurs.get("client_secteur") and valeurs.get("ville") else ""
    rappel = f'<div class="doux">Ville actuelle : {esc(ancienne)} — choisis le secteur correspondant.</div>' if ancienne else ""
    return f'<div><label for="client_secteur">Ville / secteur{etoile}</label>{select}{rappel}</div>'


def bloc_options_travaux(valeurs):
    """Options à connaître pour préparer la job : nacelle, sort du bois (jamais cachées dans les paramètres avancés)."""
    format_bois = valeurs.get("bois_format", "")
    options = "".join(f'<option value="{c}"{" selected" if c == format_bois else ""}>{esc(l)}</option>'
                      for c, l in (("16_pouces", "16 pouces"), ("4_pieds", "4 pieds")))
    return f"""<div class="large options-travaux"><label>Options du travail</label>
<div class="barre"><label class="coche"><input type="checkbox" name="nacelle" value="1"{" checked" if valeurs.get("nacelle") == "1" else ""}>Nacelle requise</label>
<label class="coche"><input type="checkbox" name="debarrasser_bois" id="debarrasser_bois" value="1"{" checked" if valeurs.get("debarrasser_bois") == "1" else ""}>Débarrasser le bois</label>
<span id="bois-format" class="coche">Bois laissé sur place, format :
<select name="bois_format" aria-label="Format du bois laissé sur place"><option value="">—</option>{options}</select></span></div>

<script>(function(){{var c=document.getElementById('debarrasser_bois'),b=document.getElementById('bois-format');
function m(){{b.style.display=c.checked?'none':'';}}c.addEventListener('change',m);m();}})();</script></div>"""


def puces_options(nacelle, debarrasser_bois, bois_format):
    """Options de la job, bien visibles : nacelle, sort du bois (vide si rien de particulier)."""
    puces = []
    if nacelle:
        puces.append("Nacelle requise")
    if debarrasser_bois:
        puces.append("Bois débarrassé")
    elif bois_format:
        puces.append("Bois laissé sur place : " + {"16_pouces": "16 pouces", "4_pieds": "4 pieds"}.get(bois_format, bois_format))
    return "".join(f'<span class="puce-opt">{esc(p)}</span>' for p in puces)


def _tel_lisible(valeurs, nom):
    """Dans le champ de saisie, « +18195550107 » s'affiche « 819-555-0107 » (enregistré, il reprend la forme de la base)."""
    t = valeurs.get(nom) or ""
    return {**valeurs, nom: f"{t[2:5]}-{t[5:8]}-{t[8:]}"} if len(t) == 12 and t.startswith("+1") and t[1:].isdigit() else valeurs


def client_essentiel(valeurs, secteurs, exige=True):
    """Ce qu'il faut pour retrouver un client : nom, téléphone, adresse des travaux, ville / secteur (liste).

    exige=False (soumission, ou client qui n'a que des soumissions) : rien n'est obligatoire.
    """
    return f"""<div class="carte"><h2>Client</h2><div class="grille">
{champ("client_nom", "Nom", valeurs, autocomplete="off")}{champ("client_prenom", "Prénom", valeurs, autocomplete="off")}
{champ("client_telephone", "Téléphone", _tel_lisible(valeurs, "client_telephone"), "tel", placeholder="450-555-0142")}
{champ("adresse", "Adresse (numéro + rue)", valeurs, large=True, placeholder="123 Rue des Érables", **({"required": True} if exige else {}))}
{champ_secteur(secteurs, valeurs, requis=exige)}</div></div>"""


def client_avance(valeurs):
    """Le reste de la fiche client (rarement utile) : à placer dans « Paramètres avancés »."""
    sms = " checked" if valeurs.get("client_sms_ok", "1") != "0" else ""
    return f"""<div class="carte"><h2>Client : autres informations</h2><div class="grille">
{champ("client_entreprise", "Entreprise / syndicat", valeurs)}{champ("client_telephone_2", "Téléphone 2", _tel_lisible(valeurs, "client_telephone_2"), "tel")}
{champ("client_courriel", "Courriel", valeurs, "email")}
<div><label>&nbsp;</label><label style="color:inherit"><input type="checkbox" name="client_sms_ok" value="1"{sms}>Rappels par texto acceptés</label></div>
{zone("client_notes", "Notes sur le client (préférences, historique)", valeurs)}
{champ("code_postal", "Code postal", valeurs, placeholder="J7Z 1A1")}{champ("province", "Province", valeurs, placeholder="QC")}
{zone("notes_acces", "Accès : barrière, chien, où stationner, où est l'arbre", valeurs)}</div>
<details style="margin-top:12px"><summary>Coordonnées GPS (seulement pour un lot sans numéro civique)</summary><div class="grille">
{champ("latitude", "Latitude", valeurs, inputmode="decimal", placeholder="45.6480")}
{champ("longitude", "Longitude (négative au Québec)", valeurs, inputmode="decimal", placeholder="-74.0920")}</div>
<p class="doux">Google Maps : clic droit sur l'endroit, puis cliquer sur les coordonnées pour les copier. Laisser vide sinon : le géocodage se fera plus tard.</p></details></div>"""


def avance(contenu, ouvert=False):
    """Section repliée « Paramètres avancés » : les options rarement utilisées. Les champs repliés sont quand même envoyés."""
    return (f'<details class="avance"{" open" if ouvert else ""}><summary>Paramètres avancés</summary>{contenu}</details>')
