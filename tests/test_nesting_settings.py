"""
Settings > Playlists as a tree (stage three, 1 Nov 2026 evening): children indented under their
parent with a fold arrow on the parent and "default" tagged, two more strip buttons (out and nest),
Up and Down within a level, a right-click on a child for Make Default and Out to the Row. The Add
window's From Existing shows children indented with their own words.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import buttons_page, pick_button


def rows_by_name(s):
    return {row.text: row for _id, row, _tick, _label, _var in s._button_rows}


def make_tree(buttons):
    buttons.load()
    top = buttons.standard("top")
    ten = buttons.add("Top 10, Best First", "top")
    deep = buttons.add("Deep Cut Top Tracks", "top")
    buttons.nest(ten["id"], top["id"])
    buttons.nest(deep["id"], top["id"])
    buttons.set_default(top["id"], ten["id"])
    return top, ten, deep


def test_the_list_shows_the_tree_and_folds(app, ui):
    import buttons
    top, ten, deep = make_tree(buttons)
    s = buttons_page(ui)
    s._buttons_refresh()
    ui.pump(0.3)
    rows = rows_by_name(s)
    assert list(rows) == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Top 10, Best First", "Deep Cut Top Tracks",
                          "Headliner", "Inner Circle", "AI Playlist"], "tree order"
    assert rows["Top 10, Best First"].indent > 0 and rows["Deep Cut Top Tracks"].indent > 0 and rows["Headliner"].indent == 0
    assert rows["Artist's Top Tracks"].fold == "open" and rows["Headliner"].fold is None
    assert rows["Top 10, Best First"].tag == "default" and rows["Deep Cut Top Tracks"].tag == ""
    s._fold(top["id"])
    ui.pump(0.3)
    rows = rows_by_name(s)
    assert "Top 10, Best First" not in rows and rows["Artist's Top Tracks"].fold == "closed", "folded away"
    s._fold(top["id"])
    ui.pump(0.3)
    assert "Top 10, Best First" in rows_by_name(s)
    assert not ui.errors, ui.errors[0]


def test_the_strip_nests_brings_out_and_moves_within_a_level(app, ui):
    import buttons
    s = buttons_page(ui)
    pick_button(ui, "Headliner")
    strip = s._list_buttons
    assert "normal" in strip["nest"].cget("state") and "disabled" in strip["out"].cget("state")
    s._button_nest()   # under Artist's Top Tracks, the one above
    ui.pump(0.4)
    top = buttons.standard("top")
    assert [b["name"] for b in buttons.children(top["id"])] == ["Headliner"]
    assert s._button_id == next(b["id"] for b in buttons.load() if b["name"] == "Headliner"), "still chosen"
    assert "normal" in strip["out"].cget("state") and "disabled" in strip["nest"].cget("state"), "a child can't nest"
    assert "disabled" in strip["up"].cget("state") and "disabled" in strip["down"].cget("state"), "an only child: nowhere to move"
    assert [b._name for b in ui.play.play_buttons] == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Inner Circle",
                                                      "AI Playlist"], "the Play tab follows"
    assert ui.play.play_buttons[2]._arrow is not None
    pick_button(ui, "Artist's Top Tracks")
    assert "disabled" in strip["nest"].cget("state"), "a parent can't be nested"
    s._button_move(1)
    ui.pump(0.3)
    assert s._button_names()[:5] == ["Similar Artists", "Similar Tracks", "Inner Circle", "Artist's Top Tracks", "Headliner"], \
        "a parent moves past the next top-level playlist, child in tow"
    pick_button(ui, "Headliner")
    s._button_unnest()
    ui.pump(0.4)
    assert buttons.get(s._button_id)["parent"] == "" and s._button_names()[4] == "Headliner"
    assert "disabled" in strip["out"].cget("state")
    assert not ui.errors, ui.errors[0]


def test_right_click_on_a_child_sets_the_default(app, ui):
    import buttons
    top, ten, deep = make_tree(buttons)
    s = buttons_page(ui)
    s._buttons_refresh()
    ui.pump(0.3)
    parent, child = buttons.get(top["id"]), buttons.get(deep["id"])
    # the menu's own commands, run as the menu would
    buttons.set_default(parent["id"], child["id"])
    s._buttons_refresh()
    ui.pump(0.3)
    rows = rows_by_name(s)
    assert rows["Deep Cut Top Tracks"].tag == "default" and rows["Top 10, Best First"].tag == ""
    assert ui.play.play_buttons[2]._label.cget("text") == "Deep Cut Top Tracks", "the Play tab's face follows"
    assert not ui.errors, ui.errors[0]


def test_from_existing_indents_children_and_says_where_they_are(app, ui):
    import buttons
    import settings_gui
    top, ten, deep = make_tree(buttons)
    buttons.set_shown(deep["id"], False)
    win = settings_gui.AddPlaylistPrompt(ui.settings)
    ui.pump(0.5)
    rows = win.existing_list._rows
    names = [r.text for r in rows]
    assert names[2:5] == ["Artist's Top Tracks", "Top 10, Best First", "Deep Cut Top Tracks"]
    assert rows[3].indent > 0 and rows[4].indent > 0 and rows[2].indent == 0
    win.existing_list.pick(3)
    ui.pump(0.2)
    assert "In the menu of Artist's Top Tracks already; Create Copy makes Top 10, Best First 2 beside it" in win.existing_note.cget("text")
    assert win.ok_button.cget("text") == "Create Copy"
    win.existing_list.pick(4)
    ui.pump(0.2)
    assert "Out of the menu of Artist's Top Tracks; Add puts it back" in win.existing_note.cget("text")
    assert win.ok_button.cget("text") == "Add"
    win.ok()
    assert win.result == ("existing", deep["id"])
    assert not ui.errors, ui.errors[0]
