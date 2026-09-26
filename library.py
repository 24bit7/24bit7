"""
24bit7 - the library, held in memory for voice commands.

Every audio file's key, name, artist, album and track number is read from JRiver
once (about a second for a large library), then refreshed quietly in the
background, so a voice command matches instantly and new albums still turn up.

It answers four questions for voice.py:
  find_album("okay computer")            -> an album, or several that share the title
  find_song("creep")                     -> a track, or several artists who share the title
  find_playlist("sunday morning")        -> a JRiver playlist or smartlist
  artist_tracks("radiohead")             -> every track by that artist, compilations too

Matching is forgiving, because speech arrives in lower case with no punctuation:
"okay" is "OK", "sixty nine" is "69", "third" is "3rd", "the kooks" is "Kooks, The".
"""

import difflib
import json
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET

import requests

import engine

GOOD = 0.80              # a match at least this close counts as found
REFRESH_MINUTES = 30     # how often the library is re-read in the background
AUDIO = "[Media Type]=[Audio]"
FIELDS = "Key,Name,Artist,Album,Album Artist (auto),Disc #,Track #"

_lock = threading.Lock()
_albums = {}             # (album, album artist) -> [track rows]
_artists = {}            # normalised artist -> artist as tagged
_tracks = []
_songs = {}              # normalised title -> [(title, artist, key, album, album artist, compilation)]
_song_titles = []
_playlists = []
_loaded_at = 0.0
_timer = None


# --- numbers ------------------------------------------------------------------

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_ORDINAL_ENDS = {"one": "first", "two": "second", "three": "third", "five": "fifth",
                 "eight": "eighth", "nine": "ninth", "twelve": "twelfth"}


def _under_100(n):
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])


def number_words(n):
    """69 -> 'sixty nine', 1999 -> 'nineteen ninety nine' (said as a year), 2004 -> 'two thousand four'."""
    if n < 100:
        return _under_100(n)
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + ("" if rest == 0 else " " + _under_100(rest))
    if (1100 <= n <= 1999 or 2010 <= n <= 2099) and n % 100 != 0:
        return _under_100(n // 100) + " " + (("oh " + _ONES[n % 100]) if n % 100 < 10 else _under_100(n % 100))
    if n < 10000:
        rest = n % 1000
        return _ONES[n // 1000] + " thousand" + ("" if rest == 0 else " " + number_words(rest))
    return str(n)


def ordinal_words(n):
    words = number_words(n).split()
    last = words[-1]
    if last in _ORDINAL_ENDS:
        words[-1] = _ORDINAL_ENDS[last]
    elif last.endswith("y"):
        words[-1] = last[:-1] + "ieth"
    else:
        words[-1] = last + "th"
    return " ".join(words)


def _spell_numbers(text):
    text = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: ordinal_words(int(m.group(1))), text)
    return re.sub(r"\b\d+\b", lambda m: number_words(int(m.group())), text)


# --- names ---------------------------------------------------------------------

def norm(text):
    """Both sides of a comparison go through this: what Alexa hears and what the tags say."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r",\s*the\s*$", "", text.strip())            # Kooks, The
    text = text.replace("&", " and ").replace("+", " and ")
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)               # (Remastered), [Deluxe Edition]
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", text)             # 1,000 -> 1000
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = _spell_numbers(text)
    words = ["okay" if w == "ok" else w for w in text.split() if w != "and"]
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def score(heard, name):
    a, b = norm(heard), norm(name)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def spoken(name):
    """How Alexa should say a tagged name: 'Kooks, The' -> 'The Kooks'."""
    m = re.match(r"^(.*?),\s*(the)\s*$", name or "", re.I)
    return f"The {m.group(1).strip()}" if m else (name or "")


# --- loading -------------------------------------------------------------------

def _get(path, **params):
    return requests.get(f"{engine.JRIVER_BASE}/{path}", params=params, auth=engine.AUTH, timeout=60)


def _read_tracks():
    r = _get("Files/Search", Query=AUDIO, Action="JSON", Fields=FIELDS)
    try:
        return [{k: str(v) for k, v in row.items()} for row in json.loads(r.text)]
    except ValueError:
        pass
    r = _get("Files/Search", Query=AUDIO, Action="MPL")
    return [{f.get("Name"): f.text or "" for f in item.findall("Field")}
            for item in ET.fromstring(r.text).findall(".//Item")]


def _read_playlists():
    out = []
    for item in ET.fromstring(_get("Playlists/List").text).findall("Item"):
        fields = {f.get("Name"): f.text or "" for f in item.findall("Field")}
        if fields.get("Type") in ("Playlist", "Smartlist"):
            out.append(fields)
    return out


def load():
    """Reads the whole library from JRiver. Returns a line for the log."""
    global _albums, _artists, _tracks, _songs, _song_titles, _playlists, _loaded_at
    engine.refresh_settings_if_changed()
    started = time.time()
    tracks = _read_tracks()
    playlists = _read_playlists()
    albums, artists, songs = {}, {}, {}
    for row in tracks:
        title, artist = (row.get("Name") or "").strip(), (row.get("Artist") or "").strip()
        album, album_artist = row.get("Album") or "", row.get("Album Artist (auto)") or ""
        if title:
            songs.setdefault(norm(title), []).append((title, artist, row["Key"], album, album_artist, False))
        if " - " in title:   # a compilation track named 'Artist - Title'
            by, just_title = (part.strip() for part in title.split(" - ", 1))
            if by and just_title:
                songs.setdefault(norm(just_title), []).append((just_title, by, row["Key"], album, album_artist, True))
        name = (row.get("Album") or "").strip()
        if name:
            albums.setdefault((name, row.get("Album Artist (auto)", "")), []).append(row)
        for artist in (row.get("Artist") or "").split(";"):
            artist = artist.strip()
            if artist:
                artists.setdefault(norm(artist), artist)
    with _lock:
        _albums, _artists, _tracks, _playlists = albums, artists, tracks, playlists
        _songs, _song_titles = songs, [t for t in songs if t]
        _loaded_at = time.time()
    return (f"Library read for voice: {len(albums)} albums, {len(playlists)} playlists "
            f"({time.time() - started:.1f} s)")


def _refresh_loop():
    global _timer
    try:
        print(load())
    except Exception as e:
        print(f"[Voice] Couldn't read the library from JRiver ({e}). Trying again later.")
    _timer = threading.Timer(REFRESH_MINUTES * 60, _refresh_loop)
    _timer.daemon = True
    _timer.start()


def start():
    """Reads the library now in the background, then every REFRESH_MINUTES."""
    stop()
    threading.Thread(target=_refresh_loop, daemon=True).start()


def stop():
    global _timer
    if _timer is not None:
        _timer.cancel()
        _timer = None


def ensure_loaded():
    """A command that arrives before the first read waits for it (about a second)."""
    if not _loaded_at:
        load()


# --- finding ---------------------------------------------------------------------

def track_order(row):
    def num(v):
        m = re.match(r"\d+", v or "")
        return int(m.group()) if m else 0
    return num(row.get("Disc #")), num(row.get("Track #"))


def find_playlist(heard):
    """The closest playlist or smartlist, or None."""
    ensure_loaded()
    with _lock:
        ranked = sorted(((score(heard, p.get("Name", "")), p) for p in _playlists), key=lambda x: -x[0])
    return ranked[0][1] if ranked and ranked[0][0] >= GOOD else None


def find_album(heard):
    """
    'okay computer' or 'best of by cat stevens'. Returns (found, matches):
      (True, [(album, artist, keys in track order)])   one album
      (False, [(album, artist, None), ...])            several share the title; ask which
      (False, [])                                      nothing close enough
    """
    ensure_loaded()
    by = None
    if " by " in heard:
        heard, by = heard.rsplit(" by ", 1)
    with _lock:
        ranked = []
        for (name, artist), rows in _albums.items():
            s = score(heard, name)
            if by:
                s = (s + score(by, artist)) / 2
            ranked.append((s, name, artist, rows))
    ranked.sort(key=lambda x: -x[0])
    if not ranked or ranked[0][0] < GOOD:
        return False, []
    best = ranked[0]
    ties = [x for x in ranked if norm(x[1]) == norm(best[1]) and x[0] >= GOOD]
    if len(ties) > 1 and not by:
        return False, [(name, artist, None) for _, name, artist, _ in ties]
    keys = [row["Key"] for row in sorted(best[3], key=track_order)]
    return True, [(best[1], best[2], keys)]


def _artist_score(heard, artist):
    return max((score(heard, part) for part in (artist or "").split(";")), default=0.0)


def _album_version_first(entry, artist_norm):
    """Sorts an artist's copies of a song: studio album, then own compilation, then others."""
    _, artist, _, album, album_artist, compilation = entry
    live = "live" in norm(album).split()
    return compilation, norm(album_artist) != artist_norm, live


def find_song(heard):
    """
    'creep' or 'creep by radiohead'. Returns (found, matches) like find_album:
      (True, [(title, artist, key)])       one song (the album version if they have several)
      (False, [(title, artist, None), ...])  different artists share the title; ask which
      (False, [])                          nothing close enough
    """
    ensure_loaded()
    by = None
    if " by " in heard:
        heard, by = heard.rsplit(" by ", 1)
    want = norm(heard)
    with _lock:
        if want in _songs:
            titles = [want]
        else:
            titles = difflib.get_close_matches(want, _song_titles, n=5, cutoff=GOOD)
        entries = [(t, e) for t in titles for e in _songs[t]]
    if not entries:
        return False, []
    if by:
        ranked = sorted(((difflib.SequenceMatcher(None, want, t).ratio() + _artist_score(by, e[1])) / 2, e)
                        for t, e in entries)
        best_score = ranked[-1][0]
        if best_score < GOOD:
            return False, []
        best = [e for s, e in ranked if s == best_score]
        pick = sorted(best, key=lambda e: _album_version_first(e, norm(e[1])))[0]
        return True, [(pick[0], pick[1], pick[2])]
    copies = [e for t, e in entries if t == titles[0]]
    artists = {}
    for e in copies:
        artists.setdefault(norm(e[1]), []).append(e)
    if len(artists) > 1:
        return False, [(group[0][0], group[0][1], None) for group in artists.values()]
    artist_norm, group = next(iter(artists.items()))
    pick = sorted(group, key=lambda e: _album_version_first(e, artist_norm))[0]
    return True, [(pick[0], pick[1], pick[2])]


def find_track_key(artist, title):
    """
    The library key for a track named by a similarity source, or None. Title
    and artist both have to match (forgiving about case, version tags and
    'Kooks, The'), and compilation copies named 'Artist - Title' count. Where
    you own several copies, the studio album version wins.
    """
    ensure_loaded()
    want = norm(title)
    if not want:
        return None
    with _lock:
        entries = list(_songs.get(want, []))
        if not entries:
            close = difflib.get_close_matches(want, _song_titles, n=3, cutoff=0.9)
            entries = [e for t in close for e in _songs[t]]
    matches = [e for e in entries if _artist_score(artist, e[1]) >= GOOD]
    if not matches:
        return None
    return sorted(matches, key=lambda e: _album_version_first(e, norm(e[1])))[0][2]


def artist_tracks(heard):
    """
    Every track by the closest artist: tagged as the artist (multi-artist tags
    included), or on a compilation named 'Artist - Title'. Returns (artist, keys),
    or (None, []) when no artist is close enough.
    """
    ensure_loaded()
    with _lock:
        ranked = sorted(((score(heard, a), a) for a in _artists.values()), key=lambda x: -x[0])
        if not ranked or ranked[0][0] < GOOD:
            return None, []
        artist = ranked[0][1]
        target = norm(artist)
        keys = []
        for row in _tracks:
            tagged = [norm(a) for a in (row.get("Artist") or "").split(";")]
            name = row.get("Name") or ""
            if target in tagged or (" - " in name and norm(name.split(" - ", 1)[0]) == target):
                keys.append(row["Key"])
    return artist, keys
