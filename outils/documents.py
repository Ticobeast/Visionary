"""Soumission et facture en PDF, à envoyer au client : logo, coordonnées de l'entreprise, prix en toutes lettres et conditions.

Une soumission acceptée devient une facture : c'est la même fiche, donc le même numéro, sous un autre titre.
 - la SOUMISSION annonce les travaux, le prix, les conditions, et laisse une case d'acceptation à signer ;
 - la FACTURE reprend les travaux et le prix, puis ajoute les paiements reçus et le solde à payer (ou « payée »).
Ce que le client lit ne contient jamais de notes internes (accès, notes sur le client, durée réelle...).

Les coordonnées (nom, NEQ, téléphone, courriel, numéros de taxes, conditions) viennent de entreprise.py ; le logo, de
ressources/logo-entreprise.svg (voir logo.py). Sans logo utilisable, le nom de l'entreprise est écrit en grosses lettres.
Aucune dépendance : le PDF est écrit à la main par pdf.py.

Numéro = numéro de la fiche (« Chantier #42 » -> 0042). Date : la soumission est datée du jour où on la produit ; la facture,
du jour de la fin des travaux une fois le chantier terminé (elle ne bouge plus), sinon du jour où on la produit.
"""
import datetime
import re
import unicodedata
from decimal import Decimal

import entreprise
import logo as logos
from noyau import LIBELLES_BOIS, LIBELLES_MODE, taxes_pour
from pdf import MOIS, Document, decouper, largeur
from vue import argent, heures

# Couleurs du logo (vert forêt, vert feuille) : le document garde la même identité.
VERT_FONCE, VERT, VERT_CLAIR = (0.055, 0.204, 0.114), (0.290, 0.478, 0.157), (0.400, 0.569, 0.145)
TEXTE, GRIS, FILET, FOND, BLANC = (0.11, 0.14, 0.11), (0.42, 0.45, 0.42), (0.83, 0.86, 0.81), (0.953, 0.965, 0.941), (1.0, 1.0, 1.0)

LARGEUR_PAGE, HAUTEUR_PAGE = 612.0, 792.0  # format Lettre (8,5 x 11 po) : le papier du Québec (1 pt = 1/72 po)
GAUCHE = 48.0
DROITE = LARGEUR_PAGE - 48.0
LARGEUR_UTILE = DROITE - GAUCHE
HAUT_PAGE_SUITE = HAUTEUR_PAGE - 62.0      # début du texte des pages 2 et suivantes
BAS_CONTENU = 110.0                        # le pied de page (NEQ, téléphone, courriel) occupe ce qui est en dessous
LARGEUR_LOGO = 178.0
STATUTS_FACTURABLES = ("en_attente", "a_planifier", "planifie", "termine")     # chantier ACCEPTÉ et pas annulé
LIBELLES_TITRE = {"soumission": "SOUMISSION", "facture": "FACTURE"}


def facture_possible(statut, genre):
    """Une facture n'existe qu'une fois la soumission acceptée (genre « chantier ») et tant que le chantier n'est pas annulé."""
    return genre == "chantier" and statut in STATUTS_FACTURABLES


# ---------------------------------------------------------------------------
# Petits formatages
# ---------------------------------------------------------------------------
def date_longue(jour):
    """« 2026-06-01 » -> « 1er juin 2026 »."""
    if not jour:
        return ""
    d = jour if isinstance(jour, datetime.date) else datetime.date.fromisoformat(str(jour)[:10])
    return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]} {d.year}"


def telephone(t):
    """« +14505550142 » -> « (450) 555-0142 »."""
    m = re.fullmatch(r"\+1(\d{3})(\d{3})(\d{4})", t or "")
    return f"({m.group(1)}) {m.group(2)}-{m.group(3)}" if m else (t or "")


def nom_fichier(genre, chantier_id, client):
    """« Soumission-0042-Jean-Tremblay.pdf » : ASCII seulement (aucun souci d'accent à l'enregistrement ou au courriel)."""
    sans_accents = unicodedata.normalize("NFKD", client or "").encode("ascii", "ignore").decode("ascii")
    reste = re.sub(r"[^A-Za-z0-9]+", "-", sans_accents).strip("-")
    return f"{'Facture' if genre == 'facture' else 'Soumission'}-{chantier_id:04d}" + (f"-{reste}" if reste else "") + ".pdf"


def _taxes(prix_ht, tps, tvq):
    """[(libellé, montant)] : « TPS (5 %) » seulement si le montant est bien celui du taux courant, sinon « TPS » tout court."""
    lignes = []
    standard_tps, standard_tvq = taxes_pour(Decimal(str(prix_ht)))
    if tps:
        lignes.append(("TPS (5 %)" if abs(Decimal(str(tps)) - standard_tps) <= Decimal("0.01") else "TPS", tps))
    if tvq:
        lignes.append(("TVQ (9,975 %)" if abs(Decimal(str(tvq)) - standard_tvq) <= Decimal("0.01") else "TVQ", tvq))
    return lignes


# ---------------------------------------------------------------------------
# Le document
# ---------------------------------------------------------------------------
class DocumentClient(Document):
    """Page à l'en-tête soigné (logo, titre, numéro, date), pied de page avec les coordonnées de l'entreprise sur chaque feuille."""

    def __init__(self, genre, numero, client, logo):
        titre = f"{LIBELLES_TITRE[genre].capitalize()} n° {numero}"
        super().__init__(f"{titre}  -  {client}", haut=HAUT_PAGE_SUITE, bas=BAS_CONTENU, format=(LARGEUR_PAGE, HAUTEUR_PAGE),
                         meta={"titre": f"{titre} - {client}", "auteur": entreprise.NOM, "sujet": f"{titre} - {client}"})
        self.genre, self.numero, self.logo_dessin = genre, numero, logo

    # --- en-tête (première page) ---------------------------------------------
    def entete(self, lignes):
        """Logo à gauche ; titre, numéro et dates à droite ; filet vert dessous. `lignes` : [(texte, gras)]."""
        haut = HAUTEUR_PAGE - 40.0
        if self.logo_dessin is not None:
            hauteur_logo = self.logo(self.logo_dessin, GAUCHE, haut, LARGEUR_LOGO)
        else:
            self._texte(GAUCHE, haut - 24, entreprise.NOM, 24, True, VERT_FONCE)
            hauteur_logo = 34.0
        y = haut - 22
        self._texte_droite(DROITE, y, LIBELLES_TITRE[self.genre], 25, True, VERT_FONCE, espacement=1.8)
        y -= 21
        for texte, gras in lignes:
            self._texte_droite(DROITE, y, texte, 11.5 if gras else 10, gras, TEXTE if gras else GRIS)
            y -= 14.5
        filet = min(haut - hauteur_logo, y) - 12
        self._rect(GAUCHE, filet, LARGEUR_UTILE, 2.2, VERT_CLAIR)
        self._rect(GAUCHE, filet, 64, 2.2, VERT_FONCE)
        self.y = filet - 20

    # --- pages suivantes et pied de page ------------------------------------------------
    def _decorer(self, numero, total):
        self._cible = numero - 1                # les primitives écrivent sur cette feuille
        try:
            if numero > 1:
                self._texte(GAUCHE, HAUTEUR_PAGE - 36, self.titre_courant, 8.5, False, GRIS)
                self._texte_droite(DROITE, HAUTEUR_PAGE - 36, entreprise.NOM, 8.5, True, VERT)
                self._trait(GAUCHE, HAUTEUR_PAGE - 44, DROITE, HAUTEUR_PAGE - 44, 0.6, FILET)
            self._pied(numero, total)
        finally:
            self._cible = -1

    def _pied(self, numero, total):
        """NEQ, téléphone et courriel (+ numéros de taxes s'ils sont connus) en bas de chaque feuille ; « Page x / y » s'il y en a plusieurs."""
        centre = (GAUCHE + DROITE) / 2
        self._rect(GAUCHE, 88, LARGEUR_UTILE, 0.8, FILET)
        y = 73.0
        self._texte_centre(centre, y, f"Numéro d'entreprise du Québec (NEQ) : {entreprise.NEQ}", 8.8, True, VERT_FONCE)
        y -= 12.5
        avant = f"{entreprise.TELEPHONE} • "
        ligne = avant + entreprise.COURRIEL + (f" • {entreprise.SITE_WEB}" if entreprise.SITE_WEB else "")
        self._texte_centre(centre, y, ligne, 8.8, False, GRIS)
        x0 = centre - largeur(ligne, 8.8) / 2
        chiffres = re.sub(r"\D", "", entreprise.TELEPHONE)
        if chiffres:
            self._lien(x0, y - 2, x0 + largeur(entreprise.TELEPHONE, 8.8), y + 9, "tel:+" + (chiffres if len(chiffres) > 10 else "1" + chiffres))
        self._lien(x0 + largeur(avant, 8.8), y - 2, x0 + largeur(avant + entreprise.COURRIEL, 8.8), y + 9, "mailto:" + entreprise.COURRIEL)
        taxes = " • ".join(x for x in (f"TPS : {entreprise.NUMERO_TPS}" if entreprise.NUMERO_TPS else "",
                                       f"TVQ : {entreprise.NUMERO_TVQ}" if entreprise.NUMERO_TVQ else "") if x)
        if taxes:
            y -= 12.5
            self._texte_centre(centre, y, taxes, 8.8, False, GRIS)
        if total > 1:
            self._texte_droite(DROITE, 36, f"Page {numero} / {total}", 8, False, GRIS)

    # --- blocs de texte -----------------------------------------------------------------
    def _lignes_bloc(self, lignes, largeur_max):
        """[(texte, taille, gras, couleur)] -> lignes coupées à la largeur donnée."""
        sortie = []
        for texte, taille, gras, couleur in lignes:
            for morceau in decouper(texte, taille, gras, largeur_max):
                sortie.append((morceau, taille, gras, couleur))
        return sortie

    @staticmethod
    def _hauteur_lignes(lignes):
        return sum(taille * 1.32 for _, taille, _, _ in lignes)

    def _ecrire_lignes(self, x, y_haut, lignes):
        y = y_haut
        for texte, taille, gras, couleur in lignes:
            y -= taille * 1.32
            self._texte(x, y, texte, taille, gras, couleur)
        return y_haut - y

    def colonnes(self, blocs, largeur_colonne):
        """Blocs côte à côte : [(ÉTIQUETTE, [(texte, taille, gras, couleur)])]. Tous partent de la même hauteur."""
        prepares = [(etiquette, self._lignes_bloc(lignes, largeur_colonne)) for etiquette, lignes in blocs]
        hauteur = 14 + max(self._hauteur_lignes(lignes) for _, lignes in prepares)
        self.besoin(hauteur + 10)
        ecart = (LARGEUR_UTILE - largeur_colonne * len(prepares)) / max(1, len(prepares) - 1) if len(prepares) > 1 else 0
        for k, (etiquette, lignes) in enumerate(prepares):
            x = GAUCHE + k * (largeur_colonne + ecart)
            self._texte(x, self.y - 8, etiquette, 7.8, True, VERT, espacement=1.3)
            self._ecrire_lignes(x, self.y - 14, lignes)
        self.y -= hauteur + 22

    def etiquette(self, texte):
        self.besoin(40)
        self._texte(GAUCHE, self.y - 8, texte, 7.8, True, VERT, espacement=1.3)
        self.y -= 16

    # --- tableau des travaux --------------------------------------------------------------
    def _bande(self, texte):
        self._rect(GAUCHE, self.y - 20, LARGEUR_UTILE, 20, VERT_FONCE)
        self._texte(GAUCHE + 10, self.y - 13.5, texte, 8.2, True, BLANC, espacement=1.3)
        self.y -= 20

    def tableau(self, titre, lignes):
        """Bande verte puis une ligne par élément : (étiquette, valeur, étiquette en gras). Une ligne reste d'un seul morceau si elle
        tient sur une page ; sinon (texte énorme) elle se poursuit sur la page suivante. La bande est reprise sur chaque page."""
        x_valeur, l_etiquette, l_valeur = GAUCHE + 132, 112.0, DROITE - 12 - (GAUCHE + 132)
        self.besoin(70)
        self._bande(titre)
        for etiquette, valeur, fort in lignes:
            lab = decouper(etiquette, 9.5, fort, l_etiquette)
            val = decouper(valeur, 9.5, False, l_valeur) if valeur else []
            n = max(len(lab), len(val), 1)
            if self.y - (21 + 12.6 * (n - 1)) < self.bas and 21 + 12.6 * (n - 1) <= self.haut - 20 - self.bas:
                self._ouvrir_page()                          # elle tient sur une page neuve : on ne la coupe pas
                self._bande(titre + " (suite)")
            debut = 0
            while debut < n:
                if self.y - 21 < self.bas:
                    self._ouvrir_page()
                    self._bande(titre + " (suite)")
                capacite = 1 + int((self.y - 21 - self.bas) // 12.6)
                fin = min(n, debut + capacite)
                y = self.y - 15
                for k, i in enumerate(range(debut, fin)):
                    if i < len(lab):
                        self._texte(GAUCHE + 10, y - 12.6 * k, lab[i], 9.5, fort, TEXTE if fort else GRIS)
                    if i < len(val):
                        self._texte(x_valeur, y - 12.6 * k, val[i], 9.5, False, TEXTE)
                self.y -= 21 + 12.6 * (fin - debut - 1)
                self._rect(GAUCHE, self.y, LARGEUR_UTILE, 0.6, FILET)
                debut = fin
        self.y -= 14

    # --- montants ------------------------------------------------------------------------
    def totaux(self, lignes, boite, notes=()):
        """Bloc à droite : lignes (libellé, texte, gras) ; `boite` = (libellé, montant, couleur) mis en évidence en vert ; notes sous la boîte."""
        largeur_bloc = 236.0
        x0 = DROITE - largeur_bloc
        hauteur = 17 * len(lignes) + 34 + sum(13 for _ in notes) + 10
        self.besoin(hauteur)
        for libelle, texte, gras in lignes:
            self._texte(x0 + 10, self.y - 12, libelle, 9.8, gras, TEXTE if gras else GRIS)
            self._texte_droite(DROITE - 10, self.y - 12, texte, 9.8, gras, TEXTE)
            self.y -= 17
            self._rect(x0, self.y, largeur_bloc, 0.6, FILET)
        self.y -= 6
        libelle, montant, couleur = boite
        self._rect(x0, self.y - 30, largeur_bloc, 30, couleur)
        self._texte(x0 + 12, self.y - 19.5, libelle, 10, True, BLANC, espacement=1.2)
        self._texte_droite(DROITE - 12, self.y - 20, montant, 14, True, BLANC)
        self.y -= 30
        for note in notes:
            self.y -= 13
            self._texte_droite(DROITE, self.y, note, 8.6, False, GRIS)
        self.y -= 16

    def conditions(self, phrases):
        self.besoin(30 + 13 * len(phrases))
        self.etiquette("CONDITIONS")
        for phrase in phrases:
            lignes = decouper(phrase, 9.3, False, LARGEUR_UTILE - 16)
            self.besoin(13 * len(lignes))
            for i, ligne in enumerate(lignes):
                self.y -= 12.8
                if i == 0:
                    self._texte(GAUCHE + 2, self.y, "•", 9.3, True, VERT)
                self._texte(GAUCHE + 14, self.y, ligne, 9.3, False, TEXTE)
        self.y -= 12

    def acceptation(self):
        """Case d'acceptation à signer (soumission)."""
        phrase = f"J'accepte la présente soumission et autorise {entreprise.NOM} à exécuter les travaux décrits ci-dessus aux conditions indiquées."
        lignes = decouper(phrase, 9.3, False, LARGEUR_UTILE - 28)
        note = f"Vous pouvez aussi accepter par courriel ({entreprise.COURRIEL}) ou par téléphone ({entreprise.TELEPHONE})."
        hauteur = 34 + 12.6 * len(lignes) + 44 + 26
        self.besoin(hauteur + 8)
        haut = self.y
        self._rect(GAUCHE, haut - hauteur, LARGEUR_UTILE, hauteur, FOND)
        self._cadre(GAUCHE, haut - hauteur, LARGEUR_UTILE, hauteur, FILET)
        self._texte(GAUCHE + 14, haut - 20, "ACCEPTATION DE LA SOUMISSION", 7.8, True, VERT, espacement=1.3)
        y = haut - 24
        for ligne in lignes:
            y -= 12.6
            self._texte(GAUCHE + 14, y, ligne, 9.3, False, TEXTE)
        y_trait = y - 36
        x = GAUCHE + 14
        for etiquette, w in (("Nom (en lettres moulées)", 160.0), ("Signature", 190.0), ("Date", LARGEUR_UTILE - 28 - 160 - 190 - 32)):
            self._trait(x, y_trait, x + w, y_trait, 0.7, GRIS)
            self._texte(x, y_trait - 10, etiquette, 7.8, False, GRIS)
            x += w + 16
        self._texte(GAUCHE + 14, haut - hauteur + 10, note, 8.2, False, GRIS)
        self.y = haut - hauteur - 16

    def remerciement(self):
        self.besoin(30)
        self.y -= 12
        self._texte_centre((GAUCHE + DROITE) / 2, self.y, entreprise.REMERCIEMENT, 11, True, VERT)
        self.y -= 12


# ---------------------------------------------------------------------------
# Contenu : lecture de la fiche et mise en page
# ---------------------------------------------------------------------------
def _lire(conn, chantier_id):
    """La fiche (v_chantiers) + travaux, paiements et date de création ; None si elle n'existe pas."""
    cur = conn.execute("SELECT * FROM v_chantiers WHERE chantier_id = ?", (chantier_id,))
    ligne = cur.fetchone()
    if ligne is None:
        return None
    d = dict(zip([c[0] for c in cur.description], ligne))
    d["travaux"] = conn.execute("SELECT t.libelle, ct.precision FROM chantier_travaux ct JOIN types_travaux t ON t.code = ct.type_travaux "
                                "WHERE ct.chantier_id = ? ORDER BY ct.type_travaux", (chantier_id,)).fetchall()
    d["paiements"] = conn.execute("SELECT date_paiement, montant, mode FROM paiements WHERE chantier_id = ? ORDER BY date_paiement, id",
                                  (chantier_id,)).fetchall()
    d["cree_le"] = conn.execute("SELECT date(cree_le) FROM chantiers WHERE id = ?", (chantier_id,)).fetchone()[0]
    return d


def _lignes_travaux(d, genre):
    lignes = [(libelle, precision or "", True) for libelle, precision in d["travaux"]] or [("Travaux", "à préciser", True)]
    if d["description"] and entreprise.IMPRIMER_DESCRIPTION:
        lignes.append(("Description", d["description"], False))
    if d["nacelle"]:
        lignes.append(("Nacelle", "Utilisation d'une nacelle", False))
    if d["debarrasser_bois"]:
        lignes.append(("Bois", "Le bois est débarrassé (enlevé du terrain).", False))
    elif d["bois_format"]:
        forme = {"16_pouces": "bûches de 16 pouces", "4_pieds": "longueurs de 4 pieds"}.get(d["bois_format"], LIBELLES_BOIS.get(d["bois_format"], ""))
        lignes.append(("Bois", f"Laissé sur place, débité en {forme}.", False))
    if genre == "soumission" and d["duree_estimee_h"]:
        lignes.append(("Durée estimée", heures(d["duree_estimee_h"]), False))
    if d["date_prevue"]:
        lignes.append(("Travaux effectués le" if d["statut"] == "termine" else "Date prévue", date_longue(d["date_prevue"]), False))
    return lignes


def _blocs_client(d):
    nom = d["client_nom_complet"]
    client = [(nom, 11, True, TEXTE)]
    if d["entreprise"] and d["entreprise"] not in nom:
        client.append((d["entreprise"], 9.6, False, TEXTE))
    for t in (d["telephone"], d["telephone_2"]):
        if t:
            client.append((telephone(t), 9.6, False, TEXTE))
    if d["courriel"]:
        client.append((d["courriel"], 9.6, False, TEXTE))
    if d["adresse"]:
        lieu = [(d["adresse"], 11, True, TEXTE),
                (" ".join(x for x in (", ".join(y for y in (d["ville"], d["province"]) if y), d["code_postal"]) if x), 9.6, False, TEXTE)]
        if d["secteur"] and d["secteur"] != d["ville"]:
            lieu.append((f"Secteur : {d['secteur']}", 9.0, False, GRIS))
    else:
        lieu = [("(adresse à confirmer)", 9.6, False, GRIS)]
    return [("CLIENT", client), ("LIEU DES TRAVAUX", lieu)]


def _construire(d, genre, aujourdhui):
    numero = f"{d['chantier_id']:04d}"
    accepte = d["genre"] == "chantier"
    client = d["client_nom_complet"]
    logo = logos.charger(entreprise.LOGO)
    doc = DocumentClient(genre, numero, client, logo)

    # --- en-tête : numéro, date, validité ou échéance
    if genre == "soumission":
        jour = (datetime.date.fromisoformat(d["date_soumission"] or d["cree_le"] or aujourdhui.isoformat()) if accepte else aujourdhui)
        droite = [(f"N° {numero}", True), (f"Date : {date_longue(jour)}", False)]
        if accepte:
            droite.append((f"Acceptée le {date_longue(d['accepte_le'])}" if d["accepte_le"] else "Acceptée", False))
        else:
            limite = jour + datetime.timedelta(days=entreprise.VALIDITE_SOUMISSION_JOURS)
            droite.append((f"Valide jusqu'au {date_longue(limite)}", False))
    else:
        jour = datetime.date.fromisoformat(d["date_prevue"]) if d["statut"] == "termine" and d["date_prevue"] else aujourdhui
        acquittee = d["paye"] > 0 and d["solde"] <= 0
        droite = [(f"N° {numero}", True), (f"Date : {date_longue(jour)}", False),
                  (f"Payée le {date_longue(d['paiements'][-1][0])}" if acquittee else "Échéance : à la réception", False)]
    doc.entete(droite)

    # --- client et lieu, travaux
    doc.colonnes(_blocs_client(d), 236.0)
    doc.tableau("DESCRIPTION DES TRAVAUX", _lignes_travaux(d, genre))

    # --- montants
    prix = d["prix_ht"]
    if prix is None:
        doc.totaux([], ("TOTAL", "à confirmer", VERT_FONCE))
    else:
        taxes = _taxes(prix, d["tps"], d["tvq"])
        lignes = [("Montant avant taxes" if taxes else "Montant", argent(prix), False)] + [(libelle, argent(m), False) for libelle, m in taxes]
        if genre == "soumission":
            doc.totaux(lignes, ("TOTAL", argent(d["total_ttc"]), VERT_FONCE))
        else:
            lignes.append(("Total", argent(d["total_ttc"]), True))
            for date_p, montant, mode in d["paiements"]:
                lignes.append((f"Reçu le {date_longue(date_p)} ({LIBELLES_MODE.get(mode, mode)})", "- " + argent(montant), False))
            solde = max(d["solde"], 0)
            notes = [f"Facture acquittée le {date_longue(d['paiements'][-1][0])}. Merci !"] if d["paye"] > 0 and d["solde"] <= 0 else []
            doc.totaux(lignes, ("SOLDE À PAYER", argent(solde), VERT_CLAIR if solde == 0 else VERT_FONCE), notes)

    # --- conditions, acceptation
    phrases = []
    if genre == "soumission":
        if accepte:
            phrases.append(f"Soumission acceptée le {date_longue(d['accepte_le'])}." if d["accepte_le"] else "Soumission acceptée.")
        else:
            phrases.append(f"Cette soumission est valide jusqu'au {date_longue(jour + datetime.timedelta(days=entreprise.VALIDITE_SOUMISSION_JOURS))}.")
    if genre == "soumission" or not (d["paye"] > 0 and d["solde"] <= 0):      # facture acquittée : plus rien à payer ni à rappeler
        if d["modalite_paiement"]:
            phrases.append(f"Mode de règlement {'prévu ' if genre == 'soumission' else ''}: {LIBELLES_MODE.get(d['modalite_paiement'], d['modalite_paiement'])}.")
        phrases += list(entreprise.CONDITIONS_SOUMISSION if genre == "soumission" else entreprise.CONDITIONS_FACTURE)
    if phrases:
        doc.conditions(phrases)
    if genre == "soumission" and not accepte:
        doc.acceptation()
    doc.remerciement()
    return doc.octets()


def _document(conn, chantier_id, genre, aujourdhui):
    d = _lire(conn, chantier_id)
    if d is None:
        return None
    if genre == "facture" and not facture_possible(d["statut"], d["genre"]):
        return None
    octets = _construire(d, genre, aujourdhui or datetime.date.today())
    return nom_fichier(genre, chantier_id, d["client_nom_complet"]), octets


def soumission_pdf(conn, chantier_id, aujourdhui=None):
    """(nom de fichier, octets du PDF) de la soumission de la fiche ; None si la fiche n'existe pas."""
    return _document(conn, chantier_id, "soumission", aujourdhui)


def facture_pdf(conn, chantier_id, aujourdhui=None):
    """(nom de fichier, octets du PDF) de la facture de la fiche ; None si elle n'existe pas ou n'est pas encore acceptée."""
    return _document(conn, chantier_id, "facture", aujourdhui)
