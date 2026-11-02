"""
Simple and Advanced (Ben, 2 Nov 2026): a mode, not a view. In Simple a playlist builds from its first
config alone with every advanced section off; one that can't be itself there (two configs, or Consensus)
says it needs Advanced and doesn't build; shortcuts rest; the More Options switches still override.
First time: Advanced if any playlist of the listener's own has anything advanced on, else Simple.
"""


def mods():
    import buttons
    import mode
    import playmix
    return buttons, mode, playmix


def unset(playmix):
    data = playmix.load()
    data.pop("mode", None)
    playmix._save(data)


def test_the_first_time_is_simple_unless_the_listeners_own_playlists_use_something_advanced(app):
    buttons, mode, playmix = mods()
    unset(playmix)
    assert mode.current() == "simple", "a fresh install: Consensus and Artist + Guests ship advanced but don't count"
    assert mode.current() == "simple" and playmix.load()["mode"] == "simple", "remembered"
    unset(playmix)
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], DRIFT_ARTISTS="1"))
    assert mode.uses_advanced(buttons.get(artists["id"]), counting_shipped=False) == ["Drift"]
    assert mode.uses_advanced(buttons.get(artists["id"])) == ["Drift", "Hidden Tracks"], "Hidden Tracks ships on"
    assert mode.current() == "advanced", "Drift on a playlist of their own: Advanced"
    unset(playmix)
    buttons.set_settings(artists["id"], dict(artists["settings"], DRIFT_ARTISTS="0", IF_ALL_ELSE_FAILS_ARTISTS="1",
                                             SKIP_LONG_CLOSERS_ARTISTS="1"))
    assert mode.current() == "simple", "the two that ship on don't count"
    assert mode.set_current("advanced") == "advanced" and not mode.is_simple()


def test_simple_builds_the_first_config_with_the_advanced_sections_off_and_the_switches_still_override(app, monkeypatch):
    buttons, mode, playmix = mods()
    import overrides
    e = app.engine
    mode.set_current("simple")
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="strict", DRIFT_ARTISTS="1",
                                             DEEP_CUTS_ARTISTS="shuffled", NONSTOP_ARTISTS="1", SKIP_LONG_CLOSERS_ARTISTS="1",
                                             RUN_AFTER_ARTISTS="1"))
    buttons.set_shortcut(artists["id"], "Ctrl+Alt+7")
    artists = buttons.get(artists["id"])
    assert set(mode.layer("artists")) == {"AI_MODERATOR_ARTISTS", "DRIFT_ARTISTS", "DEEP_CUTS_ARTISTS", "NONSTOP_ARTISTS",
                                          "INNER_CIRCLE_ARTISTS", "SKIP_LONG_CLOSERS_ARTISTS", "IF_ALL_ELSE_FAILS_ARTISTS",
                                          "RUN_AFTER_ARTISTS"}
    assert mode.layer("top") == {"NONSTOP_TOP": "0", "SKIP_LONG_CLOSERS_TOP": "0", "IF_ALL_ELSE_FAILS_TOP": "0", "RUN_AFTER_TOP": "0"}
    seen = {}

    def fake(report=print, seed_info=None, **kw):
        seen.update(moderator=e.AI_MODERATOR_BY["artists"], deep=e.DEEP_CUTS["artists"]["mode"],
                    drift=e.DRIFT["artists"], closers=e.LONG_CLOSERS["artists"], run_after=e.RUN_AFTER["artists"][0])
        report("built")
    monkeypatch.setattr(e, buttons.BUILDERS["artists"], fake)
    buttons.run(artists, report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", ""))
    assert seen["moderator"] == "off" and seen["deep"] == "off" and seen["run_after"] is False
    assert not seen["drift"]["on"] and seen["closers"][0] is False, (seen["drift"], seen["closers"])
    assert buttons.nonstop_config(artists)["on"] is False, "Non-stop rests in Simple"
    assert buttons.with_shortcuts() == [], "so do shortcuts"
    playmix.set_open(True)
    overrides.set_switches({"moderator": "off", "deep_cuts": "spaced", "nonstop": "journey"})
    buttons.run(artists, report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", ""))
    assert seen["deep"] == "spaced", "the More Options switch beats Simple"
    assert buttons.nonstop_config(artists)["on"] is True and buttons.nonstop_config(artists)["mode"] == "journey"
    playmix.set_open(False)
    mode.set_current("advanced")
    buttons.run(artists, report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", ""))
    assert seen["moderator"] == "strict" and seen["deep"] == "shuffled", "Advanced: as the page says"
    assert [b["id"] for b in buttons.with_shortcuts()] == [artists["id"]]


def test_a_playlist_that_needs_advanced_says_so_in_simple_and_does_not_build(app, monkeypatch):
    buttons, mode, playmix = mods()
    e = app.engine
    guests = next(b for b in buttons.load() if b["name"] == "Artist + Guests")
    consensus = next(b for b in buttons.load() if b["name"] == "Consensus")
    assert mode.needs_advanced(guests) and mode.needs_advanced(consensus) and not mode.needs_advanced(buttons.standard("top"))
    built = []
    for kind in ("top", "artists"):
        monkeypatch.setattr(e, buttons.BUILDERS[kind], lambda report=print, seed_info=None, k=kind, **kw: built.append(k))
    mode.set_current("simple")
    r = app.Lines()
    assert buttons.run(guests, report=r, seed_info=e.typed_seed_info("The Beatles", "")) is None
    assert r.has("Artist + Guests needs Advanced: switch to Advanced under Settings > Playlist Settings to build it.")
    assert built == []
    mode.set_current("advanced")
    monkeypatch.setattr(e, "combine_finish", lambda *a, **k: None)
    buttons.run(guests, report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", ""))
    assert built == ["top", "artists"], "Advanced: both configs"
    counts = mode.turns_off()
    assert counts.get("Mix") == 1 and counts.get("Consensus") == 1, counts
    assert mode.summary_of({"Deep Cuts": 3, "Drift": 2, "Non-stop": 3}) == "Deep Cuts, Drift and Non-stop on 3 playlists"
    assert mode.summary_of({"Drift": 1}) == "Drift on one playlist" and mode.summary_of({}) == ""
