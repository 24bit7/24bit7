"""
The console clears what isn't a build (Ben, 13 Nov 2026): a line written while no build runs (Stop, Skip, a Multiroom
note, a start-up note, a Problem) goes ninety seconds after it appeared; a build's lines stay. The clock runs only while
the window shows and the mouse isn't over the console. Opens the real window.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)


def text(ui):
    return ui.play.log.get("1.0", "end-1c")


def settled(ui):
    ui.pump(until=lambda: not ui.play._greeting_active, timeout=20)


def test_a_line_outside_a_build_goes_and_a_builds_line_stays(app, ui, monkeypatch):
    monkeypatch.setattr(ui.gui, "CONSOLE_CLEAR_AFTER", 2)
    play = ui.play
    settled(ui)
    play._mouse_on_log = False   # the window may open under the pointer, which counts as reading the console
    play.running = True
    play._append_log("Done: 30 tracks queued in Speakers.")   # a build's line
    play.running = False
    play.report("Stopped Speakers.")
    play.report("Problem: JRiver didn't answer (timed out).")
    ui.pump(0.5)
    assert "Stopped Speakers." in text(ui) and "Problem: JRiver" in text(ui)
    ui.pump(until=lambda: "Stopped Speakers." not in text(ui), timeout=6)
    assert "Stopped Speakers." not in text(ui) and "Problem: JRiver" not in text(ui), text(ui)
    assert "Done: 30 tracks queued in Speakers." in text(ui), "a build's line stays"
    assert "Stopped Speakers." not in play._live, "and it's gone from the lines kept for the tabs"
    assert not ui.errors, ui.errors[0]


def test_nothing_goes_while_the_mouse_is_over_the_console(app, ui, monkeypatch):
    monkeypatch.setattr(ui.gui, "CONSOLE_CLEAR_AFTER", 2)
    play = ui.play
    settled(ui)
    play._mouse_on_log = True
    play.report("Skipped to the next track in Speakers.")
    ui.pump(4)
    assert "Skipped to the next track" in text(ui), "it went while being read"
    play._mouse_on_log = False
    ui.pump(until=lambda: "Skipped to the next track" not in text(ui), timeout=6)
    assert "Skipped to the next track" not in text(ui)
    assert not ui.errors, ui.errors[0]
