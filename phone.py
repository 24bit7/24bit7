"""
24bit7 - Copy Tracks To: a saved playlist's tracks copied to a phone (Ben, 23 Nov 2026).

Ben and Jo build playlists in 24bit7 and want them on their phones (both Google Pixels) without fluffing about in
JRiver. Save Playlist's pop-up has a Copy Tracks To tick: the phone (named as you like, "Ben's Phone", told apart by
Windows' device id, which carries the serial, so two of the same phone keep their own names), the folder on it
(Music to start), a limit in GB, and Clear Music First. The tracks go into artist and album folders under the chosen
one, with the playlist's .m3u8 at the top listing them in order by their paths, so the phone's player shows it as a
playlist (1.40.0 put each playlist in a folder of its own; Ben, 23 Nov 2026, wanted the band and album folders).

A phone over USB has no drive letter: it's reached through Windows Portable Devices (WPD), here through comtypes.
Proved on Ben's Pixel 9a on 23 Nov 2026: a folder made, files written (37 MB a second), a recursive delete with
no prompt. Everything below WpdPhone works against any object with the same few methods, so the tests use a fake.

Rules:
- Clear First empties the chosen folder (asked once, with the count), leaving dot folders like .thumbnails be,
  but keeps what the new playlist lists at the same place and size, so nothing is copied back (24 Nov 2026).
- Saving the same playlist again copies only what's new, and takes out what's left the playlist unless another
  playlist copied to that folder still lists it (what each put there is kept with the device's choices). A
  playlist saved empty comes off, its .m3u8 with it.
- Without Clear First, every other playlist file in the folder is checked: a song no longer there comes out of
  its list, and a playlist left with none goes.
- The limit and the phone's free space (less a margin) are filled in playlist order; what doesn't fit is said.
"""

import json
import os
import re
import time

import engine
from i18n import t, tn

META_KEY = "copy_devices"     # {device id: {"name", "folder", "limit_gb", "clear"}}
PC = "pc"                     # This PC: a folder here, for Syncthing and the like (Ben, 24 Nov 2026)
LINKS_KEY = "copy_links"      # {USB device id: "app:<id>"}: the phone's app, read from Music/.24bit7
APP_PORT = 47247              # the phone app's port (android/.../TransferService.kt)
LAST_KEY = "copy_last"        # the device id last copied to
DEFAULT_FOLDER = "Music"
SPARE = 200 * 1000 * 1000     # bytes left free on the phone, so it never fills to the brim
GB = 1000 * 1000 * 1000       # as phones and Windows' This PC count them for storage


# --- what's remembered per device ------------------------------------------------------------------------

def _meta(key, default):
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row and row[0] else default
    except Exception:
        return default


def _set_meta(key, value):
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, json.dumps(value)))
    con.commit()


def key_for(device_id):
    """The key a device's choices and records are kept under: a USB phone with the app on it is its app's."""
    return _meta(LINKS_KEY, {}).get(device_id, device_id)


def is_wifi(device_id):
    return str(device_id or "").startswith("app:")


def settings(device_id, model=""):
    """A device's remembered choices: its name (the phone's own to start), folder, limit (0 is none), Clear First.
    This PC has no folder until one is chosen."""
    saved = _meta(META_KEY, {}).get(key_for(device_id)) or {}
    pc = device_id == PC
    return {"name": t("This PC") if pc else saved.get("name") or model or saved.get("model") or t("Phone"),
            "folder": saved.get("folder") or ("" if pc else DEFAULT_FOLDER),
            "limit_gb": float(saved.get("limit_gb") or 0), "clear": bool(saved.get("clear"))}


def remember(device_id, **choices):
    every = _meta(META_KEY, {})
    key = key_for(device_id)
    every[key] = dict(every.get(key) or {}, **choices)
    _set_meta(META_KEY, every)
    _set_meta(LAST_KEY, device_id)


def last_device():
    return _meta(LAST_KEY, None)


_unlinked = set()   # USB phones looked at this run with no app on them


def _link_usb(device_id, model):
    """
    A USB phone's key: its app's ("app:...") once Music/.24bit7 has been read off it, the device id until then. The
    first time the link is found, what was kept under the device id moves to the app's key, so a phone added over
    WiFi and the same phone plugged in share one name, folder, limit and record (Ben, 24 Nov 2026).
    """
    links = _meta(LINKS_KEY, {})
    if device_id in links:
        return links[device_id]
    if device_id in _unlinked:
        return device_id
    app_id = ""
    try:
        p = WpdPhone(device_id, model)
        try:
            music = p.folder(DEFAULT_FOLDER)
            mark = p.child(music, ".24bit7") if music is not None else None
            app_id = _decode(p.read(mark)).strip() if mark is not None else ""
        finally:
            p.close()
    except Exception as e:
        engine.debug(f"Copy Tracks To: couldn't look for the app on {model} ({e})")
    if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", app_id or ""):
        _unlinked.add(device_id)
        return device_id
    key = "app:" + app_id.lower()
    links[device_id] = key
    _set_meta(LINKS_KEY, links)
    every = _meta(META_KEY, {})
    old, new = every.pop(device_id, None) or {}, every.get(key) or {}
    copied = dict(old.get("copied") or {})
    for folder, lists in (new.get("copied") or {}).items():
        copied[folder] = dict(copied.get(folder) or {}, **lists)
    merged = dict(old)
    merged.update(new)
    merged["copied"] = copied
    every[key] = merged
    _set_meta(META_KEY, every)
    return key


# --- names on the phone -------------------------------------------------------------------------------------

def safe_name(text):
    """A file or folder name a phone and Windows both take: no \\ / : * ? " < > |, no trailing dots or spaces."""
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text or "").strip().rstrip(".").strip()
    return text[:120] or "_"


def file_names(tracks):
    """
    One path per track on the phone, under the chosen folder: 'Album Artist/Album/05 Title.flac' (Ben, 23 Nov 2026:
    "keep the band/album folder structure, even though we might only have one track in a folder"). A second disc
    reads '2-05 Title'; a track with no album sits in its artist's folder. Two that would share a path get a
    number ('Intro (2).flac'). The same track gets the same path on every save, so only new ones are copied, and a
    song on two playlists is one file.
    """
    seen, out = set(), []
    for tr in tracks:
        ext = os.path.splitext(tr["path"])[1].lower()
        artist = safe_name(tr.get("album_artist") or tr.get("artist") or t("Unknown Artist"))
        album = tr.get("album") or ""
        disc, number = tr.get("disc") or 0, tr.get("number") or 0
        lead = (f"{disc}-" if disc > 1 else "") + (f"{number:02d} " if number else "")
        title = safe_name(lead + (tr.get("title") or os.path.splitext(os.path.basename(tr["path"]))[0]))
        where = f"{artist}/{safe_name(album)}" if album else artist
        path, n = f"{where}/{title}{ext}", 1
        while path.lower() in seen:
            n += 1
            path = f"{where}/{title} ({n}){ext}"
        seen.add(path.lower())
        out.append(path)
    return out


def m3u8_text(paths):
    """The playlist file, at the top of the chosen folder: the tracks in order, by their paths from there."""
    return "#EXTM3U\n" + "".join(p + "\n" for p in paths)


# --- the copy ------------------------------------------------------------------------------------------------

def tracks_for(keys):
    """The playlist's tracks you have files for: {key, path, artist, title, album, album_artist, disc, number,
    size}, in order."""
    import library
    out = []
    for k in keys:
        row = library.track_row(str(k)) or {}
        path = row.get("Filename") or ""
        if not path or not os.path.isfile(path):
            continue
        disc, number = library.track_order(row)
        out.append({"key": str(k), "path": path, "artist": row.get("Artist") or "", "title": row.get("Name") or "",
                    "album": row.get("Album") or "", "album_artist": row.get("Album Artist (auto)") or "",
                    "disc": disc or 0, "number": number or 0, "size": os.path.getsize(path)})
    return out


def size_text(n):
    return t("{gb} GB", gb=f"{n / GB:.1f}") if n >= GB / 10 else t("{mb} MB", mb=max(1, round(n / 1e6)))


def _wanted(playlist, tracks):
    """{path.lower(): size} of what the playlist puts in the folder, and the folders those paths run through."""
    wanted = {p.lower(): tr["size"] for tr, p in zip(tracks, file_names(tracks))}
    through = {p.rsplit("/", i)[0] for p in wanted for i in range(1, p.count("/") + 1)}
    return wanted, through


def _clear_plan(dirs, wanted, through, skip):
    """
    What Clear First takes out (Ben, 24 Nov 2026: a clear never deletes what the new playlist is about to copy
    back): (folders taken out whole, [(folder, file entry)] taken out one by one, how many tracks stay). A folder
    holding nothing the playlist wants goes in one; a file the playlist lists at the same place and size stays.
    Dot folders and files (.thumbnails, .24bit7) are never touched, and skip (the playlist's own .m3u8, written
    again anyway) isn't counted.
    """
    whole, files, kept = [], [], 0

    def visit(rel):
        nonlocal kept
        dirs._list(rel)
        for low, real in sorted(dirs.names[rel].items()):
            if real.startswith("."):
                continue
            child = f"{rel}/{real}" if rel else real
            dirs.ids.setdefault(child, dirs.kids[rel][low])
            if child.lower() in through:
                visit(child)
            else:
                whole.append(child)
        for low, e in sorted(dirs.files[rel].items()):
            path = f"{rel}/{e['name']}".lower() if rel else low
            if e["name"].startswith(".") or path == skip:
                continue
            if path in wanted and e.get("size") in (None, wanted[path]):
                kept += 1
            else:
                files.append((rel, e))
    visit("")
    return whole, files, kept


def clear_plan(phone, folder, playlist, tracks):
    """What Clear First would do to the folder, for the question asked once: (folders, files, tracks kept)."""
    root = phone.folder(folder, make=False)
    if root is None:
        return 0, 0, 0
    wanted, through = _wanted(playlist, tracks)
    whole, files, kept = _clear_plan(_Dirs(phone, root), wanted, through, safe_name(playlist).lower() + ".m3u8")
    return len(whole), len(files), kept


def _exists(dirs, rel):
    d, _, name = rel.rpartition("/")
    return name.lower() in dirs.listing(d)


def _decode(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _relative(line):
    """A playlist line as a path inside the folder ('Seether/Disclaimer II/03 Broken.flac'), or None for a line
    with a drive, a web address or a path above the folder, which 24bit7 never judges."""
    rel = line.strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return None if ":" in rel or rel.startswith(("/", "../")) else rel


def _tidy_playlists(phone, dirs, root, mine, skip, say):
    """
    Every other playlist file at the top of the folder, checked against what's there (Ben, 24 Nov 2026): a song
    no longer in the folder comes out of its list, and a playlist left with none goes. 24bit7's own are read from
    what it kept; any other is read off the phone, and only lines that name a file in the folder are judged (a
    line with a drive, a web address or a path above the folder stays as it is). Returns how many were changed.
    """
    changed = 0
    for low, e in sorted(dirs.listing("").items()):
        if low == skip or low.startswith(".") or not low.endswith((".m3u8", ".m3u")):
            continue
        recorded = mine.get(low)
        if recorded is not None:
            keep = [p for p in recorded if _exists(dirs, p)]
            gone, left = len(recorded) - len(keep), len(keep)
            text = m3u8_text(keep)
        else:
            try:
                lines = _decode(phone.read(e["id"])).splitlines()
            except Exception as err:
                engine.debug(f"Copy Tracks To: couldn't read {e['name']} ({err})")
                continue
            out, pending, gone, left = [], [], 0, 0
            for line in lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    pending.append(line)
                    continue
                rel = _relative(s)
                if rel is None or _exists(dirs, rel):
                    out += pending + [line]
                    left += 1
                else:
                    out += [p for p in pending if not p.strip().upper().startswith("#EXTINF")]
                    gone += 1
                pending = []
            out += pending
            text = "\n".join(out) + "\n"
        if not gone:
            continue
        changed += 1
        phone.delete([e["id"]])
        dirs.files[""].pop(low, None)
        if not left:
            mine.pop(low, None)
            say("  " + t("{name} had none of its songs left in the folder, so it was taken off.", name=e["name"]))
            continue
        phone.put_text(root, e["name"], text)
        if recorded is not None:
            mine[low] = keep
        say("  " + tn("{name} listed {count} song no longer in the folder: taken out of it.",
                      "{name} listed {count} songs no longer in the folder: taken out of it.", gone, name=e["name"]))
    return changed


def _records(phone):
    """
    What each playlist has put on this phone, by folder: (the device's key, {folder: {playlist.m3u8: [paths]}}).
    Kept with the device's choices, so a second save knows what was its own and a song another playlist still
    lists is never taken off.
    """
    key = key_for(getattr(phone, "id", None) or phone.name)
    return key, dict((_meta(META_KEY, {}).get(key) or {}).get("copied") or {})


def _keep_records(key, copied):
    every = _meta(META_KEY, {})
    every[key] = dict(every.get(key) or {}, copied=copied)
    _set_meta(META_KEY, every)


class _Dirs:
    """The folders under the chosen one, by path from it ('Godsmack/Awake'), each listed once, made when needed."""

    def __init__(self, phone, root):
        self.phone, self.ids, self.kids, self.files, self.names = phone, {"": root}, {}, {}, {}

    def _list(self, rel):
        if rel not in self.kids:
            fid = self.ids.get(rel)
            entries = self.phone.list(fid) if fid else []
            self.kids[rel] = {e["name"].lower(): e["id"] for e in entries if e["folder"]}
            self.names[rel] = {e["name"].lower(): e["name"] for e in entries if e["folder"]}
            self.files[rel] = {e["name"].lower(): e for e in entries if not e["folder"]}
        return self.kids[rel]

    def get(self, rel, make=False):
        if rel in self.ids:
            return self.ids[rel]
        parent_rel, _, name = rel.rpartition("/")
        parent = self.get(parent_rel, make)
        if parent is None:
            return None
        found = self._list(parent_rel).get(name.lower())
        if found is None and make:
            found = self.phone.make(parent, name)
            self.kids[parent_rel][name.lower()] = found
            self.names[parent_rel][name.lower()] = name
            self.kids[rel], self.files[rel], self.names[rel] = {}, {}, {}
        if found is not None:
            self.ids[rel] = found
        return found

    def listing(self, rel):
        """{name: entry} of the files in a folder, {} if it isn't there."""
        if self.get(rel) is None:
            return {}
        self._list(rel)
        return self.files[rel]

    def forget(self, rel):
        parent_rel, _, name = rel.rpartition("/")
        self.kids.get(parent_rel, {}).pop(name.lower(), None)
        self.names.get(parent_rel, {}).pop(name.lower(), None)
        for d in [d for d in set(self.ids) | set(self.kids) if d == rel or d.lower().startswith(rel.lower() + "/")
                  or d.lower() == rel.lower()]:
            self.ids.pop(d, None)
            self.kids.pop(d, None)
            self.files.pop(d, None)
            self.names.pop(d, None)

    def drop_if_empty(self, rel):
        """An album or artist folder left with nothing in it goes too (its parent next, up to the chosen folder)."""
        while rel:
            fid = self.get(rel)
            if fid is None or self.phone.list(fid):
                return
            self.phone.delete([fid])
            self.forget(rel)
            rel = rel.rpartition("/")[0]


def copy_playlist(phone, folder, playlist, tracks, limit_gb=0, clear=False, say=print, progress=None, stop=None):
    """
    Copies tracks (from tracks_for) into the chosen folder on the phone, each in its artist's and album's folders,
    with playlist.m3u8 at the top listing them in order. Returns how many tracks the .m3u8 lists.
    progress, if given, is called with a dict as each track starts and once at the end ("state" copying, done or
    stopped, "done" and "count" tracks, "bytes" and "total", "track", and at the end "line" and "note").
    stop, if given, is asked before each track: True stops there, the .m3u8 listing what's on the phone.
    """
    started = time.time()
    root = phone.folder(folder, make=True)
    device, copied = _records(phone)
    fkey = re.sub(r"[\\/]+", "/", folder or "").strip("/").lower()
    mine = dict(copied.get(fkey) or {})
    dirs = _Dirs(phone, root)
    m3u = safe_name(playlist) + ".m3u8"
    pkey = m3u.lower()
    if clear:
        wanted, through = _wanted(playlist, tracks)
        whole, loose, held = _clear_plan(dirs, wanted, through, pkey)
        ids = [dirs.get(rel) for rel in whole] + [e["id"] for _rel, e in loose]
        if ids:
            phone.delete([i for i in ids if i is not None])
        for rel in whole:
            dirs.forget(rel)
        for rel, e in loose:
            dirs.files[rel].pop(e["name"].lower(), None)
        for rel in sorted({rel for rel, _e in loose if rel}, key=lambda d: -d.count("/")):
            dirs.drop_if_empty(rel)
        if whole or loose:
            folders = tn("{count} folder", "{count} folders", len(whole))
            files = tn("{count} file", "{count} files", len(loose))
            say("  " + (tn("Cleared {folder} on {phone}: {folders} and {files} taken out, {count} track already "
                           "there kept.",
                           "Cleared {folder} on {phone}: {folders} and {files} taken out, {count} tracks already "
                           "there kept.", held, folder=folder, phone=phone.name, folders=folders, files=files)
                        if held else
                        t("Cleared {folder} on {phone}: {folders} and {files} taken out.", folder=folder,
                          phone=phone.name, folders=folders, files=files)))
        mine = {}
    # 1.40.0 put a playlist in a folder of its own, its .m3u8 inside: that goes, the tracks now in artists' folders
    own = safe_name(playlist)
    old = dirs.get(own)
    if old is not None and pkey in dirs.listing(own):
        phone.delete([old])
        dirs.forget(own)
        say("  " + t("{name} had a folder of its own from before: its tracks now go in artist and album folders.",
                     name=own))
    paths = file_names(tracks)
    wanted = {p.lower() for p in paths}
    others = {p.lower() for name, ps in mine.items() if name != pkey for p in ps}
    stale = [p for p in mine.get(pkey, []) if p.lower() not in wanted and p.lower() not in others]
    removed = 0
    for p in stale:
        d, _, name = p.rpartition("/")
        e = dirs.listing(d).get(name.lower())
        if e:
            phone.delete([e["id"]])
            dirs.files[d].pop(name.lower(), None)
            removed += 1
    for d in sorted({p.rpartition("/")[0] for p in stale}, key=lambda d: -d.count("/")):
        dirs.drop_if_empty(d)
    if removed:
        say("  " + tn("Took out {count} track no longer in the playlist.",
                      "Took out {count} tracks no longer in the playlist.", removed))
    # what fits: the limit and the phone's free space, filled in playlist order
    on_phone = {}
    for p in paths:
        d, _, name = p.rpartition("/")
        on_phone[p] = dirs.listing(d).get(name.lower())
    room = phone.free() - SPARE
    if limit_gb:
        held = sum(e.get("size") or 0 for e in on_phone.values() if e)
        room = min(room, limit_gb * GB - held)
    todo, kept, left_out = [], set(), []
    for tr, p in zip(tracks, paths):
        already = on_phone[p]
        if already is not None and (already.get("size") in (None, tr["size"])):
            kept.add(p)
            continue
        if tr["size"] > room:
            left_out.append(tr)
            continue
        room -= tr["size"]
        todo.append((tr, p, already))
    total = sum(tr["size"] for tr, _, _ in todo)
    count = len(kept) + len(todo)
    if todo:
        say("  " + tn("Copying {count} track ({size}) to {phone}...", "Copying {count} tracks ({size}) to {phone}...",
                      len(todo), size=size_text(total), phone=phone.name))
    done_bytes, done, stopped = 0, 0, False
    for i, (tr, p, already) in enumerate(todo, 1):
        if stop is not None and stop():
            stopped = True
            break
        if progress is not None:
            progress({"state": "copying", "done": len(kept), "count": count, "bytes": done_bytes, "total": total,
                      "track": f"{tr.get('artist') or ''} - {tr.get('title') or ''}".strip(" -")})
        d, _, name = p.rpartition("/")
        parent = dirs.get(d, make=True)
        if already is not None:   # a different size: a newer file of the same track
            phone.delete([already["id"]])
        phone.put(parent, tr["path"], name, tr["size"])
        dirs.listing(d)[name.lower()] = {"id": None, "name": name, "folder": False, "size": tr["size"]}
        kept.add(p)
        done_bytes += tr["size"]
        done = i
        if i == len(todo) or i % 10 == 0:
            say("  " + t("Copied {done} of {count} ({size}).", done=i, count=len(todo), size=size_text(done_bytes)))
    listed = [p for p in paths if p in kept]
    old_m3u = dirs.listing("").get(pkey)
    if old_m3u is not None:
        phone.delete([old_m3u["id"]])
    if tracks:
        phone.put_text(root, m3u, m3u8_text(listed))
        mine[pkey] = listed
    else:   # a playlist emptied in JRiver and saved again: it comes off (Ben, 24 Nov 2026)
        mine.pop(pkey, None)
    if not clear:
        _tidy_playlists(phone, dirs, root, mine, pkey, say)
    copied[fkey] = mine
    _keep_records(device, copied)
    note = ""
    if left_out:
        what = size_text(sum(tr["size"] for tr in left_out))
        note = (tn("Note: {count} track ({size}) didn't fit within {limit} GB, so it was left out.",
                   "Note: {count} tracks ({size}) didn't fit within {limit} GB, so they were left out.",
                   len(left_out), size=what, limit=f"{limit_gb:g}") if limit_gb else
                tn("Note: {count} track ({size}) didn't fit in the phone's free space, so it was left out.",
                   "Note: {count} tracks ({size}) didn't fit in the phone's free space, so they were left out.",
                   len(left_out), size=what))
        say("  " + note)
    secs = round(time.time() - started)
    if not tracks:
        line = t("Took {name}.m3u8 off {phone}: the playlist is empty now.", name=own, phone=phone.name)
    elif stopped:
        line = t("Stopped: {count} of {total} tracks are on {phone}, with {name}.m3u8. Copying again picks up the "
                 "rest.", count=len(listed), total=count, phone=phone.name, name=own)
    elif todo:
        line = tn("Copied to {phone}: {count} track in {folder}, with {name}.m3u8 ({secs} s).",
                  "Copied to {phone}: {count} tracks in {folder}, with {name}.m3u8 ({secs} s).", len(listed),
                  phone=phone.name, folder=folder, name=own, secs=secs)
    else:   # saved again with nothing new: only the .m3u8 was written
        line = tn("Already on {phone}: {count} track in {folder}, with {name}.m3u8.",
                  "Already on {phone}: {count} tracks in {folder}, with {name}.m3u8.", len(listed),
                  phone=phone.name, folder=folder, name=own)
    say(line)
    if progress is not None:
        progress({"state": "stopped" if stopped else "done", "done": len(listed), "count": count,
                  "bytes": done_bytes, "total": total, "track": "", "line": line, "note": note, "secs": secs})
    return len(listed)


# --- Manage Folder ----------------------------------------------------------------------------------------------

AUDIO = (".flac", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".aif", ".aiff", ".wma", ".ape", ".wv",
         ".dsf", ".dff", ".mpc", ".alac")


def is_track(name):
    return name.lower().endswith(AUDIO)


def names_text(names):
    """"Indie-Chill", "Indie-Chill and Road Trip", "Indie-Chill, Road Trip and L.A. Woman": names only, never
    translated, joined the way the language joins a list."""
    names = list(names)
    if len(names) < 2:
        return "".join(names)
    return t("{names} and {last}", names=", ".join(names[:-1]), last=names[-1])


class Folder:
    """
    Manage Folder's picture of the folder copied to (Ben, 24 Nov 2026, as drawn), read once: its playlists (the
    .m3u8 and .m3u files at its top, each with the songs it lists that are there), and every file under it, by
    folder, so artists, albums and tracks can be ticked and deleted. Dot folders and files (.thumbnails, .24bit7)
    are left out, as they are never touched.
    """

    def __init__(self, phone, folder):
        self.phone, self.folder = phone, folder
        self.root = phone.folder(folder, make=False)
        self.device, self.copied = _records(phone)
        self.fkey = re.sub(r"[\\/]+", "/", folder or "").strip("/").lower()
        self.mine = dict(self.copied.get(self.fkey) or {})
        self.dirs = _Dirs(phone, self.root) if self.root is not None else None
        self.files = {}     # path.lower(): {"rel", "size", "id"}
        self.folders = {}   # path.lower(): path, every folder under the chosen one
        self.playlists = []
        if self.root is None:
            return
        self._walk("")
        for low, e in sorted(self.dirs.files[""].items()):
            if low.startswith(".") or not low.endswith((".m3u8", ".m3u")):
                continue
            recorded = self.mine.get(low)
            try:
                listed = (recorded if recorded is not None else
                          [r for r in map(_relative, _decode(phone.read(e["id"])).splitlines())
                           if r and not r.startswith("#")])
            except Exception as err:
                engine.debug(f"Manage Folder: couldn't read {e['name']} ({err})")
                listed = []
            paths = list(dict.fromkeys(p.lower() for p in listed if p.lower() in self.files))
            self.playlists.append({"name": e["name"].rsplit(".", 1)[0], "low": low, "id": e["id"], "paths": paths,
                                   "tracks": sum(is_track(p) for p in paths),
                                   "size": sum(self.files[p]["size"] for p in paths)})
        self.lists_of = {}   # path.lower(): [the names of the playlists listing it]
        for pl in self.playlists:
            for p in pl["paths"]:
                self.lists_of.setdefault(p, []).append(pl["name"])

    def _walk(self, rel):
        self.dirs._list(rel)
        for low, real in sorted(self.dirs.names[rel].items()):
            if real.startswith("."):
                continue
            child = f"{rel}/{real}" if rel else real
            self.dirs.ids.setdefault(child, self.dirs.kids[rel][low])
            self.folders[child.lower()] = child
            self._walk(child)
        for low, e in sorted(self.dirs.files[rel].items()):
            if e["name"].startswith(".") or (not rel and low.endswith((".m3u8", ".m3u"))):
                continue
            path = f"{rel}/{e['name']}" if rel else e["name"]
            self.files[path.lower()] = {"rel": path, "size": e.get("size") or 0, "id": e["id"]}

    @property
    def size(self):
        return sum(f["size"] for f in self.files.values())

    def under(self, folder):
        """The files under a folder (its path from the chosen one), as path.lower()."""
        start = folder.lower() + "/"
        return {k for k in self.files if k.startswith(start)}

    def tree(self):
        """
        Artists and albums: [node] for the folders at the top (artists), each with its folders (albums) and files
        (tracks) as children, then loose files. A node is a dict: name, rel, kind ("folder" or "file"), children,
        files (path.lower() of every file under it), tracks, size, lists (names of the playlists listing any).
        """
        def node(rel, kind):
            files = self.under(rel) if kind == "folder" else {rel.lower()}
            lists = sorted({n for f in files for n in self.lists_of.get(f, [])}, key=str.lower)
            return {"name": rel.rpartition("/")[2], "rel": rel, "kind": kind, "children": [], "files": files,
                    "tracks": sum(is_track(f) for f in files), "size": sum(self.files[f]["size"] for f in files),
                    "lists": lists}

        def children(parent):
            depth = parent.count("/") + 1 if parent else 0
            start = parent.lower() + "/" if parent else ""
            subs = sorted((r for k, r in self.folders.items() if k.startswith(start) and r.count("/") == depth),
                          key=str.lower)
            loose = sorted((f["rel"] for k, f in self.files.items() if k.startswith(start)
                            and f["rel"].count("/") == depth), key=str.lower)
            out = []
            for r in subs:
                n = node(r, "folder")
                n["children"] = children(r)
                out.append(n)
            return out + [node(r, "file") for r in loose]
        return children("")

    def plan(self, playlists=(), folders=(), files=()):
        """
        What deleting the ticked would do (Ben, 24 Nov 2026, as drawn): a playlist ticked takes its file and the
        songs no other playlist lists; an album or artist ticked goes whole, and every playlist listing its songs
        is amended (taken off if none are left). {"playlists": [low], "folders": [rel], "files": {path.lower()},
        "loose": [path.lower()] deleted one by one, "tracks", "size", "amended": [names], "kept": songs of a ticked
        playlist staying because another lists them}.
        """
        ticked = set(playlists)
        folders = sorted({f for f in folders if f.lower() in self.folders}, key=lambda f: f.count("/"))
        whole = []
        for f in folders:
            if not any(f.lower().startswith(w.lower() + "/") for w in whole):
                whole.append(f)
        going = set().union(*(self.under(f) for f in whole)) if whole else set()
        going |= {f.lower() for f in files if f.lower() in self.files}
        still = {p for pl in self.playlists if pl["low"] not in ticked for p in pl["paths"]}
        kept = set()
        for pl in self.playlists:
            if pl["low"] in ticked:
                going |= {p for p in pl["paths"] if p not in still}
                kept |= {p for p in pl["paths"] if p in still and p not in going}
        loose = sorted(p for p in going if not any(p.startswith(w.lower() + "/") for w in whole))
        amended = [pl["name"] for pl in self.playlists
                   if pl["low"] not in ticked and any(p in going for p in pl["paths"])]
        return {"playlists": [pl["low"] for pl in self.playlists if pl["low"] in ticked], "folders": whole,
                "files": going, "loose": loose, "tracks": sum(is_track(p) for p in going),
                "size": sum(self.files[p]["size"] for p in going), "amended": amended, "kept": len(kept)}

    def plan_text(self, plan, what):
        """The amber line above Delete: what goes, said before it does, so no further question is asked."""
        if not plan["playlists"] and not plan["files"]:
            return ""
        what = dict(what=what, phone=self.phone.name, size=size_text(plan["size"]),
                    tracks=tn("{count} track", "{count} tracks", plan["tracks"]), lists=names_text(plan["amended"]))
        if not plan["files"]:
            return tn("Deleting {what} takes the playlist off {phone}. Its songs stay, as other playlists list them.",
                      "Deleting {what} takes the playlists off {phone}. Their songs stay, as other playlists list "
                      "them.", len(plan["playlists"]), **what)
        if plan["amended"]:
            return t("Deleting {what} takes {tracks} ({size}) off {phone} and out of {lists}.", **what)
        return t("Deleting {what} takes {tracks} ({size}) off {phone}.", **what)

    def delete(self, plan, say=print):
        """Deletes what plan() said, amends the playlists left, and keeps 24bit7's records in step."""
        if self.root is None:
            return
        by_name = {pl["low"]: pl for pl in self.playlists}
        ids = [self.dirs.get(f) for f in plan["folders"]]
        ids += [self.files[p]["id"] for p in plan["loose"]]
        ids += [by_name[low]["id"] for low in plan["playlists"]]
        self.phone.delete([i for i in ids if i is not None])
        for f in plan["folders"]:
            self.dirs.forget(f)
        for p in plan["loose"]:
            d, _, name = self.files[p]["rel"].rpartition("/")
            self.dirs.files.get(d, {}).pop(name.lower(), None)
        for low in plan["playlists"]:
            self.dirs.files[""].pop(low, None)
            self.mine.pop(low, None)
            say("  " + t("Took {name} off {phone}.", name=by_name[low]["name"], phone=self.phone.name))
        parents = {self.files[p]["rel"].rpartition("/")[0] for p in plan["loose"]}
        parents |= {f.rpartition("/")[0] for f in plan["folders"]}
        for d in sorted((d for d in parents if d), key=lambda d: -d.count("/")):
            self.dirs.drop_if_empty(d)
        if plan["files"]:
            say("  " + tn("Deleted {count} track ({size}) from {folder} on {phone}.",
                          "Deleted {count} tracks ({size}) from {folder} on {phone}.", plan["tracks"],
                          size=size_text(plan["size"]), folder=self.folder, phone=self.phone.name))
        _tidy_playlists(self.phone, self.dirs, self.root, self.mine, None, say)
        self.copied[self.fkey] = self.mine
        _keep_records(self.device, self.copied)


# --- where a copy can go --------------------------------------------------------------------------------------

def targets():
    """
    [(device id, model)] the Device list offers: the phones plugged in, the phones added over WiFi that aren't
    plugged in too (one phone is one device: Music/.24bit7 links the two), then This PC.
    """
    out, seen = [], set()
    for device_id, model in devices():
        out.append((device_id, model))
        seen.add(_link_usb(device_id, model))
    for key, entry in _meta(META_KEY, {}).items():
        if is_wifi(key) and entry.get("code") and key not in seen:
            out.append((key, entry.get("model") or ""))
    return out + [(PC, t("This PC"))]


def label(device_id, model=""):
    """How the Device list shows it: "Ben's Phone (USB)", "Jo's Phone (WiFi)", "This PC"."""
    name = settings(device_id, model)["name"]
    if device_id == PC:
        return name
    return t("{name} (WiFi)", name=name) if is_wifi(device_id) else t("{name} (USB)", name=name)


def open_device(device_id, name):
    """The device to copy to: a phone over USB or WiFi, or a folder on This PC."""
    if device_id == PC:
        return FolderDevice(name)
    if is_wifi(device_id):
        return WifiPhone.find(device_id, name)
    return WpdPhone(device_id, name)


def _shell_item(parts):
    """The shell's item for a path under This PC (a phone has no drive letter, so Explorer reaches it by names:
    "Pixel 9a", its storage, then the folders), or None. The phone's storage is taken as its first."""
    import comtypes.client as cc
    shell = cc.CreateObject("Shell.Application", dynamic=True)
    here, item = shell.NameSpace(17), None
    for i, part in enumerate(parts):
        items = here.Items()
        found = [items.Item(k) for k in range(items.Count)]
        found = [f for f in found if f.IsFolder]
        if part is None:
            item = found[0] if found else None
        else:
            item = next((f for f in found if (f.Name or "").lower() == part.lower()), None)
        if item is None:
            return None
        if i < len(parts) - 1:
            here = item.GetFolder
    return item


def open_in_explorer(device_id, model, folder):
    """
    Open Folder (Ben, 24 Nov 2026): Explorer at the folder copied to: a folder here as it is, a phone's by USB
    through This PC. A phone over WiFi has none (Explorer can't reach it). False if it isn't there.
    """
    if device_id == PC:
        if not folder or not os.path.isdir(folder):
            return False
        os.startfile(folder)
        return True
    if is_wifi(device_id):
        return False
    item = _shell_item([model, None] + [p for p in re.split(r"[\\/]+", folder or "") if p])
    if item is None:
        return False
    item.InvokeVerb()
    return True


def pc_folder_problem(folder):
    """
    Why This PC's folder won't do, or "" (24 Nov 2026): it must be a whole path, not a drive's top, and hold none of
    the library's own files, since Clear First would take them out.
    """
    folder = (folder or "").strip()
    if not folder or not os.path.isabs(folder):
        return t("Choose a folder on this PC with Browse.")
    full = os.path.normcase(os.path.abspath(folder)).rstrip("\\/")
    if os.path.splitdrive(full)[1] in ("", "\\", "/"):
        return t("That's a whole drive: choose a folder in it.")
    import library
    inside = full + os.sep
    if any(os.path.normcase(f).startswith(inside) for f in library.filenames() if f):
        return t("That folder holds your library's music, so 24bit7 won't copy into it.")
    return ""


class FolderDevice:
    """This PC: a folder here, through the same few methods as a phone, so the copy, the tidy-up and Clear First
    work alike. Paths are its ids. Nothing outside the chosen folder is ever deleted."""

    def __init__(self, name=None):
        self.id, self.name, self.root = PC, name or t("This PC"), None

    def close(self):
        pass

    def free(self):
        import shutil
        return shutil.disk_usage(self.root or os.getcwd()).free

    def capacity(self):
        import shutil
        return shutil.disk_usage(self.root or os.getcwd()).total

    def list(self, parent):
        out = []
        with os.scandir(parent) as found:
            for e in found:
                folder = e.is_dir()
                out.append({"id": e.path, "name": e.name, "folder": folder,
                            "size": None if folder else e.stat().st_size})
        return out

    def child(self, parent, name):
        return next((e["id"] for e in self.list(parent) if e["name"].lower() == name.lower()), None)

    def folder(self, path, make=False):
        if pc_folder_problem(path):
            return None
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            if not make:
                return None
            os.makedirs(path)
        self.root = path
        return path

    def make(self, parent, name):
        path = os.path.join(parent, name)
        os.makedirs(path, exist_ok=True)
        return path

    def put(self, parent, path, name, size):
        import shutil
        dest = os.path.join(parent, name)
        shutil.copyfile(path, dest + ".part")
        os.replace(dest + ".part", dest)
        return dest

    def put_text(self, parent, name, text):
        dest = os.path.join(parent, name)
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return dest

    def read(self, oid):
        with open(oid, "rb") as f:
            return f.read()

    def delete(self, ids):
        import shutil
        inside = os.path.normcase(self.root or "") + os.sep
        for oid in ids:
            if not self.root or not os.path.normcase(os.path.abspath(oid)).startswith(inside):
                raise RuntimeError(f"won't delete outside the chosen folder: {oid}")
            if os.path.isdir(oid):
                shutil.rmtree(oid)
            elif os.path.exists(oid):
                os.remove(oid)


# --- a phone over WiFi, through the 24bit7 app on it ------------------------------------------------------------

def _home_networks():
    """The PC's own home networks, as the first three parts of its addresses ('192.168.0'): private ranges only,
    so Tailscale's 100.x and the like are never scanned."""
    import ipaddress
    import socket
    found = set()
    try:
        names = {socket.gethostname(), ""}
        addrs = {a[4][0] for n in names for a in socket.getaddrinfo(n, None, socket.AF_INET)}
    except Exception:
        addrs = set()
    try:   # the address the PC would reach the router from, in case the name gives only the loopback
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 9))
        addrs.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    for a in addrs:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback and not ip.is_link_local and not a.startswith("100."):
            found.add(a.rsplit(".", 1)[0])
    return sorted(found)


def _open_port(host, port=None, timeout=0.4):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port or APP_PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


SLOW_SCAN = 1.5   # the second look's wait per address (Ben, 24 Nov 2026: Jo's first Add found nothing, the second did)


def find_apps(code, timeout=0.4, again=SLOW_SCAN):
    """
    Every phone on the home network with the 24bit7 app open that answers to this code: [(address, info)]. The PC
    can't hear the app announce itself (Windows' firewall keeps that out, 24 Nov 2026), so it tries the app's port
    across each home network, a few seconds at most, and asks whoever answers. If none does, it looks once more,
    waiting longer at each address (again), so a phone slow to answer the first time is still found; that costs a
    few seconds only on a miss.
    """
    from concurrent.futures import ThreadPoolExecutor
    hosts = [f"{net}.{i}" for net in _home_networks() for i in range(1, 255)]
    out = []
    for wait in [timeout] + ([again] if again and again > timeout else []):
        with ThreadPoolExecutor(64) as pool:
            open_ = [h for h, ok in zip(hosts, pool.map(lambda h: _open_port(h, timeout=wait), hosts)) if ok]
        for h in open_:
            try:
                out.append((f"{h}:{APP_PORT}", WifiPhone.info_at(f"{h}:{APP_PORT}", code)))
            except Exception:
                continue
        if out:
            break
    return out


def add_wifi(code):
    """
    + Add a Phone Over WiFi: the phone answering to the code, remembered by its app's id with the code and where it
    was found. (key, model, known): known when it's a phone already kept, by USB or WiFi.
    """
    code = (code or "").strip()
    found = find_apps(code) if re.fullmatch(r"\d{4}", code) else []
    if not found:
        return None
    address, info = found[0]
    key = "app:" + str(info["id"]).lower()
    known = key in _meta(META_KEY, {})
    every = _meta(META_KEY, {})
    every[key] = dict(every.get(key) or {}, code=code, address=address, model=info.get("name") or "")
    _set_meta(META_KEY, every)
    return key, info.get("name") or "", known


class WifiPhone:
    """A phone over WiFi, through the 24bit7 app on it (Ben, 24 Nov 2026). Paths from its shared storage are its
    ids ('Music/Seether'). Proved on Ben's Pixel 9a the same day: 41 MB in 0.6 s from the wired media PC."""

    def __init__(self, key, name, code, address):
        self.id, self.name, self.code, self.address = key, name, code, address

    @staticmethod
    def info_at(address, code, timeout=3):
        import http.client
        host, _, port = address.rpartition(":")
        con = http.client.HTTPConnection(host, int(port), timeout=timeout, blocksize=1 << 16)
        try:
            con.request("GET", "/info", headers={"X-24bit7-Code": code})
            r = con.getresponse()
            body = r.read()
            if r.status != 200:
                raise RuntimeError(f"{r.status}")
            return json.loads(body)
        finally:
            con.close()

    @classmethod
    def find(cls, key, name):
        """The phone, at the address it was last found at or, if it's moved, wherever it answers now."""
        entry = _meta(META_KEY, {}).get(key) or {}
        code, address = entry.get("code") or "", entry.get("address") or ""
        if address:
            try:
                if "app:" + str(cls.info_at(address, code, timeout=1.5).get("id")).lower() == key:
                    return cls(key, name, code, address)
            except Exception:
                pass
        for where, info in find_apps(code):
            if "app:" + str(info.get("id")).lower() == key:
                remember_quietly(key, address=where)
                return cls(key, name, code, where)
        raise RuntimeError(t("{phone} isn't answering. Open 24bit7 on it, on the same WiFi as this PC.", phone=name))

    def close(self):
        pass

    def _call(self, method, path, rel=None, body=None, length=None, timeout=120):
        import http.client
        import urllib.parse
        host, _, port = self.address.rpartition(":")
        con = http.client.HTTPConnection(host, int(port), timeout=timeout, blocksize=1 << 16)
        url = path + ("?path=" + urllib.parse.quote(rel, safe="") if rel is not None else "")
        headers = {"X-24bit7-Code": self.code}
        if length is not None:
            headers["Content-Length"] = str(length)
        try:
            con.request(method, url, body=body, headers=headers)
            r = con.getresponse()
            data = r.read()
            if r.status == 404:
                return None
            if r.status >= 300:
                raise RuntimeError(f"{self.name}: {r.status} {data[:200].decode('utf-8', 'replace')}")
            return data
        finally:
            con.close()

    def _json(self, *a, **k):
        data = self._call(*a, **k)
        return None if data is None else json.loads(data)

    def free(self):
        return int(self._json("GET", "/info")["free"])

    def capacity(self):
        return int(self._json("GET", "/info")["total"])

    def list(self, parent):
        got = self._json("GET", "/list", parent) or {"entries": []}
        return [{"id": f"{parent}/{e['name']}" if parent else e["name"], "name": e["name"], "folder": bool(e["dir"]),
                 "size": None if e["dir"] else int(e["size"])} for e in got["entries"]]

    def child(self, parent, name):
        return next((e["id"] for e in self.list(parent) if e["name"].lower() == name.lower()), None)

    def folder(self, path, make=False):
        rel = "/".join(p for p in re.split(r"[\\/]+", path or "") if p)
        if not rel:
            return ""
        if self._call("GET", "/list", rel) is None:
            if not make:
                return None
            self._call("POST", "/mkdir", rel)
        return rel

    def make(self, parent, name):
        rel = f"{parent}/{name}" if parent else name
        self._call("POST", "/mkdir", rel)
        return rel

    def put(self, parent, path, name, size):
        rel = f"{parent}/{name}" if parent else name
        with open(path, "rb") as f:
            self._call("PUT", "/file", rel, body=f, length=size, timeout=300)
        return rel

    def put_text(self, parent, name, text):
        data = text.encode("utf-8")
        rel = f"{parent}/{name}" if parent else name
        self._call("PUT", "/file", rel, body=data, length=len(data))
        return rel

    def read(self, oid):
        data = self._call("GET", "/file", oid)
        if data is None:
            raise RuntimeError(f"{oid} isn't there")
        return data

    def delete(self, ids):
        for oid in ids:
            if oid:   # never the whole phone
                self._call("DELETE", "/file", oid)


def remember_quietly(key, **choices):
    """Kept for a device without making it the last one used (where a WiFi phone was found)."""
    every = _meta(META_KEY, {})
    every[key] = dict(every.get(key) or {}, **choices)
    _set_meta(META_KEY, every)


# --- Windows Portable Devices ----------------------------------------------------------------------------------

_OBJ = "{EF6B490D-5CD8-437A-AFFC-DA8B60EE4A3C}"
_STORAGE = "{01A3057A-74D6-4E80-BEA7-DC4C212CE50A}"
_FOLDER_TYPES = ("{27E2E392-A111-48E0-AB0C-E17705A05F85}", "{99ED0160-17FF-4C44-9D98-1D7A6F941921}")


def _wpd():
    """comtypes and the two WPD type libraries, loaded on first use (generated into comtypes' own cache)."""
    import comtypes
    import comtypes.client as cc
    cc.GetModule("portabledeviceapi.dll")
    cc.GetModule("portabledevicetypes.dll")
    import comtypes.gen.PortableDeviceApiLib as port
    import comtypes.gen.PortableDeviceTypesLib as types
    return comtypes, cc, port, types


def com_begin():
    """COM for a thread that talks to a phone (the copy runs on one). Nothing if comtypes isn't there."""
    try:
        import comtypes
        comtypes.CoInitialize()
        return True
    except Exception:
        return False


def com_end():
    try:
        import comtypes
        comtypes.CoUninitialize()
    except Exception:
        pass


def is_phone(device_id):
    """
    A phone or player plugged in over USB (MTP). Windows lists every drive as a portable device too (on the media
    PC, D: and four library disks as "New Volume", 23 Nov 2026), and Clear First must never reach one of those.
    """
    return (device_id or "").lower().startswith("\\\\?\\usb#")


def devices():
    """[(device id, the name the phone gives itself)] for every phone Windows has plugged in over USB."""
    import ctypes
    from ctypes import POINTER, byref, c_ulong, c_wchar_p
    try:
        comtypes, cc, port, _types = _wpd()
        m = cc.CreateObject(port.PortableDeviceManager, clsctx=comtypes.CLSCTX_INPROC_SERVER,
                            interface=port.IPortableDeviceManager)
        count = c_ulong(0)
        m._IPortableDeviceManager__com_GetDevices(POINTER(c_wchar_p)(), byref(count))
        if not count.value:
            return []
        ids = (c_wchar_p * count.value)()
        m._IPortableDeviceManager__com_GetDevices(ctypes.cast(ids, POINTER(c_wchar_p)), byref(count))
        out = []
        for i in range(count.value):
            if not is_phone(ids[i]):
                continue
            n = c_ulong(0)
            m._IPortableDeviceManager__com_GetDeviceFriendlyName(ids[i], POINTER(ctypes.c_ushort)(), byref(n))
            buf = ctypes.create_unicode_buffer(max(1, n.value))
            m._IPortableDeviceManager__com_GetDeviceFriendlyName(ids[i], ctypes.cast(buf, POINTER(ctypes.c_ushort)),
                                                                 byref(n))
            out.append((ids[i], buf.value))
        return out
    except Exception as e:
        engine.debug(f"Copy Tracks To: couldn't list devices ({e})")
        return []


class WpdPhone:
    """A phone over USB, through Windows Portable Devices. Folders are reached by path from its main storage."""

    def __init__(self, device_id, name):
        self.id, self.name = device_id, name
        comtypes, cc, port, types = self._lib = _wpd()
        self._dev = cc.CreateObject(port.PortableDevice, clsctx=comtypes.CLSCTX_INPROC_SERVER,
                                    interface=port.IPortableDevice)
        self._dev.Open(device_id, self._values())
        self._content = self._dev.Content()
        self._storage = self._main_storage()

    def close(self):
        try:
            self._dev.Close()
        except Exception:
            pass

    # helpers
    def _key(self, fmtid, pid):
        comtypes, _cc, port, _types = self._lib
        k = port._tagpropertykey()
        k.fmtid, k.pid = comtypes.GUID(fmtid), pid
        return k

    def _values(self):
        comtypes, cc, port, types = self._lib
        return cc.CreateObject(types.PortableDeviceValues, clsctx=comtypes.CLSCTX_INPROC_SERVER,
                               interface=port.IPortableDeviceValues)

    def _children(self, parent):
        import ctypes
        from ctypes import POINTER, byref, c_ulong, c_wchar_p
        en = self._content.EnumObjects(0, parent, None)
        out = []
        while True:
            ids = (c_wchar_p * 64)()
            got = c_ulong(0)
            en._IEnumPortableDeviceObjectIDs__com_Next(64, ctypes.cast(ids, POINTER(c_wchar_p)), byref(got))
            if not got.value:
                return out
            out += [ids[i] for i in range(got.value)]

    def _props(self, oid):
        v = self._content.Properties().GetValues(oid, None)

        def get(how, key):
            try:
                return how(key)
            except Exception:
                return None
        name = get(v.GetStringValue, self._key(_OBJ, 12)) or get(v.GetStringValue, self._key(_OBJ, 4)) or ""
        kind = str(get(v.GetGuidValue, self._key(_OBJ, 7)) or "").upper()
        return {"id": oid, "name": name, "folder": kind in _FOLDER_TYPES,
                "size": get(v.GetUnsignedLargeIntegerValue, self._key(_OBJ, 11))}

    def _main_storage(self):
        """The storage with the most room (a Pixel has one, 'Internal shared storage')."""
        best, room = None, -1
        for sid in self._children("DEVICE"):
            cap = self._storage_value(sid, 4) or 0
            if cap > room:
                best, room = sid, cap
        if best is None:
            raise RuntimeError(t("{phone} shows no storage. Unlock it and choose File Transfer on its USB "
                                 "notification.", phone=self.name))
        return best

    def _storage_value(self, sid, pid):
        try:
            v = self._content.Properties().GetValues(sid, None)
            return v.GetUnsignedLargeIntegerValue(self._key(_STORAGE, pid))
        except Exception:
            return None

    # what copy_playlist uses
    def free(self):
        return self._storage_value(self._storage, 5) or 0

    def capacity(self):
        return self._storage_value(self._storage, 4) or 0

    def list(self, parent):
        return [self._props(c) for c in self._children(parent)]

    def child(self, parent, name):
        return next((e["id"] for e in self.list(parent) if e["name"].lower() == name.lower()), None)

    def folder(self, path, make=False):
        """The folder at a path from the main storage ('Music', 'Music/Jo'), made if make, else None if missing."""
        here = self._storage
        for part in [p for p in re.split(r"[\\/]+", path or "") if p]:
            found = self.child(here, part)
            if found is None:
                if not make:
                    return None
                found = self.make(here, part)
            here = found
        return here

    def make(self, parent, name):
        from ctypes import byref, c_wchar_p
        comtypes = self._lib[0]
        v = self._values()
        v.SetStringValue(self._key(_OBJ, 3), parent)
        v.SetStringValue(self._key(_OBJ, 4), name)
        v.SetStringValue(self._key(_OBJ, 12), name)
        v.SetGuidValue(self._key(_OBJ, 7), comtypes.GUID(_FOLDER_TYPES[0]))
        v.SetGuidValue(self._key(_OBJ, 6), comtypes.GUID("{30010000-AE6C-4804-98BA-C57B46965FE7}"))
        oid = c_wchar_p()
        self._content._IPortableDeviceContent__com_CreateObjectWithPropertiesOnly(v, byref(oid))
        return oid.value

    def _write(self, parent, name, size, chunks):
        import ctypes
        from ctypes import POINTER, byref, c_ulong, c_wchar_p
        comtypes, _cc, port, _types = self._lib
        v = self._values()
        v.SetStringValue(self._key(_OBJ, 3), parent)
        v.SetStringValue(self._key(_OBJ, 4), name)
        v.SetStringValue(self._key(_OBJ, 12), name)
        v.SetUnsignedLargeIntegerValue(self._key(_OBJ, 11), size)
        v.SetGuidValue(self._key(_OBJ, 7), comtypes.GUID("{0085E0A6-8D34-45D7-BC5C-447E59C73D48}"))
        v.SetGuidValue(self._key(_OBJ, 6), comtypes.GUID("{30000000-AE6C-4804-98BA-C57B46965FE7}"))
        best, cookie, stream = c_ulong(0), c_wchar_p(), POINTER(port.IStream)()
        self._content._IPortableDeviceContent__com_CreateObjectWithPropertiesAndData(v, byref(stream), byref(best),
                                                                                    byref(cookie))
        for data in chunks(max(best.value, 256 * 1024)):
            buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
            stream._ISequentialStream__com_RemoteWrite(buf, len(data), byref(c_ulong(0)))
        stream.Commit(0)

    def put(self, parent, path, name, size):
        def chunks(n):
            with open(path, "rb") as f:
                while True:
                    data = f.read(n)
                    if not data:
                        return
                    yield data
        self._write(parent, name, size, chunks)

    def put_text(self, parent, name, text):
        data = text.encode("utf-8")
        self._write(parent, name, len(data), lambda n: (data[i:i + n] for i in range(0, len(data), n)))

    def read(self, oid):
        """A file's bytes (a playlist file, for the tidy-up), through the default resource's stream."""
        import ctypes
        from ctypes import POINTER, byref, c_ulong
        comtypes, _cc, port, _types = self._lib
        best, stream = c_ulong(0), POINTER(port.IStream)()
        key = self._key("{E81E79BE-34F0-41BF-B53F-F1A06AE87842}", 0)   # WPD_RESOURCE_DEFAULT
        self._content.Transfer()._IPortableDeviceResources__com_GetStream(oid, byref(key), 0, byref(best),
                                                                          byref(stream))
        out, n = bytearray(), max(best.value, 64 * 1024)
        while True:
            buf = (ctypes.c_ubyte * n)()
            got = c_ulong(0)
            stream._ISequentialStream__com_RemoteRead(buf, n, byref(got))
            if not got.value:
                return bytes(out)
            out += bytes(buf[:got.value])

    def delete(self, ids):
        """Gone, folders with all they hold (recursively, with no prompt on the phone)."""
        from ctypes import POINTER
        comtypes, cc, port, types = self._lib
        coll = cc.CreateObject(types.PortableDevicePropVariantCollection, clsctx=comtypes.CLSCTX_INPROC_SERVER,
                               interface=port.IPortableDevicePropVariantCollection)
        v, key = self._values(), self._key(_OBJ, 2)
        for oid in ids:
            v.SetStringValue(key, oid)
            coll.Add(v.GetValue(key))
        self._content._IPortableDeviceContent__com_Delete(1, coll, POINTER(POINTER(
            port.IPortableDevicePropVariantCollection))())
