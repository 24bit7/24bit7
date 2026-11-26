"""
A paused zone is free for a Play tab build (Ben, 26 Nov 2026). A stuck Alexa flash briefing left the Sonos
paused; a Search build to Multiroom saw a busy zone, so nothing fast-started and the playlist was queued
behind the paused track with nothing pressing play. Now a paused zone plays at once, as a stopped one does,
and a playing zone still queues after its track. Nothing here opens a window.
"""

from test_fast_start_more import first_play


def seed(app, artist, title):
    return app.engine.typed_seed_info(artist, title)


def test_a_paused_zone_plays_the_new_playlist_at_once(app):
    j = app.jriver
    j.play("Speakers", [j.key_of("Queen", "Somebody To Love")], state=1)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    z = j.zone("Speakers")
    assert first_play(app) is not None, r.text()
    assert not r.has("after the current track"), r.text()
    assert z.state == 2, "the zone is playing, not left paused"
    assert z.playlist[0] == first_play(app) and z.pos == 0, "the new playlist leads, the paused track made way"


def test_a_playing_zone_still_queues_after_its_track(app):
    j = app.jriver
    current = j.key_of("Queen", "Somebody To Love")
    j.play("Speakers", [current])
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    z = j.zone("Speakers")
    assert first_play(app) is None
    assert r.has("Queued in Speakers after the current track"), r.text()
    assert z.playlist[0] == current
