"""
24bit7 - devices.
Per Alexa device (the Device Playlists box under Settings > Playlist Settings): which playlist
each voice phrase runs there. The phrases are the slots: Music like, Songs by, Tracks like this
and Genre. A slot runs the standard playlist of its kind until the device is given its own
(make_own), a playlist marked with the device's id that lives in the box, not on the Play tab;
reset puts a slot back to the standard. A device also plays to a JRiver zone (voice's table).
Kept as JSON in the database's meta table, keyed by device id.
"""

import json

from i18n import N_, t

import engine

META_KEY = "devices"

# Voice phrases, the kind of build each one stands for, and the Alexa intents that mean it
PHRASES = [("music_like", N_("Music like")), ("songs_by", N_("Songs by")),
           ("tracks_like", N_("Tracks like this")), ("play_something", N_("Genre"))]   # as spoken (2 Nov 2026)
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
    """A device removed takes its choices and its own playlists with it."""
    import buttons
    for b in buttons.of_device(device_id):
        buttons.remove(b["id"])
    data = load()
    if str(device_id) in data:
        del data[str(device_id)]
        save(data)


def name_of(device_id):
    """The device's name as voice's table has it, or 'Device'."""
    import voice
    return next((name for did, name, _zone, _heard in voice.devices() if did == str(device_id)), None) or t("Device")


def rows(device_id):
    """
    The Device Playlists box's rows: [(phrase, label, playlist, own)], the playlist each phrase runs,
    own when it's the device's own (else the standard playlist of the phrase's kind, shown greyed).
    """
    import buttons
    record = for_device(device_id)
    out = []
    for phrase, label in PHRASES:
        chosen = record["buttons"].get(phrase)
        b = buttons.get(chosen) if chosen else None
        own = b is not None and b.get("device") == str(device_id)
        if b is None or not (own or buttons.has_kind(b, PHRASE_KINDS[phrase])):
            b, own = buttons.standard(PHRASE_KINDS[phrase]), False
        out.append((phrase, label, b, own))
    return out


def make_own(device_id, phrase, source=("standard", None)):
    """
    Gives a device its own playlist for a phrase, which lives in the Device Playlists box: a copy of
    the standard playlist of the phrase's kind ("standard", None), of any playlist ("copy", id), or a
    template ("template", key). Any kind goes: a phrase can run whatever the listener gives it.
    Returns the playlist.
    """
    import buttons
    kind = PHRASE_KINDS[phrase]
    how, what = source
    if how == "template":
        made, _wants_page = buttons.add_from_choice(("template", what))
    elif how == "copy":
        made = buttons.duplicate(what)
    else:
        made = buttons.add("", kind)
    data = load()
    record = data.get(str(device_id)) or blank()
    old = record["buttons"].get(phrase)
    previous = buttons.get(old) if old and old != made["id"] else None
    if previous is not None and previous.get("device") == str(device_id):
        buttons.remove(old)   # the slot's earlier own playlist goes, so the new one can take its name
    items = buttons.load()
    for b in items:
        if b["id"] == made["id"]:
            b["device"], b["parent"], b["default"] = str(device_id), "", ""
            b["name"] = buttons.unique_name(f"{name_of(device_id)} {t(buttons.KIND_NAMES[b['kind']])}")                 if b["kind"] is not None else buttons.unique_name(name_of(device_id))
        elif b.get("default") == made["id"]:
            b["default"] = ""
    buttons.save(items)
    record["buttons"][phrase] = made["id"]
    data[str(device_id)] = record
    save(data)
    return buttons.get(made["id"])


def reset(device_id, phrase):
    """A slot back to the standard playlist of its kind; the device's own playlist for it is deleted."""
    import buttons
    data = load()
    record = data.get(str(device_id)) or blank()
    chosen = record["buttons"].get(phrase)
    record["buttons"][phrase] = None
    data[str(device_id)] = record
    save(data)
    b = buttons.get(chosen) if chosen else None
    if b is not None and b.get("device") == str(device_id):
        buttons.remove(chosen)


def restore_defaults(device_id):
    """Restore Default Device Playlists: every slot back to the standard."""
    for phrase in PHRASE_KINDS:
        reset(device_id, phrase)


def playlist_for(device_id, phrase):
    """The playlist a voice phrase runs on a device: its choice if it still exists and fits, else the standard one."""
    import buttons
    phrase = INTENT_PHRASES.get(phrase, phrase)
    kind = PHRASE_KINDS.get(phrase)
    if kind is None:
        return None
    chosen = for_device(device_id)["buttons"].get(phrase) if device_id else None
    button = buttons.get(chosen) if chosen else None
    own = button is not None and button.get("device") == str(device_id)   # the device's own runs whatever kind it is
    return button if button and (own or buttons.has_kind(button, kind)) else buttons.standard(kind)


def used_by(button_id):
    """[device ids] with this playlist chosen for any phrase."""
    return [device_id for device_id, record in load().items() if button_id in record["buttons"].values()]
