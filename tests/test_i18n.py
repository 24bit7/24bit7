"""
Languages (stage one of German, 20 Oct 2026): the English stays in the code, i18n.t() swaps in the chosen
language's text, and every piece of text the code asks for has a German version, so the two never drift apart.
"""

import ast
import json
import os
import re
import string

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _de():
    with open(os.path.join(REPO, "locale", "de.json"), encoding="utf-8") as f:
        return json.load(f)


def _asked_for():
    """Every t("...") and N_("...") in the app's code, as (file, English)."""
    found = []
    for name in sorted(os.listdir(REPO)):
        if not name.endswith((".py", ".pyw")) or name.startswith(("apply_", "builtin_keys")):
            continue
        with open(os.path.join(REPO, name), encoding="utf-8") as f:
            tree = ast.parse(f.read(), name)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) in ("t", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.append((name, node.args[0].value))
    return found


def _blanks(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_english_is_unchanged_and_blanks_are_filled(app):
    import i18n
    i18n.set_language("en")
    assert i18n.t("Language") == "Language"
    assert i18n.t("Restart 24bit7 now to switch to {language}?", language="Deutsch") == \
        "Restart 24bit7 now to switch to Deutsch?"


def test_german_comes_from_the_table(app):
    import i18n
    i18n.set_language("de")
    try:
        assert i18n.t("Language") == "Sprache"
        assert "Deutsch" in i18n.t("Restart 24bit7 now to switch to {language}?", language="Deutsch")
        assert i18n.t("Text nobody has translated") == "Text nobody has translated", "falls back to the English"
    finally:
        i18n.set_language("en")


def test_an_unknown_language_means_english(app):
    import i18n
    i18n.set_language("xx")
    assert i18n.LANGUAGE == "en" and i18n.t("Language") == "Language"


def test_every_text_the_code_asks_for_has_german():
    de = _de()
    missing = [f"{name}: {text!r}" for name, text in _asked_for() if text not in de]
    assert not missing, "No German for:\n" + "\n".join(missing)


def test_german_keeps_the_same_blanks():
    wrong = [en for en, de in _de().items() if _blanks(en) != _blanks(de)]
    assert not wrong, f"These lose or gain a {{blank}} in German: {wrong}"


def test_no_german_left_over_for_text_the_code_no_longer_has():
    asked = {text for _, text in _asked_for()}
    stale = [en for en in _de() if en not in asked]
    assert not stale, f"German kept for text no longer in the code: {stale}"


def test_the_setting_is_read_and_stays_out_of_profiles(app):
    import profiles
    app.set_env(UI_LANGUAGE="de")
    assert app.engine.UI_LANGUAGE == "de"
    app.set_env(UI_LANGUAGE="")
    assert app.engine.UI_LANGUAGE == "en"
    assert "UI_LANGUAGE" not in profiles.EXTRA_ENV_KEYS, "the language belongs to the PC, not a profile"


def test_settings_offers_only_finished_languages():
    import i18n
    assert i18n.OFFERED[0] == "en"
    assert set(i18n.OFFERED) <= set(dict(i18n.LANGUAGES))


def test_the_release_carries_the_translations():
    with open(os.path.join(REPO, "build.bat"), encoding="utf-8") as f:
        bat = f.read()
    assert re.search(r'--add-data "locale;locale"', bat)
