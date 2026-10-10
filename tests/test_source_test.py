"""Test My Sources, the engine: running, scoring, storing, the sample, and the ready line."""

import importlib
import json
import time

SEEDS = [
    {"genre": "Rock", "tier": "famous", "artist": "Queen", "track": "Bohemian Rhapsody"},
    {"genre": "Rock", "tier": "famous", "artist": "The Beatles", "track": "Something"},
    {"genre": "Rock", "tier": "hidden", "artist": "Badfinger", "track": "Baby Blue"},
    {"genre": "Pop", "tier": "famous", "artist": "The Hollies", "track": "Bus Stop"},
    {"genre": "Pop", "tier": "hidden", "artist": "The Byrds", "track": "Turn! Turn! Turn!"},
]


def st(app):
    (app.folder / "source_test_seeds.json").write_text(json.dumps({"version": 1, "seeds": SEEDS}), encoding="utf-8")
    return importlib.import_module("source_test")


def test_quick_takes_one_famous_and_one_hidden_per_genre(app):
    s = st(app)
    assert len(s.load_seeds()) == 5
    assert [x["artist"] for x in s.load_seeds(quick=True)] == ["Queen", "Badfinger", "The Hollies", "The Byrds"]


def test_sources_to_test_follow_the_keys(app):
    s = st(app)
    t = s.sources_to_test()
    assert [c for c, _ in t["artists"]] == ["lastfm", "listenbrainz", "deezer", "youtube"]   # Tidal: no keys
    assert "ai" not in [c for c, _ in t["tracks"]]
    assert "ai" in [c for c, _ in s.sources_to_test(include_ai=True)["tracks"]]


def test_a_full_run(app):
    s = st(app)
    result = s.run(wait_for_builds=False)
    assert result["mode"] == "full" and len(result["seeds"]) == 5
    names = {r["source"] for r in result["rows"]}
    assert {"lastfm", "listenbrainz", "deezer", "youtube"} <= names
    lastfm = [r for r in result["rows"] if r["source"] == "lastfm" and r["section"] == "tracks"]
    assert len(lastfm) == 5 and all(r["answered"] and r["hits"] for r in lastfm)
    sc = result["scores"]["tracks"]["sources"]["lastfm"]
    assert 0 < sc["performance"] <= 100 and sc["best_at"]
    assert "Bohemian Rhapsody" not in json.dumps(result["rows"])   # counts only, no names


def test_the_seed_never_counts(app):
    s = st(app)
    seed = SEEDS[0]
    key = app.library.find_track_key(seed["artist"], seed["track"])
    assert key
    hits = s.library_hits("tracks", [(seed["artist"], seed["track"]), ("The Hollies", "Bus Stop")], seed)
    assert str(key) not in hits and len(hits) == 1
    assert s.library_hits("artists", ["Queen", "The Hollies"], seed) == [app.engine.artist_key("The Hollies")]


def test_artist_check_is_strict(app):
    s = st(app)
    assert s.owned_artist("Queen") and s.owned_artist("Queen & David Bowie")   # the lead artist counts
    assert not s.owned_artist("Queen Latifah")                                # a longer name doesn't


def test_every_source_is_scored_at_the_same_depth(app, monkeypatch):
    s = st(app)
    monkeypatch.setattr(s, "load_seeds", lambda quick=False: SEEDS[:1])
    monkeypatch.setattr(s, "sources_to_test", lambda include_ai=False: {
        "artists": [("lastfm", "Last.fm")], "tracks": [("lastfm", "Last.fm")]})
    long_tracks = [("Nobody", f"Song {i}") for i in range(45)]
    long_artists = [f"Nobody {i}" for i in range(35)]
    monkeypatch.setattr(s, "ask", lambda section, code, a, t:
                        ((long_artists if section == "artists" else long_tracks), 0.1))
    result = s.run(wait_for_builds=False)
    rows = {r["section"]: r for r in result["rows"]}
    assert rows["artists"]["returned"] == s.ARTIST_DEPTH and rows["artists"]["returned_all"] == 35
    assert rows["tracks"]["returned"] == s.TRACK_DEPTH and rows["tracks"]["returned_all"] == 45
    assert set(result["timing"]) == {"asking", "matching", "waiting"}
    assert any(line.startswith("Time: asking the sources") for line in s.report_lines(result))


def test_unique_counts_what_no_other_source_found(app, monkeypatch):
    s = st(app)
    monkeypatch.setattr(s, "load_seeds", lambda quick=False: SEEDS[:1])
    monkeypatch.setattr(s, "sources_to_test", lambda include_ai=False: {
        "artists": [], "tracks": [("lastfm", "Last.fm"), ("deezer", "Deezer")]})
    answers = {"lastfm": [("The Hollies", "Bus Stop"), ("Badfinger", "Baby Blue")],
               "deezer": [("The Hollies", "Bus Stop")]}
    monkeypatch.setattr(s, "ask", lambda section, code, a, t: (answers[code], 0.1))
    result = s.run(wait_for_builds=False)
    rows = {r["source"]: r for r in result["rows"]}
    assert rows["lastfm"]["unique"] == 1 and rows["deezer"]["unique"] == 0


def test_scoring_rules(app):
    s = st(app)
    rows = []
    def add(genre, source, hits):
        rows.append({"seed": 0, "genre": genre, "section": "tracks", "source": source, "name": source,
                     "answered": True, "returned": 10, "hits": hits, "seconds": 1.0, "unique": 0})
    for g, a, b in (("Rock", 10, 5), ("Pop", 4, 8), ("Jazz", 1, 2), ("Folk", 6, 6)):
        add(g, "a", a)
        add(g, "b", b)
    result = {"genres": ["Rock", "Pop", "Jazz", "Folk"], "rows": rows,
              "sources": {"artists": [], "tracks": [["a", "A"], ["b", "B"]]}}
    sc = s.score(result)["tracks"]
    assert sc["genres"]["Jazz"]["thin"] and not sc["genres"]["Rock"]["thin"]
    assert sc["genres"]["Pop"]["by"]["a"]["percent"] == 50
    assert sc["sources"]["a"]["performance"] == round((100 + 50 + 100) / 3)   # Jazz left out: thin
    assert sc["sources"]["a"]["best_at"][0] == "Rock" and "Jazz" not in sc["sources"]["a"]["best_at"]
    assert not set(sc["sources"]["a"]["best_at"]) & set(sc["sources"]["a"]["worst_at"])


def test_store_seen_and_the_ready_line(app):
    s = st(app)
    s.run(quick=True, wait_for_builds=False)
    own, is_sample = s.load_results()
    assert own and not is_sample and own["mode"] == "quick"
    assert s.unseen()
    app.engine.session_start("Similar Tracks", {"Artist": "Queen", "Name": "Bohemian Rhapsody"})
    assert app.printed.has("Source test ready")
    s.mark_seen()
    app.printed.clear()
    app.engine.session_start("Similar Tracks", {"Artist": "Queen", "Name": "Bohemian Rhapsody"})
    assert not app.printed.has("Source test ready")


def test_the_sample_stands_in_until_a_run(app):
    s = st(app)
    assert s.load_results() == (None, False)
    s.run(quick=True, wait_for_builds=False)
    path = s.make_sample()
    s._table().execute("DELETE FROM source_tests")
    sample, is_sample = s.load_results()
    assert is_sample and sample["sample"] and path.endswith("source_test_sample.json")
    assert s.report_lines(sample, True)[0].startswith("Sample results from a")


def test_pauses_while_a_build_runs(app):
    s = st(app)
    app.engine._SESSION_STARTED[999] = time.time()
    assert s.build_running()
    calls = {"n": 0}

    def stop():
        calls["n"] += 1
        return calls["n"] > 1
    assert s.run(stop=stop) is None and calls["n"] >= 2   # waited, then stopped: nothing saved
    assert s.latest_own() is None
    app.engine._SESSION_STARTED.pop(999)


def test_background_run_says_started_and_ready(app):
    s = st(app)
    assert s.start_background(quick=True)
    assert app.printed.has("Source test started in the background")
    s._thread.join(timeout=60)
    assert app.printed.has("Source test ready")


def test_asking_at_once_gives_the_same_results(app):
    s = st(app)
    together = s.run(quick=True, wait_for_builds=False, parallel=True)
    in_turn = s.run(quick=True, wait_for_builds=False, parallel=False)
    strip = lambda rows: [{k: v for k, v in r.items() if k != "seconds"} for r in rows]
    assert strip(together["rows"]) == strip(in_turn["rows"])


def test_cancel_stops_before_the_next_seed(app, monkeypatch):
    s = st(app)
    real = s.ask

    def slow(*a):
        s.cancel()   # cancelled while the first seed is being asked
        return real(*a)
    monkeypatch.setattr(s, "ask", slow)
    assert s.start_background(quick=True)
    s._thread.join(timeout=60)
    assert s.latest_own() is None
    assert app.printed.has("Source test cancelled")
    assert s.progress_state["n"] == 1


def test_sample_wording_and_export(app, tmp_path):
    s = st(app)
    result = s.run(quick=True, wait_for_builds=False)
    assert s.sample_notice({"library_tracks": 140683}).startswith(
        "Sample results from a 140,683-track library. Source performance varies between libraries")
    path = s.export_csv(result, str(tmp_path / "out.csv"))
    text = open(path, encoding="utf-8").read()
    assert text.startswith("Section,Genre,Source,Performance %") and "Similar Tracks,Rock,Last.fm" in text
    assert "Seeds answered" in s.cell_detail(result, "tracks", "Rock", "lastfm")
