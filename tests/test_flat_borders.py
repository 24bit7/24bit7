"""
Old-style Tk widgets get a thin flat edge from the theme, not 3D shading.
"""

import pytest

tk = pytest.importorskip("tkinter")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_classic_widgets_are_flat(theme):
    import tabs
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        tabs.apply_theme(root, theme)
        entry, spin, button = tk.Entry(root), tk.Spinbox(root), tk.Button(root, text="Clear")
        listbox = tk.Listbox(root)
        for w in (entry, spin, listbox, button):
            assert str(w.cget("relief")) == "flat", w
            assert int(w.cget("highlightthickness")) == 1, w
            assert str(w.cget("highlightbackground")).lower() == tabs.PALETTE["field_edge"].lower(), w
        assert str(spin.cget("buttonuprelief")) == "flat"
        own = tk.Frame(root, bd=1, relief="solid")
        assert str(own.cget("relief")) == "solid", "a widget's own border is kept"
        button.event_generate("<Enter>")
        root.update()
        tabs._button_enter(type("E", (), {"widget": button})())
        assert str(button.cget("background")).lower() == tabs.PALETTE["button_hover"].lower()
        tabs._button_leave(type("E", (), {"widget": button})())
        assert str(button.cget("background")).lower() == tabs.PALETTE["button_bg"].lower()
    finally:
        root.destroy()
