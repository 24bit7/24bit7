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
    assert p.moderator_cb.cget("text") == "AI Moderator: Off"
    right_click(p.moderator_cb)
    assert p.moderator_cb.cget("text") == "AI Moderator: Strict"
    click(p.moderator_cb)
    assert p.moderator_cb.cget("text") == "AI Moderator: Off"
    click(p.moderator_cb)
    assert p.moderator_cb.cget("text") == "AI Moderator: Relaxed"


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
    assert texts[-2:] == ["+ Add Playlist", "Show Credits"], texts
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
