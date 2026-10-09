"""The Play tab's More Options buttons carry no hover notes (they're in the manual instead)."""

from test_gui import ui  # noqa: F401  (the GUI fixture)


def test_more_options_buttons_have_no_notes(app, ui):
    p = ui.play
    p._show_more(True)
    ui.pump(1.0)
    for b in (p.seed_cb, p.behaviour_cb, p.moderator_cb, p.drift_cb, p.nonstop_cb):
        assert not hasattr(b._label, "_tooltip"), b.cget("text")
        assert str(b._label.cget("cursor")) in ("hand2", ""), b.cget("text")
    notes = [w for w in p.extras_row.winfo_children() if hasattr(w, "_note_text")]
    assert not notes
