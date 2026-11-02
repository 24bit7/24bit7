"""
The Device Playlists box under Settings > Playlist Settings (Ben, 2 Nov 2026), in place of the Devices
tab: a tab per Alexa device; Plays to, Remove, Enable Switch To and Last heard; four phrase rows, each
the playlist that phrase runs, greyed with a Standard tag until the device has its own; Restore Default
Device Playlists. The Zones section stays under Other and Voice Commands keeps the switch timing.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui, KITCHEN, LOUNGE  # noqa: F401  (the GUI fixture)
from test_settings_buttons import walk, labels, settings_pane, tab_titles, page_named


def box_page(ui, device_id=KITCHEN):
    page_named(ui, "Playlist Settings")
    s = ui.settings
    s._buttons_refresh()
    s._device_pick(device_id)
    ui.pump(0.3)
    return s


def row_texts(s):
    return [(row.text, row.tag) for _phrase, row, _playlist, _own in s._device_rows]


def test_the_box_lists_the_devices_as_tabs_with_the_standards_greyed(app, ui):
    s = box_page(ui)
    titles = tab_titles(settings_pane(ui))
    assert "Playlist Settings" in titles and "Devices" not in titles and "Zones" not in titles
    tabs_ = [w.cget("text") for w in walk(s._device_tabs) if isinstance(w, tk.Label)]
    assert set(tabs_) == {"Kitchen Echo", "Lounge Dot"}
    assert row_texts(s) == [("Music like: Similar Artists", "Standard"), ("Songs by: Artist's Top Tracks", "Standard"),
                            ("Tracks like this: Similar Tracks", "Standard"), ("Genre: AI Playlist", "Standard")]
    texts = labels(s._device_head)
    assert "Plays to" in texts and "Remove" in texts and "Enable Switch To" in texts
    assert any(x.startswith("Last heard") for x in texts)
    assert "Your Playlist Buttons" in labels(s._buttons_outer) and "Device Playlists" in labels(s._buttons_outer)
    assert not ui.errors, ui.errors[0]


def test_a_greyed_row_makes_the_devices_own_and_right_click_puts_the_standard_back(app, ui, monkeypatch):
    import buttons
    import devices
    import settings_gui
    s = box_page(ui)
    opened = []

    class FakePrompt:
        def __init__(self, parent, device=None):
            opened.append(device)
            self.result = ("template", "inner_circle")
    monkeypatch.setattr(settings_gui, "AddPlaylistPrompt", FakePrompt)
    monkeypatch.setattr(s, "wait_window", lambda w: None)
    s._device_make_own("music_like", "Music like")
    ui.pump(0.4)
    assert opened == [("Kitchen Echo", "Music like")]
    own = buttons.of_device(KITCHEN)
    assert [b["name"] for b in own] == ["Kitchen Echo Similar Artists"] and own[0]["made"] == "inner_circle"
    assert row_texts(s)[0] == ("Music like: Kitchen Echo Similar Artists", ""), "its own: full colour, no tag"
    assert s._button_id == own[0]["id"] and s._button_page.button["id"] == own[0]["id"], "its page opened on the right"
    assert "Kitchen Echo's own playlist for \"Music like\"" in " ".join(labels(s._button_right))
    assert "Kitchen Echo Similar Artists" not in s._button_names(), "not in the buttons list"
    assert "Kitchen Echo Similar Artists" not in [b._name for b in ui.play.play_buttons], "nor on the Play tab"
    assert devices.playlist_for(KITCHEN, "music_like")["id"] == own[0]["id"]
    s._device_back_to_standard("music_like", own[0])
    ui.pump(0.3)
    assert buttons.of_device(KITCHEN) == [] and row_texts(s)[0][1] == "Standard"
    assert s._button_id == buttons.buttons_only()[0]["id"], "the page falls back to the first button"
    assert not ui.errors, ui.errors[0]


def test_zone_switch_rename_and_remove_live_in_the_box(app, ui, monkeypatch):
    import devices
    import tabs
    s = box_page(ui)
    s._device_zone_cb.set("Sonos")
    s._device_zone_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.4)
    assert dict((d[0], d[2]) for d in app.voice.devices())[KITCHEN] == "Sonos"
    assert "disabled" not in s._device_switch.state()
    s._device_switch.invoke()
    ui.pump(0.2)
    assert "Sonos" in app.voice.switch_unticked()
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "Kitchen Dot")
    s._device_rename(KITCHEN, "Kitchen Echo")
    ui.pump(0.3)
    assert dict((d[0], d[1]) for d in app.voice.devices())[KITCHEN] == "Kitchen Dot"
    assert "Kitchen Dot" in [w.cget("text") for w in walk(s._device_tabs) if isinstance(w, tk.Label)]
    devices.make_own(KITCHEN, "tracks_like")
    from tkinter import messagebox
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._device_remove()
    ui.pump(0.3)
    assert KITCHEN not in [d[0] for d in app.voice.devices()] and KITCHEN not in devices.load()
    import buttons
    assert buttons.of_device(KITCHEN) == [], "its own playlists went with it"
    assert s._device_id == LOUNGE
    assert not ui.errors, ui.errors[0]


def test_restore_default_device_playlists_and_the_add_window_for_a_device(app, ui, monkeypatch):
    import buttons
    import devices
    import settings_gui
    s = box_page(ui)
    devices.make_own(KITCHEN, "music_like")
    devices.make_own(KITCHEN, "play_something", ("copy", buttons.standard("vibe")["id"]))
    s._buttons_refresh()
    ui.pump(0.3)
    assert [tag for _t, tag in row_texts(s)] == ["", "Standard", "Standard", ""]
    from tkinter import messagebox
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._device_restore_defaults()
    ui.pump(0.3)
    assert buttons.of_device(KITCHEN) == [] and [tag for _t, tag in row_texts(s)] == ["Standard"] * 4
    win = settings_gui.AddPlaylistPrompt(ui.settings, device=("Kitchen Echo", "Songs by"))
    ui.pump(0.5)
    assert win.title() == 'Give Kitchen Echo its own "Songs by" playlist'
    assert set(win._tabs) == {"existing", "template"}, "no New for a device"
    assert win.ok_button.cget("text") == "Use a Copy"
    assert "A copy of it becomes Kitchen Echo's own for \"Songs by\"" in win.existing_note.cget("text")
    win._pick_tab("template")
    ui.pump(0.2)
    assert win.ok_button.cget("text") == "Use the Template"
    win._tab_by(1)
    assert win._tab == "existing", "round the two"
    win.destroy()
    assert not ui.errors, ui.errors[0]


def test_zones_are_back_under_other_and_voice_keeps_the_timing(app, ui):
    import settings_gui
    other = page_named(ui, "Other")
    ui.pump(0.8)
    texts = labels(other)
    assert "Follow JRiver's active zone" in texts and "Speakers" in texts and "Kitchen" in texts, texts[:40]
    s = ui.settings
    s.zone_vars["Kitchen"].set(False)
    s._save_zone_settings()
    ui.pump(0.2)
    assert settings_gui.read_env().get("HIDDEN_ZONES") == "Kitchen"
    voice = page_named(ui, "Voice Commands")
    texts = labels(voice)
    assert "Switch Timing Adjustment" in texts and "Enable Switch To" not in texts and "Last heard" not in texts
    assert not ui.errors, ui.errors[0]
