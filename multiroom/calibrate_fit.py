"""
The calibration solver (Multiroom, stage 3b, 9 Nov 2026): a recording of a run plus its log give Start, Resume and
the DAC delay, and whether two fresh starts repeat.

Each room's clicks are found in its own pitch band (the Sonos at 1 kHz, the DAC at 3.5 kHz), as a loudness
envelope in one-millisecond steps. Play 1's start is found by correlating the Sonos's onset rises with the click
train; each later passage is found the same way within a few seconds of where the log says it should be, since a
jump or a restart lands a moment after the command. A click counts when both rooms are well above the background
near where it's due; the Speakers' click is the loudest burst in its band there (a click's sharp front leaks into
the other band, so a first crossing misreads by about 7 ms). Per passage: the median gap Speakers minus Sonos
and its scatter. Then, with g1 to g4 the gaps of the four passages in ms, D the DAC delay used and S, R the numbers
used:
  the DAC delay's error, samples   dD = (g1 - g4) / (1000 / 44100 - 1000 / 192000)
  Start                            S - (g1 - dD * 1000 / 44100)
  Resume                           R + (g2 - g1)
  repeat                           |g3 - g1|
A gap includes where the phone sat between the rooms (about three milliseconds a metre), which is why the recording
is made where you listen: the numbers line the rooms up there.
"""

import json

import numpy as np

from . import calibrate

BAND_WIDTH = 0.25        # each room's band: a quarter either side of its pitch
LEVEL_OVER = 3.0         # a click counts when its burst is this many times the band's background
ENOUGH = 0.5             # and a passage counts when this share of its clicks are found
SCATTER_MS = 5.0         # a passage whose gaps spread more than this (one standard deviation) is refused
SEARCH_S = 4.0           # how far either side of the log's time a passage's clicks are looked for
MS_PER_SAMPLE = 1000 / 44100 - 1000 / calibrate.HIGH_RATE   # a sample of DAC delay, between the two rates, in ms


class Result:
    def __init__(self):
        self.passages = {}     # name: {"gap", "scatter", "found", "expected", "levels"}
        self.problems = []     # (key, values) for the app to word; empty when the numbers can be trusted
        self.start = self.resume = self.dac = self.repeat = None

    @property
    def ok(self):
        return not self.problems and self.start is not None


# --- the recording's two rooms --------------------------------------------------------------------------

def band(x, rate, hz, width=BAND_WIDTH):
    f = np.fft.rfftfreq(len(x), 1 / rate)
    spec = np.fft.rfft(x)
    spec[(f < hz * (1 - width)) | (f > hz * (1 + width))] = 0
    return np.fft.irfft(spec, len(x))


def envelope_ms(b, rate):
    """The band's loudness in one-millisecond steps, whatever the recording's rate."""
    hop = max(1, rate // 1000)
    e = np.sqrt(np.convolve(b * b, np.ones(hop) / hop, "same"))
    idx = (np.arange(int(len(b) * 1000 / rate)) * rate / 1000).astype(int)
    return e[np.minimum(idx, len(e) - 1)]


def rises(e):
    r = np.maximum(np.diff(e, prepend=e[0]), 0)
    top = np.percentile(r, 99.9) or 1.0
    return np.minimum(r, top) / top


def find_pattern(rise, clicks_ms, lo_ms=0, hi_ms=None, earliest=False):
    """
    Where a train of clicks (ms, from zero) best lines up with the onset rises, searched between lo and hi.
    earliest: the first alignment nearly as good as the best, for a pattern the recording holds twice (the track
    is played twice in a run, and the second play can score higher when the first began a few clicks late).
    """
    train = np.zeros(int(clicks_ms[-1] - clicks_ms[0]) + 1)
    train[(clicks_ms - clicks_ms[0]).astype(int)] = 1
    hi_ms = len(rise) if hi_ms is None else min(hi_ms, len(rise))
    lo_ms = max(0, lo_ms)
    seg = rise[lo_ms:hi_ms]
    if len(seg) <= len(train):
        return None
    score = np.correlate(seg, train, "valid")
    best = float(score.max())
    if best <= 0:
        return None
    if earliest:
        strong = np.flatnonzero(score >= 0.6 * best)
        k = int(strong[0])
        # the peak of that first strong stretch, not its foot
        end = strong[strong < k + 2000].max() + 1
        k = k + int(score[k:end].argmax())
    else:
        k = int(score.argmax())
    return lo_ms + k - int(clicks_ms[0])   # the recording ms where the track's zero would be


def onset_near(e, due_ms, before=350, after=600, frac=0.3):
    """The onset of the loudest burst within before and after of due_ms: (ms, level)."""
    a, b = max(0, int(due_ms - before)), min(len(e), int(due_ms + after))
    if b <= a + 1:
        return None, 0.0
    seg = e[a:b]
    k = int(np.argmax(seg))
    peak = float(seg[k])
    j = k
    while j > 0 and seg[j] > peak * frac:
        j -= 1
    return a + j, peak


# --- the solver ------------------------------------------------------------------------------------------

def solve(wav_path, log_path):
    """The Result for a recording and its run's log."""
    x, rate = calibrate.read_wav(wav_path)
    with open(log_path, encoding="utf-8") as f:
        log = json.load(f)
    return solve_signal(x, rate, log)


def solve_signal(x, rate, log):
    res = Result()
    envs = {room: envelope_ms(band(x, rate, hz), rate) for room, hz in calibrate.TONES.items()}
    bg = {room: max(float(np.percentile(e, 50)), 1e-9) for room, e in envs.items()}
    sonos_rise = rises(envs["sonos"])
    ct = calibrate.click_times(log.get("track_seconds", calibrate.TRACK_SECONDS))
    jump_from, jump_to = log.get("jump", [calibrate.JUMP_FROM, calibrate.JUMP_TO])
    passages = {p["name"]: p for p in log["passages"]}
    if "start" not in passages:
        res.problems.append(("no_log", {}))
        return res

    # play 1's zero: the clicks before the jump, anywhere in the recording
    first = ct[(ct >= calibrate.LEAD) & (ct < jump_from)] * 1000
    zero1 = find_pattern(sonos_rise, first, earliest=True)
    if zero1 is None:
        res.problems.append(("no_pattern", {}))
        return res
    run0 = zero1 - passages["start"]["run_t"] * 1000   # the run's clock, in recording ms

    for name, p in passages.items():
        lo, hi = p["window"]
        window = ct[(ct >= lo) & (ct <= hi)]
        if name == "start":
            zero = zero1
        else:
            # where this passage's track zero would be, from the log, then the pattern found around it
            if name == "jump":
                guess = run0 + p["run_t"] * 1000 - jump_to * 1000
            else:
                guess = run0 + passages["restart"]["run_t"] * 1000
            zero = find_pattern(sonos_rise, window * 1000, int(guess + lo * 1000 - SEARCH_S * 1000),
                                int(guess + hi * 1000 + SEARCH_S * 1000))
            if zero is None:
                res.problems.append(("passage_lost", {"passage": name}))
                continue
        gaps, levels = [], []
        for c in window:
            due = zero + c * 1000
            so, ls = onset_near(envs["sonos"], due)
            sp, lp = onset_near(envs["speakers"], due)
            if so is None or sp is None:
                continue
            if ls < LEVEL_OVER * bg["sonos"] or lp < LEVEL_OVER * bg["speakers"]:
                continue
            gaps.append(sp - so)
            levels.append((ls / bg["sonos"], lp / bg["speakers"]))
        gaps = np.array(gaps, dtype=float)
        entry = {"expected": int(len(window)), "found": int(len(gaps)), "levels": levels, "zero_ms": zero}
        if len(gaps) < ENOUGH * len(window) or len(gaps) < 3:
            entry.update(gap=None, scatter=None)
            res.passages[name] = entry
            res.problems.append(("too_few", {"passage": name, "found": len(gaps), "expected": len(window)}))
            continue
        # the gap: the median, and its scatter over the clicks within 30 ms of it (the rest are misreads)
        med = float(np.median(gaps))
        near = gaps[np.abs(gaps - med) <= 30]
        gap, scatter = float(np.median(near)), float(np.std(near)) if len(near) > 1 else 0.0
        entry.update(gap=gap, scatter=scatter, found=int(len(near)))
        res.passages[name] = entry
        if scatter > SCATTER_MS:
            res.problems.append(("scattered", {"passage": name, "scatter": round(scatter, 1)}))
        if len(near) < ENOUGH * len(window):
            res.problems.append(("too_few", {"passage": name, "found": len(near), "expected": len(window)}))

    g = {name: e.get("gap") for name, e in res.passages.items()}
    used = log.get("numbers", {})
    if all(g.get(k) is not None for k in ("start", "jump", "restart", "rate")):
        d_samples = (g["start"] - g["rate"]) / MS_PER_SAMPLE
        res.dac = int(round(float(used.get("dac", 0)) + d_samples))
        res.start = round(float(used.get("start", 0)) - (g["start"] - d_samples * 1000 / 44100), 1)
        res.resume = round(float(used.get("resume", 0)) + (g["jump"] - g["start"]), 1)
        res.repeat = round(abs(g["restart"] - g["start"]), 1)
        if res.dac < 0:
            res.problems.append(("dac_negative", {"dac": res.dac}))
    return res
