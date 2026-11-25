import pytest

from cut_layout.model import Piece, polygon_area, polygon_centroid

# L de 30 × 20 mm : rectangle 30 × 10 (bas) + rectangle 10 × 10 (haut gauche).
# Barycentre calculé à la main : aire 400 ; x = (300·15 + 100·5)/400 = 12,5 ; y = (300·5 + 100·15)/400 = 7,5
L_SHAPE = ((0, 0), (30, 0), (30, 10), (10, 10), (10, 20), (0, 20))


def test_aire_et_barycentre_de_surface():
    assert polygon_area(L_SHAPE) == pytest.approx(400)
    assert polygon_centroid(L_SHAPE) == pytest.approx((12.5, 7.5), abs=1e-12)


def test_barycentre_independant_du_sens_et_de_la_densite_des_sommets():
    # sens horaire, et un côté découpé en nombreux sommets : la moyenne des sommets bougerait, pas le barycentre
    dense = [(x / 10, 0) for x in range(0, 300)] + list(L_SHAPE[1:])
    assert polygon_centroid(dense) == pytest.approx((12.5, 7.5), abs=1e-9)
    assert polygon_centroid(dense[::-1]) == pytest.approx((12.5, 7.5), abs=1e-9)


def test_barycentre_aire_nulle_refuse():
    with pytest.raises(ValueError):
        polygon_centroid(((0, 0), (1, 1), (2, 2)))


def test_dimensions_piece():
    p = Piece("L", "bloc", tuple((x + 100, y - 50) for x, y in L_SHAPE))
    assert p.bbox == (100, -50, 130, -30)
    assert (p.width, p.height, p.area) == (30, 20, 400)
    assert p.centroid == pytest.approx((112.5, -42.5))
