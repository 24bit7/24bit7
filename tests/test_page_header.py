"""
The playlist page's header (Ben, 2 Nov 2026): Name and Title in Menu as boxes, a Preview of the button
with its menu and this playlist's row outlined, the Simple / Advanced pill, and Shortcut moved down into
a section of its own.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk, labels


def test_title_in_menu_on_a_child_and_the_preview_shows_the_parents_menu(app, ui):
    import buttons
    top = buttons.standard("top")
    ten = buttons.add("Top 10, Best First", "top")
    buttons.nest(ten["id"], top["id"])
    pick_button(ui, "Top 10, Best First")
    s = ui.settings
    assert s._subtitle_box is not None and s._subtitle_var.get() == ""
    s._subtitle_var.set("Ten, Best First")
    s._subtitle_box.focus_force()
    ui.pump(0.2)
    s._subtitle_box.event_generate("<Return>")
    ui.pump(0.3)
    assert buttons.get(ten["id"])["subtitle"] == "Ten, Best First"
    assert [text for _pl, text, _d in buttons.menu_rows(buttons.get(top["id"]))] == ["Artist's Top Tracks", "Ten, Best First"]
    assert s._preview_rows == ["Artist's Top Tracks", "Ten, Best First"], "the child's preview is its parent's menu"
    texts = [s._preview.itemcget(i, "text") for i in s._preview.find_all() if s._preview.type(i) == "text"]
    assert "Artist's Top Tracks" in texts and "Ten, Best First" in texts and "default" in texts, texts
    assert "Preview:" in labels(s._preview_frame), "Preview: to the left of the picture (Ben, 3 Nov 2026)"
    pick_button(ui, "Artist's Top Tracks")
    assert s._preview_rows == ["Artist's Top Tracks", "Ten, Best First"], "the parent's preview is its own menu"
    pick_button(ui, "Similar Tracks")
    assert s._preview_rows == ["Similar Tracks", "playlist button abc", "playlist button xyz"], "a plain button: placeholders"
    assert not ui.errors, ui.errors[0]


def test_the_pill_switches_mode_and_simple_asks_when_it_turns_things_off(app, ui, monkeypatch):
    import buttons
    import mode
    from tkinter import messagebox
    pick_button(ui, "Similar Artists")
    s = ui.settings
    assert mode.current() == "advanced" and list(s._mode_labels) == ["simple", "advanced"]
    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a[1]) or False)
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], DRIFT_ARTISTS="1", DEEP_CUTS_ARTISTS="spaced"))
    s._set_mode("simple")
    ui.pump(0.2)
    assert len(asked) == 1 and asked[0].startswith("Simple turns off ") and "Drift" in asked[0] and "Deep Cuts" in asked[0]
    assert mode.current() == "advanced", "a no leaves it"
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._set_mode("simple")
    ui.pump(0.4)
    assert mode.current() == "simple"
    assert s._mode_labels["simple"].cget("bg") != s._mode_labels["advanced"].cget("bg"), "the chosen half is filled"
    s._set_mode("advanced")
    ui.pump(0.4)
    assert mode.current() == "advanced"
    assert not ui.errors, ui.errors[0]


def test_shortcut_is_a_section_below_the_configs_and_a_new_page_opens_on_the_name_box(app, ui):
    import buttons
    import settings_gui
    pick_button(ui, "Similar Artists")
    s = ui.settings
    texts = labels(s._button_right)
    assert "Shortcut" in texts
    heads = [w for w in walk(s._button_inner) if isinstance(w, tk.Label) and w.cget("text") in ("Non-stop", "Shortcut", "Hidden Tracks")
             and str(w.cget("font")) == settings_gui.HEADING_FONT]
    order = []
    for w in sorted(heads, key=lambda w: w.winfo_rooty()):   # the section headers, top to bottom, each once
        if w.cget("text") not in order:
            order.append(w.cget("text"))
    assert order == ["Non-stop", "Shortcut", "Hidden Tracks"], order
    made = buttons.add("Quiet Evening", "artists")
    s.show_playlist(made["id"], rename=True)
    ui.pump(0.6)
    assert s._name_box.get() == "Quiet Evening" and s._name_box.selection_present(),         "a new playlist's page opens on the Name box with the name selected (focus itself isn't reliable in a test window)"
    assert not ui.errors, ui.errors[0]
