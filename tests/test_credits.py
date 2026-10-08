"""
Show Credits: album-wide and per-track Discogs credits, in the order chosen in
Settings > Other. Discogs is faked by handing explore_credits a release.
"""

RELEASE = {
    "extraartists": [
        {"name": "Tommy LiPuma", "role": "Producer", "tracks": ""},
        {"name": "Al Schmitt", "role": "Recorded By, Mixed By", "tracks": ""},
        {"name": "Jeff Hamilton", "role": "Drums", "tracks": "2 to 4"},
        {"name": "Christian McBride", "role": "Bass", "tracks": "1, 5"},
        {"name": "Diana Krall", "role": "Piano", "tracks": ""},   # the artist: always left out
    ],
    "tracklist": [
        {"type_": "heading", "title": "Side One"},
        {"position": "1", "title": "Like Someone In Love", "type_": "track",
         "extraartists": [{"name": "Russell Malone", "role": "Guitar"}]},
        {"position": "2", "title": "Isn't It Romantic", "type_": "track"},
        {"position": "3", "title": "L-O-V-E", "type_": "track"},
        {"position": "4", "title": "No Moon At All", "type_": "track",
         "extraartists": [{"name": "Anthony Wilson", "role": "Guitar"}]},
        {"position": "5", "title": "Blue Skies", "type_": "track"},
    ],
}


def fake_discogs(app, monkeypatch, title="No Moon at All (Remastered)", release=RELEASE):
    e = app.engine
    monkeypatch.setattr(e, "DISCOGS_TOKEN", "test-discogs")
    monkeypatch.setattr(e, "refresh_settings_if_changed", lambda: None)
    monkeypatch.setattr(e, "get_playing_info", lambda *a, **k: {
        "PlayingNowPosition": "0", "Artist": "Diana Krall", "Album": "Turn Up the Quiet", "Name": title})
    monkeypatch.setattr(e, "discogs_find_release", lambda artist, album: (1, "Turn Up The Quiet (2017)"))
    monkeypatch.setattr(e, "discogs_get", lambda path, params=None: release)


def run(app, scope, first):
    e = app.engine
    e.CREDITS_SCOPE, e.CREDITS_FIRST = scope, first
    out = app.Lines()
    e.explore_credits(report=out)
    return out


def test_covers_reads_ranges_and_lists(app):
    engine = app.engine
    positions = ["A1", "A2", "A3", "B1", "B2"]
    assert engine._discogs_covers("A2 to B1", positions) == {"A2", "A3", "B1"}
    assert engine._discogs_covers("A1, B2", positions) == {"A1", "B2"}
    assert engine._discogs_covers("C9, A1 to Z9", positions) == set()   # unknown positions are ignored


def test_credit_lists_split_album_and_tracks(app):
    album, per_track = app.engine.discogs_credit_lists(RELEASE, "Diana Krall")
    assert [name for name, _ in album] == ["Tommy LiPuma", "Al Schmitt"]
    by_title = {title: [n for n, _ in people] for _, title, people in per_track}
    assert by_title["No Moon At All"] == ["Anthony Wilson", "Jeff Hamilton"]   # guitar ranks above drums
    assert by_title["Like Someone In Love"] == ["Russell Malone", "Christian McBride"]
    assert by_title["Blue Skies"] == ["Christian McBride"]
    assert len(per_track) == 5   # the Side One heading isn't a track


def test_current_track_first(app, monkeypatch):
    fake_discogs(app, monkeypatch)
    text = run(app, "current", "track").text()
    track_at, album_at = text.index("Credited on this track (No Moon At All)"), text.index("Credited on the album")
    assert track_at < album_at
    assert "Jeff Hamilton (Drums)" in text and "Anthony Wilson (Guitar)" in text
    assert "Russell Malone" not in text and "Diana Krall (" not in text


def test_album_first(app, monkeypatch):
    fake_discogs(app, monkeypatch)
    text = run(app, "current", "album").text()
    assert text.index("Credited on the album") < text.index("Credited on this track")


def test_all_tracks_grouped(app, monkeypatch):
    fake_discogs(app, monkeypatch)
    out = run(app, "all", "track")
    text = out.text()
    assert "Credited on each track:" in text
    assert out.has("    1 Like Someone In Love") and out.has("      Russell Malone (Guitar)")
    assert out.has("    5 Blue Skies")
    assert text.index("Credited on each track") < text.index("Credited on the album")


def test_track_not_on_release(app, monkeypatch):
    fake_discogs(app, monkeypatch, title="A Song From Somewhere Else")
    text = run(app, "current", "track").text()
    assert "isn't on this Discogs release" in text
    assert "Credited on the album" in text   # the album credits still show


def test_track_without_its_own_credits(app, monkeypatch):
    release = {"extraartists": [{"name": "Tommy LiPuma", "role": "Producer", "tracks": ""}],
               "tracklist": [{"position": "1", "title": "No Moon At All", "type_": "track"}]}
    fake_discogs(app, monkeypatch, release=release)
    assert "has no credits of its own" in run(app, "current", "track").text()
    assert "no track has credits of its own" in run(app, "all", "track").text()


def test_settings_load_and_fall_back(app):
    e = app.engine
    app.set_env(CREDITS_SCOPE="all", CREDITS_FIRST="album")
    assert (e.CREDITS_SCOPE, e.CREDITS_FIRST) == ("all", "album")
    app.set_env(CREDITS_SCOPE="nonsense", CREDITS_FIRST="")
    assert (e.CREDITS_SCOPE, e.CREDITS_FIRST) == ("current", "track")
