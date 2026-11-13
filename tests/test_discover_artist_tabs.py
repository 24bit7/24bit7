"""
Discover's three tabs (Ben, 10 and 11 Nov 2026): Sessions, the history build by build as before, then
Missing Artists and Gaps in Your Artists, which share Genre, Period and Zone and keep a Sound each, and the
opened row. These open real windows.
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


def artist_tab(ui, kind="Missing Artists"):
    d = ui.discover
    ui.nb.select(d)
    d.ensure_loaded()
    ui.pump(0.3)
    d.show_view(kind)
    s = d.missing_page if kind == "Missing Artists" else d.gaps_page
    ui.pump(until=lambda: s.ready and not s._fetching, timeout=20)
    return s


def rows(s):
    return [s.tree.item(i, "values") for i in s.tree.get_children()]


def test_sessions_keeps_the_table_and_the_artist_tabs_sit_beside_it(app, ui):
    d = ui.discover
    assert str(d.tree.winfo_toplevel()) == str(d.winfo_toplevel())
    assert d.tree.master.master is d.sessions_page, "the table lives on Sessions"
    labels = [lab.cget("text") for lab in d.pane._tabs]
    assert labels == ["Sessions", "Missing Artists", "Gaps in Your Artists"]
    assert d.pane.select() == str(d.sessions_page), "Discover opens on Sessions, as it did"
    assert not ui.errors, ui.errors[0]


def test_missing_artists_with_genre_zone_and_sound(app, ui):
    history(app)
    stations_meta(app)
    more_metal(app)
    s = artist_tab(ui)
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
    s = artist_tab(ui)
    i = next(n for n, v in enumerate(s.genre_menu.cget("values")) if v.startswith("Psychedelic / Prog"))
    s.genre_menu.current(i)
    s.genre_menu.event_generate("<<ComboboxSelected>>")
    ui.pump(until=lambda: s.ready and s.result.get("station"), timeout=10)
    assert [(r[0], r[1]) for r in rows(s)] == [("Trivium", "1")]
    assert "pointed to by your Psychedelic / Prog artists" in s.count_label.cget("text")
    assert not ui.errors, ui.errors[0]


def test_gaps_has_its_own_columns(app, ui):
    history(app)
    s = artist_tab(ui, "Gaps in Your Artists")
    assert [s.tree.heading(c, "text") for c in s.tree.cget("columns")] == \
        ["Artist", "Matched", "Missed", "Songs You Don't Have"]
    assert rows(s)[0] == ("Pink Floyd", "1", "1", "Money")
    assert "artists you own were named" in s.count_label.cget("text")
    assert not ui.errors, ui.errors[0]


def test_genre_period_and_zone_carry_across_but_sound_does_not(app, ui):
    """Ben, 11 Nov 2026: the two tabs share Genre, Period and Zone; each keeps its own Sound."""
    history(app)
    stations_meta(app)
    more_metal(app)
    m = artist_tab(ui)
    i = next(n for n, v in enumerate(m.zone_menu.cget("values")) if v.startswith("Speakers"))
    m.zone_menu.current(i)
    m.zone_menu.event_generate("<<ComboboxSelected>>")
    ui.pump(until=lambda: m.ready and m.result.get("builds") == 1, timeout=10)
    m.period_var.set("Last 12 months")
    m.period_menu.event_generate("<<ComboboxSelected>>")
    ui.pump(until=lambda: m.ready, timeout=10)
    m.sound = "numetal"
    g = artist_tab(ui, "Gaps in Your Artists")
    assert g.zone_menu.get().startswith("Speakers"), g.zone_menu.get()
    assert g.period_var.get() == "Last 12 months"
    assert g.sound is None, "Sound is each tab's own"
    assert g.result["builds"] == 1
    assert not ui.errors, ui.errors[0]


def test_genre_is_greyed_while_radio_rests(app, ui):
    import radio
    history(app)
    radio._set_meta(radio.ANALYSIS_KEY, {"when": "2026-11-10", "resting": {"have": 50, "need": 500}, "lanes": []})
    s = artist_tab(ui)
    assert str(s.genre_menu.cget("state")) == "disabled"
    assert "resting" in s._genre_why
    assert not ui.errors, ui.errors[0]


def test_column_titles_fit_on_a_screen_scaled_up(app, ui):
    """Ben, 11 Nov 2026: at his display scaling "Your Artists" read "Your /" and "Builds" "Buil"; the number
    columns had fixed pixel widths. Now each is measured from its title in the heading font, numbers centred."""
    import tkinter.font as tkfont
    history(app)
    stations_meta(app)
    old = float(ui.root.tk.call("tk", "scaling"))
    ui.root.tk.call("tk", "scaling", old * 2)
    try:
        for kind in ("Missing Artists", "Gaps in Your Artists"):
            s = artist_tab(ui, kind)
            s.restyle()
            ui.pump(0.2)
            size = getattr(__import__("engine"), "TABLE_FONT_SIZE", 9)
            head = tkfont.Font(family="Segoe UI", size=size, weight="bold")
            for c in s.tree.cget("columns"):
                title = s.tree.heading(c, "text")
                assert int(s.tree.column(c, "minwidth")) >= head.measure(title), (kind, title)
                assert int(s.tree.column(c, "width")) >= head.measure(title), (kind, title)
            numbers = [c for c in s.tree.cget("columns") if c not in ("artist", "sound", "songs")]
            assert {str(s.tree.column(c, "anchor")) for c in numbers} == {"center"}, kind
    finally:
        ui.root.tk.call("tk", "scaling", old)
    assert not ui.errors, ui.errors[0]


def test_rows_are_striped_and_the_artist_column_fits_its_names(app, ui):
    """Ben, 11 Nov 2026: every other row shaded on all three tabs, so a row is easy to follow across; the
    Artist column as wide as its names need, Sound or the songs taking the rest; text titles over their text."""
    import tkinter.font as tkfont
    import engine
    import tabs
    history(app)
    stations_meta(app)
    more_metal(app)
    session(app, artist="The Kinks", started="2026-11-11 21:00",   # the latest, so Sessions opens on it
            seen=[("Nonpoint", "Victim", "Last.fm", 0), ("Crossfade", "Cold", "Last.fm", 0)])
    for kind in ("Missing Artists", "Gaps in Your Artists"):
        s = artist_tab(ui, kind)
        kids = s.tree.get_children()
        assert len(kids) >= 2, kind
        assert ["stripe" in s.tree.item(i, "tags") for i in kids[:4]] == [False, True, False, True][:len(kids[:4])]
        assert str(s.tree.tag_configure("stripe", "background")) == tabs.stripe_colour(), kind
        cell = tkfont.Font(family="Segoe UI", size=getattr(engine, "TABLE_FONT_SIZE", 9))
        widest = max(cell.measure(s.tree.set(i, "artist")) for i in kids)
        assert int(s.tree.column("artist", "width")) <= max(widest, 200) + 40, (kind, s.tree.column("artist", "width"))
        assert not s.tree.column("artist", "stretch") and s.tree.column(s.tree.cget("columns")[-1], "stretch")
        assert str(s.tree.heading("artist", "anchor")) == "w" and \
            str(s.tree.heading(s.tree.cget("columns")[-1], "anchor")) == "w", kind
    d = ui.discover
    d.pane.select(d.sessions_page)
    ui.pump(0.3)
    d._populate()
    kids = d.tree.get_children()
    assert len(kids) >= 2
    assert ["stripe" in d.tree.item(i, "tags") for i in kids[:2]] == [False, True]
    assert str(d.tree.tag_configure("stripe", "background")) == tabs.stripe_colour()
    assert not ui.errors, ui.errors[0]


def test_refresh_reads_the_library_again_and_an_artist_bought_since_drops_off(app, ui):
    """Ben, 13 Nov 2026: Refresh at the right of the count line reads the library from JRiver now, so an artist
    added since leaves Missing Artists; the time it was last read is in the hover note, not on the line."""
    history(app)
    s = artist_tab(ui)
    assert any(r[0] == "Nonpoint" for r in rows(s))
    line = s.count_label.master
    assert s.refresh_button.master is line and \
        s.refresh_button.winfo_rootx() > s.count_label.winfo_rootx(), "Refresh sits at the right of the count line"
    j = app.jriver
    row = dict(j.tracks[0], Key="99001", Artist="Nonpoint", Name="Bullet With a Name", Album="Vengeance")
    j.tracks.append(row)
    j.by_key[row["Key"]] = row
    s.reload()
    ui.pump(until=lambda: s.ready and not s._reloading, timeout=20)
    assert not any(r[0] == "Nonpoint" for r in rows(s)), "Nonpoint is in the library now"
    assert "Last read at" in s._refresh_note()
    assert "Last read" not in s.count_label.cget("text"), "the time goes in the hover note"
    assert not ui.errors, ui.errors[0]
