"""
24bit7 - Discover tab.

Browses the discoveries logged by every playlist run: artists (and tracks) that
weren't in the library, plus the ones that were, filterable by hit/miss and by
session. A per-row Search opens the chosen digital store's search page in the
browser, so a discovery leads to buying it rather than pirating it.
"""

import csv
import os
import urllib.parse
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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
}


class DiscoverTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.sessions = []
        self._loaded = False
        self._build_controls()
        self._build_table()
        # Rows are loaded the first time the tab is shown (see ensure_loaded),
        # so app startup isn't slowed by inserting hundreds of table rows.

    def ensure_loaded(self):
        """Called by the main window when this tab becomes visible."""
        if not self._loaded:
            self._loaded = True
            self.refresh()

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

        tk.Label(bar, text="   Session:").pack(side="left")
        self.session_var = tk.StringVar(value="All sessions")
        self.session_menu = ttk.Combobox(bar, textvariable=self.session_var,
                                         state="readonly", width=28)
        self.session_menu.pack(side="left", padx=(4, 0))
        self.session_menu.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        self.count_label = tk.Label(bar, text="", fg="#777")
        self.count_label.pack(side="right")

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

        style = ttk.Style(self)
        # Rows must be tall enough for the DPI-scaled font, or text gets clipped.
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=32)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        cols = ("seed", "artist", "track", "sources", "found", "date")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="browse")
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
        self.tree.bind("<Double-1>", lambda e: self.search_selected())

        btnbar = tk.Frame(self, padx=12, pady=8)
        btnbar.pack(fill="x")
        self.store_label = tk.Label(btnbar, text="", fg="#777")
        self.store_label.pack(side="left")
        tk.Button(btnbar, text="Search selected in store",
                  command=self.search_selected).pack(side="right")
        tk.Button(btnbar, text="Export to CSV",
                  command=self.export_csv).pack(side="right", padx=(0, 8))
        tk.Button(btnbar, text="Refresh", command=self.refresh).pack(side="right", padx=(0, 8))

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
            labels.append(f"{started}  {seed}")
            self._session_ids.append(sid)
        self.session_menu.config(values=labels)
        if self.session_var.get() not in labels:
            self.session_var.set("All sessions")

    def refresh(self):
        self._reload_sessions()
        engine.load_settings()   # pick up the current DIGITAL_STORE
        self.store_label.config(text=f"Store: {engine.DIGITAL_STORE}")

        f = self.filter_var.get()
        found = None if f == "all" else (f == "hits")
        idx = self.session_menu.current()
        session_id = self._session_ids[idx] if 0 <= idx < len(self._session_ids) else None

        self._rows = engine.list_discoveries(found=found, session_id=session_id)
        self._populate()

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
                seed, r["artist"], r["track"] or "", r["sources"] or "", found, r["date"]))
            self._visible.append((seed, r["artist"] or "", r["track"] or "",
                                  r["sources"] or "", found, r["date"] or ""))
        self.count_label.config(text=f"{len(self._visible)} shown")

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

    def search_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        row = self._rows[int(sel[0])]
        terms = row["artist"]
        if row["track"]:
            terms += f" {row['track']}"
        query = urllib.parse.quote_plus(terms)
        builder = STORE_SEARCH.get(engine.DIGITAL_STORE, STORE_SEARCH["bandcamp"])
        webbrowser.open(builder(query))