"""Listes à cocher (QListWidget) à hauteur de ligne fixe.

Sans hauteur fixée, Qt calcule d'abord les lignes sans le `padding` de la feuille de style
(lignes serrées), puis les agrandit au premier changement d'état d'une case (constaté le 24.11.2026
dans la liste des pièces, puis le 25.11.2026 dans la liste des nœuds marqués). Toute liste à cocher
de l'application passe par `add_check_item`.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem

INDICATOR_PX = 16      # case à cocher (14 px + bordure, styles/*.qss)
ROW_PADDING_PX = 4     # = padding vertical de QListWidget::item (styles/dark.qss)


def check_row_size(widget: QListWidget) -> QSize:
    """Hauteur d'une ligne : texte ou case (la plus grande), plus le padding du thème en haut et en bas."""
    return QSize(0, max(widget.fontMetrics().height(), INDICATOR_PX) + 2 * ROW_PADDING_PX)


def add_check_item(widget: QListWidget, text: str, *, checked: bool = False, data: Any = None,
                   enabled: bool = True) -> QListWidgetItem:
    """Ajoute une ligne à cocher (ou une ligne grisée, non cochable, si `enabled` est faux)."""
    item = QListWidgetItem(text)
    item.setSizeHint(check_row_size(widget))
    if data is not None:
        item.setData(Qt.UserRole, data)
    if enabled:
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    else:
        item.setFlags(Qt.NoItemFlags)
    widget.addItem(item)
    return item
