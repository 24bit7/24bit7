"""
24bit7 - Hidden Tracks, scanned rather than guessed (Ben, 13 Nov 2026).

Some albums hide a bonus track after a long silence at the end of their last track. Before 1.37.0 the
hidden-track check left out every album closer longer than a set time, which threw away real songs (System Of A
Down's "Aerials" is 3:55 with its hidden track making 6:11) and every long prog or ambient ending. Now:

  - Scanned: the last track on its album, over MINUTES long (library details only, no setting).
  - The scan: Windows decodes the file read-only through Media Foundation (multiroom.calibrate.decode, no ffmpeg),
    read in chunks, a tenth of a second at a time. A hidden track is either of two gaps with sound after it:
    SILENCE seconds or more below QUIET_DB, anywhere (the usual hidden track: in two hundred of Ben's 1990s album
    closers, all fourteen had twenty seconds to eight minutes of it), or ZERO_GAP seconds or more of true digital
    silence in the second half of the track (Aerials has two and a half, at 63%; the same short gaps earlier on
    were a long piece's movements, Orbital's The Box at 42%, or a two-part track). The cut point is where the
    silence starts. It runs in the background straight after a playlist is sent: the silence always comes after
    the song, and the scan takes seconds. This is Listen for Them; Over Minutes (the old rule) needs no scan.
  - Remembered in the database by file key and length, once ever; a file that changes length is scanned again.
  - Playing: a watcher, only while a marked track plays in a zone 24bit7 sent it to, sends Next at the cut point
    (straight to JRiver, so it never counts as a skip). With Multiroom it acts on the leader, which the Speakers
    follow.
  - Only 24bit7's own playlists: an album, song or playlist asked for by name plays in full (forget_zone).
  - A closer Windows can't decode (DSD, APE, WavPack) or whose file can't be reached is left out, as every long
    closer was before, with a console line saying why (Ben).
  - While 24bit7 is closed nothing sends Next, so the hidden track plays.

Files are never written to: Ben asked about splitting them, and Mags argued against it (13 Nov 2026).
"""

import math
import os
import tempfile
import threading
import time
import wave

import requests

import engine
from i18n import t

MINUTES = 5          # an album closer longer than this is scanned
SILENCE = 10.0       # seconds of near silence, with sound after it, that make a hidden track
QUIET_DB = -60.0     # louder than this is sound
ZERO_GAP = 2.5       # seconds of true digital silence that make one in the second half of a track (Aerials)
ZERO = 1e-4          # a slice whose every sample is below this (about -80 dB) is true silence
SLICE = 0.1          # seconds per loudness reading
UNREADABLE = {"dsf", "dff", "dsd", "ape", "wv"}   # Media Foundation can't decode these
NEAR = 5.0           # seconds before the cut point when the watcher starts asking four times a second
CLOSE_POLL, TRACK_POLL, IDLE_POLL = 0.25, 1.0, 2.0

_lock = threading.Lock()
_watch = {}          # zone id -> set of keys (long closers 24bit7 sent there)
_jumped = {}         # zone id -> the key last moved on from, so Next is sent once
_queue = []          # keys waiting for a scan, with the report to tell
_scanner = None
_watcher = None
decode = None        # the decoder (multiroom.calibrate.decode); the tests put a stand-in here
THREADS = True       # the scans and the watcher on threads of their own; the tests run them by hand


# --- what's known ----------------------------------------------------------------------------------------

def _table():
    con = engine.db()
    con.execute("CREATE TABLE IF NOT EXISTS hidden_tracks (key TEXT PRIMARY KEY, seconds REAL, state TEXT, "
                "cut REAL, why TEXT, checked_at REAL)")
    return con


def known(key):
    """{state: "cut", "none" or "unreadable", cut, why} for a track scanned at its present length, else None."""
    import library
    row = library.track_row(key) or {}
    seconds = _number(row.get("Duration"))
    try:
        got = _table().execute("SELECT seconds, state, cut, why FROM hidden_tracks WHERE key=?", (str(key),)).fetchone()
    except Exception:
        return None
    if not got or (seconds and got[0] and abs(got[0] - seconds) > 1.0):
        return None   # never scanned, or the file has changed since
    return {"state": got[1], "cut": got[2], "why": got[3]}


def _keep(key, seconds, state, cut=None, why=None):
    con = _table()
    con.execute("INSERT OR REPLACE INTO hidden_tracks (key, seconds, state, cut, why, checked_at) VALUES (?,?,?,?,?,?)",
                (str(key), seconds, state, cut, why, time.time()))
    con.commit()


def cut_of(key):
    """Seconds into the track where its hidden track's silence starts, or None."""
    k = known(key)
    return k["cut"] if k and k["state"] == "cut" else None


def is_candidate(key):
    """(seconds, name, artist) for an album closer over MINUTES long, else None."""
    import library
    closer = library.closer_info(key)
    return closer if closer and closer[0] > MINUTES * 60 else None


def leave_out(key):
    """
    Why a long closer is left out (a file that can't be checked), or None: it plays, its hidden track cut off once
    known. Only asked for album closers over MINUTES long.
    """
    k = known(key)
    if k and k["state"] == "unreadable":
        return k["why"] or t("its file couldn't be checked for a hidden track")
    ext = _ext(key)
    if ext in UNREADABLE:
        return t("a {kind} file can't be checked for a hidden track", kind=ext.upper())
    return None


def _ext(key):
    import library
    name = (library.track_row(key) or {}).get("Filename") or ""
    return os.path.splitext(name)[1].lower().lstrip(".")


def _number(text):
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def length(seconds):
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


# --- the scan --------------------------------------------------------------------------------------------

def find_cut(path):
    """
    Where a WAV's hidden track's silence starts, in seconds, or None: the first gap, with sound before it and
    after it, that is SILENCE seconds or more below QUIET_DB, or ZERO_GAP seconds or more of true digital silence
    starting in the second half of the track. Read in chunks, a slice at a time, so a long 24/192 file never sits
    in memory whole.
    """
    import numpy as np
    with wave.open(path, "rb") as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        if w.getcomptype() != "NONE" or width not in (1, 2, 3, 4):
            raise ValueError(f"a {width * 8}-bit {w.getcomptype()} WAV can't be read")
        per = max(1, int(rate * SLICE))
        half = w.getnframes() / rate / 2 if w.getnframes() else None   # no length known: the long gap only
        need = int(round(SILENCE / SLICE))
        need_zero = int(round(ZERO_GAP / SLICE))
        heard, quiet_from, zero_from, zeros, n = False, None, None, 0, 0
        while True:
            raw = w.readframes(per)
            if not raw:
                return None
            x = _samples(np, raw, width, ch)
            rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
            db = 20 * math.log10(rms) if rms > 0 else -200.0
            if db < QUIET_DB:
                if heard and quiet_from is None:
                    quiet_from = n
                if heard and x.size and float(np.max(np.abs(x))) < ZERO:
                    zero_from = n if zero_from is None else zero_from
                    zeros = max(zeros, n + 1 - zero_from)
                else:
                    zero_from = None
            else:
                if quiet_from is not None:
                    if n - quiet_from >= need:
                        return quiet_from * SLICE
                    if zeros >= need_zero and half is not None and quiet_from * SLICE >= half:
                        return quiet_from * SLICE
                heard, quiet_from, zero_from, zeros = True, None, None, 0
            n += 1


def _samples(np, raw, width, ch):
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / 2147483648
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        x = (((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) ^ 0x800000) - 0x800000).astype(np.float64) / 8388608
    else:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128
    return x[:len(x) - len(x) % ch].reshape(-1, ch).mean(axis=1) if ch > 1 else x


def scan(key, report=None):
    """Scans one closer and keeps the answer. Says so when it finds a hidden track or can't check the file."""
    import library
    row = library.track_row(key) or {}
    seconds = _number(row.get("Duration"))
    path = row.get("Filename") or ""
    name, artist = row.get("Name") or "?", row.get("Artist") or "?"
    if not path or not os.path.isfile(path):
        why = t("its file couldn't be reached")
        _keep(key, seconds, "unreadable", why=why)
        _say(report, t("Note: {name} by {artist} will be left out from now on: {why}.", name=name, artist=artist,
                       why=why))
        return None
    out = None
    try:
        dec = decode or _decoder()
        out = dec(path, tempfile.gettempdir())
        cut = find_cut(out)
    except Exception as e:
        why = t("Windows couldn't decode its file")
        engine.debug(f"Hidden Tracks: {name} by {artist}: {e}")
        _keep(key, seconds, "unreadable", why=why)
        _say(report, t("Note: {name} by {artist} will be left out from now on: {why}.", name=name, artist=artist,
                       why=why))
        return None
    finally:
        if out and os.path.abspath(out) != os.path.abspath(path):
            try:
                os.remove(out)   # the decoded copy, never the file itself
            except OSError:
                pass
    _keep(key, seconds, "cut" if cut is not None else "none", cut=cut)
    if cut is not None:
        _say(report, t("{name} by {artist}: plays to {length}, its hidden track left out.", name=name, artist=artist,
                       length=length(cut)))
    return cut


def _decoder():
    from multiroom import calibrate
    return calibrate.decode


def _say(report, line):
    if report is not None:
        try:
            report("  " + line)
        except Exception:
            pass   # a build's report can refuse once it's cancelled; the answer is kept regardless


def scan_later(keys, report=None):
    """Queues closers not scanned yet; one background thread works through them in turn."""
    global _scanner
    with _lock:
        waiting = {k for k, _ in _queue}
        _queue.extend((k, report) for k in keys if k not in waiting)
        if THREADS and (_scanner is None or not _scanner.is_alive()):
            _scanner = threading.Thread(target=_scan_all, daemon=True, name="hidden-tracks")
            _scanner.start()


def run_queue():
    """The scans waiting, here and now (the tests' way in)."""
    _scan_all()


def _scan_all():
    while True:
        with _lock:
            if not _queue:
                return
            key, report = _queue.pop(0)
        if known(key) is None:
            try:
                scan(key, report)
            except Exception as e:
                engine.debug(f"Hidden Tracks: scanning {key} failed ({e})")


# --- what 24bit7 sent, and the watcher -------------------------------------------------------------------

def sent(zone, keys, append=False, report=None, start=True):
    """
    A playlist 24bit7 built went to a zone: its long closers are watched there (append: added to those already
    watched; otherwise they replace them, as the playlist does). Known cuts are said; the rest are scanned.
    """
    closers = [str(k) for k in keys if is_candidate(k)]
    with _lock:
        if append:
            _watch.setdefault(zone, set()).update(closers)
        else:
            _watch[zone] = set(closers)
    todo = []
    for key in closers:
        k = known(key)
        if k is None:
            todo.append(key)
        elif k["state"] == "cut":
            import library
            row = library.track_row(key) or {}
            _say(report, t("{name} by {artist}: plays to {length}, its hidden track left out.",
                           name=row.get("Name") or "?", artist=row.get("Artist") or "?", length=length(k["cut"])))
    if todo:
        scan_later(todo, report)
    if closers and start:
        _start_watcher()


def forget_zone(zone):
    """Something asked for by name replaced the zone's Playing Now: it plays in full, so nothing there is watched."""
    with _lock:
        _watch.pop(zone, None)


def watched(zone):
    with _lock:
        return set(_watch.get(zone, ()))


def _start_watcher():
    global _watcher
    with _lock:
        if THREADS and (_watcher is None or not _watcher.is_alive()):
            _watcher = threading.Thread(target=_watch_loop, daemon=True, name="hidden-watch")
            _watcher.start()


def _watch_loop():
    while True:
        with _lock:
            if not any(_watch.values()):
                return
        try:
            delay = step()
        except Exception as e:
            engine.debug(f"Hidden Tracks: the watcher stumbled ({e})")
            delay = IDLE_POLL
        time.sleep(delay)


def step():
    """
    One look at each zone with a marked track: playing one past its cut point gets Next, sent once. Returns how
    long to wait: a quarter second near a cut point, a second while a marked track plays, two otherwise.
    """
    delay = IDLE_POLL
    for zone in [z for z, keys in list(_watch.items()) if keys]:
        marked = {k: c for k in watched(zone) if (c := cut_of(k)) is not None}
        if not marked:
            continue
        info = engine.get_playing_info(zone)
        if not info:
            continue
        key = str(info.get("FileKey") or "")
        if key not in marked or str(info.get("State")) != "2":
            _jumped.pop(zone, None)
            continue
        pos = _number(info.get("PositionMS")) or 0.0
        left = marked[key] - pos / 1000
        if left <= 0:
            if _jumped.get(zone) != key:
                _jumped[zone] = key
                _next(zone)
            continue
        delay = min(delay, CLOSE_POLL if left <= NEAR else TRACK_POLL)
    return delay


def _next(zone):
    """Next, straight to JRiver: the jump past a hidden track is never counted as a skip."""
    requests.get(f"{engine.JRIVER_BASE}/Playback/Next", params={"Zone": zone}, auth=engine.AUTH, timeout=10)
