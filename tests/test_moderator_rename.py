"""The AI Moderator is called the Moderator from 1.20.0: older builds and usage records still read right."""


def test_log_reads_old_and_new_moderator_lines(app):
    import buildlog
    old = "  AI Moderator (Balanced): checking 34 tracks against the seed...\n  AI Moderator: 2 removed."
    new = "  Moderator (Strict): checking 20 tracks against the seed...\n  Moderator: 3 removed."
    assert buildlog._moderator(old) == "Balanced, 2 removed"
    assert buildlog._moderator(new) == "Strict, 3 removed"


def test_usage_under_the_old_name_counts_under_the_new(app):
    import ai_usage
    con = ai_usage._table()
    for feature in ("AI Moderator", "Moderator"):
        con.execute("INSERT INTO ai_usage (at, feature, model, input, cache_write, cache_read, output) "
                    "VALUES (1, ?, 'claude-haiku-4-5-20251001', 1000, 0, 0, 300)", (feature,))
    con.commit()
    by = {f: n for f, n, *_ in ai_usage.totals()["by_feature"]}
    assert "AI Moderator" not in by and by.get("Moderator") == 2


def test_console_says_moderator(app):
    e = app.engine
    app.set_env(AI_MODERATOR="balanced", AI_MODERATOR_TRACKS="balanced", MODERATOR_WARNED="1")
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=e.typed_seed_info("The Beatles", "Here Comes The Sun"))
    assert r.has("Moderator (") and not r.has("AI Moderator"), r.text()
