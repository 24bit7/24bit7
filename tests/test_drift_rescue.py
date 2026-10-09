"""
Drift picks up an empty build: with Custom Sources it starts from the seed itself; on the
same sources as the playlist it says why it can't, and If All Else Fails runs as before.
"""

import pytest

from test_gui import ui  # noqa: F401  (the GUI fixture)

STONES = ("The Rolling Stones", "The Last Time")
BASE = dict(DRIFT_TRACKS="1", DRIFT_TRACKS_USING="tracks", DRIFT_TRACKS_ROUNDS="1", SIMILAR_TRACK_SOURCES="ai",
            SKIP_PLAYED_TRACKS="0", AI_MODERATOR_TRACKS="off", AI_MODERATOR="off", IF_ALL_ELSE_FAILS_TRACKS="1")


@pytest.fixture
def ai_finds_nothing(app, monkeypatch):
    """The playlist's own source finds nothing; Last.fm (Drift's Custom Source) knows one track."""
    e = app.engine
    asked = []

    def candidates(artists, title, report=print):
        asked.append(list(e.SIMILAR_TRACK_SOURCES))
        if e.SIMILAR_TRACK_SOURCES == ["lastfm"]:
            return [(STONES, ["Last.fm"])], ["Last.fm"]
        return [], []
    monkeypatch.setattr(e, "similar_track_candidates", candidates)
    e.LAST_NO_MATCH = False
    return e, asked


def build(app, e):
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=e.typed_seed_info("The Beatles", "Something"))
    return r


def test_custom_sources_pick_up_an_empty_build(app, ai_finds_nothing):
    e, asked = ai_finds_nothing
    app.set_env(**BASE, DRIFT_TRACKS_SOURCES_MODE="custom", DRIFT_TRACKS_TRACK_SOURCES="lastfm")
    r = build(app, e)
    assert r.has("Drift: nothing found, so it starts from the seed, using tracks similar to "
                 "The Beatles - Something (from Last.fm)..."), r.text()
    assert r.has("Drift: 1 found from the seed."), r.text()
    assert "The Rolling Stones - The Last Time" in app.jriver.titles("Speakers"), app.jriver.titles("Speakers")
    assert not r.has("I couldn't find a match"), r.text()
    assert ["lastfm"] in asked


def test_same_sources_say_why_and_fall_through(app, ai_finds_nothing):
    e, asked = ai_finds_nothing
    app.set_env(**BASE, DRIFT_TRACKS_SOURCES_MODE="same")
    r = build(app, e)
    assert r.has("Drift: nothing to start from, and it uses the same sources as the playlist"), r.text()
    assert r.has("I couldn't find a match"), r.text()
    assert ["lastfm"] not in asked


def test_drift_off_stays_quiet(app, ai_finds_nothing):
    e, _ = ai_finds_nothing
    app.set_env(**dict(BASE, DRIFT_TRACKS="0"), DRIFT_TRACKS_SOURCES_MODE="custom",
                DRIFT_TRACKS_TRACK_SOURCES="lastfm")
    r = build(app, e)
    assert not [l for l in r if "Drift:" in l], r.text()


def test_nothing_from_the_seed_either(app, monkeypatch, ai_finds_nothing):
    e, _ = ai_finds_nothing
    monkeypatch.setattr(e, "similar_track_candidates", lambda *a, **k: ([], []))
    app.set_env(**BASE, DRIFT_TRACKS_SOURCES_MODE="custom", DRIFT_TRACKS_TRACK_SOURCES="lastfm")
    r = build(app, e)
    assert r.has("Drift: nothing found from the seed either."), r.text()
    assert r.has("I couldn't find a match"), r.text()


def test_similar_artists_pick_up_an_empty_build(app, monkeypatch):
    e = app.engine
    app.set_env(DRIFT_ARTISTS="1", DRIFT_ARTISTS_USING="artists", DRIFT_ARTISTS_ROUNDS="1",
                DRIFT_ARTISTS_SOURCES_MODE="custom", DRIFT_ARTISTS_ARTIST_SOURCES="lastfm",
                SIMILAR_SOURCES="ai", SKIP_PLAYED_ARTISTS="0", AI_MODERATOR_ARTISTS="off", AI_MODERATOR="off")

    def similar(seed, limit=10, **k):
        return ([("The Rolling Stones", ["Last.fm"])], "Last.fm") if e.SIMILAR_SOURCES == ["lastfm"] else ([], "none")
    monkeypatch.setattr(e, "blended_similar_artists", similar)
    real_pick = e.pick_top_tracks_for_artist

    def pick(artist, *a, **k):   # the seed artist has nothing either, so the build is empty
        return ([], 0) if artist == "The Beatles" else real_pick(artist, *a, **k)
    monkeypatch.setattr(e, "pick_top_tracks_for_artist", pick)
    r = app.Lines()
    e.create_similar_playlist(report=r, seed_info=e.typed_seed_info("The Beatles", "Something"))
    assert r.has("Drift: nothing found, so it starts from the seed, using artists similar to The Beatles"), r.text()
    assert any(t.startswith("The Rolling Stones - ") for t in app.jriver.titles("Speakers")), \
        app.jriver.titles("Speakers")


def test_settings_note_follows_the_sources_choice(app, ui):
    from tkinter import ttk
    import settings_gui
    from test_settings_seed_columns import option_page, walk
    for option in ("Similar Artists", "Similar Tracks"):
        page = option_page(ui, option=option)
        warn = next(w for w in walk(page) if w.winfo_class() == "Label"
                    and str(w.cget("text")) == settings_gui.DRIFT_SAME_WARNING)
        box = next(w for w in walk(page) if isinstance(w, ttk.Combobox)
                   and "Custom Sources" in w.cget("values"))
        box.set("Custom Sources")
        box.event_generate("<<ComboboxSelected>>")
        ui.pump(0.2)
        assert warn.winfo_manager() == "", option
        box.set("Same as Settings > Sources")
        box.event_generate("<<ComboboxSelected>>")
        ui.pump(0.2)
        assert warn.winfo_manager() == "grid", option
    page = option_page(ui, option="AI Playlist")
    assert not [w for w in walk(page) if w.winfo_class() == "Label"
                and str(w.cget("text")) == settings_gui.DRIFT_SAME_WARNING]
