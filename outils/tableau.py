"""Page Journée (créer et gérer une journée complète) et actions rapides (statut, facturation, encaissement, ordre).

Journée (/journee) : on choisit une date, on voit son déroulement (heures calculées, ordre modifiable, statut,
paiements, temps et montant totaux), on filtre les chantiers à placer (secteur, délai d'attente, statut), on en
coche plusieurs et on les ajoute à la journée. Les durées et les prix ne se modifient pas ici : ce sont ceux du chantier.
"""
import datetime
import sqlite3
from urllib.parse import urlencode

from pathlib import Path

from calendrier import panneau_jour
from composants import (FILTRES_ATTENTE, JOURNEE_H, TRIS, avec_params, cellule_adresse, cellule_client, cellule_montant,
                        lignes_vue, nom_client, retour_valide)
from noyau import (annuler_chantier, changer_statut, cle, deplacer, jours_attente, planifier_lot, priorite, rouvrir_chantier,
                   terminer_chantier, transaction)
from pdf import journee_pdf
from vue import _BASE, badge_attente, esc, gabarit, heures, redirection


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


def action_terminer(conn, form):
    """Termine un chantier planifié ; si le client a payé (« paye = oui »), enregistre aussi l'encaissement du solde complet.
    Le chantier est alors terminé ET payé : il va dans les archives."""
    paye = form.get("paye") == "oui"
    return _terminer(conn, form, "termine_paye" if paye else "termine",
                     lambda: terminer_chantier(conn, _id(form), form.get("duree_reelle_h"), paye=paye, mode=form.get("mode")),
                     extra={"terminer": None})


def action_annuler(conn, form):
    """Annule un chantier : il disparaît de la journée et va dans les archives."""
    return _terminer(conn, form, "annule", lambda: annuler_chantier(conn, _id(form)), extra={"terminer": None})


def action_rouvrir(conn, form):
    return _terminer(conn, form, "rouvert", lambda: rouvrir_chantier(conn, _id(form)), extra={"terminer": None})


def action_retirer(conn, form):
    return _terminer(conn, form, "retire", lambda: changer_statut(conn, _id(form), "a_planifier"))


def action_deplacer(conn, form):
    return _terminer(conn, form, "deplace", lambda: deplacer(conn, _id(form), form.get("sens", "")))


# ---------------------------------------------------------------------------
# Journée
# ---------------------------------------------------------------------------
def _jour_valide(texte):
    try:
        return datetime.date.fromisoformat(texte).isoformat() if texte else None
    except ValueError:
        return None


def page_journee(conn, query):
    aujourdhui_iso = datetime.date.today().isoformat()
    demain = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    jour = _jour_valide(query.get("date")) or demain
    d = datetime.date.fromisoformat(jour)
    f_statut = query.get("statut") if query.get("statut") in ("a_planifier", "planifie") else "a_planifier"
    f_attente = query.get("attente", "")
    f_secteur = query.get("secteur", "")
    tri = query.get("tri") if query.get("tri") in dict(TRIS) else "secteur"
    toutes, aujourdhui = lignes_vue(conn, "statut IN ('a_planifier','planifie')")      # une soumission ne se planifie qu'une fois acceptée
    for l in toutes:
        l["jours"] = jours_attente(l["attente_depuis"], aujourdhui)

    retour = "/journee?" + urlencode({k: v for k, v in (("date", jour), ("statut", f_statut), ("attente", f_attente), ("secteur", f_secteur), ("tri", tri)) if v})
    precedent, suivant = (d - datetime.timedelta(days=1)).isoformat(), (d + datetime.timedelta(days=1)).isoformat()
    navigation = (f'<form class="recherche nav-jour" method="get" action="/journee"><a class="bouton secondaire nj-prec" href="/journee?date={precedent}" aria-label="Jour précédent">Précédent</a>'
                  f'<input type="date" name="date" value="{jour}" style="max-width:170px" aria-label="Journée" onchange="this.form.submit()"><button type="submit">Afficher</button>'
                  f'<a class="bouton secondaire nj-suiv" href="/journee?date={suivant}" aria-label="Jour suivant">Suivant</a>'
                  f'<a class="bouton secondaire pc-seul" href="/journee?date={demain}">Demain</a>'
                  f'<a class="bouton secondaire pc-seul" href="/?date={jour}">Voir au calendrier</a>'
                  + (f'<a class="bouton secondaire tel-seul nj-auj" href="/journee?date={aujourdhui_iso}">Aujourd\'hui</a>' if jour != aujourdhui_iso else "")
                  + '</form>')
    deja_h = sum(l["duree_estimee_h"] or 0 for l in toutes if l["statut"] == "planifie" and l["date_prevue"] == jour)
    deja_m = sum(l["total_ttc"] or 0 for l in toutes if l["statut"] == "planifie" and l["date_prevue"] == jour)
    journee = panneau_jour(conn, jour, retour, gestion=True)

    # --- les chantiers à placer
    candidats = [l for l in toutes if l["statut"] == f_statut and not (l["statut"] == "planifie" and l["date_prevue"] == jour)]
    secteurs = sorted({l["secteur_nom"] for l in candidats}, key=cle)
    if f_secteur:
        candidats = [l for l in candidats if l["secteur_nom"] == f_secteur]
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
                         (("a_planifier", "À planifier"), ("planifie", "Planifiés un autre jour (déplacer)")))
    opt_att = "".join(f'<option value="{c}"{" selected" if c == f_attente else ""}>{esc(t)}</option>' for c, t in FILTRES_ATTENTE)
    opt_sec = '<option value="">Tous les secteurs</option>' + "".join(f'<option value="{esc(s)}"{" selected" if s == f_secteur else ""}>{esc(s)}</option>' for s in secteurs)
    opt_tri = "".join(f'<option value="{c}"{" selected" if c == tri else ""}>{esc(t)}</option>' for c, t in TRIS)
    ouvert = " ouvert" if (f_statut != "a_planifier" or f_attente or f_secteur or tri != "secteur") else ""        # téléphone : repliés sous « Filtres »
    filtres = (f'<form class="recherche filtres-jour{ouvert}" method="get" action="/journee"><input type="hidden" name="date" value="{jour}">'
               '<button type="button" class="filtres-bascule" onclick="this.form.classList.toggle(\'ouvert\')">Filtres</button>'
               f'<select name="statut" aria-label="Statut">{opt_statut}</select><select name="attente" aria-label="Délai d\'attente">{opt_att}</select>'
               f'<select name="secteur" aria-label="Secteur">{opt_sec}</select><select name="tri" aria-label="Tri">{opt_tri}</select>'
               f'<button type="submit">Filtrer</button></form>')

    corps, secteur_courant = "", None
    for l in candidats:
        if tri == "secteur" and l["secteur_nom"] != secteur_courant:
            secteur_courant = l["secteur_nom"]
            dans = [x for x in candidats if x["secteur_nom"] == secteur_courant]
            h = sum(x["duree_estimee_h"] or 0 for x in dans)
            corps += (f'<tr><td colspan="6"><b>Secteur : {esc(secteur_courant)}</b> <span class="doux">{len(dans)} chantier{"s" if len(dans) > 1 else ""}'
                      f'{" · " + heures(h) if h else ""}</span></td></tr>')
        prio = priorite(l["jours"])
        autre_jour = f'<div class="doux">prévu le {esc(l["date_prevue"])}</div>' if l["statut"] == "planifie" else ""
        if l["duree_estimee_h"]:
            duree = f'<span class="total">Durée {heures(l["duree_estimee_h"])}</span>'
            case = (f'<input type="checkbox" name="sel_{l["chantier_id"]}" value="1" aria-label="Choisir {esc(nom_client(l))}">')
        else:
            duree = f'<a href="/chantier/{l["chantier_id"]}">durée à estimer : ouvrir le chantier</a>'
            case = '<input type="checkbox" disabled title="La durée estimée est obligatoire pour planifier">'
        corps += (f'<tr data-id="{l["chantier_id"]}" data-h="{l["duree_estimee_h"] or 0}" data-m="{l["total_ttc"] or 0}" class="ligne-{prio}"><td class="c-case">{case}</td>'
                  f'<td class="c-depuis">{badge_attente(l["jours"], prio)}<div class="doux">depuis {esc(l["attente_depuis"])}</div></td>'
                  f'<td class="c-client">{cellule_client(l)}</td><td class="c-adresse">{cellule_adresse(l)}</td><td class="c-travaux"><a href="/chantier/{l["chantier_id"]}">{esc(l["travaux_detail"] or l["type_libelle"])}</a>'
                  f'<div>{duree}</div>{"<div class=doux>" + esc(l["description"]) + "</div>" if l["description"] else ""}{autre_jour}</td>'
                  f'<td class="c-montant">{cellule_montant(l)}</td></tr>')
    if candidats:
        liste = (f'<form method="post" action="/journee/planifier" id="lot" data-deja="{deja_h}" data-deja-m="{deja_m}" data-cap="{JOURNEE_H:g}">'
                 f'<input type="hidden" name="date" value="{jour}"><input type="hidden" name="retour" value="{esc(retour)}">'
                 f'<div class="liste-defile"><table class="tableau candidats"><thead><tr><th></th><th>Attente</th><th>Client</th><th>Adresse</th><th>Travaux · durée</th>'
                 f'<th class="droite">Montant</th></tr></thead><tbody>{corps}</tbody></table></div>'
                 f'<div class="sel-total barre"><span id="sel">0 sélectionné</span><button type="submit">Ajouter à la journée du {jour}</button></div></form>'
                 + _SCRIPT_SELECTION)
    else:
        liste = '<div class="carte">Aucun chantier ne correspond à ces filtres.</div>'
    contenu = (f'<h1>Journée</h1>{navigation}{journee}'
               f'<h2>Chantiers à placer dans cette journée</h2>{filtres}{liste}')
    return gabarit("Journée", contenu, query.get("ok"), query.get("err"), large=True)


_SCRIPT_SELECTION = """<script>
(function(){var f=document.getElementById('lot');if(!f)return;var base=parseFloat(f.dataset.deja)||0,baseM=parseFloat(f.dataset.dejaM)||0,cap=parseFloat(f.dataset.cap)||8;
function fr(x,n){return x.toFixed(n).replace('.',',');}
function maj(){var n=0,t=0,m=0;f.querySelectorAll('tr[data-id]').forEach(function(tr){var c=tr.querySelector('input[type=checkbox]');
if(c.checked){n++;t+=parseFloat(tr.dataset.h)||0;m+=parseFloat(tr.dataset.m)||0;}});
document.getElementById('sel').textContent=n+' sélectionné'+(n>1?'s':'')+' · '+fr(t,1)+' h, '+fr(m,2)+' $, journée : '+fr(base+t,1)+' h sur '+cap+' h, '+fr(baseM+m,2)+' $';}
f.addEventListener('change',maj);maj();})();
</script>"""


def action_planifier_lot(conn, form):
    """Ajoute les chantiers cochés à la fin de la journée, dans l'ordre où ils sont affichés."""
    ids = [int(k[4:]) for k, v in form.items() if k.startswith("sel_") and k[4:].isdigit() and v]
    jour = form.get("date", "")
    return _terminer(conn, form, "planifie_lot", lambda: planifier_lot(conn, ids, jour))


def _vers_journee(c, q, f, *g):
    return redirection("/journee" + ("?" + urlencode(q) if q else ""))


def telecharger_journee(conn, query):
    """PDF de la journée (tous les détails des chantiers) : téléchargement direct, la base n'est pas modifiée."""
    try:
        jour = datetime.date.fromisoformat(query.get("date", "")).isoformat()
    except ValueError:
        jour = datetime.date.today().isoformat()
    corps = journee_pdf(conn, jour, Path(_BASE["db"]).parent if _BASE.get("db") else None)
    return ("200 OK", [("Content-Type", "application/pdf"), ("Content-Disposition", f'attachment; filename="journee-{jour}.pdf"')], corps)


ROUTES_TABLEAU = [
    ("GET", r"^/journee\.pdf$", lambda c, q, f, *g: telecharger_journee(c, q)),
    ("GET", r"^/journee$", lambda c, q, f, *g: page_journee(c, q)),
    ("POST", r"^/journee/planifier$", lambda c, q, f, *g: action_planifier_lot(c, f)),
    ("GET", r"^/tournee$", _vers_journee),                                   # anciens liens et favoris
    ("GET", r"^/suivi$", lambda c, q, f, *g: redirection("/chantiers")),     # le Suivi n'existe plus : Journée + Chantiers
    ("POST", r"^/action/terminer$", lambda c, q, f, *g: action_terminer(c, f)),
    ("POST", r"^/action/annuler$", lambda c, q, f, *g: action_annuler(c, f)),
    ("POST", r"^/action/rouvrir$", lambda c, q, f, *g: action_rouvrir(c, f)),
    ("POST", r"^/action/retirer$", lambda c, q, f, *g: action_retirer(c, f)),
    ("POST", r"^/action/deplacer$", lambda c, q, f, *g: action_deplacer(c, f)),
]
