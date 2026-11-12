"""
No waiting in silence (Ben, 10 Nov 2026). Similar Artists, Similar Tracks, AI Playlist and Top Tracks already
started their first track while the rest was found; Play & Embellish and Radio built the whole playlist first,
and an AI Playlist could start nothing until the AI's whole list was back. Now, on a stopped zone:
  Play & Embellish   the playlist's own first track plays at once (it leads whatever is added)
  Radio              the round's first pillar song plays at once
  AI Playlist        a quick first call finds an opener while the main call finds the list
and the fast start tells Multiroom a playlist has started. Nothing here opens a window.
"""

from types import SimpleNamespace

from test_radio import EVERYONE, play_counts
from test_radio_playlist import made_radio, radio  # noqa: F401  (the radio fixture)

ROAD_TRIP = {"ID": "202", "Name": "Road Trip"}


def first_play(app):
    """The keys of the first call that started a zone playing (a call with a Location only queues), or None."""
    plays = [p for p in app.jriver.calls_to("Playback/PlayByKey") if "Location" not in p]
    return str(plays[0]["Key"]) if plays else None


# --- Play & Embellish -------------------------------------------------------------------------------------

def test_embellish_plays_the_playlists_first_track_at_once_and_the_rest_follows(app):
    import embellish
    j = app.jriver
    yours = j.playlists[1]["keys"]
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, "ordered", "p50", r)
    assert first_play(app) == yours[0], "the first track started by itself, before anything was found"
    z = j.zone("Speakers").playlist
    assert z[0] == yours[0] and len(z) == 15 and len(set(z)) == 15, (z, r.text())
    assert [k for k in z if k in yours] == yours, "the rest followed it in, your order kept"


def test_embellish_on_a_playing_zone_queues_as_before(app):
    import embellish
    j = app.jriver
    yours = j.playlists[1]["keys"]
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, "ordered", "p50", r)
    assert first_play(app) is None, "music is already playing, so nothing starts early"
    assert r.has("Queued in Speakers after the current track"), r.text()
    assert j.zone("Speakers").playlist[1] == yours[0]


def test_a_one_artist_playlist_starts_too_now_it_builds_a_circle(app):
    """Before 12 Nov 2026 one artist had nothing to build, so nothing started."""
    import embellish
    r = app.Lines()
    embellish.embellish({"ID": "203", "Name": "60s Smartlist"}, None, "p50", r)
    assert r.has("Every track on 60s Smartlist is by The Beatles, so the circle is"), r.text()
    assert first_play(app) is not None


def test_embellish_in_review_starts_nothing(app):
    import embellish
    e = app.engine
    e.REVIEW_MODE = True
    try:
        e.review_reset()
        embellish.embellish(ROAD_TRIP, None, "p50", app.Lines())
    finally:
        e.REVIEW_MODE = False
    assert first_play(app) is None and not app.jriver.zone("Speakers").playlist


# --- Radio --------------------------------------------------------------------------------------------------

def test_radio_plays_a_pillar_song_at_once_and_the_round_follows(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    j = app.jriver
    opener = first_play(app)
    assert opener and "," not in opener, "one track started by itself"
    pillars = next(x for x in r if "Pillars this round:" in x)
    assert j.by_key[opener]["Artist"] in pillars, (j.by_key[opener]["Artist"], pillars)
    z = j.zone("Speakers").playlist
    assert z[0] == opener and len(z) > 1 and len(set(z)) == len(z), (z, r.text())
    entry = app.engine.NONSTOP_ZONES[j.zone("Speakers").id]
    assert opener in entry["keys"] and entry["kind"] == "radio", "Non-stop knows the opener was sent"


def test_radio_on_a_playing_zone_starts_nothing_early(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    assert first_play(app) is None
    assert r.has("Queued in Speakers after the current track"), r.text()


# --- AI Playlist --------------------------------------------------------------------------------------------

def others(app):
    return [r for r in app.jriver.tracks if r["Artist"] != "Various Artists"]


def test_ai_playlist_opens_with_a_quick_pick_while_the_full_list_is_found(app):
    e, j = app.engine, app.jriver
    row = others(app)[1]   # the fake's full list is every other track from the first, so this isn't in it
    app.ai.opener = [("Nobody", "Nothing"), (row["Artist"], row["Name"]), (others(app)[3]["Artist"], others(app)[3]["Name"])]
    r = app.Lines()
    e.create_vibe_playlist("late night drive", report=r)
    assert r.has(f"Playing first, while the AI finds the rest: {row['Artist']} - {row['Name']}"), r.text()
    assert first_play(app) == row["Key"], "the first of its picks that's in the library started"
    z = j.zone("Speakers").playlist
    assert z[0] == row["Key"] and len(z) > 1 and len(set(z)) == len(z), (z, r.text())
    quick = [c for c in app.ai.calls if "to open a playlist" in c[1]]
    assert len(quick) == 1 and quick[0][0] == e.ai_model("quick"), quick


def test_an_opener_the_full_list_also_names_is_sent_once(app):
    e, j = app.engine, app.jriver
    row = others(app)[0]   # in the fake's full list too
    app.ai.opener = [(row["Artist"], row["Name"])]
    e.create_vibe_playlist("late night drive", report=app.Lines())
    z = j.zone("Speakers").playlist
    assert z[0] == row["Key"] and z.count(row["Key"]) == 1, z


def test_no_opener_in_the_library_and_the_playlist_builds_as_before(app):
    e, j = app.engine, app.jriver
    app.ai.opener = [("Nobody", "Nothing")]
    r = app.Lines()
    e.create_vibe_playlist("late night drive", report=r)
    assert not r.has("Playing first, while the AI finds the rest"), r.text()
    assert j.zone("Speakers").playlist, r.text()


def test_the_quick_call_is_only_made_when_it_can_start_something(app):
    e, j = app.engine, app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    e.create_vibe_playlist("late night drive", report=app.Lines())
    assert not [c for c in app.ai.calls if "to open a playlist" in c[1]], "music is playing: one call, as before"
    stopped = SimpleNamespace(zone="10001", started=False)
    assert e.vibe_opener_wanted(stopped, None, None)
    assert not e.vibe_opener_wanted(SimpleNamespace(zone=None, started=False), None, None), "nowhere to start it"
    assert not e.vibe_opener_wanted(SimpleNamespace(zone="10001", started=True), None, None), "something already started"
    assert not e.vibe_opener_wanted(stopped, "a prompt of its own", None), "Steer asks in its own words"
    assert not e.vibe_opener_wanted(stopped, None, object()), "and has its BPM check"
    app.set_env(USE_AI="0")
    assert not e.vibe_opener_wanted(stopped, None, None)
    app.set_env(USE_AI="1", AI_PROVIDER="ollama", OLLAMA_MODEL="gemma3:4b")
    assert not e.vibe_opener_wanted(stopped, None, None), "a local model takes one request at a time"


# --- Multiroom ----------------------------------------------------------------------------------------------

def test_a_fast_start_on_the_leader_asks_the_speakers_to_follow(app):
    e, j = app.engine, app.jriver
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Sonos", MULTIROOM_FOLLOWER="Speakers",
                OUTPUT_TARGET="multiroom")
    asked = []
    e.MULTIROOM_HOOK = lambda: asked.append(1)
    key = j.key_of("The Beatles", "Something")
    fast = e.FastStart(None, app.Lines())
    fast.play(key)
    assert fast.started and j.zone("Sonos").playlist == [key]
    assert asked == [1], "the Speakers join at the first track, not when the rest arrives"
