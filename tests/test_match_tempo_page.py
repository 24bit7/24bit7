"""
Match Tempo on the playlist page (Ben, 5 Nov 2026): in Playlist Selection for Similar Artists and Similar
Tracks configs. Advanced: Off, Prefer or Strict. Simple: one tick, ticked for Prefer (and for Strict, which
builds as Prefer there). Saved into the config like its other settings.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button


def setting(name, key):
    import buttons
    b = next(x for x in buttons.load() if x["name"] == name)
    return (b.get("settings") or {}).get(key)


def test_advanced_offers_off_prefer_strict_and_saves(app, ui):
    import mode
    s = ui.settings
    mode.set_current("advanced")
    pick_button(ui, "Similar Artists")
    ui.pump(0.4)
    p = s._button_page
    cb = p.tempo_choice
    assert list(cb.cget("values")) == ["Off", "Prefer", "Strict"] and cb.get() == "Off"
    cb.set("Strict")
    cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.3)
    assert setting("Similar Artists", "MATCH_TEMPO_ARTISTS") == "strict"
    pick_button(ui, "Similar Tracks")
    ui.pump(0.4)
    assert s._button_page.tempo_choice.get() == "Off", "each config its own"
    assert not ui.errors, ui.errors[0]


def test_simple_is_a_tick_and_strict_shows_ticked(app, ui):
    import buttons
    import mode
    s = ui.settings
    b = buttons.standard("artists")
    buttons.set_settings(b["id"], dict(b["settings"], MATCH_TEMPO_ARTISTS="strict"))
    pick_button(ui, "Similar Tracks")
    mode.set_current("simple")
    pick_button(ui, "Similar Artists")
    ui.pump(0.4)
    tick = s._button_page.tempo_tick
    assert tick.cget("text") == "Match Tempo" and tick.instate(["selected"]), "Strict reads as ticked in Simple"
    tick.invoke()
    ui.pump(0.3)
    assert setting("Similar Artists", "MATCH_TEMPO_ARTISTS") == "off"
    tick.invoke()
    ui.pump(0.3)
    assert setting("Similar Artists", "MATCH_TEMPO_ARTISTS") == "prefer", "ticked in Simple is Prefer"
    mode.set_current("advanced")
    assert not ui.errors, ui.errors[0]
