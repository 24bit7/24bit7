"""
24bit7 - Settings tab.

A frame (embedded in the main window's notebook) that reads current values from
.env, presents them as sub-tabbed controls, and auto-saves changes back to .env
whenever a control changes. Comments, blank lines and unmanaged keys are
preserved; only managed keys are updated or appended. Text fields save when
focus leaves them (so half-typed keys aren't written); checkboxes and dropdowns
save immediately. The engine picks up the file via its .env mod-time check.
Each page is made of boxed sections; a setting's explanation sits behind a small
? beside it, shown while the pointer is over it.
"""

import os
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox, simpledialog, filedialog

import engine
import tray
import voice
import hotkeys
import saved_playlists
import filters
from tabs import TabbedPane, PALETTE

ENV_FILE = engine.ENV_FILE   # single source of truth for where .env lives

# The Voice Commands guides, on GitHub (linked from the bottom of Settings > Voice Commands)
DOCS_URL = "https://github.com/24bit7/24bit7/blob/main/docs/"
VOICE_DOCS = [("How Voice Commands work", DOCS_URL + "MANUAL.md#voice-commands",
               "What it does, what you can say, and settings per device."),
              ("Setting up the Alexa skill", DOCS_URL + "MANUAL.md#setting-up-the-alexa-skill",
               "Step by step, from an Amazon developer account to your first command.")]

# --- About tab -------------------------------------------------------------
REPO_URL = "https://github.com/24bit7/24bit7"
FORUM_URL = "https://yabb.jriver.com/interact/index.php/topic,144381.0.html"   # the JRiver forum thread; empty hides the link
MANUAL_PDF = "24bit7_Manual.pdf"   # shipped next to 24bit7.exe in the release zip
# The voice commands, as in the manual's Voice Commands chapter
VOICE_COMMAND_LIST = [
    ("songs by <artist>", "Artist's Top Tracks"),
    ("music like <artist>", "Similar Artists, seeded from the artist's most popular track"),
    ("tracks like <song>  (by <artist>)", "Similar Tracks"),
    ("genre <anything>", "AI Playlist, e.g. \"genre nu metal with grunge\" (needs an Anthropic key)"),
    ("album <name>", "Plays the album now, in track order"),
    ("song <title>  (by <artist>)", "Plays the song now, then stops"),
    ("playlist <name>", "Plays one of your JRiver playlists or smartlists now"),
    ("shuffle songs by <artist>", "Every track by the artist in your library, shuffled"),
    ("skip / next / next song", "The next track in that device's zone"),
    ("who is this / what's playing", "Alexa says the track, artist and album"),
    ("more like this / more of this", "Similar Tracks seeded from what's playing"),
]
CREDITS = [
    ("Last.fm", "https://www.last.fm"),
    ("ListenBrainz", "https://listenbrainz.org"),
    ("MusicBrainz", "https://musicbrainz.org"),
    ("Deezer", "https://www.deezer.com"),
    ("YouTube Music (via ytmusicapi)", "https://github.com/sigma67/ytmusicapi"),
    ("Discogs", "https://www.discogs.com"),
    ("Anthropic (Claude)", "https://www.anthropic.com"),
    ("JRiver Media Center", "https://jriver.com"),
]


# Listed alphabetically by display name
SOURCE_NAMES = [("ai", "AI"), ("deezer", "Deezer"),
                ("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"),
                ("youtube", "YouTube")]
# YouTube suggests artists only, so it isn't offered as a top-track source
TOP_SOURCE_NAMES = [s for s in SOURCE_NAMES if s[0] != "youtube"]
# Sources that can suggest tracks like a track
TRACK_SOURCE_NAMES = [("ai", "AI"), ("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"), ("youtube", "YouTube")]


KEY_HELP = {
    "LASTFM_API_KEY": ("Last.fm API key",
        "Create an API account at last.fm/api (Get an API account).\n"
        "Your key is shown on your account's API page. It's free."),
    "LISTENBRAINZ_TOKEN": ("ListenBrainz token",
        "Sign in at listenbrainz.org (uses a MusicBrainz account),\n"
        "then copy your User Token from listenbrainz.org/settings."),
    "DISCOGS_TOKEN": ("Discogs token",
        "Go to discogs.com/settings/developers and click\n"
        "'Generate new token' under Personal access token."),
    "ANTHROPIC_API_KEY": ("Anthropic API key",
        "At platform.claude.com, add billing credit under Settings,\n"
        "then create a key under API keys. Copy it once at creation."),
    "JRIVER_PASS": ("JRiver Media Network",
        "Set the username and password in JRiver under\n"
        "Tools > Options > Media Network > Authentication."),
}

KEY_FIELDS = ["LASTFM_API_KEY", "LISTENBRAINZ_TOKEN", "DISCOGS_TOKEN",
              "ANTHROPIC_API_KEY", "JRIVER_USER", "JRIVER_PASS"]

NO_KEY_TEXT = "You need to add an Anthropic key to use this function"
CONSOLE_QUERY_WARNING = ("Console Query sends the console, your settings (without keys) and 24bit7's "
                         "code to Claude each time you ask a question. The first question costs a few "
                         "pence, more than the AI Moderator.\n\nTurn it on?")
MODERATOR_CHOICES = ["Off", "Relaxed", "Balanced", "Strict"]
MODERATOR_LEVELS_HELP = (
    "Relaxed: removes only clear clashes, at most a fifth of the tracks.\n"
    "Balanced: removes anything that noticeably shifts the tone, energy or mood, at most two fifths.\n"
    "Strict: keeps only tracks close to the seed, however many that leaves. Drift can top a short "
    "playlist up.\n"
    "Tracks it doesn't know well enough to judge are always kept, and genre is never a reason on its own.")
MODERATOR_WARNING = ("AI Moderator checks each playlist using the Anthropic API, which uses credits "
                     "from your Anthropic account. Each playlist costs a fraction of a penny.")


class Tooltip:
    """A small note shown while the pointer is over a widget, or on a click, when when() says so."""

    def __init__(self, widget, text, when=lambda: True):
        self.widget, self.text, self.when, self.tip = widget, text, when, None
        widget.bind("<Enter>", lambda e: self.show(), add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        widget.bind("<Button-1>", lambda e: self.show(), add="+")
        widget.bind("<Destroy>", lambda e: self.hide(), add="+")

    def show(self):
        if self.tip or not self.when():
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg=PALETTE["tooltip_bg"], fg=PALETTE["tooltip_fg"], relief="solid", borderwidth=1, justify="left",
                 wraplength=460, font=("Segoe UI", 9), padx=8, pady=5).pack()

    def hide(self):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def warn_moderator_once(parent):
    """The one-off credits warning, the first time AI Moderator is switched on anywhere."""
    if engine.MODERATOR_WARNED:
        return
    messagebox.showinfo("AI Moderator", MODERATOR_WARNING, parent=parent)
    write_env({"MODERATOR_WARNED": "1"})
    engine.MODERATOR_WARNED = True


HEADING_FONT = ("Segoe UI", 10, "bold")
HELP_FONT = ("Segoe UI", 8)
HELP_FG = "#666"
LABEL_FONT = ("Segoe UI", 9, "bold")
SECTION_FG = "#1f4e8c"    # section titles, in the logo blue
SECTION_EDGE = "#aab4c3"  # the thin line round each section
HELP_MARK_BG = "#8a97aa"


def help_mark(parent, text):
    """A small ? that shows text in a popup while the pointer is over it."""
    mark = tk.Label(parent, text="?", font=("Segoe UI", 8, "bold"), fg=PALETTE["help_mark_fg"], bg=PALETTE["help_mark_bg"],
                    width=2, cursor="question_arrow")
    Tooltip(mark, text)
    return mark


def section(parent, title, help_text=None, row=None, title_fg=None):
    """
    A boxed section: a thin rectangle with its title (and optional ?) on the top
    edge. Returns the box to build the section's controls in. Stacked with grid
    in column 0 of parent, one under another, or at row if given.
    """
    box = tk.LabelFrame(parent, bd=0, padx=14, pady=10, highlightthickness=1,
                        highlightbackground=PALETTE["section_edge"], highlightcolor=PALETTE["section_edge"])
    head = tk.Frame(box)
    tk.Label(head, text=title, font=HEADING_FONT, fg=title_fg or PALETTE["section_fg"]).pack(side="left")
    if help_text:
        help_mark(head, help_text).pack(side="left", padx=(6, 0))
    box.configure(labelwidget=head)
    if row is None:
        row = parent.grid_size()[1]
    box.grid(row=row, column=0, sticky="ew", pady=(0, 14))
    parent.grid_columnconfigure(0, weight=1)
    return box


def read_env():
    values = {}
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def write_env(updates):
    """
    Updates managed keys in place, preserving comments, blanks and unmanaged
    keys. A key whose value is None is removed from the file.
    """
    removals = {k for k, v in updates.items() if v is None}
    updates = {k: v for k, v in updates.items() if v is not None}
    lines = []
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    seen = set()
    out = []
    for line in lines:
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in removals:
                continue
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    appended = [f"{k}={v}" for k, v in updates.items() if k not in seen]
    if appended:
        if out and out[-1].strip():
            out.append("")
        out.extend(appended)
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


class ProfilePage:
    """
    One Sources or Playlist tab: Windows (Main) (device_id None), or a device's.
    Holds its values (env), its controls (vars) and how it saves, so the same
    builder fills every tab.
    """

    def __init__(self, kind, device_id, env, vars_, save):
        self.kind, self.device_id, self.env, self.vars, self.save = kind, device_id, env, vars_, save
        self.loading, self.body, self.resync = False, None, lambda: None

    def values(self):
        """The tab's settings as .env strings, for Main's .env or a device's own copy."""
        if self.kind == "saved":   # the Saved Playlists page keeps its own table
            return self.collect()
        v = self.vars
        if self.kind == "sources":
            out = {group: ",".join(code for code, tick in v[group].items() if tick.get())
                   for group in ("SIMILAR_SOURCES", "SIMILAR_TRACK_SOURCES", "TOP_TRACK_SOURCES")}
            for key in ("SIMILAR_MIN_AGREEMENT", "SIMILAR_TRACK_MIN_AGREEMENT"):
                out[key] = "1" if v[key].get() == "Off" else v[key].get()
            for key in ("LISTENBRAINZ_ALGORITHM", "LISTENBRAINZ_TRACK_ALGORITHM"):
                out[key] = v[key].get()
            for group in engine.MODERATOR_GROUPS:
                key = f"AI_MODERATOR_{group.upper()}"
                if key in v:   # Windows (Main) sets these on the Play tab
                    out[key] = v[key].get().lower()
            return out
        out = {key: v[key].get().strip() for key in PLAYLIST_TEXT_KEYS}
        for group, (on, using, rounds, _) in self.drift.items():
            name = f"DRIFT_{group.upper()}"
            out[name] = "1" if on.get() else "0"
            out[f"{name}_USING"] = option_code(drift_using_options(group), using.get())
            if f"{name}_SOURCES_MODE" in v:
                out[f"{name}_SOURCES_MODE"] = option_code(DRIFT_SOURCE_MODES, v[f"{name}_SOURCES_MODE"].get())
                for kind in ("ARTIST", "TRACK"):
                    out[f"{name}_{kind}_SOURCES"] = ",".join(
                        code for code, tick in v[f"{name}_{kind}_SOURCES"].items() if tick.get())
                    agree = v[f"{name}_{kind}_AGREE"].get()
                    out[f"{name}_{kind}_AGREE"] = "1" if agree == "Off" else agree
            out[f"{name}_ROUNDS"] = rounds.get()
        if "AI_MODERATOR_VIBE" in v:
            out["AI_MODERATOR_VIBE"] = v["AI_MODERATOR_VIBE"].get().lower()
        for group in engine.PLAYED_GROUPS:
            g = group.upper()
            out[f"SKIP_PLAYED_{g}"] = "1" if v[f"SKIP_PLAYED_{g}"].get() else "0"
            out[f"SKIP_LONG_CLOSERS_{g}"] = "1" if v[f"SKIP_LONG_CLOSERS_{g}"].get() else "0"
            out[f"LONG_CLOSER_MINUTES_{g}"] = v[f"LONG_CLOSER_MINUTES_{g}"].get().strip()
            out[f"NONSTOP_{g}"] = "1" if v[f"NONSTOP_{g}"].get() else "0"
            out[f"NONSTOP_{g}_RESEED"] = option_code(NONSTOP_RESEED_OPTIONS, v[f"NONSTOP_{g}_RESEED"].get())
            out[f"RUN_AFTER_{g}"] = "1" if v[f"RUN_AFTER_{g}"].get() else "0"
            out[f"RUN_AFTER_{g}_PATH"] = v[f"RUN_AFTER_{g}_PATH"].get().strip()
            if group != "vibe":
                out[f"NONSTOP_{g}_USING"] = option_code(NONSTOP_USING_OPTIONS, v[f"NONSTOP_{g}_USING"].get())
        out["NONSTOP_VIBE_WITH"] = option_code(NONSTOP_WITH_OPTIONS, v["NONSTOP_VIBE_WITH"].get())
        out["NONSTOP_TOP_REST"] = "1" if v["NONSTOP_TOP_REST"].get() else "0"
        out["NONSTOP_TOP_REST_COUNT"] = v["NONSTOP_TOP_REST_COUNT"].get().strip().lower()
        return out


# Playlist settings saved as typed (spin boxes and dropdowns)
PLAYLIST_TEXT_KEYS = ["SIMILAR_ARTIST_TRACK_COUNT", "SIMILAR_ARTIST_LIMIT", "TRACKS_PER_ARTIST_POOL",
                      "TRACKS_PER_ARTIST_PICK", "SIMILAR_TRACK_COUNT", "SIMILAR_TRACK_PER_ARTIST",
                      "SIMILAR_TRACK_ORDER", "TOP_TRACKS_COUNT", "TOP_TRACKS_ORDER", "VIBE_TRACK_COUNT",
                      "SKIP_PLAYED_ARTISTS_DAYS", "SKIP_PLAYED_TRACKS_DAYS",
                      "SKIP_PLAYED_TOP_DAYS", "SKIP_PLAYED_VIBE_DAYS"]

# Drift using: (saved value, label shown). AI is for vibe playlists only, and never the default.
DRIFT_USING_OPTIONS = [("artists", "Similar artists"), ("tracks", "Similar tracks"), ("ai", "AI")]
# AI Playlist's Drift choices say plainly which ones use the AI
VIBE_DRIFT_USING_OPTIONS = [("artists", "Similar artists (no AI)"), ("tracks", "Similar tracks (no AI)"),
                            ("ai", "AI (uses credits)")]
DRIFT_SOURCE_MODES = [("same", "Same as Settings > Sources"), ("custom", "Custom Sources")]
DRIFT_ARTIST_SOURCE_NAMES = [s for s in SOURCE_NAMES if s[0] != "ai"]   # Drift from the sources never uses the AI
DRIFT_SOURCES_HELP = ("Same as Settings > Sources uses the sources you picked for this Play option. Custom "
                      "Sources lets the top-up rounds use different ones, for example steadier sources first "
                      "and more adventurous ones to fill the gaps.")


def drift_using_options(group):
    """The Drift using choices for a Play option (AI only for AI Playlist)."""
    return VIBE_DRIFT_USING_OPTIONS if group == "vibe" else DRIFT_USING_OPTIONS[:2]

# The Play options, as the tabs inside Sources and Playlist
PLAY_OPTIONS = [("artists", "Similar Artists"), ("tracks", "Similar Tracks"),
                ("top", "Artist's Top Tracks"), ("vibe", "AI Playlist")]

# Non-stop dropdowns: (saved value, label shown)
NONSTOP_USING_OPTIONS = [("artists", "Similar artists"), ("tracks", "Similar tracks")]
NONSTOP_RESEED_OPTIONS = [("last", "Last track"), ("second", "2nd track")]
NONSTOP_WITH_OPTIONS = [("vibe", "More from the AI"), ("artists", "Similar artists"), ("tracks", "Similar tracks")]
# Saved Playlists dropdowns
SAVED_NONSTOP_OPTIONS = [("no", "No"), ("artists", "Similar artists"), ("tracks", "Similar tracks")]
SAVED_SKIP_OPTIONS = [("0", "Off"), ("1", "1 day"), ("2", "2 days"), ("3", "3 days"), ("7", "7 days"),
                      ("14", "14 days"), ("30", "30 days")]
ALL_FOLDERS = "All folders"   # the JRiver Playlists folder filter's first choice


def table_colours():
    """(heading, odd row, even row) backgrounds for the Saved Playlists table, light or dark."""
    import tabs
    if tabs.THEME == "dark":
        return "#000000", "#1f2023", "#2a2c30"
    return "#e4e4e4", "#ffffff", "#f4f4f4"


# The ? beside each Number of tracks
TARGET_HELP = 'This is the target number of tracks. The playlist may come out shorter, depending on how many matches are in your library. If your playlists are often too short, tick Drift to fill them out.'
TOP_TARGET_HELP = "This is the target number of tracks. The playlist may come out shorter, depending on how many of the artist's top tracks are in your library."


def option_code(options, label):
    """A dropdown's label back to the value saved in .env (the first option if it's not recognised)."""
    return next((code for code, shown in options if shown == label), options[0][0])


def option_label(options, code):
    return dict(options).get(code, options[0][1])

def drift_values(env, group):
    """A group's Drift settings from a tab's values, or Main's (with its carried-over top-up) if unset."""
    name = f"DRIFT_{group.upper()}"
    if name not in env:
        return engine.DRIFT[group]
    rounds = env.get(f"{name}_ROUNDS", "3")
    return {"on": env[name].strip().lower() in ("1", "true", "yes"),
            "using": {"tracks": "tracks", "ai": "ai"}.get(env.get(f"{name}_USING", ""), "artists")
                     if group == "vibe" else ("tracks" if env.get(f"{name}_USING", "") == "tracks" else "artists"),
            "rounds": int(rounds) if rounds.isdigit() else 3}


def set_enabled(widget, enabled):
    """Greys out (or brings back) every control inside widget. The ? marks stay live."""
    for child in widget.winfo_children():
        if isinstance(child, tk.Label) and child.cget("text") == "?":
            continue
        if isinstance(child, ttk.Widget):
            try:
                child.state(["!disabled"] if enabled else ["disabled"])
            except tk.TclError:
                pass
        elif isinstance(child, (tk.Label, tk.Spinbox, tk.Entry, tk.Checkbutton, tk.Button)):
            try:
                child.config(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass
        set_enabled(child, enabled)


def sync_agreement(p, sources_key, agree_key, box_name, most):
    """Off, 2 ... the number of ticked sources (at most `most`); greyed out below two."""
    box = getattr(p, box_name)
    ticked = sum(1 for v in p.vars[sources_key].values() if v.get())
    if ticked < 2:
        box.config(state="disabled")
        return
    options = ["Off"] + [str(n) for n in range(2, min(ticked, most) + 1)]
    box.config(values=options, state="readonly")
    if p.vars[agree_key].get() not in options:
        p.vars[agree_key].set(options[-1])


def sync_drift(p):
    """Drift using and Rounds grey out while their Drift tick is off."""
    for on, _, _, boxes in p.drift.values():
        for cb in boxes:
            cb.config(state="readonly" if on.get() else "disabled")
    sync_drift_sources(p)
    # AI Playlist's moderator: only for Drift from the sources, and only with an Anthropic key
    mod_cb = getattr(p, "vibe_mod_cb", None)
    if mod_cb is not None and "vibe" in p.drift:
        on, using, _, _ = p.drift["vibe"]
        ok = (on.get() and option_code(drift_using_options("vibe"), using.get()) != "ai"
              and bool(engine.ANTHROPIC_API_KEY))
        mod_cb.config(state="readonly" if ok else "disabled")


def sync_drift_sources(p):
    """Drift sources: hidden when Drift uses the AI; the ticks only with Custom Sources, following Drift using."""
    for group, (mode, mode_row, panel, frames) in getattr(p, "drift_src", {}).items():
        _, using, _, _ = p.drift[group]
        code = option_code(drift_using_options(group), using.get())
        if code == "ai":
            mode_row.grid_remove()
            panel.grid_remove()
            continue
        mode_row.grid()
        if option_code(DRIFT_SOURCE_MODES, mode.get()) != "custom":
            panel.grid_remove()
            continue
        panel.grid()
        for kind, frame in frames.items():
            if (kind == "ARTIST") == (code == "artists"):
                frame.pack(anchor="w")
            else:
                frame.pack_forget()


def sync_played(p):
    """Each group's days box greys out while its Skip recently played tick is off."""
    for group, box in p.played_boxes.items():
        box.config(state="normal" if p.vars[f"SKIP_PLAYED_{group.upper()}"].get() else "disabled")


def sync_long_closers(p):
    """Each option's minutes box greys out while its Hidden Tracks tick is off."""
    for g, sb in p.closer_sbs.items():
        sb.config(state="normal" if p.vars[f"SKIP_LONG_CLOSERS_{g}"].get() else "disabled")


def sync_nonstop(p):
    """Each option's Non-stop choices grey out while it's off; the song count while its own tick is off."""
    for g, (body, rest_cb) in p.nonstop_parts.items():
        on = p.vars[f"NONSTOP_{g}"].get()
        set_enabled(body, on)
        if rest_cb is not None:
            rest_cb.state(["!disabled"] if on and p.vars["NONSTOP_TOP_REST"].get() else ["disabled"])


def sync_pick_limit(p):
    """
    Keeps 'tracks per artist selection' from exceeding 'number of artist's top
    tracks': the selection's ceiling follows the pool, and the selection is
    clamped down if the pool drops below it. Ignores half-typed values.
    """
    try:
        pool = max(1, int(p.vars["TRACKS_PER_ARTIST_POOL"].get()))
    except (ValueError, KeyError):
        return
    p.pick_sb.config(to=pool)
    try:
        pick = int(p.vars["TRACKS_PER_ARTIST_PICK"].get())
    except ValueError:
        return
    if pick > pool:
        p.vars["TRACKS_PER_ARTIST_PICK"].set(str(pool))   # its trace saves


class SettingsTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.env = read_env()
        self.vars = {}
        self._source_boxes = []   # (tick, code, label, purpose) for the "(no key yet)" marks
        self._loading = True   # suppress auto-save while building controls
        self._option_tab_choice = {}   # the Play option tab last open under Sources and Playlist

        nb = TabbedPane(self, font=("Segoe UI", 10, "bold"), pad=(16, 6))
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_sources(nb)
        self._build_playlist(nb)
        self._build_filters(nb)
        self._build_search_sites(nb)
        self._build_keys(nb)
        self._build_voice(nb)
        self._build_saved(nb)   # after Voice Commands: these settings only apply to playlists asked for by voice
        self._build_other(nb)
        self._build_about(nb)

        self._loading = False
        self._refresh_key_marks()

    # --- persistence -------------------------------------------------------

    def _current_updates(self):
        # Sources and Playlist come from their Windows (Main) tabs; devices save their own
        updates = dict(self._main_sources.values())
        updates.update(self._main_playlist.values())
        for key in ["CACHE_DAYS", "JRIVER_HOST", "YOUTUBE_PLAYLIST_LENGTH"] + KEY_FIELDS:
            updates[key] = self.vars[key].get().strip()
        for group in ("DIGITAL_STORES", "REFERENCE_SITES"):
            updates[group] = ",".join(code for code, v in self.vars[group].items() if v.get())
        updates["DIGITAL_STORE"] = None   # pre-1.1.0 single-store key, superseded
        updates["LISTEN_SITES"] = ",".join(code for code, v in self.vars["LISTEN_SITES"].items() if v.get())
        for n in range(1, engine.CUSTOM_SITE_SLOTS + 1):
            name = self.vars[f"CUSTOM_SITE_{n}_NAME"].get().strip()
            url = self.vars[f"CUSTOM_SITE_{n}_URL"].get().strip()
            artist_only = self.vars[f"CUSTOM_SITE_{n}_MODE"].get() == "Artist only"
            # An empty row is removed from .env altogether, which keeps the file tidy
            updates[f"CUSTOM_SITE_{n}_NAME"] = name or None
            updates[f"CUSTOM_SITE_{n}_URL"] = url or None
            updates[f"CUSTOM_SITE_{n}_MODE"] = ("artist" if artist_only else "track") if (name or url) else None
        updates["DEBUG"] = None   # replaced by the console's Simple/Advanced switch in 1.11.0
        updates["CONSOLE_QUERY"] = "1" if self.vars["CONSOLE_QUERY"].get() else "0"
        updates["THEME"] = self.vars["THEME"].get().lower()
        updates["SIMILAR_REQUIRE_AGREEMENT"] = None   # old on/off key, superseded
        updates["SIMILAR_TRACK_TOPUP"] = None   # replaced by Drift in 1.4.0
        for key in ("START_IN_TRAY", "CLOSE_TO_TRAY", "PREFER_OFFICIAL_VIDEOS"):
            updates[key] = "1" if self.vars[key].get() else "0"
        return updates

    def _on_theme_changed(self, *_):
        """Saves the theme, then offers to restart so it takes effect."""
        self._save()
        choice = self.vars["THEME"].get().lower()
        if messagebox.askyesno("Theme", f"Restart 24bit7 now to switch to the {choice} theme?",
                               parent=self):
            self.winfo_toplevel().event_generate("<<Restart24bit7>>")

    def _refresh_key_marks(self):
        """Adds '(no key yet)' after a source whose key field is empty, and clears it once filled."""
        self._source_boxes = [b for b in self._source_boxes if b[0].winfo_exists()]   # device tabs rebuild theirs
        for box, code, label, purpose in self._source_boxes:
            key = {"lastfm": "LASTFM_API_KEY", "ai": "ANTHROPIC_API_KEY"}.get(code)
            if code == "listenbrainz" and purpose == "top":
                key = "LISTENBRAINZ_TOKEN"
            var = self.vars.get(key) if key else None
            missing = var is not None and not var.get().strip()
            try:
                box.config(text=label + ("  (no key yet)" if missing else ""))
            except tk.TclError:
                pass

    def _save(self, *_):
        """Auto-save. Skips writing empty source lists (keeps the last good file)."""
        if self._loading or self._main_sources.loading or self._main_playlist.loading:
            return
        self._refresh_key_marks()
        self._sync_moderator_box(self._main_sources)
        updates = self._current_updates()
        if (not updates["SIMILAR_SOURCES"] or not updates["TOP_TRACK_SOURCES"] or not updates["DIGITAL_STORES"]
                or not updates["SIMILAR_TRACK_SOURCES"]):
            return   # don't persist a no-sources / no-stores state; user is mid-change
        try:
            write_env(updates)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)

    # --- tabs --------------------------------------------------------------

    def _scroll_tab(self, nb, text):
        """
        A Settings page that scrolls (scrollbar and mouse wheel) when its content is
        taller than the window. Returns the inner frame to build on. The inner frame
        gets <<Shown>> each time the page is opened, in place of <Map>.
        """
        outer = tk.Frame(nb)
        nb.add(outer, text=text)
        return self._scroll_page(outer, fill_outer=False)

    def _scroll_page(self, outer, fill_outer=True):
        """The scrolling part of _scroll_tab, in any frame (a page with no tab row of its own)."""
        if fill_outer:
            holder = tk.Frame(outer)
            holder.pack(fill="both", expand=True)
            outer = holder
        canvas = tk.Canvas(outer, highlightthickness=0, bd=0, bg=outer.cget("bg"))
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, padx=12, pady=12)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        def wheel(e):
            if canvas.bbox("all") and canvas.bbox("all")[3] > canvas.winfo_height():
                canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        outer.bind("<Map>", lambda e: inner.event_generate("<<Shown>>"))
        return inner

    # --- Sources and Playlist: Windows (Main) and one tab per device --------

    def _line(self, box, r, label=None, pady=(4, 4)):
        """A row inside a section: an optional bold label, then whatever is packed into the frame returned."""
        row = tk.Frame(box)
        row.grid(row=r, column=0, columnspan=6, sticky="w", pady=pady)
        if label:
            tk.Label(row, text=label, font=LABEL_FONT).pack(side="left", padx=(0, 10))
        return row

    def _device_pane(self, nb, text, kind):
        """
        A top-level Settings page (Sources or Playlist). With no device ticked for
        Own settings under Voice Commands it's just the sections, as Windows (Main).
        With one or more, it holds a row of tabs: Windows (Main), then one per
        ticked device. Checked each time the page is opened.
        """
        outer = tk.Frame(nb)
        nb.add(outer, text=text)
        self._panes[kind] = {"outer": outer, "pane": None, "devices": {}, "main": None}
        self._layout_device_pane(kind, first=True)
        outer.bind("<Map>", lambda e: self._layout_device_pane(kind))
        return self._panes[kind]["main"]

    def _layout_device_pane(self, kind, first=False):
        """Builds the page with or without its tab row, rebuilding only when that changes."""
        info = self._panes[kind]
        wanted = bool(self._own_devices())
        if not first and wanted == (info["pane"] is not None):
            if wanted:
                self._sync_device_tabs(kind)
            return
        for child in info["outer"].winfo_children():
            child.destroy()
        info["devices"] = {}
        # A rebuild reads the saved values, as the page may have been changed since Settings opened
        if kind == "saved":   # kept in the database, not .env
            main = ProfilePage(kind, None, saved_playlists.main_settings(), {}, self._save_saved_main)
        else:
            env = self.env if first else read_env()
            main = ProfilePage(kind, None, env, self.vars, self._save)
        fill = self._filler(kind)
        if wanted:
            info["pane"] = TabbedPane(info["outer"], font=("Segoe UI", 9, "bold"), pad=(12, 4))
            info["pane"].pack(fill="both", expand=True, pady=(6, 0))
            fill(self._scroll_tab(info["pane"], "Windows (Main)"), main)
        else:
            info["pane"] = None
            fill(self._scroll_page(info["outer"]), main)
        info["main"] = main
        if kind == "sources":
            self._main_sources = main
        elif kind == "saved":
            self._main_saved = main
        else:
            self._main_playlist = main
        if wanted:
            self._sync_device_tabs(kind)

    def _own_devices(self):
        """device_id -> name, for devices ticked for Own settings under Voice Commands."""
        return {d[0]: d[1] for d in voice.devices() if d[4]}

    def _sync_device_tabs(self, kind):
        """Adds a tab for each device ticked for Own settings, and removes tabs for the rest."""
        info = self._panes[kind]
        pane, pages = info["pane"], info["devices"]
        wanted = self._own_devices()
        for device_id in [d for d in pages if d not in wanted]:
            pane.remove(pages.pop(device_id)["outer"])
        for device_id, name in wanted.items():
            if device_id in pages:
                pane.rename(pages[device_id]["outer"], name)
                continue
            inner = self._scroll_tab(pane, name)
            page = {"outer": inner.master.master, "inner": inner}
            pages[device_id] = page
            # rebuilt each time the tab is opened, once Tk has finished showing it
            page["outer"].bind("<Map>", lambda e, d=device_id: self.after_idle(
                lambda: self._fill_device_page(kind, d)), add="+")

    def _fill_device_page(self, kind, device_id):
        """
        (Re)builds a device's tab each time it's opened: the Copy Windows (Main)
        tick, then the same sections as Main. Copying, it shows Main's current
        values greyed out; otherwise the device's own.
        """
        page = self._panes[kind]["devices"].get(device_id)
        if not page:
            return
        inner = page["inner"]
        for child in inner.winfo_children():
            child.destroy()
        own = voice.device_page(device_id, kind)
        copying = own is None
        if kind == "saved":
            env = own if not copying else saved_playlists.main_settings()
        else:
            env = dict(read_env())
            if not copying:
                env.update(own)
        p = ProfilePage(kind, device_id, env, {}, lambda *_: None)
        p.save = lambda *_, p=p: self._save_device_page(p)
        copy_var = tk.BooleanVar(value=copying)
        head = tk.Frame(inner)
        head.grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Checkbutton(head, text="Copy Windows (Main)", variable=copy_var, style="Big.TCheckbutton",
                        command=lambda: self._copy_toggled(kind, device_id, p, copy_var.get())).pack(side="left")
        help_mark(head, "Ticked, this device uses the same settings as the Windows app, and follows any "
                        "change made there. Untick it to give this device settings of its own, starting "
                        "from a copy of the Windows ones.").pack(side="left", padx=(8, 0))
        body = tk.Frame(inner)
        body.grid(row=1, column=0, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)
        self._filler(kind)(body, p)
        p.body = body
        self._refresh_key_marks()
        if copying:
            set_enabled(body, False)

    def _copy_toggled(self, kind, device_id, p, copying):
        if copying:
            voice.set_device_page(device_id, kind, None)
            self._fill_device_page(kind, device_id)   # back to showing Main's values
            return
        voice.set_device_page(device_id, kind, p.values())
        set_enabled(p.body, True)
        p.resync()

    def _save_device_page(self, p):
        if p.loading or voice.device_page(p.device_id, p.kind) is None:
            return   # still building, or copying Main (nothing of its own to save)
        values = p.values()
        if p.kind == "sources" and not (values["SIMILAR_SOURCES"] and values["TOP_TRACK_SOURCES"]
                                        and values["SIMILAR_TRACK_SOURCES"]):
            return   # mid-change with every source unticked; keep the last good set
        voice.set_device_page(p.device_id, p.kind, values)

    def _build_sources(self, nb):
        ttk.Style(self).configure("Big.TCheckbutton", font=("Segoe UI", 11))
        self._panes = getattr(self, "_panes", {})
        self._main_sources = self._device_pane(nb, "Sources", "sources")

    def _build_playlist(self, nb):
        self._panes = getattr(self, "_panes", {})
        self._main_playlist = self._device_pane(nb, "Playlist", "playlist")

    def _build_saved(self, nb):
        self._panes = getattr(self, "_panes", {})
        self._main_saved = self._device_pane(nb, "JRiver Playlists", "saved")

    def _filler(self, kind):
        return {"sources": self._fill_sources, "playlist": self._fill_playlist, "saved": self._fill_saved}[kind]

    # --- the Filters page ---

    def _build_filters(self, nb):
        """A library of named filters on the left; the chosen one on the right."""
        tab = self._scroll_tab(nb, "Filters")
        self._filters = filters.load()
        self._filter_i = 0 if self._filters else None
        left = tk.Frame(tab)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        self._filter_right = tk.Frame(tab)
        self._filter_right.grid(row=0, column=1, sticky="nwe")
        tab.grid_columnconfigure(1, weight=1)

        box = section(left, "Your filters",
                      "Filters narrow the playlists 24bit7 builds (Similar Artists, Similar Tracks, Artist's Top "
                      "Tracks and AI Playlist), including Drift and non-stop top-ups. Each one applies to every Play "
                      "option on the devices it's ticked for. Where several apply, a track must pass them all. "
                      "Albums, songs, shuffles and JRiver playlists asked for by voice play as asked.")
        self._filter_list = tk.Listbox(box, height=8, width=26, activestyle="none", exportselection=False,
                                       font=("Segoe UI", 10))
        self._filter_list.grid(row=0, column=0, sticky="w")
        self._filter_list.bind("<<ListboxSelect>>", self._filter_picked)
        buttons = tk.Frame(box)
        buttons.grid(row=1, column=0, sticky="w", pady=(8, 0))
        for text, command in (("New", self._filter_new), ("Rename", self._filter_rename),
                              ("Duplicate", self._filter_duplicate), ("Delete", self._filter_delete)):
            tk.Button(buttons, text=text, width=7, command=command).pack(side="left", padx=(0, 3))
        box = section(left, "Active filters", "What applies where, from the filters that are on.")
        self._filter_summary = tk.Frame(box)
        self._filter_summary.grid(row=0, column=0, sticky="w")
        tab.bind("<<Shown>>", lambda e: self._filter_refresh(), add="+")
        self._filter_refresh()

    def _filter_devices(self):
        """[(value, label)] for Applies on: all, the Windows app, then each Alexa device."""
        # only speakers with their own settings: any other follows Windows (Main), as everywhere else
        return [(filters.ALL, "All devices"), (filters.MAIN, "Windows (Main)")] + filters.own_devices()

    def _filter_playlists(self):
        """[(id, label)] for Only pick from, from the JRiver Playlists table (read from JRiver if it's empty)."""
        rows = saved_playlists.main_settings()["rows"]
        if not rows:
            try:
                rows = saved_playlists.merge_scan(saved_playlists.main_settings(), saved_playlists.scan())["rows"]
            except Exception:
                rows = {}
        items = [(pid, f"{r.get('name') or pid}  ({r.get('folder') or saved_playlists.ROOT}, {r.get('type') or 'Playlist'})")
                 for pid, r in rows.items()]
        return [("", "None")] + sorted(items, key=lambda x: x[1].lower())

    def _filter_save(self):
        try:
            filters.save(self._filters)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        self._filter_fill_list()
        self._filter_fill_summary()

    def _filter_refresh(self):
        self._filter_fill_list()
        self._filter_fill_summary()
        self._filter_fill_editor()

    def _filter_fill_list(self):
        lb = self._filter_list
        lb.delete(0, "end")
        for item in self._filters:
            lb.insert("end", item["name"] + ("" if item.get("on") else "   (off)"))
        if self._filter_i is not None and self._filter_i < len(self._filters):
            lb.selection_set(self._filter_i)

    def _filter_fill_summary(self):
        frame = self._filter_summary
        for child in frame.winfo_children():
            child.destroy()
        r = 0
        for value, label in self._filter_devices()[1:]:
            names = [x["name"] for x in self._filters if filters.applies(x, None if value == filters.MAIN else value)]
            tk.Label(frame, text=label, font=LABEL_FONT, anchor="w").grid(row=r, column=0, sticky="w",
                                                                           pady=(4 if r else 0, 0))
            tk.Label(frame, text=", ".join(names) or "No filters", anchor="w", fg=PALETTE["help_fg"],
                     font=HELP_FONT, wraplength=230, justify="left").grid(row=r + 1, column=0, sticky="w")
            r += 2

    def _filter_picked(self, _e=None):
        chosen = self._filter_list.curselection()
        if chosen:
            self._filter_i = chosen[0]
            self._filter_fill_editor()

    def _filter_fill_editor(self):
        right = self._filter_right
        for child in right.winfo_children():
            child.destroy()
        if self._filter_i is None or self._filter_i >= len(self._filters):
            box = section(right, "No filter chosen")
            tk.Label(box, text="Click New to make your first filter.", fg=PALETTE["help_fg"],
                     font=HELP_FONT).grid(row=0, column=0, sticky="w")
            return
        item = self._filters[self._filter_i]
        keep = []

        box = section(right, item["name"])
        row = tk.Frame(box)
        row.grid(row=0, column=0, sticky="w")
        on = tk.BooleanVar(value=bool(item.get("on")))
        keep.append(on)

        def on_toggled():
            item["on"] = on.get()
            self._filter_save()
        ttk.Checkbutton(row, text="On", variable=on, command=on_toggled).pack(side="left")
        help_mark(row, "Off keeps the filter for later without it applying anywhere.").pack(side="left", padx=(8, 0))
        head = tk.Frame(box)
        head.grid(row=1, column=0, sticky="w", pady=(10, 2))
        tk.Label(head, text="Applies on", font=LABEL_FONT).pack(side="left")
        help_mark(head, "All devices covers the Play tab and every Alexa device. Windows (Main) is the Play tab, "
                        "plus any speaker without its own settings (Settings > Voice Commands > Own "
                        "settings), and shortcuts and non-stop on its zone. Speakers with their own settings "
                        "are listed by name.").pack(
            side="left", padx=(8, 0))
        devs = tk.Frame(box)
        devs.grid(row=2, column=0, sticky="w")
        ticks = {}

        def devices_changed():
            item["devices"] = [v for v, var in ticks.items() if var.get()]
            sync_devices()
            self._filter_save()

        def sync_devices():
            everything = ticks[filters.ALL].get()
            for value, (var, widget) in boxes.items():
                if value != filters.ALL:
                    widget.state(["disabled"] if everything else ["!disabled"])
        boxes = {}
        for n, (value, label) in enumerate(self._filter_devices()):
            var = tk.BooleanVar(value=value in item.get("devices", []))
            ticks[value] = var
            keep.append(var)
            tick = ttk.Checkbutton(devs, text=label, variable=var, command=devices_changed)
            tick.grid(row=n // 4, column=n % 4, sticky="w", padx=(0, 14), pady=1)
            boxes[value] = (var, tick)
        sync_devices()

        box = section(right, "Only pick from",
                      "Every playlist this filter applies to only uses tracks on this JRiver playlist or "
                      "smartlist. Set up any filtering you like in JRiver's smartlist editor, and 24bit7 "
                      "respects it. The list comes from Settings > JRiver Playlists.")
        options = self._filter_playlists()
        labels = dict(options)
        pick = tk.StringVar(value=labels.get(item.get("pick_from", ""), "None"))
        keep.append(pick)
        cb = ttk.Combobox(box, textvariable=pick, values=[l for _, l in options], state="readonly", width=44)
        cb.grid(row=0, column=0, sticky="w")

        def picked(_e=None):
            pid = next((p for p, l in options if l == pick.get()), "")
            item["pick_from"] = pid
            item["pick_name"] = pick.get().split("  (")[0] if pid else ""
            cb.selection_clear()
            self._filter_save()
        cb.bind("<<ComboboxSelected>>", picked)

        # --- Rules ---
        box = section(right, "Rules",
                      "Tracks must match all (or any) of the rules. A track with no value for a field passes that "
                      "rule, and the log counts them; an unrated track counts as rating 0, and an unplayed one "
                      "as played 0 times and never played. Rating 0 means unrated. Sample rate at most 48 kHz "
                      "saves JRiver converting on the fly for a Sonos.")
        top = tk.Frame(box)
        top.grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(top, text="Tracks must match").pack(side="left")
        match = tk.StringVar(value=item.get("match", "all"))
        keep.append(match)
        match_cb = ttk.Combobox(top, textvariable=match, values=["all", "any"], state="readonly", width=5)
        match_cb.pack(side="left", padx=6)
        tk.Label(top, text="of these rules").pack(side="left")

        def match_changed(_e=None):
            item["match"] = match.get()
            match_cb.selection_clear()
            self._filter_save()
        match_cb.bind("<<ComboboxSelected>>", match_changed)
        rows = tk.Frame(box)
        rows.grid(row=1, column=0, sticky="w")
        field_labels = [label for _, label, _, _ in filters.FIELDS]
        units = {"days": "days", "minutes": "minutes", "khz": "kHz"}

        def rule_row(r, rule):
            label, ops, kind = filters.FIELD_INFO[rule["field"]]
            field = tk.StringVar(value=label)
            op = tk.StringVar(value=dict(ops).get(rule.get("op"), ops[0][1]))
            keep.extend([field, op])
            field_cb = ttk.Combobox(rows, textvariable=field, values=field_labels, state="readonly", width=13)
            field_cb.grid(row=r, column=0, sticky="w", pady=3)
            op_cb = ttk.Combobox(rows, textvariable=op, values=[l for _, l in ops], state="readonly", width=17)
            op_cb.grid(row=r, column=1, sticky="w", padx=6)
            cell = tk.Frame(rows)
            cell.grid(row=r, column=2, sticky="w")

            def field_changed(_e=None):
                code = next(c for c, l, _, _ in filters.FIELDS if l == field.get())
                if code != rule["field"]:
                    rule.clear()
                    rule.update(filters.blank_rule(code))
                    self._filter_save()
                    self._filter_fill_editor()

            def op_changed(_e=None):
                rule["op"] = next(c for c, l in ops if l == op.get())
                self._filter_save()
                if kind == "year":
                    self._filter_fill_editor()   # between needs a second box
            field_cb.bind("<<ComboboxSelected>>", field_changed)
            op_cb.bind("<<ComboboxSelected>>", op_changed)
            if kind == "stars":
                chosen = {x for x in str(rule.get("value", "")).split(",") if x}
                stars = {}

                def stars_changed():
                    rule["value"] = ",".join(str(n) for n in range(6) if stars[n].get())
                    self._filter_save()
                for n in range(6):
                    stars[n] = tk.BooleanVar(value=str(n) in chosen)
                    keep.append(stars[n])
                    ttk.Checkbutton(cell, text=str(n), variable=stars[n], command=stars_changed).pack(
                        side="left", padx=(0, 6))
            else:
                def entry(key, width):
                    var = tk.StringVar(value=rule.get(key, ""))
                    keep.append(var)
                    tk.Entry(cell, textvariable=var, width=width).pack(side="left")

                    def typed(*_):
                        rule[key] = var.get().strip()
                        self._filter_save()
                    var.trace_add("write", typed)
                if rule["field"] == "file_type":   # a dropdown of the types in your library
                    var = tk.StringVar(value=rule.get("value", ""))
                    keep.append(var)
                    types = filters.file_types()
                    if var.get() and var.get().lower() not in types:
                        types.append(var.get().lower())
                    type_cb = ttk.Combobox(cell, textvariable=var, values=types, state="readonly", width=10)
                    type_cb.pack(side="left")

                    def type_picked(_e=None, var=var, type_cb=type_cb):
                        rule["value"] = var.get()
                        type_cb.selection_clear()
                        self._filter_save()
                    type_cb.bind("<<ComboboxSelected>>", type_picked)
                else:
                    entry("value", 18 if kind == "text" else 8)
                if kind == "year" and rule.get("op") == "between":
                    tk.Label(cell, text="and").pack(side="left", padx=6)
                    entry("value2", 8)
                if kind in units:
                    tk.Label(cell, text=units[kind]).pack(side="left", padx=(6, 0))

            def remove():
                item["rules"].remove(rule)
                self._filter_save()
                self._filter_fill_editor()
            tk.Button(rows, text="\u2715", width=2, command=remove).grid(row=r, column=3, sticky="w", padx=(8, 0))
        for r, rule in enumerate(item.get("rules") or []):
            rule_row(r, rule)

        def add_rule():
            item.setdefault("rules", []).append(filters.blank_rule())
            self._filter_save()
            self._filter_fill_editor()
        tk.Button(box, text="Add rule", width=10, command=add_rule).grid(row=2, column=0, sticky="w", pady=(8, 0))
        right.keep = keep   # hold the variables while the page shows

    def _filter_new(self):
        name = simpledialog.askstring("New filter", "Name for the new filter:", parent=self)
        if not name or not name.strip():
            return
        self._filters.append(filters.blank(name.strip()))
        self._filter_i = len(self._filters) - 1
        self._filter_save()
        self._filter_fill_editor()

    def _filter_rename(self):
        if self._filter_i is None:
            return
        item = self._filters[self._filter_i]
        name = simpledialog.askstring("Rename filter", "New name:", initialvalue=item["name"], parent=self)
        if name and name.strip():
            item["name"] = name.strip()
            self._filter_save()
            self._filter_fill_editor()

    def _filter_duplicate(self):
        if self._filter_i is None:
            return
        copy = filters.tidy(dict(self._filters[self._filter_i]))
        copy.update(id=filters.blank()["id"], name=copy["name"] + " copy")
        copy["devices"] = list(copy["devices"])
        copy["rules"] = [dict(r) for r in copy["rules"]]
        self._filters.insert(self._filter_i + 1, copy)
        self._filter_i += 1
        self._filter_save()
        self._filter_fill_editor()

    def _filter_delete(self):
        if self._filter_i is None:
            return
        item = self._filters[self._filter_i]
        if not messagebox.askyesno("Delete filter", f"Delete the filter {item['name']}?", parent=self):
            return
        del self._filters[self._filter_i]
        self._filter_i = min(self._filter_i, len(self._filters) - 1) if self._filters else None
        self._filter_save()
        self._filter_fill_editor()

    # --- the JRiver Playlists page ---

    def _fill_saved(self, tab, p):
        """
        How your JRiver playlists play when asked for by voice: one shared row
        (All playlists, ticked) or a row each (the table), never both at once.
        """
        p.loading = True
        p.data = saved_playlists.tidy(p.env)
        tab.grid_columnconfigure(0, weight=1)
        WIDTHS = (16, 26, 9)   # Folder, Playlist, Type

        def changed(*_):
            if not p.loading:
                p.save()

        def row_controls(parent, r, bg, row, on_change, col=3):
            """Shuffle, Non-stop, Reseed from and Skip for one row; writes back into row as they change."""
            sh = tk.BooleanVar(value=row.get("shuffle") == "1")
            ns = tk.StringVar(value=option_label(SAVED_NONSTOP_OPTIONS, row.get("nonstop", "no")))
            rs = tk.StringVar(value=option_label(NONSTOP_RESEED_OPTIONS, row.get("reseed", "last")))
            sk = tk.StringVar(value=option_label(SAVED_SKIP_OPTIONS, str(row.get("skip", "0"))))
            p.keep += [sh, ns, rs, sk]
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col, sticky="nsew")
            ttk.Checkbutton(cell, variable=sh).pack(padx=20, pady=2)
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col + 1, sticky="nsew")
            ns_cb = ttk.Combobox(cell, textvariable=ns, values=[s for _, s in SAVED_NONSTOP_OPTIONS],
                                 state="readonly", width=15)
            ns_cb.pack(anchor="w", padx=6, pady=2)
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col + 2, sticky="nsew")
            rs_cb = ttk.Combobox(cell, textvariable=rs, values=[s for _, s in NONSTOP_RESEED_OPTIONS],
                                 state="readonly", width=10)
            rs_cb.pack(anchor="w", padx=6, pady=2)
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col + 3, sticky="nsew")
            sk_cb = ttk.Combobox(cell, textvariable=sk, values=[s for _, s in SAVED_SKIP_OPTIONS],
                                 state="readonly", width=9)
            sk_cb.pack(anchor="w", padx=6, pady=2)

            def store(*_):
                row["shuffle"] = "1" if sh.get() else "0"
                row["nonstop"] = option_code(SAVED_NONSTOP_OPTIONS, ns.get())
                row["reseed"] = option_code(NONSTOP_RESEED_OPTIONS, rs.get())
                row["skip"] = option_code(SAVED_SKIP_OPTIONS, sk.get())
                sync_reseed()
                on_change()

            def sync_reseed():
                live = "disabled" not in ns_cb.state()
                rs_cb.state(["!disabled"] if live and row.get("nonstop", "no") != "no" else ["disabled"])
            for var in (sh, ns, rs, sk):
                var.trace_add("write", store)
            p.reseed_syncs.append(sync_reseed)

        def header(parent, labels, clicks=None):
            """A heading row; clicks maps a column to what clicking its heading does."""
            for c, text in enumerate(labels):
                lab = tk.Label(parent, text=text, font=LABEL_FONT, anchor="w", bg=table_colours()[0],
                               width=WIDTHS[c] if c < 3 else 0)
                lab.grid(row=0, column=c, sticky="we", ipadx=8, ipady=4)
                if clicks and c in clicks:
                    lab.config(cursor="hand2")
                    lab.bind("<Button-1>", lambda e, f=clicks[c]: f())
            return parent

        def cell(parent, r, c, text, bg):
            tk.Label(parent, text=text, anchor="w", bg=bg, width=WIDTHS[c]).grid(
                row=r, column=c, sticky="we", ipadx=8, ipady=2)

        p.keep, p.reseed_syncs = [], []
        CONTROLS = ["Shuffle", "Non-stop", "Reseed from", "Skip recent"]   # short, so headings fit their dropdowns

        # --- All playlists ---
        box = section(tab, "All playlists",
                      "Ticked, the two rows below apply, one to every playlist and one to every "
                      "smartlist, and the table is greyed out. Unticked, each playlist follows its own "
                      "row in the table.\n"
                      "JRiver can randomise a smartlist itself, for example with a random album sort, "
                      "and shuffling it here would break those albums up, so you may want Shuffle off "
                      "on the smartlist row.")
        p.all_var = tk.BooleanVar(value=p.data["all"] == "1")

        def all_toggled():
            p.data["all"] = "1" if p.all_var.get() else "0"
            p.resync()
            changed()
        ttk.Checkbutton(box, text="Use global playlist settings", variable=p.all_var,
                        command=all_toggled).grid(row=0, column=0, sticky="w", pady=(0, 6))
        p.all_row = header(tk.Frame(box, bd=1, relief="solid"), ["Folder", "Playlist", "Type"] + CONTROLS)
        p.all_row.grid(row=1, column=0, sticky="w")
        bg = p.all_row.cget("bg")
        for r, (name, kind, key) in enumerate((("All playlists", "Playlist", "all_row"),
                                               ("All smartlists", "Smartlist", "all_row_smart")), start=1):
            for c, text in enumerate(("All folders", name, kind)):
                cell(p.all_row, r, c, text, bg)
            row_controls(p.all_row, r, bg, p.data[key], changed)

        # --- Playlists ---
        box = section(tab, "Playlists",
                      "Your JRiver playlists and smartlists. These settings apply when you ask for a playlist by "
                      "voice. Playlists you start in JRiver itself aren't changed. Click Folder or Playlist to "
                      "sort by it; click again for Z-A. Root (the top level) always comes first.\n"
                      "Skip recent leaves out tracks played in the last few days, but never empties a playlist.")
        bar = tk.Frame(box)
        bar.grid(row=0, column=0, sticky="we", pady=(0, 8))
        tk.Label(bar, text="Folder").pack(side="left")
        p.folder_var = tk.StringVar(value=ALL_FOLDERS)
        p.folder_cb = ttk.Combobox(bar, textvariable=p.folder_var, state="readonly", width=20)
        p.folder_cb.pack(side="left", padx=(8, 18))
        tk.Label(bar, text="Search").pack(side="left")
        p.search_var = tk.StringVar()
        tk.Entry(bar, textvariable=p.search_var, width=24).pack(side="left", padx=(8, 0))
        p.count_label = tk.Label(bar, text="", fg=PALETTE["help_fg"], font=HELP_FONT)
        p.count_label.pack(side="left", padx=(14, 0))
        p.rescan_btn = tk.Button(bar, text="Rescan", width=10, command=lambda: rescan(loud=True))
        p.rescan_btn.pack(side="right", padx=(24, 0))
        p.table_holder = tk.Frame(box)
        p.table_holder.grid(row=1, column=0, sticky="w")
        tk.Label(box, text="New playlists arrive with Shuffle off, Non-stop No and Skip Off.",
                 fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=2, column=0, sticky="w", pady=(6, 0))

        def text_key(text):
            text = (text or "").strip().lower()
            return text[4:] if text.startswith("the ") else text

        def ordered(rows):
            """Sorted by Folder or Playlist, A-Z or Z-A; with Folder, Root always comes first."""
            backwards = p.data.get("sort") == "za"
            if p.data.get("sort_by") == "name":
                return sorted(rows, key=lambda x: (text_key(x[1].get("name")), text_key(x[1].get("folder"))),
                              reverse=backwards)
            root = [x for x in rows if (x[1].get("folder") or saved_playlists.ROOT) == saved_playlists.ROOT]
            rest = [x for x in rows if x not in root]
            by_name = lambda x: text_key(x[1].get("name"))
            return (sorted(root, key=by_name, reverse=backwards)
                    + sorted(rest, key=lambda x: (text_key(x[1].get("folder")), by_name(x)), reverse=backwards))

        def sort_by(column):
            if p.data.get("sort_by") == column:
                p.data["sort"] = "za" if p.data.get("sort") == "az" else "az"
            else:
                p.data["sort_by"], p.data["sort"] = column, "az"
            build_table()
            changed()

        def fill_folders():
            folders = {row.get("folder") or saved_playlists.ROOT for row in p.data["rows"].values()}
            others = sorted((f for f in folders if f != saved_playlists.ROOT), key=text_key)
            p.folder_cb.config(values=[ALL_FOLDERS] + ([saved_playlists.ROOT] if saved_playlists.ROOT in folders
                                                       else []) + others)
            if p.folder_var.get() not in p.folder_cb.cget("values"):
                p.folder_var.set(ALL_FOLDERS)

        def build_table(*_):
            for child in p.table_holder.winfo_children():
                child.destroy()
            p.table = None
            p.reseed_syncs[:] = p.reseed_syncs[:2]   # keep the two global rows'
            rows = ordered(list(p.data["rows"].items()))
            folder = p.folder_var.get()
            wanted = p.search_var.get().strip().lower()
            shown = [(pid, row) for pid, row in rows
                     if (folder == ALL_FOLDERS or (row.get("folder") or saved_playlists.ROOT) == folder)
                     and (wanted in (row.get("name") or "").lower() or wanted in (row.get("folder") or "").lower())]
            total = len(rows)
            p.count_label.config(text=f"{total} playlist{'' if total == 1 else 's'}"
                                 + (f", {len(shown)} shown" if len(shown) != total else ""))
            if not rows:
                tk.Label(p.table_holder, text="No playlists yet. Make sure JRiver is running, then click Rescan.",
                         fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=0, column=0, sticky="w")
                return
            arrow = " \u25b2" if p.data.get("sort") == "az" else " \u25bc"
            by = p.data.get("sort_by")
            labels = ["Folder" + (arrow if by != "name" else ""), "Playlist" + (arrow if by == "name" else ""),
                      "Type"] + CONTROLS
            p.table = header(tk.Frame(p.table_holder, bd=1, relief="solid"), labels,
                             {0: lambda: sort_by("folder"), 1: lambda: sort_by("name")})
            p.table.grid(row=0, column=0, sticky="w")
            for r, (pid, row) in enumerate(shown, start=1):
                bg = table_colours()[1 if r % 2 else 2]
                cell(p.table, r, 0, row.get("folder") or saved_playlists.ROOT, bg)
                cell(p.table, r, 1, row.get("name") or pid, bg)
                cell(p.table, r, 2, row.get("type") or "", bg)
                row_controls(p.table, r, bg, row, changed)
            p.resync()

        def rescan(loud=False):
            try:
                found = saved_playlists.scan()
            except Exception as e:
                if loud:
                    messagebox.showerror("Rescan", f"Couldn't read your playlists from JRiver.\n\n{e}", parent=self)
                return
            # refresh the playlist list only: the global rows' controls write into p.data's own
            # all_row and all_row_smart, so p.data must stay the same object
            p.data["rows"] = saved_playlists.merge_scan(p.data, found)["rows"]
            fill_folders()
            build_table()
            changed()

        p.search_var.trace_add("write", build_table)
        p.folder_cb.bind("<<ComboboxSelected>>", lambda e: (p.folder_cb.selection_clear(), build_table()))

        def resync():
            together = p.all_var.get()
            set_enabled(p.all_row, together)
            if getattr(p, "table", None) is not None and p.table.winfo_exists():
                set_enabled(p.table, not together)
            for sync in p.reseed_syncs:
                sync()
        p.resync = resync
        p.collect = lambda: saved_playlists.tidy(p.data)
        fill_folders()
        build_table()
        p.loading = False
        self.after(200, rescan)   # each time the tab opens: names, folders and new playlists, fresh from JRiver

    def _save_saved_main(self, *_):
        p = getattr(self, "_main_saved", None)
        if p is None or p.loading or self._loading:
            return
        try:
            saved_playlists.set_main_settings(p.values())
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)

    # --- the Sources sections ---

    def _listenbrainz_row(self, p, box, r, key, notes):
        """The ListenBrainz algorithm dropdown for one section, with its notes behind a ?."""
        row = self._line(box, r, "ListenBrainz algorithm", pady=(10, 0))
        p.vars[key] = tk.StringVar(value=p.env.get(key, "alltime"))
        cb = ttk.Combobox(row, textvariable=p.vars[key], values=["alltime", "recent"],
                          state="readonly", width=10)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", p.save)
        help_mark(row, notes).pack(side="left", padx=(8, 0))
        return r + 1

    def _option_tabs(self, tab, kind, options=PLAY_OPTIONS):
        """The row of Play option tabs inside a Sources or Playlist page. Returns {group: page}."""
        pane = TabbedPane(tab, font=("Segoe UI", 9, "bold"), pad=(12, 4), box=True, indent=6)
        pane.grid(row=tab.grid_size()[1], column=0, sticky="nsew")
        tab.grid_columnconfigure(0, weight=1)
        pages = {}
        for group, title in options:
            page = tk.Frame(pane, padx=10, pady=12)
            pane.add(page, text=title)
            pages[group] = page
        chosen = self._option_tab_choice.get(kind)
        if chosen in pages:   # reopen on the option last looked at
            pane.select(pages[chosen])

        def remember(_e=None):
            for group, page in pages.items():
                if pane.select() == str(page):
                    self._option_tab_choice[kind] = group
        pane.bind("<<NotebookTabChanged>>", remember, add="+")
        return pages

    def _source_ticks(self, p, box, r, group, names, default, command, purpose, help_text=None,
                      lb_key=None, lb_notes=None):
        """
        The sources for one Play option, one per line, with an optional ? beside
        the first. lb_key: the ListenBrainz algorithm dropdown, on its line.
        """
        frame = tk.Frame(box)
        frame.grid(row=r, column=0, columnspan=6, sticky="w", pady=(2, 4))
        chosen = [x.strip().lower() for x in p.env.get(group, default).split(",") if x.strip()]
        p.vars[group] = {}
        for n, (code, label) in enumerate(names):
            line = tk.Frame(frame)
            line.pack(anchor="w", pady=1)
            v = tk.BooleanVar(value=code in chosen)
            p.vars[group][code] = v

            def ticked(command=command):
                self._sync_listenbrainz(p)
                command()
            tick = ttk.Checkbutton(line, text=label, variable=v, command=ticked,
                                   style="AI.Big.TCheckbutton" if code == "ai" else "Big.TCheckbutton")
            if code == "ai":   # purple: uses Anthropic credit
                ttk.Style(line).configure("AI.Big.TCheckbutton", font=("Segoe UI", 11),
                                          foreground=PALETTE["ai_purple"])
            tick.pack(side="left")
            self._source_boxes.append((tick, code, label, purpose))
            if help_text and n == 0:
                help_mark(line, help_text).pack(side="left", padx=(10, 0))
            if code == "listenbrainz" and lb_key:
                p.vars[lb_key] = tk.StringVar(value=p.env.get(lb_key, "alltime"))
                cb = ttk.Combobox(line, textvariable=p.vars[lb_key], values=["alltime", "recent"],
                                  state="readonly", width=9)
                cb.pack(side="left", padx=(14, 0))
                cb.bind("<<ComboboxSelected>>", p.save)
                help_mark(line, lb_notes).pack(side="left", padx=(8, 0))
                p.lb_cbs.append((v, cb))
        return r + 1

    def _sync_listenbrainz(self, p):
        """Each ListenBrainz algorithm dropdown greys out while ListenBrainz is unticked."""
        for tick, cb in getattr(p, "lb_cbs", []):
            cb.state(["!disabled"] if tick.get() else ["disabled"])

    def _moderator_section(self, p, page, group):
        """An AI Moderator tick for one Play option, greyed out until there's an Anthropic key."""
        box = section(page, "AI Moderator",
                      "Checks each playlist (and each Drift round) once with Claude Haiku, and removes tracks "
                      "that clash with the seed's tone, energy and mood. Logs each removal with its reason. "
                      "Uses a little Anthropic credit each time, a fraction of a penny per playlist.",
                      title_fg=PALETTE["ai_purple"])
        key = f"AI_MODERATOR_{group.upper()}"
        p.vars[key] = tk.StringVar(value=engine.moderator_settings(p.env.get)[group].title())

        def chosen(*_):
            if p.vars[key].get() != "Off":
                warn_moderator_once(self)
            cb.selection_clear()
            p.save()
        row = self._line(box, 0, "Level", pady=(0, 0))
        cb = ttk.Combobox(row, textvariable=p.vars[key], values=MODERATOR_CHOICES, state="readonly", width=9)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", chosen)
        help_mark(row, MODERATOR_LEVELS_HELP).pack(side="left", padx=(8, 0))
        Tooltip(cb, NO_KEY_TEXT, when=lambda: not self._anthropic_key())
        p.moderator_boxes.append(cb)

    def _fill_sources(self, tab, p):
        p.loading = True
        p.moderator_boxes = []
        pages = self._option_tabs(tab, "sources", PLAY_OPTIONS[:3])   # vibe playlists always come from the AI
        p.lb_cbs = []

        def similar_changed():
            sync_agreement(p, "SIMILAR_SOURCES", "SIMILAR_MIN_AGREEMENT", "agree_cb", 5)
            p.save()

        def tracks_changed():
            sync_agreement(p, "SIMILAR_TRACK_SOURCES", "SIMILAR_TRACK_MIN_AGREEMENT", "track_agree_cb", 99)
            p.save()

        # --- Similar Artists ---
        box = section(pages["artists"], "Sources",
                               "YouTube suggests from the playing track, using YouTube Music's up next queue. "
                               "No key needed. Ticked on its own, it plays YouTube's queue as is, matched against "
                               "your library. Ticked with other sources, its artists join the blend. It's an "
                               "unofficial route, so it may break now and then.")
        r = self._source_ticks(p, box, 0, "SIMILAR_SOURCES", SOURCE_NAMES, "lastfm", similar_changed, "similar",
                               lb_key="LISTENBRAINZ_ALGORITHM",
                               lb_notes="alltime: from all listening history; leans toward well-known artists.\n"
                                        "recent: what people are playing alongside this artist right now.")
        # How many sources must agree. Replaced the old on/off tick box; an old
        # on/off setting carries over (on -> 2, off -> Off).
        legacy_on = p.env.get("SIMILAR_REQUIRE_AGREEMENT", "1") in ("1", "true", "yes")
        start = p.env.get("SIMILAR_MIN_AGREEMENT", "").strip() or ("2" if legacy_on else "1")
        p.vars["SIMILAR_MIN_AGREEMENT"] = tk.StringVar(value="Off" if start in ("0", "1") else start)
        row = self._line(box, r, "Sources that must agree", pady=(10, 0))
        p.agree_cb = ttk.Combobox(row, textvariable=p.vars["SIMILAR_MIN_AGREEMENT"], state="readonly", width=6)
        p.agree_cb.pack(side="left")
        p.agree_cb.bind("<<ComboboxSelected>>", p.save)
        help_mark(row, "How many sources must agree before an artist is picked. Higher means a smoother "
                       "playlist with fewer wildcards, but less chance of discovering something new. "
                       "Tip: try single sources on their own before blending.").pack(side="left", padx=(8, 0))
        if p.device_id is not None:   # Windows (Main) chooses on the Play tab
            self._moderator_section(p, pages["artists"], "artists")

        # --- Similar Tracks: its own sources and agreement ---
        box = section(pages["tracks"], "Sources",
                      "Tracks like the seed track, for the Similar Tracks button. No key needed for "
                      "ListenBrainz or YouTube.")
        r = self._source_ticks(p, box, 0, "SIMILAR_TRACK_SOURCES", TRACK_SOURCE_NAMES, "lastfm,listenbrainz,youtube",
                               tracks_changed, "similar", lb_key="LISTENBRAINZ_TRACK_ALGORITHM",
                               lb_notes="alltime: from all listening history.\n"
                                        "recent: roughly the last six months; older songs may find fewer matches.")
        start = p.env.get("SIMILAR_TRACK_MIN_AGREEMENT", "2").strip() or "2"
        p.vars["SIMILAR_TRACK_MIN_AGREEMENT"] = tk.StringVar(value="Off" if start in ("0", "1") else start)
        row = self._line(box, r, "Sources that must agree", pady=(10, 0))
        p.track_agree_cb = ttk.Combobox(row, textvariable=p.vars["SIMILAR_TRACK_MIN_AGREEMENT"],
                                        state="readonly", width=6)
        p.track_agree_cb.pack(side="left")
        p.track_agree_cb.bind("<<ComboboxSelected>>", p.save)
        help_mark(row, "How many sources must agree on a track before it's used. If too few agreed tracks "
                       "are in your library, the agreement is relaxed a step at a time, and the log says so."
                  ).pack(side="left", padx=(8, 0))
        if p.device_id is not None:   # Windows (Main) chooses on the Play tab
            self._moderator_section(p, pages["tracks"], "tracks")

        # --- Artist's Top Tracks ---
        box = section(pages["top"], "Sources",
                      "More services means richer, more varied playlists, but slower; fewer is quicker. "
                           "ListenBrainz is the slowest source on a first run, because its lookups are limited "
                      "to one a second. Repeat runs are quick.")
        self._source_ticks(p, box, 0, "TOP_TRACK_SOURCES", TOP_SOURCE_NAMES, "lastfm", p.save, "top")

        p.resync = lambda: (sync_agreement(p, "SIMILAR_SOURCES", "SIMILAR_MIN_AGREEMENT", "agree_cb", 5),
                            sync_agreement(p, "SIMILAR_TRACK_SOURCES", "SIMILAR_TRACK_MIN_AGREEMENT",
                                           "track_agree_cb", 99),
                            self._sync_moderator_box(p), self._sync_listenbrainz(p))
        p.resync()
        p.loading = False

    def _on_console_query_toggled(self):
        """Ticking Console Query asks first; with no Anthropic key it explains and stays off."""
        var = self.vars["CONSOLE_QUERY"]
        if var.get():
            if not self._anthropic_key():
                messagebox.showinfo("Console Query", NO_KEY_TEXT, parent=self)
                var.set(False)
            elif not messagebox.askyesno("Console Query", CONSOLE_QUERY_WARNING, parent=self):
                var.set(False)
        self._save()

    def _anthropic_key(self):
        var = self.vars.get("ANTHROPIC_API_KEY")
        return (var.get().strip() if var is not None else "") or engine.ANTHROPIC_API_KEY

    def _sync_moderator_box(self, p):
        """Every AI Moderator tick is greyed out until there's an Anthropic key."""
        for tick in getattr(p, "moderator_boxes", []):
            tick.state(["!disabled"] if self._anthropic_key() else ["disabled"])

    # --- the Playlist sections ---

    def _fill_playlist(self, tab, p):
        """
        Playlist settings in one tab per Play option: the playlist itself, then
        Drift, Non-stop and Hidden Tracks, each in its own boxed section.
        """
        p.loading = True
        p.drift = {}           # group -> (on, using, rounds, (dropdowns))
        p.drift_src = {}       # group -> (mode, its row, the Custom Sources panel, {kind: frame})
        p.played_boxes = {}    # group -> its days box
        p.closer_sbs = {}      # GROUP -> its minutes box
        p.nonstop_parts = {}   # GROUP -> (its choices, the song-count dropdown or None)
        pages = self._option_tabs(tab, "playlist")
        nonstop_cfg = engine.nonstop_settings(p.env.get)
        closer_cfg = engine.closer_settings(p.env.get)
        where = {}     # the box being filled and its next row

        def begin(group, title, help_text=None):
            where["box"], where["r"] = section(pages[group], title, help_text), 0

        def place(widget, pady=4):
            """Puts a label-less row (a tick box and friends) across the box."""
            widget.grid(row=where["r"], column=0, columnspan=3, sticky="w", pady=pady)
            where["r"] += 1

        def spin(label, key, default, lo, hi, help_text=None):
            box, r = where["box"], where["r"]
            tk.Label(box, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=p.env.get(key, default))
            p.vars[key] = var
            cell = tk.Frame(box)   # the control with its ? right beside it
            cell.grid(row=r, column=1, sticky="w", padx=(12, 0))
            sb = tk.Spinbox(cell, from_=lo, to=hi, textvariable=var, width=6, command=p.save)
            sb.pack(side="left")
            if help_text:
                help_mark(cell, help_text).pack(side="left", padx=(8, 0))
            var.trace_add("write", p.save)
            where["r"] += 1
            return var, sb

        def choice(label, key, default, values, help_text=None):
            box, r = where["box"], where["r"]
            tk.Label(box, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
            p.vars[key] = tk.StringVar(value=p.env.get(key, default))
            cell = tk.Frame(box)
            cell.grid(row=r, column=1, sticky="w", padx=(12, 0))
            cb = ttk.Combobox(cell, textvariable=p.vars[key], values=values, state="readonly", width=12)
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", p.save)
            if help_text:
                help_mark(cell, help_text).pack(side="left", padx=(8, 0))
            where["r"] += 1

        def recent(group):
            """Skip tracks played in the last [n] days (1 by default), with its ?."""
            name = f"SKIP_PLAYED_{group.upper()}"
            main_on, main_days = engine.SKIP_PLAYED[group]
            p.vars[name] = tk.BooleanVar(value=p.env.get(name, "1" if main_on else "0") in ("1", "true", "yes"))
            p.vars[f"{name}_DAYS"] = tk.StringVar(value=p.env.get(f"{name}_DAYS", str(main_days)))
            row = tk.Frame(where["box"])

            def toggled():
                sync_played(p)
                p.save()
            ttk.Checkbutton(row, text="Skip tracks played in the last", variable=p.vars[name],
                            command=toggled).pack(side="left")
            days = tk.Spinbox(row, from_=1, to=365, textvariable=p.vars[f"{name}_DAYS"], width=4, command=p.save)
            days.pack(side="left", padx=(6, 6))
            tk.Label(row, text="days").pack(side="left")
            help_mark(row, "Leaves out anything JRiver has played within that many days, using its Last "
                           "Played date. The seed track is never left out. JRiver's library is re-read every "
                           "half hour, so a track played in the last few minutes may still get in. Drift, if "
                           "it's on, fills any gaps this leaves.").pack(side="left", padx=(8, 0))
            p.vars[f"{name}_DAYS"].trace_add("write", p.save)
            p.played_boxes[group] = days
            place(row, pady=(8, 4))

        def drift(group):
            """The Drift section: its tick box, then Drift using and Rounds."""
            note = ("If a playlist comes up short, search again using what's already been found, "
                    "until the playlist reaches its length. More rounds fill more gaps but can "
                    "wander further from where you started.")
            if group == "vibe":
                note = ("Tops the playlist up from your music sources (Last.fm and the others you've ticked), "
                        "not the AI, unless Drift using is set to AI. AI asks again with your description, "
                        "leaving out what's already been found or tried, and uses a little Anthropic credit "
                        "each round.")
            begin(group, "Drift", note)
            box = where["box"]
            cfg = drift_values(p.env, group)
            on = tk.BooleanVar(value=cfg["on"])
            using = tk.StringVar(value=option_label(drift_using_options(group), cfg["using"]))
            rounds = tk.StringVar(value=str(cfg["rounds"]))

            def toggled():
                sync_drift(p)
                p.save()
            place(ttk.Checkbutton(box, text="Search again when a playlist comes up short", variable=on,
                                  command=toggled), pady=(0, 2))
            row = tk.Frame(box)
            tk.Label(row, text="Drift using").pack(side="left")
            choices = drift_using_options(group)
            using_cb = ttk.Combobox(row, textvariable=using, values=[shown for _, shown in choices],
                                    state="readonly", width=22 if group == "vibe" else 14)
            using_cb.pack(side="left", padx=(6, 18))
            tk.Label(row, text="Rounds").pack(side="left")
            rounds_cb = ttk.Combobox(row, textvariable=rounds, values=[str(n) for n in range(1, 7)],
                                     state="readonly", width=3)
            rounds_cb.pack(side="left", padx=(6, 0))
            for cb in (using_cb, rounds_cb):
                cb.bind("<<ComboboxSelected>>", p.save)
            place(row, pady=(0, 4))
            # Drift sources: the same as Settings > Sources, or Custom Sources of its own
            name = f"DRIFT_{group.upper()}"
            mode = tk.StringVar(value=option_label(
                DRIFT_SOURCE_MODES, p.env.get(f"{name}_SOURCES_MODE", "same").strip().lower()))
            p.vars[f"{name}_SOURCES_MODE"] = mode
            mode_row = tk.Frame(box)
            tk.Label(mode_row, text="Drift sources").pack(side="left")
            mode_cb = ttk.Combobox(mode_row, textvariable=mode, values=[s for _, s in DRIFT_SOURCE_MODES],
                                   state="readonly", width=26)
            mode_cb.pack(side="left", padx=(6, 0))
            help_mark(mode_row, DRIFT_SOURCES_HELP).pack(side="left", padx=(8, 0))
            place(mode_row, pady=(0, 4))
            panel = tk.Frame(box)
            frames = {}
            for kind, names, agree_values, main in (
                    ("ARTIST", DRIFT_ARTIST_SOURCE_NAMES, ["Off", "2", "3", "4"],
                     [c for c in engine.SIMILAR_SOURCES if c != "ai"]),
                    ("TRACK", [s for s in TRACK_SOURCE_NAMES if s[0] != "ai"], ["Off", "2", "3"],
                     [c for c in engine.SIMILAR_TRACK_SOURCES if c != "ai"])):
                frame = tk.Frame(panel)
                tk.Label(frame, text="Similar artists from" if kind == "ARTIST" else "Similar tracks from",
                         fg=PALETTE["text_secondary"]).pack(anchor="w")
                ticks = tk.Frame(frame)
                ticks.pack(anchor="w", pady=(2, 2))
                saved = p.env.get(f"{name}_{kind}_SOURCES", "")
                chosen = ([x.strip().lower() for x in saved.split(",") if x.strip()] if saved.strip()
                          else list(main))   # nothing saved yet: start from Settings > Sources
                p.vars[f"{name}_{kind}_SOURCES"] = {}
                for code, label in names:
                    var = tk.BooleanVar(value=code in chosen)
                    p.vars[f"{name}_{kind}_SOURCES"][code] = var
                    ttk.Checkbutton(ticks, text=label, variable=var, command=p.save).pack(side="left", padx=(0, 12))
                agree_row = tk.Frame(frame)
                agree_row.pack(anchor="w", pady=(2, 0))
                tk.Label(agree_row, text="Sources that must agree").pack(side="left")
                start = p.env.get(f"{name}_{kind}_AGREE", "1").strip() or "1"
                agree = tk.StringVar(value="Off" if start in ("0", "1") else start)
                p.vars[f"{name}_{kind}_AGREE"] = agree
                agree_cb = ttk.Combobox(agree_row, textvariable=agree, values=agree_values, state="readonly",
                                        width=6)
                agree_cb.pack(side="left", padx=(6, 0))
                agree_cb.bind("<<ComboboxSelected>>", p.save)
                help_mark(agree_row, "How many of the ticked sources must agree before Drift uses a suggestion. "
                                     "It can't be more than the sources that answer.").pack(side="left", padx=(8, 0))
                frames[kind] = frame
            place(panel, pady=(0, 4))
            panel.grid_configure(padx=(16, 0))
            p.drift[group] = (on, using, rounds, (using_cb, rounds_cb, mode_cb))
            p.drift_src[group] = (mode, mode_row, panel, frames)

            def sources_changed(*_):
                mode_cb.selection_clear()
                sync_drift(p)
                p.save()
            mode_cb.bind("<<ComboboxSelected>>", sources_changed)
            using_cb.bind("<<ComboboxSelected>>", lambda e: sync_drift(p), add="+")
            if group == "vibe":   # AI Playlist: an AI Moderator for what Drift adds from the sources
                mod_row = tk.Frame(box)
                tk.Label(mod_row, text="AI Moderator on Drift tracks", fg=PALETTE["ai_purple"]).pack(side="left")
                p.vars["AI_MODERATOR_VIBE"] = tk.StringVar(
                    value=engine.moderator_settings(p.env.get)["vibe"].title())
                mod_cb = ttk.Combobox(mod_row, textvariable=p.vars["AI_MODERATOR_VIBE"], values=MODERATOR_CHOICES,
                                      state="readonly", width=9)
                mod_cb.pack(side="left", padx=(6, 0))

                def mod_chosen(*_):
                    if p.vars["AI_MODERATOR_VIBE"].get() != "Off":
                        warn_moderator_once(self)
                    mod_cb.selection_clear()
                    p.save()
                mod_cb.bind("<<ComboboxSelected>>", mod_chosen)
                using_cb.bind("<<ComboboxSelected>>", lambda e: sync_drift(p), add="+")
                help_mark(mod_row, "Checks the tracks Drift adds from similar artists or similar tracks against "
                                   "your description, and removes any that clash. The AI's own picks are never "
                                   "checked. Only works when Drift is on and not using the AI.\n"
                                   + MODERATOR_LEVELS_HELP).pack(side="left", padx=(8, 0))
                Tooltip(mod_cb, NO_KEY_TEXT, when=lambda: not self._anthropic_key())
                place(mod_row, pady=(0, 4))
                p.vibe_mod_cb = mod_cb

        def nonstop(group):
            """The Non-stop section: its tick box, then how this option's playlists carry on."""
            g, cfg = group.upper(), nonstop_cfg[group]
            begin(group, "Non-stop",
                  "When the last track of a playlist 24bit7 built starts playing, more are added to the end, "
                  "so the music doesn't stop. A playlist keeps following these settings all evening, even "
                  "after it carries on as Similar Tracks or Similar Artists. Only playlists 24bit7 sent are "
                  "topped up: an album or playlist you start in JRiver yourself ends as normal.")
            box = where["box"]
            p.vars[f"NONSTOP_{g}"] = tk.BooleanVar(value=cfg["on"])

            def toggled():
                sync_nonstop(p)
                p.save()
            place(ttk.Checkbutton(box, text="Keep going when the playlist reaches its last track",
                                  variable=p.vars[f"NONSTOP_{g}"], command=toggled), pady=(0, 2))
            body = tk.Frame(box)
            place(body, pady=(0, 4))
            rows = {"r": 0}

            def option(label, key, options, current, help_text):
                r = rows["r"]
                tk.Label(body, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
                p.vars[key] = tk.StringVar(value=option_label(options, current))
                cell = tk.Frame(body)
                cell.grid(row=r, column=1, sticky="w", padx=(12, 0))
                cb = ttk.Combobox(cell, textvariable=p.vars[key], values=[shown for _, shown in options],
                                  state="readonly", width=22)
                cb.pack(side="left")
                cb.bind("<<ComboboxSelected>>", p.save)
                help_mark(cell, help_text).pack(side="left", padx=(8, 0))
                rows["r"] += 1

            rest_cb = None
            if group == "top":
                row = tk.Frame(body)
                row.grid(row=rows["r"], column=0, columnspan=2, sticky="w", pady=(2, 4))
                rows["r"] += 1
                p.vars["NONSTOP_TOP_REST"] = tk.BooleanVar(
                    value=p.env.get("NONSTOP_TOP_REST", "1") in ("1", "true", "yes"))
                count = p.env.get("NONSTOP_TOP_REST_COUNT", "20").strip()
                p.vars["NONSTOP_TOP_REST_COUNT"] = tk.StringVar(
                    value="Unlimited" if count.lower() == "unlimited" else count)

                def rest_toggled():
                    sync_nonstop(p)
                    p.save()
                ttk.Checkbutton(row, text="First, the rest of the artist, up to",
                                variable=p.vars["NONSTOP_TOP_REST"], command=rest_toggled).pack(side="left")
                rest_cb = ttk.Combobox(row, textvariable=p.vars["NONSTOP_TOP_REST_COUNT"],
                                       values=["10", "20", "30", "50", "100", "Unlimited"],
                                       state="readonly", width=10)
                rest_cb.pack(side="left", padx=(6, 6))
                rest_cb.bind("<<ComboboxSelected>>", p.save)
                tk.Label(row, text="songs").pack(side="left")
                help_mark(row, "When the top tracks finish, the artist's other songs in your library play "
                               "next, shuffled. After that, their most popular track seeds a new playlist. "
                               "Unticked, it goes straight to the new playlist.").pack(side="left", padx=(8, 0))
            if group == "vibe":
                option("Continues with", "NONSTOP_VIBE_WITH", NONSTOP_WITH_OPTIONS, cfg["with"],
                       "More from the AI asks the AI again with the original description (a little "
                       "Anthropic credit each time). Similar artists or Similar tracks carry on from the "
                       "music, with no credit used.")
            else:
                option("Then play using" if group == "top" else "Play using", f"NONSTOP_{g}_USING",
                       NONSTOP_USING_OPTIONS, cfg["using"], "What each top-up is built with.")
            option("Reseed from", f"NONSTOP_{g}_RESEED", NONSTOP_RESEED_OPTIONS, cfg["reseed"],
                   "Last track: each top-up follows on from where the music has got to, so it wanders as "
                   "the evening goes on.\nSecond track: each top-up seeds from the first pick after the "
                   "original seed, so the music stays close to how it started.")
            p.nonstop_parts[g] = (body, rest_cb)

        def hidden(group):
            """The Hidden Tracks section for one Play option."""
            g = group.upper()
            on, minutes = closer_cfg[group]
            begin(group, "Hidden Tracks")
            row = tk.Frame(where["box"])
            p.vars[f"SKIP_LONG_CLOSERS_{g}"] = tk.BooleanVar(value=on)
            p.vars[f"LONG_CLOSER_MINUTES_{g}"] = tk.StringVar(value=str(minutes))
            sb = tk.Spinbox(row, from_=3, to=30, textvariable=p.vars[f"LONG_CLOSER_MINUTES_{g}"],
                            width=4, command=p.save)

            def toggled():
                sync_long_closers(p)
                p.save()
            ttk.Checkbutton(row, text="Skip the last track on an album if it's longer than",
                            variable=p.vars[f"SKIP_LONG_CLOSERS_{g}"], command=toggled).pack(side="left")
            sb.pack(side="left", padx=(6, 6))
            tk.Label(row, text="minutes").pack(side="left")
            help_mark(row, "Long album closers often hide a bonus track after a long silence. Albums, songs "
                           "and playlists you ask for by name always play in full.").pack(side="left", padx=(8, 0))
            p.vars[f"LONG_CLOSER_MINUTES_{g}"].trace_add("write", p.save)
            p.closer_sbs[g] = sb
            place(row)

        def run_after(group):
            """The Run After Building section: a file to run once the playlist is in JRiver."""
            key = f"RUN_AFTER_{group.upper()}"
            begin(group, "Run After Building")
            p.vars[key] = tk.BooleanVar(value=p.env.get(key, "0") in ("1", "true", "yes"))
            p.vars[f"{key}_PATH"] = tk.StringVar(value=p.env.get(f"{key}_PATH", ""))
            row = tk.Frame(where["box"])
            ttk.Checkbutton(row, text="Run this file after building", variable=p.vars[key],
                            command=p.save).pack(side="left")
            entry = tk.Entry(row, textvariable=p.vars[f"{key}_PATH"], width=48)
            entry.pack(side="left", padx=(8, 4))
            entry.bind("<FocusOut>", p.save)

            def browse():
                path = filedialog.askopenfilename(
                    parent=self, title="Run after building",
                    filetypes=[("Programs and scripts", "*.bat *.cmd *.exe *.ps1 *.py *.pyw"), ("All files", "*.*")])
                if path:
                    p.vars[f"{key}_PATH"].set(os.path.normpath(path))
                    p.vars[key].set(True)
                    p.save()
            ttk.Button(row, text="Browse...", command=browse).pack(side="left")
            help_mark(row, "Runs the file once the playlist is in JRiver, added playlists included, and only "
                           "if the build worked. It runs in the background and isn't told anything about the "
                           "playlist. A .bat, .exe, PowerShell or Python script all work. Non-stop top-ups "
                           "don't run it.").pack(side="left", padx=(8, 0))
            place(row)

        # --- Similar Artists ---
        begin("artists", "Playlist")
        spin("Number of tracks", "SIMILAR_ARTIST_TRACK_COUNT", "30", 5, 100, TARGET_HELP)
        spin("Number of artists", "SIMILAR_ARTIST_LIMIT", "20", 1, 50)
        pool_var, _ = spin("Number of artist's top tracks", "TRACKS_PER_ARTIST_POOL", "5", 1, 20)
        _, p.pick_sb = spin("Tracks per artist selection", "TRACKS_PER_ARTIST_PICK", "3", 1, 20,
                            "Top tracks come from your Top-track sources (Last.fm, Deezer and so on), for "
                            "the seed artist and each similar artist. Selecting fewer than the top tracks "
                            "(say 3 of 5) means the same seed gives a different playlist each run, as the "
                            "selection is random.")
        pool_var.trace_add("write", lambda *a: sync_pick_limit(p))
        recent("artists")
        drift("artists")
        nonstop("artists")
        hidden("artists")
        run_after("artists")

        # --- Similar Tracks ---
        begin("tracks", "Playlist")
        spin("Number of tracks", "SIMILAR_TRACK_COUNT", "30", 5, 100, TARGET_HELP)
        spin("Most tracks per artist", "SIMILAR_TRACK_PER_ARTIST", "3", 1, 20, "Includes the seed artist.")
        choice("Order", "SIMILAR_TRACK_ORDER", "shuffled", ["shuffled", "similar first"],
               "Similar first keeps the order the sources agreed on, strongest matches first. "
               "Shuffled mixes them up.")
        recent("tracks")
        drift("tracks")
        nonstop("tracks")
        hidden("tracks")
        run_after("tracks")

        # --- Artist's Top Tracks ---
        begin("top", "Playlist")
        spin("Number of tracks (1-20)", "TOP_TRACKS_COUNT", "10", 1, 20, TOP_TARGET_HELP)
        choice("Order", "TOP_TRACKS_ORDER", "popular", ["popular", "reverse", "random"],
               "popular: most played first\nreverse: least played first\nrandom: shuffled")
        recent("top")
        nonstop("top")
        hidden("top")
        run_after("top")

        # --- Vibe Playlist ---
        begin("vibe", "Playlist")
        spin("Number of tracks", "VIBE_TRACK_COUNT", "20", 5, 100, TARGET_HELP)
        recent("vibe")
        drift("vibe")
        nonstop("vibe")
        hidden("vibe")
        run_after("vibe")

        p.resync = lambda: (sync_pick_limit(p), sync_drift(p), sync_long_closers(p), sync_played(p),
                            sync_nonstop(p))
        p.resync()
        p.loading = False

    def _build_keys(self, nb):
        tab = self._scroll_tab(nb, "Keys")
        box = section(tab, "Keys and passwords")
        for r, key in enumerate(KEY_FIELDS):
            tk.Label(box, text=key, anchor="w",
                     **({"fg": PALETTE["ai_purple"]} if key == "ANTHROPIC_API_KEY" else {})
                     ).grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=self.env.get(key, ""))
            self.vars[key] = var
            entry = tk.Entry(box, textvariable=var, show="\u2022", width=32)
            entry.grid(row=r, column=1, padx=(8, 4))
            entry.bind("<FocusOut>", self._save)   # save when leaving the field
            self._add_show_toggle(box, entry, r)
            if key in KEY_HELP:
                button = tk.Button(box, text="?", width=2, command=lambda k=key: self._show_help(k))
                button.grid(row=r, column=3, padx=(4, 0))
                Tooltip(button, KEY_HELP[key][1].replace("\n", " ") + "\nClick for these steps in a window.")

    def _add_show_toggle(self, parent, entry, row):
        show = tk.BooleanVar(value=False)
        def toggle():
            entry.config(show="" if show.get() else "\u2022")
        ttk.Checkbutton(parent, text="Show", variable=show, command=toggle).grid(
            row=row, column=2, sticky="w")

    def _build_other(self, nb):
        tab = self._scroll_tab(nb, "Other")

        # --- General ---
        box = section(tab, "General")
        tk.Label(box, text="Cache days (reuse answers for)", anchor="w").grid(
            row=0, column=0, sticky="w", pady=4)
        self.vars["CACHE_DAYS"] = tk.StringVar(value=self.env.get("CACHE_DAYS", "30"))
        sb = tk.Spinbox(box, from_=1, to=365, textvariable=self.vars["CACHE_DAYS"], width=6,
                        command=self._save)
        sb.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.vars["CACHE_DAYS"].trace_add("write", self._save)

        tk.Label(box, text="JRiver host", anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        self.vars["JRIVER_HOST"] = tk.StringVar(value=self.env.get("JRIVER_HOST", "127.0.0.1:52199"))
        e = tk.Entry(box, textvariable=self.vars["JRIVER_HOST"], width=22)
        e.grid(row=1, column=1, sticky="w", padx=(12, 0))
        e.bind("<FocusOut>", self._save)

        tk.Label(box, text="YouTube playlist length", anchor="w").grid(row=2, column=0, sticky="w", pady=4)
        self.vars["YOUTUBE_PLAYLIST_LENGTH"] = tk.StringVar(value=self.env.get("YOUTUBE_PLAYLIST_LENGTH", "50"))
        cell = tk.Frame(box)
        cell.grid(row=2, column=1, sticky="w", padx=(12, 0))
        tk.Spinbox(cell, from_=5, to=50, textvariable=self.vars["YOUTUBE_PLAYLIST_LENGTH"], width=6,
                   command=self._save).pack(side="left")
        help_mark(cell, "How many videos a playlist holds when Output is set to YouTube (5 to 50). "
                        "50 is the most YouTube allows in one playlist link.").pack(side="left", padx=(8, 0))
        self.vars["YOUTUBE_PLAYLIST_LENGTH"].trace_add("write", self._save)

        self.vars["PREFER_OFFICIAL_VIDEOS"] = tk.BooleanVar(
            value=self.env.get("PREFER_OFFICIAL_VIDEOS", "0") in ("1", "true", "yes"))
        cell = tk.Frame(box)
        cell.grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(cell, text="Prefer official music videos",
                       variable=self.vars["PREFER_OFFICIAL_VIDEOS"], command=self._save).pack(side="left")
        help_mark(cell, "YouTube Music usually plays the audio-only version of a song, shown with the album cover. Tick this to play the artist's official music video instead, where one exists. Videos can run longer than the song because of intros and outros, and a few may not play in your region. Songs without an official video still play as audio.").pack(side="left", padx=(8, 0))

        tk.Label(box, text="Theme", anchor="w").grid(row=4, column=0, sticky="w", pady=4)
        self.vars["THEME"] = tk.StringVar(
            value="Dark" if self.env.get("THEME", "light").strip().lower() == "dark" else "Light")
        cell = tk.Frame(box)
        cell.grid(row=4, column=1, sticky="w", padx=(12, 0))
        theme_cb = ttk.Combobox(cell, textvariable=self.vars["THEME"], values=["Light", "Dark"],
                                state="readonly", width=8)
        theme_cb.pack(side="left")
        help_mark(cell, 'Light or dark colours for the whole app. The theme is applied when 24bit7 starts, so changing it offers a restart straight away.').pack(side="left", padx=(8, 0))
        theme_cb.bind("<<ComboboxSelected>>", self._on_theme_changed)

        row = tk.Frame(box)
        row.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        # Console Query: magenta, as it uses AI credits. Off by default; ticking it asks first.
        self.vars["CONSOLE_QUERY"] = tk.BooleanVar(
            value=self.env.get("CONSOLE_QUERY", "0").strip().lower() in ("1", "true", "yes"))
        ttk.Checkbutton(row, variable=self.vars["CONSOLE_QUERY"],
                        command=self._on_console_query_toggled).pack(side="left")
        cq_label = tk.Label(row, text="Enable Console Query", fg=PALETTE["ai_purple"], cursor="hand2")
        cq_label.pack(side="left")

        def label_clicked(_e):
            self.vars["CONSOLE_QUERY"].set(not self.vars["CONSOLE_QUERY"].get())
            self._on_console_query_toggled()
        cq_label.bind("<Button-1>", label_clicked)
        help_mark(row, "Adds Query to the console's Copy and Clear strip. Ask Claude why a playlist came "
                       "out the way it did, and get suggested setting changes. Each question sends the "
                       "console, your settings (without keys) and 24bit7's code, so it uses more Anthropic "
                       "credit than AI Moderator."
                  ).pack(side="left", padx=(8, 0))

        # --- Zones: which JRiver zones appear in the Play tab's Zone and Output lists ---
        # Filled when the tab is first shown, so a slow JRiver never delays startup.
        box = section(tab, "Zones",
                      "Show: untick a zone to hide it from the Zone and Output lists on the Play tab.\n"
                      "Default: the zone Now Playing opens on when 24bit7 starts. Picking a zone by hand "
                      "always wins.\n"
                      "Follow: Now Playing tracks whichever zone JRiver has active, so Default is greyed out.\n"
                      "A DLNA speaker such as a Sonos only appears once DLNA Controller is ticked in JRiver "
                      "(Tools > Options > Media Network > Advanced). Press Rescan after ticking it.")
        self.zone_frame = tk.Frame(box)
        self.zone_frame.grid(row=0, column=0, sticky="w")
        tk.Button(box, text="Rescan", width=10, command=self._fill_zone_boxes).grid(
            row=0, column=1, sticky="nw", padx=(24, 0))
        self.follow_var = tk.BooleanVar(value=engine.FOLLOW_ACTIVE_ZONE)
        ttk.Checkbutton(box, text="Follow JRiver's active zone", variable=self.follow_var,
                        command=self._save_zone_settings).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.zone_vars, self.zone_radios = {}, {}
        self.default_zone_var = tk.StringVar(value=engine.DEFAULT_ZONE)
        self._zones_filled = False
        tab.bind("<<Shown>>", lambda e: None if self._zones_filled else self._fill_zone_boxes())

        # --- Windows: start with Windows, start hidden in the tray, and close to the tray ---
        box = section(tab, "Windows",
                      "Voice Commands need 24bit7 running, so for voice after a restart, tick Start with "
                      "Windows and set JRiver Media Center or Media Server to start with Windows as well.")
        self.startup_var = tk.BooleanVar(value=tray.startup_command() is not None)
        startup_box = ttk.Checkbutton(box, text="Start with Windows", variable=self.startup_var,
                                      command=self._startup_toggled)
        startup_box.grid(row=0, column=0, sticky="w")
        self.vars["START_IN_TRAY"] = tk.BooleanVar(value=self.env.get("START_IN_TRAY", "1") in ("1", "true", "yes"))
        ttk.Checkbutton(box, text="Start in the tray (hidden, when Windows starts it)",
                        variable=self.vars["START_IN_TRAY"], command=self._save).grid(row=1, column=0, sticky="w")
        self.vars["CLOSE_TO_TRAY"] = tk.BooleanVar(value=self.env.get("CLOSE_TO_TRAY", "0") in ("1", "true", "yes"))
        ttk.Checkbutton(box, text="Close to tray (the X hides 24bit7; Quit from the tray icon)",
                        variable=self.vars["CLOSE_TO_TRAY"], command=self._save).grid(row=2, column=0, sticky="w")
        # Only shown when something needs doing: another copy starts with Windows, or the tray can't load
        self.startup_note = tk.Label(box, text="", fg="#a33", font=HELP_FONT, justify="left")
        self.startup_note.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self._show_startup_note()
        if not sys.platform.startswith("win"):
            startup_box.state(["disabled"])

        # --- Keyboard Shortcuts: global keys a remote can send, even with 24bit7 in the tray ---
        box = section(tab, "Keyboard Shortcuts",
                      "Shortcuts work anywhere in Windows, even while 24bit7 is minimised or in the tray, so a "
                      "remote that sends key presses (a Flirc, a Harmony, a phone app) can start a playlist.\n"
                      "Click a box and press the keys you want; Esc cancels. Letters and numbers need Ctrl, Alt, "
                      "Shift or Win with them; F-keys and media keys can be used on their own.\n"
                      "Each shortcut seeds from the zone's current track (paused or stopped counts), or from the "
                      "last track played when its Playing Now is empty, and plays to that zone. A zone with an "
                      "Alexa device that has Own settings uses that device's settings.")
        self._build_shortcuts(box)

    # --- About -------------------------------------------------------------------

    def _about_link(self, parent, text, target, row, blurb=None):
        """An underlined link in the section-title colour, with an optional grey line after it."""
        link = tk.Label(parent, text=text, fg=PALETTE["section_fg"], cursor="hand2",
                        font=("Segoe UI", 10, "underline"))
        link.grid(row=row, column=0, sticky="w", pady=2)
        if callable(target):
            link.bind("<Button-1>", lambda e: target())
        else:
            link.bind("<Button-1>", lambda e, u=target: webbrowser.open_new_tab(u))
        if blurb:
            tk.Label(parent, text=blurb, fg=PALETTE["help_fg"], font=HELP_FONT).grid(
                row=row, column=1, sticky="w", padx=(12, 0))
        return link

    def _open_manual(self):
        """The PDF beside the app if it's there, otherwise the manual on GitHub."""
        path = os.path.join(engine.APP_DIR, MANUAL_PDF)
        if os.path.exists(path):
            try:
                os.startfile(path)
                return
            except Exception:
                pass
        webbrowser.open_new_tab(REPO_URL + "/blob/main/docs/MANUAL.md")

    def _build_about(self, nb):
        """About: version, links, voice commands, credits and licence. Nothing here is saved."""
        tab = self._scroll_tab(nb, "About")
        packaged = getattr(sys, "frozen", False)
        version = engine.VERSION
        # The packaged app points at its own release; the dev copy at main, as it may be ahead
        ref = f"v{version}" if packaged else "main"

        # --- Logo, tagline, version ---
        head = tk.Frame(tab)
        head.grid(row=0, column=0, sticky="w", pady=(0, 4))
        for part, colour in (("24", PALETTE["brand_blue"]), ("bit", PALETTE["brand_orange"]),
                             ("7", PALETTE["brand_blue"])):
            tk.Label(head, text=part, font=("Segoe UI", 18, "bold"), fg=colour).pack(side="left")
        tk.Label(head, text="/", font=("Segoe UI", 10), fg=PALETTE["text_muted"]).pack(
            side="left", anchor="s", padx=(12, 8), pady=(0, 5))
        tk.Label(head, text="Perfect Playlists and Music Discovery", font=("Segoe UI", 10),
                 fg=PALETTE["text_muted"]).pack(side="left", anchor="s", pady=(0, 5))
        tk.Label(tab, text=f"Version {version}", font=LABEL_FONT).grid(row=1, column=0, sticky="w")
        tk.Label(tab, justify="left", wraplength=640, anchor="w",
                 text=("Builds playlists from your own JRiver library around whatever is playing, using "
                       "Last.fm, ListenBrainz, Deezer and YouTube Music. It runs without AI; the AI "
                       "features are optional and need your own Anthropic key.")).grid(
            row=2, column=0, sticky="w", pady=(6, 14))

        # --- Links ---
        box = section(tab, "Links")
        links = [
            ("User manual (PDF)", self._open_manual, "How everything in 24bit7 works."),
            ("GitHub", REPO_URL, "The code, issues and every release."),
            ("README", f"{REPO_URL}/blob/{ref}/README.md", "Overview, setup and what's new."),
            ("Release notes" if packaged else "Releases",
             f"{REPO_URL}/releases/tag/v{version}" if packaged else f"{REPO_URL}/releases",
             f"What changed in {version}." if packaged else "Every published version."),
            ("Reporting a problem", f"{REPO_URL}/blob/{ref}/README.md#reporting-a-problem",
             "What to send when something goes wrong."),
        ]
        if FORUM_URL:
            links.append(("JRiver forum thread", FORUM_URL, "Questions, ideas and feedback."))
        for r, (text, target, blurb) in enumerate(links):
            self._about_link(box, text, target, r, blurb)

        # --- Voice Commands ---
        box = section(tab, "Voice Commands")
        note = tk.Frame(box)
        note.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        tk.Label(note, justify="left", wraplength=640, anchor="w",
                 text=("Voice commands only work with the needle drop Alexa skill, which you set up "
                       "yourself under a free Amazon developer account.")).pack(anchor="w")
        guide = tk.Frame(note)
        guide.pack(anchor="w", pady=(2, 0))
        tk.Label(guide, text="Full instructions:").pack(side="left")
        g = tk.Label(guide, text="Setting up the Alexa skill", fg=PALETTE["section_fg"], cursor="hand2",
                     font=("Segoe UI", 9, "underline"))
        g.pack(side="left", padx=(6, 0))
        g.bind("<Button-1>", lambda e: webbrowser.open_new_tab(f"{REPO_URL}/blob/{ref}/docs/MANUAL.md#setting-up-the-alexa-skill"))
        tk.Label(box, text='Say "Alexa, open needle drop", then a command, or all in one breath: '
                           '"Alexa, ask needle drop for music like Agnes Obel".',
                 justify="left", wraplength=640, fg=PALETTE["help_fg"], font=HELP_FONT).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        for r, (say, get) in enumerate(VOICE_COMMAND_LIST, start=2):
            tk.Label(box, text=say, font=LABEL_FONT, anchor="w").grid(row=r, column=0, sticky="w", pady=1)
            tk.Label(box, text=get, anchor="w", justify="left", wraplength=420).grid(
                row=r, column=1, sticky="w", padx=(16, 0), pady=1)
        r = len(VOICE_COMMAND_LIST) + 2
        tk.Label(box, text="No command starts with \"play\": Alexa hands those to a music service instead.",
                 fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 2))
        self._about_link(box, "How Voice Commands work", f"{REPO_URL}/blob/{ref}/docs/MANUAL.md#voice-commands",
                         r + 1, "Every command, what you hear back, and settings per device.")

        # --- Credits ---
        box = section(tab, "Credits")
        tk.Label(box, text="Recommendation data and playback come from:", anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for r, (name, url) in enumerate(CREDITS, start=1):
            self._about_link(box, name, url, r)

        # --- Licence ---
        box = section(tab, "Licence")
        tk.Label(box, text="MIT Licence. Copyright (c) 2026 Ben Walker-Williams.", anchor="w").grid(
            row=0, column=0, sticky="w")
        self._about_link(box, "Read the licence", f"{REPO_URL}/blob/main/LICENSE", 1)

        # Wrapped text follows the window's width rather than a fixed number of pixels
        wrapped, todo = [], [tab]
        while todo:
            w = todo.pop()
            todo.extend(w.winfo_children())
            if isinstance(w, tk.Label) and int(float(str(w.cget("wraplength")) or 0)) > 0:
                wrapped.append(w)

        def rewrap(_e=None):
            right = tab.winfo_rootx() + tab.winfo_width()
            for label in wrapped:
                width = max(200, right - label.winfo_rootx() - 40)
                if int(float(str(label.cget("wraplength")))) != width:
                    label.config(wraplength=width)
        tab.bind("<Configure>", rewrap, add="+")

    # --- Keyboard Shortcuts ------------------------------------------------------

    def _build_shortcuts(self, box):
        self.hotkey_vars, self.hotkey_notes = {}, {}
        self._hotkey_capturing, self._hotkey_held = None, set()
        if not hotkeys.AVAILABLE:
            tk.Label(box, text="Keyboard shortcuts need Windows.", fg=PALETTE["help_fg"],
                     font=HELP_FONT).grid(row=0, column=0, sticky="w")
            return
        tk.Label(box, text="Shortcuts apply to which zone:", anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self.hotkey_zone_var = tk.StringVar(value=self.env.get("HOTKEY_ZONE", "") or hotkeys.NOW_PLAYING_ZONE)
        zone_cb = ttk.Combobox(box, textvariable=self.hotkey_zone_var, state="readonly", width=28,
                               values=[hotkeys.NOW_PLAYING_ZONE])
        zone_cb.config(postcommand=lambda: zone_cb.config(
            values=[hotkeys.NOW_PLAYING_ZONE] + engine.zone_names(include_hidden=True)))
        zone_cb.grid(row=0, column=1, columnspan=3, sticky="w", padx=(12, 0))
        zone_cb.bind("<<ComboboxSelected>>", lambda e: self._hotkey_zone_changed(zone_cb))
        for r, (code, label) in enumerate(hotkeys.ACTIONS, start=1):
            tk.Label(box, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=self.env.get(f"HOTKEY_{code}", ""))
            entry = tk.Entry(box, textvariable=var, width=24, state="readonly", cursor="hand2")
            entry.grid(row=r, column=1, sticky="w", padx=(12, 0))
            entry.bind("<Button-1>", lambda e: e.widget.focus_set())
            entry.bind("<FocusIn>", lambda e, c=code: self._hotkey_capture_start(c))
            entry.bind("<FocusOut>", lambda e, c=code: self._hotkey_capture_end(c))
            entry.bind("<KeyPress>", lambda e, c=code: self._hotkey_key(c, e, True))
            entry.bind("<KeyRelease>", lambda e, c=code: self._hotkey_key(c, e, False))
            tk.Button(box, text="Clear", width=7, command=lambda c=code: self._hotkey_clear(c)).grid(
                row=r, column=2, sticky="w", padx=(8, 0))
            note = tk.Label(box, text="", fg="#a33", font=HELP_FONT, anchor="w", justify="left")
            note.grid(row=r, column=3, sticky="w", padx=(10, 0))
            self.hotkey_vars[code], self.hotkey_notes[code] = var, note

    def refresh_hotkey_notes(self, problems=None):
        """Shows next to each box any shortcut Windows wouldn't take."""
        problems = hotkeys.errors() if problems is None else problems
        for code, note in getattr(self, "hotkey_notes", {}).items():
            note.config(text=problems.get(code, ""), fg="#a33")

    def _hotkey_restart(self):
        self.refresh_hotkey_notes(hotkeys.restart())

    def _hotkey_zone_changed(self, combo):
        value = self.hotkey_zone_var.get()
        try:
            write_env({"HOTKEY_ZONE": "" if value == hotkeys.NOW_PLAYING_ZONE else value})
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        combo.selection_clear()

    def _hotkey_save(self, code, combo):
        self.hotkey_vars[code].set(combo)
        try:
            write_env({f"HOTKEY_{code}": combo})   # blank, not removed, so the change is picked up at once
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)

    def _hotkey_clear(self, code):
        self._hotkey_save(code, "")
        if self._hotkey_capturing is None:
            self._hotkey_restart()

    def _hotkey_capture_start(self, code):
        """While a box is being set, every shortcut is released, so pressing one doesn't start a playlist."""
        self._hotkey_capturing, self._hotkey_held = code, set()
        hotkeys.stop()
        self.hotkey_notes[code].config(text="Press the keys you want (Esc to cancel)", fg=PALETTE["help_fg"])

    def _hotkey_capture_end(self, code):
        if self._hotkey_capturing != code:
            return
        self._hotkey_capturing, self._hotkey_held = None, set()
        self._hotkey_restart()

    def _hotkey_key(self, code, event, down):
        """Builds the shortcut from the keys held: modifiers first, then the key itself."""
        vk = event.keycode
        if vk in hotkeys.MODIFIER_VKS:
            (self._hotkey_held.add if down else self._hotkey_held.discard)(hotkeys.MODIFIER_VKS[vk])
            return "break"
        if not down:
            return "break"
        mods = set(self._hotkey_held)
        if event.state & 0x0001:
            mods.add("Shift")
        if event.state & 0x0004:
            mods.add("Ctrl")
        if event.state & 0x20000:
            mods.add("Alt")
        note = self.hotkey_notes[code]
        if event.keysym == "Escape" and not mods:
            self.focus_set()   # cancel: the box keeps what it had
            return "break"
        if event.keysym in ("Tab", "ISO_Left_Tab") and not mods:
            return None        # Tab still moves to the next control
        if hotkeys.key_name(vk) is None:
            note.config(text="That key can't be used for a shortcut.", fg="#a33")
            return "break"
        if not mods and hotkeys.needs_modifier(vk):
            note.config(text="Add Ctrl, Alt, Shift or Win to that key.", fg="#a33")
            return "break"
        combo = hotkeys.combo_text(mods, vk)
        for other, var in self.hotkey_vars.items():
            if other != code and var.get() == combo:
                note.config(text=f"Already used for {hotkeys.LABELS[other]}.", fg="#a33")
                return "break"
        self._hotkey_save(code, combo)
        self.focus_set()   # done: leaving the box registers the shortcuts again
        return "break"

    def _startup_toggled(self):
        try:
            tray.set_startup(self.startup_var.get())
        except Exception as e:
            self.startup_var.set(tray.startup_command() is not None)
            messagebox.showerror("Start with Windows", f"Couldn't change the startup setting: {e}", parent=self)
        self._show_startup_note()

    def _show_startup_note(self):
        lines = []
        current = tray.startup_command()
        if current and current != tray.launch_command():
            lines.append("Windows starts a different copy of 24bit7. Untick and tick again to start this one.")
        if not tray.available():
            lines.append("The tray needs pystray and Pillow: run  pip install pystray Pillow  and restart.")
        self.startup_note.config(text="\n".join(lines))
        if lines:
            self.startup_note.grid()
        else:
            self.startup_note.grid_remove()

    def _fill_zone_boxes(self):
        """Per zone: a Show tick (hidden zones drop off the Play tab) and a Default button."""
        self._zones_filled = True
        for child in self.zone_frame.winfo_children():
            child.destroy()
        engine.refresh_settings_if_changed()
        names = engine.zone_names(include_hidden=True)
        self.zone_vars, self.zone_radios = {}, {}
        if not names:
            tk.Label(self.zone_frame, text="No zones found. Is JRiver running, with Media Network on?",
                     fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=0, column=0, sticky="w")
            return
        tk.Label(self.zone_frame, text="Show", fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=0, column=0, sticky="w")
        tk.Label(self.zone_frame, text="Default", fg=PALETTE["help_fg"], font=HELP_FONT).grid(
            row=0, column=1, sticky="w", padx=(24, 0))
        rb = ttk.Radiobutton(self.zone_frame, text="JRiver's active zone", value="",
                             variable=self.default_zone_var, command=self._save_zone_settings)
        rb.grid(row=1, column=1, sticky="w", padx=(24, 0))
        self.zone_radios[""] = rb
        # A default zone JRiver can't see right now (speaker unplugged) still gets a row
        missing = [engine.DEFAULT_ZONE] if engine.DEFAULT_ZONE and engine.DEFAULT_ZONE not in names else []
        for r, name in enumerate(names + missing, start=2):
            if name in names:
                v = tk.BooleanVar(value=name not in engine.HIDDEN_ZONES)
                ttk.Checkbutton(self.zone_frame, text=name, variable=v,
                                command=self._save_zone_settings).grid(row=r, column=0, sticky="w")
                self.zone_vars[name] = v
            else:
                tk.Label(self.zone_frame, text=f"{name} (not found)", fg=PALETTE["help_fg"]).grid(row=r, column=0, sticky="w")
            rb = ttk.Radiobutton(self.zone_frame, value=name, variable=self.default_zone_var,
                                 command=self._save_zone_settings)
            rb.grid(row=r, column=1, sticky="w", padx=(24, 0))
            self.zone_radios[name] = rb
        self._sync_zone_controls()

    def _sync_zone_controls(self):
        """Default greys out while Follow is ticked, and for any hidden zone."""
        follow = self.follow_var.get()
        for name, rb in self.zone_radios.items():
            hidden = name in self.zone_vars and not self.zone_vars[name].get()
            rb.state(["disabled"] if follow or hidden else ["!disabled"])

    def _save_zone_settings(self):
        # Hiding the default zone puts the default back to JRiver's active zone
        default = self.default_zone_var.get()
        if default in self.zone_vars and not self.zone_vars[default].get():
            self.default_zone_var.set("")
        self._sync_zone_controls()
        # Zones hidden earlier but not in JRiver right now stay hidden
        hidden = {n for n, v in self.zone_vars.items() if not v.get()}
        hidden |= {n for n in engine.HIDDEN_ZONES if n not in self.zone_vars}
        try:
            write_env({"HIDDEN_ZONES": "|".join(sorted(hidden)),
                       "DEFAULT_ZONE": self.default_zone_var.get(),
                       "FOLLOW_ACTIVE_ZONE": "1" if self.follow_var.get() else "0"})
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)

    def _build_voice(self, nb):
        """Voice Commands: the listener switch, its key, the devices heard, and a test."""
        tab = self._scroll_tab(nb, "Voice Commands")

        # --- Voice Commands: the switch and the key ---
        box = section(tab, "Voice Commands")
        self.voice_on = tk.BooleanVar(value=engine.VOICE_ENABLED)
        ttk.Checkbutton(box, text="Voice Commands (listen for commands from the Alexa skill)",
                        variable=self.voice_on, command=self._voice_toggled).grid(
            row=0, column=0, columnspan=5, sticky="w")
        self.voice_status = tk.Label(box, text=voice.status(), fg=PALETTE["help_fg"], font=HELP_FONT)
        self.voice_status.grid(row=1, column=0, columnspan=5, sticky="w")

        tk.Label(box, text="Key", anchor="w").grid(row=2, column=0, sticky="w", pady=(12, 2))
        self.voice_key_var = tk.StringVar(value=engine.VOICE_KEY)
        key_box = tk.Frame(box)   # hidden like the other keys; Show is unticked every time Settings opens
        key_box.grid(row=2, column=1, sticky="w", padx=(12, 8), pady=(12, 2))
        key_entry = tk.Entry(key_box, textvariable=self.voice_key_var, width=40, state="readonly",
                             show="\u2022")
        key_entry.pack(side="left")
        show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_box, text="Show", variable=show_key,
                       command=lambda: key_entry.config(show="" if show_key.get() else "\u2022")).pack(
            side="left", padx=(6, 0))
        tk.Button(box, text="Copy", width=8, command=self._voice_copy_key).grid(row=2, column=2, sticky="w", pady=(12, 2))
        tk.Button(box, text="New key", width=8, command=self._voice_new_key).grid(
            row=2, column=3, sticky="w", padx=(8, 0), pady=(12, 2))
        help_mark(box, "The Alexa skill sends this key with every command; anything without it is refused. "
                       "24bit7 only listens on this PC. The tunnel set up for the skill connects it to Amazon."
                  ).grid(row=2, column=4, sticky="w", padx=(8, 0), pady=(12, 2))

        # --- Devices ---
        box = section(tab, "Devices",
                      "Say a command on a device that isn't set up and it appears here. Pick the zone it "
                      "plays to.")
        self.voice_dev_frame = tk.Frame(box)
        self.voice_dev_frame.grid(row=0, column=0, sticky="w")
        tk.Button(box, text="Refresh", width=10, command=self._fill_voice_devices).grid(
            row=1, column=0, sticky="w", pady=(8, 0))

        # --- Test ---
        box = section(tab, "Test", "Sends a pretend command, as if a device had heard it. "
                                   "The build itself shows in the Play tab log.")
        test = tk.Frame(box)
        test.grid(row=0, column=0, sticky="w")
        tk.Label(test, text="Music like").pack(side="left")
        self.voice_test_artist = tk.Entry(test, width=24)
        self.voice_test_artist.insert(0, "Agnes Obel")
        self.voice_test_artist.pack(side="left", padx=(6, 12))
        tk.Label(test, text="on").pack(side="left")
        self.voice_test_zone = ttk.Combobox(test, state="readonly", width=22,
                                            postcommand=lambda: self.voice_test_zone.config(values=engine.zone_names()))
        self.voice_test_zone.pack(side="left", padx=(6, 12))
        tk.Button(test, text="Send test", width=10, command=self._voice_test).pack(side="left")
        self.voice_test_result = tk.Label(box, text="", fg=PALETTE["help_fg"], font=HELP_FONT, justify="left")
        self.voice_test_result.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # --- Guides: links to the two Voice Commands documents on GitHub ---
        box = section(tab, "Guides")
        for r, (title, url, blurb) in enumerate(VOICE_DOCS):
            link = tk.Label(box, text=title, fg=PALETTE["section_fg"], cursor="hand2", font=("Segoe UI", 10, "underline"))
            link.grid(row=r, column=0, sticky="w", pady=2)
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open_new_tab(u))
            tk.Label(box, text=blurb, fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=r, column=1, sticky="w", padx=(12, 0))

        tab.bind("<<Shown>>", lambda e: (self.voice_status.config(text=voice.status()), self._fill_voice_devices()))

    def _voice_toggled(self):
        updates = {"VOICE_ENABLED": "1" if self.voice_on.get() else "0"}
        if self.voice_on.get() and not engine.VOICE_KEY:
            updates["VOICE_KEY"] = voice.new_key()
        try:
            write_env(updates)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        self._voice_restart()

    def _voice_restart(self):
        self.voice_status.config(text=voice.restart())
        self.voice_key_var.set(engine.VOICE_KEY or "")

    def _voice_copy_key(self):
        self.clipboard_clear()
        self.clipboard_append(self.voice_key_var.get())

    def _voice_new_key(self):
        if engine.VOICE_KEY and not messagebox.askyesno(
                "New key", "The Alexa skill will need the new key as well. Make a new one?", parent=self):
            return
        try:
            write_env({"VOICE_KEY": voice.new_key()})
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        self._voice_restart()

    def _fill_voice_devices(self):
        """One row per Alexa device heard: its name, the zone it plays to, when it was last heard."""
        for child in self.voice_dev_frame.winfo_children():
            child.destroy()
        rows = voice.devices()
        if not rows:
            tk.Label(self.voice_dev_frame, text="No devices heard yet.", fg=PALETTE["help_fg"], font=HELP_FONT).grid(
                row=0, column=0, sticky="w")
            return
        zones = engine.zone_names()
        for c, heading in enumerate(("Name", "Zone", "Last heard", "")):
            tk.Label(self.voice_dev_frame, text=heading, fg=PALETTE["help_fg"], font=HELP_FONT).grid(
                row=0, column=c, sticky="w", padx=(0, 12))
        own_head = tk.Frame(self.voice_dev_frame)
        own_head.grid(row=0, column=4, sticky="w", padx=(12, 0))
        switch_head = tk.Frame(self.voice_dev_frame)
        switch_head.grid(row=0, column=5, sticky="w", padx=(12, 0))
        tk.Label(switch_head, text="Enable Switch To", fg=PALETTE["help_fg"], font=HELP_FONT).pack(side="left")
        help_mark(switch_head, "Ticked, this device's zone is one you can switch the music to, with \"Alexa, ask "
                               "needle drop to switch\" or the Switch Zones keyboard shortcut. With two zones "
                               "ticked, switching moves the music straight to the other one. With three or more, "
                               "Alexa asks which zone, or you can say \"switch to\" and the zone name; the "
                               "shortcut steps through them in turn. The music carries on from the same track, "
                               "and the zone it left stops. Two devices on the same zone share one tick.").pack(
            side="left", padx=(6, 0))
        switch_off = voice.switch_unticked()
        tk.Label(own_head, text="Own settings", fg=PALETTE["help_fg"], font=HELP_FONT).pack(side="left")
        help_mark(own_head, "Tick a device to give it its own tab under Settings > Sources and Settings > "
                            "Playlist. Each tab starts with Copy Windows (Main) ticked, following the Windows "
                            "app's settings; untick Copy there to change that device's settings, for example "
                            "to try different settings on two speakers. Unticked here, the device uses Windows "
                            "(Main), and anything it had is kept for next time.").pack(side="left", padx=(6, 0))
        for r, (device_id, name, zone, heard, own) in enumerate(rows, start=1):
            name_var = tk.StringVar(value=name)
            entry = tk.Entry(self.voice_dev_frame, textvariable=name_var, width=22)
            entry.grid(row=r, column=0, sticky="w", padx=(0, 12), pady=2)
            save_name = lambda e, d=device_id, v=name_var: voice.update_device(d, name=v.get().strip() or "Device")
            entry.bind("<FocusOut>", save_name)
            entry.bind("<Return>", save_name)
            zone_var = tk.StringVar(value=zone or "Not set")
            cb = ttk.Combobox(self.voice_dev_frame, textvariable=zone_var, state="readonly", width=22,
                              values=["Not set"] + zones + ([zone] if zone and zone not in zones else []))
            cb.grid(row=r, column=1, sticky="w", padx=(0, 12), pady=2)
            cb.bind("<<ComboboxSelected>>", lambda e, d=device_id, v=zone_var: voice.update_device(
                d, zone="" if v.get() == "Not set" else v.get()))
            tk.Label(self.voice_dev_frame, text=heard or "").grid(row=r, column=2, sticky="w", padx=(0, 12))
            tk.Button(self.voice_dev_frame, text="Remove", width=8,
                      command=lambda d=device_id: (voice.remove_device(d), self._fill_voice_devices())).grid(
                row=r, column=3, sticky="w", pady=2)
            own_var = tk.BooleanVar(value=bool(own))
            ttk.Checkbutton(self.voice_dev_frame, variable=own_var,
                            command=lambda d=device_id, v=own_var: voice.set_own_settings(d, v.get())).grid(
                row=r, column=4, sticky="w", padx=(12, 0))
            switch_var = tk.BooleanVar(value=bool(zone) and zone not in switch_off)
            box = ttk.Checkbutton(self.voice_dev_frame, variable=switch_var,
                                  command=lambda z=zone, v=switch_var: (voice.set_switch_enabled(z, v.get()),
                                                                       self._fill_voice_devices()))
            box.grid(row=r, column=5, sticky="w", padx=(12, 0))
            if not zone:   # no zone yet: nothing to switch to
                box.state(["disabled"])

    def _voice_test(self):
        if not voice.status().startswith("Listening"):
            self.voice_test_result.config(text="Switch Voice Commands on first.")
            return
        zone = self.voice_test_zone.get()
        artist = self.voice_test_artist.get().strip()
        if not zone or not artist:
            self.voice_test_result.config(text="Type an artist and pick a zone to test with.")
            return
        self.voice_test_result.config(text="Sending...")
        result = []
        # sent from a background thread, so the window never waits on the listener
        threading.Thread(target=lambda: result.append(voice.send_test(artist, zone)), daemon=True).start()

        def show():
            if result:
                self.voice_test_result.config(text="Alexa would " + result[0])
            else:
                self.after(200, show)
        self.after(200, show)

    def _build_search_sites(self, nb):
        """Discover search sites: which stores and reference sites to open per row."""
        tab = self._scroll_tab(nb, "Search")
        ttk.Style(self).configure("Big.TCheckbutton", font=("Segoe UI", 11))
        cols = 4

        def ticks(box, group, options, chosen):
            for c in range(cols):
                box.grid_columnconfigure(c, weight=1, uniform="sites")   # equal-width columns
            self.vars[group] = {}
            for i, (code, label) in enumerate(options):
                v = tk.BooleanVar(value=code in chosen)
                self.vars[group][code] = v
                ttk.Checkbutton(box, text=label, variable=v, command=self._save,
                                style="Big.TCheckbutton").grid(
                    row=i // cols, column=i % cols, sticky="w", padx=(0, 16), pady=2)

        # Carry over a pre-1.1.0 single DIGITAL_STORE if the new key isn't there yet.
        stores_raw = self.env.get("DIGITAL_STORES", self.env.get("DIGITAL_STORE", "bandcamp"))
        box = section(tab, "Stores",
                      "Search by artist and track. Each ticked site gets its own button on the Discover tab. "
                      "At least one store must stay ticked.")
        ticks(box, "DIGITAL_STORES", engine.STORE_OPTIONS,
              [x.strip().lower() for x in stores_raw.split(",") if x.strip()])
        box = section(tab, "Reference", "Search the artist, for a discography. Each ticked site gets its own "
                                        "button on the Discover tab.")
        ticks(box, "REFERENCE_SITES", engine.REFERENCE_OPTIONS, self._csv_list("REFERENCE_SITES", ""))
        box = section(tab, "Listen", "Search by artist and track. Each ticked site gets its own button on the "
                                     "Discover tab.")
        ticks(box, "LISTEN_SITES", engine.LISTEN_OPTIONS, self._csv_list("LISTEN_SITES", "youtube"))

        box = section(tab, "Custom sites",
                      "To add a site: search for anything on it, copy the address from your browser, then replace "
                      "your search words with {query}. Example: https://www.prestomusic.com/search?q={query}\n"
                      "Clear the button name to remove a site. Only links starting with http:// or https:// "
                      "are used.")
        box.grid_columnconfigure(1, weight=1)   # the link field takes whatever width is left
        for c, heading in enumerate(("Button name", "Search link", "Search by")):
            tk.Label(box, text=heading, fg=PALETTE["help_fg"], font=HELP_FONT).grid(
                row=0, column=c, sticky="w", padx=(0, 8))
        for n in range(1, engine.CUSTOM_SITE_SLOTS + 1):
            name_var = tk.StringVar(value=self.env.get(f"CUSTOM_SITE_{n}_NAME", ""))
            url_var = tk.StringVar(value=self.env.get(f"CUSTOM_SITE_{n}_URL", ""))
            artist_only = self.env.get(f"CUSTOM_SITE_{n}_MODE", "track").strip().lower() == "artist"
            mode_var = tk.StringVar(value="Artist only" if artist_only else "Artist and track")
            self.vars[f"CUSTOM_SITE_{n}_NAME"] = name_var
            self.vars[f"CUSTOM_SITE_{n}_URL"] = url_var
            self.vars[f"CUSTOM_SITE_{n}_MODE"] = mode_var
            name_entry = tk.Entry(box, textvariable=name_var, width=18)
            name_entry.grid(row=n, column=0, sticky="w", padx=(0, 8), pady=2)
            url_entry = tk.Entry(box, textvariable=url_var, width=20)
            url_entry.grid(row=n, column=1, sticky="ew", padx=(0, 8), pady=2)
            for entry in (name_entry, url_entry):
                entry.bind("<FocusOut>", self._save)   # save when leaving the field
            mode_cb = ttk.Combobox(box, textvariable=mode_var, state="readonly", width=16,
                                   values=["Artist and track", "Artist only"])
            mode_cb.grid(row=n, column=2, sticky="w", pady=2)
            mode_cb.bind("<<ComboboxSelected>>", self._save)

    # --- helpers -----------------------------------------------------------

    def _csv_list(self, key, default):
        return [x.strip().lower() for x in self.env.get(key, default).split(",") if x.strip()]

    def _show_help(self, key):
        title, body = KEY_HELP[key]
        messagebox.showinfo(title, body, parent=self)