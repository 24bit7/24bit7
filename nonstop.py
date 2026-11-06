"""
24bit7 - non-stop.

Keeps a playlist 24bit7 built going: when the last of its tracks starts playing
in a zone, more are added to the end, so the music never stops. Set per playlist
under Settings > Playlists. The music follows the Non-stop settings of the
playlist that built it, all evening.

  Similar Artists, Similar Tracks: top up using the Play using choice, seeded
      from the last track or the second track (Reseed from).
  Artist's Top Tracks: first the rest of the artist's songs, shuffled (up to a
      number, or unlimited), then a new playlist seeded from their most popular track.
  Vibe Playlist: more of the same vibe (asks the AI again), or Similar Artists /
      Similar Tracks like the others.

Keep It Tight reseeds each top-up from a track of the original playlist instead, a
different one each time, then carries on as Wander when they've all
been used. A JRiver playlist row set to Reseed from "Whole playlist" does the same.

Only playlists 24bit7 sent are topped up (engine.NONSTOP_ZONES remembers them);
anything you start in JRiver yourself ends as normal. Each last track triggers
one top-up. Top-ups are queued on the Play tab like voice commands. A top-up
that builds another kind (Artist Matching music topped up with Track Matching)
runs the standard playlist of that kind, under the original playlist's filters
as well.
"""

import random
import threading

import engine
from i18n import t, tn


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


def origin_button(zone_name, entry):
    """
    The playlist whose Non-stop settings the music follows: the one that built it, or, if
    that's gone (or it was a voice shuffle), the standard playlist of the kind it started as.
    """
    import buttons
    b = buttons.get(entry["button"]) if entry.get("button") else None
    if b is None:
        kind = entry.get("origin") or entry.get("kind") or "artists"
        b = buttons.standard(kind if kind in ("artists", "tracks", "top", "vibe") else "artists")
    return b


def config_for(zone_name, entry):
    """Non-stop's {"on", "using", "reseed", "mode"} for a playlist: its saved row's, or its button's."""
    import buttons
    origin = entry.get("origin") or entry.get("kind") or "artists"
    if origin == "radio":   # Radio always carries on: a fresh round from other pillars
        return {"on": True}
    if origin == "saved":
        cfg = entry.get("saved_cfg")
        return dict(cfg, on=True) if cfg else {"on": False}
    button = origin_button(zone_name, entry)
    return buttons.nonstop_config(button) if button else {"on": False}


def _watch():
    while not _stop.wait(POLL_SECONDS):
        try:
            _check_zones()
        except Exception as e:
            engine.print(t("Problem: Non-stop couldn't check the zones ({e}).", e=e))


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
        if str(info.get("State") or "") in ("0", "1"):
            continue   # stopped or paused on it: nothing more should play
        marker = (key, count)
        if entry.get("fired") == marker:
            continue   # this last track has had its top-up
        zone_name = engine.zone_label(zone)
        if not config_for(zone_name, entry).get("on"):
            continue
        entry["fired"] = marker
        entry["ends_at"] = engine.nonstop_track_ends(info)
        if _submit is not None:
            _submit(_job(zone, zone_name, info), t("Non-stop: {zone} reached its last track", zone=zone_name),
                    {"from": "nonstop", "zone": zone})


def _second_track_seed(zone, info):
    """The second track in Playing Now (the first pick after the original seed), or the playing one."""
    rows = engine.playing_now_rows(zone)
    if len(rows) >= 2 and rows[1].get("Key"):
        return engine.seed_from_row(rows[1], zone)
    return dict(info, ZoneID=zone)


def _build(mode, seed, zone_name, origin, report):
    """
    A top-up as Artist Matching or Track Matching: the playlist that built the music if it's
    that kind, else the standard playlist of that kind, under the original playlist's filters too.
    """
    import buttons
    button = origin if origin is not None and origin["kind"] == mode else buttons.standard(mode)
    if button is None:
        report("  " + t("Problem: there's no {kind} button to build with. Restore Default Buttons under Settings > Buttons.",
                        kind=t(buttons.KIND_NAMES[mode])))
        return
    # under the filters of the config the original playlist carries on as (each config's own, 2 Nov 2026)
    extra = list(buttons.continue_as(origin).get("filters") or []) if origin is not None else []
    options = {"topup": True} if mode == "artists" else {}
    buttons.run(button, report=report, seed_info=seed, extra_filters=extra, **options)


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
        report("  " + t("No more songs by {get} in your library, so moving on.", get=entry.get('top_artist')))
        return False
    random.shuffle(keys)
    if engine.NONSTOP_TOP_REST_COUNT:
        keys = keys[:engine.NONSTOP_TOP_REST_COUNT]
    report("  " + tn("Adding {count} more song by {artist}, shuffled.", "Adding {count} more songs by {artist}, shuffled.",
                     len(keys), artist=library.spoken(artist)))
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
            report("  " + t("Keep It Tight: reseeding from a track of the original playlist."))
            return engine.seed_from_row(row, zone)
    if not entry.get("tight_done"):
        entry["tight_done"] = True
        report("  " + t("Keep It Tight has used every track of the original playlist as a seed, so carrying on as Wander."))
    return None


def _job(zone, zone_name, info):
    def run(report):
        import buttons
        try:
            engine.refresh_settings_if_changed()
            engine.OUTPUT_OVERRIDE = zone_name
            engine.NONSTOP_APPEND = True
            engine.NONSTOP_CONTEXT = {}   # adding the rest of an artist isn't a new build
            with engine._nonstop_lock:
                entry = engine.NONSTOP_ZONES.get(zone)
            if not entry:
                return
            kind = entry.get("kind")
            origin = entry.get("origin") or kind
            if origin == "radio":   # never from Radio's own picks: from the lane's pillars, so it stays in the lane
                report("  " + t("{zone} is on its last track, so Radio plays on.", zone=zone_name))
                button = buttons.get(entry["button"]) if entry.get("button") else None
                if not buttons.is_radio(button):   # the playlist that started it has gone: Radio as shipped
                    button = next((b for b in buttons.load() if buttons.is_radio(b)), None) or \
                        buttons.ready_made_button("radio", {"artists": buttons.standard("artists")})
                buttons.run_radio(button, report=report, lane_id=entry.get("radio_lane"))
                return
            cfg = config_for(zone_name, entry)
            if origin == "saved":
                button = None
                cfg = {"using": "tracks", "reseed": "last", **cfg}
            else:
                button = origin_button(zone_name, entry)
                if button is not None:
                    button = buttons.continue_as(button)   # a mix carries on as the config its Mix says
            tight = (cfg.get("reseed") == "whole") if origin == "saved" else cfg.get("mode") == "tight"
            report("  " + (t("{zone} is on its last track, so adding more, with {button}.", zone=zone_name,
                             button=button["name"])
                           if button is not None and not button.get("standard")
                           else t("{zone} is on its last track, so adding more.", zone=zone_name)))
            if kind == "top" and entry.get("stage") == "first" and button is not None:
                entry["stage"] = "rest"
                # the rest of the artist's songs, as the button's Non-stop settings say (NONSTOP_TOP_REST)
                if buttons.run(button, report=report,
                               build=lambda report, **kw: engine.NONSTOP_TOP_REST and _rest_of_artist(zone, entry, info, report)):
                    return
            if kind == "top":
                entry["stage"] = "after"
                seed = (_tight_seed(zone, entry, report) if tight else None) or _top_seed(zone, entry, info)
                report("  " + t("Carrying on from {artist}, {name}.", artist=seed['Artist'], name=seed['Name']))
                _build(cfg["using"], seed, zone_name, button, report)
                return
            if origin == "vibe":
                if cfg.get("with") == "vibe" and entry.get("vibe") and button is not None:
                    report("  " + t("More of the same vibe: {vibe}", vibe=entry['vibe']))
                    buttons.run(button, report=report, theme=entry["vibe"])
                    return
                mode = cfg.get("with") if cfg.get("with") in ("artists", "tracks") else "artists"
            else:
                mode = cfg["using"]
            seed = _tight_seed(zone, entry, report) if tight else None
            if seed is None:
                seed = _second_track_seed(zone, info) if cfg.get("reseed") == "second" else dict(info, ZoneID=zone)
            report("  " + t("Reseeding from {artist}, {name}.", artist=seed['Artist'], name=seed['Name']))
            _build(mode, seed, zone_name, button, report)
        finally:
            engine.OUTPUT_OVERRIDE = None
            engine.NONSTOP_APPEND = False
    return run
