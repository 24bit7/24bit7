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
    def make(*specs):
        out = []
        for n, (artist, title, size) in enumerate(specs):
            p = tmp_path / f"{n:02d} {title}.flac"
            p.write_bytes(b"x" * size)
            out.append({"key": str(n), "path": str(p), "artist": artist, "title": title, "size": size})
        return out
    return make


def test_tracks_and_their_m3u8_go_into_a_folder_named_after_the_playlist(app, files):
    import phone
    ph = FakePhone()
    tracks = files(("The Doors", "Riders On The Storm", 300), ("The Doors", "L.A. Woman", 200))
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Jo's Mix", tracks, say=said) == 2
    assert ph.names("Music/Jo's Mix") == ["Jo's Mix.m3u8", "The Doors - L.A. Woman.flac",
                                          "The Doors - Riders On The Storm.flac"]
    assert ph.text("Music/Jo's Mix", "Jo's Mix.m3u8") == ("#EXTM3U\nThe Doors - Riders On The Storm.flac\n"
                                                         "The Doors - L.A. Woman.flac\n"), "in playlist order"
    assert said.has("Copied to Ben's Phone: 2 tracks in Music/Jo's Mix, with Jo's Mix.m3u8"), said.text()


def test_clear_first_empties_the_folder_but_dot_folders(app, files):
    import phone
    ph = FakePhone()
    music = ph.folder("Music", make=True)
    thumbs = ph.make(music, ".thumbnails")
    ph.put_text(thumbs, "a.jpg", "x")
    old = ph.make(music, "Old Album")
    ph.put_text(old, "01.flac", "x")
    ph.put_text(music, "loose.mp3", "x")
    assert phone.clear_count(ph, "Music") == (1, 1), "asked once, with the count; .thumbnails isn't counted"
    phone.copy_playlist(ph, "Music", "New", files(("A", "One", 10)), clear=True, say=app.Lines())
    assert ph.names("Music") == [".thumbnails", "New"]
    assert ph.names("Music/.thumbnails") == ["a.jpg"]


def test_without_clear_first_the_rest_of_the_folder_stays(app, files):
    import phone
    ph = FakePhone()
    music = ph.folder("Music", make=True)
    ph.make(music, "Old Album")
    phone.copy_playlist(ph, "Music", "New", files(("A", "One", 10)), say=app.Lines())
    assert ph.names("Music") == ["New", "Old Album"]


def test_a_second_save_copies_only_whats_new_and_takes_out_what_left(app, files):
    import phone
    ph = FakePhone()
    a, b, c = files(("A", "One", 10), ("B", "Two", 20), ("C", "Three", 30))
    phone.copy_playlist(ph, "Music", "Mix", [a, b], say=app.Lines())
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [b, c], say=said)
    assert ph.writes == ["C - Three.flac"], "only the new one"
    assert ph.names("Music/Mix") == ["B - Two.flac", "C - Three.flac", "Mix.m3u8"]
    assert said.has("Took out 1 track no longer in the playlist."), said.text()
    ph.writes.clear()
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Mix", [b, c], say=said)
    assert ph.writes == [] and said.has("Already on Ben's Phone: 2 tracks in Music/Mix, with Mix.m3u8."), said.text()


def test_the_limit_is_filled_in_playlist_order_and_whats_left_is_said(app, files, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "GB", 100)   # a hundred bytes to the "GB", so the files can be small
    ph = FakePhone()
    tracks = files(("A", "One", 60), ("B", "Two", 60), ("C", "Three", 30))
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Mix", tracks, limit_gb=1, say=said) == 2
    assert ph.names("Music/Mix") == ["A - One.flac", "C - Three.flac", "Mix.m3u8"], "Two didn't fit, Three did"
    assert said.has("Note: 1 track"), said.text()
    assert "B - Two" not in ph.text("Music/Mix", "Mix.m3u8")


def test_the_phones_free_space_is_a_limit_too(app, files, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "SPARE", 0)
    ph = FakePhone(free=50)
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Mix", files(("A", "One", 40), ("B", "Two", 40)), say=said) == 1
    assert said.has("didn't fit in the phone's free space"), said.text()


def test_names_are_safe_and_two_alike_get_a_number(app, files):
    import phone
    tracks = files(("AC/DC", "T.N.T.", 1), ("Sigur Rós", "Intro", 1), ("Sigur Rós", "Intro", 1))
    assert phone.file_names(tracks) == ["AC_DC - T.N.T.flac", "Sigur Rós - Intro.flac", "Sigur Rós - Intro (2).flac"]
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
