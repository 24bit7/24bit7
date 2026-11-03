"""
The Device Playlists box's model (Ben, 2 Nov 2026). A device's phrases are its slots: Music like, Songs by,
Tracks like this and Genre. A slot runs the standard playlist of its kind until the device is given its
own, a playlist marked with the device's id that lives in the box, not on the Play tab, and can be of any
kind (a phrase runs whatever the listener gives it). Reset puts a slot back; Restore does all four.
"""

ECHO = "amzn1.ask.device.ECHO"


def echo(app, name="Kitchen Echo"):
    v = app.voice
    v._hear_device(ECHO)
    v.update_device(ECHO, name=name, zone="Kitchen")


def test_a_fresh_device_runs_the_standards_and_its_rows_say_so(app):
    import buttons
    import devices
    echo(app)
    assert [label for _p, label in devices.PHRASES] == ["Music like", "Songs by", "Tracks like this", "Genre"], "as spoken"
    rows = devices.rows(ECHO)
    assert [(phrase, b["name"], own) for phrase, _label, b, own in rows] == [
        ("music_like", "Similar Artists", False), ("songs_by", "Artist's Top Tracks", False),
        ("tracks_like", "Similar Tracks", False), ("play_something", "AI Playlist", False)]
    assert devices.name_of(ECHO) == "Kitchen Echo" and devices.name_of("nobody") == "Device"


def test_make_own_copies_into_the_box_and_reset_puts_the_standard_back(app):
    import buttons
    import devices
    echo(app)
    before = [b["name"] for b in buttons.shown()]
    own = devices.make_own(ECHO, "music_like")
    assert own["device"] == ECHO and own["kind"] == "artists" and own["name"] == "Kitchen Echo Similar Artists"
    assert own["settings"] == buttons.standard("artists")["settings"], "a copy of the standard to start from"
    assert [b["name"] for b in buttons.shown()] == before, "not on the Play tab"
    assert [b["name"] for b in buttons.of_device(ECHO)] == ["Kitchen Echo Similar Artists"]
    rows = {phrase: (b["name"], is_own) for phrase, _label, b, is_own in devices.rows(ECHO)}
    assert rows["music_like"] == ("Kitchen Echo Similar Artists", True) and rows["songs_by"][1] is False
    assert devices.playlist_for(ECHO, "music_like")["id"] == own["id"]
    assert devices.playlist_for(ECHO, "more_artists")["id"] == own["id"], "the intents that mean the phrase too"
    # a second own for the same slot replaces the first
    again = devices.make_own(ECHO, "music_like", ("template", "inner_circle"))
    assert again["made"] == "inner_circle" and again["name"] == "Kitchen Echo Similar Artists"
    assert buttons.get(own["id"]) is None, "the earlier own playlist for the slot is gone"
    devices.reset(ECHO, "music_like")
    assert buttons.get(again["id"]) is None and buttons.of_device(ECHO) == []
    assert devices.playlist_for(ECHO, "music_like")["standard"] == "artists"


def test_a_phrase_can_run_any_kind_the_listener_gives_it(app):
    import buttons
    import devices
    echo(app)
    consensus = next(b for b in buttons.load() if b["name"] == "Consensus")
    hijack = devices.make_own(ECHO, "songs_by", ("copy", consensus["id"]))
    assert hijack["kind"] == "artists" and hijack["device"] == ECHO and hijack["parent"] == ""
    assert hijack["name"] == "Kitchen Echo Similar Artists"
    assert devices.playlist_for(ECHO, "songs_by")["id"] == hijack["id"], "Songs by runs an Artist Matching playlist now"
    assert buttons.get(consensus["id"])["name"] == "Consensus", "the original is untouched"
    assert devices.playlist_for("someone-else", "songs_by")["standard"] == "top"


def test_restore_defaults_and_forget_take_the_devices_playlists_with_them(app):
    import buttons
    import devices
    echo(app)
    devices.make_own(ECHO, "music_like")
    devices.make_own(ECHO, "tracks_like")
    assert len(buttons.of_device(ECHO)) == 2
    devices.restore_defaults(ECHO)
    assert buttons.of_device(ECHO) == [] and all(not own for _p, _l, _b, own in devices.rows(ECHO))
    devices.make_own(ECHO, "play_something")
    devices.forget(ECHO)
    assert buttons.of_device(ECHO) == [] and ECHO not in devices.load()
    assert buttons.standard("vibe") is not None, "only the device's own went"


def test_copy_settings_from_links_a_phrase_to_any_playlist_as_it_is(app):
    """
    Copy Settings From, ticked (Ben, 3 Nov 2026): the phrase runs the chosen playlist itself, any kind, with no
    copy made. Before this a linked playlist of another kind fell back to the standard. Linking deletes the
    device's own for the slot; linking to the standard stores no choice.
    """
    import buttons
    import devices
    echo(app)
    consensus = next(b for b in buttons.load() if b["name"] == "Consensus")
    devices.link(ECHO, "songs_by", consensus["id"])
    assert devices.playlist_for(ECHO, "songs_by")["id"] == consensus["id"], "an Artist Matching playlist for Songs by"
    assert buttons.of_device(ECHO) == [], "no copy made"
    row = next(r for r in devices.rows(ECHO) if r[0] == "songs_by")
    assert row[2]["id"] == consensus["id"] and row[3] is False, "shown greyed, not the device's own"
    own = devices.make_own(ECHO, "songs_by", ("copy", consensus["id"]))
    assert own["copied_from"] == consensus["id"], "Copy Settings From shows what it was copied from, greyed"
    devices.link(ECHO, "songs_by", buttons.standard("top")["id"])
    assert buttons.get(own["id"]) is None, "ticking again deletes the device's own"
    assert devices.for_device(ECHO)["buttons"]["songs_by"] is None, "the standard is stored as no choice"
    assert devices.playlist_for(ECHO, "songs_by")["standard"] == "top"
    buttons.remove(consensus["id"])
    devices.link(ECHO, "music_like", buttons.standard("tracks")["id"])
    assert devices.playlist_for(ECHO, "music_like")["kind"] == "tracks"
