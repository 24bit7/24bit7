"""
Artist + Guests (30 Oct 2026; two configs since stage C, 31 Oct): the seed artist's top tracks, two at
a time, with one track from a close similar artist between them. Honest when guests run short:
the hosts carry on alone.
"""

QUIET = dict(DRIFT_ARTISTS="0", SKIP_PLAYED_ARTISTS="0", SKIP_PLAYED_TOP="0", AI_MODERATOR="off",
             SKIP_LONG_CLOSERS_ARTISTS="0", SKIP_LONG_CLOSERS_TOP="0", TOP_TRACKS_COUNT="6", TOP_TRACKS_ORDER="popular")


def seed(app, artist):
    return app.engine.typed_seed_info(artist, "")


def artist_of(title):
    return title.split(" - ", 1)[0]


def headliner(app):
    import buttons
    h = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    buttons.set_settings(h["id"], dict(h["settings"], TOP_TRACKS_COUNT="6"))   # shipped at twelve; these count hosts in sixes
    return buttons.get(h["id"])


def test_weave_alternates_appends_or_shuffles(app):
    e = app.engine
    hosts, guests = ["h1", "h2", "h3", "h4", "h5", "h6"], ["g1", "g2", "g3"]
    assert e.weave([hosts, guests], "alternate", [2, 1]) == ["h1", "h2", "g1", "h3", "h4", "g2", "h5", "h6", "g3"]
    assert e.weave([["h1", "h2", "h3", "h4"], ["g1"]], "alternate", [2, 1]) == ["h1", "h2", "g1", "h3", "h4"]
    assert e.weave([hosts, guests], "append") == hosts + guests
    assert sorted(e.weave([hosts, guests], "shuffle")) == sorted(hosts + guests)


def test_headliner_puts_a_guest_after_every_two_hosts(app):
    app.set_env(**QUIET)
    import buttons
    r = app.Lines()
    buttons.run(headliner(app), report=r, seed_info=seed(app, "The Beatles"))
    titles = app.jriver.titles("Speakers")
    assert len(titles) == 11, (titles, r.text())   # six hosts, five guests
    for i, title in enumerate(titles[:9], 1):
        assert (artist_of(title) != "The Beatles") == (i % 3 == 0), (i, titles)
    assert all(artist_of(tt) != "The Beatles" for tt in titles[9:]), "the guests left over follow"
    guests = [artist_of(tt) for tt in titles if artist_of(tt) != "The Beatles"]
    assert len(set(guests)) == 5, guests
    assert r.has("Mix: alternating, 2 from config 1, 1 from config 2."), r.text()


def test_headliner_carries_on_alone_when_guests_run_short(app, monkeypatch):
    app.set_env(**QUIET)
    import buttons
    e = app.engine
    monkeypatch.setattr(e, "blended_similar_artists", lambda *a, **k: ([("Queen", ["Last.fm"])], "Last.fm"))
    # Queen's one pick is random among her top tracks, and the fake sources name one nobody owns: picked, Queen
    # gives nothing and the test saw six tracks, about one run in four (it stopped the 1.33.0 build, 10 Nov 2026).
    # The pick isn't what this test is about, so it takes the first.
    monkeypatch.setattr(e.random, "sample", lambda names, n: list(names)[:n])
    r = app.Lines()
    buttons.run(headliner(app), report=r, seed_info=seed(app, "The Beatles"))
    titles = app.jriver.titles("Speakers")
    assert len(titles) == 7 and artist_of(titles[2]) == "Queen", titles
    assert all(artist_of(tt) == "The Beatles" for tt in titles[3:]), titles
    assert r.has("Similar artists in your library: 1 of 5"), r.text()


def test_headliner_with_no_guests_at_all(app, monkeypatch):
    app.set_env(**QUIET)
    import buttons
    e = app.engine
    monkeypatch.setattr(e, "blended_similar_artists", lambda *a, **k: ([], "none"))
    r = app.Lines()
    buttons.run(headliner(app), report=r, seed_info=seed(app, "The Beatles"))
    titles = app.jriver.titles("Speakers")
    assert len(titles) == 6 and all(artist_of(tt) == "The Beatles" for tt in titles), titles
    assert not r.has("Mix:"), "one config's tracks: nothing to weave"
