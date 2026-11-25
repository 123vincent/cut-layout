import os
from pathlib import Path

import pytest

# Dossier des échantillons (exemple publié dans samples/) : SM2D_SAMPLES s'il est défini, sinon samples/ à la racine.
# Doit être fixé avant l'import de tests/geom/test_sm2d_geom.py, qui le lit au chargement.
os.environ.setdefault("SM2D_SAMPLES", str(Path(__file__).resolve().parents[1] / "samples"))


@pytest.fixture(autouse=True)
def english():
    """Tests en anglais (langue de référence) ; un test peut changer de langue, rétablie ensuite."""
    from cut_layout.i18n import set_language
    set_language("en")
    yield
    set_language("en")
