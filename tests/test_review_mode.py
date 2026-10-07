"""
Review Mode: an app build loads the playlist into a stopped zone and leaves it stopped on track one.
"""


def build(app):
    r = app.Lines()
    seed = app.engine.typed_seed_info("The Beatles", "Here Comes The Sun")
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed)
    return r


def test_play_instantly_starts_the_zone(app):
    build(app)
    z = app.jriver.zone("Speakers")
    assert z.state == 2 and len(z.playlist) > 5


def test_review_mode_loads_and_stops(app, monkeypatch):
    monkeypatch.setattr(app.engine, "REVIEW_MODE", True)
    r = build(app)
    z = app.jriver.zone("Speakers")
    assert z.state == 0, r.text()
    assert len(z.playlist) > 5 and z.pos == 0, r.text()
    assert r.has("Loaded for review"), r.text()
    assert not r.has("Fast start"), "no fast start in Review Mode"


def test_review_mode_leaves_a_playing_zone_playing(app, monkeypatch):
    keys = [r["Key"] for r in app.jriver.by_key.values()][:2]
    app.jriver.play("Speakers", keys)
    monkeypatch.setattr(app.engine, "REVIEW_MODE", True)
    r = build(app)
    z = app.jriver.zone("Speakers")
    assert z.state == 2, r.text()
    assert not r.has("Loaded for review"), r.text()


def test_voice_ignores_review_mode(app, monkeypatch):
    monkeypatch.setattr(app.engine, "REVIEW_MODE", True)
    monkeypatch.setattr(app.engine, "VOICE_TAKEOVER", True)
    build(app)
    assert app.jriver.zone("Speakers").state == 2
