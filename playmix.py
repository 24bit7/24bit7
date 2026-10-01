"""
24bit7 - JRiver playlists joined to a build from the Play tab (Add playlist).

Each row is a JRiver playlist or smartlist and how it joins 24bit7's tracks:
  before   its tracks first, in the playlist's own order
  after    its tracks last, in its own order
  mix      spread through 24bit7's tracks: evenly ("even", so both finish
           together) or at random ("random")
Rows play in the order they're listed. They're kept in the meta table between
runs. Use counts, kept by JRiver playlist ID so a rename keeps its count, put the
most used playlists at the top of the picker. App builds only: voice doesn't use them.
"""

import json
import time

import engine

META_KEY = "play_mix"
MODES = {"mix": "Mix", "before": "Add before", "after": "Add after"}
SPREADS = {"even": "Spaced evenly", "random": "Mixed randomly"}


def _blank():
    return {"rows": [], "counts": {}, "last_used": {}, "open": False}


def load():
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
        data = json.loads(row[0]) if row and row[0] else {}
    except Exception:
        data = {}
    out = _blank()
    if isinstance(data, dict):
        out.update({k: v for k, v in data.items() if k in out})
    return out


def _save(data):
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (META_KEY, json.dumps(data)))
    con.commit()


def _clean(row):
    mode = row.get("mode") if row.get("mode") in MODES else "after"
    spread = row.get("spread") if row.get("spread") in SPREADS else "even"
    return {"id": str(row.get("id") or ""), "name": str(row.get("name") or ""), "mode": mode, "spread": spread}


def rows():
    """The Play tab's rows, in order, as last left."""
    return [_clean(r) for r in load()["rows"] if isinstance(r, dict) and r.get("id")]


def set_rows(new_rows):
    data = load()
    data["rows"] = [_clean(r) for r in new_rows if r.get("id")]
    _save(data)


def is_open():
    """Whether the Play tab's More options row was left open."""
    return bool(load().get("open"))


def set_open(value):
    data = load()
    data["open"] = bool(value)
    _save(data)


def record_use(ids):
    """Counts one use of each playlist in a build that used them."""
    data = load()
    now = int(time.time())
    for pid in {str(i) for i in ids if i}:
        data["counts"][pid] = int(data["counts"].get(pid, 0)) + 1
        data["last_used"][pid] = now
    _save(data)


def picker_order(playlists, text=""):
    """
    ([(playlist, count)], [playlist]) matching text: used ones, most used first
    (the more recently used first on a tie), then the rest A to Z.
    """
    data = load()
    counts, last = data["counts"], data["last_used"]
    wanted = (text or "").casefold().strip()
    matches = [p for p in playlists if wanted in str(p.get("Name", "")).casefold()]
    used = sorted((p for p in matches if counts.get(p["ID"])),
                  key=lambda p: (-int(counts[p["ID"]]), -int(last.get(p["ID"], 0))))
    rest = sorted((p for p in matches if not counts.get(p["ID"])), key=lambda p: str(p["Name"]).casefold())
    return [(p, int(counts[p["ID"]])) for p in used], rest


def summary(current):
    """One line saying what the next build will do with these rows, or "" with none."""
    current = [r for r in current if r.get("id")]
    if not current:
        return ""
    parts = [r["name"] for r in current if r["mode"] == "before"]
    mixed = [f"{r['name']} ({SPREADS[r['spread']].lower()})" for r in current if r["mode"] == "mix"]
    middle = "24bit7's tracks"
    if mixed:
        middle += " mixed with " + (mixed[0] if len(mixed) == 1 else ", ".join(mixed[:-1]) + " and " + mixed[-1])
    parts.append(middle)
    parts += [r["name"] for r in current if r["mode"] == "after"]
    return "Next build: " + ", then ".join(parts) + "."
