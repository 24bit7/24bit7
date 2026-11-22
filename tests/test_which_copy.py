"""
Which copy wins when you own several (Ben, 20 Nov 2026). Led Zeppelin's Celebration Day played its live
Black Dog where he'd have had the one on IV (the live album has no "live" in its name, so the two tied and
JRiver's order decided), and a remix came in where he owned the original. The order now: the title asked
for before one with a version tag or other words in brackets; then the earliest year, undated copies after
dated ones; then the album rules as before (own album before a compilation, live last).
"""


def _add(app, key, title, artist, album, year, album_artist=None):
    row = dict(app.jriver.tracks[0], Key=str(key), Name=title, Artist=artist, Album=album,
               **{"Album Artist (auto)": album_artist or artist, "Date (year)": str(year) if year else ""})
    app.jriver.tracks.append(row)
    app.jriver.by_key[row["Key"]] = row
    return row["Key"]


def test_the_earlier_album_wins_over_a_later_live_one(app):
    live = _add(app, 9301, "Black Dog", "Led Zeppelin", "Celebration Day", 2012)   # listed first, as JRiver did
    original = _add(app, 9302, "Black Dog", "Led Zeppelin", "Led Zeppelin IV", 1971)
    app.library.load()
    assert app.library.find_track_key("Led Zeppelin", "Black Dog") == original
    found, matches = app.library.find_song("black dog")
    assert found and matches[0][2] == original
    found, matches = app.library.find_song("black dog by led zeppelin")
    assert found and matches[0][2] == original
    assert app.library.copies(live) == [live, original]
    assert app.library.copies(original)[0] == original


def test_the_original_wins_over_a_remix(app):
    remix = _add(app, 9311, "Blue Monday (Hardfloor Remix)", "New Order", "Substance", 1987)
    original = _add(app, 9312, "Blue Monday", "New Order", "Power, Corruption & Lies", 1993)   # a later reissue's year
    app.library.load()
    assert app.library.find_track_key("New Order", "Blue Monday") == original
    assert app.library.find_track_key("New Order", "Blue Monday (Hardfloor Remix)") == original, \
        "a version tag in the request is ignored, as it always was"
    found, matches = app.library.find_song("blue monday")
    assert found and matches[0][2] == original


def test_brackets_that_are_part_of_the_title_asked_for_win(app):
    plain = _add(app, 9321, "Another Brick In The Wall", "Pink Floyd", "The Wall", 1979)
    part_two = _add(app, 9322, "Another Brick In The Wall (Part 2)", "Pink Floyd", "The Wall", 1979)
    remaster = _add(app, 9323, "Another Brick In The Wall (Part 2) (Remastered)", "Pink Floyd", "Echoes", 1975)
    app.library.load()
    lib = app.library
    assert lib.find_track_key("Pink Floyd", "Another Brick In The Wall (Part 2)") == part_two
    assert lib.find_track_key("Pink Floyd", "Another Brick In The Wall") == plain
    assert lib.find_track_key("Pink Floyd", "Another Brick In The Wall, Part 2") == part_two
    found, matches = lib.find_song("another brick in the wall part two")
    assert found and matches[0][2] == part_two
    assert remaster not in (lib.find_track_key("Pink Floyd", "Another Brick In The Wall (Part 2)"),
                            lib.find_track_key("Pink Floyd", "Another Brick In The Wall"))


def test_a_version_is_still_found_when_its_the_only_copy(app):
    only = _add(app, 9331, "Regret (Fire Island Mix)", "New Order", "Regret", 1993)
    app.library.load()
    assert app.library.find_track_key("New Order", "Regret") == only


def test_a_copy_with_no_year_comes_after_the_dated_ones(app):
    undated = _add(app, 9341, "Ceremony", "New Order", "Singles", None)
    dated = _add(app, 9342, "Ceremony", "New Order", "Substance", 1987)
    app.library.load()
    assert app.library.find_track_key("New Order", "Ceremony") == dated
    assert undated in app.library.copies(dated)


def test_the_same_year_falls_back_to_the_album_rules(app):
    compilation = _add(app, 9351, "Temptation", "New Order", "Now 1987", 1987, album_artist="Various Artists")
    own = _add(app, 9352, "Temptation", "New Order", "Substance", 1987)
    live = _add(app, 9353, "Temptation", "New Order", "Live In Glasgow", 1987)
    app.library.load()
    assert app.library.find_track_key("New Order", "Temptation") == own
    assert app.library.copies(own) == [own, compilation], "a live recording is another song, not a copy"
    assert app.library.copies(live) == [live]


def test_a_live_named_album_loses_even_when_its_the_earlier(app):
    """Ben, 22 Nov 2026: on his library the year alone picked Live At Leeds over Tommy, and sixty one like it."""
    live = _add(app, 9361, "We're Not Gonna Take It", "The Who", "Live At Leeds", 1970)
    studio = _add(app, 9362, "We're Not Gonna Take It", "The Who", "Tommy", 1979)
    only_live = _add(app, 9363, "Young Man Blues", "The Who", "Live At Leeds", 1970)
    app.library.load()
    assert app.library.find_track_key("The Who", "We're Not Gonna Take It") == studio
    found, matches = app.library.find_song("we're not gonna take it")
    assert found and matches[0][2] == studio
    assert app.library.find_track_key("The Who", "Young Man Blues") == only_live, "a live copy still plays when it's all you own"
