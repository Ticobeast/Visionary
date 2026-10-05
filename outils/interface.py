#!/usr/bin/env python3
"""Interface de saisie locale de SylvainCulteur (s'ouvre dans le navigateur).

    python3 outils/interface.py                 # base réelle : data/sylvainculteur.db
    python3 outils/interface.py --db data/test.db

Aucune installation : bibliothèque standard seulement. Le serveur n'écoute que sur
cet ordinateur (127.0.0.1) : rien n'est accessible depuis le réseau ni depuis Internet.
Utilise les mêmes règles de validation que l'import CSV (noyau.py).
Arrêter : Ctrl+C dans la fenêtre du terminal.
"""
import argparse
import datetime
import html
import re
import sqlite3
import sys
import threading
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import noyau  # noqa: E402
from noyau import (COLONNES, DB_DEFAUT, MODES, STATUTS, Index, Ligne, Resultat, alias_types_travaux,  # noqa: E402
                   cle, creer_chantier, lire_ligne, mettre_a_jour_client, mettre_a_jour_fiche, ouvrir_base,
                   sauvegarder, trouver_ou_creer_client)

LIBELLES_STATUT = {"soumission": "Soumission", "refuse": "Refusé", "accepte": "Accepté",
                   "planifie": "Planifié", "termine": "Terminé", "annule": "Annulé"}
LIBELLES_PAIEMENT = {"non_facture": "À facturer", "a_payer": "Facturé, à recevoir", "partiel": "Partiel",
                     "paye": "Payé", "a_venir": "À venir", "sans_objet": "—", "prix_manquant": "Prix manquant"}
LIBELLES_MODE = {"comptant": "Comptant", "cheque": "Chèque", "interac": "Interac", "carte": "Carte", "autre": "Autre"}
MESSAGES = {
    "cree": "Chantier créé.",
    "cree_reutilise": "Chantier créé pour un client déjà dans la base (même adresse) : sa fiche a été réutilisée.",
    "maj": "Modifications enregistrées.",
    "paiement": "Paiement ajouté.",
    "paiement_supprime": "Paiement supprimé.",
    "supprime": "Chantier supprimé.",
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
details summary{cursor:pointer;color:var(--accent-fonce);font-weight:600;margin-bottom:10px}
@media (max-width:700px){th:nth-child(n+5),td:nth-child(n+5){display:none}}
"""


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def argent(x):
    return "" if x is None else f"{x:,.2f} $".replace(",", " ").replace(".", ",")


def gabarit(titre, contenu, message=None):
    msg = f'<div class="message">{esc(MESSAGES[message])}</div>' if message in MESSAGES else ""
    return f"""<!doctype html><html lang="fr-CA"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(titre)} — SylvainCulteur</title>
<style>{CSS}</style></head><body>
<header><strong>SylvainCulteur</strong><a href="/">Chantiers</a><a href="/nouveau">+ Nouveau chantier</a></header>
<main>{msg}{contenu}</main></body></html>"""


def badge(code, libelle):
    return f'<span class="badge b-{esc(code)}">{esc(libelle)}</span>'


# ---------------------------------------------------------------------------
# Formulaire
# ---------------------------------------------------------------------------
def champ(nom, libelle, valeurs, type_="text", large=False, **attrs):
    extra = "".join(f' {k.replace("_", "-")}="{esc(v)}"' if v is not True else f' {k}' for k, v in attrs.items())
    classe = ' class="large"' if large else ""
    return (f'<div{classe}><label for="{nom}">{esc(libelle)}</label>'
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
    return f'<div><label for="{nom}">{esc(libelle)}</label><select id="{nom}" name="{nom}"{extra}>{choix}</select></div>'


def formulaire(conn, valeurs, action, erreurs=(), client_id=None, nouveau=True, bouton="Enregistrer"):
    types = list(conn.execute("SELECT code, libelle FROM types_travaux ORDER BY libelle"))
    erreurs_html = ""
    if erreurs:
        erreurs_html = ('<div class="erreurs"><strong>À corriger avant d\'enregistrer :</strong><ul>'
                        + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>")
    sms = " checked" if valeurs.get("client_sms_ok", "1") != "0" else ""
    taxes = " checked" if valeurs.get("taxes_auto") else ""
    paiement = ""
    if nouveau:
        paiement = f"""<div class="carte"><h2>Paiement déjà reçu <span class="doux">(facultatif)</span></h2><div class="grille">
{champ("paiement_date", "Date du paiement", valeurs, "date")}{champ("paiement_montant", "Montant reçu (taxes incluses)", valeurs, inputmode="decimal", placeholder="551,88")}
{liste("paiement_mode", "Mode", [(m, LIBELLES_MODE[m]) for m in MODES], valeurs, vide="—")}</div>
<p class="doux">Pour plusieurs versements (acompte + solde), enregistre ici le premier, puis ajoute les autres sur la page du chantier.</p></div>"""
    cid = f'<input type="hidden" name="client_id" value="{esc(client_id)}">' if client_id else ""
    return f"""{erreurs_html}<form method="post" action="{esc(action)}">{cid}
<div class="carte"><h2>Client</h2><div class="grille">
{champ("client_nom", "Nom", valeurs, autocomplete="off")}{champ("client_prenom", "Prénom", valeurs, autocomplete="off")}
{champ("client_entreprise", "Entreprise / syndicat", valeurs)}{champ("client_telephone", "Téléphone", valeurs, "tel", placeholder="450-555-0142")}
{champ("client_telephone_2", "Téléphone 2", valeurs, "tel")}{champ("client_courriel", "Courriel", valeurs, "email")}
<div><label>&nbsp;</label><label style="color:inherit"><input type="checkbox" name="client_sms_ok" value="1"{sms}>Rappels par texto acceptés</label></div>
{zone("client_notes", "Notes sur le client (préférences, historique)", valeurs)}</div></div>

<div class="carte"><h2>Adresse des travaux</h2><div class="grille">
{champ("adresse", "Adresse (numéro + rue)", valeurs, large=True, required=True, placeholder="123 Rue des Érables")}
{champ("ville", "Ville", valeurs, required=True)}{champ("code_postal", "Code postal", valeurs, placeholder="J7Z 1A1")}
{champ("province", "Province", valeurs, placeholder="QC")}
{zone("notes_acces", "Accès : barrière, chien, où stationner, où est l'arbre", valeurs)}</div>
<details style="margin-top:12px"><summary>Coordonnées GPS (seulement pour un lot sans numéro civique)</summary><div class="grille">
{champ("latitude", "Latitude", valeurs, inputmode="decimal", placeholder="45.6480")}
{champ("longitude", "Longitude (négative au Québec)", valeurs, inputmode="decimal", placeholder="-74.0920")}</div>
<p class="doux">Google Maps : clic droit sur l'endroit → cliquer sur les coordonnées pour les copier. Laisser vide sinon : le géocodage se fera plus tard.</p></details></div>

<div class="carte"><h2>Travaux</h2><div class="grille">
{liste("type_travaux", "Type de travaux", types, valeurs, vide="Choisir…", required=True)}
{liste("statut", "Statut", [(s, LIBELLES_STATUT[s]) for s in STATUTS], valeurs, required=True)}
{zone("description", "Description (imprimée sur la feuille de route)", valeurs)}
{champ("date_soumission", "Date de la soumission", valeurs, "date")}{champ("date_prevue", "Date prévue", valeurs, "date")}
{champ("heure_prevue", "Heure prévue (rendez-vous fixe)", valeurs, "time")}{champ("date_realisee", "Date réalisée", valeurs, "date")}
{champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal", placeholder="2,5")}
{champ("duree_reelle_h", "Durée réelle (heures)", valeurs, inputmode="decimal")}</div>
<p class="doux">Durée = temps passé sur place, en heures décimales (2,5 = 2 h 30). Statut « Planifié » : date prévue obligatoire. « Terminé » : date réalisée obligatoire.</p></div>

<div class="carte"><h2>Prix et facture</h2><div class="grille">
{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal", placeholder="480,00")}
{champ("tps", "TPS ($)", valeurs, inputmode="decimal")}{champ("tvq", "TVQ ($)", valeurs, inputmode="decimal")}
<div><label>&nbsp;</label><label style="color:inherit"><input type="checkbox" name="taxes_auto" value="1"{taxes}>Calculer TPS 5 % et TVQ 9,975 % si vides</label></div>
{champ("numero_facture", "N° de facture", valeurs)}{champ("date_facture", "Date de la facture / du reçu", valeurs, "date")}</div></div>
{paiement}
<div class="carte"><h2>Notes et fichiers</h2><div class="grille">
{zone("notes", "Notes sur ce chantier", valeurs)}
{champ("ref_papier", "Où est la fiche papier ?", valeurs, placeholder="Classeur A, fiche 12")}
{champ("fichier_papier", "Scan de la fiche (chemin dans data/)", valeurs, placeholder="papier/2026/gagnon.pdf")}
{champ("dossier_photos", "Dossier de photos (chemin dans data/)", valeurs, placeholder="photos/2026/2026-06-14_gagnon")}</div></div>
<div class="barre"><button type="submit">{esc(bouton)}</button><a class="bouton secondaire" href="/">Annuler</a></div></form>"""


def valeurs_vides():
    return {"client_sms_ok": "1", "province": "QC", "statut": "soumission"}


def _txt(x, fmt=None):
    return "" if x is None else (fmt(x) if fmt else str(x))


def valeurs_client(conn, client_id):
    r = conn.execute("SELECT prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, adresse, ville,"
                     " province, code_postal, latitude, longitude, notes_acces, notes FROM clients WHERE id = ?",
                     (client_id,)).fetchone()
    cols = ["client_prenom", "client_nom", "client_entreprise", "client_telephone", "client_telephone_2",
            "client_courriel", "client_sms_ok", "adresse", "ville", "province", "code_postal", "latitude",
            "longitude", "notes_acces", "client_notes"]
    return {c: _txt(x, repr if c in ("latitude", "longitude") else None) for c, x in zip(cols, r)}


def valeurs_chantier(conn, chantier_id):
    r = conn.execute("SELECT client_id, type_travaux, description, notes, statut, date_soumission, date_prevue,"
                     " heure_prevue, date_realisee, duree_estimee_h, duree_reelle_h, prix_ht, tps, tvq,"
                     " numero_facture, date_facture, dossier_photos, fichier_papier, ref_papier"
                     " FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return None
    cols = ["client_id", "type_travaux", "description", "notes", "statut", "date_soumission", "date_prevue",
            "heure_prevue", "date_realisee", "duree_estimee_h", "duree_reelle_h", "prix_ht", "tps", "tvq",
            "numero_facture", "date_facture", "dossier_photos", "fichier_papier", "ref_papier"]
    fmt = {"duree_estimee_h": lambda x: f"{x:g}", "duree_reelle_h": lambda x: f"{x:g}",
           "prix_ht": lambda x: f"{x:.2f}", "tps": lambda x: f"{x:.2f}" if x else "", "tvq": lambda x: f"{x:.2f}" if x else ""}
    d = {c: _txt(x, fmt.get(c)) for c, x in zip(cols, r)}
    client_id = r[0]
    d.update(valeurs_client(conn, client_id))
    return d, client_id


@contextmanager
def transaction(conn):
    conn.execute("BEGIN")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def lire_formulaire(conn, form):
    brut = {c: form.get(c, "") for c in COLONNES}
    brut["client_sms_ok"] = "1" if form.get("client_sms_ok") else "0"
    brut["taxes_auto"] = "1" if form.get("taxes_auto") else ""
    v, erreurs = lire_ligne(brut, alias_types_travaux(conn), taxes_auto=bool(form.get("taxes_auto")))
    return brut, v, erreurs


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_liste(conn, query):
    q = query.get("q", "").strip()
    statut = query.get("statut", "")
    paiement = query.get("paiement", "")
    sql = ("SELECT chantier_id, client_nom_complet, entreprise, adresse, ville, telephone, type_libelle, description,"
           " statut, statut_paiement, solde, date_prevue, date_realisee, date_soumission FROM v_chantiers WHERE 1=1")
    params = []
    if statut in STATUTS:
        sql += " AND statut = ?"
        params.append(statut)
    if paiement == "a_recevoir":
        sql += " AND statut_paiement IN ('a_payer', 'partiel')"
    elif paiement in LIBELLES_PAIEMENT:
        sql += " AND statut_paiement = ?"
        params.append(paiement)
    ordre = "ASC" if statut == "planifie" else "DESC"
    sql += f" ORDER BY COALESCE(date_prevue, date_realisee, date_soumission, '') {ordre}, chantier_id DESC"
    lignes = conn.execute(sql, params).fetchall()
    if q:
        mots = cle(q).split()
        lignes = [r for r in lignes if all(m in cle(" ".join(str(x) for x in r[1:8] if x)) for m in mots)]
    total = len(lignes)
    lignes = lignes[:300]

    def puce(href, nombre, texte):
        return f'<a class="puce" href="{href}"><b>{nombre}</b><span>{esc(texte)}</span></a>'
    nf = conn.execute("SELECT count(*), COALESCE(SUM(solde), 0) FROM v_chantiers WHERE statut_paiement = 'non_facture'").fetchone()
    ar = conn.execute("SELECT count(*), COALESCE(SUM(solde), 0) FROM v_chantiers WHERE statut_paiement IN ('a_payer','partiel')").fetchone()
    pl = conn.execute("SELECT count(*) FROM v_chantiers WHERE statut = 'planifie'").fetchone()[0]
    mq = conn.execute("SELECT count(*) FROM v_chantiers WHERE statut_paiement = 'prix_manquant'").fetchone()[0]
    puces = (puce("/?paiement=non_facture", nf[0], f"à facturer · {argent(nf[1])}")
             + puce("/?paiement=a_recevoir", ar[0], f"à recevoir · {argent(ar[1])}")
             + puce("/?statut=planifie", pl, "planifiés")
             + (puce("/?paiement=prix_manquant", mq, "prix manquants") if mq else ""))

    opt_statut = '<option value="">Tous les statuts</option>' + "".join(
        f'<option value="{s}"{" selected" if s == statut else ""}>{LIBELLES_STATUT[s]}</option>' for s in STATUTS)
    paiements = [("a_recevoir", "À recevoir (facturé ou partiel)")] + [(k, v) for k, v in LIBELLES_PAIEMENT.items() if k != "sans_objet"]
    opt_paiement = '<option value="">Tous les paiements</option>' + "".join(
        f'<option value="{k}"{" selected" if k == paiement else ""}>{esc(v)}</option>' for k, v in paiements)
    recherche = (f'<form class="recherche" method="get" action="/"><input type="search" name="q" value="{esc(q)}" '
                 f'placeholder="Chercher : nom, téléphone, adresse, ville…"><select name="statut">{opt_statut}</select>'
                 f'<select name="paiement">{opt_paiement}</select><button type="submit">Chercher</button></form>')

    if lignes:
        corps = ""
        for (cid, nom, entreprise, adresse, ville, tel, type_, desc, st, stp, solde, dp, dr, ds) in lignes:
            date_ = dp or dr or ds or ""
            nom_aff = nom if not entreprise or entreprise == nom else f"{nom} · {entreprise}"
            solde_aff = argent(solde) if stp in ("non_facture", "a_payer", "partiel") else ""
            corps += (f'<tr><td>{esc(date_)}</td><td><a href="/chantier/{cid}">{esc(nom_aff)}</a></td>'
                      f'<td>{esc(adresse)}, {esc(ville)}</td><td>{esc(type_)}</td><td>{badge(st, LIBELLES_STATUT[st])}</td>'
                      f'<td>{badge(stp, LIBELLES_PAIEMENT[stp]) if stp != "sans_objet" else ""}</td><td class="droite">{esc(solde_aff)}</td></tr>')
        tableau = ('<table><thead><tr><th>Date</th><th>Client</th><th>Adresse</th><th>Travaux</th><th>Statut</th>'
                   f'<th>Paiement</th><th class="droite">Solde</th></tr></thead><tbody>{corps}</tbody></table>')
        if total > len(lignes):
            tableau += f'<p class="doux">{len(lignes)} premiers résultats sur {total} : précise la recherche.</p>'
    else:
        tableau = '<div class="carte">Aucun chantier ne correspond. <a href="/nouveau">Créer le premier ?</a></div>'
    return gabarit("Chantiers", f'<h1>Chantiers</h1><div class="puces">{puces}</div>{recherche}{tableau}', query.get("ok"))


def page_nouveau(conn, query):
    q = query.get("q", "").strip()
    client_id = query.get("client_id", "")
    valeurs, bandeau = valeurs_vides(), ""
    if client_id.isdigit() and conn.execute("SELECT 1 FROM clients WHERE id = ?", (client_id,)).fetchone():
        valeurs = {**valeurs, **valeurs_client(conn, client_id)}
        valeurs["statut"] = "soumission"
        bandeau = (f'<div class="message">Nouveau chantier pour <b>{esc(valeurs.get("client_prenom"))} {esc(valeurs.get("client_nom"))} '
                   f'{esc(valeurs.get("client_entreprise"))}</b>, {esc(valeurs.get("adresse"))}. Les informations du client sont celles de sa fiche.'
                   f' <a href="/nouveau">Plutôt un nouveau client</a></div>')
    else:
        client_id = ""
    trouves = ""
    if q and not client_id:
        mots = cle(q).split()
        lignes = [r for r in conn.execute("SELECT id, prenom, nom, entreprise, adresse, ville, telephone FROM clients ORDER BY nom")
                  if all(m in cle(" ".join(str(x) for x in r[1:] if x)) for m in mots)][:10]
        liens = "".join(f'<li><a href="/nouveau?client_id={r[0]}">{esc(" ".join(x for x in r[1:4] if x))} — {esc(r[4])}, {esc(r[5])}'
                        f' {esc(r[6] or "")}</a></li>' for r in lignes) or "<li>Aucun client trouvé : remplis le formulaire ci-dessous.</li>"
        trouves = f'<div class="carte"><h2>Clients trouvés</h2><ul>{liens}</ul></div>'
    recherche = ""
    if not client_id:
        recherche = (f'<form class="recherche" method="get" action="/nouveau"><input type="search" name="q" value="{esc(q)}" '
                     'placeholder="Le client existe déjà ? Chercher par nom, téléphone ou adresse…"><button class="secondaire" type="submit">Chercher</button></form>')
    contenu = f'<h1>Nouveau chantier</h1>{bandeau}{recherche}{trouves}{formulaire(conn, valeurs, "/nouveau", client_id=client_id or None)}'
    return gabarit("Nouveau chantier", contenu)


def creer(conn, form):
    brut, v, erreurs = lire_formulaire(conn, form)
    client_id = form.get("client_id", "")
    client_id = int(client_id) if client_id.isdigit() else None
    if not erreurs:
        res, avertissements = Resultat(), []
        try:
            with transaction(conn):
                if client_id:
                    mettre_a_jour_client(conn, client_id, v)
                else:
                    client_id = trouver_ou_creer_client(conn, Index(conn), v, res, avertissements.append)
                chantier_id = creer_chantier(conn, client_id, v, res, avertissements.append, verifier_doublon=False)
            ok = "cree_reutilise" if res.clients_reutilises else "cree"
            return redirection(f"/chantier/{chantier_id}?ok={ok}")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    contenu = f'<h1>Nouveau chantier</h1>{formulaire(conn, brut, "/nouveau", erreurs, client_id=client_id)}'
    return gabarit("Nouveau chantier", contenu)


def page_chantier(conn, chantier_id, query, valeurs=None, erreurs=(), erreur_paiement=()):
    trouve = valeurs_chantier(conn, chantier_id)
    if trouve is None:
        return gabarit("Introuvable", '<h1>Chantier introuvable</h1><p><a href="/">Retour à la liste</a></p>'), 404
    depuis_base, client_id = trouve
    fiche = conn.execute("SELECT statut, statut_paiement, total_ttc, paye, solde, prix_ht, tps, tvq, client_nom_complet, adresse_maps"
                         " FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    statut, stp, total, paye, solde, prix, tps, tvq, nom, adresse_maps = fiche
    maps = f"https://www.google.com/maps/search/?api=1&query={quote(adresse_maps)}"
    resume = (f'<div class="carte"><div class="barre"><h2 style="margin:0">{esc(nom)}</h2>{badge(statut, LIBELLES_STATUT[statut])}'
              f'{badge(stp, LIBELLES_PAIEMENT[stp]) if stp != "sans_objet" else ""}'
              f'<span class="doux">{esc(adresse_maps)}</span> <a href="{esc(maps)}" target="_blank" rel="noopener">Voir sur Google Maps</a></div>'
              f'<p class="doux" style="margin-bottom:0">Prix {argent(prix)} · TPS {argent(tps)} · TVQ {argent(tvq)} · '
              f'<b>Total {argent(total)}</b> · Reçu {argent(paye)} · <b>Solde {argent(solde)}</b></p></div>')
    pmts = conn.execute("SELECT id, date_paiement, mode, montant, reference FROM paiements WHERE chantier_id = ? ORDER BY date_paiement, id", (chantier_id,)).fetchall()
    lignes = "".join(
        f'<tr><td>{esc(d)}</td><td>{esc(LIBELLES_MODE[m])}</td><td>{esc(ref)}</td><td class="droite">{argent(mt)}</td>'
        f'<td class="droite"><form method="post" action="/paiement/{pid}/supprimer" onsubmit="return confirm(\'Supprimer ce paiement ?\')">'
        f'<button class="danger" type="submit">Supprimer</button></form></td></tr>' for pid, d, m, mt, ref in pmts)
    table_p = (f'<table><thead><tr><th>Date</th><th>Mode</th><th>Référence</th><th class="droite">Montant</th><th></th></tr></thead><tbody>{lignes}</tbody></table>'
               if pmts else '<p class="doux">Aucun paiement enregistré.</p>')
    ev = {"paiement_date": datetime.date.today().isoformat(), **(erreur_paiement[1] if erreur_paiement else {})}
    err_p = ('<div class="erreurs"><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreur_paiement[0]) + "</ul></div>") if erreur_paiement else ""
    ajout = f"""{err_p}<form method="post" action="/chantier/{chantier_id}/paiement"><div class="grille">
{champ("paiement_date", "Date", ev, "date", required=True)}{champ("paiement_montant", "Montant ($)", ev, inputmode="decimal", required=True, placeholder="500,00")}
{liste("paiement_mode", "Mode", [(m, LIBELLES_MODE[m]) for m in MODES], ev, required=True)}{champ("paiement_reference", "Référence (n° de chèque…)", ev)}
<div><label>&nbsp;</label><button type="submit">Ajouter le paiement</button></div></div></form>"""
    autres = conn.execute("SELECT chantier_id, type_libelle, COALESCE(date_prevue, date_realisee, date_soumission, ''), statut"
                          " FROM v_chantiers WHERE client_id = ? AND chantier_id <> ? ORDER BY 3 DESC", (client_id, chantier_id)).fetchall()
    autres_html = ""
    if autres:
        autres_html = ('<div class="carte"><h2>Autres chantiers de ce client</h2><ul>' + "".join(
            f'<li><a href="/chantier/{i}">{esc(d)} — {esc(t)}</a> {badge(s, LIBELLES_STATUT[s])}</li>' for i, t, d, s in autres) + "</ul></div>")
    form_html = formulaire(conn, valeurs if valeurs is not None else depuis_base, f"/chantier/{chantier_id}", erreurs,
                           client_id=client_id, nouveau=False, bouton="Enregistrer les modifications")
    actions = (f'<div class="barre" style="margin-bottom:16px"><a class="bouton secondaire" href="/nouveau?client_id={client_id}">+ Nouveau chantier pour ce client</a></div>')
    supprimer = (f'<form method="post" action="/chantier/{chantier_id}/supprimer" onsubmit="return confirm(\'Supprimer ce chantier ? '
                 f'Le client sera aussi supprimé s\\\'il n\\\'a aucun autre chantier. Cette action est définitive.\')">'
                 f'<button class="danger" type="submit">Supprimer ce chantier</button></form>')
    contenu = (f'<h1>Chantier #{chantier_id}</h1>{resume}{actions}<div class="carte"><h2>Paiements</h2>{table_p}'
               f'<h2 style="margin-top:16px">Ajouter un paiement</h2>{ajout}</div>{autres_html}{form_html}'
               f'<div class="carte"><h2>Zone de danger</h2>{supprimer}</div>')
    return gabarit(f"Chantier {chantier_id}", contenu, query.get("ok") if query else None)


def modifier(conn, chantier_id, form):
    brut, v, erreurs = lire_formulaire(conn, form)
    if not erreurs:
        try:
            with transaction(conn):
                mettre_a_jour_fiche(conn, chantier_id, v)
            return redirection(f"/chantier/{chantier_id}?ok=maj")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    return page_chantier(conn, chantier_id, {}, valeurs=brut, erreurs=erreurs)


def ajouter_paiement(conn, chantier_id, form):
    brut = {c: form.get(c, "") for c in ("paiement_date", "paiement_montant", "paiement_mode", "paiement_reference")}
    L = Ligne(brut)
    d, m, mode = L.jour("paiement_date"), L.montant("paiement_montant"), L.choix("paiement_mode", MODES)
    for nom, val in (("paiement_date", d), ("paiement_montant", m), ("paiement_mode", mode)):
        if val is None and not any(nom in e for e in L.erreurs):
            L.erreurs.append(f"{nom} est obligatoire")
    if m is not None and m == 0:
        L.erreurs.append("paiement_montant doit être supérieur à 0")
    if not L.erreurs:
        try:
            with transaction(conn):
                conn.execute("INSERT INTO paiements (chantier_id, date_paiement, montant, mode, reference) VALUES (?,?,?,?,?)",
                             (chantier_id, d, float(m), mode, L.texte("paiement_reference")))
            return redirection(f"/chantier/{chantier_id}?ok=paiement")
        except sqlite3.IntegrityError as e:
            L.erreurs.append(f"Refusé par la base : {e}")
    return page_chantier(conn, chantier_id, {}, erreur_paiement=(L.erreurs, brut))


def supprimer_paiement(conn, paiement_id):
    ligne = conn.execute("SELECT chantier_id FROM paiements WHERE id = ?", (paiement_id,)).fetchone()
    if ligne is None:
        return gabarit("Introuvable", "<h1>Paiement introuvable</h1>"), 404
    with transaction(conn):
        conn.execute("DELETE FROM paiements WHERE id = ?", (paiement_id,))
    return redirection(f"/chantier/{ligne[0]}?ok=paiement_supprime")


def supprimer_chantier(conn, chantier_id):
    ligne = conn.execute("SELECT client_id FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if ligne is None:
        return gabarit("Introuvable", "<h1>Chantier introuvable</h1>"), 404
    try:
        with transaction(conn):
            conn.execute("DELETE FROM chantiers WHERE id = ?", (chantier_id,))
            if not conn.execute("SELECT 1 FROM chantiers WHERE client_id = ?", (ligne[0],)).fetchone():
                conn.execute("DELETE FROM clients WHERE id = ?", (ligne[0],))
    except sqlite3.IntegrityError:
        return page_chantier(conn, chantier_id, {}, erreurs=["Impossible de supprimer : ce chantier a des paiements. Supprime-les d'abord."])
    return redirection("/?ok=supprime")


def redirection(url):
    return ("303 See Other", [("Location", url)], b"")


# ---------------------------------------------------------------------------
# Routage (indépendant du réseau : facile à tester)
# ---------------------------------------------------------------------------
ROUTES = [
    ("GET", r"^/$", lambda c, q, f, *g: page_liste(c, q)),
    ("GET", r"^/nouveau$", lambda c, q, f, *g: page_nouveau(c, q)),
    ("POST", r"^/nouveau$", lambda c, q, f, *g: creer(c, f)),
    ("GET", r"^/chantier/(\d+)$", lambda c, q, f, i: page_chantier(c, int(i), q)),
    ("POST", r"^/chantier/(\d+)$", lambda c, q, f, i: modifier(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/paiement$", lambda c, q, f, i: ajouter_paiement(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/supprimer$", lambda c, q, f, i: supprimer_chantier(c, int(i))),
    ("POST", r"^/paiement/(\d+)/supprimer$", lambda c, q, f, i: supprimer_paiement(c, int(i))),
]


def repondre(db_path, methode, chemin, query=None, form=None):
    """Retourne (statut HTTP, en-têtes, corps en bytes)."""
    query, form = query or {}, form or {}
    for m, motif, gestionnaire in ROUTES:
        correspondance = re.match(motif, chemin)
        if m == methode and correspondance:
            break
    else:
        return "404 Not Found", [("Content-Type", "text/html; charset=utf-8")], gabarit("Introuvable", "<h1>Page introuvable</h1>").encode()
    conn = None
    try:
        conn, _ = ouvrir_base(db_path)
        resultat = gestionnaire(conn, query, form, *correspondance.groups())
        if isinstance(resultat, str):
            page, code = resultat, 200
        elif len(resultat) == 3:  # redirection
            return resultat
        else:
            page, code = resultat
        statut = {200: "200 OK", 404: "404 Not Found"}[code]
        return statut, [("Content-Type", "text/html; charset=utf-8")], page.encode("utf-8")
    except sqlite3.OperationalError as e:
        page = gabarit("Base occupée", f"<h1>La base est occupée</h1><p>{esc(e)}</p><p>Ferme les autres programmes qui l'utilisent "
                                       "(DB Browser par exemple) puis recharge la page.</p>")
        return "503 Service Unavailable", [("Content-Type", "text/html; charset=utf-8")], page.encode("utf-8")
    except Exception as e:  # noqa: BLE001 : on affiche l'erreur plutôt que de planter le serveur
        page = gabarit("Erreur", f"<h1>Erreur inattendue</h1><p>{esc(type(e).__name__)} : {esc(e)}</p><p><a href=\"/\">Retour</a></p>")
        return "500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")], page.encode("utf-8")
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Serveur HTTP
# ---------------------------------------------------------------------------
class Gestionnaire(BaseHTTPRequestHandler):
    db_path = DB_DEFAUT
    hotes_autorises = ()

    def log_message(self, *args):  # silence : le terminal reste lisible
        pass

    def _traiter(self, methode):
        # Protection contre les sites web qui tenteraient d'écrire dans la base à ton insu
        # (requêtes « cross-site » et « DNS rebinding ») : l'hôte et l'origine doivent être locaux.
        origine = self.headers.get("Origin")
        if self.headers.get("Host") not in self.hotes_autorises or (origine and urlsplit(origine).netloc not in self.hotes_autorises):
            return self._envoyer("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")], "Accès refusé.".encode())
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        form = {}
        if methode == "POST":
            taille = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(taille).decode("utf-8", "replace"), keep_blank_values=True).items()}
        self._envoyer(*repondre(self.db_path, methode, url.path, query, form))

    def _envoyer(self, statut, en_tetes, corps):
        code, _, texte = statut.partition(" ")
        self.send_response(int(code), texte)
        for k, v in en_tetes:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        self._traiter("GET")

    def do_POST(self):
        self._traiter("POST")


def creer_serveur(db_path, port):
    classe = type("GestionnaireLie", (Gestionnaire,), {
        "db_path": Path(db_path), "hotes_autorises": (f"127.0.0.1:{port}", f"localhost:{port}")})
    return ThreadingHTTPServer(("127.0.0.1", port), classe)


def main(argv=None):
    p = argparse.ArgumentParser(description="Interface de saisie locale (navigateur).")
    p.add_argument("--db", default=str(DB_DEFAUT), help=f"fichier de base (défaut : {DB_DEFAUT})")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur automatiquement")
    a = p.parse_args(argv)
    db = Path(a.db)
    conn, existait = ouvrir_base(db)
    conn.close()
    if existait and not list((db.parent / "sauvegardes").glob(f"{datetime.date.today():%Y-%m-%d}_*")):
        print(f"Sauvegarde du jour : {sauvegarder(db, 'demarrage')}")
    try:
        serveur = creer_serveur(db, a.port)
    except OSError:
        sys.exit(f"Le port {a.port} est déjà utilisé (l'interface est peut-être déjà ouverte ?). Essaie : --port {a.port + 1}")
    url = f"http://localhost:{a.port}/"
    print(f"Base : {db}\nInterface : {url}\nArrêter : Ctrl+C")
    if not a.sans_navigateur:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêté.")
    finally:
        serveur.server_close()


if __name__ == "__main__":
    main()
