"""
Configs and Mix (stage C of the playlist builder, 31 Oct 2026): a playlist is one or more configs,
each finding tracks its own way, woven together as its Mix says. Drift runs from the config the Mix
names; Non-stop carries on as the one it names.
"""

QUIET = dict(DRIFT_ARTISTS="0", DRIFT_TRACKS="0", SKIP_PLAYED_ARTISTS="0", SKIP_PLAYED_TRACKS="0", SKIP_PLAYED_TOP="0",
             AI_MODERATOR="off", TOP_TRACKS_COUNT="3", TOP_TRACKS_ORDER="popular", SIMILAR_TRACK_COUNT="4")


def seed(app, artist="The Beatles", title="Something"):
    return app.engine.typed_seed_info(artist, title)


def two_configs(app, kind2="tracks", **mix):
    import buttons
    buttons.load()
    b = buttons.add("Pair", "top")
    b = buttons.add_config(b["id"], kind2)
    if mix:
        buttons.set_mix(b["id"], **mix)
    return buttons.get(b["id"])


def artist_of(title):
    return title.split(" - ", 1)[0]


# --- the model ---------------------------------------------------------------------------------

def test_a_plain_playlist_has_one_config_and_a_default_mix(app):
    import buttons
    b = buttons.standard("tracks")
    assert buttons.configs(b) == [{"kind": "tracks", "settings": b["settings"]}]
    assert b["mix"] == {"combine": "shuffle", "pattern": [1], "drift_from": 0, "continue_as": 0}
    assert buttons.continue_as(b) is b


def test_add_remove_and_set_a_config(app):
    import buttons
    app.set_env(SIMILAR_TRACK_COUNT="7")
    b = two_configs(app)
    assert [c["kind"] for c in buttons.configs(b)] == ["top", "tracks"]
    assert b["configs"][0]["settings"]["SIMILAR_TRACK_COUNT"] == "7", "starts from the standard playlist of its kind"
    assert b["mix"]["drift_from"] == 1, "Top Tracks has no Drift, so Drift moves to the first config that has"
    assert b["mix"]["pattern"] == [1, 1]
    buttons.set_config_settings(b["id"], 1, {"SIMILAR_TRACK_COUNT": "9", "TOP_TRACKS_COUNT": "99", "DRIFT_TRACKS": "1"})
    b = buttons.get(b["id"])
    assert b["configs"][0]["settings"]["SIMILAR_TRACK_COUNT"] == "9" and "TOP_TRACKS_COUNT" not in b["configs"][0]["settings"]
    assert b["settings"].get("TOP_TRACKS_COUNT") != "99", "the first config is untouched"
    assert buttons.describe(b) == "Artist's Top Tracks + Track Matching, Drift"
    buttons.set_mix(b["id"], combine="alternate", pattern=[3, 9, 4], continue_as=1, drift_from=7)
    b = buttons.get(b["id"])
    assert b["mix"] == {"combine": "alternate", "pattern": [3, 5], "drift_from": 0, "continue_as": 1}, "kept in range"
    assert buttons.continue_as(b)["kind"] == "tracks" and buttons.continue_as(b)["configs"] == []
    assert buttons.continue_as(b)["id"] == b["id"], "Non-stop still knows which playlist built the music"
    b = buttons.add_config(b["id"], "vibe")
    assert [c["kind"] for c in buttons.configs(b)] == ["top", "tracks", "vibe"] and b["mix"]["pattern"] == [3, 5, 1]
    b = buttons.remove_config(b["id"], 1)
    assert [c["kind"] for c in buttons.configs(b)] == ["top", "vibe"]
    assert b["mix"]["continue_as"] == 0 and b["mix"]["pattern"] == [3, 1], "indexes and the pattern follow the removal"
    assert buttons.remove_config(b["id"], 0) == b, "the first config can't be removed"


def test_the_old_guests_headliner_becomes_two_configs_on_load(app):
    import json
    import buttons
    items = buttons.load()
    old = buttons.blank("Old Headliner", "top")
    old["settings"] = {"TOP_TRACKS_COUNT": "8", "TOP_GUESTS": "third"}
    con = app.engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (buttons.META_KEY, json.dumps(items + [old])))
    con.commit()
    b = buttons.get(old["id"])
    assert [c["kind"] for c in buttons.configs(b)] == ["top", "artists"] and b["mix"]["combine"] == "alternate"
    assert b["settings"] == {"TOP_TRACKS_COUNT": "8"} and b["configs"][0]["settings"]["SIMILAR_ARTIST_LIMIT"] == "5"


def test_nonstop_follows_the_continue_as_config(app):
    import buttons
    b = two_configs(app)
    buttons.set_config_settings(b["id"], 1, dict(b["configs"][0]["settings"], NONSTOP_TRACKS="1", NONSTOP_TRACKS_MODE="tight"))
    buttons.set_settings(b["id"], dict(b["settings"], NONSTOP_TOP="0"))
    b = buttons.get(b["id"])
    assert buttons.nonstop_config(b)["on"] is False, "continue as config 1 (Top Tracks), whose Non-stop is off"
    buttons.set_mix(b["id"], continue_as=1)
    cfg = buttons.nonstop_config(buttons.get(b["id"]))
    assert cfg["on"] is True and cfg["mode"] == "tight"


# --- building ----------------------------------------------------------------------------------

def test_append_plays_one_config_then_the_next_with_nothing_twice(app):
    import buttons
    app.set_env(**QUIET)
    b = two_configs(app, combine="append")
    r = app.Lines()
    buttons.run(b, report=r, seed_info=seed(app))
    titles = app.jriver.titles("Speakers")
    assert r.has("Config 1 of 2: Artist's Top Tracks") and r.has("Config 2 of 2: Track Matching"), r.text()
    assert len(titles) >= 5 and all(artist_of(tt) == "The Beatles" for tt in titles[:3]), (titles, r.text())
    assert len(set(titles)) == len(titles), "nothing sent twice"
    assert not r.has("Mix:"), "Append is how the configs were queued already"


def test_alternate_and_shuffle_reorder_what_follows_the_current_track(app):
    import buttons
    app.set_env(**QUIET)
    b = two_configs(app, combine="alternate", pattern=[1, 1])
    r = app.Lines()
    buttons.run(b, report=r, seed_info=seed(app))
    titles = app.jriver.titles("Speakers")
    assert r.has("Mix: alternating, 1 from config 1, 1 from config 2."), r.text()
    assert artist_of(titles[0]) == "The Beatles" and artist_of(titles[1]) != "The Beatles", titles
    assert artist_of(titles[2]) == "The Beatles" and artist_of(titles[3]) != "The Beatles", titles
    buttons.set_mix(b["id"], combine="shuffle")
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r, seed_info=seed(app))
    assert r.has("Mix: shuffled together."), r.text()
    after = app.jriver.titles("Speakers")[1:]   # the track left playing from the last build stays, as ever
    assert len(set(after)) == len(after), after


def test_drift_runs_from_the_named_config_only(app, monkeypatch):
    import buttons
    e = app.engine
    app.set_env(**dict(QUIET, DRIFT_TRACKS="1", DRIFT_ARTISTS="1"))
    seen = {}

    import os

    def fake_tracks(report=print, seed_info=None, **k):
        seen["tracks"] = os.environ.get("DRIFT_TRACKS")   # the config's settings are laid over .env for its build

    def fake_artists(report=print, seed_info=None, **k):
        seen["artists"] = os.environ.get("DRIFT_ARTISTS")
    monkeypatch.setattr(e, "create_similar_tracks_playlist", fake_tracks)
    monkeypatch.setattr(e, "create_similar_playlist", fake_artists)
    buttons.load()
    b = buttons.add("Both", "tracks")
    b = buttons.add_config(b["id"], "artists")
    assert b["mix"]["drift_from"] == 0
    buttons.run(b, report=app.Lines(), seed_info=seed(app))
    assert seen == {"tracks": "1", "artists": "0"}, seen
    buttons.set_mix(b["id"], drift_from=1)
    seen.clear()
    buttons.run(buttons.get(b["id"]), report=app.Lines(), seed_info=seed(app))
    assert seen == {"tracks": "0", "artists": "1"}, seen


def test_the_whole_playlist_settings_are_the_first_configs_for_every_config(app, monkeypatch):
    import os
    import buttons
    e = app.engine
    seen = {}

    def fake_artists(report=print, seed_info=None, **k):
        seen.update({key: os.environ.get(key) for key in ("SKIP_PLAYED_ARTISTS", "SKIP_PLAYED_ARTISTS_DAYS", "DEEP_CUTS_ARTISTS",
                                                           "LONG_CLOSER_MINUTES_ARTISTS", "NONSTOP_ARTISTS", "DRIFT_ARTISTS")})
    monkeypatch.setattr(e, buttons.BUILDERS["top"], lambda report=print, seed_info=None, **k: None)
    monkeypatch.setattr(e, "create_similar_playlist", fake_artists)
    buttons.load()
    b = buttons.add("Pair", "top")
    buttons.set_settings(b["id"], dict(b["settings"], SKIP_PLAYED_TOP="1", SKIP_PLAYED_TOP_DAYS="9", LONG_CLOSER_MINUTES_TOP="11"))
    b = buttons.add_config(b["id"], "artists")
    buttons.set_config_settings(b["id"], 1, dict(b["configs"][0]["settings"], SKIP_PLAYED_ARTISTS="0", SKIP_PLAYED_ARTISTS_DAYS="2",
                                                 DEEP_CUTS_ARTISTS="spaced", NONSTOP_ARTISTS="1", DRIFT_ARTISTS="1"))
    buttons.run(buttons.get(b["id"]), report=app.Lines(), seed_info=seed(app))
    assert seen["SKIP_PLAYED_ARTISTS"] == "1" and seen["SKIP_PLAYED_ARTISTS_DAYS"] == "9", "config 1's Skip played, as shown"
    assert seen["LONG_CLOSER_MINUTES_ARTISTS"] == "11"
    assert seen["DEEP_CUTS_ARTISTS"] == "off", "Top Tracks has no Deep Cuts, so the hidden one stays off"
    assert seen["NONSTOP_ARTISTS"] == "1" and seen["DRIFT_ARTISTS"] == "1", "Non-stop and Drift follow the Mix, not config 1"


def test_a_top_up_and_a_build_of_its_own_run_the_first_config_alone(app, monkeypatch):
    import buttons
    e = app.engine
    calls = []
    monkeypatch.setattr(e, buttons.BUILDERS["top"], lambda report=print, seed_info=None, **k: calls.append("top"))
    monkeypatch.setattr(e, "create_similar_tracks_playlist", lambda report=print, seed_info=None, **k: calls.append("tracks"))
    b = two_configs(app)
    buttons.run(b, report=app.Lines(), seed_info=seed(app), build=lambda report, seed_info, **k: calls.append("own"))
    assert calls == ["own"]
    e.NONSTOP_APPEND = True
    try:
        buttons.run(b, report=app.Lines(), seed_info=seed(app))
    finally:
        e.NONSTOP_APPEND = False
    assert calls == ["own", "top"], "a Non-stop top-up never weaves"


def test_an_ai_config_with_no_theme_is_asked_for_music_like_the_seed(app, monkeypatch):
    import buttons
    e = app.engine
    asked = []
    monkeypatch.setattr(e, "create_vibe_playlist", lambda vibe, report=print, **k: asked.append(vibe))
    monkeypatch.setattr(e, buttons.BUILDERS["top"], lambda report=print, seed_info=None, **k: None)
    b = two_configs(app, "vibe")
    buttons.run(b, report=app.Lines(), seed_info=seed(app))
    assert asked == ["music like The Beatles - Something"], asked
