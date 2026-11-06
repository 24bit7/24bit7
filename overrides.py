"""
24bit7 - the More Options row's three switches: Moderator, Deep Cuts and Non-stop.

Agreed with Ben, 2 Nov 2026. The row being open is the override: while it's open the three
switches beat every playlist's own settings, for every build (the Play tab, voice, shortcuts and
Non-stop's top-ups); closed, the playlists' pages decide and the switches do nothing. The row
remembers open or closed between launches (playmix), so the override does too.

Each switch steps through its settings, as the 1.28 row did: the Moderator Off, Relaxed, Balanced
or Strict; Deep Cuts Off, Spaced or Shuffled; Non-stop Off, Keep It Tight or Wander. Off turns the
thing off for every playlist; any other setting runs for every playlist. What a setting leaves
open (how much Deep Cuts top up by, what Non-stop plays using and reseeds from) stays the
playlist's own, or the standard playlist of its kind's when the page has it off.

The switches start from the row 1.28 had, whose values are still in .env after the upgrade. A
fresh install has them off, so the switches start Off. They're kept with the row's open flag.
"""

from i18n import N_, t

import engine
import playmix

SWITCHES = ("moderator", "deep_cuts", "nonstop")
NAMES = {"moderator": N_("Moderator"), "deep_cuts": N_("Deep Cuts"), "nonstop": N_("Non-stop")}
# each switch's settings in click order, as the code knows them; LABELS is what the switch shows (through t())
VALUES = {"moderator": ("off", "relaxed", "balanced", "strict"),
          "deep_cuts": ("off", "spaced", "shuffled"),
          "nonstop": ("off", "tight", "journey")}
LABELS = {"off": N_("Off"), "relaxed": N_("Relaxed"), "balanced": N_("Balanced"), "strict": N_("Strict"),
          "spaced": N_("Spaced"), "shuffled": N_("Shuffled"), "tight": N_("Keep It Tight"), "journey": N_("Wander")}
GROUPS = {"artists": "ARTISTS", "tracks": "TRACKS", "top": "TOP", "vibe": "VIBE"}
OPEN_LINE = N_("More Options Open: any settings set here override your playlists' own settings. The override ends "
               "when More Options closes.")


def labels(name):
    """The switch's faces in click order, English, shown through t() by the switch."""
    return [LABELS[v] for v in VALUES[name]]


def code_for(name, label):
    """The setting behind a face ('Keep It Tight' -> 'tight')."""
    return next((v for v in VALUES[name] if LABELS[v] == label), "off")


def _getter(values):
    return lambda name, default="": values.get(name, default) if values.get(name) not in (None, "") else default


def _env():
    import buttons
    return buttons._env_values()


def _seed(env):
    """The 1.28 row's values, from .env as it stands. A fresh .env gives three Offs."""
    get = _getter(env)
    levels = engine.moderator_settings(get)
    moderator = next((levels[g] for g in engine.MODERATOR_GROUPS if levels.get(g, "off") != "off"), "off")
    deep = next((m for m in ((get(f"DEEP_CUTS_{g.upper()}", "off") or "off").strip().lower() for g in engine.DEEP_CUT_GROUPS)
                 if m in VALUES["deep_cuts"] and m != "off"), "off")
    nonstop = next((cfg["mode"] for cfg in engine.nonstop_settings(get).values() if cfg.get("on")), "off")
    return {"moderator": moderator, "deep_cuts": deep, "nonstop": nonstop}


def _clean(saved):
    """Saved values made whole: an unknown setting is off; the first build's True/False become Balanced/Spaced/Wander or off."""
    out = {}
    for name in SWITCHES:
        v = saved.get(name) if isinstance(saved, dict) else None
        if v is True:
            v = {"moderator": "balanced", "deep_cuts": "spaced", "nonstop": "journey"}[name]
        out[name] = v if v in VALUES[name] else "off"
    return out


def switches():
    """The three switches as last left: {"moderator", "deep_cuts", "nonstop"} -> the setting that runs. Seeded once."""
    data = playmix.load()
    saved = data.get("switches")
    if not isinstance(saved, dict):
        saved = _seed(_env())
        data["switches"] = saved
        playmix._save(data)
    return _clean(saved)


def set_switch(name, value):
    if name not in SWITCHES or value not in VALUES[name]:
        raise ValueError((name, value))
    data = playmix.load()
    current = switches()
    current[name] = value
    data["switches"] = current
    playmix._save(data)
    return current


def set_switches(values):
    """All three at once (the Use Its Settings pill)."""
    data = playmix.load()
    data["switches"] = _clean(values)
    playmix._save(data)
    return dict(data["switches"])


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
    What a playlist's own page has, as the three switches would show it: its Moderator level, its
    Deep Cuts mode and its Non-stop mode (off when Non-stop is off). For Use Its Settings.
    """
    import buttons
    kind = button.get("kind")
    if kind is None:
        return {"moderator": "off", "deep_cuts": "off", "nonstop": "off"}
    if kind == buttons.RADIO:   # Radio's Moderator and Deep Cuts are Artist Matching's keys; it always plays on
        get = _getter(_merged(button))
        level = engine.moderator_settings(get).get("artists", "off")
        deep = (get("DEEP_CUTS_ARTISTS", "off") or "off").strip().lower()
        return _clean({"moderator": level, "deep_cuts": deep, "nonstop": "journey"})
    get = _getter(_merged(button))
    level = engine.moderator_settings(get).get(kind, "off") if kind in engine.MODERATOR_GROUPS or kind == "vibe" else "off"
    deep = (get(f"DEEP_CUTS_{GROUPS[kind]}", "off") or "off").strip().lower() if kind in engine.DEEP_CUT_GROUPS else "off"
    own = buttons.nonstop_own(button)
    return _clean({"moderator": level, "deep_cuts": deep, "nonstop": own["mode"] if own.get("on") else "off"})


def layer(button, kind, settings=None):
    """
    The settings the switches lay over one config's for a build, while the row is open: the
    Moderator level and Deep Cuts mode for the config's kind, as the switches read. Non-stop is
    applied where it's read (nonstop_config), not here. Empty when the row is closed or the kind
    has neither (Artist's Top Tracks).
    """
    if not active():
        return {}
    on = switches()
    out = {}
    g = GROUPS.get(kind, "")
    if kind in engine.MODERATOR_GROUPS or kind == "vibe":
        out[f"AI_MODERATOR_{g}"] = on["moderator"]
    if kind in engine.DEEP_CUT_GROUPS:
        out[f"DEEP_CUTS_{g}"] = on["deep_cuts"]
    return out


def nonstop(cfg, button):
    """
    Non-stop's config for a playlist with the switch laid over it, while the row is open: Off turns
    it off; Keep It Tight or Wander turns it on in that mode, playing using and reseeding from what
    the playlist's own page says, or the standard playlist of its kind's when the page has it off.
    """
    if not active():
        return cfg
    mode = switches()["nonstop"]
    if mode == "off":
        return dict(cfg, on=False)
    if not cfg.get("on"):
        import buttons
        kind = (buttons.continue_as(button) if button else {}).get("kind")
        standard_of = buttons.standard(kind) if kind else None
        if standard_of is not None and standard_of.get("id") != (button or {}).get("id"):
            std = buttons.nonstop_own(standard_of)
            if std.get("on"):
                cfg = std
    return dict(cfg, on=True, mode=mode)


def summary():
    """One console line's worth: 'Moderator Balanced, Deep Cuts Off, Non-stop Wander'."""
    on = switches()
    return ", ".join(f"{t(NAMES[k])} {t(LABELS[on[k]])}" for k in SWITCHES)
