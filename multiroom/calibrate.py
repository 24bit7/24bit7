"""
Calibration (Multiroom, stage three, 9 Nov 2026): the test sound, the run, and the recording's decode. The solver
that reads the recording is calibrate_fit (stage 3b).

One phone recording of about three minutes gives the three numbers for the kit: Start, Resume and the DAC delay
in samples, and whether two fresh starts agree. Both rooms play clicks the whole way, the Sonos at 1 kHz from a
WAV JRiver plays to the leader zone, the DAC at 3.5 kHz from the follower's child placed on the Sonos's clock
with the numbers as they stand, so the recording measures what's left over. The clicks fall at uneven gaps (seed
247, as the sync tests did), so the pattern lines up with itself only at zero shift.

The run, in track seconds of the click track (TRACK_SECONDS long):
  1. fresh start: JRiver plays the track from the top             clicks measured 5 to 38 s
  2. jump: JRiver jumps the leader zone from 40 s to 90 s           clicks measured 95 to 128 s
  3. stop and start again: the track from the top once more        clicks measured 5 to 38 s
  4. new rate: the DAC reopens at 192 kHz, the Sonos carries on      clicks measured 45 to 80 s
A log beside the WAV says when each passage began on the run's clock, at what DAC rate, with what numbers.
"""

import json
import os
import subprocess
import tempfile
import time
import wave

import numpy as np

SEED = 247
LEAD = 3.0                 # seconds of silence before the first click
TRACK_SECONDS = 140.0      # the click track's length: long enough for a jump to 90 s and forty seconds after
TONES = {"sonos": 1000, "speakers": 3500}
TRACK_RATE = 44100
JUMP_FROM, JUMP_TO = 40.0, 90.0
RESTART_AT = 130.0         # track seconds into the first play when the zone is stopped and played again
RATE_AT = 40.0             # track seconds into the second play when the DAC reopens at the high rate
HIGH_RATE = 192000
END_AT = 85.0              # track seconds into the second play when the run ends
PASSAGES = [               # name, which play of the track, the window of track seconds the solver reads
    ("start", 1, (5.0, 38.0)),
    ("jump", 1, (95.0, 128.0)),
    ("restart", 2, (5.0, 38.0)),
    ("rate", 2, (45.0, 80.0)),
]
TRACK_NAME = "24bit7 calibration.wav"
LOG_NAME = "24bit7 calibration.json"


def click_times(length=TRACK_SECONDS, lead=LEAD, seed=SEED):
    """The clicks' times in seconds, at uneven gaps of 1.2 to 2.8 s."""
    rng = np.random.default_rng(seed)
    times, t = [], lead
    while t < length - 2:
        times.append(t)
        t += rng.uniform(1.2, 2.8)
    return np.array(times)


def click(rate, hz):
    """Eight milliseconds of a tone with a sharp front, dying away."""
    n = int(0.008 * rate)
    k = np.arange(n) / rate
    return (np.sin(2 * np.pi * hz * k) * np.exp(-k / 0.002) * 0.8).astype(np.float32)


def pattern(rate, hz, length=TRACK_SECONDS):
    """The click track as mono float32 at rate."""
    out = np.zeros(int(length * rate), np.float32)
    c = click(rate, hz)
    for t in click_times(length):
        i = int(round(t * rate))
        out[i:i + len(c)] += c[:max(0, min(len(c), len(out) - i))]
    return out


def write_click_track(path, hz=TONES["sonos"], rate=TRACK_RATE, length=TRACK_SECONDS):
    """The Sonos's track: a 16-bit stereo WAV of the 1 kHz clicks, about 25 MB for 140 s."""
    mono = pattern(rate, hz, length)
    pcm = (np.clip(mono, -1, 1) * 32767).astype("<i2")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(pcm, 2).tobytes())
    return path


class ClickFormat:
    """What fetch.read_format gives, for a click track: rate, channels, bits, float, header, frames."""

    def __init__(self, rate, frames):
        self.rate, self.channels, self.bits, self.is_float, self.header, self.frames = rate, 2, 32, True, 0, frames


class ClickStream:
    """TrackStream's shape over a click pattern held in memory: the follower plays it like any track."""

    def __init__(self, fmt, from_sample, data):
        self.fmt, self.position, self.data = fmt, from_sample, data
        self.short_reads = 0
        self.closed = False
        self.key = None

    def read(self, n):
        out = np.zeros((n, 2), np.float32)
        a, b = self.position, min(self.position + n, len(self.data))
        if b > a:
            out[:b - a, 0] = self.data[a:b]
            out[:b - a, 1] = self.data[a:b]
        self.position += n
        return out, max(0, b - a)

    def seek(self, sample):
        self.position = max(0, sample)

    @property
    def done(self):
        return self.position >= self.fmt.frames

    def wait_buffered(self, frames, timeout=5.0):
        return True

    def close(self):
        self.closed = True


class ClickSource:
    """
    Stands in for follower.Source during a calibration: whatever track the leader zone names, the follower gets
    the 3.5 kHz click pattern at the current DAC rate. set_rate changes it for the next track started.
    """

    def __init__(self, rate=TRACK_RATE, hz=TONES["speakers"], length=TRACK_SECONDS):
        self.rate, self.hz, self.length = rate, hz, length
        self._cache = {}

    def set_rate(self, rate):
        self.rate = rate

    def _data(self, rate):
        if rate not in self._cache:
            self._cache[rate] = pattern(rate, self.hz, self.length)
        return self._cache[rate]

    def format(self, key):
        return ClickFormat(self.rate, int(self.length * self.rate))

    def open(self, key, fmt, from_sample):
        s = ClickStream(fmt, from_sample, self._data(fmt.rate))
        s.key = key
        return s


# --- the run ----------------------------------------------------------------------------------------------

class Run:
    """
    Drives one calibration run: the click track to the leader zone through JRiver, the follower's child placing
    its clicks, the jump, the stop and restart, the DAC's change of rate, and the log. jriver is an mcws.JRiver
    (or a stand-in with play_file, position, stop, play, info, delete_file); link has calibrate(settings, rate)
    and calibrate_rate(rate); now is the clock; sleep waits (the tests pass a stand-in); say gets one line a step.
    """

    def __init__(self, jriver, link, leader, settings, folder, now=time.perf_counter, sleep=time.sleep, say=print):
        self.jriver, self.link, self.leader, self.settings = jriver, link, leader, dict(settings)
        self.folder, self.now, self.sleep, self.say = folder, now, sleep, say
        self.track = os.path.join(folder, TRACK_NAME)
        self.log_path = os.path.join(folder, LOG_NAME)
        self.log = {"began": None, "numbers": {k: settings.get(k) for k in ("start", "resume", "dac")},
                    "passages": [], "track_seconds": TRACK_SECONDS, "jump": [JUMP_FROM, JUMP_TO],
                    "high_rate": HIGH_RATE}
        self.key = None

    def _mark(self, name, play, window, rate):
        self.log["passages"].append({"name": name, "play": play, "window": list(window), "rate": rate,
                                     "run_t": self.now() - self.t0})

    def _until(self, run_t):
        wait = self.t0 + run_t - self.now()
        if wait > 0:
            self.sleep(wait)

    def go(self):
        """The whole run. Returns the log's path. Raises on a JRiver problem, after stopping what it started."""
        if not os.path.isfile(self.track):
            self.say("Making the click track...")
            write_click_track(self.track)
        self.log["began"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            # 1. a fresh start: JRiver plays the click track from the top; the child places its clicks on the clock
            self.say("Playing the test sound in both rooms. Leave the recording running until it stops.")
            self.jriver.play_file(self.leader, self.track)
            self.t0 = self.now()
            self.key = self.jriver.info(self.leader).get("key")
            self.link.calibrate(self.settings, TRACK_RATE)
            self._mark("start", 1, PASSAGES[0][2], TRACK_RATE)
            # 2. a jump within the track
            self._until(JUMP_FROM)
            self.jriver.position(self.leader, int(JUMP_TO * 1000))
            self._mark("jump", 1, PASSAGES[1][2], TRACK_RATE)
            self.say("Jumped.")
            # 3. stop, then the track from the top again
            self._until(JUMP_FROM + (RESTART_AT - JUMP_TO))
            self.jriver.stop(self.leader)
            self.sleep(2.0)
            self.jriver.play(self.leader)
            restart_t = self.now() - self.t0
            self._mark("restart", 2, PASSAGES[2][2], TRACK_RATE)
            self.say("Started again from the top.")
            # 4. the DAC at the high rate, the Sonos carrying on
            self._until(restart_t + RATE_AT)
            self.link.calibrate_rate(HIGH_RATE)
            self._mark("rate", 2, PASSAGES[3][2], HIGH_RATE)
            self.say(f"The DAC is at {HIGH_RATE // 1000} kHz now.")
            self._until(restart_t + END_AT)
        finally:
            try:
                self.jriver.stop(self.leader)
            except Exception:
                pass
            try:
                self.link.stop()
            except Exception:
                pass
            if self.key:
                try:
                    self.jriver.delete_file(self.key)   # out of the library again; the file stays on disk
                except Exception:
                    pass
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.log, f, indent=2)
        self.say("Done: stop the recording, get it onto this PC, then Load Recording...")
        return self.log_path


# --- the recording -----------------------------------------------------------------------------------------

DECODE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "decode_media.ps1")


def is_plain_wav(path):
    """A PCM WAV the solver can read straight off."""
    try:
        with wave.open(path, "rb") as w:
            return w.getsampwidth() in (1, 2, 3, 4) and w.getcomptype() == "NONE"
    except (wave.Error, OSError, EOFError):
        return False


def decode(path, out_dir=None, run=subprocess.run):
    """
    The recording as a 16-bit mono 44.1 kHz WAV the solver reads: a plain WAV as it is, anything else (a phone's
    m4a, mp3, FLAC, a 24-bit WAV) through Windows Media Foundation with decode_media.ps1, no ffmpeg. Returns the
    WAV's path; raises RuntimeError with the reason when Windows can't decode it.
    """
    if is_plain_wav(path):
        return path
    out_dir = out_dir or tempfile.gettempdir()
    out_name = os.path.splitext(os.path.basename(path))[0] + ".decoded.wav"
    # -Plain: Media Foundation's own WAV profile. Asking it for 44.1 kHz mono fails with "Unknown" (9 Nov 2026),
    # so the rate and channels are whatever the recording had, and read_wav takes it from there.
    r = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", DECODE_SCRIPT,
             "-In", os.path.abspath(path), "-OutDir", out_dir, "-OutName", out_name, "-Plain"],
            capture_output=True, text=True, timeout=300)
    out = os.path.join(out_dir, out_name)
    if r.returncode != 0 or not os.path.isfile(out):
        reason = (r.stdout or "").strip().splitlines()[-1:] or [(r.stderr or "").strip()[:200]]
        raise RuntimeError(f"Windows couldn't decode {os.path.basename(path)} ({reason[0] or 'no reason given'}).")
    return out


def read_wav(path):
    """A PCM WAV as (mono float array, rate): 8, 16, 24 or 32-bit, any number of channels averaged."""
    with wave.open(path, "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        x = ((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) ^ 0x800000) - 0x800000
        x = x.astype(np.float64) / 8388608
    elif width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128
    else:
        raise ValueError(f"A {width * 8}-bit WAV can't be read.")
    return x.reshape(-1, ch).mean(axis=1), rate
