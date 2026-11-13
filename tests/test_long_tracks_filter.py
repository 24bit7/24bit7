"""
Long Tracks ships as a filter (Ben, 13 Nov 2026): off, Every playlist ticked for when it's turned on, one rule that
keeps tracks shorter than fifteen minutes, so the long ones are left out. Added once: deleted, it stays gone. It was
asked for as a setting beside Hidden Tracks, which a Duration rule already does; shipping it shows what filters can do.
"""


def long_tracks():
    import filters
    return next((x for x in filters.load() if x["id"] == filters.LONG_ID), None)


def test_long_tracks_ships_off_for_every_playlist(app):
    f = long_tracks()
    assert f is not None, "Long Tracks isn't in the list"
    assert f["name"] == "Long Tracks" and not f["on"] and f["every"]
    assert f["rules"] == [{"field": "duration", "op": "shorter", "value": "15", "value2": ""}]
    assert f["builtin"] == "", "an ordinary filter: renamed, changed or deleted like any other"


def test_its_rule_leaves_out_a_track_over_fifteen_minutes_and_keeps_one_under(app):
    import filters
    rule = long_tracks()["rules"][0]
    assert filters.rule_result(rule, "1", {"Duration": str(16 * 60)}) is False
    assert filters.rule_result(rule, "1", {"Duration": str(14 * 60)}) is True


def test_deleted_it_doesnt_come_back(app):
    import filters
    filters.save([x for x in filters.load() if x["id"] != filters.LONG_ID])
    assert long_tracks() is None
