"""
tabs.flow lays a row of widgets out like words in a paragraph (2 Nov 2026): one line while there's room,
wrapping onto the next when the box they sit in is narrower than they are, and back to one line when it
widens. A Playlist Selection sentence with its number boxes, or a row of sources, then fits any window
and any language instead of running off the right edge.
"""

import tkinter as tk

import pytest

import tabs


@pytest.fixture
def root():
    r = tk.Tk()   # shown, not withdrawn: a hidden window gets no Configure events, and the wrapping follows them
    r.geometry("+60+60")
    yield r
    r.destroy()


def words_of(frame):
    return [w for w in frame.winfo_children() if not getattr(w, "corner_tile", False)]


def rows_of(frame):
    """Each word's line, counted from the top, from where it's placed."""
    ys = sorted({int(w.place_info()["y"]) for w in words_of(frame)})
    return [ys.index(int(w.place_info()["y"])) for w in words_of(frame)]


def test_words_wrap_when_the_box_is_narrow_and_unwrap_when_it_widens(root):
    box = tk.Frame(root, width=900, height=60)
    box.pack_propagate(False)
    box.pack()
    row = tk.Frame(box)
    row.pack(anchor="w")
    for word in ("Limit To", "30", "tracks, from", "20", "artists, pick", "5", "of each artist's top", "7", "tracks"):
        tk.Label(row, text=word, font=("Segoe UI", 10)).pack(side="left")
    words = row.winfo_children()
    tabs.flow(row)
    root.update_idletasks()
    root.update()
    assert set(rows_of(row)) == {0}, "room enough: one line"
    tiles = tabs.corner_tiles(words[1], radius=3)   # a number box's tiles sit in the row too, but aren't words
    xs = [int(w.place_info()["x"]) for w in words_of(row)]
    assert xs == sorted(xs) and xs[0] == 0, "left to right from the edge"
    box.configure(width=300)
    root.update_idletasks()
    root.update()
    rows = rows_of(row)
    assert rows[0] == 0 and max(rows) >= 1 and rows == sorted(rows), "wrapped onto further lines, in order"
    assert row.winfo_reqwidth() <= 300, "the frame is no wider than its room"
    second = [w for w in words_of(row) if rows_of(row)[words_of(row).index(w)] == 1]
    assert int(second[0].place_info()["x"]) == 0, "a new line starts at the edge, not under the first line's columns"
    assert all(str(tl.place_info()["in"]) == str(words[1]) for tl in tiles), "the tiles still ride on their widget"
    box.configure(width=900)
    root.update_idletasks()
    root.update()
    assert set(rows_of(row)) == {0}, "wide again: one line again"
