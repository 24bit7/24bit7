"""
24bit7 - Blend, for JRiver playlists asked for by voice (Settings > JRiver Playlists).

With Blend ticked for a playlist, it starts at once as usual, then 24bit7 finds
new tracks like it in the background and weaves them in: one of yours, one new,
strictly alternating, until the new tracks run out, after which the playlist
carries on as normal (and Non-stop takes over at its end if that's on).

  Seeds      the playlist's first, middle and last tracks; later rounds seed from
             what's been found, like Drift, with no round limit
  How many   one new track per playlist track, at most CAP; it stops early when a
             round finds nothing new
  Modes      Similar artists: top tracks by artists like the seeds' artists, from
             the Similar Artists sources (a few per artist, as a Similar Artists
             build picks them); Similar tracks: songs like the seed tracks, from the
             Similar Tracks sources. Either way, what several seeds suggest ranks
             first, and a device's own settings are used if it has them
  Rules      never a track already in the playlist; Skip recent, Filters, the
             hidden-track check and "at most N per artist" all apply
"""

import time

import requests

import engine

CAP = 50              # the most new tracks one blend adds
SEEDS_PER_ROUND = 3


def _seed_rows(keys):
    """The playlist's first, middle and last tracks, as library rows."""
    import library
    picks = [keys[0], keys[len(keys) // 2], keys[-1]] if keys else []
    rows, seen = [], set()
    for k in picks:
        row = library.track_row(k)
        if row and str(k) not in seen:
            seen.add(str(k))
            rows.append(row)
    return rows


def _remove_after_current(zone, pos, count):
    for idx in range(count - 1, pos, -1):
        requests.get(f"{engine.JRIVER_BASE}/Playback/EditPlaylist",
                     params={"Zone": zone, "Action": "Remove", "Source": str(idx)}, auth=engine.AUTH, timeout=10)
        time.sleep(0.02)


def interleave(rest, new):
    """One new, one of yours, until the new ones run out; then the rest of yours."""
    out = []
    for i in range(max(len(rest), len(new))):
        if i < len(new):
            out.append(new[i])
        if i < len(rest):
            out.append(rest[i])
    return out


def _candidates(mode, artist, title, say):
    """[((artist, title), weight)] for one seed."""
    artists = engine.split_values(artist) or [artist]
    if mode == "artists":
        similar, _ = engine.blended_similar_artists(artists, limit=engine.SIMILAR_ARTIST_LIMIT,
                                                    seed_track=title, report=say)
        out = []
        for a, sources in similar:
            top, _ = engine.blended_top_tracks(a, limit=engine.TRACKS_PER_ARTIST_POOL)
            out += [((a, t), len(sources)) for t, _ in top]
        return out
    candidates, _ = engine.similar_track_candidates(artists, title, report=say)
    return [(pair, len(sources)) for pair, sources in candidates]


def find(keys, report, quiet=None, mode="tracks"):
    """New tracks like the playlist: [key], up to one per playlist track and CAP."""
    import library
    target = min(len(keys), CAP)
    exclude = {str(k) for k in keys}
    group = "artists" if mode == "artists" else "tracks"
    per_artist = engine.TRACKS_PER_ARTIST_PICK if mode == "artists" else engine.SIMILAR_TRACK_PER_ARTIST
    played = engine.PlayedFilter(group, report=report, filters=True)
    per, found, used, rounds = {}, [], set(), 0
    seeds = [(r.get("Artist") or "", r.get("Name") or "", str(r.get("Key"))) for r in _seed_rows(keys)]
    say = quiet or (lambda line: None)
    while seeds and len(found) < target:
        rounds += 1
        votes = {}
        for artist, title, key in seeds:
            used.add(key)
            for (a, t), weight in _candidates(mode, artist, title, say):
                ident = (engine.artist_key(a), engine.clean_name(t))
                score, pair = votes.get(ident, (0, (a, t)))
                votes[ident] = (score + 10 + weight, pair)   # agreement across seeds counts most
        added = 0
        for ident, (_, (a, t)) in sorted(votes.items(), key=lambda x: -x[1][0]):
            if len(found) >= target:
                break
            key = library.find_track_key(a, t)
            if not key or str(key) in exclude or str(key) in found:
                continue
            owner = engine.owner_key(a, key)
            if per.get(owner, 0) >= per_artist or not played.fresh(key):
                continue
            per[owner] = per.get(owner, 0) + 1
            found.append(str(key))
            added += 1
        report(f"  Round {rounds}: {added} new track{'' if added == 1 else 's'} found ({len(found)} of {target}).")
        if not added:
            break   # nothing new to find: stop rather than loop
        seeds = []
        for k in found:
            if k not in used and len(seeds) < SEEDS_PER_ROUND:
                row = library.track_row(k)
                if row:
                    seeds.append((row.get("Artist") or "", row.get("Name") or "", k))
    played.done()
    if len(found) < target:
        report(f"  Note: found {len(found)} new tracks of the {target} wanted, so the blend ends early "
               f"and the rest of the playlist plays as normal.")
    return found


def job(zone, keys, name, device_id=None, mode="tracks"):
    """The blend as a Play tab job: runs after the playlist has started."""
    def run(report):
        import hotkeys
        import filters
        zone_name = engine.zone_label(zone)
        _, _, profile = hotkeys._device_for_zone(zone_name)
        started = time.time()
        try:
            engine.refresh_settings_if_changed()
            engine.use_profile(profile)
            engine.FILTER_DEVICE = filters.device_for_zone(zone_name)
            engine.LAST_OUTPUT, engine.LAST_OUTPUT_ID = zone_name, zone
            report(f"  Blending in {'similar artists' if mode == 'artists' else 'similar tracks'}, "
                   f"one new track for each of yours, up to {CAP}.")
            new = find(keys, report, quiet=report, mode=mode)
            if not new:
                report("Problem: nothing new was found to blend in, so the playlist plays as saved.")
                return
            info = engine.get_playing_info(zone) or {}
            current = str(info.get("FileKey") or "")
            if current not in {str(k) for k in keys}:
                report("Note: the music on this zone changed while the blend was found, so it was left alone.")
                return
            pos, count = int(info.get("PlayingNowPosition", -1)), int(info.get("PlayingNowTracks", 0))
            rest = [r["Key"] for r in engine.playing_now_rows(zone)[pos + 1:] if r.get("Key")]
            _remove_after_current(zone, pos, count)
            engine.queue_tracks(interleave(rest, new), zone)
            with engine._nonstop_lock:
                entry = engine.NONSTOP_ZONES.get(zone)
                if entry is not None:
                    entry["keys"] |= set(new)
            report(f"Done: {len(new)} new track{'' if len(new) == 1 else 's'} blended into {name} "
                   f"in {zone_name}, {max(0, round(time.time() - started))} s.")
        finally:
            engine.use_profile(None)
            engine.FILTER_DEVICE = None
    return run
