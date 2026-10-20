"""
Non-stop and a zone stopped by hand (datdude, 20 Oct 2026): stopping on the last track meant music started
again seconds later, as JRiver plays a stopped zone when tracks are added to it. A zone stopped or paused
by hand now gets nothing; a last track that simply ran out before the top-up was ready still carries on.
"""

import pytest


@pytest.fixture
def last_track(app, monkeypatch):
    """A saved playlist with Non-stop on, playing its last track in Speakers. Returns (zone, jobs, clock)."""
    import nonstop
    sp, e = app.saved_playlists, app.engine
    data = sp.main_settings()
    data["rows"] = {"201": dict(sp.DEFAULT_ROW, nonstop="tracks")}
    sp.set_main_settings(data)
    sp.play({"ID": "201", "Name": "Sunday Morning", "Type": "Playlist"}, "10001", report=app.Lines())
    z = app.jriver.zone("Speakers")
    z.pos, z.state, z.position_ms = len(z.playlist) - 1, 2, 0
    clock = [1000.0]
    monkeypatch.setattr(e, "_clock", lambda: clock[0], raising=False)
    jobs = []
    nonstop.attach(lambda job, heading, origin=None: jobs.append(job))
    return z, jobs, clock


def _run(app, jobs):
    r = app.Lines()
    jobs[-1](r)
    return r


def test_stopped_by_hand_adds_nothing(app, last_track):
    import nonstop
    z, jobs, clock = last_track
    n = len(z.playlist)
    nonstop._check_zones()
    assert jobs
    z.state = 0                 # Stop pressed a few seconds in, while the top-up is being found
    clock[0] += 5
    r = _run(app, jobs)
    assert len(z.playlist) == n, "nothing added, so JRiver has nothing to start"
    assert r.has("Non-stop: Speakers was stopped, so nothing was added."), r.text()


def test_paused_adds_nothing(app, last_track):
    import nonstop
    z, jobs, clock = last_track
    n = len(z.playlist)
    nonstop._check_zones()
    z.state = 1
    r = _run(app, jobs)
    assert len(z.playlist) == n
    assert r.has("Non-stop: Speakers was paused, so nothing was added."), r.text()


def test_track_that_ran_out_still_carries_on(app, last_track):
    import nonstop
    z, jobs, clock = last_track
    n = len(z.playlist)
    nonstop._check_zones()
    z.state = 0                 # the last track ended on its own before the top-up was ready
    clock[0] += 60 * 60
    r = _run(app, jobs)
    assert len(z.playlist) > n, r.text()
    assert not r.has("nothing was added")


def test_still_playing_carries_on(app, last_track):
    import nonstop
    z, jobs, clock = last_track
    n = len(z.playlist)
    nonstop._check_zones()
    r = _run(app, jobs)
    assert len(z.playlist) > n, r.text()


def test_stopped_or_paused_last_track_starts_no_top_up(app, last_track):
    import nonstop
    z, jobs, clock = last_track
    for state in (0, 1):
        z.state = state
        nonstop._check_zones()
    assert not jobs, "a last track that isn't playing starts nothing"


def test_play_again_lets_non_stop_try_again(app, last_track):
    import nonstop
    z, jobs, clock = last_track
    nonstop._check_zones()
    z.state = 0
    _run(app, jobs)
    z.state = 2                 # play pressed on the last track again
    nonstop._check_zones()
    assert len(jobs) == 2, "a held top-up doesn't use up the last track"
