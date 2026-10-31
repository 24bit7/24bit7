"""
24bit7 - devices.

Per Alexa device (Settings > Devices): which playlist each voice phrase runs there. A
device plays to a JRiver zone (its row under Settings > Devices), and besides that zone
these choices are all a device holds: filters and Non-stop belong to the playlists.

Kept as JSON in the database's meta table, keyed by device id. A device with no record, or
a phrase left unset, runs the standard playlist of that phrase's kind.
"""

import json

from i18n import N_

import engine

META_KEY = "devices"

# Voice phrases, the kind of build each one stands for, and the Alexa intents that mean it
PHRASES = [("music_like", N_("Music like")), ("songs_by", N_("Songs by")),
           ("tracks_like", N_("Tracks like this")), ("play_something", N_("Play something"))]
PHRASE_KINDS = {"music_like": "artists", "songs_by": "top", "tracks_like": "tracks", "play_something": "vibe"}
INTENT_PHRASES = {"music_like": "music_like", "more_artists": "music_like", "songs_by": "songs_by",
                  "tracks_like": "tracks_like", "more_like": "tracks_like",
                  "genre": "play_something", "only": "play_something"}


def blank():
    return {"buttons": {phrase: None for phrase, _ in PHRASES}}


def tidy(item):
    out = blank()
    out["buttons"] = {phrase: (str(v) if v else None) for phrase, v in (item.get("buttons") or {}).items()
                      if phrase in PHRASE_KINDS}
    for phrase in PHRASE_KINDS:
        out["buttons"].setdefault(phrase, None)
    return out


def load_raw():
    """{device id: record} as saved, without running the playlists upgrade."""
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
        data = json.loads(row[0]) if row and row[0] else {}
    except Exception:
        data = {}
    return {str(k): tidy(v) for k, v in data.items() if isinstance(v, dict)}


def load():
    """{device id: record}. The first call ever runs the playlists upgrade, which fills in the devices' choices."""
    import buttons
    buttons.load()
    return load_raw()


def save(data):
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (META_KEY, json.dumps({str(k): tidy(v) for k, v in data.items()})))
    con.commit()


def for_device(device_id):
    return load().get(str(device_id)) or blank()


def update(device_id, **fields):
    data = load()
    record = data.get(str(device_id)) or blank()
    record.update(fields)
    data[str(device_id)] = record
    save(data)
    return record


def forget(device_id):
    """A device removed under Settings > Devices takes its choices with it."""
    data = load()
    if str(device_id) in data:
        del data[str(device_id)]
        save(data)


def playlist_for(device_id, phrase):
    """The playlist a voice phrase runs on a device: its choice if it still exists and fits, else the standard one."""
    import buttons
    phrase = INTENT_PHRASES.get(phrase, phrase)
    kind = PHRASE_KINDS.get(phrase)
    if kind is None:
        return None
    chosen = for_device(device_id)["buttons"].get(phrase) if device_id else None
    button = buttons.get(chosen) if chosen else None
    return button if button and buttons.has_kind(button, kind) else buttons.standard(kind)


def used_by(button_id):
    """[device ids] with this playlist chosen for any phrase."""
    return [device_id for device_id, record in load().items() if button_id in record["buttons"].values()]
