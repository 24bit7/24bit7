"""
Artist's Top Tracks from what's playing: Playing Now is cut back to the current
track and the top tracks queued after it. When the playing song is itself one of
the artist's top tracks, it must not be queued a second time.
"""


def test_playing_seed_is_not_queued_again(app):
    app.set_env(TOP_TRACKS_COUNT="5", TOP_TRACKS_ORDER="popular")
    e = app.engine
    key = next(k for k, r in app.jriver.by_key.items() if r["Artist"] == "Queen" and r["Name"] == "Bohemian Rhapsody")
    app.jriver.play("Speakers", [key])   # Bohemian Rhapsody is playing, and it's Queen's top track
    r = app.Lines()
    e.play_top_n(report=r)              # no seed handed in: builds from what's playing
    titles = app.jriver.titles("Speakers")
    assert titles[0] == "Queen - Bohemian Rhapsody", r.text()
    assert titles.count("Queen - Bohemian Rhapsody") == 1, titles
    assert len(titles) == len(set(titles)), titles
    assert r.has("Playing now: Queen - Bohemian Rhapsody"), r.text()


def test_searched_seed_still_opens_the_playlist(app):
    app.set_env(TOP_TRACKS_COUNT="5", TOP_TRACKS_ORDER="popular")
    e = app.engine
    r = app.Lines()
    e.play_top_n(report=r, seed_info=e.typed_seed_info("Queen", "Bohemian Rhapsody"))
    titles = app.jriver.titles("Speakers")
    assert titles[0] == "Queen - Bohemian Rhapsody" and titles.count("Queen - Bohemian Rhapsody") == 1, r.text()
    assert not r.has("Playing now:")
