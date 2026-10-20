"""
A keyboard shortcut per profile: Settings > Other > Keyboard Shortcuts has a "Load DJ"
box for each saved profile, kept in .env as HOTKEY_PROFILE_<name>. Pressing it loads
that profile and restarts 24bit7, or does nothing if it's already loaded. Switch
Profiles' A to Z order can't be relied on from a remote or an automation; a key
that always lands on one profile can.
"""

import importlib
import os


def setup(app, *names):
    p = importlib.import_module("profiles")
    for name in names:
        p.save(name)
    return p, importlib.import_module("hotkeys")


def test_each_profile_has_a_shortcut_of_its_own(app):
    p, hotkeys = setup(app, "DJ", "Surround Sound")
    assert p.shortcut_code("DJ") == "PROFILE_DJ"
    assert p.shortcut_code("Surround Sound") == "PROFILE_Surround_Sound"   # a key .env can hold
    assert p.shortcut_key("DJ") == "HOTKEY_PROFILE_DJ"
    assert hotkeys.profile_actions() == [("PROFILE_DJ", "Load DJ", "DJ"),
                                         ("PROFILE_Surround_Sound", "Load Surround Sound", "Surround Sound")]
    assert hotkeys.label("PROFILE_Surround_Sound") == "Load Surround Sound"
    assert hotkeys.label("SWITCH_PROFILES") == "Switch Profiles"
    assert hotkeys.is_profile("PROFILE_DJ") and not hotkeys.is_profile("SWITCH_PROFILES")


def test_a_profile_shortcut_is_registered_with_the_others(app):
    p, hotkeys = setup(app, "DJ")
    app.set_env(HOTKEY_PROFILE_DJ="Ctrl+Alt+7", HOTKEY_SIMILAR_TRACKS="Ctrl+Alt+1")
    assert hotkeys.assigned() == {"SIMILAR_TRACKS": "Ctrl+Alt+1", "PROFILE_DJ": "Ctrl+Alt+7"}


def test_the_shortcut_loads_that_profile_and_asks_for_a_restart(app):
    p, hotkeys = setup(app, "DJ", "Explore")   # current: Explore
    out = app.Lines()
    hotkeys._job("PROFILE_DJ")(out)
    assert out.has('Switching to the profile "DJ"')
    assert os.path.isfile(p.PENDING)
    assert hotkeys.take_restart() is True


def test_already_loaded_does_nothing(app):
    p, hotkeys = setup(app, "Explore", "DJ")   # current: DJ
    out = app.Lines()
    hotkeys._job("PROFILE_DJ")(out)
    assert out.has('The profile "DJ" is already loaded.')
    assert not os.path.isfile(p.PENDING)
    assert hotkeys.take_restart() is False


def test_loaded_but_changed_loads_it_again(app):
    p, hotkeys = setup(app, "DJ")
    p._write_env({"CONSOLE_MODE": "simple"})
    out = app.Lines()
    hotkeys._job("PROFILE_DJ")(out)
    assert out.has("weren't saved") and out.has('Switching to the profile "DJ"')
    assert hotkeys.take_restart() is True


def test_a_deleted_profile_says_so(app):
    p, hotkeys = setup(app, "DJ")
    p.delete("DJ")
    out = app.Lines()
    hotkeys._job("PROFILE_DJ")(out)
    assert out.has("Problem: that profile has been deleted")
    assert hotkeys.take_restart() is False


def test_deleting_a_profile_clears_its_shortcut(app):
    p, hotkeys = setup(app, "DJ", "Explore")
    app.set_env(HOTKEY_PROFILE_DJ="Ctrl+Alt+7", HOTKEY_PROFILE_Explore="Ctrl+Alt+8")
    p.delete("DJ")
    env = p._read_env()
    assert "HOTKEY_PROFILE_DJ" not in env and env["HOTKEY_PROFILE_Explore"] == "Ctrl+Alt+8"


def test_pressed_during_a_build_says_it_will_wait(app):
    p, hotkeys = setup(app, "DJ")
    notes, queued = [], []
    hotkeys.attach(lambda job, heading, origin=None: queued.append(heading), busy=lambda: True, note=notes.append)
    try:
        hotkeys._pressed("PROFILE_DJ")
    finally:
        hotkeys.attach(None)
    assert notes == ["Load DJ requested: it will switch once the current build has finished."]
    assert queued == ["Shortcut: Load DJ"]


def test_the_shortcut_is_not_part_of_the_profile(app):
    p, _ = setup(app, "DJ")
    assert not any(k.startswith("HOTKEY_PROFILE_") for k in p.env_keys())


def test_the_console_heading_is_german_in_german(app):
    """20 Oct 2026: a shortcut's console heading and its wait note stayed English."""
    import i18n
    p, hotkeys = setup(app, "DJ")
    notes, queued = [], []
    hotkeys.attach(lambda job, heading, origin=None: queued.append(heading), busy=lambda: True, note=notes.append)
    i18n.set_language("de")
    try:
        hotkeys._pressed("PROFILE_DJ")
    finally:
        i18n.set_language("en")
        hotkeys.attach(None)
    assert queued == ["Tastenkürzel: DJ laden"]
    assert notes[0].startswith("DJ laden angefordert")
