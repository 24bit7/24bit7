"""
Issue #10 (28 Oct 2026): an AI Playlist found four Simon & Garfunkel tracks in the library, the user's filter
left them all out, and the console said "nothing the AI picked is in your library", with no word of the filter.
When every pick found in the library is left out, the console now says so and why.
"""

import json
import time


def _ai_picks_three_played_tracks(app):
    rows = [r for r in app.jriver.tracks if r["Genre"] == "Rock"][:3]
    for row in rows:
        app.jriver.mark_played(row["Key"], time.time() - 600)   # ten minutes ago
    app.library.load()
    picks = [{"artist": r["Artist"], "track": r["Name"]} for r in rows]
    picks.append({"artist": "Nobody You Own", "track": "Not Here"})
    app.ai.script.append((json.dumps(picks), "end_turn"))


def test_picks_left_out_are_not_called_missing(app):
    app.set_env(SKIP_PLAYED_VIBE="1", SKIP_PLAYED_VIBE_DAYS="1", DRIFT_VIBE="0")
    _ai_picks_three_played_tracks(app)
    r = app.Lines()
    app.engine.create_vibe_playlist("singer songwriter duos", report=r)
    assert not app.jriver.zone("Speakers").playlist
    assert r.has("the 3 tracks the AI picked from your library were all left out"), r.text()
    assert r.has("Skipped 3 tracks played in the last 1 day"), r.text()
    assert not r.has("nothing the AI picked is in your library"), r.text()


def test_nothing_found_still_says_so(app):
    app.set_env(DRIFT_VIBE="0")
    app.ai.script.append((json.dumps([{"artist": "Nobody You Own", "track": "Not Here"}]), "end_turn"))
    r = app.Lines()
    app.engine.create_vibe_playlist("singer songwriter duos", report=r)
    assert r.has("nothing the AI picked is in your library"), r.text()


def test_only_says_what_it_left_out(app):
    """Only's early returns gave the same reason without the count of what was skipped."""
    artist = next(r["Artist"] for r in app.jriver.tracks if r["Genre"] == "Rock")
    for row in app.jriver.tracks:
        if row["Artist"] == artist:
            app.jriver.mark_played(row["Key"], time.time() - 600)
    app.library.load()
    app.set_env(SKIP_PLAYED_VIBE="1", SKIP_PLAYED_VIBE_DAYS="1")
    r = app.Lines()
    app.engine.create_only_playlist(f"chill {artist}", report=r)
    assert r.has("was played recently or is left out"), r.text()
    assert r.has("played in the last 1 day"), r.text()
