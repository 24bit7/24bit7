"""
The Play tab's JRiver Playlists tab (Ben, 6 Nov 2026): a third seed tab between Now Playing and Search. The
Playlist box opens a list (the recent five, then A to Z, narrowed as you type); Play and Play & Embellish run
like any build. The row's playlist buttons grey out while it shows (they start from a track or an artist).
After a build that went to a JRiver zone, Save Playlist appears at the row's top right.
"""

import tkinter as tk

from test_gui import ui, console  # noqa: F401  (the GUI fixture)


def lists_tab(ui):
    p = ui.play
    p._end_greeting(keep=False)
    p.seed_nb.select(p.playlists_tab)
    ui.pump(0.3)
    return p


def test_the_tab_sits_between_now_playing_and_search_and_greys_the_playlists(app, ui):
    p = ui.play
    names = [tab.cget("text") for tab in p.seed_nb._tabs]
    assert names == ["Now Playing", "JRiver Playlists", "Search"], names
    lists_tab(ui)
    assert all(b._state == "disabled" for b in p.play_buttons), "they start from a track or an artist"
    assert p.credits_button._state == "disabled"
    assert p.play_list_button._state == "normal" and p.embellish_button._state == "normal"
    p.seed_nb.select(p.search_tab)
    ui.pump(0.2)
    assert all(b._state == "normal" for b in p.play_buttons if not getattr(b, "_needs_advanced", False))
    assert not ui.errors, ui.errors[0]


def test_the_list_opens_narrows_and_picks(app, ui):
    p = lists_tab(ui)
    p._open_playlists()
    ui.pump(0.2)
    rows = [pl["Name"] for pl, _ in p._playlists_pop._rows]
    assert rows == sorted(rows, key=str.lower) and "Sunday Morning" in rows, rows
    tags = {pl["Name"]: row.tag for pl, row in p._playlists_pop._rows}
    assert tags["Sunday Morning"] == "", "a playlist at the top level has no folder tag"
    p.playlist_entry.insert(0, "sun")
    p._playlists_typed(type("E", (), {"keysym": "n"})())
    ui.pump(0.2)
    assert [pl["Name"] for pl, _ in p._playlists_pop._rows] == ["Sunday Morning"]
    p._pick_first_playlist()
    ui.pump(0.2)
    assert p.playlist_entry.get() == "Sunday Morning" and p._playlists_pop is None
    assert not ui.errors, ui.errors[0]


def test_play_and_embellish_then_save_playlist(app, ui):
    import embellish
    j = app.jriver
    p = lists_tab(ui)
    road_trip = next(x for x in j.playlists if x["ID"] == "202")
    p._pick_playlist({"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"})
    embellish.set_choice("order", "ordered")
    p.embellish_button._command()
    ui.wait_idle()
    z = j.zone("Speakers").playlist
    assert len(z) == 15 and [k for k in z if k in road_trip["keys"]] == road_trip["keys"], console(ui)
    assert "Embellish: Road Trip" in console(ui)
    assert all(b._state == "disabled" for b in p.play_buttons), "still on the tab after the build"
    assert p._save_shown and p.save_button.winfo_manager() == "place", "Save Playlist after a build to a zone"
    assert p._save_default == "Road Trip (Embellished)"
    import tabs
    real = tabs.ask_name
    tabs.ask_name = lambda parent, title, prompt, initial="": initial
    try:
        p.save_button._command()
    finally:
        tabs.ask_name = real
    ui.pump(0.3)
    saved = next(x for x in j.playlists if x["Name"] == "Road Trip (Embellished)")
    assert saved["keys"] == z, "the zone's Playing Now, as it is"
    assert 'Saved 15 tracks as the JRiver playlist "Road Trip (Embellished)".' in console(ui)
    assert [x["id"] for x in embellish.recent()][0] == "202", "now at the top of the list"
    p._open_playlists()
    ui.pump(0.2)
    texts = [w.cget("text") for w in p._playlists_pop.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]
    assert "RECENT" in texts, texts
    p._close_playlists()
    assert not ui.errors, ui.errors[0]


def test_the_amounts_menu_offers_what_settings_ticks_and_runs_a_pick_once(app, ui, monkeypatch):
    """Ben, 7 Nov 2026: names only, the default ticked, a pick runs once; one amount left and the arrow goes."""
    import embellish
    p = lists_tab(ui)
    ran = []
    monkeypatch.setattr(p, "on_play_playlist", lambda embellish_it, amount=None: ran.append((embellish_it, amount)))
    p._choice_menu("amount")
    ui.pump(0.2)
    pop = p._children_popup
    assert [code for code, _, _ in pop._rows] == ["p10", "p20", "p50", "double", "triple", "out"]
    assert [mark for _, _, mark in pop._rows] == ["", "", "✓", "", "", ""], "+50% until changed"
    labels = [w for w in pop.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]
    assert not labels, "no notes under the rows"
    p._choose("amount", "out")
    ui.pump(0.1)
    assert ran == [(True, "out")] and embellish.choices()["amount"] == "p50", "this once; the default stays"
    embellish.set_amounts(shown=["p20", "double"], default="double")
    p._choice_menu("amount")
    ui.pump(0.2)
    assert [(c, m) for c, _, m in p._children_popup._rows] == [("p20", ""), ("double", "✓")]
    p._close_children()
    embellish.set_amounts(shown=["double"])
    ui.root.event_generate("<<EmbellishAmounts>>")
    ui.pump(0.1)
    assert not p.embellish_button.has_arrow(), "one amount: nothing to choose"
    embellish.set_amounts(shown=["double", "out"])
    ui.root.event_generate("<<EmbellishAmounts>>")
    ui.pump(0.1)
    assert p.embellish_button.has_arrow()
    assert not ui.errors, ui.errors[0]


def lined_up_pair(p):
    """The row's last two playlists on its first line that end clear of Output (as _line_up_lists picks)."""
    first = [b for b in p.play_buttons if b.winfo_y() == p.play_buttons[0].winfo_y()]
    limit = p.output_box.winfo_rootx() - 24
    pairs = [(first[i], first[i + 1]) for i in range(len(first) - 2, -1, -1)]
    return next(pair for pair in pairs if pair[1].winfo_rootx() + pair[1].winfo_width() <= limit)


def test_play_and_embellish_line_up_with_the_last_two_playlists(app, ui):
    """Ben, 7 Nov 2026: the two buttons sit over the row's last two playlists clear of Output, as wide, the box
    meeting them."""
    p = lists_tab(ui)
    root = p.winfo_toplevel()
    for width in (1180, 1600):
        root.geometry(f"{width}x{root.winfo_height()}")
        ui.pump(0.6)
        under_play, under_emb = lined_up_pair(p)
        for top, under in ((p.play_list_button, under_play), (p.embellish_button, under_emb)):
            assert abs(top.winfo_rootx() - under.winfo_rootx()) <= 1, (width, top.cget("text"), top.winfo_rootx(),
                                                                       under.winfo_rootx())
            assert abs(top.winfo_width() - under.winfo_width()) <= 1, (width, top.cget("text"))
        box_right = p.playlist_entry.winfo_rootx() + p.playlist_entry.winfo_width()
        assert abs(box_right + 24 - p.play_list_button.winfo_rootx()) <= 1, "the box stretches to meet Play"
        assert p.embellish_button.winfo_rootx() + p.embellish_button.winfo_width() <= p.output_box.winfo_rootx(), \
            "Output stays clear"
    assert not ui.errors, ui.errors[0]
