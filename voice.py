"""
24bit7 - voice commands.

A small listener for the Alexa skill (or anything else that knows the key).
It only listens on this PC (127.0.0.1); a tunnel is what connects it to Amazon.

  POST /command   header X-24bit7-Key: <VOICE_KEY>
                  body {"intent": "songs_by" | "music_like" | "genre",
                        "value": "Agnes Obel", "device": "<Alexa device ID>",
                        "zone": "Sonos"}        # zone is optional and beats the device's zone
                  reply {"speech": "Music like Agnes Obel, coming up on Sonos."}
  GET  /ping      same header; reply {"ok": true, "app": "24bit7", "version": ...}

Alexa gives a skill about eight seconds to answer, so the reply goes back at once
and the playlist is built afterwards, one build at a time, through the Play tab.
Each Alexa device is remembered in the database with the zone it plays to.
"""

import hmac
import json
import secrets
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import engine

INTENTS = ("songs_by", "music_like", "genre")
TEST_DEVICE = "24bit7-settings-test"

_server = None
_thread = None
_submit = None          # set by the GUI: submit(job, heading) queues a build on the Play tab
_status = "Off"
_lock = threading.Lock()


# --- devices ------------------------------------------------------------------

def _devices_table():
    engine.db().execute("""CREATE TABLE IF NOT EXISTS voice_devices (
        device_id TEXT PRIMARY KEY, name TEXT, zone TEXT, last_heard TEXT)""")


def devices():
    """[(device_id, name, zone, last_heard)], most recently heard first."""
    with _lock:
        _devices_table()
        return engine.db().execute(
            "SELECT device_id, name, zone, last_heard FROM voice_devices "
            "WHERE device_id != ? ORDER BY last_heard DESC", (TEST_DEVICE,)).fetchall()


def update_device(device_id, name=None, zone=None):
    with _lock:
        _devices_table()
        if name is not None:
            engine.db().execute("UPDATE voice_devices SET name=? WHERE device_id=?", (name, device_id))
        if zone is not None:
            engine.db().execute("UPDATE voice_devices SET zone=? WHERE device_id=?", (zone, device_id))
        engine.db().commit()


def remove_device(device_id):
    with _lock:
        _devices_table()
        engine.db().execute("DELETE FROM voice_devices WHERE device_id=?", (device_id,))
        engine.db().commit()


def _hear_device(device_id):
    """Records that a device spoke. Returns (name, zone); a new device gets a name and no zone."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _lock:
        _devices_table()
        con = engine.db()
        row = con.execute("SELECT name, zone FROM voice_devices WHERE device_id=?", (device_id,)).fetchone()
        if row:
            con.execute("UPDATE voice_devices SET last_heard=? WHERE device_id=?", (now, device_id))
        else:
            count = con.execute("SELECT COUNT(*) FROM voice_devices").fetchone()[0]
            row = (f"New speaker {count + 1}", "")
            con.execute("INSERT INTO voice_devices VALUES (?,?,?,?)", (device_id, row[0], "", now))
        con.commit()
    return row


# --- commands -----------------------------------------------------------------

def _job(intent, value, zone):
    """The build itself, run on the Play tab's worker thread."""
    def run(report):
        engine.refresh_settings_if_changed()
        engine.OUTPUT_OVERRIDE = zone
        try:
            if intent == "songs_by":
                engine.play_top_n(report=report, seed_info=engine.typed_seed_info(value))
            elif intent == "music_like":
                tracks, _ = engine.blended_top_tracks(value, limit=1)
                if not tracks:
                    report(f"Couldn't find top tracks for '{value}', so there's nothing to seed from.")
                    return
                report(f"  Seed track: {tracks[0][0]} (the artist's most popular track)")
                engine.create_similar_playlist(report=report, seed_info=engine.typed_seed_info(value, tracks[0][0]))
            else:
                engine.create_vibe_playlist(value, report=report)
        finally:
            engine.OUTPUT_OVERRIDE = None
    return run


def handle_command(body, busy=False):
    """
    Works out the reply and queues the build. Returns (status, speech):
      started  the build begins now (the skill plays two chimes)
      pending  it waits for the build already running (the skill says so)
      problem  nothing was queued; speech says why
    """
    intent = (body.get("intent") or "").strip().lower()
    value = (body.get("value") or "").strip()
    device = (body.get("device") or "").strip()
    if intent not in INTENTS:
        return "problem", "Say songs by, music like, or genre, followed by what you'd like."
    if not value:
        return "problem", ("I didn't catch the artist." if intent != "genre" else "I didn't catch the genre.")

    name, zone = _hear_device(device or "unknown device")
    zone = (body.get("zone") or "").strip() or zone
    if not zone:
        return "problem", "This speaker isn't set up yet. Assign it to a zone in 24bit7, under Settings, Voice."
    if engine.zone_id(zone) is None:
        return "problem", f"I can't find the {zone} zone in JRiver."
    if intent == "genre" and engine.vibe_blocker():
        return "problem", "Genre playlists need an Anthropic key in 24bit7."
    if _submit is None:
        return "problem", "24bit7 isn't ready yet. Try again in a moment."

    words = {"songs_by": f"Songs by {value}", "music_like": f"Music like {value}",
             "genre": f"A {value} playlist"}[intent]
    phrase = {"songs_by": "songs by", "music_like": "music like", "genre": "genre"}[intent]
    _submit(_job(intent, value, zone), f"Voice, {name}: {phrase} {value}, to {zone}")
    if busy:
        return "pending", "Please wait, request pending."
    return "started", f"{words}, coming up on {zone}."


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):   # keep the console quiet
        pass

    def _reply(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _key_ok(self):
        given = self.headers.get("X-24bit7-Key", "")
        return bool(engine.VOICE_KEY) and hmac.compare_digest(given, engine.VOICE_KEY)

    def do_GET(self):
        if self.path.split("?")[0] != "/ping":
            return self._reply(404, {"error": "not found"})
        if not self._key_ok():
            return self._reply(401, {"error": "wrong key"})
        self._reply(200, {"ok": True, "app": "24bit7", "version": engine.VERSION})

    def do_POST(self):
        if self.path.split("?")[0] != "/command":
            return self._reply(404, {"error": "not found"})
        if not self._key_ok():
            return self._reply(401, {"error": "wrong key"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 10000)) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._reply(400, {"error": "body must be a JSON object"})
        status, speech = handle_command(body, busy=_is_busy())
        self._reply(200, {"status": status, "speech": speech})


_is_busy = lambda: False   # replaced by the GUI


# --- starting and stopping ------------------------------------------------------

def attach(submit, is_busy):
    """The GUI hands over how to queue a build and how to tell if one is running."""
    global _submit, _is_busy
    _submit, _is_busy = submit, is_busy


def new_key():
    return secrets.token_urlsafe(24)


def status():
    return _status


def stop():
    global _server, _thread, _status
    if _server is not None:
        _server.shutdown()
        _server.server_close()
    _server, _thread, _status = None, None, "Off"


def restart():
    """Starts (or stops) the listener to match the current settings."""
    global _server, _thread, _status
    stop()
    engine.refresh_settings_if_changed()
    if not engine.VOICE_ENABLED:
        return _status
    if not engine.VOICE_KEY:
        _status = "Off: no key yet"
        return _status
    try:
        _server = ThreadingHTTPServer(("127.0.0.1", engine.VOICE_PORT), _Handler)
    except OSError:
        _status = f"Off: port {engine.VOICE_PORT} is already in use"
        _server = None
        return _status
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    _status = f"Listening on 127.0.0.1:{engine.VOICE_PORT}"
    return _status


def send_test(artist, zone):
    """What the Settings Test button sends: a real music_like command through the listener."""
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{engine.VOICE_PORT}/command",
        data=json.dumps({"intent": "music_like", "value": artist, "device": TEST_DEVICE,
                         "zone": zone}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-24bit7-Key": engine.VOICE_KEY or ""},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            reply = json.loads(r.read())
    except Exception as e:
        return f"get no reply from the listener ({e})."
    if reply.get("status") == "started":
        return f"chime twice. ({reply.get('speech', '')})"
    return f'say "{reply.get("speech", "")}"'
