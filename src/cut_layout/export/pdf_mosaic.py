"""Export PDF de la mosaïque à l'échelle 1:1. Sans Qt.

Première page (si `overview`) : plan de montage, vue d'ensemble réduite (grille, repères, lettres
des coins, pièces nommées, feuilles vides grisées), échelle indiquée — pas à l'échelle 1:1.
Puis une page par cellule contenant une partie de pièce (pages vides omises), ligne par ligne
depuis L1-C1. Sur chaque page :
- le tracé des pièces dans la zone imprimée (cellule élargie de la bande, découpé en Python) ;
- le cadre de coupe en pointillés, à la marge d'assemblage ;
- le repère « Li-Cj » (anglais « Ri-Cj ») dans la bande du bas, hors du cadre (part avec la chute) ;
- les repères en T des nœuds marqués (découpés comme le contour), le nom du nœud s'il tombe dans la
  zone imprimée ;
- une lettre dans chaque coin commun à plusieurs feuilles (`Grid.corner_letters`), à l'intérieur du
  cadre pour rester sur la feuille découpée : à l'assemblage, les coins de même lettre se rejoignent.
Toujours noir sur blanc, quel que soit le thème de l'écran.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import _, fmt
from ..model.clip import clip_closed_polyline, clip_segment, point_in_rect, polygon_touches_rect
from ..model.marks import TeeMark
from ..model.correction import NO_CORRECTION, PrintCorrection
from ..model.mosaic import Grid
from ..model.piece import Point, polygon_centroid
from .pdf_common import begin_page, end_page, fit_text, new_canvas, polyline, set_font

PIECE_LINE_MM = 0.3
FRAME_LINE_MM = 0.2
FRAME_DASH_MM = (3.0, 2.0)
LABEL_SIZE_PT = 8
LABEL_OFFSET_MM = 2.0          # depuis le coin du cadre, le long du bord du bas
CORNER_LETTER_SIZE_PT = 10
CORNER_INSET_MM = 1.5          # distance de la lettre aux deux bords du cadre, vers l'intérieur
CAP_HEIGHT = 0.72              # hauteur des majuscules d'Helvetica, en fraction du corps
MARK_LINE_MM = 0.3
MARK_LABEL_SIZE_PT = 7
OVERVIEW_MARGIN_MM = 15.0
OVERVIEW_HEADER_MM = 34.0      # titre, nom du patron et légende, en haut de la page
OVERVIEW_EMPTY_GREY = 0.88     # remplissage des feuilles vides (non imprimées)
OVERVIEW_LABEL_GREY = 0.55
OVERVIEW_LETTER_RADIUS_MM = 2.6


@dataclass
class ExportReport:
    path: Path
    pages: list[tuple[int, int]] = field(default_factory=list)      # dans l'ordre du PDF
    omitted: list[tuple[int, int]] = field(default_factory=list)
    overview: bool = False       # première page = plan de montage
    overview_scale: float = 0.0  # plan → page de montage (ex. 0,2 = 1:5)


def _corner_letters(c, letters: dict[str, str], a: float, W: float, H: float):
    set_font(c, CORNER_LETTER_SIZE_PT, bold=True)
    cap = CORNER_LETTER_SIZE_PT * 25.4 / 72 * CAP_HEIGHT
    left, right = a + CORNER_INSET_MM, W - a - CORNER_INSET_MM
    bottom, top = a + CORNER_INSET_MM, H - a - CORNER_INSET_MM - cap
    for corner, letter in letters.items():
        y = bottom if corner[0] == "b" else top
        if corner[1] == "l":
            c.drawString(left, y, letter)
        else:
            c.drawRightString(right, y, letter)


def _overview(c, grid: Grid, outlines, name: str, omitted: set[tuple[int, int]]) -> float:
    """Plan de montage sur une page du format des feuilles, dans l'orientation qui donne la plus
    grande échelle ; renvoie l'échelle plan → page."""
    s = grid.settings
    m = OVERVIEW_MARGIN_MM
    ext_w, ext_h = grid.extent
    xs = [0.0, ext_w] + [x for _name, pts in outlines for x, _y in pts]
    ys = [0.0, ext_h] + [y for _name, pts in outlines for _x, y in pts]
    x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)

    def fit(size):
        area_w, area_h = size[0] - 2 * m, size[1] - 2 * m - OVERVIEW_HEADER_MM
        return min(area_w / (x_max - x_min), area_h / (y_max - y_min)), area_w, area_h
    short, long = sorted(s.sheet_size)
    W, H = max([(short, long), (long, short)], key=lambda size: fit(size)[0])
    k, area_w, area_h = fit((W, H))
    ox = m + (area_w - k * (x_max - x_min)) / 2 - k * x_min
    oy = m + (area_h - k * (y_max - y_min)) / 2 - k * y_min

    def page(p: Point) -> Point:
        return ox + k * p[0], oy + k * p[1]

    begin_page(c, (W, H))
    width = W - 2 * m
    y = H - m - 5
    set_font(c, 13, bold=True)
    c.drawString(m, y, _("Assembly plan"))
    if name:      # nom du patron sur sa propre ligne, réduit ou raccourci s'il dépasse la largeur
        text, size = fit_text(c, name, width, 10)
        y -= 5.5
        set_font(c, size)
        c.drawString(m, y, text)
    y -= 6
    lines = [(_("Scale 1:{ratio} — do not measure on this page").format(ratio=fmt(1 / k, 1)), True),
             (_("{rows} × {cols} sheets {sheet}; grey: empty sheet, not printed.").format(
                 rows=grid.rows, cols=grid.cols, sheet=s.describe()), False),
             (_("Cut each sheet along its dashed frame, then join the corners bearing the same letter."), False)]
    for line, bold in lines:
        text, size = fit_text(c, line, width, 9, bold)
        set_font(c, size, bold)
        c.drawString(m, y, text)
        y -= 4.5

    w, h = s.cell_size
    c.setLineWidth(0.25)
    for r, col in grid.cells():
        x0, y0 = page(grid.cell_rect(r, col)[:2])
        c.setFillGray(OVERVIEW_EMPTY_GREY if (r, col) in omitted else 1.0)
        c.rect(x0, y0, k * w, k * h, stroke=1, fill=1)
    c.setFillGray(OVERVIEW_LABEL_GREY)
    set_font(c, min(14.0, k * h / 4 / (25.4 / 72)), bold=True)
    for r, col in grid.cells():
        x0, y0, x1, y1 = grid.cell_rect(r, col)
        cx, cy = page(((x0 + x1) / 2, (y0 + y1) / 2))
        c.drawCentredString(cx, cy, Grid.label(r, col))

    c.setFillGray(0.0)
    c.setLineWidth(PIECE_LINE_MM)
    set_font(c, 8)
    for name, pts in outlines:
        polyline(c, [page(p) for p in pts], close=True)
        cx, cy = page(polygon_centroid(pts))
        c.drawCentredString(cx, cy, name)

    set_font(c, 7, bold=True)
    c.setLineWidth(0.25)
    r_disc = OVERVIEW_LETTER_RADIUS_MM
    for (i, j), letter in grid.corner_letters().items():
        cx, cy = page((j * w, i * h))
        c.setFillGray(1.0)
        c.circle(cx, cy, r_disc, stroke=1, fill=1)
        c.setFillGray(0.0)
        c.drawCentredString(cx, cy - 7 * 25.4 / 72 * CAP_HEIGHT / 2, letter)
    end_page(c)
    return k


def _tee_marks(c, grid: Grid, r: int, col: int, printed, marks: list[TeeMark]):
    c.setLineWidth(MARK_LINE_MM)
    set_font(c, MARK_LABEL_SIZE_PT)
    cap = MARK_LABEL_SIZE_PT * 25.4 / 72 * CAP_HEIGHT
    for m in marks:
        for p, q in (m.stem, m.bar):
            seg = clip_segment(p, q, printed)
            if seg is not None:
                polyline(c, [grid.plan_to_sheet(r, col, v) for v in seg])
        if point_in_rect(m.label_at, printed):
            x, y = grid.plan_to_sheet(r, col, m.label_at)
            c.drawCentredString(x, y - cap / 2, m.node)


def export_mosaic(path: str | Path, grid: Grid, outlines: list[tuple[str, list[Point]]],
                  title: str = "Cutting layout", correction: PrintCorrection = NO_CORRECTION,
                  overview: bool = True, name: str = "", marks: list[TeeMark] = ()) -> ExportReport:
    """`outlines` : (nom, contour placé en coordonnées du plan, mm). `marks` : repères en T placés.
    `overview` : plan de montage
    en première page (sans correction d'échelle : il n'est pas à l'échelle 1:1), `name` : nom du
    patron affiché sous son titre."""
    s = grid.settings
    W, H = s.sheet_size
    a = s.assembly_margin
    factors = correction.page_factors(s.orientation)
    report = ExportReport(Path(path))
    for r, col in grid.cells():
        cell = grid.cell_rect(r, col)
        if any(polygon_touches_rect(pts, cell) for _name, pts in outlines):
            report.pages.append((r, col))
        else:
            report.omitted.append((r, col))
    if not report.pages:
        return report
    c = new_canvas(path, title)
    if overview:
        report.overview = True
        report.overview_scale = _overview(c, grid, outlines, name, set(report.omitted))
    for r, col in report.pages:
        begin_page(c, (W, H), factors)

        printed = grid.printed_rect(r, col)
        c.setLineWidth(PIECE_LINE_MM)
        c.setDash()
        for _name, pts in outlines:
            for part in clip_closed_polyline(pts, printed):
                polyline(c, [grid.plan_to_sheet(r, col, p) for p in part])

        _tee_marks(c, grid, r, col, printed, marks)

        c.setLineWidth(FRAME_LINE_MM)
        c.setDash(list(FRAME_DASH_MM))
        c.rect(a, a, W - 2 * a, H - 2 * a, stroke=1, fill=0)
        c.setDash()

        _corner_letters(c, grid.cell_corner_letters(r, col), a, W, H)

        set_font(c, LABEL_SIZE_PT, bold=True)
        baseline = s.print_margin + (s.bleed - LABEL_SIZE_PT * 25.4 / 72 * 0.7) / 2
        c.drawString(a + LABEL_OFFSET_MM, baseline, Grid.label(r, col))
        end_page(c)
    c.save()
    return report
