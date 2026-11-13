"""
Hidden Tracks, scanned rather than guessed (sprint for 1.37.0, Ben 13 Nov 2026): an album closer over five minutes
is scanned for ten seconds or more of near silence with sound after it; the cut point is remembered by file key and
length; a watcher sends Next there, straight to JRiver, so it never counts as a skip; a closer that can't be checked
(DSD, APE, WavPack, or a file that can't be reached) is left out as before, with a line saying why. Files are never
written to. The fake world runs no threads: the scans and the watcher are run by hand here (conftest).
"""

import math
import os
import struct
import wave

import pytest


def _wav(path, parts, rate=8000, width=2):
    """parts: (seconds, loud) pairs, a 440 Hz tone, digital silence (False) or a hiss near -70 dB ("hiss": quiet
    but never true silence, like a room or tape between songs), mono."""
    frames = bytearray()
    for seconds, loud in parts:
        for i in range(int(seconds * rate)):
            if loud == "hiss":
                v = 0.0004 * (1 if (i * 7919) % 13 < 6 else -1)
            else:
                v = 0.5 * math.sin(2 * math.pi * 440 * i / rate) if loud else 0.0
            if width == 2:
                frames += struct.pack("<h", int(v * 32767))
            else:
                n = int(v * 8388607) & 0xFFFFFF
                frames += bytes((n & 0xFF, (n >> 8) & 0xFF, n >> 16))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return str(path)


@pytest.fixture
def hidden(app):
    import hidden
    import library
    library.ensure_loaded()   # a build has always read the library by the time it sends a playlist
    hidden._queue.clear()
    hidden._watch.clear()
    hidden._jumped.clear()
    return hidden


def _echoes(app):
    return app.jriver.key_of("Pink Floyd", "Echoes")


# --- the scan --------------------------------------------------------------------------------------------

def test_the_cut_point_is_where_ten_seconds_of_silence_before_more_sound_starts(app, hidden, tmp_path):
    path = _wav(tmp_path / "a.wav", [(3, True), (12, False), (2, True)])
    assert hidden.find_cut(path) == pytest.approx(3.0, abs=0.5)


def test_a_24_bit_file_reads_the_same(app, hidden, tmp_path):
    path = _wav(tmp_path / "a.wav", [(3, True), (12, False), (2, True)], width=3)
    assert hidden.find_cut(path) == pytest.approx(3.0, abs=0.5)


def test_silence_at_the_very_end_or_a_short_pause_is_no_hidden_track(app, hidden, tmp_path):
    assert hidden.find_cut(_wav(tmp_path / "end.wav", [(3, True), (15, False)])) is None
    assert hidden.find_cut(_wav(tmp_path / "pause.wav", [(3, True), (6, False), (3, True)])) is None
    assert hidden.find_cut(_wav(tmp_path / "intro.wav", [(12, False), (3, True)])) is None, "silence before any sound"


def test_a_short_true_silence_in_the_second_half_is_a_hidden_track_as_aerials_has(app, hidden, tmp_path):
    """Ben's Aerials: the song ends at 3:53, two and a half seconds of digital silence, then the hidden track.
    Scaled down: twenty seconds of song, 2.6 of silence, ten of hidden track."""
    path = _wav(tmp_path / "a.wav", [(20, True), (2.6, False), (10, True)])
    assert hidden.find_cut(path) == pytest.approx(20.0, abs=0.2)


def test_the_same_short_silence_in_the_first_half_is_a_movement_not_a_hidden_track(app, hidden, tmp_path):
    """Orbital's The Box (a short silence at 42% of 28 minutes) and a two-part track at 27% played in full."""
    assert hidden.find_cut(_wav(tmp_path / "a.wav", [(8, True), (2.6, False), (20, True)])) is None


def test_a_short_quiet_spell_that_isnt_true_silence_is_part_of_the_song(app, hidden, tmp_path):
    """A build-up or a room tone near -70 dB, however late, is not a gap before a hidden track."""
    assert hidden.find_cut(_wav(tmp_path / "a.wav", [(20, True), (4, "hiss"), (10, True)])) is None
    assert hidden.find_cut(_wav(tmp_path / "b.wav", [(3, True), (12, "hiss"), (2, True)])) == pytest.approx(3.0, abs=0.2),         "ten seconds of quiet is still a hidden track, silent or not"


def test_a_short_true_silence_shorter_than_two_and_a_half_seconds_is_a_pause(app, hidden, tmp_path):
    assert hidden.find_cut(_wav(tmp_path / "a.wav", [(20, True), (1.5, False), (10, True)])) is None


def test_a_scan_keeps_its_answer_says_where_it_plays_to_and_deletes_only_the_decoded_copy(app, hidden, tmp_path,
                                                                                         monkeypatch):
    key = _echoes(app)
    original = app.jriver.by_key[key]["Filename"]
    decoded = []

    def decode(path, folder):
        assert path == original
        decoded.append(_wav(tmp_path / "decoded.wav", [(4, True), (11, False), (2, True)]))
        return decoded[-1]
    monkeypatch.setattr(hidden, "decode", decode)
    monkeypatch.setattr(hidden.os.path, "isfile", lambda p: p == original)
    removed = []
    real_remove = os.remove
    monkeypatch.setattr(hidden.os, "remove", lambda p: (removed.append(p), real_remove(p)))
    r = app.Lines()
    assert hidden.scan(key, r) == pytest.approx(4.0, abs=0.5)
    assert removed == decoded, "the decoded copy goes; the file itself is never touched"
    assert hidden.cut_of(key) == pytest.approx(4.0, abs=0.5)
    assert "Echoes by Pink Floyd: plays to 0:04, its hidden track left out." in r.text()
    assert hidden.leave_out(key) is None, "a closer with a hidden track plays, cut short"


def test_a_closer_with_no_hidden_track_is_remembered_and_plays_in_full(app, hidden, tmp_path, monkeypatch):
    key = _echoes(app)
    monkeypatch.setattr(hidden, "decode", lambda p, f: _wav(tmp_path / "d.wav", [(5, True)]))
    monkeypatch.setattr(hidden.os.path, "isfile", lambda p: True)
    assert hidden.scan(key) is None
    assert hidden.known(key)["state"] == "none" and hidden.cut_of(key) is None and hidden.leave_out(key) is None


def test_a_file_that_cant_be_reached_is_left_out_from_then_on_with_a_reason(app, hidden):
    key = _echoes(app)
    r = app.Lines()
    hidden.scan(key, r)
    assert "Note: Echoes by Pink Floyd will be left out from now on: its file couldn't be reached." in r.text()
    assert hidden.leave_out(key) == "its file couldn't be reached"


def test_a_file_windows_cant_decode_is_left_out_with_a_reason(app, hidden, monkeypatch):
    key = _echoes(app)
    monkeypatch.setattr(hidden.os.path, "isfile", lambda p: True)

    def refuse(path, folder):
        raise RuntimeError("no decoder")
    monkeypatch.setattr(hidden, "decode", refuse)
    hidden.scan(key)
    assert hidden.leave_out(key) == "Windows couldn't decode its file"


def test_dsd_ape_and_wavpack_are_left_out_without_a_scan(app, hidden, monkeypatch):
    import library
    key = _echoes(app)
    row = dict(library.track_row(key), Filename="F:\\Music\\Pink Floyd\\Meddle\\06 Echoes.dsf")
    monkeypatch.setattr(library, "track_row", lambda k: row if str(k) == str(key) else None)
    assert hidden.leave_out(key) == "a DSF file can't be checked for a hidden track"


def test_a_file_that_changes_length_is_scanned_again(app, hidden):
    key = _echoes(app)
    seconds = float(app.jriver.by_key[key]["Duration"])
    hidden._keep(key, seconds, "cut", cut=600.0)
    assert hidden.cut_of(key) == 600.0
    hidden._keep(key, seconds + 30, "cut", cut=600.0)
    assert hidden.known(key) is None, "a new rip or edit of the file: what was found no longer holds"


def test_only_album_closers_over_five_minutes_are_candidates(app, hidden):
    assert hidden.is_candidate(_echoes(app)), "Echoes, 23:31, last on Meddle"
    assert not hidden.is_candidate(app.jriver.key_of("Pink Floyd", "Fearless")), "not the last on its album"


# --- what 24bit7 sent, and the watcher -------------------------------------------------------------------

def _playing(app, zone, keys, at, key):
    z = app.jriver.zone(zone)
    z.playlist, z.pos, z.state, z.position_ms = list(keys), keys.index(key), 2, int(at * 1000)


def test_the_watcher_sends_next_once_at_the_cut_point_and_it_isnt_a_skip(app, hidden):
    key = _echoes(app)
    other = app.jriver.key_of("Pink Floyd", "Fearless")
    zid = app.engine.zone_id("Kitchen")
    hidden._keep(key, float(app.jriver.by_key[key]["Duration"]), "cut", cut=600.0)
    r = app.Lines()
    hidden.sent(zid, [other, key], report=r)
    assert "Echoes by Pink Floyd: plays to 10:00, its hidden track left out." in r.text()
    assert hidden.watched(zid) == {str(key)}
    _playing(app, "Kitchen", [other, key], 500, key)
    assert hidden.step() == hidden.TRACK_POLL and not app.jriver.calls_to("Playback/Next")
    app.jriver.zone("Kitchen").position_ms = 597000
    assert hidden.step() == hidden.CLOSE_POLL, "near the cut it asks four times a second"
    app.jriver.zone("Kitchen").position_ms = 600200
    hidden.step()
    hidden.step()
    assert len(app.jriver.calls_to("Playback/Next")) == 1, "Next once, not every look"


def test_a_closer_not_scanned_yet_is_queued_and_found_by_the_time_it_plays(app, hidden, tmp_path, monkeypatch):
    key = _echoes(app)
    monkeypatch.setattr(hidden, "decode", lambda p, f: _wav(tmp_path / "d.wav", [(4, True), (11, False), (2, True)]))
    monkeypatch.setattr(hidden.os.path, "isfile", lambda p: True)
    r = app.Lines()
    hidden.sent(app.engine.zone_id("Kitchen"), [key], report=r)
    assert [k for k, _ in hidden._queue] == [str(key)]
    hidden.run_queue()
    assert hidden.cut_of(key) is not None and "plays to 0:04" in r.text()


def test_something_asked_for_by_name_plays_in_full(app, hidden):
    import voice
    key = _echoes(app)
    zid = app.engine.zone_id("Kitchen")
    hidden._keep(key, float(app.jriver.by_key[key]["Duration"]), "cut", cut=600.0)
    hidden.sent(zid, [key])
    assert hidden.watched(zid)
    voice._play_keys([key], zid)
    assert not hidden.watched(zid), "an album asked for by name plays in full, hidden track and all"


def test_a_build_sends_its_long_closers_to_the_watcher(app, hidden):
    app.set_env(SKIP_LONG_CLOSERS="1")
    key = _echoes(app)
    r = app.Lines()
    app.engine.send_to_jriver([key, app.jriver.key_of("Pink Floyd", "Fearless")], report=r, zone_name="Kitchen")
    assert hidden.watched(app.engine.zone_id("Kitchen")) == {str(key)}
    assert "Pink Floyd - Echoes" in app.jriver.titles("Kitchen"), "scanned, not guessed: the song plays"


def test_a_build_leaves_out_a_closer_that_cant_be_checked_and_says_why(app, hidden):
    app.set_env(SKIP_LONG_CLOSERS="1")
    key = _echoes(app)
    hidden._keep(key, float(app.jriver.by_key[key]["Duration"]), "unreadable", why="its file couldn't be reached")
    r = app.Lines()
    kept = app.engine.drop_long_closers([key], report=r, group="top")
    assert kept == []
    assert "Skipped Echoes by Pink Floyd: last on its album, and its file couldn't be reached." in r.text()


def test_the_old_tick_reads_as_listen_for_them_or_off_and_minutes_is_its_own(app, hidden):
    get = {"SKIP_LONG_CLOSERS_TOP": "1", "SKIP_LONG_CLOSERS_ARTISTS": "0", "SKIP_LONG_CLOSERS_TRACKS": "minutes",
           "LONG_CLOSER_MINUTES_TRACKS": "8"}.get
    cfg = app.engine.closer_settings(lambda k, d="": get(k, d))
    assert cfg["top"][0] == "listen" and cfg["artists"][0] == "off" and cfg["tracks"] == ("minutes", 8)
    assert cfg["vibe"][0] == "listen", "a new install, and anyone with the old tick on, listens for them"
    assert [app.engine.closer_stored(m) for m in ("listen", "off", "minutes")] == ["1", "0", "minutes"]


def test_over_minutes_leaves_out_every_long_closer_unscanned_as_before(app, hidden):
    app.set_env(SKIP_LONG_CLOSERS_TOP="minutes", LONG_CLOSER_MINUTES_TOP="6")
    key = _echoes(app)
    r = app.Lines()
    assert app.engine.drop_long_closers([key], report=r, group="top") == []
    assert "Skipped Echoes by Pink Floyd: last on its album, and over 6 minutes long." in r.text()
    assert not app.engine.listening("top")
    app.engine.send_to_jriver([app.jriver.key_of("Pink Floyd", "Fearless")], report=r, zone_name="Kitchen")
    assert not hidden.watched(app.engine.zone_id("Kitchen")) and not hidden._queue, "nothing scanned or watched"


def test_hidden_tracks_off_leaves_closers_alone(app, hidden):
    app.set_env(SKIP_LONG_CLOSERS="0", SKIP_LONG_CLOSERS_TOP="0")
    key = _echoes(app)
    hidden._keep(key, float(app.jriver.by_key[key]["Duration"]), "unreadable", why="x")
    assert app.engine.drop_long_closers([key], report=app.Lines(), group="top") == [key]
