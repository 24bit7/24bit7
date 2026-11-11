"""
The console heads a build with its playlist's kind, Artist Matching or Track Matching (Ben, 11 Nov 2026): it said
"Similar Artists:" and "Similar Tracks:", names the playlist pages had dropped. The Log reads the new names, and
older entries headed the old way show under the new names too, so the Log reads one name all the way down.
"""

import pytest


@pytest.fixture
def german(app):
    import i18n
    i18n.set_language("de")
    yield i18n
    i18n.set_language("en")


def heading(r):
    return next(line for line in r if line.strip()).strip()


def test_a_track_matching_build_is_headed_track_matching(app):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles",
                                                                                              "Here Comes The Sun"))
    assert heading(r).startswith("Track Matching: The Beatles - Here Comes The Sun"), r.text()
    assert "Similar Tracks:" not in r.text(), r.text()


def test_an_artist_matching_build_is_headed_artist_matching(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    assert heading(r) == "Artist Matching: The Beatles - Something", r.text()
    assert "Similar Artists:" not in r.text(), r.text()


def test_the_headings_in_german(app, german):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles",
                                                                                              "Here Comes The Sun"))
    assert heading(r).startswith("Titel-Abgleich: The Beatles - Here Comes The Sun"), r.text()
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    assert heading(r) == "Künstler-Abgleich: The Beatles - Something", r.text()


def test_the_log_names_new_builds_and_old_ones_alike(app):
    import buildlog
    app.engine.LAST_BUILD = None   # the kind comes from the console text, as for a voice or older build
    for text, kind in (("Track Matching: x\nDone: 1 track queued in Speakers.", "Track Matching"),
                       ("Similar Tracks: x\nDone: 1 track queued in Speakers.", "Track Matching"),
                       ("Artist Matching: x\nDone: 1 track queued in Speakers.", "Artist Matching"),
                       ("Similar Artists: x\nDone: 1 track queued in Speakers.", "Artist Matching")):
        buildlog.record_job(None, text)
        assert buildlog.recent(limit=1)[0]["kind"] == kind, text
    # kept before the rename, under the old names
    assert buildlog.playlist_type({"kind": "Similar Tracks"}) == "Track Matching"
    assert buildlog.playlist_type({"kind": "Similar Artists (Cancelled)"}) == "Artist Matching (Cancelled)"
    assert buildlog.playlist_type({"kind": "Similar Tracks", "chain_pos": 3}) == "Track Matching · Non-stop 003"
    assert buildlog.INSTANT["music_like"] == "Artist Matching" and buildlog.INSTANT["tracks_like"] == "Track Matching"


def test_the_log_names_in_german(app, german):
    import buildlog
    assert buildlog.playlist_type({"kind": "Similar Tracks"}) == "Titel-Abgleich"
    assert buildlog.playlist_type({"kind": "Artist Matching"}) == "Künstler-Abgleich"
    app.engine.LAST_BUILD = None
    buildlog.record_job(None, "Ähnliche Titel: x\nFertig: 1 Titel.")   # an older German build
    assert buildlog.recent(limit=1)[0]["kind"] == "Track Matching"
