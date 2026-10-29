"""
Issue #12 (29 Oct 2026): "only ACDC" by voice found no artist, as the tag is AC/DC ('ac dc' once the slash
goes) and Alexa never writes the slash. A look through Ben's library found two more gaps in the rules every
name comparison shares: a straight apostrophe left a gap and a curly one didn't, so Jane's Addiction was two
artists, and "Guns and Roses" missed Guns N' Roses. The names here are the awkward ones from his library.
"""

import pytest

from test_voice import alexa, KITCHEN   # noqa: F401 (the fixture)

ARTISTS = ["AC/DC", "Guns N' Roses", "Salt-N-Pepa", "Rag 'n' Bone Man", "Youssou N'Dour", "Jane's Addiction",
           "D'Angelo", "Gus Gus", "N.W.A.", "M.I.A.", "Led Zeppelin"]


@pytest.fixture
def lib(app):
    j = app.jriver
    template = next(r for r in j.tracks if r["Genre"] == "Rock")
    for n, artist in enumerate(ARTISTS):
        row = dict(template, Key=str(97000 + n), Artist=artist, Name=f"{artist} song", Album=f"{artist} album",
                   **{"Album Artist (auto)": artist})
        j.tracks.append(row)
        j.by_key[row["Key"]] = row
    app.library.load()
    return app.library


@pytest.mark.parametrize("heard, artist", [
    ("ACDC", "AC/DC"), ("chill acdc", "AC/DC"), ("AC DC", "AC/DC"),
    ("guns and roses", "Guns N' Roses"), ("guns n roses", "Guns N' Roses"),
    ("salt and pepa", "Salt-N-Pepa"), ("rag and bone man", "Rag 'n' Bone Man"),
    ("youssou n'dour", "Youssou N'Dour"), ("youssou ndour", "Youssou N'Dour"),
    ("janes addiction", "Jane's Addiction"), ("jane’s addiction", "Jane's Addiction"),
    ("dangelo", "D'Angelo"), ("gusgus", "Gus Gus"), ("nwa", "N.W.A."), ("m i a", "M.I.A."),
])
def test_only_finds_the_artist(lib, heard, artist):
    assert lib.artist_in_text(heard)[0] == artist


def test_the_mood_words_are_kept(lib):
    assert lib.artist_in_text("chill acdc") == ("AC/DC", "chill")


def test_ordinary_words_find_no_artist(lib):
    for heard in ("rainy sunday jazz", "chill", "late night driving", "feel good"):
        assert lib.artist_in_text(heard) == (None, ""), heard


def test_apostrophes_compare_the_same(lib):
    assert lib.norm("Jane's Addiction") == lib.norm("Jane’s Addiction") == "janes addiction"
    assert lib.norm("Rock'n'Roll") == lib.norm("Rock 'n' Roll") == lib.norm("rock and roll") == "rock roll"
    assert lib.norm("Youssou N'Dour") == "youssou ndour", "his N isn't 'and'"
    assert lib.norm("N.W.A") == "nwa", "initials keep their N"


def test_only_acdc_by_voice(app, lib, alexa):
    r = alexa.say("OnlyIntent", "ACDC")
    assert r.started, r
