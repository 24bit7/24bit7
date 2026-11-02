"""
The More Options row's switches as overrides (Ben, 2 Nov 2026). The row open is the override: its
Moderator, Deep Cuts and Non-stop switches beat every playlist's own settings for every build; closed,
the pages decide. Off turns the thing off; On runs it the playlist's own way, else the standard
playlist of its kind's way, else the shipped default. Seeded once from the 1.28 row's values in .env.
"""


def mods():
    import buttons
    import overrides
    import playmix
    return buttons, overrides, playmix


def unseeded(playmix):
    data = playmix.load()
    data["switches"] = None
    playmix._save(data)


def by_name(buttons, name):
    return next(b for b in buttons.load() if b["name"] == name)


def test_the_switches_seed_once_from_the_old_row_and_start_off_on_a_fresh_install(app):
    buttons, overrides, playmix = mods()
    unseeded(playmix)
    assert overrides.switches() == {"moderator": False, "deep_cuts": False, "nonstop": False}, "a fresh .env: all off"
    unseeded(playmix)
    app.set_env(AI_MODERATOR_ARTISTS="balanced", DEEP_CUTS_TRACKS="spaced", NONSTOP_ARTISTS="1")
    assert overrides.switches() == {"moderator": True, "deep_cuts": True, "nonstop": True}, "1.28's row, not off: on"
    app.set_env(AI_MODERATOR_ARTISTS="off", DEEP_CUTS_TRACKS="off", NONSTOP_ARTISTS="0")
    assert overrides.switches() == {"moderator": True, "deep_cuts": True, "nonstop": True}, "seeded once, then remembered"
    assert overrides.set_switch("deep_cuts", False)["deep_cuts"] is False
    assert overrides.switches()["deep_cuts"] is False and overrides.switches()["moderator"] is True


def test_with_the_row_closed_the_switches_do_nothing(app):
    buttons, overrides, playmix = mods()
    playmix.set_open(False)
    overrides.set_switches({"moderator": False, "deep_cuts": False, "nonstop": False})
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="strict", DEEP_CUTS_ARTISTS="shuffled",
                                             NONSTOP_ARTISTS="1"))
    artists = buttons.get(artists["id"])
    assert overrides.layer(artists, "artists") == {}
    assert buttons.nonstop_config(artists)["on"] is True, "the page decides"
    r = app.Lines()
    buttons.run(artists, report=r, seed_info=app.engine.typed_seed_info("The Beatles", ""))
    assert not r.has("More Options"), "nothing said when nothing is overridden"


def test_off_switches_turn_the_three_off_for_a_build_and_the_console_says_so(app, monkeypatch):
    buttons, overrides, playmix = mods()
    playmix.set_open(True)
    overrides.set_switches({"moderator": False, "deep_cuts": False, "nonstop": False})
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="strict", DEEP_CUTS_ARTISTS="shuffled",
                                             NONSTOP_ARTISTS="1"))
    artists = buttons.get(artists["id"])
    assert overrides.layer(artists, "artists") == {"AI_MODERATOR_ARTISTS": "off", "DEEP_CUTS_ARTISTS": "off"}
    assert buttons.nonstop_config(artists)["on"] is False, "the switch beats the page"
    seen = {}
    e = app.engine

    def fake_build(report=print, seed_info=None, **kw):
        seen["moderator"] = e.AI_MODERATOR_BY["artists"]
        seen["deep"] = e.DEEP_CUTS["artists"]["mode"]
        report("built")
    monkeypatch.setattr(e, buttons.BUILDERS["artists"], fake_build)
    resting = (e.AI_MODERATOR_BY["artists"], dict(e.PROFILE))
    r = app.Lines()
    buttons.run(artists, report=r, seed_info=e.typed_seed_info("The Beatles", ""))
    assert seen == {"moderator": "off", "deep": "off"}, "laid over the playlist's own settings for the build"
    assert r.has("More Options: Moderator off, Deep Cuts off, Non-stop off, over this playlist's own settings.")
    assert (e.AI_MODERATOR_BY["artists"], dict(e.PROFILE)) == resting, "and lifted off again afterwards"
    r = app.Lines()
    buttons.run(artists, report=r, seed_info=e.typed_seed_info("The Beatles", ""), topup=True)
    assert not r.has("More Options"), "a Non-stop top-up isn't a new build: said once"
    playmix.set_open(False)


def test_on_runs_it_the_playlists_way_then_the_standards_then_the_shipped_default(app):
    buttons, overrides, playmix = mods()
    playmix.set_open(True)
    overrides.set_switches({"moderator": True, "deep_cuts": True, "nonstop": True})
    artists = buttons.standard("artists")
    # the playlist's own page says: its way
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="relaxed", DEEP_CUTS_ARTISTS="shuffled",
                                             NONSTOP_ARTISTS="1", NONSTOP_ARTISTS_RESEED="second"))
    assert overrides.layer(buttons.get(artists["id"]), "artists") == {"AI_MODERATOR_ARTISTS": "relaxed",
                                                                        "DEEP_CUTS_ARTISTS": "shuffled"}
    assert buttons.nonstop_config(buttons.get(artists["id"]))["reseed"] == "second"
    # a playlist of the kind with it off: the standard's way
    own = buttons.add("Quiet Evening", "artists")
    buttons.set_settings(own["id"], dict(own["settings"], AI_MODERATOR_ARTISTS="off", DEEP_CUTS_ARTISTS="off", NONSTOP_ARTISTS="0",
                                         NONSTOP_ARTISTS_RESEED="last"))
    assert overrides.layer(buttons.get(own["id"]), "artists") == {"AI_MODERATOR_ARTISTS": "relaxed", "DEEP_CUTS_ARTISTS": "shuffled"}
    cfg = buttons.nonstop_config(buttons.get(own["id"]))
    assert cfg["on"] is True and cfg["reseed"] == "second", "the standard's Non-stop set-up"
    # the standard off too: the shipped default
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="off", DEEP_CUTS_ARTISTS="off", NONSTOP_ARTISTS="0"))
    assert overrides.layer(buttons.get(own["id"]), "artists") == {"AI_MODERATOR_ARTISTS": "balanced", "DEEP_CUTS_ARTISTS": "spaced"}
    cfg = buttons.nonstop_config(buttons.get(own["id"]))
    assert cfg["on"] is True and cfg["reseed"] == "last" and cfg["using"] == "artists"
    # Artist's Top Tracks has no Moderator and no Deep Cuts: the switches leave it alone
    top = buttons.standard("top")
    assert overrides.layer(top, "top") == {}
    playmix.set_open(False)


def test_from_playlist_reads_a_pages_three_as_switches(app):
    buttons, overrides, playmix = mods()
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="balanced", DEEP_CUTS_ARTISTS="off",
                                             NONSTOP_ARTISTS="1"))
    assert overrides.from_playlist(buttons.get(artists["id"])) == {"moderator": True, "deep_cuts": False, "nonstop": True}
    top = buttons.standard("top")
    buttons.set_settings(top["id"], dict(top["settings"], NONSTOP_TOP="0"))
    assert overrides.from_playlist(buttons.get(top["id"])) == {"moderator": False, "deep_cuts": False, "nonstop": False}
    assert overrides.set_switches(overrides.from_playlist(buttons.get(artists["id"])))["nonstop"] is True
