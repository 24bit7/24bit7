"""
The Play tab's More Options row as click-through buttons (Seed first), the teal bars for
Seed: Playing Now, the once-only console note, the separator line and the rounded Search boxes.
"""

from test_gui import console, ui  # noqa: F401  (the GUI fixture)


def click(button):
    button._step(1)


def right_click(button):
    button._step(-1)


def test_seed_clicks_through_and_saves(app, ui):
    import settings_gui
    p = ui.play
    assert p.seed_cb.cget("text") == "Seed: Current Track"
    click(p.seed_cb)
    assert p.seed_cb.cget("text") == "Seed: Playing Now"
    assert settings_gui.read_env().get("PLAY_SEED") == "playing_now"
    assert app.engine.play_seed_is_playing_now()
    click(p.seed_cb)
    assert settings_gui.read_env().get("PLAY_SEED") == "current"


def test_teal_bars_follow_seed_on_now_playing_only(app, ui):
    p = ui.play
    similar = [b for b in p.buttons if b.cget("text") in ("Similar Artists", "Similar Tracks")]
    others = [b for b in p.buttons if b.cget("text") in ("Artist's Top Tracks", "AI Playlist")]
    click(p.seed_cb)
    ui.pump(0.2)
    assert all(b._accent == p.seed_colour for b in similar)
    assert all(b._accent != p.seed_colour for b in others)
    p.seed_nb.select(p.search_tab)
    ui.pump(0.3)
    assert all(b._accent is None for b in similar), "a typed seed ignores Seed"
    p.seed_nb.select(p.seed_nb._pages[0])
    ui.pump(0.3)
    assert all(b._accent == p.seed_colour for b in similar)


def test_first_switch_to_playing_now_explains_once(app, ui):
    import settings_gui
    p = ui.play
    p._greeting_active = False
    click(p.seed_cb)
    ui.pump(0.5)
    text = console(ui)
    assert "Seed: Playing Now" in text and "Similar Artists picks 5 artists" in text, text
    assert settings_gui.read_env().get("SEED_PLAYING_NOW_SEEN") == "1"
    p._clear_log()
    click(p.seed_cb)
    click(p.seed_cb)
    ui.pump(0.5)
    assert "Similar Artists picks" not in console(ui), "only the first time"


def test_moderator_steps_both_ways(app, ui):
    p = ui.play
    app.set_env(ANTHROPIC_API_KEY="test-key", USE_AI="1")
    p.sync_moderator()
    p.moderator_cb.config(state="normal")
    assert p.moderator_cb.cget("text") == "Moderator: Off"
    right_click(p.moderator_cb)
    assert p.moderator_cb.cget("text") == "Moderator: Strict"
    click(p.moderator_cb)
    assert p.moderator_cb.cget("text") == "Moderator: Off"
    click(p.moderator_cb)
    assert p.moderator_cb.cget("text") == "Moderator: Relaxed"


def test_mode_button(app, ui):
    import settings_gui
    p = ui.play
    assert p.behaviour_cb.cget("text") == "Play Mode"
    click(p.behaviour_cb)
    assert p.behaviour_cb.cget("text") == "Review Mode" and p._review_mode()
    assert settings_gui.read_env().get("PLAY_BEHAVIOUR") == "review"
    click(p.behaviour_cb)
    assert p.behaviour_cb.cget("text") == "Play Mode"


def test_row_order_and_separator(app, ui):
    p = ui.play
    p._show_more(True)
    ui.pump(0.2)
    assert p.more_line.winfo_manager()
    texts = [getattr(w, "cget")("text") for w in p.extras_row.pack_slaves() if hasattr(w, "_label")]
    assert texts[0].startswith("Seed:") and texts[1] == "Play Mode"
    assert texts[-3:] == ["+ Add Playlist", "Show Credits", "?"], texts   # ? packed at the right-hand end
    p._show_more(False)
    ui.pump(0.2)
    assert not p.more_line.winfo_manager()


def test_playing_now_seed_from_the_play_tab(app, ui):
    j = app.jriver
    j.play("Speakers", [j.key_of("Queen", "Bohemian Rhapsody"), j.key_of("The Hollies", "Bus Stop"),
                        j.key_of("The Byrds", "Mr. Tambourine Man")])
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    ui.play._greeting_active = False
    click(ui.play.seed_cb)
    ui.play.on_similar()
    ui.wait_idle()
    text = console(ui)
    assert "Artists sampled from Playing Now:" in text and "Done:" in text, text
    assert not ui.errors, ui.errors


def test_rounded_search_boxes(app, ui):
    from tabs import RoundedEntry
    p = ui.play
    assert isinstance(p.search_artist, RoundedEntry) and isinstance(p.search_track, RoundedEntry)
    p.search_artist.insert(0, "The Beatles")
    assert p.search_artist.get() == "The Beatles"
    p.seed_nb.select(p.search_tab)
    ui.pump(0.2)
    p.on_similar()
    ui.wait_idle()
    assert "Similar Artists: The Beatles" in console(ui), console(ui)


def test_moderator_and_infinity_names(app, ui):
    """Moderator (magenta while on: it's the AI) and Non-stop shown as the infinity sign."""
    p = ui.play
    assert p.moderator_cb.cget("text").startswith("Moderator: ")
    assert p.nonstop_cb.cget("text") == "∞: Off"
    p.nonstop_cb.set("Wander")
    assert p.nonstop_cb.cget("text") == "∞: Wander"
    p.nonstop_cb.set("Off")


def test_deep_cuts_button_sits_between_drift_and_infinity(app, ui):
    p = ui.play
    p._show_more(True)
    ui.pump(0.2)
    texts = [w.cget("text") for w in p.extras_row.pack_slaves() if hasattr(w, "_label")]
    order = [t.split(":")[0] for t in texts]
    assert order[:6] == ["Seed", "Play Mode", "Moderator", "Drift", "Deep Cuts", "∞"], texts


def test_deep_cuts_button_sets_every_option(app, ui):
    p, e = ui.play, app.engine
    p.deepcuts_var.set("Spaced")
    p._on_deepcuts_changed()
    env = (app.folder / ".env").read_text()
    for g in ("ARTISTS", "TRACKS", "VIBE"):
        assert f"DEEP_CUTS_{g}=spaced" in env
    assert all(e.DEEP_CUTS[g]["mode"] == "spaced" for g in e.DEEP_CUT_GROUPS)
    assert "DEEP_CUTS_TOP" not in env
    p.deepcuts_var.set("Off")
    p._on_deepcuts_changed()
    assert all(e.DEEP_CUTS[g]["mode"] == "off" for g in e.DEEP_CUT_GROUPS)


def test_deep_cuts_button_shows_off_when_options_differ(app, ui):
    app.set_env(DEEP_CUTS_ARTISTS="spaced", DEEP_CUTS_TRACKS="shuffled", DEEP_CUTS_VIBE="spaced")
    ui.play._sync_play_switches()
    assert ui.play.deepcuts_var.get() == "Off"
    app.set_env(DEEP_CUTS_TRACKS="spaced")
    ui.play._sync_play_switches()
    assert ui.play.deepcuts_var.get() == "Spaced"



def test_infinity_is_bigger_and_bold(app, ui):
    p = ui.play
    sym_font, val_font = p.nonstop_cb._symbol_fonts()
    assert sym_font.size > val_font.size * 1.4, "the symbol a couple of sizes bigger"
    assert "Bold" in " ".join(sym_font.getname()), sym_font.getname()


def test_infinity_is_drawn_in_so_nothing_can_cover_it(app, ui):
    """Drawn into the button's picture: no windows on top for a neighbour's redraw to paint over."""
    p = ui.play
    assert not p.nonstop_cb._label.winfo_children()
    before = p.nonstop_cb._label.cget("image")
    p.nonstop_cb.set("Wander")
    assert p.nonstop_cb._label.cget("image") != before, "a new picture for the new value"
    p.deepcuts_cb._step(1)   # a neighbour changes size
    ui.pump(0.2)
    assert p.nonstop_cb.cget("text") == "∞: Wander"
    p.nonstop_cb.set("Off")
    p.deepcuts_cb.set("Off")


def test_infinity_centred_up_and_down(app, ui):
    import tabs
    b = ui.play.nonstop_cb
    w, h = b._size
    sym_font, val_font = b._symbol_fonts()
    (sx, sy), (vx, vy) = tabs.symbol_layout(w, h, "∞", "Wander", sym_font, val_font)
    _, top, _, bottom = sym_font.getbbox("∞")
    _, x_top, _, x_bottom = val_font.getbbox("x")
    value_middle = vy + (x_top + x_bottom) / 2
    assert abs((sy + top + sy + bottom) / 2 - value_middle) <= 1, "the glyph sits level with the value, not the button"


def test_help_switch_gates_the_play_tab_notes(app, ui):
    p = ui.play
    assert p.help_var.get() == "Off", "off by default"
    for widget in (p.deepcuts_cb, p.drift_cb, p.more_button, p.output_cb, p.buttons[0]):
        assert not widget._tooltip.when(), "no notes while ? is off"
    p.help_var.set("On")
    p._on_help_changed()
    for widget in (p.deepcuts_cb, p.drift_cb, p.more_button, p.output_cb, p.buttons[0]):
        assert widget._tooltip.when()
    assert "PLAY_HELP=1" in (app.folder / ".env").read_text(), "remembered"
    assert p.review_panel._notes_on(), "Review follows it too"
    p.help_var.set("Off")
    p._on_help_changed()
    assert not p.review_panel._notes_on()


def test_greyed_out_notes_show_whatever_help_says(app, ui):
    p = ui.play
    app.set_env(ANTHROPIC_API_KEY="")
    assert p._moderator_tip.when(), "why the Moderator is greyed out shows with ? off"


def test_play_notes_are_two_and_a_half_buttons_wide(app, ui):
    p = ui.play
    width = p.buttons[0]._size[0]
    assert p.note_wrap() == int(width * 2.5)
    for widget in (p.deepcuts_cb, p.more_button, p.buttons[0]):
        assert widget._tooltip._wrap() == int(width * 2.5)
    assert p.review_panel._note_wrap() == int(width * 2.5), "Review's notes match"
