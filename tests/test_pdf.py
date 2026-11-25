"""PDF relus avec pdfplumber : dimensions et positions mesurées dans le fichier généré.

Tolérance de relecture : 0,01 mm (validée par Vincent le 24.11.2026). L'écart relevé le
24.11.2026 entre valeur écrite et valeur relue est < 0,0001 mm (reportlab écrit 4 décimales en mm).
"""
import math
import os

import pdfplumber
import pytest

from cut_layout.export import export_mosaic, export_test_page
from cut_layout.export.test_page import EDGE_DISTANCES_MM, X_RULER_MM, Y_RULER_MM
from cut_layout.importers import Sm2dPattern
from cut_layout.model.mosaic import Grid, SheetSettings, fit_grid
from cut_layout.model.placement import Placement, placed_bbox, placed_outline, placement_at_corner

TOL = 0.01                    # mm, validée par Vincent
PT = 72 / 25.4                # points par mm


def mm(v):
    return float(v) / PT


def page_objects(page):
    """Rectangles, lignes et chemins en mm, origine en bas à gauche."""
    H = float(page.height)

    def conv(o):
        return [(mm(x), mm(H - y)) for x, y in o["pts"]]
    return {
        "rects": [(mm(o["x0"]), mm(H - o["bottom"]), mm(o["x1"]), mm(H - o["top"]), o.get("dash")) for o in page.rects],
        "lines": [conv(o) for o in page.lines],
        "curves": [conv(o) for o in page.curves],
    }


def all_points(objs):
    return [p for kind in ("lines", "curves") for path in objs[kind] for p in path]


# --- mosaïque : pièce rectangulaire connue ------------------------------------

@pytest.fixture
def rect_export(tmp_path):
    # rectangle 300 × 100 mm, coin inférieur gauche en (50, 20) : couvre les colonnes 1 et 2 de la ligne 1
    rect = [(50.0, 20.0), (350.0, 20.0), (350.0, 120.0), (50.0, 120.0)]
    s = SheetSettings()
    grid = Grid(s, rows=2, cols=3)
    path = tmp_path / "mosaique.pdf"
    report = export_mosaic(path, grid, [("R", rect)], overview=False)
    return path, grid, report, rect


def test_pages_vides_omises_et_ordre(rect_export):
    _, grid, report, _ = rect_export
    assert report.pages == [(1, 1), (1, 2)]
    assert report.omitted == [(1, 3), (2, 1), (2, 2), (2, 3)]


def test_taille_de_page_exacte(rect_export):
    path, *_ = rect_export
    with pdfplumber.open(path) as pdf:
        assert len(pdf.pages) == 2
        for page in pdf.pages:
            assert (mm(page.width), mm(page.height)) == pytest.approx((210.0, 297.0), abs=TOL)


def test_cadre_de_coupe_a_la_marge_d_assemblage(rect_export):
    path, *_ = rect_export
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            frames = [r for r in page_objects(page)["rects"] if r[4] is not None and r[4][0]]
            assert len(frames) == 1
            assert frames[0][:4] == pytest.approx((10.0, 10.0, 200.0, 287.0), abs=TOL)


def test_trace_a_la_bonne_position(rect_export):
    # page L1-C1 : coin (50, 20) du plan → (60, 30) sur la feuille ; bord haut y = 120 → 130
    path, *_ = rect_export
    with pdfplumber.open(path) as pdf:
        pts = all_points(page_objects(pdf.pages[0]))
    assert any(math.dist(p, (60.0, 30.0)) < TOL for p in pts)
    assert any(abs(p[1] - 130.0) < TOL for p in pts)


def test_trace_jamais_au_dela_de_la_marge_d_impression(rect_export):
    path, *_ = rect_export
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for x, y in all_points(page_objects(page)):
                assert 5.0 - TOL <= x <= 205.0 + TOL and 5.0 - TOL <= y <= 292.0 + TOL


def test_continuite_entre_pages_voisines(rect_export):
    # le bord bas du rectangle traverse la frontière x = 190 du plan : présent à x = 200 (L1-C1) et x = 10 (L1-C2)
    path, *_ = rect_export
    with pdfplumber.open(path) as pdf:
        p1 = all_points(page_objects(pdf.pages[0]))
        p2 = all_points(page_objects(pdf.pages[1]))
    # L1-C1 imprime jusqu'à x = 195 du plan (205 sur la feuille) ; L1-C2 depuis 185 (5 sur la feuille)
    assert any(math.dist(p, (205.0, 30.0)) < TOL for p in p1)
    assert any(math.dist(p, (5.0, 30.0)) < TOL for p in p2)
    # même point du plan (x = 190, y = 20) : (200, 30) sur L1-C1 et (10, 30) sur L1-C2, sur le segment tracé
    for pts, target in ((p1, (200.0, 30.0)), (p2, (10.0, 30.0))):
        xs = sorted(x for x, y in pts if abs(y - 30.0) < TOL)
        assert xs[0] - TOL <= target[0] <= xs[-1] + TOL


def test_repere_de_page_dans_la_bande(rect_export):
    path, *_ = rect_export
    with pdfplumber.open(path) as pdf:
        for page, label in zip(pdf.pages, ("R1-C1", "R1-C2")):
            words = page.extract_words()
            w = next(w for w in words if w["text"] == label)
            bottom = mm(page.height - w["bottom"])
            top = mm(page.height - w["top"])
            assert 5.0 - TOL <= bottom and top <= 10.0 + TOL      # entre la marge d'impression et le cadre


def test_aucune_page_si_plan_vide(tmp_path):
    report = export_mosaic(tmp_path / "vide.pdf", Grid(SheetSettings(), 1, 1), [])
    assert report.pages == [] and not (tmp_path / "vide.pdf").exists()


# --- mosaïque : patron réel ---------------------------------------------------

def test_patron_reel_cotes_relues_dans_le_pdf(tmp_path):
    s = os.environ["SM2D_SAMPLES"]
    p = Sm2dPattern(os.path.join(s, "patron.sm2d"), os.path.join(s, "mesures.smis")).piece("Demi-devant")
    pl = Placement("D7", 30.0, 15.0, 0.0)
    outline = placed_outline(p, pl)
    grid = fit_grid(SheetSettings(), [placed_bbox(p, pl)])
    path = tmp_path / "devant.pdf"
    report = export_mosaic(path, grid, [("Demi-devant", outline)], overview=False)
    assert report.pages == [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1), (3, 2)]
    # D7 (30 ; 15) du plan → (40 ; 25) sur la feuille L1-C1
    with pdfplumber.open(path) as pdf:
        pts = all_points(page_objects(pdf.pages[0]))
        assert any(math.dist(q, (40.0, 25.0)) < TOL for q in pts)
        # bas de la pièce relu sur la ligne 1, haut relu sur la ligne 3 (pages 5 et 6), ramenés au plan
        bottom = min(y for i in (0, 1) for x, y in all_points(page_objects(pdf.pages[i]))) - 10.0
        top = max(y for i in (4, 5) for x, y in all_points(page_objects(pdf.pages[i]))) - 10.0 + 2 * 277.0
    x0, y0, x1, y1 = placed_bbox(p, pl)
    assert (bottom, top) == pytest.approx((y0, y1), abs=TOL)
    assert top - bottom == pytest.approx(685.0, abs=0.1)          # grande cote du tutoriel


# --- page d'essai -------------------------------------------------------------

@pytest.fixture(params=["portrait", "landscape"])
def test_page(tmp_path, request):
    """Page d'essai dans l'orientation de la mise en page (paysage : vérifier la correction en paysage)."""
    path = export_test_page(tmp_path / "essai.pdf", SheetSettings(orientation=request.param))
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        return page_objects(page), (mm(page.width), mm(page.height)), page.extract_words(), request.param


def test_page_d_essai_dans_l_orientation_choisie(test_page):
    _, size, _, orientation = test_page
    expected = (210.0, 297.0) if orientation == "portrait" else (297.0, 210.0)
    assert size == pytest.approx(expected, abs=TOL)


def test_page_d_essai_cadre_de_coupe(test_page):
    objs, (W, H), _, _ = test_page
    frames = [r for r in objs["rects"] if r[4] is not None and r[4][0]]
    assert len(frames) == 1 and frames[0][:4] == pytest.approx((10.0, 10.0, W - 10.0, H - 10.0), abs=TOL)


def test_page_d_essai_traits_de_bord(test_page):
    objs, (W, H), _, _ = test_page
    lines = objs["lines"]
    for d in EDGE_DISTANCES_MM:
        assert any(abs(a[1] - d) < TOL and abs(b[1] - d) < TOL for a, b in lines)              # bas
        assert any(abs(a[1] - (H - d)) < TOL and abs(b[1] - (H - d)) < TOL for a, b in lines)  # haut
        assert any(abs(a[0] - d) < TOL and abs(b[0] - d) < TOL for a, b in lines)              # gauche
        assert any(abs(a[0] - (W - d)) < TOL and abs(b[0] - (W - d)) < TOL for a, b in lines)  # droite


def test_page_d_essai_regles_x_180_et_y_260(test_page):
    """x = petit côté du papier (180 mm), y = grand côté (260 mm) : en paysage, x est verticale."""
    objs, _, words, orientation = test_page
    long_lines = {(round(abs(b[0] - a[0]), 6), round(abs(b[1] - a[1]), 6)) for a, b in objs["lines"]
                  if math.dist(a, b) > 100}
    horizontal, vertical = (X_RULER_MM, Y_RULER_MM) if orientation == "portrait" else (Y_RULER_MM, X_RULER_MM)
    assert len(long_lines) == 2
    got = [v for d in sorted(long_lines) for v in d]
    assert got == pytest.approx([v for d in sorted([(horizontal, 0.0), (0.0, vertical)]) for v in d], abs=TOL)
    assert (X_RULER_MM, Y_RULER_MM) == (180, 260)


def test_page_d_essai_regles_dans_le_cadre(test_page):
    objs, (W, H), _, _ = test_page
    for a, b in objs["lines"]:
        if math.dist(a, b) > 100:
            for x, y in (a, b):
                assert 10.0 < x < W - 10.0 and 10.0 < y < H - 10.0


def test_lettres_dans_les_coins_communs(rect_export):
    # grille 2 × 3 : A (0,1), B (0,2), C (1,0), D (1,1), E (1,2), F (1,3), G (2,1), H (2,2)
    path, *_ = rect_export
    expected = [{"br": "A", "tl": "C", "tr": "D"}, {"bl": "A", "br": "B", "tl": "D", "tr": "E"}]
    with pdfplumber.open(path) as pdf:
        for page, letters in zip(pdf.pages, expected):
            words = {w["text"]: w for w in page.extract_words()}
            for corner, letter in letters.items():
                w = words[letter]
                x0, x1 = mm(w["x0"]), mm(w["x1"])
                bottom, top = mm(page.height - w["bottom"]), mm(page.height - w["top"])
                assert 10.0 < x0 and x1 < 200.0 and 10.0 < bottom and top < 287.0     # dans le cadre
                if corner[0] == "b":
                    assert bottom < 10.0 + 3.0
                else:
                    assert top > 287.0 - 3.0
                if corner[1] == "l":
                    assert x0 < 10.0 + 3.0
                else:
                    assert x1 > 200.0 - 3.0
            assert not set(words) & set("FGH")


@pytest.fixture
def overview_export(tmp_path):
    rect = [(50.0, 20.0), (350.0, 20.0), (350.0, 120.0), (50.0, 120.0)]
    grid = Grid(SheetSettings(), rows=2, cols=3)
    path = tmp_path / "montage.pdf"
    report = export_mosaic(path, grid, [("Rectangle", rect)], title="Essai", name="Essai")
    return path, grid, report


def test_plan_de_montage_en_premiere_page(overview_export):
    path, grid, report = overview_export
    assert report.overview and report.pages == [(1, 1), (1, 2)]
    with pdfplumber.open(path) as pdf:
        assert len(pdf.pages) == 1 + len(report.pages)
        text = pdf.pages[0].extract_text()
        assert text.split("\n")[:2] == ["Assembly plan", "Essai"]
        assert "do not measure" in text and "Rectangle" in text
        for r, c in grid.cells():
            assert Grid.label(r, c) in text
        words = {w["text"] for w in pdf.pages[0].extract_words()}
        assert set(grid.corner_letters().values()) <= words
        # les pages suivantes sont les feuilles 1:1, dans l'ordre
        assert "R1-C1" in pdf.pages[1].extract_text() and "R1-C2" in pdf.pages[2].extract_text()


def test_plan_de_montage_echelle_indiquee_exacte(overview_export):
    path, grid, report = overview_export
    k = report.overview_scale
    # grille de 3 × 2 cellules A4 (570 × 554 mm) dans 180 × 239 mm : la largeur limite
    assert k == pytest.approx((210 - 30) / (3 * 190))
    with pdfplumber.open(path) as pdf:
        assert f"Scale 1:{1 / k:.1f}" in pdf.pages[0].extract_text()
        rects = page_objects(pdf.pages[0])["rects"]
    widths = sorted({round(r[2] - r[0], 3) for r in rects})
    assert any(w == pytest.approx(190 * k, abs=TOL) for w in widths)       # cellule réduite à l'échelle


def test_plan_de_montage_feuilles_vides_grisees(overview_export):
    path, grid, report = overview_export
    with pdfplumber.open(path) as pdf:
        fills = [r for r in pdf.pages[0].rects if r["fill"]]
    grey = [r for r in fills if r["non_stroking_color"] not in ((1,), (1.0,), [1], [1.0], 1)]
    assert len(grey) == len(report.omitted) == 4


def test_plan_de_montage_en_paysage_si_plus_grand(tmp_path):
    rect = [(10.0, 10.0), (700.0, 10.0), (700.0, 100.0), (10.0, 100.0)]
    grid = Grid(SheetSettings(), rows=1, cols=4)            # 760 × 277 mm : bien plus large que haut
    path = tmp_path / "large.pdf"
    report = export_mosaic(path, grid, [("Bande", rect)])
    with pdfplumber.open(path) as pdf:
        first, sheet = pdf.pages[0], pdf.pages[1]
        assert (mm(first.width), mm(first.height)) == pytest.approx((297.0, 210.0), abs=TOL)
        assert (mm(sheet.width), mm(sheet.height)) == pytest.approx((210.0, 297.0), abs=TOL)   # feuilles inchangées
    assert report.overview_scale == pytest.approx((297 - 30) / 760)


@pytest.mark.parametrize("name", ["patron_de_base_buste_et_manche_exemple_de_nom_tres_long_2026_boulot",
                                  "x" * 300])
def test_plan_de_montage_nom_long_dans_la_page(tmp_path, name):
    rect = [(10.0, 10.0), (100.0, 10.0), (100.0, 100.0), (10.0, 100.0)]
    path = tmp_path / "long.pdf"
    export_mosaic(path, Grid(SheetSettings(), 1, 1), [("R", rect)], name=name)
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        assert max(ch["x1"] for ch in page.chars) <= page.width - 15.0 * PT + 0.01
        text = page.extract_text()
    shown = text.split("\n")[1]
    assert shown == name or (shown.endswith("…") and name.startswith(shown[:-1]))


def test_page_d_essai_regles_raccourcies_sur_un_petit_format():
    from cut_layout.export.test_page import ruler_lengths
    assert ruler_lengths(SheetSettings()) == (180, 260)
    assert ruler_lengths(SheetSettings("custom", custom_width=150.0, custom_height=200.0)) == (120, 160)


def test_page_d_essai_paysage_correction_echangee(tmp_path):
    """Paysage : la correction x (petit côté du papier) s'applique à la hauteur de la page."""
    from cut_layout.model.correction import PrintCorrection
    corr = PrintCorrection(190.0, 188.8, 277.0, 276.7)
    path = export_test_page(tmp_path / "p.pdf", SheetSettings(orientation="landscape"), correction=corr)
    with pdfplumber.open(path) as pdf:
        objs = page_objects(pdf.pages[0])
    frame = next(r for r in objs["rects"] if r[4] is not None and r[4][0])
    width, height = frame[2] - frame[0], frame[3] - frame[1]
    assert width == pytest.approx(277.0 * corr.fy, abs=TOL)      # grand côté du papier : y
    assert height == pytest.approx(190.0 * corr.fx, abs=TOL)     # petit côté du papier : x
