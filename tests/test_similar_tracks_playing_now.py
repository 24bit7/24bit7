"""
Similar Tracks with the Seed setting on Playing Now: tracks sampled from Playing Now,
each in turn finding its share, plus Similar Artists' "Already in Playing Now" wording.
"""

import re

QUIET = dict(DRIFT_TRACKS="0", DRIFT_ARTISTS="0", SKIP_PLAYED_TRACKS="0", SKIP_PLAYED_ARTISTS="0",
             AI_MODERATOR="off")


def play_mix(app):
    j = app.jriver
    keys = [j.key_of("Queen", "Bohemian Rhapsody"), j.key_of("The Hollies", "Bus Stop"),
            j.key_of("The Byrds", "Mr. Tambourine Man"), j.key_of("Badfinger", "Baby Blue"),
            j.key_of("Kinks, The", "Waterloo Sunset")]
    j.play("Speakers", keys)
    return keys


def build(app):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                              playing_now=True)
    return r


def test_samples_tracks_from_different_artists(app):
    app.set_env(PN_SAMPLE_TRACKS="3", PN_TRACKS_PER_SAMPLE="2", **QUIET)
    play_mix(app)
    r = build(app)
    line = next((l for l in r if "Tracks sampled from Playing Now:" in l), "")
    pairs = line.split(":", 1)[1].split(";")
    assert len(pairs) == 3, r.text()
    assert len({p.split(" - ")[0].strip() for p in pairs}) == 3, r.text()
    assert len(re.findall(r"Similar to .+, taking", r.text())) == 3, r.text()
    assert r.has("Done:"), r.text()


def test_leaves_out_tracks_already_in_playing_now(app):
    app.set_env(PN_SAMPLE_TRACKS="5", PN_TRACKS_PER_SAMPLE="3", **QUIET)
    keys = play_mix(app)
    r = build(app)
    playlist = app.jriver.zone("Speakers").playlist
    assert playlist[0] == keys[0], r.text()
    assert not set(playlist[1:]) & set(keys), r.text()


def test_most_tracks_per_artist_counts_across_the_list(app):
    app.set_env(PN_SAMPLE_TRACKS="5", PN_TRACKS_PER_SAMPLE="4", PN_SIMILAR_TRACK_PER_ARTIST="1", **QUIET)
    play_mix(app)
    r = build(app)
    from collections import Counter
    titles = app.jriver.titles("Speakers")[1:]
    per = Counter(t.split(" - ")[0] for t in titles)
    assert titles and max(per.values()) == 1, (per, r.text())


def test_similar_first_order_builds(app):
    app.set_env(PN_SAMPLE_TRACKS="3", PN_TRACKS_PER_SAMPLE="2", SIMILAR_TRACK_ORDER="similar first", **QUIET)
    play_mix(app)
    r = build(app)
    assert r.has("most similar first"), r.text()


def test_one_track_falls_back_to_current_track(app):
    app.set_env(**QUIET)
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    r = build(app)
    assert r[0].startswith("Similar Tracks: The Beatles - Something") or r.has("Similar Tracks: The Beatles - Something")
    assert r.has("fewer than 2 tracks"), r.text()
    assert r.has("Done:"), r.text()


def test_review_mode_playing_now_column_for_tracks(app):
    assert app.engine.playing_now_track_figures()["PN_TRACKS_PER_SAMPLE"] == 6
    app.set_env(REVIEW_SAME_TRACKS_PN="0", REVIEW_PN_TRACKS_PER_SAMPLE="3")
    assert app.engine.playing_now_track_figures(review=True)["PN_TRACKS_PER_SAMPLE"] == 3
    assert app.engine.playing_now_track_figures(review=False)["PN_TRACKS_PER_SAMPLE"] == 6


def test_similar_artists_says_already_in_playing_now(app):
    app.set_env(PN_SAMPLE_ARTISTS="5", PN_TRACKS_PER_ARTIST_PICK="20", PN_TRACKS_PER_ARTIST_POOL="20", **QUIET)
    play_mix(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                       playing_now=True)
    assert r.has("Already in Playing Now: Waterloo Sunset"), r.text()
    assert not r.has("In library: Waterloo Sunset"), r.text()
