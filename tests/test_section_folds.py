"""
The page's sections are open when their thing is on and closed when it's off, with no fold of the user's
own (Ben, 2 Nov 2026): a closed section opens when its header is clicked so it can be switched on; left off,
it's closed again next time. Sources and Playlist Selection are always on, so always open.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk


def section_boxes(page):
    """{title: the section's box} for every section on the page that folds."""
    out = {}
    for w in walk(page):
        if isinstance(w, tk.Frame) and hasattr(w, "is_open") and w.master.winfo_children():
            head = w.master.winfo_children()[0]
            titles = [c.cget("text") for c in head.winfo_children() if isinstance(c, tk.Label) and c.cget("text") not in ("▾", "▸")]
            if titles:
                out[titles[0]] = w
    return out


def test_sections_open_when_on_and_closed_when_off(app, ui):
    import buttons
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], DRIFT_ARTISTS="0", DEEP_CUTS_ARTISTS="spaced", NONSTOP_ARTISTS="0",
                                             INNER_CIRCLE_ARTISTS="0", AI_MODERATOR_ARTISTS="balanced", SKIP_LONG_CLOSERS_ARTISTS="1",
                                             IF_ALL_ELSE_FAILS_ARTISTS="0", RUN_AFTER_ARTISTS="0"))
    pick_button(ui, "Similar Artists")
    s = ui.settings
    s._button_fill_page()   # built afresh from the settings just saved (the page is kept when the pick doesn't change)
    ui.pump(0.4)
    boxes = section_boxes(s._button_inner)
    state = {title: box.is_open() for title, box in boxes.items()}
    assert state["Drift"] is False and state["Non-stop"] is False and state["Consensus"] is False
    assert state["If All Else Fails"] is False and state["Run After Building"] is False and state["Shortcut"] is False
    assert state["Deep Cuts"] is True and state["Moderator"] is True and state["Hidden Tracks"] is True
    assert "Sources" not in boxes and "Playlist Selection" not in boxes, "always on: no fold"
    assert not boxes["Drift"].winfo_manager(), "a closed section shows only its header"
    # click a closed header: it opens so the thing can be switched on
    head = boxes["Drift"].master.winfo_children()[0]
    head.event_generate("<Button-1>")
    ui.pump(0.2)
    assert boxes["Drift"].is_open() and boxes["Drift"].winfo_manager()
    # switched off, a section closes after the save; switched on, it stays open
    p = s._button_page
    p.vars["DEEP_CUTS_ARTISTS"].set("Off")
    p.save()
    ui.pump(0.3)
    assert boxes["Deep Cuts"].is_open() is False
    p.vars["NONSTOP_ARTISTS"].set(True)
    p.save()
    ui.pump(0.3)
    assert boxes["Non-stop"].is_open() is True
    buttons.set_shortcut(artists["id"], "Ctrl+Alt+5")
    s._buttons_changed()
    ui.pump(0.2)
    assert boxes["Shortcut"].is_open() is True, "a shortcut set opens the section"
    assert not ui.errors, ui.errors[0]
