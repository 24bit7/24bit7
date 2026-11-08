"""
The Playlist Settings tab after Ben saw 1.30.0 on his own set-up (3 Nov 2026): the left column and the
page each scroll as one piece, header included; Take a Tour, A- A+ and the Simple / Advanced pill share
one row; the Preview is half its first size, "Preview:" to its left, its text two points under the page's; the corners are square again; the text is the
note's size, with A- and A+ moving every Settings screen; Consensus and Moderator sit under the configs.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk

import tabs


def ancestors(w):
    while w is not None:
        yield w
        w = w.master


def heads(page):
    """The section titles down the page, in order."""
    return [w.cget("text") for w in walk(page) if isinstance(w, tk.Label) and str(w.cget("font")) == "S24.heading"]


def test_the_column_and_the_page_scroll_as_one_with_square_corners(app, ui):
    pick_button(ui, "Similar Artists")
    s = ui.settings
    ui.pump(0.3)
    page = s._button_inner
    assert isinstance(page.master, tk.Canvas), "the page is in a scrolling canvas"
    for w in (s._name_box, s._preview, s._mode_labels["simple"], s._tour_button):
        assert page in ancestors(w), "the header scrolls with the page"
    column = next(w for w in ancestors(s._button_list) if isinstance(w, tk.Canvas))
    devices = next(w for w in ancestors(s._device_restore) if isinstance(w, tk.Canvas))
    assert column is not page.master and devices is not column, \
        "Your Playlist Buttons scrolls apart from the page; Device Playlists has its own column on Devices (5 Nov 2026)"
    assert column.winfo_width() >= s._button_list.master.winfo_reqwidth(), "the column asks for the width its content needs"
    assert not [w for w in walk(s) if getattr(w, "corner_tile", False)] and not hasattr(tabs, "corner_tiles")
    assert not ui.errors, ui.errors[0]


def test_take_a_tour_sits_under_advanced_beside_the_preview_and_the_preview_is_small(app, ui):
    """Ben, 3 Nov 2026: A- A+ and the pill on one row, Take a Tour under Advanced at the right, within the header's
    height beside the Preview, so nothing below moves down."""
    import settings_gui
    pick_button(ui, "Similar Artists")
    s = ui.settings
    ui.pump(0.3)
    row = [s._size_labels["smaller"], s._size_labels["larger"], s._mode_labels["simple"], s._mode_labels["advanced"]]
    ys = [w.winfo_rooty() for w in row]
    assert max(ys) - min(ys) <= settings_gui.scaled(s, 8), ys
    xs = [w.winfo_rootx() for w in row]
    assert xs == sorted(xs), "A- A+, then the pill"
    tour, advanced, preview = s._tour_button, s._mode_labels["advanced"], s._preview
    assert tour.winfo_rooty() >= advanced.winfo_rooty() + advanced.winfo_height(), "under the pill"
    right = lambda w: w.winfo_rootx() + w.winfo_width()
    assert abs(right(tour) - right(advanced)) <= settings_gui.scaled(s, 4), "right-aligned under Advanced"
    assert tour.winfo_rooty() + tour.winfo_height() <= preview.winfo_rooty() + preview.winfo_height(),         "no lower than the Preview, so the page below stays put"
    frame = s._preview_frame
    import tkinter as tk
    import tkinter.font as tkfont
    say = next(w for w in frame.winfo_children() if isinstance(w, tk.Label))
    assert say.cget("text") == "Preview:" and say.winfo_rootx() < preview.winfo_rootx(), "Preview: then the picture"
    assert abs(say.winfo_rooty() - preview.winfo_rooty()) <= settings_gui.scaled(s, 8), "on the same row"
    half = settings_gui.scaled(frame, 190 * 0.5)
    assert half <= int(preview.cget("width")) <= half + settings_gui.scaled(frame, 40), "half the first draft's width"
    fonts = {preview.itemcget(i, "font") for i in preview.find_all() if preview.type(i) == "text"}
    assert fonts <= {"S24.tiny", "S24.tinybold"}, fonts
    body = tkfont.nametofont("S24.body", root=s).cget("size")
    assert tkfont.nametofont("S24.tiny", root=s).cget("size") == body - 2, "two points under the page, so A- A+ moves it"
    assert not ui.errors, ui.errors[0]


def test_the_sources_ticks_are_the_settings_size(app, ui):
    import tkinter.font as tkfont
    pick_button(ui, "Similar Artists")
    s = ui.settings
    ui.pump(0.3)
    style = ttk.Style(s)
    for name in ("Big.TCheckbutton", "AI.Big.TCheckbutton"):
        assert str(style.lookup(name, "font")) == "S24.body", name
    lastfm = next(w for w in walk(s._button_inner) if isinstance(w, ttk.Checkbutton) and w.cget("text") == "Last.fm")
    assert str(style.lookup(str(lastfm.cget("style")), "font")) == "S24.body"
    assert tkfont.nametofont("S24.body", root=s).cget("size") == 8
    assert not ui.errors, ui.errors[0]


def test_a_minus_and_a_plus_set_the_text_size_of_every_settings_screen(app, ui):
    import settings_gui
    pick_button(ui, "Similar Artists")
    s = ui.settings
    ui.pump(0.3)
    body = tkfont.nametofont("S24.body", root=s)
    assert body.cget("size") == 8 and s._text_size == 8 and "SETTINGS_FONT_SIZE" not in settings_gui.read_env()
    assert str(s._button_rows[0][1]._font) == "S24.body", "the list rows"
    assert str(s._name_box.cget("font")) == "S24.body", "the Name box"
    tick = next(w for w in walk(s._button_inner) if isinstance(w, ttk.Checkbutton) and "Big" not in str(w.cget("style")))
    assert str(tick.cget("style")) == "S24.TCheckbutton"
    assert "Playlist Selection" in heads(s._button_inner), "section titles in the heading font"
    s._size_labels["larger"].event_generate("<Button-1>")
    ui.pump(0.6)
    assert body.cget("size") == 9 and settings_gui.read_env()["SETTINGS_FONT_SIZE"] == "9"
    assert tkfont.nametofont("S24.heading", root=s).cget("size") == 10
    assert s._text_size == 9 and str(s._button_rows[0][1]._font) == "S24.body", "the rows are rebuilt in the named font"
    s._text_size_step(-1)
    ui.pump(0.4)
    assert body.cget("size") == 8 and settings_gui.read_env()["SETTINGS_FONT_SIZE"] == "8"
    for _ in range(4):
        s._text_size_step(-1)
        ui.pump(0.3)
    assert body.cget("size") == tabs.SETTINGS_FONT_MIN == 6, "the floor"
    s._text_size_step(2)
    ui.pump(0.4)
    assert settings_gui.read_env()["SETTINGS_FONT_SIZE"] == "8"
    assert not ui.errors, ui.errors[0]


def test_consensus_and_moderator_sit_under_the_configs(app, ui):
    pick_button(ui, "Similar Artists")
    s = ui.settings
    ui.pump(0.3)
    titles = heads(s._button_inner)
    order = [t_ for t_ in titles if t_ in ("Sources", "Playlist Selection", "Filters", "Consensus", "Moderator", "Drift")]
    assert order == ["Sources", "Playlist Selection", "Filters", "Consensus", "Moderator", "Drift"], order
    selection = next(w for w in walk(s._button_inner) if isinstance(w, tk.Label) and w.cget("text") == "Playlist Selection")
    inner = s._button_inner
    block = next(w for w in ancestors(selection) if w.master is inner)   # the config box: a child of the page
    for title in ("Consensus", "Moderator"):
        label = next(w for w in walk(inner) if isinstance(w, tk.Label) and w.cget("text") == title)
        assert next(w for w in ancestors(label) if w.master is inner) is not block, f"{title} is outside the config box"
    # two matching configs: each has its own, titled by kind
    p = pick_button(ui, "Similar Tracks")
    s._config_add(p.button, "artists")
    ui.pump(0.5)
    titles = heads(s._button_inner)
    assert "Consensus for Track Matching" in titles and "Consensus for Artist Matching" in titles, titles
    assert "Moderator for Track Matching" in titles and "Moderator for Artist Matching" in titles
    assert not ui.errors, ui.errors[0]
