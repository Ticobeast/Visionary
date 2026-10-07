"""Raccourcis : les pastilles en haut des pages Chantiers et Soumissions, que chaque personne choisit elle-même.

Un raccourci = un nom + des critères de la liste (statut, paiement, secteur, délai d'attente, compte, texte). La pastille montre
combien de fiches correspondent ; un clic applique les critères, un second clic les retire. On les ajoute, retire et réordonne
dans la page « Modifier les raccourcis » (chaque compte garde les siens ; sans comptes, ils sont communs). Les raccourcis
financiers (paiement) sont réservés à l'administrateur.
"""
import sqlite3
from urllib.parse import parse_qsl, quote, urlencode

from listes import ATTENTES, CRITERES, compter_chantiers, compter_soumissions, filtres_depuis
from noyau import LIBELLES_STATUT, lister_secteurs, transaction
from vue import LIBELLES_PAIEMENT, argent, esc, est_admin, gabarit, liste, redirection, utilisateur_courant

PAGES = {"chantiers": ("/chantiers", "Chantiers"), "soumissions": ("/soumissions", "Soumissions")}
VIDE = "__vide__"      # ligne invisible : « cette personne a retiré tous ses raccourcis » (sinon le départ reviendrait)
LIBELLES_ATTENTE = {"urgente": "30 jours et plus", "surveiller": "7 à 30 jours", "normale": "moins de 7 jours", "relance": "7 jours et plus"}

# (code, nom, critères, financier)
CATALOGUE = {
    "chantiers": [
        ("a_planifier", "À planifier", "statut=a_planifier", False),
        ("planifie", "Planifiés", "statut=planifie", False),
        ("en_attente", "En attente", "statut=en_attente", False),
        ("termine", "Terminés", "statut=termine", False),
        ("a_recevoir", "À recevoir", "paiement=a_recevoir", True),
        ("partiel", "Payés en partie", "paiement=partiel", True),
        ("prix_manquant", "Prix manquants", "paiement=prix_manquant", True),
        ("relance", "À planifier depuis 7 jours et plus", "attente=relance&statut=a_planifier", False),
        ("urgents", "À planifier depuis 30 jours et plus", "attente=urgente&statut=a_planifier", False),
    ],
    "soumissions": [
        ("moi", "Mes soumissions", "par=moi", False),
        ("relancer", "À relancer (7 jours et plus)", "attente=relance", False),
        ("urgentes", "Sans réponse depuis 30 jours et plus", "attente=urgente", False),
    ],
}
DEFAUTS = {("chantiers", True): ("a_recevoir", "planifie", "a_planifier"), ("chantiers", False): ("a_planifier", "planifie"),
           ("soumissions", True): ("moi", "relancer"), ("soumissions", False): ("moi", "relancer")}


CRITERES_PAGE = {"chantiers": ("statut", "paiement", "secteur", "attente", "q"), "soumissions": ("secteur", "attente", "par", "q")}
STATUTS_CHANTIER = ("a_planifier", "en_attente", "planifie", "termine", "annule")


def canonique(filtre):
    """Critères d'un raccourci sous forme de texte stable (critères connus seulement, valeurs non vides, ordre alphabétique)."""
    paires = {}
    for k, v in parse_qsl(filtre or "", keep_blank_values=False):
        v = v.strip()[:60]
        if k in CRITERES and v:
            paires[k] = v
    return urlencode(sorted(paires.items()))


def _uid():
    u = utilisateur_courant()
    return u["id"] if u else None


def _installer_defauts(conn, page, uid):
    """Au premier passage d'une personne : on enregistre ses raccourcis de départ, une seule fois même si deux appareils arrivent ensemble."""
    ouverte = conn.in_transaction                       # déjà dans une transaction (ajout, retrait...) : c'est elle qui valide
    if not ouverte:
        conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM raccourcis WHERE page = ? AND utilisateur_id IS ?", (page, uid)).fetchone() is None:
            modeles = {code: (nom, filtre) for code, nom, filtre, _ in CATALOGUE[page]}
            codes = [c for c in DEFAUTS[(page, est_admin())] if uid is not None or "par" not in dict(parse_qsl(modeles[c][1]))]
            for rang, code in enumerate(codes, 1):
                conn.execute("INSERT INTO raccourcis (utilisateur_id, page, libelle, filtre, ordre) VALUES (?, ?, ?, ?, ?)",
                             (uid, page, modeles[code][0], canonique(modeles[code][1]), rang * 10))
    except BaseException:
        if not ouverte:
            conn.execute("ROLLBACK")
        raise
    if not ouverte:
        conn.execute("COMMIT")


def lister(conn, page):
    """[(id, nom, critères)] des raccourcis de la personne ; au premier passage, ceux du départ."""
    uid = _uid()
    requete = "SELECT id, libelle, filtre FROM raccourcis WHERE page = ? AND utilisateur_id IS ? ORDER BY ordre, id"
    lignes = conn.execute(requete, (page, uid)).fetchall()
    if not lignes:
        _installer_defauts(conn, page, uid)
        lignes = conn.execute(requete, (page, uid)).fetchall()
    return [l for l in lignes if l[2] != VIDE]


def decrire(page, filtre, secteurs):
    """Les critères en français : « Statut : Planifié · Secteur : Centre-ville »."""
    f = dict(parse_qsl(filtre))
    morceaux = []
    if f.get("statut"):
        morceaux.append("Statut : " + LIBELLES_STATUT.get(f["statut"], f["statut"]))
    if f.get("paiement"):
        morceaux.append("Paiement : " + ("À recevoir" if f["paiement"] == "a_recevoir" else LIBELLES_PAIEMENT.get(f["paiement"], f["paiement"])))
    if f.get("secteur"):
        morceaux.append("Secteur : " + next((lib for code, lib, _ in secteurs if code == f["secteur"]), f["secteur"]))
    if f.get("attente"):
        morceaux.append("Attente : " + LIBELLES_ATTENTE.get(f["attente"], f["attente"]))
    if f.get("par"):
        morceaux.append("Ouverte par moi" if f["par"] == "moi" else "Ouverte par " + f["par"])
    if f.get("q"):
        morceaux.append(f"Texte : « {f['q']} »")
    return " · ".join(morceaux)


def barre(conn, page, query):
    """Les pastilles de raccourcis de la page ; celle dont les critères sont ceux de la page est surlignée."""
    admin, u = est_admin(), utilisateur_courant()
    compter = compter_chantiers if page == "chantiers" else compter_soumissions
    adresse = PAGES[page][0]
    actuels = canonique(urlencode({c: query.get(c, "") for c in CRITERES}))
    pastilles = ""
    for _, nom, filtre in lister(conn, page):
        criteres = dict(parse_qsl(filtre))
        if ("paiement" in criteres and not admin) or ("par" in criteres and not u):       # finances : administrateur ; « mes soumissions » : avec comptes
            continue
        n, somme = compter(conn, filtres_depuis(criteres, u["nom"] if u else None))
        actif = filtre == actuels
        detail = f" · {argent(somme)}" if criteres.get("paiement") in ("a_recevoir", "partiel") and somme else ""
        cible = adresse if actif else f"{adresse}?{filtre}"
        pastilles += (f'<a class="puce{" actif" if actif else ""}" href="{esc(cible)}"><b>{n}</b><span>{esc(nom)}{esc(detail)}</span></a>')
    return (f'<div class="raccourcis-bloc"><div class="raccourcis">{pastilles}</div>'
            f'<a class="modifier" href="/raccourcis?page={page}">Modifier les raccourcis</a></div>')


# ---------------------------------------------------------------------------
# Modifier les raccourcis
# ---------------------------------------------------------------------------
def _page(query_ou_form):
    page = query_ou_form.get("page", "")
    return page if page in PAGES else "chantiers"


def _critere_invalide(conn, page, filtre):
    """Premier critère qui n'a pas de sens pour cette page ou dont la valeur n'existe pas (None si tout va bien)."""
    secteurs = {code for code, _, _ in lister_secteurs(conn)}
    for k, v in parse_qsl(filtre):
        if k not in CRITERES_PAGE[page]:
            return k
        if ((k == "statut" and v not in STATUTS_CHANTIER) or (k == "paiement" and v != "a_recevoir" and v not in LIBELLES_PAIEMENT)
                or (k == "attente" and v not in ATTENTES) or (k == "secteur" and v not in secteurs) or (k == "par" and v != "moi")):
            return k
    return None


def ajouter(conn, page, nom, filtre):
    """Retourne la liste des erreurs."""
    filtre = canonique(filtre)
    if not filtre:
        return ["choisis au moins un critère (statut, secteur, délai...)"]
    if not est_admin() and "paiement" in dict(parse_qsl(filtre)):
        return ["les raccourcis sur les paiements sont réservés à l'administrateur"]
    if _critere_invalide(conn, page, filtre):
        return ["ce critère n'existe pas : choisis dans les listes proposées"]
    nom = " ".join((nom or "").split())[:40] or decrire(page, filtre, lister_secteurs(conn))
    existants = lister(conn, page)
    if any(f == filtre for _, _, f in existants):
        return ["ce raccourci existe déjà"]
    uid = _uid()
    conn.execute("DELETE FROM raccourcis WHERE page = ? AND utilisateur_id IS ? AND filtre = ?", (page, uid, VIDE))
    suivant = conn.execute("SELECT COALESCE(MAX(ordre), 0) + 10 FROM raccourcis WHERE page = ? AND utilisateur_id IS ?", (page, uid)).fetchone()[0]
    conn.execute("INSERT INTO raccourcis (utilisateur_id, page, libelle, filtre, ordre) VALUES (?, ?, ?, ?, ?)", (uid, page, nom, filtre, suivant))
    return []


def retirer(conn, page, raccourci_id):
    uid = _uid()
    n = conn.execute("DELETE FROM raccourcis WHERE id = ? AND page = ? AND utilisateur_id IS ? AND filtre <> ?", (raccourci_id, page, uid, VIDE)).rowcount
    reste = conn.execute("SELECT count(*) FROM raccourcis WHERE page = ? AND utilisateur_id IS ?", (page, uid)).fetchone()[0]
    if n and not reste:          # plus aucun : on le retient, sinon les raccourcis du départ reviendraient au prochain affichage
        conn.execute("INSERT INTO raccourcis (utilisateur_id, page, libelle, filtre, ordre) VALUES (?, ?, '-', ?, 1000)", (uid, page, VIDE))
    return [] if n else ["raccourci introuvable"]


def deplacer(conn, page, raccourci_id, sens):
    uid = _uid()
    lignes = conn.execute("SELECT id FROM raccourcis WHERE page = ? AND utilisateur_id IS ? AND filtre <> ? ORDER BY ordre, id", (page, uid, VIDE)).fetchall()
    ids = [r[0] for r in lignes]
    if raccourci_id not in ids or sens not in ("haut", "bas"):
        return ["raccourci introuvable"]
    i = ids.index(raccourci_id)
    j = i - 1 if sens == "haut" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    for rang, x in enumerate(ids, 1):
        conn.execute("UPDATE raccourcis SET ordre = ? WHERE id = ?", (rang * 10, x))
    return []


def reinitialiser(conn, page):
    conn.execute("DELETE FROM raccourcis WHERE page = ? AND utilisateur_id IS ?", (page, _uid()))
    return []


def page_raccourcis(conn, query, erreurs=(), saisie=None):
    page = _page(query)
    adresse, nom_page = PAGES[page]
    secteurs = lister_secteurs(conn)
    admin = est_admin()
    actuels = lister(conn, page)
    lignes = ""
    for rang, (id_, nom, filtre) in enumerate(actuels):
        def fleche(sens, symbole, titre, inactif):
            return (f'<form class="mini" method="post" action="/raccourcis/{id_}/deplacer"><input type="hidden" name="page" value="{page}">'
                    f'<input type="hidden" name="sens" value="{sens}"><button type="submit" class="secondaire fleche" title="{titre}" aria-label="{titre}"'
                    f'{" disabled" if inactif else ""}>{symbole}</button></form>')
        lignes += (f'<tr><td class="col-ordre"><div class="fleches">{fleche("haut", "&#9650;", "Monter", rang == 0)}{fleche("bas", "&#9660;", "Descendre", rang == len(actuels) - 1)}</div></td>'
                   f'<td><b>{esc(nom)}</b><div class="doux">{esc(decrire(page, filtre, secteurs))}</div></td>'
                   f'<td class="droite"><form class="mini" method="post" action="/raccourcis/{id_}/retirer"><input type="hidden" name="page" value="{page}">'
                   f'<button type="submit" class="secondaire">Retirer</button></form></td></tr>')
    tableau = (f'<div class="liste-defile"><table><thead><tr><th>Ordre</th><th>Raccourci</th><th></th></tr></thead><tbody>{lignes}</tbody></table></div>'
               if lignes else '<p class="doux">Aucun raccourci : ajoutes-en ci-dessous.</p>')
    presents = {f for _, _, f in actuels}
    propositions = ""
    for code, nom, filtre, financier in CATALOGUE[page]:
        if (financier and not admin) or ("par" in dict(parse_qsl(filtre)) and _uid() is None):
            continue
        if canonique(filtre) in presents:
            continue
        propositions += (f'<form class="mini" method="post" action="/raccourcis/ajouter"><input type="hidden" name="page" value="{page}">'
                         f'<input type="hidden" name="code" value="{code}"><button type="submit" class="secondaire">+ {esc(nom)}</button></form>')
    propositions = propositions or '<span class="doux">Tous les raccourcis proposés sont déjà là.</span>'

    v = saisie or {}
    champs = []
    if page == "chantiers":
        champs.append(liste("statut", "Statut", [(s, LIBELLES_STATUT[s]) for s in STATUTS_CHANTIER], v, vide="Tous"))
        if admin:
            champs.append(liste("paiement", "Paiement", [("a_recevoir", "À recevoir")] + [(c, l) for c, l in LIBELLES_PAIEMENT.items() if c != "sans_objet"], v, vide="Tous"))
    elif _uid() is not None:
        champs.append(liste("par", "Ouverte par", [("moi", "Moi")], v, vide="Tous"))
    champs.append(liste("secteur", "Secteur", [(c, l) for c, l, _ in secteurs], v, vide="Tous"))
    champs.append(liste("attente", "Délai d'attente", [(c, LIBELLES_ATTENTE[c]) for c in ("relance", "urgente", "surveiller", "normale")], v, vide="Tous"))
    champs.append(f'<div><label for="q">Texte contenu</label><input id="q" name="q" value="{esc(v.get("q", ""))}" placeholder="un nom, une rue..."></div>')
    champs.append(f'<div><label for="libelle">Nom du raccourci (facultatif)</label><input id="libelle" name="libelle" value="{esc(v.get("libelle", ""))}" maxlength="40"></div>')
    err = ('<div class="erreurs"><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>") if erreurs else ""
    contenu = (f'<h1>Raccourcis : {esc(nom_page)}</h1>'
               f'<p class="doux">Les raccourcis sont les pastilles en haut de la page {esc(nom_page)}. Chaque personne garde les siens.</p>{err}'
               f'<div class="carte"><h2>Mes raccourcis</h2>{tableau}</div>'
               f'<div class="carte"><h2>Ajouter un raccourci proposé</h2><div class="barre">{propositions}</div></div>'
               f'<div class="carte"><h2>Créer un raccourci personnalisé</h2><form method="post" action="/raccourcis/ajouter"><input type="hidden" name="page" value="{page}">'
               f'<div class="grille">{"".join(champs)}</div><div class="barre" style="margin-top:12px"><button type="submit">Ajouter</button></div></form></div>'
               f'<div class="barre"><a class="bouton secondaire" href="{adresse}">Retour à {esc(nom_page)}</a>'
               f'<form class="mini" method="post" action="/raccourcis/reinitialiser" onsubmit="return confirm(&#x27;Rétablir les raccourcis comme au départ ?&#x27;)">'
               f'<input type="hidden" name="page" value="{page}"><button type="submit" class="danger">Rétablir ceux du départ</button></form></div>')
    return gabarit("Raccourcis", contenu, query.get("ok"), query.get("err"), section=page)


def _retour(page, erreurs, ok):
    if erreurs:
        return redirection(f"/raccourcis?page={page}&err=" + quote(" ; ".join(erreurs)))
    return redirection(f"/raccourcis?page={page}&ok={ok}")


def post_ajouter(conn, form):
    page = _page(form)
    if form.get("code"):
        modele = next((m for m in CATALOGUE[page] if m[0] == form["code"]), None)
        erreurs = ["raccourci inconnu"] if modele is None else None
        if modele is not None:
            nom, filtre = modele[1], modele[2]
    else:
        nom = form.get("libelle", "")
        filtre = urlencode([(c, form.get(c, "")) for c in CRITERES])
        erreurs = None
    if erreurs is None:
        try:
            with transaction(conn):
                erreurs = ajouter(conn, page, nom, filtre)
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    return _retour(page, erreurs, "raccourci_ajoute")


def post_retirer(conn, raccourci_id, form):
    page = _page(form)
    with transaction(conn):
        erreurs = retirer(conn, page, raccourci_id)
    return _retour(page, erreurs, "raccourci_retire")


def post_deplacer(conn, raccourci_id, form):
    page = _page(form)
    with transaction(conn):
        erreurs = deplacer(conn, page, raccourci_id, form.get("sens", ""))
    return _retour(page, erreurs, "") if erreurs else redirection(f"/raccourcis?page={page}")


def post_reinitialiser(conn, form):
    page = _page(form)
    with transaction(conn):
        reinitialiser(conn, page)
    return _retour(page, [], "raccourcis_reinitialises")


ROUTES_RACCOURCIS = [
    ("GET", r"^/raccourcis$", lambda c, q, f, *g: page_raccourcis(c, q)),
    ("POST", r"^/raccourcis/ajouter$", lambda c, q, f, *g: post_ajouter(c, f)),
    ("POST", r"^/raccourcis/reinitialiser$", lambda c, q, f, *g: post_reinitialiser(c, f)),
    ("POST", r"^/raccourcis/(\d+)/retirer$", lambda c, q, f, i: post_retirer(c, int(i), f)),
    ("POST", r"^/raccourcis/(\d+)/deplacer$", lambda c, q, f, i: post_deplacer(c, int(i), f)),
]
