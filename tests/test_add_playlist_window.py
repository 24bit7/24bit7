"""
The Add a Playlist window (1 Nov 2026): three tabs, From Existing, From Template and New, in place of a
form. From Existing lists what's off the Play tab; From Template the four kinds as shipped, Headliner and
Inner Circle; New has a sentence and Create. Enter and a double-click answer like Add.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


def open_window(ui):
    import settings_gui
    win = settings_gui.AddPlaylistPrompt(ui.settings)
    ui.pump(0.5)
    return win


def test_from_existing_when_something_is_off_the_row(app, ui):
    import buttons
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    buttons.set_shown(head["id"], False)
    win = open_window(ui)
    assert win._tab == "existing" and win.existing_list.get(0, "end") == ("Headliner",)
    assert win.existing_note.cget("text").startswith("Headliner: Artist's Top Tracks + Artist Matching")
    assert win.ok_button.cget("text") == "Add"
    win.ok()
    assert win.result == ("existing", head["id"])


def test_from_template_and_new(app, ui):
    win = open_window(ui)
    assert win._tab == "template", "nothing off the row: it opens on the templates"
    assert win.existing_list is None
    assert win.template_list.get(0, "end") == ("Artist Matching", "Track Matching", "Artist's Top Tracks", "AI Playlist",
                                               "Headliner", "Inner Circle")
    win.template_list.selection_clear(0, "end")
    win.template_list.selection_set(5)
    win.template_list.event_generate("<<ListboxSelect>>")
    ui.pump(0.2)
    assert win.template_note.cget("text").startswith("The seed's three closest artists")
    win._pick_tab("new")
    ui.pump(0.2)
    assert win.ok_button.cget("text") == "Create"
    win.ok()
    assert win.result == ("new", None)
    win = open_window(ui)
    win.cancel()
    assert win.result is None
    assert not ui.errors, ui.errors[0]
