"""
A source that keeps failing says so at start-up (12 Nov 2026): every "Problem: X didn't answer" line notes X
against its build, and when the same source had trouble in each of the last three builds that ask the sources,
the console's first lines say so once. No setting: it says nothing while the sources answer.
"""


def test_a_source_that_didnt_answer_is_noted_against_the_build(app):
    e = app.engine
    sid = e.session_start("similar", {"Artist": "A", "Name": "B"})
    e.no_answer("Deezer", "  Problem: Deezer didn't answer for similar artists (timed out).")
    e.session_finish(sid, 0, report=app.Lines())
    assert e.db().execute("SELECT no_answer FROM sessions WHERE id=?", (sid,)).fetchone()[0] == "Deezer"
    sid = e.session_start("similar", {"Artist": "A", "Name": "B"})
    e.session_finish(sid, 0, report=app.Lines())
    assert e.db().execute("SELECT no_answer FROM sessions WHERE id=?", (sid,)).fetchone()[0] == "", "one build's trouble"


def three(app, troubles, mode="similar"):
    e = app.engine
    for names in troubles:
        sid = e.session_start(mode, {"Artist": "A", "Name": "B"})
        for n in names:
            e.no_answer(n, f"  Problem: {n} didn't answer for similar artists (x).")
        e.session_finish(sid, 0, report=app.Lines())


def test_three_in_a_row_says_so_at_start_up(app):
    three(app, [("Deezer", "Tidal"), ("Deezer",), ("Deezer", "Tidal")])
    r = app.Lines()
    app.engine.say_failing_sources(r)
    assert r.has("Problem: Deezer had trouble answering in each of your last three builds."), r.text()
    assert not r.has("Tidal"), "Tidal answered in one of them"


def test_one_good_build_breaks_the_run(app):
    three(app, [("Deezer",), ("Deezer",), ()])
    r = app.Lines()
    app.engine.say_failing_sources(r)
    assert r.text().strip() == ""


def test_builds_that_dont_ask_the_sources_dont_count(app):
    three(app, [("Deezer",), ("Deezer",), ("Deezer",)])
    three(app, [()], mode="vibe")
    three(app, [()], mode="jriver_playlist")
    r = app.Lines()
    app.engine.say_failing_sources(r)
    assert r.has("Deezer had trouble"), r.text()


def test_too_few_builds_and_older_ones_say_nothing(app):
    e = app.engine
    three(app, [("Deezer",), ("Deezer",)])
    assert e.failing_sources() == []
    e.db().execute("INSERT INTO sessions (started_at, mode, sources, queued) VALUES ('2026-11-01 10:00', 'similar', '', 0)")
    e.db().commit()
    assert e.failing_sources() == [], "a build from before 1.35.0 kept no record"


def test_a_real_build_with_a_source_down(app):
    """The engine's own source calls note it: a build with Last.fm down records Last.fm."""
    app.set_env(SIMILAR_SOURCES="lastfm,deezer")
    app.web.down = {"lastfm"}
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Here Comes The Sun"))
    row = app.engine.db().execute("SELECT no_answer FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    assert "Last.fm" in (row[0] or ""), r.text()


def test_german(app):
    three(app, [("Deezer",)] * 3)
    import i18n
    i18n.set_language("de")
    try:
        r = app.Lines()
        app.engine.say_failing_sources(r)
        assert r.has("Problem: Deezer hatte bei jeder deiner letzten drei Playlists Mühe zu antworten."), r.text()
    finally:
        i18n.set_language("en")
