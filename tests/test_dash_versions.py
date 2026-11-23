"""
A version after a dash (Ben, 23 Nov 2026): Radio looked up "Don't Stop Me Now - Remastered 2011" and two more
Queen songs he owns and called them not in the library. A version in brackets was always dropped; one after a dash
is dropped the same way now, while the whole title is still filed, so a song whose name has a dash in it is found.
"""

from test_which_copy import _add


def test_a_remaster_after_a_dash_finds_the_song(app):
    titles = ["Don't Stop Me Now", "Another One Bites The Dust", "Under Pressure"]
    for i, title in enumerate(titles):
        _add(app, 9400 + i, title, "Queen", "Greatest Hits", 1981)
    app.library.load()
    keys = {title: app.library.find_track_key("Queen", title) for title in titles}   # the fake world has some too
    for title, key in keys.items():
        assert key and app.library.find_track_key("Queen", f"{title} - Remastered 2011") == key, title
    assert app.library.find_track_key("Queen", "Under Pressure – 2011 Mix") == keys["Under Pressure"], "any dash"
    assert app.library.find_track_key("Queen", "Under Pressure - From 'Some Film'") == keys["Under Pressure"]


def test_a_library_copy_with_a_dash_version_is_found_and_loses_to_the_plain_one(app):
    live = _add(app, 9411, "Paranoid - Live", "Black Sabbath", "Past Lives", 2002)
    app.library.load()
    assert app.library.find_track_key("Black Sabbath", "Paranoid") == live, "all you own still plays"
    studio = _add(app, 9412, "Paranoid", "Black Sabbath", "Paranoid", 2009)   # a later reissue's year
    app.library.load()
    assert app.library.find_track_key("Black Sabbath", "Paranoid") == studio, "the plain title wins, as with brackets"


def test_a_dash_that_is_part_of_the_name_stays(app):
    named = _add(app, 9421, "Hey Hey, My My - Into The Black", "Neil Young", "Rust Never Sleeps", 1979)
    radio = _add(app, 9422, "Radio - Radio", "Elvis Costello", "This Year's Model", 1978)
    app.library.load()
    assert app.library.find_track_key("Neil Young", "Hey Hey, My My - Into The Black") == named, "no version word"
    assert app.library.find_track_key("Elvis Costello", "Radio - Radio") == radio, "the whole title is filed too"
    assert app.library.find_track_key("Neil Young", "Hey Hey, My My") is None, "nothing dropped without a version"
