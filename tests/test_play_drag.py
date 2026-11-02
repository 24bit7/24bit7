"""
Dragging a playlist along the Play tab's row (1 Nov 2026): a drag image in its own small window
follows the pointer (a widget can't show outside its parent, so the button itself never could),
the row re-flows as the pointer passes each button so the gap opens where the drop will land, and
the strip over the console holds two centred pills, Settings and Remove, with a dashed outline that
fills in under the pointer. No caption.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


class At:
    def __init__(self, x, y):
        self.x_root, self.y_root = x, y


def names(p):
    return [b._name for b in p.play_buttons]


def middle(widget):
    return widget.winfo_rootx() + widget.winfo_width() // 2, widget.winfo_rooty() + widget.winfo_height() // 2


def test_the_row_reflows_while_dragging_and_the_drop_keeps_that_order(app, ui):
    import buttons
    p = ui.play
    ui.pump(0.3)
    first, third = p.play_buttons[0], p.play_buttons[2]
    x, y = middle(first)
    p._drag_start(At(x, y), first)
    p._drag_move(At(x + 2, y), first)
    assert not p._drag_moved and getattr(p, "_drag_image", None) is None, "a few pixels is still a click"
    tx, ty = middle(third)
    p._drag_move(At(tx + 10, ty), first)   # right of Artist's Top Tracks' middle
    ui.pump(0.2)
    assert p._drag_moved and isinstance(p._drag_image, tk.Toplevel) and p._drag_image.winfo_exists()
    assert names(p)[:3] == ["Similar Tracks", "Artist's Top Tracks", "Similar Artists"], "the slot slid along the row"
    assert first._dim, "the dragged button's slot shows dimmed"
    assert p._drop_box is not None and p._drop_box.winfo_exists()
    p._drag_end(At(tx + 10, ty), first)
    ui.pump(0.3)
    assert [b["name"] for b in buttons.shown()][:3] == ["Similar Tracks", "Artist's Top Tracks", "Similar Artists"]
    assert names(p)[:3] == ["Similar Tracks", "Artist's Top Tracks", "Similar Artists"]
    assert p._drag_image is None and p._drop_box is None, "the drag image and the strip are gone"
    assert not p.play_buttons[2]._dim, "drawn as usual again"
    assert not ui.errors, ui.errors[0]


def test_the_strip_has_two_centred_dashed_pills_and_no_caption(app, ui):
    from tabs import PALETTE
    p = ui.play
    ui.pump(0.3)
    fb = p.play_buttons[1]
    x, y = middle(fb)
    p._drag_start(At(x, y), fb)
    p._drag_move(At(x + 40, y), fb)
    ui.pump(0.3)
    box = p._drop_box
    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)
    assert not [w for w in walk(box) if isinstance(w, tk.Label)], "no caption: nothing but the two pills"
    settings, remove = p._targets["settings"][1], p._targets["remove"][1]
    import tkinter.font as tkfont
    assert settings._font[1] == tkfont.nametofont("TkDefaultFont").actual("size"), "the Play buttons' text size (2 Nov 2026)"
    assert settings._ph == settings._px(48) and settings._pw == settings._px(170), "fifteen percent smaller than 56 by 200"
    assert remove._colour == PALETTE["brand_orange"]
    assert settings.lit is False and settings.itemcget(settings.find_all()[0], "dash") != "", "a dashed outline"
    inner = settings.master.master
    left_gap = inner.winfo_rootx() - box.winfo_rootx()
    right_gap = box.winfo_rootx() + box.winfo_width() - (inner.winfo_rootx() + inner.winfo_width())
    assert abs(left_gap - right_gap) <= 4, (left_gap, right_gap, "centred")
    sx, sy = middle(settings)
    p._drag_move(At(sx, sy), fb)
    ui.pump(0.2)
    assert settings.lit is True and remove.lit is False, "filled in under the pointer"
    assert names(p)[1] == "Similar Tracks", "over the strip the row stays put"
    opened = []
    p.open_playlist_settings = lambda bid, rename=False: opened.append(bid)
    p._drag_end(At(sx, sy), fb)
    ui.pump(0.3)
    assert opened == [fb._button["id"]]
    assert not ui.errors, ui.errors[0]
