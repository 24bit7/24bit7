"""
Multiroom, stage two (9 Nov 2026): the speaker and DAC profiles, Check Clock's verdicts, and Nudge. Windowless.
"""

import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import clockcheck, profiles, sonos
finally:
    sys.path.remove(REPO)

from test_follower import World, START, TOL  # noqa: E402


# --- profiles ------------------------------------------------------------------------------------------

def test_the_sonos_one_and_the_hugo_are_known_and_anything_else_is_generic():
    one = profiles.pick_speaker("Sonos", "Sonos One")
    assert (one["name"], one["clock"], one["start"], one["resume"], one["tested"]) == ("Sonos One", "sonos", 90.0, 95.0, True)
    other = profiles.pick_speaker("", "Sonos Play:5")
    assert other["name"] == "Sonos" and other["clock"] == "sonos" and not other["tested"]
    generic = profiles.pick_speaker("Denon", "HEOS 5")
    assert generic["name"] == "Generic" and generic["clock"] == "upnp" and not generic["tested"]
    hugo = profiles.pick_dac("Hugo (Chord Async USB 44.1kHz-384kHz)", "ASIO Chord  1.04")
    assert hugo["name"] == "Chord Hugo TT" and hugo["dac"] == 1660
    assert profiles.pick_dac("Speakers (Xonar SoundCard)", "")["dac"] == 0
    assert profiles.pick_speaker("Sonos", "Sonos One") is not profiles.pick_speaker("Sonos", "Sonos One"), "a copy each time"


def test_the_line_under_the_numbers_says_where_they_came_from():
    one, hugo = profiles.pick_speaker("Sonos", "Sonos One"), profiles.pick_dac("Hugo", "ASIO Chord")
    assert profiles.source_line("profiles", one, hugo) == "From the Sonos One and Chord Hugo TT profiles."
    assert profiles.source_line("typed", one, hugo) == "Typed by hand."
    assert profiles.source_line("recording:9 Nov 2026", one, hugo) == "From your recording of 9 Nov 2026."
    assert profiles.source_line("profiles", profiles.pick_speaker("", ""), hugo).startswith("Generic: not measured yet.")


# --- Check Clock -------------------------------------------------------------------------------------------

def reads(seconds=10.0, every=0.01, rtt=0.004, whole=False, rate=1.0, state="PLAYBACK_STATE_PLAYING"):
    out, t = [], 100.0
    while t < 100.0 + seconds:
        pos = (t - 100.0) * rate * 1000
        pos = int(pos // 1000 * 1000) if whole else int(pos)
        out.append(sonos.Read(t, rtt, pos if state == "PLAYBACK_STATE_PLAYING" else None, state))
        t += every
    return out


def test_a_millisecond_clock_that_keeps_time_is_green():
    v = clockcheck.check(reads())
    assert v.colour == "green" and v.ms_clock and v.rtt_ms == pytest.approx(4.0) and abs(v.slope - 1) < 0.001
    assert v.text == "Clock: millisecond position, 4 ms round trip, steady. Good."


def test_a_whole_second_clock_is_amber_and_worth_trying():
    v = clockcheck.check(reads(whole=True))
    assert v.colour == "amber" and not v.ms_clock and "whole seconds only" in v.text and "Worth trying" in v.text


def test_a_clock_that_runs_at_the_wrong_rate_is_red():
    v = clockcheck.check(reads(rate=0.95))
    assert v.colour == "red" and "doesn't keep time" in v.text and "won't start" in v.text


def test_no_answer_and_nothing_playing_each_say_so():
    assert clockcheck.check([]).colour == "red"
    v = clockcheck.check(reads(state="PLAYBACK_STATE_IDLE"))
    assert v.colour == "amber" and "nothing was playing" in v.text


def test_a_slow_clock_is_still_green_but_says_so():
    v = clockcheck.check(reads(rtt=0.080))
    assert v.colour == "green" and "Slow to answer" in v.text


# --- Nudge --------------------------------------------------------------------------------------------------

def test_a_nudge_moves_start_and_the_speakers_shift_as_they_play():
    w = World()
    w.run(0.5)
    c0 = w.play()
    w.run(5.0)
    w.f.nudge(5)
    w.run(3.0)
    assert w.said(f"Start is now {START * 1000 + 5:.0f} ms.")
    off = w.offsets(c0 + START + 0.005, since=w.sim.t - 2)
    assert len(off) > 50 and np.abs(off).max() < TOL, f"out by up to {np.abs(off).max():.2f} ms"
    w.f.nudge(-5)
    w.run(3.0)
    assert np.abs(w.offsets(c0 + START, since=w.sim.t - 2)).max() < TOL
