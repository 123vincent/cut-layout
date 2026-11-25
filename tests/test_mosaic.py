"""Mosaïque : tailles de cellule, pavage, bande imprimée, repère feuille, ajustement automatique."""
import pytest

from cut_layout.model.mosaic import Grid, MosaicError, SheetSettings, fit_grid, column_letters

# PROMPT §3 bis, avec une marge d'assemblage de 10 mm
CELLS = {
    ("A4", "portrait"): (190.0, 277.0),
    ("A4", "landscape"): (277.0, 190.0),
    ("A3", "portrait"): (277.0, 400.0),
    ("A3", "landscape"): (400.0, 277.0),
}


@pytest.mark.parametrize("fmt,cell", CELLS.items())
def test_taille_de_cellule(fmt, cell):
    assert SheetSettings(*fmt).cell_size == cell


def test_bande_imprimee_5_mm_par_defaut():
    assert SheetSettings().bleed == 5.0


@pytest.mark.parametrize("kw", [
    dict(print_margin=10.0), dict(print_margin=12.0), dict(print_margin=-1.0),
    dict(format="B5"), dict(format="custom"), dict(format="custom", custom_width=40.0, custom_height=300.0), dict(orientation="Portrait"), dict(assembly_margin=110.0, print_margin=1.0),
])
def test_reglages_invalides_refuses(kw):
    with pytest.raises(MosaicError):
        SheetSettings(**kw)


def test_cellules_ligne_1_en_bas_colonne_1_a_gauche():
    g = Grid(SheetSettings(), rows=2, cols=3)
    assert g.cell_rect(1, 1) == (0.0, 0.0, 190.0, 277.0)       # entièrement dans x ≥ 0, y ≥ 0
    assert g.cell_rect(2, 3) == (380.0, 277.0, 570.0, 554.0)
    assert list(g.cells()) == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)]
    assert Grid.label(2, 3) == "R2-C3"
    with pytest.raises(MosaicError):
        g.cell_rect(3, 1)


def test_pavage_sans_trou_ni_recouvrement():
    g = Grid(SheetSettings("A3", "landscape"), rows=3, cols=4)
    for r, c in g.cells():
        x0, y0, x1, y1 = g.cell_rect(r, c)
        if c < g.cols:
            assert g.cell_rect(r, c + 1)[0] == x1
        if r < g.rows:
            assert g.cell_rect(r + 1, c)[1] == y1
    assert g.cell_rect(g.rows, g.cols)[2:] == g.extent


def test_portion_imprimee():
    g = Grid(SheetSettings(), rows=2, cols=2)
    assert g.printed_rect(1, 2) == (185.0, -5.0, 385.0, 282.0)


def test_cadre_de_coupe_a_la_marge_d_assemblage_sur_la_feuille():
    s = SheetSettings()
    g = Grid(s, rows=2, cols=2)
    W, H = s.sheet_size
    for r, c in g.cells():
        x0, y0, x1, y1 = g.cell_rect(r, c)
        assert g.plan_to_sheet(r, c, (x0, y0)) == (10.0, 10.0)
        assert g.plan_to_sheet(r, c, (x1, y1)) == (W - 10.0, H - 10.0)
        px0, py0, px1, py1 = g.printed_rect(r, c)
        # étendue imprimée : exactement jusqu'à la marge d'impression, jamais au-delà
        assert g.plan_to_sheet(r, c, (px0, py0)) == (5.0, 5.0)
        assert g.plan_to_sheet(r, c, (px1, py1)) == (W - 5.0, H - 5.0)


def test_continuite_entre_cellules_voisines():
    # un point de la frontière L1-C1 | L1-C2 est imprimé sur les deux pages, au même point du plan
    g = Grid(SheetSettings(), rows=1, cols=2)
    p = (190.0, 100.0)
    a, b = g.plan_to_sheet(1, 1, p), g.plan_to_sheet(1, 2, p)
    assert a == (200.0, 110.0) and b == (10.0, 110.0)     # bord droit du cadre / bord gauche du cadre
    for (r, c) in ((1, 1), (1, 2)):
        x0, y0, x1, y1 = g.printed_rect(r, c)
        assert x0 <= p[0] <= x1 and y0 <= p[1] <= y1


@pytest.mark.parametrize("bboxes,rows,cols", [
    ([], 1, 1),
    ([(0, 0, 190.0, 277.0)], 1, 1),                        # exactement une cellule
    ([(0, 0, 190.0 + 1e-9, 277.0)], 1, 1),                 # bruit d'arrondi : pas de feuille de plus
    ([(0, 0, 190.01, 277.0)], 1, 2),
    ([(0, 0, 285.0, 700.333), (305, 0, 580, 685)], 3, 4),  # demi-dos + demi-devant côte à côte
    ([(-50, -20, 100, 100)], 1, 1),                        # partie négative non couverte (signalée ailleurs)
])
def test_ajustement_automatique(bboxes, rows, cols):
    g = fit_grid(SheetSettings(), bboxes)
    assert (g.rows, g.cols) == (rows, cols)


def test_lettres_des_coins_communs():
    g = Grid(SheetSettings(), rows=2, cols=2)
    # coins extérieurs (0,0), (0,2), (2,0), (2,2) : une seule feuille, pas de lettre
    assert g.corner_letters() == {(0, 1): "A", (1, 0): "B", (1, 1): "C", (1, 2): "D", (2, 1): "E"}
    assert g.cell_corner_letters(1, 1) == {"br": "A", "tl": "B", "tr": "C"}
    assert g.cell_corner_letters(2, 2) == {"bl": "C", "br": "D", "tl": "E"}
    assert Grid(SheetSettings(), rows=1, cols=1).corner_letters() == {}


def test_coin_commun_meme_lettre_sur_chaque_feuille():
    g = Grid(SheetSettings(), rows=3, cols=4)
    offsets = {"bl": (-1, -1), "br": (-1, 0), "tl": (0, -1), "tr": (0, 0)}
    seen = {}
    for r, c in g.cells():
        for corner, letter in g.cell_corner_letters(r, c).items():
            di, dj = offsets[corner]
            seen.setdefault(letter, set()).add((r + di, c + dj))
    assert all(len(v) == 1 for v in seen.values())          # une lettre = un seul point du plan
    assert len(seen) == (3 + 1) * (4 + 1) - 4


@pytest.mark.parametrize("n,text", [(0, "A"), (25, "Z"), (26, "AA"), (27, "AB"), (701, "ZZ"), (702, "AAA")])
def test_suite_des_lettres(n, text):
    assert column_letters(n) == text


@pytest.mark.parametrize("fmt,size", [("A2", (420, 594)), ("A1", (594, 841)), ("A0", (841, 1189)),
                                      ("Letter", (215.9, 279.4)), ("Legal", (215.9, 355.6)),
                                      ("Tabloid", (279.4, 431.8))])
def test_formats_standard(fmt, size):
    assert SheetSettings(fmt).sheet_size == size
    assert SheetSettings(fmt, "landscape").sheet_size == size[::-1]


@pytest.mark.parametrize("w,h", [(500.0, 700.0), (700.0, 500.0)])
def test_format_personnalise_petit_cote_en_largeur(w, h):
    """Le petit côté est la largeur en portrait, quel que soit l'ordre de saisie (x = petit côté du papier)."""
    s = SheetSettings("custom", custom_width=w, custom_height=h)
    assert s.sheet_size == (500.0, 700.0) and s.cell_size == (480.0, 680.0)
    assert SheetSettings("custom", "landscape", custom_width=w, custom_height=h).sheet_size == (700.0, 500.0)
    assert s.describe() == "custom 500 × 700 mm portrait"
