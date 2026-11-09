"""
The Speakers' DAC (Multiroom, stage one, 9 Nov 2026).

An output stream through PortAudio, ASIO by preference: on the media PC the Hugo's ASIO driver started within about
five milliseconds every time, and reports no latency of its own, so a block is placed by the time its callback runs.
The callback gets (out, frames, now), with now on the same clock as the Sonos's reads.

FakeOutput has the same shape, driven by a simulated clock, for the tests.
"""

import os
import re
import time

os.environ.setdefault("SD_ENABLE_ASIO", "1")   # sounddevice reads it when it loads, so before any import of it

import numpy as np  # noqa: E402

GENERIC = {"audio", "async", "output", "speakers", "speaker", "device", "digital", "driver", "high", "definition",
           "media", "center", "sound", "soundcard", "streaming", "electronics", "windows", "primary"}


def _sd():
    import sounddevice
    return sounddevice


def devices():
    """[(index, name, host api, output channels)] for every output device PortAudio sees."""
    sd = _sd()
    apis = sd.query_hostapis()
    return [(i, d["name"], apis[d["hostapi"]]["name"], d["max_output_channels"])
            for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] > 0]


def find_device(hint, found=None, prefer="ASIO"):
    """
    The index of the output device that best matches hint, ASIO first, or None. hint is a device name as JRiver
    gives it ("Hugo (Chord Async USB 44.1kHz-384kHz)"), or part of one. JRiver's name and the ASIO driver's
    ("ASIO Chord 1.04") rarely match whole, so a shared word of four letters or more counts, leaving out words
    every device has. Any ASIO device that matches beats any other that does; then WASAPI; JRiver's own ASIO
    driver is never chosen.
    """
    found = devices() if found is None else found
    want = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", hint or "")} - GENERIC
    order = {prefer: 2, "Windows WASAPI": 1}
    best, best_score = None, None
    for i, name, api, ch in found:
        if ch < 2 or "jriver" in name.lower():
            continue
        if hint and hint.lower() in name.lower():
            score = 10
        else:
            have = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", name)}
            score = len(want & have)
        if not score:
            continue
        score = (order.get(api, 0), score)
        if best_score is None or score > best_score:
            best, best_score = i, score
    return best


class Output:
    """A PortAudio output stream at one rate. callback(out, frames, now) fills out, a (frames, channels) array."""

    def __init__(self, device, rate, channels, callback, now=time.perf_counter, blocksize=0):
        sd = _sd()
        self.rate, self.channels = rate, channels
        self.status = None   # the last underflow or other PortAudio complaint, as text

        def cb(out, frames, tm, status):
            if status:
                self.status = str(status)
            callback(out, frames, now())

        self.stream = sd.OutputStream(device=device, samplerate=rate, channels=channels, dtype="float32",
                                      callback=cb, latency="low", blocksize=blocksize)

    @property
    def name(self):
        return _sd().query_devices(self.stream.device)["name"]

    def start(self):
        self.stream.start()

    def close(self):
        try:
            self.stream.stop()
        finally:
            self.stream.close()


class SimTime:
    """A clock the tests move by hand: now() is whatever t says."""

    def __init__(self, t=1000.0):
        self.t = t

    def now(self):
        return self.t


class FakeOutput:
    """
    An output that runs on a SimTime, as the Hugo's ASIO driver behaves (silent check, 9 Nov 2026). Block k plays
    at its slot, first + k * blocksize / rate on the DAC's own clock (ppm makes that clock fast). Its callback comes
    earlier: the first prime blocks are all asked for at once when the stream opens, the rest a steady prime - 1
    blocks ahead of their slots, and with burst over one, burst blocks at a time (the Hugo at 192 kHz: four).
    jitter(k) is added to each callback's time. Every block is kept with its callback time and its slot, so a test
    can see which sample played when.
    """

    instances = []

    def __init__(self, device, rate, channels, callback, sim=None, blocksize=1024, ppm=0.0, jitter=None, prime=1,
                 burst=1):
        self.device, self.rate, self.channels, self.callback = device, rate, channels, callback
        self.sim, self.blocksize, self.ppm = sim, blocksize, ppm
        self.prime, self.burst = prime, burst
        self.jitter = jitter or (lambda k: 0.0)
        self.blocks = []          # (callback time, block)
        self.slots = []           # the time each block played
        self.started = self.closed = False
        self.k = 0
        self.t0 = None
        FakeOutput.instances.append(self)

    name = "Fake DAC"

    def start(self):
        self.started = True
        self.t0 = self.sim.t

    def slot(self, k):
        return self.t0 + k * self.blocksize / self.rate / (1 + self.ppm / 1e6)

    def asked(self, k):
        """When block k's callback comes."""
        head = k - k % self.burst
        return max(self.t0, self.slot(head) - (self.prime - 1) * self.blocksize / self.rate) + self.jitter(k)

    def step(self):
        now = self.asked(self.k)
        self.sim.t = max(self.sim.t, now)
        out = np.zeros((self.blocksize, self.channels), np.float32)
        self.callback(out, self.blocksize, now)
        self.blocks.append((now, out))
        self.slots.append(self.slot(self.k))
        self.k += 1

    def run(self, seconds):
        """Blocks until seconds of the SimTime have gone by."""
        end = self.sim.t + seconds
        while not self.closed and self.asked(self.k) <= end:
            self.step()
        self.sim.t = max(self.sim.t, end)

    def close(self):
        self.closed = True
