"""
Music asked for by voice plays in the room of the Echo that heard it (Ben, 10 Nov 2026). His wife asked for music
like Disturbed at the Sonos and it played on the Speakers too: the Play tab's Output had been left on Multiroom,
and the rule looked only at where the playlist went (the leader zone), not at who asked. Now a build asked for by
voice never starts the Speakers following; if they're following when it lands in the leader's room, they finish
the track they're on and drop out; and "multiroom" by voice brings them back. More like this adds to what's
playing, so it leaves the rooms as they are. Through the real skill code, against the fake JRiver.
"""

from test_voice import alexa, KITCHEN, LOUNGE  # noqa: F401  (the Alexa fixture)


class FakeLink:
    """The follower's link as voice and the Play tab see it: what it was asked, and whether it's meant to follow."""
    def __init__(self):
        self.calls, self.wanted = [], False

    def start(self):
        self.calls.append("start")
        self.wanted = True

    def stop(self):
        self.calls.append("stop")
        self.wanted = False

    def leave(self):
        self.calls.append("leave")
        self.wanted = False

    def running(self):
        return bool(self.calls)   # once started the child stays connected, idle, after a leave


def multiroom_on(app, following=True):
    """Output left on Multiroom; the Kitchen Echo is in the leader's room, the Lounge Dot in the follower's."""
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Kitchen", MULTIROOM_FOLLOWER="Speakers",
                OUTPUT_TARGET="multiroom")
    link = FakeLink()
    app.voice.attach_multiroom(link.start, link.stop, link.running, leave=link.leave, following=lambda: link.wanted)
    # the Play tab's hook, as gui.multiroom_build_sent has it: start unless the Speakers are meant to be following
    app.engine.MULTIROOM_HOOK = lambda: None if link.wanted else link.start()
    if following:
        link.start()
        link.calls.clear()
    return link


def test_a_build_asked_for_in_the_leaders_room_never_starts_the_speakers(app, alexa):
    link = multiroom_on(app, following=False)
    r = alexa.say("MusicLikeIntent", "the beatles")
    assert r.started, r
    logs = alexa.run_jobs()
    assert app.jriver.zone("Kitchen").playlist, logs[0].text()
    assert link.calls == [], "Output on Multiroom is for the Play tab's builds, not for whoever asks in that room"
    assert not app.engine.VOICE_BUILD, "and the mark comes off when the build ends"


def test_the_speakers_drop_out_when_music_is_asked_for_in_the_leaders_room(app, alexa):
    link = multiroom_on(app)
    j = app.jriver
    j.play("Kitchen", j.playlists[0]["keys"])
    alexa.say("MusicLikeIntent", "the beatles")
    logs = alexa.run_jobs()
    assert link.calls == ["leave"], "they finish their track and stop following; nothing starts them again"
    assert logs[0].has("[Voice] Asked for on Kitchen, so the Speakers drop out after this track"), logs[0].text()


def test_an_album_asked_for_in_the_leaders_room_drops_them_before_it_plays(app, alexa):
    link = multiroom_on(app)
    j = app.jriver
    j.play("Kitchen", j.playlists[0]["keys"])
    at_leave = []
    real = link.leave
    link.leave = lambda: (at_leave.append(list(j.zone("Kitchen").playlist)), real())
    app.voice.attach_multiroom(link.start, link.stop, link.running, leave=link.leave, following=lambda: link.wanted)
    r = alexa.say("AlbumIntent", "abbey road")
    assert r.started, r
    assert link.calls == ["leave"]
    assert at_leave == [j.playlists[0]["keys"]], "told to leave before the album replaced what was playing"
    assert j.zone("Kitchen").playlist != j.playlists[0]["keys"]


def test_more_like_this_and_other_rooms_leave_the_speakers_following(app, alexa):
    link = multiroom_on(app)
    j = app.jriver
    j.play("Kitchen", j.playlists[0]["keys"])
    r = alexa.say("MoreLikeThisIntent")
    assert r.started, r
    alexa.run_jobs()
    assert link.calls == [], "more of what's playing, where it's playing"
    alexa.say("MusicLikeIntent", "the beatles", device=LOUNGE)   # asked for in the Speakers' own room
    alexa.run_jobs()
    assert link.calls == [], "only the leader's room is the one the Speakers follow"


def test_multiroom_by_voice_brings_them_back_and_the_play_tab_still_starts_them(app, alexa):
    link = multiroom_on(app)
    e, j = app.engine, app.jriver
    j.play("Kitchen", j.playlists[0]["keys"])
    alexa.say("MusicLikeIntent", "the beatles")
    alexa.run_jobs()
    assert link.calls == ["leave"] and not link.wanted
    r = alexa.say("MultiroomIntent")
    assert r.started and link.calls == ["leave", "start"], r
    link.leave()   # asked for by voice again, later
    link.calls.clear()
    j.play("Speakers", [j.key_of("The Beatles", "Something")])   # the Play tab's seed, in the zone it shows
    r = app.Lines()
    e.create_similar_playlist(report=r)   # a build from the Play tab, Output still on Multiroom
    assert link.calls == ["start"], ("idle but still connected: it's whether they're wanted that counts", r.text())


def test_non_stop_adding_to_the_leader_leaves_the_rooms_as_they_are(app):
    e, j = app.engine, app.jriver
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Kitchen", MULTIROOM_FOLLOWER="Speakers",
                OUTPUT_TARGET="multiroom")
    asked = []
    e.MULTIROOM_HOOK = lambda: asked.append(1)
    zid = j.zone("Kitchen").id
    e.NONSTOP_APPEND = True
    try:
        e._multiroom_sent(zid)
    finally:
        e.NONSTOP_APPEND = False
    assert asked == [], "a playlist asked for by voice isn't joined by the Speakers when Non-stop adds to it"
    e._multiroom_sent(zid)
    assert asked == [1]
