"""
Settings > Buttons: the Seed and Review Mode columns (Current Track | Playing Now, twice) on a
standard button's Playlist page only, each saving straight to .env.
"""

import tkinter as tk
from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import inner_page, pick_button


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def option_page(ui, button="Similar Artists"):
    """A button's Playlist page, built and on screen."""
    pick_button(ui, button)
    return inner_page(ui, "Playlist")


def row_cell(page, label, column):
    """The widget in the grid row titled label, in column (1 Current Track ... 4 Review Mode's Playing Now)."""
    title = next(w for w in walk(page) if isinstance(w, (tk.Label, ttk.Checkbutton))
                 and str(w.cget("text")) == label)
    row = int(title.grid_info()["row"])
    box = title.master
    found = [w for w in box.grid_slaves(row=row, column=column)]
    return found[0] if found else None


def spinbox_in(cell):
    return next(w for w in walk(cell) if isinstance(w, tk.Spinbox))


def mirror(page, text):
    return next(w for w in walk(page) if isinstance(w, ttk.Checkbutton) and w.cget("text") == text)


def test_main_has_four_columns(app, ui):
    page = option_page(ui)
    texts = [str(w.cget("text")) for w in walk(page) if isinstance(w, tk.Label)]
    for text in ("SEED", "REVIEW MODE", "Playing Now", "Artists sampled from Playing Now", "per sampled artist"):
        assert text in texts, text
    assert row_cell(page, "Artists sampled from Playing Now", 1) is None   # blank under Current Track
    assert mirror(page, "Mirror Current Track") and mirror(page, "Mirror Playing Now")
    assert not ui.errors, ui.errors


def test_playing_now_figures_save_to_env(app, ui):
    import settings_gui
    page = option_page(ui)
    sb = spinbox_in(row_cell(page, "Artists sampled from Playing Now", 2))
    sb.delete(0, "end")
    sb.insert(0, "7")
    ui.pump(0.2)
    assert settings_gui.read_env().get("PN_SAMPLE_ARTISTS") == "7"
    assert app.engine.playing_now_artist_figures()["PN_SAMPLE_ARTISTS"] == 7


def test_mirror_playing_now_greys_its_column(app, ui):
    import settings_gui
    page = option_page(ui)
    sb = spinbox_in(row_cell(page, "Number of artists", 4))
    assert str(sb.cget("state")) == "disabled"
    tick = mirror(page, "Mirror Playing Now")
    tick.invoke()   # untick: Review Mode's Playing Now column gets its own figures
    ui.pump(0.2)
    assert settings_gui.read_env().get("REVIEW_SAME_ARTISTS_PN") == "0"
    assert str(sb.cget("state")) == "normal"
    sb.delete(0, "end")
    sb.insert(0, "2")
    ui.pump(0.2)
    assert app.engine.playing_now_artist_figures(review=True)["PN_ARTISTS_PER_SAMPLE"] == 2
    assert app.engine.playing_now_artist_figures(review=False)["PN_ARTISTS_PER_SAMPLE"] == 4


def test_similar_tracks_columns(app, ui):
    import settings_gui
    page = option_page(ui, "Similar Tracks")
    sb = spinbox_in(row_cell(page, "Number of tracks", 2))
    assert sb.get() == "6"
    sb.delete(0, "end")
    sb.insert(0, "8")
    ui.pump(0.2)
    assert settings_gui.read_env().get("PN_TRACKS_PER_SAMPLE") == "8"
    texts = [str(w.cget("text")) for w in walk(page) if isinstance(w, tk.Label)]
    assert "Tracks sampled from Playing Now" in texts and texts.count("Every column") == 2


def test_review_mode_most_tracks_per_artist(app):
    app.set_env(REVIEW_SAME_TRACKS="0", REVIEW_SIMILAR_TRACK_PER_ARTIST="1")
    assert app.engine.review_overrides().get("SIMILAR_TRACK_PER_ARTIST") == "1"


def test_profiles_carry_the_new_settings(app):
    import profiles
    keys = profiles.env_keys()
    for key in ("PLAY_SEED", "PN_SAMPLE_ARTISTS", "PN_TRACKS_PER_SAMPLE", "REVIEW_SAME_ARTISTS_PN",
                "REVIEW_PN_SAMPLE_TRACKS", "REVIEW_SIMILAR_TRACK_PER_ARTIST"):
        assert key in keys, key
    assert "SEED_PLAYING_NOW_SEEN" not in keys   # the first-time note never comes back with a profile


def test_a_button_of_your_own_has_no_playing_now_column(app, ui):
    import buttons
    buttons.add("Sunday", "artists")
    page = option_page(ui, "Sunday")
    texts = [str(w.cget("text")) for w in walk(page) if isinstance(w, tk.Label)]
    assert "Playing Now" not in texts and "SEED" not in texts, texts
    assert not ui.errors, ui.errors
