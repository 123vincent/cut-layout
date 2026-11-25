"""
pyinstaller_build.py — construit CutLayout en application autonome, sans installation de Python.

Usage :
    .venv\\Scripts\\python pyinstaller_build.py

Résultat (dossier « portable », à copier ou dézipper n'importe où) :
    Windows : pyinstaller_dist/CutLayout/CutLayout.exe   + pyinstaller_dist/CutLayout-<version>-windows.zip
    macOS   : pyinstaller_dist/CutLayout.app             + pyinstaller_dist/CutLayout-<version>-macos.zip
    Linux   : pyinstaller_dist/CutLayout/CutLayout       + pyinstaller_dist/CutLayout-<version>-linux.zip

PyInstaller ne fait pas de compilation croisée : chaque système se construit sur ce système
(même script, même .spec). Le build Windows est le seul vérifié à ce jour.
"""
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "CutLayout"
SPEC_FILE = ROOT / f"pyinstaller_{APP_NAME}.spec"
BUILD_DIR = ROOT / "pyinstaller_build"
DIST_DIR = ROOT / "pyinstaller_dist"
VERSION_INFO = ROOT / "pyinstaller_version_info.txt"
LOG_FILE = ROOT / "pyinstaller_build_logs.txt"
DESCRIPTION = "Plan de coupe imprimable 1:1 pour patrons Seamly2D"
PLATFORMS = {"win32": "windows", "darwin": "macos"}


def read_version() -> str:
    text = (ROOT / "src" / "cut_layout" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def generate_version_info(version: str) -> None:
    """Propriétés du fichier .exe (Windows) : nom, description, version."""
    parts = (version.split(".") + ["0", "0", "0"])[:3]
    v = ", ".join(parts + ["0"])
    VERSION_INFO.write_text(f"""# {APP_NAME} — propriétés du .exe (généré par pyinstaller_build.py)
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v}), prodvers=({v}), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable(u'040904B0', [
      StringStruct(u'FileDescription', u'{APP_NAME} — {DESCRIPTION}'),
      StringStruct(u'FileVersion', u'{version}'),
      StringStruct(u'InternalName', u'{APP_NAME}'),
      StringStruct(u'OriginalFilename', u'{APP_NAME}.exe'),
      StringStruct(u'ProductName', u'{APP_NAME}'),
      StringStruct(u'ProductVersion', u'{version}'),
    ])]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")


def _force_delete(func, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def clear_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=_force_delete)


def build() -> bool:
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
           "--workpath", str(BUILD_DIR), "--distpath", str(DIST_DIR), str(SPEC_FILE)]
    result = subprocess.run(cmd, capture_output=True, cwd=ROOT)
    LOG_FILE.write_text(result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"),
                        encoding="utf-8")
    if result.returncode != 0:
        print(f"[ERREUR] Échec du build — voir {LOG_FILE.name}")
        return False
    return True


def make_zip(version: str) -> Path:
    system = PLATFORMS.get(sys.platform, "linux")
    target = DIST_DIR / (f"{APP_NAME}.app" if sys.platform == "darwin" else APP_NAME)
    base = DIST_DIR / f"{APP_NAME}-{version}-{system}"
    return Path(shutil.make_archive(str(base), "zip", root_dir=DIST_DIR, base_dir=target.name))


def folder_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1_048_576


if __name__ == "__main__":
    t0 = datetime.now()
    version = read_version()
    print(f"[INFO] {APP_NAME} {version} — {platform.system()} {platform.machine()}, Python {platform.python_version()}")
    clear_dir(BUILD_DIR)
    clear_dir(DIST_DIR)
    if sys.platform == "win32":
        generate_version_info(version)
    ok = build()
    clear_dir(BUILD_DIR)
    VERSION_INFO.unlink(missing_ok=True)
    if ok:
        folder = DIST_DIR / APP_NAME
        print(f"[OK]   {folder}  ({folder_size_mb(folder):.0f} Mo)")
        archive = make_zip(version)
        print(f"[OK]   {archive}  ({archive.stat().st_size / 1_048_576:.0f} Mo)")
    print(f"[INFO] {'Build terminé' if ok else 'Build ÉCHOUÉ'} — {datetime.now() - t0}")
    sys.exit(0 if ok else 1)
