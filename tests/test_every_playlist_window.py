"""
Edit Filters with Every playlist (Ben, 5 Nov 2026): a tick beside On; Skipped Tracks shows what it leaves out
in place of rules and can't be deleted; a playlist's own ticks show an Every playlist filter ticked and greyed.
"""

from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk, labels


def checks(widget):
    return {w.cget("text"): w for w in walk(widget) if isinstance(w, ttk.Checkbutton)}


def test_every_playlist_tick_and_skipped_tracks_in_edit_filters(app, ui, monkeypatch):
    import filters
    from tkinter import messagebox
    f = filters.blank("Stereo")
    filters.save(filters.load() + [f])
    pick_button(ui, "Artist + Guests")
    s = ui.settings
    win = s._open_filters()
    ui.pump(0.4)
    names = [x["name"] for x in s._filters]
    s._filter_i = names.index("Skipped Tracks")
    s._filter_fill_editor()
    ui.pump(0.2)
    texts = labels(win)
    assert "What It Leaves Out" in texts and "Rules" not in texts and "Only pick from" not in texts
    assert "Used by: Every playlist" in texts
    told = []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: told.append(a[1]))
    s._filter_delete()
    assert told and "Skipped Tracks" in [x["name"] for x in filters.load()], "it stays"
    s._filter_i = names.index("Stereo")
    s._filter_fill_editor()
    ui.pump(0.2)
    checks(win)["Every playlist"].invoke()
    ui.pump(0.3)
    assert next(x for x in filters.load() if x["id"] == f["id"])["every"] is True
    assert "Used by: Every playlist" in labels(win)
    win.destroy()
    ui.pump(0.3)
    row = checks(s._button_filter_row)
    assert row["Stereo   (every playlist)"].instate(["disabled", "selected"]), row.keys()
    assert not ui.errors, ui.errors[0]
