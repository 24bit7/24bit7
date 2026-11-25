"""
Select From Hits (Ben, 25 Nov 2026; Most Played until then, Use Adaptive Selections until 23 Nov; Ben, 12 Nov): a tick in Similar Artists' and Radio's Playlist Selection, on by
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
    assert r.has(f"Select From Hits: {name} has 1 hit, so just that one."), r.text()
    theirs = by(app, sent, name)
    assert len(theirs) == 1, (theirs, r.text())
    assert library.track_row(theirs[0])["Name"] == titles[0], "the hit, not one of the rest"


def test_two_hits_give_at_most_two(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000, 4000] + [500] * (len(titles) - 2)   # a fifth of 10,000 is 2,000
    r, sent = build(app)
    assert r.has(f"Select From Hits: {name} has 2 hits, so 2 picked from those."), r.text()
    assert 1 <= len(by(app, sent, name)) <= 2, r.text()


def test_an_artist_whose_plays_hold_up_is_left_alone(app):
    """The fake world's counts fall gently (1000, 999, ...): every song is a hit, so the pick is as asked."""
    import library
    library.load()
    r, sent = build(app)
    assert r.has("hits, so 3 picked from those."), r.text()


def test_unticked_it_picks_as_before(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)
    r, sent = build(app, ADAPTIVE_ARTISTS="off")
    assert not r.has("Select From Hits:"), r.text()
    assert len(by(app, sent, name)) >= 2, "three picked from five, one of the five not owned"


def test_with_last_fm_silent_nothing_is_cut(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)
    app.set_env(TOP_TRACK_SOURCES="deezer")   # the titles from Deezer, as the shipped settings have them
    app.web.down.add("lastfm")
    r, sent = build(app, TOP_TRACK_SOURCES="deezer", SIMILAR_SOURCES="deezer", SIMILAR_MIN_AGREEMENT="1")
    assert not r.has("Select From Hits:"), r.text()
    assert r.has(f"No play counts from Last.fm for {name}, so its top tracks are used instead."), \
        "said, so the hits weren't left out without a word (25 Nov 2026)"
    assert not r.has("Problem: Last.fm didn't answer for"), "a second opinion, not a problem"
    assert len(by(app, sent, name)) >= 2, r.text()


def test_last_fm_sizes_the_cut_when_another_source_gives_the_titles(app):
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000] + [300] * (len(titles) - 1)
    r, sent = build(app, TOP_TRACK_SOURCES="deezer")
    assert r.has(f"Select From Hits: {name} has 1 hit"), r.text()
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
    assert r.has(f"Select From Hits: {name} has 1 hit"), r.text()
    new = [k for k in app.jriver.zone("Speakers").playlist if k not in yours]
    assert len(by(app, new, name)) <= 1, r.text()


def test_the_tick_is_one_of_similar_artists_and_radios_settings_and_kept_in_profiles(app):
    import buttons
    import engine
    assert "ADAPTIVE_ARTISTS" in buttons.KIND_KEYS["artists"]
    assert "ADAPTIVE_ARTISTS" in buttons.RADIO_KEYS
    assert "ADAPTIVE_ARTISTS" in engine.PROFILE_KEYS["playlist"]
    app.engine.load_settings()
    assert engine.ADAPTIVE_PICK == "down", "on by default, as Most Played was"


def top_build(app, **env):
    """Artist's Top Tracks for the one-hit wonder, ten asked for, most popular first."""
    import library
    library.load()
    name, titles = owned_artist(app)
    app.web.plays[name] = [10000, 4000] + [300] * (len(titles) - 2)   # two widely played
    seed = app.engine.typed_seed_info(name, "")
    app.set_env(TOP_TRACKS_COUNT="10", TOP_TRACKS_ORDER="popular", **env)
    app.engine.load_settings()
    r = app.Lines()
    app.engine.play_top_n(report=r, seed_info=seed)
    return r, name, titles, app.jriver.zone("Speakers").playlist


def test_most_played_on_top_tracks_takes_only_the_widely_played(app):
    """Ben, 23 Nov 2026, building playlists for Jo: "I don't want 10 tracks if they only have 4 worth adding"."""
    import library
    r, name, titles, sent = top_build(app, ADAPTIVE_TOP="down")
    assert r.has(f"Select From Hits: {name} has 2 hits, so 2 picked from those."), r.text()
    assert 1 <= len(sent) <= 2 and {library.track_row(k)["Name"] for k in sent} <= set(titles[:2]), r.text()


def test_top_tracks_is_as_before_unless_ticked(app):
    r, name, titles, sent = top_build(app)
    assert not r.has("Select From Hits:"), r.text()
    assert len(sent) > 2, "off by default: Top 10 still means ten, as far as you own them"
    import buttons
    import engine
    assert "ADAPTIVE_TOP" in buttons.KIND_KEYS["top"] and "ADAPTIVE_TOP" in engine.PROFILE_KEYS["playlist"]
    assert engine.ADAPTIVE_TOP == "off"


def hits_of(monkeypatch, n):
    import engine
    names = [f"Song {i}" for i in range(1, n + 1)]
    monkeypatch.setattr(engine, "hit_titles", lambda artist: list(names))
    return names


def test_the_pool_is_the_hits_themselves_not_the_sources_top_few(app, monkeypatch):
    """Ben, 25 Nov 2026: a deep artist (the Beatles, fifty hits) gave five of the same top seven every build.
    Now the pool is every hit, so the handful differs from build to build."""
    import engine
    names = hits_of(monkeypatch, 20)
    r = app.Lines()
    pool, take, used = engine.select_from_hits("The Beatles", names[:7], 5, r, mode="down")
    assert used and take == 5 and sorted(pool) == sorted(names), "all twenty hits to pick from"
    assert r.has("Select From Hits: The Beatles has 20 hits, so 5 picked from those."), r.text()


def test_both_gives_up_to_half_again_rounded_up(app, monkeypatch):
    """Ben, 25 Nov 2026: up is capped at half again, rounded up, so 5 gives 8 (Breaking Benjamin's twenty-odd
    hits mustn't swamp the other artists)."""
    import engine
    names = hits_of(monkeypatch, 25)
    assert engine.select_from_hits("Breaking Benjamin", names[:7], 5, app.Lines(), mode="both")[1] == 8
    assert engine.select_from_hits("Breaking Benjamin", names[:7], 4, app.Lines(), mode="both")[1] == 6
    hits_of(monkeypatch, 3)
    assert engine.select_from_hits("The Monkees", names[:7], 5, app.Lines(), mode="both")[1] == 3, "no more than the hits"
    assert engine.select_from_hits("The Monkees", names[:7], 5, app.Lines(), mode="down")[1] == 3


def test_most_playeds_saved_values_read_as_down():
    """A playlist saved with Most Played ticked (1) reads as down, so nothing changes at the upgrade."""
    import engine
    assert [engine.hits_mode(v) for v in ("1", "0", True, False, "", "down", "both", "off", None)] == \
        ["down", "off", "down", "off", "off", "down", "both", "off", "off"]
