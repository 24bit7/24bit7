"""
24bit7 - Discover's Missing Artists and Gaps in Your Artists (Ben, 10 and 11 Nov 2026).

Reads the history every build logs (sessions and discoveries) and answers two questions:

- Missing Artists: artists the sources named that aren't in the library, ranked by how many of your
  artists point to them. Checked against the library, not the build's "found" flag, so an artist you
  own whose song was missing is a gap, not a missing artist.
- Gaps in Your Artists: artists you own, with the songs matched and the songs named that you don't have.

(A third view, Sources, a scoreboard of what each source named and found, was dropped on 11 Nov 2026: Ben
found nothing on it to act on, and Test My Sources already says whether a source works.)

Filters: Period, Zone (where it played, from the build kept in the Log), Genre (Radio's stations: a row
counts under the stations of the seed artists that led to it) and Sound (an artist's own Last.fm tags,
shared by several artists in view). Neither filter reads the library's Genre field: another user's may be
empty or a mess. Nothing here writes to the history; the only thing kept is Last.fm's tags, in Radio's
own tag cache, so Radio and Discover ask about an artist once between them.
"""

import re
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import engine
from i18n import N_

PERIODS = (N_("All time"), N_("Last 6 months"), N_("Last 12 months"))
PERIOD_DAYS = {"All time": None, "Last 6 months": 183, "Last 12 months": 365}
VIEWS = (N_("Missing Artists"), N_("Gaps in Your Artists"))
NO_SEED_ARTIST = {"vibe", "radio", "embellish", "jriver_playlist", "blend"}   # their seed_artist isn't an artist
SOUND_MIN = 3        # a sound is listed when at least this many artists in view share it
SOUNDS_PER_ARTIST = 8
DECADE = re.compile(r"^(?:19|20)?(\d0)'?s$")   # 80s, 1980s, 80's: Radio's rule drops them, Sound keeps them
_AND = re.compile(r"\s*(?:&|\+|'n'|'n|n'|\bn\b|\band\b)\s*")
_fetch_lock = threading.Lock()


# --- the history in view -------------------------------------------------------------------------

def rows(period="All time", zone=None, now=None):
    """
    Every name looked up in the builds in view, as dicts: session, started, mode, zone, asked_by,
    artist, track, sources (a list), found, seed_artist (the artist that led to it, or "").
    zone None is every zone.
    """
    q = ("SELECT s.id, s.started_at, s.mode, s.seed_artist, s.zone, s.asked_by, "
         "d.artist, d.track, d.sources, d.found, d.seed "
         "FROM discoveries d JOIN sessions s ON s.id = d.session_id")
    conds, args = [], []
    days = PERIOD_DAYS.get(period)
    if days:
        conds.append("s.started_at >= ?")
        args.append(((now or datetime.now()) - timedelta(days=days)).strftime("%Y-%m-%d"))
    if zone is not None:
        conds.append("COALESCE(s.zone, '') = ?")
        args.append(zone)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    out = []
    for sid, started, mode, s_artist, zone_, asked, artist, track, sources, found, seed in engine.db().execute(q, args):
        if not (artist or "").strip():
            continue
        out.append({"session": sid, "started": started, "mode": mode, "zone": zone_ or "", "asked_by": asked or "",
                    "artist": artist.strip(), "track": (track or "").strip(),
                    "sources": [x.strip() for x in (sources or "").split(",") if x.strip()],
                    "found": bool(found), "seed_artist": seed_artist(mode, s_artist, seed)})
    return out


def seed_artist(mode, session_artist, seed):
    """The artist that led to a row: a Playing Now build's sampled track, else the session's seed artist."""
    if seed and " - " in seed:
        return seed.split(" - ")[0].strip()
    if mode in NO_SEED_ARTIST:
        return ""
    return (session_artist or "").strip()


def zones():
    """[(zone, Counter of who asked)], most builds first. "" is a build whose zone isn't known."""
    found = defaultdict(Counter)
    for zone, asked in engine.db().execute("SELECT COALESCE(zone, ''), COALESCE(asked_by, '') FROM sessions"):
        found[zone][asked] += 1
    return sorted(found.items(), key=lambda kv: (-sum(kv[1].values()), kv[0].lower()))


def _key(name):
    return engine.artist_key(name or "")


def _song(track):
    return (track or "").strip().lower()


def owned(name):
    import library
    return library.has_artist(name)


# --- the three views ----------------------------------------------------------------------------

def missing_artists(view):
    """
    Artists not in the library, as dicts: artist, key, yours ({key: name} of your artists that point to it,
    folded by case, so SOiL and Soil are one), builds (session ids) and songs (Counter of the tracks named).
    Ranked by how many of your artists point to it, then by builds.
    """
    found, mine = {}, {}
    for r in view:
        k = _key(r["artist"])
        if k not in found:
            if owned(r["artist"]):
                found[k] = None
                continue
            found[k] = {"artist": r["artist"], "key": k, "yours": {}, "builds": set(), "songs": Counter()}
        m = found[k]
        if m is None:
            continue
        seed = r["seed_artist"]
        if seed and seed not in mine:
            mine[seed] = owned(seed)   # a typed seed you don't own isn't one of your artists
        if seed and mine[seed] and _key(seed) != k:
            m["yours"].setdefault(_key(seed), seed)
        m["builds"].add(r["session"])
        if r["track"]:
            m["songs"][r["track"]] += 1
    out = [m for m in found.values() if m]
    out.sort(key=lambda m: (-len(m["yours"]), -len(m["builds"]), m["artist"].lower()))
    return out


def gaps(view):
    """
    Artists you own that the sources named, as dicts: artist, key, matched (songs found in the library),
    missed (songs named that you don't have, as named), builds. Most songs missed first.
    """
    found = {}
    for r in view:
        k = _key(r["artist"])
        if k not in found:
            found[k] = ({"artist": r["artist"], "key": k, "hit": set(), "miss": {}, "builds": set()}
                        if owned(r["artist"]) else None)
        g = found[k]
        if g is None:
            continue
        g["builds"].add(r["session"])
        if r["track"]:
            if r["found"]:
                g["hit"].add(_song(r["track"]))
            else:
                g["miss"].setdefault(_song(r["track"]), r["track"])
    out = []
    for g in found.values():
        if g:
            missed = [name for low, name in g["miss"].items() if low not in g["hit"]]
            out.append({"artist": g["artist"], "key": g["key"], "matched": len(g["hit"]), "missed": missed,
                        "builds": g["builds"]})
    out.sort(key=lambda g: (-len(g["missed"]), g["matched"], g["artist"].lower()))
    return out


# --- Genre: Radio's stations ---------------------------------------------------------------------

def stations():
    """
    (Radio's top-level stations, why not): the stations, or [] and a reason when Radio has none to offer
    (never analysed, or resting because the library's plays are too few).
    """
    import radio
    if radio.resting():
        return [], N_("Radio is resting, so there are no stations to filter by.")
    found = [x for x in radio.lanes() if x.get("centroid")]
    if not found:
        return [], N_("Radio hasn't made its stations yet.")
    return found, None


def station_finder(cache=None):
    """station(artist name): the id of the station whose genres fit the artist best, as Radio's fitter does, or None."""
    import radio
    tops, _why = stations()
    centres = {x["id"]: radio._unit(x["centroid"]) for x in tops}
    cache = tag_cache() if cache is None else cache
    known = {}

    def station(name):
        k = _key(name)
        if k not in known:
            genres, _case = radio.genres_for(k, {"genres": Counter()}, cache)
            best = None
            if genres and centres:
                mine = radio._unit(genres)
                sims = {i: radio._cosine(mine, c) for i, c in centres.items()}
                best = max(sims, key=sims.get)
                if sims[best] <= 0:
                    best = None
            known[k] = best
        return known[k]
    return station


def in_station(kind, items, view, station_id, station):
    """
    The rows of a view that belong to a station. Missing Artists: the ones a seed artist in the station
    points to, with Your Artists recounted within it. Gaps: the artists you own that sit in it. A build with
    no seed artist (an AI Playlist, Radio, Play & Embellish) only shows under All genres.
    """
    if station_id is None:
        return items
    if kind == "Missing Artists":
        out = []
        for m in items:
            yours = {k: n for k, n in m["yours"].items() if station(n) == station_id}
            if yours:
                out.append(dict(m, yours=yours))
        out.sort(key=lambda m: (-len(m["yours"]), -len(m["builds"]), m["artist"].lower()))
        return out
    return [g for g in items if station(g["artist"]) == station_id]


# --- Sound: an artist's own Last.fm tags ----------------------------------------------------------

def tag_cache():
    """Last.fm's tags as Radio keeps them: {artist key: [[tag, weight]]}."""
    import radio
    return dict(radio._meta(radio.TAGS_KEY, {}))


def sound_key(tag):
    """
    The spelling a sound is merged by: synthpop, synth pop and synth-pop are one; hip hop and hip-hop;
    rock and roll, rock & roll and rock n roll; 80s, 1980s and 80's.
    """
    tag = (tag or "").strip().lower()
    m = DECADE.match(tag)
    if m:
        return m.group(1) + "s"
    tag = _AND.sub(" and ", f" {tag} ").strip()
    return re.sub(r"[\s\-_./]+", "", tag)


def sounds_of(name, cache):
    """An artist's sounds: its Last.fm tags applied strongly (Radio's rule), decades kept, best first, merged by spelling."""
    import radio
    out, seen = [], set()
    for tag, weight in cache.get(_key(name)) or []:
        tag = (tag or "").strip().lower()
        if weight < radio.TAG_MIN or not tag:
            continue
        if radio.NOT_GENRE.match(tag) and not DECADE.match(tag):
            continue
        k = sound_key(tag)
        if k and k not in seen:
            seen.add(k)
            out.append((k, DECADE.match(tag) and k or tag))
        if len(out) >= SOUNDS_PER_ARTIST:
            break
    return out


def sound_list(names, cache, station=None):
    """
    The Sound filter for the artists in view: [(key, shown as, how many artists, broad)], shared by at least
    SOUND_MIN artists, most first. Broad is a sound that only restates the station (metal in Metal), shown
    but greyed. Also returns how many of the artists have no sound to go by.
    """
    count, spelt = Counter(), defaultdict(Counter)
    untagged = 0
    for name in names:
        mine = sounds_of(name, cache)
        if not mine:
            untagged += 1
        for k, shown in mine:
            count[k] += 1
            spelt[k][shown] += 1
    broad = {sound_key(g) for g in (station or {}).get("genres") or []}
    listed = [(k, spelt[k].most_common(1)[0][0], n, k in broad) for k, n in count.most_common() if n >= SOUND_MIN]
    return listed, untagged


def with_sound(names_rows, sound, cache, name_of=lambda r: r["artist"]):
    """The rows whose artist has the sound (a sound_key)."""
    if not sound:
        return names_rows
    return [r for r in names_rows if any(k == sound for k, _ in sounds_of(name_of(r), cache))]


def untagged(names, cache):
    """The names Radio's tag cache knows nothing about yet (never asked)."""
    return [n for n in names if _key(n) not in cache]


def fetch_tags(names, cancelled=lambda: False):
    """
    Asks Last.fm for the tags of the artists not yet in Radio's tag cache, four at a time, keeping them as it
    goes. About four hundred artists the first time on Ben's history, a minute or two; after that only the new
    ones. Returns how many were fetched. Nothing without a Last.fm key.
    """
    import radio
    if not engine.LASTFM_KEY:
        return 0
    with _fetch_lock:
        cache = tag_cache()
        todo, seen = [], set()
        for n in names:
            k = _key(n)
            if k and k not in cache and k not in seen:
                seen.add(k)
                todo.append((k, n))
        if not todo:
            return 0
        from concurrent.futures import ThreadPoolExecutor

        def one(pair):
            if cancelled():
                return pair[0], None
            try:
                data = radio._lastfm({"method": "artist.gettoptags", "artist": pair[1], "autocorrect": 1})
                return pair[0], [[x["name"].lower().strip(), int(x.get("count", 0))]
                                 for x in data.get("toptags", {}).get("tag", [])]
            except Exception as e:
                engine.debug(f"Discover: no tags for {pair[1]} ({e})")
                return pair[0], None
        got = 0
        for start in range(0, len(todo), 100):
            if cancelled():
                break
            with ThreadPoolExecutor(max_workers=4) as pool:
                found = [(k, tags) for k, tags in pool.map(one, todo[start:start + 100]) if tags is not None]
            if found:
                kept = tag_cache()   # Radio may have added some meanwhile
                kept.update(found)
                radio._set_meta(radio.TAGS_KEY, kept)
                got += len(found)
        return got


# --- one call for the screen ---------------------------------------------------------------------

def build(kind="Missing Artists", period="All time", zone=None, station_id=None, sound=None, cache=None, now=None):
    """
    Everything an artists tab shows for one choice of view and filters:
    {"items", "builds" (sessions in view), "looked_up" (names in view), "sounds", "untagged", "station"}.
    """
    cache = tag_cache() if cache is None else cache
    view = rows(period, zone, now=now)
    tops, _why = stations()
    station = station_finder(cache)
    chosen = next((x for x in tops if x["id"] == station_id), None)
    items = missing_artists(view) if kind == "Missing Artists" else gaps(view)
    items = in_station(kind, items, view, chosen and station_id, station)
    sounds, bare = sound_list([x["artist"] for x in items], cache, chosen)
    items = with_sound(items, sound, cache)
    return {"items": items, "builds": len({r["session"] for r in view}), "looked_up": len(view),
            "sounds": sounds, "untagged": bare, "station": chosen}
