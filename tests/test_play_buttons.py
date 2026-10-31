"""
The Play tab draws its buttons from the button list (stage two, 31 Oct 2026): + adds one, right-click
renames, moves or removes one, a click runs that button's settings, the notes say what each has on,
and the row wraps when the window is narrow.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


def names(p):
    return [b._name for b in p.play_buttons]


class Click:
    x_root = y_root = 0


def test_row_comes_from_the_button_list_then_more_options_and_plus(app, ui):
    p = ui.play
    assert names(p) == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Headliner", "AI Playlist"]
    ui.pump(0.3)
    row = p.play_buttons + [p.more_button, p.add_button]
    xs = [b.winfo_x() for b in row]
    assert xs == sorted(xs) and len(set(xs)) == len(xs), xs
    assert len({b.winfo_y() for b in row}) == 1, "one row at 1400 wide"
    assert p.add_button.cget("text") == "+"
    assert p.buttons[-1] is p.credits_button, "Show Credits still greys out with the rest"


def test_plus_adds_a_button_starting_from_one_of_its_kind(app, ui, monkeypatch):
    import buttons
    p = ui.play
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    monkeypatch.setattr(p, "_ask_new_button", lambda: ("Sunday Guests", "top", head["id"]))
    p.on_add_button()
    assert names(p)[-1] == "Sunday Guests"
    new = p.play_buttons[-1]._button
    assert new["kind"] == "top" and new["settings"]["TOP_GUESTS"] == "third"
    assert p.play_buttons[-1]._tooltip.text.endswith("Artist's Top Tracks, Guests"), "its note says what's on"
    monkeypatch.setattr(p, "_ask_new_button", lambda: None)
    p.on_add_button()
    assert names(p)[-1] == "Sunday Guests", "Cancel adds nothing"


def test_right_click_menu_moves_renames_removes_and_restores(app, ui, monkeypatch):
    import tabs
    from tkinter import messagebox
    p = ui.play
    menus = []
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda self, *a, **k: menus.append(self))

    def labels(menu):
        return [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]

    p._button_menu(Click(), p.play_buttons[3]._button)   # Headliner
    menu = menus[-1]
    assert labels(menu) == ["Rename", "Move Left", "Move Right", "Remove", "Restore Default Buttons"]
    assert menu.entrycget(5, "state") == "disabled", "nothing to restore while the four are there"
    menu.invoke(1)   # Move Left
    assert names(p)[2:4] == ["Headliner", "Artist's Top Tracks"]
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "Star Turn")
    p._button_menu(Click(), p.play_buttons[2]._button)
    menus[-1].invoke(0)   # Rename
    assert names(p)[2] == "Star Turn"
    p._button_menu(Click(), p.play_buttons[0]._button)
    assert menus[-1].entrycget(1, "state") == "disabled", "the first can't move left"
    menus[-1].invoke(3)   # Remove: the question answered No by the fixture
    assert names(p)[0] == "Similar Artists"
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    p._button_menu(Click(), p.play_buttons[0]._button)
    menus[-1].invoke(3)
    assert names(p) == ["Similar Tracks", "Star Turn", "Artist's Top Tracks", "AI Playlist"]
    p._button_menu(Click(), None)   # right-click on +
    assert labels(menus[-1]) == ["Restore Default Buttons"] and menus[-1].entrycget(0, "state") == "normal"
    menus[-1].invoke(0)
    assert names(p)[-1] == "Similar Artists", "the missing standard button comes back at the end"
    assert not ui.errors, ui.errors[0]


def test_a_click_runs_that_button(app, ui, monkeypatch):
    import buttons
    p = ui.play
    ran = []
    monkeypatch.setattr(buttons, "run", lambda button, **kw: ran.append((button["name"], kw["seed_info"]["Artist"])))
    p.seed_nb.select(p.search_tab)
    ui.pump(0.2)
    p.search_artist.insert(0, "The Beatles")
    p.play_buttons[3]._command()   # Headliner, from the typed seed
    ui.wait_idle()
    assert ran == [("Headliner", "The Beatles")]
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
    assert len(ran) == 1 and ui.answers[-1][1][0] == "No Button", ui.answers


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
