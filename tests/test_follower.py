"""
Multiroom, the follower (9 Nov 2026): the Speakers play what the Sonos plays, in step. Everything here runs on a
simulated clock: a simulated Sonos counter, a stub JRiver, tracks whose every sample says where it is, and a fake
DAC that records which sample it was handed when. One test streams over HTTP from tests/fake_dlna.py.

The truth a test checks against: with the sound origin O (our time at which the track's first sample leaves the
Sonos), the sample at the head of a block handed over at our time t should be (t - O) * rate + DAC.
"""

import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import fetch, follower, mcws, output, sonos
finally:
    sys.path.remove(REPO)

PLAY = "PLAYBACK_STATE_PLAYING"
START, RESUME, DAC = 0.093, 0.095, 1660
FULL = 2 ** 23
# In step means within TOL ms of the truth: the follower leaves anything under its 1 ms dead band alone, and the
# clock's estimate sits a little late (the answer's 0.2 ms way back, positions in whole ms).
TOL = 1.3


# --- the simulated world ------------------------------------------------------------------------

class SimSonos(sonos.ReadLog):
    """
    A Sonos counter read about every 10 ms on the simulated clock, as the real one answers (9 Nov 2026): the request
    waits before the counter is read, the answer comes back in 0.2 ms, the position is in whole ms. errs: extra
    delay on the way back for the next reads, in seconds, the one thing that moves an upper bound.
    """

    def __init__(self, sim, every=0.0103, rtt=0.004, back=0.0002):
        super().__init__(now=sim.now, keep=10.0)
        self.sim, self.every, self.rtt, self.back = sim, every, rtt, back
        self.c0 = None
        self.errs = []
        self.next_t = sim.t

    def _fill(self):
        while self.next_t <= self.sim.t:
            t = self.next_t
            self.next_t += self.every
            if self.c0 is None:
                self._keep(sonos.Read(t, self.rtt, None, "PLAYBACK_STATE_IDLE"))
            else:
                back = self.back + (self.errs.pop(0) if self.errs else 0.0)
                a, b = t - (self.rtt - self.back), t + back
                self._keep(sonos.Read((a + b) / 2, b - a, int((t - self.c0) * 1000), PLAY))

    def recent(self, window=None, since=None):
        self._fill()
        return super().recent(window, since)

    def latest(self):
        self._fill()
        return super().latest()

    def play(self, at_ms=0, errs=()):
        """Starts (or jumps) the counter at at_ms now. Returns the counter origin C."""
        self._fill()
        self.c0 = self.sim.t - at_ms / 1000
        self.errs = list(errs)
        return self.c0

    def stop(self):
        self._fill()
        self.c0 = None


class SimStream:
    """TrackStream's shape, with no waiting: sample i reads i / 2**23 on the left and its negative on the right."""

    def __init__(self, fmt, from_sample):
        self.fmt, self.position = fmt, from_sample
        self.dry = False
        self.short_reads = 0
        self.owed = 0
        self.closed = False

    def read(self, n):
        out = np.zeros((n, 2), np.float32)
        got = 0
        if self.dry:
            self.short_reads += 1
        else:
            idx = np.arange(self.position, self.position + n)
            ok = idx < self.fmt.frames
            out[ok, 0] = (idx[ok] % FULL) / FULL
            out[ok, 1] = -out[ok, 0]
            got = int(ok.sum())
        self.position += n
        return out, got

    def seek(self, sample):
        self.position = sample

    @property
    def done(self):
        return self.position >= self.fmt.frames

    def wait_buffered(self, frames, timeout=5.0):
        return True

    def close(self):
        self.closed = True


class SimSource:
    def __init__(self, rate=44100, seconds=300):
        self.rate, self.seconds = rate, seconds
        self.streams = []

    def format(self, key):
        frames = int(self.seconds * self.rate)
        return fetch.Format(self.rate, 2, 24, False, 44, frames * 6)

    def open(self, key, fmt, from_sample):
        s = SimStream(fmt, from_sample)
        self.streams.append(s)
        return s


class StubJRiver:
    def __init__(self):
        self.zones = {"Sonos": {"state": 0, "key": None}, "Speakers": {"state": 0, "key": None}}
        self.stopped = []

    def info(self, zone):
        z = self.zones[zone]
        return {"state": z["state"], "key": z["key"], "next_key": None, "position_ms": 0, "name": f"Track {z['key']}",
                "status": ""}

    def stop(self, zone):
        self.zones[zone]["state"] = 0
        self.stopped.append(zone)


class World:
    def __init__(self, rate=44100, seconds=300, ppm=0.0, jitter=None, source=None, prime=1, burst=1):
        self.sim = output.SimTime(1000.0)
        self.sonos = SimSonos(self.sim)
        self.jr = StubJRiver()
        self.src = source or SimSource(rate, seconds)
        self.lines = []
        self.outs = []

        def open_output(dev, rate, channels, callback):
            o = output.FakeOutput(dev, rate, channels, callback, sim=self.sim, ppm=ppm, jitter=jitter, prime=prime,
                                  burst=burst)
            self.outs.append(o)
            return o

        self.f = follower.Follower(self.sonos, self.jr, "Sonos", "Speakers", self.src, open_output,
                                   start_ms=START * 1000, resume_ms=RESUME * 1000, dac=DAC, now=self.sim.now,
                                   say=self.lines.append)

    def play(self, key=1, at_ms=0, errs=()):
        self.jr.zones["Sonos"].update(state=mcws.PLAYING, key=key)
        return self.sonos.play(at_ms, errs)

    def run(self, seconds, step=0.02):
        end = self.sim.t + seconds
        while self.sim.t < end - 1e-9:
            self.f.step()
            o = self.f.out
            if o is not None and not o.closed:
                o.run(min(step, end - self.sim.t))
            else:
                self.sim.t = min(end, self.sim.t + step)

    def offsets(self, o_true, rate=44100, since=None, out=None):
        """
        For each block (after since) with music at its head: how far from the truth, in ms (late positive), by the
        time the block played (its slot), not when it was asked for.
        """
        res = []
        out = out or self.outs[-1]
        for (_, block), t in zip(out.blocks, out.slots):
            if since is not None and t < since:
                continue
            if block[0, 0] <= 0:
                continue
            idx = round(float(block[0, 0]) * FULL)
            d = ((t - o_true) * rate + DAC - idx + FULL / 2) % FULL - FULL / 2   # the index coding wraps at 2**23
            res.append(d / rate * 1000)
        return np.array(res)

    def said(self, fragment):
        return [line for line in self.lines if fragment in line]


# --- rule 1: placement -----------------------------------------------------------------------------

@pytest.mark.parametrize("rate", [44100, 192000])
def test_every_block_is_placed_to_the_sample(rate):
    sim = output.SimTime(500.0)
    fmt = SimSource(rate, 60).format(1)
    origin = 500.0 - 7.25   # the track's first sample left the Sonos 7.25 s ago
    p = follower.Player(SimStream(fmt, int(7.0 * rate)), rate, 2, DAC, origin)
    out = output.FakeOutput(None, rate, 2, p.callback, sim=sim)
    out.start()
    out.run(10.0)
    w = World(rate)
    w.outs = [out]
    off = w.offsets(origin, rate)
    assert len(off) > 100
    assert np.abs(off).max() < 1000 / rate, "a block was more than a sample out"


def test_a_block_before_the_track_starts_is_silence():
    # The DAC opens a little before the Sonos's first sample: what comes before sample 0 is silence.
    sim = output.SimTime(100.0)
    fmt = SimSource(44100, 60).format(1)
    p = follower.Player(SimStream(fmt, 0), 44100, 2, DAC, 100.2)
    out = output.FakeOutput(None, 44100, 2, p.callback, sim=sim)
    out.start()
    out.run(0.5)
    first_music = next(t for t, b in out.blocks if b.any())
    assert not out.blocks[0][1].any()
    assert 100.2 - DAC / 44100 - 0.03 < first_music < 100.2


# --- rule 2: a fresh start ------------------------------------------------------------------------

def test_a_fresh_start_is_in_step(capsys=None):
    w = World()
    w.run(0.5)
    c0 = w.play(key=7)
    w.run(6.0)
    assert w.outs, "the Speakers never started"
    off = w.offsets(c0 + START, since=c0 + 2.5)
    assert len(off) > 50 and np.abs(off).max() < TOL, f"out by up to {np.abs(off).max():.2f} ms"
    assert w.said("Track 7: 44.1 kHz, 24-bit.")
    assert w.said("Speakers in from the first note.")   # placed on the first read, before the Sonos's first note


def test_a_rough_first_read_is_pulled_in_gently_never_jumped():
    # The first reads after a start come back late: here they put the Speakers 1.5 ms behind. Two seconds in, the
    # refined clock finds that, and single samples are skipped until it's under a millisecond.
    w = World()
    w.run(0.5)
    c0 = w.play(errs=[0.0015] * 3)
    w.run(2.0)
    early = w.offsets(c0 + START, since=c0 + 1.0)
    assert np.median(early) == pytest.approx(1.5, abs=0.7)
    w.run(40.0)
    p = w.f.player
    assert p.moves == [] and p.nudged > 10
    late = w.offsets(c0 + START, since=c0 + 35)
    assert np.abs(late).max() < TOL
    assert w.said("Clock refined by")


# --- the Hugo's own way of asking for blocks ---------------------------------------------------------------

@pytest.mark.parametrize("rate,prime,burst", [(44100, 6, 1), (192000, 12, 4)])
def test_a_dac_that_asks_ahead_and_in_bursts_is_still_in_step(rate, prime, burst):
    # Silent check on the Hugo, 9 Nov 2026: six blocks asked for at once when it opens, and at 192 kHz four at a
    # time. Timing blocks by their own callbacks read that as errors of 8 to 100 ms and moved the Speakers out.
    w = World(rate=rate, prime=prime, burst=burst, jitter=lambda k: ((k * 7919) % 11 - 5) * 0.00006)
    w.run(0.5)
    c0 = w.play()
    w.run(60.0, step=0.05)
    off = w.offsets(c0 + START, rate=rate, since=c0 + 2.5)
    assert len(off) > 100 and np.abs(off).max() < TOL, f"out by up to {np.abs(off).max():.2f} ms"
    assert w.f.player.moves == []


# --- drift ----------------------------------------------------------------------------------------------

def test_a_dac_running_fast_is_held_in_step():
    # The Hugo's clock against the Sonos's: about 17 ppm on 9 Nov 2026. 30 ppm for ten minutes would be 18 ms.
    w = World(ppm=30.0, seconds=700, prime=6)
    w.run(0.5)
    c0 = w.play()
    w.run(600.0, step=0.1)
    off = w.offsets(c0 + START, since=c0 + 60)
    assert np.abs(off).max() < 1.5, f"out by up to {np.abs(off).max():.2f} ms"
    assert w.f.player.moves == []


def test_a_big_error_is_moved_at_once():
    w = World()
    w.run(0.5)
    c0 = w.play()
    w.run(3.0)
    w.f.player.lead += int(0.040 * 44100)   # 40 ms of silence: the Speakers drop 40 ms behind
    w.run(3.0)
    assert [by for _, by in w.f.player.moves] == [pytest.approx(0.040 * 44100, abs=50)]
    assert w.said("ms out; moved them")


# --- joining, jumping, stopping, changing track -----------------------------------------------------

def test_joining_a_track_already_playing():
    w = World()
    c0 = w.play(key=3, at_ms=40000)
    w.sim.t += 1.5          # the Sonos has been playing a while before the follower starts
    w.run(5.0)
    off = w.offsets(c0 + START, since=w.sim.t - 3)
    assert len(off) > 50 and np.abs(off).max() < TOL


def test_a_jump_is_placed_with_the_resume_lateness():
    # After a jump the Sonos's counter runs about 95 ms behind its sound (9 Nov 2026).
    w = World()
    w.run(0.5)
    w.play()
    w.run(5.0)
    c1 = w.sonos.play(at_ms=120000)
    w.run(5.0)
    off = w.offsets(c1 + START - RESUME, since=c1 + 120 + 2.5)
    assert len(off) > 50 and np.abs(off).max() < TOL
    assert w.said("Jumped to 120.0 s.")
    off_early = w.offsets(c1 + START - RESUME, since=c1 + 120 + 0.3)
    assert np.abs(off_early).max() < 2.0


def test_a_jump_back_seeks_rather_than_waiting():
    w = World()
    w.run(0.5)
    w.play(at_ms=100000)
    w.run(5.0)
    c1 = w.sonos.play(at_ms=20000)
    w.run(4.0)
    off = w.offsets(c1 + START - RESUME, since=c1 + 20 + 2.5)
    assert len(off) > 50 and np.abs(off).max() < TOL


def test_when_the_sonos_stops_the_speakers_stop():
    w = World()
    w.run(0.5)
    w.play()
    w.run(3.0)
    w.sonos.stop()
    w.jr.zones["Sonos"]["state"] = mcws.STOPPED
    w.run(2.0)
    assert w.f.out is None and w.outs[-1].closed
    assert w.said("The Sonos stopped, so the Speakers have too.")


def test_a_new_track_starts_fresh():
    w = World(seconds=5)
    w.run(0.5)
    w.play(key=1)
    w.run(5.0)          # the track ends; the next starts on the Sonos 300 ms later
    w.run(0.3)
    c2 = w.play(key=2)
    w.run(4.0)
    assert len(w.outs) == 2 and len(w.said("Track 1:")) == 1
    off = w.offsets(c2 + START, since=c2 + 2.5)
    assert len(off) > 50 and np.abs(off).max() < TOL
    assert w.said("Track 2: 44.1 kHz")


# --- rule 7: a dry buffer ----------------------------------------------------------------------------

def test_a_dry_buffer_is_silence_and_the_music_comes_back_in_place():
    w = World()
    w.run(0.5)
    c0 = w.play()
    w.run(4.0)
    w.src.streams[-1].dry = True
    w.run(0.5)
    w.src.streams[-1].dry = False
    w.run(3.0)
    assert len(w.said("isn't arriving fast enough")) == 1
    off = w.offsets(c0 + START, since=c0 + 2.5)
    assert np.abs(off).max() < TOL
    assert w.f.player.moves == []


# --- rule 10: freeing the DAC ----------------------------------------------------------------------------

def test_the_follower_zone_is_stopped_so_its_dac_is_free():
    w = World()
    w.jr.zones["Speakers"].update(state=mcws.PLAYING, key=5)
    w.run(0.5)
    w.play()
    w.run(1.0)
    assert w.jr.stopped == ["Speakers"]
    assert w.said("Stopped the Speakers zone in JRiver so its DAC is free.")


def test_a_drift_nudge_touches_one_sample_where_the_wave_changes_least():
    data = np.zeros((8, 2), np.float32)
    data[:, 0] = [0.0, 0.5, 0.9, 0.9, 0.5, 0.0, -0.5, -0.9]
    data[:, 1] = -data[:, 0]
    dropped = follower.nudge(data, 1)
    assert dropped[:, 0].tolist() == pytest.approx([0.0, 0.5, 0.9, 0.5, 0.0, -0.5, -0.9])
    repeated = follower.nudge(data[:7], -1)
    assert repeated[:, 0].tolist() == pytest.approx([0.0, 0.5, 0.9, 0.9, 0.9, 0.5, 0.0, -0.5])


# --- over HTTP, from the fake DLNA server ------------------------------------------------------------------

def test_streaming_from_the_server_is_placed_the_same():
    from fake_dlna import FakeDLNA
    with FakeDLNA() as server:
        server.add(21, rate=96000, seconds=8, bits=24)
        w = World(rate=96000, source=follower.Source(server.base))
        w.run(0.5)
        c0 = w.play(key=21)
        w.run(0.1)
        assert w.f.player is not None
        assert w.f.player.stream.wait_buffered(int(5.5 * 96000), timeout=10)
        w.run(5.0)
        off = w.offsets(c0 + START, rate=96000, since=c0 + 2.5)
        assert len(off) > 50 and np.abs(off).max() < TOL


# --- the output device ---------------------------------------------------------------------------------

def test_the_hugos_asio_driver_is_found_from_jrivers_name_for_it():
    # 9 Nov 2026, the media PC: JRiver calls the Speakers' DAC "Hugo (Chord Async USB 44.1kHz-384kHz)".
    found = [(8, "Hugo (Chord Async USB 44.1kHz-3", "MME", 2),
             (17, "Hugo (Chord Async USB 44.1kHz-384kHz)", "Windows DirectSound", 2),
             (18, "ASIO Chord  1.04", "ASIO", 2), (19, "JRiver Media Center 36", "ASIO", 2),
             (22, "Speakers (Xonar SoundCard)", "Windows WASAPI", 2),
             (24, "Hugo (Chord Async USB 44.1kHz-384kHz)", "Windows WASAPI", 2)]
    assert output.find_device("Hugo (Chord Async USB 44.1kHz-384kHz)", found) == 18   # ASIO, not its WASAPI twin
    assert output.find_device("Chord", found) == 18
    assert output.find_device("Speakers (Xonar SoundCard)", found) == 22
    assert output.find_device("Garage", found) is None
