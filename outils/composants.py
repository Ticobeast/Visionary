"""Composants partagés par le tableau de bord (calendrier) et la page Journée : lecture des chantiers, cellules de tableau,
formulaires rapides (statut, facturation, encaissement) et fenêtre de confirmation « Terminé »."""
import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from noyau import (MODES, SEUIL_SURVEILLER, SEUIL_URGENT, STATUTS, cle, jours_attente)
from vue import (LIBELLES_MODE, LIBELLES_PAIEMENT, LIBELLES_STATUT, argent, badge, esc, heures, lien_maps, puces_options)

JOURNEE_H = 8.0   # repère d'une journée de travail (heures), pour voir ce qu'il reste de place

TRIS = [("attente", "Délai d'attente (le plus long d'abord)"), ("secteur", "Secteur (ville, code postal)"),
        ("duree", "Durée (la plus longue d'abord)")]
FILTRES_ATTENTE = [("", "Tous les délais"), ("urgente", f"Urgents (plus de {SEUIL_URGENT} j)"),
                   ("surveiller", f"À surveiller ({SEUIL_SURVEILLER} à {SEUIL_URGENT} j)"),
                   ("normale", f"Normaux (moins de {SEUIL_SURVEILLER} j)")]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

COLONNES_VUE = ["chantier_id", "client_id", "client_nom_complet", "telephone", "adresse", "ville", "code_postal",
                "adresse_maps", "type_libelle", "travaux_detail", "description", "statut", "statut_paiement", "solde",
                "total_ttc", "paye", "prix_ht", "date_prevue", "ordre_jour", "duree_estimee_h", "attente_depuis",
                "modalite_paiement", "secteur", "nacelle", "debarrasser_bois", "bois_format", "secteur_tri"]


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------
def lignes_vue(conn, condition="1=1", params=()):
    """Chantiers de la vue sous forme de dicts, avec le délai d'attente calculé."""
    colonnes = ", ".join(c for c in COLONNES_VUE if c != "secteur_tri")
    cur = conn.execute(f"SELECT {colonnes} FROM v_chantiers WHERE {condition}", params)
    noms = [d[0] for d in cur.description]
    aujourdhui = datetime.date.today()
    lignes = []
    for r in cur.fetchall():
        l = dict(zip(noms, r))
        l["secteur_nom"] = l["secteur"] or l["ville"]
        l["secteur_tri"] = (cle(l["secteur_nom"]), (l["code_postal"] or "").replace(" ", ""))
        lignes.append(l)
    return lignes, aujourdhui


def nom_client(l):
    return l["client_nom_complet"]


def retour_valide(retour, defaut="/"):
    """N'accepte qu'un chemin local (jamais une adresse externe)."""
    if not retour or not retour.startswith("/") or retour.startswith("//") or "\\" in retour:
        return defaut
    return retour


def avec_params(url, **params):
    u = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k not in params]
    q += [(k, v) for k, v in params.items() if v is not None]
    return urlunsplit(("", "", u.path or "/", urlencode(q), ""))


# ---------------------------------------------------------------------------
# Composants
# ---------------------------------------------------------------------------
def mode_conseille(modalite):
    """Mode de règlement prévu du chantier (choix unique) ; Interac à défaut."""
    return modalite if modalite in MODES else "interac"


VERROUILLE = '<span class="badge b-termine" title="Chantier terminé : verrouillé en lecture seule">Terminé</span>'


def cellule_client(l):
    tel = l["telephone"]
    tel_txt = f'<div class="doux">{esc(tel[2:5] + "-" + tel[5:8] + "-" + tel[8:])}</div>' if tel and len(tel) == 12 else ""
    return f'<a href="/client/{l["client_id"]}">{esc(nom_client(l))}</a>{tel_txt}'


def cellule_adresse(l):
    return (f'{lien_maps(l["adresse_maps"], l["adresse"])}<div class="doux">{esc(l["secteur_nom"])}'
            f'{" · " + esc(l["code_postal"]) if l["code_postal"] else ""}</div>')


def cellule_travaux(l):
    duree = f'<span class="total">Durée {heures(l["duree_estimee_h"])}</span>' if l["duree_estimee_h"] else '<span class="doux">durée à estimer</span>'
    desc = f'<div class="doux">{esc(l["description"])}</div>' if l["description"] else ""
    options = puces_options(l["nacelle"], l["debarrasser_bois"], l["bois_format"])
    return (f'<a href="/chantier/{l["chantier_id"]}">{esc(l["travaux_detail"] or l["type_libelle"])}</a><div>{duree}</div>'
            f'{f"<div>{options}</div>" if options else ""}{desc}')


def cellule_montant(l):
    """Valeur du travail, bien visible à droite : total taxes incluses (le prix avant taxes en dessous)."""
    if l["total_ttc"] is None or not l["total_ttc"]:
        return '<div class="montant"><small>prix à saisir</small></div>'
    avant = f'<small>{argent(l["prix_ht"])} avant taxes</small>' if l["prix_ht"] is not None and abs(l["total_ttc"] - l["prix_ht"]) > 0.004 else ""
    return f'<div class="montant">{argent(l["total_ttc"])}{avant}</div>'


def lien_facture(chantier_id, texte="Facture", classe=""):
    """Raccourci vers la facture en PDF (nouvel onglet) : la soumission acceptée devient une facture."""
    return (f'<a class="bouton secondaire{" " + classe if classe else ""}" href="/facture/{chantier_id}/pdf" target="_blank" rel="noopener" '
            f'title="Ouvrir la facture en PDF (nouvel onglet)">{esc(texte)}</a>')


def liens_pdf(chantier_id, document="soumission"):
    """Un seul bouton, au nom du document (« Soumission » ou « Facture ») : ouvre le PDF dans un nouvel onglet (on l'y imprime ou l'enregistre)."""
    nom, titre = ("Facture", "la facture") if document == "facture" else ("Soumission", "la soumission")
    return (f'<a class="bouton secondaire lien-pdf" href="/{document}/{chantier_id}/pdf" target="_blank" rel="noopener" '
            f'title="Ouvrir {titre} en PDF (nouvel onglet)">{nom}</a>')


def bouton_terminer(l, retour):
    """« Terminer » sur un chantier planifié : ouvre une fenêtre de confirmation (avec « payé ou pas »).
    À côté, le raccourci « Facture » (PDF) : sur place, on remet la facture avant ou après avoir confirmé."""
    if l["statut"] == "planifie":
        return (f'<span class="groupe-actions"><a class="bouton" href="{esc(avec_params(retour, terminer=l["chantier_id"], ok=None, err=None))}">Terminer</a>'
                + lien_facture(l["chantier_id"], classe="facture-pc") + "</span>")
    if l["statut"] == "termine":
        return '<span class="groupe-actions"><span class="doux">Terminé</span>' + lien_facture(l["chantier_id"], classe="facture-pc") + "</span>"
    return ""


def fenetre_terminer(conn, chantier_id, chemin, query):
    """Fenêtre « Terminer ce chantier » : confirmation, et le client a-t-il payé ou pas.

    Une fois terminé, le chantier est verrouillé et le client est considéré comme facturé. Vide si le chantier n'existe plus
    ou n'est plus « Planifié » (lien périmé).
    """
    r = conn.execute("SELECT statut, client_nom_complet, travaux_detail, type_libelle, duree_estimee_h, solde, prix_ht, modalite_paiement"
                     " FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    if r is None or r[0] != "planifie":
        return ""
    _, nom, detail, type_, duree, solde, prix, modalite = r
    reste = {k: v for k, v in query.items() if k not in ("terminer", "ok", "err")}
    retour = chemin + ("?" + urlencode(reste) if reste else "")
    if prix is not None and solde and solde > 0:
        mode = mode_conseille(modalite)
        options = "".join(f'<option value="{m}"{" selected" if m == mode else ""}>{esc(LIBELLES_MODE[m])}</option>' for m in MODES)
        paiement = (f'<p class="question">Le client a-t-il payé ?</p>'
                    f'<p><label class="coche"><input type="radio" name="paye" value="oui"> Oui, payé en totalité : <b>{esc(argent(solde))}</b></label></p>'
                    f'<p><label class="coche"><input type="radio" name="paye" value="non" checked> Pas encore payé</label></p>'
                    f'<div style="margin-bottom:12px"><label for="mode">Mode de paiement (si payé)</label>'
                    f'<select id="mode" name="mode">{options}</select></div>')
    elif prix is None:
        paiement = '<p class="doux">Le prix n\'est pas saisi : ajoute-le sur la page du chantier pour enregistrer un paiement.</p>'
    else:
        paiement = '<p class="doux">Ce chantier est déjà payé en totalité.</p>'
    return (f'<div class="modale" role="dialog" aria-modal="true" aria-labelledby="modale-titre"><div class="modale-carte">'
            f'<h2 id="modale-titre">Terminer ce chantier</h2><p><b>{esc(nom)}</b> : {esc(detail or type_)}</p>'
            f'<p class="question">Confirmes-tu que ce chantier est terminé ?</p>'
            f'<form method="post" action="/action/terminer"><input type="hidden" name="chantier_id" value="{chantier_id}">'
            f'<input type="hidden" name="retour" value="{esc(retour)}">{paiement}'
            f'<div style="margin-bottom:12px"><label for="duree_reelle_h">Durée réelle (heures), reprise de la durée estimée</label>'
            f'<input id="duree_reelle_h" name="duree_reelle_h" value="{duree and format(duree, "g") or ""}" inputmode="decimal"></div>'
            f'<p class="doux">Une fois terminé, le chantier est verrouillé en lecture seule et le client est considéré comme facturé.</p>'
            f'<div class="barre"><button type="submit">Oui, il est terminé</button>'
            f'{lien_facture(chantier_id, "Facture (PDF)")}'
            f'<a class="bouton secondaire" href="{esc(retour)}">Annuler</a></div></form></div></div>')
