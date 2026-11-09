"""The engine calls behind the Now Playing row's Stop, Clear Playing Now and Skip Track (9 Nov 2026). Windowless."""


def test_stop_clear_and_skip_act_on_the_zone_and_a_skip_is_counted(app):
    e, j = app.engine, app.jriver
    keys = [j.key_of("The Beatles", "Something"), j.key_of("The Beatles", "Here Comes The Sun")]
    j.play("Speakers", keys)
    zone = j.zone("Speakers").id
    skipped = e.skip_track(zone)
    assert skipped == keys[0] and j.zone("Speakers").pos == 1
    assert j.fields_made and j.fields_made[0][0] == e.SKIP_FIELD, "a Skip Track counts like a voice skip"
    e.stop_zone(zone)
    assert j.zone("Speakers").state == 0 and j.zone("Speakers").playlist == keys, "stopped, the list kept"
    e.clear_playing_now(zone)
    assert j.zone("Speakers").playlist == [] and j.zone("Speakers").pos == -1


def test_a_skip_with_nothing_playing_records_nothing(app):
    e, j = app.engine, app.jriver
    zone = j.zone("Kitchen").id
    assert e.skip_track(zone) in (None, "", "-1") and not j.fields_made
