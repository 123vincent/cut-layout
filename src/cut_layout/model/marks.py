"""Repère en T d'un nœud du contour (décision de Vincent, 25.11.2026). Sans Qt.

La pointe de la tige est sur le nœud ; la tige, perpendiculaire au contour, entre dans la pièce
(STEM_MM) ; la barre, parallèle au contour, la termine (BAR_MM) ; le nom du nœud est centré au-delà
de la barre (LABEL_DIST_MM du nœud). Le repère reste ainsi sur le gabarit découpé au contour.

Direction du contour au nœud : corde entre les points du contour situés à ±TANGENT_HALF_MM (longueur
d'arc) de part et d'autre du nœud. Sur une courbe régulière, c'est la tangente ; sur un angle du
contour, c'est la perpendiculaire à la bissectrice, et la tige suit alors la bissectrice.
Le sens « vers l'intérieur » est vérifié par un point d'essai dans le polygone.

Géométrie calculée dans le repère du brouillon, puis placée par la même transformation que le contour
(rotation, symétrie) : le T reste perpendiculaire au contour et du côté intérieur.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from ..i18n import _
from .clip import point_in_polygon
from .piece import Piece, Point
from .placement import Placement, to_plan

STEM_MM = 5.0
BAR_MM = 4.0
LABEL_DIST_MM = 8.0
TANGENT_HALF_MM = 2.0
INSIDE_PROBE_MM = 0.5


@dataclass(frozen=True)
class TeeMark:
    node: str
    stem: tuple[Point, Point]      # du nœud vers l'intérieur
    bar: tuple[Point, Point]
    label_at: Point                # centre du nom


def _project(outline, p: Point) -> tuple[int, float]:
    """Segment le plus proche du point et paramètre de la projection sur ce segment."""
    best = (math.inf, 0, 0.0)
    n = len(outline)
    for i in range(n):
        (ax, ay), (bx, by) = outline[i], outline[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / l2))
        d = math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)
        if d < best[0]:
            best = (d, i, t)
    return best[1], best[2]


def _point_at(outline, cumul: list[float], s: float) -> Point:
    """Point du contour fermé à l'abscisse curviligne s (modulo le périmètre)."""
    s %= cumul[-1]
    i = min(bisect.bisect_right(cumul, s) - 1, len(outline) - 1)
    (ax, ay), (bx, by) = outline[i], outline[(i + 1) % len(outline)]
    seg = cumul[i + 1] - cumul[i]
    t = 0.0 if seg == 0 else (s - cumul[i]) / seg
    return ax + t * (bx - ax), ay + t * (by - ay)


def tee_mark(piece: Piece, node: str) -> TeeMark:
    """Repère en T du nœud, dans le repère du brouillon (mm)."""
    try:
        p = piece.nodes[node]
    except KeyError:
        raise ValueError(_("unknown node for {piece!r}: {node!r}").format(piece=piece.name, node=node)) from None
    outline = piece.outline
    n = len(outline)
    cumul = [0.0]
    for i in range(n):
        cumul.append(cumul[-1] + math.dist(outline[i], outline[(i + 1) % n]))
    i, t = _project(outline, p)
    s = cumul[i] + t * (cumul[i + 1] - cumul[i])
    (ax, ay), (bx, by) = _point_at(outline, cumul, s - TANGENT_HALF_MM), _point_at(outline, cumul, s + TANGENT_HALF_MM)
    length = math.hypot(bx - ax, by - ay)
    tx, ty = (bx - ax) / length, (by - ay) / length
    nx, ny = -ty, tx
    if not point_in_polygon((p[0] + INSIDE_PROBE_MM * nx, p[1] + INSIDE_PROBE_MM * ny), list(outline)):
        nx, ny = -nx, -ny

    def at(d: float, w: float = 0.0) -> Point:
        return p[0] + d * nx + w * tx, p[1] + d * ny + w * ty
    return TeeMark(node, (p, at(STEM_MM)), (at(STEM_MM, -BAR_MM / 2), at(STEM_MM, BAR_MM / 2)),
                   at(LABEL_DIST_MM))


def placed_tee(piece: Piece, placement: Placement, node: str) -> TeeMark:
    """Repère en T placé sur le plan (mm)."""
    m = tee_mark(piece, node)

    def f(q: Point) -> Point:
        return to_plan(piece, placement, q)
    return TeeMark(node, (f(m.stem[0]), f(m.stem[1])), (f(m.bar[0]), f(m.bar[1])), f(m.label_at))


def placed_marks(piece: Piece, placement: Placement) -> list[TeeMark]:
    return [placed_tee(piece, placement, node) for node in placement.marks]
