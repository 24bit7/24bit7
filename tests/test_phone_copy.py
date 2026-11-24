"""
Copy Tracks To (Ben, 23 Nov 2026): Save Playlist's tracks copied to a phone, into a folder named after the
playlist with an .m3u8 beside them. Clear First empties the chosen folder but dot folders; a second save copies
only what's new and takes out what left the playlist; the limit and the phone's free space are filled in playlist
order. Against a fake phone: the real one (Windows Portable Devices) was proved by hand on Ben's Pixel 9a.
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


def test_tracks_go_in_artist_and_album_folders_with_the_m3u8_at_the_top(app, files):
    """Ben, 23 Nov 2026: "keep the band/album folder structure, even though we might only have one track in a folder"."""
    import phone
    ph = FakePhone()
    tracks = files(("The Doors", "Riders On The Storm", 300, "L.A. Woman", 10),
                   ("The Doors", "L.A. Woman", 200, "L.A. Woman", 6), ("Seether", "Broken", 100, "Disclaimer II", 3))
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Jo's Mix", tracks, say=said) == 3
    assert ph.names("Music") == ["Jo's Mix.m3u8", "Seether", "The Doors"]
    assert ph.names("Music/The Doors/L.A. Woman") == ["06 L.A. Woman.flac", "10 Riders On The Storm.flac"]
    assert ph.names("Music/Seether/Disclaimer II") == ["03 Broken.flac"]
    assert ph.text("Music", "Jo's Mix.m3u8") == ("#EXTM3U\nThe Doors/L.A. Woman/10 Riders On The Storm.flac\n"
                                                "The Doors/L.A. Woman/06 L.A. Woman.flac\n"
                                                "Seether/Disclaimer II/03 Broken.flac\n"), "in playlist order"
    assert said.has("Copied to Ben's Phone: 3 tracks in Music, with Jo's Mix.m3u8"), said.text()


def test_clear_first_empties_the_folder_but_dot_folders(app, files):
    import phone
    ph = FakePhone()
    music = ph.folder("Music", make=True)
    thumbs = ph.make(music, ".thumbnails")
    ph.put_text(thumbs, "a.jpg", "x")
    old = ph.make(music, "Old Album")
    ph.put_text(old, "01.flac", "x")
    ph.put_text(music, "loose.mp3", "x")
    new = files(("A", "One", 10))
    assert phone.clear_plan(ph, "Music", "New", new) == (1, 1, 0), \
        "asked once, with the count; .thumbnails isn't counted"
    phone.copy_playlist(ph, "Music", "New", new, clear=True, say=app.Lines())
    assert ph.names("Music") == [".thumbnails", "A", "New.m3u8"]
    assert ph.names("Music/.thumbnails") == ["a.jpg"]


def test_clear_first_keeps_what_the_new_playlist_lists(app, files):
    """Ben, 24 Nov 2026: "During a clear and add new, we should check we're not deleting something that already
    exists from the new playlist". Same place and size stays and isn't copied again; the rest goes."""
    import phone
    ph = FakePhone()
    a, b, c, d = files(("A", "One", 10, "First", 1), ("A", "Two", 20, "First", 2), ("B", "Three", 30, "Second", 3),
                       ("C", "Four", 40, "Third", 4))
    phone.copy_playlist(ph, "Music", "Old", [a, b, c], say=app.Lines())
    music = ph.folder("Music")
    ph.put_text(ph.folder("Music/A"), ".24bit7", "id")   # dot files stay anywhere
    ph.put_text(music, "Other.m3u8", "#EXTM3U\nB/Second/03 Three.flac\n")
    assert phone.clear_plan(ph, "Music", "New", [a, d]) == (1, 3, 1), \
        "B's folder whole; Two, Old.m3u8 and Other.m3u8 one by one; One kept"
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "New", [a, d], clear=True, say=said)
    assert ph.writes == ["04 Four.flac"], "One was there already, so only Four is copied"
    assert ph.names("Music") == ["A", "C", "New.m3u8"]
    assert ph.names("Music/A") == [".24bit7", "First"] and ph.names("Music/A/First") == ["01 One.flac"]
    assert said.has("Cleared Music on Ben's Phone: 1 folder and 3 files taken out, 1 track already there kept."), \
        said.text()


def test_clear_first_replaces_a_file_of_another_size(app, files):
    import phone
    ph = FakePhone()
    a, = files(("A", "One", 10, "First", 1))
    ph.put_text(ph.folder("Music/A/First", make=True), "01 One.flac", "short")
    ph.writes.clear()
    phone.copy_playlist(ph, "Music", "New", [a], clear=True, say=app.Lines())
    assert ph.writes == ["01 One.flac"] and ph.names("Music/A/First") == ["01 One.flac"]


def test_other_playlists_lose_songs_no_longer_in_the_folder(app, files):
    """Ben, 24 Nov 2026: review the playlists already in the folder and amend any whose songs have gone."""
    import phone
    ph = FakePhone()
    a, b, c = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2), ("C", "Three", 30, "Third", 3))
    phone.copy_playlist(ph, "Music", "Mine", [a, b], say=app.Lines())
    music = ph.folder("Music")
    ph.put_text(music, "Hand.m3u8", "#EXTM3U\n#EXTINF:200,B - Two\nB\\Second\\02 Two.flac\n#EXTINF:100,Gone\n"
                                    "Lost/Song.flac\nD:\\Music\\Elsewhere.flac\n")
    ph.put_text(music, "Empty.m3u", "#EXTM3U\nNothing/Here.mp3\n")
    ph.delete([ph.child(ph.folder("Music/A/First"), "01 One.flac")])   # deleted by hand on the phone
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "New", [c], say=said)
    assert ph.text("Music", "Mine.m3u8") == "#EXTM3U\nB/Second/02 Two.flac\n"
    assert ph.text("Music", "Hand.m3u8") == ("#EXTM3U\n#EXTINF:200,B - Two\nB\\Second\\02 Two.flac\n"
                                            "D:\\Music\\Elsewhere.flac\n"), "a drive's path is left as it is"
    assert "Empty.m3u" not in ph.names("Music")
    assert said.has("Mine.m3u8 listed 1 song no longer in the folder: taken out of it."), said.text()
    assert said.has("Empty.m3u had none of its songs left in the folder, so it was taken off."), said.text()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "New", [c], say=said)
    assert not said.has("listed") and not said.has("taken off"), "nothing more to amend: " + said.text()


def test_a_playlist_saved_empty_comes_off_with_its_own_tracks(app, files):
    import phone
    ph = FakePhone()
    a, b = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2))
    phone.copy_playlist(ph, "Music", "Mix", [a, b], say=app.Lines())
    phone.copy_playlist(ph, "Music", "Other", [b], say=app.Lines())
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Mix", [], say=said) == 0
    assert ph.names("Music") == ["B", "Other.m3u8"], "One goes; Two stays for Other"
    assert said.has("Took Mix.m3u8 off Ben's Phone: the playlist is empty now."), said.text()


def test_without_clear_first_the_rest_of_the_folder_stays(app, files):
    import phone
    ph = FakePhone()
    music = ph.folder("Music", make=True)
    ph.make(music, "Old Album")
    phone.copy_playlist(ph, "Music", "New", files(("A", "One", 10)), say=app.Lines())
    assert ph.names("Music") == ["A", "New.m3u8", "Old Album"]


def test_a_second_save_copies_only_whats_new_and_takes_out_what_left(app, files):
    import phone
    ph = FakePhone()
    a, b, c = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2), ("C", "Three", 30, "Third", 3))
    phone.copy_playlist(ph, "Music", "Mix", [a, b], say=app.Lines())
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [b, c], say=said)
    assert ph.writes == ["03 Three.flac"], "only the new one"
    assert ph.names("Music") == ["B", "C", "Mix.m3u8"], "A's folders went with its only track"
    assert said.has("Took out 1 track no longer in the playlist."), said.text()
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [b, c], say=said)
    assert ph.writes == [] and said.has("Already on Ben's Phone: 2 tracks in Music, with Mix.m3u8."), said.text()


def test_a_song_another_playlist_lists_stays_and_is_copied_once(app, files):
    import phone
    ph = FakePhone()
    a, b, c = files(("A", "One", 10, "First", 1), ("B", "Two", 20, "Second", 2), ("C", "Three", 30, "Third", 3))
    phone.copy_playlist(ph, "Music", "Mix", [a, b], say=app.Lines())
    ph.writes.clear()
    phone.copy_playlist(ph, "Music", "Other", [b, c], say=app.Lines())
    assert ph.writes == ["03 Three.flac"], "Two is on the phone already, from Mix"
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [a], say=said)
    assert ph.names("Music/B/Second") == ["02 Two.flac"], "Other still lists it"
    assert not said.has("Took out"), said.text()


def test_a_playlist_in_a_folder_of_its_own_from_1_40_moves_to_the_new_folders(app, files):
    import phone
    ph = FakePhone()
    music = ph.folder("Music", make=True)
    own = ph.make(music, "Mix")
    ph.put_text(own, "A - One.flac", "x")
    ph.put_text(own, "Mix.m3u8", "#EXTM3U\nA - One.flac\n")
    keep = ph.make(music, "Godsmack")   # an artist's folder isn't taken for an old playlist folder
    ph.put_text(keep, "x.flac", "x")
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", files(("A", "One", 10)), say=said)
    assert ph.names("Music") == ["A", "Godsmack", "Mix.m3u8"]
    assert said.has("Mix had a folder of its own from before"), said.text()


def test_the_limit_is_filled_in_playlist_order_and_whats_left_is_said(app, files, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "GB", 100)   # a hundred bytes to the "GB", so the files can be small
    ph = FakePhone()
    tracks = files(("A", "One", 60), ("B", "Two", 60), ("C", "Three", 30))
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Mix", tracks, limit_gb=1, say=said) == 2
    assert ph.names("Music") == ["A", "C", "Mix.m3u8"], "Two didn't fit, Three did"
    assert said.has("Note: 1 track"), said.text()
    assert "Two" not in ph.text("Music", "Mix.m3u8")


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
    assert seen[-1]["line"].startswith("Copied to Ben's Phone: 3 tracks in Music")
    ph2, seen = FakePhone(), []
    n = phone.copy_playlist(ph2, "Music", "Mix", tracks, say=app.Lines(), progress=seen.append,
                            stop=lambda: len(ph2.writes) >= 1)
    assert n == 1 and ph2.text("Music", "Mix.m3u8") == "#EXTM3U\nA/One.flac\n", "the .m3u8 lists what got there"
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
