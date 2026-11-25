"""
The Devices tab on screen (Ben, 25 Nov 2026, as drawn: mockups/devices_and_hits.html), in place of Manage Folder.
It shows after Settings once 24bit7 knows a device; Albums (artists closed to start, opening to albums and tracks)
and Playlists side by side; ticking says in amber what Delete takes, Delete takes it and the folder is read again;
a phone on WiFi that isn't answering says to open the app, with Open Folder hidden; the library box adds an album
straight into Albums; Save's Open Devices brings the tab forward. Against the fake phone from test_phone_copy.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)
from test_manage_folder import _phone
from test_phone_copy import FakePhone, files   # noqa: F401  (the fake phone and the tracks fixture)

BEN = "Ben's Phone"   # the fake phone has no device id, so 24bit7 keeps its records under its name


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


def _tab(ui, monkeypatch, ph, known, device=BEN):
    import phone
    monkeypatch.setattr(phone, "known", lambda: known)
    monkeypatch.setattr(phone, "open_device", lambda device_id, name: ph if ph is not None else
                        (_ for _ in ()).throw(RuntimeError("not answering")))
    ui.play._end_greeting()
    tab = ui.gui.attach_devices(ui.root, ui.nb, ui.play, watch=False)
    tab.presence.show()
    ui.nb.select(tab)
    tab.shown()
    ui.pump(until=lambda: device in tab.contents or tab.answering.get(device) is False, timeout=15)
    ui.pump(0.3)
    return tab


def _settled(ui, tab):
    """Every job the tab's worker had done and its news read (the worker waits a moment before it ends)."""
    ui.pump(until=lambda: tab._poll is None and tab._jobs.empty(), timeout=15)
    ui.pump(0.2)


def test_the_tab_shows_only_while_a_phone_answers(app, ui, monkeypatch):
    """
    Ben, 25 Nov 2026: the Devices tab only "when 24bit7 detects an open phone", a phone plugged in over USB too.
    It comes and goes with what answers, but never from under you: on it, it waits until you leave. Kept, not
    destroyed, so it comes back as it was. Then the looking itself, on its thread.
    """
    import phone
    monkeypatch.setattr(phone, "known", lambda: [])
    ui.play._end_greeting()
    tab = ui.gui.attach_devices(ui.root, ui.nb, ui.play, watch=False)
    p = tab.presence
    assert tab not in ui.nb._pages, "nothing answering: no tab"
    p.answered(["usb-1"])
    assert tab in ui.nb._pages
    ui.nb.select(tab)
    ui.pump(0.2)
    p.answered([])
    assert tab in ui.nb._pages and ui.nb.select() == str(tab), "not from under you"
    ui.nb.select(ui.play)
    ui.pump(0.2)
    assert tab not in ui.nb._pages and tab.winfo_exists(), "gone once you left it, the page kept"
    p.answered(["app:jo"])
    assert tab in ui.nb._pages
    p.answered([])
    assert tab not in ui.nb._pages, "not on it: gone straight away"
    answering = {"ids": ["usb-1"]}
    monkeypatch.setattr(phone, "present", lambda: list(answering["ids"]))
    p.watch(every=0.2)
    try:
        ui.pump(until=lambda: tab in ui.nb._pages, timeout=10)
        assert tab in ui.nb._pages, "the looking found the phone"
        answering["ids"] = []
        ui.pump(until=lambda: tab not in ui.nb._pages, timeout=10)
        assert tab not in ui.nb._pages, "and saw it go"
    finally:
        p.stop()
    assert not ui.errors, ui.errors[0]


def test_clicking_the_tab_again_leaves_the_rows_alone(app, ui, files, monkeypatch):
    """
    Ben, 25 Nov 2026: clicking the tab was "a bit jittery". Each click looked for the devices again and read the
    folder again, and each answer rebuilt the chips and every row, twice. Now what finds the same leaves them be.
    """
    import phone
    ph = _phone(app, files)
    phone.remember_quietly(BEN, name=BEN)
    tab = _tab(ui, monkeypatch, ph, [(BEN, "Pixel 9a", "usb", True)])
    _settled(ui, tab)
    rows, chips = tab.albums.rows.winfo_children(), tab.chips.winfo_children()
    lists = tab.lists.rows.winfo_children()
    assert rows and chips and lists
    ui.nb.select(ui.play)
    ui.pump(0.2)
    ui.nb.select(tab)
    tab.shown()
    _settled(ui, tab)
    assert tab.albums.rows.winfo_children() == rows and all(w.winfo_exists() for w in rows), "the same rows"
    assert tab.lists.rows.winfo_children() == lists and tab.chips.winfo_children() == chips
    assert not ui.errors, ui.errors[0]


def test_the_tab_lists_ticks_and_deletes(app, ui, files, monkeypatch):
    import phone
    ph = _phone(app, files)
    phone.remember_quietly(BEN, name=BEN)
    tab = _tab(ui, monkeypatch, ph, [(BEN, "Pixel 9a", "usb", True)])
    assert tab.winfo_ismapped() and tab.current == BEN
    assert "Ben's Phone" in _texts(tab.chips) and "USB" in _texts(tab.chips)
    assert tab.folder_label.cget("text") == "Music"
    assert tab.meter_label.cget("text").startswith("1 MB in Music · ") and \
        tab.meter_label.cget("text").endswith("free on Ben's Phone"), tab.meter_label.cget("text")
    assert tab.status.cget("text") == "" and tab.open_button.winfo_ismapped()
    albums, lists = _texts(tab.albums.rows), _texts(tab.lists.rows)
    assert "Pink Floyd" in albums and "Radiohead" in albums and "OK Computer" not in albums, "artists start closed"
    assert tab.albums_head.cget("text") == "3 albums, 1 MB"
    assert [x for x in lists if x in ("Hand", "Indie-Chill", "Road Trip")] == ["Hand", "Indie-Chill", "Road Trip"]
    tab._fold(("dir", "Albums/Radiohead"))
    tab._fold(("pl", "indie-chill.m3u8"))
    ui.pump(0.2)
    albums, lists = _texts(tab.albums.rows), _texts(tab.lists.rows)
    assert "OK Computer" in albums and "in Hand" in albums
    assert "Radiohead - Airbag" in lists and "also in Road Trip" in lists, "a playlist opens to its songs"
    assert tab.note.cget("text") == "Tick what to take off, then Delete."
    tab.tick_for[("pl", "road trip.m3u8")].invoke()
    assert tab.note.cget("text").startswith("Deleting Road Trip"), tab.note.cget("text")
    tab.tick_for[("pl", "road trip.m3u8")].invoke()
    assert not tab.ticked
    tab.tick_for[("dir", "Albums/Radiohead")].invoke()
    assert tab.tick_for[("dir", "Albums/Radiohead/In Rainbows")].instate(["selected", "disabled"]), \
        "inside a ticked artist"
    tab.tick_for[("dir", "Albums/Radiohead")].invoke()
    tab.tick_for[("dir", "Albums/Radiohead/In Rainbows")].invoke()
    assert tab.note.cget("text") == "Deleting In Rainbows takes 2 tracks (1 MB) off Ben's Phone and out of Hand."
    tab.delete()
    ui.pump(until=lambda: not tab.busy, timeout=15)
    ui.pump(0.3)
    assert ph.names("Music/Albums/Radiohead") == ["OK Computer"]
    assert "In Rainbows" not in _texts(tab.albums.rows), "read again after the delete"
    assert "Deleted 2 tracks (1 MB) from Music on Ben's Phone." in ui.play.log.get("1.0", "end")
    assert not ui.errors, ui.errors[0]


def test_a_phone_on_wifi_not_answering_says_to_open_the_app(app, ui, monkeypatch):
    import phone
    phone.remember_quietly("app:jo", name="Jo's Phone", code="1234", model="Pixel 9a")
    tab = _tab(ui, monkeypatch, None, [("app:jo", "Pixel 9a", "wifi", None)], device="app:jo")
    assert tab.status.cget("text") == "Jo's Phone isn't answering. Open the 24bit7 app on it."
    assert "not found" in _texts(tab.chips)
    assert not tab.open_button.winfo_ismapped(), "Explorer can't reach a phone on WiFi"
    tab.add(("artist", "Pink Floyd"))
    assert tab.note.cget("text") == "Choose a device that's answering first."
    assert not ui.errors, ui.errors[0]


def test_the_library_box_adds_an_album_into_albums(app, ui, files, monkeypatch):
    import phone
    ph = FakePhone()
    phone.remember_quietly(BEN, name=BEN)
    meddle = files(("Pink Floyd", "One Of These Days", 100, "Meddle", 1), ("Pink Floyd", "Echoes", 200, "Meddle", 4))
    monkeypatch.setattr(phone, "tracks_for", lambda keys: meddle)
    tab = _tab(ui, monkeypatch, ph, [(BEN, "Pixel 9a", "usb", True)])
    assert "No albums on it yet. Type an artist, album or track above to add one." in _texts(tab.albums.rows)
    groups = tab.suggestions("meddle")
    assert groups == [("Albums", [("Meddle · Pink Floyd", ("album", ("Meddle", "Pink Floyd")))])]
    tab.find_box.entry.insert(0, "medd")
    tab._suggest()
    ui.pump(0.2)
    assert tab._pop is not None and tab._pop.rows[0][0] == ("album", ("Meddle", "Pink Floyd"))
    tab.add(groups[0][1][0][1])
    assert tab._pop is None and tab.busy
    ui.pump(until=lambda: not tab.busy, timeout=15)
    ui.pump(0.3)
    assert ph.names("Music/Albums/Pink Floyd/Meddle") == ["01 One Of These Days.flac", "04 Echoes.flac"]
    albums = _texts(tab.albums.rows)
    assert "Pink Floyd" in albums and "2 tracks of Meddle" in albums, "two of Meddle's four: said on the row"
    log = ui.play.log.get("1.0", "end")
    assert "Adding Meddle to Ben's Phone..." in log and "Added Meddle to Music/Albums on Ben's Phone" in log, log
    assert not ui.errors, ui.errors[0]


def test_save_opens_devices_at_the_phone(app, ui, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "targets", lambda: [("app:1", "Pixel 9a"), (phone.PC, "This PC")])
    monkeypatch.setattr(phone, "known", lambda: [("app:1", "Pixel 9a", "wifi", None)])
    monkeypatch.setattr(phone, "open_device", lambda device_id, name: (_ for _ in ()).throw(RuntimeError("away")))
    ui.play._end_greeting()
    tab = ui.gui.attach_devices(ui.root, ui.nb, ui.play, watch=False)
    assert tab not in ui.nb._pages, "no device known yet: no tab"
    save = ui.gui.SavePrompt(ui.play, "What's playing in Speakers (3 tracks, 1 MB).", "Mix", 1_000_000)
    ui.pump(0.2)
    save.copy_var.set(True)
    save._copy_toggled()
    ui.pump(0.3)
    assert save.clear_tick.cget("text") == "Clear Playlists First"
    assert save.clear_note.cget("text") == "Takes off the playlists already on Pixel 9a. Your albums stay."
    assert not save.open_link.winfo_ismapped() and save.devices_link.winfo_ismapped(), "Explorer can't reach WiFi"
    save._open_devices()
    ui.pump(until=lambda: "app:1" in tab.answering, timeout=15)
    ui.pump(0.3)
    assert not save.winfo_exists() and save.result is None
    assert tab in ui.nb._pages and ui.nb.select() == str(tab), "the tab added and brought forward"
    assert tab.current == "app:1"
    assert not ui.errors, ui.errors[0]
