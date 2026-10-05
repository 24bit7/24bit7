"""
24bit7 - build records, for the console's tabs and its Log (1.11.0).

Every finished build is kept in 24bit7.db with its full console text and the
figures the Log shows: when, who asked (the Main Window, a shortcut, an Alexa
device, or Non-stop), the zone, the Play option, the sources used, tracks queued
and not in library, what the AI Moderator did, and how many Problem and Note
lines it had. A voice command that comes to nothing is kept too.

Each source keeps its last KEEP builds: the Main Window (shortcuts included) and
each Alexa device. A Non-stop top-up files under whoever started the playlist and
joins its chain: the build that started it becomes 001, each top-up the next number.
"""

import re
import threading
from datetime import datetime

import engine

KEEP = 50
MAIN = "main"   # the Main Window's tab key; a device's is its device ID
_lock = threading.Lock()

KINDS = {"similar": "Similar Artists", "youtube_queue": "Similar Artists", "similar_tracks": "Similar Tracks",
         "top_tracks": "Artist's Top Tracks", "vibe": "AI Playlist"}
HEADINGS = ("Similar Artists", "Similar Tracks", "Artist's Top Tracks", "AI Playlist", "Show Credits")
INSTANT = {"songs_by": "Artist's Top Tracks", "music_like": "Similar Artists", "tracks_like": "Similar Tracks",
           "genre": "AI Playlist", "album": "Album", "song": "Song", "playlist": "Playlist",
           "shuffle": "Shuffle Songs by Artist", "skip": "Skip", "who_is_this": "Who Is This",
           "more_like": "More Like This", "switch_zones": "Switch", "stop": "Stop", "pause": "Pause",
           "resume": "Resume", "keep_going": "Keep It Going"}
_TIME = re.compile(r"^\d\d:\d\d  ")


def _table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS builds (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, tab TEXT, from_label TEXT, zone TEXT, zone_id TEXT,
        kind TEXT, sources TEXT, queued INTEGER, misses INTEGER, moderator TEXT,
        problems INTEGER, notes INTEGER, chain_id INTEGER, chain_pos INTEGER, text TEXT)""")


def _bodies(text):
    return [_TIME.sub("", line.strip()) for line in text.splitlines()]


def _kind_from_text(text):
    for body in _bodies(text):
        for heading in HEADINGS:
            if body.startswith(heading + ":"):
                return heading
    return ""


def _moderator(text):
    """'Balanced, 3 removed' from the AI Moderator's lines, Drift rounds included; '' if it didn't run."""
    level = re.search(r"AI Moderator \((\w+)\): checking", text)
    if not level:
        return ""
    removed = sum(int(n) for n in re.findall(r"AI Moderator: (\d+) removed", text))
    return f"{level.group(1)}, {removed} removed"


def _count(text, word):
    return sum(1 for body in _bodies(text) if body.startswith(word))


def device_name(device_id):
    if device_id == "24bit7-settings-test":
        return "Voice Test"
    try:
        row = engine.db().execute("SELECT name FROM voice_devices WHERE device_id=?", (device_id,)).fetchone()
        return row[0] if row and row[0] else "Unknown Device"
    except Exception:
        return "Unknown Device"


def _insert(con, row):
    con.execute("INSERT INTO builds (at, tab, from_label, zone, zone_id, kind, sources, queued, misses, moderator, "
                "problems, notes, chain_id, chain_pos, text) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["at"], row["tab"], row["from_label"], row["zone"], row["zone_id"], row["kind"],
                 row["sources"], row["queued"], row["misses"], row["moderator"], row["problems"],
                 row["notes"], row["chain_id"], row["chain_pos"], row["text"]))
    rid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.execute("DELETE FROM builds WHERE tab=? AND id NOT IN "
                "(SELECT id FROM builds WHERE tab=? ORDER BY id DESC LIMIT ?)", (row["tab"], row["tab"], KEEP))
    con.commit()
    return rid


def record_job(origin, text):
    """
    Keeps a finished build. origin says who asked: None for the Main Window, or
    {"from": "voice", "device": id}, {"from": "shortcut"}, {"from": "nonstop", "zone": id}.
    Reads what engine noted about the build (LAST_BUILD, LAST_OUTPUT, LAST_OUTPUT_ID).
    """
    if not text.strip():
        return None
    origin = origin or {}
    built = engine.LAST_BUILD or {}
    zone_id = str(engine.LAST_OUTPUT_ID or origin.get("zone") or "")
    row = {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "tab": MAIN, "from_label": "Main Window",
           "zone": engine.LAST_OUTPUT or "", "zone_id": zone_id,
           "kind": KINDS.get(built.get("mode")) or _kind_from_text(text),
           "sources": (built.get("sources") or "").replace(" + ", ", "),
           "queued": built.get("queued"), "misses": built.get("misses"),
           "moderator": _moderator(text), "problems": _count(text, "Problem:"), "notes": _count(text, "Note:"),
           "chain_id": None, "chain_pos": None, "text": text}
    if row["zone"] == "YouTube":
        row["misses"] = None   # nothing is checked against the library
    kind = origin.get("from")
    with _lock:
        con = engine.db()
        _table(con)
        if kind == "voice":
            row["tab"] = origin.get("device") or "unknown device"
            row["from_label"] = device_name(row["tab"])
        elif kind == "shortcut":
            row["from_label"] = "Shortcut"
        elif kind == "nonstop":
            row["from_label"] = "Non-stop"
            prev = con.execute("SELECT id, tab, chain_id, chain_pos FROM builds WHERE zone_id=? "
                               "ORDER BY id DESC LIMIT 1", (zone_id,)).fetchone() if zone_id else None
            if prev:
                pid, tab, chain_id, chain_pos = prev
                if chain_pos is None:   # the playlist's first build only gets its number now
                    con.execute("UPDATE builds SET chain_id=?, chain_pos=1 WHERE id=?", (pid, pid))
                    chain_id, chain_pos = pid, 1
                row.update(tab=tab, chain_id=chain_id, chain_pos=chain_pos + 1)
        return _insert(con, row)


def record_instant(device_id, intent, text, zone=""):
    """A voice command that came to nothing: kept under its device, as one problem."""
    with _lock:
        con = engine.db()
        _table(con)
        return _insert(con, {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "tab": device_id or "unknown device",
                             "from_label": device_name(device_id), "zone": zone, "zone_id": "",
                             "kind": INSTANT.get(intent, "Voice Command"), "sources": "", "queued": None,
                             "misses": None, "moderator": "", "problems": max(1, _count(text, "Problem:")),
                             "notes": _count(text, "Note:"), "chain_id": None, "chain_pos": None, "text": text})


def recent(tab=None, limit=None):
    """Builds newest first, as dicts: all of them, or one tab's."""
    with _lock:
        con = engine.db()
        _table(con)
        sql = ("SELECT id, at, tab, from_label, zone, zone_id, kind, sources, queued, misses, moderator, "
               "problems, notes, chain_id, chain_pos, text FROM builds")
        args = []
        if tab is not None:
            sql += " WHERE tab=?"
            args.append(tab)
        sql += " ORDER BY id DESC"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        cols = ["id", "at", "tab", "from_label", "zone", "zone_id", "kind", "sources", "queued", "misses",
                "moderator", "problems", "notes", "chain_id", "chain_pos", "text"]
        return [dict(zip(cols, r)) for r in con.execute(sql, args).fetchall()]


def tabs():
    """[(tab, label)] for the devices with builds kept, by name. The Main Window isn't included."""
    with _lock:
        con = engine.db()
        _table(con)
        keys = [r[0] for r in con.execute("SELECT DISTINCT tab FROM builds WHERE tab != ?", (MAIN,)).fetchall()]
    return sorted(((k, device_name(k)) for k in keys), key=lambda x: x[1].lower())


def tab_for_zone(zone_id):
    """The tab a Non-stop top-up on this zone files under: whoever started the playlist."""
    if not zone_id:
        return MAIN
    with _lock:
        con = engine.db()
        _table(con)
        row = con.execute("SELECT tab FROM builds WHERE zone_id=? ORDER BY id DESC LIMIT 1",
                          (str(zone_id),)).fetchone()
    return row[0] if row else MAIN


def playlist_type(row):
    """'Similar Tracks', or 'Similar Tracks · Non-stop 003' for a build in a chain."""
    kind = row.get("kind") or ""
    if row.get("chain_pos"):
        return f"{kind} · Non-stop {row['chain_pos']:03d}"
    return kind
