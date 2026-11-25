"""Fenêtre « Mise en page » : format, orientation et marge d'assemblage du plan de coupe.

La marge d'impression est un réglage de l'imprimante (préférences) : affichée, pas modifiable ici.
Les valeurs choisies sont celles du plan (enregistrées dans le .cutl) ; la case « valeurs par défaut »
les écrit aussi dans les préférences, pour les nouveaux plans.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QVBoxLayout)

from ..i18n import _, fmt_g, ngettext
from ..model.mosaic import (CUSTOM, CUSTOM_RANGE_MM, FORMATS, ORIENTATIONS, MosaicError, Rect, SheetSettings,
                            fit_grid, format_label, orientation_label)
from ..units import format_cm


class PageSetupDialog(QDialog):
    def __init__(self, sheet: SheetSettings, piece_boxes: list[Rect], parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Page setup"))
        self._boxes = piece_boxes
        self._sheet: SheetSettings | None = sheet

        self.format = QComboBox()
        for f in FORMATS:
            self.format.addItem(format_label(f), f)
        self.format.setCurrentIndex(self.format.findData(sheet.format))

        w, h = sheet.portrait_size
        self.width, self.height = self._mm_spin(w), self._mm_spin(h)
        size = QHBoxLayout()
        size.addWidget(self.width)
        size.addWidget(QLabel("×"))
        size.addWidget(self.height)

        self.orientation = QComboBox()
        for o in ORIENTATIONS:
            self.orientation.addItem(orientation_label(o), o)
        self.orientation.setCurrentIndex(self.orientation.findData(sheet.orientation))

        self.assembly = QDoubleSpinBox()
        self.assembly.setRange(0.0, 200.0)
        self.assembly.setDecimals(1)
        self.assembly.setSuffix(" mm")
        self.assembly.setValue(sheet.assembly_margin)

        form = QFormLayout()
        form.addRow(_("Sheet format"), self.format)
        form.addRow(_("Custom size (width × height)"), size)
        form.addRow(_("Orientation"), self.orientation)
        form.addRow(_("Assembly margin (cutting frame)"), self.assembly)
        form.addRow(_("Print margin (printer)"),
                    QLabel(_("{value} mm — set in File > Preferences").format(value=fmt_g(sheet.print_margin))))

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.save_default = QCheckBox(_("Also use as default for new layouts"))
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.info)
        layout.addWidget(self.save_default)
        layout.addWidget(self.buttons)

        self._print_margin = sheet.print_margin
        for signal in (self.format.currentIndexChanged, self.orientation.currentIndexChanged,
                       self.width.valueChanged, self.height.valueChanged, self.assembly.valueChanged):
            signal.connect(self._update)
        self._update()

    @staticmethod
    def _mm_spin(value: float) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(*CUSTOM_RANGE_MM)
        s.setDecimals(1)
        s.setSuffix(" mm")
        s.setValue(value)
        return s

    def sheet(self) -> SheetSettings | None:
        """Réglages saisis, ou None s'ils sont invalides."""
        return self._sheet

    def _update(self):
        fmt = self.format.currentData()
        custom = fmt == CUSTOM
        self.width.setEnabled(custom)
        self.height.setEnabled(custom)
        if not custom:              # dimensions du format standard affichées pour information
            for spin, v in zip((self.width, self.height), SheetSettings(fmt).portrait_size):
                spin.blockSignals(True)
                spin.setValue(v)
                spin.blockSignals(False)
        try:
            self._sheet = SheetSettings(fmt, self.orientation.currentData(), self.assembly.value(),
                                        self._print_margin,
                                        self.width.value() if custom else 0.0,
                                        self.height.value() if custom else 0.0)
        except MosaicError as e:
            self._sheet = None
            self.info.setText(f"<b style='color:#c00000'>{e}</b>")
        else:
            s = self._sheet
            W, H = s.sheet_size
            w, h = s.cell_size
            grid = fit_grid(s, self._boxes)
            self.info.setText(
                _("Sheet {W} × {H} cm, cutting frame {w} × {h} cm.").format(
                    W=format_cm(W, 1), H=format_cm(H, 1), w=format_cm(w, 1), h=format_cm(h, 1))
                + "<br>" + ngettext("Current pieces: {rows} × {cols} = {count} sheet.",
                                    "Current pieces: {rows} × {cols} = {count} sheets.", grid.count).format(
                    rows=grid.rows, cols=grid.cols, count=grid.count))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(self._sheet is not None)
