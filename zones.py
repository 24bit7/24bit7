"""
24bit7 - zones.

Per JRiver zone (Settings > Zones): which button each voice phrase runs there, the
zone's filters (applied to anything 24bit7 sends to that zone, from Alexa, a keyboard
shortcut or the Play tab), and whether Non-stop may top up playlists in it. An Alexa
device plays to a zone (Settings > Voice), so a device has no settings of its own.

Kept as JSON in the database's meta table, keyed by zone name. A zone with no record,
or a phrase left unset, uses the standard button of that phrase's kind.
"""

import json

from i18n import N_

import engine

META_KEY = "zones"

# Voice phrases, the kind of build each one stands for, and the Alexa intents that mean it
PHRASES = [("music_like", N_("Music like")), ("songs_by", N_("Songs by")),
           ("tracks_like", N_("Tracks like this")), ("play_something", N_("Play something"))]
PHRASE_KINDS = {"music_like": "artists", "songs_by": "top", "tracks_like": "tracks", "play_something": "vibe"}
INTENT_PHRASES = {"music_like": "music_like", "more_artists": "music_like", "songs_by": "songs_by",
                  "tracks_like": "tracks_like", "more_like": "tracks_like",
                  "genre": "play_something", "only": "play_something"}


def blank(name):
    return {"name": name, "buttons": {phrase: None for phrase, _ in PHRASES}, "filters": [], "nonstop": True}


def tidy(item):
    out = blank(str(item.get("name") or ""))
    out.update({k: v for k, v in item.items() if k in out})
    out["buttons"] = {phrase: (str(v) if v else None) for phrase, v in (out.get("buttons") or {}).items()
                      if phrase in PHRASE_KINDS}
    for phrase in PHRASE_KINDS:
        out["buttons"].setdefault(phrase, None)
    out["filters"] = [str(f) for f in (out.get("filters") or [])]
    out["nonstop"] = bool(out.get("nonstop", True))
    return out


def load_raw():
    """{zone name: record} as saved, without running the buttons upgrade."""
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
        data = json.loads(row[0]) if row and row[0] else {}
    except Exception:
        data = {}
    return {name: tidy(dict(item, name=name)) for name, item in data.items() if isinstance(item, dict)}


def load():
    """{zone name: record}. The first call ever runs the buttons upgrade, which fills in the devices' zones."""
    import buttons
    buttons.load()
    return load_raw()


def save(data):
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (META_KEY, json.dumps({name: tidy(dict(item, name=name)) for name, item in data.items()})))
    con.commit()


def for_zone(name):
    return load().get(name) or blank(name)


def update(name, **fields):
    data = load()
    record = data.get(name) or blank(name)
    record.update(fields)
    data[name] = record
    save(data)
    return record


def filter_ids(zone_name):
    """The zone's filters, for a build whose playlist goes there."""
    if not zone_name:
        return []
    return list(for_zone(zone_name)["filters"])


def nonstop_on(zone_name):
    """Whether Non-stop may top up playlists in this zone (the how is each button's)."""
    return bool(for_zone(zone_name)["nonstop"]) if zone_name else True


def button_for(zone_name, phrase):
    """The button a voice phrase runs in a zone: the zone's choice if it still exists, else the standard one."""
    import buttons
    phrase = INTENT_PHRASES.get(phrase, phrase)
    kind = PHRASE_KINDS.get(phrase)
    if kind is None:
        return None
    chosen = for_zone(zone_name)["buttons"].get(phrase) if zone_name else None
    button = buttons.get(chosen) if chosen else None
    return button if button and button["kind"] == kind else buttons.standard(kind)
