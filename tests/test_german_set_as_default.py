"""
German Settings > JRiver Playlists: "Als Vorgabe setzen" ran past the All playlists box's right edge at the
screenshots' width, from 1.33.0 (the Embellish table made the page's row of columns wider). The Skip recent
column's German title, "Kürzlich gespielte auslassen", was the widest heading on the row; "Kürzlich gespielt"
frees the room (12 Nov 2026).
"""

import tkinter as tk

import pytest

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import page_named, walk

pytestmark = pytest.mark.windows


@pytest.fixture
def german(app):
    import i18n
    i18n.set_language("de")
    yield i18n
    i18n.set_language("en")


def test_set_as_default_ends_inside_its_box_in_german(app, german, ui):
    from i18n import t
    ui.root.geometry("1180x820")   # the screenshots' size
    ui.pump(0.4)
    page = page_named(ui, t("JRiver Playlists"))
    ui.pump(0.8)
    shown = [w for w in walk(page) if isinstance(w, tk.Button) and str(w.cget("text")) == "Als Vorgabe setzen"]
    assert shown, "the All playlists rows each have the button"
    for b in shown:
        box = b
        while box is not None and not hasattr(box, "section_title") and box.master is not None:
            box = box.master   # the section the button sits in
        box = box if hasattr(box, "section_title") else b.winfo_toplevel()
        right, edge = b.winfo_rootx() + b.winfo_width(), box.winfo_rootx() + box.winfo_width()
        assert right <= edge, f"Als Vorgabe setzen ends at {right}, past its box's edge at {edge}"
