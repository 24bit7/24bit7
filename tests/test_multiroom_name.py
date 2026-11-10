"""
"Multiroom" in the Output list means one thing (10 Nov 2026). Ben's house copy had a JRiver zone of that name and
the feature off: picking the zone was kept as the feature, the engine found the feature off and sent the playlist
where Same zone goes (the Speakers), and nothing said so. Now the name is the feature only while the feature is on,
a zone that shares it is left out of the lists while it is, and an Output that isn't switched on says where the
playlist went instead. Nothing here opens a window.
"""

import pytest

ROAD_TRIP = {"ID": "202", "Name": "Road Trip"}
ON = dict(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Sonos", MULTIROOM_FOLLOWER="Speakers")


@pytest.fixture
def zone_named_multiroom(app):
    """A JRiver zone called Multiroom beside the usual three, as on Ben's media PC."""
    from fakes import Zone
    j = app.jriver
    j.zones["10016"] = Zone("10016", "Multiroom")
    j.zone_order.append("10016")
    app.engine._zone_list(fresh=True)
    return j.zones["10016"]


def test_multiroom_is_the_zone_of_that_name_while_the_feature_is_off(app, zone_named_multiroom):
    e = app.engine
    assert not e.MULTIROOM_ENABLED
    assert e.multiroom_or_zone("Multiroom") == "zone:Multiroom"
    assert e.multiroom_or_zone("Kitchen") == "zone:Kitchen"
    assert "Multiroom" in e.listed_zone_names(), "with the feature off the zone is a zone like any other"
    app.set_env(OUTPUT_TARGET=e.multiroom_or_zone("Multiroom"))
    assert e.OUTPUT_TARGET == "zone:Multiroom" and e.OUTPUT_DROPPED is None
    assert e.output_zone() == "10016", "the playlist goes to the zone that was picked"


def test_multiroom_is_the_feature_while_it_is_on_and_the_zone_leaves_the_lists(app, zone_named_multiroom):
    e = app.engine
    app.set_env(**ON)
    assert e.multiroom_or_zone("Multiroom") == "multiroom"
    assert e.multiroom_or_zone("Kitchen") == "zone:Kitchen"
    assert "Multiroom" not in e.listed_zone_names(), "the name showed twice in Output"
    assert "Multiroom" in e.zone_names(), "Settings' own lists still have every zone"
    assert {"Speakers", "Kitchen", "Sonos"} <= set(e.listed_zone_names())


def test_output_on_multiroom_with_the_feature_off_says_where_the_playlist_went(app):
    import embellish
    e = app.engine
    app.set_env(MULTIROOM_ENABLED="0", OUTPUT_TARGET="multiroom")
    assert e.OUTPUT_TARGET == "jriver" and e.OUTPUT_DROPPED == "multiroom"
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, "ordered", "triple", r)
    assert app.jriver.zone("Speakers").playlist, r.text()
    assert r.has("Note: Output is set to Multiroom, but Multiroom isn't switched on (Settings > Other > Multiroom), "
                 "so this went to Speakers."), r.text()


def test_the_note_is_said_once_a_build_and_not_for_a_voice_zone_or_a_top_up(app):
    e = app.engine
    app.set_env(MULTIROOM_ENABLED="0", OUTPUT_TARGET="multiroom")
    keys = list(app.jriver.by_key)[:4]
    e.BUILD_STARTED = 1234.5
    try:
        r = app.Lines()
        e.send_to_jriver(keys[:2], typed=True, report=r)
        e.send_to_jriver(keys[2:], typed=True, report=r, append=True)
        assert sum("Output is set to Multiroom" in line for line in r) == 1, r.text()
        e.BUILD_STARTED = 2345.6   # the next build says it again
        r = app.Lines()
        e.send_to_jriver(keys[:2], typed=True, report=r, zone_name="Kitchen")
        assert not r.has("Output is set to"), "a voice command names its own zone"
        e.send_to_jriver(keys[:2], typed=True, report=r)
        assert r.has("Output is set to Multiroom"), r.text()
    finally:
        e.BUILD_STARTED = None


def test_no_note_when_output_is_what_it_says(app):
    import embellish
    e = app.engine
    for env in (dict(OUTPUT_TARGET="jriver"), dict(OUTPUT_TARGET="zone:Kitchen"), dict(OUTPUT_TARGET="multiroom", **ON)):
        app.set_env(**env)
        assert e.OUTPUT_DROPPED is None, env
        r = app.Lines()
        embellish.embellish(ROAD_TRIP, "ordered", "half", r)
        assert not r.has("Output is set to"), (env, r.text())


def test_an_unticked_streaming_output_says_so_too(app):
    e = app.engine
    app.set_env(OUTPUT_TARGET="tidal", EXTRA_OUTPUTS="")
    assert e.OUTPUT_TARGET == "jriver" and e.OUTPUT_DROPPED == "tidal"
    r = app.Lines()
    e.send_to_jriver(list(app.jriver.by_key)[:1], typed=True, report=r)
    assert r.has("Note: Output is set to Tidal, but Tidal isn't ticked under Settings > Other > Additional Outputs, "
                 "so this went to Speakers."), r.text()
