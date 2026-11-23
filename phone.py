"""
24bit7 - Copy Tracks To: a saved playlist's tracks copied to a phone (Ben, 23 Nov 2026).

Ben and Jo build playlists in 24bit7 and want them on their phones (both Google Pixels) without fluffing about in
JRiver. Save Playlist's pop-up has a Copy Tracks To tick: the phone (named as you like, "Ben's Phone", told apart by
Windows' device id, which carries the serial, so two of the same phone keep their own names), the folder on it
(Music to start), a limit in GB, and Clear Music First. The tracks go into a folder named after the playlist, with
an .m3u8 beside them listing them in order by file name, so the phone's player shows it as a playlist.

A phone over USB has no drive letter: it's reached through Windows Portable Devices (WPD), here through comtypes.
Proved on Ben's Pixel 9a on 23 Nov 2026: a folder made, files written (37 MB a second), a recursive delete with
no prompt. Everything below WpdPhone works against any object with the same few methods, so the tests use a fake.

Rules:
- Clear First empties the chosen folder (asked once, with the count), leaving dot folders like .thumbnails be.
- Saving the same playlist again copies only what's new, and takes out what's left the playlist, in its own folder.
- The limit and the phone's free space (less a margin) are filled in playlist order; what doesn't fit is said.
"""

import json
import os
import re
import time

import engine
from i18n import t, tn

META_KEY = "copy_devices"     # {device id: {"name", "folder", "limit_gb", "clear"}}
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


def settings(device_id, model=""):
    """A device's remembered choices: its name (the phone's own to start), folder, limit (0 is none), Clear First."""
    saved = _meta(META_KEY, {}).get(device_id) or {}
    return {"name": saved.get("name") or model or t("Phone"), "folder": saved.get("folder") or DEFAULT_FOLDER,
            "limit_gb": float(saved.get("limit_gb") or 0), "clear": bool(saved.get("clear"))}


def remember(device_id, **choices):
    every = _meta(META_KEY, {})
    every[device_id] = dict(every.get(device_id) or {}, **choices)
    _set_meta(META_KEY, every)
    _set_meta(LAST_KEY, device_id)


def last_device():
    return _meta(LAST_KEY, None)


# --- names on the phone -------------------------------------------------------------------------------------

def safe_name(text):
    """A file or folder name a phone and Windows both take: no \\ / : * ? " < > |, no trailing dots or spaces."""
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text or "").strip().rstrip(".").strip()
    return text[:120] or "_"


def file_names(tracks):
    """
    One name per track for the phone: 'Artist - Title.flac', a number added where two would share a name
    ('Intro (2).flac'), so the same track gets the same name on every save and only new ones are copied.
    """
    seen, out = set(), []
    for tr in tracks:
        ext = os.path.splitext(tr["path"])[1].lower()
        base = safe_name(f"{tr.get('artist') or ''} - {tr.get('title') or ''}".strip(" -"))
        name, n = base + ext, 1
        while name.lower() in seen:
            n += 1
            name = f"{base} ({n}){ext}"
        seen.add(name.lower())
        out.append(name)
    return out


def m3u8_text(names):
    """The playlist file: the tracks in order, by name, beside it in the same folder."""
    return "#EXTM3U\n" + "".join(n + "\n" for n in names)


# --- the copy ------------------------------------------------------------------------------------------------

def tracks_for(keys):
    """The playlist's tracks you have files for: {key, path, artist, title, size}, in order."""
    import library
    out = []
    for k in keys:
        row = library.track_row(str(k)) or {}
        path = row.get("Filename") or ""
        if not path or not os.path.isfile(path):
            continue
        out.append({"key": str(k), "path": path, "artist": row.get("Artist") or "", "title": row.get("Name") or "",
                    "size": os.path.getsize(path)})
    return out


def size_text(n):
    return t("{gb} GB", gb=f"{n / GB:.1f}") if n >= GB / 10 else t("{mb} MB", mb=max(1, round(n / 1e6)))


def clear_count(phone, folder):
    """What Clear First would take out of the folder: (folders, files), dot folders and files left out."""
    parent = phone.folder(folder, make=False)
    if parent is None:
        return 0, 0
    kept = [e for e in phone.list(parent) if not e["name"].startswith(".")]
    return sum(1 for e in kept if e["folder"]), sum(1 for e in kept if not e["folder"])


def copy_playlist(phone, folder, playlist, tracks, limit_gb=0, clear=False, say=print):
    """
    Copies tracks (from tracks_for) into folder/playlist on the phone, with playlist.m3u8 beside them. Returns
    how many tracks are there now.
    """
    started = time.time()
    root = phone.folder(folder, make=True)
    if clear:
        gone = [e for e in phone.list(root) if not e["name"].startswith(".")]
        if gone:
            phone.delete([e["id"] for e in gone])
            say("  " + t("Cleared {folder} on {phone}: {count} folders and files taken out.", folder=folder,
                         phone=phone.name, count=len(gone)))
    here = phone.child(root, safe_name(playlist))
    if here is None:
        here = phone.make(root, safe_name(playlist))
    names = file_names(tracks)
    m3u = safe_name(playlist) + ".m3u8"
    on_phone = {e["name"].lower(): e for e in phone.list(here) if not e["folder"]}
    wanted = {n.lower() for n in names} | {m3u.lower()}
    stale = [e for n, e in on_phone.items() if n not in wanted]
    if stale:
        phone.delete([e["id"] for e in stale])
        say("  " + tn("Took out {count} track no longer in the playlist.",
                      "Took out {count} tracks no longer in the playlist.", len(stale)))
    # what fits: the limit and the phone's free space, filled in playlist order
    room = phone.free() - SPARE
    if limit_gb:
        held = sum(e.get("size") or 0 for n, e in on_phone.items() if n in wanted and n != m3u.lower())
        room = min(room, limit_gb * GB - held)
    todo, kept, left_out = [], [], []
    for tr, name in zip(tracks, names):
        already = on_phone.get(name.lower())
        if already is not None and (already.get("size") in (None, tr["size"])):
            kept.append(name)
            continue
        if tr["size"] > room:
            left_out.append(tr)
            continue
        room -= tr["size"]
        todo.append((tr, name, already))
        kept.append(name)
    total = sum(tr["size"] for tr, _, _ in todo)
    if todo:
        say("  " + t("Copying {count} tracks ({size}) to {phone}...", count=len(todo), size=size_text(total),
                     phone=phone.name))
    done_bytes = 0
    for i, (tr, name, already) in enumerate(todo, 1):
        if already is not None:   # a different size: a newer file of the same track
            phone.delete([already["id"]])
        phone.put(here, tr["path"], name, tr["size"])
        done_bytes += tr["size"]
        if i == len(todo) or i % 5 == 0:
            say("  " + t("Copied {done} of {count} ({size}).", done=i, count=len(todo), size=size_text(done_bytes)))
    old = on_phone.get(m3u.lower())
    if old is not None:
        phone.delete([old["id"]])
    phone.put_text(here, m3u, m3u8_text(kept))
    if left_out:
        what = size_text(sum(tr["size"] for tr in left_out))
        say("  " + (tn("Note: {count} track ({size}) didn't fit within {limit} GB, so it was left out.",
                       "Note: {count} tracks ({size}) didn't fit within {limit} GB, so they were left out.",
                       len(left_out), size=what, limit=f"{limit_gb:g}") if limit_gb else
                    tn("Note: {count} track ({size}) didn't fit in the phone's free space, so it was left out.",
                       "Note: {count} tracks ({size}) didn't fit in the phone's free space, so they were left out.",
                       len(left_out), size=what)))
    if todo:
        say(t('Copied to {phone}: {count} tracks in {folder}/{name}, with {name}.m3u8 ({secs} s).', phone=phone.name,
              count=len(kept), folder=folder, name=safe_name(playlist), secs=round(time.time() - started)))
    else:   # saved again with nothing new: only the .m3u8 was written
        say(t("Already on {phone}: {count} tracks in {folder}/{name}, with {name}.m3u8.", phone=phone.name,
              count=len(kept), folder=folder, name=safe_name(playlist)))
    return len(kept)


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
