"""
Select From Hits on the playlist page (Ben, 25 Nov 2026, as drawn; a tick called Most Played until then, Use
Adaptive Selections until 23 Nov, Ben, 12 Nov 2026). A click-through, Off, ↓ and ↕, at the end of Similar Artists'
and Radio's first Playlist Selection sentence, ↓ by default; the sentence says what it does ("pick [5] of each
artist's hits, fewer if they have fewer, up to 8 if they have plenty"), the pool's box going while it's on. Saved
into the config like its other settings. Not on Similar Tracks, which picks no artist's top tracks; on Artist's
Top Tracks on a row of its own, off by default.
"""

import pytest

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button

pytestmark = pytest.mark.windows


def setting(name, key):
    import buttons
    b = next(x for x in buttons.load() if x["name"] == name)
    return (b.get("settings") or {}).get(key)


def test_down_by_default_at_the_end_of_the_sentence_which_it_rewords(app, ui):
    s = ui.settings
    pick_button(ui, "Similar Artists")
    ui.pump(0.4)
    p = s._button_page
    button = p.adaptive_tick
    line = p.hit_lines[0]
    assert button.cget("text") == "Select From Hits ↓", "down by default, as Most Played was on"
    assert button.master is line["row"], "in the sentence, at its end"
    assert line["top"].cget("text") == "of each artist's hits, fewer if they have fewer."
    assert not line["pool"].winfo_manager(), "the pool's box goes: the hits are the pool"
    button._step(1)
    ui.pump(0.3)
    assert button.cget("text") == "Select From Hits ↕"
    pick = int(line["pick"].get())
    assert line["top"].cget("text") == (f"of each artist's hits, fewer if they have fewer, up to "
                                        f"{-(-pick * 3 // 2)} if they have plenty.")
    assert setting("Similar Artists", "ADAPTIVE_ARTISTS") == "both"
    button._step(1)
    ui.pump(0.3)
    assert button.cget("text") == "Select From Hits: Off"
    assert line["top"].cget("text") == "of each artist's top" and line["pool"].winfo_manager(), "as before"
    assert setting("Similar Artists", "ADAPTIVE_ARTISTS") == "off"
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
    assert s._button_page.adaptive_tick.cget("text") == "Select From Hits ↓"
    assert not ui.errors, ui.errors[0]


def test_artists_top_tracks_has_it_off(app, ui):
    """On Artist's Top Tracks (Ben, 23 Nov 2026): off by default, so Top 15 still means fifteen; saved."""
    s = ui.settings
    pick_button(ui, "Artist's Top Tracks")
    ui.pump(0.4)
    button = s._button_page.adaptive_tick
    assert button.cget("text") == "Select From Hits: Off"
    button._step(1)
    ui.pump(0.3)
    assert setting("Artist's Top Tracks", "ADAPTIVE_TOP") == "down"
    assert not ui.errors, ui.errors[0]
