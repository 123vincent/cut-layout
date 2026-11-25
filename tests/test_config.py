import configparser

import pytest

from cut_layout.config import ConfigError, adopt_legacy_config, load_config, read_language, render, save_value
from cut_layout.i18n import set_language


def write(p, text):
    p.write_text(text, encoding="utf-8")
    return p


def test_fichier_cree_avec_les_valeurs_par_defaut(tmp_path):
    p = tmp_path / "sous" / "config.ini"
    c = load_config(p)
    assert (c.sheet.format, c.sheet.orientation, c.sheet.assembly_margin, c.sheet.print_margin, c.theme,
            c.language) == ("A4", "portrait", 10.0, 5.0, "light", "auto")


def test_fichier_cree_liste_les_valeurs_possibles(tmp_path):
    load_config(tmp_path / "config.ini")
    text = (tmp_path / "config.ini").read_text(encoding="utf-8")
    assert "# Sheet format: A4 | A3" in text
    assert "# Sheet orientation: portrait | landscape" in text
    assert "# Screen theme: light | dark" in text
    assert "# Interface language: auto | en | fr" in text


def test_commentaires_dans_la_langue_de_l_interface_cles_en_anglais(tmp_path):
    set_language("fr")
    load_config(tmp_path / "config.ini")
    text = (tmp_path / "config.ini").read_text(encoding="utf-8")
    assert "# Format de la feuille : A4 | A3" in text
    assert "[sheet]" in text and "assembly_margin_mm = 10" in text and "x_measured_mm = 180" in text


def test_valeurs_lues(tmp_path):
    p = write(tmp_path / "config.ini", render({"format": "A3", "orientation": "landscape", "print_margin_mm": "4,5"}))
    c = load_config(p)
    assert c.sheet.cell_size == (400.0, 277.0) and c.sheet.print_margin == 4.5


def test_cles_absentes_valeurs_par_defaut(tmp_path):
    c = load_config(write(tmp_path / "config.ini", "[sheet]\nformat = A3\n"))
    assert (c.sheet.format, c.sheet.orientation, c.theme) == ("A3", "portrait", "light")


@pytest.mark.parametrize("text,msg", [
    ("[sheet]\nprint_margin_mm = 10\n", "smaller"),
    ("[sheet]\nformat = A5\n", "unknown format"),
    ("[display]\ntheme = black\n", "possible: light \\| dark"),
    ("[display]\nlanguage = xx\n", "possible: auto \\| en \\| fr"),
    ("[sheet]\nmargin = 3\n", "unknown key\\(s\\)"),
    ("[sheets]\nformat = A4\n", "unknown section\\(s\\)"),
    ("[sheet]\nassembly_margin_mm = ten\n", "ten"),
    ("format = A4\n", "unreadable"),
])
def test_valeurs_invalides_refusees(tmp_path, text, msg):
    with pytest.raises(ConfigError, match=msg):
        load_config(write(tmp_path / "config.ini", text))


def test_message_d_erreur_traduit(tmp_path):
    set_language("fr")
    with pytest.raises(ConfigError, match="format inconnu"):
        load_config(write(tmp_path / "config.ini", "[sheet]\nformat = A5\n"))


@pytest.mark.parametrize("key,value", [("theme", "dark"), ("language", "fr")])
def test_enregistrer_une_valeur_conserve_commentaires_et_valeurs(tmp_path, key, value):
    p = write(tmp_path / "config.ini", render({"format": "A3"}))
    save_value(key, value, p)
    assert p.read_text(encoding="utf-8") == render({"format": "A3", key: value})
    assert getattr(load_config(p), key) == value


def test_lecture_de_la_langue_seule(tmp_path):
    assert read_language(tmp_path / "absent.ini") == "auto"
    assert read_language(write(tmp_path / "a.ini", render({"language": "fr"}))) == "fr"
    assert read_language(write(tmp_path / "b.ini", "[display]\nlanguage = xx\n")) == "auto"
    assert read_language(write(tmp_path / "c.ini", "pas un ini")) == "auto"


def test_correction_d_impression_lue(tmp_path):
    p = write(tmp_path / "config.ini", render({"x_expected_mm": "190", "x_measured_mm": "188,8",
                                                 "y_expected_mm": "277", "y_measured_mm": "276.7"}))
    c = load_config(p).correction
    assert c.fx == pytest.approx(190 / 188.8) and c.fy == pytest.approx(277 / 276.7)


def test_correction_par_defaut_aucune(tmp_path):
    assert load_config(tmp_path / "config.ini").correction.is_identity


def test_correction_aberrante_refusee(tmp_path):
    with pytest.raises(ConfigError, match="5 %"):
        load_config(write(tmp_path / "config.ini", "[printer]\nx_measured_mm = 18\n"))


def test_sections_manquantes_ajoutees(tmp_path):
    p = write(tmp_path / "config.ini", "# my notes\n[sheet]\nformat = A3\n")
    c = load_config(p)
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# my notes\n[sheet]\nformat = A3\n")
    assert "[printer]" in text and "x_measured_mm = 180" in text and "language = auto" in text
    assert c.sheet.format == "A3" and c.correction.is_identity
    load_config(p)
    assert p.read_text(encoding="utf-8").count("[printer]") == 1


def test_conversion_de_l_ancien_fichier_aux_cles_francaises(tmp_path):
    old = ("[feuille]\nformat = A3\norientation = paysage\nmarge_assemblage_mm = 12\nmarge_impression_mm = 4\n\n"
           "[affichage]\ntheme = sombre\n\n"
           "[impression]\n# Mesure du 24.11.2026\nx_attendue_mm = 190\nx_mesuree_mm = 188.8\n"
           "y_attendue_mm = 277\ny_mesuree_mm = 276.7\n")
    p = write(tmp_path / "config.ini", old)
    assert read_language(p) == "fr"
    c = load_config(p)
    assert (c.sheet.format, c.sheet.orientation, c.sheet.assembly_margin, c.sheet.print_margin, c.theme,
            c.language) == ("A3", "landscape", 12.0, 4.0, "dark", "fr")
    assert (c.correction.fx, c.correction.fy) == pytest.approx((190 / 188.8, 277 / 276.7))
    assert (tmp_path / "config.ini.old").read_text(encoding="utf-8") == old
    cp = configparser.ConfigParser()
    cp.read(p, encoding="utf-8")
    assert cp.sections() == ["sheet", "display", "printer"]
    assert cp["printer"]["x_measured_mm"] == "188.8"


def test_reprise_de_la_configuration_de_plan_de_coupe(tmp_path):
    """Premier lancement après le renommage : l'ancien config.ini est copié, l'ancien dossier reste intact."""
    old_dir = tmp_path / ".plan_de_coupe"
    old_dir.mkdir()
    legacy = write(old_dir / "config.ini", "[printer]\nx_expected_mm = 190\nx_measured_mm = 188,8\n")
    new = tmp_path / ".cut_layout" / "config.ini"
    assert adopt_legacy_config(new, legacy) == legacy
    assert new.read_text(encoding="utf-8") == legacy.read_text(encoding="utf-8")
    assert legacy.is_file()
    assert load_config(new).correction.fx == pytest.approx(190 / 188.8)


def test_pas_de_reprise_si_nouvelle_configuration_ou_pas_d_ancienne(tmp_path):
    new = write(tmp_path / "new.ini", "[display]\ntheme = dark\n")
    legacy = write(tmp_path / "old.ini", "[display]\ntheme = light\n")
    assert adopt_legacy_config(new, legacy) is None
    assert "dark" in new.read_text(encoding="utf-8")
    absent = tmp_path / "absent" / "config.ini"
    assert adopt_legacy_config(absent, tmp_path / "nothing.ini") is None
    assert not absent.exists()
