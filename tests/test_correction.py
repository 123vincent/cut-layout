"""Correction d'échelle de l'imprimante : facteurs, validation, effet relu dans le PDF."""
import math

import pdfplumber
import pytest

from cut_layout.export import export_mosaic, export_test_page
from cut_layout.export.test_page import X_RULER_MM, Y_RULER_MM
from cut_layout.model.correction import NO_CORRECTION, CorrectionError, PrintCorrection
from cut_layout.model.mosaic import Grid, SheetSettings

TOL = 0.01     # mm, validée par Vincent
PT = 72 / 25.4

# mesure de Vincent du 24.11.2026 sur le cadre de coupe A4 (page d'essai sans correction,
# imprimante laser) : 188,8 mm pour 190 en x, 276,7 mm pour 277 en y
VINCENT = PrintCorrection(190, 188.8, 277, 276.7)
FX, FY = 190 / 188.8, 277 / 276.7


def test_facteurs():
    assert (VINCENT.fx, VINCENT.fy) == pytest.approx((FX, FY))
    assert NO_CORRECTION.is_identity and not VINCENT.is_identity


def test_paysage_echange_les_axes():
    assert VINCENT.page_factors("portrait") == (VINCENT.fx, VINCENT.fy)
    assert VINCENT.page_factors("landscape") == (VINCENT.fy, VINCENT.fx)


@pytest.mark.parametrize("args", [(180, 0, 260, 260), (-1, 180, 260, 260), (180, 170, 260, 260), (190, 200, 277, 277)])
def test_valeurs_refusees(args):
    with pytest.raises(CorrectionError):
        PrintCorrection(*args)


def test_correction_juste_sous_la_limite_acceptee():
    PrintCorrection(180, 172.5, 260, 260)       # +4,3 %


def _lines_mm(path):
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        H = float(page.height)
        lines = [[(x / PT, (H - y) / PT) for x, y in o["pts"]] for o in page.lines]
        rects = [(o["x0"] / PT, (H - o["bottom"]) / PT, o["x1"] / PT, (H - o["top"]) / PT, o.get("dash"))
                 for o in page.rects]
    return lines, rects


def test_page_d_essai_corrigee(tmp_path):
    path = export_test_page(tmp_path / "essai.pdf", SheetSettings(), correction=VINCENT)
    lines, rects = _lines_mm(path)
    rulers = sorted((abs(b[0] - a[0]), abs(b[1] - a[1])) for a, b in lines if math.dist(a, b) > 100)
    # règles allongées du facteur de correction : réduites par l'imprimante, elles mesureront 180 et 260
    assert rulers[0] == pytest.approx((0.0, Y_RULER_MM * FY), abs=TOL)
    assert rulers[1] == pytest.approx((X_RULER_MM * FX, 0.0), abs=TOL)
    # cadre de coupe agrandi autour du centre de la page (105 ; 148,5) : 190 × FX = 191,27 ; 277 × FY = 277,30
    frame = next(r for r in rects if r[4] is not None and r[4][0])
    assert frame[:4] == pytest.approx((105.0 - 95.0 * FX, 148.5 - 138.5 * FY,
                                       105.0 + 95.0 * FX, 148.5 + 138.5 * FY), abs=TOL)
    assert frame[2] - frame[0] == pytest.approx(190.0 * 190 / 188.8, abs=TOL)


def test_page_d_essai_sans_correction_inchangee(tmp_path):
    path = export_test_page(tmp_path / "essai.pdf", SheetSettings(), correction=NO_CORRECTION)
    lines, _ = _lines_mm(path)
    rulers = sorted(math.dist(a, b) for a, b in lines if math.dist(a, b) > 100)
    assert rulers == pytest.approx([X_RULER_MM, Y_RULER_MM], abs=TOL)


def test_mosaique_corrigee(tmp_path):
    rect = [(50.0, 20.0), (150.0, 20.0), (150.0, 120.0), (50.0, 120.0)]
    path = tmp_path / "m.pdf"
    export_mosaic(path, Grid(SheetSettings(), 1, 1), [("R", rect)], correction=VINCENT, overview=False)
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        H = float(page.height)
        # un contour fermé à 4 côtés droits est classé par pdfplumber parmi les rectangles
        pts = [(x / PT, (H - y) / PT) for o in page.curves + page.lines + page.rects for x, y in o["pts"]]
    # coin (60, 30) sur la feuille, x corrigé autour du centre de la page (105)
    expected = (105.0 + (60.0 - 105.0) * FX, 148.5 + (30.0 - 148.5) * FY)
    assert any(math.dist(p, expected) < TOL for p in pts)
