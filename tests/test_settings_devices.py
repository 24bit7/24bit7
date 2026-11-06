"""
The Devices box (Ben, 2 Nov 2026; renamed from Device Playlists and Last heard dropped, 3 Nov 2026), on a
Devices tab of its own again since 5 Nov 2026, with the same page as Playlist Settings: a tab per Alexa device; Plays to, Remove and Enable
Switch To; four phrase rows, each the playlist that phrase runs, greyed until the device has its own (tagged
Standard while it's the standard); Restore Default Device Playlists. A row opens its page with "Copy Settings
From:" on the first row. The Zones section stays under Other and Voice Commands keeps the switch timing.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui, KITCHEN, LOUNGE  # noqa: F401  (the GUI fixture)
from test_settings_buttons import walk, labels, settings_pane, tab_titles, page_named


def box_page(ui, device_id=KITCHEN):
    page_named(ui, "Devices")
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
    assert "Playlist Settings" in titles and "Devices" in titles and "Zones" not in titles
    assert titles.index("Devices") == titles.index("Playlist Settings") + 1, "Devices straight after Playlist Settings"
    tabs_ = [w.cget("text") for w in walk(s._device_tabs) if isinstance(w, tk.Label)]
    assert set(tabs_) == {"Kitchen Echo", "Lounge Dot"}
    assert row_texts(s) == [("Music like: Similar Artists", "Standard"), ("Songs by: Artist's Top Tracks", "Standard"),
                            ("Tracks like this: Similar Tracks", "Standard"), ("Genre: AI Playlist", "Standard")]
    texts = labels(s._device_head)
    assert "Plays to" in texts and "Remove" in texts and "Enable Switch To" in texts
    assert not any(x.startswith("Last heard") for x in texts), "Last heard went (Ben, 3 Nov 2026)"
    outer = labels(s._buttons_outer)
    assert "Your Playlist Buttons" in outer and "Devices" not in outer, "the Devices box left Playlist Settings"
    own = labels(s._devices_outer)
    assert "Devices" in own and "Device Playlists" not in own and "Your Playlist Buttons" not in own
    assert "Restore Default Device Playlists" in own and "Restore Default Playlists" not in own
    assert not ui.errors, ui.errors[0]


def test_copy_settings_from_links_hides_the_page_and_unticking_makes_the_devices_own(app, ui, monkeypatch):
    """Ben, 3 Nov 2026: a row opens a page whose first row is "[x] Copy Settings From: [playlist]", no explanation.
    Ticked, the phrase runs that playlist as it is (any kind, chosen in the dropdown) and nothing shows below.
    Unticked, the device gets its own copy, set up below, with the dropdown greyed at what it was copied from.
    Ticking again asks, then deletes the device's own."""
    import buttons
    import devices
    from tkinter import messagebox
    s = box_page(ui)
    standard = buttons.standard("top")
    s._device_rows[1][1].event_generate("<Button-1>")   # Songs by, greyed
    ui.pump(0.4)
    assert s._from_device == (KITCHEN, "songs_by") and s._button_id == standard["id"], "the playlist it runs"
    assert [row.chosen for _p, row, _b, _o in s._device_rows] == [False, True, False, False], "the clicked row is outlined"
    assert not any(r[1].chosen for r in s._button_rows), "only the device row is outlined, not the button it copies"
    assert s._device_strip_tick.cget("text") == "Copy Settings From:" and s._device_strip_tick.instate(["selected"])
    assert labels(s._device_strip) == ["Copy Settings From:"], "the tick alone, no explanation (Ben, 3 Nov 2026)"
    assert s._device_strip_from.get() == "Artist's Top Tracks" and "Similar Artists" in s._device_strip_from.cget("values")
    assert s._button_page is None and not s._name_box.winfo_ismapped(), "ticked: nothing below the line"
    assert s._preview is None and s._preview_frame is None, "no Preview on a device's page (Ben, 3 Nov 2026)"
    # another playlist in the dropdown, any kind: linked as it is, no copy
    s._device_strip_from.set("Similar Artists")
    s._device_strip_from.event_generate("<<ComboboxSelected>>")
    ui.pump(0.4)
    linked = buttons.standard("artists")
    assert devices.playlist_for(KITCHEN, "songs_by")["id"] == linked["id"] and buttons.of_device(KITCHEN) == []
    assert row_texts(s)[1] == ("Songs by: Similar Artists", "Standard") and s._button_page is None
    # unticked: the device's own, copied from the chosen one, its settings below
    s._device_strip_tick.invoke()
    ui.pump(0.5)
    own = buttons.of_device(KITCHEN)
    assert len(own) == 1 and own[0]["kind"] == "artists" and own[0]["copied_from"] == linked["id"]
    assert devices.playlist_for(KITCHEN, "songs_by")["id"] == own[0]["id"] and s._button_id == own[0]["id"]
    assert row_texts(s)[1] == (f"Songs by: {own[0]['name']}", ""), "its own: full colour, no tag"
    assert not s._device_strip_tick.instate(["selected"]) and s._device_strip_from.instate(["disabled"])
    assert s._device_strip_from.get() == "Similar Artists", "greyed at what it was copied from"
    assert s._button_page is not None and s._name_box.winfo_ismapped(), "its settings show"
    assert s._preview is None, "no Preview on the device's own page either"
    assert own[0]["name"] not in s._button_names(), "not in the buttons list"
    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: asked.append(a[1]) or False)
    s._device_strip_tick.invoke()
    ui.pump(0.3)
    assert asked and buttons.of_device(KITCHEN), "a no keeps it"
    assert not s._device_strip_tick.instate(["selected"])
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._device_strip_tick.invoke()
    ui.pump(0.4)
    assert buttons.of_device(KITCHEN) == [] and devices.playlist_for(KITCHEN, "songs_by")["id"] == linked["id"]
    assert s._from_device == (KITCHEN, "songs_by") and s._device_strip_tick.instate(["selected"])
    page_named(ui, "Playlist Settings")
    assert s._from_device is None and s._device_strip is None, "Playlist Settings leaves the device's page"
    assert not any(row.chosen for _p, row, _b, _o in s._device_rows), "no device row outlined"
    assert not ui.errors, ui.errors[0]


def test_devices_is_a_tab_of_its_own_and_each_tab_keeps_its_page(app, ui):
    """Ben, 5 Nov 2026: Settings > Playlist Settings split in two. Each tab is the old one minus the other box,
    the same page on the right of both. The page is built on whichever tab is showing; each remembers its own."""
    import buttons
    s = ui.settings
    page_named(ui, "Playlist Settings")
    chosen = buttons.standard("tracks")["id"]
    s._pick_button(chosen)
    ui.pump(0.3)
    assert s._button_right is s._list_right and s._name_box.winfo_ismapped()
    assert not s._device_right.winfo_children(), "nothing built on the hidden tab"
    page_named(ui, "Devices")
    assert s._button_right is s._device_right and not s._list_right.winfo_children()
    assert s._from_device == (KITCHEN, "music_like"), "the chosen device's first phrase opens"
    assert s._device_strip is not None and s._device_strip.winfo_ismapped(), "Copy Settings From on its first row"
    s._device_rows[2][1].event_generate("<Button-1>")   # Tracks like this
    ui.pump(0.4)
    assert s._from_device == (KITCHEN, "tracks_like")
    page_named(ui, "Playlist Settings")
    assert s._button_right is s._list_right and s._from_device is None and s._device_strip is None
    assert s._button_id == chosen, "back on Playlist Settings, the playlist chosen there"
    assert [r for r in s._button_rows if r[0] == chosen][0][1].chosen
    page_named(ui, "Devices")
    assert s._from_device == (KITCHEN, "tracks_like"), "back on Devices, the row opened there"
    s.show_playlist(buttons.standard("top")["id"])   # the Play tab's cog, from the Devices tab
    ui.pump(0.4)
    assert s._button_right is s._list_right and s._from_device is None
    assert s._button_id == buttons.standard("top")["id"] and s._name_box.winfo_ismapped()
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
    assert s._device_id == LOUNGE and s._from_device == (LOUNGE, "music_like"), "the next device's page opens"
    assert not ui.errors, ui.errors[0]


def test_restore_default_device_playlists(app, ui, monkeypatch):
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
    s._device_slot_page(KITCHEN, "music_like")
    devices.make_own(KITCHEN, "music_like")
    s._device_restore_defaults()
    ui.pump(0.3)
    assert s._from_device == (KITCHEN, "music_like") and s._button_id == buttons.standard("artists")["id"],         "the open device page shows the standard after a restore"
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
