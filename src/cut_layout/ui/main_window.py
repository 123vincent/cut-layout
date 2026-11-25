"""Fenêtre principale : import, placement, grille de la mosaïque."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence, QPainter, QUndoStack
from PySide6.QtWidgets import (QApplication, QFileDialog, QGraphicsView, QLabel, QMainWindow, QMessageBox)

from ..config import (CONFIG_PATH, LANGUAGE_SETTINGS, Config, ConfigError, load_config, save_sheet_defaults,
                      save_value)
from ..importers import Sm2dImportError, Sm2dPattern, measurements_path
from ..export import export_mosaic, export_test_page
from ..i18n import AUTO, LANGUAGE_NAMES, _, ngettext
from ..model.correction import NO_CORRECTION
from ..model.mosaic import Grid, MosaicError, SheetSettings, fit_grid
from ..model.marks import placed_marks
from ..model.placement import placed_outline, placement_at_corner, reference_point
from ..project import EXTENSION, OPEN_EXTENSIONS, Project, ProjectError, changed_files, load_project, save_project, sha256
from ..units import format_cm
from .commands import AddPiecesCommand, RemovePiecesCommand, SetPlacementCommand, SetSheetCommand
from .page_setup_dialog import PageSetupDialog
from .piece_properties_dialog import PiecePropertiesDialog
from .piece_selection_dialog import PieceSelectionDialog
from .scene import CuttingScene, PieceItem, to_plan
from .theme import apply_app_theme

# Placement par défaut d'une pièce importée : à droite des pièces déjà placées, sur l'axe x,
# sans rotation (aucun chevauchement possible). Modifiable ensuite dans ses propriétés.
IMPORT_GAP_MM = 20.0
ZOOM_STEP = 1.15
DRAG_DECIMALS = 1    # position après un glisser arrondie à 0,1 mm ; valeur fine : fenêtre de propriétés


class CuttingView(QGraphicsView):
    """Clic sur une pièce : la sélectionne ; glisser : la déplace ; double-clic : ses propriétés.
    Glisser dans le vide : déplace la vue."""

    mouse_moved = Signal(float, float)   # coordonnées du plan, mm
    piece_double_clicked = Signal(object)  # PieceItem
    piece_moving = Signal(object)        # PieceItem, pendant le glisser
    piece_moved = Signal(object, object)  # PieceItem, placement avant le glisser ; au relâchement

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setMouseTracking(True)
        self._drag = None    # (pièce, position écran de départ, point du plan de départ, placement de départ, actif)

    def _piece_at_point(self, point) -> PieceItem | None:
        item = self.itemAt(point)
        while item is not None and not isinstance(item, PieceItem):
            item = item.parentItem()
        return item

    def mouseDoubleClickEvent(self, event):
        item = self._piece_at_point(event.position().toPoint())
        if item is not None:
            self.piece_double_clicked.emit(item)
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        item = self._piece_at_point(event.position().toPoint()) if event.button() == Qt.LeftButton else None
        if item is None:
            super().mousePressEvent(event)
            return
        self.scene().clearSelection()
        item.setSelected(True)
        pos = event.position().toPoint()
        self._drag = (item, pos, to_plan(self.mapToScene(pos)), item.placement, False)
        event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self.mouse_moved.emit(*to_plan(self.mapToScene(pos)))
        if self._drag is None:
            super().mouseMoveEvent(event)
            return
        item, start_pos, start, placement, active = self._drag
        if not active and (pos - start_pos).manhattanLength() < QApplication.startDragDistance():
            return     # simple clic : la pièce ne bouge pas
        self._drag = (item, start_pos, start, placement, True)
        x, y = to_plan(self.mapToScene(pos))
        item.set_placement(replace(placement, x=round(placement.x + x - start[0], DRAG_DECIMALS),
                                   y=round(placement.y + y - start[1], DRAG_DECIMALS)))
        self.piece_moving.emit(item)

    def mouseReleaseEvent(self, event):
        if self._drag is None:
            super().mouseReleaseEvent(event)
            return
        item, _pos, _start, placement, active = self._drag
        self._drag = None
        if active:
            self.piece_moved.emit(item, placement)

    def wheelEvent(self, event):
        f = ZOOM_STEP if event.angleDelta().y() > 0 else 1 / ZOOM_STEP
        self.scale(f, f)

    def fit_all(self):
        r = self.scene().itemsBoundingRect().adjusted(-20, -20, 20, 20)
        self.fitInView(r, Qt.KeepAspectRatio)


class MainWindow(QMainWindow):
    def __init__(self, config: Config | None = None, config_path: Path = CONFIG_PATH):
        super().__init__()
        self.setWindowTitle("CutLayout")
        self.config = config or Config()
        self.config_path = config_path
        self.pattern: Sm2dPattern | None = None
        self.project_path: Path | None = None
        # mise en page du plan : défauts des préférences, puis celle du .cutl ou de la fenêtre Mise en page
        self.sheet: SheetSettings = self.config.sheet
        self.scene = CuttingScene(self, theme=self.config.theme)
        self.view = CuttingView(self.scene)
        self.setCentralWidget(self.view)

        self.pos_label = QLabel()
        self.sel_label = QLabel()
        self.mosaic_label = QLabel()
        self.statusBar().addWidget(self.sel_label, 1)
        self.statusBar().addPermanentWidget(self.mosaic_label)
        self.statusBar().addPermanentWidget(self.pos_label)
        self.view.mouse_moved.connect(self._show_position)
        self.scene.selectionChanged.connect(self._show_selection)
        self.view.piece_double_clicked.connect(self.edit_piece)
        self.view.piece_moving.connect(self._piece_moving)
        self.view.piece_moved.connect(self._piece_moved)
        self.undo_stack = QUndoStack(self)

        self._build_menus()
        self.update_grid()
        self.resize(1200, 800)
        self._saved_state = self._state()

    def _build_menus(self):
        m = self.menuBar().addMenu(_("&File"))
        a = QAction(_("&Open a pattern…"), self, shortcut=QKeySequence.Open, triggered=self.open_pattern)
        m.addAction(a)
        m.addSeparator()
        m.addAction(QAction(_("Open a cutting &layout…"), self, shortcut="Ctrl+Shift+O", triggered=self.open_project))
        self.save_action = QAction(_("&Save the cutting layout"), self, shortcut=QKeySequence.Save,
                                   triggered=self.save_project, enabled=False)
        m.addAction(self.save_action)
        self.save_as_action = QAction(_("Save the cutting layout &as…"), self, shortcut=QKeySequence.SaveAs,
                                      triggered=self.save_project_as, enabled=False)
        m.addAction(self.save_as_action)
        m.addSeparator()
        m.addAction(QAction(_("&Export PDF…"), self, shortcut="Ctrl+E", triggered=self.export_pdf))
        m.addSeparator()
        m.addAction(QAction(_("&Preferences…"), self, triggered=self.open_config_file))
        m.addAction(QAction(_("&Reload preferences"), self, shortcut="F5", triggered=self.reload_config))
        m.addSeparator()
        m.addAction(QAction(_("&Quit"), self, shortcut=QKeySequence.Quit, triggered=self.close))
        e = self.menuBar().addMenu(_("&Edit"))
        # TRANSLATORS: prefix of the menu entry, followed by the name of the action (e.g. "Undo Move Demi-dos")
        self.undo_action = self.undo_stack.createUndoAction(self, _("&Undo"))
        self.undo_action.setShortcuts(QKeySequence.Undo)
        # TRANSLATORS: prefix of the menu entry, followed by the name of the action
        self.redo_action = self.undo_stack.createRedoAction(self, _("&Redo"))
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        e.addAction(self.undo_action)
        e.addAction(self.redo_action)
        p = self.menuBar().addMenu(_("&Piece"))
        self.add_action = QAction(_("&Add pieces…"), self, triggered=self.choose_pieces, enabled=False)
        p.addAction(self.add_action)
        p.addSeparator()
        p.addAction(QAction(_("&Properties…"), self, shortcut="Ctrl+I", triggered=self.edit_selected_piece))
        p.addAction(QAction(_("&Remove from layout"), self, shortcut=QKeySequence.Delete,
                            triggered=self.remove_selected_pieces))
        # TRANSLATORS: menu of the menu bar; its mnemonic must differ from File, Edit, Piece, View
        s = self.menuBar().addMenu(_("Page &setup"))
        s.addAction(QAction(_("&Page setup…"), self, shortcut="Ctrl+Shift+P", triggered=self.page_setup))
        s.addSeparator()
        s.addAction(QAction(_("Printer &test page (without correction)…"), self,
                            triggered=lambda: self.save_test_page(corrected=False)))
        s.addAction(QAction(_("Printer test page (with &correction)…"), self,
                            triggered=lambda: self.save_test_page(corrected=True)))
        v = self.menuBar().addMenu(_("&View"))
        v.addAction(QAction(_("&Show all"), self, shortcut="Ctrl+0", triggered=self.view.fit_all))
        self.dark_action = QAction(_("&Dark theme"), self, checkable=True, checked=self.config.theme == "dark",
                                   toggled=self.toggle_dark)
        v.addAction(self.dark_action)
        lang = v.addMenu(_("&Language"))
        group = QActionGroup(self)
        names = {AUTO: _("Automatic (system language)"), **LANGUAGE_NAMES}
        self.language_actions = {}
        for code in LANGUAGE_SETTINGS:
            act = QAction(names[code], self, checkable=True, checked=self.config.language == code)
            act.triggered.connect(lambda _checked=False, c=code: self.set_language(c))
            group.addAction(act)
            lang.addAction(act)
            self.language_actions[code] = act
        h = self.menuBar().addMenu(_("&Help"))
        h.addAction(QAction(_("&About CutLayout…"), self, triggered=self.about))

    # -- configuration, thème, grille ------------------------------------------
    def update_grid(self):
        """Grille ajustée automatiquement au plus petit nombre de feuilles couvrant les pièces."""
        self.scene.update_collisions()
        grid = fit_grid(self.sheet, [it.plan_bbox() for it in self.scene.pieces()])
        self.scene.set_grid(grid)
        w, h = self.sheet.cell_size
        self.mosaic_label.setText(ngettext(
            "{rows} × {cols} = {count} sheet {sheet} (frame {w} × {h} cm)",
            "{rows} × {cols} = {count} sheets {sheet} (frame {w} × {h} cm)", grid.count).format(
            rows=grid.rows, cols=grid.cols, count=grid.count, sheet=self.sheet.describe(),
            w=format_cm(w, 1), h=format_cm(h, 1)))

    # -- mise en page ----------------------------------------------------------
    def _apply_sheet(self, sheet: SheetSettings):
        self.sheet = sheet
        self.update_grid()

    def page_setup(self):
        dlg = PageSetupDialog(self.sheet, [it.plan_bbox() for it in self.scene.pieces()], self)
        if dlg.exec() != PageSetupDialog.Accepted or dlg.sheet() is None:
            return
        new = dlg.sheet()
        if new != self.sheet:
            self.undo_stack.push(SetSheetCommand(self._apply_sheet, self.sheet, new))
        if dlg.save_default.isChecked():
            try:
                save_sheet_defaults(new, self.config_path)
            except (OSError, ConfigError) as e:
                QMessageBox.warning(self, _("Page setup"), _("Default values not saved:") + f"\n{e}")
                return
            self.config = replace(self.config, sheet=replace(new, print_margin=self.config.sheet.print_margin))

    def _with_printer_margin(self, sheet: SheetSettings) -> tuple[SheetSettings, str | None]:
        """Mise en page du plan avec la marge d'impression des préférences (réglage de l'imprimante).
        Si elle n'est pas compatible avec la marge d'assemblage du plan, la mise en page est gardée telle
        quelle et le message d'erreur est renvoyé."""
        try:
            return replace(sheet, print_margin=self.config.sheet.print_margin), None
        except MosaicError as e:
            return sheet, str(e)

    def _after_change(self):
        self.update_grid()
        self._show_selection()

    def _set_placement(self, item: PieceItem, old, new, text: str):
        if new != old:
            self.undo_stack.push(SetPlacementCommand(self.scene, item, old, new, text, self._after_change))

    def _piece_moved(self, item: PieceItem, before):
        self._set_placement(item, before, item.placement, _("Move {name}").format(name=item.piece.name))

    def _piece_moving(self, _item):
        self.scene.update_collisions()     # couleur de collision visible pendant le glisser
        self._show_selection()

    def open_config_file(self):
        load_config(self.config_path)    # crée le fichier par défaut s'il n'existe pas
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config_path)))

    def reload_config(self):
        try:
            config = load_config(self.config_path)
        except ConfigError as e:
            QMessageBox.critical(self, _("Configuration"), _("Configuration not applied:") + f"\n{e}")
            return
        language_changed = config.language != self.config.language
        self.config = config
        self._apply_theme(config.theme)
        self.language_actions[config.language].setChecked(True)
        self.dark_action.blockSignals(True)
        self.dark_action.setChecked(config.theme == "dark")
        self.dark_action.blockSignals(False)
        if self.pattern is None:            # pas encore de plan : il suit les valeurs par défaut
            self.sheet = config.sheet
        else:                               # plan en cours : seule la marge d'impression vient des préférences
            self.sheet, error = self._with_printer_margin(self.sheet)
            if error:
                QMessageBox.warning(self, _("Configuration"),
                                    _("Print margin not applied to this layout:") + f"\n{error}")
        self.update_grid()
        if language_changed:
            QMessageBox.information(self, _("Language"), _("The language will change at the next start."))

    def toggle_dark(self, checked: bool):
        theme = "dark" if checked else "light"
        self.config = replace(self.config, theme=theme)
        self._apply_theme(theme)
        try:
            save_value("theme", theme, self.config_path)
        except (OSError, ConfigError, ValueError) as e:
            QMessageBox.warning(self, _("Configuration"), _("Theme applied but not saved:") + f"\n{e}")

    def set_language(self, language: str):
        """Enregistrée dans la configuration ; appliquée au prochain démarrage."""
        if language == self.config.language:
            return
        try:
            save_value("language", language, self.config_path)
        except (OSError, ConfigError, ValueError) as e:
            QMessageBox.warning(self, _("Configuration"), _("Language not saved:") + f"\n{e}")
            self.language_actions[self.config.language].setChecked(True)
            return
        self.config = replace(self.config, language=language)
        QMessageBox.information(self, _("Language"), _("The language will change at the next start."))

    def _apply_theme(self, theme: str):
        app = QApplication.instance()
        if app is not None:
            apply_app_theme(app, theme)
        self.scene.set_theme(theme)

    # -- à propos ----------------------------------------------------------------
    def about_text(self) -> str:
        from .. import __version__
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion
        import html
        import platform
        import reportlab
        return (f"<h3>CutLayout {__version__}</h3>"
                + "<p>" + _("Printable 1:1 cutting layout for Seamly2D patterns.") + "</p>"
                + "<p>" + _("Preferences: {path}").format(path=html.escape(str(self.config_path))) + "</p>"
                + "<p style='color:gray'>Python {py} · Qt {qt} · PySide6 {ps} · reportlab {rl}<br>{os}</p>".format(
                    py=platform.python_version(), qt=qVersion(), ps=pyside_version, rl=reportlab.Version,
                    os=platform.platform(terse=True)))

    def about(self):
        QMessageBox.about(self, _("About CutLayout"), self.about_text())

    # -- export PDF --------------------------------------------------------------
    def _default_dir(self) -> Path:
        return self.pattern.sm2d_path.parent if self.pattern is not None else Path.home()

    def export_pdf(self):
        items = self.scene.pieces()
        if not items:
            QMessageBox.information(self, _("Export PDF"), _("No piece on the layout."))
            return
        outside = [it.piece.name for it in items if it.is_outside()]
        if outside and QMessageBox.warning(
                self, _("Export PDF"),
                _("Piece(s) partly outside the layout (negative x or y): {names}\n"
                  "The part outside the layout will not be printed.\n\nExport anyway?").format(
                    names=", ".join(outside)),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.scene.update_collisions()
        overlapping = [it.piece.name for it in items if it.collides_with]
        if overlapping and QMessageBox.warning(
                self, _("Export PDF"),
                _("Overlapping pieces: {names}\n\nExport anyway?").format(names=", ".join(overlapping)),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        stem = self.pattern.sm2d_path.stem if self.pattern is not None else "layout"
        # TRANSLATORS: suffix of the exported PDF file name, no spaces
        suffix = _("cutting_layout")
        path = QFileDialog.getSaveFileName(self, _("Export PDF"),
                                           str(self._default_dir() / f"{stem}_{suffix}.pdf"), "PDF (*.pdf)")[0]
        if not path:
            return
        grid = fit_grid(self.sheet, [it.plan_bbox() for it in items])
        outlines = [(it.piece.name, placed_outline(it.piece, it.placement)) for it in items]
        marks = [m for it in items for m in placed_marks(it.piece, it.placement)]
        try:
            report = export_mosaic(path, grid, outlines, title=_("Cutting layout — {name}").format(name=stem),
                                   correction=self.config.correction, name=stem, marks=marks)
        except OSError as e:
            QMessageBox.critical(self, _("Export PDF"), _("Cannot write the file:") + f"\n{e}")
            return
        omitted = ", ".join(Grid.label(r, c) for r, c in report.omitted) or _("none")
        n = len(report.pages)
        text = ngettext("{n} page {sheet} exported, row by row from {first}.",
                        "{n} pages {sheet} exported, row by row from {first}.", n).format(
            n=n, sheet=self.sheet.describe(), first=Grid.label(1, 1))
        text += "\n" + _("Empty pages omitted: {omitted}.").format(omitted=omitted)
        text += "\n" + _("First page: assembly plan (reduced, not to scale).")
        text += "\n" + _("Printer: {correction}.").format(correction=self.config.correction.describe())
        text += "\n\n" + _("Print at 100 % (actual size).")
        self._offer_open(path, text)

    def save_test_page(self, corrected: bool):
        s = self.sheet
        correction = self.config.correction if corrected else NO_CORRECTION
        # TRANSLATORS: parts of the test page file name, no spaces
        name = _("test_page")
        suffix = _("with_correction") if corrected else _("without_correction")
        path = QFileDialog.getSaveFileName(
            self, _("Printer test page"),
            str(self._default_dir() / f"{name}_{s.format}_{s.orientation}_{suffix}.pdf"), "PDF (*.pdf)")[0]
        if not path:
            return
        try:
            export_test_page(path, s, correction=correction)
        except OSError as e:
            QMessageBox.critical(self, _("Printer test page"), _("Cannot write the file:") + f"\n{e}")
            return
        self._offer_open(path, _("Test page {sheet} saved ({correction}).\n\n"
                                 "Print at 100 % (actual size), then follow the instructions on the page.").format(
            sheet=s.describe(), correction=correction.describe()))

    def _offer_open(self, path: str, text: str):
        box = QMessageBox(QMessageBox.Information, "PDF", f"{text}\n\n{path}", parent=self)
        open_btn = box.addButton(_("Open the PDF"), QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # -- import ----------------------------------------------------------------
    def open_pattern(self, sm2d: str | None = None):
        if not sm2d:
            sm2d = QFileDialog.getOpenFileName(self, _("Open a Seamly2D pattern"), "",
                                               _("Seamly2D pattern (*.sm2d)"))[0]
            if not sm2d:
                return
        smis = self._choose_measurements(Path(sm2d))
        if smis is None:
            return
        try:
            pattern = Sm2dPattern(sm2d, smis)
        except Sm2dImportError as e:
            QMessageBox.critical(self, _("Import failed"), str(e))
            return
        if not self._confirm_replace(_("Open a pattern")):
            return
        self.scene.clear_pieces()
        self.sheet = self.config.sheet          # nouveau plan : mise en page par défaut des préférences
        self.update_grid()
        self._set_pattern(pattern, None)
        self._saved_state = self._state()
        self.undo_stack.clear()
        self.choose_pieces()

    # -- modifications non enregistrées -----------------------------------------
    def _state(self):
        """Ce qu'enregistre un .cutl : patron, mesures, mise en page, pièces et placements."""
        paths = (None, None) if self.pattern is None else (self.pattern.sm2d_path, self.pattern.smis_path)
        return paths, self.sheet, frozenset((it.piece.name, it.placement) for it in self.scene.pieces())

    def is_modified(self) -> bool:
        return self._state() != self._saved_state

    def _confirm_discard(self, title: str) -> bool:
        """Propose d'enregistrer les modifications ; faux si l'utilisateur annule."""
        if not self.is_modified():
            return True
        answer = QMessageBox.question(
            self, title, _("The cutting layout has unsaved changes. Save them?"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            self.save_project()
            return not self.is_modified()       # enregistrement annulé ou en échec : on reste
        return answer == QMessageBox.Discard

    def _confirm_replace(self, title: str) -> bool:
        """Avant de remplacer les pièces du plan (autre patron, autre plan)."""
        if self.is_modified():
            return self._confirm_discard(title)
        return not self.scene.pieces() or QMessageBox.question(
            self, title, _("Remove the pieces already imported from the layout?")) == QMessageBox.Yes

    def closeEvent(self, event):
        if self._confirm_discard(_("Quit")):
            event.accept()
        else:
            event.ignore()

    def _set_pattern(self, pattern: Sm2dPattern, project_path: Path | None):
        self.pattern = pattern
        self.project_path = project_path
        for act in (self.add_action, self.save_action, self.save_as_action):
            act.setEnabled(True)
        self._update_title()

    def _update_title(self):
        title = _("CutLayout — {pattern}  (measurements: {measurements})").format(
            pattern=self.pattern.sm2d_path.name, measurements=self.pattern.smis_path.name)
        if self.project_path is not None:
            title = f"{self.project_path.name} — {title}"
        self.setWindowTitle(title)

    # -- fichier de plan de coupe (.cutl) ---------------------------------------
    def save_project(self):
        if self.project_path is None:
            self.save_project_as()
        else:
            self._write_project(self.project_path)

    def save_project_as(self):
        if self.pattern is None:
            return
        # TRANSLATORS: file type in the save dialog; keep the {pattern} placeholder
        path = QFileDialog.getSaveFileName(
            self, _("Save the cutting layout"),
            str(self._default_dir() / f"{self.pattern.sm2d_path.stem}{EXTENSION}"),
            _("Cutting layout ({pattern})").format(pattern=f"*{EXTENSION}"))[0]
        if path:
            self._write_project(Path(path).with_suffix(EXTENSION))

    def _write_project(self, path: Path):
        items = sorted(self.scene.pieces(), key=lambda it: it.piece.name)
        try:
            project = Project(self.pattern.sm2d_path, self.pattern.smis_path,
                              sha256(self.pattern.sm2d_path), sha256(self.pattern.smis_path), self.sheet,
                              [(it.piece.name, it.placement) for it in items])
            save_project(path, project)
        except OSError as e:
            QMessageBox.critical(self, _("Save the cutting layout"), _("Cannot write the file:") + f"\n{e}")
            return
        self.project_path = path
        self._saved_state = self._state()
        self._update_title()
        self.statusBar().showMessage(_("Cutting layout saved: {path}").format(path=path), 5000)

    def open_project(self, path: str | None = None):
        if not path:
            path = QFileDialog.getOpenFileName(self, _("Open a cutting layout"), str(self._default_dir()),
                                               _("Cutting layout ({pattern})").format(
                                                   pattern=" ".join(f"*{e}" for e in OPEN_EXTENSIONS)))[0]
            if not path:
                return
        title = _("Open a cutting layout")
        try:
            project = load_project(Path(path))
            missing_files = [p for p in (project.sm2d, project.smis) if not p.is_file()]
            if missing_files:
                raise ProjectError(_("file(s) not found:") + "\n" + "\n".join(map(str, missing_files)))
            changed = changed_files(project)
            pattern = Sm2dPattern(project.sm2d, project.smis)
            names = set(pattern.piece_names())
        except (ProjectError, Sm2dImportError, OSError) as e:
            QMessageBox.critical(self, title, str(e))
            return
        if changed and QMessageBox.warning(
                self, title,
                _("Modified since the cutting layout was saved:\n{files}\n\n"
                  "The pieces will be recomputed from the current files, at the saved positions. "
                  "Check them (overlaps are shown in colour).\n\nOpen anyway?").format(
                    files="\n".join(map(str, changed))),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        if not self._confirm_replace(title):
            return
        self.scene.clear_pieces()
        skipped, lost_marks = [], []
        for name, placement in project.placements:
            if name not in names:
                skipped.append(_("{name}: no longer in the pattern").format(name=name))
                continue
            try:
                piece = pattern.piece(name)
                reference_point(piece, placement.ref)
            except (Sm2dImportError, ValueError) as e:
                skipped.append(f"{name}: {e}")
                continue
            lost = [m for m in placement.marks if m not in piece.nodes]
            if lost:
                placement = replace(placement, marks=tuple(m for m in placement.marks if m in piece.nodes))
                lost_marks.append(_("{name}: marked node(s) no longer in the pattern: {nodes}").format(
                    name=name, nodes=", ".join(lost)))
            self.scene.add_piece(piece, placement)
        self.sheet, margin_error = self._with_printer_margin(project.sheet)
        self._set_pattern(pattern, Path(path))
        self._saved_state = self._state()
        self.undo_stack.clear()
        self.update_grid()
        self.view.fit_all()
        notes = []
        if margin_error:
            notes.append(_("Print margin of the preferences not applied to this layout:") + f"\n{margin_error}")
        if skipped:
            notes.append(_("Pieces not placed:") + "\n" + "\n".join(skipped))
        if lost_marks:
            notes.append(_("Marks removed:") + "\n" + "\n".join(lost_marks))
        if notes:
            QMessageBox.warning(self, title, "\n\n".join(notes))

    def _choose_measurements(self, sm2d: Path) -> str | None:
        try:
            declared = measurements_path(sm2d)
        except Exception as e:   # XML illisible : signalé, puis choix manuel
            QMessageBox.warning(self, _("Measurements"), _("Cannot read the measurements path: {error}").format(error=e))
            declared = None
        if declared is not None and declared.is_file():
            box = QMessageBox(QMessageBox.Question, _("Measurements file"),
                              _("The pattern uses the measurements:\n{path}\n\nUse this file?").format(path=declared),
                              parent=self)
            use = box.addButton(_("Use"), QMessageBox.AcceptRole)
            other = box.addButton(_("Choose another…"), QMessageBox.ActionRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is use:
                return str(declared)
            if box.clickedButton() is not other:
                return None
        elif declared is not None:
            QMessageBox.information(self, _("Measurements file"),
                                    _("The measurements file declared by the pattern was not found:\n{path}\n\n"
                                      "Choose the .smis file to use.").format(path=declared))
        smis = QFileDialog.getOpenFileName(self, _("Measurements file"), str(sm2d.parent),
                                           _("Individual measurements (*.smis)"))[0]
        return smis or None

    def choose_pieces(self):
        if self.pattern is None:
            return
        try:
            pieces = [self.pattern.piece(n) for n in self.pattern.piece_names()]
        except Sm2dImportError as e:
            QMessageBox.critical(self, _("Import failed"), str(e))
            return
        imported = {it.piece.name for it in self.scene.pieces()}
        dlg = PieceSelectionDialog(pieces, imported, self)
        if dlg.exec() != PieceSelectionDialog.Accepted:
            return
        by_name = {p.name: p for p in pieces}
        x = max((it.plan_bbox()[2] + IMPORT_GAP_MM for it in self.scene.pieces()), default=0.0)
        items = []
        for name in dlg.selected_names():
            piece = by_name[name]
            items.append(PieceItem(piece, placement_at_corner(piece, x, 0.0), self.scene.colors))
            x = items[-1].plan_bbox()[2] + IMPORT_GAP_MM
        if items:
            self.undo_stack.push(AddPiecesCommand(self.scene, items, self._after_change))
        self.view.fit_all()

    # -- propriétés d'une pièce ------------------------------------------------
    def edit_selected_piece(self):
        sel = [it for it in self.scene.selectedItems() if isinstance(it, PieceItem)]
        if len(sel) != 1:
            QMessageBox.information(self, _("Properties"), _("Select a piece (click), or double-click it."))
            return
        self.edit_piece(sel[0])

    def remove_selected_pieces(self):
        """Retire les pièces sélectionnées du plan (elles restent réimportables par « Ajouter des pièces »)."""
        items = sorted((it for it in self.scene.selectedItems() if isinstance(it, PieceItem)),
                       key=lambda it: it.piece.name)
        if items:
            self.undo_stack.push(RemovePiecesCommand(self.scene, items, self._after_change))

    def edit_piece(self, item: PieceItem):
        dlg = PiecePropertiesDialog(item.piece, item.placement, self)

        def apply(placement):
            self._set_placement(item, item.placement, placement,
                                _("Change the properties of {name}").format(name=item.piece.name))
        dlg.applied.connect(apply)
        dlg.exec()

    # -- barre d'état ----------------------------------------------------------
    def _show_position(self, x, y):
        self.pos_label.setText(f"x = {format_cm(x)} cm   y = {format_cm(y)} cm")

    def _show_selection(self):
        sel = [it for it in self.scene.selectedItems() if isinstance(it, PieceItem)]
        self.sel_label.setText("   |   ".join(it.description() for it in sel))
