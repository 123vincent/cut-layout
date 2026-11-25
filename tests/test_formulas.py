"""Fonctions des formules Seamly2D (liste du wiki transmise par Vincent le 25.11.2026).

Ces tests vérifient l'implémentation (valeurs de référence de la bibliothèque math de Python) ;
ils ne prouvent pas que Seamly2D donne les mêmes valeurs : la validation par un fichier enregistré
par Seamly2D, avec des cotes relevées par Vincent, reste à faire.
"""
import math
import os
import xml.etree.ElementTree as ET

import pytest
from sm2d_geom import FUNCTION_NAMES, Model

from cut_layout.importers import Sm2dPattern, UnsupportedContent
from cut_layout.importers.sm2d_importer import find_unsupported, unknown_functions

S = os.environ["SM2D_SAMPLES"]
SM2D, SMIS = os.path.join(S, "patron.sm2d"), os.path.join(S, "mesures.smis")


@pytest.fixture(scope="module")
def m():
    return Model(SM2D, SMIS)


@pytest.mark.parametrize("formula,expected", [
    # trigonométrie : radians sans suffixe (exemple du wiki : sin(90) = 0,893997), degrés avec D
    ("sin(90)", 0.8939966636005579), ("cos(_pi)", -1.0), ("tan(_pi/4)", 1.0),
    ("asin(1)", math.pi / 2), ("acos(0)", math.pi / 2), ("atan(1)", math.pi / 4),
    ("sinD(30)", 0.5), ("cosD(60)", 0.5), ("tanD(45)", 1.0),
    ("asinD(0.5)", 30.0), ("acosD(0.5)", 60.0), ("atanD(1)", 45.0),
    # hyperboliques
    ("sinh(1)", math.sinh(1)), ("cosh(1)", math.cosh(1)), ("tanh(1)", math.tanh(1)),
    ("asinh(1)", math.asinh(1)), ("acosh(2)", math.acosh(2)), ("atanh(0.5)", math.atanh(0.5)),
    # générales
    ("abs(-2.5)", 2.5), ("sqrt(16)", 4.0), ("exp(1)", math.e), ("ln(exp(2))", 2.0),
    ("log(1000)", 3.0), ("log10(100)", 2.0), ("log2(8)", 3.0),
    ("sign(-3)", -1.0), ("sign(0)", 0.0), ("sign(2)", 1.0), ("rint(2.4)", 2.0), ("rint(2.6)", 3.0),
    ("min(3; 1; 2)", 1.0), ("max(3; 1; 2)", 3.0), ("sum(1; 2; 3.5)", 6.5), ("avg(1; 2; 6)", 3.0),
    ("min(3, 1)", 1.0),
    # conversions et constante
    ("radTodeg(_pi)", 180.0), ("degTorad(180)", math.pi), ("2*_pi", 2 * math.pi),
])
def test_fonction(m, formula, expected):
    assert m.ev(formula) == pytest.approx(expected, rel=1e-12, abs=1e-12)


def test_casse_respectee(m):
    """Comme dans Seamly2D : acosD est juste, acosd est faux."""
    assert "acosD" in FUNCTION_NAMES and "acosd" not in FUNCTION_NAMES
    with pytest.raises(NameError):            # eval signale l'identifiant inconnu par NameError
        m.ev("acosd(0.5)")


def test_mesures_et_fonctions_ensemble(m):
    assert m.ev("sqrt(bust_circ^2)") == pytest.approx(m.ns["bust_circ"])


def test_formules_refusees_restent_refusees(m):
    for f in ("__import__('os')", "(1).real", "a.b"):
        with pytest.raises(ValueError):
            m.ev(f)


# --- contrôle préalable de l'importeur -------------------------------------------

def test_fonction_inconnue_detectee():
    assert unknown_functions("sinD(30) + fmod(5; 2) + Acos(1)") == ["Acos", "fmod"]
    assert unknown_functions("(bust_circ + #ais)/2 + SplPath_A_B") == []


def test_echantillon_sans_fonction_inconnue():
    assert find_unsupported(ET.parse(SM2D).getroot()) == []      # descriptions « (exemple: 6) » ignorées


def test_fonction_inconnue_refusee_a_l_import(tmp_path):
    tree = ET.parse(SM2D)
    root = tree.getroot()
    root.find("variables")[0].set("formula", "fmod(7; 2)")
    root.find("draftBlock/calculation/point[@type='endLine']").set("length", "acosd(0.5)")
    path = tmp_path / "patron.sm2d"
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    with pytest.raises(UnsupportedContent) as e:
        Sm2dPattern(path, SMIS)
    text = str(e.value)
    assert "'fmod'" in text and "'acosd'" in text


@pytest.mark.parametrize("formula,error", [("mesure_inconnue * 2", "NameError"), ("asin(2)", "ValueError"),
                                           ("sqrt(1; 2)", "TypeError"), ("exp(1000)", "OverflowError")])
def test_erreur_de_calcul_signalee_sans_plantage(tmp_path, formula, error):
    """Identifiant inconnu, hors domaine, mauvais nombre d'arguments : erreur d'import explicite."""
    from cut_layout.importers import Sm2dImportError
    tree = ET.parse(SM2D)
    tree.getroot().find("variables")[0].set("formula", formula)
    path = tmp_path / "patron.sm2d"
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    with pytest.raises(Sm2dImportError, match=error):
        Sm2dPattern(path, SMIS)
