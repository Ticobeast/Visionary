"""Pages d'une fiche : soumission ou chantier (même fiche, autre nom) : formulaire, consultation / modification, paiements, duplication.

Règles appliquées ici :
  * une SOUMISSION se remplit comme on veut : rien n'est obligatoire. Pour l'ACCEPTER (elle devient un chantier « À planifier »),
    le programme vérifie les conditions (noyau.CONDITIONS_ACCEPTATION) et demande de compléter ce qui manque ;
  * le client (nom, adresse, coordonnées) est en LECTURE SEULE sur toutes les pages d'une fiche, avant et après
    l'enregistrement : il ne se modifie que depuis sa fiche (bouton « Modifier le client »). Le serveur relit
    toujours le client dans la base, quoi que le navigateur envoie ;
  * le statut ne se choisit jamais à la main : boutons Accepter / Refuser (soumission), Journée (planification), Terminer, Annuler ;
  * un chantier « Terminé » est verrouillé : on le consulte et on peut encaisser (le client est considéré comme facturé d'office), rien d'autre ;
  * jamais de solde négatif : un paiement ne peut pas dépasser ce qu'il reste à payer ;
  * pour un chantier, la durée estimée est obligatoire ; la durée réelle n'apparaît qu'au moment de la clôture et se préremplit.
"""
import datetime
import sqlite3

from urllib.parse import quote, urlencode

from composants import liens_pdf, lien_telecharger
from photos import bloc as bloc_photos
from documents import facture_possible
from noyau import (COLONNES, MSG_MODIFIE_ENTRE_TEMPS, STATUTS_SOUMISSION, TYPES_AVEC_BOIS, VERROU, _txt, alias_types_travaux, appliquer_secteur, cle,
                   dupliquer_chantier, empreinte, encaisser, libelles_manques, lire_ligne, lister_secteurs, manques_pour_accepter,
                   mettre_a_jour_fiche, remettre_en_soumission, supprimer_chantier as supprimer_chantier_noyau, transaction, travaux_depuis_formulaire,
                   valeurs_client)
from vue import (libelle_statut, est_admin, LIBELLES_MODE, LIBELLES_PAIEMENT, MODES, adresses, argent, avance, badge, badge_statut, bloc_options_travaux,
                 bloc_types, case_taxes, champ, champ_modalite, client_avance, client_essentiel, esc, gabarit, heures, liste, lien_maps, lien_tel,
                 redirection, texte_attente, url_fiche, utilisateur_courant, zone)


def types_triees(conn):
    """Types de travaux, alphabétiques sans tenir compte des accents, « Autre » en dernier."""
    return sorted(conn.execute("SELECT code, libelle FROM types_travaux"), key=lambda t: (t[0] == "autre", cle(t[1])))


def valeurs_vides():
    """Valeurs par défaut d'un nouveau client + chantier : la date de la demande est celle d'aujourd'hui."""
    return {"client_sms_ok": "1", "province": "QC", "statut": "soumission", "date_soumission": datetime.date.today().isoformat()}


def valeurs_chantier(conn, chantier_id):
    """(valeurs du chantier + de son client sous forme de textes, client_id), ou None."""
    cols = ["client_id", "description", "statut", "date_soumission", "date_prevue", "duree_estimee_h", "duree_reelle_h",
            "prix_ht", "tps", "tvq", "modalite_paiement", "dossier_photos",
            "nacelle", "debarrasser_bois", "bois_format"]
    r = conn.execute(f"SELECT {', '.join(cols)} FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return None
    fmt = {"duree_estimee_h": lambda x: f"{x:g}", "duree_reelle_h": lambda x: f"{x:g}",
           "nacelle": lambda x: "1" if x else "", "debarrasser_bois": lambda x: "1" if x else "",
           "prix_ht": lambda x: f"{x:.2f}", "tps": lambda x: f"{x:.2f}" if x else "", "tvq": lambda x: f"{x:.2f}" if x else ""}
    d = {c: _txt(x, fmt.get(c)) for c, x in zip(cols, r)}
    for code, precision in conn.execute("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = ?", (chantier_id,)):
        d[f"type_{code}"] = "1"
        d[f"precision_{code}"] = precision or ""
    client_id = r[0]
    d.update(valeurs_client(conn, client_id))
    return d, client_id


def appliquer_options(brut, form, travaux, exige=True):
    """Options de la job (cases du formulaire) dans la ligne brute ; retourne les erreurs.

    Le format du bois n'a de sens que si le bois n'est pas débarrassé : il est alors exigé pour un abattage / élagage
    (sauf dans une soumission, où rien n'est obligatoire).
    """
    brut["nacelle"] = "1" if form.get("nacelle") else "0"
    brut["debarrasser_bois"] = "1" if form.get("debarrasser_bois") else "0"
    brut["bois_format"] = "" if brut["debarrasser_bois"] == "1" else form.get("bois_format", "")
    if exige and brut["debarrasser_bois"] == "0" and not brut["bois_format"] and any(code in TYPES_AVEC_BOIS for code, _ in travaux):
        return ["bois_format : précise le format du bois laissé sur place (16 pouces ou 4 pieds), ou coche « Débarrasser le bois »"]
    return []


def lire_formulaire(conn, form, client_id=None, chantier_id=None):
    """Valide un formulaire de soumission ou de chantier.

    Avec client_id, le client vient TOUJOURS de la base (jamais du formulaire). Le statut n'est jamais choisi dans le
    formulaire : une création est toujours une « Soumission » (rien d'obligatoire) ; sur une fiche existante le serveur garde
    le statut et la date de la base (les boutons Accepter, Refuser, Journée... les changent).
    """
    brut = {c: form.get(c, "") for c in COLONNES}
    if chantier_id is None:                                                # création : toujours une soumission
        statut, date_actuelle = "soumission", None
    else:
        statut, date_actuelle = conn.execute("SELECT statut, date_prevue FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    soumission = statut in STATUTS_SOUMISSION
    erreurs_secteur = []
    if client_id:
        brut.update(valeurs_client(conn, client_id))
    else:
        brut["client_sms_ok"] = "1" if form.get("client_sms_ok") else "0"
        erreurs_secteur = appliquer_secteur(conn, brut, requis=not soumission)       # la ville vient du secteur choisi
    brut["statut"], brut["date_prevue"] = statut, date_actuelle or ""
    for c in ("paiement_date", "paiement_montant", "paiement_mode"):               # un paiement ne s'enregistre jamais ici (page du chantier)
        brut[c] = ""
    if chantier_id is None:
        brut["date_soumission"] = brut["date_soumission"] or datetime.date.today().isoformat()
    brut["taxes_auto"] = "1" if form.get("taxes_auto") else ""
    travaux, valeurs_travaux = travaux_depuis_formulaire(conn, form)
    brut.update(valeurs_travaux)
    brut["type_travaux"] = travaux
    erreurs_bois = appliquer_options(brut, form, travaux, exige=not soumission)
    v, erreurs = lire_ligne(brut, alias_types_travaux(conn), taxes_auto=bool(form.get("taxes_auto")))
    if erreurs_secteur:
        erreurs = [e for e in erreurs if "ville est obligatoire" not in e]
    return brut, v, erreurs_secteur + erreurs + erreurs_bois


# ---------------------------------------------------------------------------
# Formulaires
# ---------------------------------------------------------------------------
def _erreurs_html(erreurs):
    if not erreurs:
        return ""
    return ('<div class="erreurs"><strong>À corriger avant d\'enregistrer :</strong><ul>'
            + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>")


def cartes_chantier(conn, valeurs, creation, soumission=False):
    """(essentiel, avancé) : l'essentiel en clair ; le reste dans « Paramètres avancés ».

    Essentiel : travaux, options (nacelle, bois), durée estimée, prix, description. soumission=True : rien n'est obligatoire.
    Le statut n'est jamais un champ : il est affiché (et change avec les boutons de la page).
    La durée réelle n'existe pas à la création ; ensuite elle n'apparaît (dans les paramètres avancés) que pour un
    chantier « Planifié » et reste vide : à « Terminé », elle reprend la durée estimée.
    """
    taxes = " checked" if valeurs.get("taxes_auto") else ""
    statut_date = ""
    if not creation and valeurs.get("date_prevue"):
        statut_date = (f'<div><label>Date des travaux</label><div><b>{esc(valeurs["date_prevue"])}</b> '
                       '<span class="doux">(se change dans la page Journée)</span></div></div>')
    exige = {} if soumission else {"required": True}
    if soumission:
        aide = ('<p class="doux">Rien n\'est obligatoire : remplis ce que tu sais. Pour <b>accepter</b> la soumission, il faudra le nom, le téléphone, '
                "l'adresse, le secteur, les travaux, la durée et le prix : le programme demandera ce qui manque.</p>")
    else:
        aide = ('<p class="doux">Durée = temps passé sur place, en heures décimales (2,5 = 2 h 30) : <b>obligatoire</b>, '
                'elle sert à calculer les heures de la journée.</p>')
    essentiel = f"""<div class="carte"><h2>Travaux</h2><div class="grille">
{bloc_types(types_triees(conn), valeurs)}
{bloc_options_travaux(valeurs)}
{statut_date}
{champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal", placeholder="2,5", **exige)}
{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal", placeholder="480,00")}
{case_taxes("taxes_auto", taxes)}
{zone("description", "Description (imprimée sur la feuille de route)", valeurs)}</div>
{aide}</div>"""

    duree_reelle = ""
    if not creation and valeurs.get("statut") == "planifie":
        duree_reelle = champ("duree_reelle_h", "Durée réelle (heures)", valeurs, inputmode="decimal", placeholder="comme l'estimée")
    avance_html = f"""<div class="carte"><h2>Dates et taxes</h2><div class="grille">
{champ("date_soumission", "Date de la demande de soumission", valeurs, "date")}{duree_reelle}
{champ("tps", "TPS ($)", valeurs, inputmode="decimal")}{champ("tvq", "TVQ ($)", valeurs, inputmode="decimal")}
{champ_modalite(valeurs)}</div>
<p class="doux pc-seul">TPS : laisse vide pour la calculer (case « Ajouter TPS et TVQ » cochée). Le statut ne se choisit pas : il change avec les boutons (Accepter ou Refuser une soumission, la page Journée pour planifier, Terminer, Annuler). À « Terminé », la durée réelle reprend la durée estimée.</p></div>"""
    avance_html += f"""<div class="carte pc-seul"><h2>Fichiers</h2><div class="grille">
{champ("dossier_photos", "Dossier de photos (chemin dans data/)", valeurs, placeholder="photos/2026/2026-06-14_gagnon")}</div></div>"""
    return essentiel, avance_html


def formulaire_nouveau(conn, valeurs, erreurs=()):
    """Nouvelle SOUMISSION (client + travaux) : rien n'est obligatoire. Le reste est en « Paramètres avancés »."""
    essentiel, avance_chantier = cartes_chantier(conn, valeurs, creation=True, soumission=True)
    return (f'{_erreurs_html(erreurs)}<form method="post" action="/nouveau">{client_essentiel(valeurs, lister_secteurs(conn), exige=False)}{essentiel}'
            f'{avance(client_avance(valeurs) + avance_chantier, ouvert=bool(erreurs))}'
            '<div class="barre"><button type="submit">Créer la soumission</button><a class="bouton secondaire annuler" href="/soumissions">Annuler</a></div></form>'
            '<p class="doux">La soumission créée, tu reviens à la fiche du client. Elle s\'ouvre ensuite depuis l\'onglet Soumissions.</p>')


def carte_client_lecture(conn, client_id, retour=""):
    """Client d'une fiche : AFFICHÉ, jamais modifiable ici (le bouton mène à sa fiche de modification, puis revient à `retour`)."""
    r = conn.execute("SELECT prenom, nom, entreprise, telephone, telephone_2, courriel, adresse, ville, province, code_postal, notes_acces"
                     " FROM clients WHERE id = ?", (client_id,)).fetchone()
    prenom, nom, entreprise, tel, tel2, courriel, adresse, ville, prov, cp, acces = r
    nom_complet = (" ".join(x for x in (prenom, nom) if x) + (f" · {entreprise}" if entreprise and (prenom or nom) else (entreprise or ""))) or "(client à identifier)"
    adresse_texte, adresse_maps = adresses(adresse, ville, prov, cp)
    tels = " · ".join(lien_tel(t) for t in (tel, tel2) if t and len(t) == 12) or "—"
    return (f'<div class="lecture-seule"><div class="barre"><h2 style="margin:0">{esc(nom_complet)}</h2>'
            f'<a class="bouton secondaire" href="/client/{client_id}/modifier{"?retour=" + quote(retour, safe="") if retour else ""}">Modifier le client</a>'
            f'<a class="bouton secondaire" href="/client/{client_id}">Fiche client</a></div>'
            f'<p style="margin:8px 0 0"><b>Adresse :</b> {lien_maps(adresse_maps, adresse_texte)}</p>'
            f'<p style="margin:4px 0 0"><b>Téléphone :</b> {tels}{" · <b>Courriel :</b> " + esc(courriel) if courriel else ""}'
            f'{" · <b>Accès :</b> " + esc(acces) if acces else ""}</p>'
            '<p class="doux" style="margin:8px 0 0">Lecture seule : le nom, l\'adresse et les coordonnées du client ne se modifient que depuis sa fiche.</p></div>')


# ---------------------------------------------------------------------------
# Page d'un chantier
# ---------------------------------------------------------------------------
def _bloc_lecture(conn, chantier_id, v):
    """Chantier terminé : toutes les informations, en lecture seule."""
    detail = conn.execute("SELECT travaux_detail FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()[0]
    lignes = [("Travaux", detail), ("Description", v.get("description")), ("Date de la demande", v.get("date_soumission")),
              ("Date des travaux", v.get("date_prevue")), ("Durée estimée", heures(float(v["duree_estimee_h"])) if v.get("duree_estimee_h") else ""),
              ("Durée réelle", heures(float(v["duree_reelle_h"])) if v.get("duree_reelle_h") else ""),
              ("Prix avant taxes", argent(float(v["prix_ht"])) if v.get("prix_ht") else ""),
              ("TPS", argent(float(v["tps"])) if v.get("tps") else ""), ("TVQ", argent(float(v["tvq"])) if v.get("tvq") else ""),
              ("Mode de règlement", LIBELLES_MODE.get(v.get("modalite_paiement"), "")), ("Photos", v.get("dossier_photos"))]
    corps = "".join(f"<dt>{esc(k)}</dt><dd>{esc(val)}</dd>" for k, val in lignes if val)
    return f'<div class="carte"><h2>Détails</h2><dl class="lecture">{corps}</dl></div>'


def _bloc_paiements(conn, chantier_id, prix, solde, termine, erreur_paiement):
    pmts = conn.execute("SELECT id, date_paiement, mode, montant, reference FROM paiements WHERE chantier_id = ? ORDER BY date_paiement, id", (chantier_id,)).fetchall()
    lignes = "".join(
        f'<tr><td class="c-date">{esc(d)}</td><td class="c-mode">{esc(LIBELLES_MODE[m])}</td><td class="c-ref">{esc(ref)}</td><td class="droite c-montant">{argent(mt)}</td>'
        f'<td class="droite col-actions"><form method="post" action="/paiement/{pid}/supprimer" onsubmit="return confirm(\'Supprimer ce paiement ?\')">'
        f'<button class="danger" type="submit" aria-label="Supprimer ce paiement" title="Supprimer ce paiement">Supprimer</button></form></td></tr>' for pid, d, m, mt, ref in pmts)
    table = (f'<div class="liste-defile"><table class="paiements"><thead><tr><th>Date</th><th>Mode</th><th>Référence</th><th class="droite">Montant</th><th></th></tr></thead><tbody>{lignes}</tbody></table></div>'
             if pmts else '<p class="doux">Aucun paiement enregistré.</p>')
    ev = {"paiement_date": datetime.date.today().isoformat(), "paiement_montant": f"{solde:.2f}" if solde and solde > 0 else "",
          **(erreur_paiement[1] if erreur_paiement else {})}
    err = ('<div class="erreurs"><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreur_paiement[0]) + "</ul></div>") if erreur_paiement else ""
    if prix is None:
        ajout = '<p class="doux">Le prix n\'est pas saisi : renseigne-le pour pouvoir enregistrer un paiement.</p>'
    elif solde is not None and solde <= 0:
        ajout = '<p class="doux">Ce chantier est entièrement payé. Un solde négatif est interdit : aucun autre paiement ne peut être ajouté.</p>'
    else:
        ajout = f"""{err}<form method="post" action="/chantier/{chantier_id}/paiement"><div class="grille">
{champ("paiement_date", "Date", ev, "date", required=True)}{champ("paiement_montant", "Montant ($)", ev, inputmode="decimal", required=True)}
{liste("paiement_mode", "Mode", [(m, LIBELLES_MODE[m]) for m in MODES], ev, required=True)}{champ("paiement_reference", "Référence (n° de chèque…)", ev)}
<div><label>&nbsp;</label><button type="submit">Ajouter le paiement</button></div></div></form>"""
    if prix is None or (solde is not None and solde <= 0):          # rien à ajouter : simple message
        bas = ajout
    else:                                                            # l'ajout reste à un clic ; ouvert s'il y a une erreur
        bas = f'<details style="margin-top:12px"{" open" if erreur_paiement else ""}><summary>+ Ajouter un paiement</summary>{ajout}</details>'
    return f'<div class="carte"><h2>Paiements</h2>{table}{bas}</div>'


def _autres_chantiers(conn, client_id, chantier_id):
    autres = conn.execute("SELECT chantier_id, type_libelle, attente_depuis, statut, genre"
                          " FROM v_chantiers WHERE client_id = ? AND chantier_id <> ? ORDER BY 3 DESC", (client_id, chantier_id)).fetchall()
    liste_html = ("<ul>" + "".join(f'<li><a href="{url_fiche(i, g)}">{esc(d)} — {esc(t)}</a> {badge_statut(st, g)}</li>'
                                   for i, t, d, st, g in autres) + "</ul>") if autres else '<p class="doux">Aucune autre fiche pour ce client.</p>'
    return (f'<div class="carte pc-seul"><h2>Autres soumissions et chantiers de ce client</h2>{liste_html}'
            f'<div class="barre"><a class="bouton secondaire" href="/client/{client_id}/soumission/nouveau">+ Nouvelle soumission pour ce client</a></div></div>')


def _formulaire_action(retour, action, chantier_id, texte, classe="", confirmation=""):
    """Petit formulaire à un bouton (Accepter, Refuser, Rouvrir...) : retour sur la page de la fiche."""
    confirmer = f' onsubmit="return confirm({esc(repr(confirmation))})"' if confirmation else ""
    return (f'<form class="mini" method="post" action="{action}"{confirmer}>'
            f'<input type="hidden" name="chantier_id" value="{chantier_id}"><input type="hidden" name="retour" value="{esc(retour)}">'
            f'<button type="submit"{f" class={classe}" if classe else ""}>{texte}</button></form>')


CONFIRMATION_REFUS = "Refuser cette soumission ? Elle ira dans les soumissions refusées (en bas de la liste) ; tu pourras la rouvrir."


def boutons_soumission(chantier_id, retour, retour_accepter=None, pdf=True):
    """Accepter / En attente / Refuser : les boutons rapides d'une soumission en cours (la page qui les place les enveloppe).
    `retour` : où l'on revient après avoir refusé ; `retour_accepter` (par défaut le même) : où l'on revient après avoir accepté
    ou mis en attente. « En attente » ouvre une petite page (date de reprise, ou jusqu'à nouvel ordre)."""
    return (f'<form class="mini" method="post" action="/soumission/{chantier_id}/accepter">'
            f'<input type="hidden" name="retour" value="{esc(retour_accepter or retour)}"><button type="submit">Accepter</button></form>'
            f'<a class="bouton secondaire" href="/soumission/{chantier_id}/attente?retour={quote(retour_accepter or retour, safe="")}">En attente</a>'
            f'<form class="mini" method="post" action="/soumission/{chantier_id}/refuser" onsubmit="return confirm({esc(repr(CONFIRMATION_REFUS))})">'
            f'<input type="hidden" name="retour" value="{esc(retour)}"><button type="submit" class="secondaire">Refuser</button></form>'
            + (liens_pdf(chantier_id, "soumission") if pdf else ""))


def _bloc_documents(chantier_id, statut, genre, soumission=False):
    """Carte « Documents pour le client » d'un chantier accepté : sa soumission, et sa facture (administrateur : elle montre les paiements)."""
    lignes = [("Soumission", liens_pdf(chantier_id, "soumission") + lien_telecharger(chantier_id, "soumission"))]
    if est_admin() and facture_possible(statut, genre):
        lignes.append(("Facture", liens_pdf(chantier_id, "facture") + lien_telecharger(chantier_id, "facture")))
    corps = "".join(f'<div class="ligne-document"><b>{nom}</b><div class="actions-page">{liens}</div></div>' for nom, liens in lignes)
    return f'<div class="carte documents{" documents-pc" if soumission else ""}"><h2>Documents pour le client</h2>{corps}</div>'


def page_chantier(conn, chantier_id, query, valeurs=None, erreurs=(), erreur_paiement=(), erreur_globale=None):
    trouve = valeurs_chantier(conn, chantier_id)
    if trouve is None:
        return gabarit("Introuvable", '<h1>Fiche introuvable</h1><p><a href="/chantiers">Retour aux chantiers</a> · <a href="/soumissions">Retour aux soumissions</a></p>'), 404
    depuis_base, client_id = trouve
    (statut, genre, stp, total, paye, solde, prix, tps, tvq, nom, detail, archive, date_prevue, duree, demande, cree_par, reprise) = conn.execute(
        "SELECT statut, genre, statut_paiement, total_ttc, paye, solde, prix_ht, tps, tvq, client_nom_complet, travaux_detail, archive,"
        " date_prevue, duree_estimee_h, date_soumission, cree_par, reprise_le FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    soumission = genre == "soumission"
    refusee = soumission and statut == "annule"
    termine = statut == "termine"
    base = "/soumission" if soumission else "/chantier"
    mot = "Soumission" if soumission else "Chantier"
    badges = badge_statut(statut, genre)
    if not soumission:
        badges += (badge(stp, LIBELLES_PAIEMENT[stp]) if stp != "sans_objet" else "") + ('<span class="badge">Archivé</span>' if archive else "")
    infos = " · ".join(x for x in (
        (f"Demande du {demande}" if soumission and demande else ""),
        (f"Prévu le {date_prevue}" if date_prevue and not termine else (f"Fait le {date_prevue}" if date_prevue else "")),
        (f"Durée {heures(duree)}" if duree else ""),
        (f"Ouverte par {cree_par}" if soumission and cree_par else ""),
        (f"En attente : {texte_attente(reprise)}" if statut == "en_attente" else "")) if x)
    montants = (f'<div class="montant">{argent(total) if total is not None and total else "prix à saisir"}'
                + (f'<small>{argent(prix)} + TPS {argent(tps)} + TVQ {argent(tvq)}</small>' if total else "")
                + (f'<small>reçu {argent(paye)} · solde <b>{argent(solde)}</b></small>' if total and est_admin() and not soumission else "") + "</div>")
    coin = (f'<a class="lien-pdf-coin" href="/soumission/{chantier_id}/pdf" target="_blank" rel="noopener" '
            'title="Ouvrir la soumission en PDF (nouvel onglet)">Soumission</a>') if soumission else ""      # téléphone : discret, en haut à droite
    resume = (f'<div class="carte resume-chantier">{coin}<div><div class="barre"><h2 style="margin:0">{esc(nom)}</h2>{badges}</div>'
              f'<p style="margin:10px 0 0"><b>Travaux :</b> {esc(detail) if detail else "à préciser"}</p>'
              f'{f"<p class=doux style=margin-bottom:0>{esc(infos)}</p>" if infos else ""}</div>{montants}</div>')

    def bouton(action, texte, classe="", confirmation=""):
        confirmer = f' onsubmit="return confirm({esc(repr(confirmation))})"' if confirmation else ""
        return (f'<form class="mini" method="post" action="/action/{action}"{confirmer}><input type="hidden" name="chantier_id" value="{chantier_id}">'
                f'<input type="hidden" name="retour" value="{base}/{chantier_id}"><button type="submit"{f" class={classe}" if classe else ""}>{texte}</button></form>')

    dupliquer = f'<a class="bouton secondaire" href="/chantier/{chantier_id}/dupliquer">Dupliquer</a>'
    manque = ""
    if soumission and not refusee:
        manques = manques_pour_accepter(conn, chantier_id)
        # depuis la fiche : accepter mène au nouveau chantier ; refuser reste sur la fiche (on peut la rouvrir tout de suite)
        boutons = boutons_soumission(chantier_id, f"/soumission/{chantier_id}", f"/chantier/{chantier_id}", pdf=False) + dupliquer
        if manques:
            manque = f'<p class="manque">Pour accepter, il manque encore : {esc(", ".join(libelles_manques(manques)))}.</p>'
    elif refusee:
        boutons = _formulaire_action(f"{base}/{chantier_id}", f"/soumission/{chantier_id}/rouvrir", chantier_id, "Rouvrir la soumission") + dupliquer
    else:
        boutons = dupliquer
        if statut == "planifie" and est_admin():
            boutons = f'<a class="bouton" href="/chantier/{chantier_id}?terminer={chantier_id}">Terminer</a>' + boutons
        if statut in ("a_planifier", "en_attente"):
            boutons = _formulaire_action(f"/chantier/{chantier_id}", f"/chantier/{chantier_id}/remettre-soumission", chantier_id, "Remettre en soumission", "secondaire",
                                         "Remettre ce chantier en soumission ? Il retourne dans l'onglet Soumissions.") + boutons
        if statut == "a_planifier":
            boutons = f'<a class="bouton secondaire" href="/chantier/{chantier_id}/attente?retour=%2Fchantier%2F{chantier_id}">Mettre en attente</a>' + boutons
        if statut == "en_attente":
            boutons = (_formulaire_action(f"/chantier/{chantier_id}", f"/chantier/{chantier_id}/reprendre", chantier_id, "Sortir de l'attente")
                       + f'<a class="bouton secondaire" href="/chantier/{chantier_id}/attente?retour=%2Fchantier%2F{chantier_id}">Changer la date</a>' + boutons)
        if statut == "annule" and est_admin():
            boutons = bouton("rouvrir", "Rouvrir (À planifier)") + boutons
    actions = f'<div class="actions-bloc"><div class="actions-page{" actions-sou" if soumission and not refusee else ""}">{boutons}</div>{manque}</div>'
    documents_client = _bloc_documents(chantier_id, statut, genre, soumission) + bloc_photos(conn, chantier_id)
    bandeau = ""
    if refusee:
        bandeau = ('<div class="verrou-termine">Soumission <b>refusée</b> : elle est dans la section « Refusées » de l\'onglet Soumissions. '
                   'Tu peux la rouvrir si le client a changé d\'avis.</div>')
    elif statut == "en_attente":
        bandeau = ('<div class="verrou-termine">Chantier <b>en attente</b> : il n\'est pas proposé dans la Journée. '
                   + ("Il redevient « À planifier » le <b>" + esc(reprise) + "</b>, ou dès que tu l'en sors." if reprise
                      else "Il reste en attente jusqu'à ce que tu l'en sortes.") + '</div>')
    elif statut == "annule":
        bandeau = ('<div class="verrou-termine">Chantier <b>annulé</b> : il est dans les archives. Il disparaît des journées ; '
                   'tu peux le rouvrir si l\'annulation était une erreur.</div>')
    corps = carte_client_lecture(conn, client_id, f"{base}/{chantier_id}")
    paiements = "" if (soumission or not est_admin()) else _bloc_paiements(conn, chantier_id, prix, solde, termine, erreur_paiement)   # finances : administrateur seulement
    autres = _autres_chantiers(conn, client_id, chantier_id)
    ce = "cette soumission" if soumission else "ce chantier"
    msg_suppr = f"Supprimer {ce} ? Le client sera aussi supprimé s’il n’a aucune autre fiche. Cette action est définitive."

    if termine:
        verrou = ('<div class="verrou-termine"><b>Chantier terminé : verrouillé en lecture seule.</b> Le client est considéré comme facturé. Il ne peut plus être modifié, '
                  'rouvert ni supprimé. Restent possibles : les paiements et la duplication (pour un travail récurrent).'
                  + (' Il est <b>archivé</b> (terminé et payé).' if archive else '') + '</div>')
        contenu = (f'<h1>Chantier #{chantier_id}</h1>{resume}{verrou}{actions}{documents_client}{corps}{paiements}'
                   f'{avance(_bloc_lecture(conn, chantier_id, depuis_base) + autres)}')
    elif refusee:
        suppression = (f'<div class="carte"><h2>Supprimer</h2><form method="post" action="/soumission/{chantier_id}/supprimer" '
                       f'onsubmit="return confirm({esc(repr(msg_suppr))})"><button class="danger" type="submit">Supprimer cette soumission</button></form></div>'
                       if est_admin() else "")
        contenu = f'<h1>Soumission #{chantier_id}</h1>{resume}{bandeau}{actions}{documents_client}{corps}{avance(_bloc_lecture(conn, chantier_id, depuis_base) + autres + suppression)}'
    else:
        essentiel, avance_chantier = cartes_chantier(conn, valeurs if valeurs is not None else depuis_base, creation=False, soumission=soumission)
        annuler = ('<button class="danger" type="submit" form="annuler-chantier" onclick="return confirm(\'Annuler ce chantier ? Il disparaît de sa journée '
                   'et va dans les archives.\')">Annuler le chantier</button> ' if statut != "annule" and not soumission else "")
        supprimer = (f'<button class="danger" type="submit" form="supprimer-chantier" onclick="return confirm({esc(repr(msg_suppr))})">'
                     f'Supprimer {ce}</button>')
        danger = f'<div class="carte"><h2>{"Supprimer" if soumission else "Annuler ou supprimer"}</h2><div class="barre">{annuler}{supprimer}</div></div>'
        fermer = "/soumissions" if soumission else "/chantiers"
        formulaire = (f'{_erreurs_html(erreurs)}<form method="post" action="{base}/{chantier_id}">'
                      f'<input type="hidden" name="empreinte" value="{empreinte(depuis_base)}">{essentiel}'
                      '<div class="barre" style="margin-bottom:16px"><button type="submit">Enregistrer les modifications</button>'
                      f'<a class="bouton secondaire fermer" href="{fermer}">Fermer</a></div>'
                      f'{avance(avance_chantier + autres + (danger if est_admin() else ""), ouvert=bool(erreurs))}</form>'
                      f'<form id="supprimer-chantier" method="post" action="{base}/{chantier_id}/supprimer"></form>'
                      f'<form id="annuler-chantier" method="post" action="/action/annuler"><input type="hidden" name="chantier_id" value="{chantier_id}">'
                      f'<input type="hidden" name="retour" value="{base}/{chantier_id}"></form>')
        contenu = f'<h1>{mot} #{chantier_id}</h1>{resume}{bandeau}{actions}{documents_client}{corps}{paiements}{formulaire}'
    return gabarit(f"{mot} {chantier_id}", contenu, query.get("ok") if query else None, erreur_globale or (query.get("err") if query else None))


def _genre_et_statut(conn, chantier_id):
    r = conn.execute("SELECT genre, statut FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    return r if r else (None, None)


def modifier(conn, chantier_id, form):
    trouve = valeurs_chantier(conn, chantier_id)
    if trouve is None:
        return page_chantier(conn, chantier_id, {})
    actuel, client_id = trouve
    genre, statut = _genre_et_statut(conn, chantier_id)
    base = url_fiche(chantier_id, genre)
    if genre == "soumission" and statut == "annule":
        return page_chantier(conn, chantier_id, {}, erreur_globale="Soumission refusée : rouvre-la d'abord pour la modifier.")
    if form.get("empreinte") and form["empreinte"] != empreinte(actuel):        # quelqu'un a modifié la fiche depuis l'ouverture du formulaire
        return page_chantier(conn, chantier_id, {}, erreur_globale=MSG_MODIFIE_ENTRE_TEMPS)
    brut, v, erreurs = lire_formulaire(conn, form, client_id=client_id, chantier_id=chantier_id)     # le client vient de la base
    if not erreurs:
        try:
            with transaction(conn):
                erreurs = mettre_a_jour_fiche(conn, chantier_id, v)
            if not erreurs:
                return redirection(f"{base}?ok=maj")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    if erreurs == [VERROU]:
        return page_chantier(conn, chantier_id, {}, erreur_globale=VERROU)
    return page_chantier(conn, chantier_id, {}, valeurs=brut, erreurs=erreurs)


def ajouter_paiement(conn, chantier_id, form):
    brut = {c: form.get(c, "") for c in ("paiement_date", "paiement_montant", "paiement_mode", "paiement_reference")}
    avant = conn.execute("SELECT statut FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    try:
        with transaction(conn):
            erreurs = encaisser(conn, chantier_id, brut["paiement_montant"], brut["paiement_mode"], brut["paiement_date"] or None,
                                brut["paiement_reference"])
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return page_chantier(conn, chantier_id, {}, erreur_paiement=(erreurs, brut))
    # chantier « Planifié » : on propose ensuite de le passer à « Terminé » (fenêtre de confirmation)
    proposer = f"&terminer={chantier_id}" if avant and avant[0] == "planifie" else ""
    return redirection(f"/chantier/{chantier_id}?ok=paiement{proposer}")


def supprimer_paiement(conn, paiement_id):
    ligne = conn.execute("SELECT chantier_id FROM paiements WHERE id = ?", (paiement_id,)).fetchone()
    if ligne is None:
        return gabarit("Introuvable", "<h1>Paiement introuvable</h1>"), 404
    with transaction(conn):
        conn.execute("DELETE FROM paiements WHERE id = ?", (paiement_id,))
    return redirection(f"/chantier/{ligne[0]}?ok=paiement_supprime")


def supprimer_chantier(conn, chantier_id):
    trouve = valeurs_chantier(conn, chantier_id)
    if trouve is None:
        return gabarit("Introuvable", "<h1>Fiche introuvable</h1>"), 404
    genre, _ = _genre_et_statut(conn, chantier_id)
    try:
        with transaction(conn):
            erreurs = supprimer_chantier_noyau(conn, chantier_id)
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return page_chantier(conn, chantier_id, {}, erreur_globale=" ".join(erreurs))
    return redirection("/soumissions?ok=soumission_supprimee" if genre == "soumission" else "/chantiers?ok=supprime")


# ---------------------------------------------------------------------------
# Duplication : nouvelle soumission d'après un chantier existant (travaux récurrents)
# ---------------------------------------------------------------------------
def _form_duplication(conn, chantier_id, valeurs, erreurs=()):
    r = conn.execute("SELECT client_nom_complet, travaux_detail, statut, genre FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    taxes = " checked" if valeurs.get("avec_taxes") else ""
    return (f'{_erreurs_html(erreurs)}<div class="lecture-seule"><b>Fiche d\'origine :</b> {esc(r[0])} — {esc(r[1])} '
            f'({esc(libelle_statut(r[2], r[3]))}). Les travaux, la durée, le prix et le mode de règlement sont repris ; les dates repartent '
            f'd\'aujourd\'hui ({datetime.date.today().isoformat()}) ; les paiements et la durée réelle ne sont pas copiés.</div>'
            f'<form method="post" action="/chantier/{chantier_id}/dupliquer"><div class="carte"><h2>Nouvelle soumission</h2><div class="grille">'
            f'{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal")}'
            f'{case_taxes("avec_taxes", taxes)}'
            f'{champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal")}'
            f'{zone("description", "Description (notes)", valeurs)}</div></div>'
            f'<div class="barre"><button type="submit">Créer la soumission</button><a class="bouton secondaire annuler" href="{url_fiche(chantier_id, "soumission" if r[3] == "soumission" else "chantier")}">Annuler</a></div></form>')


def page_dupliquer(conn, chantier_id):
    r = conn.execute("SELECT prix_ht, tps, tvq, duree_estimee_h, description FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return gabarit("Introuvable", "<h1>Chantier introuvable</h1>"), 404
    valeurs = {"prix_ht": f"{r[0]:.2f}" if r[0] is not None else "", "avec_taxes": "1" if (r[1] or 0) + (r[2] or 0) > 0 else "",
               "duree_estimee_h": f"{r[3]:g}" if r[3] else "", "description": r[4] or ""}
    return gabarit("Dupliquer le chantier", f'<h1>Dupliquer le chantier #{chantier_id}</h1>{_form_duplication(conn, chantier_id, valeurs)}')


def dupliquer(conn, chantier_id, form):
    if valeurs_chantier(conn, chantier_id) is None:
        return gabarit("Introuvable", "<h1>Chantier introuvable</h1>"), 404
    try:
        with transaction(conn):
            nouveau, erreurs = dupliquer_chantier(conn, chantier_id, prix_ht=form.get("prix_ht", ""), avec_taxes=bool(form.get("avec_taxes")),
                                                  duree=form.get("duree_estimee_h", ""), description=form.get("description", ""),
                                                  cree_par=(utilisateur_courant() or {}).get("nom"))
    except sqlite3.IntegrityError as e:
        nouveau, erreurs = None, [f"Refusé par la base : {e}"]
    if erreurs:
        valeurs = {c: form.get(c, "") for c in ("prix_ht", "duree_estimee_h", "description")}
        valeurs["avec_taxes"] = "1" if form.get("avec_taxes") else ""
        return gabarit("Dupliquer le chantier", f'<h1>Dupliquer le chantier #{chantier_id}</h1>{_form_duplication(conn, chantier_id, valeurs, erreurs)}')
    return redirection(f"/soumission/{nouveau}?ok=duplique")


def _vers_la_bonne_page(conn, chantier_id, query, genre_attendu):
    """/chantier/N et /soumission/N montrent la même fiche : on va à la page qui correspond à son état."""
    genre, _ = _genre_et_statut(conn, chantier_id)
    if genre is not None and genre != genre_attendu:
        return redirection(url_fiche(chantier_id, genre) + ("?" + urlencode(query) if query else ""))
    return page_chantier(conn, chantier_id, query)


def remettre_en_soumission_page(conn, chantier_id, form):
    try:
        with transaction(conn):
            erreurs = remettre_en_soumission(conn, chantier_id)
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return page_chantier(conn, chantier_id, {}, erreur_globale=" ".join(erreurs))
    return redirection(f"/soumission/{chantier_id}?ok=remise_soumission")


ROUTES_CHANTIER = [
    ("GET", r"^/chantier/(\d+)$", lambda c, q, f, i: _vers_la_bonne_page(c, int(i), q, "chantier")),
    ("POST", r"^/chantier/(\d+)/remettre-soumission$", lambda c, q, f, i: remettre_en_soumission_page(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)$", lambda c, q, f, i: modifier(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/paiement$", lambda c, q, f, i: ajouter_paiement(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/supprimer$", lambda c, q, f, i: supprimer_chantier(c, int(i))),
    ("GET", r"^/chantier/(\d+)/dupliquer$", lambda c, q, f, i: page_dupliquer(c, int(i))),
    ("POST", r"^/chantier/(\d+)/dupliquer$", lambda c, q, f, i: dupliquer(c, int(i), f)),
    ("POST", r"^/paiement/(\d+)/supprimer$", lambda c, q, f, i: supprimer_paiement(c, int(i))),
]
