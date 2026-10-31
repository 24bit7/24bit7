"""
Settings > Zones (stage four, 31 Oct 2026): one page per JRiver zone, with Show and Default (moved from
Other), the button each voice phrase runs, its filters and a Non-stop switch. Also from stage four: the
shortcut box on a button's page, and JRiver Playlists as one page.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import walk, labels, settings_pane, tab_titles, pick_button


def page_named(ui, title):
    s = ui.settings
    pane = settings_pane(ui)
    page = pane._pages[tab_titles(pane).index(title)]
    ui.nb.select(s)
    pane.select(page)
    ui.pump(0.4)
    return page


def zones_page(ui):
    page_named(ui, "Zones")
    return ui.settings


def pick_zone(ui, name):
    s = zones_page(ui)
    s._zones_refresh()
    s._zone_list.selection_clear(0, "end")
    s._zone_list.selection_set(s._zone_rows.index(name))
    s._zone_picked()
    ui.pump(0.3)
    return s


def ticks(widget):
    return [w for w in walk(widget) if isinstance(w, ttk.Checkbutton)]


def tick_named(widget, text):
    return next(w for w in ticks(widget) if str(w.cget("text")) == text)


def combos(widget):
    return [w for w in walk(widget) if isinstance(w, ttk.Combobox)]


def test_zones_tab_follows_buttons_and_other_loses_its_zones_section(app, ui):
    import zones
    zones.update("Attic", filters=[])   # a zone JRiver can't see
    s = zones_page(ui)
    titles = tab_titles(settings_pane(ui))
    assert titles.index("Zones") == titles.index("Buttons") + 1, titles
    assert "Follow JRiver's active zone" in labels(s._zone_right.master)
    assert "Follow JRiver's active zone" not in labels(page_named(ui, "Other"))
    s = zones_page(ui)
    names = app.engine.zone_names(include_hidden=True)
    assert s._zone_rows == names + ["Attic"], s._zone_rows
    assert s._zone_list.get("end") == "Attic (not found)"
    texts = labels(s._zone_right)
    for text in ("Show in the Zone and Output lists", "Default zone", "Music like", "Songs by", "Tracks like this",
                 "Play something", "Non-stop may top up playlists in this zone"):
        assert text in texts, text
    pick_zone(ui, "Attic")
    assert any(t.startswith("JRiver can't see this zone") for t in labels(s._zone_right))
    assert not ui.errors, ui.errors[0]


def test_show_default_and_follow_save_to_env(app, ui):
    import settings_gui
    s = pick_zone(ui, "Kitchen")
    show, default = tick_named(s._zone_right, "Show in the Zone and Output lists"), tick_named(s._zone_right, "Default zone")
    assert "disabled" not in default.state()
    show.invoke()
    ui.pump(0.2)
    assert settings_gui.read_env().get("HIDDEN_ZONES") == "Kitchen"
    assert "disabled" in default.state(), "a hidden zone can't be the default"
    show.invoke()
    default.invoke()
    ui.pump(0.2)
    env = settings_gui.read_env()
    assert env.get("HIDDEN_ZONES") == "" and env.get("DEFAULT_ZONE") == "Kitchen", env
    s = pick_zone(ui, "Speakers")
    default = tick_named(s._zone_right, "Default zone")
    assert s._zone_default_var.get() == "", "Speakers isn't the default any more"
    default.invoke()
    ui.pump(0.2)
    assert settings_gui.read_env().get("DEFAULT_ZONE") == "Speakers"
    s = pick_zone(ui, "Kitchen")
    assert s._zone_default_var.get() == ""
    follow = tick_named(s._zone_right.master, "Follow JRiver's active zone")
    follow.invoke()
    ui.pump(0.2)
    assert settings_gui.read_env().get("FOLLOW_ACTIVE_ZONE") == "1"
    assert "disabled" in tick_named(s._zone_right, "Default zone").state()
    follow.invoke()
    ui.pump(0.2)
    assert settings_gui.read_env().get("FOLLOW_ACTIVE_ZONE") == "0"
    assert not ui.errors, ui.errors[0]


def test_phrase_dropdowns_pick_a_button(app, ui):
    import buttons
    import zones
    sunday = buttons.add("Sunday", "tracks")
    s = pick_zone(ui, "Kitchen")
    cb = next(c for c in combos(s._zone_right) if "Sunday" in c.cget("values"))
    assert tuple(cb.cget("values")) == ("Similar Tracks", "Sunday") and cb.get() == "Similar Tracks"
    cb.set("Sunday")
    cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert zones.load()["Kitchen"]["buttons"]["tracks_like"] == sunday["id"]
    assert zones.button_for("Kitchen", "more_like")["id"] == sunday["id"]
    cb.set("Similar Tracks")
    cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert zones.load()["Kitchen"]["buttons"]["tracks_like"] is None, "the standard button is kept as unset"
    pick_zone(ui, "Speakers")
    cb = next(c for c in combos(s._zone_right) if "Sunday" in c.cget("values"))
    assert cb.get() == "Similar Tracks", "another zone is untouched"


def test_zone_filters_tick_and_edit_filters_says_so(app, ui):
    import filters
    import zones
    f = filters.blank("Stereo")
    filters.save([f])
    s = pick_zone(ui, "Kitchen")
    stereo = tick_named(s._zone_filter_row, "Stereo")
    stereo.invoke()
    ui.pump(0.2)
    assert zones.filter_ids("Kitchen") == [f["id"]]
    win = s._open_filters()
    ui.pump(0.4)
    assert "Used by: the Kitchen zone" in labels(win), labels(win)
    win.destroy()
    ui.pump(0.2)
    tick_named(s._zone_filter_row, "Stereo").invoke()
    ui.pump(0.2)
    assert zones.filter_ids("Kitchen") == []
    assert not ui.errors, ui.errors[0]


def test_the_zones_non_stop_switch(app, ui):
    import zones
    s = pick_zone(ui, "Kitchen")
    assert zones.nonstop_on("Kitchen")
    tick_named(s._zone_right, "Non-stop may top up playlists in this zone").invoke()
    ui.pump(0.2)
    assert not zones.nonstop_on("Kitchen") and zones.nonstop_on("Speakers")


def test_a_buttons_page_has_a_shortcut_box(app, ui):
    import buttons
    import hotkeys
    p = pick_button(ui, "Headliner")
    s = ui.settings
    code = hotkeys.button_code(p.button["id"])
    assert code in s.hotkey_vars and "Shortcut" in labels(s._button_right)
    s._hotkey_save(code, "Ctrl+Alt+8")
    ui.pump(0.2)
    assert buttons.get(p.button["id"])["shortcut"] == "Ctrl+Alt+8"
    assert hotkeys.assigned() == {code: "Ctrl+Alt+8"}
    pick_button(ui, "AI Playlist")
    assert not any(hotkeys.is_button(c) for c in s.hotkey_vars), "an AI Playlist has no shortcut box"
    assert "Shortcut" not in labels(s._button_right)
    page_named(ui, "Other")
    assert "SHUFFLE_ARTIST" in s.hotkey_vars and "SIMILAR_TRACKS" not in s.hotkey_vars
    texts = labels(page_named(ui, "Other"))
    assert "Shuffle Songs by Artist" in texts and "Similar Tracks" not in texts
    assert not ui.errors, ui.errors[0]


def test_jriver_playlists_is_one_page(app, ui):
    page = page_named(ui, "JRiver Playlists")
    ui.pump(0.8)
    texts = labels(page)
    assert "Copy Windows (Main)" not in texts and "Windows (Main)" not in texts
    assert not [w for w in walk(page) if hasattr(w, "_tabs")], "no device tabs inside the page"
    assert "Use global playlist settings" in texts, texts[:20]
