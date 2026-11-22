"""
Alexa checks its own connection (Ben, 20 Nov 2026). On 17 Nov the media PC was renamed, its public address changed
with it, and the first anyone knew was the Echo saying 24bit7 wasn't connected. 24bit7 now learns the address
Alexa's requests come in on (no setting), tries it at start-up and each hour, and says once in the console when
it stops answering, and once more when it's back.
"""

import json
import urllib.request

from test_voice import alexa, KITCHEN   # noqa: F401  (the mock Alexa fixture)

PUBLIC = "mediaserver.example.ts.net"


def command(app, device=KITCHEN, **headers):
    req = urllib.request.Request(f"http://127.0.0.1:{app.engine.VOICE_PORT}/command",
                                 data=json.dumps({"intent": "pause", "value": "", "device": device}).encode(),
                                 headers={"Content-Type": "application/json", "X-24bit7-Key": app.engine.VOICE_KEY,
                                          **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_the_address_is_learnt_from_alexas_request(app, alexa):
    import voice
    assert voice.public_address() == "", "nobody has used voice: nothing to check"
    command(app)   # straight to the listener, as Settings' Test button and these tests call it
    assert voice.public_address() == "", "this PC's own address isn't a public one"
    command(app, **{"X-Forwarded-Host": PUBLIC, "X-Forwarded-Proto": "https"})
    assert voice.public_address() == f"https://{PUBLIC}"
    command(app, device=voice.TEST_DEVICE, **{"X-Forwarded-Host": "other.example.net"})
    assert voice.public_address() == f"https://{PUBLIC}", "the Test button isn't Alexa"
    command(app, Host="renamed.example.ts.net")   # a tunnel that passes the name as Host
    assert voice.public_address() == "https://renamed.example.ts.net", "it follows a rename by itself"


def test_a_dead_address_is_said_once_after_two_tries_and_once_when_its_back(app, alexa, monkeypatch):
    import voice
    command(app, **{"X-Forwarded-Host": PUBLIC})
    answers, tried = [True], []
    monkeypatch.setattr(voice, "_address_answers", lambda address: tried.append(address) or answers[0])
    assert voice.check_address() is None and tried == [f"https://{PUBLIC}"]
    answers[0] = False
    assert voice.check_address() is None, "one miss could be a blip: it's tried again first"
    assert voice.address_wait() == voice.ADDRESS_RETRY
    line = voice.check_address()
    assert line == (f"Problem: Alexa can't reach 24bit7 at https://{PUBLIC}. Has the PC's name or the tunnel "
                    "changed?"), line
    assert voice.check_address() is None and voice.check_address() is None, "said once, not every hour"
    assert voice.address_wait() == voice.ADDRESS_EVERY
    answers[0] = True
    assert voice.check_address() == f"Alexa can reach 24bit7 again at https://{PUBLIC}."
    assert voice.check_address() is None


def test_nothing_is_checked_until_alexa_has_called(app, alexa, monkeypatch):
    import voice
    tried = []
    monkeypatch.setattr(voice, "_address_answers", lambda address: tried.append(address) or False)
    assert voice.check_address() is None and voice.check_address() is None and not tried


def test_an_answer_of_any_kind_from_the_listener_counts(app, alexa):
    """Asked without the key, the listener says 401: the route works. Only no answer at all is a dead address."""
    import voice
    assert voice._address_answers(f"http://127.0.0.1:{app.engine.VOICE_PORT}") is True
    assert voice._address_answers("http://127.0.0.1:9") is False
