"""
24bit7 - stacking artists on the Search tab (Ben, 23 Nov 2026).

Ben was making playlists for Jo's phone, a few songs from each of a list of artists, and didn't want ten from
an artist with four worth having. On the Search tab the Artist box lists the library's artists as you type,
each with Add; the artists added are the stack. Go plays up to the chosen number (five to start) of each one's
top tracks that you own, shuffled with the artists spread, to Output like any build, so Save Playlist keeps it.
With Select From Hits on (down, to start) an artist's songs come at random from their hits, so a one-hit wonder
gives the hit; both also gives up to half as many again for an artist with plenty (25 Nov 2026; Most Played, a
tick, until then). The number and the choice are remembered; the stack clears after Go.

Each artist walks down its pool until it has enough you own: the hits, shuffled, while Select From Hits is on,
else the sources' top songs to POOL deep. The Main Filter applies, as for Artist's Top Tracks; Skip
Played doesn't (it's a list you chose). Nothing here plays on by itself: Non-stop is left out, as for an album.
"""

import json
import random

import engine
from i18n import t, tn

CHOICE_KEY = "search_stack"   # {"count": n, "most_played": "off", "down" or "both" (1.43's "1"/"0" read too)}
COUNTS = list(range(1, 21))
DEFAULT_COUNT = 5
POOL = 30     # how far down the sources' list an artist is read without Most Played
MODE = "stack"


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


def choices():
    """{"count": tracks per artist, "most_played": bool}, as last chosen."""
    saved = _meta(CHOICE_KEY, {})
    try:
        count = int(saved.get("count", DEFAULT_COUNT))
    except (TypeError, ValueError):
        count = DEFAULT_COUNT
    count = count if count in COUNTS else DEFAULT_COUNT
    return {"count": count, "most_played": engine.hits_mode(saved.get("most_played", "down"))}


def set_choice(key, value):
    saved = dict(_meta(CHOICE_KEY, {}))
    saved[key] = value
    _set_meta(CHOICE_KEY, saved)


def names_text(artists):
    """'Stevie Nicks, Fleet Foxes and Kate Bush', or 'Stevie Nicks, Fleet Foxes and 4 more'."""
    if len(artists) <= 3:
        return artists[0] if len(artists) == 1 else t("{names} and {last}", names=", ".join(artists[:-1]),
                                                        last=artists[-1])
    return t("{names} and {count} more", names=", ".join(artists[:2]), count=len(artists) - 2)


def _artist_tracks(artist, count, most_played, played, session_id, report):
    """Up to count keys you own for one artist, most played first; each one looked up logged to Discover."""
    found, _label = engine.blended_top_tracks(artist, limit=POOL)
    if not found:
        report("  " + t("Problem: no source returned top tracks for {artist}.", artist=artist))
        return []
    names = [title for title, _by in found]
    names, count, _used = engine.select_from_hits(artist, names, count, report, indent="  ",
                                                  mode=engine.hits_mode(most_played))
    by = dict(found)
    keys = []
    for title in names:
        if len(keys) >= count:
            break
        key = engine.find_jriver_key_by_track(artist, title)
        use = played.pick(key) if key else None
        if use and use not in keys:
            keys.append(use)
        engine.session_log(session_id, artist, title, by.get(title) or [], found=bool(key))
    return keys


def build(artists, count, most_played, report=print):
    """Go: the stack's tracks to Output, shuffled with the artists spread. Returns how many went."""
    artists = [a for a in artists if a]
    if not artists:
        return 0
    label = names_text(artists)
    mode = engine.hits_mode(most_played)
    report(t("Search: {names}, up to {count} each, from their hits.", names=label, count=count) if mode == "down" else
           t("Search: {names}, up to {count} each from their hits, more for artists with plenty.", names=label,
             count=count) if mode == "both" else
           t("Search: {names}, up to {count} each.", names=label, count=count))
    session_id = engine.session_start(MODE, {"Artist": "", "Name": label})
    # the Main Filter and Hidden Tracks as Artist's Top Tracks has them; never Skip Played (a list you chose)
    played = engine.PlayedFilter("top", report=report, setting=(False, 1), filters=True)
    keys = []
    try:
        for artist in artists:
            engine.check_cancelled()
            got = _artist_tracks(artist, count, most_played, played, session_id, report)
            report("  " + tn("{artist}: {count} track.", "{artist}: {count} tracks.", len(got), artist=artist))
            keys += [k for k in got if k not in keys]
    finally:
        played.done()
    if not keys:
        report(t("Problem: none of their top tracks are {where}.", where=engine.where_found(True)))
        engine.session_finish(session_id, 0, report=report)
        return 0
    random.shuffle(keys)
    keys = engine.spread_artists(keys)
    engine.send_to_jriver(keys, typed=True, report=report)
    if engine.LAST_OUTPUT_ID is not None:
        engine.nonstop_forget(engine.LAST_OUTPUT_ID)   # a list you chose: nothing plays on by itself
    engine.SAVE_NAME = label
    engine.session_finish(session_id, len(keys), report=report)
    return len(keys)
