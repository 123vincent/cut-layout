"""Patron de démonstration du tutoriel (docs/tutoriel/demo/, mesures fictives) : doit rester importable,
sinon le tutoriel et ses illustrations (tools/tutorial_screenshots.py) ne sont plus reproductibles."""
import math
from pathlib import Path

import pytest

from cut_layout.importers import Sm2dPattern, measurements_path

DEMO = Path(__file__).resolve().parents[1] / "docs" / "tutoriel" / "demo"
SM2D = DEMO / "jupe_demo.sm2d"


def test_patron_de_demonstration_importable():
    smis = measurements_path(SM2D)
    assert smis == (DEMO / "mesures_demo.smis").resolve() and smis.exists()
    p = Sm2dPattern(SM2D, smis)
    assert p.piece_names() == ["Devant", "Dos", "Ceinture", "Poche"]
    devant, ceinture = p.piece("Devant"), p.piece("Ceinture")
    assert devant.on_fold and not devant.forbid_flipping
    assert ceinture.forbid_flipping                      # case « Retourner » grisée (tutoriel § 5.3)
    # mesures fictives : (96 + 4) / 4 = 25 cm de large ; hauteur 58 cm + remontée de A5, placé à
    # 70/4 + 2 = 19,5 cm LE LONG de la ligne inclinée d'angle atanD(1,5 / 19,5)
    assert devant.width == pytest.approx(250.0, abs=1e-6)
    assert devant.height == pytest.approx(580.0 + 195.0 * math.sin(math.atan(1.5 / 19.5)), abs=1e-6)
    assert (ceinture.width, ceinture.height) == pytest.approx((730.0, 80.0), abs=1e-6)
    assert set(p.piece("Poche").nodes) == {"P", "P1", "P2", "P5", "P3"}
