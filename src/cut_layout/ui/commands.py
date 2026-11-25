"""Commandes annulables (QUndoStack) : placement d'une pièce, ajout et retrait de pièces.

Chaque commande garde les objets PieceItem eux-mêmes : une pièce retirée puis remise est le même objet,
si bien que les commandes plus anciennes de la pile qui la désignent restent valables.
`on_change` (fourni par la fenêtre) recalcule la grille et la barre d'état après chaque redo/undo.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QUndoCommand

from ..i18n import _
from ..model.mosaic import SheetSettings
from ..model.placement import Placement
from .scene import CuttingScene, PieceItem


def _names(items: list[PieceItem]) -> str:
    return ", ".join(it.piece.name for it in items)


def _select(scene: CuttingScene, items: list[PieceItem]) -> None:
    scene.clearSelection()
    for it in items:
        it.setSelected(True)


class SetPlacementCommand(QUndoCommand):
    """Nouveau placement d'une pièce (glisser à la souris ou fenêtre de propriétés)."""

    def __init__(self, scene: CuttingScene, item: PieceItem, old: Placement, new: Placement, text: str,
                 on_change: Callable[[], None]):
        super().__init__(text)
        self.scene, self.item, self.old, self.new, self.on_change = scene, item, old, new, on_change

    def _apply(self, placement: Placement) -> None:
        self.item.set_placement(placement)
        _select(self.scene, [self.item])
        self.on_change()

    def redo(self):
        self._apply(self.new)

    def undo(self):
        self._apply(self.old)


class SetSheetCommand(QUndoCommand):
    """Mise en page du plan (format, orientation, marge d'assemblage)."""

    def __init__(self, apply: Callable[[SheetSettings], None], old: SheetSettings, new: SheetSettings):
        super().__init__(_("Page setup"))
        self.apply, self.old, self.new = apply, old, new

    def redo(self):
        self.apply(self.new)

    def undo(self):
        self.apply(self.old)


class AddPiecesCommand(QUndoCommand):
    def __init__(self, scene: CuttingScene, items: list[PieceItem], on_change: Callable[[], None]):
        super().__init__(_("Add {names}").format(names=_names(items)))
        self.scene, self.items, self.on_change = scene, items, on_change

    def redo(self):
        self.scene.add_items(self.items)
        self.on_change()

    def undo(self):
        self.scene.remove_pieces(self.items)
        self.on_change()


class RemovePiecesCommand(QUndoCommand):
    def __init__(self, scene: CuttingScene, items: list[PieceItem], on_change: Callable[[], None]):
        super().__init__(_("Remove {names}").format(names=_names(items)))
        self.scene, self.items, self.on_change = scene, items, on_change

    def redo(self):
        self.scene.remove_pieces(self.items)
        self.on_change()

    def undo(self):
        self.scene.add_items(self.items)
        _select(self.scene, self.items)
        self.on_change()
