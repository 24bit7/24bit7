"""
24bit7 - Settings window.

Reads current values from .env, presents them as tabbed controls, and writes
changes back safely: existing comments, blank lines and unmanaged keys are
preserved; only the keys this window owns are updated or appended. The engine
picks up the saved file automatically via its .env mod-time check.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox

ENV_FILE = ".env"

SOURCE_NAMES = [("lastfm", "Last.fm"), ("listenbrainz", "ListenBrainz"),
                ("deezer", "Deezer"), ("ai", "AI")]

DIGITAL_STORES = ["bandcamp", "discogs", "qobuz", "amazon", "juno",
                  "hdtracks", "hiresaudio", "7digital"]

# "where do I get this" help text per credential
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
    """Returns a dict of the current KEY=VALUE pairs in .env (comments ignored)."""
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
    Writes updates back to .env, preserving comments, blank lines and any key
    this window doesn't manage. Managed keys already present are updated in
    place; managed keys not present are appended.
    """
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


class SettingsWindow(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("24bit7 - Settings")
        self.geometry("520x520")
        self.resizable(False, False)
        self.env = read_env()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.vars = {}
        self._build_sources(nb)
        self._build_playlist(nb)
        self._build_keys(nb)
        self._build_other(nb)

        bar = tk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bar, text="Save", width=12, command=self.on_save).pack(side="right")
        tk.Button(bar, text="Cancel", width=12, command=self.destroy).pack(side="right", padx=(0, 8))

    # --- helpers -----------------------------------------------------------

    def _csv_list(self, key, default):
        return [x.strip().lower() for x in self.env.get(key, default).split(",") if x.strip()]

    def _labelled(self, parent, text, row):
        tk.Label(parent, text=text, anchor="w").grid(row=row, column=0, sticky="w", pady=4)

    # --- tabs --------------------------------------------------------------

    def _build_sources(self, nb):
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Sources")

        tk.Label(tab, text="Similar-artist sources", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        chosen_sim = self._csv_list("SIMILAR_SOURCES", "lastfm")
        self.vars["SIMILAR_SOURCES"] = {}
        for i, (code, label) in enumerate(SOURCE_NAMES):
            v = tk.BooleanVar(value=code in chosen_sim)
            self.vars["SIMILAR_SOURCES"][code] = v
            tk.Checkbutton(tab, text=label, variable=v).grid(row=1, column=i, sticky="w")

        tk.Label(tab, text="Top-track sources", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, sticky="w", pady=(16, 4))
        chosen_top = self._csv_list("TOP_TRACK_SOURCES", "lastfm")
        self.vars["TOP_TRACK_SOURCES"] = {}
        for i, (code, label) in enumerate(SOURCE_NAMES):
            v = tk.BooleanVar(value=code in chosen_top)
            self.vars["TOP_TRACK_SOURCES"][code] = v
            tk.Checkbutton(tab, text=label, variable=v).grid(row=3, column=i, sticky="w")

        tk.Label(tab, text="ListenBrainz algorithm", font=("Segoe UI", 9, "bold")).grid(
            row=4, column=0, sticky="w", pady=(16, 4))
        self.vars["LISTENBRAINZ_ALGORITHM"] = tk.StringVar(
            value=self.env.get("LISTENBRAINZ_ALGORITHM", "alltime"))
        ttk.Combobox(tab, textvariable=self.vars["LISTENBRAINZ_ALGORITHM"],
                     values=["alltime", "recent"], state="readonly", width=18).grid(
            row=5, column=0, columnspan=2, sticky="w")

    def _build_playlist(self, nb):
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Playlist")
        rows = [
            ("Similar artists (count)", "SIMILAR_ARTIST_LIMIT", "20"),
            ("Library tracks per artist to consider", "TRACKS_PER_ARTIST_POOL", "5"),
            ("Tracks per artist to queue", "TRACKS_PER_ARTIST_PICK", "3"),
            ("Top tracks (count, 1-20)", "TOP_TRACKS_COUNT", "10"),
        ]
        for r, (label, key, default) in enumerate(rows):
            self._labelled(tab, label, r)
            var = tk.StringVar(value=self.env.get(key, default))
            self.vars[key] = var
            tk.Spinbox(tab, from_=1, to=50, textvariable=var, width=6).grid(
                row=r, column=1, sticky="w", padx=(12, 0))

        self._labelled(tab, "Top-tracks order", len(rows))
        self.vars["TOP_TRACKS_ORDER"] = tk.StringVar(value=self.env.get("TOP_TRACKS_ORDER", "popular"))
        ttk.Combobox(tab, textvariable=self.vars["TOP_TRACKS_ORDER"],
                     values=["popular", "reverse", "random"], state="readonly", width=12).grid(
            row=len(rows), column=1, sticky="w", padx=(12, 0))

    def _build_keys(self, nb):
        tab = tk.Frame(nb, padx=12, pady=12)
        nb.add(tab, text="Keys")
        for r, key in enumerate(KEY_FIELDS):
            self._labelled(tab, key, r)
            var = tk.StringVar(value=self.env.get(key, ""))
            self.vars[key] = var
            entry = tk.Entry(tab, textvariable=var, show="\u2022", width=34)
            entry.grid(row=r, column=1, padx=(8, 4))
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

        self._labelled(tab, "Cache days (reuse answers for)", 0)
        self.vars["CACHE_DAYS"] = tk.StringVar(value=self.env.get("CACHE_DAYS", "30"))
        tk.Spinbox(tab, from_=1, to=365, textvariable=self.vars["CACHE_DAYS"], width=6).grid(
            row=0, column=1, sticky="w", padx=(12, 0))

        self._labelled(tab, "Digital store (for Discover search)", 1)
        self.vars["DIGITAL_STORE"] = tk.StringVar(value=self.env.get("DIGITAL_STORE", "bandcamp"))
        ttk.Combobox(tab, textvariable=self.vars["DIGITAL_STORE"], values=DIGITAL_STORES,
                     state="readonly", width=14).grid(row=1, column=1, sticky="w", padx=(12, 0))

        self._labelled(tab, "JRiver host", 2)
        self.vars["JRIVER_HOST"] = tk.StringVar(value=self.env.get("JRIVER_HOST", "127.0.0.1:52199"))
        tk.Entry(tab, textvariable=self.vars["JRIVER_HOST"], width=22).grid(
            row=2, column=1, sticky="w", padx=(12, 0))

        self.vars["DEBUG"] = tk.BooleanVar(value=self.env.get("DEBUG", "0") in ("1", "true", "yes"))
        tk.Checkbutton(tab, text="Debug (log raw source lists)",
                       variable=self.vars["DEBUG"]).grid(row=3, column=0, sticky="w", pady=(12, 0))

    # --- help + save -------------------------------------------------------

    def _show_help(self, key):
        title, body = KEY_HELP[key]
        messagebox.showinfo(title, body, parent=self)

    def on_save(self):
        updates = {}

        for group in ("SIMILAR_SOURCES", "TOP_TRACK_SOURCES"):
            chosen = [code for code, v in self.vars[group].items() if v.get()]
            if not chosen:
                messagebox.showwarning("No sources",
                                       f"Pick at least one {group.replace('_', ' ').lower()}.",
                                       parent=self)
                return
            updates[group] = ",".join(chosen)

        for key in ["LISTENBRAINZ_ALGORITHM", "SIMILAR_ARTIST_LIMIT", "TRACKS_PER_ARTIST_POOL",
                    "TRACKS_PER_ARTIST_PICK", "TOP_TRACKS_COUNT", "TOP_TRACKS_ORDER",
                    "CACHE_DAYS", "DIGITAL_STORE", "JRIVER_HOST"] + KEY_FIELDS:
            updates[key] = self.vars[key].get().strip()

        updates["DEBUG"] = "1" if self.vars["DEBUG"].get() else "0"

        try:
            write_env(updates)
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=self)
            return
        messagebox.showinfo("Saved", "Settings saved. They apply on your next run.", parent=self)
        self.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    SettingsWindow(root)
    root.mainloop()