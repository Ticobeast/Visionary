"""Composants partagés par le calendrier, le suivi et les tournées : lecture des chantiers, cellules de tableau,
formulaires rapides (statut, facturation, encaissement) et fenêtre de confirmation « Terminé »."""
import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from noyau import (MODES, SEUIL_SURVEILLER, SEUIL_URGENT, STATUTS, cle, jours_attente)
from vue import (LIBELLES_MODE, LIBELLES_PAIEMENT, LIBELLES_STATUT, argent, badge, esc, heures, lien_maps)

JOURNEE_H = 8.0   # repère d'une journée de travail (heures), pour voir ce qu'il reste de place

VUES = [
    ("aplanifier", "À planifier"),
    ("enattente", "En attente"),
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
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

COLONNES_VUE = ["chantier_id", "client_id", "client_nom_complet", "telephone", "adresse", "ville", "code_postal",
                "adresse_maps", "type_libelle", "travaux_detail", "description", "statut", "statut_paiement", "solde",
                "total_ttc", "paye", "prix_ht", "date_prevue", "ordre_jour", "duree_estimee_h", "attente_depuis",
                "modalite_paiement", "date_facture", "secteur_tri"]


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
        l["secteur_tri"] = (cle(l["ville"]), (l["code_postal"] or "").replace(" ", ""))
        lignes.append(l)
    return lignes, aujourdhui


def reference_attente(l, vue):
    """Date à partir de laquelle on compte l'attente, selon l'onglet."""
    if vue in ("afacturer",):
        return l["date_prevue"] or l["attente_depuis"]
    if vue == "arecevoir":
        return l["date_facture"] or l["date_prevue"] or l["attente_depuis"]
    return l["attente_depuis"]


def dans_vue(l, vue):
    st, sp = l["statut"], l["statut_paiement"]
    return {"aplanifier": st == "a_planifier", "enattente": st == "en_attente", "soumissions": st == "soumission",
            "planifies": st == "planifie", "afacturer": sp in ("non_facture", "prix_manquant"),
            "arecevoir": sp in ("a_payer", "partiel")}[vue]


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


def form_statut(l, retour, avec_date=True):
    if l["statut"] == "termine":              # un chantier terminé ne change plus de statut
        return VERROUILLE
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


def actions_paiement(l, retour):
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
        out.append(f'<div class="doux">Règlement prévu : {esc(LIBELLES_MODE.get(l["modalite_paiement"], l["modalite_paiement"]))}</div>')
    if sp == "non_facture":
        out.append(f'<form class="mini" method="post" action="/action/facturer"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
                   f'<input type="hidden" name="retour" value="{esc(retour)}"><button type="submit" class="secondaire">Facturer</button></form>')
    if sp == "prix_manquant":
        out.append(f'<div class="doux"><a href="/chantier/{l["chantier_id"]}">Saisir le prix</a></div>')
    # on n'encaisse que ce qui est fait ou planifié (acompte) ; pas une soumission ni un chantier à planifier
    if st in ("planifie", "termine") and l["solde"] and l["solde"] > 0 and l["total_ttc"]:
        mode = mode_conseille(l["modalite_paiement"])
        options = "".join(f'<option value="{m}"{" selected" if m == mode else ""}>{esc(LIBELLES_MODE[m])}</option>' for m in MODES)
        out.append(f'<form class="mini" method="post" action="/action/encaisser"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
                   f'<input type="hidden" name="retour" value="{esc(retour)}"><input class="court" style="width:84px" name="montant" '
                   f'value="{l["solde"]:.2f}" inputmode="decimal" aria-label="Montant reçu" title="Montant reçu (taxes incluses)">'
                   f'<select name="mode" aria-label="Mode de paiement">{options}</select><button type="submit">Encaisser</button></form>')
    return "".join(out)


def cellule_client(l):
    tel = l["telephone"]
    tel_txt = f'<div class="doux">{esc(tel[2:5] + "-" + tel[5:8] + "-" + tel[8:])}</div>' if tel and len(tel) == 12 else ""
    return f'<a href="/client/{l["client_id"]}">{esc(nom_client(l))}</a>{tel_txt}'


def cellule_adresse(l):
    return (f'{lien_maps(l["adresse_maps"], l["adresse"])}<div class="doux">{esc(l["ville"])}'
            f'{" · " + esc(l["code_postal"]) if l["code_postal"] else ""}</div>')


def cellule_travaux(l):
    duree = f'<span class="total">⏱ {heures(l["duree_estimee_h"])}</span>' if l["duree_estimee_h"] else '<span class="doux">durée à estimer</span>'
    desc = f'<div class="doux">{esc(l["description"])}</div>' if l["description"] else ""
    return f'<a href="/chantier/{l["chantier_id"]}">{esc(l["travaux_detail"] or l["type_libelle"])}</a><div>{duree}</div>{desc}'


def form_statut_jour(l, retour):
    """Statut + durée estimée d'un chantier, dans la vue d'une journée (la date reste celle de la journée)."""
    if l["statut"] == "termine":
        return VERROUILLE
    options = "".join(f'<option value="{s}"{" selected" if s == l["statut"] else ""}>{esc(LIBELLES_STATUT[s])}</option>' for s in STATUTS)
    duree = f"{l['duree_estimee_h']:g}" if l["duree_estimee_h"] else ""
    return (f'<form class="mini" method="post" action="/action/statut"><input type="hidden" name="chantier_id" value="{l["chantier_id"]}">'
            f'<input type="hidden" name="retour" value="{esc(retour)}"><input type="hidden" name="date_prevue" value="{esc(l["date_prevue"])}">'
            f'<select name="statut" aria-label="Statut">{options}</select>'
            f'<input class="court" name="duree_estimee_h" value="{esc(duree)}" inputmode="decimal" placeholder="h" '
            f'title="Durée estimée en heures (2,5 = 2 h 30) : les heures de passage sont recalculées">'
            f'<button type="submit" class="secondaire">OK</button></form>')


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
            f'<div class="barre"><form method="post" action="/action/statut"><input type="hidden" name="chantier_id" value="{chantier_id}">'
            f'<input type="hidden" name="statut" value="termine"><input type="hidden" name="retour" value="{esc(retour)}">'
            f'<div style="margin-bottom:12px"><label for="duree_reelle_h">Durée réelle (heures) — reprise de la durée estimée</label>'
            f'<input id="duree_reelle_h" name="duree_reelle_h" value="{r[4] and format(r[4], "g") or ""}" inputmode="decimal"></div>'
            f'<button type="submit">Oui, passer à Terminé</button></form>'
            f'<a class="bouton secondaire" href="{esc(retour)}">Non, laisser Planifié</a></div></div></div>')
