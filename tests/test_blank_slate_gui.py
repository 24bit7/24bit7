"""
A blank slate on screen (1 Nov 2026): on the Play tab it sits in grey with a note that always shows,
and pressing it writes one console line and opens its page. Its page has no Config 1, only + Add a
Config; the first config added becomes Config 1, and Remove on a made playlist's Config 1 is allowed.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import shown_labels


def test_a_blank_slate_on_the_play_tab_says_so_and_opens_its_page(app, ui, monkeypatch):
    import buttons
    from tabs import PALETTE
    p = ui.play
    buttons.load()
    new, _ = buttons.add_from_choice(("new", None))
    p.refresh_buttons()
    ui.pump(0.3)
    b = p.play_buttons[-1]
    assert b._name == "New Playlist" and b._text_fg == PALETTE["help_fg"], "grey text: nothing to build"
    assert p._button_note(new) == "No config yet. Click to open its page and add one."
    assert p._dial_values(new) == {"moderator": None, "drift": None, "deepcuts": None, "nonstop": None}
    opened = []
    monkeypatch.setattr(p, "open_playlist_settings", lambda bid, rename=False: opened.append(bid))
    p._end_greeting(keep=False)
    p.on_button(new)
    ui.pump(0.3)
    assert opened == [new["id"]]
    assert "New Playlist has no config yet. Add one on its page under Settings > Playlists." in p.log.get("1.0", "end")
    assert not ui.errors, ui.errors[0]


def test_a_blank_slates_page_adds_its_first_config_and_can_lose_it_again(app, ui, monkeypatch):
    import buttons
    from tkinter import messagebox
    s = ui.settings
    buttons.load()
    new, _ = buttons.add_from_choice(("new", None))
    s.show_playlist(new["id"])
    ui.pump(0.5)
    texts = shown_labels(s._button_right)
    assert "No config yet: add one below." in texts and not any(t.startswith("Config 1") for t in texts)
    assert s._button_page is None
    s._config_add(buttons.get(new["id"]), "tracks")
    ui.pump(0.5)
    texts = shown_labels(s._button_right)
    assert "Config 1" in texts and "Track Matching" not in texts, "the kind sits in the heading's dropdown, not a label"
    assert s._button_page is not None and s._button_page.config_kind == "tracks"
    assert "Remove" in texts, "a made playlist's Config 1 can be removed"
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._config_remove(buttons.get(new["id"]), 0)
    ui.pump(0.5)
    assert buttons.get(new["id"])["kind"] is None and s._button_page is None, "a blank slate again"
    std = buttons.standard("artists")
    s.show_playlist(std["id"])
    ui.pump(0.5)
    first_block = s._button_inner.winfo_children()[0]
    assert "Config 1" in shown_labels(first_block), "the standard playlist's page is up"
    assert "Remove" not in shown_labels(first_block), "a standard playlist keeps its own config"
    assert not ui.errors, ui.errors[0]
