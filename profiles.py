"""
profiles.py - saved sets of settings for different ways of listening (Settings > Other > Profiles).

A profile holds Windows (Main)'s listening settings: the Play tab options, Sources,
Playlist settings, Filters, the JRiver Playlists rows, the Play tab's Add Playlist rows,
the Preview zone, cache length and the console. It leaves out anything tied to the PC
or the person: keys, the JRiver connection, Alexa devices (those with Own Settings keep
theirs), keyboard shortcuts, the tray, the title bar, the theme and Discover's sites.

Each profile is a small JSON file in the profiles folder beside 24bit7, so profiles
survive updates and can be copied to another PC. Loading writes the profile as
"pending" and restarts 24bit7; the new copy applies it before anything reads a setting,
so nothing from the old copy can save over it on the way out.
"""
import json
import os
import re

import engine

PROFILE_DIR = os.path.join(engine.APP_DIR, "profiles")
PENDING = os.path.join(PROFILE_DIR, "_pending.json")
CURRENT_KEY = "PROFILE_CURRENT"   # in .env: the profile last loaded or saved
SWITCH_OFF_KEY = "PROFILE_SWITCH_OFF"   # in .env: profiles unticked under Enable Switch To (new ones start ticked)

# .env settings beyond Settings > Sources and Playlist (engine.PROFILE_KEYS)
EXTRA_ENV_KEYS = ["PLAY_BEHAVIOUR", "OUTPUT_TARGET", "YOUTUBE_PLAYLIST_LENGTH", "PREFER_OFFICIAL_VIDEOS",
                  "REVIEW_PREVIEW_ZONE", "CACHE_KEEP", "CONSOLE_MODE", "CONSOLE_QUERY", "USE_AI",
                  "CREDITS_SCOPE", "CREDITS_FIRST",   # Settings > Other > Show Credits
                  # the AI Playlist window's choices (a DJ profile can open on Steer with its usual chips)
                  "AI_DIALOG_MODE", "AI_CREATE_THEME", "AI_IF_SHORT", "AI_STEER_SEED", "AI_STEER_TONE",
                  "AI_STEER_DIRS", "AI_STEER_OWN", "AI_STEER_STRENGTH", "AI_STEER_COUNT",
                  # Settings > Playlist's Review column
                  "REVIEW_SAME_ARTISTS", "REVIEW_SAME_TRACKS", "REVIEW_SAME_TOP",
                  "REVIEW_SIMILAR_ARTIST_TRACK_COUNT", "REVIEW_SIMILAR_ARTIST_TRACK_LIMIT",
                  "REVIEW_SIMILAR_ARTIST_LIMIT", "REVIEW_TRACKS_PER_ARTIST_POOL", "REVIEW_TRACKS_PER_ARTIST_PICK",
                  "REVIEW_SIMILAR_TRACK_COUNT", "REVIEW_TOP_TRACKS_COUNT"]
# kept in the database's meta table: Filters, JRiver Playlists (Windows Main), Add Playlist rows
META_KEYS = ["filters", "saved_playlists", "play_mix"]


def env_keys():
    keys = []
    for k in engine.PROFILE_KEYS["sources"] + engine.PROFILE_KEYS["playlist"] + EXTRA_ENV_KEYS:
        if k not in keys:
            keys.append(k)
    return keys


def _read_env():
    from settings_gui import read_env   # the same reader write_env pairs with
    return read_env()


def _write_env(updates):
    from settings_gui import write_env   # here rather than at the top: settings_gui is the GUI
    write_env(updates)


def snapshot():
    """The current settings a profile holds. A setting that isn't set is None (its default)."""
    env = _read_env()
    data = {"env": {k: env.get(k) for k in env_keys()}, "meta": {}}
    con = engine.db()
    for key in META_KEYS:
        row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        data["meta"][key] = row[0] if row else None
    return data


def _path(name):
    safe = re.sub(r"[^\w\- ]+", "", name).strip() or "Profile"
    return os.path.join(PROFILE_DIR, f"{safe}.json")


def names():
    """Saved profiles by name, A to Z."""
    out = []
    try:
        files = os.listdir(PROFILE_DIR)
    except OSError:
        return []
    for f in files:
        if f.endswith(".json") and not f.startswith("_"):
            try:
                with open(os.path.join(PROFILE_DIR, f), encoding="utf-8") as fh:
                    out.append(json.load(fh).get("name") or f[:-5])
            except (OSError, ValueError):
                continue
    return sorted(out, key=str.lower)


def read(name):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def exists(name):
    return os.path.isfile(_path(name))


def current():
    """The profile last loaded or saved, if its file is still there."""
    name = (_read_env().get(CURRENT_KEY) or "").strip()
    return name if name and exists(name) else ""


def changed(name=None):
    """True when the settings no longer match the profile (the current one by default)."""
    name = name or current()
    saved = read(name) if name else None
    if not saved:
        return True
    now = snapshot()
    return now["env"] != saved.get("env") or now["meta"] != saved.get("meta")


def save(name):
    """Saves the current settings as a profile (replacing one of that name) and makes it current."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    data = snapshot()
    data["name"] = name
    data["version"] = engine.VERSION
    with open(_path(name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    _write_env({CURRENT_KEY: name})


def delete(name):
    try:
        os.remove(_path(name))
    except OSError:
        pass
    if (_read_env().get(CURRENT_KEY) or "").strip() == name:
        _write_env({CURRENT_KEY: None})
    if name in _switch_off():
        set_in_switch(name, True)   # forget it from the unticked list too


# --- Switch Profiles: the keyboard shortcut steps through the ticked profiles ----------------

def _switch_off():
    return [n for n in (_read_env().get(SWITCH_OFF_KEY) or "").split("|") if n]


def in_switch(name):
    return name not in _switch_off()


def set_in_switch(name, on):
    off = [n for n in _switch_off() if n != name] + ([] if on else [name])
    _write_env({SWITCH_OFF_KEY: "|".join(off) or None})


def switch_names():
    """The profiles ticked under Enable Switch To, A to Z."""
    off = set(_switch_off())
    return [n for n in names() if n not in off]


def switch_target():
    """(the profile Switch Profiles loads next, None) or (None, why there isn't one)."""
    ticked = switch_names()
    if not ticked:
        return None, "no profiles are ticked under Enable Switch To (Settings > Other > Profiles)."
    cur = current()
    others = [n for n in ticked if n != cur]
    if not others:
        return None, (f'"{cur}" is the only profile ticked under Enable Switch To, so there\'s nothing to '
                      "switch to. Tick another in Settings > Other > Profiles.")
    after = [n for n in others if n.lower() > cur.lower()] if cur else []
    return (after or others)[0], None


def queue_load(name):
    """Marks a profile to be applied when 24bit7 next starts (Load then restarts it)."""
    data = read(name)
    if not data:
        raise RuntimeError(f'the profile "{name}" couldn\'t be read')
    data["name"] = name
    os.makedirs(PROFILE_DIR, exist_ok=True)
    with open(PENDING, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def apply(data):
    """Writes a profile's settings into .env, the running settings and the database."""
    env = {k: v for k, v in (data.get("env") or {}).items() if k in env_keys()}
    updates = dict(env)   # None: not set, so the default applies; anything else as saved
    updates[CURRENT_KEY] = data.get("name") or None
    _write_env(updates)
    for k, v in updates.items():   # this copy has already read .env: bring it up to date
        if v is None:
            os.environ.pop(k, None)
            continue
        os.environ[k] = str(v)
    con = engine.db()
    for key, value in (data.get("meta") or {}).items():
        if key not in META_KEYS:
            continue
        if value is None:
            con.execute("DELETE FROM meta WHERE key=?", (key,))
        else:
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    con.commit()
    engine.load_settings()


def apply_pending():
    """At start-up: applies a profile chosen with Load, then forgets it. Returns its name, or ''."""
    if not os.path.isfile(PENDING):
        return ""
    try:
        with open(PENDING, encoding="utf-8") as fh:
            data = json.load(fh)
        apply(data)
        return data.get("name") or ""
    except Exception as e:
        print(f"Problem: the profile couldn't be loaded ({e}).")
        return ""
    finally:
        try:
            os.remove(PENDING)
        except OSError:
            pass
