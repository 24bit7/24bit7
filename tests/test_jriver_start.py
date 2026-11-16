"""
JRiver had crashed (16 Nov 2026), and the kitchen's "happy go lucky" was told the Sonos zone couldn't be found in
JRiver. Now a request that finds JRiver gone says so, and if JRiver is on this PC 24bit7 starts it: Alexa says
"uno momento" at once and the request runs by itself once JRiver answers. A JRiver elsewhere, or running but
hung, is never started. No real JRiver is started here: the launch is stood in for.
"""

import time

import pytest

from test_voice import KITCHEN, alexa  # noqa: F401  (the fixture)


@pytest.fixture
def local(app, monkeypatch):
    """JRiver on this PC, crashed: not answering and no process. The stand-in launch brings the fake one up."""
    e = app.engine
    launched = []
    monkeypatch.setattr(e, "jriver_is_local", lambda: True)
    monkeypatch.setattr(e, "jriver_running", lambda: False)
    monkeypatch.setattr(e, "jriver_exe", lambda: r"C:\Program Files\J River\Media Center 36\Media Center 36.exe")

    def launch(exe):
        launched.append(exe)
        if bring_up[0]:
            app.jriver.up = True
    bring_up = [True]
    monkeypatch.setattr(e, "_launch_jriver", launch)
    app.jriver.up = False
    return launched, bring_up


def wait_for(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_jriver_down_is_said_as_that_not_a_missing_zone(app, alexa):
    """The guard: with JRiver gone (and not on this PC to start) the reply blamed the zone."""
    app.jriver.up = False
    r = alexa.say("SongsByIntent", "the beatles")
    assert "couldn't reach JRiver" in r.ssml and "zone" not in r.ssml, r
    assert not alexa.jobs


def test_a_missing_zone_is_still_said_while_jriver_answers(app, alexa):
    app.voice.update_device(KITCHEN, zone="Garage")
    assert "can't find the Garage zone" in alexa.say("SongsByIntent", "the beatles").ssml


def test_voice_starts_jriver_and_runs_the_request_once_it_answers(app, alexa, local):
    launched, _ = local
    r = alexa.say("SongsByIntent", "the beatles")
    assert "JRiver wasn't running, so I've started it, uno momento." in r.ssml and not r.started, r
    assert launched == [r"C:\Program Files\J River\Media Center 36\Media Center 36.exe"]
    assert wait_for(lambda: alexa.jobs), "the request should run by itself once JRiver answers"
    assert "Songs by" in alexa.jobs[0][1] or "the beatles" in alexa.jobs[0][1].lower(), alexa.jobs[0][1]
    assert app.printed.has("JRiver wasn't running, so 24bit7 started it.")


def test_two_requests_while_it_starts_start_it_once(app, alexa, local):
    launched, bring_up = local
    bring_up[0] = False   # still starting when the second request comes
    for _ in range(2):
        assert "uno momento" in alexa.say("SongsByIntent", "the beatles").ssml
    assert len(launched) == 1
    app.jriver.up = True
    assert wait_for(lambda: len(alexa.jobs) == 2), alexa.jobs


def test_a_jriver_that_never_answers_is_said_in_the_console(app, alexa, local, monkeypatch):
    _, bring_up = local
    bring_up[0] = False
    monkeypatch.setattr(app.engine, "JRIVER_START_WAIT", 0.3)
    assert "uno momento" in alexa.say("SongsByIntent", "the beatles").ssml
    assert wait_for(lambda: app.printed.has("didn't answer within a minute of starting")), app.printed.text()
    assert not alexa.jobs


def test_jriver_on_another_pc_is_never_started(app, alexa, monkeypatch):
    launched = []
    monkeypatch.setattr(app.engine, "_launch_jriver", launched.append)
    app.jriver.up = False   # the fake JRiver's host is fake-jriver:52199, not this PC
    assert "couldn't reach JRiver" in alexa.say("SongsByIntent", "the beatles").ssml
    assert not launched


def test_a_hung_jriver_is_left_alone(app, alexa, local, monkeypatch):
    launched, _ = local
    monkeypatch.setattr(app.engine, "jriver_running", lambda: True)   # running, not answering
    assert "couldn't reach JRiver" in alexa.say("SongsByIntent", "the beatles").ssml
    assert not launched


def test_stop_and_pause_dont_start_jriver(app, local):
    launched, _ = local
    for intent in ("stop", "pause"):
        status, speech, _ = app.voice.respond({"intent": intent, "device": KITCHEN})
        assert "uno momento" not in speech
    assert not launched


def test_a_build_from_the_window_starts_jriver_and_waits(app, local):
    launched, _ = local
    assert app.engine.ensure_jriver()
    assert len(launched) == 1 and app.jriver.up
    assert app.printed.has("JRiver wasn't running, so 24bit7 started it.")
    assert app.engine.ensure_jriver() and len(launched) == 1, "answering now: nothing more to start"


@pytest.mark.parametrize("host, is_local", [("127.0.0.1:52199", True), ("localhost:52199", True), ("[::1]:52199", True),
                                            ("LOCALHOST", True), ("192.168.0.133:52199", False),
                                            ("media-pc:52199", False)])
def test_only_this_pc_counts_as_local(app, host, is_local):
    app.engine.JRIVER_HOST = host
    assert app.engine.jriver_is_local() is is_local
