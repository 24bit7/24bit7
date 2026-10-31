"""
Voice commands, Non-stop, keyboard shortcuts and Blend run through playlists (stage four, 31 Oct
2026, then devices in place of zones that evening). A voice command runs the playlist its device
names for the phrase; Non-stop tops the music up as the playlist that built it says; a playlist's
shortcut lives on the playlist; the old per-device settings path is gone.
"""

import importlib
import importlib.util
import os

from test_voice import alexa, KITCHEN, LOUNGE  # noqa: F401  (the mock Alexa fixture)


def mods():
    return (importlib.import_module("buttons"), importlib.import_module("devices"), importlib.import_module("filters"),
            importlib.import_module("nonstop"), importlib.import_module("hotkeys"))


def seed(app, artist="The Beatles", title="Here Comes The Sun"):
    return app.engine.typed_seed_info(artist, title)


def short_tracks_button(name="Kitchen Tracks", count="5", **settings):
    """A Similar Tracks button of your own that builds a short playlist."""
    buttons = importlib.import_module("buttons")
    b = buttons.add(name, "tracks")
    buttons.set_settings(b["id"], dict(b["settings"], SIMILAR_TRACK_COUNT=count, **settings))
    return buttons.get(b["id"])


def year_filter(name="Sixties", before="1968"):
    filters = importlib.import_module("filters")
    f = filters.blank(name)
    f["rules"] = [{"field": "year", "op": "before", "value": before, "value2": ""}]
    filters.save(filters.load() + [f])
    return f


def point(device, phrase, button):
    """Settings > Devices: this device's phrase runs that playlist."""
    devices = importlib.import_module("devices")
    record = devices.for_device(device)
    record["buttons"][phrase] = button["id"]
    devices.update(device, buttons=record["buttons"])


def last_track(app, zone_name):
    z = app.jriver.zone(zone_name)
    z.pos, z.state, z.position_ms = len(z.playlist) - 1, 2, 0
    return z


def topup_jobs(app):
    nonstop = importlib.import_module("nonstop")
    jobs = []
    nonstop.attach(lambda job, heading, origin=None: jobs.append(job))
    nonstop._check_zones()
    return jobs


def years_of(app, keys):
    return [int(app.jriver.by_key[k]["Date (year)"]) for k in keys]


# --- voice -------------------------------------------------------------------------------

def test_a_voice_command_runs_the_devices_playlist(app, alexa):
    b = short_tracks_button()
    point(KITCHEN, "tracks_like", b)
    r = alexa.say("TracksLikeIntent", "here comes the sun")
    assert r.started, r
    assert alexa.jobs[0][1].endswith(", with Kitchen Tracks"), alexa.jobs[0][1]
    log = alexa.run_jobs()[0]
    assert log.has("Done:"), log.text()
    assert 1 < len(app.jriver.zone("Kitchen").playlist) <= 6, log.text()
    r = alexa.say("TracksLikeIntent", "here comes the sun", device=LOUNGE)   # no record: the standard playlist
    assert ", with" not in alexa.jobs[0][1], alexa.jobs[0][1]
    alexa.run_jobs()
    assert len(app.jriver.zone("Speakers").playlist) > 6
    assert app.engine.PROFILE == {} and app.engine.FILTER_IDS is None and app.engine.BUILD_BUTTON is None


def test_only_runs_under_the_ai_playlist_button(app, alexa, monkeypatch):
    buttons, _, _, _, _ = mods()
    f = year_filter()
    vibe = buttons.standard("vibe")
    buttons.set_filters(vibe["id"], [f["id"]])
    buttons.set_settings(vibe["id"], dict(vibe["settings"], VIBE_TRACK_COUNT="7"))
    seen = {}
    monkeypatch.setattr(app.engine, "create_only_playlist",
                        lambda value, report=print: seen.update(value=value, ids=list(app.engine.FILTER_IDS),
                                                                count=app.engine.VIBE_TRACK_COUNT))
    r = alexa.say("OnlyIntent", "chilled the beatles")
    assert r.started, r
    alexa.run_jobs()
    assert seen["value"] == "chilled the beatles" and seen["ids"] == [f["id"]] and seen["count"] == 7, seen


def test_a_device_with_no_playlist_of_the_kind_says_so(app, alexa):
    buttons, _, _, _, _ = mods()
    for b in buttons.of_kind("tracks"):
        buttons.remove(b["id"])
    alexa.say("TracksLikeIntent", "here comes the sun")
    log = alexa.run_jobs()[0]
    assert log.has("Problem: there's no Similar Tracks button to build with"), log.text()


# --- Non-stop ----------------------------------------------------------------------------

def test_non_stop_follows_the_button_that_built_the_playlist(app):
    app.set_env(NONSTOP_TRACKS="0")
    buttons, _, _, _, _ = mods()
    e = app.engine
    evening = short_tracks_button("Evening", NONSTOP_TRACKS="1")
    r = app.Lines()
    buttons.run(evening, report=r, seed_info=seed(app))
    z = last_track(app, "Speakers")
    before = len(z.playlist)
    assert e.NONSTOP_ZONES["10001"]["button"] == evening["id"]
    jobs = topup_jobs(app)
    assert len(jobs) == 1, "the button that built it has Non-stop on"
    lines = app.Lines()
    jobs[0](lines)
    assert lines.has("so adding more, with Evening."), lines.text()
    assert len(z.playlist) > before and z.playlist[:before] == z.playlist[:before], lines.text()
    # the standard button, with Non-stop off, gets no top-up in another zone
    e.OUTPUT_OVERRIDE = "Kitchen"
    try:
        buttons.run(buttons.standard("tracks"), report=app.Lines(), seed_info=seed(app))
    finally:
        e.OUTPUT_OVERRIDE = None
    last_track(app, "Kitchen")
    assert e.NONSTOP_ZONES["10002"]["button"] == buttons.standard("tracks")["id"]
    assert len(topup_jobs(app)) == 0


def test_a_deleted_playlist_falls_back_to_the_standard_one_of_that_kind(app):
    app.set_env(NONSTOP_TRACKS="0")
    buttons, _, _, _, _ = mods()
    evening = short_tracks_button("Evening", NONSTOP_TRACKS="1")
    buttons.run(evening, report=app.Lines(), seed_info=seed(app))
    last_track(app, "Speakers")
    buttons.remove(evening["id"])
    assert topup_jobs(app) == [], "the standard Similar Tracks has Non-stop off"
    standard = buttons.standard("tracks")
    buttons.set_settings(standard["id"], dict(standard["settings"], NONSTOP_TRACKS="1"))
    jobs = topup_jobs(app)
    assert len(jobs) == 1
    lines = app.Lines()
    jobs[0](lines)
    assert lines.has("so adding more.") and not lines.has(", with "), lines.text()


def test_a_top_up_of_another_kind_runs_the_standard_playlist_under_the_original_filters(app):
    buttons, _, filters, _, _ = mods()
    no_jazz = filters.blank("No Jazz")   # broad, so the top-up has tracks left to add
    no_jazz["rules"] = [{"field": "genre", "op": "not_contains", "value": "jazz", "value2": ""}]
    filters.save(filters.load() + [no_jazz])
    artists = buttons.add("Rock Artists", "artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], NONSTOP_ARTISTS="1", NONSTOP_ARTISTS_USING="tracks"))
    buttons.set_filters(artists["id"], [no_jazz["id"]])
    std = buttons.standard("tracks")
    buttons.set_settings(std["id"], dict(std["settings"], SIMILAR_TRACK_COUNT="4"))
    buttons.run(buttons.get(artists["id"]), report=app.Lines(), seed_info=seed(app))
    z = last_track(app, "Speakers")
    before = len(z.playlist)
    jobs = topup_jobs(app)
    assert len(jobs) == 1
    lines = app.Lines()
    jobs[0](lines)
    added = z.playlist[before:]
    assert 0 < len(added) <= 4, lines.text()
    assert lines.has("Filters: No Jazz") and lines.has("with Rock Artists."), lines.text()
    assert all("jazz" not in str(app.jriver.by_key[k].get("Genre", "")).lower() for k in added), lines.text()


# --- keyboard shortcuts ------------------------------------------------------------------

def test_a_buttons_shortcut_is_registered_and_runs_it(app):
    buttons, _, _, _, hotkeys = mods()
    b = short_tracks_button()
    buttons.set_shortcut(b["id"], "Ctrl+Alt+9")
    code = hotkeys.button_code(b["id"])
    assert hotkeys.assigned() == {code: "Ctrl+Alt+9"}
    assert hotkeys.label(code) == "Kitchen Tracks" and hotkeys.shown(code) == "Kitchen Tracks"
    j = app.jriver
    j.play("Speakers", j.playlists[0]["keys"])
    app.set_env(HOTKEY_ZONE="Speakers")
    lines = app.Lines()
    hotkeys._job(code)(lines)
    assert lines.has("Zone: Speakers") and lines.has("Done:"), lines.text()
    assert 1 < len(j.zone("Speakers").playlist) <= 6, lines.text()
    buttons.set_shortcut(b["id"], "")
    assert hotkeys.assigned() == {}


def test_the_old_build_shortcuts_move_onto_the_standard_buttons(app):
    buttons, _, _, _, hotkeys = mods()
    app.set_env(HOTKEY_SIMILAR_TRACKS="Ctrl+Alt+1", HOTKEY_TOP_TRACKS="Ctrl+Alt+3", HOTKEY_SHUFFLE_ARTIST="Ctrl+Alt+4")
    items = buttons.load()
    assert buttons.standard("tracks")["shortcut"] == "Ctrl+Alt+1"
    assert buttons.standard("top")["shortcut"] == "Ctrl+Alt+3"
    assert buttons.standard("artists")["shortcut"] == ""
    env_text = open(app.folder / ".env", encoding="utf-8").read()
    assert "HOTKEY_SIMILAR_TRACKS" not in env_text and "HOTKEY_TOP_TRACKS" not in env_text
    assert "HOTKEY_SHUFFLE_ARTIST=Ctrl+Alt+4" in env_text, "the fixed shortcuts stay in .env"
    assert os.environ.get("HOTKEY_SIMILAR_TRACKS") is None
    assert hotkeys.assigned() == {hotkeys.button_code(buttons.standard("tracks")["id"]): "Ctrl+Alt+1",
                                  hotkeys.button_code(buttons.standard("top")["id"]): "Ctrl+Alt+3",
                                  "SHUFFLE_ARTIST": "Ctrl+Alt+4"}
    assert [c for c, _ in hotkeys.ACTIONS] == ["SHUFFLE_ARTIST", "SWITCH_ZONES", "SWITCH_PROFILES", "KEEP_GOING"]
    assert len(items) == 5


def test_a_removed_or_ai_buttons_shortcut_says_so(app):
    buttons, _, _, _, hotkeys = mods()
    lines = app.Lines()
    hotkeys._job(hotkeys.button_code("nosuch"))(lines)
    assert lines.has("Problem: that button has been removed"), lines.text()
    lines = app.Lines()
    hotkeys._job(hotkeys.button_code(buttons.standard("vibe")["id"]))(lines)
    assert lines.has("Problem: an AI Playlist button needs a theme"), lines.text()


# --- Blend, filters, devices -------------------------------------------------------------

def test_blend_runs_as_the_devices_tracks_playlist(app, alexa):
    from test_blend import blend_on
    buttons, _, _, _, _ = mods()
    sixties = year_filter()
    b = short_tracks_button()
    buttons.set_filters(b["id"], [sixties["id"]])
    point(KITCHEN, "tracks_like", buttons.get(b["id"]))
    blend_on(app)
    alexa.say("PlaylistIntent", "sunday morning")
    log = alexa.run_jobs()[0]
    assert log.has("Blending in similar tracks") and log.has("Filters: Sixties"), log.text()
    assert app.engine.PROFILE == {} and app.engine.FILTER_IDS is None


def test_filters_have_no_applies_on_list(app):
    _, _, filters, _, _ = mods()
    f = year_filter()
    assert "devices" not in f and "devices" not in filters.load()[0]
    assert not hasattr(filters, "ALL") and not hasattr(filters, "device_for_zone")
    assert "devices" not in f and importlib.util.find_spec("zones") is None, "filters belong to playlists only"
    assert not filters.Active([]) and not filters.Active(None)
    assert [x["id"] for x in filters.Active([f["id"]]).items] == [f["id"]]


def test_devices_have_no_settings_of_their_own(app, alexa):
    v = app.voice
    rows = v.devices()
    assert rows and all(len(row) == 4 for row in rows), rows
    for gone in ("device_profile", "device_page", "set_device_page", "set_own_settings"):
        assert not hasattr(v, gone), gone
    assert not hasattr(app.engine, "FILTER_DEVICE")
