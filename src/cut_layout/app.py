"""Point d'entrée : cut-layout [patron.sm2d | plan.cutl | ancien plan.pdc]"""
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .config import CONFIG_PATH, Config, ConfigError, adopt_legacy_config, load_config, read_language
from .i18n import _, resolve_language, set_language
from .project import OPEN_EXTENSIONS


def _install_qt_translation(app: QApplication, language: str) -> None:
    """Boutons et dialogues standard de Qt (OK, Annuler, Oui…) dans la langue choisie."""
    if language == "en":
        return
    translator = QTranslator(app)
    if translator.load(f"qtbase_{language}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("CutLayout")
    app.setApplicationVersion(__version__)
    adopted = adopt_legacy_config(CONFIG_PATH)
    # la langue doit être fixée avant le chargement complet : les messages d'erreur de la configuration
    # et les commentaires d'un fichier créé à la première ouverture sont traduits
    language = resolve_language(read_language(CONFIG_PATH), QLocale.system().name())
    set_language(language)
    _install_qt_translation(app, language)

    from .ui.main_window import MainWindow
    from .ui.theme import apply_app_theme
    try:
        config, error = load_config(CONFIG_PATH), None
    except ConfigError as e:
        config, error = Config(), e
    apply_app_theme(app, config.theme)
    w = MainWindow(config, CONFIG_PATH)
    w.show()
    if adopted is not None:
        w.statusBar().showMessage(_("Configuration copied from {path}").format(path=adopted), 10000)
    if error is not None:
        QMessageBox.warning(w, _("Configuration"), f"{error}\n\n" + _("Default values used."))
    if len(argv) > 1:
        if argv[1].lower().endswith(OPEN_EXTENSIONS):
            w.open_project(argv[1])
        else:
            w.open_pattern(argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
