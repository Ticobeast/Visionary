#!/usr/bin/env python3
"""Crée une base d'ESSAI remplie de fausses données (clients et chantiers fictifs).

    python3 outils/donnees_test.py                  # crée data/test.db (≈ 40 chantiers)
    python3 outils/donnees_test.py --nombre 100     # plus de données
    python3 outils/interface.py --db data/test.db   # l'essayer sans risque

Sert à s'entraîner et à tester avant de saisir tes vrais dossiers. Refuse de toucher à la
vraie base (sylvainculteur.db). Les dates sont calculées par rapport à aujourd'hui : on y
trouve des chantiers passés (payés, impayés, non facturés), des chantiers planifiés et des
soumissions. Téléphones en 555-01xx (réservés à la fiction).
"""
import argparse
import datetime
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from noyau import (DB_DEFAUT, Index, Resultat, alias_types_travaux, creer_chantier, lire_ligne,  # noqa: E402
                   ouvrir_base, trouver_ou_creer_client)

PRENOMS = ["Marie", "Jean", "Sylvie", "Luc", "Nathalie", "Pierre", "Isabelle", "Marc", "Julie", "André",
           "Chantal", "Daniel", "Josée", "Michel", "Louise", "Éric", "Francine", "Guy", "Manon", "Yves"]
NOMS = ["Tremblay", "Gagnon", "Roy", "Côté", "Bouchard", "Gauthier", "Morin", "Lavoie", "Fortin", "Gagné",
        "Ouellet", "Pelletier", "Bélanger", "Lévesque", "Bergeron", "Leblanc", "Paquette", "Girard", "Simard", "Boucher"]
RUES = ["Rue des Érables", "Rue des Pins", "Boulevard du Lac", "Chemin des Cèdres", "Avenue du Parc", "Rue Principale",
        "Rang Saint-Jean", "Rue des Bouleaux", "Montée Sainte-Marie", "Rue des Lilas"]
VILLES = [("Saint-Jérôme", "J7Z"), ("Blainville", "J7C"), ("Mirabel", "J7J"), ("Sainte-Thérèse", "J7E"),
          ("Saint-Eustache", "J7R"), ("Prévost", "J0R"), ("Boisbriand", "J7G"), ("Lorraine", "J6Z")]
TYPES = {  # code: (prix min, prix max, description)
    "taille_haie": (250, 900, "haie de cèdres, environ {n} m"),
    "emondage": (300, 1500, "{n} arbres matures"),
    "elagage": (400, 1800, "grand arbre au-dessus de la maison, grimpeur requis"),
    "abattage": (600, 2500, "arbre mort d'environ {n} m, débitage inclus"),
    "essouchement": (150, 500, "{n} souches"),
}
MODES = ["interac", "interac", "cheque", "comptant", "carte"]


def jour(d):
    return d.isoformat()


def generer(db, nombre=40, graine=2026):
    rnd = random.Random(graine)
    aujourdhui = datetime.date.today()
    conn, _ = ouvrir_base(db)
    alias = alias_types_travaux(conn)
    idx, res = Index(conn), Resultat()
    clients = []
    for i in range(max(1, nombre * 2 // 3)):
        ville, prefixe = rnd.choice(VILLES)
        clients.append(dict(
            client_nom=rnd.choice(NOMS), client_prenom=rnd.choice(PRENOMS),
            client_telephone=f"+1450555{100 + i % 100:04d}",
            adresse=f"{rnd.randint(2, 1999)} {rnd.choice(RUES)}", ville=ville,
            code_postal=f"{prefixe} {rnd.randint(1, 9)}{rnd.choice('ABCEGHJKLMNPRSTVXY')}{rnd.randint(1, 9)}",
            client_sms_ok="0" if rnd.random() < 0.1 else "1"))
    conn.execute("BEGIN")
    for k in range(nombre):
        c = dict(rnd.choice(clients))
        type_ = rnd.choice(list(TYPES))
        pmin, pmax, modele = TYPES[type_]
        prix = round(rnd.randint(pmin, pmax) / 5) * 5
        duree = max(1.0, round(prix / 250 * 2) / 2)
        travaux = f"{type_}: {modele.format(n=rnd.randint(2, 40))}"
        if rnd.random() < 0.2:      # un chantier sur cinq combine deux types de travaux
            autre = rnd.choice([t_ for t_ in TYPES if t_ != type_])
            travaux += f" + {autre}: {TYPES[autre][2].format(n=rnd.randint(2, 20))}"
            prix += round(rnd.randint(TYPES[autre][0], TYPES[autre][1]) / 5) * 5
        ligne = {**c, "type_travaux": travaux, "description": rnd.choice(["", "", "Résidus ramassés.", "Appeler avant de venir."]),
                 "duree_estimee_h": f"{min(duree, 8):g}", "prix_ht": f"{prix:.2f}", "ref_papier": f"Classeur A, fiche {k + 1}"}
        sort = rnd.random()
        if sort < 0.70:        # passé : terminé
            realise = aujourdhui - datetime.timedelta(days=rnd.randint(8, 540))
            ligne.update(statut="termine", date_soumission=jour(realise - datetime.timedelta(days=rnd.randint(3, 20))),
                         date_prevue=jour(realise),
                         duree_reelle_h=f"{min(duree + rnd.choice([-0.5, 0, 0, 0.5, 1]), 8):g}")
            etat = rnd.random()
            if etat < 0.70:    # facturé et payé
                ligne.update(date_facture=jour(realise), numero_facture=f"{realise.year}-{k + 1:03d}")
                total = round(prix * 1.14975, 2)
                ligne.update(paiement_date=jour(realise + datetime.timedelta(days=rnd.randint(0, 20))),
                             paiement_montant=f"{total:.2f}", paiement_mode=rnd.choice(MODES))
            elif etat < 0.85:  # facturé, pas payé
                ligne.update(date_facture=jour(realise + datetime.timedelta(days=1)), numero_facture=f"{realise.year}-{k + 1:03d}")
            # sinon : non facturé
        elif sort < 0.85:      # à venir : planifié, parfois avec acompte
            prevu = aujourdhui + datetime.timedelta(days=rnd.randint(1, 25))
            ligne.update(statut="planifie", date_soumission=jour(prevu - datetime.timedelta(days=rnd.randint(5, 20))),
                         date_prevue=jour(prevu), heure_prevue=rnd.choice(["", "08:00", "09:30", "13:00"]))
            if rnd.random() < 0.3:
                ligne.update(paiement_date=jour(aujourdhui), paiement_montant="100.00", paiement_mode="interac")
        else:                  # soumissions, acceptés, refusés, annulés
            ligne.update(statut=rnd.choice(["soumission", "soumission", "accepte", "refuse", "annule"]),
                         date_soumission=jour(aujourdhui - datetime.timedelta(days=rnd.randint(1, 30))))
        v, erreurs = lire_ligne(ligne, alias, taxes_auto=True)
        assert not erreurs, (ligne, erreurs)
        client_id = trouver_ou_creer_client(conn, idx, v, res, lambda m: None)
        creer_chantier(conn, client_id, v, res, lambda m: None, verifier_doublon=False)
    conn.execute("COMMIT")
    conn.close()
    return res


def main(argv=None):
    p = argparse.ArgumentParser(description="Crée une base d'essai avec de fausses données.")
    p.add_argument("--db", default=str(DB_DEFAUT.parent / "test.db"))
    p.add_argument("--nombre", type=int, default=40, help="nombre de chantiers (défaut : 40)")
    p.add_argument("--remplacer", action="store_true", help="écraser la base d'essai si elle existe déjà")
    a = p.parse_args(argv)
    db = Path(a.db)
    if db.name == DB_DEFAUT.name:
        sys.exit("Refus : ce script ne touche jamais à la vraie base (" + DB_DEFAUT.name + ").")
    if db.exists() and db.stat().st_size > 0:
        if not a.remplacer:
            sys.exit(f"{db} existe déjà. Ajoute --remplacer pour la recréer.")
        db.unlink()
    res = generer(db, a.nombre)
    print(f"Base d'essai créée : {db}\n{res.chantiers} chantiers, {res.clients_crees} clients, {res.paiements} paiements (fictifs).")
    print(f"L'essayer :  python3 outils/interface.py --db {db}")


if __name__ == "__main__":
    main()
