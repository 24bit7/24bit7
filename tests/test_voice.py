"""
Voice commands end to end: a real-shaped Alexa request goes through the needle
drop skill (alexa/lambda_function.py, run with the real ask-sdk), over HTTP to
24bit7's listener, and the build runs against the fake JRiver.
"""

import importlib
import json
import sys
import uuid

import pytest

KITCHEN = "amzn1.ask.device.KITCHEN"
LOUNGE = "amzn1.ask.device.LOUNGE"
STRANGER = "amzn1.ask.device.NEW"


class Alexa:
    """Plays the part of Amazon: builds request envelopes and calls the skill."""
    def __init__(self, app, monkeypatch):
        sys.path.insert(0, str(app.folder / "alexa"))
        for m in ("lambda_function", "skill_settings"):
            sys.modules.pop(m, None)
        self.skill = importlib.import_module("lambda_function")
        monkeypatch.setattr(self.skill, "BIT7_URL", f"http://127.0.0.1:{app.engine.VOICE_PORT}")
        monkeypatch.setattr(self.skill, "BIT7_KEY", app.engine.VOICE_KEY)
        self.session = {}

    def _envelope(self, request, device, new=True):
        return {
            "version": "1.0",
            "session": {"new": new, "sessionId": "amzn1.echo-api.session.x", "application": {"applicationId": "app"},
                        "attributes": dict(self.session), "user": {"userId": "user"}},
            "context": {"System": {"application": {"applicationId": "app"}, "user": {"userId": "user"},
                                   "device": {"deviceId": device, "supportedInterfaces": {}},
                                   "apiEndpoint": "https://api.amazonalexa.com"}},
            "request": dict(request, requestId=f"req-{uuid.uuid4()}", timestamp="2026-10-05T12:00:00Z",
                            locale="en-GB"),
        }

    def say(self, intent, query=None, device=KITCHEN, new=True):
        slots = {"query": {"name": "query", "value": query}} if query is not None else {}
        out = self.skill.lambda_handler(self._envelope(
            {"type": "IntentRequest", "intent": {"name": intent, "confirmationStatus": "NONE", "slots": slots}},
            device, new), None)
        self.session = out.get("sessionAttributes") or {}
        return Reply(out)

    def launch(self, device=KITCHEN):
        return Reply(self.skill.lambda_handler(self._envelope({"type": "LaunchRequest"}, device), None))


class Reply:
    def __init__(self, raw):
        self.raw = raw
        resp = raw["response"]
        self.ssml = (resp.get("outputSpeech") or {}).get("ssml", "")
        self.ends = resp.get("shouldEndSession")
        self.reprompt = ((resp.get("reprompt") or {}).get("outputSpeech") or {}).get("ssml", "")

    @property
    def started(self):
        return "<audio" in self.ssml and self.ends is True

    def __repr__(self):
        return f"Reply({self.ssml!r}, ends={self.ends})"


@pytest.fixture
def alexa(app, monkeypatch):
    v = app.voice
    jobs = []
    busy = [False]

    def submit(job, heading, meta=None):
        jobs.append((job, heading, meta))
    v.attach(submit, lambda: busy[0])
    status = v.restart()
    assert status.startswith("Listening"), status
    for device, name, zone in ((KITCHEN, "Kitchen Echo", "Kitchen"), (LOUNGE, "Lounge Dot", "Speakers")):
        v._hear_device(device)
        v.update_device(device, name=name, zone=zone)
    a = Alexa(app, monkeypatch)
    a.jobs, a.busy = jobs, busy

    def run_jobs():
        logs = []
        while jobs:
            job, heading, meta = jobs.pop(0)
            lines = app.Lines()
            lines(heading)
            job(lines)
            logs.append(lines)
        return logs
    a.run_jobs = run_jobs
    return a


# --- the listener itself -----------------------------------------------------------

def test_ping_and_key(app, alexa):
    import urllib.request
    import urllib.error
    url = f"http://127.0.0.1:{app.engine.VOICE_PORT}/ping"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"X-24bit7-Key": app.engine.VOICE_KEY})) as r:
        assert json.loads(r.read())["version"] == app.engine.VERSION
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(urllib.request.Request(url, headers={"X-24bit7-Key": "wrong"}))
    assert e.value.code == 401


def test_wrong_key_in_skill_is_explained(app, alexa, monkeypatch):
    monkeypatch.setattr(alexa.skill, "BIT7_KEY", "wrong")
    r = alexa.say("SongsByIntent", "the beatles")
    assert "didn't accept the key" in r.ssml


def test_listener_down_is_explained(app, alexa):
    app.voice.stop()
    r = alexa.say("SongsByIntent", "the beatles")
    assert "isn't answering" in r.ssml


def test_launch_and_help(app, alexa):
    r = alexa.launch()
    assert "Ready" in r.ssml and r.ends is not True
    assert "list commands" in r.reprompt.lower() and "songs by" not in r.reprompt.lower(), r.reprompt
    r = alexa.say("AMAZON.HelpIntent")
    assert "songs by" in r.ssml.lower()
    r = alexa.say("AMAZON.StopIntent")
    assert r.ends is True


def test_not_caught_says_short_line_once(app, alexa):
    r = alexa.say("AMAZON.FallbackIntent")
    assert "didn't catch that" in r.ssml and "list commands" in r.ssml.lower(), r
    assert "songs by" not in r.ssml.lower(), "the list is never read unless asked for"
    assert not r.reprompt, "no second reading"
    assert r.ends is False, "listens once more"


def test_list_commands_reads_once_then_listens(app, alexa):
    r = alexa.say("ListCommandsIntent")
    for words in ("songs by", "album", "skip", "keep it going", "pause", "switch"):
        assert words in r.ssml.lower(), words
    assert not r.reprompt and r.ends is False, r


# --- keep it going ----------------------------------------------------------------------

def test_keep_going_tops_up_music_started_in_jriver(app, alexa):
    import nonstop
    j, e = app.jriver, app.engine
    album = [r["Key"] for r in j.tracks if r["Album"] == "Help!"]
    j.play("Kitchen", album)                              # started in JRiver, not by 24bit7
    r = alexa.say("KeepGoingIntent")
    assert r.started, r
    assert e.NONSTOP_ZONES["10002"]["saved_cfg"]["using"] == "tracks", "the Similar Tracks Non-stop settings"
    r = alexa.say("KeepGoingIntent")
    assert "already on" in r.ssml, r
    z = j.zone("Kitchen")
    z.pos = len(album) - 1                                 # the last track starts
    jobs = []
    nonstop.attach(lambda job, heading, origin=None: jobs.append(job))
    nonstop._check_zones()
    assert jobs, "the last track should trigger a top-up"
    lines = app.Lines()
    jobs[0](lines)
    assert len(z.playlist) > len(album) and z.playlist[:len(album)] == album, lines.text()


def test_keep_going_uses_settings_even_when_nonstop_is_off(app, alexa):
    app.set_env(NONSTOP_TRACKS="0", NONSTOP_TRACKS_USING="artists", NONSTOP_TRACKS_RESEED="second")
    j = app.jriver
    j.play("Kitchen", j.playlists[0]["keys"])
    alexa.say("KeepGoingIntent")
    assert app.engine.NONSTOP_ZONES["10002"]["saved_cfg"] == {"using": "artists", "reseed": "second"}


def test_keep_going_nothing_playing(app, alexa):
    r = alexa.say("KeepGoingIntent")
    assert "Nothing's playing on Kitchen" in r.ssml, r


def test_keep_going_ends_when_music_is_replaced(app, alexa):
    j = app.jriver
    j.play("Kitchen", j.playlists[0]["keys"])
    alexa.say("KeepGoingIntent")
    alexa.say("AlbumIntent", "abbey road")
    assert "10002" not in app.engine.NONSTOP_ZONES


def test_keep_going_shortcut(app, alexa):
    import hotkeys
    j = app.jriver
    j.play("Speakers", j.playlists[0]["keys"])
    app.set_env(HOTKEY_ZONE="Speakers")
    lines = app.Lines()
    hotkeys._job("KEEP_GOING")(lines)
    assert lines.has("Non-stop is on for Speakers"), lines.text()
    assert "10001" in app.engine.NONSTOP_ZONES


# --- stop, pause, resume ---------------------------------------------------------------

def test_stop_pause_resume_act_on_the_device_zone(app, alexa):
    j = app.jriver
    j.play("Speakers", j.playlists[0]["keys"])          # the Lounge Dot's zone
    j.play("Kitchen", j.playlists[1]["keys"])
    r = alexa.say("PauseMusicIntent", device=LOUNGE)
    assert r.started and j.zone("Speakers").state == 1 and j.zone("Kitchen").state == 2, r
    r = alexa.say("PauseMusicIntent", device=LOUNGE)
    assert "already paused" in r.ssml, r
    r = alexa.say("ResumeMusicIntent", device=LOUNGE)
    assert r.started and j.zone("Speakers").state == 2, r
    r = alexa.say("StopMusicIntent", device=LOUNGE)
    assert r.started and j.zone("Speakers").state == 0 and j.zone("Kitchen").state == 2, r
    r = alexa.say("StopMusicIntent", device=LOUNGE)
    assert "Nothing's playing" in r.ssml, r


def test_pause_keeps_the_place(app, alexa):
    j = app.jriver
    j.play("Kitchen", j.playlists[0]["keys"], pos=2)
    j.zone("Kitchen").position_ms = 61000
    alexa.say("PauseMusicIntent")
    alexa.say("ResumeMusicIntent")
    z = j.zone("Kitchen")
    assert (z.pos, z.position_ms, z.state) == (2, 61000, 2)


# --- switch -----------------------------------------------------------------------------

def test_switch_with_two_zones_goes_straight_there(app, alexa):
    j = app.jriver
    keys = j.playlists[1]["keys"]
    j.play("Kitchen", keys, pos=3)
    j.zone("Kitchen").position_ms = 95000
    r = alexa.say("SwitchZonesIntent")                     # from the Kitchen Echo
    assert r.started, r
    k, s = j.zone("Kitchen"), j.zone("Speakers")
    assert s.playlist == keys and s.pos == 3 and s.position_ms == 95000 and s.state == 2
    assert k.state == 0, "the zone it left stops"


def test_switch_from_a_room_with_nothing_playing(app, alexa):
    j = app.jriver
    j.play("Kitchen", j.playlists[1]["keys"])
    r = alexa.say("SwitchZonesIntent", device=LOUNGE)       # the only zone playing is Kitchen
    assert r.started and j.zone("Speakers").state == 2 and j.zone("Kitchen").state == 0, r


def test_switch_keeps_pause_and_moves_nonstop(app, alexa):
    j, e = app.jriver, app.engine
    j.play("Kitchen", j.playlists[1]["keys"], state=1)
    e.nonstop_record("10002", j.playlists[1]["keys"], kind="tracks")
    alexa.say("SwitchZonesIntent")
    assert j.zone("Speakers").state == 1, "a paused zone arrives paused"
    assert "10001" in e.NONSTOP_ZONES and "10002" not in e.NONSTOP_ZONES


def sonos_device(app):
    v = app.voice
    v._hear_device("amzn1.ask.device.SONOS")
    v.update_device("amzn1.ask.device.SONOS", name="Sonos One", zone="Sonos")


def test_switch_with_three_zones_asks_then_answer(app, alexa):
    j = app.jriver
    sonos_device(app)
    j.play("Kitchen", j.playlists[1]["keys"])
    r = alexa.say("SwitchZonesIntent")
    assert "Which zone?" in r.ssml and "Speakers" in r.ssml and "Sonos" in r.ssml and r.ends is not True, r
    assert "to, then the zone" in r.reprompt, r.reprompt
    r = alexa.say("SwitchToIntent", "the sonos", new=False)
    assert r.started and j.zone("Sonos").state == 2 and j.zone("Kitchen").state == 0, r


def test_switch_to_named_zone(app, alexa):
    j = app.jriver
    sonos_device(app)
    j.play("Kitchen", j.playlists[1]["keys"])
    r = alexa.say("SwitchToIntent", "speakers")
    assert r.started and j.zone("Speakers").state == 2, r


def test_switch_respects_enable_switch_to(app, alexa):
    j = app.jriver
    sonos_device(app)
    app.voice.set_switch_enabled("Sonos", False)
    j.play("Kitchen", j.playlists[1]["keys"])
    r = alexa.say("SwitchToIntent", "sonos")
    assert "isn't ticked" in r.ssml, r
    r = alexa.say("SwitchZonesIntent")                     # only Speakers left, so straight there
    assert r.started and j.zone("Speakers").state == 2, r


def test_switch_ignores_zones_without_a_device(app, alexa):
    assert "Sonos" not in app.voice.switch_targets()


def test_switch_nothing_playing(app, alexa):
    r = alexa.say("SwitchZonesIntent")
    assert "Nothing's playing" in r.ssml, r


def test_switch_shortcut_steps_through_zones(app, alexa):
    j = app.jriver
    sonos_device(app)
    j.play("Kitchen", j.playlists[1]["keys"])
    order = []
    for _ in range(3):
        playing = [z for z in ("Speakers", "Kitchen", "Sonos") if j.zone(z).state == 2]
        line = app.voice.switch_step(playing[0])
        order.append(line)
    assert order[0].endswith("from Kitchen to Sonos.") and order[1].endswith("from Sonos to Speakers.") \
        and order[2].endswith("from Speakers to Kitchen."), order


def test_model_has_every_intent_the_skill_handles(app, alexa):
    import json
    model = json.load(open(app.folder / "alexa" / "interaction_model.json", encoding="utf-8"))
    names = {i["name"] for i in model["interactionModel"]["languageModel"]["intents"]}
    handled = set(alexa.skill.INTENTS) | set(alexa.skill.ZONE_INTENTS) | {
        "ByArtistIntent", "SwitchToIntent", "ListCommandsIntent", "AMAZON.HelpIntent", "AMAZON.FallbackIntent",
        "AMAZON.StopIntent", "AMAZON.CancelIntent"}
    assert handled <= names, handled - names
    for intent in model["interactionModel"]["languageModel"]["intents"]:
        for sample in intent.get("samples", []):
            assert "-" not in sample and not sample.lower().startswith("play "), sample


# --- devices ------------------------------------------------------------------------

def test_new_device_is_told_to_set_up(app, alexa):
    r = alexa.say("SongsByIntent", "the beatles", device=STRANGER)
    assert "isn't set up yet" in r.ssml
    names = [d[1] for d in app.voice.devices()]
    assert any(n.startswith("New device") for n in names)
    assert not alexa.jobs


def test_device_zone_missing_in_jriver(app, alexa):
    app.voice.update_device(KITCHEN, zone="Garage")
    r = alexa.say("SongsByIntent", "the beatles")
    assert "can't find the Garage zone" in r.ssml


def test_failed_command_goes_to_console_and_log(app, alexa):
    import buildlog
    r = alexa.say("AlbumIntent", "an album that does not exist")
    assert "couldn't find an album" in r.ssml
    assert app.printed.has('Problem: Alexa said "I couldn\'t find an album')
    rows = buildlog.recent()
    assert rows, "the failed command should be kept in the Log"


# --- instant commands ------------------------------------------------------------------

def test_album(app, alexa):
    r = alexa.say("AlbumIntent", "abbey road")
    assert r.started
    assert app.jriver.titles("Kitchen")[0] == "The Beatles - Come Together"
    assert len(app.jriver.zone("Kitchen").playlist) == 7


def test_album_spoken_numbers_and_the(app, alexa):
    r = alexa.say("AlbumIntent", "something else")
    assert r.started
    assert app.jriver.titles("Kitchen")[0].startswith("Kinks, The - ")


def test_album_shared_title_asks_then_by_artist(app, alexa):
    r = alexa.say("AlbumIntent", "greatest hits")
    assert r.ends is not True and "Which one" in r.ssml, r
    assert alexa.session.get("ask") == "album"
    r = alexa.say("ByArtistIntent", "queen", new=False)
    assert r.started, r
    assert app.jriver.titles("Kitchen")[0] == "Queen - Bohemian Rhapsody"


def test_song(app, alexa):
    r = alexa.say("SongIntent", "waterloo sunset")
    assert r.started
    assert app.jriver.titles("Kitchen") == ["Kinks, The - Waterloo Sunset"]


def test_song_bracketed_title(app, alexa):
    r = alexa.say("SongIntent", "i can't get no satisfaction")
    assert r.started, r
    assert app.jriver.titles("Kitchen") == ["The Rolling Stones - (I Can't Get No) Satisfaction"]


def test_song_heard_as_songs_by(app, alexa):
    r = alexa.say("SongIntent", "by the beatles")   # "song by" heard for "songs by"
    assert r.started
    assert alexa.jobs and "songs by" in alexa.jobs[0][1]


def test_shuffle(app, alexa):
    r = alexa.say("ShuffleIntent", "the beatles")
    assert r.started
    titles = app.jriver.titles("Kitchen")
    assert titles and all(t.startswith("The Beatles - ") for t in titles)
    assert len(titles) == 15


def test_shuffle_misheard_artist(app, alexa):
    r = alexa.say("ShuffleIntent", "the beetles")
    assert r.started, r


def test_shuffle_skips_long_closer(app, alexa):
    alexa.say("ShuffleIntent", "pink floyd")
    assert "Pink Floyd - Echoes" not in app.jriver.titles("Kitchen")


def test_playlist_plays_as_saved(app, alexa):
    r = alexa.say("PlaylistIntent", "sunday morning")
    assert r.started
    assert app.jriver.zone("Kitchen").playlist == app.jriver.playlists[0]["keys"]
    assert app.jriver.calls_to("Playback/PlayPlaylist")


def test_playlist_shared_name_asks_by_folder(app, alexa):
    r = alexa.say("PlaylistIntent", "road trip")
    assert r.ends is not True, r
    assert "by" in r.ssml.lower()
    r = alexa.say("ByArtistIntent", "smartlist", new=False)
    assert r.started, r
    assert app.jriver.zone("Kitchen").playlist == app.jriver.playlists[4]["keys"]


def test_playlist_reprompt_matches_question(app, alexa):
    """After "Say by, then the folder", the reprompt should not ask for an artist."""
    r = alexa.say("PlaylistIntent", "road trip")
    assert "artist" not in r.reprompt.lower(), r.reprompt


def test_playlist_global_shuffle_applies(app, alexa):
    sp = app.saved_playlists
    data = sp.main_settings()
    data["all"] = "1"
    data["all_row"]["shuffle"] = "1"
    sp.set_main_settings(data)
    alexa.say("PlaylistIntent", "road trip")
    alexa.say("ByArtistIntent", "playlist", new=False)
    z = app.jriver.zone("Kitchen")
    assert sorted(z.playlist) == sorted(app.jriver.playlists[1]["keys"])
    assert not app.jriver.calls_to("Playback/PlayPlaylist"), "shuffled lists are sent by key, not played as saved"


def test_playlist_device_own_settings(app, alexa):
    sp, v = app.saved_playlists, app.voice
    own = sp.blank()
    own["all"] = "1"
    own["all_row"]["nonstop"] = "tracks"
    v.set_own_settings(KITCHEN, True)
    v.set_device_page(KITCHEN, "saved", own)
    alexa.say("PlaylistIntent", "sunday morning")
    entry = app.engine.NONSTOP_ZONES.get("10002")
    assert entry and entry.get("saved_cfg", {}).get("using") == "tracks"
    alexa.say("PlaylistIntent", "sunday morning", device=LOUNGE)
    assert "10001" not in app.engine.NONSTOP_ZONES, "Lounge copies Windows (Main), which has Non-stop off"


# --- builds -------------------------------------------------------------------------------

def test_songs_by(app, alexa):
    r = alexa.say("SongsByIntent", "the beatles")
    assert r.started
    logs = alexa.run_jobs()
    assert logs and logs[0].has("Done:"), logs[0].text() if logs else ""
    titles = app.jriver.titles("Kitchen")
    assert titles and all(t.startswith("The Beatles") for t in titles)


def test_music_like(app, alexa):
    r = alexa.say("MusicLikeIntent", "the beatles")
    assert r.started
    log = alexa.run_jobs()[0]
    assert log.has("Done:"), log.text()
    assert len(app.jriver.zone("Kitchen").playlist) >= 20


def test_tracks_like_known_song(app, alexa):
    r = alexa.say("TracksLikeIntent", "here comes the sun")
    assert r.started
    log = alexa.run_jobs()[0]
    assert log.has("Done:"), log.text()
    assert app.jriver.zone("Kitchen").playlist


def test_tracks_like_shared_title_asks(app, alexa):
    app.jriver.tracks.append(dict(app.jriver.tracks[0], Key="9001", Name="Yesterday", Artist="Ray Charles",
                                  Album="Ray Sings", **{"Album Artist (auto)": "Ray Charles"}))
    app.jriver.by_key["9001"] = app.jriver.tracks[-1]
    r = alexa.say("TracksLikeIntent", "yesterday")
    assert "Which one" in r.ssml, r
    r = alexa.say("ByArtistIntent", "ray charles", new=False)
    assert r.started, r


def test_tracks_like_this_means_more_like_this(app, alexa):
    app.jriver.play("Kitchen", [app.jriver.key_of("The Beatles", "Something")])
    r = alexa.say("TracksLikeIntent", "this")
    assert r.started, r
    assert alexa.jobs and "more like" in alexa.jobs[0][1]


def test_genre(app, alexa):
    r = alexa.say("GenreIntent", "sunday morning coffee")
    assert r.started
    log = alexa.run_jobs()[0]
    assert log.has("Done:"), log.text()


def test_genre_needs_key(app, alexa):
    app.set_env(ANTHROPIC_API_KEY="")
    r = alexa.say("GenreIntent", "jazz")
    assert "Anthropic key" in r.ssml


def test_busy_says_pending(app, alexa):
    alexa.busy[0] = True
    app.voice._running[0] = "Speakers"   # another zone's build is running
    r = alexa.say("MusicLikeIntent", "queen")
    assert "pending" in r.ssml.lower(), r


def test_newer_command_takes_over(app, alexa):
    alexa.say("MusicLikeIntent", "queen")
    alexa.say("MusicLikeIntent", "the hollies")
    logs = alexa.run_jobs()
    assert logs[0].has("newer voice command"), logs[0].text()
    assert logs[1].has("Done:")


# --- zone commands --------------------------------------------------------------------------

def test_who_is_this(app, alexa):
    app.jriver.play("Kitchen", [app.jriver.key_of("Kinks, The", "Waterloo Sunset")])
    r = alexa.say("WhoIsThisIntent")
    assert "Waterloo Sunset by The Kinks, from Something Else" in r.ssml, r


def test_who_is_this_compilation(app, alexa):
    app.jriver.play("Kitchen", [app.jriver.key_of("Various Artists", "Petula Clark - Downtown")])
    r = alexa.say("WhoIsThisIntent")
    assert "Downtown by Petula Clark" in r.ssml, r


def test_skip(app, alexa):
    keys = app.jriver.zone("Kitchen")
    app.jriver.play("Kitchen", app.jriver.playlists[0]["keys"])
    r = alexa.say("SkipIntent")
    assert r.started
    assert app.jriver.zone("Kitchen").pos == 1


def test_skip_at_end(app, alexa):
    app.jriver.play("Kitchen", app.jriver.playlists[0]["keys"][:1])
    r = alexa.say("SkipIntent")
    assert "Nothing to skip to" in r.ssml


def test_nothing_playing(app, alexa):
    r = alexa.say("WhoIsThisIntent")
    assert "Nothing's playing on Kitchen" in r.ssml


def test_more_like_this_keeps_current_track(app, alexa):
    first = app.jriver.key_of("The Beatles", "Something")
    app.jriver.play("Kitchen", [first, app.jriver.key_of("Queen", "Somebody To Love")])
    r = alexa.say("MoreLikeThisIntent")
    assert r.started
    log = alexa.run_jobs()[0]
    z = app.jriver.zone("Kitchen")
    assert z.playlist[0] == first and z.pos == 0, log.text()
    assert len(z.playlist) > 2


def test_jriver_down(app, alexa):
    app.jriver.up = False
    app.engine._ZONE_CACHE = None if hasattr(app.engine, "_ZONE_CACHE") else None
    r = alexa.say("WhoIsThisIntent")
    assert "JRiver" in r.ssml, r
