"""
Discover's two tabs (Ben, 10 Nov 2026): Sessions, the history build by build as before, and Statistics,
with its three views, the Genre, Period and Zone drop-downs, the Sound chips and the opened row.
These open real windows.
"""

from test_discover_stats import history, session, stations_meta
from test_gui import ui  # noqa: F401  (the GUI fixture)


def more_metal(app):
    """A third missing artist, so nu metal is shared by three and shows as a chip."""
    import radio
    session(app, artist="The Beatles", started="2026-11-08 20:00", seen=[("Mudvayne", "Dig", "Last.fm", 0)])
    tags = radio._meta(radio.TAGS_KEY, {})
    tags.update({"nonpoint": [["nu metal", 100]], "trivium": [["nu metal", 90], ["metalcore", 80]],
                 "mudvayne": [["nu-metal", 100]]})
    radio._set_meta(radio.TAGS_KEY, tags)


def statistics(ui):
    d = ui.discover
    ui.nb.select(d)
    d.ensure_loaded()
    ui.pump(0.3)
    d.show_statistics()
    s = d.stats_page
    ui.pump(until=lambda: s.ready and not s._fetching, timeout=20)
    return s


def rows(s):
    return [s.tree.item(i, "values") for i in s.tree.get_children()]


def test_sessions_keeps_the_table_and_statistics_sits_beside_it(app, ui):
    d = ui.discover
    assert str(d.tree.winfo_toplevel()) == str(d.winfo_toplevel())
    assert d.tree.master.master is d.sessions_page, "the table lives on Sessions"
    labels = [lab.cget("text") for lab in d.pane._tabs]
    assert labels == ["Sessions", "Statistics"]
    assert d.pane.select() == str(d.sessions_page), "Discover opens on Sessions, as it did"
    assert not ui.errors, ui.errors[0]


def test_missing_artists_with_genre_zone_and_sound(app, ui):
    history(app)
    stations_meta(app)
    more_metal(app)
    s = statistics(ui)
    got = rows(s)
    assert [r[0] for r in got][:1] == ["Nonpoint"] and {r[0] for r in got} == {"Nonpoint", "Trivium", "Mudvayne"}
    assert got[0][1] == "2", "The Beatles and The Kinks point to Nonpoint"
    assert "3 artists you don't own, from 4 builds." in s.count_label.cget("text"), s.count_label.cget("text")

    genres = list(s.genre_menu.cget("values"))
    assert genres[0] == "All genres" and "Rock / Classic Rock (3)" in genres, genres
    zones = list(s.zone_menu.cget("values"))
    assert "Speakers (Echo Dot)" in zones and "Sonos (Main Window)" in zones, zones

    chips = [w for w in s.chips.winfo_children() if hasattr(w, "sound_key")]
    assert [c.sound_key for c in chips] == ["numetal"], "nu metal and nu-metal are one; metalcore is on one artist"
    ui.pump(0.3)   # the chips are laid out after idle
    chips[0].event_generate("<Button-1>", x=4, y=4)
    ui.pump(until=lambda: s.ready and s.sound == "numetal", timeout=10)
    assert s.sound == "numetal"

    s.tree.selection_set("0")
    ui.pump(0.3)
    lines = " ".join(w.cget("text") for row in s._open_lines.winfo_children() for w in row.winfo_children())
    assert "is on the lists of" in lines and "The Beatles" in lines and "The Kinks" in lines, lines
    assert s._open_buttons.winfo_children(), "the store buttons"
    assert not ui.errors, ui.errors[0]


def test_the_genre_menu_counts_again_inside_a_station(app, ui):
    history(app)
    stations_meta(app)
    session(app, artist="Pink Floyd", seen=[("Trivium", "Shogun", "Last.fm", 0)])
    s = statistics(ui)
    i = next(n for n, v in enumerate(s.genre_menu.cget("values")) if v.startswith("Psychedelic / Prog"))
    s.genre_menu.current(i)
    s.genre_menu.event_generate("<<ComboboxSelected>>")
    ui.pump(until=lambda: s.ready and s.result.get("station"), timeout=10)
    assert [(r[0], r[1]) for r in rows(s)] == [("Trivium", "1")]
    assert "pointed to by your Psychedelic / Prog artists" in s.count_label.cget("text")
    assert not ui.errors, ui.errors[0]


def test_gaps_and_sources_change_the_columns(app, ui):
    history(app)
    s = statistics(ui)
    s.show_view("Gaps in Your Artists")
    ui.pump(until=lambda: s.ready, timeout=10)
    assert [s.tree.heading(c, "text") for c in s.tree.cget("columns")] == \
        ["Artist", "Matched", "Missed", "Songs You Don't Have"]
    assert rows(s)[0] == ("Pink Floyd", "1", "1", "Money")
    s.show_view("Sources")
    ui.pump(until=lambda: s.ready, timeout=10)
    assert rows(s)[0] == ("Last.fm", "5", "40%", "1")
    texts = [w.cget("text") for w in s.chips.winfo_children()]
    assert texts == ["Sound doesn't apply to sources."]
    assert "songs looked up in" in s.count_label.cget("text")
    assert not ui.errors, ui.errors[0]


def test_genre_is_greyed_while_radio_rests(app, ui):
    import radio
    history(app)
    radio._set_meta(radio.ANALYSIS_KEY, {"when": "2026-11-10", "resting": {"have": 50, "need": 500}, "lanes": []})
    s = statistics(ui)
    assert str(s.genre_menu.cget("state")) == "disabled"
    assert "resting" in s._genre_why
    assert not ui.errors, ui.errors[0]
