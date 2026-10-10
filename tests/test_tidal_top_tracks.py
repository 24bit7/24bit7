"""Tidal as a top tracks source: popularity order, a repeated version dropped, fallbacks."""


def on(app, **more):
    app.set_env(TIDAL_CLIENT_ID="test-id", TIDAL_CLIENT_SECRET="test-secret", TOP_TRACK_SOURCES="tidal", **more)


def an_artist(app):
    return next(a for a in app.web.lib_artists if len(app.web.top_tracks(a)) > 2)


def test_popularity_order_with_the_repeat_dropped(app):
    on(app)
    a = an_artist(app)
    titles = app.engine.tidal_top_tracks(a, limit=10)
    want = app.web.top_tracks(a)[:10]
    assert titles == want   # the acoustic repeat of the first never takes a place
    assert len(titles) == len(set(titles))


def test_lead_artist_fallback(app):
    on(app)
    a = an_artist(app)
    assert app.engine.tidal_top_tracks(f"{a} & Nobody Known", limit=3) == app.web.top_tracks(a)[:3]


def test_no_keys_skips_tidal_for_top_tracks(app):
    app.set_env(TIDAL_CLIENT_ID="", TIDAL_CLIENT_SECRET="", TOP_TRACK_SOURCES="tidal")
    assert not app.engine.source_has_key("tidal", "top")
    assert any("Tidal" in n for n in app.engine.missing_key_notes(top_tracks=True))


def test_tidal_down_fails_soft(app):
    on(app)
    app.web.down.add("tidal")
    assert app.engine.tidal_top_tracks(an_artist(app)) == []


def test_in_the_top_track_plan(app):
    on(app)
    providers, _ = app.engine.top_track_plan(10)
    assert [p[0] for p in providers] == ["Tidal"]
