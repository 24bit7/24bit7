"""Tidal as a source: similar tracks and artists, keys, failing soft, and Settings' !!."""

import os

import pytest

try:   # the full interface on a virtual screen, shared with test_gui.py
    from test_gui import ui  # noqa: F401
except Exception:   # no Tk here: the GUI test below skips
    pass


def tidal_on(app, tracks=True, artists=False):
    app.set_env(TIDAL_CLIENT_ID="test-id", TIDAL_CLIENT_SECRET="test-secret",
                SIMILAR_TRACK_SOURCES="lastfm,tidal" if tracks else "lastfm",
                SIMILAR_SOURCES="lastfm,tidal" if artists else "lastfm")


def seed(app):
    a = next(a for a in app.web.artists if app.web.top_tracks(a))
    return a, app.web.top_tracks(a)[0]


def test_similar_tracks_studio_version_and_paging(app):
    tidal_on(app)
    e = app.engine
    artist, track = seed(app)
    tid = e.tidal_track_id(artist, track)
    assert app.web._tidal_get("tracks", tid) == (artist, track, "")   # the live take is passed over
    pairs = e.tidal_similar_tracks(artist, track, limit=30)
    expected = [list(p) for p in app.web.similar_tracks(artist, track)][:30]
    assert pairs == expected and len(pairs) > 20                       # two pages followed


def test_similar_artists(app):
    tidal_on(app, artists=True)
    artist, _ = seed(app)
    names = app.engine.tidal_similar(artist, limit=10)
    assert names and artist not in names
    assert names == [app.engine.canonicalise_conjunction(n) for n in app.web.similar_artists(artist)[:10]]


def test_blended_with_the_other_sources(app):
    tidal_on(app)
    artist, track = seed(app)
    lines = app.Lines()
    blended, answered = app.engine.similar_track_candidates([artist], track, report=lines)
    assert "Tidal" in answered and "Last.fm" in answered
    assert any("Tidal" in sources for _, sources in blended)
    assert lines.has("Tidal:")


def test_no_keys_skips_tidal(app):
    app.set_env(TIDAL_CLIENT_ID="", TIDAL_CLIENT_SECRET="", SIMILAR_TRACK_SOURCES="lastfm,tidal",
                SIMILAR_SOURCES="lastfm,tidal")
    e = app.engine
    assert not e.source_has_key("tidal")
    artist, track = seed(app)
    lines = app.Lines()
    _, answered = e.similar_track_candidates([artist], track, report=lines)
    assert answered == ["Last.fm"] and lines.has("Tidal is ticked but has no key")
    assert any("Tidal" in n for n in e.missing_key_notes(similar=True))
    assert not [c for c in app.web.calls if c[0] == "tidal"]


def test_tidal_down_fails_soft(app):
    tidal_on(app, artists=True)
    app.web.down.add("tidal")
    e = app.engine
    artist, track = seed(app)
    assert e.tidal_similar_tracks(artist, track) == []
    assert e.tidal_similar(artist) == []
    _, answered = e.similar_track_candidates([artist], track, report=app.Lines())
    assert answered == ["Last.fm"]


def test_tidal_is_a_top_track_source(app):
    assert app.engine.PROVIDERS["tidal"][2] is app.engine.tidal_top_tracks


def test_token_reused(app):
    tidal_on(app, artists=True)
    artist, track = seed(app)
    app.engine.tidal_similar_tracks(artist, track)
    app.engine.tidal_similar(artist)
    logins = [c for c in app.web.calls if c[0] == "tidal" and c[1] == "/v1/oauth2/token"]
    assert len(logins) == 1


def test_settings_lists(app):
    import settings_gui as s
    assert ("tidal", "Tidal") in s.SOURCE_NAMES and ("tidal", "Tidal") in s.TRACK_SOURCE_NAMES
    assert "tidal" in [c for c, _ in s.TOP_SOURCE_NAMES]
    assert "TIDAL_CLIENT_ID" in s.KEY_FIELDS and "TIDAL_CLIENT_SECRET" in s.KEY_FIELDS
    assert "TIDAL_CLIENT_ID" in s.KEY_HELP


@pytest.mark.skipif(not os.environ.get("DISPLAY") and os.name != "nt", reason="needs a display")
def test_no_weak_mark_any_more(app, ui):
    import tkinter as tk
    from tkinter import ttk
    from test_gui import visit_every_page
    pane = next(c for c in ui.settings.winfo_children() if hasattr(c, "select"))
    ui.nb.select(ui.settings)
    ui.pump(0.5)
    visit_every_page(ui, pane)
    marks = []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Label) and c.cget("text") == "!!":
                marks.append(c)
            walk(c)
    walk(ui.settings)
    # Similar Artists' Tidal only: each !! sits on its own source line, never in Drift's row of ticks
    assert not marks   # the !! went in 1.18.0: Test My Sources shows the same with real figures
