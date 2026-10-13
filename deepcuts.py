"""
24bit7 - Deep Cuts: tracks from the corners of the library that rarely get played.

A build can be topped up with deep cuts from the seed's genre, as the library's own
Genre tags have it (version one uses no outside data). Two ways to pick:

  - by artist (Similar Artists): the artists in the genre whose tracks have been
    played least in the last year, the bottom 20%, picked at random; then a track
    of theirs in that genre, their top tracks first.
  - by track (Similar Tracks, AI Playlist): the genre's least played tracks
    (fewest plays, then played longest ago), the bottom 20%, picked at random.

Either way: one per artist, nothing already in the build, no very short tracks
(intros, interludes), no hidden-track closers when the build skips them, and the
build's own checks (Skip Played, Filters) through allowed(). When there's nothing
to pick from, the reason comes back to be said in the console.

Everything comes from the library read 24bit7 already does every thirty minutes;
the index is rebuilt whenever that read is newer.
"""

import math
import random
import threading
import time

import engine
import library

BOTTOM_SHARE = 0.2       # the least played fifth of the genre's artists, or of its tracks
MIN_ARTISTS = 5          # fewer artists than this in the pool: no deep cuts (too little to choose from)
MIN_TRACKS = 20          # ...or fewer tracks than this
SHORTEST = 90            # seconds: anything shorter is an intro, interlude or skit, not a deep cut
RECENT_DAYS = 365        # an artist's "played lately" share counts plays in this many days
TRIES_EACH = 3           # artists tried for each deep cut before giving up on it

_lock = threading.Lock()
_index = {"at": None, "genres": {}, "names": {}}   # rebuilt when the library read is newer


def genre_key(text):
    return " ".join((text or "").casefold().split())


def genres_of(row):
    """A track's genres as the library has them: 'Dub; Reggae' is both."""
    return [g.strip() for g in (row.get("Genre") or "").split(";") if g.strip()]


VARIOUS = {"various artists", "various", "va", "v.a."}


def first_artist(row):
    """
    The track's artist: the first one tagged, or, for a various artists track named
    'Artist - Title', the artist in the title (as library matching reads them).
    """
    artist = ((row.get("Artist") or row.get("Album Artist (auto)") or "").split(";")[0]).strip()
    title = row.get("Name") or ""
    if artist.casefold() in VARIOUS and " - " in title:
        return title.split(" - ", 1)[0].strip() or artist
    return artist


def track_title(row):
    """The title as shown: without the 'Artist - ' a various artists track carries."""
    title = (row.get("Name") or "").strip()
    artist = ((row.get("Artist") or "").split(";")[0]).strip()
    if artist.casefold() in VARIOUS and " - " in title:
        return title.split(" - ", 1)[1].strip() or title
    return title


def _number(raw):
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _build_index():
    """genre key -> [track rows]; and genre key -> the genre as tagged, for the console."""
    library.ensure_loaded()
    with library._lock:
        at, tracks = library._loaded_at, list(library._tracks)
    with _lock:
        if _index["at"] == at:
            return _index
    genres, names = {}, {}
    for row in tracks:
        for g in genres_of(row):
            k = genre_key(g)
            genres.setdefault(k, []).append(row)
            names.setdefault(k, g)
    with _lock:
        _index.update(at=at, genres=genres, names=names)
        return _index


def genre_name(genre):
    return _build_index()["names"].get(genre_key(genre), genre)


def seed_genres(key):
    """The seed track's genres, or [] when it has none (or isn't in the library)."""
    row = library.track_row(key) if key else None
    return genres_of(row) if row else []


def common_genre(keys, share=0.4):
    """
    The genre most of these tracks share (for AI Playlist, which has no seed track), or
    None when no genre covers at least this share of them.
    """
    counts, seen = {}, 0
    for key in keys:
        row = library.track_row(key)
        if not row:
            continue
        seen += 1
        for g in {genre_key(x) for x in genres_of(row)}:
            counts[g] = counts.get(g, 0) + 1
    if not counts:
        return None
    best = max(counts, key=counts.get)
    return genre_name(best) if counts[best] >= max(1, share * seen) else None


def _rows_for(genres):
    """Every track in any of these genres, each once."""
    index = _build_index()["genres"]
    out, seen = [], set()
    for g in genres:
        for row in index.get(genre_key(g), []):
            key = str(row.get("Key"))
            if key not in seen:
                seen.add(key)
                out.append(row)
    return out


def _usable(row, group, exclude_keys, allowed):
    """A track a deep cut may be: long enough, not a hidden closer, not in the build, and allowed."""
    key = str(row.get("Key"))
    if key in exclude_keys or not (row.get("Name") or "").strip():
        return False
    seconds = _number(row.get("Duration"))
    if seconds and seconds < SHORTEST:
        return False
    on, minutes = engine.LONG_CLOSERS.get(group or "tracks", (engine.SKIP_LONG_CLOSERS, engine.LONG_CLOSER_MINUTES))
    closer = library.closer_info(key)
    if on and closer and closer[0] > minutes * 60:
        return False
    return allowed is None or allowed(key)


def _bottom(items, score, rng):
    """The lowest scoring fifth (at least one), ties in random order."""
    items = list(items)
    rng.shuffle(items)
    items.sort(key=score)
    return items[:max(1, math.ceil(len(items) * BOTTOM_SHARE))]


def _say(genres):
    return "; ".join(genre_name(g) for g in genres)


def pick_by_artist(genres, count, exclude_artists=(), exclude_keys=(), allowed=None, top_tracks=None,
                   group="artists", rng=None, now=None):
    """
    Deep cuts for Similar Artists: [(key, artist, title)] and a note (the reason when
    nothing could be picked, '' otherwise). top_tracks(artist) -> [titles], best first,
    is asked for each picked artist; without it, or with no title found, the artist's
    best rated track in the genre is used, then any at random.
    """
    rng, now = rng or random.Random(), now or time.time()
    if count <= 0:
        return [], ""
    if not genres:
        return [], "the seed track has no genre in your library"
    rows = _rows_for(genres)
    if library.played_dates_unreadable():
        return [], "JRiver's last played dates couldn't be read"
    skip = {library.norm(a) for a in exclude_artists if a}
    by_artist = {}
    for row in rows:
        artist = first_artist(row)
        if artist and library.norm(artist) not in skip:
            by_artist.setdefault(artist, []).append(row)
    if len(by_artist) < MIN_ARTISTS:
        return [], f"only {len(by_artist)} other artist{'' if len(by_artist) == 1 else 's'} in {_say(genres)}"
    cutoff = now - RECENT_DAYS * 86400

    def played_share(artist):
        tracks = by_artist[artist]
        recent = sum(1 for r in tracks if (library.last_played(r.get("Key")) or 0) >= cutoff)
        return recent / len(tracks)
    pool = _bottom(by_artist, played_share, rng)
    if len(pool) < MIN_ARTISTS and len(by_artist) >= MIN_ARTISTS:
        pool = sorted(by_artist, key=played_share)[:MIN_ARTISTS]   # a small genre: at least the five least played
    rng.shuffle(pool)
    exclude_keys = {str(k) for k in exclude_keys}
    picks, tried = [], 0
    for artist in pool:
        if len(picks) >= count or tried >= count * TRIES_EACH:
            break
        tried += 1
        usable = [r for r in by_artist[artist] if _usable(r, group, exclude_keys, allowed)]
        if not usable:
            continue
        row = None
        if top_tracks is not None:
            try:
                titles = top_tracks(artist) or []
            except Exception as e:
                engine.debug(f"Deep Cuts: top tracks for {artist} failed ({e})")
                titles = []
            wanted = [library.title_keys(t) for t in titles]
            for keys in wanted:
                row = next((r for r in usable if set(library.title_keys(r.get("Name"))) & set(keys)), None)
                if row:
                    break
        if row is None:
            best = max(_number(r.get("Rating")) for r in usable)
            row = rng.choice([r for r in usable if _number(r.get("Rating")) == best])
        picks.append((str(row["Key"]), artist, track_title(row)))
        exclude_keys.add(str(row["Key"]))
    if not picks:
        return [], f"none of the least played artists in {_say(genres)} had a track that could be used"
    return picks, ""


def pick_by_track(genres, count, exclude_artists=(), exclude_keys=(), allowed=None, group="tracks", rng=None):
    """
    Deep cuts for Similar Tracks and AI Playlist: [(key, artist, title)] and a note, as
    pick_by_artist. The genre's least played tracks (fewest plays, then played longest
    ago, never played first), the bottom 20%, picked at random, one per artist.
    """
    rng = rng or random.Random()
    if count <= 0:
        return [], ""
    if not genres:
        return [], "the seed track has no genre in your library"
    if library.played_dates_unreadable():
        return [], "JRiver's last played dates couldn't be read"
    skip = {library.norm(a) for a in exclude_artists if a}
    rows = [r for r in _rows_for(genres) if library.norm(first_artist(r)) not in skip]
    if len(rows) < MIN_TRACKS:
        return [], f"only {len(rows)} other track{'' if len(rows) == 1 else 's'} in {_say(genres)}"

    def neglect(row):
        return _number(row.get("Number Plays")), library.last_played(row.get("Key")) or 0
    pool = _bottom(rows, neglect, rng)
    if len(pool) < MIN_TRACKS:
        pool = sorted(rows, key=neglect)[:MIN_TRACKS]   # a small genre: at least the twenty least played
    rng.shuffle(pool)
    exclude_keys = {str(k) for k in exclude_keys}
    picks, used_artists = [], set()
    for row in pool:
        if len(picks) >= count:
            break
        artist = first_artist(row)
        if library.norm(artist) in used_artists or not _usable(row, group, exclude_keys, allowed):
            continue
        picks.append((str(row["Key"]), artist, track_title(row)))
        used_artists.add(library.norm(artist))
        exclude_keys.add(str(row["Key"]))
    if not picks:
        return [], f"none of the least played tracks in {_say(genres)} could be used"
    return picks, ""
