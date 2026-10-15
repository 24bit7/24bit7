"""
Profiles hold the zones: Settings > Other > Zones' Default and Follow, and the zone
the keyboard shortcuts apply to, so a surround profile plays to a different zone from
a stereo one. A profile saved before the zones joined isn't "changed" by them, and
loading it leaves the zone as it is.
"""

import importlib
import json


def test_zones_are_part_of_a_profile(app):
    p = importlib.import_module("profiles")
    for key in ("DEFAULT_ZONE", "FOLLOW_ACTIVE_ZONE", "HOTKEY_ZONE"):
        assert key in p.env_keys()
    assert "HIDDEN_ZONES" not in p.env_keys()   # which zones show stays with the PC


def test_loading_a_profile_brings_its_zones(app):
    p = importlib.import_module("profiles")
    app.set_env(DEFAULT_ZONE="Theater", FOLLOW_ACTIVE_ZONE="0", HOTKEY_ZONE="Theater")
    p.save("Surround")
    app.set_env(DEFAULT_ZONE="Lounge", FOLLOW_ACTIVE_ZONE="1", HOTKEY_ZONE="")
    assert p.changed("Surround")
    p.apply(p.read("Surround"))
    env = p._read_env()
    assert (env["DEFAULT_ZONE"], env["FOLLOW_ACTIVE_ZONE"], env["HOTKEY_ZONE"]) == ("Theater", "0", "Theater")
    assert app.engine.DEFAULT_ZONE == "Theater" and app.engine.FOLLOW_ACTIVE_ZONE is False
    assert not p.changed("Surround")


def test_an_older_profile_leaves_the_zone_alone(app):
    p = importlib.import_module("profiles")
    app.set_env(DEFAULT_ZONE="Lounge")
    p.save("DJ")
    with open(p._path("DJ"), encoding="utf-8") as fh:   # as saved before the zones joined profiles
        data = json.load(fh)
    for key in ("DEFAULT_ZONE", "FOLLOW_ACTIVE_ZONE", "HOTKEY_ZONE"):
        del data["env"][key]
    with open(p._path("DJ"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    assert not p.changed("DJ")   # not "changed" by a setting it never held
    app.set_env(DEFAULT_ZONE="Theater")
    assert not p.changed("DJ")
    p.apply(p.read("DJ"))
    assert p._read_env()["DEFAULT_ZONE"] == "Theater"   # loading it keeps the zone as it was
    app.set_env(CONSOLE_MODE="simple")
    assert p.changed("DJ")   # a setting it does hold still counts
