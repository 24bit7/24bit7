"""
Radio and Play & Embellish show their working and log it (Ben, 10 Nov 2026). Both matched the sources' top
tracks against the library in silence: the console said little between the first line and the last, and their
sessions in Discover were empty, since nothing looked up was ever logged. Now each pillar and agreeing artist is
a line, each of its top tracks is said, In library or Not in library, and every one is logged to the session,
hit or miss, with Radio or Embellish as its source. Nothing here opens a window.
"""

from test_radio import EVERYONE, play_counts
from test_radio_playlist import made_radio, radio  # noqa: F401  (the radio fixture)

ROAD_TRIP = {"ID": "202", "Name": "Road Trip"}
MISSING = "A Song Not In The Library"   # the fake sources name it for every artist, and nobody owns it


def logged(app, mode):
    """[(artist, track, sources, found)] for the latest session of a kind."""
    con = app.engine.db()
    sid = con.execute("SELECT id FROM sessions WHERE mode=? ORDER BY id DESC LIMIT 1", (mode,)).fetchone()[0]
    return con.execute("SELECT artist, track, sources, found FROM discoveries WHERE session_id=?", (sid,)).fetchall()


def test_embellish_says_each_agreeing_artist_and_its_tracks(app):
    import embellish
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, None, "p50", r)
    assert r.has("  Consensus: ") and r.has("(circle of 4, agree on 2)"), r.text()
    assert r.has(" artists on 2 or more of their lists; ") and r.has(" already on Road Trip."), r.text()
    assert "  The Kinks..." in r, r.text()
    assert "    In library: Waterloo Sunset" in r, r.text()
    assert f"    Not in library: {MISSING}" in r, r.text()


def test_embellish_logs_every_track_it_looks_up_for_discover(app):
    import embellish
    embellish.embellish(ROAD_TRIP, None, "p50", app.Lines())
    got = logged(app, "embellish")
    assert got, "the session was empty"
    assert {s for _a, _t, s, _f in got} == {"Embellish"}
    assert ("The Kinks", "Waterloo Sunset", "Embellish", 1) in got
    assert ("The Kinks", MISSING, "Embellish", 0) in got, "a miss is what Discover is for"
    on_list = {"The Hollies", "Queen", "The Byrds", "Badfinger"}
    assert not {a for a, _t, _s, _f in got} & on_list, "artists already on the playlist aren't looked up"


def test_radio_says_each_pillar_and_agreeing_artist_and_its_tracks(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    pillars = next(x for x in r if "Pillars this round:" in x)
    said = [x for x in r if x.startswith("  Pillar: ")]
    assert said and all(x[len("  Pillar: "):-3] in pillars for x in said), (said, pillars)
    assert any(x.startswith("    In library: ") for x in r), r.text()
    assert any(x.startswith("  ") and x.endswith("...") and "Pillar" not in x for x in r), "the agreeing artists too"


def test_radio_logs_every_track_it_looks_up_for_discover(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    got = logged(app, "radio")
    assert got, "the session was empty"
    assert {s for _a, _t, s, _f in got} == {"Radio"}
    assert any(f == 1 for _a, _t, _s, f in got) and any(f == 0 for _a, _t, _s, f in got), got
    sent = app.jriver.zone("Speakers").playlist
    hits = {(a, tr) for a, tr, _s, f in got if f == 1}
    by_key = app.jriver.by_key
    assert any((by_key[k]["Artist"], by_key[k]["Name"]) in hits for k in sent), "what played was among what was logged"
