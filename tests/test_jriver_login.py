"""
jkrichards on the forum (26 Oct 2026): on two Windows 11 PCs the zone list was empty and 24bit7 said it
couldn't connect to JRiver. JRiver was there; it turned 24bit7 away for want of a login, and its
"Access denied." was read as XML, so the console said "JRiver isn't reachable (syntax error...)".
A refusal now says where to set a login; no answer at all says to check Media Network.
"""


def test_a_refusal_says_to_set_a_login(app):
    app.jriver.refused.update({"Playback/Info", "Playback/Zones"})
    assert app.engine.get_playing_info() is None
    assert app.printed.has("JRiver turned 24bit7 away (error 401)")
    assert app.printed.has("Tools > Options > Media Network > Authentication")
    assert app.printed.has("Settings > Keys")
    assert not app.printed.has("syntax error")


def test_an_empty_zone_list_says_why(app):
    app.jriver.refused.add("Playback/Zones")
    assert app.engine.zone_names() == []
    assert app.engine.JRIVER_REFUSED[0]
    assert app.printed.has("JRiver turned 24bit7 away")
    app.jriver.refused.clear()
    assert app.engine.zone_names(), "the zones come back once JRiver lets 24bit7 in"
    assert not app.engine.JRIVER_REFUSED[0]


def test_no_answer_says_to_check_media_network(app):
    app.jriver.up = False
    assert app.engine.get_playing_info() is None
    assert app.printed.has("JRiver isn't answering at fake-jriver:52199")
    assert app.printed.has("Tools > Options > Media Network")
    assert not app.printed.has("turned 24bit7 away")


def test_said_once(app):
    app.jriver.refused.update({"Playback/Info", "Playback/Zones"})
    for _ in range(3):
        app.engine.get_playing_info()
        app.engine.zone_names()
    assert len([line for line in app.printed if "turned 24bit7 away" in line]) == 1


def test_support_log_names_the_refusal(app):
    app.jriver.refused.add("Alive")
    assert "JRiver: refused 24bit7 (error 401)" in app.engine.diagnostics_text()
