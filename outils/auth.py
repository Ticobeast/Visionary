"""Comptes, mots de passe, sessions et droits d'accès.

Principe : tant qu'aucun compte n'existe, l'interface reste ouverte sur CET ordinateur (comme avant) et refuse tout autre
appareil. Dès qu'un compte actif existe, **toutes** les pages exigent une connexion (nom + mot de passe), y compris depuis
cet ordinateur : ainsi un tunnel ou un réseau privé ne contourne jamais la porte.

  - mots de passe : jamais stockés en clair, seulement une empreinte PBKDF2-SHA256 salée (hashlib, rien à installer) ;
  - session : un jeton aléatoire dans un cookie (HttpOnly, SameSite=Lax) ; la base ne garde que son empreinte ;
  - essais ratés : blocage temporaire (par nom et par adresse) pour décourager les devinettes ;
  - droits : « admin » (tout) et « soumission » (clients et chantiers, sans finances ni suppressions).

Gérer les comptes : `python gerer_utilisateurs.py` (menu) ou la page « Utilisateurs » (administrateur).
"""
import datetime
import getpass
import hashlib
import hmac
import ipaddress
import re
import secrets
import sqlite3
import sys
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import quote, urlencode

import vue
from vue import esc, gabarit

ITERATIONS = 600_000            # coût du calcul d'une empreinte (recommandation OWASP 2023 pour PBKDF2-SHA256)
LONGUEUR_MIN = 4                # 4 suffit tant que l'accès passe par un réseau privé ; à relever (8 et plus) avant tout accès public
DUREE_SESSION_JOURS = 30
COOKIE = "sc_session"
ROLES = {"admin": "Administrateur", "soumission": "Soumission"}
MAX_ECHECS_NOM, MAX_ECHECS_IP, FENETRE_S = 5, 25, 15 * 60
STATIC = Path(__file__).resolve().parent / "static"

MOBILE = re.compile(r"Mobi|Android|iPhone|iPod", re.I)


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------
def hacher(mot_de_passe, sel=None, iterations=None):
    iterations = iterations or ITERATIONS
    sel = sel if sel is not None else secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), sel, iterations)
    return f"pbkdf2_sha256${iterations}${sel.hex()}${h.hex()}"


def verifier(mot_de_passe, stocke):
    try:
        algo, iterations, sel, attendu = stocke.split("$")
        if algo != "pbkdf2_sha256":
            return False
        h = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), bytes.fromhex(sel), int(iterations))
        return hmac.compare_digest(h.hex(), attendu)
    except (ValueError, AttributeError):
        return False


# ---------------------------------------------------------------------------
# Comptes
# ---------------------------------------------------------------------------
def _valider(nom, mot_de_passe, role=None):
    erreurs = []
    if not nom or not 2 <= len(nom.strip()) <= 40 or any(ord(c) < 32 for c in nom):
        erreurs.append("le nom doit avoir de 2 à 40 caractères")
    if mot_de_passe is not None and len(mot_de_passe) < LONGUEUR_MIN:
        erreurs.append(f"le mot de passe doit avoir au moins {LONGUEUR_MIN} caractères")
    if role is not None and role not in ROLES:
        erreurs.append("rôle inconnu")
    return erreurs


def creer_utilisateur(conn, nom, mot_de_passe, role="soumission"):
    """Crée un compte. Retourne la liste des erreurs (vide si tout va bien)."""
    nom = (nom or "").strip()
    erreurs = _valider(nom, mot_de_passe, role)
    if erreurs:
        return erreurs
    try:
        conn.execute("INSERT INTO utilisateurs (nom, role, mot_de_passe) VALUES (?, ?, ?)", (nom, role, hacher(mot_de_passe)))
    except sqlite3.IntegrityError:
        return [f"un compte « {nom} » existe déjà"]
    return []


def lister_utilisateurs(conn):
    cur = conn.execute("SELECT id, nom, role, actif, cree_le FROM utilisateurs ORDER BY nom")
    return [dict(zip(("id", "nom", "role", "actif", "cree_le"), r)) for r in cur.fetchall()]


def nombre_actifs(conn):
    return conn.execute("SELECT count(*) FROM utilisateurs WHERE actif = 1").fetchone()[0]


def _id_utilisateur(conn, ref):
    r = conn.execute("SELECT id FROM utilisateurs WHERE id = ? OR nom = ?", (ref if str(ref).isdigit() else -1, str(ref))).fetchone()
    return r[0] if r else None


def changer_mot_de_passe(conn, ref, mot_de_passe):
    uid = _id_utilisateur(conn, ref)
    if uid is None:
        return ["compte introuvable"]
    erreurs = _valider("xx", mot_de_passe)
    if erreurs:
        return erreurs
    conn.execute("UPDATE utilisateurs SET mot_de_passe = ? WHERE id = ?", (hacher(mot_de_passe), uid))
    conn.execute("DELETE FROM sessions WHERE utilisateur_id = ?", (uid,))      # les appareils connectés doivent se reconnecter
    return []


def _dernier_admin_actif(conn, uid):
    r = conn.execute("SELECT role, actif FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
    if not r or r[0] != "admin" or r[1] != 1:
        return False
    return conn.execute("SELECT count(*) FROM utilisateurs WHERE role = 'admin' AND actif = 1").fetchone()[0] <= 1


def definir_actif(conn, ref, actif):
    uid = _id_utilisateur(conn, ref)
    if uid is None:
        return ["compte introuvable"]
    if not actif and _dernier_admin_actif(conn, uid):
        return ["impossible de désactiver le dernier administrateur"]
    conn.execute("UPDATE utilisateurs SET actif = ? WHERE id = ?", (1 if actif else 0, uid))
    if not actif:
        conn.execute("DELETE FROM sessions WHERE utilisateur_id = ?", (uid,))
    return []


def changer_role(conn, ref, role):
    uid = _id_utilisateur(conn, ref)
    if uid is None or role not in ROLES:
        return ["compte ou rôle inconnu"]
    if role != "admin" and _dernier_admin_actif(conn, uid):
        return ["impossible de retirer les droits du dernier administrateur"]
    conn.execute("UPDATE utilisateurs SET role = ? WHERE id = ?", (role, uid))
    return []


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def _empreinte(jeton):
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def _maintenant():
    return datetime.datetime.now()


def ouvrir_session(conn, utilisateur_id):
    conn.execute("DELETE FROM sessions WHERE expire_le < ?", (_maintenant().strftime("%Y-%m-%d %H:%M:%S"),))    # ménage des sessions périmées
    jeton = secrets.token_urlsafe(32)
    expire = (_maintenant() + datetime.timedelta(days=DUREE_SESSION_JOURS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO sessions (jeton_hash, utilisateur_id, expire_le) VALUES (?, ?, ?)", (_empreinte(jeton), utilisateur_id, expire))
    return jeton


def utilisateur_de_session(conn, jeton):
    """{id, nom, role} du compte connecté avec ce jeton, ou None (jeton inconnu, expiré, compte désactivé)."""
    if not jeton:
        return None
    maintenant = _maintenant().strftime("%Y-%m-%d %H:%M:%S")
    r = conn.execute("SELECT u.id, u.nom, u.role, s.expire_le FROM sessions s JOIN utilisateurs u ON u.id = s.utilisateur_id "
                     "WHERE s.jeton_hash = ? AND u.actif = 1 AND s.expire_le > ?", (_empreinte(jeton), maintenant)).fetchone()
    if r is None:
        return None
    renouvelle = (_maintenant() + datetime.timedelta(days=DUREE_SESSION_JOURS)).strftime("%Y-%m-%d %H:%M:%S")
    if (datetime.datetime.strptime(renouvelle, "%Y-%m-%d %H:%M:%S") - datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S")).days >= 1:
        conn.execute("UPDATE sessions SET expire_le = ? WHERE jeton_hash = ?", (renouvelle, _empreinte(jeton)))   # session glissante
    return {"id": r[0], "nom": r[1], "role": r[2]}


def fermer_session(conn, jeton):
    if jeton:
        conn.execute("DELETE FROM sessions WHERE jeton_hash = ?", (_empreinte(jeton),))


# ---------------------------------------------------------------------------
# Essais ratés : blocage temporaire (en mémoire : repart à zéro si le programme redémarre)
# ---------------------------------------------------------------------------
_ECHECS = {}
_VERROU = threading.Lock()
_horloge = time.time          # remplaçable dans les tests


def _recents(cle):
    limite = _horloge() - FENETRE_S
    _ECHECS[cle] = [t for t in _ECHECS.get(cle, []) if t > limite]
    return _ECHECS[cle]


def secondes_de_blocage(nom, ip):
    """0 si la connexion est permise ; sinon le nombre de secondes à attendre."""
    with _VERROU:
        attente = 0
        for cle, maximum in ((("nom", (nom or "").lower()), MAX_ECHECS_NOM), (("ip", ip), MAX_ECHECS_IP)):
            t = _recents(cle)
            if len(t) >= maximum:
                attente = max(attente, int(t[-maximum] + FENETRE_S - _horloge()) + 1)
        return attente


def noter_echec(nom, ip):
    with _VERROU:
        for cle in (("nom", (nom or "").lower()), ("ip", ip)):
            _recents(cle).append(_horloge())


def effacer_echecs(nom):
    with _VERROU:
        _ECHECS.pop(("nom", (nom or "").lower()), None)


def reinitialiser_blocages():
    with _VERROU:
        _ECHECS.clear()


def connexion(conn, nom, mot_de_passe, ip):
    """(utilisateur ou None, message d'erreur ou None)."""
    nom = (nom or "").strip()
    attente = secondes_de_blocage(nom, ip)
    if attente:
        return None, f"Trop d'essais. Réessaie dans {max(1, (attente + 59) // 60)} minute(s)."
    r = conn.execute("SELECT id, nom, role, mot_de_passe, actif FROM utilisateurs WHERE nom = ?", (nom,)).fetchone()
    ok = verifier(mot_de_passe or "", r[3] if r else hacher("bidon", sel=b"0" * 16))     # même durée de calcul si le compte n'existe pas
    if r is None or not ok or r[4] != 1:
        noter_echec(nom, ip)
        return None, "Nom ou mot de passe incorrect."
    effacer_echecs(nom)
    return {"id": r[0], "nom": r[1], "role": r[2]}, None


# ---------------------------------------------------------------------------
# Droits
# ---------------------------------------------------------------------------
_REFUS_SOUMISSION = [re.compile(p) for p in (
    r"^/utilisateurs", r"^/secteurs", r"^/client/\d+/supprimer$", r"^/chantier/\d+/supprimer$", r"^/chantier/\d+/paiement$",
    r"^/paiement/", r"^/journee", r"^/action/", r"^/tournee", r"^/suivi")]


def permis(role, methode, chemin):
    if role == "admin":
        return True
    if role == "soumission":
        return not any(p.search(chemin) for p in _REFUS_SOUMISSION)
    return False


def _cookie(requete):
    try:
        c = SimpleCookie(requete.get("cookie") or "")
        return c[COOKIE].value if COOKIE in c else None
    except Exception:  # noqa: BLE001 : en-tête Cookie illisible = pas de session
        return None


def _est_local(ip):
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _page_refus(titre, message, statut="403 Forbidden"):
    corps = gabarit(titre, f'<div class="carte"><h2>{esc(titre)}</h2><p>{message}</p></div>', public=True)
    return statut, [("Content-Type", "text/html; charset=utf-8")], corps.encode("utf-8")


def controler(conn, requete, methode, chemin, query=None):
    """Porte d'entrée : None si la requête peut continuer (le compte est mis dans vue.CONTEXTE), sinon une réponse toute faite."""
    vue.CONTEXTE.utilisateur = None
    public = chemin in ("/connexion", "/favicon.ico") or chemin.startswith("/logo.")
    if nombre_actifs(conn) == 0:
        if not _est_local(requete.get("ip", "")):
            return _page_refus("Aucun compte", "Aucun compte n'est encore créé : l'accès à distance est fermé. Sur l'ordinateur de l'atelier, "
                                               "lance <b>gerer_utilisateurs.py</b> pour créer le premier compte.")
        suite = None
    else:
        utilisateur = utilisateur_de_session(conn, _cookie(requete))
        if utilisateur is None:
            if public:
                return None
            retour = chemin + ("?" + urlencode(query) if query else "")
            cible = "/connexion" + ("?suite=" + quote(retour, safe="") if methode == "GET" and retour != "/" else "")
            return "303 See Other", [("Location", cible)], b""
        vue.CONTEXTE.utilisateur = utilisateur
        if chemin == "/connexion" and methode == "GET":
            return "303 See Other", [("Location", "/")], b""
        if not permis(utilisateur["role"], methode, chemin):
            return _page_refus("Accès réservé", "Cette page est réservée à l'administrateur. <a href=\"/chantiers\">Retour aux chantiers</a>")
        suite = utilisateur
    # page d'accueil : le téléphone et le compte « soumission » arrivent directement sur la liste des chantiers
    if methode == "GET" and chemin == "/" and ((suite and suite["role"] != "admin") or MOBILE.search(requete.get("agent") or "")):
        return "303 See Other", [("Location", "/chantiers")], b""
    return None


# ---------------------------------------------------------------------------
# Pages : connexion, déconnexion, comptes
# ---------------------------------------------------------------------------
def _cookie_session(jeton, secure=False):
    base = f"{COOKIE}={jeton}; Path=/; HttpOnly; SameSite=Lax; Max-Age={DUREE_SESSION_JOURS * 86400}"
    return base + ("; Secure" if secure else "")


def page_connexion(conn, query, erreur=None, nom=""):
    from composants import retour_valide
    suite = retour_valide(query.get("suite", ""), "/")
    if nombre_actifs(conn) == 0:
        avis = ('<p class="doux">Aucun compte n\'est créé : l\'accès reste ouvert sur cet ordinateur. Pour créer les comptes, lance '
                '<b>gerer_utilisateurs.py</b>.</p>')
    else:
        avis = ""
    err = f'<div class="erreurs">{esc(erreur)}</div>' if erreur else ""
    corps = (f'<div class="connexion"><div class="carte">{vue.logo_html()}<span class="tag-badge">Accès équipe</span><h1>Connexion</h1>{err}{avis}'
             f'<form method="post" action="/connexion"><input type="hidden" name="suite" value="{esc(suite)}">'
             f'<div class="champ"><label for="nom">Nom d\'utilisateur</label><input id="nom" name="nom" value="{esc(nom)}" autocomplete="username" '
             f'autocapitalize="none" autocorrect="off" required autofocus></div>'
             f'<div class="champ"><label for="mdp">Mot de passe</label><input id="mdp" name="mot_de_passe" type="password" autocomplete="current-password" required></div>'
             f'<button type="submit" class="plein">Se connecter</button></form></div></div>')
    return gabarit("Connexion", corps, public=True)


def post_connexion(conn, requete, form):
    utilisateur, erreur = connexion(conn, form.get("nom", ""), form.get("mot_de_passe", ""), requete.get("ip", ""))
    if utilisateur is None:
        corps = page_connexion(conn, {"suite": form.get("suite", "")}, erreur, form.get("nom", ""))
        return "200 OK", [("Content-Type", "text/html; charset=utf-8")], corps.encode("utf-8")
    jeton = ouvrir_session(conn, utilisateur["id"])
    from composants import retour_valide
    return ("303 See Other", [("Location", retour_valide(form.get("suite", ""), "/")),
                              ("Set-Cookie", _cookie_session(jeton, requete.get("https", False)))], b"")


def post_deconnexion(conn, requete):
    fermer_session(conn, _cookie(requete))
    return ("303 See Other", [("Location", "/connexion"), ("Set-Cookie", f"{COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")], b"")


def page_utilisateurs(conn, query):
    lignes = ""
    for u in lister_utilisateurs(conn):
        etat = "actif" if u["actif"] else "désactivé"
        bascule = ("Désactiver" if u["actif"] else "Réactiver")
        lignes += (f'<tr><td><b>{esc(u["nom"])}</b></td><td>{esc(ROLES[u["role"]])}</td><td>{esc(etat)}</td><td class="droite">'
                   f'<form class="mini" method="post" action="/utilisateurs/{u["id"]}/mot-de-passe">'
                   f'<input name="mot_de_passe" type="password" placeholder="Nouveau mot de passe" autocomplete="new-password" required>'
                   f'<button class="secondaire" type="submit">Changer</button></form>'
                   f'<form class="mini" method="post" action="/utilisateurs/{u["id"]}/actif"><input type="hidden" name="actif" value="{0 if u["actif"] else 1}">'
                   f'<button class="secondaire" type="submit">{bascule}</button></form></td></tr>')
    ajout = ('<div class="carte"><h2>Ajouter un compte</h2><form method="post" action="/utilisateurs/ajouter"><div class="grille">'
             '<div><label for="n">Nom d\'utilisateur</label><input id="n" name="nom" required autocapitalize="none"></div>'
             '<div><label for="m">Mot de passe</label><input id="m" name="mot_de_passe" type="password" autocomplete="new-password" required></div>'
             '<div><label for="r">Droits</label><select id="r" name="role"><option value="soumission">Soumission (clients et chantiers)</option>'
             '<option value="admin">Administrateur (tout)</option></select></div></div>'
             '<div class="barre" style="margin-top:12px"><button type="submit">Ajouter</button></div></form>'
             f'<p class="doux">Mot de passe : {LONGUEUR_MIN} caractères au minimum. Avant de rendre l\'application accessible sur Internet, utilise des mots de passe longs.</p></div>')
    err = query.get("err")
    contenu = (f'<h1>Utilisateurs</h1>{f"<div class=erreurs>{esc(err)}</div>" if err else ""}'
               f'<div class="liste-defile"><table><thead><tr><th>Nom</th><th>Droits</th><th>État</th><th></th></tr></thead><tbody>{lignes}</tbody></table></div>{ajout}')
    return gabarit("Utilisateurs", contenu, query.get("ok"))


def _retour_utilisateurs(erreurs, ok):
    if erreurs:
        return "303 See Other", [("Location", "/utilisateurs?err=" + quote(" ; ".join(erreurs)))], b""
    return "303 See Other", [("Location", f"/utilisateurs?ok={ok}")], b""


def ajouter(conn, form):
    return _retour_utilisateurs(creer_utilisateur(conn, form.get("nom", ""), form.get("mot_de_passe", ""), form.get("role", "soumission")), "utilisateur_cree")


def mot_de_passe(conn, uid, form):
    return _retour_utilisateurs(changer_mot_de_passe(conn, int(uid), form.get("mot_de_passe", "")), "mdp_change")


def actif(conn, uid, form):
    return _retour_utilisateurs(definir_actif(conn, int(uid), form.get("actif") == "1"), "utilisateur_maj")


def logo(nom):
    fichier = STATIC / f"logo.{nom}"
    if nom not in ("svg", "png") or not fichier.exists():
        return "404 Not Found", [("Content-Type", "text/plain; charset=utf-8")], b"Pas de logo."
    return "200 OK", [("Content-Type", "image/svg+xml" if nom == "svg" else "image/png")], fichier.read_bytes()


# ---------------------------------------------------------------------------
# Ligne de commande : python gerer_utilisateurs.py
# ---------------------------------------------------------------------------
def _demander_mot_de_passe(invite="Mot de passe"):
    while True:
        a = getpass.getpass(f"{invite} (invisible pendant la saisie) : ")
        if len(a) < LONGUEUR_MIN:
            print(f"  Au moins {LONGUEUR_MIN} caractères.")
            continue
        if getpass.getpass("Retape-le : ") != a:
            print("  Les deux saisies sont différentes.")
            continue
        if len(a) < 8:
            print("  Attention : mot de passe court. Acceptable tant que l'accès passe par ton réseau privé Tailscale ;")
            print("  utilise des mots de passe plus longs avant de mettre l'application sur Internet.")
        return a


def main(db_path, argv=None):
    from noyau import ouvrir_base, transaction
    conn, _ = ouvrir_base(db_path)
    print(f"Base : {db_path}")
    try:
        while True:
            print("\nComptes :")
            comptes = lister_utilisateurs(conn)
            for u in comptes:
                print(f"  - {u['nom']}  ({ROLES[u['role']]}{'' if u['actif'] else ', désactivé'})")
            if not comptes:
                print("  (aucun : l'accès reste ouvert sur cet ordinateur seulement)")
            choix = input("\n[A]jouter  [M]ot de passe à changer  [D]ésactiver/réactiver  [Q]uitter : ").strip().lower()[:1]
            if choix in ("q", ""):
                return 0
            if choix == "a":
                nom = input("Nom d'utilisateur : ").strip()
                role = "admin" if input("Administrateur (tout) ? [o/N] : ").strip().lower().startswith("o") else "soumission"
                erreurs = creer_utilisateur(conn, nom, _demander_mot_de_passe())
                if not erreurs and role == "admin":
                    erreurs = changer_role(conn, nom, "admin")
                print("  Compte créé." if not erreurs else "  Refusé : " + " ; ".join(erreurs))
            elif choix == "m":
                nom = input("Nom du compte : ").strip()
                erreurs = changer_mot_de_passe(conn, nom, _demander_mot_de_passe("Nouveau mot de passe"))
                print("  Mot de passe changé (les appareils connectés devront se reconnecter)." if not erreurs else "  Refusé : " + " ; ".join(erreurs))
            elif choix == "d":
                nom = input("Nom du compte : ").strip()
                ref = _id_utilisateur(conn, nom)
                if ref is None:
                    print("  Compte introuvable.")
                    continue
                actuel = conn.execute("SELECT actif FROM utilisateurs WHERE id = ?", (ref,)).fetchone()[0]
                erreurs = definir_actif(conn, ref, not actuel)
                print(("  Compte désactivé." if actuel else "  Compte réactivé.") if not erreurs else "  Refusé : " + " ; ".join(erreurs))
    except (KeyboardInterrupt, EOFError):
        print()
        return 0
    finally:
        conn.close()


ROUTES_AUTH = [
    ("GET", r"^/connexion$", lambda c, q, f, *g: page_connexion(c, q)),
    ("POST", r"^/connexion$", lambda c, q, f, *g: post_connexion(c, vue.CONTEXTE.requete, f)),
    ("POST", r"^/deconnexion$", lambda c, q, f, *g: post_deconnexion(c, vue.CONTEXTE.requete)),
    ("GET", r"^/utilisateurs$", lambda c, q, f, *g: page_utilisateurs(c, q)),
    ("POST", r"^/utilisateurs/ajouter$", lambda c, q, f, *g: ajouter(c, f)),
    ("POST", r"^/utilisateurs/(\d+)/mot-de-passe$", lambda c, q, f, i: mot_de_passe(c, i, f)),
    ("POST", r"^/utilisateurs/(\d+)/actif$", lambda c, q, f, i: actif(c, i, f)),
    ("GET", r"^/logo\.(svg|png)$", lambda c, q, f, ext: logo(ext)),
    ("GET", r"^/favicon\.ico$", lambda c, q, f, *g: logo("png")),
]
