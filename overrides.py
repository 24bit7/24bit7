"""
24bit7 - the More Options row's three switches: Moderator, Deep Cuts and Non-stop.

Agreed with Ben, 2 Nov 2026. The row being open is the override: while it's open the three
switches beat every playlist's own settings, for every build (the Play tab, voice, shortcuts and
Non-stop's top-ups); closed, the playlists' pages decide and the switches do nothing. The row
remembers open or closed between launches (playmix), so the override does too.

Each switch is Off or On. Off turns the thing off. On runs it the way the playlist's own page
says; if its page has it off, the standard playlist of that kind's way; if that's off too, the
shipped default: Moderator Balanced, Deep Cuts Spaced, Non-stop as the kind's own settings.

The switches start from the row 1.28 had, whose values are still in .env after the upgrade
(the Moderator level, the Deep Cuts mode and Non-stop per kind): anything not off is On. A fresh
install has them off, so the switches start Off. They're kept with the row's open flag.
"""

from i18n import N_, t

import engine
import playmix

SWITCHES = ("moderator", "deep_cuts", "nonstop")
NAMES = {"moderator": N_("Moderator"), "deep_cuts": N_("Deep Cuts"), "nonstop": N_("Non-stop")}
GROUPS = {"artists": "ARTISTS", "tracks": "TRACKS", "top": "TOP", "vibe": "VIBE"}


def _getter(values):
    return lambda name, default="": values.get(name, default) if values.get(name) not in (None, "") else default


def _env():
    import buttons
    return buttons._env_values()


def _seed(env):
    """The 1.28 row's values, from .env as it stands: anything not off is On. A fresh .env gives three Offs."""
    get = _getter(env)
    levels = engine.moderator_settings(get)
    moderator = any(levels.get(g, "off") != "off" for g in engine.MODERATOR_GROUPS)
    deep = any((get(f"DEEP_CUTS_{g.upper()}", "off") or "off").strip().lower() not in ("off", "")
               for g in engine.DEEP_CUT_GROUPS)
    nonstop = any(cfg.get("on") for cfg in engine.nonstop_settings(get).values())
    return {"moderator": moderator, "deep_cuts": deep, "nonstop": nonstop}


def switches():
    """The three switches as last left: {"moderator", "deep_cuts", "nonstop"} -> bool. Seeded once."""
    data = playmix.load()
    saved = data.get("switches")
    if not isinstance(saved, dict):
        saved = _seed(_env())
        data["switches"] = saved
        playmix._save(data)
    return {name: bool(saved.get(name)) for name in SWITCHES}


def set_switch(name, on):
    if name not in SWITCHES:
        raise ValueError(name)
    data = playmix.load()
    current = switches()
    current[name] = bool(on)
    data["switches"] = current
    playmix._save(data)
    return current


def set_switches(values):
    """All three at once (the Use Its Settings pill)."""
    data = playmix.load()
    data["switches"] = {name: bool(values.get(name)) for name in SWITCHES}
    playmix._save(data)
    return dict(data["switches"])


OPEN_LINE = N_("More Options Open: any settings set here override your playlists' own settings. The override ends "
               "when More Options closes.")


def told():
    """Whether the one-off dialog about the switches has been shown (the first time the row is opened by hand)."""
    return bool(playmix.load().get("told"))


def set_told():
    data = playmix.load()
    data["told"] = True
    playmix._save(data)


def active():
    """Whether the switches are in force: the More Options row is open."""
    return playmix.is_open()


def _merged(button):
    """A playlist's first config's settings over .env, as a build sees them."""
    env = _env()
    return dict(env, **(button.get("settings") or {})) if button else dict(env)


def from_playlist(button):
    """
    What a playlist's own page has: the three switches as that playlist would set them
    (Moderator level not off, Deep Cuts mode not off, Non-stop on). For Use Its Settings.
    """
    import buttons
    kind = button.get("kind")
    if kind is None:
        return {"moderator": False, "deep_cuts": False, "nonstop": False}
    merged = _merged(button)
    get = _getter(merged)
    level = engine.moderator_settings(get).get(kind, "off") if kind in engine.MODERATOR_GROUPS or kind == "vibe" else "off"
    deep = (get(f"DEEP_CUTS_{GROUPS[kind]}", "off") or "off").strip().lower() if kind in engine.DEEP_CUT_GROUPS else "off"
    return {"moderator": level != "off", "deep_cuts": deep not in ("off", ""),
            "nonstop": bool(buttons.nonstop_own(button).get("on"))}   # the page's own, not the switch's


def _fallback(kind, key, own, standard_of, shipped, off=("off", "")):
    """own if it isn't off, else the standard playlist of the kind's value, else the shipped default."""
    if own not in off:
        return own
    if standard_of is not None:
        value = (dict(_env(), **(standard_of.get("settings") or {})).get(key, "") or "").strip().lower()
        if value not in off:
            return value
    return shipped


def layer(button, kind, settings=None):
    """
    The settings the switches lay over one config's for a build, while the row is open:
    the Moderator level and Deep Cuts mode for the config's kind. Non-stop is applied where it's
    read (nonstop_config), not here. Empty when the row is closed or the kind has neither.
    """
    if not active():
        return {}
    import buttons
    on = switches()
    merged = dict(_env(), **(settings if settings is not None else (button.get("settings") or {})))
    standard_of = buttons.standard(kind)
    out = {}
    g = GROUPS.get(kind, "")
    if kind in engine.MODERATOR_GROUPS or kind == "vibe":
        key = f"AI_MODERATOR_{g}"
        own = engine.moderator_settings(_getter(merged)).get(kind, "off")
        out[key] = _fallback(kind, key, own, standard_of, "balanced") if on["moderator"] else "off"
    if kind in engine.DEEP_CUT_GROUPS:
        key = f"DEEP_CUTS_{g}"
        own = (merged.get(key, "off") or "off").strip().lower()
        out[key] = _fallback(kind, key, own, standard_of, "spaced") if on["deep_cuts"] else "off"
    return out


def nonstop(cfg, button):
    """
    Non-stop's config for a playlist with the switch laid over it, while the row is open:
    Off turns it off; On keeps the playlist's own set-up, or the standard playlist of its
    kind's when the page has it off, or the kind's defaults.
    """
    if not active():
        return cfg
    if not switches()["nonstop"]:
        return dict(cfg, on=False)
    if cfg.get("on"):
        return cfg
    import buttons
    kind = (buttons.continue_as(button) if button else {}).get("kind")
    standard_of = buttons.standard(kind) if kind else None
    if standard_of is not None and standard_of.get("id") != (button or {}).get("id"):
        std = buttons.nonstop_own(standard_of)
        if std.get("on"):
            return dict(std, on=True)
    return dict(cfg, on=True)


def summary():
    """One console line saying what the row applies: 'Moderator off, Deep Cuts on, Non-stop off'."""
    on = switches()
    parts = [t("{name} on", name=t(NAMES[k])) if on[k] else t("{name} off", name=t(NAMES[k])) for k in SWITCHES]
    return ", ".join(parts)
