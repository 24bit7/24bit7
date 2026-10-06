"""
Add Playlist rows (Play tab), Settings > Filters, and how JRiver playlists play by voice.
"""

import time


def seed(app, artist, title):
    return app.engine.typed_seed_info(artist, title)


def build_with_rows(app, rows, builder="tracks"):
    e = app.engine
    e.MIX_ROWS, e.MIX_KEEP, e.MIX_FAST_KEY, e.MIX_NOTED = rows, set(), None, False
    r = app.Lines()
    try:
        if builder == "tracks":
            e.create_similar_tracks_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
        else:
            e.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    finally:
        e.MIX_ROWS, e.MIX_KEEP, e.MIX_FAST_KEY = None, set(), None
    return r


# --- Add Playlist rows -------------------------------------------------------------------

def test_add_before_and_after(app):
    j = app.jriver
    sunday, road = j.playlists[0]["keys"], j.playlists[1]["keys"]
    r = build_with_rows(app, [{"id": "201", "name": "Sunday Morning", "mode": "before"},
                              {"id": "202", "name": "Road Trip", "mode": "after"}])
    z = j.zone("Speakers").playlist
    # tracks already in 24bit7's set are left out of an added playlist, by design
    head = [k for k in sunday if k in z[:len(sunday)]]
    import re
    added_after = int(re.search(r"Road Trip: (\d+) tracks? added after", r.text()).group(1))
    tail = z[-added_after:]
    assert z[:len(head)] == head and len(head) >= len(sunday) - 2, r.text()
    assert tail == [k for k in road if k in tail], r.text()


def test_add_before_plays_its_first_track_first(app):
    """With an Add before row, fast start plays that playlist's first track (his 1 Oct call)."""
    j = app.jriver
    first = j.playlists[0]["keys"][0]
    r = build_with_rows(app, [{"id": "201", "name": "Sunday Morning", "mode": "before"}])
    assert j.zone("Speakers").playlist[0] == first, r.text()


def test_mix_spaced_evenly_finishes_together(app):
    j = app.jriver
    mix = []
    for n in range(8):   # a local band no source knows, so none of these are in 24bit7's own picks
        row = dict(j.tracks[0], Key=str(8000 + n), Name=f"Demo {n}", Artist="Local Band", Album="Demos",
                   **{"Album Artist (auto)": "Local Band", "Track #": str(n + 1)})
        j.tracks.append(row)
        j.by_key[row["Key"]] = row
        mix.append(row["Key"])
    j.add_playlist("298", "Demos", "Demos", "Playlist", mix)
    r = build_with_rows(app, [{"id": "298", "name": "Demos", "mode": "mix", "spread": "even"}])
    z = j.zone("Speakers").playlist
    where = [z.index(k) for k in mix if k in z]
    assert len(where) == len([k for k in mix]), r.text()
    assert where == sorted(where), "a mixed playlist keeps its own order"
    gaps = [b - a for a, b in zip(where, where[1:])]
    assert max(gaps) - min(gaps) <= 2, f"spaced evenly: {where}"
    assert len(z) - 1 - where[-1] <= max(gaps), "both lists should finish together"


def test_mix_drops_duplicates(app):
    j = app.jriver
    beatles = j.playlists[2]["keys"]   # 60s Smartlist: every Beatles track
    r = build_with_rows(app, [{"id": "203", "name": "60s Smartlist", "mode": "after"}])
    z = j.zone("Speakers").playlist
    assert len(z) == len(set(z)), "no track twice"
    assert r.has("already in the playlist left out"), r.text()


def test_rows_play_alone_when_nothing_matched(app):
    for s in ("lastfm", "listenbrainz"):
        app.web.empty.add(s)
    r = build_with_rows(app, [{"id": "202", "name": "Road Trip", "mode": "after"}])
    z = app.jriver.zone("Speakers").playlist
    assert set(app.jriver.playlists[1]["keys"]) <= set(z), r.text()


def test_rows_left_out_on_youtube(app, monkeypatch):
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)
    app.set_env(OUTPUT_TARGET="youtube")
    r = build_with_rows(app, [{"id": "202", "name": "Road Trip", "mode": "after"}])
    assert r.has("added playlists were left out"), r.text()


def test_rows_keep_long_closers(app):
    """Added playlists come through exactly as JRiver gives them: the hidden-track check leaves them alone."""
    j = app.jriver
    echoes = j.key_of("Pink Floyd", "Echoes")
    j.add_playlist("299", "Prog", "Prog", "Playlist", [echoes])
    build_with_rows(app, [{"id": "299", "name": "Prog", "mode": "after"}])
    assert echoes in j.zone("Speakers").playlist


def test_rows_saved_and_counted(app):
    import playmix
    playmix.set_rows([{"id": "202", "name": "Road Trip", "mode": "mix", "spread": "random"}])
    assert playmix.rows()[0]["spread"] == "random"
    build_with_rows(app, playmix.rows())
    assert playmix.load()["counts"].get("202") == 1


# --- Filters -------------------------------------------------------------------------------

def add_filter(app, **kw):
    import filters
    f = filters.blank(kw.pop("name", "Test"))
    f.update(kw)
    filters.save(filters.load() + [f])
    return f


def test_filter_year_rule(app):
    add_filter(app, rules=[{"field": "year", "op": "before", "value": "1968", "value2": ""}])
    r = build_with_rows(app, None)
    years = [int(app.jriver.by_key[k]["Date (year)"]) for k in app.jriver.zone("Speakers").playlist[1:]]
    assert years and all(y < 1968 for y in years), r.text()
    assert r.has("Filters:") and r.has("left out")


def test_filter_seed_never_filtered(app):
    add_filter(app, rules=[{"field": "genre", "op": "contains", "value": "jazz", "value2": ""}])
    r = build_with_rows(app, None)
    assert app.jriver.zone("Speakers").playlist[:1] == [app.jriver.key_of("The Beatles", "Here Comes The Sun")]


def test_filter_pick_from_playlist(app):
    add_filter(app, pick_from="202", pick_name="Road Trip")
    r = build_with_rows(app, None)
    allowed = set(app.jriver.playlists[1]["keys"]) | {app.jriver.key_of("The Beatles", "Here Comes The Sun")}
    assert set(app.jriver.zone("Speakers").playlist) <= allowed, r.text()


def test_filter_off_does_nothing(app):
    add_filter(app, on=False, rules=[{"field": "year", "op": "before", "value": "1900", "value2": ""}])
    r = build_with_rows(app, None)
    assert len(app.jriver.zone("Speakers").playlist) > 10, r.text()


def test_filter_for_main_only_skips_device(app):
    import filters
    app.voice._hear_device("amzn1.ask.device.KITCHEN")
    app.voice.set_own_settings("amzn1.ask.device.KITCHEN", True)   # a speaker with its own settings
    add_filter(app, devices=[filters.MAIN], rules=[{"field": "year", "op": "before", "value": "1900", "value2": ""}])
    app.engine.FILTER_DEVICE = "amzn1.ask.device.KITCHEN"
    try:
        r = build_with_rows(app, None)
    finally:
        app.engine.FILTER_DEVICE = None
    assert not r.has("Filters:"), "a Windows (Main) filter shouldn't apply to a speaker with its own settings " + r.text()


# --- JRiver playlists by voice ------------------------------------------------------------

def test_saved_playlist_skip_recent_never_empties(app):
    sp, j = app.saved_playlists, app.jriver
    for k in j.playlists[0]["keys"]:
        j.mark_played(k, time.time() - 600)
    app.library.load()
    data = sp.main_settings()
    data["rows"] = {"201": dict(sp.DEFAULT_ROW, skip="1")}
    sp.set_main_settings(data)
    r = app.Lines()
    ok, what = sp.play({"ID": "201", "Name": "Sunday Morning", "Type": "Playlist"}, "10001", report=r)
    assert ok and j.zone("Speakers").playlist == j.playlists[0]["keys"], r.text()
    assert r.has("plays in full")


def test_saved_playlist_skip_recent_leaves_out_played(app):
    sp, j = app.saved_playlists, app.jriver
    played = j.playlists[0]["keys"][0]
    j.mark_played(played, time.time() - 600)
    app.library.load()
    data = sp.main_settings()
    data["rows"] = {"201": dict(sp.DEFAULT_ROW, skip="1")}
    sp.set_main_settings(data)
    sp.play({"ID": "201", "Name": "Sunday Morning", "Type": "Playlist"}, "10001", report=app.Lines())
    assert played not in j.zone("Speakers").playlist


def test_saved_playlist_smartlist_row_separate(app):
    sp = app.saved_playlists
    data = sp.main_settings()
    data["all"] = "1"
    data["all_row"]["shuffle"] = "1"
    data["all_row_smart"]["shuffle"] = "0"
    sp.set_main_settings(data)
    sp.play({"ID": "204", "Name": "Random Album", "Type": "Smartlist"}, "10001", report=app.Lines())
    assert app.jriver.zone("Speakers").playlist == app.jriver.playlists[3]["keys"], "smartlist order kept"


def test_saved_tidy_keeps_old_settings(app):
    old = {"all": "1", "all_row": {"shuffle": "1", "shuffle_smart": "0", "nonstop": "tracks", "reseed": "last",
                                   "skip": "2"}}
    out = app.saved_playlists.tidy(old)
    assert out["all_row"]["shuffle"] == "1" and out["all_row_smart"]["shuffle"] == "0"
    assert out["all_row_smart"]["nonstop"] == "tracks"


def test_saved_playlist_nonstop_tops_up(app):
    import nonstop
    sp, j = app.saved_playlists, app.jriver
    data = sp.main_settings()
    data["rows"] = {"201": dict(sp.DEFAULT_ROW, nonstop="tracks")}
    sp.set_main_settings(data)
    sp.play({"ID": "201", "Name": "Sunday Morning", "Type": "Playlist"}, "10001", report=app.Lines())
    z = j.zone("Speakers")
    n = len(z.playlist)
    z.pos = n - 1
    jobs = []
    nonstop.attach(lambda job, heading, origin=None: jobs.append(job))
    nonstop._check_zones()
    assert jobs, "the last track should trigger a top-up"
    r = app.Lines()
    jobs[0](r)
    assert len(z.playlist) > n and z.playlist[:n] == j.playlists[0]["keys"], r.text()
    nonstop._check_zones()
    assert len(jobs) == 1, "one top-up per last track"


def test_nonstop_mode_settings(app):
    by = app.engine.nonstop_settings({"NONSTOP_TRACKS": "1", "NONSTOP_TRACKS_MODE": "tight"}.get)
    assert by["tracks"]["mode"] == "tight" and by["artists"]["mode"] == "journey"


def test_saved_playlist_whole_playlist_keeps_it_tight(app):
    import nonstop
    sp, j = app.saved_playlists, app.jriver
    data = sp.main_settings()
    data["rows"] = {"201": dict(sp.DEFAULT_ROW, nonstop="tracks", reseed="whole")}
    sp.set_main_settings(data)
    sp.play({"ID": "201", "Name": "Sunday Morning", "Type": "Playlist"}, "10001", report=app.Lines())
    z = j.zone("Speakers")
    original = list(z.playlist)
    entry = app.engine.NONSTOP_ZONES["10001"]
    assert entry["saved_cfg"]["reseed"] == "whole" and entry["original"] == set(original)
    z.pos = len(z.playlist) - 1
    jobs = []
    nonstop.attach(lambda job, heading, origin=None: jobs.append(job))
    nonstop._check_zones()
    r = app.Lines()
    jobs[0](r)
    assert r.has("Keep It Tight: reseeding"), r.text()
    assert entry["seeded"] and entry["seeded"] <= set(original), "seeds come from the original playlist"
    assert entry["original"] == set(original), "top-ups never join the original"


def test_keep_it_tight_runs_out_then_carries_on(app):
    import nonstop
    e = app.engine
    entry = {"original": {"k-missing"}, "seeded": set()}
    r = app.Lines()
    assert nonstop._tight_seed("10001", entry, r) is None
    assert r.has("carrying on as Let's See Where This Goes")
