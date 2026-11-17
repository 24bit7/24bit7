"""
Restore JRiver, Settings > Other (17 Nov 2026, Ben): Off, Start If Closed (the default) or Start If Closed, Restart
If Hung. Off says JRiver isn't running and leaves it, since a JRiver that keeps going may be a sign of something
else. Restart If Hung waits ten seconds in case JRiver is only busy, closes it gently, by force if it won't go, and
starts its Media Server; never one started less than two minutes ago, never twice in ten minutes. No real JRiver
is closed or started here: the processes are stood in for.
"""

import time

import pytest

from test_voice import alexa  # noqa: F401  (the fixture)

EXE = r"C:\Program Files\J River\Media Center 36\Media Center 36.exe"


@pytest.fixture
def stuck(app, monkeypatch):
    """JRiver on this PC, running an hour, not answering; Restore JRiver on Restart If Hung."""
    e = app.engine
    app.set_env(JRIVER_RESTORE="restart")
    st = {"pids": [4242], "killed": [], "launched": [], "gentle_works": True, "age": 3600.0}
    monkeypatch.setattr(e, "JRIVER_HUNG_AFTER", 0.3)
    monkeypatch.setattr(e, "JRIVER_CLOSE_WAIT", 0.3)
    monkeypatch.setattr(e, "jriver_is_local", lambda: True)
    monkeypatch.setattr(e, "jriver_pids", lambda: list(st["pids"]))
    monkeypatch.setattr(e, "jriver_running", lambda: bool(st["pids"]))
    monkeypatch.setattr(e, "jriver_age", lambda: st["age"] if st["pids"] else None)
    monkeypatch.setattr(e, "jriver_exe", lambda: EXE)

    def kill(pids, force):
        st["killed"].append(("force" if force else "gentle", list(pids)))
        if force or st["gentle_works"]:
            st["pids"] = []

    def launch(exe):
        st["launched"].append(exe)
        st["pids"] = [5151]
        st["age"] = 0.0
        app.jriver.up = True

    monkeypatch.setattr(e, "_kill", kill)
    monkeypatch.setattr(e, "_launch_jriver", launch)
    app.jriver.up = False
    return st


def wait_for(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_restart_if_hung_restarts_a_stuck_jriver_and_runs_the_request(app, alexa, stuck):
    r = alexa.say("SongsByIntent", "the beatles")
    assert "If it's still stuck in ten seconds I'll restart it, uno momento." in r.ssml, r
    assert wait_for(lambda: alexa.jobs), "the request runs once JRiver is back"
    assert stuck["killed"] == [("gentle", [4242])] and stuck["launched"] == [EXE]
    assert app.printed.has("JRiver had stopped answering, so 24bit7 closed it and started it again.")


def test_a_jriver_that_wont_close_is_closed_by_force(app, alexa, stuck):
    stuck["gentle_works"] = False
    alexa.say("SongsByIntent", "the beatles")
    assert wait_for(lambda: alexa.jobs)
    assert [k for k, _ in stuck["killed"]] == ["gentle", "force"]
    assert app.printed.has("closed it by force and started it again.")


def test_a_jriver_that_was_only_busy_is_left_to_answer(app, alexa, stuck):
    alexa.say("SongsByIntent", "the beatles")
    app.jriver.up = True   # answers within the ten seconds
    assert wait_for(lambda: alexa.jobs)
    assert not stuck["killed"] and not stuck["launched"]


def test_a_jriver_started_moments_ago_is_never_closed(app, alexa, stuck):
    stuck["age"] = 30.0   # may still be loading
    assert "running but not answering" in alexa.say("SongsByIntent", "the beatles").ssml
    time.sleep(0.5)
    assert not stuck["killed"] and not alexa.jobs


def test_never_twice_in_ten_minutes(app, alexa, stuck):
    alexa.say("SongsByIntent", "the beatles")
    assert wait_for(lambda: alexa.jobs)
    app.jriver.up = False            # stuck again a minute later
    stuck["age"] = 3600.0
    assert "running but not answering" in alexa.say("SongsByIntent", "the beatles").ssml
    assert len(stuck["killed"]) == 1


def test_two_requests_while_stuck_restart_it_once(app, alexa, stuck):
    for _ in range(2):
        assert "uno momento" in alexa.say("SongsByIntent", "the beatles").ssml
    assert wait_for(lambda: len(alexa.jobs) == 2), alexa.jobs
    assert len(stuck["killed"]) == 1 and len(stuck["launched"]) == 1


def test_a_build_says_so_and_restarts_it(app, stuck):
    assert app.engine.ensure_jriver()
    assert app.printed.has("If it's still stuck in ten seconds, 24bit7 will restart it.")
    assert stuck["launched"] == [EXE]


def test_start_if_closed_leaves_a_stuck_jriver_and_says_how_to_fix_it(app, stuck):
    app.set_env(JRIVER_RESTORE="start")
    assert not app.engine.ensure_jriver()
    assert not stuck["killed"]
    assert app.printed.has("JRiver is running but not answering, so it may be stuck.")


def test_off_never_starts_jriver_and_says_it_isnt_running(app, alexa, stuck):
    app.set_env(JRIVER_RESTORE="off")
    stuck["pids"] = []   # closed
    assert "JRiver isn't running on the media PC." in alexa.say("SongsByIntent", "the beatles").ssml
    assert not app.engine.ensure_jriver()
    assert not stuck["launched"]
    assert app.printed.has("JRiver isn't running. Start it, or set Settings > Other > Restore JRiver")


def test_off_leaves_a_stuck_jriver_too(app, alexa, stuck):
    app.set_env(JRIVER_RESTORE="off")
    assert "running but not answering" in alexa.say("SongsByIntent", "the beatles").ssml
    assert not stuck["killed"]


@pytest.mark.parametrize("value, read", [("off", "off"), ("start", "start"), ("restart", "restart"),
                                         ("Restart", "restart"), ("", "start"), ("sometimes", "start")])
def test_the_setting_is_read_with_start_if_closed_as_the_default(app, value, read):
    app.set_env(JRIVER_RESTORE=value)
    assert app.engine.JRIVER_RESTORE == read


def test_jriver_processes_are_found_by_id(app):
    out = ('"System Idle Process","0","Services","0","8 K"\n"Media Center 36.exe","17660","Console","1","47,368 K"\n'
           '"MC36.exe","2210","Console","1","12,004 K"\n"JRService.exe","14640","Services","0","9,120 K"\n')
    assert app.engine.jriver_pids_in(out) == [17660, 2210]
