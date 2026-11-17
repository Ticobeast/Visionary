"""Tests du glisser-déposer : l'ordre complet d'une journée ou des raccourcis enregistré d'un coup, et ce que la page fournit au geste."""
import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))
import noyau  # noqa: E402
import vue  # noqa: E402
from test_tableau import AUJOURDHUI, BaseTableau  # noqa: E402

DEMAIN = (AUJOURDHUI + datetime.timedelta(days=1)).isoformat()


class TestOrdreDeLaJournee(BaseTableau):
    def setUp(self):
        super().setUp()
        c = noyau.ouvrir_base(self.db)[0]
        for rang, nom in enumerate(("Demain", "Urgent", "Surveiller"), 1):
            c.execute("UPDATE chantiers SET statut = 'planifie', date_prevue = ?, ordre_jour = ?, duree_estimee_h = COALESCE(duree_estimee_h, 1) WHERE id = ?",
                      (DEMAIN, rang, self.ids[nom]))
        c.close()
        self.a, self.b, self.c = (self.ids[n] for n in ("Demain", "Urgent", "Surveiller"))

    def ordre(self):
        return [r[0] for r in self.sql("SELECT id FROM chantiers WHERE date_prevue = ? ORDER BY ordre_jour", (DEMAIN,))]

    def ordonner(self, ids, date=DEMAIN):
        return self.post("/action/ordonner", {"date": date, "ordre": ",".join(str(i) for i in ids), "retour": f"/journee?date={DEMAIN}"})

    def test_nouvel_ordre_enregistre(self):
        self.assertEqual(self.ordre(), [self.a, self.b, self.c])
        statut, en_tetes, _ = self.ordonner([self.c, self.a, self.b])
        self.assertTrue(statut.startswith("303"))
        self.assertIn("ok=deplace", en_tetes["Location"])
        self.assertEqual(self.ordre(), [self.c, self.a, self.b])
        self.assertEqual(self.sql("SELECT ordre_jour FROM chantiers WHERE id = ?", (self.c,)), [(1,)])      # rangs 1, 2, 3

    def test_liste_incomplete_ou_etrangere_refusee(self):
        for mauvais in ([self.a, self.b], [self.a, self.b, self.c, self.ids["Normal"]], [self.a, self.a, self.b], [self.a, self.b, 99999]):
            _, en_tetes, _ = self.ordonner(mauvais)
            self.assertIn("err=", en_tetes["Location"], mauvais)
            self.assertEqual(self.ordre(), [self.a, self.b, self.c], mauvais)                               # rien n'a bougé

    def test_saisie_illisible_refusee(self):
        for form in ({"date": DEMAIN, "ordre": "1;drop"}, {"date": "demain", "ordre": f"{self.a},{self.b},{self.c}"}, {"date": DEMAIN, "ordre": ""}):
            _, en_tetes, _ = self.post("/action/ordonner", {**form, "retour": "/journee"})
            self.assertIn("err=", en_tetes["Location"], form)
        self.assertEqual(self.ordre(), [self.a, self.b, self.c])

    def test_la_page_journee_fournit_le_geste(self):
        _, page = self.get("/journee", {"date": DEMAIN})
        self.assertIn('<tbody data-glisser="ordre-jour">', page)
        for i in (self.a, self.b, self.c):
            self.assertIn(f'<tr data-id="{i}"><td class="col-ordre"><span class="poignee"', page)
        self.assertIn('<form id="ordre-jour" method="post" action="/action/ordonner" hidden>', page)
        self.assertIn(f'<input type="hidden" name="date" value="{DEMAIN}">', page)
        self.assertIn('action="/action/deplacer"', page)                     # les flèches restent pour qui n'a pas JavaScript
        self.assertIn("data-glisser", vue.SCRIPT_GLISSER)

    def test_pas_de_geste_dans_le_tableau_de_bord_ni_pour_un_seul_chantier(self):
        _, page = self.get("/", {"date": DEMAIN})
        self.assertNotIn("data-glisser=", page.replace("[data-glisser]", "").replace("getAttribute('data-glisser')", ""))
        c = noyau.ouvrir_base(self.db)[0]
        c.execute("UPDATE chantiers SET statut = 'a_planifier', date_prevue = NULL, ordre_jour = NULL WHERE id IN (?, ?)", (self.b, self.c))
        c.close()
        _, page = self.get("/journee", {"date": DEMAIN})
        self.assertNotIn('<tbody data-glisser="ordre-jour">', page)          # un seul chantier : rien à réordonner


class TestOrdreDesRaccourcis(BaseTableau):
    def ids_raccourcis(self):
        return [r[0] for r in self.sql("SELECT id FROM raccourcis WHERE page = 'chantiers' AND filtre <> '' ORDER BY ordre, id")]

    def test_nouvel_ordre_enregistre(self):
        _, page = self.get("/raccourcis", {"page": "chantiers"})            # crée les raccourcis du départ
        self.assertIn("data-glisser=ordre-raccourcis", page)
        self.assertIn('<form id="ordre-raccourcis" method="post" action="/raccourcis/ordonner" hidden>', page)
        avant = self.ids_raccourcis()
        self.assertGreaterEqual(len(avant), 3)
        nouveau = [avant[-1]] + avant[:-1]
        statut, en_tetes, _ = self.post("/raccourcis/ordonner", {"page": "chantiers", "ordre": ",".join(map(str, nouveau))})
        self.assertEqual((statut[:3], en_tetes["Location"]), ("303", "/raccourcis?page=chantiers"))
        self.assertEqual(self.ids_raccourcis(), nouveau)

    def test_liste_incomplete_refusee(self):
        self.get("/raccourcis", {"page": "chantiers"})
        avant = self.ids_raccourcis()
        for ordre in (",".join(map(str, avant[:-1])), "abc", ""):
            _, en_tetes, _ = self.post("/raccourcis/ordonner", {"page": "chantiers", "ordre": ordre})
            self.assertIn("err=", en_tetes["Location"], ordre)
        self.assertEqual(self.ids_raccourcis(), avant)


class TestRetourAuToucher(BaseTableau):
    def test_tuile_surlignee_et_journee_animee(self):
        """Une tuile touchée garde un contour vert ; sur téléphone, la journée choisie dans le calendrier monte en douceur."""
        import telephone
        self.assertIn('t.classList.add("touche")', vue.SCRIPT_TOUCHE)
        self.assertIn("tr.touche{outline:2px solid var(--vert);outline-offset:-2px}", vue.CSS)
        self.assertIn(".carte.arrive{animation:monte .28s", telephone.CSS_TELEPHONE)
        # le contour ne vient qu'au vrai toucher (clic) : rien ne s'allume quand le doigt se pose pour faire défiler
        self.assertNotIn("tbody tr:active", telephone.CSS_TELEPHONE)
        self.assertIn('document.addEventListener("click"', vue.SCRIPT_TOUCHE)
        # iPhone : pas de rectangle gris sur le nom au toucher, ni de menu « Partager le lien » au toucher long sur une tuile
        self.assertIn("*{-webkit-tap-highlight-color:transparent}", telephone.CSS_TELEPHONE)
        self.assertIn("table.archive tbody tr{-webkit-touch-callout:none;-webkit-user-select:none;user-select:none}", telephone.CSS_TELEPHONE)
        _, page = self.get("/", {"date": DEMAIN})
        self.assertIn('<div class="carte carte-jour arrive">', page)          # on vient de choisir un jour
        vide = (AUJOURDHUI + datetime.timedelta(days=9)).isoformat()
        _, page = self.get("/", {"date": vide})
        self.assertIn('<div class="carte arrive"><h2>', page)                 # une journée vide arrive de la même façon
        _, page = self.get("/")
        self.assertNotIn(" arrive", page.split("</head>")[1].split("<script")[0])      # simple ouverture du tableau de bord : pas d'animation
        self.assertIn(vue.SCRIPT_TOUCHE, page)


if __name__ == "__main__":
    unittest.main()
