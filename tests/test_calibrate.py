"""
Calibration, stage 3a (9 Nov 2026): the click track, the follower placing clicks from a ClickSource on the Sonos's
clock, the run's order and log, and the recording's decode. Windowless; no hardware, no network.
"""

import json
import os
import sys
import wave

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import calibrate
finally:
    sys.path.remove(REPO)

from test_follower import World, START, TOL, DAC  # noqa: E402


# --- the click track -------------------------------------------------------------------------------------

def test_the_clicks_fall_at_uneven_gaps_and_the_same_every_time():
    t = calibrate.click_times()
    assert t[0] == calibrate.LEAD and t[-1] < calibrate.TRACK_SECONDS - 2
    gaps = np.diff(t)
    assert gaps.min() >= 1.2 and gaps.max() <= 2.8 and len(set(np.round(gaps, 3))) > 10, "uneven, so the pattern can't line up with itself"
    assert np.array_equal(t, calibrate.click_times())


def test_the_sonos_track_is_a_plain_wav_with_the_clicks_where_the_times_say(tmp_path):
    path = calibrate.write_click_track(str(tmp_path / "clicks.wav"), length=20.0)
    with wave.open(path, "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (44100, 2, 2, 20 * 44100)
    x, rate = calibrate.read_wav(path)
    for t in calibrate.click_times(20.0):
        i = int(round(t * rate))
        assert np.abs(x[i:i + 50]).max() > 0.3 and np.abs(x[i - 400:i - 10]).max() < 0.01, f"no click at {t}"
    assert calibrate.is_plain_wav(path)


# --- the follower on clicks ----------------------------------------------------------------------------

def click_onsets(out, rate):
    """
    Our times at which each click's first sample was handed to the fake DAC, from its blocks. The follower hands
    samples DAC frames early so a real DAC's delay lands them on time, and the fake has no delay of its own, so a
    click due at O + c is handed at O + c - DAC / rate.
    """
    onsets, last = [], -1.0
    for (_, block), t in zip(out.blocks, out.slots):
        hot = np.flatnonzero(np.abs(block[:, 0]) > 0.05)
        for i in hot:
            when = t + i / rate
            if when - last > 0.5:
                onsets.append(when)
            last = when
    return np.array(onsets)


def test_the_follower_places_the_clicks_on_the_sonos_clock():
    src = calibrate.ClickSource(44100, length=30.0)
    w = World(source=src)
    w.run(0.5)
    c0 = w.play(key=1)
    w.run(12.0)
    o = c0 + START
    got = click_onsets(w.outs[-1], 44100)
    want = o + calibrate.click_times(30.0) - DAC / 44100
    want = want[(want > w.sim.t - 9) & (want < w.sim.t - 0.1)]
    assert len(want) >= 4
    for t in want:
        assert np.abs(got - t).min() * 1000 < TOL, f"click due at {t:.3f} landed {np.abs(got - t).min() * 1000:.2f} ms off"


def test_a_change_of_dac_rate_rejoins_mid_track_at_the_new_rate():
    src = calibrate.ClickSource(44100, length=60.0)
    w = World(source=src)
    w.run(0.5)
    c0 = w.play(key=1)
    w.run(10.0)
    src.set_rate(192000)
    w.f.rejoin()
    w.run(8.0)
    assert len(w.outs) == 2 and w.outs[1].rate == 192000
    o = c0 + START
    got = click_onsets(w.outs[1], 192000)
    want = o + calibrate.click_times(60.0) - DAC / 192000
    want = want[(want > w.outs[1].t0 + 1.0) & (want < w.sim.t - 0.1)]
    assert len(want) >= 3
    for t in want:
        assert np.abs(got - t).min() * 1000 < TOL, f"click due at {t:.3f} landed {np.abs(got - t).min() * 1000:.2f} ms off"


# --- the run ----------------------------------------------------------------------------------------------

class SimClock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class StubJRiver:
    def __init__(self):
        self.calls = []

    def play_file(self, zone, path):
        self.calls.append(("play_file", zone, os.path.basename(path)))

    def info(self, zone):
        return {"key": 77, "state": 2}

    def position(self, zone, ms):
        self.calls.append(("position", zone, ms))

    def stop(self, zone):
        self.calls.append(("stop", zone))

    def play(self, zone):
        self.calls.append(("play", zone))

    def delete_file(self, key):
        self.calls.append(("delete_file", key))


class StubLink:
    def __init__(self):
        self.calls = []

    def calibrate(self, settings, rate):
        self.calls.append(("calibrate", rate, settings["start"]))

    def calibrate_rate(self, rate):
        self.calls.append(("calibrate_rate", rate))

    def stop(self):
        self.calls.append(("stop",))


def test_the_run_drives_jriver_and_the_child_in_order_and_logs_the_passages(tmp_path, monkeypatch):
    monkeypatch.setattr(calibrate, "TRACK_SECONDS", 140.0)
    clock, jr, lk, lines = SimClock(), StubJRiver(), StubLink(), []
    settings = {"leader": "Sonos", "follower": "Speakers", "start": 90.0, "resume": 95.0, "dac": 1660}
    run = calibrate.Run(jr, lk, "Sonos", settings, str(tmp_path), now=clock.now, sleep=clock.sleep, say=lines.append)
    log_path = run.go()
    assert jr.calls == [("play_file", "Sonos", calibrate.TRACK_NAME), ("position", "Sonos", 90000),
                        ("stop", "Sonos"), ("play", "Sonos"), ("stop", "Sonos"), ("delete_file", 77)]
    assert lk.calls == [("calibrate", 44100, 90.0), ("calibrate_rate", 192000), ("stop",)]
    log = json.load(open(log_path, encoding="utf-8"))
    names = [p["name"] for p in log["passages"]]
    assert names == ["start", "jump", "restart", "rate"]
    # the jump at 40 s lands on track 90 s, so track 130 s comes at run 80 s; two seconds stopped; the rate 40 s on
    run_t = [round(p["run_t"]) for p in log["passages"]]
    assert run_t == [0, 40, 82, 122], run_t
    assert [p["rate"] for p in log["passages"]] == [44100, 44100, 44100, 192000]
    assert [p["play"] for p in log["passages"]] == [1, 1, 2, 2]
    assert log["numbers"] == {"start": 90.0, "resume": 95.0, "dac": 1660}
    assert os.path.isfile(tmp_path / calibrate.TRACK_NAME), "the click track stays for the next run"
    assert lines[-1].startswith("Done: stop the recording")


def test_a_jriver_problem_mid_run_still_stops_and_tidies_up(tmp_path):
    clock, jr, lk = SimClock(), StubJRiver(), StubLink()
    jr.position = lambda zone, ms: (_ for _ in ()).throw(RuntimeError("JRiver went away"))
    run = calibrate.Run(jr, lk, "Sonos", {"start": 90, "resume": 95, "dac": 1660}, str(tmp_path),
                        now=clock.now, sleep=clock.sleep, say=lambda s: None)
    with pytest.raises(RuntimeError):
        run.go()
    assert ("stop", "Sonos") in jr.calls and ("delete_file", 77) in jr.calls and ("stop",) in lk.calls


# --- the recording ---------------------------------------------------------------------------------------

def test_a_plain_wav_is_used_as_it_is_and_anything_else_goes_through_windows(tmp_path):
    wav = calibrate.write_click_track(str(tmp_path / "rec.wav"), length=5.0)
    assert calibrate.decode(wav) == wav
    m4a = tmp_path / "rec.m4a"
    m4a.write_bytes(b"not really audio")
    ran = []

    def fake_run(args, **kw):
        ran.append(args)
        out = os.path.join(args[args.index("-OutDir") + 1], args[args.index("-OutName") + 1])
        calibrate.write_click_track(out, length=1.0)
        return type("R", (), {"returncode": 0, "stdout": "wrote", "stderr": ""})()
    out = calibrate.decode(str(m4a), out_dir=str(tmp_path), run=fake_run)
    assert out.endswith("rec.decoded.wav") and os.path.isfile(out)
    assert ran[0][:5] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    assert ran[0][5].endswith("decode_media.ps1") and os.path.isfile(ran[0][5]), "the decode script ships in the package"


def test_a_recording_windows_cant_decode_is_refused_with_the_reason(tmp_path):
    bad = tmp_path / "rec.m4a"
    bad.write_bytes(b"x")

    def fake_run(args, **kw):
        return type("R", (), {"returncode": 1, "stdout": "source: audio/mp4\ncannot transcode: Unknown", "stderr": ""})()
    with pytest.raises(RuntimeError, match="couldn't decode rec.m4a .*cannot transcode: Unknown"):
        calibrate.decode(str(bad), out_dir=str(tmp_path), run=fake_run)
