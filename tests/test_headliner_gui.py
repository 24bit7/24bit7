"""
The Play tab's room for Headliner (30 Oct 2026): Output moves from the button row to the right of
the Zone line, on both seed tabs, and the AI usage figure moves up to the seed tabs' row.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)


def test_headliner_sits_between_top_tracks_and_ai_playlist(app, ui):
    names = [getattr(b, "_name", None) for b in ui.play.buttons]
    i = names.index("Headliner")
    assert names[i - 1] == "Artist's Top Tracks" and names[i + 1] == "AI Playlist", names
    button = ui.play.play_buttons[i]._button   # a ready-made button: Artist's Top Tracks with Guests on
    assert button["kind"] == "top" and button["settings"]["TOP_GUESTS"] == "third" and not button["standard"]


def test_output_is_on_the_zone_line_on_both_tabs(app, ui):
    p = ui.play
    assert p.output_cb.master is p.output_box and p.output_box.winfo_manager() == "place"
    ui.pump(0.3)
    zone_mid = p.zone_cb.winfo_rooty() + p.zone_cb.winfo_height() // 2
    out_mid = p.output_cb.winfo_rooty() + p.output_cb.winfo_height() // 2
    assert abs(zone_mid - out_mid) <= 6, (zone_mid, out_mid)
    assert p.output_cb.winfo_rootx() > p.np_track.winfo_rootx() + p.np_track.winfo_width() - 1
    p.seed_nb.select(p.search_tab)
    ui.pump(0.3)
    assert p.output_cb.winfo_ismapped()
    box_mid = p.search_artist.winfo_rooty() + p.search_artist.winfo_height() // 2
    out_mid = p.output_cb.winfo_rooty() + p.output_cb.winfo_height() // 2
    assert abs(box_mid - out_mid) <= 6, (box_mid, out_mid)


def test_ai_usage_sits_on_the_seed_tabs_row(app, ui):
    p = ui.play
    app.set_env(AI_USAGE_NOW_PLAYING="1")
    p._sync_usage_box()
    ui.pump(0.3)
    strip = p.seed_nb._strip
    assert str(p.usage_box.place_info().get("in")) == str(strip)
    p.seed_nb.select(p.search_tab)
    ui.pump(0.2)
    assert p.usage_box.winfo_ismapped(), "shows on Search too"
