"""
The Search tab's stack on screen (Ben, 23 Nov 2026): the Artist box lists your artists as you type, each with
+ Add; Go, how many each and Select From Hits appear after the Track box, in the gap before Output, once someone is
added; Go plays to Output and clears the stack.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)


def test_add_shows_go_and_go_plays_and_clears(app, ui):
    import library
    library.load()
    p = ui.play
    p._end_greeting()
    p.seed_nb.select(p.search_tab)
    ui.pump(0.4)
    assert not p.stack_row.winfo_ismapped(), "nothing stacked: no Go"
    name = next(a for a in library.artist_list() if a.lower().startswith("the b"))
    p.search_artist.entry.focus_force()
    p.search_artist.insert(0, name[:5])
    p._fill_artists()
    ui.pump(0.3)
    rows = dict(p._artists_pop._rows)
    assert name in rows and rows[name].tag == "+ Add", list(rows)
    p._stack_toggle(name)
    ui.pump(0.4)
    assert p._stack == [name] and p.search_artist.get() == ""
    assert f"{name} added to the stack. Add more, or click Go." in p.log.get("1.0", "end")
    assert p.stack_row.winfo_ismapped(), "Go shows once someone is added"
    # on the same row: after the Track box, clear of Output
    track_right = p.search_track.winfo_rootx() + p.search_track.winfo_width()
    assert p.stack_go.winfo_rootx() > track_right
    row_right = p.stack_row.winfo_rootx() + p.stack_row.winfo_width()
    assert row_right <= p.output_box.winfo_rootx(), (row_right, p.output_box.winfo_rootx())
    assert abs(p.stack_go.winfo_rooty() - p.search_track.winfo_rooty()) <= 12, "level with the boxes"
    assert p.stack_count.get() == "5" and p.stack_most.get() == "down"
    # with nothing typed, the list is what's been added, each with Remove
    p._fill_artists()
    ui.pump(0.2)
    assert [(a, r.tag) for a, r in p._artists_pop._rows] == [(name, "Remove")]
    # the box taking the keyboard back while the list is drawn doesn't start a second list mid-draw (found by the shot)
    pop = p._artists_pop
    p._artists_filling = True
    p._fill_artists()
    p._artists_filling = False
    assert p._artists_pop is pop and pop.winfo_exists()
    p.on_stack_go()
    ui.wait_idle()
    assert app.jriver.zone("Speakers").playlist, "played to Output"
    assert p._stack == [] and not p.stack_row.winfo_ismapped(), "the stack clears after Go"
    assert not ui.errors, ui.errors[0]


def test_one_line_each_with_the_count_and_remove_takes_go_away_again(app, ui):
    """Ben, 23 Nov 2026: "Seether added to the stack, now 11 artists", never every artist restated each time."""
    import library
    library.load()
    p = ui.play
    p._end_greeting()   # while the greeting types, lines wait for it
    p.seed_nb.select(p.search_tab)
    ui.pump(0.3)
    first, second = library.artist_list()[:2]
    p._stack_toggle(first)
    p._stack_toggle(second)
    ui.pump(0.3)
    log = p.log.get("1.0", "end")
    assert f"{second} added to the stack, now 2 artists." in log, log
    assert log.count(first) == 1, "the first artist isn't said again when the second is added"
    p._stack_toggle(second)
    ui.pump(0.2)
    assert f"{second} taken off the stack, now 1 artist." in p.log.get("1.0", "end")
    p._stack_toggle(first)
    ui.pump(0.3)
    assert p._stack == [] and not p.stack_row.winfo_ismapped()
    assert f"{first} taken off the stack, which is empty now." in p.log.get("1.0", "end")
    p._close_artists()
    assert not ui.errors, ui.errors[0]
