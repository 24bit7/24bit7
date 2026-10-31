"""
Settings > Playlists (stage three, 31 Oct 2026, then the tick list and one page that evening): a page per
playlist in place of the Sources, Playlist and Filters tabs. A page shows only its kind's sections, saves
into the playlist (the standard one of each kind also writes .env), ticks filters, and opens Edit Filters
as a window. A tick beside each name says whether it's on the Play tab.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)


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


def page_named(ui, title):
    s = ui.settings
    pane = settings_pane(ui)
    page = pane._pages[tab_titles(pane).index(title)]
    ui.nb.select(s)
    pane.select(page)
    ui.pump(0.4)
    return page


def buttons_page(ui):
    """Settings > Playlists on screen. Returns the SettingsTab."""
    s = ui.settings
    pane = settings_pane(ui)
    ui.nb.select(s)
    pane.select(pane._pages[tab_titles(pane).index("Playlists")])
    ui.pump(0.3)
    return s


def pick_button(ui, name):
    """Clicks a playlist in the list; returns its ProfilePage."""
    s = buttons_page(ui)
    s._buttons_refresh()   # as opening the page does: a playlist added behind its back is listed
    s._pick_button(next(b["id"] for b in s._buttons if b["name"] == name))
    ui.pump(0.4)
    return s._button_page


def inner_page(ui, title):
    """The playlist's one page: its sources and its settings together (title kept for older callers)."""
    ui.pump(0.3)
    return ui.settings._button_inner


def test_playlists_tab_replaces_sources_playlist_and_filters(app, ui):
    s = buttons_page(ui)
    titles = tab_titles(settings_pane(ui))
    assert "Playlists" in titles and not {"Sources", "Playlist", "Filters", "Buttons", "Zones"} & set(titles), titles
    assert "Devices" in titles
    assert s._button_names() == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Headliner", "Inner Circle", "AI Playlist"]
    assert s._button_id == s._buttons[0]["id"] and s._button_page.button["name"] == "Similar Artists"
    assert not [w for w in walk(s._button_right) if hasattr(w, "_tabs")], "one page, no inner tabs"
    texts = labels(s._button_inner)
    assert "Config 1" in texts and "Similar Artists" in texts and "SOURCES" in texts and "PLAYLIST" in texts, texts[:12]
    pick_button(ui, "AI Playlist")
    assert "SOURCES" not in labels(s._button_inner), "an AI Playlist has no sources to pick"
    assert not ui.errors, ui.errors[0]


def test_the_tick_puts_a_playlist_on_the_play_tab_and_move_up_and_down_reorder(app, ui):
    import buttons
    s = buttons_page(ui)
    _id, _row, tick, _label, var = s._button_rows[3]   # Headliner
    assert var.get() is True
    tick.invoke()
    ui.pump(0.3)
    assert buttons.get(s._buttons[3]["id"])["shown"] is False
    assert "Headliner" not in [b._name for b in ui.play.play_buttons], "the Play tab follows"
    tick.invoke()
    ui.pump(0.3)
    assert "Headliner" in [b._name for b in ui.play.play_buttons]
    pick_button(ui, "Headliner")
    s._button_move(-1)
    ui.pump(0.3)
    assert s._button_names()[2:4] == ["Headliner", "Artist's Top Tracks"]
    assert [b._name for b in ui.play.play_buttons][2] == "Headliner"
    s._button_move(1)
    ui.pump(0.3)
    assert s._button_names()[2:4] == ["Artist's Top Tracks", "Headliner"]
    assert not ui.errors, ui.errors[0]


def test_the_name_at_the_top_renames_in_place(app, ui):
    import buttons
    pick_button(ui, "Headliner")
    s = ui.settings
    s._button_title.event_generate("<Button-1>")
    ui.pump(0.3)
    entry = next(w for w in walk(s._button_right) if isinstance(w, tk.Entry) and w.get() == "Headliner")
    entry.delete(0, "end")
    entry.insert(0, "Star Turn")
    entry.event_generate("<Return>")
    ui.pump(0.3)
    assert s._button_title.cget("text") == "Star Turn" and s._button_names()[3] == "Star Turn"
    assert buttons.get(s._button_id)["name"] == "Star Turn"
    assert [b._name for b in ui.play.play_buttons][3] == "Star Turn", "the Play tab follows"
    assert not ui.errors, ui.errors[0]


def test_a_page_shows_only_its_kind_with_its_switches(app, ui):
    p = pick_button(ui, "Headliner")
    assert "TOP_TRACKS_COUNT" in p.vars and "NONSTOP_TOP_REST" in p.vars and "TOP_TRACK_SOURCES" in p.vars
    assert not any(k in p.vars for k in ("SIMILAR_ARTIST_LIMIT", "SIMILAR_SOURCES", "DRIFT_TOP", "VIBE_TRACK_COUNT"))
    assert p.button["kind"] == "top" and not p.columns
    p = pick_button(ui, "Similar Artists")
    assert "SIMILAR_ARTIST_LIMIT" in p.vars and "DRIFT_ARTISTS_FROM" in p.vars and "SIMILAR_SOURCES" in p.vars
    assert "AI_MODERATOR_ARTISTS" in p.vars, "the Moderator is on every button's Sources page"
    assert "DEEP_CUTS_ARTISTS" in p.vars and "DEEP_CUTS_ARTISTS_SHARE" in p.vars, "and the Deep Cuts switch further down the page"
    assert "TOP_TRACKS_COUNT" not in p.vars
    assert not ui.errors, ui.errors[0]


def test_inner_circle_sits_on_a_matching_page_and_its_dials_keep_in_step(app, ui):
    import buttons
    import settings_gui
    p = pick_button(ui, "Headliner")
    assert not any(k.startswith("INNER_CIRCLE") for k in p.vars), "Top Tracks has no circle"
    p = pick_button(ui, "Similar Artists")
    page = inner_page(ui, "Sources")
    tick = next(w for w in walk(page) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "Inner Circle")
    size_cb = next(c for c in walk(page) if isinstance(c, ttk.Combobox) and tuple(c.cget("values")) == ("3", "4", "5"))
    agree_cb = next(c for c in walk(page) if isinstance(c, ttk.Combobox) and tuple(c.cget("values")) == ("2", "3"))
    assert "disabled" in size_cb.state() and "disabled" in agree_cb.state(), "greyed out until Inner Circle is on"
    tick.invoke()
    ui.pump(0.3)
    assert "disabled" not in size_cb.state()
    assert buttons.standard("artists")["settings"]["INNER_CIRCLE_ARTISTS"] == "1"
    assert settings_gui.read_env().get("INNER_CIRCLE_ARTISTS") == "1", "the standard playlist also writes .env"
    size_cb.set("5")
    size_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.3)
    assert tuple(agree_cb.cget("values")) == ("2", "3", "4", "5")
    agree_cb.set("4")
    agree_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.3)
    s = buttons.standard("artists")["settings"]
    assert s["INNER_CIRCLE_ARTISTS_SIZE"] == "5" and s["INNER_CIRCLE_ARTISTS_AGREE"] == "4"
    size_cb.set("3")
    size_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.3)
    assert agree_cb.get() == "3", "agree can't be more than the circle"
    assert buttons.standard("artists")["settings"]["INNER_CIRCLE_ARTISTS_AGREE"] == "3"
    p = pick_button(ui, "Inner Circle")
    assert p.vars["INNER_CIRCLE_ARTISTS"].get() is True and p.vars["INNER_CIRCLE_ARTISTS_SIZE"].get() == "3"
    assert not ui.errors, ui.errors[0]


def test_a_second_config_has_its_own_block_and_the_mix_section_appears(app, ui):
    import buttons
    from tkinter import messagebox
    p = pick_button(ui, "Similar Tracks")
    page = inner_page(ui, "Sources")
    texts = labels(page)
    assert "Config 1" in texts and "Mix" not in texts and "Config 2" not in texts
    s = ui.settings
    s._config_add(p.button, "artists")
    ui.pump(0.5)
    page = inner_page(ui, "Sources")
    texts = labels(page)
    assert "Config 2" in texts and "Mix" in texts and "Combine" in texts and "Drift from" in texts and "Continue as" in texts
    assert texts.count("Drift") == 1 and texts.count("Non-stop") == 1, "the whole-playlist sections show once"
    pages = s._button_pages
    assert [getattr(q, "config_kind", None) for q in pages] == ["tracks", "artists"]
    pages[1].vars["SIMILAR_ARTIST_LIMIT"].set("9")
    ui.pump(0.3)
    b = buttons.get(p.button["id"])
    assert b["configs"][0]["settings"]["SIMILAR_ARTIST_LIMIT"] == "9", "config 2's page saves into config 2"
    assert "SIMILAR_ARTIST_LIMIT" not in b["settings"]
    combine_cb, pattern_vars, drift_cb, cont_cb = s._mix_controls
    combine_cb.set("Alternate")
    combine_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.3)
    pattern_vars[1].set("3")
    combine_cb.event_generate("<<ComboboxSelected>>")   # any Mix change saves the lot
    ui.pump(0.3)
    b = buttons.get(p.button["id"])
    assert b["mix"]["combine"] == "alternate" and b["mix"]["pattern"] == [1, 3]
    cont_cb.set(cont_cb.cget("values")[1])
    cont_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.5)
    assert buttons.get(p.button["id"])["mix"]["continue_as"] == 1
    monkeypatch_yes = lambda *a, **k: True
    old = messagebox.askyesno
    messagebox.askyesno = monkeypatch_yes
    try:
        s._config_remove(buttons.get(p.button["id"]), 1)
    finally:
        messagebox.askyesno = old
    ui.pump(0.5)
    b = buttons.get(p.button["id"])
    assert b["configs"] == [] and b["mix"]["continue_as"] == 0
    assert "Mix" not in labels(inner_page(ui, "Sources"))
    assert not ui.errors, ui.errors[0]


def test_a_custom_button_saves_into_itself_only(app, ui):
    import buttons
    import settings_gui
    env_before = settings_gui.read_env().get("TOP_TRACKS_COUNT")
    p = pick_button(ui, "Headliner")
    p.vars["TOP_TRACKS_COUNT"].set("15")
    ui.pump(0.3)
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    assert head["settings"]["TOP_TRACKS_COUNT"] == "15" and [c["kind"] for c in head["configs"]] == ["artists"]
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
    assert s._button_names()[-1] == "Sunday Guests" and s._button_page.button["name"] == "Sunday Guests"
    assert [c["kind"] for c in s._button_page.button["configs"]] == ["artists"]
    assert [b._name for b in ui.play.play_buttons][-1] == "Sunday Guests", "the Play tab follows"
    s._button_remove()   # the question answered No by the fixture
    assert s._button_names()[-1] == "Sunday Guests"
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._button_remove()
    ui.pump(0.3)
    assert "Sunday Guests" not in s._button_names()
    assert s._button_page.button["name"] == "Similar Artists", "back to the first"
    assert "Sunday Guests" not in [b._name for b in ui.play.play_buttons]
    s._button_restore()
    assert ui.answers[-1][1][0] == "Restore Default Buttons", "nothing missing: it says so"
    buttons.remove(buttons.standard("tracks")["id"])
    s._buttons_refresh()
    s._button_restore()
    ui.pump(0.3)
    assert s._button_names()[-1] == "Similar Tracks" and s._button_page.button["kind"] == "tracks"
    assert not ui.errors, ui.errors[0]


def test_the_list_follows_the_play_tab(app, ui, monkeypatch):
    import buttons
    import tabs
    s = buttons_page(ui)
    pick_button(ui, "Headliner")
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "Star Turn")
    ui.play._rename_button(buttons.get(s._button_id))
    s._buttons_refresh()   # as opening the page does
    assert s._button_names()[3] == "Star Turn" and s._button_title.cget("text") == "Star Turn"
    assert s._button_page.button["id"] == s._button_id, "the page wasn't rebuilt for a rename"


def test_voice_tab_has_no_own_settings_column(app, ui):
    pane = settings_pane(ui)
    ui.nb.select(ui.settings)
    pane.select(pane._pages[tab_titles(pane).index("Voice Commands")])
    ui.pump(0.5)
    texts = labels(pane._pages[tab_titles(pane).index("Voice Commands")])
    assert "Own settings" not in texts and "Switch Timing Adjustment" in texts
    assert "Enable Switch To" not in texts, "the devices live under Settings > Devices now"
