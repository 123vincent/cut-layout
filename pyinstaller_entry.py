"""Point d'entrée du build PyInstaller (cut_layout/__main__.py fait un import relatif, inutilisable comme script)."""
import sys

from cut_layout.app import main

if __name__ == "__main__":
    sys.exit(main())
