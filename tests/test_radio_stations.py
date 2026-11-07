"""
Radio's stations and shared settings (Ben, 7 Nov 2026). Radio's settings and filters are one set for every
Radio button: a change on any Radio's page changes them all, a new Radio joins them, and a list from before
gets them once (the first Radio's). The Stations section sets how many stations there are (a new count cuts
the stations again from the genres kept, asking Last.fm nothing), and a station can be renamed: the name
sticks across a Re-analyse, and a Radio button playing it follows the new name.
"""

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


def two_radios():
    import buttons
    a, _ = buttons.add_from_choice(("template", "radio"))
    b, _ = buttons.add_from_choice(("template", "radio"))
    return buttons, a, b


def test_a_change_on_one_radio_changes_them_all(app):
    buttons, a, b = two_radios()
    assert b["name"] == "Radio 2"
    buttons.set_settings(a["id"], dict(a["settings"], TRACKS_PER_ARTIST_PICK="4", AI_MODERATOR_ARTISTS="strict"))
    assert buttons.get(b["id"])["settings"]["TRACKS_PER_ARTIST_PICK"] == "4"
    assert buttons.get(b["id"])["settings"]["AI_MODERATOR_ARTISTS"] == "strict"
    buttons.set_filters(b["id"], ["f1"])
    assert buttons.get(a["id"])["filters"] == ["f1"], "filters are shared too"
    std = buttons.standard("artists")
    assert buttons.get(std["id"])["filters"] != ["f1"], "only Radio playlists share"


def test_a_new_radio_joins_the_shared_settings(app):
    buttons, a, _b = two_radios()
    buttons.set_settings(a["id"], dict(a["settings"], DEEP_CUTS_ARTISTS="spaced"))
    buttons.set_filters(a["id"], ["f2"])
    c, _ = buttons.add_from_choice(("template", "radio"))
    assert c["settings"]["DEEP_CUTS_ARTISTS"] == "spaced" and c["filters"] == ["f2"], \
        "from the template too: the Radio there is, not the standard Similar Artists"
    d = buttons.duplicate(a["id"])
    assert d["settings"] == buttons.get(a["id"])["settings"]


def test_radios_that_differ_are_made_one_set_once(app):
    import buttons
    import engine
    _buttons, a, b = two_radios()
    items = buttons.load()
    for x in items:   # as a 1.31.0 list from before 7 Nov might be: each Radio its own
        if x["id"] == b["id"]:
            x["settings"] = dict(x["settings"], TRACKS_PER_ARTIST_PICK="9")
    buttons.save(items)
    con = engine.db()
    con.execute("DELETE FROM meta WHERE key=?", (buttons.RADIO_SHARED_KEY,))
    con.commit()
    printed = []
    old = engine.print
    engine.print = lambda *x, **k: printed.append(" ".join(str(s) for s in x))
    try:
        buttons.load()
    finally:
        engine.print = old
    assert buttons.get(b["id"])["settings"] == buttons.get(a["id"])["settings"], "the first Radio's, for all"
    assert any("Radio's settings are shared by every Radio button now. They all have Radio's." in p for p in printed), printed
    printed.clear()
    engine.print = lambda *x, **k: printed.append(" ".join(str(s) for s in x))
    try:
        buttons.load()
    finally:
        engine.print = old
    assert not printed, "said once"


def test_the_count_asked_for_sets_how_many_stations(app, radio):
    play_counts(app, EVERYONE)
    radio.set_row(count=2)
    radio.analyse(app.Lines())
    assert len(radio.lanes()) == 2
    radio.set_row(count=40)
    r = app.Lines()
    radio.analyse(r, fresh=False)
    made = len(radio.lanes())
    assert 2 < made < 40, made
    assert r.has(f"You asked for 40 stations; {made} is as many as stand alone"), r.text()


def test_a_new_count_asks_last_fm_nothing_new(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    canon = sum(1 for c in app.web.calls if c[2].get("method") == "tag.gettopartists")
    assert canon
    radio.set_row(count=2)
    radio.analyse(app.Lines(), fresh=False)
    radio.set_row(count=None)
    radio.analyse(app.Lines(), fresh=False)
    assert sum(1 for c in app.web.calls if c[2].get("method") == "tag.gettopartists") == canon, \
        "the genres' top artists kept from last time"
    radio.analyse(app.Lines())
    assert sum(1 for c in app.web.calls if c[2].get("method") == "tag.gettopartists") > canon, \
        "Re-analyse asks again"


def test_a_renamed_station_keeps_its_name_and_its_buttons(app, radio):
    import buttons
    play_counts(app, EVERYONE)
    radio.set_row(count=3)
    radio.analyse(app.Lines())
    assert len(radio.lanes()) >= 2
    first = radio.lanes()[0]
    genre_name = first["name"]
    b, _ = buttons.add_from_choice(("template", "radio"))
    buttons.set_lane(b["id"], genre_name)
    assert radio.rename(first["id"], "Guitars") is None
    assert radio.lane(first["id"])["name"] == "Guitars" and radio.lane(first["id"])["auto"] == genre_name
    assert buttons.get(b["id"])["lane"] == "Guitars", "a Radio playing it follows the new name"
    assert radio.lane_named("Guitars")["id"] == first["id"]
    radio.analyse(app.Lines())
    assert radio.lanes()[0]["name"] == "Guitars", "kept across a Re-analyse"
    assert radio.moderator_seed(radio.lanes()[0], ["X"]).startswith(f"vibe: {genre_name} radio"), \
        "the Moderator judges by the genres, not your name for it"
    other = radio.lanes()[1]
    assert radio.rename(other["id"], "guitars") == "Another station is called guitars."
    assert radio.rename(first["id"], "") is None
    assert radio.lanes()[0]["name"] == genre_name, "blank goes back to the genre name"
    assert buttons.get(b["id"])["lane"] == genre_name
    radio.analyse(app.Lines())
    assert radio.lanes()[0]["name"] == genre_name


def test_a_name_for_a_station_thats_gone_is_kept_and_said(app, radio):
    play_counts(app, EVERYONE)
    radio.set_row(count=3)
    radio.analyse(app.Lines())
    last = radio.lanes()[-1]
    radio.rename(last["id"], "Odds and Sods")
    saved = radio.names()
    saved["Polka / Oompah"] = "Brass"   # a station from an earlier cut, not in this one
    radio._set_meta(radio.NAMES_KEY, saved)
    r = app.Lines()
    radio.analyse(r, fresh=False)
    assert r.has("Your name Brass is kept for Polka / Oompah, which isn't a station this time."), r.text()
    assert "Polka / Oompah" in radio.names(), "kept, for when it comes back"
    assert any(x["name"] == "Odds and Sods" for x in radio.lanes(include_children=True)), "a station still there keeps its name"
