"""Listen on Tidal, Create Playlist and Additional Outputs: what the engine reads, with the defaults older .env files get."""


def test_defaults_keep_things_as_they_were(app):
    """An .env from before these settings: YouTube everywhere it was, Tidal nowhere until ticked."""
    e = app.engine
    assert "PLAYLIST_SITES" not in app.env and "EXTRA_OUTPUTS" not in app.env
    assert e.PLAYLIST_SITES == ["youtube"]
    assert e.EXTRA_OUTPUTS == ["youtube"]
    app.set_env(OUTPUT_TARGET="youtube")
    assert e.OUTPUT_TARGET == "youtube"


def test_ticks_read(app):
    e = app.engine
    app.set_env(PLAYLIST_SITES="youtube,tidal", EXTRA_OUTPUTS="tidal", LISTEN_SITES="youtube,tidal")
    assert e.PLAYLIST_SITES == ["youtube", "tidal"]
    assert e.EXTRA_OUTPUTS == ["tidal"]
    assert e.LISTEN_SITES == ["youtube", "tidal"]
    app.set_env(PLAYLIST_SITES="", EXTRA_OUTPUTS="", LISTEN_SITES="")
    assert e.PLAYLIST_SITES == [] and e.EXTRA_OUTPUTS == [] and e.LISTEN_SITES == []


def test_an_unticked_output_is_never_used(app):
    e = app.engine
    app.set_env(OUTPUT_TARGET="youtube", EXTRA_OUTPUTS="tidal")
    assert e.OUTPUT_TARGET == "jriver" and e.output_streaming() is None
    app.set_env(OUTPUT_TARGET="zone:Speakers", EXTRA_OUTPUTS="")
    assert e.OUTPUT_TARGET == "zone:Speakers", "zones are never affected"


def test_listen_on_tidal_searches_artist_and_track(app):
    import importlib
    discover_gui = importlib.import_module("discover_gui")
    assert dict(app.engine.LISTEN_OPTIONS)["tidal"] == "Tidal"
    url = discover_gui.LISTEN_SEARCH["tidal"]("Mazzy%20Star%20Fade%20Into%20You")
    assert url == "https://tidal.com/search?q=Mazzy%20Star%20Fade%20Into%20You"
