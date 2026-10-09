"""
AI Moderator and single tracks (datdude's GitHub issue): a Drift round that finds one track
used to go through unchecked and silently. Balanced and Strict now check it; Relaxed skips
it and says so; whenever the moderator is set but can't run, the console says why.
"""

import json

import pytest

DOWN_RODEO = [("k1", "Rage Against the Machine", "Down Rodeo")]
SO_FAR = [("k9", "Portishead", "Glory Box"), ("k8", "Massive Attack", "Teardrop")]


def remove_reply(app, number=1, reason="aggressive rap-metal, far from the playlist's trip-hop calm"):
    app.ai.script.append((json.dumps({"remove": [{"number": number, "artist": "Rage Against the Machine",
                                                  "title": "Down Rodeo", "reason": reason}]}), "end_turn"))


@pytest.mark.parametrize("level", ["balanced", "strict"])
def test_single_drift_track_is_checked(app, level):
    app.set_env(AI_MODERATOR_TRACKS=level)
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    remove_reply(app)
    r = app.Lines()
    removed = app.engine.moderate(DOWN_RODEO, "Portishead - Glory Box", report=r, reference=SO_FAR)
    assert removed == {"k1"}, r.text()
    assert r.has(f"AI Moderator ({level.title()}): checking 1 track against the seed and the playlist so far"), r.text()
    assert r.has("Removed Rage Against the Machine - Down Rodeo"), r.text()


def test_relaxed_skips_a_single_track_and_says_so(app):
    app.set_env(AI_MODERATOR_TRACKS="relaxed")
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    remove_reply(app)
    waiting = len(app.ai.script)
    r = app.Lines()
    assert app.engine.moderate(DOWN_RODEO, "Portishead - Glory Box", report=r, reference=SO_FAR) == set()
    assert r.has("AI Moderator (Relaxed): skipped Rage Against the Machine - Down Rodeo, as there's only 1 track"), \
        r.text()
    assert len(app.ai.script) == waiting, "the AI wasn't asked"


def test_relaxed_still_checks_two_or_more(app):
    app.set_env(AI_MODERATOR_TRACKS="relaxed")
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    remove_reply(app)
    r = app.Lines()
    app.engine.moderate(DOWN_RODEO + SO_FAR, "Portishead - Glory Box", report=r)
    assert r.has("AI Moderator (Relaxed): checking 3 tracks"), r.text()


def test_set_but_no_ai_says_why_once(app):
    app.set_env(AI_MODERATOR_TRACKS="strict", ANTHROPIC_API_KEY="")
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    app.engine.ai_off_reset()
    r = app.Lines()
    app.engine.moderate(DOWN_RODEO, "Portishead - Glory Box", report=r)
    app.engine.moderate(SO_FAR, "Portishead - Glory Box", report=r)
    lines = [l for l in r if "AI Moderator skipped: the AI isn't set up" in l]
    assert len(lines) == 1, r.text()


def test_off_by_choice_is_silent(app):
    app.set_env(AI_MODERATOR_TRACKS="off")
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    r = app.Lines()
    assert app.engine.moderate(DOWN_RODEO, "Portishead - Glory Box", report=r) == set()
    assert not [l for l in r if "Moderator" in l], r.text()


def test_drift_round_with_one_track_is_moderated(app):
    """The Drift round path itself, with the round's own level, passes a single track to the check."""
    app.set_env(AI_MODERATOR_TRACKS="balanced")
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    drift = app.engine.Drift("tracks", 30, None, app.Lines(), seed="Portishead - Glory Box")
    drift.tracks = lambda keys: [t for t in DOWN_RODEO + SO_FAR if t[0] in {str(k) for k in keys}]
    drift.base = ["k9", "k8"]
    remove_reply(app)
    keys = ["k9", "k8", "k1"]
    removed = drift.moderate(keys, ["k1"], drift_round=True)
    assert "k1" in removed and keys == ["k9", "k8"]
