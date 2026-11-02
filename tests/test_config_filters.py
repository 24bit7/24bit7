"""
Filters belong to each config of a playlist (Ben, 2 Nov 2026), so the hosts in Artist + Guests can come
from the whole library while the guests are stereo only. A playlist saved before that gives every config
the playlist's filters, so nothing changes for anyone until they untick one.
"""


def add_filter(app, name="Stereo only"):
    import filters
    f = filters.blank(name)
    f["rules"] = [{"field": "year", "op": "before", "value": "1968", "value2": ""}]
    filters.save(filters.load() + [f])
    return f


def test_a_playlist_saved_before_gives_every_config_its_filters(app):
    import buttons
    f = add_filter(app)
    guests = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    assert len(guests["configs"]) == 1, "two configs: its own and the guests"
    items = buttons.load()
    for b in items:
        if b["id"] == guests["id"]:
            b["filters"] = [f["id"]]
            del b["configs"][0]["filters"]   # as 1.29 saved a mix: filters on the playlist only
    buttons.save(items)
    cfgs = buttons.configs(buttons.get(guests["id"]))
    assert [c["filters"] for c in cfgs] == [[f["id"]], [f["id"]]], "each config took the playlist's"
    assert buttons.describe(buttons.get(guests["id"])).endswith("Filters")


def test_each_config_builds_under_its_own_filters_and_used_by_names_the_config(app, monkeypatch):
    import buttons
    import filters
    e = app.engine
    f = add_filter(app)
    guests = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    buttons.set_filters(guests["id"], [], 0)
    buttons.set_filters(guests["id"], [f["id"]], 1)
    guests = buttons.get(guests["id"])
    assert buttons.configs(guests)[0]["filters"] == [] and buttons.configs(guests)[1]["filters"] == [f["id"]]
    assert filters.used_by(f["id"]) == ["Artist + Guests (config 2)"]
    assert buttons.describe(guests).endswith("Filters"), "said even when only a later config has them"
    seen = []

    def fake(report=print, seed_info=None, **kw):
        seen.append(list(e.FILTER_IDS or []))
        report("built")
    for kind in ("top", "artists"):
        monkeypatch.setattr(e, buttons.BUILDERS[kind], fake)
    monkeypatch.setattr(e, "combine_finish", lambda *a, **k: None)
    buttons.run(guests, report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", ""))
    assert seen == [[], [f["id"]]], "the hosts from the whole library, the guests under the filter"
    # a single-config playlist: Used by names it plainly, and a new config starts with the first's filters
    artists = buttons.standard("artists")
    buttons.set_filters(artists["id"], [f["id"]])
    assert "Similar Artists" in filters.used_by(f["id"])
    buttons.add_config(artists["id"], "tracks")
    assert buttons.configs(buttons.get(artists["id"]))[1]["filters"] == [f["id"]]


def test_a_mix_carries_on_as_its_config_with_that_configs_filters(app):
    import buttons
    f = add_filter(app)
    guests = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    buttons.set_filters(guests["id"], [f["id"]], 1)
    guests = buttons.get(guests["id"])
    g = buttons.get(guests["id"])
    g["mix"]["continue_as"] = 1
    carried = buttons.continue_as(g)
    assert carried["kind"] == "artists" and carried["filters"] == [f["id"]], "Non-stop tops up under the guests' filter"
    g["mix"]["continue_as"] = 0
    assert buttons.continue_as(g)["filters"] == [], "or under the hosts' (none) when it carries on as them"
    # a copy keeps each config's filters; the first config moving up takes its own with it
    copy = buttons.duplicate(guests["id"])
    assert [c["filters"] for c in buttons.configs(copy)] == [[], [f["id"]]]
    buttons.remove_config(copy["id"], 0)
    moved = buttons.get(copy["id"])
    assert moved["kind"] == "artists" and moved["filters"] == [f["id"]]
