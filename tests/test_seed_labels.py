"""
Discover's Seed column for builds with no seed artist (Ben, 23 Nov 2026): Radio read "? - Classic Rock / Rock".
Now it's "Radio: Classic Rock / Rock", and a JRiver playlist (Play, Play & Embellish, Blend) is "Playlist: Happy
Go Lucky". An album keeps "Artist - Album". Nothing here opens a window.
"""


def test_the_seed_says_what_it_was_built_from(app):
    from discover_gui import seed_label
    assert seed_label("radio", "", "Classic Rock / Rock") == "Radio: Classic Rock / Rock"
    for mode in ("embellish", "jriver_playlist", "blend"):
        assert seed_label(mode, "", "Happy Go Lucky") == "Playlist: Happy Go Lucky", mode
    assert seed_label("embellish", "Queen", "A Night At The Opera") == "Queen - A Night At The Opera", "an album"
    assert seed_label("similar", "Queen", "") == "Queen"
    assert seed_label("similar_tracks", "Queen", "Under Pressure") == "Queen - Under Pressure"
    assert seed_label("similar", "", "") == "?"


def test_discover_rows_and_the_session_list_carry_the_kind(app):
    e = app.engine
    sid = e.session_start("radio", {"Artist": "", "Name": "Classic Rock / Rock"})
    e.session_log(sid, "Queen", "Under Pressure", ["Last.fm"], found=False)
    row = next(r for r in e.list_discoveries() if r["session_id"] == sid)
    from discover_gui import seed_label
    assert seed_label(row["mode"], row["seed_artist"], row["seed_track"]) == "Radio: Classic Rock / Rock"
    _sid, _started, mode, artist, track = next(s for s in e.list_sessions() if s[0] == sid)
    assert seed_label(mode, artist, track) == "Radio: Classic Rock / Rock"
