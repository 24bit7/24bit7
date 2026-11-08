"""
24bit7 - Edit Pillars (Ben, 7 Nov 2026): Edit on a station's row in Radio's Stations section opens this.
The station's pillars on the left (search, Remove), every artist in your library on the right (search,
+ Add, with how many tracks you own), Restore Pillars, Close. Saved as you go, like renaming a station;
radio.py keeps the edits by the station's genre path, so a Re-analyse keeps them.
"""

import tkinter as tk
from tkinter import ttk

import engine
import radio
import tabs
from i18n import t, tn
from tabs import PALETTE, PromptWindow, RoundedEntry

FEW_TRACKS = 5   # fewer owned than this: "few tracks" beside the artist, as a round takes a few of a pillar's songs


def _list_colours():
    if tabs.THEME == "dark":
        return (PALETTE.get("field_bg") or "#2a2c30", PALETTE.get("text") or "#e8e8e8",
                getattr(tabs, "MATRIX_HI", "#3a4a5a"))
    return PALETTE.get("field_bg") or "#ffffff", PALETTE.get("field_fg") or "#1a1a1a", "#cfe0f7"


class PillarsWindow(PromptWindow):
    """The station's pillars and your library side by side. .changed() runs after every change."""

    ok_text = "Close"

    def __init__(self, parent, lane_id, changed=None):
        self.lane_id = lane_id
        self.changed = changed or (lambda: None)
        station = radio.lane(lane_id) or {"name": "", "pillars": []}
        self.station_name = station["name"]
        self.library = radio.library_artists()
        super().__init__(parent, t("Pillar Artists: {station}", station=station["name"]))
        self.cancel_button.pack_forget()
        self.bind("<Return>", self._enter)
        self.refresh()

    def _body(self, inner, bg, fg):
        px = self._px
        muted = PALETTE.get("text_muted") or "#666666"
        tk.Label(inner, text=t("Each round of this station starts from three of its pillars at random and finds the "
                               "artists they agree on. Your changes are kept when the stations are made again."),
                 font=("Segoe UI", 9), bg=bg, fg=muted, justify="left", anchor="w",
                 wraplength=px(640)).pack(anchor="w", pady=(0, px(10)))
        cols = tk.Frame(inner, bg=bg)
        cols.pack(fill="both", expand=True)
        self.left = self._column(cols, bg, fg, 0, t("Search the pillars"), t("Remove"), self.remove)
        self.right = self._column(cols, bg, fg, 1, t("Search your artists"), t("+ Add"), self.add)
        self.pillar_head = self.left["head"]
        self.right["head"].config(text=t("Add From Your Library"))
        foot = tk.Frame(inner, bg=bg)
        foot.pack(fill="x", pady=(px(8), 0))
        self.message = tk.Label(foot, text="", font=("Segoe UI", 9), bg=bg, fg=muted, anchor="w", justify="left",
                                wraplength=px(640))
        self.message.pack(anchor="w")
        row = tk.Frame(inner, bg=bg)
        row.pack(fill="x", pady=(px(10), 0))
        self.restore_button = self._button(row, t("Restore Pillars"), self.restore,
                                           PALETTE.get("field_bg") or PALETTE["button_bg"], PALETTE["line"])
        self.restore_button.pack(side="left")
        self.left["list"].bind("<Double-Button-1>", lambda e: self.remove())
        self.right["list"].bind("<Double-Button-1>", lambda e: self.add())
        for col in (self.left, self.right):
            col["search"].bind("<KeyRelease>", lambda e: self.refresh())

    def _column(self, parent, bg, fg, column, hint, action, command):
        px = self._px
        fbg, ffg, hi = _list_colours()
        frame = tk.Frame(parent, bg=bg)
        frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else px(18), 0))
        head = tk.Label(frame, text="", font=("Segoe UI", 10, "bold"), bg=bg, fg=PALETTE["section_fg"], anchor="w")
        head.pack(anchor="w", pady=(0, px(6)))
        search = RoundedEntry(frame, width=34, font=("Segoe UI", 10), placeholder=hint)
        search.pack(fill="x", pady=(0, px(6)))
        holder = tk.Frame(frame, bg=fbg, highlightthickness=1, highlightbackground=PALETTE["line"])
        holder.pack(fill="both", expand=True)
        lb = tk.Listbox(holder, height=16, width=38, activestyle="none", exportselection=False, bg=fbg, fg=ffg,
                        selectbackground=hi, selectforeground=ffg, highlightthickness=0, bd=0, font=("Segoe UI", 10))
        bar = ttk.Scrollbar(holder, orient="vertical", command=lb.yview)
        lb.config(yscrollcommand=bar.set)
        lb.pack(side="left", fill="both", expand=True, padx=(px(4), 0), pady=px(2))
        bar.pack(side="left", fill="y")
        button = self._button(frame, action, command, PALETTE.get("field_bg") or PALETTE["button_bg"],
                              PALETTE["line"])
        button.pack(anchor="w", pady=(px(6), 0))
        return {"head": head, "search": search, "list": lb, "items": [], "button": button}

    # --- what's shown ----------------------------------------------------------------------------

    def station(self):
        return radio.lane(self.lane_id)

    def refresh(self):
        station = self.station()
        if station is None:
            self.message.config(text=t("That station has gone since the stations were made again."))
            return
        muted = PALETTE.get("text_muted") or "#666666"
        pillars = list(station.get("pillars") or [])
        mine = radio.added(station)
        self.pillar_head.config(text=t("Pillars ({count})", count=len(pillars)))
        q = self.left["search"].get().strip().lower()
        lb, items = self.left["list"], self.left["items"]
        lb.delete(0, "end")
        items.clear()
        for name in pillars:
            if q and q not in name.lower():
                continue
            lb.insert("end", name + ("   " + t("added by you") if engine.artist_key(name) in mine else ""))
            items.append(name)
        q = self.right["search"].get().strip().lower()
        have = {engine.artist_key(n) for n in pillars}
        lb, items = self.right["list"], self.right["items"]
        lb.delete(0, "end")
        items.clear()
        for name, count in self.library:
            if q and q not in name.lower():
                continue
            tracks = tn("{count} track", "{count} tracks", count)
            if count < FEW_TRACKS:
                tracks += ", " + t("few tracks")
            pillar = engine.artist_key(name) in have
            lb.insert("end", f"{name}   {tracks}" + ("   " + t("a pillar") if pillar else ""))
            if pillar:
                lb.itemconfig("end", fg=muted)
            items.append(name)
            if len(items) >= 500 and not q:   # a big library: type to find the rest
                lb.insert("end", t("Type to search the rest of your artists."))
                lb.itemconfig("end", fg=muted)
                items.append(None)
                break
        edited = radio.edited(station)
        self.restore_button.config(cursor="hand2" if edited else "", fg=PALETTE["button_fg"] if edited else muted)

    def _picked(self, col):
        sel = col["list"].curselection()
        if not sel or sel[0] >= len(col["items"]):
            return None
        return col["items"][sel[0]]

    # --- changes ---------------------------------------------------------------------------------

    def _done(self, line):
        self.message.config(text=line)
        self.refresh()
        try:
            self.changed()
        except tk.TclError:
            pass

    def remove(self, name=None):
        name = name or self._picked(self.left)
        if not name:
            return
        problem = radio.remove_pillar(self.lane_id, name)
        if problem:
            self.message.config(text=problem)
            return
        self._done(t("{artist} is no longer a pillar of {station} or its halves.", artist=name,
                     station=self.station_name))

    def add(self, name=None):
        name = name or self._picked(self.right)
        station = self.station()
        if not name or station is None:
            return
        if engine.artist_key(name) in {engine.artist_key(n) for n in station.get("pillars") or []}:
            self.message.config(text=t("{artist} is already a pillar.", artist=name))
            return
        problem = radio.add_pillar(self.lane_id, name)
        if problem:
            self.message.config(text=problem)
            return
        self._done(t("{artist} is a pillar of {station}.", artist=name, station=self.station_name))

    def restore(self):
        station = self.station()
        if station is None or not radio.edited(station):
            return
        radio.restore_pillars(self.lane_id)
        self._done(t("{station} has the analysis's own pillars again.", station=self.station_name))

    def _enter(self, _event=None):
        """Enter in the library's search adds the artist picked, or the only one found; never closes."""
        focus = self.focus_get()
        if focus is not None and str(focus).startswith(str(self.right["search"])):
            items = [n for n in self.right["items"] if n]
            if self._picked(self.right) or len(items) == 1:
                self.add(self._picked(self.right) or items[0])


def open_for(parent, lane_id, changed=None):
    """Opens Edit Pillars for a station over parent's window. Returns the window."""
    return PillarsWindow(parent, lane_id, changed)
