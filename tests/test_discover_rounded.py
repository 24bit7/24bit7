"""
Discover: rounded buttons along the bottom, A- and A+ at the top right, and the bigger
rounded search box with its hint.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def loaded(app, ui):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", "Something"))
    d = ui.discover
    d.ensure_loaded()
    ui.pump(0.8)
    return d


def test_text_size_buttons(app, ui):
    import settings_gui
    d = loaded(app, ui)
    d.font_var.set("15")
    d._step_font(1)
    assert d.font_var.get() == "16" and settings_gui.read_env().get("TABLE_FONT_SIZE") == "16"
    assert d.larger_button.cget("state") == "disabled"
    d._step_font(1)
    assert d.font_var.get() == "16", "never past 16"
    for _ in range(12):
        d._step_font(-1)
    assert d.font_var.get() == "6" and d.smaller_button.cget("state") == "disabled"
    assert d.larger_button.cget("state") == "normal"
    labels = [str(w.cget("text")) for w in walk(d) if isinstance(w, tk.Label)]
    assert "Font size:" not in labels


def test_search_box_hint_and_filter(app, ui):
    d = loaded(app, ui)
    box = d.search_box
    assert box._hint.winfo_manager(), "the hint shows while the box is empty"
    d.search_var.set("Zomb")
    ui.pump(0.3)
    assert box.entry.get() == "Zomb" and not box._hint.winfo_manager()
    assert d.tree.get_children() and all("Zombies" in d.tree.item(i, "values")[2]
                                          for i in d.tree.get_children())
    d.search_var.set("")
    ui.pump(0.3)
    assert box._hint.winfo_manager()


def test_bottom_buttons_are_rounded(app, ui):
    from tabs import FlatButton
    d = loaded(app, ui)
    assert not [w for w in walk(d) if isinstance(w, tk.Button)], "no square buttons left"
    texts = [w.cget("text") for w in walk(d._bar_right) if isinstance(w, FlatButton)]
    for text in ("Clear All", "Select All", "Select None", "Refresh", "CSV"):
        assert text in texts, text
    assert all(isinstance(b, FlatButton) for b in d._site_buttons)
    d.select_all()
    ui.pump(0.3)
    count = len(d.tree.get_children())
    assert d._yt_button.cget("text") == f"Create YouTube Playlist ({count})"
    assert d._clear_sel_button.cget("text") == f"Clear Selected ({count})"
    assert not ui.errors, ui.errors
