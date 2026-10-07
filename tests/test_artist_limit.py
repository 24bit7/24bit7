"""
Similar Artists' Limit total tracks to: ticked stops at the number, unticked keeps every track found.
"""


def count_line(lines):
    import re
    for line in lines:
        m = re.search(r"Done: (\d+) tracks? (queued|sent|added)", line)
        if m:
            return int(m.group(1))
    return None


def build(app, topup=False):
    r = app.Lines()
    seed = app.engine.typed_seed_info("The Beatles", "Here Comes The Sun")
    app.engine.create_similar_playlist(report=r, seed_info=seed, topup=topup)
    return r


SETUP = dict(SIMILAR_ARTIST_TRACK_COUNT="5", TRACKS_PER_ARTIST_POOL="3", TRACKS_PER_ARTIST_PICK="3",
             SKIP_PLAYED_ARTISTS="0", DRIFT_ARTISTS="0")


def test_limit_ticked_stops_at_the_number(app):
    app.set_env(SIMILAR_ARTIST_TRACK_LIMIT="1", **SETUP)
    r = build(app)
    assert count_line(r) == 5, r.text()


def test_limit_unticked_keeps_every_track(app):
    app.set_env(SIMILAR_ARTIST_TRACK_LIMIT="0", **SETUP)
    r = build(app)
    assert r.has("no limit on total tracks"), r.text()
    assert count_line(r) > 5, r.text()


def test_nonstop_topup_keeps_to_the_number(app):
    app.set_env(SIMILAR_ARTIST_TRACK_LIMIT="0", **SETUP)
    r = build(app, topup=True)
    assert count_line(r) == 5, r.text()


def test_limit_defaults_to_ticked_and_is_a_device_setting(app):
    assert app.engine.SIMILAR_ARTIST_TRACK_LIMIT is True
    assert "SIMILAR_ARTIST_TRACK_LIMIT" in app.engine.PROFILE_KEYS["playlist"]
