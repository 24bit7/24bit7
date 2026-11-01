"""
New is a blank slate (1 Nov 2026): the + window's New makes a playlist with no config, so nothing
chooses a kind for the user. Its page adds the first config, which becomes the playlist's own;
removing the last config takes it back to blank. Until then, nothing builds it: the Play tab, a
shortcut, a voice command and Non-stop all say so instead.
"""


def new_blank(buttons):
    buttons.load()
    b, wants_page = buttons.add_from_choice(("new", None))
    assert wants_page is True
    return buttons.get(b["id"])


def test_new_is_a_blank_slate_and_stays_one_across_a_load(app):
    import buttons
    b = new_blank(buttons)
    assert b["kind"] is None and b["settings"] == {} and b["configs"] == [] and b["shown"] is True
    assert buttons.configs(b) == []
    assert buttons.describe(b) == "No config yet"
    again = buttons.get(b["id"])   # back through the database and tidy()
    assert again["kind"] is None and buttons.configs(again) == []
    assert buttons.get(new_blank(buttons)["id"])["name"] == "New Playlist 2"


def test_nothing_builds_a_blank_slate(app, monkeypatch):
    import buttons
    b = new_blank(buttons)
    called = []
    for name in buttons.BUILDERS.values():
        monkeypatch.setattr(app.engine, name, lambda *a, **k: called.append(name))
    lines = []
    assert buttons.run(b, report=lines.append) is None
    assert lines == ["New Playlist has no config yet. Add one on its page under Settings > Playlists."]
    assert called == []
    assert buttons.nonstop_config(b)["on"] is False, "Non-stop has nothing to carry on as"
    assert buttons.continue_as(b) is b
    assert buttons.needs_track(b) is False
    assert buttons.standard(None) is None, "a blank slate is never the standard playlist of anything"


def test_the_first_config_becomes_the_playlists_own(app):
    import buttons
    b = new_blank(buttons)
    b = buttons.add_config(b["id"], "tracks")
    assert b["kind"] == "tracks" and b["configs"] == []
    assert b["settings"] == buttons.standard("tracks")["settings"], "it starts from the standard playlist of its kind"
    assert [c["kind"] for c in buttons.configs(b)] == ["tracks"]
    b = buttons.add_config(b["id"], "top")
    assert [c["kind"] for c in buttons.configs(b)] == ["tracks", "top"], "the second config is a second config"
    assert buttons.describe(b).startswith("Track Matching + Artist's Top Tracks")


def test_removing_the_own_config_moves_the_next_up_or_leaves_a_blank_slate(app):
    import buttons
    b = new_blank(buttons)
    buttons.add_config(b["id"], "top")
    b = buttons.add_config(b["id"], "artists")
    buttons.set_mix(b["id"], combine="alternate", pattern=[2, 1], drift_from=1, continue_as=1)
    b = buttons.remove_config(b["id"], 0)
    assert [c["kind"] for c in buttons.configs(b)] == ["artists"], "the second config moved up into its place"
    assert b["mix"]["drift_from"] == 0 and b["mix"]["continue_as"] == 0 and b["mix"]["pattern"] == [1]
    b = buttons.remove_config(b["id"], 0)
    assert b["kind"] is None and buttons.configs(b) == [], "the last config gone: a blank slate again"
    std = buttons.standard("artists")
    assert buttons.remove_config(std["id"], 0)["kind"] == "artists", "a standard playlist keeps its own config"


def test_a_copy_of_a_blank_slate_is_blank_and_a_stored_blank_with_configs_is_tidied(app):
    import json
    import buttons
    b = new_blank(buttons)
    copy = buttons.duplicate(b["id"])
    assert copy["kind"] is None and copy["name"] == "New Playlist 2" and buttons.configs(copy) == []
    items = buttons.load()
    for item in items:
        if item["id"] == b["id"]:
            item["configs"] = [{"kind": "top", "settings": {"TOP_TRACKS_COUNT": "5"}}]
    app.engine.db().execute("UPDATE meta SET value=? WHERE key=?", (json.dumps(items), buttons.META_KEY))
    app.engine.db().commit()
    fixed = buttons.get(b["id"])
    assert fixed["kind"] == "top" and fixed["settings"] == {"TOP_TRACKS_COUNT": "5"} and fixed["configs"] == []
