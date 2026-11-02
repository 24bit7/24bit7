"""
The parent's drop-down, second take (1 Nov 2026, late): the button is one shape with the bar across
it and a black line before the arrow; the drop-down lists the parent's own row first, reading as its
Alternate Title when it has one; a row under the pointer gets the rounded green outline; and a child
can be dragged out of the drop-down onto the row, into another parent or onto the Settings pill.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button


class At:
    def __init__(self, x, y):
        self.x_root, self.y_root = x, y


def names(p):
    return [b._name for b in p.play_buttons]


def middle(widget):
    return widget.winfo_rootx() + widget.winfo_width() // 2, widget.winfo_rooty() + widget.winfo_height() // 2


def make_parent(buttons):
    buttons.load()
    top = buttons.standard("top")
    ten = buttons.add("Top 10, Best First", "top")
    deep = buttons.add("Deep Cut Top Tracks", "top")
    buttons.nest(ten["id"], top["id"])
    buttons.nest(deep["id"], top["id"])
    return top, ten, deep


def test_the_split_button_is_one_shape_with_a_divider(app, ui):
    import buttons
    import tabs
    from PIL import ImageTk
    p = ui.play
    make_parent(buttons)
    p.refresh_buttons()
    ui.pump(0.3)
    fb = p.play_buttons[2]

    class Named:   # a Tk image by name, enough for ImageTk.getimage
        def __init__(self, name):
            self.tk, self._name = fb.tk, name

        def __str__(self):
            return self._name

        def width(self):
            return int(self.tk.call("image", "width", self._name))

        def height(self):
            return int(self.tk.call("image", "height", self._name))
    face = ImageTk.getimage(Named(fb._label.cget("image"))).convert("RGBA")
    arrow = ImageTk.getimage(Named(fb._arrow.cget("image"))).convert("RGBA")
    assert face.height == arrow.height and face.width + arrow.width == fb._size[0], "cut from one picture"
    bar_y = face.height - 1 - fb._px(1) - fb._px(tabs.BUTTON_BAR) // 2
    face_bar, arrow_bar = face.getpixel((face.width // 2, bar_y)), arrow.getpixel((arrow.width // 2, bar_y))
    assert face_bar[:3] == arrow_bar[:3] and face_bar[3] > 0, "the bar runs across both parts"
    divider = arrow.getpixel((0, arrow.height // 3))   # the cut falls just before the line, so it leads the arrow part
    assert divider[:3] == (0, 0, 0), f"a black line before the arrow, got {divider}"
    assert face.getpixel((face.width - 1, face.height // 3))[:3] != (0, 0, 0), "and only the one line"
    assert not ui.errors, ui.errors[0]


def test_the_drop_down_reads_the_alternate_title_and_outlines_on_hover(app, ui):
    import buttons
    p = ui.play
    top, ten, deep = make_parent(buttons)
    buttons.set_subtitle(top["id"], "Top 12, Random Order")
    p.refresh_buttons()
    ui.pump(0.3)
    assert p.play_buttons[2]._label.cget("text") == "Artist's Top Tracks", "the face keeps the name"
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.4)
    pop = p._children_popup
    rows = [(row.text, tag) for _pl, row, tag in pop._rows]
    assert rows == [("Top 12, Random Order", "default"), ("Top 10, Best First", ""), ("Deep Cut Top Tracks", "")]
    first = pop._rows[0][1]
    assert not first.chosen
    first.event_generate("<Enter>")
    ui.pump(0.2)
    assert first.chosen, "the rounded outline on hover"
    first.event_generate("<Leave>")
    ui.pump(0.2)
    assert not first.chosen
    p._close_children()
    assert not ui.errors, ui.errors[0]


def test_a_child_drags_out_of_the_drop_down_onto_the_row(app, ui):
    import buttons
    p = ui.play
    top, ten, deep = make_parent(buttons)
    p.refresh_buttons()
    p._end_greeting(keep=False)
    ui.pump(0.3)
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.4)
    pop = p._children_popup
    child_row = pop._rows[2][1]   # Deep Cut Top Tracks
    x, y = middle(child_row)
    p._pop_press(At(x, y), deep, False)
    p._pop_drag_move(At(x + 3, y))
    assert not p._pop_pressed["dragging"], "a few pixels is still a click"
    p._pop_drag_move(At(x + 60, y - 60))
    ui.pump(0.3)
    assert p._pop_pressed["dragging"] and p._drag_image is not None and p._drop_box is not None
    assert float(pop.attributes("-alpha")) == 0.0, "the drop-down is out of sight but alive"
    head = p.play_buttons[3]   # Headliner: drop in front of it
    hx, hy = head.winfo_rootx() + 4, head.winfo_rooty() + head.winfo_height() // 2
    p._pop_drag_move(At(hx, hy))
    p._pop_release(At(hx, hy), deep)
    ui.pump(0.4)
    assert names(p)[3] == "Deep Cut Top Tracks" and names(p)[4] == "Headliner", "out onto the row, where it was dropped"
    assert buttons.get(deep["id"])["parent"] == ""
    assert "Deep Cut Top Tracks is back on the Play tab." in p.log.get("1.0", "end")
    assert p._children_popup is None and p._drag_image is None and p._drop_box is None
    assert not ui.errors, ui.errors[0]


def test_a_child_drags_into_another_parent_or_onto_settings(app, ui, monkeypatch):
    import buttons
    p = ui.play
    top, ten, deep = make_parent(buttons)
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    p.refresh_buttons()
    p._end_greeting(keep=False)
    ui.pump(0.3)
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.4)
    row = p._children_popup._rows[2][1]
    x, y = middle(row)
    p._pop_press(At(x, y), deep, False)
    p._pop_drag_move(At(x + 60, y - 60))
    head_fb = p.play_buttons[3]
    hx, hy = middle(head_fb)
    p._pop_drag_move(At(hx, hy))
    ui.pump(0.8)
    assert p._nest_target is head_fb, "held over Headliner: the target"
    p._pop_release(At(hx, hy), deep)
    ui.pump(0.4)
    assert [b["name"] for b in buttons.children(head["id"])] == ["Deep Cut Top Tracks"]
    assert [b["name"] for b in buttons.children(top["id"])] == ["Top 10, Best First"]
    assert "Deep Cut Top Tracks is under Headliner now." in p.log.get("1.0", "end")
    # onto Settings
    opened = []
    monkeypatch.setattr(p, "open_playlist_settings", lambda bid, rename=False: opened.append(bid))
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.4)
    row = p._children_popup._rows[1][1]
    x, y = middle(row)
    p._pop_press(At(x, y), ten, False)
    p._pop_drag_move(At(x + 60, y + 60))
    ui.pump(0.3)
    sx, sy = middle(p._targets["settings"][1])
    p._pop_drag_move(At(sx, sy))
    p._pop_release(At(sx, sy), ten)
    ui.pump(0.3)
    assert opened == [ten["id"]] and buttons.get(ten["id"])["parent"] == top["id"], "its page opens; it stays where it was"
    assert not ui.errors, ui.errors[0]


def test_the_default_row_does_not_drag_and_a_parent_page_has_the_alternate_title_box(app, ui):
    import buttons
    p = ui.play
    top, ten, deep = make_parent(buttons)
    p.refresh_buttons()
    ui.pump(0.3)
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.3)
    row = p._children_popup._rows[0][1]
    x, y = middle(row)
    p._pop_press(At(x, y), buttons.get(top["id"]), True)
    p._pop_drag_move(At(x + 80, y + 80))
    assert not p._pop_pressed["dragging"] and getattr(p, "_drag_image", None) is None, "the default stays put"
    p._close_children()
    s = pick_button(ui, "Artist's Top Tracks")
    ui.pump(0.3)
    settings = ui.settings
    box = settings._subtitle_box
    assert box is not None and box.winfo_manager(), "a parent's page has the Alternate Title box"
    settings._subtitle_var.set("Top 12, Random Order")
    box.focus_force()   # a generated key goes to the focus widget
    ui.pump(0.2)
    box.event_generate("<Return>")
    ui.pump(0.3)
    assert buttons.get(top["id"])["subtitle"] == "Top 12, Random Order"
    pick_button(ui, "Headliner")
    ui.pump(0.3)
    assert settings._subtitle_box is None, "not on a playlist with nothing nested under it"
    assert not ui.errors, ui.errors[0]


def test_the_drop_down_is_only_as_wide_as_its_rows_need(app, ui):
    """1 Nov 2026, late: a Tk canvas asks for ten centimetres unless told, so the drop-down came out
    twice the button's width. Its rows now ask for just their text, five spaces and the tag."""
    import tkinter.font as tkfont
    import buttons
    p = ui.play
    top, ten, deep = make_parent(buttons)
    p.refresh_buttons()
    ui.pump(0.3)
    fb = p.play_buttons[2]
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.4)
    pop = p._children_popup
    widest = max(row.winfo_reqwidth() for _pl, row, _tag in pop._rows) + 8   # the rows' padx and the popup's edge
    assert pop.winfo_width() == max(fb.winfo_width(), widest), "the wider of the button and its widest row"
    assert pop.winfo_width() < 300, "not Tk's ten centimetres"
    p._close_children()
    long_title = "Artist's Top Tracks, Twelve of Them, in the Order the Sources Rank Them"
    buttons.set_subtitle(top["id"], long_title)
    p._open_children(buttons.get(top["id"]))
    ui.pump(0.4)
    pop = p._children_popup
    row = pop._rows[0][1]
    assert pop.winfo_width() > fb.winfo_width(), "a long row widens it"
    text_right = row.bbox(row._text_id)[2]
    tag_left = row.bbox(row._tag_id)[0]
    five = tkfont.Font(root=row, font=row._font).measure(" " * 5)
    assert tag_left - text_right >= five, f"at least five spaces before the tag, got {tag_left - text_right} for {five}"
    assert row.bbox(row._tag_id)[2] <= row.winfo_width(), "and the tag is in view"
    p._close_children()
    assert not ui.errors, ui.errors[0]


def test_the_playlists_list_is_only_as_wide_as_its_names_need(app, ui):
    """2 Nov 2026: the same ten centimetres in Settings > Playlists. The list took about 380 pixels for
    names that need 200, and the page beside it was clipped at the manual's window width. The rows now
    ask for their name, with a floor so a longer name has room; the page gets the rest."""
    import buttons
    s = ui.settings
    pick_button(ui, "Similar Artists")
    rows = [r for _i, r, _l, _r, _v in s._button_rows]
    widest_name = max(r.bbox(r._text_id)[2] for r in rows)
    width = rows[0].winfo_width()
    assert all(r.winfo_width() == width for r in rows), "every row the same width"
    assert widest_name < width <= max(220, widest_name + 60), f"the list is {width} for names up to {widest_name}"
    assert width < 300, "not Tk's ten centimetres"
    page_left = s._button_right.winfo_rootx()
    assert page_left - ui.root.winfo_rootx() < 360, "so the page starts well inside the left third"
    assert not ui.errors, ui.errors[0]


def test_the_search_hint_names_track_matching_not_a_similar_tracks_button(app, ui):
    """2 Nov 2026, from the screenshots: the Search tab still said only the Similar Tracks button needs
    the track. That playlist is Track Matching now, in a menu, so the hint names it and says playlists."""
    import tkinter as tk
    hints = [w.cget("text") for w in ui.play.search_tab.winfo_children() if isinstance(w, tk.Label)]
    hint = next(h for h in hints if "needs the track" in h)
    assert "Only Track Matching needs the track; the other playlists need just the artist." in hint
    assert "Similar Tracks" not in hint and "buttons" not in hint
