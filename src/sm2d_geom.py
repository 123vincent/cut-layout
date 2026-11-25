"""Reconstruction de la géométrie d'un fichier Seamly2D (.sm2d) à partir de ses formules.

Convention : repère mathématique (y vers le haut), angles en degrés, 0° = droite,
90° = haut (comme dans les formules Seamly2D). Unité interne = unité du fichier (cm).
Les fichiers lus sont traités comme des données non fiables : les formules sont
filtrées avant évaluation.
"""
from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_SAFE = re.compile(r"^[A-Za-z0-9_+\-*/().,\s]*$")
_ATTR = re.compile(r"\.[A-Za-z_]")


def _sign(v: float) -> float:
    return 1.0 if v > 0 else -1.0 if v < 0 else 0.0


def _rint(v: float) -> float:
    """Entier le plus proche ; demi-entiers arrondis vers +∞ (floor(v + 0,5)). Comportement exact de
    Seamly2D pour les demi-entiers négatifs : INCONNU (non vérifié)."""
    return float(math.floor(v + 0.5))


# Fonctions des formules Seamly2D (wiki Seamly2D, liste transmise par Vincent le 25.11.2026).
# Modification du module validé (25.11.2026, signalée) : sin, cos, tan étaient calculés en degrés ;
# dans Seamly2D ils travaillent en RADIANS (exemple du wiki : sin(90) = 0,893997) et les versions en
# degrés portent le suffixe D (sinD, asinD…). Noms sensibles à la casse, comme dans Seamly2D.
# Aucune formule de l'échantillon validé n'utilise de fonction trigonométrique : résultats inchangés.
_FUNCS = {
    # générales
    "abs": abs, "sqrt": math.sqrt, "exp": math.exp, "ln": math.log, "log": math.log10,
    "log10": math.log10, "log2": math.log2, "sign": _sign, "rint": _rint,
    "min": lambda *a: min(a), "max": lambda *a: max(a), "sum": lambda *a: math.fsum(a),
    "avg": lambda *a: math.fsum(a) / len(a),
    # trigonométriques en radians
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    # trigonométriques en degrés
    "sinD": lambda a: math.sin(math.radians(a)), "cosD": lambda a: math.cos(math.radians(a)),
    "tanD": lambda a: math.tan(math.radians(a)),
    "asinD": lambda v: math.degrees(math.asin(v)), "acosD": lambda v: math.degrees(math.acos(v)),
    "atanD": lambda v: math.degrees(math.atan(v)),
    # hyperboliques
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "asinh": math.asinh, "acosh": math.acosh, "atanh": math.atanh,
    # conversions et constante
    "radTodeg": math.degrees, "degTorad": math.radians, "_pi": math.pi,
}
FUNCTION_NAMES = frozenset(k for k, v in _FUNCS.items() if callable(v))


def direction(angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return math.cos(a), math.sin(a)


def bezier_point(p0, p1, p2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def bezier_polyline(p0, p1, p2, p3, n=400):
    return [bezier_point(p0, p1, p2, p3, i / n) for i in range(n + 1)]


def polyline_length(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def bezier_length(p0, p1, p2, p3):
    """Longueur d'arc (polyligne fine + extrapolation de Richardson)."""
    l1 = polyline_length(bezier_polyline(p0, p1, p2, p3, 4000))
    l2 = polyline_length(bezier_polyline(p0, p1, p2, p3, 8000))
    return l2 + (l2 - l1) / 3


@dataclass
class Curve:
    name: str
    kind: str                 # "simple" ou "path"
    segments: list            # liste de (p0, p1, p2, p3)
    nodes: list               # noms des points de passage
    cached_length: float | None = None

    @property
    def length(self) -> float:
        return sum(bezier_length(*s) for s in self.segments)

    def sample(self, n=200):
        pts = []
        for s in self.segments:
            seg = bezier_polyline(*s, n=n)
            pts.extend(seg if not pts else seg[1:])
        return pts


class Namespace(dict):
    """Résolution paresseuse de Line_X_Y, AngleLine_X_Y, Spl_X_Y, SplPath_X_Y."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def __missing__(self, key):
        m = self.model
        if key.startswith("AngleLine_"):
            _, a, b = key.split("_")
            (x1, y1), (x2, y2) = m.pt[a], m.pt[b]
            return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360
        if key.startswith("Line_"):
            _, a, b = key.split("_")
            return math.dist(m.pt[a], m.pt[b])
        if key in m.curves:
            return m.curves[key].length
        if key == "CurrentLength" and m.current_length is not None:
            return m.current_length
        raise KeyError(f"identifiant inconnu : {key}")


class Model:
    def __init__(self, sm2d_path: str, smis_path: str, overrides: dict | None = None):
        self.overrides = overrides or {}
        self.pt: dict[str, tuple[float, float]] = {}
        self.pt_by_id: dict[str, str] = {}
        self.curves: dict[str, Curve] = {}
        self.curve_by_id: dict[str, Curve] = {}
        self.current_length = None
        self.ns = Namespace(self)
        self._load_measurements(smis_path)
        self.root = ET.parse(sm2d_path).getroot()
        self.unit = self.root.findtext("unit")
        self._load_variables()
        self.blocks = {}
        for blk in self.root.findall("draftBlock"):
            self._build_block(blk)

    # -- formules ---------------------------------------------------------
    def ev(self, formula: str) -> float:
        # « ; » : séparateur d'arguments de Seamly2D (ex. min(a; b)) ; « , » reste accepté.
        # Séparateur réellement écrit dans les .sm2d : INCONNU (aucune fonction à plusieurs
        # arguments dans l'échantillon) — à vérifier sur un fichier enregistré par Seamly2D.
        expr = formula.strip().replace("#", "V__").replace("^", "**").replace(";", ",")
        if not _SAFE.match(expr) or _ATTR.search(expr) or "__" in expr.replace("V__", ""):
            raise ValueError(f"formule refusée : {formula!r}")
        return float(eval(expr, {"__builtins__": {}}, _Env(self.ns)))

    def _load_measurements(self, path):
        root = ET.parse(path).getroot()
        for m in root.iter("m"):
            self.ns[m.get("name")] = float(m.get("value"))

    def _load_variables(self):
        for v in self.root.find("variables"):
            key = v.get("name")
            formula = self.overrides.get(key, v.get("formula"))
            self.ns["V__" + key.lstrip("#")] = self.ev(formula)

    # -- construction -----------------------------------------------------
    def _build_block(self, blk):
        calc = blk.find("calculation")
        for el in calc:
            if el.tag == "point":
                self._point(el)
            elif el.tag == "spline":
                self._spline(el)
        self.blocks[blk.get("name")] = blk
        # table modeling : id -> (id objet de calcul)
        self._modeling = getattr(self, "_modeling", {})
        for el in blk.find("modeling"):
            self._modeling[el.get("id")] = el.get("idObject")

    def _point(self, el):
        t, name = el.get("type"), el.get("name")
        if t == "single":
            p = (float(el.get("x")), -float(el.get("y")))  # scène : y vers le bas
        elif t == "endLine":
            b = self.pt[self.pt_by_id[el.get("basePoint")]]
            d = direction(self.ev(el.get("angle")))
            n = self.ev(el.get("length"))
            p = (b[0] + n * d[0], b[1] + n * d[1])
        elif t == "alongLine":
            a = self.pt[self.pt_by_id[el.get("firstPoint")]]
            b = self.pt[self.pt_by_id[el.get("secondPoint")]]
            self.current_length = math.dist(a, b)
            n = self.ev(el.get("length"))
            self.current_length = None
            p = (a[0] + n * (b[0] - a[0]) / math.dist(a, b), a[1] + n * (b[1] - a[1]) / math.dist(a, b))
        elif t == "intersectXY":
            a = self.pt[self.pt_by_id[el.get("firstPoint")]]
            b = self.pt[self.pt_by_id[el.get("secondPoint")]]
            p = (a[0], b[1])
        else:
            raise NotImplementedError(f"type de point non géré : {t}")
        self.pt[name] = p
        self.pt_by_id[el.get("id")] = name

    def _ctrl(self, base, angle, length):
        d = direction(self.ev(angle))
        n = self.ev(length)
        return (base[0] + n * d[0], base[1] + n * d[1])

    def _spline(self, el):
        t = el.get("type")
        cached = float(el.get("length")) if el.get("length") else None
        if t == "simpleInteractive":
            n1, n4 = self.pt_by_id[el.get("point1")], self.pt_by_id[el.get("point4")]
            p1, p4 = self.pt[n1], self.pt[n4]
            p2 = self._ctrl(p1, el.get("angle1"), el.get("length1"))
            p3 = self._ctrl(p4, el.get("angle2"), el.get("length2"))
            c = Curve(f"Spl_{n1}_{n4}", "simple", [(p1, p2, p3, p4)], [n1, n4], cached)
        elif t == "pathInteractive":
            nodes = []
            for pp in el.findall("pathPoint"):
                nm = self.pt_by_id[pp.get("pSpline")]
                base = self.pt[nm]
                nodes.append((nm, base,
                              self._ctrl(base, pp.get("angle1"), pp.get("length1")),
                              self._ctrl(base, pp.get("angle2"), pp.get("length2"))))
            segs = [(nodes[i][1], nodes[i][3], nodes[i + 1][2], nodes[i + 1][1])
                    for i in range(len(nodes) - 1)]
            c = Curve(f"SplPath_{nodes[0][0]}_{nodes[-1][0]}", "path", segs,
                      [n[0] for n in nodes], cached)
        else:
            raise NotImplementedError(f"type de courbe non géré : {t}")
        self.curves[c.name] = c
        self.curve_by_id[el.get("id")] = c

    # -- pièces -----------------------------------------------------------
    def piece_outline(self, piece, n=200):
        """Contour net (sans marge de couture), polygone fermé."""
        out = []

        def add(p):
            if not out or math.dist(out[-1], p) > 1e-9:
                out.append(p)

        for node in piece.find("nodes"):
            obj = self._modeling[node.get("idObject")]
            typ = node.get("type")
            if typ == "NodePoint":
                add(self.pt[self.pt_by_id[obj]])
            elif typ in ("NodeSpline", "NodeSplinePath"):
                pts = self.curve_by_id[obj].sample(n)
                if node.get("reverse") == "1":
                    pts = pts[::-1]
                for p in pts:
                    add(p)
            else:
                raise NotImplementedError(typ)
        if math.dist(out[0], out[-1]) < 1e-9:
            out.pop()
        return out

    def pieces(self):
        for name, blk in self.blocks.items():
            for pc in blk.find("pieces"):
                yield name, pc


class _Env(dict):
    """Locals d'eval : fonctions + espace de noms paresseux."""

    def __init__(self, ns):
        super().__init__()
        self.ns = ns

    def __missing__(self, key):
        if key in _FUNCS:
            return _FUNCS[key]
        return self.ns[key]


def polygon_area(pts):
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2
