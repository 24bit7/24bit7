"""
Settings > Other > General > Restore JRiver (17 Nov 2026): Start If Closed by default, the line under it changes
with the choice, Restart If Hung's spells out the risk to the library, and the choice is saved. Opens real windows.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import labels, page_named


def test_restore_jriver_defaults_to_start_if_closed_and_saves_the_choice(app, ui):
    s = ui.settings
    page_named(ui, "Other")
    assert "Restore JRiver" in labels(s.restore_note.master.master)
    assert s.vars["JRIVER_RESTORE"].get() == "Start If Closed"
    assert "starts its Media Server and carries on" in s.restore_note.cget("text")

    s.vars["JRIVER_RESTORE"].set("Start If Closed, Restart If Hung")
    s._restore_changed()
    ui.pump(0.2)
    assert "could damage the library" in s.restore_note.cget("text")
    assert "JRIVER_RESTORE=restart" in (app.folder / ".env").read_text()
    app.engine.refresh_settings_if_changed()
    assert app.engine.JRIVER_RESTORE == "restart"

    s.vars["JRIVER_RESTORE"].set("Off")
    s._restore_changed()
    ui.pump(0.2)
    assert "leaves it to you" in s.restore_note.cget("text")
    assert "JRIVER_RESTORE=off" in (app.folder / ".env").read_text()
    assert not ui.errors, ui.errors[0]
