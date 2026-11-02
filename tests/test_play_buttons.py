"""
The Play tab draws its buttons from the ticked playlists (stage two, 31 Oct 2026, then the tick and the
+ menu that evening): + offers the unticked ones and New..., right-click renames, copies, moves or takes
one off the row, a click runs that playlist's settings, the notes say what each has on, and the row
wraps when the window is narrow.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


def names(p):
    return [b._name for b in p.play_buttons]


class Click:
    x_root = y_root = 0


def test_row_comes_from_the_ticked_playlists_then_more_options_and_plus(app, ui):
    import buttons
    p = ui.play
    assert names(p) == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Artist + Guests", "Consensus", "AI Playlist"]
    buttons.set_shown(buttons.standard("vibe")["id"], False)
    p.refresh_buttons()
    assert names(p) == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Artist + Guests", "Consensus"], "unticked: off the row"
    buttons.set_shown(buttons.standard("vibe")["id"], True)
    p.refresh_buttons()
    ui.pump(0.3)
    row = p.play_buttons + [p.more_button, p.add_button]
    xs = [b.winfo_x() for b in row]
    assert xs == sorted(xs) and len(set(xs)) == len(xs), xs
    assert len({b.winfo_y() for b in row}) == 1, "one row at 1400 wide"
    assert p.add_button.cget("text") == "+"
    assert p.buttons[-1] is p.credits_button, "Show Credits still greys out with the rest"


def test_plus_opens_the_window_and_its_three_answers_land(app, ui, monkeypatch):
    import buttons
    p = ui.play
    opened = []
    monkeypatch.setattr(p, "open_playlist_settings", lambda bid, rename=False: opened.append((bid, rename)))
    head = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    buttons.set_shown(head["id"], False)
    p.refresh_buttons()
    assert "Artist + Guests" not in names(p)
    p._end_greeting(keep=False)   # the start-up greeting holds console lines back while it types
    monkeypatch.setattr(p, "_ask_new_button", lambda: ("existing", head["id"]))
    p.on_add_button()
    assert names(p)[3] == "Artist + Guests", "ticked again, it comes back at its place in the list"
    assert opened == [] and p.log.get("1.0", "end").count("Artist + Guests is on the Play tab") == 1
    monkeypatch.setattr(p, "_ask_new_button", lambda: ("template", "headliner"))
    p.on_add_button()
    assert names(p)[-1] == "Artist + Guests 2" and opened == []
    made = p.play_buttons[-1]._button
    assert [c["kind"] for c in buttons.configs(made)] == ["top", "artists"]
    monkeypatch.setattr(p, "_ask_new_button", lambda: ("new", None))
    p.on_add_button()
    new = p.play_buttons[-1]._button
    assert new["name"] == "New Playlist" and new["kind"] is None, "New is a blank slate"
    assert opened == [(new["id"], True)], "its page opens with the name box ready"
    monkeypatch.setattr(p, "_ask_new_button", lambda: None)
    p.on_add_button()
    assert names(p)[-1] == "New Playlist", "Cancel adds nothing"
    assert not ui.errors, ui.errors[0]


def test_matching_playlists_go_teal_with_seed_on_playing_now(app, ui):
    import buttons
    p = ui.play
    buttons.load()
    p.seed_var.set("Playing Now")
    p._sync_seed_bars()
    ui.pump(0.2)
    lit = {b._name for b in p.play_buttons if b._accent == p.seed_colour}
    assert lit == {"Similar Artists", "Similar Tracks", "Consensus"}, lit
    assert "Artist + Guests" not in lit, "its first config is Artist's Top Tracks, which never follows Seed (2 Nov 2026)"
    p.seed_var.set("Current Track")
    p._sync_seed_bars()
    assert not [b for b in p.play_buttons if b._accent == p.seed_colour]
    assert not ui.errors, ui.errors[0]


def test_right_click_menu_renames_copies_moves_removes_and_restores(app, ui, monkeypatch):
    import buttons
    import tabs
    p = ui.play
    menus = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda self, *a, **k: menus.append(self))
    opened = []
    monkeypatch.setattr(p, "open_playlist_settings", lambda bid: opened.append(bid))

    def labels(menu):
        return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]

    buttons.restore_standard()   # the fake world starts without the two Top 10s 24bit7 ships (conftest): complete it
    p.refresh_buttons()
    ui.pump(0.3)
    p._button_menu(Click(), p.play_buttons[3]._button)   # Artist + Guests
    menu = menus[-1]
    assert labels(menu) == ["Rename", "Duplicate", "Settings", "Move Left", "Move Right", "Remove from the Play Tab",
                            "Restore Default Playlists"]
    assert menu.entrycget(8, "state") == "disabled", "nothing to restore while everything shipped is there"
    menu.invoke(4)   # Move Left
    assert names(p)[2:4] == ["Artist + Guests", "Artist's Top Tracks"]
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "Star Turn")
    p._button_menu(Click(), p.play_buttons[2]._button)
    menus[-1].invoke(0)   # Rename
    assert names(p)[2] == "Star Turn"
    p._button_menu(Click(), p.play_buttons[2]._button)
    menus[-1].invoke(1)   # Duplicate
    assert names(p)[2:4] == ["Star Turn", "Star Turn 2"] and opened[-1] == p.play_buttons[3]._button["id"]
    assert [c["kind"] for c in p.play_buttons[3]._button["configs"]] == ["artists"], "a copy keeps the configs"
    p._button_menu(Click(), p.play_buttons[0]._button)
    assert menus[-1].entrycget(4, "state") == "disabled", "the first can't move left"
    menus[-1].invoke(2)   # Settings
    assert opened[-1] == p.play_buttons[0]._button["id"]
    menus[-1].invoke(6)   # Remove from the Play Tab: no question, nothing deleted
    assert names(p) == ["Similar Tracks", "Star Turn", "Star Turn 2", "Artist's Top Tracks", "Consensus", "AI Playlist"]
    assert buttons.standard("artists")["shown"] is False and len(buttons.load()) == 9
    p._button_menu(Click(), None)   # right-click on +
    assert labels(menus[-1]) == ["Restore Default Playlists"] and menus[-1].entrycget(0, "state") == "disabled", \
        "off the row isn't missing"
    buttons.remove(buttons.standard("artists")["id"])
    p._button_menu(Click(), None)
    assert menus[-1].entrycget(0, "state") == "normal"
    menus[-1].invoke(0)
    assert names(p)[-1] == "Similar Artists", "the missing standard playlist comes back at the end"
    assert not ui.errors, ui.errors[0]


def test_more_options_switches_are_overrides_and_a_click_always_builds(app, ui, monkeypatch):
    """1 Nov 2026: the live dials went (nothing arms or dims). 2 Nov 2026: Moderator, Deep Cuts and Non-stop are back
    as override switches (overrides.py) beside Seed, Mode and ?; with the bar open, a click still just builds."""
    import buttons
    p = ui.play
    p._end_greeting(keep=False)
    p._show_more(True, save=False)
    ui.pump(0.3)
    kinds = [type(w).__name__ for w in p.extras_row.winfo_children() if w.winfo_manager()]
    assert kinds.count("ClickThrough") == 6, (kinds, "Seed, Mode, Moderator, Deep Cuts, Non-stop and ?")
    assert not hasattr(p, "moderator_cb") and not hasattr(p, "_armed"), "the old dials and arming are gone"
    assert list(p.override_cbs) == ["moderator", "deep_cuts", "nonstop"]
    assert not any(b._dim for b in p.play_buttons), "nothing dimmed with the bar open"
    ran = []
    monkeypatch.setattr(p, "on_button", lambda button: ran.append(button["name"]))
    p.play_buttons[1]._command()
    ui.pump(0.2)
    assert ran == ["Similar Tracks"], "one click builds"
    text = p.log.get("1.0", "end")
    assert "More Options Open: any settings set here override" in text, "opening the bar said what the switches do"
    assert "showing" not in text and "armed" not in text, "and nothing about arming"
    p._show_more(False, save=False)
    assert not ui.errors, ui.errors[0]


def test_a_click_runs_that_button(app, ui, monkeypatch):
    import buttons
    p = ui.play
    ran = []
    monkeypatch.setattr(buttons, "run", lambda button, **kw: ran.append((button["name"], kw["seed_info"]["Artist"])))
    p.seed_nb.select(p.search_tab)
    ui.pump(0.2)
    p.search_artist.insert(0, "The Beatles")
    p.play_buttons[3]._command()   # Artist + Guests, from the typed seed
    ui.wait_idle()
    assert ran == [("Artist + Guests", "The Beatles")]
    p.play_buttons[1]._command()   # Similar Tracks needs the track too
    ui.wait_idle()
    assert len(ran) == 1 and ui.answers[-1][1][0] == "Search", ui.answers
    p.play_buttons[2]._command()   # Artist's Top Tracks: the artist is enough
    ui.wait_idle()
    assert ran[-1] == ("Artist's Top Tracks", "The Beatles")
    assert not ui.errors, ui.errors[0]


def test_enter_on_search_runs_the_standard_similar_artists(app, ui, monkeypatch):
    import buttons
    p = ui.play
    ran = []
    monkeypatch.setattr(buttons, "run", lambda button, **kw: ran.append(button["name"]))
    p.seed_nb.select(p.search_tab)
    p.search_artist.insert(0, "The Beatles")
    p.on_similar()
    ui.wait_idle()
    assert ran == ["Similar Artists"]
    buttons.remove(buttons.standard("artists")["id"])
    p.refresh_buttons()
    p.on_similar()
    ui.wait_idle()
    assert ran == ["Similar Artists", "Consensus"], "with the standard gone, the next Artist Matching playlist stands in"
    buttons.remove(buttons.standard("artists")["id"])
    p.refresh_buttons()
    p.on_similar()
    assert len(ran) == 2 and ui.answers[-1][1][0] == "No Playlist", ui.answers


def test_ai_buttons_grey_out_together(app, ui):
    import buttons
    p = ui.play
    buttons.add("Late Night", "vibe")
    p.refresh_buttons()
    app.set_env(ANTHROPIC_API_KEY="sk-test")
    app.engine.load_settings()
    p.sync_moderator()
    ai = [b for b in p.play_buttons if b._kind == "vibe"]
    assert len(ai) == 2 and all(b.cget("state") == "normal" for b in ai)
    app.set_env(ANTHROPIC_API_KEY="")
    app.engine.load_settings()
    p.sync_moderator()
    assert all(b.cget("state") == "disabled" for b in ai)
    assert all(b._ai_tip.when() for b in ai), "why they're greyed out shows with ? off"
    assert "Similar Artists" not in [b._name for b in ai]


def test_buttons_wrap_when_the_window_is_narrow(app, ui, monkeypatch):
    p = ui.play
    ui.pump(0.3)
    width = p.play_buttons[0]._size[0]
    monkeypatch.setattr(p.button_row, "winfo_width", lambda: 3 * (width + 8) + 2 * 16)   # room for three
    p._flow_buttons()
    ui.pump(0.3)
    row = p.play_buttons + [p.more_button, p.add_button]
    ys = sorted({b.winfo_y() for b in row})
    assert len(ys) == 3, ys   # three, three, then + on its own
    assert [b.winfo_y() for b in row[:3]] == [ys[0]] * 3 and row[-1].winfo_y() == ys[-1]
    assert p.button_row.winfo_height() >= ys[-1] + p.add_button._size[1], "the row grows to fit"
