"""
Rounded corners by corner tiles (Ben, 2 Nov 2026): Tk can't curve a frame, so tabs.corner_tiles lays four
small images over the corners of a one-pixel edge. The tile is page colour outside the arc, the edge colour
along it and the inside colour within; its far row and column carry the straight edge on. The tiles sit at
the corners, follow the widget, and go when it goes. Every Settings section, config box and number box has them.
"""

import tkinter as tk

import pytest

import tabs


@pytest.fixture
def root():
    r = tk.Tk()
    r.withdraw()
    tabs.apply_theme(r, "dark")
    yield r
    r.destroy()


def pixel(tile, x, y):
    return tile.image.pil.getpixel((x, y))


def test_tiles_sit_on_the_corners_and_carry_the_edge(root):
    frame = tk.Frame(root, bg="#1f2023", highlightthickness=1, highlightbackground="#7bd88f", width=200, height=100)
    frame.pack()
    tiles = tabs.corner_tiles(frame, radius=8, top="#000000", outside="#1f2023")
    root.update_idletasks()
    assert len(tiles) == 4 and frame.corner_tiles == tiles
    anchors = [(tl.place_info()["relx"], tl.place_info()["rely"], tl.place_info()["anchor"]) for tl in tiles]
    assert anchors == [("0", "0", "nw"), ("1", "0", "ne"), ("0", "1", "sw"), ("1", "1", "se")]
    assert all(str(tl.place_info()["in"]) == str(frame) for tl in tiles)
    nw = tiles[0]
    r = nw.image.width() - 1
    assert pixel(nw, 0, 0) == (31, 32, 35), "the corner pixel is the page colour: the square corner is gone"
    assert pixel(nw, r, 0) == (123, 216, 143), "the top row's far pixel carries the edge on"
    assert pixel(nw, 0, r) == (123, 216, 143), "so does the left column's"
    assert pixel(nw, r, r) == (0, 0, 0), "inside a top corner is the header's colour"
    sw = tiles[2]
    assert pixel(sw, r, 0) == (31, 32, 35), "inside a bottom corner is the body's colour"
    assert pixel(sw, 0, 0) == (123, 216, 143) and pixel(sw, 0, r) == (31, 32, 35)
    # the arc: the pixel on the diagonal is edge-coloured, not page or inside
    on_arc = pixel(nw, int(r - r * 0.7071), int(r - r * 0.7071))
    assert on_arc != (31, 32, 35) and on_arc != (0, 0, 0)
    frame.destroy()
    root.update_idletasks()
    assert not any(tl.winfo_exists() for tl in tiles), "the tiles go with the widget"


def test_round_fields_finds_every_number_box_once(root):
    holder = tk.Frame(root)
    holder.pack()
    inner = tk.Frame(holder)
    inner.pack()
    boxes = [tk.Spinbox(inner, from_=0, to=9, width=3) for _ in range(3)]
    for b in boxes:
        b.pack(side="left")
    tabs.round_fields(holder)
    tabs.round_fields(holder)
    assert all(len(b.corner_tiles) == 4 for b in boxes)
    assert len([w for w in inner.winfo_children() if isinstance(w, tk.Label)]) == 12, "done once, not twice"
    assert boxes[0].corner_tiles[0].image.width() >= 3, "a number box's radius is small"
