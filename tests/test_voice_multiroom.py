"""
Multiroom by voice (stage two, 2d, 9 Nov 2026), Ben's three room commands: switch (as before), multiroom and
single room. Through the real skill code over HTTP to 24bit7's listener, against the fake JRiver. The follower's
link is a stand-in that records what it was asked.
"""

from test_voice import alexa, KITCHEN, LOUNGE  # noqa: F401  (the Alexa fixture)


class FakeLink:
    def __init__(self):
        self.calls = []

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")

    def running(self):
        return self.calls and self.calls[-1] == "start"


def multiroom_on(app):
    """The Kitchen Echo is in the leader's room (zone Kitchen), the Lounge Dot in the follower's (zone Speakers)."""
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Kitchen", MULTIROOM_FOLLOWER="Speakers")
    link = FakeLink()
    app.voice.attach_multiroom(link.start, link.stop, link.running)
    return link


def test_multiroom_needs_the_section_on_and_the_leader_playing(app, alexa):
    r = alexa.say("MultiroomIntent")
    assert "isn't set up" in r.ssml and "Settings, Other, Multiroom" in r.ssml, r
    link = multiroom_on(app)
    r = alexa.say("MultiroomIntent")
    assert "Nothing's playing on Kitchen or the Speakers" in r.ssml and link.calls == [], r
    app.jriver.play("Kitchen", app.jriver.playlists[0]["keys"])
    r = alexa.say("MultiroomIntent", device=LOUNGE)   # from either room
    assert r.started and link.calls == ["start"], r   # started: the skill answers with its chime, as for stop and skip


def test_single_room_in_the_leaders_room_drops_the_speakers(app, alexa):
    link = multiroom_on(app)
    j = app.jriver
    j.play("Kitchen", j.playlists[0]["keys"], pos=1)
    alexa.say("MultiroomIntent")
    r = alexa.say("SingleRoomIntent", device=KITCHEN)
    assert r.started, r
    assert link.calls == ["start", "stop"]
    assert j.zone("Kitchen").state == 2 and j.zone("Kitchen").pos == 1, "the Kitchen plays on, untouched"
    assert j.zone("Speakers").state == 0


def test_single_room_in_the_speakers_room_moves_the_music_there(app, alexa):
    link = multiroom_on(app)
    j = app.jriver
    keys = j.playlists[0]["keys"]
    j.play("Kitchen", keys, pos=2)
    j.zone("Kitchen").position_ms = 45000
    alexa.say("MultiroomIntent")
    r = alexa.say("SingleRoomIntent", device=LOUNGE)
    assert r.started, r
    assert link.calls == ["start", "stop"], "the follower stops before the handover, so the DAC is free"
    z = j.zone("Speakers")
    assert z.state == 2 and z.playlist == list(keys) and z.pos == 2 and z.position_ms == 45000, "the Switch To handover"
    assert j.zone("Kitchen").state == 0, "the leader stops"


def test_single_room_with_the_leader_already_quiet_just_stops_the_follower(app, alexa):
    link = multiroom_on(app)
    r = alexa.say("SingleRoomIntent", device=LOUNGE)
    assert r.started and link.calls == ["stop"], r
    assert app.jriver.zone("Speakers").state == 0


def test_the_help_text_and_the_model_name_the_room_commands(app, alexa):
    assert "multiroom" in alexa.skill.COMMANDS and "single room" in alexa.skill.COMMANDS
    assert alexa.skill.ZONE_INTENTS["MultiroomIntent"] == "multiroom"
    assert alexa.skill.ZONE_INTENTS["SingleRoomIntent"] == "single_room"
    assert "multiroom" in app.voice.SAID and "single_room" in app.voice.SAID


def test_multiroom_with_only_the_speakers_playing_moves_the_music_to_the_leader(app, alexa):
    """12 Nov 2026: said with only the Speakers playing, it answered "Nothing's playing on Sonos". Now the music
    moves to the leader with the Switch To handover, same track and point, and the Speakers follow it."""
    link = multiroom_on(app)
    j = app.jriver
    keys = j.playlists[0]["keys"]
    j.play("Speakers", keys, pos=3)
    j.zone("Speakers").position_ms = 30000
    for device in (LOUNGE, KITCHEN):   # either room
        r = alexa.say("MultiroomIntent", device=device)
        assert r.started and link.calls[-1] == "start", r
        z = j.zone("Kitchen")
        assert z.state == 2 and z.playlist == list(keys) and z.pos == 3 and z.position_ms == 30000
        assert j.zone("Speakers").state == 0, "JRiver's Speakers zone stops: the follower plays them now"
