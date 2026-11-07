"""
The seed tabs hold still (Ben, 7 Nov 2026): Now Playing, JRiver Playlists and Search are one height, so the
bar under them and the playlist buttons don't move when the tab changes, and Output sits in the panel's middle
on all three, with each tab's row centred to match.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)


def where(p, ui):
    ui.pump(0.4)
    panel = p.seed_nb._current
    out_mid = p.output_cb.winfo_rooty() + p.output_cb.winfo_height() // 2
    panel_mid = panel.winfo_rooty() + panel.winfo_height() // 2
    return {"bar": panel.winfo_rooty() + panel.winfo_height(), "buttons": p.play_buttons[0].winfo_rooty(),
            "output": out_mid, "output_x": p.output_cb.winfo_rootx(), "panel_mid": panel_mid}


def test_bar_and_output_stay_put_between_the_seed_tabs(app, ui):
    p = ui.play
    seen = {}
    for name, page in (("now", p.seed_nb._pages[0]), ("lists", p.playlists_tab), ("search", p.search_tab),
                       ("now again", p.seed_nb._pages[0])):
        p.seed_nb.select(page)
        seen[name] = where(p, ui)
    first = seen["now"]
    for name, spot in seen.items():
        for key in ("bar", "buttons", "output", "output_x"):
            assert abs(spot[key] - first[key]) <= 1, (name, key, spot[key], first[key])
        assert abs(spot["output"] - spot["panel_mid"]) <= 2, (name, "Output in the panel's middle")
    # each tab's row is centred too, so Output is level with it
    p.seed_nb.select(p.playlists_tab)
    ui.pump(0.3)
    row = p.playlist_entry.master
    row_mid = row.winfo_rooty() + row.winfo_height() // 2
    assert abs(row_mid - seen["lists"]["output"]) <= 2, (row_mid, seen["lists"]["output"])
    p.seed_nb.select(p.search_tab)
    ui.pump(0.3)
    top = p.search_artist.winfo_rooty()
    hint = [w for w in p.search_tab.grid_slaves(row=1, column=0)][0]
    bottom = hint.winfo_rooty() + hint.winfo_height()
    assert abs((top + bottom) // 2 - seen["search"]["output"]) <= 3, "the boxes and their line centred as one"
    assert not ui.errors, ui.errors[0]


def test_a_long_title_grows_every_tab_alike(app, ui):
    p = ui.play
    p.seed_nb.select(p.seed_nb._pages[0])
    ui.pump(0.3)
    p._show_playing({"PlayingNowPosition": "0", "Name": "A Very Long Title " * 12, "Artist": "Somebody " * 8,
                     "Album": "An Album With A Long Name " * 4})
    ui.pump(0.4)
    tall = where(p, ui)
    for page in (p.playlists_tab, p.search_tab):
        p.seed_nb.select(page)
        spot = where(p, ui)
        assert abs(spot["bar"] - tall["bar"]) <= 1, (str(page), spot["bar"], tall["bar"])
    p._show_playing(None)
    p.seed_nb.select(p.seed_nb._pages[0])
    short = where(p, ui)
    assert short["bar"] <= tall["bar"], "and shrinks back with a short one"
    assert not ui.errors, ui.errors[0]
