"""Documents PDF pour le client : la soumission (toute fiche) et la facture (fiche acceptée, administrateur seulement).

    /soumission/12/pdf                 s'ouvre dans le lecteur PDF du navigateur (nouvel onglet), prêt à imprimer ou à enregistrer
    /soumission/12/pdf?telecharger=1   s'enregistre directement dans le dossier Téléchargements
    /facture/12/pdf  (même chose)      factures : refusées pour le compte « soumission » (paiements et solde = finances)

Rien n'est écrit dans la base : le PDF est refait à chaque demande, avec les données du moment.
"""
import documents
from composants import avec_params
from vue import gabarit, redirection, url_fiche


def _pdf(resultat, query):
    nom, octets = resultat
    disposition = "attachment" if query.get("telecharger") == "1" else "inline"
    return ("200 OK", [("Content-Type", "application/pdf"), ("Content-Disposition", f'{disposition}; filename="{nom}"'),
                       ("X-Content-Type-Options", "nosniff")], octets)


def _introuvable():
    return gabarit("Introuvable", '<h1>Fiche introuvable</h1><p><a href="/chantiers">Retour aux chantiers</a> · '
                                  '<a href="/soumissions">Retour aux soumissions</a></p>'), 404


def soumission(conn, query, chantier_id):
    resultat = documents.soumission_pdf(conn, chantier_id)
    return _introuvable() if resultat is None else _pdf(resultat, query)


def facture(conn, query, chantier_id):
    fiche = conn.execute("SELECT statut, genre FROM v_chantiers WHERE chantier_id = ?", (chantier_id,)).fetchone()
    if fiche is None:
        return _introuvable()
    statut, genre = fiche
    if not documents.facture_possible(statut, genre):
        message = ("La facture n'existe qu'une fois la soumission acceptée." if genre == "soumission" else "Ce chantier est annulé : il n'a pas de facture.")
        return redirection(avec_params(url_fiche(chantier_id, genre), err=message, ok=None))
    return _pdf(documents.facture_pdf(conn, chantier_id), query)


ROUTES_DOCUMENTS = [
    ("GET", r"^/soumission/(\d+)/pdf$", lambda c, q, f, i: soumission(c, q, int(i))),
    ("GET", r"^/facture/(\d+)/pdf$", lambda c, q, f, i: facture(c, q, int(i))),
]
