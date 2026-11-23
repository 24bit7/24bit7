"""
The new-version note at start-up, found from GitHub on its own thread and shown in the console. Since 1.38.0 the
link is the note's Release Notes button rather than an underlined address (tests/test_whats_new_window.py has the
rest of the note); this one follows the whole way from GitHub's answer to the page opening.
"""

import pytest

from test_gui import ui   # noqa: F401  (the GUI fixture)

LINK = "https://github.com/24bit7/24bit7/releases/tag/v99.0.0"


@pytest.fixture
def newer(app):
    app.web.latest_release = {"tag_name": "v99.0.0", "html_url": LINK}


def test_start_up_says_a_newer_version_is_out(app, newer, ui, monkeypatch):
    play = ui.play
    play._end_greeting()   # the note waits for the greeting, then goes on screen
    ui.pump(until=lambda: getattr(play, "_whats_new_row", None) is not None, timeout=10)
    assert any("99.0.0 is out" in line for line in play._live)
    notes = next(w for w in play._whats_new_row.winfo_children() if w.cget("text") == "Release Notes")
    opened = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    play.log.see("whats_new_end")
    ui.pump(0.1)
    notes.event_generate("<Button-1>", x=2, y=2)
    ui.pump(0.2)
    assert opened == [LINK]
    assert not ui.errors, ui.errors[0]
