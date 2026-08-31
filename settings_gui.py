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
import tkinter as tk
from tkinter import ttk, messagebox

import engine

ENV_FILE = engine.ENV_FILE   # single source of truth for where .env lives

# Listed alphabetically by display name
SOURCE_NAMES = [("ai", "AI"), ("deezer", "Deezer"),
                ("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz")]

DIGITAL_STORES = ["bandcamp", "discogs", "qobuz", "amazon", "juno",
                  "hdtracks", "hiresaudio", "7digital"]

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
    """Updates managed keys in place, preserving comments, blanks and unmanaged keys."""
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

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_sources(nb)
        self._build_playlist(nb)
        self._build_keys(nb)
        self._build_other(nb)

        self._loading = False

    # --- persistence -------------------------------------------------------

    def _current_updates(self):
        updates = {}
        for group in ("SIMILAR_SOURCES", "TOP_TRACK_SOURCES"):
            chosen = [code for code, v in self.vars[group].items() if v.get()]
            updates[group] = ",".join(chosen)
        for key in ["LISTENBRAINZ_ALGORITHM", "SIMILAR_ARTIST_LIMIT", "TRACKS_PER_ARTIST_POOL",
                    "TRACKS_PER_ARTIST_PICK", "TOP_TRACKS_COUNT", "VIBE_TRACK_COUNT", "TOP_TRACKS_ORDER",
                    "CACHE_DAYS", "DIGITAL_STORE", "JRIVER_HOST"] + KEY_FIELDS:
            updates[key] = self.vars[key].get().strip()
        updates["DEBUG"] = "1" if self.vars["DEBUG"].get() else "0"
        return updates

    def _save(self, *_):
        """Auto-save. Skips writing empty source lists (keeps the last good file)."""
        if self._loading:
            return
        updates = self._current_updates()
        if not updates["SIMILAR_SOURCES"] or not updates["TOP_TRACK_SOURCES"]:
            return   # don't persist a no-sources state; user is mid-change
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
            ttk.Checkbutton(tab, text=label, variable=v, command=self._save,
                            style="Big.TCheckbutton").grid(row=r, column=i, sticky="w", padx=(0, 12))
        r += 1

        tk.Label(tab, text="Top-track sources", font=("Segoe UI", 9, "bold")).grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(16, 0))
        r += 1
        chosen_top = self._csv_list("TOP_TRACK_SOURCES", "lastfm")
        self.vars["TOP_TRACK_SOURCES"] = {}
        for i, (code, label) in enumerate(SOURCE_NAMES):
            v = tk.BooleanVar(value=code in chosen_top)
            self.vars["TOP_TRACK_SOURCES"][code] = v
            ttk.Checkbutton(tab, text=label, variable=v, command=self._save,
                            style="Big.TCheckbutton").grid(row=r, column=i, sticky="w", padx=(0, 12))
        r += 1

        tk.Label(tab, text="More services = richer, more varied playlists (slower).\n"
                          "Fewer = quicker.",
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

    def _build_playlist(self, nb):
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Playlist")
        rows = [
            ("Similar artists (count)", "SIMILAR_ARTIST_LIMIT", "20", 1, 50),
            ("Library tracks per artist to consider", "TRACKS_PER_ARTIST_POOL", "5", 1, 20),
            ("Tracks per artist to queue", "TRACKS_PER_ARTIST_PICK", "3", 1, 20),
            ("Top tracks (count, 1-20)", "TOP_TRACKS_COUNT", "10", 1, 20),
            ("Vibe playlist (track count)", "VIBE_TRACK_COUNT", "20", 5, 100),
        ]
        for r, (label, key, default, lo, hi) in enumerate(rows):
            tk.Label(tab, text=label, anchor="w").grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=self.env.get(key, default))
            self.vars[key] = var
            sb = tk.Spinbox(tab, from_=lo, to=hi, textvariable=var, width=6, command=self._save)
            sb.grid(row=r, column=1, sticky="w", padx=(12, 0))
            var.trace_add("write", self._save)

        r = len(rows)
        tk.Label(tab, text="Top-tracks order", anchor="w").grid(row=r, column=0, sticky="w", pady=4)
        self.vars["TOP_TRACKS_ORDER"] = tk.StringVar(value=self.env.get("TOP_TRACKS_ORDER", "popular"))
        cb = ttk.Combobox(tab, textvariable=self.vars["TOP_TRACKS_ORDER"],
                          values=["popular", "reverse", "random"], state="readonly", width=12)
        cb.grid(row=r, column=1, sticky="w", padx=(12, 0))
        cb.bind("<<ComboboxSelected>>", self._save)
        r += 1
        bullet = "\u2022"
        tk.Label(tab,
                 text=f"{bullet}  popular - most played first\n"
                      f"{bullet}  reverse - least played first\n"
                      f"{bullet}  random - shuffled",
                 fg="#666", font=("Segoe UI", 8), justify="left").grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(6, 0))

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

        tk.Label(tab, text="Digital store (for Discover search)", anchor="w").grid(
            row=1, column=0, sticky="w", pady=4)
        self.vars["DIGITAL_STORE"] = tk.StringVar(value=self.env.get("DIGITAL_STORE", "bandcamp"))
        cb = ttk.Combobox(tab, textvariable=self.vars["DIGITAL_STORE"], values=DIGITAL_STORES,
                          state="readonly", width=14)
        cb.grid(row=1, column=1, sticky="w", padx=(12, 0))
        cb.bind("<<ComboboxSelected>>", self._save)

        tk.Label(tab, text="JRiver host", anchor="w").grid(row=2, column=0, sticky="w", pady=4)
        self.vars["JRIVER_HOST"] = tk.StringVar(value=self.env.get("JRIVER_HOST", "127.0.0.1:52199"))
        e = tk.Entry(tab, textvariable=self.vars["JRIVER_HOST"], width=22)
        e.grid(row=2, column=1, sticky="w", padx=(12, 0))
        e.bind("<FocusOut>", self._save)

        self.vars["DEBUG"] = tk.BooleanVar(value=self.env.get("DEBUG", "0") in ("1", "true", "yes"))
        tk.Checkbutton(tab, text="Debug (log raw source lists to console)",
                       variable=self.vars["DEBUG"], command=self._save).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

    # --- helpers -----------------------------------------------------------

    def _csv_list(self, key, default):
        return [x.strip().lower() for x in self.env.get(key, default).split(",") if x.strip()]

    def _show_help(self, key):
        title, body = KEY_HELP[key]
        messagebox.showinfo(title, body, parent=self)