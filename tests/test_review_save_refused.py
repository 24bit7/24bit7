"""
Review's Save when JRiver makes the playlist but refuses the tracks (Helmut, 18 Oct 2026: 401 Access denied).
The playlist is left empty, so the line says so in plain words, without JRiver's whole address.
"""

import threading
from types import SimpleNamespace

import pytest


def _keys(app, n=3):
    return [t["Key"] for t in app.jriver.tracks[:n]]


def test_refused_tracks_say_the_playlist_is_empty(app):
    app.jriver.refused.add("Playlist/AddFiles")
    with pytest.raises(app.engine.ReviewProblem) as e:
        app.engine.review_save(_keys(app), "Sunday Dub")
    line = str(e.value)
    assert line.startswith("Problem: ")
    assert '"Sunday Dub"' in line and "empty" in line
    assert "401" in line and "Settings > Keys" in line
    assert "http" not in line and "Keys=" not in line, "no JRiver address or track numbers"
    made = [p for p in app.jriver.playlists if p["Name"] == "Sunday Dub"]
    assert made and made[0]["keys"] == [], "the line matches what's in JRiver: an empty playlist"


def test_other_refusals_leave_out_the_login_hint(app):
    app.jriver.refused.add("Playlist/AddFiles")
    real = app.jriver.handle

    def as_500(method, path, params):
        r = real(method, path, params)
        if path == "Playlist/AddFiles":
            r.status_code = 500
        return r
    app.jriver.handle = as_500
    with pytest.raises(app.engine.ReviewProblem) as e:
        app.engine.review_save(_keys(app), "Sunday Dub")
    assert "500" in str(e.value) and "Settings > Keys" not in str(e.value)


def test_a_save_that_works_is_unchanged(app):
    line = app.engine.review_save(_keys(app), "Sunday Dub")
    assert line == 'Review: 3 tracks saved as the JRiver playlist "Sunday Dub".'


def test_review_shows_the_plain_line(app):
    import review_gui
    done = threading.Event()
    shown = []
    panel = SimpleNamespace(
        busy=False, _sync_buttons=lambda: None, status_label=SimpleNamespace(config=lambda **k: None),
        play=SimpleNamespace(root=SimpleNamespace(after=lambda ms, f: f())),
        _done=lambda line: (shown.append(line), done.set()))
    app.jriver.refused.add("Playlist/AddFiles")
    review_gui.ReviewPanel._run(panel, lambda: app.engine.review_save(_keys(app), "Sunday Dub"))
    assert done.wait(5)
    assert shown[0].startswith('Problem: JRiver made the playlist "Sunday Dub"')
    assert "couldn't send that" not in shown[0]
