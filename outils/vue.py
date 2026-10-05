"""Éléments d'affichage partagés par toutes les pages : styles, gabarit, composants de formulaire."""
import html
from pathlib import Path
from urllib.parse import quote

from noyau import DB_DEFAUT, LIBELLES_MODE, LIBELLES_STATUT, MODES  # noqa: F401  (réexportés pour les pages)

LIBELLES_PAIEMENT = {"non_facture": "À facturer", "a_payer": "Facturé, à recevoir", "partiel": "Partiel",
                     "paye": "Payé", "a_venir": "À venir", "sans_objet": "—", "prix_manquant": "Prix manquant"}
MESSAGES = {
    "cree": "Chantier créé.",
    "cree_reutilise": "Chantier créé pour un client déjà dans la base (même adresse) : sa fiche a été réutilisée.",
    "maj": "Modifications enregistrées.",
    "paiement": "Paiement ajouté.",
    "paiement_supprime": "Paiement supprimé.",
    "supprime": "Chantier supprimé.",
    "statut_change": "Statut mis à jour.",
    "facture": "Chantier marqué comme facturé.",
    "encaisse": "Paiement enregistré.",
    "planifie_lot": "Chantiers planifiés pour la journée.",
    "retire": "Chantier retiré de la journée : il redevient « À planifier ».",
    "deplace": "Ordre de passage mis à jour : les heures sont recalculées.",
    "client_maj": "Fiche client enregistrée.",
    "client_cree": "Chantier créé pour ce client.",
    "duplique": "Nouvelle soumission créée d'après le chantier précédent : ajuste le prix si besoin.",
}

CSS = """
:root{--fond:#f5f6f4;--carte:#fff;--texte:#1d2a22;--doux:#5b6b61;--trait:#d9ded9;--accent:#2f6b3f;--accent-fonce:#245232;
--alerte:#9b2c2c;--alerte-fond:#fbeaea;--ok-fond:#e7f3ea}
@media (prefers-color-scheme:dark){:root{--fond:#161b18;--carte:#1f2622;--texte:#e8eee9;--doux:#a3b0a7;--trait:#34403a;
--accent:#6fbf86;--accent-fonce:#8fd3a3;--alerte:#f2a0a0;--alerte-fond:#3a2323;--ok-fond:#1f3326}}
*{box-sizing:border-box}body{margin:0;background:var(--fond);color:var(--texte);font:16px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{background:var(--carte);border-bottom:1px solid var(--trait);padding:12px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header strong{font-size:18px}header a{color:var(--accent-fonce);text-decoration:none;font-weight:600}
main a{color:var(--accent-fonce)}main{max-width:1100px;margin:0 auto;padding:16px}h1{font-size:22px;margin:8px 0 16px}h2{font-size:17px;margin:0 0 12px}
.carte{background:var(--carte);border:1px solid var(--trait);border-radius:10px;padding:16px;margin-bottom:16px}
.grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
label{display:block;font-size:14px;color:var(--doux);margin-bottom:2px}
input,select,textarea{width:100%;padding:9px 10px;border:1px solid var(--trait);border-radius:8px;background:var(--carte);color:var(--texte);font:inherit}
input[type=checkbox]{width:auto;margin-right:6px}textarea{min-height:70px}
.large{grid-column:1/-1}
button,.bouton{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 16px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
@media (prefers-color-scheme:dark){button,.bouton{color:#0d1a11}}
button.secondaire,.bouton.secondaire{background:transparent;color:var(--accent-fonce);border:1px solid var(--accent)}
button.danger{background:transparent;color:var(--alerte);border:1px solid var(--alerte)}
.puces{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
.puce{background:var(--carte);border:1px solid var(--trait);border-radius:10px;padding:10px 14px;text-decoration:none;color:var(--texte);min-width:150px}
.puce b{display:block;font-size:20px}.puce span{color:var(--doux);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--carte);border:1px solid var(--trait);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--trait);vertical-align:top;font-size:15px}
td:first-child,td.droite{white-space:nowrap}th{font-size:13px;color:var(--doux);font-weight:600}tr:last-child td{border-bottom:0}td a{color:var(--accent-fonce);font-weight:600;text-decoration:none}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:13px;border:1px solid var(--trait);white-space:nowrap}
.b-non_facture,.b-prix_manquant{background:#fff1d6;color:#7a4b00;border-color:#e8c675}.b-a_payer{background:var(--alerte-fond);color:var(--alerte);border-color:var(--alerte)}
.b-partiel{background:#e3eefb;color:#1e4d86;border-color:#9cbbe3}.b-paye,.b-termine{background:var(--ok-fond);color:var(--accent-fonce);border-color:var(--accent)}
.erreurs{background:var(--alerte-fond);border:1px solid var(--alerte);color:var(--alerte);border-radius:10px;padding:12px 16px;margin-bottom:16px}
.erreurs ul{margin:6px 0 0 18px;padding:0}.message{background:var(--ok-fond);border:1px solid var(--accent);border-radius:10px;padding:10px 16px;margin-bottom:16px}
.doux{color:var(--doux);font-size:14px}.droite{text-align:right}.barre{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.recherche{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}.recherche input{flex:1;min-width:180px}.recherche select{width:auto}
.type{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:10px;align-items:center;margin-bottom:8px}
.type label.coche{display:flex;align-items:center;margin:0;color:var(--texte);font-size:16px}
.base{margin-left:auto;font-size:13px;color:var(--doux)}.base.essai{background:#fff1d6;color:#7a4b00;border:1px solid #e8c675;border-radius:99px;padding:2px 10px;font-weight:600}
@media (max-width:600px){.type{grid-template-columns:1fr}}
main.large{max-width:1500px}.liste-defile{overflow-x:auto}table.tableau .mini{flex-wrap:nowrap}table.tableau td.col-statut{min-width:330px}table.tableau td.col-paiement{min-width:230px}table.tableau th,table.tableau td{font-size:14px;padding:8px}table.tableau td:first-child{white-space:normal}
.attente{display:inline-block;border-radius:6px;padding:2px 8px;font-weight:700;font-size:13px;white-space:nowrap;border:1px solid var(--trait)}
.a-normale{background:var(--ok-fond);color:var(--accent-fonce);border-color:var(--accent)}
.a-surveiller{background:#fff1d6;color:#7a4b00;border-color:#e8c675}
.a-urgente{background:var(--alerte-fond);color:var(--alerte);border-color:var(--alerte)}
tr.ligne-urgente td:first-child{box-shadow:inset 4px 0 0 var(--alerte)}tr.ligne-surveiller td:first-child{box-shadow:inset 4px 0 0 #e8c675}
h2.groupe{margin:20px 0 8px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}h2.groupe small{color:var(--doux);font-weight:400;font-size:14px}
.mini{display:flex;gap:4px;flex-wrap:wrap;align-items:center;margin:0 0 4px}.mini select,.mini input{width:auto;padding:5px 6px;font-size:13px;min-width:0}
.mini input[type=date]{width:128px}.mini input.court{width:64px}.mini button{padding:5px 10px;font-size:13px}
.onglets{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}.onglet{padding:7px 14px;border:1px solid var(--trait);border-radius:99px;text-decoration:none;color:var(--texte);background:var(--carte)}
.onglet.actif{background:var(--accent);color:#fff;border-color:var(--accent)}@media (prefers-color-scheme:dark){.onglet.actif{color:#0d1a11}}
.verrou{background:var(--fond);border:1px dashed var(--doux);border-radius:10px;padding:12px 16px;margin-bottom:16px}.verrou b{font-size:17px}
.verrou .doux::before{content:"\1F512  "}.total{font-weight:700}.sel-total{position:sticky;bottom:0;background:var(--carte);border:1px solid var(--accent);border-radius:10px;padding:10px 16px;margin-top:12px}
.cal-nav{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}.cal-nav h2{margin:0;flex:1;text-align:center;font-size:20px;min-width:140px}
.cal-grille{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px}
.cal-tete{font-size:13px;color:var(--doux);text-align:center;font-weight:600;padding:4px 0;text-transform:capitalize}
.cal-jour{min-height:84px;padding:6px 8px;border:1px solid var(--trait);border-radius:8px;text-decoration:none;color:var(--texte);display:flex;flex-direction:column;gap:2px;background:var(--carte)}
.cal-jour:hover{border-color:var(--accent-fonce)}.cal-jour.autre-mois{opacity:.45}.cal-jour.weekend{background:var(--fond)}
.cal-jour .cal-n{font-weight:700}.cal-jour.aujourdhui .cal-n{background:var(--accent);color:#fff;border-radius:99px;padding:0 7px;align-self:flex-start}
@media (prefers-color-scheme:dark){.cal-jour.aujourdhui .cal-n{color:#0d1a11}}
.cal-jour.occupe{border-color:var(--accent);background:var(--ok-fond)}.cal-jour.chargee{border-color:var(--alerte);background:var(--alerte-fond)}
.cal-jour.selection{outline:3px solid var(--accent-fonce);outline-offset:-1px}.cal-info{font-size:12px;line-height:1.3}.cal-alerte{font-size:11px;color:var(--alerte);font-weight:700}
.col-ordre{width:62px;white-space:nowrap}.col-ordre form{display:inline-block;margin:0 2px 0 0}
button.fleche{padding:2px 8px;font-size:13px;background:transparent;color:var(--accent-fonce);border:1px solid var(--accent)}button.fleche:disabled{opacity:.3;cursor:default}
.heures{font-size:16px;white-space:nowrap}tr.diner td{background:var(--fond);color:var(--doux);font-size:13px;text-align:center}
.modale{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:50;padding:16px}
.modale-carte{background:var(--carte);border-radius:14px;padding:24px;max-width:480px;width:100%;box-shadow:0 10px 40px rgba(0,0,0,.35)}
.modale .question{font-size:19px;font-weight:700;margin:12px 0 18px}
@media (max-width:700px){.cal-jour{min-height:58px;padding:4px}.cal-info{font-size:10px}}
.requis{color:var(--alerte);font-weight:700}
.verrou-termine{background:var(--ok-fond);border:1px solid var(--accent);border-radius:10px;padding:12px 16px;margin-bottom:16px}
dl.lecture{display:grid;grid-template-columns:minmax(150px,220px) 1fr;gap:6px 14px;margin:0}dl.lecture dt{color:var(--doux);font-size:14px}dl.lecture dd{margin:0}
@media (max-width:600px){dl.lecture{grid-template-columns:1fr}}
.lecture-seule{background:var(--fond);border:1px dashed var(--doux);border-radius:10px;padding:12px 16px;margin-bottom:16px}
details summary{cursor:pointer;color:var(--accent-fonce);font-weight:600;margin-bottom:10px}
details.avance{background:var(--carte);border:1px solid var(--trait);border-radius:12px;padding:12px 16px;margin-bottom:16px}
details.avance>summary{margin-bottom:0}details.avance[open]>summary{margin-bottom:14px}
details.avance .carte{box-shadow:none;border:1px solid var(--trait)}
.col-travaux{min-width:240px}
.resume-chantier{display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap;align-items:flex-start}.resume-chantier>div:first-child{flex:1 1 320px}.resume-chantier .montant{margin-left:auto}
.montant{font-size:18px;font-weight:700;text-align:right;white-space:nowrap}.montant small{display:block;font-size:12px;font-weight:400;color:var(--doux)}
.total-jour .total,.resume-jour .total{font-weight:700}
@media (max-width:700px){table.liste th:nth-child(n+5),table.liste td:nth-child(n+5){display:none}}
"""


_BASE = {"db": None}   # base ouverte par ce serveur (affichée dans l'en-tête pour ne jamais s'y tromper)


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def argent(x):
    return "" if x is None else f"{x:,.2f} $".replace(",", " ").replace(".", ",")


def etiquette_base():
    if not _BASE["db"]:
        return ""
    nom = Path(_BASE["db"]).name
    if nom == DB_DEFAUT.name:
        return f'<span class="base">Base : {esc(nom)}</span>'
    return f'<span class="base essai" title="{esc(_BASE["db"])}">BASE D’ESSAI : {esc(nom)}</span>'


def gabarit(titre, contenu, message=None, erreur=None, large=False):
    msg = f'<div class="message">{esc(MESSAGES[message])}</div>' if message in MESSAGES else ""
    if erreur:
        msg += f'<div class="erreurs"><strong>Action refusée :</strong> {esc(erreur)}</div>'
    return f"""<!doctype html><html lang="fr-CA"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(titre)} — SylvainCulteur</title>
<style>{CSS}</style></head><body>
<header><strong>SylvainCulteur</strong><a href="/">Tableau de bord</a><a href="/journee">Journée</a><a href="/chantiers">Chantiers</a><a href="/clients">Clients</a><a href="/nouveau">+ Nouveau</a>{etiquette_base()}</header>
<main{" class=large" if large else ""}>{msg}{contenu}</main></body></html>"""


def heures(h):
    """2.5 -> « 2 h 30 » ; 3.0 -> « 3 h » ; None -> « — »."""
    if h is None:
        return "—"
    minutes = round(h * 60)
    return f"{minutes // 60} h" + (f" {minutes % 60:02d}" if minutes % 60 else "")


def lien_maps(adresse_maps, texte):
    """Lien vers Google Maps (ouvre l'itinéraire / la carte de l'adresse)."""
    url = "https://www.google.com/maps/search/?api=1&query=" + quote(adresse_maps)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener" title="Ouvrir dans Google Maps">{esc(texte)}</a>'


def badge_attente(jours, priorite):
    libelle = {"normale": "normal", "surveiller": "à surveiller", "urgente": "URGENT"}[priorite]
    return f'<span class="attente a-{priorite}" title="{libelle}">{jours} j</span>'


def champ_modalite(valeurs):
    """Mode de règlement prévu : UN seul choix (comptant, chèque, Interac, carte, autre)."""
    return liste("modalite_paiement", "Mode de règlement", [(m, LIBELLES_MODE[m]) for m in MODES], valeurs, vide="Non précisé")


def redirection(url):
    return ("303 See Other", [("Location", url)], b"")


def badge(code, libelle):
    return f'<span class="badge b-{esc(code)}">{esc(libelle)}</span>'


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


def client_essentiel(valeurs):
    """Ce qu'il faut pour retrouver un client : nom, téléphone, adresse des travaux."""
    return f"""<div class="carte"><h2>Client</h2><div class="grille">
{champ("client_nom", "Nom", valeurs, autocomplete="off")}{champ("client_prenom", "Prénom", valeurs, autocomplete="off")}
{champ("client_telephone", "Téléphone", valeurs, "tel", placeholder="450-555-0142")}
{champ("adresse", "Adresse (numéro + rue)", valeurs, large=True, required=True, placeholder="123 Rue des Érables")}
{champ("ville", "Ville", valeurs, required=True)}</div></div>"""


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
<p class="doux">Google Maps : clic droit sur l'endroit → cliquer sur les coordonnées pour les copier. Laisser vide sinon : le géocodage se fera plus tard.</p></details></div>"""


def avance(contenu, ouvert=False):
    """Section repliée « Paramètres avancés » : les options rarement utilisées. Les champs repliés sont quand même envoyés."""
    return (f'<details class="avance"{" open" if ouvert else ""}><summary>Paramètres avancés</summary>{contenu}</details>')
