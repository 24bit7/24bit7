"""
24bit7 - main window.

Three tabs in one window:
  Play      - now-playing, the three playlist actions, and a live log
  Discover  - browse logged discoveries (built in the next step)
  Settings  - auto-saving preferences and keys

The Play tab drives engine.py on a background thread, streaming progress into
its log via a thread-safe queue so the window never freezes.
"""

import sys

if "--follow" in sys.argv[1:]:
    # The Multiroom follower, run as a child of the app (24bit7.exe --follow --port N): no window, no Tk, and
    # none of the start-up below. See multiroom/service.py.
    from multiroom import service
    sys.exit(service.main(sys.argv[1:]))

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
import i18n
from i18n import N_, t, tn
import library
import tray
import voice
import hotkeys
import nonstop
from settings_gui import SettingsTab, write_env, read_env, Tooltip, NO_KEY_TEXT, ask_new_button, warn_moderator_once
from discover_gui import DiscoverTab
import tabs
from tabs import TabbedPane, PALETTE, FlatButton, InfoLine, apply_theme, ClickThrough, RoundedEntry
import buttons
from mix_gui import MixRows
from review_gui import ReviewPanel
import badge
import console_query
import playmix
import embellish
import radio
import overrides
import mode
import profiles
from ai_dialog import AIPlaylistDialog
import buildlog
import support_gui
import window_chrome
import ai_usage
from multiroom import link as multiroom_link

MULTIROOM_LABEL = engine.MULTIROOM_NAME   # the Output entry; a feature name, so not translated


def advanced_only(line):
    """
    A console line the Simple console leaves out and Advanced shows: the engine's [debug] lines, and the Multiroom
    follower's commentary (Ben, 10 Nov 2026). Hidden on screen, and left out of Copy and Console Query in Simple,
    which read what you see. A Multiroom problem always shows, and so does a note about something you can hear.
    """
    body = re.sub(r"^\d\d:\d\d  ", "", line.strip())
    return body.startswith("[debug]") or multiroom_link.advanced_only(line)


REFRESH_MS = 10000   # Now Playing panel; paused while minimised or in the tray
POLL_MS = 100
DONATE_URL = "https://paypal.me/24bit7"
SAME_ZONE_LABEL = N_("Same zone")   # shown and compared as t(SAME_ZONE_LABEL)
AI_MAGENTA = "#ff33ff"   # AI lines and Query in the console, which is always black
CONSOLE_MODES = (N_("Simple"), N_("Advanced"))
# The words a console line starts with, which set its colour (and the Log's counts): engine writes them
# through t(), so they're recognised in English and in the chosen language
PROBLEM, NOTE, DONE, REMOVED = N_("Problem:"), N_("Note:"), N_("Done:"), N_("Removed")   # the console's Mode button shows these, through t()

WELCOME_TEXT = N_(
    "Welcome to 24bit7!\n\n"
    "A starter settings file has been created. Playlists work out of the box "
    "using Deezer and YouTube, which need no keys.\n\n"
    "For richer blends, add free keys for Last.fm and ListenBrainz under "
    "Settings > Keys (the ? buttons explain how), then tick them on a button's "
    "Sources page under Settings > Buttons.\n\n"
    "JRiver needs Media Network enabled: Tools > Options > Media Network."
)


# The values below stay English in code (the switches hold and compare them); they show through t()
PLAY_BEHAVIOUR = [("instant", N_("Play")), ("review", "Review")]   # every build from the app, not voice
# What each Play tab control does, shown on hover only while the More Options row's ? is on.
# A button of your own gets its kind's note, and every button adds a line saying what it has on.
PLAY_NOTES = {
    "Similar Artists": N_("Finds artists like the seed's, then plays their best known tracks you own."),
    "Similar Tracks": N_("Finds songs like the seed track, from every source ticked on its Sources page."),
    "Artist's Top Tracks": N_("Plays the seed artist's most popular tracks that you own."),
    "Artist + Guests": N_("The seed artist's most popular tracks, two at a time, with one track from a close similar "
                    "artist you own between them."),
    "Consensus": N_("Artist Matching with Consensus on: the seed's three closest artists, then only the artists "
                       "their own lists agree on. Tight, and sometimes short."),
    "AI Playlist": N_("Describe a mood or moment and the AI picks tracks for it, from your library. Uses AI credits."),
    "+": N_("Puts a playlist you've taken off the row back, or makes a new one. Right-click any playlist to rename, "
            "copy, move or remove it; hold one to drag it."),
    "More Options": N_("Opens the row below: Seed, Mode, your JRiver playlists and Show Credits."),
    "Output": N_("Where the finished playlist goes: the zone you seeded from, another JRiver zone, or YouTube or "
                 "Tidal (ticked under Settings > Other > Additional Outputs)."),
    "Zone": N_("Which JRiver zone Now Playing shows and seeds from. Multiroom shows the leader zone, and is picked by "
               "itself when the Speakers start following."),
    "Seed": N_("What Similar Artists and Similar Tracks start from: the current track, or every track in Playing Now."),
    "Moderator": N_("While this row is open, the Moderator runs at this level for every playlist: Off, Relaxed, "
                    "Balanced or Strict. Click to step through them. Uses AI credits."),
    "Deep Cuts": N_("While this row is open, Deep Cuts are added this way for every playlist: Off, Spaced or "
                    "Shuffled. Click to step through them. How many is each playlist's own."),
    "Non-stop": N_("While this row is open, Non-stop keeps the music going this way for every playlist: Off, Keep It "
                   "Tight or Wander. Click to step through them. What it plays using is each playlist's own."),
    "Mode": N_("Play Mode plays the playlist straight away. Review Mode lists it first, so you choose what goes."),
    "+ Add JRiver Playlist": N_("Joins one of your own JRiver playlists to the next build."),
    "Top-Up": N_("Click Top-Up, then a playlist: it goes into what's left of Playing Now instead of replacing it. "
                 "The track playing carries on, nothing already there is added twice, and the rest is shuffled "
                 "together. Lasts one playlist; click Top-Up again to cancel."),
    "Show Credits": N_("Lists the producer, engineer, musicians and other credits for what's playing, from Discogs."),
    "Stop": N_("Stops this zone; in multiroom, both rooms. Once the zone is stopped the button reads Clear Playing "
               "Now, in red, and one click empties the zone's list."),
    "Skip Track": N_("The next track in this zone's list. Greyed while the zone is stopped or nothing follows."),
    "Help": N_("Hover notes for the Play tab: on, hovering over anything here explains it; off, no pop-ups."),
    "Playlist": N_("One of your JRiver playlists or smartlists. Click into the box for the list, the five you played "
                   "here most recently at the top; type to narrow it."),
    "Play": N_("Plays the playlist as it is. The arrow chooses Play Shuffled or Play Ordered."),
    "Play & Embellish": N_("Plays the playlist with new tracks woven in: the top tracks you own by artists that the "
                           "playlist's own artists agree on. The arrow chooses how many; Shuffle, Deep Cuts "
                           "and the Moderator are under Settings > JRiver Playlists."),
    "Radio": N_("Plays a station of what you listen to, with no seed: your stations come from your plays and "
                "the sources' genres. Click Radio for the last station you played; the arrow lists them all. "
                "Right-click a station to split it or add it as a button."),
    "Save Playlist": N_("Saves what's in Playing Now in the zone the last playlist went to as a JRiver playlist, so "
                        "a chain of Top-Ups or an embellished playlist can be kept."),
}
PLAYLISTS_SHOWN = 15   # rows of the All Playlists part of the list before "type to narrow"
MONTHS = (N_("Jan"), N_("Feb"), N_("Mar"), N_("Apr"), N_("May"), N_("Jun"), N_("Jul"), N_("Aug"), N_("Sep"),
          N_("Oct"), N_("Nov"), N_("Dec"))
BUTTON_GAP = 8   # between the Play tab's buttons, and between its rows of them
LIST_BOX_GAP = 24   # JRiver Playlists: between the Playlist box and Play
LIST_BOX_HEIGHT = 0.82   # and the box's height, as a share of the buttons'


class DropPill(tk.Canvas):
    """
    A drop target while a playlist is dragged (Settings, Remove): a pill with a thin dashed outline
    in its colour, filled in with that colour while the pointer is over it.
    """

    def __init__(self, master, w, h, text, colour, bg, font, px):
        super().__init__(master, width=w, height=h, bg=bg, bd=0, highlightthickness=0)
        self._pw, self._ph, self._text, self._colour, self._font, self._px = w, h, text, colour, font, px
        self.lit = None
        self.set_lit(False)

    def set_lit(self, on):
        if on == self.lit:
            return
        self.lit = on
        self.delete("all")
        c, px = self._colour, self._px
        w, h = self._pw - 1, self._ph - 1
        r = h // 2
        if on:
            self.create_oval(0, 0, 2 * r, h, fill=c, outline=c)
            self.create_oval(w - 2 * r, 0, w, h, fill=c, outline=c)
            self.create_rectangle(r, 0, w - r, h, fill=c, outline=c)
            fg = "#000000"
        else:
            dash, line = (px(5), px(4)), px(1)
            self.create_arc(0, 0, 2 * r, h, start=90, extent=180, style="arc", outline=c, width=line, dash=dash)
            self.create_arc(w - 2 * r, 0, w, h, start=-90, extent=180, style="arc", outline=c, width=line, dash=dash)
            self.create_line(r, 0, w - r, 0, fill=c, width=line, dash=dash)
            self.create_line(r, h, w - r, h, fill=c, width=line, dash=dash)
            fg = c
        self.create_text(self._pw / 2, self._ph / 2, text=self._text, font=self._font, fill=fg)


class PlayTab(tk.Frame):
    def __init__(self, master, root):
        super().__init__(master)
        self.root = root
        self.settings = None   # the Settings tab, once built
        root.bind("<<ButtonsChanged>>", lambda e: self.refresh_buttons(), add="+")   # from Settings > Buttons
        root.bind("<<RadioAnalyse>>", lambda e: self.on_radio_analyse(True), add="+")    # Radio's page: Re-analyse
        root.bind("<<RadioRecount>>", lambda e: self.on_radio_analyse(False), add="+")   # Radio's page: a new count
        root.bind("<<EmbellishAmounts>>", lambda e: self._sync_amounts(), add="+")   # Settings > JRiver Playlists
        self.log_queue = queue.Queue()
        engine.OUTPUT_HOOK = self.log_queue.put
        # Multiroom: the follower's child process, its lines in the console as "Multiroom: ..."
        self.multiroom = multiroom_link.Link(say=self.log_queue.put,
                                             on_state=lambda s: self.after(0, self._multiroom_state, s))
        engine.MULTIROOM_HOOK = self.multiroom_build_sent   # engine's print() and [debug] lines land here
        self.running = False
        self.last_playing = None
        self.voice_jobs = queue.Queue()   # (job, heading) from voice commands, run one at a time
        self.badge = badge.Badge(root)    # voice builds show on it, over Theater View
        self.badge_problems = queue.Queue()   # (asked, what Alexa said) from the voice thread

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
        self.dev_tag = None
        if engine.dev_copy():   # a copy run from a dev checkout says so beside the version (Ben, 11 Nov 2026)
            self.dev_tag = tk.Label(header, text="Dev", font=("Segoe UI", 9, "bold"), fg="#ffffff",
                                    bg=PALETTE["logo_bit"], padx=6)
            self.dev_tag.pack(side="right", anchor="s", padx=(0, 8), pady=(0, 5))
        title = tk.Frame(header)
        title.pack(side="left", anchor="w")
        BLUE, BIT = PALETTE["brand_blue"], PALETTE["logo_bit"]
        for part, colour in (("24", BLUE), ("bit", BIT), ("7", BLUE)):
            tk.Label(title, text=part, font=("Segoe UI", 18, "bold"),
                     fg=colour).pack(side="left", padx=0)
        # The tagline sits beside the logo after a "/", both at their usual sizes
        tk.Label(title, text="/", font=("Segoe UI", 10),
                 fg=PALETTE["text_muted"]).pack(side="left", anchor="s", padx=(12, 8), pady=(0, 5))
        tk.Label(title, text=t("Perfect Playlists and Music Discovery"),
                 font=("Segoe UI", 10), fg=PALETTE["text_muted"]).pack(side="left", anchor="s", pady=(0, 5))

        # The seed area: two small tabs. Whichever is showing when a button is
        # pressed is the seed - what JRiver is playing, or a typed artist and track.
        outer = tk.Frame(self, pady=8)   # no side margin: the line under the two tabs spans the window
        outer.pack(fill="x")
        self.seed_nb = TabbedPane(outer, font=("Segoe UI", 9, "bold"), pad=(14, 4), indent=22, even=True)
        self.seed_nb.pack(fill="x")

        frame = tk.Frame(self.seed_nb, padx=26, pady=8)
        self.seed_nb.add(frame, text=t("Now Playing"))
        # Zone first: which JRiver zone Now Playing reads and seeds from. Not saved,
        # so every launch starts on the active zone. The list rescans when opened.
        zone_box = tk.Frame(frame)
        zone_box.pack(side="left", padx=(0, 32))
        tk.Label(zone_box, text=t("Zone"), font=("Segoe UI", 9, "bold"), fg=PALETTE["text_secondary"]).pack(side="left", padx=(0, 6))
        self.zone_var = tk.StringVar(value="")
        self._zone_picked = False    # picked by hand: stays put until the next launch
        self._zone_settled = False   # launch zone chosen (default or active zone)
        self.zone_cb = ttk.Combobox(zone_box, textvariable=self.zone_var, values=[],
                                    state="readonly", width=24, postcommand=self._fill_zone_list)
        self.zone_cb.pack(side="left")
        self.zone_cb.bind("<<ComboboxSelected>>", self._on_zone_changed)

        # Stop (amber; Clear Playing Now in red once the zone is stopped) and Skip Track, for whichever zone
        # the row shows (Ben, 9 Nov 2026; mock-up mockups/now_playing_buttons.html). Packed on the right before
        # the track text, so they keep their room and the text takes what's left: an InfoLine asks for eighty
        # characters, and packed after it the buttons were clipped off the row.
        self._np_controls = tk.Frame(frame)
        self._np_controls.pack(side="right", padx=(12, 0))   # _place_output adds the room Output takes
        self.stop_button = FlatButton(self._np_controls, text=t("Stop"), command=self._stop_clicked, width=16,
                                      height=1, quiet=True)
        self.stop_button.pack(side="left")
        self.skip_button = FlatButton(self._np_controls, text=t("Skip Track"), command=self._skip_clicked, width=10,
                                      height=1, quiet=True)
        self.skip_button.pack(side="left", padx=(8, 0))
        self._np_stopped = None   # what the buttons last read: None before the first answer

        info = tk.Frame(frame)
        info.pack(side="left", fill="x", expand=True)
        # Grey "Track:", "Artist:" and "Album:" before the names; both lines wrap as needed
        # One prefix size for all three, and a shared tab stop just after "Artist:"
        # so the track title and the artist name start at the same point
        prefix_font = tkfont.Font(family="Segoe UI", size=7)
        self._prefix_font = prefix_font
        tab = max(prefix_font.measure(t("Track:")), prefix_font.measure(t("Artist:"))) + prefix_font.measure("  ")
        self.np_track = InfoLine(info, font=("Segoe UI", 11, "bold"), fg=PALETTE["brand_blue"],
                                 prefix_font=prefix_font, tab=tab)
        self.np_track.pack(anchor="w", fill="x")
        self.np_detail = InfoLine(info, font=("Segoe UI", 10), fg=PALETTE["text_secondary"], prefix_font=prefix_font, tab=tab)
        self.np_detail.pack(anchor="w", fill="x")
        self.np_track.show(("...", None))
        self._sync_np_controls(None)

        # AI Usage at the far right, while "Show in Now Playing" is ticked in Settings > Keys
        self.usage_box = tk.Frame(self.seed_nb)
        self.usage_label = tk.Label(self.usage_box, text="", font=("Segoe UI", 9), fg=PALETTE["ai_purple"])
        self.usage_label.pack(side="left", padx=(0, 10))
        self.usage_label.config(cursor="hand2")
        self.usage_label.bind("<Button-1>", self._usage_flip)   # dollars or tokens
        FlatButton(self.usage_box, text=t("Clear"), command=self._usage_clear, width=6, height=1,
                   quiet=True).pack(side="left")
        FlatButton(self.usage_box, text=t("Query"), command=self._usage_query, width=6, height=1,
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

        self._build_playlists_tab()

        self.search_tab = tk.Frame(self.seed_nb, padx=26, pady=8)
        self.seed_nb.add(self.search_tab, text=t("Search"))
        self.search_tab.grid_anchor("w")   # the boxes and the line under them centred in the panel, as one
        fields = tk.Frame(self.search_tab)   # one row, so each title sits right beside its box
        fields.grid(row=0, column=0, columnspan=4, sticky="w")
        tk.Label(fields, text=t("Artist"), font=("Segoe UI", 10)).pack(side="left")
        self.search_artist = RoundedEntry(fields, width=30, font=("Segoe UI", 9))
        self.search_artist.pack(side="left", padx=(4, 24))
        tk.Label(fields, text=t("Track"), font=("Segoe UI", 10)).pack(side="left")
        self.search_track = RoundedEntry(fields, width=30, font=("Segoe UI", 9))
        self.search_track.pack(side="left", padx=(4, 0))
        tk.Label(self.search_tab, text=t("Build a playlist from any track, even one you don't own. "
                                         "Only Track Matching needs the track; the other playlists need "
                                         "just the artist. Press Enter for Similar Artists."),
                 font=("Segoe UI", 8), fg=PALETTE["text_muted"]).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        for entry in (self.search_artist, self.search_track):
            entry.bind("<Return>", lambda e: self.on_similar())
        self.seed_nb.bind("<<NotebookTabChanged>>", lambda e: (self._sync_seed_buttons(), self._place_output(),
                                                              self.after_idle(self._line_up_lists)))

    # --- JRiver Playlists (Ben, 6 Nov 2026): play or embellish one of your own playlists ----------------

    def _build_playlists_tab(self):
        """The third seed tab: Playlist, Play \u25be and Play & Embellish \u25be on one row, Output at the right."""
        tab = self.playlists_tab = tk.Frame(self.seed_nb, padx=26, pady=8)
        self.seed_nb.add(tab, text=t("JRiver Playlists"))
        tab.grid_anchor("w")   # the row centred in the panel, level with Output
        row = tk.Frame(tab)
        row.grid(row=0, column=0, sticky="w")
        label = tk.Label(row, text=t("Playlist"), font=("Segoe UI", 10))
        label.pack(side="left")
        self.playlist_entry = RoundedEntry(row, width=30, font=("Segoe UI", 9))
        self.playlist_entry.pack(side="left", padx=(4, LIST_BOX_GAP))
        self._playlist_chosen = None
        self._playlists_pop = None
        self._playlists_found = None
        entry = self.playlist_entry.entry
        entry.bind("<FocusIn>", lambda e: self._open_playlists(), add="+")
        entry.bind("<Button-1>", lambda e: self._open_playlists(), add="+")
        entry.bind("<KeyRelease>", self._playlists_typed, add="+")
        entry.bind("<Return>", lambda e: self._pick_first_playlist(), add="+")
        entry.bind("<Escape>", lambda e: self._close_playlists(), add="+")
        entry.bind("<FocusOut>", lambda e: self.after(200, self._close_playlists_if_away), add="+")
        self.play_list_button = FlatButton(row, text=t("Play"), width=18, height=2,
                                           command=lambda: self.on_play_playlist(False), arrow=True,
                                           arrow_command=lambda: self._choice_menu("order"))
        self.play_list_button.pack(side="left", padx=(0, BUTTON_GAP))
        self.embellish_button = FlatButton(row, text=t("Play & Embellish"), width=18, height=2,
                                           command=lambda: self.on_play_playlist(True), arrow=True,
                                           arrow_command=lambda: self._choice_menu("amount"))
        self.embellish_button.pack(side="left")
        self._sync_amounts()
        on, wrap = self.help_on, self.note_wrap
        for widget, name in ((label, "Playlist"), (self.playlist_entry, "Playlist"), (self.play_list_button, "Play"),
                             (self.embellish_button, "Play & Embellish")):
            Tooltip(widget, t(PLAY_NOTES[name]), when=on, wrap=wrap)
        self.extra_list_buttons = [self.play_list_button, self.embellish_button]
        # the box stands a little taller than a text box usually does, nearer the buttons beside it (10 Nov 2026)
        self.playlist_entry.set_pixel_height(self.play_list_button._size[1] * LIST_BOX_HEIGHT)
        self._list_widths = (self.playlist_entry._box_w, self.play_list_button._size[0], self.embellish_button._size[0])
        tab.bind("<Map>", lambda e: e.widget is tab and self.after_idle(self._line_up_lists), add="+")

    def _line_up_lists(self):
        """
        The Playlist box, Play and Play & Embellish at three equal widths (Ben, 10 Nov 2026), from the box's left
        edge to the right edge of the row's last playlist button that ends clear of Output, on the row's first
        line should it wrap. Before that Play and Play & Embellish each matched the button under them and the box
        took the rest (7 Nov), which left the box twice the width of either. With no such button, or no room,
        the three keep their own widths.
        """
        tab = getattr(self, "playlists_tab", None)
        if tab is None or not self._seed_is_playlists() or not tab.winfo_ismapped():
            return
        entry, play, embellish = self.playlist_entry, self.play_list_button, self.embellish_button
        box_w, play_w, emb_w = self._list_widths
        row = [b for b in getattr(self, "play_buttons", []) if b.winfo_ismapped()]
        first = [b for b in row if b.winfo_y() == row[0].winfo_y()] if row else []
        self.update_idletasks()
        out = getattr(self, "output_box", None)
        limit = (out.winfo_rootx() if out is not None and out.winfo_ismapped()
                 else tab.winfo_rootx() + tab.winfo_width()) - LIST_BOX_GAP   # Output stays clear at the right
        for last in reversed(first[1:]):   # the row's last button that ends clear of Output
            right = last.winfo_rootx() + last.winfo_width()
            if right > limit:
                continue
            thirds = tabs.equal_thirds(right - entry.winfo_rootx(), LIST_BOX_GAP, BUTTON_GAP)
            if thirds[1] >= play_w // 2:
                box_w, play_w, emb_w = thirds
            break
        entry.set_pixel_width(box_w)
        play.set_pixel_width(play_w)
        embellish.set_pixel_width(emb_w)

    def _seed_is_playlists(self):
        tab = getattr(self, "playlists_tab", None)
        return tab is not None and self.seed_nb.select() == str(tab)

    def _seed_has_row(self):
        """Search and JRiver Playlists: a row of boxes, with Output level with it."""
        return self._seed_is_search() or self._seed_is_playlists()

    def _playlist_list(self):
        """Every JRiver playlist and smartlist, A to Z, read once each time the list opens."""
        import saved_playlists
        try:
            found = saved_playlists.scan()
        except Exception as e:
            engine.debug(f"JRiver Playlists: couldn't read the playlists ({e})")
            return None
        return sorted(found, key=lambda p: (p["Name"].lower(), p.get("Folder") or ""))

    def _open_playlists(self):
        if self._playlists_pop is not None:
            return
        self._playlists_found = self._playlist_list()
        self._fill_playlists()

    def _playlists_typed(self, event):
        if event.keysym in ("Return", "Escape", "Tab"):
            return
        self._playlist_chosen = None
        if self._playlists_found is None:
            self._playlists_found = self._playlist_list()
        self._fill_playlists()

    def _when(self, stamp):
        """'20:41' today, 'yesterday', or '4 Nov'."""
        try:
            when = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            return ""
        days = (datetime.now().date() - when.date()).days
        if days == 0:
            return when.strftime("%H:%M")
        if days == 1:
            return t("yesterday")
        return f"{when.day} {t(MONTHS[when.month - 1])}"

    def _fill_playlists(self):
        """The list under the box: the recent five, then every playlist A to Z, both narrowed by what's typed."""
        self._close_playlists()
        entry = self.playlist_entry
        bg, fg, muted, line = PALETTE["field_bg"], PALETTE["text"], PALETTE["help_fg"], PALETTE["line"]
        pop = self._playlists_pop = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=line, padx=1, pady=1)
        inner = tk.Frame(pop, bg=bg)
        inner.pack(fill="both", expand=True)
        pop._rows = []
        typed = entry.get().strip().lower()
        found = self._playlists_found
        import saved_playlists

        def heading(text):
            tk.Label(inner, text=text.upper(), font=("Segoe UI", 8), fg=muted, bg=bg).pack(anchor="w", padx=10,
                                                                                         pady=(6, 1))

        def add_row(playlist, tag):
            r = tabs.PickRow(inner, playlist["Name"], fg=fg, bg=bg, fit=True, tag=tag)
            r.configure(cursor="hand2")
            r.pack(fill="x", padx=3, pady=1)
            r.bind("<Enter>", lambda e, w=r: w.set_chosen(True))
            r.bind("<Leave>", lambda e, w=r: w.set_chosen(False))
            r.bind("<ButtonPress-1>", lambda e, p=playlist: self._pick_playlist(p))
            pop._rows.append((playlist, r))

        if found is None:
            tk.Label(inner, text=t("JRiver isn't answering, so the playlists can't be listed."), fg=muted, bg=bg,
                     font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=6)
        else:
            by_id = {p["ID"]: p for p in found}
            recent = [(by_id[x["id"]], x) for x in embellish.recent() if x["id"] in by_id
                      and typed in by_id[x["id"]]["Name"].lower()]
            if recent:
                heading(t("Recent"))
                for p, x in recent:
                    how = t("embellished") if x.get("how") == "embellished" else t("played")
                    add_row(p, f"{how}, {self._when(x.get('when'))}".strip(", "))
                tk.Frame(inner, bg=line, height=1).pack(fill="x", pady=4)
            matches = [p for p in found if typed in p["Name"].lower()]
            heading(t("All Playlists"))
            for p in matches[:PLAYLISTS_SHOWN]:
                where = "" if p.get("Folder") in (None, "", saved_playlists.ROOT) else p["Folder"]
                kind = t("Smartlist") if p.get("Type") == "Smartlist" else ""
                add_row(p, ", ".join(x for x in (where, kind) if x))
            if not matches:
                tk.Label(inner, text=t("No playlist has that in its name."), fg=muted, bg=bg,
                         font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(0, 6))
            elif len(matches) > PLAYLISTS_SHOWN:
                tk.Label(inner, text=t("and {count} more: type to narrow the list", count=len(matches) - PLAYLISTS_SHOWN),
                         fg=muted, bg=bg, font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(0, 6))
        pop.update_idletasks()
        w = max(pop.winfo_reqwidth(), entry.winfo_width(), 300)
        pop.geometry(f"{w}x{pop.winfo_reqheight()}+{entry.winfo_rootx()}+{entry.winfo_rooty() + entry.winfo_height() + 2}")
        pop.deiconify()
        pop.lift()

    def _close_playlists(self):
        pop, self._playlists_pop = self._playlists_pop, None
        if pop is not None:
            try:
                pop.destroy()
            except tk.TclError:
                pass

    def _close_playlists_if_away(self):
        """The box lost the keyboard: the list goes, unless the box has it back."""
        try:
            if self.focus_get() is self.playlist_entry.entry:
                return
        except (KeyError, tk.TclError):
            pass
        self._close_playlists()
        self._playlists_found = None

    def _pick_playlist(self, playlist):
        self._playlist_chosen = playlist
        self.playlist_entry.delete(0, "end")
        self.playlist_entry.insert(0, playlist["Name"])
        self._close_playlists()
        self._playlists_found = None
        self.focus_set()   # out of the box, so the list doesn't open again at once

    def _pick_first_playlist(self):
        pop = self._playlists_pop
        if pop is not None and pop._rows:
            self._pick_playlist(pop._rows[0][0])

    def _chosen_playlist(self):
        """The playlist in the box: the one picked, or the one whose name was typed in full. None after saying why."""
        typed = self.playlist_entry.get().strip()
        chosen = self._playlist_chosen
        if chosen and chosen["Name"] == typed:
            return chosen
        if not typed:
            messagebox.showinfo(t("JRiver Playlists"), t("Pick a playlist first."), parent=self)
            return None
        found = self._playlist_list() or []
        same = [p for p in found if p["Name"].lower() == typed.lower()]
        if len(same) == 1:
            return same[0]
        messagebox.showinfo(t("JRiver Playlists"),
                            t("More than one playlist is called {name}. Pick the one you mean from the list.", name=typed)
                            if same else t("There's no JRiver playlist called {name}. Pick one from the list.", name=typed),
                            parent=self)
        return None

    def _sync_amounts(self):
        """Play & Embellish's arrow only while Settings leaves more than one amount to choose from."""
        try:
            self.embellish_button.set_arrow(len(embellish.amounts()["shown"]) > 1)
        except (AttributeError, tk.TclError):
            pass

    def _choice_menu(self, which):
        """
        The arrows: Play Shuffled or Play Ordered (remembered); the amounts Settings > JRiver Playlists offers,
        names only, the default ticked, a pick running Play & Embellish with it once (Ben, 7 Nov 2026).
        """
        self._close_children()
        button = self.play_list_button if which == "order" else self.embellish_button
        options = embellish.ORDERS if which == "order" else embellish.amounts()["shown"]
        names = embellish.ORDER_NAMES if which == "order" else embellish.AMOUNT_NAMES
        current = embellish.choices()[which]
        bg, fg, muted, line = PALETTE["field_bg"], PALETTE["text"], PALETTE["help_fg"], PALETTE["line"]
        pop = self._children_popup = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=line, padx=1, pady=1)
        inner = tk.Frame(pop, bg=bg)
        inner.pack(fill="both", expand=True)
        pop._rows = []
        for code in options:
            mark = "\u2713" if code == current else ""
            r = tabs.PickRow(inner, t(names[code]), fg=fg, bg=bg, fit=True,
                             left=lambda parent, m=mark: tk.Label(parent, text=m, width=2, fg=PALETTE["button_fg"],
                                                                  bg=bg, font=("Segoe UI", 10)))
            r.configure(cursor="hand2")
            r.pack(fill="x", padx=3, pady=1)
            r.bind("<Enter>", lambda e, w=r: w.set_chosen(True))
            r.bind("<Leave>", lambda e, w=r: w.set_chosen(False))
            r.bind("<ButtonRelease-1>", lambda e, c=code: self._choose(which, c))
            pop._rows.append((code, r, mark))
        pop.update_idletasks()
        w = max(pop.winfo_reqwidth(), button.winfo_width())
        pop.geometry(f"{w}x{pop.winfo_reqheight()}+{button.winfo_rootx()}+{button.winfo_rooty() + button.winfo_height() + 2}")
        pop.deiconify()
        pop.lift()
        pop.focus_force()
        pop.bind("<Escape>", lambda e: self._close_children())
        pop.bind("<FocusOut>", lambda e: self.after(100, self._close_children_if_unfocused))

    def _choose(self, which, code):
        self._close_children()
        if which == "order":
            embellish.set_choice(which, code)
        else:   # an amount from the arrow: this once, the default stays as Settings has it
            self.on_play_playlist(True, amount=code)

    def on_play_playlist(self, embellish_it, amount=None):
        """Play or Play & Embellish: a build like any other (Play or Review Mode, Output, Top-Up)."""
        if self.running:
            return
        playlist = self._chosen_playlist()
        if playlist is None:
            return
        chosen = embellish.choices()
        if amount:
            chosen["amount"] = amount
        top_up = bool(getattr(self, "top_up_armed", False))
        if embellish_it:
            # the order is the amount's own (Settings > JRiver Playlists): Play's arrow is Play's alone (10 Nov 2026)
            target = lambda: embellish.embellish(playlist, None, chosen["amount"], self.report)
        else:
            target = lambda: embellish.play(playlist, chosen["order"], self.report)
        self._run_job(target, needs_playing=False, mix=False, review=True, top_up=top_up)

    # --- Save Playlist: after a build, the output zone's Playing Now kept as a JRiver playlist ------------

    # --- Radio: a playlist of its own kind (Ben, 6 Nov 2026), its arrow listing the lanes -------------

    def _radio_buttons(self):
        """The Radio playlists' buttons on the row."""
        return [b for b in getattr(self, "play_buttons", []) if getattr(b, "_kind", None) == buttons.RADIO]

    def _radio_resting_text(self):
        why = radio.resting()
        if not why:
            return ""
        return t("Radio is resting: it needs {need} artists you've played {plays} or more times, and there are "
                 "{have} so far. It wakes once there are enough.", need=why["need"], plays=radio.MIN_PLAYS,
                 have=why["have"])

    def _sync_radio(self):
        """Radio greys out while it rests (too little played yet), with a note saying how far off it is. It
        plays on every seed tab, JRiver Playlists included: it needs no seed."""
        text = self._radio_resting_text()
        for b in self._radio_buttons():
            if getattr(b, "_radio_note", None) is not None:
                b._radio_note.text = text
            if not self.running and not getattr(b, "_needs_advanced", False):
                b.config(state="disabled" if text else "normal")

    def on_radio(self, button, lane_id=None):
        """A Radio playlist's face (its lane, or the last lane played), or a lane picked from its arrow."""
        if self.running:
            return
        top_up = bool(getattr(self, "top_up_armed", False))

        def target():
            current = buttons.get(button["id"]) or button   # the page may have changed it since the row was drawn
            buttons.run_radio(current, report=self.report, lane_id=lane_id)
        self._run_job(target, needs_playing=False, mix=False, review=True, top_up=top_up)

    def on_radio_analyse(self, fresh=True):
        """Re-analyse (fresh), or the stations cut again at the count set on Radio's page (from the genres kept).
        Asked while a build runs, it waits for the build to finish."""
        if self.running:
            self._radio_pending = fresh or bool(getattr(self, "_radio_pending", None))
            self.report(t("Radio: the stations are made again once this build finishes."))
            return
        self._radio_pending = None
        self._close_children()
        self._run_job(lambda: radio.analyse(self.report, fresh=fresh), needs_playing=False, mix=False)

    def _open_radio(self, button):
        """The arrow: every lane with its share of your plays, the one the face plays marked; Re-analyse at the foot."""
        self._close_children()
        fb = next((b for b in self.play_buttons if b._button["id"] == button["id"]), None)
        if fb is None:
            return
        button = buttons.get(button["id"]) or button
        bg, fg, muted, line = PALETTE["field_bg"], PALETTE["text"], PALETTE["help_fg"], PALETTE["line"]
        pop = self._children_popup = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=line, padx=1, pady=1)
        inner = tk.Frame(pop, bg=bg)
        inner.pack(fill="both", expand=True)
        pop._rows = []
        pop._button = button
        result = radio.analysis()
        face, _problem = buttons.radio_lane_for(button)
        opened = set(radio.row()["open"])
        if result is None:
            tk.Label(inner, text=t("No stations yet: press Radio to make them from what you play."), fg=muted, bg=bg,
                     font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=6)
        elif result.get("resting"):
            tk.Label(inner, text=self._radio_resting_text(), fg=muted, bg=bg, font=("Segoe UI", 9), wraplength=320,
                     justify="left").pack(anchor="w", padx=10, pady=6)
        rows = radio.visible_rows()
        any_split = any(x.get("children") for x, _d in rows)   # every name starts where a split's does
        for lane_, depth in rows:
            splits = bool(lane_.get("children"))
            tag = f"{radio.share(lane_)}%"
            if face is not None and lane_["id"] == face["id"]:
                tag = t("default") + " \u00b7 " + tag
            r = tabs.PickRow(inner, lane_["name"], fg=fg, bg=bg, fit=True, tag=tag, indent=18 * depth,
                             fold=("open" if lane_["id"] in opened else "closed") if splits else None,
                             on_fold=(lambda i=lane_["id"]: self._radio_fold(i)) if splits else None,
                             fold_space=any_split)
            r.configure(cursor="hand2")
            r.pack(fill="x", padx=3, pady=1)
            r.bind("<Enter>", lambda e, w=r: w.set_chosen(True))
            r.bind("<Leave>", lambda e, w=r: w.set_chosen(False))
            r.bind("<ButtonRelease-1>", lambda e, i=lane_["id"]: (self._close_children(), self.on_radio(button, i)))
            r.bind("<Button-3>", lambda e, i=lane_["id"]: self._radio_lane_menu(e, button, i))
            pop._rows.append((lane_["id"], r))
        tk.Frame(inner, bg=line, height=1).pack(fill="x", pady=4)
        when = self._when((result or {}).get("when")) if result else ""
        again = tabs.PickRow(inner, t("Re-analyse") if result else t("Analyse Now"), fg=muted, bg=bg, fit=True,
                             tag=t("last: {when}", when=when) if when else "")
        again.configure(cursor="hand2")
        again.pack(fill="x", padx=3, pady=(0, 2))
        again.bind("<Enter>", lambda e: again.set_chosen(True))
        again.bind("<Leave>", lambda e: again.set_chosen(False))
        again.bind("<ButtonRelease-1>", lambda e: self.on_radio_analyse())
        pop._again = again
        pop.update_idletasks()
        w = max(pop.winfo_reqwidth(), fb.winfo_width(), 300)
        pop.geometry(f"{w}x{pop.winfo_reqheight()}+{fb.winfo_rootx()}+{fb.winfo_rooty() + fb.winfo_height() + 2}")
        pop.deiconify()
        pop.lift()
        pop.focus_force()
        pop.bind("<Escape>", lambda e: self._close_children())
        pop.bind("<FocusOut>", lambda e: self.after(100, self._close_children_if_unfocused))

    def _radio_fold(self, lane_id, open_=None):
        """Split (open) or Join Back (closed): the lane's halves shown under it, or folded away."""
        opened = radio.row()["open"]
        open_ = (lane_id not in opened) if open_ is None else open_
        opened = [i for i in opened if i != lane_id and not (not open_ and i.startswith(lane_id))]
        if open_:
            opened.append(lane_id)
        radio.set_row(open=opened)
        pop = getattr(self, "_children_popup", None)
        if pop is not None and getattr(pop, "_button", None):
            self._open_radio(pop._button)

    def _radio_lane_menu(self, event, button, lane_id):
        """Right-click a lane: Split or Join Back, and Add as a Button (a Radio playlist of that lane)."""
        import review_gui
        p = review_gui.palette()
        menu = tk.Menu(self, tearoff=0, bg=p["bg"], fg=p["text"], activebackground=p["row_on"],
                       activeforeground=p["accent"])
        lane_ = radio.lane(lane_id)
        if lane_ is not None:
            opened = lane_id in radio.row()["open"]
            if lane_.get("children"):
                menu.add_command(label=t("Join Back") if opened else t("Split"),
                                 command=lambda: self._radio_fold(lane_id, not opened))
            else:
                menu.add_command(label=t("Split"), state="disabled")
            menu.add_separator()
        menu.add_command(label=t("Add as a Button"), command=lambda: self._radio_add_button(button, lane_id))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _radio_add_button(self, button, lane_id):
        """A lane as a button of its own: a Radio playlist playing that lane, with this one's settings, after it."""
        lane_ = radio.lane(lane_id)
        self._close_children()
        if lane_ is None:
            return
        made = buttons.duplicate(button["id"])
        if made is None:
            return
        buttons.rename(made["id"], buttons.unique_name(lane_["name"]))
        buttons.set_lane(made["id"], lane_["name"])
        self.refresh_buttons()
        self._notice(t("Note: {name} is on the Play tab. Its page is under Settings > Playlist Settings.",
                       name=buttons.get(made["id"])["name"]))

    def _show_save(self, zone):
        self._save_zone = zone
        shown = zone is not None
        if shown != bool(getattr(self, "_save_shown", False)):
            self._save_shown = shown
            if not shown:
                self.save_button.place_forget()
            self._flow_buttons()

    def on_save_playlist(self):
        zone = getattr(self, "_save_zone", None)
        if zone is None or self.running:
            return
        label = engine.zone_label(zone)
        try:
            keys = [str(r.get("Key")) for r in engine.playing_now_rows(zone) if r.get("Key")]
        except Exception:
            keys = []
        if not keys:
            messagebox.showinfo(t("Save Playlist"), t("Playing Now in {zone} is empty, so there's nothing to save.",
                                                      zone=label), parent=self)
            return
        from tabs import ask_name
        name = ask_name(self, t("Save Playlist"),
                        t("Save what's in Playing Now in {zone} ({tracks}) as a JRiver playlist called:", zone=label,
                          tracks=tn("{count} track", "{count} tracks", len(keys))),
                        initial=getattr(self, "_save_default", "") or "")
        name = (name or "").strip()
        if not name:
            return
        import saved_playlists
        try:
            taken = any(p["Name"].lower() == name.lower() and p.get("Type") == "Playlist"
                        and p.get("Folder") == saved_playlists.ROOT for p in saved_playlists.scan())
        except Exception:
            taken = False
        if taken and not messagebox.askyesno(t("Save Playlist"),
                                             t('There\'s already a JRiver playlist called "{name}". Replace it?', name=name),
                                             parent=self):
            return
        try:
            engine.review_save(keys, name)
        except Exception as e:
            self._append_log(str(e) if str(e).startswith(("Problem", t("Problem")))
                             else t("Problem: the playlist wasn't saved ({e}).", e=e))
            return
        self._append_log(t('Saved {tracks} as the JRiver playlist "{name}".',
                           tracks=tn("{count} track", "{count} tracks", len(keys)), name=name))

    def _fill_zone_list(self):
        engine.refresh_settings_if_changed()
        self.zone_cb.config(values=engine.listed_zone_names()
                            + ([MULTIROOM_LABEL] if engine.MULTIROOM_ENABLED else []))

    def _zone_name(self):
        """The JRiver zone the row reads: Multiroom in the list means the leader zone (Ben, 9 Nov 2026)."""
        name = self.zone_var.get()
        return engine.MULTIROOM_LEADER if name == MULTIROOM_LABEL else name

    def _on_zone_changed(self, *_):
        self._zone_picked = True   # picked by hand, so it stays put until the next launch
        engine.SEED_ZONE_NAME = self._zone_name() or None
        self.zone_cb.selection_clear()
        self._update_now_playing()

    def _multiroom_state(self, state):
        """The follower's state changed: when the Speakers start following, Now Playing shows the leader as Multiroom."""
        if state == "following" and engine.MULTIROOM_ENABLED and self.zone_var.get() != MULTIROOM_LABEL:
            self.zone_var.set(MULTIROOM_LABEL)
            self._on_zone_changed()

    # --- Stop, Clear Playing Now and Skip Track -----------------------------------------------------

    def _sync_np_controls(self, info):
        """The two buttons follow what Now Playing last read: Stop while the zone plays or is paused, Clear Playing
        Now (red) once it's stopped with tracks left, greyed with none; Skip Track only while a track follows."""
        stopped = not info or str(info.get("State", "0")) == "0"
        tracks = int((info or {}).get("PlayingNowTracks") or 0)
        has_next = str((info or {}).get("NextFileKey", "-1")) not in ("", "-1")
        self._np_stopped = stopped
        if stopped:
            self.stop_button.config(text=t("Clear Playing Now"), armed=PALETTE["red"], command=self._clear_clicked,
                                    state="normal" if tracks else "disabled")
        else:
            self.stop_button.config(text=t("Stop"), armed=PALETTE["amber"], command=self._stop_clicked, state="normal")
        self.skip_button.config(state="normal" if not stopped and has_next else "disabled")

    def _zone_action(self, call, line):
        """Runs a JRiver call for the row's zone on a thread, says one line, and reads Now Playing again."""
        name = self._zone_name()
        zone = engine.zone_id(name) if name else engine.zone_id()
        if zone is None:
            self.report(t("Problem: the zone '{name}' isn't in JRiver.", name=name))
            return
        label = engine.zone_label(zone)

        def work():
            try:
                call(zone)
                self.log_queue.put(t(line, zone=label))
            except Exception as e:
                self.log_queue.put(t("Problem: JRiver didn't answer ({e}).", e=e))
            self.after(0, self._update_now_playing)
        threading.Thread(target=work, daemon=True, name="zone-action").start()

    def _stop_clicked(self):
        self._zone_action(engine.stop_zone, N_("Stopped {zone}."))

    def _clear_clicked(self):
        self._zone_action(engine.clear_playing_now, N_("Cleared Playing Now in {zone}."))

    def _skip_clicked(self):
        self._zone_action(engine.skip_track, N_("Skipped to the next track in {zone}."))

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

    def _place_output(self):
        """
        Output at the right of the seed tab that's showing, in the panel's middle on every tab (Ben, 7 Nov
        2026): the tabs are one height and their rows are centred, so it never moves when the tab changes.
        place measures from inside the panel's padding, the same 26 as Zone has on the left.
        """
        box = getattr(self, "output_box", None)
        if box is None:
            return
        page = self.seed_nb._current if self.seed_nb._current is not None else self.seed_nb._pages[0]
        box.place(in_=page, relx=1.0, rely=0.5, x=0, y=0, anchor="e")
        if page is self.seed_nb._pages[0]:
            box.update_idletasks()   # so its width is known
            # the buttons stop short of Output, and the track text short of the buttons
            self._np_controls.pack_configure(padx=(12, box.winfo_reqwidth() + 36))
        box.lift()

    def _sync_seed_buttons(self):
        """
        Show Credits needs an album, which a typed seed doesn't have, so it greys out on Search. On JRiver
        Playlists the row's playlists grey out too: they start from a track or an artist (Ben, 6 Nov 2026).
        """
        self._sync_seed_bars()   # a typed seed ignores Seed, so the bars go back to orange on Search
        if self.running:
            return
        lists = self._seed_is_playlists()
        for b in getattr(self, "play_buttons", []):
            if not getattr(b, "_needs_advanced", False) and getattr(b, "_kind", None) != buttons.RADIO:
                b.config(state="disabled" if lists else "normal")
        if getattr(self, "play_buttons", None):
            self._sync_ai_button()
            self._sync_radio()
        if not lists:
            self._close_playlists()
        button = getattr(self, "credits_button", None)
        if button is None:
            return
        button.config(state="disabled" if self._seed_has_row() else "normal")

    def _typed_seed(self, need_track, why=None):
        """The Search tab's seed, or None (after a prompt) if the fields aren't filled in."""
        artist = self.search_artist.get().strip()
        track = self.search_track.get().strip()
        if not artist or (need_track and not track):
            text = t("Type an artist and a track first.") if need_track else t("Type an artist first.")
            if need_track and why and artist:
                text = why
            messagebox.showinfo(t("Search"), text)
            return None
        return engine.typed_seed_info(artist, track)

    @property
    def buttons(self):
        """Everything greyed out during a build: the row's buttons, then Show Credits."""
        return self.play_buttons + self.extra_buttons

    def _build_buttons(self):
        # The row of buttons, one per entry in the button list (buttons.py), then More Options
        # and +. Laid out by hand so they wrap onto another row when the window is narrow.
        frame = self.button_row = tk.Frame(self)
        frame.pack(fill="x")
        frame.pack_propagate(False)
        self.play_buttons, self.extra_buttons = [], list(getattr(self, "extra_list_buttons", []))
        # More options: the quieter button. Opens the row below; stays usable during a build.
        self.more_button = FlatButton(frame, text=t("More Options"), command=self._toggle_more,
                                      width=18, height=2, quiet=True)
        # +: a button of your own. Right-click: Restore Default Buttons.
        self.add_button = FlatButton(frame, text="+", command=self.on_add_button, width=2, height=2, quiet=True)
        self.add_button._name = "+"
        for w in (self.add_button, self.add_button._label):
            w.bind("<Button-3>", lambda e: self._button_menu(e, None))
        # Save Playlist: shows after a build that went to a JRiver zone, at the row's top right
        self.save_button = FlatButton(frame, text=t("Save Playlist"), command=self.on_save_playlist, width=14, height=2,
                                      quiet=True)
        Tooltip(self.save_button, t(PLAY_NOTES["Save Playlist"]), when=self.help_on, wrap=self.note_wrap)
        self._save_shown, self._save_zone = False, None
        self._draw_buttons()
        frame.bind("<Configure>", lambda e: self._flow_buttons())

        # Output: where the finished playlist goes. Saved straight to .env; the engine
        # reads it at the start of each run, so changing it mid-run affects the next one.
        # It sits at the right of the Zone line, on both seed tabs (Ben, 30 Oct 2026: room for Artist + Guests)
        self.output_box = tk.Frame(self.seed_nb)
        tk.Label(self.output_box, text=t("Output"), font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["text_secondary"]).pack(side="left", padx=(0, 6))
        self.output_var = tk.StringVar(value=self._output_label(engine.OUTPUT_TARGET))
        self.output_cb = ttk.Combobox(self.output_box, textvariable=self.output_var,
                                      values=[t(SAME_ZONE_LABEL)] + self._extra_outputs(), state="readonly", width=24,
                                      postcommand=self._fill_output_list)
        self.output_cb.pack(side="left")
        self.output_cb.bind("<<ComboboxSelected>>", self._on_output_changed)
        self._place_output()
        self._sync_behaviour()

        # The More Options row: click-through buttons (Seed, Mode, Moderator, Drift, Non-stop as ∞), then
        # + Add Playlist and Show Credits, with the playlist rows under it. Held in a frame that's always
        # packed, so it opens in the same place, under a thin line that separates it from the buttons above.
        self.more_box = tk.Frame(self)
        self.more_box.pack(fill="x")
        self.more_line = tk.Frame(self.more_box, height=1, bg=PALETTE["line"])
        self.extras_row = tk.Frame(self.more_box, padx=16)
        dark = engine.THEME == "dark"
        self.seed_colour = tabs.seed_colour("dark" if dark else "light")   # teal, or leaf green against a teal accent
        review_colour = "#f28c28" if dark else "#a85400"         # orange: Review Mode

        # Seed: where Similar Artists and Similar Tracks start from. Windows (Main) app builds only.
        saved = read_env().get("PLAY_SEED", "current").strip().lower()
        self.seed_var = tk.StringVar(value="Playing Now" if saved == "playing_now" else "Current Track")
        self.seed_cb = ClickThrough(self.extras_row, "Seed", self.seed_var, [N_("Current Track"), "Playing Now"],
                                    command=self._on_seed_changed, plain=("Current Track",),
                                    lit={"Playing Now": self.seed_colour})
        self.seed_cb.pack(side="left", padx=(0, 8))
        # Mode (Behaviour): play straight away, or Review first. Every build from the app; voice always plays.
        saved = read_env().get("PLAY_BEHAVIOUR", "instant").strip().lower()
        self.behaviour_var = tk.StringVar(value=dict(PLAY_BEHAVIOUR).get(saved, "Play"))
        self.behaviour_cb = ClickThrough(self.extras_row, "", self.behaviour_var,
                                         [shown for _, shown in PLAY_BEHAVIOUR], command=self._on_behaviour_changed,
                                         plain=("Play",), lit={"Review": review_colour},
                                         labels={"Play": N_("Play Mode"), "Review": N_("Review Mode")})
        self.behaviour_cb.pack(side="left", padx=(0, 8))
        tk.Frame(self.extras_row, width=1, height=24, bg=PALETTE["line"]).pack(side="left", padx=(8, 16))
        # Moderator, Deep Cuts and Non-stop: overrides (overrides.py). While this row is open they beat every
        # playlist's own settings; closed, the pages decide (Ben, 2 Nov 2026). Each steps through its settings
        # as the 1.28 row did (Off, Relaxed, Balanced, Strict; Off, Spaced, Shuffled; Off, Keep It Tight, Wander).
        self.override_vars = {}
        self.override_cbs = {}
        for key, prefix, colour, symbol in (("moderator", "Moderator", PALETTE["ai_purple"], False),
                                            ("deep_cuts", "Deep Cuts", PALETTE["button_fg"], False),
                                            ("nonstop", "\u221e", PALETTE["button_fg"], True)):
            var = tk.StringVar(value="Off")
            faces = overrides.labels(key)
            cb = ClickThrough(self.extras_row, prefix, var, faces, symbol=symbol,
                              lit={face: colour for face in faces if face != "Off"},
                              command=lambda k=key: self._on_override_changed(k))
            cb.pack(side="left", padx=(0, 8))
            self.override_vars[key], self.override_cbs[key] = var, cb
        self._moderator_tip = Tooltip(self.override_cbs["moderator"], t(NO_KEY_TEXT), when=lambda: not engine.ai_enabled())
        self._sync_override_switches()
        tk.Frame(self.extras_row, width=1, height=24, bg=PALETTE["line"]).pack(side="left", padx=(8, 16))
        # Top-Up (Ben, 5 Nov 2026): armed by a click, teal; the next playlist clicked goes into what's left of
        # Playing Now and releases it. Greyed while Output is YouTube or Tidal.
        self.top_up_armed = False
        self.top_up_button = FlatButton(self.extras_row, text=t("Top-Up"), quiet=True, height=1,
                                        width=max(9, len(t("Top-Up")) + 2), command=self._toggle_top_up)
        self.top_up_button._name = "Top-Up"
        self.top_up_button.pack(side="left", padx=(0, 8))
        Tooltip(self.top_up_button, t("Top-Up adds to a JRiver zone's Playing Now, so it's off while Output is "
                                      "YouTube or Tidal."), when=self._top_up_greyed)
        # Add playlist: JRiver playlists joined to the next build from the app (not voice)
        self.add_playlist_button = FlatButton(self.extras_row, text=t("+ Add JRiver Playlist"), quiet=True,
                                              width=max(18, len(t("+ Add JRiver Playlist")) + 1),
                                              height=1, command=lambda: self.mix_rows.add())
        self.add_playlist_button.pack(side="left", padx=(0, 8))
        self.credits_button = FlatButton(self.extras_row, text=t("Show Credits"), command=self.on_credits,
                                         quiet=True, width=14, height=1)
        self.credits_button.pack(side="left")
        self.extra_buttons.append(self.credits_button)   # greyed out during a build, and on the Search tab
        # ?: hover notes for the whole Play tab, off until switched on (remembered)
        self.help_var = tk.StringVar(value="On" if read_env().get("PLAY_HELP", "0") == "1" else "Off")
        self.help_cb = ClickThrough(self.extras_row, "", self.help_var, ["Off", "On"], command=self._on_help_changed,
                                    plain=("Off",), labels={"Off": "?", "On": "?"},
                                    lit={"On": PALETTE.get("link") or PALETTE["button_fg"]})
        self.help_cb.pack(side="right")
        self._add_play_notes()
        self._sync_seed_bars()
        self.mix_rows = MixRows(self.more_box, padx=16)
        self.mix_rows.on_change = self._on_mix_rows_changed
        self._sync_top_up()
        self._show_more(playmix.is_open(), save=False)

    def help_on(self):
        """True while the More Options row's ? is on: the Play tab's hover notes show."""
        try:
            return self.help_var.get() == "On"
        except (AttributeError, tk.TclError):
            return False

    def _on_help_changed(self, *_):
        try:
            write_env({"PLAY_HELP": "1" if self.help_on() else "0"})
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)

    def note_wrap(self):
        """How wide the Play tab's notes are: two and a half of its main buttons (Similar Artists and so on)."""
        try:
            return int(self.buttons[0]._size[0] * 2.5)
        except (AttributeError, IndexError):
            return None

    def _add_play_notes(self):
        """A note on every fixed Play tab control, shown on hover only while ? is on (the row's are drawn with it)."""
        on, wrap = self.help_on, self.note_wrap
        for widget, name in ((self.more_button, "More Options"), (self.add_button, "+"), (self.output_cb, "Output"),
                             (self.zone_cb, "Zone"), (self.seed_cb, "Seed"), (self.behaviour_cb, "Mode"),
                             (self.add_playlist_button, "+ Add JRiver Playlist"), (self.help_cb, "Help"),
                             (self.top_up_button, "Top-Up"), (self.stop_button, "Stop"), (self.skip_button, "Skip Track"),
                             (self.override_cbs["deep_cuts"], "Deep Cuts"), (self.override_cbs["nonstop"], "Non-stop")):
            Tooltip(widget, t(PLAY_NOTES[name]), when=on, wrap=wrap)
        Tooltip(self.override_cbs["moderator"], t(PLAY_NOTES["Moderator"]), when=lambda: on() and engine.ai_enabled(),
                wrap=wrap)

    # --- the row of buttons -------------------------------------------------------------------------

    def _button_note(self, button):
        """A button's hover note: its own (a standard button) or its kind's, then a line saying what's on."""
        kids = buttons.children(button["id"])
        if kids:   # a parent: its default's note, then what the arrow holds
            face = buttons.runs(button)
            more = t("The arrow lists 1 more playlist.") if len(kids) == 1 else t("The arrow lists {n} more playlists.",
                                                                                 n=len(kids))
            return self._plain_note(face) + "\n" + more
        return self._plain_note(button)

    def _plain_note(self, button):
        if button.get("kind") is None:
            return t("No config yet. Click to open its page and add one.")
        if buttons.is_radio(button):
            return t(PLAY_NOTES["Radio"]) + "\n" + buttons.describe(button)
        kind_name = buttons.KIND_NAMES[button["kind"]]
        note = t(PLAY_NOTES.get(button["name"] if button.get("standard") or button["name"] in PLAY_NOTES
                                else kind_name, PLAY_NOTES[kind_name]))
        extras = buttons.describe(button)
        if extras != t(buttons.KIND_LABELS[button["kind"]]):   # more than the kind alone: configs, Drift, Non-stop...
            note += "\n" + extras
        return note

    def _draw_buttons(self):
        """Draws the row from the ticked playlists: one button each, then More Options and +."""
        for b in self.play_buttons:
            b.destroy()
        self.play_buttons = []
        on, wrap = self.help_on, self.note_wrap
        shown = buttons.shown()
        for button in shown:
            kids = buttons.children(button["id"])
            face = buttons.runs(button)   # a parent's face carries its default's name
            ai = face["kind"] == "vibe"
            empty = face["kind"] is None   # a blank slate: grey text, and its note always shows
            is_radio = buttons.is_radio(button)   # its arrow lists the lanes (a Radio playlist takes no children)
            b = FlatButton(self.button_row, text=face["name"], width=18, height=2,
                           command=lambda bt=button: self._press_playlist(bt),
                           accent=PALETTE["ai_purple"] if ai else None,   # magenta: AI credits
                           text_fg=PALETTE["ai_purple"] if ai else PALETTE["help_fg"] if empty else None,
                           arrow=bool(kids) or is_radio,
                           arrow_command=(lambda bt=button: self._open_radio(bt)) if is_radio
                           else (lambda bt=button: self._open_children(bt)))
            b._name, b._kind, b._button = button["name"], face["kind"], button
            if mode.is_simple() and mode.needs_advanced(face):   # two configs, or Consensus: not itself in Simple
                b.config(state="disabled")
                b._needs_advanced = True
                Tooltip(b, t("Needs Advanced: switch to Advanced under Settings > Playlist Settings to build it."), wrap=wrap)
            for w in (b, b._label):
                w.bind("<Button-3>", lambda e, bt=button: self._button_menu(e, bt))
                w.bind("<ButtonPress-1>", lambda e, fb=b: self._drag_start(e, fb), add="+")
                w.bind("<B1-Motion>", lambda e, fb=b: self._drag_move(e, fb), add="+")
                w.bind("<ButtonRelease-1>", lambda e, fb=b: self._drag_end(e, fb), add="+")
            if not is_radio:   # first, so the button's own note is its _tooltip
                Tooltip(b, t("Playlists start from a track or an artist, so they rest while JRiver Playlists is showing. "
                             "Use Play or Play & Embellish there."), when=self._seed_is_playlists, wrap=wrap)
            if is_radio:   # resting: why, whatever ? says; awake: its note while ? is on
                b._radio_note = Tooltip(b, "", when=lambda: bool(radio.resting()), wrap=wrap)
                Tooltip(b, self._button_note(button), when=lambda: on() and not radio.resting(), wrap=wrap)
            elif empty:
                Tooltip(b, self._button_note(button), wrap=wrap)
            elif ai:   # its "why it's greyed out" note shows whatever ? says
                Tooltip(b, self._button_note(button), when=lambda: on() and engine.ai_enabled(), wrap=wrap)
                b._ai_tip = Tooltip(b, "", when=lambda: not engine.ai_enabled())
            else:
                Tooltip(b, self._button_note(button), when=on, wrap=wrap)
            self.play_buttons.append(b)
        if getattr(self, "playlists_tab", None) is not None and self._seed_is_playlists() and not self.running:
            for b in self.play_buttons:
                if b._kind != buttons.RADIO:   # Radio needs no seed
                    b.config(state="disabled")
        self._sync_ai_button()
        if not self.running:
            self._sync_radio()
        self._flow_buttons()

    def _flow_buttons(self):
        """Places the row's buttons left to right, wrapping onto another row when the window is narrow."""
        row = self.button_row
        avail = max(row.winfo_width(), 1) - 2 * 16
        save = getattr(self, "save_button", None)
        if save is not None and getattr(self, "_save_shown", False):
            avail -= save._size[0] + BUTTON_GAP   # the row's top right is Save Playlist's
            save.place(x=max(row.winfo_width(), 1) - 16 - save._size[0], y=4)
        x = y = 0
        height = 0
        for b in self.play_buttons + [self.more_button, self.add_button]:
            w, h = b._size
            if x and x + w > avail:
                x, y = 0, y + h + BUTTON_GAP
            b.place(x=16 + x, y=4 + y)
            x += w + BUTTON_GAP
            height = y + h
        row.config(height=height + 8)
        self.after_idle(self._line_up_lists)   # JRiver Playlists' two buttons follow the row

    def refresh_buttons(self):
        """After the list changed (+, right-click, Settings > Playlists): redraws the row and the dials."""
        self._draw_buttons()
        if self.running:
            for b in self.play_buttons:
                b.config(state="disabled")

    def _press_playlist(self, button):
        """A click builds the playlist, or a parent's default (a drag's release isn't a click)."""
        if getattr(self, "_drag_moved", False):
            return   # the release of a drag, not a click
        self.on_button(buttons.runs(button))

    # --- a parent's menu: its children, the default marked ------------------------------------------

    def _open_children(self, parent):
        """The arrow on a parent: a small popup of its children under the button."""
        self._close_children()
        fb = next((b for b in self.play_buttons if b._button["id"] == parent["id"]), None)
        kids = buttons.children(parent["id"])
        if fb is None or not kids:
            return
        bg, fg, line = PALETTE["field_bg"], PALETTE["text"], PALETTE["line"]
        pop = self._children_popup = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=line, padx=1, pady=1)
        inner = tk.Frame(pop, bg=bg)
        inner.pack(fill="both", expand=True)
        pop._rows = []
        parent = buttons.get(parent["id"])
        teal = self._seed_teal()   # rows Seed applies to read in the Seed colour, as the buttons do
        for playlist, text, is_default in buttons.menu_rows(parent):
            seeded = teal and buttons.follows_seed(playlist)
            needs = mode.is_simple() and mode.needs_advanced(playlist)
            colour = (PALETTE["help_fg"] if needs else PALETTE["ai_purple"] if playlist["kind"] == "vibe"
                      else self.seed_colour if seeded else fg)
            row = tabs.PickRow(inner, text, fg=colour, bg=bg, fit=True,
                               tag=t("Needs Advanced") if needs else t("default") if is_default else "",
                               edge=self.seed_colour if seeded else None)   # the hover outline matches the text
            row.configure(cursor="hand2")
            row.pack(fill="x", padx=3, pady=1)
            row.bind("<Enter>", lambda e, r=row: r.set_chosen(True))   # the rounded outline on hover
            row.bind("<Leave>", lambda e, r=row: r.set_chosen(False))
            if playlist is parent:
                row.bind("<ButtonRelease-1>", lambda e, p=parent: self._run_child(buttons.runs(dict(p, default=""))))
                row.bind("<Button-3>", lambda e, p=parent: self._parent_row_menu(e, p))
            else:
                row.bind("<ButtonPress-1>", lambda e, c=playlist, d=is_default: self._pop_press(e, c, d))
                row.bind("<B1-Motion>", lambda e: self._pop_drag_move(e))
                row.bind("<ButtonRelease-1>", lambda e, c=playlist: self._pop_release(e, c))
                row.bind("<Button-3>", lambda e, c=playlist, p=parent: self._child_menu(e, p, c))
            pop._rows.append((playlist, row, row.tag))
        pop.update_idletasks()
        w = max(pop.winfo_reqwidth(), fb.winfo_width())   # the widest row (fit=True), or the button
        pop.geometry(f"{w}x{pop.winfo_reqheight()}+{fb.winfo_rootx()}+{fb.winfo_rooty() + fb.winfo_height() + 2}")
        pop.deiconify()
        pop.lift()
        pop.focus_force()
        pop.bind("<Escape>", lambda e: self._close_children())
        pop.bind("<FocusOut>", lambda e: self.after(100, self._close_children_if_unfocused))

    def _close_children_if_unfocused(self):
        pop = getattr(self, "_children_popup", None)
        if pop is not None and pop.winfo_exists():
            try:
                focused = pop.focus_get()
            except (KeyError, tk.TclError):
                focused = None
            if focused is None or not str(focused).startswith(str(pop)):
                self._close_children()

    def _close_children(self):
        pop = getattr(self, "_children_popup", None)
        if pop is not None:
            try:
                pop.destroy()
            except tk.TclError:
                pass
        self._children_popup = None

    def _run_child(self, child):
        """A row clicked in the menu: built once, this time."""
        self._close_children()
        self.on_button(child)

    def _parent_row_menu(self, event, parent):
        """Right-click on the parent's own row: make it the default again, and its Settings."""
        import review_gui
        p = review_gui.palette()
        menu = tk.Menu(self, tearoff=0, bg=p["bg"], fg=p["text"], activebackground=p["row_on"],
                       activeforeground=p["accent"])
        menu.add_command(label=t("Make Default"), state="normal" if parent.get("default") else "disabled",
                         command=lambda: self._set_default(parent, ""))
        menu.add_command(label=t("Settings"), command=lambda: (self._close_children(),
                                                               self.open_playlist_settings(parent["id"])))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # --- dragging a child out of the drop-down: onto the row, into another parent, or onto a pill ---

    def _pop_press(self, event, child, is_default):
        self._pop_pressed = {"child": child, "x": event.x_root, "y": event.y_root, "draggable": not is_default,
                             "dragging": False}

    def _pop_drag_move(self, event):
        press = getattr(self, "_pop_pressed", None)
        if not press or not press["draggable"]:
            return
        if not press["dragging"]:
            if abs(event.x_root - press["x"]) < self.DRAG_START and abs(event.y_root - press["y"]) < self.DRAG_START:
                return
            press["dragging"] = True
            pop = self._children_popup
            if pop is not None:
                try:
                    pop.attributes("-alpha", 0.0)   # out of sight, but alive: the mouse events keep coming to it
                except tk.TclError:
                    pop.withdraw()
            self._show_drag_image_for(press["child"]["name"])
            self._show_drop_targets(press["child"])
            press["grab"] = (self._drag_image.winfo_reqwidth() // 2, self._drag_image.winfo_reqheight() // 2)
        gx, gy = press["grab"]
        self._drag_image.geometry(f"+{event.x_root - gx}+{event.y_root - gy}")
        over = self._target_at(event.x_root, event.y_root)
        self._highlight_target(event.x_root, event.y_root)
        if over is None:
            self._watch_nest(press["child"], None, event.x_root, event.y_root)
        else:
            self._watch_nest(press["child"], None, None, None)

    def _pop_release(self, event, child):
        press = getattr(self, "_pop_pressed", None)
        self._pop_pressed = None
        if not press or not press["dragging"]:
            if press is not None:
                self._run_child(child)   # a click, not a drag
            return
        target = self._target_at(event.x_root, event.y_root)
        nest_into = getattr(self, "_nest_target", None)
        self._clear_nest()
        self._hide_drop_targets()
        self._hide_drag_image()
        self._close_children()
        if target == "settings":
            self.open_playlist_settings(child["id"])
        elif target == "use":
            self._use_settings_of(child)
        elif target == "remove":   # a playlist is a button or a device's (2 Nov 2026): off the row means deleted
            self._delete_button(child)
        elif nest_into is not None:
            parent = nest_into._button
            if buttons.nest(child["id"], parent["id"]):
                self._notice(t("Note: {child} is under {parent} now. The arrow on {parent} lists it.",
                                   child=child["name"], parent=parent["name"]))
        else:
            row = self.button_row
            on_row = row.winfo_rooty() <= event.y_root <= row.winfo_rooty() + row.winfo_height()
            if on_row:   # out onto the row, in front of the first button whose middle is right of the pointer
                before = next((b._button["id"] for b in self.play_buttons
                               if b.winfo_rooty() <= event.y_root <= b.winfo_rooty() + b.winfo_height()
                               and event.x_root < b.winfo_rootx() + b.winfo_width() // 2), None)
                buttons.unnest(child["id"])
                buttons.move_to(child["id"], before)
                self._notice(t("Note: {name} is back on the Play tab.", name=child["name"]))
        self.refresh_buttons()

    def _show_drag_image_for(self, name):
        """A drag image for a playlist that has no button on the row (one dragged out of a drop-down)."""
        self._hide_drag_image()
        sample = FlatButton(self.button_row, text=name, width=18, height=2)   # never placed: drawn for its picture
        top = self._drag_image = tk.Toplevel(self)
        top.withdraw()
        top.overrideredirect(True)
        try:
            top.attributes("-topmost", True)
            top.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        top.configure(bg=self.button_row.cget("bg"))
        tk.Label(top, image=sample._label.cget("image"), text=name, compound="center", font=sample._font,
                 fg=sample._label.cget("fg"), bg=self.button_row.cget("bg"), bd=0, highlightthickness=0).pack()
        top._sample = sample   # keeps the image alive
        top.update_idletasks()
        top.deiconify()

    def _child_menu(self, event, parent, child):
        """Right-click on a child in the menu: Make Default (or Plain Again), Out to the Row, Settings."""
        import review_gui
        p = review_gui.palette()
        menu = tk.Menu(self, tearoff=0, bg=p["bg"], fg=p["text"], activebackground=p["row_on"],
                       activeforeground=p["accent"])
        is_default = buttons.get(parent["id"]).get("default") == child["id"]
        menu.add_command(label=t("Make Default") if not is_default else t("Not the Default"),
                         command=lambda: self._set_default(parent, "" if is_default else child["id"]))
        menu.add_command(label=t("Out to the Row"), command=lambda: self._unnest(child))
        menu.add_command(label=t("Settings"), command=lambda: (self._close_children(),
                                                               self.open_playlist_settings(child["id"])))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _set_default(self, parent, child_id):
        buttons.set_default(parent["id"], child_id)
        self._close_children()
        self.refresh_buttons()

    def _unnest(self, child):
        self._close_children()
        if buttons.unnest(child["id"]):
            self.refresh_buttons()
            self._notice(t("Note: {name} is back on the Play tab.", name=child["name"]))

    # --- dragging a playlist: along the row, or onto the cog (its settings) or the cross (off the row) ---

    DRAG_START = 10   # pixels of movement before a press becomes a drag

    def _drag_start(self, event, fb):
        if fb._state != "normal":
            return
        self._drag = {"button": fb, "x": event.x_root, "y": event.y_root,
                      "grab": (event.x_root - fb.winfo_rootx(), event.y_root - fb.winfo_rooty())}
        self._drag_moved = False

    def _drag_move(self, event, fb):
        drag = getattr(self, "_drag", None)
        if not drag or drag["button"] is not fb:
            return
        if not self._drag_moved:
            if abs(event.x_root - drag["x"]) < self.DRAG_START and abs(event.y_root - drag["y"]) < self.DRAG_START:
                return
            self._drag_moved = True
            fb._pressed = False
            self._show_drag_image(fb)
            fb.config(dim=True)   # its slot stays, dimmed, and moves along the row as the pointer goes
            self._show_drop_targets(fb._button)
        gx, gy = drag["grab"]
        self._drag_image.geometry(f"+{event.x_root - gx}+{event.y_root - gy}")
        over = self._target_at(event.x_root, event.y_root)
        self._highlight_target(event.x_root, event.y_root)
        if over is None:
            self._watch_nest(fb._button, fb, event.x_root, event.y_root)
            if getattr(self, "_nest_target", None) is None:
                self._slide_slot(fb, event.x_root, event.y_root)
        else:
            self._watch_nest(fb._button, fb, None, None)

    NEST_HOLD = 500   # ms held over another button before it becomes the nest target

    def _watch_nest(self, playlist, fb, x_root, y_root):
        """
        Nesting by drag: the held playlist, kept over another button for a moment, nests under it on
        the drop. The button under the pointer is watched; after NEST_HOLD it lights as the target and
        a tag says "Nest under {name}". Moving off it clears. A playlist with children can't be nested,
        and a child dragged out of a drop-down can't go back into the same one. fb: the held playlist's
        own button, if it's on the row.
        """
        under = None
        if x_root is not None and not buttons.is_parent(playlist):
            for other in self.play_buttons:
                if (other is fb or other._button["id"] == (playlist.get("parent") or "")
                        or buttons.is_radio(other._button)):
                    continue   # Radio's arrow lists lanes, so nothing nests under it
                if (other.winfo_rootx() <= x_root <= other.winfo_rootx() + other.winfo_width()
                        and other.winfo_rooty() <= y_root <= other.winfo_rooty() + other.winfo_height()):
                    under = other
                    break
        if under is getattr(self, "_nest_watch", None):
            return
        self._clear_nest()
        self._nest_watch = under
        if under is not None:
            self._nest_job = self.after(self.NEST_HOLD, lambda: self._mark_nest(under))

    def _mark_nest(self, target):
        self._nest_job = None
        self._nest_target = target
        target.config(target=True)
        px = self.winfo_fpixels("1i") / 96.0
        tag = self._nest_tag = tk.Label(self.button_row, text=t("Nest under {name}", name=target._button["name"]),
                                        font=("Segoe UI", 8, "bold"), bg=PALETTE["button_fg"], fg="#000000",
                                        padx=int(8 * px), pady=int(2 * px))
        tag.place(x=target.winfo_x(), y=target.winfo_y() + target.winfo_height() - int(6 * px))
        tag.lift()

    def _clear_nest(self):
        job = getattr(self, "_nest_job", None)
        if job is not None:
            self.after_cancel(job)
        self._nest_job = None
        target = getattr(self, "_nest_target", None)
        if target is not None and target.winfo_exists():
            target.config(target=False)
        self._nest_target = None
        self._nest_watch = None
        tag = getattr(self, "_nest_tag", None)
        if tag is not None:
            tag.destroy()
        self._nest_tag = None

    def _show_drag_image(self, fb):
        """
        The dragged playlist follows the pointer as a small borderless window with the button's look.
        (Tk clips a widget to its parent, so the button itself could never show over the console.)
        """
        self._hide_drag_image()
        top = self._drag_image = tk.Toplevel(self)
        top.withdraw()
        top.overrideredirect(True)
        try:
            top.attributes("-topmost", True)
            top.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        top.configure(bg=self.button_row.cget("bg"))
        tk.Label(top, image=fb._label.cget("image"), text=fb._name, compound="center", font=fb._font,
                 fg=fb._label.cget("fg"), bg=self.button_row.cget("bg"), bd=0, highlightthickness=0).pack()
        top.geometry(f"+{fb.winfo_rootx()}+{fb.winfo_rooty()}")
        top.deiconify()

    def _hide_drag_image(self):
        top = getattr(self, "_drag_image", None)
        if top is not None:
            try:
                sample = getattr(top, "_sample", None)
                if sample is not None:
                    sample.destroy()
                top.destroy()
            except tk.TclError:
                pass
        self._drag_image = None

    def _slide_slot(self, fb, x_root, y_root):
        """
        Live reordering: the dragged playlist's slot moves in front of the first button whose middle is
        right of the pointer on the pointer's row, and the row re-flows, so the gap opens where the
        drop will land. Below the row (over the console) nothing moves.
        """
        others = [b for b in self.play_buttons if b is not fb]
        rows = sorted({b.winfo_rooty() for b in others})
        row_y = next((y for y in rows if y <= y_root <= y + fb.winfo_height() + BUTTON_GAP), None)
        if row_y is None:
            return
        on_row = [b for b in others if b.winfo_rooty() == row_y]
        before = next((b for b in on_row if x_root < b.winfo_rootx() + b.winfo_width() // 2), None)
        if before is None:   # past the row's last button: after it, so before whatever follows on the next row
            after_row = [b for b in others if b.winfo_rooty() > row_y]
            before = after_row[0] if after_row else None
        order = others[:]
        order.insert(order.index(before) if before is not None else len(order), fb)
        if order != self.play_buttons:
            self.play_buttons = order
            self._flow_buttons()

    def _drag_end(self, event, fb):
        drag = getattr(self, "_drag", None)
        self._drag = None
        if not drag or drag["button"] is not fb or not self._drag_moved:
            self._drag_moved = False
            return
        target = self._target_at(event.x_root, event.y_root)
        nest_into = getattr(self, "_nest_target", None)
        self._clear_nest()
        self._hide_drop_targets()
        self._hide_drag_image()
        button = fb._button
        if target == "settings":
            self.open_playlist_settings(button["id"])
        elif target == "use":
            self._use_settings_of(button)
        elif target == "remove":
            self._delete_button(button)
        elif nest_into is not None:   # held over another playlist: under it, into its menu
            parent = nest_into._button
            if buttons.nest(button["id"], parent["id"]):
                self._notice(t("Note: {child} is under {parent} now. The arrow on {parent} lists it.",
                                   child=button["name"], parent=parent["name"]))
        else:   # dropped on the row: where its slot has slid to
            i = self.play_buttons.index(fb)
            before = self.play_buttons[i + 1]._button["id"] if i + 1 < len(self.play_buttons) else None
            buttons.move_to(button["id"], before)
        self.after(50, lambda: setattr(self, "_drag_moved", False))
        self.refresh_buttons()

    def _show_drop_targets(self, button):
        """
        While a playlist is held, a strip slides over the top of the console with two big pills in the
        middle, Settings (the accent) and Remove (orange): a thin dashed outline each, filled in while
        the pointer is over it.
        """
        self._hide_drop_targets()
        scale = self.winfo_fpixels("1i") / 96.0
        px = lambda n: max(1, int(round(n * scale)))   # noqa: E731
        strip_bg = tabs.mix_colour(self, "#ffffff", "#000000", 0.11)
        box = self._drop_box = tk.Frame(self.console_box, bg=strip_bg)
        box.place(relx=0, y=0, relwidth=1)
        inner = tk.Frame(box, bg=strip_bg)
        inner.pack(pady=px(12))   # packed without a side: centred
        self._targets = {}
        # the pills read at the Play buttons' text size, fifteen percent smaller than before (Ben, 2 Nov 2026)
        font = ("Segoe UI", tkfont.nametofont("TkDefaultFont").actual("size"), "bold")
        measure = tkfont.Font(root=self, font=font)
        h = px(48)
        pills = [("settings", "\u2699  " + t("Settings"), PALETTE["button_fg"]),
                 ("remove", "\u2715  " + t("Delete"), PALETTE["brand_orange"])]
        if playmix.is_open():   # the row's switches can take this playlist's settings
            pills.append(("use", "\u2913  " + t("Use Its Settings"), self.seed_colour))
        for key, text, colour in pills:
            w = max(measure.measure(text) + px(54), px(170))
            cell = tk.Frame(inner, bg=strip_bg, padx=px(14))
            cell.pack(side="left")
            pill = DropPill(cell, w, h, text, colour, strip_bg, font, px)
            pill.pack()
            self._targets[key] = (cell, pill)

    def _hide_drop_targets(self):
        box = getattr(self, "_drop_box", None)
        if box is not None:
            box.destroy()
        self._drop_box, self._targets = None, {}

    def _target_at(self, x_root, y_root):
        for key, (cell, _pill) in getattr(self, "_targets", {}).items():
            if (cell.winfo_rootx() <= x_root <= cell.winfo_rootx() + cell.winfo_width()
                    and cell.winfo_rooty() <= y_root <= cell.winfo_rooty() + cell.winfo_height()):
                return key
        return None

    def _highlight_target(self, x_root, y_root):
        over = self._target_at(x_root, y_root)
        for key, (_cell, pill) in getattr(self, "_targets", {}).items():
            pill.set_lit(key == over)

    def open_playlist_settings(self, button_id, rename=False):
        """Settings, on this playlist's page (rename: with the name box open, for a new playlist)."""
        if self.settings is None:
            return
        self.settings.show_playlist(button_id, rename=rename)
        try:
            self.master.select(self.settings)
        except (AttributeError, tk.TclError):
            pass

    def _standard_button(self, kind):
        """The playlist a keyboard Enter or an old caller means: the standard one of that kind, if any."""
        button = buttons.standard(kind)
        if button is None:
            messagebox.showinfo(t("No Playlist"), t("There's no {kind} playlist. Right-click a playlist and choose "
                                                    "Restore Default Playlists.", kind=t(buttons.KIND_NAMES[kind])),
                                parent=self)
        return button

    def _ask_new_button(self):
        """The New Playlist window. (name, kind, the id to start from) or None for Cancel."""
        return ask_new_button(self)

    def on_add_button(self, event=None):
        """+: the Add a Playlist window, with its three ways in (from existing, from template, new)."""
        self._new_playlist()

    def _new_playlist(self):
        answer = self._ask_new_button()
        if answer is None:
            return
        button, wants_page = buttons.add_from_choice(answer)
        self.refresh_buttons()
        if button is None:
            return
        if wants_page:   # New: its page opens with the name box ready to type in
            self.open_playlist_settings(button["id"], rename=True)
        else:
            self._notice(t("Note: {name} is on the Play tab.", name=button["name"]))

    def _button_menu(self, event, button):
        """Right-click on a playlist: Rename, Duplicate, Settings, Move Left, Move Right, Remove; and Restore."""
        import review_gui
        p = review_gui.palette()   # the colours Review's Preview menu uses
        menu = tk.Menu(self, tearoff=0, bg=p["bg"], fg=p["text"], activebackground=p["row_on"],
                       activeforeground=p["accent"])
        if button is not None:
            ids = [b["id"] for b in buttons.shown()]
            i = ids.index(button["id"]) if button["id"] in ids else -1
            menu.add_command(label=t("Rename"), command=lambda: self._rename_button(button))
            menu.add_command(label=t("Duplicate"), command=lambda: self._duplicate_button(button))
            menu.add_command(label=t("Settings"), command=lambda: self.open_playlist_settings(button["id"]))
            menu.add_separator()
            menu.add_command(label=t("Move Left"), state="normal" if i > 0 else "disabled",
                             command=lambda: (buttons.move_shown(button["id"], -1), self.refresh_buttons()))
            menu.add_command(label=t("Move Right"), state="normal" if 0 <= i < len(ids) - 1 else "disabled",
                             command=lambda: (buttons.move_shown(button["id"], 1), self.refresh_buttons()))
            menu.add_command(label=t("Delete"), command=lambda: self._delete_button(button))
            menu.add_separator()
        menu.add_command(label=t("Restore Default Playlists"), state="normal" if buttons.missing_shipped() else "disabled",
                         command=lambda: (buttons.restore_standard(), self.refresh_buttons()))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _rename_button(self, button):
        name = tabs.ask_name(self, t("Rename Playlist"), t("Name"), initial=button["name"])
        if name and name.strip():
            buttons.rename(button["id"], name)
            self.refresh_buttons()

    def _duplicate_button(self, button):
        new = buttons.duplicate(button["id"])
        self.refresh_buttons()
        if new is not None:
            self.open_playlist_settings(new["id"])

    def _delete_button(self, button):
        """
        Deletes a playlist from the Play tab (the Delete pill or right-click Delete), after asking. There's no
        off-the-row state any more (2 Nov 2026): a playlist is a button or a device's. Its children come out
        onto the row; one 24bit7 ships comes back with Restore Default Playlists.
        """
        if not messagebox.askyesno(t("Delete Playlist"),
                                   t("Delete {name}? Its page and settings go with it. Restore Default Playlists brings "
                                     "back one 24bit7 ships.", name=button["name"]), parent=self):
            return
        buttons.remove(button["id"])
        self.refresh_buttons()
        self._live.clear()   # a fresh console for the note (Ben, 1 Nov)
        self._clear_log()
        self._notice(t("Note: {name} deleted.", name=button["name"]))

    def on_button(self, button):
        """Runs a playlist: from the Search tab's typed seed, or from the Now Playing zone's track."""
        if self.running:
            return
        if button["kind"] is None:   # a blank slate: say so, and open its page to add a config
            self._append_log(t(buttons.NO_CONFIG_YET, name=button["name"]))
            self.open_playlist_settings(button["id"])
            return
        if buttons.is_radio(button):   # no seed: its lane
            return self.on_radio(button)
        top_up = bool(getattr(self, "top_up_armed", False))   # let go of when the build starts
        if button["kind"] == "vibe":
            return self.on_vibe(button, top_up=top_up)
        if self._seed_is_search():
            seed = self._typed_seed(need_track=buttons.needs_track(button),
                                    why=engine.SIMILAR_NEEDS_TRACK_TEXT if button["kind"] == "artists" else None)
            if seed:
                self._run_typed(lambda **kw: buttons.run(button, **kw), seed, lambda: self.on_button(button),
                                top_up=top_up)
            return
        options = {}
        if buttons.follows_seed(button):
            options["playing_now"] = engine.play_seed_is_playing_now()   # the Seed setting
        self._run_job(lambda: self._seeded(lambda **kw: buttons.run(button, **kw), **options),
                      needs_playing=False, review=True, top_up=top_up)

    def _toggle_more(self):
        self._show_more(not self.extras_row.winfo_manager())

    def _show_more(self, open_, save=True):
        """Opens or closes the More options row. Open or closed is remembered between launches."""
        if open_:
            self.more_line.pack(fill="x", padx=16, pady=(6, 0))
            self.extras_row.pack(fill="x", pady=(12, 2))   # the console below has its own top margin
            self.mix_rows.pack(fill="x")
        else:
            self._set_top_up(False)   # it's on the row: closing the row lets go of it
            self.mix_rows.pack_forget()
            self.extras_row.pack_forget()
            self.more_line.pack_forget()
            self.more_box.configure(height=1)   # Tk keeps an emptied frame's size otherwise
            if save:   # closed by hand: the notices go, the build's lines stay (Ben, 6 Nov 2026)
                self._clear_notices()
        if save:
            playmix.set_open(open_)
        self._update_more_label()
        if open_:   # opened by hand, or found open at start-up: one line saying what the row does
            self.after_idle(lambda: self._say_overrides(by_hand=save))

    def _say_overrides(self, by_hand):
        """One console line each time the row opens; the first time it's opened by hand, a dialog too (Ben, 2 Nov 2026)."""
        self._sync_override_switches()
        self._notice(t(overrides.OPEN_LINE))
        if by_hand and not overrides.told():
            overrides.set_told()
            messagebox.showinfo(t("More Options"), t(overrides.OPEN_LINE) + "\n\n"
                                + t("Click the Moderator, Deep Cuts and Non-stop switches here to step through their "
                                    "settings. Off turns the thing off for every playlist; any other setting runs for "
                                    "every playlist. Drag a playlist onto Use Its Settings to set the switches from its "
                                    "page."), parent=self)

    def _sync_override_switches(self):
        """The three switches read what's saved (after a change, a drop on Use Its Settings, or at start-up)."""
        if not getattr(self, "override_vars", None):
            return
        for key, value in overrides.switches().items():
            self.override_vars[key].set(overrides.LABELS[value])

    def _on_override_changed(self, key):
        value = overrides.code_for(key, self.override_vars[key].get())
        overrides.set_switch(key, value)
        self.override_cbs[key].selection_clear()
        if key == "moderator" and value != "off":
            warn_moderator_once(self)
        # no console line per click (Ben, 2 Nov 2026): the line on opening the row says what the switches do,
        # and each build says what the row applied

    def _use_settings_of(self, button):
        """The Use Its Settings pill: the three switches take what this playlist's own page has."""
        values = overrides.set_switches(overrides.from_playlist(button))
        self._sync_override_switches()
        self._notice(t("Note: More Options set from {name}: {switches}.", name=button["name"],
                           switches=overrides.summary()))
        return values

    def _on_mix_rows_changed(self):
        """An added playlist changed: the console says what the next build will do, once per change."""
        self._update_more_label()
        line = "Note: " + playmix.summary(self.mix_rows.rows)
        if line != getattr(self, "_mix_note_shown", None):
            self._mix_note_shown = line
            self._notice(line)

    def _update_more_label(self):
        """The More options button's arrow: up while the row is open, down while it's closed."""
        open_ = bool(self.extras_row.winfo_manager())
        self.more_button.config(text=t("More Options") + (" \u25b4" if open_ else " \u25be"))

    @staticmethod
    def _output_label(target):
        if target == "youtube":
            return "YouTube"
        if target == "tidal":
            return "Tidal"
        if target == "multiroom":
            return MULTIROOM_LABEL
        if target.startswith("zone:"):
            return target[5:]
        return t(SAME_ZONE_LABEL)

    def _fill_output_list(self):
        self.output_cb.config(values=[t(SAME_ZONE_LABEL)] + engine.listed_zone_names() + self._extra_outputs())

    @staticmethod
    def _extra_outputs():
        """
        The services ticked under Settings > Other > Additional Outputs, as Output offers them, and Multiroom
        while it's enabled under Settings > Other > Multiroom.
        """
        engine.refresh_settings_if_changed()
        extra = [label for code, label in sorted(engine.OUTPUT_OPTIONS, key=lambda o: o[1])
                 if code in engine.EXTRA_OUTPUTS]
        if engine.MULTIROOM_ENABLED:
            extra.insert(0, MULTIROOM_LABEL)
        return extra

    def outputs_changed(self):
        """Additional Outputs changed: an Output that's been unticked goes back to Same zone, and says so."""
        was = self.output_var.get()
        offered = self._extra_outputs()   # rereads the settings first
        if engine.OUTPUT_TARGET.startswith("zone:"):
            return   # a JRiver zone, whatever it's called: nothing was unticked from under it
        if was in list(dict(engine.OUTPUT_OPTIONS).values()) + [MULTIROOM_LABEL] and was not in offered:
            self.output_var.set(t(SAME_ZONE_LABEL))
            self._on_output_changed()
            where = t("Multiroom") if was == MULTIROOM_LABEL else t("Additional Outputs")
            messagebox.showinfo(t("Output"), t("{was} is no longer ticked under {where}, so Output is "
                                               "back to {same}.", was=was, where=where, same=t(SAME_ZONE_LABEL)),
                                parent=self)

    def _on_output_changed(self, *_):
        choice = self.output_var.get()
        engine.refresh_settings_if_changed()
        # "Multiroom" is the feature only while it's on; off, it's a JRiver zone of that name (10 Nov 2026)
        target = ("youtube" if choice == "YouTube" else "tidal" if choice == "Tidal" else
                  "jriver" if choice == t(SAME_ZONE_LABEL) else engine.multiroom_or_zone(choice))
        try:
            write_env({"OUTPUT_TARGET": target})
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)
        self.output_cb.selection_clear()
        if target == "tidal" and not engine.tidal_signed_in():
            messagebox.showinfo("Tidal", t("To send playlists to Tidal, sign in first: Settings > Keys, "
                                           "Sign In to Tidal."), parent=self)
        self._sync_multiroom(target)
        self._sync_behaviour()
        self._sync_top_up()
        panel = getattr(self, "review_panel", None)
        if panel is not None:
            panel.output_changed()   # Review's actions go wherever Output now says

    # --- Multiroom ---------------------------------------------------------------------------------

    def _sync_multiroom(self, target=None):
        """
        The follower runs while Output is Multiroom: picked, or left so when 24bit7 opens, the child starts and
        the Speakers join whatever the Sonos is playing, or wait for it to play. Any other Output lets the Speakers
        finish their track, then stops them following.
        """
        engine.refresh_settings_if_changed()
        if target is None:
            target = engine.OUTPUT_TARGET
        if target == "multiroom" and engine.MULTIROOM_ENABLED:
            self.multiroom.start(engine.multiroom_settings())
        elif self.multiroom.wanted or self.multiroom.running():
            # the Speakers finish the track they're on, then stop (Ben, 9 Nov 2026): a new playlist never cuts
            # the track that's playing, and the follower says so in the console
            self.multiroom.leave()

    def multiroom_build_sent(self):
        """
        engine.MULTIROOM_HOOK: a playlist went to the leader zone. A follower already following is left be; one
        that was told to leave (a request by voice in the leader's room) sits idle, still connected, so it's
        whether it's wanted that counts, not whether it's running.
        """
        if not self.multiroom.wanted:
            self.multiroom.start(engine.multiroom_settings())

    # --- Top-Up -----------------------------------------------------------------------------------

    def _top_up_greyed(self):
        return self.output_var.get() in ("YouTube", "Tidal")

    def _sync_top_up(self):
        """Greyed, and let go of, while Output is YouTube or Tidal."""
        if self._top_up_greyed():
            self._set_top_up(False)
            self.top_up_button.config(state="disabled")
        else:
            self.top_up_button.config(state="normal")

    def _toggle_top_up(self):
        self._set_top_up(not self.top_up_armed)

    def _set_top_up(self, armed):
        """Armed: teal edge and text, and a line saying what happens next. Let go: back to plain, the line gone."""
        if armed == getattr(self, "top_up_armed", False):
            return
        self.top_up_armed = armed
        self.top_up_button.config(armed=self.seed_colour if armed else None)
        line = getattr(self, "_top_up_line", None)
        if armed:
            self._top_up_line = t("Top-Up is on: the next playlist you click goes into what's left of Playing Now. "
                                  "Click Top-Up again to cancel.")
            self._notice(self._top_up_line)
        elif line:
            self._top_up_line = None
            self._drop_notice(line)

    def _sync_behaviour(self):
        """Review works with any Output, YouTube included (it opens the ticked tracks there)."""
        if getattr(self, "behaviour_cb", None) is not None:
            self.behaviour_cb.state(["!disabled"])

    def _on_seed_changed(self, *_):
        """The Seed button: saved straight to .env, the bars follow, and the first switch to Playing Now explains it."""
        playing_now = self.seed_var.get() == "Playing Now"
        try:
            write_env({"PLAY_SEED": "playing_now" if playing_now else "current"})
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)
        self._sync_seed_bars()
        if playing_now and read_env().get("SEED_PLAYING_NOW_SEEN", "").strip() != "1":
            try:
                write_env({"SEED_PLAYING_NOW_SEEN": "1"})
            except Exception:
                pass

            def explain():
                for line in self._seed_explainer():
                    self.log_queue.put(line)
            # after the greeting has cleared the console, so the note isn't wiped with it
            self.after(13000 if self._greeting_active else 0, explain)

    def _seed_explainer(self):
        """The once-only console note for Seed: Playing Now, with the figures as they're set now."""
        art, trk = engine.playing_now_artist_figures(), engine.playing_now_track_figures()
        return [
            "Seed: Playing Now",
            "  Builds now start from your whole Playing Now list instead of the track that's playing.",
            f"  Similar Artists picks {art['PN_SAMPLE_ARTISTS']} artists from the list at random, then finds "
            f"{art['PN_ARTISTS_PER_SAMPLE']} similar artists for each, taking them in turn so nobody repeats. "
            f"Similar Tracks picks {trk['PN_SAMPLE_TRACKS']} tracks at random, each from a different artist, "
            f"and finds {trk['PN_TRACKS_PER_SAMPLE']} similar tracks for each.",
            "  Only artists and tracks in your library count. If one isn't there, 24bit7 moves further down "
            "the list.",
            "  Tracks already in Playing Now are left out, and the new list replaces Playing Now as usual. Use "
            "Review Mode if you want to add to it instead.",
            "  Results are usually broader than Current Track, and each build differs because the sample is "
            "random.",
            "  Only Similar Artists and Similar Tracks follow Seed. Change these figures in Settings > "
            "Playlist, Playing Now column.",
        ]

    def _sync_seed_bars(self):
        """Similar Artists and Similar Tracks get teal bars while Seed is Playing Now (and Now Playing is up)."""
        if not getattr(self, "buttons", None) or not hasattr(self, "seed_var"):
            return
        teal = self._seed_teal()
        for b in self.buttons:
            button = getattr(b, "_button", None)
            if button is None:
                continue
            if buttons.follows_seed(buttons.runs(button)):   # what the main part builds follows Seed
                b._accent = self.seed_colour if teal else None
                b._draw()

    def _seed_teal(self):
        """Whether Seed is on Playing Now and in force (the Now Playing tab, not Search)."""
        return getattr(self, "seed_var", None) is not None and self.seed_var.get() == "Playing Now" \
            and not self._seed_has_row()

    def _on_behaviour_changed(self, *_):
        code = {shown: c for c, shown in PLAY_BEHAVIOUR}.get(self.behaviour_var.get(), "instant")
        try:
            write_env({"PLAY_BEHAVIOUR": code})
        except Exception as e:
            messagebox.showerror(t("Save failed"), str(e), parent=self)
        self.behaviour_cb.selection_clear()

    def _review_mode(self):
        return getattr(self, "behaviour_var", None) is not None and self.behaviour_var.get() == "Review"

    def sync_moderator(self):
        """After Settings changed: the AI buttons grey out or come back, and More Options' arrow is redrawn."""
        if self.running:
            return   # a build may have a playlist's settings loaded
        engine.refresh_settings_if_changed()
        self._sync_ai_button()
        self._update_more_label()

    def _sync_ai_button(self):
        """Every AI Playlist button greys out while Use AI is Off (Settings > Keys) or there's no key."""
        on = engine.ai_enabled()
        if getattr(self, "override_cbs", None):
            self.override_cbs["moderator"].state(["!disabled"] if on else ["disabled"])
        for button in self.play_buttons:
            if getattr(button, "_kind", None) != "vibe":
                continue
            if not self.running:   # resting on JRiver Playlists too, as every playlist does there
                button.config(state="normal" if on and not self._seed_is_playlists() else "disabled")
            button._ai_tip.text = (t("AI Playlist needs {what} under Settings > Keys.", what=engine.ai_missing_text())
                                   if not engine.ai_configured() else
                                   t("Paused: Use AI is Off under Settings > Keys."))

    def _build_log(self):
        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        # The console: a black box holding the tab row (when open) and the text
        self.console_box = tk.Frame(frame, bg="#000000", highlightthickness=1, highlightbackground="#555555")
        self.console_box.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(self.console_box, wrap="word", state="disabled",
                                             font=("Consolas", 9), bg="#000000", fg=tabs.MATRIX_FG,
                                             insertbackground=tabs.MATRIX_FG, bd=0, highlightthickness=0)
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
        self._held = []   # console lines that arrive while the greeting types: shown once it clears
        self._type_greeting(t("Follow the white rabbit."), 0)
        threading.Thread(target=lambda: engine.say_if_newer(self.report), daemon=True, name="update-check").start()
        engine.say_failing_sources(self.report)

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
        Shows the AI Usage total at the right of the Now Playing and Search tabs' row while
        it's ticked in Settings > Keys (Output has the right of the Zone line).
        """
        try:
            engine.refresh_settings_if_changed()
            want = os.getenv("AI_USAGE_NOW_PLAYING", "0").strip() == "1"
            if want:
                self.usage_label.config(text=ai_usage.short(unit=self._usage_unit()))
                # on the row with the Now Playing and Search tabs, so it shows on both
                self.usage_box.place(in_=self.seed_nb._strip, relx=1.0, rely=0.5, anchor="e", x=-26)
                self.usage_box.lift()
            elif self._usage_shown:
                self.usage_box.place_forget()
            self._usage_shown = want
        except Exception as e:
            if not getattr(self, "_usage_error_said", False):
                self._usage_error_said = True
                print("  " + t("Problem: the AI Usage total couldn't show in Now Playing ({e}).", e=e))

    def _usage_unit(self):
        unit = os.getenv("AI_USAGE_NP_UNIT", "dollars").strip().lower()
        return unit if unit in ("dollars", "tokens") else "dollars"

    def _usage_flip(self, _e=None):
        """Clicking the Now Playing total switches it between dollars and tokens, and remembers it."""
        unit = "tokens" if self._usage_unit() == "dollars" else "dollars"
        try:
            write_env({"AI_USAGE_NP_UNIT": unit})
        except Exception as e:
            print("  " + t("Problem: couldn't save the AI Usage display choice ({e}).", e=e))
            return
        self._sync_usage_box()
        if self.settings is not None and hasattr(self.settings, "usage_unit_var"):
            self.settings.usage_unit_var.set(unit.title())

    def _usage_clear(self):
        if messagebox.askyesno(t("Clear AI Usage"), t("Clear the token count? It starts again from now."), parent=self):
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
            messagebox.showinfo(t("AI Usage"), t(NO_KEY_TEXT), parent=self)
            return
        try:
            self.master.select(self)   # asked from Settings: show the console
        except Exception:
            pass
        self._end_greeting()
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
            self.np_track.show((t("Track:") + "\t", "prefix"), (info.get("Name", "?"), None))
            self.np_detail.show((t("Artist:") + "\t", "prefix"), (info.get("Artist", "?"), None),
                                ("   \u00b7   ", None),
                                (t("Album:") + " ", "prefix"), (info.get("Album", "?"), None))
            self.last_playing = info
        else:
            self.np_track.show((t("Nothing playing"), None))
            self.np_detail.show((t("Start a track in this zone to seed from it"), None))
            self.last_playing = None
        self._sync_np_controls(info)
        self.seed_nb.even_out()   # a long title can wrap onto another line: every tab grows with it

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
        self._end_greeting()

    def _end_greeting(self, keep=True):
        """The greeting goes. keep: the lines that arrived while it typed go on screen in its place;
        otherwise (Clear, Close Review, a build starting) they're dropped, as the screen is being cleared."""
        held, self._held = self._held, []
        if not self._greeting_active:
            return
        self._greeting_active = False
        self._clear_log()
        if keep:
            for line in held:
                self._insert_line(line, notice=line in getattr(self, "_notices", []))

    @staticmethod
    def _line_kind(line):
        """Which colour a console line takes, from how it's written."""
        body = re.sub(r"^\d\d:\d\d  ", "", line.strip())
        if advanced_only(line):
            return "debug"
        if multiroom_link.is_problem(line):
            return "problem"
        if multiroom_link.is_note(line):
            return "note"
        if body.startswith(i18n.either(PROBLEM)):
            return "problem"
        if body.startswith(i18n.either(NOTE)):
            return "note"
        if body.startswith(i18n.either(DONE)) or (body and not line.startswith((" ", "\n"))):
            return "head"
        if any(re.search(rf"\b{re.escape(word)}\b", body) for word in i18n.either("AI")) or \
                body.startswith(i18n.either(REMOVED)):
            return "ai"
        return None

    def _notice(self, line):
        """A line that tells you about something you did (a note, the More Options line), not part of a build:
        closing More Options takes these away and leaves the build's own lines (Ben, 6 Nov 2026)."""
        return self._append_log(line, notice=True)

    def _drop_notice(self, line):
        """Takes one notice off the console (Top-Up cancelled); the others stay."""
        notices = getattr(self, "_notices", [])
        if line not in notices:
            return
        notices.remove(line)
        for kept in (self._live, self._held):
            if line in kept:
                del kept[len(kept) - 1 - kept[::-1].index(line)]
        self.log.config(state="normal")
        ranges = self.log.tag_ranges("notice")
        for start, end in reversed(list(zip(ranges[0::2], ranges[1::2]))):
            if line in self.log.get(start, end):
                self.log.delete(start, end)
                break
        self.log.config(state="disabled")

    def _clear_notices(self):
        """Takes the notices off the console and out of the kept lines; a build's lines stay as they are."""
        notices, self._notices = getattr(self, "_notices", []), []
        for line in notices:
            for kept in (self._live, self._held):
                if line in kept:
                    del kept[len(kept) - 1 - kept[::-1].index(line)]   # the latest copy: that's the notice
        self.log.config(state="normal")
        ranges = self.log.tag_ranges("notice")
        for start, end in reversed(list(zip(ranges[0::2], ranges[1::2]))):
            self.log.delete(start, end)
        self.log.config(state="disabled")
        self._mix_note_shown = None   # the same note can show again after the next change

    def _append_log(self, line, notice=False):
        if getattr(self, "_stamp_next", False) and line.strip():
            line = time.strftime("%H:%M") + "  " + line.lstrip("\n")
            self._stamp_next = False
        self._live.append(line)
        if notice:
            self._notices = getattr(self, "_notices", []) + [line]
        if getattr(self, "review_panel", None) is not None:
            self.review_panel.console_activity()   # a dot on Console while Review is showing
        if self._greeting_active:
            self._held.append(line)   # not into the middle of the greeting: shown once it clears
            return line
        self._insert_line(line, notice=notice)
        return line

    def _insert_line(self, line, notice=False):
        """Puts a line on screen, coloured by its kind, if the tab it belongs to is the one showing."""
        if not self._live_visible():
            return   # another tab is showing: the line is kept for when this build's tab is chosen
        at_bottom = self.log.yview()[1] >= 0.999   # scrolled up to read? new lines don't pull you down
        self.log.config(state="normal")
        kind = self._line_kind(line)
        tags = ((kind,) if kind else ()) + (("notice",) if notice else ())
        link = re.search(re.escape(engine.RELEASES_PAGE) + r"\S+", line)   # the new-version line's download link
        if link:
            self.log.tag_configure("release_link", underline=True)
            self.log.tag_bind("release_link", "<Button-1>", lambda e, u=link.group(0): webbrowser.open(u))
            self.log.tag_bind("release_link", "<Enter>", lambda e: self.log.config(cursor="hand2"))
            self.log.tag_bind("release_link", "<Leave>", lambda e: self.log.config(cursor=""))
            self.log.insert("end", line[:link.start()], tags)
            self.log.insert("end", link.group(0), tags + ("release_link",))
            self.log.insert("end", line[link.end():] + "\n", tags)
        else:
            self.log.insert("end", line + "\n", tags)
        if at_bottom:
            self.log.see("end")
        self.log.config(state="disabled")

    def _append_tidal_links(self, pid):
        """
        Open in Tidal app (when it's installed) and Open in Tidal web, as links under the build,
        leaving out the one the playlist has just opened in.
        """
        app_url, web_url = engine.tidal_open_links(pid)
        opened = getattr(engine, "TIDAL_OPENED", None)
        links = ([("Open in Tidal app", app_url, "tidal_app")]
                 if engine.tidal_app_installed() and opened != "app" else []) + (
            [("Open in Tidal web", web_url, "tidal_web")] if opened != "web" else [])
        if not links:
            return
        self._live.append("  " + "  ·  ".join(text for text, _, _ in links))
        if not self._live_visible():
            return
        self.log.config(state="normal")
        self.log.insert("end", "  ")
        for n, (text, url, tag) in enumerate(links):
            if n:
                self.log.insert("end", "  ·  ")
            self.log.tag_configure(tag, foreground=tabs.MATRIX_FG, underline=True)
            self.log.tag_bind(tag, "<Button-1>", lambda e, u=url: self._open_tidal(u))
            self.log.tag_bind(tag, "<Enter>", lambda e: self.log.config(cursor="hand2"))
            self.log.tag_bind(tag, "<Leave>", lambda e: self.log.config(cursor=""))
            self.log.insert("end", text, (tag,))
        self.log.insert("end", "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _open_tidal(self, url):
        try:
            if url.startswith("tidal:"):
                os.startfile(url)   # the Tidal app, straight to the playlist
            else:
                webbrowser.open(url)
        except OSError as e:
            messagebox.showerror("Tidal", f"Couldn't open Tidal ({e}).", parent=self)

    def report(self, message):
        if engine.CANCEL_REQUESTED.is_set() and threading.current_thread() is getattr(self, "_worker", None):
            raise engine.BuildCancelled()   # Cancel: the build stops at its next console line
        self.log_queue.put(message)

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        try:
            while True:
                self.badge.problem(*self.badge_problems.get_nowait())
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

    def _badge_result(self):
        """A voice build has finished: the badge says how many tracks went in, or why none did."""
        job, self._badge_job = getattr(self, "_badge_job", None), None
        if not job:
            return
        if getattr(self, "_job_cancelled", False):
            return self.badge.hide()
        count = (engine.LAST_BUILD or {}).get("queued") or 0
        why = ""
        if not count:   # the build's last Problem line, without its label
            lines = "\n".join(self._live).splitlines()   # this build's lines, whichever tab is showing
            problems = [x.strip() for x in lines if x.strip().startswith(t("Problem:"))]
            if problems:
                why = problems[-1][len(t("Problem:")):].strip()
        self.badge.done(count, job[1], why)

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # --- the console strip: Copy and Clear, shown when you click into the console ---

    def _build_console_strip(self, frame):
        black, green, dim = "#000000", tabs.MATRIX_FG, tabs.MATRIX_HI   # the console's own colours
        self.console_strip = tk.Frame(frame, bg=black)
        self.console_buttons = {}
        self.console_frame = frame
        for name, command in ((N_("Copy"), self._copy_log), (N_("Clear"), self._clear_from_strip),
                              (N_("Query"), self._open_query), (N_("Export to Log"), self._export_log),
                              (N_("Mode"), self._toggle_console_mode), (N_("Cancel"), self._cancel_build)):
            b = tk.Label(self.console_strip, text=t(name), font=("Segoe UI", 8, "bold"), bg=black, fg=green,
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
        self.console_buttons["Mode"].config(text=t(self.console_mode.title()))
        self.console_buttons["Query"].pack_forget()
        self.console_buttons["Cancel"].pack_forget()   # shown on its own while a build runs
        self._build_query_panel(frame)
        self.log.bind("<Button-1>", lambda e: self._show_console_strip(), add="+")
        self.root.bind_all("<Button-1>", self._maybe_hide_console_strip, add="+")

    # --- the console's tabs: the green arrow opens All | Main Window | one per Alexa device ---

    def _head_box(self, parent, text, command):
        """A box in the tab row, drawn like the console: green on black, a thin dark green edge."""
        b = tk.Label(parent, text=text, font=("Consolas", 9), bg="#000000", fg=tabs.MATRIX_FG, padx=10, pady=2,
                     cursor="hand2", highlightthickness=1, highlightbackground=tabs.MATRIX_HI,
                     highlightcolor=tabs.MATRIX_HI)
        b.bind("<Button-1>", lambda e: command())
        return b

    def _build_console_head(self):
        black, green = "#000000", tabs.MATRIX_FG
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
        for name, command in ((N_("Copy"), self._copy_log), (N_("Clear"), self._clear_from_strip),
                              (N_("Query"), self._open_query), (N_("Export to Log"), self._export_log),
                              (N_("Mode"), self._toggle_console_mode), (N_("Cancel"), self._cancel_build)):
            b = self._head_box(self.head_strip, t(name), command)
            b.pack(side="left", padx=(4, 0))
            self.head_buttons[name] = b
        self.head_buttons["Query"].config(fg=AI_MAGENTA, highlightbackground=AI_MAGENTA, highlightcolor=AI_MAGENTA)
        self.head_buttons["Mode"].config(text=t(self.console_mode.title()))
        self.head_buttons["Cancel"].pack_forget()   # shown on its own while a build runs
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
    LOG_COLUMNS = [(N_("Date and Time"), 13), (N_("From"), 12), (N_("Zone"), 9), (N_("Playlist Type"), 30),
                   (N_("Sources Used"), 1), (N_("Hits / Misses"), 13), (N_("Moderator"), 20), (N_("Problems"), 17),
                   ("", 15)]
    SOURCES_COLUMN = 4

    def _sync_head_strip(self):
        """On the Log tab only Simple/Advanced shows; on a console tab, the whole strip."""
        if getattr(self, "running", False):
            return   # a build is running: Cancel shows on its own
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
        black, green, dim, white = "#000000", tabs.MATRIX_FG, tabs.MATRIX_HI, "#ffffff"
        grid = self.log_grid
        for child in grid.winfo_children():
            child.destroy()
        font, bold = ("Consolas", 9), ("Consolas", 9, "bold")
        cols = len(self.LOG_COLUMNS)
        grid.grid_columnconfigure(self.SOURCES_COLUMN, weight=1)
        try:
            rows = buildlog.recent()
        except Exception:
            rows = []
        # each column at least as wide as its title in the chosen language, and the Moderator's as its longest entry
        widths = [w if c == self.SOURCES_COLUMN else max(w, len(t(title))) for c, (title, w) in enumerate(self.LOG_COLUMNS)]
        widths[6] = min(26, max([widths[6]] + [len(buildlog.moderator_shown(row["moderator"])) for row in rows]))
        for c, (title, _) in enumerate(self.LOG_COLUMNS):
            tk.Label(grid, text=t(title), font=bold, bg=black, fg=white, anchor="w", width=widths[c]).grid(
                row=0, column=c, sticky="ew", padx=(0, 6), pady=(0, 4))
        tk.Frame(grid, bg=green, height=1).grid(row=1, column=0, columnspan=cols, sticky="ew")
        r = 2
        for row in rows:
            when = row["at"]
            try:
                at = datetime.strptime(row["at"], "%Y-%m-%d %H:%M:%S")
                when = f"{at:%d} {t(ai_usage.MONTHS[at.month - 1])} {at:%H:%M}"
            except (TypeError, ValueError):
                pass
            if row["queued"] is None:
                hits = ""
            elif row["misses"] is None:
                hits = t("{count} sent", count=row["queued"])
            else:
                hits = f"{row['queued']} / {row['misses']}"
            trouble = ", ".join(x for x in (
                tn("{count} problem", "{count} problems", row["problems"]) if row["problems"] else "",
                tn("{count} note", "{count} notes", row["notes"]) if row["notes"] else "") if x)
            values = [(when, green), (t(row["from_label"] or ""), green), (row["zone"] or "", green),
                      (buildlog.playlist_type(row), green), (row["sources"] or "", green), (hits, green),
                      (buildlog.moderator_shown(row["moderator"]), AI_MAGENTA),
                      (trouble, "#ff6b6b" if row["problems"] else "#ffb000")]
            cells = []
            for c, (value, colour) in enumerate(values):
                width = widths[c]
                if c != self.SOURCES_COLUMN and len(value) > width:   # too long for its column: cut short
                    value = value[:width - 3] + "..."
                cell = tk.Label(grid, text=value, font=font, bg=black, fg=colour, anchor="w", width=width)
                cell.grid(row=r, column=c, sticky="ew", padx=(0, 6), pady=3)
                if c == self.SOURCES_COLUMN and value:   # the column narrows with the window: full list on hover
                    Tooltip(cell, value)
                cells.append(cell)
            link = tk.Label(grid, text=t("Load to Console"), font=("Consolas", 9, "underline"), bg=black, fg=green,
                            cursor="hand2", anchor="w")
            link.grid(row=r, column=cols - 1, sticky="w", pady=3)
            link.bind("<Button-1>", lambda e, b=row: self._load_build(b))
            for cell in cells:
                cell.bind("<Double-Button-1>", lambda e, b=row: self._load_build(b))
            tk.Frame(grid, bg=dim, height=1).grid(row=r + 1, column=0, columnspan=cols, sticky="ew")
            r += 2
        if not rows:
            tk.Label(grid, text=t("No builds kept yet. Each build appears here once it finishes."), font=font,
                     bg=black, fg="#5f7a66", anchor="w").grid(row=r, column=0, columnspan=cols, sticky="w", pady=6)
        else:
            tk.Label(grid, text=t("The last 50 builds from each source, newest first. Double-click a row, "
                                  "or use Load to Console."), font=font, bg=black, fg="#5f7a66", anchor="w").grid(
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
        source = t("Main Window") if self.view == "main" else buildlog.device_name(self.view)
        self._show_text(row["text"] or "")
        self.log.config(state="normal")
        self.log.tag_configure("back", foreground=tabs.MATRIX_FG, underline=True)
        self.log.tag_bind("back", "<Button-1>", lambda e, v=self.view: self._select_view(v))
        self.log.tag_bind("back", "<Enter>", lambda e: self.log.config(cursor="hand2"))
        self.log.tag_bind("back", "<Leave>", lambda e: self.log.config(cursor=""))
        self.log.insert("1.0", "\n")
        self.log.insert("1.0", t("Loaded from Log: {source}, {when}", source=source, when=when) + chain + "  \u00b7  ")
        self.log.insert("1.end", t("Back to Latest"), ("back",))
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
        if getattr(self, "running", False):
            query.pack_forget()   # a build is running: Cancel shows on its own
            return
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
        for key, label in [("all", t("All")), ("main", t("Main Window"))] + devices + [("log", t("Log"))]:
            b = self._head_box(self.head_tabs, label, lambda k=key: self._select_view(k))
            if key == self.view:   # the tab on screen: inverted, green with black text
                b.config(bg=tabs.MATRIX_FG, fg="#000000", font=("Consolas", 9, "bold"), highlightbackground=tabs.MATRIX_FG)
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
            self.after(800, lambda: b.config(text=t(name)))

    def _show_console_strip(self):
        """Top-right inside the console, clear of its scrollbar. Query shows when it's switched on."""
        if getattr(self, "tabs_open", False):
            return   # with the tabs open, the strip sits in the tab row instead
        engine.refresh_settings_if_changed()
        query = self.console_buttons["Query"]
        if getattr(engine, "CONSOLE_QUERY", False) and engine.console_query_ready() and not self.running:
            if not query.winfo_manager():
                query.pack(side="left", padx=(0, 4), before=self.console_buttons["Export to Log"])
        else:
            query.pack_forget()
        self.console_strip.place(in_=self.log, relx=1.0, x=-6, y=6, anchor="ne")
        self.console_strip.lift()

    def _sync_cancel_strip(self):
        """While a build runs, both console strips show Cancel on its own; afterwards, the usual buttons."""
        running = getattr(self, "running", False)
        for buttons, pad in ((self.console_buttons, (0, 4)), (getattr(self, "head_buttons", {}), (4, 0))):
            if not buttons:
                continue
            for b in buttons.values():
                b.pack_forget()
            buttons["Cancel"].config(text="Cancel")
            if running:
                buttons["Cancel"].pack(side="left", padx=pad)
            else:
                for name in ("Copy", "Clear", "Export to Log", "Mode"):
                    buttons[name].pack(side="left", padx=pad)
        if not running:
            if hasattr(self, "head_buttons"):
                self._sync_head_strip()
            if self.console_strip.winfo_manager():
                self._show_console_strip()

    def _cancel_build(self):
        """The console's Cancel: the build stops at its next step and says what had already gone out."""
        if not self.running or engine.CANCEL_REQUESTED.is_set():
            return
        engine.CANCEL_REQUESTED.set()
        self.log_queue.put(t("Cancelling after the AI replies...") if engine.AI_BUSY else t("Cancelling..."))
        for buttons in (self.console_buttons, getattr(self, "head_buttons", {})):
            if "Cancel" in buttons:
                buttons["Cancel"].config(text=t("Cancelling..."))

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
        self.console_buttons["Mode"].config(text=t(self.console_mode.title()), bg="#000000")
        if hasattr(self, "head_buttons"):
            self.head_buttons["Mode"].config(text=t(self.console_mode.title()))
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
            text = "\n".join(x for x in text.split("\n") if not advanced_only(x))
        self.clipboard_clear()
        self.clipboard_append(text)
        b = self.console_buttons["Copy"]
        b.config(text=t("Copied"))
        self._flash_head("Copy", t("Copied"))

        def done():
            self.console_strip.place_forget()
            b.config(text=t("Copy"), bg="#000000")
        self.after(800, done)

    def _export_log(self):
        """Diagnostics plus the console to a dated file in logs\\, then shows it in Explorer."""
        b = self.console_buttons["Export to Log"]
        try:
            path = engine.export_log(self.log.get("1.0", "end-1c"))
        except Exception as e:
            messagebox.showerror(t("Export to Log"), t("Couldn't write the log: {error}", error=e), parent=self)
            return
        b.config(text=t("Saved"))
        self._flash_head("Export to Log", t("Saved"))
        try:
            subprocess.Popen(["explorer", "/select,", path])
        except Exception:
            pass

        def done():
            self.console_strip.place_forget()
            b.config(text=t("Export to Log"), bg="#000000")
        self.after(800, done)

    def _clear_from_strip(self):
        self._end_greeting(keep=False)   # stops the greeting typing on into an empty console
        self._clear_log()
        self.console_strip.place_forget()
        self.console_buttons["Clear"].config(bg="#000000")

    # --- Console Query: ask Claude about what's in the console ---

    def _build_query_panel(self, frame):
        """The box under the console: a question, Ask and Close, with grey hints underneath."""
        self.query_panel = tk.Frame(frame)
        row = tk.Frame(self.query_panel)
        row.pack(fill="x", pady=(8, 0))
        tk.Label(row, text=t("Ask the AI"), font=("Segoe UI", 9, "bold"),
                 fg=PALETTE["ai_purple"]).pack(side="left", padx=(0, 8))
        self.query_var = tk.StringVar()
        self.query_entry = tk.Entry(row, textvariable=self.query_var, font=("Segoe UI", 10))
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda e: self._send_query())
        self.query_send = FlatButton(row, text=t("Ask"), command=self._send_query, width=8, height=1,
                                     accent=PALETTE["ai_purple"])
        self.query_send.pack(side="left", padx=(8, 0))
        FlatButton(row, text=t("Close"), command=self._close_query, width=8, height=1,
                   quiet=True).pack(side="left", padx=(8, 0))
        tk.Label(self.query_panel, text=t(console_query.HINT), font=("Segoe UI", 8),
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
            messagebox.showinfo(t("Console Query"), t(NO_KEY_TEXT), parent=self)
            return
        self._greeting_active = False
        console = self.log.get("1.0", "end-1c")
        if self.console_mode == "simple":   # Query reads what you see: Advanced sends the debug lines too
            console = "\n".join(x for x in console.split("\n") if not advanced_only(x))
        self._query_busy = True
        self.query_send.config(text=t("Asking..."), state="disabled")
        self.query_var.set("")
        self._append_query(f"\nYou asked: {question}\n", bold=True)
        console_query.ask(question, console, self.last_playing,
                          lambda answer, error: self.after(0, lambda: self._query_done(answer, error)))

    def _query_done(self, answer, error):
        self._query_busy = False
        self.query_send.config(text=t("Ask"), state="normal")
        if error:
            self._append_query(f"Console Query didn't come back: {error}\n")
        else:
            self._append_query(answer + "\n")

    def _run_job(self, target, needs_playing=True, mix=True, origin=None, review=False, top_up=False):
        if self.running:
            return
        if needs_playing and not self.last_playing:
            messagebox.showinfo(t("Nothing playing"),
                                t("Start a track in JRiver first, then try again."))
            return
        self.running = True
        engine.CANCEL_REQUESTED.clear()
        self._sync_cancel_strip()
        self._job_origin = origin   # who asked, for the build's record: None is the Main Window
        self._end_greeting(keep=False)   # the build clears the screen anyway
        for b in self.buttons:
            b.config(state="disabled")
        self._begin_live(origin)
        self._stamp_next = True   # the build's first line gets the time
        self._badge_job = (origin or {}).get("badge")   # (asked, zone, uses AI) for a voice build
        if self._badge_job:
            self.badge.working(*self._badge_job)

        rows = (playmix.rows() or None) if mix else None   # added playlists: app builds only
        review = review and origin is None and self._review_mode()   # Review: app builds, never voice
        if origin is None:
            self._show_save(None)   # back after the build, if it went to a JRiver zone
        self._job_review = review
        top_up = bool(top_up and origin is None and getattr(self, "top_up_armed", False))
        if top_up:
            self._set_top_up(False)   # one playlist: the button lets go as it starts
        self._job_top_up = top_up
        if origin is None and getattr(self, "review_panel", None) is not None:
            self.review_panel.show_console()   # a build from the window: watch it run in the console

        def worker():
            self._worker = threading.current_thread()
            self._job_cancelled = False
            engine.LAST_NO_MATCH = False
            engine.SENT_ANY = False
            engine.MIX_ROWS, engine.MIX_KEEP, engine.MIX_FAST_KEY, engine.MIX_NOTED = rows, set(), None, False
            engine.REVIEW_MODE = review
            engine.TOP_UP = top_up
            engine.SAVE_NAME = None
            overrides = {}
            engine.BUILD_STARTED, engine.LAST_OUTPUT = time.time(), None
            engine.LAST_OUTPUT_ID, engine.LAST_BUILD = None, None
            try:
                if review:
                    engine.review_reset()
                    overrides = engine.review_overrides()   # Settings > Playlist's Review column
                    if overrides:
                        engine.use_profile(overrides)
                        self.log_queue.put("  " + t("Review settings in use (the standard button's Playlist page, the Review column)."))
                target()
                if review:
                    engine.REVIEW_ROWS = engine.review_rows(engine.REVIEW_KEYS)
            except engine.BuildCancelled:
                self._job_cancelled = True
                self.log_queue.put(engine.cancel_message())
            except Exception as e:
                self.log_queue.put(t("Problem: something went wrong ({e}). Press Export to Log and attach the file when you report it.", e=e))
            finally:
                engine.MIX_ROWS, engine.MIX_KEEP, engine.MIX_FAST_KEY = None, set(), None
                if overrides:
                    engine.use_profile({})   # back to Windows (Main)'s own figures
                engine.REVIEW_MODE = False
                engine.TOP_UP = False
                engine.BUILD_STARTED = None
                if engine.CANCEL_REQUESTED.is_set():
                    self._job_cancelled = True   # a voice build catches its own cancel and says so
                self._worker = None
                self.root.after(0, self._job_done)

        threading.Thread(target=worker, daemon=True).start()

    def _job_done(self):
        try:   # everything the build wrote, then keep it for the console's Log
            while True:
                self._append_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        if (engine.LAST_OUTPUT == "Tidal" and engine.TIDAL_PLAYLIST_ID and not getattr(self, "_job_cancelled", False)
                and getattr(self, "_job_origin", None) is None):
            self._append_tidal_links(engine.TIDAL_PLAYLIST_ID)
        if getattr(self, "_suggestion", None) and not getattr(self, "_job_cancelled", False):
            self._append_suggestion()
        try:
            buildlog.record_job(getattr(self, "_job_origin", None), self.log.get("1.0", "end-1c"))
        except Exception as e:
            print(t("Note: couldn't keep this build in the Log ({e}).", e=e))
        self._fill_tabs()   # a device's first build gives it a tab
        if hotkeys.take_restart():   # Switch Profiles queued a profile: restart now the job is done
            self.root.after(500, lambda: self.root.event_generate("<<Restart24bit7>>"))
        if getattr(self, "view", None) == "log":
            self._fill_log_table()
        self.running = False
        engine.CANCEL_REQUESTED.clear()
        self._sync_cancel_strip()
        self._badge_result()
        if (engine.LAST_NO_MATCH and getattr(self, "_job_origin", None) is None
                and not getattr(self, "_job_cancelled", False)):   # a build from the app found nothing at all
            engine.LAST_NO_MATCH = False
            self.after(50, lambda: messagebox.showinfo(t("No Match"), t(engine.APP_NO_MATCH), parent=self))
        for b in self.buttons:
            b.config(state="normal")
        self._sync_ai_button()
        self._sync_seed_buttons()
        self._sync_radio()   # a Re-analyse may have woken Radio
        try:
            self.root.event_generate("<<RadioChanged>>")   # Radio's page shows the stations as they are now
        except tk.TclError:
            pass
        pending = getattr(self, "_radio_pending", None)
        if pending is not None:   # Re-analyse or a new count, asked for while the build ran
            self.after(100, lambda: self.on_radio_analyse(pending))
        if (getattr(self, "_job_origin", None) is None and not getattr(self, "_job_review", False)
                and engine.SENT_ANY and engine.LAST_OUTPUT_ID and engine.LAST_OUTPUT not in ("YouTube", "Tidal")):
            try:
                self._save_default = engine.save_name()
            except Exception:
                self._save_default = ""
            self._show_save(engine.LAST_OUTPUT_ID)
        if getattr(self, "_job_review", False) and getattr(self, "_job_cancelled", False):
            self._job_review = False   # cancelled: the Review list is dropped
        if getattr(self, "_job_review", False):   # a Review build: its tracks go to the Review list
            self._job_review = False
            self.review_panel.load(getattr(engine, "REVIEW_ROWS", []), self._review_title(),
                                   engine.REVIEW_ZONE, top_up=getattr(self, "_job_top_up", False))

    def _review_title(self):
        """The build's first line, without its time or the settings in brackets after it."""
        for line in self._live:
            if line.strip() and not line.startswith((" ", "\n")):
                return re.sub(r"^\d\d:\d\d  ", "", line.strip()).split("  (")[0]
        return "Review"

    # The standard button of each kind, for Enter on the Search tab and callers from before buttons
    def on_similar(self):
        button = self._standard_button("artists")
        if button:
            self.on_button(button)

    def on_similar_tracks(self):
        button = self._standard_button("tracks")
        if button:
            self.on_button(button)

    def on_top_tracks(self):
        button = self._standard_button("top")
        if button:
            self.on_button(button)

    def _run_typed(self, build, seed, again, top_up=False):
        """
        A build from a typed seed. Afterwards, if the artist isn't in the library but one close to it
        is ('eleven finger' for Finger Eleven), the console offers it: a click types it in and runs
        the same build again.
        """
        self._suggestion = None

        def target():
            build(report=self.report, seed_info=seed)
            try:
                artist = library.suggest_artist(seed["Artist"])
            except Exception:
                artist = None
            if artist:
                self._suggestion = (seed["Artist"], artist, again)
        self._run_job(target, needs_playing=False, review=True, top_up=top_up)

    def _append_suggestion(self):
        """'No "eleven finger" in your library. Did you mean Finger Eleven?', the question a link."""
        typed, artist, again = self._suggestion
        self._suggestion = None
        lead = t('No "{typed}" in your library.', typed=typed)
        ask = t("Did you mean {artist}?", artist=artist)
        self._live.append(lead + " " + ask)
        if not self._live_visible():
            return
        self.log.config(state="normal")
        self.log.insert("end", lead + " ", ("note",))
        self.log.tag_configure("suggest", foreground=tabs.MATRIX_FG, underline=True)
        self.log.tag_bind("suggest", "<Button-1>", lambda e: self._take_suggestion(artist, again))
        self.log.tag_bind("suggest", "<Enter>", lambda e: self.log.config(cursor="hand2"))
        self.log.tag_bind("suggest", "<Leave>", lambda e: self.log.config(cursor=""))
        self.log.insert("end", ask, ("suggest",))
        self.log.insert("end", "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _take_suggestion(self, artist, again):
        """Types the suggested artist into Search and runs the same build again."""
        if self.running:
            return
        self.log.config(cursor="")
        self.search_artist.delete(0, "end")
        self.search_artist.insert(0, artist)
        self.seed_nb.select(self.search_tab)
        again()

    def _seeded(self, build, **options):
        """Seeds from the Now Playing zone's track, or the last track played when its Playing Now is empty."""
        seed = engine.seed_or_last_played(engine.seed_zone(), self.report)
        if seed:
            build(report=self.report, seed_info=seed, **options)

    def on_credits(self):
        self._run_job(lambda: engine.explore_credits(report=self.report))

    def on_vibe(self, button=None, top_up=False):
        problem = engine.vibe_blocker()
        if problem:
            self.report(problem)
            return
        button = button or self._standard_button("vibe")
        if button is None:
            return
        AIPlaylistDialog(self.root, play=self, on_create=lambda theme, count, if_short: self._run_job(
            lambda: buttons.run(button, theme=theme, count=count, if_short=if_short, report=self.report),
            needs_playing=False, review=True, top_up=top_up), on_steer=lambda spec: self._run_job(
            lambda: engine.steer_playlist(engine.steer_seed_pairs(all_tracks=spec["seed_kind"] == "all"),
                                          spec["directions"], spec["own_words"], spec["strength"], spec["tone"],
                                          spec["count"], report=self.report, if_short=spec["if_short"]),
            needs_playing=False, review=True, top_up=top_up))


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


# --- tray: a maximised window comes back maximised ---
# Tk's deiconify shows a window at its normal size on Windows, so going to the tray
# and back lost the maximised state. The state is noted on the way out and put back.

def hide_to_tray(root, memo):
    state = root.state()
    if state != "iconic":   # minimised to the taskbar: keep what was noted before
        memo["zoomed"] = state == "zoomed"
    root.withdraw()


def show_from_tray(root, memo):
    if memo.get("zoomed"):
        root.state("zoomed")
        if root.state() != "zoomed":   # not shown by that: show it, then maximise
            root.deiconify()
            root.state("zoomed")
    else:
        root.deiconify()
    root.lift()
    root.focus_force()


# --- a maximised window opens maximised next time ---
# The maximised state is saved to .env (WINDOW_MAXIMISED) whenever it changes, not on
# the way out, so it holds however 24bit7 ends: Quit, the tray, a restart or Windows
# shutting down. Hidden and minimised states leave the last one noted alone.

def note_window_state(root, memo, save):
    state = root.state()
    if state not in ("zoomed", "normal"):
        return
    zoomed = state == "zoomed"
    if memo.get("zoomed") != zoomed:
        memo["zoomed"] = zoomed
        save(zoomed)


def window_title():
    """The taskbar's and Alt+Tab's name for the window: '24bit7 Dev' for a dev copy (Ben, 11 Nov 2026)."""
    return f"24bit7{' Dev' if engine.dev_copy() else ''}  v{engine.VERSION}"


def main():
    _enable_dpi_awareness()
    _set_app_id()
    closed_other = _close_other_copy()
    loaded_profile = profiles.apply_pending()   # a profile chosen with Load, before anything reads a setting
    i18n.set_language(engine.UI_LANGUAGE)       # once, before any screen is built: switching restarts the app
    root = tk.Tk()
    root.withdraw()   # built out of sight and shown once it's ready, so it doesn't flash up small first
    _set_window_icon(root)
    apply_theme(root, engine.THEME, engine.ACCENT_COLOUR)   # before any widgets, so they all pick it up
    root.title(window_title())
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
    play.settings = settings   # the Play tab shows AI usage in step with Settings > Keys
    settings.play = play       # Settings > Keys > Use AI greys the Play tab's AI pieces out or back in
    if loaded_profile:
        root.after(800, lambda: print(t('Profile "{loaded_profile}" loaded.', loaded_profile=loaded_profile)))
    nb.add(play, text=t("Play"))
    nb.add(discover, text=t("Discover"))
    nb.add(settings, text=t("Settings"))

    # Support link: top right of the tab row, so it shows from every tab. It opens the
    # Support window (support_gui.py). It is hidden if the window is too narrow for it
    # to sit clear of the tab buttons.
    donate = tk.Label(root, text=t("Support"), font=("Segoe UI", 9, "underline"),
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
            root.after(13000, lambda e=e: play.report(t("Note: the built-in title bar couldn't be set up ({e}), so the Windows one is used.", e=e)))

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
        root.after(400, lambda: messagebox.showinfo(t("Welcome to 24bit7"), t(WELCOME_TEXT), parent=root))

    library.start()   # the whole library in memory: Similar Tracks and voice match against it
    voice.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)),
                 lambda: play.running or not play.voice_jobs.empty())
    voice.attach_badge(lambda asked, said: play.badge_problems.put((asked, said)))
    # "multiroom" and "single room" by voice start and stop the follower (stage two, 9 Nov 2026)
    voice.attach_multiroom(start=lambda: play.multiroom.start(engine.multiroom_settings()),
                           stop=play.multiroom.stop, running=play.multiroom.running,
                           leave=play.multiroom.leave, following=lambda: play.multiroom.wanted)
    voice.restart()
    # Keyboard shortcuts (Settings > Other): queued on the Play tab like voice commands
    hotkeys.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)),
                   busy=lambda: play.running or not play.voice_jobs.empty(), note=play.report)
    problems = hotkeys.restart()
    # Non-stop (Settings > Playlist): tops up 24bit7 playlists as they reach their last track
    nonstop.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)))
    nonstop.start()
    root.after(1500, play._sync_multiroom)   # Output left on Multiroom: the Speakers follow from the start
    settings.refresh_hotkey_notes(problems)
    if problems:
        names = ", ".join(hotkeys.shown(c) for c in problems)
        root.after(13000, lambda: play.report(t("Some keyboard shortcuts didn't register ({names}). See Settings > Other > Keyboard Shortcuts.", names=names)))
    if closed_other:
        root.after(13000, lambda: play.report(t("Closed the copy of 24bit7 that was already running.")))

    # --- tray: Start in the tray (when Windows launches it) and Close to tray ---
    # whether the window was maximised when it went to the tray, or when 24bit7 last closed
    tray_memo = {"zoomed": read_env().get("WINDOW_MAXIMISED", "0").strip() == "1"}

    def save_maximised(zoomed):
        try:
            write_env({"WINDOW_MAXIMISED": "1" if zoomed else "0"})
        except OSError:
            pass

    def on_window_configure(event):
        if event.widget is root:
            note_window_state(root, tray_memo, save_maximised)
    root.bind("<Configure>", on_window_configure, add="+")

    def show_window():
        show_from_tray(root, tray_memo)

    def quit_app():
        tray.stop()
        voice.stop()
        hotkeys.stop()
        nonstop.stop()
        play.multiroom.stop()   # the Speakers stop with the app; the Sonos carries on if JRiver is playing to it
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
            hide_to_tray(root, tray_memo)   # still running: voice keeps listening
        else:
            quit_app()

    root.protocol("WM_DELETE_WINDOW", on_close)
    hidden = False
    if engine.CLOSE_TO_TRAY or (tray.started_by_windows() and engine.START_IN_TRAY):
        if tray.start(root, show_window, quit_app) and tray.started_by_windows() and engine.START_IN_TRAY:
            hidden = True   # started by Windows into the tray: stays out of sight
    if not hidden:
        show_from_tray(root, tray_memo)   # maximised again if it was last time

    root.mainloop()
    if restart["on"]:
        import subprocess
        frozen = getattr(sys, "frozen", False)   # the built .exe is its own program
        subprocess.Popen([sys.executable] + (sys.argv[1:] if frozen else sys.argv), cwd=engine.APP_DIR)


if __name__ == "__main__":
    main()
