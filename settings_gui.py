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
import re
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox, filedialog

import engine
import tray
import voice
import hotkeys
import saved_playlists
import filters
import buttons
import devices
import ai_usage
import i18n
import tabs
from tabs import TabbedPane, PALETTE, FlatButton, TCombobox, NamePrompt, PromptWindow, PickRow
from datetime import datetime
from i18n import N_, t, tn

ENV_FILE = engine.ENV_FILE   # single source of truth for where .env lives

# The Voice Commands guides, on GitHub (linked from the bottom of Settings > Voice Commands)
DOCS_URL = "https://github.com/24bit7/24bit7/blob/main/docs/"
VOICE_DOCS = [(N_("How Voice Commands work"), DOCS_URL + "MANUAL.md#voice-commands",
               N_("What it does, what you can say, and how zones and devices fit together.")),
              (N_("Setting up the Alexa skill"), DOCS_URL + "MANUAL.md#setting-up-the-alexa-skill",
               N_("Step by step, from an Amazon developer account to your first command."))]

# --- About tab -------------------------------------------------------------
REPO_URL = "https://github.com/24bit7/24bit7"
FORUM_URL = "https://yabb.jriver.com/interact/index.php/topic,144381.0.html"   # the JRiver forum thread; empty hides the link
MANUAL_PDF = "24bit7_Manual.pdf"   # shipped next to 24bit7.exe in the release zip
MANUAL_PDFS = {"de": ("24bit7_Handbuch.pdf", "MANUAL.de.md")}   # other languages' manuals, and their source
# The About tab's opening lines: they name every music source and every AI provider
ABOUT_INTRO = (N_("Builds playlists from your own JRiver library around whatever is playing, using "
               "Last.fm, ListenBrainz, Deezer, Tidal and YouTube Music. It runs without AI; the AI "
               "features are optional and need your own key for Anthropic, OpenAI or Google Gemini, "
               "or a local model through Ollama."))
# Settings > Voice Commands > New Playlists: (saved value, label shown)
VOICE_NEW_OPTIONS = [("after", N_("After this track")), ("now", N_("Play now"))]

# The voice commands, as in the manual's Voice Commands chapter
VOICE_COMMAND_LIST = [
    ("songs by <artist>", N_("Artist's Top Tracks")),
    ("music like <artist>", N_("Similar Artists, seeded from the artist's most popular track")),
    ("tracks like <song>  (by <artist>)", N_("Similar Tracks")),
    ("genre <anything>", N_("AI Playlist, e.g. \"genre nu metal with grunge\" (needs the AI set up)")),
    ("only <artist> <mood>", N_("AI Playlist of one artist you own, e.g. \"only chill Led Zeppelin\" (needs the AI set up)")),
    ("album <name>", N_("Plays the album now, in track order")),
    ("song <title>  (by <artist>)", N_("Plays the song now, then stops")),
    ("playlist <name>", N_("Plays one of your JRiver playlists or smartlists now")),
    ("shuffle songs by <artist>", N_("Every track by the artist in your library, shuffled")),
    ("skip / next / next song", N_("The next track in that device's zone")),
    ("who is this / what's playing", N_("Alexa says the track, artist and album")),
    ("more like this / more of this", N_("Similar Tracks seeded from what's playing")),
    ("more artists like this", N_("Similar Artists seeded from what's playing")),
    ("switch / switch to <zone>", N_("Moves what's playing to another zone (Enable Switch To)")),
    ("stop / pause / resume the music", N_("On that device's zone")),
    ("keep it going / non stop / go continuous", N_("Non-stop, once, for whatever is playing")),
    ("list commands / help", N_("Alexa reads the commands once")),
]
CREDITS = [
    ("Last.fm", "https://www.last.fm"),
    ("ListenBrainz", "https://listenbrainz.org"),
    ("MusicBrainz", "https://musicbrainz.org"),
    ("Deezer", "https://www.deezer.com"),
    ("Tidal", "https://tidal.com"),
    ("YouTube Music (via ytmusicapi)", "https://github.com/sigma67/ytmusicapi"),
    ("Discogs", "https://www.discogs.com"),
    ("Anthropic (Claude)", "https://www.anthropic.com"),
    ("OpenAI", "https://openai.com"),
    ("Google Gemini", "https://ai.google.dev"),
    ("Ollama", "https://ollama.com"),
    ("JRiver Media Center", "https://jriver.com"),
]

THANKS = [   # Settings > About > Thanks, and the README's Thanks section
    ("datdude", N_("Early testing and ideas, including Switch Profiles.")),
    ("Helmut", N_("Shaping Review.")),
    ("Denis", N_("The local AI work, testing it with Ollama and Gemma 3 4B, and testing 24bit7 against a 187,000-track library.")),
]


# Listed alphabetically by display name
SOURCE_NAMES = [("ai", "AI"), ("deezer", "Deezer"),
                ("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"),
                ("tidal", "Tidal"), ("youtube", "YouTube")]
# YouTube suggests artists only, so it isn't offered as a top-track source
TOP_SOURCE_NAMES = [s for s in SOURCE_NAMES if s[0] != "youtube"]
# Sources that can suggest tracks like a track
TRACK_SOURCE_NAMES = [("ai", "AI"), ("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"), ("tidal", "Tidal"),
                      ("youtube", "YouTube")]


KEY_HELP = {
    "LASTFM_API_KEY": (N_("Last.fm API key"),
        N_("Create an API account at last.fm/api (Get an API account).\n"
        "Your key is shown on your account's API page. It's free.\n"
        "24bit7 comes with a key built in, so this is optional.\n"
        "A key of your own is used instead when you fill it in.")),
    "LISTENBRAINZ_TOKEN": (N_("ListenBrainz token"),
        N_("Sign in at listenbrainz.org (uses a MusicBrainz account),\n"
        "then copy your User Token from listenbrainz.org/settings.")),
    "TIDAL_CLIENT_ID": (N_("Tidal Client ID"),
        N_("At developer.tidal.com, sign in with a TIDAL account, open Dashboard\n"
        "and choose Create App. Copy the Client ID and Client Secret from the\n"
        "app's overview page into the two Tidal fields. It's free.")),
    "TIDAL_CLIENT_SECRET": (N_("Tidal Client Secret"),
        N_("At developer.tidal.com, sign in with a TIDAL account, open Dashboard\n"
        "and choose Create App. Copy the Client ID and Client Secret from the\n"
        "app's overview page into the two Tidal fields. It's free.")),
    "TIDAL_ACCOUNT": (N_("Sign In to Tidal"),
        N_("Only needed to send playlists to Tidal. At developer.tidal.com, open Dashboard\n"
        "and the app you made for the Client ID. Under Redirect URIs add\n"
        "http://localhost:47807/tidal and under Scopes tick playlists.read\n"
        "and playlists.write. Save, then press Sign In to Tidal here.")),
    "DISCOGS_TOKEN": (N_("Discogs token"),
        N_("Go to discogs.com/settings/developers and click\n"
        "'Generate new token' under Personal access token.")),
    "ANTHROPIC_API_KEY": (N_("Anthropic API key"),
        N_("At platform.claude.com, add billing credit under Settings,\n"
        "then create a key under API keys. Copy it once at creation.")),
    "OPENAI_API_KEY": (N_("OpenAI API key"),
        N_("At platform.openai.com, add billing credit under Settings,\n"
        "then create a key under API keys. Copy it once at creation.")),
    "GEMINI_API_KEY": (N_("Google Gemini API key"),
        N_("At aistudio.google.com, choose Get API key and create one.\n"
        "There's a free tier with lower limits; add billing for more.")),
    "OLLAMA_URL": (N_("Ollama"),
        N_("Install Ollama from ollama.com, then pull a model, for example\n"
        "ollama pull gemma3:4b. Ollama's address is usually the one filled\n"
        "in here; change it only if Ollama runs on another computer.")),
    "JRIVER_PASS": (N_("JRiver Media Network"),
        N_("Set the username and password in JRiver under\n"
        "Tools > Options > Media Network > Authentication.")),
}

KEY_FIELDS = ["LASTFM_API_KEY", "LISTENBRAINZ_TOKEN", "DISCOGS_TOKEN", "TIDAL_CLIENT_ID", "TIDAL_CLIENT_SECRET",
              "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OLLAMA_URL", "OLLAMA_MODEL",
              "JRIVER_USER", "JRIVER_PASS"]
AI_FIELDS = {"anthropic": ["ANTHROPIC_API_KEY"], "openai": ["OPENAI_API_KEY"], "gemini": ["GEMINI_API_KEY"],
             "ollama": ["OLLAMA_URL", "OLLAMA_MODEL"]}   # Settings > Keys > AI shows the chosen provider's
AI_KEY_FIELDS = {k for fields in AI_FIELDS.values() for k in fields}
UNTESTED_NOTE = N_("Untested so far: please report how it goes on the JRiver forum or GitHub.")

NO_KEY_TEXT = N_("You need to set up the AI under Settings > Keys to use this function")
CONSOLE_QUERY_WARNING = (N_("Console Query sends the console, your settings (without keys) and 24bit7's "
                         "code to your AI provider each time you ask a question. The first question costs a few "
                         "pence, more than the Moderator.\n\nTurn it on?"))
MODERATOR_CHOICES = [N_("Off"), N_("Relaxed"), N_("Balanced"), N_("Strict")]   # English: shown through t()
MODERATOR_LEVELS_HELP = (
    N_("Relaxed: removes only clear clashes, at most a fifth of the tracks.\n"
    "Balanced: removes anything that noticeably shifts the tone, energy or mood, at most two fifths.\n"
    "Strict: keeps only tracks close to the seed, however many that leaves. Drift can top a short "
    "playlist up.\n"
    "Tracks it doesn't know well enough to judge are always kept, and genre is never a reason on its own."))
def moderator_warning():
    """The one-off note when Moderator is first switched on, naming the chosen provider."""
    if engine.AI_PROVIDER == "ollama":
        return t("Moderator checks each playlist with your own AI model (Ollama), on your PC. It costs nothing.")
    return t("Moderator checks each playlist using your chosen AI ({name}), which uses a little credit from your "
             "{name} account. Each playlist costs a fraction of a penny.", name=engine.ai_provider_name())


NOTE_DELAY_MS = 500   # a note waits this long, so passing the pointer over a title doesn't flash one up
NOTE_WRAP = 720       # wide and short rather than narrow and tall


def scaled(widget, pixels):
    """A width designed at 100% display scaling, at this display's scaling."""
    try:
        return int(pixels * max(1.0, widget.winfo_fpixels("1i") / 96.0))
    except tk.TclError:
        return pixels


def follow_width(label, container, margin=24, minimum=300):
    """Wrapped text follows its container's width rather than a fixed number of pixels."""
    def fit(_event=None):
        try:
            right = container.winfo_rootx() + container.winfo_width()
            width = max(scaled(label, minimum), right - label.winfo_rootx() - margin)
        except tk.TclError:
            return
        if int(float(str(label.cget("wraplength")) or 0)) != width:
            label.config(wraplength=width)
    container.bind("<Configure>", fit, add="+")
    label.bind("<Map>", fit, add="+")


class Tooltip:
    """
    A small note shown while the pointer rests on a widget, after a short delay, or on a
    click (when click is True), when when() says so. Kept fully on screen.
    """

    def __init__(self, widget, text, when=lambda: True, click=True, delay=NOTE_DELAY_MS, wrap=None):
        self.widget, self.text, self.when, self.tip = widget, text, when, None
        self.wrap = wrap   # its width in pixels, or a function giving it; the usual width if None
        self.delay, self._pending = delay, None
        widget._has_note = True
        widget._tooltip = self
        widget.bind("<Enter>", lambda e: self._wait(), add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        if click:
            widget.bind("<Button-1>", lambda e: self.show(), add="+")
        widget.bind("<Destroy>", lambda e: self.hide(), add="+")

    def _wait(self):
        self._cancel()
        if self.delay:
            self._pending = self.widget.after(self.delay, self.show)
        else:
            self.show()

    def _cancel(self):
        if self._pending is not None:
            try:
                self.widget.after_cancel(self._pending)
            except tk.TclError:
                pass
            self._pending = None

    def show(self):
        self._cancel()
        if self.tip or not self.when():
            return
        try:
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        tk.Label(self.tip, text=self.text, bg=PALETTE["tooltip_bg"], fg=PALETTE["tooltip_fg"], relief="solid",
                 borderwidth=1, justify="left", wraplength=self._wrap(), font=("Segoe UI", 9),
                 padx=10, pady=6).pack()
        self.tip.update_idletasks()   # its size, so it can be kept on screen
        w, h = self.tip.winfo_reqwidth(), self.tip.winfo_reqheight()
        sw, sh = self.tip.winfo_screenwidth(), self.tip.winfo_screenheight()
        x = max(0, min(x, sw - w - 4))
        if y + h > sh - 4:   # no room below: above the widget instead
            y = max(0, self.widget.winfo_rooty() - h - 4)
        self.tip.wm_geometry(f"+{x}+{y}")

    def _wrap(self):
        wrap = self.wrap() if callable(self.wrap) else self.wrap
        return wrap or scaled(self.widget, NOTE_WRAP)

    def hide(self):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


def warn_moderator_once(parent):
    """The one-off credits warning, the first time Moderator is switched on anywhere."""
    if engine.MODERATOR_WARNED:
        return
    messagebox.showinfo(t("Moderator"), moderator_warning(), parent=parent)
    write_env({"MODERATOR_WARNED": "1"})
    engine.MODERATOR_WARNED = True


HEADING_FONT = ("Segoe UI", 10, "bold")
# the sections for the whole playlist, under its configs, in this order (English titles: see _fill_playlist)
WHOLE_SECTIONS = ("Drift", "Deep Cuts", "Non-stop", "Hidden Tracks", "If All Else Fails", "Run After Building")
HELP_FONT = ("Segoe UI", 8)
HELP_FG = "#666"
LABEL_FONT = ("Segoe UI", 9, "bold")
SECTION_FG = "#1f4e8c"    # section titles, in the logo blue
SECTION_EDGE = "#aab4c3"  # the thin line round each section
HELP_MARK_BG = "#8a97aa"


NOTE_TITLES = (tk.Label, ttk.Label, tk.Checkbutton, ttk.Checkbutton)


def help_mark(parent, text, on=None):
    """
    A note for a setting, shown while the pointer rests on its title (the pointer
    becomes a question mark there). Returns an empty placeholder for the caller to
    pack or grid where the old ? went; once it's placed, the note goes on the row's
    title: the first label or tick box in that stretch of the row (back to the
    previous note), or in the same grid row. on names the title outright.
    If no title can be found, a ? is shown as before, so no note is ever lost.
    """
    anchor = tk.Frame(parent, width=1, height=1, bd=0, highlightthickness=0)
    anchor._note_text = text
    anchor._note_target = None
    anchor._pending = None
    if on is not None:
        _note_on(anchor, on)
    else:
        anchor._pending = anchor.after_idle(lambda: _place_note(anchor))
        anchor.bind("<Destroy>", lambda e: _cancel_note(anchor), add="+")
    return anchor


def _cancel_note(anchor):
    """
    A note still looking for its title when its row is torn down: the pending look is
    cancelled. Left to fire, Tk would run a command whose name a widget built since may
    have been given again (tkinter names them by id), with no event to pass it.
    """
    pending, anchor._pending = getattr(anchor, "_pending", None), None
    if pending:
        try:
            anchor.after_cancel(pending)
        except tk.TclError:
            pass


def _is_title(w):
    try:
        return isinstance(w, NOTE_TITLES) and str(w.cget("text")).strip() != "" \
            and not getattr(w, "_has_note", False)
    except tk.TclError:
        return False


def _note_title(anchor):
    """
    The title a placed note belongs to, or None. Looks in the note's own row first; if
    the note sits in a cell of its own (a box holding just the control), it looks
    beside that cell instead, up to two levels out.
    """
    spot = anchor
    for _ in range(3):
        title = _title_before(spot)
        if title is not None:
            return title
        spot = spot.master
        if spot is None or not spot.winfo_manager() or spot.master is None:
            return None
    return None


def _title_before(anchor):
    """The first title before this widget: in its grid row, or in its stretch of a packed row."""
    parent = anchor.master
    if anchor.winfo_manager() == "grid":
        info = anchor.grid_info()
        row, col = int(info["row"]), int(info["column"])
        before = [w for w in parent.grid_slaves(row=row)
                  if w is not anchor and int(w.grid_info()["column"]) < col]
        before.sort(key=lambda w: int(w.grid_info()["column"]))
        return next((w for w in before if _is_title(w)), None)
    if anchor.winfo_manager() != "pack":
        return None
    stretch = []
    for w in reversed(parent.winfo_children()[:parent.winfo_children().index(anchor)]):
        if hasattr(w, "_note_text"):   # the previous note's place: its title is behind it
            break
        stretch.append(w)
    return next((w for w in reversed(stretch) if _is_title(w)), None)


def _note_on(anchor, title):
    anchor._note_target = title
    Tooltip(title, anchor._note_text, click=False)
    try:
        title.config(cursor="question_arrow")
    except tk.TclError:
        pass


def _place_note(anchor):
    anchor._pending = None
    try:
        if not anchor.winfo_exists() or anchor._note_target is not None:
            return
        title = _note_title(anchor) if anchor.winfo_manager() else None
    except tk.TclError:
        return
    if title is not None:
        _note_on(anchor, title)
        return
    if not anchor.winfo_manager():   # not placed yet: look again once it is, for a while
        anchor._tries = getattr(anchor, "_tries", 0) + 1
        if anchor._tries < 50:
            anchor._pending = anchor.after(200, lambda: _place_note(anchor))
        return
    mark = tk.Label(anchor, text="?", font=("Segoe UI", 8, "bold"), fg=PALETTE["help_mark_fg"],
                    bg=PALETTE["help_mark_bg"], width=2, cursor="question_arrow")
    mark.pack()
    _note_on(anchor, mark)


def section(parent, title, help_text=None, row=None, title_fg=None):
    """
    A Settings section: a solid header bar with its title (and optional ?), black in
    dark and grey in light, over a thin-edged box. Returns the box to build the
    section's controls in. Stacked with grid in column 0 of parent, one under
    another, or at row if given.
    """
    edge = PALETTE["section_edge"]
    outer = tk.Frame(parent, bd=0, highlightthickness=1, highlightbackground=edge, highlightcolor=edge)
    head_bg = PALETTE.get("head_bg") or outer.cget("bg")
    head = tk.Frame(outer, bg=head_bg)
    head.pack(fill="x")
    tk.Label(head, text=title, font=HEADING_FONT, fg=title_fg or PALETTE.get("head_fg") or PALETTE["section_fg"],
             bg=head_bg).pack(side="left", padx=(10, 0), pady=4)
    if help_text:
        help_mark(head, help_text).pack(side="left", padx=(6, 0))
    box = tk.Frame(outer, padx=14, pady=10)
    box.pack(fill="both", expand=True)
    if row is None:
        row = parent.grid_size()[1]
    outer.grid(row=row, column=0, sticky="ew", pady=(0, 14))
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
    One settings page: a button's (Settings > Buttons: its Sources and Playlist pages share
    one of these), or a JRiver Playlists page (Windows (Main), device_id None, or a device's).
    Holds its values (env), its controls (vars) and how it saves, so the same builder fills
    every page. columns: the Review Mode and Playing Now columns, on a standard button's page.
    """

    def __init__(self, kind, device_id, env, vars_, save):
        self.kind, self.device_id, self.env, self.vars, self.save = kind, device_id, env, vars_, save
        self.loading, self.body, self.resync = False, None, lambda: None
        self.button, self.columns = None, device_id is None

    def values(self):
        """The page's settings as .env strings: only the controls it has (a button's page has one kind's)."""
        if self.kind == "saved":   # the Saved Playlists page keeps its own table
            return self.collect()
        v = self.vars
        out = {}
        for group in ("SIMILAR_SOURCES", "SIMILAR_TRACK_SOURCES", "TOP_TRACK_SOURCES"):
            if group in v:
                out[group] = ",".join(code for code, tick in v[group].items() if tick.get())
        for key in ("SIMILAR_MIN_AGREEMENT", "SIMILAR_TRACK_MIN_AGREEMENT"):
            if key in v:
                out[key] = "1" if v[key].get() == "Off" else v[key].get()
        for key in ("LISTENBRAINZ_ALGORITHM", "LISTENBRAINZ_TRACK_ALGORITHM"):
            if key in v:
                out[key] = v[key].get()
        for group in engine.MODERATOR_GROUPS:
            key = f"AI_MODERATOR_{group.upper()}"
            if key in v:
                out[key] = v[key].get().lower()
        for key in PLAYLIST_TEXT_KEYS:
            if key in v:
                out[key] = v[key].get().strip()
        if "SIMILAR_ARTIST_TRACK_LIMIT" in v:
            out["SIMILAR_ARTIST_TRACK_LIMIT"] = "1" if v["SIMILAR_ARTIST_TRACK_LIMIT"].get() else "0"
        for group, (on, using, rounds, _) in getattr(self, "drift", {}).items():
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
            if f"{name}_FROM" in v:
                out[f"{name}_FROM"] = v[f"{name}_FROM"].get()
            if f"{name}_MODERATOR" in v:
                out[f"{name}_MODERATOR"] = option_code(DRIFT_MODERATOR_OPTIONS, v[f"{name}_MODERATOR"].get())
        if "AI_MODERATOR_VIBE" in v:
            out["AI_MODERATOR_VIBE"] = v["AI_MODERATOR_VIBE"].get().lower()
        for g in ("ARTISTS", "TRACKS"):
            if f"INNER_CIRCLE_{g}" in v:
                out[f"INNER_CIRCLE_{g}"] = "1" if v[f"INNER_CIRCLE_{g}"].get() else "0"
                out[f"INNER_CIRCLE_{g}_SIZE"] = v[f"INNER_CIRCLE_{g}_SIZE"].get()
                out[f"INNER_CIRCLE_{g}_AGREE"] = v[f"INNER_CIRCLE_{g}_AGREE"].get()
        if "FALLBACK_SPOKEN" in v:
            out["FALLBACK_SPOKEN"] = "1" if v["FALLBACK_SPOKEN"].get() else "0"
        for group in engine.PLAYED_GROUPS:
            g = group.upper()
            if f"SKIP_PLAYED_{g}" not in v:   # another kind's section: not on this page
                continue
            out[f"SKIP_PLAYED_{g}"] = "1" if v[f"SKIP_PLAYED_{g}"].get() else "0"
            out[f"SKIP_LONG_CLOSERS_{g}"] = "1" if v[f"SKIP_LONG_CLOSERS_{g}"].get() else "0"
            if f"IF_ALL_ELSE_FAILS_{g}" in v:
                out[f"IF_ALL_ELSE_FAILS_{g}"] = "1" if v[f"IF_ALL_ELSE_FAILS_{g}"].get() else "0"
                out[f"IF_ALL_ELSE_FAILS_{g}_MODE"] = option_code(FALLBACK_MODE_OPTIONS,
                                                                 v[f"IF_ALL_ELSE_FAILS_{g}_MODE"].get())
                for part in ("PATH", "PLAYLIST", "PLAYLIST_NAME"):
                    out[f"IF_ALL_ELSE_FAILS_{g}_{part}"] = v[f"IF_ALL_ELSE_FAILS_{g}_{part}"].get().strip()
            out[f"LONG_CLOSER_MINUTES_{g}"] = v[f"LONG_CLOSER_MINUTES_{g}"].get().strip()
            out[f"NONSTOP_{g}"] = "1" if v[f"NONSTOP_{g}"].get() else "0"
            out[f"NONSTOP_{g}_RESEED"] = option_code(NONSTOP_RESEED_OPTIONS, v[f"NONSTOP_{g}_RESEED"].get())
            if f"NONSTOP_{g}_MODE" in v:
                out[f"NONSTOP_{g}_MODE"] = v[f"NONSTOP_{g}_MODE"].get()
            out[f"RUN_AFTER_{g}"] = "1" if v[f"RUN_AFTER_{g}"].get() else "0"
            out[f"RUN_AFTER_{g}_PATH"] = v[f"RUN_AFTER_{g}_PATH"].get().strip()
            if f"NONSTOP_{g}_USING" in v:
                out[f"NONSTOP_{g}_USING"] = option_code(NONSTOP_USING_OPTIONS, v[f"NONSTOP_{g}_USING"].get())
        if "NONSTOP_VIBE_WITH" in v:
            out["NONSTOP_VIBE_WITH"] = option_code(NONSTOP_WITH_OPTIONS, v["NONSTOP_VIBE_WITH"].get())
        for group in engine.DEEP_CUT_GROUPS:
            g = group.upper()
            if f"DEEP_CUTS_{g}_SHARE" in v:
                out[f"DEEP_CUTS_{g}_SHARE"] = v[f"DEEP_CUTS_{g}_SHARE"].get().strip() or "10"
            if f"DEEP_CUTS_{g}" in v:
                out[f"DEEP_CUTS_{g}"] = option_code(DEVICE_DEEP_CUTS, v[f"DEEP_CUTS_{g}"].get())
        if "NONSTOP_TOP_REST" in v:
            out["NONSTOP_TOP_REST"] = "1" if v["NONSTOP_TOP_REST"].get() else "0"
            out["NONSTOP_TOP_REST_COUNT"] = v["NONSTOP_TOP_REST_COUNT"].get().strip().lower()
        return out


# Playlist settings saved as typed (spin boxes and dropdowns)
PLAYLIST_TEXT_KEYS = ["SIMILAR_ARTIST_TRACK_COUNT", "SIMILAR_ARTIST_LIMIT", "TRACKS_PER_ARTIST_POOL",
                      "TRACKS_PER_ARTIST_PICK", "SIMILAR_TRACK_COUNT", "SIMILAR_TRACK_PER_ARTIST",
                      "SIMILAR_TRACK_ORDER", "SIMILAR_TRACK_VARIETY", "TOP_TRACKS_COUNT", "TOP_TRACKS_ORDER",
                      "VIBE_TRACK_COUNT", "VIBE_PER_ARTIST",
                      "SKIP_PLAYED_ARTISTS_DAYS", "SKIP_PLAYED_TRACKS_DAYS",
                      "SKIP_PLAYED_TOP_DAYS", "SKIP_PLAYED_VIBE_DAYS"]

# Drift using: (saved value, label shown). AI is for vibe playlists only, and never the default.
DRIFT_USING_OPTIONS = [("artists", N_("Similar artists")), ("tracks", N_("Similar tracks")), ("ai", "AI")]
# AI Playlist's Drift choices say plainly which ones use the AI
VIBE_DRIFT_USING_OPTIONS = [("artists", N_("Similar artists (no AI)")), ("tracks", N_("Similar tracks (no AI)")),
                            ("ai", N_("AI (uses credits)"))]
DRIFT_SOURCE_MODES = [("same", N_("Same as the Sources")), ("custom", N_("Custom Sources"))]
# If All Else Fails: what happens when a build finds nothing at all
FALLBACK_MODE_OPTIONS = [("shuffle", N_("Shuffle Genre")), ("file", N_("Run File")), ("playlist", N_("Play Playlist"))]
FALLBACK_HELP = (N_("When a build finds nothing at all. Shuffle Genre plays songs from your library in the seed "
                 "track's genre (or the artist's most common genre), at a similar tempo when the seed has a BPM "
                 "tag, leaving out the seed artist and anything played recently. Run File starts a file of your "
                 "own, such as a .bat, and Run After Building is skipped for that build. Play Playlist plays one "
                 "of your JRiver playlists or smartlists, as JRiver gives it. Unticked, the build ends with a "
                 "message."))
SPOKEN_HELP = (N_("For voice commands and keyboard shortcuts that play in a zone: before the music starts, "
               "Windows' own voice says why in that zone. The message is a short WAV file played in JRiver, so "
               "it shows in Playing Now. One setting for every playlist type. Off to start."))
NO_PLAYLIST = N_("No playlist chosen")


def choose_playlist(parent, on_pick):
    """A small window to pick a JRiver playlist or smartlist: most used first, then the rest, with a search."""
    import playmix
    try:
        playlists = saved_playlists.scan()
    except Exception:
        playlists = None
    win = tk.Toplevel(parent)
    win.title(t("Choose a Playlist"))
    win.transient(parent.winfo_toplevel())
    win.resizable(False, False)
    search = ttk.Entry(win, width=48)
    search.pack(fill="x", padx=10, pady=(10, 6))
    lb = tk.Listbox(win, height=14, width=52, activestyle="none", exportselection=False, font=("Segoe UI", 9))
    lb.pack(fill="both", expand=True, padx=10)
    items = []

    def fill(*_):
        lb.delete(0, "end")
        items.clear()
        if playlists is None:
            lb.insert("end", t("JRiver isn't answering, so there are no playlists to show."))
            items.append(None)
            return
        used, rest = playmix.picker_order(playlists, search.get())
        for p, _count in used:
            lb.insert("end", p["Name"])
            items.append(p)
        if used and rest:
            lb.insert("end", "")
            items.append(None)
        for p in rest:
            lb.insert("end", p["Name"] + (f"   ({p['Folder']})" if p.get("Folder") not in (None, "", saved_playlists.ROOT)
                                          else ""))
            items.append(p)
        if not items:
            lb.insert("end", t("No playlists match"))
            items.append(None)

    def pick(_e=None):
        sel = lb.curselection()
        item = items[sel[0]] if sel else next((x for x in items if x is not None), None)
        if item is None:
            return
        on_pick(item)
        win.destroy()

    buttons = tk.Frame(win)
    buttons.pack(fill="x", padx=10, pady=10)
    ttk.Button(buttons, text=t("Cancel"), command=win.destroy).pack(side="right")
    ttk.Button(buttons, text=t("Choose"), command=pick).pack(side="right", padx=(0, 6))
    search.bind("<KeyRelease>", lambda e: fill() if e.keysym != "Return" else None)
    search.bind("<Return>", pick)
    lb.bind("<Double-Button-1>", pick)
    win.bind("<Escape>", lambda e: win.destroy())
    fill()
    search.focus_set()
    return win
# Drift: Off, or how each round picks its seeds
DRIFT_MODE_OPTIONS = [("off", N_("Off")), ("close", N_("Keep It Tight")), ("spread", N_("Spread"))]
DRIFT_MODE_HELP = (N_("When a playlist comes up short, Drift searches again using what's already been found.\n"
                   "Keep It Tight: seeds only from the first round's tracks, so nothing strays far from your "
                   "seed. If the first round was short, Drift may run out of seeds and finish short; the "
                   "console says when.\n"
                   "Spread: seeds from across the whole playlist, including what Drift has added, so it "
                   "can travel further while branching in several directions."))
# Moderator on Drift tracks, for Similar Artists and Similar Tracks
DRIFT_MODERATOR_OPTIONS = [("same", N_("Same as build")), ("off", N_("Off")), ("relaxed", N_("Relaxed")),
                           ("balanced", N_("Balanced")), ("strict", N_("Strict"))]
DRIFT_ARTIST_SOURCE_NAMES = [s for s in SOURCE_NAMES if s[0] != "ai"]   # Drift from the sources never uses the AI
DRIFT_SOURCES_HELP = (N_("Same as the Sources uses the sources ticked in this config. Custom "
                      "Sources lets the top-up rounds use different ones, for example steadier sources first "
                      "and more adventurous ones to fill the gaps."))
DRIFT_SAME_WARNING = (N_("Same sources keep Drift's picks closest to the seed. Custom Sources give Drift a "
                      "different route if the playlist finds nothing and provide a back-up route to build "
                      "out the playlist."))


def drift_using_options(group):
    """The Drift using choices for a Play option (AI only for AI Playlist)."""
    return VIBE_DRIFT_USING_OPTIONS if group == "vibe" else DRIFT_USING_OPTIONS[:2]

# The Play options, as the tabs inside Sources and Playlist

# Deep Cuts: the switch on a button's Playlist page
DEVICE_DEEP_CUTS = [("off", N_("Off")), ("spaced", N_("Spaced")), ("shuffled", N_("Shuffled"))]

# Non-stop dropdowns: (saved value, label shown)
NONSTOP_USING_OPTIONS = [("artists", N_("Similar artists")), ("tracks", N_("Similar tracks"))]
NONSTOP_RESEED_OPTIONS = [("last", N_("Last track")), ("second", N_("2nd track"))]
SAVED_RESEED_OPTIONS = NONSTOP_RESEED_OPTIONS + [("whole", "Whole playlist")]   # JRiver Playlists rows only
NONSTOP_MODE_OPTIONS = [("off", N_("Off")), ("tight", N_("Keep It Tight")), ("journey", N_("Wander"))]
NONSTOP_MODE_HELP = (N_("When the last track of a playlist 24bit7 built starts, more are added so the music keeps going.\n"
                     "Keep It Tight: each top-up reseeds from a track of the original playlist, a different one "
                     "each time, so the evening stays close to where it started. When every track has been used "
                     "as a seed, it carries on as Wander, and the console says so.\n"
                     "Wander: each top-up reseeds from where the music has got to (Reseed "
                     "from), so the evening travels."))
NONSTOP_WITH_OPTIONS = [("vibe", N_("More from the AI")), ("artists", N_("Similar artists")), ("tracks", N_("Similar tracks"))]
# Saved Playlists dropdowns
SAVED_NONSTOP_OPTIONS = [("no", N_("No")), ("artists", N_("Similar artists")), ("tracks", N_("Similar tracks"))]
SAVED_SKIP_OPTIONS = [("0", N_("Off")), ("1", N_("1 day")), ("2", N_("2 days")), ("3", N_("3 days")), ("7", N_("7 days")),
                      ("14", N_("14 days")), ("30", N_("30 days"))]
CACHE_KEEP_OPTIONS = [("month", N_("1 Month")), ("year", N_("1 Year")), ("permanent", N_("Permanent"))]
CREDITS_SCOPE_OPTIONS = [("current", N_("Album/Current Track")), ("all", N_("Album/All Tracks"))]
CREDITS_FIRST_OPTIONS = [("track", N_("Tracks")), ("album", N_("Album"))]
CLEAR_CACHE_OPTIONS = [("month", N_("Older Than 1 Month")), ("year", N_("Older Than 1 Year")), ("all", N_("Clear All"))]
ALL_FOLDERS = N_("All folders")   # the JRiver Playlists folder filter's first choice


def table_colours():
    """(heading, odd row, even row) backgrounds for the Saved Playlists table, light or dark."""
    import tabs
    if tabs.THEME == "dark":
        return "#000000", "#1f2023", "#2a2c30"
    return "#bfc3c9", "#ffffff", "#f3f4f6"


# The ? beside each Number of tracks
LIMIT_HELP = N_("Ticked, the playlist stops at this many tracks, picked at random from everything found. Unticked, every track found goes in: Number of artists times Tracks per artist selection, plus the seed artist's, so the playlist can run long, and Drift doesn't run as there's no target to fall short of. Non-stop top-ups always keep to this number.\nTo switch the random pick off altogether, set Tracks per artist selection to the same as Number of artist's top tracks (say 5 of 5) and untick this.")
TARGET_HELP = N_('This is the target number of tracks. The playlist may come out shorter, depending on how many matches are in your library. If your playlists are often too short, tick Drift to fill them out.')
TOP_TARGET_HELP = N_("This is the target number of tracks. The playlist may come out shorter, depending on how many of the artist's top tracks are in your library.")


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
    box = getattr(p, box_name, None)
    if box is None or sources_key not in p.vars:   # another kind's sources: not on this page
        return
    ticked = sum(1 for v in p.vars[sources_key].values() if v.get())
    if ticked < 2:
        box.config(state="disabled")
        return
    options = [N_("Off")] + [str(n) for n in range(2, min(ticked, most) + 1)]
    box.config(values=options, state="readonly")
    if p.vars[agree_key].get() not in options:
        p.vars[agree_key].set(options[-1])


def sync_drift(p):
    """Drift using and Rounds grey out while their Drift tick is off."""
    for on, _, _, boxes in p.drift.values():
        for cb in boxes:
            cb.config(state="readonly" if on.get() else "disabled")
    sync_drift_sources(p)
    # AI Playlist's moderator: only for Drift from the sources, and only with the AI set up
    mod_cb = getattr(p, "vibe_mod_cb", None)
    if mod_cb is not None and "vibe" in p.drift:
        on, using, _, _ = p.drift["vibe"]
        ok = (on.get() and option_code(drift_using_options("vibe"), using.get()) != "ai"
              and engine.ai_configured())
        mod_cb.config(state="readonly" if ok else "disabled")


def sync_drift_sources(p):
    """Drift sources: hidden when Drift uses the AI; the ticks only with Custom Sources, following Drift using."""
    for group, (mode, mode_row, panel, frames) in getattr(p, "drift_src", {}).items():
        _, using, _, _ = p.drift[group]
        code = option_code(drift_using_options(group), using.get())
        warn = getattr(p, "drift_warn", {}).get(group)
        if code == "ai":
            mode_row.grid_remove()
            panel.grid_remove()
            if warn is not None:
                warn.grid_remove()
            continue
        mode_row.grid()
        if option_code(DRIFT_SOURCE_MODES, mode.get()) != "custom":
            panel.grid_remove()
            if warn is not None:
                warn.grid()
            continue
        if warn is not None:
            warn.grid_remove()
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
        reseed_cb, mode = getattr(p, "nonstop_reseed", {}).get(g), p.vars.get(f"NONSTOP_{g}_MODE")
        if reseed_cb is not None and on and mode is not None and mode.get() == "tight":
            reseed_cb.state(["disabled"])   # Keep It Tight reseeds from the original playlist instead
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


TEMPLATE_NOTES = {   # what each template is, for the Add a Playlist window
    "artists": N_("Artist Matching as 24bit7 ships it: artists like the seed's, a pick of each one's top tracks."),
    "tracks": N_("Track Matching as 24bit7 ships it: songs like the seed track, suggested song by song."),
    "top": N_("Artist's Top Tracks as 24bit7 ships it: the artist's most popular tracks that you own."),
    "vibe": N_("AI Playlist as 24bit7 ships it: describe a mood and the AI picks from your library. Uses AI credits."),
    "headliner": N_("The artist's top tracks, two at a time, with one track from a close similar artist between them."),
    "inner_circle": N_("The seed's three closest artists, then only the artists their own lists agree on. Tight, and "
                       "sometimes short."),
    "top10_first": N_("The artist's ten most popular tracks that you own, best first."),
    "top10_last": N_("The artist's ten most popular tracks that you own, least popular first."),
}


class PickList(tk.Frame):
    """
    A list of names to pick one from, drawn as rows (tabs.PickRow) on the field colour, so it reads
    as a list against the window: the chosen row has a rounded outline in the accent colour and no
    fill, the same as the list under Settings > Playlists (a Tk listbox can only fill a row). Keeps
    the listbox calls its callers use: get(0, "end"), curselection, selection_set, selection_clear,
    and <<ListboxSelect>> after a pick. Up and Down move the pick.
    """

    def __init__(self, parent, items, bg, fg, colours=None, on_double=None, indents=None):
        super().__init__(parent, bg=bg, bd=1, relief="solid", takefocus=1, highlightthickness=0)
        self._items = list(items)
        self._index = 0 if self._items else None
        self._rows = []
        self._bg = bg
        colours, indents = colours or {}, indents or {}
        for i, text in enumerate(self._items):
            row = PickRow(self, text, fg=colours.get(i) or fg, bg=bg, chosen=i == self._index, indent=indents.get(i, 0))
            row.configure(cursor="hand2")
            row.pack(fill="x", padx=3, pady=1)
            row.bind("<Button-1>", lambda e, k=i: (self.focus_set(), self.pick(k)))
            if on_double is not None:
                row.bind("<Double-Button-1>", lambda e, k=i: (self.pick(k), on_double()))
            self._rows.append(row)
        self.bind("<Up>", lambda e: self.step(-1))
        self.bind("<Down>", lambda e: self.step(1))
        self._paint()

    def _paint(self):
        for i, row in enumerate(self._rows):
            row.set_chosen(i == self._index)

    def step(self, by):
        """Moves the pick up (-1) or down (1), from the keyboard."""
        if self._items:
            self.pick(min(len(self._items) - 1, max(0, (self._index if self._index is not None else -1) + by)))
        return "break"

    def pick(self, i):
        self._index = i if 0 <= i < len(self._items) else None
        self._paint()
        self.event_generate("<<ListboxSelect>>")

    def get(self, first, last=None):
        if last is None:
            return self._items[first]
        return tuple(self._items[first:(len(self._items) if last == "end" else last + 1)])

    def curselection(self):
        return (self._index,) if self._index is not None else ()

    def selection_set(self, i):
        self._index = i if 0 <= i < len(self._items) else None
        self._paint()

    def selection_clear(self, *_):
        self._index = None
        self._paint()


class AddPlaylistPrompt(PromptWindow):
    """
    The Add a Playlist window: three tabs. From Existing lists every playlist: one that's off the
    Play tab, Add ticks back; one that's on it, Create Copy copies (Name 2, right after it). From
    Template lists the four kinds as shipped, Artist + Guests and Consensus; New makes a blank slate
    and opens its page with the name box ready. The answer in .result is ("existing", id),
    ("copy", id), ("template", key) or ("new", None); None for Cancel.
    """

    ok_text = N_("Add")

    def __init__(self, parent, device=None):
        """device=(device name, phrase label): the same window giving a device its own playlist for a phrase,
        From Existing (any playlist, a copy) and From Template only, no New (2 Nov 2026)."""
        self._device = device
        self._existing = [b for b in buttons.load() if not b.get("device")]   # a device's own aren't buttons
        self._templates = [(kind, t(label), t(TEMPLATE_NOTES[kind])) for kind, label in buttons.KIND_LABELS.items()]
        self._templates += [(r["key"], t(r["name"]), t(TEMPLATE_NOTES[r["key"]])) for r in buttons.READY_MADE]
        self._tab = "existing"
        title = t("Add a Playlist") if device is None else t("Give {device} its own \"{phrase}\" playlist",
                                                              device=device[0], phrase=device[1])
        super().__init__(parent, title)
        self._describe()   # the OK button exists now: Add or Create Copy for the first pick
        # Keys from the moment the window opens: Tab and Shift+Tab walk the tabs, Up and Down the current list
        self.bind("<Tab>", lambda e: self._tab_by(1))
        self.bind("<Shift-Tab>", lambda e: self._tab_by(-1))
        try:
            self.bind("<ISO_Left_Tab>", lambda e: self._tab_by(-1))   # Shift+Tab as some X servers name it
        except tk.TclError:
            pass
        self.bind("<Up>", lambda e: self._list_step(-1))
        self.bind("<Down>", lambda e: self._list_step(1))

    TAB_ORDER = ("existing", "template", "new")

    def _tabs_here(self):
        return self.TAB_ORDER[:2] if self._device is not None else self.TAB_ORDER

    def _tab_by(self, by):
        order = self._tabs_here()
        self._pick_tab(order[(order.index(self._tab) + by) % len(order)])
        return "break"

    def _list_step(self, by):
        lb = {"existing": self.existing_list, "template": self.template_list}.get(self._tab)
        if lb is not None:
            lb.step(by)
        return "break"

    def _body(self, inner, bg, fg):
        px = self._px
        self._tabs = {}
        row = tk.Frame(inner, bg=bg)
        row.pack(anchor="w")
        for key, label in (("existing", N_("From Existing")), ("template", N_("From Template")), ("new", N_("New"))):
            if key not in self._tabs_here():
                continue
            cell = tk.Frame(row, bg=bg)
            cell.pack(side="left", padx=(0, px(18)))
            tab = tk.Label(cell, text=t(label), font=("Segoe UI", 10, "bold"), bg=bg, cursor="hand2", pady=px(4))
            tab.pack()
            bar = tk.Frame(cell, height=px(2), bg=bg)
            bar.pack(fill="x")
            tab.bind("<Button-1>", lambda e, k=key: self._pick_tab(k))
            self._tabs[key] = (tab, bar)
        tk.Frame(inner, bg=PALETTE["line"], height=px(1)).pack(fill="x", pady=(0, px(12)))
        self._pages = {}
        rows = max(len(self._existing), len(self._templates))   # tall enough for the longer list and its note
        self._page_holder = tk.Frame(inner, bg=bg, width=px(420), height=max(px(190), rows * px(29) + px(80)))
        self._page_holder.pack(anchor="w", fill="x")
        self._page_holder.pack_propagate(False)
        list_bg = PALETTE.get("field_bg") or bg   # the text boxes' colour: the list stands apart from the window
        # From Existing
        page = tk.Frame(self._page_holder, bg=bg)
        self._pages["existing"] = page
        self.existing_list = self._listbox(page, list_bg, fg, [b["name"] for b in self._existing],
                                           {i: PALETTE["ai_purple"] for i, b in enumerate(self._existing)
                                            if b["kind"] == "vibe"},
                                           indents={i: px(22) for i, b in enumerate(self._existing) if b.get("parent")})
        self.existing_list.bind("<<ListboxSelect>>", lambda e: self._describe())
        self.existing_note = tk.Label(page, text="", font=HELP_FONT, bg=bg, fg=PALETTE["help_fg"], anchor="w",
                                      justify="left", wraplength=px(400))
        self.existing_note.pack(anchor="w", pady=(px(8), 0))
        # From Template
        page = tk.Frame(self._page_holder, bg=bg)
        self._pages["template"] = page
        self.template_list = self._listbox(page, list_bg, fg, [label for _k, label, _n in self._templates],
                                           {i: PALETTE["ai_purple"] for i, (k, _l, _n) in enumerate(self._templates)
                                            if k == "vibe"})
        self.template_list.bind("<<ListboxSelect>>", lambda e: self._describe())
        self.template_note = tk.Label(page, text="", font=HELP_FONT, bg=bg, fg=PALETTE["help_fg"], anchor="w",
                                      justify="left", wraplength=px(400))
        self.template_note.pack(anchor="w", pady=(px(8), 0))
        # New
        page = tk.Frame(self._page_holder, bg=bg)
        self._pages["new"] = page
        tk.Label(page, text=t("A blank slate: a playlist with no config yet. Its page opens under Settings > Playlists "
                              "with the name box ready to type in, and + Add a Config says what it builds."),
                 font=("Segoe UI", 10), bg=bg, fg=fg, anchor="w", justify="left",
                 wraplength=px(400)).pack(anchor="w")
        self._pick_tab(self._tab)

    def _listbox(self, page, bg, fg, items, colours=None, indents=None):
        lb = PickList(page, items, bg, fg, colours=colours, on_double=self.ok, indents=indents)
        lb.pack(fill="x")
        return lb

    def _pick_tab(self, key):
        self._tab = key
        for k, (tab, bar) in self._tabs.items():
            on = k == key
            tab.config(fg=PALETTE["button_fg"] if on else PALETTE["help_fg"])
            bar.config(bg=PALETTE["button_fg"] if on else self._colours[0])
        for k, page in self._pages.items():
            page.pack_forget()
        self._pages[key].pack(fill="both", expand=True)
        if hasattr(self, "ok_button") and key != "existing":   # From Existing's button follows the pick (_describe)
            self.set_ok_text(t("Create") if key == "new" else t("Use the Template") if self._device is not None else t("Add"))
        self._describe()
        if hasattr(self, "ok_button"):
            self._focus_first()   # the keyboard follows the tab: a list's own Up and Down bind to the list that has focus

    def _chosen(self, lb, items):
        sel = lb.curselection() if lb is not None else ()
        i = sel[0] if sel else 0
        return items[i] if 0 <= i < len(items) else None

    def _describe(self):
        if self._tab == "existing":
            b = self._chosen(self.existing_list, self._existing)
            if b is not None:
                parent = next((p for p in self._existing if p["id"] == b.get("parent")), None)
                if self._device is not None:
                    words = t("{name}: {what}. A copy of it becomes {device}'s own for \"{phrase}\".", name=b["name"],
                              what=buttons.describe(b), device=self._device[0], phrase=self._device[1])
                elif parent is not None:
                    words = t("{name}: {what}. In the menu of {parent} already; Create Copy makes {copy} beside it.",
                              name=b["name"], what=buttons.describe(b), parent=parent["name"],
                              copy=buttons.unique_name(b["name"]))
                else:
                    words = t("{name}: {what}. On the Play tab already; Create Copy makes {copy} right after it.",
                              name=b["name"], what=buttons.describe(b), copy=buttons.unique_name(b["name"]))
                self.existing_note.config(text=words)
                wanted = t("Use a Copy") if self._device is not None else t("Create Copy")
                if hasattr(self, "ok_button") and self.ok_button.cget("text") != wanted:
                    self.set_ok_text(wanted)
        elif self._tab == "template":
            chosen = self._chosen(self.template_list, self._templates)
            if chosen is not None:
                self.template_note.config(text=chosen[2])

    def _focus_first(self):
        lb = {"existing": self.existing_list, "template": self.template_list}.get(self._tab)
        (lb or self).focus_set()

    def ok(self):
        if self._tab == "existing":
            b = self._chosen(self.existing_list, self._existing)
            if b is None:
                return
            self.result = ("copy", b["id"])
        elif self._tab == "template":
            chosen = self._chosen(self.template_list, self._templates)
            if chosen is None:
                return
            self.result = ("template", chosen[0])
        else:
            self.result = ("new", None)
        self.destroy()


def ask_new_button(parent):
    """Opens the Add a Playlist window and waits: ("existing", id), ("copy", id), ("template", key), ("new", None), or None."""
    win = AddPlaylistPrompt(parent)
    try:
        win.grab_set()
    except tk.TclError:
        pass
    win.wait_window()
    return win.result


class SettingsTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.env = read_env()
        self.vars = {}
        self._source_boxes = []   # (tick, code, label, purpose) for the "(no key yet)" marks
        self._loading = True   # suppress auto-save while building controls
        self._button_page = None   # the ProfilePage of the button open under Settings > Buttons
        self.hotkey_vars, self.hotkey_notes = {}, {}   # every shortcut box: Other's, and the open button's
        self._hotkey_capturing, self._hotkey_held = None, set()

        nb = TabbedPane(self, font=("Segoe UI", 10, "bold"), pad=(16, 6))
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._pane = nb
        self._build_buttons(nb)
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
        # Each button's sources and playlist settings are saved by its own page (_save_button_page)
        updates = {}
        updates["CACHE_KEEP"] = option_code(CACHE_KEEP_OPTIONS, self.vars["CACHE_KEEP"].get())
        updates["CACHE_DAYS"] = None   # replaced by Keep Cache For
        updates["CREDITS_SCOPE"] = option_code(CREDITS_SCOPE_OPTIONS, self.vars["CREDITS_SCOPE"].get())
        updates["CREDITS_FIRST"] = option_code(CREDITS_FIRST_OPTIONS, self.vars["CREDITS_FIRST"].get())
        for key in ["JRIVER_HOST", "YOUTUBE_PLAYLIST_LENGTH"] + KEY_FIELDS:
            updates[key] = self.vars[key].get().strip()
        updates["AI_PROVIDER"] = self._ai_provider()
        for group in ("DIGITAL_STORES", "REFERENCE_SITES"):
            updates[group] = ",".join(code for code, v in self.vars[group].items() if v.get())
        updates["DIGITAL_STORE"] = None   # pre-1.1.0 single-store key, superseded
        if "DISCOVER_LABEL" in self.vars:
            updates["DISCOVER_LABEL"] = "1" if self.vars["DISCOVER_LABEL"].get() else "0"
        updates["LISTEN_SITES"] = ",".join(code for code, v in self.vars["LISTEN_SITES"].items() if v.get())
        for group in ("PLAYLIST_SITES", "EXTRA_OUTPUTS"):
            if group in self.vars:
                updates[group] = ",".join(code for code, v in self.vars[group].items() if v.get())
        if "TIDAL_OPEN" in self.vars:
            updates["TIDAL_OPEN"] = "web" if self.vars["TIDAL_OPEN"].get() == "Tidal Web" else "app"
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
        updates["ACCENT_COLOUR"] = self.vars["ACCENT_COLOUR"].get()
        if "UI_LANGUAGE" in self.vars:
            codes = {name: code for code, name in i18n.LANGUAGES}
            updates["UI_LANGUAGE"] = codes.get(self.vars["UI_LANGUAGE"].get(), "en")
        updates["SIMILAR_REQUIRE_AGREEMENT"] = None   # old on/off key, superseded
        updates["SIMILAR_TRACK_TOPUP"] = None   # replaced by Drift in 1.4.0
        for key in ("START_IN_TRAY", "CLOSE_TO_TRAY", "PREFER_OFFICIAL_VIDEOS", "WINDOWS_TITLE_BAR"):
            updates[key] = "1" if self.vars[key].get() else "0"
        return updates

    def _on_title_bar_toggled(self):
        """Saves the title bar choice, then offers to restart so it takes effect."""
        self._save()
        ask = (t("Restart 24bit7 now to use Windows' title bar?") if self.vars["WINDOWS_TITLE_BAR"].get()
               else t("Restart 24bit7 now to use 24bit7's own title bar?"))
        if messagebox.askyesno(t("Title bar"), ask, parent=self):
            self.winfo_toplevel().event_generate("<<Restart24bit7>>")

    def _on_theme_changed(self, *_):
        """Saves the theme, then offers to restart so it takes effect."""
        self._save()
        ask = (t("Restart 24bit7 now to switch to the dark theme?") if self.vars["THEME"].get() == "Dark"
               else t("Restart 24bit7 now to switch to the light theme?"))
        if messagebox.askyesno(t("Theme"), ask, parent=self):
            self.winfo_toplevel().event_generate("<<Restart24bit7>>")

    def _choose_accent(self):
        from tkinter import colorchooser
        current = tabs.tidy_accent(self.vars["ACCENT_COLOUR"].get())
        _rgb, picked = colorchooser.askcolor(color=current, title=t("Accent Colour"), parent=self)
        if picked:
            self._set_accent(picked)

    def _set_accent(self, picked):
        """Shows a colour in the preview and saves it (blank is the default), then offers a restart."""
        used = tabs.tidy_accent(picked) if picked else ""
        if used == self.vars["ACCENT_COLOUR"].get():
            return
        self.vars["ACCENT_COLOUR"].set(used)
        self._draw_accent_preview()
        why = tabs.accent_change(picked, used) if picked else None
        note = {"magenta": t("Moved away from magenta, which marks anything that uses AI credits."),
                "lighter": t("Made lighter, so it reads on the dark theme's buttons.")}.get(why, "")
        self.accent_note.config(text=note)
        if note:
            self.accent_note.pack(anchor="w")
        else:
            self.accent_note.pack_forget()
        self._save()
        if messagebox.askyesno(t("Accent Colour"), t("Restart 24bit7 now to use the new accent colour?"),
                               parent=self):
            self.winfo_toplevel().event_generate("<<Restart24bit7>>")

    def _draw_accent_preview(self):
        """A small piece of the dark theme in the chosen colour: logo, tabs, two buttons and the console."""
        a = tabs.tidy_accent(self.vars["ACCENT_COLOUR"].get())
        self.accent_swatch.config(bg=a)
        self.accent_code.config(text=a if self.vars["ACCENT_COLOUR"].get() else t("Default"))
        d, c = tabs.DARK, self.accent_preview
        k = scaled(self, 100) / 100
        c.delete("all")
        c.config(bg=d["window_bg"])
        c.create_rectangle(0, 0, 520 * k, 26 * k, fill="#000000", width=0)
        x = 10 * k
        for name in (t("Play"), t("Discover"), t("Settings")):
            item = c.create_text(x, 13 * k, text=name, anchor="w", fill=a, font=("Segoe UI", 9, "bold"))
            x = c.bbox(item)[2] + 18 * k
        x = 10 * k
        for part, colour in (("24", a), ("bit", tabs.logo_partner(a)), ("7", a)):
            item = c.create_text(x, 50 * k, text=part, anchor="w", fill=colour, font=("Segoe UI", 15, "bold"))
            x = c.bbox(item)[2] + 5 * k   # spaced as on the Play tab
        for i, (name, fg, bar) in enumerate(((t("Similar Tracks"), a, d["button_accent"]),
                                             (t("AI Playlist"), d["ai_purple"], d["ai_purple"]))):
            left = (10 + i * 128) * k
            c.create_rectangle(left, 82 * k, left + 120 * k, 110 * k, fill=d["button_bg"], width=0)
            c.create_rectangle(left, 107 * k, left + 120 * k, 110 * k, fill=bar, width=0)
            c.create_text(left + 60 * k, 95 * k, text=name, fill=fg, font=("Segoe UI", 8, "bold"))
        c.create_rectangle(276 * k, 36 * k, 510 * k, 140 * k, fill="#000000", width=0)
        c.create_rectangle(276 * k, 70 * k, 510 * k, 92 * k, fill=tabs.shade(a, 0.3), width=0)
        for i, text in enumerate((t("Similar Tracks") + ": Braided Hair", "  1 Giant Leap", t("Playing Now"))):
            c.create_text(284 * k, (48 + i * 33) * k, text=text, anchor="w", fill=a, font=("Consolas", 9))

    def _on_language_changed(self, *_):
        """Saves the language, then offers to restart so the whole app switches at once."""
        self._save()
        if messagebox.askyesno(t("Language"), t("Restart 24bit7 now to switch to {language}?",
                                                language=self.vars["UI_LANGUAGE"].get()), parent=self):
            self.winfo_toplevel().event_generate("<<Restart24bit7>>")

    def _refresh_key_marks(self):
        """Adds '(no key yet)' after a source whose key field is empty, and clears it once filled."""
        self._source_boxes = [b for b in self._source_boxes if b[0].winfo_exists()]   # button pages rebuild theirs
        for box, code, label, purpose in self._source_boxes:
            key = {"lastfm": "LASTFM_API_KEY", "ai": AI_FIELDS[self._ai_provider()][-1]}.get(code)
            if code == "listenbrainz" and purpose == "top":
                key = "LISTENBRAINZ_TOKEN"
            var = self.vars.get(key) if key else None
            missing = var is not None and not var.get().strip()
            if code == "lastfm" and engine.BUILTIN_LASTFM_KEY:   # the release's own key covers it
                missing = False
            if code == "tidal":   # needs both halves
                missing = any(k in self.vars and not self.vars[k].get().strip()
                              for k in ("TIDAL_CLIENT_ID", "TIDAL_CLIENT_SECRET"))
            try:
                box.config(text=label + ("  " + t("(no key yet)") if missing else ""))
            except tk.TclError:
                pass

    def _save(self, *_):
        """Auto-save. Skips writing an empty store list (keeps the last good file)."""
        if self._loading:
            return
        self._refresh_key_marks()
        if self._button_page is not None:
            self._sync_moderator_box(self._button_page)
        updates = self._current_updates()
        if not updates["DIGITAL_STORES"]:
            return   # don't persist a no-stores state; user is mid-change
        try:
            write_env(updates)
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    # --- tabs --------------------------------------------------------------

    def _scroll_tab(self, nb, text):
        """
        A Settings page that scrolls (scrollbar and mouse wheel) when its content is
        taller than the window. Returns the inner frame to build on. The inner frame
        gets <<Shown>> each time the page is opened, in place of <Map>.
        """
        outer = tk.Frame(nb)
        nb.add(outer, text=t(text))
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

    # --- a row inside a section ---------------------------------------------------------

    def _line(self, box, r, label=None, pady=(4, 4)):
        """A row inside a section: an optional bold label, then whatever is packed into the frame returned."""
        row = tk.Frame(box)
        row.grid(row=r, column=0, columnspan=6, sticky="w", pady=pady)
        if label:
            tk.Label(row, text=label, font=LABEL_FONT).pack(side="left", padx=(0, 10))
        return row

    def _build_saved(self, nb):
        """JRiver Playlists: one set of rows, shared by every Alexa device."""
        tab = self._scroll_tab(nb, N_("JRiver Playlists"))
        self._main_saved = ProfilePage("saved", None, saved_playlists.main_settings(), {}, self._save_saved_main)
        self._fill_saved(tab, self._main_saved)

    # --- the Buttons page --------------------------------------------------------------------

    def _build_buttons(self, nb):
        """
        Settings > Playlists: the playlists listed on the left, a tick beside each for the Play tab;
        the chosen one's page on the right, one scrolling page: its name (click to rename), its
        filters and shortcut, then its config's sources and settings. Each playlist carries one
        kind's settings. The standard playlist of each kind also writes .env.
        """
        ttk.Style(self).configure("Big.TCheckbutton", font=("Segoe UI", 11))
        outer = tk.Frame(nb)
        nb.add(outer, text=t("Playlist Settings"))
        self._buttons_outer = outer
        self._button_id = None
        left = tk.Frame(outer, padx=12, pady=12)
        left.pack(side="left", fill="y")
        box = section(left, t("Your Playlist Buttons"),
                      t("Each playlist is a recipe of its own: a kind of build, its sources and settings, the "
                        "filters it runs under and a keyboard shortcut. Ticked, it's a button on the Play tab; "
                        "unticked, it's kept here for voice commands and shortcuts. Click a name to change it. A "
                        "voice command runs the playlist its device names for the phrase (Settings > Devices), or "
                        "the standard playlist of that kind."))
        holder = tk.Frame(box)
        holder.grid(row=0, column=0, sticky="we")
        self._button_list = tk.Frame(holder, bd=1, relief="solid", bg=PALETTE.get("field_bg") or box.cget("bg"))
        self._button_list.pack(side="left", fill="x", expand=True, anchor="n")
        self._button_rows = []
        strip = tk.Frame(holder)   # six square buttons beside the list: add, delete, up, down, out, nest
        strip.pack(side="left", anchor="n", padx=(8, 0))
        self._list_buttons = {}
        self._folded = set()   # parents whose children are folded away in the list
        for key, symbol, note, command, gap in (
                ("add", "+", N_("Add a playlist: a copy of one, a template, or a new one."), self._button_add, 0),
                ("remove", "\u2212", N_("Delete the chosen playlist. Its children come out onto the row."),
                 self._button_remove, 0),
                ("up", "\u25b2", N_("Move the chosen playlist up: left on the Play tab."), lambda: self._button_move(-1), 8),
                ("down", "\u25bc", N_("Move the chosen playlist down: right on the Play tab."), lambda: self._button_move(1), 0),
                ("out", "\u25c0", N_("Bring the chosen playlist out of its parent's menu, back onto the row."),
                 self._button_unnest, 8),
                ("nest", "\u25b6", N_("Nest the chosen playlist under the one above it: off the row and into that "
                                      "playlist's menu, which its button's arrow opens."), self._button_nest, 0)):
            b = FlatButton(strip, text=symbol, width=2, command=command, quiet=True)
            b.pack(pady=(gap, 4))
            Tooltip(b, t(note))
            self._list_buttons[key] = b
        restore = tk.Label(box, text=t("Restore Default Playlists"), fg=PALETTE["button_fg"], font=HELP_FONT, cursor="hand2")
        restore.grid(row=1, column=0, sticky="w", pady=(8, 0))
        restore.bind("<Button-1>", lambda e: self._button_restore())
        Tooltip(restore, t("Puts back anything 24bit7 ships that's been deleted: a standard playlist, Artist + Guests, "
                           "Consensus or a Top 10, under the playlist it came under."))
        self._build_device_box(left)
        self._button_right = tk.Frame(outer, pady=12)
        self._button_right.pack(side="left", fill="both", expand=True, padx=(0, 12))
        outer.bind("<Map>", lambda e: self._buttons_refresh())
        self._buttons_refresh()

    def show_playlist(self, button_id, rename=False):
        """
        Opens Settings on this playlist's page (the Play tab's cog, right-click Settings, a new playlist).
        rename: the name box opens at once, cursor in it, for a playlist that's just been made.
        """
        self._button_id = button_id
        self._pane.select(self._buttons_outer)
        self._buttons_refresh()
        if rename:
            button = buttons.get(button_id)
            if button is not None:
                self.after(150, lambda: self._button_rename_inline(button))

    def _button_names(self):
        return [b["name"] for b in self._buttons]

    def _buttons_refresh(self):
        """Lists the playlists as the Play tab has them; rebuilds the right side when the chosen one changed."""
        self._buttons = buttons.buttons_only()
        ids = [b["id"] for b in self._buttons] + [b["id"] for b in buttons.load() if b.get("device")]
        if self._button_id not in ids:
            self._button_id = self._buttons[0]["id"] if self._buttons else None
        page = self._button_page
        rebuild = page is None or page.button is None or page.button["id"] != self._button_id
        self._fill_button_list()
        self._devices_refresh()
        if rebuild:
            self._button_fill_page()
        elif self._button_id is not None:   # the name may have changed on the Play tab
            title = getattr(self, "_button_title", None)
            if title is not None and title.winfo_exists():
                title.config(text=buttons.get(self._button_id)["name"])

    def _fill_button_list(self):
        """One row per playlist: its tick (on the Play tab) and its name; the chosen one highlighted."""
        for child in self._button_list.winfo_children():
            child.destroy()
        self._button_rows = []
        bg = self._button_list.cget("bg")
        parents = {b["parent"] for b in self._buttons if b.get("parent")}
        indent = scaled(self._button_list, 22)
        for b in self._buttons:
            if b.get("parent") in self._folded:
                continue   # folded away under its parent
            on = b["id"] == self._button_id   # the chosen row: a rounded outline in the accent colour, no fill
            is_parent = b["id"] in parents
            parent = next((p for p in self._buttons if p["id"] == b.get("parent")), None)
            row = PickRow(self._button_list, b["name"], fg=PALETTE["ai_purple"] if b["kind"] == "vibe" else None, bg=bg,
                          chosen=on, indent=indent if parent is not None else 0,   # no tick: everything here is on the Play tab
                          fold=("closed" if b["id"] in self._folded else "open") if is_parent else None,
                          on_fold=lambda bt=b: self._fold(bt["id"]),
                          tag=t("default") if parent is not None and parent.get("default") == b["id"] else "",
                          fit=True)   # as wide as its name needs, not Tk's ten centimetres: the page gets the rest
            row.configure(cursor="hand2")
            row.pack(fill="x", padx=3, pady=1)
            row.bind("<Button-1>", lambda e, bt=b: self._pick_button(bt["id"]))
            if parent is not None:
                row.bind("<Button-3>", lambda e, bt=b, p=parent: self._child_row_menu(e, p, bt))
            self._button_rows.append((b["id"], row, None, row, None))
        if self._button_rows:   # every row the width of the widest, with room for a longer name to come
            width = max(scaled(self._button_list, 220), max(r.winfo_reqwidth() for _i, r, _l, _r, _v in self._button_rows))
            for _i, r, _l, _r, _v in self._button_rows:
                r.configure(width=width)
        if not self._buttons:
            tk.Label(self._button_list, text=t("No playlists yet."), fg=PALETTE["help_fg"], font=HELP_FONT, bg=bg).pack(
                anchor="w", padx=8, pady=6)
        self._sync_list_buttons()

    def _sync_list_buttons(self):
        """
        Remove, Up, Down, Out and Nest grey out when they can't apply: nothing chosen; the first or last
        among its siblings; not a child; a parent, a child, or the first top-level one.
        """
        strip = getattr(self, "_list_buttons", None)
        if not strip:
            return
        chosen = next((b for b in self._buttons if b["id"] == self._button_id), None)
        sibs = [b for b in self._buttons if chosen is not None
                and (b.get("parent") or "") == (chosen.get("parent") or "")]
        i = sibs.index(chosen) if chosen is not None else -1
        strip["remove"].config(state="normal" if chosen is not None else "disabled")
        strip["up"].config(state="normal" if i > 0 else "disabled")
        strip["down"].config(state="normal" if 0 <= i < len(sibs) - 1 else "disabled")
        strip["out"].config(state="normal" if chosen is not None and chosen.get("parent") else "disabled")
        can_nest = (chosen is not None and not chosen.get("parent") and i > 0
                    and not any(b.get("parent") == chosen["id"] for b in self._buttons))
        strip["nest"].config(state="normal" if can_nest else "disabled")

    def _fold(self, parent_id):
        """The arrow on a parent row: its children fold away, or come back."""
        if parent_id in self._folded:
            self._folded.discard(parent_id)
        else:
            self._folded.add(parent_id)
        self._fill_button_list()

    def _button_nest(self):
        """Nests the chosen playlist under the top-level playlist above it."""
        chosen = next((b for b in self._buttons if b["id"] == self._button_id), None)
        if chosen is None or chosen.get("parent"):
            return
        above = [b for b in self._buttons if not b.get("parent")]
        i = above.index(chosen)
        if i == 0 or not buttons.nest(chosen["id"], above[i - 1]["id"]):
            return
        self._buttons_refresh()
        self._buttons_changed()

    def _button_unnest(self):
        if self._button_id is not None and buttons.unnest(self._button_id):
            self._buttons_refresh()
            self._buttons_changed()

    def _set_child_default(self, parent, child):
        """Make Default on a child, or Not the Default on the one that is; the Play tab's face follows."""
        is_default = parent.get("default") == child["id"]
        buttons.set_default(parent["id"], "" if is_default else child["id"])
        self._buttons_refresh()
        self._buttons_changed()

    def _child_row_menu(self, event, parent, child):
        """Right-click on a child in the list: Make Default (or Not the Default), Out to the Row."""
        import review_gui
        p = review_gui.palette()
        menu = tk.Menu(self, tearoff=0, bg=p["bg"], fg=p["text"], activebackground=p["row_on"],
                       activeforeground=p["accent"])
        is_default = parent.get("default") == child["id"]
        menu.add_command(label=t("Not the Default") if is_default else t("Make Default"),
                         command=lambda: self._set_child_default(parent, child))
        menu.add_command(label=t("Out to the Row"), command=lambda: (buttons.unnest(child["id"]), self._buttons_refresh(),
                                                                     self._buttons_changed()))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _pick_button(self, button_id):
        if button_id != self._button_id and buttons.get(button_id) is not None:   # a button's or a device's playlist
            self._button_id = button_id
            self._fill_button_list()
            self._button_fill_page()

    def _button_move(self, by):
        if self._button_id is None:
            return
        buttons.move(self._button_id, by)
        self._buttons_refresh()
        self._buttons_changed()

    def _buttons_changed(self):
        """Tells the Play tab to redraw its row: names, ticks, notes and which playlists are greyed out."""
        try:
            self.winfo_toplevel().event_generate("<<ButtonsChanged>>")
        except tk.TclError:
            pass

    def _button_add(self):
        answer = ask_new_button(self)
        if answer is None:
            return
        button, wants_page = buttons.add_from_choice(answer)
        if button is None:
            return
        self.show_playlist(button["id"], rename=wants_page)
        self._buttons_changed()

    def _button_remove(self):
        button = buttons.get(self._button_id) if self._button_id else None
        if button is None:
            return
        if not messagebox.askyesno(t("Remove Playlist"),
                                   t("Delete {name}? Its page and settings go with it.",
                                     name=button["name"]), parent=self):
            return
        buttons.remove(button["id"])
        self._button_id = None
        self._buttons_refresh()
        self._buttons_changed()

    def _button_restore(self):
        missing = buttons.restore_standard()
        if not missing:
            messagebox.showinfo(t("Restore Default Playlists"), t("Everything 24bit7 ships is there already."),
                                parent=self)
            return
        self._button_id = missing[0]["id"]
        self._buttons_refresh()
        self._buttons_changed()

    def _button_fill_page(self):
        """The right side: the playlist's name (click to rename), its filters and shortcut, then its config."""
        right = self._button_right
        for child in right.winfo_children():
            child.destroy()
        self._button_page, self._score_pages = None, []
        self._subtitle_box = None   # the Alternate Title box, on a parent's page only
        button = buttons.get(self._button_id) if self._button_id else None
        if button is None:
            holder = tk.Frame(right)
            holder.pack(fill="x")
            box = section(holder, t("No playlist chosen"))
            tk.Label(box, text=t("Click Add to make a playlist."), fg=PALETTE["help_fg"],
                     font=HELP_FONT).grid(row=0, column=0, sticky="w")
            return
        kind = button["kind"]
        head = tk.Frame(right)
        head.pack(fill="x", padx=(0, 0), pady=(0, 8))
        title_row = tk.Frame(head)
        title_row.grid(row=0, column=0, sticky="w")
        self._button_title = tk.Label(title_row, text=button["name"], font=("Segoe UI", 12, "bold"), cursor="hand2")
        if kind == "vibe":   # magenta: uses AI credit
            self._button_title.config(fg=PALETTE["ai_purple"])
        self._button_title.pack(side="left")
        tk.Label(title_row, text=t("click to rename"), fg=PALETTE["help_fg"], font=HELP_FONT).pack(side="left", padx=(10, 0))
        self._button_title.bind("<Button-1>", lambda e: self._button_rename_inline(button))
        about = t("No config yet: add one below.") if kind is None else t(buttons.KIND_LABELS[kind])
        if button.get("device"):
            phrase = next((label for ph, label in devices.PHRASES
                           if devices.for_device(button["device"])["buttons"].get(ph) == button["id"]), None)
            about = t("{device}'s own playlist for \"{phrase}\": what its voice command runs.",
                      device=devices.name_of(button["device"]), phrase=t(phrase) if phrase else "")
        elif button.get("standard"):
            about = t("Standard {kind} playlist: what a device's voice commands run unless Settings > Devices says otherwise.",
                      kind=about)
        tk.Label(head, text=about, fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=1, column=0, sticky="w")
        if buttons.is_parent(button):   # a parent: how its own option reads in its drop-down
            alt = tk.Frame(head)
            alt.grid(row=2, column=0, sticky="w", pady=(8, 0))
            tk.Label(alt, text=t("Alternate Title")).pack(side="left")
            self._subtitle_var = tk.StringVar(value=button.get("subtitle") or "")
            box_ = self._subtitle_box = ttk.Entry(alt, textvariable=self._subtitle_var, width=28)
            box_.pack(side="left", padx=(8, 0))

            def save_subtitle(_e=None, bid=button["id"]):
                if self._subtitle_var.get().strip() != (buttons.get(bid) or {}).get("subtitle", ""):
                    buttons.set_subtitle(bid, self._subtitle_var.get())
                    self._buttons = buttons.buttons_only()
                    self._buttons_changed()
            box_.bind("<FocusOut>", save_subtitle)
            box_.bind("<Return>", save_subtitle)
            help_mark(alt, t("How this playlist's own option reads in its drop-down, beside the playlists nested "
                             "under it: \"Top 12, Random Order\", say. The button keeps the name."),
                      on=box_).pack(side="left", padx=(8, 0))
        self._button_filter_row = tk.Frame(head)
        self._button_filter_row.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._button_filters_refresh()
        for old in [c for c in self.hotkey_vars if hotkeys.is_button(c)]:   # the page before this one's box
            del self.hotkey_vars[old], self.hotkey_notes[old]
        if kind != "vibe" and hotkeys.AVAILABLE:   # an AI Playlist needs a theme typed, so no key can run it
            short = tk.Frame(head)
            short.grid(row=4, column=0, sticky="w", pady=(8, 0))
            widgets = self._shortcut_row(short, 0, hotkeys.button_code(button["id"]), N_("Shortcut"),
                                         button.get("shortcut") or "")
            help_mark(short, t("Keys that run this playlist from anywhere in Windows, even with 24bit7 in the tray, "
                               "on the zone chosen under Settings > Other > Keyboard Shortcuts. Click the box and "
                               "press the keys; Esc cancels."), on=widgets[0]).grid(row=0, column=4, sticky="w",
                                                                                     padx=(8, 0))
            self.refresh_hotkey_notes()

        inner = self._button_inner = self._scroll_page(right)
        cfgs = buttons.configs(button)
        mix = buttons.tidy_mix(button.get("mix"), len(cfgs))
        base_env = dict(read_env())
        pages = []
        for n, cfg in enumerate(cfgs):
            block = self._config_block(inner, button, n, cfg)
            env = dict(base_env)
            env.update(cfg["settings"])
            p = ProfilePage("button", None, env, {}, lambda *_: None)
            p.button, p.columns = button, bool(button.get("standard")) and n == 0
            p.config_index, p.config_kind = n, cfg["kind"]
            p.save = lambda *_, p=p: self._save_button_page(p)
            pages.append((p, block))
        self._button_page, self._button_pages = (pages[0][0] if pages else None), [p for p, _ in pages]
        self._add_config_row(inner, button)
        if not pages:   # a blank slate: the row above is all there is until a config is added
            self._refresh_key_marks()
            return
        if len(cfgs) > 1:
            self._mix_section(inner, button, cfgs, mix)
        # the sections for the whole playlist sit under the configs, in a fixed order whichever config fills them
        whole = tk.Frame(inner)
        whole.grid(row=inner.grid_size()[1], column=0, sticky="ew")
        whole.grid_columnconfigure(0, weight=1)
        places = {}
        for title in WHOLE_SECTIONS:
            places[title] = tk.Frame(whole)
            places[title].grid(row=len(places), column=0, sticky="ew")
            places[title].grid_columnconfigure(0, weight=1)
        resyncs = []
        for n, (p, block) in enumerate(pages):
            kind = cfgs[n]["kind"]
            if kind != "vibe":   # an AI Playlist's tracks come from the AI, so it has no sources to pick
                self._fill_sources(block, p, kind)
                resyncs.append(p.resync)
            if len(cfgs) == 1:
                self._fill_playlist(block, p, kind, where_=places)
            else:   # the first config's whole-playlist sections, bar Drift and Non-stop, which follow the Mix
                parts = {"Playlist"} | ({"Deep Cuts", "Hidden Tracks", "If All Else Fails", "Run After Building"}
                                        if n == 0 else set())
                if n == mix["drift_from"]:
                    parts.add("Drift")
                if n == mix["continue_as"]:
                    parts.add("Non-stop")
                self._fill_playlist(block, p, kind, parts=parts, where_=places)
            resyncs.append(p.resync)
            self._sync_moderator_box(p)
        pages[0][0].resync = lambda: [r() for r in resyncs]
        self._refresh_key_marks()

    def _config_block(self, inner, button, n, cfg):
        """A config's block: "Config n · Kind" (click to fold it away), Remove on the second and later. Returns its body."""
        block = tk.Frame(inner)
        block.grid(row=inner.grid_size()[1], column=0, sticky="ew", pady=(0, 6))
        block.grid_columnconfigure(0, weight=1)
        head = tk.Frame(block)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        body = tk.Frame(block)
        body.grid(row=1, column=0, sticky="ew")
        body.grid_columnconfigure(0, weight=1)
        kind = cfg["kind"]
        arrow = tk.Label(head, text="\u25be", font=HEADING_FONT, fg=PALETTE["section_fg"], cursor="hand2")
        arrow.pack(side="left", padx=(0, 6))
        title = tk.Label(head, text=t("Config {n}", n=n + 1), font=HEADING_FONT, fg=PALETTE["section_fg"], cursor="hand2")
        title.pack(side="left")
        tk.Label(head, text="\u00b7", fg=PALETTE["help_fg"]).pack(side="left", padx=8)
        if n == 0 and button.get("standard"):   # a standard playlist is its kind; the others can change theirs
            tk.Label(head, text=t(buttons.KIND_LABELS[kind]), font=HEADING_FONT,
                     fg=PALETTE["ai_purple"] if kind == "vibe" else PALETTE["section_fg"]).pack(side="left")
        else:
            labels = [t(label) for label in buttons.KIND_LABELS.values()]
            kind_var = tk.StringVar(value=t(buttons.KIND_LABELS[kind]))
            kind_cb = TCombobox(head, textvariable=kind_var, values=labels, state="readonly",
                                width=max(len(label) for label in labels) + 2)
            kind_cb.pack(side="left")
            Tooltip(kind_cb, t("What this config does. Changing it starts the config again from the standard "
                               "playlist of that kind."))

            def kind_chosen(_e=None):
                kind_cb.selection_clear()
                chosen = next((k for k, label in buttons.KIND_LABELS.items() if t(label) == kind_var.get()), kind)
                if chosen != kind:
                    self._config_set_kind(button, n, chosen)
            kind_cb.bind("<<ComboboxSelected>>", kind_chosen)
            self._kind_boxes = getattr(self, "_kind_boxes", [])
            self._kind_boxes.append(kind_cb)
        shown = {"open": True}

        def toggle(_e=None):
            shown["open"] = not shown["open"]
            if shown["open"]:
                body.grid()
            else:
                body.grid_remove()
            arrow.config(text="\u25be" if shown["open"] else "\u25b8")
        for w in (arrow, title):
            w.bind("<Button-1>", toggle)
        if n > 0 or not button.get("standard"):   # a standard playlist keeps its own config
            remove = tk.Label(head, text=t("Remove"), fg=PALETTE["help_fg"], font=HELP_FONT, cursor="hand2")
            remove.pack(side="right")
            remove.bind("<Button-1>", lambda e: self._config_remove(button, n))
            Tooltip(remove, t("Takes this config off the playlist. Its settings go with it."))
        return body

    def _config_set_kind(self, button, n, kind):
        buttons.set_config_kind(button["id"], n, kind)
        self._buttons = buttons.buttons_only()
        self._button_fill_page()
        self._buttons_changed()

    def _config_remove(self, button, n):
        cfg = buttons.configs(button)[n]
        if not messagebox.askyesno(t("Remove Config"),
                                   t("Remove config {n} ({kind}) from {name}?", n=n + 1,
                                     kind=t(buttons.KIND_LABELS[cfg["kind"]]), name=button["name"]), parent=self):
            return
        buttons.remove_config(button["id"], n)
        self._buttons = buttons.buttons_only()
        self._button_fill_page()
        self._buttons_changed()

    def _add_config_row(self, inner, button):
        """+ Add Another Config (+ Add a Config on a blank slate): a menu of the four kinds; the new config starts from the standard playlist of its kind."""
        row = tk.Frame(inner)
        row.grid(row=inner.grid_size()[1], column=0, sticky="w", pady=(0, 14))
        empty = not buttons.configs(button)
        add = ttk.Button(row, text=t("+ Add a Config") if empty else t("+ Add Another Config"), command=lambda: menu.tk_popup(
            add.winfo_rootx(), add.winfo_rooty() + add.winfo_height()))
        add.pack(side="left")
        menu = tk.Menu(row, tearoff=0)
        for kind, label in buttons.KIND_LABELS.items():
            menu.add_command(label=t(label), command=lambda k=kind: self._config_add(button, k))
        Tooltip(add, t("What this playlist builds: Artist Matching, Track Matching, Artist's Top Tracks or an AI "
                       "Playlist, starting from the standard playlist of that kind.") if empty else
                t("A second config finds tracks its own way (Artist Matching under Artist's Top Tracks, say), "
                  "and the Mix section that appears says how they come together."))
        self._config_menu = menu

    def _config_add(self, button, kind):
        buttons.add_config(button["id"], kind)
        self._buttons = buttons.buttons_only()
        self._button_fill_page()
        self._buttons_changed()

    def _mix_section(self, inner, button, cfgs, mix):
        """Mix: how two or more configs come together, which config Drift runs from and which Non-stop carries on as."""
        box = section(inner, t("Mix"),
                      t("How the configs come together. Shuffle mixes every config's tracks in together; Append plays "
                        "one config's tracks, then the next's; Alternate takes turns, by the pattern. Each config "
                        "finds its own number of tracks. Drift from names the config Drift carries on from, and "
                        "Continue as the one Non-stop carries on as."))
        names = [t("Config {n} \u00b7 {kind}", n=i + 1, kind=t(buttons.KIND_LABELS[c["kind"]])) for i, c in enumerate(cfgs)]
        row = self._line(box, 0, t("Combine"), pady=(0, 0))
        combine_var = tk.StringVar(value=t(dict(buttons.COMBINES)[mix["combine"]]))
        combine_cb = TCombobox(row, textvariable=combine_var, values=[t(label) for _, label in buttons.COMBINES],
                               state="readonly", width=11)
        combine_cb.pack(side="left")
        pattern_row = self._line(box, 1, t("Pattern"), pady=(4, 0))
        pattern_vars = []
        for i, _name in enumerate(names):
            if i:
                tk.Label(pattern_row, text=t("then"), fg=PALETTE["help_fg"], font=HELP_FONT).pack(side="left", padx=6)
            var = tk.StringVar(value=str(mix["pattern"][i] if i < len(mix["pattern"]) else 1))
            pattern_vars.append(var)
            cb = TCombobox(pattern_row, textvariable=var, values=["1", "2", "3", "4", "5"], state="readonly", width=3)
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", lambda e, cb=cb: (cb.selection_clear(), save()))
            tk.Label(pattern_row, text=t("from config {n}", n=i + 1), fg=PALETTE["help_fg"], font=HELP_FONT).pack(
                side="left", padx=(6, 0))
        drift_names = [name for name, c in zip(names, cfgs) if buttons.has_drift(c["kind"])]
        drift_row = self._line(box, 2, t("Drift from"), pady=(4, 0))
        drift_var = tk.StringVar(value=names[mix["drift_from"]] if names[mix["drift_from"]] in drift_names
                                 else (drift_names[0] if drift_names else ""))
        drift_cb = TCombobox(drift_row, textvariable=drift_var, values=drift_names, state="readonly",
                             width=max(16, max((len(n) for n in drift_names), default=16) + 2))
        drift_cb.pack(side="left")
        if not drift_names:
            drift_cb.state(["disabled"])
        cont_row = self._line(box, 3, t("Continue as"), pady=(4, 0))
        cont_var = tk.StringVar(value=names[mix["continue_as"]])
        cont_cb = TCombobox(cont_row, textvariable=cont_var, values=names, state="readonly",
                            width=max(16, max(len(n) for n in names) + 2))
        cont_cb.pack(side="left")

        def show_pattern():
            if option_code(buttons.COMBINES, combine_var.get()) == "alternate":
                pattern_row.grid()
            else:
                pattern_row.grid_remove()

        def save(refill=False):
            fields = dict(combine=option_code(buttons.COMBINES, combine_var.get()),
                          pattern=[int(v.get() or 1) for v in pattern_vars],
                          drift_from=names.index(drift_var.get()) if drift_var.get() in names else mix["drift_from"],
                          continue_as=names.index(cont_var.get()) if cont_var.get() in names else mix["continue_as"])
            buttons.set_mix(button["id"], **fields)
            button["mix"] = buttons.get(button["id"])["mix"]
            self._buttons_changed()
            if refill:   # Drift or Non-stop now belong to another config: their sections move
                self._button_fill_page()

        def combine_chosen(_e=None):
            combine_cb.selection_clear()
            show_pattern()
            save()
        combine_cb.bind("<<ComboboxSelected>>", combine_chosen)
        drift_cb.bind("<<ComboboxSelected>>", lambda e: (drift_cb.selection_clear(), save(refill=True)))
        cont_cb.bind("<<ComboboxSelected>>", lambda e: (cont_cb.selection_clear(), save(refill=True)))
        show_pattern()
        self._mix_controls = (combine_cb, pattern_vars, drift_cb, cont_cb)

    def _button_rename_inline(self, button):
        """The name at the top becomes a box to type in; Enter or clicking away saves, Esc leaves it."""
        title = self._button_title
        if not title.winfo_exists():
            return
        parent = title.master
        var = tk.StringVar(value=button["name"])
        entry = tk.Entry(parent, textvariable=var, font=("Segoe UI", 12, "bold"), width=max(12, len(button["name"]) + 2))
        title.pack_forget()
        entry.pack(side="left", before=parent.winfo_children()[1])
        entry.focus_set()
        entry.selection_range(0, "end")

        def finish(save):
            if not entry.winfo_exists():
                return
            name = var.get().strip()
            entry.destroy()
            first = next((w for w in parent.winfo_children() if w is not title and w.winfo_manager()), None)
            if first is not None:   # back in front of "click to rename" (before= needs a packed sibling)
                title.pack(side="left", before=first)
            else:
                title.pack(side="left")
            if save and name and name != button["name"]:
                buttons.rename(button["id"], name)
                button["name"] = name
                title.config(text=name)
                self._buttons = buttons.buttons_only()
                self._fill_button_list()
                self._buttons_changed()
        entry.bind("<Return>", lambda e: finish(True))
        entry.bind("<FocusOut>", lambda e: finish(True))
        entry.bind("<Escape>", lambda e: finish(False))

    def _filter_ticks(self, row, ticked, command, title=None, help_text=None):
        """A tick per filter in a row, then Edit Filters. Returns {filter id: BooleanVar}."""
        for child in row.winfo_children():
            child.destroy()
        if title:
            label = tk.Label(row, text=title, font=LABEL_FONT)
            label.pack(side="left", padx=(0, 10))
            if help_text:
                help_mark(row, help_text, on=label)
        items = filters.load()
        if not items:
            tk.Label(row, text=t("No filters yet."), fg=PALETTE["help_fg"]).pack(side="left", padx=(0, 10))
        out = {}
        for f in items:
            var = tk.BooleanVar(value=f["id"] in ticked)
            out[f["id"]] = var
            text = f["name"] + ("" if f.get("on") else "   " + t("(off)"))
            ttk.Checkbutton(row, text=text, variable=var, command=command).pack(side="left", padx=(0, 12))
        tk.Button(row, text=t("Edit Filters..."), command=self._open_filters).pack(side="left")
        return out

    def _filter_ticks_refresh(self):
        """After Edit Filters closes or saves: the ticks on the open playlist's page follow."""
        self._button_filters_refresh()

    def _button_filters_refresh(self):
        """The Filters row on a playlist's page: a tick per filter, then Edit Filters."""
        row = getattr(self, "_button_filter_row", None)
        if row is None or not row.winfo_exists():
            return
        button = buttons.get(self._button_id) if self._button_id else None
        if button is None:
            return
        self._button_filter_vars = self._filter_ticks(
            row, button.get("filters") or [], self._button_filters_changed, t("Filters"),
            t("Every playlist this button builds, Drift and Non-stop top-ups included, must pass each "
              "ticked filter. A filter that's off is kept for later and doesn't apply."))

    def _button_filters_changed(self):
        if self._button_id:
            buttons.set_filters(self._button_id, [fid for fid, var in self._button_filter_vars.items() if var.get()])
            self._buttons_changed()

    def _save_button_page(self, p):
        """A button's page saves into the button; the standard button of its kind also writes .env."""
        if p.loading or self._loading or p.button is None:
            return
        self._refresh_key_marks()
        self._sync_moderator_box(p)
        values = p.values()
        index = getattr(p, "config_index", 0)
        kind = getattr(p, "config_kind", None) or p.button["kind"]
        sources_key = {"artists": "SIMILAR_SOURCES", "tracks": "SIMILAR_TRACK_SOURCES",
                       "top": "TOP_TRACK_SOURCES"}.get(kind)
        if sources_key in values and not values[sources_key]:
            return   # every source unticked: mid-change, keep the last good set
        # laid over what the config has: a setting with no control on the page stays as it was
        cfg = buttons.configs(p.button)[index]
        settings = dict(cfg.get("settings") or {})
        settings.update({k: v for k, v in values.items() if k in buttons.KIND_KEYS[kind]})
        buttons.set_config_settings(p.button["id"], index, settings)
        if index == 0:
            p.button["settings"] = settings
        else:
            p.button["configs"][index - 1]["settings"] = settings
        env = {k: v for k, v in values.items() if k in buttons.GLOBAL_KEYS}   # Say why in the room: one for all
        if p.button.get("standard") and index == 0:
            env.update(settings)
        if env:
            try:
                write_env(env)
            except Exception as e:
                messagebox.showerror(t("Save failed"), str(e), parent=self)
        self._buttons_changed()

    # --- the Devices page --------------------------------------------------------------------


    # --- the Device Playlists box --------------------------------------------------------------------

    def _build_device_box(self, left):
        """
        Under the buttons: a tab per Alexa device, the zone it plays to, Enable Switch To, when it was
        last heard, and the playlist each of its phrases runs (Ben, 2 Nov 2026): the standard playlist
        of that kind, greyed with a Standard tag, until the device is given its own.
        """
        box = section(left, t("Device Playlists"),
                      t("Each Alexa device that has spoken to 24bit7 and the playlist each of its phrases runs: the "
                        "standard playlist of that kind, greyed, until you give the device its own. Click a greyed row "
                        "to make one, right-click the device's own for Back to Standard, and click the device's name "
                        "to rename it. A new device appears here the first time it speaks."))
        self._device_id = None
        self._device_tabs = tk.Frame(box)
        self._device_tabs.grid(row=0, column=0, sticky="w")
        self._device_head = tk.Frame(box)
        self._device_head.grid(row=1, column=0, sticky="we", pady=(6, 4))
        self._device_rows_box = tk.Frame(box, bd=1, relief="solid", bg=PALETTE.get("field_bg") or box.cget("bg"))
        self._device_rows_box.grid(row=2, column=0, sticky="we")
        self._device_rows = []
        self._device_restore = tk.Label(box, text=t("Restore Default Device Playlists"), fg=PALETTE["button_fg"],
                                        font=HELP_FONT, cursor="hand2")
        self._device_restore.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self._device_restore.bind("<Button-1>", lambda e: self._device_restore_defaults())
        Tooltip(self._device_restore, t("Every phrase of this device back to the standard playlist of its kind; the "
                                        "device's own playlists are deleted."))

    def _devices_refresh(self):
        """The device tabs, the chosen device's header and its four phrase rows, as things stand."""
        if not hasattr(self, "_device_tabs") or not self._device_tabs.winfo_exists():
            return
        rows = voice.devices()
        ids = [r[0] for r in rows]
        if self._device_id not in ids:
            self._device_id = ids[0] if ids else None
        for frame in (self._device_tabs, self._device_head, self._device_rows_box):
            for child in frame.winfo_children():
                child.destroy()
        self._device_rows = []
        bg = self._device_rows_box.cget("bg")
        if not rows:
            tk.Label(self._device_head, text=t("Say a command on an Alexa device and it appears here."),
                     fg=PALETTE["help_fg"], font=HELP_FONT).pack(anchor="w")
            self._device_rows_box.grid_remove()
            self._device_restore.grid_remove()
            return
        self._device_rows_box.grid()
        self._device_restore.grid()
        for device_id, name, zone, heard in rows:
            on = device_id == self._device_id
            cell = tk.Frame(self._device_tabs)
            cell.pack(side="left", padx=(0, 14))
            tab = tk.Label(cell, text=name or t("Unnamed device"), font=("Segoe UI", 10, "bold"), cursor="hand2",
                           fg=PALETTE["button_fg"] if on else PALETTE["help_fg"])
            tab.pack()
            bar = tk.Frame(cell, height=2, bg=PALETTE["button_fg"] if on else cell.cget("bg"))
            bar.pack(fill="x")
            tab.bind("<Button-1>", lambda e, d=device_id: self._device_pick(d))
            tab.bind("<Double-Button-1>", lambda e, d=device_id, n=name: self._device_rename(d, n))
            tab.bind("<Button-3>", lambda e, d=device_id, n=name: self._device_rename(d, n))
            Tooltip(tab, t("Click to see this device's playlists; double-click to rename it."))
        device_id, name, zone, heard = next(r for r in rows if r[0] == self._device_id)
        head = self._device_head
        line = tk.Frame(head)
        line.pack(fill="x")
        tk.Label(line, text=t("Plays to"), font=LABEL_FONT).pack(side="left")
        zones = engine.zone_names()
        zone_var = tk.StringVar(value=zone or "Not set")
        zone_cb = TCombobox(line, textvariable=zone_var, state="readonly", width=16,
                            values=[N_("Not set")] + zones + ([zone] if zone and zone not in zones else []))
        zone_cb.pack(side="left", padx=(8, 0))
        Tooltip(zone_cb, t("The JRiver zone this device's commands play in."))

        def zone_changed(_e=None):
            zone_cb.selection_clear()
            picked = "" if zone_var.get() == t("Not set") else zone_var.get()
            voice.update_device(device_id, zone=picked)
            self._devices_refresh()   # the Switch tick depends on the zone
        zone_cb.bind("<<ComboboxSelected>>", zone_changed)
        self._device_zone_cb = zone_cb
        remove = tk.Label(line, text=t("Remove"), fg=PALETTE["help_fg"], font=HELP_FONT, cursor="hand2")
        remove.pack(side="right")
        remove.bind("<Button-1>", lambda e: self._device_remove())
        Tooltip(remove, t("Forgets this device and its own playlists. It comes back the next time it speaks to 24bit7."))
        switch_var = tk.BooleanVar(value=bool(zone) and zone not in voice.switch_unticked())
        switch = ttk.Checkbutton(head, text=t("Enable Switch To"), variable=switch_var,
                                 command=lambda: voice.set_switch_enabled(zone, switch_var.get()))
        switch.pack(anchor="w", pady=(4, 0))
        Tooltip(switch, t("Ticked, this device's zone is one you can switch the music to, with \"Alexa, ask needle drop "
                          "to switch\" or the Switch Zones keyboard shortcut. With two zones ticked, switching moves the "
                          "music straight to the other one. With three or more, Alexa asks which zone, or you can say "
                          "\"switch to\" and the zone name; the shortcut steps through them in turn. The music carries "
                          "on from the same track, and the zone it left stops. Two devices on the same zone share one tick."))
        if not zone:
            switch.state(["disabled"])
        self._device_switch = switch
        if heard:
            tk.Label(head, text=t("Last heard {when}.", when=heard), fg=PALETTE["help_fg"], font=HELP_FONT).pack(anchor="w")
        for phrase, label, playlist, own in devices.rows(device_id):
            text = t("{phrase}: {name}", phrase=t(label), name=playlist["name"]) if playlist else t(label)
            colour = (PALETTE["ai_purple"] if playlist and playlist["kind"] == "vibe" else PALETTE["text"]) if own \
                else PALETTE["help_fg"]
            row = PickRow(self._device_rows_box, text, fg=colour, bg=bg, fit=True,
                          chosen=bool(playlist) and playlist["id"] == self._button_id,
                          tag="" if own else t("Standard"))
            row.configure(cursor="hand2")
            row.pack(fill="x", padx=3, pady=1)
            if own:
                row.bind("<Button-1>", lambda e, p=playlist: self._pick_device_playlist(p["id"]))
                row.bind("<Button-3>", lambda e, ph=phrase, p=playlist: self._device_row_menu(e, ph, p))
                Tooltip(row, t("{device}'s own playlist for \"{phrase}\". Click for its page; right-click for Back to Standard.",
                               device=name or t("Device"), phrase=t(label)))
            else:
                row.bind("<Button-1>", lambda e, ph=phrase, lb=label: self._device_make_own(ph, lb))
                Tooltip(row, t("Runs the standard {name} when {device} asks. Click to give {device} its own.",
                               name=playlist["name"] if playlist else t(label), device=name or t("Device")))
            self._device_rows.append((phrase, row, playlist, own))
        if self._device_rows:
            width = max(scaled(self._device_rows_box, 220), max(r.winfo_reqwidth() for _p, r, _b, _o in self._device_rows))
            for _p, r, _b, _o in self._device_rows:
                r.configure(width=width)

    def _device_pick(self, device_id):
        if device_id != self._device_id:
            self._device_id = device_id
            self._devices_refresh()

    def _device_rename(self, device_id, name):
        new = tabs.ask_name(self, t("Rename Device"), t("A name for this device:"), initial=name or "")
        if new is None:
            return
        new = new.strip() or t("Device")
        voice.update_device(device_id, name=new)
        self._devices_refresh()

    def _device_remove(self):
        if self._device_id is None:
            return
        name = devices.name_of(self._device_id)
        if not messagebox.askyesno(t("Remove Device"), t("Remove {name}? Its own playlists go with it. It comes back the "
                                                          "next time it speaks to 24bit7.", name=name), parent=self):
            return
        gone = {b["id"] for b in buttons.of_device(self._device_id)}
        voice.remove_device(self._device_id)
        devices.forget(self._device_id)
        if self._button_id in gone:
            self._button_id = None
        self._buttons_refresh()

    def _device_restore_defaults(self):
        if self._device_id is None:
            return
        name = devices.name_of(self._device_id)
        if not messagebox.askyesno(t("Restore Default Device Playlists"),
                                   t("Every phrase of {name} back to the standard playlist of its kind? Its own playlists "
                                     "are deleted.", name=name), parent=self):
            return
        gone = {b["id"] for b in buttons.of_device(self._device_id)}
        devices.restore_defaults(self._device_id)
        if self._button_id in gone:
            self._button_id = None
        self._buttons_refresh()

    def _device_make_own(self, phrase, label):
        """A greyed row clicked: the Add window, for a copy or a template to become the device's own for the phrase."""
        if self._device_id is None:
            return
        name = devices.name_of(self._device_id)
        prompt = AddPlaylistPrompt(self, device=(name, t(label)))
        self.wait_window(prompt)
        answer = prompt.result
        if answer is None:
            return
        how, what = answer
        made = devices.make_own(self._device_id, phrase, (how, what) if how in ("copy", "template") else ("standard", None))
        self._pick_device_playlist(made["id"])

    def _device_row_menu(self, event, phrase, playlist):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=t("Back to Standard"), command=lambda: self._device_back_to_standard(phrase, playlist))
        menu.tk_popup(event.x_root, event.y_root)

    def _device_back_to_standard(self, phrase, playlist):
        devices.reset(self._device_id, phrase)
        if self._button_id == playlist["id"]:
            self._button_id = None
        self._buttons_refresh()

    def _pick_device_playlist(self, playlist_id):
        """A device's own playlist opens on the right like any other; the buttons list shows no pick."""
        self._button_id = playlist_id
        self._fill_button_list()
        self._devices_refresh()
        self._button_fill_page()

    def _open_filters(self):
        """Edit Filters: a window with the named filters on the left and the chosen one's rules on the right."""
        win = getattr(self, "_filter_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_set()
            return win
        win = self._filter_win = tk.Toplevel(self)
        win.title(t("Edit Filters"))
        win.transient(self.winfo_toplevel())
        win.geometry(f"{scaled(self, 980)}x{scaled(self, 700)}")
        win.minsize(scaled(self, 700), scaled(self, 400))
        win.bind("<Destroy>", lambda e: self._filter_ticks_refresh() if e.widget is win else None)
        tab = self._scroll_page(win)
        self._filters = filters.load()
        self._filter_i = 0 if self._filters else None
        left = tk.Frame(tab)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 14))
        self._filter_right = tk.Frame(tab)
        self._filter_right.grid(row=0, column=1, sticky="nwe")
        tab.grid_columnconfigure(1, weight=1)

        box = section(left, t("Your filters"),
                      t("Filters narrow the playlists 24bit7 builds, Drift and Non-stop top-ups included. Tick a "
                      "filter under Filters on a button's page (Settings > Buttons) and every playlist that button "
                      "builds must pass it. Where several apply, a track must pass them all. Albums, songs, "
                      "shuffles and JRiver playlists asked for by voice play as asked."))
        self._filter_list = tk.Listbox(box, height=8, width=26, activestyle="none", exportselection=False,
                                       font=("Segoe UI", 10))
        self._filter_list.grid(row=0, column=0, sticky="w")
        self._filter_list.bind("<<ListboxSelect>>", self._filter_picked)
        row = tk.Frame(box)
        row.grid(row=1, column=0, sticky="w", pady=(8, 0))
        for text, command in ((t("New"), self._filter_new), (t("Rename"), self._filter_rename),
                              (t("Duplicate"), self._filter_duplicate), (t("Delete"), self._filter_delete)):
            tk.Button(row, text=text, width=9, command=command).pack(side="left", padx=(0, 3))
        self._filter_refresh()
        return win

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
        return [("", t("None"))] + sorted(items, key=lambda x: x[1].lower())

    def _filter_save(self):
        try:
            filters.save(self._filters)
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)
        self._filter_fill_list()
        self._filter_ticks_refresh()   # the ticks on the button's page follow names and On

    def _filter_refresh(self):
        self._filter_fill_list()
        self._filter_fill_editor()

    def _filter_fill_list(self):
        lb = self._filter_list
        if not lb.winfo_exists():
            return
        lb.delete(0, "end")
        for item in self._filters:
            lb.insert("end", item["name"] + ("" if item.get("on") else "   " + t("(off)")))
        if self._filter_i is not None and self._filter_i < len(self._filters):
            lb.selection_set(self._filter_i)

    def _filter_picked(self, _e=None):
        chosen = self._filter_list.curselection()
        if chosen:
            self._filter_i = chosen[0]
            self._filter_fill_editor()

    def _filter_fill_editor(self):
        right = self._filter_right
        if not right.winfo_exists():
            return
        for child in right.winfo_children():
            child.destroy()
        if self._filter_i is None or self._filter_i >= len(self._filters):
            box = section(right, t("No filter chosen"))
            tk.Label(box, text=t("Click New to make your first filter."), fg=PALETTE["help_fg"],
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
        ttk.Checkbutton(row, text=t("On"), variable=on, command=on_toggled).pack(side="left")
        help_mark(row, t("Off keeps the filter for later without it applying anywhere.")).pack(side="left", padx=(8, 0))
        parts = filters.used_by(item["id"])
        tk.Label(box, text=(t("Used by: {names}", names=", ".join(parts)) if parts else
                            t("Not ticked on any button yet. Tick it under Filters on a button's page.")),
                 fg=PALETTE["help_fg"], font=HELP_FONT, wraplength=scaled(box, 560), justify="left").grid(
            row=1, column=0, sticky="w", pady=(8, 0))

        box = section(right, t("Only pick from"),
                      t("Every playlist this filter applies to only uses tracks on this JRiver playlist or "
                      "smartlist. Set up any filtering you like in JRiver's smartlist editor, and 24bit7 "
                      "respects it. The list comes from Settings > JRiver Playlists."))
        options = self._filter_playlists()
        labels = dict(options)
        pick = tk.StringVar(value=labels.get(item.get("pick_from", ""), "None"))
        keep.append(pick)
        cb = TCombobox(box, textvariable=pick, values=[l for _, l in options], state="readonly", width=44)
        cb.grid(row=0, column=0, sticky="w")

        def picked(_e=None):
            pid = next((p for p, l in options if l == pick.get()), "")
            item["pick_from"] = pid
            item["pick_name"] = pick.get().split("  (")[0] if pid else ""
            cb.selection_clear()
            self._filter_save()
        cb.bind("<<ComboboxSelected>>", picked)

        # --- Rules ---
        box = section(right, t("Rules"),
                      t("Tracks must match all (or any) of the rules. A track with no value for a field passes that "
                      "rule, and the log counts them; an unrated track counts as rating 0, and an unplayed one "
                      "as played 0 times and never played. Rating 0 means unrated. Sample rate at most 48 kHz "
                      "saves JRiver converting on the fly for a Sonos."))
        top = tk.Frame(box)
        top.grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(top, text=t("Tracks must match")).pack(side="left")
        match = tk.StringVar(value=item.get("match", "all"))
        keep.append(match)
        match_cb = TCombobox(top, textvariable=match, values=[N_("all"), N_("any")], state="readonly", width=7)
        match_cb.pack(side="left", padx=6)
        tk.Label(top, text=t("of these rules")).pack(side="left")

        def match_changed(_e=None):
            item["match"] = match.get()
            match_cb.selection_clear()
            self._filter_save()
        match_cb.bind("<<ComboboxSelected>>", match_changed)
        rows = tk.Frame(box)
        rows.grid(row=1, column=0, sticky="w")
        field_labels = [label for _, label, _, _ in filters.FIELDS]
        units = {"days": t("days"), "minutes": t("minutes"), "khz": "kHz"}

        def rule_row(r, rule):
            label, ops, kind = filters.FIELD_INFO[rule["field"]]
            field = tk.StringVar(value=label)
            op = tk.StringVar(value=dict(ops).get(rule.get("op"), ops[0][1]))
            keep.extend([field, op])
            field_cb = TCombobox(rows, textvariable=field, values=field_labels, state="readonly", width=13)
            field_cb.grid(row=r, column=0, sticky="w", pady=3)
            op_cb = TCombobox(rows, textvariable=op, values=[l for _, l in ops], state="readonly", width=17)
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
                    tk.Label(cell, text=t("and")).pack(side="left", padx=6)
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
        tk.Button(box, text=t("Add rule"), width=max(10, len(t("Add rule")) + 2), command=add_rule).grid(
            row=2, column=0, sticky="w", pady=(8, 0))
        right.keep = keep   # hold the variables while the page shows

    def _filter_new(self):
        name = tabs.ask_name(self._filter_win, t("New Filter"), t("Name for the new filter:"))
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
        name = tabs.ask_name(self._filter_win, t("Rename Filter"), t("New name for the filter:"), item["name"])
        if name and name.strip():
            item["name"] = name.strip()
            self._filter_save()
            self._filter_fill_editor()

    def _filter_duplicate(self):
        if self._filter_i is None:
            return
        copy = filters.tidy(dict(self._filters[self._filter_i]))
        copy.update(id=filters.blank()["id"], name=t("{name} copy", name=copy["name"]))
        copy["rules"] = [dict(r) for r in copy["rules"]]
        self._filters.insert(self._filter_i + 1, copy)
        self._filter_i += 1
        self._filter_save()
        self._filter_fill_editor()

    def _filter_delete(self):
        if self._filter_i is None:
            return
        item = self._filters[self._filter_i]
        if not messagebox.askyesno(t("Delete filter"), t("Delete the filter {name}?", name=item["name"]),
                                   parent=self._filter_win):
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
            bl = tk.StringVar(value=option_label(SAVED_NONSTOP_OPTIONS, row.get("blend", "no")))
            ns = tk.StringVar(value=option_label(SAVED_NONSTOP_OPTIONS, row.get("nonstop", "no")))
            rs = tk.StringVar(value=option_label(SAVED_RESEED_OPTIONS, row.get("reseed", "last")))
            sk = tk.StringVar(value=option_label(SAVED_SKIP_OPTIONS, str(row.get("skip", "0"))))
            p.keep += [sh, bl, ns, rs, sk]
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col, sticky="nsew")
            ttk.Checkbutton(cell, variable=sh).pack(padx=20, pady=2)
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col + 1, sticky="nsew")
            TCombobox(cell, textvariable=bl, values=[s for _, s in SAVED_NONSTOP_OPTIONS],
                         state="readonly", width=15).pack(anchor="w", padx=6, pady=2)
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col + 2, sticky="nsew")
            ns_cb = TCombobox(cell, textvariable=ns, values=[s for _, s in SAVED_NONSTOP_OPTIONS],
                                 state="readonly", width=15)
            ns_cb.pack(anchor="w", padx=6, pady=2)
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col + 3, sticky="nsew")
            rs_cb = TCombobox(cell, textvariable=rs, values=[s for _, s in SAVED_RESEED_OPTIONS],
                                 state="readonly", width=14)
            rs_cb.pack(anchor="w", padx=6, pady=2)
            cell = tk.Frame(parent, bg=bg)
            cell.grid(row=r, column=col + 4, sticky="nsew")
            sk_cb = TCombobox(cell, textvariable=sk, values=[s for _, s in SAVED_SKIP_OPTIONS],
                                 state="readonly", width=9)
            sk_cb.pack(anchor="w", padx=6, pady=2)

            def store(*_):
                row["shuffle"] = "1" if sh.get() else "0"
                row["blend"] = option_code(SAVED_NONSTOP_OPTIONS, bl.get())
                row["nonstop"] = option_code(SAVED_NONSTOP_OPTIONS, ns.get())
                row["reseed"] = option_code(SAVED_RESEED_OPTIONS, rs.get())
                row["skip"] = option_code(SAVED_SKIP_OPTIONS, sk.get())
                sync_reseed()
                on_change()

            def sync_reseed():
                live = "disabled" not in ns_cb.state()
                rs_cb.state(["!disabled"] if live and row.get("nonstop", "no") != "no" else ["disabled"])
            for var in (sh, bl, ns, rs, sk):
                var.trace_add("write", store)
            p.reseed_syncs.append(sync_reseed)

        def header(parent, labels, clicks=None):
            """A heading row; clicks maps a column to what clicking its heading does."""
            for c, text in enumerate(labels):
                holder = parent
                if text in HEAD_HELP:   # a heading with a ? beside it
                    holder = tk.Frame(parent, bg=table_colours()[0])
                    holder.grid(row=0, column=c, sticky="we", ipadx=8, ipady=4)
                lab = tk.Label(holder, text=t(text), font=LABEL_FONT, anchor="w", bg=table_colours()[0],
                               fg=PALETTE.get("head_fg") or PALETTE["section_fg"],
                               width=WIDTHS[c] if c < 3 else 0)
                if text in HEAD_HELP:
                    lab.pack(side="left")
                    help_mark(holder, t(HEAD_HELP[text])).pack(side="left", padx=(4, 0))
                else:
                    lab.grid(row=0, column=c, sticky="we", ipadx=8, ipady=4)
                if clicks and c in clicks:
                    lab.config(cursor="hand2")
                    lab.bind("<Button-1>", lambda e, f=clicks[c]: f())
            return parent

        def cell(parent, r, c, text, bg):
            tk.Label(parent, text=text, anchor="w", bg=bg, width=WIDTHS[c]).grid(
                row=r, column=c, sticky="we", ipadx=8, ipady=2)

        p.keep, p.reseed_syncs = [], []
        HEAD_HELP = {
            "Blend": N_("Weaves new music into a playlist asked for by voice: one of yours, then one new, until "
                      "the new tracks run out, up to 50. Similar artists adds top tracks by artists like the "
                      "ones in the playlist; Similar tracks adds songs like its tracks. The playlist starts "
                      "straight away and the new tracks join a few seconds later, after the song that's "
                      "playing. It uses the Sources and Playlist settings of the option you pick, and never "
                      "adds a song already in the playlist."),
            "Non-stop": N_("Keeps the music going after a playlist asked for by voice: when its last song "
                         "starts, more are added, Similar artists or Similar tracks, seeded from the song "
                         "chosen under Reseed from. It carries on until something else is played on that "
                         "zone."),
            "Reseed from": N_("Where each Non-stop top-up seeds from. Last track and 2nd track follow on from the "
                            "music, so the evening travels. Whole playlist is Keep It Tight: each top-up seeds "
                            "from one of the playlist's own tracks, a different one each time, and carries on "
                            "from the last track once they've all been used."),
        }
        CONTROLS = [N_("Shuffle"), N_("Blend"), "Non-stop", N_("Reseed from"), N_("Skip recent")]   # short, so headings fit their dropdowns

        # --- All playlists ---
        box = section(tab, t("All playlists"),
                      t("Ticked, the two rows below apply, one to every playlist and one to every "
                      "smartlist, and the table is greyed out. Unticked, each playlist follows its own "
                      "row in the table.\n"
                      "JRiver can randomise a smartlist itself, for example with a random album sort, "
                      "and shuffling it here would break those albums up, so you may want Shuffle off "
                      "on the smartlist row.\n"
                      "Set as Default copies a row into the table rows of its type that are shown "
                      "below, replacing their own settings. New playlists start with their type's row."))
        p.all_var = tk.BooleanVar(value=p.data["all"] == "1")

        def all_toggled():
            p.data["all"] = "1" if p.all_var.get() else "0"
            p.resync()
            changed()
        ttk.Checkbutton(box, text=t("Use global playlist settings"), variable=p.all_var,
                        command=all_toggled).grid(row=0, column=0, sticky="w", pady=(0, 6))
        p.all_row = header(tk.Frame(box, bd=1, relief="solid"), [N_("Folder"), "Playlist", N_("Type")] + CONTROLS
                           + [N_("Defaults")])
        p.all_row.grid(row=1, column=0, sticky="w")
        bg = p.all_row.cget("bg")
        def set_default(kind):
            """Set as Default: the type's global row into the table rows of that type now shown."""
            smart = kind != "Playlist"
            shown = [pid for pid, row in getattr(p, "shown", []) if (row.get("type") or "Playlist") == kind]
            if not shown:
                messagebox.showinfo(t("Set as Default"), t("No smartlists are shown in the table below.") if smart
                                    else t("No playlists are shown in the table below."), parent=self)
                return
            total = sum(1 for row in p.data["rows"].values() if (row.get("type") or "Playlist") == kind)
            n = len(shown)
            # whole sentences, so each language can word them its own way
            if n == 1 and total == 1:
                ask = (t("Copy the smartlist defaults to your one smartlist? Its own settings will be replaced.")
                       if smart else
                       t("Copy the playlist defaults to your one playlist? Its own settings will be replaced."))
            elif n == 1:
                ask = (t("Copy the smartlist defaults to the 1 smartlist shown? Its own settings will be replaced.")
                       if smart else
                       t("Copy the playlist defaults to the 1 playlist shown? Its own settings will be replaced."))
            elif n == total:
                ask = (t("Copy the smartlist defaults to all {n} smartlists? Their own settings will be replaced.", n=n)
                       if smart else
                       t("Copy the playlist defaults to all {n} playlists? Their own settings will be replaced.", n=n))
            else:
                ask = (t("Copy the smartlist defaults to the {n} smartlists shown? Their own settings will be "
                         "replaced.", n=n) if smart else
                       t("Copy the playlist defaults to the {n} playlists shown? Their own settings will be "
                         "replaced.", n=n))
            if not messagebox.askyesno(t("Set as Default"), ask, parent=self):
                return
            saved_playlists.copy_defaults(p.data, shown, kind)
            build_table()
            changed()

        for r, (name, kind, key) in enumerate(((t("All playlists"), "Playlist", "all_row"),
                                               (t("All smartlists"), "Smartlist", "all_row_smart")), start=1):
            for c, text in enumerate((t(ALL_FOLDERS), name, kind)):
                cell(p.all_row, r, c, text, bg)
            row_controls(p.all_row, r, bg, p.data[key], changed)
            holder = tk.Frame(p.all_row, bg=bg)
            holder.grid(row=r, column=3 + len(CONTROLS), sticky="nsew")
            tk.Button(holder, text=t("Set as Default"), command=lambda k=kind: set_default(k)).pack(
                anchor="w", padx=8, pady=2)

        # --- Playlists ---
        box = section(tab, t("Playlists"),
                      t("Your JRiver playlists and smartlists. These settings apply when you ask for a playlist by "
                      "voice. Playlists you start in JRiver itself aren't changed. Click Folder or Playlist to "
                      "sort by it; click again for Z-A. Root (the top level) always comes first.\n"
                      "Skip recent leaves out tracks played in the last few days, but never empties a playlist.\n"
                      "Blend and Non-stop are explained by the ? beside each heading."))
        bar = tk.Frame(box)
        bar.grid(row=0, column=0, sticky="we", pady=(0, 8))
        tk.Label(bar, text=t("Folder")).pack(side="left")
        p.folder_var = tk.StringVar(value=t(ALL_FOLDERS))
        p.folder_cb = ttk.Combobox(bar, textvariable=p.folder_var, state="readonly", width=20)
        p.folder_cb.pack(side="left", padx=(8, 18))
        tk.Label(bar, text=t("Search")).pack(side="left")
        p.search_var = tk.StringVar()
        tk.Entry(bar, textvariable=p.search_var, width=24).pack(side="left", padx=(8, 0))
        p.count_label = tk.Label(bar, text="", fg=PALETTE["help_fg"], font=HELP_FONT)
        p.count_label.pack(side="left", padx=(14, 0))
        p.rescan_btn = tk.Button(bar, text=t("Rescan"), width=10, command=lambda: rescan(loud=True))
        p.rescan_btn.pack(side="right", padx=(24, 0))
        p.table_holder = tk.Frame(box)
        p.table_holder.grid(row=1, column=0, sticky="w")
        tk.Label(box, text=t("New playlists arrive with the settings of their type's row under All playlists."),
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
            p.folder_cb.config(values=[t(ALL_FOLDERS)] + ([saved_playlists.ROOT] if saved_playlists.ROOT in folders
                                                       else []) + others)
            if p.folder_var.get() not in p.folder_cb.cget("values"):
                p.folder_var.set(t(ALL_FOLDERS))

        def build_table(*_):
            for child in p.table_holder.winfo_children():
                child.destroy()
            p.table = None
            p.reseed_syncs[:] = p.reseed_syncs[:2]   # keep the two global rows'
            rows = ordered(list(p.data["rows"].items()))
            folder = p.folder_var.get()
            wanted = p.search_var.get().strip().lower()
            shown = [(pid, row) for pid, row in rows
                     if (folder == t(ALL_FOLDERS) or (row.get("folder") or saved_playlists.ROOT) == folder)
                     and (wanted in (row.get("name") or "").lower() or wanted in (row.get("folder") or "").lower())]
            p.shown = shown
            total = len(rows)
            if len(shown) != total:
                p.count_label.config(text=tn("{count} playlist, {shown} shown", "{count} playlists, {shown} shown",
                                             total, shown=len(shown)))
            else:
                p.count_label.config(text=tn("{count} playlist", "{count} playlists", total))
            if not rows:
                tk.Label(p.table_holder, text=t("No playlists yet. Make sure JRiver is running, then click Rescan."),
                         fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=0, column=0, sticky="w")
                return
            arrow = " \u25b2" if p.data.get("sort") == "az" else " \u25bc"
            by = p.data.get("sort_by")
            labels = [t("Folder") + (arrow if by != "name" else ""), "Playlist" + (arrow if by == "name" else ""),
                      t("Type")] + CONTROLS
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
                    messagebox.showerror(t("Rescan"), t("Couldn't read your playlists from JRiver.\n\n{error}", error=e), parent=self)
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
            set_enabled(p.all_row, True)   # the global rows are the defaults too, so always editable
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
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    # --- the Sources sections ---

    def _listenbrainz_row(self, p, box, r, key, notes):
        """The ListenBrainz algorithm dropdown for one section, with its notes behind a ?."""
        row = self._line(box, r, t("ListenBrainz algorithm"), pady=(10, 0))
        p.vars[key] = tk.StringVar(value=p.env.get(key, "alltime"))
        cb = TCombobox(row, textvariable=p.vars[key], values=[N_("alltime"), N_("recent")],
                          state="readonly", width=10)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", p.save)
        help_mark(row, t(notes)).pack(side="left", padx=(8, 0))
        return r + 1

    def _source_ticks(self, p, box, r, group, names, default, command, purpose, help_text=None,
                      lb_key=None, lb_notes=None, scores=None, hint=None):
        """
        The sources for one kind, one per line, with an optional ? beside the first.
        lb_key: the ListenBrainz algorithm dropdown, on its line. scores: "artists" or
        "tracks", for Test My Sources' columns beside each source (Settings > Other).
        hint: "artists" or "tracks", for a quiet score figure beside each source instead.
        """
        frame = tk.Frame(box)
        frame.grid(row=r, column=0, columnspan=6, sticky="w", pady=(2, 4))
        chosen = [x.strip().lower() for x in p.env.get(group, default).split(",") if x.strip()]
        p.vars[group] = {}
        # with scores: the AI on its own line at the top (it's only tested on request), then the notice,
        # the header row, and the other sources with their scores beside them
        has_ai = bool(scores) and any(c == "ai" for c, _ in names)
        next_row = self._score_header(p, frame, scores, 1 if has_ai else 0) if scores else 0
        for n, (code, label) in enumerate(names):
            line = tk.Frame(frame)
            if scores and code == "ai":
                line.grid(row=0, column=0, columnspan=4, sticky="w", pady=1)
            elif scores:
                line.grid(row=next_row, column=0, sticky="w", pady=1)
                self._score_cells(p, frame, scores, code, next_row)
                next_row += 1
            else:
                line.pack(anchor="w", pady=1)
            v = tk.BooleanVar(value=code in chosen)
            p.vars[group][code] = v

            def ticked(command=command):
                self._sync_listenbrainz(p)
                command()
            tick = ttk.Checkbutton(line, text=label, variable=v, command=ticked,
                                   style="AI.Big.TCheckbutton" if code == "ai" else "Big.TCheckbutton")
            if code == "ai":   # magenta: uses AI credit
                ttk.Style(line).configure("AI.Big.TCheckbutton", font=("Segoe UI", 11),
                                          foreground=PALETTE["ai_purple"])
            tick.pack(side="left")
            self._source_boxes.append((tick, code, label, purpose))
            if hint and code != "ai":   # its score from the last Test My Sources, quietly
                ui = p.__dict__.setdefault("score_ui", {}).setdefault(hint, {"cells": {}})
                hint_label = tk.Label(line, text="", font=HELP_FONT, fg=PALETTE["help_fg"])
                hint_label.pack(side="left", padx=(10, 0))
                ui.setdefault("hints", {})[code] = hint_label
                if p not in self.__dict__.setdefault("_score_pages", []):
                    self._score_pages.append(p)
            if help_text and n == 0:
                help_mark(line, help_text).pack(side="left", padx=(10, 0))
            if code == "listenbrainz" and lb_key:
                p.vars[lb_key] = tk.StringVar(value=p.env.get(lb_key, "alltime"))
                cb = TCombobox(line, textvariable=p.vars[lb_key], values=[N_("alltime"), N_("recent")],
                                  state="readonly", width=9)
                cb.pack(side="left", padx=(14, 0))
                cb.bind("<<ComboboxSelected>>", p.save)
                help_mark(line, t(lb_notes)).pack(side="left", padx=(8, 0))
                p.lb_cbs.append((v, cb))
        return r + 1

    # --- Test My Sources: scores beside the sources, the start window and Full Results ---------------

    def _score_header(self, p, frame, section, row):
        """
        The notice and a header row (Source, Score, Best At, Worst At, with a rule under it)
        above a section's scored sources, from row. Returns the row the first source goes on.
        """
        import source_test
        ui = p.__dict__.setdefault("score_ui", {}).setdefault(section, {"cells": {}})
        ui["notice"] = tk.Label(frame, text="", font=HELP_FONT, wraplength=scaled(frame, 300), justify="left",
                                anchor="w", padx=8, pady=4)
        ui["notice"].grid(row=row, column=0, columnspan=4, sticky="ew", pady=(8, 6))
        notice, head_row = ui["notice"], row + 1

        def fit_notice(_event=None):
            """The notice spans the table, Source to Worst At, at any display scaling."""
            try:
                width = frame.grid_bbox(0, head_row, 3, head_row)[2] - 16
            except tk.TclError:
                return
            width = max(scaled(frame, 300), width)
            if int(float(str(notice.cget("wraplength")) or 0)) != width:
                notice.config(wraplength=width)
        frame.bind("<Configure>", fit_notice, add="+")
        for c, title in enumerate((N_("Source"), N_("Score"), N_("Best At"), N_("Worst At"))):
            lab = tk.Label(frame, text=t(title), font=LABEL_FONT, fg=PALETTE["text_secondary"], anchor="w")
            lab.grid(row=row + 1, column=c, sticky="w", padx=(0 if c == 0 else 18, 0))
            if title == "Score":
                Tooltip(lab, t(source_test.PERFORMANCE_HELP), click=False)
                lab.config(cursor="question_arrow")
        tk.Frame(frame, bg=PALETTE["line"], height=1).grid(row=row + 2, column=0, columnspan=4, sticky="ew",
                                                           pady=(2, 4))
        if p not in self.__dict__.setdefault("_score_pages", []):
            self._score_pages.append(p)
        return row + 3

    def _score_cells(self, p, frame, section, code, row):
        cells = tuple(tk.Label(frame, text="", anchor="w") for _ in range(3))
        for c, lab in enumerate(cells, start=1):
            lab.grid(row=row, column=c, sticky="w", padx=(18, 0))
        p.score_ui[section]["cells"][code] = cells

    def _score_buttons(self, p, box, section):
        """Test My Sources (Re-run Test, Cancel Test) and Full Results, on the right of the Sources bar."""
        head = box.master.winfo_children()[0]
        ui = p.__dict__.setdefault("score_ui", {}).setdefault(section, {"cells": {}})
        ui["results"] = FlatButton(head, text=t("Full Results"), command=self._open_test_results, quiet=True)
        ui["results"].pack(side="right", padx=(6, 8), pady=3)
        ui["test"] = FlatButton(head, text=t("Test My Sources"), command=self._test_button)
        ui["test"].pack(side="right", pady=3)
        ui["progress"] = tk.Label(head, text="", font=HELP_FONT, bg=head.cget("bg"),
                                  fg=PALETTE.get("head_fg") or PALETTE["section_fg"])
        ui["progress"].pack(side="right", padx=(0, 8))

    def _refresh_scores(self):
        """Fills every Sources page's scores, notice and buttons from the latest results."""
        import source_test
        result, is_sample = source_test.load_results()
        running = source_test.is_running()
        state = source_test.progress_state
        names_ok = {}
        for p in [p for p in self.__dict__.get("_score_pages", []) if p.__dict__.get("score_ui")]:
            for section, ui in p.score_ui.items():
                notice = ui.get("notice")
                scores = (result or {}).get("scores", {}).get(section, {}).get("sources", {})
                for code, hint_label in ui.get("hints", {}).items():
                    s = scores.get(code)
                    try:
                        hint_label.config(text=f"{s['performance']}%" if s else "")
                    except tk.TclError:
                        pass
                try:
                    if notice is None or not notice.winfo_exists():
                        continue
                except tk.TclError:
                    continue
                if result and is_sample:
                    notice.config(text=source_test.sample_notice(result), bg=PALETTE["button_hover"],
                                  fg=PALETTE["button_fg"])
                elif result:
                    when = datetime.strptime(result["finished"], "%Y-%m-%d %H:%M").strftime("%d %b %Y")
                    notice.config(text=t("Your results, tested {when} ({mode}).", when=when.lstrip("0"),
                                       mode=t(result["mode"].title())),
                                  bg=notice.master.cget("bg"), fg=PALETTE["help_fg"])
                else:
                    notice.config(text=t("No results yet. Test My Sources shows how each source does with your "
                                       "library."), bg=notice.master.cget("bg"), fg=PALETTE["help_fg"])
                for code, cells in ui["cells"].items():
                    s = scores.get(code)
                    if code not in names_ok:
                        names_ok[code] = engine.source_has_key(code) if code != "ai" else engine.ai_enabled()
                    fg = PALETTE["help_fg"] if not names_ok[code] else PALETTE["text_secondary"]
                    texts = ((f"{s['performance']}%", ", ".join(s["best_at"]), ", ".join(s["worst_at"]))
                             if s else ("-", "", ""))
                    for lab, text in zip(cells, texts):
                        lab.config(text=text, fg=fg)
                if ui.get("test"):
                    ui["test"].config(text=t("Cancel Test") if running else
                                      (t("Re-run Test") if result and not is_sample else t("Test My Sources")))
                    ui["results"].config(state="normal" if result else "disabled")
                    ui["progress"].config(text=t("Testing {n} of {total}", n=state["n"], total=state["of"]) if running else "")
        return result, is_sample

    def _watch_source_test(self):
        """While a test runs, the progress and buttons follow it; when it ends, the scores refresh."""
        import source_test
        self._refresh_scores()
        if source_test.is_running():
            self.after(2000, self._watch_source_test)

    def _test_button(self):
        import source_test
        if source_test.is_running():
            source_test.cancel()
            self.after(300, self._watch_source_test)
        else:
            self._open_test_window()

    def _open_test_window(self):
        """The start window: Full or Quick, Include AI, Start."""
        import source_test
        win = tk.Toplevel(self)
        win.title(t("Test My Sources"))
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        self.test_window = win
        body = tk.Frame(win, padx=16, pady=12)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=t("Asks every source what's similar to a fixed set of seed tracks across 17 genres, "
                            "and counts how many answers are in your library. It runs in the background, so "
                            "you can keep using 24bit7."), wraplength=scaled(body, 420), justify="left").pack(anchor="w")
        mode = tk.StringVar(value="full")
        full, quick = len(source_test.load_seeds()), len(source_test.load_seeds(quick=True))
        for value, text in (("full", t("Full: {seeds} seeds, about {minutes} minutes", seeds=full,
                                       minutes=source_test.minutes_for(full))),
                            ("quick", t("Quick: {seeds} seeds, about {minutes} minutes", seeds=quick,
                                        minutes=source_test.minutes_for(quick)))):
            ttk.Radiobutton(body, text=text, variable=mode, value=value).pack(anchor="w", pady=(8 if value == "full" else 2, 0))
        ai = tk.BooleanVar(value=False)
        tick = ttk.Checkbutton(body, text=t("Include AI (costs a few pence)"), variable=ai)
        tick.pack(anchor="w", pady=(10, 0))
        if not engine.ai_enabled():
            tick.state(["disabled"])
            Tooltip(tick, t(NO_KEY_TEXT))
        buttons = tk.Frame(body)
        buttons.pack(fill="x", pady=(14, 0))

        def start():
            source_test.start_background(quick=mode.get() == "quick", include_ai=ai.get())
            win.destroy()
            self._watch_source_test()
        ttk.Button(buttons, text=t("Cancel"), command=win.destroy).pack(side="right")
        ttk.Button(buttons, text=t("Start"), command=start).pack(side="right", padx=(0, 6))
        win.start = start   # for the tests
        win.mode, win.ai = mode, ai
        return win

    def _open_test_results(self):
        """Full Results: every genre against every source, for Similar Artists and Similar Tracks."""
        import source_test
        result, is_sample = source_test.load_results()
        if not result:
            return None
        if not is_sample:
            source_test.mark_seen()   # the console stops repeating "ready"
        win = tk.Toplevel(self)
        win.title(t("Source Test Results"))
        win.transient(self.winfo_toplevel())
        self.results_window = win
        top = tk.Frame(win, padx=14, pady=10)
        top.pack(fill="x")
        if is_sample:
            tk.Label(top, text=source_test.sample_notice(result), bg=PALETTE["button_hover"], fg=PALETTE["button_fg"],
                     wraplength=scaled(top, 760),
                     justify="left", anchor="w", padx=8, pady=4).pack(fill="x")
        else:
            tk.Label(top, text=t("Your results, tested {when} ({mode}, {seeds} seeds).", when=result["finished"],
                                 mode=t(result["mode"].title()), seeds=len(result["seeds"])), fg=PALETTE["help_fg"], anchor="w").pack(fill="x")
        tk.Label(top, text=t("Score against the best source in each genre; the best in each row is shaded. "
                           "Hover a cell for its detail."), font=HELP_FONT, fg=PALETTE["help_fg"],
                 anchor="w").pack(fill="x", pady=(4, 0))
        nb = TabbedPane(win, font=("Segoe UI", 10, "bold"), pad=(16, 6))
        nb.pack(fill="both", expand=True, padx=14)
        names = {c: n for sec in source_test.SECTIONS for c, n in result["sources"][sec]}
        win.grids = {}
        for section, title in (("artists", N_("Similar Artists")), ("tracks", N_("Similar Tracks"))):
            page = tk.Frame(nb, padx=4, pady=8)
            nb.add(page, text=t(title))
            codes = [c for c, _ in result["sources"][section]]
            sc = result["scores"][section]
            stripe = PALETTE.get("field_bg") or PALETTE.get("window_bg")
            tk.Label(page, text=t("Genre"), font=LABEL_FONT, fg=PALETTE["help_fg"], anchor="w",
                     padx=8, pady=4).grid(row=0, column=0, sticky="ew")
            for c, code in enumerate(codes, start=1):
                tk.Label(page, text=names.get(code, code), font=LABEL_FONT, fg=PALETTE["help_fg"],
                         padx=8, pady=4).grid(row=0, column=c, sticky="ew")
            cells = {}
            for r, genre in enumerate(result["genres"], start=1):
                gs = sc["genres"][genre]
                bg = stripe if r % 2 else page.cget("bg")
                tk.Label(page, text=genre + ("  " + t("(you own little here)") if gs["thin"] else ""), anchor="w",
                         fg=PALETTE["help_fg"] if gs["thin"] else PALETTE["text_secondary"], bg=bg,
                         padx=8, pady=3).grid(row=r, column=0, sticky="nsew")
                for c, code in enumerate(codes, start=1):
                    v = gs["by"].get(code)
                    best = bool(v) and gs["best"] > 0 and v["useful"] == gs["best"]
                    lab = tk.Label(page, text=f"{v['percent']}%" if v else "-", bg=PALETTE["button_hover"] if best
                                   else bg, fg=PALETTE["button_fg"] if best else PALETTE["text_secondary"], font=("Segoe UI", 9, "bold") if best else ("Segoe UI", 9),
                                   padx=8, pady=3)
                    lab.grid(row=r, column=c, sticky="nsew")
                    Tooltip(lab, source_test.cell_detail(result, section, genre, code), click=False)
                    cells[(genre, code)] = lab
            foot = len(result["genres"]) + 1
            tk.Frame(page, bg=PALETTE["line"], height=1).grid(row=foot, column=0, columnspan=len(codes) + 1,
                                                              sticky="ew", pady=(2, 0))
            score = tk.Label(page, text=t("Score"), font=LABEL_FONT, anchor="w", padx=8, pady=4,
                             cursor="question_arrow")
            score.grid(row=foot + 1, column=0, sticky="ew")
            Tooltip(score, t(source_test.PERFORMANCE_HELP), click=False)
            for c, code in enumerate(codes, start=1):
                s = sc["sources"].get(code)
                tk.Label(page, text=f"{s['performance']}%" if s else "-", font=LABEL_FONT,
                         padx=8, pady=4).grid(row=foot + 1, column=c, sticky="ew")
            win.grids[section] = cells
        buttons = tk.Frame(win, padx=14, pady=10)
        buttons.pack(fill="x")

        def export():
            path = filedialog.asksaveasfilename(parent=win, defaultextension=".csv", initialfile="24bit7 source test.csv",
                                                filetypes=[("CSV", "*.csv")])
            if path:
                source_test.export_csv(result, path)

        def rerun():
            win.destroy()
            self._open_test_window()
        ttk.Button(buttons, text=t("Close"), command=win.destroy).pack(side="right")
        ttk.Button(buttons, text=t("Export CSV"), command=export).pack(side="right", padx=(0, 6))
        ttk.Button(buttons, text=t("Re-run Test"), command=rerun).pack(side="right", padx=(0, 6))
        win.export = export   # for the tests
        self.after(10, self._refresh_scores)
        return win

    def _sync_listenbrainz(self, p):
        """Each ListenBrainz algorithm dropdown greys out while ListenBrainz is unticked."""
        for tick, cb in getattr(p, "lb_cbs", []):
            cb.state(["!disabled"] if tick.get() else ["disabled"])

    def _inner_circle_section(self, p, page, group):
        """Consensus for a matching config: On or Off, the circle's size, and how many lists must agree."""
        g = group.upper()
        what = t("artists") if group == "artists" else t("tracks")
        box = section(page, t("Consensus"),
                      t("Instead of the seed's own list of similar {what}, Consensus takes the seed's closest few, "
                        "fetches each one's own similar {what}, and keeps what two or more of those lists agree on: "
                        "what the things you're listening to have in common. With Seed on Playing Now, the "
                        "sampled {what} are the circle. Fewer in the circle and more agreeing is tighter, and can "
                        "come up short; the console says so, and Drift fills in if it's on.", what=what))
        on_key, size_key, agree_key = f"INNER_CIRCLE_{g}", f"INNER_CIRCLE_{g}_SIZE", f"INNER_CIRCLE_{g}_AGREE"
        p.vars[on_key] = tk.BooleanVar(value=p.env.get(on_key, "0").strip().lower() in engine.YES)
        p.vars[size_key] = tk.StringVar(value=p.env.get(size_key, "3").strip() or "3")
        p.vars[agree_key] = tk.StringVar(value=p.env.get(agree_key, "2").strip() or "2")
        tick = ttk.Checkbutton(box, text=t("Consensus"), variable=p.vars[on_key], command=lambda: (sync(), p.save()))
        tick.grid(row=0, column=0, columnspan=6, sticky="w")
        row = self._line(box, 1, t("Circle"), pady=(6, 0))
        size_cb = TCombobox(row, textvariable=p.vars[size_key], values=["3", "4", "5"], state="readonly", width=4)
        size_cb.pack(side="left")
        tk.Label(row, text=t("of the seed's closest {what}", what=what), fg=PALETTE["help_fg"], font=HELP_FONT).pack(
            side="left", padx=(8, 0))
        row = self._line(box, 2, t("Must agree"), pady=(4, 0))
        agree_cb = TCombobox(row, textvariable=p.vars[agree_key], values=["2", "3", "4", "5"], state="readonly", width=4)
        agree_cb.pack(side="left")
        tk.Label(row, text=t("of their lists"), fg=PALETTE["help_fg"], font=HELP_FONT).pack(side="left", padx=(8, 0))

        def sync(*_):
            size = int(p.vars[size_key].get() or 3)
            agree_cb.config(values=[str(n) for n in range(2, size + 1)])
            if int(p.vars[agree_key].get() or 2) > size:
                p.vars[agree_key].set(str(size))
            on = p.vars[on_key].get()
            for cb in (size_cb, agree_cb):
                cb.state(["!disabled"] if on else ["disabled"])

        def size_changed(_e=None):
            size_cb.selection_clear()
            sync()
            p.save()
        size_cb.bind("<<ComboboxSelected>>", size_changed)
        agree_cb.bind("<<ComboboxSelected>>", lambda e: (agree_cb.selection_clear(), p.save()))
        sync()

    def _moderator_section(self, p, page, group):
        """A Moderator tick for one Play option, greyed out until the AI is set up."""
        box = section(page, t("Moderator"),
                      t("Checks each playlist (and each Drift round) once with your AI's quick model, and "
                      "removes tracks that clash with the seed's tone, energy and mood. "
                      "Logs each removal with its reason. Uses a little AI credit each time, a fraction of a "
                      "penny per playlist (nothing with Ollama)."),
                      title_fg=PALETTE["ai_purple"])
        key = f"AI_MODERATOR_{group.upper()}"
        p.vars[key] = tk.StringVar(value=engine.moderator_settings(p.env.get)[group].title())

        def chosen(*_):
            if p.vars[key].get() != "Off":
                warn_moderator_once(self)
            cb.selection_clear()
            p.save()
        row = self._line(box, 0, t("Level"), pady=(0, 0))
        cb = TCombobox(row, textvariable=p.vars[key], values=MODERATOR_CHOICES, state="readonly",
                       width=max(9, max(len(t(c)) for c in MODERATOR_CHOICES) + 2))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", chosen)
        help_mark(row, t(MODERATOR_LEVELS_HELP)).pack(side="left", padx=(8, 0))
        Tooltip(cb, t(NO_KEY_TEXT), when=lambda: not self._ai_set_up())
        p.moderator_boxes.append(cb)

    def _fill_sources(self, tab, p, kind):
        """A button's Sources page: its kind's sources, how many must agree, and its Moderator."""
        p.loading = True
        p.moderator_boxes = []
        pages = {kind: tab}   # an AI Playlist's tracks come from the AI, so it has no Sources page
        p.lb_cbs = []

        def similar_changed():
            sync_agreement(p, "SIMILAR_SOURCES", "SIMILAR_MIN_AGREEMENT", "agree_cb", 5)
            p.save()

        def tracks_changed():
            sync_agreement(p, "SIMILAR_TRACK_SOURCES", "SIMILAR_TRACK_MIN_AGREEMENT", "track_agree_cb", 99)
            p.save()

        # --- Similar Artists ---
        if kind == "artists":
            box = section(pages["artists"], t("Sources"),
                                   t("YouTube suggests from the playing track, using YouTube Music's up next queue. "
                                   "No key needed. Ticked on its own, it plays YouTube's queue as is, matched against "
                                   "your library. Ticked with other sources, its artists join the blend. It's an "
                                   "unofficial route, so it may break now and then."))
            r = self._source_ticks(p, box, 0, "SIMILAR_SOURCES", SOURCE_NAMES, "lastfm", similar_changed, "similar",
                                   hint="artists", lb_key="LISTENBRAINZ_ALGORITHM",
                                   lb_notes=N_("alltime: from all listening history; leans toward well-known artists.\n"
                                            "recent: what people are playing alongside this artist right now."))
            # How many sources must agree. Replaced the old on/off tick box; an old
            # on/off setting carries over (on -> 2, off -> Off).
            legacy_on = p.env.get("SIMILAR_REQUIRE_AGREEMENT", "1") in ("1", "true", "yes")
            start = p.env.get("SIMILAR_MIN_AGREEMENT", "").strip() or ("2" if legacy_on else "1")
            p.vars["SIMILAR_MIN_AGREEMENT"] = tk.StringVar(value="Off" if start in ("0", "1") else start)
            row = self._line(box, r, t("Must agree"), pady=(10, 0))
            p.agree_cb = TCombobox(row, textvariable=p.vars["SIMILAR_MIN_AGREEMENT"], state="readonly", width=6)
            p.agree_cb.pack(side="left")
            p.agree_cb.bind("<<ComboboxSelected>>", p.save)
            help_mark(row, t("How many sources must agree before an artist is picked. Higher means a smoother "
                           "playlist with fewer wildcards, but less chance of discovering something new. "
                           "Tip: try single sources on their own before blending.")).pack(side="left", padx=(8, 0))
            self._inner_circle_section(p, pages["artists"], "artists")
            self._moderator_section(p, pages["artists"], "artists")

        # --- Similar Tracks: its own sources and agreement ---
        if kind == "tracks":
            box = section(pages["tracks"], t("Sources"),
                          t("Tracks like the seed track, for the Similar Tracks button. No key needed for "
                          "ListenBrainz or YouTube."))
            r = self._source_ticks(p, box, 0, "SIMILAR_TRACK_SOURCES", TRACK_SOURCE_NAMES, "lastfm,listenbrainz,youtube",
                                   tracks_changed, "similar", hint="tracks", lb_key="LISTENBRAINZ_TRACK_ALGORITHM",
                                   lb_notes=N_("alltime: from all listening history.\n"
                                            "recent: roughly the last six months; older songs may find fewer matches."))
            start = p.env.get("SIMILAR_TRACK_MIN_AGREEMENT", "2").strip() or "2"
            p.vars["SIMILAR_TRACK_MIN_AGREEMENT"] = tk.StringVar(value="Off" if start in ("0", "1") else start)
            row = self._line(box, r, t("Must agree"), pady=(10, 0))
            p.track_agree_cb = TCombobox(row, textvariable=p.vars["SIMILAR_TRACK_MIN_AGREEMENT"],
                                            state="readonly", width=6)
            p.track_agree_cb.pack(side="left")
            p.track_agree_cb.bind("<<ComboboxSelected>>", p.save)
            help_mark(row, t("How many sources must agree on a track before it's used. If too few agreed tracks "
                           "are in your library, the agreement is relaxed a step at a time, and the log says so.")
                      ).pack(side="left", padx=(8, 0))
            self._inner_circle_section(p, pages["tracks"], "tracks")
            self._moderator_section(p, pages["tracks"], "tracks")

        # --- Artist's Top Tracks ---
        if kind == "top":
            box = section(pages["top"], t("Sources"),
                          t("More services means richer, more varied playlists, but slower; fewer is quicker. "
                               "ListenBrainz is the slowest source on a first run, because its lookups are limited "
                          "to one a second. Repeat runs are quick."))
            self._source_ticks(p, box, 0, "TOP_TRACK_SOURCES", TOP_SOURCE_NAMES, "lastfm", p.save, "top")

        p.resync = lambda: (sync_agreement(p, "SIMILAR_SOURCES", "SIMILAR_MIN_AGREEMENT", "agree_cb", 5),
                            sync_agreement(p, "SIMILAR_TRACK_SOURCES", "SIMILAR_TRACK_MIN_AGREEMENT",
                                           "track_agree_cb", 99),
                            self._sync_moderator_box(p), self._sync_listenbrainz(p))
        p.resync()
        p.loading = False
        self._watch_source_test()   # the scores, the notice and the buttons, and a running test followed

    def _on_console_query_toggled(self):
        """Ticking Console Query asks first; with no AI set up, or on Ollama, it explains and stays off."""
        var = self.vars["CONSOLE_QUERY"]
        if var.get():
            if not self._ai_set_up():
                messagebox.showinfo(t("Console Query"), t(NO_KEY_TEXT), parent=self)
                var.set(False)
            elif self._ai_provider() == "ollama":
                messagebox.showinfo(t("Console Query"), t("Console Query isn't available with Ollama: it sends the "
                                    "console and 24bit7's code, far more than a local model can hold."), parent=self)
                var.set(False)
            elif not messagebox.askyesno(t("Console Query"), t(CONSOLE_QUERY_WARNING), parent=self):
                var.set(False)
        self._save()

    def _ai_provider(self):
        """The provider chosen under Settings > Keys > AI (the saved one until that page is built)."""
        var = getattr(self, "ai_provider_var", None)
        return option_code(engine.AI_PROVIDERS, var.get()) if var is not None else engine.AI_PROVIDER

    def _ai_set_up(self):
        """True when the chosen provider has what it needs (its key, or Ollama's model), a key just typed included."""
        provider = self._ai_provider()
        var = self.vars.get(AI_FIELDS[provider][-1])
        typed = var.get().strip() if var is not None else ""
        return bool(typed) or (provider == engine.AI_PROVIDER and engine.ai_configured())

    def _sync_moderator_box(self, p):
        """Every Moderator tick is greyed out until the AI is set up (Settings > Keys)."""
        for tick in getattr(p, "moderator_boxes", []):
            tick.state(["!disabled"] if self._ai_set_up() else ["disabled"])

    # --- the Playlist sections ---

    def _fill_playlist(self, tab, p, kind, parts=None, where_=None):
        """
        A config's settings for its kind: the playlist itself, then Drift, Deep Cuts, Non-stop,
        Hidden Tracks, If All Else Fails and Run After Building, each in its own box. parts (English
        titles) says which boxes to show; the rest are built out of sight, so the page's values stay
        whole. where_ maps a title to the frame it goes in (the whole-playlist area under the configs).
        """
        p.loading = True
        void = tk.Frame(tab)   # never gridded: the boxes another config's block shows instead
        allowed = None if parts is None else {t(x) for x in parts}
        targets = {t(k): v for k, v in (where_ or {}).items()}
        p.drift = {}           # group -> (on, using, rounds, (dropdowns))
        p.drift_warn = {}      # group -> the Same as Settings > Sources note
        p.drift_src = {}       # group -> (mode, its row, the Custom Sources panel, {kind: frame})
        p.played_boxes = {}    # group -> its days box
        p.closer_sbs = {}      # GROUP -> its minutes box
        p.nonstop_parts = {}   # GROUP -> (its choices, the song-count dropdown or None)
        pages = {kind: tab}
        nonstop_cfg = engine.nonstop_settings(p.env.get)
        closer_cfg = engine.closer_settings(p.env.get)
        where = {}     # the box being filled and its next row

        def begin(group, title, help_text=None):
            if allowed is not None and title not in allowed:
                parent = void
            else:
                parent = targets.get(title) or pages[group]
            where["box"], where["r"] = section(parent, title, help_text), 0

        def place(widget, pady=4):
            """Puts a label-less row (a tick box and friends) across the box."""
            widget.grid(row=where["r"], column=0, columnspan=3, sticky="w", pady=pady)
            where["r"] += 1

        review = {"same": {}, "boxes": {}}   # a standard button: Review Mode's Mirror ticks and its spinboxes
        review_fg = "#f28c28" if engine.THEME == "dark" else "#a85400"   # Review Mode's orange, as on the Play tab
        ROW_PAD = 7   # a little more room between rows than other pages: four columns are a lot to scan

        def review_header(group):
            """Current Track | Review Mode column headings, with Review Mode's Mirror tick (standard button only)."""
            if not p.columns:
                return
            box, r = where["box"], where["r"]
            tk.Label(box, text=t("Current Track"), font=LABEL_FONT, fg=PALETTE["help_fg"]).grid(
                row=r, column=1, sticky="w", padx=(12, 0))
            cell = tk.Frame(box)
            cell.grid(row=r, column=2, sticky="w", padx=(24, 0))
            var = tk.BooleanVar(value=read_env().get(f"REVIEW_SAME_{group.upper()}", "1").strip().lower()
                                not in ("0", "false", "no"))
            review["same"][group] = var
            title = tk.Label(cell, text=t("Review Mode"), font=LABEL_FONT, fg=review_fg)
            title.pack(side="left", padx=(0, 10))
            ttk.Checkbutton(cell, text=t("Mirror Current Track"), variable=var).pack(side="left")
            var.trace_add("write", lambda *a, g=group: review_same_changed(g))   # saves however it's changed
            help_mark(cell, t("In Review Mode you're choosing from a list, so a shortlist is often better than a "
                            "full playlist. Untick Mirror Current Track to give Review Mode its own figures "
                            "for this section; everything else here (sources, Drift, hidden tracks) is shared. "
                            "Standard button only, as voice builds never review."), on=title)
            where["r"] += 1

        def seed_header(group):
            """
            The four columns for Similar Artists and Similar Tracks (standard button only): Seed over Current Track and
            Playing Now, Review Mode over its own Current Track and Playing Now, each Review Mode column with
            a Mirror tick above its heading.
            """
            if not p.columns:
                return
            box, r = where["box"], where["r"]
            for text, col, colour in ((t("SEED"), 1, PALETTE["help_fg"]), (t("REVIEW MODE"), 3, review_fg)):
                cell = tk.Frame(box)
                cell.grid(row=r, column=col, columnspan=2, sticky="ew", padx=(12 if col == 1 else 24, 0),
                          pady=(0, 6))
                tk.Label(cell, text=text, font=("Segoe UI", 8, "bold"), fg=colour).pack(anchor="w")
                tk.Frame(cell, height=1, bg=colour).pack(fill="x")
            for col, key, text in ((3, f"REVIEW_SAME_{group.upper()}", t("Mirror Current Track")),
                                   (4, f"REVIEW_SAME_{group.upper()}_PN", t("Mirror Playing Now"))):
                var = tk.BooleanVar(value=read_env().get(key, "1").strip().lower() not in ("0", "false", "no"))
                name = group if col == 3 else f"{group}_pn"
                review["same"][name] = var
                ttk.Checkbutton(box, text=text, variable=var).grid(row=r + 1, column=col, sticky="w",
                                                                   padx=(24, 0))
                var.trace_add("write", lambda *a, g=name, k=key: review_same_changed(g, k))
            heads = ((1, t("Current Track"), PALETTE["help_fg"]), (2, t("Playing Now"), PALETTE["help_fg"]),
                     (3, t("Current Track"), review_fg), (4, t("Playing Now"), review_fg))
            for col, text, colour in heads:
                label = tk.Label(box, text=text, font=LABEL_FONT, fg=colour)
                label.grid(row=r + 2, column=col, sticky="w", padx=(12 if col == 1 else 24, 0), pady=(10, 4))
                if col == 2:
                    help_mark(box, t("Playing Now: the Play tab's Seed set to Playing Now. A few artists or tracks "
                                   "are picked at random from the whole list, and each in turn brings its own "
                                   "share of similar ones, so the results are usually broader than Current "
                                   "Track. Tracks already in Playing Now are left out. Standard button only."),
                              on=label)
                if col == 3:
                    help_mark(box, t("In Review Mode you're choosing from a list, so a shortlist is often better "
                                   "than a full playlist. Untick a Mirror tick to give Review Mode its own "
                                   "figures for that seed; everything else here (sources, Drift, hidden "
                                   "tracks) is shared. Standard button only, as voice builds never review."),
                              on=label)
            where["r"] += 3

        def review_same_changed(group, key=None):
            same = review["same"][group].get()
            write_env({key or f"REVIEW_SAME_{group.upper()}": "1" if same else "0"})
            for sb in review["boxes"].get(group, []):
                sb.config(state="disabled" if same else "normal")

        def review_twin(group, key, default, lo, hi, row=None, col=2):
            """A Review Mode spinbox for key, saved as REVIEW_<key> (standard button only)."""
            if not p.columns:
                return None
            box = where["box"]
            r = where["r"] - 1 if row is None else row
            rkey = f"REVIEW_{key}"
            var = tk.StringVar(value=read_env().get(rkey, "").strip() or read_env().get(key, "").strip()
                               or p.env.get(key, default))
            cell = tk.Frame(box)
            cell.grid(row=r, column=col, sticky="w", padx=(24, 0), pady=ROW_PAD)
            sb = tk.Spinbox(cell, from_=lo, to=hi, textvariable=var, width=6,
                            command=lambda k=rkey, v=var: write_env({k: v.get().strip()}))
            sb.pack(side="left")
            var.trace_add("write", lambda *a, k=rkey, v=var: write_env({k: v.get().strip()}))
            review["boxes"].setdefault(group, []).append(sb)
            if review["same"].get(group) is not None and review["same"][group].get():
                sb.config(state="disabled")
            return cell

        def pn_cell(key, default, lo, hi, row=None, note=None):
            """A Playing Now spinbox for key (PN_...), saved straight to .env (standard button only)."""
            if not p.columns:
                return None
            box = where["box"]
            r = where["r"] - 1 if row is None else row
            var = tk.StringVar(value=read_env().get(key, "").strip() or default)
            cell = tk.Frame(box)
            cell.grid(row=r, column=2, sticky="w", padx=(24, 0), pady=ROW_PAD)
            tk.Spinbox(cell, from_=lo, to=hi, textvariable=var, width=6,
                       command=lambda k=key, v=var: write_env({k: v.get().strip()})).pack(side="left")
            var.trace_add("write", lambda *a, k=key, v=var: write_env({k: v.get().strip()}))
            if note:
                tk.Label(cell, text=note, fg=PALETTE["help_fg"]).pack(side="left", padx=(8, 0))
            return cell

        def limit_tick(cell, key, group=None):
            """A Limit tick after a column's number, saved as key ("1" or "0"), ticked to start."""
            var = tk.BooleanVar(value=read_env().get(key, "1").strip().lower() in ("1", "true", "yes"))
            tick = ttk.Checkbutton(cell, text=t("Limit"), variable=var)
            var.trace_add("write", lambda *a: write_env({key: "1" if var.get() else "0"}))
            tick.pack(side="left", padx=(8, 0))
            if group is not None:
                review["boxes"].setdefault(group, []).append(tick)
                if review["same"].get(group) is not None and review["same"][group].get():
                    tick.config(state="disabled")
            return var

        def spin(label, key, default, lo, hi, help_text=None):
            box, r = where["box"], where["r"]
            tk.Label(box, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=ROW_PAD)
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

        def label_row(label, help_text=None):
            """A row title with nothing under Current Track (a Playing Now-only row). Returns its grid row."""
            box, r = where["box"], where["r"]
            title = tk.Label(box, text=label, anchor="w")
            title.grid(row=r, column=0, sticky="w", pady=ROW_PAD)
            if help_text:
                help_mark(box, help_text, on=title)
            where["r"] += 1
            return r

        def choice(label, key, default, values, help_text=None, note=None):
            box, r = where["box"], where["r"]
            tk.Label(box, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=ROW_PAD)
            p.vars[key] = tk.StringVar(value=p.env.get(key, default))
            cell = tk.Frame(box)
            cell.grid(row=r, column=1, columnspan=4, sticky="w", padx=(12, 0))
            cb = TCombobox(cell, textvariable=p.vars[key], values=values, state="readonly", width=12)
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", p.save)
            if help_text:
                help_mark(cell, help_text).pack(side="left", padx=(8, 0))
            if note and p.columns:
                tk.Label(cell, text=note, fg=PALETTE["help_fg"]).pack(side="left", padx=(10, 0))
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
            ttk.Checkbutton(row, text=t("Skip tracks played in the last"), variable=p.vars[name],
                            command=toggled).pack(side="left")
            days = tk.Spinbox(row, from_=1, to=365, textvariable=p.vars[f"{name}_DAYS"], width=4, command=p.save)
            days.pack(side="left", padx=(6, 6))
            tk.Label(row, text=t("days")).pack(side="left")
            help_mark(row, t("Leaves out anything JRiver has played within that many days, using its Last "
                           "Played date. The seed track is never left out. JRiver's library is re-read every "
                           "half hour, so a track played in the last few minutes may still get in. Drift, if "
                           "it's on, fills any gaps this leaves.")).pack(side="left", padx=(8, 0))
            p.vars[f"{name}_DAYS"].trace_add("write", p.save)
            p.played_boxes[group] = days
            place(row, pady=(8, 4))

        def drift(group):
            """The Drift section: its tick box, then Drift using and Rounds."""
            note = t("If a playlist comes up short, search again using what's already been found, "
                    "until the playlist reaches its length. More rounds fill more gaps but can "
                    "wander further from where you started.")
            if group == "vibe":
                note = t("Tops the playlist up from your music sources (Last.fm and the others you've ticked), "
                        "not the AI, unless Drift using is set to AI. AI asks again with your description, "
                        "leaving out what's already been found or tried, and uses a little AI credit "
                        "each round (none with Ollama).")
            begin(group, t("Drift"), note)
            box = where["box"]
            cfg = drift_values(p.env, group)
            on = tk.BooleanVar(value=cfg["on"])
            using = tk.StringVar(value=option_label(drift_using_options(group), cfg["using"]))
            rounds = tk.StringVar(value=str(cfg["rounds"]))

            def toggled():
                sync_drift(p)
                p.save()
            # One dropdown: Off, Keep It Tight or Spread. on and DRIFT_<G>_FROM follow it.
            name = f"DRIFT_{group.upper()}"
            frm = "close" if p.env.get(f"{name}_FROM", "spread").strip().lower() == "close" else "spread"
            p.vars[f"{name}_FROM"] = tk.StringVar(value=frm)
            drift_mode_var = tk.StringVar(value=option_label(DRIFT_MODE_OPTIONS, frm if cfg["on"] else "off"))
            top = tk.Frame(box)
            tk.Label(top, text=t("Drift")).pack(side="left")
            drift_mode_cb = TCombobox(top, textvariable=drift_mode_var, state="readonly", width=14,
                                         values=[s for _, s in DRIFT_MODE_OPTIONS])
            drift_mode_cb.pack(side="left", padx=(6, 0))

            def mode_chosen(_e=None, cb=drift_mode_cb, var=drift_mode_var, key=f"{name}_FROM", on=on):
                cb.selection_clear()
                code = option_code(DRIFT_MODE_OPTIONS, var.get())
                on.set(code != "off")
                if code != "off":
                    p.vars[key].set(code)
                toggled()
            drift_mode_cb.bind("<<ComboboxSelected>>", mode_chosen)
            help_mark(top, t(DRIFT_MODE_HELP)).pack(side="left", padx=(8, 0))
            place(top, pady=(0, 4))
            if not hasattr(p, "drift_modes"):
                p.drift_modes = {}
            p.drift_modes[group] = drift_mode_var
            row = tk.Frame(box)
            tk.Label(row, text=t("Drift using")).pack(side="left")
            choices = drift_using_options(group)
            using_cb = TCombobox(row, textvariable=using, values=[shown for _, shown in choices],
                                    state="readonly", width=max(22 if group == "vibe" else 14,
                                                                max(len(t(shown)) for _, shown in choices) + 1))
            using_cb.pack(side="left", padx=(6, 18))
            tk.Label(row, text=t("Rounds")).pack(side="left")
            rounds_cb = TCombobox(row, textvariable=rounds, values=[str(n) for n in range(1, 7)],
                                     state="readonly", width=3)
            rounds_cb.pack(side="left", padx=(6, 0))
            for cb in (using_cb, rounds_cb):
                cb.bind("<<ComboboxSelected>>", p.save)
            place(row, pady=(0, 4))
            drift_mod_cb = None
            if group != "vibe":   # AI Playlist has its own, below
                dm_row = tk.Frame(box)
                tk.Label(dm_row, text=t("Moderator on Drift tracks"), fg=PALETTE["ai_purple"]).pack(side="left")
                p.vars[f"{name}_MODERATOR"] = tk.StringVar(value=option_label(
                    DRIFT_MODERATOR_OPTIONS, p.env.get(f"{name}_MODERATOR", "same").strip().lower()))
                drift_mod_cb = TCombobox(dm_row, textvariable=p.vars[f"{name}_MODERATOR"],
                                            values=[s for _, s in DRIFT_MODERATOR_OPTIONS], state="readonly",
                                            width=14)
                drift_mod_cb.pack(side="left", padx=(6, 0))

                def dm_chosen(e, cb=drift_mod_cb, key=f"{name}_MODERATOR"):
                    cb.selection_clear()
                    if option_code(DRIFT_MODERATOR_OPTIONS, p.vars[key].get()) not in ("same", "off"):
                        warn_moderator_once(self)
                    p.save()
                drift_mod_cb.bind("<<ComboboxSelected>>", dm_chosen)
                help_mark(dm_row, t("Checks the tracks each Drift round adds. Same as build uses the Moderator level of the build itself; a stronger level here checks Drift harder than the first round. When most of what one seed brought in is off course, the rest of it goes too and Drift doesn't seed from that chain again.") + "\n" + t(MODERATOR_LEVELS_HELP)).pack(side="left", padx=(8, 0))
                Tooltip(drift_mod_cb, t(NO_KEY_TEXT), when=lambda: not self._ai_set_up())
                place(dm_row, pady=(0, 4))
            # Drift sources: the same as Settings > Sources, or Custom Sources of its own
            name = f"DRIFT_{group.upper()}"
            mode = tk.StringVar(value=option_label(
                DRIFT_SOURCE_MODES, p.env.get(f"{name}_SOURCES_MODE", "same").strip().lower()))
            p.vars[f"{name}_SOURCES_MODE"] = mode
            mode_row = tk.Frame(box)
            tk.Label(mode_row, text=t("Drift sources")).pack(side="left")
            mode_cb = TCombobox(mode_row, textvariable=mode, values=[s for _, s in DRIFT_SOURCE_MODES],
                                   state="readonly", width=26)
            mode_cb.pack(side="left", padx=(6, 0))
            help_mark(mode_row, t(DRIFT_SOURCES_HELP)).pack(side="left", padx=(8, 0))
            place(mode_row, pady=(0, 4))
            if group in ("artists", "tracks"):   # an empty build is only picked up with Custom Sources
                warn = tk.Label(box, text=t(DRIFT_SAME_WARNING), fg=PALETTE["text_secondary"], font=HELP_FONT,
                                wraplength=scaled(box, 440), justify="left")
                place(warn, pady=(0, 4))
                warn.grid_configure(padx=(16, 0))
                follow_width(warn, box, minimum=440)
                p.drift_warn[group] = warn
            panel = tk.Frame(box)
            frames = {}
            for kind, names, agree_values, main in (
                    ("ARTIST", DRIFT_ARTIST_SOURCE_NAMES, [N_("Off"), "2", "3", "4"],
                     [c for c in engine.SIMILAR_SOURCES if c != "ai"]),
                    ("TRACK", [s for s in TRACK_SOURCE_NAMES if s[0] != "ai"], [N_("Off"), "2", "3"],
                     [c for c in engine.SIMILAR_TRACK_SOURCES if c != "ai"])):
                frame = tk.Frame(panel)
                tk.Label(frame, text=t("Similar artists from") if kind == "ARTIST" else t("Similar tracks from"),
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
                tk.Label(agree_row, text=t("Sources that must agree")).pack(side="left")
                start = p.env.get(f"{name}_{kind}_AGREE", "1").strip() or "1"
                agree = tk.StringVar(value="Off" if start in ("0", "1") else start)
                p.vars[f"{name}_{kind}_AGREE"] = agree
                agree_cb = TCombobox(agree_row, textvariable=agree, values=agree_values, state="readonly",
                                        width=6)
                agree_cb.pack(side="left", padx=(6, 0))
                agree_cb.bind("<<ComboboxSelected>>", p.save)
                help_mark(agree_row, t("How many of the ticked sources must agree before Drift uses a suggestion. "
                                     "It can't be more than the sources that answer.")).pack(side="left", padx=(8, 0))
                frames[kind] = frame
            place(panel, pady=(0, 4))
            panel.grid_configure(padx=(16, 0))
            p.drift[group] = (on, using, rounds, tuple(cb for cb in (using_cb, rounds_cb, mode_cb, drift_mod_cb)
                                                                if cb is not None))
            p.drift_src[group] = (mode, mode_row, panel, frames)

            def sources_changed(*_):
                mode_cb.selection_clear()
                sync_drift(p)
                p.save()
            mode_cb.bind("<<ComboboxSelected>>", sources_changed)
            using_cb.bind("<<ComboboxSelected>>", lambda e: sync_drift(p), add="+")
            if group == "vibe":   # AI Playlist: a Moderator for what Drift adds from the sources
                mod_row = tk.Frame(box)
                tk.Label(mod_row, text=t("Moderator on Drift tracks"), fg=PALETTE["ai_purple"]).pack(side="left")
                p.vars["AI_MODERATOR_VIBE"] = tk.StringVar(
                    value=engine.moderator_settings(p.env.get)["vibe"].title())
                mod_cb = TCombobox(mod_row, textvariable=p.vars["AI_MODERATOR_VIBE"], values=MODERATOR_CHOICES,
                                      state="readonly", width=9)
                mod_cb.pack(side="left", padx=(6, 0))

                def mod_chosen(*_):
                    if p.vars["AI_MODERATOR_VIBE"].get() != "Off":
                        warn_moderator_once(self)
                    mod_cb.selection_clear()
                    p.save()
                mod_cb.bind("<<ComboboxSelected>>", mod_chosen)
                using_cb.bind("<<ComboboxSelected>>", lambda e: sync_drift(p), add="+")
                help_mark(mod_row, t("Checks the tracks Drift adds from similar artists or similar tracks against your description, and removes any that clash. The AI's own picks are never checked. Only works when Drift is on and not using the AI.") + "\n" + t(MODERATOR_LEVELS_HELP)).pack(side="left", padx=(8, 0))
                Tooltip(mod_cb, t(NO_KEY_TEXT), when=lambda: not self._ai_set_up())
                place(mod_row, pady=(0, 4))
                p.vibe_mod_cb = mod_cb

        def deep_cuts(group):
            """The Deep Cuts section: the switch (Off, Spaced or Shuffled) and how much to top up by."""
            g = group.upper()
            try:
                share = min(100, max(10, int(p.env.get(f"DEEP_CUTS_{g}_SHARE") or 10) // 10 * 10))
            except ValueError:
                share = 10
            if group == "artists":
                what = t("Tops the playlist up with the artists in the seed's genre you've played least lately, "
                         "then their top tracks, so the corners of your collection get a turn.")
            elif group == "vibe":
                what = t("Tops the playlist up with the tracks in the seed's genre you've played least (the genre "
                         "most of the AI's picks share, as there's no seed track), so the corners of your "
                         "collection get a turn.")
            else:
                what = t("Tops the playlist up with the tracks in the seed's genre you've played least, so the "
                         "corners of your collection get a turn.")
            switch = t("Switch it on, Spaced or Shuffled, here.")
            begin(group, t("Deep Cuts"),
                  what + " " + switch + " " + t("The genre comes from your own Genre tags, so this works best when "
                                                "they're well organised."))
            row = tk.Frame(where["box"])
            mode = (p.env.get(f"DEEP_CUTS_{g}") or "off").strip().lower()
            tk.Label(row, text=t("Deep Cuts")).pack(side="left")
            p.vars[f"DEEP_CUTS_{g}"] = tk.StringVar(
                value=option_label(DEVICE_DEEP_CUTS, mode if mode in engine.DEEP_CUT_MODES else "off"))
            mode_cb = TCombobox(row, textvariable=p.vars[f"DEEP_CUTS_{g}"],
                                   values=[shown for _, shown in DEVICE_DEEP_CUTS], state="readonly", width=12)
            mode_cb.pack(side="left", padx=(6, 24))
            title = tk.Label(row, text=t("Top Up with Deep Cuts by"))
            title.pack(side="left")
            Tooltip(title, t("How many deep cuts, as a share of the playlist, added on top of it: 10% of "
                           "30 tracks adds 3; 100% adds as many again, an even mix."))
            p.vars[f"DEEP_CUTS_{g}_SHARE"] = tk.StringVar(value=str(share))
            share_sb = tk.Spinbox(row, from_=10, to=100, increment=10, width=5, state="readonly",
                                  textvariable=p.vars[f"DEEP_CUTS_{g}_SHARE"], command=p.save)
            share_sb.pack(side="left", padx=(6, 0))
            tk.Label(row, text="%").pack(side="left", padx=(2, 0))
            if mode_cb is not None:
                def chosen(_e=None, cb=mode_cb, sb=share_sb, key=f"DEEP_CUTS_{g}"):
                    cb.selection_clear()
                    off = option_code(DEVICE_DEEP_CUTS, p.vars[key].get()) == "off"
                    sb.config(state="disabled" if off else "readonly")
                mode_cb.bind("<<ComboboxSelected>>", lambda e: (chosen(), p.save()))
                chosen()
            place(row, pady=(0, 4))

        def nonstop(group):
            """The Non-stop section: its tick box, then how this option's playlists carry on."""
            g, cfg = group.upper(), nonstop_cfg[group]
            begin(group, t("Non-stop"),
                  t("When the last track of a playlist 24bit7 built starts playing, more are added to the end, "
                  "so the music doesn't stop. A playlist keeps following these settings all evening, even "
                  "after it carries on as Similar Tracks or Similar Artists. Only playlists 24bit7 sent are "
                  "topped up: an album or playlist you start in JRiver yourself ends as normal."))
            box = where["box"]
            p.vars[f"NONSTOP_{g}"] = tk.BooleanVar(value=cfg["on"])
            p.vars[f"NONSTOP_{g}_MODE"] = tk.StringVar(value=cfg.get("mode", "journey"))

            def toggled():
                sync_nonstop(p)
                p.save()
            # One dropdown: Off, Keep It Tight or Wander
            ns_var = tk.StringVar(value=option_label(NONSTOP_MODE_OPTIONS,
                                                     cfg.get("mode", "journey") if cfg["on"] else "off"))
            top_row = tk.Frame(box)
            tk.Label(top_row, text=t("Non-stop")).pack(side="left")
            ns_cb = TCombobox(top_row, textvariable=ns_var, values=[s for _, s in NONSTOP_MODE_OPTIONS],
                                 state="readonly", width=24)
            ns_cb.pack(side="left", padx=(6, 0))

            def ns_chosen(_e=None, cb=ns_cb, var=ns_var, g=g):
                cb.selection_clear()
                code = option_code(NONSTOP_MODE_OPTIONS, var.get())
                p.vars[f"NONSTOP_{g}"].set(code != "off")
                if code != "off":
                    p.vars[f"NONSTOP_{g}_MODE"].set(code)
                toggled()
            ns_cb.bind("<<ComboboxSelected>>", ns_chosen)
            help_mark(top_row, t(NONSTOP_MODE_HELP)).pack(side="left", padx=(8, 0))
            place(top_row, pady=(0, 2))
            if not hasattr(p, "nonstop_modes"):
                p.nonstop_modes = {}
            p.nonstop_modes[g] = ns_var
            body = tk.Frame(box)
            place(body, pady=(0, 4))
            rows = {"r": 0}

            def option(label, key, options, current, help_text):
                r = rows["r"]
                tk.Label(body, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
                p.vars[key] = tk.StringVar(value=option_label(options, current))
                cell = tk.Frame(body)
                cell.grid(row=r, column=1, sticky="w", padx=(12, 0))
                cb = TCombobox(cell, textvariable=p.vars[key], values=[shown for _, shown in options],
                                  state="readonly", width=22)
                cb.pack(side="left")
                cb.bind("<<ComboboxSelected>>", p.save)
                help_mark(cell, help_text).pack(side="left", padx=(8, 0))
                rows["r"] += 1
                return cb

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
                ttk.Checkbutton(row, text=t("First, the rest of the artist, up to"),
                                variable=p.vars["NONSTOP_TOP_REST"], command=rest_toggled).pack(side="left")
                rest_cb = TCombobox(row, textvariable=p.vars["NONSTOP_TOP_REST_COUNT"],
                                       values=["10", "20", "30", "50", "100", N_("Unlimited")],
                                       state="readonly", width=10)
                rest_cb.pack(side="left", padx=(6, 6))
                rest_cb.bind("<<ComboboxSelected>>", p.save)
                tk.Label(row, text=t("songs")).pack(side="left")
                help_mark(row, t("When the top tracks finish, the artist's other songs in your library play "
                               "next, shuffled. After that, their most popular track seeds a new playlist. "
                               "Unticked, it goes straight to the new playlist.")).pack(side="left", padx=(8, 0))
            if group == "vibe":
                option(t("Continues with"), "NONSTOP_VIBE_WITH", NONSTOP_WITH_OPTIONS, cfg["with"],
                       t("More from the AI asks the AI again with the original description (a little "
                       "AI credit each time, none with Ollama). Similar artists or Similar tracks carry on "
                       "from the "
                       "music, with no credit used."))
            else:
                option(t("Then play using") if group == "top" else t("Play using"), f"NONSTOP_{g}_USING",
                       NONSTOP_USING_OPTIONS, cfg["using"], t("What each top-up is built with."))
            reseed_cb = option(t("Reseed from"), f"NONSTOP_{g}_RESEED", NONSTOP_RESEED_OPTIONS, cfg["reseed"],
                               t("For Wander. Last track: each top-up follows on from where "
                               "the music has got to, so it wanders as the evening goes on.\nSecond track: each "
                               "top-up seeds from the first pick after the original seed, so it stays closer to "
                               "how it started. Keep It Tight doesn't use this."))
            p.nonstop_parts[g] = (body, rest_cb)
            if not hasattr(p, "nonstop_reseed"):
                p.nonstop_reseed = {}
            p.nonstop_reseed[g] = reseed_cb

        def hidden(group):
            """The Hidden Tracks section for one Play option."""
            g = group.upper()
            on, minutes = closer_cfg[group]
            begin(group, t("Hidden Tracks"))
            row = tk.Frame(where["box"])
            p.vars[f"SKIP_LONG_CLOSERS_{g}"] = tk.BooleanVar(value=on)
            p.vars[f"LONG_CLOSER_MINUTES_{g}"] = tk.StringVar(value=str(minutes))
            sb = tk.Spinbox(row, from_=3, to=30, textvariable=p.vars[f"LONG_CLOSER_MINUTES_{g}"],
                            width=4, command=p.save)

            def toggled():
                sync_long_closers(p)
                p.save()
            ttk.Checkbutton(row, text=t("Skip the last track on an album if it's longer than"),
                            variable=p.vars[f"SKIP_LONG_CLOSERS_{g}"], command=toggled).pack(side="left")
            sb.pack(side="left", padx=(6, 6))
            tk.Label(row, text=t("minutes")).pack(side="left")
            help_mark(row, t("Long album closers often hide a bonus track after a long silence. Albums, songs "
                           "and playlists you ask for by name always play in full.")).pack(side="left", padx=(8, 0))
            p.vars[f"LONG_CLOSER_MINUTES_{g}"].trace_add("write", p.save)
            p.closer_sbs[g] = sb
            place(row)

        def fallback(group):
            """The If All Else Fails section: when a build finds nothing, shuffle, run a file or play a playlist."""
            key = f"IF_ALL_ELSE_FAILS_{group.upper()}"
            begin(group, t("If All Else Fails"))
            p.vars[key] = tk.BooleanVar(value=str(p.env.get(key, "0")).strip().lower() in ("1", "true", "yes"))
            mode = tk.StringVar(value=option_label(FALLBACK_MODE_OPTIONS,
                                                   p.env.get(f"{key}_MODE", "shuffle").strip().lower()))
            p.vars[f"{key}_MODE"] = mode
            for part in ("PATH", "PLAYLIST", "PLAYLIST_NAME"):
                p.vars[f"{key}_{part}"] = tk.StringVar(value=p.env.get(f"{key}_{part}", ""))
            shown = tk.StringVar(value=p.vars[f"{key}_PLAYLIST_NAME"].get() or t(NO_PLAYLIST))
            row = tk.Frame(where["box"])
            ttk.Checkbutton(row, text=t("If nothing is found"), variable=p.vars[key],
                            command=lambda: changed()).pack(side="left")
            mode_cb = TCombobox(row, textvariable=mode, values=[s for _, s in FALLBACK_MODE_OPTIONS],
                                   state="readonly", width=14)
            mode_cb.pack(side="left", padx=(8, 0))
            help_mark(row, t(FALLBACK_HELP)).pack(side="left", padx=(8, 0))
            place(row)
            file_row = tk.Frame(where["box"])
            entry = tk.Entry(file_row, textvariable=p.vars[f"{key}_PATH"], width=48)
            entry.pack(side="left", padx=(0, 4))
            entry.bind("<FocusOut>", p.save)

            def browse():
                path = filedialog.askopenfilename(
                    parent=self, title=t("If All Else Fails"),
                    filetypes=[(t("Programs and scripts"), "*.bat *.cmd *.exe *.ps1 *.py *.pyw"), (t("All files"), "*.*")])
                if path:
                    p.vars[f"{key}_PATH"].set(os.path.normpath(path))
                    p.save()
            ttk.Button(file_row, text=t("Browse..."), command=browse).pack(side="left")
            place(file_row, pady=(0, 4))
            file_row.grid_configure(padx=(16, 0))
            list_row = tk.Frame(where["box"])
            tk.Label(list_row, textvariable=shown).pack(side="left", padx=(0, 8))

            def picked(item):
                p.vars[f"{key}_PLAYLIST"].set(str(item["ID"]))
                p.vars[f"{key}_PLAYLIST_NAME"].set(item["Name"])
                shown.set(item["Name"])
                p.save()
            ttk.Button(list_row, text=t("Choose..."), command=lambda: choose_playlist(self, picked)).pack(side="left")
            place(list_row, pady=(0, 4))
            list_row.grid_configure(padx=(16, 0))
            if "FALLBACK_SPOKEN" not in p.vars:   # one setting, shown in each playlist type's section
                p.vars["FALLBACK_SPOKEN"] = tk.BooleanVar(
                    value=str(p.env.get("FALLBACK_SPOKEN", "0")).strip().lower() in ("1", "true", "yes"))
            spoken_row = tk.Frame(where["box"])
            spoken_tick = ttk.Checkbutton(spoken_row, text=t("Say why in the room first"),
                                          variable=p.vars["FALLBACK_SPOKEN"], command=lambda: p.save())
            spoken_tick.pack(side="left")
            help_mark(spoken_row, t(SPOKEN_HELP)).pack(side="left", padx=(8, 0))
            place(spoken_row, pady=(0, 4))
            spoken_row.grid_configure(padx=(16, 0))

            def sync():
                on, code = p.vars[key].get(), option_code(FALLBACK_MODE_OPTIONS, mode.get())
                mode_cb.config(state="readonly" if on else "disabled")
                spoken_tick.config(state="normal" if on else "disabled")
                file_row.grid() if on and code == "file" else file_row.grid_remove()
                list_row.grid() if on and code == "playlist" else list_row.grid_remove()

            def changed(*_):
                mode_cb.selection_clear()
                sync()
                p.save()
            mode_cb.bind("<<ComboboxSelected>>", changed)
            sync()

        def run_after(group):
            """The Run After Building section: a file to run once the playlist is in JRiver."""
            key = f"RUN_AFTER_{group.upper()}"
            begin(group, t("Run After Building"))
            p.vars[key] = tk.BooleanVar(value=p.env.get(key, "0") in ("1", "true", "yes"))
            p.vars[f"{key}_PATH"] = tk.StringVar(value=p.env.get(f"{key}_PATH", ""))
            row = tk.Frame(where["box"])
            ttk.Checkbutton(row, text=t("Run this file after building"), variable=p.vars[key],
                            command=p.save).pack(side="left")
            entry = tk.Entry(row, textvariable=p.vars[f"{key}_PATH"], width=48)
            entry.pack(side="left", padx=(8, 4))
            entry.bind("<FocusOut>", p.save)

            def browse():
                path = filedialog.askopenfilename(
                    parent=self, title=t("Run after building"),
                    filetypes=[(t("Programs and scripts"), "*.bat *.cmd *.exe *.ps1 *.py *.pyw"), (t("All files"), "*.*")])
                if path:
                    p.vars[f"{key}_PATH"].set(os.path.normpath(path))
                    p.vars[key].set(True)
                    p.save()
            ttk.Button(row, text=t("Browse..."), command=browse).pack(side="left")
            help_mark(row, t("Runs the file once the playlist is in JRiver, added playlists included, and only "
                           "if the build worked. It runs in the background and isn't told anything about the "
                           "playlist. A .bat, .exe, PowerShell or Python script all work. Non-stop top-ups "
                           "don't run it.")).pack(side="left", padx=(8, 0))
            place(row)

        # --- Similar Artists ---
        if kind == "artists":
            begin("artists", t("Playlist"))
            seed_header("artists")
            # Limit total tracks to: a tick box in the label column, the number beside it
            box, r = where["box"], where["r"]
            limit_var = tk.BooleanVar(value=p.env.get("SIMILAR_ARTIST_TRACK_LIMIT", "1") in ("1", "true", "yes"))
            p.vars["SIMILAR_ARTIST_TRACK_LIMIT"] = limit_var
            p.vars["SIMILAR_ARTIST_TRACK_COUNT"] = tk.StringVar(value=p.env.get("SIMILAR_ARTIST_TRACK_COUNT", "30"))
            cell = tk.Frame(box)
            cell.grid(row=r, column=1, sticky="w", padx=(12, 0))
            limit_sb = tk.Spinbox(cell, from_=5, to=100, textvariable=p.vars["SIMILAR_ARTIST_TRACK_COUNT"],
                                  width=6, command=p.save)
            limit_sb.pack(side="left")
            help_mark(cell, t(LIMIT_HELP)).pack(side="left", padx=(8, 0))

            def limit_toggled(save=True):
                limit_sb.config(state="normal" if limit_var.get() else "disabled")
                if save:
                    p.save()
            ttk.Checkbutton(box, text=t("Limit total tracks to"), variable=limit_var,
                            command=limit_toggled).grid(row=r, column=0, sticky="w", pady=ROW_PAD)
            limit_toggled(save=False)
            p.vars["SIMILAR_ARTIST_TRACK_COUNT"].trace_add("write", p.save)
            pcell = pn_cell("PN_SIMILAR_ARTIST_TRACK_COUNT", "30", 5, 100, row=r)
            if pcell is not None:
                limit_tick(pcell, "PN_SIMILAR_ARTIST_TRACK_LIMIT")
            rcell = review_twin("artists", "SIMILAR_ARTIST_TRACK_COUNT", "30", 5, 100, row=r, col=3)
            if rcell is not None:   # Review Mode's own Limit ticks, after their numbers
                rlimit = limit_tick(rcell, "REVIEW_SIMILAR_ARTIST_TRACK_LIMIT", "artists")
                self._review_vars = {"same": review["same"], "limit": rlimit}
                rpcell = review_twin("artists_pn", "PN_SIMILAR_ARTIST_TRACK_COUNT", "30", 5, 100, row=r, col=4)
                limit_tick(rpcell, "REVIEW_PN_SIMILAR_ARTIST_TRACK_LIMIT", "artists_pn")
            where["r"] += 1
            if p.columns:
                r = label_row(t("Artists sampled from Playing Now"),
                              t("How many artists are picked at random from Playing Now. Each one in turn finds its "
                              "share of similar artists, so no artist is used twice. With fewer artists in "
                              "Playing Now than this, every one of them is used."))
                pn_cell("PN_SAMPLE_ARTISTS", "5", 1, 20, row=r)
                review_twin("artists_pn", "PN_SAMPLE_ARTISTS", "5", 1, 20, row=r, col=4)
            spin(t("Number of artists"), "SIMILAR_ARTIST_LIMIT", "20", 1, 50,
                 t("Similar artists to take, read from the top of the sources' lists. An artist only counts once it "
                 "gives a track from your library; one that doesn't is skipped and the next one down is read "
                 "instead. Under Playing Now, this many for each sampled artist."))
            pn_cell("PN_ARTISTS_PER_SAMPLE", "4", 1, 20, note=t("per sampled artist"))
            review_twin("artists", "SIMILAR_ARTIST_LIMIT", "20", 1, 50, col=3)
            review_twin("artists_pn", "PN_ARTISTS_PER_SAMPLE", "4", 1, 20, col=4)
            pool_var, _ = spin(t("Number of artist's top tracks"), "TRACKS_PER_ARTIST_POOL", "5", 1, 20)
            pn_cell("PN_TRACKS_PER_ARTIST_POOL", "5", 1, 20)
            review_twin("artists", "TRACKS_PER_ARTIST_POOL", "5", 1, 20, col=3)
            review_twin("artists_pn", "PN_TRACKS_PER_ARTIST_POOL", "5", 1, 20, col=4)
            _, p.pick_sb = spin(t("Tracks per artist selection"), "TRACKS_PER_ARTIST_PICK", "3", 1, 20,
                                t("Top tracks come from your Top-track sources (Last.fm, Deezer and so on), for "
                                "the seed artist and each similar artist. Selecting fewer than the top tracks "
                                "(say 3 of 5) means the same seed gives a different playlist each run, as the "
                                "selection is random. For no random pick at all, set both numbers the "
                                "same and untick Limit total tracks to."))
            pn_cell("PN_TRACKS_PER_ARTIST_PICK", "3", 1, 20)
            review_twin("artists", "TRACKS_PER_ARTIST_PICK", "3", 1, 20, col=3)
            review_twin("artists_pn", "PN_TRACKS_PER_ARTIST_PICK", "3", 1, 20, col=4)
            pool_var.trace_add("write", lambda *a: sync_pick_limit(p))
            recent("artists")
            drift("artists")
            deep_cuts("artists")
            nonstop("artists")
            hidden("artists")
            fallback("artists")
            run_after("artists")

        # --- Similar Tracks ---
        if kind == "tracks":
            begin("tracks", t("Playlist"))
            seed_header("tracks")
            if p.columns:
                r = label_row(t("Tracks sampled from Playing Now"),
                              t("How many tracks are picked at random from Playing Now, each from a different artist "
                              "while there are artists left. Each one in turn finds its share of similar tracks."))
                pn_cell("PN_SAMPLE_TRACKS", "5", 1, 20, row=r)
                review_twin("tracks_pn", "PN_SAMPLE_TRACKS", "5", 1, 20, row=r, col=4)
            spin(t("Number of tracks"), "SIMILAR_TRACK_COUNT", "30", 5, 100, t(TARGET_HELP))
            pn_cell("PN_TRACKS_PER_SAMPLE", "6", 1, 50, note=t("per sampled track"))
            review_twin("tracks", "SIMILAR_TRACK_COUNT", "30", 5, 100, col=3)
            review_twin("tracks_pn", "PN_TRACKS_PER_SAMPLE", "6", 1, 50, col=4)
            spin(t("Most tracks per artist"), "SIMILAR_TRACK_PER_ARTIST", "3", 1, 20,
                 t("Includes the seed artist. Under Playing Now it counts across the whole new list."))
            pn_cell("PN_SIMILAR_TRACK_PER_ARTIST", "3", 1, 20)
            review_twin("tracks", "SIMILAR_TRACK_PER_ARTIST", "3", 1, 20, col=3)
            review_twin("tracks_pn", "PN_SIMILAR_TRACK_PER_ARTIST", "3", 1, 20, col=4)
            if p.columns:   # Variety and Order apply to every column
                tk.Frame(where["box"], height=1, bg=PALETTE["section_edge"]).grid(
                    row=where["r"], column=0, columnspan=5, sticky="ew", pady=(8, 4))
                where["r"] += 1
            choice(t("Variety"), "SIMILAR_TRACK_VARIETY", "no", [N_("yes"), N_("no")],
                   t("Yes: gathers up to twice the matches it needs and picks from them at random, the closest "
                   "the most likely, so the same seed gives a different playlist each run.\n"
                   "No: takes the closest matches in order and stops at the number of tracks, so the same "
                   "seed gives the same playlist."), note=t("Every column"))
            choice(t("Order"), "SIMILAR_TRACK_ORDER", "shuffled", [N_("shuffled"), N_("similar first")],
                   t("Similar first keeps the order the sources agreed on, strongest matches first. Under Playing "
                   "Now, each sampled track's best match comes first, then each one's second best, and so on. "
                   "Shuffled mixes them up."), note=t("Every column"))
            recent("tracks")
            drift("tracks")
            deep_cuts("tracks")
            nonstop("tracks")
            hidden("tracks")
            fallback("tracks")
            run_after("tracks")

        # --- Artist's Top Tracks ---
        if kind == "top":
            begin("top", t("Playlist"))
            review_header("top")
            spin(t("Number of tracks (1-20)"), "TOP_TRACKS_COUNT", "10", 1, 20, t(TOP_TARGET_HELP))
            review_twin("top", "TOP_TRACKS_COUNT", "10", 1, 20)
            choice(t("Order"), "TOP_TRACKS_ORDER", "popular", [N_("popular"), N_("reverse"), N_("random")],
                   t("popular: most played first\nreverse: least played first\nrandom: shuffled"))
            recent("top")
            nonstop("top")
            hidden("top")
            fallback("top")
            run_after("top")

        # --- Vibe Playlist ---
        if kind == "vibe":
            begin("vibe", t("Playlist"))
            spin(t("Number of tracks"), "VIBE_TRACK_COUNT", "20", 5, 100, t(TARGET_HELP))
            spin(t("Most tracks per artist"), "VIBE_PER_ARTIST", "3", 1, 20,
                 t("The AI often suggests several songs by one artist. Once an artist has this many, the rest "
                   "of theirs are left out and the other suggestions fill the playlist. Drift keeps to it too."))
            recent("vibe")
            drift("vibe")
            deep_cuts("vibe")
            nonstop("vibe")
            hidden("vibe")
            fallback("vibe")
            run_after("vibe")

        p.resync = lambda: (sync_pick_limit(p), sync_drift(p), sync_long_closers(p), sync_played(p),
                            sync_nonstop(p))
        p.resync()
        p.loading = False

    def _build_keys(self, nb):
        tab = self._scroll_tab(nb, N_("Keys"))
        box = section(tab, t("Keys and passwords"))
        r = 0
        for key in (k for k in KEY_FIELDS if k not in AI_KEY_FIELDS):
            self._key_row(box, r, key)
            r += 1
            if key == "TIDAL_CLIENT_SECRET":   # the Tidal account sits under its two keys
                self._tidal_account_row(box, r)
                r += 1

        # --- AI: the provider and what it needs, in its own box, with what the AI has used under it ---
        box = section(tab, "AI",
                      t("Which AI 24bit7's AI features use, and the tokens they have used since you last "
                      "cleared the count, with an estimated cost. Providers bill by tokens, and output tokens "
                      "cost several times more than input. Answers reused from the cache cost nothing and "
                      "aren't counted. Your provider's own console has your actual bill. Anthropic is the "
                      "one fully tested; OpenAI, Google Gemini and Ollama should work, and reports on how "
                      "they do are welcome."),
                      title_fg=PALETTE["ai_purple"])
        self._build_ai_provider(box)
        use = tk.Frame(box)
        use.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        use_title = tk.Label(use, text=t("Use AI"), font=LABEL_FONT, fg=PALETTE["ai_purple"])
        use_title.pack(side="left", padx=(0, 12))
        help_mark(use, t("Off pauses everything that spends AI credits, without removing your key: AI Playlist, "
                       "the Moderator, the AI as a source, Drift using the AI, Console Query and Assess Tone "
                       "all stand down, and the console says so once per build. Switch back On and every "
                       "setting is as you left it. Part of Profiles, so a No AI profile is one Load away."),
                  on=use_title)
        self.use_ai_var = tk.StringVar(value="Off" if self.env.get("USE_AI", "1").strip().lower()
                                       in ("0", "false", "no", "off") else "On")
        for choice in (N_("On"), N_("Off")):
            ttk.Radiobutton(use, text=t(choice), value=choice, variable=self.use_ai_var,
                            command=self._use_ai_changed).pack(side="left", padx=(0, 10))
        usage = tk.Frame(box)
        usage.grid(row=3, column=0, columnspan=4, sticky="w", pady=(14, 0))
        tk.Label(usage, text=t("AI Usage"), font=LABEL_FONT, fg=PALETTE["ai_purple"]).grid(row=0, column=0, sticky="w")
        self.usage_total = tk.Label(usage, text="", anchor="w", justify="left")
        self.usage_total.grid(row=1, column=0, sticky="w", pady=(4, 8))
        self._wrap_to_width(usage, [self.usage_total])
        self.usage_table = tk.Frame(usage)
        self.usage_table.grid(row=2, column=0, sticky="w")
        buttons = tk.Frame(usage)
        buttons.grid(row=3, column=0, sticky="w", pady=(10, 0))
        tk.Button(buttons, text=t("Clear"), width=8, command=self._usage_clear).pack(side="left")
        tk.Button(buttons, text=t("Query"), width=8, command=self._usage_query).pack(side="left", padx=(8, 0))
        self.usage_note = tk.Label(buttons, text="", fg=PALETTE["help_fg"], font=HELP_FONT)
        self.usage_note.pack(side="left", padx=(12, 0))
        show = tk.Frame(usage)
        show.grid(row=4, column=0, sticky="w", pady=(10, 0))
        self.usage_np_var = tk.BooleanVar(value=self.env.get("AI_USAGE_NOW_PLAYING", "0") == "1")
        ttk.Checkbutton(show, text=t("Show in Now Playing"), variable=self.usage_np_var,
                        command=self._usage_np_toggled).pack(side="left")
        tk.Label(show, text=t("as")).pack(side="left", padx=(12, 6))
        unit = self.env.get("AI_USAGE_NP_UNIT", "dollars").strip().lower()
        self.usage_unit_var = tk.StringVar(value="Tokens" if unit == "tokens" else "Dollars")
        unit_cb = TCombobox(show, textvariable=self.usage_unit_var, values=[N_("Dollars"), N_("Tokens")],
                               state="readonly", width=9)
        unit_cb.pack(side="left")
        unit_cb.bind("<<ComboboxSelected>>", lambda e: (unit_cb.selection_clear(), self._usage_unit_chosen()))
        help_mark(show, t("Clicking the total in Now Playing also switches between dollars and tokens.")).pack(
            side="left", padx=(8, 0))

        tk.Label(usage, text=t("Guide"), font=LABEL_FONT, fg=PALETTE["ai_purple"]).grid(
            row=5, column=0, sticky="w", pady=(18, 0))
        self.usage_dollar = tk.Label(usage, text="", anchor="w", justify="left")
        self.usage_dollar.grid(row=6, column=0, sticky="w", pady=(4, 8))
        self.usage_guide = tk.Frame(usage)
        self.usage_guide.grid(row=7, column=0, sticky="w")
        self.usage_legend = tk.Label(usage, text="", fg=PALETTE["help_fg"], font=HELP_FONT, anchor="w")
        self.usage_legend.grid(row=8, column=0, sticky="w", pady=(6, 0))
        rates = self.usage_rates = tk.Label(usage, text=ai_usage.rates_line(), fg=PALETTE["help_fg"], font=HELP_FONT, anchor="w",
                         justify="left")
        rates.grid(row=9, column=0, sticky="w", pady=(10, 0))
        self._wrap_to_width(usage, [self.usage_dollar, rates])
        link = self.usage_link = tk.Label(usage, text="", fg=PALETTE.get("link", PALETTE["section_fg"]),
                                          cursor="hand2", font=("Segoe UI", 9, "underline"))
        link.grid(row=10, column=0, sticky="w", pady=(2, 0))
        link.bind("<Button-1>", lambda e: ai_usage.pricing_page(self._ai_provider()) and
                  webbrowser.open_new_tab(ai_usage.pricing_page(self._ai_provider())))
        self._sync_pricing_note()
        tab.bind("<<Shown>>", lambda e: self._fill_usage(), add="+")
        self._fill_usage()

    def _build_ai_provider(self, box):
        """The Provider dropdown, and under it the chosen provider's key (or Ollama's address and model)."""
        purple = PALETTE["ai_purple"]
        row = tk.Frame(box)
        row.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        title = tk.Label(row, text=t("Provider"), font=LABEL_FONT, fg=purple)
        title.pack(side="left", padx=(0, 12))
        self.ai_provider_var = tk.StringVar(value=option_label(engine.AI_PROVIDERS, engine.AI_PROVIDER))
        cb = TCombobox(row, textvariable=self.ai_provider_var, state="readonly", width=18,
                          values=[name for _, name in engine.AI_PROVIDERS])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: (cb.selection_clear(), self._ai_provider_chosen()))
        help_mark(row, t("The AI that AI Playlist, the Moderator, the AI as a source, Steer, Assess Tone and "
                       "the Queries use. Anthropic (Claude) is the one fully tested. OpenAI and Google Gemini "
                       "need their own key and should work the same way. Ollama runs a model on your own PC "
                       "for free; smaller models give rougher results, and Console Query isn't available with "
                       "it. Keys for every provider stay saved, so switching back loses nothing."),
                  on=title).pack(side="left", padx=(8, 0))
        self.ai_untested = tk.Label(row, text=t(UNTESTED_NOTE), fg=PALETTE["help_fg"], font=HELP_FONT)
        self.ai_untested.pack(side="left", padx=(12, 0))
        self.ai_field_frames = {}
        for provider, fields in AI_FIELDS.items():
            frame = tk.Frame(box)
            frame.grid(row=1, column=0, columnspan=4, sticky="w")
            if provider == "ollama":
                self._ollama_rows(frame)
            else:
                self._key_row(frame, 0, fields[0])
            self.ai_field_frames[provider] = frame
        self._show_ai_fields()

    def _ollama_rows(self, frame):
        """Ollama: its address, the model (filled from what Ollama has installed) and Refresh."""
        purple = PALETTE["ai_purple"]
        tk.Label(frame, text="OLLAMA_URL", anchor="w", fg=purple).grid(row=0, column=0, sticky="w", pady=4)
        url = tk.StringVar(value=self.env.get("OLLAMA_URL", "") or engine.OLLAMA_DEFAULT_URL)
        self.vars["OLLAMA_URL"] = url
        entry = tk.Entry(frame, textvariable=url, width=32)
        entry.grid(row=0, column=1, padx=(8, 4))
        entry.bind("<FocusOut>", self._save)
        button = tk.Button(frame, text="?", width=2, command=lambda: self._show_help("OLLAMA_URL"))
        button.grid(row=0, column=3, padx=(4, 0))
        Tooltip(button, t(KEY_HELP["OLLAMA_URL"][1]).replace("\n", " ") + "\n" + t("Click for these steps in a window."))
        tk.Label(frame, text="OLLAMA_MODEL", anchor="w", fg=purple).grid(row=1, column=0, sticky="w", pady=4)
        model = tk.StringVar(value=self.env.get("OLLAMA_MODEL", ""))
        self.vars["OLLAMA_MODEL"] = model
        self.ollama_cb = ttk.Combobox(frame, textvariable=model, width=30)
        self.ollama_cb.grid(row=1, column=1, padx=(8, 4))
        self.ollama_cb.bind("<<ComboboxSelected>>", lambda e: (self.ollama_cb.selection_clear(), self._save(),
                                                                self._sync_play_ai()))
        self.ollama_cb.bind("<FocusOut>", lambda e: (self._save(), self._sync_play_ai()))
        tk.Button(frame, text=t("Refresh"), width=8, command=self._ollama_refresh).grid(row=1, column=2, padx=(4, 0))
        self.ollama_note = tk.Label(frame, text=t("Refresh lists the models Ollama has installed."),
                                    fg=PALETTE["help_fg"], font=HELP_FONT, anchor="w")
        self.ollama_note.grid(row=2, column=1, columnspan=3, sticky="w")

    def _ollama_refresh(self):
        """Asks Ollama which models it has, and offers them in the Model list."""
        url = self.vars["OLLAMA_URL"].get().strip() or engine.OLLAMA_DEFAULT_URL
        names = engine.ollama_models(url)
        if names is None:
            self.ollama_note.config(text=t("Ollama isn't answering at {url}. Is it running?", url=url))
            return
        self.ollama_cb.config(values=names)
        if not names:
            self.ollama_note.config(text=t("Ollama is running but has no models yet. Try: ollama pull gemma3:4b"))
            return
        self.ollama_note.config(text=tn("{count} model installed in Ollama.", "{count} models installed in Ollama.",
                                          len(names)))
        if not self.vars["OLLAMA_MODEL"].get().strip():
            self.vars["OLLAMA_MODEL"].set(names[0])
            self._save()
            self._sync_play_ai()

    def _show_ai_fields(self):
        provider = self._ai_provider()
        for name, frame in self.ai_field_frames.items():
            if name == provider:
                frame.grid()
            else:
                frame.grid_remove()
        if provider == "anthropic":
            self.ai_untested.pack_forget()
        elif not self.ai_untested.winfo_manager():
            self.ai_untested.pack(side="left", padx=(12, 0))

    def _sync_pricing_note(self):
        """The rates line and the pricing link follow the chosen provider (Ollama has no prices)."""
        provider = self._ai_provider()
        if getattr(self, "usage_rates", None) is not None:
            self.usage_rates.config(text=ai_usage.rates_line(provider))
        link = getattr(self, "usage_link", None)
        if link is not None:
            if ai_usage.pricing_page(provider):
                link.config(text=t("{provider}'s pricing page", provider=engine.ai_provider_name(provider)))
                link.grid()
            else:
                link.grid_remove()

    def _ai_provider_chosen(self):
        """A new provider: show what it needs, save, and bring the costs and the Play tab up to date."""
        self._show_ai_fields()
        self._save()
        engine.refresh_settings_if_changed()
        if self._ai_provider() == "ollama" and not self.ollama_cb.cget("values"):
            self._ollama_refresh()
        self._sync_pricing_note()
        if getattr(self, "usage_table", None) is not None:
            self._fill_usage()
        if self._ai_provider() == "ollama" and self.vars.get("CONSOLE_QUERY") is not None \
                and self.vars["CONSOLE_QUERY"].get():
            self.vars["CONSOLE_QUERY"].set(False)   # not available with a local model
            self._save()
        self._sync_play_ai()

    def _use_ai_changed(self):
        """Settings > Keys > Use AI: saved at once; the Play tab greys its AI pieces out or back in."""
        write_env({"USE_AI": "1" if self.use_ai_var.get() == "On" else "0"})
        self._sync_play_ai()

    def _sync_play_ai(self):
        """The Play tab greys its AI pieces out or back in, after Use AI or the provider changes."""
        engine.refresh_settings_if_changed()
        if self._button_page is not None:
            self._sync_moderator_box(self._button_page)
        play = getattr(self, "play", None)
        if play is not None and hasattr(play, "sync_moderator"):
            try:
                play.sync_moderator()
                play.sync_console_buttons()   # the Query button comes and goes with Use AI
                if not engine.console_query_ready() and play.query_panel.winfo_manager():
                    play._close_query()
            except Exception:
                pass

    def _key_row(self, box, r, key):
        """One key: its name, the hidden entry, Show, and the ? with where to get it."""
        tk.Label(box, text=key, anchor="w",
                 **({"fg": PALETTE["ai_purple"]} if key in AI_KEY_FIELDS else {})
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
            Tooltip(button, t(KEY_HELP[key][1]).replace("\n", " ") + "\n" + t("Click for these steps in a window."))

    def _tidal_account_row(self, box, r):
        """Tidal account: signed in or not, and Sign In to Tidal / Sign Out (for Output to Tidal)."""
        tk.Label(box, text=t("Tidal account"), anchor="w").grid(row=r, column=0, sticky="w", pady=4)
        cell = tk.Frame(box)
        cell.grid(row=r, column=1, columnspan=2, sticky="w", padx=(8, 4))
        self._tidal_button = FlatButton(cell, text=t("Sign In to Tidal"), command=self._tidal_account_pressed, quiet=True)
        self._tidal_button.pack(side="left")
        self._tidal_status = tk.Label(cell, fg=PALETTE["help_fg"], font=HELP_FONT)
        self._tidal_status.pack(side="left", padx=(8, 0))
        button = tk.Button(box, text="?", width=2, command=lambda: self._show_help("TIDAL_ACCOUNT"))
        button.grid(row=r, column=3, padx=(4, 0))
        Tooltip(button, t(KEY_HELP["TIDAL_ACCOUNT"][1]).replace("\n", " ") + "\n" + t("Click for these steps in a window."))
        self._tidal_waiting = None   # a threading.Event while a sign-in is waiting on the browser
        self._show_tidal_account()

    def _show_tidal_account(self):
        if self._tidal_waiting is not None:
            self._tidal_button.config(text=t("Cancel"))
            self._tidal_status.config(text=t("Waiting for Tidal in your browser..."))
        elif engine.tidal_signed_in():
            self._tidal_button.config(text=t("Sign Out"))
            self._tidal_status.config(text=t("Signed in"))
        else:
            self._tidal_button.config(text=t("Sign In to Tidal"))
            self._tidal_status.config(text=t("Not signed in. Only needed to send playlists to Tidal."))
        self._sync_output_parts()   # Settings > Other > Additional Outputs says it too

    def _tidal_account_pressed(self):
        if self._tidal_waiting is not None:   # Cancel
            self._tidal_waiting.set()
            return
        if engine.tidal_signed_in():
            if messagebox.askyesno("Tidal", t("Sign out of Tidal? Output to Tidal won't work until you sign in "
                                            "again."), parent=self):
                write_env({"TIDAL_REFRESH_TOKEN": None, "TIDAL_USER_ID": None})
                engine.tidal_sign_out()
                engine.refresh_settings_if_changed()
                self._show_tidal_account()
            return
        self._save()   # Client ID and Secret just typed, without leaving the field
        engine.refresh_settings_if_changed()
        cancelled = threading.Event()
        self._tidal_waiting = cancelled
        outcome = {}

        def run():
            try:
                outcome["login"] = engine.tidal_sign_in(cancelled=cancelled)
            except Exception as e:   # TidalSignInError carries a message for the user
                outcome["error"] = str(e)

        def finish():
            if not self.winfo_exists():
                return
            if not outcome:
                self.after(300, finish)
                return
            self._tidal_waiting = None
            login = outcome.get("login")
            if login:
                write_env({"TIDAL_REFRESH_TOKEN": login["refresh_token"], "TIDAL_USER_ID": login["user_id"] or None})
                engine.refresh_settings_if_changed()
            elif not cancelled.is_set():
                messagebox.showwarning("Tidal", outcome.get("error") or t("Tidal didn't sign you in."), parent=self)
            self._show_tidal_account()

        threading.Thread(target=run, daemon=True).start()
        self._show_tidal_account()
        self.after(300, finish)

    def _wrap_to_width(self, frame, labels):
        """
        Text lines wrap to the visible width of the Settings page they're on, not to
        their own frame: a wide table beside them makes that frame wider than the window.
        """
        page = frame
        while page.master is not None and not isinstance(page.master, tk.Canvas):
            page = page.master

        def fit(_event=None):
            right = page.winfo_rootx() + page.winfo_width()
            for lab in labels:
                width = max(300, right - lab.winfo_rootx() - 24)
                if int(float(str(lab.cget("wraplength")) or 0)) != width:
                    lab.config(wraplength=width)
        page.bind("<Configure>", fit, add="+")
        frame.bind("<Configure>", fit, add="+")

    def _usage_grid(self, frame, headings, rows, left=(0,)):
        """
        A table: a bold grey heading row with a rule under it, even rows, every other row a
        shade off, numbers right-aligned. rows: [[(text, kind), ...]]; kind "" is plain, "dot"
        is a magenta marker (your own average), "note" is left-aligned text.
        left: the columns that align left (the rest align right).
        """
        for child in frame.winfo_children():
            child.destroy()
        stripe = PALETTE.get("field_bg") or PALETTE.get("window_bg")
        pad = dict(padx=10, pady=4)   # inside each cell, so a shaded row is one unbroken band
        for c, heading in enumerate(headings):
            tk.Label(frame, text=t(heading), fg=PALETTE["help_fg"], font=("Segoe UI", 9, "bold"), anchor="w" if
                     (c in left or heading == "Note") else "e", **pad).grid(row=0, column=c, sticky="ew")
        tk.Frame(frame, bg=PALETTE["line"], height=1).grid(row=1, column=0, columnspan=len(headings), sticky="ew")
        for r, row in enumerate(rows, start=2):
            bg = stripe if r % 2 else None
            for c, (text, kind) in enumerate(row):
                kw = dict(anchor="w" if (c in left or kind == "note") else "e", **pad)
                if kind == "dot":
                    kw.update(fg=PALETTE["ai_purple"], font=("Segoe UI", 8))
                if bg:
                    kw["bg"] = bg
                tk.Label(frame, text=text, **kw).grid(row=r, column=c, sticky="nsew")
        for c in range(len(headings)):
            frame.grid_columnconfigure(c, weight=1 if headings[c] == "Note" else 0)

    def _fill_usage(self):
        """The AI Usage total and breakdown (heaviest first), then the per-run guide."""
        totals = ai_usage.totals()
        self.usage_total.config(text=ai_usage.headline(totals))
        rows = [((t(f), ""), (f"{n:,}", ""), (f"{i:,}", ""), (f"{o:,}", ""), (self._cost(c), ""))
                for f, n, i, o, c in totals["by_feature"]]
        if rows:
            self._usage_grid(self.usage_table, (N_("Feature"), N_("Requests"), N_("Input tokens"), N_("Output tokens"),
                                                N_("Est. cost")),
                             rows)
        else:
            for child in self.usage_table.winfo_children():
                child.destroy()
        guide = ai_usage.guide()
        dollar = ai_usage.dollar_line(guide)
        self.usage_dollar.config(text=dollar)
        if dollar:
            self.usage_dollar.grid()
        else:
            self.usage_dollar.grid_remove()   # no gap when there's nothing to say yet
        provider = self._ai_provider()

        def note_for(feature, note):   # Console Query's caching note is Anthropic's; Ollama can't run it
            if feature != "Console Query" or provider == "anthropic":
                return note or ""
            return t("not available with Ollama") if provider == "ollama" else t("per question")
        self._usage_grid(self.usage_guide, (N_("Feature"), N_("Tokens per run"), "", N_("Cost per run"), N_("Note")),
                         [((t(f), ""), (t("about {tokens}", tokens=f"{tokens:,}"), ""), ("\u25cf" if yours else "", "dot"),
                           (t("Free") if provider == "ollama" else self._cost(c), ""), (t(note_for(f, note)), "note"))
                          for f, tokens, c, note, yours in guide])
        self.usage_legend.config(text=t("\u25cf  your own average, from your recorded runs")
                                 if any(yours for *_, yours in guide) else "")

    @staticmethod
    def _cost(dollars):
        return ai_usage.cost_phrase(dollars)

    def _usage_clear(self):
        if messagebox.askyesno(t("Clear AI Usage"), t("Clear the token count? It starts again from now."), parent=self):
            ai_usage.clear()
            self._fill_usage()
            self.usage_note.config(text="")
            ai_usage.refresh_panel()

    def _usage_query(self):
        self._save()   # a key just typed counts
        engine.refresh_settings_if_changed()
        if not engine.ai_configured():
            messagebox.showinfo(t("AI Usage"), t(NO_KEY_TEXT), parent=self)
            return
        if ai_usage.query():
            self.usage_note.config(text=t("The answer is in the console on the Play tab."))
        else:
            ai_usage.ask(lambda answer, error: self.after(0, lambda: messagebox.showinfo(
                t("AI Usage"), answer or t("Query didn't come back: {error}", error=error), parent=self)))

    def _usage_np_toggled(self):
        try:
            write_env({"AI_USAGE_NOW_PLAYING": "1" if self.usage_np_var.get() else "0"})
            ai_usage.refresh_panel()
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    def _usage_unit_chosen(self):
        try:
            write_env({"AI_USAGE_NP_UNIT": self.usage_unit_var.get().lower()})
            ai_usage.refresh_panel()
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    def _add_show_toggle(self, parent, entry, row):
        show = tk.BooleanVar(value=False)
        def toggle():
            entry.config(show="" if show.get() else "\u2022")
        ttk.Checkbutton(parent, text=t("Show"), variable=show, command=toggle).grid(
            row=row, column=2, sticky="w")

    def _clear_cache(self):
        """Clear Cache: older than a month, older than a year, or everything, each with its count."""
        counts = engine.cache_counts()
        win = tk.Toplevel(self)
        win.withdraw()
        win.title(t("Clear Cache"))
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        body = tk.Frame(win, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=t("Clear saved answers from the music sources and the AI:"), anchor="w").pack(
            anchor="w", pady=(0, 8))
        choice = tk.StringVar(value="month")
        for code, label in CLEAR_CACHE_OPTIONS:
            ttk.Radiobutton(body, text=f"{t(label)} ({counts[code]:,})", variable=choice, value=code).pack(
                anchor="w", pady=2)
        tk.Label(body, text=t("Anything cleared is fetched again next time it's needed, and AI answers use "
                            "credits again."), fg=PALETTE["help_fg"], font=HELP_FONT, justify="left",
                 wraplength=scaled(body, 380)).pack(anchor="w", pady=(10, 12))
        buttons = tk.Frame(body)
        buttons.pack(anchor="e")

        def clear():
            n = engine.cache_clear(choice.get())
            win.destroy()
            line = tn("Cleared {count} cached answer.", "Cleared {count} cached answers.", n).replace(str(n), f"{n:,}", 1)
            self.cache_note.config(text=line)
            print(line)
        tk.Button(buttons, text=t("Clear"), width=10, command=clear).pack(side="left")
        tk.Button(buttons, text=t("Cancel"), width=10, command=win.destroy).pack(side="left", padx=(8, 0))
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        top = self.winfo_toplevel()
        x = top.winfo_rootx() + max(0, (top.winfo_width() - win.winfo_reqwidth()) // 2)
        y = top.winfo_rooty() + max(0, (top.winfo_height() - win.winfo_reqheight()) // 3)
        win.geometry(f"+{x}+{y}")
        win.deiconify()
        win.focus_force()
        self._clear_cache_win = win
        return win

    # --- Profiles (Settings > Other) ---

    def _build_profiles(self, tab):
        import profiles
        box = section(tab, t("Profiles"),
                      t("Save your settings as a profile, such as DJ, Explore or No AI, and switch between them. "
                      "A profile holds your buttons and their settings, the zones' choices, Filters, JRiver "
                      "Playlists, the Play tab options and Add Playlist rows, the Preview zone, the Default zone "
                      "and the shortcut zone, cache and console settings. Keys, the JRiver connection, which "
                      "zones are shown, Alexa devices, keyboard shortcuts and appearance stay as they are. "
                      "Loading restarts 24bit7; JRiver keeps playing. Each profile can have a shortcut of its "
                      "own under Keyboard Shortcuts."))
        row = tk.Frame(box)
        row.grid(row=0, column=0, sticky="w", pady=4)
        tk.Label(row, text=t("Profile"), anchor="w").pack(side="left", padx=(0, 12))
        self.profile_var = tk.StringVar()
        self.profile_cb = ttk.Combobox(row, textvariable=self.profile_var, state="readonly", width=24)
        self.profile_cb.pack(side="left")
        self.profile_cb.bind("<<ComboboxSelected>>", lambda e: self.profile_cb.selection_clear())
        for text, command, width in ((t("Load"), self._profile_load, 9), (t("Save As..."), self._profile_save_as, 14),
                                     (t("Delete"), self._profile_delete, 9)):
            tk.Button(row, text=text, width=width, command=command).pack(side="left", padx=(10, 0))
        self.profile_status = tk.Label(box, text="", anchor="w", fg=PALETTE["help_fg"], font=HELP_FONT)
        self.profile_status.grid(row=1, column=0, sticky="w", pady=(2, 0))
        # Enable Switch To: the profiles the Switch Profiles shortcut steps through
        self.profile_switch_row = tk.Frame(box)
        self.profile_switch_row.grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._fill_profiles(profiles.current())
        self.after(2000, self._poll_profile_status)

    def _fill_profiles(self, select=None):
        import profiles
        names = profiles.names()
        self.profile_cb.config(values=names)
        if select in names:
            self.profile_var.set(select)
        elif self.profile_var.get() not in names:
            self.profile_var.set(names[0] if names else "")
        self._show_profile_status()
        self._fill_profile_switch(names)
        self._fill_profile_shortcuts()

    def _fill_profile_switch(self, names):
        """One tick per profile: the ones the Switch Profiles shortcut steps through."""
        import profiles
        row = getattr(self, "profile_switch_row", None)
        if row is None:
            return
        for child in row.winfo_children():
            child.destroy()
        if not names:
            return
        tk.Label(row, text=t("Enable Switch To"), anchor="w").pack(side="left", padx=(0, 12))
        for name in names:
            var = tk.BooleanVar(value=profiles.in_switch(name))
            ttk.Checkbutton(row, text=name, variable=var,
                            command=lambda n=name, v=var: profiles.set_in_switch(n, v.get())).pack(
                side="left", padx=(0, 12))
        help_mark(row, t("The profiles the Switch Profiles keyboard shortcut steps through, A to Z "
                       "(Settings > Other > Keyboard Shortcuts). With two ticked it flips between them. "
                       "A switch during a build waits for the build to finish.")).pack(side="left")

    def _show_profile_status(self):
        import profiles
        try:
            cur = profiles.current()
            if not cur:
                text = t("Current: None")
            elif profiles.changed(cur):
                text = t("Current: {name} (changed)", name=cur)
            else:
                text = t("Current: {name}", name=cur)
        except Exception as e:
            text = t("Problem: couldn't read the profiles ({error}).", error=e)
        self.profile_status.config(text=text)

    def _poll_profile_status(self):
        """Keeps "(changed)" honest while the Other page is on screen."""
        try:
            if self.profile_status.winfo_viewable():
                self._show_profile_status()
            self.after(2000, self._poll_profile_status)
        except tk.TclError:
            pass

    def _profile_save_as(self):
        import profiles
        name = tabs.ask_name(self, t("Save Profile"), t("Name for this profile:"),
                             profiles.current() or self.profile_var.get())
        name = re.sub(r"[^\w\- ]+", "", name or "").strip()
        if not name:
            return
        if profiles.exists(name) and not messagebox.askyesno(
                t("Save Profile"), t('There\'s already a profile called "{name}". Replace it with your current settings?', name=name),
                parent=self):
            return
        profiles.save(name)
        self._fill_profiles(name)

    def _profile_load(self):
        import profiles
        name = self.profile_var.get()
        if not name:
            return
        cur = profiles.current()
        if cur == name and not profiles.changed(name):
            self.profile_status.config(text=t("Current: {name} (already loaded)", name=name))
            return
        if cur and profiles.changed(cur):
            warn = t('You\'ve changed settings since "{name}" was loaded or saved. Those changes will be lost.',
                     name=cur) + "\n\n"
        elif not cur:
            warn = t("Your current settings aren't saved as a profile, so they'll be replaced.") + "\n\n"
        else:
            warn = ""
        if not messagebox.askyesno(t("Load Profile"), warn + t('Load "{name}"? 24bit7 restarts to apply it; JRiver keeps playing.', name=name), parent=self):
            return
        try:
            profiles.queue_load(name)
        except Exception as e:
            messagebox.showerror(t("Load Profile"), t("Couldn't load it: {error}", error=e), parent=self)
            return
        self._loading = True   # nothing saves over it on the way out
        self.winfo_toplevel().event_generate("<<Restart24bit7>>")

    def _profile_delete(self):
        import profiles
        name = self.profile_var.get()
        if not name or not messagebox.askyesno(t("Delete Profile"), t('Delete the profile "{name}"? Your current settings aren\'t changed.', name=name), parent=self):
            return
        profiles.delete(name)
        self.profile_var.set("")
        self._fill_profiles()
        self._hotkey_restart()   # the deleted profile's shortcut is released

    def _build_other(self, nb):
        tab = self._scroll_tab(nb, N_("Other"))
        self._build_profiles(tab)

        # --- General ---
        box = section(tab, t("General"))
        tk.Label(box, text=t("Keep Cache For"), anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self.vars["CACHE_KEEP"] = tk.StringVar(value=option_label(CACHE_KEEP_OPTIONS, engine.CACHE_KEEP))
        cache_row = tk.Frame(box)
        cache_row.grid(row=0, column=1, sticky="w", padx=(12, 0))
        keep_cb = TCombobox(cache_row, textvariable=self.vars["CACHE_KEEP"], state="readonly", width=10,
                               values=[s for _, s in CACHE_KEEP_OPTIONS])
        keep_cb.pack(side="left")
        keep_cb.bind("<<ComboboxSelected>>", lambda e: (keep_cb.selection_clear(), self._save()))
        tk.Button(cache_row, text=t("Clear Cache..."), width=13, command=self._clear_cache).pack(
            side="left", padx=(12, 0))
        help_mark(cache_row, t("How long answers from the music sources and the AI are reused before they're "
                             "asked for again. Longer is quicker and saves AI credits; Permanent keeps them until "
                             "you clear them. Answers that MusicBrainz doesn't know an artist are always "
                             "rechecked after a month.")).pack(side="left", padx=(8, 0))
        self.cache_note = tk.Label(cache_row, text="", fg=PALETTE["help_fg"], font=HELP_FONT)
        self.cache_note.pack(side="left", padx=(12, 0))

        tk.Label(box, text=t("JRiver host"), anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        self.vars["JRIVER_HOST"] = tk.StringVar(value=self.env.get("JRIVER_HOST", "127.0.0.1:52199"))
        e = tk.Entry(box, textvariable=self.vars["JRIVER_HOST"], width=22)
        e.grid(row=1, column=1, sticky="w", padx=(12, 0))
        e.bind("<FocusOut>", self._save)

        # Language: the offered ones, plus where to ask for another. Applied when 24bit7 restarts.
        tk.Label(box, text=t("Language"), anchor="w").grid(row=3, column=0, sticky="w", pady=4)
        names = dict(i18n.LANGUAGES)
        current = engine.UI_LANGUAGE if engine.UI_LANGUAGE in i18n.OFFERED else "en"
        self.vars["UI_LANGUAGE"] = tk.StringVar(value=names[current])
        cell = tk.Frame(box)
        cell.grid(row=3, column=1, columnspan=2, sticky="w", padx=(12, 0))
        lang_cb = ttk.Combobox(cell, textvariable=self.vars["UI_LANGUAGE"], state="readonly", width=10,
                               values=[names[c] for c in i18n.OFFERED])
        lang_cb.pack(side="left")
        lang_cb.bind("<<ComboboxSelected>>", self._on_language_changed)
        help_mark(cell, t("The language 24bit7's screens and console use. Changing it restarts 24bit7. "
                          "Song, artist and album names are never translated.")).pack(side="left", padx=(8, 0))
        tk.Label(cell, text=t("Another language? Ask for it on the"), fg=PALETTE["help_fg"],
                 font=HELP_FONT).pack(side="left", padx=(16, 4))
        for i, (text, url) in enumerate(((t("JRiver Forum"), FORUM_URL), ("GitHub", REPO_URL + "/issues"))):
            if not url:
                continue
            if i:
                tk.Label(cell, text=t("or on"), fg=PALETTE["help_fg"], font=HELP_FONT).pack(side="left", padx=4)
            link = tk.Label(cell, text=text, fg=PALETTE["section_fg"], cursor="hand2",
                            font=("Segoe UI", 9, "underline"))
            link.pack(side="left")
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open_new_tab(u))

        tk.Label(box, text=t("Theme"), anchor="w").grid(row=4, column=0, sticky="w", pady=4)
        self.vars["THEME"] = tk.StringVar(
            value="Dark" if self.env.get("THEME", "light").strip().lower() == "dark" else "Light")
        cell = tk.Frame(box)
        cell.grid(row=4, column=1, sticky="w", padx=(12, 0))
        theme_cb = TCombobox(cell, textvariable=self.vars["THEME"], values=[N_("Light"), N_("Dark")],
                                state="readonly", width=8)
        theme_cb.pack(side="left")
        help_mark(cell, t('Light or dark colours for the whole app. The theme is applied when 24bit7 starts, so changing it offers a restart straight away.')).pack(side="left", padx=(8, 0))
        theme_cb.bind("<<ComboboxSelected>>", self._on_theme_changed)
        self.vars["WINDOWS_TITLE_BAR"] = tk.BooleanVar(
            value=self.env.get("WINDOWS_TITLE_BAR", "0").strip().lower() in ("1", "true", "yes"))
        ttk.Checkbutton(cell, text=t("Use the Windows title bar"), variable=self.vars["WINDOWS_TITLE_BAR"],
                        command=self._on_title_bar_toggled).pack(side="left", padx=(24, 0))
        help_mark(cell, t("Unticked, 24bit7 draws its own title bar: the Play, Discover and Settings strip runs to "
                        "the top of the window, with minimise, maximise and close at the right. Drag the strip to "
                        "move the window, double-click it to maximise. Tick this for Windows' usual title bar "
                        "instead. Either way takes effect when 24bit7 restarts.")).pack(side="left", padx=(8, 0))

        # Accent Colour: the dark theme's colour and the console's, with a preview to choose by
        tk.Label(box, text=t("Accent Colour"), anchor="w").grid(row=5, column=0, sticky="nw", pady=4)
        saved = self.env.get("ACCENT_COLOUR", "").strip()
        self.vars["ACCENT_COLOUR"] = tk.StringVar(value=tabs.tidy_accent(saved) if saved else "")
        cell = tk.Frame(box)
        cell.grid(row=5, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=4)
        line = tk.Frame(cell)
        line.pack(anchor="w")
        self.accent_swatch = tk.Frame(line, width=scaled(self, 18), height=scaled(self, 18),
                                      highlightthickness=1, highlightbackground=PALETTE["line"])
        self.accent_swatch.pack(side="left")
        self.accent_code = tk.Label(line, text="", width=8, anchor="w")
        self.accent_code.pack(side="left", padx=(6, 8))
        FlatButton(line, text=t("Choose Colour"), command=self._choose_accent, quiet=True).pack(side="left")
        FlatButton(line, text=t("Use the Default"), command=lambda: self._set_accent(""),
                   quiet=True).pack(side="left", padx=(8, 0))
        help_mark(line, t("The colour of the dark theme's tabs, buttons and titles, and of the console in either "
                          "theme. The preview shows it in the dark theme. A colour too dark to read is made lighter, "
                          "and one close to magenta is moved away from it, as magenta marks anything that uses AI "
                          "credits. It's applied when 24bit7 starts, so changing it offers a restart.")
                  ).pack(side="left", padx=(8, 0))
        self.accent_preview = tk.Canvas(cell, width=scaled(self, 520), height=scaled(self, 146),
                                        highlightthickness=0, bd=0)
        self.accent_preview.pack(anchor="w", pady=(8, 0))
        self.accent_note = tk.Label(cell, text="", fg=PALETTE["help_fg"], font=HELP_FONT)   # shown when a pick is changed
        self._draw_accent_preview()

        row = tk.Frame(box)
        row.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
        # Console Query: magenta, as it uses AI credits. Off by default; ticking it asks first.
        self.vars["CONSOLE_QUERY"] = tk.BooleanVar(
            value=self.env.get("CONSOLE_QUERY", "0").strip().lower() in ("1", "true", "yes"))
        ttk.Checkbutton(row, variable=self.vars["CONSOLE_QUERY"],
                        command=self._on_console_query_toggled).pack(side="left")
        cq_label = tk.Label(row, text=t("Enable Console Query"), fg=PALETTE["ai_purple"], cursor="hand2")
        cq_label.pack(side="left")

        def label_clicked(_e):
            self.vars["CONSOLE_QUERY"].set(not self.vars["CONSOLE_QUERY"].get())
            self._on_console_query_toggled()
        cq_label.bind("<Button-1>", label_clicked)
        help_mark(row, t("Adds Query to the console's Copy and Clear strip. Ask the AI why a playlist came "
                       "out the way it did, and get suggested setting changes. Each question sends the "
                       "console, your settings (without keys) and 24bit7's code, so it uses more AI "
                       "credit than the Moderator. Not available with Ollama.")
                  ).pack(side="left", padx=(8, 0))

        # Show Credits: the playing track's credits or every track's, and which list comes first
        tk.Label(box, text=t("Show Credits"), anchor="w").grid(row=7, column=0, sticky="w", pady=(8, 4))
        cell = tk.Frame(box)
        cell.grid(row=7, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=(8, 4))
        self.vars["CREDITS_SCOPE"] = tk.StringVar(value=option_label(CREDITS_SCOPE_OPTIONS, engine.CREDITS_SCOPE))
        scope_cb = TCombobox(cell, textvariable=self.vars["CREDITS_SCOPE"], state="readonly", width=20,
                                values=[s for _, s in CREDITS_SCOPE_OPTIONS])
        scope_cb.pack(side="left")
        scope_cb.bind("<<ComboboxSelected>>", lambda e: (scope_cb.selection_clear(), self._save()))
        tk.Label(cell, text=t("Show First")).pack(side="left", padx=(16, 6))
        self.vars["CREDITS_FIRST"] = tk.StringVar(value=option_label(CREDITS_FIRST_OPTIONS, engine.CREDITS_FIRST))
        first_cb = TCombobox(cell, textvariable=self.vars["CREDITS_FIRST"], state="readonly", width=8,
                                values=[s for _, s in CREDITS_FIRST_OPTIONS])
        first_cb.pack(side="left")
        first_cb.bind("<<ComboboxSelected>>", lambda e: (first_cb.selection_clear(), self._save()))
        help_mark(cell, t("What the Show Credits button lists from Discogs. Album/Current Track shows the "
                        "playing track's credits and the album's. Album/All Tracks lists every track that has "
                        "credits of its own, under its number and title, then the album's. Track credits "
                        "include album credits marked for that track, such as a drummer on tracks 2 to 4. "
                        "Show First picks which list comes first.")).pack(side="left", padx=(8, 0))

        self._build_sources_section(tab)
        self._build_additional_outputs(tab)

        # --- Zones: which JRiver zones appear in the Play tab's Zone and Output lists ---
        # Filled when the tab is first shown, so a slow JRiver never delays startup.
        box = section(tab, t("Zones"),
                      t("Show: untick a zone to hide it from the Zone and Output lists on the Play tab.\n"
                      "Default: the zone Now Playing opens on when 24bit7 starts. Picking a zone by hand "
                      "always wins.\n"
                      "Follow: Now Playing tracks whichever zone JRiver has active, so Default is greyed out.\n"
                      "A DLNA speaker such as a Sonos only appears once DLNA Controller is ticked in JRiver "
                      "(Tools > Options > Media Network > Advanced). Press Rescan after ticking it."))
        self.zone_frame = tk.Frame(box)
        self.zone_frame.grid(row=0, column=0, sticky="w")
        tk.Button(box, text=t("Rescan"), width=10, command=self._fill_zone_boxes).grid(
            row=0, column=1, sticky="nw", padx=(24, 0))
        self.follow_var = tk.BooleanVar(value=engine.FOLLOW_ACTIVE_ZONE)
        ttk.Checkbutton(box, text=t("Follow JRiver's active zone"), variable=self.follow_var,
                        command=self._save_zone_settings).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.zone_vars, self.zone_radios = {}, {}
        self.default_zone_var = tk.StringVar(value=engine.DEFAULT_ZONE)
        self._zones_filled = False
        tab.bind("<<Shown>>", lambda e: None if self._zones_filled else self._fill_zone_boxes())

        # --- Windows: start with Windows, start hidden in the tray, and close to the tray ---
        box = section(tab, t("Windows"),
                      t("Voice Commands need 24bit7 running, so for voice after a restart, tick Start with "
                      "Windows and set JRiver Media Center or Media Server to start with Windows as well."))
        self.startup_var = tk.BooleanVar(value=tray.startup_command() is not None)
        startup_box = ttk.Checkbutton(box, text=t("Start with Windows"), variable=self.startup_var,
                                      command=self._startup_toggled)
        startup_box.grid(row=0, column=0, sticky="w")
        self.vars["START_IN_TRAY"] = tk.BooleanVar(value=self.env.get("START_IN_TRAY", "1") in ("1", "true", "yes"))
        ttk.Checkbutton(box, text=t("Start in the tray (hidden, when Windows starts it)"),
                        variable=self.vars["START_IN_TRAY"], command=self._save).grid(row=1, column=0, sticky="w")
        self.vars["CLOSE_TO_TRAY"] = tk.BooleanVar(value=self.env.get("CLOSE_TO_TRAY", "0") in ("1", "true", "yes"))
        ttk.Checkbutton(box, text=t("Close to tray (the X hides 24bit7; Quit from the tray icon)"),
                        variable=self.vars["CLOSE_TO_TRAY"], command=self._save).grid(row=2, column=0, sticky="w")
        # Only shown when something needs doing: another copy starts with Windows, or the tray can't load
        self.startup_note = tk.Label(box, text="", fg="#a33", font=HELP_FONT, justify="left")
        self.startup_note.grid(row=3, column=0, sticky="w", pady=(4, 0))
        self._show_startup_note()
        if not sys.platform.startswith("win"):
            startup_box.state(["disabled"])

        # --- Keyboard Shortcuts: global keys a remote can send, even with 24bit7 in the tray ---
        box = section(tab, t("Keyboard Shortcuts"),
                      t("Shortcuts work anywhere in Windows, even while 24bit7 is minimised or in the tray, so a "
                      "remote that sends key presses (a Flirc, a Harmony, a phone app) can start a playlist.\n"
                      "Click a box and press the keys you want; Esc cancels. Letters and numbers need Ctrl, Alt, "
                      "Shift or Win with them; F-keys and media keys can be used on their own.\n"
                      "Each shortcut seeds from the zone's current track (paused or stopped counts), or from the "
                      "last track played when its Playing Now is empty, and plays to that zone.\n"
                      "A button's shortcut is set on its page under Buttons."))
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
        """The PDF beside the app if it's there, otherwise the manual on GitHub. In the chosen language's when there is one."""
        pdf, source = MANUAL_PDFS.get(i18n.LANGUAGE, (MANUAL_PDF, "MANUAL.md"))
        path = os.path.join(engine.APP_DIR, pdf)
        if os.path.exists(path):
            try:
                os.startfile(path)
                return
            except Exception:
                pass
        webbrowser.open_new_tab(REPO_URL + "/blob/main/docs/" + source)

    def _build_about(self, nb):
        """About: version, links, voice commands, credits and licence. Nothing here is saved."""
        tab = self._scroll_tab(nb, N_("About"))
        packaged = getattr(sys, "frozen", False)
        version = engine.VERSION
        # The packaged app points at its own release; the dev copy at main, as it may be ahead
        ref = f"v{version}" if packaged else "main"

        # --- Logo, tagline, version ---
        head = tk.Frame(tab)
        head.grid(row=0, column=0, sticky="w", pady=(0, 4))
        for part, colour in (("24", PALETTE["brand_blue"]), ("bit", PALETTE["logo_bit"]),
                             ("7", PALETTE["brand_blue"])):
            tk.Label(head, text=part, font=("Segoe UI", 18, "bold"), fg=colour).pack(side="left")
        tk.Label(head, text="/", font=("Segoe UI", 10), fg=PALETTE["text_muted"]).pack(
            side="left", anchor="s", padx=(12, 8), pady=(0, 5))
        tk.Label(head, text=t("Perfect Playlists and Music Discovery"), font=("Segoe UI", 10),
                 fg=PALETTE["text_muted"]).pack(side="left", anchor="s", pady=(0, 5))
        tk.Label(tab, text=t("Version {version}", version=version), font=LABEL_FONT).grid(row=1, column=0, sticky="w")
        tk.Label(tab, justify="left", wraplength=640, anchor="w",
                 text=t(ABOUT_INTRO)).grid(
            row=2, column=0, sticky="w", pady=(6, 14))

        # --- Links ---
        box = section(tab, t("Links"))
        links = [
            (t("User manual (PDF)"), self._open_manual, t("How everything in 24bit7 works.")),
            ("GitHub", REPO_URL, t("The code, issues and every release.")),
            ("README", f"{REPO_URL}/blob/{ref}/README.md", t("Overview, setup and what's new.")),
            (t("Release notes") if packaged else t("Releases"),
             f"{REPO_URL}/releases/tag/v{version}" if packaged else f"{REPO_URL}/releases",
             t("What changed in {version}.", version=version) if packaged else t("Every published version.")),
            (t("Reporting a problem"), f"{REPO_URL}/blob/{ref}/README.md#reporting-a-problem",
             t("What to send when something goes wrong.")),
        ]
        if FORUM_URL:
            links.append((t("JRiver forum thread"), FORUM_URL, t("Questions, ideas and feedback.")))
        for r, (text, target, blurb) in enumerate(links):
            self._about_link(box, text, target, r, blurb)

        # --- Voice Commands ---
        box = section(tab, t("Voice Commands"))
        note = tk.Frame(box)
        note.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        tk.Label(note, justify="left", wraplength=640, anchor="w",
                 text=(t("Voice commands only work with the needle drop Alexa skill, which you set up "
                       "yourself under a free Amazon developer account."))).pack(anchor="w")
        guide = tk.Frame(note)
        guide.pack(anchor="w", pady=(2, 0))
        tk.Label(guide, text=t("Full instructions:")).pack(side="left")
        g = tk.Label(guide, text=t("Setting up the Alexa skill"), fg=PALETTE["section_fg"], cursor="hand2",
                     font=("Segoe UI", 9, "underline"))
        g.pack(side="left", padx=(6, 0))
        g.bind("<Button-1>", lambda e: webbrowser.open_new_tab(f"{REPO_URL}/blob/{ref}/docs/MANUAL.md#setting-up-the-alexa-skill"))
        tk.Label(box, text=t('Say "Alexa, open needle drop", then a command, or all in one breath: '
                           '"Alexa, ask needle drop for music like Agnes Obel".'),
                 justify="left", wraplength=640, fg=PALETTE["help_fg"], font=HELP_FONT).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        for r, (say, get) in enumerate(VOICE_COMMAND_LIST, start=2):
            tk.Label(box, text=say, font=LABEL_FONT, anchor="w").grid(row=r, column=0, sticky="w", pady=1)
            tk.Label(box, text=t(get), anchor="w", justify="left", wraplength=420).grid(
                row=r, column=1, sticky="w", padx=(16, 0), pady=1)
        r = len(VOICE_COMMAND_LIST) + 2
        tk.Label(box, text=t("No command starts with \"play\": Alexa hands those to a music service instead."),
                 fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 2))
        self._about_link(box, t("How Voice Commands work"), f"{REPO_URL}/blob/{ref}/docs/MANUAL.md#voice-commands",
                         r + 1, t("Every command, what you hear back, and how zones and devices fit together."))

        # --- Credits ---
        box = section(tab, t("Credits"))
        tk.Label(box, text=t("Recommendation data and playback come from:"), anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for r, (name, url) in enumerate(CREDITS, start=1):
            self._about_link(box, name, url, r)

        # --- Thanks ---
        box = section(tab, t("Thanks"))
        for r, (name, why) in enumerate(THANKS):
            tk.Label(box, text=name, font=LABEL_FONT, anchor="w").grid(row=r, column=0, sticky="nw", pady=1)
            tk.Label(box, text=t(why), anchor="w", justify="left", wraplength=420).grid(
                row=r, column=1, sticky="w", padx=(16, 0), pady=1)

        # --- Licence ---
        box = section(tab, t("Licence"))
        tk.Label(box, text=t("MIT Licence. Copyright (c) 2026 Ben Walker-Williams."), anchor="w").grid(
            row=0, column=0, sticky="w")
        self._about_link(box, t("Read the licence"), f"{REPO_URL}/blob/main/LICENSE", 1)

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
        if not hotkeys.AVAILABLE:
            tk.Label(box, text=t("Keyboard shortcuts need Windows."), fg=PALETTE["help_fg"],
                     font=HELP_FONT).grid(row=0, column=0, sticky="w")
            return
        tk.Label(box, text=t("Shortcuts apply to which zone:"), anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self.hotkey_zone_var = tk.StringVar(value=self.env.get("HOTKEY_ZONE", "") or hotkeys.NOW_PLAYING_ZONE)
        zone_cb = TCombobox(box, textvariable=self.hotkey_zone_var, state="readonly", width=28,
                            values=[hotkeys.NOW_PLAYING_ZONE])
        zone_cb.config(postcommand=lambda: zone_cb.config(
            values=[hotkeys.NOW_PLAYING_ZONE] + engine.zone_names(include_hidden=True)))
        zone_cb.grid(row=0, column=1, columnspan=3, sticky="w", padx=(12, 0))
        zone_cb.bind("<<ComboboxSelected>>", lambda e: self._hotkey_zone_changed(zone_cb))
        for r, (code, label) in enumerate(hotkeys.ACTIONS, start=1):
            self._shortcut_row(box, r, code, label, self.env.get(f"HOTKEY_{code}", ""))
        self.hotkey_box, self.profile_shortcut_widgets = box, []
        self._fill_profile_shortcuts()

    def _shortcut_row(self, box, r, code, label, value):
        """One shortcut: its title, the box that takes the keys, Clear, and a note for problems."""
        title = tk.Label(box, text=t(label), anchor="w")
        title.grid(row=r, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=value)
        entry = tk.Entry(box, textvariable=var, width=24, state="readonly", cursor="hand2")
        entry.grid(row=r, column=1, sticky="w", padx=(12, 0))
        entry.bind("<Button-1>", lambda e: e.widget.focus_set())
        entry.bind("<FocusIn>", lambda e, c=code: self._hotkey_capture_start(c))
        entry.bind("<FocusOut>", lambda e, c=code: self._hotkey_capture_end(c))
        entry.bind("<KeyPress>", lambda e, c=code: self._hotkey_key(c, e, True))
        entry.bind("<KeyRelease>", lambda e, c=code: self._hotkey_key(c, e, False))
        clear = tk.Button(box, text=t("Clear"), width=7, command=lambda c=code: self._hotkey_clear(c))
        clear.grid(row=r, column=2, sticky="w", padx=(8, 0))
        note = tk.Label(box, text="", fg="#a33", font=HELP_FONT, anchor="w", justify="left")
        note.grid(row=r, column=3, sticky="w", padx=(10, 0))
        self.hotkey_vars[code], self.hotkey_notes[code] = var, note
        return [title, entry, clear, note]

    def _fill_profile_shortcuts(self):
        """A shortcut box per saved profile, "Load DJ", under the fixed shortcuts; rebuilt as profiles come and go."""
        box = getattr(self, "hotkey_box", None)
        if box is None:
            return
        for widget in self.profile_shortcut_widgets:
            widget.destroy()
        self.profile_shortcut_widgets = []
        for code in [c for c in self.hotkey_vars if hotkeys.is_profile(c)]:
            del self.hotkey_vars[code], self.hotkey_notes[code]
        env = read_env()
        for i, (code, _, name) in enumerate(hotkeys.profile_actions()):
            widgets = self._shortcut_row(box, len(hotkeys.ACTIONS) + 1 + i, code, t("Load {name}", name=name),
                                         env.get(f"HOTKEY_{code}", ""))
            if i == 0:
                widgets.append(help_mark(box, t("Each saved profile has a shortcut of its own that loads it, restarting "
                                              "24bit7 while JRiver keeps playing. A key that always lands on one profile "
                                              "suits a remote or an automation, where Switch Profiles' A to Z order can't "
                                              "be relied on. Pressed with that profile already loaded, it does nothing."),
                                         on=widgets[0]))
            self.profile_shortcut_widgets.extend(widgets)

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
            messagebox.showerror(t("Save failed"), str(e), parent=self)
        combo.selection_clear()

    def _hotkey_save(self, code, combo):
        self.hotkey_vars[code].set(combo)
        if hotkeys.is_button(code):   # kept with the button, not in .env
            buttons.set_shortcut(code[len(hotkeys.BUTTON_PREFIX):], combo)
            return
        try:
            write_env({f"HOTKEY_{code}": combo})   # blank, not removed, so the change is picked up at once
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    def _hotkey_clear(self, code):
        self._hotkey_save(code, "")
        if self._hotkey_capturing is None:
            self._hotkey_restart()

    def _hotkey_capture_start(self, code):
        """While a box is being set, every shortcut is released, so pressing one doesn't start a playlist."""
        self._hotkey_capturing, self._hotkey_held = code, set()
        hotkeys.stop()
        self.hotkey_notes[code].config(text=t("Press the keys you want (Esc to cancel)"), fg=PALETTE["help_fg"])

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
            note.config(text=t("That key can't be used for a shortcut."), fg="#a33")
            return "break"
        if not mods and hotkeys.needs_modifier(vk):
            note.config(text=t("Add Ctrl, Alt, Shift or Win to that key."), fg="#a33")
            return "break"
        combo = hotkeys.combo_text(mods, vk)
        for other, var in self.hotkey_vars.items():
            if other != code and var.get() == combo:
                note.config(text=t("Already used for {shortcut}.", shortcut=t(hotkeys.label(other))), fg="#a33")
                return "break"
        self._hotkey_save(code, combo)
        self.focus_set()   # done: leaving the box registers the shortcuts again
        return "break"

    def _startup_toggled(self):
        try:
            tray.set_startup(self.startup_var.get())
        except Exception as e:
            self.startup_var.set(tray.startup_command() is not None)
            messagebox.showerror(t("Start with Windows"), t("Couldn't change the startup setting: {error}", error=e), parent=self)
        self._show_startup_note()

    def _show_startup_note(self):
        lines = []
        current = tray.startup_command()
        if current and current != tray.launch_command():
            lines.append(t("Windows starts a different copy of 24bit7. Untick and tick again to start this one."))
        if not tray.available():
            lines.append(t("The tray needs pystray and Pillow: run  pip install pystray Pillow  and restart."))
        self.startup_note.config(text="\n".join(lines))
        if lines:
            self.startup_note.grid()
        else:
            self.startup_note.grid_remove()

    def _build_sources_section(self, tab):
        """
        Other > Sources: Test My Sources and Full Results, with the artist and track score tables.
        It's about the sources themselves, so it sits here rather than on every playlist's page,
        which shows each source's score as a figure beside its name.
        """
        import types
        box = section(tab, t("Sources"),
                      t("Test My Sources asks every source what's similar to a fixed set of seed tracks across "
                        "17 genres and counts how many answers are in your library, so you can see which sources "
                        "suit your collection. Each playlist's page shows the scores beside its sources."))
        p = self._other_scores = types.SimpleNamespace(score_ui={})
        self._score_buttons(p, box, "artists")
        for r, (section_key, title, names) in enumerate((("artists", N_("Artist sources"), SOURCE_NAMES),
                                                           ("tracks", N_("Track sources"), TRACK_SOURCE_NAMES))):
            frame = tk.Frame(box)
            frame.grid(row=r, column=0, sticky="w", pady=(0, 10))
            tk.Label(frame, text=t(title), font=LABEL_FONT).grid(row=0, column=0, sticky="w")
            row = self._score_header(p, frame, section_key, 1)
            for code, label in names:
                if code == "ai":   # the AI isn't scored against the others; Full Results shows what it found
                    continue
                name = tk.Label(frame, text=label, anchor="w")
                name.grid(row=row, column=0, sticky="w", pady=1)
                self._score_cells(p, frame, section_key, code, row)
                row += 1
        for key, widget in p.score_ui["artists"].items():   # one Test and Full Results serve both tables
            p.score_ui["tracks"].setdefault(key, widget)
        self._watch_source_test()

    def _fill_zone_boxes(self):
        """Per zone: a Show tick (hidden zones drop off the Play tab) and a Default button."""
        self._zones_filled = True
        for child in self.zone_frame.winfo_children():
            child.destroy()
        engine.refresh_settings_if_changed()
        names = engine.zone_names(include_hidden=True)
        self.zone_vars, self.zone_radios = {}, {}
        if not names:
            tk.Label(self.zone_frame, text=t("No zones found: JRiver turned 24bit7 away. Set a login under "
                                             "Tools > Options > Media Network > Authentication in JRiver, "
                                             "and the same in Settings > Keys.") if engine.JRIVER_REFUSED[0] else
                     t("No zones found. Is JRiver running, with Media Network on?"),
                     fg=PALETTE["help_fg"], font=HELP_FONT, wraplength=scaled(self.zone_frame, 420),
                     justify="left").grid(row=0, column=0, sticky="w")
            return
        tk.Label(self.zone_frame, text=t("Show"), fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=0, column=0, sticky="w")
        tk.Label(self.zone_frame, text=t("Default"), fg=PALETTE["help_fg"], font=HELP_FONT).grid(
            row=0, column=1, sticky="w", padx=(24, 0))
        rb = ttk.Radiobutton(self.zone_frame, text=t("JRiver's active zone"), value="",
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
                tk.Label(self.zone_frame, text=t("{name} (not found)", name=name), fg=PALETTE["help_fg"]).grid(row=r, column=0, sticky="w")
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
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    def _build_voice(self, nb):
        """Voice Commands: the listener switch, its key, New Playlists, the switch timing, and a test."""
        tab = self._scroll_tab(nb, N_("Voice Commands"))

        # --- Voice Commands: the switch and the key ---
        box = section(tab, t("Voice Commands"))
        self.voice_on = tk.BooleanVar(value=engine.VOICE_ENABLED)
        ttk.Checkbutton(box, text=t("Voice Commands (listen for commands from the Alexa skill)"),
                        variable=self.voice_on, command=self._voice_toggled).grid(
            row=0, column=0, columnspan=5, sticky="w")
        self.voice_status = tk.Label(box, text=voice.status_shown(), fg=PALETTE["help_fg"], font=HELP_FONT)
        self.voice_status.grid(row=1, column=0, columnspan=5, sticky="w")

        tk.Label(box, text=t("Key"), anchor="w").grid(row=2, column=0, sticky="w", pady=(12, 2))
        self.voice_key_var = tk.StringVar(value=engine.VOICE_KEY)
        key_box = tk.Frame(box)   # hidden like the other keys; Show is unticked every time Settings opens
        key_box.grid(row=2, column=1, sticky="w", padx=(12, 8), pady=(12, 2))
        key_entry = tk.Entry(key_box, textvariable=self.voice_key_var, width=40, state="readonly",
                             show="\u2022")
        key_entry.pack(side="left")
        show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_box, text=t("Show"), variable=show_key,
                       command=lambda: key_entry.config(show="" if show_key.get() else "\u2022")).pack(
            side="left", padx=(6, 0))
        tk.Button(box, text=t("Copy"), width=8, command=self._voice_copy_key).grid(row=2, column=2, sticky="w", pady=(12, 2))
        tk.Button(box, text=t("New key"), width=max(8, len(t("New key")) + 2), command=self._voice_new_key).grid(
            row=2, column=3, sticky="w", padx=(8, 0), pady=(12, 2))
        help_mark(box, t("The Alexa skill sends this key with every command; anything without it is refused. "
                       "24bit7 only listens on this PC. The tunnel set up for the skill connects it to Amazon.")
                  ).grid(row=2, column=4, sticky="w", padx=(8, 0), pady=(12, 2))

        new_title = tk.Label(box, text=t("New Playlists"), anchor="w")
        new_title.grid(row=3, column=0, sticky="w", pady=(8, 2))
        self.voice_new_var = tk.StringVar(value=option_label(VOICE_NEW_OPTIONS, engine.VOICE_NEW_PLAYLISTS))
        new_cb = TCombobox(box, textvariable=self.voice_new_var, values=[l for _, l in VOICE_NEW_OPTIONS],
                           state="readonly", width=16)
        new_cb.grid(row=3, column=1, sticky="w", padx=(12, 8), pady=(8, 2))
        new_cb.bind("<<ComboboxSelected>>", lambda e: write_env(
            {"VOICE_NEW_PLAYLISTS": option_code(VOICE_NEW_OPTIONS, self.voice_new_var.get())}))
        help_mark(box, t("After this track: the song playing finishes, what was queued after it is cleared, and "
                         "the new playlist follows. A stopped or paused zone starts straight away.\n"
                         "Play now: the new playlist takes over at once.\n"
                         "For playlists you ask for by voice or through the listener. Albums, songs, your JRiver "
                         "playlists and shuffles always play at once, and \"more like this\" always waits."),
                  on=new_title)

        # --- Switching: the devices themselves are under Settings > Devices ---
        box = section(tab, t("Switching"),
                      t("Each Alexa device, the zone it plays to and whether \"switch\" can move the music there "
                        "are set under Settings > Devices."))
        timing = tk.Frame(box)
        timing.grid(row=0, column=0, sticky="w")
        tk.Label(timing, text=t("Switch Timing Adjustment")).pack(side="left")
        self.switch_timing_var = tk.StringVar()
        spin = tk.Spinbox(timing, from_=-3.0, to=3.0, increment=0.25, format="%.2f", width=6,
                          textvariable=self.switch_timing_var, command=self._save_switch_timing)
        spin.pack(side="left", padx=(8, 4))
        self.switch_timing_var.set(f"{voice.switch_adjust_ms() / 1000:.2f}")
        spin.bind("<FocusOut>", self._save_switch_timing)
        spin.bind("<Return>", self._save_switch_timing)
        tk.Label(timing, text=t("seconds")).pack(side="left")
        help_mark(timing, t("Fine-tunes switching to a networked (DLNA) speaker such as a Sonos, which holds a "
                          "second or so of music before you hear it. If it repeats the last moment you heard in "
                          "the other room, move this towards minus; if it skips a little, towards plus. Switching "
                          "to a zone on this PC ignores it.")).pack(side="left", padx=(8, 0))

        # --- Test ---
        box = section(tab, t("Test"), t("Sends a pretend command, as if a device had heard it. "
                                   "The build itself shows in the Play tab log."))
        test = tk.Frame(box)
        test.grid(row=0, column=0, sticky="w")
        tk.Label(test, text=t("Music like")).pack(side="left")
        self.voice_test_artist = tk.Entry(test, width=24)
        self.voice_test_artist.insert(0, "Agnes Obel")
        self.voice_test_artist.pack(side="left", padx=(6, 12))
        tk.Label(test, text=t("on")).pack(side="left")
        self.voice_test_zone = ttk.Combobox(test, state="readonly", width=22,
                                            postcommand=lambda: self.voice_test_zone.config(values=engine.zone_names()))
        self.voice_test_zone.pack(side="left", padx=(6, 12))
        tk.Button(test, text=t("Send test"), width=10, command=self._voice_test).pack(side="left")
        self.voice_test_result = tk.Label(box, text="", fg=PALETTE["help_fg"], font=HELP_FONT, justify="left")
        self.voice_test_result.grid(row=1, column=0, sticky="w", pady=(6, 0))

        # --- Guides: links to the two Voice Commands documents on GitHub ---
        box = section(tab, t("Guides"))
        for r, (title, url, blurb) in enumerate(VOICE_DOCS):
            link = tk.Label(box, text=t(title), fg=PALETTE["section_fg"], cursor="hand2", font=("Segoe UI", 10, "underline"))
            link.grid(row=r, column=0, sticky="w", pady=2)
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open_new_tab(u))
            tk.Label(box, text=t(blurb), fg=PALETTE["help_fg"], font=HELP_FONT).grid(row=r, column=1, sticky="w", padx=(12, 0))

        tab.bind("<<Shown>>", lambda e: self.voice_status.config(text=voice.status_shown()))

    def _voice_toggled(self):
        updates = {"VOICE_ENABLED": "1" if self.voice_on.get() else "0"}
        if self.voice_on.get() and not engine.VOICE_KEY:
            updates["VOICE_KEY"] = voice.new_key()
        try:
            write_env(updates)
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)
        self._voice_restart()

    def _voice_restart(self):
        self.voice_status.config(text=voice.status_shown(voice.restart()))
        self.voice_key_var.set(engine.VOICE_KEY or "")

    def _voice_copy_key(self):
        self.clipboard_clear()
        self.clipboard_append(self.voice_key_var.get())

    def _voice_new_key(self):
        if engine.VOICE_KEY and not messagebox.askyesno(
                t("New key"), t("The Alexa skill will need the new key as well. Make a new one?"), parent=self):
            return
        try:
            write_env({"VOICE_KEY": voice.new_key()})
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)
        self._voice_restart()

    def _save_switch_timing(self, *_):
        """Saves the Switch Timing Adjustment, kept to quarter seconds between -3 and 3."""
        try:
            value = float(self.switch_timing_var.get())
        except ValueError:
            value = voice.switch_adjust_ms() / 1000
        value = max(-3.0, min(3.0, round(value * 4) / 4))
        self.switch_timing_var.set(f"{value:.2f}")
        try:
            write_env({"SWITCH_TIMING": f"{value:.2f}"})
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    def _voice_test(self):
        if not voice.status().startswith("Listening"):
            self.voice_test_result.config(text=t("Switch Voice Commands on first."))
            return
        zone = self.voice_test_zone.get()
        artist = self.voice_test_artist.get().strip()
        if not zone or not artist:
            self.voice_test_result.config(text=t("Type an artist and pick a zone to test with."))
            return
        self.voice_test_result.config(text=t("Sending..."))
        result = []
        # sent from a background thread, so the window never waits on the listener
        threading.Thread(target=lambda: result.append(voice.send_test(artist, zone)), daemon=True).start()

        def show():
            if result:
                self.voice_test_result.config(text=t("Alexa would {what}", what=result[0]))
            else:
                self.after(200, show)
        self.after(200, show)

    def _build_search_sites(self, nb):
        """Discover search sites: which stores and reference sites to open per row."""
        tab = self._scroll_tab(nb, N_("Discover"))
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
        box = section(tab, t("Stores"),
                      t("Search by artist and track. Each ticked site gets its own button on the Discover tab. "
                      "At least one store must stay ticked."))
        ticks(box, "DIGITAL_STORES", engine.STORE_OPTIONS,
              [x.strip().lower() for x in stores_raw.split(",") if x.strip()])
        box = section(tab, t("Reference"), t("Search the artist, for a discography. Each ticked site gets its own "
                                        "button on the Discover tab."))
        ticks(box, "REFERENCE_SITES", engine.REFERENCE_OPTIONS, self._csv_list("REFERENCE_SITES", ""))
        # Record Label sits with the reference sites, but keeps its own setting (DISCOVER_LABEL), on unless unticked
        self.vars["DISCOVER_LABEL"] = tk.BooleanVar(
            value=self.env.get("DISCOVER_LABEL", "1").strip().lower() in ("1", "true", "yes"))
        n = len(engine.REFERENCE_OPTIONS)
        label_tick = ttk.Checkbutton(box, text=t("Record Label"), variable=self.vars["DISCOVER_LABEL"],
                                     command=self._save, style="Big.TCheckbutton")
        label_tick.grid(row=n // cols, column=n % cols, sticky="w", padx=(0, 16), pady=2)
        Tooltip(label_tick, t("Adds a Label button to the Discover tab. It finds who released the selected track "
                            "and opens the label on Bandcamp, so buying it supports the artist through their label."))
        box = section(tab, t("Listen"), t("Search by artist and track. Each ticked site gets its own button on the "
                                     "Discover tab."))
        ticks(box, "LISTEN_SITES", engine.LISTEN_OPTIONS, self._csv_list("LISTEN_SITES", "youtube"))
        box = section(tab, t("Create Playlist"),
                      t("Tick rows on the Discover tab, then make them into one playlist to listen through. Each "
                      "ticked service gets its own button there. YouTube opens them in your browser; Tidal puts "
                      "them in your playlist called 24bit7, in place of what was there (sign in under Settings > "
                      "Keys). This is for the Discover tab only: the Play tab's Output list is set under "
                      "Settings > Other > Additional Outputs."))
        ticks(box, "PLAYLIST_SITES", engine.PLAYLIST_OPTIONS, self._csv_list("PLAYLIST_SITES", "youtube"))

        box = section(tab, t("Custom sites"),
                      t("To add a site: search for anything on it, copy the address from your browser, then replace "
                      "your search words with {query}. Example: https://www.prestomusic.com/search?q={query}\n"
                      "Clear the button name to remove a site. Only links starting with http:// or https:// "
                      "are used."))
        box.grid_columnconfigure(1, weight=1)   # the link field takes whatever width is left
        for c, heading in enumerate((t("Button name"), t("Search link"), t("Search by"))):
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
            mode_cb = TCombobox(box, textvariable=mode_var, state="readonly", width=16,
                                   values=[N_("Artist and track"), N_("Artist only")])
            mode_cb.grid(row=n, column=2, sticky="w", pady=2)
            mode_cb.bind("<<ComboboxSelected>>", self._save)

    # --- helpers -----------------------------------------------------------

    def _build_additional_outputs(self, tab):
        """
        Additional Outputs: the streaming services the Play tab's Output list offers besides
        JRiver's zones, each with its own settings under it, greyed out while it's unticked.
        """
        box = section(tab, t("Additional Outputs"),
                      t("Besides your JRiver zones, the Play tab's Output list can send a playlist to these. "
                      "Untick one to take it out of the list. Discover's Create Playlist buttons are set "
                      "separately, under Settings > Discover."))
        chosen = self._csv_list("EXTRA_OUTPUTS", "youtube")
        self.vars["EXTRA_OUTPUTS"] = {code: tk.BooleanVar(value=code in chosen) for code, _ in engine.OUTPUT_OPTIONS}
        self._output_parts = {}   # code -> the widgets greyed out while it's unticked

        # YouTube, with the two settings it had under General before
        tick = ttk.Checkbutton(box, text="YouTube", variable=self.vars["EXTRA_OUTPUTS"]["youtube"],
                               command=self._extra_outputs_changed, style="Big.TCheckbutton")
        tick.grid(row=0, column=0, columnspan=3, sticky="w", pady=(2, 0))
        Tooltip(tick, t("Output on YouTube opens the playlist in your browser, as one YouTube playlist."))
        tk.Label(box, text=t("YouTube playlist length"), anchor="w").grid(row=1, column=0, sticky="w",
                                                                         padx=(24, 0), pady=4)
        self.vars["YOUTUBE_PLAYLIST_LENGTH"] = tk.StringVar(value=self.env.get("YOUTUBE_PLAYLIST_LENGTH", "50"))
        cell = tk.Frame(box)
        cell.grid(row=1, column=1, sticky="w", padx=(12, 0))
        spin = tk.Spinbox(cell, from_=5, to=50, textvariable=self.vars["YOUTUBE_PLAYLIST_LENGTH"], width=6,
                          command=self._save)
        spin.pack(side="left")
        help_mark(cell, t("How many videos a playlist holds when Output is set to YouTube (5 to 50). "
                        "50 is the most YouTube allows in one playlist link.")).pack(side="left", padx=(8, 0))
        self.vars["YOUTUBE_PLAYLIST_LENGTH"].trace_add("write", self._save)
        self.vars["PREFER_OFFICIAL_VIDEOS"] = tk.BooleanVar(
            value=self.env.get("PREFER_OFFICIAL_VIDEOS", "0") in ("1", "true", "yes"))
        cell = tk.Frame(box)
        cell.grid(row=2, column=0, columnspan=3, sticky="w", padx=(24, 0), pady=4)
        official = ttk.Checkbutton(cell, text=t("Prefer official music videos"),
                                   variable=self.vars["PREFER_OFFICIAL_VIDEOS"], command=self._save)
        official.pack(side="left")
        help_mark(cell, t("YouTube Music usually plays the audio-only version of a song, shown with the album cover. Tick this to play the artist's official music video instead, where one exists. Videos can run longer than the song because of intros and outros, and a few may not play in your region. Songs without an official video still play as audio.")).pack(side="left", padx=(8, 0))
        self._output_parts["youtube"] = [spin, official]

        # Tidal, with whether you're signed in
        tick = ttk.Checkbutton(box, text="Tidal", variable=self.vars["EXTRA_OUTPUTS"]["tidal"],
                               command=self._extra_outputs_changed, style="Big.TCheckbutton")
        tick.grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))
        Tooltip(tick, t("Output on Tidal puts the playlist in your Tidal playlist called 24bit7, in place of "
                      "what was there. Rename it in Tidal to keep it."))
        self._tidal_output_note = tk.Label(box, text="", fg=PALETTE["help_fg"], font=HELP_FONT, anchor="w")
        self._tidal_output_note.grid(row=4, column=0, columnspan=3, sticky="w", padx=(24, 0), pady=4)
        title = tk.Label(box, text=t("Open In"), anchor="w")
        title.grid(row=5, column=0, sticky="w", padx=(24, 0), pady=4)
        Tooltip(title, t("Where the playlist opens once it's filled: the Tidal app, or Tidal's website in your "
                       "browser. If the app isn't installed, it opens on the website. The console offers the "
                       "other one too."))
        self.vars["TIDAL_OPEN"] = tk.StringVar(
            value="Tidal Web" if self.env.get("TIDAL_OPEN", "app").strip().lower() == "web" else "Tidal App")
        open_cb = TCombobox(box, textvariable=self.vars["TIDAL_OPEN"], values=[N_("Tidal App"), N_("Tidal Web")],
                               state="readonly", width=12)
        open_cb.grid(row=5, column=1, sticky="w", padx=(12, 0))
        open_cb.bind("<<ComboboxSelected>>", lambda e: (open_cb.selection_clear(), self._save()))
        self._output_parts["tidal"] = [self._tidal_output_note, open_cb]
        self._sync_output_parts()

    def _sync_output_parts(self):
        """Greys out an unticked service's own settings, and says whether you're signed in to Tidal."""
        if not hasattr(self, "_output_parts"):
            return
        self._tidal_output_note.config(
            text=t("Signed in to Tidal.") if engine.tidal_signed_in()
            else t("Not signed in yet: Settings > Keys, Sign In to Tidal."))
        for code, parts in self._output_parts.items():
            on = self.vars["EXTRA_OUTPUTS"][code].get()
            for w in parts:
                try:
                    w.config(state=("readonly" if isinstance(w, ttk.Combobox) else "normal") if on else "disabled")
                except tk.TclError:
                    pass

    def _extra_outputs_changed(self):
        self._save()
        engine.refresh_settings_if_changed()
        self._sync_output_parts()
        play = getattr(self, "play", None)
        if play is not None:
            play.outputs_changed()   # an Output that's been unticked goes back to Same zone

    def _csv_list(self, key, default):
        return [x.strip().lower() for x in self.env.get(key, default).split(",") if x.strip()]

    def _show_help(self, key):
        title, body = KEY_HELP[key]
        messagebox.showinfo(t(title), t(body), parent=self)