"""Mosaïque de feuilles : format, marges, grille de cellules. Sans Qt.

Vocabulaire (PROMPT §3 bis) :
- marge d'assemblage : distance du bord de la feuille au cadre de coupe ; les feuilles sont
  découpées le long du cadre et jointes bout à bout ;
- marge d'impression : zone non imprimable de l'imprimante, depuis le bord de la feuille ;
- cellule : le cadre de coupe ; le plan de coupe est le pavage sans trou des cellules.

Repère du plan : origine au coin inférieur gauche de la cellule L1-C1, x vers la droite,
y vers le haut, mm. Ligne 1 en bas, colonne 1 à gauche.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Iterator

from ..i18n import _, fmt_g
from .piece import Point

# Formats standard, portrait (petit côté × grand côté), mm : ISO 216 et formats nord-américains (ANSI).
SHEET_SIZES_MM = {
    "A4": (210.0, 297.0), "A3": (297.0, 420.0), "A2": (420.0, 594.0), "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
    "Letter": (215.9, 279.4), "Legal": (215.9, 355.6), "Tabloid": (279.4, 431.8),
}
CUSTOM = "custom"                     # format personnalisé : dimensions données par l'utilisateur
FORMATS = tuple(SHEET_SIZES_MM) + (CUSTOM,)
CUSTOM_RANGE_MM = (50.0, 5000.0)      # bornes d'un format personnalisé (chaque côté)
ORIENTATIONS = ("portrait", "landscape")


def orientation_label(orientation: str) -> str:
    return {"portrait": _("portrait"), "landscape": _("landscape")}.get(orientation, orientation)


def format_label(fmt: str) -> str:
    return _("Custom") if fmt == CUSTOM else {"Letter": "US Letter", "Legal": "US Legal"}.get(fmt, fmt)


FIT_TOL_MM = 1e-6    # une pièce qui touche une frontière à 1e-6 mm près n'ajoute pas de feuille

Rect = tuple[float, float, float, float]   # x0, y0, x1, y1


class MosaicError(ValueError):
    pass


@dataclass(frozen=True)
class SheetSettings:
    format: str = "A4"
    orientation: str = "portrait"
    assembly_margin: float = 10.0     # mm
    print_margin: float = 5.0         # mm, réglage de l'imprimante (préférences)
    # format personnalisé seulement : dimensions en mm, dans n'importe quel ordre ; le petit côté
    # est toujours la largeur en portrait (comme les formats standard et la correction d'imprimante :
    # x = petit côté du papier)
    custom_width: float = 0.0
    custom_height: float = 0.0

    def __post_init__(self):
        if self.format not in FORMATS:
            raise MosaicError(_("unknown format: {value!r} (possible: {choices})").format(
                value=self.format, choices=", ".join(FORMATS)))
        if self.format == CUSTOM:
            lo, hi = CUSTOM_RANGE_MM
            if not all(lo <= v <= hi for v in (self.custom_width, self.custom_height)):
                raise MosaicError(_("custom format: each side must be between {min} and {max} mm").format(
                    min=fmt_g(lo), max=fmt_g(hi)))
        if self.orientation not in ORIENTATIONS:
            raise MosaicError(_("unknown orientation: {value!r} (possible: {choices})").format(
                value=self.orientation, choices=", ".join(ORIENTATIONS)))
        if self.print_margin < 0:
            raise MosaicError(_("the print margin cannot be negative"))
        if self.print_margin >= self.assembly_margin:
            raise MosaicError(_("the print margin ({print} mm) must be smaller than the assembly margin "
                                "({assembly} mm)").format(print=fmt_g(self.print_margin),
                                                          assembly=fmt_g(self.assembly_margin)))
        w, h = self.cell_size
        if w <= 0 or h <= 0:
            raise MosaicError(_("assembly margin too large for the sheet format"))

    @property
    def portrait_size(self) -> tuple[float, float]:
        """(petit côté, grand côté), mm."""
        if self.format == CUSTOM:
            return tuple(sorted((self.custom_width, self.custom_height)))
        return SHEET_SIZES_MM[self.format]

    @property
    def sheet_size(self) -> tuple[float, float]:
        w, h = self.portrait_size
        return (w, h) if self.orientation == "portrait" else (h, w)

    @property
    def cell_size(self) -> tuple[float, float]:
        w, h = self.sheet_size
        return w - 2 * self.assembly_margin, h - 2 * self.assembly_margin

    @property
    def bleed(self) -> float:
        """Largeur imprimée au-delà du cadre de coupe, de chaque côté."""
        return self.assembly_margin - self.print_margin

    def describe(self) -> str:
        if self.format == CUSTOM:
            w, h = self.portrait_size
            return _("custom {w} × {h} mm {orientation}").format(
                w=fmt_g(w), h=fmt_g(h), orientation=orientation_label(self.orientation))
        return f"{format_label(self.format)} {orientation_label(self.orientation)}"


@dataclass(frozen=True)
class Grid:
    settings: SheetSettings
    rows: int
    cols: int

    def __post_init__(self):
        if self.rows < 1 or self.cols < 1:
            raise MosaicError(_("the grid needs at least one row and one column"))

    @property
    def count(self) -> int:
        return self.rows * self.cols

    @property
    def extent(self) -> tuple[float, float]:
        w, h = self.settings.cell_size
        return self.cols * w, self.rows * h

    def _check(self, row: int, col: int):
        if not (1 <= row <= self.rows and 1 <= col <= self.cols):
            raise MosaicError(_("cell {label} outside the {rows} × {cols} grid").format(
                label=self.label(row, col), rows=self.rows, cols=self.cols))

    def cell_rect(self, row: int, col: int) -> Rect:
        """Cadre de coupe de la cellule, en coordonnées du plan."""
        self._check(row, col)
        w, h = self.settings.cell_size
        return (col - 1) * w, (row - 1) * h, col * w, row * h

    def printed_rect(self, row: int, col: int) -> Rect:
        """Portion du plan imprimée sur la page : cellule élargie de la bande d'impression."""
        x0, y0, x1, y1 = self.cell_rect(row, col)
        b = self.settings.bleed
        return x0 - b, y0 - b, x1 + b, y1 + b

    def plan_to_sheet(self, row: int, col: int, p: Point) -> Point:
        """Point du plan → coordonnées sur la feuille (origine au coin inférieur gauche de la feuille, y vers le haut)."""
        x0, y0 = self.cell_rect(row, col)[:2]
        a = self.settings.assembly_margin
        return p[0] - x0 + a, p[1] - y0 + a

    def cells(self) -> Iterator[tuple[int, int]]:
        """Cellules ligne par ligne, depuis la ligne 1 (en bas), colonne 1 à gauche."""
        for r in range(1, self.rows + 1):
            for c in range(1, self.cols + 1):
                yield r, c

    def corner_letters(self) -> dict[tuple[int, int], str]:
        """Lettres des coins communs à au moins deux cellules (repères d'assemblage).

        Clé (i, j) : coin au point (j·w ; i·h) du plan, i = 0…rows, j = 0…cols. Les quatre coins
        extérieurs de la grille (une seule cellule) n'ont pas de lettre. Ordre : ligne par ligne
        depuis le bas, de gauche à droite, comme les pages.
        """
        letters = {}
        for i in range(self.rows + 1):
            for j in range(self.cols + 1):
                # cellules (r, c) dont le coin (i, j) est un sommet : r ∈ {i, i + 1}, c ∈ {j, j + 1}, dans la grille
                shared = (sum(1 <= r <= self.rows for r in (i, i + 1))
                          * sum(1 <= c <= self.cols for c in (j, j + 1)))
                if shared >= 2:
                    letters[(i, j)] = column_letters(len(letters))
        return letters

    def cell_corner_letters(self, row: int, col: int) -> dict[str, str]:
        """Lettres des coins d'une cellule : clés « bl », « br », « tl », « tr » (bas/haut, gauche/droite)."""
        self._check(row, col)
        letters = self.corner_letters()
        corners = {"bl": (row - 1, col - 1), "br": (row - 1, col), "tl": (row, col - 1), "tr": (row, col)}
        return {name: letters[key] for name, key in corners.items() if key in letters}

    @staticmethod
    def label(row: int, col: int) -> str:
        # TRANSLATORS: page mark printed on each sheet, R = row, C = column (French: L = ligne)
        return _("R{row}-C{col}").format(row=row, col=col)


def column_letters(n: int) -> str:
    """0 → A, 25 → Z, 26 → AA, 27 → AB… (comme les colonnes d'un tableur)."""
    text = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        text = chr(ord("A") + r) + text
    return text


def fit_grid(settings: SheetSettings, bboxes: Iterable[Rect]) -> Grid:
    """Plus petite grille (depuis l'origine) qui couvre les parties positives des boîtes englobantes.

    Les parties en x < 0 ou y < 0 ne sont pas couvertes (signalées par ailleurs). Au moins 1 × 1.
    """
    w, h = settings.cell_size
    max_x = max_y = 0.0
    for bbox in bboxes:
        max_x, max_y = max(max_x, bbox[2]), max(max_y, bbox[3])
    cols = max(1, math.ceil((max_x - FIT_TOL_MM) / w))
    rows = max(1, math.ceil((max_y - FIT_TOL_MM) / h))
    return Grid(settings, rows, cols)
