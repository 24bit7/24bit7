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
    monkeypatch.setattr(phone, "present", lambda search=False: list(answering["ids"]))
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


def test_a_phone_to_ask_about_brings_the_tab_up_with_its_question(app, ui, monkeypatch):
    """
    Ben, 25 Nov 2026 ("were you previously Ben's Phone?"): a phone 24bit7 can't tell brings the tab up with a line
    asking which phone it is and its code. A wrong code says so and changes nothing; the right one takes the line
    away and the phone is shown. With Settings > Other > Devices Off nothing brings the tab up by itself.
    """
    import engine
    import phone
    devices = []
    monkeypatch.setattr(phone, "known", lambda: list(devices))
    monkeypatch.setattr(phone, "open_device", lambda device_id, name: (_ for _ in ()).throw(RuntimeError("away")))
    phone.remember_quietly("app:old", name=BEN, model="Pixel 9a", code="1111")
    claims = []

    def claim(address, code, as_key=None, name=None):
        claims.append((address, code, as_key))
        if code != "2222":
            return None
        devices.append(("app:new", "Pixel 9a", "wifi", None))
        return "app:new"
    monkeypatch.setattr(phone, "claim", claim)
    ui.play._end_greeting()
    tab = ui.gui.attach_devices(ui.root, ui.nb, ui.play, watch=False)
    p = tab.presence
    ask = [{"address": "10.0.0.9:47247", "key": "app:new", "model": "Pixel 9a", "known": False}]
    monkeypatch.setattr(engine, "DEVICES_TAB", False)
    p.answered([], ask)
    assert tab not in ui.nb._pages, "Devices Off: nothing brings the tab up by itself"
    monkeypatch.setattr(engine, "DEVICES_TAB", True)
    p.answered([], ask)
    assert tab in ui.nb._pages, "a phone to ask about brings it up, as the question is on it"
    ui.nb.select(tab)
    ui.pump(0.3)
    texts = _texts(tab.ask_box)
    assert "A phone with the 24bit7 app is answering (Pixel 9a). Which is it?" in texts, texts
    import tkinter.ttk as ttk
    from tabs import RoundedEntry

    def find(widget, kind):
        for w in widget.winfo_children():
            if isinstance(w, kind):
                return w
            got = find(w, kind)
            if got is not None:
                return got
    pick = find(tab.ask_box, ttk.Combobox)
    assert list(pick.cget("values")) == [BEN, "A New Phone"] and pick.get() == BEN
    box = find(tab.ask_box, RoundedEntry)
    box.insert(0, "1234")
    box.entry.focus_force()   # a generated key goes to the focus widget
    ui.pump(0.2)
    box.entry.event_generate("<Return>")
    _settled(ui, tab)
    assert claims == [("10.0.0.9:47247", "1234", "app:old")]
    assert "That code isn't right. It's the four digits on the phone's screen." in _texts(tab.ask_box)
    box = find(tab.ask_box, RoundedEntry)
    box.insert(0, "2222")
    box.entry.focus_force()   # a generated key goes to the focus widget
    ui.pump(0.2)
    box.entry.event_generate("<Return>")
    _settled(ui, tab)
    assert _texts(tab.ask_box) == [], "answered: the line goes"
    assert tab.current == "app:new"
    assert not ui.errors, ui.errors[0]


def test_add_a_device_in_settings_opens_the_tab(app, ui, monkeypatch):
    """Ben, 25 Nov 2026: somewhere to add a phone before a playlist has gone to one. Settings > Other > Devices'
    + Add a Device shows the tab and takes you there, whatever answers; its switch is saved as DEVICES_TAB."""
    import engine
    import phone
    monkeypatch.setattr(phone, "known", lambda: [])
    ui.play._end_greeting()
    tab = ui.gui.attach_devices(ui.root, ui.nb, ui.play, watch=False)
    s = ui.play.settings
    assert tab not in ui.nb._pages
    s._add_device()
    ui.pump(0.3)
    assert tab in ui.nb._pages and ui.nb.select() == str(tab)
    s.vars["DEVICES_TAB"].set("Off")
    s._devices_changed()
    assert engine.DEVICES_TAB is False
    assert "DEVICES_TAB=off" in open(engine.ENV_FILE, encoding="utf-8").read()
    s.vars["DEVICES_TAB"].set("On")
    s._devices_changed()
    assert engine.DEVICES_TAB is True
    assert not ui.errors, ui.errors[0]


def test_the_first_open_draws_the_folder_once(app, ui, files, monkeypatch):
    """Ben, 25 Nov 2026: "jittery when it loaded the first time". The devices' answer drew an empty page and the
    folder's read drew it again; a device not read yet now waits for its read, so the page is drawn once."""
    import devices_gui
    import phone
    ph = _phone(app, files)
    phone.remember_quietly(BEN, name=BEN)
    draws = []
    real = devices_gui.DevicesTab.draw

    def counted(self):
        draws.append(self.current)
        return real(self)
    monkeypatch.setattr(devices_gui.DevicesTab, "draw", counted)
    tab = _tab(ui, monkeypatch, ph, [(BEN, "Pixel 9a", "usb", True)])
    _settled(ui, tab)
    assert tab.albums.rows.winfo_children(), "the folder is drawn"
    assert draws.count(BEN) == 1, draws


def test_type_its_code_reconnects_a_phone_not_answering(app, ui, monkeypatch):
    """
    Ben, 25 Nov 2026: his phone showed "not found" with "no way to enter the code". A WiFi phone not answering has
    Type Its Code... beside Rename and Forget; the code reconnects the same phone, name kept. Not for one answering.
    """
    import phone
    import tabs
    phone.remember_quietly("app:ben", name=BEN, model="Pixel 9a")
    devices = [("app:ben", "Pixel 9a", "wifi", False)]
    tab = _tab(ui, monkeypatch, None, devices, device="app:ben")
    monkeypatch.setattr(phone, "known", lambda: list(devices))
    assert tab.code_link.winfo_ismapped() and tab.code_link.cget("text") == "Type Its Code..."
    asked = []
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "1234")
    monkeypatch.setattr(phone, "reconnect", lambda key, code: asked.append((key, code)) or None)
    tab._type_code()
    _settled(ui, tab)
    assert asked == [("app:ben", "1234")]
    assert "No phone answered to that code" in tab.problem["app:ben"]
    monkeypatch.setattr(tabs, "ask_name", lambda *a, **k: "4659")

    def found(key, code):
        asked.append((key, code))
        devices[:] = [("app:ben", "Pixel 9a", "wifi", True)]
        return key
    monkeypatch.setattr(phone, "reconnect", found)
    monkeypatch.setattr(phone, "open_device", lambda device_id, name: _ReadOnly())
    tab._type_code()
    _settled(ui, tab)
    assert asked[-1] == ("app:ben", "4659")
    assert tab.answering.get("app:ben") is True and not tab.code_link.winfo_ismapped()
    assert not ui.errors, ui.errors[0]


class _ReadOnly:
    """A phone with an empty Music folder, for the read after it answers again."""
    def __new__(cls):
        from test_phone_copy import FakePhone
        ph = FakePhone()
        ph.folder("Music", make=True)
        return ph


def test_forget_and_opening_the_tab_search_the_network(app, ui, monkeypatch):
    """Ben, 25 Nov 2026: after Forget, a phone still answering waited up to five minutes to be asked about. Forget
    searches the network at once; opening the tab does too, unless it was searched in the last half minute."""
    import devices_gui
    import phone
    calls = []
    monkeypatch.setattr(devices_gui.Presence, "search_now", lambda self, older_than=0: calls.append(older_than))
    phone.remember_quietly("app:jo", name="Jo's Phone", code="1234", model="Pixel 9a")
    tab = _tab(ui, monkeypatch, None, [("app:jo", "Pixel 9a", "wifi", None)], device="app:jo")
    assert calls == [devices_gui.SEARCH_FRESH], "opening the tab"
    monkeypatch.setattr(phone, "known", lambda: [])
    tab._forget()
    _settled(ui, tab)
    assert calls[-1] == 0 and "app:jo" not in phone._meta(phone.META_KEY, {})
    assert not ui.errors, ui.errors[0]


def test_search_now_skips_a_search_this_fresh(app):
    import time
    import devices_gui
    p = devices_gui.Presence.__new__(devices_gui.Presence)
    p._wake, p._search, p.searched = None, False, time.monotonic()
    p.search_now(older_than=30)
    assert p._search is False, "searched a moment ago"
    p.search_now()
    assert p._search is True, "Forget: always"
    p._search, p.searched = False, time.monotonic() - 31
    p.search_now(older_than=30)
    assert p._search is True


def test_a_phone_just_added_shows_at_once_and_its_sort_is_counted(app, ui, files, monkeypatch):
    """
    Ben, 25 Nov 2026: Jo's phone was added, "the dialogue box goes away and it only shows my phone". Its first read
    was sorting her old folder over WiFi, and the tab waited for it without a word. Now its chip shows at once, the
    sort says how far it's got, and a read that fails still shows every device.
    """
    import threading
    import phone
    ph = _phone(app, files)
    phone.remember_quietly(BEN, name=BEN)
    phone.remember_quietly("app:jo", name="Jo's Phone", code="6575", model="Pixel 9a")
    devices = [(BEN, "Pixel 9a", "usb", True)]
    tab = _tab(ui, monkeypatch, ph, devices)
    _settled(ui, tab)
    release = threading.Event()

    def opening(device_id, name):
        if device_id == BEN:
            return ph
        release.wait(20)   # Jo's read still out
        raise RuntimeError("Jo's Phone isn't answering. Open 24bit7 on it, on the same WiFi as this PC.")
    monkeypatch.setattr(phone, "open_device", opening)
    later = devices + [("app:jo", "Pixel 9a", "wifi", None)]
    monkeypatch.setattr(phone, "known", lambda: list(later))   # a fresh list each look, as the real one gives
    tab.current = "app:jo"
    tab._job("scan")
    ui.pump(until=lambda: "Jo's Phone" in _texts(tab.chips), timeout=10)
    assert "Jo's Phone" in _texts(tab.chips) and BEN in _texts(tab.chips), "her chip before her read is back"
    tab._take(("sorting", "app:jo", 31, 84))
    assert tab.status.cget("text") == ("Sorting Music on Jo's Phone into Albums and Playlists, once: 31 of 84 files "
                                       "moved. Keep the 24bit7 app open on it.")
    tab.draw()
    assert "31 of 84" in tab.status.cget("text"), "a redraw keeps the count"
    release.set()
    _settled(ui, tab)
    assert "Jo's Phone" in _texts(tab.chips) and "app:jo" not in tab.sorting
    assert tab.status.cget("text") == "Jo's Phone isn't answering. Open the 24bit7 app on it."
    tab._take(("failed", "app:jo", "boom"))
    assert "Jo's Phone" in _texts(tab.chips) and BEN in _texts(tab.chips), "a failed read keeps every chip"
    assert not ui.errors, ui.errors[0]
