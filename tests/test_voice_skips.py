"""
Voice skips and Every playlist filters (Ben, 5 Nov 2026). "Alexa, skip" counts the skip in a JRiver field of
24bit7's own (made the first time, written without dirtying the file). The shipped Skipped Tracks filter, off
until switched on, leaves out a track skipped twice or more and every track by an artist with three such
tracks. Any filter can be set to Every playlist, which applies it whether a playlist ticks it or not.
"""

from test_voice import alexa, KITCHEN  # noqa: F401  (the voice fixture)


def skips(app, key):
    return app.jriver.by_key[str(key)].get("24bit7 Voice Skips")


def test_a_voice_skip_counts_in_24bit7s_own_field(app, alexa):
    keys = app.jriver.playlists[0]["keys"]
    app.jriver.play("Kitchen", keys)
    import library
    library.load()
    assert alexa.say("SkipIntent").started
    assert skips(app, keys[0]) == "1" and app.jriver.zone("Kitchen").pos == 1
    assert app.jriver.fields_made == [("24bit7 Voice Skips", "integer")], "made the first time"
    setinfo = app.jriver.calls_to("File/SetInfo")[-1]
    assert setinfo["Dirty"] == "0", "JRiver isn't asked to rewrite the file's tags"
    app.jriver.zone("Kitchen").pos = 0
    assert alexa.say("SkipIntent").started
    assert skips(app, keys[0]) == "2", "the copy held in memory went up too, so the count carries on"
    assert len(app.jriver.fields_made) == 1, "made once"


def test_skipped_tracks_ships_off_and_for_every_playlist(app):
    import filters
    items = filters.load()
    shipped = [x for x in items if x.get("builtin") == "skipped"]
    assert len(shipped) == 1 and shipped[0]["name"] == "Skipped Tracks"
    assert shipped[0]["on"] is False and shipped[0]["every"] is True
    assert filters.used_by(shipped[0]["id"]) == ["Every playlist"]
    assert filters.by_ids([]) == [], "off: nothing applies"
    filters.save([x for x in items if not x.get("builtin")])
    assert not [x for x in filters.load() if x.get("builtin")], "added once only"


def tag_skips(app, counts):
    for key, n in counts.items():
        app.jriver.by_key[str(key)]["24bit7 Voice Skips"] = str(n)
    import library
    library.load()


def switch_on_skipped():
    import filters
    items = filters.load()
    for x in items:
        if x.get("builtin") == "skipped":
            x["on"] = True
    filters.save(items)


def test_skipped_twice_is_left_out_and_three_such_tracks_take_the_artist(app):
    import filters
    j = app.jriver
    beatles = [r["Key"] for r in j.tracks if r["Artist"] == "The Beatles"]
    other = next(r["Key"] for r in j.tracks if r["Artist"] not in ("The Beatles",))
    tag_skips(app, {other: 2, beatles[0]: 1})
    switch_on_skipped()
    active = filters.Active([], report=app.Lines())
    assert active, "on, and for every playlist: it applies with nothing ticked"
    assert not active.allows(other), "skipped twice"
    assert active.allows(beatles[0]) and active.allows(beatles[1]), "once isn't enough"
    tag_skips(app, {beatles[0]: 2, beatles[1]: 3, beatles[2]: 2})
    active = filters.Active([], report=app.Lines())
    assert not active.allows(beatles[3]), "three of theirs skipped twice or more: the artist goes"


def test_every_playlist_applies_an_unticked_filter(app):
    import filters
    item = filters.blank("FLAC only")
    item["rules"] = [{"field": "file_type", "op": "is", "value": "mp3", "value2": ""}]
    items = filters.load() + [item]
    filters.save(items)
    assert not filters.Active([], report=app.Lines()), "not ticked anywhere, not Every playlist"
    for x in items:
        if x["id"] == item["id"]:
            x["every"] = True
    filters.save(items)
    active = filters.Active([], report=app.Lines())
    assert active and not active.allows(app.jriver.tracks[0]["Key"]), "every track here is flac"
    assert filters.used_by(item["id"]) == ["Every playlist"]


def test_a_build_leaves_out_skipped_tracks(app):
    j = app.jriver
    seed = app.engine.typed_seed_info("The Beatles", "Here Comes The Sun")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed)
    first = [k for k in j.zone("Speakers").playlist[1:]]
    assert first, r.text()
    tag_skips(app, {k: 2 for k in first[:3]})
    switch_on_skipped()
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed)
    assert not set(first[:3]) & set(j.zone("Speakers").playlist), r.text()
    assert r.has("Filters: Skipped Tracks (skipped by voice 2 times or more"), r.text()


def test_the_filter_text_doesnt_promise_a_plain_alexa_skip_counts():
    """A plain "Alexa, skip" goes to the speaker, not the skill (manual, What you can say), so it's never counted:
    the filter's text must speak of skips asked of the skill (6 Nov 2026)."""
    import filters
    assert '"Alexa, skip"' not in filters.SKIPPED_TEXT
    assert "skill" in filters.SKIPPED_TEXT
