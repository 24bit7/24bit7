"""
The arrangement 24bit7 ships (Ben, 2 Nov 2026): three buttons, two with menus. Similar Artists (titled
Artist Matching) over the standard Similar Tracks as Track Matching, Consensus and Artist + Guests;
Artist's Top Tracks set to fifteen in random order (only those two settings; the rest stays the user's),
titled Top 15, Random, over Top 10, Best First and Top 10, Best Last; AI Playlist alone; then Radio (6 Nov 2026). The fake world
elsewhere starts flat (conftest), so these tests put the real arrange_shipped back and run the upgrade.
"""


def fresh(app, monkeypatch, **env):
    if env:
        app.set_env(**env)
    import buttons
    import engine
    monkeypatch.setattr(buttons, "arrange_shipped", app.arrange_shipped)
    con = engine.db()
    con.execute("DELETE FROM meta WHERE key = ?", (buttons.META_KEY,))
    con.commit()
    return buttons, buttons.load()


def test_the_upgrade_lays_on_the_shipped_arrangement(app, monkeypatch):
    buttons, items = fresh(app, monkeypatch, TOP_TRACKS_COUNT="20", TOP_TRACKS_ORDER="popular", TOP_TRACK_SOURCES="deezer",
                           SIMILAR_TRACK_COUNT="8")
    assert [b["name"] for b in buttons.shown()] == ["Similar Artists", "Artist's Top Tracks", "AI Playlist", "Radio"]
    assert [b["name"] for b in items] == ["Similar Artists", "Track Matching", "Consensus", "Artist + Guests",
                                          "Artist's Top Tracks", "Top 10, Best First", "Top 10, Best Last", "AI Playlist",
                                          "Radio"]
    by = {b["name"]: b for b in items}
    artists, top = by["Similar Artists"], by["Artist's Top Tracks"]
    assert [c["name"] for c in buttons.children(artists["id"])] == ["Track Matching", "Consensus", "Artist + Guests"]
    assert [c["name"] for c in buttons.children(top["id"])] == ["Top 10, Best First", "Top 10, Best Last"]
    assert artists["subtitle"] == "Artist Matching" and top["subtitle"] == "Top 15, Random"
    assert all(b["default"] == "" for b in items), "each button runs itself"
    tracks = by["Track Matching"]
    assert tracks["standard"] == "tracks" and tracks["settings"]["SIMILAR_TRACK_COUNT"] == "8", "the standard, renamed, settings kept"
    assert top["settings"]["TOP_TRACKS_COUNT"] == "15" and top["settings"]["TOP_TRACKS_ORDER"] == "random", "overridden"
    assert top["settings"]["TOP_TRACK_SOURCES"] == "deezer", "and only those two: the rest stays theirs"
    first, last = by["Top 10, Best First"], by["Top 10, Best Last"]
    assert (first["settings"]["TOP_TRACKS_COUNT"], first["settings"]["TOP_TRACKS_ORDER"]) == ("10", "popular")
    assert (last["settings"]["TOP_TRACKS_COUNT"], last["settings"]["TOP_TRACKS_ORDER"]) == ("10", "reverse")
    assert first["settings"]["TOP_TRACK_SOURCES"] == "deezer" and first["made"] == "top10_first" and last["made"] == "top10_last"
    assert by["Artist + Guests"]["settings"]["TOP_TRACKS_COUNT"] == "12" and by["Artist + Guests"]["made"] == "headliner"
    assert buttons.missing_shipped() == []
    assert [r["key"] for r in buttons.READY_MADE] == ["headliner", "inner_circle", "top10_first", "top10_last", "radio"],         "offered as templates too"


def test_restore_puts_back_what_is_missing_under_its_parent_and_touches_nothing_else(app, monkeypatch):
    buttons, items = fresh(app, monkeypatch)
    by = {b["name"]: b for b in items}
    for name in ("Track Matching", "Top 10, Best Last", "Artist + Guests"):
        buttons.remove(by[name]["id"])
    assert buttons.missing_shipped() == ["Track Matching", "Artist + Guests", "Top 10, Best Last"]
    back = buttons.restore_standard()
    assert [b["name"] for b in back] == ["Track Matching", "Artist + Guests", "Top 10, Best Last"]
    artists, top = buttons.standard("artists"), buttons.standard("top")
    assert [c["name"] for c in buttons.children(artists["id"])] == ["Consensus", "Track Matching", "Artist + Guests"], \
        "back under their parent, after what was there"
    assert [c["name"] for c in buttons.children(top["id"])] == ["Top 10, Best First", "Top 10, Best Last"]
    assert buttons.standard("tracks")["name"] == "Track Matching"
    assert buttons.get(back[2]["id"])["settings"]["TOP_TRACKS_ORDER"] == "reverse"
    assert buttons.restore_standard() == [] and buttons.missing_shipped() == []
    # a parent that's gone: its children came out onto the row and stay there; Restore puts it back after the rest
    buttons.remove(top["id"])
    assert [b["name"] for b in buttons.shown()] == ["Similar Artists", "Top 10, Best First", "Top 10, Best Last", "AI Playlist",
                                                    "Radio"]
    back = buttons.restore_standard()
    assert [b["name"] for b in back] == ["Artist's Top Tracks"]
    assert [b["name"] for b in buttons.shown()] == ["Similar Artists", "Top 10, Best First", "Top 10, Best Last", "AI Playlist",
                                                    "Radio", "Artist's Top Tracks"], "nothing already there is moved"
    assert buttons.children(buttons.standard("top")["id"]) == []
