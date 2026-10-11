"""
If All Else Fails' spoken message: off unless Say why in the room first is ticked.
"""

from test_if_all_else_fails import nothing_found  # noqa: F401  (the fixture)
from test_gui import ui  # noqa: F401  (the GUI fixture)


def _voice_build(app, e, monkeypatch):
    said = []
    monkeypatch.setattr(e, "speak_in_zone", lambda text, zone, report=print: said.append(text) or 0.1)
    e.OUTPUT_OVERRIDE = "Speakers"
    try:
        r = app.Lines()
        e.create_similar_playlist(report=r, seed_info=e.typed_seed_info("The Beatles", "Something"))
    finally:
        e.OUTPUT_OVERRIDE = None
    return said, r


def test_off_by_default_nothing_spoken(app, nothing_found, monkeypatch):
    app.set_env(FALLBACK_SPOKEN="0")
    said, r = _voice_build(app, nothing_found, monkeypatch)
    assert said == [], said
    assert r.has("I couldn't find a match, shuffling songs in Rock."), r.text()
    assert app.jriver.zone("Speakers").playlist


def test_unset_is_off(app, nothing_found, monkeypatch):
    import os
    monkeypatch.delenv("FALLBACK_SPOKEN", raising=False)
    os.environ.pop("FALLBACK_SPOKEN", None)
    said, _ = _voice_build(app, nothing_found, monkeypatch)
    assert said == [], said


def test_ticked_speaks_first(app, nothing_found, monkeypatch):
    app.set_env(FALLBACK_SPOKEN="1")
    said, _ = _voice_build(app, nothing_found, monkeypatch)
    assert said == ["I couldn't find a match, shuffling songs in Rock"], said


def test_in_profiles():
    import engine
    assert "FALLBACK_SPOKEN" in engine.PROFILE_KEYS["playlist"]


def test_settings_tick_follows_if_all_else_fails(app, ui):
    from tkinter import ttk
    from test_settings_seed_columns import option_page, walk
    page = option_page(ui, option="Similar Tracks")
    ticks = [w for w in walk(page) if isinstance(w, ttk.Checkbutton)]
    main = next(w for w in ticks if w.cget("text") == "If nothing is found")
    spoken = next(w for w in ticks if w.cget("text") == "Say why in the room first")
    if main.instate(["selected"]):
        main.invoke()
    assert spoken.instate(["disabled"])
    main.invoke()
    assert not spoken.instate(["disabled"])
