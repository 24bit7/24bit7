"""
The album to buy first (Ben, 20 and 22 Nov 2026): Discover > Missing Artists says which album holds most of the
songs the sources named for an artist you don't own. On 22 Nov Deezer's plain search, tried on Ben's own list,
found P.O.D.'s Greatest Hits before Satellite for most of the songs, and Trapt's Live and Sevendust's Best Of
turned up beside the originals, so the line reads the artist's discography and files each song under the album
it first came out on, by the rules his own copies are chosen by.
"""

# P.O.D. as Deezer had them on 22 Nov 2026, cut down: the originals, a greatest hits, a live album, an acoustic
# re-recording and a deluxe reissue of the original.
POD = [
    ("Satellite (Expanded Edition; 2021 Remaster)", "2001-09-11", "album",
     ["Set It Off (2021 Remaster)", "Alive (2021 Remaster)", "Youth of the Nation (2021 Remaster)",
      "Boom (2021 Remaster)", "Celestial (2021 Remaster)", "Boom (The Crystal Method Remix) (2021 Remaster)"]),
    ("Satellite (U.S. Version)", "2001-09-11", "album", ["Set It Off", "Alive", "Youth of the Nation", "Boom"]),
    ("Payable on Death (U.S. Version)", "2003-11-03", "album", ["Wildfire", "Will You", "Change The World"]),
    ("Live (Remastered)", "1997-01-01", "album", ["Alive", "Boom", "Southtown"]),
    ("Greatest Hits (The Atlantic Years)", "2006-10-27", "album",
     ["Goodbye for Now (2006 Remaster)", "Youth of the Nation (2006 Remaster)", "Alive (2006 Remaster)",
      "Boom (2006 Remaster)", "Will You (2006 Remaster)"]),
    ("SoCal Sessions", "2014-11-17", "album", ["Alive (Acoustic Version)", "Youth Of The Nation (Acoustic Version)"]),
    ("Goodbye for Now", "2006-03-03", "single", ["Goodbye for Now"]),
]
SONGS = ["Youth of the Nation", "Alive", "Boom", "Goodbye for Now", "Will You", "Celestial", "Set It Off"]


def disco(rows):
    return [{"title": a, "date": d, "tracks": list(t)} for a, d, kind, t in rows if kind in ("album", "ep")]


def test_each_song_counts_for_the_album_it_first_came_out_on(app):
    import discover_stats as ds
    got = ds.album_to_buy(SONGS, disco(POD))
    # Satellite, not the Greatest Hits or the 1997 Live; Will You came out on Payable on Death in 2003, before
    # the Greatest Hits copy, and ties with Goodbye for Now's Greatest Hits, so the earlier album is named
    assert got == {"album": "Satellite", "count": 5, "of": 7, "then": "Payable on Death", "then_count": 1}, got


def test_live_albums_and_other_recordings_dont_count(app):
    import discover_stats as ds
    rows = [("Live", "1999-01-01", "album", ["Echo", "Headstrong", "Still Frame"]),
            ("Headstrong", "2023-05-01", "ep", ["Headstrong (Re-Recorded)", "Echo (Acoustic Version)"]),
            ("Trapt", "2002-11-05", "album", ["Echo", "Headstrong", "Still Frame (Radio Edit)"])]
    got = ds.album_to_buy(["Echo", "Headstrong", "Still Frame"], disco(rows))
    assert got == {"album": "Trapt", "count": 2, "of": 3}, got


def test_editions_fold_into_their_album(app):
    import discover_stats as ds
    assert ds.album_name("The End Begins - Digital Deluxe") == "The End Begins"
    assert ds.album_name("Seasons - Clean") == "Seasons"
    assert ds.album_name("Tantric (U.S. Version-Enh'd)") == "Tantric"
    assert ds.album_name("Someone In Control (CD Only Ltd. Edition)") == "Someone In Control"
    assert ds.album_name("(What's the Story) Morning Glory?") == "(What's the Story) Morning Glory?"
    rows = [("The End Begins - Digital Deluxe", "2008-04-29", "album", ["Down And Out", "Love Song"]),
            ("The End Begins", "2008-04-29", "album", ["Regret", "Monopoly (Clean)"])]
    got = ds.album_to_buy(["Down And Out", "Love Song", "Regret", "Monopoly"], disco(rows))
    assert got == {"album": "The End Begins", "count": 4, "of": 4}, got


def test_a_remaster_or_a_credit_is_the_original_and_a_title_in_brackets_stays_one(app):
    import discover_stats as ds
    assert ds.original_recording("Goodbye for Now (2006 Remaster)")
    assert ds.original_recording("Song - Remastered 2009")
    assert ds.original_recording("Outbreak (feat. Cory Brandan)")
    assert ds.original_recording("Scars (The Echo Song)")
    assert not ds.original_recording("Payback (Live)")
    assert not ds.original_recording("Dig (Radio Edit)")
    assert not ds.original_recording("Black - Live At The Garage")


def test_spread_about_and_too_little_to_say(app):
    import discover_stats as ds
    rows = [("One", "2000-01-01", "album", ["A"]), ("Two", "2001-01-01", "album", ["B"]),
            ("Three", "2002-01-01", "album", ["C"])]
    assert ds.album_to_buy(["A", "B", "C"], disco(rows)) == {"spread": 3}
    assert ds.album_to_buy(["A", "Z"], disco(rows)) is None, "one song found: nothing worth saying"
    assert ds.album_to_buy(["A", "B"], []) is None, "Deezer doesn't know them"


def test_the_discography_is_read_once_and_a_silent_deezer_isnt_kept(app):
    import discover_stats as ds
    app.web.discography["P.O.D."] = POD
    app.web.down.add("deezer")
    assert ds.album_line("P.O.D.", SONGS) is None, "no answer: no line"
    app.web.down.discard("deezer")
    got = ds.album_line("P.O.D.", SONGS)
    assert got["album"] == "Satellite", got
    tracks = [c for c in app.web.calls if c[0] == "deezer" and c[1].endswith("/tracks")]
    assert len(tracks) == 6, "albums and EPs only: the single isn't read"
    before = len(app.web.calls)
    assert ds.album_line("P.O.D.", SONGS) == got
    assert len(app.web.calls) == before, "the second look is from what was kept"


def test_the_line_reads_as_drawn(app):
    import artists_gui
    assert artists_gui.album_text({"album": "Odessey and Oracle", "count": 3, "of": 4, "then": "Begin Here",
                                   "then_count": 1}) == "Odessey and Oracle (3 of 4), then Begin Here (1)"
    assert artists_gui.album_text({"album": "Trapt", "count": 2, "of": 3}) == "Trapt (2 of 3)"
    assert artists_gui.album_text({"spread": 7}) == "No one album: they're spread over 7."
