"""
Inner Circle (stage B of the playlist builder, 31 Oct 2026): a mode on a matching config. The
seed's closest few (or the artists or tracks sampled from Playing Now) make the circle; each
member's own similar list is fetched, and only what two or more of those lists agree on goes
in. It stops short and says so rather than padding, and a neighbour that's really a circle
member under another name is skipped.
"""

QUIET_ARTISTS = dict(DRIFT_ARTISTS="0", SKIP_PLAYED_ARTISTS="0", AI_MODERATOR="off", AI_MODERATOR_ARTISTS="off",
                     SIMILAR_SOURCES="lastfm")
QUIET_TRACKS = dict(DRIFT_TRACKS="0", DRIFT_ARTISTS="0", SKIP_PLAYED_TRACKS="0", SKIP_PLAYED_ARTISTS="0",
                    AI_MODERATOR="off", AI_MODERATOR_TRACKS="off", SIMILAR_TRACK_SOURCES="lastfm")
STONES, FLOYD, HENDRIX, QUEEN, SG, HARRISON, SIGUR, BADFINGER = (
    "The Rolling Stones", "Pink Floyd", "Jimi Hendrix", "Queen", "Simon & Garfunkel", "George Harrison",
    "Sigur Rós", "Badfinger")


def artists_in(app):
    return {t.split(" - ")[0] for t in app.jriver.titles("Speakers")}


def fake_similar_artists(app, lists):
    """blended_similar_artists as the fake sources would answer: a list per seed name, Last.fm's."""
    def similar(seed, limit=20, seed_track=None, report=None):
        name = seed[0] if isinstance(seed, list) else seed
        found = lists.get(name, [])
        return [(a, ["Last.fm"]) for a in found[:limit]], ("Last.fm" if found else "none")
    app.engine.blended_similar_artists = similar


def fake_similar_tracks(app, lists):
    """similar_track_candidates as the fake sources would answer: a list per (artist, title)."""
    def candidates(artists, title, report=None):
        found = lists.get((artists[0], title), [])
        return [(pair, ["Last.fm"]) for pair in found], (["Last.fm"] if found else [])
    app.engine.similar_track_candidates = candidates


def test_current_track_takes_the_seeds_closest_three_and_what_their_lists_agree_on(app):
    app.set_env(INNER_CIRCLE_ARTISTS="1", INNER_CIRCLE_ARTISTS_SIZE="3", INNER_CIRCLE_ARTISTS_AGREE="2", **QUIET_ARTISTS)
    fake_similar_artists(app, {
        "The Beatles": [STONES, FLOYD, HENDRIX, QUEEN, SG],
        STONES: [FLOYD, QUEEN, "Pink Floyd Redux", SG],
        FLOYD: [HENDRIX, SIGUR],
        HENDRIX: [QUEEN, "Pink Floyd Redux", FLOYD],
    })
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    assert r.has("Inner Circle: The Rolling Stones, Pink Floyd, Jimi Hendrix (circle of 3, agree on 2)"), r.text()
    assert r.has("1 artists on 2 or more of their lists; 1 skipped as the same act."), r.text()
    assert r.has("Similar artists in your library: 4 of 4."), r.text()
    assert artists_in(app) - {"The Beatles"} == {STONES, FLOYD, HENDRIX, QUEEN}, app.jriver.titles("Speakers")
    assert r.has("Queen (on 2 of 3 lists)..."), r.text()


def test_current_track_stops_short_and_says_so_when_nothing_agrees(app):
    app.set_env(INNER_CIRCLE_ARTISTS="1", INNER_CIRCLE_ARTISTS_SIZE="3", INNER_CIRCLE_ARTISTS_AGREE="3", **QUIET_ARTISTS)
    fake_similar_artists(app, {
        "The Beatles": [STONES, FLOYD, HENDRIX, QUEEN],
        STONES: [QUEEN], FLOYD: [SG], HENDRIX: [SIGUR],
    })
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    assert r.has("Note: Inner Circle found no artists the circle agrees on."), r.text()
    assert r.has("Similar artists in your library: 3 of 3."), r.text()
    assert artists_in(app) - {"The Beatles"} == {STONES, FLOYD, HENDRIX}, app.jriver.titles("Speakers")


def test_off_by_default_leaves_artist_matching_as_it_was(app):
    app.set_env(SIMILAR_ARTIST_LIMIT="3", **QUIET_ARTISTS)
    fake_similar_artists(app, {"The Beatles": [STONES, FLOYD, HENDRIX, QUEEN], STONES: [QUEEN]})
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    assert not r.has("Inner Circle") and r.has("Similar artists in your library: 3 of 3."), r.text()


def test_playing_now_makes_the_sampled_artists_the_circle(app):
    from test_seed_playing_now import play_mix
    app.set_env(INNER_CIRCLE_ARTISTS="1", INNER_CIRCLE_ARTISTS_SIZE="3", INNER_CIRCLE_ARTISTS_AGREE="2",
                PN_SAMPLE_ARTISTS="5", PN_ARTISTS_PER_SAMPLE="2", **QUIET_ARTISTS)
    play_mix(app)   # Queen, The Hollies, The Byrds, Badfinger and the Kinks: all five are the circle
    fake_similar_artists(app, {
        QUEEN: [STONES, FLOYD], "The Hollies": [STONES, "The Byrds"], "The Byrds": [STONES, SG],
        BADFINGER: [FLOYD, HARRISON], "Kinks, The": [HARRISON], "The Kinks": [HARRISON],
    })
    r = app.Lines()
    seed = app.engine.seed_or_last_played(report=r)
    app.engine.create_similar_playlist(report=r, seed_info=seed, playing_now=True)
    assert r.has("(circle of 5, agree on 2)"), r.text()
    assert r.has("3 artists on 2 or more of their lists."), r.text()
    assert r.has("Similar artists in your library: 3 of 10."), r.text()
    added = artists_in(app) - {QUEEN, "The Hollies", "The Byrds", BADFINGER, "Kinks, The", "The Kinks"}
    assert added == {STONES, FLOYD, HARRISON}, app.jriver.titles("Speakers")


def test_track_matching_current_track_circle_of_three_tracks(app):
    app.set_env(INNER_CIRCLE_TRACKS="1", INNER_CIRCLE_TRACKS_SIZE="3", INNER_CIRCLE_TRACKS_AGREE="2",
                SIMILAR_TRACK_COUNT="8", SIMILAR_TRACK_PER_ARTIST="2", **QUIET_TRACKS)
    fake_similar_tracks(app, {
        ("The Beatles", "Something"): [(STONES, "The Last Time"), (FLOYD, "Fearless"), (HENDRIX, "Crosstown Traffic"),
                                       (SG, "The Boxer")],
        (STONES, "The Last Time"): [(QUEEN, "Bohemian Rhapsody"), (HENDRIX, "Crosstown Traffic"), (SIGUR, "Glósóli")],
        (FLOYD, "Fearless"): [(QUEEN, "Bohemian Rhapsody"), (HARRISON, "My Sweet Lord")],
        (HENDRIX, "Crosstown Traffic"): [(HARRISON, "My Sweet Lord"), (BADFINGER, "Baby Blue")],
    })
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    assert r.has("Inner Circle: The Rolling Stones - The Last Time; Pink Floyd - Fearless; Jimi Hendrix - Crosstown Traffic "
                 "(circle of 3, agree on 2)"), r.text()
    assert r.has("2 tracks on 2 or more of their lists."), r.text()
    titles = set(app.jriver.titles("Speakers"))
    assert {"The Rolling Stones - The Last Time", "Pink Floyd - Fearless", "Jimi Hendrix - Crosstown Traffic",
            "Queen - Bohemian Rhapsody", "George Harrison - My Sweet Lord"} <= titles, titles
    assert not {SG, SIGUR, BADFINGER} & {t.split(" - ")[0] for t in titles}, titles
    assert not r.has("relaxed to"), "the circle has agreed already, so nothing is relaxed"


def test_track_matching_playing_now_makes_the_sampled_tracks_the_circle(app):
    from test_similar_tracks_playing_now import play_mix
    app.set_env(INNER_CIRCLE_TRACKS="1", INNER_CIRCLE_TRACKS_SIZE="3", INNER_CIRCLE_TRACKS_AGREE="2",
                PN_SAMPLE_TRACKS="5", PN_TRACKS_PER_SAMPLE="2", SIMILAR_TRACK_PER_ARTIST="2", **QUIET_TRACKS)
    keys = play_mix(app)
    fake_similar_tracks(app, {
        (QUEEN, "Bohemian Rhapsody"): [(STONES, "The Last Time"), (FLOYD, "Fearless")],
        ("The Hollies", "Bus Stop"): [(STONES, "The Last Time"), (HARRISON, "My Sweet Lord")],
        ("The Byrds", "Mr. Tambourine Man"): [(STONES, "The Last Time")],
        (BADFINGER, "Baby Blue"): [(FLOYD, "Fearless")],
        ("Kinks, The", "Waterloo Sunset"): [(HENDRIX, "Crosstown Traffic")],
    })
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                              playing_now=True)
    assert r.has("(circle of 5, agree on 2)") and r.has("2 tracks on 2 or more of their lists."), r.text()
    assert r.has("Taking 10 from what the circle agrees on:"), r.text()
    playlist = app.jriver.zone("Speakers").playlist
    assert playlist[0] == keys[0], "the current track stays; the rest of Playing Now is replaced, as ever"
    added = set(app.jriver.titles("Speakers")) - {"Queen - Bohemian Rhapsody"}
    assert added == {"The Rolling Stones - The Last Time", "Pink Floyd - Fearless"}, app.jriver.titles("Speakers")


def test_same_act_rule_is_narrow(app):
    e = app.engine
    assert e._same_act("nick cave", "nick cave & the bad seeds")
    assert e._same_act("the jimi hendrix experience", "jimi hendrix")
    assert not e._same_act("air", "air supply"), "short names aren't trusted"
    assert not e._same_act("muse", "amused")
    assert not e._same_act("pink floyd", "pink floyd")
    assert not e._same_act("queen", "queens of the stone age")
