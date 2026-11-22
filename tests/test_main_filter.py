"""
The Main Filter (Ben, 20 Nov 2026): one set of filters for every playlist, since setting them on each playlist
was a pain. A filter is In Main Filter or not; each config of a playlist uses the Main Filter (the default) or
its own ticks, and on its own ticks the Main Filter doesn't apply to it at all. A build with no playlist behind
it (Blend, Embellish) runs under the Main Filter.

The upgrade keeps day one's playlists as they were: the Main Filter is every filter that had Every playlist
ticked, plus any filter ticked on every config of every playlist; a config whose filters came to exactly that
uses it, and any other keeps its own ticks with the Every playlist ones added, as they applied to it before.
"""

import json


def add_filter(name, every=False, on=True):
    import filters
    f = filters.blank(name)
    f.update(every=every, on=on, rules=[{"field": "year", "op": "before", "value": "1968", "value2": ""}])
    filters.save(filters.load() + [f])
    return f["id"]


def as_saved_before(app, ticks):
    """The playlists as 1.38 kept them: no Main Filter mark, each config's own ticks ({name: [[ids], ...]})."""
    import buttons
    items = buttons.load()
    for b in items:
        b["main_filter"] = ""
        lists = ticks.get(b["name"], [])
        b["filters"] = list(lists[0]) if lists else []
        for n, c in enumerate(b.get("configs") or [], start=1):
            c["filters"] = list(lists[n]) if n < len(lists) else []
    con = app.engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (buttons.META_KEY, json.dumps(items)))
    con.commit()


def lists(button):
    import buttons
    return [button.get("filters")] if buttons.is_radio(button) else [c["filters"] for c in buttons.configs(button)]


def test_a_new_playlist_uses_the_main_filter(app):
    import buttons
    import filters
    for b in buttons.load():
        assert all(l == [filters.MAIN] for l in lists(b)), b["name"]
    assert buttons.blank("New", "artists")["filters"] == [filters.MAIN]
    assert buttons.uses_main(buttons.configs(buttons.standard("artists"))[0])


def test_the_main_filter_is_what_a_build_runs_under(app):
    import buttons
    import filters
    main, other = add_filter("Old Stuff", every=True), add_filter("Not Main")
    off = add_filter("Resting", every=True, on=False)
    assert [f["id"] for f in filters.by_ids([filters.MAIN])] == [main]
    assert [f["id"] for f in filters.by_ids(None)] == [main], "no playlist behind the build: the Main Filter"
    assert [f["id"] for f in filters.by_ids([other])] == [other], "its own ticks: the Main Filter doesn't apply at all"
    assert filters.by_ids([]) == [], "its own ticks, none ticked: no filters"
    assert off in filters.main_ids() and off not in [f["id"] for f in filters.by_ids(None)], "in it, but off"
    artists = buttons.standard("artists")
    assert set(buttons.filter_ids(artists)) == set(filters.main_ids())


def test_no_starts_as_a_copy_of_the_main_filter_and_yes_keeps_the_ticks(app):
    import buttons
    import filters
    main, other = add_filter("Old Stuff", every=True), add_filter("Not Main")
    artists = buttons.standard("artists")
    buttons.set_use_main(artists["id"], False)
    cfg = buttons.configs(buttons.get(artists["id"]))[0]
    assert not buttons.uses_main(cfg) and set(cfg["filters"]) == set(filters.main_ids()), "nothing changes yet"
    buttons.set_filters(artists["id"], [other])
    assert buttons.filter_ids(buttons.get(artists["id"])) == [other]
    buttons.set_use_main(artists["id"], True)
    cfg = buttons.configs(buttons.get(artists["id"]))[0]
    assert buttons.uses_main(cfg) and buttons.own_filters(cfg) == [other], "the ticks wait for a change of mind"
    assert set(buttons.filter_ids(buttons.get(artists["id"]))) == set(filters.main_ids())
    buttons.set_use_main(artists["id"], False)
    assert buttons.configs(buttons.get(artists["id"]))[0]["filters"] == [other], "back as they were left"


def test_each_config_builds_under_the_main_filter_or_its_own(app, monkeypatch):
    import buttons
    import filters
    e = app.engine
    main, other = add_filter("Old Stuff", every=True), add_filter("Not Main")
    guests = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    buttons.set_use_main(guests["id"], False, 1)
    buttons.set_filters(guests["id"], [other], 1)
    seen = []

    def fake(report=print, seed_info=None, **kw):
        seen.append(sorted(f["id"] for f in filters.by_ids(e.FILTER_IDS)))
        report("built")
    for kind in ("top", "artists"):
        monkeypatch.setattr(e, buttons.BUILDERS[kind], fake)
    monkeypatch.setattr(e, "combine_finish", lambda *a, **k: None)
    buttons.run(buttons.get(guests["id"]), report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", ""))
    assert seen == [[main], [other]], "the hosts under the Main Filter, the guests under their own"
    assert filters.used_by(other) == ["Artist + Guests (config 2)"]
    used = filters.used_by(main)
    assert used[0] == "Main Filter" and "Artist + Guests (config 2)" not in used


def test_the_upgrade_takes_every_playlist_filters_as_the_main_filter(app):
    import buttons
    import filters
    every = add_filter("Old Stuff", every=True)
    as_saved_before(app, {})
    items = buttons.load()
    assert all(l == [filters.MAIN] for b in items for l in lists(b)), "nothing ticked anywhere: every config uses it"
    assert all(b["main_filter"] for b in items)
    assert every in filters.main_ids()


def test_the_upgrade_adds_a_filter_ticked_everywhere_to_the_main_filter(app):
    import buttons
    import filters
    everywhere = add_filter("Stereo only")
    before = buttons.load()
    as_saved_before(app, {b["name"]: [[everywhere]] * 6 for b in before})
    lines = app.Lines()
    app.engine.print = lines
    items = buttons.load()
    assert everywhere in filters.main_ids(), "the same on every build, so it's the Main Filter's now"
    assert all(l == [filters.MAIN] for b in items for l in lists(b))
    assert lines.has("Stereo only"), lines.text()


def test_the_upgrade_leaves_a_playlist_that_differs_on_its_own_ticks(app):
    import buttons
    import filters
    every, some = add_filter("Old Stuff", every=True), add_filter("Stereo only")
    shipped = [i for i in filters.main_ids() if i != every]
    as_saved_before(app, {"Artist + Guests": [[], [some]]})
    items = buttons.load()
    guests = next(b for b in items if b["name"] == "Artist + Guests")
    hosts, their_guests = lists(guests)
    assert hosts == [filters.MAIN]
    assert their_guests[0] == some and set(their_guests) == {some, every, *shipped}, \
        "its tick kept, and the Every playlist filters ticked with it, as they applied to it the day before"
    assert some not in filters.main_ids(), "ticked on one config only: not the Main Filter's"
    others = [l for b in items if b["id"] != guests["id"] for l in lists(b)]
    assert all(l == [filters.MAIN] for l in others)
    assert buttons.load() == items, "once: a second read changes nothing"


def test_an_older_profile_is_upgraded_when_its_put_back(app):
    """A profile saved before holds the playlists without the mark: they're upgraded when read, not left as bare ticks."""
    import buttons
    import filters
    every = add_filter("Old Stuff", every=True)
    buttons.load()
    as_saved_before(app, {})
    b = buttons.standard("artists")
    assert lists(b) == [[filters.MAIN]] and every in buttons.filter_ids(b)


def test_non_stop_tops_up_under_both_playlists_filters(app):
    import buttons
    import filters
    main, other = add_filter("Old Stuff", every=True), add_filter("Not Main")
    tracks = buttons.standard("tracks")
    buttons.set_use_main(tracks["id"], False)
    buttons.set_filters(tracks["id"], [other])
    ids = buttons.filter_ids(buttons.standard("artists"), extra=buttons.filter_ids(buttons.get(tracks["id"])))
    assert set(ids) == set(filters.main_ids()) | {other}, "one on the Main Filter, one on its own: a track passes both"
