"""
Copy Tracks To (Ben, 23 Nov 2026): Save's tracks copied to a phone. Since 25 Nov 2026 the chosen folder holds
Albums (artist and album folders, added from the Devices tab) and Playlists (flat, each .m3u8 beside its songs);
Clear Playlists First clears Playlists only; a second save copies only what's new and takes out what left the
playlist; the limit and the phone's free space are filled in playlist order; what was there before 1.44 is sorted
into the two once. Against a fake phone: the real one (Windows Portable Devices) was proved by hand on Ben's Pixel 9a.
"""

import itertools

import pytest


class FakePhone:
    def __init__(self, free=10 ** 10, name="Ben's Phone"):
        self.name, self._free = name, free
        self.ids = itertools.count(1)
        self.items = {"S": {"name": "Internal shared storage", "folder": True, "parent": None, "size": 0}}
        self.writes = []

    def _add(self, parent, name, folder, size=0, data=None):
        oid = f"o{next(self.ids)}"
        self.items[oid] = {"name": name, "folder": folder, "parent": parent, "size": size, "data": data}
        return oid

    def free(self):
        return self._free

    def capacity(self):
        return 117 * 10 ** 9

    def close(self):
        pass

    def list(self, parent):
        return [{"id": i, "name": e["name"], "folder": e["folder"], "size": e["size"]}
                for i, e in self.items.items() if e["parent"] == parent]

    def child(self, parent, name):
        return next((e["id"] for e in self.list(parent) if e["name"].lower() == name.lower()), None)

    def folder(self, path, make=False):
        here = "S"
        for part in [p for p in path.split("/") if p]:
            found = self.child(here, part)
            if found is None:
                if not make:
                    return None
                found = self.make(here, part)
            here = found
        return here

    def make(self, parent, name):
        return self._add(parent, name, True)

    def put(self, parent, path, name, size):
        with open(path, "rb") as f:
            data = f.read()
        self.writes.append(name)
        self._free -= size
        return self._add(parent, name, False, size, data)

    def put_text(self, parent, name, text):
        return self._add(parent, name, False, len(text.encode()), text)

    def read(self, oid):
        data = self.items[oid]["data"]
        return data if isinstance(data, bytes) else data.encode("utf-8")

    def delete(self, ids):
        for oid in ids:
            for kid in [i for i, e in self.items.items() if e["parent"] == oid]:
                self.delete([kid])
            gone = self.items.pop(oid, None)
            if gone and not gone["folder"]:
                self._free += gone["size"]

    def names(self, path):
        f = self.folder(path)
        return sorted(e["name"] for e in self.list(f)) if f else None

    def text(self, path, name):
        f = self.folder(path)
        return next(e["data"] for i, e in self.items.items() if e["parent"] == f and e["name"] == name)


@pytest.fixture
def files(tmp_path):
    """Tracks with files: (artist, title, size) or (artist, title, size, album, number)."""
    def make(*specs):
        out = []
        for n, spec in enumerate(specs):
            artist, title, size = spec[:3]
            album, number = (spec[3], spec[4]) if len(spec) > 3 else ("", 0)
            p = tmp_path / f"{n:02d} {title}.flac"
            p.write_bytes(b"x" * size)
            out.append({"key": str(n), "path": str(p), "artist": artist, "title": title, "size": size,
                        "album": album, "album_artist": "", "disc": 1 if album else 0, "number": number})
        return out
    return make


def test_playlists_are_flat_in_playlists_with_the_m3u8_beside_them(app, files):
    """Ben, 25 Nov 2026: Music/Playlists is flat, "just drop all the songs in there"; Albums keeps the folders."""
    import phone
    ph = FakePhone()
    tracks = files(("The Doors", "Riders On The Storm", 300, "L.A. Woman", 10),
                   ("The Doors", "L.A. Woman", 200, "L.A. Woman", 6), ("Seether", "Broken", 100, "Disclaimer II", 3))
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Jo's Mix", tracks, say=said) == 3
    assert ph.names("Music") == ["Playlists"]
    assert ph.names("Music/Playlists") == ["Jo's Mix.m3u8", "Seether - Broken.flac", "The Doors - L.A. Woman.flac",
                                           "The Doors - Riders On The Storm.flac"]
    assert ph.text("Music/Playlists", "Jo's Mix.m3u8") == ("#EXTM3U\nThe Doors - Riders On The Storm.flac\n"
                                                          "The Doors - L.A. Woman.flac\nSeether - Broken.flac\n")
    assert said.has("Copying 3 tracks (1 MB) into Music/Playlists on Ben's Phone..."), said.text()
    assert said.has("Copied to Ben's Phone: 3 tracks in Music/Playlists, with Jo's Mix.m3u8"), said.text()


def test_one_track_is_said_as_one_track(app, files):
    """Seen on Ben's Pixel over WiFi, 24 Nov 2026: "Copying 1 tracks" and "1 tracks in Music"."""
    import phone
    ph = FakePhone()
    one = files(("Seether", "Broken", 100, "Disclaimer II", 3))
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "One", one, say=said)
    assert said.has("Copying 1 track (1 MB) into Music/Playlists on Ben's Phone...") and \
        said.has("Copied to Ben's Phone: 1 track in Music/Playlists, with One.m3u8"), said.text()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "One", one, say=said)
    assert said.has("Already on Ben's Phone: 1 track in Music/Playlists, with One.m3u8."), said.text()
    assert "1 tracks" not in said.text()


def test_clear_playlists_first_leaves_albums_alone(app, files):
    """Ben, 25 Nov 2026: "if I select clear when I'm adding a playlist, then it just clears Music/Playlists and
    leaves albums alone", with notes in the console."""
    import phone
    ph = FakePhone()
    a, b, c, d = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2), ("C", "Three", 30, "Third", 3),
                       ("D", "Four", 40, "Fourth", 4))
    phone.add_albums(ph, "Music", [c, d], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Road Trip", [a, b], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Indie-Chill", [b], say=app.Lines())
    assert phone.clear_plan(ph, "Music", "New", [b]) == (0, 3, 1), "One and two playlists go; Two is kept"
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "New", [b, c], clear=True, say=said)
    assert ph.writes == ["C - Three.flac"], "Two was there; Three is copied again though Albums holds it"
    assert ph.names("Music/Playlists") == ["B - Two.flac", "C - Three.flac", "New.m3u8"]
    assert ph.names("Music/Albums") == ["C", "D"] and ph.names("Music/Albums/C/Third") == ["03 Three.flac"]
    assert said.has("Cleared Playlists on Ben's Phone: Indie-Chill and Road Trip, 1 track (1 MB). "
                    "Your 2 albums left alone."), said.text()
    assert said.has("1 already there, kept."), said.text()


def test_clear_first_keeps_dot_files_and_replaces_a_file_of_another_size(app, files):
    import phone
    ph = FakePhone()
    a, = files(("A", "One", 10, "First", 1))
    lists = ph.folder("Music/Playlists", make=True)
    ph.put_text(lists, ".nomedia", "")
    ph.put_text(lists, "A - One.flac", "short")
    ph.writes.clear()
    phone.copy_playlist(ph, "Music", "New", [a], clear=True, say=app.Lines())
    assert ph.writes == ["A - One.flac"] and ph.names("Music/Playlists") == [".nomedia", "A - One.flac", "New.m3u8"]


def test_other_playlists_lose_songs_no_longer_in_the_folder(app, files):
    """Ben, 24 Nov 2026: review the playlists already in the folder and amend any whose songs have gone."""
    import phone
    ph = FakePhone()
    a, b, c = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2), ("C", "Three", 30, "Third", 3))
    phone.add_albums(ph, "Music", [b], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Mine", [a, b], say=app.Lines())
    lists = ph.folder("Music/Playlists")
    ph.put_text(lists, "Hand.m3u8", "#EXTM3U\n#EXTINF:200,B - Two\n..\\Albums\\B\\Second\\02 Two.flac\n"
                                    "#EXTINF:100,Gone\n../Albums/Lost/Song.flac\nD:\\Music\\Elsewhere.flac\n")
    ph.put_text(lists, "Empty.m3u", "#EXTM3U\n../Albums/Nothing/Here.mp3\n")
    ph.delete([ph.child(lists, "A - One.flac")])   # deleted by hand on the phone
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "New", [c], say=said)
    assert ph.text("Music/Playlists", "Mine.m3u8") == "#EXTM3U\nB - Two.flac\n"
    assert ph.text("Music/Playlists", "Hand.m3u8") == ("#EXTM3U\n#EXTINF:200,B - Two\n..\\Albums\\B\\Second\\02 "
                                                      "Two.flac\nD:\\Music\\Elsewhere.flac\n"), \
        "a line into Albums is judged too; a drive's path is left as it is"
    assert "Empty.m3u" not in ph.names("Music/Playlists")
    assert said.has("Mine.m3u8 listed 1 song no longer in the folder: taken out of it."), said.text()
    assert said.has("Empty.m3u had none of its songs left in the folder, so it was taken off."), said.text()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "New", [c], say=said)
    assert not said.has("listed") and not said.has("taken off"), "nothing more to amend: " + said.text()


def test_this_pc_copies_into_a_folder_the_same_way(app, files, tmp_path):
    """Ben, 24 Nov 2026: a folder on this PC as a place to copy to, for Syncthing and the like. Plain copies."""
    import phone
    pc = phone.open_device(phone.PC, None)
    assert isinstance(pc, phone.FolderDevice) and pc.name == "This PC"
    sync = tmp_path / "Phone Sync"
    a, b = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2))
    said = app.Lines()
    assert phone.copy_playlist(pc, str(sync), "Mix", [a, b], say=said) == 2
    assert (sync / "Playlists" / "A - One.flac").read_bytes() == b"x" * 10
    assert (sync / "Playlists" / "Mix.m3u8").read_text(encoding="utf-8") == "#EXTM3U\nA - One.flac\nB - Two.flac\n"
    (sync / "Playlists" / "Loose").mkdir()
    (sync / ".stfolder").mkdir()   # Syncthing's own marker stays
    assert phone.clear_plan(pc, str(sync), "New", [a]) == (1, 2, 1)
    phone.copy_playlist(pc, str(sync), "New", [a], clear=True, say=app.Lines())
    assert sorted(x.name for x in sync.iterdir()) == [".stfolder", "Playlists"]
    assert sorted(x.name for x in (sync / "Playlists").iterdir()) == ["A - One.flac", "New.m3u8"]
    assert said.has(f"Copied to This PC: 2 tracks in {sync}/Playlists, with Mix.m3u8"), said.text()


def test_this_pc_never_takes_a_drive_or_the_library(app, tmp_path, monkeypatch):
    import library
    import phone
    lib = tmp_path / "Library"
    monkeypatch.setattr(library, "filenames", lambda: [str(lib / "Doors" / "LA Woman" / "01.flac")])
    assert phone.pc_folder_problem("") == "Choose a folder on this PC with Browse."
    assert phone.pc_folder_problem("Music") == "Choose a folder on this PC with Browse.", "never a relative path"
    assert phone.pc_folder_problem("D:\\") == "That's a whole drive: choose a folder in it."
    assert phone.pc_folder_problem(str(lib)) == "That folder holds your library's music, so 24bit7 won't copy into it."
    assert phone.pc_folder_problem(str(tmp_path / "Phone Sync")) == ""
    pc = phone.FolderDevice()
    assert pc.folder(str(lib)) is None
    pc.folder(str(tmp_path / "Phone Sync"), make=True)
    with pytest.raises(RuntimeError):
        pc.delete([str(tmp_path / "elsewhere.txt")])


def test_a_playlist_saved_empty_comes_off_with_its_own_tracks(app, files):
    import phone
    ph = FakePhone()
    a, b = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2))
    phone.copy_playlist(ph, "Music", "Mix", [a, b], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Other", [b], say=app.Lines())
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Mix", [], say=said) == 0
    assert ph.names("Music/Playlists") == ["B - Two.flac", "Other.m3u8"], "One goes; Two stays for Other"
    assert said.has("Took Mix.m3u8 off Ben's Phone: the playlist is empty now."), said.text()


def test_without_clear_first_the_rest_of_the_folder_stays(app, files):
    import phone
    ph = FakePhone()
    phone.add_albums(ph, "Music", files(("B", "Two", 10, "Second", 2)), say=app.Lines())
    lists = ph.folder("Music/Playlists", make=True)
    ph.put_text(lists, "Z - Old.flac", "x")
    phone.copy_playlist(ph, "Music", "New", files(("A", "One", 10)), say=app.Lines())
    assert ph.names("Music/Playlists") == ["A - One.flac", "New.m3u8", "Z - Old.flac"]
    assert ph.names("Music/Albums/B/Second") == ["02 Two.flac"]


def test_a_second_save_copies_only_whats_new_and_takes_out_what_left(app, files):
    import phone
    ph = FakePhone()
    a, b, c = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2), ("C", "Three", 30, "Third", 3))
    phone.copy_playlist(ph, "Music", "Mix", [a, b], say=app.Lines())
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [b, c], say=said)
    assert ph.writes == ["C - Three.flac"], "only the new one"
    assert ph.names("Music/Playlists") == ["B - Two.flac", "C - Three.flac", "Mix.m3u8"]
    assert said.has("Took out 1 track no longer in the playlist."), said.text()
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [b, c], say=said)
    assert ph.writes == [] and said.has("Already on Ben's Phone: 2 tracks in Music/Playlists, with Mix.m3u8."), \
        said.text()


def test_a_song_another_playlist_lists_stays_and_is_copied_once(app, files):
    import phone
    ph = FakePhone()
    a, b, c = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2), ("C", "Three", 30, "Third", 3))
    phone.copy_playlist(ph, "Music", "Mix", [a, b], say=app.Lines())
    ph.writes.clear()
    phone.copy_playlist(ph, "Music", "Other", [b, c], say=app.Lines())
    assert ph.writes == ["C - Three.flac"], "Two is on the phone already, from Mix"
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [a], say=said)
    assert "B - Two.flac" in ph.names("Music/Playlists"), "Other still lists it"
    assert not said.has("Took out"), said.text()


def old_layout(app, ph, files):
    """Music as 1.41 to 1.43 left it: Jo's Mix copied by 24bit7 into artist and album folders with its .m3u8 at
    the top, an album copied by hand, a playlist of the phone's own and a loose track."""
    import phone
    music = ph.folder("Music", make=True)
    ph.put_text(ph.make(music, ".thumbnails"), "a.jpg", "x")
    for path in ("The Doors/L.A. Woman/10 Riders On The Storm.flac", "Seether/Disclaimer II/03 Broken.flac",
                 "Seether/Karma And Effect/01 Because Of Me.flac", "Godsmack/Awake/01 Sick Of Life.flac"):
        d, _, name = path.rpartition("/")
        ph.put_text(ph.folder("Music/" + d, make=True), name, "x" * 5)
    ph.put_text(music, "Jo's Mix.m3u8", "#EXTM3U\nThe Doors/L.A. Woman/10 Riders On The Storm.flac\n"
                                        "Seether/Disclaimer II/03 Broken.flac\n")
    ph.put_text(music, "Gym.m3u", "#EXTM3U\nGodsmack/Awake/01 Sick Of Life.flac\nSeether/Disclaimer II/03 Broken.flac\n")
    ph.put_text(music, "Loose.mp3", "x")
    every = phone._meta(phone.META_KEY, {})
    every[phone.key_for(ph.name)] = {"copied": {"music": {"jo's mix.m3u8": [
        "The Doors/L.A. Woman/10 Riders On The Storm.flac", "Seether/Disclaimer II/03 Broken.flac"]}}}
    phone._set_meta(phone.META_KEY, every)


def test_nothing_already_in_the_folder_is_moved(app, files):
    """
    Ben, 26 Nov 2026, after Jo's own folders were sorted into Albums: 24bit7 never moves what's already in the
    folder, its own copies from before 1.44 included. It copies into Albums and Playlists only; the rest is left
    as it is and listed as Other Files, where it can be ticked and deleted. Clear Playlists First empties
    Playlists alone.
    """
    import phone
    ph = FakePhone()
    old_layout(app, ph, files)
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "New", files(("A", "One", 10)), say=said)
    phone.add_albums(ph, "Music", files(("B", "Two", 10, "Second", 2)), say=said)
    phone.copy_playlist(ph, "Music", "New", files(("A", "One", 10)), clear=True, say=said)
    assert ph.names("Music") == [".thumbnails", "Albums", "Godsmack", "Gym.m3u", "Jo's Mix.m3u8", "Loose.mp3",
                                 "Playlists", "Seether", "The Doors"], said.text()
    assert ph.names("Music/Seether") == ["Disclaimer II", "Karma And Effect"]
    assert ph.text("Music", "Gym.m3u") == ("#EXTM3U\nGodsmack/Awake/01 Sick Of Life.flac\n"
                                           "Seether/Disclaimer II/03 Broken.flac\n"), "the phone's own, untouched"
    assert ph.names("Music/Playlists") == ["A - One.flac", "New.m3u8"]
    assert not said.has("Sort"), said.text()
    folder = phone.Folder(ph, "Music")
    other = folder.other()
    assert [n["name"] for n in other] == ["Godsmack", "Seether", "The Doors", "Gym.m3u", "Jo's Mix.m3u8",
                                          "Loose.mp3"]
    assert [n["tracks"] for n in other[:3]] == [1, 2, 1]
    assert [p["name"] for p in folder.playlists] == ["New"], "Playlists holds only what Save put there"
    plan = folder.plan(folders=["Seether"], files=["Loose.mp3"])
    folder.delete(plan, say=app.Lines())
    assert ph.names("Music") == [".thumbnails", "Albums", "Godsmack", "Gym.m3u", "Jo's Mix.m3u8", "Playlists",
                                 "The Doors"], "ticked in Other Files and deleted"


def test_this_pc_leaves_what_is_there_too(app, files, tmp_path):
    import phone
    pc = phone.FolderDevice()
    sync = tmp_path / "Sync"
    (sync / "Seether" / "Disclaimer II").mkdir(parents=True)
    (sync / "Seether" / "Disclaimer II" / "03 Broken.flac").write_bytes(b"x")
    (sync / "Albums" / "Seether" / "Karma").mkdir(parents=True)
    phone.add_albums(pc, str(sync), files(("A", "One", 10, "First", 1)), say=app.Lines())
    assert sorted(x.name for x in (sync / "Albums" / "Seether").iterdir()) == ["Karma"]
    assert (sync / "Albums" / "A" / "First" / "01 One.flac").exists()
    assert sorted(x.name for x in sync.iterdir()) == ["Albums", "Seether"]
    pc.root = str(sync)
    assert [n["name"] for n in phone.Folder(pc, str(sync)).other()] == ["Seether"]


def test_adding_an_album_copies_into_albums_and_says_so(app, files):
    """The Devices tab's Add (Ben, 25 Nov 2026): straight into Albums, artist and album folders, no playlist."""
    import phone
    ph = FakePhone()
    tracks = files(("The Doors", "L.A. Woman", 20, "L.A. Woman", 6), ("The Doors", "Riders", 30, "L.A. Woman", 10))
    said, seen = app.Lines(), []
    assert phone.add_albums(ph, "Music", tracks, say=said, progress=seen.append, what="L.A. Woman") == 2
    assert ph.names("Music/Albums/The Doors/L.A. Woman") == ["06 L.A. Woman.flac", "10 Riders.flac"]
    assert said.has("Added L.A. Woman to Music/Albums on Ben's Phone (1 MB"), said.text()
    assert seen[-1]["state"] == "done" and seen[-1]["done"] == 2
    said = app.Lines()
    phone.add_albums(ph, "Music", tracks, say=said, what="L.A. Woman")
    assert said.has("L.A. Woman is already on Ben's Phone."), said.text()


def test_the_limit_is_filled_in_playlist_order_and_whats_left_is_said(app, files, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "GB", 100)   # a hundred bytes to the "GB", so the files can be small
    ph = FakePhone()
    tracks = files(("A", "One", 60), ("B", "Two", 60), ("C", "Three", 30))
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Mix", tracks, limit_gb=1, say=said) == 2
    assert ph.names("Music/Playlists") == ["A - One.flac", "C - Three.flac", "Mix.m3u8"], "Two didn't fit, Three did"
    assert said.has("Note: 1 track"), said.text()
    assert "Two" not in ph.text("Music/Playlists", "Mix.m3u8")


def test_the_phones_free_space_is_a_limit_too(app, files, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "SPARE", 0)
    ph = FakePhone(free=50)
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Mix", files(("A", "One", 40), ("B", "Two", 40)), say=said) == 1
    assert said.has("didn't fit in the phone's free space"), said.text()


def test_progress_is_told_and_stop_stops_with_what_is_there_listed(app, files):
    """For the copy's pop-up (Ben, 23 Nov 2026: "is it in progress, has it finished, I don't know")."""
    import phone
    ph = FakePhone()
    tracks = files(("A", "One", 10), ("B", "Two", 20), ("C", "Three", 30))
    seen = []
    assert phone.copy_playlist(ph, "Music", "Mix", tracks, say=app.Lines(), progress=seen.append) == 3
    assert [(e["state"], e["done"], e["track"]) for e in seen[:3]] == [
        ("copying", 0, "A - One"), ("copying", 1, "B - Two"), ("copying", 2, "C - Three")]
    assert seen[-1]["state"] == "done" and seen[-1]["done"] == 3 and seen[-1]["total"] == 60
    assert seen[-1]["line"].startswith("Copied to Ben's Phone: 3 tracks in Music/Playlists")
    ph2, seen = FakePhone(), []
    n = phone.copy_playlist(ph2, "Music", "Mix", tracks, say=app.Lines(), progress=seen.append,
                            stop=lambda: len(ph2.writes) >= 1)
    assert n == 1 and ph2.text("Music/Playlists", "Mix.m3u8") == "#EXTM3U\nA - One.flac\n", \
        "the .m3u8 lists what got there"
    assert seen[-1]["state"] == "stopped"
    assert seen[-1]["line"] == "Stopped: 1 of 3 tracks are on Ben's Phone, with Mix.m3u8. Copying again picks up the rest."


def test_names_are_safe_and_two_alike_get_a_number(app, files):
    import phone
    tracks = files(("AC/DC", "T.N.T.", 1, "High Voltage", 5), ("Sigur Rós", "Intro", 1), ("Sigur Rós", "Intro", 1))
    tracks[0]["album_artist"] = "AC/DC"
    tracks.append(dict(tracks[0], title="Disc Two", disc=2, number=1))
    assert phone.file_names(tracks) == ["AC_DC/High Voltage/05 T.N.T.flac", "Sigur Rós/Intro.flac",
                                        "Sigur Rós/Intro (2).flac", "AC_DC/High Voltage/2-01 Disc Two.flac"]
    various = dict(tracks[0], artist="Someone", album_artist="Various Artists", album="Now 1", number=7, disc=1)
    assert phone.file_names([various]) == ["Various Artists/Now 1/07 T.N.T.flac"], "by album artist, as filed"
    assert phone.safe_name('What? "Now" ...') == "What_ _Now_"
    assert phone.playlist_names(tracks) == ["AC_DC - T.N.T.flac", "Sigur Rós - Intro.flac",
                                            "Sigur Rós - Intro (2).flac", "AC_DC - Disc Two.flac"], \
        "Playlists is flat: Artist - Title"


def test_only_phones_are_offered_never_a_drive():
    """Windows lists every drive as a portable device too; Clear First must never reach a library disk."""
    import phone
    assert phone.is_phone("\\\\?\\usb#vid_18d1&pid_4ee1#63141jebf05002#{6ac27878-a6fa-4155-ba85-f98f491d4f33}")
    assert not phone.is_phone("\\\\?\\swd#wpdbusenum#{7f8f8b9d-efd5-11ed-b73a-806e6f6e6963}#0000000000100000#{6ac2}")


def test_each_device_keeps_its_own_name_and_choices(app):
    import phone
    assert phone.settings("pixel-1", "Pixel 9a") == {"name": "Pixel 9a", "folder": "Music", "limit_gb": 0,
                                                     "clear": False}
    phone.remember("pixel-1", name="Ben's Phone", limit_gb=32, clear=True)
    phone.remember("pixel-2", name="Jo's Phone")
    assert phone.settings("pixel-1", "Pixel 9a")["name"] == "Ben's Phone"
    assert phone.settings("pixel-1")["limit_gb"] == 32 and phone.settings("pixel-1")["clear"]
    assert phone.settings("pixel-2")["name"] == "Jo's Phone" and not phone.settings("pixel-2")["clear"]
    assert phone.last_device() == "pixel-2"
