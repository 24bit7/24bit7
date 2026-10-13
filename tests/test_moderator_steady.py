"""
The Moderator asks for a fixed temperature (issue #5), and Drift's chain drop names what it
drops and never empties a round (issue #6).
"""

import pytest

from test_engine import _drift


class Reply:
    def __init__(self, text):
        self.text, self.stop_reason, self.usage = text, "stop", None


@pytest.fixture
def openai(app, monkeypatch):
    e = app.engine
    monkeypatch.setattr(e, "AI_PROVIDER", "openai")
    monkeypatch.setattr(e, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(e, "USE_AI", True)
    monkeypatch.setattr(e, "ai_configured", lambda: True)
    monkeypatch.setattr(e, "record_ai", lambda *a, **k: None)
    e._TEMPERATURE_REFUSED.clear()
    e.TEMPERATURE_NOTES.clear()
    sent = []

    class Resp:
        def __init__(self, status, data):
            self.status_code, self._data, self.text = status, data, str(data)

        def json(self):
            return self._data

    state = {"refuse": False}

    def post(url, headers=None, json=None, timeout=None):
        sent.append(dict(json))
        if state["refuse"] and "temperature" in json:
            return Resp(400, {"error": {"message": "Unsupported parameter: 'temperature' is not supported "
                                                   "with this model."}})
        return Resp(200, {"choices": [{"message": {"content": '{"remove": [{"number": 2, "artist": "Artist B", "title": "Song B", '
                                                              '"reason": "too loud"}]}'},
                                       "finish_reason": "stop"}], "usage": {}})
    monkeypatch.setattr(e.requests, "post", post)
    return e, sent, state


TRACKS = [("a", "Artist A", "Song A"), ("b", "Artist B", "Song B"), ("c", "Artist C", "Song C")]


def test_moderator_asks_for_temperature_zero(app, openai):
    e, sent, _ = openai
    r = app.Lines()
    removed = e.moderate(TRACKS, "Seed - Song", report=r, level="strict")
    assert removed == {"b"}, r.text()
    assert sent and sent[0]["temperature"] == 0


def test_refused_temperature_asks_again_without_it_and_says_so_once(app, openai):
    e, sent, state = openai
    state["refuse"] = True
    r = app.Lines()
    assert e.moderate(TRACKS, "Seed - Song", report=r, level="strict") == {"b"}
    assert "temperature" in sent[0] and "temperature" not in sent[1]
    assert r.has("won't take a fixed temperature"), r.text()
    sent.clear()
    r2 = app.Lines()
    e.moderate(TRACKS, "Seed - Song", report=r2, level="strict")
    assert len(sent) == 1 and "temperature" not in sent[0], "not sent again this session"
    assert not r2.has("fixed temperature")


def test_other_ai_calls_leave_temperature_alone(app, openai):
    e, sent, _ = openai
    e.ai_request("hello", 100)
    assert "temperature" not in sent[0]


def test_strict_keeps_borderline_tracks():
    import engine
    assert "If a track is borderline on all three, keep it." in engine.MODERATOR_RULES["strict"]


def test_chain_drop_names_the_tracks(app, monkeypatch):
    d = _drift(app, DRIFT_TRACKS_MODERATOR="strict")
    d.note("Rolling Stones", "Moonlight Mile", "mm", parent="k0")
    d.note("Traffic", "Dear Mr. Fantasy", "dm", parent="k0")
    for n in range(3):
        d.note(f"Other {n}", f"Fine {n}", f"o{n}", parent="k1")
    monkeypatch.setattr(app.engine, "moderate", lambda *a, **k: {"dm"})
    new = ["mm", "dm", "o0", "o1", "o2"]
    keys = d.base + new
    removed = d.moderate(keys, new, drift_round=True)
    assert removed == {"dm", "mm"}
    assert d.report.has("half or more of what came from Artist 0 - Song 0 went off course, "
                        "so Rolling Stones - Moonlight Mile went too."), d.report.text()


def test_chain_drop_never_empties_the_round(app, monkeypatch):
    d = _drift(app, DRIFT_TRACKS_MODERATOR="strict")
    for n in range(6):   # one seed brought in six, half flagged
        d.note(f"Band {n}", f"Tune {n}", f"t{n}", parent="k0")
    monkeypatch.setattr(app.engine, "moderate", lambda *a, **k: {"t0", "t1", "t2"})
    new = [f"t{n}" for n in range(6)]
    keys = d.base + new
    removed = d.moderate(keys, new, drift_round=True)
    assert removed == {"t0", "t1", "t2"}
    assert all(k in keys for k in ("t3", "t4", "t5"))
    assert "k0" not in d.blocked
    assert d.report.has("would leave this round with nothing, so Band 3 - Tune 3, Band 4 - Tune 4 and "
                        "Band 5 - Tune 5 stay."), d.report.text()


def test_and_list():
    import engine
    assert engine.and_list(["A"]) == "A"
    assert engine.and_list(["A", "B"]) == "A and B"
    assert engine.and_list(["A", "B", "C"]) == "A, B and C"
    assert engine.and_list([]) == ""
