"""
Cancel during a build: the console's strip shows Cancel on its own while a build runs,
the build stops at its next step, and the last line says what had already gone out.
"""

import threading

import pytest

from test_gui import console, ui  # noqa: F401  (the GUI fixture)


@pytest.fixture(autouse=True)
def clear_cancel(app):
    app.engine.CANCEL_REQUESTED.clear()
    yield
    app.engine.CANCEL_REQUESTED.clear()


def test_check_cancelled_raises_once_cancel_is_pressed(app):
    app.engine.check_cancelled()   # nothing pressed: carries on
    app.engine.CANCEL_REQUESTED.set()
    with pytest.raises(app.engine.BuildCancelled):
        app.engine.check_cancelled()


def test_cancel_messages(app):
    e = app.engine
    e.LAST_OUTPUT, e.SENT_ANY = None, False
    assert e.cancel_message() == "Cancelled: nothing was sent to JRiver."
    e.LAST_OUTPUT = "Speakers"
    assert "first track was already playing in Speakers" in e.cancel_message()
    e.SENT_ANY = True
    assert "already sent to Speakers stay there" in e.cancel_message()
    e.REVIEW_MODE = True
    try:
        assert "Review list was dropped" in e.cancel_message()
    finally:
        e.REVIEW_MODE = False
        e.LAST_OUTPUT, e.SENT_ANY = None, False


def test_engine_build_stops_and_sends_nothing(app):
    """Cancel pressed before anything is found: the build stops, JRiver is untouched."""
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    lines = []

    def report(line):
        lines.append(line)
        if len(lines) == 2:
            app.engine.CANCEL_REQUESTED.set()
        app.engine.check_cancelled()

    app.engine.SENT_ANY, app.engine.LAST_OUTPUT = False, None
    with pytest.raises(app.engine.BuildCancelled):
        app.engine.create_similar_playlist(report=report)
    assert j.zone("Speakers").playlist == [j.key_of("The Beatles", "Something")]
    assert not app.engine.SENT_ANY


def test_console_cancel_button(app, ui, monkeypatch):
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    gate = threading.Event()
    real = app.engine.blended_similar_artists

    def slow(*args, **kwargs):
        gate.wait(10)
        return real(*args, **kwargs)

    monkeypatch.setattr(app.engine, "blended_similar_artists", slow)
    ui.play.on_similar()
    ui.pump(until=lambda: ui.play.running, timeout=10)
    strip = ui.play.console_buttons
    assert strip["Cancel"].winfo_manager() and not strip["Copy"].winfo_manager()
    ui.play._cancel_build()
    assert strip["Cancel"].cget("text") == "Cancelling..."
    gate.set()
    ui.wait_idle()
    text = console(ui)
    assert "Cancelling..." in text and "Cancelled: nothing was sent to JRiver." in text, text
    assert "Done:" not in text, text
    assert j.zone("Speakers").playlist == [j.key_of("The Beatles", "Something")]
    assert strip["Copy"].winfo_manager() and not strip["Cancel"].winfo_manager()
    assert strip["Cancel"].cget("text") == "Cancel"
    import buildlog
    assert buildlog.recent()[0]["kind"] == "Similar Artists (Cancelled)"
    assert not ui.errors, ui.errors


def test_next_build_runs_normally_after_a_cancel(app, ui):
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    app.engine.CANCEL_REQUESTED.set()   # left over from before: a new build clears it
    ui.play.on_similar()
    ui.wait_idle()
    assert "Done:" in console(ui), console(ui)
    assert not ui.errors, ui.errors
