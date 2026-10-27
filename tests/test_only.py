"""
"Only" (27 Oct 2026): datdude asked for "chill Led Zeppelin" and got the Eagles and Massive Attack too, as the AI
Playlist spreads across artists on purpose. "Only" is its own command, so Genre is unchanged: the artist named in
the words must be one you own, and the AI chooses from that artist's tracks in the library and nothing else.
"""

import json

import pytest

from test_voice import alexa, KITCHEN   # noqa: F401 (the fixture)

ZEP = ["Stairway To Heaven", "Going To California", "Thank You", "Kashmir", "Tangerine", "Black Dog"]


@pytest.fixture
def lib(app):
    j = app.jriver
    template = next(r for r in j.tracks if r["Genre"] == "Rock")
    rows = [("Led Zeppelin", title) for title in ZEP] + [
        ("Chill", "Chill One"), ("Anthems", "Anthem One"), ("Roses", "Rose One"),
        ("Guns N' Roses", "November Rain"), ("Guns N' Roses", "Patience")]
    for n, (artist, title) in enumerate(rows):
        row = dict(template, Key=str(96000 + n), Artist=artist, Name=title, Album=f"{artist} album",
                   **{"Album Artist (auto)": artist})
        j.tracks.append(row)
        j.by_key[row["Key"]] = row
    app.library.load()
    return app.library


def test_the_artist_is_found_in_the_words(lib):
    assert lib.artist_in_text("chill Led Zeppelin") == ("Led Zeppelin", "chill")


def test_the_longest_name_wins(lib):
    assert lib.artist_in_text("epic guns n roses songs") == ("Guns N' Roses", "epic")


def test_a_tie_goes_to_the_artist_with_more_tracks(lib):
    assert lib.artist_in_text("queen anthems")[0] == "Queen"


def test_no_artist_named(lib):
    assert lib.artist_in_text("rainy sunday morning jazz") == (None, "")


def test_no_mood_leaves_nothing_over(lib):
    assert lib.artist_in_text("songs by led zeppelin") == ("Led Zeppelin", "")


def test_only_plays_that_artist_and_shows_the_ai_their_titles(app, lib):
    app.set_env(VIBE_TRACK_COUNT="20")
    app.ai.script.append((json.dumps(["Going To California", "Thank You", "Hotel California", "Tangerine"]),
                          "end_turn"))
    r = app.Lines()
    app.engine.create_only_playlist("chill Led Zeppelin", report=r)
    titles = app.jriver.titles("Speakers")
    assert sorted(titles) == ["Led Zeppelin - Going To California", "Led Zeppelin - Tangerine",
                              "Led Zeppelin - Thank You"], r.text()   # Hotel California isn't on the list
    prompt = app.ai.sent[-1]
    assert all(title in prompt for title in ZEP) and "chill Led Zeppelin" in prompt
    assert r.has("3 of 20"), r.text()


def test_only_with_no_artist_you_own_says_so(app, lib):
    r = app.Lines()
    app.engine.create_only_playlist("rainy sunday jazz", report=r)
    assert r.has("no artist in your library"), r.text()
    assert not app.ai.calls


def test_only_by_voice(app, lib, alexa):
    r = alexa.say("OnlyIntent", "chill led zeppelin")
    assert r.started, r
    assert alexa.jobs and "only chill led zeppelin" in alexa.jobs[0][1], alexa.jobs


def test_only_by_voice_with_no_artist_you_own(app, lib, alexa):
    r = alexa.say("OnlyIntent", "rainy sunday jazz")
    assert "couldn't find an artist you own" in r.ssml, r
    assert not alexa.jobs
