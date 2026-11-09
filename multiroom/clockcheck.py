"""
Check Clock (Multiroom, stage two, 9 Nov 2026): can this speaker's clock be read well enough to follow?

Ten seconds of reads while something plays, then a verdict: does it answer, how fast, in milliseconds or whole
seconds, and does its counter move one for one with this PC's clock. Green: a millisecond counter, steady. Amber:
whole seconds, steady, worth trying. Red: nothing usable. What this can't see is whether the counter sits the same
distance from the sound at each start, because software can't hear; that's the recording's job (stage three).
"""

import collections
import time

from . import sonos

Verdict = collections.namedtuple("Verdict", "colour text answers ms_clock rtt_ms slope")

SECONDS = 10.0
FAST_MS = 50.0        # a median round trip under this is quick enough
STEADY = 0.01         # the counter's rate against our clock may differ by this much (one per cent)


def check(reads):
    """The verdict from a list of sonos.Read taken over about ten seconds."""
    answers = len(reads)
    if not reads:
        return Verdict("red", "The speaker didn't answer, so its clock can't be read. Multiroom won't start.",
                       0, False, None, None)
    playing = [r for r in reads if r.pos_ms is not None and r.state in sonos.PLAYING]
    if len(playing) < 5:
        return Verdict("amber", "The speaker answers, but nothing was playing, so the clock couldn't be checked. "
                       "Play something on it and try again.", answers, False, None, None)
    rtts = sorted(r.rtt * 1000 for r in playing)
    rtt_ms = rtts[len(rtts) // 2]
    ms_clock = sum(1 for r in playing if r.pos_ms % 1000) > len(playing) / 2
    slope = _slope([(r.t, r.pos_ms / 1000) for r in playing])
    steady = slope is not None and abs(slope - 1) < STEADY
    if not steady:
        return Verdict("red", f"The speaker's counter doesn't keep time with this PC (it runs at {slope:.3f} of "
                       f"our clock), so the rooms would drift apart. Multiroom won't start.",
                       answers, ms_clock, rtt_ms, slope)
    if ms_clock:
        quick = rtt_ms < FAST_MS
        return Verdict("green", f"Clock: millisecond position, {rtt_ms:.0f} ms round trip, steady. "
                       + ("Good." if quick else "Slow to answer, but usable."), answers, True, rtt_ms, slope)
    return Verdict("amber", f"Clock: whole seconds only, {rtt_ms:.0f} ms round trip, steady. Multiroom can run on it, "
                   "but the rooms may sit a few hundredths of a second apart. Worth trying.", answers, False, rtt_ms, slope)


def _slope(points):
    """Least squares slope of position against time, or None with too little spread."""
    n = len(points)
    mt = sum(t for t, _ in points) / n
    mp = sum(p for _, p in points) / n
    var = sum((t - mt) ** 2 for t, _ in points)
    if var < 1e-6:
        return None
    return sum((t - mt) * (p - mp) for t, p in points) / var


def measure(ip, household, group, seconds=SECONDS, sleep=time.sleep):
    """Reads a Sonos's clock for seconds and returns the verdict. Blocks: call it on a thread."""
    clock = sonos.SonosClock(ip, household, group)
    clock.start()
    try:
        sleep(seconds)
        return check(clock.recent(window=seconds))
    finally:
        clock.stop()
