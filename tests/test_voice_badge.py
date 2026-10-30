"""
The voice badge (29 Oct 2026, datdude on the forum): from the couch in Theater View there was no telling
whether a voice request had been heard. While a voice build runs, a badge sits on top of everything; it
must never take focus (a badge that did would leave Theater View deaf to the remote until clicked) and
clicks pass through it. It ends with how many tracks went in, or why none did, and fades.
"""

import ctypes
import json
import time
import tkinter as tk

import pytest

from test_gui import ui, KITCHEN, console   # noqa: F401 (the fixture)

user32 = ctypes.windll.user32
GWL_EXSTYLE, GW_OWNER = -20, 4


@pytest.fixture
def root(app):
    r = tk.Tk()
    r.geometry("300x200+100+100")
    entry = tk.Entry(r)
    entry.pack()
    r.update()
    r.focus_force()
    entry.focus_set()
    r.update()
    yield r
    r.destroy()


def pump(r, seconds):
    end = time.time() + seconds
    while time.time() < end:
        r.update()
        time.sleep(0.01)


def test_never_takes_focus_and_lets_clicks_through(root):
    import badge
    before = user32.GetForegroundWindow()
    b = badge.Badge(root)
    b.working("Only AC/DC", "Living Room", ai=True)
    pump(root, 0.5)
    assert b.showing() and user32.IsWindowVisible(b.hwnd)
    assert user32.GetForegroundWindow() == before, "the badge took focus"
    ex = user32.GetWindowLongW(b.hwnd, GWL_EXSTYLE)
    for bit in (badge.WS_EX_TRANSPARENT, badge.WS_EX_NOACTIVATE, badge.WS_EX_TOPMOST, badge.WS_EX_TOOLWINDOW):
        assert ex & bit, hex(bit)
    b.hide()


def test_shows_while_24bit7_is_in_the_tray(root):
    """An owned window hides with its owner, so the badge has none."""
    import badge
    root.withdraw()
    b = badge.Badge(root)
    b.working("Songs by Queen", "Kitchen")
    pump(root, 0.3)
    assert user32.GetWindow(b.hwnd, GW_OWNER) == 0
    assert user32.IsWindowVisible(b.hwnd)
    b.hide()
    pump(root, 0.1)
    assert not user32.IsWindowVisible(b.hwnd)


def test_what_each_state_says(root):
    import badge
    import tabs
    b = badge.Badge(root)
    b.working("Only AC/DC", "Living Room", ai=True)
    assert b.lines == ("Only AC/DC", "Living Room: asking the AI")
    assert b.dot == tabs.ACCENT, "the accent while the AI works too (datdude: magenta flashing distracted)"
    b.working("Songs by Queen", "Kitchen")
    assert b.lines == ("Songs by Queen", "Kitchen: finding tracks") and b.dot == tabs.ACCENT
    b.done(24, "Kitchen")
    assert b.state == "done" and b.lines == ("24 tracks added", "Kitchen")
    b.done(0, "Kitchen", "every track by Queen was played recently.")
    assert b.lines == ("Nothing added", "every track by Queen was played recently.")
    assert b.dot != tabs.DARK["ai_purple"]
    b.problem("only ACDC", "I couldn't find an artist you own in ACDC.")
    assert b.lines == ("Not played: only ACDC", "I couldn't find an artist you own in ACDC.")
    b.hide()


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def test_first_show_is_top_right_and_close_to_the_edge(root):
    """datdude (29 Oct 2026): the very first badge came up top left, and the gap to the edge was too big."""
    import badge
    b = badge.Badge(root)
    b.working("Songs by Queen", "Kitchen")
    rect = RECT()
    user32.GetWindowRect(b.hwnd, ctypes.byref(rect))
    margin = int(badge.MARGIN * b.scale)
    assert rect.right == root.winfo_screenwidth() - margin, (rect.left, rect.right)
    assert rect.top == margin
    assert badge.MARGIN <= 16
    b.hide()


def test_the_result_fades(root, monkeypatch):
    import badge
    monkeypatch.setattr(badge, "HOLD_MS", 100)
    b = badge.Badge(root)
    b.done(3, "Kitchen")
    pump(root, 0.3)
    assert b.showing()
    pump(root, 1.0)
    assert not b.showing() and not user32.IsWindowVisible(b.hwnd)


def _say(app, intent, value):
    import urllib.request
    body = json.dumps({"intent": intent, "value": value, "device": KITCHEN}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{app.engine.VOICE_PORT}/command", data=body, method="POST",
                                 headers={"X-24bit7-Key": app.engine.VOICE_KEY, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def test_a_voice_build_shows_on_the_badge(app, ui):
    shown = []
    real = ui.play.badge.working
    ui.play.badge.working = lambda *a, **k: shown.append(a) or real(*a, **k)
    assert _say(app, "music_like", "queen")["status"] == "started"
    ui.wait_idle()
    assert shown and shown[0][1] == "Kitchen", shown
    b = ui.play.badge
    assert b.state == "done" and b.lines[0].endswith("tracks added"), (b.lines, console(ui))
    b.hide()


def test_a_build_from_the_play_tab_shows_no_badge(app, ui):
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    ui.play.on_similar_tracks()
    ui.wait_idle()
    assert not ui.play.badge.showing() and ui.play.badge.state is None


def test_a_refused_request_shows_on_the_badge(app, ui):
    app.voice.attach_badge(lambda asked, said: ui.play.badge_problems.put((asked, said)))
    try:
        assert _say(app, "only", "rainy sunday jazz")["status"] == "problem"
        ui.pump(1.0)
    finally:
        app.voice.attach_badge(None)
    b = ui.play.badge
    assert b.lines == ("Not played: only rainy sunday jazz", "I couldn't find an artist you own in rainy sunday jazz.")
    b.hide()
