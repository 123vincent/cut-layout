# pyinstaller_CutLayout.spec
# Build : .venv\Scripts\python pyinstaller_build.py   (Windows, macOS ou Linux : construire sur chaque système)
#
# Application en un dossier (« onedir ») : démarrage rapide, aucune installation, dossier copiable tel quel.
# Les préférences restent dans le compte de l'utilisateur (~/.cut_layout/config.ini), pas dans ce dossier.

import os
import sys

spec_dir = os.path.dirname(os.path.abspath(SPEC))
src = os.path.join(spec_dir, 'src')
pkg = os.path.join(src, 'cut_layout')

# Ressources chargées par chemin relatif au module (Path(__file__).parent) : même arborescence dans le build
datas = [
    (os.path.join(pkg, 'ui', 'styles'), 'cut_layout/ui/styles'),
    (os.path.join(pkg, 'locale', 'fr', 'LC_MESSAGES', 'cut_layout.mo'), 'cut_layout/locale/fr/LC_MESSAGES'),
]

a = Analysis(
    [os.path.join(spec_dir, 'pyinstaller_entry.py')],
    pathex=[src],                     # sm2d_geom (module de premier niveau) et le paquet cut_layout
    datas=datas,
    hiddenimports=['sm2d_geom'],
    excludes=[
        # inutiles à l'application (tests, outils de développement, extras)
        'pytest', 'pdfplumber', 'pypdfium2', 'babel', 'matplotlib', 'numpy', 'tkinter',
        # modules Qt non utilisés : réduisent fortement la taille
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.Qt3DCore',
        'PySide6.QtMultimedia', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtPdf',
        'PySide6.QtNetwork', 'PySide6.QtOpenGL', 'PySide6.QtSql', 'PySide6.QtTest',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CutLayout',
    console=False,                    # application fenêtrée
    version='pyinstaller_version_info.txt' if sys.platform == 'win32' else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name='CutLayout')

if sys.platform == 'darwin':
    app = BUNDLE(coll, name='CutLayout.app', bundle_identifier=None)
