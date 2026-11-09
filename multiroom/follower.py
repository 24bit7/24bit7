"""
The follower (Multiroom, stage one, 9 Nov 2026): plays what the Sonos plays on the Speakers' DAC, in step.

Terms, as in mockups/multiroom_stage1_plan.md:
  C     the counter origin: our time at which the Sonos's positionMillis would read zero
  O     the sound origin: our time at which the track's first sample leaves the Sonos's speaker
  late  how far the counter runs behind the sound: 0 after a fresh start, Resume after a jump or a resume
        O = C + Start - late
  The sample at the head of a block handed over at our time now is (now - O) * rate + DAC, so it leaves the DAC
  at the moment the Sonos plays it.

Built here (stage 1b): placement, a fresh start (placed on the first read, refined two seconds in and pulled in
gently), joining a track already playing, a jump within a track, drift, a dry buffer, stopping the follower zone so
its DAC is free, and the leader stopping. Still to come (1c): gapless carry-on between tracks, who paused, losing
the clock.

  py -m multiroom.follower --leader Sonos --follower Speakers [--server Multiroom] [--start 93] [--resume 95]
                           [--dac 1660] [--device NAME] [--sonos ROOM] [--env PATH]
"""

import argparse
import collections
import threading
import time

import numpy as np

from . import fetch, mcws, output, sonos

PLAYING = "PLAYBACK_STATE_PLAYING"
EARLY_MS = 0            # reads this far into a run are left out of the refined origin (none: the bounds don't need it)
REFINE_AFTER = 2.0      # seconds into a run when the first rough placement is refined
CORRECT_EVERY = 1.0     # seconds between drift checks
DEAD_BAND_MS = 1.0      # closer than this, nothing is done
SLEW_PPM_PER_MS = 50.0  # how hard an error is pulled in; at 20 the Hugo's 30 ppm drift would sit 1.5 ms out
SLEW_MAX_PPM = 300.0
JUMP_OVER_MS = 20.0     # further out than this, move straight there
RESET_MS = 300          # the counter going back by more than this starts a new run
FRESH_UNDER_MS = 1500   # a run that starts under this far into a track is a fresh start; further in, a jump
STOPPED_FOR = 1.0       # seconds the Sonos must stay stopped before the Speakers stop too
ANCHOR_FROM = 1.0       # the DAC's rate is measured from this far after its first block,
WINDOW = 2.0            # over windows this long


class Player:
    """
    One track into the DAC, placed on the sound origin. callback() runs on the audio thread.

    Timing: a callback's own time is not when its block plays. The Hugo's ASIO driver asks for six blocks at once
    when it opens, and at 192 kHz its buffer holds four of ours, so they come in bursts of four (silent check,
    9 Nov 2026). The first callback is the reference, as it was when the DAC delay was measured; after that the
    DAC's sample clock counts: n frames handed over play n / r seconds after the first, with r the DAC's rate on
    our clock, measured from callback times averaged over two-second windows, which cancels the bursts out.
    """

    def __init__(self, stream, rate, channels, dac, origin):
        self.stream, self.rate, self.channels, self.dac = stream, rate, channels, dac
        self.origin = origin
        self.lead = 0            # frames of silence to hand over before the stream's next sample
        self.slew = 0.0          # samples a second to skip (positive) or repeat (negative)
        self.debt = 0.0
        self.shift = 0           # whole samples to move by at the next block, forward positive
        self.first_at = None     # our time of the first block
        self.moves = []          # (our time, samples) of every move made
        self.nudged = 0          # single samples skipped or repeated
        self.lock = threading.Lock()
        self.handed = 0          # frames handed to the DAC so far
        self.marks = collections.deque(maxlen=1000)   # (our time, frames handed, sample index) after each block
        self.anchor = None       # (mean time, mean frames handed) over the first block window: see dac_rate
        self._acc = [0.0, 0.0, 0]

    @property
    def pos(self):
        """The sample index at the head of the next block."""
        return self.stream.position - self.lead

    def target(self, now):
        return (now - self.origin) * self.rate + self.dac

    def _move(self, by):
        """
        Moves the play point by samples. A short way forward skips samples (silence first), a short way back hands
        over silence; further than that, the stream seeks.
        """
        new = self.pos + by
        if by > self.rate * 2 or by < -self.rate // 2:
            self.stream.seek(max(0, new))
            self.lead = max(0, -new)
            return
        if by > 0:
            eat = min(by, self.lead)
            self.lead -= eat
            by -= eat
            if by > self.rate * 2:
                self.stream.seek(self.stream.position + by)
            elif by:
                self.stream.read(by)
        elif by < 0:
            self.lead -= by

    def _take(self, n):
        out = np.zeros((n, self.channels), np.float32)
        quiet = min(self.lead, n)
        self.lead -= quiet
        if n > quiet:
            out[quiet:] = self.stream.read(n - quiet)[0]
        return out

    def callback(self, out, frames, now):
        if self.first_at is None:
            self._move(int(round(self.target(now))) - self.pos)
            self.first_at = now
        if self.shift:
            by, self.shift = self.shift, 0
            self._move(by)
            self.moves.append((now, by))
        k = 0
        if self.slew:
            self.debt += self.slew * frames / self.rate
            if self.debt >= 1:
                k, self.debt = 1, self.debt - 1
            elif self.debt <= -1:
                k, self.debt = -1, self.debt + 1
        data = self._take(frames + k)
        if k:
            data = nudge(data, k)
            self.nudged += 1
        out[:] = data
        self.handed += frames
        with self.lock:
            self.marks.append((now, self.handed, self.pos))
            if self.anchor is None and now >= self.first_at + ANCHOR_FROM:
                if now < self.first_at + ANCHOR_FROM + WINDOW:
                    self._acc[0] += now
                    self._acc[1] += self.handed
                    self._acc[2] += 1
                elif self._acc[2]:
                    self.anchor = (self._acc[0] / self._acc[2], self._acc[1] / self._acc[2])

    def dac_rate(self):
        """
        The DAC's sample rate on our clock: frames handed between the anchor window (one to three seconds in) and
        the last two seconds, over the time between them, each the mean of its window. The nominal rate until the
        two are ten seconds apart.
        """
        with self.lock:
            anchor, marks = self.anchor, list(self.marks)
        if anchor is None or not marks:
            return float(self.rate)
        recent = [(t, h) for t, h, _ in marks if t >= marks[-1][0] - WINDOW]
        t1 = sum(t for t, _ in recent) / len(recent)
        h1 = sum(h for _, h in recent) / len(recent)
        if t1 - anchor[0] < 10:
            return float(self.rate)
        r = (h1 - anchor[1]) / (t1 - anchor[0])
        return min(max(r, self.rate * (1 - 1e-3)), self.rate * (1 + 1e-3))

    def error(self, now):
        """Where the Sonos is minus where the DAC is at our time now, in samples; None before the first block."""
        with self.lock:
            last = self.marks[-1] if self.marks else None
        if self.first_at is None or last is None:
            return None
        _, handed, pos = last
        playing = (now - self.first_at) * self.dac_rate()   # frames the DAC has played by now
        return self.target(now) - (pos + playing - handed)

    def correct(self, now):
        """The once-a-second drift check. Returns the error it found, in ms, or None before the first block."""
        e = self.error(now)
        if e is None:
            return None
        ms = e / self.rate * 1000
        if abs(ms) < DEAD_BAND_MS:
            self.slew = 0.0
        elif abs(ms) <= JUMP_OVER_MS:
            ppm = max(-SLEW_MAX_PPM, min(SLEW_MAX_PPM, ms * SLEW_PPM_PER_MS))
            self.slew = ppm / 1e6 * self.rate
        else:
            self.slew = 0.0
            self.shift = int(round(e))
        return ms


def nudge(data, k):
    """
    Drops (k = 1) or repeats (k = -1) one sample frame where the waveform changes least, so a drift correction is
    one sample in tens of thousands and nothing else is touched: between corrections the samples are bit-perfect.
    """
    if len(data) < 4:
        return data[:len(data) - k] if k > 0 else np.vstack([data, data[-1:]])
    step = np.abs(np.diff(data, axis=0)).sum(axis=1)
    j = int(np.argmin(step[1:-1])) + 1
    if k > 0:
        return np.delete(data, j, axis=0)
    return np.insert(data, j, data[j], axis=0)


class Source:
    """Tracks from JRiver's Multiroom DLNA server."""

    def __init__(self, base):
        self.base = base

    def format(self, key):
        return fetch.read_format(fetch.track_url(self.base, key))

    def open(self, key, fmt, from_sample):
        return fetch.TrackStream(fetch.track_url(self.base, key), from_sample, fmt=fmt)


Run = collections.namedtuple("Run", "t pos_ms fresh")   # a run of the counter: our time of its first read


class Follower:
    """
    The control loop: step() is called about fifty times a second. clock is a sonos.ReadLog (a SonosClock), jriver
    an mcws.JRiver, source a Source, open_output(device, rate, channels, callback) an output.Output or a fake. say
    gets each console line.
    """

    def __init__(self, clock, jriver, leader, follower, source, open_output, device=None, start_ms=90.0,
                 resume_ms=95.0, dac=1660, now=time.perf_counter, say=print, poll=0.5):
        self.clock, self.jriver, self.leader, self.follower = clock, jriver, leader, follower
        self.source, self.open_output, self.device = source, open_output, device
        self.start_s, self.resume_s, self.dac = start_ms / 1000, resume_ms / 1000, dac
        self.now, self.say, self.poll = now, say, poll
        self.info, self.info_at = None, None
        self.player = self.out = self.track = None
        self.runs = []                       # runs of the counter seen, newest last
        self._scanned = now() - 10
        self._prev = None
        self._stopped_since = None
        self._said_in = False
        self._dry = 0
        self._dry_at = None
        self.last = None                     # (key, run time, our time) of the track that last finished

    # --- watching the Sonos --------------------------------------------------------------
    def _scan(self):
        """Finds where the counter started a new run: from stopped, or going back, or jumping on."""
        for r in self.clock.recent(since=self._scanned):
            if r.t <= self._scanned:
                continue
            self._scanned = r.t
            playing = r.state == PLAYING and r.pos_ms is not None
            p = self._prev
            self._prev = r if playing else None
            if not playing:
                continue
            if p is None or r.pos_ms < p.pos_ms - RESET_MS or \
                    r.pos_ms - p.pos_ms > (r.t - p.t) * 1000 + RESET_MS:
                self.runs.append(Run(r.t, r.pos_ms, r.pos_ms < FRESH_UNDER_MS))

    def _sonos_playing(self):
        r = self.clock.latest()
        return r is not None and r.state == PLAYING and r.pos_ms is not None

    # --- the loop ----------------------------------------------------------------------------
    def begin(self):
        """Frees the DAC: stops the follower zone in JRiver if it's playing (rule 10)."""
        try:
            if self.jriver.info(self.follower)["state"] != mcws.STOPPED:
                self.jriver.stop(self.follower)
                self.say(f"Stopped the {self.follower} zone in JRiver so its DAC is free.")
        except KeyError:
            self.say(f"There's no zone called {self.follower} in JRiver.")

    def step(self):
        now = self.now()
        if self.info_at is None or now - self.info_at >= self.poll:
            self.info, self.info_at = self.jriver.info(self.leader), now
        self._scan()
        info = self.info
        if self.player is None:
            if not (self._sonos_playing() and info["state"] == mcws.PLAYING and info["key"]):
                return
            run = self.runs[-1] if self.runs else None
            if self.last is not None:
                if not (run and run.t > self.last[1]):
                    # The track that just finished is still ending on the Sonos, or the next hasn't begun there yet.
                    # If JRiver has moved on and the Sonos's counter never showed it, join after five seconds.
                    if info["key"] == self.last[0] or now - self.last[2] < 5:
                        return
                    run = None
                elif info["key"] == self.last[0] and now - run.t < 1.0:
                    # The Sonos has started a track but JRiver, asked every half second, still names the last
                    # one: ask again rather than start the old one over (a track played twice gets a second).
                    if self.info_at is not None and now - self.info_at >= 0.05:
                        self.info_at = None
                    return
            self._start(info, run, now)
            return
        if not self._sonos_playing():
            self._stopped_since = self._stopped_since or now
            if now - self._stopped_since >= STOPPED_FOR:
                self.finish(f"The {self.leader} stopped, so the Speakers have too.")
            return
        self._stopped_since = None
        run = self.runs[-1] if self.runs else None
        if info["key"] != self.track["key"]:
            if run and run.t > self.track["run_t"] and run.fresh:   # the Sonos has started the new track
                self.finish()
                self._start(info, run, now)
            return
        if run and run.t > self.track["run_t"]:
            self._jumped(run, now)
            return
        self._keep_in_step(now)

    def _start(self, info, run, now):
        """A track begins on the Speakers: on the first read of the Sonos's run, or mid-track on the recent reads."""
        if run is not None and run.fresh and now - run.t < 5:
            c, late, how = self.clock.first_origin_after(run.t), 0.0, "start"
        else:
            c, late, how = self.clock.origin(window=1.0), 0.0, "join"
            run = Run(now - 1.0, None, False)
        if c is None:
            return
        o = c + self.start_s - late
        fmt = self.source.format(info["key"])
        self.begin()
        first = max(0, int(round((now + 0.3 - o) * fmt.rate)) + self.dac)
        stream = self.source.open(info["key"], fmt, first)
        stream.wait_buffered(int(0.25 * fmt.rate), timeout=3)
        self.player = Player(stream, fmt.rate, fmt.channels, self.dac, o)
        self.out = self.open_output(self.device, fmt.rate, fmt.channels, self.player.callback)
        self.out.start()
        self.track = {"key": info["key"], "name": info.get("name") or str(info["key"]), "fmt": fmt, "run_t": run.t,
                      "c": c, "late": late, "refined": how == "join", "checked": now, "how": how}
        self._said_in = False
        self._dry = stream.short_reads
        bits = f"{fmt.bits}-bit{' float' if fmt.is_float else ''}"
        self.say(f"{self.track['name']}: {fmt.rate / 1000:g} kHz, {bits}.")

    def _jumped(self, run, now):
        """A jump within the track (or a resume): place again on the new run, with the counter Resume late."""
        c = self.clock.first_origin_after(run.t)
        if c is None:
            return
        t = self.track
        t.update(run_t=run.t, c=c, late=self.resume_s, refined=False, checked=now)
        p = self.player
        old = p.target(now)
        p.origin = c + self.start_s - t["late"]
        p.shift = int(round(p.target(now) - old))
        p.slew = 0.0
        self.say(f"Jumped to {run.pos_ms / 1000:.1f} s.")

    def _keep_in_step(self, now):
        t, p = self.track, self.player
        if p.first_at is not None and not self._said_in:
            self._said_in = True
            into = (p.first_at - p.origin) + p.dac / p.rate   # where the track was when the DAC's first block sounded
            if into <= 0:
                self.say("Speakers in from the first note.")
            else:
                self.say(f"Speakers in {into:.2f} s into the track.")
        since = max(t["run_t"], t["c"]) + EARLY_MS / 1000
        if not t["refined"]:
            if now - t["run_t"] < REFINE_AFTER:
                return
            c = self.clock.origin(window=REFINE_AFTER, since=since)
            if c is not None:
                t.update(refined=True, checked=now)
                self.say(f"Clock refined by {(c - t['c']) * 1000:+.1f} ms.")
                t["c"] = c
                p.origin = c + self.start_s - t["late"]
            return
        if now - t["checked"] >= CORRECT_EVERY:
            t["checked"] = now
            c = self.clock.origin(window=2.0, since=since)
            if c is not None:
                p.origin = c + self.start_s - t["late"]
            ms = p.correct(now)
            if ms is not None and abs(ms) > JUMP_OVER_MS:
                self.say(f"The Speakers were {ms:+.0f} ms out; moved them.")
        dry = p.stream.short_reads
        if dry > self._dry:   # one line a stall: a stall is over after a second with no dry block
            if self._dry_at is None or now - self._dry_at > 1.0:
                self.say("The music isn't arriving fast enough: the Speakers are quiet until it does, still in step.")
            self._dry_at = now
        self._dry = dry
        if p.stream.done and p.lead == 0 and self.out is not None:
            self.finish()

    def finish(self, why=None):
        """Stops the Speakers for this track."""
        if self.out is not None:
            self.out.close()
        if self.player is not None:
            self.player.stream.close()
            self.last = (self.track["key"], self.track["run_t"], self.now())
        self.out = self.player = None
        self._stopped_since = None
        if why:
            self.say(why)

    def run(self, stop=None, every=0.02):
        stop = stop or threading.Event()
        self.begin()
        try:
            while not stop.is_set():
                self.step()
                stop.wait(every)
        finally:
            self.finish()


# --- the command line ------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(prog="py -m multiroom.follower",
                                 description="Plays what the Sonos plays on the Speakers' DAC, in step.")
    ap.add_argument("--leader", default="Sonos", help="the JRiver zone that plays to the Sonos")
    ap.add_argument("--follower", default="Speakers", help="the JRiver zone whose DAC follows")
    ap.add_argument("--server", default="Multiroom", help="the JRiver DLNA server that serves the tracks")
    ap.add_argument("--sonos", default=None, help="the Sonos's room name, if there's more than one")
    ap.add_argument("--device", default=None, help="the output device, if not the follower zone's")
    ap.add_argument("--start", type=float, default=90.0, help="Start, in ms")
    ap.add_argument("--resume", type=float, default=95.0, help="Resume, in ms")
    ap.add_argument("--dac", type=int, default=1660, help="the DAC's delay, in samples")
    ap.add_argument("--env", default=".env", help="the .env with JRiver's address")
    a = ap.parse_args(argv)

    jr = mcws.JRiver(env=a.env)
    found = sonos.find(a.sonos)
    if not found:
        raise SystemExit("No Sonos found on the network." if not a.sonos else f"No Sonos called {a.sonos}.")
    if len(found) > 1 and not a.sonos:
        raise SystemExit("More than one Sonos: say which with --sonos " + " / ".join(d["name"] for d in found))
    s = found[0]
    base = fetch.find_server(a.server)
    if not base:
        raise SystemExit(f"No DLNA server called {a.server}: is it on in JRiver's Media Network settings?")
    hint = a.device or jr.device(a.follower)[0]
    dev = output.find_device(hint)
    if dev is None:
        raise SystemExit(f"No output device matches {hint!r}.")
    print(f"Leader {a.leader} ({s['name']}, {s['ip']}); follower {a.follower} on "
          f"{output._sd().query_devices(dev)['name']}; tracks from {base}.")
    print(f"Start {a.start:g} ms, Resume {a.resume:g} ms, DAC {a.dac} samples. Ctrl+C to stop.")
    clock = sonos.SonosClock(s["ip"], s["householdId"], s["groupId"])
    clock.start()
    f = Follower(clock, jr, a.leader, a.follower, Source(base), output.Output, dev, a.start, a.resume, a.dac,
                 say=lambda line: print(time.strftime("%H:%M:%S "), line, flush=True))
    try:
        f.run()
    except KeyboardInterrupt:
        pass
    finally:
        clock.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
