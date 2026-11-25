"""Gestion des traductions (Babel, extra « dev »).

    .venv\\Scripts\\python tools\\i18n.py update    # extrait les textes du code, met à jour les .po
    .venv\\Scripts\\python tools\\i18n.py compile   # .po → .mo (fichiers lus par l'application)
    .venv\\Scripts\\python tools\\i18n.py init de   # nouvelle langue (puis l'ajouter à i18n.LANGUAGES)

Traduire : éditer locale/<langue>/LC_MESSAGES/cut_layout.po (Poedit ou éditeur de texte),
puis « compile ». Le test tests/test_i18n.py vérifie que tout est traduit et compilé.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "cut_layout"
LOCALE = PACKAGE / "locale"
POT = LOCALE / "cut_layout.pot"
DOMAIN = "cut_layout"


def pybabel(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "babel.messages.frontend", *args], check=True, cwd=ROOT)


def extract() -> None:
    LOCALE.mkdir(parents=True, exist_ok=True)
    pybabel("extract", "--no-location", "--sort-output", "--add-comments=TRANSLATORS:",
            "--keywords=_", "--keywords=ngettext:1,2", "--project=CutLayout",
            "-o", str(POT), str(PACKAGE))


def main(argv: list[str]) -> None:
    command = argv[0] if argv else "update"
    if command == "update":
        extract()
        pybabel("update", "--no-fuzzy-matching", "-D", DOMAIN, "-i", str(POT), "-d", str(LOCALE))
    elif command == "compile":
        pybabel("compile", "--statistics", "-D", DOMAIN, "-d", str(LOCALE))
    elif command == "init":
        extract()
        pybabel("init", "-D", DOMAIN, "-i", str(POT), "-d", str(LOCALE), "-l", argv[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
