"""
Search tab: Similar Artists with only the Artist field filled in.
"""


def test_similar_artists_runs_from_artist_alone(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", ""))
    assert r.has("Done:"), r.text()
    assert len(app.jriver.zone("Speakers").playlist) > 0, r.text()


def test_artist_only_title_has_no_trailing_dash(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", ""))
    first = next(line for line in r if line.strip())
    assert first.strip() == "Similar Artists: The Beatles", first


def test_artist_and_track_title_unchanged(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r,
                                       seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    first = next(line for line in r if line.strip())
    assert first.strip() == "Similar Artists: The Beatles - Something", first


def test_youtube_only_still_needs_a_track(app):
    app.set_env(SIMILAR_SOURCES="youtube")
    assert app.engine.similar_needs_track()
    app.set_env(SIMILAR_SOURCES="lastfm,youtube")
    assert not app.engine.similar_needs_track()
