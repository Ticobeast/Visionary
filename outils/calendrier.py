"""Tableau de bord : calendrier des journées planifiées + déroulement (en lecture seule) de la journée choisie.

Le calendrier (mois) montre, pour chaque jour, le nombre de chantiers et les heures prévues. Un clic sur une
date affiche le déroulement de la journée : chantiers dans leur ordre de passage avec heures de début et de fin
calculées automatiquement (début 7 h 30, dîner 12 h 00 - 12 h 30), temps et montant de chaque chantier, totaux de la
journée. Le tableau de bord sert à VOIR : on n'y modifie ni statut, ni durée, ni ordre (cela se fait dans la page
Journée) ; on peut seulement retirer un chantier de la journée. `panneau_jour(gestion=True)` sert la page Journée.
"""
import calendar
import datetime
from urllib.parse import urlencode

from composants import (JOURNEE_H, JOURS, MOIS, bouton_terminer, cellule_adresse, cellule_client, cellule_montant, cellule_travaux,
                        lignes_vue)
from noyau import DEBUT_JOURNEE, DINER_DEBUT, DINER_FIN, calculer_horaire, heure_texte, ids_de_la_journee
from vue import argent, argent_entier, esc, gabarit, heures


def _jour_valide(texte):
    try:
        return datetime.date.fromisoformat(texte).isoformat() if texte else None
    except ValueError:
        return None


def _mois_valide(texte):
    try:
        annee, mois = (int(x) for x in (texte or "").split("-"))
        return datetime.date(annee, mois, 1)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Déroulement d'une journée
# ---------------------------------------------------------------------------
def panneau_jour(conn, jour, retour, gestion=False):
    """Journée complète : résumé (durée et montant totaux), chantiers dans l'ordre de passage avec heures calculées.

    Ni statut ni paiement ici : le statut est automatique (jamais choisi à la main) et le paiement se règle dans la
    fenêtre « Terminer » ou sur la page du chantier.
    gestion=False (tableau de bord) : lecture seule ; seul le bouton Terminer, en bas de chaque chantier.
    gestion=True (page Journée) : boutons Terminer et Retirer, et une flèche vers le haut / vers le bas pour l'ordre.
    """
    d = datetime.date.fromisoformat(jour)
    ids = ids_de_la_journee(conn, jour)
    lignes, _ = lignes_vue(conn, "statut IN ('planifie', 'termine') AND date_prevue = ?", (jour,))
    par_id = {l["chantier_id"]: l for l in lignes}
    chantiers = [par_id[i] for i in ids if i in par_id]
    horaire = calculer_horaire([l["duree_estimee_h"] for l in chantiers])

    total_h = sum(l["duree_estimee_h"] or 0 for l in chantiers)
    total_jour = round(sum(l["total_ttc"] or 0 for l in chantiers), 2)
    sans_duree = sum(1 for l in chantiers if not l["duree_estimee_h"])
    titre = f'{JOURS[d.weekday()].capitalize()} {d.day} {MOIS[d.month - 1]} {d.year}'
    lien_gerer = (f'<a class="bouton secondaire" href="/journee?date={jour}">'
                  f'{"+ Ajouter des chantiers" if gestion else "Gérer cette journée"}</a>')
    if not chantiers:
        return (f'<div class="carte"><h2>{esc(titre)}</h2><p class="doux">Aucun chantier planifié ce jour-là.</p>'
                f'{"" if gestion else f"<div class=barre>{lien_gerer}</div>"}</div>')

    fin = horaire[-1]["fin"]
    chargee = total_h > JOURNEE_H
    resume = (f'<p class="resume-jour"><b>{len(chantiers)} chantier{"s" if len(chantiers) > 1 else ""}</b> · durée totale <span class="total">{heures(total_h) if total_h else "inconnue"}</span>'
              f' · début <b>{heure_texte(DEBUT_JOURNEE)}</b> · fin prévue <b>{heure_texte(fin)}</b>'
              + (f' <span class="attente a-urgente">journée chargée (plus de {heures(JOURNEE_H)})</span>' if chargee else "")
              + "</p>"
              f'<p class="total-jour">Total de la journée : <span class="total">{esc(argent(total_jour))}</span> <span class="doux">(taxes incluses)</span></p>'
              f'<p class="doux note-heures">Heures calculées d\'après l\'ordre et les durées estimées ; dîner {heure_texte(DINER_DEBUT)} - {heure_texte(DINER_FIN)} ; trajets non comptés.'
              + (f' <b>Attention : {sans_duree} chantier{"s" if sans_duree > 1 else ""} sans durée estimée : les heures sont approximatives.</b>' if sans_duree else "")
              + "</p>")

    colonnes = 7 if gestion else 5
    corps = ""
    for rang, (l, h) in enumerate(zip(chantiers, horaire)):
        if h["diner_avant"]:
            corps += f'<tr class="diner"><td colspan="{colonnes}">Dîner · {heure_texte(DINER_DEBUT)} - {heure_texte(DINER_FIN)}</td></tr>'
        horaire_html = f'<b class="heures">{heure_texte(h["debut"])} à {heure_texte(h["fin"])}</b>'
        if h["diner_dans"]:
            horaire_html += '<div class="doux">dîner inclus</div>'
        if h["duree_inconnue"]:
            horaire_html += '<div class="doux">durée à estimer</div>'
        coin = (f'<a class="lien-pdf-coin" href="/facture/{l["chantier_id"]}/pdf" target="_blank" rel="noopener" '
                f'title="Ouvrir la facture en PDF (nouvel onglet)">Facture</a>') if l["statut"] in ("planifie", "termine") else ""      # téléphone seulement
        base = (f'<td class="c-heures">{horaire_html}{coin}</td><td class="c-client">{cellule_client(l)}</td><td class="c-adresse">{cellule_adresse(l)}</td>'
                f'<td class="col-travaux c-travaux">{cellule_travaux(l)}</td>')
        if not gestion:
            # tableau de bord : le chantier, puis en bas son bouton Terminer (rien d'autre)
            corps += (f'<tr class="sans-bas">{base}<td class="c-montant">{cellule_montant(l)}</td></tr>'
                      f'<tr class="ligne-actions"><td colspan="{colonnes}">{bouton_terminer(l, retour)}</td></tr>')
            continue
        actions = bouton_terminer(l, retour)
        if l["statut"] == "planifie":
            actions += (f'<form class="mini" method="post" action="/action/retirer"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
                        f'<input type="hidden" name="retour" value="{esc(retour)}"><button type="submit" class="secondaire" '
                        f'title="Remettre dans « À planifier »">Retirer</button></form>')
        fleche = (f'<form class="mini" method="post" action="/action/deplacer"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
                  f'<input type="hidden" name="retour" value="{esc(retour)}"><input type="hidden" name="sens" value="%s">'
                  f'<button type="submit" class="secondaire fleche" title="%s" aria-label="%s" %s>%s</button></form>')
        fleches = (fleche % ("haut", "Monter", "Monter", "disabled" if rang == 0 else "", "&#9650;")
                   + fleche % ("bas", "Descendre", "Descendre", "disabled" if rang == len(chantiers) - 1 else "", "&#9660;"))
        corps += (f'<tr><td class="col-ordre"><div class="fleches">{fleches}</div><div class="doux">n° {rang + 1}</div></td>{base}'
                  f'<td class="col-actions"><div class="actions-ligne">{actions}</div></td><td class="c-montant">{cellule_montant(l)}</td></tr>')
    if gestion:
        entetes = '<th>Ordre</th><th>Heures</th><th>Client</th><th>Adresse</th><th>Travaux · durée</th><th></th><th class="droite">Montant</th>'
    else:
        entetes = '<th>Heures</th><th>Client</th><th>Adresse</th><th>Travaux · durée</th><th class="droite">Montant</th>'
    table = (f'<div class="liste-defile"><table class="tableau jour{" gestion" if gestion else ""}"><thead><tr>{entetes}</tr></thead><tbody>{corps}</tbody></table></div>')
    lien_pdf = (f'<a class="bouton" href="/journee.pdf?date={jour}" download title="Toute la journée, avec les détails de chaque chantier">'
                f'Télécharger la journée (PDF)</a>')
    pied = "" if gestion else f'<div class="barre pied-jour" style="margin-top:12px">{lien_gerer}{lien_pdf}</div>'
    return f'<div class="carte"><h2>{esc(titre)}</h2>{resume}{table}{pied}</div>'


# ---------------------------------------------------------------------------
# Calendrier du mois
# ---------------------------------------------------------------------------
def _grille(conn, premier, selection, aujourdhui):
    nb_jours = calendar.monthrange(premier.year, premier.month)[1]
    semaines = -(-(premier.weekday() + nb_jours) // 7)
    debut = premier - datetime.timedelta(days=premier.weekday())
    fin = debut + datetime.timedelta(days=semaines * 7 - 1)
    donnees = {r[0]: r[1:] for r in conn.execute(
        "SELECT date_prevue, count(*), COALESCE(SUM(duree_estimee_h), 0), SUM(statut = 'planifie'), SUM(duree_estimee_h IS NULL),"
        " ROUND(COALESCE(SUM(total_ttc), 0), 2)"
        " FROM v_chantiers WHERE statut IN ('planifie', 'termine') AND date_prevue BETWEEN ? AND ? GROUP BY date_prevue",
        (debut.isoformat(), fin.isoformat()))}
    entetes = "".join(f'<div class="cal-tete">{j[:3]}.</div>' for j in JOURS)
    cases = ""
    for i in range(semaines * 7):
        j = debut + datetime.timedelta(days=i)
        iso = j.isoformat()
        n, h, planifies, sans, montant = donnees.get(iso, (0, 0, 0, 0, 0))
        classes = ["cal-jour"]
        if j.month != premier.month:
            classes.append("autre-mois")
        if j.weekday() >= 5:
            classes.append("weekend")
        if iso == aujourdhui.isoformat():
            classes.append("aujourdhui")
        if iso == selection:
            classes.append("selection")
        info = ""
        if n:
            classes.append("occupe")
            if h > JOURNEE_H:
                classes.append("chargee")
            info = (f'<span class="cal-info"><b>{n} chantier{"s" if n > 1 else ""}</b>'
                    f'<span class="cal-ligne">Temps total : {heures(h) if h else "?"}</span>'
                    f'<span class="cal-ligne">Montant total : <span class="nw">{esc(argent_entier(montant))}</span></span></span>')
            if planifies and j < aujourdhui:
                classes.append("a-cloturer")
                info += '<span class="cal-alerte">à clôturer</span>'
        mois_lien = f"{j.year}-{j.month:02d}"
        cases += (f'<a class="{" ".join(classes)}" href="/?{urlencode({"date": iso, "mois": mois_lien})}" '
                  f'aria-label="{j.day} {MOIS[j.month - 1]}{f", {n} chantier(s)" if n else ""}"><span class="cal-n">{j.day}</span>{info}</a>')
    precedent = (premier - datetime.timedelta(days=1)).replace(day=1)
    suivant = (premier + datetime.timedelta(days=32)).replace(day=1)

    def lien(m):
        return "/?" + urlencode({"mois": f"{m.year}-{m.month:02d}", "date": selection})
    nav = (f'<div class="cal-nav"><a class="bouton secondaire" href="{lien(precedent)}" aria-label="Mois précédent">Précédent</a>'
           f'<h2>{MOIS[premier.month - 1].capitalize()} {premier.year}</h2>'
           f'<a class="bouton secondaire" href="{lien(suivant)}" aria-label="Mois suivant">Suivant</a>'
           f'<a class="bouton secondaire" href="/">Aujourd\'hui</a></div>')
    return f'<div class="carte">{nav}<div class="cal-grille">{entetes}{cases}</div></div>'


def page_calendrier(conn, query):
    aujourdhui = datetime.date.today()
    jour = _jour_valide(query.get("date")) or aujourdhui.isoformat()
    d = datetime.date.fromisoformat(jour)
    premier = _mois_valide(query.get("mois")) or d.replace(day=1)
    mois_code = f"{premier.year}-{premier.month:02d}"
    retour = "/?" + urlencode({"date": jour, "mois": mois_code})
    contenu = (f'<h1>Tableau de bord</h1>{_grille(conn, premier, jour, aujourdhui)}'
               f'{panneau_jour(conn, jour, retour)}')
    return gabarit("Tableau de bord", contenu, query.get("ok"), query.get("err"), large=True)
