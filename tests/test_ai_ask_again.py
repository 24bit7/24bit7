"""The second AI request: when none of the AI's suggestions for a seed are in the library,
it's asked once more, for different ones."""

import json

from fakes import NOT_IN_LIBRARY


def test_similar_artists_asks_again_once(app):
    e = app.engine
    app.set_env(SIMILAR_SOURCES="ai", SIMILAR_MIN_AGREEMENT="1")
    owned = [a for a in app.web.lib_artists if a != "Queen"][:3]
    app.ai.script = [(json.dumps(NOT_IN_LIBRARY), "end_turn"), (json.dumps(owned), "end_turn")]
    blended, _ = e.blended_similar_artists("Queen", limit=10)
    assert [a for a, _ in blended] == [e.canonicalise_conjunction(a) for a in owned]
    assert len(app.ai.calls) == 2
    assert "None of these are in the listener's library" in app.ai.sent[1]
    assert all(n in app.ai.sent[1] for n in NOT_IN_LIBRARY)
    assert app.printed.has("None of the AI's suggestions for Queen are in your library, so asking once more.")
    e.blended_similar_artists("Queen", limit=10)   # the better answer was cached: no third request
    assert len(app.ai.calls) == 2


def test_similar_artists_no_second_request_when_one_is_owned(app):
    app.set_env(SIMILAR_SOURCES="ai", SIMILAR_MIN_AGREEMENT="1")
    owned = [a for a in app.web.lib_artists if a != "Queen"][:1]
    app.ai.script = [(json.dumps(NOT_IN_LIBRARY + owned), "end_turn")]
    app.engine.blended_similar_artists("Queen", limit=10)
    assert len(app.ai.calls) == 1


def test_never_more_than_one_second_request(app):
    app.set_env(SIMILAR_SOURCES="ai", SIMILAR_MIN_AGREEMENT="1")
    app.ai.script = [(json.dumps(NOT_IN_LIBRARY), "end_turn"), (json.dumps(["Nobody Owned"]), "end_turn")]
    app.engine.blended_similar_artists("Queen", limit=10)
    assert len(app.ai.calls) == 2


def test_youtube_output_never_asks_again(app):
    app.set_env(SIMILAR_SOURCES="ai", SIMILAR_MIN_AGREEMENT="1", OUTPUT_TARGET="youtube")
    app.ai.script = [(json.dumps(NOT_IN_LIBRARY), "end_turn")]
    app.engine.blended_similar_artists("Queen", limit=10)
    assert len(app.ai.calls) == 1


def test_similar_tracks_asks_again_once(app):
    e = app.engine
    app.set_env(SIMILAR_TRACK_SOURCES="ai", SIMILAR_TRACK_MIN_AGREEMENT="1")
    missing = [{"artist": "The Zombies", "track": "Time of the Season"}]
    owned = [{"artist": "Badfinger", "track": "Baby Blue"}]
    app.ai.script = [(json.dumps(missing), "end_turn"), (json.dumps(owned), "end_turn")]
    lines = app.Lines()
    blended, answered = e.similar_track_candidates(["Queen"], "Somebody To Love", report=lines)
    assert [p for p, _ in blended] == [("Badfinger", "Baby Blue")]
    assert lines.has("None of the AI's suggestions for Queen - Somebody To Love are in your library")
    assert "The Zombies - Time of the Season" in app.ai.sent[1]
    assert len(app.ai.calls) == 2


def test_library_has_artist_band_credit(app):
    e = app.engine
    assert e.library_has_artist("Queen")
    assert not e.library_has_artist("The Zombies")
