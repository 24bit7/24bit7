"""
The follower (Multiroom, stage one, 9 Nov 2026): plays what the Sonos plays on the Speakers' DAC, in step.

Terms, as in mockups/multiroom_stage1_plan.md:
  C     the counter origin: our time at which the Sonos's positionMillis would read zero
  O     the sound origin: our time at which the track's first sample leaves the Sonos's speaker
  E     where a track's sound ends: O + its length
  late  how far the counter runs behind the sound: 0 after a fresh start, Resume after a jump or a resume,
        about 100 ms after a gapless change
        O = C + Start - late
  The sample at the head of a block handed over at our time now is (now - O) * rate + DAC, so it leaves the DAC
  at the moment the Sonos plays it.

What it does: places a fresh start on the Sonos's first reads and refines it two seconds in; joins a track already
playing; carries straight on into the next track when the rate is the same, and at a new rate opens the DAC afresh
but still places the track on the Sonos's change from the last one, its counter measured against where the last
track's sound ended (the change is gapless from the Sonos's side whatever the files' rates, since JRiver sends it
44.1 kHz throughout); steps back to match if the Sonos left a gap after all; trusts the next track it was told of
over JRiver's name for it, which can lag the Sonos by seconds at a change; follows a jump; holds drift to a
millisecond; keeps its place through a dry buffer; on a pause stops the Speakers and the leader zone too, so play
starts the track from the top in both rooms (Ben, 9 Nov 2026: a resumed track is never joined, since the counter's
lateness after a resume isn't known; one played on from a pause is left until the next track); carries on through a
lost clock for a minute; stops the follower zone in JRiver so its DAC is free.

  py -m multiroom.follower --leader Sonos --follower Speakers [--server Multiroom] [--start 90] [--resume 95]
                           [--dac 1660] [--device NAME] [--sonos ROOM] [--env PATH]
"""

import argparse
import collections
import threading
import time

import numpy as np

from . import fetch, mcws, output, sonos

PLAYING = "PLAYBACK_STATE_PLAYING"
PAUSED = "PLAYBACK_STATE_PAUSED"   # paused at the speaker or by JRiver; buffering and idle are other states
REFINE_AFTER = 2.0      # seconds into a run when the first placement is refined
CORRECT_EVERY = 1.0     # seconds between drift checks
DEAD_BAND_MS = 1.0      # closer than this, nothing is done
SLEW_PPM_PER_MS = 50.0  # how hard an error is pulled in; at 20 the Hugo's 30 ppm drift would sit 1.5 ms out
SLEW_MAX_PPM = 300.0
JUMP_OVER_MS = 20.0     # further out than this, move straight there
RESET_MS = 300          # the counter going back by more than this starts a new run
FRESH_UNDER_MS = 1500   # a run that starts under this far into a track is a fresh start; further in, a jump
STOPPED_FOR = 1.0       # seconds the Sonos must stay stopped before the Speakers act on it
WAIT_FOR = 5.0          # and buffering or idle while JRiver still plays, before they give up on it
ANCHOR_FROM = 1.0       # the DAC's rate is measured from this far after its first block,
WINDOW = 2.0            # over windows this long
CHANGE_MS = (-30, 250)  # a new track's counter this far behind the last one's sound end means the sound ran straight
#                         on (about 100 ms at the same rate, 9 Nov 2026; the band is wide until a rate change is
#                         measured); further behind, the Sonos left a gap and the new track is a fresh start
CHANGE_WINDOW = 1.5     # a fresh run this close to a track's sound end is the Sonos moving on to the next track
SKIP_WAIT = 1.5         # seconds a fresh run mid-track waits for JRiver to name the track, before it's a restart
PREFETCH = 20.0         # seconds before a track's end that the next one is opened
LOST_AFTER = 5.0        # seconds without a read before the Speakers carry on on their own
GIVE_UP = 60.0          # and before they stop


class Player:
    """
    One run of the DAC, placed on the sound origin, carrying on from track to track while the rate stays the same.
    callback() runs on the audio thread.

    Timing: a callback's own time is not when its block plays. The Hugo's ASIO driver asks for six blocks at once
    when it opens, and at 192 kHz its buffer holds four of ours, so they come in bursts of four (silent check,
    9 Nov 2026). The first callback is the reference, as it was when the DAC delay was measured; after that the
    DAC's sample clock counts: n frames handed over play n / r seconds after the first, with r the DAC's rate on
    our clock, measured from callback times averaged over two-second windows, which cancels the bursts out.
    """

    def __init__(self, stream, rate, channels, dac, origin):
        self.stream, self.rate, self.channels, self.dac = stream, rate, channels, dac
        self.origin = origin
        self.next = None         # the next track's stream, to carry straight on into
        self.chains = []         # (our time, key carried on from, key carried on to, the new origin)
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

    def set_origin(self, origin, chains):
        """Moves the origin, unless the player has carried on into another track since the caller last looked."""
        with self.lock:
            if len(self.chains) == chains:
                self.origin = origin
                return True
        return False

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
            if by:
                self.stream.read(by)
        elif by < 0:
            self.lead -= by

    def _chain(self, now):
        """The track has run out: carry straight on into the next, if one is ready. False if not."""
        with self.lock:
            nxt, old = self.next, self.stream
            if nxt is None:
                return False
            self.origin += old.fmt.frames / self.rate
            self.stream, self.next = nxt, None
            self.chains.append((now, getattr(old, "key", None), getattr(nxt, "key", None), self.origin))
        old.close()
        return True

    def _take(self, n, now):
        out = np.zeros((n, self.channels), np.float32)
        quiet = min(self.lead, n)
        self.lead -= quiet
        i = quiet
        while i < n:
            s = self.stream
            left = s.fmt.frames - s.position if s.fmt.frames is not None else n - i
            if left <= 0:
                if not self._chain(now):
                    break   # the end of the track: silence
                continue
            take = min(n - i, left)
            out[i:i + take] = s.read(take)[0]
            i += take
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
        data = self._take(frames + k, now)
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
            origin = self.origin
        if self.first_at is None or last is None:
            return None
        _, handed, pos = last
        playing = (now - self.first_at) * self.dac_rate()   # frames the DAC has played by now
        return (now - origin) * self.rate + self.dac - (pos + playing - handed)

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

    def place(self, now):
        """Moves straight to where the origin says, at the next block (after a jump or a gap)."""
        e = self.error(now)
        self.slew = 0.0
        if e is not None:
            self.shift = int(round(e))


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
        s = fetch.TrackStream(fetch.track_url(self.base, key), from_sample, fmt=fmt)
        s.key = key
        return s


# A run of the counter: our time of its first read, where it began, whether that was a track's start, and whether
# we watched it begin (a read came just before it) rather than finding it already going.
Run = collections.namedtuple("Run", "t pos_ms fresh seen")


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
        self.names = {}                      # track key: name, as JRiver gave them
        self.player = self.out = self.track = None
        self.runs = []                       # runs of the counter seen, newest last
        self._scanned = now() - 10
        self._prev = self._last_t = None
        self._stopped_since = None
        self._said_in = False
        self._dry = 0
        self._dry_at = None
        self._lost = False
        self._chains = 0                     # the player's carry-ons dealt with
        self.last = None                     # the track that last finished: key, run_t, at (our time), end (our
        #                                      time its sound ended, if it ran out) and next (the key after it)
        self._paused = None                  # the key of a track the Sonos paused on: not joined until the next
        self._paused_other = None            # our time JRiver first named another track meanwhile, with no fresh run
        self._said_wait = False
        self.leaving = False                 # finish the track the Speakers are on, then stop following
        self._left = False                   # done: run() returns

    # --- watching the Sonos and JRiver --------------------------------------------------------
    def _scan(self):
        """Finds where the counter started a new run: from stopped, or going back, or jumping on."""
        for r in self.clock.recent(since=self._scanned):
            if r.t <= self._scanned:
                continue
            seen = self._last_t is not None and r.t - self._last_t < 1.0
            self._scanned = self._last_t = r.t
            playing = r.state == PLAYING and r.pos_ms is not None
            p = self._prev
            self._prev = r if playing else None
            if not playing:
                continue
            if p is None or r.pos_ms < p.pos_ms - RESET_MS or \
                    r.pos_ms - p.pos_ms > (r.t - p.t) * 1000 + RESET_MS:
                self.runs.append(Run(r.t, r.pos_ms, r.pos_ms < FRESH_UNDER_MS, seen))

    def _sonos_playing(self):
        r = self.clock.latest()
        return r is not None and r.state == PLAYING and r.pos_ms is not None and \
            self.clock.last_read_age < LOST_AFTER

    def _ask(self, now):
        self.info, self.info_at = self.jriver.info(self.leader), now
        if self.info.get("key") and self.info.get("name"):
            self.names[self.info["key"]] = self.info["name"]

    def name(self, key):
        return self.names.get(key) or f"track {key}"

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
            self._ask(now)
        self._scan()
        if self.player is None:
            self._idle(now)
        else:
            self._follow(now)

    def _idle(self, now):
        info = self.info
        if self.leaving:
            self._left = True   # nothing more starts: Output moved away from Multiroom while nothing was playing
            return
        if not (self._sonos_playing() and info["state"] == mcws.PLAYING and info["key"]):
            return
        run = self.runs[-1] if self.runs else None
        last, end = self.last, None
        if last is not None:
            if not (run and run.t > last["run_t"]):
                # The track that just finished is still ending on the Sonos, or the next hasn't begun there yet.
                # If JRiver has moved on and the Sonos's counter never showed it, join after five seconds.
                if info["key"] == last["key"] or now - last["at"] < 5:
                    return
                run = None
            elif run.fresh:
                if last["end"] is not None and abs(run.t - last["end"]) < CHANGE_WINDOW:
                    end = last["end"]   # the Sonos moved on as the last track ran out
                    if info["key"] == last["key"]:
                        # JRiver, asked every half second, still names the track that just ended; on a DLNA zone it
                        # can take six seconds to catch up (9 Nov 2026, twice). The next track it gave us before the
                        # end is the one playing. Without one, or with the same track twice in the list, JRiver gets
                        # a second, then its list is read again (a top-up may have added the track late).
                        if last["next"] not in (None, last["key"]):
                            self._start(last["next"], run, now, end=end, from_key=last["key"])
                        elif now - run.t < 1.0:
                            if now - self.info_at >= 0.05:
                                self.info_at = None
                        else:
                            key = self._after(last["key"]) or info["key"]
                            self._start(key, run, now, end=end, from_key=last["key"] if key != info["key"] else None)
                        return
            elif self._paused is not None:
                # The Sonos played on from where it paused (the leader zone couldn't be stopped, or play came from
                # the Sonos itself): how late its counter runs after a resume isn't known, so the Speakers sit this
                # track out rather than play it out of step, and start again on a fresh run, the next track's
                # start. JRiver naming another track without one (its start missed) joins after five seconds.
                if info["key"] == self._paused:
                    self._paused_other = None
                    if not self._said_wait:
                        self._said_wait = True
                        self.say(f"The {self.leader} played on from where it paused, so the Speakers wait for the "
                                 f"next track.")
                    return
                self._paused_other = self._paused_other or now
                if now - self._paused_other < 5:
                    return
                run = None
        self._start(info["key"], run, now, end=end)

    def _follow(self, now):
        info = self.info
        if self._clock_lost(now):
            return
        if not self._sonos_playing():
            self._sonos_stopped(now)
            return
        self._stopped_since = None
        self._carried_on(now)
        if self.player is None:
            return
        t, p = self.track, self.player
        run = self.runs[-1] if self.runs else None
        if t["late"] is None:                              # carried on: waiting for the Sonos's counter to say how
            if run and run.t > t["run_t"] and run.fresh:
                self._settle_carry(run, now)
            elif now - t["run_t"] > 3:                     # it never showed a new run: take the clock as it is
                self._settle_carry(None, now)
            self._housekeeping(now)
            return
        fresh = run is not None and run.fresh and run.t > t["run_t"]
        end = self._end()
        changing = fresh and end is not None and abs(run.t - end) < CHANGE_WINDOW   # the Sonos moving on at the end
        if info["key"] == t["key"]:
            t.pop("from_key", None)
            t.pop("other_since", None)
        elif info["key"] != t.get("from_key"):
            # JRiver names another track. The Sonos starting it shows as a fresh run; until it does, the Speakers
            # carry on (JRiver moves on a moment before the Sonos does). The next track already open is left to
            # carry on into; anything else for five seconds, and the Speakers join the Sonos where it is.
            nxt = p.next
            if nxt is not None and getattr(nxt, "key", None) == info["key"]:
                pass
            elif fresh and now - run.t < 5:
                self.finish(end=end if changing else None)
                self._start(info["key"], run, now, end=self.last["end"])
                return
            elif now - t.setdefault("other_since", now) > 5:
                self.finish()
                self._start(info["key"], run, now)
                return
        if run and run.t > t["run_t"]:
            if changing:
                if p.next is None:
                    # The next track isn't chained (a new rate, or none known): this one ends here, and _idle starts
                    # the next on this run, placed by the Sonos's change. Taking the run for a jump to the start of
                    # this track is what played six seconds of the old one over the new (9 Nov 2026).
                    self.finish(end=end)
                else:
                    self._housekeeping(now)   # the player is about to carry on into it; _settle_carry takes it then
                return
            if run.fresh:
                # The Sonos started a track from the top mid-track: a skip to another track, which JRiver names
                # within a second or so of the Sonos starting it, or this track started over. The Speakers hold
                # where they are and ask JRiver quickly; another name is dealt with above on the next step. Taking
                # the run for a restart at once put the old track's opening over the new one for five seconds
                # (9 Nov 2026, twice).
                since = t.setdefault("fresh_since", now)
                if now - since < SKIP_WAIT:
                    if now - self.info_at >= 0.05:
                        self.info_at = None
                    self._housekeeping(now)
                    return
                t.pop("fresh_since", None)
            self._jumped(run, now)
            return
        self._keep_in_step(now)

    def _end(self):
        """Our time at which the track the Speakers are on ends on the Sonos, if its length is known."""
        p = self.player
        frames = p.stream.fmt.frames
        return None if frames is None else p.origin + frames / p.rate

    # --- starting ------------------------------------------------------------------------------
    def _start(self, key, run, now, end=None, from_key=None):
        """
        A track begins on the Speakers: on the first reads of the Sonos's run, or mid-track on the recent reads.
        end: our time the last track's sound ended, when the Sonos moved straight on to this one from it; the
        counter is then measured against it, and the track placed where the sound ran on (the Sonos's counter
        runs about 100 ms behind its sound at a change, so taking the run for a fresh start put the Speakers that
        far ahead, 9 Nov 2026). from_key: the track JRiver may still be naming while this one plays.
        """
        late, d = 0.0, None
        if run is not None and run.fresh and now - run.t < 5:
            c, how = self.clock.first_origin_after(run.t), "start"
            if c is not None and end is not None:
                d = (c + self.start_s - end) * 1000
                if CHANGE_MS[0] <= d <= CHANGE_MS[1]:
                    late, how = d / 1000, "change"
        else:
            # Joining: a run we watched begin mid-track was a jump or a resume, with the counter Resume late; one
            # already going when we came, or a track's start, we take as on time.
            if run is not None and run.seen and not run.fresh:
                late = self.resume_s
            if run is None:
                run = Run(now - 1.0, None, False, False)
            c, how = self.clock.origin(window=1.0, since=run.t), "join"
        if c is None:
            return
        o = c + self.start_s - late
        fmt = self.source.format(key)
        self.begin()
        first = max(0, int(round((now + 0.3 - o) * fmt.rate)) + self.dac)
        stream = self.source.open(key, fmt, first)
        stream.wait_buffered(int(0.25 * fmt.rate), timeout=3)
        self.player = Player(stream, fmt.rate, fmt.channels, self.dac, o)
        self.out = self.open_output(self.device, fmt.rate, fmt.channels, self.player.callback)
        self.out.start()
        self._chains = 0
        self.track = {"key": key, "fmt": fmt, "run_t": run.t, "c": c, "late": late, "carried": how == "change",
                      "refined": how == "join" and now - run.t >= REFINE_AFTER,   # a run joined young is refined later
                      "checked": now, "next": None, "next_key": None}
        if from_key is not None:
            self.track["from_key"] = from_key
        self._paused = self._paused_other = None
        self._said_wait = self._said_in = False
        self._dry = stream.short_reads
        line = f"{self.name(key)}: {self._format(fmt)}"
        if how == "change":
            line += f", straight on from the last track; the {self.leader}'s counter is {d:.0f} ms behind."
        elif d is not None:
            line += f", after a gap of {d:.0f} ms."
        else:
            line += "."
        self.say(line)

    @staticmethod
    def _format(fmt):
        return f"{fmt.rate / 1000:g} kHz, {fmt.bits}-bit{' float' if fmt.is_float else ''}"

    # --- the next track -------------------------------------------------------------------------
    def _next_key(self):
        """The track after the one the Speakers are on: JRiver's next while it's on the same track, else from its list."""
        key = self.track["key"]
        after = self._after(key)
        if self.info.get("key") == key:
            return self.info.get("next_key")
        return after

    def _after(self, key):
        """The track after key in the leader zone's list, from JRiver; None at the end of it or if it isn't there."""
        try:
            listed = self.jriver.playlist(self.leader)
        except Exception:
            return None
        self.names.update((k, n) for k, n in listed if n)   # so a track's line can name it before JRiver does
        keys = [k for k, _ in listed]
        if key in keys:
            i = keys.index(key)
            return keys[i + 1] if i + 1 < len(keys) else None
        return None

    def _prefetch(self, now):
        """Opens the next track ahead of the end, to carry straight on into it, when its rate matches."""
        t, p = self.track, self.player
        frames = t["fmt"].frames
        if p.next is not None or t["next"] == t["key"] or frames is None:
            return
        if (frames - p.pos) / p.rate > PREFETCH:
            return
        t["next"] = t["key"]   # asked once a track
        key = self._next_key()
        t["next_key"] = key     # kept past the end: JRiver may still name this track when the Sonos is on the next
        if not key or self.leaving:   # leaving: this track is the last the Speakers play
            return
        fmt = self.source.format(key)
        if (fmt.rate, fmt.channels) != (p.rate, p.channels):
            self.say(f"Next, {self.name(key)} at {self._format(fmt)}: a new rate, so the Speakers start it afresh.")
            return
        p.next = self.source.open(key, fmt, 0)

    def _carried_on(self, now):
        """Picks up a carry-on the player made on the audio thread: the Speakers are on the next track now."""
        p = self.player
        while self._chains < len(p.chains):
            when, old, new, origin = p.chains[self._chains]
            self._chains += 1
            fmt = p.stream.fmt
            self.track = {"key": new, "fmt": fmt, "run_t": when, "c": None, "late": None, "refined": True,
                          "checked": now, "next": None, "from_key": old, "end": origin}

    def _settle_carry(self, run, now):
        """
        The Sonos's counter has shown how it went into the new track. Within CHANGE_MS of the end of the last, the
        sound ran straight on, as the Speakers did. Otherwise the Sonos left a gap, and the Speakers step back to
        match it.
        """
        t, p = self.track, self.player
        c = self.clock.first_origin_after(run.t) if run else self.clock.origin(window=1.0)
        if c is None:
            return
        d = (c + self.start_s - t["end"]) * 1000
        name = self.name(t["key"])
        run_t = run.t if run else now
        if CHANGE_MS[0] <= d <= CHANGE_MS[1]:
            t.update(late=d / 1000, c=c, run_t=run_t, refined=False, checked=now, carried=True)
            self.say(f"{name}: carried straight on, as the {self.leader} did; its counter is {d:.0f} ms behind.")
        else:
            t.update(late=0.0, c=c, run_t=run_t, refined=False, checked=now)
            if p.set_origin(c + self.start_s, self._chains):
                p.place(now)
            self.say(f"{name}: the {self.leader} left a gap of {d:.0f} ms, so the Speakers stepped back to match.")

    # --- in step ------------------------------------------------------------------------------
    def _jumped(self, run, now):
        """A jump within the track (or a resume): place again on the new run, with the counter Resume late."""
        c = self.clock.first_origin_after(run.t)
        if c is None:
            return
        t, p = self.track, self.player
        t.update(run_t=run.t, c=c, late=self.resume_s, refined=False, checked=now)
        if p.set_origin(c + self.start_s - t["late"], self._chains):
            p.place(now)
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
        if not t["refined"]:
            if now - t["run_t"] < REFINE_AFTER:
                self._housekeeping(now)
                return
            c = self.clock.origin(window=REFINE_AFTER, since=t["run_t"])
            if c is not None:
                t.update(refined=True, checked=now)
                if t.get("carried"):   # the sound ran on from the last track: the refined clock refines late
                    t["late"] = c + self.start_s - p.origin
                else:
                    self.say(f"Clock refined by {(c - t['c']) * 1000:+.1f} ms.")
                    p.set_origin(c + self.start_s - t["late"], self._chains)
                t["c"] = c
            self._housekeeping(now)
            return
        if now - t["checked"] >= CORRECT_EVERY:
            t["checked"] = now
            c = self.clock.origin(window=2.0, since=t["run_t"])
            if c is not None:
                p.set_origin(c + self.start_s - t["late"], self._chains)
            ms = p.correct(now)
            if ms is not None and abs(ms) > JUMP_OVER_MS:
                self.say(f"The Speakers were {ms:+.0f} ms out; moved them.")
        self._housekeeping(now)

    def _housekeeping(self, now):
        """In step or not: the next track, a dry buffer, the end."""
        p = self.player
        self._prefetch(now)
        dry = p.stream.short_reads
        if dry > self._dry:   # one line a stall: a stall is over after a second with no dry block
            if self._dry_at is None or now - self._dry_at > 1.0:
                self.say("The music isn't arriving fast enough: the Speakers are quiet until it does, still in step.")
            self._dry_at = now
        self._dry = dry
        if p.next is None and p.stream.done and p.lead == 0 and self.out is not None:
            self.finish()

    # --- the clock lost ----------------------------------------------------------------------
    def _clock_lost(self, now):
        """No reads for five seconds: carry on on the DAC's own clock. A minute: stop. True while lost."""
        age = self.clock.last_read_age
        if age is not None and age > LOST_AFTER:
            if age > GIVE_UP:
                self._lost = False
                self.finish(f"Nothing from the {self.leader} for a minute, so the Speakers have stopped.")
                return True
            if not self._lost:
                self._lost = True
                self.say(f"Lost the {self.leader}'s clock: the Speakers carry on on their own for now.")
            self._carried_on(now)
            if self.player is not None:
                self._housekeeping(now)
            return True
        if self._lost:
            self._lost = False
            self.track["checked"] = now
            self.say(f"The {self.leader}'s clock is back.")
        return False

    # --- stopping ------------------------------------------------------------------------------------
    def _sonos_stopped(self, now):
        """
        The Sonos isn't playing. After a second, the Speakers stop if it was stopped. If it was paused, by JRiver or
        at the speaker, the Speakers stop and so does the leader zone in JRiver, which forgets its place in the
        track: play then starts the track from the top in both rooms, the case that's in step (Ben, 9 Nov 2026,
        after a resume came back half a second out). Buffering or idle while JRiver still plays (between tracks, or
        a slow network): they carry on for five seconds, then stop.
        """
        if self._stopped_since is None:
            self._stopped_since = now
        held = now - self._stopped_since
        if held < STOPPED_FOR:
            return
        if self.info_at < self._stopped_since + STOPPED_FOR:
            self._ask(now)   # JRiver's word from after the Sonos stopped, not from before
        state = self.info["state"]
        r = self.clock.latest()
        if state == mcws.STOPPED:
            self.finish(f"The {self.leader} stopped, so the Speakers have too.")
        elif state == mcws.PAUSED or (r is not None and r.state == PAUSED):
            self._paused = self.track["key"]
            self.finish()
            try:
                self.jriver.stop(self.leader)
            except Exception as e:
                self.say(f"Couldn't stop the {self.leader} zone in JRiver ({e}).")
            self.say(f"The {self.leader} paused, so both rooms have stopped; play starts the track from the top.")
        elif held >= WAIT_FOR:
            self.finish(f"The {self.leader} stopped playing, so the Speakers have too.")

    def leave_at_track_end(self):
        """
        Output moved away from Multiroom (Ben, 9 Nov 2026): the Speakers finish the track they're on, then stop
        following, as a new playlist never cuts the track that's playing. A next track already opened is let go,
        so the player can't carry on into it. Nothing playing: they stop following at once.
        """
        self.leaving = True
        p = self.player
        if p is None:
            self._left = True
            self.say("The Speakers have stopped following.")
            return
        with p.lock:
            nxt, p.next = p.next, None
        if nxt is not None:
            nxt.close()
        self.say("The Speakers finish this track, then stop following.")

    def rejoin(self):
        """Stops the Speakers and joins the leader again at once, mid-track (a calibration's change of DAC rate)."""
        self.finish()
        self.last = None

    def nudge(self, ms):
        """Moves Start by ms while music plays (Settings > Other > Multiroom, Nudge): the Speakers shift as you listen."""
        self.start_s += ms / 1000
        t, p = self.track, self.player
        if p is not None and t is not None and t.get("late") is not None and t.get("c") is not None:
            if p.set_origin(t["c"] + self.start_s - t["late"], self._chains):
                p.place(self.now())
        self.say(f"Start is now {self.start_s * 1000:.0f} ms.")

    def finish(self, why=None, end=None):
        """Stops the Speakers. end: our time the track's sound ends on the Sonos, if it ran (or is running) out."""
        p = self.player
        if self.out is not None:
            self.out.close()
        if p is not None:
            if end is None and p.next is None and p.stream.done:
                end = self._end()
            p.stream.close()
            if p.next is not None:
                p.next.close()
            self.last = {"key": self.track["key"], "run_t": self.track["run_t"], "at": self.now(), "end": end,
                         "next": self.track.get("next_key")}
        self.out = self.player = None
        self._stopped_since = None
        if self.leaving:
            self._left = True
        if why:
            self.say(why)

    def run(self, stop=None, every=0.02):
        """The loop, until stop is set or the Speakers have left (leave_at_track_end)."""
        stop = stop or threading.Event()
        self.begin()
        try:
            while not stop.is_set() and not self._left:
                self.step()
                stop.wait(every)
        finally:
            self.finish()


# --- setting up, and the command line ---------------------------------------------------------

class SetupError(Exception):
    """Something the follower needs isn't there. str() is the line for the console."""


def build(leader="Sonos", follower="Speakers", server="Multiroom", sonos_name=None, device=None, start=90.0,
          resume=95.0, dac=1660, env=".env", say=print, source=None):
    """
    Finds the Sonos, the DLNA server and the DAC, and returns (clock, follower, description): the clock not yet
    started, the description one line saying what follows what. Raises SetupError with the line to show when
    something isn't there. Used by the command line here and by multiroom.service inside 24bit7. source: a
    stand-in for the DLNA server's tracks (a calibration's clicks), in which case the server isn't looked for.
    """
    jr = mcws.JRiver(env=env)
    found = sonos.find(sonos_name)
    if not found:
        raise SetupError("No Sonos found on the network." if not sonos_name else f"No Sonos called {sonos_name}.")
    if len(found) > 1 and not sonos_name:
        raise SetupError("More than one Sonos answered: say which under Settings > Other > Multiroom ("
                         + " / ".join(d["name"] for d in found) + ").")
    s = found[0]
    if source is None:
        base = fetch.find_server(server)
        if not base:
            raise SetupError(f"No DLNA server called {server}: is it on in JRiver's Media Network settings?")
        source = Source(base)
    try:
        hint = device or jr.device(follower)[0]
    except KeyError:
        raise SetupError(f"There's no zone called {follower} in JRiver.")
    dev = output.find_device(hint)
    if dev is None:
        raise SetupError(f"No output device matches {hint!r}.")
    description = (f"Speakers following {leader} ({s['name']}, {output._sd().query_devices(dev)['name']}); "
                   f"Start {start:g} ms, Resume {resume:g} ms, DAC {dac} samples.")
    clock = sonos.SonosClock(s["ip"], s["householdId"], s["groupId"])
    f = Follower(clock, jr, leader, follower, source, output.Output, dev, start, resume, dac, say=say)
    return clock, f, description


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

    try:
        clock, f, description = build(a.leader, a.follower, a.server, a.sonos, a.device, a.start, a.resume, a.dac,
                                      a.env, say=lambda line: print(time.strftime("%H:%M:%S "), line, flush=True))
    except SetupError as e:
        raise SystemExit(str(e))
    print(description, "Ctrl+C to stop.")
    clock.start()
    try:
        f.run()
    except KeyboardInterrupt:
        pass
    finally:
        clock.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()
