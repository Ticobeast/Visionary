"""Journal des modifications : qui a fait quoi, et quand.

Un seul point d'entrée : interface.repondre appelle `noter_requete` après chaque requête POST. Si elle a réussi, UNE ligne est écrite
dans la table `journal` ; les fonctions métier ne savent rien du journal. Le journal ne se modifie jamais (déclencheurs de la base)
et il garde tout : il n'y a pas de purge automatique.

Ce qui est enregistré : la date, le nom du compte (copié en texte), un libellé court, la cible (« client 12 ») et l'adresse de la
requête sans ses paramètres. AUCUNE valeur de formulaire n'est enregistrée (ni mot de passe, ni contenu des fiches). Seule exception :
le nom tapé à la connexion, et seulement s'il est celui d'un compte existant (sinon « (nom inconnu) ») ; jamais le mot de passe.

« Réussi » veut dire : réponse 303 (redirection) dont l'adresse porte `ok=` et pas `err=` ; une page réaffichée avec des erreurs, un refus
ou une 404 n'écrit rien. Exceptions : voir SANS_PARAMETRE_OK (réussite sans `ok=`), l'ajout de photo (réponse JSON 200 avec le nom de la
photo) et la connexion (traitée à part).
"""
import json
import re
import sqlite3
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

import vue
from vue import esc, gabarit

LIGNES_PAR_PAGE = 100
NOM_INCONNU = "(nom inconnu)"

# (motif de la route, libellé ou fonction(form) -> libellé, cible)
# cible : genre de la fiche visée, dont le numéro est celui de l'adresse (premier groupe du motif) ;
#   "fiche"      : « soumission » ou « chantier » selon le début de l'adresse
#   "location"   : le numéro de client vient de l'adresse de redirection (nouveau client créé)
#   "action"     : le numéro vient du champ `chantier_id` du formulaire (routes /action/...)
#   "lot"        : les numéros des champs `sel_N` du formulaire (planification en lot)
#   None         : pas de cible
LIBELLES = (
    (r"^/connexion$", "Connexion", None),                                    # le refus est traité à part (voir noter_requete)
    (r"^/deconnexion$", "Déconnexion", None),
    (r"^/utilisateurs/ajouter$", "Compte créé", None),
    (r"^/utilisateurs/(\d+)/mot-de-passe$", "Mot de passe d'un compte changé", "compte"),
    (r"^/utilisateurs/(\d+)/actif$", lambda f: "Compte réactivé" if f.get("actif") == "1" else "Compte désactivé", "compte"),
    (r"^/journee/planifier$", "Chantiers planifiés", "lot"),
    (r"^/action/terminer$", "Chantier terminé", "action"),
    (r"^/action/annuler$", "Chantier annulé", "action"),
    (r"^/action/rouvrir$", "Chantier rouvert", "action"),
    (r"^/action/retirer$", "Chantier retiré de la journée", "action"),
    (r"^/client/(\d+)/modifier$", "Client modifié", "client"),
    (r"^/client/(\d+)/supprimer$", "Client supprimé", "client"),
    (r"^/client/(\d+)/nouvelle-adresse$", "Nouvelle adresse du client", "client"),
    (r"^/client/(\d+)/fusionner$", "Fiches fusionnées", "client"),
    (r"^/client/(\d+)/soumission/nouveau$", "Nouvelle soumission", "client"),
    (r"^/client/(\d+)/chantier/nouveau$", "Nouvelle soumission", "client"),
    (r"^/nouveau$", "Nouvelle soumission (nouveau client)", "location"),
    (r"^/soumission/(\d+)$", "Soumission modifiée", "soumission"),
    (r"^/soumission/(\d+)/supprimer$", "Soumission supprimée", "soumission"),
    (r"^/soumission/(\d+)/accepter$", "Soumission acceptée", "soumission"),
    (r"^/soumission/(\d+)/refuser$", "Soumission refusée", "soumission"),
    (r"^/soumission/(\d+)/rouvrir$", "Soumission rouverte", "soumission"),
    (r"^/soumission/(\d+)/completer$", "Soumission complétée et acceptée", "soumission"),
    (r"^/(?:soumission|chantier)/(\d+)/attente$", "Fiche mise en attente", "fiche"),
    (r"^/chantier/(\d+)/reprendre$", "Chantier sorti de l'attente", "chantier"),
    (r"^/chantier/(\d+)/remettre-soumission$", "Chantier remis en soumission", "chantier"),
    (r"^/chantier/(\d+)$", "Chantier modifié", "chantier"),
    (r"^/chantier/(\d+)/paiement$", "Paiement ajouté", "chantier"),
    (r"^/chantier/(\d+)/supprimer$", "Chantier supprimé", "chantier"),
    (r"^/chantier/(\d+)/dupliquer$", "Chantier dupliqué", "chantier"),
    (r"^/paiement/(\d+)/supprimer$", "Paiement supprimé", "paiement"),
    (r"^/raccourcis/ajouter$", "Raccourci ajouté", None),
    (r"^/raccourcis/reinitialiser$", "Raccourcis réinitialisés", None),
    (r"^/raccourcis/(\d+)/retirer$", "Raccourci retiré", "raccourci"),
    (r"^/(?:soumission|chantier)/(\d+)/photos$", "Photo ajoutée", "fiche"),
    (r"^/(?:soumission|chantier)/(\d+)/photos/([^/]+)/supprimer$", "Photo supprimée", "fiche"),
)

# Routes POST volontairement absentes du journal (motif -> raison). Un test oblige à classer chaque route POST.
NON_JOURNALISE = {
    r"^/action/deplacer$": "ordre de passage dans la journée : un clic par flèche, trop bavard et sans conséquence",
    r"^/raccourcis/(\d+)/deplacer$": "ordre des raccourcis d'une personne : préférence d'affichage, trop bavard",
    r"^/(?:soumission|chantier)/(\d+)/photos/([^/]+)/vignette$": "suite technique de l'ajout d'une photo, déjà journalisé",
}

# Réussites dont la redirection n'a pas `ok=` dans son adresse.
SANS_PARAMETRE_OK = (r"^/deconnexion$", r"^/raccourcis/(\d+)/deplacer$")

_LIBELLES = {motif: (libelle, cible) for motif, libelle, cible in LIBELLES}
_FICHE = re.compile(r"^/(soumission|chantier)/")
_CLIENT = re.compile(r"^/client/(\d+)")
_PHOTO = r"^/(?:soumission|chantier)/(\d+)/photos$"


def _propre(texte, longueur):
    """Texte sur une ligne, sans caractères de contrôle, de longueur limitée."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(texte or "")).strip()[:longueur]


def noter(conn, utilisateur, action, cible, adresse):
    """Écrit une ligne dans le journal. N'échoue JAMAIS : en cas de problème (base verrouillée, table absente...), l'erreur est écrite sur la
    console et l'action de l'utilisateur n'en souffre pas. Retourne True si la ligne est écrite. Attente maximale : un quart de seconde."""
    ancienne_attente = None
    try:
        if conn.in_transaction:                      # jamais dans la transaction de quelqu'un d'autre
            raise RuntimeError("une transaction est encore ouverte")
        ancienne_attente = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        conn.execute("PRAGMA busy_timeout = 250")
        conn.execute("INSERT INTO journal (utilisateur, action, cible, adresse) VALUES (?, ?, ?, ?)",
                     (_propre(utilisateur, 40) or None, _propre(action, 200), _propre(cible, 100) or None, _propre(adresse, 300)))
        return True
    except Exception as e:  # noqa: BLE001 : le journal ne doit jamais empêcher une action
        print(f"Journal : ligne non écrite ({type(e).__name__} : {e})", file=sys.stderr)
        return False
    finally:
        if ancienne_attente is not None:
            try:
                conn.execute(f"PRAGMA busy_timeout = {int(ancienne_attente)}")
            except Exception:  # noqa: BLE001
                pass


def _parametres(adresse):
    return parse_qs(urlsplit(adresse).query, keep_blank_values=True)


def a_reussi(motif, resultat):
    """True si le résultat du gestionnaire (voir interface.repondre) est celui d'une action réussie."""
    if isinstance(resultat, str) or len(resultat) != 3:
        return False                                  # page réaffichée (200) ou 404 : rien n'a été fait
    statut, en_tetes, corps = resultat
    if statut.startswith("200") and motif == _PHOTO:
        try:
            return "nom" in json.loads(corps)         # {"nom": ...} = photo écrite ; {"erreur": ...} = refus
        except (ValueError, TypeError):
            return False
    if not statut.startswith("303"):
        return False
    adresse = next((v for k, v in en_tetes if k == "Location"), "")
    parametres = _parametres(adresse)
    if parametres.get("err"):
        return False
    return motif in SANS_PARAMETRE_OK or bool(parametres.get("ok"))


def _cible(genre, chemin, groupes, form, resultat):
    if genre is None:
        return None
    if genre == "lot":
        ids = sorted(int(k[4:]) for k, v in form.items() if k.startswith("sel_") and k[4:].isdigit() and v)
        return ("chantiers " + ", ".join(str(i) for i in ids)) if ids else None
    if genre == "action":
        numero = str(form.get("chantier_id", ""))
        return f"chantier {numero}" if numero.isdigit() else None
    if genre == "location":
        adresse = next((v for k, v in resultat[1] if k == "Location"), "")
        m = _CLIENT.match(urlsplit(adresse).path)
        return f"client {m.group(1)}" if m else None
    if genre == "fiche":
        genre = _FICHE.match(chemin).group(1)
    return f"{genre} {groupes[0]}" if groupes else None


def noter_requete(conn, methode, motif, chemin, groupes, form, resultat, utilisateur):
    """Appelée par interface.repondre après le gestionnaire : écrit la ligne du journal si la requête POST a réussi. Ne lève jamais d'erreur.

    `utilisateur` : le compte connecté ({nom, role}) ou None (pas de comptes, ou connexion en cours)."""
    try:
        if methode != "POST" or motif not in _LIBELLES:
            return
        if motif == r"^/connexion$":                  # pas de compte connecté encore : le nom vient de ce qui a été tapé (jamais le mot de passe)
            nom = (form or {}).get("nom", "")
            reussie = not isinstance(resultat, str) and len(resultat) == 3 and resultat[0].startswith("303")      # refus : la page est réaffichée (200)
            action = "Connexion" if reussie else "Connexion refusée"
            connu = conn.execute("SELECT nom FROM utilisateurs WHERE nom = ?", (str(nom).strip(),)).fetchone()
            # Un nom qui n'est pas celui d'un compte n'est jamais copié : quelqu'un peut taper son mot de passe dans le mauvais champ.
            noter(conn, connu[0] if connu else NOM_INCONNU, action, None, chemin)
            return
        if not a_reussi(motif, resultat):
            return
        libelle, genre = _LIBELLES[motif]
        form = form or {}
        action = libelle(form) if callable(libelle) else libelle
        noter(conn, (utilisateur or {}).get("nom"), action, _cible(genre, chemin, groupes, form, resultat), chemin)
    except Exception as e:  # noqa: BLE001
        print(f"Journal : ligne non écrite ({type(e).__name__} : {e})", file=sys.stderr)


# ---------------------------------------------------------------------------
# Page (administrateur, ordinateur)
# ---------------------------------------------------------------------------
def _echapper_like(texte):
    return texte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _liens_cibles(conn, lignes):
    """{(genre, numéro): adresse de la fiche} pour les cibles qui existent encore."""
    voulus = {"client": set(), "fiche": set()}
    for ligne in lignes:
        m = re.match(r"^(client|chantier|soumission) (\d+)$", ligne["cible"] or "")
        if m:
            voulus["client" if m.group(1) == "client" else "fiche"].add(int(m.group(2)))
    liens = {}
    if voulus["client"]:
        marques = ",".join("?" * len(voulus["client"]))
        for (i,) in conn.execute(f"SELECT id FROM clients WHERE id IN ({marques})", sorted(voulus["client"])):
            liens[("client", i)] = f"/client/{i}"
    if voulus["fiche"]:
        marques = ",".join("?" * len(voulus["fiche"]))
        for i, genre in conn.execute(f"SELECT chantier_id, genre FROM v_chantiers WHERE chantier_id IN ({marques})", sorted(voulus["fiche"])):
            liens[("fiche", i)] = vue.url_fiche(i, genre)
    return liens


def page_journal(conn, query):
    compte = query.get("compte", "")
    texte = query.get("q", "").strip()
    page = int(query["p"]) if query.get("p", "").isdigit() and int(query["p"]) >= 1 else 1
    conditions, valeurs = [], []
    if compte == "-":
        conditions.append("utilisateur IS NULL")
    elif compte:
        conditions.append("utilisateur = ?")
        valeurs.append(compte)
    if texte:
        conditions.append("(action LIKE ? ESCAPE '\\' OR cible LIKE ? ESCAPE '\\')")
        valeurs += [f"%{_echapper_like(texte)}%"] * 2
    ou = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    brutes = conn.execute(f"SELECT quand, utilisateur, action, cible FROM journal{ou} ORDER BY quand DESC, id DESC LIMIT ? OFFSET ?",
                          valeurs + [LIGNES_PAR_PAGE + 1, (page - 1) * LIGNES_PAR_PAGE]).fetchall()
    suite = len(brutes) > LIGNES_PAR_PAGE
    lignes = [dict(zip(("quand", "utilisateur", "action", "cible"), r)) for r in brutes[:LIGNES_PAR_PAGE]]
    liens = _liens_cibles(conn, lignes)

    corps = ""
    for l in lignes:
        cible = esc(l["cible"] or "")
        m = re.match(r"^(client|chantier|soumission) (\d+)$", l["cible"] or "")
        if m:
            adresse = liens.get(("client" if m.group(1) == "client" else "fiche", int(m.group(2))))
            if adresse:
                cible = f'<a href="{adresse}">{cible}</a>'
        corps += (f'<tr><td>{esc(l["quand"])}</td><td>{esc(l["utilisateur"] or "—")}</td><td>{esc(l["action"])}</td><td>{cible}</td></tr>')
    if not corps:
        corps = '<tr><td colspan="4" class="doux">Rien à afficher.</td></tr>'

    noms = [r[0] for r in conn.execute("SELECT DISTINCT utilisateur FROM journal WHERE utilisateur IS NOT NULL ORDER BY utilisateur")]
    sans_nom = conn.execute("SELECT 1 FROM journal WHERE utilisateur IS NULL LIMIT 1").fetchone() is not None
    options = '<option value="">Tous les comptes</option>'
    options += "".join(f'<option value="{esc(n)}"{" selected" if n == compte else ""}>{esc(n)}</option>' for n in noms)
    if sans_nom:
        options += f'<option value="-"{" selected" if compte == "-" else ""}>—</option>'
    recherche = (f'<form class="recherche" method="get" action="/journal"><select name="compte">{options}</select>'
                 f'<input type="search" name="q" value="{esc(texte)}" placeholder="Chercher dans l\'action ou la cible…">'
                 '<button type="submit">Chercher</button></form>')

    def lien(numero, texte_lien):
        parametres = [("compte", compte), ("q", texte), ("p", str(numero) if numero > 1 else "")]
        suite_url = urlencode([(k, v) for k, v in parametres if v])
        return f'<a class="bouton secondaire" href="/journal{"?" + suite_url if suite_url else ""}">{texte_lien}</a>'
    navigation = ""
    if page > 1:
        navigation += lien(page - 1, "Plus récents")
    if suite:
        navigation += (" " if navigation else "") + lien(page + 1, "Plus anciens")
    if navigation:
        navigation = f'<div class="barre" style="margin-top:12px">{navigation}</div>'

    contenu = (f'<h1>Journal des modifications</h1><p class="doux">Qui a fait quoi et quand. Le journal garde tout et ne se modifie pas. '
               '<span class="pc-seul"><a class="doux" href="/utilisateurs">Utilisateurs</a></span></p>'
               f'{recherche}<div class="liste-defile"><table><thead><tr><th>Date et heure</th><th>Compte</th><th>Action</th><th>Cible</th></tr></thead>'
               f'<tbody>{corps}</tbody></table></div>{navigation}')
    return gabarit("Journal", contenu, large=True)


ROUTES_JOURNAL = [
    ("GET", r"^/journal$", lambda c, q, f, *g: page_journal(c, q)),
]
