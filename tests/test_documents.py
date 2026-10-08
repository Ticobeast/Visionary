"""Tests des PDF pour le client (soumission et facture) : logo vectoriel, mise en page, contenu, routes, boutons et droits.

    python3 -m unittest discover -s tests -v
"""
import datetime
import re
import shutil
import subprocess
import sys
import unittest
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "outils"))
sys.path.insert(0, str(RACINE / "tests"))
import documents  # noqa: E402
import entreprise  # noqa: E402
import interface  # noqa: E402
import logo  # noqa: E402
import noyau  # noqa: E402
import pdf  # noqa: E402
from test_pages_soumissions import BaseComptes, BasePages  # noqa: E402

AUJOURDHUI = datetime.date.today()
SVG = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>%s</svg>"
OPERATION = re.compile(rb"([\d.]+) ([\d.]+) ([\d.]+) rg BT /F(\d) ([\d.]+) Tf (?:(-?[\d.]+) Tc )?(-?[\d.]+) (-?[\d.]+) Td \((.*?)(?<!\\)\) Tj")


def pages_pdf(corps):
    """[[(x, y, taille, gras, texte)]] : tout le texte écrit, page par page (flux décompressés, Windows-1252)."""
    pages = []
    for flux in re.findall(rb"stream\n(.*?)\nendstream", corps, re.S):
        try:
            contenu = zlib.decompress(flux)
        except zlib.error:
            continue
        page = []
        for m in OPERATION.finditer(contenu):
            texte = m.group(9).replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\").decode("cp1252")
            page.append((float(m.group(7)), float(m.group(8)), float(m.group(5)), m.group(4) == b"2", texte))
        if page:
            pages.append(page)
    return pages


def lignes_pdf(corps, page=None):
    """Les lignes lues comme à l'écran : les morceaux de texte de même hauteur, de gauche à droite, séparés par « | »."""
    sortie = []
    for numero, morceaux in enumerate(pages_pdf(corps), 1):
        if page is not None and numero != page:
            continue
        groupes = []                                        # [(hauteur, [(x, texte)])] : même ligne si moins d'un point d'écart
        for x, y, _, _, texte in sorted(morceaux, key=lambda m: -m[1]):
            if groupes and abs(groupes[-1][0] - y) <= 1.0:
                groupes[-1][1].append((x, texte))
            else:
                groupes.append((y, [(x, texte)]))
        for _, parts in groupes:
            sortie.append(" | ".join(t for _, t in sorted(parts)))
    return sortie


def texte_pdf(corps):
    return "\n".join(t for page in pages_pdf(corps) for *_, t in page)


def ligne_avec(corps, fragment, page=None):
    """La première ligne qui contient ce fragment (AssertionError si aucune)."""
    for ligne in lignes_pdf(corps, page):
        if fragment in ligne:
            return ligne
    raise AssertionError(f"aucune ligne ne contient « {fragment} » :\n" + "\n".join(lignes_pdf(corps, page)))


class TestLogo(unittest.TestCase):
    def test_le_vrai_logo_est_lu_en_vectoriel(self):
        l = logo.charger(entreprise.LOGO)
        self.assertIsNotNone(l)
        self.assertAlmostEqual(l.largeur, 1296.82, 1)
        self.assertAlmostEqual(l.hauteur, 540.33, 1)
        self.assertEqual(l.operateurs.count("f*"), 3)                                   # trois tracés, règle pair-impair
        for couleur in ("0.4 0.569 0.145 rg", "0.29 0.478 0.157 rg", "0.055 0.204 0.114 rg"):      # #669125, #4A7A28, #0E341D
            self.assertIn(couleur, l.operateurs)
        self.assertGreater(l.operateurs.count(" c\n"), 2000)
        self.assertNotRegex(l.operateurs, r"[AaTtSsQqLl]\b(?! )")                       # que des m / l / c / h / f* : rien d'étranger

    def test_commandes_relatives_et_couples_implicites(self):
        l = logo.lire_svg((SVG % "<path d='M10 10 l 10 0 0 10 z m 5 5 h 2 v 2 z' fill='#ff0000' fill-rule='evenodd'/>").encode())
        self.assertEqual(l.operateurs.split("\n"), ["1 0 0 rg", "10 10 m", "20 10 l", "20 20 l", "h", "15 15 m", "17 15 l", "17 17 l", "h", "f*"])
        self.assertEqual((l.x0, l.y0, l.largeur, l.hauteur), (10.0, 10.0, 10.0, 10.0))

    def test_courbes_lisses_et_quadratiques_deviennent_des_cubiques(self):
        l = logo.lire_svg((SVG % "<path d='M0 0 C 0 10 10 10 10 0 S 20 -10 20 0 Q 25 5 30 0 Z' fill='#000'/>").encode())
        lignes = l.operateurs.split("\n")
        self.assertEqual(lignes[2], "0 10 10 10 10 0 c")
        self.assertEqual(lignes[3], "10 -10 20 -10 20 0 c")                          # premier point de contrôle : symétrique du précédent
        self.assertEqual(lignes[4], "23.33 3.33 26.67 3.33 30 0 c")                  # quadratique -> cubique équivalente
        self.assertEqual(lignes[-1], "f")                                            # nonzero par défaut

    def test_couleurs_et_remplissages(self):
        l = logo.lire_svg((SVG % "<path d='M0 0 L9 0 L9 9Z' fill='#abc'/><path d='M0 0 L5 0 L5 5Z' fill='none'/><path d='M1 1 L2 1 L2 2Z'/>").encode())
        self.assertIn("0.667 0.733 0.8 rg", l.operateurs)
        self.assertIn("0 0 0 rg", l.operateurs)                                      # sans fill : noir (règle du SVG)
        self.assertEqual(l.operateurs.count("f"), 2)                                 # le tracé « none » est ignoré
        for mauvais in ("<path d='M0 0 L9 0 L9 9Z' fill='red'/>", "<path d='M0 0 L9 0 L9 9Z' fill='url(#g)'/>",
                        "<path d='M0 0 L9 0 L9 9Z' fill='#000' fill-rule='autre'/>"):
            with self.assertRaises(logo.LogoIllisible):
                logo.lire_svg((SVG % mauvais).encode())

    def test_ce_qui_n_est_pas_un_dessin_de_tracés_simples_est_refuse(self):
        refuses = [SVG % "<text x='0' y='9'>Allo</text>",
                   SVG % "<g transform='scale(2)'><path d='M0 0 L9 0 L9 9Z' fill='#000'/></g>",
                   SVG % "<path d='M0 0 L9 0 L9 9Z' fill='#000' transform='rotate(9)'/>",
                   SVG % "<path d='M0 0 L9 0 L9 9Z' style='fill:#000'/>",
                   SVG % "<path d='M0 0 A5 5 0 0 1 10 10Z' fill='#000'/>",
                   SVG % "<path d='M0 0 L10' fill='#000'/>",
                   SVG % "<path d='10 10 L20 20' fill='#000'/>",
                   SVG % "<image href='x.png'/>",
                   SVG % "<defs><linearGradient id='g'/></defs><path d='M0 0 L9 0 L9 9Z' fill='#000'/>",
                   SVG % "",
                   SVG % "<path d='M5 5 L5 5 Z' fill='#000'/>",                    # aucune surface : boîte vide
                   "<!DOCTYPE svg [<!ENTITY a 'aaaa'>]><svg xmlns='http://www.w3.org/2000/svg'><path d='M0 0 L9 0 L9 9Z' fill='#000'/></svg>",
                   "pas du XML", ""]
        for svg in refuses:
            with self.assertRaises(logo.LogoIllisible, msg=svg[:70]):
                logo.lire_svg(svg.encode())

    def test_charger_ne_plante_jamais_et_garde_en_memoire(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            absent, mauvais, bon = Path(tmp) / "absent.svg", Path(tmp) / "mauvais.svg", Path(tmp) / "bon.svg"
            mauvais.write_text("<svg>", encoding="utf-8")
            bon.write_text(SVG % "<path d='M0 0 L9 0 L9 9Z' fill='#000'/>", encoding="utf-8")
            self.assertIsNone(logo.charger(absent))
            self.assertIsNone(logo.charger(mauvais))
            premier = logo.charger(bon)
            self.assertIsNotNone(premier)
            self.assertIs(logo.charger(bon), premier)                                # lu une seule fois
            bon.write_text(SVG % "<path d='M0 0 L20 0 L20 20Z' fill='#000'/>", encoding="utf-8")
            self.assertEqual(logo.charger(bon).largeur, 20.0)                        # fichier modifié : relu


class TestFormats(unittest.TestCase):
    def test_date_longue(self):
        self.assertEqual(documents.date_longue("2026-06-01"), "1er juin 2026")
        self.assertEqual(documents.date_longue("2026-08-14"), "14 août 2026")
        self.assertEqual(documents.date_longue(datetime.date(2027, 12, 31)), "31 décembre 2027")
        self.assertEqual(documents.date_longue("2026-02-03 10:00:00"), "3 février 2026")
        self.assertEqual(documents.date_longue(None), "")

    def test_telephone(self):
        self.assertEqual(documents.telephone("+14505550142"), "(450) 555-0142")
        self.assertEqual(documents.telephone(None), "")
        self.assertEqual(documents.telephone("poste 12"), "poste 12")

    def test_nom_de_fichier_ascii(self):
        self.assertEqual(documents.nom_fichier("soumission", 42, "Jean Tremblay"), "Soumission-0042-Jean-Tremblay.pdf")
        self.assertEqual(documents.nom_fichier("facture", 7, "Éloïse Côté-Gagné"), "Facture-0007-Eloise-Cote-Gagne.pdf")
        self.assertEqual(documents.nom_fichier("facture", 12345, '../"évil\r\n'), "Facture-12345-evil.pdf")
        self.assertEqual(documents.nom_fichier("soumission", 1, ""), "Soumission-0001.pdf")
        self.assertEqual(documents.nom_fichier("soumission", 1, "(client à identifier)"), "Soumission-0001-client-a-identifier.pdf")

    def test_libelles_de_taxes_selon_les_montants(self):
        self.assertEqual(documents._taxes(100.0, 5.0, 9.98), [("TPS (5 %)", 5.0), ("TVQ (9,975 %)", 9.98)])
        self.assertEqual(documents._taxes(100.0, 5.0, 9.97), [("TPS (5 %)", 5.0), ("TVQ (9,975 %)", 9.97)])            # un cent d'écart : arrondi
        self.assertEqual(documents._taxes(100.0, 4.0, 8.0), [("TPS", 4.0), ("TVQ", 8.0)])                          # montants saisis à la main
        self.assertEqual(documents._taxes(100.0, 0, 0), [])
        self.assertEqual(documents._taxes(100.0, 5.0, 0), [("TPS (5 %)", 5.0)])

    def test_une_facture_exige_un_chantier_accepte_et_pas_annule(self):
        for statut, genre, attendu in (("soumission", "soumission", False), ("annule", "soumission", False), ("annule", "chantier", False),
                                       ("en_attente", "chantier", True), ("a_planifier", "chantier", True), ("planifie", "chantier", True),
                                       ("termine", "chantier", True)):
            self.assertEqual(documents.facture_possible(statut, genre), attendu, (statut, genre))


class BaseDocuments(BasePages):
    """Trois dossiers d'essai : 1 Marie Gagnon (terminé, payé), 2 Pierre Lavoie (terminé, à recevoir), 3 Luc Boucher (planifié, acompte)."""

    def brut(self, chemin, cookie=None):
        import urllib.parse
        u = urllib.parse.urlsplit(chemin)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        requete = None if cookie is None else {"cookie": cookie, "ip": "100.64.1.2", "agent": "Mozilla/5.0 Chrome/120", "https": False}
        statut, en_tetes, corps = interface.repondre(self.db, "GET", u.path, query, {}, requete)
        return statut, dict(en_tetes), corps

    def pdf(self, chemin, cookie=None):
        statut, en_tetes, corps = self.brut(chemin, cookie)
        self.assertEqual(statut, "200 OK", f"{chemin} : {statut}")
        return corps

    def document(self, genre, i, aujourdhui=None):
        """(nom, octets) construits directement, sans passer par le serveur."""
        conn, _ = noyau.ouvrir_base(self.db)
        try:
            return (documents.soumission_pdf if genre == "soumission" else documents.facture_pdf)(conn, i, aujourdhui)
        finally:
            conn.close()

    def ecrire(self, requete, args=()):
        conn, _ = noyau.ouvrir_base(self.db)             # validation automatique (self.sql ne valide rien)
        try:
            conn.execute(requete, args)
        finally:
            conn.close()

    def soumission_complete(self, **perso):
        return self.complete(**{"taxes_auto": "1", **perso})


class TestSoumissionPdf(BaseDocuments):
    def test_contenu_de_la_soumission(self):
        i = self.soumission_complete(precision_emondage="six érables au fond de la cour", client_courriel="sylvie@example.com")
        corps = self.pdf(f"/soumission/{i}/pdf")
        texte = texte_pdf(corps)
        for attendu in ("SOUMISSION", f"N° {i:04d}", "CLIENT", "Sylvie Roy", "(450) 555-0111", "sylvie@example.com", "LIEU DES TRAVAUX",
                        "22 Rue des Pins", "DESCRIPTION DES TRAVAUX", "Émondage", "six érables au fond de la cour", "Durée estimée", "2 h",
                        "Montant avant taxes", "TOTAL", "CONDITIONS", "ACCEPTATION DE LA SOUMISSION", "Merci de votre confiance !",
                        "Numéro d'entreprise du Québec (NEQ) : 2265191926", "(819) 380-7742 • sylvainculteur@gmail.com"):
            self.assertIn(attendu, texte)
        self.assertIn("300,00 $", ligne_avec(corps, "Montant avant taxes"))
        self.assertIn("15,00 $", ligne_avec(corps, "TPS (5 %)"))
        self.assertIn("29,93 $", ligne_avec(corps, "TVQ (9,975 %)"))
        self.assertIn("344,93 $", ligne_avec(corps, "TOTAL"))
        self.assertIn("Cette soumission est valide jusqu'au", texte)
        self.assertIn("Le paiement est dû à la fin des travaux.", texte)

    def test_date_validite_et_acceptation_par_une_date_fixe(self):
        i = self.soumission_complete()
        _, octets = self.document("soumission", i, datetime.date(2026, 1, 15))
        self.assertIn("Date : 15 janvier 2026", texte_pdf(octets))
        self.assertIn("Valide jusqu'au 14 février 2026", texte_pdf(octets))
        self.assertIn("Cette soumission est valide jusqu'au 14 février 2026.", texte_pdf(octets))
        _, octets = self.document("soumission", i, datetime.date(2026, 3, 1))
        self.assertIn("Valide jusqu'au 31 mars 2026", texte_pdf(octets))
        ancien = entreprise.VALIDITE_SOUMISSION_JOURS
        self.addCleanup(lambda: setattr(entreprise, "VALIDITE_SOUMISSION_JOURS", ancien))
        entreprise.VALIDITE_SOUMISSION_JOURS = 15
        self.assertIn("Valide jusqu'au 16 mars 2026", texte_pdf(self.document("soumission", i, datetime.date(2026, 3, 1))[1]))

    def test_jamais_de_notes_internes_sur_un_document_du_client(self):
        i = self.soumission_complete(description="NOTE-DESCRIPTION appeler avant de venir", notes_acces="NOTE-ACCES chien dans la cour",
                                     client_notes="NOTE-CLIENT mauvais payeur")
        for chemin in (f"/soumission/{i}/pdf", "/facture/3/pdf", "/soumission/3/pdf", "/soumission/2/pdf"):
            texte = texte_pdf(self.pdf(chemin))
            for interne in ("NOTE-", "Chien dans la cour", "Prévenir le gardien", "Grimpeur requis", "stationnement arrière", "Ponctuelle"):
                self.assertNotIn(interne, texte, f"{chemin} : {interne}")
        ancien = entreprise.IMPRIMER_DESCRIPTION
        self.addCleanup(lambda: setattr(entreprise, "IMPRIMER_DESCRIPTION", ancien))
        entreprise.IMPRIMER_DESCRIPTION = True                                        # option : la description s'imprime, jamais les autres notes
        texte = texte_pdf(self.pdf(f"/soumission/{i}/pdf"))
        self.assertIn("NOTE-DESCRIPTION appeler avant de venir", texte)
        self.assertNotIn("NOTE-ACCES", texte)
        self.assertNotIn("NOTE-CLIENT", texte)

    def test_soumission_acceptee_porte_sa_date_d_acceptation_sans_case_a_signer(self):
        texte = texte_pdf(self.pdf("/soumission/3/pdf"))
        self.assertIn("SOUMISSION", texte)
        self.assertIn("Acceptée le", texte)
        self.assertIn("Soumission acceptée le", texte)
        self.assertNotIn("Valide jusqu'au", texte)
        self.assertNotIn("ACCEPTATION DE LA SOUMISSION", texte)
        for attendu in ("Luc Boucher", "Syndicat Les Jardins du Lac", "(450) 555-0163", "850 Boulevard du Lac", "Blainville, QC J7C 2X1", "Émondage",
                        "12 arbres matures", "Utilisation d'une nacelle", "Le bois est débarrassé", "6 h", "Date prévue", "14 octobre 2026",
                        "Mode de règlement prévu : Chèque."):
            self.assertIn(attendu, texte)
        self.assertNotIn("Reçu le", texte)                                            # la soumission ne parle jamais de paiements

    def test_bois_laisse_sur_place(self):
        self.assertIn("Laissé sur place, débité en bûches de 16 pouces.", texte_pdf(self.pdf("/soumission/2/pdf")))

    def test_prix_a_confirmer(self):
        i = self.soumission_complete(prix_ht="")
        corps = self.pdf(f"/soumission/{i}/pdf")
        self.assertIn("à confirmer", ligne_avec(corps, "TOTAL"))
        self.assertNotIn("Montant avant taxes", texte_pdf(corps))

    def test_taxes_saisies_a_la_main_et_absence_de_taxes(self):
        i = self.soumission_complete(taxes_auto="")
        corps = self.pdf(f"/soumission/{i}/pdf")
        self.assertIn("300,00 $", ligne_avec(corps, "Montant"))
        self.assertNotIn("avant taxes", texte_pdf(corps))                             # aucune taxe : le montant est simplement « Montant »
        self.assertNotIn("TPS", texte_pdf(corps))
        self.assertIn("300,00 $", ligne_avec(corps, "TOTAL"))
        self.ecrire("UPDATE chantiers SET tps = 12.5, tvq = 20 WHERE id = ?", (i,))
        corps = self.pdf(f"/soumission/{i}/pdf")
        self.assertIn("12,50 $", ligne_avec(corps, "TPS"))
        self.assertNotIn("TPS (5 %)", texte_pdf(corps))                               # le taux n'est annoncé que s'il correspond aux montants
        self.assertNotIn("TVQ (9,975 %)", texte_pdf(corps))
        self.assertIn("332,50 $", ligne_avec(corps, "TOTAL"))

    def test_client_a_identifier_et_adresse_a_confirmer(self):
        i = self.vide()
        texte = texte_pdf(self.pdf(f"/soumission/{i}/pdf"))
        self.assertIn("(client à identifier)", texte)
        self.assertIn("(adresse à confirmer)", texte)
        self.assertIn("à préciser", texte)

    def test_telechargement_ou_affichage(self):
        i = self.soumission_complete()
        statut, en_tetes, corps = self.brut(f"/soumission/{i}/pdf")
        self.assertEqual(statut, "200 OK")
        self.assertEqual(en_tetes["Content-Type"], "application/pdf")
        self.assertEqual(en_tetes["Content-Disposition"], f'inline; filename="Soumission-{i:04d}-Sylvie-Roy.pdf"')
        self.assertEqual(en_tetes["X-Content-Type-Options"], "nosniff")
        self.assertTrue(corps.startswith(b"%PDF-1.4") and corps.rstrip().endswith(b"%%EOF"))
        statut, en_tetes, corps2 = self.brut(f"/soumission/{i}/pdf?telecharger=1")
        self.assertEqual(en_tetes["Content-Disposition"], f'attachment; filename="Soumission-{i:04d}-Sylvie-Roy.pdf"')
        self.assertEqual(corps2, corps)                                               # même document, autre façon de le recevoir

    def test_structure_du_fichier_et_proprietes(self):
        corps = self.pdf("/soumission/3/pdf")
        debut = int(re.search(rb"startxref\n(\d+)\n", corps).group(1))
        nb = int(re.search(rb"xref\n0 (\d+)\n", corps[debut:]).group(1))
        entrees = re.findall(rb"(\d{10}) 00000 n \n", corps[debut:])
        self.assertEqual(len(entrees), nb - 1)
        for numero, position in enumerate(entrees, 1):
            self.assertTrue(corps[int(position):].startswith(b"%d 0 obj" % numero), numero)
        self.assertRegex(corps, rb"/Info \d+ 0 R")
        titre = "Soumission n° 0003 - Luc Boucher"
        self.assertIn(b"/Title <FEFF" + titre.encode("utf-16-be").hex().upper().encode() + b">", corps)
        self.assertIn(b"/DisplayDocTitle true", corps)

    def test_fiche_inconnue(self):
        for chemin in ("/soumission/999/pdf", "/facture/999/pdf"):
            self.assertEqual(self.brut(chemin)[0], "404 Not Found", chemin)

    def test_ne_modifie_rien(self):
        avant = self.sql("SELECT count(*), sum(prix_ht), group_concat(statut) FROM chantiers")
        self.pdf("/soumission/2/pdf")
        self.pdf("/facture/2/pdf")
        self.assertEqual(self.sql("SELECT count(*), sum(prix_ht), group_concat(statut) FROM chantiers"), avant)

    @unittest.skipUnless(shutil.which("pdftotext") and shutil.which("pdfinfo"), "pdftotext / pdfinfo absents")
    def test_lisible_par_un_vrai_lecteur(self):
        chemin = Path(self._tmp.name) / "s.pdf"
        chemin.write_bytes(self.pdf("/soumission/3/pdf"))
        info = subprocess.run(["pdfinfo", str(chemin)], capture_output=True, text=True, check=True).stdout
        self.assertIn("Pages:           1", info)
        self.assertIn("Soumission n° 0003 - Luc Boucher", info)
        self.assertIn("Author:          Sylvainculteur", info)
        sortie = subprocess.run(["pdftotext", "-layout", str(chemin), "-"], capture_output=True, text=True, check=True).stdout
        self.assertIn("Luc Boucher", sortie)
        self.assertRegex(sortie, r"TOTAL\s+2 529,45 \$")
        self.assertIn("2265191926", sortie)


class TestFacturePdf(BaseDocuments):
    def test_facture_d_un_chantier_termine_non_paye(self):
        corps = self.pdf("/facture/2/pdf")
        texte = texte_pdf(corps)
        self.assertIn("FACTURE", texte)
        self.assertNotIn("SOUMISSION", texte)
        self.assertIn("N° 0002", texte)
        self.assertIn("Date : 22 septembre 2026", texte)                              # chantier terminé : la date des travaux, qui ne bouge plus
        self.assertIn("Échéance : à la réception", texte)
        self.assertIn("Travaux effectués le", texte)
        for attendu in ("Pierre Lavoie", "(450) 555-0177", "Lot 12-4, Rang du Ruisseau", "Mirabel", "Élagage", "Abattage",
                        "grand érable argenté (environ 18 m) penché sur la remise", "petit frêne mort près de la grange",
                        "Le paiement est dû à la réception de la facture.", "Mode de règlement : Chèque."):
            self.assertIn(attendu, texte)
        self.assertIn("1 250,00 $", ligne_avec(corps, "Montant avant taxes"))
        self.assertIn("62,50 $", ligne_avec(corps, "TPS (5 %)"))
        self.assertIn("124,69 $", ligne_avec(corps, "TVQ (9,975 %)"))
        self.assertIn("1 437,19 $", ligne_avec(corps, "Total"))
        self.assertIn("1 437,19 $", ligne_avec(corps, "SOLDE À PAYER"))
        self.assertNotIn("Reçu le", texte)
        self.assertNotIn("acquittée", texte)
        self.assertNotIn("Durée", texte)                                              # la facture ne parle pas de durée
        self.assertNotIn("ACCEPTATION", texte)                                        # ni de case à signer

    def test_facture_payee_en_totalite(self):
        corps = self.pdf("/facture/1/pdf")
        texte = texte_pdf(corps)
        self.assertIn("Payée le 14 juin 2026", texte)
        self.assertIn("Date : 14 juin 2026", texte)
        self.assertIn("- 551,88 $", ligne_avec(corps, "Reçu le 14 juin 2026 (Interac)"))
        self.assertIn("0,00 $", ligne_avec(corps, "SOLDE À PAYER"))
        self.assertIn("Facture acquittée le 14 juin 2026. Merci !", texte)
        self.assertNotIn("Échéance", texte)                                           # plus rien à payer : ni échéance ni conditions
        self.assertNotIn("CONDITIONS", texte)

    def test_facture_d_un_chantier_planifie_avec_acompte_est_datee_du_jour(self):
        corps = self.pdf("/facture/3/pdf")
        texte = texte_pdf(corps)
        self.assertIn(f"Date : {documents.date_longue(AUJOURDHUI)}", texte)           # pas encore fait : la date où on la produit
        self.assertIn("Date prévue", texte)
        self.assertIn("14 octobre 2026", texte)
        self.assertNotIn("Travaux effectués le", texte)
        self.assertIn("- 500,00 $", ligne_avec(corps, "Reçu le 1 octobre 2026 (Chèque)".replace("1 octobre", "1er octobre")))
        self.assertIn("2 029,45 $", ligne_avec(corps, "SOLDE À PAYER"))
        self.assertIn("2 529,45 $", ligne_avec(corps, "Total"))
        _, octets = self.document("facture", 3, datetime.date(2030, 5, 6))
        self.assertIn("Date : 6 mai 2030", texte_pdf(octets))

    def test_chantier_a_planifier_et_en_attente_ont_aussi_une_facture(self):
        accepte = self.soumission_complete()
        self.post(f"/soumission/{accepte}/accepter", {"retour": "/soumissions"})
        self.assertEqual(self.etat(accepte)[0], "a_planifier")
        texte = texte_pdf(self.pdf(f"/facture/{accepte}/pdf"))
        self.assertIn("FACTURE", texte)
        self.assertIn(f"N° {accepte:04d}", texte)
        self.assertIn("344,93 $", texte)
        self.post(f"/chantier/{accepte}/attente", {"retour": "/chantiers", "choix": "indefini"})
        self.assertEqual(self.etat(accepte)[0], "en_attente")
        self.assertIn("FACTURE", texte_pdf(self.pdf(f"/facture/{accepte}/pdf")))

    def test_pas_de_facture_avant_l_acceptation_ni_apres_une_annulation(self):
        i = self.soumission_complete()
        self.assertIsNone(self.document("facture", i))
        statut, en_tetes, _ = self.brut(f"/facture/{i}/pdf")
        self.assertEqual(statut[:3], "303")
        self.assertTrue(en_tetes["Location"].startswith(f"/soumission/{i}?err="), en_tetes["Location"])
        self.assertIn("La+facture+n%27existe+qu%27une+fois+la+soumission+accept", en_tetes["Location"])
        page = self.texte(en_tetes["Location"])
        self.assertIn("La facture n'existe qu'une fois la soumission acceptée.", page)
        self.post(f"/soumission/{i}/refuser", {"retour": "/soumissions"})             # refusée : toujours pas de facture
        self.assertEqual(self.brut(f"/facture/{i}/pdf")[0][:3], "303")
        self.post("/action/annuler", {"chantier_id": "3", "retour": "/chantiers"})    # chantier accepté puis annulé
        statut, en_tetes, _ = self.brut("/facture/3/pdf")
        self.assertEqual(statut[:3], "303")
        self.assertTrue(en_tetes["Location"].startswith("/chantier/3?err="), en_tetes["Location"])
        self.assertIn("Ce chantier est annulé : il n'a pas de facture.", self.texte(en_tetes["Location"]))

    def test_nom_du_fichier_et_telechargement(self):
        statut, en_tetes, corps = self.brut("/facture/2/pdf?telecharger=1")
        self.assertEqual(en_tetes["Content-Disposition"], 'attachment; filename="Facture-0002-Pierre-Lavoie.pdf"')
        self.assertEqual(self.brut("/facture/2/pdf")[1]["Content-Disposition"], 'inline; filename="Facture-0002-Pierre-Lavoie.pdf"')

    def test_les_paiements_s_ajoutent_a_la_facture(self):
        self.post("/chantier/2/paiement", {"paiement_date": "2026-10-03", "paiement_montant": "400", "paiement_mode": "interac"})
        self.post("/chantier/2/paiement", {"paiement_date": "2026-10-05", "paiement_montant": "100,50", "paiement_mode": "comptant"})
        corps = self.pdf("/facture/2/pdf")
        self.assertIn("- 400,00 $", ligne_avec(corps, "Reçu le 3 octobre 2026 (Interac)"))
        self.assertIn("- 100,50 $", ligne_avec(corps, "Reçu le 5 octobre 2026 (Comptant)"))
        self.assertIn("936,69 $", ligne_avec(corps, "SOLDE À PAYER"))
        self.assertNotIn("acquittée", texte_pdf(corps))
        self.post("/chantier/2/paiement", {"paiement_date": "2026-10-06", "paiement_montant": "936,69", "paiement_mode": "cheque"})
        corps = self.pdf("/facture/2/pdf")
        self.assertIn("Facture acquittée le 6 octobre 2026. Merci !", texte_pdf(corps))
        self.assertIn("Payée le 6 octobre 2026", texte_pdf(corps))


class TestMiseEnPage(BaseDocuments):
    def beaucoup_de_travaux(self, i):
        long = "Taille soignée de la haie de cèdres, côté rue et côté voisin, avec ramassage complet des résidus. " * 24
        for code in ("taille_haie", "elagage", "abattage", "essouchement", "emondage"):
            self.ecrire("INSERT OR REPLACE INTO chantier_travaux (chantier_id, type_travaux, precision) VALUES (?, ?, ?)", (i, code, long))

    def test_tout_tient_sur_une_page_pour_un_cas_normal(self):
        for chemin in ("/soumission/3/pdf", "/soumission/2/pdf", "/facture/1/pdf", "/facture/2/pdf", "/facture/3/pdf"):
            self.assertEqual(len(pages_pdf(self.pdf(chemin))), 1, chemin)
            self.assertNotIn("Page 1 /", texte_pdf(self.pdf(chemin)), chemin)           # « Page x / y » seulement s'il y a plusieurs feuilles

    def test_plusieurs_pages_en_tete_pied_et_suite(self):
        i = self.soumission_complete()
        self.beaucoup_de_travaux(i)
        corps = self.pdf(f"/soumission/{i}/pdf")
        pages = pages_pdf(corps)
        n = len(pages)
        self.assertGreater(n, 2)
        for numero in range(1, n + 1):
            texte = "\n".join(t for *_, t in pages[numero - 1])
            self.assertIn("Numéro d'entreprise du Québec (NEQ) : 2265191926", texte, numero)         # coordonnées au bas de CHAQUE feuille
            self.assertIn("(819) 380-7742 • sylvainculteur@gmail.com", texte, numero)
            self.assertIn(f"Page {numero} / {n}", texte)
            if numero > 1:
                self.assertIn(f"Soumission n° {i:04d}  -  Sylvie Roy", texte)                      # rappel du document en haut des feuilles suivantes
            if 1 < numero < n:
                self.assertIn("DESCRIPTION DES TRAVAUX (suite)", texte)                           # la bande verte est reprise
        self.assertIn("SOUMISSION", "\n".join(t for *_, t in pages[0]))
        derniere = "\n".join(t for *_, t in pages[-1])
        self.assertIn("ACCEPTATION DE LA SOUMISSION", derniere)                                     # la case de signature vient en dernier
        tout = texte_pdf(corps)
        self.assertLess(tout.index("TOTAL"), tout.index("ACCEPTATION DE LA SOUMISSION"))            # après les montants, jamais avant
        for page in pages:                                                                          # rien ne déborde de la feuille ni du pied de page
            for x, y, taille, gras, texte in page:
                self.assertGreaterEqual(x, 0, texte)
                self.assertLessEqual(x + pdf.largeur(texte, taille, gras), documents.LARGEUR_PAGE - 40, texte)
                self.assertGreater(y, 30, texte)
                self.assertLess(y, documents.HAUTEUR_PAGE - 25, texte)

    def test_un_texte_enorme_se_poursuit_sur_la_page_suivante_sans_rien_perdre(self):
        i = self.soumission_complete()
        enorme = " ".join(f"mot{k}" for k in range(3000))
        self.ecrire("INSERT OR REPLACE INTO chantier_travaux (chantier_id, type_travaux, precision) VALUES (?, 'emondage', ?)", (i, enorme))
        corps = self.pdf(f"/soumission/{i}/pdf")
        tout = " ".join(texte_pdf(corps).split())
        self.assertIn("mot0 mot1 mot2", tout)
        self.assertIn("mot2999", tout)
        self.assertEqual(len(re.findall(r"mot\d+", tout)), 3000)                                    # pas un mot de perdu
        self.assertGreater(len(pages_pdf(corps)), 2)
        self.assertIn("ACCEPTATION DE LA SOUMISSION", tout)

    def test_aucune_ligne_ne_depasse_sa_colonne(self):
        i = self.soumission_complete(client_nom="Nom-de-famille-extraordinairement-long-" * 3)
        for page in pages_pdf(self.pdf(f"/soumission/{i}/pdf")):
            for x, y, taille, gras, texte in page:
                self.assertLessEqual(x + pdf.largeur(texte, taille, gras), documents.LARGEUR_PAGE - 40, texte)

    def test_l_espacement_des_lettres_ne_deborde_pas_sur_les_textes_suivants(self):
        """Dans un PDF, l'espacement (Tc) dure jusqu'au prochain réglage : chaque titre espacé le remet à 0, sinon tout le texte suivant s'élargit."""
        corps = self.pdf("/soumission/3/pdf")
        blocs = 0
        for flux in re.findall(rb"stream\n(.*?)\nendstream", corps, re.S):
            try:
                contenu = zlib.decompress(flux)
            except zlib.error:
                continue
            for bloc in re.findall(rb"BT .*? ET", contenu):
                reglages = re.findall(rb"(-?[\d.]+) Tc", bloc)
                if reglages:
                    blocs += 1
                    self.assertEqual(reglages[-1], b"0", bloc)                                      # le dernier réglage d'un texte espacé : retour à 0
        self.assertGreater(blocs, 3)                                                                # titre, étiquettes, bandes... : il y en a plusieurs

    def test_le_logo_est_dessine_en_vectoriel(self):
        corps = self.pdf("/soumission/3/pdf")
        flux = [zlib.decompress(f) for f in re.findall(rb"stream\n(.*?)\nendstream", corps, re.S)]
        page1 = next(f for f in flux if b"BT" in f)
        self.assertEqual(page1.count(b"f*"), 3)                                                     # les trois tracés du logo
        self.assertRegex(page1, rb"q [\d.]+ 0 0 -[\d.]+ [-\d.]+ [-\d.]+ cm")                        # mis à l'échelle, axe y inversé
        self.assertNotIn(b"/Image", corps)                                                          # aucune image : du dessin
        self.assertLess(len(corps), 120_000)                                                        # léger malgré les milliers de courbes

    def test_sans_logo_utilisable_le_nom_de_l_entreprise_est_ecrit(self):
        ancien = entreprise.LOGO
        self.addCleanup(lambda: setattr(entreprise, "LOGO", ancien))
        entreprise.LOGO = Path(self._tmp.name) / "inexistant.svg"
        corps = self.pdf("/soumission/3/pdf")
        self.assertIn("Sylvainculteur", [t for page in pages_pdf(corps) for *_, t in page if t == "Sylvainculteur"])
        self.assertNotIn(b"f*", b"".join(zlib.decompress(f) for f in re.findall(rb"stream\n(.*?)\nendstream", corps, re.S)))
        self.assertIn("SOUMISSION", texte_pdf(corps))

    def test_numeros_de_taxes_au_bas_des_pages_s_ils_sont_connus(self):
        self.assertNotIn("TPS :", texte_pdf(self.pdf("/facture/2/pdf")))                           # inconnus : rien d'inventé
        for nom, valeur in (("NUMERO_TPS", "123456789 RT0001"), ("NUMERO_TVQ", "1234567890 TQ0001")):
            ancien = getattr(entreprise, nom)
            self.addCleanup(lambda nom=nom, ancien=ancien: setattr(entreprise, nom, ancien))
            setattr(entreprise, nom, valeur)
        self.assertIn("TPS : 123456789 RT0001 • TVQ : 1234567890 TQ0001", texte_pdf(self.pdf("/facture/2/pdf")))

    def test_liens_courriel_et_telephone_cliquables(self):
        corps = self.pdf("/soumission/3/pdf")
        self.assertIn(b"/URI (mailto:sylvainculteur@gmail.com)", corps)
        self.assertIn(b"/URI (tel:+18193807742)", corps)

    def test_format_lettre_pour_les_documents_du_client_a4_pour_la_journee(self):
        for chemin in ("/soumission/3/pdf", "/facture/2/pdf"):
            self.assertIn(b"/MediaBox [0 0 612 792]", self.pdf(chemin), chemin)         # papier Lettre (8,5 x 11 po), celui du Québec
        self.assertIn(b"/MediaBox [0 0 595.28 841.89]", self.pdf("/journee.pdf?date=2026-10-14"))     # la feuille de route de la journée : inchangée

    def test_coordonnees_de_l_entreprise_exactes(self):
        self.assertEqual(entreprise.NEQ, "2265191926")
        self.assertEqual(entreprise.TELEPHONE, "(819) 380-7742")
        self.assertEqual(entreprise.COURRIEL, "sylvainculteur@gmail.com")
        self.assertTrue(entreprise.LOGO.is_file())

    def test_aucun_emoji_dans_les_documents(self):
        motif = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u25A0-\u25FF\u23E0-\u23FF\uFE0F\u2190-\u21FF]")
        for chemin in ("/soumission/3/pdf", "/soumission/2/pdf", "/facture/1/pdf", "/facture/2/pdf", "/facture/3/pdf"):
            self.assertEqual(motif.findall(texte_pdf(self.pdf(chemin))), [], chemin)

    def test_plusieurs_pdf_demandes_en_meme_temps(self):
        """Le serveur traite plusieurs requêtes à la fois : le logo (lu une fois, partagé) et les PDF restent corrects."""
        import threading
        logo._CACHE.clear()
        resultats, erreurs = [], []

        def demander(i):
            try:
                for chemin in ("/soumission/3/pdf", "/facture/2/pdf", "/soumission/1/pdf", "/facture/3/pdf"):
                    corps = self.pdf(chemin)
                    resultats.append((chemin, corps.count(b"f*") >= 0, len(pages_pdf(corps))))
            except Exception as e:  # noqa: BLE001 : on veut voir toute erreur, pas seulement les assertions
                erreurs.append(repr(e))

        fils = [threading.Thread(target=demander, args=(i,)) for i in range(6)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()
        self.assertEqual(erreurs, [])
        self.assertEqual(len(resultats), 24)
        self.assertTrue(all(pages == 1 for _, _, pages in resultats))

    def test_le_pdf_de_la_journee_reste_identique(self):
        """L'ajout du pied de page personnalisable ne change rien au PDF de la journée."""
        corps = self.pdf("/journee.pdf?date=2026-10-14")
        texte = texte_pdf(corps)
        self.assertIn("Journée de travail", texte)
        self.assertNotIn("2265191926", texte)


class TestBoutons(BaseDocuments):
    @staticmethod
    def ligne_de(page, i):
        return next(tr for tr in re.findall(r"<tr>.*?</tr>", page, re.S) if f'href="/soumission/{i}"' in tr)

    def test_liste_des_soumissions_pdf_a_cote_d_accepter_en_attente_refuser(self):
        a, b = self.soumission_complete(client_nom="Alpha"), self.soumission_complete(client_nom="Beta", adresse="2 Rue B")
        page = self.get("/soumissions")
        for i in (a, b):
            ligne = self.ligne_de(page, i)
            self.assertIn(f'<a class="bouton secondaire" href="/soumission/{i}/pdf" target="_blank" rel="noopener"', ligne)
            self.assertIn(f'href="/soumission/{i}/pdf?telecharger=1" download', ligne)
            ordre = [ligne.index(x) for x in (">Accepter<", ">En attente<", ">Refuser<", ">Voir PDF<", ">Télécharger PDF<")]
            self.assertEqual(ordre, sorted(ordre))                                    # dans cet ordre, sur la même ligne de boutons
            self.assertEqual(ligne.count("actions-ligne"), 1)

    def test_fiche_d_une_soumission_et_d_une_soumission_refusee(self):
        i = self.soumission_complete()
        page = self.get(f"/soumission/{i}")
        self.assertIn(f'href="/soumission/{i}/pdf"', page)
        self.assertIn(f'href="/soumission/{i}/pdf?telecharger=1"', page)
        self.assertNotIn("/facture/", page)                                           # pas de facture avant l'acceptation
        self.assertNotIn("Documents pour le client", page)
        self.post(f"/soumission/{i}/refuser", {"retour": "/soumissions"})
        page = self.get(f"/soumission/{i}")
        self.assertIn(f'href="/soumission/{i}/pdf"', page)
        self.assertNotIn("/facture/", page)

    def test_fiche_d_un_chantier_documents_soumission_et_facture(self):
        for i in (1, 2, 3):                                                           # terminé payé, terminé non payé, planifié
            page = self.get(f"/chantier/{i}")
            self.assertIn("Documents pour le client", page)
            for document in ("soumission", "facture"):
                self.assertIn(f'href="/{document}/{i}/pdf" target="_blank"', page)
                self.assertIn(f'href="/{document}/{i}/pdf?telecharger=1" download', page)
        accepte = self.soumission_complete()
        self.post(f"/soumission/{accepte}/accepter", {"retour": "/soumissions"})
        self.post(f"/chantier/{accepte}/attente", {"retour": "/chantiers", "choix": "indefini"})
        self.assertIn(f'href="/facture/{accepte}/pdf"', self.get(f"/chantier/{accepte}"))
        self.post("/action/annuler", {"chantier_id": str(accepte), "retour": "/chantiers"})
        page = self.get(f"/chantier/{accepte}")
        self.assertIn(f'href="/soumission/{accepte}/pdf"', page)
        self.assertNotIn(f"/facture/{accepte}/pdf", page)                             # annulé : plus de facture

    def test_raccourci_facture_a_cote_de_terminer_au_tableau_de_bord_et_dans_la_journee(self):
        for chemin in ("/?date=2026-10-14", "/journee?date=2026-10-14"):
            page = self.get(chemin)
            self.assertRegex(page, r'<span class="groupe-actions"><a class="bouton" href="[^"]*terminer=3">Terminer</a>'
                                   r'<a class="bouton secondaire" href="/facture/3/pdf" target="_blank" rel="noopener"[^>]*>Facture</a></span>')
        # chantier déjà terminé : « Terminé » et la facture reste à portée de la main
        jour = self.sql("SELECT date_prevue FROM chantiers WHERE id = 2")[0][0]
        page = self.get(f"/?date={jour}")
        self.assertIn('<span class="groupe-actions"><span class="doux">Terminé</span><a class="bouton secondaire" href="/facture/2/pdf"', page)

    def test_la_fenetre_terminer_propose_aussi_la_facture(self):
        page = self.get("/?date=2026-10-14&terminer=3")
        self.assertIn("Terminer ce chantier", page)
        fenetre = page[page.index('class="modale"'):]
        self.assertLess(fenetre.index("Oui, il est terminé"), fenetre.index('href="/facture/3/pdf"'))
        self.assertLess(fenetre.index('href="/facture/3/pdf"'), fenetre.index(">Annuler<"))
        self.assertIn('target="_blank"', fenetre[fenetre.index('href="/facture/3/pdf"'):][:200])
        self.assertIn("Facture (PDF)", fenetre)


class TestDroits(BaseComptes, BaseDocuments):
    def test_le_compte_soumission_a_la_soumission_pas_la_facture(self):
        i = self.complete(cookie=self.alice, taxes_auto="1")
        self.assertTrue(self.pdf(f"/soumission/{i}/pdf", cookie=self.alice).startswith(b"%PDF"))
        self.assertTrue(self.pdf("/soumission/3/pdf", cookie=self.alice).startswith(b"%PDF"))          # même celle d'un chantier accepté
        for chemin in ("/facture/3/pdf", "/facture/2/pdf", f"/facture/{i}/pdf", "/facture/3/pdf?telecharger=1"):
            statut, _, corps = self.brut(chemin, cookie=self.alice)
            self.assertEqual(statut, "403 Forbidden", chemin)
            self.assertNotIn(b"%PDF", corps)

    def test_l_administrateur_a_les_deux(self):
        self.assertTrue(self.pdf("/facture/3/pdf", cookie=self.admin).startswith(b"%PDF"))
        self.assertTrue(self.pdf("/soumission/3/pdf", cookie=self.admin).startswith(b"%PDF"))

    def test_sans_connexion_rien_ne_sort(self):
        for chemin in ("/soumission/3/pdf", "/facture/3/pdf"):
            statut, en_tetes, corps = self.brut(chemin, cookie="")
            self.assertEqual(statut[:3], "303", chemin)
            self.assertTrue(en_tetes["Location"].startswith("/connexion"), en_tetes["Location"])
            self.assertNotIn(b"%PDF", corps)

    def test_pas_de_lien_vers_la_facture_pour_le_compte_soumission(self):
        page = self.get("/chantier/3", cookie=self.alice)
        self.assertIn('href="/soumission/3/pdf"', page)
        self.assertNotIn("/facture/", page)
        self.assertNotIn(">Facture<", page)
        self.assertIn('href="/facture/3/pdf"', self.get("/chantier/3", cookie=self.admin))

    def test_le_compte_soumission_voit_les_boutons_pdf_de_sa_liste(self):
        i = self.complete(cookie=self.alice)
        ligne = TestBoutons.ligne_de(self.get("/soumissions", cookie=self.alice), i)
        self.assertIn(f'href="/soumission/{i}/pdf"', ligne)
        self.assertIn(">Télécharger PDF<", ligne)


if __name__ == "__main__":
    unittest.main()
