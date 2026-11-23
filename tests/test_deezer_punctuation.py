"""
Deezer and punctuation (Ben, 23 Nov 2026). Deezer files the real P.O.D. as "P.O.D" (515,931 fans) and an empty
namesake as "P.O.D." (eight fans). An exact match kept only the namesake, so Deezer gave P.O.D. nothing. Names
are compared with punctuation set aside now, and the fan count picks the band. Nothing here opens a window.
"""

POD_HITS = [{"id": 78073282, "name": "P.O.D.", "nb_fan": 8},
            {"id": 59911, "name": "M.O.D.", "nb_fan": 1892},
            {"id": 1443214, "name": "P.O.D", "nb_fan": 515931},
            {"id": 2543, "name": "M.O.P.", "nb_fan": 146403}]


class _Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return {"data": self._data}


def _search(monkeypatch, engine, hits):
    monkeypatch.setattr(engine.requests, "get", lambda url, params=None, **k: _Resp(hits))
    engine._deezer_id_cache.clear()


def test_deezer_finds_the_band_whatever_the_full_stops(app, monkeypatch):
    e = app.engine
    _search(monkeypatch, e, POD_HITS)
    assert e.deezer_artist_id("P.O.D.") == 1443214, "the band, not the eight-fan namesake"
    e._deezer_id_cache.clear()
    assert e.deezer_artist_id("POD") == 1443214
    _search(monkeypatch, e, [{"id": 1, "name": "M.O.P.", "nb_fan": 146403}, {"id": 2, "name": "Mop", "nb_fan": 3}])
    assert e.deezer_artist_id("Mop") in (1, 2), "punctuation aside both match; the fan count decides"


def test_a_name_of_only_punctuation_still_matches_itself(app):
    e = app.engine
    assert e._loose_name("!!!") == "!!!" and e._loose_name("!!!") != e._loose_name("???")
    assert e._loose_name("AC/DC") == e._loose_name("ACDC") == "acdc"
    assert e._loose_name("Sigur Rós") == e._loose_name("sigur ros")
