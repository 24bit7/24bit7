"""The new-version line at start-up, in the console, with its download link clickable."""

import pytest

from test_gui import ui   # noqa: F401  (the GUI fixture)


@pytest.fixture
def newer(app):
    app.web.latest_release = {"tag_name": "v99.0.0", "html_url": "https://github.com/24bit7/24bit7/releases/tag/v99.0.0"}


def test_start_up_says_a_newer_version_is_out(app, newer, ui, monkeypatch):
    play = ui.play
    ui.pump(until=lambda: any("99.0.0 is out" in line for line in play._live), timeout=10)
    play._end_greeting()   # the line waits for the greeting, then goes on screen
    start, end = play.log.tag_ranges("release_link")[:2]
    assert play.log.get(start, end) == "https://github.com/24bit7/24bit7/releases/tag/v99.0.0"
    opened = []
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    play.log.see(start)
    ui.pump(0.1)
    x, y, _, _ = play.log.bbox(start)
    play.log.event_generate("<Motion>", x=x + 2, y=y + 2)   # Tk finds the tag under the mouse as it moves
    play.log.event_generate("<Button-1>", x=x + 2, y=y + 2)
    ui.pump(0.2)
    assert opened == ["https://github.com/24bit7/24bit7/releases/tag/v99.0.0"]
