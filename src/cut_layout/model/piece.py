"""Pièce importée : contour net en mm, repère mathématique (y vers le haut). Sans Qt."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..i18n import _

Point = tuple[float, float]


def polygon_area(pts: list[Point] | tuple[Point, ...]) -> float:
    """Aire signée (positive si le contour tourne dans le sens trigonométrique)."""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2


def polygon_centroid(pts: list[Point] | tuple[Point, ...]) -> Point:
    """Centre de gravité de la surface du polygone (pas la moyenne des sommets)."""
    a = polygon_area(pts)
    if a == 0:
        raise ValueError(_("zero-area polygon: centroid undefined"))
    cx = cy = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        c = x1 * y2 - x2 * y1
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    return cx / (6 * a), cy / (6 * a)


@dataclass(frozen=True)
class Piece:
    """Contour net (ligne de couture, sans marge), dans le repère du brouillon, en mm.

    `outline` est un polygone fermé implicitement (le dernier point n'est pas répété).
    `nodes` : points nommés de la pièce situés sur le contour (nœuds de pièce et
    points de passage de ses courbes), en mm.
    """

    name: str
    block: str
    outline: tuple[Point, ...]
    nodes: dict[str, Point] = field(default_factory=dict)
    on_fold: bool = False
    forbid_flipping: bool = False    # attribut forbidFlipping du .sm2d : symétrie interdite

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.outline]
        ys = [p[1] for p in self.outline]
        return min(xs), min(ys), max(xs), max(ys)

    @property
    def width(self) -> float:
        b = self.bbox
        return b[2] - b[0]

    @property
    def height(self) -> float:
        b = self.bbox
        return b[3] - b[1]

    @property
    def area(self) -> float:
        return abs(polygon_area(self.outline))

    @property
    def centroid(self) -> Point:
        return polygon_centroid(self.outline)
