"""
What the Devices tab reads (Ben, 25 Nov 2026, as drawn: mockups/devices_and_hits.html): every device 24bit7 knows
(phone.known, any_known), Forget (which never touches the phone), and the library box's finds (library.find_items,
artist_keys, album_counts). No phone or library of Ben's: a stand-in for Windows' list of phones, and the fake
library.
"""


def test_known_lists_every_device_and_forget_touches_nothing_on_it(app, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "devices", lambda: [("usb-1", "Pixel 9a")])
    monkeypatch.setattr(phone, "_link_usb", lambda device_id, model: device_id)
    assert not phone.any_known(), "nothing remembered: the tab waits for a phone"
    phone.remember(phone.PC, folder="")
    assert not phone.any_known(), "This PC counts only once it has a folder"
    phone.remember(phone.PC, folder="C:\\Phone Sync")
    phone.remember("usb-1", name="Ben's Phone")
    phone.remember_quietly("app:jo", name="Jo's Phone", code="1234", model="Pixel 9a")
    phone.remember_quietly("usb-old", name="Old Phone", model="Pixel 6")
    assert phone.any_known()
    assert phone.known() == [("usb-1", "Pixel 9a", "usb", True), ("app:jo", "Pixel 9a", "wifi", None),
                             ("usb-old", "Pixel 6", "usb", False), (phone.PC, "This PC", "pc", True)], \
        "plugged in first, then WiFi (asked on a thread) and one not plugged in, then This PC"
    assert phone.last_device() == "usb-1"
    phone.forget("usb-1")
    assert phone.last_device() is None
    assert phone.settings("usb-1", "Pixel 9a")["name"] == "Pixel 9a", "its name, folder and records gone"
    assert phone.known()[0] == ("usb-1", "Pixel 9a", "usb", True), "still plugged in, so still shown"
    phone.forget("app:jo")
    assert [d for d, *_ in phone.known()] == ["usb-1", "usb-old", phone.PC]


def test_forget_takes_the_usb_link_with_it(app, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "devices", lambda: [])
    phone.remember_quietly("app:jo", name="Jo's Phone", code="1234")
    phone._set_meta(phone.LINKS_KEY, {"usb-jo": "app:jo", "usb-ben": "app:ben"})
    phone.forget("app:jo")
    assert phone._meta(phone.LINKS_KEY, {}) == {"usb-ben": "app:ben"}
    assert not phone.any_known()


def test_the_library_box_finds_artists_albums_and_tracks(app):
    app.library.load()
    lib = app.library
    assert lib.find_items("h") == {"artists": [], "albums": [], "tracks": []}, "two letters before it looks"
    found = lib.find_items("help")
    assert found["albums"] == [("Help!", "The Beatles")]
    assert [(name, by) for name, by, _key in found["tracks"]] == [("Help!", "The Beatles")]
    assert lib.find_items("beat")["artists"] == ["The Beatles"]
    assert len(lib.find_items("e", limit=3)["tracks"]) == 0
    assert len(lib.find_items("th", limit=3)["tracks"]) == 3, "at most limit of each"
    floyd = lib.artist_keys("Pink Floyd")
    assert len(floyd) == 4 and floyd == lib.album_keys("Meddle", "Pink Floyd"), "album by album, in track order"
    assert lib.album_counts()[("Meddle", "Pink Floyd")] == 4
    stones = lib.artist_keys("Julia Stone")
    assert len(stones) == 1, "an artist on someone else's album: their tracks only"
