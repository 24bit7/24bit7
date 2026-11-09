"""
The calibration solver (stage 3b, 9 Nov 2026) on made-up recordings with known offsets, and on tonight's real one
when it's on this PC. Windowless.
"""

import json
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import calibrate, calibrate_fit
finally:
    sys.path.remove(REPO)

SYNC = r"C:\Users\bmwil\Documents\24bit7 sync test"
RATE = 48000   # a phone records at 48 kHz


def make_log(start=90.0, resume=95.0, dac=1660, jump_lag=0.8, restart_lag=0.6):
    """A run's log as calibrate.Run writes it, with the passages at their run times."""
    return {"began": "2026-11-09 23:19:16", "numbers": {"start": start, "resume": resume, "dac": dac},
            "track_seconds": calibrate.TRACK_SECONDS, "jump": [calibrate.JUMP_FROM, calibrate.JUMP_TO],
            "high_rate": calibrate.HIGH_RATE,
            "passages": [{"name": "start", "play": 1, "window": [5.0, 38.0], "rate": 44100, "run_t": 0.0},
                         {"name": "jump", "play": 1, "window": [95.0, 128.0], "rate": 44100, "run_t": 40.0},
                         {"name": "restart", "play": 2, "window": [5.0, 38.0], "rate": 44100, "run_t": 82.0},
                         {"name": "rate", "play": 2, "window": [45.0, 80.0], "rate": 192000, "run_t": 122.0}],
            "_lags": {"jump": jump_lag, "restart": restart_lag}}


def sonos_click_times(log, rec_zero=19.5):
    """When each Sonos click sounds in the recording, in seconds, and which passage it belongs to."""
    ct = calibrate.click_times()
    lags = log["_lags"]
    out = []
    jump_at = 40.0 + lags["jump"]                 # run seconds when the Sonos actually jumps
    restart_at = 82.0 + lags["restart"]           # run seconds when play 2 actually begins
    for c in ct:                                  # play 1 before the jump
        if c < jump_at:
            out.append((rec_zero + c, "start" if 5 <= c <= 38 else None))
    for c in ct:                                  # play 1 after the jump: track 90 onwards
        if c >= calibrate.JUMP_TO:
            t = rec_zero + jump_at + (c - calibrate.JUMP_TO)
            if t < rec_zero + restart_at - 2.5:
                out.append((t, "jump" if 95 <= c <= 128 else None))
    for c in ct:                                  # play 2 from the top
        t = rec_zero + restart_at + c
        if c <= 85:
            out.append((t, "restart" if 5 <= c <= 38 else ("rate" if 45 <= c <= 80 else None)))
    return out


def synth(gaps, log, rec_zero=19.5, speakers_level=1.0, noise=0.01, seed=5, rate=RATE):
    """A two-room recording: the Sonos's 1 kHz clicks, the Speakers' 3.5 kHz clicks gaps[passage] ms later."""
    rng = np.random.default_rng(seed)
    clicks = sonos_click_times(log, rec_zero)
    length = int((clicks[-1][0] + 5) * rate)
    rec = np.zeros(length)
    c1, c2 = calibrate.click(rate, calibrate.TONES["sonos"]), calibrate.click(rate, calibrate.TONES["speakers"])
    echo = np.exp(-np.arange(int(0.03 * rate)) / (0.006 * rate)) * 0.15
    for t, passage in clicks:
        i = int(round(t * rate))
        rec[i:i + len(c1)] += 0.5 * c1
        g = gaps.get(passage, gaps.get(None, 0.0)) if passage else gaps.get(None, 0.0)
        j = int(round((t + g / 1000) * rate))
        rec[j:j + len(c2)] += speakers_level * c2
    rec = rec + np.convolve(rec, echo, "full")[:length]
    rec += rng.normal(0, noise, length)
    return rec / max(1.0, np.abs(rec).max())


def expected_gaps(true, used, phone_ms=4.0):
    """The gaps the model predicts for true numbers against the numbers used, with the phone's position."""
    d = true["dac"] - used["dac"]
    g1 = (used["start"] - true["start"]) + d * 1000 / 44100 + phone_ms
    return {"start": g1, "jump": g1 - (used["resume"] - true["resume"]), "restart": g1,
            "rate": (used["start"] - true["start"]) + d * 1000 / 192000 + phone_ms, None: g1}


def test_the_solver_gets_the_true_numbers_back_from_a_made_up_recording():
    used = {"start": 90.0, "resume": 95.0, "dac": 1660}
    true = {"start": 93.0, "resume": 99.0, "dac": 1700}
    log = make_log(**used)
    rec = synth(expected_gaps(true, used), log)
    r = calibrate_fit.solve_signal(rec, RATE, log)
    assert r.ok, r.problems
    # Start comes out lower by the phone's 4 ms: with it, the rooms meet where the phone sat, which is the point
    assert r.start == pytest.approx(true["start"] - 4.0, abs=1.0), "Start, less the phone's 4 ms"
    assert r.resume == pytest.approx(true["resume"], abs=1.0), "Resume is a difference between passages: the phone cancels"
    assert r.dac == pytest.approx(true["dac"], abs=80)
    assert r.repeat < 1.0
    for name in ("start", "jump", "restart", "rate"):
        assert r.passages[name]["found"] >= 0.8 * r.passages[name]["expected"], (name, r.passages[name])
        assert r.passages[name]["scatter"] < 1.0


def test_a_wobble_between_the_two_starts_is_reported_as_the_repeat():
    used = {"start": 90.0, "resume": 95.0, "dac": 1660}
    gaps = expected_gaps(used, used)
    gaps["restart"] = gaps["start"] + 60.0   # the second fresh start landed 60 ms off the first
    log = make_log(**used)
    r = calibrate_fit.solve_signal(synth(gaps, log), RATE, log)
    assert r.repeat == pytest.approx(60.0, abs=1.5)
    assert r.start == pytest.approx(90.0 - 4.0, abs=1.0), "the first start alone sets Start"


def test_a_room_too_faint_is_refused_with_the_reason():
    used = {"start": 90.0, "resume": 95.0, "dac": 1660}
    log = make_log(**used)
    r = calibrate_fit.solve_signal(synth(expected_gaps(used, used), log, speakers_level=0.002, noise=0.02), RATE, log)
    assert not r.ok and any(key == "too_few" for key, _ in r.problems), r.problems


def test_nothing_like_the_pattern_is_refused():
    log = make_log()
    rng = np.random.default_rng(1)
    r = calibrate_fit.solve_signal(rng.normal(0, 0.05, RATE * 60), RATE, log)
    assert not r.ok and r.problems


REAL = os.path.join(SYNC, "calibration_run1_2318.m4a")
REAL_LOG = os.path.join(SYNC, "calibration_run1_2318.json")


@pytest.mark.skipif(not (os.path.isfile(REAL) and os.path.isfile(REAL_LOG)), reason="Ben's recording isn't on this PC")
def test_bens_recording_of_9_nov_gives_his_numbers_back(tmp_path):
    # the run used 90 / 95 / 1660 and both rooms were heard aligned, so the solver should hand the same numbers
    # back, give or take the phone's place in the room and the scatter of a phone recording
    wav = calibrate.decode(REAL, out_dir=str(tmp_path))
    r = calibrate_fit.solve(wav, REAL_LOG)
    assert r.ok, r.problems
    assert r.start == pytest.approx(90.0, abs=8.0), r.start
    assert r.resume == pytest.approx(95.0, abs=8.0), r.resume
    assert r.dac == pytest.approx(1660, abs=300), r.dac
    assert r.repeat < 8.0, r.repeat
