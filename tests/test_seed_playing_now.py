"""
Similar Artists: the "only counts if it gives a library track" rule, and the
Seed setting's Playing Now option (artists sampled from Playing Now, each in turn).
"""

import re

from fakes import NOT_IN_LIBRARY

QUIET = dict(DRIFT_ARTISTS="0", SKIP_PLAYED_ARTISTS="0", AI_MODERATOR="off")


def similar_lines(r):
    """The similar artists the build read, from their '  Artist (Sources)...' lines."""
    return [m.group(1) for line in r if (m := re.match(r"^  (\S.*?) \(([^)]*)\)\.\.\.$", line))
            and m.group(2) != "seed"]


def play_mix(app, pos=0):
    j = app.jriver
    keys = [j.key_of("Queen", "Bohemian Rhapsody"), j.key_of("The Hollies", "Bus Stop"),
            j.key_of("The Byrds", "Mr. Tambourine Man"), j.key_of("Badfinger", "Baby Blue"),
            j.key_of("Kinks, The", "Waterloo Sunset")]
    j.play("Speakers", keys, pos=pos)
    return keys


def test_artist_with_no_library_tracks_is_skipped(app):
    """The sources put three artists you don't own first: they're read past, and 2 library artists still come."""
    app.set_env(SIMILAR_ARTIST_LIMIT="2", **QUIET)
    real = app.web.similar_artists
    app.web.similar_artists = lambda artist: NOT_IN_LIBRARY + [a for a in real(artist) if a not in NOT_IN_LIBRARY]
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    assert r.has("Similar artists in your library: 2 of 2"), r.text()
    assert r.has("skipped with no tracks in your library"), r.text()
    others = {t.split(" - ")[0] for t in app.jriver.titles("Speakers")} - {"The Beatles"}
    assert len(others) >= 2, app.jriver.titles("Speakers")


def test_play_seed_setting(app):
    assert not app.engine.play_seed_is_playing_now()
    app.set_env(PLAY_SEED="playing_now")
    assert app.engine.play_seed_is_playing_now()


def test_playing_now_samples_artists(app):
    app.set_env(PN_SAMPLE_ARTISTS="3", PN_ARTISTS_PER_SAMPLE="2", **QUIET)
    play_mix(app)
    r = app.Lines()
    seed = app.engine.seed_or_last_played(report=r)
    app.engine.create_similar_playlist(report=r, seed_info=seed, playing_now=True)
    line = next((l for l in r if "Artists sampled from Playing Now:" in l), "")
    assert len(line.split(":", 1)[1].split(",")) == 3, r.text()
    assert r.has("Similar Artists: Playing Now (5 tracks, 5 artists)"), r.text()
    assert r.has("Done:"), r.text()


def test_playing_now_leaves_out_tracks_already_there(app):
    app.set_env(PN_SAMPLE_ARTISTS="5", PN_ARTISTS_PER_SAMPLE="2", **QUIET)
    keys = play_mix(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                       playing_now=True)
    playlist = app.jriver.zone("Speakers").playlist
    assert playlist[0] == keys[0], r.text()   # the playing track stays at the front
    assert not set(playlist[1:]) & set(keys), r.text()


def test_playing_now_never_repeats_a_similar_artist(app):
    app.set_env(PN_SAMPLE_ARTISTS="5", PN_ARTISTS_PER_SAMPLE="2", **QUIET)
    play_mix(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                       playing_now=True)
    read = similar_lines(r)
    assert read and len(read) == len(set(read)), r.text()
    assert len(re.findall(r"Similar to .+, taking", r.text())) == 5, r.text()


def test_playing_now_with_one_track_uses_the_current_track(app):
    app.set_env(**QUIET)
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                       playing_now=True)
    assert r.has("fewer than 2 tracks"), r.text()
    assert r.has("Similar Artists: The Beatles - Something"), r.text()
    assert r.has("Done:"), r.text()


def test_search_seed_ignores_playing_now(app):
    app.set_env(**QUIET)
    play_mix(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"),
                                       playing_now=True)
    assert r.has("Similar Artists: The Beatles - Something"), r.text()
    assert not r.has("Artists sampled from Playing Now"), r.text()


def test_review_mode_playing_now_column(app):
    assert app.engine.playing_now_artist_figures()["PN_SAMPLE_ARTISTS"] == 5
    app.set_env(REVIEW_SAME_ARTISTS_PN="0", REVIEW_PN_SAMPLE_ARTISTS="2", PN_SAMPLE_ARTISTS="6")
    assert app.engine.playing_now_artist_figures(review=True)["PN_SAMPLE_ARTISTS"] == 2
    assert app.engine.playing_now_artist_figures(review=False)["PN_SAMPLE_ARTISTS"] == 6
    app.set_env(REVIEW_SAME_ARTISTS_PN="1")
    assert app.engine.playing_now_artist_figures(review=True)["PN_SAMPLE_ARTISTS"] == 6
