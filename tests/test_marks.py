"""Repères en T des nœuds marqués : géométrie (brouillon et plan), affichage, PDF."""
import math
import os

import pdfplumber
import pytest

from cut_layout.export import export_mosaic
from cut_layout.importers import Sm2dPattern
from cut_layout.model import Piece
from cut_layout.model.clip import point_in_polygon
from cut_layout.model.marks import BAR_MM, LABEL_DIST_MM, STEM_MM, placed_marks, placed_tee, tee_mark
from cut_layout.model.mosaic import Grid, SheetSettings
from cut_layout.model.placement import REF_CENTROID, Placement, placed_outline, to_plan

TOL = 0.01      # mm, tolérance de relecture PDF validée par Vincent
PT = 72 / 25.4

# Rectangle 40 × 10 mm : M au milieu du bord du bas, A au coin inférieur droit (angle de 90°).
OUTLINE = ((100, 200), (140, 200), (140, 210), (100, 210))
RECT = Piece("R", "b", OUTLINE, nodes={"M": (120, 200), "A": (140, 200), "H": (120, 210)})


@pytest.fixture(scope="module")
def pattern():
    s = os.environ["SM2D_SAMPLES"]
    return Sm2dPattern(os.path.join(s, "patron.sm2d"), os.path.join(s, "mesures.smis"))


def close(p, q, tol=1e-9):
    return math.dist(p, q) < tol


@pytest.mark.parametrize("outline", [OUTLINE, OUTLINE[::-1]], ids=["antihoraire", "horaire"])
def test_t_sur_un_bord_droit(outline):
    piece = Piece("R", "b", outline, nodes=RECT.nodes)
    m = tee_mark(piece, "M")
    assert m.stem == ((120, 200), pytest.approx((120, 205)))           # pointe sur le nœud, vers l'intérieur
    assert sorted(m.bar) == [pytest.approx((118, 205)), pytest.approx((122, 205))]
    assert m.label_at == pytest.approx((120, 208))
    h = tee_mark(piece, "H")                                             # bord du haut : vers le bas
    assert h.stem[1] == pytest.approx((120, 205))


def test_t_sur_un_angle_suit_la_bissectrice():
    m = tee_mark(RECT, "A")
    d = STEM_MM / math.sqrt(2)
    assert m.stem[1] == pytest.approx((140 - d, 200 + d))


def test_noeud_inconnu():
    with pytest.raises(ValueError, match="Z"):
        tee_mark(RECT, "Z")


def test_tous_les_noeuds_du_patron(pattern):
    """Pour chaque nœud de chaque pièce : tige de 5 mm vers l'intérieur, barre de 4 mm perpendiculaire."""
    for name in pattern.piece_names():
        piece = pattern.piece(name)
        for node in piece.nodes:
            m = tee_mark(piece, node)
            (p, q), (b0, b1) = m.stem, m.bar
            assert p == piece.nodes[node]
            assert math.dist(p, q) == pytest.approx(STEM_MM)
            assert math.dist(b0, b1) == pytest.approx(BAR_MM)
            assert close(((b0[0] + b1[0]) / 2, (b0[1] + b1[1]) / 2), q)
            sx, sy, bx, by = q[0] - p[0], q[1] - p[1], b1[0] - b0[0], b1[1] - b0[1]
            assert abs(sx * bx + sy * by) < 1e-9                               # T droit
            assert point_in_polygon(q, list(piece.outline)), (name, node)      # dans la pièce
            assert math.dist(p, m.label_at) == pytest.approx(LABEL_DIST_MM)


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("angle", [0, 90, -37.5])
def test_t_place_suit_la_piece(pattern, angle, mirrored):
    piece = pattern.piece("Demi-dos")
    pl = Placement(REF_CENTROID, 300.0, 400.0, angle, mirrored, marks=("B5", "D1"))
    marks = placed_marks(piece, pl)
    assert [m.node for m in marks] == ["B5", "D1"]
    outline = placed_outline(piece, pl)
    for m in marks:
        raw = tee_mark(piece, m.node)
        assert close(m.stem[0], to_plan(piece, pl, raw.stem[0]))
        assert close(m.bar[1], to_plan(piece, pl, raw.bar[1]))
        assert point_in_polygon(m.stem[1], outline)                    # toujours vers l'intérieur
        assert math.dist(*m.stem) == pytest.approx(STEM_MM)


# --- affichage -----------------------------------------------------------------

def test_affichage_identique_au_modele(pattern):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from cut_layout.ui.scene import CuttingScene
    QApplication.instance() or QApplication([])
    scene = CuttingScene()
    piece = pattern.piece("Demi-dos")
    pl = Placement(REF_CENTROID, 300.0, 400.0, 30.0, True, marks=("B5",))
    item = scene.add_piece(piece, pl)
    m = placed_tee(piece, pl, "B5")
    shown = item.mark_lines_plan()
    assert len(shown) == 2
    for (a, b), (p, q) in zip(shown, (m.stem, m.bar)):
        assert close(a, p) and close(b, q)
    item.set_placement(Placement(REF_CENTROID, 300.0, 400.0, 30.0, True))
    assert item.mark_lines_plan() == [] and item._mark_labels == []


def test_fenetre_proprietes_cocher_un_noeud(pattern):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from cut_layout.ui.piece_properties_dialog import PiecePropertiesDialog
    QApplication.instance() or QApplication([])
    piece = pattern.piece("Demi-dos")
    dlg = PiecePropertiesDialog(piece, Placement("D1", 0.0, 0.0, 0.0, marks=("D4",)))
    items = {dlg.marks.item(i).text(): dlg.marks.item(i) for i in range(dlg.marks.count())}
    assert list(items) == list(piece.nodes)
    assert items["D4"].checkState() == Qt.Checked and items["B5"].checkState() == Qt.Unchecked
    items["B5"].setCheckState(Qt.Checked)
    assert dlg.placement().marks == ("B5", "D4")                   # ordre des nœuds de la pièce
    items["D4"].setCheckState(Qt.Unchecked)
    assert dlg.placement().marks == ("B5",)


# --- PDF -------------------------------------------------------------------------

def test_t_imprime_a_la_bonne_position(tmp_path):
    """Pièce placée telle quelle : M (120, 200) du plan → (130, 210) sur la feuille L1-C1 (marge 10 mm)."""
    pl = Placement("M", 120.0, 200.0, 0.0, marks=("M",))
    grid = Grid(SheetSettings(), rows=1, cols=1)
    path = tmp_path / "t.pdf"
    export_mosaic(path, grid, [("R", placed_outline(RECT, pl))], overview=False, marks=placed_marks(RECT, pl))
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        H = float(page.height)
        segs = [[(float(x) / PT, (H - float(y)) / PT) for x, y in o["pts"]] for o in page.lines]
        words = page.extract_words()
    def has(p, q):
        return any((math.dist(a, p) < TOL and math.dist(b, q) < TOL) or (math.dist(a, q) < TOL and math.dist(b, p) < TOL)
                   for a, b in segs)
    assert has((130, 210), (130, 215))                                   # tige
    assert has((128, 215), (132, 215))                                   # barre
    word = next(w for w in words if w["text"] == "M")
    cx = (float(word["x0"]) + float(word["x1"])) / 2 / PT
    assert cx == pytest.approx(130.0, abs=0.05)                           # nom centré sur la tige


def test_t_a_cheval_sur_deux_feuilles(tmp_path):
    """Nœud sur la frontière C1|C2 (x = 190) : le T est imprimé sur les deux feuilles, dans la bande."""
    piece = Piece("R", "b", ((150, 20), (230, 20), (230, 60), (150, 60)), nodes={"F": (190, 20)})
    pl = Placement("F", 190.0, 20.0, 0.0, marks=("F",))
    grid = Grid(SheetSettings(), rows=1, cols=2)
    path = tmp_path / "t2.pdf"
    export_mosaic(path, grid, [("R", placed_outline(piece, pl))], overview=False, marks=placed_marks(piece, pl))
    with pdfplumber.open(path) as pdf:
        for page, x in zip(pdf.pages, (200.0, 10.0)):
            H = float(page.height)
            segs = [[(float(a) / PT, (H - float(b)) / PT) for a, b in o["pts"]] for o in page.lines]
            assert any(math.dist(s[0], (x, 30.0)) < TOL and math.dist(s[-1], (x, 35.0)) < TOL for s in segs)
