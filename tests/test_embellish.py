"""
The Play tab's JRiver Playlists tab (Ben, 6 Nov 2026): Play a JRiver playlist shuffled or in order, or Play &
Embellish it: Consensus with its artists as the circle, each agreeing artist's top tracks you own woven in.
In the fake world every artist is similar to every other, so the circle agrees on everyone.
"""

ROAD_TRIP = {"ID": "202", "Name": "Road Trip"}


def artist_of(app, key):
    return app.jriver.by_key[str(key)]["Artist"]


def test_add_half_weaves_one_new_for_every_two_in_your_order(app):
    import embellish
    j = app.jriver
    yours = j.playlists[1]["keys"]
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, "ordered", "half", r)
    z = j.zone("Speakers").playlist
    assert r.has("Embellish: Road Trip, 10 tracks by"), r.text()
    assert r.has("Done:"), r.text()
    new = [k for k in z if k not in yours]
    assert len(new) == 5, (r.text(), z)
    assert z[0] == yours[0], "your first track plays first"
    assert [k for k in z if k in yours] == yours, "Ordered keeps your order"
    on_list = {artist_of(app, k) for k in yours}
    assert not {artist_of(app, k) for k in new} & on_list, "only artists not already on it"
    gaps = [i for i, k in enumerate(z) if k in new]
    assert all(b - a >= 2 for a, b in zip(gaps, gaps[1:])), "spread between yours, never two new together"


def test_double_it_and_shuffled_keep_the_first_track_first(app):
    import embellish
    j = app.jriver
    yours = j.playlists[1]["keys"]
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, "shuffled", "double", r)
    z = j.zone("Speakers").playlist
    new = [k for k in z if k not in yours]
    assert z[0] == yours[0] and set(yours) <= set(z), r.text()
    assert 0 < len(new) <= 10, r.text()
    if len(new) < 10:   # the fake library may run out of agreeing artists' tracks: then it says so
        assert r.has("fewer than the 10 asked for"), r.text()


def test_build_it_out_takes_every_agreeing_artists_top_tracks(app):
    import embellish
    j = app.jriver
    yours = j.playlists[1]["keys"]
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, "ordered", "out", r)
    assert r.has("Stage 1:"), r.text()
    z = j.zone("Speakers").playlist
    new = [k for k in z if k not in yours]
    per = {}
    for k in new:
        per[artist_of(app, k)] = per.get(artist_of(app, k), 0) + 1
    assert new and max(per.values()) > app.engine.TRACKS_PER_ARTIST_PICK or len(new) > 5, (per, r.text())


def test_a_one_artist_playlist_says_why_and_plays_nothing(app):
    import embellish
    j = app.jriver
    before = list(j.zone("Speakers").playlist)
    r = app.Lines()
    embellish.embellish({"ID": "203", "Name": "60s Smartlist"}, "shuffled", "half", r)
    assert r.has("every track on 60s Smartlist is by The Beatles, so there's nothing for the curation rules to agree on"), r.text()
    assert j.zone("Speakers").playlist == before


def test_the_honest_lines(app):
    import embellish
    r = app.Lines()
    embellish.say_result("Road Trip", [], {"agreed": 23, "already": 23, "want": 5, "artists": 9}, r)
    assert r.has("Embellish: nothing to add. All 23 artists the curation rules agree on are already on Road Trip"), r.text()
    r = app.Lines()
    embellish.say_result("Road Trip", ["1"] * 9, {"agreed": 30, "already": 14, "want": 20, "artists": 9}, r)
    assert r.has("Embellish: added 9 tracks, fewer than the 20 asked for. 14 of the agreeing artists are already on Road Trip"), r.text()
    r = app.Lines()
    embellish.say_result("Road Trip", [], {"agreed": 0, "already": 0, "want": 5, "artists": 9}, r)
    assert r.has("don't agree on anyone else"), r.text()


def test_weave_spreads_the_new_tracks_evenly():
    import embellish
    out = embellish.weave(["a", "b", "c", "d", "e"], ["X", "Y"], ordered=True)
    assert out == ["a", "b", "X", "c", "d", "Y", "e"], out
    out = embellish.weave(["a", "b"], ["X", "Y", "Z"], ordered=True)
    assert out[0] == "a" and [k for k in out if k in "ab"] == ["a", "b"] and len(out) == 5, out


def test_play_ordered_and_shuffled(app):
    import embellish
    j = app.jriver
    yours = j.playlists[1]["keys"]
    r = app.Lines()
    embellish.play(ROAD_TRIP, "ordered", r)
    assert j.zone("Speakers").playlist == yours, r.text()
    assert r.has("Play: Road Trip, 10 tracks, in order."), r.text()
    r = app.Lines()
    embellish.play(ROAD_TRIP, "shuffled", r)
    z = j.zone("Speakers").playlist
    assert sorted(z[1:]) == sorted(yours), "a busy zone keeps its playing track, as for any build: " + r.text()


def test_recent_and_the_arrows_choices_are_remembered(app):
    import embellish
    assert embellish.choices() == {"order": "shuffled", "amount": "half"}
    embellish.set_choice("amount", "double")
    embellish.set_choice("order", "ordered")
    assert embellish.choices() == {"order": "ordered", "amount": "double"}
    for pid in ("201", "202", "203", "204", "205", "201"):
        embellish.note_recent({"ID": pid, "Name": pid}, "played")
    ids = [x["id"] for x in embellish.recent()]
    assert ids == ["201", "205", "204", "203", "202"], "most recent first, five at most, no repeats"


def test_save_playlist_suggests_a_name(app):
    import embellish
    embellish.embellish(ROAD_TRIP, "ordered", "half", app.Lines())
    assert app.engine.save_name() == "Road Trip (Embellished)"
    app.engine.SAVE_NAME = None
    seed = app.engine.typed_seed_info("The Beatles", "Here Comes The Sun")
    app.engine.create_similar_playlist(report=app.Lines(), seed_info=seed)
    assert app.engine.save_name() == "The Beatles Mix"


def test_build_it_out_names_the_button_you_press():
    """The console's button is Cancel, so Build It Out's notes say Cancel, not Stop (6 Nov 2026)."""
    import embellish
    import inspect
    assert "Stop keeps" not in inspect.getsource(embellish)
    assert "Cancel keeps" in embellish.AMOUNT_NOTES["out"]
