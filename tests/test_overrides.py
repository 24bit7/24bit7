"""
The More Options row's switches as overrides (Ben, 2 Nov 2026). The row open is the override: its
Moderator, Deep Cuts and Non-stop switches beat every playlist's own settings for every build; closed,
the pages decide. Each switch holds the setting that runs (Off, Relaxed, Balanced, Strict; Off, Spaced,
Shuffled; Off, Keep It Tight, Wander), as the 1.28 row did. Seeded once from that row's values in .env.
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


OFF = {"moderator": "off", "deep_cuts": "off", "nonstop": "off"}


def test_the_switches_seed_once_from_the_old_row_and_start_off_on_a_fresh_install(app):
    buttons, overrides, playmix = mods()
    unseeded(playmix)
    assert overrides.switches() == OFF, "a fresh .env: all off"
    unseeded(playmix)
    app.set_env(AI_MODERATOR_ARTISTS="strict", DEEP_CUTS_TRACKS="shuffled", NONSTOP_ARTISTS="1", NONSTOP_ARTISTS_MODE="tight")
    assert overrides.switches() == {"moderator": "strict", "deep_cuts": "shuffled", "nonstop": "tight"}, "1.28's row"
    app.set_env(AI_MODERATOR_ARTISTS="off", DEEP_CUTS_TRACKS="off", NONSTOP_ARTISTS="0")
    assert overrides.switches()["moderator"] == "strict", "seeded once, then remembered"
    assert overrides.set_switch("deep_cuts", "spaced")["deep_cuts"] == "spaced"
    assert overrides.switches() == {"moderator": "strict", "deep_cuts": "spaced", "nonstop": "tight"}
    # the first build of the day kept True/False: those read as Balanced, Spaced and Wander, or off
    data = playmix.load()
    data["switches"] = {"moderator": True, "deep_cuts": False, "nonstop": True}
    playmix._save(data)
    assert overrides.switches() == {"moderator": "balanced", "deep_cuts": "off", "nonstop": "journey"}
    assert overrides.labels("nonstop") == ["Off", "Keep It Tight", "Wander"] and overrides.code_for("nonstop", "Wander") == "journey"


def test_with_the_row_closed_the_switches_do_nothing(app):
    buttons, overrides, playmix = mods()
    playmix.set_open(False)
    overrides.set_switches(OFF)
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
    overrides.set_switches(OFF)
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
    assert r.has("More Options: Moderator Off, Deep Cuts Off, Non-stop Off, over this playlist's own settings.")
    assert (e.AI_MODERATOR_BY["artists"], dict(e.PROFILE)) == resting, "and lifted off again afterwards"
    r = app.Lines()
    buttons.run(artists, report=r, seed_info=e.typed_seed_info("The Beatles", ""), topup=True)
    assert not r.has("More Options"), "a Non-stop top-up isn't a new build: said once"
    playmix.set_open(False)


def test_a_setting_on_a_switch_runs_for_every_playlist_and_the_rest_stays_the_playlists_own(app, monkeypatch):
    buttons, overrides, playmix = mods()
    playmix.set_open(True)
    overrides.set_switches({"moderator": "relaxed", "deep_cuts": "shuffled", "nonstop": "tight"})
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="strict", DEEP_CUTS_ARTISTS="off",
                                             DEEP_CUTS_ARTISTS_SHARE="30", NONSTOP_ARTISTS="1", NONSTOP_ARTISTS_RESEED="second",
                                             NONSTOP_ARTISTS_MODE="journey"))
    artists = buttons.get(artists["id"])
    assert overrides.layer(artists, "artists") == {"AI_MODERATOR_ARTISTS": "relaxed", "DEEP_CUTS_ARTISTS": "shuffled"}
    seen = {}
    e = app.engine

    def fake_build(report=print, seed_info=None, **kw):
        seen["deep"] = dict(e.DEEP_CUTS["artists"])
        report("built")
    monkeypatch.setattr(e, buttons.BUILDERS["artists"], fake_build)
    buttons.run(artists, report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", ""))
    assert seen["deep"] == {"mode": "shuffled", "share": 30}, "the mode is the switch's, the share the playlist's own"
    cfg = buttons.nonstop_config(artists)
    assert cfg["on"] is True and cfg["mode"] == "tight" and cfg["reseed"] == "second", "the mode is the switch's, the rest its own"
    # a playlist whose page has Non-stop off: the standard playlist of its kind's using and reseeding, in the switch's mode
    own = buttons.add("Quiet Evening", "artists")
    buttons.set_settings(own["id"], dict(own["settings"], NONSTOP_ARTISTS="0", NONSTOP_ARTISTS_RESEED="last"))
    cfg = buttons.nonstop_config(buttons.get(own["id"]))
    assert cfg["on"] is True and cfg["mode"] == "tight" and cfg["reseed"] == "second"
    # Artist's Top Tracks has no Moderator and no Deep Cuts: the switches leave it alone
    assert overrides.layer(buttons.standard("top"), "top") == {}
    playmix.set_open(False)


def test_from_playlist_reads_a_pages_three_as_the_switches_would_show_them(app):
    buttons, overrides, playmix = mods()
    artists = buttons.standard("artists")
    buttons.set_settings(artists["id"], dict(artists["settings"], AI_MODERATOR_ARTISTS="balanced", DEEP_CUTS_ARTISTS="off",
                                             NONSTOP_ARTISTS="1", NONSTOP_ARTISTS_MODE="tight"))
    assert overrides.from_playlist(buttons.get(artists["id"])) == {"moderator": "balanced", "deep_cuts": "off", "nonstop": "tight"}
    top = buttons.standard("top")
    buttons.set_settings(top["id"], dict(top["settings"], NONSTOP_TOP="0"))
    assert overrides.from_playlist(buttons.get(top["id"])) == OFF
    assert overrides.set_switches(overrides.from_playlist(buttons.get(artists["id"])))["nonstop"] == "tight"
    assert overrides.summary() == "Moderator Balanced, Deep Cuts Off, Non-stop Keep It Tight"
