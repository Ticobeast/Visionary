"""Pages « clients » : liste, fiche client, modification du client, et formulaire SIMPLIFIÉ de nouveau chantier.

Le formulaire simplifié s'ouvre depuis la fiche d'un client : le nom et l'adresse sont verrouillés (affichés,
non modifiables : le serveur ignore tout ce que le navigateur enverrait à leur sujet) et seuls les éléments
essentiels sont demandés : travaux à faire, prix, modalité de paiement, notes.
"""
import sqlite3

from noyau import (COLONNES, Resultat, _txt, alias_types_travaux, cle, creer_chantier, lire_client, lire_ligne,
                   mettre_a_jour_client, transaction, travaux_depuis_formulaire, valeurs_client)
from vue import (LIBELLES_PAIEMENT, LIBELLES_STATUT, argent, badge, bloc_types, carte_adresse, carte_client, champ,
                 champ_modalite, esc, gabarit, heures, lien_maps, redirection, zone)


def _types(conn):
    return sorted(conn.execute("SELECT code, libelle FROM types_travaux"), key=lambda t: (t[0] == "autre", cle(t[1])))


def _nom_client(c):
    """c : dict avec prenom, nom, entreprise."""
    personne = " ".join(x for x in (c.get("prenom"), c.get("nom")) if x)
    if personne and c.get("entreprise"):
        return f"{personne} · {c['entreprise']}"
    return personne or c.get("entreprise") or ""


def _client(conn, client_id):
    r = conn.execute("SELECT id, prenom, nom, entreprise, telephone, telephone_2, courriel, sms_ok, adresse, ville, province,"
                     " code_postal, notes_acces, notes, geocode_statut FROM clients WHERE id = ?", (client_id,)).fetchone()
    if r is None:
        return None
    cols = ["id", "prenom", "nom", "entreprise", "telephone", "telephone_2", "courriel", "sms_ok", "adresse", "ville",
            "province", "code_postal", "notes_acces", "notes", "geocode_statut"]
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
    q = query.get("q", "").strip()
    lignes = conn.execute(
        "SELECT cl.id, cl.prenom, cl.nom, cl.entreprise, cl.telephone, cl.adresse, cl.ville, cl.province, cl.code_postal,"
        " (SELECT count(*) FROM chantiers ch WHERE ch.client_id = cl.id),"
        " (SELECT COALESCE(SUM(solde), 0) FROM v_chantiers v WHERE v.client_id = cl.id AND v.statut_paiement IN ('non_facture','a_payer','partiel'))"
        " FROM clients cl ORDER BY cl.nom, cl.entreprise").fetchall()
    if q:
        mots = cle(q).split()
        lignes = [r for r in lignes if all(m in cle(" ".join(str(x) for x in r[1:9] if x)) for m in mots)]
    corps = ""
    for cid, prenom, nom, entreprise, tel, adresse, ville, prov, cp, nb, du in lignes[:300]:
        maps = f"{adresse}, {ville}, {prov}" + (f" {cp}" if cp else "") + ", Canada"
        corps += (f'<tr><td><a href="/client/{cid}">{esc(_nom_client(dict(prenom=prenom, nom=nom, entreprise=entreprise)))}</a></td>'
                  f'<td>{esc(_tel(tel))}</td><td>{lien_maps(maps, f"{adresse}, {ville}")}</td><td class="droite">{nb}</td>'
                  f'<td class="droite">{esc(argent(du) if du else "")}</td></tr>')
    tableau = (f'<div class="liste-defile"><table><thead><tr><th>Client</th><th>Téléphone</th><th>Adresse</th><th class="droite">Chantiers</th>'
               f'<th class="droite">À recevoir / facturer</th></tr></thead><tbody>{corps}</tbody></table></div>'
               if corps else '<div class="carte">Aucun client. <a href="/nouveau">Créer le premier ?</a></div>')
    recherche = (f'<form class="recherche" method="get" action="/clients"><input type="search" name="q" value="{esc(q)}" '
                 'placeholder="Chercher : nom, téléphone, adresse, ville…"><button type="submit">Chercher</button></form>')
    return gabarit("Clients", f'<h1>Clients</h1>{recherche}{tableau}')


def page_client(conn, client_id, query):
    c = _client(conn, client_id)
    if c is None:
        return _introuvable()
    chantiers = conn.execute(
        "SELECT chantier_id, COALESCE(date_prevue, date_soumission, ''), type_libelle, statut, statut_paiement, total_ttc, solde"
        " FROM v_chantiers WHERE client_id = ? ORDER BY 2 DESC, chantier_id DESC", (client_id,)).fetchall()
    lignes = "".join(
        f'<tr><td><a href="/chantier/{i}">{esc(d) or "sans date"}</a></td><td>{esc(t)}</td><td>{badge(st, LIBELLES_STATUT[st])}</td>'
        f'<td>{badge(sp, LIBELLES_PAIEMENT[sp]) if sp != "sans_objet" else ""}</td><td class="droite">{argent(tot)}</td>'
        f'<td class="droite">{argent(sol) if sp in ("non_facture", "a_payer", "partiel") else ""}</td></tr>'
        for i, d, t, st, sp, tot, sol in chantiers)
    historique = (f'<div class="liste-defile"><table><thead><tr><th>Date</th><th>Travaux</th><th>Statut</th><th>Paiement</th>'
                  f'<th class="droite">Total</th><th class="droite">Solde</th></tr></thead><tbody>{lignes}</tbody></table></div>'
                  if lignes else '<p class="doux">Aucun chantier pour ce client.</p>')
    tels = " · ".join(esc(_tel(t)) for t in (c["telephone"], c["telephone_2"]) if t) or "—"

    def ligne(libelle, contenu_html):
        return f'<p style="margin:6px 0 0"><b>{libelle} :</b> {contenu_html}</p>'
    fiche = (f'<div class="carte"><div class="barre"><h2 style="margin:0">{esc(_nom_client(c))}</h2></div>'
             + ligne("Adresse", lien_maps(c["adresse_maps"], c["adresse_maps"].replace(", Canada", "")))
             + ligne("Téléphone", tels + ("" if c["sms_ok"] else " · <b>pas de rappels par texto</b>"))
             + (ligne("Courriel", esc(c["courriel"])) if c["courriel"] else "")
             + (ligne("Accès", esc(c["notes_acces"])) if c["notes_acces"] else "")
             + (ligne("Notes", esc(c["notes"])) if c["notes"] else "") + "</div>")
    actions = (f'<div class="barre" style="margin-bottom:16px"><a class="bouton" href="/client/{client_id}/chantier/nouveau">+ Nouveau chantier</a>'
               f'<a class="bouton secondaire" href="/client/{client_id}/modifier">Modifier le client</a></div>')
    return gabarit(_nom_client(c), f'<h1>Fiche client</h1>{fiche}{actions}<h2>Chantiers</h2>{historique}', query.get("ok"))


# ---------------------------------------------------------------------------
# Modification du client (la seule façon de changer son nom ou son adresse)
# ---------------------------------------------------------------------------
def _form_client(conn, client_id, valeurs, erreurs=()):
    err = ""
    if erreurs:
        err = ('<div class="erreurs"><strong>À corriger :</strong><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>")
    return (f'{err}<form method="post" action="/client/{client_id}/modifier">{carte_client(valeurs)}{carte_adresse(valeurs)}'
            f'<div class="barre"><button type="submit">Enregistrer</button><a class="bouton secondaire" href="/client/{client_id}">Annuler</a></div></form>')


def page_client_modifier(conn, client_id):
    valeurs = valeurs_client(conn, client_id)
    if valeurs is None:
        return _introuvable()
    return gabarit("Modifier le client", f'<h1>Modifier le client</h1><p class="doux">Ces informations s\'appliquent à tous les chantiers de ce client.</p>{_form_client(conn, client_id, valeurs)}')


def client_modifier(conn, client_id, form):
    if valeurs_client(conn, client_id) is None:
        return _introuvable()
    brut = {c: form.get(c, "") for c in COLONNES}
    brut["client_sms_ok"] = "1" if form.get("client_sms_ok") else "0"
    v, erreurs = lire_client(brut)
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
<div class="carte"><h2>Travaux à faire</h2><div class="grille">{bloc_types(_types(conn), valeurs)}</div></div>
<div class="carte"><h2>Prix et paiement</h2><div class="grille">
{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal", placeholder="480,00")}
<div><label>&nbsp;</label><label style="color:inherit"><input type="checkbox" name="taxes_auto" value="1"{taxes}>Ajouter TPS 5 % et TVQ 9,975 %</label></div>
{champ_modalite(valeurs)}</div></div>
<div class="carte"><h2>Notes</h2><div class="grille">{zone("description", "Notes (description du chantier, imprimée sur la feuille de route)", valeurs)}</div></div>
<div class="barre"><button type="submit">Créer le chantier</button><a class="bouton secondaire" href="/client/{client_id}">Annuler</a></div></form>
<p class="doux">Le chantier est créé « Accepté » (à planifier). La date, la durée et le statut se règlent ensuite depuis le tableau de bord ou les tournées.</p>"""


def page_chantier_nouveau(conn, client_id):
    if _client(conn, client_id) is None:
        return _introuvable()
    return gabarit("Nouveau chantier", f'<h1>Nouveau chantier</h1>{_form_simplifie(conn, client_id, {})}')


def chantier_creer(conn, client_id, form):
    if _client(conn, client_id) is None:
        return _introuvable()
    travaux, valeurs = travaux_depuis_formulaire(conn, form)
    saisie = {**valeurs, **{c: form.get(c, "") for c in ("prix_ht", "modalite_paiement", "description")},
              "taxes_auto": "1" if form.get("taxes_auto") else ""}
    # Nom, adresse et coordonnées viennent TOUJOURS de la base : ce que le navigateur enverrait est ignoré.
    brut = {c: "" for c in COLONNES}
    brut.update(valeurs_client(conn, client_id))
    brut.update({c: saisie[c] for c in ("prix_ht", "modalite_paiement", "description")})
    brut.update(statut="accepte", type_travaux=travaux)
    v, erreurs = lire_ligne(brut, alias_types_travaux(conn), taxes_auto=bool(saisie["taxes_auto"]))
    if not erreurs:
        try:
            with transaction(conn):
                chantier_id = creer_chantier(conn, client_id, v, Resultat(), lambda m: None, verifier_doublon=False)
            return redirection(f"/chantier/{chantier_id}?ok=client_cree")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    return gabarit("Nouveau chantier", f'<h1>Nouveau chantier</h1>{_form_simplifie(conn, client_id, saisie, erreurs)}')


ROUTES_CLIENTS = [
    ("GET", r"^/clients$", lambda c, q, f, *g: page_clients(c, q)),
    ("GET", r"^/client/(\d+)$", lambda c, q, f, i: page_client(c, int(i), q)),
    ("GET", r"^/client/(\d+)/modifier$", lambda c, q, f, i: page_client_modifier(c, int(i))),
    ("POST", r"^/client/(\d+)/modifier$", lambda c, q, f, i: client_modifier(c, int(i), f)),
    ("GET", r"^/client/(\d+)/chantier/nouveau$", lambda c, q, f, i: page_chantier_nouveau(c, int(i))),
    ("POST", r"^/client/(\d+)/chantier/nouveau$", lambda c, q, f, i: chantier_creer(c, int(i), f)),
]
