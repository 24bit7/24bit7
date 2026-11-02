"""
The Consensus section offers its fallback (Ben, 2 Nov 2026): "If Consensus finds fewer than [10] tracks, finish the
playlist with plain Artist Matching". The tick and the number save to the playlist's settings, the number box is greyed
until the tick is on, and both grey out with Consensus off.
"""

from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk, labels


def test_fallback_tick_and_number_save_and_grey(app, ui):
    import buttons
    p = pick_button(ui, "Similar Artists")
    s = ui.settings
    page = s._button_inner
    assert "tracks, finish the playlist with plain Artist Matching" in labels(page)
    tick = next(w for w in walk(page) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "If Consensus finds fewer than")
    assert tick.instate(["disabled"]), "greyed while Consensus is off"
    on = next(w for w in walk(page) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "Consensus")
    on.invoke()   # Consensus on: the fallback can be set
    ui.pump(0.2)
    tick.invoke()   # ticks it, saves
    ui.pump(0.3)
    p.vars["INNER_CIRCLE_ARTISTS_FALLBACK_MIN"].set("25")
    ui.pump(0.3)
    saved = buttons.standard("artists")["settings"]
    assert saved["INNER_CIRCLE_ARTISTS_FALLBACK"] == "1" and saved["INNER_CIRCLE_ARTISTS_FALLBACK_MIN"] == "25"
    sb = next(w for w in walk(page) if w.winfo_class() == "Spinbox" and str(w.cget("textvariable")) == str(p.vars["INNER_CIRCLE_ARTISTS_FALLBACK_MIN"]))
    assert str(sb.cget("state")) == "normal"
    tick.invoke()   # off again: the number box greys
    ui.pump(0.3)
    assert str(sb.cget("state")) == "disabled"
    assert buttons.standard("artists")["settings"]["INNER_CIRCLE_ARTISTS_FALLBACK"] == "0"
    on.invoke()   # Consensus off again
    ui.pump(0.3)
    assert tick.instate(["disabled"]), "greyed with Consensus off"
    assert not ui.errors, ui.errors[0]
