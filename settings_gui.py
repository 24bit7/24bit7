"""
24bit7 - Settings tab.

A frame (embedded in the main window's notebook) that reads current values from
.env, presents them as sub-tabbed controls, and auto-saves changes back to .env
whenever a control changes. Comments, blank lines and unmanaged keys are
preserved; only managed keys are updated or appended. Text fields save when
focus leaves them (so half-typed keys aren't written); checkboxes and dropdowns
save immediately. The engine picks up the file via its .env mod-time check.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import engine
import voice
from tabs import TabbedPane

ENV_FILE = engine.ENV_FILE   # single source of truth for where .env lives

# Listed alphabetically by display name
SOURCE_NAMES = [("ai", "AI"), ("deezer", "Deezer"),
                ("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"),
                ("youtube", "YouTube")]
# YouTube suggests artists only, so it isn't offered as a top-track source
TOP_SOURCE_NAMES = [s for s in SOURCE_NAMES if s[0] != "youtube"]


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

HEADING_FONT = ("Segoe UI", 10, "bold")
HELP_FONT = ("Segoe UI", 8)
HELP_FG = "#666"


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
        for group in ("SIMILAR_SOURCES", "TOP_TRACK_SOURCES"):
            chosen = [code for code, v in self.vars[group].items() if v.get()]
            updates[group] = ",".join(chosen)
        for key in ["LISTENBRAINZ_ALGORITHM", "SIMILAR_ARTIST_LIMIT", "TRACKS_PER_ARTIST_POOL",
                    "TRACKS_PER_ARTIST_PICK", "TOP_TRACKS_COUNT", "VIBE_TRACK_COUNT", "TOP_TRACKS_ORDER",
                    "CACHE_DAYS", "JRIVER_HOST", "YOUTUBE_PLAYLIST_LENGTH"] + KEY_FIELDS:
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
        if not updates["SIMILAR_SOURCES"] or not updates["TOP_TRACK_SOURCES"] or not updates["DIGITAL_STORES"]:
            return   # don't persist a no-sources / no-stores state; user is mid-change
        try:
            write_env(updates)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)

    # --- tabs --------------------------------------------------------------

    def _build_sources(self, nb):
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Sources")
        ttk.Style(self).configure("Big.TCheckbutton", font=("Segoe UI", 11))
        r = 0

        tk.Label(tab, text="Similar-artist sources", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=4, sticky="w")
        r += 1
        chosen_sim = self._csv_list("SIMILAR_SOURCES", "lastfm")
        self.vars["SIMILAR_SOURCES"] = {}
        for i, (code, label) in enumerate(SOURCE_NAMES):
            v = tk.BooleanVar(value=code in chosen_sim)
            self.vars["SIMILAR_SOURCES"][code] = v
            box = ttk.Checkbutton(tab, text=label, variable=v, command=self._similar_sources_changed,
                                  style="Big.TCheckbutton")
            box.grid(row=r, column=i, sticky="w", padx=(0, 12))
            self.__dict__.setdefault("_source_boxes", []).append((box, code, label, "similar"))
        r += 1

        tk.Label(tab, text="YouTube suggests from the playing track, using YouTube Music's up next queue. No key needed.\n"
                           "Ticked on its own, it plays YouTube's queue as is, matched against your library.\n"
                           "Ticked with other sources, its artists join the blend.\n"
                           "It's an unofficial route, so it may break now and then.",
                 fg="#666", font=("Segoe UI", 8), justify="left").grid(
            row=r, column=0, columnspan=5, sticky="w", pady=(2, 0))
        r += 1

        # How many sources must agree. Replaced the old on/off tick box; an old
        # on/off setting carries over (on -> 2, off -> Off).
        legacy_on = self.env.get("SIMILAR_REQUIRE_AGREEMENT", "1") in ("1", "true", "yes")
        start = self.env.get("SIMILAR_MIN_AGREEMENT", "").strip() or ("2" if legacy_on else "1")
        self.vars["SIMILAR_MIN_AGREEMENT"] = tk.StringVar(value="Off" if start in ("0", "1") else start)
        agree_row = tk.Frame(tab)
        agree_row.grid(row=r, column=0, columnspan=5, sticky="w", pady=(10, 0))
        tk.Label(agree_row, text="Sources that must agree", font=("Segoe UI", 9, "bold")).pack(side="left")
        self._agree_cb = ttk.Combobox(agree_row, textvariable=self.vars["SIMILAR_MIN_AGREEMENT"],
                                      state="readonly", width=6)
        self._agree_cb.pack(side="left", padx=(10, 0))
        self._agree_cb.bind("<<ComboboxSelected>>", self._save)
        self._sync_agreement_options()
        r += 1
        tk.Label(tab, text="How many sources must agree before an artist is picked.\n"
                           "Higher means a smoother playlist with fewer wildcards, but less chance of\n"
                           "discovering something new.\n"
                           "Tip: try single sources on their own before blending.",
                 fg="#666", font=("Segoe UI", 8), justify="left").grid(
            row=r, column=0, columnspan=5, sticky="w", pady=(2, 0))
        r += 1

        tk.Label(tab, text="Top-track sources", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(16, 0))
        r += 1
        chosen_top = self._csv_list("TOP_TRACK_SOURCES", "lastfm")
        self.vars["TOP_TRACK_SOURCES"] = {}
        for i, (code, label) in enumerate(TOP_SOURCE_NAMES):
            v = tk.BooleanVar(value=code in chosen_top)
            self.vars["TOP_TRACK_SOURCES"][code] = v
            box = ttk.Checkbutton(tab, text=label, variable=v, command=self._save,
                                  style="Big.TCheckbutton")
            box.grid(row=r, column=i, sticky="w", padx=(0, 12))
            self.__dict__.setdefault("_source_boxes", []).append((box, code, label, "top"))
        r += 1

        tk.Label(tab, text="More services = richer, more varied playlists (slower).\n"
                          "Fewer = quicker.\n"
                          "ListenBrainz is the slowest source on a first run, because its lookups are limited\n"
                          "to one a second. Repeat runs are quick.",
                 fg="#666", font=("Segoe UI", 9), justify="left").grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(10, 0))
        r += 1

        tk.Label(tab, text="ListenBrainz algorithm", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(20, 0))
        r += 1
        self.vars["LISTENBRAINZ_ALGORITHM"] = tk.StringVar(
            value=self.env.get("LISTENBRAINZ_ALGORITHM", "alltime"))
        cb = ttk.Combobox(tab, textvariable=self.vars["LISTENBRAINZ_ALGORITHM"],
                          values=["alltime", "recent"], state="readonly", width=18)
        cb.grid(row=r, column=0, columnspan=2, sticky="w")
        cb.bind("<<ComboboxSelected>>", self._save)
        r += 1
        tk.Label(tab,
                 text="alltime - from all listening history; leans toward well-known artists.\n"
                      "recent - what people are playing alongside this artist right now.",
                 fg="#666", font=("Segoe UI", 8), justify="left").grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(4, 0))

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
        so the labels don't need to repeat the mode name.
        """
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Playlist")
        self._row = 0

        def heading(text, first=False):
            tk.Label(tab, text=text, font=HEADING_FONT, anchor="w").grid(
                row=self._row, column=0, columnspan=2, sticky="w", pady=(0 if first else 18, 4))
            self._row += 1

        def spin(label, key, default, lo, hi):
            tk.Label(tab, text=label, anchor="w").grid(row=self._row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=self.env.get(key, default))
            self.vars[key] = var
            sb = tk.Spinbox(tab, from_=lo, to=hi, textvariable=var, width=6, command=self._save)
            sb.grid(row=self._row, column=1, sticky="w", padx=(12, 0))
            var.trace_add("write", self._save)
            self._row += 1
            return var, sb

        def note(text):
            tk.Label(tab, text=text, fg=HELP_FG, font=HELP_FONT, justify="left").grid(
                row=self._row, column=0, columnspan=2, sticky="w", pady=(0, 4))
            self._row += 1

        # --- Similar Artists ---
        heading("Similar Artists", first=True)
        spin("Number of artists", "SIMILAR_ARTIST_LIMIT", "20", 1, 50)
        pool_var, _ = spin("Number of artist's top tracks", "TRACKS_PER_ARTIST_POOL", "5", 1, 20)
        pick_var, pick_sb = spin("Tracks per artist selection", "TRACKS_PER_ARTIST_PICK", "3", 1, 20)
        note("Top tracks come from your Top-track sources (Last.fm, Deezer etc.), for the seed\n"
             "artist and each similar artist. Selecting fewer than the top tracks (e.g. 3 of 5)\n"
             "means the same seed gives a different playlist each run, as the selection is random.")
        self._pick_sb = pick_sb
        pool_var.trace_add("write", lambda *a: self._sync_pick_limit())
        self._sync_pick_limit()

        # --- Artist's Top Tracks ---
        heading("Artist's Top Tracks")
        spin("Number of tracks (1-20)", "TOP_TRACKS_COUNT", "10", 1, 20)
        tk.Label(tab, text="Order", anchor="w").grid(row=self._row, column=0, sticky="w", pady=4)
        self.vars["TOP_TRACKS_ORDER"] = tk.StringVar(value=self.env.get("TOP_TRACKS_ORDER", "popular"))
        cb = ttk.Combobox(tab, textvariable=self.vars["TOP_TRACKS_ORDER"],
                          values=["popular", "reverse", "random"], state="readonly", width=12)
        cb.grid(row=self._row, column=1, sticky="w", padx=(12, 0))
        cb.bind("<<ComboboxSelected>>", self._save)
        self._row += 1
        bullet = "\u2022"
        note(f"{bullet}  popular - most played first\n"
             f"{bullet}  reverse - least played first\n"
             f"{bullet}  random - shuffled")

        # --- Vibe Playlist ---
        heading("Vibe Playlist")
        spin("Number of tracks", "VIBE_TRACK_COUNT", "20", 5, 100)

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
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Keys")
        for r, key in enumerate(KEY_FIELDS):
            tk.Label(tab, text=key, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=self.env.get(key, ""))
            self.vars[key] = var
            entry = tk.Entry(tab, textvariable=var, show="\u2022", width=32)
            entry.grid(row=r, column=1, padx=(8, 4))
            entry.bind("<FocusOut>", self._save)   # save when leaving the field
            self._add_show_toggle(tab, entry, r)
            if key in KEY_HELP:
                tk.Button(tab, text="?", width=2,
                          command=lambda k=key: self._show_help(k)).grid(row=r, column=3, padx=(4, 0))

    def _add_show_toggle(self, parent, entry, row):
        show = tk.BooleanVar(value=False)
        def toggle():
            entry.config(show="" if show.get() else "\u2022")
        tk.Checkbutton(parent, text="Show", variable=show, command=toggle).grid(
            row=row, column=2, sticky="w")

    def _build_other(self, nb):
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Other")

        tk.Label(tab, text="Cache days (reuse answers for)", anchor="w").grid(
            row=0, column=0, sticky="w", pady=4)
        self.vars["CACHE_DAYS"] = tk.StringVar(value=self.env.get("CACHE_DAYS", "30"))
        sb = tk.Spinbox(tab, from_=1, to=365, textvariable=self.vars["CACHE_DAYS"], width=6,
                        command=self._save)
        sb.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.vars["CACHE_DAYS"].trace_add("write", self._save)

        tk.Label(tab, text="JRiver host", anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        self.vars["JRIVER_HOST"] = tk.StringVar(value=self.env.get("JRIVER_HOST", "127.0.0.1:52199"))
        e = tk.Entry(tab, textvariable=self.vars["JRIVER_HOST"], width=22)
        e.grid(row=1, column=1, sticky="w", padx=(12, 0))
        e.bind("<FocusOut>", self._save)

        self.vars["DEBUG"] = tk.BooleanVar(value=self.env.get("DEBUG", "0") in ("1", "true", "yes"))
        tk.Checkbutton(tab, text="Debug (log raw source lists to console)",
                       variable=self.vars["DEBUG"], command=self._save).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))

        tk.Label(tab, text="YouTube playlist length", anchor="w").grid(row=3, column=0, sticky="w", pady=(12, 4))
        self.vars["YOUTUBE_PLAYLIST_LENGTH"] = tk.StringVar(value=self.env.get("YOUTUBE_PLAYLIST_LENGTH", "50"))
        yt_sb = tk.Spinbox(tab, from_=5, to=50, textvariable=self.vars["YOUTUBE_PLAYLIST_LENGTH"], width=6,
                           command=self._save)
        yt_sb.grid(row=3, column=1, sticky="w", padx=(12, 0), pady=(12, 4))
        self.vars["YOUTUBE_PLAYLIST_LENGTH"].trace_add("write", self._save)
        tk.Label(tab, text="How many videos a playlist holds when Output is set to YouTube (5 to 50).\n"
                           "50 is the most YouTube allows in one playlist link.",
                 fg=HELP_FG, font=HELP_FONT, justify="left").grid(row=4, column=0, columnspan=2, sticky="w")

        # Zones: which JRiver zones appear in the Play tab's Zone and Output lists.
        # Filled when the tab is first shown, so a slow JRiver never delays startup.
        tk.Label(tab, text="Zones", font=("Segoe UI", 10, "bold")).grid(row=5, column=0, sticky="w", pady=(18, 2))
        tk.Button(tab, text="Rescan", width=10, command=self._fill_zone_boxes).grid(
            row=5, column=1, sticky="w", padx=(12, 0), pady=(18, 2))
        self.zone_frame = tk.Frame(tab)
        self.zone_frame.grid(row=6, column=0, columnspan=2, sticky="w")
        self.follow_var = tk.BooleanVar(value=engine.FOLLOW_ACTIVE_ZONE)
        ttk.Checkbutton(tab, text="Follow JRiver's active zone", variable=self.follow_var,
                        command=self._save_zone_settings).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))
        tk.Label(tab, text="Show: untick a zone to hide it from the Zone and Output lists on the Play tab.\n"
                           "Default: the zone Now Playing opens on when 24bit7 starts. Picking a zone by hand always wins.\n"
                           "Follow: Now Playing tracks whichever zone JRiver has active, so Default is greyed out.\n"
                           "A DLNA speaker such as a Sonos only appears once DLNA Controller is ticked in\n"
                           "JRiver (Tools > Options > Media Network > Advanced). Press Rescan after ticking it.",
                 fg=HELP_FG, font=HELP_FONT, justify="left").grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.zone_vars, self.zone_radios = {}, {}
        self.default_zone_var = tk.StringVar(value=engine.DEFAULT_ZONE)
        self._zones_filled = False
        tab.bind("<Map>", lambda e: None if self._zones_filled else self._fill_zone_boxes())

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
        """Voice commands: the listener switch, its key, the speakers heard, and a test."""
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Voice")
        self.voice_on = tk.BooleanVar(value=engine.VOICE_ENABLED)
        ttk.Checkbutton(tab, text="Voice control (listen for commands from the Alexa skill)",
                        variable=self.voice_on, command=self._voice_toggled).grid(
            row=0, column=0, columnspan=4, sticky="w")
        self.voice_status = tk.Label(tab, text=voice.status(), fg=HELP_FG, font=HELP_FONT)
        self.voice_status.grid(row=1, column=0, columnspan=4, sticky="w")

        tk.Label(tab, text="Key", anchor="w").grid(row=2, column=0, sticky="w", pady=(14, 2))
        self.voice_key_var = tk.StringVar(value=engine.VOICE_KEY)
        tk.Entry(tab, textvariable=self.voice_key_var, width=40, state="readonly").grid(
            row=2, column=1, sticky="w", padx=(12, 8), pady=(14, 2))
        tk.Button(tab, text="Copy", width=8, command=self._voice_copy_key).grid(row=2, column=2, sticky="w", pady=(14, 2))
        tk.Button(tab, text="New key", width=8, command=self._voice_new_key).grid(
            row=2, column=3, sticky="w", padx=(8, 0), pady=(14, 2))
        tk.Label(tab, text="The Alexa skill sends this key with every command; anything without it is refused.\n"
                           "24bit7 only listens on this PC. The tunnel set up for the skill connects it to Amazon.",
                 fg=HELP_FG, font=HELP_FONT, justify="left").grid(row=3, column=0, columnspan=4, sticky="w")

        tk.Label(tab, text="Speakers", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(18, 2))
        tk.Button(tab, text="Refresh", width=10, command=self._fill_voice_devices).grid(
            row=4, column=1, sticky="w", padx=(12, 0), pady=(18, 2))
        self.voice_dev_frame = tk.Frame(tab)
        self.voice_dev_frame.grid(row=5, column=0, columnspan=4, sticky="w")
        tk.Label(tab, text="Say a command on a speaker that isn't set up and it appears here. Pick the zone it plays to.",
                 fg=HELP_FG, font=HELP_FONT, justify="left").grid(row=6, column=0, columnspan=4, sticky="w", pady=(4, 0))

        tk.Label(tab, text="Test", font=("Segoe UI", 10, "bold")).grid(row=7, column=0, sticky="w", pady=(18, 2))
        test = tk.Frame(tab)
        test.grid(row=8, column=0, columnspan=4, sticky="w")
        tk.Label(test, text="Music like").pack(side="left")
        self.voice_test_artist = tk.Entry(test, width=24)
        self.voice_test_artist.insert(0, "Agnes Obel")
        self.voice_test_artist.pack(side="left", padx=(6, 12))
        tk.Label(test, text="on").pack(side="left")
        self.voice_test_zone = ttk.Combobox(test, state="readonly", width=22,
                                            postcommand=lambda: self.voice_test_zone.config(values=engine.zone_names()))
        self.voice_test_zone.pack(side="left", padx=(6, 12))
        tk.Button(test, text="Send test", width=10, command=self._voice_test).pack(side="left")
        self.voice_test_result = tk.Label(tab, text="", fg=HELP_FG, font=HELP_FONT, justify="left")
        self.voice_test_result.grid(row=9, column=0, columnspan=4, sticky="w", pady=(6, 0))

        tab.bind("<Map>", lambda e: (self.voice_status.config(text=voice.status()), self._fill_voice_devices()))

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
            tk.Label(self.voice_dev_frame, text="No speakers heard yet.", fg=HELP_FG, font=HELP_FONT).grid(
                row=0, column=0, sticky="w")
            return
        zones = engine.zone_names()
        for c, heading in enumerate(("Name", "Zone", "Last heard")):
            tk.Label(self.voice_dev_frame, text=heading, fg=HELP_FG, font=HELP_FONT).grid(
                row=0, column=c, sticky="w", padx=(0, 12))
        for r, (device_id, name, zone, heard) in enumerate(rows, start=1):
            name_var = tk.StringVar(value=name)
            entry = tk.Entry(self.voice_dev_frame, textvariable=name_var, width=22)
            entry.grid(row=r, column=0, sticky="w", padx=(0, 12), pady=2)
            save_name = lambda e, d=device_id, v=name_var: voice.update_device(d, name=v.get().strip() or "Speaker")
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

    def _voice_test(self):
        if not voice.status().startswith("Listening"):
            self.voice_test_result.config(text="Switch Voice control on first.")
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
                self.voice_test_result.config(text="Alexa would say: " + result[0] +
                                              "\nThe build itself shows in the Play tab log.")
            else:
                self.after(200, show)
        self.after(200, show)

    def _build_search_sites(self, nb):
        """Discover search sites: which stores and reference sites to open per row."""
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Search")
        ttk.Style(self).configure("Big.TCheckbutton", font=("Segoe UI", 11))
        cols = 4
        for c in range(cols):
            tab.grid_columnconfigure(c, weight=1, uniform="sites")   # equal-width columns
        r = 0

        tk.Label(tab, text="Stores (search by artist and track)", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=cols, sticky="w")
        r += 1
        # Carry over a pre-1.1.0 single DIGITAL_STORE if the new key isn't there yet.
        stores_raw = self.env.get("DIGITAL_STORES", self.env.get("DIGITAL_STORE", "bandcamp"))
        chosen_stores = [x.strip().lower() for x in stores_raw.split(",") if x.strip()]
        self.vars["DIGITAL_STORES"] = {}
        for i, (code, label) in enumerate(engine.STORE_OPTIONS):
            v = tk.BooleanVar(value=code in chosen_stores)
            self.vars["DIGITAL_STORES"][code] = v
            ttk.Checkbutton(tab, text=label, variable=v, command=self._save,
                            style="Big.TCheckbutton").grid(
                row=r + i // cols, column=i % cols, sticky="w", padx=(0, 16), pady=2)
        r += (len(engine.STORE_OPTIONS) + cols - 1) // cols

        tk.Label(tab, text="Reference (search the artist, for a discography)",
                 font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=cols, sticky="w", pady=(16, 0))
        r += 1
        chosen_ref = self._csv_list("REFERENCE_SITES", "")
        self.vars["REFERENCE_SITES"] = {}
        for i, (code, label) in enumerate(engine.REFERENCE_OPTIONS):
            v = tk.BooleanVar(value=code in chosen_ref)
            self.vars["REFERENCE_SITES"][code] = v
            ttk.Checkbutton(tab, text=label, variable=v, command=self._save,
                            style="Big.TCheckbutton").grid(
                row=r + i // cols, column=i % cols, sticky="w", padx=(0, 16), pady=2)
        r += (len(engine.REFERENCE_OPTIONS) + cols - 1) // cols

        tk.Label(tab, text="Listen (search by artist and track)", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=cols, sticky="w", pady=(16, 0))
        r += 1
        chosen_listen = self._csv_list("LISTEN_SITES", "youtube")
        self.vars["LISTEN_SITES"] = {}
        for i, (code, label) in enumerate(engine.LISTEN_OPTIONS):
            v = tk.BooleanVar(value=code in chosen_listen)
            self.vars["LISTEN_SITES"][code] = v
            ttk.Checkbutton(tab, text=label, variable=v, command=self._save,
                            style="Big.TCheckbutton").grid(
                row=r + i // cols, column=i % cols, sticky="w", padx=(0, 16), pady=2)
        r += (len(engine.LISTEN_OPTIONS) + cols - 1) // cols

        tk.Label(tab, text="Custom sites", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=cols, sticky="w", pady=(16, 0))
        r += 1
        custom = tk.Frame(tab)
        custom.grid(row=r, column=0, columnspan=cols, sticky="ew")
        custom.grid_columnconfigure(1, weight=1)   # the link field takes whatever width is left
        for c, heading in enumerate(("Button name", "Search link", "Search by")):
            tk.Label(custom, text=heading, fg="#666", font=("Segoe UI", 8)).grid(
                row=0, column=c, sticky="w", padx=(0, 8))
        for n in range(1, engine.CUSTOM_SITE_SLOTS + 1):
            name_var = tk.StringVar(value=self.env.get(f"CUSTOM_SITE_{n}_NAME", ""))
            url_var = tk.StringVar(value=self.env.get(f"CUSTOM_SITE_{n}_URL", ""))
            artist_only = self.env.get(f"CUSTOM_SITE_{n}_MODE", "track").strip().lower() == "artist"
            mode_var = tk.StringVar(value="Artist only" if artist_only else "Artist and track")
            self.vars[f"CUSTOM_SITE_{n}_NAME"] = name_var
            self.vars[f"CUSTOM_SITE_{n}_URL"] = url_var
            self.vars[f"CUSTOM_SITE_{n}_MODE"] = mode_var
            name_entry = tk.Entry(custom, textvariable=name_var, width=18)
            name_entry.grid(row=n, column=0, sticky="w", padx=(0, 8), pady=2)
            url_entry = tk.Entry(custom, textvariable=url_var, width=20)
            url_entry.grid(row=n, column=1, sticky="ew", padx=(0, 8), pady=2)
            for entry in (name_entry, url_entry):
                entry.bind("<FocusOut>", self._save)   # save when leaving the field
            mode_cb = ttk.Combobox(custom, textvariable=mode_var, state="readonly", width=16,
                                   values=["Artist and track", "Artist only"])
            mode_cb.grid(row=n, column=2, sticky="w", pady=2)
            mode_cb.bind("<<ComboboxSelected>>", self._save)
        r += 1
        tk.Label(tab, text="To add a site: search for anything on it, copy the address from your browser, then replace\n"
                           "your search words with {query}. Example: https://www.prestomusic.com/search?q={query}\n"
                           "Clear the button name to remove a site. Only links starting with http:// or https:// are used.",
                 fg="#666", font=("Segoe UI", 8), justify="left").grid(
            row=r, column=0, columnspan=cols, sticky="w", pady=(4, 0))
        r += 1

        tk.Label(tab, text="Each ticked site gets its own button on the Discover tab.\n"
                           "At least one store must stay ticked.",
                 fg="#666", font=("Segoe UI", 9), justify="left").grid(
            row=r, column=0, columnspan=cols, sticky="w", pady=(12, 0))

    # --- helpers -----------------------------------------------------------

    def _csv_list(self, key, default):
        return [x.strip().lower() for x in self.env.get(key, default).split(",") if x.strip()]

    def _show_help(self, key):
        title, body = KEY_HELP[key]
        messagebox.showinfo(title, body, parent=self)