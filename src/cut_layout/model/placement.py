"""Placement d'une pièce sur le plan de coupe. Sans Qt.

Repère du plan : origine au coin inférieur gauche du cadre de coupe de la cellule L1-C1,
x vers la droite, y vers le haut, en mm.

Une pièce est placée par un point de référence (barycentre de surface ou nœud nommé),
la position (x, y) de ce point sur le plan, et un angle de rotation autour de ce point
(degrés, sens trigonométrique : positif = antihoraire).

Symétrie (`mirrored`) : la pièce est d'abord retournée par rapport à l'axe vertical du brouillon passant
par le point de référence, puis tournée. L'angle garde ainsi son sens (positif = antihoraire à l'écran)
que la pièce soit retournée ou non. `toggle_mirror` retourne la pièce telle qu'elle est vue sur le plan
(axe vertical du plan passant par le point de référence) : M·R(θ) = R(−θ)·M, donc l'angle change de signe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..i18n import _
from .piece import Piece, Point

REF_CENTROID = "centroid"     # identifiant interne ; libellé affiché : reference_label()
TOL_MM = 1e-9      # tolérance de détection d'une pièce hors du plan (erreurs d'arrondi)


@dataclass(frozen=True)
class Placement:
    ref: str = REF_CENTROID     # REF_CENTROID ou nom d'un nœud de la pièce
    x: float = 0.0              # position du point de référence sur le plan, mm
    y: float = 0.0
    angle: float = 0.0          # degrés, sens trigonométrique
    mirrored: bool = False      # symétrie par rapport à l'axe vertical, appliquée avant la rotation
    marks: tuple[str, ...] = ()  # nœuds marqués d'un T (model/marks.py) ; portés ici pour être enregistrés,
                                 # annulés et comparés avec le reste des propriétés de la pièce


def normalize_angle(a: float) -> float:
    """Ramène un angle dans ]-180 ; 180]."""
    a = math.fmod(a, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def rotation(angle_deg: float) -> tuple[float, float]:
    """(cos, sin), exacts pour les multiples de 90° (pas de résidu en 1e-17)."""
    q = angle_deg / 90.0
    if q == int(q):
        return ((1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0))[int(q) % 4]
    a = math.radians(angle_deg)
    return math.cos(a), math.sin(a)


def reference_point(piece: Piece, ref: str) -> Point:
    """Point de référence dans le repère du brouillon (mm)."""
    if ref == REF_CENTROID:
        return piece.centroid
    try:
        return piece.nodes[ref]
    except KeyError:
        raise ValueError(_("unknown reference point for {piece!r}: {ref!r}").format(
            piece=piece.name, ref=ref)) from None


def reference_label(ref: str) -> str:
    """Libellé affiché d'un point de référence (nom du nœud, ou « barycentre » traduit)."""
    return _("centroid") if ref == REF_CENTROID else ref


def affine(piece: Piece, placement: Placement) -> tuple[float, float, float, float, float, float]:
    """Transformation brouillon → plan : (a, b, c, d, e, f) avec
    X = a·x + b·y + e ;  Y = c·x + d·y + f.
    Matrice : R(angle) · diag(−1, 1) si la pièce est retournée, R(angle) sinon."""
    cos, sin = rotation(placement.angle)
    m = -1.0 if placement.mirrored else 1.0
    a, b, c, d = m * cos, -sin, m * sin, cos
    rx, ry = reference_point(piece, placement.ref)
    return a, b, c, d, placement.x - (a * rx + b * ry), placement.y - (c * rx + d * ry)


def to_plan(piece: Piece, placement: Placement, p: Point) -> Point:
    a, b, c, d, e, f = affine(piece, placement)
    return a * p[0] + b * p[1] + e, c * p[0] + d * p[1] + f


def placed_outline(piece: Piece, placement: Placement) -> list[Point]:
    a, b, c, d, e, f = affine(piece, placement)
    return [(a * x + b * y + e, c * x + d * y + f) for x, y in piece.outline]


def placed_bbox(piece: Piece, placement: Placement) -> tuple[float, float, float, float]:
    pts = placed_outline(piece, placement)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def change_reference(piece: Piece, placement: Placement, ref: str) -> Placement:
    """Même position de la pièce sur le plan, autre point de référence."""
    x, y = to_plan(piece, placement, reference_point(piece, ref))
    return replace(placement, ref=ref, x=x, y=y)


def toggle_mirror(placement: Placement) -> Placement:
    """Retourne la pièce par rapport à l'axe vertical du plan passant par le point de référence
    (le point de référence ne bouge pas)."""
    return replace(placement, mirrored=not placement.mirrored, angle=normalize_angle(-placement.angle))


def placement_at_corner(piece: Piece, x: float, y: float, angle: float = 0.0,
                        ref: str = REF_CENTROID) -> Placement:
    """Placement dont le coin inférieur gauche de la boîte englobante est en (x, y)."""
    p0 = Placement(ref=ref, x=0.0, y=0.0, angle=angle)
    x0, y0 = placed_bbox(piece, p0)[:2]
    return replace(p0, x=x - x0, y=y - y0)


def outside_plan(piece: Piece, placement: Placement) -> bool:
    """Vrai si une partie de la pièce est en x < 0 ou y < 0 (hors de la grille)."""
    x0, y0 = placed_bbox(piece, placement)[:2]
    return x0 < -TOL_MM or y0 < -TOL_MM
