"""Pages « clients » : liste, fiche client, modification du client, et formulaire SIMPLIFIÉ de nouveau chantier.

Le formulaire simplifié s'ouvre depuis la fiche d'un client : le nom et l'adresse sont verrouillés (affichés,
non modifiables : le serveur ignore tout ce que le navigateur enverrait à leur sujet) et seuls les éléments
essentiels sont demandés : travaux à faire, prix, modalité de paiement, notes.
"""
import datetime
import sqlite3
from urllib.parse import urlencode

from noyau import (COLONNES, MSG_MODIFIE_ENTRE_TEMPS, empreinte, resume_suppression_client, supprimer_client as supprimer_client_noyau, Resultat, alias_types_travaux, appliquer_secteur, cle, creer_chantier, lire_client, lire_ligne,
                   lister_secteurs, mettre_a_jour_client, renommer_secteur, supprimer_secteur, ajouter_secteur, transaction, travaux_depuis_formulaire, valeurs_client)
from pages_chantier import appliquer_options
from vue import (LIBELLES_STATUT, avance, badge, bloc_options_travaux, bloc_types, champ, champ_modalite, client_avance,
                 client_essentiel, esc, gabarit, lien_maps, redirection, select_secteur, zone)


def _types(conn):
    return sorted(conn.execute("SELECT code, libelle FROM types_travaux"), key=lambda t: (t[0] == "autre", cle(t[1])))


def _nom_client(c):
    """c : dict avec prenom, nom, entreprise."""
    personne = " ".join(x for x in (c.get("prenom"), c.get("nom")) if x)
    if personne and c.get("entreprise"):
        return f"{personne} · {c['entreprise']}"
    return personne or c.get("entreprise") or ""


def _client(conn, client_id):
    r = conn.execute("SELECT cl.id, cl.prenom, cl.nom, cl.entreprise, cl.telephone, cl.telephone_2, cl.courriel, cl.sms_ok, cl.adresse, cl.ville,"
                     " cl.province, cl.code_postal, cl.notes_acces, cl.notes, cl.geocode_statut, s.libelle FROM clients cl"
                     " LEFT JOIN secteurs s ON s.code = cl.secteur WHERE cl.id = ?", (client_id,)).fetchone()
    if r is None:
        return None
    cols = ["id", "prenom", "nom", "entreprise", "telephone", "telephone_2", "courriel", "sms_ok", "adresse", "ville",
            "province", "code_postal", "notes_acces", "notes", "geocode_statut", "secteur"]
    c = dict(zip(cols, r))
    c["adresse_maps"] = f"{c['adresse']}, {c['ville']}, {c['province']}" + (f" {c['code_postal']}" if c["code_postal"] else "") + ", Canada"
    return c


def _introuvable():
    return gabarit("Introuvable", '<h1>Client introuvable</h1><p><a href="/clients">Retour aux clients</a></p>'), 404


def _tel(t):
    return f"{t[2:5]}-{t[5:8]}-{t[8:]}" if t and len(t) == 12 else (t or "")


# ---------------------------------------------------------------------------
# Liste et fiche
# ---------------------------------------------------------------------------
def page_clients(conn, query):
    """Liste épurée : Nom, Téléphone, Adresse (ni nombre de chantiers, ni montants : ils sont dans la fiche du client).
    On peut la filtrer par secteur (liste fermée : jamais de doublon d'écriture)."""
    q = query.get("q", "").strip()
    secteur = query.get("secteur", "")
    lignes = conn.execute(
        "SELECT cl.id, cl.prenom, cl.nom, cl.entreprise, cl.telephone, cl.adresse, cl.ville, cl.province, cl.code_postal, s.libelle"
        " FROM clients cl LEFT JOIN secteurs s ON s.code = cl.secteur"
        + (" WHERE cl.secteur = ?" if secteur else "") + " ORDER BY cl.nom, cl.entreprise, cl.prenom",
        (secteur,) if secteur else ()).fetchall()
    if q:
        mots = cle(q).split()
        lignes = [r for r in lignes if all(m in cle(" ".join(str(x) for x in (r[1:9] + (r[9],)) if x)) for m in mots)]
    corps = ""
    for cid, prenom, nom, entreprise, tel, adresse, ville, prov, cp, libelle_secteur in lignes[:300]:
        maps = f"{adresse}, {ville}, {prov}" + (f" {cp}" if cp else "") + ", Canada"
        corps += (f'<tr><td><a href="/client/{cid}">{esc(_nom_client(dict(prenom=prenom, nom=nom, entreprise=entreprise)))}</a></td>'
                  f'<td>{esc(_tel(tel))}</td><td>{lien_maps(maps, adresse)}<div class="doux">{esc(libelle_secteur or ville)}</div></td></tr>')
    tableau = (f'<div class="liste-defile"><table><thead><tr><th>Nom</th><th>Téléphone</th><th>Adresse</th></tr></thead>'
               f'<tbody>{corps}</tbody></table></div>'
               if corps else '<div class="carte">Aucun client. <a href="/nouveau">Créer le premier ?</a></div>')
    select_sect, _ = select_secteur(lister_secteurs(conn), {"secteur": secteur}, nom="secteur", requis=False, tout="Tous les secteurs")
    recherche = (f'<form class="recherche" method="get" action="/clients"><input type="search" name="q" value="{esc(q)}" '
                 f'placeholder="Chercher : nom, téléphone, adresse…">{select_sect}<button type="submit">Chercher</button></form>')
    nouveau = '<div class="barre" style="margin-bottom:16px"><a class="bouton" href="/nouveau">+ Nouveau client</a></div>'
    return gabarit("Clients", f'<h1>Clients</h1>{nouveau}{recherche}{tableau}<p class="doux"><a href="/secteurs">Gérer les secteurs desservis</a></p>', query.get("ok"))


def page_client(conn, client_id, query):
    c = _client(conn, client_id)
    if c is None:
        return _introuvable()
    chantiers = conn.execute(
        "SELECT chantier_id, attente_depuis, type_libelle, statut, archive"
        " FROM v_chantiers WHERE client_id = ? ORDER BY 2 DESC, chantier_id DESC", (client_id,)).fetchall()
    lignes = "".join(
        f'<tr><td><a href="/chantier/{i}">{esc(d) or "sans date"}</a></td><td>{esc(t)}</td><td>{badge(st, LIBELLES_STATUT[st])}'
        f'{" <span class=doux>archivé</span>" if arch else ""}</td></tr>'
        for i, d, t, st, arch in chantiers)
    historique = (f'<div class="liste-defile"><table><thead><tr><th>Date</th><th>Travaux</th><th>Statut</th></tr></thead>'
                  f'<tbody>{lignes}</tbody></table></div>'
                  if lignes else '<p class="doux">Aucun chantier pour ce client.</p>')
    tels = " · ".join(esc(_tel(t)) for t in (c["telephone"], c["telephone_2"]) if t) or "—"

    def ligne(libelle, contenu_html):
        return f'<p style="margin:6px 0 0"><b>{libelle} :</b> {contenu_html}</p>'
    fiche = (f'<div class="carte"><div class="barre"><h2 style="margin:0">{esc(_nom_client(c))}</h2></div>'
             + ligne("Adresse", lien_maps(c["adresse_maps"], c["adresse_maps"].replace(", Canada", "")))
             + ligne("Secteur", esc(c["secteur"]) if c["secteur"] else "<b>à choisir</b> (« Modifier le client »)")
             + ligne("Téléphone", tels + ("" if c["sms_ok"] else " · <b>pas de rappels par texto</b>"))
             + (ligne("Courriel", esc(c["courriel"])) if c["courriel"] else "")
             + (ligne("Accès", esc(c["notes_acces"])) if c["notes_acces"] else "")
             + (ligne("Notes", esc(c["notes"])) if c["notes"] else "") + "</div>")
    actions = (f'<div class="barre" style="margin-bottom:16px"><a class="bouton" href="/client/{client_id}/chantier/nouveau">+ Nouveau chantier</a>'
               f'<a class="bouton secondaire" href="/client/{client_id}/modifier">Modifier le client</a></div>')
    n, termines, paiements = resume_suppression_client(conn, client_id)
    efface = []
    if n:
        efface.append(f"{n} chantier{'s' if n > 1 else ''}" + (f" (dont {termines} terminé{'s' if termines > 1 else ''}, archives comprises)" if termines else ""))
    if paiements:
        efface.append(f"{paiements} paiement{'s' if paiements > 1 else ''}")
    detail = " et ".join(efface)
    confirmation = ("Supprimer définitivement ce client" + (f" avec {detail}" if detail else "") + " ? Tout disparaît, y compris des archives. Cette action est irréversible.")
    suppression = ('<div class="carte"><h2>Supprimer ce client</h2><p class="doux">Efface le client et tout ce qui le concerne'
                   + (f" : {esc(detail)}" if detail else "") + ". Définitif, y compris dans les archives.</p>"
                   f'<form method="post" action="/client/{client_id}/supprimer" onsubmit="return confirm({esc(repr(confirmation))})">'
                   '<button class="danger" type="submit">Supprimer le client</button></form></div>')
    return gabarit(_nom_client(c), f'<h1>Fiche client</h1>{fiche}{actions}<h2>Chantiers</h2>{historique}{suppression}', query.get("ok"), query.get("err"))


# ---------------------------------------------------------------------------
# Modification du client (la seule façon de changer son nom ou son adresse)
# ---------------------------------------------------------------------------
def _form_client(conn, client_id, valeurs, erreurs=()):
    err = ""
    if erreurs:
        err = ('<div class="erreurs"><strong>À corriger :</strong><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>")
    actuel = valeurs_client(conn, client_id)
    return (f'{err}<form method="post" action="/client/{client_id}/modifier"><input type="hidden" name="empreinte" value="{empreinte(actuel) if actuel else ""}">{client_essentiel(valeurs, lister_secteurs(conn))}{avance(client_avance(valeurs), ouvert=bool(erreurs))}'
            f'<div class="barre"><button type="submit">Enregistrer</button><a class="bouton secondaire" href="/client/{client_id}">Annuler</a></div></form>')


def page_client_modifier(conn, client_id):
    valeurs = valeurs_client(conn, client_id)
    if valeurs is None:
        return _introuvable()
    return gabarit("Modifier le client", f'<h1>Modifier le client</h1><p class="doux">Ces informations s\'appliquent à tous les chantiers de ce client.</p>{_form_client(conn, client_id, valeurs)}')


def client_modifier(conn, client_id, form):
    actuel = valeurs_client(conn, client_id)
    if actuel is None:
        return _introuvable()
    if form.get("empreinte") and form["empreinte"] != empreinte(actuel):        # modifié par quelqu'un d'autre entre-temps
        return gabarit("Modifier le client", f'<h1>Modifier le client</h1>{_form_client(conn, client_id, actuel, [MSG_MODIFIE_ENTRE_TEMPS])}')
    brut = {c: form.get(c, "") for c in COLONNES}
    brut["client_sms_ok"] = "1" if form.get("client_sms_ok") else "0"
    erreurs_secteur = appliquer_secteur(conn, brut, requis=True)         # la ville vient du secteur choisi
    v, erreurs = lire_client(brut)
    if erreurs_secteur:
        erreurs = erreurs_secteur + [e for e in erreurs if "ville est obligatoire" not in e]
    if not erreurs:
        try:
            with transaction(conn):
                mettre_a_jour_client(conn, client_id, v)
            return redirection(f"/client/{client_id}?ok=client_maj")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    return gabarit("Modifier le client", f'<h1>Modifier le client</h1>{_form_client(conn, client_id, brut, erreurs)}')


# ---------------------------------------------------------------------------
# Nouveau chantier depuis la fiche client : formulaire simplifié, nom et adresse verrouillés
# ---------------------------------------------------------------------------
def _form_simplifie(conn, client_id, valeurs, erreurs=()):
    c = _client(conn, client_id)
    err = ""
    if erreurs:
        err = ('<div class="erreurs"><strong>À corriger avant d\'enregistrer :</strong><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>")
    taxes = " checked" if valeurs.get("taxes_auto") else ""
    verrou = (f'<div class="verrou"><b>{esc(_nom_client(c))}</b><br>{esc(c["adresse"])}, {esc(c["ville"])}'
              f'{" " + esc(c["code_postal"]) if c["code_postal"] else ""}'
              f'<div class="doux">Nom et adresse verrouillés. <a href="/client/{client_id}/modifier">Modifier la fiche client</a></div></div>')
    return f"""{err}{verrou}<form method="post" action="/client/{client_id}/chantier/nouveau">
<div class="carte"><h2>Travaux à faire</h2><div class="grille">{bloc_types(_types(conn), valeurs)}
{bloc_options_travaux(valeurs)}
{champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal", placeholder="2,5", required=True)}
{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal", placeholder="480,00")}
<div><label>&nbsp;</label><label class="coche"><input type="checkbox" name="taxes_auto" value="1"{taxes}>Ajouter TPS 5 % et TVQ 9,975 %</label></div>
{zone("description", "Notes (description du chantier, imprimée sur la feuille de route)", valeurs)}</div>
<p class="doux">La durée estimée est obligatoire (heures décimales : 2,5 = 2 h 30) ; elle sert à calculer les heures de la journée.</p></div>
{avance('<div class="carte"><h2>Demande et règlement</h2><div class="grille">' + champ("date_soumission", "Date de la demande de soumission", valeurs, "date") + champ_modalite(valeurs) + "</div></div>", ouvert=bool(erreurs))}
<div class="barre"><button type="submit">Créer le chantier</button><a class="bouton secondaire" href="/client/{client_id}">Annuler</a></div></form>
<p class="doux">Le chantier est créé « À planifier ». La date des travaux et le statut se règlent ensuite depuis la page Journée ou le chantier.</p>"""


def page_chantier_nouveau(conn, client_id):
    if _client(conn, client_id) is None:
        return _introuvable()
    return gabarit("Nouveau chantier", f'<h1>Nouveau chantier</h1>{_form_simplifie(conn, client_id, {"date_soumission": datetime.date.today().isoformat()})}')


def chantier_creer(conn, client_id, form):
    if _client(conn, client_id) is None:
        return _introuvable()
    travaux, valeurs = travaux_depuis_formulaire(conn, form)
    saisie = {**valeurs, **{c: form.get(c, "") for c in ("prix_ht", "modalite_paiement", "description", "date_soumission", "duree_estimee_h")},
              "taxes_auto": "1" if form.get("taxes_auto") else ""}
    # Nom, adresse et coordonnées viennent TOUJOURS de la base : ce que le navigateur enverrait est ignoré.
    brut = {c: "" for c in COLONNES}
    brut.update(valeurs_client(conn, client_id))
    brut.update({c: saisie[c] for c in ("prix_ht", "modalite_paiement", "description", "date_soumission", "duree_estimee_h")})
    brut.update(statut="a_planifier", type_travaux=travaux)
    erreurs_bois = appliquer_options(brut, form, travaux)
    saisie.update({c: brut[c] for c in ("nacelle", "debarrasser_bois", "bois_format")})
    saisie["nacelle"] = "1" if brut["nacelle"] == "1" else ""
    saisie["debarrasser_bois"] = "1" if brut["debarrasser_bois"] == "1" else ""
    v, erreurs = lire_ligne(brut, alias_types_travaux(conn), taxes_auto=bool(saisie["taxes_auto"]))
    erreurs = erreurs + erreurs_bois
    if not erreurs:
        try:
            with transaction(conn):
                chantier_id = creer_chantier(conn, client_id, v, Resultat())
            return redirection(f"/chantier/{chantier_id}?ok=client_cree")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    return gabarit("Nouveau chantier", f'<h1>Nouveau chantier</h1>{_form_simplifie(conn, client_id, saisie, erreurs)}')


# ---------------------------------------------------------------------------
# Secteurs desservis (la liste déroulante des clients)
# ---------------------------------------------------------------------------
def page_secteurs(conn, query, erreurs=(), saisie=None):
    saisie = saisie or {}
    nombres = dict(conn.execute("SELECT secteur, count(*) FROM clients WHERE secteur IS NOT NULL GROUP BY secteur"))
    lignes = ""
    for code, libelle, ville in lister_secteurs(conn):
        n = nombres.get(code, 0)
        supprimer = (f'<form class="mini" method="post" action="/secteurs/{esc(code)}/supprimer" onsubmit="return confirm(\'Supprimer ce secteur ?\')">'
                     '<button class="danger" type="submit">Supprimer</button></form>') if not n else '<span class="doux">utilisé</span>'
        lignes += (f'<tr><td><form class="mini" method="post" action="/secteurs/{esc(code)}/renommer"><input name="libelle" value="{esc(libelle)}" '
                   f'aria-label="Nom du secteur"><button type="submit" class="secondaire">Renommer</button></form></td>'
                   f'<td>{esc(ville)}</td><td class="droite">{n}</td><td>{supprimer}</td></tr>')
    err = ('<div class="erreurs"><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>") if erreurs else ""
    ajout = (f'<div class="carte"><h2>Ajouter un secteur</h2><form method="post" action="/secteurs/ajouter"><div class="grille">'
             f'{champ("libelle", "Nom du secteur", saisie, required=True, placeholder="Ex. Cap-de-la-Madeleine")}'
             f'{champ("ville", "Ville inscrite sur l’adresse (si différente du nom)", saisie, placeholder="Ex. Trois-Rivières")}'
             '<div><label>&nbsp;</label><button type="submit">Ajouter</button></div></div></form>'
             '<p class="doux">Un secteur existant (même nom à l’accent, au tiret ou à la casse près) est refusé : pas de doublons.</p></div>')
    contenu = ('<h1>Secteurs desservis</h1><p class="doux">La liste déroulante « Ville / secteur » des clients. La ville inscrite sur l\'adresse '
               '(pour Google Maps) vient du secteur choisi : plus de « Trois Rivieres » ni de « Trois-Riviere ».</p>'
               f'{err}<div class="liste-defile"><table><thead><tr><th>Secteur</th><th>Ville sur l’adresse</th><th class="droite">Clients</th><th></th></tr></thead>'
               f'<tbody>{lignes}</tbody></table></div>{ajout}<p><a href="/clients">Retour aux clients</a></p>')
    return gabarit("Secteurs", contenu, query.get("ok"))


def _secteur_action(conn, travail, ok):
    try:
        with transaction(conn):
            erreurs = travail()
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    return redirection(f"/secteurs?ok={ok}") if not erreurs else page_secteurs(conn, {}, erreurs)


def client_supprimer(conn, client_id):
    if _client(conn, client_id) is None:
        return _introuvable()
    try:
        with transaction(conn):
            erreurs = supprimer_client_noyau(conn, client_id)
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return redirection(f"/client/{client_id}?" + urlencode({"err": " ".join(erreurs)[:300]}))
    return redirection("/clients?ok=client_supprime")


ROUTES_CLIENTS = [
    ("GET", r"^/secteurs$", lambda c, q, f, *g: page_secteurs(c, q)),
    ("POST", r"^/secteurs/ajouter$", lambda c, q, f, *g: _secteur_action(c, lambda: ajouter_secteur(c, f.get("libelle"), f.get("ville"))[1], "secteur_ajoute")),
    ("POST", r"^/secteurs/([a-z0-9_]+)/renommer$", lambda c, q, f, code: _secteur_action(c, lambda: renommer_secteur(c, code, f.get("libelle")), "secteur_maj")),
    ("POST", r"^/secteurs/([a-z0-9_]+)/supprimer$", lambda c, q, f, code: _secteur_action(c, lambda: supprimer_secteur(c, code), "secteur_supprime")),
    ("GET", r"^/clients$", lambda c, q, f, *g: page_clients(c, q)),
    ("GET", r"^/client/(\d+)$", lambda c, q, f, i: page_client(c, int(i), q)),
    ("GET", r"^/client/(\d+)/modifier$", lambda c, q, f, i: page_client_modifier(c, int(i))),
    ("POST", r"^/client/(\d+)/modifier$", lambda c, q, f, i: client_modifier(c, int(i), f)),
    ("POST", r"^/client/(\d+)/supprimer$", lambda c, q, f, i: client_supprimer(c, int(i))),
    ("GET", r"^/client/(\d+)/chantier/nouveau$", lambda c, q, f, i: page_chantier_nouveau(c, int(i))),
    ("POST", r"^/client/(\d+)/chantier/nouveau$", lambda c, q, f, i: chantier_creer(c, int(i), f)),
]
