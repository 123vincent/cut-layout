"""Découpage géométrique des contours par un rectangle. Sans Qt.

Le tracé est découpé ici, en Python, plutôt que par un masque PDF : le PDF ne contient
alors que des coordonnées situées dans la zone imprimée, ce qui se vérifie en relisant le fichier.
"""
from __future__ import annotations

from .mosaic import Rect
from .piece import Point

EPS = 1e-9


def clip_segment(p: Point, q: Point, rect: Rect) -> tuple[Point, Point] | None:
    """Liang-Barsky : partie du segment [p, q] dans le rectangle fermé, ou None."""
    x0, y0, x1, y1 = rect
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pk == 0:
            if qk < 0:
                return None
        else:
            t = qk / pk
            if pk < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return None
    a = (p[0] + t0 * dx, p[1] + t0 * dy) if t0 > 0 else p
    b = (p[0] + t1 * dx, p[1] + t1 * dy) if t1 < 1 else q
    return a, b


def clip_closed_polyline(pts: list[Point], rect: Rect) -> list[list[Point]]:
    """Parties d'un contour fermé situées dans le rectangle, en polylignes ouvertes."""
    n = len(pts)
    pieces: list[list[Point]] = []
    current: list[Point] = []
    for i in range(n):
        seg = clip_segment(pts[i], pts[(i + 1) % n], rect)
        if seg is None:
            if current:
                pieces.append(current)
                current = []
            continue
        a, b = seg
        if current and abs(current[-1][0] - a[0]) < EPS and abs(current[-1][1] - a[1]) < EPS:
            current.append(b)
        else:
            if current:
                pieces.append(current)
            current = [a, b]
    if current:
        pieces.append(current)
    # le contour est fermé : raccorder la dernière polyligne à la première si elles se touchent
    if len(pieces) > 1:
        first, last = pieces[0], pieces[-1]
        if abs(last[-1][0] - first[0][0]) < EPS and abs(last[-1][1] - first[0][1]) < EPS:
            pieces[0] = last + first[1:]
            pieces.pop()
    return pieces


def point_in_rect(p: Point, rect: Rect) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= p[0] <= x1 and y0 <= p[1] <= y1


def point_in_polygon(p: Point, pts: list[Point]) -> bool:
    x, y = p
    inside = False
    n = len(pts)
    for i in range(n):
        (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % n]
        if (ya > y) != (yb > y) and x < xa + (y - ya) * (xb - xa) / (yb - ya):
            inside = not inside
    return inside


def polygon_touches_rect(pts: list[Point], rect: Rect, margin: float = 1e-6) -> bool:
    """Vrai si la pièce (polygone plein) a une partie strictement à l'intérieur du rectangle.

    Le rectangle est réduit de `margin` : une pièce qui ne fait que toucher la frontière
    d'une cellule ne rend pas cette cellule non vide.
    """
    x0, y0, x1, y1 = rect
    inner = (x0 + margin, y0 + margin, x1 - margin, y1 - margin)
    n = len(pts)
    if any(clip_segment(pts[i], pts[(i + 1) % n], inner) for i in range(n)):
        return True
    return point_in_polygon(((x0 + x1) / 2, (y0 + y1) / 2), pts)   # cellule entièrement dans la pièce
