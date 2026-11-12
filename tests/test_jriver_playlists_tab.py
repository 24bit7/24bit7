"""
The Play tab's Playlists & Albums tab (Ben, 6 Nov 2026, as JRiver Playlists; albums 12 Nov): a third seed tab
between Now Playing and Search. The Album or Playlist box opens a list (the recent five, then the playlists A to
Z, narrowed as you type; albums once something is typed, an artist's name listing theirs); Play and Embellish run
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
    assert names == ["Now Playing", "Playlists & Albums", "Search"], names
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
    embellish.set_row(None, shuffle="0")   # the order is the amount's own setting now, not Play's arrow (10 Nov 2026)
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


def test_the_box_play_and_embellish_share_the_row_in_equal_thirds(app, ui):
    """Ben, 10 Nov 2026: the Playlist box, Play and Embellish are three equal widths, from the box's left
    edge to the end of the row's last playlist clear of Output, and the box stands nearer the buttons' height.
    Before (7 Nov) each button matched the one under it and the box was twice as wide as either."""
    p = lists_tab(ui)
    root = p.winfo_toplevel()
    for width in (1180, 1600):
        root.geometry(f"{width}x{root.winfo_height()}")
        ui.pump(0.6)
        _under_play, under_emb = lined_up_pair(p)
        box, play, emb = p.playlist_entry, p.play_list_button, p.embellish_button
        widths = (box.winfo_width(), play.winfo_width(), emb.winfo_width())
        assert widths[1] == widths[2] and 0 <= widths[0] - widths[1] <= 2, (width, widths)
        assert abs(box.winfo_rootx() + widths[0] + 24 - play.winfo_rootx()) <= 1, "the usual gap after the box"
        assert abs(play.winfo_rootx() + widths[1] + 8 - emb.winfo_rootx()) <= 1, "and between the buttons"
        right = under_emb.winfo_rootx() + under_emb.winfo_width()
        assert abs(emb.winfo_rootx() + widths[2] - right) <= 1, (width, "the row ends where it did")
        assert emb.winfo_rootx() + widths[2] <= p.output_box.winfo_rootx(), "Output stays clear"
        assert 0.75 * play.winfo_height() <= box.winfo_height() < play.winfo_height(), \
            (box.winfo_height(), play.winfo_height())
    assert not ui.errors, ui.errors[0]


def row_texts(pop):
    return [row.itemcget(row._text_id, "text") for _, row in pop._rows]


def headings(pop):
    return [w.cget("text") for w in pop.winfo_children()[0].winfo_children() if isinstance(w, tk.Label)]


def type_in(ui, p, text):
    p.playlist_entry.delete(0, "end")
    p.playlist_entry.insert(0, text)
    p._playlists_typed(type("E", (), {"keysym": "a"})())
    ui.pump(0.2)


def test_play_and_embellish_are_outlined_in_the_accent_with_no_bar(app, ui):
    """Ben, 12 Nov 2026: like Clear Playing Now, the accent's edge and text, and Embellish, not Play & Embellish."""
    import tabs
    p = lists_tab(ui)
    for b in (p.play_list_button, p.embellish_button):
        assert b._quiet and b._armed == tabs.PALETTE["button_fg"], b
    assert p.embellish_button._label.cget("text") == "Embellish"
    assert not ui.errors, ui.errors[0]


def test_albums_only_once_something_is_typed_and_an_artist_lists_theirs(app, ui):
    import library
    library.load()
    p = lists_tab(ui)
    p._open_playlists()
    ui.pump(0.2)
    assert not any(it.get("kind") == "album" for it, _ in p._playlists_pop._rows), "the empty box: no albums"
    assert "Sunday Morning (playlist)" in row_texts(p._playlists_pop)
    type_in(ui, p, "beatles")
    pop = p._playlists_pop
    assert row_texts(pop) == ["Abbey Road \u00b7 The Beatles (album)", "Help! \u00b7 The Beatles (album)",
                              "Revolver \u00b7 The Beatles (album)"], row_texts(pop)
    assert "ALBUMS" in headings(pop) and "PLAYLISTS" not in headings(pop) and "ALL PLAYLISTS" not in headings(pop)
    type_in(ui, p, "greatest")
    assert row_texts(p._playlists_pop) == ["Greatest Hits \u00b7 Queen (album)",
                                           "Greatest Hits \u00b7 The Hollies (album)"]
    type_in(ui, p, "zzz")
    assert "No album or playlist has that in its name." in headings(p._playlists_pop)
    p._close_playlists()
    assert not ui.errors, ui.errors[0]


def test_an_album_picked_changes_the_menus_and_plays_in_order(app, ui):
    import embellish
    import library
    library.load()
    p = lists_tab(ui)
    type_in(ui, p, "abbey")
    p._pick_first_playlist()
    ui.pump(0.2)
    assert p.playlist_entry.get() == "Abbey Road \u00b7 The Beatles"
    p._choice_menu("amount")
    ui.pump(0.2)
    rows = p._children_popup._rows
    assert [c for c, _, _ in rows] == ["with_hits", "and_hits", "p10", "p20", "p50", "double", "triple", "out"]
    assert [c for c, _, m in rows if m] == ["with_hits"], "With Their Hits is an album's default to start"
    p._close_children()
    p._choice_menu("order")
    ui.pump(0.2)
    assert [c for c, _, m in p._children_popup._rows if m] == ["ordered"], "an album starts in order"
    p._choose("order", "shuffled")
    assert embellish.choices()["album_order"] == "shuffled" and embellish.choices()["order"] == "shuffled"
    embellish.set_choice("album_order", "ordered")
    p.play_list_button._command()
    ui.wait_idle()
    keys = library.album_keys("Abbey Road", "The Beatles")
    assert app.jriver.zone("Speakers").playlist == keys, console(ui)
    assert "Play: Abbey Road by The Beatles, 7 tracks, in order." in console(ui)
    p.playlist_entry.delete(0, "end")
    p._open_playlists()
    ui.pump(0.2)
    assert row_texts(p._playlists_pop)[0] == "Abbey Road \u00b7 The Beatles (album)", "on the recent list"
    p._close_playlists()
    assert not ui.errors, ui.errors[0]


def test_embellish_an_album_with_their_hits(app, ui):
    import library
    library.load()
    app.web.plays["The Beatles"] = [{"Come Together": 10000, "Yesterday": 9000}.get(n, 100)
                                    for n in app.web.top_tracks("The Beatles")]
    p = lists_tab(ui)
    type_in(ui, p, "abbey")
    p._pick_first_playlist()
    p.embellish_button._command()
    ui.wait_idle()
    z = app.jriver.zone("Speakers").playlist
    assert "Embellish: Abbey Road by The Beatles, 7 tracks, With Their Hits." in console(ui), console(ui)
    assert len(z) == 8 and z[0] == library.album_keys("Abbey Road", "The Beatles")[0]
    assert not ui.errors, ui.errors[0]


def test_typed_in_full_without_picking(app, ui):
    import library
    library.load()
    p = lists_tab(ui)
    p.playlist_entry.insert(0, "Revolver")
    assert p._chosen_playlist() == {"kind": "album", "Name": "Revolver", "Artist": "The Beatles"}
    p.playlist_entry.delete(0, "end")
    p.playlist_entry.insert(0, "Greatest Hits")
    assert p._chosen_playlist() is None
    assert "More than one album or playlist is called Greatest Hits" in ui.answers[-1][1][1]
    p.playlist_entry.delete(0, "end")
    p.playlist_entry.insert(0, "Greatest Hits \u00b7 Queen")
    assert p._chosen_playlist()["Artist"] == "Queen"
    assert not ui.errors, ui.errors[0]
