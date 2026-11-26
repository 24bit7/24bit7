"""
Copy Tracks To over WiFi (Ben, 24 Nov 2026: "our own 24bit7 wireless transfer app, just a bare bones app, the
interface is 24bit7"). The phone app (android/) is a small HTTP server taking files under a four-digit code; here a
stand-in speaking the same requests runs on this PC, over a folder, so the copy, the scan that finds the phone and
the link between a phone's USB and WiFi selves are tested without one. The real app was proved on Ben's Pixel 9a
the same day (41 MB in 0.6 s from the wired media PC).
"""

import json
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class FakeApp:
    """What android/app/src/main/java/.../TransferService.kt answers, over a folder standing in for the phone."""

    def __init__(self, root, code="4659", app_id="0f8e1c2a-1111-2222-3333-444455556666", hello=True):
        self.root, self.code, self.app_id = str(root), code, app_id
        self.hello = hello   # /hello, without the code (the app from 25 Nov 2026); False: an older app
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _path(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                rel = q.get("path", [""])[0]
                full = os.path.realpath(os.path.join(app.root, rel.lstrip("/")))
                return full if full == app.root or full.startswith(app.root + os.sep) else None

            def _reply(self, status, obj=None, data=None):
                body = data if data is not None else json.dumps(obj or {}).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _ok(self):
                if self.headers.get("X-24bit7-Code") != app.code:
                    self._reply(401, {"error": "wrong code"})
                    return False
                return True

            def do_GET(self):
                route = urllib.parse.urlparse(self.path).path
                if route == "/hello" and app.hello:
                    return self._reply(200, {"id": app.app_id, "name": "Pixel 9a", "version": 2})
                if not self._ok():
                    return
                if route == "/info":
                    return self._reply(200, {"id": app.app_id, "name": "Pixel 9a", "free": 64 * 10 ** 9,
                                             "total": 117 * 10 ** 9, "version": 1})
                p = self._path()
                if p is None:
                    return self._reply(400, {"error": "bad path"})
                if route == "/list":
                    if not os.path.isdir(p):
                        return self._reply(404, {"error": "not a folder"})
                    entries = [{"name": e.name, "dir": e.is_dir(), "size": 0 if e.is_dir() else e.stat().st_size}
                               for e in os.scandir(p)]
                    return self._reply(200, {"entries": entries})
                if route == "/file":
                    if not os.path.isfile(p):
                        return self._reply(404, {"error": "no such file"})
                    return self._reply(200, data=open(p, "rb").read())
                self._reply(404)

            def do_PUT(self):
                if not self._ok():
                    return
                p = self._path()
                os.makedirs(os.path.dirname(p), exist_ok=True)
                n = int(self.headers["Content-Length"])
                with open(p, "wb") as f:
                    f.write(self.rfile.read(n))
                self._reply(201, {"size": n})

            def do_POST(self):
                if self._ok():
                    os.makedirs(self._path(), exist_ok=True)
                    self._reply(200, {"dir": True})

            def do_DELETE(self):
                if not self._ok():
                    return
                import shutil
                p = self._path()
                if p == app.root:
                    return self._reply(400, {"error": "won't delete the whole phone"})
                if os.path.isdir(p):
                    shutil.rmtree(p)
                elif os.path.exists(p):
                    os.remove(p)
                self._reply(200, {"deleted": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def address(self):
        return f"127.0.0.1:{self.port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def phone_app(tmp_path, monkeypatch):
    import phone
    storage = tmp_path / "storage"
    (storage / "Music").mkdir(parents=True)
    app = FakeApp(storage)
    monkeypatch.setattr(phone, "APP_PORT", app.port)
    monkeypatch.setattr(phone, "_home_networks", lambda: ["127.0.0"])
    yield app
    app.close()


def test_add_finds_the_phone_by_its_code_and_the_copy_goes_over_wifi(app, phone_app, tmp_path):
    import phone
    assert phone.add_wifi("1234") is None, "a wrong code finds nothing"
    key, model, known = phone.add_wifi("4659")
    assert key == "app:" + phone_app.app_id and model == "Pixel 9a" and not known
    assert (key, "Pixel 9a") in phone.targets(), "listed with the phones from now on"
    assert phone.label(key, model) == "Pixel 9a (WiFi)"
    phone.remember(key, name="Ben's Phone")
    ph = phone.open_device(key, "Ben's Phone")
    assert isinstance(ph, phone.WifiPhone) and ph.free() == 64 * 10 ** 9
    src = tmp_path / "song.flac"
    src.write_bytes(b"x" * 300_000)
    track = {"key": "1", "path": str(src), "artist": "Seether", "title": "Broken", "size": 300_000,
             "album": "Disclaimer II", "album_artist": "", "disc": 1, "number": 3}
    said = app.Lines()
    assert phone.copy_playlist(ph, "Music", "Jo's Mix", [track], say=said) == 1
    music = tmp_path / "storage" / "Music"
    assert (music / "Playlists" / "Seether - Broken.flac").read_bytes() == b"x" * 300_000
    assert (music / "Playlists" / "Jo's Mix.m3u8").read_text() == "#EXTM3U\nSeether - Broken.flac\n"
    phone.copy_playlist(ph, "Music", "Jo's Mix", [], say=said)
    assert sorted(os.listdir(music / "Playlists")) == [], "the tidy-up and an emptied playlist work over WiFi too"
    phone.add_albums(ph, "Music", [track], say=said)
    assert (music / "Albums" / "Seether" / "Disclaimer II" / "03 Broken.flac").exists()


def test_jos_own_folders_stay_where_they_are_over_wifi(app, phone_app, tmp_path):
    """Jo's phone, 25 Nov 2026: added over WiFi, its folder Music, and her own Music/Music and Signal were moved into
    Albums. Since 26 Nov they stay put, and show as Other Files."""
    import phone
    key, model, _known = phone.add_wifi("4659")
    music = tmp_path / "storage" / "Music"
    (music / "Music" / "Godsmack" / "Awake").mkdir(parents=True)
    (music / "Music" / "Godsmack" / "Awake" / "01 Sick Of Life.flac").write_bytes(b"y" * 1000)
    (music / "Signal").mkdir()
    (music / "Signal" / "out of my way.mp3").write_bytes(b"z" * 10)
    ph = phone.open_device(key, "Jo's Phone")
    track = {"key": "1", "path": str(tmp_path / "Broken.flac"), "artist": "Seether", "title": "Broken", "size": 100,
             "album": "Disclaimer II", "album_artist": "", "disc": 1, "number": 3}
    (tmp_path / "Broken.flac").write_bytes(b"x" * 100)
    said = app.Lines()
    phone.copy_playlist(ph, "Music", "Jo's Mix", [track], say=said)
    phone.add_albums(ph, "Music", [track], say=said)
    assert sorted(os.listdir(music)) == ["Albums", "Music", "Playlists", "Signal"], said.text()
    assert (music / "Music" / "Godsmack" / "Awake" / "01 Sick Of Life.flac").read_bytes() == b"y" * 1000
    assert [n["name"] for n in phone.Folder(ph, "Music").other()] == ["Music", "Signal"]


def test_add_looks_twice_for_a_phone_slow_to_answer(app, phone_app, monkeypatch):
    """Ben, 24 Nov 2026: Jo's first Add said no phone answered, the second moments later found her Pixel. A phone
    that answers only within the second, longer wait is found by one Add."""
    import phone
    waits = []

    def slow(host, port=None, timeout=0.4):
        waits.append(timeout)
        return host == "127.0.0.1" and timeout >= 1.0
    monkeypatch.setattr(phone, "_open_port", slow)
    key, model, _known = phone.add_wifi("4659")
    assert key == "app:" + phone_app.app_id and model == "Pixel 9a"
    assert sorted(set(waits)) == [0.4, phone.SLOW_SCAN], "a quick look, then a slower one"
    waits.clear()
    monkeypatch.setattr(phone, "_open_port", lambda host, port=None, timeout=0.4: waits.append(timeout) or
                        host == "127.0.0.1")
    phone.add_wifi("4659")
    assert set(waits) == {0.4}, "found at the first look: no second"


def test_a_phone_that_moved_is_found_again(app, phone_app):
    import phone
    key, _model, _known = phone.add_wifi("4659")
    phone.remember_quietly(key, address="127.0.0.1:1")   # the router gave it another address
    ph = phone.open_device(key, "Ben's Phone")
    assert ph.address == phone_app.address
    assert phone._meta(phone.META_KEY, {})[key]["address"] == phone_app.address, "remembered where it is now"


def test_a_phone_not_answering_says_to_open_the_app(app, phone_app):
    import phone
    key, _model, _known = phone.add_wifi("4659")
    phone_app.close()
    with pytest.raises(RuntimeError, match="Open 24bit7 on it, on the same WiFi as this PC"):
        phone.open_device(key, "Ben's Phone")


def test_the_same_phone_by_usb_and_wifi_is_one_device(app, phone_app, monkeypatch):
    """Ben, 24 Nov 2026, as drawn: the app leaves Music/.24bit7 with its id, which the USB side reads, so one name,
    folder, limit and record whichever way it's reached."""
    import phone
    from test_phone_copy import FakePhone
    usb_id = "\\\\?\\usb#vid_18d1&pid_4ee1#serial1#{6ac27878}"
    usb = FakePhone(name="Pixel 9a")
    usb.put_text(usb.folder("Music", make=True), ".24bit7", phone_app.app_id + "\n")
    monkeypatch.setattr(phone, "devices", lambda: [(usb_id, "Pixel 9a")])
    monkeypatch.setattr(phone, "WpdPhone", lambda device_id, name: usb)
    phone.remember(usb_id, name="Ben's Phone", folder="Music/Ben", limit_gb=30.0)
    key, _model, known = phone.add_wifi("4659")
    assert not known, "not linked until it's next plugged in"
    targets = phone.targets()
    assert targets == [(usb_id, "Pixel 9a"), (phone.PC, "This PC")], "plugged in: listed once, by USB"
    assert phone.key_for(usb_id) == key
    s = phone.settings(key)
    assert (s["name"], s["folder"], s["limit_gb"]) == ("Ben's Phone", "Music/Ben", 30.0), "its USB choices carried"
    assert phone.label(usb_id, "Pixel 9a") == "Ben's Phone (USB)"
    monkeypatch.setattr(phone, "devices", lambda: [])
    assert (key, "Pixel 9a") in phone.targets(), "unplugged: there by WiFi"
    assert phone.label(key) == "Ben's Phone (WiFi)"


def test_a_phone_given_a_new_address_brings_the_tab_up_again(app, phone_app):
    """
    Ben, 25 Nov 2026: his Pixel answered at .97 while 24bit7 had it at .248, so the Devices tab never came up (the
    half-minute look tries only the last address). The search across the network finds it by its id and keeps
    where it is now; without it, a moved phone isn't there.
    """
    import phone
    key, _model, _known = phone.add_wifi("4659")
    phone.remember_quietly(key, address="127.0.0.1:1")   # the router gave it another address
    assert phone.present() == [], "the quick look knocks only where it was"
    assert phone.present(search=True) == [key], "the search finds it"
    assert phone._meta(phone.META_KEY, {})[key]["address"] == phone_app.address, "and keeps where it is now"
    assert phone.asking() == []
    assert phone.present() == [key], "so the next quick look finds it too"


def test_an_older_app_that_moved_is_still_found_by_its_code(app, phone_app):
    """An app from before /hello can't say who it is without the code, so the codes 24bit7 keeps are tried."""
    import phone
    phone_app.hello = False
    key, _model, _known = phone.add_wifi("4659")
    phone.remember_quietly(key, address="127.0.0.1:1")
    assert phone.present(search=True) == [key] and phone.asking() == []


def test_a_known_phone_with_a_new_code_is_asked_about(app, phone_app):
    """
    Ben, 25 Nov 2026 ("were you previously Ben's Phone?"): a phone whose app was reinstalled without Music/.24bit7
    to read back keeps its id (from the file) but has a new code. 24bit7 knows it from /hello and asks for the code;
    the right one puts it back, the wrong one changes nothing.
    """
    import phone
    key, _model, _known = phone.add_wifi("4659")
    phone.remember(key, name="Ben's Phone", folder="Music/Ben")
    phone_app.code = "7777"
    assert phone.present(search=True) == []
    ask = phone.asking()
    assert ask == [{"address": phone_app.address, "key": key, "model": "Pixel 9a", "known": True}]
    assert phone.claim(phone_app.address, "1234", as_key=key) is None, "the wrong code changes nothing"
    assert phone._meta(phone.META_KEY, {})[key]["code"] == "4659"
    assert phone.claim(phone_app.address, "7777", as_key=key) == key
    assert phone.asking() == []
    assert phone.settings(key)["name"] == "Ben's Phone" and phone.present() == [key]


def test_an_unknown_phone_is_asked_which_it_is_and_takes_over_the_old_one(app, phone_app, monkeypatch):
    """
    A phone reset or replaced has a new id and code. 24bit7 asks which phone it is; the answer moves the old
    phone's name, folder, limit, records and USB link to the new id. "A New Phone" keeps it as one of its own.
    """
    import phone
    phone.remember_quietly("app:old-id", name="Ben's Phone", folder="Music/Ben", limit_gb=30.0, code="1111",
                           address="127.0.0.1:1", model="Pixel 9a")
    phone.remember("app:old-id")
    phone._set_meta(phone.LINKS_KEY, {"usb-ben": "app:old-id"})
    phone.remember_quietly("usb-jo", name="Jo's Phone", model="Pixel 9a")
    assert phone.present(search=True) == []
    assert phone.asking() == [{"address": phone_app.address, "key": "app:" + phone_app.app_id, "model": "Pixel 9a",
                               "known": False}]
    assert sorted(n for _k, n in phone.kept_phones()) == ["Ben's Phone", "Jo's Phone"]
    key = phone.claim(phone_app.address, "4659", as_key="app:old-id")
    assert key == "app:" + phone_app.app_id
    every = phone._meta(phone.META_KEY, {})
    assert "app:old-id" not in every
    s = phone.settings(key)
    assert (s["name"], s["folder"], s["limit_gb"]) == ("Ben's Phone", "Music/Ben", 30.0)
    assert every[key]["code"] == "4659" and every[key]["address"] == phone_app.address
    assert phone._meta(phone.LINKS_KEY, {}) == {"usb-ben": key}, "plugged in by USB, it's still this phone"
    assert phone.last_device() == key
    assert phone.present() == [key]


def test_a_new_phone_is_kept_as_its_own(app, phone_app):
    import phone
    phone.present(search=True)
    key = phone.claim(phone_app.address, "4659", name="Jo's Phone")
    assert phone.settings(key)["name"] == "Jo's Phone" and phone.asking() == []
    assert phone.present() == [key]


def test_the_app_reads_its_id_and_code_back_after_a_reinstall():
    """
    The app keeps its id and code in Music/.24bit7 and reads them back when its own storage is empty (a reinstall),
    and says who it is on /hello before the code is asked for. No Android here, so the source is read: the order
    matters (the /hello answer must come before the code check, and installId must look at the file first).
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "android", "app", "src", "main", "java", "io", "github",
                            "twentyfourbit7", "transfer", "TransferService.kt"), encoding="utf-8").read()
    assert src.index('path == "/hello"') < src.index('headers["x-24bit7-code"] != code(this)')
    hello = src[src.index('path == "/hello"'):src.index('headers["x-24bit7-code"] != code(this)')]
    assert "installId" in hello and "free" not in hello, "only the id and model without the code"
    assert "marked(0)" in src[src.index("fun installId"):src.index("fun ensureIdentity")]
    assert "marked(1)" in src[src.index("fun code"):src.index("fun installId")]
    assert r'installId(c) + "\n" + code(c)' in src, "the file holds the id, then the code"


def test_forget_while_a_search_is_out_doesnt_bring_the_phone_back(app, phone_app, monkeypatch):
    """
    Ben, 25 Nov 2026: Forget "just doesn't work sometimes", and Forget then Add didn't help. A search already out
    when Forget was clicked wrote the phone's address back afterwards, which made the record again without its code
    (a "Pixel 9a" with nothing to type a code into). What a look learns is now kept only for a phone still on the
    list, so a forgotten phone that answers is asked about as a new one.
    """
    import phone
    key, _model, _known = phone.add_wifi("4659")
    phone.remember_quietly(key, address="127.0.0.1:1")   # moved, so only the search finds it
    real = phone.search_network

    def forgotten_midway(*a, **k):
        out = real(*a, **k)
        phone.forget(key)   # clicked while the search was out
        return out
    monkeypatch.setattr(phone, "search_network", forgotten_midway)
    assert phone.present(search=True) == []
    assert key not in phone._meta(phone.META_KEY, {}), "not put back by the search"
    monkeypatch.setattr(phone, "search_network", real)
    phone.present(search=True)
    assert phone.asking() == [{"address": phone_app.address, "key": key, "model": "Pixel 9a", "known": False}]
    assert key not in phone._meta(phone.META_KEY, {})
    assert phone.claim(phone_app.address, "4659", name="Ben's Phone") == key, "and added again from the question"
    assert phone.present() == [key]


def test_a_forgotten_phone_isnt_put_back_by_finding_it(app, phone_app):
    """The other background writer: opening a phone that moved keeps where it's found, but not for one forgotten
    in the meantime."""
    import phone
    key, _model, _known = phone.add_wifi("4659")
    entry = phone._meta(phone.META_KEY, {})[key]
    phone.forget(key)
    phone._touch(key, address=phone_app.address)
    assert key not in phone._meta(phone.META_KEY, {})
    phone.remember_quietly(key, **dict(entry, address="127.0.0.1:1"))
    phone.open_device(key, "Ben's Phone")
    assert phone._meta(phone.META_KEY, {})[key]["address"] == phone_app.address, "kept while it's on the list"


def test_type_its_code_reconnects_a_phone_that_lost_its_code(app, phone_app):
    """
    Ben, 25 Nov 2026: his phone was kept with its name but no code or address (from the write above), so it showed
    "not found" with no way in. Any WiFi phone not answering now has Type Its Code...: the code on the phone's
    screen finds it and puts it back, name and records kept. A wrong code changes nothing.
    """
    import phone
    key = "app:" + phone_app.app_id
    phone.remember_quietly(key, name="Ben's Phone", folder="Music/Ben")
    assert (key, "", "wifi", False) in phone.known(), "a WiFi phone, not answering"
    phone.present(search=True)
    assert phone.asking()[0]["known"] is True, "and the search asks about it by name"
    assert phone.reconnect(key, "1234") is None
    assert phone.reconnect(key, "12") is None
    assert phone._meta(phone.META_KEY, {})[key].get("code") is None
    assert phone.reconnect(key, "4659") == key
    s = phone._meta(phone.META_KEY, {})[key]
    assert (s["name"], s["folder"], s["code"], s["address"]) == ("Ben's Phone", "Music/Ben", "4659", phone_app.address)
    assert phone.present() == [key] and phone.asking() == []
