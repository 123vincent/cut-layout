"""Fichier de plan de coupe (.cutl ; ancien nom .pdc, toujours lu) : patron, mesures et placement des pièces. Sans Qt.

Format JSON lisible (version 4 ; les versions 1 à 3 sont relues). Les contours ne sont pas enregistrés :
ils sont recalculés depuis le patron à l'ouverture (fichier petit, sans mesures corporelles). Les empreintes
SHA-256 du patron et des mesures signalent qu'ils ont changé depuis l'enregistrement.
Mise en page (`sheet`) : format (dimensions du format personnalisé comprises), orientation et marge
d'assemblage sont ceux du plan (25.11.2026) ; la marge d'impression enregistrée n'est qu'informative :
c'est un réglage de l'imprimante, pris dans les préférences à l'ouverture.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import _
from .model.mosaic import CUSTOM, SheetSettings
from .model.placement import Placement

EXTENSION = ".cutl"
LEGACY_EXTENSIONS = (".pdc",)          # avant le renommage en CutLayout (25.11.2026)
OPEN_EXTENSIONS = (EXTENSION,) + LEGACY_EXTENSIONS
FORMAT_VERSION = 4   # 2 : symétrie (« mirrored ») ; 3 : nœuds marqués (« marks ») ; 4 : format personnalisé
READABLE_VERSIONS = (1, 2, 3, 4)   # clés absentes des versions antérieures : valeurs par défaut


class ProjectError(ValueError):
    pass


@dataclass(frozen=True)
class Project:
    sm2d: Path
    smis: Path
    sm2d_sha256: str
    smis_sha256: str
    sheet: SheetSettings
    placements: list[tuple[str, Placement]] = field(default_factory=list)   # (nom de la pièce, placement)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _relative(target: Path, base: Path) -> str:
    """Chemin relatif au dossier du .cutl (le plan suit le patron si le dossier est déplacé) ;
    absolu si impossible (autre lecteur)."""
    try:
        return Path(os.path.relpath(Path(target).resolve(), base.resolve())).as_posix()
    except ValueError:
        return Path(target).resolve().as_posix()


def save_project(path: Path, project: Project) -> None:
    path = Path(path)
    base = path.parent
    s = project.sheet
    data = {
        "format_version": FORMAT_VERSION,
        "pattern": {"path": _relative(project.sm2d, base), "sha256": project.sm2d_sha256},
        "measurements": {"path": _relative(project.smis, base), "sha256": project.smis_sha256},
        "sheet": {"format": s.format, "orientation": s.orientation,
                  "assembly_margin_mm": s.assembly_margin, "print_margin_mm": s.print_margin,
                  **({"custom_width_mm": s.custom_width, "custom_height_mm": s.custom_height}
                     if s.format == CUSTOM else {})},
        "pieces": [{"name": name, "ref": pl.ref, "x_mm": pl.x, "y_mm": pl.y, "angle_deg": pl.angle,
                    "mirrored": pl.mirrored, "marks": list(pl.marks)}
                   for name, pl in project.placements],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _mirrored(piece: dict) -> bool:
    value = piece.get("mirrored", False)      # absent en version 1
    if not isinstance(value, bool):
        raise ValueError(f"mirrored: {value!r}")
    return value


def _marks(piece: dict) -> tuple[str, ...]:
    value = piece.get("marks", [])            # absent avant la version 3
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"marks: {value!r}")
    return tuple(value)


def load_project(path: Path) -> Project:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProjectError(_("unreadable cutting layout file: {error}").format(error=e)) from e
    if not isinstance(data, dict) or data.get("format_version") not in READABLE_VERSIONS:
        raise ProjectError(_("unsupported cutting layout file version: {version!r}").format(
            version=data.get("format_version") if isinstance(data, dict) else None))
    try:
        base = path.parent
        sheet = data["sheet"]
        return Project(
            sm2d=(base / data["pattern"]["path"]).resolve(),
            smis=(base / data["measurements"]["path"]).resolve(),
            sm2d_sha256=str(data["pattern"]["sha256"]),
            smis_sha256=str(data["measurements"]["sha256"]),
            sheet=SheetSettings(sheet["format"], sheet["orientation"],
                                float(sheet["assembly_margin_mm"]), float(sheet["print_margin_mm"]),
                                float(sheet.get("custom_width_mm", 0.0)), float(sheet.get("custom_height_mm", 0.0))),
            placements=[(str(p["name"]), Placement(str(p["ref"]), float(p["x_mm"]), float(p["y_mm"]),
                                                   float(p["angle_deg"]), _mirrored(p), _marks(p)))
                        for p in data["pieces"]],
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ProjectError(_("invalid cutting layout file: {error}").format(error=e)) from e


def changed_files(project: Project) -> list[Path]:
    """Patron ou mesures dont le contenu a changé depuis l'enregistrement."""
    return [p for p, h in ((project.sm2d, project.sm2d_sha256), (project.smis, project.smis_sha256))
            if sha256(p) != h]
