"""
Radio on the row (Ben, 6 Nov 2026): a playlist of its own kind, so it sits where it's dragged, deletes and comes
back like the others. It stays lit on every seed tab, since it needs no seed. The first press makes the lanes and
plays the biggest; after that a Radio set to Last Played plays the last lane played. Its arrow lists the lanes
with their share of the plays, Re-analyse at the foot. Right-click a lane to Split or Join Back, or Add as a
Button: a Radio playlist of that lane, after this one. It rests, greyed with a note, until enough has been played.
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


def with_radio(ui):
    """The fake world starts without Radio (conftest): add it from its template, as a user would."""
    import buttons
    made, _page = buttons.add_from_choice(("template", "radio"))
    ui.play.refresh_buttons()
    ui.pump(0.2)
    fb = next(b for b in ui.play.play_buttons if b._button["id"] == made["id"])
    return made, fb


def test_radio_is_a_row_button_and_stays_lit_on_jriver_playlists(app, ui):
    p = ui.play
    made, fb = with_radio(ui)
    assert fb is p.play_buttons[-1], "a new playlist goes at the end of the row"
    assert fb._kind == "radio" and fb._arrow, "its arrow lists the lanes"
    p.seed_nb.select(p.playlists_tab)
    ui.pump(0.3)
    assert fb._state == "normal", "no seed, so nothing to rest for"
    assert all(b._state == "disabled" for b in p.play_buttons if b is not fb), "the others need a seed"
    assert not ui.errors, ui.errors[0]


def test_first_press_analyses_then_plays_the_last_lane_after(app, ui, lowered):
    radio = lowered
    play_counts(app, EVERYONE)
    p = ui.play
    p._end_greeting(keep=False)
    made, fb = with_radio(ui)
    fb._command()
    ui.wait_idle()
    text = console(ui)
    assert "Radio: analysing what you play." in text and "Pillars this round:" in text, text
    first = radio.lanes()[0]
    assert radio.row()["default"] == first["id"], "the biggest, the first time"
    assert app.jriver.zone("Speakers").playlist
    second = radio.lanes(include_children=True)[1]   # another lane, or a Split half of the first
    p.on_radio(made, second["id"])
    ui.wait_idle()
    assert radio.row()["default"] == second["id"], "Last Played follows the lane picked from the arrow"
    p._open_radio(made)
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
    import buttons
    radio = lowered
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    p = ui.play
    made, fb = with_radio(ui)
    splittable = next((x for x in radio.lanes() if x.get("children")), None)
    if splittable is None:
        pytest.skip("the fake world made no lane with halves")
    p._open_radio(made)
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
    p._radio_add_button(made, half["id"])
    ui.pump(0.2)
    lane_button = p.play_buttons[p.play_buttons.index(next(b for b in p.play_buttons
                                                           if b._button["id"] == made["id"])) + 1]
    assert lane_button._kind == "radio" and lane_button.cget("text") == half["name"], "right after this one"
    assert buttons.get(lane_button._button["id"])["lane"] == half["name"]
    lane_button._command()
    ui.wait_idle()
    assert f"Radio: {half['name']}." in console(ui)
    assert not ui.errors, ui.errors[0]


def test_nothing_nests_under_radio(app, ui):
    import buttons
    p = ui.play
    made, fb = with_radio(ui)
    other = p.play_buttons[0]
    ui.pump(0.1)
    x, y = fb.winfo_rootx() + 10, fb.winfo_rooty() + 10
    p._watch_nest(other._button, other, x, y)
    ui.pump(0.1)
    assert getattr(p, "_nest_watch", None) is None, "Radio is never a nest target"
    assert buttons.children(made["id"]) == []
    assert not ui.errors, ui.errors[0]


def test_radio_rests_greyed_with_a_note(app, ui, lowered):
    radio = lowered
    play_counts(app, {"The Beatles": 3})
    p = ui.play
    made, fb = with_radio(ui)
    p.on_radio(made)
    ui.wait_idle()
    assert "Radio is resting" in console(ui)
    fb = next(b for b in p.play_buttons if b._button["id"] == made["id"])
    assert fb._state == "disabled"
    assert "there are 1" in fb._radio_note.text, fb._radio_note.text
    assert not ui.errors, ui.errors[0]
