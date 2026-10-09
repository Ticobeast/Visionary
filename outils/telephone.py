"""Feuille de style du TÉLÉPHONE (écrans de 700 px et moins) : léger, aéré, à la façon des applications d'Apple.

Principes : un grand titre sans bandeau ; des cartes blanches arrondies, sans bordure ; des boutons « teintés » (fond vert très pâle)
sauf l'action principale ; des champs gris clair sans contour ; des flèches plutôt que des mots (« Précédent » devient une flèche) ;
une barre d'onglets en bas (icône + nom) et un menu qui monte du bas pour le reste ; des cibles tactiles d'au moins 44 px et des
champs à 16 px (sinon l'iPhone zoome à la saisie). Les ordinateurs ne voient rien de tout cela : tout est dans le @media.
"""

CSS_TELEPHONE = r"""
@media (max-width:700px){
:root{--ombre-carte:0 2px 8px rgba(15,23,42,.04)}
html{-webkit-text-size-adjust:100%}
body{background:var(--fond);padding-bottom:calc(84px + env(safe-area-inset-bottom))}
.pied,.puces,.nav-bureau,.nav-droite,.tag-badge,.pc-seul,.cellule-barre{display:none!important}

/* en-tête : le logo, puis un grand titre */
.navbar{position:static;background:none;backdrop-filter:none;-webkit-backdrop-filter:none;border:0}
.nav-contenu{padding:14px 18px 0}.logotype{font-size:1.1rem}
.bandeau-page{background:none;border:0;padding:4px 0 2px}.bandeau-page .conteneur{padding:0 18px}
.bandeau-page h1{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:1.95rem;letter-spacing:-.03em;line-height:1.1}
.bandeau-page h1::before{content:"";flex-basis:100%;order:1;height:0;margin-top:-8px}
.bandeau-page h1 a{order:2;display:inline-flex;margin:0;padding:4px 11px;border-radius:99px;background:#fff;box-shadow:var(--ombre-carte);font-size:.76rem;font-weight:600;letter-spacing:0;color:var(--vert);text-decoration:none}
main,main.large,main.conteneur{padding:10px 16px 28px}
.message,.erreurs{border-radius:14px;margin-bottom:12px;padding:12px 14px}

/* cartes, titres, boutons, champs */
.carte,details.avance{border:1px solid var(--trait-leger);border-radius:18px;padding:16px;box-shadow:var(--ombre-carte);margin-bottom:14px}
.carte h2,details.avance h2{font-size:1.05rem;margin-bottom:10px}
details.avance{padding:4px 16px}details.avance>summary{padding:12px 0;font-size:.95rem}details.avance .carte{box-shadow:none;padding:12px 0;margin-bottom:0;border:0;border-top:1px solid var(--trait-leger);border-radius:0}
button,.bouton{min-height:44px;display:inline-flex;align-items:center;justify-content:center;border-radius:12px;padding:10px 18px;font-size:15px;box-shadow:none;transform:none!important}
button.secondaire,.bouton.secondaire{background:#fff;border:1px solid var(--trait);color:var(--vert-fonce);box-shadow:var(--ombre-carte)}
button.danger{background:#fff;border:1px solid var(--alerte);color:var(--alerte)}
button.lien{min-height:0}
input,select,textarea{font-size:16px;min-height:46px;background:#fff;border:1px solid var(--trait);border-radius:10px;padding:11px 14px}
input:focus,select:focus,textarea:focus{border-color:var(--vert);outline:0}
select{-webkit-appearance:none;appearance:none;padding-right:34px;background-image:linear-gradient(45deg,transparent 50%,#6b7a69 50%),linear-gradient(135deg,#6b7a69 50%,transparent 50%);background-position:calc(100% - 19px) 52%,calc(100% - 14px) 52%;background-size:5px 5px,5px 5px;background-repeat:no-repeat}
textarea{min-height:90px}
label{font-size:.8rem;font-weight:600;color:var(--doux);margin-bottom:5px}
label.coche,span.coche{font-size:1rem;color:var(--texte);font-weight:500}
input[type=radio]{min-height:0;width:24px;height:24px;padding:0;accent-color:var(--vert)}
input[type=checkbox]{-webkit-appearance:none;appearance:none;flex:0 0 auto;min-height:0;width:22px;height:22px;padding:0;border:2px solid var(--trait);border-radius:6px;background:#fff center/14px no-repeat}
input[type=checkbox]:checked{background-color:var(--vert);border-color:var(--vert);background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3.4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12.5l4.5 4.5L19 7.5'/%3E%3C/svg%3E")}
.grille{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.grille .large{grid-column:1/-1}
.type{display:block;margin-bottom:6px}.type input[type=text]{margin-top:6px}
@supports selector(:has(a)){.type input[type=text]{display:none}.type:has(input[type=checkbox]:checked) input[type=text]{display:block}}
dl.lecture{grid-template-columns:1fr;gap:2px}dl.lecture dt{margin-top:8px}
.lecture-seule{padding:12px 14px;border-radius:16px;border:1px solid var(--trait-leger);background:#fff;box-shadow:var(--ombre-carte)}.lecture-seule .barre{gap:8px}
.lecture-seule h2{font-size:1.05rem}.lecture-seule .bouton{min-height:36px;padding:4px 12px;font-size:13px}.lecture-seule p{margin-top:4px!important}.lecture-seule .doux{display:none}

/* recherche : le champ et, à droite, le bouton (loupe) */
.recherche{flex-wrap:nowrap;gap:8px;margin-bottom:12px}.recherche input{flex:1 1 0;min-width:0}.recherche select{display:none}
.recherche button{flex:0 0 46px;width:46px;padding:0;font-size:0;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2.4' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='6.5'/%3E%3Cpath d='M16 16l4.5 4.5'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:center;background-size:22px}
.recherche button.secondaire{background-color:#fff;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%230e341d' stroke-width='2.4' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='6.5'/%3E%3Cpath d='M16 16l4.5 4.5'/%3E%3C/svg%3E")}

/* raccourcis : pastilles à faire défiler */
.raccourcis-bloc{display:block;margin-bottom:10px}
.raccourcis{flex-wrap:nowrap;overflow-x:auto;gap:8px;padding:2px 0 6px;margin:0 -16px;padding-left:16px;padding-right:16px;scrollbar-width:none}.raccourcis::-webkit-scrollbar{display:none}
.raccourcis .puce,.puce{flex:0 0 auto;min-width:0;display:inline-flex;align-items:baseline;gap:7px;padding:9px 14px;border:1px solid var(--trait);border-radius:99px;background:#fff;box-shadow:var(--ombre-carte);white-space:nowrap}
.puce b{font-size:1rem;font-weight:800}.puce span{font-size:.8rem;color:var(--doux);font-weight:600}
.puce.actif{background:var(--vert);border-color:var(--vert);box-shadow:none}.puce.actif b,.puce.actif span{color:#fff}
.raccourcis-bloc .modifier{display:none}
.raccourcis .modifier-puce{flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;padding:9px 14px;border:1px solid var(--trait);border-radius:99px;background:#fff;box-shadow:var(--ombre-carte);color:var(--doux);font-size:.8rem;font-weight:600;text-decoration:none;white-space:nowrap}
.raccourcis .modifier-puce::before{content:"";width:16px;height:16px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 20h4l10.5-10.5a2.1 2.1 0 00-4-4L4 16z'/%3E%3Cpath d='M13.5 6.5l4 4'/%3E%3C/svg%3E") center/16px no-repeat}
.tuiles{display:flex;flex-wrap:nowrap;overflow-x:auto;gap:10px;margin:0 -16px 14px;padding:2px 16px 8px;scrollbar-width:none}.tuiles::-webkit-scrollbar{display:none}
.tuile{flex:0 0 148px;border:1px solid var(--trait-leger);box-shadow:var(--ombre-carte);padding:12px 14px}.tuile b{font-size:1.25rem}.tuile span{font-size:.8rem;line-height:1.25}
.intro-page{display:none}

/* barre d'onglets du bas (icône + nom) et feuille « Menu » */
.barre-mobile{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:1000;justify-content:space-around;gap:0;padding:6px 6px calc(6px + env(safe-area-inset-bottom));background:rgba(255,255,255,.88);backdrop-filter:saturate(180%) blur(22px);-webkit-backdrop-filter:saturate(180%) blur(22px);border-top:.5px solid rgba(14,52,29,.16)}
.barre-mobile a,.barre-mobile button.menu-bouton{flex:1 1 0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;min-height:50px;padding:2px 0;border:0;border-radius:0;background:none!important;box-shadow:none;color:#7c877b;font-size:10.5px;font-weight:600;text-decoration:none;line-height:1.1}
.barre-mobile svg{width:26px;height:26px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.barre-mobile a.actif,.barre-mobile button.menu-bouton.actif,body.menu-ouvert .barre-mobile button.menu-bouton{color:var(--vert)}
body.menu-ouvert .menu-tel{display:block}
.menu-fond{position:fixed;inset:0;background:rgba(14,52,29,.38);z-index:1001;-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}
.menu-feuille{position:fixed;left:10px;right:10px;bottom:calc(76px + env(safe-area-inset-bottom));z-index:1002;background:#fff;border-radius:20px;padding:6px 6px 8px;box-shadow:0 14px 44px rgba(0,0,0,.25)}
.menu-feuille a,.menu-feuille button{display:flex;align-items:center;justify-content:flex-start;width:100%;min-height:50px;padding:0 16px;border:0;border-radius:12px;background:none;box-shadow:none;font-size:1.02rem;font-weight:600;color:var(--vert-fonce);text-decoration:none}
.menu-feuille a.actif{background:var(--vert-doux);color:var(--vert)}
.menu-feuille form{margin:4px 0 0;padding-top:4px;border-top:.5px solid var(--trait)}.menu-feuille form button{color:var(--doux);font-weight:500}
.menu-qui{padding:8px 16px 4px;color:var(--doux);font-size:.8rem;font-weight:600}

/* listes : une carte par ligne */
.liste-defile{overflow:visible}
table:not(.stat),table:not(.stat) tbody{display:block;border:0;box-shadow:none;background:none;border-radius:0}
table:not(.stat) thead{display:none}
table:not(.stat) tr{display:block;background:#fff;border:1px solid var(--trait-leger);border-radius:18px;box-shadow:var(--ombre-carte);margin:0 0 10px;padding:12px 16px}
table:not(.stat) td{display:block;border:0;padding:2px 0;text-align:left!important;min-width:0!important;white-space:normal!important;font-size:14px;color:var(--texte)}
table:not(.stat) td:first-child{color:var(--texte);font-size:14px}
table:not(.stat) tr.diner{background:none;border:0;box-shadow:none;padding:0;text-align:center}table:not(.stat) tr.diner td{text-align:center!important;color:var(--doux);font-size:12px}
table:not(.stat) .groupe-secteur td,table:not(.stat) tr:has(> td[colspan]){background:none;border:0;box-shadow:none;padding:6px 4px 2px}
table.stat th,table.stat td{font-size:13px;padding:6px 6px}

/* chantiers */
table.chantiers tr{display:grid;grid-template-columns:1fr auto;gap:3px 10px}
table.chantiers td{padding:0}
table.chantiers td.c-client{grid-column:1;grid-row:1;font-size:1.06rem;font-weight:700}table.chantiers td.c-client a{color:var(--vert-fonce)}
table.chantiers td.c-statut{grid-column:2;grid-row:1;text-align:right!important}
table.chantiers td.c-adresse{grid-column:1/-1;grid-row:2;display:flex;flex-wrap:wrap;gap:0 8px}
table.chantiers td.c-travaux{grid-column:1;grid-row:3;display:flex;flex-wrap:wrap;gap:0 8px;align-items:baseline}
table.chantiers td.c-montant{grid-column:2;grid-row:3;text-align:right!important;font-size:1.06rem;font-weight:800;align-self:end}
table.chantiers td.c-depuis{grid-column:1;grid-row:4;font-size:13px;align-self:center}
table.chantiers td.c-paiement{grid-column:2;grid-row:4;text-align:right!important}
table.chantiers td.c-paiement .doux,table.chantiers td.c-statut .doux{font-size:12px}
table.chantiers td.c-statut .doux{display:none}
table.chantiers td .depuis{margin:3px 0 0}
table.chantiers td.c-depuis:has(.tel-seul) .date-depuis{display:none}
table.chantiers td.c-depuis:not(:has(.depuis)):not(:has(.tel-seul))::before{content:"Accepté le ";color:var(--doux)}
.tel-seul{display:inline!important;color:var(--texte)}

/* soumissions */
table.soumissions tr{position:relative;display:grid;grid-template-columns:1fr auto;gap:3px 10px}
table.soumissions td{padding:0}
table.soumissions td:nth-child(1),table.soumissions td:nth-child(2),table.soumissions td:nth-child(3),table.soumissions td:nth-child(6){grid-column:1/-1}
table.soumissions td:nth-child(1),table.soumissions td:nth-child(2),table.soumissions td:nth-child(3),table.soumissions td:nth-child(4){display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px}
table.soumissions td:nth-child(1){padding-right:96px;align-items:center;font-size:13px;color:var(--doux)}table.soumissions td:nth-child(1) div{margin:0}
table.soumissions td:nth-child(2) a{font-size:1.06rem;font-weight:700;color:var(--vert-fonce)}table.soumissions td:nth-child(2) .manque{flex-basis:100%;margin:0}
table.soumissions td:nth-child(2) .doux{margin:0}table.soumissions td:nth-child(2) a.tel{font-size:.9rem;font-weight:400;color:var(--vert)}
table.soumissions td:nth-child(5){text-align:right!important;align-self:end;font-size:1.06rem;font-weight:800}
table.soumissions td.col-actions{margin-top:6px}
table.soumissions .actions-ligne{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
table.soumissions .actions-ligne .mini{display:block;margin:0}
table.soumissions .actions-ligne .bouton,table.soumissions .actions-ligne button{width:100%;min-height:42px;padding:6px 4px;font-size:14px}
table.soumissions .lien-pdf,.lien-pdf-coin{position:absolute;top:12px;right:14px;width:auto!important;min-height:0!important;padding:2px 4px!important;border:0;background:none!important;box-shadow:none;font-size:.78rem!important;font-weight:600;color:var(--doux)!important;text-decoration:underline}
.lien-pdf-coin{display:block}.documents-pc{display:none}

/* fiche : résumé et boutons */
.resume-chantier{position:relative;gap:4px}.resume-chantier>div:first-child{padding-right:84px}.resume-chantier h2{font-size:1.15rem}
.resume-chantier .montant{font-size:1.2rem}
.actions-bloc{margin-bottom:12px}

/* calendrier */
.cal-nav{flex-wrap:nowrap;gap:8px;margin-bottom:8px}.cal-nav h2{min-width:0;font-size:1.1rem;margin:0}
.cal-nav .bouton{flex:0 0 auto;min-height:40px;padding:6px 12px;font-size:13px}
.cal-nav a[aria-label]{font-size:0;padding:0;width:40px;position:relative}.cal-nav a[aria-label]::before{content:"";position:absolute;top:50%;left:50%;width:10px;height:10px;border:solid var(--vert-fonce);border-width:0 0 2.5px 2.5px;transform:translate(-30%,-50%) rotate(45deg)}
.cal-nav a[aria-label="Mois suivant"]::before{transform:translate(-70%,-50%) rotate(-135deg)}.cal-nav a[href="/"]{order:3}
.cal-tete{font-size:11px}.cal-grille{gap:0}
.cal-jour{min-height:50px;border:0!important;background:none!important;box-shadow:none;border-radius:0;align-items:center;gap:3px;padding:4px 0}
.cal-jour.weekend{background:var(--vert-doux)!important}
.cal-jour .cal-n,.cal-jour.aujourdhui .cal-n{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;padding:0;font-size:1.05rem;font-weight:700;background:none;color:var(--texte);align-self:center}
.cal-jour.aujourdhui .cal-n{background:var(--vert)!important;color:#fff!important}
.cal-jour.selection{outline:0}.cal-jour.selection .cal-n{background:var(--vert-fonce);color:#fff}.cal-jour.aujourdhui.selection .cal-n{background:var(--vert)}
.cal-jour.occupe::after{content:"";width:6px;height:6px;border-radius:50%;background:var(--vert);display:block}.cal-jour.chargee::after{background:var(--alerte)}
.cal-jour.autre-mois{opacity:.4}.cal-info,.cal-alerte,.cal-ligne{display:none}

/* jour du tableau de bord et page de gestion du jour */
.note-heures{display:none}.resume-jour,.total-jour{display:inline;margin:0;font-size:14px}.resume-jour::after{content:" · "}.total-jour .total{white-space:nowrap}.total-jour .doux{display:none}
.pied-jour{display:grid;grid-template-columns:1fr 1fr;gap:8px}.pied-jour .bouton{width:100%;padding:8px 6px;font-size:14px;text-align:center}
.lien-pdf-coin{top:12px;right:14px}
table.tableau.jour tr.sans-bas,table.tableau.jour.gestion tr:not(.diner):not(.ligne-actions){position:relative;display:grid;grid-template-columns:auto 1fr auto;gap:2px 10px;background:var(--fond);border:1px solid var(--trait-leger);border-bottom:0;box-shadow:none}
.carte table.tableau.jour tr{background:var(--fond);box-shadow:none}
table.tableau.jour td{padding:0}
table.tableau.jour td.c-heures{grid-column:1/-1;font-size:.98rem;font-weight:700;padding-right:70px}table.tableau.jour td.c-heures .heures{font-size:.98rem}
table.tableau.jour td.c-client,table.tableau.jour td.c-adresse{grid-column:1/-1;display:flex;flex-wrap:wrap;align-items:baseline;gap:0 10px}
table.tableau.jour td.c-client a{font-size:1.06rem;font-weight:700;color:var(--vert-fonce)}
table.tableau.jour td.c-adresse a,table.tableau.jour td.c-travaux a{font-weight:400;color:var(--texte)}
table.tableau.jour td.c-travaux{grid-column:1/3;display:block}table.tableau.jour .col-travaux{min-width:0}
table.tableau.jour td.c-montant{grid-column:3;text-align:right!important;align-self:end}table.tableau.jour td.c-montant small{display:none}
table.tableau.jour:not(.gestion) .c-adresse .doux,table.tableau.jour:not(.gestion) .ligne-duree,table.tableau.jour:not(.gestion) .ligne-options,table.tableau.jour:not(.gestion) .ligne-desc{display:none}
table.tableau.jour tr.ligne-actions{padding:0 0 12px;background:var(--fond);border:1px solid var(--trait-leger);border-top:0;box-shadow:none;margin-top:0;border-radius:0 0 18px 18px}
table.tableau.jour tr.sans-bas{border-radius:18px 18px 0 0;margin-bottom:0}
table.tableau.jour tr.ligne-actions td{padding:0 16px}
table.tableau.jour tr.ligne-actions .groupe-actions{display:flex;width:100%}table.tableau.jour tr.ligne-actions .bouton{flex:1}
table.tableau.jour .facture-pc{display:none}
table.tableau.jour.gestion td.col-ordre{grid-column:1;grid-row:1;display:flex;align-items:center;gap:6px;white-space:nowrap}
table.tableau.jour.gestion .col-ordre .fleches{display:flex;gap:4px;margin:0}table.tableau.jour.gestion .col-ordre button.fleche{min-height:34px;width:34px;padding:0}table.tableau.jour.gestion .col-ordre .doux{display:none}
table.tableau.jour.gestion td.c-heures{grid-column:2/-1;grid-row:1;align-self:center}
table.tableau.jour.gestion td.col-actions{grid-column:1/-1;margin-top:6px}
table.tableau.jour.gestion .actions-ligne{display:flex;gap:8px}table.tableau.jour.gestion .actions-ligne>*{flex:1}
table.tableau.jour.gestion .actions-ligne .bouton,table.tableau.jour.gestion .actions-ligne button{width:100%}
table.tableau.jour.gestion .actions-ligne .groupe-actions{display:flex;flex:2;gap:8px}table.tableau.jour.gestion .actions-ligne .mini{display:block;flex:1}
/* page du jour : flèches sur les côtés (sans gros bouton), la date au centre, un seul bouton « Aujourd'hui » */
form.nav-jour{display:grid;grid-template-columns:34px 1fr 34px;gap:0 6px;align-items:center;margin-bottom:10px}form.nav-jour>*{min-width:0}
form.nav-jour button{display:none}
form.nav-jour input{grid-column:2;grid-row:1;width:100%;max-width:none!important;text-align:center;font-weight:600}
form.nav-jour a.nj-prec,form.nav-jour a.nj-suiv{grid-row:1;min-height:44px;width:34px;padding:0;border:0;background:none;box-shadow:none;font-size:0;position:relative}
form.nav-jour a.nj-prec{grid-column:1}form.nav-jour a.nj-suiv{grid-column:3}
form.nav-jour a.nj-prec::before,form.nav-jour a.nj-suiv::before{content:"";position:absolute;top:50%;left:50%;width:11px;height:11px;border:solid var(--vert-fonce);border-width:0 0 2.6px 2.6px;transform:translate(-30%,-50%) rotate(45deg)}
form.nav-jour a.nj-suiv::before{transform:translate(-70%,-50%) rotate(-135deg)}
form.nav-jour a.nj-auj{display:flex!important;grid-column:1/-1;justify-self:center;margin-top:8px;min-height:36px;padding:4px 18px;font-size:13px}
/* page du jour : les quatre filtres sont repliés sous un seul bouton « Filtres » */
form.filtres-jour{display:block;margin-bottom:12px}
form.filtres-jour .filtres-bascule{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:46px;padding:0 16px;border:1px solid var(--trait);border-radius:12px;background:#fff;box-shadow:var(--ombre-carte);color:var(--vert-fonce);font-weight:700;font-size:16px}
form.filtres-jour .filtres-bascule::after{content:"";width:8px;height:8px;border:solid var(--vert-fonce);border-width:0 2.2px 2.2px 0;transform:rotate(45deg);margin-top:-4px}
form.filtres-jour.ouvert .filtres-bascule::after{transform:rotate(-135deg);margin-top:4px}
form.filtres-jour select,form.filtres-jour button[type=submit]{display:none}
form.filtres-jour.ouvert{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:6px 14px 14px;border:1px solid var(--trait-leger);border-radius:18px;background:#fff;box-shadow:var(--ombre-carte)}
form.filtres-jour.ouvert .filtres-bascule{grid-column:1/-1;border:0;box-shadow:none;padding:0;min-height:40px}
form.filtres-jour.ouvert select{display:block;width:100%;max-width:none}
form.filtres-jour.ouvert button[type=submit]{display:inline-flex;grid-column:1/-1;width:100%;flex:none;font-size:15px;background-image:none}
table.candidats tr{display:grid;grid-template-columns:auto 1fr auto;gap:2px 10px}
table.candidats td{padding:0}
table.candidats td.c-case{grid-column:1;grid-row:1}
table.candidats td.c-depuis{grid-column:2;grid-row:1;display:flex;align-items:center;gap:8px;font-size:13px}
table.candidats td.c-montant{grid-column:3;grid-row:1;text-align:right!important;font-weight:800}table.candidats td.c-montant small{display:none}
table.candidats td.c-client,table.candidats td.c-adresse,table.candidats td.c-travaux{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:0 10px;align-items:baseline}
table.candidats td.c-client a{font-size:1.06rem;font-weight:700;color:var(--vert-fonce)}table.candidats td.c-travaux{display:block}
table.candidats tr.ligne-urgente{border-left:4px solid var(--alerte)}table.candidats tr.ligne-surveiller{border-left:4px solid #e8c675}table.candidats td:first-child{box-shadow:none!important}
.sel-total{bottom:calc(76px + env(safe-area-inset-bottom));padding:10px 14px;font-size:13px;gap:8px;border:0;border-radius:16px;box-shadow:0 8px 28px rgba(14,52,29,.22)}.sel-total button{width:100%}

/* fiche client : l'historique avec le badge à droite ; « Supprimer » discret (le texte est dans la confirmation) */
table.historique tr{display:grid;grid-template-columns:1fr auto;align-items:center;gap:2px 10px}
table.historique td{padding:0}
table.historique td.c-date{grid-column:1;grid-row:1;font-weight:700}table.historique td.c-date a{color:var(--vert-fonce)}
table.historique td.c-travaux{grid-column:1;grid-row:2}
table.historique td.c-statut{grid-column:2;grid-row:1/3;justify-self:end;text-align:right!important}
.carte.suppression{padding:0;border:0;box-shadow:none;background:none;margin:6px 0 0}.carte.suppression h2,.carte.suppression p{display:none}
.carte.suppression button{min-height:38px;padding:6px 16px;font-size:13px}
.verrou-termine{margin:0 0 12px;padding:12px 14px;border-radius:16px;font-size:.9rem;line-height:1.4}

/* formulaires : types et options en tuiles, boutons d'action pleine largeur */
.grille.une-colonne{grid-template-columns:1fr}
form>.barre>button[type=submit]:first-child:not(.secondaire):not(.danger){flex:1 1 auto}
.types{display:grid;grid-template-columns:1fr 1fr;gap:8px}.types>label{grid-column:1/-1;margin:0}
.types .type{margin:0}.types .type label.coche,.options-travaux label.coche{display:flex;width:100%;min-height:48px;padding:0 12px;gap:10px;border:1px solid var(--trait-leger);border-radius:12px;background:var(--fond);font-size:.98rem}
.options-travaux .barre{display:grid;grid-template-columns:1fr;gap:8px}.options-travaux>label{margin-bottom:8px}
.options-travaux #bois-format{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:2px 2px 0;font-size:.95rem;color:var(--doux)}
.options-travaux #bois-format select{flex:1 1 140px;width:auto}
@supports selector(:has(a)){
.grille>div:has(>input[type=tel]),.grille>div:has(>#client_secteur){grid-column:1/-1}
.types .type:has(input[type=checkbox]:checked){grid-column:1/-1}
.types .type label.coche:has(input:checked),.options-travaux label.coche:has(input:checked){background:#fff;border-color:var(--vert);box-shadow:var(--ombre-carte);color:var(--vert-fonce);font-weight:700}
}

/* fiches : étiquettes discrètes, boutons côte à côte */
.carte p>b:first-child,.lecture-seule p>b:first-child,.lecture-seule p b{color:var(--doux);font-weight:600;font-size:.8rem}
.carte p{margin-bottom:0}.carte p+form{margin-top:12px}.carte p a{font-weight:500}
.lecture-seule .barre{display:grid;grid-template-columns:1fr 1fr;gap:8px}.lecture-seule .barre h2{grid-column:1/-1}
.lecture-seule .barre .bouton{width:100%;min-height:40px;font-size:13px}.lecture-seule p a{font-weight:500}
.actions-client{display:grid;grid-template-columns:1fr 1fr;gap:8px}.actions-client .bouton{width:100%;padding:8px 6px;font-size:14px}
.actions-page{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.actions-page>*{min-width:0}.actions-page form{display:block;width:100%}.actions-page .bouton,.actions-page button{width:100%;flex:none;white-space:normal;text-align:center;line-height:1.15}
.actions-page>:last-child:nth-child(odd){grid-column:1/-1}
.actions-page.actions-sou{grid-template-columns:repeat(3,1fr)}.actions-page.actions-sou>:first-child{grid-column:1/-1}.actions-page.actions-sou>:last-child:nth-child(odd){grid-column:auto}
.carte.documents{display:grid;grid-template-columns:1fr 1fr;gap:10px}.carte.documents h2{grid-column:1/-1;margin:0}
.ligne-document{display:block;padding:0;margin:0}.ligne-document b{display:none}.ligne-document:only-of-type{grid-column:1/-1}
.ligne-document .actions-page{display:block}.ligne-document .bouton{width:100%}
.barre-ajout{position:absolute;top:-54px;right:16px;margin:0!important}
.barre-ajout .bouton{width:44px;height:44px;min-height:44px;padding:0;border-radius:50%;font-size:0;position:relative}
.barre-ajout .bouton::before,.barre-ajout .bouton::after{content:"";position:absolute;top:50%;left:50%;width:18px;height:2.6px;border-radius:2px;background:#fff;transform:translate(-50%,-50%)}
.barre-ajout .bouton::after{transform:translate(-50%,-50%) rotate(90deg)}
main{position:relative}

/* clients : une seule carte, une ligne par client (comme les contacts) */
table.clients tbody{background:#fff;border:1px solid var(--trait-leger);border-radius:18px;box-shadow:var(--ombre-carte);overflow:hidden}
table.clients tr{display:grid;grid-template-columns:1fr auto;gap:2px 10px;margin:0;padding:11px 16px;border:0;border-top:1px solid var(--trait-leger);border-radius:0;box-shadow:none;background:none}
table.clients tr:first-child{border-top:0}
table.clients td{padding:0}
table.clients td.c-client{grid-column:1;grid-row:1;font-size:1.02rem;font-weight:700}table.clients td.c-client a{color:var(--vert-fonce)}
table.clients td.c-tel{grid-column:2;grid-row:1;text-align:right!important;font-size:.9rem}table.clients td.c-tel a{color:var(--vert)}
table.clients td.c-adresse{grid-column:1/-1;grid-row:2;display:flex;flex-wrap:wrap;gap:0 8px;font-size:.88rem;color:var(--doux)}table.clients td.c-adresse a{color:var(--doux);font-weight:400}

/* archives : filtres repliés, idées en pastilles, une carte par résultat */
.filtres-det{margin:0 0 12px}
.filtres-det>summary{display:flex;align-items:center;justify-content:space-between;min-height:46px;padding:0 16px;border:1px solid var(--trait);border-radius:12px;background:#fff;box-shadow:var(--ombre-carte);color:var(--vert-fonce);font-weight:700;list-style:none;cursor:pointer;margin-bottom:10px}
.filtres-det>summary::-webkit-details-marker{display:none}
.filtres-det>summary::after{content:"";width:8px;height:8px;border:solid var(--vert-fonce);border-width:0 2.2px 2.2px 0;transform:rotate(45deg);margin-top:-4px}
.filtres-det[open]>summary::after{transform:rotate(-135deg);margin-top:4px}
.filtres-det[open]{background:#fff;border:1px solid var(--trait-leger);border-radius:18px;box-shadow:var(--ombre-carte);padding:6px 14px 14px}
.filtres-det[open]>summary{background:none;border:0;box-shadow:none;padding:0;margin-bottom:6px}
.barre-filtres{display:grid;grid-template-columns:1fr 1fr;gap:8px}.barre-filtres button{display:none}.barre-filtres .bouton{width:100%;font-size:14px;padding:8px 6px}
@supports selector(:has(a)){.filtres:has(.filtres-det[open]) .barre-filtres button{display:inline-flex;grid-column:1/-1}}
.idees{margin:0 0 12px}.idees .sep{display:none}
.idees-liens{display:flex;flex-wrap:nowrap;overflow-x:auto;gap:8px;margin:6px -16px 0;padding:2px 16px 6px;scrollbar-width:none}.idees-liens::-webkit-scrollbar{display:none}
.idees-liens a{flex:0 0 auto;max-width:74vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:9px 14px;border:1px solid var(--trait);border-radius:99px;background:#fff;box-shadow:var(--ombre-carte);color:var(--vert-fonce);font-size:.82rem;font-weight:600;text-decoration:none}
h2.groupe{font-size:1.1rem;margin:6px 2px 10px}
table.archive tr{display:grid;grid-template-columns:1fr auto;gap:3px 10px}
table.archive td{padding:0}
table.archive td.c-client{grid-column:1;grid-row:1;font-size:1.06rem;font-weight:700}table.archive td.c-client a{color:var(--vert-fonce)}table.archive td.c-client .doux{font-weight:400;font-size:.85rem}table.archive td.c-client .doux a{color:var(--vert)}
table.archive td.c-statut{grid-column:2;grid-row:1;text-align:right!important;font-size:.85rem;color:var(--doux)}
table.archive td.c-adresse{grid-column:1/-1;grid-row:2;display:flex;flex-wrap:wrap;gap:0 8px}table.archive td.c-adresse .doux{margin:0}
table.archive td.c-travaux{grid-column:1;grid-row:3}table.archive td.c-travaux a{font-weight:400;color:var(--texte)}
table.archive td.c-montant{grid-column:2;grid-row:3;text-align:right!important;font-size:1.06rem;font-weight:800;align-self:end}
table.archive td.c-date{grid-column:1;grid-row:4;align-self:center;font-size:13px;color:var(--doux)}
table.archive td.col-actions{grid-column:2;grid-row:4;margin-top:4px}table.archive td.col-actions .bouton{min-height:36px;padding:4px 16px;font-size:13px}

/* gestion des raccourcis */
table.gerer tr{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:8px 12px;margin:0 0 8px;padding:10px 12px;border:1px solid var(--trait-leger);border-radius:14px;box-shadow:none;background:var(--fond)}
table.gerer td{padding:0}
table.gerer .col-ordre .fleches{display:flex;gap:4px;margin:0}table.gerer .col-ordre button.fleche{min-height:36px;width:36px;padding:0}
table.gerer td:nth-child(3){text-align:right!important}table.gerer td:nth-child(3) button{min-height:36px;padding:4px 14px;font-size:13px}
table.gerer td:nth-child(2) b{font-size:1rem}table.gerer td:nth-child(2) .doux{font-size:.8rem}

/* fenêtre « Terminer » : feuille qui monte du bas */
.modale{align-items:flex-end;padding:0;z-index:1100}
.modale-carte{max-width:none;width:100%;border-radius:22px 22px 0 0;padding:22px 18px calc(18px + env(safe-area-inset-bottom));max-height:92vh;overflow:auto}
.modale .question{font-size:1.05rem;margin:8px 0 12px}
.modale .barre{display:grid;grid-template-columns:1fr 1fr;gap:8px}.modale .barre button{grid-column:1/-1}.modale .barre .bouton{width:100%}
}
"""
