"""Fenêtre de propriétés d'une pièce : point de référence, position, rotation, symétrie, nœuds marqués."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QLabel, QListWidget, QPushButton, QVBoxLayout)

from ..i18n import _
from ..model.piece import Piece
from ..model.placement import (REF_CENTROID, Placement, change_reference, normalize_angle, outside_plan,
                               placed_bbox, toggle_mirror)
from ..units import format_cm
from .check_list import add_check_item

UNITS = {"cm": (10.0, 3), "mm": (1.0, 2)}     # mm par unité affichée, décimales (résolution 0,01 mm)
COORD_RANGE_MM = 100_000.0


class PiecePropertiesDialog(QDialog):
    """Les valeurs exactes sont conservées en mm ; un champ n'écrase la valeur exacte
    que si l'utilisateur le modifie (pas d'arrondi silencieux dû à l'affichage)."""

    applied = Signal(object)    # Placement

    def __init__(self, piece: Piece, placement: Placement, parent=None):
        super().__init__(parent)
        self.piece = piece
        self._pl = placement
        self.setWindowTitle(_("Properties — {name}").format(name=piece.name))

        self.ref = QComboBox()
        self.ref.addItem(_("Centroid (area)"), REF_CENTROID)
        for name in piece.nodes:
            self.ref.addItem(_("Node {name}").format(name=name), name)
        self.ref.setCurrentIndex(self.ref.findData(placement.ref))

        self.unit = QComboBox()
        self.unit.addItems(list(UNITS))
        self.x = self._coord_spin()
        self.y = self._coord_spin()

        self.angle = QDoubleSpinBox()
        self.angle.setRange(-360.0, 360.0)
        self.angle.setDecimals(2)
        self.angle.setSuffix(" °")
        steps = QHBoxLayout()
        steps.addWidget(self.angle)
        for label, delta in (("−90°", -90.0), ("+90°", 90.0), ("180°", 180.0)):
            b = QPushButton(label)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _checked=False, d=delta: self._rotate_by(d))
            steps.addWidget(b)

        self.mirror = QCheckBox(_("Mirror (vertical axis through the reference point)"))
        self.mirror.setChecked(placement.mirrored)
        if piece.forbid_flipping and not placement.mirrored:
            self.mirror.setEnabled(False)
            self.mirror.setToolTip(_("Flipping is forbidden for this piece in the pattern (Seamly2D)."))

        # nœuds marqués d'un T : liste à cocher, dans l'ordre des nœuds de la pièce
        self.marks = QListWidget()
        for name in piece.nodes:
            add_check_item(self.marks, name, checked=name in placement.marks)
        self.marks.setToolTip(_("A T mark is drawn at each checked node: its stem starts on the node, "
                                "perpendicular to the outline, towards the inside of the piece."))
        self.marks.setMaximumHeight(160)

        form = QFormLayout()
        form.addRow(_("Reference point"), self.ref)
        form.addRow(_("Unit"), self.unit)
        form.addRow(_("x from the origin"), self.x)
        form.addRow(_("y from the origin"), self.y)
        form.addRow(_("Rotation (counterclockwise +)"), steps)
        form.addRow(_("Mirror"), self.mirror)
        form.addRow(_("Marked nodes (T)"), self.marks)

        self.info = QLabel()
        self.info.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(lambda: self.applied.emit(self.placement()))

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.info)
        layout.addWidget(buttons)

        self._show_values()
        self.ref.currentIndexChanged.connect(self._ref_changed)
        self.unit.currentIndexChanged.connect(self._show_values)
        self.x.valueChanged.connect(lambda v: self._edited("x", v))
        self.y.valueChanged.connect(lambda v: self._edited("y", v))
        self.angle.valueChanged.connect(lambda v: self._edited("angle", v))
        self.mirror.toggled.connect(self._mirror_toggled)
        self.marks.itemChanged.connect(self._marks_changed)

    def _coord_spin(self) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setKeyboardTracking(False)
        return s

    # -- valeurs -----------------------------------------------------------------
    def placement(self) -> Placement:
        return replace(self._pl, angle=normalize_angle(self._pl.angle))

    def _k(self) -> float:
        return UNITS[self.unit.currentText()][0]

    def _show_values(self):
        k, dec = UNITS[self.unit.currentText()]
        for spin, v in ((self.x, self._pl.x), (self.y, self._pl.y)):
            spin.blockSignals(True)
            spin.setDecimals(dec)
            spin.setRange(-COORD_RANGE_MM / k, COORD_RANGE_MM / k)
            spin.setSuffix(f" {self.unit.currentText()}")
            spin.setValue(v / k)
            spin.blockSignals(False)
        self.angle.blockSignals(True)
        self.angle.setValue(self._pl.angle)
        self.angle.blockSignals(False)
        self._update_info()

    def _edited(self, field: str, value: float):
        k = 1.0 if field == "angle" else self._k()
        self._pl = replace(self._pl, **{field: value * k})
        self._update_info()

    def _ref_changed(self):
        self._pl = change_reference(self.piece, self._pl, self.ref.currentData())
        self._show_values()

    def _rotate_by(self, delta: float):
        self._pl = replace(self._pl, angle=normalize_angle(self._pl.angle + delta))
        self._show_values()

    def _mirror_toggled(self, checked: bool):
        """Retourne la pièce telle qu'on la voit sur le plan : l'angle change de signe (voir toggle_mirror)."""
        if checked != self._pl.mirrored:
            self._pl = toggle_mirror(self._pl)
            self._show_values()

    def _marks_changed(self, _item=None):
        checked = tuple(self.marks.item(i).text() for i in range(self.marks.count())
                        if self.marks.item(i).checkState() == Qt.Checked)
        self._pl = replace(self._pl, marks=checked)

    def _update_info(self):
        pl = self.placement()
        x0, y0, x1, y1 = placed_bbox(self.piece, pl)
        text = _("Bounding box on the layout: x {x0} to {x1} cm, y {y0} to {y1} cm ({w} × {h} cm).").format(
            x0=format_cm(x0), x1=format_cm(x1), y0=format_cm(y0), y1=format_cm(y1),
            w=format_cm(x1 - x0), h=format_cm(y1 - y0))
        if outside_plan(self.piece, pl):
            text += "<br><b style='color:#c00000'>{}</b>".format(
                _("Part of the piece is outside the layout (negative x or y)."))
        self.info.setText(text)

    def _ok(self):
        self.applied.emit(self.placement())
        self.accept()
