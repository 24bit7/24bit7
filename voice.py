"""
24bit7 - voice commands.

A small listener for the Alexa skill (or anything else that knows the key).
It only listens on this PC (127.0.0.1); a tunnel is what connects it to Amazon.

  POST /command   header X-24bit7-Key: <VOICE_KEY>
                  body {"intent": "songs_by" | "music_like" | "genre" |
                                  "tracks_like" | "album" | "song" | "playlist" | "shuffle" |
                                  "skip" | "who_is_this" | "more_like",
                        "value": "Agnes Obel", "device": "<Alexa device ID>",
                        "zone": "Sonos"}        # zone is optional and beats the device's zone
                  reply {"speech": "Music like Agnes Obel, coming up on Sonos."}
  GET  /ping      same header; reply {"ok": true, "app": "24bit7", "version": ...}

Alexa gives a skill about eight seconds to answer, so the reply goes back at once
and the playlist is built afterwards, one build at a time, through the Play tab.
Albums, songs, playlists and shuffles need no building: they replace what's playing
on the zone straight away, matched against the library held in library.py.
Skip, who is this and more like this need no value: they work on what the
device's zone is playing.
Each Alexa device is remembered in the database with the zone it plays to.
"""

import hmac
import json
import random
import re
import secrets
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

import engine
import library
import saved_playlists

import itertools

# Voice takeover: the newest command for a zone wins
_take_lock = threading.Lock()
_seq = itertools.count(1)
_latest = {}        # zone -> number of the newest voice command for it
_open = {}          # zone -> voice builds submitted and not yet finished
_running = [None]   # zone of the voice build running now, if any


def _takes_over(zone):
    """True when the build running now is a voice build for this zone and no other zone is waiting."""
    with _take_lock:
        return _running[0] == zone and not any(n > 0 for z, n in _open.items() if z != zone)

INTENTS = ("songs_by", "music_like", "genre", "tracks_like", "album", "song", "playlist", "shuffle",
           "skip", "who_is_this", "more_like", "switch_zones", "keep_going", "stop", "pause", "resume")
COMING = ()   # intents in the skill whose 24bit7 side isn't built yet
ZONE_INTENTS = ("skip", "who_is_this", "more_like", "stop", "pause", "resume",
                "keep_going")   # act on what the zone is playing
THIS_WORDS = ("this", "this one", "this song", "this track", "it")   # "tracks like this" = more like this
INSTANT = ("album", "song", "playlist", "shuffle")   # played straight away, nothing to build
SHUFFLE_CAP = 400                            # most tracks a shuffle sends to JRiver
TEST_DEVICE = "24bit7-settings-test"

_server = None
_thread = None
_submit = None          # set by the GUI: submit(job, heading) queues a build on the Play tab
_status = "Off"
_lock = threading.Lock()


# --- devices ------------------------------------------------------------------

def _devices_table():
    con = engine.db()
    con.execute("""CREATE TABLE IF NOT EXISTS voice_devices (
        device_id TEXT PRIMARY KEY, name TEXT, zone TEXT, last_heard TEXT)""")
    columns = [row[1] for row in con.execute("PRAGMA table_info(voice_devices)")]
    if "moderator" not in columns:   # a per-device AI Moderator tick, during 1.4.0's development
        con.execute("ALTER TABLE voice_devices ADD COLUMN moderator INTEGER DEFAULT 0")
    if "sources" not in columns:
        # Each device's own Sources and Playlist settings (JSON), or NULL to copy Windows (Main).
        con.execute("ALTER TABLE voice_devices ADD COLUMN sources TEXT")
        con.execute("ALTER TABLE voice_devices ADD COLUMN playlist TEXT")
        # A device that had its own AI Moderator tick gets its own Sources, with the moderator on
        own = json.dumps({**engine.profile_values("sources"), "AI_MODERATOR": "1"})
        con.execute("UPDATE voice_devices SET sources=? WHERE moderator=1", (own,))
    if "own_settings" not in columns:
        # The Own settings tick: only a ticked device gets tabs under Sources and Playlist.
        # A device that already has settings of its own starts ticked.
        con.execute("ALTER TABLE voice_devices ADD COLUMN own_settings INTEGER DEFAULT 0")
        con.execute("UPDATE voice_devices SET own_settings=1 WHERE sources IS NOT NULL OR playlist IS NOT NULL")
    if "saved" not in columns:
        # Each device's own Saved Playlists settings (JSON), or NULL to copy Windows (Main)
        con.execute("ALTER TABLE voice_devices ADD COLUMN saved TEXT")
    con.commit()


def devices():
    """[(device_id, name, zone, last_heard, own_settings)], most recently heard first."""
    with _lock:
        _devices_table()
        return engine.db().execute(
            "SELECT device_id, name, zone, last_heard, COALESCE(own_settings, 0) FROM voice_devices "
            "WHERE device_id != ? ORDER BY last_heard DESC", (TEST_DEVICE,)).fetchall()


def set_own_settings(device_id, on):
    """The Own settings tick. Unticked, the device uses Windows (Main); what it had is kept for next time."""
    with _lock:
        _devices_table()
        engine.db().execute("UPDATE voice_devices SET own_settings=? WHERE device_id=?", (1 if on else 0, device_id))
        engine.db().commit()


def update_device(device_id, name=None, zone=None):
    with _lock:
        _devices_table()
        if name is not None:
            engine.db().execute("UPDATE voice_devices SET name=? WHERE device_id=?", (name, device_id))
        if zone is not None:
            engine.db().execute("UPDATE voice_devices SET zone=? WHERE device_id=?", (zone, device_id))
        engine.db().commit()


def device_page(device_id, kind):
    """A device's own "sources", "playlist" or "saved" settings as a dict, or None when it copies Windows (Main)."""
    if kind not in ("sources", "playlist", "saved") or not device_id:
        return None
    with _lock:
        _devices_table()
        row = engine.db().execute(f"SELECT {kind} FROM voice_devices WHERE device_id=?", (device_id,)).fetchone()
    try:
        return json.loads(row[0]) if row and row[0] else None
    except ValueError:
        return None


def set_device_page(device_id, kind, values):
    """Saves a device's own settings of one kind; None goes back to copying Windows (Main)."""
    if kind not in ("sources", "playlist", "saved"):
        return
    with _lock:
        _devices_table()
        engine.db().execute(f"UPDATE voice_devices SET {kind}=? WHERE device_id=?",
                            (json.dumps(values) if values is not None else None, device_id))
        engine.db().commit()


def device_profile(device_id):
    """
    Everything a device has of its own (Sources and Playlist), for engine.use_profile.
    Empty when its Own settings tick is off, or both its tabs copy Windows (Main).
    """
    with _lock:
        _devices_table()
        row = engine.db().execute("SELECT own_settings FROM voice_devices WHERE device_id=?", (device_id,)).fetchone()
    if not (row and row[0]):
        return {}
    profile = {}
    for kind in ("sources", "playlist"):
        profile.update(device_page(device_id, kind) or {})
    return profile


def remove_device(device_id):
    with _lock:
        _devices_table()
        engine.db().execute("DELETE FROM voice_devices WHERE device_id=?", (device_id,))
        engine.db().commit()


def _hear_device(device_id):
    """Records that a device spoke. Returns (name, zone); a new device gets a name and no zone."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with _lock:
        _devices_table()
        con = engine.db()
        row = con.execute("SELECT name, zone FROM voice_devices WHERE device_id=?", (device_id,)).fetchone()
        if row:
            con.execute("UPDATE voice_devices SET last_heard=? WHERE device_id=?", (now, device_id))
        else:
            count = con.execute("SELECT COUNT(*) FROM voice_devices").fetchone()[0]
            row = (f"New device {count + 1}", "")
            con.execute("INSERT INTO voice_devices (device_id, name, zone, last_heard, moderator) "
                        "VALUES (?,?,?,?,0)", (device_id, row[0], "", now))
        con.commit()
    return row


# --- commands -----------------------------------------------------------------

def _job(intent, value, zone, profile=None, device=None):
    """
    The build itself, run on the Play tab's worker thread, with the device's own settings if it has any.
    Takeover: a newer voice command for the same zone stops this build at its next step (or skips it
    if it hasn't started yet), and a paused zone counts as free, so after "Alexa, stop" the next command plays.
    """
    with _take_lock:
        seq = next(_seq)
        _latest[zone] = seq
        _open[zone] = _open.get(zone, 0) + 1

    def superseded():
        return _latest.get(zone) != seq

    def run(report):
        def guarded(line):
            if superseded():
                raise engine.BuildCancelled()
            report(line)

        try:
            if superseded():
                report(f"  Skipped: a newer voice command for {zone} took over.")
                return
            with _take_lock:
                _running[0] = zone
            engine.refresh_settings_if_changed()
            engine.OUTPUT_OVERRIDE = zone
            engine.use_profile(profile)
            # More like this keeps the current track playing and replaces what's queued after it,
            # so it uses the Play tab's rule (queue after a busy zone) rather than taking the zone over
            engine.VOICE_TAKEOVER = intent != "more_like"
            engine.CANCEL_CHECK = superseded
            engine.FILTER_DEVICE = device   # Settings > Filters ticked for this device apply
            _build(intent, value, guarded)
        except engine.BuildCancelled:
            report(f"  Stopped: a newer voice command for {zone} took over.")
        finally:
            engine.OUTPUT_OVERRIDE = None
            engine.use_profile(None)
            engine.VOICE_TAKEOVER = False
            engine.CANCEL_CHECK = None
            engine.FILTER_DEVICE = None
            with _take_lock:
                _running[0] = None
                _open[zone] = max(0, _open.get(zone, 1) - 1)
    return run


def _build(intent, value, report):
    """The playlist build for a voice command (report stops it if a newer command took over)."""
    if intent == "songs_by":
        engine.play_top_n(report=report, seed_info=engine.typed_seed_info(value))
    elif intent == "music_like":
        tracks, _ = engine.blended_top_tracks(value, limit=1)
        if not tracks:
            report(f"Couldn't find top tracks for '{value}', so there's nothing to seed from.")
            return
        report(f"  Seed track: {tracks[0][0]} (the artist's most popular track)")
        engine.create_similar_playlist(report=report, seed_info=engine.typed_seed_info(value, tracks[0][0]))
    elif intent == "tracks_like":
        artist, title = value
        engine.create_similar_tracks_playlist(report=report,
                                              seed_info=engine.typed_seed_info(artist, title))
    elif intent == "more_like":   # value: the zone's track when the command was heard
        engine.create_similar_tracks_playlist(report=report, seed_info=value)
    else:
        engine.create_vibe_playlist(value, report=report)


def _play_keys(keys, zone_id):
    r = requests.get(f"{engine.JRIVER_BASE}/Playback/PlayByKey",
                     params={"Key": ",".join(str(k) for k in keys), "Zone": zone_id},
                     auth=engine.AUTH, timeout=10)
    return r.status_code == 200


def _either(names):
    names = [library.spoken(n) for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _top_five_start(artist, keys):
    """A random pick from the artist's top 5 that's in the shuffle, or None."""
    try:
        top, _ = engine.blended_top_tracks(artist, limit=5)
    except Exception:
        return None
    owned = {str(k) for k in keys}
    hits = [k for k in (library.find_track_key(artist, t) for t, _ in top) if k and str(k) in owned]
    return random.choice(hits) if hits else None


def _play_now(intent, value, zone, device=None):
    """Albums, songs, playlists and shuffles: replace what's playing on the zone at once."""
    zid = engine.zone_id(zone)
    if intent == "playlist":
        found, matches = saved_playlists.find(value)
        if not matches:
            return "problem", f"I couldn't find a playlist called {value.rsplit(' by ', 1)[0]}.", {}
        if not found:   # two or more share the name: ask which (the answer comes back as 'name by smartlist')
            return "ask", saved_playlists.ask_which(matches), {"ask": "playlist", "title": matches[0].get("Name")}
        # Shuffle, Non-stop and Skip recently played from Settings > JRiver Playlists
        ok, what = saved_playlists.play(matches[0], zid, device)
    elif intent in ("album", "song"):
        finder = library.find_album if intent == "album" else library.find_song
        found, matches = finder(value)
        if not matches:
            what = "an album" if intent == "album" else "a song"
            return "problem", f"I couldn't find {what} called {value.rsplit(' by ', 1)[0]}.", {}
        if not found:
            title = matches[0][0]
            artists = [artist for _, artist, _ in matches]
            if len(artists) <= 3:
                speech = f"{title} by {_either(artists)}. Which one?"
            else:
                speech = f"You have {len(artists)} {intent}s called {title}. Which artist?"
            return "ask", speech, {"ask": intent, "title": title}
        title, artist, keys = matches[0]
        keys = keys if intent == "album" else [keys]
        ok, what = _play_keys(keys, zid), f"{intent} {title} by {library.spoken(artist)}"
        engine.nonstop_forget(zid)   # an album or song ends as normal
    else:
        artist, keys = library.artist_tracks(value)
        if not keys:
            return "problem", f"I couldn't find any songs by {value}.", {}
        keys = engine.drop_long_closers(keys, report=print, group="top")
        # Recently played: the Artist's Top Tracks setting, the device's own if it has one
        own = device_profile(device) if device else {}
        main_on, main_days = engine.SKIP_PLAYED["top"]
        on = own.get("SKIP_PLAYED_TOP", "1" if main_on else "0") in ("1", "true", "yes")
        days = own.get("SKIP_PLAYED_TOP_DAYS", str(main_days))
        played = engine.PlayedFilter("top", report=print, setting=(on, int(days) if days.isdigit() else main_days))
        keys = [k for k in keys if played.fresh(k)] or keys   # never leave a shuffle empty
        played.done()
        random.shuffle(keys)
        lead = _top_five_start(artist, keys)
        if lead:   # a shuffle opens on one of their best known songs
            keys = [lead] + [k for k in keys if str(k) != str(lead)]
        ok, what = _play_keys(keys[:SHUFFLE_CAP], zid), f"{min(len(keys), SHUFFLE_CAP)} songs by {library.spoken(artist)}, shuffled"
        if ok:   # non-stop: when the shuffle ends, the opening track seeds a new playlist
            engine.nonstop_record(zid, keys[:SHUFFLE_CAP], kind="top", stage="rest", vibe=None,
                                  top_artist=artist, top_first=str(lead) if lead else None)
    if not ok:
        return "problem", "JRiver didn't start it. Is JRiver running on the media PC?", {}
    print(f"[Voice] Playing {what} on {zone}")
    return "started", f"Playing {what} on {zone}.", {}


def _tracks_like_seed(value):
    """
    'creep' or 'creep by radiohead' -> ((artist, title), None) to seed Similar Tracks from,
    or (None, reply) when Alexa should answer instead. Names come from the library
    where the song is there; with 'by <artist>' it doesn't have to be.
    """
    found, matches = library.find_song(value)
    if found:
        title, artist, _ = matches[0]
        return (artist, title), None
    if " by " in value:
        title, artist = (part.strip() for part in value.rsplit(" by ", 1))
        return (artist, title), None
    if not matches:
        return None, ("problem", f"I couldn't find a song called {value}. "
                                 f"Say tracks like, then the song, by the artist.", {})
    title = matches[0][0]
    artists = [artist for _, artist, _ in matches]
    if len(artists) <= 3:
        speech = f"{title} by {_either(artists)}. Which one?"
    else:
        speech = f"You have {len(artists)} songs called {title}. Which artist?"
    return None, ("ask", speech, {"ask": "tracks_like", "title": title})


# --- skip, who is this, more like this ----------------------------------------

def _speakable(info):
    """
    (title, artist, album) as Alexa should say them. Remaster, soundtrack and
    other version suffixes are dropped, and an 'Artist - Title' name (how
    compilation series are tagged, with the series as the artist) is split.
    """
    import re
    name = engine.normalise_punctuation(info.get("Name") or "").strip()
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)                         # (Remastered 2011), [Live]
    name = re.sub(r"\s+-\s+from\s.*$", "", name, flags=re.I)                     # - From 'Casino Royale' Soundtrack
    name = re.sub(rf"\s+-\s+[^-]*\b{engine.VERSION_WORDS}\b[^-]*$", "", name, flags=re.I)   # - 2012 Remaster
    name = re.sub(r"\s*(feat\.|featuring|ft\.)\s.*$", "", name, flags=re.I).strip()
    artists = [a for a in engine.split_values(info.get("Artist")) if a != "Unknown"]
    artist = " and ".join(library.spoken(a) for a in artists[:2])
    album = (info.get("Album") or "").strip()
    if album == "Unknown":
        album = ""
    if " - " in name:   # compilation tagging: the real artist is in the name
        left, right = (part.strip() for part in name.split(" - ", 1))
        if left and right:
            artist, name = library.spoken(left), right
    return name or "this track", artist, album


def _zone_command(intent, device, body):
    """Skip, who is this and more like this, on the zone of the device that heard it."""
    name, zone = _hear_device(device or "unknown device")
    zone = (body.get("zone") or "").strip() or zone
    if not zone:
        return "problem", "This device isn't set up yet. Assign it to a zone in 24bit7, under Settings, Voice Commands.", {}
    zid = engine.zone_id(zone)
    if zid is None:
        return "problem", f"I can't find the {zone} zone in JRiver.", {}
    info = engine.get_playing_info(zid)
    if info is None:
        return "problem", "I couldn't reach JRiver. Is it running on the media PC?", {}
    try:
        pos, count = int(info.get("PlayingNowPosition") or -1), int(info.get("PlayingNowTracks") or 0)
    except ValueError:
        pos, count = -1, 0
    state = engine.zone_state(zid)
    if pos < 0 or count == 0 or state == 0:
        return "problem", f"Nothing's playing on {zone}.", {}

    if intent == "keep_going":
        return keep_going(zone)

    if intent in ("stop", "pause", "resume"):
        if intent == "pause" and state == 1:
            return "said", f"{zone} is already paused.", {}
        if intent == "resume" and state == 2:
            return "said", f"{zone} is already playing.", {}
        if intent == "stop":
            r = requests.get(f"{engine.JRIVER_BASE}/Playback/Stop", params={"Zone": zid},
                             auth=engine.AUTH, timeout=10)
        else:
            r = requests.get(f"{engine.JRIVER_BASE}/Playback/Pause",
                             params={"State": 1 if intent == "pause" else 0, "Zone": zid},
                             auth=engine.AUTH, timeout=10)
        if r.status_code != 200:
            return "problem", f"JRiver didn't {intent}. Is it running on the media PC?", {}
        print(f"[Voice] {name}: {intent} on {zone}")
        return "started", f"{intent.title()}.", {}

    if intent == "skip":
        if pos + 1 >= count:
            return "problem", "Nothing to skip to.", {}
        try:
            r = requests.get(f"{engine.JRIVER_BASE}/Playback/Next", params={"Zone": zid},
                             auth=engine.AUTH, timeout=10)
            ok = r.status_code == 200
        except Exception:
            ok = False
        if not ok:
            return "problem", "JRiver didn't skip. Is it running on the media PC?", {}
        print(f"[Voice] {name}: skipped {info.get('Name')} on {zone}")
        return "started", "Skipped.", {}

    title, artist, album = _speakable(info)
    if intent == "who_is_this":
        speech = f"That's {title}" + (f" by {artist}" if artist else "")
        speech += f", from {album}." if album and album.lower() != title.lower() else "."
        print(f"[Voice] {name}: who is this on {zone}: {speech}")
        return "said", speech, {}

    # more like this: Similar Tracks seeded from the zone's track, queued after it
    if _submit is None:
        return "problem", "24bit7 isn't ready yet. Try again in a moment.", {}
    seed = dict(info)
    seed["ZoneID"] = zid
    shown = f"{title} by {artist}" if artist else title
    profile = device_profile(device or "unknown device")
    _submit(_job("more_like", seed, zone, profile, device or "unknown device"),
            f"Voice, {name}: more like {shown}, to {zone}" + (", with its own settings" if profile else ""),
            {"from": "voice", "device": device or "unknown device"})
    if _is_busy() and not _takes_over(zone):
        return "pending", "Please wait, request pending.", {}
    return "started", f"More like {shown}, coming up on {zone}.", {}


# --- switch, stop, pause, resume ------------------------------------------------
# Switch moves whatever is playing to another zone: the same Playing Now, from the
# same track and point, and the zone it left stops. The zones it can move to are
# the ones ticked under Enable Switch To (Settings > Voice Commands), kept by zone
# name so a zone with no device can be added later; a zone is ticked unless unticked.

SWITCH_META = "switch_off"   # zone names unticked under Enable Switch To


def switch_unticked():
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (SWITCH_META,)).fetchone()
        return set(json.loads(row[0])) if row and row[0] else set()
    except Exception:
        return set()


def set_switch_enabled(zone, on):
    off = switch_unticked()
    (off.discard if on else off.add)(zone)
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (SWITCH_META, json.dumps(sorted(off))))
    con.commit()


def switch_targets():
    """Zones that can be switched to, in JRiver's order: zones a device plays to, minus those unticked."""
    off = switch_unticked()
    with_device = {zone for _, _, zone, _, _ in devices() if zone}
    return [z for z in engine.zone_names(include_hidden=True) if z in with_device and z not in off]


def _info_items(zid):
    r = requests.get(f"{engine.JRIVER_BASE}/Playback/Info", params={"Zone": zid}, auth=engine.AUTH, timeout=10)
    import xml.etree.ElementTree as ET
    return {i.get("Name"): (i.text or "").strip() for i in ET.fromstring(r.text).findall("Item")}


def _playing(zid):
    """True when the zone has a Playing Now and is playing or paused."""
    try:
        items = _info_items(zid)
        return items.get("State") in ("1", "2") and int(items.get("PlayingNowTracks") or 0) > 0
    except Exception:
        return False


def _mcws(path, **params):
    return requests.get(f"{engine.JRIVER_BASE}/{path}", params=params, auth=engine.AUTH, timeout=10)


SWITCH_START_TIMEOUT = 8   # seconds for a DLNA zone to start playing before the track starts from the top
SWITCH_SEEK_CHECK = 4      # seconds to watch for the jump taking effect
SWITCH_RETRY_S = 1.0       # pause before the one retry of a refused jump
SWITCH_BUFFER_S = 1.5      # wait after the jump before the volume comes back, so the speaker's buffer clears
SWITCH_POLL = 0.25
HANDOVER_BACKGROUND = True   # the handover runs in the background so Alexa answers straight away (tests run it inline)


def switch_adjust_ms():
    """The Switch Timing Adjustment in ms (minus means the DLNA zone jumps further into the track). Default -1 s."""
    engine.refresh_settings_if_changed()
    raw = os.getenv("SWITCH_TIMING", "").strip()
    try:
        value = float(raw) if raw else -1.0
    except ValueError:
        value = -1.0
    return int(round(max(-3.0, min(3.0, value)) * 1000))


def _ms(items):
    return int(float(items.get("PositionMS") or 0))


def _is_dlna(zid):
    """True when JRiver marks the zone as a DLNA renderer (ZoneDLNA=1). False if it can't tell."""
    try:
        import xml.etree.ElementTree as ET
        r = _mcws("Playback/Zones")
        items = {i.get("Name"): (i.text or "").strip() for i in ET.fromstring(r.text).findall("Item")}
        for n in range(int(items.get("NumberZones") or 0)):
            if items.get(f"ZoneID{n}") == str(zid):
                return items.get(f"ZoneDLNA{n}") == "1"
    except Exception:
        pass
    return False


def _volume(zid):
    """A zone's volume level (0 to 1), or None if JRiver doesn't say."""
    try:
        import xml.etree.ElementTree as ET
        r = _mcws("Playback/Volume", Zone=zid)
        items = {i.get("Name"): (i.text or "").strip() for i in ET.fromstring(r.text).findall("Item")}
        return float(items["Level"])
    except Exception:
        return None


def _wait_started(tid):
    """Seconds until the zone is playing with its clock moving, or None if it hasn't within SWITCH_START_TIMEOUT."""
    t0, last = time.time(), None
    while time.time() - t0 < SWITCH_START_TIMEOUT:
        items = _info_items(tid)
        playing = items.get("State") == "2"
        if playing and last is not None and _ms(items) > last:
            return time.time() - t0
        last = _ms(items) if playing else None
        time.sleep(SWITCH_POLL)
    return None


def _jump_took(tid, want):
    """True once the zone's position has reached the jump (give or take 1.5 s)."""
    t0 = time.time()
    while True:
        if _ms(_info_items(tid)) >= want - 1500:
            return True
        if time.time() - t0 >= SWITCH_SEEK_CHECK:
            return False
        time.sleep(SWITCH_POLL)


def _leave(sid, tid):
    """The zone left stops, and Non-stop follows the music."""
    _mcws("Playback/Stop", Zone=sid)
    with engine._nonstop_lock:
        entry = engine.NONSTOP_ZONES.pop(sid, None)
        if entry is not None:
            entry.pop("fired", None)
            engine.NONSTOP_ZONES[tid] = entry


def _handover(sid, tid, target, level):
    """
    The rest of a switch onto a DLNA zone, which is already muted and starting the track:
    wait for it to play, jump to where the old zone has reached, let its buffer clear,
    then bring the volume back and stop the old zone. Any failure leaves the track
    playing from the top there, as before. The volume is always restored.
    """
    t0 = time.time()
    try:
        started = _wait_started(tid)
        if started is None:
            print(f"  {target} didn't start within {SWITCH_START_TIMEOUT} s, so the track starts from the top there.")
            return
        adjust = switch_adjust_ms()
        took = False
        for attempt in (1, 2):
            want = max(0, _ms(_info_items(sid)) - adjust)
            _mcws("Playback/Position", Position=want, Zone=tid)
            if _jump_took(tid, want):
                took = True
                break
            if attempt == 1:
                time.sleep(SWITCH_RETRY_S)
        if not took:
            print(f"  {target} didn't accept the jump, so the track starts from the top there.")
            return
        time.sleep(SWITCH_BUFFER_S)
        engine.debug(f"Switch to {target}: started in {started:.2f} s, adjustment {adjust / 1000:.2f} s, "
                     f"jump on try {attempt}, handover {time.time() - t0:.2f} s")
    except Exception as e:
        print(f"  Problem: the switch to {target} hit an error ({e}), so the track starts from the top there.")
    finally:
        try:
            _mcws("Playback/Volume", Level=level, Zone=tid)
        except Exception as e:
            print(f"  Problem: couldn't put {target}'s volume back ({e}). Set it to {round(level * 100)}% in JRiver.")
        _leave(sid, tid)


def _move(source, target):
    """
    Moves source's Playing Now to target at the same track and point; source stops. Non-stop follows.
    Onto a DLNA zone (the Sonos) it hands over: see _handover, which carries on in the background.
    """
    sid, tid = engine.zone_id(source), engine.zone_id(target)
    items = _info_items(sid)
    pos = int(items.get("PlayingNowPosition") or 0)
    ms = int(float(items.get("PositionMS") or 0))
    paused = items.get("State") == "1"
    keys = [r["Key"] for r in engine.playing_now_rows(sid) if r.get("Key")]
    if not keys:
        return False
    level = _volume(tid) if not paused and ms > 1000 and _is_dlna(tid) else None
    if level is not None:
        _mcws("Playback/Volume", Level=0, Zone=tid)
        if not saved_playlists._send(keys, tid):
            _mcws("Playback/Volume", Level=level, Zone=tid)
            return False
        if pos > 0:
            _mcws("Playback/PlayByIndex", Index=pos, Zone=tid)
        job = lambda: _handover(sid, tid, target, level)
        if HANDOVER_BACKGROUND:
            threading.Thread(target=job, daemon=True, name="switch-handover").start()
        else:
            job()
        print(f"[Voice] Switched from {source} to {target}")
        return True
    if not saved_playlists._send(keys, tid):
        return False
    if pos > 0:
        _mcws("Playback/PlayByIndex", Index=pos, Zone=tid)
    if ms > 1000:
        _mcws("Playback/Position", Position=ms, Zone=tid)
    if paused:
        _mcws("Playback/Pause", State=1, Zone=tid)
    _leave(sid, tid)
    print(f"[Voice] Switched from {source} to {target}")
    return True


def _source_zone(preferred):
    """The zone to move from: preferred if it's playing, else the only zone playing. (zone, problem)"""
    if preferred and engine.zone_id(preferred) and _playing(engine.zone_id(preferred)):
        return preferred, None
    playing = [z for z in engine.zone_names(include_hidden=True) if _playing(engine.zone_id(z))]
    if not playing:
        return None, "Nothing's playing to switch."
    if len(playing) > 1:
        return None, "More than one zone is playing. Ask from a speaker in the room you're moving from."
    return playing[0], None


def _switch(device, value, body):
    """Switch, switch zones, switch to <zone>: by voice."""
    name, zone = _hear_device(device or "unknown device")
    zone = (body.get("zone") or "").strip() or zone
    source, problem = _source_zone(zone)
    if problem:
        return "problem", problem, {}
    others = [z for z in switch_targets() if z != source]
    heard = library.norm(re.sub(r"^(to\s+)?(the\s+)?", "", value.strip(), flags=re.I)) if value else ""
    if heard:
        best = max(others, key=lambda z: library.score(heard, z), default=None)
        if best is None or library.score(heard, best) < library.GOOD:
            if engine.zone_id(value) is None and heard not in [library.norm(z) for z in engine.zone_names(True)]:
                return "problem", f"I can't find a zone called {value}.", {}
            return "problem", (f"{value} isn't ticked to switch to. Tick it under Enable Switch To, "
                               f"in 24bit7's Voice Commands settings."), {}
        target = best
    elif not others:
        return "problem", ("There's no other zone to switch to. Tick zones under Enable Switch To, "
                           "in 24bit7's Voice Commands settings."), {}
    elif len(others) == 1:
        target = others[0]
    else:
        listed = ", ".join(others[:-1]) + " or " + others[-1]
        return "ask", f"Which zone? {listed}.", {"ask": "zone", "title": ""}
    if not _move(source, target):
        return "problem", "JRiver didn't switch it. Is JRiver running on the media PC?", {}
    return "started", f"Switching to {target}.", {}


def keep_going(zone):
    """
    Keep It Going: Non-stop, once, for whatever is playing on a zone, even music
    started in JRiver itself. It tops up with the zone's Similar Tracks Non-stop
    settings (Using, Reseed from; a device's own if it has them), whether or not
    Non-stop is switched on there, and ends when something else replaces the music.
    Returns (status, speech, extra) like the other voice commands.
    """
    import hotkeys
    import nonstop
    zid = engine.zone_id(zone)
    if zid is None:
        return "problem", f"I can't find the {zone} zone in JRiver.", {}
    if not _playing(zid):
        return "problem", f"Nothing's playing on {zone}.", {}
    _, _, profile = hotkeys._device_for_zone(zone)
    settings = engine.nonstop_settings(nonstop._settings_for(profile).get)
    with engine._nonstop_lock:
        entry = engine.NONSTOP_ZONES.get(zid)
    if entry:
        origin = entry.get("origin") or entry.get("kind")
        on = bool(entry.get("saved_cfg")) if origin == "saved" else settings.get(origin, {}).get("on")
        if on:
            return "said", f"Non-stop is already on for {zone}.", {}
    keys = [r["Key"] for r in engine.playing_now_rows(zid) if r.get("Key")]
    if not keys:
        return "problem", f"Nothing's playing on {zone}.", {}
    cfg = settings["tracks"]
    engine.nonstop_record(zid, keys, kind="saved", stage="after", vibe=None,
                          # Off there means Wander; otherwise the mode chosen there
                          saved_cfg={"using": cfg["using"],
                                     "reseed": "whole" if cfg.get("on") and cfg.get("mode") == "tight" else cfg["reseed"]})
    print(f"[Voice] Keep It Going: Non-stop on for {zone}")
    return "started", f"Non-stop is on for {zone}.", {}


def switch_step(preferred):
    """The Switch Zones shortcut: moves what's playing to the next ticked zone. Returns a line for the console."""
    source, problem = _source_zone(preferred)
    if problem:
        return f"  Problem: {problem}"
    targets = switch_targets()
    others = [z for z in targets if z != source]
    if not others:
        return "  Problem: there's no other zone to switch to. Tick zones under Enable Switch To, in Voice Commands."
    after = [z for z in targets if targets.index(z) > targets.index(source)] if source in targets else []
    target = (after or others)[0]
    return f"  Switched from {source} to {target}." if _move(source, target) else \
        "  Problem: JRiver didn't switch it. Is JRiver running?"


ARTIST_CLOSE = 0.85   # how close a heard artist must be to a library artist to use the library's spelling


def _library_artist(heard):
    """
    The library's own spelling of a heard artist, so a mishearing like
    'the beetles' becomes 'The Beatles'. Exact matches first (with 'Beatles, The'
    forms), then the closest spelling at ARTIST_CLOSE or better. Otherwise the
    heard name as it was (the artist may simply not be in the library).
    """
    try:
        library.ensure_loaded()
        with library._lock:
            names = list(library._artists.values())
        best_score, best = max(((library.score(heard, a), a) for a in names), default=(0.0, None))
    except Exception:
        return heard
    if best and best_score >= ARTIST_CLOSE:
        return library.spoken(best)
    return heard


def handle_command(body, busy=False):
    """
    Works out the reply and queues the build, or plays an album, playlist or
    shuffle at once. Returns (status, speech, extra):
      started  the build begins now, or the music has started (the skill plays two chimes)
      pending  it waits for the build already running (the skill says so)
      ask      several albums share the title; extra carries it, and the skill asks which
      problem  nothing was queued; speech says why
    """
    intent = (body.get("intent") or "").strip().lower()
    value = (body.get("value") or "").strip()
    device = (body.get("device") or "").strip()
    if intent not in INTENTS:
        return "problem", "Say songs by, music like, or genre, followed by what you'd like.", {}
    if intent == "song" and value.lower().startswith("by "):   # Alexa heard "songs by" as "song by"
        intent, value = "songs_by", value[3:].strip()
    if intent in ("tracks_like", "music_like") and value.lower() in THIS_WORDS:   # "songs like this"
        intent, value = "more_like", ""
    if intent == "switch_zones":
        try:
            return _switch(device, value, body)
        except Exception as e:
            print(f"[Voice] switch failed: {e}")
            return "problem", "I couldn't reach JRiver. Is it running on the media PC?", {}
    if intent in COMING:
        return "said", "That's coming in the next update of 24bit7.", {}
    if intent in ZONE_INTENTS:
        try:
            return _zone_command(intent, device, body)
        except Exception as e:
            print(f"[Voice] {intent} failed: {e}")
            return "problem", "I couldn't reach JRiver. Is it running on the media PC?", {}
    if not value:
        missing = {"genre": "the genre", "album": "the album", "song": "the song", "tracks_like": "the song",
                   "playlist": "the playlist"}.get(intent, "the artist")
        return "problem", f"I didn't catch {missing}.", {}

    name, zone = _hear_device(device or "unknown device")
    zone = (body.get("zone") or "").strip() or zone
    if not zone:
        return "problem", "This device isn't set up yet. Assign it to a zone in 24bit7, under Settings, Voice Commands.", {}
    if engine.zone_id(zone) is None:
        return "problem", f"I can't find the {zone} zone in JRiver.", {}
    if intent in INSTANT:
        try:
            return _play_now(intent, value, zone, device)
        except Exception as e:
            print(f"[Voice] {intent} '{value}' failed: {e}")
            return "problem", "I couldn't reach the library in JRiver. Is JRiver running on the media PC?", {}
    if intent == "genre" and engine.vibe_blocker():
        return "problem", "Genre playlists need an Anthropic key in 24bit7.", {}
    if _submit is None:
        return "problem", "24bit7 isn't ready yet. Try again in a moment.", {}
    if intent == "tracks_like":
        try:
            value, reply = _tracks_like_seed(value)
        except Exception as e:
            print(f"[Voice] tracks like '{value}' failed: {e}")
            return "problem", "I couldn't reach the library in JRiver. Is JRiver running on the media PC?", {}
        if reply:
            return reply

    heard = value
    if intent in ("songs_by", "music_like"):
        value = _library_artist(value)
    corrected = f" (heard '{heard}')" if isinstance(value, str) and value.lower() != heard.lower() else ""

    shown = f"{value[1]} by {library.spoken(value[0])}" if intent == "tracks_like" else value
    words = {"songs_by": f"Songs by {shown}", "music_like": f"Music like {shown}",
             "genre": f"A {shown} playlist", "tracks_like": f"Tracks like {shown}"}[intent]
    phrase = {"songs_by": "songs by", "music_like": "music like", "genre": "genre",
              "tracks_like": "tracks like"}[intent]
    profile = device_profile(device or "unknown device")
    _submit(_job(intent, value, zone, profile, device or "unknown device"),
            f"Voice, {name}: {phrase} {shown}{corrected}, to {zone}" + (", with its own settings" if profile else ""),
            {"from": "voice", "device": device or "unknown device"})
    if busy and not _takes_over(zone):
        return "pending", "Please wait, request pending.", {}
    return "started", f"{words}, coming up on {zone}.", {}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):   # keep the console quiet
        pass

    def _reply(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _key_ok(self):
        given = self.headers.get("X-24bit7-Key", "")
        return bool(engine.VOICE_KEY) and hmac.compare_digest(given, engine.VOICE_KEY)

    def do_GET(self):
        if self.path.split("?")[0] != "/ping":
            return self._reply(404, {"error": "not found"})
        if not self._key_ok():
            return self._reply(401, {"error": "wrong key"})
        self._reply(200, {"ok": True, "app": "24bit7", "version": engine.VERSION})

    def do_POST(self):
        if self.path.split("?")[0] != "/command":
            return self._reply(404, {"error": "not found"})
        if not self._key_ok():
            return self._reply(401, {"error": "wrong key"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 10000)) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self._reply(400, {"error": "body must be a JSON object"})
        status, speech, extra = handle_command(body, busy=_is_busy())
        if status == "problem":
            _log_problem(body, speech)
        self._reply(200, {"status": status, "speech": speech, **extra})


SAID = {"songs_by": "songs by", "music_like": "music like", "tracks_like": "tracks like", "genre": "genre",
        "album": "album", "song": "song", "playlist": "playlist", "shuffle": "shuffle songs by", "skip": "skip",
        "who_is_this": "who is this", "more_like": "more like this", "switch_zones": "switch zones",
        "keep_going": "keep it going", "stop": "stop the music", "pause": "pause the music",
        "resume": "resume the music"}


def _log_problem(body, speech):
    """A voice command that came to nothing: what was asked, and what Alexa said back, in the console."""
    device = (body.get("device") or "").strip()
    try:
        with _lock:
            _devices_table()
            row = engine.db().execute("SELECT name FROM voice_devices WHERE device_id=?", (device,)).fetchone()
        name = row[0] if row and row[0] else "an unknown device"
    except Exception:
        name = "an unknown device"
    intent = (body.get("intent") or "").strip().lower()
    asked = " ".join(x for x in (SAID.get(intent, intent or "a command"), (body.get("value") or "").strip()) if x)
    first = f"{datetime.now().strftime('%H:%M')}  Voice, {name}: {asked}"
    second = f'  Problem: Alexa said "{speech}"'
    engine.print(first)
    engine.print(second)
    try:
        import buildlog   # here rather than at the top: it imports engine
        buildlog.record_instant(device or "unknown device", intent, first + "\n" + second)
    except Exception as e:
        engine.debug(f"Couldn't keep the failed voice command in the Log: {e}")


_is_busy = lambda: False   # replaced by the GUI


# --- starting and stopping ------------------------------------------------------

def attach(submit, is_busy):
    """The GUI hands over how to queue a build and how to tell if one is running."""
    global _submit, _is_busy
    _submit, _is_busy = submit, is_busy


def new_key():
    return secrets.token_urlsafe(24)


def status():
    return _status


def stop():
    global _server, _thread, _status
    if _server is not None:
        _server.shutdown()
        _server.server_close()
    _server, _thread, _status = None, None, "Off"


def restart():
    """Starts (or stops) the listener to match the current settings."""
    global _server, _thread, _status
    stop()
    engine.refresh_settings_if_changed()
    if not engine.VOICE_ENABLED:
        return _status
    if not engine.VOICE_KEY:
        _status = "Off: no key yet"
        return _status
    try:
        _server = ThreadingHTTPServer(("127.0.0.1", engine.VOICE_PORT), _Handler)
    except OSError:
        _status = f"Off: port {engine.VOICE_PORT} is already in use"
        _server = None
        return _status
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    _status = f"Listening on 127.0.0.1:{engine.VOICE_PORT}"
    return _status


def send_test(artist, zone):
    """What the Settings Test button sends: a real music_like command through the listener."""
    import urllib.request
    req = urllib.request.Request(
        f"http://127.0.0.1:{engine.VOICE_PORT}/command",
        data=json.dumps({"intent": "music_like", "value": artist, "device": TEST_DEVICE,
                         "zone": zone}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-24bit7-Key": engine.VOICE_KEY or ""},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            reply = json.loads(r.read())
    except Exception as e:
        return f"get no reply from the listener ({e})."
    if reply.get("status") == "started":
        return f"play its tone. ({reply.get('speech', '')})"
    return f'say "{reply.get("speech", "")}"'
