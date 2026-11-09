"""
Settings > Other > Multiroom (stage two, 9 Nov 2026): the section from the design page, minus the pause tick.
Off by default; ticked, the Play tab's Output list gains Multiroom; the speaker, DAC and DLNA server are found
(stand-ins here, nothing on the network); the numbers come from the profiles until typed over; Check Clock shows
its verdict. Opens the real window.
"""

from types import SimpleNamespace

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import labels, page_named, walk


class FakeLink:
    def __init__(self):
        self.started, self.stopped, self.nudges, self.wanted = [], 0, [], False

    def start(self, settings):
        self.started.append(dict(settings))
        self.wanted = True

    def stop(self):
        self.stopped += 1
        self.wanted = False

    def leave(self):   # Output moved away: the Speakers finish the track, then stop
        self.stopped += 1
        self.wanted = False

    def running(self):
        return self.wanted

    def nudge(self, ms):
        self.nudges.append(ms)


def quiet_network(monkeypatch):
    """Nothing on the network: a Sonos One in the Kitchen, a Multiroom server and the Hugo are 'found' at once."""
    from multiroom import sonos, fetch, mcws, output, clockcheck
    monkeypatch.setattr(sonos, "find", lambda name=None, **k: [
        {"ip": "10.0.0.5", "name": "Kitchen", "model": "Sonos One", "householdId": "h", "groupId": "g"}])
    monkeypatch.setattr(fetch, "find_server", lambda name, **k: "http://10.0.0.1:52101")
    monkeypatch.setattr(mcws.JRiver, "device", lambda self, zone: ("Hugo (Chord Async USB 44.1kHz-384kHz)", "ASIO"))
    monkeypatch.setattr(output, "find_device", lambda hint, found=None, prefer="ASIO": 18)
    monkeypatch.setattr(output, "_sd", lambda: SimpleNamespace(query_devices=lambda i: {"name": "ASIO Chord  1.04"}))
    monkeypatch.setattr(clockcheck, "measure", lambda *a, **k: clockcheck.Verdict(
        "green", "Clock: millisecond position, 4 ms round trip, steady. Good.", 900, True, 4.0, 1.0,
        "ms_good", {"rtt": "4"}))


def buttons(widget):
    return [str(w.cget("text")) for w in walk(widget) if isinstance(w, tk.Button)]


def test_the_section_is_off_by_default_and_enabling_it_adds_multiroom_to_output(app, ui, monkeypatch):
    quiet_network(monkeypatch)
    ui.play.multiroom = FakeLink()
    s = ui.settings
    page_named(ui, "Other")
    texts = labels(s._mr_box)
    for text in ("Enable Multiroom", "Leader", "Speaker", "Follower", "Plays through", "DLNA server", "Adjustments",
                 "Start", "Resume", "DAC delay", "Nudge"):
        assert text in texts, text
    assert "Pausing one room pauses both" not in texts, "the tick went with the evening's pause rule"
    assert {"Check Clock", "Calibrate...", "-5 ms", "+5 ms"} <= set(buttons(s._mr_box))
    assert not s.vars["MULTIROOM_ENABLED"].get() and "Multiroom is off." in s._mr_speaker.cget("text")
    assert str(s._mr_check.cget("state")) == "disabled" and "Multiroom" not in ui.play._extra_outputs()

    s.vars["MULTIROOM_ENABLED"].set(True)
    s.vars["MULTIROOM_LEADER"].set("Sonos")
    s.vars["MULTIROOM_FOLLOWER"].set("Speakers")
    s._multiroom_changed()
    ui.pump(until=lambda: "Sonos One" in s._mr_speaker.cget("text"), timeout=10)
    env = (app.folder / ".env").read_text()
    assert "MULTIROOM_ENABLED=1" in env and "MULTIROOM_LEADER=Sonos" in env and "MULTIROOM_FOLLOWER=Speakers" in env
    assert ui.play._extra_outputs()[0] == "Multiroom"
    assert s._mr_speaker.cget("text") == "Kitchen · Sonos One  ·  profile: Sonos One"
    assert s._mr_device.cget("text") == "ASIO Chord  1.04  ·  profile: Chord Hugo"
    assert not s._mr_device_entry.winfo_ismapped(), "the device box shows only when nothing matched"
    assert s._mr_server.cget("text") == "Found at http://10.0.0.1:52101."
    assert (s.vars["MULTIROOM_START"].get(), s.vars["MULTIROOM_RESUME"].get(), s.vars["MULTIROOM_DAC"].get()) == ("90", "95", "1660")
    assert s._mr_from.cget("text") == "From the Sonos One and Chord Hugo profiles."
    assert str(s._mr_check.cget("state")) == "normal"

    s._multiroom_check_clock()
    ui.pump(until=lambda: s._mr_clock.cget("text").startswith("Clock:"), timeout=10)
    assert s._mr_clock.cget("text") == "Clock: millisecond position, 4 ms round trip, steady. Good."
    assert not ui.errors, ui.errors[0]


def test_typing_a_number_or_nudging_marks_it_typed_and_a_nudge_reaches_the_follower(app, ui, monkeypatch):
    quiet_network(monkeypatch)
    link = ui.play.multiroom = FakeLink()
    s = ui.settings
    page_named(ui, "Other")
    s.vars["MULTIROOM_ENABLED"].set(True)
    s.vars["MULTIROOM_LEADER"].set("Sonos")
    s.vars["MULTIROOM_FOLLOWER"].set("Speakers")
    s._multiroom_changed()
    ui.pump(until=lambda: "Sonos One" in s._mr_speaker.cget("text"), timeout=10)
    s.vars["MULTIROOM_START"].set("100")
    ui.pump(0.3)
    assert s._mr_from.cget("text") == "Typed by hand."
    assert "MULTIROOM_START=100" in (app.folder / ".env").read_text() and "MULTIROOM_FROM=typed" in (app.folder / ".env").read_text()
    link.wanted = True
    s._multiroom_nudge(5)
    ui.pump(0.3)
    assert s.vars["MULTIROOM_START"].get() == "105" and link.nudges == [5]
    assert "MULTIROOM_START=105" in (app.folder / ".env").read_text()
    assert not ui.errors, ui.errors[0]


def test_unticking_multiroom_puts_output_back_to_same_zone_and_stops_the_follower(app, ui, monkeypatch):
    quiet_network(monkeypatch)
    link = ui.play.multiroom = FakeLink()
    s = ui.settings
    page_named(ui, "Other")
    s.vars["MULTIROOM_ENABLED"].set(True)
    s.vars["MULTIROOM_LEADER"].set("Sonos")
    s.vars["MULTIROOM_FOLLOWER"].set("Speakers")
    s._multiroom_changed()
    ui.pump(0.3)
    ui.play.output_var.set("Multiroom")
    ui.play._on_output_changed()
    ui.pump(0.3)
    assert "OUTPUT_TARGET=multiroom" in (app.folder / ".env").read_text()
    assert link.started and link.started[-1]["leader"] == "Sonos", "picking Multiroom starts the follower"
    s.vars["MULTIROOM_ENABLED"].set(False)
    s._multiroom_changed()
    ui.pump(0.5)
    assert ui.play.output_var.get() == "Same zone"
    assert any("Multiroom" in str(a) for a in ui.answers), "the message says which section unticked it"
    assert link.stopped >= 1 and "MULTIROOM_ENABLED=0" in (app.folder / ".env").read_text()
    assert not ui.errors, ui.errors[0]
