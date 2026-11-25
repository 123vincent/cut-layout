"""Page d'essai d'imprimante (PROMPT §8, étape 4). Sans Qt.

Au format et dans l'orientation de la mise en page (paysage ajouté le 25.11.2026 pour vérifier la
correction en paysage). Contenu :
- sur chaque bord, des traits à 2, 3, 4, 5 et 6 mm du bord de la feuille, décalés le long du
  bord : le plus petit trait imprimé en entier donne la zone non imprimable de ce côté ;
- le cadre de coupe en pointillés, à la marge d'assemblage : il doit s'imprimer en entier ;
- une règle le long du petit côté du papier (x, 180 mm) et une le long du grand côté (y, 260 mm) :
  longueurs différentes, pour qu'aucune confusion entre x et y ne soit possible (demandé par Vincent).
  x et y sont ceux de la correction d'imprimante (x = petit côté du papier) : en paysage, la règle x
  est verticale et la règle y horizontale. Sur un format trop petit, une règle est raccourcie au
  multiple de 10 mm qui tient dans le cadre ;
- les réglages en cours, la correction appliquée et la marche à suivre.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..i18n import _, fmt_g
from ..model.correction import NO_CORRECTION, PrintCorrection
from ..model.mosaic import SheetSettings
from .pdf_common import begin_page, end_page, new_canvas, set_font
from .pdf_mosaic import FRAME_DASH_MM, FRAME_LINE_MM

EDGE_DISTANCES_MM = (2.0, 3.0, 4.0, 5.0, 6.0)
EDGE_TICK_MM = 12.0            # longueur des traits de bord
EDGE_STEP_MM = 24.0            # pas le long du bord entre deux traits (trait + étiquette)
THIN_MM = 0.1
X_RULER_MM = 180               # règle le long du petit côté du papier (x de la correction)
Y_RULER_MM = 260               # règle le long du grand côté du papier (y de la correction)
RULER_INSET_MM = 5.0           # depuis le cadre : règle verticale (x) et début des règles
H_RULER_INSET_MM = 8.0         # depuis le cadre du bas : ligne de la règle horizontale (chiffres en dessous)
RULER_GAP_MM = 7.0             # la règle du grand côté commence plus loin : chiffres des deux règles séparés
TEXT_X_MM = 35.0


def ruler_lengths(settings: SheetSettings) -> tuple[int, int]:
    """Longueurs (x, y) des règles : 180 et 260 mm, raccourcies au multiple de 10 mm qui tient dans le
    cadre de coupe si le format est trop petit."""
    short, long = settings.portrait_size
    a = settings.assembly_margin
    room_short = short - 2 * a - RULER_INSET_MM
    room_long = long - 2 * a - RULER_INSET_MM - RULER_GAP_MM
    return (max(10, min(X_RULER_MM, int(room_short // 10) * 10)),
            max(10, min(Y_RULER_MM, int(room_long // 10) * 10)))


def ruler_layout(settings: SheetSettings) -> dict[str, tuple[tuple[float, float], int, bool]]:
    """Règles x et y : (origine sur la page, longueur, horizontale). En portrait, x est horizontale ;
    en paysage, x est verticale (le petit côté du papier est alors la hauteur de la page)."""
    a = settings.assembly_margin
    lx, ly = ruler_lengths(settings)
    start, late = a + RULER_INSET_MM, a + RULER_INSET_MM + RULER_GAP_MM
    h_y = a + H_RULER_INSET_MM
    if settings.orientation == "portrait":
        return {"x": ((start, h_y), lx, True), "y": ((start, late), ly, False)}
    return {"y": ((late, h_y), ly, True), "x": ((start, start), lx, False)}


def _edge_ticks(c, W: float, H: float):
    """Traits parallèles à chaque bord, à 2…6 mm, centrés sur le bord ; étiquette après chaque trait."""
    set_font(c, 6)
    c.setLineWidth(THIN_MM)
    n = len(EDGE_DISTANCES_MM)
    for side in ("bas", "haut", "gauche", "droite"):
        length = W if side in ("bas", "haut") else H
        start = (length - n * EDGE_STEP_MM) / 2
        for i, d in enumerate(EDGE_DISTANCES_MM):
            s0 = start + i * EDGE_STEP_MM
            s1 = s0 + EDGE_TICK_MM
            label = fmt_g(d)
            if side == "bas":
                c.line(s0, d, s1, d)
                c.drawString(s1 + 1, d - 0.6, label)
            elif side == "haut":
                c.line(s0, H - d, s1, H - d)
                c.drawString(s1 + 1, H - d - 0.6, label)
            elif side == "gauche":
                c.line(d, s0, d, s1)
                c.drawString(d - 0.6, s1 + 1, label)
            else:
                c.line(W - d, s0, W - d, s1)
                c.drawString(W - d - 0.6, s1 + 1, label)


def _ruler(c, origin, length: int, horizontal: bool, label: str):
    x0, y0 = origin
    c.setLineWidth(THIN_MM)
    set_font(c, 6)
    if horizontal:
        c.line(x0, y0, x0 + length, y0)
    else:
        c.line(x0, y0, x0, y0 + length)
    for k in range(length + 1):
        h = 4.0 if k % 10 == 0 else 2.5 if k % 5 == 0 else 1.5
        if horizontal:
            c.line(x0 + k, y0, x0 + k, y0 - h)
            if k % 10 == 0:
                c.drawCentredString(x0 + k, y0 - 6.5, str(k // 10))
        else:
            c.line(x0, y0 + k, x0 + h, y0 + k)
            if k % 10 == 0:
                c.drawString(x0 + 5, y0 + k - 0.8, str(k // 10))
    set_font(c, 8, bold=True)
    if horizontal:
        c.drawString(x0 + length / 2 - 25, y0 + 2, label)
    else:
        c.saveState()
        c.translate(x0 + 12, y0 + length / 2 - 25)    # à droite des chiffres
        c.rotate(90)
        c.drawString(0, 0, label)
        c.restoreState()


def export_test_page(path: str | Path, settings: SheetSettings, when: datetime | None = None,
                     correction: PrintCorrection = NO_CORRECTION) -> Path:
    """Page d'essai ; `correction` : NO_CORRECTION pour mesurer l'imprimante, la correction
    en cours pour vérifier qu'elle ramène les cotes à leur valeur."""
    W, H = settings.sheet_size
    a = settings.assembly_margin
    short, long = settings.portrait_size
    fx, fy = short - 2 * a, long - 2 * a          # cadre de coupe le long du petit (x) et du grand (y) côté
    c = new_canvas(path, _("Printer test page"))
    begin_page(c, (W, H), correction.page_factors(settings.orientation))

    _edge_ticks(c, W, H)

    c.setLineWidth(FRAME_LINE_MM)
    c.setDash(list(FRAME_DASH_MM))
    c.rect(a, a, W - 2 * a, H - 2 * a, stroke=1, fill=0)
    c.setDash()

    rulers = ruler_layout(settings)
    labels = {"x": _("Short side of the paper: {length} mm ruler (x)"),
              "y": _("Long side of the paper: {length} mm ruler (y)")}
    for axis, (origin, length, horizontal) in rulers.items():
        _ruler(c, origin, length, horizontal, labels[axis].format(length=length))
    lx, ly = rulers["x"][1], rulers["y"][1]

    when = when or datetime.now()
    header = [
        (_("Printer test page — CutLayout"), True),
        (_("Format {sheet} · assembly margin {assembly} mm · print margin set to {print} mm · {date}").format(
            sheet=settings.describe(), assembly=fmt_g(a), print=fmt_g(settings.print_margin),
            # TRANSLATORS: strftime date format of the test page
            date=when.strftime(_("%Y-%m-%d %H:%M"))), False),
        (_("Printed with: {correction}").format(correction=correction.describe()), True),
    ]
    steps = _("1. Print at 100 % (“Actual size”), without “Fit to page”.\n"
              "2. Measure the rulers (x: {x} mm, y: {y} mm) or the cutting frame\n"
              "    ({frame}, between the dashed lines): the longest length is the most accurate.\n"
              "3. The dashed cutting frame must be printed entirely, on all four sides.\n"
              "4. On each edge, note the smallest line printed entirely (2 to 6 mm from the edge):\n"
              "    this is the non-printable area on that side. Set print_margin_mm to at least the\n"
              "    largest of the four values, and below the assembly margin.\n"
              "5. Scale error measured on a page WITHOUT correction: enter the expected and measured\n"
              "    lengths in the [printer] section of the preferences (File > Preferences).").format(
        x=lx, y=ly, frame=f"x {fmt_g(fx)} × y {fmt_g(fy)} mm")
    lines = header + [(line, False) for line in steps.split("\n")]
    y = H - a - 10
    for text, bold in lines:
        set_font(c, 10 if bold else 8.5, bold)
        c.drawString(TEXT_X_MM, y, text)
        y -= 6 if bold else 5
    end_page(c)
    c.save()
    return Path(path)
