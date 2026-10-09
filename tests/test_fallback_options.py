"""
If All Else Fails options: off to start; Shuffle Genre, Run File or Play Playlist when on.
"""

import os

import pytest

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_if_all_else_fails import nothing_found  # noqa: F401
from test_if_all_else_fails import QUIET


def build(app, e):
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=e.typed_seed_info("The Beatles", "Something"))
    return r


def test_off_to_start(app, nothing_found):
    for k in ("IF_ALL_ELSE_FAILS_ARTISTS", "IF_ALL_ELSE_FAILS_TRACKS", "IF_ALL_ELSE_FAILS_TOP", "IF_ALL_ELSE_FAILS_VIBE"):
        os.environ.pop(k, None)
    assert not nothing_found.fallback_on("tracks")
    assert nothing_found.fallback_mode("tracks") == "shuffle"


def test_play_playlist(app, nothing_found):
    e = nothing_found
    app.set_env(IF_ALL_ELSE_FAILS_TRACKS_MODE="playlist", IF_ALL_ELSE_FAILS_TRACKS_PLAYLIST="201",
                IF_ALL_ELSE_FAILS_TRACKS_PLAYLIST_NAME="Sunday Morning")
    r = build(app, e)
    assert r.has("I couldn't find a match, playing Sunday Morning."), r.text()
    want = next(p["keys"] for p in app.jriver.playlists if p["ID"] == "201")
    sent = [str(k) for k in app.jriver.zone("Speakers").playlist]
    assert [str(k) for k in want] == [k for k in sent if k in {str(x) for x in want}], (want, sent)
    assert not e.LAST_NO_MATCH


def test_missing_playlist_says_so(app, nothing_found):
    app.set_env(IF_ALL_ELSE_FAILS_TRACKS_MODE="playlist", IF_ALL_ELSE_FAILS_TRACKS_PLAYLIST="999",
                IF_ALL_ELSE_FAILS_TRACKS_PLAYLIST_NAME="Gone")
    r = build(app, nothing_found)
    assert r.has("If All Else Fails' playlist Gone"), r.text()
    assert not r.has("shuffling songs"), r.text()
    assert nothing_found.LAST_NO_MATCH


def test_run_file_skips_run_after_building(app, nothing_found, monkeypatch, tmp_path):
    import subprocess
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **k: started.append(args))
    script = tmp_path / "AutoPlay.bat"
    script.write_text("@echo off")
    other = tmp_path / "Other.bat"
    other.write_text("@echo off")
    app.set_env(IF_ALL_ELSE_FAILS_TRACKS_MODE="file", IF_ALL_ELSE_FAILS_TRACKS_PATH=str(script),
                RUN_AFTER_TRACKS="1", RUN_AFTER_TRACKS_PATH=str(other))
    r = build(app, nothing_found)
    assert r.has("I couldn't find a match, running AutoPlay."), r.text()
    assert r.has("Ran AutoPlay.bat (If All Else Fails)."), r.text()
    assert r.has("Run After Building skipped, as If All Else Fails ran a file instead."), r.text()
    assert len(started) == 1 and str(script) in started[0], started
    assert not nothing_found.LAST_NO_MATCH
    assert not app.jriver.zone("Speakers").playlist[1:]


def test_missing_file_says_so(app, nothing_found):
    app.set_env(IF_ALL_ELSE_FAILS_TRACKS_MODE="file", IF_ALL_ELSE_FAILS_TRACKS_PATH="C:/nowhere/x.bat")
    r = build(app, nothing_found)
    assert r.has("wasn't found"), r.text()
    assert nothing_found.LAST_NO_MATCH


def test_voice_hears_the_playlist_name(app, nothing_found, monkeypatch):
    said = []
    monkeypatch.setattr(nothing_found, "speak_in_zone", lambda text, zone, report=print: said.append(text) or 0.1)
    app.set_env(IF_ALL_ELSE_FAILS_TRACKS_MODE="playlist", IF_ALL_ELSE_FAILS_TRACKS_PLAYLIST="203",
                IF_ALL_ELSE_FAILS_TRACKS_PLAYLIST_NAME="60s Smartlist")
    nothing_found.OUTPUT_OVERRIDE = "Speakers"
    try:
        build(app, nothing_found)
    finally:
        nothing_found.OUTPUT_OVERRIDE = None
    assert said == ["I couldn't find a match, playing 60s Smartlist"], said


def test_settings_rows_follow_the_choice(app, ui):
    from tkinter import ttk
    import settings_gui
    from test_settings_seed_columns import option_page, walk
    page = option_page(ui, option="Similar Tracks")
    tick = next(w for w in walk(page) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "If nothing is found")
    box = next(w for w in walk(page) if isinstance(w, ttk.Combobox) and "Run File" in w.cget("values"))
    browse = next(w for w in walk(page) if isinstance(w, ttk.Button) and w.cget("text") == "Browse..."
                  and not any(isinstance(c, ttk.Checkbutton) for c in w.master.winfo_children()))
    choose = next(w for w in walk(page) if isinstance(w, ttk.Button) and w.cget("text") == "Choose...")
    assert str(box.cget("state")) == "disabled"
    tick.invoke()
    ui.pump(0.2)
    for label, file_on, list_on in (("Run File", True, False), ("Play Playlist", False, True),
                                    ("Shuffle Genre", False, False)):
        box.set(label)
        box.event_generate("<<ComboboxSelected>>")
        ui.pump(0.3)
        assert (browse.master.winfo_manager() == "grid") == file_on, label
        assert (choose.master.winfo_manager() == "grid") == list_on, label
    env = settings_gui.read_env()
    assert env.get("IF_ALL_ELSE_FAILS_TRACKS") == "1" and env.get("IF_ALL_ELSE_FAILS_TRACKS_MODE") == "shuffle"
    assert "IF_ALL_ELSE_FAILS_TRACKS_MODE" in app.engine.PROFILE_KEYS["playlist"]


def w_is_frame(w):
    return w.winfo_class() == "Frame"


def test_playlist_picker_chooses(app, ui):
    import settings_gui
    got = []
    win = settings_gui.choose_playlist(ui.nb, got.append)
    ui.pump(0.2)
    lb = next(w for w in win.winfo_children() if w.winfo_class() == "Listbox")
    names = list(lb.get(0, "end"))
    assert any(n.startswith("Sunday Morning") for n in names), names
    i = next(n for n, x in enumerate(names) if x.startswith("Sunday Morning"))
    lb.selection_set(i)
    from tkinter import ttk
    choose = next(w for f in win.winfo_children() if w_is_frame(f) for w in f.winfo_children()
                  if isinstance(w, ttk.Button) and w.cget("text") == "Choose")
    choose.invoke()
    ui.pump(0.2)
    assert got and got[0]["ID"] == "201", got
