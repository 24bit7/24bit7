"""
Radio's button (Ben, 6 Nov 2026, from the mock-up): after the playlists on the row, lit on every seed tab. The
first press makes the lanes and plays the biggest; after that it plays the last lane played. The arrow lists
the lanes with their share of the plays, Re-analyse at the foot. Right-click a lane to Split or Join Back, and
Add as a Button. It rests, greyed with a note, until enough has been played.
"""

import pytest

from test_gui import ui, console  # noqa: F401  (the GUI fixture)
from test_radio import EVERYONE, play_counts


@pytest.fixture
def lowered(app, monkeypatch):
    import radio
    for name, value in (("MIN_PLAYS", 1), ("MIN_ARTISTS", 4), ("LANE_MIN", 2), ("PILLAR_OWNED", 2),
                        ("PILLARS_TO_SPLIT", 2), ("LANES_MAX", 3)):
        monkeypatch.setattr(radio, name, value)
    monkeypatch.setattr(radio.time, "sleep", lambda s: None)
    return radio


def test_radio_sits_after_the_playlists_and_stays_lit_on_jriver_playlists(app, ui):
    p = ui.play
    order = p.play_buttons + p._radio_row() + [p.more_button]
    xs = [b.winfo_x() + 10000 * b.winfo_y() for b in order]
    assert xs == sorted(xs), "the playlists, then Radio, then More Options"
    p.seed_nb.select(p.playlists_tab)
    ui.pump(0.3)
    assert p.radio_button._state == "normal", "no seed, so nothing to rest for"
    assert not ui.errors, ui.errors[0]


def test_first_press_analyses_then_plays_the_last_lane_after(app, ui, lowered):
    radio = lowered
    play_counts(app, EVERYONE)
    p = ui.play
    p._end_greeting(keep=False)
    p.radio_button._command()
    ui.wait_idle()
    text = console(ui)
    assert "Radio: analysing what you play." in text and "Pillars this round:" in text, text
    first = radio.lanes()[0]
    assert radio.row()["default"] == first["id"], "the biggest, the first time"
    assert app.jriver.zone("Speakers").playlist
    second = radio.lanes(include_children=True)[1]   # another lane, or a Split half of the first
    p.on_radio(second["id"])
    ui.wait_idle()
    assert radio.row()["default"] == second["id"], "the face follows the last lane played"
    p._open_radio()
    ui.pump(0.2)
    pop = p._children_popup
    if second["id"] not in [i for i, _ in pop._rows]:   # a half shows once its lane is split open
        p._radio_fold(radio.lanes()[0]["id"], True)
        ui.pump(0.2)
        pop = p._children_popup
    tags = {lane_id: row.tag for lane_id, row in pop._rows}
    assert tags[second["id"]].startswith("default"), tags
    assert pop._again is not None, "Re-analyse at the foot"
    p._close_children()
    assert not ui.errors, ui.errors[0]


def test_split_join_back_and_add_as_a_button(app, ui, lowered):
    radio = lowered
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    p = ui.play
    splittable = next((x for x in radio.lanes() if x.get("children")), None)
    if splittable is None:
        pytest.skip("the fake world made no lane with halves")
    p._open_radio()
    ui.pump(0.1)
    p._radio_fold(splittable["id"], True)
    ui.pump(0.2)
    ids = [i for i, _ in p._children_popup._rows]
    assert [c["id"] for c in splittable["children"]] == ids[ids.index(splittable["id"]) + 1:][:2], ids
    p._radio_fold(splittable["id"], False)
    ui.pump(0.2)
    assert splittable["children"][0]["id"] not in [i for i, _ in p._children_popup._rows]
    p._close_children()
    half = splittable["children"][0]
    p._radio_pin(half["id"], True)
    ui.pump(0.2)
    assert [b._lane for b in p.radio_lane_buttons] == [half["id"]]
    b = p.radio_lane_buttons[0]
    assert b.cget("text") == half["name"] and b.winfo_x() > p.radio_button.winfo_x() or b.winfo_y() > p.radio_button.winfo_y()
    b._command()
    ui.wait_idle()
    assert f"Radio: {half['name']}." in console(ui)
    p._radio_pin(half["id"], False)
    ui.pump(0.2)
    assert not p.radio_lane_buttons
    assert not ui.errors, ui.errors[0]


def test_radio_rests_greyed_with_a_note(app, ui, lowered):
    radio = lowered
    play_counts(app, {"The Beatles": 3})
    p = ui.play
    p.on_radio()
    ui.wait_idle()
    assert "Radio is resting" in console(ui)
    assert p.radio_button._state == "disabled"
    assert "there are 1 so far" in p._radio_note.text or "there are 1" in p._radio_note.text, p._radio_note.text
    assert not ui.errors, ui.errors[0]
