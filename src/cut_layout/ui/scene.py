"""Scène du plan de coupe. Unité de scène = 1 mm.

Le plan est en repère mathématique (origine en bas à gauche, y vers le haut).
Qt a l'axe y vers le bas : la seule inversion se fait ici, dans `to_scene` / `to_plan`
et dans `placement_transform`.
"""
from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsItemGroup, QGraphicsLineItem,
                               QGraphicsPathItem, QGraphicsScene, QGraphicsSimpleTextItem)

from ..i18n import _, fmt_g
from ..model.marks import tee_mark
from ..model.mosaic import Grid
from ..model.piece import Piece
from ..model.piece import polygon_area
from ..model.placement import (REF_CENTROID, Placement, affine, outside_plan, placed_bbox, placed_outline,
                               reference_label, reference_point)
from ..units import format_cm
from .theme import SCENE_COLORS, SceneColors

AXIS_LENGTH_MM = 100.0
NODE_RADIUS_PX = 3
REF_SIZE_PX = 7
CELL_LABEL_HEIGHT_MM = 25.0
CORNER_LETTER_HEIGHT_MM = 14.0
ORIGIN_LABEL_HEIGHT_MM = 14.0  # « 0 » de l'origine, en bas à gauche du point
CORNER_DISC_RADIUS_MM = 12.0   # pastille sous la lettre : masque les pointillés
# surface commune au-delà de laquelle deux pièces sont en collision ; en dessous : contact bord à bord
# (bruit numérique de deux contours qui se touchent)
COLLISION_TOL_MM2 = 1.0
Z_GRID, Z_AXIS, Z_PIECES = -2, -1, 0


def to_scene(x: float, y: float) -> QPointF:
    return QPointF(x, -y)


def to_plan(p: QPointF) -> tuple[float, float]:
    return p.x(), -p.y()


def plan_rect(x0: float, y0: float, x1: float, y1: float) -> QRectF:
    """Rectangle du plan (y vers le haut) → rectangle de scène."""
    return QRectF(QPointF(x0, -y1), QPointF(x1, -y0))


def placement_transform(piece: Piece, placement: Placement) -> QTransform:
    """Transformation des coordonnées de l'item (brouillon, y inversé) vers la scène (plan, y inversé)."""
    a, b, c, d, e, f = affine(piece, placement)
    # scène = F·A·F·item + F·t, avec F = diag(1, -1) ; QTransform : x' = m11 x + m21 y + dx, y' = m12 x + m22 y + dy
    return QTransform(a, -c, -b, d, e, -f)


def cosmetic_pen(color, style=Qt.SolidLine, width=0) -> QPen:
    pen = QPen(QColor(color), width, style)   # largeur 0 = 1 pixel quel que soit le zoom
    pen.setCosmetic(True)
    return pen


def overlap_area(a: QPainterPath, b: QPainterPath) -> float:
    """Surface commune de deux contours fermés (mm²)."""
    if not a.boundingRect().intersects(b.boundingRect()):
        return 0.0
    common = a.intersected(b)
    return sum(abs(polygon_area([(p.x(), p.y()) for p in poly])) for poly in common.toFillPolygons())


def format_angle(a: float) -> str:
    return fmt_g(a) + "°"


class _Marker(QGraphicsEllipseItem):
    """Pastille de taille constante à l'écran."""

    def __init__(self, parent, pos: QPointF, radius_px: float):
        super().__init__(QRectF(-radius_px, -radius_px, 2 * radius_px, 2 * radius_px), parent)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setPos(pos)

    def set_color(self, color: str):
        self.setPen(cosmetic_pen(color))
        self.setBrush(QColor(color))


class _Label(QGraphicsSimpleTextItem):
    def __init__(self, parent, pos: QPointF, text: str):
        super().__init__(text, parent)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setPos(pos)

    def set_color(self, color: str):
        self.setBrush(QColor(color))


class _MarkLabel(QGraphicsSimpleTextItem):
    """Nom d'un nœud marqué, centré sur son point, taille constante à l'écran."""

    def __init__(self, parent, pos: QPointF, text: str):
        super().__init__(text, parent)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        r = self.boundingRect()
        self.setTransform(QTransform.fromTranslate(-r.width() / 2, -r.height() / 2))
        self.setPos(pos)

    def set_color(self, color: str):
        self.setBrush(QColor(color))


class _RefCross(QGraphicsPathItem):
    def __init__(self, parent):
        super().__init__(parent)
        s = REF_SIZE_PX
        path = QPainterPath(QPointF(-s, 0))
        path.lineTo(s, 0)
        path.moveTo(0, -s)
        path.lineTo(0, s)
        self.setPath(path)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

    def set_color(self, color: str):
        self.setPen(cosmetic_pen(color, width=2))


class PieceItem(QGraphicsPathItem):
    """Contour d'une pièce. Le chemin est en coordonnées du brouillon (y inversé) ;
    le placement est porté par la transformation de l'item."""

    def __init__(self, piece: Piece, placement: Placement | None = None,
                 colors: SceneColors = SCENE_COLORS["light"]):
        super().__init__()
        self.piece = piece
        self.colors = colors
        self.collides_with: list[str] = []    # noms des pièces chevauchées, tenu à jour par la scène
        path = QPainterPath(to_scene(*piece.outline[0]))
        for p in piece.outline[1:]:
            path.lineTo(to_scene(*p))
        path.closeSubpath()
        self.setPath(path)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(Z_PIECES)

        self._node_items = []
        for name, xy in piece.nodes.items():
            pos = to_scene(*xy)
            self._node_items.append(_Marker(self, pos, NODE_RADIUS_PX))
            self._node_items.append(_Label(self, pos, f" {name}"))
        self._marks_path = QGraphicsPathItem(self)     # repères en T, repère du brouillon comme le contour
        self._mark_labels: list[_MarkLabel] = []
        self._marks: tuple[str, ...] | None = None
        self._ref_cross = _RefCross(self)
        self._ref_label = _Label(self, QPointF(), "")
        self._set_nodes_visible(False)
        self.set_placement(placement or Placement())

    # -- placement ---------------------------------------------------------------
    def set_placement(self, placement: Placement) -> None:
        self.placement = placement
        self.setTransform(placement_transform(self.piece, placement))
        if placement.marks != self._marks:
            self._build_marks(placement.marks)
        ref = to_scene(*reference_point(self.piece, placement.ref))
        self._ref_cross.setPos(ref)
        self._ref_label.setPos(ref)
        self._ref_label.setText(" " + reference_label(REF_CENTROID) if placement.ref == REF_CENTROID else "")
        self.set_colors(self.colors)
        self.setToolTip(self.description())

    def _build_marks(self, marks: tuple[str, ...]) -> None:
        """Les T sont dessinés dans le repère du brouillon : la transformation de la pièce les place."""
        path = QPainterPath()
        for label in self._mark_labels:
            label.setParentItem(None)
            if label.scene() is not None:
                label.scene().removeItem(label)
        self._mark_labels = []
        for node in marks:
            m = tee_mark(self.piece, node)
            for p, q in (m.stem, m.bar):
                path.moveTo(to_scene(*p))
                path.lineTo(to_scene(*q))
            self._mark_labels.append(_MarkLabel(self, to_scene(*m.label_at), node))
        self._marks_path.setPath(path)
        self._marks = marks

    def mark_lines_plan(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Segments des T tels qu'affichés, en coordonnées du plan (vérification de l'affichage)."""
        path, out = self._marks_path.path(), []
        for k in range(0, path.elementCount(), 2):
            a, b = path.elementAt(k), path.elementAt(k + 1)
            out.append((to_plan(self.mapToScene(QPointF(a.x, a.y))), to_plan(self.mapToScene(QPointF(b.x, b.y)))))
        return out

    def set_colors(self, colors: SceneColors) -> None:
        self.colors = colors
        color = (colors.outside if self.is_outside() else colors.collision if self.collides_with
                 else colors.piece)
        self.setPen(cosmetic_pen(color))
        self._marks_path.setPen(cosmetic_pen(color, width=2))
        for label in self._mark_labels:
            label.set_color(color)
        fill = QColor(color)
        fill.setAlpha(colors.piece_fill_alpha)
        self.setBrush(fill)
        for it in self._node_items:
            it.set_color(colors.node)
        self._ref_cross.set_color(colors.ref)
        self._ref_label.set_color(colors.ref)

    def plan_bbox(self) -> tuple[float, float, float, float]:
        """Boîte englobante du contour placé, en coordonnées du plan (mm)."""
        return placed_bbox(self.piece, self.placement)

    def is_outside(self) -> bool:
        return outside_plan(self.piece, self.placement)

    def plan_path(self) -> QPainterPath:
        """Contour placé, en coordonnées du plan (mm)."""
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(x, y) for x, y in placed_outline(self.piece, self.placement)]))
        path.closeSubpath()
        return path

    def set_collisions(self, names: list[str]) -> None:
        if names != self.collides_with:
            self.collides_with = names
            self.set_colors(self.colors)
            self.setToolTip(self.description())

    def description(self) -> str:
        p, pl = self.piece, self.placement
        text = _("{name}: {width} × {height} cm").format(name=p.name, width=format_cm(p.width),
                                                          height=format_cm(p.height))
        if p.on_fold:
            text += " — " + _("on fold")
        text += " — " + _("{ref} at ({x}; {y}) cm, {angle}").format(
            ref=reference_label(pl.ref), x=format_cm(pl.x), y=format_cm(pl.y), angle=format_angle(pl.angle))
        if pl.mirrored:
            text += " — " + _("mirrored")
        if self.is_outside():
            text += " — " + _("OUTSIDE THE LAYOUT (negative x or y)")
        if self.collides_with:
            text += " — " + _("OVERLAPS {names}").format(names=", ".join(self.collides_with))
        return text

    # -- nœuds visibles quand la pièce est sélectionnée --------------------------
    def _set_nodes_visible(self, visible: bool):
        for it in self._node_items:
            it.setVisible(visible)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self._set_nodes_visible(bool(value))
        return super().itemChange(change, value)


class GridItem(QGraphicsItemGroup):
    """Cadres de coupe (pointillés), étiquettes Li-Cj et lettres d'assemblage des coins communs
    (une fois par coin, centrée sur le point ; le PDF la répète dans le coin de chaque feuille)."""

    def __init__(self, grid: Grid, colors: SceneColors):
        super().__init__()
        self.grid = grid
        self.setZValue(Z_GRID)
        # chaque frontière tracée une seule fois (deux rectangles superposés brouilleraient les pointillés)
        pen = cosmetic_pen(colors.cut_frame, Qt.DashLine)
        width, height = grid.extent
        xs = [0.0] + [grid.cell_rect(1, c)[2] for c in range(1, grid.cols + 1)]
        ys = [0.0] + [grid.cell_rect(r, 1)[3] for r in range(1, grid.rows + 1)]
        for x in xs:
            self.addToGroup(self._line(to_scene(x, 0.0), to_scene(x, height), pen))
        for y in ys:
            self.addToGroup(self._line(to_scene(0.0, y), to_scene(width, y), pen))

        font = QFont()
        font.setPointSizeF(10)
        for r, c in grid.cells():
            label = QGraphicsSimpleTextItem(Grid.label(r, c))
            label.setFont(font)
            label.setBrush(QColor(colors.cell_label))
            br = label.boundingRect()
            label.setScale(CELL_LABEL_HEIGHT_MM / br.height())
            x0, y0, x1, y1 = grid.cell_rect(r, c)
            centre = to_scene((x0 + x1) / 2, (y0 + y1) / 2)
            label.setPos(centre - QPointF(br.width(), br.height()) * label.scale() / 2)
            self.addToGroup(label)

        self.corner_labels = {}      # lettre → item, coordonnées du plan du coin en data(0)
        w, h = grid.settings.cell_size
        for (i, j), letter in grid.corner_letters().items():
            centre = to_scene(j * w, i * h)
            r = CORNER_DISC_RADIUS_MM
            disc = QGraphicsEllipseItem(QRectF(centre.x() - r, centre.y() - r, 2 * r, 2 * r))
            disc.setPen(cosmetic_pen(colors.cut_frame))
            disc.setBrush(QColor(colors.background))
            self.addToGroup(disc)
            label = QGraphicsSimpleTextItem(letter)
            label.setFont(font)
            label.setBrush(QColor(colors.cut_frame))
            br = label.boundingRect()
            label.setScale(CORNER_LETTER_HEIGHT_MM / br.height())
            label.setPos(centre - QPointF(br.width(), br.height()) * label.scale() / 2)
            label.setData(0, (j * w, i * h))
            self.addToGroup(label)
            self.corner_labels[letter] = label

    @staticmethod
    def _line(a: QPointF, b: QPointF, pen: QPen) -> QGraphicsLineItem:
        item = QGraphicsLineItem(QLineF(a, b))
        item.setPen(pen)
        return item

    def lines_plan(self) -> list[tuple[float, float, float, float]]:
        """Lignes de coupe affichées, en coordonnées du plan (x0, y0, x1, y1)."""
        out = []
        for it in self.childItems():
            if isinstance(it, QGraphicsLineItem):
                l = it.line()
                out.append((*to_plan(l.p1()), *to_plan(l.p2())))
        return out


class CuttingScene(QGraphicsScene):
    def __init__(self, parent=None, theme: str = "light"):
        super().__init__(parent)
        self.colors = SCENE_COLORS[theme]
        self.grid_item: GridItem | None = None
        self._axis_items = []
        self._draw_origin()
        self.setBackgroundBrush(QColor(self.colors.background))

    def _draw_origin(self):
        pen = cosmetic_pen(self.colors.axis, Qt.DashLine)
        self._axis_items = [self.addLine(0, 0, AXIS_LENGTH_MM, 0, pen), self.addLine(0, 0, 0, -AXIS_LENGTH_MM, pen)]
        label = self.addSimpleText("0")
        label.setBrush(QColor(self.colors.axis))
        br = label.boundingRect()
        label.setScale(ORIGIN_LABEL_HEIGHT_MM / br.height())
        label.setPos(-br.width() * label.scale() - 1.0, 1.0)
        self._axis_items.append(label)
        for it in self._axis_items:
            it.setZValue(Z_AXIS)

    def set_theme(self, theme: str):
        self.colors = SCENE_COLORS[theme]
        self.setBackgroundBrush(QColor(self.colors.background))
        for it in self._axis_items:
            self.removeItem(it)
        self._draw_origin()
        for it in self.pieces():
            it.set_colors(self.colors)
        if self.grid_item is not None:
            self.set_grid(self.grid_item.grid)

    def set_grid(self, grid: Grid | None):
        if self.grid_item is not None:
            self.removeItem(self.grid_item)
            self.grid_item = None
        if grid is not None:
            self.grid_item = GridItem(grid, self.colors)
            self.addItem(self.grid_item)

    def pieces(self) -> list[PieceItem]:
        return [it for it in self.items() if isinstance(it, PieceItem)]

    def add_piece(self, piece: Piece, placement: Placement) -> PieceItem:
        item = PieceItem(piece, placement, self.colors)
        self.addItem(item)
        self.update_collisions()
        return item

    def add_items(self, items: list[PieceItem]):
        """Remet des pièces existantes (annuler un retrait) aux couleurs du thème en cours."""
        for it in items:
            it.set_colors(self.colors)
            self.addItem(it)
        self.update_collisions()

    def remove_pieces(self, items: list[PieceItem]):
        for it in items:
            self.removeItem(it)
        self.update_collisions()

    def update_collisions(self) -> None:
        """Recalcule les chevauchements entre pièces (surface commune > COLLISION_TOL_MM2)."""
        items = sorted(self.pieces(), key=lambda it: it.piece.name)
        hits = {it: [] for it in items}
        paths = {it: it.plan_path() for it in items}
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if overlap_area(paths[a], paths[b]) > COLLISION_TOL_MM2:
                    hits[a].append(b.piece.name)
                    hits[b].append(a.piece.name)
        for it, names in hits.items():
            it.set_collisions(names)

    def clear_pieces(self):
        self.remove_pieces(self.pieces())
