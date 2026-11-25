"""Choix des pièces à importer."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QVBoxLayout

from ..i18n import _
from ..model.piece import Piece
from ..units import format_cm
from .check_list import add_check_item


class PieceSelectionDialog(QDialog):
    def __init__(self, pieces: list[Piece], already_imported: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Pieces to import"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("Check the pieces to import (net outlines, without seam allowance):")))
        self.list = QListWidget()
        for p in pieces:
            text = _("{name}   ({width} × {height} cm)").format(
                name=p.name, width=format_cm(p.width), height=format_cm(p.height))
            if p.on_fold:
                text += " — " + _("on fold")
            if p.name in already_imported:
                add_check_item(self.list, text + "   — " + _("already imported"), data=p.name, enabled=False)
            else:
                add_check_item(self.list, text, data=p.name)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, 260)

    def selected_names(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]
