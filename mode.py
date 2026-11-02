"""
24bit7 - Simple and Advanced, the playlist pages' mode.

Agreed with Ben, 2 Nov 2026. One setting for the listener, not per playlist and not in Profiles,
kept beside the More Options row's state (playmix). Simple is a mode, not a view: a playlist
builds from its first config alone, and the advanced sections are off in every build (Moderator,
Drift, Deep Cuts, Non-stop, Consensus, Hidden Tracks, If All Else Fails, Run After Building,
Shortcut). Their settings stay stored, so Advanced brings them back as they were. A playlist that
can't be itself in Simple (two or more configs, or Consensus on) doesn't build there: the console
says it needs Advanced, and the Play tab greys it. The More Options switches still override in
Simple: they're something the listener set by hand on the Play tab, not a section.

First time: Advanced if any playlist of the listener's own (not a ready-made 24bit7 ships) has
anything beyond Sources and Playlist Selection on, else Simple. Hidden Tracks and If All Else Fails
ship on, so they don't count towards that.
"""

from i18n import N_, t

import engine
import playmix

SIMPLE, ADVANCED = "simple", "advanced"
NEEDS_ADVANCED = N_("{name} needs Advanced: switch to Advanced under Settings > Playlist Settings to build it.")

# What Simple turns off, per kind: (section, the key that holds it, its off value). G is the kind's group.
_OFF = [
    (N_("Moderator"), "AI_MODERATOR_{G}", "off"),
    (N_("Drift"), "DRIFT_{G}", "0"),
    (N_("Deep Cuts"), "DEEP_CUTS_{G}", "off"),
    (N_("Non-stop"), "NONSTOP_{G}", "0"),
    (N_("Consensus"), "INNER_CIRCLE_{G}", "0"),
    (N_("Hidden Tracks"), "SKIP_LONG_CLOSERS_{G}", "0"),
    (N_("If All Else Fails"), "IF_ALL_ELSE_FAILS_{G}", "0"),
    (N_("Run After Building"), "RUN_AFTER_{G}", "0"),
]
_SHIPS_ON = {"Hidden Tracks", "If All Else Fails"}   # on in a fresh install: not a sign the listener went advanced


def _is_on(key, value):
    value = (value or "").strip().lower()
    if key.startswith("AI_MODERATOR_"):
        return value not in ("", "off", "0")
    if key.startswith("DEEP_CUTS_"):
        return value not in ("", "off")
    return value in engine.YES


def current():
    """"simple" or "advanced", as last chosen; the first time, worked out from the listener's playlists."""
    data = playmix.load()
    saved = data.get("mode")
    if saved not in (SIMPLE, ADVANCED):
        saved = default_mode()
        data["mode"] = saved
        playmix._save(data)
    return saved


def set_current(value):
    if value not in (SIMPLE, ADVANCED):
        raise ValueError(value)
    data = playmix.load()
    data["mode"] = value
    playmix._save(data)
    return value


def is_simple():
    return current() == SIMPLE


def uses_advanced(button, counting_shipped=True):
    """
    The advanced things a playlist has on, by section name: a second config ("Mix"), a shortcut, and
    each section of _OFF that's on in any of its configs. counting_shipped=False leaves out the two
    that ship on (Hidden Tracks, If All Else Fails), for the first-time default.
    """
    import buttons
    cfgs = buttons.configs(button)
    out = []
    if len(cfgs) > 1:
        out.append("Mix")
    if button.get("shortcut"):
        out.append("Shortcut")
    env = buttons._env_values()
    for cfg in cfgs:
        merged = dict(env, **cfg["settings"])
        g = cfg["kind"].upper()
        for section, tmpl, _off in _OFF:
            key = tmpl.format(G=g)
            if key in buttons.KIND_KEYS[cfg["kind"]] and section not in out and _is_on(key, merged.get(key)):
                if counting_shipped or section not in _SHIPS_ON:
                    out.append(section)
    return out


def default_mode():
    """Advanced if any playlist of the listener's own has anything advanced on; the ready-mades 24bit7 ships don't count."""
    import buttons
    for b in buttons.load():
        if b.get("made"):
            continue
        if uses_advanced(b, counting_shipped=False):
            return ADVANCED
    return SIMPLE


def needs_advanced(button):
    """Whether a playlist can't be itself in Simple: two or more configs, or Consensus on in its first config."""
    import buttons
    cfgs = buttons.configs(button)
    if len(cfgs) > 1:
        return True
    if not cfgs:
        return False
    g = cfgs[0]["kind"].upper()
    return _is_on(f"INNER_CIRCLE_{g}", cfgs[0]["settings"].get(f"INNER_CIRCLE_{g}", ""))


def layer(kind):
    """The settings Simple lays over one config's for a build: every advanced section off. Empty in Advanced."""
    if not is_simple():
        return {}
    import buttons
    g = kind.upper()
    out = {}
    for _section, tmpl, off in _OFF:
        key = tmpl.format(G=g)
        if key in buttons.KIND_KEYS.get(kind, []):
            out[key] = off
    return out


def turns_off(items=None):
    """
    What switching to Simple turns off, for the message: {section: how many playlists have it on},
    counting the listener's buttons and devices' playlists alike, in the order the sections are listed.
    """
    import buttons
    items = buttons.load() if items is None else items
    counts = {}
    for b in items:
        for section in uses_advanced(b):
            counts[section] = counts.get(section, 0) + 1
    order = ["Mix"] + [s for s, _k, _o in _OFF] + ["Shortcut"]
    return {s: counts[s] for s in order if s in counts}


def summary_of(counts):
    """'Deep Cuts, Drift and Non-stop on three playlists', for the switch-to-Simple line."""
    if not counts:
        return ""
    names = [t(s) for s in counts]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " " + t("and") + " " + names[-1]
    playlists = max(counts.values())
    return t("{sections} on {n} playlists", sections=joined, n=playlists) if playlists != 1 \
        else t("{sections} on one playlist", sections=joined)
