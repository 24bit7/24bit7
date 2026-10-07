"""
24bit7 - non-stop.

Keeps a playlist 24bit7 built going: when the last of its tracks starts playing
in a zone, more are added to the end, so the music never stops. Set per Play
option under Settings > Playlist (Windows (Main), or a device's own tab). A
playlist follows the Non-stop settings of the option it started as, all evening.

  Similar Artists, Similar Tracks: top up using the Play using choice, seeded
      from the last track or the second track (Reseed from).
  Artist's Top Tracks: first the rest of the artist's songs, shuffled (up to a
      number, or unlimited), then a new playlist seeded from their most popular track.
  Vibe Playlist: more of the same vibe (asks the AI again), or Similar Artists /
      Similar Tracks like the others.

Keep It Tight reseeds each top-up from a track of the original playlist instead, a
different one each time, then carries on as Let's See Where This Goes when they've all
been used. A JRiver playlist row set to Reseed from "Whole playlist" does the same.

Only playlists 24bit7 sent are topped up (engine.NONSTOP_ZONES remembers them);
anything you start in JRiver yourself ends as normal. Each last track triggers
one top-up. Top-ups are queued on the Play tab like voice commands, with the
settings of the Alexa device mapped to the zone if it has its own.
"""

import random
import threading

from dotenv import dotenv_values

import engine
import filters

POLL_SECONDS = 15   # a top-up only has to land while the last track plays
YES = ("1", "true", "yes")

_submit = None
_thread = None
_stop = threading.Event()


def attach(submit):
    """The GUI hands over how to queue a build on the Play tab."""
    global _submit
    _submit = submit


def start():
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_watch, daemon=True, name="24bit7 non-stop")
    _thread.start()


def stop():
    _stop.set()


def _device_for_zone(zone_name):
    try:
        import hotkeys
        return hotkeys._device_for_zone(zone_name)
    except Exception:
        return None, None, {}


def _settings_for(profile):
    """The zone's settings without touching the ones a running build is using: .env with the device's own on top."""
    values = {k: (v or "") for k, v in dotenv_values(engine.ENV_FILE).items()}
    values.update(profile or {})
    return values


def _watch():
    while not _stop.wait(POLL_SECONDS):
        try:
            _check_zones()
        except Exception as e:
            engine.print(f"Problem: Non-stop couldn't check the zones ({e}).")


def _check_zones():
    with engine._nonstop_lock:
        zones = list(engine.NONSTOP_ZONES.items())
    for zone, entry in zones:
        info = engine.get_playing_info(zone)
        if not info:
            continue
        try:
            position, count = int(info.get("PlayingNowPosition", "-1")), int(info.get("PlayingNowTracks", "0"))
        except (TypeError, ValueError):
            continue
        key = str(info.get("FileKey") or "")
        if count <= 0 or position != count - 1 or key not in entry["keys"]:
            continue   # not on the last track, or the zone is playing something 24bit7 didn't send
        marker = (key, count)
        if entry.get("fired") == marker:
            continue   # this last track has had its top-up
        zone_name = engine.zone_label(zone)
        device_id, device_name, profile = _device_for_zone(zone_name)
        origin = entry.get("origin") or entry.get("kind") or "artists"
        if origin == "saved":   # a saved playlist: its row in Settings > Saved Playlists said Non-stop
            on = bool(entry.get("saved_cfg"))
        else:
            on = engine.nonstop_settings(_settings_for(profile).get).get(origin, {}).get("on")
        if not on:
            continue
        entry["fired"] = marker
        if _submit is not None:
            _submit(_job(zone, zone_name, profile, info), f"Non-stop: {zone_name} reached its last track",
                    {"from": "nonstop", "zone": zone})


def _second_track_seed(zone, info):
    """The second track in Playing Now (the first pick after the original seed), or the playing one."""
    rows = engine.playing_now_rows(zone)
    if len(rows) >= 2 and rows[1].get("Key"):
        return engine.seed_from_row(rows[1], zone)
    return dict(info, ZoneID=zone)


def _build(mode, seed, report):
    if mode == "artists":
        engine.create_similar_playlist(report=report, seed_info=seed, topup=True)
    else:
        engine.create_similar_tracks_playlist(report=report, seed_info=seed)


def _rest_of_artist(zone, entry, info, report):
    """Artist's Top Tracks, stage two: the artist's other songs, shuffled. False if there are none left."""
    import library
    artist, keys = library.artist_tracks(entry.get("top_artist") or info.get("Artist") or "")
    sent = engine.nonstop_sent(zone) | {str(info.get("FileKey") or "")}
    keys = [str(k) for k in keys if str(k) not in sent]
    played = engine.PlayedFilter("top", report=report, filters=True)
    keys = [k for k in keys if played.fresh(k)]
    played.done()
    if not keys:
        report(f"  No more songs by {entry.get('top_artist')} in your library, so moving on.")
        return False
    random.shuffle(keys)
    if engine.NONSTOP_TOP_REST_COUNT:
        keys = keys[:engine.NONSTOP_TOP_REST_COUNT]
    report(f"  Adding {len(keys)} more song{'' if len(keys) == 1 else 's'} by {library.spoken(artist)}, shuffled.")
    engine.send_to_jriver(keys, report=report, append=True, closer_group="top")
    return True


def _top_seed(zone, entry, info):
    """Artist's Top Tracks, stage three: the artist's most popular track found earlier."""
    import library
    key = entry.get("top_first")
    if key:
        library.ensure_loaded()
        with library._lock:
            row = next((r for r in library._tracks if str(r.get("Key")) == str(key)), None)
        if row:
            return engine.seed_from_row(row, zone)
    return dict(info, ZoneID=zone)


def _tight_seed(zone, entry, report):
    """
    Keep It Tight: a track of the original playlist not used as a seed yet, picked at random.
    None once they've all been used (said once in the console).
    """
    import library
    library.ensure_loaded()
    seeded = entry.setdefault("seeded", set())
    pool = sorted(k for k in entry.get("original", ()) if k not in seeded)
    random.shuffle(pool)
    for key in pool:
        seeded.add(key)
        with library._lock:
            row = library._by_key.get(str(key))
        if row:
            report("  Keep It Tight: reseeding from a track of the original playlist.")
            return engine.seed_from_row(row, zone)
    if not entry.get("tight_done"):
        entry["tight_done"] = True
        report("  Keep It Tight has used every track of the original playlist as a seed, "
               "so carrying on as Let's See Where This Goes.")
    return None


def _job(zone, zone_name, profile, info):
    def run(report):
        try:
            engine.refresh_settings_if_changed()
            engine.OUTPUT_OVERRIDE = zone_name
            engine.use_profile(profile)
            engine.NONSTOP_APPEND = True
            engine.FILTER_DEVICE = filters.device_for_zone(zone_name)
            engine.NONSTOP_CONTEXT = {}   # adding the rest of an artist isn't a new build
            with engine._nonstop_lock:
                entry = engine.NONSTOP_ZONES.get(zone)
            if not entry:
                return
            kind = entry.get("kind")
            origin = entry.get("origin") or kind
            if origin == "saved":
                cfg = entry.get("saved_cfg") or {"using": "tracks", "reseed": "last"}
            else:
                cfg = engine.NONSTOP_BY.get(origin) or engine.NONSTOP_BY["artists"]
            tight = (cfg.get("reseed") == "whole") if origin == "saved" else cfg.get("mode") == "tight"
            report(f"  {zone_name} is on its last track, so adding more."
                   + (" (with its device's own settings)" if profile else ""))
            if kind == "top" and entry.get("stage") == "first":
                entry["stage"] = "rest"
                if engine.NONSTOP_TOP_REST and _rest_of_artist(zone, entry, info, report):
                    return
            if kind == "top":
                entry["stage"] = "after"
                seed = (_tight_seed(zone, entry, report) if tight else None) or _top_seed(zone, entry, info)
                report(f"  Carrying on from {seed['Artist']}, {seed['Name']}.")
                _build(cfg["using"], seed, report)
                return
            if origin == "vibe":
                if cfg.get("with") == "vibe" and entry.get("vibe"):
                    report(f"  More of the same vibe: {entry['vibe']}")
                    engine.create_vibe_playlist(entry["vibe"], report=report)
                    return
                mode = cfg.get("with") if cfg.get("with") in ("artists", "tracks") else "artists"
            else:
                mode = cfg["using"]
            seed = _tight_seed(zone, entry, report) if tight else None
            if seed is None:
                seed = _second_track_seed(zone, info) if cfg.get("reseed") == "second" else dict(info, ZoneID=zone)
            report(f"  Reseeding from {seed['Artist']}, {seed['Name']}.")
            _build(mode, seed, report)
        finally:
            engine.OUTPUT_OVERRIDE = None
            engine.NONSTOP_APPEND = False
            engine.FILTER_DEVICE = None
            engine.use_profile(None)
    return run
