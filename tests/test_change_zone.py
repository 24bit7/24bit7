"""
Change Zone on the Now Playing row (Ben, 23 Nov 2026): "Move From the Speakers", To another zone or Multiroom,
When Restart This Track or From the Next Track. Restart: the zone stops and the other starts this track from the
top. Next track: the zone finishes this track, stops, and the other starts the next one. To Multiroom the leader
plays first and the follower joins it; from the leader the follower just joins; while Multiroom runs the choices
are just the leader or just the follower.
"""


class FakeLink:
    def __init__(self):
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")

    def running(self):
        return bool(self.calls) and self.calls[-1] == "start"


def multiroom_on(app):
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Sonos", MULTIROOM_FOLLOWER="Speakers")
    app.engine.load_settings()
    link = FakeLink()
    app.voice.attach_multiroom(link.start, link.stop, link.running, leave=link.stop, following=link.running)
    return link


def playing(app, zone="Speakers", pos=2, ms=45000):
    j = app.jriver
    keys = j.playlists[1]["keys"]
    j.play(zone, keys, pos=pos)
    j.zone(zone).position_ms = ms
    return keys


def test_restart_moves_this_track_from_the_top(app):
    j, v = app.jriver, app.voice
    keys = playing(app)
    said = app.Lines()
    assert v.change_zone("Speakers", "Kitchen", v.RESTART, said)
    k = j.zone("Kitchen")
    assert k.state == 2 and k.playlist == list(keys) and k.pos == 2 and k.position_ms == 0, "this track, from the top"
    assert j.zone("Speakers").state == 0
    assert said.has("Moved from Speakers to Kitchen."), said.text()


def test_next_track_waits_for_the_end_then_plays_the_next_one(app):
    j, v = app.jriver, app.voice
    keys = playing(app)
    z = j.zone("Speakers")
    dur = int(float(j.by_key[keys[2]]["Duration"]) * 1000)
    z.position_ms = dur - 100   # about to end
    said = app.Lines()
    assert v.change_zone("Speakers", "Kitchen", v.NEXT, said)
    k = j.zone("Kitchen")
    assert k.state == 2 and k.pos == 3, "the next track, in the other zone"
    assert z.state == 0
    assert said.has("After this track in Speakers, the next one plays in Kitchen."), said.text()


def test_next_track_moves_the_one_that_has_just_started(app, monkeypatch):
    """Read a moment late: the Speakers have already begun the next track, which is the one that moves."""
    j, v = app.jriver, app.voice
    keys = playing(app, ms=1000)
    z = j.zone("Speakers")
    real = v._info_items
    reads = []

    def info(zid):
        reads.append(zid)
        if len(reads) == 3:   # change_zone's read, the wait's first, then the one that finds it moved on
            z.pos, z.position_ms = 3, 50
        return real(zid)
    monkeypatch.setattr(v, "_info_items", info)
    monkeypatch.setattr(v.time, "sleep", lambda s: None)
    assert v.change_zone("Speakers", "Kitchen", v.NEXT, app.Lines())
    assert j.zone("Kitchen").pos == 3


def test_next_track_gives_up_if_the_zone_stops_first(app, monkeypatch):
    j, v = app.jriver, app.voice
    playing(app, ms=1000)
    real = v._info_items
    reads = []

    def info(zid):
        reads.append(zid)
        if len(reads) == 2:
            j.zone("Speakers").state = 0
        return real(zid)
    monkeypatch.setattr(v, "_info_items", info)
    monkeypatch.setattr(v.time, "sleep", lambda s: None)
    said = app.Lines()
    assert not v.change_zone("Speakers", "Kitchen", v.NEXT, said)
    assert j.zone("Kitchen").state == 0
    assert said.has("Speakers stopped before the track ended, so nothing moved."), said.text()


def test_next_track_on_the_last_track_says_so(app):
    j, v = app.jriver, app.voice
    keys = playing(app)
    j.zone("Speakers").pos = len(keys) - 1
    said = app.Lines()
    assert not v.change_zone("Speakers", "Kitchen", v.NEXT, said)
    assert said.has("This is the last track in Speakers, so nothing follows it to move."), said.text()


def test_from_the_speakers_to_multiroom_the_leader_plays_then_the_speakers_join(app):
    j, v = app.jriver, app.voice
    link = multiroom_on(app)
    targets, when = v.change_targets("Speakers")
    assert targets[-1] == v.MULTIROOM and "Sonos" in targets and when
    keys = playing(app)
    order = []
    link.start = lambda: order.append(("start", j.zone("Sonos").state))
    app.voice.attach_multiroom(link.start, link.stop, link.running, leave=link.stop, following=link.running)
    assert v.change_zone("Speakers", v.MULTIROOM, v.RESTART, app.Lines())
    s = j.zone("Sonos")
    assert s.playlist == list(keys) and s.pos == 2 and s.position_ms == 0
    assert order == [("start", 2)], "the leader is playing before the follower is told to join"
    assert j.zone("Speakers").state == 0, "JRiver's Speakers zone stops: the follower plays them now"


def test_from_the_leader_multiroom_needs_no_when_and_the_follower_joins(app):
    v = app.voice
    link = multiroom_on(app)
    playing(app, zone="Sonos")
    targets, when = v.change_targets("Sonos")
    assert v.MULTIROOM in targets and when, "When is still asked for the plain moves"
    assert v.change_zone("Sonos", v.MULTIROOM, None, app.Lines())
    assert link.calls == ["start"] and app.jriver.zone("Sonos").state == 2, "the Sonos plays on, untouched"


def test_while_multiroom_runs_its_just_the_leader_or_just_the_follower(app):
    j, v = app.jriver, app.voice
    link = multiroom_on(app)
    keys = playing(app, zone="Sonos")
    link.start()
    assert v.change_targets("Sonos") == (["Sonos", "Speakers"], False)
    said = app.Lines()
    assert v.change_zone("Sonos", "Speakers", None, said)
    z = j.zone("Speakers")
    assert link.calls[-1] == "stop" and z.state == 2 and z.playlist == list(keys) and z.pos == 2 and z.position_ms == 45000
    assert j.zone("Sonos").state == 0
    assert said.has("Just the Speakers now."), said.text()
    assert not said.has("[Voice]"), "a button, not a voice request"


def test_just_the_leader_leaves_it_playing(app):
    j, v = app.jriver, app.voice
    link = multiroom_on(app)
    playing(app, zone="Sonos")
    link.start()
    assert v.change_zone("Sonos", "Sonos", None, app.Lines())
    assert link.calls[-1] == "stop" and j.zone("Sonos").state == 2


def test_non_stop_follows_the_music(app):
    import engine
    j, v = app.jriver, app.voice
    playing(app)
    sid, kid = engine.zone_id("Speakers"), engine.zone_id("Kitchen")
    engine.NONSTOP_ZONES[sid] = {"mode": "similar"}
    assert v.change_zone("Speakers", "Kitchen", v.RESTART, app.Lines())
    assert kid in engine.NONSTOP_ZONES and sid not in engine.NONSTOP_ZONES
