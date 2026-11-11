"""
Discover's Missing Artists and Gaps in Your Artists (Ben, 10 and 11 Nov 2026), filtered by
Period, Zone, Genre (Radio's stations) and Sound (an artist's own Last.fm tags). Also the zone and asker each
session now keeps, and the back-fill from the console's Log for sessions from before. Nothing here opens a window.

The fake library has The Beatles, The Kinks, Pink Floyd, Jimi Hendrix and the rest; Nonpoint, Crossfade and
Trivium aren't in it.
"""

import os
import sqlite3
from datetime import datetime


def session(app, mode="similar", artist="The Beatles", track="", started="2026-11-10 20:00", zone="Sonos",
            asked_by="Main Window", seen=()):
    """A session and its discoveries, written straight to the history: seen is [(artist, track, sources, found, seed)]."""
    con = app.engine.db()
    sid = con.execute("INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued, "
                      "zone, asked_by) VALUES (?,?,?,?,?,?,?,?,?)",
                      (started, mode, artist, track, "", "", 0, zone, asked_by)).lastrowid
    for row in seen:
        a, t_, s, f = row[:4]
        seed = row[4] if len(row) > 4 else None
        con.execute("INSERT INTO discoveries (session_id, artist, track, sources, found, seed) VALUES (?,?,?,?,?,?)",
                    (sid, a, t_, s, int(f), seed))
    con.commit()
    return sid


def history(app):
    """Three builds: Nonpoint from The Beatles and The Kinks (folded twice: THE KINKS), Trivium from one."""
    session(app, artist="The Beatles", started="2026-11-01 20:00", seen=[
        ("Nonpoint", "Bullet With a Name", "Last.fm", 0), ("Nonpoint", "Alive and Kicking", "Last.fm, Deezer", 0),
        ("Pink Floyd", "Echoes", "Last.fm", 1), ("Pink Floyd", "Money", "Deezer", 0),
        ("Trivium", "In Waves", "AI", 0)])
    session(app, artist="The Kinks", started="2026-11-05 21:00", zone="Speakers", asked_by="Echo Dot", seen=[
        ("Nonpoint", "Bullet With a Name", "Last.fm", 0), ("Pink Floyd", "Echoes", "Deezer, seed", 1)])
    session(app, artist="THE KINKS", started="2026-03-01 10:00", seen=[
        ("Nonpoint", "Victim", "Last.fm", 0), ("Jimi Hendrix", "Crosstown Traffic", "Last.fm", 1)])


def test_missing_artists_are_checked_against_the_library_and_ranked_by_your_artists(app):
    import discover_stats as ds
    history(app)
    got = ds.missing_artists(ds.rows())
    names = [m["artist"] for m in got]
    assert names == ["Nonpoint", "Trivium"], "Pink Floyd's missing song is a gap, not a missing artist"
    nonpoint = got[0]
    assert sorted(nonpoint["yours"].values(), key=str.lower) == ["The Beatles", "The Kinks"], \
        "The Kinks and THE KINKS are one of your artists"
    assert len(nonpoint["builds"]) == 3
    assert nonpoint["songs"]["Bullet With a Name"] == 2


def test_a_typed_seed_you_dont_own_isnt_one_of_your_artists(app):
    import discover_stats as ds
    session(app, artist="Crossfade", seen=[("Nonpoint", "Victim", "Last.fm", 0)])
    assert ds.missing_artists(ds.rows())[0]["yours"] == {}


def test_a_playing_now_row_counts_the_artist_it_was_sampled_from(app):
    import discover_stats as ds
    session(app, artist="", mode="similar", seen=[("Nonpoint", "Victim", "Last.fm", 0, "Pink Floyd - Echoes")])
    session(app, artist="AI Playlist", mode="vibe", seen=[("Trivium", "In Waves", "AI", 0)])
    got = {m["artist"]: m for m in ds.missing_artists(ds.rows())}
    assert list(got["Nonpoint"]["yours"].values()) == ["Pink Floyd"]
    assert got["Trivium"]["yours"] == {}, "an AI Playlist's seed isn't an artist"


def test_gaps_list_the_songs_you_dont_have_by_artists_you_own(app):
    import discover_stats as ds
    history(app)
    got = {g["artist"]: g for g in ds.gaps(ds.rows())}
    assert set(got) == {"Pink Floyd", "Jimi Hendrix"}
    assert got["Pink Floyd"]["matched"] == 1 and got["Pink Floyd"]["missed"] == ["Money"]
    assert ds.gaps(ds.rows())[0]["artist"] == "Pink Floyd", "most songs missed first"


def test_the_sources_view_is_gone(app):
    """Ben, 11 Nov 2026: the Sources scoreboard led nowhere, so Discover has two artist tabs and no third view."""
    import discover_stats as ds
    assert ds.VIEWS == ("Missing Artists", "Gaps in Your Artists")
    assert not hasattr(ds, "sources")


def test_period_and_zone_narrow_the_builds_in_view(app):
    import discover_stats as ds
    history(app)
    now = datetime(2026, 11, 10, 22, 0)
    assert len({r["session"] for r in ds.rows("Last 6 months", now=now)}) == 2
    assert len({r["session"] for r in ds.rows("Last 12 months", now=now)}) == 3
    speakers = ds.build("Missing Artists", zone="Speakers", now=now)
    assert speakers["builds"] == 1 and [m["artist"] for m in speakers["items"]] == ["Nonpoint"]
    zones = dict(ds.zones())
    assert zones["Sonos"]["Main Window"] == 2 and zones["Speakers"]["Echo Dot"] == 1


def test_a_session_gets_the_zone_and_asker_of_the_build_kept_in_the_log(app):
    import buildlog
    e = app.engine
    e.JOB_SESSIONS.clear()
    older = session(app, zone="Kitchen", asked_by="Main Window")
    e.JOB_SESSIONS.append(older)   # already known: never overwritten
    first = e.session_start("similar", {"Artist": "The Beatles", "Name": ""})
    second = e.session_start("top_tracks", {"Artist": "The Kinks", "Name": ""})
    e.LAST_OUTPUT, e.LAST_OUTPUT_ID = "Sonos", "10001"
    buildlog.record_job({"from": "shortcut"}, "Done: 30 tracks.")
    got = dict(((sid, (z, a)) for sid, z, a in e.db().execute("SELECT id, zone, asked_by FROM sessions")))
    assert got[first] == got[second] == ("Sonos", "Shortcut")
    assert got[older] == ("Kitchen", "Main Window")
    assert e.JOB_SESSIONS == []


def test_sessions_from_before_learn_their_zone_from_the_log(app):
    """An old database: sessions without a zone, and the Log's builds. Each session takes the first build
    kept within twenty minutes of its start; one with none gets "", so the next build doesn't claim it."""
    e = app.engine
    if e._db is not None:
        e._db.close()
        e._db = None
    path = e.DB_FILE
    for p in (path, path + "-journal", path + "-wal"):
        if os.path.exists(p):
            os.remove(p)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, mode TEXT, "
                "seed_artist TEXT, seed_track TEXT, seed_album TEXT, sources TEXT, queued INTEGER)")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('csv_imported', '1')")
    con.execute("CREATE TABLE builds (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, tab TEXT, from_label TEXT, "
                "zone TEXT, zone_id TEXT, kind TEXT, sources TEXT, queued INTEGER, misses INTEGER, moderator TEXT, "
                "problems INTEGER, notes INTEGER, chain_id INTEGER, chain_pos INTEGER, text TEXT)")
    for started in ("2026-11-01 20:00", "2026-11-01 20:00", "2026-11-02 09:00", "2026-11-03 18:30"):
        con.execute("INSERT INTO sessions (started_at, mode) VALUES (?, 'similar')", (started,))
    for at, zone, who in (("2026-11-01 20:03:10", "Sonos", "Echo Dot"), ("2026-11-02 08:59:59", "Speakers", "Main Window"),
                          ("2026-11-02 09:25:00", "Speakers", "Main Window"), ("2026-11-03 18:31:00", "", "Main Window")):
        con.execute("INSERT INTO builds (at, zone, from_label) VALUES (?,?,?)", (at, zone, who))
    con.commit()
    con.close()
    got = e.db().execute("SELECT zone, asked_by FROM sessions ORDER BY id").fetchall()
    assert got == [("Sonos", "Echo Dot"), ("Sonos", "Echo Dot"), ("", ""), ("", "Main Window")], got


def test_sound_merges_spellings_and_keeps_decades(app):
    import discover_stats as ds
    assert ds.sound_key("synthpop") == ds.sound_key("synth pop") == ds.sound_key("Synth-Pop")
    assert ds.sound_key("hip-hop") == ds.sound_key("hip hop") == ds.sound_key("Hip Hop")
    assert ds.sound_key("rock and roll") == ds.sound_key("rock & roll") == ds.sound_key("rock n roll") \
        == ds.sound_key("rock 'n' roll")
    assert ds.sound_key("80s") == ds.sound_key("1980s") == ds.sound_key("80's") == "80s"
    cache = {"nonpoint": [["nu metal", 100], ["seen live", 60], ["80s", 40], ["american", 30], ["metal", 5]]}
    assert ds.sounds_of("Nonpoint", cache) == [("numetal", "nu metal"), ("80s", "80s")], \
        "seen live and american go, as in Radio; a decade stays; a weak tag goes"


def test_the_sound_list_shows_shared_sounds_and_greys_the_broad_ones(app):
    import discover_stats as ds
    cache = {"a": [["nu metal", 90], ["metal", 80]], "b": [["nu-metal", 90], ["metal", 80]],
             "c": [["Nu Metal", 90], ["metal", 80], ["metalcore", 50]], "d": [["metalcore", 70]], "e": []}
    listed, untagged = ds.sound_list(["A", "B", "C", "D", "E"], cache, {"genres": ["metal", "heavy metal"]})
    assert [(k, n, broad) for k, _shown, n, broad in listed] == [("numetal", 3, False), ("metal", 3, True)], \
        "metalcore is on two artists only"
    assert listed[0][1] in ("nu metal", "nu-metal", "Nu Metal".lower())
    assert untagged == 1


def stations_meta(app):
    """Two stations, as Radio's analysis keeps them, and the tags of the artists in the history."""
    import radio
    radio._set_meta(radio.ANALYSIS_KEY, {"when": "2026-11-10", "resting": None, "lanes": [
        {"id": "1", "name": "Rock / Classic Rock", "genres": ["rock", "classic rock"], "artists": 3, "plays": 10,
         "pillars": [], "children": [], "centroid": {"rock": 0.8, "classic rock": 0.6}},
        {"id": "2", "name": "Psychedelic / Prog", "genres": ["psychedelic", "progressive rock"], "artists": 2,
         "plays": 5, "pillars": [], "children": [], "centroid": {"psychedelic": 0.7, "progressive rock": 0.7}}]})
    radio._set_meta(radio.TAGS_KEY, {
        "the beatles": [["rock", 100], ["classic rock", 90]], "the kinks": [["classic rock", 100], ["rock", 80]],
        "pink floyd": [["progressive rock", 100], ["psychedelic", 80]],
        "jimi hendrix": [["psychedelic", 100], ["rock", 40]],
        "nonpoint": [["nu metal", 100]], "trivium": [["metalcore", 100]]})


def test_genre_files_a_missing_artist_by_the_stations_of_your_artists_that_point_to_it(app):
    import discover_stats as ds
    history(app)
    session(app, artist="Pink Floyd", seen=[("Trivium", "Shogun", "Last.fm", 0)])
    stations_meta(app)
    rock = ds.build("Missing Artists", station_id="1")
    assert [(m["artist"], len(m["yours"])) for m in rock["items"]] == [("Nonpoint", 2), ("Trivium", 1)]
    prog = ds.build("Missing Artists", station_id="2")
    assert [(m["artist"], list(m["yours"].values())) for m in prog["items"]] == [("Trivium", ["Pink Floyd"])], \
        "Your Artists is counted again inside the station"
    gaps = ds.build("Gaps in Your Artists", station_id="2")
    assert {g["artist"] for g in gaps["items"]} == {"Pink Floyd", "Jimi Hendrix"}, "an owned artist sits in its own station"
    every = ds.build("Missing Artists")
    assert every["station"] is None and len(every["items"]) == 2


def test_genre_is_greyed_with_a_reason_while_radio_rests(app):
    import discover_stats as ds
    import radio
    radio._set_meta(radio.ANALYSIS_KEY, {"when": "2026-11-10", "resting": {"have": 50, "need": 500}, "lanes": []})
    found, why = ds.stations()
    assert found == [] and "resting" in why
    radio._set_meta(radio.ANALYSIS_KEY, None)
    assert ds.stations()[0] == [] and ds.stations()[1]


def test_the_sound_filter_keeps_the_artists_with_that_sound(app):
    import discover_stats as ds
    history(app)
    stations_meta(app)
    got = ds.build("Missing Artists", sound="numetal")
    assert [m["artist"] for m in got["items"]] == ["Nonpoint"]


def test_tags_are_fetched_once_into_radios_cache(app):
    import discover_stats as ds
    import radio
    radio._set_meta(radio.TAGS_KEY, {"the beatles": [["rock", 100]]})
    asked = lambda: [c for c in app.web.calls if c[0] == "lastfm" and c[2].get("method") == "artist.gettoptags"]
    before = len(asked())
    assert ds.fetch_tags(["The Beatles", "The Kinks", "the kinks", "Pink Floyd"]) == 2
    assert len(asked()) - before == 2, "The Beatles was cached, The Kinks asked once"
    kept = radio._meta(radio.TAGS_KEY, {})
    assert "the kinks" in kept and "pink floyd" in kept and kept["the beatles"] == [["rock", 100]]
    assert ds.fetch_tags(["The Kinks"]) == 0 and len(asked()) - before == 2


def test_no_lastfm_key_asks_nothing(app, monkeypatch):
    import discover_stats as ds
    monkeypatch.setattr(app.engine, "LASTFM_KEY", "")
    before = len(app.web.calls)
    assert ds.fetch_tags(["The Kinks"]) == 0 and len(app.web.calls) == before


def test_a_number_column_is_as_wide_as_its_title_or_its_widest_number(app):
    """Ben, 11 Nov 2026: on a screen scaled up, "Your Artists" read "Your /" in a column of fixed width."""
    import artists_gui
    head = lambda text: 20 * len(text)    # a bold font on a screen scaled to double
    cell = lambda text: 10 * len(text)
    assert artists_gui.number_width("Your Artists", [7, 10], head, cell) == 240 + artists_gui.PAD
    assert artists_gui.number_width("Gefunden", [1234567890123456789], head, cell) == 190 + artists_gui.PAD


def test_the_stripe_is_a_shade_off_the_page_either_way(app):
    """Ben, 11 Nov 2026: every other row a little lighter on a dark theme, a little darker on a light one."""
    import tabs
    def brightness(c):
        r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
        return r + g + b
    dark, light = "#1b1b1b", "#f3f4f6"
    assert 0 < brightness(tabs.stripe_colour(dark)) - brightness(dark) < 90
    assert 0 < brightness(light) - brightness(tabs.stripe_colour(light)) < 90
