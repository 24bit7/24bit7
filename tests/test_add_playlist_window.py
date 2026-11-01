"""
The Add a Playlist window (1 Nov 2026): three tabs, From Existing, From Template and New, in place of a
form. From Existing lists every playlist: one that's off the Play tab, Add ticks back; one on it, Create
Copy copies (Name 2, right after it). From Template lists the four kinds as shipped, Headliner and Inner
Circle; New (a blank slate) has a sentence and Create. Enter and a double-click answer like Add. The
lists sit on the field colour and draw the pick as a rounded outline in the accent colour, not a filled row.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)


def open_window(ui):
    import settings_gui
    win = settings_gui.AddPlaylistPrompt(ui.settings)
    ui.pump(0.5)
    return win


def test_from_existing_lists_every_playlist_and_adds_back_or_copies(app, ui):
    import buttons
    from tabs import PALETTE
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    buttons.set_shown(head["id"], False)
    win = open_window(ui)
    assert win._tab == "existing"
    assert win.existing_list.get(0, "end") == ("Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Headliner",
                                                "Inner Circle", "AI Playlist"), "every playlist, on the row or not"
    assert win.existing_note.cget("text").startswith("Similar Artists: Artist Matching")
    assert "Create Copy makes Similar Artists 2 right after it" in win.existing_note.cget("text")
    assert win.ok_button.cget("text") == "Create Copy"
    rows = win.existing_list._rows
    assert rows[0].chosen and not rows[1].chosen, "the pick is a rounded outline in the accent colour"
    assert rows[0].find_all() and rows[0].type(rows[0].find_all()[0]) == "image", "drawn as a rounded shape, not a box"
    assert rows[0]._shape is not None and rows[0].itemcget(rows[0]._shape_id, "image") == str(rows[0]._shape)
    assert win.existing_list.cget("bg") == PALETTE["field_bg"] != win._colours[0], "the list stands apart from the window"
    win.existing_list.pick(3)
    ui.pump(0.2)
    assert win.existing_note.cget("text").startswith("Headliner: Artist's Top Tracks + Artist Matching")
    assert "Off the Play tab; Add puts it back" in win.existing_note.cget("text")
    assert win.ok_button.cget("text") == "Add"
    assert rows[3].chosen and not rows[0].chosen
    win.ok()
    assert win.result == ("existing", head["id"])
    win = open_window(ui)
    win.existing_list.pick(1)
    win.ok()
    assert win.result == ("copy", buttons.standard("tracks")["id"])
    assert not ui.errors, ui.errors[0]


def test_from_template_and_new(app, ui):
    win = open_window(ui)
    win._pick_tab("template")
    ui.pump(0.2)
    assert win.template_list.get(0, "end") == ("Artist Matching", "Track Matching", "Artist's Top Tracks", "AI Playlist",
                                               "Headliner", "Inner Circle")
    assert win.ok_button.cget("text") == "Add"
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


def test_keys_move_the_pick_and_the_tabs_switch(app, ui):
    win = open_window(ui)
    win._pick_tab("template")
    ui.pump(0.2)
    win.template_list.step(1)
    win.template_list.step(1)
    assert win.template_list.curselection() == (2,) and win.template_note.cget("text"), "Down moves the pick and the note follows"
    win._pick_tab("existing")
    ui.pump(0.2)
    assert win._pages["existing"].winfo_manager() and not win._pages["template"].winfo_manager()
    win.cancel()
    assert not ui.errors, ui.errors[0]


def test_tab_walks_the_tabs_and_the_arrows_work_without_a_click(app, ui):
    import buttons
    win = open_window(ui)
    assert win._tab == "existing"
    win.focus_force()   # the keyboard is on the window, not in a list
    ui.pump(0.2)
    win.event_generate("<Down>")
    win.event_generate("<Down>")
    ui.pump(0.2)
    assert win.existing_list.curselection() == (2,), "Down moved the pick with no click into the list"
    assert win.existing_note.cget("text").startswith("Artist's Top Tracks:")
    win.event_generate("<Tab>")
    ui.pump(0.2)
    assert win._tab == "template" and win.focus_get() is not None
    win.event_generate("<Tab>")
    ui.pump(0.2)
    assert win._tab == "new" and win.ok_button.cget("text") == "Create"
    win.event_generate("<Tab>")
    ui.pump(0.2)
    assert win._tab == "existing", "round it goes"
    win.event_generate("<Shift-Tab>")
    ui.pump(0.2)
    assert win._tab == "new", "and back"
    win._pick_tab("template")
    win.event_generate("<Up>")
    win.event_generate("<Down>")
    win.event_generate("<Down>")
    win.event_generate("<Return>")
    ui.pump(0.3)
    assert win.result == ("template", "top"), "Enter adds the pick the arrows made"
    assert not ui.errors, ui.errors[0]
