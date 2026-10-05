"""Pages d'un chantier : formulaire de saisie, consultation / modification, paiements, facture, duplication.

Règles appliquées ici :
  * le client (nom, adresse, coordonnées) est en LECTURE SEULE sur toutes les pages d'un chantier, avant et après
    l'enregistrement : il ne se modifie que depuis sa fiche (bouton « Modifier le client »). Le serveur relit
    toujours le client dans la base, quoi que le navigateur envoie ;
  * un chantier « Terminé » est verrouillé : on le consulte, on peut le facturer et encaisser, rien d'autre ;
  * jamais de solde négatif : un paiement ne peut pas dépasser ce qu'il reste à payer ;
  * la durée estimée est obligatoire ; la durée réelle n'apparaît qu'au moment de la clôture et se préremplit.
"""
import datetime
import sqlite3

from noyau import (COLONNES, STATUTS, VERROU, _txt, alias_types_travaux, cle, dupliquer_chantier, encaisser, facturer,
                   lire_ligne, mettre_a_jour_fiche, supprimer_chantier as supprimer_chantier_noyau, transaction,
                   travaux_depuis_formulaire, valeurs_client)
from vue import (LIBELLES_MODE, LIBELLES_PAIEMENT, LIBELLES_STATUT, MODES, argent, avance, badge, bloc_types,
                 champ, champ_modalite, client_avance, client_essentiel, esc, gabarit, heures, liste, lien_maps, redirection, zone)


def types_triees(conn):
    """Types de travaux, alphabétiques sans tenir compte des accents, « Autre » en dernier."""
    return sorted(conn.execute("SELECT code, libelle FROM types_travaux"), key=lambda t: (t[0] == "autre", cle(t[1])))


def valeurs_vides():
    """Valeurs par défaut d'un nouveau client + chantier : la date de la demande est celle d'aujourd'hui."""
    return {"client_sms_ok": "1", "province": "QC", "statut": "soumission", "date_soumission": datetime.date.today().isoformat()}


def valeurs_chantier(conn, chantier_id):
    """(valeurs du chantier + de son client sous forme de textes, client_id), ou None."""
    cols = ["client_id", "description", "statut", "date_soumission", "date_prevue", "duree_estimee_h", "duree_reelle_h",
            "prix_ht", "tps", "tvq", "modalite_paiement", "numero_facture", "date_facture", "dossier_photos",
            "fichier_papier", "ref_papier"]
    r = conn.execute(f"SELECT {', '.join(cols)} FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()
    if r is None:
        return None
    fmt = {"duree_estimee_h": lambda x: f"{x:g}", "duree_reelle_h": lambda x: f"{x:g}",
           "prix_ht": lambda x: f"{x:.2f}", "tps": lambda x: f"{x:.2f}" if x else "", "tvq": lambda x: f"{x:.2f}" if x else ""}
    d = {c: _txt(x, fmt.get(c)) for c, x in zip(cols, r)}
    for code, precision in conn.execute("SELECT type_travaux, precision FROM chantier_travaux WHERE chantier_id = ?", (chantier_id,)):
        d[f"type_{code}"] = "1"
        d[f"precision_{code}"] = precision or ""
    client_id = r[0]
    d.update(valeurs_client(conn, client_id))
    return d, client_id


def lire_formulaire(conn, form, client_id=None):
    """Valide un formulaire de chantier. Avec client_id, le client vient TOUJOURS de la base (jamais du formulaire)."""
    brut = {c: form.get(c, "") for c in COLONNES}
    if client_id:
        brut.update(valeurs_client(conn, client_id))
    else:
        brut["client_sms_ok"] = "1" if form.get("client_sms_ok") else "0"
        brut["statut"] = brut["statut"] or "soumission"                    # création : valeurs par défaut des paramètres avancés
        brut["date_soumission"] = brut["date_soumission"] or datetime.date.today().isoformat()
    brut["taxes_auto"] = "1" if form.get("taxes_auto") else ""
    travaux, valeurs_travaux = travaux_depuis_formulaire(conn, form)
    brut.update(valeurs_travaux)
    brut["type_travaux"] = travaux
    v, erreurs = lire_ligne(brut, alias_types_travaux(conn), taxes_auto=bool(form.get("taxes_auto")))
    return brut, v, erreurs


# ---------------------------------------------------------------------------
# Formulaires
# ---------------------------------------------------------------------------
def _erreurs_html(erreurs):
    if not erreurs:
        return ""
    return ('<div class="erreurs"><strong>À corriger avant d\'enregistrer :</strong><ul>'
            + "".join(f"<li>{esc(e)}</li>" for e in erreurs) + "</ul></div>")


def cartes_chantier(conn, valeurs, creation):
    """(essentiel, avancé) : l'essentiel d'un chantier en clair ; le reste dans « Paramètres avancés ».

    Essentiel : travaux, durée estimée, prix, description (et, pour un chantier existant, statut et date des travaux).
    La durée réelle n'existe pas à la création ; ensuite elle n'apparaît (dans les paramètres avancés) que pour un
    chantier « Planifié » et reste vide : à « Terminé », elle reprend la durée estimée.
    """
    taxes = " checked" if valeurs.get("taxes_auto") else ""
    statut_date = ""
    if not creation:
        statut_date = (f'{liste("statut", "Statut", [(s, LIBELLES_STATUT[s]) for s in STATUTS], valeurs, required=True)}'
                       f'{champ("date_prevue", "Date des travaux (prévue, puis réalisée)", valeurs, "date")}')
    essentiel = f"""<div class="carte"><h2>Travaux</h2><div class="grille">
{bloc_types(types_triees(conn), valeurs)}
{statut_date}
{champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal", placeholder="2,5", required=True)}
{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal", placeholder="480,00")}
<div><label>&nbsp;</label><label style="color:inherit"><input type="checkbox" name="taxes_auto" value="1"{taxes}>Ajouter TPS 5 % et TVQ 9,975 %</label></div>
{zone("description", "Description (imprimée sur la feuille de route)", valeurs)}</div>
<p class="doux">Durée = temps passé sur place, en heures décimales (2,5 = 2 h 30) : <b>obligatoire</b>, elle sert à calculer les heures de la journée.</p></div>"""

    duree_reelle = ""
    if not creation and valeurs.get("statut") == "planifie":
        duree_reelle = champ("duree_reelle_h", "Durée réelle (heures)", valeurs, inputmode="decimal", placeholder="comme l'estimée")
    statut_creation = ""
    if creation:
        statut_creation = (f'{liste("statut", "Statut", [(s, LIBELLES_STATUT[s]) for s in STATUTS], valeurs)}'
                           f'{champ("date_prevue", "Date des travaux (obligatoire si Planifié ou Terminé)", valeurs, "date")}')
    avance_html = f"""<div class="carte"><h2>Dates, taxes et facture</h2><div class="grille">
{statut_creation}{champ("date_soumission", "Date de la demande ou de la soumission", valeurs, "date")}{duree_reelle}
{champ("tps", "TPS ($) — vide : calculée si la case est cochée", valeurs, inputmode="decimal")}{champ("tvq", "TVQ ($)", valeurs, inputmode="decimal")}
{champ_modalite(valeurs)}{champ("numero_facture", "N° de facture", valeurs)}{champ("date_facture", "Date de la facture / du reçu", valeurs, "date")}</div>
<p class="doux">Statut « Planifié » ou « Terminé » : la date des travaux est obligatoire. Quand le chantier passe à « Terminé », la durée réelle reprend la durée estimée.</p></div>"""
    if creation:
        avance_html += f"""<div class="carte"><h2>Paiement déjà reçu <span class="doux">(facultatif)</span></h2><div class="grille">
{champ("paiement_date", "Date du paiement", valeurs, "date")}{champ("paiement_montant", "Montant reçu (taxes incluses)", valeurs, inputmode="decimal", placeholder="551,88")}
{liste("paiement_mode", "Mode", [(m, LIBELLES_MODE[m]) for m in MODES], valeurs, vide="—")}</div>
<p class="doux">Le montant ne peut pas dépasser le total du chantier (jamais de solde négatif). D'autres paiements s'ajoutent ensuite sur la page du chantier.</p></div>"""
    avance_html += f"""<div class="carte"><h2>Fichiers</h2><div class="grille">
{champ("ref_papier", "Où est la fiche papier ?", valeurs, placeholder="Classeur A, fiche 12")}
{champ("fichier_papier", "Scan de la fiche (chemin dans data/)", valeurs, placeholder="papier/2026/gagnon.pdf")}
{champ("dossier_photos", "Dossier de photos (chemin dans data/)", valeurs, placeholder="photos/2026/2026-06-14_gagnon")}</div></div>"""
    return essentiel, avance_html


def formulaire_nouveau(conn, valeurs, erreurs=()):
    """Nouveau CLIENT + chantier : l'essentiel d'abord (client, travaux, durée, prix) ; le reste en « Paramètres avancés »."""
    essentiel, avance_chantier = cartes_chantier(conn, valeurs, creation=True)
    return (f'{_erreurs_html(erreurs)}<form method="post" action="/nouveau">{client_essentiel(valeurs)}{essentiel}'
            f'{avance(client_avance(valeurs) + avance_chantier, ouvert=bool(erreurs))}'
            '<div class="barre"><button type="submit">Créer le chantier</button><a class="bouton secondaire" href="/">Annuler</a></div></form>'
            '<p class="doux">Le chantier créé, tu pourras l\'ouvrir pour voir ou compléter tous les détails.</p>')


def carte_client_lecture(conn, client_id):
    """Client d'un chantier : AFFICHÉ, jamais modifiable ici."""
    r = conn.execute("SELECT prenom, nom, entreprise, telephone, telephone_2, courriel, adresse, ville, province, code_postal, notes_acces"
                     " FROM clients WHERE id = ?", (client_id,)).fetchone()
    prenom, nom, entreprise, tel, tel2, courriel, adresse, ville, prov, cp, acces = r
    nom_complet = " ".join(x for x in (prenom, nom) if x) + (f" · {entreprise}" if entreprise and (prenom or nom) else (entreprise or ""))
    adresse_maps = f"{adresse}, {ville}, {prov}" + (f" {cp}" if cp else "") + ", Canada"
    tels = " · ".join(f"{t[2:5]}-{t[5:8]}-{t[8:]}" for t in (tel, tel2) if t and len(t) == 12) or "—"
    return (f'<div class="lecture-seule"><div class="barre"><h2 style="margin:0">🔒 {esc(nom_complet)}</h2>'
            f'<a class="bouton secondaire" href="/client/{client_id}/modifier">Modifier le client</a>'
            f'<a class="bouton secondaire" href="/client/{client_id}">Fiche client</a></div>'
            f'<p style="margin:8px 0 0"><b>Adresse :</b> {lien_maps(adresse_maps, adresse_maps.replace(", Canada", ""))}</p>'
            f'<p style="margin:4px 0 0"><b>Téléphone :</b> {esc(tels)}{" · <b>Courriel :</b> " + esc(courriel) if courriel else ""}'
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
              ("Mode de règlement", LIBELLES_MODE.get(v.get("modalite_paiement"), "")), ("N° de facture", v.get("numero_facture")),
              ("Date de la facture", v.get("date_facture")), ("Fiche papier", v.get("ref_papier")),
              ("Scan de la fiche", v.get("fichier_papier")), ("Photos", v.get("dossier_photos"))]
    corps = "".join(f"<dt>{esc(k)}</dt><dd>{esc(val)}</dd>" for k, val in lignes if val)
    return f'<div class="carte"><h2>Détails</h2><dl class="lecture">{corps}</dl></div>'


def _bloc_paiements(conn, chantier_id, prix, solde, termine, erreur_paiement):
    pmts = conn.execute("SELECT id, date_paiement, mode, montant, reference FROM paiements WHERE chantier_id = ? ORDER BY date_paiement, id", (chantier_id,)).fetchall()
    lignes = "".join(
        f'<tr><td>{esc(d)}</td><td>{esc(LIBELLES_MODE[m])}</td><td>{esc(ref)}</td><td class="droite">{argent(mt)}</td>'
        f'<td class="droite"><form method="post" action="/paiement/{pid}/supprimer" onsubmit="return confirm(\'Supprimer ce paiement ?\')">'
        f'<button class="danger" type="submit">Supprimer</button></form></td></tr>' for pid, d, m, mt, ref in pmts)
    table = (f'<table><thead><tr><th>Date</th><th>Mode</th><th>Référence</th><th class="droite">Montant</th><th></th></tr></thead><tbody>{lignes}</tbody></table>'
             if pmts else '<p class="doux">Aucun paiement enregistré.</p>')
    ev = {"paiement_date": datetime.date.today().isoformat(), "paiement_montant": f"{solde:.2f}" if solde and solde > 0 else "",
          **(erreur_paiement[1] if erreur_paiement else {})}
    err = ('<div class="erreurs"><ul>' + "".join(f"<li>{esc(e)}</li>" for e in erreur_paiement[0]) + "</ul></div>") if erreur_paiement else ""
    if prix is None:
        ajout = '<p class="doux">Le prix n\'est pas saisi : renseigne-le pour pouvoir enregistrer un paiement.</p>'
    elif solde is not None and solde <= 0:
        ajout = '<p class="doux">✔ Ce chantier est entièrement payé. Un solde négatif est interdit : aucun autre paiement ne peut être ajouté.</p>'
    else:
        ajout = f"""{err}<form method="post" action="/chantier/{chantier_id}/paiement"><div class="grille">
{champ("paiement_date", "Date", ev, "date", required=True)}{champ("paiement_montant", f"Montant ($) — au plus {solde:.2f}".replace(".", ","), ev, inputmode="decimal", required=True)}
{liste("paiement_mode", "Mode", [(m, LIBELLES_MODE[m]) for m in MODES], ev, required=True)}{champ("paiement_reference", "Référence (n° de chèque…)", ev)}
<div><label>&nbsp;</label><button type="submit">Ajouter le paiement</button></div></div></form>"""
    if prix is None or (solde is not None and solde <= 0):          # rien à ajouter : simple message
        bas = ajout
    else:                                                            # l'ajout reste à un clic ; ouvert s'il y a une erreur
        bas = f'<details style="margin-top:12px"{" open" if erreur_paiement else ""}><summary>+ Ajouter un paiement</summary>{ajout}</details>'
    return f'<div class="carte"><h2>Paiements</h2>{table}{bas}</div>'


def _autres_chantiers(conn, client_id, chantier_id):
    autres = conn.execute("SELECT chantier_id, type_libelle, COALESCE(date_prevue, date_soumission, ''), statut"
                          " FROM v_chantiers WHERE client_id = ? AND chantier_id <> ? ORDER BY 3 DESC", (client_id, chantier_id)).fetchall()
    liste_html = ("<ul>" + "".join(f'<li><a href="/chantier/{i}">{esc(d)} — {esc(t)}</a> {badge(s, LIBELLES_STATUT[s])}</li>'
                                   for i, t, d, s in autres) + "</ul>") if autres else '<p class="doux">Aucun autre chantier pour ce client.</p>'
    return (f'<div class="carte"><h2>Autres chantiers de ce client</h2>{liste_html}'
            f'<div class="barre"><a class="bouton secondaire" href="/client/{client_id}/chantier/nouveau">+ Nouveau chantier pour ce client</a></div></div>')


def page_chantier(conn, chantier_id, query, valeurs=None, erreurs=(), erreur_paiement=(), erreur_globale=None):
    trouve = valeurs_chantier(conn, chantier_id)
    if trouve is None:
        return gabarit("Introuvable", '<h1>Chantier introuvable</h1><p><a href="/chantiers">Retour à la liste</a></p>'), 404
    depuis_base, client_id = trouve
    (statut, stp, total, paye, solde, prix, tps, tvq, nom, detail, archive, date_facture, date_prevue, duree) = conn.execute(
        "SELECT statut, statut_paiement, total_ttc, paye, solde, prix_ht, tps, tvq, client_nom_complet, travaux_detail, archive, date_facture,"
        " date_prevue, duree_estimee_h FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    termine = statut == "termine"
    badges = (badge(statut, LIBELLES_STATUT[statut]) + (badge(stp, LIBELLES_PAIEMENT[stp]) if stp != "sans_objet" else "")
              + ('<span class="badge">📦 Archivé</span>' if archive else ""))
    infos = " · ".join(x for x in (f"Prévu le {date_prevue}" if date_prevue and not termine else (f"Fait le {date_prevue}" if date_prevue else ""),
                                   f"⏱ {heures(duree)}" if duree else "") if x)
    montants = (f'<div class="montant">{argent(total) if total is not None and total else "prix à saisir"}'
                + (f'<small>{argent(prix)} + TPS {argent(tps)} + TVQ {argent(tvq)}</small>' if total else "")
                + (f'<small>reçu {argent(paye)} · solde <b>{argent(solde)}</b></small>' if total else "") + "</div>")
    resume = (f'<div class="carte resume-chantier"><div><div class="barre"><h2 style="margin:0">{esc(nom)}</h2>{badges}</div>'
              f'<p style="margin:10px 0 0"><b>Travaux :</b> {esc(detail)}</p>'
              f'{f"<p class=doux style=margin-bottom:0>{esc(infos)}</p>" if infos else ""}</div>{montants}</div>')
    actions = (f'<div class="barre" style="margin-bottom:16px"><a class="bouton secondaire" href="/chantier/{chantier_id}/dupliquer">Dupliquer le chantier</a></div>')
    corps = carte_client_lecture(conn, client_id)
    paiements = _bloc_paiements(conn, chantier_id, prix, solde, termine, erreur_paiement)
    autres = _autres_chantiers(conn, client_id, chantier_id)

    if termine:
        facturation = ""
        if not date_facture and prix is not None:
            facturation = (f'<div class="carte"><h2>Facturation</h2><form method="post" action="/chantier/{chantier_id}/facturer"><div class="grille">'
                           f'{champ("date_facture", "Date de la facture", {"date_facture": datetime.date.today().isoformat()}, "date")}'
                           f'{champ("numero_facture", "N° de facture (facultatif)", {})}'
                           f'<div><label>&nbsp;</label><button type="submit">Marquer comme facturé</button></div></div></form></div>')
        verrou = ('<div class="verrou-termine"><b>🔒 Chantier terminé : verrouillé en lecture seule.</b> Il ne peut plus être modifié, rouvert '
                  'ni supprimé. Restent possibles : la facturation, les paiements et la duplication (pour un travail récurrent).'
                  + (' Il est <b>archivé</b> (terminé et payé).' if archive else '') + '</div>')
        contenu = (f'<h1>Chantier #{chantier_id}</h1>{resume}{verrou}{actions}{corps}{facturation}{paiements}'
                   f'{avance(_bloc_lecture(conn, chantier_id, depuis_base) + autres)}')
    else:
        essentiel, avance_chantier = cartes_chantier(conn, valeurs if valeurs is not None else depuis_base, creation=False)
        danger = (f'<div class="carte"><h2>Zone de danger</h2><button class="danger" type="submit" form="supprimer-chantier" '
                  f'onclick="return confirm(\'Supprimer ce chantier ? Le client sera aussi supprimé s\\\'il n\\\'a aucun autre chantier. Cette action est définitive.\')">'
                  f'Supprimer ce chantier</button></div>')
        formulaire = (f'{_erreurs_html(erreurs)}<form method="post" action="/chantier/{chantier_id}">{essentiel}'
                      '<div class="barre" style="margin-bottom:16px"><button type="submit">Enregistrer les modifications</button>'
                      '<a class="bouton secondaire" href="/">Annuler</a></div>'
                      f'{avance(avance_chantier + autres + danger, ouvert=bool(erreurs))}</form>'
                      f'<form id="supprimer-chantier" method="post" action="/chantier/{chantier_id}/supprimer"></form>')
        contenu = f'<h1>Chantier #{chantier_id}</h1>{resume}{actions}{corps}{paiements}{formulaire}'
    return gabarit(f"Chantier {chantier_id}", contenu, query.get("ok") if query else None, erreur_globale or (query.get("err") if query else None))


def modifier(conn, chantier_id, form):
    trouve = valeurs_chantier(conn, chantier_id)
    if trouve is None:
        return page_chantier(conn, chantier_id, {})
    _, client_id = trouve
    brut, v, erreurs = lire_formulaire(conn, form, client_id=client_id)     # le client vient de la base, pas du formulaire
    if not erreurs:
        try:
            with transaction(conn):
                erreurs = mettre_a_jour_fiche(conn, chantier_id, v)
            if not erreurs:
                return redirection(f"/chantier/{chantier_id}?ok=maj")
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
    if valeurs_chantier(conn, chantier_id) is None:
        return gabarit("Introuvable", "<h1>Chantier introuvable</h1>"), 404
    try:
        with transaction(conn):
            erreurs = supprimer_chantier_noyau(conn, chantier_id)
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return page_chantier(conn, chantier_id, {}, erreur_globale=" ".join(erreurs))
    return redirection("/chantiers?ok=supprime")


def facturer_chantier(conn, chantier_id, form):
    try:
        with transaction(conn):
            erreurs = facturer(conn, chantier_id, form.get("date_facture") or None, form.get("numero_facture"))
    except sqlite3.IntegrityError as e:
        erreurs = [f"Refusé par la base : {e}"]
    if erreurs:
        return page_chantier(conn, chantier_id, {}, erreur_globale=" ; ".join(erreurs))
    return redirection(f"/chantier/{chantier_id}?ok=facture")


# ---------------------------------------------------------------------------
# Duplication : nouvelle soumission d'après un chantier existant (travaux récurrents)
# ---------------------------------------------------------------------------
def _form_duplication(conn, chantier_id, valeurs, erreurs=()):
    r = conn.execute("SELECT client_nom_complet, travaux_detail, statut FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    taxes = " checked" if valeurs.get("avec_taxes") else ""
    return (f'{_erreurs_html(erreurs)}<div class="lecture-seule"><b>Chantier d\'origine :</b> {esc(r[0])} — {esc(r[1])} '
            f'({esc(LIBELLES_STATUT[r[2]])}). Les travaux, la durée, le prix et le mode de règlement sont repris ; les dates repartent '
            f'd\'aujourd\'hui ({datetime.date.today().isoformat()}) ; les paiements, la facture et la durée réelle ne sont pas copiés.</div>'
            f'<form method="post" action="/chantier/{chantier_id}/dupliquer"><div class="carte"><h2>Nouvelle soumission</h2><div class="grille">'
            f'{champ("prix_ht", "Prix avant taxes ($)", valeurs, inputmode="decimal")}'
            f'<div><label>&nbsp;</label><label style="color:inherit"><input type="checkbox" name="avec_taxes" value="1"{taxes}>Ajouter TPS 5 % et TVQ 9,975 %</label></div>'
            f'{champ("duree_estimee_h", "Durée estimée (heures)", valeurs, inputmode="decimal", required=True)}'
            f'{zone("description", "Description (notes)", valeurs)}</div></div>'
            f'<div class="barre"><button type="submit">Créer la soumission</button><a class="bouton secondaire" href="/chantier/{chantier_id}">Annuler</a></div></form>')


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
                                                  duree=form.get("duree_estimee_h", ""), description=form.get("description", ""))
    except sqlite3.IntegrityError as e:
        nouveau, erreurs = None, [f"Refusé par la base : {e}"]
    if erreurs:
        valeurs = {c: form.get(c, "") for c in ("prix_ht", "duree_estimee_h", "description")}
        valeurs["avec_taxes"] = "1" if form.get("avec_taxes") else ""
        return gabarit("Dupliquer le chantier", f'<h1>Dupliquer le chantier #{chantier_id}</h1>{_form_duplication(conn, chantier_id, valeurs, erreurs)}')
    return redirection(f"/chantier/{nouveau}?ok=duplique")


ROUTES_CHANTIER = [
    ("GET", r"^/chantier/(\d+)$", lambda c, q, f, i: page_chantier(c, int(i), q)),
    ("POST", r"^/chantier/(\d+)$", lambda c, q, f, i: modifier(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/paiement$", lambda c, q, f, i: ajouter_paiement(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/facturer$", lambda c, q, f, i: facturer_chantier(c, int(i), f)),
    ("POST", r"^/chantier/(\d+)/supprimer$", lambda c, q, f, i: supprimer_chantier(c, int(i))),
    ("GET", r"^/chantier/(\d+)/dupliquer$", lambda c, q, f, i: page_dupliquer(c, int(i))),
    ("POST", r"^/chantier/(\d+)/dupliquer$", lambda c, q, f, i: dupliquer(c, int(i), f)),
    ("POST", r"^/paiement/(\d+)/supprimer$", lambda c, q, f, i: supprimer_paiement(c, int(i))),
]
