"""
24bit7 - Copy Tracks To: a saved playlist's tracks copied to a phone (Ben, 23 Nov 2026).

Ben and Jo build playlists in 24bit7 and want them on their phones (both Google Pixels) without fluffing about in
JRiver. Save Playlist's pop-up has a Copy Tracks To tick: the phone (named as you like, "Ben's Phone", told apart by
Windows' device id, which carries the serial, so two of the same phone keep their own names), the folder on it
(Music to start), a limit in GB, and Clear Playlists First. Since 1.44.0 (Ben, 25 Nov 2026) the folder holds two:
Albums, artist and album folders added from the Devices tab, and Playlists, flat, each song named "Artist - Title"
beside the .m3u8s that list them, so the phone's player shows each as a playlist. Clear Playlists First clears
Playlists only. What 1.43 left at the top of the folder is sorted into the two once, the first time it's used.

A phone over USB has no drive letter: it's reached through Windows Portable Devices (WPD), here through comtypes.
Proved on Ben's Pixel 9a on 23 Nov 2026: a folder made, files written (37 MB a second), a recursive delete with
no prompt. Everything below WpdPhone works against any object with the same few methods, so the tests use a fake.

Rules:
- Clear First empties Playlists (asked once, with the count), never Albums, but keeps what the new playlist lists
  at the same place and size, so nothing is copied back (24 Nov 2026).
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
            app_id = (_decode(p.read(mark)).strip().splitlines() or [""])[0].strip() if mark is not None else ""
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


def playlist_names(tracks):
    """
    One file name per track in Playlists (Ben, 25 Nov 2026: Playlists is flat, Albums keeps the folders):
    'Artist - Title.flac'. Two that would share a name get a number ('Intro (2).flac'); the same track gets the
    same name on every save, so only new ones are copied, and a song on two playlists is one file.
    """
    seen, out = set(), []
    for tr in tracks:
        ext = os.path.splitext(tr["path"])[1].lower()
        artist = tr.get("artist") or tr.get("album_artist") or t("Unknown Artist")
        title = tr.get("title") or os.path.splitext(os.path.basename(tr["path"]))[0]
        base = safe_name(f"{artist} - {title}")
        name, n = base + ext, 1
        while name.lower() in seen:
            n += 1
            name = f"{base} ({n}){ext}"
        seen.add(name.lower())
        out.append(name)
    return out


def m3u8_text(paths):
    """The playlist file, in Playlists: the tracks in order, by their paths from there."""
    return "#EXTM3U\n" + "".join(p + "\n" for p in paths)


ALBUMS, PLAYLISTS = "Albums", "Playlists"   # the two folders inside the chosen one (Ben, 25 Nov 2026)


def _fkey(folder):
    return re.sub(r"[\\/]+", "/", folder or "").strip("/").lower()


def _lists_key(folder):
    """The key Playlists' records are kept under: the chosen folder's, with /playlists."""
    return _fkey(folder) + "/" + PLAYLISTS.lower()


def sub(folder, name):
    """A folder inside the chosen one: 'Music/Playlists'."""
    return f"{(folder or '').rstrip(chr(92) + '/')}/{name}" if folder else name


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


def _wanted(paths, tracks):
    """{path.lower(): size} of what the playlist puts in the folder, and the folders those paths run through."""
    wanted = {p.lower(): tr["size"] for tr, p in zip(tracks, paths)}
    through = {p.rsplit("/", i)[0] for p in wanted for i in range(1, p.count("/") + 1)}
    return wanted, through


def _clear_plan(dirs, wanted, through, skip, start=""):
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
    if start:
        dirs.get(start)
    visit(start)
    return whole, files, kept


def clear_plan(phone, folder, playlist, tracks):
    """What Clear Playlists First would do to Playlists, for the question asked once: (folders, files, tracks
    kept). Albums is never touched."""
    root = phone.folder(folder, make=False)
    if root is None:
        return 0, 0, 0
    dirs = _Dirs(phone, root)
    if dirs.get(PLAYLISTS) is None:
        return 0, 0, 0
    paths = [f"{PLAYLISTS}/{n}" for n in playlist_names(tracks)]
    wanted, through = _wanted(paths, tracks)
    whole, files, kept = _clear_plan(dirs, wanted, through, f"{PLAYLISTS}/{safe_name(playlist)}.m3u8".lower(),
                                     start=PLAYLISTS)
    return len(whole), len(files), kept


def _exists(dirs, rel):
    d, _, name = rel.rpartition("/")
    return name.lower() in dirs.listing(d)


def _decode(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _relative(line, base=""):
    """
    A playlist line as a path inside the chosen folder ('Albums/Seether/Disclaimer II/03 Broken.flac'), read from
    the folder the playlist is in (base: 'Playlists'), so '../Albums/...' works. None for a line with a drive, a
    web address or a path above the chosen folder, which 24bit7 never judges.
    """
    rel = line.strip().replace("\\", "/")
    if not rel or ":" in rel or rel.startswith("/"):
        return None
    parts = [p for p in base.split("/") if p]
    for part in rel.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts) or None


def _tidy_playlists(phone, dirs, base, mine, skip, say):
    """
    Every other playlist file in Playlists (base), checked against what's there (Ben, 24 Nov 2026): a song no
    longer in the folder comes out of its list, and a playlist left with none goes. 24bit7's own are read from
    what it kept (names in Playlists); any other is read off the phone, and only lines that name a file in the
    chosen folder are judged (a line with a drive, a web address or a path above it stays as it is). Returns how
    many were changed.
    """
    changed = 0
    root = dirs.get(base)
    if root is None:
        return 0
    for low, e in sorted(dirs.listing(base).items()):
        if low == skip or low.startswith(".") or not low.endswith((".m3u8", ".m3u")):
            continue
        recorded = mine.get(low)
        if recorded is not None:
            keep = [p for p in recorded if _exists(dirs, f"{base}/{p}")]
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
                rel = _relative(s, base)
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
        dirs.files[base].pop(low, None)
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
        """An album or artist folder left with nothing in it goes too (its parent next, up to Albums or Playlists,
        which stay)."""
        while rel and rel.lower() not in (ALBUMS.lower(), PLAYLISTS.lower()):
            fid = self.get(rel)
            if fid is None or self.phone.list(fid):
                return
            self.phone.delete([fid])
            self.forget(rel)
            rel = rel.rpartition("/")[0]


def _albums_count(dirs):
    """How many album folders Albums holds (artist/album), for the Clear line."""
    if dirs.get(ALBUMS) is None:
        return 0
    dirs._list(ALBUMS)
    n = 0
    for low, real in list(dirs.names[ALBUMS].items()):
        if real.startswith("."):
            continue
        rel = f"{ALBUMS}/{real}"
        dirs.ids.setdefault(rel, dirs.kids[ALBUMS][low])
        dirs._list(rel)
        subs = [r for r in dirs.names[rel].values() if not r.startswith(".")]
        n += len(subs) or 1
    return n


def _move(phone, dirs, src_dir, e, dst_dir, name):
    """One file to another folder under the chosen one: the device's own move where it has one (This PC), else
    read, written again and the old one deleted (a phone: the app and Windows' portable devices have no move)."""
    parent = dirs.get(dst_dir, make=True)
    hook = getattr(dirs, "on_move", None)
    if hook is not None:
        hook()
    if hasattr(phone, "move"):
        phone.move(e["id"], parent, name)
    else:
        import tempfile
        data = phone.read(e["id"])
        fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(name)[1])
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            phone.put(parent, tmp, name, len(data))
        finally:
            os.remove(tmp)
        phone.delete([e["id"]])
    dirs.files[src_dir].pop(e["name"].lower(), None)
    dirs.listing(dst_dir)[name.lower()] = {"id": None, "name": name, "folder": False, "size": e.get("size")}


def _move_tree(phone, dirs, src, dst):
    """A folder and all it holds to dst, merged with one already there. Returns how many files moved."""
    if hasattr(phone, "move") and dirs.get(dst) is None:
        parent_rel, _, name = dst.rpartition("/")
        phone.move(dirs.get(src), dirs.get(parent_rel, make=True), name)
        dirs.forget(src)
        dirs.forget(dst)
        return 1
    moved = 0
    dirs._list(src)
    for low, real in sorted(dirs.names[src].items()):
        dirs.ids.setdefault(f"{src}/{real}", dirs.kids[src][low])
        moved += _move_tree(phone, dirs, f"{src}/{real}", f"{dst}/{real}")
    for low, e in sorted(dirs.files[src].items()):
        _move(phone, dirs, src, e, dst, e["name"])
        moved += 1
    fid = dirs.get(src)
    if fid is not None and not phone.list(fid):
        phone.delete([fid])
        dirs.forget(src)
    return moved


def _flat_name(path, taken):
    """'The Doors/L.A. Woman/03 Love Her Madly.flac' as 'The Doors - Love Her Madly.flac', numbered if taken."""
    folder, _, fname = path.rpartition("/")
    base, ext = os.path.splitext(fname)
    title = re.sub(r"^\d+(-\d+)?\s+", "", base) or base
    artist = path.split("/")[0] if folder else ""
    stem = safe_name(f"{artist} - {title}" if artist else title)
    name, n = stem + ext.lower(), 1
    while name.lower() in taken:
        n += 1
        name = f"{stem} ({n}){ext.lower()}"
    taken.add(name.lower())
    return name


def _arranged(phone, folder):
    entry = _meta(META_KEY, {}).get(key_for(getattr(phone, "id", None) or phone.name)) or {}
    return _fkey(folder) in (entry.get("arranged") or [])


def arrange(phone, folder, say=print, progress=None):
    """
    Once per device and folder (Ben, 25 Nov 2026): the folder as it was before 1.44 sorted into Albums and
    Playlists. What 24bit7's records say it copied for playlists goes into Playlists, one flat folder ('Artist -
    Title.flac'), the playlists rewritten to match; any other playlist file goes there too, its lines now pointing
    into Albums; every other folder at the top (artists, albums) and loose track goes into Albums. Nothing is
    deleted but folders left empty. Returns how many files moved. progress, if given, is called with (files moved,
    files to move) as each file goes, where files go one at a time (a phone over WiFi: read and written again,
    which took Jo's 84 files about half an hour, 25 Nov 2026), so the Devices tab can say how far it's got.
    """
    device = key_for(getattr(phone, "id", None) or phone.name)
    every = _meta(META_KEY, {})
    entry = dict(every.get(device) or {})
    fkey = _fkey(folder)
    if fkey in (entry.get("arranged") or []):
        return 0
    root = phone.folder(folder, make=False)
    moved, lists_moved, albums_moved = 0, 0, 0
    copied = dict(entry.get("copied") or {})
    old = dict(copied.pop(fkey, None) or {})
    if root is not None:
        dirs = _Dirs(phone, root)
        dirs._list("")
        keep = (ALBUMS.lower(), PLAYLISTS.lower())
        tops = [real for low, real in sorted(dirs.names[""].items()) if not real.startswith(".") and low not in keep]
        loose = [e for low, e in sorted(dirs.files[""].items()) if not e["name"].startswith(".")]
        if tops or loose or old:
            say("  " + t("Sorting {folder} on {phone} into Albums and Playlists, once...", folder=folder,
                         phone=phone.name))
            if progress is not None and not hasattr(phone, "move"):
                count = sum(1 for p in Folder(phone, folder).files if p.split("/")[0] not in keep)
                done = [0]

                def moved_one():
                    done[0] += 1
                    progress(min(done[0], count), count)
                dirs.on_move = moved_one
                progress(0, count)
        if dirs.get(PLAYLISTS) is not None:
            dirs._list(PLAYLISTS)
        taken_names = set(dirs.listing(PLAYLISTS)) if dirs.get(PLAYLISTS) is not None else set()
        new_name = {}   # old path.lower(): its name in Playlists
        lists = dict(copied.get(_lists_key(folder)) or {})
        for m3u_low, paths in sorted(old.items()):
            names = []
            for p in paths:
                if p.lower() in new_name:
                    names.append(new_name[p.lower()])
                    continue
                d, _, fname = p.rpartition("/")
                e = dirs.listing(d).get(fname.lower())
                if not e or not d:
                    continue
                name = _flat_name(p, taken_names)
                _move(phone, dirs, d, e, PLAYLISTS, name)
                new_name[p.lower()] = name
                names.append(name)
                moved += 1
            e = dirs.files[""].get(m3u_low)
            if e is not None:
                phone.delete([e["id"]])
                dirs.files[""].pop(m3u_low, None)
                loose = [x for x in loose if x["name"].lower() != m3u_low]
            if names:
                phone.put_text(dirs.get(PLAYLISTS, make=True), (e or {}).get("name") or m3u_low, m3u8_text(names))
                dirs.listing(PLAYLISTS)[m3u_low] = {"id": None, "name": (e or {}).get("name") or m3u_low,
                                                    "folder": False, "size": None}
                lists[m3u_low] = names
                lists_moved += 1
        for d in sorted({p.rpartition("/")[0] for p in new_name if "/" in p}, key=lambda d: -d.count("/")):
            while d:   # artist and album folders the playlists' tracks left empty
                fid = dirs.get(d)
                if fid is None or phone.list(fid):
                    break
                phone.delete([fid])
                dirs.forget(d)
                d = d.rpartition("/")[0]
        for e in loose:
            low = e["name"].lower()
            if low.endswith((".m3u8", ".m3u")):
                try:
                    lines = _decode(phone.read(e["id"])).splitlines()
                except Exception as err:
                    engine.debug(f"Copy Tracks To: couldn't read {e['name']} ({err})")
                    continue
                out = []
                for line in lines:
                    s = line.strip()
                    rel = None if not s or s.startswith("#") else _relative(s)
                    if rel is None:
                        out.append(line)
                    elif rel.lower() in new_name:
                        out.append(new_name[rel.lower()])
                    else:
                        out.append(f"../{ALBUMS}/{rel}")
                phone.delete([e["id"]])
                dirs.files[""].pop(low, None)
                phone.put_text(dirs.get(PLAYLISTS, make=True), e["name"], "\n".join(out) + "\n")
                lists_moved += 1
            elif is_track(low):
                _move(phone, dirs, "", e, ALBUMS, e["name"])
                moved += 1
        dirs.names.pop("", None)
        dirs.kids.pop("", None)
        dirs.files.pop("", None)
        dirs._list("")
        for low, real in sorted(dirs.names[""].items()):
            if real.startswith(".") or low in keep:
                continue
            dirs.ids.setdefault(real, dirs.kids[""][low])
            moved += _move_tree(phone, dirs, real, f"{ALBUMS}/{real}")
            albums_moved += 1
        copied[_lists_key(folder)] = lists
        if tops or loose or old:
            parts = []
            if albums_moved:
                parts.append(tn("{count} folder into Albums", "{count} folders into Albums", albums_moved))
            if lists_moved:
                parts.append(tn("{count} playlist into Playlists", "{count} playlists into Playlists", lists_moved))
            say("  " + (t("Sorted {folder} on {phone}: {what}.", folder=folder, phone=phone.name,
                          what=names_text(parts)) if parts else
                        t("Sorted {folder} on {phone}.", folder=folder, phone=phone.name)))
    every = _meta(META_KEY, {})
    if device not in every and getattr(phone, "id", None) is not None and is_wifi(device):
        return moved   # forgotten while it was being sorted: not put back
    entry = dict(every.get(device) or {})
    entry["copied"] = copied
    entry["arranged"] = sorted(set(entry.get("arranged") or []) | {fkey})
    every[device] = entry
    _set_meta(META_KEY, every)
    return moved


def copy_playlist(phone, folder, playlist, tracks, limit_gb=0, clear=False, say=print, progress=None, stop=None):
    """
    Copies tracks (from tracks_for) into Playlists in the chosen folder on the phone (Ben, 25 Nov 2026: one flat
    folder, 'Artist - Title.flac'), with playlist.m3u8 beside them listing them in order. Albums is never touched:
    Clear Playlists First clears Playlists only. Returns how many tracks the .m3u8 lists.
    progress, if given, is called with a dict as each track starts and once at the end ("state" copying, done or
    stopped, "done" and "count" tracks, "bytes" and "total", "track", and at the end "line" and "note").
    stop, if given, is asked before each track: True stops there, the .m3u8 listing what's on the phone.
    """
    started = time.time()
    root = phone.folder(folder, make=True)
    arrange(phone, folder, say)
    device, copied = _records(phone)
    lkey = _lists_key(folder)
    mine = dict(copied.get(lkey) or {})
    dirs = _Dirs(phone, root)
    dirs.get(PLAYLISTS, make=True)
    where = sub(folder, PLAYLISTS)
    own = safe_name(playlist)
    m3u = own + ".m3u8"
    pkey = m3u.lower()
    names = playlist_names(tracks)
    paths = [f"{PLAYLISTS}/{n}" for n in names]
    if clear:
        wanted, through = _wanted(paths, tracks)
        whole, loose, held = _clear_plan(dirs, wanted, through, f"{PLAYLISTS}/{m3u}".lower(), start=PLAYLISTS)
        ids = [dirs.get(rel) for rel in whole] + [e["id"] for _rel, e in loose]
        if ids:
            phone.delete([i for i in ids if i is not None])
        for rel in whole:
            dirs.forget(rel)
        for rel, e in loose:
            dirs.files[rel].pop(e["name"].lower(), None)
        if whole or loose:
            lists = sorted((e["name"].rsplit(".", 1)[0] for _rel, e in loose
                            if e["name"].lower().endswith((".m3u8", ".m3u"))), key=str.lower)
            gone = [e for _rel, e in loose if is_track(e["name"])]
            size = size_text(sum(e.get("size") or 0 for e in gone))
            what = (tn("{names}, {count} track ({size})", "{names}, {count} tracks ({size})", len(gone),
                       names=names_text(lists), size=size) if lists else
                    tn("{count} track ({size})", "{count} tracks ({size})", len(gone), size=size))
            albums = _albums_count(dirs)
            say("  " + t("Cleared Playlists on {phone}: {what}.", phone=phone.name, what=what)
                + (" " + tn("Your {count} album left alone.", "Your {count} albums left alone.", albums)
                   if albums else ""))
        mine = {}
    stale = [p for p in mine.get(pkey, []) if p.lower() not in {n.lower() for n in names}
             and p.lower() not in {q.lower() for k, ps in mine.items() if k != pkey for q in ps}]
    removed = 0
    for p in stale:
        e = dirs.listing(PLAYLISTS).get(p.lower())
        if e:
            phone.delete([e["id"]])
            dirs.files[PLAYLISTS].pop(p.lower(), None)
            removed += 1
    if removed:
        say("  " + tn("Took out {count} track no longer in the playlist.",
                      "Took out {count} tracks no longer in the playlist.", removed))
    # what fits: the limit and the phone's free space, filled in playlist order
    here = dirs.listing(PLAYLISTS)
    on_phone = {p: here.get(n.lower()) for p, n in zip(paths, names)}
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
        say("  " + tn("Copying {count} track ({size}) into {folder} on {phone}...",
                      "Copying {count} tracks ({size}) into {folder} on {phone}...",
                      len(todo), size=size_text(total), folder=where, phone=phone.name))
        if kept:
            say("  " + tn("{count} already there, kept.", "{count} already there, kept.", len(kept)))
    done_bytes, stopped = 0, False
    parent = dirs.get(PLAYLISTS)
    for i, (tr, p, already) in enumerate(todo, 1):
        if stop is not None and stop():
            stopped = True
            break
        if progress is not None:
            progress({"state": "copying", "done": len(kept), "count": count, "bytes": done_bytes, "total": total,
                      "track": f"{tr.get('artist') or ''} - {tr.get('title') or ''}".strip(" -")})
        name = p.rpartition("/")[2]
        if already is not None:   # a different size: a newer file of the same track
            phone.delete([already["id"]])
        phone.put(parent, tr["path"], name, tr["size"])
        here[name.lower()] = {"id": None, "name": name, "folder": False, "size": tr["size"]}
        kept.add(p)
        done_bytes += tr["size"]
        if i == len(todo) or i % 10 == 0:
            say("  " + t("Copied {done} of {count} ({size}).", done=i, count=len(todo), size=size_text(done_bytes)))
    listed = [p.rpartition("/")[2] for p in paths if p in kept]
    old_m3u = here.get(pkey)
    if old_m3u is not None and old_m3u.get("id") is not None:
        phone.delete([old_m3u["id"]])
    if tracks:
        phone.put_text(parent, m3u, m3u8_text(listed))
        mine[pkey] = listed
    else:   # a playlist emptied in JRiver and saved again: it comes off (Ben, 24 Nov 2026)
        mine.pop(pkey, None)
        here.pop(pkey, None)
    if not clear:
        _tidy_playlists(phone, dirs, PLAYLISTS, mine, pkey, say)
    copied[lkey] = mine
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
                  phone=phone.name, folder=where, name=own, secs=secs)
    else:   # saved again with nothing new: only the .m3u8 was written
        line = tn("Already on {phone}: {count} track in {folder}, with {name}.m3u8.",
                  "Already on {phone}: {count} tracks in {folder}, with {name}.m3u8.", len(listed),
                  phone=phone.name, folder=where, name=own)
    say(line)
    if progress is not None:
        progress({"state": "stopped" if stopped else "done", "done": len(listed), "count": count,
                  "bytes": done_bytes, "total": total, "track": "", "line": line, "note": note, "secs": secs})
    return len(listed)


def add_albums(phone, folder, tracks, say=print, progress=None, stop=None, what=""):
    """
    The Devices tab's Add (Ben, 25 Nov 2026): tracks copied into Albums, each in its artist's and album's folders,
    no playlist file; what's there already at the same size is kept. what names it for the console ('L.A. Woman',
    '2 tracks of L.A. Woman'). Returns how many are now there.
    """
    started = time.time()
    root = phone.folder(folder, make=True)
    arrange(phone, folder, say)
    dirs = _Dirs(phone, root)
    paths = [f"{ALBUMS}/{p}" for p in file_names(tracks)]
    room = phone.free() - SPARE
    todo, kept, left_out = [], 0, []
    for tr, p in zip(tracks, paths):
        d, _, name = p.rpartition("/")
        already = dirs.listing(d).get(name.lower())
        if already is not None and already.get("size") in (None, tr["size"]):
            kept += 1
        elif tr["size"] > room:
            left_out.append(tr)
        else:
            room -= tr["size"]
            todo.append((tr, p, already))
    total = sum(tr["size"] for tr, _, _ in todo)
    done_bytes, stopped, done = 0, False, 0
    for i, (tr, p, already) in enumerate(todo, 1):
        if stop is not None and stop():
            stopped = True
            break
        if progress is not None:
            progress({"state": "copying", "done": kept + i - 1, "count": kept + len(todo), "bytes": done_bytes,
                      "total": total, "track": f"{tr.get('artist') or ''} - {tr.get('title') or ''}".strip(" -")})
        d, _, name = p.rpartition("/")
        parent = dirs.get(d, make=True)
        if already is not None:
            phone.delete([already["id"]])
        phone.put(parent, tr["path"], name, tr["size"])
        dirs.listing(d)[name.lower()] = {"id": None, "name": name, "folder": False, "size": tr["size"]}
        done_bytes += tr["size"]
        done = i
    secs = round(time.time() - started)
    what = what or tn("{count} track", "{count} tracks", len(tracks))
    note = ""
    if left_out:
        note = tn("Note: {count} track ({size}) didn't fit in the phone's free space, so it was left out.",
                  "Note: {count} tracks ({size}) didn't fit in the phone's free space, so they were left out.",
                  len(left_out), size=size_text(sum(tr["size"] for tr in left_out)))
        say("  " + note)
    if stopped:
        line = t("Stopped: {count} of {total} tracks of {what} are on {phone}.", count=kept + done,
                 total=kept + len(todo), what=what, phone=phone.name)
    elif todo:
        line = t("Added {what} to {folder} on {phone} ({size}, {secs} s).", what=what, folder=sub(folder, ALBUMS),
                 phone=phone.name, size=size_text(done_bytes), secs=secs)
    else:
        line = t("{what} is already on {phone}.", what=what, phone=phone.name)
    say(line)
    if progress is not None:
        progress({"state": "stopped" if stopped else "done", "done": kept + done, "count": kept + len(todo),
                  "bytes": done_bytes, "total": total, "track": "", "line": line, "note": note, "secs": secs})
    return kept + done


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
    The Devices tab's picture of the folder copied to (Ben, 25 Nov 2026, as drawn; Manage Folder's until then),
    read once: its playlists (the .m3u8 and .m3u files in Playlists, each with the songs it lists that are there),
    and every file under it, by folder, so artists, albums and tracks in Albums can be ticked and deleted. Paths
    are from the chosen folder ('Albums/Seether/...', 'Playlists/Seether - Broken.flac'). Dot folders and files
    (.thumbnails, .24bit7) are left out, as they are never touched.
    """

    def __init__(self, phone, folder):
        self.phone, self.folder = phone, folder
        self.root = phone.folder(folder, make=False)
        self.device, self.copied = _records(phone)
        self.lkey = _lists_key(folder)
        self.mine = dict(self.copied.get(self.lkey) or {})
        self.dirs = _Dirs(phone, self.root) if self.root is not None else None
        self.files = {}     # path.lower(): {"rel", "size", "id"}
        self.folders = {}   # path.lower(): path, every folder under the chosen one
        self.playlists = []
        self.lists_of = {}  # path.lower(): [the names of the playlists listing it]
        if self.root is None:
            return
        self._walk("")
        here = self.dirs.listing(PLAYLISTS) if self.dirs.get(PLAYLISTS) is not None else {}
        for low, e in sorted(here.items()):
            if low.startswith(".") or not low.endswith((".m3u8", ".m3u")):
                continue
            recorded = self.mine.get(low)
            try:
                listed = ([f"{PLAYLISTS}/{n}" for n in recorded] if recorded is not None else
                          [r for r in (_relative(x, PLAYLISTS) for x in _decode(phone.read(e["id"])).splitlines()
                                       if x.strip() and not x.strip().startswith("#")) if r])
            except Exception as err:
                engine.debug(f"Manage Folder: couldn't read {e['name']} ({err})")
                listed = []
            paths = list(dict.fromkeys(p.lower() for p in listed if p.lower() in self.files))
            self.playlists.append({"name": e["name"].rsplit(".", 1)[0], "low": low, "id": e["id"], "paths": paths,
                                   "tracks": sum(is_track(p) for p in paths),
                                   "size": sum(self.files[p]["size"] for p in paths)})
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
            if e["name"].startswith(".") or (rel.lower() == PLAYLISTS.lower() and low.endswith((".m3u8", ".m3u"))):
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

    def tree(self, start=ALBUMS):
        """
        Artists and albums: [node] for the folders in Albums (artists), each with its folders (albums) and files
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
        return children(start) if start.lower() in self.folders or not start else []

    def plan(self, playlists=(), folders=(), files=(), songs=()):
        """
        What deleting the ticked would do (Ben, 24 Nov 2026, as drawn): a playlist ticked takes its file and the
        songs in Playlists no other playlist lists (never anything in Albums); an album or artist ticked goes whole,
        and every playlist listing its songs is amended (taken off if none are left); a song ticked under a playlist
        (songs: [(playlist, path)]) comes out of that one. {"playlists": [low], "folders": [rel], "files":
        {path.lower()}, "loose": [path.lower()] deleted one by one, "tracks", "size", "amended": [names], "kept":
        songs of a ticked playlist staying because another lists them, "unlist": {playlist: paths} taken out of a
        playlist but kept}.
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
        kept, flat = set(), PLAYLISTS.lower() + "/"
        for pl in self.playlists:
            if pl["low"] in ticked:
                going |= {p for p in pl["paths"] if p not in still and p.startswith(flat)}
                kept |= {p for p in pl["paths"] if p in still and p not in going}
        # a song ticked under a playlist (Ben, 25 Nov 2026): out of that playlist; its file goes only if it's in
        # Playlists and no other playlist left lists it
        unlist = {}
        for low, path in songs:
            path = path.lower()
            if low in ticked or path not in self.files or path in going:
                continue
            unlist.setdefault(low, set()).add(path)
        for low, paths in unlist.items():
            for path in paths:
                others = [pl for pl in self.playlists if pl["low"] != low and pl["low"] not in ticked
                          and path in pl["paths"] and path not in unlist.get(pl["low"], ())]
                if not others and path.startswith(flat):
                    going.add(path)
        unlist = {low: paths - going for low, paths in unlist.items() if paths - going}
        loose = sorted(p for p in going if not any(p.startswith(w.lower() + "/") for w in whole))
        amended = [pl["name"] for pl in self.playlists if pl["low"] not in ticked
                   and (pl["low"] in unlist or any(p in going for p in pl["paths"]))]
        return {"playlists": [pl["low"] for pl in self.playlists if pl["low"] in ticked], "folders": whole,
                "files": going, "loose": loose, "tracks": sum(is_track(p) for p in going),
                "size": sum(self.files[p]["size"] for p in going), "amended": amended, "kept": len(kept),
                "unlist": unlist}

    def plan_text(self, plan, what):
        """The amber line above Delete: what goes, said before it does, so no further question is asked."""
        unlist = plan.get("unlist") or {}
        if not plan["playlists"] and not plan["files"] and not unlist:
            return ""
        what = dict(what=what, phone=self.phone.name, size=size_text(plan["size"]),
                    tracks=tn("{count} track", "{count} tracks", plan["tracks"]), lists=names_text(plan["amended"]))
        if not plan["files"] and not plan["playlists"]:
            return t("Deleting {what} takes it out of {lists}. The songs stay on {phone}, as other playlists list "
                     "them.", **what)
        if not plan["files"]:
            return tn("Deleting {what} takes the playlist off {phone}. Its songs stay, as other playlists list them.",
                      "Deleting {what} takes the playlists off {phone}. Their songs stay, as other playlists list "
                      "them.", len(plan["playlists"]), **what)
        if plan["amended"]:
            return t("Deleting {what} takes {tracks} ({size}) off {phone} and out of {lists}.", **what)
        line = t("Deleting {what} takes {tracks} ({size}) off {phone}.", **what)
        if self.playlists and all(p.startswith(ALBUMS.lower() + "/") for p in plan["files"]):
            line += " " + t("Your playlists don't use them.")
        return line

    def _unlist(self, pl, paths, say):
        """Songs taken out of one playlist whose files stay (another playlist lists them, or they're in Albums)."""
        for cache in (self.dirs.kids, self.dirs.files, self.dirs.names):   # the tidy-up may have rewritten it
            cache.pop(PLAYLISTS, None)
        here = self.dirs.listing(PLAYLISTS)
        e = here.get(pl["low"])
        if e is None:
            return
        recorded = self.mine.get(pl["low"])
        if recorded is not None:
            keep = [n for n in recorded if f"{PLAYLISTS}/{n}".lower() not in paths]
            text = m3u8_text(keep)
        else:
            try:
                lines = _decode(self.phone.read(e["id"])).splitlines()
            except Exception as err:
                engine.debug(f"Devices: couldn't read {e['name']} ({err})")
                return
            out, pending = [], []
            for line in lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    pending.append(line)
                    continue
                rel = _relative(s, PLAYLISTS)
                if rel is not None and rel.lower() in paths:
                    out += [p for p in pending if not p.strip().upper().startswith("#EXTINF")]
                else:
                    out += pending + [line]
                pending = []
            text = "\n".join(out + pending) + "\n"
            keep = None
        self.phone.delete([e["id"]])
        self.phone.put_text(self.dirs.get(PLAYLISTS), e["name"], text)
        if keep is not None:
            self.mine[pl["low"]] = keep
        say("  " + tn("Took {count} song out of {name}.", "Took {count} songs out of {name}.", len(paths),
                      name=pl["name"]))

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
            self.dirs.files.get(PLAYLISTS, {}).pop(low, None)
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
        _tidy_playlists(self.phone, self.dirs, PLAYLISTS, self.mine, None, say)
        for low, paths in (plan.get("unlist") or {}).items():
            self._unlist(by_name[low], paths, say)
        self.copied[self.lkey] = self.mine
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


def known():
    """
    The Devices tab's devices (Ben, 25 Nov 2026): [(device id, model, kind, here)], kind "usb", "wifi" or "pc".
    The phones plugged in (here), then every other phone 24bit7 remembers, by WiFi or not plugged in, then This PC
    once a folder on it has been copied to. A WiFi phone's here is None: whether it answers is asked on a thread.
    """
    out, seen = [], set()
    for device_id, model in devices():
        out.append((device_id, model, "usb", True))
        seen |= {device_id, _link_usb(device_id, model)}
    every = _meta(META_KEY, {})
    for key, entry in every.items():
        if key in seen or key == PC or not isinstance(entry, dict):
            continue
        wifi = is_wifi(key)   # one kept without its code is still a WiFi phone: Type Its Code... reconnects it
        out.append((key, entry.get("model") or "", "wifi" if wifi else "usb",
                    None if wifi and entry.get("code") else False))
    if (every.get(PC) or {}).get("folder"):
        out.append((PC, t("This PC"), "pc", True))
    return out


def any_known():
    """Whether 24bit7 remembers a device (a phone copied to or added over WiFi, or This PC's folder), so the
    Devices tab shows from the start."""
    return any(isinstance(e, dict) and (k != PC or e.get("folder")) for k, e in _meta(META_KEY, {}).items())


def present(timeout=1.5, search=False):
    """
    The phones answering now, so the Devices tab shows only then (Ben, 25 Nov 2026: "when 24bit7 detects an open
    phone", USB counting too): every phone plugged in over USB, and every phone added over WiFi whose app answers at
    the address it was last found at. With search, the whole home network is looked at as well (the Devices look
    does it when it starts and every five minutes: knocking on every door each half minute would be a lot), so a
    phone the router gave a new address is found and the address kept (Ben's Pixel went from .248 to .97, 25 Nov
    2026), and a phone 24bit7 can't tell is put on asking(). This PC never counts.
    """
    out = [device_id for device_id, _model in devices()]
    answered = set()
    for key, entry in _meta(META_KEY, {}).items():
        if not (is_wifi(key) and isinstance(entry, dict) and entry.get("code") and entry.get("address")):
            continue
        try:
            if "app:" + str(WifiPhone.info_at(entry["address"], entry["code"], timeout=timeout).get("id")).lower() == key:
                out.append(key)
                answered.add(entry["address"])
        except Exception:
            continue
    if search:
        found, asks = search_network(skip=answered)
        kept = _meta(META_KEY, {})
        for key, address in found:
            if key not in kept:
                continue   # forgotten while the search was out (Forget, on the Devices tab)
            _touch(key, address=address)
            if key not in out:
                out.append(key)
        _asking[:] = asks
    else:
        _asking[:] = [a for a in _asking if a["address"] not in answered]
    return out


_asking = []   # the last search's phones 24bit7 couldn't tell (asking)


def asking():
    """
    The phones with the 24bit7 app answering that 24bit7 can't tell (Ben, 25 Nov 2026): [{address, key, model,
    known}]. known: the id is a phone 24bit7 keeps, but the code it has no longer works (the app was reinstalled
    without Music/.24bit7 to read it back from). Not known: a phone it has never seen, or one that was reset; key is
    None for an older app that won't say who it is without the code. The Devices tab asks about each.
    """
    return [dict(a) for a in _asking]


def hello(address, timeout=1.5):
    """Who the app at this address is, without the code ({id, name}), or None: an older app (before /hello) or no
    answer. Only the id and the phone's model: nothing on the phone is read without the code."""
    import http.client
    host, _, port = address.rpartition(":")
    con = http.client.HTTPConnection(host, int(port), timeout=timeout)
    try:
        con.request("GET", "/hello")
        r = con.getresponse()
        body = r.read()
        return json.loads(body) if r.status == 200 else None
    except Exception:
        return None
    finally:
        con.close()


def search_network(skip=(), timeout=0.4):
    """
    Every phone with the 24bit7 app answering on the home network: ([(key, address)] for those that answer to the
    code 24bit7 keeps, the asking() list for the rest). One quick pass (a background look, so no slower second pass
    as + Add has). Addresses in skip have answered already.
    """
    from concurrent.futures import ThreadPoolExecutor
    every = _meta(META_KEY, {})
    codes = {k: e["code"] for k, e in every.items() if is_wifi(k) and isinstance(e, dict) and e.get("code")}
    hosts = [f"{net}.{i}" for net in _home_networks() for i in range(1, 255)]
    with ThreadPoolExecutor(64) as pool:
        open_ = [h for h, ok in zip(hosts, pool.map(lambda h: _open_port(h, timeout=timeout), hosts)) if ok]
    found, asks = [], []
    for h in open_:
        address = f"{h}:{APP_PORT}"
        if address in skip:
            continue
        me = hello(address)
        if me and me.get("id"):
            key = "app:" + str(me["id"]).lower()
            if key in codes and _answers(address, codes[key]) == key:
                found.append((key, address))
            else:
                asks.append({"address": address, "key": key, "model": me.get("name") or "", "known": key in every})
            continue
        for key, code in codes.items():   # an older app: only a code 24bit7 keeps tells who it is
            if _answers(address, code) == key:
                found.append((key, address))
                break
        else:
            asks.append({"address": address, "key": None, "model": "", "known": False})
    return found, asks


def reconnect(key, code):
    """
    Type Its Code... (Ben, 25 Nov 2026): a WiFi phone that isn't answering, given the code on its screen. It's looked
    for across the home network and, once it answers to the code, kept as this phone (its name, folder, limit and
    records stay; a reset phone with a new id takes them over). The key, or None if no phone answered to the code.
    """
    code = (code or "").strip()
    found = find_apps(code) if re.fullmatch(r"\d{4}", code) else []
    if not found:
        return None
    mine = [a for a, info in found if "app:" + str(info.get("id")).lower() == key]
    return claim((mine or [found[0][0]])[0], code, as_key=key)


def kept_phones():
    """The phones 24bit7 keeps, for the Devices tab's "which is it?": [(key, name)], one per name (a phone kept by
    USB and by WiFi under the same name is offered once, as the WiFi one)."""
    out = {}
    for key, entry in _meta(META_KEY, {}).items():
        if key == PC or not isinstance(entry, dict):
            continue
        name = settings(key, entry.get("model") or "")["name"]
        if name not in out or is_wifi(key):
            out[name] = key
    return [(key, name) for name, key in out.items()]


def _answers(address, code):
    """The key of the app at this address if it takes the code, else None."""
    try:
        return "app:" + str(WifiPhone.info_at(address, code, timeout=1.5).get("id")).lower()
    except Exception:
        return None


def claim(address, code, as_key=None, name=None):
    """
    The answer to the Devices tab's question: the phone at this address, with the code shown on it, is as_key (a
    phone 24bit7 keeps) or, with no as_key, a new one called name. Its name, folder, limit and records move to the
    id it answers with, and the USB link follows. The phone's key, or None when the code isn't right.
    """
    code = (code or "").strip()
    if not re.fullmatch(r"\d{4}", code):
        return None
    try:
        info = WifiPhone.info_at(address, code, timeout=3)
    except Exception:
        return None
    key = "app:" + str(info.get("id")).lower()
    every = _meta(META_KEY, {})
    entry = dict(every.get(key) or {})
    if as_key and as_key != key:
        entry = dict(entry, **(every.pop(as_key, None) or {}))
        links = {u: key if a == as_key else a for u, a in _meta(LINKS_KEY, {}).items()}
        if not is_wifi(as_key):
            links[as_key] = key   # a phone kept by USB only: plugged in again, it's this one
        _set_meta(LINKS_KEY, links)
        if last_device() == as_key:
            _set_meta(LAST_KEY, key)
    entry.update(code=code, address=address, model=info.get("name") or entry.get("model") or "")
    if name and not as_key:
        entry["name"] = name
    every[key] = entry
    _set_meta(META_KEY, every)
    _asking[:] = [a for a in _asking if a["address"] != address]
    return key


def forget(device_id):
    """Forget (the Devices tab): the device out of 24bit7's list, with its name, folder, limit and records.
    Nothing on the phone is touched."""
    key = key_for(device_id)
    every = _meta(META_KEY, {})
    every.pop(key, None)
    every.pop(device_id, None)
    _set_meta(META_KEY, every)
    _set_meta(LINKS_KEY, {u: a for u, a in _meta(LINKS_KEY, {}).items() if a != key and u != device_id})
    if last_device() in (device_id, key):
        _set_meta(LAST_KEY, None)


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

    def move(self, oid, parent, name):
        """A file or folder to another folder under the chosen one, without copying it."""
        dest = os.path.join(parent, name)
        os.replace(oid, dest)
        return dest

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
                _touch(key, address=where)
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


def _touch(key, **choices):
    """
    What a look in the background learned (where a phone answers now), kept only for a device still on the list.
    A look that finishes just after Forget never puts the phone back as a half-made record, which looked like
    Forget not working and left a phone with no code to give (Ben, 25 Nov 2026).
    """
    every = _meta(META_KEY, {})
    if key in every:
        every[key] = dict(every[key], **choices)
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
