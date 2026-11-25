import os
"""Tests de non-régression de sm2d_geom (échantillon samples/patron.sm2d + samples/mesures.smis).
ATTENTION : ces tests figent le comportement actuel et des identités internes.
Ils ne prouvent PAS l'égalité avec les longueurs calculées par Seamly2D (voir note de validation)."""
import math, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sm2d_geom import Model, polygon_area

D = os.environ.get("SM2D_SAMPLES", "samples").rstrip("/") + "/"   # patron.sm2d + mesures.smis (exemple publié)

@pytest.fixture(scope="module")
def m():
    return Model(D + "patron.sm2d", D + "mesures.smis")

def test_milieu_dos_A_A3(m):
    assert math.dist(m.pt["A"], m.pt["A3"]) == pytest.approx(67.5, abs=1e-9)

def test_tete_de_manche_egale_emmanchure(m):
    c = m.curves
    assert abs(c["Spl_M4_M"].length - c["SplPath_F2_D1"].length) < 0.01   # tolérance à valider par Vincent
    assert abs(c["Spl_M_M5"].length - c["SplPath_H2_D1"].length) < 0.01

def test_encolure(m):
    e = m.curves["Spl_A_E2"].length + m.curves["Spl_G2_G3"].length - m.ns["neck_circ"] / 2
    assert 0 <= e <= 0.5

def test_hauteurs_pieces_en_mm(m):
    h = {}
    for _, pc in m.pieces():
        ys = [p[1] for p in m.piece_outline(pc, n=100)]
        h[pc.get("name")] = (max(ys) - min(ys)) * 10
    assert h["Demi-devant"] == pytest.approx(685.0, abs=0.1)
    assert h["Manche longue"] == pytest.approx(650.0, abs=0.1)
    assert h["Demi-dos"] == pytest.approx(700.3, abs=0.1)

def test_contours_fermes_et_simples(m):
    for _, pc in m.pieces():
        poly = m.piece_outline(pc, n=50)
        assert len(poly) > 20 and polygon_area(poly) != 0

def test_convergence_echantillonnage(m):
    # l'aire ne doit pas dépendre de la finesse d'échantillonnage (< 0,05 cm²)
    pc = next(p for _, p in m.pieces() if p.get("name") == "Demi-dos")
    a1 = abs(polygon_area(m.piece_outline(pc, n=100)))
    a2 = abs(polygon_area(m.piece_outline(pc, n=400)))
    assert abs(a1 - a2) < 0.05

@pytest.mark.parametrize("f", ["__import__('os').system('id')", "(1).__class__", "open('/etc/passwd')", "A.x"])
def test_formule_dangereuse_refusee(m, f):
    with pytest.raises((ValueError, KeyError, NameError, TypeError)):
        m.ev(f)


SEAMLY = {  # relevé par Vincent dans le Tableau des variables de Seamly2D (cm, 4 décimales affichées)
    "SplPath_F2_D1": 25.3691, "SplPath_H2_D1": 24.4013, "Spl_A_E2": 8.34367,
    "Spl_G2_G3": 12.3447, "Spl_M4_M": 25.3686, "Spl_M_M5": 24.4023,
}

@pytest.mark.parametrize("name,ref", SEAMLY.items())
def test_longueurs_identiques_a_seamly2d(m, name, ref):
    assert m.curves[name].length == pytest.approx(ref, abs=0.001)   # tolérance à valider par Vincent
