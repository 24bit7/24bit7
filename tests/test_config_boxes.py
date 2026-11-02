"""
Each config is a box (Ben, 2 Nov 2026): a bordered frame with its header, Sources across in one row,
Must agree on its own row, Playlist Selection, and Filters at the end, each config's own.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk, labels


def test_each_config_is_a_bordered_box_with_sources_across_and_its_own_filters(app, ui):
    import buttons
    import filters
    from tabs import PALETTE
    f = filters.blank("Stereo")
    filters.save(filters.load() + [f])
    pick_button(ui, "Artist + Guests")
    s = ui.settings
    ui.pump(0.3)
    assert sorted(s._button_filter_rows) == [0, 1], "a Filters strip per config"
    blocks = [row for row in s._button_filter_rows.values()]
    for row in blocks:
        box = row
        while box is not None and not (isinstance(box, tk.Frame) and str(box.cget("highlightbackground")) == PALETTE["button_fg"]
                                       and int(box.cget("highlightthickness")) >= 1):
            box = box.master
        assert box is not None, "the Filters strip sits inside the config's bordered box"
    ticks = [w for w in walk(s._button_filter_rows[1]) if isinstance(w, ttk.Checkbutton)]
    assert [t_.cget("text") for t_ in ticks] == ["Stereo"]
    ticks[0].invoke()
    ui.pump(0.3)
    guests = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    assert [c["filters"] for c in buttons.configs(guests)] == [[], [f["id"]]], "ticked on the second config only"
    assert filters.used_by(f["id"]) == ["Artist + Guests (config 2)"]
    # the sources read across: every tick of the first config's Sources on one line
    pick_button(ui, "Similar Artists")
    page = ui.settings._button_inner
    NAMES = ("Last.fm", "Deezer", "YouTube", "Tidal")
    def name(w):   # "Tidal  (no key yet)" in the fake world, which has no Tidal key
        return str(w.cget("text")).split("  ")[0]
    ticks = [w for w in walk(page) if isinstance(w, ttk.Checkbutton) and name(w) in NAMES]
    strips = {}   # each tick sits in its own line frame, and the lines of one strip are packed side by side in one frame
    for t_ in ticks:
        strips.setdefault(t_.master.master, set()).add(name(t_))
    top = min(strips, key=lambda f: f.winfo_rooty())   # the Sources strip; Drift's Custom Sources repeat the names lower down
    assert strips[top] == {"Last.fm", "Deezer", "YouTube", "Tidal"}, "one row"
    assert all(line.pack_info()["side"] == "left" for line in top.winfo_children()), "the lines read across"
    texts = labels(page)
    assert "Must agree" in texts and "Playlist Selection" in texts
    assert not ui.errors, ui.errors[0]
