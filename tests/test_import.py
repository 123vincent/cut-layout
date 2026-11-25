"""Import .sm2d + .smis : contrôle du contenu, unités, cotes en mm."""
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from sm2d_geom import Model
from cut_layout.importers import (Sm2dImportError, Sm2dPattern, UnsupportedContent,
                                  find_unsupported, measurements_path)

SAMPLES = Path(os.environ["SM2D_SAMPLES"])
SM2D, SMIS = SAMPLES / "patron.sm2d", SAMPLES / "mesures.smis"


@pytest.fixture(scope="module")
def pattern():
    return Sm2dPattern(SM2D, SMIS)


def _modified_copy(tmp_path, edit, src=SM2D, name="patron.sm2d"):
    tree = ET.parse(src)
    edit(tree.getroot())
    out = tmp_path / name
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    return out


# --- chemin des mesures ---------------------------------------------------

def test_chemin_mesures_relatif_au_sm2d(tmp_path):
    def edit(root):
        root.find("measurements").text = "../mesures/Individuel/x.smis"
    sub = tmp_path / "patrons"
    sub.mkdir()
    p = _modified_copy(sub, edit)
    assert measurements_path(p) == (tmp_path / "mesures" / "Individuel" / "x.smis").resolve()


def test_chemin_mesures_absent(tmp_path):
    def edit(root):
        root.remove(root.find("measurements"))
    assert measurements_path(_modified_copy(tmp_path, edit)) is None


# --- contrôle du contenu --------------------------------------------------

def test_echantillon_entierement_gere():
    assert find_unsupported(ET.parse(SM2D).getroot()) == []


def test_element_inconnu_refuse_avec_son_nom(tmp_path):
    # sm2d_geom sauterait cet élément sans erreur : l'importeur doit le refuser
    def edit(root):
        calc = root.find("draftBlock/calculation")
        ET.SubElement(calc, "arc", id="999", type="simple", name="Arc_X")
    with pytest.raises(UnsupportedContent) as e:
        Sm2dPattern(_modified_copy(tmp_path, edit), SMIS)
    assert any("<arc>" in p and "999" in p for p in e.value.problems)


def test_type_de_point_inconnu_refuse(tmp_path):
    def edit(root):
        root.find("draftBlock/calculation/point[@type='endLine']").set("type", "bisector")
    with pytest.raises(UnsupportedContent, match="bisector"):
        Sm2dPattern(_modified_copy(tmp_path, edit), SMIS)


def test_noeud_de_piece_inconnu_refuse(tmp_path):
    def edit(root):
        root.find(".//piece/nodes/node").set("type", "NodeArc")
    with pytest.raises(UnsupportedContent, match="NodeArc"):
        Sm2dPattern(_modified_copy(tmp_path, edit), SMIS)


def test_attribut_de_noeud_inconnu_refuse(tmp_path):
    def edit(root):
        root.find(".//piece/nodes/node").set("excluded", "true")
    with pytest.raises(UnsupportedContent, match="excluded"):
        Sm2dPattern(_modified_copy(tmp_path, edit), SMIS)


def test_unites_differentes_refusees(tmp_path):
    def edit(root):
        root.find("unit").text = "mm"
    smis = _modified_copy(tmp_path, edit, src=SMIS, name="mesures.smis")
    with pytest.raises(Sm2dImportError, match="different units"):
        Sm2dPattern(SM2D, smis)


def test_unite_non_geree_refusee(tmp_path):
    def edit(root):
        root.find("unit").text = "inch"
    sm2d = _modified_copy(tmp_path, edit)
    smis = _modified_copy(tmp_path, edit, src=SMIS, name="mesures.smis")
    with pytest.raises(Sm2dImportError, match="unsupported unit"):
        Sm2dPattern(sm2d, smis)


# --- pièces et cotes ------------------------------------------------------

def test_liste_des_pieces(pattern):
    assert pattern.piece_names() == ["Demi-dos", "Demi-devant", "Manche longue", "Manche courte"]


def test_conversion_cm_mm_exacte_par_rapport_au_module(pattern):
    # même contour que sm2d_geom, multiplié par 10, point par point
    m = Model(str(SM2D), str(SMIS))
    for block, pc in m.pieces():
        ref = m.piece_outline(pc, n=pattern.samples_per_segment)
        got = pattern.piece(pc.get("name")).outline
        assert len(got) == len(ref)
        assert max(math.dist(g, (x * 10, y * 10)) for g, (x, y) in zip(got, ref)) == 0.0


# L × H en mm. Hauteurs : grandes cotes du tutoriel (tolérance 0,1 mm, comme test_sm2d_geom).
# Largeurs : valeurs du module arrondies à 0,1 mm dans la note de validation (tolérance 0,05 mm).
EXPECTED_MM = {
    "Demi-dos": (285.0, 700.3),
    "Demi-devant": (275.0, 685.0),
    "Manche longue": (382.7, 650.0),
    "Manche courte": (382.7, 220.0),
}


@pytest.mark.parametrize("name,dims", EXPECTED_MM.items())
def test_cotes_des_pieces_en_mm(pattern, name, dims):
    p = pattern.piece(name)
    assert p.width == pytest.approx(dims[0], abs=0.05)
    assert p.height == pytest.approx(dims[1], abs=0.1)


def test_noeuds_sur_le_contour(pattern):
    # D7 (exemple du scénario de Vincent) et C5 (ancre) sont des nœuds du demi-devant
    p = pattern.piece("Demi-devant")
    assert {"D7", "C5", "D1"} <= set(p.nodes)
    m = Model(str(SM2D), str(SMIS))
    for nm, xy in p.nodes.items():
        assert xy == (m.pt[nm][0] * 10, m.pt[nm][1] * 10)
        assert min(math.dist(xy, q) for q in p.outline) < 1e-9


def test_pieces_au_pli(pattern):
    assert {n: pattern.piece(n).on_fold for n in pattern.piece_names()} == {
        "Demi-dos": True, "Demi-devant": True, "Manche longue": False, "Manche courte": False}


def _max_deviation(coarse, fine):
    """Plus grande distance d'un point du contour fin au polygone grossier."""
    def seg_dist(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
    segs = list(zip(coarse, coarse[1:] + coarse[:1]))
    return max(min(seg_dist(p, a, b) for a, b in segs) for p in fine[::7])


@pytest.mark.parametrize("name", ["Demi-dos", "Manche longue"])
def test_ecart_d_echantillonnage_inferieur_a_0_01_mm(pattern, name):
    # mesuré le 24.11.2026 : 0,0010 mm (dos), 0,0027 mm (manche) à 200 points par segment
    fine = Sm2dPattern(SM2D, SMIS, samples_per_segment=1600).piece(name).outline
    assert _max_deviation(pattern.piece(name).outline, fine) < 0.01


def test_retournement_interdit_lu_dans_le_patron(tmp_path, pattern):
    assert not any(pattern.piece(n).forbid_flipping for n in pattern.piece_names())    # échantillon : "false"

    def edit(root):
        root.find(".//piece[@name='Demi-dos']").set("forbidFlipping", "true")
    p = Sm2dPattern(_modified_copy(tmp_path, edit), SMIS)
    assert p.piece("Demi-dos").forbid_flipping and not p.piece("Demi-devant").forbid_flipping
