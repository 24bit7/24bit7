"""
One Discover session per Radio listen (Ben, 23 Nov 2026: "we only consolidate back to back sessions"). Every
Radio round was a session of its own, so an afternoon of one station was a page of "Radio: Classic Rock / Rock".
Non-stop's next round now adds to the session that started the listen, as does the station pressed again while
its zone is still playing it; after something else, or with the zone stopped, it's a new session. Nothing here
opens a window.
"""

from test_radio import EVERYONE, play_counts
from test_radio_playlist import radio  # noqa: F401  (the radio fixture)


def _radio_sessions(app):
    return [r[0] for r in app.engine.db().execute("SELECT id FROM sessions WHERE mode='radio' ORDER BY id")]


def _rows(app, sid):
    return app.engine.db().execute("SELECT COUNT(*) FROM discoveries WHERE session_id=?", (sid,)).fetchone()[0]


def _queued(app, sid):
    return app.engine.db().execute("SELECT queued FROM sessions WHERE id=?", (sid,)).fetchone()[0]


def test_non_stop_rounds_add_to_the_listen(app, radio):
    import nonstop
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    lane = radio.lanes()[0]
    radio.build(lane["id"], app.Lines())
    zone = app.jriver.zone("Speakers")
    first = _radio_sessions(app)
    assert len(first) == 1
    rows, queued = _rows(app, first[0]), _queued(app, first[0])
    assert rows and queued
    zone.pos = len(zone.playlist) - 1
    r = app.Lines()
    nonstop._job(zone.id, "Speakers", {})(r)
    assert r.has("Radio plays on."), r.text()
    assert _radio_sessions(app) == first, "the next round is the same session"
    assert _rows(app, first[0]) > rows, "with the new round's rows"
    assert _queued(app, first[0]) == len(zone.playlist), "and the tracks of both rounds"
    done = [x for x in r if x.startswith("Done:")]
    assert done and str(len(zone.playlist) - queued) in done[-1], ("the Done line is this round's", done)


def test_pressing_the_station_again_while_it_plays_carries_on(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    lane = radio.lanes()[0]
    radio.build(lane["id"], app.Lines())
    zone = app.jriver.zone("Speakers")
    zone.state = 2
    radio.build(lane["id"], app.Lines())
    assert len(_radio_sessions(app)) == 1, "back to back"
    zone.state = 0
    radio.build(lane["id"], app.Lines())
    assert len(_radio_sessions(app)) == 2, "the zone had stopped: a new listen"


def test_another_station_or_something_else_in_between_is_a_new_session(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    lanes = radio.lanes()
    radio.build(lanes[0]["id"], app.Lines())
    zone = app.jriver.zone("Speakers")
    zone.state = 2
    if len(lanes) > 1:
        radio.build(lanes[1]["id"], app.Lines())
        assert len(_radio_sessions(app)) == 2, "another station"
    app.engine.nonstop_forget(zone.id)   # an album went on in between
    radio.build(lanes[0]["id"], app.Lines())
    assert len(_radio_sessions(app)) == (3 if len(lanes) > 1 else 2)
