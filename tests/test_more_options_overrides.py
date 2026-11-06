"""
The More Options row's three switches on the Play tab (Ben, 2 Nov 2026): Moderator, Deep Cuts and
Non-stop, Off or On, lit when On. Opening the row drops a note saying they override every playlist's
own settings while it's open; closing by hand clears the notices and keeps the build. With the row open, dragging a
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
    assert cbs["deep_cuts"].get() == "Spaced" and overrides.switches()["deep_cuts"] == "spaced"
    assert "Deep Cuts Spaced" not in log(p), "a click says nothing: the opening line already did (Ben, 2 Nov)"
    cbs["deep_cuts"]._step(1)
    cbs["deep_cuts"]._step(1)
    ui.pump(0.2)
    assert cbs["deep_cuts"].get() == "Off" and overrides.switches()["deep_cuts"] == "off", "Spaced, Shuffled, round to Off"
    assert log(p).count("Note:") == 0, "still nothing"
    assert cbs["moderator"]._values == ["Off", "Relaxed", "Balanced", "Strict"], "the 1.28 click-through"
    assert cbs["nonstop"]._values == ["Off", "Keep It Tight", "Wander"]
    import tabs
    assert cbs["moderator"]._lit == {v: tabs.PALETTE["ai_purple"] for v in ("Relaxed", "Balanced", "Strict")}, \
        "the Moderator spends AI credits: magenta at any level"
    p._show_more(False)
    assert not ui.errors, ui.errors[0]


def test_opening_the_row_says_one_line_and_the_first_time_a_dialog_too(app, ui, monkeypatch):
    """Ben, 2 Nov 2026: the long note went unread. One short line each time the row opens, nothing on closing,
    and the first time it's opened by hand a dialog says it properly. Start-up restoring an open row: the line only."""
    import gui
    import overrides
    p = ui.play
    p._end_greeting(keep=False)
    shown = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, text, **kw: shown.append((title, text)))
    overrides.set_switches({"moderator": "off", "deep_cuts": "spaced", "nonstop": "off"})
    line = ("More Options Open: any settings set here override your playlists' own settings. The override ends when "
            "More Options closes.")
    assert overrides.told() is False
    p._show_more(True)
    ui.pump(0.3)
    assert log(p).count(line) == 1
    assert p.override_cbs["deep_cuts"].get() == "Spaced", "the switches read what's saved when the row opens"
    assert len(shown) == 1 and shown[0][0] == "More Options" and shown[0][1].startswith(line), "the one-off dialog"
    assert "Use Its Settings" in shown[0][1] and overrides.told() is True
    p._show_more(False)
    ui.pump(0.3)
    assert "closed" not in log(p), "nothing said on closing: the line already said when the override ends"
    assert log(p).count(line) == 0, "closing by hand takes the line away (Ben, 6 Nov 2026)"
    p._show_more(True)
    ui.pump(0.3)
    assert log(p).count(line) == 1 and len(shown) == 1, "the line again, once, the dialog never again"
    p._show_more(False)
    p._show_more(True, save=False)   # as start-up restores a row left open
    ui.pump(0.3)
    assert log(p).count(line) == 1 and len(shown) == 1, "the line at start-up too, never the dialog"
    p._show_more(False, save=False)
    assert not ui.errors, ui.errors[0]


def test_the_third_pill_shows_only_with_the_row_open_and_sets_the_switches_from_a_drop(app, ui):
    import buttons
    import overrides
    p = ui.play
    p._end_greeting(keep=False)
    buttons.load()
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="balanced", DEEP_CUTS_ARTISTS="off",
                                             NONSTOP_ARTISTS="1", NONSTOP_ARTISTS_MODE="tight"))
    overrides.set_switches({"moderator": "off", "deep_cuts": "spaced", "nonstop": "off"})
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
    assert overrides.switches() == {"moderator": "balanced", "deep_cuts": "off", "nonstop": "tight"}, "as its page has them"
    assert {k: cb.get() for k, cb in p.override_cbs.items()} == {"moderator": "Balanced", "deep_cuts": "Off",
                                                                  "nonstop": "Keep It Tight"}
    assert "Note: More Options set from Similar Artists: Moderator Balanced, Deep Cuts Off, Non-stop Keep It Tight." in log(p)
    assert [b._name for b in p.play_buttons][0] == "Similar Artists", "the row is as it was"
    p._show_more(False)
    assert not ui.errors, ui.errors[0]


def test_closing_the_row_takes_the_notices_away_and_keeps_the_build(app, ui):
    """Ben, 6 Nov 2026: four opens and closes left four copies of the More Options line. Closing the row by
    hand now clears every notice (the More Options line, the orange notes) and leaves a build's own lines."""
    p = ui.play
    p._end_greeting(keep=False)
    p._show_more(True)
    ui.pump(0.3)
    p._append_log("Similar Artists (Seed: Joe Satriani - Ice 9)")
    p._append_log("  Note: two tracks were left out, as they were played today.")
    p._notice("Note: the next build is 24bit7's tracks only.")
    ui.pump(0.2)
    assert "More Options Open" in log(p) and "24bit7's tracks only" in log(p)
    p._show_more(False)
    ui.pump(0.3)
    text = log(p)
    assert "More Options Open" not in text and "24bit7's tracks only" not in text, "the notices go"
    assert "Similar Artists (Seed: Joe Satriani - Ice 9)" in text, "the build stays"
    assert "two tracks were left out" in text, "a note that's part of a build stays too"
    assert not any("More Options Open" in x or "tracks only" in x for x in p._live), "gone from the kept lines too"
    assert any("Joe Satriani" in x for x in p._live)
    for _ in range(3):
        p._show_more(True)
        ui.pump(0.2)
        p._show_more(False)
        ui.pump(0.2)
    assert "More Options Open" not in log(p), "no pile of lines however often it's opened and closed"
    assert not ui.errors, ui.errors[0]
