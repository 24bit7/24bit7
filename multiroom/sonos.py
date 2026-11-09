"""
The Sonos's clock (Multiroom, stage one, 9 Nov 2026).

The Sonos's newer local control API answers on a websocket at port 1443 with its playback position to the
millisecond. Reading it about a hundred times a second, each read gives one estimate of the counter origin C, our
clock's time at which positionMillis would have read zero: the read's midpoint minus the position. Most reads come
back in about 4 ms; the slow ones (15 to 80 ms at a track's start) carry more error, so the origin is the median of
the twenty quickest recent reads. The UPnP whole-second position was tried first and wobbles by 67 ms between starts.

The API key is the example one the open-source Sonos libraries use; the Sonos accepts any key in that form.
"""

import collections
import json
import re
import select
import socket
import ssl
import threading
import time
import urllib.parse
import urllib.request

KEY = "123e4567-e89b-12d3-a456-426655440000"
SUBPROTOCOL = "v1.api.smartspeaker.audio"
ZONE_PLAYER = "urn:schemas-upnp-org:device:ZonePlayer:1"
PLAYING = ("PLAYBACK_STATE_PLAYING",)


def info(ip, port=1400, timeout=3):
    """The Sonos's /info: householdId, groupId, the device's name and more."""
    with urllib.request.urlopen(f"http://{ip}:{port}/info", timeout=timeout) as r:
        return json.load(r)


def local_addresses():
    """This PC's IPv4 addresses, leaving out loopback. A PC with a VPN or a virtual adapter has more than one."""
    try:
        found = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        found = set()
    return sorted(ip for ip in found if not ip.startswith("127."))


def ssdp_search(target, timeout=3.0, ifaces=None):
    """
    Every location that answers an SSDP search for this device type, in the order they answered. The search goes
    out on each of the PC's addresses, since Windows sends multicast out of one adapter only, not always the LAN's.
    """
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
           f"MX: 2\r\nST: {target}\r\n\r\n").encode()
    socks = []
    for ip in (ifaces if ifaces is not None else local_addresses()) or [None]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if ip:
                s.bind((ip, 0))
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
            s.sendto(msg, ("239.255.255.250", 1900))
            socks.append(s)
        except OSError:
            s.close()
    found, end = [], time.monotonic() + timeout
    try:
        while socks and time.monotonic() < end:
            ready, _, _ = select.select(socks, [], [], min(0.3, max(0.0, end - time.monotonic())))
            for s in ready:
                try:
                    data, _ = s.recvfrom(65507)
                except OSError:
                    continue
                m = re.search(r"(?im)^location:\s*(\S+)", data.decode(errors="replace"))
                if m and m.group(1) not in found:
                    found.append(m.group(1))
    finally:
        for s in socks:
            s.close()
    return found


def find(name=None, locations=None, timeout=3.0):
    """
    The Sonos players on the network, as dicts with ip, name, householdId and groupId. With a name, only the ones
    whose room name contains it (case ignored). locations stands in for the SSDP search in tests.
    """
    if locations is None:
        locations = ssdp_search(ZONE_PLAYER, timeout)
    out, seen = [], set()
    for loc in locations:
        host = urllib.parse.urlparse(loc)
        ip = host.hostname
        if ip in seen:
            continue
        seen.add(ip)
        try:
            i = info(ip, host.port or 1400)
        except (OSError, ValueError):
            continue
        room = (i.get("device") or {}).get("name") or i.get("name") or ""
        if name and name.lower() not in room.lower():
            continue
        out.append({"ip": ip, "name": room, "householdId": i.get("householdId"), "groupId": i.get("groupId")})
    return out


Read = collections.namedtuple("Read", "t rtt pos_ms state")   # t: our clock at the read's midpoint, in seconds


def origin_of(reads, n=20):
    """The counter origin from a set of reads: the median of (t - position) over the n quickest. None if none."""
    good = sorted((r for r in reads if r.pos_ms is not None and r.state in PLAYING), key=lambda r: r.rtt)[:n]
    if not good:
        return None
    est = sorted(r.t - r.pos_ms / 1000.0 for r in good)
    mid = len(est) // 2
    return est[mid] if len(est) % 2 else (est[mid - 1] + est[mid]) / 2


class SonosClock(threading.Thread):
    """
    Reads the Sonos's playback status over and over on its own thread and keeps the recent reads.

    url is wss://ip:1443/websocket/api for a real Sonos; tests pass a fake's ws:// address. now is the clock every
    read is stamped with (time.perf_counter, the one the audio callbacks use).
    """

    def __init__(self, ip=None, household=None, group=None, url=None, interval=0.01, keep=10.0,
                 now=time.perf_counter, retry=1.0):
        super().__init__(daemon=True, name="SonosClock")
        self.url = url or f"wss://{ip}:1443/websocket/api"
        self.household, self.group = household, group
        self.interval, self.keep, self.now, self.retry = interval, keep, now, retry
        self.reads = collections.deque()
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.connected = threading.Event()
        self.error = None          # the last connection or read failure, as text
        self._ws = None

    # --- the reading thread ---------------------------------------------------------
    def _connect(self):
        from websockets.sync.client import connect
        ctx = None
        if self.url.startswith("wss:"):
            ctx = ssl.create_default_context()   # the Sonos's certificate is its own, so it isn't checked
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return connect(self.url, ssl=ctx, subprotocols=[SUBPROTOCOL], additional_headers={"X-Sonos-Api-Key": KEY},
                       open_timeout=5, close_timeout=1)

    def _command(self):
        return json.dumps([{"namespace": "playback:1", "command": "getPlaybackStatus",
                            "householdId": self.household, "groupId": self.group}, {}])

    def read_once(self, ws):
        """One status read: sends the command, waits for the answer, stamps it. Returns the Read."""
        a = self.now()
        ws.send(self._command())
        reply = json.loads(ws.recv(timeout=5))
        b = self.now()
        body = reply[1] if isinstance(reply, list) and len(reply) > 1 and isinstance(reply[1], dict) else {}
        pos = body.get("positionMillis")
        return Read((a + b) / 2, b - a, int(pos) if pos is not None else None, body.get("playbackState"))

    def run(self):
        while not self.stopping.is_set():
            try:
                with self._connect() as ws:
                    self._ws = ws
                    self.connected.set()
                    self.error = None
                    while not self.stopping.is_set():
                        self._keep(self.read_once(ws))
                        if self.interval:
                            self.stopping.wait(self.interval)
            except Exception as e:   # the Sonos went away, restarted or refused: try again shortly
                self.error = f"{type(e).__name__}: {e}"
            finally:
                self._ws = None
                self.connected.clear()
            self.stopping.wait(self.retry)

    def _keep(self, r):
        with self.lock:
            self.reads.append(r)
            while self.reads and self.reads[0].t < r.t - self.keep:
                self.reads.popleft()

    def stop(self):
        self.stopping.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    # --- what the follower asks ------------------------------------------------------
    def recent(self, window=None, since=None):
        """The kept reads, optionally only those of the last window seconds and those after since."""
        with self.lock:
            reads = list(self.reads)
        if window is not None and reads:
            reads = [r for r in reads if r.t >= self.now() - window]
        if since is not None:
            reads = [r for r in reads if r.t >= since]
        return reads

    def origin(self, window=2.0, n=20, since=None):
        """C from the twenty quickest playing reads of the last two seconds (and after since). None if none."""
        return origin_of(self.recent(window, since), n)

    def first_origin_after(self, t):
        """C from the first playing read after our time t: quick but rough, to place a stream at a fresh start."""
        for r in self.recent(since=t):
            if r.pos_ms is not None and r.state in PLAYING:
                return r.t - r.pos_ms / 1000.0
        return None

    def latest(self):
        with self.lock:
            return self.reads[-1] if self.reads else None

    @property
    def state(self):
        r = self.latest()
        return r.state if r else None

    @property
    def last_read_age(self):
        """Seconds since the last read came back, or None before the first."""
        r = self.latest()
        return None if r is None else self.now() - r.t

