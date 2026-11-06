"""
Radio (Ben, 5 Nov 2026): lanes from what you play, pillars from the sources' canon and your own most played,
builds by Consensus over random pillars, and Non-stop carrying on from pillars. The fake world is small, so
the thresholds are lowered; its Last.fm knows sixties rock, folk and a few others (fakes.TAGS).
"""

import pytest


@pytest.fixture
def radio(app, monkeypatch):
    import radio
    for name, value in (("MIN_PLAYS", 1), ("MIN_ARTISTS", 4), ("LANE_MIN", 2), ("PILLAR_OWNED", 2),
                        ("PILLARS_TO_SPLIT", 2), ("LANES_MAX", 3)):
        monkeypatch.setattr(radio, name, value)
    monkeypatch.setattr(radio.time, "sleep", lambda s: None)
    return radio


def play_counts(app, counts):
    """counts: {artist as tagged: plays per track}."""
    for r in app.jriver.tracks:
        if r["Artist"] in counts:
            r["Number Plays"] = str(counts[r["Artist"]])
    import library
    library.load()


EVERYONE = {"The Beatles": 5, "The Hollies": 3, "Kinks, The": 3, "The Byrds": 2, "Badfinger": 2,
            "George Harrison": 2, "The Rolling Stones": 4, "Simon & Garfunkel": 3, "Jimi Hendrix": 2, "Queen": 3,
            "Pink Floyd": 4, "Sigur Rós": 2, "David Guetta": 1, "Various Artists": 9}


def test_the_genre_rule_sources_first_then_your_tag_then_nothing(radio):
    row = {"name": "X", "plays": 9, "owned": 3, "genres": __import__("collections").Counter({"Rock/Pop": 3}), "named": 0}
    assert radio.genres_for("x", row, {"x": [("seen live", 100), ("shoegaze", 80)]}) == ({"shoegaze": 80}, "sources")
    assert radio.genres_for("x", row, {"x": []}) == ({"rock/pop": 100}, "own"), "no source knows it: your tag"
    row["genres"] = __import__("collections").Counter()
    assert radio.genres_for("x", row, {}) == ({}, "none"), "neither: not a data point"


def test_compilations_are_never_pillars(radio):
    assert radio.is_compilation({"name": "Various Artists", "owned": 2, "named": 0})
    assert radio.is_compilation({"name": "Buddha Bar", "owned": 1078, "named": 1078}), "every track 'Artist - Title'"
    assert not radio.is_compilation({"name": "Moby", "owned": 149, "named": 2})
    assert radio.is_compilation({"name": "Dope;Angus Stone", "owned": 6, "named": 0}), "two acts in one tag"


def test_clustering_finds_the_two_families(radio):
    vecs = [radio._unit(v) for v in ({"rock": 1, "classic rock": 1}, {"rock": 1, "classic rock": 0.8},
                                     {"classic rock": 1, "rock": 0.6}, {"ambient": 1, "electronic": 1},
                                     {"electronic": 1, "ambient": 0.7})]
    merges = radio.cluster(vecs)
    assert len(merges) == 4
    kids, leaves = radio._tree(5, merges)
    groups = sorted(sorted(leaves[r]) for r in radio._cut(5, merges, 2))
    assert groups == [[0, 1, 2], [3, 4]], groups


def test_radio_rests_until_theres_enough_played(app, radio):
    play_counts(app, {"The Beatles": 5, "Queen": 2})
    r = app.Lines()
    result = radio.analyse(r)
    assert result["resting"] == {"have": 2, "need": 4} and not result["lanes"]
    assert r.has("Radio is resting: it needs 4 artists you've played 1 or more times, and there are 2 so far."), r.text()


def test_analysis_makes_lanes_with_pillars(app, radio):
    play_counts(app, EVERYONE)
    r = app.Lines()
    result = radio.analyse(r)
    assert result["lanes"], r.text()
    assert r.has("Genres from the sources for"), r.text()
    names = [x["name"] for x in result["lanes"]]
    assert len(names) == len(set(names)), names
    top = result["lanes"][0]
    assert "Classic Rock" in top["name"] or "Rock" in top["name"], names
    every_pillar = {p for x in radio.lanes(include_children=True) for p in x["pillars"]}
    assert "Various Artists" not in every_pillar, "a compilation is never a pillar"
    assert "David Guetta" not in every_pillar, "one track owned: under the pillar mark"
    assert app.web.calls and any(c[2].get("method") == "tag.gettopartists" for c in app.web.calls), "the canon"
    asked = sum(1 for c in app.web.calls if c[2].get("method") == "artist.gettoptags")
    radio.analyse(app.Lines())
    assert sum(1 for c in app.web.calls if c[2].get("method") == "artist.gettoptags") == asked, \
        "a Re-analyse only asks about artists it hasn't asked about before"


def test_a_build_plays_a_pillar_first_and_non_stop_carries_on(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    lane = radio.lanes()[0]
    r = app.Lines()
    radio.build(lane["id"], r)
    z = app.jriver.zone("Speakers").playlist
    assert z, r.text()
    assert r.has(f"Radio: {lane['name']}."), r.text()
    assert r.has("Pillars this round:") and r.has("Done:"), r.text()
    pillars = {app.engine.artist_key(p) for p in lane["pillars"]}
    assert app.engine.artist_key(app.jriver.by_key[z[0]]["Artist"]) in pillars, "a pillar song starts it"
    entry = app.engine.NONSTOP_ZONES[app.jriver.zone("Speakers").id]
    assert entry["origin"] == "radio" and entry["radio_lane"] == lane["id"]
    import nonstop
    assert nonstop.config_for("Speakers", entry) == {"on": True}, "Radio always plays on"
    before = list(z)
    app.jriver.zone("Speakers").pos = len(before) - 1
    r = app.Lines()
    nonstop._job(app.jriver.zone("Speakers").id, "Speakers", {})(r)
    after = app.jriver.zone("Speakers").playlist
    assert after[:len(before)] == before, "a top-up only adds"
    assert r.has("Speakers is on its last track, so Radio plays on."), r.text()
    assert not set(after[len(before):]) & set(before), "nothing it already sent"


def test_new_artists_join_a_lane_without_a_reanalyse(app, radio, monkeypatch):
    monkeypatch.setattr(radio, "tag_top_artists", lambda tag, limit=100: [])   # pillars from your plays alone
    play_counts(app, {k: v for k, v in EVERYONE.items() if k != "The Hollies"})
    radio.analyse(app.Lines())
    play_counts(app, EVERYONE)
    r = app.Lines()
    radio.join_new_artists(r)
    assert any("The Hollies" in x["pillars"] for x in radio.lanes()), r.text()
    assert r.has("Radio: The Hollies joins"), r.text()
