"""Tableau de bord opérationnel et organisation des tournées journalières.

Tableau de bord (/) : ce qu'il y a à planifier (classé par délai d'attente), les soumissions en attente de
réponse, les chantiers planifiés (par jour, avec durée totale), ce qui reste à facturer et à encaisser.
Chaque ligne a ses actions rapides (statut, facturation, encaissement) : pas besoin d'ouvrir la fiche.

Tournées (/tournee) : on choisit une journée, on filtre les chantiers à placer (secteur, délai d'attente,
statut), on en coche plusieurs et on les ajoute à la journée en un clic, avec le total d'heures.
"""
import datetime
import sqlite3
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from noyau import (MODES, STATUTS, SEUIL_SURVEILLER, SEUIL_URGENT, changer_statut, cle, encaisser, facturer,
                   jours_attente, planifier_lot, priorite, transaction)
from vue import (LIBELLES_MODE, LIBELLES_PAIEMENT, LIBELLES_STATUT, argent, badge, badge_attente, esc, gabarit,
                 heures, lien_maps, redirection)

JOURNEE_H = 8.0   # repère d'une journée de travail (heures), pour voir ce qu'il reste de place

VUES = [
    ("aplanifier", "À planifier"),
    ("soumissions", "Soumissions"),
    ("planifies", "Planifiés"),
    ("afacturer", "À facturer"),
    ("arecevoir", "À recevoir"),
]
TRIS = [("attente", "Délai d'attente (le plus long d'abord)"), ("secteur", "Secteur (ville, code postal)"),
        ("duree", "Durée (la plus longue d'abord)")]
FILTRES_ATTENTE = [("", "Tous les délais"), ("urgente", f"Urgents (plus de {SEUIL_URGENT} j)"),
                   ("surveiller", f"À surveiller ({SEUIL_SURVEILLER} à {SEUIL_URGENT} j)"),
                   ("normale", f"Normaux (moins de {SEUIL_SURVEILLER} j)")]
TITRES_PRIORITE = {"urgente": f"Urgent : plus de {SEUIL_URGENT} jours d'attente",
                   "surveiller": f"À surveiller : {SEUIL_SURVEILLER} à {SEUIL_URGENT} jours",
                   "normale": f"Normal : moins de {SEUIL_SURVEILLER} jours"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

COLONNES_VUE = ["chantier_id", "client_id", "client_nom_complet", "telephone", "adresse", "ville", "code_postal",
                "adresse_maps", "type_libelle", "travaux_detail", "description", "statut", "statut_paiement", "solde",
                "total_ttc", "paye", "prix_ht", "date_prevue", "heure_prevue", "duree_estimee_h", "attente_depuis",
                "modalite_paiement", "date_facture", "secteur_tri"]


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------
def _lignes(conn, condition="1=1", params=()):
    """Chantiers de la vue sous forme de dicts, avec le délai d'attente calculé."""
    colonnes = ", ".join(c for c in COLONNES_VUE if c != "secteur_tri")
    cur = conn.execute(f"SELECT {colonnes} FROM v_chantiers WHERE {condition}", params)
    noms = [d[0] for d in cur.description]
    aujourdhui = datetime.date.today()
    lignes = []
    for r in cur.fetchall():
        l = dict(zip(noms, r))
        l["secteur_tri"] = (cle(l["ville"]), (l["code_postal"] or "").replace(" ", ""))
        lignes.append(l)
    return lignes, aujourdhui


def _reference_attente(l, vue):
    """Date à partir de laquelle on compte l'attente, selon l'onglet."""
    if vue in ("afacturer",):
        return l["date_prevue"] or l["attente_depuis"]
    if vue == "arecevoir":
        return l["date_facture"] or l["date_prevue"] or l["attente_depuis"]
    return l["attente_depuis"]


def _dans_vue(l, vue):
    st, sp = l["statut"], l["statut_paiement"]
    return {"aplanifier": st == "accepte", "soumissions": st == "soumission", "planifies": st == "planifie",
            "afacturer": sp in ("non_facture", "prix_manquant"), "arecevoir": sp in ("a_payer", "partiel")}[vue]


def _nom(l):
    return l["client_nom_complet"]


def retour_valide(retour, defaut="/"):
    """N'accepte qu'un chemin local (jamais une adresse externe)."""
    if not retour or not retour.startswith("/") or retour.startswith("//") or "\\" in retour:
        return defaut
    return retour


def _avec_params(url, **params):
    u = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k not in params]
    q += [(k, v) for k, v in params.items() if v is not None]
    return urlunsplit(("", "", u.path or "/", urlencode(q), ""))


# ---------------------------------------------------------------------------
# Composants
# ---------------------------------------------------------------------------
def _mode_conseille(modalite):
    m = cle(modalite or "")
    for mot, mode in (("interac", "interac"), ("cheque", "cheque"), ("comptant", "comptant"), ("carte", "carte")):
        if mot in m:
            return mode
    return "interac"


def _form_statut(l, retour, avec_date=True):
    options = "".join(f'<option value="{s}"{" selected" if s == l["statut"] else ""}>{esc(LIBELLES_STATUT[s])}</option>' for s in STATUTS)
    duree = f"{l['duree_estimee_h']:g}" if l["duree_estimee_h"] else ""
    date = ""
    if avec_date:
        date = (f'<input type="date" name="date_prevue" value="{esc(l["date_prevue"])}" title="Date des travaux (obligatoire pour Planifié / Terminé)">'
                f'<input class="court" name="duree_estimee_h" value="{esc(duree)}" inputmode="decimal" placeholder="h" '
                f'title="Durée estimée en heures (2,5 = 2 h 30)">')
    return (f'<form class="mini" method="post" action="/action/statut"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
            f'<input type="hidden" name="retour" value="{esc(retour)}"><select name="statut" aria-label="Statut">{options}</select>{date}'
            f'<button type="submit" class="secondaire">OK</button></form>')


def _actions_paiement(l, retour):
    sp, st = l["statut_paiement"], l["statut"]
    out = []
    if sp not in ("sans_objet", "a_venir"):
        out.append(badge(sp, LIBELLES_PAIEMENT[sp]))
    if l["total_ttc"]:
        detail = f'Total {argent(l["total_ttc"])}'
        if l["paye"]:
            detail += f' · reçu {argent(l["paye"])} · solde <b>{argent(l["solde"])}</b>'
        out.append(f'<div class="doux">{detail}</div>')
    if l["modalite_paiement"]:
        out.append(f'<div class="doux">Modalité : {esc(l["modalite_paiement"])}</div>')
    if sp == "non_facture":
        out.append(f'<form class="mini" method="post" action="/action/facturer"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
                   f'<input type="hidden" name="retour" value="{esc(retour)}"><button type="submit" class="secondaire">Facturer</button></form>')
    if sp == "prix_manquant":
        out.append(f'<div class="doux"><a href="/chantier/{l["chantier_id"]}">Saisir le prix</a></div>')
    # on n'encaisse que ce qui est fait ou planifié (acompte) ; pas une soumission ni un chantier à planifier
    if st in ("planifie", "termine") and l["solde"] and l["solde"] > 0 and l["total_ttc"]:
        mode = _mode_conseille(l["modalite_paiement"])
        options = "".join(f'<option value="{m}"{" selected" if m == mode else ""}>{esc(LIBELLES_MODE[m])}</option>' for m in MODES)
        out.append(f'<form class="mini" method="post" action="/action/encaisser"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
                   f'<input type="hidden" name="retour" value="{esc(retour)}"><input class="court" style="width:84px" name="montant" '
                   f'value="{l["solde"]:.2f}" inputmode="decimal" aria-label="Montant reçu" title="Montant reçu (taxes incluses)">'
                   f'<select name="mode" aria-label="Mode de paiement">{options}</select><button type="submit">Encaisser</button></form>')
    return "".join(out)


def _cellule_client(l):
    tel = l["telephone"]
    tel_txt = f'<div class="doux">{esc(tel[2:5] + "-" + tel[5:8] + "-" + tel[8:])}</div>' if tel and len(tel) == 12 else ""
    return f'<a href="/client/{l["client_id"]}">{esc(_nom(l))}</a>{tel_txt}'


def _cellule_adresse(l):
    return (f'{lien_maps(l["adresse_maps"], l["adresse"])}<div class="doux">{esc(l["ville"])}'
            f'{" · " + esc(l["code_postal"]) if l["code_postal"] else ""}</div>')


def _cellule_travaux(l):
    duree = f'<span class="total">⏱ {heures(l["duree_estimee_h"])}</span>' if l["duree_estimee_h"] else '<span class="doux">durée à estimer</span>'
    desc = f'<div class="doux">{esc(l["description"])}</div>' if l["description"] else ""
    return f'<a href="/chantier/{l["chantier_id"]}">{esc(l["travaux_detail"] or l["type_libelle"])}</a><div>{duree}</div>{desc}'


# ---------------------------------------------------------------------------
# Tableau de bord
# ---------------------------------------------------------------------------
def page_tableau(conn, query):
    vue = query.get("vue") if query.get("vue") in dict(VUES) else "aplanifier"
    f_attente = query.get("attente", "")
    f_secteur = query.get("secteur", "")
    tri = query.get("tri") if query.get("tri") in dict(TRIS) else "attente"
    q = query.get("q", "").strip()
    toutes, aujourdhui = _lignes(conn, "statut IN ('soumission','accepte','planifie') OR statut_paiement IN "
                                       "('non_facture','prix_manquant','a_payer','partiel')")
    for l in toutes:
        l["jours"] = {v: jours_attente(_reference_attente(l, v), aujourdhui) for v, _ in VUES}

    # Onglets : nombre de chantiers (et d'urgents pour les files d'attente)
    onglets = ""
    for code, titre in VUES:
        dedans = [l for l in toutes if _dans_vue(l, code)]
        urgents = sum(1 for l in dedans if priorite(l["jours"][code]) == "urgente") if code in ("aplanifier", "soumissions", "arecevoir") else 0
        extra = f' · <b>{urgents} urgent{"s" if urgents > 1 else ""}</b>' if urgents else ""
        classe = " actif" if code == vue else ""
        onglets += f'<a class="onglet{classe}" href="/?vue={code}">{esc(titre)} ({len(dedans)}{extra})</a>'

    lignes = [l for l in toutes if _dans_vue(l, vue)]
    secteurs = sorted({l["ville"] for l in lignes}, key=cle)
    if f_secteur:
        lignes = [l for l in lignes if l["ville"] == f_secteur]
    if f_attente:
        lignes = [l for l in lignes if priorite(l["jours"][vue]) == f_attente]
    if q:
        mots = cle(q).split()
        lignes = [l for l in lignes if all(m in cle(" ".join(str(l[c]) for c in ("client_nom_complet", "adresse", "ville", "travaux_detail", "description") if l[c])) for m in mots)]

    retour = "/?" + urlencode({k: v for k, v in (("vue", vue), ("attente", f_attente), ("secteur", f_secteur), ("tri", tri), ("q", q)) if v})

    # Filtres
    opt_att = "".join(f'<option value="{c}"{" selected" if c == f_attente else ""}>{esc(t)}</option>' for c, t in FILTRES_ATTENTE)
    opt_sec = '<option value="">Tous les secteurs</option>' + "".join(f'<option value="{esc(s)}"{" selected" if s == f_secteur else ""}>{esc(s)}</option>' for s in secteurs)
    opt_tri = "".join(f'<option value="{c}"{" selected" if c == tri else ""}>{esc(t)}</option>' for c, t in TRIS)
    filtres = (f'<form class="recherche" method="get" action="/"><input type="hidden" name="vue" value="{vue}">'
               f'<input type="search" name="q" value="{esc(q)}" placeholder="Chercher…"><select name="attente" aria-label="Délai d\'attente">{opt_att}</select>'
               f'<select name="secteur" aria-label="Secteur">{opt_sec}</select><select name="tri" aria-label="Tri">{opt_tri}</select>'
               f'<button type="submit">Filtrer</button></form>')

    # Groupes
    def cle_tri(l):
        if tri == "secteur":
            return (l["secteur_tri"], -l["jours"][vue])
        if tri == "duree":
            return (-(l["duree_estimee_h"] or 0), -l["jours"][vue])
        return (-l["jours"][vue], l["secteur_tri"])
    groupes = []
    if vue in ("aplanifier", "soumissions", "arecevoir") and tri == "attente":
        for prio in ("urgente", "surveiller", "normale"):
            membres = sorted([l for l in lignes if priorite(l["jours"][vue]) == prio], key=cle_tri)
            if membres:
                groupes.append((TITRES_PRIORITE[prio], membres, None))
    elif vue in ("aplanifier", "soumissions") and tri == "secteur":
        for ville in sorted({l["ville"] for l in lignes}, key=cle):
            groupes.append((f"Secteur : {ville}", sorted([l for l in lignes if l["ville"] == ville], key=cle_tri), None))
    elif vue == "planifies":
        for jour in sorted({l["date_prevue"] for l in lignes}):
            membres = sorted([l for l in lignes if l["date_prevue"] == jour],
                             key=lambda l: (l["heure_prevue"] or "99:99", l["secteur_tri"]))
            groupes.append((jour, membres, jour))
    else:
        groupes.append((None, sorted(lignes, key=cle_tri), None))

    # Corps
    colonne_date = {"aplanifier": "Attente", "soumissions": "Attente", "planifies": "Heure", "afacturer": "Depuis", "arecevoir": "Depuis"}[vue]
    html_groupes = ""
    for titre, membres, jour in groupes:
        total_h = sum(l["duree_estimee_h"] or 0 for l in membres)
        entete = ""
        if titre is not None:
            if jour:
                d = datetime.date.fromisoformat(jour)
                libelle = f'{JOURS[d.weekday()].capitalize()} {jour}'
                lien = f' · <a href="/tournee?date={jour}">Organiser la tournée</a>'
            else:
                libelle, lien = titre, ""
            entete = (f'<h2 class="groupe">{esc(libelle)} <small>{len(membres)} chantier{"s" if len(membres) > 1 else ""} · '
                      f'<b>{heures(total_h) if total_h else "durée inconnue"}</b>{lien}</small></h2>')
        corps = ""
        for l in membres:
            prio = priorite(l["jours"][vue])
            if vue == "planifies":
                premiere = f'<b>{esc(l["heure_prevue"] or "—")}</b>'
            else:
                ref = _reference_attente(l, vue)
                premiere = f'{badge_attente(l["jours"][vue], prio)}<div class="doux">depuis {esc(ref)}</div>'
            classe = f' class="ligne-{prio}"' if prio != "normale" and vue != "planifies" else ""
            corps += (f'<tr{classe}><td>{premiere}</td><td>{_cellule_client(l)}</td><td>{_cellule_adresse(l)}</td>'
                      f'<td>{_cellule_travaux(l)}</td><td class="col-statut">'
                      f'{_form_statut(l, retour, avec_date=l["statut"] != "termine")}</td><td class="col-paiement">{_actions_paiement(l, retour)}</td></tr>')
        html_groupes += (entete + f'<div class="liste-defile"><table class="tableau"><thead><tr><th>{colonne_date}</th><th>Client</th><th>Adresse</th>'
                         f'<th>Travaux · durée</th><th>Statut</th><th>Paiement</th></tr></thead><tbody>{corps}</tbody></table></div>')
    if not html_groupes:
        html_groupes = '<div class="carte">Rien à afficher avec ces filtres. 🎉</div>'

    total_h = sum(l["duree_estimee_h"] or 0 for l in lignes)
    resume = ""
    if lignes:
        argent_total = sum(l["solde"] for l in lignes if l["statut_paiement"] in ("non_facture", "a_payer", "partiel"))
        resume = (f'<p class="doux">{len(lignes)} chantier{"s" if len(lignes) > 1 else ""} · durée totale <b>{heures(total_h) if total_h else "—"}</b>'
                  + (f' · à facturer/recevoir <b>{argent(argent_total)}</b>' if vue in ("afacturer", "arecevoir") else "") + "</p>")
    return gabarit("Tableau de bord", f'<h1>Tableau de bord</h1><div class="onglets">{onglets}</div>{filtres}{resume}{html_groupes}',
                   query.get("ok"), query.get("err"), large=True)


# ---------------------------------------------------------------------------
# Actions rapides (POST) : retour à la page d'où elles viennent
# ---------------------------------------------------------------------------
def _terminer(conn, form, ok, travail):
    retour = retour_valide(form.get("retour"))
    try:
        with transaction(conn):
            erreurs = travail()
            if erreurs:
                raise _Refus(erreurs)
    except _Refus as r:
        return redirection(_avec_params(retour, err=" ; ".join(r.erreurs)[:300], ok=None))
    except sqlite3.IntegrityError as e:
        return redirection(_avec_params(retour, err=f"Refusé par la base : {e}"[:300], ok=None))
    return redirection(_avec_params(retour, ok=ok, err=None))


class _Refus(Exception):
    def __init__(self, erreurs):
        self.erreurs = erreurs


def _id(form):
    v = form.get("chantier_id", "")
    return int(v) if v.isdigit() else 0


def action_statut(conn, form):
    return _terminer(conn, form, "statut_change", lambda: changer_statut(
        conn, _id(form), form.get("statut", ""), form.get("date_prevue"), form.get("duree_estimee_h")))


def action_facturer(conn, form):
    return _terminer(conn, form, "facture", lambda: facturer(conn, _id(form)))


def action_encaisser(conn, form):
    return _terminer(conn, form, "encaisse", lambda: encaisser(conn, _id(form), form.get("montant"), form.get("mode")))


def action_retirer(conn, form):
    return _terminer(conn, form, "retire", lambda: changer_statut(conn, _id(form), "accepte"))


# ---------------------------------------------------------------------------
# Tournées
# ---------------------------------------------------------------------------
def _jour_valide(texte):
    try:
        return datetime.date.fromisoformat(texte).isoformat() if texte else None
    except ValueError:
        return None


def page_tournee(conn, query):
    demain = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    jour = _jour_valide(query.get("date")) or demain
    d = datetime.date.fromisoformat(jour)
    f_statut = query.get("statut") if query.get("statut") in ("accepte", "soumission", "planifie") else "accepte"
    f_attente = query.get("attente", "")
    f_secteur = query.get("secteur", "")
    tri = query.get("tri") if query.get("tri") in dict(TRIS) else "secteur"
    toutes, aujourdhui = _lignes(conn, "statut IN ('soumission','accepte','planifie')")
    for l in toutes:
        l["jours"] = jours_attente(l["attente_depuis"], aujourdhui)

    # --- la journée
    du_jour = sorted([l for l in toutes if l["statut"] == "planifie" and l["date_prevue"] == jour],
                     key=lambda l: (l["heure_prevue"] or "99:99", l["secteur_tri"]))
    deja_h = sum(l["duree_estimee_h"] or 0 for l in du_jour)
    sans_duree = sum(1 for l in du_jour if not l["duree_estimee_h"])
    retour = "/tournee?" + urlencode({k: v for k, v in (("date", jour), ("statut", f_statut), ("attente", f_attente), ("secteur", f_secteur), ("tri", tri)) if v})
    precedent, suivant = (d - datetime.timedelta(days=1)).isoformat(), (d + datetime.timedelta(days=1)).isoformat()
    navigation = (f'<form class="recherche" method="get" action="/tournee"><a class="bouton secondaire" href="/tournee?date={precedent}">◀</a>'
                  f'<input type="date" name="date" value="{jour}" style="max-width:170px" aria-label="Journée"><button type="submit">Afficher</button>'
                  f'<a class="bouton secondaire" href="/tournee?date={suivant}">▶</a>'
                  f'<a class="bouton secondaire" href="/tournee?date={demain}">Demain</a></form>')
    corps = ""
    for n, l in enumerate(du_jour, 1):
        corps += (f'<tr><td><b>{n}</b></td><td>{esc(l["heure_prevue"] or "")}</td><td>{_cellule_client(l)}</td><td>{_cellule_adresse(l)}</td>'
                  f'<td>{_cellule_travaux(l)}</td><td><form class="mini" method="post" action="/action/retirer"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
                  f'<input type="hidden" name="retour" value="{esc(retour)}"><button type="submit" class="danger" title="Remettre dans « à planifier »">Retirer</button></form></td></tr>')
    table_jour = (f'<div class="liste-defile"><table class="tableau"><thead><tr><th>#</th><th>Heure</th><th>Client</th><th>Adresse</th><th>Travaux · durée</th><th></th></tr></thead>'
                  f'<tbody>{corps}</tbody></table></div>' if du_jour else '<p class="doux">Rien de planifié ce jour-là : choisis des chantiers ci-dessous.</p>')
    reste = JOURNEE_H - deja_h
    etat = (f'<span class="a-urgente attente">dépasse de {heures(-reste)}</span>' if reste < 0
            else f'<span class="a-normale attente">il reste {heures(reste)}</span>')
    avert = f' · <span class="doux">{sans_duree} sans durée estimée</span>' if sans_duree else ""
    en_tete_jour = (f'<h2>{esc(JOURS[d.weekday()].capitalize())} {jour}</h2><p>{len(du_jour)} chantier{"s" if len(du_jour) > 1 else ""} · '
                    f'<span class="total">{heures(deja_h) if deja_h else "0 h"}</span> sur {heures(JOURNEE_H)} {etat}{avert}</p>')

    # --- les chantiers à placer
    candidats = [l for l in toutes if l["statut"] == f_statut and not (l["statut"] == "planifie" and l["date_prevue"] == jour)]
    secteurs = sorted({l["ville"] for l in candidats}, key=cle)
    if f_secteur:
        candidats = [l for l in candidats if l["ville"] == f_secteur]
    if f_attente:
        candidats = [l for l in candidats if priorite(l["jours"]) == f_attente]
    def cle_tri(l):
        if tri == "secteur":
            return (l["secteur_tri"], -l["jours"])
        if tri == "duree":
            return (-(l["duree_estimee_h"] or 0), -l["jours"])
        return (-l["jours"], l["secteur_tri"])
    candidats.sort(key=cle_tri)

    opt_statut = "".join(f'<option value="{c}"{" selected" if c == f_statut else ""}>{t}</option>' for c, t in
                         (("accepte", "À planifier (acceptés)"), ("soumission", "Soumissions"), ("planifie", "Planifiés un autre jour (déplacer)")))
    opt_att = "".join(f'<option value="{c}"{" selected" if c == f_attente else ""}>{esc(t)}</option>' for c, t in FILTRES_ATTENTE)
    opt_sec = '<option value="">Tous les secteurs</option>' + "".join(f'<option value="{esc(s)}"{" selected" if s == f_secteur else ""}>{esc(s)}</option>' for s in secteurs)
    opt_tri = "".join(f'<option value="{c}"{" selected" if c == tri else ""}>{esc(t)}</option>' for c, t in TRIS)
    filtres = (f'<form class="recherche" method="get" action="/tournee"><input type="hidden" name="date" value="{jour}">'
               f'<select name="statut" aria-label="Statut">{opt_statut}</select><select name="attente" aria-label="Délai d\'attente">{opt_att}</select>'
               f'<select name="secteur" aria-label="Secteur">{opt_sec}</select><select name="tri" aria-label="Tri">{opt_tri}</select>'
               f'<button type="submit">Filtrer</button></form>')

    corps, secteur_courant = "", None
    for l in candidats:
        if tri == "secteur" and l["ville"] != secteur_courant:
            secteur_courant = l["ville"]
            dans = [x for x in candidats if x["ville"] == secteur_courant]
            h = sum(x["duree_estimee_h"] or 0 for x in dans)
            corps += (f'<tr><td colspan="7"><b>Secteur : {esc(secteur_courant)}</b> <span class="doux">{len(dans)} chantier{"s" if len(dans) > 1 else ""}'
                      f'{" · " + heures(h) if h else ""}</span></td></tr>')
        prio = priorite(l["jours"])
        duree = f"{l['duree_estimee_h']:g}" if l["duree_estimee_h"] else ""
        autre_jour = f'<div class="doux">prévu le {esc(l["date_prevue"])}</div>' if l["statut"] == "planifie" else ""
        corps += (f'<tr data-id="{l["chantier_id"]}" class="ligne-{prio}"><td><input type="checkbox" name="sel_{l["chantier_id"]}" value="1" '
                  f'aria-label="Choisir {esc(_nom(l))}"></td><td>{badge_attente(l["jours"], prio)}<div class="doux">depuis {esc(l["attente_depuis"])}</div></td>'
                  f'<td>{_cellule_client(l)}</td><td>{_cellule_adresse(l)}</td><td><a href="/chantier/{l["chantier_id"]}">{esc(l["travaux_detail"] or l["type_libelle"])}</a>'
                  f'{"<div class=doux>" + esc(l["description"]) + "</div>" if l["description"] else ""}{autre_jour}</td>'
                  f'<td><input class="duree court" style="width:70px" name="duree_{l["chantier_id"]}" value="{duree}" inputmode="decimal" '
                  f'placeholder="h" aria-label="Durée estimée en heures"></td>'
                  f'<td>{badge(l["statut_paiement"], LIBELLES_PAIEMENT[l["statut_paiement"]]) if l["statut_paiement"] not in ("sans_objet", "a_venir") else ""}</td></tr>')
    if candidats:
        liste = (f'<form method="post" action="/tournee/planifier" id="lot" data-deja="{deja_h}" data-cap="{JOURNEE_H:g}">'
                 f'<input type="hidden" name="date" value="{jour}"><input type="hidden" name="retour" value="{esc(retour)}">'
                 f'<div class="liste-defile"><table class="tableau"><thead><tr><th></th><th>Attente</th><th>Client</th><th>Adresse</th><th>Travaux</th><th>Durée (h)</th><th>Paiement</th></tr></thead>'
                 f'<tbody>{corps}</tbody></table></div>'
                 f'<div class="sel-total barre"><span id="sel">0 sélectionné</span><button type="submit">Ajouter à la journée du {jour}</button></div></form>'
                 + _SCRIPT_SELECTION)
    else:
        liste = '<div class="carte">Aucun chantier ne correspond à ces filtres.</div>'
    contenu = (f'<h1>Tournées</h1>{navigation}<div class="carte">{en_tete_jour}{table_jour}</div>'
               f'<h2>Chantiers à placer</h2>{filtres}{liste}')
    return gabarit("Tournées", contenu, query.get("ok"), query.get("err"), large=True)


_SCRIPT_SELECTION = """<script>
(function(){var f=document.getElementById('lot');if(!f)return;var base=parseFloat(f.dataset.deja)||0,cap=parseFloat(f.dataset.cap)||8;
function maj(){var n=0,t=0;f.querySelectorAll('tr[data-id]').forEach(function(tr){var c=tr.querySelector('input[type=checkbox]');
if(c.checked){n++;var d=parseFloat((tr.querySelector('input.duree').value||'').replace(',','.'));if(!isNaN(d))t+=d;}});
document.getElementById('sel').textContent=n+' sélectionné'+(n>1?'s':'')+' · '+t.toFixed(1).replace('.',',')+' h → journée : '+(base+t).toFixed(1).replace('.',',')+' h sur '+cap+' h';}
f.addEventListener('change',maj);f.addEventListener('input',maj);maj();})();
</script>"""


def action_planifier_lot(conn, form):
    ids = sorted(int(k[4:]) for k, v in form.items() if k.startswith("sel_") and k[4:].isdigit() and v)
    durees = {i: form.get(f"duree_{i}", "") for i in ids}
    jour = form.get("date", "")
    return _terminer(conn, form, "planifie_lot", lambda: planifier_lot(conn, ids, jour, durees))


ROUTES_TABLEAU = [
    ("GET", r"^/$", lambda c, q, f, *g: page_tableau(c, q)),
    ("GET", r"^/tournee$", lambda c, q, f, *g: page_tournee(c, q)),
    ("POST", r"^/tournee/planifier$", lambda c, q, f, *g: action_planifier_lot(c, f)),
    ("POST", r"^/action/statut$", lambda c, q, f, *g: action_statut(c, f)),
    ("POST", r"^/action/facturer$", lambda c, q, f, *g: action_facturer(c, f)),
    ("POST", r"^/action/encaisser$", lambda c, q, f, *g: action_encaisser(c, f)),
    ("POST", r"^/action/retirer$", lambda c, q, f, *g: action_retirer(c, f)),
]
