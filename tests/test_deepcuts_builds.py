"""Deep Cuts (stage 3): builds topped up with the least played of the seed's genre."""

import re

import pytest


@pytest.fixture(autouse=True)
def corners(app):
    """Twelve obscure Rock artists, three tracks each, never played: the corners deep cuts are for."""
    j = app.jriver
    template = next(r for r in j.tracks if r["Genre"] == "Rock")
    for a in range(12):
        for t in range(3):
            row = dict(template, Key=str(90000 + a * 10 + t), Artist=f"Obscure Band {a}",
                       Name=f"Deep Track {a}-{t}", Album=f"Lost Album {a}", **{"Album Artist (auto)": f"Obscure Band {a}"})
            row.update({"Track #": str(t + 1), "Duration": "240.0", "Number Plays": "0", "Last Played": ""})
            j.tracks.append(row)
            j.by_key[row["Key"]] = row
    app.library.load()


def seed(app, artist="The Beatles", title="Here Comes The Sun"):
    return app.engine.typed_seed_info(artist, title)


def deep_line(lines):
    return next((l for l in lines if "Deep Cuts" in l), "")


def added(lines):
    m = re.search(r"Deep Cuts \([^)]*\): (\d+) from", deep_line(lines))
    return int(m.group(1)) if m else 0


def test_off_by_default(app):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert not deep_line(r), r.text()


def test_similar_tracks_tops_up_by_the_share(app):
    app.set_env(DEEP_CUTS_TRACKS="spaced", DEEP_CUTS_TRACKS_SHARE="20", SIMILAR_TRACK_COUNT="10")
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    line = deep_line(r)
    assert "Deep Cuts (Rock, spaced)" in line and "tracks you rarely play" in line, r.text()
    titles = app.jriver.titles("Speakers")
    n = added(r)
    assert n == round((len(titles) - n) * 0.2), (n, titles)   # on top of the build, not in place of it
    assert titles[0] == "The Beatles - Here Comes The Sun", "the first track still leads"


def test_hundred_percent_is_as_many_again(app):
    app.set_env(DEEP_CUTS_TRACKS="shuffled", DEEP_CUTS_TRACKS_SHARE="100", SIMILAR_TRACK_COUNT="5")
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    titles = app.jriver.titles("Speakers")
    n = added(r)
    assert n and len(titles) == 2 * (len(titles) - n), (n, titles, r.text())


def test_similar_artists_picks_neglected_artists(app):
    app.set_env(DEEP_CUTS_ARTISTS="spaced", DEEP_CUTS_ARTISTS_SHARE="10")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app))
    assert "artists you haven't played lately" in deep_line(r), r.text()


def test_top_tracks_never_gets_deep_cuts(app):
    app.set_env(DEEP_CUTS_ARTISTS="spaced", DEEP_CUTS_TRACKS="spaced", DEEP_CUTS_VIBE="spaced")
    assert "top" not in app.engine.DEEP_CUTS


def test_no_genre_says_why(app):
    for row in app.jriver.tracks:
        if row["Artist"] == "The Beatles":
            row["Genre"] = ""
    app.library.load()
    app.set_env(DEEP_CUTS_TRACKS="spaced")
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert "Deep Cuts: none this time, as" in deep_line(r), r.text()


def test_logged_to_discover(app):
    app.set_env(DEEP_CUTS_TRACKS="spaced", DEEP_CUTS_TRACKS_SHARE="20")
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    rows = app.engine.db().execute("SELECT sources, found FROM discoveries WHERE sources = 'Deep Cuts'").fetchall()
    assert len(rows) == added(r) and all(found for _, found in rows)


def test_moderator_removals_are_replaced(app, monkeypatch):
    e = app.engine
    app.set_env(DEEP_CUTS_TRACKS="spaced", DEEP_CUTS_TRACKS_SHARE="30", SIMILAR_TRACK_COUNT="10")
    monkeypatch.setattr(e, "moderator_level", lambda: "balanced")
    checked = []

    def moderate(tracks, seed_text, report=print, level=None, reference=None):
        checked.append(len(tracks))
        return {tracks[0][0]}   # removes one of each list it's shown
    monkeypatch.setattr(e, "moderate", moderate)
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    want = round((len(app.jriver.titles("Speakers")) - added(r)) * 0.3)
    assert added(r) == want, r.text()   # the spares covered the removal


def test_ai_playlist_uses_the_genre_its_picks_share(app):
    app.set_env(DEEP_CUTS_VIBE="spaced", DEEP_CUTS_VIBE_SHARE="20", VIBE_TRACK_COUNT="10")
    r = app.Lines()
    app.engine.create_vibe_playlist("Sunday morning", report=r)
    line = deep_line(r)
    assert line, r.text()
    assert "none this time" in line or "Deep Cuts (" in line


def test_tidal_output_gets_the_same_tracks_from_tidal(app, monkeypatch):
    e = app.engine
    app.set_env(TIDAL_CLIENT_ID="id", TIDAL_CLIENT_SECRET="secret", TIDAL_REFRESH_TOKEN="fake-refresh",
                OUTPUT_TARGET="tidal", EXTRA_OUTPUTS="youtube,tidal", DEEP_CUTS_TRACKS="spaced",
                DEEP_CUTS_TRACKS_SHARE="20")
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert "none of the picks were on Tidal" in deep_line(r), r.text()   # the fake Tidal hasn't got them
    real = e.tidal_track_id_cached
    monkeypatch.setattr(e, "tidal_track_id_cached",
                        lambda a, t: f"t-{t}" if a.startswith("Obscure Band") else real(a, t))
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert added(r), r.text()
    assert not app.jriver.calls_to("Playback/PlayByKey")


def test_a_device_with_its_own_settings_gets_deep_cuts(app):
    """A voice build for a device with settings of its own follows that device's Deep Cuts switch."""
    e = app.engine
    assert e.DEEP_CUTS["tracks"]["mode"] == "off"
    e.use_profile({"DEEP_CUTS_TRACKS": "spaced", "DEEP_CUTS_TRACKS_SHARE": "20"})
    try:
        assert e.DEEP_CUTS["tracks"] == {"mode": "spaced", "share": 20}
        r = app.Lines()
        e.create_similar_tracks_playlist(report=r, seed_info=seed(app))
        assert added(r), r.text()
    finally:
        e.use_profile({})
    assert e.DEEP_CUTS["tracks"]["mode"] == "off", "Windows (Main)'s own setting again"


def test_the_line_is_all_german_in_german(app):
    """20 Oct 2026: the mode and 'tracks you rarely play' went into the German line in English."""
    import i18n
    app.set_env(DEEP_CUTS_TRACKS="spaced", DEEP_CUTS_TRACKS_SHARE="20", SIMILAR_TRACK_COUNT="10")
    i18n.set_language("de")
    try:
        r = app.Lines()
        app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    finally:
        i18n.set_language("en")
    line = deep_line(r)
    assert "Deep Cuts (Rock, verteilt)" in line and "aus Titeln, die du selten spielst" in line, r.text()
