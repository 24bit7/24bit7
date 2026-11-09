"""
A fake of JRiver's Multiroom DLNA server for the Multiroom tests (9 Nov 2026): serves /Music/F<key>.wav with byte
ranges, as the real one does, and /description.xml with its friendly name.

Every sample says where it is: on the left channel a sample's value is its index (as a fraction of full scale), on
the right its negative, so a test can tell exactly which sample was handed over when, and that the channels are the
right way round.
"""

import re
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

SCALE = {16: 32768, 24: 8388608, 32: 16777216}   # 32 means 32-bit float, exact for indexes up to 2**24


class Track:
    def __init__(self, rate=44100, seconds=10.0, bits=24, channels=2, extensible=False):
        self.rate, self.bits, self.channels = rate, bits, channels
        self.frames = int(round(rate * seconds))
        self.extensible = extensible
        self.frame_bytes = channels * bits // 8

    def header(self):
        tag = 3 if self.bits == 32 else 1
        block = self.frame_bytes
        data_bytes = self.frames * block
        if self.extensible:
            fmt = struct.pack("<HHIIHHHHIH14s", 0xFFFE, self.channels, self.rate, self.rate * block, block, self.bits,
                              22, self.bits, 3, tag, b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71")
        else:
            fmt = struct.pack("<HHIIHH", tag, self.channels, self.rate, self.rate * block, block, self.bits)
        body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", data_bytes)
        return b"RIFF" + struct.pack("<I", len(body) - 4 + data_bytes) + body

    @staticmethod
    def value(i, bits):
        """The float a sample index decodes to on the left channel."""
        return (i % SCALE[bits]) / SCALE[bits]

    def frames_bytes(self, first, count):
        i = np.arange(first, first + count, dtype=np.int64) % SCALE[self.bits]
        if self.bits == 32:
            left = (i / SCALE[32]).astype("<f4")
            cols = [left, -left]
        else:
            cols = [i, -i]
        a = np.stack(cols[:self.channels], axis=1).reshape(-1)
        if self.bits == 16:
            return a.astype("<i2").tobytes()
        if self.bits == 24:
            v = a.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3]
            return v.tobytes()
        return a.astype("<f4").tobytes()

    @property
    def size(self):
        return len(self.header()) + self.frames * self.frame_bytes

    def byte_range(self, start, end):
        """The file's bytes from start to end inclusive, as chunks."""
        head = self.header()
        pos = start
        if pos < len(head):
            yield head[pos:min(end + 1, len(head))]
            pos = len(head)
        fb = self.frame_bytes
        while pos <= end:
            first = (pos - len(head)) // fb
            count = min(8192, self.frames - first)
            if count <= 0:
                return
            data = self.frames_bytes(first, count)
            skip = (pos - len(head)) - first * fb
            data = data[skip:skip + end + 1 - pos]
            yield data
            pos += len(data)


class FakeDLNA:
    def __init__(self, name="Multiroom"):
        self.name = name
        self.tracks = {}
        self.ranges = []           # (key, start, end) of every media request
        self.stall_at = None       # (key, byte offset, seconds): stop sending for that long once past that byte
        self._server = None

    def add(self, key, **kw):
        self.tracks[str(key)] = Track(**kw)
        return self.tracks[str(key)]

    def start(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                if self.path == "/description.xml":
                    body = (f"<?xml version=\"1.0\"?><root><device><friendlyName>{fake.name}</friendlyName>"
                            "<deviceType>urn:schemas-upnp-org:device:MediaServer:1</deviceType></device></root>").encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/xml")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                m = re.fullmatch(r"/Music/F(\d+)\.wav", self.path)
                track = fake.tracks.get(m.group(1)) if m else None
                if track is None:
                    self.send_error(404)
                    return
                size = track.size
                start, end = 0, size - 1
                rng = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
                if rng:
                    start = int(rng.group(1))
                    end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
                fake.ranges.append((m.group(1), start, end))
                if start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(206 if rng else 200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if rng:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                sent = start
                try:
                    for chunk in track.byte_range(start, end):
                        stall = fake.stall_at
                        if stall and stall[0] == m.group(1) and sent <= stall[1] < sent + len(chunk):
                            cut = stall[1] - sent
                            self.wfile.write(chunk[:cut])
                            self.wfile.flush()
                            time.sleep(stall[2])
                            chunk = chunk[cut:]
                            sent += cut
                        self.wfile.write(chunk)
                        sent += len(chunk)
                except (ConnectionError, OSError):
                    pass

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    @property
    def base(self):
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def location(self):
        return f"{self.base}/description.xml"

    def close(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.close()
