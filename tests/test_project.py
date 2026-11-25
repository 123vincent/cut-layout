"""Fichier de plan de coupe (.cutl) : enregistrement, relecture, détection des fichiers modifiés."""
import json
from dataclasses import replace
import os
import shutil

import pytest

from cut_layout.model.mosaic import SheetSettings
from cut_layout.model.placement import REF_CENTROID, Placement
from cut_layout.project import (EXTENSION, OPEN_EXTENSIONS, Project, ProjectError, changed_files, load_project, save_project,
                                sha256)

SAMPLES = os.environ["SM2D_SAMPLES"]


@pytest.fixture
def files(tmp_path):
    folder = tmp_path / "patrons"
    folder.mkdir()
    sm2d = shutil.copy(os.path.join(SAMPLES, "patron.sm2d"), folder / "patron.sm2d")
    smis = shutil.copy(os.path.join(SAMPLES, "mesures.smis"), folder / "mesures.smis")
    return folder, sm2d, smis


def make(sm2d, smis):
    return Project(sm2d, smis, sha256(sm2d), sha256(smis), SheetSettings("A3", "landscape"),
                   [("Demi-dos", Placement(REF_CENTROID, 123.456789, 300.0, -90.0)),
                    ("Manche courte", Placement("M4", 500.0, 12.5, 30.0, mirrored=True, marks=("M5", "M")))])


def test_aller_retour_sans_perte(files):
    folder, sm2d, smis = files
    path = folder / "plan.cutl"
    project = make(sm2d, smis)
    save_project(path, project)
    loaded = load_project(path)
    assert loaded == project
    assert changed_files(loaded) == []


def test_chemins_relatifs_et_sans_contours(files):
    folder, sm2d, smis = files
    path = folder / "plans" / "plan.cutl"
    path.parent.mkdir()
    save_project(path, make(sm2d, smis))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pattern"]["path"] == "../patron.sm2d" and data["measurements"]["path"] == "../mesures.smis"
    assert set(data["pieces"][0]) == {"name", "ref", "x_mm", "y_mm", "angle_deg", "mirrored", "marks"}  # pas de contour
    assert data["format_version"] == 4 and data["pieces"][1]["mirrored"] is True
    assert data["pieces"][1]["marks"] == ["M5", "M"]


def test_dossier_deplace_le_plan_suit(files, tmp_path):
    folder, sm2d, smis = files
    save_project(folder / "plan.cutl", make(sm2d, smis))
    moved = shutil.move(str(folder), str(tmp_path / "ailleurs"))
    loaded = load_project(tmp_path / "ailleurs" / "plan.cutl")
    assert loaded.sm2d == (tmp_path / "ailleurs" / "patron.sm2d").resolve()
    assert changed_files(loaded) == [] and moved


def test_patron_modifie_detecte(files):
    folder, sm2d, smis = files
    save_project(folder / "plan.cutl", make(sm2d, smis))
    with open(smis, "ab") as f:
        f.write(b"\n")
    loaded = load_project(folder / "plan.cutl")
    assert changed_files(loaded) == [loaded.smis]


@pytest.mark.parametrize("text,msg", [
    ("pas du json", "unreadable"),
    ('{"format_version": 5}', "version"),
    ('{"format_version": 1, "pattern": {}}', "invalid"),
])
def test_fichier_invalide_refuse(tmp_path, text, msg):
    path = tmp_path / "plan.cutl"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ProjectError, match=msg):
        load_project(path)


def test_ancienne_extension_pdc_relue(files):
    """Avant le renommage en CutLayout, les plans portaient l'extension .pdc : le contenu est identique."""
    folder, sm2d, smis = files
    save_project(folder / "plan.cutl", make(sm2d, smis))
    shutil.copy(folder / "plan.cutl", folder / "ancien.pdc")
    assert load_project(folder / "ancien.pdc") == load_project(folder / "plan.cutl")
    assert ".pdc" in OPEN_EXTENSIONS and EXTENSION == ".cutl"


def test_version_1_relue_sans_symetrie(files):
    """Fichier enregistré avant la symétrie : pas de clé « mirrored », version 1."""
    folder, sm2d, smis = files
    path = folder / "plan.cutl"
    save_project(path, make(sm2d, smis))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["format_version"] = 1
    for p in data["pieces"]:
        del p["mirrored"], p["marks"]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert [(pl.mirrored, pl.marks) for _n, pl in load_project(path).placements] == [(False, ())] * 2


def test_symetrie_invalide_refusee(files):
    folder, sm2d, smis = files
    path = folder / "plan.cutl"
    save_project(path, make(sm2d, smis))
    path.write_text(path.read_text(encoding="utf-8").replace("true", '"oui"'), encoding="utf-8")
    with pytest.raises(ProjectError, match="invalid"):
        load_project(path)


def test_noeuds_marques_invalides_refuses(files):
    folder, sm2d, smis = files
    path = folder / "plan.cutl"
    save_project(path, make(sm2d, smis))
    path.write_text(path.read_text(encoding="utf-8").replace('"M5"', "5"), encoding="utf-8")
    with pytest.raises(ProjectError, match="invalid"):
        load_project(path)


def test_format_personnalise_enregistre(files):
    folder, sm2d, smis = files
    path = folder / "plan.cutl"
    project = replace(make(sm2d, smis), sheet=SheetSettings("custom", "landscape", 12.5, 5.0, 594.0, 841.0))
    save_project(path, project)
    assert load_project(path) == project
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["sheet"]["custom_width_mm"] == 594.0 and data["sheet"]["custom_height_mm"] == 841.0
