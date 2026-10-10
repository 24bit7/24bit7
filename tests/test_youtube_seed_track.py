"""YouTube seeds from a track in Playing Now and Drift artist rounds; one message when it can't."""

from test_seed_playing_now import QUIET, play_mix


def test_playing_now_gives_youtube_each_artists_track(app, monkeypatch):
    e = app.engine
    app.set_env(PN_SAMPLE_ARTISTS="3", PN_ARTISTS_PER_SAMPLE="2", SIMILAR_SOURCES="youtube,lastfm", **QUIET)
    play_mix(app)
    asked = []
    real = e.blended_similar_artists

    def record(seed, limit=20, seed_track=None, report=None):
        asked.append((seed, seed_track))
        return real(seed, limit=limit, seed_track=seed_track, report=report)
    monkeypatch.setattr(e, "blended_similar_artists", record)
    r = app.Lines()
    e.create_similar_playlist(report=r, seed_info=e.seed_or_last_played(report=r), playing_now=True)
    assert asked and all(track for _, track in asked), asked
    assert not r.has("needs a track to seed from") and not app.printed.has("needs a track to seed from")


def test_drift_artist_round_gives_youtube_the_seed_track(app, monkeypatch):
    e = app.engine
    app.set_env(DRIFT_ARTISTS="1", DRIFT_ARTISTS_USING="artists", DRIFT_ARTISTS_ROUNDS="1",
                DRIFT_ARTISTS_SOURCES_MODE="custom", DRIFT_ARTISTS_ARTIST_SOURCES="youtube",
                SIMILAR_SOURCES="ai", SKIP_PLAYED_ARTISTS="0", AI_MODERATOR_ARTISTS="off", AI_MODERATOR="off")
    drift_calls = []

    def similar(seed, limit=10, seed_track=None, **k):
        if e.SIMILAR_SOURCES == ["youtube"]:
            drift_calls.append(seed_track)
            return [("The Rolling Stones", ["YouTube"])], "YouTube"
        return [], "none"
    monkeypatch.setattr(e, "blended_similar_artists", similar)
    real_pick = e.pick_top_tracks_for_artist

    def pick(artist, *a, **k):   # the seed artist has nothing either, so Drift starts from the seed
        return ([], 0) if artist == "The Beatles" else real_pick(artist, *a, **k)
    monkeypatch.setattr(e, "pick_top_tracks_for_artist", pick)
    e.create_similar_playlist(report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", "Something"))
    assert drift_calls and drift_calls[0] == "Something", drift_calls


def test_no_track_is_one_message_not_two(app):
    e = app.engine
    app.set_env(SIMILAR_SOURCES="youtube,lastfm", SIMILAR_MIN_AGREEMENT="1")
    e.blended_similar_artists("Queen", limit=5)
    text = app.printed.text()
    assert text.count("needs a track to seed from") == 1
    assert "YouTube returned no similar artists" not in text


def test_drift_warning_wording(app):
    import settings_gui
    assert settings_gui.DRIFT_SAME_WARNING.startswith("Same sources keep Drift's picks closest to the seed.")
