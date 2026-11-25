"""
Stacking artists on the Search tab (Ben, 23 Nov 2026, building playlists for Jo's phone): Go plays up to the
chosen number of each added artist's top songs you own, shuffled with the artists spread, to Output; with Most
Played ticked an artist gives only their widely played songs, so a one-hit wonder gives the hit. Logged to
Discover as one session; Save Playlist offers the artists' names; nothing plays on by itself afterwards.
"""


def owned(app, count, least=4, skip=()):
    """count of the fake world's artists with at least `least` top tracks in the library."""
    import library
    library.load()
    found = []
    for name in app.web.artists:
        if name in skip:
            continue
        titles = app.web.top_tracks(name)
        if len([t for t in titles if library.find_track_key(name, t)]) >= least:
            found.append((name, titles))
        if len(found) == count:
            return found
    raise AssertionError("the fake library hasn't enough artists with tracks")


def artist_of(k):
    import library
    return library.track_row(k).get("Artist") or ""


def go(app, artists, count=3, most_played="off"):
    import stack
    r = app.Lines()
    n = stack.build(artists, count, most_played, r)
    return r, n, app.jriver.zone("Speakers").playlist


def test_go_takes_up_to_the_number_from_each_artist(app):
    (a, _), (b, _) = owned(app, 2)
    r, n, sent = go(app, [a, b], count=3)
    assert n == len(sent) and 2 <= n <= 6, r.text()
    for name in (a, b):
        theirs = [k for k in sent if name.lower() in artist_of(k).lower()]
        assert 1 <= len(theirs) <= 3, (name, r.text())
    assert r.has(f"Search: {a} and {b}, up to 3 each."), r.text()
    assert r.has(f"  {a}: "), r.text()


def test_most_played_gives_a_one_hit_wonder_its_hit(app):
    import library
    (a, titles), (b, _) = owned(app, 2)
    app.web.plays[a] = [10000] + [300] * (len(titles) - 1)
    r, n, sent = go(app, [a, b], count=5, most_played="down")
    theirs = [k for k in sent if a.lower() in artist_of(k).lower()]
    assert [library.track_row(k)["Name"] for k in theirs] == [titles[0]], r.text()
    assert r.has(f"  {a}: 1 track."), r.text()
    assert r.has("each, from their hits."), "the first line says it's on"


def test_without_most_played_the_one_hit_wonder_gives_the_number(app):
    (a, titles), = owned(app, 1)
    app.web.plays[a] = [10000] + [300] * (len(titles) - 1)
    r, n, sent = go(app, [a], count=3)
    assert n == 3, r.text()


def test_one_session_save_name_and_nothing_plays_on(app):
    import engine
    (a, _), (b, _), (c, _), (d, _) = owned(app, 4, least=2)
    engine.NONSTOP_ZONES.clear()
    r, n, sent = go(app, [a, b, c, d], count=2)
    assert engine.SAVE_NAME == f"{a}, {b} and 2 more", engine.SAVE_NAME
    rows = engine.db().execute("SELECT mode, seed_track FROM sessions ORDER BY id DESC LIMIT 1").fetchone()
    assert rows[0] == "stack", rows
    assert not engine.NONSTOP_ZONES, "a list you chose: Non-stop isn't left set up for it"


def test_artists_spread(app):
    import engine
    (a, _), (b, _), (c, _) = owned(app, 3)
    r, n, sent = go(app, [a, b, c], count=4)
    names = [engine.artist_key(artist_of(k)) for k in sent]
    assert all(x != y for x, y in zip(names, names[1:])), names


def test_choices_are_remembered(app):
    import stack
    assert stack.choices() == {"count": 5, "most_played": "down"}, "five each and Select From Hits down to start"
    stack.set_choice("count", 8)
    stack.set_choice("most_played", "both")
    assert stack.choices() == {"count": 8, "most_played": "both"}
    stack.set_choice("most_played", "0")   # as 1.43 kept it
    assert stack.choices()["most_played"] == "off"


def test_discover_seed_says_search(app):
    import discover_gui
    import discover_stats
    assert discover_gui.seed_label("stack", "", "A and B") == "Search: A and B"
    assert "stack" in discover_stats.NO_SEED_ARTIST
