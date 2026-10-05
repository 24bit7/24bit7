"""
Blend (Settings > JRiver Playlists): new tracks like a playlist, woven in one for one.
"""

import pytest

from test_voice import alexa, KITCHEN   # noqa: F401  (the mock Alexa fixture)


def blend_on(app, pid="201", mode="tracks"):
    sp = app.saved_playlists
    data = sp.main_settings()
    data["rows"] = {pid: dict(sp.DEFAULT_ROW, blend=mode)}
    sp.set_main_settings(data)


def test_blend_weaves_one_for_one(app, alexa):
    j = app.jriver
    playlist = j.playlists[0]["keys"]            # Sunday Morning, 6 tracks
    blend_on(app)
    r = alexa.say("PlaylistIntent", "sunday morning")
    assert r.started, r
    assert j.zone("Kitchen").playlist == playlist, "the playlist starts at once, as saved"
    log = alexa.run_jobs()[0]
    z = j.zone("Kitchen").playlist
    assert log.has("Done:") and log.has("blended into Sunday Morning"), log.text()
    assert z[0] == playlist[0]
    yours = z[0::2]
    new = z[1::2]
    assert yours == playlist, z
    assert len(new) == len(playlist) and not set(new) & set(playlist), z   # one new per playlist track


def test_blend_keeps_the_current_track_playing(app, alexa):
    j = app.jriver
    playlist = j.playlists[0]["keys"]
    blend_on(app)
    alexa.say("PlaylistIntent", "sunday morning")
    j.zone("Kitchen").pos = 2                   # two tracks in by the time the blend is ready
    log = alexa.run_jobs()[0]
    z = j.zone("Kitchen")
    assert z.playlist[:3] == playlist[:3] and z.pos == 2, log.text()
    assert z.playlist[3] not in playlist, "a new track follows the playing one"


def test_blend_cap(app, alexa, monkeypatch):
    import blend
    monkeypatch.setattr(blend, "CAP", 2)
    j = app.jriver
    blend_on(app)
    alexa.say("PlaylistIntent", "sunday morning")
    log = alexa.run_jobs()[0]
    new = [k for k in j.zone("Kitchen").playlist if k not in j.playlists[0]["keys"]]
    assert len(new) == 2, log.text()


def test_blend_runs_dry(app, alexa):
    for s in ("lastfm", "listenbrainz"):
        app.web.empty.add(s)
    j = app.jriver
    blend_on(app)
    alexa.say("PlaylistIntent", "sunday morning")
    log = alexa.run_jobs()[0]
    assert log.has("nothing new was found"), log.text()
    assert j.zone("Kitchen").playlist == j.playlists[0]["keys"]


def test_blend_leaves_changed_music_alone(app, alexa):
    j = app.jriver
    blend_on(app)
    alexa.say("PlaylistIntent", "sunday morning")
    j.play("Kitchen", [j.key_of("Queen", "Bohemian Rhapsody")])   # someone put something else on
    log = alexa.run_jobs()[0]
    assert log.has("left alone") and j.titles("Kitchen") == ["Queen - Bohemian Rhapsody"], log.text()


def test_blend_off_plays_as_saved(app, alexa):
    alexa.say("PlaylistIntent", "sunday morning")
    assert not alexa.jobs and app.jriver.calls_to("Playback/PlayPlaylist")


def test_blend_goes_in_the_log_under_the_device(app, alexa):
    import buildlog
    blend_on(app)
    alexa.say("PlaylistIntent", "sunday morning")
    job, heading, origin = alexa.jobs[0]
    assert heading.startswith("Blend: Sunday Morning") and origin == {"from": "voice", "device": KITCHEN}


def test_blend_similar_artists(app, alexa):
    j = app.jriver
    playlist = j.playlists[0]["keys"]
    blend_on(app, mode="artists")
    alexa.say("PlaylistIntent", "sunday morning")
    log = alexa.run_jobs()[0]
    z = j.zone("Kitchen").playlist
    assert log.has("Blending in similar artists"), log.text()
    assert z[0::2] == playlist and len(z[1::2]) == len(playlist), log.text()
    assert any(c[0] == "lastfm" and c[2].get("method") == "artist.getsimilar" for c in app.web.calls)


def test_blend_tick_from_first_build_reads_as_similar_tracks(app):
    out = app.saved_playlists.tidy({"rows": {"201": {"blend": "1"}, "202": {"blend": "0"}}})
    assert out["rows"]["201"]["blend"] == "tracks" and out["rows"]["202"]["blend"] == "no"
