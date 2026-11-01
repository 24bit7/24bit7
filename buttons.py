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
# How a playlist's configs come together (Mix), and what a plain playlist's mix looks like
COMBINES = [("shuffle", N_("Shuffle")), ("append", N_("Append")), ("alternate", N_("Alternate"))]


def mix_default():
    return {"combine": "shuffle", "pattern": [], "drift_from": 0, "continue_as": 0}


# The ready-made playlists, offered as templates and made at the upgrade: each starts from the standard
# playlist of its kind(s) with these settings laid on top. Headliner: the artist's top tracks, two at a
# time, with one track from a close similar artist between them (Ben, 30 Oct 2026, listening to Zero 7).
READY_MADE = [
    {"key": "headliner", "name": N_("Headliner"), "kind": "top", "settings": {},
     "configs": [("artists", {"SIMILAR_ARTIST_LIMIT": "5", "SIMILAR_ARTIST_TRACK_COUNT": "6", "TRACKS_PER_ARTIST_PICK": "1"})],
     "mix": {"combine": "alternate", "pattern": [2, 1], "drift_from": 1, "continue_as": 0}},
    {"key": "inner_circle", "name": N_("Inner Circle"), "kind": "artists",
     "settings": {"INNER_CIRCLE_ARTISTS": "1", "INNER_CIRCLE_ARTISTS_SIZE": "3", "INNER_CIRCLE_ARTISTS_AGREE": "2"},
     "configs": [], "mix": None},
]

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
                "TRACKS_PER_ARTIST_POOL", "TRACKS_PER_ARTIST_PICK", "NONSTOP_ARTISTS_USING",
                "INNER_CIRCLE_ARTISTS", "INNER_CIRCLE_ARTISTS_SIZE", "INNER_CIRCLE_ARTISTS_AGREE"],
    "tracks": ["SIMILAR_TRACK_SOURCES", "SIMILAR_TRACK_MIN_AGREEMENT", "LISTENBRAINZ_TRACK_ALGORITHM",
               "AI_MODERATOR_TRACKS", "SIMILAR_TRACK_COUNT", "SIMILAR_TRACK_PER_ARTIST", "SIMILAR_TRACK_ORDER",
               "SIMILAR_TRACK_VARIETY", "NONSTOP_TRACKS_USING",
               "INNER_CIRCLE_TRACKS", "INNER_CIRCLE_TRACKS_SIZE", "INNER_CIRCLE_TRACKS_AGREE"],
    "top": ["TOP_TRACK_SOURCES", "TOP_TRACKS_COUNT", "TOP_TRACKS_ORDER", "NONSTOP_TOP_USING",
            "NONSTOP_TOP_REST", "NONSTOP_TOP_REST_COUNT"],
    "vibe": ["VIBE_TRACK_COUNT", "VIBE_PER_ARTIST", "AI_MODERATOR_VIBE", "NONSTOP_VIBE_WITH"],
}
KIND_KEYS = {kind: _OWN[kind] + [k.format(G=kind.upper()) for k in _EACH + (_DRIFT if kind != "top" else [])]
             for kind, _ in KINDS}
# Older single settings that every kind started from, and one that covers every kind: not a button's
GLOBAL_KEYS = ["AI_MODERATOR", "NONSTOP", "NONSTOP_USING", "NONSTOP_RESEED", "NONSTOP_VIBE",
               "SKIP_LONG_CLOSERS", "LONG_CLOSER_MINUTES", "FALLBACK_SPOKEN"]

# What a blank slate says when something tries to build it (the Play tab, a shortcut, a voice command)
NO_CONFIG_YET = N_("{name} has no config yet. Add one on its page under Settings > Playlists.")

# Which engine build each kind runs
BUILDERS = {"artists": "create_similar_playlist", "tracks": "create_similar_tracks_playlist",
            "top": "play_top_n", "vibe": "create_vibe_playlist"}


def blank(name, kind):
    """
    A playlist: its first config is its own kind and settings; "configs" holds any further ones
    ({"kind", "settings"}), and "mix" says how they come together (see mix_default). kind None
    is a blank slate (New under the Play tab's +): no config yet, so nothing to build until one
    is added on its page; the first config added becomes its own.
    """
    return {"id": uuid.uuid4().hex[:8], "name": name, "kind": kind, "settings": {}, "filters": [],
            "shortcut": "", "standard": "", "shown": True, "configs": [], "mix": mix_default(),
            "parent": "", "default": ""}   # nested under another playlist; a parent's default child (see nest)


def tidy(item):
    if "kind" in item and item.get("kind") is None:
        kind = None   # a blank slate, saved as it was made
    else:
        kind = item.get("kind") if item.get("kind") in KIND_NAMES else "artists"
    out = blank(str(item.get("name") or t("Button")), kind)
    out.update({k: v for k, v in item.items() if k in out})
    settings = {str(k): str(v) for k, v in (item.get("settings") or {}).items()}
    out["configs"] = [{"kind": c["kind"], "settings": {str(k): str(v) for k, v in (c.get("settings") or {}).items()
                                                        if k in KIND_KEYS[c["kind"]]}}
                      for c in (out.get("configs") or []) if isinstance(c, dict) and c.get("kind") in KIND_NAMES]
    if kind is None and out["configs"]:   # a blank slate carries no configs: the first is its own
        first = out["configs"].pop(0)
        kind, settings = first["kind"], first["settings"]
        out["kind"] = kind
    if kind == "top" and settings.get("TOP_GUESTS") == "third" and not out["configs"]:
        # Headliner as the dev build of 30 Oct 2026 kept it (a Guests setting): now top tracks + artist matching
        recipe = next(r for r in READY_MADE if r["key"] == "headliner")
        env = _env_values()
        out["configs"] = [{"kind": k, "settings": dict(settings_from(env.get, k), **extra)} for k, extra in recipe["configs"]]
        out["mix"] = dict(recipe["mix"])
    out["settings"] = {k: v for k, v in settings.items() if k in KIND_KEYS.get(kind, [])}
    out["filters"] = [str(f) for f in (out.get("filters") or [])]
    out["shown"] = bool(out.get("shown", True))
    out["parent"] = str(out.get("parent") or "")
    out["default"] = str(out.get("default") or "")
    out["mix"] = tidy_mix(out.get("mix"), len(out["configs"]) + (0 if kind is None else 1))
    return out


def tidy_mix(mix, count):
    """A playlist's mix as stored, made whole for `count` configs: a pattern entry per config, indexes in range."""
    mix = dict(mix_default(), **(mix if isinstance(mix, dict) else {}))
    out = {"combine": mix.get("combine") if mix.get("combine") in dict(COMBINES) else "shuffle"}
    pattern = []
    for n in (mix.get("pattern") or []):
        try:
            pattern.append(min(5, max(1, int(n))))
        except (TypeError, ValueError):
            pattern.append(1)
    out["pattern"] = pattern[:count] + [1] * max(0, count - len(pattern))
    for key in ("drift_from", "continue_as"):
        try:
            n = int(mix.get(key, 0))
        except (TypeError, ValueError):
            n = 0
        out[key] = n if 0 <= n < count else 0
    return out


def configs(button):
    """A playlist's configs in order: its own kind and settings first, then any added under it. A blank slate has none."""
    if button.get("kind") is None:
        return []
    return [{"kind": button["kind"], "settings": button.get("settings") or {}}] + list(button.get("configs") or [])


def has_drift(kind):
    """Whether a kind has Drift at all (Artist's Top Tracks hasn't)."""
    return kind != "top"


def continue_as(button):
    """
    The config Non-stop carries on as, playlist-shaped: the playlist with that config's kind and
    settings as its own and no further configs. A plain playlist comes back as itself.
    """
    cfgs = configs(button)
    if len(cfgs) <= 1:   # a plain playlist, or a blank slate
        return button
    i = (button.get("mix") or {}).get("continue_as", 0)
    cfg = cfgs[i] if 0 <= i < len(cfgs) else cfgs[0]
    return dict(button, kind=cfg["kind"], settings=dict(cfg["settings"]), configs=[], mix=mix_default())


def add_config(button_id, kind):
    """Another config under a playlist, starting from the standard playlist of its kind. Returns the playlist."""
    items = load()
    b = next(x for x in items if x["id"] == button_id)
    base = standard(kind)
    settings = dict(base["settings"]) if base else template_settings(kind)
    if b.get("kind") is None:   # a blank slate: its first config is its own
        b["kind"], b["settings"], b["configs"], b["mix"] = kind, settings, [], mix_default()
        save(items)
        return get(button_id)
    b["configs"].append({"kind": kind, "settings": settings})
    cfgs = configs(b)
    if not has_drift(cfgs[b["mix"]["drift_from"]]["kind"]) and has_drift(kind):
        b["mix"]["drift_from"] = len(cfgs) - 1   # the first config with Drift gets it
    save(items)
    return get(button_id)


def remove_config(button_id, index):
    """
    Takes config `index` off a playlist. Index 0 is the playlist's own: the next config moves up
    into its place, or with none left the playlist is a blank slate again. A standard playlist
    keeps its own.
    """
    items = load()
    b = next(x for x in items if x["id"] == button_id)
    if not 0 <= index < len(configs(b)) or (index == 0 and b.get("standard")):
        return get(button_id)
    if index == 0:
        if b["configs"]:
            first = b["configs"].pop(0)
            b["kind"], b["settings"] = first["kind"], first["settings"]
        else:
            b["kind"], b["settings"] = None, {}
    else:
        del b["configs"][index - 1]
    mix = b["mix"]
    for key in ("drift_from", "continue_as"):
        if mix[key] == index:
            mix[key] = 0
        elif mix[key] > index:
            mix[key] -= 1
    if index < len(mix["pattern"]):
        del mix["pattern"][index]
    save(items)
    return get(button_id)


def set_config_settings(button_id, index, settings):
    """One config's settings (index 0 is the playlist's own), kept to its kind's keys."""
    if index == 0:
        return set_settings(button_id, settings)
    items = load()
    for b in items:
        if b["id"] == button_id and 1 <= index <= len(b["configs"]):
            cfg = b["configs"][index - 1]
            cfg["settings"] = {k: str(v) for k, v in settings.items() if k in KIND_KEYS[cfg["kind"]]}
    save(items)


def set_config_kind(button_id, index, kind):
    """
    Changes a config's kind (index 0 is the playlist's own): its settings start again from the
    standard playlist of the new kind, or the kind's shipped defaults. A standard playlist's own
    kind can't change. Returns the playlist.
    """
    items = load()
    b = next(x for x in items if x["id"] == button_id)
    if kind not in KIND_NAMES or (index == 0 and b.get("standard")):
        return b
    base = standard(kind)
    settings = dict(base["settings"]) if base and base["id"] != button_id else template_settings(kind)
    if index == 0:
        b["kind"], b["settings"] = kind, settings
    elif 1 <= index <= len(b["configs"]):
        b["configs"][index - 1] = {"kind": kind, "settings": settings}
    else:
        return b
    cfgs = configs(b)
    if not has_drift(cfgs[b["mix"]["drift_from"]]["kind"]):   # Drift can't come from Artist's Top Tracks
        b["mix"]["drift_from"] = next((i for i, c in enumerate(cfgs) if has_drift(c["kind"])), 0)
    save(items)
    return get(button_id)


def add_from_choice(choice):
    """
    The Add a Playlist window's answer: ("existing", id) ticks a playlist back onto the Play tab;
    ("copy", id) copies one that's on it; ("template", key) adds the template (a kind's shipped defaults, or Headliner or Inner Circle)
    under its own name, ticked; ("new", None) adds a blank slate called New Playlist, ticked, with
    no config until its page adds one. Returns (the playlist, whether it's new and wants its page).
    """
    how, what = choice
    if how == "existing":
        b = get(what)
        if b is not None and not b.get("shown", True):
            set_shown(what, True)
        return get(what), False
    if how == "copy":   # one that's on the Play tab already: a copy, Name 2, right after it
        return duplicate(what), False
    if how == "template":
        recipe = next((r for r in READY_MADE if r["key"] == what), None)
        if recipe is not None:
            return add(unique_name(t(recipe["name"])), recipe["kind"], f"{TEMPLATE}:{what}"), False
        kind = what if what in KIND_NAMES else "artists"
        return add(unique_name(t(KIND_LABELS[kind])), kind, TEMPLATE), False
    return add(unique_name(t("New Playlist")), None), True


def set_mix(button_id, **fields):
    """How a playlist's configs come together: combine, pattern, drift_from, continue_as."""
    items = load()
    for b in items:
        if b["id"] == button_id:
            b["mix"] = tidy_mix(dict(b["mix"], **fields), len(b["configs"]) + 1)
    save(items)


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
    return settle(_adopt_env_shortcuts(items))


# --- nesting: a playlist under another, one level deep ---------------------------------------------
#
# A playlist with a parent sits in that parent's menu on the Play tab rather than on the row. The
# parent's button runs its default: itself, or the child its "default" names. The stored list is in
# tree order (each parent followed by its children), which is the order everything shows.

def settle(items):
    """
    Makes the tree whole and puts the list in tree order: a parent must exist and be top-level, a
    child has no children of its own (they come out to the row), and a default must be a child.
    """
    ids = {b["id"] for b in items}
    by_id = {b["id"]: b for b in items}
    for b in items:
        p = b.get("parent") or ""
        if p and (p not in ids or p == b["id"] or by_id[p].get("parent")):
            b["parent"] = ""
    for b in items:
        if b.get("default") and not any(c["id"] == b["default"] and c.get("parent") == b["id"] for c in items):
            b["default"] = ""
        if b.get("parent"):
            b["default"] = ""
    ordered = []
    for b in items:
        if not b.get("parent"):
            ordered.append(b)
            ordered += [c for c in items if c.get("parent") == b["id"]]
    return ordered


def children(parent_id, ticked_only=True):
    """A parent's children in order: the ticked ones (in its menu), or every one."""
    return [b for b in load() if b.get("parent") == parent_id and (b.get("shown", True) or not ticked_only)]


def is_parent(button):
    return any(b.get("parent") == button["id"] for b in load())


def nest(child_id, parent_id):
    """
    Puts a playlist under another: off the row and into the parent's menu, after any children it
    has. One level deep: a child can't take children, and a playlist with children can't be nested.
    Returns whether it happened.
    """
    items = load()
    by_id = {b["id"]: b for b in items}
    child, parent = by_id.get(child_id), by_id.get(parent_id)
    if child is None or parent is None or child is parent or parent.get("parent"):
        return False
    if any(b.get("parent") == child_id for b in items):
        return False
    child["parent"] = parent_id
    child["default"] = ""
    save(settle(items))
    return True


def unnest(child_id):
    """Brings a child out onto the row, right after its parent's group. Returns whether it happened."""
    items = load()
    child = next((b for b in items if b["id"] == child_id), None)
    if child is None or not child.get("parent"):
        return False
    parent_id = child["parent"]
    items.remove(child)
    last = max(k for k, b in enumerate(items) if b["id"] == parent_id or b.get("parent") == parent_id)
    items.insert(last + 1, child)
    child["parent"] = ""
    for b in items:
        if b["id"] == parent_id and b.get("default") == child_id:
            b["default"] = ""
    save(settle(items))
    return True


def set_default(parent_id, child_id):
    """What a parent's button runs: one of its children, or "" for the parent itself."""
    items = load()
    for b in items:
        if b["id"] == parent_id and not b.get("parent"):
            b["default"] = child_id if any(c["id"] == child_id and c.get("parent") == parent_id for c in items) else ""
    save(items)


def runs(button):
    """The playlist a button's main part builds: the parent's default child if it has one, else itself."""
    if button.get("default"):
        child = get(button["default"])
        if child is not None and child.get("parent") == button["id"]:
            return child
    return button


def siblings(items, button):
    """The playlists at the same level as this one, in order: the top level, or one parent's children."""
    return [b for b in items if (b.get("parent") or "") == (button.get("parent") or "")]


def _group(items, button):
    """A top-level playlist with its children, as one block to move; a child on its own."""
    if button.get("parent"):
        return [button]
    return [button] + [c for c in items if c.get("parent") == button["id"]]


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
    if kind is None:
        return None
    items = of_kind(kind)
    return next((b for b in items if b.get("standard") == kind), items[0] if items else None)


def has_kind(button, kind):
    """Whether a playlist builds this kind (its config's kind; a playlist with several configs, any of them)."""
    return button.get("kind") == kind


def shown():
    """The playlists on the Play tab's row, in the order shown: ticked, and not nested under another."""
    return [b for b in load() if b.get("shown", True) and not b.get("parent")]


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
    (from_id TEMPLATE). kind None: a blank slate, no config until its page adds one.
    """
    items = load()
    ready = next((r for r in READY_MADE if from_id == f"{TEMPLATE}:{r['key']}"), None)
    if ready is not None:   # Headliner, Inner Circle: the standard playlists of its kinds with the recipe laid on top
        new = ready_made_button(ready["key"], {k: standard(k) for k in KIND_NAMES})
        new["name"] = name.strip() or t(ready["name"])
    elif kind is None:
        new = blank(name.strip() or t("New Playlist"), None)
    else:
        new = blank(name.strip() or t(KIND_LABELS[kind]), kind)
        if from_id == TEMPLATE:
            new["settings"] = template_settings(kind)
        else:
            source = next((b for b in items if b["id"] == from_id and b["kind"] == kind), None) or standard(kind)
            if source:
                new["settings"], new["filters"] = dict(source["settings"]), list(source["filters"])
                new["configs"] = [{"kind": c["kind"], "settings": dict(c["settings"])} for c in source.get("configs") or []]
                new["mix"] = tidy_mix(source.get("mix"), len(new["configs"]) + 1)
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


def _swap_with_sibling(items, button_id, by, among=None):
    """Moves a playlist past the next sibling (by -1 up, +1 down), its children with it. among: the siblings that count."""
    moving = next((b for b in items if b["id"] == button_id), None)
    if moving is None:
        return items
    sibs = among if among is not None else siblings(items, moving)
    sibs = [b for b in sibs if (b.get("parent") or "") == (moving.get("parent") or "")]
    ids = [b["id"] for b in sibs]
    if button_id not in ids:
        return items
    i = ids.index(button_id)
    j = min(max(i + by, 0), len(ids) - 1)   # a big step stops at the end
    if j == i:
        return items
    block = _group(items, moving)
    other = _group(items, sibs[j])
    for b in block:
        items.remove(b)
    anchor = items.index(other[0]) if by < 0 else items.index(other[-1]) + 1
    return items[:anchor] + block + items[anchor:]


def move(button_id, by):
    """Moves a playlist among its siblings: by -1 is one place up (left on the row), +1 one place down."""
    save(_swap_with_sibling(load(), button_id, by))


def remove(button_id):
    """Deletes a playlist. Its children, if any, come out onto the row where it was."""
    items = load()
    for b in items:
        if b.get("parent") == button_id:
            b["parent"] = ""
        if b.get("default") == button_id:
            b["default"] = ""
    save([b for b in items if b["id"] != button_id])


def move_shown(button_id, by):
    """Moves a playlist along the Play tab's row: by -1 one place left, +1 one place right, past unticked ones."""
    items = load()
    row = [b for b in items if b.get("shown", True) and not b.get("parent")]
    save(_swap_with_sibling(items, button_id, by, among=row))


def move_to(button_id, before_id):
    """Drops a playlist in front of another on the Play tab's row (before_id None: at the end), its children with it."""
    items = load()
    moving = next((b for b in items if b["id"] == button_id), None)
    if moving is None or button_id == before_id or moving.get("parent"):
        return
    block = _group(items, moving)
    for b in block:
        items.remove(b)
    if before_id is None:
        items += block
    else:
        anchor = next((k for k, b in enumerate(items) if b["id"] == before_id), len(items))
        items = items[:anchor] + block + items[anchor:]
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
    moving["parent"] = source.get("parent") or ""   # a child's copy sits beside it in the menu
    group = _group(items, source)
    items.insert(items.index(group[-1]) + 1, moving)
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
    button = continue_as(button)   # a mix carries on as the config its Mix says
    if button.get("kind") is None:   # a blank slate: nothing to carry on as
        return {"on": False, "using": "artists", "reseed": "last", "mode": "journey"}
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


def ready_made_button(key, bases):
    """
    A ready-made playlist (Headliner, Inner Circle) from the standard playlists of its kinds:
    bases is {kind: the standard playlist or None}. A kind with no standard starts from the
    shipped defaults.
    """
    recipe = next(r for r in READY_MADE if r["key"] == key)

    def start(kind):
        base = bases.get(kind)
        return dict(base["settings"]) if base else template_settings(kind)
    b = blank(t(recipe["name"]), recipe["kind"])
    b["settings"] = dict(start(recipe["kind"]), **recipe["settings"])
    base = bases.get(recipe["kind"])
    b["filters"] = list(base["filters"]) if base else []
    b["configs"] = [{"kind": kind, "settings": dict(start(kind), **extra)} for kind, extra in recipe["configs"]]
    b["mix"] = tidy_mix(recipe["mix"], len(b["configs"]) + 1)
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
    at = items.index(by_kind["vibe"])   # before AI Playlist (Ben, 30 Oct): Headliner, then Inner Circle
    items.insert(at, ready_made_button("headliner", by_kind))
    items.insert(at + 1, ready_made_button("inner_circle", by_kind))
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
    remembered with what it sends, for Non-stop. A playlist of two or more configs builds
    each in turn and weaves them as its Mix says (_run_mix); a top-up or a `build` of its own
    runs as the first config alone.
    """
    cfgs = configs(button)
    if not cfgs:   # a blank slate: nothing to build until its page adds a config
        report(t(NO_CONFIG_YET, name=button["name"]))
        return None
    if build is not None or len(cfgs) == 1 or engine.NONSTOP_APPEND or options.get("topup"):
        return _run_one(button, button["kind"], button.get("settings") or {}, report, seed_info, build, extra_filters,
                        options)
    return _run_mix(button, cfgs, report, seed_info, extra_filters, options)


def _run_one(button, kind, settings, report, seed_info, build, extra_filters, options):
    """One config of a playlist, under the playlist's filters."""
    ids = list(button.get("filters") or [])
    ids += [i for i in extra_filters if i not in ids]
    previous = dict(engine.PROFILE)
    before = engine.BUILD_BUTTON
    engine.use_profile(dict(settings or {}, **previous))
    engine.FILTER_IDS = ids
    engine.BUILD_BUTTON = button["id"]
    try:
        if build is not None:
            return build(report=report, seed_info=seed_info, **options)
        builder = getattr(engine, BUILDERS[kind])
        if kind == "vibe":
            return builder(options.pop("theme", ""), report=report, **options)
        return builder(report=report, seed_info=seed_info, **options)
    finally:
        engine.FILTER_IDS = None
        engine.BUILD_BUTTON = before
        engine.use_profile(previous or None)


def whole_playlist_settings(first, kind):
    """
    The first config's whole-playlist settings (Skip played, Hidden Tracks, If All Else Fails, Run After
    Building, Deep Cuts) as `kind`'s keys, for a later config of a mix. Non-stop and Drift aren't among
    them: those follow the Mix's Continue as and Drift from. Deep Cuts goes off when the first config
    has none (Artist's Top Tracks).
    """
    g0, g = first["kind"].upper(), kind.upper()
    out = {}
    for tmpl in _EACH:
        if tmpl.startswith("NONSTOP_"):
            continue
        k0, k = tmpl.format(G=g0), tmpl.format(G=g)
        if k in KIND_KEYS[kind] and k0 in first["settings"]:
            out[k] = first["settings"][k0]
    for tmpl in ("DEEP_CUTS_{G}", "DEEP_CUTS_{G}_SHARE"):
        k0, k = tmpl.format(G=g0), tmpl.format(G=g)
        if k in KIND_KEYS[kind]:
            if k0 in KIND_KEYS[first["kind"]]:
                if k0 in first["settings"]:
                    out[k] = first["settings"][k0]
            elif tmpl == "DEEP_CUTS_{G}":
                out[k] = "off"
    return out


def _run_mix(button, cfgs, report, seed_info, extra_filters, options):
    """
    A playlist of two or more configs: the same seed for each, built one after another. The
    first config's tracks go out as any playlist's would; each later config's are added after
    them, and nothing is sent twice. Drift runs from the config the Mix names and no other.
    Then engine.combine_finish weaves them as the Mix says. An AI Playlist config with no theme
    typed is asked for music like the seed.
    """
    mix = tidy_mix(button.get("mix"), len(cfgs))
    if seed_info is None and any(c["kind"] != "vibe" for c in cfgs):
        seed_info = engine.get_playing_info()   # one seed for every config
        if not seed_info or seed_info.get("PlayingNowPosition") == "-1":
            report(engine.NOTHING_PLAYING)
            return None
    engine.COMBINE_TRACE, engine.COMBINE_INDEX = [], 0
    try:
        for i, cfg in enumerate(cfgs):
            engine.check_cancelled()
            engine.COMBINE_INDEX = i
            settings = dict(cfg["settings"])
            if i:   # the sections shown for the whole playlist are the first config's: they apply to every config
                settings.update(whole_playlist_settings(cfgs[0], cfg["kind"]))
            if i != mix["drift_from"]:
                settings[f"DRIFT_{cfg['kind'].upper()}"] = "0"
            report(t("Config {n} of {total}: {kind}", n=i + 1, total=len(cfgs), kind=t(KIND_LABELS[cfg["kind"]])))
            opts = dict(options)
            if cfg["kind"] == "vibe":
                if not opts.get("theme") and seed_info:
                    opts["theme"] = (t("music like {artist} - {title}", artist=seed_info.get("Artist", ""),
                                       title=seed_info.get("Name", "")) if seed_info.get("Name")
                                     else t("music like {artist}", artist=seed_info.get("Artist", "")))
            else:
                for key in ("theme", "count", "if_short", "prompt", "check"):
                    opts.pop(key, None)
            _run_one(button, cfg["kind"], settings, report, seed_info, None, extra_filters, opts)
        by_config = {}
        for i, keys in engine.COMBINE_TRACE:
            by_config.setdefault(i, []).extend(keys)
        engine.COMBINE_TRACE = None
        engine.combine_finish(by_config, mix["combine"], mix["pattern"], seed_info, report)
    finally:
        engine.COMBINE_TRACE, engine.COMBINE_INDEX = None, 0
    return None


def describe(button):
    """A short line for a hover note: the kind (or kinds, joined with +), then what's on."""
    cfgs = configs(button)
    if not cfgs:
        return t("No config yet")
    mix = tidy_mix(button.get("mix"), len(cfgs))
    s = button.get("settings") or {}
    g = button["kind"].upper()
    bits = [" + ".join(t(KIND_LABELS[c["kind"]]) for c in cfgs)]
    if any(c["settings"].get(f"INNER_CIRCLE_{c['kind'].upper()}", "0") in engine.YES for c in cfgs):
        bits.append("Inner Circle")
    d = cfgs[mix["drift_from"]]
    if d["settings"].get(f"DRIFT_{d['kind'].upper()}", "0") in engine.YES:
        bits.append("Drift")
    if s.get(f"DEEP_CUTS_{g}", "off") not in ("off", ""):
        bits.append("Deep Cuts")
    n = cfgs[mix["continue_as"]]
    if n["settings"].get(f"NONSTOP_{n['kind'].upper()}", "0") in engine.YES:
        bits.append("Non-stop")
    if button.get("filters"):
        bits.append(t("Filters"))
    return ", ".join(bits)
