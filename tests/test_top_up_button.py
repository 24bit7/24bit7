"""
The Top-Up button on the More Options row (Ben, 5 Nov 2026). A click arms it: a teal edge and teal text (the
Seed colour, the knock-on colour) and a line saying what happens next. A click on any playlist lets go of it
and runs that playlist as a Top-Up; clicking Top-Up again first cancels it and the line goes. Greyed while
Output is YouTube or Tidal, and let go of when the row closes.
"""

from test_gui import ui, console  # noqa: F401  (the GUI fixture)


def open_row(ui):
    p = ui.play
    p._end_greeting(keep=False)
    p._show_more(True)
    ui.pump(0.3)
    return p


def test_a_click_arms_it_in_teal_and_another_cancels(app, ui):
    p = open_row(ui)
    b = p.top_up_button
    assert b.master is p.extras_row and b.cget("text") == "Top-Up"
    assert not p.top_up_armed and b._armed is None
    b._command()
    ui.pump(0.2)
    assert p.top_up_armed and b._armed == p.seed_colour, "teal, as Seed's Playing Now"
    assert "Top-Up is on: the next playlist you click" in console(ui)
    b._command()
    ui.pump(0.2)
    assert not p.top_up_armed and b._armed is None
    assert "Top-Up is on" not in console(ui), "cancelled: the line goes"
    assert not ui.errors, ui.errors[0]


def test_a_playlist_click_lets_go_and_runs_as_a_top_up(app, ui):
    j = app.jriver
    keys = [r["Key"] for r in j.tracks if r["Artist"] == "The Beatles"][:3]   # the first is the seed
    j.play("Speakers", keys, pos=0)
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    p = open_row(ui)
    p.top_up_button._command()
    ui.pump(0.2)
    p.on_similar()
    ui.pump(0.2)
    assert not p.top_up_armed, "let go of as the build starts"
    ui.wait_idle()
    z = j.zone("Speakers")
    assert z.playlist[0] == keys[0] and set(keys[1:]) <= set(z.playlist), "the rest stayed, shuffled in"
    assert len(z.playlist) > len(keys) and len(z.playlist) == len(set(z.playlist))
    assert "Top-Up:" in console(ui), console(ui)
    assert not app.engine.TOP_UP, "one playlist only"
    p.on_similar()
    ui.wait_idle()
    assert "Top-Up:" not in console(ui), "the next build is an ordinary one"
    assert not ui.errors, ui.errors[0]


def test_greyed_for_youtube_and_let_go_when_the_row_closes(app, ui):
    p = open_row(ui)
    p.top_up_button._command()
    p.output_var.set("YouTube")
    p._sync_top_up()
    ui.pump(0.2)
    assert not p.top_up_armed and p.top_up_button.cget("state") == "disabled"
    p.output_var.set(p.output_cb.cget("values")[0])
    p._sync_top_up()
    assert p.top_up_button.cget("state") == "normal"
    p.top_up_button._command()
    p._show_more(False)
    ui.pump(0.2)
    assert not p.top_up_armed, "it's on the row: closing the row lets go of it"
    assert not ui.errors, ui.errors[0]
