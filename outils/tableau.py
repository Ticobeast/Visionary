"""Suivi (files d'attente par statut), actions rapides et organisation des tournées.

Suivi (/suivi) : ce qu'il y a à planifier (classé par délai d'attente), les soumissions et chantiers en attente,
les chantiers planifiés (par jour), ce qui reste à facturer et à encaisser, avec les actions rapides de chaque ligne.

Tournées (/tournee) : on choisit une journée, on voit son déroulement (heures calculées, ordre modifiable), on filtre
les chantiers à placer (secteur, délai d'attente, statut), on en coche plusieurs et on les ajoute à la journée.
"""
import datetime
import sqlite3
from urllib.parse import urlencode

from calendrier import panneau_jour
from composants import (FILTRES_ATTENTE, JOURNEE_H, JOURS, TITRES_PRIORITE, TRIS, VUES, actions_paiement, avec_params,
                        cellule_adresse, cellule_client, cellule_travaux, dans_vue, form_statut, lignes_vue, nom_client,
                        reference_attente, retour_valide)
from noyau import (STATUTS, SEUIL_SURVEILLER, SEUIL_URGENT, changer_statut, cle, deplacer, encaisser, facturer,
                   jours_attente, planifier_lot, priorite, transaction)
from vue import (LIBELLES_PAIEMENT, LIBELLES_STATUT, argent, badge, badge_attente, esc, gabarit, heures, redirection)


# ---------------------------------------------------------------------------
# Suivi
# ---------------------------------------------------------------------------
def page_suivi(conn, query):
    vue = query.get("vue") if query.get("vue") in dict(VUES) else "aplanifier"
    f_attente = query.get("attente", "")
    f_secteur = query.get("secteur", "")
    tri = query.get("tri") if query.get("tri") in dict(TRIS) else "attente"
    q = query.get("q", "").strip()
    toutes, aujourdhui = lignes_vue(conn, "statut IN ('soumission','en_attente','a_planifier','planifie') OR statut_paiement IN "
                                          "('non_facture','prix_manquant','a_payer','partiel')")
    for l in toutes:
        l["jours"] = {v: jours_attente(reference_attente(l, v), aujourdhui) for v, _ in VUES}

    # Onglets : nombre de chantiers (et d'urgents pour les files d'attente)
    onglets = ""
    for code, titre in VUES:
        dedans = [l for l in toutes if dans_vue(l, code)]
        urgents = sum(1 for l in dedans if priorite(l["jours"][code]) == "urgente") if code in ("aplanifier", "enattente", "soumissions", "arecevoir") else 0
        extra = f' · <b>{urgents} urgent{"s" if urgents > 1 else ""}</b>' if urgents else ""
        classe = " actif" if code == vue else ""
        onglets += f'<a class="onglet{classe}" href="/suivi?vue={code}">{esc(titre)} ({len(dedans)}{extra})</a>'

    lignes = [l for l in toutes if dans_vue(l, vue)]
    secteurs = sorted({l["ville"] for l in lignes}, key=cle)
    if f_secteur:
        lignes = [l for l in lignes if l["ville"] == f_secteur]
    if f_attente:
        lignes = [l for l in lignes if priorite(l["jours"][vue]) == f_attente]
    if q:
        mots = cle(q).split()
        lignes = [l for l in lignes if all(m in cle(" ".join(str(l[c]) for c in ("client_nom_complet", "adresse", "ville", "travaux_detail", "description") if l[c])) for m in mots)]

    retour = "/suivi?" + urlencode({k: v for k, v in (("vue", vue), ("attente", f_attente), ("secteur", f_secteur), ("tri", tri), ("q", q)) if v})

    # Filtres
    opt_att = "".join(f'<option value="{c}"{" selected" if c == f_attente else ""}>{esc(t)}</option>' for c, t in FILTRES_ATTENTE)
    opt_sec = '<option value="">Tous les secteurs</option>' + "".join(f'<option value="{esc(s)}"{" selected" if s == f_secteur else ""}>{esc(s)}</option>' for s in secteurs)
    opt_tri = "".join(f'<option value="{c}"{" selected" if c == tri else ""}>{esc(t)}</option>' for c, t in TRIS)
    filtres = (f'<form class="recherche" method="get" action="/suivi"><input type="hidden" name="vue" value="{vue}">'
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
    if vue in ("aplanifier", "enattente", "soumissions", "arecevoir") and tri == "attente":
        for prio in ("urgente", "surveiller", "normale"):
            membres = sorted([l for l in lignes if priorite(l["jours"][vue]) == prio], key=cle_tri)
            if membres:
                groupes.append((TITRES_PRIORITE[prio], membres, None))
    elif vue in ("aplanifier", "enattente", "soumissions") and tri == "secteur":
        for ville in sorted({l["ville"] for l in lignes}, key=cle):
            groupes.append((f"Secteur : {ville}", sorted([l for l in lignes if l["ville"] == ville], key=cle_tri), None))
    elif vue == "planifies":
        for jour in sorted({l["date_prevue"] for l in lignes}):
            membres = sorted([l for l in lignes if l["date_prevue"] == jour],
                             key=lambda l: (l["ordre_jour"] or 1000000, l["secteur_tri"]))
            groupes.append((jour, membres, jour))
    else:
        groupes.append((None, sorted(lignes, key=cle_tri), None))

    # Corps
    colonne_date = {"aplanifier": "Attente", "enattente": "Attente", "soumissions": "Attente", "planifies": "Ordre", "afacturer": "Depuis", "arecevoir": "Depuis"}[vue]
    html_groupes = ""
    for titre, membres, jour in groupes:
        total_h = sum(l["duree_estimee_h"] or 0 for l in membres)
        entete = ""
        if titre is not None:
            if jour:
                d = datetime.date.fromisoformat(jour)
                libelle = f'{JOURS[d.weekday()].capitalize()} {jour}'
                lien = f' · <a href="/?date={jour}">Voir la journée</a> · <a href="/tournee?date={jour}">Organiser la tournée</a>'
            else:
                libelle, lien = titre, ""
            entete = (f'<h2 class="groupe">{esc(libelle)} <small>{len(membres)} chantier{"s" if len(membres) > 1 else ""} · '
                      f'<b>{heures(total_h) if total_h else "durée inconnue"}</b>{lien}</small></h2>')
        corps = ""
        for l in membres:
            prio = priorite(l["jours"][vue])
            if vue == "planifies":
                premiere = f'<b>n° {esc(l["ordre_jour"] or "—")}</b>'
            else:
                ref = reference_attente(l, vue)
                premiere = f'{badge_attente(l["jours"][vue], prio)}<div class="doux">depuis {esc(ref)}</div>'
            classe = f' class="ligne-{prio}"' if prio != "normale" and vue != "planifies" else ""
            corps += (f'<tr{classe}><td>{premiere}</td><td>{cellule_client(l)}</td><td>{cellule_adresse(l)}</td>'
                      f'<td>{cellule_travaux(l)}</td><td class="col-statut">'
                      f'{form_statut(l, retour, avec_date=l["statut"] != "termine")}</td><td class="col-paiement">{actions_paiement(l, retour)}</td></tr>')
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
    return gabarit("Suivi", f'<h1>Suivi des chantiers</h1><div class="onglets">{onglets}</div>{filtres}{resume}{html_groupes}',
                   query.get("ok"), query.get("err"), large=True)


# ---------------------------------------------------------------------------
# Actions rapides (POST) : retour à la page d'où elles viennent
# ---------------------------------------------------------------------------
class _Refus(Exception):
    def __init__(self, erreurs):
        self.erreurs = erreurs


def _terminer(conn, form, ok, travail, extra=None):
    retour = retour_valide(form.get("retour"))
    try:
        with transaction(conn):
            erreurs = travail()
            if erreurs:
                raise _Refus(erreurs)
    except _Refus as r:
        return redirection(avec_params(retour, err=" ; ".join(r.erreurs)[:300], ok=None))
    except sqlite3.IntegrityError as e:
        return redirection(avec_params(retour, err=f"Refusé par la base : {e}"[:300], ok=None))
    return redirection(avec_params(retour, ok=ok, err=None, **(extra or {})))


def _id(form):
    v = form.get("chantier_id", "")
    return int(v) if v.isdigit() else 0


def action_statut(conn, form):
    return _terminer(conn, form, "statut_change", lambda: changer_statut(
        conn, _id(form), form.get("statut", ""), form.get("date_prevue"), form.get("duree_estimee_h"), form.get("duree_reelle_h")),
        extra={"terminer": None})


def action_facturer(conn, form):
    return _terminer(conn, form, "facture", lambda: facturer(conn, _id(form), form.get("date_facture") or None, form.get("numero_facture")))


def action_encaisser(conn, form):
    """Enregistre le paiement ; si le chantier est « Planifié », propose ensuite de le passer à « Terminé »."""
    r = conn.execute("SELECT statut FROM chantiers WHERE id = ?", (_id(form),)).fetchone()
    extra = {"terminer": _id(form)} if r and r[0] == "planifie" else {"terminer": None}
    return _terminer(conn, form, "encaisse", lambda: encaisser(conn, _id(form), form.get("montant"), form.get("mode")), extra=extra)


def action_retirer(conn, form):
    return _terminer(conn, form, "retire", lambda: changer_statut(conn, _id(form), "a_planifier"))


def action_deplacer(conn, form):
    return _terminer(conn, form, "deplace", lambda: deplacer(conn, _id(form), form.get("sens", "")))


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
    f_statut = query.get("statut") if query.get("statut") in ("a_planifier", "en_attente", "soumission", "planifie") else "a_planifier"
    f_attente = query.get("attente", "")
    f_secteur = query.get("secteur", "")
    tri = query.get("tri") if query.get("tri") in dict(TRIS) else "secteur"
    toutes, aujourdhui = lignes_vue(conn, "statut IN ('soumission','en_attente','a_planifier','planifie')")
    for l in toutes:
        l["jours"] = jours_attente(l["attente_depuis"], aujourdhui)

    retour = "/tournee?" + urlencode({k: v for k, v in (("date", jour), ("statut", f_statut), ("attente", f_attente), ("secteur", f_secteur), ("tri", tri)) if v})
    precedent, suivant = (d - datetime.timedelta(days=1)).isoformat(), (d + datetime.timedelta(days=1)).isoformat()
    navigation = (f'<form class="recherche" method="get" action="/tournee"><a class="bouton secondaire" href="/tournee?date={precedent}">◀</a>'
                  f'<input type="date" name="date" value="{jour}" style="max-width:170px" aria-label="Journée"><button type="submit">Afficher</button>'
                  f'<a class="bouton secondaire" href="/tournee?date={suivant}">▶</a>'
                  f'<a class="bouton secondaire" href="/tournee?date={demain}">Demain</a>'
                  f'<a class="bouton secondaire" href="/?date={jour}">Voir au calendrier</a></form>')
    deja_h = sum(l["duree_estimee_h"] or 0 for l in toutes if l["statut"] == "planifie" and l["date_prevue"] == jour)
    journee = panneau_jour(conn, jour, retour)

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
                         (("a_planifier", "À planifier"), ("en_attente", "En attente"), ("soumission", "Soumissions"),
                          ("planifie", "Planifiés un autre jour (déplacer)")))
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
                  f'aria-label="Choisir {esc(nom_client(l))}"></td><td>{badge_attente(l["jours"], prio)}<div class="doux">depuis {esc(l["attente_depuis"])}</div></td>'
                  f'<td>{cellule_client(l)}</td><td>{cellule_adresse(l)}</td><td><a href="/chantier/{l["chantier_id"]}">{esc(l["travaux_detail"] or l["type_libelle"])}</a>'
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
    contenu = (f'<h1>Tournées</h1>{navigation}{journee}'
               f'<h2>Chantiers à placer dans cette journée</h2>{filtres}{liste}')
    return gabarit("Tournées", contenu, query.get("ok"), query.get("err"), large=True)


_SCRIPT_SELECTION = """<script>
(function(){var f=document.getElementById('lot');if(!f)return;var base=parseFloat(f.dataset.deja)||0,cap=parseFloat(f.dataset.cap)||8;
function maj(){var n=0,t=0;f.querySelectorAll('tr[data-id]').forEach(function(tr){var c=tr.querySelector('input[type=checkbox]');
if(c.checked){n++;var d=parseFloat((tr.querySelector('input.duree').value||'').replace(',','.'));if(!isNaN(d))t+=d;}});
document.getElementById('sel').textContent=n+' sélectionné'+(n>1?'s':'')+' · '+t.toFixed(1).replace('.',',')+' h → journée : '+(base+t).toFixed(1).replace('.',',')+' h sur '+cap+' h';}
f.addEventListener('change',maj);f.addEventListener('input',maj);maj();})();
</script>"""


def action_planifier_lot(conn, form):
    """Ajoute les chantiers cochés à la fin de la journée, dans l'ordre où ils sont affichés."""
    ids = [int(k[4:]) for k, v in form.items() if k.startswith("sel_") and k[4:].isdigit() and v]
    durees = {i: form.get(f"duree_{i}", "") for i in ids}
    jour = form.get("date", "")
    return _terminer(conn, form, "planifie_lot", lambda: planifier_lot(conn, ids, jour, durees))


ROUTES_TABLEAU = [
    ("GET", r"^/suivi$", lambda c, q, f, *g: page_suivi(c, q)),
    ("GET", r"^/tournee$", lambda c, q, f, *g: page_tournee(c, q)),
    ("POST", r"^/tournee/planifier$", lambda c, q, f, *g: action_planifier_lot(c, f)),
    ("POST", r"^/action/statut$", lambda c, q, f, *g: action_statut(c, f)),
    ("POST", r"^/action/facturer$", lambda c, q, f, *g: action_facturer(c, f)),
    ("POST", r"^/action/encaisser$", lambda c, q, f, *g: action_encaisser(c, f)),
    ("POST", r"^/action/retirer$", lambda c, q, f, *g: action_retirer(c, f)),
    ("POST", r"^/action/deplacer$", lambda c, q, f, *g: action_deplacer(c, f)),
]
