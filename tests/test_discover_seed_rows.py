"""
Discover with Playing Now builds: the session reads "Playing Now (Multiple Tracks)", and each
row's Seed is the sampled Playing Now track it came from. Plus the size 9 search boxes.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)

QUIET = dict(DRIFT_ARTISTS="0", DRIFT_TRACKS="0", SKIP_PLAYED_ARTISTS="0", SKIP_PLAYED_TRACKS="0",
             AI_MODERATOR="off")


def play_mix(app):
    j = app.jriver
    j.play("Speakers", [j.key_of("Queen", "Bohemian Rhapsody"), j.key_of("The Hollies", "Bus Stop"),
                        j.key_of("The Byrds", "Mr. Tambourine Man"), j.key_of("Badfinger", "Baby Blue")])
    return {"Queen - Bohemian Rhapsody", "The Hollies - Bus Stop", "The Byrds - Mr. Tambourine Man",
            "Badfinger - Baby Blue"}


def test_similar_artists_rows_carry_their_seed_track(app):
    app.set_env(PN_SAMPLE_ARTISTS="4", PN_ARTISTS_PER_SAMPLE="2", **QUIET)
    seeds = play_mix(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                       playing_now=True)
    rows = app.engine.list_discoveries()
    assert rows, r.text()
    assert {row["seed"] for row in rows} <= seeds, {row["seed"] for row in rows}
    assert len({row["seed"] for row in rows}) > 1
    assert rows[0]["seed_artist"] == "Playing Now (Multiple Tracks)"
    sessions = app.engine.list_sessions()
    assert "Playing Now (Multiple Tracks)" in [s[3] for s in sessions]


def test_similar_tracks_rows_carry_their_seed_track(app):
    app.set_env(PN_SAMPLE_TRACKS="3", PN_TRACKS_PER_SAMPLE="2", **QUIET)
    seeds = play_mix(app)
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                              playing_now=True)
    rows = app.engine.list_discoveries()
    assert rows and all(row["seed"] in seeds for row in rows), [row["seed"] for row in rows]


def test_current_track_rows_keep_the_session_seed(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    rows = app.engine.list_discoveries()
    assert rows and all(row["seed"] is None for row in rows)


def test_discover_shows_the_seed_track(app, ui):
    app.set_env(PN_SAMPLE_ARTISTS="4", PN_ARTISTS_PER_SAMPLE="2", **QUIET)
    seeds = play_mix(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.seed_or_last_played(report=r),
                                       playing_now=True)
    d = ui.discover
    d.ensure_loaded()
    d.filter_menu.set("All")
    d._on_filter_changed()
    ui.pump(0.8)
    shown = {d.tree.item(i, "values")[1] for i in d.tree.get_children()}
    assert shown and shown <= seeds, shown
    assert any("Playing Now (Multiple Tracks)" in v for v in d.session_menu.cget("values")), \
        d.session_menu.cget("values")


def test_search_boxes_are_size_9(app, ui):
    for box in (ui.play.search_artist, ui.play.search_track, ui.discover.search_box):
        import tkinter.font as tkfont
        assert tkfont.Font(font=box.entry.cget("font")).actual("size") == 9, box.entry.cget("font")
