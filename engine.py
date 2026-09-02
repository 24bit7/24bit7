import os
import sys
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import time
import random
import re
import csv
import unicodedata
import json
import sqlite3
from datetime import datetime


def app_dir():
    """
    The folder the app lives in, whether running as plain Python or as a
    frozen (PyInstaller) build. All data files (.env, database, legacy CSV)
    are anchored here, so launching from a shortcut, the taskbar or another
    working directory always finds the same files.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = app_dir()
VERSION = "1.0.1"
ENV_FILE = os.path.join(APP_DIR, ".env")
TARGET_ZONE = "-1"
CSV_FILE = os.path.join(APP_DIR, "FutureDiscoveries.csv")      # legacy log, imported once into the database
DB_FILE = os.path.join(APP_DIR, "24bit7.db")

_env_mtime = None   # modification time of .env when settings were last loaded


def _int_setting(name, default, lo, hi):
    """Reads an integer setting from .env, clamped to a range, falling back to the default."""
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        print(f"[Settings] {name}='{raw}' isn't a number, using {default}.")
        value = default
    return max(lo, min(hi, value))


def load_settings():
    """
    (Re)reads every setting from .env into module-level globals. Called once at
    import and again by refresh_settings_if_changed() whenever .env is edited,
    so both the GUI and the CLI pick up changes without a restart.
    """
    global AUTH, JRIVER_HOST, JRIVER_BASE, LASTFM_KEY, LISTENBRAINZ_TOKEN
    global DISCOGS_TOKEN, ANTHROPIC_API_KEY
    global SIMILAR_SOURCES, TOP_TRACK_SOURCES, LISTENBRAINZ_ALGORITHM_SETTING
    global DIGITAL_STORE, DEBUG, SIMILAR_ARTIST_LIMIT, TRACKS_PER_ARTIST_POOL
    global TRACKS_PER_ARTIST_PICK, TOP_TRACKS_COUNT, TOP_TRACKS_ORDER, CACHE_DAYS
    global TABLE_FONT_SIZE, VIBE_TRACK_COUNT

    load_dotenv(ENV_FILE, override=True)

    AUTH = (os.getenv("JRIVER_USER"), os.getenv("JRIVER_PASS"))
    JRIVER_HOST = os.getenv("JRIVER_HOST", "127.0.0.1:52199")
    JRIVER_BASE = f"http://{JRIVER_HOST}/MCWS/v1"
    LASTFM_KEY = os.getenv("LASTFM_API_KEY")
    LISTENBRAINZ_TOKEN = os.getenv("LISTENBRAINZ_TOKEN")
    DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    SIMILAR_SOURCES = [x.strip().lower() for x in os.getenv("SIMILAR_SOURCES", "lastfm").split(",") if x.strip()]
    TOP_TRACK_SOURCES = [x.strip().lower() for x in os.getenv("TOP_TRACK_SOURCES", "lastfm").split(",") if x.strip()]
    LISTENBRAINZ_ALGORITHM_SETTING = os.getenv("LISTENBRAINZ_ALGORITHM", "alltime").strip().lower()
    DIGITAL_STORE = os.getenv("DIGITAL_STORE", "bandcamp").strip().lower()
    DEBUG = os.getenv("DEBUG", "0").strip().lower() in ("1", "true", "yes")

    SIMILAR_ARTIST_LIMIT = _int_setting("SIMILAR_ARTIST_LIMIT", 20, 1, 50)
    TRACKS_PER_ARTIST_POOL = _int_setting("TRACKS_PER_ARTIST_POOL", 5, 1, 20)
    TRACKS_PER_ARTIST_PICK = _int_setting("TRACKS_PER_ARTIST_PICK", 3, 1, 20)
    TOP_TRACKS_COUNT = _int_setting("TOP_TRACKS_COUNT", 10, 1, 20)
    TOP_TRACKS_ORDER = os.getenv("TOP_TRACKS_ORDER", "popular").strip().lower()
    if TOP_TRACKS_ORDER not in ("popular", "reverse", "random"):
        print(f"[Settings] TOP_TRACKS_ORDER='{TOP_TRACKS_ORDER}' not recognised, using 'popular'.")
        TOP_TRACKS_ORDER = "popular"
    CACHE_DAYS = _int_setting("CACHE_DAYS", 30, 1, 365)
    TABLE_FONT_SIZE = _int_setting("TABLE_FONT_SIZE", 9, 6, 16)   # Discover table font
    VIBE_TRACK_COUNT = _int_setting("VIBE_TRACK_COUNT", 20, 5, 100)  # target size for vibe playlists


def refresh_settings_if_changed():
    """Reloads settings if .env has been edited since we last read it. Cheap timestamp check."""
    global _env_mtime
    try:
        mtime = os.path.getmtime(ENV_FILE)
    except OSError:
        return
    if mtime != _env_mtime:
        load_settings()
        _env_mtime = mtime


FIRST_RUN = False   # True when this launch created a fresh .env (new install)

DEFAULT_ENV = """# 24bit7 settings. Edit through the app's Settings tab (recommended) or here.

# JRiver connection. Media Network must be enabled in JRiver
# (Tools > Options > Media Network). User/pass only if you set authentication.
JRIVER_HOST=127.0.0.1:52199
JRIVER_USER=
JRIVER_PASS=

# Service keys. Deezer needs no key, so 24bit7 works out of the box.
# The ? buttons in Settings > Keys explain how to get each of these (all free
# except Anthropic, which is pay-as-you-go).
LASTFM_API_KEY=
LISTENBRAINZ_TOKEN=
DISCOGS_TOKEN=
ANTHROPIC_API_KEY=

# Recommendation sources (comma-separated: lastfm, listenbrainz, deezer, ai)
SIMILAR_SOURCES=lastfm,deezer
TOP_TRACK_SOURCES=lastfm,deezer
LISTENBRAINZ_ALGORITHM=alltime

# Playlist sizes and order
SIMILAR_ARTIST_LIMIT=20
TRACKS_PER_ARTIST_POOL=5
TRACKS_PER_ARTIST_PICK=3
TOP_TRACKS_COUNT=10
TOP_TRACKS_ORDER=popular
VIBE_TRACK_COUNT=20

# Other
DIGITAL_STORE=bandcamp
CACHE_DAYS=30
TABLE_FONT_SIZE=9
DEBUG=0
"""


def ensure_env_exists():
    """Creates a commented starter .env on a fresh install and flags first run."""
    global FIRST_RUN
    if os.path.isfile(ENV_FILE):
        return
    FIRST_RUN = True
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(DEFAULT_ENV)
        print(f"[Settings] Created starter settings file: {ENV_FILE}")
    except OSError as e:
        print(f"[Settings] Could not create {ENV_FILE}: {e}")


ensure_env_exists()
load_settings()
try:
    _env_mtime = os.path.getmtime(ENV_FILE)
except OSError:
    _env_mtime = None


def debug(msg):
    if DEBUG:
        print(f"    [debug] {msg}")


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Database: provider cache, sessions and discoveries (SQLite, no install needed)
# ---------------------------------------------------------------------------

_db = None


def db():
    """Opens the database on first use and creates tables if needed."""
    global _db
    if _db is None:
        _db = sqlite3.connect(DB_FILE, check_same_thread=False)
        _db.execute("""CREATE TABLE IF NOT EXISTS cache (
            source TEXT, kind TEXT, key TEXT, payload TEXT, fetched_at REAL,
            PRIMARY KEY (source, kind, key))""")
        _db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, mode TEXT,
            seed_artist TEXT, seed_track TEXT, seed_album TEXT, sources TEXT, queued INTEGER)""")
        _db.execute("""CREATE TABLE IF NOT EXISTS discoveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER,
            artist TEXT, track TEXT, sources TEXT, found INTEGER)""")
        _db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        _db.commit()
        import_legacy_csv()
    return _db


def cache_get(source, kind, key):
    """Returns the cached list for (source, kind, key) if younger than CACHE_DAYS, else None."""
    row = db().execute("SELECT payload, fetched_at FROM cache WHERE source=? AND kind=? AND key=?",
                       (source, kind, key)).fetchone()
    if not row:
        return None
    if time.time() - row[1] > CACHE_DAYS * 86400:
        return None
    return json.loads(row[0])


def cache_put(source, kind, key, items):
    db().execute("INSERT OR REPLACE INTO cache (source, kind, key, payload, fetched_at) VALUES (?,?,?,?,?)",
                 (source, kind, key, json.dumps(items), time.time()))
    db().commit()


def cached_call(source, kind, key, fetch_fn):
    """Serves from cache when possible, otherwise calls fetch_fn() and stores a non-empty result."""
    hit = cache_get(source, kind, key)
    if hit is not None:
        debug(f"{source} {kind} for '{key}' served from cache")
        return hit
    items = fetch_fn()
    if items:
        cache_put(source, kind, key, items)
    return items


def session_start(mode, seed_info, sources=""):
    cur = db().execute(
        "INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued) "
        "VALUES (?,?,?,?,?,?,0)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), mode,
         seed_info.get("Artist"), seed_info.get("Name"), seed_info.get("Album"), sources))
    db().commit()
    return cur.lastrowid


def session_log(session_id, artist, track, sources, found):
    db().execute("INSERT INTO discoveries (session_id, artist, track, sources, found) VALUES (?,?,?,?,?)",
                 (session_id, artist, track, ", ".join(sources) if isinstance(sources, list) else sources,
                  1 if found else 0))


def session_finish(session_id, queued, sources=None, report=print):
    if sources is not None:
        db().execute("UPDATE sessions SET sources=? WHERE id=?", (sources, session_id))
    db().execute("UPDATE sessions SET queued=? WHERE id=?", (queued, session_id))
    db().commit()
    misses = db().execute("SELECT COUNT(*) FROM discoveries WHERE session_id=? AND found=0",
                          (session_id,)).fetchone()[0]
    report(f"Session {session_id} saved ({queued} tracks queued, {misses} discoveries not in library).")


def import_legacy_csv():
    """One-off import of the old FutureDiscoveries.csv, grouped into sessions by date and seed."""
    if _db.execute("SELECT value FROM meta WHERE key='csv_imported'").fetchone():
        return
    if os.path.isfile(CSV_FILE):
        with open(CSV_FILE, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        sessions = {}
        for r in rows:
            key = (r.get("Date", ""), r.get("Seed Artist", ""), r.get("Seed Track", ""))
            if key not in sessions:
                cur = _db.execute(
                    "INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued) "
                    "VALUES (?,?,?,?,?,?,0)",
                    (key[0], "legacy", key[1], key[2], "", r.get("Source", "") or "legacy CSV"))
                sessions[key] = cur.lastrowid
            _db.execute("INSERT INTO discoveries (session_id, artist, track, sources, found) VALUES (?,?,?,?,0)",
                        (sessions[key], r.get("Discovered Artist", ""), r.get("Discovered Track", ""),
                         r.get("Source", "")))
        print(f"Imported {len(rows)} rows from {CSV_FILE} into {DB_FILE} ({len(sessions)} sessions).")
    _db.execute("INSERT INTO meta (key, value) VALUES ('csv_imported', ?)", (datetime.now().isoformat(),))
    _db.commit()


# --- Discover queries (read-only helpers for the Discover tab) --------------

def list_sessions():
    """Returns [(id, started_at, mode, seed_artist, seed_track)] newest first."""
    return db().execute(
        "SELECT id, started_at, mode, seed_artist, seed_track FROM sessions ORDER BY id DESC"
    ).fetchall()


def list_discoveries(found=None, session_id=None):
    """
    Returns discovery rows as dicts, newest session first.
    found: None for all, True for hits, False for misses.
    session_id: restrict to one session, or None for all.
    """
    q = ("SELECT d.artist, d.track, d.sources, d.found, s.started_at, d.session_id, "
         "s.seed_artist, s.seed_track "
         "FROM discoveries d JOIN sessions s ON s.id = d.session_id")
    conds, args = [], []
    if found is not None:
        conds.append("d.found = ?")
        args.append(1 if found else 0)
    if session_id is not None:
        conds.append("d.session_id = ?")
        args.append(session_id)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY d.session_id DESC, d.id ASC"
    rows = db().execute(q, args).fetchall()
    return [{"artist": r[0], "track": r[1], "sources": r[2], "found": bool(r[3]),
             "date": r[4], "session_id": r[5], "seed_artist": r[6], "seed_track": r[7]}
            for r in rows]


def get_playing_info():
    """Gets the current artist, track name and Playing Now position from JRiver."""
    try:
        r = requests.get(f"{JRIVER_BASE}/Playback/Info", params={"Zone": TARGET_ZONE}, auth=AUTH)
        root = ET.fromstring(r.text)
        info = {"Artist": "Unknown", "Album": "Unknown", "Name": "Unknown",
                "PlayingNowPosition": "-1", "PlayingNowTracks": "0"}
        for item in root.findall('Item'):
            if item.get('Name') in info:
                info[item.get('Name')] = item.text
        return info
    except Exception as e:
        print(f"[Error] Could not get playing info: {e}")
        return None


def remove_from_playing_now(index):
    """Removes a single track from Playing Now by 0-based index."""
    requests.get(
        f"{JRIVER_BASE}/Playback/EditPlaylist",
        params={"Zone": TARGET_ZONE, "Action": "Remove", "Source": str(index)},
        auth=AUTH
    )


def clear_around_current():
    """
    Strips Playing Now down to just the currently playing track, without
    interrupting playback. Removes everything after the current track
    (from the end backwards, so indices stay valid), then everything
    before it (index 0 repeatedly).
    """
    info = get_playing_info()
    if not info:
        return
    try:
        current_pos = int(info["PlayingNowPosition"])
        count = int(info["PlayingNowTracks"])
    except (ValueError, TypeError):
        print("[Warning] Could not read Playing Now position, skipping clear.")
        return

    if current_pos < 0 or count <= 1:
        return

    after = count - 1 - current_pos
    before = current_pos
    print(f"Clearing Playing Now: {before} before, {after} after the current track...")

    for idx in range(count - 1, current_pos, -1):
        remove_from_playing_now(idx)
        time.sleep(0.05)

    for _ in range(before):
        remove_from_playing_now(0)
        time.sleep(0.05)


def queue_tracks(keys):
    """Appends a list of file keys to the end of Playing Now in one call."""
    if not keys:
        return
    requests.get(
        f"{JRIVER_BASE}/Playback/PlayByKey",
        params={"Key": ",".join(str(k) for k in keys), "Location": "End", "Zone": TARGET_ZONE},
        auth=AUTH
    )


VERSION_WORDS = r'(remaster|remastered|mix|master|edit|version|live|mono|stereo|demo|single|radio|acoustic|instrumental)'


def clean_name(s):
    """Strips common variations from track names for fuzzy matching."""
    s = s.lower().strip()
    s = re.sub(r'\(.*?\)|\[.*?\]', '', s)                       # (Live), [Remaster 2011] etc.
    s = re.sub(rf'\s+-\s+[^-]*\b{VERSION_WORDS}\b[^-]*$', '', s)  # " - 2012 Mix/Master", " - Live at..."
    s = re.sub(r'\s*(feat\.|featuring|ft\.)\s.*', '', s)         # feat. credits
    s = re.sub(r'[^\w\s]', '', s)                                # punctuation
    return re.sub(r'\s+', ' ', s).strip()


def normalise_artist(artist_name):
    """
    Strips 'The' prefix/suffix and trailing '& The X' / 'and the X'
    backing-band credits for cleaner searching, so Last.fm's fully-credited
    artist name (e.g. 'Ben Harper & The Criminals') still matches a library
    where the artist has been normalised down to just the main act
    ('Ben Harper'). Deliberately requires 'the' right after the conjunction,
    so true duo/group names like 'Simon & Garfunkel' or 'Hall & Oates' are
    left untouched.
    """
    search_term = artist_name.strip()
    search_term = re.sub(
        r'\s+(&|and)\s+the\s+.*$',
        '',
        search_term,
        flags=re.IGNORECASE
    ).strip()
    search_term = re.sub(r'^(The\s+)|(,\s+The)$', '', search_term, flags=re.IGNORECASE).strip()
    return search_term


def strip_accents(s):
    """'José González' -> 'Jose Gonzalez', 'Trüby Trio' -> 'Truby Trio'."""
    decomposed = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def strip_initial_dots(s):
    """
    Collapses dotted initials: 'U.N.K.L.E.' -> 'UNKLE', 'M.I.A.' -> 'MIA',
    'R.E.M.' -> 'REM'. Only touches dots between single letters, so
    'Mr. Scruff' and 'Jr.' are left alone.
    """
    # Repeatedly remove a dot that sits between two single letters (or after a
    # single letter at the end), which is the initials pattern.
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\b([A-Za-z])\.(?=[A-Za-z]\b|[A-Za-z]\.|\s|$)', r'\1', s)
    return s


def norm_artist_text(s):
    """Accent-free, dot-collapsed form used wherever two artist names are compared."""
    return strip_accents(strip_initial_dots(s))


def deinvert_the(name):
    """
    Turns a trailing ', The' into a leading 'The' so library-style names match
    canonical databases. 'Isley Brothers, The' -> 'The Isley Brothers'.
    Returns the name unchanged if there's no trailing ', The'.
    """
    m = re.match(r'^(.*),\s*(The|A|An)$', name.strip(), re.IGNORECASE)
    return f"{m.group(2)} {m.group(1)}" if m else name.strip()


def jriver_search_artist_items(artist_name):
    """
    Runs the JRiver library search for an artist and returns the matching
    MPL items plus the accent-free search term used for regex filtering.
    Queries with accents stripped first; if that returns nothing and the
    name had accents, queries again with the original spelling so libraries
    that keep accents still match.
    """
    term_original = normalise_artist(artist_name)
    term_ascii = norm_artist_text(term_original)
    # Try the normalised form first (no accents, no dotted initials), then the
    # original spelling, so libraries tagged either way still match.
    queries = [term_ascii] if term_ascii == term_original else [term_ascii, term_original]
    for query in queries:
        r = requests.get(
            f"{JRIVER_BASE}/Files/Search",
            params={"Query": query, "Action": "MPL"},
            auth=AUTH
        )
        if r.status_code != 200 or not r.text:
            continue
        items = ET.fromstring(r.text).findall(".//Item")
        if items:
            return items, term_ascii
    return [], term_ascii


def artist_matches(pattern, fields):
    """Applies the artist regex to the normalised (accent-free, dot-collapsed) artist field."""
    actual_artist = fields.get("Artist", "") or fields.get("Album Artist", "")
    return bool(pattern.search(norm_artist_text(actual_artist)))


# ---------------------------------------------------------------------------
# Recommendation Providers
# Each service exposes two functions with identical shapes:
#   similar(artist_name, limit) -> list of artist names
#   top_tracks(artist_name, limit) -> list of track names, most popular first
# A run uses one service only; no cross-service fallback.
# ---------------------------------------------------------------------------

USER_AGENT = "JRiverGenius/1.0 (personal playlist tool)"
# ListenBrainz Labs similar-artists algorithms. Two are offered on the menu;
# the others are known to exist and can be added to LISTENBRAINZ_ALGORITHMS later:
#   session_based_days_1825_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30  (5 years, per-listener cap)
#   session_based_days_1800_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30  (same, 1800 days)
#   session_based_days_7500_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30  (all time, per-listener cap)
#   session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30               (all time, unfiltered, max 50)
LISTENBRAINZ_ALGORITHMS = {
    "recent": ("Recent - what people are playing alongside this artist right now",
               "session_based_days_75_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30"),
    "alltime": ("All time",
                "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30"),
}
LISTENBRAINZ_DEFAULT = "alltime"


def listenbrainz_algorithm_from_settings():
    """Returns (label, algorithm string) for the LISTENBRAINZ_ALGORITHM setting."""
    key = LISTENBRAINZ_ALGORITHM_SETTING if LISTENBRAINZ_ALGORITHM_SETTING in LISTENBRAINZ_ALGORITHMS else LISTENBRAINZ_DEFAULT
    return LISTENBRAINZ_ALGORITHMS[key]


def canonicalise_conjunction(artist_name):
    """
    Normalises '+' and 'and' to '&' in artist names returned by any
    provider, so they match this library's '&' convention (e.g.
    'Florence and the Machine' -> 'Florence & the Machine') before the
    name is ever used as a JRiver search term.
    """
    name = re.sub(r'\s*\+\s*', ' & ', artist_name)
    name = re.sub(r'\s+and\s+', ' & ', name, flags=re.IGNORECASE)
    return name


# --- Last.fm ---------------------------------------------------------------

def lastfm_similar(artist_name, limit=20):
    url = "http://ws.audioscrobbler.com/2.0/"
    params = {"method": "artist.getsimilar", "artist": artist_name,
              "api_key": LASTFM_KEY, "format": "json", "limit": limit}
    try:
        r = requests.get(url, params=params)
        names = [a['name'] for a in r.json().get('similarartists', {}).get('artist', [])]
        return [canonicalise_conjunction(n) for n in names]
    except Exception as e:
        print(f"[Error] Last.fm similar artists failed: {e}")
        return []


def lastfm_top_tracks_with_counts(artist_name, limit=10):
    """Returns [(track name, playcount)] most popular first."""
    url = "http://ws.audioscrobbler.com/2.0/"
    params = {"method": "artist.gettoptracks", "artist": artist_name,
              "api_key": LASTFM_KEY, "format": "json", "limit": limit}
    try:
        r = requests.get(url, params=params)
        return [(t['name'], int(t.get('playcount', 0)))
                for t in r.json().get('toptracks', {}).get('track', [])]
    except Exception as e:
        print(f"[Error] Last.fm top tracks failed for {artist_name}: {e}")
        return []


def lastfm_top_tracks(artist_name, limit=10):
    return [name for name, _ in lastfm_top_tracks_with_counts(artist_name, limit)]


# --- Deezer (public catalogue endpoints, no key) ---------------------------

_deezer_id_cache = {}


def deezer_artist_id(artist_name, verbose=False):
    """
    Resolves an artist name to a Deezer ID. Deezer's search isn't ranked
    by popularity and common names return several artists, so prefer an
    exact name match and, within that, the highest fan count.
    """
    if artist_name in _deezer_id_cache:
        return _deezer_id_cache[artist_name]
    artist_id = None
    try:
        r = requests.get("https://api.deezer.com/search/artist",
                         params={"q": artist_name, "limit": 10})
        data = r.json().get("data", [])
        if data:
            target = artist_name.strip().lower()
            exact = [a for a in data if a.get("name", "").strip().lower() == target]
            pool = exact if exact else data
            best = max(pool, key=lambda a: a.get("nb_fan", 0))
            artist_id = best["id"]
            if verbose:
                print(f"  [Deezer] Using '{best.get('name')}' (id {artist_id}, "
                      f"{best.get('nb_fan', 0)} fans) from {len(data)} search hits")
    except Exception as e:
        print(f"[Error] Deezer artist search failed for {artist_name}: {e}")
    _deezer_id_cache[artist_name] = artist_id
    return artist_id


def deezer_similar(artist_name, limit=20):
    artist_id = deezer_artist_id(artist_name, verbose=True)
    if not artist_id:
        print(f"[Deezer] No artist match for {artist_name}")
        return []
    try:
        r = requests.get(f"https://api.deezer.com/artist/{artist_id}/related",
                         params={"limit": limit})
        names = [a["name"] for a in r.json().get("data", [])]
        return [canonicalise_conjunction(n) for n in names]
    except Exception as e:
        print(f"[Error] Deezer related artists failed: {e}")
        return []


def deezer_top_tracks(artist_name, limit=10):
    artist_id = deezer_artist_id(artist_name, verbose=True)
    if not artist_id:
        return []
    try:
        r = requests.get(f"https://api.deezer.com/artist/{artist_id}/top",
                         params={"limit": limit})
        return [t["title"] for t in r.json().get("data", [])]
    except Exception as e:
        print(f"[Error] Deezer top tracks failed for {artist_name}: {e}")
        return []


# --- ListenBrainz (via MusicBrainz ID lookup, no key) ----------------------

_mbid_cache = {}


def _musicbrainz_query(name):
    """Single MusicBrainz artist search for one name spelling. Returns an MBID or None."""
    for attempt in range(3):
        try:
            r = requests.get("https://musicbrainz.org/ws/2/artist/",
                             params={"query": f'artist:"{name}"', "fmt": "json", "limit": 1},
                             headers={"User-Agent": USER_AGENT})
            if r.status_code == 503:
                print(f"  [MusicBrainz] Busy, retrying ({attempt + 1}/3)...")
                time.sleep(2.0)
                continue
            if r.status_code != 200:
                print(f"[Error] MusicBrainz returned {r.status_code} for {name}: {r.text[:200]}")
                return None
            artists = r.json().get("artists", [])
            return artists[0]["id"] if artists else None
        except Exception as e:
            print(f"[Error] MusicBrainz lookup failed for {name}: {e}")
            return None
    return None


def musicbrainz_artist_id(artist_name):
    """
    Resolves an artist name to a MusicBrainz ID. Tries the name as given, then
    the de-inverted form ('Isley Brothers, The' -> 'The Isley Brothers'), since
    libraries often store the sort-name form that MusicBrainz doesn't match.
    MusicBrainz asks for 1 req/sec.
    """
    if artist_name in _mbid_cache:
        return _mbid_cache[artist_name]
    candidates = [artist_name]
    deinverted = deinvert_the(artist_name)
    if deinverted != artist_name:
        candidates.append(deinverted)
    mbid = None
    for name in candidates:
        mbid = _musicbrainz_query(name)
        time.sleep(1.0)
        if mbid:
            break
    _mbid_cache[artist_name] = mbid
    return mbid


def listenbrainz_similar(artist_name, limit=20, algorithm=None):
    algorithm = algorithm or LISTENBRAINZ_ALGORITHMS[LISTENBRAINZ_DEFAULT][1]
    mbid = musicbrainz_artist_id(artist_name)
    if not mbid:
        print(f"[ListenBrainz] No MusicBrainz match for {artist_name}")
        return []
    try:
        r = requests.post("https://labs.api.listenbrainz.org/similar-artists/json",
                          json=[{"artist_mbids": [mbid], "algorithm": algorithm}],
                          headers={"User-Agent": USER_AGENT})
        data = r.json()
        # The Labs endpoint has changed shape over time; handle the known variants
        if isinstance(data, list) and data and isinstance(data[0], dict) and "data" in data[0]:
            data = data[0]["data"]
        if isinstance(data, dict):
            data = data.get("data", [])
        names = []
        for item in data:
            name = item.get("name") or item.get("artist_name")
            if name and name != artist_name:
                names.append(name)
        if not names and data:
            print(f"[ListenBrainz] Unrecognised response shape, first item: {data[0]}")
        return [canonicalise_conjunction(n) for n in names[:limit]]
    except Exception as e:
        print(f"[Error] ListenBrainz similar artists failed: {e}")
        return []


def listenbrainz_top_tracks(artist_name, limit=10):
    mbid = musicbrainz_artist_id(artist_name)
    if not mbid:
        return []
    if not LISTENBRAINZ_TOKEN:
        print("[ListenBrainz] LISTENBRAINZ_TOKEN is missing from .env; top tracks need it.")
        return []
    try:
        r = requests.get(f"https://api.listenbrainz.org/1/popularity/top-recordings-for-artist/{mbid}",
                         headers={"User-Agent": USER_AGENT,
                                  "Authorization": f"Token {LISTENBRAINZ_TOKEN}"})
        if r.status_code != 200:
            print(f"[Error] ListenBrainz top recordings returned {r.status_code}: {r.text[:200]}")
            return []
        try:
            data = r.json()
        except ValueError:
            print(f"[ListenBrainz] Top recordings: status {r.status_code}, "
                  f"content-type {r.headers.get('Content-Type')}, body starts: {r.text[:300]!r}")
            return []
        if isinstance(data, dict):
            data = data.get("payload") or data.get("recordings") or []
        names = [t.get("recording_name") or t.get("name") for t in data]
        names = [n for n in names if n]
        if not names and data:
            print(f"[ListenBrainz] Unrecognised top-tracks shape, first item: {data[0]}")
        return names[:limit]
    except Exception as e:
        print(f"[Error] ListenBrainz top tracks failed for {artist_name}: {e}")
        return []


# --- AI (Anthropic API, LLM knowledge of music) ----------------------------

AI_MODEL = "claude-sonnet-5"   # switch here if a cheaper or stronger model suits better
AI_SIMILAR_PROMPT = (
    "List the {limit} musical artists most similar to \"{artist}\", most similar first. "
    "Consider sound, era, scene and audience. Use each artist's most common spelling. "
    "Respond with a JSON array of artist name strings only, no commentary, no code fences."
)
AI_VIBE_PROMPT = (
    "Suggest {count} songs that fit this mood or description: \"{vibe}\".\n"
    "Favour well-known, widely-available recordings across a range of artists. "
    "Respond with a JSON array of objects with keys \"artist\" and \"track\" only, "
    "no commentary, no code fences."
)
AI_VIBE_SUGGESTIONS_PROMPT = (
    "Suggest three short, evocative music playlist moods a listener might enjoy, "
    "each under eight words (for example a time of day, activity, feeling or era). "
    "Respond with a JSON array of three strings only, no commentary, no code fences."
)
AI_TOP_TRACKS_PROMPT = (
    "List the {limit} most popular songs by \"{artist}\", most popular first, "
    "judged by overall listenership. Use official song titles without album or version notes. "
    "Respond with a JSON array of song title strings only, no commentary, no code fences."
)


def _salvage_json_array(text):
    """
    Recovers a list from a truncated JSON array like ["A","B","C  (no closing bracket).
    Returns the complete quoted strings found, or [] if none.
    """
    return re.findall(r'"([^"]+)"', text)


def ai_ask_list(prompt):
    """Sends a prompt expecting a JSON array of strings; returns the list or []."""
    if not ANTHROPIC_API_KEY:
        print("[AI] ANTHROPIC_API_KEY is missing from .env.")
        return []
    try:
        import anthropic
    except ImportError:
        print("[AI] The anthropic package isn't installed. Run: pip install anthropic")
        return []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=AI_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _salvage_json_array(text)
            if data:
                print(f"[AI] Response was truncated; recovered {len(data)} names.")
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
        print(f"[AI] Unexpected response shape: {text[:200]}")
    except Exception as e:
        print(f"[AI] Request failed: {e}")
    return []


def ai_ask_json(prompt, max_tokens=2000):
    """Sends a prompt expecting JSON; returns the parsed value or None."""
    if not ANTHROPIC_API_KEY:
        print("[AI] ANTHROPIC_API_KEY is missing from .env.")
        return None
    try:
        import anthropic
    except ImportError:
        print("[AI] The anthropic package isn't installed. Run: pip install anthropic")
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(model=AI_MODEL, max_tokens=max_tokens,
                                         messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        return json.loads(text)
    except Exception as e:
        print(f"[AI] Request failed: {e}")
        return None


def ai_vibe_suggestions():
    """Three random playlist moods for the vibe dialog. Returns a list of strings (may be empty)."""
    data = ai_ask_json(AI_VIBE_SUGGESTIONS_PROMPT, max_tokens=200)
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()][:3]
    return []


def ai_vibe_tracks(vibe, count):
    """Artist/track pairs for a vibe. Returns [(artist, track)]."""
    data = ai_ask_json(AI_VIBE_PROMPT.format(vibe=vibe, count=count))
    pairs = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("artist") and item.get("track"):
                pairs.append((canonicalise_conjunction(str(item["artist"]).strip()),
                              str(item["track"]).strip()))
    return pairs


def ai_similar(artist_name, limit=20):
    names = ai_ask_list(AI_SIMILAR_PROMPT.format(artist=artist_name, limit=limit))
    names = [canonicalise_conjunction(n) for n in names
             if strip_accents(n).lower() != strip_accents(artist_name).lower()]
    return names[:limit]


def ai_top_tracks(artist_name, limit=10):
    return ai_ask_list(AI_TOP_TRACKS_PROMPT.format(artist=artist_name, limit=limit))[:limit]


def deezer_artist_exists(artist_name):
    """
    Exact-name check against Deezer's keyless catalogue, used to verify
    AI-suggested artists before they're logged as discoveries.
    """
    try:
        r = requests.get("https://api.deezer.com/search/artist",
                         params={"q": artist_name, "limit": 10})
        target = strip_accents(artist_name).strip().lower()
        return any(strip_accents(a.get("name", "")).strip().lower() == target
                   for a in r.json().get("data", []))
    except Exception:
        return False


# --- Registry and chooser --------------------------------------------------

PROVIDERS = {
    "lastfm":       ("Last.fm",      lastfm_similar,       lastfm_top_tracks),
    "listenbrainz": ("ListenBrainz", listenbrainz_similar, listenbrainz_top_tracks),
    "deezer":       ("Deezer",       deezer_similar,       deezer_top_tracks),
    "ai":           ("AI",           ai_similar,           ai_top_tracks),
}


def sources_from_settings(names, setting_name):
    """
    Maps a list of source names from .env to provider tuples, dropping unknown
    names with a warning. Falls back to Last.fm if nothing valid is left.
    """
    chosen = []
    for name in names:
        if name in PROVIDERS:
            chosen.append(PROVIDERS[name])
        else:
            print(f"[Settings] Unknown source '{name}' in {setting_name}, ignoring. "
                  f"Valid: {', '.join(PROVIDERS)}")
    if not chosen:
        print(f"[Settings] No valid sources in {setting_name}, using Last.fm.")
        chosen.append(PROVIDERS["lastfm"])
    return chosen


def blend_lists(results, key_fn):
    """
    Merges ranked lists from several sources into one ranking.
    results: list of (source_name, [items]) in the order the sources were listed.
    Each item earns (n - position) points from each list it appears on, so an
    item high on two lists beats one high on one, and an item deep in three
    lists beats one midway in one. Ties keep first-seen order.
    Returns [(item, [source names that suggested it])], best first.
    """
    scores, sources, first_seen, display = {}, {}, {}, {}
    order = 0
    for source_name, items in results:
        n = len(items)
        for pos, item in enumerate(items):
            k = key_fn(item)
            if k not in scores:
                scores[k] = 0
                sources[k] = []
                first_seen[k] = order
                display[k] = item
                order += 1
            if source_name in sources[k]:
                continue   # a source votes once per item, even if it lists two versions
            scores[k] += n - pos
            sources[k].append(source_name)
    ranked = sorted(scores, key=lambda k: (-scores[k], first_seen[k]))
    return [(display[k], sources[k]) for k in ranked]


def artist_key(name):
    return norm_artist_text(canonicalise_conjunction(name)).lower().strip()


BLEND_DEPTH = 2   # ask each source for this many times the wanted count, so overlaps deeper down still merge


def blended_similar_artists(seed_artist, limit=20):
    """Similar artists from every source in SIMILAR_SOURCES, blended. Returns ([(artist, sources)], label)."""
    providers = sources_from_settings(SIMILAR_SOURCES, "SIMILAR_SOURCES")
    fetch = min(limit * BLEND_DEPTH, 50) if len(providers) > 1 else limit
    results, labels = [], []
    for service_name, similar_fn, _ in providers:
        kwargs, label = {}, service_name
        if similar_fn is listenbrainz_similar:
            algo_label, algo_string = listenbrainz_algorithm_from_settings()
            kwargs["algorithm"] = algo_string
            label = f"{service_name} ({algo_label.split(' - ')[0]})"
        names = cached_call(label, "similar", f"{artist_key(seed_artist)}|{fetch}",
                            lambda: similar_fn(seed_artist, limit=fetch, **kwargs))
        debug(f"{service_name} similar artists: {names}")
        if names:
            results.append((service_name, names))
            labels.append(label)
        else:
            print(f"  [{service_name}] returned no similar artists, skipping.")
    return blend_lists(results, artist_key)[:limit], " + ".join(labels) if labels else "none"


def blended_top_tracks(artist, limit=10):
    """Top tracks from every source in TOP_TRACK_SOURCES, blended. Returns ([(track, sources)], label)."""
    providers = sources_from_settings(TOP_TRACK_SOURCES, "TOP_TRACK_SOURCES")
    fetch = min(limit * BLEND_DEPTH, 50) if len(providers) > 1 else limit
    results, labels = [], []
    for service_name, _, top_tracks_fn in providers:
        names = cached_call(service_name, "top_tracks", f"{artist_key(artist)}|{fetch}",
                            lambda: top_tracks_fn(artist, limit=fetch))
        debug(f"{service_name} top tracks: {names}")
        if names:
            results.append((service_name, names))
            labels.append(service_name)
        else:
            print(f"  [{service_name}] returned no top tracks, skipping.")
    return blend_lists(results, clean_name)[:limit], " + ".join(labels) if labels else "none"


# ---------------------------------------------------------------------------
# JRiver Search Functions
# ---------------------------------------------------------------------------

def get_verified_keys_for_artist(artist_name, pool=None, pick=None):
    """
    Searches the JRiver library for tracks by the given artist and returns
    `pick` keys chosen at random from the first `pool` matches. Both default
    to the TRACKS_PER_ARTIST_* settings. Pass pick=None with a pool to get
    the whole pool in library order.
    """
    pool = pool or TRACKS_PER_ARTIST_POOL
    try:
        items, search_term = jriver_search_artist_items(artist_name)
        keys = []
        pattern = re.compile(rf'\b{re.escape(search_term)}\b', re.IGNORECASE)
        for item in items:
            fields = {f.get("Name"): f.text for f in item.findall("Field") if f.text}
            if artist_matches(pattern, fields) and fields.get("Key"):
                keys.append(fields.get("Key"))

        top_n = keys[:pool]
        if pick is None and pool != TRACKS_PER_ARTIST_POOL:
            return top_n
        pick = pick or TRACKS_PER_ARTIST_PICK
        return random.sample(top_n, min(pick, len(top_n)))

    except Exception as e:
        print(f"  [Error] Search failed for {artist_name}: {e}")
        return []


def find_jriver_key_by_track(artist_name, track_name):
    """
    Looks up a specific track in JRiver by artist and track name.
    Uses fuzzy matching to handle remaster tags, live versions, feat. credits etc.
    """
    clean_track = clean_name(track_name)

    try:
        items, search_term = jriver_search_artist_items(artist_name)
        artist_pattern = re.compile(rf'\b{re.escape(search_term)}\b', re.IGNORECASE)

        for item in items:
            fields = {f.get("Name"): f.text for f in item.findall("Field") if f.text}
            actual_track = fields.get("Name", "") or fields.get("Title", "")

            if artist_matches(artist_pattern, fields) and clean_name(actual_track) == clean_track:
                return fields.get("Key")
    except Exception as e:
        print(f"  [Error] Track search failed for {track_name}: {e}")
    return None


# ---------------------------------------------------------------------------
# Mode 1: Similar Artist Playlist
# ---------------------------------------------------------------------------

def create_similar_playlist(report=print):
    """
    Finds similar artists via Last.fm, queues library tracks,
    and logs missing artists to CSV for future discovery.
    Also seeds the queue with the seed artist's own top 5 Last.fm tracks
    (excluding the track that's currently playing).
    Can be run mid-album: Playing Now is stripped to the current track
    before the new tracks are added, without interrupting playback.
    """
    refresh_settings_if_changed()
    seed_info = get_playing_info()
    if not seed_info or seed_info["PlayingNowPosition"] == "-1":
        report("Nothing playing. Seed from a track first!")
        return

    report(f"\nSeeding from: {seed_info['Artist']} - {seed_info['Name']}")
    session_id = session_start("similar", seed_info)

    # Use a set to avoid duplicate track keys
    collected_keys = set()

    # --- Seed artist's own top tracks (excluding the currently playing track) ---
    report(f"  Adding top tracks for seed artist: {seed_info['Artist']}...")
    seed_clean = clean_name(seed_info['Name'])
    # Fetch a few extra in case the seed track itself is among the top 5
    seed_top_tracks, _ = blended_top_tracks(seed_info['Artist'], limit=10)

    seed_keys_added = 0
    for track_name, _ in seed_top_tracks:
        if seed_keys_added >= 5:
            break
        if clean_name(track_name) == seed_clean:
            continue  # don't re-add the seed track itself
        key = find_jriver_key_by_track(seed_info['Artist'], track_name)
        if key:
            if key not in collected_keys:
                collected_keys.add(key)
                seed_keys_added += 1
            report(f"    Added: {track_name}")
        else:
            report(f"    Not in library: {track_name}")

    similar, source_label = blended_similar_artists(seed_info['Artist'], limit=SIMILAR_ARTIST_LIMIT)
    report(f"  Similar artists via {source_label}: {len(similar)} candidates")

    for artist, suggested_by in similar:
        tag = f"  Checking: {artist} ({', '.join(suggested_by)})..."
        keys = get_verified_keys_for_artist(artist)
        if keys:
            report(f"{tag} Found in library.")
            collected_keys.update(keys)
            session_log(session_id, artist, "", suggested_by, found=True)
        else:
            if suggested_by == ["AI"] and not deezer_artist_exists(artist):
                report(f"{tag} Not in library, and not a verifiable artist name. Skipping.")
                continue
            report(f"{tag} Not in library. Logging...")
            top, _ = blended_top_tracks(artist, limit=1)
            top_track = top[0][0] if top else "Unknown Track"
            session_log(session_id, artist, top_track, suggested_by, found=False)

    # Update JRiver queue
    queued = 0
    if collected_keys:
        keys_list = list(collected_keys)
        random.shuffle(keys_list)
        clear_around_current()
        report(f"Injecting {len(keys_list)} library tracks into queue...")
        queue_tracks(keys_list)
        queued = len(keys_list)
        report("Queue refreshed.")
    else:
        report("No library matches found.")
    session_finish(session_id, queued, sources=source_label, report=report)


# ---------------------------------------------------------------------------
# Mode 4: Vibe Playlist (AI-described mood, two-step)
# ---------------------------------------------------------------------------

VIBE_BACKFILL_THRESHOLD = 0.50   # run step 2 when this share (or more) of step-1 picks are misses


def create_vibe_playlist(vibe, report=print):
    """
    Builds a playlist from a text description of a mood.
    Step 1: AI suggests artist/track pairs (always AI, regardless of source
            settings, since no other source takes a description). Hits queue,
            misses are logged as discoveries.
    Step 2: only if the step-1 miss rate reaches VIBE_BACKFILL_THRESHOLD, the
            step-1 HIT artists become seeds for Last.fm + Deezer similar artists
            (no AI), and library tracks from those fill up to VIBE_TRACK_COUNT.
    Everything is shuffled before queueing.
    """
    refresh_settings_if_changed()
    vibe = (vibe or "").strip()
    if not vibe:
        report("No vibe given.")
        return
    target = VIBE_TRACK_COUNT
    report(f"\nVibe: {vibe}  (target {target} tracks)")

    seed_info = {"Artist": "Vibe", "Name": vibe, "Album": ""}
    session_id = session_start("vibe", seed_info, "AI")

    # --- Step 1: AI wings it -------------------------------------------------
    report("  Step 1: asking AI for tracks...")
    pairs = ai_vibe_tracks(vibe, count=target)
    if not pairs:
        report("  AI returned nothing usable.")
        session_finish(session_id, 0, report=report)
        return

    keys, hit_artists, misses = [], [], 0
    for artist, track in pairs:
        key = find_jriver_key_by_track(artist, track)
        if key:
            report(f"    Found: {artist} - {track}")
            if key not in keys:
                keys.append(key)
            if artist_key(artist) not in {artist_key(a) for a in hit_artists}:
                hit_artists.append(artist)
            session_log(session_id, artist, track, "AI", found=True)
        else:
            report(f"    Not in library: {artist} - {track}")
            misses += 1
            session_log(session_id, artist, track, "AI", found=False)

    miss_rate = misses / len(pairs)
    report(f"  Step 1 done: {len(keys)} found, {misses} missing ({miss_rate:.0%} miss rate).")

    # --- Step 2: backfill from similar artists, only if needed --------------------
    if len(keys) < target and miss_rate >= VIBE_BACKFILL_THRESHOLD:
        if not hit_artists:
            report("  Nothing matched, so no seeds for a backfill. Try a different vibe.")
        else:
            report(f"  Step 2: filling from artists similar to your {len(hit_artists)} hit(s) "
                   f"via Last.fm + Deezer...")
            backfill_providers = [PROVIDERS["lastfm"], PROVIDERS["deezer"]]
            seen_artists = {artist_key(a) for a in hit_artists}
            for seed in hit_artists:
                if len(keys) >= target:
                    break
                results = []
                for service_name, similar_fn, _ in backfill_providers:
                    names = cached_call(service_name, "similar", f"{artist_key(seed)}|20",
                                        lambda: similar_fn(seed, limit=20))
                    if names:
                        results.append((service_name, names))
                for artist, suggested_by in blend_lists(results, artist_key):
                    if len(keys) >= target:
                        break
                    if artist_key(artist) in seen_artists:
                        continue
                    seen_artists.add(artist_key(artist))
                    picks = get_verified_keys_for_artist(artist)
                    if picks:
                        added = [k for k in picks if k not in keys]
                        keys.extend(added)
                        report(f"    + {artist} ({', '.join(suggested_by)}): {len(added)} track(s)")
                        session_log(session_id, artist, "", suggested_by, found=True)
                    else:
                        top, _ = blended_top_tracks(artist, limit=1)
                        top_track = top[0][0] if top else "Unknown Track"
                        session_log(session_id, artist, top_track, suggested_by, found=False)
            report(f"  Step 2 done: {len(keys)} tracks total.")

    if not keys:
        report("No library matches found.")
        session_finish(session_id, 0, report=report)
        return

    random.shuffle(keys)
    keys = keys[:target]
    clear_around_current()
    report(f"Queuing {len(keys)} tracks (shuffled)...")
    queue_tracks(keys)
    report("Queue refreshed.")
    session_finish(session_id, len(keys), report=report)


# ---------------------------------------------------------------------------
# Mode 2: Artist Top 10 by Popularity
# ---------------------------------------------------------------------------

def play_top_n(report=print):
    """
    Plays the top N tracks for the current artist, ranked across the
    configured TOP_TRACK_SOURCES. N and the play order (most popular first,
    least popular first, or random) come from the TOP_TRACKS_* settings.
    Can be run mid-album: Playing Now is stripped to the current track
    before the new tracks are added, without interrupting playback.
    """
    refresh_settings_if_changed()
    seed_info = get_playing_info()
    if not seed_info or seed_info["PlayingNowPosition"] == "-1":
        report("Nothing playing. Seed from a track first!")
        return

    artist = seed_info['Artist']
    n = TOP_TRACKS_COUNT
    order = TOP_TRACKS_ORDER

    report(f"\nFetching top {n} tracks for: {artist} ({order} order)")

    top_tracks, source_label = blended_top_tracks(artist, limit=n)
    if not top_tracks:
        report("Could not retrieve top tracks from any configured source.")
        return
    report(f"  Ranked via {source_label}")
    session_id = session_start("top_tracks", seed_info, source_label)

    ordered_keys = []
    for track_name, suggested_by in top_tracks[:n]:
        tag = f"  Looking up: {track_name} ({', '.join(suggested_by)})..."
        key = find_jriver_key_by_track(artist, track_name)
        report(f"{tag} {'Found.' if key else 'Not in library.'}")
        if key:
            ordered_keys.append(key)
        session_log(session_id, artist, track_name, suggested_by, found=bool(key))

    if not ordered_keys:
        report("None of the top tracks were found in your library.")
        session_finish(session_id, 0, report=report)
        return

    if order == "random":
        random.shuffle(ordered_keys)
    elif order == "reverse":
        ordered_keys.reverse()

    clear_around_current()
    labels = {"popular": "most popular first", "reverse": "least popular first", "random": "random order"}
    report(f"\nQueuing {len(ordered_keys)} tracks, {labels[order]}...")
    queue_tracks(ordered_keys)
    report("Done!")
    session_finish(session_id, len(ordered_keys), report=report)


# ---------------------------------------------------------------------------
# Mode 3: Explore a record's credits (Discogs)
# ---------------------------------------------------------------------------

DISCOGS_BASE = "https://api.discogs.com"

# Credit roles worth following, in the order they're offered. Discogs role
# strings are free text ("Producer, Mixed By", "Drums, Percussion"), so we
# match on the keyword appearing anywhere in the role.
DISCOGS_ROLE_PRIORITY = ["Producer", "Mixed By", "Engineer", "Recorded By",
                         "Featuring", "Guitar", "Bass", "Drums", "Keyboards",
                         "Piano", "Vocals", "Saxophone", "Trumpet", "Written-By"]


def discogs_get(path, params=None):
    if not DISCOGS_TOKEN:
        print("[Discogs] DISCOGS_TOKEN is missing from .env.")
        return None
    try:
        r = requests.get(f"{DISCOGS_BASE}{path}", params=params or {},
                         headers={"User-Agent": USER_AGENT,
                                  "Authorization": f"Discogs token={DISCOGS_TOKEN}"})
        if r.status_code != 200:
            print(f"[Discogs] {path} returned {r.status_code}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        print(f"[Discogs] Request failed for {path}: {e}")
        return None


def discogs_clean_name(name):
    """Removes Discogs disambiguation suffixes like 'John Smith (2)'."""
    return re.sub(r'\s*\(\d+\)$', '', name).strip()


_release_master = {}   # release id -> master id, filled by discogs_find_release


def discogs_find_release(artist, album):
    """
    Finds the Discogs release for the playing album. Returns (release id, label) or None.
    Searches for the master release first (the album as a work, not a specific
    pressing), picks the most-owned match, and uses its main release, which is
    the canonical pressing with the fullest credits. Falls back to a plain
    release search ranked by owners if no master exists.
    """
    def most_owned(results):
        return max(results, key=lambda r: r.get("community", {}).get("have", 0))

    for params in ({"artist": artist, "release_title": album, "type": "master", "per_page": 10},
                   {"q": f"{artist} {album}", "type": "master", "per_page": 10}):
        data = discogs_get("/database/search", params)
        if data and data.get("results"):
            master = most_owned(data["results"])
            detail = discogs_get(f"/masters/{master['id']}")
            if detail and detail.get("main_release"):
                label = f"{master.get('title')} ({detail.get('year', '?')}, main release of master {master['id']})"
                _release_master[detail["main_release"]] = master["id"]
                return detail["main_release"], label
            break

    for params in ({"artist": artist, "release_title": album, "type": "release", "per_page": 25},
                   {"q": f"{artist} {album}", "type": "release", "per_page": 25}):
        data = discogs_get("/database/search", params)
        if data and data.get("results"):
            best = most_owned(data["results"])
            label = f"{best.get('title')} ({best.get('year', '?')}, {', '.join(best.get('format', [])[:2])})"
            return best["id"], label
    return None


def discogs_release_credits(release_id, seed_artist):
    """
    Collects credited people from a release (release-level and per-track),
    excluding the seed artist. Returns a list of (name, roles) sorted so
    the most useful roles come first.
    """
    data = discogs_get(f"/releases/{release_id}")
    if not data:
        return []
    people = {}
    sources = list(data.get("extraartists", []))
    for track in data.get("tracklist", []):
        sources.extend(track.get("extraartists", []))
    seed_clean = strip_accents(seed_artist).lower()
    for credit in sources:
        name = discogs_clean_name(credit.get("name", ""))
        if not name or strip_accents(name).lower() == seed_clean:
            continue
        roles = people.setdefault(name, set())
        for role in credit.get("role", "").split(","):
            role = role.strip()
            if role:
                roles.add(role)

    def rank(item):
        name, roles = item
        joined = " ".join(roles)
        for i, key in enumerate(DISCOGS_ROLE_PRIORITY):
            if key.lower() in joined.lower():
                return i
        return len(DISCOGS_ROLE_PRIORITY)

    return sorted(people.items(), key=rank)