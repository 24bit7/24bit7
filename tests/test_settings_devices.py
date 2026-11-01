"""
Settings > Devices (31 Oct 2026, in place of Zones): a page per Alexa device with its name, the zone it
plays to, Enable Switch To, and the playlist each voice phrase runs. The Zones section (Show, Default,
Follow) is back under Other, and the Voice Commands tab keeps the switch timing without a device table.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui, KITCHEN, LOUNGE  # noqa: F401  (the GUI fixture)
from test_settings_buttons import walk, labels, settings_pane, tab_titles, page_named


def devices_page(ui):
    page_named(ui, "Devices")
    return ui.settings


def pick_device(ui, device_id):
    s = devices_page(ui)
    s._devices_refresh()
    s._device_id = device_id
    s._device_fill_page()
    ui.pump(0.3)
    return s


def combos(widget):
    return [w for w in walk(widget) if isinstance(w, ttk.Combobox)]


def test_devices_tab_lists_the_devices_heard_and_their_pages(app, ui):
    s = devices_page(ui)
    titles = tab_titles(settings_pane(ui))
    assert "Devices" in titles and "Zones" not in titles
    assert s._device_list.get(0, "end") == ("Kitchen Echo", "Lounge Dot") or set(s._device_list.get(0, "end")) == {"Kitchen Echo", "Lounge Dot"}
    texts = labels(s._device_right)
    for text in ("Name", "Plays to", "Enable Switch To", "Music like", "Songs by", "Tracks like this", "Play something"):
        assert text in texts, text
    assert not ui.errors, ui.errors[0]


def test_phrase_dropdowns_pick_a_playlist_for_the_device(app, ui):
    import buttons
    import devices
    sunday = buttons.add("Sunday", "tracks")
    s = pick_device(ui, KITCHEN)
    cb = next(c for c in combos(s._device_right) if "Sunday" in c.cget("values"))
    assert tuple(cb.cget("values")) == ("Similar Tracks", "Sunday") and cb.get() == "Similar Tracks"
    cb.set("Sunday")
    cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert devices.load()[KITCHEN]["buttons"]["tracks_like"] == sunday["id"]
    assert devices.playlist_for(KITCHEN, "more_like")["id"] == sunday["id"]
    assert devices.playlist_for(LOUNGE, "tracks_like")["standard"] == "tracks", "another device is untouched"
    cb.set("Similar Tracks")
    cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert devices.load()[KITCHEN]["buttons"]["tracks_like"] is None, "the standard playlist is kept as unset"
    assert not ui.errors, ui.errors[0]


def test_name_zone_and_switch_save(app, ui):
    s = pick_device(ui, KITCHEN)
    entry = next(w for w in walk(s._device_right) if isinstance(w, tk.Entry))
    entry.delete(0, "end")
    entry.insert(0, "Kitchen Dot")
    entry.focus_force()   # Tk sends a generated key press to the focus widget
    ui.pump(0.2)
    entry.event_generate("<Return>")
    ui.pump(0.3)
    assert dict((d[0], d[1]) for d in app.voice.devices())[KITCHEN] == "Kitchen Dot"
    assert "Kitchen Dot" in s._device_list.get(0, "end") and s._device_title.cget("text") == "Kitchen Dot"
    zone_cb = next(c for c in combos(s._device_right) if "Not set" in c.cget("values"))
    zone_cb.set("Sonos")
    zone_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.4)
    assert dict((d[0], d[2]) for d in app.voice.devices())[KITCHEN] == "Sonos"
    switch = next(w for w in walk(s._device_right) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "Enable Switch To")
    assert "disabled" not in switch.state()
    switch.invoke()
    ui.pump(0.2)
    assert "Sonos" in app.voice.switch_unticked()
    assert not ui.errors, ui.errors[0]


def test_remove_forgets_the_device_and_its_choices(app, ui, monkeypatch):
    import buttons
    import devices
    from tkinter import messagebox
    sunday = buttons.add("Sunday", "tracks")
    record = devices.for_device(KITCHEN)
    record["buttons"]["tracks_like"] = sunday["id"]
    devices.update(KITCHEN, buttons=record["buttons"])
    s = pick_device(ui, KITCHEN)
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._device_remove()
    ui.pump(0.3)
    assert KITCHEN not in [d[0] for d in app.voice.devices()] and KITCHEN not in devices.load()
    assert s._device_id == LOUNGE


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
