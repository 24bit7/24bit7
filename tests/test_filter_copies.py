"""
Issue #10 again (29 Oct 2026): his songs are in his library twice, a stereo MP3 and a surround FLAC of
the same album, and his stereo zone's filter only picks from a smartlist of the MP3s. 24bit7 looked each
AI pick up as one copy, the FLAC, which the filter left out, so nothing played. Where the filters turn
a copy down, your other copies of the song are tried; and a song played recently counts whichever copy
was played.
"""

import json
import time


def _stereo_copies(app, rows):
    """An MP3 copy of each row, on the same album, and a Stereo smartlist holding only those."""
    j = app.jriver
    mp3 = []
    for n, row in enumerate(rows):
        copy = dict(row, Key=str(9100 + n), **{"File Type": "mp3", "Filename": row["Filename"][:-5] + ".mp3"})
        j.tracks.append(copy)
        j.by_key[copy["Key"]] = copy
        mp3.append(copy["Key"])
    j.add_playlist("299", "AutoPlay Stereo", "AutoPlay\\AutoPlay Stereo", "Smartlist", mp3)
    app.library.load()
    return mp3


def _stereo_filter():
    import filters
    f = filters.blank("Stereo")
    f.update(pick_from="299", pick_name="AutoPlay Stereo")
    filters.save(filters.load() + [f])


def _ai_picks(app, rows):
    picks = [{"artist": r["Artist"], "track": r["Name"]} for r in rows]
    app.ai.script.append((json.dumps(picks), "end_turn"))


def _rock(app):
    return [r for r in app.jriver.tracks if r["Genre"] == "Rock"][:3]


def test_the_copy_the_filter_allows_is_used(app):
    app.set_env(DRIFT_VIBE="0")
    rows = _rock(app)
    mp3 = _stereo_copies(app, rows)
    assert app.library.find_track_key(rows[0]["Artist"], rows[0]["Name"]) == rows[0]["Key"], "the FLAC is found first"
    _stereo_filter()
    _ai_picks(app, rows)
    r = app.Lines()
    app.engine.create_vibe_playlist("singer songwriter duos", report=r)
    assert sorted(app.jriver.zone("Speakers").playlist) == sorted(mp3), r.text()
    assert not r.has("left out by your filters"), r.text()


def test_recently_played_counts_any_copy(app):
    """Hearing the MP3 yesterday keeps the FLAC out today too."""
    app.set_env(DRIFT_VIBE="0", SKIP_PLAYED_VIBE="1", SKIP_PLAYED_VIBE_DAYS="2")
    rows = _rock(app)
    mp3 = _stereo_copies(app, rows)
    for key in mp3:
        app.jriver.mark_played(key, time.time() - 600)
    app.library.load()
    _ai_picks(app, rows)
    r = app.Lines()
    app.engine.create_vibe_playlist("singer songwriter duos", report=r)
    assert not app.jriver.zone("Speakers").playlist, r.text()
    assert r.has("Skipped 3 tracks played in the last 2 days"), r.text()


def test_copies_are_the_same_song_only(app):
    j = app.jriver
    row = _rock(app)[0]
    mp3 = _stereo_copies(app, [row])[0]
    live = dict(row, Key="9200", Album="Live at the Fillmore")
    j.tracks.append(live)
    j.by_key[live["Key"]] = live
    app.library.load()
    assert app.library.copies(row["Key"]) == [row["Key"], mp3]
    assert app.library.copies(mp3) == [mp3, row["Key"]]
    assert app.library.copies("9200") == ["9200"], "a live recording isn't a copy of the studio one"
