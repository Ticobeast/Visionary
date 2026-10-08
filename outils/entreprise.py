"""Coordonnées de l'entreprise, imprimées sur les soumissions et les factures (PDF envoyés aux clients).

C'est le SEUL fichier à modifier pour changer ce qui paraît sur ces documents : le texte, les numéros, les conditions.
Enregistre le fichier, puis relance le programme.
"""
from pathlib import Path

NOM = "Sylvainculteur"
NEQ = "2265191926"                                   # Numéro d'entreprise du Québec
TELEPHONE = "(819) 380-7742"
COURRIEL = "sylvainculteur@gmail.com"
SITE_WEB = ""                                        # facultatif, ex. "sylvainculteur.ca" : écrit après le courriel, au bas des pages

# Numéros d'inscription aux taxes : OBLIGATOIRES sur une facture qui compte la TPS et la TVQ (loi). À remplir avec ceux que
# Revenu Québec t'a remis, par exemple "123456789 RT0001" et "1234567890 TQ0001". Vides : rien n'est imprimé.
NUMERO_TPS = ""
NUMERO_TVQ = ""

VALIDITE_SOUMISSION_JOURS = 30                       # « Cette soumission est valide jusqu'au ... »

# La « Description » d'une fiche sert d'abord de notes pour la feuille de route (« appeler avant de venir », « grimpeur requis ») :
# elle n'est pas imprimée sur les documents du client. True : elle l'est aussi (les travaux et leurs précisions le sont toujours).
IMPRIMER_DESCRIPTION = False

# Lignes ajoutées sous « Conditions » (une phrase par ligne). Le mode de règlement prévu et la date de validité s'ajoutent tout seuls.
CONDITIONS_SOUMISSION = ["Le paiement est dû à la fin des travaux."]
CONDITIONS_FACTURE = ["Le paiement est dû à la réception de la facture."]
REMERCIEMENT = "Merci de votre confiance !"

LOGO = Path(__file__).resolve().parent / "ressources" / "logo-entreprise.svg"      # remplace ce fichier pour changer de logo (SVG de tracés)
