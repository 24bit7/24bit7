"""
"Why is this here?" in Review (12 Nov 2026): a Found By column says which sources named each track for this
build, and resting on it gives the sentence, with the seed. Read back from what Discover records for the build's
own sessions, so an earlier build's records never answer for this one.
"""


def review_build(app, monkeypatch, kind="tracks"):
    monkeypatch.setattr(app.engine, "REVIEW_MODE", True)
    app.engine.review_reset()
    r = app.Lines()
    seed = app.engine.typed_seed_info("The Beatles", "Here Comes The Sun")
    if kind == "tracks":
        app.engine.create_similar_tracks_playlist(report=r, seed_info=seed)
    else:
        app.engine.create_similar_playlist(report=r, seed_info=seed)
    return app.engine.review_rows(app.engine.REVIEW_KEYS), r


def test_track_matching_says_which_sources_named_each_track_and_from_what_seed(app, monkeypatch):
    rows, r = review_build(app, monkeypatch)
    assert rows, r.text()
    told = [x for x in rows if x["why"]]
    assert len(told) == len(rows), [x for x in rows if not x["why"]]
    seed = [x for x in told if x["why"] == "Seed"]
    assert [x["title"] for x in seed] == ["Here Comes The Sun"], "the typed seed opens the playlist"
    assert seed[0]["why_more"] == "The track you started from."
    for x in told:
        if x in seed:
            continue
        assert x["why_more"].endswith("as like The Beatles - Here Comes The Sun."), x
        assert all(s.strip() in ("Last.fm", "ListenBrainz", "Deezer", "Tidal", "YouTube") for s in x["why"].split(",")), x


def test_artist_matching_names_the_artist_and_the_seeds_own(app, monkeypatch):
    rows, r = review_build(app, monkeypatch, "artists")
    whys = {x["why"] for x in rows}
    assert "Seed artist" in whys or any(x["artist"] != "The Beatles" for x in rows), r.text()
    other = next(x for x in rows if x["artist"] != "The Beatles" and x["why"])
    import fakes   # the sources may name an artist as they know it (The Jimi Hendrix Experience), which Found By quotes
    said = {other["artist"], fakes.SOURCE_NAME.get(other["artist"], other["artist"])}
    assert other["why_more"] in {f"{other['why']} named {name} as like The Beatles - Here Comes The Sun." for name in said},         other["why_more"]
    own = [x for x in rows if x["why"] == "Seed artist"]
    assert all(x["why_more"] == "One of The Beatles's own top tracks: the seed's artist." for x in own)


def test_an_earlier_build_never_answers_for_this_one(app, monkeypatch):
    rows, _ = review_build(app, monkeypatch)
    app.engine.review_reset()   # the next Review build starts: the first one's records are behind it
    again = app.engine.review_rows([x["key"] for x in rows])
    assert all(x["why"] == "" and x["why_more"] == "" for x in again)


def test_each_kind_of_record_reads_as_a_sentence(app):
    w = app.engine._why
    assert w("Deep Cuts", None, "X", ("A", "B"), "similar")[0] == "Deep Cuts"
    assert w("AI", None, "X", ("AI Playlist", "Rainy day"), "vibe") == ("AI", "The AI's pick for Rainy day.")
    assert w("Embellish", None, "X", ("", "Road Trip"), "embellish") == (
        "Embellish", "Added by Embellish, from artists like the ones in Road Trip.")
    assert w("Last.fm", None, "Moby", ("Moby", ""), "top_tracks")[1] == "One of Moby's top tracks on Last.fm."
    assert w("Last.fm", "Moby - Porcelain", "Air", ("Playing Now (Multiple Tracks)", ""), "similar")[1] == \
        "Last.fm named Air as like Moby - Porcelain.", "a Playing Now build names the track it came from"


def test_german(app, monkeypatch):
    rows, _ = review_build(app, monkeypatch)
    import i18n
    i18n.set_language("de")
    try:
        assert app.engine._why("Last.fm", "Moby - Porcelain", "Air", ("", ""), "similar")[1] == \
            "Last.fm hat Air als ähnlich zu Moby - Porcelain genannt."
    finally:
        i18n.set_language("en")
