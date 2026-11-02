"""
Playlist Selection as sentences (Ben, 2 Nov 2026), in place of the Seed and Review Mode columns: "When Seed
is Current Track" and, on a standard playlist, "When Seed is Playing Now", each a line with its boxes in it;
"Separate Settings for Review Mode" ticked shows the two lines again in an orange box, saved as REVIEW_ keys.
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
    """A button's page, built and on screen (other test files import this, so it stays a single widget)."""
    pick_button(ui, button)
    return inner_page(ui, "Playlist")


def option_pair(ui, button="Similar Artists"):
    """(the scrolling page, its ProfilePage)."""
    return option_page(ui, button), ui.settings._button_page


def texts_in(page):
    return [str(w.cget("text")) for w in walk(page) if isinstance(w, (tk.Label, ttk.Checkbutton))]


def set_box(sb, value, ui):
    sb.delete(0, "end")
    sb.insert(0, value)
    ui.pump(0.2)


def test_the_standard_playlist_has_both_seed_lines_and_the_review_tick(app, ui):
    page, p = option_pair(ui)
    texts = texts_in(page)
    for text in ("Playlist Selection", "When Seed is Current Track", "When Seed is Playing Now", "Limit To", "tracks, from",
                 "artists, pick", "of each artist's top", "artists from Playing Now, take", "Separate Settings for Review Mode"):
        assert text in texts, text
    assert not {"SEED", "REVIEW MODE", "Mirror Playing Now", "Artists sampled from Playing Now"} & set(texts), "the columns are gone"
    assert set(p.seed_boxes) == {"current", "pn", "review_current", "review_pn"}
    assert p.seed_boxes["current"]["TRACKS_PER_ARTIST_PICK"] is p.pick_sb
    assert not ui.errors, ui.errors


def test_the_current_track_line_saves_into_the_playlist_and_the_limit_tick_greys_its_box(app, ui):
    import buttons
    page, p = option_pair(ui)
    boxes = p.seed_boxes["current"]
    set_box(boxes["SIMILAR_ARTIST_LIMIT"], "9", ui)
    assert buttons.standard("artists")["settings"]["SIMILAR_ARTIST_LIMIT"] == "9"
    assert str(boxes["SIMILAR_ARTIST_TRACK_COUNT"].cget("state")) == "normal"
    boxes["SIMILAR_ARTIST_TRACK_LIMIT"].invoke()   # untick Limit To
    ui.pump(0.2)
    assert str(boxes["SIMILAR_ARTIST_TRACK_COUNT"].cget("state")) == "disabled"
    assert buttons.standard("artists")["settings"]["SIMILAR_ARTIST_TRACK_LIMIT"] == "0"
    assert not ui.errors, ui.errors


def test_playing_now_figures_save_to_env(app, ui):
    import settings_gui
    page, p = option_pair(ui)
    set_box(p.seed_boxes["pn"]["PN_SAMPLE_ARTISTS"], "7", ui)
    assert settings_gui.read_env().get("PN_SAMPLE_ARTISTS") == "7"
    assert app.engine.playing_now_artist_figures()["PN_SAMPLE_ARTISTS"] == 7


def test_separate_review_settings_show_the_orange_box_and_save_as_review_keys(app, ui):
    import settings_gui
    page, p = option_pair(ui)
    s = ui.settings
    var, frame = s._review_vars["separate"], None
    assert var.get() is False and all(v.get() for v in s._review_vars["same"].values()), "mirroring to start"
    sb = p.seed_boxes["review_pn"]["PN_ARTISTS_PER_SAMPLE"]
    assert not sb.winfo_ismapped(), "the review lines are hidden while mirroring"
    var.set(True)
    ui.pump(0.3)
    assert settings_gui.read_env().get("REVIEW_SAME_ARTISTS") == "0" and settings_gui.read_env().get("REVIEW_SAME_ARTISTS_PN") == "0"
    assert sb.winfo_ismapped() and not any(v.get() for v in s._review_vars["same"].values())
    set_box(sb, "2", ui)
    assert app.engine.playing_now_artist_figures(review=True)["PN_ARTISTS_PER_SAMPLE"] == 2
    assert app.engine.playing_now_artist_figures(review=False)["PN_ARTISTS_PER_SAMPLE"] == 4
    var.set(False)
    ui.pump(0.3)
    assert settings_gui.read_env().get("REVIEW_SAME_ARTISTS") == "1" and not sb.winfo_ismapped()
    assert not ui.errors, ui.errors


def test_similar_tracks_lines(app, ui):
    import settings_gui
    page, p = option_pair(ui, "Similar Tracks")
    sb = p.seed_boxes["pn"]["PN_TRACKS_PER_SAMPLE"]
    assert sb.get() == "6"
    set_box(sb, "8", ui)
    assert settings_gui.read_env().get("PN_TRACKS_PER_SAMPLE") == "8"
    texts = texts_in(page)
    assert "tracks from Playing Now, take" in texts and "Every column" not in texts
    assert "Variety" in texts and "Order" in texts, "the two choices stay under the lines"


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


def test_a_button_of_your_own_has_only_the_current_track_line(app, ui):
    import buttons
    buttons.add("Sunday", "artists")
    page, p = option_pair(ui, "Sunday")
    texts = texts_in(page)
    assert "When Seed is Current Track" in texts and "When Seed is Playing Now" not in texts, texts
    assert "Separate Settings for Review Mode" not in texts
    assert set(p.seed_boxes) == {"current"}
    assert not ui.errors, ui.errors
