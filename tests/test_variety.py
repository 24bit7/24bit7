"""
Similar Tracks' Variety option: Yes picks at random from a wider pool, No takes the closest in order.
"""


def build(app):
    r = app.Lines()
    seed = app.engine.typed_seed_info("The Beatles", "Here Comes The Sun")
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed)
    return r


def found(lines):
    """The 'In library:' tracks in the order they were found (closest first)."""
    out = []
    for line in lines:
        line = line.strip()
        if line.startswith("In library: "):
            out.append(line[len("In library: "):].rsplit("  (", 1)[0])
    return out


def test_variety_no_takes_the_closest_in_order(app):
    app.set_env(SIMILAR_TRACK_COUNT="6", SIMILAR_TRACK_ORDER="similar first", SIMILAR_TRACK_VARIETY="no",
                SKIP_PLAYED_TRACKS="0", AI_MODERATOR_TRACKS="off")
    assert app.engine.SIMILAR_TRACK_VARIETY is False
    r = build(app)
    titles = app.jriver.titles("Speakers")
    assert not r.has("at random"), r.text()
    song = lambda t: t.split(" - ", 1)[-1]   # the library may tag the artist differently ("Kinks, The")
    assert [song(t) for t in titles[1:]] == [song(t) for t in found(r)[:len(titles) - 1]], r.text()


def test_variety_yes_picks_from_a_wider_pool(app):
    app.set_env(SIMILAR_TRACK_COUNT="6", SIMILAR_TRACK_VARIETY="yes", SKIP_PLAYED_TRACKS="0",
                AI_MODERATOR_TRACKS="off")
    assert app.engine.SIMILAR_TRACK_VARIETY is True
    r = build(app)
    assert r.has("at random"), r.text()
    assert len(found(r)) > len(app.jriver.titles("Speakers")) - 1, r.text()


def test_variety_defaults_to_no(app):
    assert app.engine.SIMILAR_TRACK_VARIETY is False


def test_variety_is_a_device_setting(app):
    assert "SIMILAR_TRACK_VARIETY" in app.engine.PROFILE_KEYS["playlist"]
