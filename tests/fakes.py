"""
24bit7 test suite - the fake world.

Everything 24bit7 talks to, faked in memory so the tests never touch a real
JRiver, a real library, the internet or an API key:

  FakeJRiver   the Media Center web service (MCWS): a small library, zones with
               their own Playing Now, playlists and smartlists. Records every
               call, so a test can check exactly what would have played.
  FakeWeb      Last.fm, Deezer, MusicBrainz, ListenBrainz (and Labs), with
               answers built from the fake library plus a few artists it lacks.
  FakeAI       stands in for anthropic.Anthropic: similar artists, top tracks,
               similar tracks, AI Playlist, vibe suggestions and the Moderator.
  FakeYTMusic  stands in for ytmusicapi.YTMusic (search and up next).

install() routes every requests call through them; anything else raises, so
a test can never leak onto the network.
"""

import json
import re
import time
import unicodedata
import urllib.parse
from types import SimpleNamespace
from xml.sax.saxutils import escape

import requests

JRIVER_HOST = "fake-jriver:52199"
DAY = 86400


# --- the library -----------------------------------------------------------------

def _albums():
    """(album artist, album, year, genre, [(title, seconds, artist or None)])"""
    return [
        ("The Beatles", "Abbey Road", 1969, "Rock", [
            ("Come Together", 259), ("Something", 182), ("Here Comes The Sun", 185),
            ("Because", 165), ("Golden Slumbers", 91), ("The End", 139), ("Her Majesty", 23)]),
        ("The Beatles", "Help!", 1965, "Rock", [
            ("Help!", 138), ("Yesterday", 125), ("Ticket To Ride", 190), ("I've Just Seen A Face", 125)]),
        ("The Beatles", "Revolver", 1966, "Rock", [
            ("Taxman", 159), ("Eleanor Rigby", 128), ("Here, There And Everywhere", 145),
            ("Tomorrow Never Knows", 180)]),
        ("Kinks, The", "Something Else", 1967, "Rock", [
            ("Waterloo Sunset", 195), ("Death Of A Clown", 184), ("David Watts", 152)]),
        ("The Hollies", "Greatest Hits", 1973, "Pop", [
            ("Bus Stop", 172), ("Carrie Anne", 175), ("He Ain't Heavy, He's My Brother", 260),
            ("Long Cool Woman (In A Black Dress)", 199)]),
        ("Queen", "Greatest Hits", 1981, "Rock", [
            ("Bohemian Rhapsody", 355), ("Somebody To Love", 296), ("Don't Stop Me Now", 209)]),
        ("The Byrds", "Mr. Tambourine Man", 1965, "Folk Rock", [
            ("Mr. Tambourine Man", 149), ("Turn! Turn! Turn!", 229), ("Eight Miles High", 215)]),
        ("Badfinger", "Straight Up", 1971, "Rock", [
            ("Baby Blue", 216), ("Day After Day", 191), ("Take It All", 268)]),
        ("George Harrison", "All Things Must Pass", 1970, "Rock", [
            ("My Sweet Lord", 278), ("What Is Life", 264), ("Isn't It A Pity", 425)]),
        ("Jimi Hendrix", "Electric Ladyland", 1968, "Rock", [
            ("All Along The Watchtower", 241), ("Crosstown Traffic", 145), ("Voodoo Child (Slight Return)", 312)]),
        ("Simon & Garfunkel", "Bridge Over Troubled Water", 1970, "Folk", [
            ("Bridge Over Troubled Water", 292), ("The Boxer", 308), ("Cecilia", 175)]),
        ("The Rolling Stones", "Out Of Our Heads", 1965, "Rock", [
            ("(I Can't Get No) Satisfaction", 223), ("The Last Time", 221), ("Play With Fire", 134)]),
        ("Pink Floyd", "Meddle", 1971, "Rock", [
            ("One Of These Days", 357), ("A Pillow Of Winds", 310), ("Fearless", 368), ("Echoes", 1411)]),
        ("Sigur Rós", "Takk...", 2005, "Post-Rock", [
            ("Glósóli", 375), ("Hoppípolla", 268), ("Sæglópur", 492)]),
        ("David Guetta", "Sexy Chick", 2009, "Dance", [("Sexy Chick", 196)]),
        ("Various Artists", "Now 1965", 1965, "Pop", [
            ("Petula Clark - Downtown", 185, "Various Artists"), ("The Zombies - She's Not There", 145, "Various Artists")]),
        ("Angus & Julia Stone", "Down The Way", 2010, "Folk", [
            ("Big Jet Plane", 238, "Angus & Julia Stone"), ("Yellow Brick Road", 431, "Angus Stone;Julia Stone")]),
    ]


def build_library(now=None):
    now = now or time.time()
    rows, key = [], 1000
    for album_artist, album, year, genre, tracks in _albums():
        for n, t in enumerate(tracks, 1):
            title, seconds = t[0], t[1]
            artist = t[2] if len(t) > 2 else album_artist
            key += 1
            rows.append({
                "Key": str(key), "Name": title, "Artist": artist, "Album": album,
                "Album Artist (auto)": album_artist, "Disc #": "1", "Track #": str(n),
                "Duration": str(float(seconds)), "Last Played": "",
                "Rating": "", "Date (year)": str(year), "Number Plays": "0",
                "Date Imported": str(int(now - 400 * DAY)), "Genre": genre, "File Type": "flac",
                "Bit Depth": "24" if year > 2000 else "16", "Sample Rate": "44100",
                "Filename": f"F:\\Music\\{album_artist}\\{album}\\{n:02d} {title}.flac",
                "Description": "Singles:" if album_artist == "David Guetta" else "",
                "Media Type": "Audio"})
    return rows


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _fold(s):
    return strip_accents(s).lower()


def _mpl(rows, fields=None):
    out = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?><MPL Version=\"2.0\" Title=\"MCWS\">"]
    for row in rows:
        out.append("<Item>")
        for k, v in row.items():
            if fields and k not in fields:
                continue
            out.append(f"<Field Name=\"{escape(k)}\">{escape(str(v))}</Field>")
        out.append("</Item>")
    out.append("</MPL>")
    return "".join(out)


def _response(items, status="OK"):
    body = "".join(f"<Item Name=\"{escape(k)}\">{escape(str(v))}</Item>" for k, v in items.items())
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response Status=\"{status}\">{body}</Response>"


class Resp:
    """Enough of requests.Response for 24bit7."""
    def __init__(self, status=200, text="", data=None, headers=None):
        self.status_code = status
        self.text = text if data is None else json.dumps(data)
        self.headers = headers or {"Content-Type": "application/json" if data is not None else "text/xml"}
        self.content = self.text.encode("utf-8")
        self.ok = status < 400

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


# --- JRiver ----------------------------------------------------------------------

class Zone:
    def __init__(self, zid, name):
        self.id, self.name = zid, name
        self.playlist = []      # Playing Now keys
        self.pos = -1
        self.state = 0          # 0 stopped, 1 paused, 2 playing
        self.position_ms = 0    # how far into the current track
        self.dlna = False       # JRiver's ZoneDLNA flag
        self.volume = 1.0


class FakeJRiver:
    def __init__(self, zones=(("10001", "Speakers"), ("10002", "Kitchen"), ("10003", "Sonos"))):
        self.tracks = build_library()
        self.by_key = {r["Key"]: r for r in self.tracks}
        self.zones = {zid: Zone(zid, name) for zid, name in zones}
        self.zone_order = [zid for zid, _ in zones]
        self.current = self.zone_order[0]
        self.calls = []          # (path, params)
        self.up = True
        self.playlists = []
        keys = [r["Key"] for r in self.tracks]
        beatles = [r["Key"] for r in self.tracks if r["Artist"] == "The Beatles"]
        self.add_playlist("201", "Sunday Morning", "Sunday Morning", "Playlist", keys[10:16])
        self.add_playlist("202", "Road Trip", "Mixes\\Road Trip", "Playlist", keys[20:30])
        self.add_playlist("203", "60s Smartlist", "Smartlists\\60s Smartlist", "Smartlist", beatles)
        self.add_playlist("204", "Random Album", "Random Album\\Random Album", "Smartlist", keys[30:36])
        self.add_playlist("205", "Road Trip", "Smartlists\\Road Trip", "Smartlist", keys[0:5])   # shares a name

    # helpers for tests
    def add_playlist(self, pid, name, path, kind, keys):
        self.playlists.append({"ID": pid, "Name": name, "Path": path, "Type": kind, "keys": list(keys)})

    def key_of(self, artist, title):
        for r in self.tracks:
            if r["Name"] == title and (artist is None or r["Artist"] == artist):
                return r["Key"]
        raise KeyError((artist, title))

    def zone(self, name_or_id):
        for z in self.zones.values():
            if name_or_id in (z.id, z.name):
                return z
        raise KeyError(name_or_id)

    def play(self, zone_name, keys, pos=0, state=2):
        z = self.zone(zone_name)
        z.playlist, z.pos, z.state = [str(k) for k in keys], pos, state

    def mark_played(self, key, when):
        self.by_key[str(key)]["Last Played"] = str(int(when))

    def titles(self, zone_name):
        z = self.zone(zone_name)
        return [f"{self.by_key[k]['Artist']} - {self.by_key[k]['Name']}" for k in z.playlist]

    def calls_to(self, path):
        return [p for c, p in self.calls if c == path]

    # the web service
    def _zone_for(self, params):
        zid = str(params.get("Zone", "-1"))
        if zid == "-1":
            zid = self.current
        return self.zones.get(zid)

    def handle(self, method, path, params):
        self.calls.append((path, dict(params)))
        if not self.up:
            raise requests.ConnectionError("JRiver isn't running (fake)")
        if path == "Alive":
            return Resp(text=_response({"RuntimeGUID": "x", "LibraryVersion": "24", "ProgramName": "JRiver Media Center",
                                        "ProgramVersion": "34.0.20", "FriendlyName": "FAKE"}))
        if path == "Playback/Zones":
            items = {"NumberZones": len(self.zone_order), "CurrentZoneID": self.current,
                     "CurrentZoneIndex": self.zone_order.index(self.current)}
            for n, zid in enumerate(self.zone_order):
                items[f"ZoneID{n}"], items[f"ZoneName{n}"] = zid, self.zones[zid].name
                items[f"ZoneDLNA{n}"] = "1" if self.zones[zid].dlna else "0"
            return Resp(text=_response(items))
        if path == "Playback/Info":
            z = self._zone_for(params)
            if z is None:
                return Resp(text=_response({}, "Failure"))
            items = {"ZoneID": z.id, "ZoneName": z.name, "State": z.state, "PositionMS": z.position_ms,
                     "PlayingNowPosition": z.pos, "PlayingNowTracks": len(z.playlist)}
            if 0 <= z.pos < len(z.playlist):
                row = self.by_key[z.playlist[z.pos]]
                items.update(FileKey=row["Key"], Name=row["Name"], Artist=row["Artist"], Album=row["Album"])
            return Resp(text=_response(items))
        if path == "Playback/Playlist":
            z = self._zone_for(params)
            fields = (params.get("Fields") or "").split(",") or None
            return Resp(text=_mpl([self.by_key[k] for k in z.playlist], fields))
        if path == "Playback/PlayByKey":
            z = self._zone_for(params)
            keys = [k for k in str(params.get("Key", "")).split(",") if k]
            loc = params.get("Location")
            if loc == "End":
                z.playlist += keys
            elif loc == "Next":
                z.playlist[z.pos + 1:z.pos + 1] = keys
            else:
                z.playlist, z.pos, z.state, z.position_ms = keys, 0, 2, 0
            return Resp(text=_response({}))
        if path == "Playback/Stop":
            self._zone_for(params).state = 0
            return Resp(text=_response({}))
        if path == "Playback/Pause":
            z = self._zone_for(params)
            if z.playlist:
                want = str(params.get("State", "-1"))
                z.state = 1 if want == "1" or (want == "-1" and z.state == 2) else 2
            return Resp(text=_response({}))
        if path == "Playback/Volume":
            z = self._zone_for(params)
            if "Level" in params:
                z.volume = float(params["Level"])
            return Resp(text=_response({"Level": z.volume}))
        if path == "Playback/PlayByIndex":
            z = self._zone_for(params)
            z.pos, z.state, z.position_ms = int(params.get("Index", 0)), 2, 0
            return Resp(text=_response({}))
        if path == "Playback/Position":
            z = self._zone_for(params)
            if "Position" in params:
                z.position_ms = int(params["Position"])
            return Resp(text=_response({"Position": z.position_ms}))
        if path == "Playback/EditPlaylist":
            z = self._zone_for(params)
            if params.get("Action") == "Remove":
                i = int(params.get("Source"))
                if 0 <= i < len(z.playlist):
                    del z.playlist[i]
                    if i < z.pos:
                        z.pos -= 1
            return Resp(text=_response({}))
        if path == "Playback/Next":
            z = self._zone_for(params)
            if z.pos + 1 < len(z.playlist):
                z.pos += 1
            return Resp(text=_response({}))
        if path == "Playback/PlayPlaylist":
            z = self._zone_for(params)
            pl = next(p for p in self.playlists if p["ID"] == str(params.get("Playlist")))
            z.playlist, z.pos, z.state = list(pl["keys"]), 0, 2
            return Resp(text=_response({}))
        if path == "Playlists/Add":
            name = str(params.get("Path", ""))
            old = next((p for p in self.playlists if p["Path"] == name and p["Type"] == "Playlist"), None)
            if old is not None and params.get("CreateMode") == "Overwrite":
                old["keys"], pid = [], old["ID"]
            else:
                pid = str(300 + len(self.playlists))
                self.add_playlist(pid, name.split("\\")[-1], name, "Playlist", [])
            return Resp(text=_response({"PlaylistID": pid}))
        if path == "Playlist/AddFile":
            return Resp(status=500, text="")   # as on a real JRiver: AddFiles is the one that works
        if path == "Playlist/AddFiles":
            pl = next(p for p in self.playlists if p["ID"] == str(params.get("Playlist")))
            pl["keys"] += [k for k in str(params.get("Keys", "")).split(",") if k]
            return Resp(text=_response({}))
        if path == "Playlists/List":
            body = "".join("<Item>" + "".join(f"<Field Name=\"{k}\">{escape(v)}</Field>"
                                              for k, v in p.items() if k != "keys") + "</Item>"
                           for p in self.playlists)
            return Resp(text=f"<Response Status=\"OK\">{body}</Response>")
        if path == "Playlist/Files":
            pl = next((p for p in self.playlists if p["ID"] == str(params.get("Playlist"))), None)
            if pl is None:
                return Resp(text=_response({}, "Failure"))
            return Resp(text=_mpl([self.by_key[k] for k in pl["keys"]], ["Key"]))
        if path == "Files/Search":
            return self._search(params)
        return Resp(404, "unknown MCWS call")

    def _search(self, params):
        query = str(params.get("Query", "")).strip()
        rows = list(self.tracks)
        n = None
        if "~sort=[Last Played]-d" in query:
            rows = sorted((r for r in rows if r["Last Played"]), key=lambda r: -float(r["Last Played"]))
        m = re.search(r"~n=(\d+)", query)
        if m:
            n = int(m.group(1))
        words = re.sub(r"\[Media Type\]=\[Audio\]|~\S+", "", query).split()
        if words:
            want = [_fold(w) for w in words]
            rows = [r for r in rows
                    if all(w in _fold(" ".join((r["Artist"], r["Album Artist (auto)"], r["Album"], r["Name"])))
                           for w in want)]
        if n is not None:
            rows = rows[:n]
        fields = (params.get("Fields") or "").split(",") if params.get("Fields") else None
        if params.get("Action") == "JSON":
            return Resp(data=[{k: r[k] for k in (fields or r) if k in r} for r in rows])
        return Resp(text=_mpl(rows, fields))


# --- the music services ----------------------------------------------------------

# Artists the sources know that aren't in the library, and the names sources use
# that differ from the library's tags (credit matching both ways).
NOT_IN_LIBRARY = ["The Zombies", "Harry Nilsson", "The Move"]
SOURCE_NAME = {"Jimi Hendrix": "The Jimi Hendrix Experience", "Kinks, The": "The Kinks",
               "Simon & Garfunkel": "Simon and Garfunkel"}


class FakeWeb:
    def __init__(self, jriver):
        self.j = jriver
        self.calls = []                 # (service, detail)
        self.down = set()               # services answering with an error
        self.empty = set()              # services answering with nothing
        lib_artists = []
        for r in jriver.tracks:
            a = r["Album Artist (auto)"]
            if a not in lib_artists and a != "Various Artists":
                lib_artists.append(a)
        self.lib_artists = lib_artists
        self.artists = [SOURCE_NAME.get(a, a) for a in lib_artists] + NOT_IN_LIBRARY

    def similar_artists(self, artist):
        others = [a for a in self.artists if a.lower() != artist.lower()]
        return others

    def top_tracks(self, artist):
        lib = {SOURCE_NAME.get(a, a).lower(): a for a in self.lib_artists}
        tagged = lib.get(artist.lower()) or next((a for a in self.lib_artists if a.lower() == artist.lower()), None)
        titles = [r["Name"] for r in self.j.tracks if tagged and r["Album Artist (auto)"] == tagged]
        if artist in NOT_IN_LIBRARY:
            titles = [f"{artist} Hit {n}" for n in range(1, 6)]
        return titles + (["A Song Not In The Library"] if titles else [])

    def similar_tracks(self, artist, track):
        out = []
        for a in self.artists:
            if a.lower() == artist.lower():
                continue
            for t in self.top_tracks(a)[:2]:
                out.append([a, t])
        return out

    def handle(self, method, url, params, body):
        u = urllib.parse.urlparse(url)
        host, path = u.netloc, u.path
        service = {"ws.audioscrobbler.com": "lastfm", "api.deezer.com": "deezer", "musicbrainz.org": "musicbrainz",
                   "labs.api.listenbrainz.org": "listenbrainz", "api.listenbrainz.org": "listenbrainz",
                   "api.discogs.com": "discogs"}.get(host)
        if service is None:
            raise AssertionError(f"Unexpected network call: {method} {url}")
        self.calls.append((service, path, dict(params or {})))
        if service in self.down:
            raise requests.ConnectionError(f"{service} is down (fake)")
        empty = service in self.empty
        if service == "lastfm":
            m, artist = params.get("method"), params.get("artist", "")
            if m == "artist.getsimilar":
                names = [] if empty else self.similar_artists(artist)[:int(params.get("limit", 20))]
                return Resp(data={"similarartists": {"artist": [{"name": n} for n in names]}})
            if m == "artist.gettoptracks":
                names = [] if empty else self.top_tracks(artist)
                return Resp(data={"toptracks": {"track": [{"name": n, "playcount": 1000 - i}
                                                          for i, n in enumerate(names)]}})
            if m == "track.getsimilar":
                pairs = [] if empty else self.similar_tracks(artist, params.get("track", ""))
                return Resp(data={"similartracks": {"track": [{"name": t, "artist": {"name": a}} for a, t in pairs]}})
        if service == "deezer":
            if path == "/search/artist":
                q = params.get("q", "")
                return Resp(data={"data": [] if empty else [{"id": abs(hash(q.lower())) % 10**8, "name": q, "nb_fan": 9}]})
            m = re.match(r"/artist/(\d+)/(related|top)", path)
            if m:
                name = self._deezer_name(int(m.group(1)))
                if m.group(2) == "related":
                    names = [] if empty else self.similar_artists(name)[::-1][:int(params.get("limit", 20))]
                    return Resp(data={"data": [{"name": n} for n in names]})
                titles = [] if empty else self.top_tracks(name)
                return Resp(data={"data": [{"title": t} for t in titles]})
        if service == "musicbrainz":
            if path.startswith("/ws/2/artist"):
                name = re.sub(r'^artist:"|"$', "", params.get("query", ""))
                known = any(name.lower() == a.lower() for a in self.artists) or name in self.lib_artists
                return Resp(data={"artists": [{"id": "mbid:" + name.lower()}] if known and not empty else []})
            return Resp(data={})
        if service == "listenbrainz":
            if path == "/similar-artists/json":
                mbid = body[0]["artist_mbids"][0]
                names = [] if empty else self.similar_artists(mbid[5:])
                return Resp(data=[{"data": [{"name": n} for n in names]}])
            if path.startswith("/1/popularity/top-recordings-for-artist/"):
                name = path.rsplit("/", 1)[1][5:]
                return Resp(data=[] if empty else [{"recording_name": t} for t in self.top_tracks(name)])
            if path == "/acr-lookup/json":
                a, t = params.get("artist_credit_name", ""), params.get("recording_name", "")
                return Resp(data=[] if empty else [{"recording_mbid": f"rec:{a}|{t}"}])
            if path == "/similar-recordings/json":
                a, t = body[0]["recording_mbids"][0][4:].split("|", 1)
                pairs = [] if empty else self.similar_tracks(a, t)[::-1]
                return Resp(data=[{"recording_mbid": f"rec:{x}|{y}", "recording_name": y, "artist_credit_name": x}
                                  for x, y in pairs])
        return Resp(404, "not faked")

    def _deezer_name(self, artist_id):
        for name in self.artists + self.lib_artists:
            if abs(hash(name.lower())) % 10**8 == artist_id:
                return name
        return ""


# --- the AI ----------------------------------------------------------------------

class FakeAI:
    """Replaces anthropic.Anthropic. Replies to each 24bit7 prompt by what it asks for."""
    def __init__(self, web):
        self.web = web
        self.calls = []                 # (model, prompt/system first line)
        self.script = []                # queued replies (text, stop_reason) used before the defaults
        self.remove = []                # moderator: indexes to remove
        self.fail = None                # an exception to raise
        outer = self

        class Client:
            def __init__(self, api_key=None, **kw):
                self.messages = SimpleNamespace(create=outer.create)
        self.Client = Client

    def create(self, model=None, max_tokens=None, messages=None, system=None, **kw):
        prompt = messages[0]["content"] if messages else ""
        self.calls.append((model, (system if isinstance(system, str) else "")[:80] or prompt[:80], kw))
        self.sent = getattr(self, "sent", []) + [str(prompt)]
        if self.fail:
            raise self.fail
        if self.script:
            text, stop = self.script.pop(0)
        else:
            text, stop = self._answer(prompt, system), "end_turn"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                               usage=SimpleNamespace(input_tokens=100, output_tokens=len(text) // 3))

    def _answer(self, prompt, system):
        if system and "playlist moderator" in system:
            listed = dict(re.findall(r"^(\d+)\. (.+)$", prompt.split("Candidates:", 1)[-1], re.M))
            out = []
            for i in self.remove:
                artist, _, title = listed.get(str(i), " - ").partition(" - ")
                out.append({"number": i, "artist": artist, "title": title, "reason": "too loud for the seed"})
            return json.dumps({"remove": out})
        m = re.search(r'most similar to "(.+?)", most similar first', prompt)
        if m:
            return json.dumps(self.web.similar_artists(m.group(1)))
        m = re.search(r'most popular songs by "(.+?)"', prompt)
        if m:
            return json.dumps(self.web.top_tracks(m.group(1)))
        m = re.search(r'songs most similar to "(.+?)" by (.+?), most similar first', prompt)
        if m:
            return json.dumps([{"artist": a, "track": t} for a, t in self.web.similar_tracks(m.group(2), m.group(1))],
                              separators=(",", ":"))
        if "shared tone" in prompt:
            return "Warm late-70s disco and funk, mid-tempo, upbeat"
        if "move from there" in prompt:
            pairs = [(r["Artist"], r["Name"]) for r in self.web.j.tracks if r["Artist"] != "Various Artists"][1::2]
            return json.dumps([{"artist": a, "track": t} for a, t in pairs])
        if "playlist moods" in prompt:
            return json.dumps(["Sunday morning coffee", "Late night drive", "Summer garden party"])
        if "fit this mood" in prompt:
            pairs = [(r["Artist"], r["Name"]) for r in self.web.j.tracks if r["Artist"] != "Various Artists"][::2]
            return json.dumps([{"artist": a, "track": t} for a, t in pairs] + [{"artist": "Nobody", "track": "Nothing"}])
        if "Console" in prompt or "console" in prompt:
            return "That track was dropped because it wasn't in your library."
        return "[]"


# --- YouTube Music ---------------------------------------------------------------

class FakeYTMusic:
    def __init__(self, web):
        self.web = web
        self.calls = []

    def search(self, query, filter=None, limit=5, **kw):
        self.calls.append(("search", query))
        for a in self.web.artists:
            if query.lower().startswith(a.lower() + " "):
                title = query[len(a) + 1:]
                return [{"videoId": f"vid-{a}-{title}"[:40], "title": title, "artists": [{"name": a}]}]
        return []

    def get_watch_playlist(self, videoId=None, limit=50, radio=False, **kw):
        self.calls.append(("watch", videoId))
        a, t = videoId[4:].split("-", 1) if "-" in videoId[4:] else ("", "")
        pairs = self.web.similar_tracks(a, t)
        return {"tracks": [{"videoId": f"vid{n}", "title": t2, "artists": [{"name": a2}]}
                           for n, (a2, t2) in enumerate(pairs)]}

    def get_song(self, videoId):
        return {"videoDetails": {"title": videoId}}


# --- wiring ----------------------------------------------------------------------

def install(monkeypatch, jriver, web):
    """Routes every requests call: MCWS to the fake JRiver, the music services to FakeWeb."""
    def request(self, method, url, params=None, data=None, headers=None, json=None, **kw):
        u = urllib.parse.urlparse(url)
        if u.netloc == JRIVER_HOST:
            path = u.path.split("/MCWS/v1/", 1)[1]
            p = dict(urllib.parse.parse_qsl(u.query))
            p.update(params or {})
            return jriver.handle(method, path, p)
        return web.handle(method, url, params or dict(urllib.parse.parse_qsl(u.query)), json)
    monkeypatch.setattr(requests.Session, "request", request)
