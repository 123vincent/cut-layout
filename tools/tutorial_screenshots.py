"""Génère les illustrations du tutoriel (docs/tutoriel/img/) à partir du patron de démonstration.

    .venv\\Scripts\\python tools\\tutorial_screenshots.py [--lang fr|en]

Patron et mesures FICTIFS (docs/tutoriel/demo/) : aucune donnée personnelle dans les images.
Les préférences de l'utilisateur ne sont ni lues ni modifiées (configuration temporaire).
À relancer après une modification de l'interface.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "tutoriel" / "demo"
SM2D, SMIS = DEMO / "jupe_demo.sm2d", DEMO / "mesures_demo.smis"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="fr", choices=("fr", "en"))
    args = ap.parse_args()
    out = ROOT / "docs" / "tutoriel" / ("img" if args.lang == "fr" else f"img_{args.lang}")
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtWidgets import QApplication

    from cut_layout.app import _install_qt_translation
    from cut_layout.i18n import set_language

    app = QApplication(sys.argv[:1])
    set_language(args.lang)
    _install_qt_translation(app, args.lang)

    import pypdfium2 as pdfium

    from cut_layout.config import Config
    from cut_layout.export import export_mosaic, export_test_page
    from cut_layout.importers import Sm2dPattern
    from cut_layout.model.marks import placed_marks
    from cut_layout.model.mosaic import fit_grid
    from cut_layout.model.placement import placed_bbox, placed_outline, placement_at_corner, toggle_mirror
    from cut_layout.ui.main_window import MainWindow
    from cut_layout.ui.page_setup_dialog import PageSetupDialog
    from cut_layout.ui.piece_properties_dialog import PiecePropertiesDialog
    from cut_layout.ui.piece_selection_dialog import PieceSelectionDialog
    from cut_layout.ui.scene import PieceItem
    from cut_layout.ui.theme import apply_app_theme

    tmp = Path(tempfile.mkdtemp())
    config = Config()
    apply_app_theme(app, config.theme)
    pattern = Sm2dPattern(SM2D, SMIS)
    pieces = {n: pattern.piece(n) for n in pattern.piece_names()}

    def settle():
        for _ in range(5):
            app.processEvents()

    def save(widget, name):
        settle()
        widget.grab().save(str(out / name))
        print(out / name)

    def at_corner(piece, x, y, angle=0.0, mirrored=False, marks=()):
        """Placement dont la boîte englobante (après rotation et symétrie) commence en (x, y)."""
        pl = placement_at_corner(piece, x, y, angle)
        if mirrored:
            pl = toggle_mirror(pl)
        x0, y0, _x1, _y1 = placed_bbox(piece, pl)
        return replace(pl, x=pl.x + x - x0, y=pl.y + y - y0, marks=tuple(marks))

    # --- fenêtre principale avec le plan de démonstration -------------------------------------
    w = MainWindow(config, tmp / "config.ini")
    w.resize(1280, 820)
    w._set_pattern(pattern, None)
    gap = 20.0          # écart par défaut à l'import (IMPORT_GAP_MM)
    layout = [("Devant", 0.0, 0.0, 0.0, False, ("A3",)),
              ("Dos", 250.0 + gap, 0.0, 0.0, True, ("B3",)),
              ("Ceinture", 2 * (250.0 + gap), 0.0, 90.0, False, ()),
              ("Poche", 2 * (250.0 + gap) + 80.0 + gap, 0.0, 0.0, False, ("P5",))]
    items = {}
    for name, x, y, angle, mirrored, marks in layout:
        items[name] = PieceItem(pieces[name], at_corner(pieces[name], x, y, angle, mirrored, marks), w.scene.colors)
    w.scene.add_items(list(items.values()))
    w.update_grid()
    w._saved_state = w._state()
    w.show()
    settle()
    w.view.fit_all()
    items["Devant"].setSelected(True)
    w._show_position(312.0, 147.5)
    save(w, "fenetre_principale.png")

    # menus
    for i, action in enumerate(w.menuBar().actions()):
        menu = action.menu()
        menu.popup(w.mapToGlobal(QPoint(0, 0)))
        save(menu, f"menu_{i + 1}.png")
        menu.hide()

    # À propos (chemin des préférences remplacé : pas de nom d'utilisateur dans l'image)
    from PySide6.QtWidgets import QMessageBox
    w.config_path = Path("C:/Users/<nom>/.cut_layout/config.ini")
    box = QMessageBox(QMessageBox.NoIcon, "", w.about_text(), QMessageBox.Ok, w)
    box.show()
    save(box, "a_propos.png")
    box.close()
    w.config_path = tmp / "config.ini"

    # gros plan : pièce sélectionnée (nœuds visibles), T de montage
    w.scene.clearSelection()
    items["Poche"].setSelected(True)
    x0, y0, x1, y1 = items["Poche"].plan_bbox()
    from cut_layout.ui.scene import plan_rect
    w.view.fitInView(plan_rect(x0 - 25, y0 - 25, x1 + 25, y1 + 25), Qt.KeepAspectRatio)
    save(w.view, "poche_selectionnee.png")

    # collision et pièce hors du plan
    poche = items["Poche"]
    before = poche.placement
    poche.set_placement(at_corner(pieces["Poche"], 2 * (250.0 + gap) - 60.0, 380.0))
    w.update_grid()
    w.scene.clearSelection()
    poche.setSelected(True)
    w._show_selection()
    x0, y0, x1, y1 = items["Dos"].plan_bbox()
    w.view.fitInView(plan_rect(x0 + 100, 250, x1 + 150, 650), Qt.KeepAspectRatio)
    save(w, "chevauchement.png")
    poche.set_placement(before)
    devant = items["Devant"]
    d_before = devant.placement
    devant.set_placement(replace(d_before, x=d_before.x - 60.0))
    w.update_grid()
    w.scene.clearSelection()
    devant.setSelected(True)
    w._show_selection()
    w.view.fitInView(plan_rect(-120, -40, 300, 640), Qt.KeepAspectRatio)
    save(w, "hors_du_plan.png")
    devant.set_placement(d_before)
    w.update_grid()

    # thème sombre (sans enregistrer dans les préférences)
    apply_app_theme(app, "dark")
    w.scene.set_theme("dark")
    w.scene.clearSelection()
    w.view.fit_all()
    save(w, "theme_sombre.png")
    apply_app_theme(app, "light")
    w.scene.set_theme("light")

    # --- fenêtres de dialogue ----------------------------------------------------------------
    sel = PieceSelectionDialog(list(pieces.values()), {"Ceinture"}, w)
    sel.list.item(0).setCheckState(Qt.Checked)
    sel.list.item(1).setCheckState(Qt.Checked)
    sel.show()
    save(sel, "choix_des_pieces.png")
    sel.close()

    props = PiecePropertiesDialog(pieces["Dos"], items["Dos"].placement, w)
    props.show()
    save(props, "proprietes.png")
    props.close()

    setup = PageSetupDialog(w.sheet, [it.plan_bbox() for it in w.scene.pieces()], w)
    setup.show()
    save(setup, "mise_en_page.png")
    setup.close()

    # import refusé : un arc et une fonction inconnue ajoutés au patron de démonstration
    import xml.etree.ElementTree as ET
    from PySide6.QtWidgets import QMessageBox
    from cut_layout.i18n import _
    from cut_layout.importers import Sm2dImportError
    tree = ET.parse(SM2D)
    root = tree.getroot()
    root.find("variables")[0].set("formula", "fmod(9; 4)")
    ET.SubElement(root.find("draftBlock/calculation"), "arc",
                  {"id": "90", "type": "arcWithLength", "name": "Arc_A_90", "center": "1", "radius": "5"})
    bad = tmp / "jupe_demo.sm2d"
    tree.write(bad, encoding="UTF-8", xml_declaration=True)
    try:
        Sm2dPattern(bad, SMIS)
    except Sm2dImportError as e:
        box = QMessageBox(QMessageBox.Critical, _("Import failed"), str(e), QMessageBox.Ok, w)
        box.show()
        save(box, "import_refuse.png")
        box.close()

    # --- PDF : plan de montage, une feuille, page d'essai ---------------------------------------
    grid = fit_grid(w.sheet, [it.plan_bbox() for it in w.scene.pieces()])
    outlines = [(it.piece.name, placed_outline(it.piece, it.placement)) for it in w.scene.pieces()]
    marks = [m for it in w.scene.pieces() for m in placed_marks(it.piece, it.placement)]
    pdf = tmp / "jupe_demo.pdf"
    report = export_mosaic(pdf, grid, outlines, title="jupe_demo", name="jupe_demo", marks=marks)
    doc = pdfium.PdfDocument(str(pdf))

    def page_png(page, name):
        """Page rendue avec un filet gris : sinon le blanc de la page se confond avec le fond de GitHub."""
        from PIL import ImageOps
        ImageOps.expand(page.render(scale=1.6).to_pil(), border=2, fill="#9a9a9a").save(out / name)
        print(out / name)

    page_png(doc[0], "pdf_plan_de_montage.png")
    # feuille qui contient le T du Devant (A3) : la première feuille non vide après le plan de montage
    target = next((i for i, (r, c) in enumerate(report.pages) if (r, c) == (2, 2)), 1)
    page_png(doc[target + 1], "pdf_feuille.png")
    from datetime import datetime
    test = export_test_page(tmp / "test.pdf", w.sheet, when=datetime(2026, 11, 25, 12, 0))   # date fixe : image stable
    page_png(pdfium.PdfDocument(str(test))[0], "page_essai.png")
    print("PDF :", len(report.pages), "feuilles", [f"{r}-{c}" for r, c in report.pages])
    w._saved_state = w._state()
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
