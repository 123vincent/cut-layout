"""Import d'un patron Seamly2D (.sm2d + .smis) au-dessus de sm2d_geom.

Le calcul de la géométrie est entièrement délégué à sm2d_geom (validé contre Seamly2D :
docs/NOTE_validation_geometrie.md).
Ce module ajoute :
- un contrôle préalable du contenu : tout ce que sm2d_geom ignorerait ou ne sait pas
  calculer est refusé avec un message qui nomme l'élément ;
- le contrôle de cohérence d'unité entre .sm2d et .smis ;
- la conversion en mm (unité interne).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from sm2d_geom import FUNCTION_NAMES, Model

from ..i18n import _
from ..model.piece import Piece
from ..units import mm_per_unit

SUPPORTED_POINTS = {"single", "endLine", "alongLine", "intersectXY"}
SUPPORTED_SPLINES = {"simpleInteractive", "pathInteractive"}
IGNORED_CALCULATION_TAGS = {"line"}          # tracé entre deux points, sans effet sur les pièces
SUPPORTED_NODES = {"NodePoint", "NodeSpline", "NodeSplinePath"}
KNOWN_NODE_ATTRIBUTES = {"idObject", "type", "reverse"}

DEFAULT_SAMPLES_PER_SEGMENT = 200
# appel de fonction dans une formule : identifiant suivi d'une parenthèse ouvrante
_CALL = re.compile(r"(?<![\w#.])([A-Za-z_]\w*)\s*\(")
# attributs d'un élément de <calculation> qui ne sont pas des formules (texte libre, références)
NON_FORMULA_ATTRIBUTES = {"name", "type", "id", "notes", "description", "lineColor", "color", "typeLine",
                          "penStyle", "lineWeight", "mx", "my", "showLabel", "inUse"}


class Sm2dImportError(Exception):
    pass


class UnsupportedContent(Sm2dImportError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(_("unsupported content:") + "\n- " + "\n- ".join(problems))


def measurements_path(sm2d_path: str | Path) -> Path | None:
    """Chemin du .smis déclaré dans <measurements>, résolu par rapport au dossier du .sm2d.

    Renvoie None si le .sm2d n'en déclare pas. Le fichier n'est pas forcément présent.
    """
    sm2d_path = Path(sm2d_path)
    ref = (ET.parse(sm2d_path).getroot().findtext("measurements") or "").strip()
    if not ref:
        return None
    p = Path(ref)
    return p if p.is_absolute() else (sm2d_path.parent / p).resolve()


def unknown_functions(formula: str) -> list[str]:
    """Fonctions appelées dans une formule et absentes de sm2d_geom (noms sensibles à la casse)."""
    return sorted({name for name in _CALL.findall(formula) if name not in FUNCTION_NAMES})


def find_unsupported(root: ET.Element) -> list[str]:
    """Liste des éléments du .sm2d que sm2d_geom ignorerait ou refuserait."""
    problems = []
    variables = root.find("variables")
    for v in variables if variables is not None else []:
        formula = v.get("formula") or ""
        for fn in unknown_functions(formula):
            problems.append(_("variable {name}: unknown function {function!r} in {formula!r}").format(
                name=v.get("name"), function=fn, formula=formula))
    for blk in root.findall("draftBlock"):
        bname = blk.get("name")
        calc = blk.find("calculation")
        for el in calc if calc is not None else []:
            t = el.get("type")
            obj = f"{el.get('name') or '?'} (id {el.get('id')})"
            for attr, value in el.attrib.items():
                if attr not in NON_FORMULA_ATTRIBUTES:
                    for fn in unknown_functions(value):
                        problems.append(_("[{block}] {object}: unknown function {function!r} in {formula!r}").format(
                            block=bname, object=obj, function=fn, formula=value))
            if el.tag == "point":
                if t not in SUPPORTED_POINTS:
                    problems.append(_("[{block}] point {object}: unsupported type {type!r}").format(
                        block=bname, object=obj, type=t))
            elif el.tag == "spline":
                if t not in SUPPORTED_SPLINES:
                    problems.append(_("[{block}] curve {object}: unsupported type {type!r}").format(
                        block=bname, object=obj, type=t))
            elif el.tag not in IGNORED_CALCULATION_TAGS:
                problems.append(_("[{block}] element <{tag}> {object}, type {type!r}: not supported").format(
                    block=bname, tag=el.tag, object=obj, type=t))
        pieces = blk.find("pieces")
        for pc in pieces if pieces is not None else []:
            nodes = pc.find("nodes")
            for node in nodes if nodes is not None else []:
                t = node.get("type")
                if t not in SUPPORTED_NODES:
                    problems.append(_("[{block}] piece {piece!r}: unsupported node type {type!r}").format(
                        block=bname, piece=pc.get("name"), type=t))
                extra = sorted(set(node.attrib) - KNOWN_NODE_ATTRIBUTES)
                if extra:
                    problems.append(_("[{block}] piece {piece!r}: unsupported node attribute(s) {attributes} "
                                      "(effect on the outline UNKNOWN)").format(
                        block=bname, piece=pc.get("name"), attributes=", ".join(extra)))
    return problems


class Sm2dPattern:
    """Patron chargé : liste des pièces et calcul de leur contour net en mm."""

    def __init__(self, sm2d_path: str | Path, smis_path: str | Path,
                 samples_per_segment: int = DEFAULT_SAMPLES_PER_SEGMENT):
        self.sm2d_path = Path(sm2d_path)
        self.smis_path = Path(smis_path)
        self.samples_per_segment = samples_per_segment
        try:
            root = ET.parse(self.sm2d_path).getroot()
            smis_root = ET.parse(self.smis_path).getroot()
        except ET.ParseError as e:
            raise Sm2dImportError(_("unreadable XML file: {error}").format(error=e)) from e

        problems = find_unsupported(root)
        if problems:
            raise UnsupportedContent(problems)

        self.unit = (root.findtext("unit") or "").strip()
        smis_unit = (smis_root.findtext("unit") or "").strip()
        if self.unit != smis_unit:
            raise Sm2dImportError(_("different units: pattern {pattern!r}, measurements {measurements!r}").format(
                pattern=self.unit, measurements=smis_unit))
        try:
            self._k = mm_per_unit(self.unit)
        except ValueError as e:
            raise Sm2dImportError(str(e)) from e

        try:
            self.model = Model(str(self.sm2d_path), str(self.smis_path))
        # NameError : identifiant inconnu dans une formule (eval le signale ainsi) ; TypeError : mauvais nombre
        # d'arguments ; ValueError : aussi hors domaine (asin(2)) ; OverflowError : exp(1000)
        except (KeyError, NameError, TypeError, ValueError, NotImplementedError, ZeroDivisionError,
                OverflowError) as e:
            raise Sm2dImportError(_("cannot compute the pattern: {error_type}: {error}").format(
                error_type=type(e).__name__, error=e)) from e

        self._pieces: dict[str, tuple[str, ET.Element]] = {}
        for block, pc in self.model.pieces():
            name = pc.get("name")
            if name in self._pieces:
                raise Sm2dImportError(_("duplicate piece name: {name!r}").format(name=name))
            self._pieces[name] = (block, pc)

    def piece_names(self) -> list[str]:
        """Noms des pièces, dans l'ordre du fichier."""
        return list(self._pieces)

    def piece(self, name: str) -> Piece:
        block, pc = self._pieces[name]
        m, k = self.model, self._k
        outline = m.piece_outline(pc, n=self.samples_per_segment)
        nodes = {}
        for node in pc.find("nodes"):
            obj = m._modeling[node.get("idObject")]
            if node.get("type") == "NodePoint":
                names = [m.pt_by_id[obj]]
            else:
                names = m.curve_by_id[obj].nodes
            for nm in names:
                x, y = m.pt[nm]
                nodes[nm] = (x * k, y * k)
        data = pc.find("data")
        return Piece(
            name=name,
            block=block,
            outline=tuple((x * k, y * k) for x, y in outline),
            nodes=nodes,
            on_fold=data is not None and data.get("onFold") == "true",
            forbid_flipping=pc.get("forbidFlipping") == "true",
        )
