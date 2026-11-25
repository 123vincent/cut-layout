"""Conversion des unités de fichier vers l'unité interne (millimètre)."""
from .i18n import _, fmt

# Facteurs exacts par définition. Seule l'unité "cm" est vérifiée sur un fichier réel ;
# toute autre valeur de <unit> est refusée plutôt que devinée.
MM_PER_UNIT = {
    "mm": 1.0,
    "cm": 10.0,
}


def mm_per_unit(unit: str) -> float:
    try:
        return MM_PER_UNIT[unit]
    except KeyError:
        raise ValueError(_("unsupported unit: {unit!r} (supported: {supported})").format(
            unit=unit, supported=", ".join(MM_PER_UNIT))) from None


def format_cm(mm: float, decimals: int = 2) -> str:
    """Affichage en cm, séparateur décimal de la langue."""
    return fmt(mm / 10, decimals)
