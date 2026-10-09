"""Éléments d'affichage partagés par toutes les pages : styles, gabarit, composants de formulaire."""
import html
import re
import threading
from pathlib import Path
from urllib.parse import quote

from noyau import DB_DEFAUT, LIBELLES_MODE, LIBELLES_STATUT, MODES, adresses, libelle_statut  # noqa: F401  (réexportés pour les pages)

LIBELLES_PAIEMENT = {"a_payer": "À recevoir", "partiel": "Partiel",
                     "paye": "Payé", "a_venir": "À venir", "sans_objet": "—", "prix_manquant": "Prix manquant"}
MESSAGES = {
    "cree": "Chantier créé.",
    "cree_reutilise": "Chantier créé pour un client déjà dans la base (même adresse) : sa fiche a été réutilisée.",
    "maj": "Modifications enregistrées.",
    "paiement": "Paiement ajouté.",
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
.total{font-weight:700}.sel-total{position:sticky;bottom:0;background:var(--carte);border:1px solid var(--accent);border-radius:10px;padding:10px 16px;margin-top:12px}
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
@media (max-width:700px){table.liste th:nth-child(n+5),table.liste td:nth-child(n+5){display:none}}

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
.lien-pdf-coin{display:none;position:absolute;top:10px;right:14px;font-size:.78rem;font-weight:600;color:var(--doux)!important;text-decoration:underline}.carte.documents h2{margin:0 0 8px}.ligne-document{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:6px 0}.ligne-document b{min-width:112px}.ligne-document .actions-page .bouton{padding:8px 16px;font-size:.9rem}
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
.barre-mobile,.menu-tel{display:none}
/* Téléphone : cibles tactiles de 44 px, champs à 16 px (sinon l'iPhone zoome), tableaux de la journée en cartes */
@media (max-width:700px){
main,main.large,main.conteneur{padding:16px 12px 24px}.navbar{position:static}.nav-contenu{padding:10px 14px;gap:10px}.nav-bureau{display:none}.nav-droite .admin-seul{display:none}.nav-droite{gap:8px}
.bandeau-page{padding:18px 0 14px}.conteneur{padding:0 14px}.bandeau-page h1{font-size:1.5rem}
body{padding-bottom:84px}.pied{display:none}.puces{display:none}.recherche select{display:none}
.raccourcis-bloc{display:block}.tuiles{grid-template-columns:repeat(2,minmax(0,1fr))}.cellule-barre{display:none}.raccourcis{flex-wrap:nowrap;overflow-x:auto;padding-bottom:4px}.raccourcis .puce{flex:0 0 auto;min-width:110px}.raccourcis-bloc .modifier{display:inline-block;margin-top:8px}
.barre-mobile{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:1000;gap:6px;padding:10px 10px calc(10px + env(safe-area-inset-bottom));background:rgba(255,255,255,.96);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-top:1px solid var(--trait-leger)}
.barre-mobile a{flex:1 1 0;display:inline-flex;align-items:center;justify-content:center;min-height:48px;border-radius:10px;font-weight:700;font-size:.76rem;padding:0 2px;text-align:center;text-decoration:none;color:var(--vert-fonce);background:#fff;border:1px solid var(--trait);box-shadow:var(--ombre-sm)}
.barre-mobile a.actif{background:var(--vert-doux);border-color:var(--vert-bord);color:var(--vert)}
.barre-mobile a.principal{flex:1.35 1 0;background:var(--vert);border-color:transparent;color:#fff;box-shadow:var(--ombre-btn)}
.connexion{margin:20px auto}table.liste,.liste-defile table{border:0;box-shadow:none;background:none;border-radius:0}

button,.bouton{min-height:44px;display:inline-flex;align-items:center;justify-content:center}
input,select,textarea,.mini input,.mini select{font-size:16px;min-height:44px}.mini button,.actions-ligne .bouton,.actions-ligne button,.actions-page .bouton,.actions-page button{font-size:15px;min-height:44px;padding:8px 16px}
input[type=checkbox],input[type=radio]{min-height:0;width:22px;height:22px}
.recherche select,.recherche input,.cal-nav .bouton,.onglets{flex:1 1 auto}.recherche select{width:100%}
.cal-jour{min-height:58px;padding:4px 3px}.cal-ligne{display:none}.cal-info{font-size:11px}.cal-info b{display:block;font-size:0}.cal-info b::first-letter{font-size:13px}.cal-tete{font-size:11px}
td,th{white-space:normal!important}
table.tableau,table.tableau tbody,.liste-defile table,.liste-defile table tbody,table.liste,table.liste tbody{display:block}table.tableau thead,.liste-defile table thead,table.liste thead{display:none}
.liste-defile table tr,table.liste tr{display:block;border:1px solid var(--trait);border-radius:10px;margin:0 0 10px;padding:6px 4px}.liste-defile table td,table.liste td{display:block;border:0;padding:3px 8px;text-align:left!important}
.liste-defile table td:first-child,table.liste td:first-child{color:var(--doux);font-size:13px}.liste-defile table td.droite form{margin-top:4px}
table.liste td:nth-child(n+5){display:none}table.tableau tr{display:block;border:1px solid var(--trait);border-radius:10px;margin:0 0 10px;padding:6px 4px;background:var(--carte)}
table.tableau tr.sans-bas{margin-bottom:0;border-bottom:0;border-radius:10px 10px 0 0;padding-bottom:0}
table.tableau tr.ligne-actions{border-top:0;border-radius:0 0 10px 10px;padding-top:0}
table.tableau tr.diner{border:0;background:none;padding:0;text-align:center}table.tableau tr.diner td{padding:2px}
table.tableau td{display:block;border:0;padding:4px 8px;min-width:0!important;text-align:left!important}
table.tableau td.col-ordre{display:flex;align-items:center;gap:10px}table.tableau .col-ordre .fleches{margin:0}
table.tableau tr.ligne-actions td{text-align:left!important}.actions-ligne,.groupe-actions{flex-wrap:wrap}
.liste-defile{overflow-x:visible}.carte{padding:12px}
dl.lecture{grid-template-columns:1fr}.type{grid-template-columns:1fr}
.modale-carte{padding:18px}
/* barre du bas + feuille « Menu » */
.barre-mobile button.menu-bouton{flex:1 1 0;display:inline-flex;align-items:center;justify-content:center;min-height:48px;border-radius:10px;font-weight:700;font-size:.76rem;padding:0 2px;color:var(--vert-fonce);background:#fff;border:1px solid var(--trait);box-shadow:var(--ombre-sm)}
.barre-mobile button.menu-bouton.actif,body.menu-ouvert .barre-mobile button.menu-bouton{background:var(--vert-doux);border-color:var(--vert-bord);color:var(--vert)}
body.menu-ouvert .menu-tel{display:block}
.menu-fond{position:fixed;left:0;right:0;top:0;bottom:80px;background:rgba(14,52,29,.45);z-index:1001}
.menu-feuille{position:fixed;left:10px;right:10px;bottom:84px;z-index:1002;background:#fff;border-radius:18px;padding:8px;box-shadow:0 12px 40px rgba(0,0,0,.28)}
.menu-feuille a,.menu-feuille button{display:flex;align-items:center;justify-content:flex-start;width:100%;min-height:48px;padding:0 14px;border-radius:10px;border:0;background:none;box-shadow:none;font-weight:700;font-size:1rem;color:var(--vert-fonce);text-decoration:none}
.menu-feuille a.actif{background:var(--vert-doux);color:var(--vert)}.menu-feuille form{margin:0;border-top:1px solid var(--trait-leger);margin-top:4px;padding-top:4px}.menu-feuille form button{color:var(--doux);font-weight:600}
.menu-qui{padding:6px 14px;color:var(--doux);font-size:.85rem;font-weight:600}
/* chantiers : carte compacte */
table.chantiers tr{display:grid;grid-template-columns:1fr auto;gap:3px 10px;padding:10px 12px}
table.chantiers td{display:block!important;padding:0!important;font-size:14px}
table.chantiers td.c-client{grid-column:1;grid-row:1;font-size:16px;font-weight:700}
table.chantiers td.c-statut{grid-column:2;grid-row:1;text-align:right!important}table.chantiers td.c-statut .doux{font-size:12px}
table.chantiers td.c-adresse{grid-column:1/-1;grid-row:2;display:flex!important;flex-wrap:wrap;gap:0 8px}
table.chantiers td.c-travaux{grid-column:1;grid-row:3;display:flex!important;flex-wrap:wrap;gap:0 8px;align-items:baseline}
table.chantiers td.c-montant{grid-column:2;grid-row:3;text-align:right!important;font-size:16px;align-self:end}
table.chantiers td.c-depuis{grid-column:1;grid-row:4;color:var(--texte)!important;font-size:13px!important}
table.chantiers td.c-paiement{grid-column:2;grid-row:4;text-align:right!important}table.chantiers td.c-paiement .doux{font-size:12px}
table.chantiers td.c-depuis .depuis{margin:2px 0 0}
/* tableau de bord et journée : carte compacte, « Facture » en haut à droite */
.lien-pdf-coin{position:absolute;top:10px;right:12px}
table.tableau.jour tr.sans-bas,table.tableau.jour.gestion tr:not(.diner):not(.ligne-actions){position:relative;display:grid;grid-template-columns:auto 1fr auto;gap:2px 10px;padding:10px 12px}
table.tableau.jour td{padding:0!important}
table.tableau.jour td.c-heures{grid-column:1/-1;font-size:1rem;padding-right:70px!important}
table.tableau.jour td.c-client,table.tableau.jour td.c-adresse{grid-column:1/-1;display:flex!important;flex-wrap:wrap;align-items:baseline;gap:0 10px}
table.tableau.jour td.c-travaux{grid-column:1/3;display:block}
table.tableau.jour td.c-montant{grid-column:3;text-align:right!important;align-self:end}
table.tableau.jour .col-travaux{min-width:0!important}
table.tableau.jour tr.ligne-actions{padding:0 12px 10px}
table.tableau.jour tr.ligne-actions .groupe-actions{display:flex;width:100%}
table.tableau.jour tr.ligne-actions .bouton{flex:1}
table.tableau.jour .facture-pc{display:none}
table.tableau.jour.gestion td.col-ordre{grid-column:1;grid-row:1}table.tableau.jour.gestion td.c-heures{grid-column:2/-1;grid-row:1;align-self:center}
table.tableau.jour.gestion td.col-actions{grid-column:1/-1;margin-top:4px;min-width:0!important}
table.tableau.jour.gestion .actions-ligne{display:flex;gap:8px}table.tableau.jour.gestion .actions-ligne>*{flex:1}table.tableau.jour.gestion .actions-ligne .bouton,table.tableau.jour.gestion .actions-ligne button{width:100%}
table.tableau.jour.gestion .actions-ligne .groupe-actions{display:flex;flex:2;gap:8px}table.tableau.jour.gestion .actions-ligne .mini{display:block;flex:1}
/* journée : navigation et filtres sur téléphone */
form.nav-jour{display:grid;grid-template-columns:1fr 1.4fr 1fr;gap:8px}form.nav-jour>*{width:100%!important;max-width:none!important;min-width:0}
form.nav-jour a:nth-child(1){order:1}form.nav-jour input{order:2}form.nav-jour a:nth-child(4){order:3}form.nav-jour button{order:4}form.nav-jour a:nth-child(5){order:5}form.nav-jour a:nth-child(6){order:6}
form.nav-jour .bouton,form.nav-jour button{padding:6px 4px;font-size:13px;text-align:center}
form.filtres-jour{display:grid;grid-template-columns:1fr 1fr;gap:8px}form.filtres-jour select{display:block!important;width:100%;max-width:none}form.filtres-jour button{grid-column:1/-1}
table.candidats tr{display:grid;grid-template-columns:auto 1fr auto;gap:2px 10px;padding:10px 12px}
table.candidats td{padding:0!important}
table.candidats td.c-case{grid-column:1;grid-row:1}table.candidats td.c-depuis{grid-column:2;grid-row:1;display:flex!important;align-items:center;gap:8px;color:var(--texte)!important;font-size:13px!important}
table.candidats td.c-montant{grid-column:3;grid-row:1;text-align:right!important}
table.candidats td.c-client,table.candidats td.c-adresse,table.candidats td.c-travaux{grid-column:1/-1;display:flex!important;flex-wrap:wrap;gap:0 10px;align-items:baseline}
table.candidats td.c-travaux{display:block!important}
table.tableau.jour td.c-heures{color:var(--texte)!important;font-size:1rem!important}table.tableau.jour td.c-montant small{display:none}
.note-heures{display:none}.pied-jour{display:grid;grid-template-columns:1fr 1fr;gap:8px}.pied-jour .bouton{width:100%;padding:8px 6px;font-size:14px;min-height:42px;text-align:center}
table.tableau.jour.gestion td.col-ordre{display:flex!important;align-items:center;gap:6px;white-space:nowrap}table.tableau.jour.gestion .col-ordre .fleches{display:flex;gap:4px;margin:0}
table.tableau.jour.gestion .col-ordre button.fleche{min-height:34px;width:34px;padding:0}table.tableau.jour.gestion .col-ordre .doux{display:none}
table.candidats tr.ligne-urgente{border-left:4px solid var(--alerte)}table.candidats tr.ligne-surveiller{border-left:4px solid #e8c675}table.candidats td:first-child{box-shadow:none!important}
table.candidats td.c-montant small{display:none}.sel-total{bottom:76px;padding:8px 12px;font-size:13px;gap:8px}.sel-total button{width:100%;min-height:40px;padding:6px 10px;font-size:14px}
table.chantiers td.c-depuis:not(:has(.depuis))::before{content:"Accepté le ";color:var(--doux)}

/* Téléphone : calendrier compact aux couleurs de celui de l'ordinateur (un point sous les jours chargés), recherche sur une ligne, fiches compactes */
.cal-jour{min-height:52px;padding:4px 0;gap:3px;align-items:center;border-radius:10px}
.cal-jour .cal-n,.cal-jour.aujourdhui .cal-n{width:30px;height:30px;display:flex;align-items:center;justify-content:center;border-radius:50%;padding:0;font-size:1rem;font-weight:700;background:none;color:var(--texte);align-self:center}
.cal-jour.aujourdhui .cal-n{background:var(--vert);color:#fff}
.cal-jour.occupe::after{content:"";width:6px;height:6px;border-radius:50%;background:var(--vert);display:block}.cal-jour.chargee::after{background:var(--alerte)}
.cal-jour.selection{outline:2px solid var(--vert);outline-offset:-1px}
.cal-jour.autre-mois{opacity:.45}.cal-info,.cal-alerte{display:none}.cal-grille{gap:3px}
.cal-nav{flex-wrap:nowrap;gap:6px}.cal-nav h2{min-width:0;font-size:1.05rem}.cal-nav .bouton{flex:0 0 auto;min-height:40px;padding:6px 12px;font-size:13px}
.cal-nav a[aria-label]{font-size:0;padding:0;width:40px;position:relative}.cal-nav a[aria-label]::before{content:"";position:absolute;top:50%;left:50%;width:10px;height:10px;border:solid var(--vert-fonce);border-width:0 0 2.5px 2.5px;transform:translate(-30%,-50%) rotate(45deg)}
.cal-nav a[aria-label="Mois suivant"]::before{transform:translate(-70%,-50%) rotate(-135deg)}
.cal-nav a[href="/"]{order:3}
.recherche{flex-wrap:nowrap}.recherche input{flex:1 1 0;min-width:0}.recherche button{flex:0 0 auto}
.resume-chantier{position:relative;gap:6px}.resume-chantier>div:first-child{padding-right:84px}
.lien-pdf-coin{display:block}.documents-pc{display:none}
.lecture-seule{padding:10px 12px}.lecture-seule .barre{gap:6px}.lecture-seule .bouton{min-height:36px;padding:5px 10px;font-size:13px}.lecture-seule h2{font-size:1rem}.lecture-seule p{margin-top:4px!important}
.actions-page{gap:6px}.actions-page .bouton,.actions-page button{padding:8px 10px;font-size:14px;min-height:40px}
table.soumissions tr{position:relative;display:grid;grid-template-columns:1fr auto;gap:3px 10px;padding:10px 12px}
table.soumissions td{padding:0!important}
table.soumissions td:nth-child(1),table.soumissions td:nth-child(2),table.soumissions td:nth-child(3),table.soumissions td:nth-child(6){grid-column:1/-1}
table.soumissions td:nth-child(1),table.soumissions td:nth-child(2),table.soumissions td:nth-child(3),table.soumissions td:nth-child(4){display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px}
table.soumissions td:nth-child(1){padding-right:90px!important;align-items:center}table.soumissions td:nth-child(1) div{margin:0}
table.soumissions td:nth-child(2) .manque{flex-basis:100%;margin:0}
table.soumissions td:nth-child(5){display:block;text-align:right!important;align-self:end}
table.soumissions td.col-actions{margin-top:4px;min-width:0!important}
table.soumissions .actions-ligne{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
table.soumissions .actions-ligne .mini{display:block;margin:0}
table.soumissions .actions-ligne .bouton,table.soumissions .actions-ligne button{width:100%;min-height:40px;padding:6px 4px;font-size:14px}
table.soumissions .lien-pdf{position:absolute;top:10px;right:12px;width:auto!important;min-height:0!important;padding:2px 4px!important;border:0;background:none;box-shadow:none;color:var(--doux);font-size:12.5px!important;text-decoration:underline}
}
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


def _barre_mobile(section):
    """Téléphone : en bas, le plus important ; le reste dans la feuille « Menu »."""
    admin = est_admin()

    def lien(href, texte, actif):
        return f'<a href="{href}" class="{"actif" if actif else ""}">{texte}</a>'
    principaux = ([("/", "Tableau de bord", "tableau")] if admin else []) + [("/chantiers", "Chantiers", "chantiers"), ("/soumissions", "Soumissions", "soumissions")]
    reste = ([("/journee", "Journée", "journee"), ("/clients", "Clients", "clients"), ("/archives", "Archives", "archives")] if admin else [("/clients", "Clients", "clients")])
    if not admin:                          # compte « soumission » : ses trois onglets restent en bas
        principaux, reste = principaux + reste, []
    reste.append(("/nouveau", "Nouvelle soumission", "nouveau"))
    u = utilisateur_courant()
    if u and u["role"] == "admin":
        reste.append(("/utilisateurs", "Utilisateurs", "utilisateurs"))
    sortie = '<form method="post" action="/deconnexion"><button type="submit">Se déconnecter</button></form>' if u else ""
    qui = f'<div class="menu-qui">{esc(u["nom"])}</div>' if u else ""
    menu_actif = any(section == code for _, _, code in reste)
    bas = "".join(lien(h, t, section == c) for h, t, c in principaux)
    bas += f'<button type="button" class="menu-bouton{" actif" if menu_actif else ""}" onclick="document.body.classList.toggle(\'menu-ouvert\')" aria-label="Ouvrir le menu">Menu</button>'
    feuille = "".join(lien(h, t, section == c) for h, t, c in reste)
    return (f'<nav class="barre-mobile">{bas}</nav><div class="menu-tel"><div class="menu-fond" onclick="document.body.classList.remove(\'menu-ouvert\')"></div>'
            f'<div class="menu-feuille">{qui}{feuille}{sortie}</div></div>')


def gabarit(titre, contenu, message=None, erreur=None, large=False, public=False, section=None):
    msg = f'<div class="message">{esc(MESSAGES[message])}</div>' if message in MESSAGES else ""
    if erreur:
        msg += f'<div class="erreurs"><strong>Action refusée :</strong> {esc(erreur)}</div>'
    section = section or section_de(getattr(CONTEXTE, "chemin", ""))
    tete = f'<style>{CSS}</style></head><body>'
    entete = ('<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">'
              f'<meta name="theme-color" content="#0e341d"><title>{esc(titre)} — SylvainCulteur</title>')
    if public:           # page de connexion et refus : pas de menu
        return f'<!doctype html><html lang="fr-CA"><head>{entete}{tete}<main class="connexion-page">{msg}{contenu}</main></body></html>'
    classe_large = " large" if large else ""
    bandeau = ""
    m = re.match(r"\s*(<h1[^>]*>.*?</h1>)", contenu, re.S)
    if m:              # le titre de la page va dans un bandeau vert pâle, comme le haut du site
        bandeau = (f'<section class="bandeau-page"><div class="conteneur{classe_large}"><span class="tag-badge">{esc(NOMS_SECTIONS.get(section, "Sylvainculteur"))}</span>{m.group(1)}</div></section>')
        contenu = contenu[m.end():]
    return (f'<!doctype html><html lang="fr-CA"><head>{entete}{tete}{_navigation(section)}{bandeau}'
            f'<main class="conteneur{classe_large}">{msg}{contenu}</main>'
            '<footer class="pied"><b>Sylvainculteur</b> · Depuis 2008 · Gestion interne</footer>'
            f'{_barre_mobile(section)}{SCRIPT_POSITION}</body></html>')


# Changer de jour, de mois ou de filtre sur la même page : on reste à la même hauteur au lieu de remonter en haut.
SCRIPT_POSITION = (
    '<script>(function(){var k="pos:"+location.pathname;try{var v=sessionStorage.getItem(k);'
    'if(v!==null){sessionStorage.removeItem(k);window.scrollTo(0,parseInt(v,10)||0);}}catch(e){}'
    'function g(){try{sessionStorage.setItem(k,String(window.pageYOffset));}catch(e){}}'
    'document.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a[href]");'
    'if(a&&!a.target&&a.pathname===location.pathname&&a.origin===location.origin&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey)g();});'
    'document.addEventListener("submit",function(e){var f=e.target;if(f.method&&f.method.toLowerCase()==="get"&&'
    'new URL(f.action||location.href,location.href).pathname===location.pathname)g();});})();</script>')


def heures(h):
    """2.5 -> « 2 h 30 » ; 3.0 -> « 3 h » ; None -> « — »."""
    if h is None:
        return "—"
    minutes = round(h * 60)
    return f"{minutes // 60} h" + (f" {minutes % 60:02d}" if minutes % 60 else "")


def case_taxes(nom, cochee):
    """« Ajouter TPS et TVQ » : sur sa propre ligne de la grille (le libellé est trop long pour une colonne)."""
    return (f'<div class="large"><label class="coche"><input type="checkbox" name="{nom}" value="1"{" checked" if cochee else ""}>'
            'Ajouter TPS 5 % et TVQ 9,975 %</label></div>')


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
    """« reprise le 2026-06-01 » ou « jusqu'à nouvel ordre » : la fin de l'attente d'un chantier mis de côté."""
    return f"reprise le {reprise}" if reprise else "jusqu'à nouvel ordre"


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
    return f'<div class="large"><label>Types de travaux : coche un ou plusieurs</label>{lignes}</div>'


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
<p class="doux" style="margin:4px 0 0">Abattage / élagage : si le bois n'est pas débarrassé, précise son format (16 pouces ou 4 pieds).</p>
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


def client_essentiel(valeurs, secteurs, exige=True):
    """Ce qu'il faut pour retrouver un client : nom, téléphone, adresse des travaux, ville / secteur (liste).

    exige=False (soumission, ou client qui n'a que des soumissions) : rien n'est obligatoire.
    """
    return f"""<div class="carte"><h2>Client</h2><div class="grille">
{champ("client_nom", "Nom", valeurs, autocomplete="off")}{champ("client_prenom", "Prénom", valeurs, autocomplete="off")}
{champ("client_telephone", "Téléphone", valeurs, "tel", placeholder="450-555-0142")}
{champ("adresse", "Adresse (numéro + rue)", valeurs, large=True, placeholder="123 Rue des Érables", **({"required": True} if exige else {}))}
{champ_secteur(secteurs, valeurs, requis=exige)}</div></div>"""


def client_avance(valeurs):
    """Le reste de la fiche client (rarement utile) : à placer dans « Paramètres avancés »."""
    sms = " checked" if valeurs.get("client_sms_ok", "1") != "0" else ""
    return f"""<div class="carte"><h2>Client : autres informations</h2><div class="grille">
{champ("client_entreprise", "Entreprise / syndicat", valeurs)}{champ("client_telephone_2", "Téléphone 2", valeurs, "tel")}
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
