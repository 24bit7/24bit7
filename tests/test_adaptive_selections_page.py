"""
Most Played (Use Adaptive Selections until 23 Nov 2026) on the playlist page (Ben, 12 Nov 2026): a tick in Similar Artists' and Radio's
Playlist Selection, above "Skip tracks played in the last [n] days", on by default, its note on the tick.
Saved into the config like its other settings. Not on Similar Tracks, which picks no artist's top tracks.
"""

import pytest

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button

pytestmark = pytest.mark.windows


def setting(name, key):
    import buttons
    b = next(x for x in buttons.load() if x["name"] == name)
    return (b.get("settings") or {}).get(key)


def test_ticked_by_default_above_skip_played_and_saved(app, ui):
    s = ui.settings
    pick_button(ui, "Similar Artists")
    ui.pump(0.4)
    p = s._button_page
    tick = p.adaptive_tick
    assert tick.cget("text") == "Most Played" and tick.instate(["selected"]), "on by default"
    skip = p.played_boxes["artists"].master
    assert tick.master.grid_info()["row"] < skip.grid_info()["row"], "above Skip tracks played"
    tick.invoke()
    ui.pump(0.3)
    assert setting("Similar Artists", "ADAPTIVE_ARTISTS") == "0"
    tick.invoke()
    ui.pump(0.3)
    assert setting("Similar Artists", "ADAPTIVE_ARTISTS") == "1"
    pick_button(ui, "Similar Tracks")
    ui.pump(0.4)
    assert getattr(s._button_page, "adaptive_tick", None) is None, "Similar Tracks picks no artist's top tracks"
    assert not ui.errors, ui.errors[0]


def test_radio_has_it_too(app, ui):
    import buttons
    s = ui.settings
    radio, _page = buttons.add_from_choice(("template", "radio"))
    pick_button(ui, radio["name"])
    ui.pump(0.4)
    assert s._button_page.adaptive_tick.instate(["selected"])
    assert not ui.errors, ui.errors[0]


def test_artists_top_tracks_has_it_unticked(app, ui):
    """Most Played on Artist's Top Tracks (Ben, 23 Nov 2026): off by default, saved into the playlist."""
    s = ui.settings
    pick_button(ui, "Artist's Top Tracks")
    ui.pump(0.4)
    tick = s._button_page.adaptive_tick
    assert tick.cget("text") == "Most Played" and not tick.instate(["selected"]), "off by default"
    tick.invoke()
    ui.pump(0.3)
    assert setting("Artist's Top Tracks", "ADAPTIVE_TOP") == "1"
    assert not ui.errors, ui.errors[0]
