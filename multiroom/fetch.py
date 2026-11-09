"""
Fetching the track the Sonos is playing (Multiroom, stage one, 9 Nov 2026).

JRiver's Multiroom DLNA server hands any library track to a plain HTTP GET at /Music/F<key>.wav, with the server's
DSP and output format applied, and answers byte-range requests. So the follower needs no renderer of its own: it
reads the WAV header, then streams the samples from where it wants them into a buffer up to thirty seconds ahead.
JRiver renumbers the server's port when it restarts, so the server is found by name at every start.
"""

import collections
import re
import struct
import threading
import urllib.parse
import urllib.request

import numpy as np

MEDIA_SERVER = "urn:schemas-upnp-org:device:MediaServer:1"
HEADER_BYTES = 4096
CHUNK = 64 * 1024


def _home_first(location):
    """
    Sort key: the server's address on the home network before any other. JRiver answers on every adapter, and on
    Ben's media PC the first answer came from a VPN's 100.64 address (9 Nov 2026), which stops working when the VPN
    does. Python's sort is stable, so equals keep the order they answered in.
    """
    import ipaddress
    try:
        ip = ipaddress.ip_address(urllib.parse.urlparse(location).hostname or "")
    except ValueError:
        return 2
    if ip.is_loopback:
        return 1
    return 0 if ip.is_private and ip not in ipaddress.ip_network("100.64.0.0/10") else 2


def find_server(name, locations=None, timeout=3.0):
    """
    The base URL (http://ip:port) of the DLNA server whose friendly name contains name (case ignored), or None.
    locations stands in for the SSDP search in tests.
    """
    if locations is None:
        from .sonos import ssdp_search
        locations = ssdp_search(MEDIA_SERVER, timeout)
    for loc in sorted(locations, key=_home_first):
        try:
            with urllib.request.urlopen(loc, timeout=3) as r:
                xml = r.read().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        m = re.search(r"<friendlyName>(.*?)</friendlyName>", xml, re.S)
        if m and name.lower() in m.group(1).strip().lower():
            u = urllib.parse.urlparse(loc)
            return f"{u.scheme}://{u.netloc}"
    return None


def track_url(base, key):
    return f"{base}/Music/F{key}.wav"


class Format:
    """What a WAV header says: rate, channels, bits, int or float samples, where the data starts and how long it is."""

    def __init__(self, rate, channels, bits, is_float, data_offset, data_bytes):
        self.rate, self.channels, self.bits, self.is_float = rate, channels, bits, is_float
        self.data_offset, self.data_bytes = data_offset, data_bytes
        self.frame_bytes = channels * bits // 8

    @property
    def frames(self):
        """The track's length in samples, or None for a stream that doesn't say."""
        if not self.data_bytes or self.data_bytes >= 0xFFFFFFF0:
            return None
        return self.data_bytes // self.frame_bytes

    def __repr__(self):
        kind = "float" if self.is_float else "int"
        return f"Format({self.rate} Hz, {self.channels} ch, {self.bits}-bit {kind}, data at {self.data_offset})"


def parse_header(head):
    """The Format from the start of a WAV file. Raises ValueError if it isn't one, or the header is cut short."""
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    i, fmt = 12, None
    while i + 8 <= len(head):
        cid, size = head[i:i + 4], struct.unpack("<I", head[i + 4:i + 8])[0]
        if cid == b"fmt ":
            if i + 8 + 16 > len(head):
                break
            tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", head[i + 8:i + 24])
            if tag == 0xFFFE and size >= 40 and i + 8 + 40 <= len(head):   # WAVE_FORMAT_EXTENSIBLE: the real tag
                tag = struct.unpack("<H", head[i + 32:i + 34])[0]
            if tag not in (1, 3):
                raise ValueError(f"WAV format {tag} isn't PCM")
            fmt = (rate, ch, bits, tag == 3)
        elif cid == b"data":
            if fmt is None:
                raise ValueError("WAV data before its format")
            return Format(*fmt, i + 8, size)
        i += 8 + size + (size & 1)
    raise ValueError("WAV header cut short")


def to_float(raw, fmt):
    """Whole frames of raw sample bytes as a float32 array of (frames, channels), full scale at 1.0."""
    if fmt.is_float and fmt.bits == 32:
        a = np.frombuffer(raw, "<f4")
    elif fmt.bits == 16:
        a = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif fmt.bits == 24:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        a = v.astype(np.float32) / 8388608.0
    elif fmt.bits == 32:
        a = (np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648.0).astype(np.float32)
    else:
        raise ValueError(f"{fmt.bits}-bit samples")
    return a.reshape(-1, fmt.channels).astype(np.float32, copy=False)


def _get(url, start=None, end=None, timeout=10):
    req = urllib.request.Request(url)
    if start is not None:
        req.add_header("Range", f"bytes={start}-" + ("" if end is None else str(end)))
    return urllib.request.urlopen(req, timeout=timeout)


def read_format(url):
    """The track's Format, from its first few kilobytes."""
    with _get(url, 0, HEADER_BYTES - 1) as r:
        return parse_header(r.read(HEADER_BYTES))


class TrackStream:
    """
    One track, streamed from from_sample onwards into a buffer up to ahead seconds deep, on its own thread.

    read(n) is for the audio callback: it never waits. It returns n frames, with silence where the buffer ran dry,
    and how many of them were real. position is the sample index the next read starts at. seek(sample) drops the
    buffer and asks the server for a new range. done is set once the track's last sample has been read.
    """

    def __init__(self, url, from_sample=0, ahead=30.0, fmt=None):
        self.url = url
        self.fmt = fmt or read_format(url)
        self.ahead = ahead
        self.cond = threading.Condition()
        self.blocks = collections.deque()
        self.head = 0                 # frames already taken from blocks[0]
        self.buffered = 0             # frames waiting in blocks
        self.position = from_sample   # the sample index the next read() starts at
        self.ended = False            # the reader has reached the end of the track
        self.error = None             # the last fetch failure, as text
        self.short_reads = 0          # reads that ran out of data before the end of the track
        self.owed = 0                 # frames played as silence in a stall, dropped when they arrive
        self.closed = False
        self._gen = 0
        self._start_reader(from_sample)

    # --- the reader thread ---------------------------------------------------------------
    def _start_reader(self, sample):
        self._gen += 1
        threading.Thread(target=self._reader, args=(self._gen, sample), daemon=True, name="TrackStream").start()

    def _reader(self, gen, sample):
        f = self.fmt
        start = f.data_offset + sample * f.frame_bytes
        end = None
        if f.frames is not None:
            if sample >= f.frames:
                with self.cond:
                    if gen == self._gen:
                        self.ended = True
                return
            end = f.data_offset + f.data_bytes - 1
        limit = int(self.ahead * f.rate)
        left = b""
        try:
            with _get(self.url, start, end) as r:
                while True:
                    with self.cond:
                        while self._gen == gen and not self.closed and self.buffered >= limit:
                            self.cond.wait(0.5)
                        if self._gen != gen or self.closed:
                            return
                    data = r.read1(CHUNK)   # what has arrived, up to a chunk: read() would wait for all of it
                    if not data:
                        break
                    data = left + data
                    whole = len(data) - len(data) % f.frame_bytes
                    left = data[whole:]
                    if whole:
                        block = to_float(data[:whole], f)
                        with self.cond:
                            if self._gen != gen:
                                return
                            self.blocks.append(block)
                            self.buffered += len(block)
                            self.cond.notify_all()
        except Exception as e:
            with self.cond:
                if self._gen == gen:
                    self.error = f"{type(e).__name__}: {e}"
        with self.cond:
            if self._gen == gen:
                self.ended = True
                self.cond.notify_all()

    # --- the audio side --------------------------------------------------------------------
    def read(self, n):
        """
        (frames, real): n frames from position on, silence where the data hasn't arrived. Frames that came out as
        silence are owed: when they arrive they're dropped, so the stream stays placed through a stall.
        """
        out = np.zeros((n, self.fmt.channels), np.float32)
        got = 0
        with self.cond:
            while self.owed and self.blocks:
                b = self.blocks[0]
                drop = min(self.owed, len(b) - self.head)
                self.owed -= drop
                self.buffered -= drop
                self.head += drop
                if self.head >= len(b):
                    self.blocks.popleft()
                    self.head = 0
            if not self.owed:
                while got < n and self.blocks:
                    b = self.blocks[0]
                    take = min(n - got, len(b) - self.head)
                    out[got:got + take] = b[self.head:self.head + take]
                    got += take
                    self.head += take
                    if self.head >= len(b):
                        self.blocks.popleft()
                        self.head = 0
                self.buffered -= got
            if got < n and not self.ended:
                self.owed += n - got
                self.short_reads += 1
            self.cond.notify_all()
        self.position += n
        return out, got

    @property
    def done(self):
        """The reader reached the end and every sample has been read."""
        return self.ended and not self.blocks

    @property
    def seconds_ahead(self):
        return self.buffered / self.fmt.rate

    def wait_buffered(self, frames, timeout=5.0):
        """Waits until at least frames are buffered (or the track has ended). True if they are."""
        with self.cond:
            self.cond.wait_for(lambda: self.buffered >= frames or self.ended, timeout)
            return self.buffered >= frames

    def seek(self, sample):
        """Drops what's buffered and streams again from this sample."""
        with self.cond:
            self.blocks.clear()
            self.head = self.buffered = self.owed = 0
            self.position = sample
            self.ended = False
            self.error = None
            self.cond.notify_all()
            self._start_reader(sample)

    def close(self):
        with self.cond:
            self.closed = True
            self._gen += 1
            self.cond.notify_all()
