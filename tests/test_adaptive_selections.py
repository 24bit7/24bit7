"""
Use Adaptive Selections (Ben, 12 Nov 2026): a tick in Similar Artists' and Radio's Playlist Selection, on by
default. "Pick 3 of each artist's top 5" shrinks for an artist whose Last.fm plays fall off a cliff: a hit is
a song with at least a fifth of the plays of the artist's biggest, and the pool and the pick shrink to the
number of hits, so a one-hit wonder gives its hit and not the rest. It only ever cuts down. Last.fm's counts
size it whichever sources give the titles; with no counts, or the tick off, picking is as it was.
Measured on 157 of Ben's artists the same day: 4 Non Blondes one hit, Massive Attack ten, Radiohead thirty.
"""

SEED = ("The Beatles", "Here Comes The Sun")


def owned_artist(app, least=4):
    """A similar artist the fake library has at least `least` top tracks of (the source's name for it)."""
    import library
    for name in app.web.artists:
        if name == SEED[0]:
            continue
        titles = app.web.top_tracks(name)
        owned = [t for t in titles if library.find_track_key(name, t)]
        if len(owned) >= least:
            return name, titles
    raise AssertionError("the fake library has no artist with enough tracks")


def build(app, **env):
    app.set_env(SIMILAR_ARTIST_TRACK_LIMIT="0", TRACKS_PER_ARTIST_PICK="3", TRACKS_PER_ARTIST_POOL="5", **env)
    app.engine.load_settings()
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info(*SEED))
    return r, app.jriver.zone("Speakers").playlist


def by(app, keys, name):
    import library
    return [k for k in keys if app.engine.artist_key(library.track_row(k).get("Artist") or "")
            == app.engine.artist_key(name) or (library.track_row(k).get("Artist") or "").lower() in name.lower()]


def test_a_one_hit_wonder_gives_its_hit_and_says_so(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)   # the next song has three per cent of the hit's plays
    r, sent = build(app)
    assert r.has(f"Adaptive Selections: {name} has 1 widely played song, so the pick comes from that."), r.text()
    theirs = by(app, sent, name)
    assert len(theirs) == 1, (theirs, r.text())
    assert library.track_row(theirs[0])["Name"] == titles[0], "the hit, not one of the rest"


def test_two_hits_give_at_most_two(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000, 4000] + [500] * (len(titles) - 2)   # a fifth of 10,000 is 2,000
    r, sent = build(app)
    assert r.has(f"Adaptive Selections: {name} has 2 widely played songs, so the pick comes from those."), r.text()
    assert 1 <= len(by(app, sent, name)) <= 2, r.text()


def test_an_artist_whose_plays_hold_up_is_left_alone(app):
    """The fake world's counts fall gently (1000, 999, ...): every song is a hit, nothing is cut or said."""
    import library
    library.load()
    r, sent = build(app)
    assert not r.has("Adaptive Selections:"), r.text()


def test_unticked_it_picks_as_before(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)
    r, sent = build(app, ADAPTIVE_ARTISTS="0")
    assert not r.has("Adaptive Selections:"), r.text()
    assert len(by(app, sent, name)) >= 2, "three picked from five, one of the five not owned"


def test_with_last_fm_silent_nothing_is_cut(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)
    app.set_env(TOP_TRACK_SOURCES="deezer")   # the titles from Deezer, as the shipped settings have them
    app.web.down.add("lastfm")
    r, sent = build(app, TOP_TRACK_SOURCES="deezer", SIMILAR_SOURCES="deezer", SIMILAR_MIN_AGREEMENT="1")
    assert not r.has("Adaptive Selections:"), r.text()
    assert not r.has("Problem: Last.fm didn't answer for"), "a second opinion fails quietly, artist by artist"
    assert len(by(app, sent, name)) >= 2, r.text()


def test_last_fm_sizes_the_cut_when_another_source_gives_the_titles(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)
    r, sent = build(app, TOP_TRACK_SOURCES="deezer")
    assert r.has(f"Adaptive Selections: {name} has 1 widely played song"), r.text()
    assert len(by(app, sent, name)) == 1, r.text()


def test_versions_of_a_song_count_once():
    import engine
    rows = [("Mambo No. 5", 1000), ("Mambo No. 5 (Remastered)", 900), ("I Got A Girl", 100)]
    best = {}
    for n, p in rows:
        k = engine.clean_name(n)
        best[k] = max(best.get(k, 0), p)
    assert len(best) == 2, "the remaster folds into the song (clean_name), so it can't count as a second hit"


def test_embellish_cuts_an_agreeing_one_hit_wonder_too(app):
    import embellish
    import library
    library.load()
    road_trip = {"ID": "202", "Name": "Road Trip"}
    yours = app.jriver.playlists[1]["keys"]
    on_list = {app.engine.artist_key(library.track_row(k)["Artist"]) for k in yours}
    name, titles = next((n, app.web.top_tracks(n)) for n in app.web.artists
                        if app.engine.artist_key(n) not in on_list and len(
                            [t for t in app.web.top_tracks(n) if library.find_track_key(n, t)]) >= 3)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)
    r = app.Lines()
    embellish.embellish(road_trip, "ordered", "out", r)
    assert r.has(f"Adaptive Selections: {name} has 1 widely played song"), r.text()
    new = [k for k in app.jriver.zone("Speakers").playlist if k not in yours]
    assert len(by(app, new, name)) <= 1, r.text()


def test_the_tick_is_one_of_similar_artists_and_radios_settings_and_kept_in_profiles(app):
    import buttons
    import engine
    assert "ADAPTIVE_ARTISTS" in buttons.KIND_KEYS["artists"]
    assert "ADAPTIVE_ARTISTS" in buttons.RADIO_KEYS
    assert "ADAPTIVE_ARTISTS" in engine.PROFILE_KEYS["playlist"]
    app.engine.load_settings()
    assert engine.ADAPTIVE_PICK is True, "on by default"
