"""
24bit7 - Test My Sources: the engine (no screens; those come in 5b).

Asks every similarity source the same question a real build asks ("what's similar to this
seed?") for a fixed, curated set of seeds across 17 genres (source_test_seeds.json), and
counts how many of the answers are in your library. The genre is only the label on the test
seed, used to group results; nothing is judged by genre tags, which vary too much to trust.

Measured per seed and source, for Similar Artists and Similar Tracks separately: answered,
results returned, in your library (the seed itself never counts), found by no other source,
and time taken. Scored per section:

  per genre    a source's useful matches (in your library) against the best source for that genre
  Performance  the average of those across genres, as a percentage
  Best At      the three genres where it does best against the others; Worst At, the three worst
  thin genres  where even the best source found fewer than THIN useful matches: flagged, and left
               out of Best At and Worst At (they say more about the library than the source)

Runs in the background, pausing between seeds while a build is running. The console says when
it starts and when it's ready, and repeats "ready" at the start of each build until the report
is opened. Results live in 24bit7.db (the latest run); source_test_sample.json, shipped with
24bit7, stands in until a user runs their own. It holds scores only, nothing about anyone's tracks.

From PowerShell:
    py source_test.py              full test (68 seeds), then prints the results
    py source_test.py --quick      quick test (34 seeds: one famous and one hidden per genre)
    py source_test.py --ai         include the AI (costs a few pence)
    py source_test.py --show       print the latest results again
    py source_test.py --make-sample   write your latest run as source_test_sample.json (for releases)
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

import engine



def _data_file(name):
    """Beside 24bit7 (running from the folder), else in the packaged app's bundled files."""
    for folder in (engine.APP_DIR, getattr(sys, "_MEIPASS", None)):
        if folder and os.path.exists(os.path.join(folder, name)):
            return os.path.join(folder, name)
    return os.path.join(engine.APP_DIR, name)


SEEDS_NAME, SAMPLE_NAME = "source_test_seeds.json", "source_test_sample.json"
THIN = 3                    # a genre where the best source finds fewer useful matches than this is thin
ARTIST_FETCH = 30           # similar artists asked of each source per seed
TRACK_FETCH = 50            # similar tracks asked of each source per seed
ARTIST_DEPTH = 20           # every source is scored on the same depth: its top 20 artists per seed
TRACK_DEPTH = 30            # ... and its top 30 tracks, about what a build reads
SECONDS_PER_SEED = 10       # with the sources asked at once (the first real runs took about 16 a seed in turn)
BUSY_WINDOW = 15 * 60       # a build counts as running for at most this long (a cancelled one can't hold it)
SECTIONS = ("artists", "tracks")
READY_LINE = ("Source test ready: open Full Results under Settings > Sources to see how each source "
              "does with your library.")

_thread = None
_lock = threading.Lock()
_stop = threading.Event()                  # set by cancel(): the running test stops before the next seed
progress_state = {"n": 0, "of": 0}       # for the screens: which seed a running test is on

SAMPLE_NOTICE = ("Sample results from a {tracks:,}-track library. Source performance varies between "
                 "libraries, so run the test on yours for figures that fit your collection.")
PERFORMANCE_HELP = ("How much of your library a source reaches from the test's seeds, against the best "
                    "source for each genre: 100% means it matched the best in every genre. Sources that "
                    "favour well-known artists reach more of a large library.")


def sample_notice(result):
    return SAMPLE_NOTICE.format(tracks=int((result or {}).get("library_tracks") or 0))


# --- seeds ----------------------------------------------------------------------------

def load_seeds(quick=False):
    """The test seeds, in file order. Quick: the first famous and first hidden seed of each genre."""
    with open(_data_file(SEEDS_NAME), encoding="utf-8") as f:
        seeds = json.load(f)["seeds"]
    if not quick:
        return seeds
    out, taken = [], set()
    for s in seeds:
        if (s["genre"], s["tier"]) not in taken:
            taken.add((s["genre"], s["tier"]))
            out.append(s)
    return out


def genres(seeds):
    out = []
    for s in seeds:
        if s["genre"] not in out:
            out.append(s["genre"])
    return out


# --- which sources can be asked ------------------------------------------------------------

def sources_to_test(include_ai=False):
    """{section: [(code, name)]} for every source that can be asked now."""
    def usable(code):
        if code == "ai":
            return include_ai and engine.ai_enabled()
        return engine.source_has_key(code)
    artists = [(c, engine.PROVIDERS[c][0]) for c in engine.PROVIDERS if usable(c)]
    tracks = [(c, engine.TRACK_PROVIDERS[c][0]) for c in engine.TRACK_PROVIDERS if usable(c)]
    return {"artists": artists, "tracks": tracks}


def _ask_artists(code, artist, track):
    fn = engine.PROVIDERS[code][1]
    if code == "youtube":
        return engine.youtube_similar(artist, limit=ARTIST_FETCH, track=track)
    return fn(artist, limit=ARTIST_FETCH)


def _ask_tracks(code, artist, track):
    return engine.TRACK_PROVIDERS[code][1](artist, track)


def ask(section, code, artist, track):
    """
    One source's answer for one seed, as a real build asks: the full credit first, then the lead
    artist when a joint credit finds nothing (not for the AI or YouTube, as in a build).
    Returns (answer list, seconds). Never raises.
    """
    started = time.time()
    tries = [artist]
    lead = engine.primary_artist(artist)
    if lead and code not in ("ai", "youtube"):
        tries.append(lead)
    answer = []
    for who in tries:
        try:
            answer = (_ask_artists if section == "artists" else _ask_tracks)(code, who, track) or []
        except Exception as e:
            engine.debug(f"Source test: {code} failed for {who} - {track} ({e})")
            answer = []
        if answer:
            break
    if section == "tracks":
        answer = [tuple(p) for p in answer if isinstance(p, (list, tuple)) and len(p) == 2 and p[0] and p[1]]
        if answer and code != "youtube":   # the same cache a build reads, so the test warms up builds
            label = (f"{engine.TRACK_PROVIDERS[code][0]} ({engine.LISTENBRAINZ_TRACK_ALGORITHM_SETTING})"
                     if code == "listenbrainz" else engine.TRACK_PROVIDERS[code][0])
            try:
                engine.cache_put(label, "similar_tracks", f"{engine.artist_key(artist)}|{engine.clean_name(track)}",
                                 [list(p) for p in answer])
            except Exception as e:
                engine.debug(f"Source test: couldn't cache {code}'s answer ({e})")
    else:
        answer = [a for a in answer if isinstance(a, str) and a.strip()]
    return answer, time.time() - started


# --- what's in the library -----------------------------------------------------------------

def owned_artist(name):
    """
    The test's strict check: the library has this artist under the same name, or under the
    credit's lead artist. Stricter than the builds' check, which also accepts band credits, so
    a short library name can't make a long list of famous names look owned.
    """
    import library
    library.ensure_loaded()
    known = library._artists
    lead = engine.primary_artist(name)
    return library.norm(name) in known or bool(lead and library.norm(lead) in known)


def minutes_for(n):
    """The time estimate for n seeds, in whole minutes."""
    return max(1, round(n * SECONDS_PER_SEED / 60))


def library_hits(section, answer, seed):
    """The answer's items that are in the library, as comparable keys. The seed never counts."""
    import library   # here rather than at the top: library imports engine
    seed_artists = {engine.artist_key(seed["artist"])}
    lead = engine.primary_artist(seed["artist"])
    if lead:
        seed_artists.add(engine.artist_key(lead))
    hits = []
    if section == "artists":
        for name in answer:
            k = engine.artist_key(name)
            if k not in seed_artists and k not in hits and owned_artist(name):
                hits.append(k)
        return hits
    seed_key = library.find_track_key(seed["artist"], seed["track"])
    for a, t in answer:
        key = library.find_track_key(a, t)
        if key and str(key) != str(seed_key) and str(key) not in hits:
            hits.append(str(key))
    return hits


# --- running --------------------------------------------------------------------------------

def build_running():
    """True while a playlist build is under way (started recently and not yet finished)."""
    now = time.time()
    return any(now - started < BUSY_WINDOW for started in list(engine._SESSION_STARTED.values()))


def _ask_all(section, testing, seed, parallel):
    """Every source's answer for one seed, asked at once (or in turn): {code: (answer, seconds)}."""
    codes = [c for c, _ in testing[section]]
    if not parallel or len(codes) < 2:
        return {c: ask(section, c, seed["artist"], seed["track"]) for c in codes}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(codes)) as pool:
        futures = {c: pool.submit(ask, section, c, seed["artist"], seed["track"]) for c in codes}
        return {c: f.result() for c, f in futures.items()}


def run(quick=False, include_ai=False, progress=None, wait_for_builds=True, stop=None, parallel=True):
    """
    The whole test. progress(line) gets one line per seed (None: quiet). Returns the result dict,
    already saved. stop(): a callable that, when True, ends the run early (nothing is saved).
    parallel: each seed's sources are asked at once (each service keeps to its own limits).
    """
    import library
    library.ensure_loaded()
    seeds = load_seeds(quick)
    testing = sources_to_test(include_ai)
    started = time.time()
    timing = {"asking": 0.0, "matching": 0.0, "waiting": 0.0}
    rows = []   # one per seed, section and source: counts only, no names
    progress_state.update(n=0, of=len(seeds))
    for n, seed in enumerate(seeds, 1):
        while wait_for_builds and build_running():
            if stop and stop():
                return None
            time.sleep(2)
            timing["waiting"] += 2
        if stop and stop():
            return None
        progress_state["n"] = n
        if progress:
            progress(f"  Testing {seed['genre']}: {seed['artist']} - {seed['track']} ({n} of {len(seeds)})")
        for section in SECTIONS:
            found = {}
            asked_at = time.time()
            answers = _ask_all(section, testing, seed, parallel)
            timing["asking"] += time.time() - asked_at
            for code, name in testing[section]:
                answer, secs = answers[code]
                full = len(answer)
                answer = answer[:ARTIST_DEPTH if section == "artists" else TRACK_DEPTH]   # the same depth for all
                matched = time.time()
                hits = library_hits(section, answer, seed)
                timing["matching"] += time.time() - matched
                found[code] = set(hits)
                rows.append({"seed": n - 1, "genre": seed["genre"], "section": section, "source": code,
                             "name": name, "answered": bool(answer), "returned": len(answer),
                             "returned_all": full, "hits": len(hits), "seconds": round(secs, 2)})
            for row in rows[len(rows) - len(testing[section]):]:
                others = set().union(*[v for c, v in found.items() if c != row["source"]])
                row["unique"] = len(found[row["source"]] - others)
    result = {
        "version": 1, "finished": datetime.now().strftime("%Y-%m-%d %H:%M"), "mode": "quick" if quick else "full",
        "seconds": round(time.time() - started), "seeds": [{"genre": s["genre"], "artist": s["artist"],
                                                             "track": s["track"], "tier": s["tier"]} for s in seeds],
        "genres": genres(seeds), "library_tracks": len(getattr(library, "_tracks", []) or []),
        "sources": {sec: [[c, nm] for c, nm in testing[sec]] for sec in SECTIONS},
        "rows": rows, "depth": {"artists": ARTIST_DEPTH, "tracks": TRACK_DEPTH},
        "timing": {k: round(v) for k, v in timing.items()},
    }
    result["scores"] = score(result)
    save(result)
    return result


def start_background(quick=False, include_ai=False):
    """Starts a run in the background. False if one is already running."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop.clear()
        n = len(load_seeds(quick))
        engine.print(f"Source test started in the background ({n} seeds, about {minutes_for(n)} minutes). "
                     f"You can keep using 24bit7.")

        def work():
            try:
                if run(quick=quick, include_ai=include_ai, stop=_stop.is_set) is not None:
                    engine.print(READY_LINE)
                else:
                    engine.print("Source test cancelled. Nothing was saved, so the last results still show.")
            except Exception as e:
                engine.print(f"Problem: the source test stopped ({e}).")
        _thread = threading.Thread(target=work, daemon=True, name="source-test")
        _thread.start()
        return True


def is_running():
    return _thread is not None and _thread.is_alive()


def cancel():
    """Stops a running test before its next seed. Nothing half-finished is saved."""
    _stop.set()


# --- scoring --------------------------------------------------------------------------------

def score(result):
    """{section: {"genres": {genre: {"best": n, "thin": bool, "by": {code: {...}}}}, "sources": {code: {...}}}}"""
    out = {}
    for section in SECTIONS:
        codes = [c for c, _ in result["sources"][section]]
        per_genre = {}
        for g in result["genres"]:
            by = {}
            for c in codes:
                rows = [r for r in result["rows"] if r["section"] == section and r["source"] == c and r["genre"] == g]
                if not rows:
                    continue
                by[c] = {"useful": sum(r["hits"] for r in rows), "returned": sum(r["returned"] for r in rows),
                         "returned_all": sum(r.get("returned_all", r["returned"]) for r in rows),
                         "answered": sum(r["answered"] for r in rows), "asked": len(rows),
                         "unique": sum(r.get("unique", 0) for r in rows),
                         "seconds": round(sum(r["seconds"] for r in rows), 1)}
            best = max((v["useful"] for v in by.values()), default=0)
            for v in by.values():
                v["percent"] = round(100 * v["useful"] / best) if best else 0
            per_genre[g] = {"best": best, "thin": best < THIN, "by": by}
        sources = {}
        for c in codes:
            counted = [(g, per_genre[g]["by"][c]) for g in result["genres"]
                       if c in per_genre[g]["by"] and not per_genre[g]["thin"]]
            if not counted:   # every genre thin: score on whatever there is
                counted = [(g, per_genre[g]["by"][c]) for g in result["genres"]
                           if c in per_genre[g]["by"] and per_genre[g]["best"]]
            ranked = sorted(counted, key=lambda gv: (-gv[1]["percent"], -gv[1]["useful"]))
            best_at = [g for g, _ in ranked[:3]]
            worst = [g for g, _ in reversed(ranked) if g not in best_at][:3]   # never the same genre in both
            sources[c] = {
                "performance": round(sum(v["percent"] for _, v in counted) / len(counted)) if counted else 0,
                "best_at": best_at,
                "worst_at": worst,
            }
        out[section] = {"genres": per_genre, "sources": sources}
    return out


# --- storing, and the sample ------------------------------------------------------------------

def _table():
    con = engine.db()
    con.execute("""CREATE TABLE IF NOT EXISTS source_tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, finished_at TEXT, mode TEXT, payload TEXT, seen INTEGER DEFAULT 0)""")
    return con


def save(result):
    con = _table()
    con.execute("INSERT INTO source_tests (finished_at, mode, payload, seen) VALUES (?,?,?,0)",
                (result["finished"], result["mode"], json.dumps(result)))
    con.execute("DELETE FROM source_tests WHERE id NOT IN (SELECT id FROM source_tests ORDER BY id DESC LIMIT 1)")
    con.commit()


def latest_own():
    """The user's own latest run, or None."""
    row = _table().execute("SELECT payload FROM source_tests ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(row[0]) if row else None


def load_results():
    """(result, is_sample): the user's own latest run, else the shipped sample, else (None, False)."""
    own = latest_own()
    if own:
        return own, False
    try:
        with open(_data_file(SAMPLE_NAME), encoding="utf-8") as f:
            return json.load(f), True
    except (OSError, ValueError):
        return None, False


def unseen():
    """True when the user's latest run hasn't been opened yet."""
    row = _table().execute("SELECT seen FROM source_tests ORDER BY id DESC LIMIT 1").fetchone()
    return bool(row) and not row[0]


def mark_seen():
    con = _table()
    con.execute("UPDATE source_tests SET seen=1")
    con.commit()


def remind_if_ready():
    """At the start of each build: the ready line again, until the report has been opened."""
    try:
        if not is_running() and unseen():
            engine.print(READY_LINE)
    except Exception:
        pass


def cell_detail(result, section, genre, code):
    """The hover text for one cell of Full Results."""
    v = result["scores"][section]["genres"][genre]["by"].get(code)
    if not v:
        return "Not tested."
    depth = (result.get("depth") or {}).get(section)
    returned = f"{v['returned']}" + (f" (top {depth} of {v['returned_all']} each seed)"
                                       if depth and v.get("returned_all", 0) > v["returned"] else "")
    return (f"Seeds answered: {v['answered']} of {v['asked']}\n"
            f"Results used: {returned}\n"
            f"In your library: {v['useful']}\n"
            f"Found by no other source: {v['unique']}\n"
            f"Time: {v['seconds']} s")


def export_csv(result, path):
    """Every genre and source, for both sections, as a CSV file."""
    import csv
    names = {c: n for sec in SECTIONS for c, n in result["sources"][sec]}
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Section", "Genre", "Source", "Performance %", "In your library", "Results used",
                    "Results returned", "Seeds answered", "Seeds asked", "Found by no other source", "Seconds",
                    "You own little here"])
        for section in SECTIONS:
            title = "Similar Artists" if section == "artists" else "Similar Tracks"
            for g in result["genres"]:
                gs = result["scores"][section]["genres"][g]
                for c, v in gs["by"].items():
                    w.writerow([title, g, names.get(c, c), v["percent"], v["useful"], v["returned"],
                                v.get("returned_all", v["returned"]), v["answered"], v["asked"], v["unique"],
                                v["seconds"], "yes" if gs["thin"] else ""])
    return path


def make_sample():
    """Writes the latest run as the shipped sample: scores and counts only. Returns the path."""
    own = latest_own()
    if not own:
        raise SystemExit("No test has been run yet: run `py source_test.py` first.")
    sample = dict(own, sample=True)
    path = os.path.join(engine.APP_DIR, SAMPLE_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=1)
    return path


# --- printing (the command line; Settings gets its own view in 5b) ------------------------------

def report_lines(result, is_sample=False):
    names = {c: n for sec in SECTIONS for c, n in result["sources"][sec]}
    lines = []
    if is_sample:
        lines.append(sample_notice(result))
    else:
        lines.append(f"Your results, tested {result['finished']} ({result['mode']}, {len(result['seeds'])} seeds, "
                     f"{result['seconds'] // 60} min {result['seconds'] % 60} s).")
        t = result.get("timing")
        if t:
            lines.append(f"Time: asking the sources {t['asking'] // 60} min {t['asking'] % 60} s, matching your "
                         f"library {t['matching'] // 60} min {t['matching'] % 60} s"
                         + (f", waiting for builds {t['waiting'] // 60} min" if t.get("waiting") else "") + ".")
    for section in SECTIONS:
        sc = result["scores"][section]
        lines += ["", "Similar Artists" if section == "artists" else "Similar Tracks"]
        lines.append(f"  {'Source':<14}{'Performance':<13}{'Best At':<34}Worst At")
        for c, s in sorted(sc["sources"].items(), key=lambda cs: -cs[1]["performance"]):
            lines.append(f"  {names.get(c, c):<14}{str(s['performance']) + '%':<13}"
                         f"{', '.join(s['best_at']):<34}{', '.join(s['worst_at'])}")
        codes = [c for c, _ in result["sources"][section]]
        lines.append("")
        lines.append(f"  {'Genre':<12}" + "".join(f"{names.get(c, c)[:12]:<14}" for c in codes))
        for g in result["genres"]:
            gs = sc["genres"][g]
            cells = []
            for c in codes:
                v = gs["by"].get(c)
                cells.append(f"{(str(v['percent']) + '% (' + str(v['useful']) + ')') if v else '-':<14}")
            lines.append(f"  {g:<12}" + "".join(cells) + ("  you own little here" if gs["thin"] else ""))
    return lines


def main(argv):
    if "--make-sample" in argv:
        print(f"Wrote {make_sample()}")
        return
    if "--show" not in argv:
        quick, ai = "--quick" in argv, "--ai" in argv
        n = len(load_seeds(quick))
        print(f"Source test: {n} seeds{', with the AI' if ai else ''}. This takes about {minutes_for(n)} minutes.")
        engine.OUTPUT_HOOK = None
        if run(quick=quick, include_ai=ai, progress=print, wait_for_builds=False) is None:
            return
    result, is_sample = load_results()
    if not result:
        print("No results yet: run `py source_test.py` first.")
        return
    for line in report_lines(result, is_sample):
        print(line)
    if not is_sample:
        mark_seen()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    main(sys.argv[1:])
