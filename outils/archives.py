"""Onglet Archives : tout l'historique de l'entreprise, pour chercher et comparer (réservé à l'administrateur : les montants y sont).

On y trouve les chantiers TERMINÉS (payés ou non), les chantiers ANNULÉS et les soumissions REFUSÉES. On filtre par texte (nom, adresse,
travaux, précisions : « cèdre »), type de travaux, secteur, période (dates précises, ou « il y a plus / moins de N mois »), montant ;
on trie ; on peut ne garder qu'un résultat par client (pour savoir qui relancer) ; « Exporter » donne un fichier CSV pour Excel.
Au-dessus des résultats : des chiffres clés ; en dessous : des statistiques (par type de travaux, secteur, année, mois de l'année) et
le taux d'acceptation des soumissions. La petite section « Archives » de la page Chantiers reste, comme avant.
"""
import csv
import datetime
import io
from urllib.parse import urlencode

from noyau import cle, decaler_mois, lister_secteurs
from vue import argent, badge_statut, esc, gabarit, heures, url_fiche

LIMITE_RESULTATS = 200
RESULTATS = (("termine", "Chantiers terminés"), ("annule", "Chantiers annulés"), ("refusee", "Soumissions refusées"), ("tout", "Tout l'historique"))
TRIS = (("recent", "Plus récent d'abord"), ("ancien", "Plus ancien d'abord"), ("montant", "Montant, du plus élevé"), ("client", "Client, de A à Z"))
MOIS_PLUS = ((1, "1 mois"), (3, "3 mois"), (6, "6 mois"), (9, "9 mois"), (12, "1 an"), (18, "18 mois"), (24, "2 ans"), (36, "3 ans"), (60, "5 ans"))
MOIS_MOINS = ((3, "3 mois"), (6, "6 mois"), (12, "1 an"), (24, "2 ans"), (36, "3 ans"), (60, "5 ans"))
NOMS_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
COLONNES = ("chantier_id, client_id, client_nom_complet, entreprise, telephone, courriel, adresse, ville, secteur, secteur_code, types_codes,"
            " type_libelle, travaux_detail, description, statut, genre, date_prevue, date_soumission, accepte_le, attente_depuis,"
            " duree_estimee_h, duree_reelle_h, prix_ht, total_ttc, paye, solde, statut_paiement, cree_par")
CONDITIONS = {"termine": "statut = 'termine'", "annule": "statut = 'annule' AND genre = 'chantier'",
              "refusee": "statut = 'annule' AND genre = 'soumission'", "tout": "statut IN ('termine', 'annule')"}
CHAMPS_TEXTE = ("client_nom_complet", "entreprise", "telephone", "courriel", "adresse", "ville", "secteur", "travaux_detail", "description")


# ---------------------------------------------------------------------------
# Les critères
# ---------------------------------------------------------------------------
def _date(texte):
    try:
        return datetime.date.fromisoformat((texte or "").strip()).isoformat()
    except ValueError:
        return ""


def _mois(texte):
    texte = (texte or "").strip()
    return int(texte) if texte.isdigit() and 1 <= int(texte) <= 600 else 0


def _montant(texte):
    texte = (texte or "").strip().replace(" ", "").replace(" ", "").replace("$", "").replace(",", ".")
    try:
        x = float(texte)
    except ValueError:
        return 0.0
    return x if 0 < x < 10_000_000 else 0.0


def lire_filtres(conn, query):
    """Critères valides d'une requête (ce qui n'a pas de sens est ignoré). Retourne un dict de textes, sans les critères vides
    (sauf « resultat » et « tri », qui ont toujours une valeur)."""
    types = {code for (code,) in conn.execute("SELECT code FROM types_travaux")}
    secteurs = {code for code, _, _ in lister_secteurs(conn)}
    f = {"q": " ".join((query.get("q") or "").split())[:100],
         "type": query.get("type") if query.get("type") in types else "",
         "secteur": query.get("secteur") if query.get("secteur") in secteurs else "",
         "resultat": query.get("resultat") if query.get("resultat") in CONDITIONS else "termine",
         "du": _date(query.get("du")), "au": _date(query.get("au")),
         "plus_de": str(_mois(query.get("plus_de")) or ""), "moins_de": str(_mois(query.get("moins_de")) or ""),
         "montant_min": (f"{_montant(query.get('montant_min')):g}" if _montant(query.get("montant_min")) else ""),
         "par_client": "1" if query.get("par_client") in ("1", "on", "oui") else "",
         "tri": query.get("tri") if query.get("tri") in dict(TRIS) else "recent"}
    return {k: v for k, v in f.items() if v or k in ("resultat", "tri")}


def _date_ref(ligne):
    """La date qui situe la fiche dans le temps : les travaux (terminé), sinon l'acceptation, la demande..."""
    return ligne["date_prevue"] or ligne["accepte_le"] or ligne["date_soumission"] or ligne["attente_depuis"] or ""


def selectionner(conn, f, aujourdhui=None):
    """Les fiches de l'historique qui répondent aux critères `f` (dicts, avec « date_ref »), triées."""
    aujourdhui = aujourdhui or datetime.date.today()
    cur = conn.execute(f"SELECT {COLONNES} FROM v_chantiers WHERE {CONDITIONS[f.get('resultat', 'termine')]}")
    noms = [d[0] for d in cur.description]
    lignes = []
    for r in cur.fetchall():
        l = dict(zip(noms, r))
        l["date_ref"] = _date_ref(l)
        lignes.append(l)
    if f.get("type"):
        lignes = [l for l in lignes if f["type"] in (l["types_codes"] or "").split("+")]
    if f.get("secteur"):
        lignes = [l for l in lignes if l["secteur_code"] == f["secteur"]]
    if f.get("du"):
        lignes = [l for l in lignes if l["date_ref"] >= f["du"]]
    if f.get("au"):
        lignes = [l for l in lignes if l["date_ref"] <= f["au"]]
    if f.get("plus_de"):                                         # fait il y a plus de N mois : au plus tard à cette date
        limite = decaler_mois(aujourdhui, -int(f["plus_de"])).isoformat()
        lignes = [l for l in lignes if l["date_ref"] <= limite]
    if f.get("moins_de"):                                        # fait il y a moins de N mois : au plus tôt à cette date
        limite = decaler_mois(aujourdhui, -int(f["moins_de"])).isoformat()
        lignes = [l for l in lignes if l["date_ref"] >= limite]
    if f.get("montant_min"):
        lignes = [l for l in lignes if l["prix_ht"] is not None and l["prix_ht"] >= float(f["montant_min"])]
    if f.get("q"):
        mots = cle(f["q"]).split()
        lignes = [l for l in lignes if all(m in cle(" ".join(str(l[c]) for c in CHAMPS_TEXTE if l[c])) for m in mots)]
    trier(lignes, f.get("tri", "recent"))
    return lignes


def trier(lignes, tri):
    if tri == "ancien":
        lignes.sort(key=lambda l: (l["date_ref"], l["chantier_id"]))
    elif tri == "montant":
        lignes.sort(key=lambda l: (l["prix_ht"] is None, -(l["prix_ht"] or 0), l["chantier_id"]))
    elif tri == "client":
        lignes.sort(key=lambda l: (cle(l["client_nom_complet"]), l["date_ref"]))
    else:
        lignes.sort(key=lambda l: (l["date_ref"], l["chantier_id"]), reverse=True)


def regrouper_par_client(lignes, tri="recent"):
    """Un résultat par client (pour savoir qui relancer) : son dernier chantier, combien de fois, pour quel total."""
    clients = {}
    for l in sorted(lignes, key=lambda x: (x["date_ref"], x["chantier_id"])):          # du plus ancien au plus récent : le dernier écrase
        g = clients.setdefault(l["client_id"], {"nb": 0, "total": 0.0})
        g.update(client_id=l["client_id"], client_nom_complet=l["client_nom_complet"], telephone=l["telephone"], courriel=l["courriel"],
                 adresse=l["adresse"], ville=l["ville"], secteur=l["secteur"], date_ref=l["date_ref"], chantier_id=l["chantier_id"],
                 type_libelle=l["type_libelle"], statut=l["statut"], genre=l["genre"])
        g["nb"] += 1
        g["total"] += l["prix_ht"] or 0
    groupes = list(clients.values())
    if tri == "ancien":
        groupes.sort(key=lambda g: (g["date_ref"], g["chantier_id"]))
    elif tri == "montant":
        groupes.sort(key=lambda g: (-g["total"], g["chantier_id"]))
    elif tri == "client":
        groupes.sort(key=lambda g: (cle(g["client_nom_complet"]), g["date_ref"]))
    else:
        groupes.sort(key=lambda g: (g["date_ref"], g["chantier_id"]), reverse=True)
    return groupes


# ---------------------------------------------------------------------------
# Les statistiques
# ---------------------------------------------------------------------------
def _moyenne(valeurs):
    valeurs = list(valeurs)
    return sum(valeurs) / len(valeurs) if valeurs else None


def _durees(l):
    """Durée de travail d'un chantier : la durée réelle, à défaut l'estimée."""
    return l["duree_reelle_h"] or l["duree_estimee_h"] or 0


def _groupe(lignes, cle_groupe):
    """{clé: statistiques} d'un ensemble de chantiers terminés : nombre, chiffre d'affaires, prix moyen, durée moyenne, revenu par heure."""
    groupes = {}
    for l in lignes:
        groupes.setdefault(cle_groupe(l), []).append(l)
    sortie = {}
    for k, membres in groupes.items():
        avec_prix = [m for m in membres if m["prix_ht"] is not None]
        ca = round(sum(m["prix_ht"] for m in avec_prix), 2)
        heures_prix = sum(_durees(m) for m in avec_prix if _durees(m))
        sortie[k] = {"n": len(membres), "ca": ca, "prix_moyen": (ca / len(avec_prix)) if avec_prix else None,
                     "duree_moyenne": _moyenne(_durees(m) for m in membres if _durees(m)),
                     "par_heure": (sum(m["prix_ht"] for m in avec_prix if _durees(m)) / heures_prix) if heures_prix else None}
    return sortie


def statistiques(lignes):
    """Chiffres clés et ventilations (chantiers terminés seulement : ce sont eux qui ont rapporté)."""
    termines = [l for l in lignes if l["statut"] == "termine"]
    annules = sum(1 for l in lignes if l["statut"] == "annule" and l["genre"] == "chantier")
    refusees = sum(1 for l in lignes if l["genre"] == "soumission")
    tout = _groupe(termines, lambda l: "tout")["tout"] if termines else {"n": 0, "ca": 0.0, "prix_moyen": None, "duree_moyenne": None, "par_heure": None}
    a_recevoir = round(sum(l["solde"] or 0 for l in termines if l["statut_paiement"] in ("a_payer", "partiel")), 2)
    mois = _groupe([l for l in termines if l["date_ref"]], lambda l: int(l["date_ref"][5:7]))
    return {
        "n_total": len(lignes), "n_termines": len(termines), "n_annules": annules, "n_refusees": refusees,
        "ca_ht": tout["ca"], "ca_ttc": round(sum(l["total_ttc"] or 0 for l in termines), 2),
        "recu": round(sum(l["paye"] or 0 for l in termines), 2), "a_recevoir": a_recevoir,
        "prix_moyen": tout["prix_moyen"], "duree_moyenne": tout["duree_moyenne"], "par_heure": tout["par_heure"],
        "clients": len({l["client_id"] for l in termines}),
        "par_type": _groupe(termines, lambda l: l["type_libelle"] or "(sans type)"),
        "par_secteur": _groupe(termines, lambda l: l["secteur"] or "(sans secteur)"),
        "par_annee": _groupe([l for l in termines if l["date_ref"]], lambda l: l["date_ref"][:4]),
        "par_mois": {m: mois.get(m, {"n": 0, "ca": 0.0}) for m in range(1, 13)},
    }


def statistiques_soumissions(conn, f):
    """Que deviennent les soumissions ? Acceptées (devenues chantiers), refusées, encore en cours ; taux d'acceptation, délai de réponse,
    et le détail par personne qui les a ouvertes. Mêmes critères que la recherche (texte, type, secteur, période sur la date de la demande)
    sauf le résultat, le montant et le regroupement."""
    cur = conn.execute("SELECT genre, statut, accepte_le, date_soumission, attente_depuis, cree_par, secteur_code, types_codes, client_nom_complet,"
                       " entreprise, telephone, courriel, adresse, ville, secteur, travaux_detail, description FROM v_chantiers")
    noms = [d[0] for d in cur.description]
    lignes = [dict(zip(noms, r)) for r in cur.fetchall()]
    for l in lignes:
        l["demande"] = l["date_soumission"] or l["attente_depuis"] or ""
    if f.get("type"):
        lignes = [l for l in lignes if f["type"] in (l["types_codes"] or "").split("+")]
    if f.get("secteur"):
        lignes = [l for l in lignes if l["secteur_code"] == f["secteur"]]
    if f.get("du"):
        lignes = [l for l in lignes if l["demande"] >= f["du"]]
    if f.get("au"):
        lignes = [l for l in lignes if l["demande"] <= f["au"]]
    if f.get("q"):
        mots = cle(f["q"]).split()
        lignes = [l for l in lignes if all(m in cle(" ".join(str(l[c]) for c in CHAMPS_TEXTE if l[c])) for m in mots)]

    def issue(l):
        if l["genre"] == "chantier":
            return "acceptee"
        return "refusee" if l["statut"] == "annule" else "en_cours"

    def resume(membres):
        acceptees = [l for l in membres if issue(l) == "acceptee"]
        refusees = [l for l in membres if issue(l) == "refusee"]
        delais = []
        for l in acceptees:
            if l["accepte_le"] and l["demande"] and l["accepte_le"] >= l["demande"]:
                delais.append((datetime.date.fromisoformat(l["accepte_le"]) - datetime.date.fromisoformat(l["demande"])).days)
        decidees = len(acceptees) + len(refusees)
        return {"total": len(membres), "acceptees": len(acceptees), "refusees": len(refusees), "en_cours": len(membres) - decidees,
                "taux": (len(acceptees) / decidees) if decidees else None, "delai": _moyenne(delais)}
    par_personne = {}
    for l in lignes:
        if l["cree_par"]:
            par_personne.setdefault(l["cree_par"], []).append(l)
    return {"global": resume(lignes), "par_personne": {nom: resume(m) for nom, m in sorted(par_personne.items(), key=lambda x: cle(x[0]))}}


# ---------------------------------------------------------------------------
# L'affichage
# ---------------------------------------------------------------------------
def _tel(t):
    return f"{t[2:5]}-{t[5:8]}-{t[8:]}" if t and len(t) == 12 else (t or "")


def _pct(x):
    return "—" if x is None else f"{x * 100:.0f} %".replace(".", ",")


def _jours(x):
    return "—" if x is None else f"{x:.0f} j"


def _montant_ou_tiret(x):
    return argent(x) if x else "—"


def _mois_selection(nom, options, choisi):
    texte = choisi if choisi and choisi.isdigit() and int(choisi) not in dict(options) else ""
    extra = f'<option value="{esc(texte)}" selected>{esc(texte)} mois</option>' if texte else ""
    return ('<option value="">Peu importe</option>' + "".join(
        f'<option value="{m}"{" selected" if choisi == str(m) else ""}>{esc(t)}</option>' for m, t in options) + extra)


def _formulaire(conn, f):
    types = conn.execute("SELECT code, libelle FROM types_travaux ORDER BY libelle COLLATE NOCASE").fetchall()
    secteurs = lister_secteurs(conn)
    opt_types = '<option value="">Tous les types</option>' + "".join(
        f'<option value="{esc(c)}"{" selected" if f.get("type") == c else ""}>{esc(l)}</option>' for c, l in types)
    opt_secteurs = '<option value="">Tous les secteurs</option>' + "".join(
        f'<option value="{esc(c)}"{" selected" if f.get("secteur") == c else ""}>{esc(l)}</option>' for c, l, _ in secteurs)
    opt_resultat = "".join(f'<option value="{c}"{" selected" if f["resultat"] == c else ""}>{esc(t)}</option>' for c, t in RESULTATS)
    opt_tri = "".join(f'<option value="{c}"{" selected" if f["tri"] == c else ""}>{esc(t)}</option>' for c, t in TRIS)
    return (
        '<form class="filtres" method="get" action="/archives">'
        f'<div class="recherche"><input type="search" name="q" value="{esc(f.get("q", ""))}" aria-label="Texte cherché" '
        'placeholder="Chercher : nom, adresse, travaux, précision (ex. cèdre)…"><button type="submit">Chercher</button></div>'
        '<div class="grille">'
        f'<div><label for="resultat">Quoi</label><select id="resultat" name="resultat">{opt_resultat}</select></div>'
        f'<div><label for="type">Type de travaux</label><select id="type" name="type">{opt_types}</select></div>'
        f'<div><label for="secteur">Secteur</label><select id="secteur" name="secteur">{opt_secteurs}</select></div>'
        f'<div><label for="plus_de">Fait il y a plus de</label><select id="plus_de" name="plus_de">{_mois_selection("plus_de", MOIS_PLUS, f.get("plus_de", ""))}</select></div>'
        f'<div><label for="moins_de">et il y a moins de</label><select id="moins_de" name="moins_de">{_mois_selection("moins_de", MOIS_MOINS, f.get("moins_de", ""))}</select></div>'
        f'<div><label for="du">Ou entre le</label><input id="du" type="date" name="du" value="{esc(f.get("du", ""))}"></div>'
        f'<div><label for="au">et le</label><input id="au" type="date" name="au" value="{esc(f.get("au", ""))}"></div>'
        f'<div><label for="montant_min">Prix avant taxes d\'au moins ($)</label><input id="montant_min" name="montant_min" inputmode="decimal" '
        f'value="{esc(f.get("montant_min", ""))}"></div>'
        f'<div><label for="tri">Trier par</label><select id="tri" name="tri">{opt_tri}</select></div>'
        '</div>'
        f'<p><label class="coche"><input type="checkbox" name="par_client" value="1"{" checked" if f.get("par_client") else ""}> '
        'Un seul résultat par client (son dernier chantier) : pour savoir qui relancer</label></p>'
        '<div class="barre"><button type="submit">Chercher</button><a class="bouton secondaire" href="/archives">Tout effacer</a>'
        f'<a class="bouton secondaire" href="/archives.csv?{esc(urlencode(f))}" title="Un fichier qui s\'ouvre dans Excel">Exporter (Excel)</a></div></form>')


def _idees(aujourdhui):
    """Quelques recherches toutes faites (la première est l'exemple type : qui relancer pour sa haie de cèdres)."""
    annee = aujourdhui.year - 1
    idees = (("Haies de cèdre faites il y a plus d'un an : qui relancer ?",
              {"type": "taille_haie", "q": "cedre", "plus_de": "12", "par_client": "1", "tri": "ancien"}),
             ("Tous les clients de plus d'un an", {"plus_de": "12", "par_client": "1", "tri": "ancien"}),
             (f"Tout ce qui a été terminé en {annee}", {"du": f"{annee}-01-01", "au": f"{annee}-12-31"}),
             ("Plus gros chantiers (1 000 $ et plus)", {"montant_min": "1000", "tri": "montant"}),
             ("Soumissions refusées", {"resultat": "refusee"}))
    liens = " · ".join(f'<a href="/archives?{esc(urlencode(q))}">{esc(t)}</a>' for t, q in idees)
    return f'<p class="doux">Idées de recherche : {liens}</p>'


def _tuile(valeur, libelle, aide=""):
    titre = f' title="{esc(aide)}"' if aide else ""
    return f'<div class="tuile"{titre}><b>{valeur}</b><span>{esc(libelle)}</span></div>'


def _tuiles(st):
    tuiles = [_tuile(str(st["n_termines"]), "chantiers terminés"), _tuile(argent(st["ca_ht"]), "chiffre d'affaires avant taxes"),
              _tuile(_montant_ou_tiret(st["prix_moyen"]), "prix moyen par chantier"),
              _tuile(heures(st["duree_moyenne"]) if st["duree_moyenne"] else "—", "durée moyenne"),
              _tuile(f"{argent(st['par_heure'])}/h" if st["par_heure"] else "—", "revenu par heure",
                     "Prix avant taxes divisé par les heures passées sur place (durée réelle, sinon estimée) : par heure de chantier, pas par personne."),
              _tuile(str(st["clients"]), "clients différents")]
    if st["a_recevoir"]:
        tuiles.append(_tuile(argent(st["a_recevoir"]), "encore à recevoir"))
    if st["n_annules"]:
        tuiles.append(_tuile(str(st["n_annules"]), "chantiers annulés"))
    if st["n_refusees"]:
        tuiles.append(_tuile(str(st["n_refusees"]), "soumissions refusées"))
    return f'<div class="tuiles">{"".join(tuiles)}</div>'


def _tableau_stat(titre, groupes, premiere, ordre=None, limite=None, avec_moyennes=False, note="", large=False):
    """Un tableau de statistiques avec une barre proportionnelle au chiffre d'affaires."""
    cles = list(ordre) if ordre is not None else sorted(groupes, key=lambda k: (-groupes[k]["ca"], str(k)))
    autres = None
    if limite and len(cles) > limite:
        reste = cles[limite:]
        cles = cles[:limite]
        autres = {"n": sum(groupes[k]["n"] for k in reste), "ca": round(sum(groupes[k]["ca"] for k in reste), 2)}
    plus_haut = max([groupes[k]["ca"] for k in cles] + ([autres["ca"]] if autres else []) + [0.01])
    if not any(groupes[k]["n"] for k in cles):
        return ""
    entete = f'<th>{esc(premiere)}</th><th class="droite">Nb</th><th class="droite">Chiffre d\'affaires</th>' + (
        '<th class="droite">Prix moyen</th><th class="droite">Durée moy.</th><th class="droite">$/h</th>' if avec_moyennes else "") + "<th></th>"

    def ligne(libelle, g):
        moyennes = (f'<td class="droite">{_montant_ou_tiret(g.get("prix_moyen"))}</td>'
                    f'<td class="droite">{heures(g["duree_moyenne"]) if g.get("duree_moyenne") else "—"}</td>'
                    f'<td class="droite">{_montant_ou_tiret(g.get("par_heure"))}</td>') if avec_moyennes else ""
        largeur = max(2, round(g["ca"] / plus_haut * 100)) if g["ca"] else 0
        return (f'<tr><td>{esc(libelle)}</td><td class="droite">{g["n"]}</td><td class="droite">{argent(g["ca"])}</td>{moyennes}'
                f'<td class="cellule-barre"><span class="stat-barre" style="width:{largeur}%"></span></td></tr>')
    corps = "".join(ligne(str(k) if not isinstance(k, int) else NOMS_MOIS[k - 1], groupes[k]) for k in cles if groupes[k]["n"] or ordre is not None)
    if autres:
        corps += ligne("Autres", autres)
    note_html = f'<p class="doux" style="margin-bottom:0">{esc(note)}</p>' if note else ""
    return (f'<div class="carte{" large" if large else ""}"><h2>{esc(titre)}</h2><div class="stat-defile"><table class="stat"><thead><tr>{entete}</tr></thead>'
            f'<tbody>{corps}</tbody></table></div>{note_html}</div>')


def _bloc_soumissions(ss):
    g = ss["global"]
    if not g["total"]:
        return ""

    def ligne(nom, r):
        return (f'<tr><td>{esc(nom)}</td><td class="droite">{r["total"]}</td><td class="droite">{r["acceptees"]}</td><td class="droite">{r["refusees"]}</td>'
                f'<td class="droite">{r["en_cours"]}</td><td class="droite"><b>{_pct(r["taux"])}</b></td><td class="droite">{_jours(r["delai"])}</td></tr>')
    corps = ligne("Toutes les soumissions", g) + "".join(ligne(nom, r) for nom, r in ss["par_personne"].items())
    return ('<div class="carte large"><h2>Que deviennent les soumissions ?</h2><div class="stat-defile"><table class="stat"><thead><tr><th></th><th class="droite">Ouvertes</th>'
            '<th class="droite">Acceptées</th><th class="droite">Refusées</th><th class="droite">En cours</th><th class="droite">Taux d\'acceptation</th>'
            f'<th class="droite">Délai de réponse</th></tr></thead><tbody>{corps}</tbody></table></div>'
            '<p class="doux" style="margin-bottom:0">Taux d\'acceptation = acceptées sur (acceptées + refusées) ; les soumissions encore en cours ne comptent pas. '
            'Délai de réponse = jours entre la demande et l\'acceptation. Les chantiers « en attente » comptent comme acceptés. '
            'Les critères de recherche s\'appliquent (texte, type, secteur, période sur la date de la demande).</p></div>')


def _identite(nom, tel, lien):
    """Le nom du client (lien) et, dessous, son téléphone."""
    return f'<a href="{lien}">{esc(nom)}</a>' + (f'<div class="doux">{esc(_tel(tel))}</div>' if tel else "")


def _lieu(adresse, secteur, ville):
    return f'{esc(adresse)}<div class="doux">{esc(secteur or ville)}</div>'


def _relancer(client_id):
    """Pour relancer un client : ouvrir une nouvelle soumission à son nom."""
    return (f'<td class="col-actions"><div class="actions-ligne actions-soumission"><a class="bouton secondaire" '
            f'href="/client/{client_id}/soumission/nouveau" title="Ouvrir une nouvelle soumission pour ce client">Relancer</a></div></td>')


def _resultats(lignes, groupes, f, historique_vide=False):
    if f.get("par_client"):
        total = len(groupes)
        corps = ""
        for g in groupes[:LIMITE_RESULTATS]:
            lien_client = f"/client/{g['client_id']}"
            corps += (f'<tr><td>{esc(g["date_ref"])}</td><td>{_identite(g["client_nom_complet"], g["telephone"], lien_client)}</td>'
                      f'<td>{_lieu(g["adresse"], g["secteur"], g["ville"])}</td>'
                      f'<td><a href="{url_fiche(g["chantier_id"], g["genre"])}">{esc(g["type_libelle"] or "à préciser")}</a></td>'
                      f'<td class="droite">{g["nb"]}</td><td class="montant">{_montant_ou_tiret(g["total"])}</td>{_relancer(g["client_id"])}</tr>')
        tete = ('<th>Dernier chantier</th><th>Client</th><th>Adresse</th><th>Travaux</th><th class="droite">Nb</th>'
                '<th class="droite">Total avant taxes</th><th></th>')
        unite = "client" + ("s" if total > 1 else "")
    else:
        total = len(lignes)
        corps = ""
        for l in lignes[:LIMITE_RESULTATS]:
            corps += (f'<tr><td>{esc(l["date_ref"])}</td><td>{_identite(l["client_nom_complet"], l["telephone"], url_fiche(l["chantier_id"], l["genre"]))}</td>'
                      f'<td>{_lieu(l["adresse"], l["secteur"], l["ville"])}</td><td>{esc(l["travaux_detail"] or "à préciser")}</td>'
                      f'<td>{badge_statut(l["statut"], l["genre"])}</td><td class="montant">{_montant_ou_tiret(l["prix_ht"])}</td>{_relancer(l["client_id"])}</tr>')
        tete = ('<th>Date</th><th>Client</th><th>Adresse</th><th>Travaux</th><th>Résultat</th><th class="droite">Prix avant taxes</th><th></th>')
        unite = "fiche" + ("s" if total > 1 else "")
    if not total and historique_vide:
        return ('<div class="carte">Pas encore d\'historique : les chantiers terminés, les chantiers annulés et les soumissions refusées apparaîtront ici, '
                'avec leurs statistiques.</div>')
    if not total:
        return '<div class="carte">Rien ne correspond à ces critères. Élargis la recherche (moins de filtres) ou <a href="/archives">efface-les tous</a>.</div>'
    suite = (f'<p class="doux">Les {LIMITE_RESULTATS} premiers sur {total} sont affichés : précise la recherche, ou utilise « Exporter » pour tout avoir.</p>'
             if total > LIMITE_RESULTATS else "")
    return (f'<h2 class="groupe">Résultats <small>{total} {unite} · <a href="#statistiques">voir les statistiques</a></small></h2>'
            f'<div class="liste-defile"><table class="tableau archive"><thead><tr>{tete}</tr></thead><tbody>{corps}</tbody></table></div>{suite}')


def page_archives(conn, query):
    f = lire_filtres(conn, query)
    lignes = selectionner(conn, f)
    groupes = regrouper_par_client(lignes, f["tri"]) if f.get("par_client") else []
    st = statistiques(lignes)
    historique_vide = conn.execute("SELECT 1 FROM v_chantiers WHERE statut IN ('termine', 'annule') LIMIT 1").fetchone() is None
    sections = "".join((
        _tableau_stat("Par type de travaux", st["par_type"], "Travaux", limite=12, avec_moyennes=True, large=True,
                      note="Un chantier qui combine deux types a sa propre ligne (« Abattage + Élagage »)."),
        _tableau_stat("Par secteur", st["par_secteur"], "Secteur", limite=12),
        _tableau_stat("Par année", st["par_annee"], "Année", ordre=sorted(st["par_annee"], reverse=True)),
        _tableau_stat("Selon le mois de l'année (toutes années ensemble)", st["par_mois"], "Mois", ordre=range(1, 13),
                      note="Pour voir quand l'ouvrage est là : janvier à décembre, années confondues."),
        _bloc_soumissions(statistiques_soumissions(conn, f))))
    stats = (f'<h2 class="groupe" id="statistiques">Statistiques <small>sur les chantiers terminés qui correspondent</small></h2>'
             f'<div class="grille-stats">{sections}</div>') if sections else ""
    contenu = (f'<h1>Archives</h1><p class="doux">Tout l\'historique : chantiers terminés, annulés et soumissions refusées. Cherche, compare, '
               'exporte. (Les chantiers en cours restent dans Chantiers.)</p>'
               f'{_formulaire(conn, f)}{_idees(datetime.date.today())}{_tuiles(st)}{_resultats(lignes, groupes, f, historique_vide)}{stats}')
    return gabarit("Archives", contenu, section="archives", large=True)


# ---------------------------------------------------------------------------
# Export CSV (s'ouvre dans Excel : séparateur « ; », virgule décimale, accents)
# ---------------------------------------------------------------------------
def _cellule(x):
    """Texte sûr pour un tableur : une cellule qui commencerait par = + - @ serait prise pour une formule."""
    x = "" if x is None else str(x)
    return "'" + x if x[:1] in ("=", "+", "-", "@", "\t", "\r") else x


def _nombre(x):
    return "" if x is None else f"{x:.2f}".replace(".", ",")


def _heures_csv(x):
    return "" if x is None else f"{x:g}".replace(".", ",")


def exporter_csv(conn, query):
    f = lire_filtres(conn, query)
    lignes = selectionner(conn, f)
    sortie = io.StringIO()
    ecrivain = csv.writer(sortie, delimiter=";", lineterminator="\r\n")
    if f.get("par_client"):
        ecrivain.writerow(["Client", "Téléphone", "Courriel", "Adresse", "Secteur", "Dernier chantier", "Nombre de chantiers", "Total avant taxes",
                           "Travaux du dernier chantier"])
        for g in regrouper_par_client(lignes, f["tri"]):
            ecrivain.writerow([_cellule(g["client_nom_complet"]), _cellule(_tel(g["telephone"])), _cellule(g["courriel"]), _cellule(g["adresse"]),
                               _cellule(g["secteur"] or g["ville"]), g["date_ref"], g["nb"], _nombre(g["total"]), _cellule(g["type_libelle"])])
    else:
        ecrivain.writerow(["Date", "Client", "Téléphone", "Courriel", "Adresse", "Secteur", "Travaux", "Résultat", "Prix avant taxes",
                           "Total taxes incluses", "Durée estimée (h)", "Durée réelle (h)", "Reçu", "À recevoir"])
        for l in lignes:
            a_recevoir = l["solde"] if l["statut_paiement"] in ("a_payer", "partiel") else None
            ecrivain.writerow([l["date_ref"], _cellule(l["client_nom_complet"]), _cellule(_tel(l["telephone"])), _cellule(l["courriel"]),
                               _cellule(l["adresse"]), _cellule(l["secteur"] or l["ville"]), _cellule(l["travaux_detail"]),
                               "Refusée" if l["genre"] == "soumission" else {"termine": "Terminé", "annule": "Annulé"}[l["statut"]],
                               _nombre(l["prix_ht"]), _nombre(l["total_ttc"] if l["prix_ht"] is not None else None), _heures_csv(l["duree_estimee_h"]),
                               _heures_csv(l["duree_reelle_h"]), _nombre(l["paye"]), _nombre(a_recevoir)])
    corps = ("﻿" + sortie.getvalue()).encode("utf-8")                    # le BOM : Excel lit alors correctement les accents
    nom = f"archives-{datetime.date.today().isoformat()}.csv"
    return ("200 OK", [("Content-Type", "text/csv; charset=utf-8"), ("Content-Disposition", f'attachment; filename="{nom}"')], corps)


ROUTES_ARCHIVES = [
    ("GET", r"^/archives\.csv$", lambda c, q, f, *g: exporter_csv(c, q)),
    ("GET", r"^/archives$", lambda c, q, f, *g: page_archives(c, q)),
]
