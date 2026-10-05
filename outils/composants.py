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
                "modalite_paiement", "date_facture", "secteur", "nacelle", "debarrasser_bois", "bois_format", "secteur_tri"]


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


VERROUILLE = '<span class="badge b-termine" title="Chantier terminé : verrouillé en lecture seule">🔒 Terminé</span>'


def bouton_encaisser(l, retour):
    """« Encaisser » en un clic : le montant prévu (le solde) est affiché mais NON modifiable ; on confirme seulement.

    Un montant partiel (acompte) s'enregistre sur la page du chantier. Seuls les chantiers planifiés ou terminés s'encaissent.
    """
    if l["statut"] not in ("planifie", "termine") or not l["solde"] or l["solde"] <= 0 or not l["total_ttc"]:
        return ""
    mode = mode_conseille(l["modalite_paiement"])
    options = "".join(f'<option value="{m}"{" selected" if m == mode else ""}>{esc(LIBELLES_MODE[m])}</option>' for m in MODES)
    texte = f"Encaisser {argent(l['solde'])} ?"
    return (f'<form class="mini encaisser" method="post" action="/action/encaisser" onsubmit="return confirm({esc(repr(texte))})">'
            f'<input type="hidden" name="chantier_id" value="{l["chantier_id"]}"><input type="hidden" name="retour" value="{esc(retour)}">'
            f'<span class="doux">Montant prévu :<br><b class="nw">{argent(l["solde"])}</b></span>'
            f'<select name="mode" aria-label="Mode de paiement">{options}</select><button type="submit">Encaisser</button></form>')


def paiement_cellule(l, retour):
    """État du paiement (lecture seule) + bouton Encaisser."""
    return paiement_lecture(l) + bouton_encaisser(l, retour)


def cellule_client(l):
    tel = l["telephone"]
    tel_txt = f'<div class="doux">{esc(tel[2:5] + "-" + tel[5:8] + "-" + tel[8:])}</div>' if tel and len(tel) == 12 else ""
    return f'<a href="/client/{l["client_id"]}">{esc(nom_client(l))}</a>{tel_txt}'


def cellule_adresse(l):
    return (f'{lien_maps(l["adresse_maps"], l["adresse"])}<div class="doux">{esc(l["secteur_nom"])}'
            f'{" · " + esc(l["code_postal"]) if l["code_postal"] else ""}</div>')


def cellule_travaux(l):
    duree = f'<span class="total">⏱ {heures(l["duree_estimee_h"])}</span>' if l["duree_estimee_h"] else '<span class="doux">durée à estimer</span>'
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


def paiement_lecture(l):
    """État du paiement en lecture seule : statut, reçu et solde (aucun formulaire)."""
    sp = l["statut_paiement"]
    out = []
    if sp not in ("sans_objet", "a_venir"):
        out.append(badge(sp, LIBELLES_PAIEMENT[sp]))
    if l["paye"]:
        out.append(f'<div class="doux">reçu {argent(l["paye"])}'
                   + (f' · solde <b>{argent(l["solde"])}</b>' if l["solde"] and l["solde"] > 0 else "") + "</div>")
    if l["modalite_paiement"] and sp not in ("paye", "sans_objet"):
        out.append(f'<div class="doux">Règlement prévu : {esc(LIBELLES_MODE.get(l["modalite_paiement"], l["modalite_paiement"]))}</div>')
    return "".join(out) or '<span class="doux">—</span>'


def fenetre_terminer(conn, chantier_id, chemin, query):
    """Fenêtre de confirmation affichée après un encaissement sur un chantier « Planifié ».

    Vide si le chantier n'existe plus ou n'est plus « Planifié » (lien périmé).
    """
    r = conn.execute("SELECT statut, client_nom_complet, travaux_detail, type_libelle, duree_estimee_h FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    if r is None or r[0] != "planifie":
        return ""
    reste = {k: v for k, v in query.items() if k not in ("terminer", "ok", "err")}
    retour = chemin + ("?" + urlencode(reste) if reste else "")
    return (f'<div class="modale" role="dialog" aria-modal="true" aria-labelledby="modale-titre"><div class="modale-carte">'
            f'<h2 id="modale-titre">Paiement enregistré</h2><p><b>{esc(r[1])}</b> — {esc(r[2] or r[3])}</p>'
            f'<p class="question">Voulez-vous passer ce chantier au statut &quot;Terminé&quot; ?</p>'
            f'<p class="doux">Une fois terminé, le chantier est verrouillé en lecture seule.</p>'
            f'<div class="barre"><form method="post" action="/action/terminer"><input type="hidden" name="chantier_id" value="{chantier_id}">'
            f'<input type="hidden" name="retour" value="{esc(retour)}">'
            f'<div style="margin-bottom:12px"><label for="duree_reelle_h">Durée réelle (heures) — reprise de la durée estimée</label>'
            f'<input id="duree_reelle_h" name="duree_reelle_h" value="{r[4] and format(r[4], "g") or ""}" inputmode="decimal"></div>'
            f'<button type="submit">Oui, passer à Terminé</button></form>'
            f'<a class="bouton secondaire" href="{esc(retour)}">Non, laisser Planifié</a></div></div></div>')
