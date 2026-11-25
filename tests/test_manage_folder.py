"""
The device's folder as the Devices tab shows it (Ben, 25 Nov 2026, as drawn; Manage Folder's window until then):
Albums as artists and albums, Playlists as its playlists, ticked and deleted. A playlist ticked takes its file and
its songs in Playlists that no other playlist lists, never anything in Albums; an album or artist ticked goes whole
and every playlist listing its songs is amended, or taken off if none are left; the amber line above Delete says
what goes, so there's no further question. Against the fake phone from test_phone_copy.
"""

from test_phone_copy import FakePhone, files   # noqa: F401  (the fake phone and the tracks fixture)


def _phone(app, files):
    """Indie-Chill and Road Trip copied by 24bit7, two Radiohead albums and Wish You Were Here added, and a
    playlist made by hand that points into Albums."""
    import phone
    ph = FakePhone()
    ok1, ok2, rain1, rain2 = files(("Radiohead", "Airbag", 100, "OK Computer", 1),
                                   ("Radiohead", "Paranoid Android", 200, "OK Computer", 2),
                                   ("Radiohead", "15 Step", 300, "In Rainbows", 1),
                                   ("Radiohead", "Bodysnatchers", 400, "In Rainbows", 2))
    phone.add_albums(ph, "Music", [ok1, ok2, rain1, rain2], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Indie-Chill", [ok1, ok2, rain1], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Road Trip", [ok1, rain2], say=app.Lines())
    lists = ph.folder("Music/Playlists")
    ph.put_text(lists, "Hand.m3u8", "#EXTM3U\n#EXTINF:1,Radiohead - Bodysnatchers\n"
                                    "..\\Albums\\Radiohead\\In Rainbows\\02 Bodysnatchers.flac\nD:\\Elsewhere.flac\n")
    wish = ph.folder("Music/Albums/Pink Floyd/Wish You Were Here", make=True)
    ph.put_text(wish, "01 Shine On.flac", "x" * 500)
    ph.put_text(wish, "folder.jpg", "jpg")
    ph.put_text(ph.make(ph.folder("Music"), ".thumbnails"), "a.jpg", "x")
    return ph


def test_the_folder_is_read_as_albums_and_playlists(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    assert [(p["name"], p["tracks"]) for p in f.playlists] == [("Hand", 1), ("Indie-Chill", 3), ("Road Trip", 2)], \
        "a line with a drive isn't one of the folder's"
    tree = f.tree()
    assert [n["name"] for n in tree] == ["Pink Floyd", "Radiohead"], "Albums only; .thumbnails is never shown"
    radiohead = tree[1]
    assert (radiohead["tracks"], radiohead["size"]) == (4, 1000)
    rain, ok = radiohead["children"]
    assert (ok["name"], ok["lists"]) == ("OK Computer", []), "the playlists have their own copies"
    assert (rain["name"], rain["lists"]) == ("In Rainbows", ["Hand"])
    assert [c["name"] for c in ok["children"]] == ["01 Airbag.flac", "02 Paranoid Android.flac"], \
        "albums open to their tracks"
    wish = tree[0]["children"][0]
    assert (wish["tracks"], wish["lists"]) == (1, []), "in no playlist; folder.jpg isn't a track"
    assert f.size == 1000 + 500 + 3 + 100 + 200 + 300 + 400, "Albums and Playlists"


def test_a_playlist_ticked_takes_its_own_songs_never_an_album(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(playlists=["indie-chill.m3u8"])
    assert sorted(plan["files"]) == ["playlists/radiohead - 15 step.flac",
                                     "playlists/radiohead - paranoid android.flac"]
    assert plan["tracks"] == 2 and plan["kept"] == 1, "Airbag stays: Road Trip lists it"
    assert f.plan_text(plan, "Indie-Chill") == "Deleting Indie-Chill takes 2 tracks (1 MB) off Ben's Phone."
    said = app.Lines()
    f.delete(plan, say=said)
    assert ph.names("Music/Playlists") == ["Hand.m3u8", "Radiohead - Airbag.flac", "Radiohead - Bodysnatchers.flac",
                                           "Road Trip.m3u8"]
    assert ph.names("Music/Albums/Radiohead/OK Computer") == ["01 Airbag.flac", "02 Paranoid Android.flac"]
    assert said.has("Took Indie-Chill off Ben's Phone.") and said.has("Deleted 2 tracks (1 MB) from Music"), \
        said.text()
    copied = phone._records(ph)[1]["music/playlists"]
    assert "indie-chill.m3u8" not in copied and "road trip.m3u8" in copied, "24bit7's records kept in step"


def test_a_playlist_whose_songs_are_all_in_albums_takes_only_its_file(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(playlists=["hand.m3u8"])
    assert not plan["files"]
    assert f.plan_text(plan, "Hand") == ("Deleting Hand takes the playlist off Ben's Phone. Its songs stay, as "
                                         "other playlists list them.")


def test_an_album_ticked_comes_out_of_every_playlist_listing_it(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(folders=["Albums/Radiohead/In Rainbows"])
    assert f.plan_text(plan, "In Rainbows") == ("Deleting In Rainbows takes 2 tracks (1 MB) off Ben's Phone and out "
                                                "of Hand.")
    said = app.Lines()
    f.delete(plan, say=said)
    assert ph.names("Music/Albums/Radiohead") == ["OK Computer"]
    assert ph.text("Music/Playlists", "Hand.m3u8") == "#EXTM3U\nD:\\Elsewhere.flac\n", \
        "a drive's line is left as it is"
    assert "Radiohead - 15 Step.flac" in ph.names("Music/Playlists"), "the playlists' own copies stay"
    assert said.has("Hand.m3u8 listed 1 song no longer in the folder: taken out of it."), said.text()


def test_an_artist_ticked_goes_whole_and_albums_stays(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(folders=["Albums/Radiohead", "Albums/Radiohead/OK Computer"],
                  files=["Albums/Radiohead/In Rainbows/01 15 Step.flac"])
    assert plan["folders"] == ["Albums/Radiohead"] and plan["loose"] == [] and plan["tracks"] == 4, \
        "what's inside a ticked artist isn't deleted twice"
    f.delete(plan, say=app.Lines())
    assert ph.names("Music/Albums") == ["Pink Floyd"]
    f = phone.Folder(ph, "Music")
    f.delete(f.plan(folders=["Albums/Pink Floyd"]), say=app.Lines())
    assert ph.names("Music") == [".thumbnails", "Albums", "Playlists"], "Albums stays, empty"


def test_a_playlist_emptied_by_deleting_comes_off(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(files=["Playlists/Radiohead - Airbag.flac", "Playlists/Radiohead - Bodysnatchers.flac"])
    said = app.Lines()
    f.delete(plan, say=said)
    assert "Road Trip.m3u8" not in ph.names("Music/Playlists")
    assert said.has("Road Trip.m3u8 had none of its songs left in the folder, so it was taken off."), said.text()


def test_a_track_on_its_own(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(folders=["Albums/Pink Floyd/Wish You Were Here"])
    assert f.plan_text(plan, "Wish You Were Here") == ("Deleting Wish You Were Here takes 1 track (1 MB) off Ben's "
                                                       "Phone. Your playlists don't use them.")
    f.delete(plan, say=app.Lines())
    assert ph.names("Music/Albums") == ["Radiohead"], "the artist's folder left empty goes too"
    f = phone.Folder(ph, "Music")
    f.delete(f.plan(files=["Albums/Radiohead/OK Computer/02 Paranoid Android.flac"]), say=app.Lines())
    assert ph.names("Music/Albums/Radiohead/OK Computer") == ["01 Airbag.flac"]


def test_a_song_ticked_under_a_playlist_comes_out_of_that_one(app, files):
    """Ben, 25 Nov 2026 (the Devices tab): a song ticked under a playlist leaves that playlist; its file stays while
    another playlist lists it, and goes when none does."""
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    airbag = ("indie-chill.m3u8", "playlists/radiohead - airbag.flac")
    plan = f.plan(songs=[airbag])
    assert not plan["files"] and plan["unlist"] == {"indie-chill.m3u8": {airbag[1]}}, "Road Trip lists Airbag too"
    assert f.plan_text(plan, "Airbag") == ("Deleting Airbag takes it out of Indie-Chill. The songs stay on Ben's "
                                           "Phone, as other playlists list them.")
    said = app.Lines()
    f.delete(plan, say=said)
    assert said.has("Took 1 song out of Indie-Chill."), said.text()
    assert "Radiohead - Airbag.flac" in ph.names("Music/Playlists")
    assert "Airbag" not in ph.text("Music/Playlists", "Indie-Chill.m3u8")
    assert "Airbag" in ph.text("Music/Playlists", "Road Trip.m3u8")
    f = phone.Folder(ph, "Music")
    assert [p["tracks"] for p in f.playlists if p["name"] == "Indie-Chill"] == [2], "read back as it now is"
    plan = f.plan(songs=[("indie-chill.m3u8", "playlists/radiohead - paranoid android.flac")])
    assert plan["files"] == {"playlists/radiohead - paranoid android.flac"} and not plan["unlist"], \
        "no other playlist lists it: the file goes"
    assert f.plan_text(plan, "Paranoid Android") == ("Deleting Paranoid Android takes 1 track (1 MB) off Ben's Phone "
                                                     "and out of Indie-Chill.")
    f.delete(plan, say=app.Lines())
    assert "Radiohead - Paranoid Android.flac" not in ph.names("Music/Playlists")
    assert "Paranoid" not in ph.text("Music/Playlists", "Indie-Chill.m3u8")


def test_a_song_ticked_in_a_hand_made_playlist_leaves_its_album_alone(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    song = ("hand.m3u8", "albums/radiohead/in rainbows/02 bodysnatchers.flac")
    plan = f.plan(songs=[song])
    assert not plan["files"], "a song in Albums is never deleted from a playlist"
    f.delete(plan, say=app.Lines())
    assert ph.text("Music/Playlists", "Hand.m3u8") == "#EXTM3U\nD:\\Elsewhere.flac\n", \
        "its line and its #EXTINF go; a line 24bit7 doesn't know stays"
    assert ph.names("Music/Albums/Radiohead/In Rainbows") == ["01 15 Step.flac", "02 Bodysnatchers.flac"]


def test_a_folder_not_there_yet_is_empty(app):
    import phone
    f = phone.Folder(FakePhone(), "Music")
    assert (f.playlists, f.tree(), f.size) == ([], [], 0)
    assert f.plan_text(f.plan(), "") == ""
