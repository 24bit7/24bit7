"""
Nested playlists on the Play tab (stage two, 1 Nov 2026 evening): a parent's button is split, its
face carrying the default's name and an arrow opening a popup of its children, the default tagged.
A child in the popup builds once; right-click offers Make Default, Out to the Row and Settings.
Holding a dragged playlist over another button for a moment makes it the nest target, and the drop
nests. Removing a playlist clears the console before the note.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


class At:
    def __init__(self, x, y):
        self.x_root, self.y_root = x, y


def names(p):
    return [b._name for b in p.play_buttons]


def faces(p):
    return [b._label.cget("text") for b in p.play_buttons]


def middle(widget):
    return widget.winfo_rootx() + widget.winfo_width() // 2, widget.winfo_rooty() + widget.winfo_height() // 2


def make_parent(buttons):
    buttons.load()
    top = buttons.standard("top")
    ten = buttons.add("Top 10, Best First", "top")
    buttons.nest(ten["id"], top["id"])
    return top, ten


def test_a_parent_is_a_split_button_whose_face_runs_the_default(app, ui, monkeypatch):
    import buttons
    p = ui.play
    top, ten = make_parent(buttons)
    p.refresh_buttons()
    ui.pump(0.3)
    assert names(p) == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Headliner", "Inner Circle", "AI Playlist"]
    fb = p.play_buttons[2]
    assert fb._arrow is not None and p.play_buttons[1]._arrow is None, "only the parent has the arrow"
    assert fb._size[0] > p.play_buttons[1]._size[0], "and is wider for it"
    ran = []
    monkeypatch.setattr(p, "on_button", lambda button: ran.append(button["name"]))
    fb._command()
    assert ran == ["Artist's Top Tracks"], "the face runs the parent itself, to start"
    buttons.set_default(top["id"], ten["id"])
    p.refresh_buttons()
    ui.pump(0.3)
    fb = p.play_buttons[2]
    assert faces(p)[2] == "Top 10, Best First" and names(p)[2] == "Artist's Top Tracks", "the face carries the default's name"
    fb._command()
    assert ran[-1] == "Top 10, Best First"
    note = p._button_note(buttons.get(top["id"]))
    assert "The arrow lists 1 more playlist." in note and note.startswith(p._plain_note(buttons.get(ten["id"])))
    assert not ui.errors, ui.errors[0]


def test_the_arrow_opens_the_children_and_a_child_builds_once(app, ui, monkeypatch):
    import buttons
    p = ui.play
    top, ten = make_parent(buttons)
    deep = buttons.add("Deep Cut Top Tracks", "top")
    buttons.nest(deep["id"], top["id"])
    buttons.set_default(top["id"], ten["id"])
    p.refresh_buttons()
    ui.pump(0.3)
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.4)
    pop = p._children_popup
    assert pop is not None and pop.winfo_exists() and pop.winfo_viewable()
    rows = [(child["name"], tag.cget("text")) for child, _row, tag in pop._rows]
    assert rows == [("Top 10, Best First", "default"), ("Deep Cut Top Tracks", "")]
    fb = p.play_buttons[2]
    assert pop.winfo_rooty() >= fb.winfo_rooty() + fb.winfo_height(), "under the button"
    ran = []
    monkeypatch.setattr(p, "on_button", lambda button: ran.append(button["name"]))
    p._run_child(deep)
    ui.pump(0.2)
    assert ran == ["Deep Cut Top Tracks"] and p._children_popup is None, "built once, and the popup closed"
    p._set_default(buttons.get(top["id"]), deep["id"])
    ui.pump(0.3)
    assert faces(p)[2] == "Deep Cut Top Tracks"
    p._end_greeting(keep=False)
    p._unnest(buttons.get(ten["id"]))
    ui.pump(0.3)
    assert names(p)[3] == "Top 10, Best First", "out to the row, after its old parent"
    assert "Top 10, Best First is back on the Play tab." in p.log.get("1.0", "end")
    assert not ui.errors, ui.errors[0]


def test_holding_over_another_button_nests_on_the_drop(app, ui):
    import buttons
    p = ui.play
    buttons.load()
    ten = buttons.add("Top 10, Best First", "top")
    p.refresh_buttons()
    p._end_greeting(keep=False)
    ui.pump(0.3)
    fb = p.play_buttons[-1]
    assert fb._name == "Top 10, Best First"
    top_button = p.play_buttons[2]
    x, y = middle(fb)
    p._drag_start(At(x, y), fb)
    p._drag_move(At(x - 40, y), fb)
    tx, ty = middle(top_button)
    p._drag_move(At(tx, ty), fb)
    ui.pump(0.2)
    assert p._nest_target is None, "not yet: a pass over a button is a reorder"
    ui.pump(0.6)
    assert p._nest_target is top_button and top_button._target, "held: Artist's Top Tracks lights as the target"
    assert p._nest_tag is not None and p._nest_tag.cget("text") == "Nest under Artist's Top Tracks"
    p._drag_move(At(tx + 2, ty), fb)
    ui.pump(0.1)
    assert p._nest_target is top_button, "a wobble keeps it"
    p._drag_end(At(tx + 2, ty), fb)
    ui.pump(0.4)
    top = buttons.standard("top")
    assert [b["name"] for b in buttons.children(top["id"])] == ["Top 10, Best First"]
    assert "Top 10, Best First" not in names(p) and p.play_buttons[2]._arrow is not None
    assert "Top 10, Best First is under Artist's Top Tracks now." in p.log.get("1.0", "end")
    assert p._nest_target is None and p._nest_tag is None and not p.play_buttons[2]._target
    # a parent can't be nested: holding it over another button does nothing
    parent_fb = p.play_buttons[2]
    px_, py_ = middle(parent_fb)
    p._drag_start(At(px_, py_), parent_fb)
    p._drag_move(At(px_ - 40, py_), parent_fb)
    hx, hy = middle(p.play_buttons[3])
    p._drag_move(At(hx, hy), parent_fb)
    ui.pump(0.8)
    assert p._nest_target is None
    p._drag_end(At(hx, hy), parent_fb)
    ui.pump(0.3)
    assert not ui.errors, ui.errors[0]


def test_removing_a_playlist_clears_the_console_first(app, ui):
    p = ui.play
    p._end_greeting(keep=False)
    p._append_log("Old build output.")
    p._remove_button(p.play_buttons[3]._button)   # Headliner
    ui.pump(0.3)
    text = p.log.get("1.0", "end")
    assert "Old build output." not in text and "Headliner is off the Play tab." in text
    assert p._live == [l for l in p._live if "Headliner is off" in l], "the kept lines start again too"
    assert not ui.errors, ui.errors[0]
