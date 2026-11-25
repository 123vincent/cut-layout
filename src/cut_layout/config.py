"""Fichier de configuration : format de feuille, marges, affichage, correction d'imprimante.

Format INI commenté (configparser, bibliothèque standard). Clés en anglais (décision de Vincent,
24.11.2026) ; commentaires dans la langue de l'interface au moment de la création du fichier,
avec les valeurs possibles générées depuis les constantes du code.
Emplacement : ~/.cut_layout/config.ini (compte de l'utilisateur), créé avec les valeurs par défaut s'il
n'existe pas. Au premier lancement après le renommage (plan-de-coupe → CutLayout, 25.11.2026), le
config.ini de ~/.plan_de_coupe/ est copié ; l'ancien dossier n'est pas modifié.
Un fichier de l'ancien format (clés françaises, avant le 24.11.2026) est converti automatiquement,
l'original étant conservé sous config.ini.old.
"""
from __future__ import annotations

import configparser
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import AUTO, LANGUAGES, _, fmt_g
from .model.correction import NO_CORRECTION, CorrectionError, PrintCorrection
from .model.mosaic import CUSTOM, CUSTOM_RANGE_MM, FORMATS, ORIENTATIONS, MosaicError, SheetSettings

CONFIG_DIR = Path.home() / ".cut_layout"
CONFIG_PATH = CONFIG_DIR / "config.ini"
LEGACY_CONFIG_PATH = Path.home() / ".plan_de_coupe" / "config.ini"
THEMES = ("light", "dark")
LANGUAGE_SETTINGS = (AUTO,) + LANGUAGES

DEFAULTS = {
    "sheet": {
        "format": "A4",
        "orientation": "portrait",
        "assembly_margin_mm": "10",
        "print_margin_mm": "5",
        "custom_width_mm": "",      # format personnalisé seulement
        "custom_height_mm": "",
    },
    "display": {
        "theme": "light",
        "language": AUTO,
    },
    "printer": {
        "x_expected_mm": "180",
        "x_measured_mm": "180",
        "y_expected_mm": "260",
        "y_measured_mm": "260",
    },
}

# ancien format (clés françaises) → nouveau
LEGACY_KEYS = {
    ("feuille", "format"): ("sheet", "format"),
    ("feuille", "orientation"): ("sheet", "orientation"),
    ("feuille", "marge_assemblage_mm"): ("sheet", "assembly_margin_mm"),
    ("feuille", "marge_impression_mm"): ("sheet", "print_margin_mm"),
    ("affichage", "theme"): ("display", "theme"),
    ("impression", "x_attendue_mm"): ("printer", "x_expected_mm"),
    ("impression", "x_mesuree_mm"): ("printer", "x_measured_mm"),
    ("impression", "y_attendue_mm"): ("printer", "y_expected_mm"),
    ("impression", "y_mesuree_mm"): ("printer", "y_measured_mm"),
}
LEGACY_VALUES = {"paysage": "landscape", "clair": "light", "sombre": "dark"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    sheet: SheetSettings = field(default_factory=SheetSettings)
    theme: str = "light"
    language: str = AUTO
    correction: PrintCorrection = NO_CORRECTION


def _choices(values) -> str:
    return " | ".join(values)


def _comment(text: str) -> str:
    return "\n".join("# " + line if line else "#" for line in text.split("\n"))


def _sections(values: dict | None = None) -> dict[str, str]:
    """Texte de chaque section, commentaires dans la langue courante ; valeurs données, défauts sinon."""
    v = {key: value for section in DEFAULTS.values() for key, value in section.items()}
    v.update(values or {})
    sheet = [
        "[sheet]",
        _comment(_("Sheet format: {choices}").format(choices=_choices(FORMATS))),
        f"format = {v['format']}",
        "",
        _comment(_("Sheet orientation: {choices}").format(choices=_choices(ORIENTATIONS))),
        f"orientation = {v['orientation']}",
        "",
        _comment(_("Assembly margin, in mm: from the sheet edge to the cutting frame (dashed line).\n"
                   "Sheets are cut along this frame and butted together. Default: 10")),
        f"assembly_margin_mm = {v['assembly_margin_mm']}",
        "",
        _comment(_("Print margin, in mm: non-printable area of the printer, from the edge.\n"
                   "Must be smaller than the assembly margin. Default: 5 (measure it with the test page)")),
        f"print_margin_mm = {v['print_margin_mm']}",
        "",
        _comment(_("Custom format only (format = custom): sheet width and height, in mm,\n"
                   "from {min} to {max}. The short side is the width in portrait.").format(
            min=fmt_g(CUSTOM_RANGE_MM[0]), max=fmt_g(CUSTOM_RANGE_MM[1]))),
        f"custom_width_mm = {v['custom_width_mm']}",
        f"custom_height_mm = {v['custom_height_mm']}",
    ]
    display = [
        "[display]",
        _comment(_("Screen theme: {choices}  (the PDF is always black on white)").format(
            choices=_choices(THEMES))),
        f"theme = {v['theme']}",
        "",
        _comment(_("Interface language: {choices}  (auto = system language; restart required)").format(
            choices=_choices(LANGUAGE_SETTINGS))),
        f"language = {v['language']}",
    ]
    printer = [
        "[printer]",
        _comment(_("Printer scale correction. Measure on a test page printed WITHOUT correction\n"
                   "(Page setup > Printer test page, without correction), then enter for each axis\n"
                   "the expected length and the measured length, in mm:\n"
                   "  x = short side of the paper, y = long side of the paper (in portrait and landscape).\n"
                   "  Possible lengths: rulers (180 in x, 260 in y) or the cutting frame\n"
                   "  (A4: 190 in x, 277 in y). The longest length gives the most accurate correction.\n"
                   "Expected = measured: no correction. Correction limited to ±5 %.")),
        f"x_expected_mm = {v['x_expected_mm']}",
        f"x_measured_mm = {v['x_measured_mm']}",
        f"y_expected_mm = {v['y_expected_mm']}",
        f"y_measured_mm = {v['y_measured_mm']}",
    ]
    return {"sheet": "\n".join(sheet), "display": "\n".join(display), "printer": "\n".join(printer)}


def render(values: dict | None = None) -> str:
    """Texte complet du fichier, valeurs données (clé → valeur), défauts pour les autres."""
    header = _comment(_("CutLayout preferences\n"
                        "After editing: in the application, File > Reload preferences (F5).\n"
                        "Lines starting with # are comments."))
    return "\n\n".join([header, *_sections(values).values()]) + "\n"


def _add_missing_sections(path: Path, cp: configparser.ConfigParser) -> configparser.ConfigParser:
    """Complète un fichier existant avec les sections commentées qui lui manquent (valeurs par défaut)."""
    missing = [text for name, text in _sections().items() if not cp.has_section(name)]
    if not missing:
        return cp
    text = path.read_text(encoding="utf-8").rstrip("\n")
    path.write_text("\n\n".join([text, *missing]) + "\n", encoding="utf-8")
    return _read(path)


def _read(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    try:
        cp.read_string(path.read_text(encoding="utf-8"), source=str(path))
    except configparser.Error as e:
        raise ConfigError(_("{path}: unreadable file: {error}").format(path=path, error=e)) from e
    return cp


def _is_legacy(cp: configparser.ConfigParser) -> bool:
    return any(cp.has_section(s) for s in ("feuille", "affichage", "impression"))


def _migrate_legacy(path: Path, cp: configparser.ConfigParser) -> configparser.ConfigParser:
    """Convertit un fichier aux clés françaises ; l'original est conservé (config.ini.old).
    L'application n'existait qu'en français : la langue est fixée à « fr »."""
    if not _is_legacy(cp):
        return cp
    values = {"language": "fr"}
    for (old_section, old_key), (_section, new_key) in LEGACY_KEYS.items():
        if cp.has_option(old_section, old_key):
            value = cp.get(old_section, old_key).strip()
            values[new_key] = LEGACY_VALUES.get(value, value)
    backup = path.with_name(path.name + ".old")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(render(values), encoding="utf-8")
    return _read(path)


def _parse(cp: configparser.ConfigParser) -> Config:
    unknown_sections = sorted(set(cp.sections()) - set(DEFAULTS))
    if unknown_sections:
        raise ConfigError(_("unknown section(s): {names} (known: {known})").format(
            names=", ".join(unknown_sections), known=", ".join(DEFAULTS)))
    values = {}
    for section, defaults in DEFAULTS.items():
        if cp.has_section(section):
            unknown = sorted(set(cp[section]) - set(defaults))
            if unknown:
                raise ConfigError(_("[{section}] unknown key(s): {names} (known: {known})").format(
                    section=section, names=", ".join(unknown), known=", ".join(defaults)))
        for key, default in defaults.items():
            values[key] = cp.get(section, key, fallback=default).strip()
    for key, allowed in (("theme", THEMES), ("language", LANGUAGE_SETTINGS)):
        if values[key] not in allowed:
            raise ConfigError(_("{key}: unknown value {value!r} (possible: {choices})").format(
                key=key, value=values[key], choices=_choices(allowed)))

    def num(key):
        if key.startswith("custom_") and not values[key]:
            return 0.0           # non renseigné : refusé par SheetSettings si format = custom
        try:
            return float(values[key].replace(",", "."))
        except ValueError:
            raise ConfigError(_("{key}: number expected, got {value!r}").format(key=key, value=values[key])) from None
    try:
        sheet = SheetSettings(format=values["format"], orientation=values["orientation"],
                              assembly_margin=num("assembly_margin_mm"), print_margin=num("print_margin_mm"),
                              custom_width=num("custom_width_mm"), custom_height=num("custom_height_mm"))
        correction = PrintCorrection(num("x_expected_mm"), num("x_measured_mm"),
                                     num("y_expected_mm"), num("y_measured_mm"))
    except (MosaicError, CorrectionError) as e:
        raise ConfigError(str(e)) from e
    return Config(sheet=sheet, theme=values["theme"], language=values["language"], correction=correction)


def adopt_legacy_config(path: Path = CONFIG_PATH, legacy: Path = LEGACY_CONFIG_PATH) -> Path | None:
    """Copie la configuration de l'ancien nom de l'application si la nouvelle n'existe pas encore.
    Renvoie le fichier copié, ou None si rien n'a été fait."""
    if path.exists() or not legacy.is_file():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, path)
    return legacy


def read_language(path: Path = CONFIG_PATH) -> str:
    """Réglage de langue seul (avant le chargement complet), « auto » si absent ou illisible."""
    try:
        cp = _read(path)
    except (ConfigError, OSError):
        return AUTO
    if _is_legacy(cp):
        return "fr"
    value = cp.get("display", "language", fallback=AUTO).strip()
    return value if value in LANGUAGE_SETTINGS else AUTO


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Lit la configuration ; crée le fichier commenté avec les valeurs par défaut s'il n'existe pas."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(), encoding="utf-8")
    cp = _add_missing_sections(path, _migrate_legacy(path, _read(path)))
    try:
        return _parse(cp)
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from e


def save_value(key: str, value: str, path: Path = CONFIG_PATH) -> None:
    """Enregistre une valeur de la section [display] en ne modifiant que sa ligne."""
    allowed = {"theme": THEMES, "language": LANGUAGE_SETTINGS}[key]
    if value not in allowed:
        raise ConfigError(_("{key}: unknown value {value!r} (possible: {choices})").format(
            key=key, value=value, choices=_choices(allowed)))
    _write_values("display", {key: value}, path)


def _write_values(section: str, values: dict[str, str], path: Path) -> None:
    """Ne réécrit que les lignes des clés données (commentaires conservés) ; clé absente : ajoutée
    sous l'en-tête de sa section."""
    if not path.exists():
        load_config(path)
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        line = re.compile(rf"^(\s*{key}\s*=).*$", re.MULTILINE)
        if line.search(text):
            text = line.sub(lambda m: f"{m.group(1)} {value}", text, count=1)
        elif f"[{section}]" in text:
            text = text.replace(f"[{section}]", f"[{section}]\n{key} = {value}", 1)
        else:
            text = text.rstrip("\n") + f"\n\n[{section}]\n{key} = {value}\n"
    path.write_text(text, encoding="utf-8")


def save_sheet_defaults(sheet: SheetSettings, path: Path = CONFIG_PATH) -> None:
    """Format, orientation et marge d'assemblage par défaut des nouveaux plans. La marge d'impression,
    réglage de l'imprimante, n'est pas modifiée ici."""
    values = {"format": sheet.format, "orientation": sheet.orientation,
              "assembly_margin_mm": f"{sheet.assembly_margin:g}"}
    if sheet.format == CUSTOM:
        values.update(custom_width_mm=f"{sheet.custom_width:g}", custom_height_mm=f"{sheet.custom_height:g}")
    _write_values("sheet", values, path)
