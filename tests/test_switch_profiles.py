"""
Switch Profiles: the keyboard shortcut steps through the profiles ticked under
Enable Switch To (Settings > Other > Profiles), loading the next one.
"""

import importlib
import os


def setup_profiles(app, *names):
    profiles = importlib.import_module("profiles")
    for name in names:
        profiles.save(name)
    return profiles


def test_two_ticked_flip_between_them(app):
    p = setup_profiles(app, "DJ", "Explore")   # saving Explore last makes it current
    assert p.switch_target() == ("DJ", None)
    p.save("DJ")
    assert p.switch_target() == ("Explore", None)


def test_three_step_round_in_order_and_skip_unticked(app):
    p = setup_profiles(app, "Alpha", "Bravo", "Charlie", "Delta")   # current: Delta
    assert p.switch_target() == ("Alpha", None)                      # wraps round
    p.save("Alpha")
    assert p.switch_target() == ("Bravo", None)
    p.set_in_switch("Bravo", False)
    assert not p.in_switch("Bravo")
    assert p.switch_target() == ("Charlie", None)
    assert p.switch_names() == ["Alpha", "Charlie", "Delta"]


def test_current_unticked_goes_to_the_next_ticked(app):
    p = setup_profiles(app, "Alpha", "Bravo", "Charlie")
    p.save("Bravo")
    p.set_in_switch("Bravo", False)
    assert p.switch_target() == ("Charlie", None)


def test_nothing_to_switch_to(app):
    p = setup_profiles(app, "DJ", "Explore")
    p.set_in_switch("DJ", False)
    target, problem = p.switch_target()        # current: Explore, the only one ticked
    assert target is None and "only profile ticked" in problem
    p.set_in_switch("Explore", False)
    target, problem = p.switch_target()
    assert target is None and "no profiles are ticked" in problem


def test_new_profiles_start_ticked_and_delete_forgets(app):
    p = setup_profiles(app, "DJ")
    p.set_in_switch("DJ", False)
    p.save("Party")
    assert p.in_switch("Party")
    p.delete("DJ")
    assert "DJ" not in (p._read_env().get(p.SWITCH_OFF_KEY) or "")


def test_ticks_are_not_part_of_a_profile(app):
    p = setup_profiles(app, "DJ")
    assert p.SWITCH_OFF_KEY not in p.env_keys()


def test_shortcut_queues_the_load_and_asks_for_a_restart(app):
    p = setup_profiles(app, "DJ", "Explore")
    hotkeys = importlib.import_module("hotkeys")
    out = app.Lines()
    hotkeys._job("SWITCH_PROFILES")(out)
    assert out.has('Switching to the profile "DJ"')
    assert os.path.isfile(p.PENDING)
    assert hotkeys.take_restart() is True
    assert hotkeys.take_restart() is False   # only once


def test_shortcut_with_nothing_to_switch_to(app):
    setup_profiles(app, "DJ")
    hotkeys = importlib.import_module("hotkeys")
    out = app.Lines()
    hotkeys._job("SWITCH_PROFILES")(out)
    assert out.has("Problem:") and hotkeys.take_restart() is False


def test_unsaved_changes_are_noted_not_blocking(app):
    p = setup_profiles(app, "DJ", "Explore")
    p._write_env({"CONSOLE_MODE": "simple"})   # a change since Explore was saved
    hotkeys = importlib.import_module("hotkeys")
    out = app.Lines()
    hotkeys._job("SWITCH_PROFILES")(out)
    assert out.has("weren't saved") and out.has('Switching to the profile "DJ"')


def test_pressed_during_a_build_says_it_will_wait(app):
    hotkeys = importlib.import_module("hotkeys")
    notes, queued = [], []
    hotkeys.attach(lambda job, heading, origin=None: queued.append(heading), busy=lambda: True,
                   note=notes.append)
    try:
        hotkeys._pressed("SWITCH_PROFILES")
        hotkeys._pressed("SIMILAR_TRACKS")
    finally:
        hotkeys.attach(None)
    assert notes == ["Switch Profiles requested: it will switch once the current build has finished."]
    assert queued == ["Shortcut: Switch Profiles", "Shortcut: Similar Tracks"]


def test_settings_shows_a_tick_per_profile(app, monkeypatch):
    import tkinter as tk
    tray = importlib.import_module("tray")   # pystray needs a desktop tray; on Linux test runs there isn't one
    monkeypatch.setattr(tray, "available", lambda: False)
    monkeypatch.setattr(tray, "start", lambda *a, **k: False)
    from tkinter import ttk
    from conftest import load_gui
    p = setup_profiles(app, "DJ", "Explore")
    p.set_in_switch("DJ", False)
    gui = load_gui(app.folder)
    root = tk.Tk()
    try:
        nb = gui.TabbedPane(root, font=("Segoe UI", 10, "bold"), pad=(16, 6))
        nb.pack()
        settings = gui.SettingsTab(nb)
        boxes = [w for w in settings.profile_switch_row.winfo_children() if isinstance(w, ttk.Checkbutton)]
        assert [b.cget("text") for b in boxes] == ["DJ", "Explore"]
        assert [bool(int(root.getvar(b.cget("variable")))) for b in boxes] == [False, True]
        boxes[0].invoke()
        assert p.in_switch("DJ")
    finally:
        import gc
        settings = boxes = None
        gc.collect()   # Tk variables go while their window still exists, so none is left for later tests
        root.destroy()
