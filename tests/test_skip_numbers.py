"""
Skipped Tracks' two numbers (Ben, 8 Nov 2026): how many voice skips leave a track out (two to start), and how
many tracks left out that way leave their artist out (three to start), each one to nine on the filter's page.
Only tracks left out count towards an artist, not every track skipped once (Ben's choice).
"""

import pytest

from test_voice_skips import switch_on_skipped, tag_skips


def set_limits(track=None, artist=None):
    import filters
    items = filters.load()
    for x in items:
        if x.get("builtin") == "skipped":
            if track is not None:
                x["track_skips"] = track
            if artist is not None:
                x["artist_skips"] = artist
    filters.save(items)


def test_the_track_number_is_the_filters_own(app):
    import filters
    j = app.jriver
    key = next(r["Key"] for r in j.tracks if r["Artist"] != "The Beatles")
    tag_skips(app, {key: 2})
    switch_on_skipped()
    assert not filters.Active([], report=app.Lines()).allows(key), "two, as shipped"
    set_limits(track=3)
    assert filters.Active([], report=app.Lines()).allows(key), "set to three: two skips let it through"
    set_limits(track=1)
    tag_skips(app, {key: 1})
    assert not filters.Active([], report=app.Lines()).allows(key), "set to one: one skip does it"


def test_the_artist_number_counts_tracks_left_out(app):
    import filters
    j = app.jriver
    beatles = [r["Key"] for r in j.tracks if r["Artist"] == "The Beatles"]
    switch_on_skipped()
    tag_skips(app, {beatles[0]: 2, beatles[1]: 1, beatles[2]: 1})
    assert filters.Active([], report=app.Lines()).allows(beatles[3]), "one left out of three needed"
    set_limits(artist=1)
    active = filters.Active([], report=app.Lines())
    assert not active.allows(beatles[3]), "set to one: one track left out takes the artist"
    set_limits(track=3, artist=1)
    assert filters.Active([], report=app.Lines()).allows(beatles[3]), \
        "skipped once or twice isn't left out at three, so it doesn't count towards the artist"


@pytest.mark.parametrize("given, want", [(None, (2, 3)), ({"track_skips": 0, "artist_skips": 40}, (1, 9)),
                                         ({"track_skips": "x"}, (2, 3)), ({"track_skips": 4, "artist_skips": 5}, (4, 5))])
def test_limits_keep_to_one_to_nine(app, given, want):
    import filters
    assert filters.skip_limits(given if given is not None else {}) == want


def test_the_numbers_survive_a_save_and_show_in_the_console_line(app):
    import filters
    set_limits(track=4, artist=6)
    item = next(x for x in filters.load() if x.get("builtin") == "skipped")
    assert (item["track_skips"], item["artist_skips"]) == (4, 6), "kept when the list is saved and read back"
    assert filters.describe(item) == ("Skipped Tracks (skipped by voice 4 times or more, and artists with 6 or more "
                                      "such tracks)")
    assert filters.skipped_list()[0] == [], "nothing skipped four times"
