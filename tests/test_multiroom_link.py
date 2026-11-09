"""
Multiroom, stage two (9 Nov 2026): the follower as 24bit7's child. The child's protocol (multiroom.service), the
app's end (multiroom.link) with a stand-in child on a thread, and the engine's Output "Multiroom": a build goes to
the leader zone and the Speakers are asked to follow. Nothing here opens a window or touches the network beyond
127.0.0.1.
"""

import json
import os
import socket
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import follower, link, service
finally:
    sys.path.remove(REPO)


# --- a stand-in for follower.build --------------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.started = self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeFollower:
    """Says one line when it starts, then waits to be stopped; or falls over, if asked to."""

    def __init__(self, say, die=False):
        self.say, self.die = say, die
        self.nudges = []

    def nudge(self, ms):
        self.nudges.append(ms)
        self.say(f"Start is now {90 + sum(self.nudges):.0f} ms.")

    def leave_at_track_end(self):
        self.say("The Speakers finish this track, then stop following.")
        self.left.set()

    def rejoin(self):
        self.say("rejoined")

    def run(self, stop=None):
        import threading
        self.left = threading.Event()
        if self.die:
            raise RuntimeError("the DAC went away")
        self.say("The Sound Of Silence: 48 kHz, 24-bit.")
        while not stop.is_set() and not self.left.is_set():
            stop.wait(0.05)
        self.say("stopped")


def make_build(die=False, fail=None, calls=None):
    def build(leader, follower_zone, server, sonos_name, device, start, resume, dac, env, say, source=None):
        if calls is not None:
            calls.append({"leader": leader, "follower": follower_zone, "server": server, "start": start,
                          "dac": dac, "env": env, "source": source})
        if fail:
            raise follower.SetupError(fail)
        return FakeClock(), FakeFollower(say, die), f"Speakers following {leader} (Kitchen, ASIO Chord 1.04)"
    return build


def until(test, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if test():
            return True
        time.sleep(0.02)
    return False


# --- the child's protocol ------------------------------------------------------------------------------

class AppEnd:
    """The app's side of a socketpair, talking JSON lines to a Service on a thread."""

    def __init__(self, build):
        self.mine, theirs = socket.socketpair()
        self.svc = service.Service(theirs, build=build)
        self.thread = threading.Thread(target=self.svc.run, daemon=True)
        self.thread.start()
        self.reader = self.mine.makefile("r", encoding="utf-8")
        self.got = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for raw in self.reader:
            self.got.append(json.loads(raw))

    def send(self, **cmd):
        self.mine.sendall((json.dumps(cmd) + "\n").encode("utf-8"))

    def lines(self):
        return [m["line"] for m in self.got if "line" in m]

    def states(self):
        return [m["state"] for m in self.got if "state" in m]

    def problems(self):
        return [m["problem"] for m in self.got if "problem" in m]


def test_the_child_follows_on_start_and_stops_on_stop():
    calls = []
    a = AppEnd(make_build(calls=calls))
    a.send(cmd="start", leader="Sonos", follower="Speakers", server="Multiroom", start=90, resume=95, dac=1660,
           env=r"C:\x\.env")
    assert until(lambda: "The Sound Of Silence: 48 kHz, 24-bit." in a.lines())
    assert a.states() == ["following"] and a.lines()[0].startswith("Speakers following Sonos")
    assert calls == [{"leader": "Sonos", "follower": "Speakers", "server": "Multiroom", "start": 90.0, "dac": 1660,
                      "env": r"C:\x\.env", "source": None}]
    a.send(cmd="stop")
    assert until(lambda: a.states() == ["following", "idle"])
    assert "stopped" in a.lines()
    a.send(cmd="quit")
    a.thread.join(5)
    assert not a.thread.is_alive()


def test_a_setup_problem_reaches_the_app_as_a_problem_line():
    a = AppEnd(make_build(fail="No DLNA server called Multiroom: is it on in JRiver's Media Network settings?"))
    a.send(cmd="start")
    assert until(lambda: a.states() == ["idle"])
    assert a.problems() == ["No DLNA server called Multiroom: is it on in JRiver's Media Network settings?"]


def test_the_child_exits_when_the_app_goes():
    a = AppEnd(make_build())
    a.send(cmd="start")
    assert until(lambda: a.states() == ["following"])
    a.mine.shutdown(socket.SHUT_RDWR)   # the app died (the reader holds a copy of the handle, so shut it down)
    a.mine.close()
    a.thread.join(5)
    assert not a.thread.is_alive(), "the child outlived the app"


# --- the app's end -----------------------------------------------------------------------------------

def thread_spawn(build):
    """A spawn(port) that runs a Service on a thread instead of a process."""
    def spawn(port):
        conn = socket.create_connection(("127.0.0.1", port), timeout=5)
        conn.settimeout(None)
        t = threading.Thread(target=service.Service(conn, build=build).run, daemon=True)
        t.start()
        return None
    return spawn


SETTINGS = {"leader": "Sonos", "follower": "Speakers", "server": "Multiroom", "sonos": "", "device": "",
            "start": 90.0, "resume": 95.0, "dac": 1660, "env": ".env"}


def test_the_link_starts_the_child_and_shows_its_lines_with_the_prefix():
    lines = []
    lk = link.Link(say=lines.append, spawn=thread_spawn(make_build()))
    lk.start(SETTINGS)
    assert until(lambda: "Multiroom: The Sound Of Silence: 48 kHz, 24-bit." in lines)
    assert lines[0] == "Multiroom: Speakers following Sonos (Kitchen, ASIO Chord 1.04)"
    assert lk.state == "following" and lk.running()
    lk.stop()
    assert not lk.running() and lk.state == "off"


def test_a_nudge_reaches_the_running_follower():
    lines = []
    lk = link.Link(say=lines.append, spawn=thread_spawn(make_build()))
    lk.nudge(5)   # nothing running: nothing happens
    lk.start(SETTINGS)
    assert until(lambda: lk.state == "following")
    lk.nudge(5)
    assert until(lambda: "Multiroom: Start is now 95 ms." in lines)
    lk.stop()


def test_leave_lets_the_follower_finish_and_keeps_the_child_for_later():
    lines = []
    lk = link.Link(say=lines.append, spawn=thread_spawn(make_build()))
    lk.start(SETTINGS)
    assert until(lambda: lk.state == "following")
    lk.leave()
    assert until(lambda: lk.state == "idle")
    assert "Multiroom: The Speakers finish this track, then stop following." in lines
    assert not lk.wanted and lk.running(), "the child stays connected for a later start"
    lk.start(SETTINGS)   # Output back on Multiroom: the same child follows again
    assert until(lambda: lk.state == "following")
    assert lines.count("Multiroom: Speakers following Sonos (Kitchen, ASIO Chord 1.04)") == 2
    lk.stop()


def test_a_calibration_follows_with_clicks_and_changes_the_dacs_rate():
    # stage three: the child follows the leader with the 3.5 kHz click pattern in place of the server's tracks,
    # and calibrate_rate reopens the DAC at another rate mid-track
    from multiroom import calibrate
    lines, calls = [], []
    lk = link.Link(say=lines.append, spawn=thread_spawn(make_build(calls=calls)))
    lk.calibrate(SETTINGS, 44100)
    assert until(lambda: lk.state == "following")
    assert isinstance(calls[-1]["source"], calibrate.ClickSource) and calls[-1]["source"].rate == 44100
    lk.calibrate_rate(192000)
    assert until(lambda: "Multiroom: rejoined" in lines)
    assert calls[-1]["source"].rate == 192000
    lk.stop()


def test_a_problem_from_the_child_is_a_problem_line():
    lines = []
    lk = link.Link(say=lines.append, spawn=thread_spawn(make_build(fail="No Sonos found on the network.")))
    lk.start(SETTINGS)
    assert until(lambda: any("Problem" in line for line in lines))
    assert lines == ["Multiroom: Problem: No Sonos found on the network."]
    lk.stop()


def test_a_child_that_dies_is_started_once_more_then_given_up():
    lines = []
    deaths = []

    def build(*args, say=None, **kw):
        deaths.append(1)
        return FakeClock(), FakeFollower(say, die=True), "Speakers following Sonos"

    # a follower that falls over makes the child report the problem and go idle; the link treats a closed
    # connection as the child dying, so close it from the child's side after the problem
    def spawn(port):
        conn = socket.create_connection(("127.0.0.1", port), timeout=5)
        conn.settimeout(None)
        svc = service.Service(conn, build=build)
        orig = svc._follow

        def follow_then_die(cmd):
            orig(cmd)
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
        svc._follow = follow_then_die
        threading.Thread(target=svc.run, daemon=True).start()
        return None

    lk = link.Link(say=lines.append, spawn=spawn)
    lk.start(SETTINGS)
    assert until(lambda: any("stopped again" in line for line in lines), timeout=8)
    assert len(deaths) == 2, "the child wasn't started exactly once more"
    assert "Multiroom: the follower stopped on its own; starting it again." in lines
    assert not lk.wanted and lk.state == "off"


# --- the engine: Output on Multiroom ---------------------------------------------------------------------

def test_output_multiroom_sends_to_the_leader_and_asks_the_speakers_to_follow(app):
    e = app.engine
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Sonos", MULTIROOM_FOLLOWER="Speakers",
                OUTPUT_TARGET="multiroom")
    assert e.OUTPUT_TARGET == "multiroom" and e.MULTIROOM_ENABLED
    assert e.output_streaming() is None
    assert e.output_zone() == app.jriver.zone("Sonos").id
    asked = []
    e.MULTIROOM_HOOK = lambda: asked.append(1)
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    r = app.Lines()
    e.create_similar_playlist(report=r)
    assert j.zone("Sonos").playlist, r.text()
    assert asked == [1], "the Speakers weren't asked to follow"
    assert e.multiroom_settings()["leader"] == "Sonos" and e.multiroom_settings()["dac"] == 1660
    assert e.multiroom_settings()["env"] == e.ENV_FILE


def test_output_multiroom_falls_back_to_same_zone_while_multiroom_is_off(app):
    e = app.engine
    app.set_env(MULTIROOM_ENABLED="0", OUTPUT_TARGET="multiroom")
    assert e.OUTPUT_TARGET == "jriver"
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Sonos", MULTIROOM_FOLLOWER="", OUTPUT_TARGET="multiroom")
    assert e.OUTPUT_TARGET == "jriver", "no follower zone, so Multiroom can't be on"


def test_a_build_to_another_zone_doesnt_start_the_speakers(app):
    e = app.engine
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Sonos", MULTIROOM_FOLLOWER="Speakers",
                OUTPUT_TARGET="zone:Kitchen")
    asked = []
    e.MULTIROOM_HOOK = lambda: asked.append(1)
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    e.create_similar_playlist(report=app.Lines())
    assert j.zone("Kitchen").playlist and asked == []


def test_the_follower_builds_from_the_settings_dict_the_engine_gives(app):
    # the keys the engine sends are the ones service.Service hands to follower.build
    s = app.engine.multiroom_settings()
    assert set(s) == {"leader", "follower", "server", "sonos", "device", "start", "resume", "dac", "env"}
