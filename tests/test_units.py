import pytest

from cut_layout.i18n import set_language
from cut_layout.units import format_cm, mm_per_unit


def test_cm_vers_mm_facteur_10():
    assert mm_per_unit("cm") == 10.0
    assert 68.5 * mm_per_unit("cm") == 685.0


def test_mm_identite():
    assert mm_per_unit("mm") == 1.0


@pytest.mark.parametrize("unit", ["inch", "", "CM", "m"])
def test_unite_inconnue_refusee(unit):
    with pytest.raises(ValueError):
        mm_per_unit(unit)


def test_format_cm():
    assert format_cm(685.0) == "68.50"
    assert format_cm(700.333, 1) == "70.0"
    set_language("fr")
    assert format_cm(685.0) == "68,50"
