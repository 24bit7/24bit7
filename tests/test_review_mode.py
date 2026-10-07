"""
Review: an app build collects its tracks for the Review view and leaves JRiver alone.
"""


def build(app):
    r = app.Lines()
    seed = app.engine.typed_seed_info("The Beatles", "Here Comes The Sun")
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed)
    return r


def review_on(app, monkeypatch):
    monkeypatch.setattr(app.engine, "REVIEW_MODE", True)
    app.engine.review_reset()


def test_play_starts_the_zone(app):
    build(app)
    z = app.jriver.zone("Speakers")
    assert z.state == 2 and len(z.playlist) > 5


def test_review_collects_and_leaves_a_stopped_zone_alone(app, monkeypatch):
    review_on(app, monkeypatch)
    r = build(app)
    z = app.jriver.zone("Speakers")
    assert z.state == 0 and not z.playlist, r.text()
    assert len(app.engine.REVIEW_KEYS) > 5, r.text()
    assert len(set(app.engine.REVIEW_KEYS)) == len(app.engine.REVIEW_KEYS), "no repeats"
    assert app.engine.REVIEW_ZONE is not None
    assert r.has("ready in Review, nothing played"), r.text()
    assert not r.has("Fast start"), "no fast start in Review"


def test_review_leaves_a_playing_zone_untouched(app, monkeypatch):
    keys = [row["Key"] for row in app.jriver.by_key.values()][:2]
    app.jriver.play("Speakers", keys)
    review_on(app, monkeypatch)
    r = build(app)
    z = app.jriver.zone("Speakers")
    assert z.state == 2, r.text()
    assert [str(k) for k in z.playlist] == [str(k) for k in keys], "Playing Now unchanged"
    assert app.engine.REVIEW_KEYS, r.text()


def test_review_skips_run_after_building(app, monkeypatch):
    monkeypatch.setattr(app.engine, "RUN_AFTER", {g: (True, "C:/not-there.bat")
                                                 for g in ("artists", "tracks", "top", "vibe")})
    review_on(app, monkeypatch)
    r = build(app)
    assert not r.has("Run After Building"), r.text()
    monkeypatch.setattr(app.engine, "REVIEW_MODE", False)
    r = build(app)
    assert r.has("Run After Building"), "a normal build still runs it"


def test_voice_ignores_review(app, monkeypatch):
    review_on(app, monkeypatch)
    monkeypatch.setattr(app.engine, "VOICE_TAKEOVER", True)
    build(app)
    assert app.jriver.zone("Speakers").state == 2
    assert not app.engine.REVIEW_KEYS


def test_library_reads_bpm():
    import library
    assert "BPM" in library.FIELDS.split(",")
