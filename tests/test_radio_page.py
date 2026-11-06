"""
Radio's page under Settings > Playlist Settings (Ben, 6 Nov 2026): Lane, Sources, Playlist Selection and Filters
in one box; Moderator, Deep Cuts and Shortcut under it in Advanced. No Consensus, Drift, Mix, Non-stop, Hidden
Tracks, If All Else Fails or Run After Building, and no Add Another Config. What it sets is what Radio builds with.
"""

from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, shown, shown_labels

NOT_RADIO = ("Consensus", "Drift", "Mix", "Non-stop", "Hidden Tracks", "If All Else Fails", "Run After Building",
             "+ Add Another Config", "+ Add a Config", "When Seed is Current Track", "When Seed is Playing Now",
             "Separate Settings for Review Mode", "Config 1")


def texts_of(s):
    inner = s._button_inner
    return shown_labels(inner) + [w.cget("text") for w in shown(inner) if isinstance(w, ttk.Checkbutton)]


def made_radio():
    import buttons
    made, _page = buttons.add_from_choice(("template", "radio"))
    return made


def test_radio_page_shows_its_own_sections(app, ui):
    import hotkeys
    import mode
    mode.set_current("advanced")
    made_radio()
    pick_button(ui, "Radio")
    s = ui.settings
    texts = texts_of(s)
    for here in ("Lane", "Sources", "Must agree", "Playlist Selection", "Each Round", "Filters", "Moderator", "Deep Cuts"):
        assert here in texts, (here, texts)
    if hotkeys.AVAILABLE:
        assert "Shortcut" in texts
    for gone in NOT_RADIO:
        assert gone not in texts, gone
    assert not ui.errors, ui.errors[0]


def test_what_the_page_sets_is_saved_on_radio(app, ui):
    import buttons
    import mode
    mode.set_current("advanced")
    made = made_radio()
    p = pick_button(ui, "Radio")
    p.vars["TRACKS_PER_ARTIST_POOL"].set("8")
    p.vars["TRACKS_PER_ARTIST_PICK"].set("4")
    ui.pump(0.2)
    p.vars["AI_MODERATOR_ARTISTS"].set("Strict")
    p.save()
    saved = buttons.get(made["id"])["settings"]
    assert saved["TRACKS_PER_ARTIST_PICK"] == "4" and saved["TRACKS_PER_ARTIST_POOL"] == "8", saved
    assert saved["AI_MODERATOR_ARTISTS"] == "strict"
    assert set(saved) <= set(buttons.RADIO_KEYS), "only Radio's keys"
    assert buttons.get(made["id"])["kind"] == "radio" and buttons.configs(buttons.get(made["id"])) == []
    assert not ui.errors, ui.errors[0]


def test_lane_picks_a_lane_or_last_played(app, ui, monkeypatch):
    import buttons
    import radio
    monkeypatch.setattr(radio, "lanes", lambda include_children=False: [
        {"id": "1", "name": "Classic Rock"}, {"id": "2", "name": "Jazz"}])
    made = made_radio()
    pick_button(ui, "Radio")
    cb = ui.settings._radio_lane_box
    assert list(cb.cget("values")) == ["Last Played", "Classic Rock", "Jazz"] and cb.get() == "Last Played"
    cb.set("Jazz")
    cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert buttons.get(made["id"])["lane"] == "Jazz", "kept by name, so a Re-analyse keeps it"
    cb.set("Last Played")
    cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert buttons.get(made["id"])["lane"] == ""
    assert not ui.errors, ui.errors[0]


def test_filters_tick_onto_radio(app, ui):
    import buttons
    import filters
    f = filters.blank("Stereo")
    filters.save([f])
    made = made_radio()
    pick_button(ui, "Radio")
    s = ui.settings
    ticks = s._button_filter_vars[0]
    assert list(ticks) == [f["id"]]
    ticks[f["id"]].set(True)
    s._config_filters_changed(0)
    assert buttons.get(made["id"])["filters"] == [f["id"]]
    assert not ui.errors, ui.errors[0]


def test_simple_keeps_lane_sources_selection_and_filters(app, ui):
    import mode
    mode.set_current("simple")
    made_radio()
    pick_button(ui, "Radio")
    texts = texts_of(ui.settings)
    for here in ("Lane", "Sources", "Playlist Selection", "Filters"):
        assert here in texts, here
    for gone in ("Moderator", "Deep Cuts", "Shortcut") + NOT_RADIO:
        assert gone not in texts, gone
    mode.set_current("advanced")
    assert not ui.errors, ui.errors[0]
