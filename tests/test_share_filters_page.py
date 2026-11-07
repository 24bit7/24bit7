"""
Edit Filters for At least (Ben, 7 Nov 2026): What It Does with Leave out or At least [20]%, an Other field rule
whose name box reads the field into the library and whose value box lists the values in your library, a line
under it saying how many tracks have one or that JRiver has no such field, and the playlist page's tick naming
the share.
"""

from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk, labels


def radios(widget):
    return {w.cget("text"): w for w in walk(widget) if isinstance(w, ttk.Radiobutton)}


def test_what_it_does_and_an_other_field_rule(app, ui):
    import filters
    for row in app.jriver.tracks:
        if row["Album Artist (auto)"] == "Sigur Rós":
            row["Country"] = "New Zealand"
    f = filters.blank("Kiwi Music")
    filters.save(filters.load() + [f])
    pick_button(ui, "Similar Artists")
    s = ui.settings
    buttons_mod = __import__("buttons")
    buttons_mod.set_filters(buttons_mod.standard("artists")["id"], [f["id"]])
    win = s._open_filters()
    ui.pump(0.4)
    s._filter_i = [x["name"] for x in s._filters].index("Kiwi Music")
    s._filter_fill_editor()
    ui.pump(0.3)
    assert "What It Does" in labels(win)
    assert str(s._filter_share_box.cget("state")) == "disabled", "Leave out to start: the share box greyed"
    radios(win)["At least"].invoke()
    ui.pump(0.2)
    saved = next(x for x in filters.load() if x["id"] == f["id"])
    assert saved["mode"] == "least" and filters.share_of(saved) == 20
    assert str(s._filter_share_box.cget("state")) == "normal"
    s._filter_share_box.set("25")
    ui.pump(0.2)
    assert filters.share_of(next(x for x in filters.load() if x["id"] == f["id"])) == 25
    # an Other field rule: the name, read into the library once typed; its values listed; the line under it
    s._filters[s._filter_i]["rules"] = [filters.blank_rule("other")]
    s._filter_save()
    s._filter_fill_editor()
    ui.pump(0.3)
    entry = next(w for w in walk(win) if isinstance(w, ttk.Entry)
                 and not isinstance(w, (ttk.Combobox, ttk.Spinbox)) and w.winfo_ismapped())   # the field's name
    entry.focus_force()
    entry.delete(0, "end")
    entry.insert(0, "country")   # as typed: JRiver's spelling is used
    entry.event_generate("<Return>")
    ui.pump(1.0)
    rule = next(x for x in filters.load() if x["id"] == f["id"])["rules"][0]
    assert rule["name"] == "Country", rule
    assert "Country: 3 tracks by 1 artist have a value. The list holds the values in your library." in labels(win), \
        labels(win)
    box = next(w for w in walk(win) if isinstance(w, ttk.Combobox) and "New Zealand" in w.cget("values"))
    box.set("New Zealand")
    ui.pump(0.2)
    assert next(x for x in filters.load() if x["id"] == f["id"])["rules"][0]["value"] == "New Zealand"
    # a rule saved before the library copy read its field: the page reads it again and the line follows
    import library
    for row in app.jriver.tracks:
        if row["Album Artist (auto)"] == "Pink Floyd":
            row["Mood"] = "Calm"
    items = filters.load()
    rule_f = filters.blank("Calm")
    rule_f["rules"] = [{"field": "other", "name": "Mood", "op": "is", "value": "Calm", "value2": ""}]
    filters.save(items + [rule_f])
    assert not library.has_fields(["Mood"])
    s._filters = filters.load()
    s._filter_i = [x["name"] for x in s._filters].index("Calm")
    s._filter_fill_editor()
    ui.pump(1.5)
    assert library.has_fields(["Mood"])
    assert "Mood: 4 tracks by 1 artist have a value. The list holds the values in your library." in labels(win), \
        labels(win)
    s._filter_i = [x["name"] for x in s._filters].index("Kiwi Music")
    # a name JRiver doesn't have
    s._filters[s._filter_i]["rules"][0].update(name="Countyr", value="")
    s._filter_save()
    s._filter_fill_editor()
    ui.pump(0.3)
    assert "JRiver has no field called Countyr, so this rule does nothing." in labels(win)
    win.destroy()
    ui.pump(0.3)
    ticks = [w.cget("text") for w in walk(s._button_filter_row) if isinstance(w, ttk.Checkbutton)]
    assert "Kiwi Music (at least 25%)" in ticks, ticks
    assert not ui.errors, ui.errors[0]
