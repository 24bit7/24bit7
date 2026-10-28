"""
The accent colour (Settings > Other, 28 Oct 2026). The dark theme's green glared on a laptop
screen, so the default was softened from #00ff41 and the colour can be chosen. Every green in
the dark theme and the console comes from one accent; a colour too dark to read is lightened,
one close to magenta (the AI colour) is moved off it, and the logo's "bit" never turns magenta.
"""

import colorsys
import glob
import os

import pytest

import tabs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def default_accent():
    tabs.set_accent("")
    yield
    tabs.set_accent("")


def _hue(colour):
    return colorsys.rgb_to_hls(*tabs._hex_rgb(colour))[0] * 360


def test_default_is_the_softer_green():
    assert tabs.ACCENT == tabs.DEFAULT_ACCENT == "#7bd88f"
    assert tabs.MATRIX_FG == tabs.DEFAULT_ACCENT
    assert all(tabs.DARK[k] == tabs.DEFAULT_ACCENT for k in tabs.ACCENT_KEYS)
    assert tabs.DARK["logo_bit"] == "#f28c28", "green's opposite is magenta, so the logo keeps its orange"


def test_chosen_colour_reaches_the_dark_theme_and_console():
    tabs.set_accent("#3d98ff")
    assert all(tabs.DARK[k] == "#3d98ff" for k in tabs.ACCENT_KEYS)
    assert tabs.MATRIX_FG == "#3d98ff"
    assert tabs.MATRIX_HI == tabs.shade("#3d98ff", 0.3)
    assert tabs.DARK["logo_bit"] not in ("#3d98ff", tabs.DARK["ai_purple"])


def test_blank_or_broken_gives_the_default():
    for value in ("", None, "green", "#12345"):
        assert tabs.tidy_accent(value) == tabs.DEFAULT_ACCENT


def test_too_dark_is_lightened():
    used = tabs.tidy_accent("#000080")
    assert tabs.contrast(used, tabs.DARK["button_bg"]) >= tabs.MIN_CONTRAST
    assert tabs.accent_change("#000080", used) == "lighter"


def test_magenta_is_moved_off():
    for picked in ("#ff00ff", "#cc33cc", "#ff33ff"):
        used = tabs.tidy_accent(picked)
        assert tabs._hue_gap(_hue(used), tabs.AI_HUE) >= tabs.AI_HUE_GAP - 1, picked
        assert tabs.accent_change(picked, used) == "magenta"


def test_logo_bit_is_never_magenta():
    for hue in range(0, 360, 5):
        accent = tabs._rgb_hex(colorsys.hls_to_rgb(hue / 360, 0.6, 0.8))
        bit = tabs.logo_partner(tabs.tidy_accent(accent))
        assert bit == "#f28c28" or tabs._hue_gap(_hue(bit), tabs.AI_HUE) >= 30, accent


def test_review_follows_the_accent(monkeypatch):
    import engine
    import review_gui
    monkeypatch.setattr(engine, "THEME", "dark")
    own = review_gui.tabs   # in the full suite Review can be loaded from the test's copy of the app
    try:
        own.set_accent("#ffb000")
        p = review_gui.palette()
        assert p["accent"] == p["act_fg"] == review_gui.CONSOLE["accent"] == "#ffb000"
        assert p["line"] == own.shade("#ffb000", 0.23)
    finally:
        own.set_accent("")


def test_saved_in_profiles_and_read_at_start(app):
    import engine
    import profiles
    assert "ACCENT_COLOUR" in profiles.EXTRA_ENV_KEYS
    app.set_env(ACCENT_COLOUR="#3d98ff")
    assert engine.ACCENT_COLOUR == "#3d98ff"


def test_no_green_left_hard_coded():
    """The old green written into a screen would ignore the chosen accent."""
    for path in glob.glob(os.path.join(ROOT, "*.py")) + glob.glob(os.path.join(ROOT, "*.pyw")):
        with open(path, encoding="utf-8") as f:
            text = f.read().lower()
        assert "#00ff41" not in text and "#0d4d1c" not in text, os.path.basename(path)

