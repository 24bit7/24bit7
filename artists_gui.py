"""
24bit7 - Discover's Missing Artists and Gaps in Your Artists tabs (Ben, 10 and 11 Nov 2026).

What the history says across builds, from discover_stats, one view a tab beside Sessions: artists the sources
keep naming that you don't own, and songs you don't have by artists you do. Narrowed by Genre (Radio's
stations), Period and Zone (with who asked), which both tabs share, and Sound (the artists' own Last.fm tags),
which each keeps for itself. A row opens underneath: who points to the artist, the songs named, and the same
store and reference buttons as Sessions. (A third view, Sources, was dropped on 11 Nov 2026: nothing on it led
anywhere.)

The numbers are worked out on a thread (the library may need reading), and the first time the tab is shown
Last.fm is asked, in the background, for the tags of artists not yet known, after which Sound fills in.
"""

import os
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.parse
import webbrowser
from tkinter import ttk

import engine
import discover_stats as ds
import tabs
from i18n import t, tn, N_
from tabs import PALETTE, FlatButton, TCombobox

ALL_GENRES = N_("All genres")
ALL_ZONES = N_("All zones")
NOT_KNOWN = N_("Not known")
SOUNDS_SHOWN = 12   # chips before "and N more"
PAD = 24   # room around a column's title, for the edges and the sort arrow

COLUMNS = {   # view -> [(column, heading, width, numbers)]
    "Missing Artists": [("artist", N_("Artist"), 200, False), ("yours", N_("Your Artists"), 100, True),
                        ("builds", N_("Builds"), 70, True), ("sound", N_("Sound"), 260, False)],
    "Gaps in Your Artists": [("artist", N_("Artist"), 200, False), ("matched", N_("Matched"), 80, True),
                             ("missed", N_("Missed"), 80, True), ("songs", N_("Songs You Don't Have"), 320, False)],
}


def number_width(title, values, head, cell):
    """
    A number column's width (Ben, 11 Nov 2026): its title in the heading font or its widest number, whichever
    is wider, plus room either side. Measured with the fonts on screen, so it holds at any display scaling,
    table text size or language: fixed pixel widths cut "Your Artists" to "Your /" on a screen scaled up.
    """
    return max([head(title)] + [cell(str(v)) for v in values]) + PAD


class Shared:
    """What the two tabs share: Genre, Period and Zone, and whether Last.fm has been asked for tags yet."""

    def __init__(self):
        self.period = "All time"
        self.zone = None
        self.station_id = None
        self.fetched = False


def _list(names, most=3):
    """'a, b, c and four more', for the opened row."""
    names = list(names)
    shown = ", ".join(names[:most])
    if len(names) > most:
        shown += " " + t("and {count} more", count=len(names) - most)
    return shown


class ArtistsView(tk.Frame):
    def __init__(self, master, kind, shared, sites=None):
        super().__init__(master)
        self._sites = sites or (lambda: [])   # Discover's site list: [(label, "track" or "artist", url builder)]
        self.kind = kind     # "Missing Artists" or "Gaps in Your Artists"
        self.shared = shared
        self.sound = None    # each tab its own: the two lists hold different artists
        self.result = None
        self._items = []
        self._sort = (None, False)
        self._busy = 0          # a newer request supersedes an older one still working
        self.ready = False
        self._fetching = False
        self._all_sounds = False
        self._inbox = queue.Queue()   # results from the worker threads, picked up on Tk's own thread
        self._polling = None
        self._label_busy = False
        self._build()

    # --- layout ------------------------------------------------------------

    def _build(self):
        bar = tk.Frame(self, padx=22)
        bar.pack(fill="x", pady=(14, 0))
        tk.Label(bar, text=t("Genre:")).pack(side="left")
        self.genre_menu = ttk.Combobox(bar, state="readonly", width=34)
        self.genre_menu.pack(side="left", padx=(4, 14))
        self.genre_menu.bind("<<ComboboxSelected>>", self._genre_picked)
        self._genre_ids = [None]
        tk.Label(bar, text=t("Period:")).pack(side="left")
        self.period_var = tk.StringVar(value="All time")
        self.period_menu = TCombobox(bar, textvariable=self.period_var, values=ds.PERIODS, state="readonly", width=15)
        self.period_menu.pack(side="left", padx=(4, 14))
        self.period_menu.bind("<<ComboboxSelected>>", self._period_picked)
        tk.Label(bar, text=t("Zone:")).pack(side="left")
        self.zone_menu = ttk.Combobox(bar, state="readonly", width=36)
        self.zone_menu.pack(side="left", padx=(4, 0), fill="x", expand=True)
        self.zone_menu.bind("<<ComboboxSelected>>", self._zone_picked)
        self._zone_values = [None]

        self._sound_row = tk.Frame(self, padx=22)
        self._sound_row.pack(fill="x", pady=(10, 0))
        self._sound_title = tk.Label(self._sound_row, text=t("Sound:"))
        self._sound_title.pack(side="left", anchor="n")
        self.chips = tk.Frame(self._sound_row)
        self.chips.pack(side="left", fill="x", expand=True, padx=(6, 0))
        tabs.flow(self.chips, gap=6, within=self._sound_row)

        # the count, with Refresh at its right above the table's corner (Ben, 13 Nov 2026)
        line = tk.Frame(self, padx=22)
        line.pack(fill="x", pady=(8, 0))
        self.count_label = tk.Label(line, text=t("Loading..."), fg=PALETTE["text_muted"], anchor="w")
        self.count_label.pack(side="left", fill="x", expand=True)
        self.refresh_button = FlatButton(line, text=t("Refresh"), width=10, height=1, command=self.reload)
        self.refresh_button.pack(side="right")
        from settings_gui import Tooltip
        note = Tooltip(self.refresh_button, "")
        note.when = lambda: bool(setattr(note, "text", self._refresh_note()) or True)
        self._reloading = False

        wrap = tk.Frame(self, padx=22, pady=8)
        wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(wrap, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._open_row())

        self.opened = tk.Frame(self, padx=22)
        self.opened.pack(fill="x", pady=(0, 10))
        self._open_lines = tk.Frame(self.opened)
        self._open_lines.pack(fill="x")
        self._open_buttons = tk.Frame(self.opened)
        self._open_buttons.pack(fill="x", pady=(6, 0))
        self._set_columns()

    def _set_columns(self):
        cols = COLUMNS[self.kind]
        self.tree.configure(columns=[c for c, _h, _w, _n in cols])
        size = getattr(engine, "TABLE_FONT_SIZE", 9)
        self._cell_font = ("Segoe UI", size)
        self._head_measure = tkfont.Font(self, family="Segoe UI", size=size, weight="bold").measure
        self._cell_measure = tkfont.Font(self, family="Segoe UI", size=size).measure
        self.tree.tag_configure("cell", font=self._cell_font)
        for c, heading, width, numbers in cols:
            title = t(heading)
            # a title sits over its column's contents: centred over numbers, at the left over text (Ben, 11 Nov 2026)
            self.tree.heading(c, text=title, anchor="center" if numbers else "w",
                              command=lambda cc=c: self._sort_by(cc))
            fits = self._head_measure(title) + PAD
            if numbers:   # as wide as the title needs, the number centred under it
                self.tree.column(c, width=fits, minwidth=fits, anchor="center", stretch=False)
            else:         # Artist fits its names (see _fit_columns); the last column takes the rest
                self.tree.column(c, width=max(width, fits), minwidth=fits, anchor="w", stretch=c != "artist")

    def _fit_columns(self, rows):
        """
        A number column widens if one of its numbers is wider than its title. Artist is as wide as its longest
        name, never narrower than its title nor wider than a third of the table, so Sound or the songs get the
        room (Ben, 11 Nov 2026: the Artist column was far wider than its names).
        """
        for n, (c, heading, _w, numbers) in enumerate(COLUMNS[self.kind]):
            title = t(heading)
            if numbers:
                fits = number_width(title, [r[n] for r in rows], self._head_measure, self._cell_measure)
                self.tree.column(c, width=fits, minwidth=fits)
            elif c == "artist":
                least = self._head_measure(title) + PAD
                widest = max([self._cell_measure(str(r[n])) for r in rows], default=0) + PAD
                room = self.tree.winfo_width()
                most = room // 3 if room > 1 else widest
                self.tree.column(c, width=max(least, min(widest, most)), minwidth=least)

    def restyle(self):
        """A new table text size (Sessions' A- and A+): measured again and the rows put back."""
        self._set_columns()
        if self._items:
            self._populate()

    # --- choices -----------------------------------------------------------

    def _genre_picked(self, _e=None):
        i = self.genre_menu.current()
        self.shared.station_id = self._genre_ids[i] if 0 <= i < len(self._genre_ids) else None
        self.sound = None
        self.genre_menu.selection_clear()
        self.refresh()

    def _zone_picked(self, _e=None):
        i = self.zone_menu.current()
        self.shared.zone = self._zone_values[i] if 0 <= i < len(self._zone_values) else None
        self.zone_menu.selection_clear()
        self.refresh()

    def _period_picked(self, _e=None):
        self.shared.period = self.period_var.get()
        self.period_menu.selection_clear()
        self.refresh()

    def pick_sound(self, key):
        self.sound = None if key == self.sound else key
        self.refresh()

    # --- data --------------------------------------------------------------

    @staticmethod
    def _refresh_note():
        """Refresh's hover note, with the time the library was last read (Ben: in the note, not on the line)."""
        import time
        import library
        note = t("Reads your library from JRiver again, so artists and songs you've added since drop off the list. "
                 "24bit7 also does this every thirty minutes.")
        if library._loaded_at:
            note += " " + t("Last read at {time}.", time=time.strftime("%H:%M", time.localtime(library._loaded_at)))
        return note

    def reload(self):
        """Refresh: reads the library from JRiver now, on a thread, then works the list out again."""
        if self._reloading:
            return
        self._reloading = True
        self.refresh_button.config(state="disabled")
        self.count_label.config(text=t("Reading your library from JRiver..."))

        def work():
            import library
            try:
                library.load()
                error = None
            except Exception as e:
                error = e
            self._inbox.put(lambda: self._reloaded(error))
        threading.Thread(target=work, daemon=True).start()
        self.ready = False
        if self._polling is None:
            self._poll()

    def _reloaded(self, error):
        self._reloading = False
        if not self.winfo_exists():
            return
        self.refresh_button.config(state="normal")
        if error is not None:
            self.ready = True
            self.count_label.config(text=t("Couldn't read your library from JRiver ({error}).", error=error))
            return
        self.refresh()

    def refresh(self):
        """Works the numbers out on a thread, then shows them; the first time, also asks Last.fm for tags."""
        self._busy += 1
        self.ready = False   # until these numbers are shown (the tests wait on it)
        ticket = self._busy
        if self.period_var.get() != self.shared.period:   # the other tab may have changed it
            self.period_var.set(self.shared.period)
        choice = (self.kind, self.shared.period, self.shared.zone, self.shared.station_id, self.sound)
        self.count_label.config(text=t("Working it out..."))

        def work():
            try:
                result = ds.build(*choice)
                extra = self._extras(*choice[:3])
                error = None
            except Exception as e:
                result, extra, error = None, None, e
            self._inbox.put(lambda: self._done(ticket, result, extra, error))
        threading.Thread(target=work, daemon=True).start()
        if self._polling is None:
            self._poll()

    def _poll(self):
        """
        Runs what the worker threads have finished, on Tk's thread. A thread never calls Tk itself: that needs
        the main loop running, which the screenshots and the tests drive by hand.
        """
        self._polling = None
        try:
            while True:
                self._inbox.get_nowait()()
        except queue.Empty:
            pass
        if not self.winfo_exists():
            return
        if (not self.ready or self._fetching or self._label_busy or self._reloading) and self._polling is None:
            self._polling = self.after(50, self._poll)   # (a refresh run above may have started one already)

    @staticmethod
    def _extras(kind, period, zone):
        """
        The drop-downs' lists, worked out with the numbers on the worker thread (so from the choice as it was,
        never from Tk): stations with a count each, zones with who asked.
        """
        tops, why = ds.stations()
        counts = {}
        if tops:
            view = ds.rows(period, zone)
            items = ds.missing_artists(view) if kind == "Missing Artists" else ds.gaps(view)
            station = ds.station_finder()
            for x in tops:
                counts[x["id"]] = len(ds.in_station(kind, items, view, x["id"], station))
        return {"stations": tops, "why": why, "counts": counts, "zones": ds.zones()}

    def _done(self, ticket, result, extra, error):
        if ticket != self._busy or not self.winfo_exists():
            return
        if error is not None:
            self.count_label.config(text=t("Couldn't work the numbers out ({error}).", error=error))
            engine.debug(f"Discover {self.kind}: {error!r}")
            return
        self.result = result
        self.ready = True
        self._fill_menus(extra)
        self._fill_sounds()
        self._items = list(result["items"])
        self._apply_sort()
        self._populate()
        self._say_count()
        if not self.shared.fetched:
            self.shared.fetched = True
            self._fetch_tags()

    def _fill_menus(self, extra):
        tops = extra["stations"]
        labels = [t(ALL_GENRES)]
        self._genre_ids = [None]
        for x in tops:
            n = extra["counts"].get(x["id"])
            labels.append(f"{x['name']} ({n})" if n is not None else x["name"])
            self._genre_ids.append(x["id"])
        self.genre_menu.config(values=labels)
        if self.shared.station_id not in self._genre_ids:
            self.shared.station_id = None
        self.genre_menu.current(self._genre_ids.index(self.shared.station_id))
        self.genre_menu.config(state="readonly" if tops else "disabled")
        self._genre_why = t(extra["why"]) if extra["why"] else ""
        self._note(self.genre_menu, self._genre_why)

        labels, self._zone_values = [t(ALL_ZONES)], [None]
        for zone, asked in extra["zones"]:
            who = ", ".join(t(a) for a, _n in asked.most_common() if a)
            name = zone or t(NOT_KNOWN)
            labels.append(f"{name} ({who})" if who else name)
            self._zone_values.append(zone)
        self.zone_menu.config(values=labels)
        if self.shared.zone not in self._zone_values:
            self.shared.zone = None
        self.zone_menu.current(self._zone_values.index(self.shared.zone))

    def _note(self, widget, text):
        """A hover note saying why a control is greyed (or none)."""
        from settings_gui import Tooltip
        old = getattr(widget, "_tooltip", None)
        if old is not None:
            old.text = text
            old.when = lambda: bool(old.text)
        elif text:
            note = Tooltip(widget, text)
            note.when = lambda: bool(note.text)

    def _fill_sounds(self):
        for w in self.chips.winfo_children():
            w.destroy()
        result = self.result or {}
        listed = result.get("sounds") or []
        muted = PALETTE["text_muted"]
        if self._fetching:
            tk.Label(self.chips, text=t("Asking Last.fm for the artists' tags..."), fg=muted).pack(side="left")
        elif not listed:
            tk.Label(self.chips, text=t("No sound is shared by three or more of these artists."),
                     fg=muted).pack(side="left")
        else:
            shown = listed if self._all_sounds else listed[:SOUNDS_SHOWN]
            if self.sound and self.sound not in [k for k, *_r in shown]:
                shown = shown + [x for x in listed if x[0] == self.sound]
            for key, name, count, broad in shown:
                on = key == self.sound
                chip = tk.Label(self.chips, text=f"{name}  {count}", padx=7, pady=1, cursor="hand2",
                                highlightthickness=1,
                                highlightbackground=PALETTE["button_fg"] if on else PALETTE["line"],
                                fg=PALETTE["button_fg"] if on else (muted if broad else PALETTE.get("text", "#000000")))
                chip.pack(side="left")
                chip.bind("<Button-1>", lambda e, k=key: self.pick_sound(k))
                chip.sound_key = key
            if len(listed) > SOUNDS_SHOWN:
                more = tk.Label(self.chips, cursor="hand2", fg=PALETTE["link"], font=("Segoe UI", 9, "underline"),
                                text=t("Fewer") if self._all_sounds
                                else t("and {count} more", count=len(listed) - SOUNDS_SHOWN))
                more.pack(side="left")
                more.bind("<Button-1>", lambda e: self._toggle_sounds())
        self.chips.after_idle(self.chips.reflow)

    def _toggle_sounds(self):
        self._all_sounds = not self._all_sounds
        self._fill_sounds()

    def _say_count(self):
        r = self.result
        n = len(self._items)
        station = (r.get("station") or {}).get("name")
        if self.kind == "Missing Artists":
            if station:
                text = tn("{count} artist you don't own, pointed to by your {station} artists.",
                          "{count} artists you don't own, pointed to by your {station} artists.", n, station=station)
            else:
                text = tn("{count} artist you don't own, from {builds} builds.",
                          "{count} artists you don't own, from {builds} builds.", n, builds=r["builds"])
        else:
            text = tn("{count} artist you own was named, in {builds} builds.",
                      "{count} artists you own were named, in {builds} builds.", n, builds=r["builds"])
        if r.get("untagged"):
            text += " " + tn("{count} has no tags to go by.", "{count} have no tags to go by.", r["untagged"])
        self.count_label.config(text=text)

    def _fetch_tags(self):
        """Last.fm's tags for the artists in the history not yet known, in the background; Sound fills in after."""
        names = set()
        for r in ds.rows():
            names.add(r["artist"])
            if r["seed_artist"]:
                names.add(r["seed_artist"])
        todo = ds.untagged(sorted(names), ds.tag_cache())
        if not todo or not engine.LASTFM_KEY:
            return
        self._fetching = True
        self._fill_sounds()

        def work():
            try:
                ds.fetch_tags(todo, cancelled=lambda: not self.winfo_exists())
            except Exception as e:
                engine.debug(f"Discover: tags ({e!r})")
            self._inbox.put(self._fetched_tags)
        threading.Thread(target=work, daemon=True).start()
        if self._polling is None:
            self._poll()

    def _fetched_tags(self):
        self._fetching = False
        if self.winfo_exists():
            self.refresh()

    # --- the table ---------------------------------------------------------

    def _cells(self, item):
        if self.kind == "Missing Artists":
            sounds = ", ".join(name for _k, name in ds.sounds_of(item["artist"], self._cache())[:2])
            return item["artist"], len(item["yours"]), len(item["builds"]), sounds
        return item["artist"], item["matched"], len(item["missed"]), ", ".join(item["missed"])

    def _cache(self):
        if getattr(self, "_cache_for", None) is not self.result:
            self._cache_for, self._tags = self.result, ds.tag_cache()
        return self._tags

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        rows = [self._cells(item) for item in self._items]
        self.tree.tag_configure("stripe", background=tabs.stripe_colour())
        for i, row in enumerate(rows):
            self.tree.insert("", "end", iid=str(i), values=row, tags=("cell", "stripe") if i % 2 else ("cell",))
        self._fit_columns(rows)
        self._open_row()

    def _sort_value(self, item, col):
        if col == "artist":
            return (item.get(col) or "").lower()
        value = item.get(col)
        if col == "songs":
            value = len(item["missed"])
        return len(value) if isinstance(value, (set, list, dict)) else (value or 0)

    def _apply_sort(self):
        col, reverse = self._sort
        if col is None:   # the view's own order: most first
            return
        self._items.sort(key=lambda x: self._sort_value(x, col), reverse=reverse)

    def _sort_by(self, col):
        col0, reverse = self._sort
        numbers = col != "artist"
        self._sort = (col, (not reverse) if col == col0 else numbers)   # numbers start most first
        self._apply_sort()
        self._populate()

    # --- the opened row ----------------------------------------------------

    def selected(self):
        sel = self.tree.selection()
        return self._items[int(sel[0])] if sel and int(sel[0]) < len(self._items) else None

    def _open_row(self):
        for w in self._open_lines.winfo_children() + self._open_buttons.winfo_children():
            w.destroy()
        item = self.selected()
        if item is None:
            return
        muted = PALETTE["text_muted"]

        def line(label, text):
            row = tk.Frame(self._open_lines)
            row.pack(fill="x", anchor="w")
            tk.Label(row, text=label, fg=muted).pack(side="left")
            tk.Label(row, text=text, anchor="w", justify="left", wraplength=900).pack(side="left", padx=(6, 0))

        if self.kind == "Missing Artists":
            yours = sorted(item["yours"].values(), key=str.lower)
            if yours:
                line(t("{artist} is on the lists of", artist=item["artist"]), _list(yours, 8))
            songs = [s for s, _n in item["songs"].most_common()]
            if songs:
                line(t("Songs named"), _list(songs))
            track = songs[0] if songs else ""
        else:
            if item["missed"]:
                line(t("Songs you don't have"), _list(item["missed"], 8))
            track = item["missed"][0] if item["missed"] else ""
        if track and os.getenv("DISCOVER_LABEL", "1").strip().lower() in ("1", "true", "yes"):
            self._label_button = FlatButton(self._open_buttons, text=t("Label"), quiet=True, height=1,
                                            command=lambda: self._find_label(item["artist"], track))
            self._label_button.pack(side="left", padx=(0, 12))
        for label, kind, builder in self._sites():
            FlatButton(self._open_buttons, text=label, quiet=True, height=1,
                       command=lambda k=kind, f=builder: self._open_site(item["artist"], track, k, f)).pack(
                side="left", padx=(0, 6))

    @staticmethod
    def _open_site(artist, track, kind, builder):
        terms = artist
        if kind == "track" and track:
            terms += f" {track}"
        webbrowser.open_new_tab(builder(urllib.parse.quote_plus(terms)))

    def _find_label(self, artist, track):
        """Who released the row's most named song, opened on Bandcamp, as the Label button in Sessions does."""
        key = f"{engine.artist_key(artist)}|{engine.clean_name(track)}"
        cached = engine.cache_get("24bit7", "label", key)
        if cached:
            self._open_label(artist, track, cached)
            return
        button = self._label_button
        button.config(text=t("Finding label..."), state="disabled")

        def work():
            try:
                result, error = engine.find_label(artist, track), None
            except Exception as e:
                result, error = None, e
            self._inbox.put(lambda: self._label_done(button, artist, track, key, result, error))
        self._label_busy = True
        threading.Thread(target=work, daemon=True).start()
        if self._polling is None:
            self._poll()

    def _label_done(self, button, artist, track, key, result, error):
        self._label_busy = False
        try:
            button.config(text=t("Label"), state="normal")
        except tk.TclError:   # the row was closed meanwhile
            pass
        if error is not None:
            self.count_label.config(text=t("Label lookup failed: {error}", error=error))
            return
        if result.get("label") is not None:
            engine.cache_put("24bit7", "label", key, result)
        self._open_label(artist, track, result)

    def _open_label(self, artist, track, result):
        url, note = engine.label_page(artist, track, result)
        self.count_label.config(text=note + ".")
        webbrowser.open_new_tab(url)
