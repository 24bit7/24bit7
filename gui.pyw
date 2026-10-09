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
from datetime import datetime
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
from review_gui import ReviewPanel
import console_query
import playmix
import profiles
from ai_dialog import AIPlaylistDialog
import buildlog
import support_gui
import window_chrome
import ai_usage


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
PLAY_RESEED = [("last", "Last track"), ("second", "2nd track")]
PLAY_NONSTOP = [("off", "Off"), ("tight", "Keep It Tight"), ("journey", "Wander")]
PLAY_BEHAVIOUR = [("instant", "Play"), ("review", "Review")]   # every build from the app, not voice
PLAY_DRIFT = [("off", "Off"), ("close", "Keep It Tight"), ("spread", "Spread")]   # as Settings > Playlist shows them   # as Settings > Playlist shows them


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
        ai_usage.set_query_handler(self._usage_query)
        ai_usage.set_panel_refresh(self._sync_usage_box)

        # First Now Playing read happens just after the window appears, not
        # during construction, so a slow JRiver never delays startup.
        self.after(200, self._refresh_now_playing)
        self.after(POLL_MS, self._drain_log_queue)
        # Coming back from the tray or the taskbar: show what's playing straight away
        root.bind("<Map>", self._on_window_shown, add="+")

    def _build_now_playing(self):
        header = tk.Frame(self, padx=16, pady=12)
        header.pack(fill="x")
        # The version, on the right of the header line (the window has no title bar to show it)
        tk.Label(header, text=f"v{engine.VERSION}", font=("Segoe UI", 9),
                 fg=PALETTE["text_muted"]).pack(side="right", anchor="s", pady=(0, 5))
        title = tk.Frame(header)
        title.pack(side="left", anchor="w")
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
        outer = tk.Frame(self, pady=8)   # no side margin: the line under the two tabs spans the window
        outer.pack(fill="x")
        self.seed_nb = TabbedPane(outer, font=("Segoe UI", 9, "bold"), pad=(14, 4), indent=22)
        self.seed_nb.pack(fill="x")

        frame = tk.Frame(self.seed_nb, padx=26, pady=8)
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

        # AI Usage at the far right, while "Show in Now Playing" is ticked in Settings > Keys
        self.usage_box = tk.Frame(frame)
        self.usage_label = tk.Label(self.usage_box, text="", font=("Segoe UI", 9), fg=PALETTE["ai_purple"])
        self.usage_label.pack(side="left", padx=(0, 10))
        self.usage_label.config(cursor="hand2")
        self.usage_label.bind("<Button-1>", self._usage_flip)   # dollars or tokens
        FlatButton(self.usage_box, text="Clear", command=self._usage_clear, width=6, height=1,
                   quiet=True).pack(side="left")
        FlatButton(self.usage_box, text="Query", command=self._usage_query, width=6, height=1,
                   quiet=True).pack(side="left", padx=(6, 0))
        self._usage_shown = False
        self._usage_info = info
        self._sync_usage_box()

        # Clicking the Now Playing tab, or anywhere in its panel, reads JRiver straight away
        def refresh_now(_e=None):
            if not self.running:
                self.after_idle(self._update_now_playing)   # after the tab has switched
        for widget in (frame, info, self.np_track, self.np_detail):
            widget.bind("<Button-1>", refresh_now, add="+")
            widget.config(cursor="hand2")
        self.seed_nb._tabs[0].bind("<Button-1>", refresh_now, add="+")   # the Now Playing tab

        self.search_tab = tk.Frame(self.seed_nb, padx=26, pady=8)
        self.seed_nb.add(self.search_tab, text="Search")
        tk.Label(self.search_tab, text="Artist", font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w")
        self.search_artist = ttk.Entry(self.search_tab, width=34, font=("Segoe UI", 11), style="Field.TEntry")
        self.search_artist.grid(row=0, column=1, sticky="w", padx=(8, 20))
        tk.Label(self.search_tab, text="Track", font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w")
        self.search_track = ttk.Entry(self.search_tab, width=34, font=("Segoe UI", 11), style="Field.TEntry")
        self.search_track.grid(row=0, column=3, sticky="w", padx=(8, 0))
        tk.Label(self.search_tab, text="Build a playlist from any track, even one you don't own. "
                                       "Similar Artists and Artist's Top Tracks need only the "
                                       "artist. Press Enter for Similar Artists.",
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

    def _typed_seed(self, need_track, why=None):
        """The Search tab's seed, or None (after a prompt) if the fields aren't filled in."""
        artist = self.search_artist.get().strip()
        track = self.search_track.get().strip()
        if not artist or (need_track and not track):
            text = "Type an artist and a track first." if need_track else "Type an artist first."
            if need_track and why and artist:
                text = why
            messagebox.showinfo("Search", text)
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
                           accent=PALETTE["ai_purple"] if handler == self.on_vibe else None,   # magenta: AI credits
                           text_fg=PALETTE["ai_purple"] if handler == self.on_vibe else None)
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
        self._sync_behaviour()

        # The More options row: Show Credits, AI Moderator, Add playlist, with the playlist
        # rows under it. Held in a frame that's always packed, so it opens in the same place.
        self.more_box = tk.Frame(self)
        self.more_box.pack(fill="x")
        self.extras_row = tk.Frame(self.more_box, padx=16, pady=4)
        # Behaviour: play straight away, or Review first. Every build from the app; voice always plays.
        tk.Label(self.extras_row, text="Behaviour", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["text_secondary"]).pack(side="left", padx=(0, 6))
        saved = read_env().get("PLAY_BEHAVIOUR", "instant").strip().lower()
        self.behaviour_var = tk.StringVar(value=dict(PLAY_BEHAVIOUR).get(saved, "Play"))
        self.behaviour_cb = ttk.Combobox(self.extras_row, textvariable=self.behaviour_var, state="readonly",
                                         width=8, values=[shown for _, shown in PLAY_BEHAVIOUR])
        self.behaviour_cb.pack(side="left")
        self.behaviour_cb.bind("<<ComboboxSelected>>", self._on_behaviour_changed)
        help_mark(self.extras_row, "Play: the playlist starts as soon as it's found.\n"
                                   "Review: nothing is sent to JRiver. The tracks found are listed in Review, "
                                   "in the console area, where you tick the ones you want in the order you "
                                   "want them, then add them to Playing Now, load them as new or save them "
                                   "as a playlist. A Preview zone lets you listen first.\n"
                                   "For every build from the app, Now Playing and Search. Voice commands, "
                                   "keyboard shortcuts and Non-stop always play straight away. Not used when "
                                   "Output is YouTube.").pack(side="left", padx=(8, 0))
        # AI Moderator sets Windows (Main)'s moderator; devices with settings of their own keep theirs.
        tk.Label(self.extras_row, text="AI Moderator", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["ai_purple"]).pack(side="left", padx=(24, 6))
        self.moderator_var = tk.StringVar(value="Off")
        self.moderator_cb = ttk.Combobox(self.extras_row, textvariable=self.moderator_var,
                                         values=MODERATOR_CHOICES, state="readonly", width=9)
        self.moderator_cb.pack(side="left")
        self.moderator_cb.bind("<<ComboboxSelected>>", self._on_moderator_changed)
        self._moderator_tip = Tooltip(self.moderator_cb, NO_KEY_TEXT, when=lambda: not engine.ai_enabled())
        help_mark(self.extras_row, "Checks Similar Artists and Similar Tracks playlists with the AI's quick "
                                   "model and removes tracks that clash with the seed's tone, energy and mood. "
                                   "Uses a little AI credit, a fraction of a penny per playlist.\n"
                                   + MODERATOR_LEVELS_HELP + "\n"
                                   "Voice devices with settings of their own keep their own choice "
                                   "(Settings > Sources).").pack(side="left", padx=(8, 0))
        # Drift and Non-stop: a second door onto Settings > Playlist for Windows (Main).
        # Changing them here changes them there, for every Play option at once.
        tk.Label(self.extras_row, text="Drift", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["text_secondary"]).pack(side="left", padx=(24, 6))
        self.drift_var = tk.StringVar(value="Off")
        self.drift_cb = ttk.Combobox(self.extras_row, textvariable=self.drift_var,
                                     values=[shown for _, shown in PLAY_DRIFT], state="readonly", width=13)
        self.drift_cb.pack(side="left")
        self.drift_cb.bind("<<ComboboxSelected>>", self._on_drift_changed)
        help_mark(self.extras_row, "Searches again when a playlist comes up short, for Similar Artists, "
                                   "Similar Tracks and AI Playlist. Keep It Tight seeds only from the first "
                                   "round, so nothing strays far (it can finish short); Spread seeds from across "
                                   "the whole playlist and can travel further. Drift using and Rounds are set for "
                                   "each in Settings > Playlist, and changing Drift here changes it there too. "
                                   "Shows a mode only when all three agree. Voice devices with settings of their "
                                   "own keep theirs.").pack(side="left", padx=(8, 0))
        tk.Label(self.extras_row, text="Non-stop", font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["text_secondary"]).pack(side="left", padx=(24, 6))
        self.nonstop_var = tk.StringVar(value="Off")
        self.nonstop_cb = ttk.Combobox(self.extras_row, textvariable=self.nonstop_var,
                                       values=[shown for _, shown in PLAY_NONSTOP],
                                       state="readonly", width=14)
        self.nonstop_cb.pack(side="left")
        self.nonstop_cb.bind("<<ComboboxSelected>>", self._on_nonstop_changed)
        help_mark(self.extras_row, "Keeps the music going: when the last track of a playlist 24bit7 built "
                                   "starts, more are added. Keep It Tight reseeds from the original playlist's "
                                   "tracks, so the evening stays close to where it started; Wander "
                                   "follows the music wherever it leads. Applies to all four Play options. "
                                   "The rest of the Non-stop settings are in Settings > Playlist, and changing "
                                   "Non-stop here changes it there too. Shows a mode only when all four agree. "
                                   "Voice devices with settings of their own keep theirs.").pack(side="left", padx=(8, 0))
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
        self._sync_behaviour()
        panel = getattr(self, "review_panel", None)
        if panel is not None:
            panel.output_changed()   # Review's actions go wherever Output now says

    def _sync_behaviour(self):
        """Review works with any Output, YouTube included (it opens the ticked tracks there)."""
        if getattr(self, "behaviour_cb", None) is not None:
            self.behaviour_cb.state(["!disabled"])

    def _on_behaviour_changed(self, *_):
        code = {shown: c for c, shown in PLAY_BEHAVIOUR}.get(self.behaviour_var.get(), "instant")
        try:
            write_env({"PLAY_BEHAVIOUR": code})
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
        self.behaviour_cb.selection_clear()

    def _review_mode(self):
        return getattr(self, "behaviour_var", None) is not None and self.behaviour_var.get() == "Review"

    def sync_moderator(self):
        """Shows Windows (Main)'s moderator choice, greyed out until the AI is set up."""
        if self.running:
            return   # a voice build may have a device's settings loaded
        engine.refresh_settings_if_changed()
        by = engine.AI_MODERATOR_BY
        levels = {by.get("artists", "off"), by.get("tracks", "off")}
        self.moderator_var.set(levels.pop().title() if len(levels) == 1 else "Off")   # Off unless both agree
        self.moderator_cb.state(["!disabled"] if engine.ai_enabled() else ["disabled"])
        self._moderator_tip.text = (NO_KEY_TEXT if not engine.ai_configured()
                                    else "Paused: Use AI is Off under Settings > Keys.")
        self._sync_ai_button()
        self._sync_play_switches()
        self._update_more_label()

    def _sync_ai_button(self):
        """AI Playlist greys out while Use AI is Off (Settings > Keys) or there's no key."""
        button = next((b for b in self.buttons if b.cget("text") == "AI Playlist"), None)
        if button is None:
            return
        on = engine.ai_enabled()
        if not self.running:
            button.config(state="normal" if on else "disabled")
        if not hasattr(self, "_ai_button_tip"):
            self._ai_button_tip = Tooltip(button, "", when=lambda: not engine.ai_enabled())
        self._ai_button_tip.text = (f"AI Playlist needs {engine.ai_missing_text()} under Settings > Keys."
                                    if not engine.ai_configured() else
                                    "Paused: Use AI is Off under Settings > Keys.")

    def _sync_play_switches(self):
        """Drift and Non-stop as Settings > Playlist has them for Windows (Main): No unless every option agrees."""
        drift = {(engine.DRIFT[g].get("from", "spread") if engine.DRIFT[g]["on"] else "off")
                 for g in DRIFT_GROUPS if g in engine.DRIFT}
        self.drift_var.set(dict(PLAY_DRIFT).get(drift.pop() if len(drift) == 1 else "off", "Off"))
        by = engine.NONSTOP_BY
        states = {(by[g].get("mode", "journey") if by[g]["on"] else "off") for g in NONSTOP_GROUPS if g in by}
        self.nonstop_var.set(dict(PLAY_NONSTOP).get(states.pop() if len(states) == 1 else "off", "Off"))

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
        code = {shown: code for code, shown in PLAY_DRIFT}.get(self.drift_var.get(), "off")
        on = code != "off"
        updates = {f"DRIFT_{g.upper()}": "1" if on else "0" for g in DRIFT_GROUPS}
        if on:
            updates.update({f"DRIFT_{g.upper()}_FROM": code for g in DRIFT_GROUPS})

        def apply(page):
            from settings_gui import sync_drift
            for g in DRIFT_GROUPS:
                if g in getattr(page, "drift", {}):
                    page.drift[g][0].set(on)
                    if on and f"DRIFT_{g.upper()}_FROM" in page.vars:
                        page.vars[f"DRIFT_{g.upper()}_FROM"].set(code)
                    if g in getattr(page, "drift_modes", {}):
                        page.drift_modes[g].set(self.drift_var.get())
            if getattr(page, "drift", None):
                sync_drift(page)
        self.drift_cb.selection_clear()
        self._save_play_switches(updates, apply)

    def _on_nonstop_changed(self, *_):
        code = {shown: c for c, shown in PLAY_NONSTOP}.get(self.nonstop_var.get(), "off")
        on = code != "off"
        updates = {}
        for g in NONSTOP_GROUPS:
            updates[f"NONSTOP_{g.upper()}"] = "1" if on else "0"
            if on:
                updates[f"NONSTOP_{g.upper()}_MODE"] = code

        def apply(page):
            from settings_gui import sync_nonstop
            for g in NONSTOP_GROUPS:
                G = g.upper()
                if f"NONSTOP_{G}" in page.vars:
                    page.vars[f"NONSTOP_{G}"].set(on)
                if on and f"NONSTOP_{G}_MODE" in page.vars:
                    page.vars[f"NONSTOP_{G}_MODE"].set(code)
                if G in getattr(page, "nonstop_modes", {}):
                    page.nonstop_modes[G].set(self.nonstop_var.get())
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
        self.review_panel = ReviewPanel(self)   # Console | Review
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

    def _sync_usage_box(self):
        """
        Shows the AI Usage total pinned to the right edge of Now Playing while it's ticked
        in Settings > Keys. The track text stops short of it, so the two never overlap.
        """
        try:
            engine.refresh_settings_if_changed()
            want = os.getenv("AI_USAGE_NOW_PLAYING", "0").strip() == "1"
            if want:
                self.usage_label.config(text=ai_usage.short(unit=self._usage_unit()))
                self.usage_box.place(relx=1.0, rely=0.5, anchor="e", x=-12)
                self.usage_box.lift()
                self.update_idletasks()
                self._usage_info.pack_configure(padx=(0, self.usage_box.winfo_reqwidth() + 36))
            elif self._usage_shown:
                self.usage_box.place_forget()
                self._usage_info.pack_configure(padx=0)
            self._usage_shown = want
        except Exception as e:
            if not getattr(self, "_usage_error_said", False):
                self._usage_error_said = True
                print(f"  Problem: the AI Usage total couldn't show in Now Playing ({e}).")

    def _usage_unit(self):
        unit = os.getenv("AI_USAGE_NP_UNIT", "dollars").strip().lower()
        return unit if unit in ("dollars", "tokens") else "dollars"

    def _usage_flip(self, _e=None):
        """Clicking the Now Playing total switches it between dollars and tokens, and remembers it."""
        unit = "tokens" if self._usage_unit() == "dollars" else "dollars"
        try:
            write_env({"AI_USAGE_NP_UNIT": unit})
        except Exception as e:
            print(f"  Problem: couldn't save the AI Usage display choice ({e}).")
            return
        self._sync_usage_box()
        if self.settings is not None and hasattr(self.settings, "usage_unit_var"):
            self.settings.usage_unit_var.set(unit.title())

    def _usage_clear(self):
        if messagebox.askyesno("Clear AI Usage", "Clear the token count? It starts again from now.", parent=self):
            ai_usage.clear()
            self._sync_usage_box()
            if self.settings is not None and hasattr(self.settings, "_fill_usage"):
                self.settings._fill_usage()

    def _usage_query(self):
        """Query: Claude reads the token counts and settings, and answers in the console."""
        if getattr(self, "_query_busy", False):
            return
        engine.refresh_settings_if_changed()
        if not engine.ai_configured():
            messagebox.showinfo("AI Usage", NO_KEY_TEXT, parent=self)
            return
        try:
            self.master.select(self)   # asked from Settings: show the console
        except Exception:
            pass
        self._greeting_active = False
        self._query_busy = True
        self._append_query(f"\nYou asked: {ai_usage.QUESTION}\n", bold=True)

        def done(answer, error):
            self._query_busy = False
            self._append_query(f"AI Usage Query didn't come back: {error}\n" if error else answer + "\n")
            self._sync_usage_box()
            if self.settings is not None and hasattr(self.settings, "_fill_usage"):
                self.settings._fill_usage()
        ai_usage.ask(lambda answer, error: self.after(0, lambda: done(answer, error)))

    def _refresh_now_playing(self):
        # Nobody can see the panel while 24bit7 is minimised or in the tray, so JRiver
        # isn't asked. The Play buttons and shortcuts read the zone fresh when pressed.
        if not self.running and self._window_visible():
            self._update_now_playing()
        self.after(REFRESH_MS, self._refresh_now_playing)

    def _update_now_playing(self):
        """
        Asks JRiver what's playing, in the background, so the window never waits for JRiver
        (it can be slow to answer while it sends the whole library at startup). The panel
        updates when the answer arrives (_np_poll); until then it shows what it last knew.
        """
        self._sync_usage_box()
        if getattr(self, "_np_busy", False):
            self._np_again = True   # ask once more as soon as this answer is in
            return
        self._np_busy, self._np_again, self._np_result = True, False, None
        engine.refresh_settings_if_changed()
        threading.Thread(target=self._np_fetch, daemon=True, name="now-playing").start()
        self.after(40, self._np_poll)

    def _np_fetch(self):
        """In the background: the zone to follow (as _follow_active_zone decides it), then what's playing there."""
        name = note = None
        info = None
        try:
            if not self._zone_picked and (not self._zone_settled or engine.FOLLOW_ACTIVE_ZONE):
                zones, current = engine._read_zones()
                if zones:
                    names = [n for _, n in zones]
                    follow, pick = engine.FOLLOW_ACTIVE_ZONE, ""
                    if engine.DEFAULT_ZONE and not follow and not self._zone_settled:
                        if engine.DEFAULT_ZONE in names:
                            pick = engine.DEFAULT_ZONE
                        else:
                            note = (f"Default zone '{engine.DEFAULT_ZONE}' wasn't found in JRiver, "
                                    f"so Now Playing opened on the active zone.")
                    if not pick:
                        pick = next((n for i, n in zones if i == current), "")
                    name = pick
                    if not self._zone_picked:   # a zone picked by hand meanwhile wins
                        engine.SEED_ZONE_NAME = pick or None
            info = engine.get_playing_info()
        except Exception as e:
            engine.debug(f"Now Playing couldn't ask JRiver ({e})")
        self._np_result = (name, note, info)

    def _np_poll(self):
        """On the window's worker: shows the background answer once it's in."""
        result = self._np_result
        if result is None:
            self.after(40, self._np_poll)
            return
        self._np_result, self._np_busy = None, False
        name, note, info = result
        if name is not None and not self._zone_picked:
            self._zone_settled = True
            if self.zone_var.get() != name:
                self.zone_var.set(name)
        if note:   # after the greeting has cleared the log, so the note isn't wiped with it
            self.after(13000 if self._greeting_active else 0, lambda: self.report(note))
        self._show_playing(info)
        if self._np_again:
            self._np_again = False
            self._update_now_playing()

    def _show_playing(self, info):
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
        if getattr(self, "review_panel", None) is not None:
            self.review_panel.console_activity()   # a dot on Console while Review is showing
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
        self.console_head = tk.Frame(self.console_box, bg=black)   # packed only while the tabs are open
        # Closed, the arrow floats over the top middle of the text, so the text starts on the first line
        self.head_arrow = tk.Label(self.console_box, text="\u25bc", font=("Consolas", 10), bg=black, fg=green,
                                   cursor="hand2", padx=10)
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
            self.head_arrow.place_forget()
            if not self.console_head.winfo_manager():
                self.console_head.pack(fill="x", before=self.log.frame)
            self.head_arrow.pack(in_=self.console_head, anchor="n")
            self.head_row.pack(fill="x", padx=8, pady=(0, 6))
            self.head_line.pack(fill="x", padx=8, pady=(0, 4))
            self.console_strip.place_forget()
            self._sync_head_query()
            self._fill_tabs()
        else:
            self.head_row.pack_forget()
            self.head_line.pack_forget()
            self.head_arrow.pack_forget()
            self.console_head.pack_forget()
            if self.view != "all":
                self._select_view("all")
            self.head_arrow.place(in_=self.log, relx=0.5, y=0, anchor="n")
            self.head_arrow.lift()
        panel = getattr(self, "review_panel", None)
        if panel is not None:
            panel.dock_arrow()   # with the Console | Review switch showing, the arrow sits in its row
        if save:
            try:
                write_env({"CONSOLE_TABS": "1" if open_ else "0"})
            except Exception:
                pass

    # --- the Log tab: the last 50 builds from each source, newest first ---

    # (title, width in characters); Sources Used (width 1) takes whatever room is left
    LOG_COLUMNS = [("Date and Time", 13), ("From", 12), ("Zone", 9), ("Playlist Type", 30),
                   ("Sources Used", 1), ("Hits / Misses", 13), ("AI Moderator", 20), ("Problems", 17), ("", 15)]
    SOURCES_COLUMN = 4

    def _sync_head_strip(self):
        """On the Log tab only Simple/Advanced shows; on a console tab, the whole strip."""
        on_log = self.view == "log"
        for name in ("Copy", "Clear", "Export to Log"):
            self.head_buttons[name].pack_forget()
        self.head_buttons["Query"].pack_forget()
        if not on_log:
            for name in ("Copy", "Clear", "Export to Log"):
                self.head_buttons[name].pack(side="left", padx=(4, 0), before=self.head_buttons["Mode"])
            self._sync_head_query()

    def _show_console_text(self):
        if getattr(self, "log_table", None) is not None and self.log_table.winfo_manager():
            self.log_table.pack_forget()
            self.log.pack(fill="both", expand=True)

    def _build_log_table(self):
        black = "#000000"
        self.log_table = tk.Frame(self.console_box, bg=black)
        canvas = tk.Canvas(self.log_table, bg=black, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(self.log_table, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.log_grid = tk.Frame(canvas, bg=black, padx=8, pady=6)
        window = canvas.create_window((0, 0), window=self.log_grid, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        self.log_grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def wheel(e):
            canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self.log_canvas = canvas

    def _show_log_table(self):
        if getattr(self, "log_table", None) is None:
            self._build_log_table()
        if self.log.winfo_manager():
            self.log.pack_forget()
        if not self.log_table.winfo_manager():
            self.log_table.pack(fill="both", expand=True)
        self._fill_log_table()

    def _fill_log_table(self):
        black, green, dim, white = "#000000", "#00ff41", "#0d4d1c", "#ffffff"
        grid = self.log_grid
        for child in grid.winfo_children():
            child.destroy()
        font, bold = ("Consolas", 9), ("Consolas", 9, "bold")
        cols = len(self.LOG_COLUMNS)
        grid.grid_columnconfigure(self.SOURCES_COLUMN, weight=1)
        for c, (title, width) in enumerate(self.LOG_COLUMNS):
            tk.Label(grid, text=title, font=bold, bg=black, fg=white, anchor="w", width=width).grid(
                row=0, column=c, sticky="ew", padx=(0, 6), pady=(0, 4))
        tk.Frame(grid, bg=green, height=1).grid(row=1, column=0, columnspan=cols, sticky="ew")
        try:
            rows = buildlog.recent()
        except Exception:
            rows = []
        r = 2
        for row in rows:
            when = row["at"]
            try:
                when = datetime.strptime(row["at"], "%Y-%m-%d %H:%M:%S").strftime("%d %b %H:%M")
            except (TypeError, ValueError):
                pass
            if row["queued"] is None:
                hits = ""
            elif row["misses"] is None:
                hits = f"{row['queued']} sent"
            else:
                hits = f"{row['queued']} / {row['misses']}"
            trouble = ", ".join(x for x in (
                f"{row['problems']} problem{'' if row['problems'] == 1 else 's'}" if row["problems"] else "",
                f"{row['notes']} note{'' if row['notes'] == 1 else 's'}" if row["notes"] else "") if x)
            values = [(when, green), (row["from_label"] or "", green), (row["zone"] or "", green),
                      (buildlog.playlist_type(row), green), (row["sources"] or "", green), (hits, green),
                      (row["moderator"] or "", AI_MAGENTA),
                      (trouble, "#ff6b6b" if row["problems"] else "#ffb000")]
            cells = []
            for c, (value, colour) in enumerate(values):
                width = self.LOG_COLUMNS[c][1]
                if c != self.SOURCES_COLUMN and len(value) > width:   # too long for its column: cut short
                    value = value[:width - 3] + "..."
                cell = tk.Label(grid, text=value, font=font, bg=black, fg=colour, anchor="w",
                                width=self.LOG_COLUMNS[c][1])
                cell.grid(row=r, column=c, sticky="ew", padx=(0, 6), pady=3)
                if c == self.SOURCES_COLUMN and value:   # the column narrows with the window: full list on hover
                    Tooltip(cell, value)
                cells.append(cell)
            link = tk.Label(grid, text="Load to Console", font=("Consolas", 9, "underline"), bg=black, fg=green,
                            cursor="hand2", anchor="w")
            link.grid(row=r, column=cols - 1, sticky="w", pady=3)
            link.bind("<Button-1>", lambda e, b=row: self._load_build(b))
            for cell in cells:
                cell.bind("<Double-Button-1>", lambda e, b=row: self._load_build(b))
            tk.Frame(grid, bg=dim, height=1).grid(row=r + 1, column=0, columnspan=cols, sticky="ew")
            r += 2
        if not rows:
            tk.Label(grid, text="No builds kept yet. Each build appears here once it finishes.", font=font,
                     bg=black, fg="#5f7a66", anchor="w").grid(row=r, column=0, columnspan=cols, sticky="w", pady=6)
        else:
            tk.Label(grid, text="The last 50 builds from each source, newest first. Double-click a row, "
                                "or use Load to Console.", font=font, bg=black, fg="#5f7a66", anchor="w").grid(
                row=r, column=0, columnspan=cols, sticky="w", pady=(8, 0))
        self.log_canvas.yview_moveto(0)

    def _load_build(self, row):
        """Opens a kept build in its source's tab, with a line saying so and a way back to the latest."""
        self.view = row["tab"] or "main"
        self._fill_tabs()
        self._sync_head_strip()
        self._show_console_text()
        when = (row["at"] or "")[11:16]
        chain = f" (Non-stop {row['chain_pos']:03d})" if row.get("chain_pos") else ""
        source = "Main Window" if self.view == "main" else buildlog.device_name(self.view)
        self._show_text(row["text"] or "")
        self.log.config(state="normal")
        self.log.tag_configure("back", foreground="#00ff41", underline=True)
        self.log.tag_bind("back", "<Button-1>", lambda e, v=self.view: self._select_view(v))
        self.log.tag_bind("back", "<Enter>", lambda e: self.log.config(cursor="hand2"))
        self.log.tag_bind("back", "<Leave>", lambda e: self.log.config(cursor=""))
        self.log.insert("1.0", "\n")
        self.log.insert("1.0", f"Loaded from Log: {source}, {when}{chain}  \u00b7  ")
        self.log.insert("1.end", "Back to Latest", ("back",))
        self.log.see("1.0")
        self.log.config(state="disabled")

    def sync_console_buttons(self):
        """The Query buttons come and go with Console Query and Use AI (Settings)."""
        self._sync_head_query()
        if self.console_strip.winfo_manager():
            self._show_console_strip()
        elif not (getattr(engine, "CONSOLE_QUERY", False) and engine.console_query_ready()):
            self.console_buttons["Query"].pack_forget()

    def _sync_head_query(self):
        engine.refresh_settings_if_changed()
        query = self.head_buttons["Query"]
        if getattr(engine, "CONSOLE_QUERY", False) and engine.console_query_ready() and self.view != "log":
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
        for key, label in [("all", "All"), ("main", "Main Window")] + devices + [("log", "Log")]:
            b = self._head_box(self.head_tabs, label, lambda k=key: self._select_view(k))
            if key == self.view:   # the tab on screen: inverted, green with black text
                b.config(bg="#00ff41", fg="#000000", font=("Consolas", 9, "bold"), highlightbackground="#00ff41")
            b.pack(side="left", padx=(0, 4))

    def _live_visible(self):
        return self.view == "all" or self.view == self._live_tab

    def _select_view(self, view):
        """Shows a tab: All is the latest build from anywhere; the others, their own latest; Log, the table."""
        self.view = view
        self._fill_tabs()
        self._sync_head_strip()
        if view == "log":
            self._show_log_table()
            return
        self._show_console_text()
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
        if getattr(engine, "CONSOLE_QUERY", False) and engine.console_query_ready():
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
        tk.Label(row, text="Ask the AI", font=("Segoe UI", 9, "bold"),
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
        if not engine.ai_configured():
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

    def _run_job(self, target, needs_playing=True, mix=True, origin=None, review=False):
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
        review = review and bool(mix) and self._review_mode()   # Review: app builds, never voice
        self._job_review = review
        if origin is None and getattr(self, "review_panel", None) is not None:
            self.review_panel.show_console()   # a build from the window: watch it run in the console

        def worker():
            engine.MIX_ROWS, engine.MIX_KEEP, engine.MIX_FAST_KEY, engine.MIX_NOTED = rows, set(), None, False
            engine.REVIEW_MODE = review
            overrides = {}
            engine.BUILD_STARTED, engine.LAST_OUTPUT = time.time(), None
            engine.LAST_OUTPUT_ID, engine.LAST_BUILD = None, None
            try:
                if review:
                    engine.review_reset()
                    overrides = engine.review_overrides()   # Settings > Playlist's Review column
                    if overrides:
                        engine.use_profile(overrides)
                        self.log_queue.put("  Review settings in use (Settings > Playlist, the Review column).")
                target()
                if review:
                    engine.REVIEW_ROWS = engine.review_rows(engine.REVIEW_KEYS)
            except Exception as e:
                self.log_queue.put(f"Problem: something went wrong ({e}). Press Export to Log "
                                   f"and attach the file when you report it.")
            finally:
                engine.MIX_ROWS, engine.MIX_KEEP, engine.MIX_FAST_KEY = None, set(), None
                if overrides:
                    engine.use_profile({})   # back to Windows (Main)'s own figures
                engine.REVIEW_MODE = False
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
        if hotkeys.take_restart():   # Switch Profiles queued a profile: restart now the job is done
            self.root.after(500, lambda: self.root.event_generate("<<Restart24bit7>>"))
        if getattr(self, "view", None) == "log":
            self._fill_log_table()
        self.running = False
        for b in self.buttons:
            b.config(state="normal")
        self._sync_ai_button()
        self._sync_seed_buttons()
        if getattr(self, "_job_review", False):   # a Review build: its tracks go to the Review list
            self._job_review = False
            self.review_panel.load(getattr(engine, "REVIEW_ROWS", []), self._review_title(),
                                   engine.REVIEW_ZONE)

    def _review_title(self):
        """The build's first line, without its time or the settings in brackets after it."""
        for line in self._live:
            if line.strip() and not line.startswith((" ", "\n")):
                return re.sub(r"^\d\d:\d\d  ", "", line.strip()).split("  (")[0]
        return "Review"

    def on_similar(self):
        if self._seed_is_search():
            seed = self._typed_seed(need_track=engine.similar_needs_track(),
                                    why=engine.SIMILAR_NEEDS_TRACK_TEXT)
            if seed:
                self._run_job(lambda: engine.create_similar_playlist(report=self.report, seed_info=seed),
                              needs_playing=False, review=True)
            return
        self._run_job(lambda: self._seeded(engine.create_similar_playlist), needs_playing=False, review=True)

    def on_similar_tracks(self):
        if self._seed_is_search():
            seed = self._typed_seed(need_track=True)
            if seed:
                self._run_job(lambda: engine.create_similar_tracks_playlist(report=self.report, seed_info=seed),
                              needs_playing=False, review=True)
            return
        self._run_job(lambda: self._seeded(engine.create_similar_tracks_playlist), needs_playing=False,
                      review=True)

    def on_top_tracks(self):
        if self._seed_is_search():
            seed = self._typed_seed(need_track=False)
            if seed:
                self._run_job(lambda: engine.play_top_n(report=self.report, seed_info=seed),
                              needs_playing=False, review=True)
            return
        self._run_job(lambda: self._seeded(engine.play_top_n), needs_playing=False, review=True)

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
        AIPlaylistDialog(self.root, play=self, on_create=lambda theme, count, if_short: self._run_job(
            lambda: engine.create_vibe_playlist(theme, count=count, if_short=if_short, report=self.report),
            needs_playing=False, review=True), on_steer=lambda spec: self._run_job(
            lambda: engine.steer_playlist(engine.steer_seed_pairs(all_tracks=spec["seed_kind"] == "all"),
                                          spec["directions"], spec["own_words"], spec["strength"], spec["tone"],
                                          spec["count"], report=self.report, if_short=spec["if_short"]),
            needs_playing=False, review=True))


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
    loaded_profile = profiles.apply_pending()   # a profile chosen with Load, before anything reads a setting
    root = tk.Tk()
    root.withdraw()   # built out of sight and shown once it's ready, so it doesn't flash up small first
    _set_window_icon(root)
    apply_theme(root, engine.THEME)   # before any widgets, so they all pick it up
    root.title(f"24bit7  v{engine.VERSION}")
    # Open at 75% of the screen so it fits any monitor/DPI, then centre it.
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = int(sw * 0.75), int(sh * 0.75)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    root.minsize(680, 480)

    nb = TabbedPane(root, font=("Segoe UI", 11, "bold"), pad=(20, 8), strip=True)
    nb.pack(fill="both", expand=True)

    play = PlayTab(nb, root)
    discover = DiscoverTab(nb)
    settings = SettingsTab(nb)
    play.settings = settings   # the Play tab's Drift and Non-stop change Settings > Playlist
    settings.play = play       # Settings > Keys > Use AI greys the Play tab's AI pieces out or back in
    if loaded_profile:
        root.after(800, lambda: print(f'Profile "{loaded_profile}" loaded.'))
    nb.add(play, text="Play")
    nb.add(discover, text="Discover")
    nb.add(settings, text="Settings")

    # Support link: top right of the tab row, so it shows from every tab. It opens the
    # Support window (support_gui.py). It is hidden if the window is too narrow for it
    # to sit clear of the tab buttons.
    donate = tk.Label(root, text="Support", font=("Segoe UI", 9, "underline"),
                      fg=PALETTE.get("strip_fg") or PALETTE["link"], bg=PALETTE.get("strip_bg") or root.cget("bg"),
                      cursor="hand2")
    donate.bind("<Button-1>", lambda e: support_gui.show(root))

    chrome_room = {"w": 0}   # the built-in title bar's buttons, when it's on

    def place_donate(event=None):
        if event is not None and event.widget is not root:
            return
        room = root.winfo_width() - nb.tabs_width() - donate.winfo_reqwidth() - 40 - chrome_room["w"]
        if room > 0:
            strip = nb._strip
            donate.place(relx=1.0, x=-16 - chrome_room["w"],
                         y=nb.winfo_y() + strip.winfo_y() + strip.winfo_height() // 2, anchor="e")
            donate.lift()
        else:
            donate.place_forget()
    root.bind("<Configure>", place_donate, add="+")
    root.after(100, place_donate)

    # The built-in title bar (Windows): the strip runs to the top of the window, with its own
    # minimise, maximise and close. Settings > Other > Use the Windows title bar turns it off.
    if os.name == "nt" and os.getenv("WINDOWS_TITLE_BAR", "0").strip().lower() not in ("1", "true", "yes"):
        try:
            chrome_room["w"] = window_chrome.attach(root, nb).width
            root.after(150, place_donate)
        except Exception as e:
            root.after(13000, lambda e=e: play.report(f"Note: the built-in title bar couldn't be set up ({e}), "
                                                      f"so the Windows one is used."))

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
    hotkeys.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)),
                   busy=lambda: play.running or not play.voice_jobs.empty(), note=play.report)
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
    hidden = False
    if engine.CLOSE_TO_TRAY or (tray.started_by_windows() and engine.START_IN_TRAY):
        if tray.start(root, show_window, quit_app) and tray.started_by_windows() and engine.START_IN_TRAY:
            hidden = True   # started by Windows into the tray: stays out of sight
    if not hidden:
        root.deiconify()

    root.mainloop()
    if restart["on"]:
        import subprocess
        frozen = getattr(sys, "frozen", False)   # the built .exe is its own program
        subprocess.Popen([sys.executable] + (sys.argv[1:] if frozen else sys.argv), cwd=engine.APP_DIR)


if __name__ == "__main__":
    main()
