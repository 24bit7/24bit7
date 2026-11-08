"""
24bit7 - Radio (Ben, 5 Nov 2026; built 6 Nov 2026). A playlist with no seed: lanes from what you play.

Analysis (once, then by hand with Re-analyse)
  Played artists    every artist with MIN_PLAYS or more plays in JRiver (Number Plays, the whole library)
  Genre rule        the sources' genres first (Last.fm's weighted tags for the artist); your own Genre tag
                    only when no source knows the artist; neither, and the artist isn't a data point
  Lanes             artists clustered by their genres (average linkage on cosine similarity), cut into at
                    most LANES_MAX groups; a group of fewer than LANE_MIN artists folds into its nearest
                    neighbour. A lane is named by its two strongest genres, weighted by plays
  Split             a lane's own two halves one level down the same tree: no new analysis. Offered when
                    both halves have LANE_MIN artists and PILLARS_TO_SPLIT pillars of their own. A half
                    that's nearly a copy of its lane (most of its pillars the same) gives way to its own
                    halves, so a split always shows something new (7 Nov 2026)
  Pillars           about twelve of your own most played in the lane, blended with about eight of the
                    sources' canon for it (Last.fm's top artists for its genres) that you own (PILLAR_OWNED
                    tracks or more), each side filling the other's gap: your own first since 7 Nov 2026, as
                    broad tags pulled mainstream acts into the canon. Compilations (every track named
                    "Artist - Title", or Various Artists) are never pillars. Your edits (Edit on a station's
                    row) are laid over them, kept by the station's genre path
  Resting           too little played yet (fewer than MIN_ARTISTS played artists with genres): Radio rests
                    and says how far off it is

A build
  Consensus over three random pillars: artists on two or more of their similar-artist lists, each giving
  its top tracks you own, with a couple of each circle pillar's own (at random from its best known five).
  An agreeing artist that another station fits over twice as well (NEAR) is left out, so a round stays
  in the station without the Moderator. Short of TARGET_MINUTES, another
  pillar joins (still two or more lists, against everything pulled so far), up to six. A pillar song goes
  first so music starts at once. Non-stop carries on with a fresh round from other random pillars, never
  from what Radio itself played, so it stays in the lane.
"""

import json
import random
import re
import time
from collections import Counter, defaultdict
from datetime import datetime

import requests

import engine
from i18n import t, tn

MIN_PLAYS = 10          # an artist with this many plays counts as played
MIN_ARTISTS = 40        # played artists with genres needed before Radio wakes
TAG_MIN = 10            # a Last.fm tag's weight (0 to 100) to count
TAGS_PER_ARTIST = 8
LANES_MAX = 24
LANE_MIN = 5
PILLAR_OWNED = 5
PILLARS_CANON = 8
PILLARS_OWN = 12
NEAR = 0.5              # an agreeing artist is left out when another station fits it over twice as well
COPY_SHARE = 0.75       # a half with this share of its lane's pillars is a copy: its own halves stand in
ANALYSIS_VERSION = 2    # 7 Nov 2026: own pillars first, copies give way; an older analysis is cut again
PILLARS_TO_SPLIT = 6
ARTISTS_MAX = 1500      # the most played artists analysed, for a very big library
TARGET_MINUTES = 60
CIRCLE_START = 3
CIRCLE_MAX = 6
AGREE = 2
PILLAR_SONGS = 5
STATIONS_MAX = 40      # the most stations the Stations section's box asks for
ANALYSIS_KEY = "radio_analysis"
ROW_KEY = "radio_row"   # the face's lane (the last played), the lanes split open, the station count asked for
TAGS_KEY = "radio_tags"
CANON_KEY = "radio_canon"   # Last.fm's top artists per genre: kept so a new station count re-cuts in seconds
NAMES_KEY = "radio_names"   # the stations you renamed: {its genre path: your name}
PILLARS_KEY = "radio_pillars"   # your pillar edits: {a station's genre path: {"add": [names], "remove": [names]}}
_canon_cache = None         # the CANON_KEY cache while an analysis runs
NOT_GENRE = re.compile(
    r"^(seen live|favou?rites?|love|loved|awesome|beautiful|male vocalists?|female vocalists?|\d{2,4}s?|"
    r"british|uk|american|usa|english|german|french|canadian|australian|irish|scottish|swedish|norwegian|"
    r"icelandic|japanese|danish|dutch|new zealand|kiwi|all|my|albums i own|under \d+ listeners|spotify|"
    r"check out|good|cool|amazing|genius|legend|legends|classic|best|favorite artists|favourite artists|"
    r"compilation|various artists|mix|dj mix|seen in concert)$", re.I)
COMPILATION_NAMES = {"various artists", "various", "va", "soundtrack", "original soundtrack"}


# --- what's kept ------------------------------------------------------------------------------------

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


def analysis():
    """The last analysis: {"when", "lanes": [lane], "resting": None or why}, or None before the first."""
    return _meta(ANALYSIS_KEY, None)


def lanes(include_children=False):
    """Every lane, top level first; with include_children, the Split halves too (depth first)."""
    out = []

    def walk(items):
        for lane in items:
            out.append(lane)
            if include_children:
                walk(lane.get("children") or [])
    walk((analysis() or {}).get("lanes") or [])
    return out


def lane(lane_id):
    return next((x for x in lanes(include_children=True) if x["id"] == lane_id), None)


def lane_by_key(key):
    """The lane with this genre path (its "key"), or None."""
    return next((x for x in lanes(include_children=True) if key and x.get("key") == key), None)


def outdated():
    """An analysis made before this version's rules (ANALYSIS_VERSION): the next Radio press cuts it again."""
    result = analysis()
    return bool(result and result.get("lanes") and (result.get("version") or 1) < ANALYSIS_VERSION)


def recut(report, lane_id=None):
    """
    Cuts an outdated analysis again from the genres kept (seconds, no new questions to the sources), keeping
    your names and pillar edits, and the last station played. Returns lane_id's station's new id (or None).
    """
    old, last = lane(lane_id) if lane_id else None, lane(row()["default"]) if row()["default"] else None
    report(t("Radio: making the stations again with this version's rules. It takes a few seconds; your names "
             "and pillars are kept."))
    analyse(report, fresh=False)
    if last is not None:
        found = lane_by_key(last.get("key")) or lane_named(last.get("auto") or last["name"])
        set_row(default=found["id"] if found else None)
    found = (lane_by_key(old.get("key")) or lane_named(old.get("auto") or old["name"])) if old else None
    return found["id"] if found else None


def lane_named(name):
    """
    The lane a Radio playlist set to a lane plays, by its name (Classic Rock / Rock), so it survives a
    Re-analyse, which numbers the lanes afresh. None when no lane is called that now.
    """
    wanted = (name or "").strip().lower()
    if not wanted:
        return None
    every = lanes(include_children=True)
    return next((x for x in every if x["name"].lower() == wanted), None) \
        or next((x for x in every if (x.get("auto") or "").lower() == wanted), None)


def row():
    """
    {"default": lane id, "open": [lane ids split open], "buttons": [lane ids on the row, before 1.31.0],
    "count": the number of stations asked for on Radio's page, or None for as many as the analysis finds,
    "recent": [genre paths of the last stations played, newest first]}.
    """
    saved = _meta(ROW_KEY, {})
    count = saved.get("count")
    return {"default": saved.get("default"), "open": list(saved.get("open") or []),
            "buttons": list(saved.get("buttons") or []), "count": int(count) if count else None,
            "recent": list(saved.get("recent") or [])}


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")   # shown through t()


def when_text(stamp):
    """The analysis's time as Radio's page shows it: '20:18' today, else '6 Nov, 20:18'."""
    try:
        when = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return ""
    if when.date() == datetime.now().date():
        return when.strftime("%H:%M")
    return f"{when.day} {t(MONTHS[when.month - 1])}, {when.strftime('%H:%M')}"


def names():
    """The stations you renamed: {genre path: your name}."""
    return dict(_meta(NAMES_KEY, {}))


def rename(lane_id, name):
    """
    Renames a station (Ben, 7 Nov 2026). Blank goes back to its genre name. Kept by the station's genre path,
    so the name comes back with the station after a Re-analyse or a new count; a Radio playlist set to the
    station follows the new name. Returns a problem line, or None.
    """
    result = analysis()
    found = lane(lane_id)
    if not result or found is None:
        return t("That station has gone since the stations were made again.")
    new = (name or "").strip() or found.get("auto") or found["name"]
    if any(x["name"].lower() == new.lower() and x["id"] != lane_id for x in lanes(include_children=True)):
        return t("Another station is called {name}.", name=new)
    old = found["name"]
    saved = names()
    if new == (found.get("auto") or found["name"]):
        saved.pop(found.get("key") or found["name"], None)
    else:
        saved[found.get("key") or found["name"]] = new

    def walk(items):
        for x in items:
            if x["id"] == lane_id:
                x["name"] = new
            walk(x.get("children") or [])
    walk(result.get("lanes") or [])
    _set_meta(ANALYSIS_KEY, result)
    _set_meta(NAMES_KEY, saved)
    import buttons
    items = buttons.load()
    moved = False
    for b in items:
        if buttons.is_radio(b) and (b.get("lane") or "").lower() == old.lower():
            b["lane"], moved = new, True
    if moved:
        buttons.save(items)
    return None


def _apply_names(out, report):
    """Each station's genre name kept as "auto" and its genre path as "key"; your names laid over them."""
    saved = names()
    seen = set()

    def walk(items, path):
        for x in items:
            x["auto"] = x["name"]
            x["key"] = (path + " > " if path else "") + x["auto"]
            seen.add(x["key"])
            if x["key"] in saved:
                x["name"] = saved[x["key"]]
            walk(x.get("children") or [], x["key"])
    walk(out, "")
    for key, name in saved.items():
        if key not in seen:
            report("  " + t("Your name {name} is kept for {station}, which isn't a station this time.", name=name,
                            station=key.split(" > ")[-1]))


def set_row(**changes):
    saved = row()
    saved.update(changes)
    _set_meta(ROW_KEY, saved)


def default_lane():
    """The lane Radio's face plays: the last played, or the biggest the first time (or once that lane's gone)."""
    wanted = row()["default"]
    if wanted and lane(wanted):
        return lane(wanted)
    found = lanes()
    return found[0] if found else None


# --- by voice (8 Nov 2026) --------------------------------------------------------------------------

RECENT_MAX = 5   # stations Needle Drop offers when asked for Radio with no station
ORDINALS = {"first": 0, "one": 0, "second": 1, "two": 1, "third": 2, "three": 2, "fourth": 3, "four": 3,
            "fifth": 4, "five": 4, "last": -1}
FILLER = {"the", "station", "radio", "please", "number", "a"}


def remember_played(lane_):
    """A station played, newest first in the list Needle Drop offers; kept by genre path, which a Re-analyse keeps."""
    key = lane_.get("key") or lane_["name"]
    recent = [k for k in row()["recent"] if k != key]
    set_row(recent=([key] + recent)[:RECENT_MAX])


def recent_lanes(count=RECENT_MAX):
    """The stations Needle Drop offers: the last played, newest first, then the biggest to make up the count."""
    out = []
    for key in row()["recent"]:
        found = lane_by_key(key) or lane_named(key)
        if found and all(x["id"] != found["id"] for x in out):
            out.append(found)
    for x in lanes():
        if all(y["id"] != x["id"] for y in out):
            out.append(x)
    return out[:count]


def spoken_name(lane_):
    """A station as Alexa says it: 'Folk / Singer-Songwriter' reads as 'Folk and Singer-Songwriter'."""
    return lane_["name"].replace(" / ", " and ")


def ask_which(offered):
    """'Which station? One, Classic Rock and Rock. Two, Folk.' Numbered, since a name may hold an 'and'."""
    words = ("One", "Two", "Three", "Four", "Five")
    return "Which station? " + " ".join(f"{words[i]}, {spoken_name(x)}." for i, x in enumerate(offered[:len(words)]))


def match_station(heard, offered=None):
    """
    The station a spoken answer names, or None: 'the second one' or 'two' from the list offered; else the name in
    full ('classic rock rock'), one part of it ('folk'), or every word heard within it ('vocal'), as renamed or
    by its genre name. Several alike: the one offered first, then the biggest.
    """
    import library
    offered = recent_lanes() if offered is None else offered
    words = [w for w in library.norm(heard or "").split() if w not in FILLER]
    if words and words[0] in ORDINALS and (len(words) == 1 or words[1:] == ["one"]):
        index = ORDINALS[words[0]]
        return offered[index] if offered and index < len(offered) else None
    phrase = " ".join(words)
    if not phrase:
        return None
    every = lanes(include_children=True)
    order = {x["id"]: i for i, x in enumerate(offered)}

    def names(x):
        return [n for n in (x["name"], x.get("auto") or "") if n]

    def best(found):
        return min(found, key=lambda x: (order.get(x["id"], len(order)), -share(x))) if found else None
    tiers = (
        lambda x: any(library.norm(n) == phrase for n in names(x)),
        lambda x: any(library.norm(part) == phrase for n in names(x) for part in n.split("/")),
        lambda x: any(set(words) <= set(library.norm(n).split()) for n in names(x)),
    )
    for rule in tiers:
        found = best([x for x in every if rule(x)])
        if found:
            return found
    return None


def resting():
    """Why Radio rests ({"have", "need"}), or None."""
    result = analysis()
    return (result or {}).get("resting")


def share(lane_):
    """The lane's share of the plays across every lane, as a whole percentage."""
    total = sum(x["plays"] for x in lanes()) or 1
    return round(100 * lane_["plays"] / total)


def visible_rows():
    """The lane list as shown: (lane, depth), a split lane's halves under it while it's open."""
    opened = set(row()["open"])
    out = []

    def walk(items, depth):
        for x in items:
            out.append((x, depth))
            if x["id"] in opened and x.get("children"):
                walk(x["children"], depth + 1)
    walk((analysis() or {}).get("lanes") or [], 0)
    return out


# --- the library ------------------------------------------------------------------------------------

def _plays(row):
    try:
        return int(float(row.get("Number Plays") or 0))
    except (TypeError, ValueError):
        return 0


def library_view():
    """
    {artist key: {"name", "plays", "owned", "genres": Counter, "named": tracks named "X - Y"}} from the
    library held in memory.
    """
    import library
    library.ensure_loaded()
    with library._lock:
        rows = list(library._tracks)
    out = {}
    for r in rows:
        name = r.get("Artist") or ""
        a = engine.artist_key(name)
        if not a:
            continue
        v = out.setdefault(a, {"name": name, "plays": 0, "owned": 0, "genres": Counter(), "named": 0})
        v["owned"] += 1
        v["plays"] += _plays(r)
        if " - " in str(r.get("Name") or ""):
            v["named"] += 1
        for g in str(r.get("Genre") or "").split(";"):
            if g.strip():
                v["genres"][g.strip()] += 1
    return out


def is_compilation(view_row):
    """
    Not an act to build a lane on: Various Artists, a compilation series (every track named "Artist -
    Title"), or two acts in one tag ("Dope;Angus Stone").
    """
    if view_row["name"].strip().lower() in COMPILATION_NAMES or ";" in view_row["name"]:
        return True
    return view_row["owned"] >= 3 and view_row["named"] * 2 >= view_row["owned"]


# --- the sources ------------------------------------------------------------------------------------

def _lastfm(params):
    r = requests.get("http://ws.audioscrobbler.com/2.0/",
                     params=dict(params, api_key=engine.LASTFM_KEY, format="json"), timeout=15)
    return r.json()


def artist_tags(names, report, cache=None):
    """
    {artist key: [(genre, weight)]} from Last.fm, for the artists not already cached. Kept between
    analyses, so a Re-analyse only asks about new artists. None for an artist Last.fm couldn't answer.
    """
    cache = dict(_meta(TAGS_KEY, {})) if cache is None else cache
    todo = [(a, n) for a, n in names if a not in cache]
    if todo:
        report("  " + t("Asking Last.fm for the genres of {count} artists. The first time takes a few minutes.",
                        count=len(todo)))
    failed = 0
    for i, (a, name) in enumerate(todo, 1):
        engine.check_cancelled()
        try:
            data = _lastfm({"method": "artist.gettoptags", "artist": name, "autocorrect": 1})
            cache[a] = [(x["name"].lower().strip(), int(x.get("count", 0)))
                        for x in data.get("toptags", {}).get("tag", [])]
        except Exception as e:
            engine.debug(f"Radio: no tags for {name} ({e})")
            failed += 1
            continue   # not cached, so the next analysis asks again
        if i % 100 == 0:
            _set_meta(TAGS_KEY, cache)
            report("    " + t("{done} of {count}...", done=i, count=len(todo)))
        time.sleep(0.2)
    _set_meta(TAGS_KEY, cache)
    if failed:
        report("  " + t("Note: Last.fm didn't answer for {count} artists; their own Genre tags stood in.", count=failed))
    return cache


def tag_top_artists(tag, limit=100):
    """Last.fm's top artists for a genre, best first."""
    try:
        data = _lastfm({"method": "tag.gettopartists", "tag": tag, "limit": limit})
        return [x["name"] for x in data.get("topartists", {}).get("artist", [])]
    except Exception as e:
        engine.debug(f"Radio: no top artists for {tag} ({e})")
        return []


def _top_for(tag):
    """tag_top_artists, from the analysis's cache when it has the genre (a new station count asks nothing)."""
    if _canon_cache is not None and _canon_cache.get(tag):
        return list(_canon_cache[tag])
    found = tag_top_artists(tag)
    if _canon_cache is not None and found:
        _canon_cache[tag] = found
    return found


def genres_for(a, view_row, cache):
    """The genre rule: sources first, then your own tag, else nothing. Returns ({genre: weight}, case)."""
    src = [(g, w) for g, w in (cache.get(a) or []) if w >= TAG_MIN and not NOT_GENRE.match(g)]
    if src:
        return dict(src[:TAGS_PER_ARTIST]), "sources"
    if view_row["genres"]:
        return {g.lower(): 100 for g, _ in view_row["genres"].most_common(2)}, "own"
    return {}, "none"


# --- lanes ------------------------------------------------------------------------------------------

def _cosine(u, v):
    if len(u) > len(v):
        u, v = v, u
    dot = sum(w * v.get(g, 0.0) for g, w in u.items())
    return dot


def _unit(vec):
    norm = sum(w * w for w in vec.values()) ** 0.5 or 1.0
    return {g: w / norm for g, w in vec.items()}


def cluster(vectors):
    """
    Average-linkage clustering of unit vectors (the nearest-neighbour chain). Returns the merges as
    (similarity, cluster a, cluster b, new cluster) in the order a tree is built, most similar first;
    clusters 0..n-1 are the items themselves.
    """
    n = len(vectors)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            sim[i][j] = sim[j][i] = _cosine(vectors[i], vectors[j])
    size = [1] * n
    active = set(range(n))
    label = list(range(n))   # the cluster id now held at each row of sim
    merges, chain = [], []
    next_id = n
    while len(active) > 1:
        if not chain:
            chain.append(min(active))
        a = chain[-1]
        prev = chain[-2] if len(chain) > 1 else None
        best, best_sim = None, -2.0
        for c in active:
            if c == a:
                continue
            s = sim[a][c]
            if s > best_sim or (s == best_sim and c == prev):
                best, best_sim = c, s
        if best == prev:
            chain.pop()
            chain.pop()
            # rows a and prev merge into row a; Lance-Williams for average linkage
            for c in active:
                if c not in (a, prev):
                    s = (size[a] * sim[a][c] + size[prev] * sim[prev][c]) / (size[a] + size[prev])
                    sim[a][c] = sim[c][a] = s
            merges.append((best_sim, label[a], label[prev], next_id))
            size[a] += size[prev]
            active.discard(prev)
            label[a] = next_id
            next_id += 1
        else:
            chain.append(best)
    # the chain finds merges out of order. Average linkage never merges at a higher similarity than the
    # merges below it, so most similar first puts every merge after the two it joins
    merges.sort(key=lambda m: (-m[0], m[3]))
    return merges


def _tree(n, merges):
    """{node: (left, right)} and each node's leaves."""
    kids, leaves = {}, {i: [i] for i in range(n)}
    for _s, a, b, new in merges:
        kids[new] = (a, b)
        leaves[new] = leaves[a] + leaves[b]
    return kids, leaves


def _cut(n, merges, k):
    """The roots left once all but the last k - 1 merges are made: k groups (fewer if there are fewer items)."""
    keep = merges[:max(0, n - k)]
    roots = set(range(n))
    for _s, a, b, new in keep:
        roots.discard(a)
        roots.discard(b)
        roots.add(new)
    return roots


def _name(genres, prefer=None):
    """The lane's two strongest genres; the sources' own genres first, so a lane isn't named after your tag."""
    ranked = [g for g, _ in genres.most_common()]
    if prefer:
        ranked = [g for g in ranked if g in prefer] + [g for g in ranked if g not in prefer]
    top = ranked[:2]
    return " / ".join(g.title() if g.islower() else g for g in top) or t("Radio")


def _lane_info(members, artists, vecs, view):
    genres = Counter()
    for i in members:
        for g, w in vecs[i].items():
            genres[g] += w * max(1, view[artists[i]]["plays"])
    return genres


def _canon(genres, view, owned_ok, report):
    """The sources' canon for a lane: Last.fm's top artists for its top genres that you own. Artist keys, best first."""
    tags = [g for g, _ in genres.most_common(2)]
    ranked = []
    lists = [_top_for(g) for g in tags]
    lists = [x for x in lists if x]
    if len(lists) == 2:   # both genres: artists high in both first, by their summed rank
        a_rank = {engine.artist_key(n): i for i, n in enumerate(lists[0])}
        b_rank = {engine.artist_key(n): i for i, n in enumerate(lists[1])}
        both = sorted(set(a_rank) & set(b_rank), key=lambda k: a_rank[k] + b_rank[k])
        ranked = both + [engine.artist_key(n) for n in lists[0] + lists[1]]
    elif lists:
        ranked = [engine.artist_key(n) for n in lists[0]]
    out = []
    for a in ranked:
        if a in owned_ok and a not in out:
            out.append(a)
    return out


def pillars_for(members_keys, genres, view, report, elsewhere=(), own_keys=None):
    """
    About twelve of your own most played in the lane and eight canon, each side filling the other's gap.
    elsewhere: artists you play that the analysis put in another lane, so the canon doesn't pull them in.
    """
    elsewhere = set(elsewhere)
    owned_ok = {a for a, v in view.items() if v["owned"] >= PILLAR_OWNED and not is_compilation(v)
                and a not in elsewhere}
    canon = _canon(genres, view, owned_ok, report)
    own = sorted((a for a in (members_keys if own_keys is None else own_keys) if a in owned_ok),
                 key=lambda a: -view[a]["plays"])   # a stray folded in from a tiny group isn't one of the lane's own
    total = PILLARS_CANON + PILLARS_OWN
    take_own = min(len(own), max(PILLARS_OWN, total - len(canon)))
    picked = own[:take_own]
    for a in canon + own[take_own:]:
        if len(picked) >= total:
            break
        if a not in picked:
            picked.append(a)
    return [view[a]["name"] for a in picked]


def _make_lane(lane_id, node, kids, leaves, artists, vecs, view, report, depth, prefer=None, extra=()):
    members = list(leaves[node]) + list(extra)
    keys = [artists[i] for i in members]
    genres = _lane_info(members, artists, vecs, view)
    elsewhere = set(artists) - set(keys)
    lane_ = {"id": lane_id, "name": _name(genres, prefer), "genres": [g for g, _ in genres.most_common(6)],
             "artists": len(keys), "plays": sum(view[a]["plays"] for a in keys),
             "pillars": pillars_for(keys, genres, view, report, elsewhere,
                                    own_keys=[artists[i] for i in leaves[node]]), "children": [],
             "centroid": dict(Counter({g: w for g, w in genres.items()}).most_common(12))}
    split = node
    while split in kids and min(len(leaves[c]) for c in kids[split]) < LANE_MIN:
        split = max(kids[split], key=lambda c: len(leaves[c]))   # a sliver isn't a half: look further down
    if depth < 3 and split in kids:
        halves = []
        for side, child in zip("ab", kids[split]):
            if len(leaves[child]) < LANE_MIN:
                halves = []
                break
            halves.append(_make_lane(f"{lane_id}{side}", child, kids, leaves, artists, vecs, view, report, depth + 1,
                                     prefer))
        if len(halves) == 2 and all(len(h["pillars"]) >= PILLARS_TO_SPLIT for h in halves) \
                and halves[0]["name"] != halves[1]["name"]:
            lane_["children"] = without_copies(lane_, halves)
    return lane_


def is_copy(half, parent):
    """A half whose pillars are mostly its lane's: playing it would sound like the lane itself."""
    mine = half.get("pillars") or []
    theirs = {engine.artist_key(n) for n in parent.get("pillars") or []}
    return bool(mine) and sum(engine.artist_key(n) in theirs for n in mine) >= COPY_SHARE * len(mine)


def without_copies(parent, halves):
    """
    A split's halves, with any half that's nearly a copy of the lane replaced by its own halves (Ben, 7 Nov
    2026): Rock opens to Blues, Grunge, Classic Rock and the rest, not to Blues and another Rock. A copy with
    no halves of its own stays: it's the lane without its other half.
    """
    out = list(halves)
    while True:
        i = next((i for i, h in enumerate(out) if h.get("children") and is_copy(h, parent)), None)
        if i is None:
            return out
        out[i:i + 1] = out[i]["children"]


def _stations_cut(n, merges, leaves, asked):
    """
    The tree cut into groups: k groups, where k is one per twenty artists (at most LANES_MAX) or, with a
    count asked for on Radio's page, the fewest that give that many groups of LANE_MIN artists or more (as
    near as the tree allows). Returns (roots, groups big enough to be stations).
    """
    def at(k):
        roots = _cut(n, merges, k)
        return roots, [r for r in roots if len(leaves[r]) >= LANE_MIN]
    if not asked:
        return at(max(2, min(LANES_MAX, n // 20)))
    best = None
    for k in range(1, n + 1):   # k groups hold at most k stations; more asked than the tree allows: the most it gives
        roots, big = at(k)
        if best is None or len(big) > len(best[1]):
            best = (roots, big)
        if len(big) >= asked:
            return roots, big
    return best


def analyse(report=print, fresh=True):
    """
    Reads plays, asks the sources for genres, makes the lanes and their pillars, and keeps the lot.
    fresh: Re-analyse asks Last.fm for each genre's top artists again; a new station count (fresh False)
    uses the ones kept from last time, so it takes seconds.
    """
    global _canon_cache
    _canon_cache = {} if fresh else dict(_meta(CANON_KEY, {}))
    try:
        return _analyse(report)
    finally:
        _set_meta(CANON_KEY, _canon_cache)
        _canon_cache = None


def _analyse(report):
    started = time.time()
    view = library_view()
    played = sorted((a for a, v in view.items() if v["plays"] >= MIN_PLAYS), key=lambda a: -view[a]["plays"])
    played = played[:ARTISTS_MAX]
    report(t("Radio: analysing what you play. {count} artists have {plays} or more plays.", count=len(played),
             plays=MIN_PLAYS))
    cache = artist_tags([(a, view[a]["name"]) for a in played], report)
    artists, vecs, cases, prefer = [], [], Counter(), set()
    for a in played:
        genres, case = genres_for(a, view[a], cache)
        cases[case] += 1
        if case == "sources":
            prefer |= set(genres)
        if genres:
            artists.append(a)
            vecs.append(_unit(genres))
    report("  " + t("Genres from the sources for {sources} artists, from your own tags for {own}, none for {none}.",
                    sources=cases["sources"], own=cases["own"], none=cases["none"]))
    if len(artists) < MIN_ARTISTS:
        result = {"when": datetime.now().strftime("%Y-%m-%d %H:%M"), "lanes": [],
                  "resting": {"have": len(artists), "need": MIN_ARTISTS}}
        _set_meta(ANALYSIS_KEY, result)
        report(t("Radio is resting: it needs {need} artists you've played {plays} or more times, and there are "
                 "{have} so far. It wakes once there are enough.", need=MIN_ARTISTS, plays=MIN_PLAYS,
                 have=len(artists)))
        return result
    merges = cluster(vecs)
    kids, leaves = _tree(len(artists), merges)
    asked = row()["count"]
    roots, big = _stations_cut(len(artists), merges, leaves, asked)
    small = [r for r in roots if len(leaves[r]) < LANE_MIN]
    if not big:
        big, small = [max(roots, key=lambda r: len(leaves[r]))], [r for r in roots if r != max(roots, key=lambda r: len(leaves[r]))]
    # a small group folds into the big one whose genres are nearest
    centroids = {r: _unit(Counter({g: w for i in leaves[r] for g, w in vecs[i].items()})) for r in big}
    extra = defaultdict(list)
    for r in small:
        mine = _unit(Counter({g: w for i in leaves[r] for g, w in vecs[i].items()}))
        target = max(big, key=lambda b: _cosine(mine, centroids[b]))
        extra[target] += leaves[r]
    out = []
    ordered = sorted(big, key=lambda r: -sum(view[artists[i]]["plays"] for i in leaves[r] + extra[r]))
    for n, r in enumerate(ordered, 1):
        engine.check_cancelled()
        # the folded-in artists count in the lane, though Split keeps to the tree's halves
        out.append(_make_lane(str(n), r, kids, leaves, artists, vecs, view, report, depth=0, prefer=prefer,
                              extra=extra[r]))
    taken = Counter(x["name"] for x in out)
    for x in out:   # two lanes can't share a name: the second takes its third genre instead
        if taken[x["name"]] > 1 and len(x["genres"]) > 2:
            x["name"] = " / ".join(g.title() for g in (x["genres"][0], x["genres"][2]))
    _apply_names(out, report)
    _lay_pillars(out, report)
    result = {"when": datetime.now().strftime("%Y-%m-%d %H:%M"), "lanes": out, "resting": None,
              "known": [a for a in played], "version": ANALYSIS_VERSION}
    _set_meta(ANALYSIS_KEY, result)
    report(tn("Radio: {count} station, from {artists} artists, {seconds} s.",
              "Radio: {count} stations, from {artists} artists, {seconds} s.", len(out), artists=len(artists),
              seconds=max(0, round(time.time() - started))))
    if asked and len(out) < asked:
        report("  " + t("You asked for {asked} stations; {made} is as many as stand alone, since the rest would "
                        "have fewer than {least} artists.", asked=asked, made=len(out), least=LANE_MIN))
    for x in out:
        report("  " + t("{name}: {artists} artists; pillars {pillars}.", name=x["name"], artists=x["artists"],
                        pillars=", ".join(x["pillars"][:6]) + ("..." if len(x["pillars"]) > 6 else "")))
    return result


# --- your pillars (Edit on a station's row, Ben, 7 Nov 2026) ----------------------------------------

def pillar_edits():
    """{a station's genre path: {"add": [artist names], "remove": [artist names]}}."""
    return dict(_meta(PILLARS_KEY, {}))


def _path(x):
    return x.get("key") or x.get("auto") or x["name"]


def _ensure_keys(result):
    """An analysis from before renames has no genre paths: they're worked out once, as _apply_names does."""
    def walk(items, path):
        for x in items:
            x.setdefault("auto", x["name"])
            x.setdefault("key", (path + " > " if path else "") + x["auto"])
            walk(x.get("children") or [], x["key"])
    walk(result.get("lanes") or [], "")


def _lay_pillars(items, report=None):
    """
    Each station's pillars: the analysis's own (kept as "auto_pillars"), less what you removed from it or from
    a station it's a half of, plus what you added to it. A half left with fewer than CIRCLE_START keeps its own.
    """
    saved = pillar_edits()
    seen = set()

    def walk(xs, removed):
        for x in xs:
            x.setdefault("auto_pillars", list(x.get("pillars") or []))
            mine = saved.get(_path(x)) or {}
            seen.add(_path(x))
            gone = removed | {engine.artist_key(n) for n in mine.get("remove") or []}
            kept = [n for n in x["auto_pillars"] if engine.artist_key(n) not in gone]
            if len(kept) < CIRCLE_START:
                kept = [n for n in x["auto_pillars"] if engine.artist_key(n) not in removed] or list(x["auto_pillars"])
            for n in mine.get("add") or []:
                if engine.artist_key(n) not in {engine.artist_key(k) for k in kept}:
                    kept.append(n)
            x["pillars"] = kept
            walk(x.get("children") or [], gone)
    walk(items, set())
    if report is not None:
        for path in saved:
            if path not in seen:
                report("  " + t("Your pillars for {station} are kept, though it isn't a station this time.",
                                station=path.split(" > ")[-1]))


def _save_pillars(result, saved):
    _set_meta(PILLARS_KEY, saved)
    _lay_pillars(result.get("lanes") or [])
    _set_meta(ANALYSIS_KEY, result)


def _every(result):
    out = []

    def walk(items):
        for x in items:
            out.append(x)
            walk(x.get("children") or [])
    walk(result.get("lanes") or [])
    return out


def _editing(lane_id):
    """(the analysis, the station in it, your edits, the station's own edits), or None if it's gone."""
    result = analysis()
    if not result:
        return None
    _ensure_keys(result)
    found = next((x for x in _every(result) if x["id"] == lane_id), None)
    if found is None:
        return None
    saved = pillar_edits()
    mine = saved.setdefault(_path(found), {"add": [], "remove": []})
    mine.setdefault("add", [])
    mine.setdefault("remove", [])
    return result, found, saved, mine


def _tidy(saved):
    for path in [p for p, v in saved.items() if not (v.get("add") or v.get("remove"))]:
        saved.pop(path)


def edited(lane_):
    """Whether you've changed this station's pillars (Restore Pillars is offered)."""
    mine = pillar_edits().get(_path(lane_)) or {}
    return bool(mine.get("add") or mine.get("remove"))


def added(lane_):
    """The artists you added to this station, as keys."""
    return {engine.artist_key(n) for n in (pillar_edits().get(_path(lane_)) or {}).get("add") or []}


def add_pillar(lane_id, name):
    """Adds an artist from your library to a station's pillars. Returns a problem line, or None."""
    found = _editing(lane_id)
    if found is None:
        return t("That station has gone since the stations were made again.")
    result, station, saved, mine = found
    a = engine.artist_key(name)
    if a not in {engine.artist_key(n) for n in station.get("pillars") or []}:
        mine["remove"] = [n for n in mine["remove"] if engine.artist_key(n) != a]
        if a not in {engine.artist_key(n) for n in station.get("auto_pillars") or station.get("pillars") or []}:
            mine["add"].append(name)
    _tidy(saved)
    _save_pillars(result, saved)
    return None


def remove_pillar(lane_id, name):
    """Removes a pillar from a station and its halves; at least CIRCLE_START stay. A problem line, or None."""
    found = _editing(lane_id)
    if found is None:
        return t("That station has gone since the stations were made again.")
    result, station, saved, mine = found
    if len(station.get("pillars") or []) <= CIRCLE_START:
        return t("A station needs at least {count} pillars, since each round starts from {count}.", count=CIRCLE_START)
    a = engine.artist_key(name)
    if a in {engine.artist_key(n) for n in mine["add"]}:
        mine["add"] = [n for n in mine["add"] if engine.artist_key(n) != a]
    else:
        mine["remove"].append(name)
    _tidy(saved)
    _save_pillars(result, saved)
    return None


def restore_pillars(lane_id):
    """The analysis's own pillars again for this station, and for its halves as far as this station goes."""
    found = _editing(lane_id)
    if found is None:
        return
    result, station, saved, _mine = found
    saved.pop(_path(station), None)
    _save_pillars(result, saved)


def removed_from(lane_):
    """Artist keys you removed from this station or from a station it's a half of."""
    saved = pillar_edits()
    parts = _path(lane_).split(" > ")
    out = set()
    for i in range(1, len(parts) + 1):
        out |= {engine.artist_key(n) for n in (saved.get(" > ".join(parts[:i])) or {}).get("remove") or []}
    return out


def library_artists():
    """[(name, tracks you own)] for Edit's Add From Your Library: every artist but compilations, A to Z."""
    view = library_view()
    rows = [(v["name"], v["owned"]) for v in view.values() if not is_compilation(v)]
    return sorted(rows, key=lambda r: r[0].lower())


def join_new_artists(report, limit=10):
    """
    Artists played enough since the analysis join the lane nearest in genre, as pillars of their own when
    they qualify, without a Re-analyse. A few at a time, at the start of a build.
    """
    result = analysis()
    if not result or not result.get("lanes"):
        return
    view = library_view()
    known = set(result.get("known") or [])
    new = [a for a, v in view.items() if v["plays"] >= MIN_PLAYS and a not in known][:limit]
    if not new:
        return
    cache = artist_tags([(a, view[a]["name"]) for a in new], lambda line: None)
    joined = []
    for a in new:
        known.add(a)
        genres, _case = genres_for(a, view[a], cache)
        if not genres or view[a]["owned"] < PILLAR_OWNED or is_compilation(view[a]):
            continue
        mine = _unit(genres)
        target = max(result["lanes"], key=lambda x: _cosine(mine, _unit(x.get("centroid") or {})))
        if a in removed_from(target):   # you took it out: it doesn't come back by itself
            continue
        if view[a]["name"] not in target["pillars"]:
            target.setdefault("auto_pillars", list(target["pillars"])).append(view[a]["name"])
            target["pillars"].append(view[a]["name"])
            joined.append((view[a]["name"], target["name"]))
    result["known"] = sorted(known)
    _set_meta(ANALYSIS_KEY, result)
    for name, lane_name in joined:
        report("  " + t("Radio: {artist} joins {station} as a pillar.", artist=name, station=lane_name))


# --- a build ----------------------------------------------------------------------------------------

def _owned_top(artist, have, played, limit, pool=None):
    """
    An artist's top tracks you own, then your most played of theirs, up to limit. pool: pick limit at
    random from the owned ones among the artist's top pool (Radio's page: "pick 3 of each artist's top 5"),
    as Artist Matching does; None takes them in the sources' order (a pillar's own songs: its best known).
    """
    import library
    out = []
    top, _label = engine.blended_top_tracks(artist, limit=max(limit, pool or 0, engine.TRACKS_PER_ARTIST_POOL))
    if pool:
        owned = []
        for title, _sources in top[:pool]:
            key = library.find_track_key(artist, title)
            key = played.pick(key) if key and str(key) not in have else None
            if key and str(key) not in have and str(key) not in owned:
                owned.append(str(key))
        random.shuffle(owned)
        out = owned[:limit]
        if len(out) >= limit:
            return out
        top = top[pool:]
    for title, _sources in top:
        key = library.find_track_key(artist, title)
        key = played.pick(key) if key and str(key) not in have else None
        if key and str(key) not in have and str(key) not in out:
            out.append(str(key))
        if len(out) >= limit:
            return out
    a = engine.artist_key(artist)
    with library._lock:
        rows = [r for r in library._tracks if engine.artist_key(r.get("Artist") or "") == a]
    for r in sorted(rows, key=lambda r: -_plays(r)):
        key = str(r.get("Key"))
        if key not in have and key not in out and played.pick(key):
            out.append(key)
        if len(out) >= limit:
            break
    return out


def _minutes(keys):
    import library
    total = 0.0
    for k in keys:
        try:
            total += float((library.track_row(k) or {}).get("Duration") or 0)
        except (TypeError, ValueError):
            pass
    return total / 60.0


def find(lane_, report, minutes=TARGET_MINUTES, avoid=(), own=None):
    """
    The tracks for one round: (keys, the pillars used). avoid: keys already sent (Non-stop's rounds).
    own: a list that gets the pillars' own songs (the Moderator's yardstick).
    """
    pillars = list(lane_["pillars"])
    random.shuffle(pillars)
    if not pillars:
        return [], []
    have = {str(k) for k in avoid}
    played = engine.PlayedFilter("artists", report=report, filters=True)
    circle, lists, picks, seen_artists, off = [], {}, [], set(), []
    own = [] if own is None else own
    fits = fitter(lane_)
    try:
        while pillars and len(circle) < CIRCLE_MAX and (not picks or _minutes(picks) < minutes):
            engine.check_cancelled()
            joining = pillars[:CIRCLE_START] if not circle else pillars[:1]
            pillars = pillars[len(joining):]
            if circle:
                report("  " + t("Short of {minutes} minutes: {artist} joins ({count} of {most} pillars).",
                                minutes=minutes, artist=joining[0], count=len(circle) + 1, most=CIRCLE_MAX))
            for p in joining:
                found, _label = engine.blended_similar_artists(p, limit=30, report=report)
                lists[engine.artist_key(p)] = [a for a, _ in found]
            circle += joining
            agreed, _same = engine.inner_circle(circle, lambda m: lists[engine.artist_key(m)],
                                                min(AGREE, len(circle)), key=engine.artist_key)
            for p in joining:   # a couple of each pillar's own, at random from its best known five
                for key in _owned_top(p, have, played, 2, pool=PILLAR_SONGS):
                    have.add(key)
                    picks.append(key)
                    own.append(key)
            fits.learn([artist for artist, _why in agreed[len(circle):]])
            for artist, _why in agreed[len(circle):]:   # Radio's page: pick n of each artist's top m
                a = engine.artist_key(artist)
                if a in seen_artists:
                    continue
                seen_artists.add(a)
                if not fits(artist):
                    off.append(artist)
                    continue
                for key in _owned_top(artist, have, played, engine.TRACKS_PER_ARTIST_PICK,
                                      pool=max(engine.TRACKS_PER_ARTIST_POOL, engine.TRACKS_PER_ARTIST_PICK)):
                    have.add(key)
                    picks.append(key)
        if off:
            report("  " + tn("Left out {count} agreeing artist whose genres don't fit {station}: {names}.",
                             "Left out {count} agreeing artists whose genres don't fit {station}: {names}.", len(off),
                             station=lane_["name"], names=", ".join(off[:5]) + ("..." if len(off) > 5 else "")))
        # At least filters (7 Nov 2026): the round's share, the pillars' own songs kept
        picks = engine.apply_shares(picks, played, report, keep=own, artists=circle)
    finally:
        played.done()
    return picks, circle


def fitter(lane_):
    """
    fits(artist name): whether an agreeing artist belongs in this station (Ben, 7 Nov 2026). Its genres from
    the sources (Last.fm's tags, kept from the analysis or asked for once by learn()) are set against every
    top-level station's: it's left out when another station fits it more than twice as well (NEAR) as the one
    this round is for (for a half, the station it's a half of). No genres, or none any station shares: kept,
    as nothing says where it belongs. Your own Genre tags aren't used: "Rock/Pop" or "Dance/Electronic" put
    Grimes in Soundtrack and Burial in House. Without this only the Moderator, which needs AI, kept a round in
    the station: two pillars that both list a pop act brought it in. On Ben's library this kept all 159
    artists the analysis put in Electronic / Ambient and left out 366 of the 388 it put elsewhere.
    fits.learn(names) asks Last.fm, in parallel, about the ones not yet known.
    """
    tops = (analysis() or {}).get("lanes") or []
    centres = {x["id"]: _unit(x.get("centroid") or {}) for x in tops}
    m = re.match(r"\d+", str(lane_.get("id") or ""))
    here = m.group(0) if m else None
    cache = _meta(TAGS_KEY, {})
    asked = set()

    def fits(name):
        if here not in centres or len(centres) < 2:
            return True
        a = engine.artist_key(name)
        genres, _case = genres_for(a, {"genres": Counter()}, cache)
        if not genres:
            return True
        mine = _unit(genres)
        sims = {i: _cosine(mine, c) for i, c in centres.items()}
        best = max(sims, key=sims.get)
        return best == here or sims[best] <= 0 or sims[here] >= NEAR * sims[best]

    def learn(names):
        todo = [(engine.artist_key(n), n) for n in names
                if engine.artist_key(n) not in cache and engine.artist_key(n) not in asked]
        if not todo or here not in centres or not engine.LASTFM_KEY:
            return
        asked.update(a for a, _n in todo)
        from concurrent.futures import ThreadPoolExecutor

        def one(pair):
            try:
                data = _lastfm({"method": "artist.gettoptags", "artist": pair[1], "autocorrect": 1})
                return pair[0], [(x["name"].lower().strip(), int(x.get("count", 0)))
                                 for x in data.get("toptags", {}).get("tag", [])]
            except Exception:
                return pair[0], None
        with ThreadPoolExecutor(max_workers=4) as pool:
            found = [(a, tags) for a, tags in pool.map(one, todo) if tags is not None]
        if found:
            cache.update(found)
            kept = _meta(TAGS_KEY, {})
            kept.update(found)
            _set_meta(TAGS_KEY, kept)
    fits.learn = learn
    return fits


def _tracks(keys):
    """[(key, artist, title)] for the Moderator."""
    import library
    out = []
    for k in keys:
        row = library.track_row(k) or {}
        out.append((str(k), row.get("Artist") or "", row.get("Name") or ""))
    return out


def moderator_seed(lane_, circle):
    """What the Moderator judges a round against: the lane and the pillars in it this round."""
    return f"vibe: {lane_.get('auto') or lane_['name']} radio, in the sound of {', '.join(circle)}"   # its genres, not your name for it


def moderate(picks, own, seed, report):
    """
    Radio's Moderator (6 Nov 2026), its level from Radio's page or the More Options switch: the agreeing
    artists' tracks are checked against the lane, with the pillars' own songs as what fits. The pillars'
    songs stay. Nothing removed when it's off, or when the AI can't run (said once).
    """
    level = engine.AI_MODERATOR_BY.get("artists", "off")
    guests = [k for k in picks if k not in set(own)]
    if level in ("", "off") or not guests:
        return picks
    removed = engine.moderate(_tracks(guests), seed, report, level=level, reference=_tracks(own))
    return [k for k in picks if k not in removed] if removed else picks


def deep_cuts(keys, seed, report):
    """Radio's Deep Cuts: lesser-played artists from the genre most of this round shares, as the page sets."""
    try:
        import deepcuts
        genre = deepcuts.common_genre(keys, share=0.3)
    except Exception:
        genre = None
    cfg = engine.DEEP_CUTS.get("artists") or {}
    if cfg.get("mode", "off") == "off":
        return keys
    if not genre:
        report("  " + t("Deep Cuts: none this round, as no one genre is shared by enough of its tracks."))
        return keys
    return engine.add_deep_cuts(keys, None, report, group="artists", genres=[genre], moderator_seed=seed)


def build(lane_id, report=print):
    """Radio: one round for the lane, a pillar song first, the rest spread. Non-stop carries on from pillars."""
    lane_ = lane(lane_id)
    if lane_ is None:
        report(t("Problem: that Radio station has gone. Re-analyse under Radio's arrow or on its page to make the "
                 "stations again."))
        return
    appending = engine.NONSTOP_APPEND
    if not appending:
        report(t("Radio: {name}.", name=lane_["name"]))
        join_new_artists(report)
        lane_ = lane(lane_id) or lane_
    session_id = engine.session_start("radio", {"Artist": "", "Name": lane_["name"]})
    avoid = set()
    if appending and engine.OUTPUT_OVERRIDE:
        with engine._nonstop_lock:
            for entry in engine.NONSTOP_ZONES.values():
                if entry.get("radio_lane") == lane_id:
                    avoid |= set(entry.get("keys") or ())
    own = []
    picks, circle = find(lane_, report, avoid=avoid, own=own)
    report("  " + t("Pillars this round: {names}.", names=", ".join(circle)))
    if not picks:
        report(t("Radio: nothing found for {name} this time. The sources may not be answering; try again in a "
                 "minute.", name=lane_["name"]))
        engine.session_finish(session_id, 0, sources="none", report=report)
        return
    seed = moderator_seed(lane_, circle)
    picks = moderate(picks, own, seed, report)
    first, rest = picks[0], picks[1:]
    random.shuffle(rest)
    keys = engine.spread_artists([first] + rest, keep=first)
    keys = deep_cuts(keys, seed, report)
    import library
    artists = {engine.artist_key((library.track_row(k) or {}).get("Artist") or "") for k in keys}
    report("  " + t("{tracks}, about {minutes} minutes, from {artists} artists.",
                    tracks=tn("{count} track", "{count} tracks", len(keys)), minutes=round(_minutes(keys)),
                    artists=len(artists)))
    engine.send_to_jriver(keys, typed=True, report=report, append=appending)
    zone = engine.LAST_OUTPUT_ID
    if zone is not None:
        with engine._nonstop_lock:
            entry = engine.NONSTOP_ZONES.get(zone)
            if entry is not None:
                entry.update(radio_lane=lane_id, origin="radio", kind="radio")
    engine.session_finish(session_id, len(keys), report=report)
    engine.SAVE_NAME = t("{name} Radio", name=lane_["name"])
