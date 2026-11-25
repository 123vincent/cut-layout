"""Outils communs aux exports PDF (reportlab). Unité de dessin : le millimètre.

Choix de reportlab plutôt que QPdfWriter (essai du 24.11.2026) : QPdfWriter arrondit la
taille de page au point entier (A4 → 209,90 × 297,04 mm) et décale le tracé de 0,04 mm ;
reportlab écrit la page et les coordonnées exactes (écart relu < 0,00001 mm).
"""
from __future__ import annotations

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .. import __version__

APP_ID = f"CutLayout {__version__}"     # propriétés du PDF : version qui l'a produit (traçabilité)

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
PT_TO_MM = 25.4 / 72


def new_canvas(path: str, title: str) -> canvas.Canvas:
    c = canvas.Canvas(str(path), pageCompression=0)
    c.setTitle(title)
    c.setAuthor("CutLayout")
    c.setCreator(APP_ID)
    return c


def begin_page(c: canvas.Canvas, size_mm: tuple[float, float], factors: tuple[float, float] = (1.0, 1.0)) -> None:
    """Page de la taille exacte donnée ; repère en mm, origine en bas à gauche, y vers le haut.

    `factors` : correction d'échelle de l'imprimante (horizontal, vertical), appliquée autour
    du centre de la page à tout le contenu.
    """
    w, h = size_mm
    c.setPageSize((w * mm, h * mm))
    c.saveState()
    c.scale(mm, mm)
    if factors != (1.0, 1.0):
        c.translate(w / 2, h / 2)
        c.scale(*factors)
        c.translate(-w / 2, -h / 2)


def end_page(c: canvas.Canvas) -> None:
    c.restoreState()
    c.showPage()


def set_font(c: canvas.Canvas, size_pt: float, bold: bool = False) -> None:
    c.setFont(FONT_BOLD if bold else FONT, size_pt * PT_TO_MM)


def fit_text(c: canvas.Canvas, text: str, max_width_mm: float, size_pt: float, bold: bool = False,
             min_size_pt: float = 6.0) -> tuple[str, float]:
    """Texte et corps (pt) qui tiennent dans `max_width_mm` : corps réduit jusqu'à `min_size_pt`,
    puis texte raccourci par la fin avec « … »."""
    font = FONT_BOLD if bold else FONT

    def width(t: str, size: float) -> float:
        return c.stringWidth(t, font, size * PT_TO_MM)
    size = size_pt
    while size > min_size_pt and width(text, size) > max_width_mm:
        size = max(min_size_pt, size - 0.5)
    if width(text, size) <= max_width_mm:
        return text, size
    while text and width(text + "…", size) > max_width_mm:
        text = text[:-1]
    return text + "…", size


def polyline(c: canvas.Canvas, pts, close: bool = False) -> None:
    p = c.beginPath()
    p.moveTo(*pts[0])
    for q in pts[1:]:
        p.lineTo(*q)
    if close:
        p.close()
    c.drawPath(p, stroke=1, fill=0)
