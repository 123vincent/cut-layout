"""Scène et fenêtre de propriétés Qt : unité = mm, axe y du plan vers le haut,
affichage identique au modèle de placement."""
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cut_layout.importers import Sm2dPattern  # noqa: E402
from cut_layout.model.mosaic import Grid, SheetSettings, fit_grid  # noqa: E402
from cut_layout.model.placement import (REF_CENTROID, Placement, placed_outline,  # noqa: E402
                                        placement_at_corner)
from cut_layout.ui.piece_properties_dialog import PiecePropertiesDialog  # noqa: E402
from cut_layout.ui.scene import CuttingScene, overlap_area, to_plan, to_scene  # noqa: E402
from cut_layout.ui.theme import SCENE_COLORS  # noqa: E402

SAMPLES = os.environ["SM2D_SAMPLES"]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def scene(app):
    return CuttingScene()


@pytest.fixture(scope="module")
def pattern():
    return Sm2dPattern(os.path.join(SAMPLES, "patron.sm2d"), os.path.join(SAMPLES, "mesures.smis"))


def test_inversion_d_axe_aller_retour():
    assert to_scene(12.5, 30.0).y() == -30.0
    assert to_plan(to_scene(12.5, 30.0)) == (12.5, 30.0)


@pytest.mark.parametrize("name", ["Demi-dos", "Demi-devant", "Manche longue", "Manche courte"])
def test_piece_affichee_en_mm(scene, pattern, name):
    p = pattern.piece(name)
    item = scene.add_piece(p, placement_at_corner(p, 300.0, 10.0))
    r = item.mapRectToScene(item.path().boundingRect())       # rotation nulle : boîte exacte
    assert (r.left(), -r.bottom()) == pytest.approx((300.0, 10.0), abs=1e-9)
    assert (r.width(), r.height()) == pytest.approx((p.width, p.height), abs=1e-9)


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("angle", [0, 90, -90, 180, 37.5])
@pytest.mark.parametrize("ref", [REF_CENTROID, "D7"])
def test_affichage_identique_au_modele(scene, pattern, ref, angle, mirrored):
    # chaque point du contour affiché coïncide avec le contour placé calculé sans Qt
    p = pattern.piece("Demi-devant")
    pl = Placement(ref, 300.0, 10.0, angle, mirrored)
    item = scene.add_piece(p, pl)
    model = placed_outline(p, pl)
    for i in range(0, len(p.outline), 25):
        shown = to_plan(item.mapToScene(to_scene(*p.outline[i])))
        assert math.dist(shown, model[i]) < 1e-9


def test_rotation_positive_antihoraire_a_l_ecran(scene, pattern):
    # D7 est sur l'ourlet ; à +90° autour du barycentre, un point situé sous le barycentre passe à sa droite
    p = pattern.piece("Demi-devant")
    item = scene.add_piece(p, Placement(REF_CENTROID, 500.0, 500.0, 90.0))
    gx, gy = 500.0, 500.0
    d7 = to_plan(item.mapToScene(to_scene(*p.nodes["D7"])))
    cx, cy = p.centroid
    assert p.nodes["D7"][1] < cy                 # D7 sous le barycentre dans le brouillon
    assert d7[0] > gx and abs(d7[1] - gy - (p.nodes["D7"][0] - cx)) < 1e-9


def test_retirer_une_piece(app, pattern):
    sc = CuttingScene()
    a = sc.add_piece(pattern.piece("Demi-dos"), Placement())
    b = sc.add_piece(pattern.piece("Demi-devant"), Placement())
    sc.remove_pieces([a])
    assert sc.pieces() == [b] and a.scene() is None


def test_grille_affichee_egale_au_modele(app):
    from cut_layout.model.mosaic import Grid, SheetSettings
    sc = CuttingScene()
    g = Grid(SheetSettings(), rows=2, cols=3)
    sc.set_grid(g)
    lines = set(sc.grid_item.lines_plan())
    # verticales x = 0, 190, 380, 570 sur y ∈ [0 ; 554] ; horizontales y = 0, 277, 554 sur x ∈ [0 ; 570]
    expected = {(x, 0.0, x, 554.0) for x in (0.0, 190.0, 380.0, 570.0)} | \
               {(0.0, y, 570.0, y) for y in (0.0, 277.0, 554.0)}
    assert lines == expected
    # chaque côté de chaque cadre de coupe du modèle est porté par une ligne affichée
    for r, c in g.cells():
        x0, y0, x1, y1 = g.cell_rect(r, c)
        assert any(l[0] == l[2] == x0 and l[1] <= y0 and y1 <= l[3] for l in lines)
        assert any(l[1] == l[3] == y1 and l[0] <= x0 and x1 <= l[2] for l in lines)


def test_changement_de_theme(app, pattern):
    from cut_layout.model.mosaic import Grid, SheetSettings
    from cut_layout.ui.theme import SCENE_COLORS
    sc = CuttingScene(theme="light")
    it = sc.add_piece(pattern.piece("Demi-dos"), Placement())
    sc.set_grid(Grid(SheetSettings(), 1, 1))
    sc.set_theme("dark")
    assert sc.backgroundBrush().color().name() == SCENE_COLORS["dark"].background
    assert it.colors is SCENE_COLORS["dark"] and sc.grid_item is not None


# --- fenêtre de propriétés --------------------------------------------------

def test_dialogue_changer_de_reference_ne_deplace_pas(app, pattern):
    p = pattern.piece("Demi-devant")
    pl = Placement("D7", 300.0, 10.0, 90.0)
    dlg = PiecePropertiesDialog(p, pl)
    dlg.ref.setCurrentIndex(dlg.ref.findData("C5"))
    new = dlg.placement()
    assert new.ref == "C5" and new.angle == 90.0
    assert max(math.dist(a, b) for a, b in zip(placed_outline(p, pl), placed_outline(p, new))) < 1e-9


def test_dialogue_saisie_en_cm_stockee_en_mm(app, pattern):
    p = pattern.piece("Demi-devant")
    dlg = PiecePropertiesDialog(p, Placement("D7", 0.0, 0.0, 0.0))
    dlg.x.setValue(30.0)                         # unité par défaut : cm
    dlg.y.setValue(1.0)
    assert (dlg.placement().x, dlg.placement().y) == (300.0, 10.0)
    dlg.unit.setCurrentText("mm")
    assert dlg.x.value() == 300.0
    dlg.y.setValue(12.5)
    assert dlg.placement().y == 12.5


def test_dialogue_pas_d_arrondi_silencieux(app, pattern):
    # une position non représentable à l'affichage (0,01 mm) n'est pas modifiée si on ne touche pas au champ
    p = pattern.piece("Demi-devant")
    pl = Placement(REF_CENTROID, 123.456789, 9.87654321, 12.5)
    dlg = PiecePropertiesDialog(p, pl)
    dlg.unit.setCurrentText("mm")
    dlg.unit.setCurrentText("cm")
    assert dlg.placement() == pl


def test_dialogue_increments_de_rotation(app, pattern):
    p = pattern.piece("Demi-devant")
    dlg = PiecePropertiesDialog(p, Placement("D7", 0.0, 0.0, 0.0))
    dlg._rotate_by(-90)
    assert dlg.placement().angle == -90.0
    dlg._rotate_by(-90)
    dlg._rotate_by(-90)
    assert dlg.placement().angle == 90.0         # -270 normalisé


def test_dialogue_symetrie(app, pattern):
    p = pattern.piece("Demi-devant")
    pl = Placement("D7", 300.0, 10.0, 30.0)
    dlg = PiecePropertiesDialog(p, pl)
    assert dlg.mirror.isEnabled() and not dlg.mirror.isChecked()
    dlg.mirror.setChecked(True)
    assert dlg.placement() == Placement("D7", 300.0, 10.0, -30.0, mirrored=True)
    assert dlg.angle.value() == -30.0                      # angle affiché mis à jour
    dlg._rotate_by(90)
    assert dlg.placement().angle == 60.0 and dlg.placement().mirrored
    dlg.mirror.setChecked(False)
    assert dlg.placement() == Placement("D7", 300.0, 10.0, -60.0)


def test_dialogue_symetrie_interdite(app, pattern):
    from dataclasses import replace
    p = replace(pattern.piece("Demi-devant"), forbid_flipping=True)
    dlg = PiecePropertiesDialog(p, Placement("D7", 300.0, 10.0, 0.0))
    assert not dlg.mirror.isEnabled() and "forbidden" in dlg.mirror.toolTip()
    # pièce déjà retournée (plan enregistré avant que le patron l'interdise) : on peut la remettre à l'endroit
    dlg = PiecePropertiesDialog(p, Placement("D7", 300.0, 10.0, 0.0, mirrored=True))
    assert dlg.mirror.isEnabled()


def test_description_piece_retournee(scene, pattern):
    item = scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 300.0, 400.0, 0.0, mirrored=True))
    assert "mirrored" in item.description()
    scene.remove_pieces([item])


@pytest.mark.parametrize("language,expected_messages", [("fr", 1), ("auto", 0)])
def test_rechargement_signale_un_changement_de_langue(app, tmp_path, monkeypatch, language, expected_messages):
    from cut_layout.config import load_config, render
    from cut_layout.ui import main_window
    shown = []
    monkeypatch.setattr(main_window.QMessageBox, "information", lambda *args: shown.append(args[2]))
    path = tmp_path / "config.ini"
    path.write_text(render(), encoding="utf-8")
    w = main_window.MainWindow(load_config(path), path)
    path.write_text(render({"language": language}), encoding="utf-8")
    w.reload_config()
    assert w.config.language == language and w.language_actions[language].isChecked()
    assert shown == ["The language will change at the next start."] * expected_messages


def _window_with_piece(app, tmp_path, pattern):
    from cut_layout.config import load_config
    from cut_layout.ui.main_window import MainWindow
    w = MainWindow(load_config(tmp_path / "config.ini"), tmp_path / "config.ini")
    piece = pattern.piece("Demi-dos")
    item = w.scene.add_piece(piece, Placement(REF_CENTROID, 100.0, 300.0, 0.0))
    w.resize(800, 600)
    w.show()
    w.view.resetTransform()
    w.view.scale(1.0, 1.0)              # 1 pixel = 1 mm
    w.view.centerOn(to_scene(100.0, 300.0))
    app.processEvents()
    return w, item


def _drag(w, start, end):
    from PySide6.QtTest import QTest
    vp = w.view.viewport()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(vp, end)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, end)


def test_glisser_une_piece_la_deplace(app, tmp_path, pattern):
    w, item = _window_with_piece(app, tmp_path, pattern)
    start = w.view.mapFromScene(to_scene(100.0, 300.0))
    _drag(w, start, start + QPoint(50, -30))      # écran : y vers le bas → plan : y vers le haut
    assert item.isSelected()
    assert (item.placement.x, item.placement.y) == pytest.approx((150.0, 330.0), abs=0.05)
    assert item.placement.x == round(item.placement.x, 1)    # arrondi à 0,1 mm
    assert w.scene.grid_item.grid == fit_grid(w.config.sheet, [item.plan_bbox()])


def test_simple_clic_ne_deplace_pas(app, tmp_path, pattern):
    w, item = _window_with_piece(app, tmp_path, pattern)
    start = w.view.mapFromScene(to_scene(100.0, 300.0))
    _drag(w, start, start + QPoint(1, 1))
    assert item.isSelected() and (item.placement.x, item.placement.y) == (100.0, 300.0)


def test_glisser_dans_le_vide_ne_deplace_pas_les_pieces(app, tmp_path, pattern):
    w, item = _window_with_piece(app, tmp_path, pattern)
    empty = w.view.mapFromScene(to_scene(100.0 - 250.0, 300.0))
    assert w.view._piece_at_point(empty) is None
    _drag(w, empty, empty + QPoint(50, 50))
    assert (item.placement.x, item.placement.y) == (100.0, 300.0)


def test_ajouter_des_pieces_dans_le_menu_piece(app, tmp_path):
    from cut_layout.config import load_config
    from cut_layout.ui.main_window import MainWindow
    w = MainWindow(load_config(tmp_path / "config.ini"), tmp_path / "config.ini")
    menus = {m.text(): [a.text() for a in m.menu().actions()] for m in w.menuBar().actions()}
    assert "&Add pieces…" in menus["&Piece"] and "&Add pieces…" not in menus["&File"]


@pytest.fixture
def collision_scene(app, pattern):
    sc = CuttingScene()
    dos = pattern.piece("Demi-dos")
    a = sc.add_piece(dos, placement_at_corner(dos, 0.0, 0.0))
    manche = pattern.piece("Manche courte")
    b = sc.add_piece(manche, placement_at_corner(manche, a.plan_bbox()[2] + 20.0, 0.0))
    return sc, a, b


def test_pieces_separees_sans_collision(collision_scene):
    sc, a, b = collision_scene
    assert a.collides_with == [] and b.collides_with == []
    assert a.pen().color().name() == SCENE_COLORS["light"].piece


def test_pieces_qui_se_chevauchent_en_couleur_de_collision(collision_scene):
    sc, a, b = collision_scene
    # boîtes englobantes qui se recouvrent de 10 mm, formes séparées : pas de collision
    b.set_placement(placement_at_corner(b.piece, a.plan_bbox()[2] - 10.0, 0.0))
    sc.update_collisions()
    assert overlap_area(a.plan_path(), b.plan_path()) == 0.0 and b.collides_with == []
    # manche posée sur le dos, dans le plan (x, y > 0)
    b.set_placement(placement_at_corner(b.piece, 50.0, 100.0))
    sc.update_collisions()
    assert a.collides_with == ["Manche courte"] and b.collides_with == ["Demi-dos"]
    assert b.pen().color().name() == SCENE_COLORS["light"].collision
    assert "OVERLAPS Demi-dos" in b.description()


def test_contact_bord_a_bord_n_est_pas_une_collision(app):
    from cut_layout.model.piece import Piece
    sc = CuttingScene()
    sq = Piece(name="c1", outline=((0, 0), (100, 0), (100, 100), (0, 100)), nodes={}, block="b")
    sq2 = Piece(name="c2", outline=sq.outline, nodes={}, block="b")
    sc.add_piece(sq, placement_at_corner(sq, 0.0, 0.0))
    b = sc.add_piece(sq2, placement_at_corner(sq2, 100.0, 0.0))     # bords communs, sans recouvrement
    assert b.collides_with == []
    b.set_placement(placement_at_corner(sq2, 99.0, 0.0))            # 1 × 100 mm = 100 mm² de recouvrement
    sc.update_collisions()
    assert b.collides_with == ["c1"]


def test_overlap_area_exacte(app):
    from PySide6.QtGui import QPainterPath
    from cut_layout.ui.scene import overlap_area
    p, q = QPainterPath(), QPainterPath()
    p.addRect(0, 0, 100, 50)
    q.addRect(60, 20, 100, 100)
    assert overlap_area(p, q) == pytest.approx(40 * 30, abs=1e-6)


def test_lettres_des_coins_affichees_sur_la_grille(scene):
    grid = Grid(SheetSettings(), rows=3, cols=2)
    scene.set_grid(grid)
    labels = scene.grid_item.corner_labels
    w, h = grid.settings.cell_size
    assert set(labels) == set("ABCDEFGH")
    for (i, j), letter in grid.corner_letters().items():
        item = labels[letter]
        assert item.data(0) == (j * w, i * h)
        assert to_plan(item.sceneBoundingRect().center()) == pytest.approx((j * w, i * h), abs=1e-6)


def test_enregistrer_puis_rouvrir_un_plan(app, tmp_path, monkeypatch):
    import shutil
    from cut_layout.config import load_config
    from cut_layout.ui import main_window
    folder = tmp_path / "p"
    folder.mkdir()
    sm2d = shutil.copy(os.path.join(SAMPLES, "patron.sm2d"), folder / "patron.sm2d")
    smis = shutil.copy(os.path.join(SAMPLES, "mesures.smis"), folder / "mesures.smis")
    messages = []
    for kind in ("warning", "critical", "information"):
        monkeypatch.setattr(main_window.QMessageBox, kind, lambda *a, k=kind: messages.append((k, a[2])))
    monkeypatch.setattr(main_window.QMessageBox, "question", lambda *a: main_window.QMessageBox.Yes)

    w = main_window.MainWindow(load_config(tmp_path / "config.ini"), tmp_path / "config.ini")
    pattern = Sm2dPattern(sm2d, smis)
    w._set_pattern(pattern, None)
    placements = {"Demi-dos": Placement(REF_CENTROID, 150.0, 400.0, 90.0),
                  "Manche courte": Placement("M4", 600.0, 50.0, 0.0)}
    for name, pl in placements.items():
        w.scene.add_piece(pattern.piece(name), pl)
    cutl = folder / "plan.cutl"
    monkeypatch.setattr(main_window.QFileDialog, "getSaveFileName", lambda *a: (str(cutl), ""))
    w.save_project()                       # pas encore de fichier : « enregistrer sous »
    assert cutl.is_file() and w.project_path == cutl and cutl.name in w.windowTitle()

    w2 = main_window.MainWindow(load_config(tmp_path / "config.ini"), tmp_path / "config.ini")
    w2.open_project(str(cutl))
    assert messages == []
    assert {it.piece.name: it.placement for it in w2.scene.pieces()} == placements
    assert w2.save_action.isEnabled() and w2.add_action.isEnabled()

    # pièce disparue du patron : signalée, les autres sont placées
    data = cutl.read_text(encoding="utf-8").replace('"Manche courte"', '"Col"')
    cutl.write_text(data, encoding="utf-8")
    w2.open_project(str(cutl))
    assert [it.piece.name for it in w2.scene.pieces()] == ["Demi-dos"]
    assert messages and "Col" in messages[-1][1]


@pytest.fixture
def window_with_pattern(app, tmp_path, monkeypatch):
    import shutil
    from cut_layout.config import load_config
    from cut_layout.ui import main_window
    folder = tmp_path / "p"
    folder.mkdir()
    sm2d = shutil.copy(os.path.join(SAMPLES, "patron.sm2d"), folder / "patron.sm2d")
    smis = shutil.copy(os.path.join(SAMPLES, "mesures.smis"), folder / "mesures.smis")
    w = main_window.MainWindow(load_config(tmp_path / "config.ini"), tmp_path / "config.ini")
    pattern = Sm2dPattern(sm2d, smis)
    w._set_pattern(pattern, None)
    w._saved_state = w._state()
    monkeypatch.setattr(main_window.QFileDialog, "getSaveFileName", lambda *a: (str(folder / "plan.cutl"), ""))
    asked = []

    def answer(value):
        monkeypatch.setattr(main_window.QMessageBox, "question", lambda *a: asked.append(a[2]) or value)
    return w, pattern, main_window.QMessageBox, answer, asked


def test_fermeture_sans_modification_sans_question(window_with_pattern):
    w, _pattern, box, answer, asked = window_with_pattern
    answer(box.Cancel)
    assert w.close() and asked == []


@pytest.mark.parametrize("choice,closes,saved", [("Save", True, True), ("Discard", True, False),
                                                 ("Cancel", False, False)])
def test_fermeture_avec_modifications(window_with_pattern, tmp_path, choice, closes, saved):
    w, pattern, box, answer, asked = window_with_pattern
    w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    assert w.is_modified()
    answer(getattr(box, choice))
    assert w.close() is closes
    assert len(asked) == 1 and "unsaved changes" in asked[0]
    assert (tmp_path / "p" / "plan.cutl").is_file() is saved


def test_deplacer_apres_enregistrement_rend_le_plan_modifie(window_with_pattern):
    w, pattern, *_ = window_with_pattern
    item = w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    w.save_project()
    assert not w.is_modified()
    item.set_placement(Placement(REF_CENTROID, 150.1, 400.0, 0.0))
    assert w.is_modified()
    item.set_placement(Placement(REF_CENTROID, 150.0, 400.0, 0.0))     # retour à l'état enregistré
    assert not w.is_modified()


def test_enregistrement_annule_la_fenetre_reste_ouverte(window_with_pattern, monkeypatch):
    w, pattern, box, answer, _asked = window_with_pattern
    from cut_layout.ui import main_window
    w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    monkeypatch.setattr(main_window.QFileDialog, "getSaveFileName", lambda *a: ("", ""))
    answer(box.Save)
    assert w.close() is False


# -- annuler / rétablir -----------------------------------------------------------

def test_menu_edition_annuler_retablir(window_with_pattern):
    from PySide6.QtGui import QKeySequence
    w, *_ = window_with_pattern
    menus = {m.text(): m.menu().actions() for m in w.menuBar().actions()}
    assert [a.text() for a in w.menuBar().actions()][:3] == ["&File", "&Edit", "&Piece"]
    assert menus["&Edit"] == [w.undo_action, w.redo_action]
    assert QKeySequence("Ctrl+Z") in w.undo_action.shortcuts()
    assert {QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")} <= set(w.redo_action.shortcuts())
    assert not w.undo_action.isEnabled() and not w.redo_action.isEnabled()


def test_annuler_un_glisser(app, tmp_path, pattern):
    w, item = _window_with_piece(app, tmp_path, pattern)
    start = w.view.mapFromScene(to_scene(100.0, 300.0))
    _drag(w, start, start + QPoint(50, -30))
    moved = item.placement
    assert w.undo_stack.count() == 1 and w.undo_action.text() == "&Undo Move Demi-dos"
    w.undo_action.trigger()
    assert item.placement == Placement(REF_CENTROID, 100.0, 300.0, 0.0)
    assert w.scene.grid_item.grid == fit_grid(w.config.sheet, [item.plan_bbox()])
    w.redo_action.trigger()
    assert item.placement == moved


def test_un_simple_clic_n_entre_pas_dans_l_historique(app, tmp_path, pattern):
    w, item = _window_with_piece(app, tmp_path, pattern)
    start = w.view.mapFromScene(to_scene(100.0, 300.0))
    _drag(w, start, start + QPoint(1, 1))
    assert w.undo_stack.count() == 0


def test_annuler_une_modification_de_proprietes(window_with_pattern, monkeypatch):
    from cut_layout.ui import main_window
    w, pattern, *_ = window_with_pattern
    item = w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    new = Placement("B5", 300.0, 10.0, 90.0)
    applied = []

    class FakeDialog:
        def __init__(self, *a):
            self.applied = self

        def connect(self, slot):
            applied.append(slot)

        def exec(self):
            applied[0](new)
            applied[0](new)          # « Appliquer » puis « OK » sans changement : une seule entrée
    monkeypatch.setattr(main_window, "PiecePropertiesDialog", FakeDialog)
    w.edit_piece(item)
    assert item.placement == new and w.undo_stack.count() == 1
    assert w.undo_stack.undoText() == "Change the properties of Demi-dos"
    w.undo_stack.undo()
    assert item.placement == Placement(REF_CENTROID, 150.0, 400.0, 0.0)


def test_annuler_un_retrait_remet_la_meme_piece(window_with_pattern):
    w, pattern, *_ = window_with_pattern
    a = w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    b = w.scene.add_piece(pattern.piece("Demi-devant"), Placement(REF_CENTROID, 600.0, 400.0, 0.0))
    a.setSelected(True)
    w.remove_selected_pieces()
    assert w.scene.pieces() == [b] and w.undo_stack.undoText() == "Remove Demi-dos"
    w.undo_stack.undo()
    assert set(w.scene.pieces()) == {a, b} and a.isSelected() and a.placement.x == 150.0
    w.undo_stack.redo()
    assert w.scene.pieces() == [b]


def test_retirer_sans_selection_n_entre_pas_dans_l_historique(window_with_pattern):
    w, *_ = window_with_pattern
    w.remove_selected_pieces()
    assert w.undo_stack.count() == 0


def test_annuler_un_ajout_de_pieces(window_with_pattern, monkeypatch):
    from cut_layout.ui import main_window
    w, *_ = window_with_pattern
    monkeypatch.setattr(main_window.PieceSelectionDialog, "exec", lambda self: main_window.PieceSelectionDialog.Accepted)
    monkeypatch.setattr(main_window.PieceSelectionDialog, "selected_names", lambda self: ["Demi-dos", "Demi-devant"])
    w.choose_pieces()
    assert sorted(it.piece.name for it in w.scene.pieces()) == ["Demi-devant", "Demi-dos"]
    assert w.undo_stack.count() == 1 and w.undo_stack.undoText() == "Add Demi-dos, Demi-devant"
    w.undo_stack.undo()
    assert w.scene.pieces() == [] and not w.is_modified()
    w.undo_stack.redo()
    assert len(w.scene.pieces()) == 2


def test_annuler_jusqu_a_l_etat_enregistre(window_with_pattern):
    w, pattern, *_ = window_with_pattern
    item = w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    w.save_project()
    w._set_placement(item, item.placement, Placement(REF_CENTROID, 160.0, 400.0, 0.0), "Move")
    assert w.is_modified()
    w.undo_stack.undo()
    assert not w.is_modified()


def test_piece_remise_apres_changement_de_theme(window_with_pattern):
    w, pattern, *_ = window_with_pattern
    item = w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    item.setSelected(True)
    w.remove_selected_pieces()
    w.scene.set_theme("dark")
    w.undo_stack.undo()
    assert item.colors == SCENE_COLORS["dark"]


def test_ouvrir_un_plan_vide_l_historique(window_with_pattern):
    w, pattern, box, answer, _asked = window_with_pattern
    item = w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    w._set_placement(item, item.placement, Placement(REF_CENTROID, 160.0, 400.0, 0.0), "Move")
    w.save_project()
    answer(box.Yes)                      # « retirer les pièces déjà importées ? »
    w.open_project(str(w.project_path))
    assert w.undo_stack.count() == 0 and not w.undo_action.isEnabled()


def test_ouvrir_un_plan_noeud_marque_disparu(window_with_pattern, monkeypatch):
    from cut_layout.ui import main_window
    w, pattern, box, answer, _asked = window_with_pattern
    w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0, marks=("B5", "D4")))
    w.save_project()
    path = w.project_path
    path.write_text(path.read_text(encoding="utf-8").replace('"D4"', '"ZZ"'), encoding="utf-8")
    warnings = []
    monkeypatch.setattr(main_window.QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    answer(box.Yes)
    w.open_project(str(path))
    (item,) = w.scene.pieces()
    assert item.placement.marks == ("B5",)
    assert len(warnings) == 1 and "ZZ" in warnings[0] and "Marks removed" in warnings[0]


# -- mise en page ---------------------------------------------------------------

def test_fenetre_mise_en_page(app):
    from PySide6.QtWidgets import QDialogButtonBox
    from cut_layout.ui.page_setup_dialog import PageSetupDialog
    dlg = PageSetupDialog(SheetSettings(), [(0.0, 0.0, 300.0, 100.0)])
    ok = dlg.buttons.button(QDialogButtonBox.Ok)
    assert not dlg.width.isEnabled() and dlg.width.value() == 210.0
    assert "2 sheets" in dlg.info.text()
    dlg.orientation.setCurrentIndex(dlg.orientation.findData("landscape"))
    assert dlg.sheet() == SheetSettings("A4", "landscape") and "1 × 2 = 2 sheets" in dlg.info.text()
    dlg.format.setCurrentIndex(dlg.format.findData("custom"))
    assert dlg.width.isEnabled()
    dlg.width.setValue(700.0)
    dlg.height.setValue(500.0)
    assert dlg.sheet() == SheetSettings("custom", "landscape", 10.0, 5.0, 700.0, 500.0)
    assert dlg.sheet().sheet_size == (700.0, 500.0) and ok.isEnabled()
    dlg.assembly.setValue(4.0)                     # marge d'assemblage < marge d'impression (5 mm)
    assert dlg.sheet() is None and not ok.isEnabled() and "print margin" in dlg.info.text()


def _accept_page_setup(monkeypatch, sheet, save_default=False):
    from cut_layout.ui import main_window

    class FakeDialog:
        Accepted = 1

        def __init__(self, *a):
            self.save_default = type("C", (), {"isChecked": lambda self: save_default})()

        def exec(self):
            return 1

        def sheet(self):
            return sheet
    monkeypatch.setattr(main_window, "PageSetupDialog", FakeDialog)


def test_mise_en_page_du_plan_annulable_et_enregistree(window_with_pattern, monkeypatch, tmp_path):
    w, pattern, box, answer, _asked = window_with_pattern
    w.scene.add_piece(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 150.0, 400.0, 0.0))
    w.save_project()
    a3 = SheetSettings("A3", "landscape", 12.0, 5.0)
    _accept_page_setup(monkeypatch, a3)
    w.page_setup()
    assert w.sheet == a3 and w.scene.grid_item.grid.settings == a3 and w.is_modified()
    assert w.undo_stack.undoText() == "Page setup" and "A3 landscape" in w.mosaic_label.text()
    w.undo_stack.undo()
    assert w.sheet == SheetSettings() and not w.is_modified()
    w.undo_stack.redo()
    w.save_project()
    w.sheet = SheetSettings()                              # rouvrir : la mise en page vient du .cutl
    answer(box.Discard)                                    # modification (mise en page) abandonnée
    w.open_project(str(w.project_path))
    assert w.sheet == a3
    assert "format = A4" in (tmp_path / "config.ini").read_text(encoding="utf-8")   # préférences inchangées


def test_mise_en_page_par_defaut_enregistree(window_with_pattern, monkeypatch, tmp_path):
    from cut_layout.config import load_config
    w, *_ = window_with_pattern
    custom = SheetSettings("custom", "portrait", 15.0, 5.0, 594.0, 841.0)
    _accept_page_setup(monkeypatch, custom, save_default=True)
    w.page_setup()
    assert load_config(tmp_path / "config.ini").sheet == custom and w.config.sheet == custom


def test_preferences_rechargees_ne_changent_pas_la_mise_en_page_du_plan(window_with_pattern, tmp_path):
    from cut_layout.config import render
    w, *_ = window_with_pattern
    w.sheet = SheetSettings("A3", "landscape", 12.0, 5.0)
    (tmp_path / "config.ini").write_text(render({"format": "A4", "print_margin_mm": "4"}), encoding="utf-8")
    w.reload_config()
    assert w.sheet == SheetSettings("A3", "landscape", 12.0, 4.0)       # seule la marge d'impression change


def test_menu_mise_en_page(window_with_pattern):
    w, *_ = window_with_pattern
    menus = {m.text(): [a.text() for a in m.menu().actions()] for m in w.menuBar().actions()}
    assert [a.text() for a in w.menuBar().actions()] == ["&File", "&Edit", "&Piece", "Page &setup", "&View", "&Help"]
    assert menus["Page &setup"][0] == "&Page setup…"
    assert not any("test page" in t for t in menus["&File"])
    assert sum("test page" in t for t in menus["Page &setup"]) == 2


# -- listes à cocher : hauteur de ligne fixe ------------------------------------

def test_listes_a_cocher_hauteur_de_ligne_fixe(app, pattern):
    """Sans hauteur fixée, les lignes sont serrées puis s'agrandissent au premier cochage (padding du thème)."""
    from cut_layout.ui.check_list import INDICATOR_PX, ROW_PADDING_PX, check_row_size
    from cut_layout.ui.piece_selection_dialog import PieceSelectionDialog
    pieces = [pattern.piece(n) for n in pattern.piece_names()]
    dialogs = [PieceSelectionDialog(pieces, {"Demi-dos"}),
               PiecePropertiesDialog(pattern.piece("Demi-dos"), Placement(REF_CENTROID, 0.0, 0.0, 0.0))]
    for lst in (dialogs[0].list, dialogs[1].marks):
        expected = check_row_size(lst).height()
        assert expected >= INDICATOR_PX + 2 * ROW_PADDING_PX
        heights = {lst.item(i).sizeHint().height() for i in range(lst.count())}
        assert heights == {expected}
        lst.item(1).setCheckState(Qt.Checked)                 # cocher ne change pas la hauteur
        assert lst.item(1).sizeHint().height() == expected


# -- version : « À propos » et propriétés du PDF ---------------------------------------

def test_a_propos_affiche_la_version(app, tmp_path):
    from cut_layout.config import Config
    from cut_layout.ui.main_window import MainWindow
    from cut_layout import __version__
    w = MainWindow(Config(), tmp_path / "config.ini")
    text = w.about_text()
    assert f"CutLayout {__version__}" in text and str(tmp_path / "config.ini") in text
    menus = [a.text() for a in w.menuBar().actions()]
    assert menus[-1] == "&Help"


def test_version_dans_les_proprietes_du_pdf(tmp_path):
    import pdfplumber
    from cut_layout import __version__
    from cut_layout.export import export_test_page
    from cut_layout.model.mosaic import SheetSettings
    path = export_test_page(tmp_path / "essai.pdf", SheetSettings())
    with pdfplumber.open(path) as pdf:
        assert pdf.metadata["Creator"] == f"CutLayout {__version__}"
