"""
The Moderator runs on Anthropic again, on Haiku 5.5 (12 Nov 2026). From October it had failed on every build:
anthropic 1.x has no temperature setting, so asking for temperature 0 was an error before anything was sent, and
the Log's column still read "Balanced, 0 removed". Now Anthropic is never sent a temperature, the fake client
refuses what the real package refuses, a check that never came back says "didn't run" (older entries too), and a
safety refusal says the Moderator didn't run instead of passing for "nothing clashed".
"""

import pytest

TRACKS = [("a", "Artist A", "Song A"), ("b", "Artist B", "Song B"), ("c", "Artist C", "Song C")]


@pytest.fixture
def german(app):
    import i18n
    i18n.set_language("de")
    yield i18n
    i18n.set_language("en")


def test_the_fake_refuses_what_the_real_package_refuses(app):
    import anthropic
    client = anthropic.Anthropic(api_key="x")
    with pytest.raises(TypeError, match="temperature"):
        client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": "hi"}], temperature=0)


def test_the_moderator_runs_on_haiku_5_5_with_no_temperature(app):
    e = app.engine
    app.ai.remove = [2]
    r = app.Lines()
    e.MODERATOR_RUN.update(level=None, removed=0, ran=0, failed=0)
    assert e.moderate(TRACKS, "Seed - Song", report=r, level="strict") == {"b"}, r.text()
    model, _, kw = app.ai.calls[-1]
    assert model == "claude-haiku-5-5" and "temperature" not in kw
    assert not r.has("Problem") and not r.has("fixed temperature"), r.text()
    assert e.moderator_column() == "Strict, 1 removed"


def test_a_build_with_the_moderator_on_moderates(app):
    app.set_env(AI_MODERATOR_TRACKS="balanced", SIMILAR_TRACK_COUNT="15")
    app.ai.remove = [2, 3]
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(
        report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Here Comes The Sun"))
    assert not r.has("Problem: Moderator"), r.text()
    assert r.has("Moderator: 2 removed"), r.text()
    assert app.engine.LAST_BUILD["moderator"] == "Balanced, 2 removed"


def test_a_check_that_never_came_back_says_didnt_run(app):
    app.set_env(AI_MODERATOR_TRACKS="strict")
    app.ai.fail = RuntimeError("the line went dead")
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(
        report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Here Comes The Sun"))
    assert r.has("Problem: Moderator didn't run"), r.text()
    assert app.engine.LAST_BUILD["moderator"] == "Strict, didn't run"


def test_one_round_failing_and_another_running_counts_what_ran(app):
    e = app.engine
    e.MODERATOR_RUN.update(level=None, removed=0, ran=0, failed=0)
    app.ai.fail = RuntimeError("the line went dead")
    e.moderate(TRACKS, "Seed - Song", report=app.Lines(), level="strict")
    assert e.moderator_column() == "Strict, didn't run"
    app.ai.fail = None
    app.ai.remove = []
    e.moderate(TRACKS, "Seed - Song", report=app.Lines(), level="strict")
    assert e.moderator_column() == "Strict, 0 removed"


def test_a_refusal_is_not_nothing_clashed(app):
    e = app.engine
    e.MODERATOR_RUN.update(level=None, removed=0, ran=0, failed=0)
    app.ai.script = [("", "refusal")]
    r = app.Lines()
    assert e.moderate(TRACKS, "Seed - Song", report=r, level="strict") == set()
    assert r.has("Problem: Moderator didn't run, as the AI declined to check these tracks."), r.text()
    assert e.moderator_column() == "Strict, didn't run"


def test_older_log_entries_that_never_ran_read_didnt_run(app, german):
    import buildlog
    con = app.engine.db()
    buildlog.recent()   # makes the table
    failed = ("18:13  Similar Artists: Black Stone Cherry - Lonely Train\n"
              "  Moderator (Balanced): checking 71 tracks against the seed...\n"
              "  Problem: Moderator didn't run, as the check didn't come back (Messages.create() got an unexpected "
              "keyword argument 'temperature').\nDone: 30 tracks queued in Sonos, 178 not in library, 78 s.\n")
    ran = ("19:00  Similar Artists: Live - Lightning Crashes\n"
           "  Moderator (Balanced): checking 40 tracks against the seed...\n"
           "Done: 30 tracks queued in Sonos, 12 not in library, 40 s.\n")
    for at, text in (("2026-11-11 18:15:14", failed), ("2026-11-11 19:00:00", ran)):
        buildlog._insert(con, dict(at=at, tab="Main Window", from_label="Main Window", zone="Sonos", zone_id="1",
                                   kind="Artist Matching", sources="Last.fm", queued=30, misses=0,
                                   moderator="Balanced, 0 removed", problems=0, notes=0, chain_id=None,
                                   chain_pos=None, text=text))
    con.commit()
    rows = {r["at"]: r["moderator"] for r in buildlog.recent()}
    assert rows["2026-11-11 18:15:14"] == "Balanced, didn't run"
    assert rows["2026-11-11 19:00:00"] == "Balanced, 0 removed", "a check that came back with nothing stays"
    assert buildlog.moderator_shown("Balanced, didn't run") == "Ausgewogen, lief nicht"


def test_haiku_5_5_is_priced_and_named(app):
    import ai_usage
    assert ai_usage.price_for("claude-haiku-5-5") == (0.10, 0.50)
    assert ai_usage.price_for("claude-haiku-4-5-20251001") == (1.00, 5.00), "older usage keeps its price"
    assert ai_usage.MODEL_NAMES["claude-haiku-5-5"] == "Haiku 5.5"
    assert ai_usage.QUERY_MODEL == app.engine.MODERATOR_MODEL == "claude-haiku-5-5"
