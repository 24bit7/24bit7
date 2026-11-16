"""
The main window's side of starting JRiver when it has stopped (16 Nov 2026): a build starts it and waits before
it runs, and a button that needs something playing says JRiver has just been started. Opens real windows.
"""

import pytest

from test_gui import ui  # noqa: F401  (the fixture)


@pytest.fixture
def crashed(app, monkeypatch):
    e = app.engine
    launched = []
    monkeypatch.setattr(e, "jriver_is_local", lambda: True)
    monkeypatch.setattr(e, "jriver_running", lambda: False)
    monkeypatch.setattr(e, "jriver_exe", lambda: r"C:\Program Files\J River\Media Center 36\Media Center 36.exe")
    monkeypatch.setattr(e, "_launch_jriver", lambda exe: launched.append(exe) or setattr(app.jriver, "up", True))
    return launched


def test_a_build_starts_jriver_before_it_runs(app, ui, crashed):
    app.jriver.up = False
    seen = []
    ui.play._run_job(lambda: seen.append(app.jriver.up), needs_playing=False, mix=False)
    ui.wait_idle()
    assert crashed and seen == [True], "the build ran once JRiver answered"
    assert "JRiver wasn't running, so 24bit7 started it." in ui.play.log.get("1.0", "end")


def test_nothing_playing_says_jriver_was_started(app, ui, crashed):
    app.jriver.up = False
    ui.play.last_playing = None
    ui.answers.clear()
    ui.play._run_job(lambda: None, needs_playing=True, mix=False)
    ui.pump(0.2)
    assert crashed
    assert any("JRiver wasn't running, so 24bit7 started it. Start a track" in str(a) for a in ui.answers), ui.answers
