#!/usr/bin/env python3
"""Interface de saisie locale de SylvainCulteur (s'ouvre dans le navigateur).

    python3 outils/interface.py                 # base réelle : data/sylvainculteur.db
    python3 outils/interface.py --db data/test.db

Aucune installation : bibliothèque standard seulement. Le serveur n'écoute que sur
cet ordinateur (127.0.0.1) : rien n'est accessible depuis le réseau ni depuis Internet.
Utilise les mêmes règles de validation que l'import CSV (noyau.py).
Arrêter : Ctrl+C dans la fenêtre du terminal.
"""
import argparse
import datetime
import re
import sqlite3
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import noyau  # noqa: E402
from noyau import (DB_DEFAUT, STATUTS, Index, Resultat, cle, creer_chantier, jours_attente, lister_secteurs, ouvrir_base,  # noqa: E402
                   priorite, sauvegarder, service_nuage, transaction, trouver_ou_creer_client)
from pages_chantier import (ROUTES_CHANTIER, formulaire_nouveau, lire_formulaire, valeurs_chantier,  # noqa: E402,F401
                            valeurs_vides)
from vue import (LIBELLES_PAIEMENT, LIBELLES_STATUT, MESSAGES, _BASE, argent, badge, badge_attente, esc, gabarit,  # noqa: E402,F401
                 heures, redirection, select_secteur)

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
LIMITE_ARCHIVES = 50     # archives affichées d'un coup (les plus récentes) ; la recherche couvre tout


def _lignes_chantiers(conn, archive, statut, paiement, secteur, q, limite):
    sql = ("SELECT chantier_id, client_nom_complet, entreprise, adresse, ville, telephone, travaux_detail, description,"
           " statut, statut_paiement, solde, date_prevue, attente_depuis, type_libelle, duree_estimee_h, total_ttc,"
           " secteur"
           " FROM v_chantiers WHERE archive = ?")
    params = [1 if archive else 0]
    if statut in STATUTS:
        sql += " AND statut = ?"
        params.append(statut)
    if paiement == "a_recevoir":
        sql += " AND statut_paiement IN ('a_payer', 'partiel')"
    elif paiement in LIBELLES_PAIEMENT:
        sql += " AND statut_paiement = ?"
        params.append(paiement)
    if secteur:
        sql += " AND secteur_code = ?"
        params.append(secteur)
    sql += " ORDER BY attente_depuis DESC, chantier_id DESC"          # date principale : celle de la demande / soumission
    lignes = conn.execute(sql, params).fetchall()
    if q:
        mots = cle(q).split()
        lignes = [r for r in lignes if all(m in cle(" ".join(str(x) for x in (r[1:8] + (r[16],)) if x)) for m in mots)]
    return len(lignes), lignes[:limite]


def _table_chantiers(lignes):
    aujourdhui = datetime.date.today()
    corps = ""
    for (cid, nom, entreprise, adresse, ville, tel, detail, desc, st, stp, solde, dp, attente, type_, duree, total,
         secteur) in lignes:
        nom_aff = nom if not entreprise or entreprise == nom else f"{nom} · {entreprise}"
        date_ = esc(attente or "")                                      # la date de la demande, pas la date planifiée
        if st in ("soumission", "en_attente", "a_planifier") and attente:
            jours = jours_attente(attente, aujourdhui)
            date_ += f'<div>{badge_attente(jours, priorite(jours))}</div>'
        prevu = f'<div class="doux">prévu le {esc(dp)}</div>' if dp and st == "planifie" else ""
        paiement = badge(stp, LIBELLES_PAIEMENT[stp]) if stp != "sans_objet" else ""
        if stp in ("a_payer", "partiel") and solde and total and abs(solde - total) > 0.004:
            paiement += f'<div class="doux">solde {esc(argent(solde))}</div>'
        duree_aff = f'<div class="doux">Durée {esc(heures(duree))}</div>' if duree else ""
        corps += (f'<tr><td>{date_}</td><td><a href="/chantier/{cid}">{esc(nom_aff)}</a></td>'
                  f'<td>{esc(adresse)}<div class="doux">{esc(secteur or ville)}</div></td>'
                  f'<td>{esc(type_)}{duree_aff}</td>'
                  f'<td>{badge(st, LIBELLES_STATUT[st])}{prevu}</td>'
                  f'<td>{paiement}</td><td class="montant">{esc(argent(total)) if total else ""}</td></tr>')
    return ('<table class="liste"><thead><tr><th>Demande</th><th>Client</th><th>Adresse</th><th>Travaux</th><th>Statut</th>'
            f'<th>Paiement</th><th class="droite">Montant</th></tr></thead><tbody>{corps}</tbody></table>')


def page_chantiers(conn, query):
    """Chantiers actifs ; plus bas, les archives (annulés, et terminés ET payés : déplacés là automatiquement)."""
    q = query.get("q", "").strip()
    statut = query.get("statut", "")
    paiement = query.get("paiement", "")
    secteur = query.get("secteur", "")
    n_actifs, actifs = _lignes_chantiers(conn, False, statut, paiement, secteur, q, 300)
    n_archives, archives = _lignes_chantiers(conn, True, statut, paiement, secteur, q, LIMITE_ARCHIVES)
    total_archives = conn.execute("SELECT count(*) FROM v_chantiers WHERE archive = 1").fetchone()[0]

    def puce(href, nombre, texte):
        return f'<a class="puce" href="{href}"><b>{nombre}</b><span>{esc(texte)}</span></a>'
    ar = conn.execute("SELECT count(*), COALESCE(SUM(solde), 0) FROM v_chantiers WHERE statut_paiement IN ('a_payer','partiel')").fetchone()
    pl = conn.execute("SELECT count(*) FROM v_chantiers WHERE statut = 'planifie'").fetchone()[0]
    mq = conn.execute("SELECT count(*) FROM v_chantiers WHERE statut_paiement = 'prix_manquant'").fetchone()[0]
    puces = (puce("/chantiers?paiement=a_recevoir", ar[0], f"à recevoir · {argent(ar[1])}")
             + puce("/chantiers?statut=planifie", pl, "planifiés")
             + (puce("/chantiers?paiement=prix_manquant", mq, "prix manquants") if mq else ""))

    opt_statut = '<option value="">Tous les statuts</option>' + "".join(
        f'<option value="{s}"{" selected" if s == statut else ""}>{LIBELLES_STATUT[s]}</option>' for s in STATUTS)
    paiements = [("a_recevoir", "À recevoir (terminé non payé, ou acompte)")] + [(k, v) for k, v in LIBELLES_PAIEMENT.items() if k != "sans_objet"]
    opt_paiement = '<option value="">Tous les paiements</option>' + "".join(
        f'<option value="{k}"{" selected" if k == paiement else ""}>{esc(v)}</option>' for k, v in paiements)
    select_sect, _ = select_secteur(lister_secteurs(conn), {"secteur": secteur}, nom="secteur", requis=False, tout="Tous les secteurs")
    recherche = (f'<form class="recherche" method="get" action="/chantiers"><input type="search" name="q" value="{esc(q)}" '
                 f'placeholder="Chercher : nom, téléphone, adresse, secteur…"><select name="statut">{opt_statut}</select>'
                 f'<select name="paiement">{opt_paiement}</select>{select_sect}<button type="submit">Chercher</button></form>')

    if actifs:
        tableau = _table_chantiers(actifs)
        if n_actifs > len(actifs):
            tableau += f'<p class="doux">{len(actifs)} premiers résultats sur {n_actifs} : précise la recherche.</p>'
    else:
        tableau = '<div class="carte">Aucun chantier actif ne correspond. <a href="/nouveau">Créer le premier ?</a></div>'

    if n_archives:
        suite = (f'<p class="doux">{len(archives)} plus récent{"s" if len(archives) > 1 else ""} sur {n_archives} : '
                 'utilise la recherche pour retrouver un ancien chantier.</p>' if n_archives > len(archives) else "")
        archives_html = _table_chantiers(archives) + suite
    else:
        archives_html = '<div class="carte doux">Aucune archive' + (" ne correspond à cette recherche." if total_archives else " pour l'instant.") + "</div>"
    lien_archives = f' <a class="doux" href="#archives">Archives ({total_archives})</a>' if total_archives else ""
    section_archives = (f'<h2 id="archives" style="margin-top:32px">Archives <small class="doux">({total_archives})</small></h2>'
                        '<p class="doux">Chantiers <b>annulés</b>, et chantiers <b>terminés et payés</b> : ils sont déplacés ici automatiquement. '
                        'Les terminés sont verrouillés en lecture seule ; « Dupliquer » crée une nouvelle soumission pour un travail récurrent.</p>'
                        + archives_html)
    return gabarit("Chantiers", f'<h1>Chantiers{lien_archives}</h1><div class="puces">{puces}</div>{recherche}{tableau}{section_archives}', query.get("ok"))


def page_nouveau(conn, query):
    q = query.get("q", "").strip()
    client_id = query.get("client_id", "")
    if client_id.isdigit():          # ancien lien : un client existant passe par sa fiche
        return redirection(f"/client/{client_id}")
    trouves = ""
    if q:
        mots = cle(q).split()
        lignes = [r for r in conn.execute("SELECT id, prenom, nom, entreprise, adresse, ville, telephone FROM clients ORDER BY nom")
                  if all(m in cle(" ".join(str(x) for x in r[1:] if x)) for m in mots)][:10]
        liens = "".join(f'<li><a href="/client/{r[0]}">{esc(" ".join(x for x in r[1:4] if x))} — {esc(r[4])}, {esc(r[5])}'
                        f' {esc(r[6] or "")}</a></li>' for r in lignes) or "<li>Aucun client trouvé : remplis le formulaire ci-dessous.</li>"
        trouves = (f'<div class="carte"><h2>Clients trouvés</h2><ul>{liens}</ul>'
                   '<p class="doux">Ouvre la fiche du client pour lui ajouter un chantier (nom et adresse sont déjà connus).</p></div>')
    recherche = (f'<form class="recherche" method="get" action="/nouveau"><input type="search" name="q" value="{esc(q)}" '
                 'placeholder="Le client existe déjà ? Chercher par nom, téléphone ou adresse…"><button class="secondaire" type="submit">Chercher</button></form>')
    contenu = f'<h1>Nouveau client et chantier</h1>{recherche}{trouves}{formulaire_nouveau(conn, valeurs_vides())}'
    return gabarit("Nouveau client et chantier", contenu)


def creer(conn, form):
    brut, v, erreurs = lire_formulaire(conn, form)
    if not erreurs:
        res = Resultat()
        try:
            with transaction(conn):
                # un client déjà connu (même adresse) est réutilisé TEL QUEL : sa fiche ne se modifie que depuis la fiche client
                client_id = trouver_ou_creer_client(conn, Index(conn), v, res)
                chantier_id = creer_chantier(conn, client_id, v, res)
            ok = "cree_reutilise" if res.clients_reutilises else "cree"
            return redirection(f"/chantier/{chantier_id}?ok={ok}")
        except sqlite3.IntegrityError as e:
            erreurs = [f"Refusé par la base : {e}"]
    contenu = f'<h1>Nouveau client et chantier</h1>{formulaire_nouveau(conn, brut, erreurs)}'
    return gabarit("Nouveau client et chantier", contenu)


# ---------------------------------------------------------------------------
# Routage (indépendant du réseau : facile à tester)
# ---------------------------------------------------------------------------
from pages_clients import ROUTES_CLIENTS  # noqa: E402
from tableau import ROUTES_TABLEAU  # noqa: E402
from calendrier import page_calendrier  # noqa: E402
from composants import fenetre_terminer  # noqa: E402

ROUTES = ROUTES_TABLEAU + ROUTES_CLIENTS + ROUTES_CHANTIER + [
    ("GET", r"^/$", lambda c, q, f, *g: page_calendrier(c, q)),
    ("GET", r"^/chantiers$", lambda c, q, f, *g: page_chantiers(c, q)),
    ("GET", r"^/nouveau$", lambda c, q, f, *g: page_nouveau(c, q)),
    ("POST", r"^/nouveau$", lambda c, q, f, *g: creer(c, f)),
]


def repondre(db_path, methode, chemin, query=None, form=None):
    """Retourne (statut HTTP, en-têtes, corps en bytes)."""
    query, form = query or {}, form or {}
    _BASE["db"] = str(db_path)
    for m, motif, gestionnaire in ROUTES:
        correspondance = re.match(motif, chemin)
        if m == methode and correspondance:
            break
    else:
        return "404 Not Found", [("Content-Type", "text/html; charset=utf-8")], gabarit("Introuvable", "<h1>Page introuvable</h1>").encode()
    conn = None
    try:
        conn, _ = ouvrir_base(db_path)
        resultat = gestionnaire(conn, query, form, *correspondance.groups())
        if isinstance(resultat, str):
            page, code = resultat, 200
        elif len(resultat) == 3:  # redirection
            return resultat
        else:
            page, code = resultat
        statut = {200: "200 OK", 404: "404 Not Found"}[code]
        if methode == "GET" and code == 200 and query.get("terminer", "").isdigit():
            # après un encaissement sur un chantier « Planifié » : fenêtre « Voulez-vous passer ce chantier à Terminé ? »
            page = page.replace("</main>", fenetre_terminer(conn, int(query["terminer"]), chemin, query) + "</main>", 1)
        return statut, [("Content-Type", "text/html; charset=utf-8")], page.encode("utf-8")
    except sqlite3.OperationalError as e:
        page = gabarit("Base occupée", f"<h1>La base est occupée</h1><p>{esc(e)}</p><p>Ferme les autres programmes qui l'utilisent "
                                       "(DB Browser par exemple) puis recharge la page.</p>")
        return "503 Service Unavailable", [("Content-Type", "text/html; charset=utf-8")], page.encode("utf-8")
    except Exception as e:  # noqa: BLE001 : on affiche l'erreur plutôt que de planter le serveur
        page = gabarit("Erreur", f"<h1>Erreur inattendue</h1><p>{esc(type(e).__name__)} : {esc(e)}</p><p><a href=\"/\">Retour</a></p>")
        return "500 Internal Server Error", [("Content-Type", "text/html; charset=utf-8")], page.encode("utf-8")
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# Serveur HTTP
# ---------------------------------------------------------------------------
class Gestionnaire(BaseHTTPRequestHandler):
    db_path = DB_DEFAUT
    hotes_autorises = ()

    def log_message(self, *args):  # silence : le terminal reste lisible
        pass

    def _traiter(self, methode):
        # Protection contre les sites web qui tenteraient d'écrire dans la base à ton insu
        # (requêtes « cross-site » et « DNS rebinding ») : l'hôte et l'origine doivent être locaux.
        origine = self.headers.get("Origin")
        if self.headers.get("Host") not in self.hotes_autorises or (origine and urlsplit(origine).netloc not in self.hotes_autorises):
            return self._envoyer("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")], "Accès refusé.".encode())
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query, keep_blank_values=True).items()}
        form = {}
        if methode == "POST":
            taille = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(taille).decode("utf-8", "replace"), keep_blank_values=True).items()}
        self._envoyer(*repondre(self.db_path, methode, url.path, query, form))

    def _envoyer(self, statut, en_tetes, corps):
        code, _, texte = statut.partition(" ")
        self.send_response(int(code), texte)
        for k, v in en_tetes:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):
        self._traiter("GET")

    def do_POST(self):
        self._traiter("POST")


def creer_serveur(db_path, port):
    classe = type("GestionnaireLie", (Gestionnaire,), {
        "db_path": Path(db_path), "hotes_autorises": (f"127.0.0.1:{port}", f"localhost:{port}")})
    return ThreadingHTTPServer(("127.0.0.1", port), classe)


def main(argv=None):
    p = argparse.ArgumentParser(description="Interface de saisie locale (navigateur).")
    p.add_argument("--db", default=str(DB_DEFAUT), help=f"fichier de base (défaut : {DB_DEFAUT})")
    p.add_argument("--essai", action="store_true", help="ouvre la base d'essai (data/test.db) au lieu de la vraie base")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur automatiquement")
    a = p.parse_args(argv)
    db = DB_DEFAUT.parent / "test.db" if a.essai else Path(a.db)
    if a.essai and db.exists() and db.stat().st_size > 0:
        ancienne = sqlite3.connect(db)
        version = ancienne.execute("PRAGMA user_version").fetchone()[0]
        ancienne.close()
        if version != noyau.VERSION_SCHEMA:        # base d'essai d'une version précédente : de fausses données, on la refait
            db.unlink()
            print("Ancienne base d'essai (format périmé) supprimée : elle est recréée.")
    if a.essai and not (db.exists() and db.stat().st_size > 0):
        import donnees_test
        res = donnees_test.generer(db)
        print(f"Base d'essai créée avec de fausses données : {res.chantiers} chantiers.")
    conn, existait = ouvrir_base(db)
    conn.close()
    if existait and not list((db.parent / "sauvegardes").glob(f"{datetime.date.today():%Y-%m-%d}_*")):
        print(f"Sauvegarde du jour : {sauvegarder(db, 'demarrage')}")
    try:
        serveur = creer_serveur(db, a.port)
    except OSError:
        sys.exit(f"Le port {a.port} est déjà utilisé (l'interface est peut-être déjà ouverte ?). Essaie : --port {a.port + 1}")
    url = f"http://localhost:{a.port}/"
    mode = "BASE D'ESSAI (fausses données)" if db.name != DB_DEFAUT.name else "BASE RÉELLE"
    print(f"{mode} : {db}\nInterface : {url}\nArrêter : Ctrl+C")
    if db.name == DB_DEFAUT.name:
        print("Pour t'entraîner sur de fausses données, lance plutôt :  python outils/interface.py --essai")
    nuage = service_nuage(db)
    if nuage:
        print(f"\nATTENTION : ce dossier semble synchronisé par {nuage}. Les données de tes clients seraient copiées sur\n"
              "des serveurs externes (contraire à l'objectif « 100 % local »), et SQLite peut avoir des problèmes dans un\n"
              "dossier synchronisé. Déplace tout le dossier du projet hors de ce service (ex. C:\\SylvainCulteur).\n")
    if not a.sans_navigateur:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêté.")
    finally:
        serveur.server_close()


if __name__ == "__main__":
    main()
