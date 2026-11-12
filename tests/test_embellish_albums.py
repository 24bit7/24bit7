"""
Albums on the Playlists & Albums tab (Ben, 12 Nov 2026). An album plays in order unless Play's arrow says
otherwise; Embellish offers the amounts, the album taken as a playlist of its tracks, and With Their Hits (the
album and the artist's widely played songs from their other albums, shuffled, the first track first) and And
Their Hits (the album in order, then those songs, biggest first). A hit is as Use Adaptive Selections counts
it: a fifth of the Last.fm plays of the artist's biggest. A song on the album never comes back as a hit.
Embellish with one artist (an album, or a one-artist playlist, which used to say there was nothing to agree on)
builds its circle from the artist and two of the five artists most like them, picked at random. Play has no
Non-stop of its own: More Options' switch turns it on (before, Play followed Artist Matching's Non-stop).
"""


def abbey_road(app):
    import library
    library.load()
    found, matches = library.find_album("abbey road")
    assert found, matches
    album, artist, keys = matches[0]
    return {"kind": "album", "Name": album, "Artist": artist, "keys": [str(k) for k in keys]}


def title(key):
    import library
    return library.track_row(key)["Name"]


def beatles_hits(app):
    """Come Together, Yesterday, Help!, Here Comes The Sun and Eleanor Rigby are hits; the rest aren't."""
    big = {"Come Together": 10000, "Yesterday": 9000, "Help!": 8000, "Here Comes The Sun": 7000, "Eleanor Rigby": 3000}
    app.web.plays["The Beatles"] = [big.get(n, 100) for n in app.web.top_tracks("The Beatles")]


def test_and_their_hits_plays_the_album_in_order_then_the_hits_biggest_first(app):
    import embellish
    album = abbey_road(app)
    beatles_hits(app)
    r = app.Lines()
    embellish.embellish(album, None, "and_hits", r)
    z = app.jriver.zone("Speakers").playlist
    assert r.has("Embellish: Abbey Road by The Beatles, 7 tracks, And Their Hits."), r.text()
    assert r.has("The Beatles has 5 widely played songs on Last.fm: 2 on this album, 3 you own from other albums."), r.text()
    assert r.has("Added 3 of their hits after the album, biggest first."), r.text()
    assert z[:7] == album["keys"], "the album first, in its order"
    assert [title(k) for k in z[7:]] == ["Yesterday", "Help!", "Eleanor Rigby"], r.text()


def test_with_their_hits_shuffles_them_through_the_album_its_first_track_first(app):
    import embellish
    album = abbey_road(app)
    beatles_hits(app)
    r = app.Lines()
    embellish.embellish(album, None, "with_hits", r)
    z = app.jriver.zone("Speakers").playlist
    assert r.has("Added 3 of their hits, shuffled through the album."), r.text()
    assert z[0] == album["keys"][0], "Come Together still opens it"
    assert sorted(title(k) for k in z if k not in album["keys"]) == ["Eleanor Rigby", "Help!", "Yesterday"]
    assert set(album["keys"]) <= set(z) and len(z) == 10


def test_a_hit_on_the_album_never_comes_back_even_as_another_copy(app):
    import embellish
    album = abbey_road(app)
    beatles_hits(app)
    r = app.Lines()
    embellish.embellish(album, None, "and_hits", r)
    names = [title(k) for k in app.jriver.zone("Speakers").playlist]
    assert names.count("Come Together") == 1 and names.count("Here Comes The Sun") == 1, names


def test_no_counts_from_last_fm_and_the_album_plays_as_it_is(app):
    import embellish
    album = abbey_road(app)
    app.web.down.add("lastfm")
    r = app.Lines()
    embellish.embellish(album, None, "with_hits", r)
    assert r.has("Last.fm has no play counts for The Beatles, so their hits can't be told from the rest: "
                 "Abbey Road by The Beatles plays as it is."), r.text()
    assert app.jriver.zone("Speakers").playlist == album["keys"]


def test_an_album_takes_the_amounts_too_with_a_circle_of_three(app):
    import embellish
    album = abbey_road(app)
    r = app.Lines()
    embellish.embellish(album, "ordered", "double", r)
    z = app.jriver.zone("Speakers").playlist
    assert r.has("Embellish: Abbey Road by The Beatles, 7 tracks by 1 artist, Double."), r.text()
    assert r.has("Every track on Abbey Road by The Beatles is by The Beatles, so the circle is The Beatles and two "
                 "of the five artists most like them, picked at random:"), r.text()
    new = [k for k in z if k not in album["keys"]]
    assert new, r.text()
    assert [k for k in z if k in album["keys"]] == album["keys"], "Ordered keeps the album's order"
    import library
    assert not any(library.track_row(k)["Artist"] == "The Beatles" for k in new), "only other artists"


def test_the_two_picked_give_their_own_songs_and_the_pick_is_random(app):
    import embellish
    import random
    album = abbey_road(app)
    seen = set()
    for seed in range(6):
        random.seed(seed)
        r = app.Lines()
        embellish.find(album["keys"], "Abbey Road", "double", r)
        line = next(x for x in r if "picked at random:" in x)
        seen.add(line.rsplit(":", 1)[1].strip())
        one, two = line.rsplit(":", 1)[1].strip().rstrip(".").split(" and ")
        assert r.has(f"{one}..."), "a picked artist's own top tracks are looked up"
    assert len(seen) > 1, "a different pair now and then"


def test_a_one_artist_playlist_builds_its_circle_the_same_way(app):
    """Before 12 Nov 2026 it said there was nothing for the curation rules to agree on, and played nothing."""
    import embellish
    r = app.Lines()
    embellish.embellish({"ID": "203", "Name": "60s Smartlist"}, "shuffled", "half", r)
    assert r.has("so the circle is The Beatles and two of the five artists most like them"), r.text()
    assert not r.has("nothing for the curation rules"), r.text()


def test_too_few_artists_like_them_says_so_and_plays_it_as_it_is(app):
    import embellish
    import library
    for s in ("lastfm", "deezer", "listenbrainz", "tidal", "youtube"):
        app.web.empty.add(s)
    r = app.Lines()
    embellish.embellish({"ID": "203", "Name": "60s Smartlist"}, "shuffled", "half", r)
    assert r.has("your sources know too few artists like them to build a circle"), r.text()
    z = app.jriver.zone("Speakers").playlist
    assert z and all(library.track_row(k)["Artist"] == "The Beatles" for k in z), "nothing added"


def test_play_an_album_in_order_and_play_runs_no_non_stop_of_its_own(app):
    import embellish
    import playmix
    album = abbey_road(app)
    playmix.set_open(False) if hasattr(playmix, "set_open") else None
    r = app.Lines()
    embellish.play(album, "ordered", r)
    assert r.has("Play: Abbey Road by The Beatles, 7 tracks, in order."), r.text()
    assert app.jriver.zone("Speakers").playlist == album["keys"]
    import nonstop
    entry = app.engine.NONSTOP_ZONES.get(app.engine.zone_id("Speakers")) or next(iter(app.engine.NONSTOP_ZONES.values()))
    assert not nonstop.config_for("Speakers", entry).get("on"), "More Options closed: Play stops at the end"


def test_more_options_turns_non_stop_on_for_play(app):
    import embellish
    import overrides
    album = abbey_road(app)
    overrides.set_switch("nonstop", "tight")
    import playmix
    playmix.set_open(True)
    try:
        r = app.Lines()
        embellish.play(album, "ordered", r)
        assert r.has("More Options: Non-stop Keep It Tight, over this album's own settings."), r.text()
        import nonstop
        entry = next(iter(app.engine.NONSTOP_ZONES.values()))
        cfg = nonstop.config_for("Speakers", entry)
        assert cfg.get("on") and cfg.get("reseed") == "whole" and cfg.get("using") == "artists", cfg
    finally:
        playmix.set_open(False)


def test_a_playlist_no_longer_borrows_artist_matchings_non_stop(app):
    import buttons
    import embellish
    std = buttons.standard("artists")
    buttons.set_settings(std["id"], dict(std["settings"], NONSTOP_ARTISTS="1"))
    r = app.Lines()
    embellish.play({"ID": "202", "Name": "Road Trip"}, "shuffled", r)
    import nonstop
    entry = next(iter(app.engine.NONSTOP_ZONES.values()))
    assert not nonstop.config_for("Speakers", entry).get("on"), "Artist Matching's Non-stop is its own"


def test_the_album_rows_start_with_both_hits_offered_with_their_hits_the_default(app):
    import embellish
    a = embellish.albums()
    assert a["shown"] == ["with_hits", "and_hits"] and a["default"] == "with_hits"
    assert a["rows"]["and_hits"] == {"nonstop": "no"}
    a = embellish.set_albums(shown=["and_hits"], default="with_hits", and_hits="artists")
    assert a["shown"] == ["and_hits"] and a["default"] == "and_hits", "the default stays one that's offered"
    assert a["rows"]["and_hits"]["nonstop"] == "artists"
    a = embellish.set_albums(default="p50")
    assert a["default"] == "p50", "an amount can be an album's default too"
    assert embellish.choices()["album_order"] == "ordered", "an album plays in order to start"


def test_an_album_goes_on_the_recent_list_as_an_album(app):
    import embellish
    album = abbey_road(app)
    embellish.play(album, "ordered", app.Lines())
    top = embellish.recent()[0]
    assert top["kind"] == "album" and top["artist"] == "The Beatles" and top["name"] == "Abbey Road"
