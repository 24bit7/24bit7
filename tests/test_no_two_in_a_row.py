"""
No two by the same artist in a row (27 Oct 2026, Ben): every built playlist is spread so the same artist
never plays twice running where it can be avoided, moving as little as it can. Where it can't be avoided
the repeats stay. Artist's Top Tracks, albums, songs and the user's own JRiver playlists keep their order.
"""

import json

import pytest


@pytest.fixture
def lib(app):
    """Tracks by A, B, C and 'Bob Marley' / 'Bob Marley & The Wailers', keyed A1, A2 and so on."""
    j = app.jriver
    template = next(r for r in j.tracks if r["Genre"] == "Rock")
    names = {"A": "Artist Aye", "B": "Artist Bee", "C": "Artist Cee", "M": "Bob Marley",
             "W": "Bob Marley & The Wailers"}
    for letter, artist in names.items():
        for n in range(1, 6):
            row = dict(template, Key=f"{letter}{n}", Artist=artist, Name=f"{artist} song {n}",
                       Album=f"{artist} album", **{"Album Artist (auto)": artist})
            j.tracks.append(row)
            j.by_key[row["Key"]] = row
    app.library.load()
    return app.engine


def _letters(keys):
    return " ".join(k[0] for k in keys)


def test_a_pair_is_split(lib):
    assert lib.spread_artists(["A1", "A2", "B1"]) == ["A1", "B1", "A2"]


def test_the_order_barely_changes(lib):
    assert lib.spread_artists(["A1", "B1", "B2", "C1", "A2"]) == ["A1", "B1", "C1", "B2", "A2"]


def test_repeats_stay_when_it_cant_be_done(lib):
    assert _letters(lib.spread_artists(["A1", "A2", "A3", "B1"])) == "A B A A"


def test_an_artist_with_over_half_goes_first(lib):
    assert _letters(lib.spread_artists(["B1", "A1", "A2"])) == "A B A"


def test_a_fast_start_track_stays_first(lib):
    assert _letters(lib.spread_artists(["B1", "A1", "A2", "A3"], keep="B1")) == "B A A A"
    assert _letters(lib.spread_artists(["A1", "A2", "A3", "B1", "B2"], keep="A1")) == "A B A B A"


def test_a_drift_round_is_checked_against_the_track_before(lib):
    assert lib.spread_artists(["A2", "B1"], after="A1") == ["B1", "A2"]


def test_a_band_credit_counts_as_its_first_act(lib):
    assert _letters(lib.spread_artists(["M1", "W1", "A1"])) == "M A W"


def test_an_ai_playlist_has_no_two_in_a_row(lib, app, monkeypatch):
    app.set_env(VIBE_TRACK_COUNT="12", VIBE_PER_ARTIST="4", DRIFT_VIBE="0")
    picks = [{"artist": app.jriver.by_key[f"{letter}{n}"]["Artist"], "track": app.jriver.by_key[f"{letter}{n}"]["Name"]}
             for letter in "ABC" for n in range(1, 5)]   # grouped by artist: A A A A B B B B C C C C
    app.ai.script.append((json.dumps(picks), "end_turn"))
    monkeypatch.setattr(lib.random, "shuffle", lambda keys: None)   # keep the AI's grouped order
    r = app.Lines()
    lib.create_vibe_playlist("anything", report=r)
    sent = [str(k) for k in app.jriver.zone("Speakers").playlist]
    assert len(sent) == 12, r.text()
    assert all(a[0] != b[0] for a, b in zip(sent, sent[1:])), _letters(sent)


def test_a_non_stop_top_up_is_checked_against_the_zone(lib, app, monkeypatch):
    """The top-up's first track mustn't repeat the artist the zone's Playing Now ends on."""
    app.jriver.play("Speakers", ["B1", "A1"])
    monkeypatch.setattr(lib, "NONSTOP_APPEND", True)
    monkeypatch.setattr(lib, "nonstop_held", lambda zone: None)
    lib.send_to_jriver(["A2", "C1"], zone_name="Speakers", report=app.Lines())
    assert app.jriver.zone("Speakers").playlist == ["B1", "A1", "C1", "A2"]
