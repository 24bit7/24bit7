"""
Radio and Top-Up by voice (Ben, 8 Nov 2026). "Radio folk" plays that station on the device's zone; "radio" alone
asks which of the last five played, numbered, and the answer is a name or "the second one". "Top up" asks what
with, and the next command goes into what's left of Playing Now instead of replacing it.
"""

import pytest

from test_voice import alexa, KITCHEN  # noqa: F401  (the voice fixture)
from test_radio import EVERYONE, play_counts


@pytest.fixture
def stations(app, monkeypatch):
    import radio
    for name, value in (("MIN_PLAYS", 1), ("MIN_ARTISTS", 4), ("LANE_MIN", 2), ("PILLAR_OWNED", 2),
                        ("PILLARS_TO_SPLIT", 2), ("LANES_MAX", 3)):
        monkeypatch.setattr(radio, name, value)
    monkeypatch.setattr(radio.time, "sleep", lambda s: None)
    play_counts(app, EVERYONE)
    radio.set_row(count=3)
    radio.analyse(app.Lines())
    assert len(radio.lanes()) >= 2, "the fake world needs two stations or more"
    return radio


def test_radio_alone_lists_the_stations_numbered_and_the_second_one_plays(app, alexa, stations):
    radio = stations
    r = alexa.say("RadioIntent")
    offered = radio.recent_lanes()
    assert "Which station? One, " in r.ssml and r.ends is not True, r
    assert radio.spoken_name(offered[1]) in r.ssml
    assert alexa.session.get("ask") == "station"
    r = alexa.say("StationIntent", "the second one", new=False)
    assert r.started, r
    log = alexa.run_jobs()[0]
    assert log.has(f"radio {offered[1]['name']}, to Kitchen"), log.text()
    assert app.jriver.zone("Kitchen").playlist, "the station plays in the device's zone"
    assert radio.recent_lanes()[0]["id"] == offered[1]["id"], "now the newest of the last five"


def test_radio_by_name_finds_the_station_by_part_of_its_name(app, alexa, stations):
    radio = stations
    target = radio.lanes()[-1]
    part = target["name"].split(" / ")[0]
    r = alexa.say("RadioIntent", part.lower())
    assert r.started, r
    log = alexa.run_jobs()[0]
    assert log.has(f"radio {radio.match_station(part)['name']}"), log.text()


def test_a_station_nobody_has_asks_again_with_the_list(app, alexa, stations):
    r = alexa.say("RadioIntent", "polka")
    assert "couldn't find a station called polka" in r.ssml and "Which station? One," in r.ssml, r
    assert r.ends is not True and not alexa.jobs


def test_an_answer_out_of_turn_isnt_taken_for_a_station(app, alexa, stations):
    r = alexa.say("StationIntent", "folk")
    assert "didn't catch" in r.ssml and not alexa.jobs, r


def test_matching_rules(app, stations):
    radio = stations
    every = radio.lanes()
    assert radio.match_station("two", every)["id"] == every[1]["id"]
    assert radio.match_station("the first one", every)["id"] == every[0]["id"]
    assert radio.match_station("number nine", every) is None, "nine isn't an ordinal on the list"
    full = every[0]["name"]
    assert radio.match_station(full.replace(" / ", " ") + " station", every)["id"] == every[0]["id"]
    assert radio.match_station("zydeco", every) is None


def test_the_last_five_are_the_last_played_then_the_biggest(app, stations):
    radio = stations
    every = radio.lanes()
    radio.remember_played(every[-1])
    assert radio.recent_lanes()[0]["id"] == every[-1]["id"]
    assert {x["id"] for x in radio.recent_lanes()} == {x["id"] for x in every[:5]} | {every[-1]["id"]} \
        or len(every) > 5
    for x in every:
        radio.remember_played(x)
    assert len(radio.row()["recent"]) <= radio.RECENT_MAX


def test_no_stations_yet_says_how_to_make_them(app, alexa):
    r = alexa.say("RadioIntent", "folk")
    assert "Radio has no stations yet" in r.ssml and r.ends is True, r


def keys_of(app, n):
    return [row["Key"] for row in app.jriver.tracks][:n]


def test_top_up_then_music_like_joins_whats_left_of_playing_now(app, alexa):
    every = keys_of(app, 8)
    app.jriver.play("Kitchen", every, pos=2, state=2)
    r = alexa.say("TopUpIntent")
    assert "Top up with what?" in r.ssml and r.ends is not True, r
    assert alexa.session.get("top_up") is True
    r = alexa.say("MusicLikeIntent", "the beatles", new=False)
    assert r.started, r
    log = alexa.run_jobs()[0]
    assert log.has("as a Top-Up") and log.has("Top-Up:"), log.text()
    z = app.jriver.zone("Kitchen")
    assert z.playlist[:3] == every[:3] and z.pos == 2, "played and playing left alone"
    assert set(every[3:]) <= set(z.playlist), "the rest still to play is kept"
    assert app.engine.TOP_UP is False, "lasts the one build"


def test_without_top_up_a_voice_build_still_replaces(app, alexa):
    every = keys_of(app, 8)
    app.jriver.play("Kitchen", every, pos=2, state=2)
    alexa.say("MusicLikeIntent", "the beatles")
    alexa.run_jobs()
    assert not set(every[3:]) <= set(app.jriver.zone("Kitchen").playlist), "a voice build takes over"


def test_top_up_then_an_album_joins_instead_of_replacing(app, alexa):
    every = keys_of(app, 6)
    app.jriver.play("Kitchen", every, pos=1, state=2)
    alexa.say("TopUpIntent")
    r = alexa.say("AlbumIntent", "abbey road", new=False)
    assert r.started, r
    z = app.jriver.zone("Kitchen")
    assert z.playlist[:2] == every[:2] and set(every[2:]) <= set(z.playlist) and len(z.playlist) > len(every), z.playlist


def test_top_up_radio(app, alexa, stations):
    every = keys_of(app, 6)
    app.jriver.play("Kitchen", every, pos=1, state=2)
    alexa.say("TopUpIntent")
    r = alexa.say("RadioIntent", "the first one", new=False)
    assert r.started, r
    log = alexa.run_jobs()[0]
    assert log.has("Top-Up, radio") and log.has("Top-Up:"), log.text()
    assert app.jriver.zone("Kitchen").playlist[:2] == every[:2]


def test_the_model_has_the_new_intents(app, alexa):
    import json
    model = json.load(open(app.folder / "alexa" / "interaction_model.json", encoding="utf-8"))
    lm = model["interactionModel"]["languageModel"]
    names = {i["name"] for i in lm["intents"]}
    assert {"RadioIntent", "StationIntent", "TopUpIntent"} <= names
    assert any(x["name"] == "STATION" for x in lm["types"])
