"""
24bit7 - keyboard shortcuts.

Global shortcuts that work while 24bit7 is minimised or in the tray, so a
remote that sends key presses (a Flirc, a Harmony, a phone app) can start a
playlist from the sofa. Set under Settings > Other > Keyboard Shortcuts.

Each shortcut acts on one zone: "Zone shown in Now Playing", or a zone named in
HOTKEY_ZONE. It seeds from that zone's current track (paused or stopped counts),
or, when Playing Now is empty, from the most recently played track in the
library. The build runs through the Play tab like a voice command, with the
settings of the Alexa device mapped to that zone if it has its own.

Uses Windows' own RegisterHotKey on a small thread of its own, so there's
nothing to install and no admin rights needed. On other systems it does nothing.

  .env: HOTKEY_ZONE=<zone name, blank for the Now Playing zone>
        HOTKEY_SIMILAR_TRACKS=Ctrl+Alt+1   (and _SIMILAR_ARTISTS, _TOP_TRACKS, _SHUFFLE_ARTIST)
"""

import os
import sys
import threading

import engine

ACTIONS = [   # (code, label): the order they appear in Settings
    ("SIMILAR_TRACKS", "Similar Tracks"),
    ("SIMILAR_ARTISTS", "Similar Artists"),
    ("TOP_TRACKS", "Artist's Top Tracks"),
    ("SHUFFLE_ARTIST", "Shuffle Songs by Artist"),
    ("SWITCH_ZONES", "Switch Zones"),
    ("SWITCH_PROFILES", "Switch Profiles"),
    ("KEEP_GOING", "Keep It Going"),
]
LABELS = dict(ACTIONS)
NOW_PLAYING_ZONE = "Zone shown in Now Playing"

AVAILABLE = sys.platform.startswith("win")

# --- keys ---------------------------------------------------------------------
# Modifier names in the order they're written, and their RegisterHotKey flags
MODIFIERS = [("Ctrl", 0x0002), ("Alt", 0x0001), ("Shift", 0x0004), ("Win", 0x0008)]
MOD_NOREPEAT = 0x4000            # holding a key down fires once, not over and over
MODIFIER_VKS = {0x10: "Shift", 0xA0: "Shift", 0xA1: "Shift", 0x11: "Ctrl", 0xA2: "Ctrl", 0xA3: "Ctrl",
                0x12: "Alt", 0xA4: "Alt", 0xA5: "Alt", 0x5B: "Win", 0x5C: "Win"}


def _key_names():
    """Key name -> Windows virtual-key code, for the keys a shortcut can use."""
    names = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
    names.update({str(d): 0x30 + d for d in range(10)})
    names.update({f"F{n}": 0x6F + n for n in range(1, 25)})
    names.update({f"Num{d}": 0x60 + d for d in range(10)})
    names.update({"NumMultiply": 0x6A, "NumAdd": 0x6B, "NumSubtract": 0x6D, "NumDecimal": 0x6E, "NumDivide": 0x6F,
                  "Space": 0x20, "PageUp": 0x21, "PageDown": 0x22, "End": 0x23, "Home": 0x24,
                  "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "Insert": 0x2D, "Delete": 0x2E,
                  "MediaNext": 0xB0, "MediaPrevious": 0xB1, "MediaStop": 0xB2, "MediaPlayPause": 0xB3,
                  "BrowserBack": 0xA6, "BrowserForward": 0xA7, "BrowserRefresh": 0xA8, "BrowserHome": 0xAC,
                  "LaunchMail": 0xB4, "LaunchMedia": 0xB5, "LaunchApp1": 0xB6, "LaunchApp2": 0xB7})
    return names


KEY_NAMES = _key_names()
VK_NAMES = {vk: name for name, vk in KEY_NAMES.items()}


def key_name(vk):
    """A virtual-key code's name for a shortcut, or None if it can't be used."""
    return VK_NAMES.get(vk)


def combo_text(mods, vk):
    """('Ctrl', 'Alt'), 0x31 -> 'Ctrl+Alt+1'. Modifiers always in the same order."""
    order = [m for m, _ in MODIFIERS if m in mods]
    return "+".join(order + [key_name(vk)])


def needs_modifier(vk):
    """Plain letters, numbers and the like would take over typing everywhere, so they need Ctrl, Alt, Shift or Win."""
    name = key_name(vk) or ""
    return not (name.startswith("F") and name[1:].isdigit()) and not name.startswith(("Media", "Browser", "Launch"))


def parse(text):
    """'Ctrl+Alt+1' -> (modifier flags, virtual-key code), or None if it isn't a shortcut."""
    parts = [p.strip() for p in (text or "").split("+")]
    if not parts or not parts[-1]:
        return None
    flags = 0
    for part in parts[:-1]:
        flag = dict(MODIFIERS).get(part)
        if flag is None:
            return None
        flags |= flag
    vk = KEY_NAMES.get(parts[-1]) or KEY_NAMES.get(parts[-1].upper())
    if vk is None or (not flags and needs_modifier(vk)):
        return None
    return flags, vk


def assigned():
    """{action code: 'Ctrl+Alt+1'} for every shortcut set in .env."""
    engine.refresh_settings_if_changed()
    out = {}
    for code, _ in ACTIONS:
        value = os.getenv(f"HOTKEY_{code}", "").strip()
        if value:
            out[code] = value
    return out


def target_zone_setting():
    """The zone named in Settings, or '' for the zone shown in Now Playing."""
    engine.refresh_settings_if_changed()
    return os.getenv("HOTKEY_ZONE", "").strip()


# --- the listener thread ----------------------------------------------------------

_submit = None          # set by the GUI: submit(job, heading) queues a build on the Play tab
_listener = None
_errors = {}            # action code -> why Windows wouldn't take its shortcut
_lock = threading.Lock()


if AVAILABLE:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.RegisterHotKey.restype = wintypes.BOOL
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wintypes.BOOL
    _user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    _user32.GetMessageW.restype = wintypes.BOOL
    _user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT,
                                     wintypes.UINT, wintypes.UINT]
    _user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    WM_HOTKEY, WM_QUIT = 0x0312, 0x0012


class _Listener(threading.Thread):
    """Registers the shortcuts and waits for Windows to say one was pressed."""

    def __init__(self, combos):
        super().__init__(daemon=True, name="24bit7 shortcuts")
        self.combos = combos
        self.errors = {}
        self.ready = threading.Event()
        self.thread_id = None

    def run(self):
        self.thread_id = _kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # gives this thread its message queue
        ids = {}
        for n, (code, text) in enumerate(self.combos.items(), start=1):
            parsed = parse(text)
            if not parsed:
                self.errors[code] = f"'{text}' isn't a shortcut 24bit7 can use."
                continue
            flags, vk = parsed
            if _user32.RegisterHotKey(None, n, flags | MOD_NOREPEAT, vk):
                ids[n] = code
            else:
                err = _kernel32.GetLastError()
                why = ("another program already uses this shortcut" if err == 1409
                       else f"Windows error {err}")
                self.errors[code] = f"Windows refused it: {why}."
        self.ready.set()
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in ids:
                    _pressed(ids[msg.wParam])
        finally:
            for n in ids:
                _user32.UnregisterHotKey(None, n)

    def stop(self):
        if self.thread_id:
            _user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        self.join(2)


_busy = None            # set by the GUI: True while a build is running or waiting
_note = None            # set by the GUI: writes a line to the console straight away
_restart_wanted = False   # Switch Profiles asked for a restart once its job is done


def attach(submit, busy=None, note=None):
    """The GUI hands over how to queue a build on the Play tab, how to tell it's busy, and its console."""
    global _submit, _busy, _note
    _submit, _busy, _note = submit, busy, note


def take_restart():
    """True once, after Switch Profiles has queued a profile: the GUI then restarts 24bit7."""
    global _restart_wanted
    wanted, _restart_wanted = _restart_wanted, False
    return wanted


def stop():
    """Releases every shortcut (also while one is being set in Settings, so pressing it doesn't fire it)."""
    global _listener
    with _lock:
        if _listener is not None:
            _listener.stop()
            _listener = None


def restart():
    """Registers the shortcuts in .env. Returns {action code: problem} for any Windows wouldn't take."""
    global _listener, _errors
    stop()
    if not AVAILABLE:
        _errors = {}
        return _errors
    combos = assigned()
    with _lock:
        if not combos:
            _errors = {}
            return _errors
        _listener = _Listener(combos)
        _listener.start()
        _listener.ready.wait(3)
        _errors = dict(_listener.errors)
    for code, problem in _errors.items():
        print(f"[Shortcuts] {LABELS[code]} ({combos[code]}): {problem}")
    return _errors


def errors():
    return dict(_errors)


# --- what a shortcut does -----------------------------------------------------------

def _pressed(code):
    """Runs on the listener thread: queue the build on the Play tab and get straight back to listening."""
    if _submit is None:
        return
    if code == "SWITCH_PROFILES" and _busy is not None and _note is not None and _busy():
        _note("Switch Profiles requested: it will switch once the current build has finished.")
    _submit(_job(code), f"Shortcut: {LABELS[code]}", {"from": "shortcut"})


def _device_for_zone(zone_name):
    """(device ID, name, own settings) for the Alexa device on this zone with Own settings ticked, else (None, None, {})."""
    try:
        import voice
        for device_id, name, zone, _, own in voice.devices():
            if zone == zone_name and own:
                return device_id, name, voice.device_profile(device_id)
    except Exception:
        pass
    return None, None, {}


def _switch_profiles(report):
    """Loads the next profile ticked under Enable Switch To; 24bit7 restarts once this job is done."""
    global _restart_wanted
    import profiles
    target, problem = profiles.switch_target()
    if problem:
        report(f"  Problem: {problem}")
        return
    current = profiles.current()
    if current and profiles.changed(current):
        report(f'  Note: settings changed since "{current}" was loaded weren\'t saved to it.')
    try:
        profiles.queue_load(target)
    except Exception as e:
        report(f"  Problem: couldn't load the profile ({e}).")
        return
    report(f'  Switching to the profile "{target}". 24bit7 restarts to apply it; JRiver keeps playing.')
    _restart_wanted = True


def _job(code):
    def run(report):
        if code == "SWITCH_PROFILES":   # no zone or seed needed
            _switch_profiles(report)
            return
        engine.refresh_settings_if_changed()
        wanted = target_zone_setting()
        if wanted:
            zid = engine.zone_id(wanted)
            if zid is None:
                report(f"  Problem: the shortcut zone '{wanted}' isn't in JRiver. Pick another under "
                       f"Settings > Other > Keyboard Shortcuts.")
                return
        else:
            zid = engine.seed_zone()
            if zid is None:
                report("  Problem: the Now Playing zone isn't in JRiver, so the shortcut did nothing.")
                return
            if zid == engine.ACTIVE_ZONE:
                zid = engine.zone_id()
        zone_name = engine.zone_label(zid)
        if code == "SWITCH_ZONES":   # the zones ticked under Enable Switch To, in turn
            import voice
            report(voice.switch_step(zone_name))
            return
        if code == "KEEP_GOING":   # Non-stop, once, for whatever this zone is playing
            import voice
            status, speech, _ = voice.keep_going(zone_name)
            report(f"  Problem: {speech}" if status == "problem" else f"  {speech}")
            return
        seed = engine.seed_or_last_played(zid, report)
        if not seed:
            return
        device_id, device_name, profile = _device_for_zone(zone_name)
        report(f"  Zone: {zone_name}" + (f", with {device_name}'s own settings" if profile else ""))
        if code == "SHUFFLE_ARTIST":
            import voice
            artist = (engine.split_values(seed.get("Artist")) or [""])[0]
            if not artist or artist == "Unknown":
                report("  The seed track has no artist, so there's nothing to shuffle.")
                return
            status, speech, _ = voice._play_now("shuffle", artist, zone_name, device_id)
            report(f"  {speech}")
            return
        try:
            engine.OUTPUT_OVERRIDE = zone_name
            engine.use_profile(profile)
            import filters
            engine.FILTER_DEVICE = filters.device_for_zone(zone_name)
            if code == "SIMILAR_TRACKS":
                engine.create_similar_tracks_playlist(report=report, seed_info=seed)
            elif code == "SIMILAR_ARTISTS":
                engine.create_similar_playlist(report=report, seed_info=seed)
            elif code == "TOP_TRACKS":
                engine.play_top_n(report=report, seed_info=seed)
        finally:
            engine.OUTPUT_OVERRIDE = None
            engine.use_profile(None)
            engine.FILTER_DEVICE = None
    return run
