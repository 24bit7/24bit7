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
from i18n import t, tn

GOOD = 0.80              # a match at least this close counts as found
REFRESH_MINUTES = 30     # how often the library is re-read in the background
AUDIO = "[Media Type]=[Audio]"
FIELDS = ("Key,Name,Artist,Album,Album Artist (auto),Disc #,Track #,Duration,BPM,Last Played,"
          # for Settings > Filters rules
          "Rating,Date (year),Number Plays,Date Imported,Genre,File Type,Bit Depth,Sample Rate,Filename")

_lock = threading.Lock()
_albums = {}             # (album, album artist) -> [track rows]
_artists = {}            # normalised artist -> artist as tagged
_tracks = []
_songs = {}              # normalised title -> [(title, artist, key, album, album artist, compilation)]
_song_titles = []
_playlists = []
_loaded_at = 0.0
_closers = {}            # key -> (seconds, name, artist) for the last track of each album
_played = {}             # key -> when JRiver last played it (Unix seconds), for tracks it has played
_played_unread = False   # True when the library had Last Played values but none could be read
_by_key = {}             # key -> track row, for filter rules
_copies = {}             # key -> every copy you own of that song, best first (see copies())
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
    text = engine.fold_name_chars(text)                          # the character rules every comparison shares
    if _APOSTROPHE.search(text):   # only when there is one: the library runs every name through this
        text = _N_JOINER.sub(" n ", text)                        # Rock'n'Roll: the n stands alone, as 'and'
        text = _APOSTROPHE.sub("", text)                         # Jane's = Jane’s = Janes, D'Angelo = Dangelo
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r",\s*the\s*$", "", text.strip())            # Kooks, The
    text = text.replace("&", " and ").replace("+", " and ")
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)               # (Remastered), [Deluxe Edition]
    text = re.sub(r"(\d),(\d{3})\b", r"\1\2", text)             # 1,000 -> 1000
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = _spell_numbers(text)
    words = ["okay" if w == "ok" else w for w in text.split() if w != "and"]
    if words and words[0] == "the":
        words = words[1:]
    # a lone 'n' left after the initials join up is 'and' (Guns N' Roses, Salt-N-Pepa), so dropped
    # like it; N.W.A keeps its n, and Youssou N'Dour's became 'ndour' with the apostrophe
    return " ".join(w for w in _join_initials(words) if w != "n")


# Apostrophes go without leaving a gap, straight or curly: a tag may use either
_APOSTROPHE = re.compile(r"['’‘`]")
_N_JOINER = re.compile(r"(?<=\w)\s*['’‘`]n['’‘`]\s*(?=\w)", re.I)


def _join_initials(words):
    """
    Joins a run of two or more single letters into one word, so 'U.N.K.L.E.'
    ('u n k l e' once the dots go) and a source's 'UNKLE' compare the same.
    Applied to both sides of every comparison, so it never favours either.
    """
    out, run = [], []
    for w in words + [""]:
        if len(w) == 1 and w.isalpha():
            run.append(w)
            continue
        out.extend(["".join(run)] if len(run) > 1 else run)
        run = []
        if w:
            out.append(w)
    return out


_BRACKET_DROP_START = re.compile(r"\s*(feat\.?|featuring|ft\.?|with|from)\b", re.I)
_BRACKET_DROP_ANY = re.compile(r"\b(remix|bonus|deluxe|" + engine.VERSION_WORDS.strip("()") + r")\b", re.I)


def _unwrap_brackets(title):
    """
    'Long Cool Woman (in a Black Dress)' -> 'Long Cool Woman  in a Black Dress '.
    Brackets holding a version tag or a credit are dropped instead, as norm() does.
    """
    def keep(m):
        inner = m.group(0)[1:-1]
        if _BRACKET_DROP_START.match(inner) or _BRACKET_DROP_ANY.search(inner):
            return " "
        return f" {inner} "
    return re.sub(r"\(.*?\)|\[.*?\]", keep, title or "")


# A dropped "g" at the end of a word, straight or curly apostrophe: Lightnin', Lovin', Ramblin'
_DROPPED_G = re.compile(r"(?<=[a-z])in['\u2019\u2018`](?![a-z])", re.I)


def title_keys(title):
    """
    Every form a title is filed and looked up under: brackets removed (as
    always), and brackets unwrapped with their words kept when they're part of
    the title. Most titles have no brackets and give one key.
    Each form is also filed with a dropped "g" restored (Lightnin' -> Lightning).
    """
    keys = []
    for form in (title, _unwrap_brackets(title)):
        for k in (norm(form), norm(_DROPPED_G.sub("ing", form or ""))):
            if k and k not in keys:
                keys.append(k)
    return keys


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
    started = time.time()
    r = _get("Files/Search", Query=AUDIO, Action="JSON", Fields=FIELDS)
    answered = time.time()
    try:
        # strict=False: a control character in a tag (a pasted line break, a stray byte from an
        # old ripper) is kept as it is, instead of making the whole library unreadable
        rows = [{k: str(v) for k, v in row.items()} for row in json.loads(r.text, strict=False)]
        engine.debug(f"Library: JRiver answered in {answered - started:.1f} s, "
                     f"decoding {len(rows):,} tracks took {time.time() - answered:.1f} s")
        return rows
    except ValueError as e:
        print(t("Note: JRiver's library list couldn't be read as JSON ({e}), so reading it as MPL instead.", e=e))
    r = _get("Files/Search", Query=AUDIO, Action="MPL")
    return [{f.get("Name"): f.text or "" for f in item.findall("Field")}
            for item in ET.fromstring(engine.xml_safe(r.text)).findall(".//Item")]


def _read_playlists():
    out = []
    for item in ET.fromstring(engine.xml_safe(_get("Playlists/List").text)).findall("Item"):
        fields = {f.get("Name"): f.text or "" for f in item.findall("Field")}
        if fields.get("Type") in ("Playlist", "Smartlist"):
            out.append(fields)
    return out


def load():
    """Reads the whole library from JRiver. Returns a line for the log."""
    global _albums, _artists, _tracks, _songs, _song_titles, _playlists, _loaded_at, _closers
    global _played, _played_unread, _by_key, _copies
    engine.refresh_settings_if_changed()
    started = time.time()
    tracks = _read_tracks()
    playlists = _read_playlists()
    albums, artists, songs, groups, normed = {}, {}, {}, {}, {}
    for row in tracks:
        title, artist = (row.get("Name") or "").strip(), (row.get("Artist") or "").strip()
        album, album_artist = row.get("Album") or "", row.get("Album Artist (auto)") or ""
        if title:
            keys = title_keys(title)
            for k in keys:
                songs.setdefault(k, []).append((title, artist, row["Key"], album, album_artist, False))
            if keys and artist:
                if artist not in normed:
                    normed[artist] = norm(artist)
                live = "live" in album.lower() and "live" in norm(album).split()   # another song, not a copy
                groups.setdefault((normed[artist], keys[0], live), []).append(
                    (title, artist, row["Key"], album, album_artist, False))
        if " - " in title:   # a compilation track named 'Artist - Title'
            by, just_title = (part.strip() for part in title.split(" - ", 1))
            if by and just_title:
                for k in title_keys(just_title):
                    songs.setdefault(k, []).append((just_title, by, row["Key"], album, album_artist, True))
        name = (row.get("Album") or "").strip()
        if name:
            albums.setdefault((name, row.get("Album Artist (auto)", "")), []).append(row)
        for artist in (row.get("Artist") or "").split(";"):
            artist = artist.strip()
            if artist:
                artists.setdefault(norm(artist), artist)
    closers = {}
    for rows in albums.values():
        if len(rows) < 2:
            continue   # a lone track can't be told apart from a single
        last = max(rows, key=track_order)
        if track_order(last)[1] <= 0:
            continue   # no track numbers, so no telling which one is last
        try:
            seconds = float(last.get("Duration") or 0)
        except ValueError:
            continue
        closers[str(last["Key"])] = (seconds, last.get("Name") or "", last.get("Artist") or "")
    played, seen = {}, 0
    for row in tracks:
        raw = (row.get("Last Played") or "").strip()
        if raw and raw != "0":
            seen += 1
            when = played_time(raw)
            if when:
                played[str(row["Key"])] = when
    by_key = {str(row.get("Key")): row for row in tracks}
    copies_of = {}
    for (artist_norm, _, _), entries in groups.items():
        if len(entries) > 1:
            best = [str(e[2]) for e in sorted(entries, key=lambda e: _album_version_first(e, artist_norm))]
            for k in best:
                copies_of[k] = best
    with _lock:
        _albums, _artists, _tracks, _playlists = albums, artists, tracks, playlists
        _by_key = by_key
        _copies = copies_of
        _closers = closers
        _played, _played_unread = played, bool(seen and not played)
        _songs, _song_titles = songs, [tval for tval in songs if tval]
        _loaded_at = time.time()
    engine.debug(f"Library: {len(tracks):,} tracks read and indexed in {time.time() - started:.1f} s")
    return (f"Library read for voice: {len(albums)} albums, {len(playlists)} playlists "
            f"({time.time() - started:.1f} s)")


def _refresh_loop():
    global _timer
    try:
        print(load())
    except Exception as e:
        print(t("[Voice] Couldn't read the library from JRiver ({e}). Trying again later.", e=e))
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


def played_time(raw):
    """
    JRiver's Last Played as Unix seconds, or None. It can arrive as Unix seconds,
    as JRiver's own day count (days since 30 December 1899, like a spreadsheet),
    or as a formatted date, depending on the version and how it's asked for.
    """
    from datetime import datetime
    try:
        value = float(raw)
    except ValueError:
        value = None
    if value is not None:
        if value > 100000000:          # Unix seconds (after 1973)
            return value
        if 20000 < value < 100000:     # days since 30 December 1899
            return (value - 25569) * 86400
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).timestamp()
        except ValueError:
            continue
    return None


def track_row(key):
    """A track's fields from the library held in memory, or None."""
    with _lock:
        return _by_key.get(str(key))


def last_played(key):
    """When JRiver last played this track (Unix seconds), or None if never (or unknown)."""
    with _lock:
        return _played.get(str(key))


def copies(key):
    """
    Every copy you own of this track: the key itself first, then the others the way
    find_track_key prefers them (studio album first). A copy is the same artist and title
    as tagged, such as a stereo MP3 and a surround FLAC of one album; a live recording
    only counts as a copy of another live one. Just [key] for a track with no copies.
    """
    with _lock:
        best = _copies.get(str(key))
    if not best:
        return [str(key)]
    return [str(key)] + [k for k in best if k != str(key)]


def last_played_any(key):
    """When JRiver last played any copy of this track (Unix seconds), or None."""
    with _lock:
        times = [_played[k] for k in (_copies.get(str(key)) or [str(key)]) if k in _played]
    return max(times) if times else None


def played_dates_unreadable():
    """True if the library has Last Played values that couldn't be read, so the filter can't work."""
    with _lock:
        return _played_unread


def closer_info(key):
    """(seconds, name, artist) if the track is the last on its album, else None."""
    with _lock:
        return _closers.get(str(key))


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
        entries = [(tval, e) for tval in titles for e in _songs[tval]]
    if not entries:
        return False, []
    if by:
        ranked = sorted(((difflib.SequenceMatcher(None, want, tval).ratio() + _artist_score(by, e[1])) / 2, e)
                        for tval, e in entries)
        best_score = ranked[-1][0]
        if best_score < GOOD:
            return False, []
        best = [e for s, e in ranked if s == best_score]
        pick = sorted(best, key=lambda e: _album_version_first(e, norm(e[1])))[0]
        return True, [(pick[0], pick[1], pick[2])]
    copies = [e for tval, e in entries if tval == titles[0]]
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
    wants = title_keys(title)
    if not wants:
        return None
    entries, seen = [], set()

    def add(found):
        for e in found:
            if (e[2], e[5]) not in seen:   # the same file can sit under two keys
                seen.add((e[2], e[5]))
                entries.append(e)

    with _lock:
        for w in wants:
            add(_songs.get(w, []))
        if not entries:
            for w in wants:
                for tval in difflib.get_close_matches(w, _song_titles, n=3, cutoff=engine.NEAR_TITLE):
                    add(_songs[tval])
    matches = [e for e in entries if _artist_score(artist, e[1]) >= GOOD]
    if not matches:
        # 'Mark Ronson feat. Amy Winehouse' against a tag of 'Mark Ronson' (or the other
        # way round): compare the first-named acts, the title having matched already
        matches = [e for e in entries if _primary_match(artist, e[1])]
        if matches:
            engine.debug(f"Matched on primary artist: {artist} - {title} (as {matches[0][1]})")
    if not matches:
        # 'Jimi Hendrix' against a tag of 'The Jimi Hendrix Experience': the source's
        # artist as whole words inside the tag, the title having matched already
        matches = [e for e in entries if _band_match(artist, e[1])]
        if matches:
            engine.debug(f"Matched on band name: {artist} - {title} (as {matches[0][1]})")
    if not matches:
        return None
    return sorted(matches, key=lambda e: _album_version_first(e, norm(e[1])))[0][2]


def _credit_words(text):
    """A credit as lower-case words, keeping 'the' and 'and' ('&' and '+' become 'and')."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower().strip()
    m = re.match(r"^(.*),\s*the$", text)                       # Kooks, The -> the kooks
    if m:
        text = "the " + m.group(1)
    text = text.replace("&", " and ").replace("+", " and ")
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)
    return re.sub(r"[^a-z0-9 ]", " ", text).split()


def _band_holds(short, long_):
    """
    True when long_ is a band credit built round short, in one of three shapes:
      The Jimi Hendrix Experience  'The' + the name + one or two band words
      Bob Marley & The Wailers     the name, then and / & / +
      Bob Marley & The Wailers     and / & / + [the], then the name, at the end ('The Wailers')
    Anything else, 'of' included ('Eagles of Death Metal'), or a bare suffix with no
    'The' ('Boston Pops'), doesn't count.
    """
    s, l = _credit_words(short), _credit_words(long_)
    if s[:1] == ["the"]:
        s = s[1:]
    core_l = l[1:] if l[:1] == ["the"] else l
    if not s or s == core_l or len(" ".join(s)) < 3:
        return False
    n = len(s)
    for i in range(len(l) - n + 1):
        if l[i:i + n] != s:
            continue
        before, after = l[:i], l[i + n:]
        if before == ["the"] and 1 <= len(after) <= 2 and not ({"of", "and"} & set(after)):
            return True
        if after[:1] == ["and"] and before in ([], ["the"]):
            return True
        if not after and (before[-1:] == ["and"] or before[-2:] == ["and", "the"]):
            return True
    return False


def _band_match(artist, tagged):
    """
    True when the source's credit and a tag are the same act inside a band credit,
    either way round: 'The Jimi Hendrix Experience' against a tag of 'Jimi Hendrix',
    or 'Jimi Hendrix' against 'The Jimi Hendrix Experience'. Only used after the full
    credit and the first-named act have missed, and the title has matched.
    """
    return any(_band_holds(artist, part) or _band_holds(part, artist)
               for part in (tagged or "").split(";") if part.strip())


def _primary_match(artist, tagged):
    """True when the first-named act of the source's credit matches the tag's."""
    want = engine.primary_artist(artist) or artist
    return any(score(want, engine.primary_artist(part) or part) >= GOOD
               for part in (tagged or "").split(";") if part.strip())


def suggest_artist(typed):
    """
    For an artist typed into Search that isn't in the library: the library artist it most likely
    means, or None. The same words in another order ('eleven finger' for Finger Eleven) first, then
    the one clear nearest name. Only ever offered, never used without asking.
    """
    want = norm(typed)
    if not want:
        return None
    ensure_loaded()
    with _lock:
        if want in _artists:
            return None
        words = sorted(want.split())
        swapped = [a for n, a in _artists.items() if sorted(n.split()) == words]
        if len(swapped) == 1:
            return swapped[0]
        ranked = sorted(((score(typed, a), a) for a in _artists.values()), key=lambda x: -x[0])
    if not ranked or ranked[0][0] < GOOD or (len(ranked) > 1 and ranked[1][0] == ranked[0][0]):
        return None
    return ranked[0][1]


FILLER = {"songs", "song", "tracks", "track", "music", "by", "the", "of", "from", "some", "stuff"}


def artist_in_text(text):
    """
    The library artist named somewhere in free text, for "only chill Led Zeppelin": (artist as
    tagged, the other words), or (None, "") when no artist you own is named. The words must
    appear whole and in order, with or without the gaps between them: Alexa writes AC/DC as
    'ACDC' (issue #12), and GusGus may be tagged 'Gus Gus'. The longest name wins ('Guns N
    Roses' over 'Roses'); between names of the same length, the artist with more tracks. Names
    under three letters are ignored, as they turn up inside ordinary words. The other words come
    back without filler ('songs', 'by'), so an empty string means no mood was given.
    """
    words = norm(text).split()
    if not words:
        return None, ""
    ensure_loaded()
    with _lock:
        squashed = {}
        for n, a in _artists.items():
            if len(n) >= 3:
                squashed.setdefault(n.replace(" ", ""), []).append((n, a))
        found = []   # (normalised name, artist as tagged, where its words start and end)
        for i in range(len(words)):
            for j in range(i + 1, min(len(words), i + 8) + 1):
                found += [(n, a, i, j) for n, a in squashed.get("".join(words[i:j]), [])]
        if not found:
            return None, ""
        size = {}
        if len({f[0] for f in found}) > 1:
            wanted = {f[0] for f in found}
            for row in _tracks:
                for a in (row.get("Artist") or "").split(";"):
                    n = norm(a)
                    if n in wanted:
                        size[n] = size.get(n, 0) + 1
    n, artist, at, end = max(found, key=lambda f: (len(f[0].split()), size.get(f[0], 0)))
    rest = [w for w in words[:at] + words[end:] if w not in FILLER]
    return artist, " ".join(rest)


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
