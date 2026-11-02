"""
Take a Tour (Ben, 2 Nov 2026): from the Playlist Settings page in Advanced, the dashed Take a Tour box opens
Artist + Guests and walks the sections in order with a dimming shade, a lit section and a pop-up (Back, Next,
Close, "n of 14"). The pop-up texts are the sections' hover notes. A closed section opens while it's lit and
folds back after. Rebuilding the page (switching to Simple) ends the tour.
"""

import tkinter as tk

from i18n import t
from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import pick_button, walk


def notes_on(page):
    return {getattr(w, "_note_text", None) for w in walk(page)} - {None}


def test_tour_walks_the_sections_with_their_notes(app, ui):
    import buttons
    import tour
    pick_button(ui, "Similar Artists")
    s = ui.settings
    assert s._tour_button.winfo_exists(), "the Take a Tour box shows in Advanced"
    assert tour.note_for("Mix") not in notes_on(s._button_inner), "one config: no Mix"
    s._start_tour()
    ui.pump(0.5)
    run = s._tour
    assert run is not None and run.running
    guests = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    assert s._button_id == guests["id"], "the tour opens Artist + Guests"
    assert run.steps[0] is None and run.steps[1:] == list(tour.ORDER), run.steps
    assert len(run.steps) == 14
    assert run.text.cget("text") == t(tour.OPENER) and run.count.cget("text") == "1 of 14"
    assert run.shade.winfo_exists() and run.popup.winfo_exists()
    assert str(run.back._state) == "disabled"
    # the headers carry the same notes the tour shows
    page_notes = notes_on(s._button_inner)
    for title in tour.ORDER:
        assert tour.note_for(title) in page_notes, title
    run.next_()
    ui.pump(0.3)
    assert run.at == 1 and run.lit is run.sections["Sources"] and run.lit.section_title == "Sources"
    assert run.text.cget("text") == tour.note_for("Sources") and run.title.cget("text") == "Sources"
    assert run.hole.winfo_ismapped(), "the shade has a hole on the lit section"
    # a closed section opens while lit, and folds back when the tour moves on
    closed = next((title for title in tour.ORDER[4:]   # past Mix, which never folds
                   if not run.sections[title].winfo_children()[1].is_open()), None)
    assert closed is not None, "Artist + Guests has at least one section off"
    run.show(run.steps.index(closed))
    ui.pump(0.3)
    box = run.sections[closed].winfo_children()[1]
    assert box.is_open() and run.opened is box
    run.next_()
    ui.pump(0.3)
    assert box.is_open() is False, "folded back"
    run.back_()
    ui.pump(0.2)
    assert run.at == run.steps.index(closed) and box.is_open()
    run.show(len(run.steps) - 1)
    ui.pump(0.2)
    assert run.next._label.cget("text") == "Finish"
    run.next_()
    ui.pump(0.3)
    assert not run.running and s._tour is None
    assert not run.shade and not run.popup
    # switching to Simple rebuilds the page and ends a running tour
    s._start_tour()
    ui.pump(0.4)
    run = s._tour
    import mode
    mode.set_current("simple")   # as the pill does once its question is answered (the fixture answers No)
    s._button_fill_page()
    ui.pump(0.5)
    assert not run.running and s._tour is None
    assert not s._tour_button.winfo_exists(), "no Take a Tour box in Simple"
    s._set_mode("advanced")
    ui.pump(0.3)
    assert s._tour_button.winfo_exists()
    assert not ui.errors, ui.errors[0]
