"""
A playlist is either a button or a device's (Ben, 2 Nov 2026). The unticked state went: everything
under Your Playlist Buttons is on the Play tab, on the row or in a menu, and a device's own playlists
live in the Device Playlists box. A 1.29 database with off-the-row playlists converts once on load.
"""


def test_an_off_the_row_playlist_from_1_29_becomes_a_devices_or_comes_back_said_once(app):
    import buttons
    import devices
    items = buttons.load()
    tracks = next(b for b in items if b["standard"] == "tracks")
    guests = next(b for b in items if b["name"] == "Artist + Guests")
    tracks["shown"] = False   # as 1.29 kept a playlist off the Play tab
    guests["shown"] = False
    buttons.save(items)
    record = devices.blank()
    record["buttons"]["tracks_like"] = tracks["id"]   # a device's phrase names it: it's that device's
    devices.save({"echo-1": record})
    app.printed.clear()
    items = buttons.load()
    by = {b["name"]: b for b in items}
    assert by["Similar Tracks"]["device"] == "echo-1" and by["Similar Tracks"]["shown"] is True
    assert by["Artist + Guests"]["device"] == "" and by["Artist + Guests"]["shown"] is True, "nobody's: back on the row"
    assert [b["name"] for b in buttons.shown()] == ["Similar Artists", "Artist's Top Tracks", "Artist + Guests", "Consensus",
                                                    "AI Playlist"]
    assert [b["name"] for b in buttons.of_device("echo-1")] == ["Similar Tracks"]
    notes = [line for line in app.printed if "back on the Play tab" in line]
    assert notes == ["Note: Artist + Guests back on the Play tab: a playlist is either a button or a device's now "
                     "(Settings > Playlist Settings)."]
    app.printed.clear()
    buttons.load()
    assert not [line for line in app.printed if "back on the Play tab" in line], "said once"
    assert not hasattr(buttons, "set_shown"), "there's no untick any more"


def test_from_existing_copies_and_a_devices_playlist_is_not_offered(app):
    import buttons
    items = buttons.load()
    next(b for b in items if b["standard"] == "vibe")["device"] = "echo-1"
    buttons.save(items)
    head = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    made, wants_page = buttons.add_from_choice(("existing", head["id"]))
    assert made["name"] == "Artist + Guests 2" and wants_page is False, "an older 'existing' answer copies too"
    assert "AI Playlist" not in [b["name"] for b in buttons.shown()], "the device's own isn't a button"
