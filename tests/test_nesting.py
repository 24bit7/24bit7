"""
Nested playlists, the model (stage one, 1 Nov 2026 evening): a playlist can sit under another, one
level deep. The row is the ticked top-level playlists; a parent's menu is its ticked children; the
parent's button runs its default, itself unless a child is named. The stored list is in tree order,
moves stay within a level, and a deleted parent's children come out onto the row.
"""


def names(items):
    return [b["name"] for b in items]


def setup(buttons):
    buttons.load()
    top = buttons.standard("top")
    ten = buttons.add("Top 10, Best First", "top")
    deep = buttons.add("Deep Cut Top Tracks", "top")
    return top, ten, deep


def test_nesting_takes_a_playlist_off_the_row_and_into_the_parents_menu(app):
    import buttons
    top, ten, deep = setup(buttons)
    assert buttons.nest(ten["id"], top["id"]) and buttons.nest(deep["id"], top["id"])
    assert names(buttons.shown()) == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Headliner", "Inner Circle",
                                      "AI Playlist"], "the children left the row"
    assert names(buttons.children(top["id"])) == ["Top 10, Best First", "Deep Cut Top Tracks"]
    assert buttons.is_parent(buttons.get(top["id"])) and not buttons.is_parent(buttons.get(ten["id"]))
    order = names(buttons.load())
    assert order.index("Top 10, Best First") == order.index("Artist's Top Tracks") + 1, "tree order: children follow their parent"
    assert order.index("Headliner") == order.index("Deep Cut Top Tracks") + 1
    buttons.set_shown(deep["id"], False)
    assert names(buttons.children(top["id"])) == ["Top 10, Best First"], "unticked: out of the menu, kept"
    assert names(buttons.children(top["id"], ticked_only=False)) == ["Top 10, Best First", "Deep Cut Top Tracks"]


def test_one_level_deep(app):
    import buttons
    top, ten, deep = setup(buttons)
    buttons.nest(ten["id"], top["id"])
    assert not buttons.nest(deep["id"], ten["id"]), "a child can't take children"
    assert not buttons.nest(top["id"], deep["id"]), "a playlist with children can't be nested"
    assert not buttons.nest(top["id"], top["id"])
    assert buttons.get(deep["id"])["parent"] == "" and buttons.get(top["id"])["parent"] == ""


def test_the_default_is_what_the_button_runs(app):
    import buttons
    top, ten, _deep = setup(buttons)
    buttons.nest(ten["id"], top["id"])
    assert buttons.runs(buttons.get(top["id"]))["id"] == top["id"], "itself, to start"
    buttons.set_default(top["id"], ten["id"])
    assert buttons.get(top["id"])["default"] == ten["id"]
    assert buttons.runs(buttons.get(top["id"]))["name"] == "Top 10, Best First"
    buttons.set_default(top["id"], "nonsense")
    assert buttons.get(top["id"])["default"] == "", "only a child can be the default"
    buttons.set_default(top["id"], ten["id"])
    assert buttons.unnest(ten["id"])
    assert buttons.get(top["id"])["default"] == "", "out of the menu: no longer the default"
    assert buttons.get(ten["id"])["parent"] == "" and names(buttons.shown())[3] == "Top 10, Best First", "back on the row after its old parent"


def test_moves_stay_within_a_level_and_carry_children(app):
    import buttons
    top, ten, deep = setup(buttons)
    buttons.nest(ten["id"], top["id"])
    buttons.nest(deep["id"], top["id"])
    buttons.move(deep["id"], -1)
    assert names(buttons.children(top["id"])) == ["Deep Cut Top Tracks", "Top 10, Best First"], "a child moves among the children"
    buttons.move(deep["id"], -1)
    assert names(buttons.children(top["id"])) == ["Deep Cut Top Tracks", "Top 10, Best First"], "and no further up"
    buttons.move(top["id"], -1)
    order = names(buttons.load())
    assert order[:5] == ["Similar Artists", "Artist's Top Tracks", "Deep Cut Top Tracks", "Top 10, Best First", "Similar Tracks"], \
        "a parent moves past the next top-level playlist, children with it"
    buttons.move_shown(top["id"], 1)
    assert names(buttons.shown())[:3] == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks"]
    head = next(b for b in buttons.load() if b["name"] == "Headliner")
    buttons.move_to(top["id"], head["id"])
    order = names(buttons.load())
    assert order[order.index("Headliner") - 3:order.index("Headliner")] == ["Artist's Top Tracks", "Deep Cut Top Tracks", "Top 10, Best First"]
    buttons.move_to(ten["id"], head["id"])
    assert buttons.get(ten["id"])["parent"] == top["id"], "a child isn't dropped onto the row by a move"


def test_deleting_a_parent_frees_its_children_and_a_copy_of_a_child_sits_beside_it(app):
    import buttons
    top, ten, deep = setup(buttons)
    buttons.nest(ten["id"], top["id"])
    buttons.nest(deep["id"], top["id"])
    copy = buttons.duplicate(ten["id"])
    assert copy["parent"] == top["id"]
    assert names(buttons.children(top["id"])) == ["Top 10, Best First", "Top 10, Best First 2", "Deep Cut Top Tracks"]
    buttons.remove(top["id"])
    assert all(buttons.get(i)["parent"] == "" for i in (ten["id"], copy["id"], deep["id"])), "out onto the row"
    assert "Top 10, Best First" in names(buttons.shown())


def test_a_stored_tangle_settles_on_load(app):
    import json
    import buttons
    top, ten, deep = setup(buttons)
    items = buttons.load()
    by = {b["name"]: b for b in items}
    by["Top 10, Best First"]["parent"] = top["id"]
    by["Deep Cut Top Tracks"]["parent"] = ten["id"]      # under a child: not allowed
    by["Headliner"]["parent"] = "gone"                   # a parent that doesn't exist
    by["Artist's Top Tracks"]["default"] = deep["id"]    # not one of its children
    con = app.engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (buttons.META_KEY, json.dumps(items)))
    con.commit()
    loaded = {b["name"]: b for b in buttons.load()}
    assert loaded["Top 10, Best First"]["parent"] == top["id"]
    assert loaded["Deep Cut Top Tracks"]["parent"] == "" and loaded["Headliner"]["parent"] == ""
    assert loaded["Artist's Top Tracks"]["default"] == ""
    order = names(buttons.load())
    assert order.index("Top 10, Best First") == order.index("Artist's Top Tracks") + 1, "in tree order"
