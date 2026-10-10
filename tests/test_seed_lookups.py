"""Seed lookups: lead-artist fallback, MusicBrainz recording search, title variants."""


def a_track(app):
    a = next(a for a in app.web.lib_artists if app.web.top_tracks(a))
    return a, app.web.top_tracks(a)[0]


def test_similar_tracks_fall_back_to_the_lead_artist(app):
    app.set_env(SIMILAR_TRACK_SOURCES="lastfm")
    lead, track = a_track(app)
    joint = f"{lead} & Nobody Known"
    app.web.unknown.add(joint)
    lines = app.Lines()
    blended, answered = app.engine.similar_track_candidates([joint], track, report=lines)
    assert answered == ["Last.fm"] and blended
    asked = [c[2].get("artist") for c in app.web.calls if c[0] == "lastfm"]
    assert asked[:2] == [joint, lead]   # the full credit first, then the lead artist


def test_a_known_credit_never_tries_the_lead(app):
    app.set_env(SIMILAR_TRACK_SOURCES="lastfm")
    lead, track = a_track(app)
    app.engine.similar_track_candidates([lead], track, report=app.Lines())
    asked = [c[2].get("artist") for c in app.web.calls if c[0] == "lastfm"]
    assert asked == [lead]


def test_similar_artists_fall_back_and_drop_the_lead(app):
    app.set_env(SIMILAR_SOURCES="lastfm", SIMILAR_MIN_AGREEMENT="1")
    lead, _ = a_track(app)
    joint = f"{lead} & Nobody Known"
    app.web.unknown.add(joint)
    blended, label = app.engine.blended_similar_artists(joint, limit=10)
    names = [a for a, _ in blended]
    assert names and app.engine.artist_key(lead) not in [app.engine.artist_key(n) for n in names]


def test_listenbrainz_found_through_musicbrainz_search(app):
    app.set_env(SIMILAR_TRACK_SOURCES="listenbrainz")
    artist, track = a_track(app)
    app.web.acr_miss.add((artist, track))
    pairs = app.engine.listenbrainz_similar_tracks(artist, track)
    assert pairs
    assert any(c[0] == "musicbrainz" and c[1].startswith("/ws/2/recording") for c in app.web.calls)


def test_listenbrainz_still_empty_when_nobody_knows_it(app):
    artist, track = a_track(app)
    app.web.acr_miss.add((artist, track))
    app.web.unknown.add(artist)
    assert app.engine.listenbrainz_similar_tracks(artist, track) == []


def test_title_folding(app):
    f = app.engine.title_folded
    assert f("King Tubbys Meets Rockers Uptown") == f("King Tubby Meets Rockers Uptown")
    assert f("The Message") == f("Message")
    assert f("Paranoid") != f("Paranoid Android")
