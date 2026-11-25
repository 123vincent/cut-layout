"""Traductions : catalogue complet, compilé, et placeholders identiques à l'anglais."""
import re
import string
from pathlib import Path

import pytest
from babel.messages.extract import extract_from_dir
from babel.messages.mofile import read_mo
from babel.messages.pofile import read_po

from cut_layout import i18n
from cut_layout.i18n import _, fmt, ngettext, resolve_language, set_language
from cut_layout.model.correction import PrintCorrection
from cut_layout.model.mosaic import Grid

PACKAGE = Path(i18n.__file__).parent
TRANSLATED = [lang for lang in i18n.LANGUAGES if lang != "en"]
KEYWORDS = {"_": None, "ngettext": (1, 2)}


def catalog(lang):
    with (i18n.LOCALE_DIR / lang / "LC_MESSAGES" / f"{i18n.DOMAIN}.po").open("rb") as f:
        return read_po(f)


def source_messages():
    ids = set()
    for _file, _line, msg, _comments, _ctx in extract_from_dir(str(PACKAGE), keywords=KEYWORDS,
                                                                comment_tags=("TRANSLATORS:",)):
        ids.add(msg[0] if isinstance(msg, tuple) else msg)
    return ids


def fields(text):
    return sorted(f for _lit, f, spec, conv in string.Formatter().parse(text) if f is not None)


@pytest.mark.parametrize("lang", TRANSLATED)
def test_tous_les_textes_du_code_sont_traduits(lang):
    cat = catalog(lang)
    translated = {}
    for m in cat:
        if m.id and not m.fuzzy:
            key = m.id[0] if isinstance(m.id, tuple) else m.id
            strings = m.string if isinstance(m.string, tuple) else (m.string,)
            if all(strings):
                translated[key] = m
    missing = source_messages() - set(translated)
    assert not missing, f"à traduire (tools/i18n.py update) : {sorted(missing)}"


@pytest.mark.parametrize("lang", TRANSLATED)
def test_mo_compile_a_jour(lang):
    def key(m):
        return (tuple(m.id) if isinstance(m.id, (list, tuple)) else m.id,
                tuple(m.string) if isinstance(m.string, (list, tuple)) else m.string)
    with (i18n.LOCALE_DIR / lang / "LC_MESSAGES" / f"{i18n.DOMAIN}.mo").open("rb") as f:
        mo = dict(key(m) for m in read_mo(f) if m.id)
    po = dict(key(m) for m in catalog(lang) if m.id and not m.fuzzy)
    assert mo == po, "lancer : tools/i18n.py compile"


@pytest.mark.parametrize("lang", TRANSLATED)
def test_memes_placeholders_que_l_anglais(lang):
    for m in catalog(lang):
        if not m.id:
            continue
        ids = m.id if isinstance(m.id, tuple) else (m.id,)
        strings = m.string if isinstance(m.string, tuple) else (m.string,)
        for s in strings:
            assert fields(s) == fields(ids[0]), m.id
        if m.id == "%Y-%m-%d %H:%M":
            assert set(re.findall(r"%\w", m.string)) == {"%Y", "%m", "%d", "%H", "%M"}


@pytest.mark.parametrize("setting,system,expected", [
    ("fr", "en_US", "fr"), ("en", "fr_FR", "en"),
    ("auto", "fr_FR", "fr"), ("auto", "fr-CH", "fr"), ("auto", "de_DE", "en"), ("auto", None, "en"),
])
def test_langue_effective(setting, system, expected):
    assert resolve_language(setting, system) == expected


def test_langue_inconnue_refusee():
    with pytest.raises(ValueError):
        set_language("xx")


def test_francais():
    set_language("fr")
    assert _("&File") == "&Fichier"
    assert Grid.label(2, 3) == "L2-C3"
    assert ngettext("{n} page {sheet} exported, row by row from {first}.",
                    "{n} pages {sheet} exported, row by row from {first}.", 1).startswith("{n} page {sheet} exportée")
    assert fmt(1.5, 2) == "1,50"
    assert PrintCorrection(190, 188.8, 277, 276.7).describe() == "correction d'échelle x × 1,00636, y × 1,00108"


def test_anglais():
    assert Grid.label(2, 3) == "R2-C3"
    assert fmt(1.5, 2) == "1.50"
    assert PrintCorrection(190, 188.8, 277, 276.7).describe() == "scale correction x × 1.00636, y × 1.00108"


def test_suffixe_du_pdf_en_francais():
    """Le renommage en CutLayout avait remplacé « plan_de_coupe » par « cut_layout » dans la traduction
    (constaté le 25.11.2026) : le nom de fichier proposé doit rester dans la langue de l'utilisateur."""
    from cut_layout.i18n import _, set_language
    set_language("fr")
    try:
        assert _("cutting_layout") == "plan_de_coupe"
    finally:
        set_language("en")
