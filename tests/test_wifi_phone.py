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

    def __init__(self, root, code="4659", app_id="0f8e1c2a-1111-2222-3333-444455556666"):
        self.root, self.code, self.app_id = str(root), code, app_id
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
                if not self._ok():
                    return
                route = urllib.parse.urlparse(self.path).path
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


def test_the_old_layout_is_sorted_over_wifi_by_copying(app, phone_app, tmp_path):
    """The app has no move, so sorting what 1.43 left reads each file back and writes it in its new place."""
    import phone
    key, model, _known = phone.add_wifi("4659")
    music = tmp_path / "storage" / "Music"
    (music / "Godsmack" / "Awake").mkdir(parents=True)
    (music / "Godsmack" / "Awake" / "01 Sick Of Life.flac").write_bytes(b"y" * 1000)
    ph = phone.open_device(key, "Ben's Phone")
    said = app.Lines()
    phone.arrange(ph, "Music", say=said)
    assert (music / "Albums" / "Godsmack" / "Awake" / "01 Sick Of Life.flac").read_bytes() == b"y" * 1000
    assert sorted(os.listdir(music)) == ["Albums"], said.text()


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
