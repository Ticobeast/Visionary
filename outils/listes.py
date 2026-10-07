"""Sélections des listes Chantiers et Soumissions, partagées par les pages et par les pastilles de raccourcis.

Les critères (`filtres`) sont ceux de la barre de recherche et des raccourcis :
  statut     statut d'un chantier (Chantiers seulement)
  paiement   « a_recevoir » ou un statut de paiement (Chantiers, administrateur)
  secteur    code du secteur
  attente    « urgente » (plus de 30 j), « surveiller » (7 à 30 j), « normale », ou « relance » (7 j et plus)
  par        compte qui a ouvert la soumission (« moi » = le compte connecté) (Soumissions)
  q          texte cherché (nom, téléphone, adresse, secteur, travaux...)
"""
import datetime

from noyau import SEUIL_SURVEILLER, STATUTS, cle, jours_attente, priorite
from vue import LIBELLES_PAIEMENT

CRITERES = ("statut", "paiement", "secteur", "attente", "par", "q")
ATTENTES = ("urgente", "surveiller", "normale", "relance")


def filtres_depuis(query, nom_utilisateur=None):
    """Critères valides d'une requête (les inconnus sont ignorés) ; « par=moi » devient le nom du compte connecté."""
    f = {c: (query.get(c) or "").strip() for c in CRITERES}
    if f["statut"] not in STATUTS:
        f["statut"] = ""
    if f["paiement"] != "a_recevoir" and f["paiement"] not in LIBELLES_PAIEMENT:
        f["paiement"] = ""
    if f["attente"] not in ATTENTES:
        f["attente"] = ""
    if f["par"] == "moi":
        f["par"] = nom_utilisateur or ""
    return {c: v for c, v in f.items() if v}


def _attente_ok(attente_depuis, voulue, aujourdhui):
    jours = jours_attente(attente_depuis, aujourdhui)
    if voulue == "relance":
        return jours >= SEUIL_SURVEILLER
    return priorite(jours) == voulue


def _colonnes(curseur, lignes):
    noms = [d[0] for d in curseur.description]
    return [dict(zip(noms, r)) for r in lignes]


def _texte(ligne, champs):
    return cle(" ".join(str(ligne[c]) for c in champs if ligne.get(c)))


def selection_chantiers(conn, f, archive):
    """Chantiers (jamais de soumissions) : actifs (archive=False) ou archives (annulés, terminés et payés)."""
    sql = ("SELECT chantier_id, client_nom_complet, entreprise, adresse, ville, telephone, travaux_detail, description, statut,"
           " statut_paiement, solde, date_prevue, attente_depuis, type_libelle, duree_estimee_h, total_ttc, secteur, genre"
           " FROM v_chantiers WHERE genre = 'chantier' AND archive = ?")
    params = [1 if archive else 0]
    if f.get("statut") in STATUTS:
        sql += " AND statut = ?"
        params.append(f["statut"])
    paiement = f.get("paiement")
    if paiement == "a_recevoir":
        sql += " AND statut_paiement IN ('a_payer', 'partiel')"
    elif paiement in LIBELLES_PAIEMENT:
        sql += " AND statut_paiement = ?"
        params.append(paiement)
    if f.get("secteur"):
        sql += " AND secteur_code = ?"
        params.append(f["secteur"])
    sql += " ORDER BY attente_depuis DESC, chantier_id DESC"
    cur = conn.execute(sql, params)
    lignes = _colonnes(cur, cur.fetchall())
    aujourdhui = datetime.date.today()
    if f.get("attente"):                              # le délai d'attente ne concerne que les chantiers encore « À planifier »
        lignes = [l for l in lignes if l["statut"] == "a_planifier" and _attente_ok(l["attente_depuis"], f["attente"], aujourdhui)]
    if f.get("q"):
        mots = cle(f["q"]).split()
        champs = ("client_nom_complet", "entreprise", "adresse", "ville", "telephone", "travaux_detail", "description", "secteur")
        lignes = [l for l in lignes if all(m in _texte(l, champs) for m in mots)]
    return lignes


def selection_soumissions(conn, f, refusees=False):
    """Soumissions en cours (refusees=False) ou refusées (refusees=True), jamais de chantiers."""
    sql = ("SELECT chantier_id, client_nom_complet, entreprise, adresse, ville, telephone, travaux_detail, description, statut, genre,"
           " duree_estimee_h, total_ttc, prix_ht, attente_depuis, cree_par, type_libelle, secteur"
           " FROM v_chantiers WHERE genre = 'soumission' AND archive = ?")
    params = [1 if refusees else 0]
    if f.get("par"):
        sql += " AND cree_par = ?"
        params.append(f["par"])
    if f.get("secteur"):
        sql += " AND secteur_code = ?"
        params.append(f["secteur"])
    sql += " ORDER BY attente_depuis DESC, chantier_id DESC"
    cur = conn.execute(sql, params)
    lignes = _colonnes(cur, cur.fetchall())
    if f.get("attente") and not refusees:
        aujourdhui = datetime.date.today()
        lignes = [l for l in lignes if _attente_ok(l["attente_depuis"], f["attente"], aujourdhui)]
    if f.get("q"):
        mots = cle(f["q"]).split()
        champs = ("client_nom_complet", "entreprise", "adresse", "ville", "telephone", "travaux_detail", "description", "secteur", "cree_par")
        lignes = [l for l in lignes if all(m in _texte(l, champs) for m in mots)]
    return lignes


def compter_chantiers(conn, f):
    """(nombre, total à recevoir) pour une pastille : actifs et archives ensemble."""
    lignes = selection_chantiers(conn, f, False) + selection_chantiers(conn, f, True)
    return len(lignes), round(sum(l["solde"] or 0 for l in lignes if l["statut_paiement"] in ("a_payer", "partiel")), 2)


def compter_soumissions(conn, f):
    return len(selection_soumissions(conn, f, False)), 0
