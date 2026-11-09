"""
A fake Sonos for the Multiroom tests (9 Nov 2026): the websocket that answers getPlaybackStatus with a millisecond
counter, and the HTTP /info page with the household and group. Nothing here touches the real Sonos.

The counter runs on our own clock (time.perf_counter unless a test gives another), so a test can say exactly where the
Sonos's counter origin is and check that the follower found it.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

KEY = "123e4567-e89b-12d3-a456-426655440000"
SUBPROTOCOL = "v1.api.smartspeaker.audio"
HOUSEHOLD = "Sonos_FAKEHOUSEHOLD"
GROUP = "RINCON_FAKE01400:1"


class FakeSonos:
    """
    play(at_ms) starts the counter, pause() freezes it, resume() runs it on, jump(to_ms) moves it, next_track(gap_ms)
    restarts it from zero after a gap. latency is each read's round trip in seconds (split evenly either way, so the
    midpoint is exact); slow is a list of (there, back) delays used once each, first come first served, for the slow
    and lopsided reads at a track's start, whose midpoints are off by half the difference. quiet stops it answering; skew_ppm makes its counter run fast (positive) or slow.
    """

    def __init__(self, now=time.perf_counter, latency=0.004, name="Living Room", resume_late=0.095):
        self.now = now
        self.latency = latency
        self.slow = []
        self.name = name
        self.resume_late = resume_late
        self.skew_ppm = 0.0
        self.quiet = threading.Event()
        self.lock = threading.Lock()
        self.state = "PLAYBACK_STATE_IDLE"
        self._origin = None        # our time at which the counter read zero (running), or
        self._held_ms = 0          # the counter's value while paused
        self.late = 0.0            # how far the counter runs behind the sound: 0 after play, resume_late after a resume
        self.requests = []         # every command received, as parsed JSON
        self.refused = []          # connections turned away, and why
        self.conns = set()
        self._ws = None
        self._http = None

    # --- the counter -------------------------------------------------------------------
    def position_ms(self, at=None):
        with self.lock:
            if self.state != "PLAYBACK_STATE_PLAYING" or self._origin is None:
                return self._held_ms if self._origin is not None or self._held_ms else None
            t = self.now() if at is None else at
            return int((t - self._origin) * 1000 * (1 + self.skew_ppm / 1e6))

    @property
    def origin(self):
        """Our time at which the counter read (or would have read) zero, while it runs."""
        return self._origin

    def play(self, at_ms=0, slow=()):
        with self.lock:
            self.slow = list(slow)
            self._origin = self.now() - at_ms / 1000
            self.state = "PLAYBACK_STATE_PLAYING"
            self.late = 0.0

    def pause(self):
        held = self.position_ms()
        with self.lock:
            self._held_ms = held or 0
            self.state = "PLAYBACK_STATE_PAUSED"

    def resume(self):
        with self.lock:
            self._origin = self.now() - self._held_ms / 1000
            self.state = "PLAYBACK_STATE_PLAYING"
            self.late = self.resume_late

    def jump(self, to_ms):
        with self.lock:
            self._origin = self.now() - to_ms / 1000
            self.late = self.resume_late

    def next_track(self, gap_ms=0):
        with self.lock:
            self._origin = self.now() + gap_ms / 1000
            self.late = 0.0

    def stop(self):
        with self.lock:
            self._origin, self._held_ms = None, 0
            self.state = "PLAYBACK_STATE_IDLE"

    # --- the websocket -------------------------------------------------------------------
    def _round_trip(self):
        with self.lock:
            return self.slow.pop(0) if self.slow else (self.latency / 2, self.latency / 2)

    def _handle(self, conn):
        if conn.request.headers.get("X-Sonos-Api-Key") != KEY:
            self.refused.append("no API key")
            return
        if conn.subprotocol != SUBPROTOCOL:
            self.refused.append("wrong subprotocol")
            return
        self.conns.add(conn)
        try:
            self._serve(conn)
        except ConnectionClosed:
            pass
        finally:
            self.conns.discard(conn)

    def _serve(self, conn):
        for message in conn:
            cmd = json.loads(message)
            self.requests.append(cmd)
            head = cmd[0] if isinstance(cmd, list) and cmd else {}
            while self.quiet.is_set():
                time.sleep(0.01)
            there, back = self._round_trip()
            time.sleep(there)
            if head.get("namespace") != "playback:1" or head.get("command") != "getPlaybackStatus" \
                    or head.get("householdId") != HOUSEHOLD or head.get("groupId") != GROUP:
                reply = [{"namespace": head.get("namespace"), "success": False},
                         {"_objectType": "globalError", "errorCode": "ERROR_INVALID_PARAMETER"}]
            else:
                body = {"_objectType": "playbackStatus", "playbackState": self.state}
                pos = self.position_ms()
                if pos is not None:
                    body["positionMillis"] = pos
                reply = [{"namespace": "playback:1", "response": "playbackStatus", "success": True,
                          "householdId": HOUSEHOLD, "groupId": GROUP}, body]
            time.sleep(back)
            conn.send(json.dumps(reply))

    # --- the /info page --------------------------------------------------------------------
    def _info(self):
        return {"device": {"id": "RINCON_FAKE01400", "name": self.name, "model": "S18", "modelDisplayName": "One"},
                "householdId": HOUSEHOLD, "playerId": "RINCON_FAKE01400", "groupId": GROUP,
                "websocketUrl": "wss://127.0.0.1:1443/websocket/api"}

    # --- running ---------------------------------------------------------------------------
    def start(self):
        self._ws = serve(self._handle, "127.0.0.1", 0, subprotocols=[SUBPROTOCOL], compression=None)
        threading.Thread(target=self._ws.serve_forever, daemon=True).start()
        fake = self

        class Info(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/info":
                    self.send_error(404)
                    return
                body = json.dumps(fake._info()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Info)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return self

    @property
    def url(self):
        return f"ws://127.0.0.1:{self._ws.socket.getsockname()[1]}/websocket/api"

    @property
    def info_port(self):
        return self._http.server_address[1]

    def drop(self):
        """Closes every open connection, as a Sonos does when it restarts; it goes on accepting new ones."""
        for c in list(self.conns):
            c.close()

    def close(self):
        self.quiet.clear()
        self.drop()
        if self._ws is not None:
            self._ws.shutdown()
        if self._http is not None:
            self._http.shutdown()
            self._http.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.close()
