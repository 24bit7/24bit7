"""
Edit Pillars (Ben, 7 Nov 2026): Edit on a station's row opens a window with the station's pillars (search,
Remove) and every artist in your library (search, + Add, how many tracks you own, the pillars greyed), Restore
Pillars and Close. The row's grey list of pillars follows each change.
"""

from tkinter import ttk  # noqa: F401

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button
from test_radio import EVERYONE, play_counts
from test_radio_page import lowered, made_radio  # noqa: F401  (the fixture)


def row_texts(s, lane_id):
    ids = [i for i, _e in s._radio_station_rows]
    table = s._radio_station_rows[ids.index(lane_id)][1].master.master
    r = ids.index(lane_id)
    return [w.cget("text") for w in table.grid_slaves(row=r) if hasattr(w, "cget") and "text" in w.keys()]


def test_edit_pillars_window(app, ui, lowered):
    radio = lowered
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    made_radio()
    pick_button(ui, "Radio")
    s = ui.settings
    first = radio.lanes()[0]
    assert "Edit" in row_texts(s, first["id"])
    edit = next(w for w in s._radio_station_rows[0][1].master.master.grid_slaves(row=0, column=5))
    edit.invoke()
    ui.pump(0.5)
    win = s._pillars_window
    assert win.winfo_exists()
    assert win.pillar_head.cget("text") == f"Pillars ({len(first['pillars'])})"
    assert win.left["items"] == first["pillars"]
    assert "Various Artists" not in win.right["items"], "compilations aren't offered"
    gone = first["pillars"][0]
    win.left["list"].selection_set(0)
    win.remove()
    ui.pump(0.2)
    assert gone not in radio.lane(first["id"])["pillars"]
    assert win.message.cget("text") == f"{gone} is no longer a pillar of {first['name']} or its halves."
    assert gone not in " ".join(row_texts(s, first["id"])), "the row follows"
    # search the library and add
    win.right["search"].entry.insert(0, "guetta")
    win.refresh()
    assert win.right["items"] == ["David Guetta"]
    assert "few tracks" in win.right["list"].get(0), "one track owned"
    win.right["search"].entry.focus_force()
    ui.pump(0.1)
    win.event_generate("<Return>")   # Enter adds the only artist found, and doesn't close
    ui.pump(0.2)
    assert win.winfo_exists()
    assert "David Guetta" in radio.lane(first["id"])["pillars"]
    win.left["search"].entry.insert(0, "guetta")
    win.refresh()
    assert win.left["list"].get(0).endswith("added by you")
    win.restore()
    ui.pump(0.2)
    assert radio.lane(first["id"])["pillars"][0] == gone and "David Guetta" not in radio.lane(first["id"])["pillars"]
    win.ok()
    ui.pump(0.2)
    assert not win.winfo_exists()
    assert not ui.errors, ui.errors[0]
