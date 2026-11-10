"""
Multiroom, the Sonos's clock (9 Nov 2026): reading the millisecond counter over the websocket and finding its origin.
Against tests/fake_sonos.py; nothing touches the real Sonos.
"""

import os
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import sonos
finally:
    sys.path.remove(REPO)
from fake_sonos import FakeSonos, GROUP, HOUSEHOLD

R = sonos.Read
PLAY, PAUSED = "PLAYBACK_STATE_PLAYING", "PLAYBACK_STATE_PAUSED"


def wait_for(cond, timeout=5.0):
    end = time.perf_counter() + timeout
    while time.perf_counter() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def fake():
    with FakeSonos() as f:
        yield f


@pytest.fixture
def clock(fake):
    c = sonos.SonosClock(household=HOUSEHOLD, group=GROUP, url=fake.url, interval=0.005)
    c.start()
    yield c
    c.stop()


# --- the origin from a set of reads --------------------------------------------------------

def read(sampled, pos_ms, there, back):
    """A read whose counter was sampled at our time sampled: asked there seconds before, answered back seconds after."""
    a, b = sampled - there, sampled + back
    return R((a + b) / 2, b - a, pos_ms, PLAY)


def test_origin_is_the_second_lowest_upper_bound():
    # 9 Nov 2026, 14:15: for about fifteen seconds after a track starts the Sonos holds each request 15 to 300 ms
    # before reading its counter, then answers fast. Midpoints wander by tens of ms; the upper bounds don't.
    busy = [read(100 + k, k * 1000, there=0.015 + 0.03 * (k % 7), back=0.0005) for k in range(1, 20)]
    assert sonos.origin_of(busy) == pytest.approx(100.0005, abs=1e-6)
    midpoints = sorted(r.t - r.pos_ms / 1000 for r in sorted(busy, key=lambda r: r.rtt)[:20])
    assert midpoints[len(midpoints) // 2] < 99.97, "the old median of midpoints is tens of ms out on these"
    odd = read(130, 30000, there=0.001, back=-0.010)   # one read that claims an impossible early answer
    assert sonos.origin_of(busy + [odd]) == pytest.approx(100.0005, abs=1e-6), "one odd read mustn't pull it"


def test_origin_leaves_out_reads_that_arent_playing():
    reads = [R(50.0, 0.001, 0, PAUSED), R(60.0, 0.001, None, PLAY), R(100.0, 0.004, 0, PLAY)]
    assert sonos.origin_of(reads) == pytest.approx(100.002)
    assert sonos.origin_of(reads[:2]) is None


# --- against the fake Sonos -----------------------------------------------------------------

def test_the_clock_finds_the_counter_origin(fake, clock):
    fake.play(at_ms=12345)
    assert wait_for(lambda: len(clock.recent(since=fake.origin + 12.4)) >= 40)
    c = clock.origin(window=1.0)
    assert c is not None
    assert abs(c - fake.origin) < 0.003, f"origin off by {(c - fake.origin) * 1000:.1f} ms"
    assert clock.state == PLAY


def test_it_asks_the_way_the_sonos_wants(fake, clock):
    # The key, the subprotocol, the household and the group: without any of them the real Sonos says no.
    fake.play()
    assert wait_for(lambda: clock.latest() is not None)
    assert fake.refused == []
    head = fake.requests[0][0]
    assert (head["namespace"], head["command"]) == ("playback:1", "getPlaybackStatus")
    assert (head["householdId"], head["groupId"]) == (HOUSEHOLD, GROUP)


def test_lopsided_slow_reads_at_a_track_start_dont_move_the_origin(fake, clock):
    # At a track's start the Sonos answers slowly, and a read that is slow one way has its midpoint off. Each of
    # these is 30 ms off by its midpoint; its upper bound is only off by its 10 ms way back, and the others' aren't.
    assert wait_for(lambda: clock.latest() is not None)
    t0 = time.perf_counter()
    fake.play(slow=[(0.070, 0.010)] * 5)
    assert wait_for(lambda: len(clock.recent(since=t0)) >= 40)
    lopsided = [r for r in clock.recent(since=t0) if r.rtt > 0.07 and r.pos_ms is not None]
    assert lopsided and all(abs(r.t - r.pos_ms / 1000 - fake.origin) > 0.02 for r in lopsided)
    assert abs(clock.origin(since=t0) - fake.origin) < 0.003
    first = clock.first_origin_after(t0)
    # the five slow reads are 10 ms late by their upper bound; a busy PC adds a little (12.08 ms once in the full
    # suite of 10 Nov 2026, with every window test running around it), so the bound leaves room for that
    assert first is not None and abs(first - fake.origin) < 0.015


def test_a_paused_sonos_gives_no_origin(fake, clock):
    fake.play(at_ms=5000)
    assert wait_for(lambda: clock.state == PLAY)
    fake.pause()
    t0 = time.perf_counter()
    assert wait_for(lambda: len(clock.recent(since=t0 + 0.05)) >= 5)
    assert clock.state == PAUSED
    assert clock.origin(since=t0 + 0.05) is None


def test_the_age_of_the_last_read_grows_when_the_sonos_goes_quiet(fake, clock):
    fake.play()
    assert wait_for(lambda: clock.latest() is not None)
    assert clock.last_read_age < 0.1
    fake.quiet.set()
    time.sleep(0.3)
    assert clock.last_read_age > 0.25
    fake.quiet.clear()
    assert wait_for(lambda: clock.last_read_age < 0.05)


def test_the_clock_connects_again_after_the_sonos_drops_it(fake):
    c = sonos.SonosClock(household=HOUSEHOLD, group=GROUP, url=fake.url, interval=0.005, retry=0.1)
    c.start()
    try:
        fake.play()
        assert wait_for(lambda: c.latest() is not None)
        fake.drop()   # the Sonos restarts
        assert wait_for(lambda: c.error is not None)
        t0 = time.perf_counter()
        assert wait_for(lambda: len(c.recent(since=t0)) >= 5), "no reads after the drop"
        assert c.connected.is_set()
    finally:
        c.stop()


def test_find_reads_household_and_group_from_info(fake):
    loc = f"http://127.0.0.1:{fake.info_port}/xml/device_description.xml"
    found = sonos.find(locations=[loc, loc])
    assert found == [{"ip": "127.0.0.1", "name": "Living Room", "householdId": HOUSEHOLD, "groupId": GROUP,
                      "model": "Sonos One"}]   # the model keys the speaker profile (stage two)
    assert sonos.find("living", locations=[loc])[0]["name"] == "Living Room"
    assert sonos.find("Kitchen", locations=[loc]) == []
