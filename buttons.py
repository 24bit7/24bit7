"""
24bit7 - playlists (buttons, in the code).

A playlist on the Play tab is a whole recipe: a kind of build (Artist Matching, Track
Matching, Artist's Top Tracks or AI Playlist), that kind's settings as .env strings (its
sources and its playlist settings, Drift, Deep Cuts, Non-stop and the rest), the filters
ticked for it, an optional keyboard shortcut, and whether it's shown on the Play tab. The
engine runs one by laying its settings over .env (engine.use_profile) under its filters.
Voice commands run the playlist a device names for the phrase (devices.py), Non-stop tops
a playlist up with the Non-stop settings of the playlist that built it, and a playlist's
shortcut runs it from the keyboard.

Playlists are kept as JSON in the database's meta table, in the order shown. The first load
with none makes the standard four from .env, so day one changes nothing, then Headliner. An
Alexa device with settings of its own gets a playlist for each kind whose values differ from
the main ones ("Kitchen Echo Similar Tracks"), kept off the Play tab, which that device's
phrases run. Filters that applied to all devices or to Windows (Main) are ticked on the
standard playlists; a filter that applied to one device only is ticked nowhere, and the
console says so once.
"""

import json
import uuid

from i18n import N_, t

import engine

META_KEY = "buttons"

KINDS = [("artists", N_("Similar Artists")), ("tracks", N_("Similar Tracks")),
         ("top", N_("Artist's Top Tracks")), ("vibe", N_("AI Playlist"))]
KIND_NAMES = dict(KINDS)   # the standard playlists' names, as they always were
# What each kind of build is called on a playlist's page and in the New Playlist window
KIND_LABELS = {"artists": N_("Artist Matching"), "tracks": N_("Track Matching"),
               "top": N_("Artist's Top Tracks"), "vibe": N_("AI Playlist")}
TEMPLATE = "template"   # New Playlist's "from": the kind's shipped defaults rather than one of your playlists

# The settings each kind carries. Every key under Settings > Sources and Playlist
# belongs to one kind, or stays in .env for every build (GLOBAL_KEYS); tests check that.
_EACH = ["IF_ALL_ELSE_FAILS_{G}", "IF_ALL_ELSE_FAILS_{G}_MODE", "IF_ALL_ELSE_FAILS_{G}_PATH",
         "IF_ALL_ELSE_FAILS_{G}_PLAYLIST", "IF_ALL_ELSE_FAILS_{G}_PLAYLIST_NAME",
         "SKIP_PLAYED_{G}", "SKIP_PLAYED_{G}_DAYS", "SKIP_LONG_CLOSERS_{G}", "LONG_CLOSER_MINUTES_{G}",
         "NONSTOP_{G}", "NONSTOP_{G}_RESEED", "NONSTOP_{G}_MODE", "RUN_AFTER_{G}", "RUN_AFTER_{G}_PATH"]
_DRIFT = ["DRIFT_{G}", "DRIFT_{G}_USING", "DRIFT_{G}_ROUNDS", "DRIFT_{G}_FROM", "DRIFT_{G}_MODERATOR",
          "DRIFT_{G}_SOURCES_MODE", "DRIFT_{G}_ARTIST_SOURCES", "DRIFT_{G}_ARTIST_AGREE",
          "DRIFT_{G}_TRACK_SOURCES", "DRIFT_{G}_TRACK_AGREE", "DEEP_CUTS_{G}", "DEEP_CUTS_{G}_SHARE"]
_OWN = {
    "artists": ["SIMILAR_SOURCES", "SIMILAR_MIN_AGREEMENT", "LISTENBRAINZ_ALGORITHM", "AI_MODERATOR_ARTISTS",
                "SIMILAR_ARTIST_TRACK_COUNT", "SIMILAR_ARTIST_TRACK_LIMIT", "SIMILAR_ARTIST_LIMIT",
                "TRACKS_PER_ARTIST_POOL", "TRACKS_PER_ARTIST_PICK", "NONSTOP_ARTISTS_USING"],
    "tracks": ["SIMILAR_TRACK_SOURCES", "SIMILAR_TRACK_MIN_AGREEMENT", "LISTENBRAINZ_TRACK_ALGORITHM",
               "AI_MODERATOR_TRACKS", "SIMILAR_TRACK_COUNT", "SIMILAR_TRACK_PER_ARTIST", "SIMILAR_TRACK_ORDER",
               "SIMILAR_TRACK_VARIETY", "NONSTOP_TRACKS_USING"],
    "top": ["TOP_TRACK_SOURCES", "TOP_TRACKS_COUNT", "TOP_TRACKS_ORDER", "TOP_GUESTS", "NONSTOP_TOP_USING",
            "NONSTOP_TOP_REST", "NONSTOP_TOP_REST_COUNT"],
    "vibe": ["VIBE_TRACK_COUNT", "VIBE_PER_ARTIST", "AI_MODERATOR_VIBE", "NONSTOP_VIBE_WITH"],
}
KIND_KEYS = {kind: _OWN[kind] + [k.format(G=kind.upper()) for k in _EACH + (_DRIFT if kind != "top" else [])]
             for kind, _ in KINDS}
# Older single settings that every kind started from, and one that covers every kind: not a button's
GLOBAL_KEYS = ["AI_MODERATOR", "NONSTOP", "NONSTOP_USING", "NONSTOP_RESEED", "NONSTOP_VIBE",
               "SKIP_LONG_CLOSERS", "LONG_CLOSER_MINUTES", "FALLBACK_SPOKEN"]

# Which engine build each kind runs
BUILDERS = {"artists": "create_similar_playlist", "tracks": "create_similar_tracks_playlist",
            "top": "play_top_n", "vibe": "create_vibe_playlist"}


def blank(name, kind):
    return {"id": uuid.uuid4().hex[:8], "name": name, "kind": kind, "settings": {}, "filters": [],
            "shortcut": "", "standard": "", "shown": True}


def tidy(item):
    kind = item.get("kind") if item.get("kind") in KIND_NAMES else "artists"
    out = blank(str(item.get("name") or t("Button")), kind)
    out.update({k: v for k, v in item.items() if k in out})
    out["settings"] = {str(k): str(v) for k, v in (out.get("settings") or {}).items() if k in KIND_KEYS[kind]}
    out["filters"] = [str(f) for f in (out.get("filters") or [])]
    out["shown"] = bool(out.get("shown", True))
    return out


def _stored():
    """The saved list, or None when buttons have never been saved (the upgrade hasn't run)."""
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    try:
        items = json.loads(row[0])
    except ValueError:
        return []
    return [tidy(x) for x in items if isinstance(x, dict)]


def load():
    """Every button, in the order shown. The first call ever makes them from today's settings."""
    items = _stored()
    if items is None:
        upgrade()
        items = _stored() or []
    return _adopt_env_shortcuts(items)


def save(items):
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (META_KEY, json.dumps([tidy(x) for x in items])))
    con.commit()


def get(button_id):
    return next((b for b in load() if b["id"] == button_id), None)


def of_kind(kind):
    return [b for b in load() if b["kind"] == kind]


def standard(kind):
    """The standard playlist of a kind (the one made at the upgrade), else the first of that kind, else None."""
    items = of_kind(kind)
    return next((b for b in items if b.get("standard") == kind), items[0] if items else None)


def has_kind(button, kind):
    """Whether a playlist builds this kind (its config's kind; a playlist with several configs, any of them)."""
    return button.get("kind") == kind


def shown():
    """The playlists ticked for the Play tab, in the order shown."""
    return [b for b in load() if b.get("shown", True)]


def set_shown(button_id, on):
    """The tick beside a playlist under Settings > Playlists: on the Play tab, or kept for voice and shortcuts only."""
    items = load()
    for b in items:
        if b["id"] == button_id:
            b["shown"] = bool(on)
    save(items)


# --- the Play tab's + and right-click ---------------------------------------------------------

def add(name, kind, from_id=None):
    """
    A new playlist at the end of the list, ticked, with the settings and filters of the one it starts
    from: one of yours by id, the standard one of its kind by default, or the kind's shipped defaults
    (from_id TEMPLATE).
    """
    items = load()
    new = blank(name.strip() or t(KIND_LABELS[kind]), kind)
    if from_id == TEMPLATE:
        new["settings"] = template_settings(kind)
    else:
        source = next((b for b in items if b["id"] == from_id and b["kind"] == kind), None) or standard(kind)
        if source:
            new["settings"], new["filters"] = dict(source["settings"]), list(source["filters"])
    save(items + [new])
    return new


def template_settings(kind):
    """A kind's settings as 24bit7 ships them: every key at its default."""
    return settings_from(lambda key, default=None: default, kind)


def unique_name(base):
    """base, or "base 2", "base 3"... the first not already a playlist's name."""
    names = {b["name"] for b in load()}
    if base not in names:
        return base
    n = 2
    while f"{base} {n}" in names:
        n += 1
    return f"{base} {n}"


def rename(button_id, name):
    items = load()
    for b in items:
        if b["id"] == button_id and name.strip():
            b["name"] = name.strip()
    save(items)


def move(button_id, by):
    """Moves a button along the row: by -1 is one place left, +1 one place right."""
    items = load()
    ids = [b["id"] for b in items]
    if button_id not in ids:
        return
    i = ids.index(button_id)
    j = min(max(i + by, 0), len(items) - 1)
    items.insert(j, items.pop(i))
    save(items)


def remove(button_id):
    save([b for b in load() if b["id"] != button_id])


def move_shown(button_id, by):
    """Moves a playlist along the Play tab's row: by -1 one place left, +1 one place right, past hidden ones."""
    items = load()
    row = [b["id"] for b in items if b.get("shown", True)]
    if button_id not in row:
        return
    i = row.index(button_id)
    j = i + by
    if j < 0 or j >= len(row):
        return
    moving = next(b for b in items if b["id"] == button_id)
    items.remove(moving)
    anchor = next(k for k, b in enumerate(items) if b["id"] == row[j])
    items.insert(anchor + (1 if by > 0 else 0), moving)
    save(items)


def move_to(button_id, before_id):
    """Drops a playlist in front of another on the Play tab's row (before_id None: at the end)."""
    items = load()
    moving = next((b for b in items if b["id"] == button_id), None)
    if moving is None or button_id == before_id:
        return
    items.remove(moving)
    if before_id is None:
        items.append(moving)
    else:
        anchor = next((k for k, b in enumerate(items) if b["id"] == before_id), len(items))
        items.insert(anchor, moving)
    save(items)


def duplicate(button_id):
    """A copy of a playlist, named "<name> 2" (or the next free number), ticked, right after it on the row."""
    source = get(button_id)
    if source is None:
        return None
    new = add(unique_name(source["name"]), source["kind"], button_id)
    items = load()
    moving = next(b for b in items if b["id"] == new["id"])
    items.remove(moving)
    items.insert(next(k for k, b in enumerate(items) if b["id"] == button_id) + 1, moving)
    save(items)
    return get(new["id"])


def set_settings(button_id, settings):
    """Settings > Buttons saved a button's page: only its kind's keys are kept."""
    items = load()
    for b in items:
        if b["id"] == button_id:
            b["settings"] = {str(k): str(v) for k, v in settings.items() if k in KIND_KEYS[b["kind"]]}
    save(items)


def set_filters(button_id, ids):
    """The filters ticked on a button's page, in the order shown."""
    items = load()
    for b in items:
        if b["id"] == button_id:
            b["filters"] = [str(i) for i in ids]
    save(items)


def set_shortcut(button_id, combo):
    """The keyboard shortcut set on a button's page ('Ctrl+Alt+1', or blank for none)."""
    items = load()
    for b in items:
        if b["id"] == button_id:
            b["shortcut"] = (combo or "").strip()
    save(items)


def with_shortcuts():
    """The buttons with a shortcut set, in the order shown."""
    return [b for b in load() if b.get("shortcut")]


def nonstop_config(button):
    """
    Non-stop as a button has it, its settings over .env: {"on", "using", "reseed", "mode"},
    plus "with" for an AI Playlist. A playlist is topped up as the button that built it says.
    """
    merged = dict(_env_values(), **(button.get("settings") or {}))
    return engine.nonstop_settings(lambda name, default="": merged.get(name, default))[button["kind"]]


# The three build shortcuts lived in .env before buttons (Settings > Other > Keyboard Shortcuts)
OLD_SHORTCUT_KEYS = {"HOTKEY_SIMILAR_TRACKS": "tracks", "HOTKEY_SIMILAR_ARTISTS": "artists", "HOTKEY_TOP_TRACKS": "top"}


def _adopt_env_shortcuts(items):
    """Each old build shortcut moves onto the standard button of its kind, once, and leaves .env."""
    import os
    present = [k for k in OLD_SHORTCUT_KEYS if os.environ.get(k) is not None]
    if not present:
        return items
    for key in present:
        combo = os.environ.get(key, "").strip()
        b = next((x for x in items if x.get("standard") == OLD_SHORTCUT_KEYS[key]), None)
        if combo and b is not None and not b.get("shortcut"):
            b["shortcut"] = combo
    save(items)
    _drop_env_keys(present)
    for key in present:
        os.environ.pop(key, None)
    return items


def _drop_env_keys(keys):
    """Removes keys from .env, keeping every other line as it is."""
    try:
        with open(engine.ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return
    kept = [line for line in lines
            if not ("=" in line and not line.lstrip().startswith("#") and line.split("=", 1)[0].strip() in keys)]
    if kept != lines:
        with open(engine.ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))


def needs_track(button):
    """Whether a Similar Artists button needs the track typed too (YouTube its only source), under its own settings."""
    if button["kind"] == "tracks":
        return True
    if button["kind"] != "artists":
        return False
    previous = dict(engine.PROFILE)
    engine.use_profile(dict(button.get("settings") or {}, **previous))
    try:
        return bool(engine.similar_needs_track())
    finally:
        engine.use_profile(previous or None)


# --- settings ---------------------------------------------------------------------------------

def settings_from(get_value, kind):
    """
    One kind's settings from a getter (os.getenv, or a dict's get), as .env strings. The
    older single settings (NONSTOP, SKIP_LONG_CLOSERS, AI_MODERATOR) are resolved into
    the kind's own keys, so a button stands on its own without them.
    """
    out = {}
    for key in KIND_KEYS[kind]:
        value = get_value(key)
        if value is not None and str(value).strip() != "":
            out[key] = str(value).strip()
    g = kind.upper()

    def getter(name, default=""):
        value = get_value(name)
        return default if value is None else str(value)
    ns = engine.nonstop_settings(getter)[kind]
    out[f"NONSTOP_{g}"] = "1" if ns["on"] else "0"
    out[f"NONSTOP_{g}_RESEED"] = ns["reseed"]
    out[f"NONSTOP_{g}_MODE"] = ns["mode"]
    if kind == "vibe":
        out["NONSTOP_VIBE_WITH"] = ns["with"]
    else:
        out[f"NONSTOP_{g}_USING"] = ns["using"]
    on, minutes = engine.closer_settings(getter)[kind]
    out[f"SKIP_LONG_CLOSERS_{g}"] = "1" if on else "0"
    out[f"LONG_CLOSER_MINUTES_{g}"] = str(minutes)
    if kind in engine.MODERATOR_GROUPS:
        out[f"AI_MODERATOR_{g}"] = engine.moderator_settings(getter)[kind]
    return out


def _env_values():
    """.env as it stands (not os.environ, which a running build may have laid a profile over)."""
    from dotenv import dotenv_values
    try:
        return {k: (v or "") for k, v in dotenv_values(engine.ENV_FILE).items()}
    except Exception:
        return {}


def standard_buttons(env=None):
    """The four standard buttons as .env has them: what a user had before buttons."""
    env = _env_values() if env is None else env
    out = []
    for kind, name in KINDS:
        b = blank(t(name), kind)
        b["settings"], b["standard"] = settings_from(env.get, kind), kind
        out.append(b)
    return out


def headliner_button(top):
    """Headliner: the standard Artist's Top Tracks with Guests on."""
    b = blank(t("Headliner"), "top")
    b["settings"] = dict(top["settings"], TOP_GUESTS="third")
    b["filters"] = list(top["filters"])
    return b


def restore_standard():
    """Restore Default Buttons: puts back any of the standard four that's gone, after the rest."""
    items = load()
    have = {b.get("standard") for b in items}
    missing = [b for b in standard_buttons() if b["standard"] not in have]
    if missing:
        save(items + missing)
    return missing


# --- the upgrade from Settings > Sources and Playlist ------------------------------------------

_OLD_ALL, _OLD_MAIN = "all", "main"   # a filter's old Applies on list: every device, and Windows (Main)


def _old_devices():
    """
    Alexa devices as they were before buttons: [(device_id, name, zone, own settings, had own
    JRiver Playlists settings)] for those with Own settings ticked, read straight from the
    voice_devices table's own_settings, sources, playlist and saved columns, which nothing else
    reads now.
    """
    try:
        con = engine.db()
        columns = {row[1] for row in con.execute("PRAGMA table_info(voice_devices)")}
        if not {"own_settings", "sources", "playlist"} <= columns:
            return []
        saved = "saved" if "saved" in columns else "NULL"
        rows = con.execute(f"SELECT device_id, name, zone, sources, playlist, {saved} FROM voice_devices "
                           "WHERE COALESCE(own_settings, 0) = 1").fetchall()
    except Exception:
        return []
    out = []
    for device_id, name, zone, sources, playlist, saved_own in rows:
        own = {}
        for raw in (sources, playlist):
            try:
                own.update(json.loads(raw) if raw else {})
            except ValueError:
                pass
        out.append((device_id, name, zone, own, bool(saved_own)))
    return out


def upgrade():
    """
    The first run with playlists: the standard four from .env, Headliner, then a playlist per
    kind an Alexa device with its own settings changed, which that device's phrases run and
    which stays off the Play tab. Filters for all devices or Windows (Main) go on the standard
    playlists; a device-only filter goes nowhere, said once. Runs once: saving an empty list
    counts as done.
    """
    import filters
    env = _env_values()
    items = standard_buttons(env)
    by_kind = {b["kind"]: b for b in items}
    items.insert(items.index(by_kind["vibe"]), headliner_button(by_kind["top"]))   # before AI Playlist (Ben, 30 Oct)
    all_filters = filters.stored_raw()   # with their old Applies on lists
    shared = [f["id"] for f in all_filters
              if _OLD_ALL in f.get("devices", []) or _OLD_MAIN in f.get("devices", [])]
    for b in items:
        b["filters"] = list(shared)

    import devices
    device_data = devices.load_raw()
    for device_id, name, zone, profile, saved_own in _old_devices():
        shown_name = name or t("Device")
        if saved_own:
            engine.print(t("Note: {name}'s own JRiver Playlists settings are no longer used; every device follows "
                           "Settings > JRiver Playlists.", name=shown_name))
        for f in all_filters:
            if device_id in f.get("devices", []) and f["id"] not in shared:
                engine.print(t("Note: the filter {filter} applied to {name} only. Filters belong to playlists now: "
                               "tick it on a playlist under Settings > Playlists if you still want it.",
                               filter=f.get("name", ""), name=shown_name))
        if not profile:
            continue
        record = device_data.setdefault(device_id, devices.blank())
        merged = dict(env, **profile)
        made = []
        for kind, label in KINDS:
            own_settings = settings_from(merged.get, kind)
            if own_settings == by_kind[kind]["settings"]:
                continue
            b = blank(f"{shown_name} {t(label)}", kind)
            b["settings"], b["filters"], b["shown"] = own_settings, list(shared), False
            items.append(b)
            made.append(b)
            for phrase, phrase_kind in devices.PHRASE_KINDS.items():
                if phrase_kind == kind:
                    record["buttons"][phrase] = b["id"]
        if made:
            engine.print(t("Note: {name} had settings of its own. They're now playlists of its own under Settings > "
                           "Playlists ({names}), which its voice commands run; they're kept off the Play tab.",
                           name=shown_name, names=", ".join(x["name"] for x in made)))
    save(items)
    devices.save(device_data)


# --- running one ------------------------------------------------------------------------------

def run(button, report=print, seed_info=None, build=None, extra_filters=(), **options):
    """
    Builds a playlist: its settings laid over .env, under its filters. Extra options go to
    the engine's build (AI Playlist's theme and count). A profile already in use (Review
    Mode's column) stays on top and comes back afterwards. build: another engine call to run
    under the playlist in place of its kind's (voice's "only", a Non-stop top-up's steps,
    Blend's search); it gets report=, seed_info= and the options. extra_filters: more filter
    ids (a top-up keeps the filters of the playlist that built the music). The playlist is
    remembered with what it sends, for Non-stop.
    """
    ids = list(button.get("filters") or [])
    ids += [i for i in extra_filters if i not in ids]
    previous = dict(engine.PROFILE)
    before = engine.BUILD_BUTTON
    engine.use_profile(dict(button.get("settings") or {}, **previous))
    engine.FILTER_IDS = ids
    engine.BUILD_BUTTON = button["id"]
    try:
        if build is not None:
            return build(report=report, seed_info=seed_info, **options)
        builder = getattr(engine, BUILDERS[button["kind"]])
        if button["kind"] == "vibe":
            return builder(options.pop("theme", ""), report=report, **options)
        return builder(report=report, seed_info=seed_info, **options)
    finally:
        engine.FILTER_IDS = None
        engine.BUILD_BUTTON = before
        engine.use_profile(previous or None)


def describe(button):
    """A short line for a hover note: the kind, then what's on."""
    s = button.get("settings") or {}
    g = button["kind"].upper()
    bits = [t(KIND_LABELS[button["kind"]])]
    if button["kind"] == "top" and s.get("TOP_GUESTS") == "third":
        bits.append(t("Guests"))
    if s.get(f"DRIFT_{g}", "0") in engine.YES:
        bits.append("Drift")
    if s.get(f"DEEP_CUTS_{g}", "off") not in ("off", ""):
        bits.append("Deep Cuts")
    if s.get(f"NONSTOP_{g}", "0") in engine.YES:
        bits.append("Non-stop")
    if button.get("filters"):
        bits.append(t("Filters"))
    return ", ".join(bits)
