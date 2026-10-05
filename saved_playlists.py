"""
24bit7 - saved playlists.

How your own JRiver playlists and smartlists play when you ask for one by voice
("playlist dinner party"), set under Settings > JRiver Playlists:

  Shuffle      tracks shuffled before they're sent (JRiver's shuffle mode is left alone)
  Non-stop     No / Similar artists / Similar tracks: when the last track starts, more are added
  Reseed from  Last track / 2nd track, for non-stop
  Skip         leave out tracks played in the last n days (never leaving the playlist empty)

Either global rows ("Use global playlist settings"), one for every playlist
and one for every smartlist, or a row each. Windows (Main) is kept in the database's meta table; a device
with Own settings can have its own copy (voice_devices.saved). Playlists you
start in JRiver itself aren't touched: 24bit7 never sees them start.
"""

import json
import random
import xml.etree.ElementTree as ET

import requests

import engine

DEFAULT_ROW = {"shuffle": "0", "blend": "no", "nonstop": "no", "reseed": "last", "skip": "0"}   # new playlists: as saved
SEND_CHUNK = 400   # keys per JRiver call, so a long playlist doesn't make an over-long address
META_KEY = "saved_playlists"


ROOT = "Root"   # the folder name shown for playlists at the top level


def blank():
    return {"all": "0", "all_row": dict(DEFAULT_ROW), "all_row_smart": dict(DEFAULT_ROW), "rows": {},
            "sort": "az", "sort_by": "folder"}


def tidy(data):
    """Fills in anything missing, so older or partial settings always read cleanly."""
    out = blank()
    if isinstance(data, dict):
        out.update({k: v for k, v in data.items() if k in out})
    out["all_row"] = {**DEFAULT_ROW, **(out.get("all_row") or {})}
    # The smartlist row: older settings start it as a copy of the playlist row, Shuffle from shuffle_smart
    old_smart = out["all_row"].pop("shuffle_smart", None)
    if not (isinstance(data, dict) and data.get("all_row_smart")):
        out["all_row_smart"] = dict(out["all_row"], shuffle=old_smart or out["all_row"]["shuffle"])
    out["all_row_smart"] = {**DEFAULT_ROW, **(out.get("all_row_smart") or {})}
    out["rows"] = {str(pid): {**DEFAULT_ROW, **(row or {})} for pid, row in (out.get("rows") or {}).items()}
    for row in [out["all_row"], out["all_row_smart"], *out["rows"].values()]:   # Blend was a tick at first
        row["blend"] = {"1": "tracks", "0": "no"}.get(str(row.get("blend")), row.get("blend"))
        if row["blend"] not in ("no", "artists", "tracks"):
            row["blend"] = "no"
    return out


def main_settings():
    """Windows (Main)'s Saved Playlists settings."""
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
        return tidy(json.loads(row[0]) if row and row[0] else None)
    except Exception:
        return blank()


def set_main_settings(data):
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (META_KEY, json.dumps(tidy(data))))
    con.commit()


def settings_for(device_id=None):
    """A device's own settings if it has Own settings ticked and its own copy, else Windows (Main)'s."""
    if device_id:
        try:
            import voice
            own = voice.device_page(device_id, "saved") if any(
                d[0] == device_id and d[4] for d in voice.devices()) else None
            if own is not None:
                return tidy(own)
        except Exception:
            pass
    return main_settings()


def row_for(data, playlist_id, kind=None):
    """The settings one playlist plays with: the shared row, or its own (new playlists get the defaults).
    kind is "Playlist" or "Smartlist": with global settings on, each type has its own row."""
    if str(data.get("all", "0")) == "1":
        return dict(data["all_row_smart"] if kind == "Smartlist" else data["all_row"])
    return dict(data["rows"].get(str(playlist_id)) or DEFAULT_ROW)


def folder_of(playlist):
    """The folder a playlist sits in, from JRiver's Path ('Random Album\\1001 Albums' -> 'Random Album')."""
    # JRiver separates folders with a backslash only; a "/" is part of a name ("Rock/Pop (90's)")
    path, name = str(playlist.get("Path") or "").strip("\\"), str(playlist.get("Name") or "")
    if name and path.endswith("\\" + name):
        path = path[:-len(name) - 1]
    elif "\\" in path:
        path = path.rsplit("\\", 1)[0]
    else:
        return ROOT
    parts = [x for x in path.split("\\") if x]
    return " > ".join(parts) if parts else ROOT


def type_of(playlist):
    return "Smartlist" if str(playlist.get("Type") or "").lower() == "smartlist" else "Playlist"


def scan():
    """[{"ID", "Name", "Folder", "Type"}] for every playlist and smartlist in JRiver. Raises if JRiver can't be reached."""
    import library
    return [{"ID": str(p.get("ID")), "Name": p.get("Name") or "", "Folder": folder_of(p), "Type": type_of(p)}
            for p in library._read_playlists() if p.get("ID")]


def merge_scan(data, found):
    """Adds new playlists (with the defaults), drops deleted ones, and keeps names, folders and types current."""
    data = tidy(data)
    rows = {}
    for p in found:
        row = data["rows"].get(p["ID"]) or dict(DEFAULT_ROW)
        row.update(name=p["Name"], folder=p.get("Folder") or ROOT, type=p.get("Type") or "Playlist")
        rows[p["ID"]] = row
    data["rows"] = rows
    return data


def find(heard, _split=True):
    """
    The playlist meant by what was heard, like library.find_album:
      (True, [playlist])          one
      (False, [playlist, ...])    several share the name; ask which
      (False, [])                 nothing close enough
    'vocal jazz by smartlist', 'vocal jazz by playlist' or 'vocal jazz by random album'
    answers the question; 'vocal jazz smartlist' picks the type up front.
    """
    import library
    original, heard, by, want = heard, heard.strip(), None, None
    if _split and " by " in heard:
        heard, by = (part.strip() for part in heard.rsplit(" by ", 1))
    low = heard.lower()
    for word, kind in ((" smart list", "Smartlist"), (" smartlist", "Smartlist"), (" playlist", "Playlist")):
        if low.endswith(word):
            heard, want = heard[:-len(word)].strip(), kind
            break
    library.ensure_loaded()
    with library._lock:
        lists = list(library._playlists)
    ranked = sorted(((library.score(heard, p.get("Name", "")), p) for p in lists), key=lambda x: -x[0])
    if not ranked or ranked[0][0] < library.GOOD:
        return find(original, _split=False) if by else (False, [])   # 'Stand by Me' is a name, not an answer
    name = library.norm(ranked[0][1].get("Name", ""))
    same = [p for s, p in ranked if s >= library.GOOD and library.norm(p.get("Name", "")) == name]
    if by:
        b = by.lower()
        if b.startswith("smart"):
            want = "Smartlist"
        elif b in ("playlist", "the playlist", "a playlist", "normal playlist"):
            want = "Playlist"
        else:   # a folder
            spoken_root = ("top level", "the top level", "root")
            scored = [((1.0 if b in spoken_root and folder_of(p) == ROOT else library.score(by, folder_of(p))), p)
                      for p in same]
            best = max((s for s, _ in scored), default=0)
            if best >= library.GOOD:
                same = [p for s, p in scored if s == best]
    if want:
        same = [p for p in same if type_of(p) == want] or same
    return (len(same) == 1), same


def ask_which(matches):
    """What Alexa asks when several playlists share a name."""
    title = matches[0].get("Name") or "that"

    def where(p):
        folder = folder_of(p)
        return "at the top level" if folder == ROOT else f"in {folder.replace(' > ', ', ')}"
    types = [type_of(p) for p in matches]
    if len(matches) == 2 and len(set(types)) == 2:
        smart, plain = (matches if types[0] == "Smartlist" else matches[::-1])
        return (f"You have two called {title}: the smartlist {where(smart)}, and the playlist {where(plain)}. "
                f"Say by smartlist, or by playlist.")
    places = [where(p) for p in matches]
    listed = places[0] if len(places) == 1 else ", ".join(places[:-1]) + " or " + places[-1]
    return f"You have {len(matches)} called {title}, {listed}. Say by, then the folder."


def playlist_keys(playlist_id):
    """The file keys of a playlist or smartlist, in its order."""
    r = requests.get(f"{engine.JRIVER_BASE}/Playlist/Files",
                     params={"Playlist": playlist_id, "PlaylistType": "ID", "Fields": "Key"},
                     auth=engine.AUTH, timeout=30)
    keys = []
    for item in ET.fromstring(r.text).findall(".//Item"):
        for field in item.findall("Field"):
            if field.get("Name") == "Key" and field.text:
                keys.append(field.text.strip())
    return keys


def _send(keys, zone):
    """Replaces Playing Now with keys, in chunks for a long playlist."""
    first = requests.get(f"{engine.JRIVER_BASE}/Playback/PlayByKey",
                         params={"Key": ",".join(keys[:SEND_CHUNK]), "Zone": zone}, auth=engine.AUTH, timeout=15)
    if first.status_code != 200:
        return False
    for start in range(SEND_CHUNK, len(keys), SEND_CHUNK):
        engine.queue_tracks(keys[start:start + SEND_CHUNK], zone)
    return True


def play(found, zone, device_id=None, report=print):
    """
    Plays a playlist (found: {"ID", "Name"} from library.find_playlist) on a zone
    with its Saved Playlists settings. Returns (ok, what was started, for Alexa to say).
    """
    pid, name = str(found.get("ID")), found.get("Name") or "playlist"
    row = row_for(settings_for(device_id), pid, type_of(found))
    shuffle = row.get("shuffle") == "1"
    days = int(row["skip"]) if str(row.get("skip", "0")).isdigit() else 0
    nonstop = row.get("nonstop", "no") if row.get("nonstop") in ("artists", "tracks") else "no"
    blend = row.get("blend") if row.get("blend") in ("artists", "tracks") else None
    what = f"playlist {name}" + (", shuffled" if shuffle else "") + (", with new tracks blended in" if blend else "")
    if not shuffle and not days and nonstop == "no" and not blend:
        # nothing to change: JRiver plays it itself, exactly as saved
        r = requests.get(f"{engine.JRIVER_BASE}/Playback/PlayPlaylist",
                         params={"Playlist": pid, "PlaylistType": "ID", "Zone": zone}, auth=engine.AUTH, timeout=10)
        engine.nonstop_forget(zone)
        return r.status_code == 200, what
    try:
        keys = playlist_keys(pid)
    except Exception as e:
        report(f"  Problem: couldn't read {name} from JRiver ({e}), so it plays as saved.")
        keys = []
    if not keys:
        r = requests.get(f"{engine.JRIVER_BASE}/Playback/PlayPlaylist",
                         params={"Playlist": pid, "PlaylistType": "ID", "Zone": zone}, auth=engine.AUTH, timeout=10)
        engine.nonstop_forget(zone)
        return r.status_code == 200, f"playlist {name}"
    if days:
        played = engine.PlayedFilter("top", report=report, setting=(True, days))
        fresh = [k for k in keys if played.fresh(k)]
        played.done()
        if fresh:
            keys = fresh
        else:   # the safety net: a voice command should never end in silence
            report(f"  Note: everything in {name} was played in the last {days} "
                   f"day{'' if days == 1 else 's'}, so it plays in full.")
    if shuffle:
        random.shuffle(keys)
    if not _send(keys, zone):
        return False, what
    if blend:   # the playlist is playing; the new tracks are found on the Play tab and woven in
        try:
            import voice
            import blend as blender
            if voice._submit is not None:
                voice._submit(blender.job(zone, keys, name, device_id, blend),
                              f"Blend: {name} on {engine.zone_label(zone)}",
                              {"from": "voice", "device": device_id} if device_id else None)
        except Exception as e:
            report(f"  Problem: the blend didn't start ({e}), so {name} plays as saved.")
    if nonstop == "no":
        engine.nonstop_forget(zone)
    else:
        engine.nonstop_record(zone, keys, kind="saved", stage="after", vibe=None,
                              saved_cfg={"using": nonstop, "reseed": "second" if row.get("reseed") == "second"
                                         else "last"})
    return True, what
