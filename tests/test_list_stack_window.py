"""
Stacking on Playlists & Albums, on screen (Ben, 24 Nov 2026). Each row of the list has + Add in a strip at its right,
as tall as the row (Remove once stacked); the rest of the row picks it on its own, as before, which clears a stack
and says so. The box clears for the next name and the list stays open, stacked ones under a STACKED heading while
nothing's typed; leaving the box, it reads "Abbey Road · The Beatles and 1 more". Play, Embellish and Save take the
lot, and the stack clears after any of them. One console line for each add or remove.
"""

from test_gui import ui, console  # noqa: F401  (the GUI fixture)
from test_jriver_playlists_tab import headings, lists_tab, type_in

ROAD_TRIP = {"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"}


def row_for(pop, text):
    return next(row for _, row in pop._rows if text in row.text)


def click(ui, row, x):
    row.event_generate("<Enter>", x=x, y=5)
    row.event_generate("<ButtonPress-1>", x=x, y=5)
    if row.winfo_exists():   # a pick closes the list under the mouse
        row.event_generate("<ButtonRelease-1>", x=x, y=5)
    ui.pump(0.3)


def test_add_strip_stacks_the_name_picks_alone_and_play_takes_the_lot(app, ui):
    import embellish
    import library
    library.load()
    p = lists_tab(ui)
    type_in(ui, p, "abbey")
    row = row_for(p._playlists_pop, "Abbey Road")
    assert row.action == "+ Add" and row.winfo_height() == row._h, "the strip is the row's full height"
    click(ui, row, row.winfo_width() - 5)
    assert [x["Name"] for x in p._list_stack] == ["Abbey Road"]
    assert "Abbey Road by The Beatles added to the stack. Add more, or click Play, Embellish or Save." in console(ui)
    assert p.playlist_entry.get() == "" and p._playlists_pop is not None, "the box clears; the list stays open"
    pop = p._playlists_pop
    assert "STACKED" in headings(pop) and row_for(pop, "Abbey Road").action == "Remove"
    p._stack_toggle_list(ROAD_TRIP)
    ui.pump(0.3)
    assert "Road Trip added to the stack, now 2 in it." in console(ui)
    p.focus_set()
    p._close_playlists_if_away()
    assert p.playlist_entry.get() == "Abbey Road · The Beatles and 1 more"
    assert p._save_target()[0] == "box" and p.save_button.winfo_ismapped()
    assert embellish.is_stack(p._chosen_playlist())
    embellish.set_choice("order", "ordered")
    p.play_list_button._command()
    ui.wait_idle()
    keys = library.album_keys("Abbey Road", "The Beatles")
    road = next(x for x in app.jriver.playlists if x["ID"] == "202")["keys"]
    assert app.jriver.zone("Speakers").playlist == keys + [k for k in road if k not in keys], console(ui)
    assert p._list_stack == [] and p.playlist_entry.get() == "", "the stack clears with Play"
    # a stack, then a name clicked: that one alone, the stack cleared, said in the console
    p._stack_toggle_list(ROAD_TRIP)
    type_in(ui, p, "abbey")
    row = row_for(p._playlists_pop, "Abbey Road")
    click(ui, row, 20)
    assert p._list_stack == [] and p.playlist_entry.get() == "Abbey Road · The Beatles"
    assert "Abbey Road by The Beatles picked on its own, so the stack of 1 is cleared." in console(ui)
    assert not ui.errors, ui.errors[0]


def test_remove_and_save_a_stack(app, ui, monkeypatch):
    import library
    library.load()
    p = lists_tab(ui)
    p._stack_toggle_list({"kind": "album", "Name": "Abbey Road", "Artist": "The Beatles"})
    p._stack_toggle_list(ROAD_TRIP)
    p._stack_toggle_list({"kind": "album", "Name": "Abbey Road", "Artist": "The Beatles"})
    ui.pump(0.3)
    assert "Abbey Road by The Beatles taken off the stack, now 1 in it." in console(ui)
    p._stack_toggle_list({"kind": "album", "Name": "Abbey Road", "Artist": "The Beatles"})
    ui.pump(0.3)
    asked = []
    monkeypatch.setattr(ui.gui, "ask_save", lambda parent, prompt, initial, size, **k:
                        asked.append((prompt, initial, k)) or (initial, True, None))
    p.save_button._command()
    ui.pump(0.3)
    prompt, initial, kw = asked[0]
    assert initial == "Road Trip and Abbey Road" and prompt.startswith("Road Trip and Abbey Road (")
    assert prompt.endswith("without playing them.")
    assert kw == {"jriver": False, "jriver_ok": True, "copy": True}, "a stack can be saved in JRiver too"
    saved = next(x for x in app.jriver.playlists if x["Name"] == "Road Trip and Abbey Road")
    assert len(saved["keys"]) == len(set(saved["keys"])) > 7
    assert p._list_stack == [] and app.jriver.zone("Speakers").playlist == [], "saved without playing; the stack clears"
    assert not ui.errors, ui.errors[0]
