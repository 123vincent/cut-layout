"""Thèmes d'affichage (light, dark) : couleurs de la scène + feuille de style Qt (styles/<thème>.qss).

Pour modifier l'apparence : éditer les couleurs ci-dessous (scène) et le fichier .qss
correspondant (fenêtres, menus, champs). Le PDF n'est jamais concerné : il reste noir sur blanc.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import QApplication

STYLES_DIR = Path(__file__).parent / "styles"


@dataclass(frozen=True)
class SceneColors:
    background: str
    piece: str
    piece_fill_alpha: int
    outside: str
    collision: str
    node: str
    ref: str
    axis: str
    cut_frame: str
    cell_label: str


SCENE_COLORS = {
    "light": SceneColors(background="#ffffff", piece="#1f4e79", piece_fill_alpha=25, outside="#c00000", collision="#b000b0",
                         node="#555555", ref="#c05000", axis="#999999",
                         cut_frame="#7f7f7f", cell_label="#d0d0d0"),
    "dark": SceneColors(background="#1e1f22", piece="#7fb3e6", piece_fill_alpha=35, outside="#ff6b6b", collision="#ff70ff",
                          node="#b0b0b0", ref="#ffa040", axis="#6a6a6a",
                          cut_frame="#8a8a8a", cell_label="#3a3c40"),
}


def apply_app_theme(app: QApplication, theme: str) -> None:
    """Style Fusion (rendu identique sur toutes les plateformes) + feuille de style du thème."""
    app.setStyle("Fusion")
    qss = STYLES_DIR / f"{theme}.qss"
    text = qss.read_text(encoding="utf-8") if qss.exists() else ""
    # les url() d'une feuille de style Qt sont relatives au dossier courant, pas au fichier .qss
    app.setStyleSheet(text.replace("{styles}", STYLES_DIR.as_posix()))
