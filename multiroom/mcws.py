"""
The few JRiver calls the follower makes (Multiroom, stage one, 9 Nov 2026): what the leader zone is playing and the
next track, stopping the follower zone so its DAC is free, and the follower zone's DAC.

The host, user and password come from .env, as engine.load_settings reads them; the password is never shown.
"""

import os
import xml.etree.ElementTree as ET

import requests

STOPPED, PAUSED, PLAYING = 0, 1, 2


def read_env(path=".env"):
    """The JRiver settings from a .env file (only these three, and only what's there)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                k, sep, v = line.strip().partition("=")
                if sep and k in ("JRIVER_HOST", "JRIVER_USER", "JRIVER_PASS"):
                    out[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def items(text):
    """MCWS's <Item Name="...">value</Item> answer as a dict."""
    return {i.get("Name"): (i.text or "") for i in ET.fromstring(text).findall("Item")}


def _int(v, default=-1):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class JRiver:
    def __init__(self, host=None, user=None, password=None, env=".env", timeout=5):
        conf = read_env(env) if env else {}
        self.host = host or conf.get("JRIVER_HOST") or os.getenv("JRIVER_HOST") or "127.0.0.1:52199"
        user = user if user is not None else conf.get("JRIVER_USER", os.getenv("JRIVER_USER"))
        password = password if password is not None else conf.get("JRIVER_PASS", os.getenv("JRIVER_PASS"))
        self.auth = (user, password) if user else None
        self.base = f"http://{self.host}/MCWS/v1"
        self.timeout = timeout
        self._zones = None

    def __repr__(self):
        return f"JRiver({self.host})"   # never the password

    def call(self, path, **params):
        r = requests.get(f"{self.base}/{path}", params=params, auth=self.auth, timeout=self.timeout)
        r.raise_for_status()
        return items(r.text)

    def zones(self, refresh=False):
        """{zone name: zone id}, hidden zones too (the follower zone is usually hidden)."""
        if self._zones is None or refresh:
            z = self.call("Playback/Zones", Hidden=1)
            self._zones = {z.get(f"ZoneName{n}"): z.get(f"ZoneID{n}") for n in range(_int(z.get("NumberZones"), 0))}
        return self._zones

    def zone_id(self, name):
        """The id of the zone with this name (case ignored), or of this id; KeyError if there's none."""
        for refresh in (False, True):
            zones = self.zones(refresh)
            for zname, zid in zones.items():
                if name in (zname, zid) or (zname or "").lower() == str(name).lower():
                    return zid
        raise KeyError(name)

    def info(self, zone):
        """
        What a zone is doing: state (0 stopped, 1 paused, 2 playing), key and next_key (None when there's none),
        position_ms and name.
        """
        i = self.call("Playback/Info", Zone=self.zone_id(zone))
        key, nxt = _int(i.get("FileKey")), _int(i.get("NextFileKey"))
        return {"state": _int(i.get("State"), STOPPED), "key": key if key >= 0 else None,
                "next_key": nxt if nxt >= 0 else None, "position_ms": _int(i.get("PositionMS"), 0),
                "name": i.get("Name") or "", "status": i.get("Status") or ""}

    def stop(self, zone):
        self.call("Playback/Stop", Zone=self.zone_id(zone))

    # --- the calibration run (stage three) ----------------------------------------------------------
    def play_file(self, zone, path):
        """Plays a file from disk to a zone; JRiver imports it into the library on the way (delete_file undoes that)."""
        self.call("Playback/PlayByFilename", Filenames=path, Zone=self.zone_id(zone))

    def play(self, zone):
        """Play on a stopped zone: the current track from the top."""
        self.call("Playback/Play", Zone=self.zone_id(zone))

    def position(self, zone, ms):
        self.call("Playback/Position", Position=int(ms), Zone=self.zone_id(zone))

    def delete_file(self, key):
        """Takes a track out of the library; its default mode leaves the file on disk (checked 9 Nov 2026)."""
        self.call("File/Delete", File=int(key))

    def playlist(self, zone):
        """A zone's Playing Now, in order, as [(key, name)]."""
        r = requests.get(f"{self.base}/Playback/Playlist", params={"Zone": self.zone_id(zone), "Fields": "Key,Name"},
                         auth=self.auth, timeout=self.timeout)
        r.raise_for_status()
        out = []
        for item in ET.fromstring(r.text).findall(".//Item"):
            f = {x.get("Name"): x.text or "" for x in item.findall("Field")}
            if _int(f.get("Key")) >= 0:
                out.append((_int(f.get("Key")), f.get("Name", "")))
        return out

    def device(self, zone):
        """(device name, plugin) a zone plays through, such as ("Hugo (Chord Async USB 44.1kHz-384kHz)", "WASAPI")."""
        d = self.call("Configuration/Audio/GetDevice", Zone=self.zone_id(zone))
        return d.get("DeviceName") or "", d.get("DevicePlugin") or ""
