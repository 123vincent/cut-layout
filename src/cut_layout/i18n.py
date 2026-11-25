"""Traduction de l'interface (gettext). Sans Qt.

Langue de référence : l'anglais (textes du code). Traductions : locale/<langue>/LC_MESSAGES/cut_layout.po,
compilées en .mo (tools/i18n.py). Ajouter une langue : voir tools/i18n.py.
"""
from __future__ import annotations

import gettext
from pathlib import Path

DOMAIN = "cut_layout"
LOCALE_DIR = Path(__file__).parent / "locale"
LANGUAGES = ("en", "fr")            # "en" = textes du code, sans catalogue
LANGUAGE_NAMES = {"en": "English", "fr": "Français"}
AUTO = "auto"

_translation: gettext.NullTranslations = gettext.NullTranslations()
_language = "en"


def resolve_language(setting: str, system_locale: str | None) -> str:
    """Langue effective : `setting` si c'est une langue gérée ; pour « auto », celle du système
    (ex. « fr_FR » → « fr ») si elle est gérée, sinon l'anglais."""
    if setting in LANGUAGES:
        return setting
    code = (system_locale or "").replace("-", "_").split("_")[0].lower()
    return code if code in LANGUAGES else "en"


def set_language(language: str) -> None:
    global _translation, _language
    if language not in LANGUAGES:
        raise ValueError(f"unsupported language: {language!r}")
    _translation = (gettext.NullTranslations() if language == "en"
                    else gettext.translation(DOMAIN, LOCALE_DIR, languages=[language]))
    _language = language


def current_language() -> str:
    return _language


def _(message: str) -> str:
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


def fmt(value: float, decimals: int) -> str:
    """Nombre avec le séparateur décimal de la langue (virgule en français)."""
    text = f"{value:.{decimals}f}"
    return text.replace(".", ",") if _language == "fr" else text


def fmt_g(value: float) -> str:
    """Nombre sans zéros inutiles (format g), séparateur de la langue."""
    text = f"{value:g}"
    return text.replace(".", ",") if _language == "fr" else text
