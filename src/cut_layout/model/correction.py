"""Correction d'échelle de l'imprimante. Sans Qt.

Mesurée sur une page d'essai imprimée sans correction : pour chaque axe du papier,
longueur attendue / longueur mesurée. L'export agrandit (ou réduit) le contenu de chaque
page de ce facteur, autour du centre de la page, pour que l'imprimante le ramène à la cote.

Axes du papier : x = petit côté (largeur en portrait), y = grand côté.
Pour une page en paysage, le pilote d'impression tourne la page sur le papier : les facteurs
sont alors échangés. Vérifié le 25.11.2026 sur une imprimante laser (même bac) :
pages d'essai A4 portrait et paysage avec correction, règles relues 180 et 260 mm dans les deux cas.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..i18n import _, fmt, fmt_g

MAX_CORRECTION = 0.05      # au-delà de ±5 %, c'est probablement une erreur de saisie


class CorrectionError(ValueError):
    pass


@dataclass(frozen=True)
class PrintCorrection:
    x_expected: float = 180.0     # mm, petit côté du papier
    x_measured: float = 180.0
    y_expected: float = 260.0     # mm, grand côté du papier
    y_measured: float = 260.0

    def __post_init__(self):
        for key, v in (("x_expected_mm", self.x_expected), ("x_measured_mm", self.x_measured),
                       ("y_expected_mm", self.y_expected), ("y_measured_mm", self.y_measured)):
            if not v > 0:
                raise CorrectionError(_("{key}: must be positive ({value})").format(key=key, value=fmt_g(v)))
        for axis, f in (("x", self.fx), ("y", self.fy)):
            if abs(f - 1) > MAX_CORRECTION:
                raise CorrectionError(
                    _("{axis} correction of {percent} %: beyond ±{limit} %, check the lengths entered").format(
                        axis=axis, percent=("+" if f >= 1 else "") + fmt(100 * (f - 1), 2),
                        limit=fmt_g(100 * MAX_CORRECTION)))

    @property
    def fx(self) -> float:
        return self.x_expected / self.x_measured

    @property
    def fy(self) -> float:
        return self.y_expected / self.y_measured

    @property
    def is_identity(self) -> bool:
        return self.fx == 1.0 and self.fy == 1.0

    def page_factors(self, orientation: str) -> tuple[float, float]:
        """Facteurs (horizontal, vertical) de la page PDF selon son orientation."""
        return (self.fx, self.fy) if orientation == "portrait" else (self.fy, self.fx)

    def describe(self) -> str:
        if self.is_identity:
            return _("no scale correction")
        return _("scale correction x × {fx}, y × {fy}").format(fx=fmt(self.fx, 5), fy=fmt(self.fy, 5))


NO_CORRECTION = PrintCorrection()
