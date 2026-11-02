"""
The More Options row's three switches on the Play tab (Ben, 2 Nov 2026): Moderator, Deep Cuts and
Non-stop, Off or On, lit when On. Opening the row drops a note saying they override every playlist's
own settings while it's open; closing says the pages decide again. With the row open, dragging a
playlist shows a third pill, Use Its Settings, which sets the switches from that playlist's page.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


class At:
    def __init__(self, x, y):
        self.x_root, self.y_root = x, y


def middle(widget):
    return widget.winfo_rootx() + widget.winfo_width() // 2, widget.winfo_rooty() + widget.winfo_height() // 2


def log(p):
    return p.log.get("1.0", "end")


def test_the_three_switches_start_off_and_a_click_saves_and_says(app, ui):
    import overrides
    p = ui.play
    p._end_greeting(keep=False)
    cbs = p.override_cbs
    assert list(cbs) == ["moderator", "deep_cuts", "nonstop"]
    assert all(cb.get() == "Off" for cb in cbs.values()), "a fresh install: all off"
    assert all(cb.master is p.extras_row for cb in cbs.values()), "on the More Options row"
    assert cbs["nonstop"]._symbol and cbs["nonstop"]._prefix == "∞", "Non-stop as the infinity sign, as in 1.28"
    p._show_more(True)
    ui.pump(0.3)
    cbs["deep_cuts"]._step(1)
    ui.pump(0.2)
    assert cbs["deep_cuts"].get() == "On" and overrides.switches()["deep_cuts"] is True
    assert "Deep Cuts on for every build while this row is open." in log(p)
    cbs["deep_cuts"]._step(1)
    ui.pump(0.2)
    assert cbs["deep_cuts"].get() == "Off" and overrides.switches()["deep_cuts"] is False
    assert "Deep Cuts off for every build while this row is open." in log(p)
    import tabs
    assert cbs["moderator"]._lit == {"On": tabs.PALETTE["ai_purple"]}, "the Moderator spends AI credits: magenta"
    p._show_more(False)
    assert not ui.errors, ui.errors[0]


def test_opening_the_row_says_it_overrides_and_closing_says_the_pages_decide(app, ui):
    import overrides
    p = ui.play
    p._end_greeting(keep=False)
    overrides.set_switches({"moderator": False, "deep_cuts": True, "nonstop": False})
    p._show_more(True)
    ui.pump(0.3)
    assert ("Note: Moderator, Deep Cuts and Non-stop here override every playlist's own settings while this row is "
            "open (Moderator off, Deep Cuts on, Non-stop off). Close the row and the playlists' pages decide again.") in log(p)
    assert p.override_cbs["deep_cuts"].get() == "On", "the switches read what's saved when the row opens"
    p._show_more(False)
    ui.pump(0.3)
    assert "Note: More Options closed. Each playlist's own settings decide again." in log(p)
    before = log(p)
    p._show_more(True, save=False)   # as start-up restores a row left open: said then too
    ui.pump(0.3)
    assert log(p).count("override every playlist's own settings") == before.count("override every playlist's own settings") + 1
    p._show_more(False, save=False)
    ui.pump(0.3)
    assert log(p).count("More Options closed") == 1, "start-up restoring a closed row says nothing"
    assert not ui.errors, ui.errors[0]


def test_the_third_pill_shows_only_with_the_row_open_and_sets_the_switches_from_a_drop(app, ui):
    import buttons
    import overrides
    p = ui.play
    p._end_greeting(keep=False)
    buttons.load()
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="balanced", DEEP_CUTS_ARTISTS="off",
                                             NONSTOP_ARTISTS="1"))
    overrides.set_switches({"moderator": False, "deep_cuts": True, "nonstop": False})
    p.refresh_buttons()
    ui.pump(0.3)
    fb = p.play_buttons[0]
    assert fb._name == "Similar Artists"
    # row closed: two pills
    p._show_more(False)
    x, y = middle(fb)
    p._drag_start(At(x, y), fb)
    p._drag_move(At(x + 40, y), fb)
    ui.pump(0.3)
    assert list(p._targets) == ["settings", "remove"]
    p._drag_end(At(x + 40, y), fb)
    ui.pump(0.3)
    # row open: a third
    p._show_more(True)
    ui.pump(0.3)
    fb = p.play_buttons[0]   # the row is redrawn after a drop
    x, y = middle(fb)
    p._drag_start(At(x, y), fb)
    p._drag_move(At(x + 40, y), fb)
    ui.pump(0.3)
    assert list(p._targets) == ["settings", "remove", "use"]
    use = p._targets["use"][1]
    assert use._colour == p.seed_colour and "Use Its Settings" in use._text
    ux, uy = middle(use)
    p._drag_move(At(ux, uy), fb)
    ui.pump(0.2)
    assert use.lit is True
    p._drag_end(At(ux, uy), fb)
    ui.pump(0.3)
    assert overrides.switches() == {"moderator": True, "deep_cuts": False, "nonstop": True}, "as its page has them"
    assert {k: cb.get() for k, cb in p.override_cbs.items()} == {"moderator": "On", "deep_cuts": "Off", "nonstop": "On"}
    assert "Note: More Options set from Similar Artists: Moderator on, Deep Cuts off, Non-stop on." in log(p)
    assert [b._name for b in p.play_buttons][0] == "Similar Artists", "the row is as it was"
    p._show_more(False)
    assert not ui.errors, ui.errors[0]
