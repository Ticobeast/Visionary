"""Onglet Soumissions : la liste, les boutons rapides Accepter / Refuser, et la complétion avant l'acceptation.

Une soumission est un chantier pas encore accepté : même fiche, autre nom. On l'ouvre dès que le client appelle, avec ce
qu'on sait (rien n'est obligatoire). Accepter la met dans Chantiers, « À planifier », mais seulement si tout ce qu'il faut est
rempli (noyau.CONDITIONS_ACCEPTATION) : sinon le programme demande au soumissionneur de compléter ce qui manque, dans une
page qui ne montre que les champs manquants. Refuser la met dans les soumissions refusées (section du bas), d'où on peut la rouvrir.
"""
import datetime
import sqlite3
from urllib.parse import quote, urlencode

import raccourcis
from composants import avec_params, retour_valide
from listes import CRITERES, filtres_depuis, selection_soumissions
from noyau import (STATUTS_SOUMISSION, TYPES_AVEC_BOIS, accepter_soumission, appliquer_secteur, jours_attente, lire_client,
                   lister_secteurs, libelles_manques, manques_pour_accepter, mettre_a_jour_client, mettre_a_jour_fiche, priorite,
                   refuser_soumission, rouvrir_chantier, transaction, travaux_depuis_formulaire, valeurs_client)
from pages_chantier import (_formulaire_action, _genre_et_statut, _vers_la_bonne_page, boutons_soumission, lire_formulaire, modifier,
                            supprimer_chantier, types_triees, valeurs_chantier)
from vue import (argent, badge_attente, bloc_options_travaux, bloc_types, case_taxes, champ, champ_secteur, esc, gabarit, heures, redirection,
                 url_fiche, utilisateur_courant)

LIMITE_REFUSEES = 50
COURTS = {"nom": "nom", "telephone": "téléphone", "adresse": "adresse", "secteur": "secteur", "travaux": "travaux", "bois": "sort du bois",
          "duree": "durée", "prix": "prix"}


# ---------------------------------------------------------------------------
# La liste
# ---------------------------------------------------------------------------
def _tel(t):
    return f"{t[2:5]}-{t[5:8]}-{t[8:]}" if t and len(t) == 12 else (t or "")


def _table(conn, lignes, retour, refusees=False):
    aujourdhui = datetime.date.today()
    corps = ""
    for l in lignes:
        i = l["chantier_id"]
        nom = l["client_nom_complet"] if not l["entreprise"] or l["entreprise"] in l["client_nom_complet"] else f'{l["client_nom_complet"]} · {l["entreprise"]}'
        jours = jours_attente(l["attente_depuis"], aujourdhui)
        demande = esc(l["attente_depuis"] or "")
        if not refusees:
            demande += f'<div>{badge_attente(jours, priorite(jours))}</div>'
        if l["cree_par"]:
            demande += f'<div class="doux">par {esc(l["cree_par"])}</div>'
        manques = [] if refusees else manques_pour_accepter(conn, i)
        manque = f'<div class="manque">Il manque : {esc(", ".join(COURTS[c] for c in manques))}</div>' if manques else ""
        tel = f'<div class="doux">{esc(_tel(l["telephone"]))}</div>' if l["telephone"] else ""
        adresse = f'{esc(l["adresse"])}<div class="doux">{esc(l["secteur"] or l["ville"])}</div>' if l["adresse"] else '<span class="doux">—</span>'
        duree = f'<div class="doux">Durée {esc(heures(l["duree_estimee_h"]))}</div>' if l["duree_estimee_h"] else ""
        travaux = esc(l["type_libelle"]) if l["type_libelle"] else '<span class="doux">à préciser</span>'
        montant = f'<td class="montant">{esc(argent(l["total_ttc"]))}</td>' if l["total_ttc"] else '<td class="montant"><small>prix à saisir</small></td>'
        if refusees:
            action = f'<div class="actions-ligne">{_formulaire_action(retour, f"/soumission/{i}/rouvrir", i, "Rouvrir", "secondaire")}</div>'
        else:
            action = f'<div class="actions-ligne">{boutons_soumission(i, retour)}</div>'
        corps += (f'<tr><td>{demande}</td><td><a href="{url_fiche(i, "soumission")}">{esc(nom)}</a>{tel}{manque}</td><td>{adresse}</td>'
                  f'<td>{travaux}{duree}</td>{montant}<td class="col-actions">{action}</td></tr>')
    return ('<div class="liste-defile"><table class="tableau"><thead><tr><th>Demande</th><th>Client</th><th>Adresse</th><th>Travaux</th>'
            f'<th class="droite">Montant</th><th></th></tr></thead><tbody>{corps}</tbody></table></div>')


def page_soumissions(conn, query):
    u = utilisateur_courant()
    f = filtres_depuis(query, u["nom"] if u else None)
    en_cours = selection_soumissions(conn, f, False)
    refusees = selection_soumissions(conn, f, True)
    total_refusees = conn.execute("SELECT count(*) FROM v_chantiers WHERE genre = 'soumission' AND archive = 1").fetchone()[0]
    demande = {c: query.get(c, "") for c in CRITERES if query.get(c)}
    retour = "/soumissions" + ("?" + urlencode(demande) if demande else "")

    attente = "".join(f'<option value="{c}"{" selected" if f.get("attente") == c else ""}>{esc(t)}</option>'
                      for c, t in (("", "Tous les délais"), ("relance", "À relancer (7 jours et plus)"), ("urgente", "30 jours et plus")))
    auteurs = [r[0] for r in conn.execute("SELECT DISTINCT cree_par FROM chantiers WHERE cree_par IS NOT NULL AND cree_par <> '' ORDER BY cree_par COLLATE NOCASE")]
    choisi = f.get("par", "")
    par = '<option value="">Toutes les soumissions</option>' + "".join(
        f'<option value="{esc(a)}"{" selected" if a == choisi else ""}>Ouvertes par {esc(a)}</option>' for a in auteurs)
    select_par = f'<select name="par" aria-label="Ouverte par">{par}</select>' if auteurs else ""      # sans comptes, personne n'« ouvre » une soumission
    recherche = (f'<form class="recherche" method="get" action="/soumissions"><input type="search" name="q" value="{esc(f.get("q", ""))}" '
                 f'placeholder="Chercher : nom, téléphone, adresse, travaux…"><select name="attente" aria-label="Délai">{attente}</select>'
                 f'{select_par}<button type="submit">Chercher</button></form>')

    if en_cours:
        tableau = _table(conn, en_cours, retour)
    else:
        tableau = '<div class="carte">Aucune soumission en cours' + (" ne correspond à cette recherche." if demande else ".") + ' <a href="/nouveau">Ouvrir une soumission ?</a></div>'
    if refusees:
        suite = f'<p class="doux">{len(refusees[:LIMITE_REFUSEES])} plus récentes sur {len(refusees)} : utilise la recherche pour retrouver une ancienne soumission.</p>' if len(refusees) > LIMITE_REFUSEES else ""
        bas = _table(conn, refusees[:LIMITE_REFUSEES], retour, refusees=True) + suite
    else:
        bas = '<div class="carte doux">Aucune soumission refusée' + (" ne correspond à cette recherche." if demande else " pour l'instant.") + "</div>"
    lien_refusees = f' <a class="doux" href="#refusees">Refusées ({total_refusees})</a>' if total_refusees else ""
    section_refusees = (f'<h2 id="refusees" style="margin-top:32px">Refusées <small class="doux">({total_refusees})</small></h2>'
                        '<p class="doux">Soumissions refusées par le client. Elles ne sont plus dans les chantiers ; « Rouvrir » la remet en cours.</p>' + bas)
    contenu = (f'<h1>Soumissions{lien_refusees}</h1><div class="barre" style="margin-bottom:16px"><a class="bouton" href="/nouveau">+ Nouvelle soumission</a></div>'
               f'{raccourcis.barre(conn, "soumissions", query)}{recherche}{tableau}{section_refusees}')
    return gabarit("Soumissions", contenu, query.get("ok"), query.get("err"), large=True)


# ---------------------------------------------------------------------------
# Accepter, refuser, rouvrir
# ---------------------------------------------------------------------------
def _agir(conn, form, travail, ok, defaut="/soumissions"):
    retour = retour_valide(form.get("retour"), defaut)
    try:
        with transaction(conn):
            erreurs = travail()
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return redirection(avec_params(retour, err=" ; ".join(erreurs)[:300], ok=None))
    return redirection(avec_params(retour, ok=ok, err=None))


def _introuvable():
    return gabarit("Introuvable", '<h1>Soumission introuvable</h1><p><a href="/soumissions">Retour aux soumissions</a></p>'), 404


def post_accepter(conn, i, form):
    genre, statut = _genre_et_statut(conn, i)
    if genre is None:
        return _introuvable()
    retour = retour_valide(form.get("retour"), "/soumissions")
    if statut in STATUTS_SOUMISSION and manques_pour_accepter(conn, i):        # il manque des renseignements : on les demande
        return redirection(f"/soumission/{i}/completer?retour={quote(retour, safe='')}")
    return _agir(conn, form, lambda: accepter_soumission(conn, i), "soumission_acceptee")


def post_refuser(conn, i, form):
    if _genre_et_statut(conn, i)[0] is None:
        return _introuvable()
    return _agir(conn, form, lambda: refuser_soumission(conn, i), "soumission_refusee")


def post_rouvrir(conn, i, form):
    genre, statut = _genre_et_statut(conn, i)
    if genre != "soumission" or statut != "annule":
        return _agir(conn, form, lambda: ["seule une soumission refusée peut être rouverte"], "")
    return _agir(conn, form, lambda: rouvrir_chantier(conn, i), "soumission_rouverte")


# ---------------------------------------------------------------------------
# Compléter ce qui manque pour accepter
# ---------------------------------------------------------------------------
def _formulaire_completer(conn, i, manques, valeurs, retour, erreurs=(), message=None):
    secteurs = lister_secteurs(conn)
    nom, travaux, adresse = conn.execute("SELECT client_nom_complet, travaux_detail, adresse FROM v_chantiers WHERE chantier_id = ?", (i,)).fetchone()
    champs = []
    if "nom" in manques:
        champs += [champ("client_nom", "Nom", valeurs, autocomplete="off"), champ("client_prenom", "Prénom", valeurs, autocomplete="off"),
                   champ("client_entreprise", "Entreprise (si pas de nom)", valeurs),
                   '<p class="doux large" style="margin:-4px 0 0">Un nom, ou le nom d\'une entreprise, suffit.</p>']
    if "telephone" in manques:
        champs.append(champ("client_telephone", "Téléphone", valeurs, "tel", placeholder="450-555-0142", required=True))
    if "adresse" in manques:
        champs.append(champ("adresse", "Adresse (numéro + rue)", valeurs, large=True, required=True, placeholder="123 Rue des Érables"))
    if "secteur" in manques:
        champs.append(champ_secteur(secteurs, valeurs, requis=True))
    if "duree" in manques:
        champs.append(champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal", placeholder="2,5", required=True))
    if "prix" in manques:
        taxes = " checked" if valeurs.get("taxes_auto") else ""
        champs.append(champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal", placeholder="480,00", required=True))
        champs.append(case_taxes("taxes_auto", taxes))
    if "travaux" in manques:
        champs.append(bloc_types(types_triees(conn), valeurs))
    if "travaux" in manques or "bois" in manques:
        champs.append(bloc_options_travaux(valeurs))
    liste_manques = "".join(f"<li>{esc(t)}</li>" for t in libelles_manques(manques))
    err = ('<div class="erreurs"><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>") if erreurs else ""
    info = f'<div class="message">{esc(message)}</div>' if message else ""
    return (f'{info}{err}<div class="carte"><h2>{esc(nom)}</h2><p>{esc(travaux) if travaux else "travaux à préciser"}</p>'
            f'<p>Pour mettre cette soumission dans <b>Chantiers, À planifier</b>, il faut encore :</p><ul>{liste_manques}</ul></div>'
            f'<form method="post" action="/soumission/{i}/completer"><input type="hidden" name="retour" value="{esc(retour)}">'
            f'<div class="carte"><h2>À compléter</h2><div class="grille">{"".join(champs)}</div></div>'
            f'<div class="barre"><button type="submit">Enregistrer et accepter</button>'
            f'<a class="bouton secondaire" href="{esc(url_fiche(i, "soumission"))}">Annuler</a></div></form>')


def page_completer(conn, i, query, erreurs=(), valeurs=None, message=None):
    trouve = valeurs_chantier(conn, i)
    if trouve is None:
        return _introuvable()
    genre, statut = _genre_et_statut(conn, i)
    if statut not in STATUTS_SOUMISSION:
        return redirection(url_fiche(i, genre))
    manques = manques_pour_accepter(conn, i)
    retour = retour_valide(query.get("retour"), "/soumissions")
    if not manques:                                    # tout est déjà rempli : rien à compléter
        return redirection(url_fiche(i, genre))
    return gabarit(f"Accepter la soumission {i}", f'<h1>Accepter la soumission #{i}</h1>' + _formulaire_completer(
        conn, i, manques, valeurs if valeurs is not None else trouve[0], retour, erreurs, message), section="soumissions")


def post_completer(conn, i, form):
    trouve = valeurs_chantier(conn, i)
    if trouve is None:
        return _introuvable()
    actuel, client_id = trouve
    genre, statut = _genre_et_statut(conn, i)
    if statut not in STATUTS_SOUMISSION:
        return redirection(url_fiche(i, genre))
    retour = retour_valide(form.get("retour"), "/soumissions")
    manques = manques_pour_accepter(conn, i)
    erreurs = []
    # --- le client : seulement les renseignements qui manquent (jamais ceux déjà là)
    client = dict(valeurs_client(conn, client_id))
    champs_client = {"nom": ("client_nom", "client_prenom", "client_entreprise"), "telephone": ("client_telephone",),
                     "adresse": ("adresse",), "secteur": ("client_secteur",)}
    client_modifie = False
    for code, cles in champs_client.items():
        if code in manques:
            client_modifie = True
            for k in cles:
                client[k] = form.get(k, "")
    vc = None
    if client_modifie:
        erreurs += appliquer_secteur(conn, client, requis=False)
        vc, erreurs_client = lire_client(client, exige=False)
        erreurs += erreurs_client
    # --- la fiche : durée, prix, travaux et sort du bois s'ils manquent
    saisie = dict(actuel)
    if "duree" in manques:
        saisie["duree_estimee_h"] = form.get("duree_estimee_h", "")
    if "prix" in manques:
        saisie["prix_ht"] = form.get("prix_ht", "")
    if "travaux" in manques or "bois" in manques:
        _, valeurs_types = travaux_depuis_formulaire(conn, form)
        if "travaux" in manques:
            saisie = {k: v for k, v in saisie.items() if not k.startswith(("type_", "precision_"))}
            saisie.update(valeurs_types)
        saisie["nacelle"] = "1" if form.get("nacelle") else ""
        saisie["debarrasser_bois"] = "1" if form.get("debarrasser_bois") else ""
        saisie["bois_format"] = "" if saisie["debarrasser_bois"] else form.get("bois_format", "")
    saisie["taxes_auto"] = "1" if form.get("taxes_auto") else ""
    brut, v, erreurs_fiche = lire_formulaire(conn, saisie, client_id=client_id, chantier_id=i)
    erreurs += erreurs_fiche
    if ("travaux" in manques or "bois" in manques) and not erreurs and any(code in TYPES_AVEC_BOIS for code, _ in v["travaux"]) \
            and not v["debarrasser_bois"] and not v["bois_format"]:
        erreurs.append("bois_format : précise le format du bois laissé sur place (16 pouces ou 4 pieds), ou coche « Débarrasser le bois »")
    accepte = False
    if not erreurs:
        try:
            with transaction(conn):
                if vc is not None:
                    mettre_a_jour_client(conn, client_id, vc)
                erreurs = mettre_a_jour_fiche(conn, i, v)
                if not erreurs and not manques_pour_accepter(conn, i):
                    erreurs = accepter_soumission(conn, i)
                    accepte = not erreurs
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    if accepte:
        return redirection(avec_params(retour, ok="soumission_acceptee", err=None))
    reste = manques_pour_accepter(conn, i)
    if not erreurs and reste:
        erreurs = ["Ce qui a été saisi est enregistré, mais il manque encore : " + ", ".join(libelles_manques(reste)) + "."]
    if not reste and erreurs:                                           # plus rien à compléter mais l'acceptation a échoué
        return redirection(avec_params(retour, err=" ; ".join(erreurs)[:300], ok=None))
    formulaire = dict(form)
    return gabarit(f"Accepter la soumission {i}", f'<h1>Accepter la soumission #{i}</h1>' + _formulaire_completer(
        conn, i, reste or manques, formulaire, retour, erreurs), section="soumissions")


ROUTES_SOUMISSIONS = [
    ("GET", r"^/soumissions$", lambda c, q, f, *g: page_soumissions(c, q)),
    ("GET", r"^/soumission/(\d+)$", lambda c, q, f, i: _vers_la_bonne_page(c, int(i), q, "soumission")),
    ("POST", r"^/soumission/(\d+)$", lambda c, q, f, i: modifier(c, int(i), f)),
    ("POST", r"^/soumission/(\d+)/supprimer$", lambda c, q, f, i: supprimer_chantier(c, int(i))),
    ("POST", r"^/soumission/(\d+)/accepter$", lambda c, q, f, i: post_accepter(c, int(i), f)),
    ("POST", r"^/soumission/(\d+)/refuser$", lambda c, q, f, i: post_refuser(c, int(i), f)),
    ("POST", r"^/soumission/(\d+)/rouvrir$", lambda c, q, f, i: post_rouvrir(c, int(i), f)),
    ("GET", r"^/soumission/(\d+)/completer$", lambda c, q, f, i: page_completer(c, int(i), q)),
    ("POST", r"^/soumission/(\d+)/completer$", lambda c, q, f, i: post_completer(c, int(i), f)),
]
