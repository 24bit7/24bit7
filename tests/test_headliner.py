"""
Headliner (30 Oct 2026): the seed artist's top tracks, with every third track a guest spot,
one track each from the closest similar artists in the library. Honest when guests run short.
"""


def seed(app, artist):
    return app.engine.typed_seed_info(artist, "")


def artist_of(title):
    return title.split(" - ", 1)[0]


def test_weave_puts_a_guest_every_third_track(app):
    e = app.engine
    assert e.weave_guests(["h1", "h2", "h3", "h4", "h5", "h6"], ["g1", "g2", "g3"]) == \
        ["h1", "h2", "g1", "h3", "h4", "g2", "h5", "h6", "g3"]
    assert e.weave_guests(["h1", "h2", "h3", "h4"], ["g1"]) == ["h1", "h2", "g1", "h3", "h4"]


def test_headliner_every_third_track_is_a_different_guest(app):
    app.set_env(TOP_TRACKS_COUNT="6", TOP_TRACKS_ORDER="popular")
    r = app.Lines()
    app.engine.play_headliner(report=r, seed_info=seed(app, "The Beatles"))
    titles = app.jriver.titles("Speakers")
    assert len(titles) == 9, r.text()
    for i, title in enumerate(titles, 1):
        assert (artist_of(title) != "The Beatles") == (i % 3 == 0), (i, titles)
    guests = [artist_of(tt) for tt in titles[2::3]]
    assert len(set(guests)) == 3, guests
    assert r.has("Headliner: The Beatles") and r.has("played alongside"), r.text()


def test_headliner_says_when_guests_run_short(app, monkeypatch):
    app.set_env(TOP_TRACKS_COUNT="6", TOP_TRACKS_ORDER="popular")
    e = app.engine
    monkeypatch.setattr(e, "blended_similar_artists", lambda *a, **k: ([("Queen", ["Last.fm"])], "Last.fm"))
    r = app.Lines()
    e.play_headliner(report=r, seed_info=seed(app, "The Beatles"))
    titles = app.jriver.titles("Speakers")
    assert len(titles) == 7 and artist_of(titles[2]) == "Queen", titles
    assert r.has("1 of 3 guest spots filled"), r.text()


def test_headliner_on_their_own_with_no_guests(app, monkeypatch):
    app.set_env(TOP_TRACKS_COUNT="6", TOP_TRACKS_ORDER="popular")
    e = app.engine
    monkeypatch.setattr(e, "blended_similar_artists", lambda *a, **k: ([], "none"))
    r = app.Lines()
    e.play_headliner(report=r, seed_info=seed(app, "The Beatles"))
    titles = app.jriver.titles("Speakers")
    assert len(titles) == 6 and all(artist_of(tt) == "The Beatles" for tt in titles), titles
    assert r.has("on their own"), r.text()


def test_headliner_never_asks_the_ai_for_guest_tracks(app):
    app.set_env(TOP_TRACKS_COUNT="6", SIMILAR_TRACK_SOURCES="ai,lastfm")
    app.engine.play_headliner(report=app.Lines(), seed_info=seed(app, "The Beatles"))
    assert not any("songs most similar to" in sent for sent in getattr(app.ai, "sent", [])), app.ai.sent
