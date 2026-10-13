"""Deep Cuts (stage 2): picking the least played artists and tracks of the seed's genre, from the library alone."""

import random
import time

import pytest


@pytest.fixture
def dc(app):
    import importlib
    deepcuts = importlib.import_module("deepcuts")
    app.library.load()
    return deepcuts


def rows(app, genre=None, artist=None):
    return [r for r in app.jriver.tracks if (genre is None or r["Genre"] == genre)
            and (artist is None or r["Artist"] == artist)]


def play(app, artist=None, genre=None, plays=50, days_ago=10):
    for r in rows(app, genre, artist):
        r["Number Plays"] = str(plays)
        r["Last Played"] = str(int(time.time() - days_ago * 86400))


def reload(app):
    app.library.load()


def test_seed_genres_and_split_values(app, dc):
    j = app.jriver
    key = j.key_of("The Beatles", "Here Comes The Sun")
    assert dc.seed_genres(key) == ["Rock"]
    j.by_key[key]["Genre"] = "Rock; Pop"
    reload(app)
    assert dc.seed_genres(key) == ["Rock", "Pop"], "a genre list counts as each of its genres"


def test_by_track_picks_the_least_played(app, dc):
    play(app, genre="Rock")                    # every Rock track played lots
    quiet = [r for r in rows(app, "Rock") if r["Artist"] in ("Queen", "Badfinger", "Pink Floyd")]
    for r in quiet:
        r["Number Plays"], r["Last Played"] = "0", ""
    reload(app)
    picks, note = dc.pick_by_track(["Rock"], 3, exclude_artists=["The Beatles"], rng=random.Random(1))
    assert note == "" and len(picks) == 3
    artists = [a for _, a, _ in picks]
    assert len(set(artists)) == 3, "one per artist"
    assert set(artists) <= {"Queen", "Badfinger", "Pink Floyd", "The Kinks", "Jimi Hendrix",
                            "George Harrison", "The Rolling Stones"}
    assert "The Beatles" not in artists


def test_by_track_leaves_out_short_tracks_and_what_is_already_in(app, dc):
    j = app.jriver
    in_build = [j.key_of("Queen", "Bohemian Rhapsody")]
    for _ in range(20):
        picks, _ = dc.pick_by_track(["Rock"], 6, exclude_keys=in_build, rng=random.Random(_))
        for key, artist, title in picks:
            assert key not in in_build
            assert float(j.by_key[key]["Duration"]) >= dc.SHORTEST, title   # never "Her Majesty" (0:23)


def test_hidden_closers_left_out_when_the_build_skips_them(app, dc):
    app.set_env(SKIP_LONG_CLOSERS="1", LONG_CLOSER_MINUTES="6")
    echoes = app.jriver.key_of("Pink Floyd", "Echoes")
    for seed in range(30):
        picks, _ = dc.pick_by_track(["Rock"], 8, rng=random.Random(seed))
        assert echoes not in [k for k, _, _ in picks]


def test_allowed_is_respected(app, dc):
    banned = {r["Key"] for r in rows(app, "Rock", "Queen")}
    for seed in range(10):
        picks, _ = dc.pick_by_track(["Rock"], 8, allowed=lambda k: k not in banned, rng=random.Random(seed))
        assert not banned & {k for k, _, _ in picks}


def test_by_artist_picks_neglected_artists(app, dc):
    play(app, genre="Rock", days_ago=10)       # all Rock played lately...
    for name in ("Badfinger", "The Rolling Stones"):
        for r in rows(app, "Rock", name):     # ...except these two
            r["Last Played"] = str(int(time.time() - 800 * 86400))
    reload(app)
    seen = set()
    for seed in range(20):
        picks, note = dc.pick_by_artist(["Rock"], 2, exclude_artists=["The Beatles"], rng=random.Random(seed))
        assert note == ""
        seen |= {a for _, a, _ in picks}
    assert {"Badfinger", "The Rolling Stones"} <= seen, seen   # the five least played: these two always in it
    assert "The Beatles" not in seen


def test_by_artist_one_played_track_doesnt_make_an_artist_recent(app, dc):
    """The share of an artist's tracks played lately counts, not their single latest play."""
    play(app, genre="Rock", days_ago=10)
    for name in ("Badfinger", "Queen"):
        for r in rows(app, "Rock", name):
            r["Last Played"] = ""
    rows(app, "Rock", "Queen")[0]["Last Played"] = str(int(time.time() - 3600))   # one Queen track last night
    reload(app)
    seen = set()
    for seed in range(20):
        picks, _ = dc.pick_by_artist(["Rock"], 2, rng=random.Random(seed))
        seen |= {a for _, a, _ in picks}
    assert "Queen" in seen, "one of three tracks played: still among the least played"


def test_by_artist_uses_top_tracks_first(app, dc):
    picks, _ = dc.pick_by_artist(["Rock"], 9, top_tracks=lambda a: ["Day After Day"] if a == "Badfinger" else [],
                                 rng=random.Random(3))
    badfinger = [t for _, a, t in picks if a == "Badfinger"]
    assert badfinger in ([], ["Day After Day"])
    picks, _ = dc.pick_by_artist(["Rock"], 9, rng=random.Random(3),
                                 top_tracks=lambda a: ["Day After Day"] if a == "Badfinger" else [])
    assert all(t == "Day After Day" for _, a, t in picks if a == "Badfinger")


def test_honest_reasons(app, dc):
    j = app.jriver
    assert dc.pick_by_track([], 3) == ([], "the seed track has no genre in your library")
    picks, note = dc.pick_by_track(["Folk"], 3)
    assert not picks and note.startswith("only ") and "Folk" in note
    picks, note = dc.pick_by_artist(["Folk"], 3)
    assert not picks and "other artist" in note
    for r in j.tracks:
        r["Last Played"] = "not a date"
    reload(app)
    assert dc.pick_by_track(["Rock"], 3)[1] == "JRiver's last played dates couldn't be read"


def test_common_genre_for_ai_playlists(app, dc):
    j = app.jriver
    rock = [r["Key"] for r in rows(app, "Rock")][:6]
    pop = [r["Key"] for r in rows(app, "Pop")][:2]
    assert dc.common_genre(rock + pop) == "Rock"
    spread = [rows(app, g)[0]["Key"] for g in ("Rock", "Pop", "Folk", "Folk Rock", "Post-Rock", "Dance")]
    assert dc.common_genre(spread) is None, "no genre covers enough of them"


def test_index_follows_the_next_library_read(app, dc):
    assert not dc.pick_by_track(["Trip Hop"], 2)[0]
    for r in rows(app, "Rock"):
        r["Genre"] = "Trip Hop"
    reload(app)
    assert dc.pick_by_track(["trip hop"], 2)[0], "the new genre is found, in any case"


def test_various_artists_tracks_count_as_their_real_artist(app, dc):
    for r in rows(app, "Rock", "Queen"):
        r["Artist"], r["Name"] = "Various Artists", f"Stasis - {r['Name']}"
    reload(app)
    seen = set()
    for seed in range(30):
        picks, _ = dc.pick_by_track(["Rock"], 8, rng=random.Random(seed))
        assert "Various Artists" not in {a for _, a, _ in picks}
        seen |= {(a, t) for _, a, t in picks if a == "Stasis"}
    assert seen and all(" - " not in t for _, t in seen), seen
    by = {}
    for seed in range(30):
        picks, _ = dc.pick_by_track(["Rock"], 8, rng=random.Random(seed))
        assert len([a for _, a, _ in picks if a == "Stasis"]) <= 1, "still one per artist"
