"""
24bit7 - Discover tab.

Browses the discoveries logged by every playlist run: artists (and tracks) that
weren't in the library, plus the ones that were, filterable by hit/miss and by
session. A per-row Search opens the ticked stores' search pages (artist and
track) and reference sites (artist only) in the browser, one tab each, so a
discovery leads to buying it rather than pirating it.
"""

import csv
import os
import urllib.parse
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
from datetime import datetime

import engine

# Search URL builders per store. Each takes an "artist track" query string.
STORE_SEARCH = {
    "bandcamp":   lambda q: f"https://bandcamp.com/search?q={q}",
    "discogs":    lambda q: f"https://www.discogs.com/search/?q={q}&type=release",
    "qobuz":      lambda q: f"https://www.qobuz.com/gb-en/search?q={q}",
    "amazon":     lambda q: f"https://www.amazon.co.uk/s?k={q}&i=digital-music",
    "juno":       lambda q: f"https://www.juno.co.uk/search/?q%5Ball%5D%5B%5D={q}",
    "hdtracks":   lambda q: f"https://www.hdtracks.com/#/search?q={q}",
    "hiresaudio": lambda q: f"https://www.highresaudio.com/en/search?q={q}",
    "7digital":   lambda q: f"https://www.7digital.com/search?q={q}",
    "bleep":      lambda q: f"https://bleep.com/search?q={q}",
    "beatport":   lambda q: f"https://www.beatport.com/search?q={q}",
}

# Reference sites take an artist-only query, for browsing the discography.
REFERENCE_SEARCH = {
    "wikipedia":   lambda q: f"https://en.wikipedia.org/w/index.php?search={q}",
    "discogs_ref": lambda q: f"https://www.discogs.com/search/?q={q}&type=artist",
    "allmusic":    lambda q: f"https://www.allmusic.com/search/artists/{q}",
    "musicbrainz": lambda q: f"https://musicbrainz.org/search?query={q}&type=artist&method=indexed",
}

# "Listen" sites take an "artist track" query, like the stores.
LISTEN_SEARCH = {
    "youtube": lambda q: f"https://www.youtube.com/results?search_query={q}",
}


def custom_search(url):
    """Builder for a user's own site: {query} marks where the search words go (else they go on the end)."""
    return lambda q: url.replace("{query}", q) if "{query}" in url else url + q


SESSION_MENU_WIDTH = 50   # minimum characters; the box also stretches with the window


def short_started(started):
    """
    Compact form of a session's start time for the dropdown:
    '2026-09-04 22:02' -> '04 Sep 22:02'. Anything that doesn't parse
    (e.g. legacy CSV dates) is shown as stored.
    """
    try:
        return datetime.strptime(started, "%Y-%m-%d %H:%M").strftime("%d %b %H:%M")
    except (TypeError, ValueError):
        return started or "?"


class DiscoverTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.sessions = []
        self._loaded = False
        self._build_controls()
        self._build_table()
        # Rows are loaded the first time the tab is shown (see ensure_loaded),
        # so app startup isn't slowed by inserting hundreds of table rows.

    def _apply_table_font(self):
        """
        Sizes the table from the TABLE_FONT_SIZE setting. On Windows the ttk
        Treeview ignores a font set on the style for cell text, so the cell font
        is applied through a row tag (which is honoured). Row height is measured
        from the real rendered font so it fits at any DPI.
        """
        size = getattr(engine, "TABLE_FONT_SIZE", 9)
        self._cell_font = tkfont.Font(family="Segoe UI", size=size)
        rowheight = self._cell_font.metrics("linespace") + 8
        style = ttk.Style(self)
        style.configure("Treeview", rowheight=rowheight)
        style.configure("Treeview.Heading", font=("Segoe UI", size, "bold"))
        # Row tag carries the cell font; every inserted row gets this tag.
        self.tree.tag_configure("cell", font=self._cell_font)

    def _on_font_change(self):
        """Applies a new table font size immediately and saves it to .env."""
        try:
            size = int(self.font_var.get())
        except ValueError:
            return
        if not 6 <= size <= 16:
            return
        engine.TABLE_FONT_SIZE = size
        self._apply_table_font()
        if getattr(self, "_rows", None) is not None:
            self._populate()   # re-insert rows so the new tag font takes effect
        try:
            from settings_gui import write_env
            write_env({"TABLE_FONT_SIZE": str(size)})
        except Exception:
            pass

    def ensure_loaded(self):
        """Called by the main window when this tab becomes visible."""
        if not self._loaded:
            self._loaded = True
            self.refresh()
        else:
            engine.refresh_settings_if_changed()   # a site ticked in Settings shows up straight away
            self._rebuild_site_buttons()

    # --- layout ------------------------------------------------------------

    def _build_controls(self):
        bar = tk.Frame(self, padx=12, pady=8)
        bar.pack(fill="x")

        ttk.Style(self).configure("Big.TRadiobutton", font=("Segoe UI", 11))
        self.filter_var = tk.StringVar(value="misses")
        for label, val in [("Misses", "misses"), ("Hits", "hits"), ("All", "all")]:
            ttk.Radiobutton(bar, text=label, variable=self.filter_var, value=val,
                            command=self.refresh, style="Big.TRadiobutton").pack(
                side="left", padx=(0, 10))

        # Count label is packed first so it keeps its spot on the right; the
        # session dropdown then stretches to fill whatever width is left.
        self.count_label = tk.Label(bar, text="", fg="#777")
        self.count_label.pack(side="right")

        tk.Label(bar, text="   Session:").pack(side="left")
        self.session_var = tk.StringVar(value="All sessions")
        self.session_menu = ttk.Combobox(bar, textvariable=self.session_var,
                                         state="readonly", width=SESSION_MENU_WIDTH)
        self.session_menu.pack(side="left", padx=(4, 12), fill="x", expand=True)
        self.session_menu.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        search_bar = tk.Frame(self, padx=12)
        search_bar.pack(fill="x")
        tk.Label(search_bar, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._populate())
        tk.Entry(search_bar, textvariable=self.search_var).pack(
            side="left", fill="x", expand=True, padx=(4, 0))

    def _build_table(self):
        wrap = tk.Frame(self, padx=12, pady=8)
        wrap.pack(fill="both", expand=True)

        cols = ("seed", "artist", "track", "sources", "found", "date")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="browse")
        self._apply_table_font()
        headings = {"seed": "Seed", "artist": "Artist", "track": "Track",
                    "sources": "Suggested by", "found": "In library", "date": "When"}
        widths = {"seed": 160, "artist": 140, "track": 150, "sources": 120,
                  "found": 65, "date": 100}
        for c in cols:
            self.tree.heading(c, text=headings[c], command=lambda cc=c: self._sort_by(cc))
            self.tree.column(c, width=widths[c], anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sync_site_buttons())

        btnbar = tk.Frame(self, padx=12, pady=8)
        btnbar.pack(fill="x")

        # One row: Font size on the left, the site buttons after it, Refresh and CSV
        # pinned right. Only if the site buttons can't fit do they drop to a second row.
        self._bar_top = tk.Frame(btnbar)
        self._bar_top.pack(fill="x")
        self._bar_left = tk.Frame(self._bar_top)
        self._bar_left.pack(side="left")
        # Font size control lives here, where its effect is visible.
        tk.Label(self._bar_left, text="Font size:").pack(side="left")
        self.font_var = tk.StringVar(value=str(getattr(engine, "TABLE_FONT_SIZE", 9)))
        tk.Spinbox(self._bar_left, from_=6, to=16, textvariable=self.font_var, width=4,
                   command=self._on_font_change).pack(side="left", padx=(4, 0))
        self.font_var.trace_add("write", lambda *a: self._on_font_change())

        self._bar_right = tk.Frame(self._bar_top)
        self._bar_right.pack(side="right")
        tk.Button(self._bar_right, text="CSV", command=self.export_csv).pack(side="right")
        tk.Button(self._bar_right, text="Refresh", command=self.refresh).pack(side="right", padx=(0, 8))

        self._sites_inline = tk.Frame(self._bar_top)   # the site buttons, when they fit on the row
        self._sites_inline.pack(side="left", padx=(16, 0))
        self._sites_below = tk.Frame(btnbar)           # ...or here, as a second row, when they don't
        self._site_buttons = []
        self._site_signature = None
        self._site_mode = "inline"
        self._sites_needed = 0
        self._bar_top.bind("<Configure>", lambda e: self._place_site_buttons())

        self._rows = []           # parallel list of dicts backing the tree
        self._sort_col = None
        self._sort_reverse = False

    # --- data --------------------------------------------------------------

    def _reload_sessions(self):
        self.sessions = engine.list_sessions()
        labels = ["All sessions"]
        self._session_ids = [None]
        for sid, started, mode, artist, track in self.sessions:
            seed = artist or "?"
            if track:
                seed += f" - {track}"
            labels.append(f"{short_started(started)}  {seed}")
            self._session_ids.append(sid)
        self.session_menu.config(values=labels)
        if self.session_var.get() not in labels:
            self.session_var.set("All sessions")

    def refresh(self):
        self._reload_sessions()
        engine.load_settings()   # pick up DIGITAL_STORES, REFERENCE_SITES and TABLE_FONT_SIZE
        self._apply_table_font()
        self._rebuild_site_buttons()

        f = self.filter_var.get()
        found = None if f == "all" else (f == "hits")
        idx = self.session_menu.current()
        session_id = self._session_ids[idx] if 0 <= idx < len(self._session_ids) else None

        self._rows = engine.list_discoveries(found=found, session_id=session_id)
        self._populate()

    def _sites_text(self):
        labels = dict(engine.STORE_OPTIONS + engine.REFERENCE_OPTIONS)
        stores = [labels.get(c, c) for c in engine.DIGITAL_STORES]
        refs = [labels.get(c, c) for c in engine.REFERENCE_SITES]
        text = "Search: " + ", ".join(stores)
        if refs:
            text += "  +  " + ", ".join(refs)
        return text

    def _seed_text(self, r):
        seed = r.get("seed_artist") or "?"
        if r.get("seed_track"):
            seed += f" - {r['seed_track']}"
        return seed

    def _populate(self):
        term = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        self.tree.delete(*self.tree.get_children())
        self._visible = []
        for i, r in enumerate(self._rows):
            seed = self._seed_text(r)
            found = "yes" if r["found"] else "no"
            haystack = " ".join([seed, r["artist"] or "", r["track"] or "",
                                 r["sources"] or "", found, r["date"] or ""]).lower()
            if term and term not in haystack:
                continue
            self.tree.insert("", "end", iid=str(i), values=(
                seed, r["artist"], r["track"] or "", r["sources"] or "", found, r["date"]),
                tags=("cell",))
            self._visible.append((seed, r["artist"] or "", r["track"] or "",
                                  r["sources"] or "", found, r["date"] or ""))
        self.count_label.config(text=f"{len(self._visible)} shown")
        self._sync_site_buttons()

    def export_csv(self):
        if not getattr(self, "_visible", None):
            messagebox.showinfo("Nothing to export", "No rows are shown.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")], initialfile="24bit7_discoveries.csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Seed", "Artist", "Track", "Suggested by", "In library", "When"])
                w.writerows(self._visible)
        except Exception as e:
            messagebox.showerror("Export failed", str(e), parent=self)
            return
        messagebox.showinfo("Exported", f"Saved {len(self._visible)} rows to\n{path}", parent=self)

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col, self._sort_reverse = col, False
        if col == "seed":
            self._rows.sort(key=lambda r: self._seed_text(r).lower(), reverse=self._sort_reverse)
        else:
            keymap = {"artist": "artist", "track": "track", "sources": "sources",
                      "found": "found", "date": "date"}
            self._rows.sort(key=lambda r: (r[keymap[col]] is None, r[keymap[col]]),
                            reverse=self._sort_reverse)
        self._populate()

    # --- actions -----------------------------------------------------------

    def _site_list(self):
        """[(button label, 'track' or 'artist', url builder)] for every ticked and custom site, A to Z."""
        labels = dict(engine.STORE_OPTIONS + engine.REFERENCE_OPTIONS + getattr(engine, "LISTEN_OPTIONS", []))
        sites = [(labels.get(c, c), "track", STORE_SEARCH[c]) for c in engine.DIGITAL_STORES if c in STORE_SEARCH]
        sites += [(labels.get(c, c), "artist", REFERENCE_SEARCH[c])
                  for c in engine.REFERENCE_SITES if c in REFERENCE_SEARCH]
        sites += [(labels.get(c, c), "track", LISTEN_SEARCH[c])
                  for c in getattr(engine, "LISTEN_SITES", []) if c in LISTEN_SEARCH]
        sites += [(s["name"], s["mode"], custom_search(s["url"])) for s in getattr(engine, "CUSTOM_SITES", [])]
        return sorted(sites, key=lambda s: s[0].lower())

    def _rebuild_site_buttons(self, force=False):
        """Rebuilds the site buttons when the ticked sites have changed (or the row they sit on has)."""
        sites = self._site_list()
        signature = [(label, kind) for label, kind, _ in sites] + [s.get("url") for s in getattr(engine, "CUSTOM_SITES", [])]
        if signature == self._site_signature and not force:
            self._sync_site_buttons()
            return
        self._site_signature = signature
        for b in self._site_buttons:
            b.destroy()
        parent = self._sites_inline if self._site_mode == "inline" else self._sites_below
        self._site_buttons = []
        for label, kind, builder in sites:
            b = tk.Button(parent, text=label, command=lambda k=kind, f=builder: self.open_site(k, f))
            b.pack(side="left", padx=(0, 6))
            self._site_buttons.append(b)
        self.update_idletasks()
        self._sites_needed = parent.winfo_reqwidth()
        self._sync_site_buttons()
        self._place_site_buttons()

    def _place_site_buttons(self):
        """Keeps the site buttons on the main row if they fit, otherwise moves the whole set to a second row."""
        width = self._bar_top.winfo_width()
        if width <= 1 or not self._site_buttons:
            mode = "inline"
        else:
            room = width - self._bar_left.winfo_reqwidth() - self._bar_right.winfo_reqwidth() - 16 - 8
            mode = "inline" if self._sites_needed <= room else "below"
        if mode == "below":
            self._sites_below.pack(fill="x", pady=(6, 0))
        else:
            self._sites_below.pack_forget()
        if mode != self._site_mode:
            self._site_mode = mode
            self._rebuild_site_buttons(force=True)

    def _sync_site_buttons(self):
        """Site buttons only work on a selected row, so they are greyed out until there is one."""
        state = "normal" if self.tree.selection() else "disabled"
        for b in getattr(self, "_site_buttons", []):
            b.config(state=state)

    def open_site(self, kind, builder):
        """Opens ONE site for the selected row: artist + track, or artist only for reference-style sites."""
        sel = self.tree.selection()
        if not sel:
            return
        row = self._rows[int(sel[0])]
        terms = row["artist"] or ""
        if kind == "track" and row["track"]:
            terms += f" {row['track']}"
        webbrowser.open_new_tab(builder(urllib.parse.quote_plus(terms)))
