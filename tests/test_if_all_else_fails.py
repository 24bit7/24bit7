"""
If All Else Fails: a build that finds nothing shuffles songs in the seed's genre
(at a similar tempo where BPM tags allow), or says why it can't.
"""

from collections import Counter

import pytest

from test_gui import ui  # noqa: F401  (the GUI fixture)

QUIET = dict(DRIFT_ARTISTS="0", DRIFT_TRACKS="0", SKIP_PLAYED_ARTISTS="0", SKIP_PLAYED_TRACKS="0",
             AI_MODERATOR="off", IF_ALL_ELSE_FAILS_ARTISTS="1", IF_ALL_ELSE_FAILS_TRACKS="1",
             IF_ALL_ELSE_FAILS_TOP="1", IF_ALL_ELSE_FAILS_VIBE="1")


@pytest.fixture
def nothing_found(app, monkeypatch):
    """Every source comes back empty, so the build finds nothing at all."""
    e = app.engine
    monkeypatch.setattr(e, "blended_similar_artists", lambda *a, **k: ([], "none"))
    monkeypatch.setattr(e, "pick_top_tracks_for_artist", lambda *a, **k: ([], 0))
    monkeypatch.setattr(e, "similar_track_candidates", lambda *a, **k: ([], []))
    app.set_env(**QUIET)
    e.LAST_NO_MATCH = False
    return e


def artists_of(app):
    """The artists queued after the seed track (a searched track in the library plays first)."""
    return [t.split(" - ")[0] for t in app.jriver.titles("Speakers")[1:]]


def test_shuffles_the_seed_genre(app, nothing_found):
    r = app.Lines()
    nothing_found.create_similar_playlist(report=r, seed_info=nothing_found.typed_seed_info("The Beatles", "Something"))
    assert r.has("I couldn't find a match, shuffling songs in Rock."), r.text()
    assert r.has("Why: nothing was found beyond the seed track itself. Genre from the seed track's Genre tag."), r.text()
    names = artists_of(app)
    assert names and "The Beatles" not in names, names
    assert max(Counter(names).values()) <= int(nothing_found.TRACKS_PER_ARTIST_PICK)
    assert not nothing_found.LAST_NO_MATCH


def test_similar_tempo_when_bpm_tags_allow(app, nothing_found):
    import library
    j = app.jriver
    seed = j.key_of("The Beatles", "Something")
    rock = [r for r in j.by_key.values() if r["Genre"] == "Rock" and r["Artist"] != "The Beatles"]
    for n, row in enumerate(rock):
        row["BPM"] = "120" if n % 2 == 0 else "80"
    j.by_key[seed]["BPM"] = "118"
    library.load()
    r = app.Lines()
    nothing_found.create_similar_playlist(report=r, seed_info=nothing_found.typed_seed_info("The Beatles", "Something"))
    assert r.has("I couldn't find a match, shuffling songs in Rock at a similar tempo."), r.text()
    sent = app.jriver.zone("Speakers").playlist[1:]
    assert sent and all(j.by_key[k]["BPM"] == "120" for k in sent), [j.by_key[k]["BPM"] for k in sent]


def test_off_says_why_and_sends_nothing(app, nothing_found):
    app.set_env(IF_ALL_ELSE_FAILS_ARTISTS="0")
    r = app.Lines()
    nothing_found.create_similar_playlist(report=r,
                                          seed_info=nothing_found.typed_seed_info("The Beatles", "A Song Nobody Has"))
    assert r.has("I couldn't find a match. Please try another seed."), r.text()
    assert r.has("If All Else Fails is off"), r.text()
    assert not app.jriver.zone("Speakers").playlist
    assert nothing_found.LAST_NO_MATCH


def test_no_genre_no_fallback(app, nothing_found):
    r = app.Lines()
    nothing_found.create_similar_playlist(report=r, seed_info=nothing_found.typed_seed_info("Nobody Anyone Knows", ""))
    assert r.has("there's no genre for the seed in your library"), r.text()
    assert nothing_found.LAST_NO_MATCH


def test_artist_seed_uses_the_artists_most_common_genre(app, nothing_found):
    r = app.Lines()
    nothing_found.create_similar_playlist(report=r, seed_info=nothing_found.typed_seed_info("Simon & Garfunkel", ""))
    assert r.has("shuffling songs in Folk"), r.text()
    assert r.has("Simon & Garfunkel's most common genre in your library"), r.text()


def test_similar_tracks_falls_back_too(app, nothing_found):
    r = app.Lines()
    nothing_found.create_similar_tracks_playlist(report=r,
                                                 seed_info=nothing_found.typed_seed_info("The Beatles", "Something"))
    assert r.has("shuffling songs in Rock"), r.text()
    assert "The Beatles" not in artists_of(app)


def test_review_mode_fills_the_review_list(app, nothing_found):
    e = nothing_found
    e.REVIEW_MODE, e.REVIEW_KEYS = True, []
    try:
        r = app.Lines()
        e.create_similar_playlist(report=r, seed_info=e.typed_seed_info("The Beatles", "Something"))
        assert e.REVIEW_KEYS, r.text()
        assert not app.jriver.zone("Speakers").playlist
    finally:
        e.REVIEW_MODE, e.REVIEW_KEYS = False, []


def test_voice_build_speaks_first(app, nothing_found, monkeypatch):
    said = []
    monkeypatch.setattr(nothing_found, "speak_in_zone", lambda text, zone, report=print: said.append(text) or 0.1)
    nothing_found.OUTPUT_OVERRIDE = "Speakers"
    try:
        r = app.Lines()
        nothing_found.create_similar_playlist(report=r,
                                              seed_info=nothing_found.typed_seed_info("The Beatles", "Something"))
    finally:
        nothing_found.OUTPUT_OVERRIDE = None
    assert said == ["I couldn't find a match, shuffling songs in Rock"], said
    assert app.jriver.zone("Speakers").playlist


def test_not_when_an_added_playlist_played(app, nothing_found, monkeypatch):
    monkeypatch.setattr(nothing_found, "send_mix_only", lambda *a, **k: 5)
    r = app.Lines()
    nothing_found.create_similar_playlist(report=r,
                                          seed_info=nothing_found.typed_seed_info("The Beatles", "A Song Nobody Has"))
    assert not r.has("shuffling songs") and not r.has("try another seed"), r.text()


def test_app_shows_no_match_message(app, ui, nothing_found, monkeypatch):
    import gui
    shown = []
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda title, text, **k: shown.append((title, text)))
    app.set_env(IF_ALL_ELSE_FAILS_ARTISTS="0")
    p = ui.play
    p.seed_nb.select(p.search_tab)
    p.search_artist.insert(0, "The Beatles")
    p.search_track.insert(0, "A Song Nobody Has")
    p.on_similar()
    ui.wait_idle()
    ui.pump(0.3)
    assert ("No Match", nothing_found.APP_NO_MATCH) in shown, shown


def test_setting_on_every_playlist_tab(app, ui):
    import tkinter as tk
    from tkinter import ttk
    import settings_gui
    from test_settings_seed_columns import option_page, walk
    for option in ("Similar Artists", "Similar Tracks", "Artist's Top Tracks", "AI Playlist"):
        page = option_page(ui, option=option)
        ticks = [w for w in walk(page) if isinstance(w, ttk.Checkbutton)
                 and w.cget("text") == "If nothing is found"]
        assert len(ticks) == 1, option
    page = option_page(ui, option="Similar Artists")
    tick = next(w for w in walk(page) if isinstance(w, ttk.Checkbutton)
                and w.cget("text") == "If nothing is found")
    tick.invoke()
    ui.pump(0.3)
    assert settings_gui.read_env().get("IF_ALL_ELSE_FAILS_ARTISTS") == "1"   # off to start, so one click turns it on
    device = option_page(ui, device="Kitchen Echo", option="Similar Artists")
    assert any(isinstance(w, ttk.Checkbutton) and w.cget("text") == "If nothing is found"
               for w in walk(device))
    assert "IF_ALL_ELSE_FAILS_ARTISTS" in app.engine.PROFILE_KEYS["playlist"]
