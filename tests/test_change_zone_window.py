"""
Change Zone on the Now Playing row, on screen (Ben, 23 Nov 2026): beside Stop and Skip Track, greyed while the
zone is stopped; its pop-up "Move From Speakers" lists To and When, moves the music, and the row follows it.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)


def prompt_in(ui):
    import gui
    return next((w for w in ui.root.winfo_children() if isinstance(w, gui.ChangeZonePrompt)), None)


def test_change_zone_moves_the_music_and_the_row_follows(app, ui):
    j = app.jriver
    p = ui.play
    p._end_greeting()   # while the greeting types, lines wait for it
    p._sync_np_controls({"State": "0", "PlayingNowTracks": "0"})
    assert p.change_button._state == "disabled", "greyed while the zone is stopped"
    keys = j.playlists[1]["keys"]
    j.play("Speakers", keys, pos=2)
    p.zone_var.set("Speakers")
    p._sync_np_controls({"State": "2", "PlayingNowTracks": str(len(keys)), "NextFileKey": keys[3]})
    assert p.change_button._state == "normal"
    seen = {}

    def answer():
        win = prompt_in(ui)
        if win is None:
            p.after(100, answer)
            return
        seen["title"] = win.title()
        seen["to"] = [w.cget("text") for w in win.winfo_children()[0].winfo_children()[-1].winfo_children()
                      if w.winfo_class() == "TRadiobutton"]
        win.to_var.set("Kitchen")
        win.when_var.set("restart")
        win.ok()
    p.after(200, answer)
    p._change_zone_clicked()
    ui.pump(until=lambda: j.zone("Kitchen").state == 2 and p.zone_var.get() == "Kitchen", timeout=10)
    assert seen["title"] == "Move From Speakers"
    assert "Kitchen" in seen["to"] and "Speakers" not in seen["to"], seen
    assert "Restart This Track" in seen["to"] and "From the Next Track" in seen["to"], seen
    k = j.zone("Kitchen")
    assert k.playlist == list(keys) and k.pos == 2 and j.zone("Speakers").state == 0
    assert p.zone_var.get() == "Kitchen", "the row shows where the music went"
    ui.pump(0.5)
    assert "Moved from Speakers to Kitchen." in p.log.get("1.0", "end")
    assert not ui.errors, ui.errors[0]


import pytest


@pytest.fixture
def in_german(app):
    import i18n
    i18n.set_language("de")   # before the window is built, as test_gui's German tests do
    yield
    i18n.set_language("en")


def test_the_rows_buttons_fit_their_german(app, in_german, ui):
    """23 Nov 2026: "Titel überspringen" ran over Skip Track's edge, and "Zone wechseln" would have too."""
    import tkinter.font as tkfont
    p = ui.play
    assert p.skip_button._label.cget("text") == "Titel überspringen", "the window is in German"
    import i18n
    for b, texts in ((p.stop_button, ("Stop", "Clear Playing Now")), (p.skip_button, ("Skip Track",)),
                     (p.change_button, ("Change Zone",))):
        font = tkfont.Font(font=b._label.cget("font"))
        for text in map(i18n.t, texts):   # Stop's other face too
            assert b._size[0] >= font.measure(text) + 8, (text, b._size[0], font.measure(text))
    assert not ui.errors, ui.errors[0]


def test_cancel_moves_nothing(app, ui):
    j = app.jriver
    p = ui.play
    keys = j.playlists[1]["keys"]
    j.play("Speakers", keys, pos=1)
    p.zone_var.set("Speakers")
    p.after(300, lambda: prompt_in(ui).cancel())
    p._change_zone_clicked()
    ui.pump(0.5)
    assert j.zone("Speakers").state == 2 and j.zone("Kitchen").state == 0
    assert not ui.errors, ui.errors[0]
