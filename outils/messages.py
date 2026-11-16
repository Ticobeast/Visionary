"""Textos et courriels préremplis pour le client (rappel de la visite, suivi d'une soumission, rappel de paiement).

Rien ne part tout seul : le bouton ouvre l'application Messages (ou Courriel) du téléphone avec le texte déjà écrit ;
on le relit, on le corrige au besoin, et on appuie sur Envoyer. Aucun service à payer, rien ne sort du programme.

Le message proposé dépend de la fiche :
- soumission en cours                          -> suivi de la soumission ;
- chantier planifié (aujourd'hui ou plus tard) -> rappel de la visite (jour, avant-midi ou après-midi) ;
- chantier terminé avec un solde à payer       -> rappel de paiement (montants : administrateur seulement).
Le client a refusé les rappels par texto (case de sa fiche) : pas de bouton Texto, le courriel reste offert.
"""
import datetime
from urllib.parse import quote

import entreprise
from noyau import DINER_DEBUT, calculer_horaire, ids_de_la_journee
from vue import argent, esc

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
VOYELLES = "aeiouyéèêàâîôûh"

TITRES = {"suivi": "Suivi de la soumission", "rappel": "Rappel de la visite", "paiement": "Rappel de paiement"}
SUJETS = {"suivi": "Suivi de votre soumission", "rappel": "Rappel de notre visite", "paiement": "Rappel de paiement"}


def _travaux(type_libelle):
    """« Taille de haie » -> « les travaux de taille de haie » ; « Émondage + Essouchement » -> « les travaux d'émondage et
    d'essouchement ». Sans type : « vos travaux »."""
    if not type_libelle:
        return "vos travaux"
    morceaux = [t.strip().lower() for t in type_libelle.split("+") if t.strip()]
    avec_de = ["d'" + t if t[0] in VOYELLES else "de " + t for t in morceaux]
    return "les travaux " + (", ".join(avec_de[:-1]) + " et " + avec_de[-1] if len(avec_de) > 1 else avec_de[0])


def _date_texte(jour, aujourdhui):
    """« demain, mardi 17 novembre » ; « aujourd'hui » ; « le jeudi 19 novembre »."""
    d = datetime.date.fromisoformat(jour)
    date = f"{JOURS[d.weekday()]} {d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]}"
    if d == aujourdhui:
        return "aujourd'hui"
    if d == aujourdhui + datetime.timedelta(days=1):
        return "demain, " + date
    return "le " + date


def _moment(conn, chantier_id, jour):
    """« en avant-midi » ou « en après-midi », d'après l'heure de début calculée dans la journée (trajets non comptés :
    on reste volontairement vague)."""
    ids = ids_de_la_journee(conn, jour)
    if chantier_id not in ids:
        return ""
    durees = {i: d for i, d in conn.execute(
        f"SELECT id, duree_estimee_h FROM chantiers WHERE id IN ({','.join('?' * len(ids))})", ids)}
    debut = calculer_horaire([durees[i] for i in ids])[ids.index(chantier_id)]["debut"]
    return "en avant-midi" if debut < DINER_DEBUT else "en après-midi"


def _bonjour(prenom):
    return f"Bonjour {prenom.strip()}," if prenom and prenom.strip() else "Bonjour,"


def message(conn, chantier_id, finances=False, aujourdhui=None):
    """Le message proposé pour cette fiche : {"sorte", "titre", "sujet", "texte", "bonjour", "corps", "telephone", "courriel",
    "texto_ok"},
    ou None (rien à proposer : à planifier, en attente, annulé, refusé, payé...).
    `finances` : le compte connecté voit les montants (sinon, pas de rappel de paiement)."""
    r = conn.execute("SELECT genre, statut, prenom, telephone, courriel, sms_ok, type_libelle, date_prevue, total_ttc, solde,"
                     " modalite_paiement FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    if r is None:
        return None
    genre, statut, prenom, tel, courriel, sms_ok, type_libelle, jour, total, solde, modalite = r
    aujourdhui = aujourdhui or datetime.date.today()
    tel = tel if tel and len(tel) == 12 else None
    travaux = _travaux(type_libelle)
    contact = f"Vous pouvez répondre à ce message ou appeler au {entreprise.TELEPHONE}."

    if genre == "soumission" and statut == "soumission":
        sorte = "suivi"
        prix = f" ({argent(total)} taxes incluses)" if total else ""
        corps = (f"Je fais un petit suivi de notre soumission pour {travaux}{prix}. "
                 f"Avez-vous des questions, ou souhaitez-vous aller de l'avant ? {contact}")
    elif genre == "chantier" and statut == "planifie" and jour and jour >= aujourdhui.isoformat():
        sorte = "rappel"
        moment = _moment(conn, chantier_id, jour)
        corps = (f"Petit rappel : nous passerons chez vous {_date_texte(jour, aujourdhui)}{', ' + moment if moment else ''}, "
                 f"pour {travaux}. Si ce moment ne vous convient plus, {contact[0].lower() + contact[1:]}")
    elif genre == "chantier" and statut == "termine" and finances and solde and solde > 0.004:
        sorte = "paiement"
        interac = (f" Le virement Interac peut être envoyé à {entreprise.COURRIEL}." if modalite == "interac" else "")
        corps = (f"Merci encore de nous avoir confié {travaux}. Selon nos dossiers, un solde de {argent(solde)} reste à payer.{interac} "
                 f"Si c'est déjà fait, ne tenez pas compte de ce message. Pour toute question : {entreprise.TELEPHONE}.")
    else:
        return None
    texte = f"{_bonjour(prenom)} ici {entreprise.NOM}. {corps} Merci !"
    return {"sorte": sorte, "titre": TITRES[sorte], "sujet": f"{SUJETS[sorte]} - {entreprise.NOM}", "texte": texte,
            "bonjour": _bonjour(prenom), "corps": corps,
            "telephone": tel, "courriel": courriel or None, "texto_ok": bool(tel and sms_ok)}


def url_texto(telephone, texte):
    """Lien qui ouvre Messages avec le texte prérempli. « ?&body= » : la forme comprise par l'iPhone ET par Android."""
    return f"sms:{telephone}?&body={quote(texte, safe='')}"


def url_courriel(courriel, sujet, bonjour, corps):
    """Lien qui ouvre le courriel avec le sujet et le texte (salutation, message, signature) déjà écrits."""
    corps = f"{bonjour}\n\n{corps}\n\nMerci !\n\n{entreprise.NOM}\n{entreprise.TELEPHONE}"
    return f"mailto:{quote(courriel, safe='@')}?subject={quote(sujet, safe='')}&body={quote(corps, safe='')}"


def boutons(m, classe=""):
    """Boutons « Texto » et « Courriel » d'un message (vide si le client n'a ni téléphone accepté, ni courriel)."""
    html = ""
    if m["texto_ok"]:
        html += (f'<a class="bouton secondaire{" " + classe if classe else ""}" href="{esc(url_texto(m["telephone"], m["texte"]))}" '
                 f'title="Ouvre Messages avec le texte déjà écrit : relis-le, puis envoie">Texto</a>')
    if m["courriel"]:
        html += (f'<a class="bouton secondaire{" " + classe if classe else ""}" href="{esc(url_courriel(m["courriel"], m["sujet"], m["bonjour"], m["corps"]))}" '
                 f'title="Ouvre le courriel avec le texte déjà écrit : relis-le, puis envoie">Courriel</a>')
    return html


def carte(conn, chantier_id, finances=False):
    """Carte « Message au client » d'une fiche : le message proposé, ses boutons Texto et Courriel. Vide s'il n'y a rien à proposer."""
    m = message(conn, chantier_id, finances)
    if m is None:
        return ""
    liens = boutons(m)
    if not liens:
        manque = ("Le client a refusé les textos et n'a pas de courriel." if m["telephone"]
                  else "Ajoute un téléphone ou un courriel sur la fiche du client.")
        liens = f'<p class="doux" style="margin:0">{manque}</p>'
    elif m["telephone"] and not m["texto_ok"]:
        liens += '<span class="doux">pas de textos (refusés par le client)</span>'
    return (f'<div class="carte message-client"><h2>Message au client</h2><p class="sorte-message"><b>{esc(m["titre"])}</b></p>'
            f'<p class="apercu-message">{esc(m["texte"])}</p><div class="barre">{liens}</div></div>')
