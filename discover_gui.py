"""
24bit7 - Discover tab.

Browses the discoveries logged by every playlist run: artists (and tracks) that
weren't in the library, plus the ones that were, filterable by hit/miss and by
session. A per-row Search opens the ticked stores' search pages (artist and
track) and reference sites (artist only) in the browser, one tab each, so a
discovery leads to buying it rather than pirating it. The Label button finds who
released the selected track and opens the label on Bandcamp, so buying it
supports the artist through their label.
"""

import csv
import os
import threading
import time
import urllib.parse
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
from datetime import datetime

import engine
from i18n import t, tn
from tabs import PALETTE, FlatButton, RoundedEntry

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
    "tidal":   lambda q: f"https://tidal.com/search?q={q}",
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
        # so app startup isn't slowed by inserting hundreds of table rows. Everything
        # else is in place from the start: the site buttons are drawn now, and
        # Session says it's loading until the sessions arrive.
        self.session_var.set(t("Loading sessions..."))
        self.count_label.config(text=t("Loading..."))
        self.after_idle(self._rebuild_site_buttons)

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
        # The tick column fits its box at any font size and display scaling
        self._tick_width = self._cell_font.measure("\u2611") + 16
        if "tick" in (self.tree["columns"] or ()):
            self.tree.column("tick", width=self._tick_width, minwidth=self._tick_width)

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
            # The tab shows straight away with "Loading..."; the table fills a moment later
            self.count_label.config(text=t("Loading..."))
            self.after_idle(lambda: self.after(15, self._first_load))
        else:
            engine.refresh_settings_if_changed()   # a site ticked in Settings shows up straight away
            self._rebuild_site_buttons()

    def _first_load(self):
        started = time.time()
        self.refresh()
        engine.debug(f"Discover: {len(self._rows):,} rows in {time.time() - started:.2f} s")

    # --- layout ------------------------------------------------------------

    def _build_controls(self):
        bar = tk.Frame(self, padx=22, pady=8)
        bar.pack(fill="x", pady=(14, 0))   # clear of the tabs above

        # Show: which discoveries the table lists (the value the rest of the tab reads)
        tk.Label(bar, text=t("Show:")).pack(side="left")
        self.filter_var = tk.StringVar(value="misses")
        self._filter_names = {t("Misses"): "misses", t("Hits"): "hits", t("All"): "all"}
        self.filter_menu = ttk.Combobox(bar, values=list(self._filter_names), state="readonly", width=10)
        self.filter_menu.set(t("Misses"))
        self.filter_menu.pack(side="left", padx=(4, 0))
        self.filter_menu.bind("<<ComboboxSelected>>", self._on_filter_changed)

        # Count label is packed first so it keeps its spot on the right; the
        # session dropdown then stretches to fill whatever width is left.
        self.count_label = tk.Label(bar, text="", fg=PALETTE["text_muted"])
        self.count_label.pack(side="right")

        tk.Label(bar, text="   " + t("Session:")).pack(side="left")
        self.session_var = tk.StringVar(value=t("All sessions"))
        self.session_menu = ttk.Combobox(bar, textvariable=self.session_var,
                                         state="readonly", width=SESSION_MENU_WIDTH)
        self.session_menu.pack(side="left", padx=(4, 12), fill="x", expand=True)
        self.session_menu.bind("<<ComboboxSelected>>", self._on_session_picked)

        search_bar = tk.Frame(self, padx=22)
        search_bar.pack(fill="x", pady=(8, 4))
        tk.Label(search_bar, text=t("Search:")).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._populate())
        self.search_box = RoundedEntry(search_bar, width=36, font=("Segoe UI", 9),
                                       placeholder=t("Artist, track or seed"), textvariable=self.search_var)
        self.search_box.pack(side="left", padx=(4, 0))
        # Text size for the table, right-aligned on the search row: A- and A+ (6 to 16, remembered)
        self.font_var = tk.StringVar(value=str(getattr(engine, "TABLE_FONT_SIZE", 9)))
        self.font_var.trace_add("write", lambda *a: self._on_font_change())
        sizes = tk.Frame(search_bar)
        sizes.pack(side="right")
        self.smaller_button = FlatButton(sizes, text="A-", quiet=True, height=1, command=lambda: self._step_font(-1))
        self.smaller_button.pack(side="left", padx=(0, 6))
        self.larger_button = FlatButton(sizes, text="A+", quiet=True, height=1, command=lambda: self._step_font(1))
        self.larger_button.pack(side="left")
        self._sync_font_buttons()

    def _step_font(self, by):
        """A- and A+: one size smaller or larger, between 6 and 16."""
        try:
            size = int(self.font_var.get())
        except ValueError:
            size = getattr(engine, "TABLE_FONT_SIZE", 9)
        self.font_var.set(str(max(6, min(16, size + by))))
        self._sync_font_buttons()

    def _sync_font_buttons(self):
        """A- greys out at the smallest size, A+ at the largest."""
        try:
            size = int(self.font_var.get())
        except ValueError:
            return
        self.smaller_button.config(state="disabled" if size <= 6 else "normal")
        self.larger_button.config(state="disabled" if size >= 16 else "normal")

    def _on_session_picked(self, _event=None):
        """A session picked by hand stays chosen; until then Discover follows the latest session."""
        self._session_picked = True
        self.session_menu.selection_clear()
        self.refresh()

    def _on_filter_changed(self, _event=None):
        self.filter_var.set(self._filter_names.get(self.filter_menu.get(), "misses"))
        self.filter_menu.selection_clear()
        self.refresh()

    def _build_table(self):
        wrap = tk.Frame(self, padx=22, pady=8)
        wrap.pack(fill="both", expand=True)

        cols = ("tick", "seed", "artist", "track", "sources", "found", "date")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="browse")
        self._apply_table_font()
        headings = {"tick": "", "seed": t("Seed"), "artist": t("Artist"), "track": t("Track"),
                    "sources": t("Suggested by"), "found": t("In library"), "date": t("When")}
        widths = {"tick": self._tick_width, "seed": 160, "artist": 140, "track": 150, "sources": 120,
                  "found": 65, "date": 100}
        for c in cols:
            if c == "tick":   # the tick box column: click a box (or press Space) to tick a row
                self.tree.heading(c, text=headings[c])
                self.tree.column(c, width=widths[c], minwidth=widths[c], stretch=False, anchor="center")
                continue
            self.tree.heading(c, text=headings[c], command=lambda cc=c: self._sort_by(cc))
            self.tree.column(c, width=widths[c], anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._sync_site_buttons())
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", lambda e: self._toggle_selected())

        btnbar = tk.Frame(self, padx=22, pady=8)
        btnbar.pack(fill="x")

        # One row: the site buttons on the left, Refresh and CSV pinned right.
        # Only if the site buttons can't fit do they drop to a second row.
        self._bar_top = tk.Frame(btnbar)
        self._bar_top.pack(fill="x")
        self._bar_left = tk.Frame(self._bar_top)
        self._bar_left.pack(side="left")

        self._bar_right = tk.Frame(self._bar_top)
        self._bar_right.pack(side="right")
        FlatButton(self._bar_right, text="CSV", quiet=True, height=1, command=self.export_csv).pack(side="right")
        FlatButton(self._bar_right, text=t("Refresh"), quiet=True, height=1,
                   command=self.refresh).pack(side="right", padx=(0, 8))
        FlatButton(self._bar_right, text=t("Select None"), quiet=True, height=1,
                   command=self.select_none).pack(side="right", padx=(0, 8))
        self._select_all_button = FlatButton(self._bar_right, text=t("Select All"), quiet=True, height=1,
                                             command=self.select_all)
        self._select_all_button.pack(side="right", padx=(0, 4))
        # Appears once a row is ticked; the status line beside it says how the last playlist went
        self._yt_button = FlatButton(self._bar_right, text=t("Create YouTube Playlist"), quiet=True, height=1,
                                     command=self.create_youtube_playlist)
        self._tidal_button = FlatButton(self._bar_right, text=t("Create Tidal Playlist"), quiet=True, height=1,
                                        command=self.create_tidal_playlist)
        # After a Tidal playlist is filled: links to open it, until the next thing the status line says
        self._tidal_open = tk.Frame(self._bar_right)
        self._tidal_open_pid = None
        # Clear all always shows, at the far left of the group; Clear selected appears with the ticks
        FlatButton(self._bar_right, text=t("Clear All"), quiet=True, height=1,
                   command=self.clear_all).pack(side="right", padx=(0, 16))
        self._clear_sel_button = FlatButton(self._bar_right, text=t("Clear Selected"), quiet=True, height=1,
                                            command=self.clear_selected)
        self._yt_note = ""   # how the last YouTube playlist went, shown after the row count
        self._last_view = None

        self._sites_inline = tk.Frame(self._bar_top)   # the site buttons, when they fit on the row
        self._sites_inline.pack(side="left")
        self._sites_below = tk.Frame(btnbar)           # ...or here, as a second row, when they don't
        self._site_buttons = []
        self._label_button = None
        self._label_busy = False
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
        labels = [t("All sessions")]
        self._session_ids = [None]
        for sid, started, mode, artist, track in self.sessions:
            seed = artist or "?"
            if track:
                seed += f" - {track}"
            labels.append(f"{short_started(started)}  {seed}")
            self._session_ids.append(sid)
        self.session_menu.config(values=labels)
        # Until you pick one, Discover opens on the latest session (All sessions stays first in the list)
        if not getattr(self, "_session_picked", False) or self.session_var.get() not in labels:
            self.session_var.set(labels[1] if len(labels) > 1 else t("All sessions"))

    def refresh(self):
        self._reload_sessions()
        engine.load_settings()   # pick up DIGITAL_STORES, REFERENCE_SITES and TABLE_FONT_SIZE
        self._apply_table_font()
        self._rebuild_site_buttons()

        f = self.filter_var.get()
        found = None if f == "all" else (f == "hits")
        idx = self.session_menu.current()
        session_id = self._session_ids[idx] if 0 <= idx < len(self._session_ids) else None

        # Ticks survive Refresh; a different session or Misses/Hits/All starts clean
        view = (f, session_id)
        keep = ({self._row_key(r) for r in self._rows if r.get("_ticked")}
                if view == self._last_view else set())
        self._last_view = view
        self._rows = engine.list_discoveries(found=found, session_id=session_id)
        for r in self._rows:
            r["_ticked"] = self._row_key(r) in keep
        self._populate()

    def _sites_text(self):
        labels = dict(engine.STORE_OPTIONS + engine.REFERENCE_OPTIONS)
        stores = [labels.get(c, c) for c in engine.DIGITAL_STORES]
        refs = [labels.get(c, c) for c in engine.REFERENCE_SITES]
        text = t("Search:") + " " + ", ".join(stores)
        if refs:
            text += "  +  " + ", ".join(refs)
        return text

    def _seed_text(self, r):
        seed = r.get("seed_artist") or "?"
        if r.get("seed_track"):
            seed += f" - {r['seed_track']}"
        if r.get("seed"):   # a Playing Now build: the sampled track this row came from
            seed = r["seed"]
        return seed

    def _populate(self):
        term = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        self.tree.delete(*self.tree.get_children())
        self._visible = []
        for i, r in enumerate(self._rows):
            seed = self._seed_text(r)
            found = t("yes") if r["found"] else t("no")
            haystack = " ".join([seed, r["artist"] or "", r["track"] or "",
                                 r["sources"] or "", found, r["date"] or ""]).lower()
            if term and term not in haystack:
                continue
            self.tree.insert("", "end", iid=str(i), values=(
                self._tick_mark(r), seed, r["artist"], r["track"] or "", r["sources"] or "", found, r["date"]),
                tags=("cell",))
            self._visible.append((seed, r["artist"] or "", r["track"] or "",
                                  r["sources"] or "", found, r["date"] or ""))
        self._show_count()
        self._sync_site_buttons()
        self._sync_ticks()

    def export_csv(self):
        if not getattr(self, "_visible", None):
            messagebox.showinfo(t("Nothing to export"), t("No rows are shown."), parent=self)
            return
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".csv",
            filetypes=[(t("CSV files"), "*.csv")], initialfile="24bit7_discoveries.csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([t("Seed"), t("Artist"), t("Track"), t("Suggested by"), t("In library"), t("When")])
                w.writerows(self._visible)
        except Exception as e:
            messagebox.showerror(t("Export failed"), str(e), parent=self)
            return
        messagebox.showinfo(t("Exported"), tn("Saved {count} row to\n{path}", "Saved {count} rows to\n{path}",
                                              len(self._visible), path=path), parent=self)

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

    # --- ticks and the YouTube playlist ---------------------------------------

    @staticmethod
    def _row_key(r):
        return r.get("session_id"), r.get("artist"), r.get("track")

    @staticmethod
    def _tick_mark(r):
        return "\u2611" if r.get("_ticked") else "\u2610"

    def _on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell" and self.tree.identify_column(event.x) == "#1":
            iid = self.tree.identify_row(event.y)
            if iid:
                self._toggle(iid)

    def _toggle_selected(self):
        for iid in self.tree.selection():
            self._toggle(iid)
        return "break"

    def _toggle(self, iid):
        row = self._rows[int(iid)]
        row["_ticked"] = not row.get("_ticked")
        self.tree.set(iid, "tick", self._tick_mark(row))
        self._sync_ticks()

    def select_all(self):
        """Ticks the rows currently shown (after the Misses/Hits/All filter and the search box)."""
        for iid in self.tree.get_children():
            self._rows[int(iid)]["_ticked"] = True
            self.tree.set(iid, "tick", self._tick_mark(self._rows[int(iid)]))
        self._sync_ticks()

    def select_none(self):
        for r in self._rows:
            r["_ticked"] = False
        for iid in self.tree.get_children():
            self.tree.set(iid, "tick", self._tick_mark(self._rows[int(iid)]))
        self._sync_ticks()

    def _sync_ticks(self):
        """
        While any row is ticked: a Create Playlist button for each service ticked under
        Settings > Discover > Create Playlist, then Clear Selected.
        """
        count = sum(1 for r in getattr(self, "_rows", []) if r.get("_ticked"))
        sites = getattr(engine, "PLAYLIST_SITES", ["youtube"])
        wanted = ([b for code, b in (("youtube", self._yt_button), ("tidal", self._tidal_button)) if code in sites]
                  + [self._clear_sel_button]) if count else []
        shown = [b for b in (self._yt_button, self._tidal_button, self._clear_sel_button) if b.winfo_manager()]
        if shown != wanted:   # repacked only when the set changes, so ticking rows doesn't flicker
            for b in shown:
                b.pack_forget()
            after = self._select_all_button
            for b in wanted:
                b.pack(side="right", padx=(0, 8), after=after)
                after = b
        self._clear_sel_button.config(text=f"{t('Clear Selected')} ({count})")
        if str(self._yt_button.cget("state")) != "disabled":
            self._yt_button.config(text=f"{t('Create YouTube Playlist')} ({count})")
        if str(self._tidal_button.cget("state")) != "disabled":
            self._tidal_button.config(text=f"{t('Create Tidal Playlist')} ({count})")
        self._place_site_buttons()

    def create_tidal_playlist(self):
        """Puts the ticked tracks (in table order) into the Tidal playlist called 24bit7, in place of what was there."""
        ticked = [r for r in self._rows if r.get("_ticked")]
        pairs = [(r["artist"], r["track"]) for r in ticked if r.get("artist") and r.get("track")]
        if not pairs:
            self._set_yt_status(t("None of the ticked rows has a track to look up."))
            return
        if not engine.tidal_signed_in():
            self._set_yt_status(t("Sign in to Tidal first: Settings > Keys, Sign In to Tidal."))
            return
        self._tidal_button.config(state="disabled", text=t("Looking up on Tidal..."))
        self._set_yt_status("")

        def work():
            said = []
            try:
                ids = engine.tidal_ids_for_pairs(pairs)
                sent = engine.send_to_tidal([i for i in ids if i], report=said.append) if any(ids) else 0
            except Exception as e:
                ids, sent, said = [], 0, [t("Problem: Tidal lookup failed ({error}).", error=e)]
            self.after(0, lambda: self._tidal_done(pairs, ids, sent, said))
        threading.Thread(target=work, daemon=True).start()

    def _tidal_done(self, pairs, ids, sent, said):
        self._tidal_button.config(state="normal")
        self._sync_ticks()
        if not sent:
            problem = next((line for line in said if line.startswith("Problem:")), "")
            self._set_yt_status(problem.replace("Problem: ", "", 1) if problem
                                else t("None of the ticked tracks were found on Tidal."))
            return
        missing = len(pairs) - len([i for i in ids if i])
        if missing:
            text = t('{sent} of {total} in your Tidal playlist "{name}", {missing} not found on Tidal.',
                     sent=sent, total=len(pairs), name=engine.TIDAL_PLAYLIST_NAME, missing=missing)
        else:
            text = t('{sent} of {total} in your Tidal playlist "{name}".',
                     sent=sent, total=len(pairs), name=engine.TIDAL_PLAYLIST_NAME)
        if any("Tidal app isn't installed" in line for line in said):   # engine's English line, until stage 3
            text += " " + t("The Tidal app isn't installed, so it opened on Tidal's website.")
        self._set_yt_status(text)
        self._show_tidal_open(engine.TIDAL_PLAYLIST_ID)

    def _show_tidal_open(self, pid):
        """Open in Tidal app (when it's installed) and Open in Tidal web, beside the status line."""
        for w in self._tidal_open.winfo_children():
            w.destroy()
        self._tidal_open_pid = pid
        if not pid:
            self._tidal_open.pack_forget()
            return
        app_url, web_url = engine.tidal_open_links(pid)
        opened = getattr(engine, "TIDAL_OPENED", None)   # the playlist has just opened there: offer the other
        links = ([(t("Open in Tidal app"), app_url)] if engine.tidal_app_installed() and opened != "app" else []) + (
            [(t("Open in Tidal web"), web_url)] if opened != "web" else [])
        for n, (text, url) in enumerate(links):
            if n:
                tk.Label(self._tidal_open, text="·").pack(side="left", padx=4)
            link = tk.Label(self._tidal_open, text=text, fg=PALETTE["link"], cursor="hand2",
                            font=("Segoe UI", 9, "underline"))
            link.pack(side="left")
            link.bind("<Button-1>", lambda e, u=url: self._open_tidal(u))
        self._tidal_open.pack(side="left", padx=(0, 12), before=self._bar_right.winfo_children()[0])

    def _open_tidal(self, url):
        try:
            if url.startswith("tidal:"):
                os.startfile(url)   # the Tidal app, straight to the playlist
            else:
                webbrowser.open(url)
        except OSError as e:
            messagebox.showerror("Tidal", t("Couldn't open Tidal ({error}).", error=e), parent=self)

    def create_youtube_playlist(self):
        """Looks the ticked tracks up on YouTube (in table order) and opens them as an instant playlist."""
        ticked = [r for r in self._rows if r.get("_ticked")]
        pairs = [(r["artist"], r["track"]) for r in ticked if r.get("artist") and r.get("track")]
        if not pairs:
            self._set_yt_status(t("None of the ticked rows has a track to look up."))
            return
        over = max(0, len(pairs) - engine.YOUTUBE_PLAYLIST_MAX)
        pairs = pairs[:engine.YOUTUBE_PLAYLIST_MAX]
        self._yt_button.config(state="disabled", text=t("Looking up on YouTube..."))
        self._set_yt_status("")

        def work():
            try:
                ids = engine.youtube_ids_for_pairs(pairs)
            except Exception as e:
                ids, error = [], e
            else:
                error = None
            self.after(0, lambda: self._youtube_done(pairs, ids, over, error))
        threading.Thread(target=work, daemon=True).start()

    def _youtube_done(self, pairs, ids, over, error):
        self._yt_button.config(state="normal")
        self._sync_ticks()
        if error is not None:
            self._set_yt_status(t("YouTube lookup failed: {error}", error=error))
            return
        found = list(dict.fromkeys(v for v in ids if v))
        if not found:
            self._set_yt_status(t("None of the ticked tracks were found on YouTube."))
            return
        webbrowser.open("https://www.youtube.com/watch_videos?video_ids=" + ",".join(found))
        missing = len(pairs) - len(found)
        if missing:
            text = t("Opened {found} of {total}, {missing} not found on YouTube.",
                     found=len(found), total=len(pairs), missing=missing)
        else:
            text = t("Opened {found} of {total}.", found=len(found), total=len(pairs))
        if over:
            text += " " + t("YouTube takes {most} at most, so {over} more were left out.",
                            most=engine.YOUTUBE_PLAYLIST_MAX, over=over)
        self._set_yt_status(text)

    def clear_all(self):
        if not messagebox.askyesno(
                t("Clear all history"),
                t("Are you sure? This will clear your whole Discover history, every session.\n\n"
                  "It can't be undone."),
                icon="warning", default="no", parent=self):
            return
        removed = engine.clear_discoveries()
        self._rows = []
        self.session_var.set(t("All sessions"))
        self.refresh()
        self._set_yt_status(tn("History cleared ({count} row).", "History cleared ({count} rows).", removed))

    def clear_selected(self):
        ticked = [r for r in self._rows if r.get("_ticked")]
        if not ticked:
            return
        if not messagebox.askyesno(
                t("Clear selected"),
                tn("Are you sure? This will clear the {count} ticked row from your Discover history.\n\n"
                   "It can't be undone.",
                   "Are you sure? This will clear the {count} ticked rows from your Discover history.\n\n"
                   "It can't be undone.", len(ticked)),
                icon="warning", default="no", parent=self):
            return
        removed = engine.clear_discoveries([r.get("id") for r in ticked])
        for r in self._rows:
            r["_ticked"] = False
        self.refresh()
        self._set_yt_status(tn("Cleared {count} row.", "Cleared {count} rows.", removed))

    def _set_yt_status(self, text):
        self._yt_note = text
        if getattr(self, "_tidal_open_pid", None):   # the Open in Tidal links belong to the last message only
            self._show_tidal_open(None)
        self._show_count()

    def _show_count(self):
        """The row count at the top right, followed by how the last YouTube playlist went."""
        text = t("{count} shown", count=len(getattr(self, '_visible', [])))
        self.count_label.config(text=f"{self._yt_note}    {text}" if self._yt_note else text)

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
        show_label = os.getenv("DISCOVER_LABEL", "1").strip().lower() in ("1", "true", "yes")
        signature = ([(label, kind) for label, kind, _ in sites] + [s.get("url") for s in getattr(engine, "CUSTOM_SITES", [])]
                     + [show_label])
        if signature == self._site_signature and not force:
            self._sync_site_buttons()
            return
        self._site_signature = signature
        for b in self._site_buttons:
            b.destroy()
        parent = self._sites_inline if self._site_mode == "inline" else self._sites_below
        self._site_buttons = []
        self._label_button = None
        if show_label:   # Settings > Discover > Reference > Record Label
            self._label_button = FlatButton(parent, text=t("Finding label...") if self._label_busy else t("Label"),
                                            quiet=True, height=1,
                                           command=self.find_label)
            self._label_button.pack(side="left", padx=(0, 12))
            self._site_buttons.append(self._label_button)
        for label, kind, builder in sites:
            b = FlatButton(parent, text=label, quiet=True, height=1,
                           command=lambda k=kind, f=builder: self.open_site(k, f))
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
            b.config(state="disabled" if b is self._label_button and self._label_busy else state)

    def find_label(self):
        """Finds the selected track's label in the background, then opens it on Bandcamp."""
        sel = self.tree.selection()
        if not sel or self._label_busy:
            return
        row = self._rows[int(sel[0])]
        artist, track = (row.get("artist") or "").strip(), (row.get("track") or "").strip()
        if not artist or not track:
            self._set_yt_status(t("Label needs a row with both an artist and a track."))
            return
        key = f"{engine.artist_key(artist)}|{engine.clean_name(track)}"
        cached = engine.cache_get("24bit7", "label", key)
        if cached:
            self._open_label(artist, track, cached)
            return
        self._label_busy = True
        self._label_button.config(text=t("Finding label..."), state="disabled")
        self._set_yt_status(t("Finding the label for {artist} - {track}...", artist=artist, track=track))

        def work():
            try:
                result, error = engine.find_label(artist, track), None
            except Exception as e:
                result, error = None, e
            self.after(0, lambda: self._label_done(artist, track, key, result, error))
        threading.Thread(target=work, daemon=True).start()

    def _label_done(self, artist, track, key, result, error):
        self._label_busy = False
        try:
            self._label_button.config(text=t("Label"))
        except (tk.TclError, AttributeError):   # gone, or switched off in Settings meanwhile
            pass
        self._sync_site_buttons()
        if error is not None:
            self._set_yt_status(t("Label lookup failed: {error}", error=error))
            return
        if result.get("label") is not None:   # a label (or self-released) is kept; "not found" is tried again next time
            engine.cache_put("24bit7", "label", key, result)
        self._open_label(artist, track, result)

    def _open_label(self, artist, track, result):
        url, note = engine.label_page(artist, track, result)
        self._set_yt_status(note + ".")
        webbrowser.open_new_tab(url)

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
