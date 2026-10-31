"""
Buttons and zones (stage one, 31 Oct 2026): the upgrade from Settings > Sources and Playlist,
and the engine running a button under its settings and filters plus the zone's.
"""

import importlib

KITCHEN = "amzn1.ask.device.KITCHEN"


def mods():
    return importlib.import_module("buttons"), importlib.import_module("devices"), importlib.import_module("filters")


def seed(app, artist="The Beatles", title="Here Comes The Sun"):
    return app.engine.typed_seed_info(artist, title)


def add_filter(app, **kw):
    """A filter. devices= writes an old Applies on list, as the database held it before buttons."""
    import json
    import filters
    devices = kw.pop("devices", None)
    f = filters.blank(kw.pop("name", "Test"))
    f.update(kw)
    stored = dict(f, **({"devices": devices} if devices is not None else {}))
    con = app.engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (filters.META_KEY, json.dumps(filters.stored_raw() + [stored])))
    con.commit()
    return f


def kitchen(app, page=None, zone="Kitchen", saved=None):
    """
    An Alexa device in the kitchen as the database held it before buttons: Own settings ticked,
    with a playlist page (and JRiver Playlists settings) of its own if given.
    """
    import json
    v = app.voice
    v._hear_device(KITCHEN)
    v.update_device(KITCHEN, name="Kitchen Echo", zone=zone)
    con = app.engine.db()
    con.execute("UPDATE voice_devices SET own_settings=1, playlist=?, saved=? WHERE device_id=?",
                (json.dumps(page) if page is not None else None, json.dumps(saved) if saved is not None else None,
                 KITCHEN))
    con.commit()


# --- the upgrade -------------------------------------------------------------------------

def test_every_setting_belongs_to_one_kind_or_is_global(app):
    buttons, _, _ = mods()
    e = app.engine
    seen = {}
    for kind, keys in buttons.KIND_KEYS.items():
        for k in keys:
            assert k not in seen, f"{k} is in both {seen[k]} and {kind}"
            seen[k] = kind
    missing = [k for k in e.PROFILE_KEYS["sources"] + e.PROFILE_KEYS["playlist"]
               if k not in seen and k not in buttons.GLOBAL_KEYS]
    assert not missing, f"not in any kind: {missing}"


def test_first_load_makes_the_standard_four_from_env_then_headliner(app):
    app.set_env(SIMILAR_ARTIST_LIMIT="7", TOP_TRACKS_COUNT="12", SIMILAR_TRACK_COUNT="8")
    buttons, _, _ = mods()
    items = buttons.load()
    assert [b["name"] for b in items] == ["Similar Artists", "Similar Tracks", "Artist's Top Tracks", "Headliner",
                                          "Inner Circle", "AI Playlist"]
    assert [b["kind"] for b in items] == ["artists", "tracks", "top", "top", "artists", "vibe"]
    by = {b["name"]: b for b in items}
    assert by["Similar Artists"]["settings"]["SIMILAR_ARTIST_LIMIT"] == "7"
    assert by["Similar Tracks"]["settings"]["SIMILAR_TRACK_COUNT"] == "8"
    assert by["Artist's Top Tracks"]["settings"]["TOP_TRACKS_COUNT"] == "12"
    assert by["Artist's Top Tracks"]["standard"] == "top" and by["Headliner"]["standard"] == ""
    assert by["Headliner"]["settings"]["TOP_GUESTS"] == "third"
    assert by["Headliner"]["settings"]["TOP_TRACKS_COUNT"] == "12", "Headliner starts from the standard Top Tracks"
    assert "SIMILAR_TRACK_COUNT" not in by["Similar Artists"]["settings"], "a button only holds its kind's keys"
    circle = by["Inner Circle"]
    assert circle["kind"] == "artists" and circle["standard"] == "" and circle["shown"] is True
    assert circle["settings"]["INNER_CIRCLE_ARTISTS"] == "1" and circle["settings"]["INNER_CIRCLE_ARTISTS_SIZE"] == "3"
    assert circle["settings"]["INNER_CIRCLE_ARTISTS_AGREE"] == "2"
    assert circle["settings"]["SIMILAR_ARTIST_LIMIT"] == "7", "Inner Circle starts from the standard Similar Artists"
    assert "INNER_CIRCLE_ARTISTS" not in by["Similar Artists"]["settings"], "and the standard one stays as it was"


def test_upgrade_resolves_the_old_single_settings_into_each_button(app):
    """The pre-1.6.0 NONSTOP and the single AI_MODERATOR were every option's starting value: each button gets its own."""
    app.set_env(NONSTOP="1", NONSTOP_USING="artists", AI_MODERATOR="1", SKIP_LONG_CLOSERS="0")
    buttons, _, _ = mods()
    by = {b["kind"]: b for b in buttons.load() if b["standard"]}
    for kind in ("artists", "tracks", "top"):
        s = by[kind]["settings"]
        assert s[f"NONSTOP_{kind.upper()}"] == "1" and s[f"NONSTOP_{kind.upper()}_USING"] == "artists", s
        assert s[f"SKIP_LONG_CLOSERS_{kind.upper()}"] == "0"
    assert by["artists"]["settings"]["AI_MODERATOR_ARTISTS"] == "balanced"   # the old Yes
    assert by["tracks"]["settings"]["AI_MODERATOR_TRACKS"] == "balanced"
    assert "AI_MODERATOR" not in by["artists"]["settings"]


def test_upgrade_runs_once_and_keeps_what_was_added(app):
    buttons, _, _ = mods()
    first = buttons.load()
    extra = buttons.blank("Sunday", "tracks")
    buttons.save(first + [extra])
    again = buttons.load()
    assert [b["id"] for b in again] == [b["id"] for b in first] + [extra["id"]]
    buttons.save([])
    assert buttons.load() == [], "an empty list is a choice, not a reason to upgrade again"


def test_device_with_its_own_settings_gets_a_playlist_it_runs_kept_off_the_play_tab(app):
    app.set_env(SIMILAR_TRACK_COUNT="30")
    buttons, devices, _ = mods()
    main_playlist = app.engine.profile_values("playlist")
    kitchen(app, page=dict(main_playlist, SIMILAR_TRACK_COUNT="12"))
    items = buttons.load()
    names = [b["name"] for b in items]
    assert "Kitchen Echo Similar Tracks" in names, names
    assert "Kitchen Echo Similar Artists" not in names, "only the kinds whose values differ get a playlist"
    own = next(b for b in items if b["name"] == "Kitchen Echo Similar Tracks")
    assert own["kind"] == "tracks" and own["settings"]["SIMILAR_TRACK_COUNT"] == "12"
    assert own["shown"] is False and all(b["shown"] for b in items if b is not own), "off the Play tab; the rest on it"
    assert [b["name"] for b in buttons.shown()] == names[:6]
    record = devices.load()[KITCHEN]
    assert record["buttons"]["tracks_like"] == own["id"]
    assert record["buttons"]["music_like"] is None
    assert devices.playlist_for(KITCHEN, "tracks_like")["id"] == own["id"]
    assert devices.playlist_for(KITCHEN, "more_like")["id"] == own["id"], "more like this is the same phrase"
    assert devices.playlist_for(KITCHEN, "music_like")["standard"] == "artists", "unset phrases run the standard playlist"
    assert devices.playlist_for("nobody", "tracks_like")["standard"] == "tracks", "a device with no record too"
    assert app.printed.has("Kitchen Echo had settings of its own") and app.printed.has("Kitchen Echo Similar Tracks"), \
        app.printed.text()
    assert devices.used_by(own["id"]) == [KITCHEN]


def test_device_whose_settings_match_main_gets_no_playlist(app):
    buttons, devices, _ = mods()
    kitchen(app, page=dict(app.engine.profile_values("playlist")), saved=app.saved_playlists.blank())
    assert len(buttons.load()) == 6
    assert all(v is None for v in devices.load().get(KITCHEN, devices.blank())["buttons"].values())
    assert app.printed.has("Kitchen Echo's own JRiver Playlists settings are no longer used"), app.printed.text()
    assert not app.printed.has("had settings of its own")


def test_upgrade_ticks_shared_filters_on_the_standard_playlists_and_says_so_for_a_device_only_one(app):
    buttons, devices, filters = mods()
    kitchen(app)
    everyone = add_filter(app, name="Everyone", devices=["all"])
    main_only = add_filter(app, name="Main", devices=["main"])
    kitchen_only = add_filter(app, name="Kitchen", devices=[KITCHEN])
    items = buttons.load()
    for b in items:
        assert b["filters"] == [everyone["id"], main_only["id"]], (b["name"], b["filters"])
    assert filters.used_by(kitchen_only["id"]) == []
    assert app.printed.has("the filter Kitchen applied to Kitchen Echo only"), app.printed.text()


def test_a_template_starts_from_the_shipped_defaults_and_a_copy_gets_the_next_free_name(app):
    app.set_env(SIMILAR_TRACK_COUNT="8")
    buttons, _, _ = mods()
    buttons.load()
    fresh = buttons.add("Fresh", "tracks", buttons.TEMPLATE)
    assert fresh["settings"].get("SIMILAR_TRACK_COUNT") is None, "a template ignores what .env has"
    assert fresh["settings"]["NONSTOP_TRACKS"] == "0" and fresh["shown"] is True
    copy = buttons.add("Copy", "tracks")
    assert copy["settings"]["SIMILAR_TRACK_COUNT"] == "8", "no from: the standard one of its kind"
    assert buttons.unique_name("Similar Tracks") == "Similar Tracks 2" and buttons.unique_name("New") == "New"
    twin = buttons.duplicate(buttons.standard("tracks")["id"])
    assert twin["name"] == "Similar Tracks 2" and twin["settings"]["SIMILAR_TRACK_COUNT"] == "8"
    assert [b["name"] for b in buttons.load()][1:3] == ["Similar Tracks", "Similar Tracks 2"], "right after its source"


def test_the_ready_made_templates_make_headliner_and_inner_circle_from_the_standard_ones(app):
    app.set_env(SIMILAR_ARTIST_LIMIT="7", TOP_TRACKS_COUNT="12")
    buttons, _, _ = mods()
    buttons.load()
    assert [r[0] for r in buttons.READY_MADE] == ["headliner", "inner_circle"]
    head = buttons.add(buttons.unique_name("Headliner"), "artists", "template:headliner")
    assert head["name"] == "Headliner 2" and head["kind"] == "top", "the recipe's kind wins over the one passed"
    assert head["settings"]["TOP_GUESTS"] == "third" and head["settings"]["TOP_TRACKS_COUNT"] == "12"
    circle = buttons.add("Tight", "artists", "template:inner_circle")
    assert circle["kind"] == "artists" and circle["settings"]["INNER_CIRCLE_ARTISTS"] == "1"
    assert circle["settings"]["SIMILAR_ARTIST_LIMIT"] == "7"
    assert buttons.describe(circle).startswith("Artist Matching, Inner Circle"), buttons.describe(circle)
    for key in ("INNER_CIRCLE_TRACKS", "INNER_CIRCLE_TRACKS_SIZE", "INNER_CIRCLE_TRACKS_AGREE"):
        assert key in buttons.KIND_KEYS["tracks"] and key not in buttons.KIND_KEYS["artists"]


def test_restore_default_buttons_puts_back_only_what_is_missing(app):
    buttons, _, _ = mods()
    items = buttons.load()
    kept = [b for b in items if b["standard"] != "artists"]
    buttons.save(kept)
    back = buttons.restore_standard()
    assert [b["standard"] for b in back] == ["artists"]
    names = [b["name"] for b in buttons.load()]
    assert names == ["Similar Tracks", "Artist's Top Tracks", "Headliner", "Inner Circle", "AI Playlist", "Similar Artists"]
    assert buttons.restore_standard() == []


# --- running one -------------------------------------------------------------------------

def test_run_uses_the_buttons_settings_and_filters_then_puts_everything_back(app):
    buttons, _, _ = mods()
    e = app.engine
    old = add_filter(app, name="Sixties", devices=[], rules=[{"field": "year", "op": "before", "value": "1968", "value2": ""}])
    b = buttons.blank("Short and old", "tracks")
    b["settings"] = {"SIMILAR_TRACK_COUNT": "8"}
    b["filters"] = [old["id"]]
    r = app.Lines()
    buttons.run(b, report=r, seed_info=seed(app))
    z = app.jriver.zone("Speakers").playlist
    assert 1 < len(z) <= 9, r.text()
    years = [int(app.jriver.by_key[k]["Date (year)"]) for k in z[1:]]
    assert all(y < 1968 for y in years), r.text()
    assert r.has("Filters: Sixties"), r.text()
    assert e.SIMILAR_TRACK_COUNT == 30, "the button's settings are gone after the build"
    assert e.FILTER_IDS is None and e.PROFILE == {}


def test_a_filter_that_is_not_ticked_on_the_button_does_nothing(app):
    buttons, _, filters = mods()
    add_filter(app, name="Nothing", devices=["all"],
               rules=[{"field": "year", "op": "before", "value": "1900", "value2": ""}])
    b = buttons.blank("Plain", "tracks")
    r = app.Lines()
    buttons.run(b, report=r, seed_info=seed(app))
    assert len(app.jriver.zone("Speakers").playlist) > 10, r.text()
    assert not r.has("Filters:"), "Applies on no longer decides anything for a button build: " + r.text()


def test_top_tracks_button_with_guests_on_is_a_headliner(app):
    buttons, _, _ = mods()
    by = {b["name"]: b for b in buttons.load()}
    r = app.Lines()
    buttons.run(by["Headliner"], report=r, seed_info=seed(app, "The Beatles", ""))
    assert r.has("Headliner: The Beatles"), r.text()
    r = app.Lines()
    buttons.run(by["Artist's Top Tracks"], report=r, seed_info=seed(app, "The Beatles", ""))
    assert r.has("Artist's Top Tracks: The Beatles") and not r.has("Headliner"), r.text()
    assert app.engine.TOP_GUESTS == "off", "the Guests setting is gone after the build"


def test_describe_says_what_is_on(app):
    buttons, _, _ = mods()
    b = buttons.blank("Evening", "artists")
    b["settings"] = {"DRIFT_ARTISTS": "1", "NONSTOP_ARTISTS": "1", "DEEP_CUTS_ARTISTS": "spaced"}
    b["filters"] = ["abc"]
    assert buttons.describe(b) == "Artist Matching, Drift, Deep Cuts, Non-stop, Filters"
    assert buttons.describe(buttons.blank("Plain", "tracks")) == "Track Matching"
    by = {x["name"]: x for x in buttons.load()}
    assert buttons.describe(by["Headliner"]).startswith("Artist's Top Tracks, Guests")


def test_a_build_with_no_button_runs_no_filters(app):
    """Filters only ever apply through a button (its own and its zone's): a plain engine build has none."""
    buttons, _, filters = mods()
    f = add_filter(app, name="Everywhere", rules=[{"field": "year", "op": "before", "value": "1900", "value2": ""}])
    for b in buttons.load():
        buttons.set_filters(b["id"], [f["id"]])
    e = app.engine
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert not r.has("Filters:") and len(app.jriver.zone("Speakers").playlist) > 10, r.text()
    r = app.Lines()
    buttons.run(buttons.standard("tracks"), report=r, seed_info=seed(app))
    assert r.has("Filters: Everywhere"), r.text()


# --- the Play tab's + and right-click (stage two) --------------------------------------------

def test_add_starts_from_a_button_of_the_same_kind(app):
    buttons, _, _ = mods()
    items = buttons.load()
    items[3]["filters"] = ["abc"]   # Headliner
    buttons.save(items)
    head = buttons.load()[3]
    new = buttons.add("Sunday Guests", "top", head["id"])
    items = buttons.load()
    assert items[-1]["name"] == "Sunday Guests" and items[-1]["id"] == new["id"]
    assert items[-1]["settings"]["TOP_GUESTS"] == "third" and items[-1]["filters"] == ["abc"]
    assert not items[-1]["standard"]
    plain = buttons.add("  ", "tracks", "no-such-id")   # no name: the kind's; nothing to copy: the standard one's
    assert plain["name"] == "Track Matching" and plain["settings"] == buttons.standard("tracks")["settings"]
    wrong = buttons.add("Odd", "vibe", head["id"])      # a button of another kind: not copied
    assert wrong["settings"] == buttons.standard("vibe")["settings"]


def test_rename_move_and_remove(app):
    buttons, _, _ = mods()
    head = buttons.load()[3]
    buttons.rename(head["id"], " Star Turn ")
    assert buttons.get(head["id"])["name"] == "Star Turn"
    buttons.rename(head["id"], "   ")
    assert buttons.get(head["id"])["name"] == "Star Turn", "an empty name changes nothing"
    buttons.move(head["id"], -1)
    assert [b["name"] for b in buttons.load()][2:4] == ["Star Turn", "Artist's Top Tracks"]
    buttons.move(head["id"], -5)
    assert buttons.load()[0]["id"] == head["id"], "stops at the left-hand end"
    buttons.move(head["id"], 9)
    assert buttons.load()[-1]["id"] == head["id"], "and at the right"
    buttons.move("no-such-id", 1)
    buttons.remove(head["id"])
    assert buttons.get(head["id"]) is None and len(buttons.load()) == 5
    assert buttons.standard("top")["name"] == "Artist's Top Tracks"


def test_needs_track_under_the_buttons_own_sources(app):
    buttons, _, _ = mods()
    e = app.engine
    yt = buttons.blank("YouTube only", "artists")
    yt["settings"] = {"SIMILAR_SOURCES": "youtube"}
    assert buttons.needs_track(yt) is True
    assert buttons.needs_track(buttons.standard("artists")) is False
    assert buttons.needs_track(buttons.standard("tracks")) is True
    assert buttons.needs_track(buttons.standard("top")) is False
    assert e.PROFILE == {}, "the button's settings are gone again"


def test_run_keeps_a_review_profile_on_top_of_the_button(app):
    buttons, _, _ = mods()
    e = app.engine
    b = buttons.blank("Long", "tracks")
    b["settings"] = {"SIMILAR_TRACK_COUNT": "20"}
    e.use_profile({"SIMILAR_TRACK_COUNT": "4"})   # as a Review build lays Settings > Playlist's Review column
    try:
        r = app.Lines()
        buttons.run(b, report=r, seed_info=seed(app))
        assert len(app.jriver.zone("Speakers").playlist) <= 5, r.text()
        assert e.PROFILE == {"SIMILAR_TRACK_COUNT": "4"}, "the Review profile is back afterwards"
    finally:
        e.use_profile(None)


# --- Settings > Buttons (stage three) ------------------------------------------------------

def test_set_settings_keeps_only_the_kinds_keys_and_filters_say_who_uses_them(app):
    buttons, devices, filters = mods()
    head = buttons.load()[3]
    buttons.set_settings(head["id"], {"TOP_TRACKS_COUNT": "15", "SIMILAR_ARTIST_LIMIT": "9", "TOP_GUESTS": "third"})
    assert buttons.get(head["id"])["settings"] == {"TOP_TRACKS_COUNT": "15", "TOP_GUESTS": "third"}
    f = add_filter(app, name="Stereo")
    assert filters.used_by(f["id"]) == []
    buttons.set_filters(head["id"], [f["id"]])
    assert buttons.get(head["id"])["filters"] == [f["id"]]
    assert filters.used_by(f["id"]) == ["Headliner"]
    buttons.set_shown(head["id"], False)
    assert buttons.get(head["id"])["shown"] is False and "Headliner" not in [b["name"] for b in buttons.shown()]
    buttons.set_shown(head["id"], True)
    assert buttons.get(head["id"])["shown"] is True
    buttons.set_filters("no-such-id", [f["id"]])
    assert len(buttons.load()) == 6
