"""
Profiles carry the buttons and zones (stage five, 31 Oct 2026): a profile saved today brings its
buttons (settings and filters) and each zone's choices back; a button's shortcut stays with the
PC like the other shortcuts; a profile saved before buttons loads into the standard buttons and
leaves your own buttons and the zones alone.
"""

import importlib
import json


def mods():
    return importlib.import_module("profiles"), importlib.import_module("buttons"), importlib.import_module("zones")


def test_buttons_and_zones_are_in_a_profile_without_their_shortcuts(app):
    p, buttons, zones = mods()
    assert "buttons" in p.META_KEYS and "zones" in p.META_KEYS
    sunday = buttons.add("Sunday", "tracks")
    buttons.set_shortcut(sunday["id"], "Ctrl+Alt+9")
    zones.update("Kitchen", nonstop=False)
    snap = p.snapshot()
    saved = json.loads(snap["meta"]["buttons"])
    assert [b["name"] for b in saved][-1] == "Sunday" and all(b["shortcut"] == "" for b in saved)
    assert json.loads(snap["meta"]["zones"])["Kitchen"]["nonstop"] is False
    assert buttons.get(sunday["id"])["shortcut"] == "Ctrl+Alt+9", "the snapshot doesn't touch the real one"


def test_loading_brings_buttons_and_zones_back_and_keeps_the_pcs_shortcuts(app):
    p, buttons, zones = mods()
    sunday = buttons.add("Sunday", "tracks")
    buttons.set_settings(sunday["id"], dict(sunday["settings"], SIMILAR_TRACK_COUNT="7"))
    record = zones.for_zone("Kitchen")
    record["buttons"]["tracks_like"] = sunday["id"]
    zones.update("Kitchen", buttons=record["buttons"], nonstop=False)
    buttons.set_shortcut(sunday["id"], "Ctrl+Alt+9")
    p.save("DJ")
    assert not p.changed("DJ")
    buttons.set_shortcut(sunday["id"], "Ctrl+Alt+2")
    assert not p.changed("DJ"), "a shortcut is the PC's, not the profile's"
    buttons.set_settings(sunday["id"], dict(buttons.get(sunday["id"])["settings"], SIMILAR_TRACK_COUNT="12"))
    assert p.changed("DJ")
    zones.update("Kitchen", nonstop=True)
    buttons.remove(sunday["id"])
    p.apply(p.read("DJ"))
    back = buttons.get(sunday["id"])
    assert back and back["settings"]["SIMILAR_TRACK_COUNT"] == "7"
    assert back["shortcut"] == "", "a button that was gone has no shortcut on this PC"
    assert not zones.nonstop_on("Kitchen") and zones.button_for("Kitchen", "tracks_like")["id"] == sunday["id"]
    assert not p.changed("DJ")


def test_the_standard_buttons_keep_their_shortcuts_through_a_load(app):
    p, buttons, _ = mods()
    p.save("Plain")
    tracks = buttons.standard("tracks")
    buttons.set_shortcut(tracks["id"], "Ctrl+Alt+1")
    buttons.set_settings(tracks["id"], dict(tracks["settings"], SIMILAR_TRACK_COUNT="12"))
    p.apply(p.read("Plain"))
    tracks = buttons.standard("tracks")
    assert tracks["shortcut"] == "Ctrl+Alt+1" and tracks["settings"].get("SIMILAR_TRACK_COUNT", "30") != "12"


def test_an_older_profile_loads_into_the_standard_buttons(app):
    p, buttons, zones = mods()
    app.set_env(SIMILAR_TRACK_COUNT="30")
    buttons.load()
    p.save("Old")
    with open(p._path("Old"), encoding="utf-8") as fh:   # as saved before buttons joined profiles
        data = json.load(fh)
    del data["meta"]["buttons"], data["meta"]["zones"]
    with open(p._path("Old"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    sunday = buttons.add("Sunday", "tracks")
    zones.update("Kitchen", nonstop=False)
    assert not p.changed("Old"), "not changed by settings it never held"
    data["env"]["SIMILAR_TRACK_COUNT"] = "9"
    with open(p._path("Old"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    count = len(buttons.load())
    p.apply(p.read("Old"))
    assert buttons.standard("tracks")["settings"]["SIMILAR_TRACK_COUNT"] == "9"
    assert app.engine.SIMILAR_TRACK_COUNT == 9
    items = buttons.load()
    assert len(items) == count and buttons.get(sunday["id"]) is not None, "your own buttons are left alone"
    assert not zones.nonstop_on("Kitchen"), "and so are the zones"
