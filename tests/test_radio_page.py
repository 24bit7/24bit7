"""
Radio's page under Settings > Playlist Settings (Ben, 6 Nov 2026; two boxes, 7 Nov 2026). This Button: Station,
and Shortcut in Advanced. All Radio Buttons, shared by every Radio: Stations (the count, Re-analyse, a row per
station to rename or split), Sources, Playlist Selection, Filters, and in Advanced the Moderator and Deep Cuts.
No Consensus, Drift, Mix, Non-stop, Hidden Tracks, If All Else Fails or Run After Building, and no Add Another
Config. What it sets is what Radio builds with.
"""

import pytest
from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, shown, shown_labels
from test_radio import EVERYONE, play_counts

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
    for here in ("This Button", "Station", "All Radio Buttons", "Stations", "Show", "Sources", "Must agree",
                 "Playlist Selection", "Each Round", "Filters", "Moderator", "Deep Cuts"):
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


def test_station_picks_a_station_or_last_played(app, ui, monkeypatch):
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


def test_simple_keeps_station_stations_sources_selection_and_filters(app, ui):
    import mode
    mode.set_current("simple")
    made_radio()
    pick_button(ui, "Radio")
    texts = texts_of(ui.settings)
    for here in ("Station", "Stations", "Sources", "Playlist Selection", "Filters"):
        assert here in texts, here
    for gone in ("Moderator", "Deep Cuts", "Shortcut") + NOT_RADIO:
        assert gone not in texts, gone
    mode.set_current("advanced")
    assert not ui.errors, ui.errors[0]


@pytest.fixture
def lowered(app, monkeypatch):
    import radio
    for name, value in (("MIN_PLAYS", 1), ("MIN_ARTISTS", 4), ("LANE_MIN", 2), ("PILLAR_OWNED", 2),
                        ("PILLARS_TO_SPLIT", 2), ("LANES_MAX", 3)):
        monkeypatch.setattr(radio, name, value)
    monkeypatch.setattr(radio.time, "sleep", lambda s: None)
    return radio


def test_a_change_on_one_radios_page_changes_every_radio(app, ui):
    import buttons
    import mode
    mode.set_current("advanced")
    first = made_radio()
    second = made_radio()
    p = pick_button(ui, "Radio 2")
    p.vars["AI_MODERATOR_ARTISTS"].set("Strict")
    p.save()
    assert buttons.get(first["id"])["settings"]["AI_MODERATOR_ARTISTS"] == "strict", "shared by every Radio"
    assert buttons.get(second["id"])["settings"]["AI_MODERATOR_ARTISTS"] == "strict"
    assert not ui.errors, ui.errors[0]


def test_stations_rename_split_and_count(app, ui, lowered):
    radio = lowered
    play_counts(app, EVERYONE)
    radio.set_row(count=3)
    radio.analyse(app.Lines())
    made_radio()
    pick_button(ui, "Radio")
    s = ui.settings
    assert s._radio_count_box.get() == str(len(radio.lanes()))
    assert s._radio_again.cget("text") == "Re-analyse"
    rows = dict(s._radio_station_rows)
    first = radio.lanes()[0]
    entry = rows[first["id"]]
    entry.delete(0, "end")
    entry.insert(0, "Guitars")
    entry.focus_force()
    ui.pump(0.1)
    entry.event_generate("<Return>")
    ui.pump(0.2)
    assert radio.lane(first["id"])["name"] == "Guitars"
    assert "Guitars" in list(s._radio_lane_box.cget("values")), "the Station list follows"
    splittable = next((x for x in radio.lanes() if x.get("children")), None)
    if splittable is not None:
        s._radio_refresh()
        ids_before = [i for i, _ in s._radio_station_rows]
        arrow = s._radio_station_rows[ids_before.index(splittable["id"])][1].master.master.grid_slaves(
            row=ids_before.index(splittable["id"]), column=0)[0]
        arrow.event_generate("<Button-1>")
        ui.pump(0.2)
        assert splittable["id"] in radio.row()["open"], "the arrow is Split"
        ids = [i for i, _ in s._radio_station_rows]
        assert splittable["children"][0]["id"] in ids
    s._radio_count_box.delete(0, "end")
    s._radio_count_box.insert(0, "2")
    s._radio_count_box.focus_force()
    ui.pump(0.1)
    s._radio_count_box.event_generate("<Return>")
    ui.wait_idle()
    ui.pump(0.3)
    assert radio.row()["count"] == 2
    assert len(radio.lanes()) == 2, "the Play tab cut the stations again"
    assert s._radio_count_box.get() == "2" and len([1 for _i, _e in s._radio_station_rows]) >= 2
    assert not ui.errors, ui.errors[0]
