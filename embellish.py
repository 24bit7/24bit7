"""
24bit7 - the Play tab's JRiver Playlists tab (Ben, 6 Nov 2026).

Play plays a JRiver playlist or smartlist, shuffled or in its own order. Play & Embellish
grows it first: Consensus with the playlist's own artists as the circle, then the top
tracks you own by each artist the circle agrees on, woven in with yours.

  +10%, +20%, +50%   one new track for every ten, five or two on the playlist
  Double, Triple     as many new tracks as the playlist has, or twice as many
  Build It Out       every agreeing artist's top tracks you own, until none are left

Which amounts the arrow offers, and which the button itself runs, are set under Settings >
JRiver Playlists > Play & Embellish (Ben, 7 Nov 2026): all six to start, +50% the default
(the Add Half of 1.31.0's first days). Picking one from the arrow runs it once.

The circle is taken ten of the playlist's artists at a time, picked at random (a big
playlist is sampled, as Playing Now is). Every amount but Build It Out stops as soon as it
has enough; Build It Out says what each stage added, and Cancel keeps what's found so
far: the lot goes in when it finishes or is stopped, so Ordered stays in your order.

The playlist's first track plays first. Ordered keeps your order with the new tracks
spread evenly between; Shuffled shuffles the lot, with the artists spread.

How an amount builds is set in the same place (Ben, 10 Nov 2026): Shuffle, Deep Cuts and the
Moderator, in one row that serves every amount (the default) or a row per amount. Shuffle is
on to start. Deep Cuts top up what Embellish adds, from the genre most of the playlist
shares, and the Moderator checks the new tracks against the playlist; the More Options
switches beat both while that row is open, as they do for every playlist. Play's arrow
(Play Shuffled, Play Ordered) is Play's alone. Anything asked for by voice runs the default
amount with that amount's row.

Albums too (Ben, 12 Nov 2026): the tab is Playlists & Albums, and Play & Embellish is Embellish. An album
plays in order unless Play's arrow says otherwise (remembered apart from a playlist's), and Embellish offers
the amounts, the album taken as a playlist of its tracks, plus With Their Hits (the album and the artist's
widely played songs from their other albums, shuffled, its first track first) and And Their Hits (the album
in order, then those songs, biggest first). A hit is as Use Adaptive Selections counts it, by Last.fm's plays.
A playlist or album by one artist builds its circle from that artist and two picked at random from the five
most like them. Play has no Non-stop of its own: More Options' switch turns it on.
"""

import json
import random

import engine
from i18n import N_, t, tn

AMOUNTS = ("p10", "p20", "p50", "double", "triple", "out")
AMOUNT_NAMES = {"p10": N_("+10%"), "p20": N_("+20%"), "p50": N_("+50%"), "double": N_("Double"),
                "triple": N_("Triple"), "out": N_("Build It Out")}
SHARES = {"p10": 0.1, "p20": 0.2, "p50": 0.5, "double": 1.0, "triple": 2.0}   # new tracks per track on the playlist
DEFAULT_AMOUNT = "p50"
OLD_AMOUNTS = {"half": "p50"}   # 1.31.0's first days: Add Half and Double It
AMOUNTS_KEY = "embellish_amounts"   # {"shown": [codes], "default": code}: Settings > JRiver Playlists
ORDERS = ("shuffled", "ordered")
HITS = ("with_hits", "and_hits")   # an album's own Embellish options (12 Nov 2026)
HIT_NAMES = {"with_hits": N_("With Their Hits"), "and_hits": N_("And Their Hits")}
HITS_MOST = 10      # the most hits an album is given
ALBUMS_KEY = "embellish_albums"   # {"shown": [codes], "default": code, "rows": {code: {"nonstop"}}}
PARTNERS = 2        # a one-artist circle: the artist and this many of...
PARTNERS_FROM = 5   # ...the artists most like them, picked at random
ORDER_NAMES = {"shuffled": N_("Play Shuffled"), "ordered": N_("Play Ordered")}
STAGE = 10          # playlist artists added to the circle per stage
AGREE = 2           # an artist on this many of the circle's lists is agreed on
BIG = 30            # Build It Out over more artists than this says up front it may take a while
RECENT = 5          # the most recent shown at the top of the list
RECENT_KEY = "jriver_playlists_recent"
CHOICE_KEY = "jriver_playlists_choices"
SETTINGS_KEY = "embellish_settings"   # {"all": "1" or "0", "all_row": row, "rows": {amount: row}}
DEFAULT_ROW = {"shuffle": "1", "deep_cuts": "off", "deep_share": "10", "moderator": "off", "nonstop": "no"}
NONSTOP_USING = ("no", "artists", "tracks")   # the Non-stop column (12 Nov 2026), as a JRiver playlist's row has it
REFERENCE = 15      # the playlist's own tracks shown to the Moderator as what fits


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


def is_album(item):
    """A pick from the box: an album ({"kind": "album", "Name", "Artist", "keys"}) rather than a JRiver playlist."""
    return isinstance(item, dict) and item.get("kind") == "album"


def album_id(name, artist):
    return f"album:{artist}|{name}"


def recent():
    """[{"id", "name", "how", "when"}] most recent first: what 24bit7 played or embellished (JRiver keeps no dates).
    An album's carries "kind": "album" and its "artist"."""
    items = _meta(RECENT_KEY, [])
    return [x for x in items if isinstance(x, dict) and x.get("id")][:RECENT]


def note_recent(playlist, how):
    """Puts a playlist at the top of the recent five. how: "played" or "embellished"."""
    from datetime import datetime
    album = is_album(playlist)
    pid = album_id(playlist.get("Name"), playlist.get("Artist")) if album else str(playlist.get("ID"))
    items = [x for x in recent() if str(x.get("id")) != pid]
    entry = {"id": pid, "name": playlist.get("Name") or "", "how": how,
             "when": datetime.now().strftime("%Y-%m-%d %H:%M")}
    if album:
        entry.update(kind="album", artist=playlist.get("Artist") or "")
    items.insert(0, entry)
    _set_meta(RECENT_KEY, items[:RECENT])


def choices():
    """{"order": "shuffled" or "ordered" (Play's arrow, remembered), "album_order" (the same for an album, In
    Order to start), "amount": the default amount, "album_amount": an album's default (Settings)}."""
    saved = _meta(CHOICE_KEY, {})
    order = saved.get("order") if saved.get("order") in ORDERS else "shuffled"
    album_order = saved.get("album_order") if saved.get("album_order") in ORDERS else "ordered"
    return {"order": order, "album_order": album_order, "amount": amounts()["default"],
            "album_amount": albums()["default"]}


def set_choice(key, value):
    """Play's arrow: Shuffled or Ordered, remembered. (The amount is Settings' default: set_amounts.)"""
    saved = dict(_meta(CHOICE_KEY, {}))
    saved[key] = value
    _set_meta(CHOICE_KEY, saved)


def amounts():
    """
    {"shown": the amounts the arrow offers, in AMOUNTS' order, "default": what the button runs}. At least one
    is shown and the default is one of them. Before this setting, the arrow's last choice was the default.
    """
    saved = _meta(AMOUNTS_KEY, None)
    if not isinstance(saved, dict):
        old = _meta(CHOICE_KEY, {}).get("amount")
        old = OLD_AMOUNTS.get(old, old)
        return {"shown": list(AMOUNTS), "default": old if old in AMOUNTS else DEFAULT_AMOUNT}
    shown = [a for a in AMOUNTS if a in (saved.get("shown") or [])] or [DEFAULT_AMOUNT]
    default = saved.get("default") if saved.get("default") in shown else shown[0]
    return {"shown": shown, "default": default}


def set_amounts(shown=None, default=None):
    """Settings > JRiver Playlists: which amounts the arrow offers, and the default. Kept sensible either way."""
    now = amounts()
    shown = [a for a in AMOUNTS if a in (now["shown"] if shown is None else shown)] or [now["default"]]
    default = now["default"] if default is None else default
    if default not in shown:
        default = shown[0]
    _set_meta(AMOUNTS_KEY, {"shown": shown, "default": default})
    return {"shown": shown, "default": default}


def albums():
    """
    An album's own Embellish options, Settings' Albums rows (12 Nov 2026): {"shown": the hits options the arrow
    offers beside the amounts, "default": what the button runs for an album (a hits option or an amount),
    "rows": {code: {"nonstop": no, artists or tracks}}}. Both shown, With Their Hits the default, Non-stop off.
    """
    saved = _meta(ALBUMS_KEY, None)
    saved = saved if isinstance(saved, dict) else {}
    shown = [h for h in HITS if h in saved.get("shown", list(HITS))]
    choosable = shown + amounts()["shown"]
    default = saved.get("default") if saved.get("default") in choosable else (shown or choosable)[0]
    rows = {}
    for h in HITS:
        row = (saved.get("rows") or {}).get(h) or {}
        rows[h] = {"nonstop": row.get("nonstop") if row.get("nonstop") in NONSTOP_USING else "no"}
    return {"shown": shown, "default": default, "rows": rows}


def set_albums(shown=None, default=None, **rows):
    """Settings' Albums rows: which hits options are offered, an album's default, and each one's Non-stop
    (set_albums(with_hits="artists"))."""
    now = albums()
    shown = [h for h in HITS if h in (now["shown"] if shown is None else shown)]
    default = now["default"] if default is None else default
    if default not in shown + amounts()["shown"]:
        default = (shown + amounts()["shown"])[0]
    for h, using in rows.items():
        if h in HITS and using in NONSTOP_USING:
            now["rows"][h] = {"nonstop": using}
    data = {"shown": shown, "default": default, "rows": now["rows"]}
    _set_meta(ALBUMS_KEY, data)
    return albums()


# --- how an amount builds: one row for every amount, or a row each ------------------------------------

def _tidy_row(row, base):
    out = dict(base)
    if isinstance(row, dict):
        out.update({k: str(v) for k, v in row.items() if k in DEFAULT_ROW})
    out["shuffle"] = "1" if out.get("shuffle") == "1" else "0"
    if out.get("deep_cuts") not in engine.DEEP_CUT_MODES:
        out["deep_cuts"] = "off"
    share = int(out["deep_share"]) if str(out.get("deep_share")).isdigit() else 10
    out["deep_share"] = str(min(100, max(10, share - share % 10)))
    if out.get("moderator") not in engine.MODERATOR_LEVELS:
        out["moderator"] = "off"
    if out.get("nonstop") not in NONSTOP_USING:
        out["nonstop"] = "no"
    return out


def _nonstop_was():
    """
    What Non-stop did after an Embellish before the column (12 Nov 2026): the standard Artist Matching playlist's
    Non-stop. The column starts from it, once, so nobody's Embellish changes at the upgrade.
    """
    try:
        import buttons
        std = buttons.standard("artists")
        cfg = buttons.nonstop_own(std) if std is not None else {"on": False}
    except Exception:
        return "no"
    if not cfg.get("on"):
        return "no"
    return cfg.get("using") if cfg.get("using") in ("artists", "tracks") else "artists"


def _tidy(data):
    data = data if isinstance(data, dict) else {}
    all_row = _tidy_row(data.get("all_row"), DEFAULT_ROW)
    rows = {a: _tidy_row(r, all_row) for a, r in (data.get("rows") or {}).items()
            if a in AMOUNTS and isinstance(r, dict)}
    return {"all": "0" if str(data.get("all")) == "0" else "1", "all_row": all_row, "rows": rows}


def settings():
    """
    {"all": "1" while one row serves every amount (the default), "all_row": that row, "rows": {amount: its own}}.
    A row is {"shuffle", "deep_cuts" (off, spaced or shuffled), "deep_share" (what Deep Cuts top up by, ten to a
    hundred per cent of what Embellish adds), "moderator" (a level), "nonstop" (no, artists or tracks: what's
    added when the playlist reaches its last track)}. Before this table Embellish followed Play's
    arrow, so the first read keeps that order as the All amounts row's Shuffle, once: nobody's Embellish changes
    at the upgrade, and from then on the arrow is Play's alone.
    """
    saved = _meta(SETTINGS_KEY, None)
    if not isinstance(saved, dict):
        was = _meta(CHOICE_KEY, {}).get("order")
        saved = {"all": "1", "all_row": dict(DEFAULT_ROW, shuffle="0" if was == "ordered" else "1",
                                             nonstop=_nonstop_was()), "rows": {}}
        try:
            _set_meta(SETTINGS_KEY, saved)
        except Exception:
            pass   # the database can't be written just now: the same answer is worked out next time
    elif "nonstop" not in (saved.get("all_row") or {}):   # saved before the Non-stop column: it starts as it was
        saved = dict(saved, all_row=dict(saved.get("all_row") or {}, nonstop=_nonstop_was()))
        try:
            _set_meta(SETTINGS_KEY, saved)
        except Exception:
            pass
    return _tidy(saved)


def set_settings(data):
    """Settings > JRiver Playlists > Play & Embellish: the tick, the All amounts row and the amounts' own rows."""
    data = _tidy(data)
    _set_meta(SETTINGS_KEY, data)
    return data


def row_for(amount, data=None):
    """The row one amount builds with: the All amounts row, or its own (a copy of that row until it's changed)."""
    data = settings() if data is None else _tidy(data)
    if data["all"] == "1":
        return dict(data["all_row"])
    return dict(data["rows"].get(OLD_AMOUNTS.get(amount, amount)) or data["all_row"])


def use_one_row(on):
    """
    The table's tick, "Use the same settings for every amount". Off, each amount runs its own row: the rows made
    while it was off before are kept, and an amount never given one runs a copy of the All amounts row.
    """
    data = settings()
    data["all"] = "1" if on else "0"
    return set_settings(data)


def set_row(amount, **changes):
    """
    One line of the table changed: amount None is the All amounts row. An amount's first change gives it a row
    of its own, the rest of it copied from the All amounts row as it stood.
    """
    data = settings()
    if amount is None:
        data["all_row"].update(changes)
    else:
        amount = OLD_AMOUNTS.get(amount, amount)
        data["rows"].setdefault(amount, dict(data["all_row"])).update(changes)
    return set_settings(data)


def _plan(amount, report):
    """An amount's row for this build, the More Options switches over it while that row is open (and said so)."""
    row = row_for(amount)
    import overrides
    if overrides.active():
        on = overrides.switches()
        report(t("More Options: {switches}, over this playlist's own settings.", switches=overrides.summary()))
        row["moderator"], row["deep_cuts"] = on["moderator"], on["deep_cuts"]
        row["nonstop_mode"] = on["nonstop"]
    return row


def nonstop_cfg(row):
    """
    Non-stop after this Embellish, as Non-stop reads a JRiver playlist's ({"using", "reseed"}), or None for none.
    The row's column plays on from the last track; the More Options switch, while its row is open, turns it off,
    or on with Wander (from the last track) or Keep It Tight (from the playlist), using the row's kind or artists.
    """
    using = row.get("nonstop", "no")
    mode = row.get("nonstop_mode")
    if mode == "off":
        return None
    if mode in ("tight", "journey"):
        return {"using": using if using in ("artists", "tracks") else "artists",
                "reseed": "whole" if mode == "tight" else "last"}
    if using not in ("artists", "tracks"):
        return None
    return {"using": using, "reseed": "last"}


# --- the build ------------------------------------------------------------------------------------

def want_for(amount, count):
    """How many new tracks an amount asks for, on a playlist of count tracks. None: as many as there are."""
    amount = OLD_AMOUNTS.get(amount, amount)
    if amount == "out":
        return None
    return max(1, int(round(count * SHARES.get(amount, 0.5))))


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
    library.ensure_loaded()   # asked before the build reads the library: the count in the first line, the fast start
    out = {}
    for k in keys:
        row = library.track_row(k) or {}
        name = row.get("Artist") or ""
        a = engine.artist_key(name)
        if a and a not in out:
            out[a] = name
    return out


def find(keys, name, amount, report, spare=0, session_id=None):
    """
    New tracks for the playlist: (new keys, what happened). Returns None when there's nothing for the
    circle to agree on (one artist), having said so. spare: a share more than the amount asks for, found
    up front so the Moderator's removals are replaced (never for Build It Out, which takes everything).
    Each agreeing artist is a line in the console, and each of its top tracks looked up is said, In library or
    Not in library, and logged to the session for Discover, as Similar Artists does (10 Nov 2026: Embellish
    worked in silence and its sessions were empty).
    """
    import library
    library.ensure_loaded()
    on_list = _artists(keys)
    partners = []
    if len(on_list) < 2:
        # One artist (an album, or a playlist of one artist's songs): the circle is the artist and two of the
        # five most like them, picked at random so each run differs (Ben, 12 Nov 2026)
        only = next(iter(on_list.values()), "")
        partners = _partners(only, report) if only else []
        if not partners:
            report(t("Embellish: every track on {name} is by {artist}, and your sources know too few artists like "
                     "them to build a circle, so there's nothing to add.", name=name, artist=only or "?"))
            return None
        report("  " + t("Every track on {name} is by {artist}, so the circle is {artist} and two of the five artists "
                        "most like them, picked at random: {picks}.", name=name, artist=only,
                        picks=t("{one} and {two}", one=partners[0], two=partners[1])))
    asked = want = want_for(amount, len(keys))
    if want is not None and spare:
        want += max(1, int(want * spare))
    if amount == "out" and len(on_list) > BIG:
        report("  " + t("Build It Out: {name} has {tracks} by {artists} artists. That can mean several hundred tracks "
                        "and a few minutes; Cancel keeps whatever is in.", name=name,
                        tracks=tn("{count} track", "{count} tracks", len(keys)), artists=len(on_list)))
    have = {str(k) for k in keys}
    played = engine.PlayedFilter("artists", report=report, filters=True)
    cap = None if amount == "out" else engine.TRACKS_PER_ARTIST_PICK
    order = list(on_list.values())
    random.shuffle(order)   # a big playlist is sampled, ten artists a stage
    order += partners
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
            guests = agreed[len(circle):]
            if partners and stage == 1:   # the two picked are the closest to the artist: their songs go in too
                taken = {engine.artist_key(p) for p in partners}
                guests = [(p, None) for p in partners] + [g for g in guests if engine.artist_key(g[0]) not in taken]
            report("  " + t("Consensus: {names} (circle of {size}, agree on {agree})", names=", ".join(members),
                            size=len(circle), agree=AGREE))
            report("  " + t("{agreed} artists on {agree} or more of their lists; {already} already on {name}.",
                            agreed=len(guests), agree=AGREE, name=name,
                            already=sum(1 for g, _why in guests if engine.artist_key(g) in on_list)))
            picks = {}
            for artist, _why in guests:
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
                report("  " + t("{artist}...", artist=artist))
                if not top:
                    report("    " + t("No top tracks returned for {artist}.", artist=artist))
                # Use Adaptive Selections (12 Nov 2026): a one-hit wonder gives its hit, not the rest
                titles, each = engine.adaptive_cut(artist, [title for title, _ in top], cap or len(top), report)
                most = cap
                if len(titles) < len(top):
                    top = top[:len(titles)]
                    most = each if cap else None
                owned = []
                for title, _sources in top:
                    key = library.find_track_key(artist, title)
                    report("    " + t("{found_label}: {track_name}", track_name=title,
                                      found_label=t("In library") if key else t("Not in library")))
                    if session_id is not None:
                        engine.session_log(session_id, artist, title, ["Embellish"], found=bool(key))
                    key = played.pick(key) if key and str(key) not in have else None
                    if key and str(key) not in have and str(key) not in owned:
                        owned.append(str(key))
                picks[artist] = owned[:most] if most else owned
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
    return new, {"agreed": len(agreed_all), "already": len(already), "want": asked, "artists": len(on_list)}


def _partners(artist, report):
    """Two of the five artists most like this one, at random; [] when the sources know fewer than two."""
    found, _label = engine.blended_similar_artists(artist, limit=30, report=report)
    me = engine.artist_key(artist)
    near = [a for a, _ in found if engine.artist_key(a) != me][:PARTNERS_FROM]
    if len(near) < PARTNERS:
        return []
    return random.sample(near, PARTNERS)


def _tracks(keys):
    """[(key, artist, title)] as the Moderator takes them."""
    import library
    out = []
    for k in keys:
        row = library.track_row(k) or {}
        out.append((str(k), row.get("Artist") or "", row.get("Name") or ""))
    return out


def moderator_seed(name, keys):
    """What the Moderator judges the new tracks against: the playlist, by its name and the artists on it."""
    artists = list(_artists(keys).values())[:10]
    return f"vibe: the playlist {name}, in the sound of {', '.join(artists)}"


def moderate(new, keys, name, level, report):
    """
    The Moderator on what Embellish adds (10 Nov 2026): the new tracks checked against the playlist, with some of
    its own tracks, spread through it, as what fits. Your own tracks are never checked. Returns (kept, how many
    went). Off, or with no AI to run it (said once by the engine), nothing goes.
    """
    if level in ("", "off") or not new:
        return new, 0
    keys = [str(k) for k in keys]
    step = max(1, len(keys) // REFERENCE)
    removed = engine.moderate(_tracks(new), moderator_seed(name, keys), report, level=level,
                              reference=_tracks(keys[::step][:REFERENCE]))
    return ([k for k in new if k not in removed], len(removed)) if removed else (new, 0)


def deep_cuts(out, keys, new, name, row, report):
    """
    Deep Cuts on an embellished playlist (10 Nov 2026): lesser-played artists from the genre most of your playlist
    shares, as Radio picks them, topping up what Embellish added by the row's share (your own playlist is yours,
    so the share is of the new tracks). Spaced or Shuffled through the lot, the first track still leading.
    """
    if row["deep_cuts"] == "off" or not new:
        return out
    try:
        import deepcuts
        genre = deepcuts.common_genre(keys, share=0.3)
    except Exception:
        genre = None
    if not genre:
        report("  " + t("Deep Cuts: none this time, as no one genre is shared by enough of the tracks on {name}.",
                        name=name))
        return out
    share = int(row["deep_share"])
    return engine.add_deep_cuts(out, None, report, group="artists", genres=[genre],
                                moderator_seed=moderator_seed(name, keys),
                                cfg={"mode": row["deep_cuts"], "share": share}, level=row["moderator"],
                                count=max(1, round(len(new) * share / 100)))


def say_result(name, new, stats, report, removed=0):
    """The honest line: what was added, or why not as many as asked. removed: how many the Moderator took out."""
    added, want, agreed, already = len(new), stats["want"], stats["agreed"], stats["already"]
    if removed and not added:
        report(t("Embellish: nothing to add, as the Moderator removed every track found for {name}.", name=name))
        return
    if removed and want is not None and added < want:
        report("  " + t("Embellish: added {added}, fewer than the {want} asked for, as the Moderator removed {removed}.",
                        added=tn("{count} track", "{count} tracks", added), want=want, removed=removed))
        return
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


def shown_name(item):
    """'OK Computer by Radiohead' for an album, the playlist's name for a playlist."""
    if is_album(item):
        return t("{album} by {artist}", album=item.get("Name") or "", artist=item.get("Artist") or "")
    return item.get("Name") or t("playlist")


def _read(playlist, report):
    if is_album(playlist):   # an album: its tracks in disc and track order, read from the library when picked
        name = shown_name(playlist)
        keys = [str(k) for k in playlist.get("keys") or []]
        if not keys:
            report(t("Problem: {name} has no tracks in your library now, so there's nothing to play.", name=name))
            return name, None
        return name, keys
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


def _play_nonstop(item, report):
    """
    Play has no Non-stop of its own (Ben, 12 Nov 2026): More Options' switch, while its row is open, turns it
    on (Wander from the last track, Keep It Tight from the playlist's or album's own), with similar artists.
    Before this, Play carried on as the standard Artist Matching playlist's Non-stop said. A playlist's row
    under Settings (Skip recent, Non-stop) is for voice alone.
    """
    import overrides
    if not overrides.active():
        return None
    mode = overrides.switches()["nonstop"]
    report("  " + (t("More Options: Non-stop {setting}, over this album's own settings.", setting=t(overrides.LABELS[mode]))
                   if is_album(item) else
                   t("More Options: Non-stop {setting}, over this playlist's own settings.",
                     setting=t(overrides.LABELS[mode]))))
    return nonstop_cfg({"nonstop": "no", "nonstop_mode": mode})


def play(playlist, order, report):
    """Play: the playlist or album as it is, shuffled or in order, through the usual output (Review, Top-Up,
    YouTube...)."""
    name, keys = _read(playlist, report)
    if keys is None:
        return
    ordered = order == "ordered"
    report(t("Play: {name}, {tracks}, {how}.", name=name, tracks=tn("{count} track", "{count} tracks", len(keys)),
             how=t("in order") if ordered else t("shuffled")))
    if not ordered:
        keys = list(keys)
        random.shuffle(keys)
    session_id = engine.session_start("jriver_playlist", {"Artist": playlist.get("Artist") or "", "Name": name})
    engine.NONSTOP_CONTEXT["own_nonstop"] = _play_nonstop(playlist, report)
    engine.send_to_jriver(keys, typed=True, report=report)
    note_recent(playlist, "played")
    engine.session_finish(session_id, len(keys), sources="JRiver", report=report)
    engine.SAVE_NAME = name


def embellish(playlist, order, amount, report):
    """
    Play & Embellish: the playlist with new tracks woven in, as the amount's row under Settings > JRiver Playlists
    has it (Shuffle, Deep Cuts, the Moderator). order: "ordered" or "shuffled" beats the row's Shuffle for this
    run; None, as the Play tab passes, takes the row's.
    """
    name, keys = _read(playlist, report)
    if keys is None:
        return
    artists = len(_artists(keys))
    amount = OLD_AMOUNTS.get(amount, amount)
    if amount in HITS:
        return hits(playlist, amount, report)
    report(tn("Embellish: {name}, {tracks} by {count} artist, {amount}.",
              "Embellish: {name}, {tracks} by {count} artists, {amount}.", artists, name=name,
              tracks=tn("{count} track", "{count} tracks", len(keys)), amount=t(AMOUNT_NAMES[amount])))
    row = _plan(amount, report)
    ordered = (order == "ordered") if order else row["shuffle"] != "1"
    level = row["moderator"]
    can_moderate = level != "off" and engine.ai_configured() and engine.USE_AI
    session_id = engine.session_start("embellish", {"Artist": playlist.get("Artist") or "", "Name": name})
    engine.NONSTOP_CONTEXT["own_nonstop"] = nonstop_cfg(row)   # the Non-stop column, not Artist Matching's
    # Fast start (10 Nov 2026): the playlist's own first track leads whatever is added, so on a stopped zone it
    # plays now and the rest follows it in when the build is done. One artist builds a circle too (12 Nov 2026), so
    # every playlist and album starts; if nothing can be added, the rest of it follows as it is.
    fast = engine.FastStart(None, report, enabled=True)
    fast.play(keys[0])
    result = find(keys, name, amount, report, spare=engine.MODERATOR_EXTRA[level] if can_moderate else 0,
                  session_id=session_id)
    if result is None:
        if fast.started:   # already playing: the rest of it follows, as it is
            engine.send_to_jriver(fast.rest(list(keys)), typed=True, report=report, append=True)
            engine.session_finish(session_id, len(keys), sources="none", report=report)
            return
        engine.session_finish(session_id, 0, sources="none", report=report)
        return
    new, stats = result
    new, removed = moderate(new, keys, name, level, report)
    if stats["want"] is not None:
        new = new[:stats["want"]]   # the spares found for the Moderator, if it didn't need them
    say_result(name, new, stats, report, removed=removed)
    if new:
        report("  " + t("Added {tracks} from the agreeing artists, woven between yours, {how}.",
                        tracks=tn("{count} track", "{count} tracks", len(new)),
                        how=t("in your order") if ordered else t("shuffled")))
    out = weave(keys, new, ordered)
    out = deep_cuts(out, keys, new, name, row, report)
    engine.send_to_jriver(fast.rest(out), typed=True, report=report, append=fast.started)
    note_recent(playlist, "embellished")
    engine.session_finish(session_id, len(out), report=report)
    engine.SAVE_NAME = t("{name} (Embellished)", name=name)


# --- an album with the artist's hits (Ben, 12 Nov 2026) -------------------------------------------------

def _hits_plan(how, report):
    """The hits option's row (its Non-stop), the More Options switch over it while that row is open."""
    row = dict(albums()["rows"][how])
    import overrides
    if overrides.active():
        report(t("More Options: {switches}, over this album's own settings.", switches=overrides.summary()))
        row["nonstop_mode"] = overrides.switches()["nonstop"]
    return row


def their_hits(artist, keys, report, session_id=None):
    """
    The artist's widely played songs you own that aren't on the album, biggest first, at most HITS_MOST, as
    keys; [] (having said why) when there are none, and None when Last.fm has no counts for the artist. A song
    on the album is left out by its title, so a best-of's copy of one of the album's songs doesn't come back.
    """
    import library
    titles = engine.hit_titles(artist)
    if not titles:
        return None
    on_album = {engine.clean_name((library.track_row(k) or {}).get("Name") or "") for k in keys}
    have = {str(k) for k in keys}
    out, on, missing = [], 0, 0
    for title in titles:
        if len(out) >= HITS_MOST:
            break
        if engine.clean_name(title) in on_album:
            on += 1
            continue
        key = library.find_track_key(artist, title)
        report("    " + t("{found_label}: {track_name}", track_name=title,
                          found_label=t("In library") if key else t("Not in library")))
        if session_id is not None:
            engine.session_log(session_id, artist, title, ["Embellish"], found=bool(key))
        if not key:
            missing += 1
        elif str(key) not in have and str(key) not in out:
            out.append(str(key))
    report("  " + tn("{artist} has {count} widely played song on Last.fm: {on} on this album, {added} you own from "
                     "other albums.",
                     "{artist} has {count} widely played songs on Last.fm: {on} on this album, {added} you own from "
                     "other albums.", len(titles), artist=artist, on=on, added=len(out)))
    return out


def hits(album, how, report):
    """With Their Hits or And Their Hits: the album and the artist's hits from their other albums."""
    name, keys = _read(album, report)
    if keys is None:
        return
    artist = album.get("Artist") or ""
    report(t("Embellish: {name}, {tracks}, {how}.", name=name, tracks=tn("{count} track", "{count} tracks", len(keys)),
             how=t(HIT_NAMES[how])))
    row = _hits_plan(how, report)
    session_id = engine.session_start("embellish", {"Artist": artist, "Name": name})
    engine.NONSTOP_CONTEXT["own_nonstop"] = nonstop_cfg(row)
    fast = engine.FastStart(None, report, enabled=True)
    fast.play(keys[0])
    new = their_hits(artist, keys, report, session_id=session_id)
    if new is None:
        report("  " + t("Last.fm has no play counts for {artist}, so their hits can't be told from the rest: "
                        "{name} plays as it is.", artist=artist, name=name))
        new = []
    elif not new:
        report("  " + t("Nothing to add: none of {artist}'s widely played songs that you own are on other albums, "
                        "so {name} plays as it is.", artist=artist, name=name))
    elif how == "with_hits":
        report("  " + tn("Added {count} of their hits, shuffled through the album.",
                         "Added {count} of their hits, shuffled through the album.", len(new)))
    else:
        report("  " + tn("Added {count} of their hits after the album, biggest first.",
                         "Added {count} of their hits after the album, biggest first.", len(new)))
    out = weave(keys, new, False) if how == "with_hits" and new else list(keys) + new
    engine.send_to_jriver(fast.rest(out), typed=True, report=report, append=fast.started)
    note_recent(album, "embellished")
    engine.session_finish(session_id, len(out), report=report)
    engine.SAVE_NAME = t("{name} (Embellished)", name=name)

