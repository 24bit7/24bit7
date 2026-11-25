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


def test_the_stack_row_as_drawn_and_enter_on_empty_boxes_does_nothing(app, ui, monkeypatch):
    """
    Ben, 25 Nov 2026, as drawn: Enter in the Artist or Track box with both empty raised "Type an artist first.",
    which looked like an error, and now does nothing. # Tracks is a box like Artist and Track taking 1 to 20 (a
    letter isn't taken, 0 or 21 goes back to the last good number); the order is # Tracks, Select From Hits, Go;
    STACK SETTINGS in the accent green sits above them, showing and going with them, and nothing else moves.
    """
    import library
    import stack
    from tkinter import messagebox
    from tabs import PALETTE
    library.load()
    p = ui.play
    p._end_greeting()
    p.seed_nb.select(p.search_tab)
    ui.pump(0.4)
    asked = []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: asked.append(a))
    builds = []
    monkeypatch.setattr(p, "on_similar", lambda: builds.append(1))
    for box in (p.search_artist, p.search_track):
        box.entry.focus_force()
        ui.pump(0.1)
        box.entry.event_generate("<Return>")
        ui.pump(0.1)
    assert asked == [] and builds == [], "empty boxes: Enter does nothing"
    p.search_artist.insert(0, "Seether")
    p.search_artist.entry.focus_force()
    ui.pump(0.1)
    p.search_artist.entry.event_generate("<Return>")
    ui.pump(0.1)
    assert builds == [1], "something typed: Enter builds as before"
    p.search_artist.delete(0, "end")
    before = (p.search_artist.winfo_rooty(), p.search_track.winfo_rootx())
    name = library.artist_list()[0]
    p._stack_toggle(name)
    ui.pump(0.4)
    assert (p.search_artist.winfo_rooty(), p.search_track.winfo_rootx()) == before, "nothing moves"
    assert p.stack_heading.winfo_ismapped() and p.stack_heading.cget("text") == "STACK SETTINGS"
    assert p.stack_heading.cget("fg") == PALETTE["go"]
    box, most, go = p.stack_count_box, p.stack_most_tick, p.stack_go
    assert box.winfo_rootx() < most.winfo_rootx() < go.winfo_rootx(), "# Tracks, Select From Hits, then Go"
    assert p.stack_heading.winfo_rooty() + p.stack_heading.winfo_height() <= box.winfo_rooty() + 2, "above them"
    assert abs(p.stack_heading.winfo_rootx() - p.stack_row.winfo_rootx()) <= 2, "over the boxes, from their left"
    labels = [w.cget("text") for w in p.stack_row.winfo_children() if w.winfo_class() == "Label"]
    assert "# Tracks" in labels and "each" not in labels
    entry = box.entry
    entry.delete(0, "end")
    entry.insert(0, "x")
    assert box.get() == "", "letters aren't taken"
    for typed, kept in (("12", "12"), ("0", "12"), ("21", "12"), ("", "12"), ("20", "20"), ("1", "1")):
        entry.delete(0, "end")
        entry.insert(0, typed)
        p._stack_count_done()
        assert p.stack_count.get() == kept, (typed, p.stack_count.get())
    assert stack.choices()["count"] == 1, "remembered"
    p._stack_toggle(name)
    ui.pump(0.3)
    assert not p.stack_row.winfo_ismapped() and not p.stack_heading.winfo_ismapped(), "the heading goes too"
    assert not ui.errors, ui.errors[0]
