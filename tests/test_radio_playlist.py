"""
Radio as a playlist (Ben, 6 Nov 2026): optional, so it drags, deletes, comes from a template and back with
Restore Default Playlists like the others. Its page has Lane, Sources, Playlist Selection, Filters, Moderator,
Deep Cuts and Shortcut; its settings are Artist Matching's keys, started from the standard Similar Artists
playlist so day one sounds the same. No configs, no Mix, no children, no voice phrase. A list from before
1.31.0 gets it once at the end of the row, with each lane button made a Radio playlist of that lane.
"""

import json

import pytest

from test_radio import EVERYONE, play_counts


@pytest.fixture
def radio(app, monkeypatch):
    import radio
    for name, value in (("MIN_PLAYS", 1), ("MIN_ARTISTS", 4), ("LANE_MIN", 2), ("PILLAR_OWNED", 2),
                        ("PILLARS_TO_SPLIT", 2), ("LANES_MAX", 3)):
        monkeypatch.setattr(radio, name, value)
    monkeypatch.setattr(radio.time, "sleep", lambda s: None)
    return radio


def made_radio(app):
    import buttons
    b, _page = buttons.add_from_choice(("template", "radio"))
    return buttons, b


def test_the_template_makes_radio_from_the_standard_similar_artists(app):
    import buttons
    std = buttons.standard("artists")
    buttons.set_settings(std["id"], dict(std["settings"], TRACKS_PER_ARTIST_PICK="4", SIMILAR_SOURCES="deezer",
                                         AI_MODERATOR_ARTISTS="strict"))
    buttons.set_filters(std["id"], ["f1"])
    _, b = made_radio(app)
    assert b["kind"] == "radio" and b["name"] == "Radio" and b["made"] == "radio"
    assert b["settings"]["TRACKS_PER_ARTIST_PICK"] == "4" and b["settings"]["SIMILAR_SOURCES"] == "deezer"
    assert b["settings"]["AI_MODERATOR_ARTISTS"] == "off" and b["settings"]["DEEP_CUTS_ARTISTS"] == "off", \
        "Moderator and Deep Cuts start off"
    assert set(b["settings"]) <= set(buttons.RADIO_KEYS), "only Radio's keys"
    assert b["filters"] == ["f1"] and b["lane"] == ""
    assert buttons.configs(b) == [] and not buttons.follows_seed(b) and not buttons.needs_track(b)


def test_radio_keeps_only_its_keys_and_takes_no_configs_or_children(app):
    buttons, b = made_radio(app)
    buttons.set_settings(b["id"], {"TRACKS_PER_ARTIST_PICK": "2", "DRIFT_ARTISTS": "1", "TOP_TRACKS_COUNT": "9"})
    assert buttons.get(b["id"])["settings"] == {"TRACKS_PER_ARTIST_PICK": "2"}
    buttons.add_config(b["id"], "tracks")
    assert buttons.get(b["id"])["configs"] == [] and buttons.get(b["id"])["kind"] == "radio"
    other = buttons.standard("vibe")
    assert not buttons.nest(other["id"], b["id"]), "its arrow lists lanes, so no children"
    parent = buttons.standard("artists")
    assert buttons.nest(b["id"], parent["id"]), "it can go under another playlist"
    assert buttons.get(b["id"])["parent"] == parent["id"]


def test_delete_and_restore(app):
    buttons, b = made_radio(app)
    buttons.remove(b["id"])
    assert "Radio" in buttons.missing_shipped()
    back = buttons.restore_standard()
    assert any(x["kind"] == "radio" for x in back)
    assert buttons.load()[-1]["kind"] == "radio", "after the rest"


def test_a_list_from_before_gets_radio_once_with_its_lane_buttons(app, radio):
    import buttons
    import engine
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    lane = radio.lanes()[0]
    radio.set_row(buttons=[lane["id"]])
    items = buttons.load()
    assert not any(buttons.is_radio(b) for b in items), "the fake world starts without it (conftest)"
    con = engine.db()
    con.execute("DELETE FROM meta WHERE key = ?", (buttons.RADIO_ADOPTED_KEY,))
    con.commit()
    printed = []
    engine.print = lambda *a, **k: printed.append(" ".join(str(x) for x in a))
    items = buttons.load()
    made = [b for b in items if buttons.is_radio(b)]
    assert [b["name"] for b in made] == ["Radio", lane["name"]]
    assert made[1]["lane"] == lane["name"], "the lane by name, so a Re-analyse keeps it"
    assert [b["name"] for b in buttons.shown()][-2:] == ["Radio", lane["name"]], "at the end of the row"
    assert radio.row()["buttons"] == []
    assert any("Radio is a playlist now" in x for x in printed), printed
    buttons.remove(made[0]["id"])
    assert sum(1 for b in buttons.load() if b["made"] == "radio") == 0, "once: a deleted Radio stays deleted"


def test_a_device_phrase_cant_copy_radio(app):
    buttons, b = made_radio(app)
    assert b["id"] in [x["id"] for x in buttons.buttons_only()]
    assert b["id"] not in [x["id"] for x in buttons.for_voice()]


def test_simple_and_advanced_count_radios_moderator(app):
    import mode
    buttons, b = made_radio(app)
    assert mode.uses_advanced(buttons.get(b["id"])) == []
    buttons.set_settings(b["id"], {"AI_MODERATOR_ARTISTS": "balanced"})
    assert mode.uses_advanced(buttons.get(b["id"])) == ["Moderator"]
    assert not mode.needs_advanced(buttons.get(b["id"]))


def test_a_build_reads_its_own_settings_and_lane(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    lane = radio.lanes()[1] if len(radio.lanes()) > 1 else radio.lanes()[0]
    buttons.set_lane(b["id"], lane["name"])
    buttons.set_settings(b["id"], dict(buttons.get(b["id"])["settings"], TRACKS_PER_ARTIST_PICK="1"))
    seen = {}
    real = radio._owned_top

    def spy(artist, have, played, limit, pool=None):
        if pool:
            seen["pick"] = limit
        return real(artist, have, played, limit, pool)
    radio._owned_top = spy
    try:
        r = app.Lines()
        buttons.run(buttons.get(b["id"]), report=r)
    finally:
        radio._owned_top = real
    assert r.has(f"Radio: {lane['name']}."), r.text()
    assert seen.get("pick") == 1, "Pick from Radio's own page"
    entry = app.engine.NONSTOP_ZONES[app.jriver.zone("Speakers").id]
    assert entry["button"] == b["id"], "Non-stop carries on with this playlist's settings"
    assert radio.row()["default"] != lane["id"] or radio.lanes()[0]["id"] == lane["id"], \
        "a playlist set to a lane doesn't move the last-played lane"


def test_a_lane_thats_gone_says_so(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    buttons.set_lane(b["id"], "Polka / Oompah")
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    assert r.has("Radio plays the station Polka / Oompah, which isn't there since the stations were made again"), r.text()
    assert not app.jriver.zone("Speakers").playlist


def test_the_moderator_checks_the_guests_against_the_pillars(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    buttons.set_settings(b["id"], dict(buttons.get(b["id"])["settings"], AI_MODERATOR_ARTISTS="balanced"))
    app.ai.remove = [1]
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    assert r.has("Moderator (Balanced): checking"), r.text()
    assert r.has("against the seed and the playlist so far"), "the pillars' songs as what fits"
    sent = app.ai.sent[-1]
    assert "Seed vibe:" in sent and " radio, in the sound of " in sent, sent
    assert r.has("Removed "), r.text()


def test_the_more_options_switch_overrides_radios_moderator(app, radio):
    import overrides
    import playmix
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    playmix.set_open(True)
    assert overrides.active()
    overrides.set_switch("moderator", "strict")
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    assert r.has("More Options: Moderator Strict"), r.text()
    assert r.has("Moderator (Strict): checking"), r.text()
