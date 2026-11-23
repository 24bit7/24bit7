"""
Discover's Seed for Radio (Ben, 23 Nov 2026): the session is "Radio: Classic Rock / Rock", but each row's Seed is
the pillar that led to it. A pillar's own song has that pillar; an agreeing artist has the first pillar whose
similar-artist list named it ("Just the first"). Missing Artists counts a Radio miss under that pillar, and
Review's Found By says who it was like. Nothing here opens a window.
"""

from test_radio import EVERYONE, play_counts
from test_radio_playlist import made_radio, radio  # noqa: F401  (the radio fixture)


def _seeds(app):
    con = app.engine.db()
    sid = con.execute("SELECT id FROM sessions WHERE mode='radio' ORDER BY id DESC LIMIT 1").fetchone()[0]
    return con.execute("SELECT artist, seed FROM discoveries WHERE session_id=?", (sid,)).fetchall()


def test_each_radio_row_names_the_pillar_that_led_to_it(app, radio):
    play_counts(app, EVERYONE)
    radio.analyse(app.Lines())
    buttons, b = made_radio(app)
    r = app.Lines()
    buttons.run(buttons.get(b["id"]), report=r)
    pillars = [x[len("  Pillar: "):-3] for x in r if x.startswith("  Pillar: ")]
    rows = _seeds(app)
    assert rows and all(seed for _a, seed in rows), "every row has a seed"
    assert all(seed in pillars for _a, seed in rows), (rows, pillars)
    own = [(a, s) for a, s in rows if a in pillars]
    others = [(a, s) for a, s in rows if a not in pillars]
    assert own and all(a == s for a, s in own), "a pillar's own song has the pillar itself"
    assert others and all(a != s for a, s in others), "an agreeing artist has the pillar that named it"
    assert "," not in "".join(s for _a, s in others), "just the first pillar"


def test_missing_artists_and_found_by_read_the_pillar(app):
    import discover_stats
    assert discover_stats.seed_artist("radio", "", "Led Zeppelin") == "Led Zeppelin"
    assert discover_stats.seed_artist("radio", "", None) == "", "older rows had no seed"
    why = app.engine._why
    assert why("Last.fm", "Led Zeppelin", "Foghat", ("", "Classic Rock / Rock"), "radio")[1] \
        == "Last.fm named Foghat as like Led Zeppelin."
    assert why("Last.fm", "Queen", "Queen", ("", "Classic Rock / Rock"), "radio")[1] \
        == "One of Queen's top tracks on Last.fm.", "a pillar's own song"
