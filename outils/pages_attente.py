"""Mettre en attente : un chantier accepté qu'on ne peut pas faire tout de suite (saison, client pas prêt...).

Deux façons d'arriver ici :
  * le troisième bouton d'une SOUMISSION (« En attente ») : le client a dit oui, mais pas maintenant. La soumission doit être complète,
    comme pour l'accepter ; elle devient un chantier accepté, « En attente » ;
  * le bouton « Mettre en attente » d'un chantier « À planifier ».
Un chantier en attente n'est plus proposé dans la Journée. Il redevient « À planifier » tout seul à la date de reprise choisie, ou reste
en attente jusqu'à nouvel ordre ; « Sortir de l'attente » le remet à planifier tout de suite.
"""
import datetime
import sqlite3
from urllib.parse import quote

from composants import avec_params, retour_valide
from noyau import decaler_mois, manques_pour_accepter, mettre_en_attente, sortir_de_l_attente, transaction
from pages_chantier import _genre_et_statut, valeurs_chantier
from vue import argent, esc, gabarit, redirection, texte_attente, url_fiche

RACCOURCIS_DATE = (("Dans 1 mois", 1), ("Dans 2 mois", 2), ("Dans 3 mois", 3), ("Dans 6 mois", 6))


def _introuvable():
    return gabarit("Introuvable", '<h1>Fiche introuvable</h1><p><a href="/chantiers">Retour aux chantiers</a> · <a href="/soumissions">Retour aux soumissions</a></p>'), 404


def _vers_completer(i, retour):
    """Une soumission incomplète ne peut pas être mise en attente : on demande d'abord ce qui manque (comme pour l'accepter)."""
    return redirection(f"/soumission/{i}/completer?pour=attente&retour={quote(retour, safe='')}")


def _refus(i, genre, statut):
    """Message quand la mise en attente n'a pas de sens pour cette fiche (None si elle est permise)."""
    if statut in ("soumission", "a_planifier", "en_attente"):
        return None
    if statut == "planifie":
        return "ce chantier est placé dans une journée : retire-le d'abord de sa journée (page Journée), puis mets-le en attente"
    return "seul un chantier « À planifier » ou une soumission complète peut être mis en attente"


def page_attente(conn, i, query, erreurs=(), saisie=None):
    if valeurs_chantier(conn, i) is None:
        return _introuvable()
    genre, statut = _genre_et_statut(conn, i)
    retour = retour_valide(query.get("retour"), f"/chantier/{i}")
    refus = _refus(i, genre, statut)
    if refus:
        return redirection(avec_params(url_fiche(i, genre), err=refus, ok=None))
    if statut == "soumission" and manques_pour_accepter(conn, i):
        return _vers_completer(i, retour)
    nom, travaux, total, reprise = conn.execute(
        "SELECT client_nom_complet, travaux_detail, total_ttc, reprise_le FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone()
    deja = statut == "en_attente"
    saisie = saisie or {}
    choix = saisie.get("choix") or ("indefini" if deja and not reprise and not query.get("reprise_le") else "date")
    prefixe = "soumission" if genre == "soumission" else "chantier"
    if "reprise_le" in saisie:
        date_choisie = saisie["reprise_le"]
    else:
        date_choisie = query.get("reprise_le") or reprise or ""
    demain = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    rapides = " · ".join(
        f'<a href="/{prefixe}/{i}/attente?retour={quote(retour, safe="")}&amp;reprise_le={decaler_mois(datetime.date.today(), n).isoformat()}">{esc(t)}</a>'
        for t, n in RACCOURCIS_DATE)
    err = ('<div class="erreurs"><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>") if erreurs else ""
    if genre == "soumission":
        intro = ("Le client a accepté, mais on ne fera pas le travail tout de suite (par exemple, pas de taille de haie en avril). La soumission devient un "
                 "<b>chantier accepté, en attente</b> : il est dans Chantiers et n'est plus proposé dans la Journée.")
    else:
        intro = "Un chantier en attente n'est plus proposé dans la Journée."
    etat = (f'<p class="doux">Actuellement : en attente, <b>{esc(texte_attente(reprise))}</b>.</p>' if deja else "")
    sortir = ""
    if deja:
        sortir = (f'<form method="post" action="/chantier/{i}/reprendre" style="margin-top:12px"><input type="hidden" name="retour" value="{esc(retour)}">'
                  '<button type="submit" class="secondaire">Sortir de l\'attente maintenant</button></form>')
    titre = "Changer l'attente" if deja else "Mettre en attente"
    contenu = (f'<h1>{titre}</h1>{err}'
               f'<div class="carte"><h2>{esc(nom)}</h2><p>{esc(travaux) if travaux else "travaux à préciser"}'
               f'{" · " + esc(argent(total)) if total else ""}</p><p>{intro}</p>{etat}</div>'
               f'<form method="post" action="/{prefixe}/{i}/attente"><input type="hidden" name="retour" value="{esc(retour)}">'
               '<div class="carte"><h2>Jusqu\'à quand ?</h2>'
               '<div class="barre"><label class="coche"><input type="radio" name="choix" value="date" id="choix-date"'
               f'{" checked" if choix == "date" else ""}> Jusqu\'au</label>'
               f'<input type="date" name="reprise_le" value="{esc(date_choisie)}" min="{demain}" style="max-width:190px" aria-label="Date de reprise" '
               'onchange="document.getElementById(\'choix-date\').checked=true" oninput="document.getElementById(\'choix-date\').checked=true"></div>'
               f'<p class="doux" style="margin:8px 0 14px">Il redevient « À planifier » ce jour-là, tout seul. Rapide : {rapides}</p>'
               '<label class="coche"><input type="radio" name="choix" value="indefini"'
               f'{" checked" if choix == "indefini" else ""}> Jusqu\'à nouvel ordre</label>'
               '<p class="doux" style="margin:8px 0 0">Il reste en attente tant que tu ne l\'as pas sorti toi-même (bouton « Sortir de l\'attente » sur sa fiche).</p></div>'
               f'<div class="barre"><button type="submit">{"Enregistrer" if deja else "Mettre en attente"}</button>'
               f'<a class="bouton secondaire" href="{esc(retour)}">Annuler</a></div></form>{sortir}')
    return gabarit("Mettre en attente", contenu, section="soumissions" if genre == "soumission" else "chantiers")


def post_attente(conn, i, form):
    if valeurs_chantier(conn, i) is None:
        return _introuvable()
    genre, statut = _genre_et_statut(conn, i)
    retour = retour_valide(form.get("retour"), f"/chantier/{i}")
    refus = _refus(i, genre, statut)
    if refus:
        return redirection(avec_params(url_fiche(i, genre), err=refus, ok=None))
    if statut == "soumission" and manques_pour_accepter(conn, i):
        return _vers_completer(i, retour)
    choix = form.get("choix", "date")
    reprise = (form.get("reprise_le") or "").strip() if choix == "date" else ""
    erreurs = []
    if choix not in ("date", "indefini"):
        erreurs.append("choisis « jusqu'au… » ou « jusqu'à nouvel ordre »")
    elif choix == "date" and not reprise:
        erreurs.append("choisis la date de reprise, ou « jusqu'à nouvel ordre »")
    if not erreurs:
        try:
            with transaction(conn):
                erreurs = mettre_en_attente(conn, i, reprise or None)
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return page_attente(conn, i, {"retour": retour}, erreurs, saisie={"choix": choix, "reprise_le": reprise})
    return redirection(avec_params(retour, ok="attente_modifiee" if statut == "en_attente" else "mis_en_attente", err=None))


def post_reprendre(conn, i, form):
    if valeurs_chantier(conn, i) is None:
        return _introuvable()
    retour = retour_valide(form.get("retour"), f"/chantier/{i}")
    try:
        with transaction(conn):
            erreurs = sortir_de_l_attente(conn, i)
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return redirection(avec_params(retour, err=" ; ".join(erreurs)[:300], ok=None))
    return redirection(avec_params(retour, ok="sorti_attente", err=None))


ROUTES_ATTENTE = [
    ("GET", r"^/(?:soumission|chantier)/(\d+)/attente$", lambda c, q, f, i: page_attente(c, int(i), q)),
    ("POST", r"^/(?:soumission|chantier)/(\d+)/attente$", lambda c, q, f, i: post_attente(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/reprendre$", lambda c, q, f, i: post_reprendre(c, int(i), f)),
]
