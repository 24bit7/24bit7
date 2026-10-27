"""
Most tracks per artist for the AI Playlist (27 Oct 2026): datdude asked for "industrial rock" and half the
list was NIN. The per-artist limit covered Drift's top-up but not the AI's own picks. It now covers both,
as its own row in the AI Playlist column (VIBE_PER_ARTIST, default three).
"""

import collections
import json


def _keen_on_one_artist(app):
    """Scripts the AI to answer with every track the library's biggest artist has, then two of everyone else's."""
    by_artist = collections.defaultdict(list)
    for row in app.jriver.tracks:
        by_artist[row["Artist"]].append(row["Name"])
    big = max(by_artist, key=lambda a: len(by_artist[a]))
    picks = [{"artist": big, "track": name} for name in by_artist[big]]
    for artist, names in by_artist.items():
        if artist != big:
            picks += [{"artist": artist, "track": name} for name in names[:2]]
    app.ai.script.append((json.dumps(picks), "end_turn"))
    return big, len(by_artist[big])


def _sent_by(app, artist):
    rows = [app.jriver.by_key[str(k)] for k in app.jriver.zone("Speakers").playlist]
    return sum(1 for r in rows if r["Artist"] == artist)


def test_the_ai_picks_keep_to_the_limit(app):
    app.set_env(VIBE_TRACK_COUNT="100", VIBE_PER_ARTIST="3", DRIFT_VIBE="0")   # nothing trimmed
    big, owned = _keen_on_one_artist(app)
    assert owned > 3   # the fake library must give the limit something to do
    r = app.Lines()
    app.engine.create_vibe_playlist("industrial rock", report=r)
    assert _sent_by(app, big) == 3, r.text()
    assert r.has("more left out, as"), r.text()


def test_the_limit_follows_the_setting(app):
    app.set_env(VIBE_TRACK_COUNT="100", VIBE_PER_ARTIST="1", DRIFT_VIBE="0")
    big, _ = _keen_on_one_artist(app)
    app.engine.create_vibe_playlist("industrial rock", report=app.Lines())
    assert _sent_by(app, big) == 1
