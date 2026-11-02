"""
Consensus's fallback (Ben, 2 Nov 2026): "If Consensus finds fewer than [10] tracks, finish the playlist
with plain Artist Matching" (or Track Matching). Off by default, since Consensus's whole point is to come
up short rather than loosen; on, what the circle agreed on stays and the seed's own list fills the rest,
and the console says so.
"""

from test_inner_circle import QUIET_ARTISTS, QUIET_TRACKS, STONES, FLOYD, HENDRIX, QUEEN, SG, SIGUR, BADFINGER, HARRISON, \
    artists_in, fake_similar_artists, fake_similar_tracks


def nothing_agrees(app, **env):
    app.set_env(INNER_CIRCLE_ARTISTS="1", INNER_CIRCLE_ARTISTS_SIZE="3", INNER_CIRCLE_ARTISTS_AGREE="3",
                SIMILAR_ARTIST_LIMIT="4", **QUIET_ARTISTS, **env)
    fake_similar_artists(app, {
        "The Beatles": [STONES, FLOYD, HENDRIX, QUEEN],
        STONES: [QUEEN], FLOYD: [SG], HENDRIX: [SIGUR],
    })


def test_off_by_default_consensus_still_stops_short(app):
    import buttons
    import engine
    nothing_agrees(app)
    assert engine.INNER_CIRCLE["artists"] == (True, 3, 3, False, 10)
    assert "INNER_CIRCLE_ARTISTS_FALLBACK" in buttons.KIND_KEYS["artists"] and "INNER_CIRCLE_TRACKS_FALLBACK_MIN" in buttons.KIND_KEYS["tracks"]
    r = app.Lines()
    engine.create_similar_playlist(report=r, seed_info=engine.typed_seed_info("The Beatles", "Something"))
    assert r.has("Note: Consensus found no artists the circle agrees on."), r.text()
    assert not r.has("plain Artist Matching"), "no fallback unless asked"
    assert artists_in(app) - {"The Beatles"} == {STONES, FLOYD, HENDRIX}


def test_on_and_short_the_seeds_own_list_finishes_the_playlist_and_the_console_says_so(app):
    import engine
    nothing_agrees(app, INNER_CIRCLE_ARTISTS_FALLBACK="1", INNER_CIRCLE_ARTISTS_FALLBACK_MIN="50")
    r = app.Lines()
    engine.create_similar_playlist(report=r, seed_info=engine.typed_seed_info("The Beatles", "Something"))
    text = r.text()
    assert "tracks the circle agrees on, fewer than 50: the rest is plain Artist Matching." in text, text
    assert r.has("Plain Artist Matching: 1 more artists in your library."), text
    assert artists_in(app) - {"The Beatles"} == {STONES, FLOYD, HENDRIX, QUEEN}, "Queen, from the seed's own list"


def test_on_but_consensus_found_enough_nothing_changes(app):
    import engine
    nothing_agrees(app, INNER_CIRCLE_ARTISTS_FALLBACK="1", INNER_CIRCLE_ARTISTS_FALLBACK_MIN="1")
    r = app.Lines()
    engine.create_similar_playlist(report=r, seed_info=engine.typed_seed_info("The Beatles", "Something"))
    assert not r.has("plain Artist Matching"), "the circle's three gave more than one track: no fallback"
    assert artists_in(app) - {"The Beatles"} == {STONES, FLOYD, HENDRIX}


def test_track_matching_falls_back_to_the_seeds_own_list(app):
    import engine
    lists = {
        ("The Beatles", "Something"): [(STONES, "The Last Time"), (FLOYD, "Fearless"), (HENDRIX, "Crosstown Traffic"),
                                       (SG, "The Boxer"), (BADFINGER, "Baby Blue")],
        (STONES, "The Last Time"): [(QUEEN, "Bohemian Rhapsody")],
        (FLOYD, "Fearless"): [(HARRISON, "My Sweet Lord")],
        (HENDRIX, "Crosstown Traffic"): [(SIGUR, "Glósóli")],
    }
    app.set_env(INNER_CIRCLE_TRACKS="1", INNER_CIRCLE_TRACKS_SIZE="3", INNER_CIRCLE_TRACKS_AGREE="2",
                SIMILAR_TRACK_COUNT="8", SIMILAR_TRACK_PER_ARTIST="2", **QUIET_TRACKS)
    fake_similar_tracks(app, lists)
    r = app.Lines()
    engine.create_similar_tracks_playlist(report=r, seed_info=engine.typed_seed_info("The Beatles", "Something"))
    titles = set(app.jriver.titles("Speakers"))
    assert r.has("0 tracks on 2 or more of their lists.") and not r.has("plain Track Matching"), r.text()
    assert not {SG, BADFINGER} & {x.split(" - ")[0] for x in titles}, "off: the seed's own list isn't used"
    app.set_env(INNER_CIRCLE_TRACKS_FALLBACK="1", INNER_CIRCLE_TRACKS_FALLBACK_MIN="10")
    app.jriver.zone("Speakers").playlist.clear()
    r = app.Lines()
    engine.create_similar_tracks_playlist(report=r, seed_info=engine.typed_seed_info("The Beatles", "Something"))
    assert r.has("Consensus found 0 tracks the circle agrees on, fewer than 10: the rest is plain Track Matching."), r.text()
    titles = {x.split(" - ")[0] for x in app.jriver.titles("Speakers")}
    assert {SG, BADFINGER} <= titles, titles
