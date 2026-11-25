"""Placement : point de référence, position, rotation autour de la référence."""
import math
import os

import pytest

from cut_layout.importers import Sm2dPattern
from cut_layout.model import Piece
from cut_layout.model.placement import (REF_CENTROID, Placement, change_reference, normalize_angle,
                                        outside_plan, placed_bbox, placed_outline, placement_at_corner,
                                        reference_point, rotation, to_plan, toggle_mirror)

# Rectangle 40 × 10 mm placé n'importe où dans le brouillon, nœud "A" au coin inférieur droit.
RECT = Piece("R", "b", ((100, 200), (140, 200), (140, 210), (100, 210)), nodes={"A": (140, 200)})


@pytest.fixture(scope="module")
def devant():
    s = os.environ["SM2D_SAMPLES"]
    return Sm2dPattern(os.path.join(s, "patron.sm2d"), os.path.join(s, "mesures.smis")).piece("Demi-devant")


def test_reference_barycentre_et_noeud():
    assert reference_point(RECT, REF_CENTROID) == pytest.approx((120, 205))
    assert reference_point(RECT, "A") == (140, 200)
    with pytest.raises(ValueError):
        reference_point(RECT, "Z")


def test_point_de_reference_place_aux_coordonnees_saisies(devant):
    # scénario de Vincent : D7 en (30 cm ; 1 cm)
    pl = Placement("D7", 300.0, 10.0, 0.0)
    assert to_plan(devant, pl, devant.nodes["D7"]) == pytest.approx((300.0, 10.0), abs=1e-9)


@pytest.mark.parametrize("angle,expected", [(0, (1, 0)), (90, (0, 1)), (180, (-1, 0)), (-90, (0, -1)), (270, (0, -1))])
def test_rotation_sens_trigonometrique_exacte(angle, expected):
    assert rotation(angle) == expected          # égalité exacte, pas d'approximation


def test_rotation_90_sur_le_plan():
    # référence A ; le coin opposé (100, 210) est à (-40, +10) de A ; après +90° : (-10, -40)
    pl = Placement("A", 500, 500, 90)
    assert to_plan(RECT, pl, (100, 210)) == (490, 460)
    x0, y0, x1, y1 = placed_bbox(RECT, pl)
    assert (x1 - x0, y1 - y0) == (10, 40)       # largeur et hauteur échangées


@pytest.mark.parametrize("angle", [0, 90, -90, 180, 37.5, -123.25])
def test_rotation_autour_de_la_reference_et_isometrie(devant, angle):
    for ref in (REF_CENTROID, "D7", "C5"):
        pl = Placement(ref, 400.0, 600.0, angle)
        assert to_plan(devant, pl, reference_point(devant, ref)) == pytest.approx((400, 600), abs=1e-9)
        out = placed_outline(devant, pl)
        for i in (0, 57, 300):
            assert math.dist(out[i], out[i + 1]) == pytest.approx(
                math.dist(devant.outline[i], devant.outline[i + 1]), abs=1e-9)
        assert Piece("x", "b", tuple(out)).area == pytest.approx(devant.area, rel=1e-12)


@pytest.mark.parametrize("angle", [0, 90, 33])
def test_changer_de_reference_ne_deplace_pas_la_piece(devant, angle):
    pl = Placement("D7", 300.0, 10.0, angle)
    pl2 = change_reference(devant, pl, REF_CENTROID)
    assert pl2.ref == REF_CENTROID and pl2.angle == angle
    a, b = placed_outline(devant, pl), placed_outline(devant, pl2)
    assert max(math.dist(p, q) for p, q in zip(a, b)) < 1e-9


@pytest.mark.parametrize("angle", [0, 90, -90, 180, 45])
def test_placement_par_le_coin_inferieur_gauche(devant, angle):
    pl = placement_at_corner(devant, 250.0, 0.0, angle)
    x0, y0, _, _ = placed_bbox(devant, pl)
    assert (x0, y0) == pytest.approx((250.0, 0.0), abs=1e-9)
    assert not outside_plan(devant, pl)


def test_piece_hors_du_plan_signalee():
    assert not outside_plan(RECT, placement_at_corner(RECT, 0, 0))
    assert outside_plan(RECT, placement_at_corner(RECT, -0.01, 0))
    assert outside_plan(RECT, placement_at_corner(RECT, 0, -0.01))
    assert outside_plan(RECT, Placement(REF_CENTROID, 0, 0, 0))   # barycentre à l'origine


@pytest.mark.parametrize("a,n", [(0, 0), (180, 180), (-180, 180), (270, -90), (-270, 90), (450, 90), (360, 0)])
def test_normalisation_angle(a, n):
    assert normalize_angle(a) == n


# -- symétrie ------------------------------------------------------------------

def test_symetrie_rectangle_reference_fixe():
    """Nœud A (coin inférieur droit) en (0, 0) : retourné, le rectangle passe à gauche de A."""
    pl = Placement("A", 0.0, 0.0, 0.0, mirrored=True)
    assert placed_bbox(RECT, pl) == (0.0, 0.0, 40.0, 10.0)
    assert to_plan(RECT, pl, (100, 200)) == (40.0, 0.0)          # coin inférieur gauche → à droite
    assert to_plan(RECT, Placement("A", 0.0, 0.0, 90.0, mirrored=True), (100, 200)) == (0.0, 40.0)


def _area(pts):
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))


@pytest.mark.parametrize("angle", [0, 90, -90, 180, 37.5])
@pytest.mark.parametrize("ref", [REF_CENTROID, "D7"])
def test_retourner_sur_le_plan_axe_vertical_par_la_reference(devant, angle, ref):
    """toggle_mirror = image miroir, sur le plan, par l'axe vertical x = x_ref ; référence immobile."""
    pl = Placement(ref, 300.0, 400.0, angle)
    flipped = toggle_mirror(pl)
    assert flipped.mirrored and flipped.angle == normalize_angle(-angle)
    expected = [(2 * 300.0 - x, y) for x, y in placed_outline(devant, pl)]
    got = placed_outline(devant, flipped)
    assert max(math.dist(p, q) for p, q in zip(got, expected)) < 1e-9
    assert to_plan(devant, flipped, reference_point(devant, ref)) == pytest.approx((300.0, 400.0), abs=1e-9)
    assert _area(got) == pytest.approx(-_area(placed_outline(devant, pl)), rel=1e-12)   # même aire, sens inversé
    assert toggle_mirror(flipped) == Placement(ref, 300.0, 400.0, normalize_angle(angle))


@pytest.mark.parametrize("angle", [0, 90, 33])
def test_rotation_positive_antihoraire_meme_retournee(devant, angle):
    """Retournée ou non, +90° fait tourner la pièce dans le sens antihoraire autour de la référence."""
    for mirrored in (False, True):
        pl = Placement(REF_CENTROID, 0.0, 0.0, angle, mirrored)
        before = placed_outline(devant, pl)
        after = placed_outline(devant, Placement(REF_CENTROID, 0.0, 0.0, angle + 90, mirrored))
        assert max(math.dist((-y, x), q) for (x, y), q in zip(before, after)) < 1e-9


def test_changer_de_reference_piece_retournee(devant):
    pl = Placement(REF_CENTROID, 300.0, 400.0, 30.0, mirrored=True)
    moved = change_reference(devant, pl, "D7")
    assert moved.mirrored
    assert max(math.dist(p, q) for p, q in zip(placed_outline(devant, pl), placed_outline(devant, moved))) < 1e-9
