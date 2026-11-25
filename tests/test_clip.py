import pytest

from cut_layout.model.clip import clip_closed_polyline, clip_segment, point_in_polygon, polygon_touches_rect

R = (0.0, 0.0, 10.0, 10.0)


def flat(parts):
    return [v for part in parts for p in part for v in p]


def test_segment_entierement_dedans_inchange():
    assert clip_segment((1, 1), (9, 2), R) == ((1, 1), (9, 2))


def test_segment_coupe_aux_bords():
    assert flat([clip_segment((-5, 5), (15, 5), R)]) == pytest.approx([0, 5, 10, 5])


def test_segment_dehors():
    assert clip_segment((-5, -1), (15, -1), R) is None
    assert clip_segment((11, 0), (11, 10), R) is None


def test_contour_qui_deborde_en_une_polyligne():
    # carré 4..14 : sort par la droite et par le haut ; la partie dedans est une seule polyligne
    sq = [(4, 4), (14, 4), (14, 14), (4, 14)]
    parts = clip_closed_polyline(sq, R)
    assert len(parts) == 1
    assert flat(parts) == pytest.approx([4, 10, 4, 4, 10, 4])


def test_contour_qui_traverse_en_deux_polylignes():
    band = [(-5, 2), (15, 2), (15, 8), (-5, 8)]
    parts = clip_closed_polyline(band, R)
    assert flat(sorted(parts)) == pytest.approx(flat(sorted([[(0, 2), (10, 2)], [(10, 8), (0, 8)]])))


def test_contour_interieur_ferme_conserve():
    tri = [(1, 1), (5, 1), (3, 4)]
    parts = clip_closed_polyline(tri, R)
    assert parts == [[(1, 1), (5, 1), (3, 4), (1, 1)]]


def test_point_dans_polygone():
    sq = [(0, 0), (4, 0), (4, 4), (0, 4)]
    assert point_in_polygon((2, 2), sq) and not point_in_polygon((5, 2), sq)


@pytest.mark.parametrize("poly,expected", [
    ([(2, 2), (3, 2), (3, 3)], True),                        # dedans
    ([(-5, -5), (20, -5), (20, 20), (-5, 20)], True),        # cellule entièrement dans la pièce
    ([(10, 0), (20, 0), (20, 10), (10, 10)], False),         # ne fait que toucher le bord droit
    ([(10 - 1e-3, 0), (20, 0), (20, 10)], True),             # dépasse de 0,001 mm dans la cellule
    ([(11, 1), (12, 1), (12, 2)], False),                    # dehors
])
def test_piece_dans_la_cellule(poly, expected):
    assert polygon_touches_rect(poly, R) is expected
