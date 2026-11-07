"""
At least (Ben, 7 Nov 2026): a filter can ask for a share of each playlist instead of leaving tracks out,
"Kiwi Music: at least 20% of each playlist has Country New Zealand". After the build, tracks that count
are swapped in for the last of those that don't, from artists you own found deeper in the similar-artist
lists already fetched; short of that the usual tracks stay and the console says how far short it fell.
Other field: a rule on any JRiver field by name, read into the library copy alongside the usual fields.
"""

# The fake world's Kiwi tracks: each artist's third track on (not the seed's). A plain build takes each artist's
# top two only, so it never has one; the share finds them through artists deeper in the similar list.
SETUP = dict(SIMILAR_ARTIST_TRACK_COUNT="6", SIMILAR_ARTIST_TRACK_LIMIT="1", TRACKS_PER_ARTIST_POOL="2",
             TRACKS_PER_ARTIST_PICK="2", SKIP_PLAYED_ARTISTS="0", DRIFT_ARTISTS="0",
             SIMILAR_SOURCES="lastfm", SIMILAR_MIN_AGREEMENT="1")


def kiwi_world(app):
    for row in app.jriver.tracks:
        if row["Album Artist (auto)"] not in ("The Beatles", "Various Artists") and int(row["Track #"]) >= 3:
            row["Country"] = "New Zealand"
    import filters
    f = filters.blank("Kiwi Music")
    f.update(mode="least", share=30,
             rules=[{"field": "other", "name": "Country", "op": "is", "value": "New Zealand", "value2": ""}])
    filters.save(filters.load() + [f])
    app.library.load()
    return f


def build(app, f, artist="The Beatles"):
    r = app.Lines()
    e = app.engine
    e.FILTER_IDS = [f["id"]]
    try:
        e.create_similar_playlist(report=r, seed_info=e.typed_seed_info(artist, "Here Comes The Sun"))
    finally:
        e.FILTER_IDS = None
    return r


def kiwi(app, key):
    return app.jriver.by_key[str(key)].get("Country") == "New Zealand"


def test_the_library_reads_a_field_an_other_field_rule_names(app):
    kiwi_world(app)
    names, extra = app.library.fields()
    assert "Country" in names.split(",") and extra == {"Country"}
    assert app.library.has_fields(["Country"]) and not app.library.has_fields(["Mood"])
    row = next(r for r in app.library._tracks if r.get("Name") == "Echoes")
    assert row.get("Country") == "New Zealand", "read into the copy in memory"
    import filters
    assert "Country" in filters.jriver_fields(fresh=True).values()
    values, tracks, artists = filters.field_values("Country")
    assert values == ["New Zealand"] and tracks > 0 and artists >= 2


def test_other_field_rules_and_a_blank_value_never_counts_towards_a_share(app):
    import filters
    f = kiwi_world(app)
    kiwi_row = next(r for r in app.jriver.tracks if r["Name"] == "Echoes")
    blank_row = next(r for r in app.jriver.tracks if r["Artist"] == "The Beatles")
    rule = f["rules"][0]
    assert filters.rule_result(rule, kiwi_row["Key"], kiwi_row) is True
    assert filters.rule_result(rule, blank_row["Key"], blank_row) is filters.MISSING, "leave out: passes, as before"
    assert filters.matches(f, kiwi_row["Key"], kiwi_row) and not filters.matches(f, blank_row["Key"], blank_row)
    assert filters.rule_result(dict(rule, op="is_not"), kiwi_row["Key"], kiwi_row) is False
    assert filters.rule_result(dict(rule, op="contains", value="zeal"), kiwi_row["Key"], kiwi_row) is True
    assert filters.describe(f) == "Kiwi Music (at least 30%: Country is New Zealand)"
    assert filters.other_fields() == ["Country"]
    active = filters.Active([f["id"]], report=app.Lines())
    assert active and active.shares and not active.items, "a share, not a leave out"
    assert active.allows(blank_row["Key"]), "At least never leaves a track out"


def test_a_build_gets_its_share_from_deeper_in_the_similar_artists(app):
    app.set_env(**SETUP)
    f = kiwi_world(app)
    r = build(app, f)
    playlist = app.jriver.zone("Speakers").playlist
    assert len(playlist) == 6, r.text()
    kiwis = [k for k in playlist if kiwi(app, k)]
    assert len(kiwis) >= 2, (len(kiwis), r.text())
    assert r.has("Looking deeper in the similar artists for Kiwi Music"), r.text()
    assert r.has("Kiwi Music: 2 of 6 tracks (33%), as asked."), r.text()
    assert r.has("Filters: Kiwi Music (at least 30%: Country is New Zealand)"), r.text()
    assert playlist.index(kiwis[0]) < len(playlist) - 2, \
        "spread through the playlist, not all at the end"


def test_without_the_share_the_same_build_has_no_kiwis(app):
    """The guard's other half: a plain build takes each artist's top two, none of them a Kiwi track."""
    app.set_env(**SETUP)
    f = kiwi_world(app)
    import filters
    items = filters.load()
    for item in items:
        if item["id"] == f["id"]:
            item["on"] = False
    filters.save(items)
    r = build(app, f)
    assert not [k for k in app.jriver.zone("Speakers").playlist if kiwi(app, k)], r.text()


def test_short_of_the_share_the_usual_tracks_fill_up_and_it_says_so(app):
    app.set_env(**SETUP)
    f = kiwi_world(app)
    import filters
    items = filters.load()
    for item in items:
        if item["id"] == f["id"]:
            item["share"] = 90
    filters.save(items)
    r = build(app, f)
    playlist = app.jriver.zone("Speakers").playlist
    assert len(playlist) == 6, "filled up with the usual tracks"
    have = len([k for k in playlist if kiwi(app, k)])
    assert 0 < have < 6
    assert r.has(f"Kiwi Music: {have} of 6 tracks ({round(100 * have / 6)}%), short of the 90% asked for"), r.text()
    assert r.has("The usual tracks fill the rest."), r.text()


def test_one_artists_tracks_say_the_share_doesnt_apply(app):
    f = kiwi_world(app)
    r = app.Lines()
    e = app.engine
    e.FILTER_IDS = [f["id"]]
    try:
        e.play_top_n(report=r, seed_info=e.typed_seed_info("The Beatles", ""))
    finally:
        e.FILTER_IDS = None
    assert r.has("Kiwi Music: a playlist of one artist's tracks matches all or nothing, so its share doesn't "
                 "apply here."), r.text()
