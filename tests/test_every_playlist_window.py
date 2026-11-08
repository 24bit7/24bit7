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


def test_skipped_tracks_lists_whats_left_out_and_lets_it_back_in(app, ui):
    import filters
    import library
    from tkinter import ttk  # noqa: F401
    j = app.jriver
    beatles = [r["Key"] for r in j.tracks if r["Artist"] == "The Beatles"][:3]
    other = next(r for r in j.tracks if r["Artist"] != "The Beatles")
    for k in beatles:
        j.by_key[k]["24bit7 Voice Skips"] = "2"
    j.by_key[other["Key"]]["24bit7 Voice Skips"] = "3"
    library.load()
    s = ui.settings
    win = s._open_filters()
    ui.pump(0.3)
    s._filter_i = [x["name"] for x in s._filters].index("Skipped Tracks")
    s._filter_fill_editor()
    ui.pump(0.2)
    texts = labels(win)
    assert "The Beatles, every track (3 tracks left out)" in texts, texts
    line = f"{other['Artist']} - {other['Name']}, skipped 3 times"
    assert line in texts
    import tkinter as tk
    button = next(w for w in walk(win) if isinstance(w, tk.Button) and w.cget("text") == "Let Back In"
                  and w.grid_info().get("row") == next(x for x in walk(win) if isinstance(x, tk.Label)
                                                        and x.cget("text") == line).grid_info()["row"])
    button.invoke()
    ui.pump(0.3)
    assert j.by_key[other["Key"]]["24bit7 Voice Skips"] == "" and line not in labels(win)
    artist_button = next(w for w in walk(win) if isinstance(w, tk.Button) and w.cget("text") == "Let Back In")
    artist_button.invoke()
    ui.pump(0.3)
    assert all(j.by_key[k]["24bit7 Voice Skips"] == "" for k in beatles)
    assert "Nothing yet: no track has been skipped by voice 2 times." in labels(win)
    win.destroy()
    assert not ui.errors, ui.errors[0]


def test_skipped_tracks_numbers_are_set_on_its_page_and_left_out_now_follows(app, ui):
    """Ben, 8 Nov 2026: the two numbers in boxes, saved as typed, Left Out Now redrawn to match."""
    import filters
    import library
    j = app.jriver
    other = next(r for r in j.tracks if r["Artist"] != "The Beatles")
    j.by_key[other["Key"]]["24bit7 Voice Skips"] = "2"
    library.load()
    s = ui.settings
    win = s._open_filters()
    ui.pump(0.3)
    s._filter_i = [x["name"] for x in s._filters].index("Skipped Tracks")
    s._filter_fill_editor()
    ui.pump(0.2)
    texts = labels(win)
    assert "Leave out a track skipped by voice" in texts and "tracks left out." in texts, texts
    line = f"{other['Artist']} - {other['Name']}, skipped 2 times"
    assert line in texts
    track_box = s._skip_boxes["track_skips"]
    assert track_box.get() == "2" and s._skip_boxes["artist_skips"].get() == "3"
    track_box.set("3")
    ui.pump(0.3)
    assert filters.skip_limits() == (3, 3), "saved as typed"
    texts = labels(win)
    assert line not in texts and "Nothing yet: no track has been skipped by voice 3 times." in texts, texts
    assert texts.count("Left Out Now") == 1, "the old section went"
    win.destroy()
    assert not ui.errors, ui.errors[0]
