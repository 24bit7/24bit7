"""
24bit7 - main window.

Three tabs in one window:
  Play      - now-playing, the three playlist actions, and a live log
  Discover  - browse logged discoveries (built in the next step)
  Settings  - auto-saving preferences and keys

The Play tab drives engine.py on a background thread, streaming progress into
its log via a thread-safe queue so the window never freezes.
"""

import os
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, scrolledtext, messagebox

import engine
import library
import tray
import voice
import hotkeys
import nonstop
from settings_gui import SettingsTab, write_env, read_env, warn_moderator_once, Tooltip, NO_KEY_TEXT, help_mark
from settings_gui import MODERATOR_CHOICES, MODERATOR_LEVELS_HELP
from discover_gui import DiscoverTab
from tabs import TabbedPane, PALETTE, FlatButton, InfoLine, apply_theme
from mix_gui import MixRows
import console_query
import playmix
import buildlog


REFRESH_MS = 10000   # Now Playing panel; paused while minimised or in the tray
POLL_MS = 100
DONATE_URL = "https://paypal.me/24bit7"
SAME_ZONE_LABEL = "Same zone"
AI_MAGENTA = "#ff33ff"   # AI lines and Query in the console, which is always black

WELCOME_TEXT = (
    "Welcome to 24bit7!\n\n"
    "A starter settings file has been created. Playlists work out of the box "
    "using Deezer and YouTube, which need no keys.\n\n"
    "For richer blends, add free keys for Last.fm and ListenBrainz under "
    "Settings > Keys (the ? buttons explain how), then tick them under "
    "Settings > Sources.\n\n"
    "JRiver needs Media Network enabled: Tools > Options > Media Network."
)


# The Play tab's Drift and Non-stop switches: which Play options each covers, and Non-stop's reseed choices
DRIFT_GROUPS = ("artists", "tracks", "vibe")            # Top Tracks has no Drift
NONSTOP_GROUPS = ("artists", "tracks", "top", "vibe")
PLAY_RESEED = [("last", "Last track"), ("second", "2nd track")]   # as Settings > Playlist shows them


class PlayTab(tk.Frame):
    def __init__(self, master, root):
        super().__init__(master)
        self.root = root
        self.settings = None   # the Settings tab, once built: Drift and Non-stop write through it
        self.log_queue = queue.Queue()
        engine.OUTPUT_HOOK = self.log_queue.put   # engine's print() and [debug] lines land here
        self.running = False
        self.last_playing = None
        self.voice_jobs = queue.Queue()   # (job, heading) from voice commands, run one at a time

        self._build_now_playing()
        self._build_buttons()
        self._build_log()
        self.sync_moderator()

        # First Now Playing read happens just after the window appears, not
        # during construction, so a slow JRiver never delays startup.
        self.after(200, self._refresh_now_playing)
        self.after(POLL_MS, self._drain_log_queue)
        # Coming back from the tray or the taskbar: show what's playing straight away
        root.bind("<Map>", self._on_window_shown, add="+")

    def _build_now_playing(self):
        header = tk.Frame(self, padx=16, pady=12)
        header.pack(fill="x")
        title = tk.Frame(header)
        title.pack(anchor="w")
        BLUE, ORANGE = PALETTE["brand_blue"], PALETTE["brand_orange"]
        for part, colour in (("24", BLUE), ("bit", ORANGE), ("7", BLUE)):
            tk.Label(title, text=part, font=("Segoe UI", 18, "bold"),
                     fg=colour).pack(side="left", padx=0)
        # The tagline sits beside the logo after a "/", both at their usual sizes
        tk.Label(title, text="/", font=("Segoe UI", 10),
                 fg=PALETTE["text_muted"]).pack(side="left", anchor="s", padx=(12, 8), pady=(0, 5))
        tk.Label(title, text="Perfect Playlists and Music Discovery",
                 font=("Segoe UI", 10), fg=PALETTE["text_muted"]).pack(side="left", anchor="s", pady=(0, 5))

        # The seed area: two small tabs. Whichever is showing when a button is
        # pressed is the seed - what JRiver is playing, or a typed artist and track.
        outer = tk.Frame(self, padx=16, pady=8)
        outer.pack(fill="x")
        self.seed_nb = TabbedPane(outer, font=("Segoe UI", 9, "bold"), pad=(14, 4), box=True, indent=6)
        self.seed_nb.pack(fill="x")

        frame = tk.Frame(self.seed_nb, padx=10, pady=8)
        self.seed_nb.add(frame, text="Now Playing")
        # Zone first: which JRiver zone Now Playing reads and seeds from. Not saved,
        # so every launch starts on the active zone. The list rescans when opened.
        zone_box = tk.Frame(frame)
        zone_box.pack(side="left", padx=(0, 32))
        tk.Label(zone_box, text="Zone", font=("Segoe UI", 9, "bold"), fg=PALETTE["text_secondary"]).pack(side="left", padx=(0, 6))
        self.zone_var = tk.StringVar(value="")
        self._zone_picked = False    # picked by hand: stays put until the next launch
        self._zone_settled = False   # launch zone chosen (default or active zone)
        self.zone_cb = ttk.Combobox(zone_box, textvariable=self.zone_var, values=[],
                                    state="readonly", width=24, postcommand=self._fill_zone_list)
        self.zone_cb.pack(side="left")
        self.zone_cb.bind("<<ComboboxSelected>>", self._on_zone_changed)

        info = tk.Frame(frame)
        info.pack(side="left", fill="x", expand=True)
        # Grey "Track:", "Artist:" and "Album:" before the names; both lines wrap as needed
        # One prefix size for all three, and a shared tab stop just after "Artist:"
        # so the track title and the artist name start at the same point
        prefix_font = tkfont.Font(family="Segoe UI", size=7)
        self._prefix_font = prefix_font
        tab = max(prefix_font.measure("Track:"), prefix_font.measure("Artist:")) + prefix_font.measure("  ")
        self.np_track = InfoLine(info, font=("Segoe UI", 11, "bold"), fg=PALETTE["brand_blue"],
                                 prefix_font=prefix_font, tab=tab)
        self.np_track.pack(anchor="w", fill="x")
        self.np_detail = InfoLine(info, font=("Segoe UI", 10), fg=PALETTE["text_secondary"], prefix_font=prefix_font, tab=tab)
        self.np_detail.pack(anchor="w", fill="x")
        self.np_track.show(("...", None))

        # Clicking the Now Playing tab, or anywhere in its panel, reads JRiver straight away
        def refresh_now(_e=None):
            if not self.running:
                self.after_idle(self._update_now_playing)   # after the tab has switched
        for widget in (frame, info, self.np_track, self.np_detail):
            widget.bind("<Button-1>", refresh_now, add="+")
            widget.config(cursor="hand2")
        self.seed_nb._tabs[0].bind("<Button-1>", refresh_now, add="+")   # the Now Playing tab

        self.search_tab = tk.Frame(self.seed_nb, padx=10, pady=8)
        self.seed_nb.add(self.search_tab, text="Search")
        tk.Label(self.search_tab, text="Artist", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.search_artist = tk.Entry(self.search_tab, width=34, font=("Segoe UI", 11))
        self.search_artist.grid(row=0, column=1, sticky="w", padx=(8, 20))
        tk.Label(self.search_tab, text="Track", font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w")
        self.search_track = tk.Entry(self.search_tab, width=34, font=("Segoe UI", 11))
        self.search_track.grid(row=0, column=3, sticky="w", padx=(8, 0))
        tk.Label(self.search_tab, text="Build a playlist from any track, even one you don't own. "
                                       "Press Enter for Similar Artists.",
                 font=("Segoe UI", 8), fg=PALETTE["text_muted"]).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for entry in (self.search_artist, self.search_track):
            entry.bind("<Return>", lambda e: self.on_similar())
        self.seed_nb.bind("<<NotebookTabChanged>>", lambda e: self._sync_seed_buttons())

    def _fill_zone_list(self):
        self.zone_cb.config(values=engine.zone_names())

    def _on_zone_changed(self, *_):
        self._zone_picked = True   # picked by hand, so it stays put until the next launch
        engine.SEED_ZONE_NAME = self.zone_var.get() or None
        self.zone_cb.selection_clear()
        self._update_now_playing()

    def _follow_active_zone(self):
        """
        Sets the Zone dropdown until you pick one by hand. At launch it opens on the
        default zone (Settings > Other), or on JRiver's active zone when there's no
        default, and stays there. With Follow ticked it keeps tracking JRiver's
        active zone instead.
        """
        if self._zone_picked:
            return
        engine.refresh_settings_if_changed()
        follow = engine.FOLLOW_ACTIVE_ZONE
        if self._zone_settled and not follow:
            return
        zones, current = engine._read_zones()
        if not zones:
            return   # JRiver isn't answering yet; the next refresh tries again
        names = [n for _, n in zones]
        name = ""
        if engine.DEFAULT_ZONE and not follow and not self._zone_settled:
            if engine.DEFAULT_ZONE in names:
                name = engine.DEFAULT_ZONE
            else:
                note = (f"Default zone '{engine.DEFAULT_ZONE}' wasn't found in JRiver, "
                        f"so Now Playing opened on the active zone.")
                # after the greeting has cleared the log, so the note isn't wiped with it
                self.after(13000 if self._greeting_active else 0, lambda: self.report(note))
        if not name:
            name = next((n for i, n in zones if i == current), "")
        self._zone_settled = True
        engine.SEED_ZONE_NAME = name or None
        if self.zone_var.get() != name:
            self.zone_var.set(name)

    def _seed_is_search(self):
        return self.seed_nb.select() == str(self.search_tab)

    def _sync_seed_buttons(self):
        """Show Credits needs an album, which a typed seed doesn't have, so it greys out on Search."""
        button = getattr(self, "credits_button", None)
        if button is None or self.running:
            return
        button.config(state="disabled" if self._seed_is_search() else "normal")

    def _typed_seed(self, need_track):
        """The Search tab's seed, or None (after a prompt) if the fields aren't filled in."""
        artist = self.search_artist.get().strip()
        track = self.search_track.get().strip()
        if not artist or (need_track and not track):
            messagebox.showinfo("Search", "Type an artist and a track first." if need_track
                                else "Type an artist first.")
            return None
        return engine.typed_seed_info(artist, track)

    def _build_buttons(self):
        frame = tk.Frame(self, padx=16, pady=4)
        frame.pack(fill="x")
        self.buttons = []
        for text, handler in [
            ("Similar Artists", self.on_similar),
            ("Similar Tracks", self.on_similar_tracks),
            ("Artist's Top Tracks", self.on_top_tracks),
            ("AI Playlist", self.on_vibe),
        ]:
            b = FlatButton(frame, text=text, command=handler, width=18, height=2,
                           accent=PALETTE["ai_purple"] if handler == self.on_vibe else None)   # purple: uses AI credits
            b.pack(side="left", padx=(0, 8))
            self.buttons.append(b)
        # More options: the quieter button. Opens the row below; stays usable during a build.
        self.more_button = FlatButton(frame, text="More Options", command=self._toggle_more,
                                      width=18, height=2, quiet=True)
        self.more_button.pack(side="left", padx=(0, 8))

        # Output: where the finished playlist goes. Saved straight to .env; the engine
        # reads it at the start of each run, so changing it mid-run affects the next one.
        tk.Label(frame, text="Output", font=("Segoe UI", 9, "bold"), fg=PALETTE["text_secondary"]).pack(side="left", padx=(8, 6))
        self.output_var = tk.StringVar(value=self._output_label(engine.OUTPUT_TARGET))
        self.output_cb = ttk.Combobox(frame, textvariable=self.output_var,
                                      values=[SAME_ZONE_LABEL, "YouTube"], state="readonly", width=24,
                                      postcommand=self._fill_output_list)
        self.output_cb.pack(side="left")
        self.output_cb.bind("<<ComboboxSelected>>", self._on_output_changed)

        # The More options row: Show Credits, AI Moderator, Add playlist, with the playlist
        # rows under it. Held in a frame that's always packed, so it opens in the same place.
        self.more_box = tk.Frame(self)
        self.more_box.pack(fill="x")
        self.extras_row = tk.Frame(self.more_box, padx=16, pady=4)
        # AI Moderator sets Windows (Main)'s moderator; devices with settings of their own keep theirs.
        tk.Label(self.extras_row, text="AI Moderator", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["ai_purple"]).pack(side="left", padx=(0, 6))
        self.moderator_var = tk.StringVar(value="Off")
        self.moderator_cb = ttk.Combobox(self.extras_row, textvariable=self.moderator_var,
                                         values=MODERATOR_CHOICES, state="readonly", width=9)
        self.moderator_cb.pack(side="left")
        self.moderator_cb.bind("<<ComboboxSelected>>", self._on_moderator_changed)
        Tooltip(self.moderator_cb, NO_KEY_TEXT, when=lambda: not engine.ANTHROPIC_API_KEY)
        help_mark(self.extras_row, "Checks Similar Artists and Similar Tracks playlists with Claude Haiku "
                                   "and removes tracks that clash with the seed's tone, energy and mood. "
                                   "Uses a little Anthropic credit, a fraction of a penny per playlist.\n"
                                   + MODERATOR_LEVELS_HELP + "\n"
                                   "Voice devices with settings of their own keep their own choice "
                                   "(Settings > Sources).").pack(side="left", padx=(8, 0))
        # Drift and Non-stop: a second door onto Settings > Playlist for Windows (Main).
        # Changing them here changes them there, for every Play option at once.
        tk.Label(self.extras_row, text="Drift", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["text_secondary"]).pack(side="left", padx=(24, 6))
        self.drift_var = tk.StringVar(value="No")
        self.drift_cb = ttk.Combobox(self.extras_row, textvariable=self.drift_var,
                                     values=["No", "Yes"], state="readonly", width=5)
        self.drift_cb.pack(side="left")
        self.drift_cb.bind("<<ComboboxSelected>>", self._on_drift_changed)
        help_mark(self.extras_row, "Searches again when a playlist comes up short, for Similar Artists, "
                                   "Similar Tracks and AI Playlist. Drift using and Rounds are set for each in "
                                   "Settings > Playlist, and changing Drift here changes it there too. "
                                   "Shows Yes only when all three have it on. Voice devices with "
                                   "settings of their own keep theirs.").pack(side="left", padx=(8, 0))
        tk.Label(self.extras_row, text="Non-stop", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["text_secondary"]).pack(side="left", padx=(24, 6))
        self.nonstop_var = tk.StringVar(value="No")
        self.nonstop_cb = ttk.Combobox(self.extras_row, textvariable=self.nonstop_var,
                                       values=["No"] + [shown for _, shown in PLAY_RESEED],
                                       state="readonly", width=10)
        self.nonstop_cb.pack(side="left")
        self.nonstop_cb.bind("<<ComboboxSelected>>", self._on_nonstop_changed)
        help_mark(self.extras_row, "Keeps the music going: when the last track of a playlist 24bit7 built "
                                   "starts, more are added, reseeded from the track chosen here. Applies to "
                                   "all four Play options. The rest of the Non-stop settings are in "
                                   "Settings > Playlist, and changing Non-stop here changes it there too. "
                                   "Shows a track only when all four are on and set the same way. Voice "
                                   "devices with settings of their own keep theirs.").pack(side="left", padx=(8, 0))
        self.credits_button = FlatButton(self.extras_row, text="Show Credits", command=self.on_credits,
                                         quiet=True, width=14, height=1)
        self.credits_button.pack(side="left", padx=(24, 0))
        self.buttons.append(self.credits_button)   # greyed out during a build, and on the Search tab
        # Add playlist: JRiver playlists joined to the next build from the app (not voice)
        FlatButton(self.extras_row, text="+ Add Playlist", quiet=True, width=14, height=1,
                   command=lambda: self.mix_rows.add()).pack(side="left", padx=(8, 0))
        self.mix_rows = MixRows(self.more_box, padx=16)
        self.mix_rows.on_change = self._update_more_label
        self._show_more(playmix.is_open(), save=False)

    def _toggle_more(self):
        self._show_more(not self.extras_row.winfo_manager())

    def _show_more(self, open_, save=True):
        """Opens or closes the More options row. Open or closed is remembered between launches."""
        if open_:
            self.extras_row.pack(fill="x")
            self.mix_rows.pack(fill="x")
        else:
            self.mix_rows.pack_forget()
            self.extras_row.pack_forget()
            self.more_box.configure(height=1)   # Tk keeps an emptied frame's size otherwise
        if save:
            playmix.set_open(open_)
        self._update_more_label()

    def _update_more_label(self):
        """The More options button's arrow: up while the row is open, down while it's closed."""
        open_ = bool(self.extras_row.winfo_manager())
        self.more_button.config(text="More Options \u25b4" if open_ else "More Options \u25be")

    @staticmethod
    def _output_label(target):
        if target == "youtube":
            return "YouTube"
        if target.startswith("zone:"):
            return target[5:]
        return SAME_ZONE_LABEL

    def _fill_output_list(self):
        self.output_cb.config(values=[SAME_ZONE_LABEL] + engine.zone_names() + ["YouTube"])

    def _on_output_changed(self, *_):
        choice = self.output_var.get()
        target = ("youtube" if choice == "YouTube" else
                  "jriver" if choice == SAME_ZONE_LABEL else "zone:" + choice)
        try:
            write_env({"OUTPUT_TARGET": target})
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        self.output_cb.selection_clear()

    def sync_moderator(self):
        """Shows Windows (Main)'s moderator choice, greyed out until there's an Anthropic key."""
        if self.running:
            return   # a voice build may have a device's settings loaded
        engine.refresh_settings_if_changed()
        by = engine.AI_MODERATOR_BY
        levels = {by.get("artists", "off"), by.get("tracks", "off")}
        self.moderator_var.set(levels.pop().title() if len(levels) == 1 else "Off")   # Off unless both agree
        self.moderator_cb.state(["!disabled"] if engine.ANTHROPIC_API_KEY else ["disabled"])
        self._sync_play_switches()
        self._update_more_label()

    def _sync_play_switches(self):
        """Drift and Non-stop as Settings > Playlist has them for Windows (Main): No unless every option agrees."""
        drift = {bool(engine.DRIFT[g]["on"]) for g in DRIFT_GROUPS if g in engine.DRIFT}
        self.drift_var.set("Yes" if drift == {True} else "No")
        by = engine.NONSTOP_BY
        states = {(by[g]["reseed"] if by[g]["on"] else "no") for g in NONSTOP_GROUPS if g in by}
        state = states.pop() if len(states) == 1 else "no"
        self.nonstop_var.set(dict(PLAY_RESEED).get(state, "No"))

    def _save_play_switches(self, updates, apply):
        """
        Writes Drift or Non-stop into Settings > Playlist (Windows (Main)): sets the Settings
        tab's own controls so its next save can't put the old values back, then writes .env.
        """
        settings = getattr(self, "settings", None)
        page = getattr(settings, "_main_playlist", None) if settings else None
        try:
            if page is not None:
                apply(page)
                settings._save()
            write_env(updates)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        engine.refresh_settings_if_changed()
        self._update_more_label()

    def _on_drift_changed(self, *_):
        on = self.drift_var.get() == "Yes"
        updates = {f"DRIFT_{g.upper()}": "1" if on else "0" for g in DRIFT_GROUPS}

        def apply(page):
            from settings_gui import sync_drift
            for g in DRIFT_GROUPS:
                if g in getattr(page, "drift", {}):
                    page.drift[g][0].set(on)
            if getattr(page, "drift", None):
                sync_drift(page)
        self.drift_cb.selection_clear()
        self._save_play_switches(updates, apply)

    def _on_nonstop_changed(self, *_):
        choice = self.nonstop_var.get()
        reseed = {shown: code for code, shown in PLAY_RESEED}.get(choice)
        updates = {}
        for g in NONSTOP_GROUPS:
            updates[f"NONSTOP_{g.upper()}"] = "1" if reseed else "0"
            if reseed:
                updates[f"NONSTOP_{g.upper()}_RESEED"] = reseed

        def apply(page):
            from settings_gui import sync_nonstop
            for g in NONSTOP_GROUPS:
                on_key, rs_key = f"NONSTOP_{g.upper()}", f"NONSTOP_{g.upper()}_RESEED"
                if on_key in page.vars:
                    page.vars[on_key].set(bool(reseed))
                if reseed and rs_key in page.vars:
                    page.vars[rs_key].set(choice)
            if getattr(page, "nonstop_parts", None):
                sync_nonstop(page)
        self.nonstop_cb.selection_clear()
        self._save_play_switches(updates, apply)

    def _on_moderator_changed(self, *_):
        value = self.moderator_var.get().lower()
        if value != "off":
            warn_moderator_once(self)
        try:
            write_env({"AI_MODERATOR_ARTISTS": value, "AI_MODERATOR_TRACKS": value})
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        self.moderator_cb.selection_clear()
        self._update_more_label()

    def _build_log(self):
        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        # The console: a black box holding the tab row (when open) and the text
        self.console_box = tk.Frame(frame, bg="#000000", highlightthickness=1, highlightbackground="#555555")
        self.console_box.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(self.console_box, wrap="word", state="disabled",
                                             font=("Consolas", 9), bg="#000000", fg="#00ff41",
                                             insertbackground="#00ff41", bd=0, highlightthickness=0)
        self.log.pack(fill="both", expand=True)
        # Colour by line type (the words lead, so Copy, Export and Query read the same without colour)
        bold = ("Consolas", 9, "bold")
        self.log.tag_configure("head", foreground="#ffffff", font=bold)
        self.log.tag_configure("problem", foreground="#ff6b6b")
        self.log.tag_configure("note", foreground="#ffb000")
        self.log.tag_configure("ai", foreground=AI_MAGENTA)
        self.log.tag_configure("debug", foreground="#5f7a66")
        self.console_mode = "advanced" if read_env().get("CONSOLE_MODE", "simple").strip().lower() == "advanced" \
            else "simple"
        self.log.tag_configure("debug", elide=self.console_mode == "simple")
        self._build_console_strip(frame)
        self._build_console_head()
        self._greeting_active = True
        self._type_greeting("Follow the white rabbit.", 0)

    def _window_visible(self):
        try:
            return self.root.state() not in ("withdrawn", "iconic")
        except Exception:
            return True

    def _on_window_shown(self, event):
        if event.widget is self.root and not self.running:
            self._update_now_playing()

    def _refresh_now_playing(self):
        # Nobody can see the panel while 24bit7 is minimised or in the tray, so JRiver
        # isn't asked. The Play buttons and shortcuts read the zone fresh when pressed.
        if not self.running and self._window_visible():
            self._update_now_playing()
        self.after(REFRESH_MS, self._refresh_now_playing)

    def _update_now_playing(self):
        self._follow_active_zone()
        info = engine.get_playing_info()
        if info and info.get("PlayingNowPosition", "-1") != "-1":
            self.np_track.show(("Track:\t", "prefix"), (info.get("Name", "?"), None))
            self.np_detail.show(("Artist:\t", "prefix"), (info.get("Artist", "?"), None),
                                ("   \u00b7   ", None),
                                ("Album: ", "prefix"), (info.get("Album", "?"), None))
            self.last_playing = info
        else:
            self.np_track.show(("Nothing playing", None))
            self.np_detail.show(("Start a track in this zone to seed from it", None))
            self.last_playing = None

    def _type_greeting(self, text, i):
        """Types the greeting one character at a time, then clears it after 10 seconds."""
        if not self._greeting_active:
            return
        if i < len(text):
            self.log.config(state="normal")
            self.log.insert("end", text[i])
            self.log.config(state="disabled")
            self.after(60, lambda: self._type_greeting(text, i + 1))
        else:
            self.after(10000, self._clear_greeting)

    def _clear_greeting(self):
        if self._greeting_active:
            self._greeting_active = False
            self._clear_log()

    @staticmethod
    def _line_kind(line):
        """Which colour a console line takes, from how it's written."""
        body = re.sub(r"^\d\d:\d\d  ", "", line.strip())
        if body.startswith("[debug]"):
            return "debug"
        if body.startswith("Problem:"):
            return "problem"
        if body.startswith("Note:"):
            return "note"
        if body.startswith("Done:") or (body and not line.startswith((" ", "\n"))):
            return "head"
        if re.search(r"\bAI\b", body) or body.startswith("Removed "):
            return "ai"
        return None

    def _append_log(self, line):
        if getattr(self, "_stamp_next", False) and line.strip():
            line = time.strftime("%H:%M") + "  " + line.lstrip("\n")
            self._stamp_next = False
        self._live.append(line)
        if not self._live_visible():
            return   # another tab is showing: the line is kept for when this build's tab is chosen
        at_bottom = self.log.yview()[1] >= 0.999   # scrolled up to read? new lines don't pull you down
        self.log.config(state="normal")
        kind = self._line_kind(line)
        self.log.insert("end", line + "\n", (kind,) if kind else ())
        if at_bottom:
            self.log.see("end")
        self.log.config(state="disabled")

    def report(self, message):
        self.log_queue.put(message)

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self._next_voice_job()
        self.after(POLL_MS, self._drain_log_queue)

    def _next_voice_job(self):
        """Starts the next voice build once nothing else is running."""
        if self.running:
            return
        try:
            job, heading, origin = self.voice_jobs.get_nowait()
        except queue.Empty:
            return

        def target():
            self.report(heading)
            job(self.report)
        # voice, shortcuts, non-stop: no added playlists
        self._run_job(target, needs_playing=False, mix=False, origin=origin)

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # --- the console strip: Copy and Clear, shown when you click into the console ---

    def _build_console_strip(self, frame):
        black, green, dim = "#000000", "#00ff41", "#0d4d1c"   # the console's own colours
        self.console_strip = tk.Frame(frame, bg=black)
        self.console_buttons = {}
        self.console_frame = frame
        for name, command in (("Copy", self._copy_log), ("Clear", self._clear_from_strip),
                              ("Query", self._open_query), ("Export to Log", self._export_log),
                              ("Mode", self._toggle_console_mode)):
            b = tk.Label(self.console_strip, text=name, font=("Segoe UI", 8, "bold"), bg=black, fg=green,
                         padx=8, pady=1, cursor="hand2", highlightthickness=1,
                         highlightbackground=green, highlightcolor=green)
            b.pack(side="left", padx=(0, 4))
            b.bind("<Enter>", lambda e, w=b: w.config(bg=dim))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=black))
            b.bind("<Button-1>", lambda e, c=command: c())
            self.console_buttons[name] = b
        # Query is magenta (it uses AI credits) and only shows once Console Query is switched on
        self.console_buttons["Query"].config(fg=AI_MAGENTA, highlightbackground=AI_MAGENTA,
                                             highlightcolor=AI_MAGENTA)
        self.console_buttons["Mode"].config(text=self.console_mode.title())
        self.console_buttons["Query"].pack_forget()
        self._build_query_panel(frame)
        self.log.bind("<Button-1>", lambda e: self._show_console_strip(), add="+")
        self.root.bind_all("<Button-1>", self._maybe_hide_console_strip, add="+")

    # --- the console's tabs: the green arrow opens All | Main Window | one per Alexa device ---

    def _head_box(self, parent, text, command):
        """A box in the tab row, drawn like the console: green on black, a thin dark green edge."""
        b = tk.Label(parent, text=text, font=("Consolas", 9), bg="#000000", fg="#00ff41", padx=10, pady=2,
                     cursor="hand2", highlightthickness=1, highlightbackground="#0d4d1c",
                     highlightcolor="#0d4d1c")
        b.bind("<Button-1>", lambda e: command())
        return b

    def _build_console_head(self):
        black, green = "#000000", "#00ff41"
        self.console_head = tk.Frame(self.console_box, bg=black)
        self.console_head.pack(fill="x", before=self.log.frame)
        self.head_arrow = tk.Label(self.console_head, text="\u25bc", font=("Consolas", 10), bg=black, fg=green,
                                   cursor="hand2", padx=10)
        self.head_arrow.pack(anchor="n")
        self.head_arrow.bind("<Button-1>", lambda e: self._set_tabs_open(not self.tabs_open))
        self.head_row = tk.Frame(self.console_head, bg=black)
        self.head_tabs = tk.Frame(self.head_row, bg=black)
        self.head_tabs.pack(side="left")
        self.head_strip = tk.Frame(self.head_row, bg=black)
        self.head_strip.pack(side="right")
        self.head_buttons = {}
        for name, command in (("Copy", self._copy_log), ("Clear", self._clear_from_strip),
                              ("Query", self._open_query), ("Export to Log", self._export_log),
                              ("Mode", self._toggle_console_mode)):
            b = self._head_box(self.head_strip, name, command)
            b.pack(side="left", padx=(4, 0))
            self.head_buttons[name] = b
        self.head_buttons["Query"].config(fg=AI_MAGENTA, highlightbackground=AI_MAGENTA, highlightcolor=AI_MAGENTA)
        self.head_buttons["Mode"].config(text=self.console_mode.title())
        self.head_line = tk.Frame(self.console_head, bg=green, height=1)
        self.view = "all"                     # the tab on screen: "all", "main" or a device ID
        self._live, self._live_tab = [], "main"   # the build running (or last run) and the tab it files under
        self.tabs_open = read_env().get("CONSOLE_TABS", "0").strip() == "1"
        self._set_tabs_open(self.tabs_open, save=False)

    def _set_tabs_open(self, open_, save=True):
        self.tabs_open = open_
        self.head_arrow.config(text="\u25b2" if open_ else "\u25bc")
        if open_:
            self.head_row.pack(fill="x", padx=8, pady=(0, 6))
            self.head_line.pack(fill="x", padx=8, pady=(0, 4))
            self.console_strip.place_forget()
            self._sync_head_query()
            self._fill_tabs()
        else:
            self.head_row.pack_forget()
            self.head_line.pack_forget()
            if self.view != "all":
                self._select_view("all")
        if save:
            try:
                write_env({"CONSOLE_TABS": "1" if open_ else "0"})
            except Exception:
                pass

    def _sync_head_query(self):
        engine.refresh_settings_if_changed()
        query = self.head_buttons["Query"]
        if getattr(engine, "CONSOLE_QUERY", False) and engine.ANTHROPIC_API_KEY:
            if not query.winfo_manager():
                query.pack(side="left", padx=(4, 0), before=self.head_buttons["Export to Log"])
        else:
            query.pack_forget()

    def _fill_tabs(self):
        if not self.tabs_open:
            return
        for child in self.head_tabs.winfo_children():
            child.destroy()
        try:
            devices = buildlog.tabs()
        except Exception:
            devices = []
        for key, label in [("all", "All"), ("main", "Main Window")] + devices:
            b = self._head_box(self.head_tabs, label, lambda k=key: self._select_view(k))
            if key == self.view:   # the tab on screen: inverted, green with black text
                b.config(bg="#00ff41", fg="#000000", font=("Consolas", 9, "bold"), highlightbackground="#00ff41")
            b.pack(side="left", padx=(0, 4))

    def _live_visible(self):
        return self.view == "all" or self.view == self._live_tab

    def _select_view(self, view):
        """Shows a tab: All is the latest build from anywhere; the others, their own latest."""
        self.view = view
        self._fill_tabs()
        if self._live_visible() and (self._live or self.running):
            self._show_text("\n".join(self._live))
            return
        try:
            rows = buildlog.recent(None if view == "all" else view, 1)
        except Exception:
            rows = []
        self._show_text(rows[0]["text"] if rows else "")

    def _show_text(self, text):
        self._greeting_active = False
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        for line in text.split("\n") if text else []:
            kind = self._line_kind(line)
            self.log.insert("end", line + "\n", (kind,) if kind else ())
        self.log.see("end")
        self.log.config(state="disabled")

    def _begin_live(self, origin):
        """A build is starting: note the tab it files under, and clear the screen if that's the one showing."""
        origin = origin or {}
        kind = origin.get("from")
        if kind == "voice":
            tab = origin.get("device") or "unknown device"
        elif kind == "nonstop":
            try:
                tab = buildlog.tab_for_zone(origin.get("zone"))
            except Exception:
                tab = "main"
        else:
            tab = "main"
        self._live, self._live_tab = [], tab
        if self._live_visible():
            self._clear_log()

    def _flash_head(self, name, text):
        b = getattr(self, "head_buttons", {}).get(name)
        if b is not None:
            b.config(text=text)
            self.after(800, lambda: b.config(text=name))

    def _show_console_strip(self):
        """Top-right inside the console, clear of its scrollbar. Query shows when it's switched on."""
        if getattr(self, "tabs_open", False):
            return   # with the tabs open, the strip sits in the tab row instead
        engine.refresh_settings_if_changed()
        query = self.console_buttons["Query"]
        if getattr(engine, "CONSOLE_QUERY", False) and engine.ANTHROPIC_API_KEY:
            if not query.winfo_manager():
                query.pack(side="left", padx=(0, 4), before=self.console_buttons["Export to Log"])
        else:
            query.pack_forget()
        self.console_strip.place(in_=self.log, relx=1.0, x=-6, y=6, anchor="ne")
        self.console_strip.lift()

    def _maybe_hide_console_strip(self, event):
        """A click anywhere but the console or the strip hides the strip."""
        w, strip = str(event.widget), str(self.console_strip)
        if w == str(self.log) or w == strip or w.startswith(strip + "."):
            return
        self.console_strip.place_forget()

    def _toggle_console_mode(self):
        """Simple hides the debug lines; Advanced shows them. Both are always recorded, and remembered."""
        self.console_mode = "advanced" if self.console_mode == "simple" else "simple"
        self.log.tag_configure("debug", elide=self.console_mode == "simple")
        self.console_buttons["Mode"].config(text=self.console_mode.title(), bg="#000000")
        if hasattr(self, "head_buttons"):
            self.head_buttons["Mode"].config(text=self.console_mode.title())
        try:
            write_env({"CONSOLE_MODE": self.console_mode})
        except Exception:
            pass
        self.log.see("end")

    def _copy_log(self):
        """What's highlighted, or the whole console if nothing is. Simple leaves the debug lines out."""
        try:
            text = self.log.get("sel.first", "sel.last")
        except tk.TclError:
            text = self.log.get("1.0", "end-1c")
        if self.console_mode == "simple":
            text = "\n".join(x for x in text.split("\n") if not x.lstrip().startswith("[debug]"))
        self.clipboard_clear()
        self.clipboard_append(text)
        b = self.console_buttons["Copy"]
        b.config(text="Copied")
        self._flash_head("Copy", "Copied")

        def done():
            self.console_strip.place_forget()
            b.config(text="Copy", bg="#000000")
        self.after(800, done)

    def _export_log(self):
        """Diagnostics plus the console to a dated file in logs\\, then shows it in Explorer."""
        b = self.console_buttons["Export to Log"]
        try:
            path = engine.export_log(self.log.get("1.0", "end-1c"))
        except Exception as e:
            messagebox.showerror("Export to Log", f"Couldn't write the log: {e}", parent=self)
            return
        b.config(text="Saved")
        self._flash_head("Export to Log", "Saved")
        try:
            subprocess.Popen(["explorer", "/select,", path])
        except Exception:
            pass

        def done():
            self.console_strip.place_forget()
            b.config(text="Export to Log", bg="#000000")
        self.after(800, done)

    def _clear_from_strip(self):
        self._greeting_active = False   # stops the greeting typing on into an empty console
        self._clear_log()
        self.console_strip.place_forget()
        self.console_buttons["Clear"].config(bg="#000000")

    # --- Console Query: ask Claude about what's in the console ---

    def _build_query_panel(self, frame):
        """The box under the console: a question, Ask and Close, with grey hints underneath."""
        self.query_panel = tk.Frame(frame)
        row = tk.Frame(self.query_panel)
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text="Ask Claude", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["ai_purple"]).pack(side="left", padx=(0, 8))
        self.query_var = tk.StringVar()
        self.query_entry = tk.Entry(row, textvariable=self.query_var, font=("Segoe UI", 10))
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda e: self._send_query())
        self.query_send = FlatButton(row, text="Ask", command=self._send_query, width=8, height=1,
                                     accent=PALETTE["ai_purple"])
        self.query_send.pack(side="left", padx=(8, 0))
        FlatButton(row, text="Close", command=self._close_query, width=8, height=1,
                   quiet=True).pack(side="left", padx=(8, 0))
        tk.Label(self.query_panel, text=console_query.HINT, font=("Segoe UI", 8),
                 fg=PALETTE["text_muted"], anchor="w", justify="left").pack(anchor="w", pady=(4, 0))
        self._query_busy = False

    def _open_query(self):
        self.console_strip.place_forget()
        self.console_buttons["Query"].config(bg="#000000")
        if not self.query_panel.winfo_manager():
            # packed ahead of the console so it gets its height first; the console shrinks
            self.query_panel.pack(side="bottom", fill="x", before=self.console_box)
        self.query_entry.focus_set()

    def _close_query(self):
        self.query_panel.pack_forget()

    def _append_query(self, text, bold=False):
        """Questions and answers go into the console in magenta, so they stand out from the log."""
        self.log.tag_configure("query", foreground=AI_MAGENTA)
        self.log.tag_configure("query_q", foreground=AI_MAGENTA, font=("Consolas", 9, "bold"))
        self.log.config(state="normal")
        self.log.insert("end", text, "query_q" if bold else "query")
        self.log.see("end")
        self.log.config(state="disabled")

    def _send_query(self):
        question = self.query_var.get().strip()
        if not question or self._query_busy:
            return
        engine.refresh_settings_if_changed()
        if not engine.ANTHROPIC_API_KEY:
            messagebox.showinfo("Console Query", NO_KEY_TEXT, parent=self)
            return
        self._greeting_active = False
        console = self.log.get("1.0", "end-1c")
        if self.console_mode == "simple":   # Query reads what you see: Advanced sends the debug lines too
            console = "\n".join(x for x in console.split("\n") if not x.lstrip().startswith("[debug]"))
        self._query_busy = True
        self.query_send.config(text="Asking...", state="disabled")
        self.query_var.set("")
        self._append_query(f"\nYou asked: {question}\n", bold=True)
        console_query.ask(question, console, self.last_playing,
                          lambda answer, error: self.after(0, lambda: self._query_done(answer, error)))

    def _query_done(self, answer, error):
        self._query_busy = False
        self.query_send.config(text="Ask", state="normal")
        if error:
            self._append_query(f"Console Query didn't come back: {error}\n")
        else:
            self._append_query(answer + "\n")

    def _run_job(self, target, needs_playing=True, mix=True, origin=None):
        if self.running:
            return
        if needs_playing and not self.last_playing:
            messagebox.showinfo("Nothing playing",
                                "Start a track in JRiver first, then try again.")
            return
        self.running = True
        self._job_origin = origin   # who asked, for the build's record: None is the Main Window
        self._greeting_active = False
        for b in self.buttons:
            b.config(state="disabled")
        self._begin_live(origin)
        self._stamp_next = True   # the build's first line gets the time

        rows = (playmix.rows() or None) if mix else None   # added playlists: app builds only

        def worker():
            engine.MIX_ROWS, engine.MIX_KEEP, engine.MIX_FAST_KEY, engine.MIX_NOTED = rows, set(), None, False
            engine.BUILD_STARTED, engine.LAST_OUTPUT = time.time(), None
            engine.LAST_OUTPUT_ID, engine.LAST_BUILD = None, None
            try:
                target()
            except Exception as e:
                self.log_queue.put(f"Problem: something went wrong ({e}). Press Export to Log "
                                   f"and attach the file when you report it.")
            finally:
                engine.MIX_ROWS, engine.MIX_KEEP, engine.MIX_FAST_KEY = None, set(), None
                engine.BUILD_STARTED = None
                self.root.after(0, self._job_done)

        threading.Thread(target=worker, daemon=True).start()

    def _job_done(self):
        try:   # everything the build wrote, then keep it for the console's Log
            while True:
                self._append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        try:
            buildlog.record_job(getattr(self, "_job_origin", None), self.log.get("1.0", "end-1c"))
        except Exception as e:
            print(f"Note: couldn't keep this build in the Log ({e}).")
        self._fill_tabs()   # a device's first build gives it a tab
        self.running = False
        for b in self.buttons:
            b.config(state="normal")
        self._sync_seed_buttons()

    def on_similar(self):
        if self._seed_is_search():
            seed = self._typed_seed(need_track=True)
            if seed:
                self._run_job(lambda: engine.create_similar_playlist(report=self.report, seed_info=seed),
                              needs_playing=False)
            return
        self._run_job(lambda: self._seeded(engine.create_similar_playlist), needs_playing=False)

    def on_similar_tracks(self):
        if self._seed_is_search():
            seed = self._typed_seed(need_track=True)
            if seed:
                self._run_job(lambda: engine.create_similar_tracks_playlist(report=self.report, seed_info=seed),
                              needs_playing=False)
            return
        self._run_job(lambda: self._seeded(engine.create_similar_tracks_playlist), needs_playing=False)

    def on_top_tracks(self):
        if self._seed_is_search():
            seed = self._typed_seed(need_track=False)
            if seed:
                self._run_job(lambda: engine.play_top_n(report=self.report, seed_info=seed),
                              needs_playing=False)
            return
        self._run_job(lambda: self._seeded(engine.play_top_n), needs_playing=False)

    def _seeded(self, build):
        """Seeds from the Now Playing zone's track, or the last track played when its Playing Now is empty."""
        seed = engine.seed_or_last_played(engine.seed_zone(), self.report)
        if seed:
            build(report=self.report, seed_info=seed)

    def on_credits(self):
        self._run_job(lambda: engine.explore_credits(report=self.report))

    def on_vibe(self):
        problem = engine.vibe_blocker()
        if problem:
            self.report(problem)
            return
        VibeDialog(self.root, on_submit=lambda vibe: self._run_job(
            lambda: engine.create_vibe_playlist(vibe, report=self.report), needs_playing=False))


class VibeDialog(tk.Toplevel):
    """
    Asks for a mood description. Three AI-suggested vibes load in the background
    and appear as clickable buttons; click one to use it, or type your own.
    """
    def __init__(self, master, on_submit):
        super().__init__(master)
        self.title("AI Playlist")
        self.resizable(False, False)
        self.on_submit = on_submit
        self.transient(master)

        body = tk.Frame(self, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Describe the mood, era, activity or feeling:",
                 font=("Segoe UI", 10)).pack(anchor="w")
        self.entry = tk.Entry(body, width=48, font=("Segoe UI", 11))
        self.entry.pack(fill="x", pady=(6, 10))
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self.submit())

        tk.Label(body, text="Or try one of these:", fg=PALETTE["text_muted"]).pack(anchor="w")
        # First suggestion: more like what's playing, greyed out until something is
        self.like_text = None
        self.like_button = tk.Button(body, text="More tracks like what's playing", anchor="w",
                                     state="disabled", command=lambda: self._use(self.like_text))
        self.like_button.pack(fill="x", pady=(4, 0))
        self.suggest_frame = tk.Frame(body)
        self.suggest_frame.pack(fill="x", pady=(4, 12))
        self.loading = tk.Label(self.suggest_frame, text="Thinking...", fg=PALETTE["text_faint"])
        self.loading.pack(anchor="w")

        bar = tk.Frame(body)
        bar.pack(fill="x")
        tk.Button(bar, text="Create playlist", width=16, command=self.submit).pack(side="right")
        tk.Button(bar, text="Cancel", width=10, command=self.destroy).pack(side="right", padx=(0, 8))

        threading.Thread(target=self._load_suggestions, daemon=True).start()
        threading.Thread(target=self._load_playing, daemon=True).start()

    def _load_playing(self):
        try:
            info = engine.get_playing_info()
        except Exception:
            info = None
        self.after(0, lambda: self._show_playing(info))

    def _show_playing(self, info):
        if not self.winfo_exists():
            return
        title = ((info or {}).get("Name") or "").strip()
        artist = ((info or {}).get("Artist") or "").split(";")[0].strip()
        if not info or info.get("PlayingNowPosition") == "-1" or not title or title == "Unknown":
            return   # nothing playing: the button stays greyed out
        shown = title if len(title) <= 45 else title[:42].rstrip() + "..."
        by = f" by {engine.deinvert_the(artist)}" if artist and artist != "Unknown" else ""
        self.like_text = f'More tracks like "{title}"{by}, with the same tone, energy and mood'
        self.like_button.config(text=f'More tracks like "{shown}"', state="normal")

    def _load_suggestions(self):
        try:
            ideas = engine.ai_vibe_suggestions()
        except Exception:
            ideas = []
        self.after(0, lambda: self._show_suggestions(ideas))

    def _show_suggestions(self, ideas):
        if not self.winfo_exists():
            return
        self.loading.destroy()
        if not ideas:
            tk.Label(self.suggest_frame, text="(no suggestions right now)", fg=PALETTE["text_faint"]).pack(anchor="w")
            return
        for idea in ideas:
            tk.Button(self.suggest_frame, text=idea, anchor="w",
                      command=lambda t=idea: self._use(t)).pack(fill="x", pady=2)

    def _use(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()

    def submit(self):
        vibe = self.entry.get().strip()
        if not vibe:
            return
        self.destroy()
        self.on_submit(vibe)


def _enable_dpi_awareness():
    """Tell Windows this app is DPI-aware so text renders sharp, not upscaled."""
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _set_app_id():
    """Its own taskbar identity, so Windows shows the 24bit7 icon rather than Python's."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("24bit7.24bit7")
    except Exception:
        pass


def _set_window_icon(root):
    """The 24bit7 icon in the title bar and taskbar; keeps Tk's feather if the file is missing."""
    import os
    base = getattr(sys, "_MEIPASS", engine.APP_DIR)   # the packaged app keeps its files in _MEIPASS
    try:
        root.iconbitmap(default=os.path.join(base, "24bit7.ico"))
    except Exception:
        pass


PID_FILE = os.path.join(engine.APP_DIR, "24bit7.pid")


def _close_other_copy():
    """
    Closes the copy of 24bit7 already running, if there is one, so this launch
    gets the keyboard shortcuts and the tray icon. Returns True if one was closed.
    """
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            old = int(f.read().strip())
    except (OSError, ValueError):
        old = 0
    closed = False
    if old and old != os.getpid() and sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                       ctypes.POINTER(wintypes.DWORD)]
            k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
            k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            QUERY, TERMINATE, SYNC = 0x1000, 0x0001, 0x00100000
            h = k32.OpenProcess(QUERY | TERMINATE | SYNC, False, old)
            if h:
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    name = buf.value.lower() if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else ""
                    if "python" in name or "24bit7" in name:   # only ever a 24bit7 process, never a reused id
                        k32.TerminateProcess(h, 0)
                        k32.WaitForSingleObject(h, 3000)
                        closed = True
                finally:
                    k32.CloseHandle(h)
        except Exception:
            pass
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    return closed


def _forget_pid():
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            mine = f.read().strip() == str(os.getpid())
        if mine:
            os.remove(PID_FILE)
    except OSError:
        pass


def main():
    _enable_dpi_awareness()
    _set_app_id()
    closed_other = _close_other_copy()
    root = tk.Tk()
    _set_window_icon(root)
    apply_theme(root, engine.THEME)   # before any widgets, so they all pick it up
    root.title(f"24bit7  v{engine.VERSION}")
    # Open at 75% of the screen so it fits any monitor/DPI, then centre it.
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = int(sw * 0.75), int(sh * 0.75)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    root.minsize(680, 480)

    nb = TabbedPane(root, font=("Segoe UI", 11, "bold"), pad=(20, 8))
    nb.pack(fill="both", expand=True, pady=(6, 0))

    play = PlayTab(nb, root)
    discover = DiscoverTab(nb)
    settings = SettingsTab(nb)
    play.settings = settings   # the Play tab's Drift and Non-stop change Settings > Playlist
    nb.add(play, text="Play")
    nb.add(discover, text="Discover")
    nb.add(settings, text="Settings")

    # Donate link: top right of the tab row, so it shows from every tab. It is hidden
    # if the window is too narrow for it to sit clear of the tab buttons.
    donate = tk.Label(root, text="Buy me a coffee \u2615", font=("Segoe UI", 9, "underline"),
                      fg=PALETTE["link"], cursor="hand2")
    donate.bind("<Button-1>", lambda e: webbrowser.open(DONATE_URL))

    def place_donate(event=None):
        if event is not None and event.widget is not root:
            return
        room = root.winfo_width() - nb.tabs_width() - donate.winfo_reqwidth() - 40
        if room > 0:
            donate.place(relx=1.0, x=-16, y=nb.winfo_y() + nb.strip_height() // 2, anchor="e")
        else:
            donate.place_forget()
    root.bind("<Configure>", place_donate, add="+")
    root.after(100, place_donate)

    def on_tab_changed(event):
        if nb.select() == str(discover):
            discover.ensure_loaded()
        elif nb.select() == str(play):
            play.sync_moderator()
    nb.bind("<<NotebookTabChanged>>", on_tab_changed)

    # Fresh install: engine just created a starter .env, so open on Settings
    # and say hello once. Never shown again after that.
    if engine.FIRST_RUN:
        nb.select(settings)
        root.after(400, lambda: messagebox.showinfo("Welcome to 24bit7", WELCOME_TEXT, parent=root))

    library.start()   # the whole library in memory: Similar Tracks and voice match against it
    voice.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)),
                 lambda: play.running or not play.voice_jobs.empty())
    voice.restart()
    # Keyboard shortcuts (Settings > Other): queued on the Play tab like voice commands
    hotkeys.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)))
    problems = hotkeys.restart()
    # Non-stop (Settings > Playlist): tops up 24bit7 playlists as they reach their last track
    nonstop.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)))
    nonstop.start()
    settings.refresh_hotkey_notes(problems)
    if problems:
        names = ", ".join(hotkeys.LABELS[c] for c in problems)
        root.after(13000, lambda: play.report(f"Some keyboard shortcuts didn't register ({names}). "
                                              f"See Settings > Other > Keyboard Shortcuts."))
    if closed_other:
        root.after(13000, lambda: play.report("Closed the copy of 24bit7 that was already running."))

    # --- tray: Start in the tray (when Windows launches it) and Close to tray ---
    def show_window():
        root.deiconify()
        root.lift()
        root.focus_force()

    def quit_app():
        tray.stop()
        voice.stop()
        hotkeys.stop()
        nonstop.stop()
        library.stop()
        _forget_pid()
        root.destroy()

    # Settings > Other > Theme offers a restart: quit here, start again after mainloop
    restart = {"on": False}

    def restart_app(_event=None):
        restart["on"] = True
        quit_app()
    root.bind("<<Restart24bit7>>", restart_app)

    def on_close():
        engine.refresh_settings_if_changed()
        if engine.CLOSE_TO_TRAY and tray.start(root, show_window, quit_app):
            root.withdraw()   # still running: voice keeps listening
        else:
            quit_app()

    root.protocol("WM_DELETE_WINDOW", on_close)
    if engine.CLOSE_TO_TRAY or (tray.started_by_windows() and engine.START_IN_TRAY):
        if tray.start(root, show_window, quit_app) and tray.started_by_windows() and engine.START_IN_TRAY:
            root.withdraw()

    root.mainloop()
    if restart["on"]:
        import subprocess
        frozen = getattr(sys, "frozen", False)   # the built .exe is its own program
        subprocess.Popen([sys.executable] + (sys.argv[1:] if frozen else sys.argv), cwd=engine.APP_DIR)


if __name__ == "__main__":
    main()
