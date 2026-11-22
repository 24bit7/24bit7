"""
Simple on the screens (Ben, 2 Nov 2026): a page shows one config with Sources, Playlist Selection and Filters
(collapsed), none of the advanced sections, no Review Mode line; the Play tab greys Artist + Guests and
Consensus with a Needs Advanced note, and the list tags them. Advanced brings it all back.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk, shown, shown_labels


def test_simple_shows_one_plain_config_and_greys_what_needs_advanced(app, ui):
    import mode
    s = ui.settings
    mode.set_current("simple")
    pick_button(ui, "Artist + Guests")
    ui.pump(0.4)
    s._fill_button_list()
    ui.play.refresh_buttons()
    ui.pump(0.4)
    assert list(s._button_filter_rows) == [0], "the first config alone"
    # what's on screen: the sections a config builds out of sight (to keep its values whole) don't count
    texts = shown_labels(s._button_inner) + [w.cget("text") for w in shown(s._button_inner) if isinstance(w, ttk.Checkbutton)]
    for gone in ("Mix", "Drift", "Moderator", "Consensus", "Shortcut", "Non-stop", "Deep Cuts", "Hidden Tracks",
                 "If All Else Fails", "Run After Building", "+ Add Another Config", "Separate Settings for Review Mode"):
        assert gone not in texts, gone
    assert "Sources" in texts and "Playlist Selection" in texts and "Filters" in texts
    assert "Use Main Filter" in texts, "Simple shows the line as Advanced does (20 Nov 2026; folded away before)"
    by_name = {b._name: b for b in ui.play.play_buttons}
    assert str(by_name["Artist + Guests"].cget("state")) == "disabled" and str(by_name["Consensus"].cget("state")) == "disabled"
    assert str(by_name["Similar Artists"].cget("state")) == "normal"
    tags = {row.text: row.tag for _id, row, _l, _r, _v in s._button_rows}
    assert tags["Artist + Guests"] == "Needs Advanced" and tags["Consensus"] == "Needs Advanced" and tags["Similar Artists"] == ""
    pick_button(ui, "Similar Artists")
    texts = shown_labels(s._button_inner) + [w.cget("text") for w in shown(s._button_inner) if isinstance(w, ttk.Checkbutton)]
    assert "When Seed is Playing Now" in texts and "Separate Settings for Review Mode" not in texts
    assert "Consensus" not in texts and "Moderator" not in texts
    # back to Advanced: everything returns
    s._set_mode("advanced")
    ui.pump(0.5)
    texts = shown_labels(s._button_inner)
    assert "Drift" in texts and "Moderator" in texts and "Consensus" in texts and "Shortcut" in texts
    by_name = {b._name: b for b in ui.play.play_buttons}
    assert str(by_name["Artist + Guests"].cget("state")) == "normal"
    assert all(row.tag != "Needs Advanced" for _id, row, _l, _r, _v in s._button_rows)
    assert not ui.errors, ui.errors[0]
