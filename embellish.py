"""
24bit7 - the Play tab's JRiver Playlists tab (Ben, 6 Nov 2026).

Play plays a JRiver playlist or smartlist, shuffled or in its own order. Play & Embellish
grows it first: Consensus with the playlist's own artists as the circle, then the top
tracks you own by each artist the circle agrees on, woven in with yours.

  Add Half      one new track for every two on the playlist
  Double It     as many new tracks as the playlist has
  Build It Out  every agreeing artist's top tracks you own, until none are left

The circle is taken ten of the playlist's artists at a time, picked at random (a big
playlist is sampled, as Playing Now is). Add Half and Double It stop as soon as they
have enough; Build It Out says what each stage added, and Cancel keeps what's found so
far: the lot goes in when it finishes or is stopped, so Ordered stays in your order.

The playlist's first track plays first. Ordered keeps your order with the new tracks
spread evenly between; Shuffled shuffles the lot, with the artists spread.
"""

import json
import random

import engine
from i18n import N_, t, tn

AMOUNTS = ("half", "double", "out")
AMOUNT_NAMES = {"half": N_("Add Half"), "double": N_("Double It"), "out": N_("Build It Out")}
AMOUNT_NOTES = {"half": N_("One new track for every two on the playlist."),
                "double": N_("As many new tracks as the playlist has."),
                "out": N_("Every agreeing artist's top tracks you own, ten artists at a time. Cancel keeps what's in.")}
ORDERS = ("shuffled", "ordered")
ORDER_NAMES = {"shuffled": N_("Play Shuffled"), "ordered": N_("Play Ordered")}
STAGE = 10          # playlist artists added to the circle per stage
AGREE = 2           # an artist on this many of the circle's lists is agreed on
BIG = 30            # Build It Out over more artists than this says up front it may take a while
RECENT = 5          # the most recent shown at the top of the list
RECENT_KEY = "jriver_playlists_recent"
CHOICE_KEY = "jriver_playlists_choices"


# --- what's remembered: the recent five, and the two arrows' last choices ---------------------------

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


def recent():
    """[{"id", "name", "how", "when"}] most recent first: what 24bit7 played or embellished (JRiver keeps no dates)."""
    items = _meta(RECENT_KEY, [])
    return [x for x in items if isinstance(x, dict) and x.get("id")][:RECENT]


def note_recent(playlist, how):
    """Puts a playlist at the top of the recent five. how: "played" or "embellished"."""
    from datetime import datetime
    pid = str(playlist.get("ID"))
    items = [x for x in recent() if str(x.get("id")) != pid]
    items.insert(0, {"id": pid, "name": playlist.get("Name") or "", "how": how,
                     "when": datetime.now().strftime("%Y-%m-%d %H:%M")})
    _set_meta(RECENT_KEY, items[:RECENT])


def choices():
    """{"order": "shuffled" or "ordered", "amount": "half", "double" or "out"}: the arrows' last choices."""
    saved = _meta(CHOICE_KEY, {})
    order = saved.get("order") if saved.get("order") in ORDERS else "shuffled"
    amount = saved.get("amount") if saved.get("amount") in AMOUNTS else "half"
    return {"order": order, "amount": amount}


def set_choice(key, value):
    saved = choices()
    saved[key] = value
    _set_meta(CHOICE_KEY, saved)


# --- the build ------------------------------------------------------------------------------------

def want_for(amount, count):
    """How many new tracks an amount asks for, on a playlist of count tracks. None: as many as there are."""
    if amount == "out":
        return None
    if amount == "double":
        return count
    return max(1, count // 2)


def weave(keys, new, ordered):
    """
    The playlist with the new tracks in, its first track first. Ordered: your order kept, the new
    tracks spread evenly between. Shuffled: the rest and the new shuffled together, artists spread.
    """
    keys, new = [str(k) for k in keys], [str(k) for k in new]
    if not keys:
        return new
    first, rest = keys[0], keys[1:]
    if not ordered:
        lot = rest + new
        random.shuffle(lot)
        return engine.spread_artists([first] + lot, keep=first)
    out, i, j, r, m = [first], 0, 0, len(rest), len(new)
    while i < r or j < m:
        # a new track goes in whenever the new ones have fallen behind their share of the way through
        if j < m and (i >= r or (j + 1) * (r + 1) <= (i + 1) * (m + 1)):
            out.append(new[j])
            j += 1
        else:
            out.append(rest[i])
            i += 1
    return out


def _artists(keys):
    """The playlist's artists: {artist key: name as tagged}, in order of first appearance."""
    import library
    out = {}
    for k in keys:
        row = library.track_row(k) or {}
        name = row.get("Artist") or ""
        a = engine.artist_key(name)
        if a and a not in out:
            out[a] = name
    return out


def find(keys, name, amount, report):
    """
    New tracks for the playlist: (new keys, what happened). Returns None when there's nothing for the
    circle to agree on (one artist), having said so.
    """
    import library
    library.ensure_loaded()
    on_list = _artists(keys)
    if len(on_list) < 2:
        only = next(iter(on_list.values()), "")
        report(t("Embellish: every track on {name} is by {artist}, so there's nothing for the curation rules to "
                 "agree on. Similar Artists from one of its tracks would grow it.", name=name, artist=only))
        return None
    want = want_for(amount, len(keys))
    if amount == "out" and len(on_list) > BIG:
        report("  " + t("Build It Out: {name} has {tracks} by {artists} artists. That can mean several hundred tracks "
                        "and a few minutes; Cancel keeps whatever is in.", name=name,
                        tracks=tn("{count} track", "{count} tracks", len(keys)), artists=len(on_list)))
    have = {str(k) for k in keys}
    played = engine.PlayedFilter("artists", report=report, filters=True)
    cap = None if amount == "out" else engine.TRACKS_PER_ARTIST_PICK
    order = list(on_list.values())
    random.shuffle(order)   # a big playlist is sampled, ten artists a stage
    lists, circle, new = {}, [], []
    agreed_all, already, tried = set(), set(), set()
    stage = 0
    try:
        while order and (want is None or len(new) < want):
            engine.check_cancelled()
            stage += 1
            members, order = order[:STAGE], order[STAGE:]
            for m in members:
                found, _label = engine.blended_similar_artists(m, limit=30, report=report)
                lists[engine.artist_key(m)] = [a for a, _ in found]
            circle += members
            agreed, _same = engine.inner_circle(circle, lambda m: lists[engine.artist_key(m)], AGREE,
                                                key=engine.artist_key)
            picks = {}
            for artist, _why in agreed[len(circle):]:
                a = engine.artist_key(artist)
                agreed_all.add(a)
                if a in on_list:
                    already.add(a)
                    continue
                if a in tried:
                    continue
                tried.add(a)
                engine.check_cancelled()
                top, _label = engine.blended_top_tracks(artist, limit=engine.TRACKS_PER_ARTIST_POOL)
                owned = []
                for title, _sources in top:
                    key = library.find_track_key(artist, title)
                    key = played.pick(key) if key and str(key) not in have else None
                    if key and str(key) not in have and str(key) not in owned:
                        owned.append(str(key))
                picks[artist] = owned[:cap] if cap else owned
            before = len(new)
            while any(picks.values()) and (want is None or len(new) < want):
                for artist in list(picks):   # one each in turn, so the new tracks spread across the artists
                    if picks[artist] and (want is None or len(new) < want):
                        key = picks[artist].pop(0)
                        if key not in have:
                            have.add(key)
                            new.append(key)
            if amount == "out":
                report("  " + t("Stage {stage}: {artists} artists, {tracks} added.", stage=stage, artists=len(members),
                                tracks=tn("{count} track", "{count} tracks", len(new) - before)))
        # At least filters (7 Nov 2026): their share of what's added; your own playlist is yours
        new = engine.apply_shares(new, played, report, artists=list(on_list.values()))
    except engine.BuildCancelled:
        if amount != "out" or not new:
            raise
        engine.CANCEL_REQUESTED.clear()   # Build It Out: Cancel keeps what's found, and it plays
        report("  " + t("Stopped at stage {stage}: keeping the {tracks} found so far.", stage=stage,
                        tracks=tn("{count} track", "{count} tracks", len(new))))
    finally:
        played.done()
    return new, {"agreed": len(agreed_all), "already": len(already), "want": want, "artists": len(on_list)}


def say_result(name, new, stats, report):
    """The honest line: what was added, or why not as many as asked."""
    added, want, agreed, already = len(new), stats["want"], stats["agreed"], stats["already"]
    if not added:
        if not agreed:
            report(t("Embellish: the artists on {name} don't agree on anyone else, so there's nothing to add.",
                     name=name))
        elif already == agreed:
            report(t("Embellish: nothing to add. All {count} artists the curation rules agree on are already on "
                     "{name}, and their top tracks you own are in it.", count=agreed, name=name))
        else:
            report(t("Embellish: nothing to add. {already} of the {count} agreeing artists are already on {name}, "
                     "and the rest have no top tracks you own.", already=already, count=agreed, name=name))
        return
    if want is not None and added < want:
        report("  " + t("Embellish: added {added}, fewer than the {want} asked for. {already} of the agreeing artists "
                        "are already on {name}, and the rest have no more top tracks you own.",
                        added=tn("{count} track", "{count} tracks", added), want=want, already=already, name=name))


def _read(playlist, report):
    import saved_playlists
    name = playlist.get("Name") or t("playlist")
    try:
        keys = saved_playlists.playlist_keys(str(playlist.get("ID")))
    except Exception as e:
        report(t("Problem: couldn't read {name} from JRiver ({e}).", name=name, e=e))
        return name, None
    if not keys:
        report(t("Problem: {name} is empty in JRiver, so there's nothing to play.", name=name))
        return name, None
    return name, keys


def play(playlist, order, report):
    """Play: the playlist as it is, shuffled or in order, through the usual output (Review, Top-Up, YouTube...)."""
    name, keys = _read(playlist, report)
    if keys is None:
        return
    ordered = order == "ordered"
    report(t("Play: {name}, {tracks}, {how}.", name=name, tracks=tn("{count} track", "{count} tracks", len(keys)),
             how=t("in order") if ordered else t("shuffled")))
    if not ordered:
        keys = list(keys)
        random.shuffle(keys)
    session_id = engine.session_start("jriver_playlist", {"Artist": "", "Name": name})
    engine.send_to_jriver(keys, typed=True, report=report)
    note_recent(playlist, "played")
    engine.session_finish(session_id, len(keys), sources="JRiver", report=report)
    engine.SAVE_NAME = name


def embellish(playlist, order, amount, report):
    """Play & Embellish: the playlist with new tracks woven in."""
    name, keys = _read(playlist, report)
    if keys is None:
        return
    ordered = order == "ordered"
    artists = len(_artists(keys))
    report(t("Embellish: {name}, {tracks} by {artists} artists, {amount}.", name=name,
             tracks=tn("{count} track", "{count} tracks", len(keys)), artists=artists, amount=t(AMOUNT_NAMES[amount])))
    session_id = engine.session_start("embellish", {"Artist": "", "Name": name})
    result = find(keys, name, amount, report)
    if result is None:
        engine.session_finish(session_id, 0, sources="none", report=report)
        return
    new, stats = result
    say_result(name, new, stats, report)
    if new:
        report("  " + t("Added {tracks} from the agreeing artists, woven between yours, {how}.",
                        tracks=tn("{count} track", "{count} tracks", len(new)),
                        how=t("in your order") if ordered else t("shuffled")))
    out = weave(keys, new, ordered)
    engine.send_to_jriver(out, typed=True, report=report)
    note_recent(playlist, "embellished")
    engine.session_finish(session_id, len(out), report=report)
    engine.SAVE_NAME = t("{name} (Embellished)", name=name)
