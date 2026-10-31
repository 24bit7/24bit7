"""
Settings > Buttons (stage three, 31 Oct 2026): one page per button in place of the Sources, Playlist
and Filters tabs. A page shows only its kind's sections, saves into the button (the standard button
of each kind also writes .env), ticks filters, and opens Edit Filters as a window.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui, visit_every_page  # noqa: F401  (the GUI fixture)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def labels(widget):
    return [str(w.cget("text")) for w in walk(widget) if isinstance(w, (tk.Label, ttk.Checkbutton))]


def settings_pane(ui):
    return next(c for c in ui.settings.winfo_children() if hasattr(c, "select"))


def tab_titles(pane):
    return [t.cget("text") for t in pane._tabs]


def buttons_page(ui):
    """Settings > Buttons on screen. Returns the SettingsTab."""
    s = ui.settings
    pane = settings_pane(ui)
    ui.nb.select(s)
    pane.select(pane._pages[tab_titles(pane).index("Buttons")])
    ui.pump(0.3)
    return s


def pick_button(ui, name):
    """Clicks a button in the list; returns its ProfilePage."""
    s = buttons_page(ui)
    s._buttons_refresh()   # as opening the page does: a button added behind its back is listed
    names = [b["name"] for b in s._buttons]
    s._button_list.selection_clear(0, "end")
    s._button_list.selection_set(names.index(name))
    s._button_picked()
    ui.pump(0.4)
    return s._button_page


def inner_pane(ui):
    """The Sources | Playlist pane on the right of Settings > Buttons."""
    return [p for p in walk(ui.settings._button_right) if hasattr(p, "_tabs") and hasattr(p, "select")][0]


def inner_page(ui, title):
    pane = inner_pane(ui)
    page = pane._pages[tab_titles(pane).index(title)]
    pane.select(page)
    ui.pump(0.3)
    return page


def test_buttons_tab_replaces_sources_playlist_and_filters(app, ui):
    s = buttons_page(ui)
    titles = tab_titles(settings_pane(ui))
    assert "Buttons" in titles and not {"Sources", "Playlist", "Filters"} & set(titles), titles
    assert s._button_list.get(0, "end") == ("Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Headliner",
                                            "AI Playlist")
    assert s._button_list.curselection() == (0,) and s._button_page.button["name"] == "Similar Artists"
    assert tab_titles(inner_pane(ui)) == ["Sources", "Playlist"]
    pick_button(ui, "AI Playlist")
    assert tab_titles(inner_pane(ui)) == ["Playlist"], "an AI Playlist has no sources to pick"
    assert not ui.errors, ui.errors[0]


def test_a_page_shows_only_its_kind_with_its_switches(app, ui):
    p = pick_button(ui, "Headliner")
    assert "TOP_TRACKS_COUNT" in p.vars and "NONSTOP_TOP_REST" in p.vars and "TOP_TRACK_SOURCES" in p.vars
    assert not any(k in p.vars for k in ("SIMILAR_ARTIST_LIMIT", "SIMILAR_SOURCES", "DRIFT_TOP", "VIBE_TRACK_COUNT"))
    assert p.button["kind"] == "top" and not p.columns
    p = pick_button(ui, "Similar Artists")
    assert "SIMILAR_ARTIST_LIMIT" in p.vars and "DRIFT_ARTISTS_FROM" in p.vars and "SIMILAR_SOURCES" in p.vars
    assert "AI_MODERATOR_ARTISTS" in p.vars, "the Moderator is on every button's Sources page"
    assert "DEEP_CUTS_ARTISTS" in p.vars and "DEEP_CUTS_ARTISTS_SHARE" in p.vars, "and the Deep Cuts switch on its Playlist page"
    assert "TOP_TRACKS_COUNT" not in p.vars
    assert not ui.errors, ui.errors[0]


def test_a_custom_button_saves_into_itself_only(app, ui):
    import buttons
    import settings_gui
    env_before = settings_gui.read_env().get("TOP_TRACKS_COUNT")
    p = pick_button(ui, "Headliner")
    p.vars["TOP_TRACKS_COUNT"].set("15")
    ui.pump(0.3)
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    assert head["settings"]["TOP_TRACKS_COUNT"] == "15" and head["settings"]["TOP_GUESTS"] == "third"
    assert buttons.standard("top")["settings"].get("TOP_TRACKS_COUNT", "10") != "15"
    assert settings_gui.read_env().get("TOP_TRACKS_COUNT") == env_before, ".env is the standard button's"
    assert set(head["settings"]) <= set(buttons.KIND_KEYS["top"]), "only its kind's keys are kept"


def test_the_standard_button_also_writes_env(app, ui):
    import buttons
    import settings_gui
    p = pick_button(ui, "Artist's Top Tracks")
    p.vars["TOP_TRACKS_COUNT"].set("12")
    ui.pump(0.3)
    assert buttons.standard("top")["settings"]["TOP_TRACKS_COUNT"] == "12"
    assert settings_gui.read_env().get("TOP_TRACKS_COUNT") == "12"
    app.engine.refresh_settings_if_changed()
    assert app.engine.TOP_TRACKS_COUNT == 12
    assert next(b for b in buttons.load() if b["name"] == "Headliner")["settings"].get("TOP_TRACKS_COUNT", "10") != "12"


def test_deep_cuts_switch_on_every_button_and_the_standard_one_reaches_env(app, ui):
    import buttons
    import settings_gui

    def switch(page):
        return [w for w in walk(page) if isinstance(w, ttk.Combobox)
                and tuple(w.cget("values")) == ("Off", "Spaced", "Shuffled")]
    pick_button(ui, "Similar Artists")
    page = inner_page(ui, "Playlist")
    switches = switch(page)
    assert len(switches) == 1
    switches[0].set("Spaced")
    switches[0].event_generate("<<ComboboxSelected>>")
    ui.pump(0.3)
    assert buttons.standard("artists")["settings"]["DEEP_CUTS_ARTISTS"] == "spaced"
    assert settings_gui.read_env().get("DEEP_CUTS_ARTISTS") == "spaced"
    app.engine.refresh_settings_if_changed()
    assert app.engine.DEEP_CUTS["artists"]["mode"] == "spaced"
    buttons.add("Sunday", "artists")
    pick_button(ui, "Sunday")
    page = inner_page(ui, "Playlist")
    assert len(switch(page)) == 1, "a button of your own has its own switch"
    pick_button(ui, "Headliner")
    assert not switch(inner_page(ui, "Playlist")), "Artist's Top Tracks has no Deep Cuts"
    assert not ui.errors, ui.errors[0]


def test_review_and_playing_now_columns_only_on_the_standard_button(app, ui):
    import buttons
    pick_button(ui, "Similar Artists")
    texts = labels(inner_page(ui, "Playlist"))
    for text in ("SEED", "REVIEW MODE", "Playing Now", "Mirror Playing Now", "Artists sampled from Playing Now"):
        assert text in texts, text
    buttons.add("Sunday", "artists")
    pick_button(ui, "Sunday")
    texts = labels(inner_page(ui, "Playlist"))
    assert "Playing Now" not in texts and "SEED" not in texts and "Mirror Playing Now" not in texts
    assert "Number of artists" in texts


def test_filters_tick_on_the_page_and_edit_filters_opens_a_window(app, ui):
    import buttons
    import filters
    f = filters.blank("Stereo")
    filters.save([f])
    p = pick_button(ui, "Headliner")
    s = ui.settings
    ticks = [w for w in walk(s._button_filter_row) if isinstance(w, ttk.Checkbutton)]
    assert [t.cget("text") for t in ticks] == ["Stereo"]
    ticks[0].invoke()
    ui.pump(0.2)
    assert buttons.get(p.button["id"])["filters"] == [f["id"]]
    assert ui.play.play_buttons[3]._tooltip.text.endswith("Filters"), "the Play tab's note follows"
    win = s._open_filters()
    ui.pump(0.4)
    assert win.title() == "Edit Filters" and win.winfo_exists()
    texts = labels(win)
    assert "Applies on" not in texts and "Active filters" not in texts
    assert "Used by: Headliner" in texts, texts
    assert s._open_filters() is win, "opened again, it's the same window"
    ticks[0].invoke()
    ui.pump(0.2)
    s._filter_fill_editor()
    assert any(t.startswith("Not ticked on any button yet") for t in labels(win))
    win.destroy()
    ui.pump(0.2)
    assert not ui.errors, ui.errors[0]


def test_add_remove_and_restore_from_settings(app, ui, monkeypatch):
    import buttons
    import settings_gui
    from tkinter import messagebox
    s = buttons_page(ui)
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    monkeypatch.setattr(settings_gui, "ask_new_button", lambda parent: ("Sunday Guests", "top", head["id"]))
    s._button_add()
    ui.pump(0.3)
    assert s._button_list.get("end") == "Sunday Guests" and s._button_page.button["name"] == "Sunday Guests"
    assert s._button_page.button["settings"]["TOP_GUESTS"] == "third"
    assert [b._name for b in ui.play.play_buttons][-1] == "Sunday Guests", "the Play tab follows"
    s._button_remove()   # the question answered No by the fixture
    assert s._button_list.get("end") == "Sunday Guests"
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._button_remove()
    ui.pump(0.3)
    assert "Sunday Guests" not in s._button_list.get(0, "end")
    assert s._button_page.button["name"] == "Similar Artists", "back to the first"
    assert "Sunday Guests" not in [b._name for b in ui.play.play_buttons]
    s._button_restore()
    assert ui.answers[-1][1][0] == "Restore Default Buttons", "nothing missing: it says so"
    buttons.remove(buttons.standard("tracks")["id"])
    s._buttons_refresh()
    s._button_restore()
    ui.pump(0.3)
    assert s._button_list.get("end") == "Similar Tracks" and s._button_page.button["kind"] == "tracks"
    assert not ui.errors, ui.errors[0]


def test_the_list_follows_the_play_tab(app, ui, monkeypatch):
    import buttons
    import tabs
    s = buttons_page(ui)
    pick_button(ui, "Headliner")
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "Star Turn")
    ui.play._rename_button(buttons.get(s._button_id))
    s._buttons_refresh()   # as opening the page does
    assert s._button_list.get(3) == "Star Turn" and s._button_title.cget("text") == "Star Turn"
    assert s._button_page.button["id"] == s._button_id, "the page wasn't rebuilt for a rename"


def test_voice_tab_has_no_own_settings_column(app, ui):
    pane = settings_pane(ui)
    ui.nb.select(ui.settings)
    pane.select(pane._pages[tab_titles(pane).index("Voice Commands")])
    ui.pump(0.5)
    texts = labels(pane._pages[tab_titles(pane).index("Voice Commands")])
    assert "Own settings" not in texts and "Enable Switch To" in texts
