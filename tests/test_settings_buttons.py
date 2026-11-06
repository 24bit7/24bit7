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


def shown(widget):
    """Like walk, but skips anything not placed by a geometry manager: the sections a config builds out of sight."""
    yield widget
    for child in widget.winfo_children():
        if child.winfo_manager():
            yield from shown(child)


def shown_labels(widget):
    return [str(w.cget("text")) for w in shown(widget) if isinstance(w, (tk.Label, ttk.Checkbutton))]


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
    pane.select(pane._pages[tab_titles(pane).index("Playlist Settings")])
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
    assert "Playlist Settings" in titles and not {"Sources", "Playlist", "Filters", "Buttons", "Playlists", "Zones"} & set(titles), titles
    assert "Devices" in titles, "folded into Playlist Settings on 2 Nov 2026, its own tab again on 5 Nov 2026"
    assert s._button_names() == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Artist + Guests", "Consensus", "AI Playlist"]
    assert s._button_id == s._buttons[0]["id"] and s._button_page.button["name"] == "Similar Artists"
    assert not [w for w in walk(s._button_right) if hasattr(w, "_tabs")], "one page, no inner tabs"
    texts = labels(s._button_inner)
    assert "Config 1" in texts and "Artist Matching" in texts and "Sources" in texts and "Playlist Selection" in texts, texts[:12]
    pick_button(ui, "AI Playlist")
    assert "Sources" not in labels(s._button_inner), "an AI Playlist has no sources to pick"
    assert not ui.errors, ui.errors[0]


def test_the_list_has_no_tick_and_move_up_and_down_reorder(app, ui):
    """2 Nov 2026: a playlist is a button or a device's, so the list has no tick: everything in it is on the Play tab."""
    import buttons
    s = buttons_page(ui)
    _id, row, tick, _label, var = s._button_rows[3]   # Artist + Guests
    assert tick is None and var is None and row.left is None, "no tick"
    assert "Artist + Guests" in [b._name for b in ui.play.play_buttons]
    pick_button(ui, "Artist + Guests")
    s._button_move(-1)
    ui.pump(0.3)
    assert s._button_names()[2:4] == ["Artist + Guests", "Artist's Top Tracks"]
    assert [b._name for b in ui.play.play_buttons][2] == "Artist + Guests"
    s._button_move(1)
    ui.pump(0.3)
    assert s._button_names()[2:4] == ["Artist's Top Tracks", "Artist + Guests"]
    assert not ui.errors, ui.errors[0]


def test_the_chosen_row_is_a_border_and_the_help_line_is_gone(app, ui):
    from tabs import PALETTE
    s = buttons_page(ui)
    pick_button(ui, "Artist + Guests")
    ui.pump(0.3)
    rows = {bid: row for bid, row, _tick, _label, _var in s._button_rows}
    import buttons
    head = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    chosen = rows[head["id"]]
    assert chosen.chosen and chosen.text == "Artist + Guests", "a rounded outline in the accent colour"
    assert chosen.cget("bg") == s._button_list.cget("bg") == PALETTE["field_bg"], "no fill, on the field colour"
    others = [r for bid, r in rows.items() if bid != head["id"]]
    assert not any(r.chosen for r in others)
    assert "Ticked: on the Play tab. Rename: click the name at the top of its page." not in labels(s._buttons_outer)
    assert not ui.errors, ui.errors[0]


def test_the_name_box_at_the_top_renames(app, ui):
    """2 Nov 2026: the name is a box at the top of the page, beside Title in Menu, not a click-to-rename label."""
    import buttons
    pick_button(ui, "Artist + Guests")
    s = ui.settings
    entry = s._name_box
    assert entry.get() == "Artist + Guests"
    s._name_var.set("Star Turn")
    entry.focus_force()   # Tk sends a generated key press to the focus widget
    ui.pump(0.2)
    entry.event_generate("<Return>")
    ui.pump(0.3)
    assert s._name_var.get() == "Star Turn" and s._button_names()[3] == "Star Turn"
    assert buttons.get(s._button_id)["name"] == "Star Turn"
    assert [b._name for b in ui.play.play_buttons][3] == "Star Turn", "the Play tab follows"
    assert not ui.errors, ui.errors[0]


def test_a_page_shows_only_its_kind_with_its_switches(app, ui):
    p = pick_button(ui, "Artist + Guests")
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
    p = pick_button(ui, "Artist + Guests")
    assert not any(k.startswith("INNER_CIRCLE") for k in p.vars), "Top Tracks has no circle"
    p = pick_button(ui, "Similar Artists")
    page = inner_page(ui, "Sources")
    tick = next(w for w in walk(page) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "Consensus")
    size_cb = next(c for c in walk(page) if isinstance(c, ttk.Combobox) and tuple(c.cget("values")) == ("3", "4", "5"))
    agree_cb = next(c for c in walk(page) if isinstance(c, ttk.Combobox) and tuple(c.cget("values")) == ("2", "3"))
    assert "disabled" in size_cb.state() and "disabled" in agree_cb.state(), "greyed out until Consensus is on"
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
    p = pick_button(ui, "Consensus")
    assert p.vars["INNER_CIRCLE_ARTISTS"].get() is True and p.vars["INNER_CIRCLE_ARTISTS_SIZE"].get() == "3"
    assert not ui.errors, ui.errors[0]


def test_the_config_heading_changes_the_kind_except_on_a_standard_playlist(app, ui):
    import buttons
    p = pick_button(ui, "Similar Artists")
    page = inner_page(ui, "Sources")
    assert not getattr(ui.settings, "_kind_boxes", []) or not any(
        cb.winfo_exists() and str(cb.master.master.master) == str(page) for cb in ui.settings._kind_boxes), \
        "a standard playlist's own kind is a label"
    p = pick_button(ui, "Artist + Guests")
    ui.pump(0.3)
    boxes = [cb for cb in ui.settings._kind_boxes if cb.winfo_exists()]
    assert [cb.get() for cb in boxes] == ["Artist's Top Tracks", "Artist Matching"]
    boxes[1].set("Track Matching")
    boxes[1].event_generate("<<ComboboxSelected>>")
    ui.pump(0.5)
    head = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    assert [c["kind"] for c in buttons.configs(head)] == ["top", "tracks"]
    assert "SIMILAR_TRACK_COUNT" in head["configs"][0]["settings"]
    assert not ui.errors, ui.errors[0]


def test_a_second_config_has_its_own_block_and_the_mix_section_appears(app, ui):
    import buttons
    from tkinter import messagebox
    p = pick_button(ui, "Similar Tracks")
    page = inner_page(ui, "Sources")
    texts = shown_labels(page)
    assert "Config 1" in texts and "Mix" not in texts and "Config 2" not in texts
    drift_labels, nonstop_labels = texts.count("Drift"), texts.count("Non-stop")
    s = ui.settings
    s._config_add(p.button, "artists")
    ui.pump(0.5)
    page = inner_page(ui, "Sources")
    texts = shown_labels(page)
    assert "Config 2" in texts and "Mix" in texts and "Combine" in texts and "Drift from" in texts and "Continue as" in texts
    assert texts.count("Drift") == drift_labels and texts.count("Non-stop") == nonstop_labels, "the whole-playlist sections show once"
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
    assert "Mix" not in shown_labels(inner_page(ui, "Sources"))
    assert not ui.errors, ui.errors[0]


def test_a_custom_button_saves_into_itself_only(app, ui):
    import buttons
    import settings_gui
    env_before = settings_gui.read_env().get("TOP_TRACKS_COUNT")
    p = pick_button(ui, "Artist + Guests")
    p.vars["TOP_TRACKS_COUNT"].set("15")
    ui.pump(0.3)
    head = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    assert head["settings"]["TOP_TRACKS_COUNT"] == "15" and [c["kind"] for c in head["configs"]] == ["artists"]
    assert buttons.standard("top")["settings"].get("TOP_TRACKS_COUNT", "10") != "15"
    assert settings_gui.read_env().get("TOP_TRACKS_COUNT") == env_before, ".env is the standard button's"
    assert set(head["settings"]) <= set(buttons.KIND_KEYS["top"]), "only its kind's keys are kept"


def test_the_standard_button_also_writes_env(app, ui):
    import buttons
    import settings_gui
    p = pick_button(ui, "Artist's Top Tracks")
    p.vars["TOP_TRACKS_COUNT"].set("13")
    ui.pump(0.3)
    assert buttons.standard("top")["settings"]["TOP_TRACKS_COUNT"] == "13"
    assert settings_gui.read_env().get("TOP_TRACKS_COUNT") == "13"
    app.engine.refresh_settings_if_changed()
    assert app.engine.TOP_TRACKS_COUNT == 13
    assert next(b for b in buttons.load() if b["name"] == "Artist + Guests")["settings"].get("TOP_TRACKS_COUNT", "10") != "13"


def test_deep_cuts_switch_on_every_button_and_the_standard_one_reaches_env(app, ui):
    import buttons
    import settings_gui

    def switch(page):
        return [w for w in shown(page) if isinstance(w, ttk.Combobox)
                and tuple(w.cget("values")) == ("Off", "Spaced", "Shuffled")]
    pick_button(ui, "Similar Artists")
    page = inner_page(ui, "Playlist")
    # Deep Cuts is off, so its section is closed (2 Nov 2026): click its header to open it
    box = next(w for w in walk(page) if isinstance(w, tk.Frame) and hasattr(w, "is_open")
               and any(c.cget("text") == "Deep Cuts" for c in w.master.winfo_children()[0].winfo_children()
                       if isinstance(c, tk.Label)))
    if not box.is_open():
        box.master.winfo_children()[0].event_generate("<Button-1>")
        ui.pump(0.3)
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
    pick_button(ui, "Artist + Guests")
    assert not switch(inner_page(ui, "Playlist")), "Artist's Top Tracks has no Deep Cuts"
    assert not ui.errors, ui.errors[0]


def test_the_playing_now_line_and_review_tick_are_only_on_the_standard_button(app, ui):
    import buttons
    from tkinter import ttk
    pick_button(ui, "Similar Artists")
    page = inner_page(ui, "Playlist")
    texts = labels(page) + [w.cget("text") for w in walk(page) if isinstance(w, ttk.Checkbutton)]
    for text in ("When Seed is Current Track", "When Seed is Playing Now", "Review Mode uses the same settings"):
        assert text in texts, text
    buttons.add("Sunday", "artists")
    pick_button(ui, "Sunday")
    page = inner_page(ui, "Playlist")
    texts = labels(page) + [w.cget("text") for w in walk(page) if isinstance(w, ttk.Checkbutton)]
    assert "When Seed is Playing Now" not in texts and "Review Mode uses the same settings" not in texts
    assert "When Seed is Current Track" in texts and "tracks, from" in texts


def test_filters_tick_on_the_page_and_edit_filters_opens_a_window(app, ui):
    import buttons
    import filters
    f = filters.blank("Stereo")
    filters.save([f])
    p = pick_button(ui, "Artist + Guests")
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
    assert "Used by: Artist + Guests (config 1)" in texts, texts   # filters are each config's (2 Nov 2026)
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
    head = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    monkeypatch.setattr(settings_gui, "ask_new_button", lambda parent: ("template", "headliner"))
    s._button_add()
    ui.pump(0.3)
    assert s._button_names()[-1] == "Artist + Guests 2" and s._button_page.button["name"] == "Artist + Guests 2"
    assert [c["kind"] for c in s._button_page.button["configs"]] == ["artists"]
    assert [b._name for b in ui.play.play_buttons][-1] == "Artist + Guests 2", "the Play tab follows"
    assert "disabled" in s._list_buttons["down"].cget("state") and "normal" in s._list_buttons["up"].cget("state")
    monkeypatch.setattr(settings_gui, "ask_new_button", lambda parent: ("new", None))
    s._button_add()
    ui.pump(0.6)
    assert s._button_names()[-1] == "New Playlist" and s._button_page is None, "a blank slate has no config page yet"
    entry = next((w for w in walk(s._button_right) if isinstance(w, tk.Entry) and w.get() == "New Playlist"), None)
    assert entry is not None, "the name box is open on a new playlist's page"
    entry.delete(0, "end")
    entry.insert(0, "Sunday Guests")
    entry.focus_force()
    ui.pump(0.2)
    entry.event_generate("<Return>")
    ui.pump(0.3)
    assert s._button_names()[-1] == "Sunday Guests"
    s._button_remove()   # the question answered No by the fixture
    assert s._button_names()[-1] == "Sunday Guests"
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._button_remove()
    ui.pump(0.3)
    assert "Sunday Guests" not in s._button_names()
    buttons.remove(buttons.get(s._button_names() and next(b["id"] for b in buttons.load() if b["name"] == "Artist + Guests 2"))["id"])
    s._buttons_refresh()
    assert s._button_page.button["name"] == "Similar Artists", "back to the first"
    assert "Sunday Guests" not in [b._name for b in ui.play.play_buttons]
    buttons.restore_standard()   # the fake world starts without the two Top 10s 24bit7 ships (conftest): complete it
    s._buttons_refresh()
    s._button_restore()
    assert ui.answers[-1][1][0] == "Restore Default Playlists", "nothing missing: it says so"
    buttons.remove(buttons.standard("tracks")["id"])
    s._buttons_refresh()
    s._button_restore()
    ui.pump(0.3)
    tracks = buttons.standard("tracks")
    assert tracks["name"] == "Track Matching" and s._button_page.button["kind"] == "tracks", "back as it ships"
    assert tracks["parent"] == buttons.standard("artists")["id"], "under Similar Artists, where it ships"
    assert "Track Matching" in s._button_names()
    assert not ui.errors, ui.errors[0]


def test_the_list_follows_the_play_tab(app, ui, monkeypatch):
    import buttons
    import tabs
    s = buttons_page(ui)
    pick_button(ui, "Artist + Guests")
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "Star Turn")
    ui.play._rename_button(buttons.get(s._button_id))
    s._buttons_refresh()   # as opening the page does
    assert s._button_names()[3] == "Star Turn"
    assert s._button_page.button["id"] == s._button_id, "the page wasn't rebuilt for a rename"


def test_voice_tab_has_no_own_settings_column(app, ui):
    pane = settings_pane(ui)
    ui.nb.select(ui.settings)
    pane.select(pane._pages[tab_titles(pane).index("Voice Commands")])
    ui.pump(0.5)
    texts = labels(pane._pages[tab_titles(pane).index("Voice Commands")])
    assert "Own settings" not in texts and "Switch Timing Adjustment" in texts
    assert "Enable Switch To" not in texts, "the devices live under Settings > Devices now"
