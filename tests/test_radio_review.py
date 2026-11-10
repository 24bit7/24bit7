"""
Radio, reviewed with Ben (7 Nov 2026): an agreeing artist another station fits over twice as well is left out
of a round; your own most played come first as pillars, the canon filling the gap; a half that's a copy of its
station gives way to its own halves; a pillar's own songs come at random from its best known five; an analysis
from before these rules is cut again at the next press. And Edit Pillars: add, remove (from the halves too),
Restore, at least three, kept through a Re-analyse.
"""

from collections import Counter

import pytest

from test_radio import radio, play_counts, EVERYONE  # noqa: F401  (the fixture and the fake world's plays)


def view_of(owned_plays):
    return {k: {"name": k.title(), "plays": p, "owned": 9, "genres": Counter(), "named": 0}
            for k, p in owned_plays.items()}


def test_your_own_most_played_come_first_and_the_canon_fills(radio, monkeypatch):
    own = {f"own{i:02}": 100 - i for i in range(15)}
    canon = [f"canon{i:02}" for i in range(15)]
    view = view_of(dict(own, **{c: 1 for c in canon}))
    monkeypatch.setattr(radio, "_canon", lambda genres, view, owned_ok, report: list(canon))
    picked = [n.lower() for n in radio.pillars_for(list(own), Counter(), view, print)]
    assert len(picked) == 20
    assert picked[:12] == [f"own{i:02}" for i in range(12)], picked
    assert picked[12:] == canon[:8], "eight of the canon after"
    few = {f"own{i:02}": 100 - i for i in range(4)}
    picked = [n.lower() for n in radio.pillars_for(list(few), Counter(), view_of(dict(few, **{c: 1 for c in canon})),
                                                   print)]
    assert picked[:4] == list(few) and len(picked) == 19, "the canon fills what your own can't"


def lane(lid, pillars, children=()):
    return {"id": lid, "name": lid, "pillars": list(pillars), "children": list(children)}


def test_a_half_thats_a_copy_gives_way_to_its_own_halves(radio):
    names = [f"a{i}" for i in range(20)]
    parent = lane("1", names)
    grandkids = [lane("1ba", names[:10] + ["g1", "g2"]), lane("1bb", ["x1", "x2", "x3"])]
    copy = lane("1b", names[:16] + ["c1", "c2", "c3", "c4"], grandkids)   # sixteen of twenty: a copy
    blues = lane("1a", ["b1", "b2", "b3", "b4"])
    assert radio.is_copy(copy, parent) and not radio.is_copy(blues, parent)
    assert [x["id"] for x in radio.without_copies(parent, [blues, copy])] == ["1a", "1ba", "1bb"]
    plain = lane("1b", copy["pillars"])   # a copy with no halves of its own stays
    assert [x["id"] for x in radio.without_copies(parent, [blues, plain])] == ["1a", "1b"]


def two_stations(radio, monkeypatch, tags):
    result = {"lanes": [{"id": "1", "name": "Rock", "pillars": ["P1", "P2", "P3"], "children": [],
                         "centroid": {"rock": 1.0, "classic rock": 0.6}},
                        {"id": "2", "name": "Electronic", "pillars": ["E1", "E2", "E3"], "children": [],
                         "centroid": {"electronic": 1.0, "ambient": 0.7}}], "version": radio.ANALYSIS_VERSION}
    store = {radio.ANALYSIS_KEY: result, radio.TAGS_KEY: dict(tags)}
    monkeypatch.setattr(radio, "_meta", lambda key, default: store.get(key, default))
    monkeypatch.setattr(radio, "_set_meta", lambda key, value: store.__setitem__(key, value))
    return result, store


def test_an_artist_another_station_fits_better_is_left_out(radio, monkeypatch, app):
    tags = {"queen": [("rock", 100), ("classic rock", 80)], "moby": [("electronic", 100), ("ambient", 60)],
            "gorillaz": [("electronic", 70), ("rock", 60), ("alternative", 50)]}
    result, store = two_stations(radio, monkeypatch, tags)
    fits = radio.fitter(result["lanes"][1])
    assert not fits("Queen"), "Rock fits Queen far better than Electronic"
    assert fits("Moby") and fits("Gorillaz"), "near enough"
    assert fits("Nobody Knows"), "no genres: nothing says where it belongs"
    asked = []

    def lastfm(params):
        asked.append(params["artist"])
        return {"toptags": {"tag": [{"name": "classic rock", "count": 100}]}}
    monkeypatch.setattr(radio, "_lastfm", lastfm)
    fits.learn(["Nobody Knows", "Queen"])
    assert asked == ["Nobody Knows"], "asks only about the ones not yet known"
    assert not fits("Nobody Knows") and "nobody knows" in store[radio.TAGS_KEY], "kept for next time"
    fits.learn(["Nobody Knows"])
    assert asked == ["Nobody Knows"], "never twice"


def test_a_round_leaves_out_what_doesnt_fit_and_says_so(app, radio, monkeypatch):
    """The guard for find(): Queen agrees with every pillar, but Rock fits it, so an Electronic round leaves it out."""
    play_counts(app, EVERYONE)
    result, _store = two_stations(radio, monkeypatch, {"queen": [("rock", 100), ("classic rock", 90)]})
    station = dict(result["lanes"][1], pillars=["Pink Floyd", "Sigur Rós", "The Beatles"])
    e = app.engine
    monkeypatch.setattr(e, "blended_similar_artists",
                        lambda artist, limit=30, report=None: ([("Queen", 1), ("Jimi Hendrix", 1)], "x"))
    r = app.Lines()
    picks, circle = radio.find(station, r)
    artists = {app.jriver.by_key[str(k)]["Artist"] for k in picks}
    assert "Queen" not in artists, r.text()
    assert "Jimi Hendrix" in artists, "an artist with no genres known is kept"
    assert r.has("Left out 1 agreeing artist whose genres don't fit Electronic: Queen."), r.text()


def test_a_pillars_own_songs_come_at_random_from_its_best_known_five(app, radio, monkeypatch):
    play_counts(app, EVERYONE)
    calls = []

    def owned_top(artist, have, played, limit, pool=None, **more):
        calls.append((artist, limit, pool))
        return []
    monkeypatch.setattr(radio, "_owned_top", owned_top)
    monkeypatch.setattr(app.engine, "blended_similar_artists", lambda artist, limit=30, report=None: ([], "x"))
    radio.find({"id": "1", "name": "Rock", "pillars": ["The Beatles", "Queen", "The Hollies"], "centroid": {}},
               app.Lines())
    pillar_calls = [c for c in calls if c[0] in ("The Beatles", "Queen", "The Hollies")]
    assert pillar_calls and all(c[1] == 2 and c[2] == radio.PILLAR_SONGS == 5 for c in pillar_calls), pillar_calls


def test_an_older_analysis_is_cut_again_at_the_next_press(app, radio, monkeypatch):
    import buttons
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    result = radio.analysis()
    result.pop("version")
    radio._set_meta(radio.ANALYSIS_KEY, result)
    assert radio.outdated()
    monkeypatch.setattr(radio, "build", lambda lane_id, report=print: report(f"built {lane_id}"))
    r = app.Lines()
    b, _ = buttons.add_from_choice(("template", "radio"))
    buttons.run_radio(b, report=r)
    assert r.has("Radio: making the stations again with this version's rules."), r.text()
    assert not radio.outdated() and radio.analysis()["version"] == radio.ANALYSIS_VERSION
    assert r.has("built "), r.text()


@pytest.fixture
def stations(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    return radio


def test_edit_pillars_add_remove_restore(app, stations):
    radio = stations
    first = radio.lanes()[0]
    before = list(first["pillars"])
    assert len(before) > 3
    gone = before[0]
    assert radio.remove_pillar(first["id"], gone) is None
    assert gone not in radio.lane(first["id"])["pillars"]
    for half in radio.lanes(include_children=True):
        if half["id"].startswith(first["id"]):
            assert gone not in half["pillars"], "removed from the halves too"
    assert radio.edited(radio.lane(first["id"]))
    assert radio.add_pillar(first["id"], "David Guetta") is None
    now = radio.lane(first["id"])
    assert now["pillars"][-1] == "David Guetta" and app.engine.artist_key("David Guetta") in radio.added(now)
    radio.analyse(app.Lines())   # a Re-analyse keeps them
    again = next(x for x in radio.lanes() if x.get("key") == first.get("key"))
    assert gone not in again["pillars"] and "David Guetta" in again["pillars"]
    radio.restore_pillars(again["id"])
    back = radio.lane(again["id"])
    assert back["pillars"] == back["auto_pillars"] and gone in back["pillars"] and not radio.edited(back)


def test_a_removed_artist_doesnt_come_back_by_itself_and_three_stay(app, stations, monkeypatch):
    radio = stations
    first = radio.lanes()[0]
    names = list(first["pillars"])
    for n in names[:-3]:
        assert radio.remove_pillar(first["id"], n) is None
    assert radio.remove_pillar(first["id"], names[-1]) == \
        "A station needs at least 3 pillars, since each round starts from 3."
    assert len(radio.lane(first["id"])["pillars"]) == 3
    # an artist removed doesn't rejoin as a new pillar
    result = radio.analysis()
    result["known"] = [k for k in result["known"] if k != app.engine.artist_key(names[0])]
    radio._set_meta(radio.ANALYSIS_KEY, result)
    radio.join_new_artists(app.Lines())
    assert names[0] not in radio.lane(first["id"])["pillars"]


def test_library_artists_lists_your_artists_not_compilations(app, stations):
    names = [n for n, _count in stations.library_artists()]
    assert "Pink Floyd" in names and "Various Artists" not in names
    assert names == sorted(names, key=str.lower)
