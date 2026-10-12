"""
The character rules every name comparison shares (accents, '$' as 's', '&' and '+'),
and near-miss titles, which only lookups by an already-matched artist may use.
Cases from the Tidal name-match test of 12 Oct 2026.
"""

import pytest


def test_shared_character_rules(app):
    e = app.engine
    assert e.fold_name_chars("JAŸ-Z") == "JAY-Z"
    assert e.fold_name_chars("Travi$ Scott") == "Travis Scott"
    assert e.fold_name_chars("Ke$ha") == "Kesha"
    assert e.fold_name_chars("$5 Bill") == "$5 Bill"               # money stays money
    assert e.fold_name_chars("Halcyon + On + On") == "Halcyon and On and On"


def test_artists_compare_alike_everywhere(app):
    e, lib = app.engine, app.library
    for a, b in (("Travi$ Scott", "Travis Scott"), ("Ke$ha", "Kesha"), ("JAŸ-Z", "JAY-Z")):
        assert e.artist_key(a) == e.artist_key(b)                   # source against source
        assert lib.norm(a) == lib.norm(b)                           # against the library


def test_titles_compare_alike_everywhere(app):
    e, lib = app.engine, app.library
    for a, b in (("Halcyon + On + On", "Halcyon And On And On"), ("Café del Mar", "Cafe del Mar")):
        assert e.clean_name(a) == e.clean_name(b)
        assert lib.norm(a) == lib.norm(b)


def test_existing_keys_unchanged(app):
    """These are cache keys in 24bit7.db: names the new rules don't touch keep their old key."""
    e = app.engine
    assert e.artist_key("Florence + the Machine") == e.artist_key("Florence & the Machine") == "florence & the machine"
    assert e.artist_key("Simon & Garfunkel") == "simon & garfunkel"
    assert e.clean_name("Girls & Boys") == "girls and boys"
    assert e.clean_name("Everlong (Acoustic Version)") == "everlong"


@pytest.mark.parametrize("a, b, alike", [
    ("Al of me", "All of Me", True),
    ("Song 2", "Song 3", False),
    ("Symphony No. 5", "Symphony No. 6", False),
    ("Everlong", "Everlong", True),
    ("Teardrop", "Angel", False),
])
def test_near_title(app, a, b, alike):
    assert app.engine.near_title(a, b) is alike


def stub_tidal(app, monkeypatch, catalogue):
    """Tidal's search, answering only queries it has listed: {query: [(id, [artists], title, version)]}."""
    e = app.engine
    rows = {r[0]: r for found in catalogue.values() for r in found}
    searched = []

    def search(query, kind):
        searched.append(query)
        return [r[0] for r in catalogue.get(query, [])]
    monkeypatch.setattr(e, "tidal_search_ids", search)
    monkeypatch.setattr(e, "tidal_track_details", lambda ids: [rows[i] for i in ids])
    return searched


def test_tidal_finds_plus_for_and(app, monkeypatch):
    stub_tidal(app, monkeypatch, {"Orbital Halcyon And On And On": [("1", ["Orbital"], "HALCYON + ON + ON", "")]})
    assert app.engine.tidal_track_id("Orbital", "Halcyon And On And On") == "1"


def test_tidal_near_miss_needs_the_same_artist(app, monkeypatch):
    stub_tidal(app, monkeypatch, {
        "Les Gammas Al of me": [("1", ["John Legend"], "All of Me", ""), ("2", ["Les Gammas"], "All of Me", "")]})
    assert app.engine.tidal_track_id("Les Gammas", "Al of me") == "2"


def test_tidal_exact_title_beats_a_near_miss(app, monkeypatch):
    stub_tidal(app, monkeypatch, {
        "Blur Song 2": [("1", ["Blur"], "Song 3", ""), ("2", ["Blur"], "Song 2", "")]})
    assert app.engine.tidal_track_id("Blur", "Song 2") == "2"


def test_tidal_never_takes_another_number(app, monkeypatch):
    stub_tidal(app, monkeypatch, {"Blur Song 2": [("1", ["Blur"], "Song 3", "")]})
    assert app.engine.tidal_track_id("Blur", "Song 2") is None


def test_tidal_searches_again_with_the_folded_artist(app, monkeypatch):
    searched = stub_tidal(app, monkeypatch, {"Travis Scott 3500": [("1", ["Travis Scott"], "3500", "")]})
    assert app.engine.tidal_track_id("Travi$ Scott", "3500") == "1"
    assert searched == ["Travi$ Scott 3500", "Travis Scott 3500"]


def test_tidal_no_second_search_when_nothing_folds(app, monkeypatch):
    searched = stub_tidal(app, monkeypatch, {})
    assert app.engine.tidal_track_id("Blur", "Song 2") is None
    assert searched == ["Blur Song 2"]
