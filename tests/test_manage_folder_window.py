"""
Manage Folder and Open Folder on screen (Ben, 24 Nov 2026, as drawn): beside Browse in Save's Folder line; Manage
Folder lists the folder's playlists, then artists and albums, an album opening to its tracks, "in no playlist" in
amber; ticking says in amber what Delete takes, Delete takes it and the list is read again. Open Folder hides for
a phone over WiFi. Against the fake phone from test_phone_copy.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)
from test_manage_folder import _phone
from test_phone_copy import files   # noqa: F401  (the tracks fixture)


def _texts(widget):
    out = []
    for w in widget.winfo_children():
        try:
            if w.cget("text"):
                out.append(w.cget("text"))
        except Exception:
            pass
        out += _texts(w)
    return out


def test_manage_folder_lists_ticks_and_deletes(app, ui, files, monkeypatch):
    import phone
    ph = _phone(app, files)
    monkeypatch.setattr(phone, "open_device", lambda device_id, name: ph)
    ui.play._end_greeting()
    win = ui.gui.ManageFolder(ui.play, "usb-1", "Ben's Phone", "Music", 30.0, model="Pixel 9a")
    ui.pump(until=lambda: win.contents is not None, timeout=15)
    ui.pump(0.2)
    shown = _texts(win.rows)
    assert shown[:2] == ["PLAYLISTS", "Hand"] and "ARTISTS AND ALBUMS" in shown
    assert "Radiohead" in shown and "OK Computer" not in shown, "artists start closed"
    assert win.used_label.cget("text") == "1 MB used of your 30 GB limit"
    assert win.free_label.cget("text").endswith("free on Ben's Phone")
    win._fold("Pink Floyd")
    ui.pump(0.2)
    assert "in no playlist" in _texts(win.rows)
    win._fold("Radiohead")
    win._fold("Radiohead/In Rainbows")
    ui.pump(0.2)
    assert "02 Bodysnatchers.flac" in _texts(win.rows), "an album opens to its tracks"
    assert win.note.cget("text") == "Tick what to take off, then Delete."
    win.tick_for[("pl", "road trip.m3u8")].invoke()   # a click: ticked, then unticked
    assert ("pl", "road trip.m3u8") in win.ticked and win.note.cget("text").startswith("Deleting Road Trip")
    win.tick_for[("pl", "road trip.m3u8")].invoke()
    assert not win.ticked and win.tick_for[("pl", "road trip.m3u8")].instate(["!selected"])
    win.tick_for[("dir", "Radiohead")].invoke()
    assert win.tick_for[("dir", "Radiohead/In Rainbows")].instate(["selected", "disabled"]), "inside a ticked artist"
    win.tick_for[("dir", "Radiohead")].invoke()
    win.tick_for[("dir", "Radiohead/In Rainbows")].invoke()
    ui.pump(0.2)
    assert win.note.cget("text") == ("Deleting In Rainbows takes 2 tracks (1 MB) off Ben's Phone and out of Hand, "
                                     "Indie-Chill and Road Trip.")
    win.ok()
    ui.pump(until=lambda: not win.busy, timeout=15)
    ui.pump(0.3)
    assert ph.names("Music/Radiohead") == ["OK Computer"]
    assert win.changed and not win.ticked
    assert "In Rainbows" not in _texts(win.rows), "read again after the delete"
    log = ui.play.log.get("1.0", "end")
    assert "Deleted 2 tracks (1 MB) from Music on Ben's Phone." in log, log
    win.cancel()
    assert not ui.errors, ui.errors[0]


def test_open_folder_beside_browse_and_hidden_for_wifi(app, ui, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "targets", lambda: [("app:1", "Pixel 9a"), (phone.PC, "This PC")])
    monkeypatch.setattr(phone, "open_device", lambda device_id, name: (_ for _ in ()).throw(RuntimeError("away")))
    ui.play._end_greeting()
    save = ui.gui.SavePrompt(ui.play, "What's playing in Speakers (3 tracks, 1 MB).", "Mix", 1_000_000)
    ui.pump(0.2)
    save.copy_var.set(True)
    save._copy_toggled()
    ui.pump(0.3)
    assert save._device()[0] == "app:1"
    assert not save.open_link.winfo_ismapped() and save.manage_link.winfo_ismapped(), "Explorer can't reach WiFi"
    save.device_cb.current(1)
    save._device_picked()
    ui.pump(0.2)
    assert save.open_link.winfo_ismapped()
    save.folder_box.delete(0, "end")
    save._manage_folder()
    assert save.warn.cget("text") == "Choose a folder on this PC with Browse."
    save.destroy()
    assert not ui.errors, ui.errors[0]
