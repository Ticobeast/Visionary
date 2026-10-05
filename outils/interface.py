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
import re
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import noyau  # noqa: E402
from noyau import (COLONNES, _txt, DB_DEFAUT, MODES, STATUTS, Index, Ligne, Resultat, alias_types_travaux,  # noqa: E402
                   cle, creer_chantier, lire_ligne, mettre_a_jour_client, mettre_a_jour_fiche, ouvrir_base,
                   sauvegarder, service_nuage, transaction, travaux_depuis_formulaire, trouver_ou_creer_client,
                   valeurs_client)
from vue import (LIBELLES_MODE, LIBELLES_PAIEMENT, LIBELLES_STATUT, MESSAGES, _BASE, argent, badge,  # noqa: E402
                 bloc_types, carte_adresse, carte_client, champ, champ_modalite, esc, gabarit, liste, redirection, zone)

def formulaire(conn, valeurs, action, erreurs=(), client_id=None, nouveau=True, bouton="Enregistrer"):
    types = sorted(conn.execute("SELECT code, libelle FROM types_travaux"),
                   key=lambda t: (t[0] == "autre", cle(t[1])))     # alphabétique sans tenir compte des accents, « Autre » en dernier
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
{carte_client(valeurs)}

{carte_adresse(valeurs)}

<div class="carte"><h2>Travaux</h2><div class="grille">
{bloc_types(types, valeurs)}
{liste("statut", "Statut", [(s, LIBELLES_STATUT[s]) for s in STATUTS], valeurs, required=True)}
{zone("description", "Description (imprimée sur la feuille de route)", valeurs)}
{champ("date_soumission", "Date de la demande ou de la soumission", valeurs, "date")}{champ("date_prevue", "Date des travaux (prévue, puis réalisée)", valeurs, "date")}
{champ("heure_prevue", "Heure prévue (rendez-vous fixe)", valeurs, "time")}
{champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal", placeholder="2,5")}
{champ("duree_reelle_h", "Durée réelle (heures)", valeurs, inputmode="decimal")}</div>
<p class="doux">Durée = temps passé sur place, en heures décimales (2,5 = 2 h 30). Statuts « Planifié » et « Terminé » : la date des travaux est obligatoire. Si le chantier change de jour, modifie simplement cette date.</p></div>

<div class="carte"><h2>Prix et facture</h2><div class="grille">
{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal", placeholder="480,00")}
{champ("tps", "TPS ($)", valeurs, inputmode="decimal")}{champ("tvq", "TVQ ($)", valeurs, inputmode="decimal")}
<div><label>&nbsp;</label><label style="color:inherit"><input type="checkbox" name="taxes_auto" value="1"{taxes}>Calculer TPS 5 % et TVQ 9,975 % si vides</label></div>
{champ_modalite(valeurs)}{champ("numero_facture", "N° de facture", valeurs)}{champ("date_facture", "Date de la facture / du reçu", valeurs, "date")}</div></div>
{paiement}
<div class="carte"><h2>Notes et fichiers</h2><div class="grille">
{champ("ref_papier", "Où est la fiche papier ?", valeurs, placeholder="Classeur A, fiche 12")}
{champ("fichier_papier", "Scan de la fiche (chemin dans data/)", valeurs, placeholder="papier/2026/gagnon.pdf")}
{champ("dossier_photos", "Dossier de photos (chemin dans data/)", valeurs, placeholder="photos/2026/2026-06-14_gagnon")}</div></div>
<div class="barre"><button type="submit">{esc(bouton)}</button><a class="bouton secondaire" href="/">Annuler</a></div></form>"""


def valeurs_vides():
    return {"client_sms_ok": "1", "province": "QC", "statut": "soumission"}


def valeurs_chantier(conn, chantier_id):
    cols = ["client_id", "description", "statut", "date_soumission", "date_prevue", "heure_prevue",
            "duree_estimee_h", "duree_reelle_h", "prix_ht", "tps", "tvq", "modalite_paiement", "numero_facture", "date_facture",
            "dossier_photos", "fichier_papier", "ref_papier"]
    r = conn.execute(f"SELECT {', '.join(cols)} FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return None
    fmt = {"duree_estimee_h": lambda x: f"{x:g}", "duree_reelle_h": lambda x: f"{x:g}",
           "prix_ht": lambda x: f"{x:.2f}", "tps": lambda x: f"{x:.2f}" if x else "", "tvq": lambda x: f"{x:.2f}" if x else ""}
    d = {c: _txt(x, fmt.get(c)) for c, x in zip(cols, r)}
    for code, precision in conn.execute("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = ?", (chantier_id,)):
        d[f"type_{code}"] = "1"
        d[f"precision_{code}"] = precision or ""
    client_id = r[0]
    d.update(valeurs_client(conn, client_id))
    return d, client_id


def lire_formulaire(conn, form):
    brut = {c: form.get(c, "") for c in COLONNES}
    brut["client_sms_ok"] = "1" if form.get("client_sms_ok") else "0"
    brut["taxes_auto"] = "1" if form.get("taxes_auto") else ""
    travaux, valeurs_travaux = travaux_depuis_formulaire(conn, form)
    brut.update(valeurs_travaux)
    brut["type_travaux"] = travaux
    v, erreurs = lire_ligne(brut, alias_types_travaux(conn), taxes_auto=bool(form.get("taxes_auto")))
    return brut, v, erreurs


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page_chantiers(conn, query):
    q = query.get("q", "").strip()
    statut = query.get("statut", "")
    paiement = query.get("paiement", "")
    sql = ("SELECT chantier_id, client_nom_complet, entreprise, adresse, ville, telephone, travaux_detail, description,"
           " statut, statut_paiement, solde, date_prevue, date_soumission, type_libelle FROM v_chantiers WHERE 1=1")
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
    sql += f" ORDER BY COALESCE(date_prevue, date_soumission, '') {ordre}, chantier_id DESC"
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
    puces = (puce("/chantiers?paiement=non_facture", nf[0], f"à facturer · {argent(nf[1])}")
             + puce("/chantiers?paiement=a_recevoir", ar[0], f"à recevoir · {argent(ar[1])}")
             + puce("/chantiers?statut=planifie", pl, "planifiés")
             + (puce("/chantiers?paiement=prix_manquant", mq, "prix manquants") if mq else ""))

    opt_statut = '<option value="">Tous les statuts</option>' + "".join(
        f'<option value="{s}"{" selected" if s == statut else ""}>{LIBELLES_STATUT[s]}</option>' for s in STATUTS)
    paiements = [("a_recevoir", "À recevoir (facturé ou partiel)")] + [(k, v) for k, v in LIBELLES_PAIEMENT.items() if k != "sans_objet"]
    opt_paiement = '<option value="">Tous les paiements</option>' + "".join(
        f'<option value="{k}"{" selected" if k == paiement else ""}>{esc(v)}</option>' for k, v in paiements)
    recherche = (f'<form class="recherche" method="get" action="/chantiers"><input type="search" name="q" value="{esc(q)}" '
                 f'placeholder="Chercher : nom, téléphone, adresse, ville…"><select name="statut">{opt_statut}</select>'
                 f'<select name="paiement">{opt_paiement}</select><button type="submit">Chercher</button></form>')

    if lignes:
        corps = ""
        for (cid, nom, entreprise, adresse, ville, tel, detail, desc, st, stp, solde, dp, ds, type_) in lignes:
            date_ = dp or ds or ""
            nom_aff = nom if not entreprise or entreprise == nom else f"{nom} · {entreprise}"
            solde_aff = argent(solde) if stp in ("non_facture", "a_payer", "partiel") else ""
            corps += (f'<tr><td>{esc(date_)}</td><td><a href="/chantier/{cid}">{esc(nom_aff)}</a></td>'
                      f'<td>{esc(adresse)}, {esc(ville)}</td><td>{esc(type_)}</td><td>{badge(st, LIBELLES_STATUT[st])}</td>'
                      f'<td>{badge(stp, LIBELLES_PAIEMENT[stp]) if stp != "sans_objet" else ""}</td><td class="droite">{esc(solde_aff)}</td></tr>')
        tableau = ('<table class="liste"><thead><tr><th>Date</th><th>Client</th><th>Adresse</th><th>Travaux</th><th>Statut</th>'
                   f'<th>Paiement</th><th class="droite">Solde</th></tr></thead><tbody>{corps}</tbody></table>')
        if total > len(lignes):
            tableau += f'<p class="doux">{len(lignes)} premiers résultats sur {total} : précise la recherche.</p>'
    else:
        tableau = '<div class="carte">Aucun chantier ne correspond. <a href="/nouveau">Créer le premier ?</a></div>'
    return gabarit("Chantiers", f'<h1>Chantiers</h1><div class="puces">{puces}</div>{recherche}{tableau}', query.get("ok"))


def page_nouveau(conn, query):
    q = query.get("q", "").strip()
    client_id = query.get("client_id", "")
    if client_id.isdigit():          # ancien lien : un client existant passe par sa fiche
        return redirection(f"/client/{client_id}")
    trouves = ""
    if q:
        mots = cle(q).split()
        lignes = [r for r in conn.execute("SELECT id, prenom, nom, entreprise, adresse, ville, telephone FROM clients ORDER BY nom")
                  if all(m in cle(" ".join(str(x) for x in r[1:] if x)) for m in mots)][:10]
        liens = "".join(f'<li><a href="/client/{r[0]}">{esc(" ".join(x for x in r[1:4] if x))} — {esc(r[4])}, {esc(r[5])}'
                        f' {esc(r[6] or "")}</a></li>' for r in lignes) or "<li>Aucun client trouvé : remplis le formulaire ci-dessous.</li>"
        trouves = (f'<div class="carte"><h2>Clients trouvés</h2><ul>{liens}</ul>'
                   '<p class="doux">Ouvre la fiche du client pour lui ajouter un chantier (nom et adresse sont déjà connus).</p></div>')
    recherche = (f'<form class="recherche" method="get" action="/nouveau"><input type="search" name="q" value="{esc(q)}" '
                 'placeholder="Le client existe déjà ? Chercher par nom, téléphone ou adresse…"><button class="secondaire" type="submit">Chercher</button></form>')
    contenu = f'<h1>Nouveau client et chantier</h1>{recherche}{trouves}{formulaire(conn, valeurs_vides(), "/nouveau")}'
    return gabarit("Nouveau client et chantier", contenu)


def creer(conn, form):
    brut, v, erreurs = lire_formulaire(conn, form)
    if not erreurs:
        res, avertissements = Resultat(), []
        try:
            with transaction(conn):
                client_id = trouver_ou_creer_client(conn, Index(conn), v, res, avertissements.append)
                chantier_id = creer_chantier(conn, client_id, v, res, avertissements.append, verifier_doublon=False)
            ok = "cree_reutilise" if res.clients_reutilises else "cree"
            return redirection(f"/chantier/{chantier_id}?ok={ok}")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    contenu = f'<h1>Nouveau client et chantier</h1>{formulaire(conn, brut, "/nouveau", erreurs)}'
    return gabarit("Nouveau client et chantier", contenu)


def page_chantier(conn, chantier_id, query, valeurs=None, erreurs=(), erreur_paiement=()):
    trouve = valeurs_chantier(conn, chantier_id)
    if trouve is None:
        return gabarit("Introuvable", '<h1>Chantier introuvable</h1><p><a href="/">Retour à la liste</a></p>'), 404
    depuis_base, client_id = trouve
    fiche = conn.execute("SELECT statut, statut_paiement, total_ttc, paye, solde, prix_ht, tps, tvq, client_nom_complet, adresse_maps, travaux_detail"
                         " FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    statut, stp, total, paye, solde, prix, tps, tvq, nom, adresse_maps, detail = fiche
    maps = f"https://www.google.com/maps/search/?api=1&query={quote(adresse_maps)}"
    resume = (f'<div class="carte"><div class="barre"><h2 style="margin:0">{esc(nom)}</h2>{badge(statut, LIBELLES_STATUT[statut])}'
              f'{badge(stp, LIBELLES_PAIEMENT[stp]) if stp != "sans_objet" else ""}'
              f'<span class="doux">{esc(adresse_maps)}</span> <a href="{esc(maps)}" target="_blank" rel="noopener">Voir sur Google Maps</a></div>'
              f'<p style="margin:10px 0 0"><b>Travaux :</b> {esc(detail)}</p>'
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
    autres = conn.execute("SELECT chantier_id, type_libelle, COALESCE(date_prevue, date_soumission, ''), statut"
                          " FROM v_chantiers WHERE client_id = ? AND chantier_id <> ? ORDER BY 3 DESC", (client_id, chantier_id)).fetchall()
    autres_html = ""
    if autres:
        autres_html = ('<div class="carte"><h2>Autres chantiers de ce client</h2><ul>' + "".join(
            f'<li><a href="/chantier/{i}">{esc(d)} — {esc(t)}</a> {badge(s, LIBELLES_STATUT[s])}</li>' for i, t, d, s in autres) + "</ul></div>")
    form_html = formulaire(conn, valeurs if valeurs is not None else depuis_base, f"/chantier/{chantier_id}", erreurs,
                           client_id=client_id, nouveau=False, bouton="Enregistrer les modifications")
    actions = (f'<div class="barre" style="margin-bottom:16px"><a class="bouton secondaire" href="/client/{client_id}">Fiche client</a><a class="bouton secondaire" href="/client/{client_id}/chantier/nouveau">+ Nouveau chantier pour ce client</a></div>')
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
    return redirection("/chantiers?ok=supprime")


# ---------------------------------------------------------------------------
# Routage (indépendant du réseau : facile à tester)
# ---------------------------------------------------------------------------
from pages_clients import ROUTES_CLIENTS  # noqa: E402
from tableau import ROUTES_TABLEAU  # noqa: E402

ROUTES = ROUTES_TABLEAU + ROUTES_CLIENTS + [
    ("GET", r"^/chantiers$", lambda c, q, f, *g: page_chantiers(c, q)),
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
    _BASE["db"] = str(db_path)
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
    p.add_argument("--essai", action="store_true", help="ouvre la base d'essai (data/test.db) au lieu de la vraie base")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur automatiquement")
    a = p.parse_args(argv)
    db = DB_DEFAUT.parent / "test.db" if a.essai else Path(a.db)
    if a.essai and not (db.exists() and db.stat().st_size > 0):
        import donnees_test
        res = donnees_test.generer(db)
        print(f"Base d'essai créée avec de fausses données : {res.chantiers} chantiers.")
    conn, existait = ouvrir_base(db)
    conn.close()
    if existait and not list((db.parent / "sauvegardes").glob(f"{datetime.date.today():%Y-%m-%d}_*")):
        print(f"Sauvegarde du jour : {sauvegarder(db, 'demarrage')}")
    try:
        serveur = creer_serveur(db, a.port)
    except OSError:
        sys.exit(f"Le port {a.port} est déjà utilisé (l'interface est peut-être déjà ouverte ?). Essaie : --port {a.port + 1}")
    url = f"http://localhost:{a.port}/"
    mode = "BASE D'ESSAI (fausses données)" if db.name != DB_DEFAUT.name else "BASE RÉELLE"
    print(f"{mode} : {db}\nInterface : {url}\nArrêter : Ctrl+C")
    if db.name == DB_DEFAUT.name:
        print("Pour t'entraîner sur de fausses données, lance plutôt :  python outils/interface.py --essai")
    nuage = service_nuage(db)
    if nuage:
        print(f"\nATTENTION : ce dossier semble synchronisé par {nuage}. Les données de tes clients seraient copiées sur\n"
              "des serveurs externes (contraire à l'objectif « 100 % local »), et SQLite peut avoir des problèmes dans un\n"
              "dossier synchronisé. Déplace tout le dossier du projet hors de ce service (ex. C:\\SylvainCulteur).\n")
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
