"""
Manage Folder (Ben, 24 Nov 2026, as drawn): the folder copied to, as its playlists and then its artists and albums,
ticked and deleted. A playlist ticked takes its file and the songs no other playlist lists; an album or artist
ticked goes whole and every playlist listing its songs is amended, or taken off if none are left; the amber line
above Delete says what goes, so there's no further question. Against the fake phone from test_phone_copy.
"""

from test_phone_copy import FakePhone, files   # noqa: F401  (the fake phone and the tracks fixture)


def _phone(app, files):
    """Indie-Chill and Road Trip copied by 24bit7, a playlist made by hand, and an album in no playlist."""
    import phone
    ph = FakePhone()
    ok1, ok2, rain1, rain2 = files(("Radiohead", "Airbag", 100, "OK Computer", 1),
                                   ("Radiohead", "Paranoid Android", 200, "OK Computer", 2),
                                   ("Radiohead", "15 Step", 300, "In Rainbows", 1),
                                   ("Radiohead", "Bodysnatchers", 400, "In Rainbows", 2))
    phone.copy_playlist(ph, "Music", "Indie-Chill", [ok1, ok2, rain1], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Road Trip", [ok1, rain2], say=app.Lines())
    music = ph.folder("Music")
    ph.put_text(music, "Hand.m3u8", "#EXTM3U\n#EXTINF:1,Radiohead - Bodysnatchers\n"
                                    "Radiohead\\In Rainbows\\02 Bodysnatchers.flac\nD:\\Elsewhere.flac\n")
    wish = ph.folder("Music/Pink Floyd/Wish You Were Here", make=True)
    ph.put_text(wish, "01 Shine On.flac", "x" * 500)
    ph.put_text(wish, "folder.jpg", "jpg")
    ph.put_text(ph.make(music, ".thumbnails"), "a.jpg", "x")
    return ph


def test_the_folder_is_read_as_playlists_then_artists_and_albums(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    assert [(p["name"], p["tracks"]) for p in f.playlists] == [("Hand", 1), ("Indie-Chill", 3), ("Road Trip", 2)], \
        "a line with a drive isn't one of the folder's"
    tree = f.tree()
    assert [n["name"] for n in tree] == ["Pink Floyd", "Radiohead"], ".thumbnails is never shown"
    radiohead = tree[1]
    assert (radiohead["tracks"], radiohead["size"]) == (4, 1000)
    rain, ok = radiohead["children"]
    assert (ok["name"], ok["lists"]) == ("OK Computer", ["Indie-Chill", "Road Trip"])
    assert (rain["name"], rain["lists"]) == ("In Rainbows", ["Hand", "Indie-Chill", "Road Trip"])
    assert [c["name"] for c in ok["children"]] == ["01 Airbag.flac", "02 Paranoid Android.flac"], \
        "albums open to their tracks"
    wish = tree[0]["children"][0]
    assert (wish["tracks"], wish["lists"]) == (1, []), "in no playlist; folder.jpg isn't a track"
    assert f.size == 1000 + 500 + 3


def test_a_playlist_ticked_takes_the_songs_no_other_playlist_lists(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(playlists=["indie-chill.m3u8"])
    assert sorted(plan["files"]) == ["radiohead/in rainbows/01 15 step.flac",
                                     "radiohead/ok computer/02 paranoid android.flac"]
    assert plan["tracks"] == 2 and plan["kept"] == 1, "Airbag stays: Road Trip lists it"
    assert f.plan_text(plan, "Indie-Chill") == "Deleting Indie-Chill takes 2 tracks (1 MB) off Ben's Phone."
    said = app.Lines()
    f.delete(plan, say=said)
    assert ph.names("Music") == [".thumbnails", "Hand.m3u8", "Pink Floyd", "Radiohead", "Road Trip.m3u8"]
    assert ph.names("Music/Radiohead/OK Computer") == ["01 Airbag.flac"]
    assert ph.names("Music/Radiohead/In Rainbows") == ["02 Bodysnatchers.flac"]
    assert said.has("Took Indie-Chill off Ben's Phone.") and said.has("Deleted 2 tracks (1 MB) from Music"), \
        said.text()
    copied = phone._records(ph)[1]["music"]
    assert "indie-chill.m3u8" not in copied and "road trip.m3u8" in copied, "24bit7's records kept in step"


def test_a_playlist_whose_songs_are_all_elsewhere_takes_only_its_file(app, files):
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
    plan = f.plan(folders=["Radiohead/In Rainbows"])
    assert f.plan_text(plan, "In Rainbows") == ("Deleting In Rainbows takes 2 tracks (1 MB) off Ben's Phone and out "
                                                "of Hand, Indie-Chill and Road Trip.")
    said = app.Lines()
    f.delete(plan, say=said)
    assert ph.names("Music/Radiohead") == ["OK Computer"]
    assert ph.text("Music", "Indie-Chill.m3u8") == ("#EXTM3U\nRadiohead/OK Computer/01 Airbag.flac\n"
                                                   "Radiohead/OK Computer/02 Paranoid Android.flac\n")
    assert ph.text("Music", "Road Trip.m3u8") == "#EXTM3U\nRadiohead/OK Computer/01 Airbag.flac\n"
    assert ph.text("Music", "Hand.m3u8") == "#EXTM3U\nD:\\Elsewhere.flac\n", "a drive's line is left as it is"
    assert said.has("Indie-Chill.m3u8 listed 1 song no longer in the folder: taken out of it."), said.text()


def test_an_artist_ticked_goes_whole_and_an_emptied_playlist_comes_off(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(folders=["Radiohead", "Radiohead/OK Computer"], files=["Radiohead/In Rainbows/01 15 Step.flac"])
    assert plan["folders"] == ["Radiohead"] and plan["loose"] == [] and plan["tracks"] == 4, \
        "what's inside a ticked artist isn't deleted twice"
    said = app.Lines()
    f.delete(plan, say=said)
    assert ph.names("Music") == [".thumbnails", "Hand.m3u8", "Pink Floyd"]
    assert said.has("Road Trip.m3u8 had none of its songs left in the folder, so it was taken off."), said.text()


def test_an_album_in_no_playlist_and_a_track_on_its_own(app, files):
    import phone
    ph = _phone(app, files)
    f = phone.Folder(ph, "Music")
    plan = f.plan(folders=["Pink Floyd/Wish You Were Here"])
    assert f.plan_text(plan, "Wish You Were Here") == ("Deleting Wish You Were Here takes 1 track (1 MB) off Ben's "
                                                       "Phone.")
    f.delete(plan, say=app.Lines())
    assert ph.names("Music") == [".thumbnails", "Hand.m3u8", "Indie-Chill.m3u8", "Radiohead", "Road Trip.m3u8"], \
        "the artist's folder left empty goes too"
    f = phone.Folder(ph, "Music")
    plan = f.plan(files=["Radiohead/OK Computer/02 Paranoid Android.flac"])
    f.delete(plan, say=app.Lines())
    assert ph.names("Music/Radiohead/OK Computer") == ["01 Airbag.flac"]
    assert "Paranoid" not in ph.text("Music", "Indie-Chill.m3u8")


def test_a_folder_not_there_yet_is_empty(app):
    import phone
    f = phone.Folder(FakePhone(), "Music")
    assert (f.playlists, f.tree(), f.size) == ([], [], 0)
    assert f.plan_text(f.plan(), "") == ""
