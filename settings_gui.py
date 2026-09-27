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
from tkinter import ttk, messagebox

import engine
import tray
import voice
from tabs import TabbedPane

ENV_FILE = engine.ENV_FILE   # single source of truth for where .env lives

# Listed alphabetically by display name
SOURCE_NAMES = [("ai", "AI"), ("deezer", "Deezer"),
                ("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"),
                ("youtube", "YouTube")]
# YouTube suggests artists only, so it isn't offered as a top-track source
TOP_SOURCE_NAMES = [s for s in SOURCE_NAMES if s[0] != "youtube"]
# Sources that can suggest tracks like a track
TRACK_SOURCE_NAMES = [("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"), ("youtube", "YouTube")]


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
        tk.Label(self.tip, text=self.text, bg="#ffffe0", relief="solid", borderwidth=1, justify="left",
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
    mark = tk.Label(parent, text="?", font=("Segoe UI", 8, "bold"), fg="white", bg=HELP_MARK_BG,
                    width=2, cursor="question_arrow")
    Tooltip(mark, text)
    return mark


def section(parent, title, help_text=None, row=None):
    """
    A boxed section: a thin rectangle with its title (and optional ?) on the top
    edge. Returns the box to build the section's controls in. Stacked with grid
    in column 0 of parent, one under another, or at row if given.
    """
    box = tk.LabelFrame(parent, bd=0, padx=14, pady=10, highlightthickness=1,
                        highlightbackground=SECTION_EDGE, highlightcolor=SECTION_EDGE)
    head = tk.Frame(box)
    tk.Label(head, text=title, font=HEADING_FONT, fg=SECTION_FG).pack(side="left")
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


class SettingsTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.env = read_env()
        self.vars = {}
        self._loading = True   # suppress auto-save while building controls

        nb = TabbedPane(self, font=("Segoe UI", 10, "bold"), pad=(16, 6))
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_sources(nb)
        self._build_playlist(nb)
        self._build_search_sites(nb)
        self._build_keys(nb)
        self._build_other(nb)
        self._build_voice(nb)

        self._loading = False
        self._refresh_key_marks()

    # --- persistence -------------------------------------------------------

    def _current_updates(self):
        updates = {}
        for group in ("SIMILAR_SOURCES", "TOP_TRACK_SOURCES", "SIMILAR_TRACK_SOURCES"):
            chosen = [code for code, v in self.vars[group].items() if v.get()]
            updates[group] = ",".join(chosen)
        for key in ["LISTENBRAINZ_ALGORITHM", "LISTENBRAINZ_TRACK_ALGORITHM", "SIMILAR_ARTIST_LIMIT", "TRACKS_PER_ARTIST_POOL",
                    "TRACKS_PER_ARTIST_PICK", "TOP_TRACKS_COUNT", "VIBE_TRACK_COUNT", "TOP_TRACKS_ORDER",
                    "CACHE_DAYS", "JRIVER_HOST", "YOUTUBE_PLAYLIST_LENGTH",
                    "SIMILAR_TRACK_COUNT", "SIMILAR_TRACK_PER_ARTIST", "SIMILAR_TRACK_ORDER",
                    "LONG_CLOSER_MINUTES", "SIMILAR_ARTIST_TRACK_COUNT"] + KEY_FIELDS:
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
        updates["DEBUG"] = "1" if self.vars["DEBUG"].get() else "0"
        agree = self.vars["SIMILAR_MIN_AGREEMENT"].get()
        updates["SIMILAR_MIN_AGREEMENT"] = "1" if agree == "Off" else agree
        updates["SIMILAR_REQUIRE_AGREEMENT"] = None   # old on/off key, superseded
        agree = self.vars["SIMILAR_TRACK_MIN_AGREEMENT"].get()
        updates["SIMILAR_TRACK_MIN_AGREEMENT"] = "1" if agree == "Off" else agree
        for group, (on, using, rounds, _) in self._drift.items():
            name = f"DRIFT_{group.upper()}"
            updates[name] = "1" if on.get() else "0"
            updates[f"{name}_USING"] = "tracks" if using.get() == "Similar tracks" else "artists"
            updates[f"{name}_ROUNDS"] = rounds.get()
        updates["SIMILAR_TRACK_TOPUP"] = None   # replaced by Drift in 1.4.0
        updates["SKIP_LONG_CLOSERS"] = "1" if self.vars["SKIP_LONG_CLOSERS"].get() else "0"
        for key in ("START_IN_TRAY", "CLOSE_TO_TRAY"):
            updates[key] = "1" if self.vars[key].get() else "0"
        return updates

    def _refresh_key_marks(self):
        """Adds '(no key yet)' after a source whose key field is empty, and clears it once filled."""
        for box, code, label, purpose in getattr(self, "_source_boxes", []):
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
        if self._loading:
            return
        self._refresh_key_marks()
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

    def _line(self, box, r, label=None, pady=(4, 4)):
        """A row inside a section: an optional bold label, then whatever is packed into the frame returned."""
        row = tk.Frame(box)
        row.grid(row=r, column=0, columnspan=6, sticky="w", pady=pady)
        if label:
            tk.Label(row, text=label, font=LABEL_FONT).pack(side="left", padx=(0, 10))
        return row

    def _listenbrainz_row(self, box, r, key, notes):
        """The ListenBrainz algorithm dropdown for one section, with its notes behind a ?."""
        row = self._line(box, r, "ListenBrainz algorithm", pady=(10, 0))
        self.vars[key] = tk.StringVar(value=self.env.get(key, "alltime"))
        cb = ttk.Combobox(row, textvariable=self.vars[key], values=["alltime", "recent"],
                          state="readonly", width=10)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._save)
        help_mark(row, notes).pack(side="left", padx=(8, 0))
        return r + 1

    def _source_ticks(self, box, r, group, names, default, command, purpose, help_text=None):
        """One row of source tick boxes, with an optional ? at the end."""
        row = self._line(box, r)
        chosen = self._csv_list(group, default)
        self.vars[group] = {}
        for code, label in names:
            v = tk.BooleanVar(value=code in chosen)
            self.vars[group][code] = v
            tick = ttk.Checkbutton(row, text=label, variable=v, command=command, style="Big.TCheckbutton")
            tick.pack(side="left", padx=(0, 14))
            self.__dict__.setdefault("_source_boxes", []).append((tick, code, label, purpose))
        if help_text:
            help_mark(row, help_text).pack(side="left", padx=(2, 0))
        return r + 1

    def _build_sources(self, nb):
        tab = self._scroll_tab(nb, "Sources")
        ttk.Style(self).configure("Big.TCheckbutton", font=("Segoe UI", 11))

        # --- Similar Artists ---
        box = section(tab, "Similar Artists")
        r = self._source_ticks(box, 0, "SIMILAR_SOURCES", SOURCE_NAMES, "lastfm", self._similar_sources_changed,
                               "similar",
                               "YouTube suggests from the playing track, using YouTube Music's up next queue. "
                               "No key needed. Ticked on its own, it plays YouTube's queue as is, matched against "
                               "your library. Ticked with other sources, its artists join the blend. It's an "
                               "unofficial route, so it may break now and then.")
        # How many sources must agree. Replaced the old on/off tick box; an old
        # on/off setting carries over (on -> 2, off -> Off).
        legacy_on = self.env.get("SIMILAR_REQUIRE_AGREEMENT", "1") in ("1", "true", "yes")
        start = self.env.get("SIMILAR_MIN_AGREEMENT", "").strip() or ("2" if legacy_on else "1")
        self.vars["SIMILAR_MIN_AGREEMENT"] = tk.StringVar(value="Off" if start in ("0", "1") else start)
        row = self._line(box, r, "Sources that must agree", pady=(10, 0))
        self._agree_cb = ttk.Combobox(row, textvariable=self.vars["SIMILAR_MIN_AGREEMENT"],
                                      state="readonly", width=6)
        self._agree_cb.pack(side="left")
        self._agree_cb.bind("<<ComboboxSelected>>", self._save)
        help_mark(row, "How many sources must agree before an artist is picked. Higher means a smoother "
                       "playlist with fewer wildcards, but less chance of discovering something new. "
                       "Tip: try single sources on their own before blending.").pack(side="left", padx=(8, 0))
        self._sync_agreement_options()
        r += 1
        self._listenbrainz_row(box, r, "LISTENBRAINZ_ALGORITHM",
                               "alltime: from all listening history; leans toward well-known artists.\n"
                               "recent: what people are playing alongside this artist right now.")

        # --- Similar Tracks: its own sources and agreement ---
        box = section(tab, "Similar Tracks")
        r = self._source_ticks(box, 0, "SIMILAR_TRACK_SOURCES", TRACK_SOURCE_NAMES, "lastfm,listenbrainz,youtube",
                               self._track_sources_changed, "similar",
                               "Tracks like the seed track, for the Similar Tracks button. No key needed for "
                               "ListenBrainz or YouTube.")
        start = self.env.get("SIMILAR_TRACK_MIN_AGREEMENT", "2").strip() or "2"
        self.vars["SIMILAR_TRACK_MIN_AGREEMENT"] = tk.StringVar(value="Off" if start in ("0", "1") else start)
        row = self._line(box, r, "Sources that must agree", pady=(10, 0))
        self._track_agree_cb = ttk.Combobox(row, textvariable=self.vars["SIMILAR_TRACK_MIN_AGREEMENT"],
                                            state="readonly", width=6)
        self._track_agree_cb.pack(side="left")
        self._track_agree_cb.bind("<<ComboboxSelected>>", self._save)
        help_mark(row, "How many sources must agree on a track before it's used. If too few agreed tracks "
                       "are in your library, the agreement is relaxed a step at a time, and the log says so."
                  ).pack(side="left", padx=(8, 0))
        self._sync_track_agreement_options()
        r += 1
        self._listenbrainz_row(box, r, "LISTENBRAINZ_TRACK_ALGORITHM",
                               "alltime: from all listening history.\n"
                               "recent: roughly the last six months; older songs may find fewer matches.")

        # --- Artist's Top Tracks ---
        box = section(tab, "Artist's Top Tracks")
        self._source_ticks(box, 0, "TOP_TRACK_SOURCES", TOP_SOURCE_NAMES, "lastfm", self._save, "top",
                           "More services means richer, more varied playlists, but slower; fewer is quicker. "
                           "ListenBrainz is the slowest source on a first run, because its lookups are limited "
                           "to one a second. Repeat runs are quick.")

    def _track_sources_changed(self):
        self._sync_track_agreement_options()
        self._save()

    def _sync_track_agreement_options(self):
        """Off, 2 ... the number of ticked Similar Tracks sources; greyed out below two."""
        ticked = sum(1 for v in self.vars["SIMILAR_TRACK_SOURCES"].values() if v.get())
        if ticked < 2:
            self._track_agree_cb.config(state="disabled")
            return
        options = ["Off"] + [str(n) for n in range(2, ticked + 1)]
        self._track_agree_cb.config(values=options, state="readonly")
        if self.vars["SIMILAR_TRACK_MIN_AGREEMENT"].get() not in options:
            self.vars["SIMILAR_TRACK_MIN_AGREEMENT"].set(options[-1])

    def _similar_sources_changed(self):
        self._sync_agreement_options()
        self._save()

    def _sync_agreement_options(self):
        # The agreement dropdown offers Off, 2 ... N, where N is the number of
        # ticked similar-artist sources, and a value above N is brought down to N.
        # With fewer than two sources ticked the setting doesn't apply, so the
        # dropdown is greyed out and the value is kept for when sources return.
        ticked = sum(1 for v in self.vars["SIMILAR_SOURCES"].values() if v.get())
        if ticked < 2:
            self._agree_cb.config(state="disabled")
            return
        options = ["Off"] + [str(n) for n in range(2, min(ticked, 5) + 1)]
        self._agree_cb.config(values=options, state="readonly")
        if self.vars["SIMILAR_MIN_AGREEMENT"].get() not in options:
            self.vars["SIMILAR_MIN_AGREEMENT"].set(options[-1])

    def _build_playlist(self, nb):
        """
        Playlist settings grouped under the Play-tab mode each one belongs to,
        one boxed section per mode, so the labels don't need to repeat the mode name.
        """
        tab = self._scroll_tab(nb, "Playlist")
        self._drift = {}   # group -> (on, using, rounds, (dropdowns))
        where = {}         # the box being filled and its next row

        def begin(title, help_text=None):
            where["box"], where["r"] = section(tab, title, help_text), 0

        def place(widget, help_text=None, pady=4):
            """Puts a label-less row (a tick box and friends) across the box."""
            widget.grid(row=where["r"], column=0, columnspan=3, sticky="w", pady=pady)
            where["r"] += 1

        def spin(label, key, default, lo, hi, help_text=None):
            box, r = where["box"], where["r"]
            tk.Label(box, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=self.env.get(key, default))
            self.vars[key] = var
            cell = tk.Frame(box)   # the control with its ? right beside it
            cell.grid(row=r, column=1, sticky="w", padx=(12, 0))
            sb = tk.Spinbox(cell, from_=lo, to=hi, textvariable=var, width=6, command=self._save)
            sb.pack(side="left")
            if help_text:
                help_mark(cell, help_text).pack(side="left", padx=(8, 0))
            var.trace_add("write", self._save)
            where["r"] += 1
            return var, sb

        def choice(label, key, default, values, help_text=None):
            box, r = where["box"], where["r"]
            tk.Label(box, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
            self.vars[key] = tk.StringVar(value=self.env.get(key, default))
            cell = tk.Frame(box)
            cell.grid(row=r, column=1, sticky="w", padx=(12, 0))
            cb = ttk.Combobox(cell, textvariable=self.vars[key], values=values, state="readonly", width=12)
            cb.pack(side="left")
            cb.bind("<<ComboboxSelected>>", self._save)
            if help_text:
                help_mark(cell, help_text).pack(side="left", padx=(8, 0))
            where["r"] += 1

        def drift(group):
            """The Drift tick box and its ?, then Drift using and Rounds."""
            box = where["box"]
            cfg = engine.DRIFT[group]
            on = tk.BooleanVar(value=cfg["on"])
            using = tk.StringVar(value="Similar tracks" if cfg["using"] == "tracks" else "Similar artists")
            rounds = tk.StringVar(value=str(cfg["rounds"]))
            head = tk.Frame(box)
            ttk.Checkbutton(head, text="Drift", variable=on, command=self._drift_toggled).pack(side="left")
            help_mark(head, "If a playlist comes up short, search again using what's already been found, "
                            "until the playlist reaches its length. More rounds fill more gaps but can wander "
                            "further from where you started.").pack(side="left", padx=(8, 0))
            place(head, pady=(10, 2))
            row = tk.Frame(box)
            tk.Label(row, text="Drift using").pack(side="left")
            using_cb = ttk.Combobox(row, textvariable=using, values=["Similar tracks", "Similar artists"],
                                    state="readonly", width=14)
            using_cb.pack(side="left", padx=(6, 18))
            tk.Label(row, text="Rounds").pack(side="left")
            rounds_cb = ttk.Combobox(row, textvariable=rounds, values=[str(n) for n in range(1, 7)],
                                     state="readonly", width=3)
            rounds_cb.pack(side="left", padx=(6, 0))
            for cb in (using_cb, rounds_cb):
                cb.bind("<<ComboboxSelected>>", self._save)
            place(row, pady=(0, 4))
            self._drift[group] = (on, using, rounds, (using_cb, rounds_cb))

        # --- Similar Artists ---
        begin("Similar Artists")
        spin("Number of tracks", "SIMILAR_ARTIST_TRACK_COUNT", "30", 5, 100)
        spin("Number of artists", "SIMILAR_ARTIST_LIMIT", "20", 1, 50)
        pool_var, _ = spin("Number of artist's top tracks", "TRACKS_PER_ARTIST_POOL", "5", 1, 20)
        pick_var, pick_sb = spin("Tracks per artist selection", "TRACKS_PER_ARTIST_PICK", "3", 1, 20,
                                 "Top tracks come from your Top-track sources (Last.fm, Deezer and so on), for "
                                 "the seed artist and each similar artist. Selecting fewer than the top tracks "
                                 "(say 3 of 5) means the same seed gives a different playlist each run, as the "
                                 "selection is random.")
        self._pick_sb = pick_sb
        pool_var.trace_add("write", lambda *a: self._sync_pick_limit())
        self._sync_pick_limit()
        drift("artists")

        # --- Similar Tracks ---
        begin("Similar Tracks")
        spin("Number of tracks", "SIMILAR_TRACK_COUNT", "30", 5, 100)
        spin("Most tracks per artist", "SIMILAR_TRACK_PER_ARTIST", "3", 1, 20,
             "Includes the seed artist.")
        choice("Order", "SIMILAR_TRACK_ORDER", "shuffled", ["shuffled", "similar first"],
               "Similar first keeps the order the sources agreed on, strongest matches first. "
               "Shuffled mixes them up.")
        drift("tracks")

        # --- Artist's Top Tracks ---
        begin("Artist's Top Tracks")
        spin("Number of tracks (1-20)", "TOP_TRACKS_COUNT", "10", 1, 20)
        choice("Order", "TOP_TRACKS_ORDER", "popular", ["popular", "reverse", "random"],
               "popular: most played first\nreverse: least played first\nrandom: shuffled")

        # --- Vibe Playlist ---
        begin("Vibe Playlist")
        spin("Number of tracks", "VIBE_TRACK_COUNT", "20", 5, 100)
        drift("vibe")
        self._sync_drift()

        # --- Hidden Tracks ---
        begin("Hidden Tracks")
        row = tk.Frame(where["box"])
        self.vars["SKIP_LONG_CLOSERS"] = tk.BooleanVar(value=self.env.get("SKIP_LONG_CLOSERS", "1") == "1")
        self.vars["LONG_CLOSER_MINUTES"] = tk.StringVar(value=self.env.get("LONG_CLOSER_MINUTES", "6"))
        self._closer_sb = tk.Spinbox(row, from_=3, to=30, textvariable=self.vars["LONG_CLOSER_MINUTES"],
                                     width=4, command=self._save)
        ttk.Checkbutton(row, text="Skip the last track on an album if it's longer than",
                        variable=self.vars["SKIP_LONG_CLOSERS"],
                        command=self._long_closers_toggled).pack(side="left")
        self._closer_sb.pack(side="left", padx=(6, 6))
        tk.Label(row, text="minutes").pack(side="left")
        help_mark(row, "Long album closers often hide a bonus track after a long silence. This applies to "
                       "every playlist 24bit7 builds. Albums, songs and playlists you ask for by name always "
                       "play in full.").pack(side="left", padx=(8, 0))
        self.vars["LONG_CLOSER_MINUTES"].trace_add("write", self._save)
        place(row)
        self._sync_long_closers()

    def _drift_toggled(self):
        self._sync_drift()
        self._save()

    def _sync_drift(self):
        """Drift using and Rounds grey out while their Drift tick is off."""
        for on, _, _, boxes in self._drift.values():
            for cb in boxes:
                cb.config(state="readonly" if on.get() else "disabled")

    def _long_closers_toggled(self):
        self._sync_long_closers()
        self._save()

    def _sync_long_closers(self):
        """The minutes box greys out while the tick is off."""
        self._closer_sb.config(state="normal" if self.vars["SKIP_LONG_CLOSERS"].get() else "disabled")

    def _sync_pick_limit(self):
        """
        Keeps 'tracks per artist selection' from exceeding 'library tracks per
        artist to consider': the selection spinner's ceiling follows the
        consider value, and the selection is clamped down if consider drops
        below it. Ignores half-typed (non-numeric) values.
        """
        try:
            pool = int(self.vars["TRACKS_PER_ARTIST_POOL"].get())
        except (ValueError, KeyError):
            return
        pool = max(1, pool)
        self._pick_sb.config(to=pool)
        try:
            pick = int(self.vars["TRACKS_PER_ARTIST_PICK"].get())
        except ValueError:
            return
        if pick > pool:
            self.vars["TRACKS_PER_ARTIST_PICK"].set(str(pool))   # trace on this var saves

    def _build_keys(self, nb):
        tab = self._scroll_tab(nb, "Keys")
        box = section(tab, "Keys and passwords")
        for r, key in enumerate(KEY_FIELDS):
            tk.Label(box, text=key, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
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
        tk.Checkbutton(parent, text="Show", variable=show, command=toggle).grid(
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

        self.vars["DEBUG"] = tk.BooleanVar(value=self.env.get("DEBUG", "0") in ("1", "true", "yes"))
        tk.Checkbutton(box, text="Debug (log raw source lists to console)",
                       variable=self.vars["DEBUG"], command=self._save).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

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
                     fg=HELP_FG, font=HELP_FONT).grid(row=0, column=0, sticky="w")
            return
        tk.Label(self.zone_frame, text="Show", fg=HELP_FG, font=HELP_FONT).grid(row=0, column=0, sticky="w")
        tk.Label(self.zone_frame, text="Default", fg=HELP_FG, font=HELP_FONT).grid(
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
                tk.Label(self.zone_frame, text=f"{name} (not found)", fg=HELP_FG).grid(row=r, column=0, sticky="w")
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
        self.voice_status = tk.Label(box, text=voice.status(), fg=HELP_FG, font=HELP_FONT)
        self.voice_status.grid(row=1, column=0, columnspan=5, sticky="w")

        tk.Label(box, text="Key", anchor="w").grid(row=2, column=0, sticky="w", pady=(12, 2))
        self.voice_key_var = tk.StringVar(value=engine.VOICE_KEY)
        key_box = tk.Frame(box)   # hidden like the other keys; Show is unticked every time Settings opens
        key_box.grid(row=2, column=1, sticky="w", padx=(12, 8), pady=(12, 2))
        key_entry = tk.Entry(key_box, textvariable=self.voice_key_var, width=40, state="readonly",
                             show="\u2022")
        key_entry.pack(side="left")
        show_key = tk.BooleanVar(value=False)
        tk.Checkbutton(key_box, text="Show", variable=show_key,
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
                      "Say a command on a device that isn't set up and it appears here. "
                      "Pick the zone it plays to.")
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
        self.voice_test_result = tk.Label(box, text="", fg=HELP_FG, font=HELP_FONT, justify="left")
        self.voice_test_result.grid(row=1, column=0, sticky="w", pady=(6, 0))

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
            tk.Label(self.voice_dev_frame, text="No devices heard yet.", fg=HELP_FG, font=HELP_FONT).grid(
                row=0, column=0, sticky="w")
            return
        zones = engine.zone_names()
        has_key = bool(engine.ANTHROPIC_API_KEY)
        for c, heading in enumerate(("Name", "Zone", "AI Moderator", "Last heard")):
            tk.Label(self.voice_dev_frame, text=heading, fg=HELP_FG, font=HELP_FONT).grid(
                row=0, column=c, sticky="w", padx=(0, 12))
        for r, (device_id, name, zone, heard, moderator) in enumerate(rows, start=1):
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
            mod_var = tk.BooleanVar(value=bool(moderator) and has_key)
            mod_box = ttk.Checkbutton(self.voice_dev_frame, variable=mod_var,
                                      state="normal" if has_key else "disabled",
                                      command=lambda d=device_id, v=mod_var: self._voice_moderator(d, v))
            mod_box.grid(row=r, column=2, sticky="w", padx=(0, 12))
            Tooltip(mod_box, NO_KEY_TEXT, when=lambda: not engine.ANTHROPIC_API_KEY)
            tk.Label(self.voice_dev_frame, text=heard or "").grid(row=r, column=3, sticky="w", padx=(0, 12))
            tk.Button(self.voice_dev_frame, text="Remove", width=8,
                      command=lambda d=device_id: (voice.remove_device(d), self._fill_voice_devices())).grid(
                row=r, column=4, sticky="w", pady=2)

    def _voice_moderator(self, device_id, var):
        if var.get():
            warn_moderator_once(self)
        voice.update_device(device_id, moderator=var.get())

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
            tk.Label(box, text=heading, fg=HELP_FG, font=HELP_FONT).grid(
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