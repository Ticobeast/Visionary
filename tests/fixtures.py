"""Données de départ des tests : trois dossiers fictifs (téléphones en 555-01xx, courriels @example.com).

 1  Marie Gagnon     taille de haie, TERMINÉ et PAYÉ (donc archivé)
 2  Pierre Lavoie    élagage + abattage, TERMINÉ, rien payé (à recevoir)
 3  Luc Boucher      émondage, PLANIFIÉ le 2026-10-14, acompte de 500 $ reçu (nacelle, bois débarrassé)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import noyau  # noqa: E402

EXEMPLES = [{'client_nom': 'Gagnon',
  'client_prenom': 'Marie',
  'client_telephone': '+14505550142',
  'adresse': '123 Rue des Érables',
  'ville': 'Saint-Jérôme',
  'code_postal': 'J7Z 1A1',
  'type_travaux': 'taille_haie: cèdres côté rue et côté voisin, environ 35 m, hauteur 2 m',
  'statut': 'termine',
  'description': 'Résidus ramassés.',
  'date_soumission': '2026-05-28',
  'date_prevue': '2026-06-14',
  'duree_estimee_h': '3.0',
  'duree_reelle_h': '3.5',
  'prix_ht': '480.00',
  'tps': '24.00',
  'tvq': '47.88',
  'modalite_paiement': 'interac',
  
  'paiement_date': '2026-06-14',
  'paiement_montant': '551.88',
  'paiement_mode': 'interac',
  'dossier_photos': 'photos/2026/2026-06-14_gagnon',
  'client_courriel': 'marie.gagnon@example.com',
  'client_sms_ok': '1',
  'client_notes': 'Ponctuelle, préfère les avant-midi.'},
 {'client_nom': 'Lavoie',
  'client_prenom': 'Pierre',
  'client_telephone': '+14505550177',
  'adresse': 'Lot 12-4, Rang du Ruisseau',
  'ville': 'Mirabel',
  'type_travaux': 'elagage: grand érable argenté (environ 18 m) penché sur la remise + abattage: petit frêne mort près de la grange',
  'nacelle': 'non',
  'debarrasser_bois': 'non',
  'bois_format': '16 pouces',
  'statut': 'termine',
  'description': "Grimpeur requis pour l'érable. Débitage du frêne en longueurs de 16 pouces.",
  'date_soumission': '2026-09-10',
  'date_prevue': '2026-09-22',
  'duree_estimee_h': '4.0',
  'duree_reelle_h': '4.5',
  'prix_ht': '1250.00',
  'tps': '62.50',
  'tvq': '124.69',
  'modalite_paiement': 'cheque',
  'notes_acces': 'Chemin de terre. Stationner près de la grange. Chien dans la cour (attaché).',
  'dossier_photos': 'photos/2026/2026-09-22_lavoie',
  'latitude': '45.6480',
  'longitude': '-74.0920'},
 {'client_nom': 'Boucher',
  'client_prenom': 'Luc',
  'client_entreprise': 'Syndicat Les Jardins du Lac',
  'client_telephone': '+14505550163',
  'adresse': '850 Boulevard du Lac',
  'ville': 'Blainville',
  'code_postal': 'J7C 2X1',
  'type_travaux': 'emondage: 12 arbres matures en bordure du stationnement (érables et frênes)',
  'nacelle': 'oui',
  'debarrasser_bois': 'oui',
  'statut': 'planifie',
  'description': 'Branches ramassées. Prévenir le gardien la veille.',
  'date_soumission': '2026-09-25',
  'date_prevue': '2026-10-14',
  'duree_estimee_h': '6.0',
  'prix_ht': '2200.00',
  'tps': '110.00',
  'tvq': '219.45',
  'modalite_paiement': 'cheque',
  'paiement_date': '2026-10-01',
  'paiement_montant': '500.00',
  'paiement_mode': 'cheque',
  'notes_acces': 'Entrée par le stationnement arrière. Demander le code de la barrière au gardien.',
  'dossier_photos': 'photos/2026/2026-10-14_jardins-du-lac'}]


def creer_exemples(db):
    """Crée la base `db` avec les trois dossiers ci-dessus. Retourne le nombre de chantiers créés."""
    conn, _ = noyau.ouvrir_base(db)
    alias = noyau.alias_types_travaux(conn)
    idx, res = noyau.Index(conn), noyau.Resultat()
    conn.execute("BEGIN")
    for brut in EXEMPLES:
        v, erreurs = noyau.lire_ligne(dict(brut), alias, taxes_auto=False)
        assert not erreurs, erreurs
        client_id = noyau.trouver_ou_creer_client(conn, idx, v, res)
        noyau.creer_chantier(conn, client_id, v, res)
    conn.execute("COMMIT")
    conn.close()
    return res.chantiers
