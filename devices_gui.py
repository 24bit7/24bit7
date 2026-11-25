"""
The Devices tab (Ben, 25 Nov 2026, as drawn: mockups/devices_and_hits.html). It appears after Settings while a
phone answers, plugged in over USB or with the 24bit7 app open on the WiFi, and goes once none does (Presence);
no setting. A read again that finds the folder as it was leaves the rows alone, so clicking the tab doesn't jitter.

At the top, every device 24bit7 knows, a green dot for one answering now and a grey one for one that isn't, then
+ Add a Phone Over WiFi. Under it the chosen device's folder, Rename and Forget (which never touches the phone),
and what the folder holds against the limit and the free space. Then two lists side by side: Albums (artist and
album folders, with a box to add an artist, album or track from the library, copied straight in) and Playlists
(what Save put there, each opening to its songs). Tick and Delete: the amber line says what goes, so there's no
further question. Open Folder is hidden for a phone on WiFi, since Explorer can't reach it.

Every read, add and delete runs on one worker thread, a job at a time (a phone takes seconds), handing its news
back through a queue the tab reads; the window is never touched from the thread.
"""

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import engine
import library
import phone
import tabs
from i18n import t, tn
from tabs import PALETTE, FlatButton, RoundedEntry

SHOWN = 6   # suggestions of each kind under the library box
WATCH_EVERY = 30   # seconds between looks for a phone answering (phone.present)
SEARCH_EVERY = 300   # seconds between looks across the whole home network (a phone given a new address)
SEARCH_FRESH = 30    # opening the tab searches the network again unless it was searched this recently


class Presence:
    """
    Whether the Devices tab is in the strip (Ben, 25 Nov 2026: only "when 24bit7 detects an open phone", a phone
    plugged in over USB counting too). A thread asks phone.present() every WATCH_EVERY seconds; the tab is added
    while a phone answers and taken away when none does, but never from under you: while you're on it, it waits
    until you leave. Save's Open Devices shows it whatever answers (show). The page is kept, not destroyed, so
    what it last read is there when it comes back.
    """

    def __init__(self, nb, tab, placed=None):
        self.nb, self.tab, self.placed = nb, tab, placed
        self.on = False
        self.asking = []       # phones the last look couldn't tell (phone.asking)
        self.waiting = False   # nothing answers, but the tab is showing: it goes once you leave it
        self._wake = None
        self._search = False    # search_now: the next look searches the whole network
        self.searched = None    # when the network was last searched (time.monotonic), None before the first
        self._stop = threading.Event()   # the window's gone: the looking stops
        nb.bind("<<NotebookTabChanged>>", lambda e: self.left(), add="+")
        tab.bind("<Destroy>", lambda e: self._stop.set() if e.widget is tab else None, add="+")

    def show(self):
        self.waiting = False
        if self.on:
            return
        self.on = True
        self.nb.add(self.tab, text=t("Devices"))
        self._placed()

    def answered(self, ids, asking=()):
        """The latest look: the ids of the phones answering, and the phones it needs to ask about (phone.asking),
        which bring the tab up too, as the question is on it. With Settings > Other > Devices Off, nothing brings it
        up by itself (engine.DEVICES_TAB)."""
        self.asking = list(asking)
        if hasattr(self.tab, "set_asking"):
            self.tab.set_asking(self.asking)
        if (ids or asking) and engine.DEVICES_TAB:
            self.show()
        elif self.on:
            if self.nb.select() == str(self.tab):
                self.waiting = True
            else:
                self._hide()

    def left(self):
        if self.waiting and self.nb.select() != str(self.tab):
            self._hide()

    def _hide(self):
        self.waiting = self.on = False
        self.nb.remove(self.tab, keep=True)
        self._placed()

    def _placed(self):
        if self.placed is not None:
            self.tab.after(50, self.placed)

    def watch(self, every=WATCH_EVERY, search_every=SEARCH_EVERY):
        """The looking, on a thread of its own (a WiFi phone takes a second or so to answer, or not). The whole home
        network is searched on the first look and then every search_every seconds (phone.present's search)."""
        found, self._wake = queue.Queue(), threading.Event()

        def look():
            phone.com_begin()
            try:
                while not self._stop.is_set():
                    due = (self._search or self.searched is None
                           or time.monotonic() - self.searched >= search_every)
                    self._search = False
                    try:
                        ids = phone.present(search=True) if due else phone.present()
                        if due:
                            self.searched = time.monotonic()
                        found.put((ids, phone.asking()))
                    except Exception as e:
                        engine.debug(f"Devices: couldn't look for phones ({e})")
                    self._wake.wait(every)
                    self._wake.clear()
            finally:
                phone.com_end()
        threading.Thread(target=look, daemon=True, name="devices-watch").start()

        def check():
            if self._stop.is_set():
                return
            latest = None
            while not found.empty():
                latest = found.get_nowait()
            if latest is not None:
                self.answered(*latest)
            self.tab.after(1000 if every >= 1 else 100, check)
        self.tab.after(500 if every >= 1 else 50, check)

    def poke(self):
        """Look now (a copy has just gone to a phone)."""
        if self._wake is not None:
            self._wake.set()

    def search_now(self, older_than=0):
        """Search the whole network now, not at the next five-minute mark (Ben, 25 Nov 2026: after Forget, a phone
        still answering waited up to five minutes to be asked about). older_than: only if the last search is older."""
        if self.searched is not None and time.monotonic() - self.searched < older_than:
            return
        self._search = True
        self.poke()

    def stop(self):
        self._stop.set()
        self.poke()


def _looks(f):
    """What a folder's lists are drawn from: its files and sizes, and each playlist's songs."""
    return (f.folder, tuple(sorted((k, v["size"]) for k, v in f.files.items())),
            tuple((pl["low"], tuple(pl["paths"])) for pl in f.playlists))


def _scale(widget):
    try:
        s = max(1.0, widget.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        s = 1.0
    return lambda n: max(1, int(round(n * s))) if n else 0


class _List(tk.Frame):
    """A scrolled list of rows (a grid in a frame on a canvas), the wheel working over any of its rows."""

    def __init__(self, master, height):
        super().__init__(master, bg=PALETTE["line"], padx=1, pady=1)
        px = _scale(self)
        self.field = master.cget("bg")
        self.canvas = tk.Canvas(self, height=px(height), bg=self.field, highlightthickness=0, bd=0, width=px(300))
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rows = tk.Frame(self.canvas, bg=self.field)
        self._id = self.canvas.create_window(0, 0, window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._id, width=e.width))
        self._tag = f"DevicesWheel{id(self)}"
        self.bind_class(self._tag, "<MouseWheel>", self._wheel)
        self.rows.columnconfigure(1, weight=1)

    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def clear(self):
        for w in self.rows.winfo_children():
            w.destroy()

    def wheel_everywhere(self):
        todo = [self.canvas, self.rows]
        while todo:
            w = todo.pop()
            if self._tag not in w.bindtags():
                w.bindtags((self._tag,) + w.bindtags())
            todo += w.winfo_children()


class DevicesTab(tk.Frame):
    LIST_HEIGHT = 360

    def __init__(self, master, log=print, add_wifi=None):
        super().__init__(master)
        self._log, self._add_wifi = log, add_wifi
        self._px = _scale(self)
        self.devices = []             # [(device id, model, kind, here)] from phone.known()
        self.current = None           # the device id shown
        self.answering = {}           # device id: True, False or None (not asked yet)
        self.contents = {}            # device id: phone.Folder last read (shown greyed while it isn't answering)
        self.free = {}                # device id: bytes free when last read
        self.problem = {}             # device id: why the last read failed
        self.ticked, self.opened = set(), set()
        self.tick_for = {}            # the row's key: its tick, as last drawn
        self.adding = {}              # artist folder (lower): [done, count] while an add runs
        self.busy = False
        self._due = False   # the page waits for the first read of a device (one draw, not two)
        self.sorting = {}   # device id: (files moved, files to move) while the one-off sort runs (phone.arrange)
        self._jobs, self._news = queue.Queue(), queue.Queue()
        self._poll = None
        self._worker = None
        self._pop = None
        self._counts = {}
        self._on_screen = None        # (device id, _looks of the folder, live) the lists were last drawn from, so a
                                      # read again that finds the same leaves the rows alone (no jitter on a click)
        self.asking = []              # phone.asking(): the phones to ask about
        self.ask_problem = {}         # address: why the code given didn't do
        self._build()
        self.bind("<Destroy>", self._gone, add="+")

    # --- the layout ---------------------------------------------------------------------------------------

    def _build(self):
        px = self._px
        bg = self.cget("bg")
        fg = PALETTE.get("text") or "#000000"
        self._bg, self._fg = bg, fg
        outer = tk.Frame(self, bg=bg)
        outer.pack(fill="both", expand=True, padx=px(16), pady=px(12))
        self.chips = tk.Frame(outer, bg=bg)
        self.chips.pack(anchor="w", fill="x")
        self.ask_box = tk.Frame(outer, bg=bg)   # the phones 24bit7 can't tell, one question each (set_asking)
        self.ask_box.pack(anchor="w", fill="x")
        info = tk.Frame(outer, bg=bg)
        info.pack(anchor="w", fill="x", pady=(px(10), 0))
        tk.Label(info, text=t("Folder"), font=("Segoe UI", 10), bg=bg, fg=fg).pack(side="left")
        self.folder_label = tk.Label(info, text="", font=("Segoe UI", 10, "bold"), bg=bg, fg=fg)
        self.folder_label.pack(side="left", padx=(px(8), px(16)))
        self.rename_link = self._link(info, t("Rename"), self._rename)
        self.rename_link.pack(side="left")
        self.forget_link = self._link(info, t("Forget"), self._forget)
        self.forget_link.pack(side="left", padx=(px(12), 0))
        # a WiFi phone that isn't answering: its code typed again reconnects it (Ben, 25 Nov 2026: Forget and add
        # again was the only way, and Forget is the wrong tool for it)
        self.code_link = self._link(info, t("Type Its Code..."), self._type_code)
        self.meter_label = tk.Label(outer, text="", font=("Segoe UI", 9), bg=bg, fg=PALETTE["help_fg"], anchor="w")
        self.meter_label.pack(anchor="w", pady=(px(8), 0))
        self.bar = tk.Canvas(outer, height=px(6), bg=PALETTE["line"], highlightthickness=0, bd=0)
        self.bar.pack(anchor="w", fill="x", pady=(px(4), 0))
        self.bar.bind("<Configure>", lambda e: self._meter())
        self.status = tk.Label(outer, text="", font=("Segoe UI", 10), bg=bg, fg=PALETTE["amber"], anchor="w",
                               justify="left")
        self.status.pack(anchor="w", pady=(px(6), 0))
        cols = tk.Frame(outer, bg=bg)
        cols.pack(fill="both", expand=True, pady=(px(8), 0))
        cols.columnconfigure(0, weight=1, uniform="cols")
        cols.columnconfigure(1, weight=1, uniform="cols")
        cols.rowconfigure(0, weight=1)
        left = tk.Frame(cols, bg=bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
        right = tk.Frame(cols, bg=bg)
        right.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))
        self.albums_head = self._heading(left, t("Albums"))
        self.find_box = RoundedEntry(left, width=34, font=("Segoe UI", 10),
                                     placeholder=t("Add an artist, album or track"))
        self.find_box.pack(anchor="w", pady=(px(4), px(6)))
        self.find_box.entry.bind("<KeyRelease>", lambda e: self._suggest(), add="+")
        self.find_box.entry.bind("<FocusOut>", lambda e: self.after(200, self._close_pop_if_away), add="+")
        self.find_box.entry.bind("<Escape>", lambda e: self._close_pop(), add="+")
        self.albums = _List(left, self.LIST_HEIGHT)
        self.albums.pack(fill="both", expand=True)
        self.lists_head = self._heading(right, t("Playlists"))
        self.albums_note = tk.Label(right, text=t("Playlists come from Save on the Play tab. Here you can take one "
                                                  "off, or take songs out of one."),
                                    font=("Segoe UI", 9), bg=bg, fg=PALETTE["help_fg"], anchor="w", justify="left")
        self.albums_note.pack(anchor="w", fill="x", pady=(px(4), px(6)))
        self.albums_note.bind("<Configure>", lambda e: self.albums_note.config(wraplength=max(px(200), e.width)))
        self.lists = _List(right, self.LIST_HEIGHT)
        self.lists.pack(fill="both", expand=True)
        foot = tk.Frame(outer, bg=bg)
        foot.pack(fill="x", pady=(px(8), 0))
        self.note = tk.Label(foot, text="", font=("Segoe UI", 9), bg=bg, fg=PALETTE["help_fg"], anchor="w",
                             justify="left")
        self.note.pack(side="left", fill="x", expand=True)
        self.delete_button = FlatButton(foot, text=t("Delete"), command=self.delete, text_fg=PALETTE["red"])
        self.delete_button.pack(side="right")
        self.open_button = FlatButton(foot, text=t("Open Folder"), command=self._open_folder, quiet=True)
        self.open_button.pack(side="right", padx=(0, px(8)))
        self.note.bind("<Configure>", lambda e: self.note.config(wraplength=max(px(200), e.width)))

    def _link(self, parent, text, command):
        link = tk.Label(parent, text=text, font=("Segoe UI", 9, "underline"), bg=parent.cget("bg"),
                        fg=PALETTE["button_fg"], cursor="hand2")
        link.bind("<Button-1>", lambda e: command())
        return link

    def _heading(self, parent, text):
        row = tk.Frame(parent, bg=self._bg)
        row.pack(anchor="w", fill="x")
        tk.Label(row, text=text.upper(), font=("Segoe UI", 9, "bold"), bg=self._bg,
                 fg=PALETTE["help_fg"]).pack(side="left")
        small = tk.Label(row, text="", font=("Segoe UI", 9), bg=self._bg, fg=PALETTE["help_fg"])
        small.pack(side="left", padx=(self._px(8), 0))
        return small

    # --- the worker ---------------------------------------------------------------------------------------

    def _gone(self, event):
        if event.widget is self and self._poll:
            try:
                self.after_cancel(self._poll)
            except tk.TclError:
                pass
            self._poll = None

    def _job(self, *job):
        self._jobs.put(job)
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._work, daemon=True, name="devices")
            self._worker.start()
        if self._poll is None:
            self._poll = self.after(120, self._read_news)

    def _work(self):
        phone.com_begin()
        try:
            while True:
                try:
                    job = self._jobs.get(timeout=1.5)
                except queue.Empty:
                    return
                try:
                    self._run(job)
                except Exception as e:   # a job's own failure is said; the next job still runs
                    engine.debug(f"Devices: {job[0]}: {e}")
                    self._news.put(("failed", job[1] if len(job) > 1 else None, str(e)))
        finally:
            phone.com_end()

    def _settings(self, device_id):
        model = next((m for d, m, _k, _h in self.devices if d == device_id), "")
        return phone.settings(device_id, model), model

    def _run(self, job):
        kind = job[0]
        if kind == "scan":
            self._news.put(("devices", phone.known()))
            return
        if kind == "reconnect":
            _, device_id, code = job
            key = phone.reconnect(phone.key_for(device_id), code)
            self._news.put(("claimed", None, key, device_id) if key else
                           ("failed", device_id, t("No phone answered to that code. Check the 24bit7 app is open "
                                                   "on it, on the same WiFi as this PC.")))
            return
        if kind == "claim":
            _, address, code, as_key = job
            self._news.put(("claimed", address, phone.claim(address, code, as_key=as_key), as_key))
            return
        device_id = job[1]
        s, _model = self._settings(device_id)
        say = self._log
        try:
            p = phone.open_device(device_id, s["name"])
        except Exception as e:
            self._news.put(("away", device_id, str(e)))
            return
        try:
            if device_id == phone.PC:
                p.root = s["folder"] if s["folder"] and os.path.isdir(s["folder"]) else None
            if kind == "delete":
                f = phone.Folder(p, s["folder"])
                f.delete(f.plan(**job[2]), say=say)
            elif kind == "add":
                what, keys, folder_key = job[2], job[3], job[4]
                tracks = phone.tracks_for(keys)
                if not tracks:
                    say(t("Problem: none of {what}'s files could be found, so nothing was copied.", what=what))
                else:
                    say(t("Adding {what} to {phone}...", what=what, phone=s["name"]))
                    phone.add_albums(p, s["folder"], tracks, say=say, what=what,
                                     progress=lambda n: self._news.put(("adding", device_id, folder_key, n)))
                self._news.put(("added", device_id, folder_key))
            elif kind == "read" and (device_id != phone.PC or p.root):
                phone.arrange(p, s["folder"], say=say,   # what 1.43 left, sorted the first time it's opened
                              progress=lambda done, count: self._news.put(("sorting", device_id, done, count)))
            f = phone.Folder(p, s["folder"])
            try:
                free = p.free()
            except Exception:
                free = None
            self._news.put(("read", device_id, f, free))
        finally:
            p.close()

    def _read_news(self):
        self._poll = None
        try:
            while True:
                news = self._news.get_nowait()
                self._take(news)
        except queue.Empty:
            pass
        if not self._jobs.empty() or (self._worker is not None and self._worker.is_alive()):
            self._poll = self.after(150, self._read_news)
        else:
            self.busy = False
            self._sync_note()

    def _take(self, news):
        kind = news[0]
        if kind == "devices":
            before = (list(self.devices), dict(self.answering), self.current)
            self.devices = news[1]
            ids = [d for d, *_ in self.devices]
            if self.current not in ids:
                last = phone.last_device()
                keys = [phone.key_for(d) for d in ids]
                self.current = ids[keys.index(phone.key_for(last))] if last and phone.key_for(last) in keys else \
                    (ids[0] if ids else None)
            for d, _m, _k, here in self.devices:
                if here is not None:
                    self.answering[d] = here
            if self.current is not None:
                self._job("read", self.current)
            first = self.current is not None and self.current not in self.contents
            # the same devices: nothing redrawn; a device not read yet waits for its read (or its "away"), so the
            # first open draws once rather than an empty page and then the lists (Ben, 25 Nov 2026: "jittery")
            if (self.devices, self.answering, self.current) != before:
                self._chips()   # every device at once, a new one included (Jo's Phone, 25 Nov 2026)
                if first and self._on_screen is None and not self.albums.rows.winfo_children():
                    self._due = True   # nothing on the page yet: it's drawn with the read
                    self.status.config(text=self._reading(self.current), fg=PALETTE["help_fg"])
                else:
                    self.draw()
        elif kind == "read":
            _, device_id, f, free = news
            same = (self.answering.get(device_id) is True and device_id not in self.problem
                    and device_id == self.current and self._on_screen == (device_id, _looks(f), True))
            was = self.answering.get(device_id)
            self.answering[device_id], self.contents[device_id], self.free[device_id] = True, f, free
            self.sorting.pop(device_id, None)
            self.problem.pop(device_id, None)
            if device_id == self.current:
                self.ticked = {k for k in self.ticked if self._exists(k)}
            if same:   # read again and nothing has changed (the tab clicked): only the free space can have moved
                self._show_meter(device_id, f)
                return
            if was is not True or self._due:
                self._due = False
                self._chips()
            self.draw()
        elif kind == "away":
            _, device_id, why = news
            changed = self.answering.get(device_id) is not False or self.problem.get(device_id) != why
            self.answering[device_id], self.problem[device_id] = False, why
            self.sorting.pop(device_id, None)
            if changed or self._due:
                self._due = False
                self._chips()
                self.draw()
        elif kind == "adding":
            _, device_id, folder_key, n = news
            self.adding[folder_key] = [n.get("done", 0), n.get("count", 0)]
            if device_id == self.current:
                self.draw()
        elif kind == "added":
            self.adding.pop(news[2], None)
        elif kind == "claimed":
            _, address, key, as_key = news
            if key is None and address is not None:
                self.ask_problem[address] = t("That code isn't right. It's the four digits on the phone's screen.")
                self._ask_rows()
                return
            self.ask_problem.pop(address, None)
            self.asking = [a for a in self.asking if a["address"] != address]
            self.answering.pop(as_key, None)
            self.problem.pop(as_key, None)
            self._ask_rows()
            if as_key is None:
                model = phone.settings(key, "")["name"]
                name = tabs.ask_name(self, t("New Phone"), t("A name for this phone, so you can tell it from others:"),
                                     initial=model)
                if name and name.strip():
                    phone.remember_quietly(key, name=name.strip())
                self._log(t("Added {phone}.", phone=phone.settings(key, "")["name"]))
            else:
                self._log(t("{phone} is answering again.", phone=phone.settings(key, "")["name"]))
            self.current = key
            self._job("scan")
        elif kind == "sorting":
            _, device_id, done, count = news
            self.sorting[device_id] = (done, count)
            if device_id == self.current:
                self.status.config(text=self._reading(device_id), fg=PALETTE["help_fg"])
        elif kind == "failed":
            device_id = news[1]
            self._log(t("Problem: {e}", e=news[2]))
            if device_id is not None:
                self.problem[device_id] = news[2]
                self.sorting.pop(device_id, None)
            self._due = False
            self._chips()   # a read that failed still shows every device
            self.draw()

    # --- what's shown --------------------------------------------------------------------------------------

    def shown(self):
        """The tab brought forward: the devices looked for again, and the one chosen read again; the network searched
        too, unless it was in the last SEARCH_FRESH seconds."""
        self._job("scan")
        presence = getattr(self, "presence", None)
        if presence is not None:
            presence.search_now(older_than=SEARCH_FRESH)

    def show_device(self, device_id):
        """Save's Open Devices: the device to show when the tab comes forward (shown() reads it)."""
        keys = {phone.key_for(d): d for d, *_ in self.devices}
        self.current = keys.get(phone.key_for(device_id), device_id)
        self.ticked, self.opened = set(), set()

    def _chips(self):
        px = self._px
        for w in self.chips.winfo_children():
            w.destroy()
        for device_id, model, kind, _here in self.devices:
            s = phone.settings(device_id, model)
            on = self.answering.get(device_id)
            chosen = device_id == self.current
            back = PALETTE.get("field_bg") if chosen else self._bg
            chip = tk.Frame(self.chips, bg=PALETTE["button_fg"] if chosen else PALETTE["line"], padx=1, pady=1)
            chip.pack(side="left", padx=(0, px(8)))
            inner = tk.Frame(chip, bg=back, padx=px(10), pady=px(4), cursor="hand2")
            inner.pack()
            dot = tk.Canvas(inner, width=px(10), height=px(10), bg=back, highlightthickness=0, bd=0)
            dot.create_oval(1, 1, px(9), px(9), width=0,
                            fill=PALETTE["go"] if on else PALETTE.get("text_faint") or PALETTE["help_fg"])
            dot.pack(side="left", padx=(0, px(6)))
            tk.Label(inner, text=s["name"], font=("Segoe UI", 10, "bold" if chosen else "normal"), bg=back,
                     fg=self._fg).pack(side="left")
            how = (t("This PC") if kind == "pc" else t("WiFi") if kind == "wifi" else t("USB")) if on is not False \
                else (t("not found") if kind == "wifi" else t("not plugged in"))
            if kind != "pc" or s["name"] != t("This PC"):
                tk.Label(inner, text=how, font=("Segoe UI", 9), bg=back, fg=PALETTE["help_fg"]
                         ).pack(side="left", padx=(px(6), 0))
            for w in (chip, inner, *inner.winfo_children()):
                w.bind("<Button-1>", lambda e, d=device_id: self.pick(d))
        if self._add_wifi is not None:
            self._link(self.chips, t("+ Add a Phone Over WiFi..."), self._add).pack(side="left", padx=(px(4), 0))

    def set_asking(self, items):
        """The latest look's phones to ask about (phone.asking). Redrawn only when they change, so a code half
        typed isn't wiped by the next look."""
        if [a["address"] for a in items] == [a["address"] for a in self.asking]:
            return
        self.asking = [dict(a) for a in items]
        self._ask_rows()

    def _ask_rows(self):
        """
        A line per phone 24bit7 can't tell (Ben, 25 Nov 2026): a phone it keeps answering with a new code, or one
        it has never seen (reset, a new phone, or one never added), with which phone it is and the code shown on it.
        """
        px = self._px
        for w in self.ask_box.winfo_children():
            w.destroy()
        kept = phone.kept_phones()
        for a in self.asking:
            row = tk.Frame(self.ask_box, bg=self._bg)
            row.pack(anchor="w", fill="x", pady=(px(10), 0))
            if a["known"]:
                name = phone.settings(a["key"], a["model"])["name"]
                text = t("{phone} has a new code. Type the code shown on the phone.", phone=name)
            elif a["model"]:
                text = t("A phone with the 24bit7 app is answering ({model}). Which is it?", model=a["model"])
            else:
                text = t("A phone with the 24bit7 app is answering. Which is it?")
            tk.Label(row, text=text, font=("Segoe UI", 10), bg=self._bg, fg=PALETTE["amber"]).pack(side="left")
            keys = [None]
            if not a["known"]:
                names = [n for _k, n in kept] + [t("A New Phone")]
                keys = [k for k, _n in kept] + [None]
                var = row.var = tk.StringVar(row, value=names[0])   # kept: a variable let go empties the box
                pick = ttk.Combobox(row, textvariable=var, values=names, state="readonly",
                                    width=max(len(n) for n in names) + 1, font=("Segoe UI", 10))
                pick.pack(side="left", padx=(px(8), 0))
            tk.Label(row, text=t("Code"), font=("Segoe UI", 10), bg=self._bg, fg=self._fg
                     ).pack(side="left", padx=(px(12), px(6)))
            box = RoundedEntry(row, width=6, font=("Segoe UI", 10))
            box.pack(side="left")

            def go(a=a, box=box, pick=None if a["known"] else pick, keys=keys):
                as_key = a["key"] if a["known"] else keys[pick.current()] if pick.current() >= 0 else None
                self._job("claim", a["address"], box.get().strip(), as_key)
            box.bind("<Return>", lambda e, go=go: go())
            FlatButton(row, text=t("OK"), command=go, quiet=True).pack(side="left", padx=(px(8), 0))
            if a["address"] in self.ask_problem:
                tk.Label(row, text=self.ask_problem[a["address"]], font=("Segoe UI", 9), bg=self._bg,
                         fg=PALETTE["red"]).pack(side="left", padx=(px(10), 0))

    def pick(self, device_id):
        if device_id == self.current:
            return
        self.current = device_id
        self.ticked, self.opened = set(), set()
        self._chips()
        self.draw()
        self._job("read", device_id)

    def _add(self):
        added = self._add_wifi(self)
        if added:
            self.current = added
            self._job("scan")

    def _rename(self):
        if self.current is None:
            return
        s, _model = self._settings(self.current)
        name = tabs.ask_name(self, t("Rename"), t("A name for this phone, so you can tell it from others:"),
                             initial=s["name"])
        if name and name.strip():
            phone.remember_quietly(phone.key_for(self.current), name=name.strip())
            self._chips()
            self.draw()

    def _forget(self):
        if self.current is None:
            return
        s, _model = self._settings(self.current)
        phone.forget(self.current)
        self._log(t("Forgot {phone}. Nothing on it was touched.", phone=s["name"]))
        self.contents.pop(self.current, None)
        self.answering.pop(self.current, None)
        self.current = None
        self._job("scan")
        self._search_soon()   # a phone still answering is asked about straight away, not in five minutes

    def _search_soon(self):
        presence = getattr(self, "presence", None)
        if presence is not None:
            presence.search_now()

    def _type_code(self):
        """Type Its Code...: the code on the phone's screen, and the phone looked for and reconnected."""
        if self.current is None:
            return
        s, _model = self._settings(self.current)
        code = tabs.ask_name(self, t("Type Its Code"),
                             t("The four-digit code on {phone}'s screen, with the 24bit7 app open:", phone=s["name"]))
        if code and code.strip():
            self.status.config(text=t("Looking for {phone}...", phone=s["name"]), fg=PALETTE["help_fg"])
            self._job("reconnect", self.current, code.strip())

    def _open_folder(self):
        if self.current is None:
            return
        s, model = self._settings(self.current)
        try:
            opened = phone.open_in_explorer(self.current, model, s["folder"])
        except Exception as e:
            engine.debug(f"Open Folder: {e}")
            opened = False
        if not opened:
            self.note.config(text=t("Couldn't open {folder} on it in Explorer. Is it unlocked and set to File "
                                    "Transfer?", folder=s["folder"]), fg=PALETTE["amber"])

    def _meter(self):
        px = self._px
        self.bar.delete("all")
        f = self.contents.get(self.current)
        if f is None or self.current is None:
            return
        s, _model = self._settings(self.current)
        if s["limit_gb"]:
            share = f.size / (s["limit_gb"] * phone.GB)
            w = self.bar.winfo_width()
            self.bar.create_rectangle(0, 0, int(w * min(1.0, share)), px(6), width=0,
                                      fill=PALETTE["go"] if share <= 1 else PALETTE["amber"])

    def draw(self):
        """The folder line, the meter and both lists, from what was read last."""
        device = self.current
        self.tick_for = {}
        if device is None:
            self._on_screen = None
            self.code_link.pack_forget()
            self.folder_label.config(text="")
            self.meter_label.config(text="")
            self.status.config(text=t("Plug in a phone, unlocked and set to File Transfer, or add one over WiFi."),
                               fg=PALETTE["help_fg"])
            self.albums.clear()
            self.lists.clear()
            self._sync_note()
            return
        s, model = self._settings(device)
        kind = next((k for d, _m, k, _h in self.devices if d == device), "usb")
        self.folder_label.config(text=s["folder"] or t("not chosen yet"))
        if device == phone.PC:
            self.rename_link.pack_forget()
        elif not self.rename_link.winfo_manager():
            self.rename_link.pack(side="left", before=self.forget_link)
        if kind == "wifi" and self.answering.get(device) is False:
            if not self.code_link.winfo_manager():
                self.code_link.pack(side="left", padx=(self._px(12), 0))
        else:
            self.code_link.pack_forget()
        if kind == "wifi" or self.answering.get(device) is False:
            self.open_button.pack_forget()
        elif not self.open_button.winfo_manager():
            self.open_button.pack(side="right", padx=(0, self._px(8)))
        f = self.contents.get(device)
        on = self.answering.get(device)
        if on is False:
            self.status.config(text=t("{phone} isn't answering. Open the 24bit7 app on it.", phone=s["name"])
                               if kind == "wifi" else t("{phone} isn't plugged in.", phone=s["name"]),
                               fg=PALETTE["amber"])
        elif f is None or device in self.sorting:
            self.status.config(text=self._reading(device), fg=PALETTE["help_fg"])
        else:
            self.status.config(text="")
        if f is None:
            self._on_screen = None
            self.meter_label.config(text="")
            self.albums.clear()
            self.lists.clear()
            self.albums_head.config(text="")
            self.lists_head.config(text="")
            self._sync_note()
            return
        self._show_meter(device, f)
        live = on is not False
        self._draw_albums(f, live)
        self._draw_lists(f, live)
        self._on_screen = (device, _looks(f), live)
        self._sync_note()

    def _reading(self, device):
        """The line while a device is read: or, the first time a folder from before 1.44 is opened, sorted, with how
        far it's got (a phone over WiFi moves each file by copying it, which takes a while)."""
        s, _model = self._settings(device)
        if device in self.sorting:
            done, count = self.sorting[device]
            return t("Sorting {folder} on {phone} into Albums and Playlists, once: {done} of {count} files moved. "
                     "Keep the 24bit7 app open on it.", folder=s["folder"], phone=s["name"], done=done, count=count)
        return t("Reading {folder} on {phone}...", folder=s["folder"], phone=s["name"])

    def _show_meter(self, device, f):
        s, _model = self._settings(device)
        used = phone.size_text(f.size)
        text = (t("{used} used of your {limit} GB limit", used=used, limit=f"{s['limit_gb']:g}") if s["limit_gb"]
                else t("{used} in {folder}", used=used, folder=s["folder"]))
        if self.free.get(device) is not None:
            text += " · " + t("{free} free on {phone}", free=phone.size_text(self.free[device]), phone=s["name"])
        if self.meter_label.cget("text") != text:
            self.meter_label.config(text=text)
        self._meter()

    def _row(self, lst, key, name, depth, count_text, size, note="", note_fg=None, fold=None, live=True):
        px = self._px
        field = lst.field
        r = lst.rows.grid_size()[1]
        fg = self._fg if live else PALETTE["help_fg"]
        if key is not None:
            covered = self._covered(key)
            var = f"devices_tick_{id(self)}_{id(lst)}_{r}"
            self.tk.globalsetvar(var, "1" if covered or key in self.ticked else "0")
            tick = ttk.Checkbutton(lst.rows, variable=var)
            tick.configure(command=lambda: self._toggle(key, tick.instate(["selected"])))
            if covered or not live:
                tick.state(["disabled"])
            tick.grid(row=r, column=0, sticky="w", padx=(px(6), 0))
            self.tick_for[key] = tick
        cell = tk.Frame(lst.rows, bg=field)
        cell.grid(row=r, column=1, sticky="w", padx=(px(16 * depth), 0), pady=px(1))
        if fold is not None:
            tabs.FoldBox(cell, fold, lambda: self._fold(key)).pack(side="left")
        else:
            tk.Frame(cell, bg=field, width=px(26)).pack(side="left")
        label = tk.Label(cell, text=name, font=("Segoe UI", 10), bg=field, fg=fg, anchor="w")
        label.pack(side="left")
        if fold is not None:
            label.bind("<Button-1>", lambda e: self._fold(key))
            label.config(cursor="hand2")
        if note:
            tk.Label(cell, text=note, font=("Segoe UI", 9), bg=field, fg=note_fg or PALETTE["help_fg"]
                     ).pack(side="left", padx=(px(8), 0))
        tk.Label(lst.rows, text=count_text, font=("Segoe UI", 9), bg=field, fg=PALETTE["help_fg"]
                 ).grid(row=r, column=2, sticky="e", padx=px(8))
        tk.Label(lst.rows, text=phone.size_text(size) if size else "", font=("Segoe UI", 9), bg=field,
                 fg=PALETTE["help_fg"]).grid(row=r, column=3, sticky="e", padx=(0, px(8)))

    def _album_total(self, artist_folder, album_folder):
        if not self._counts:
            try:
                for (album, by), n in library.album_counts().items():
                    key = (phone.safe_name(by or "").lower(), phone.safe_name(album).lower())
                    self._counts[key] = max(n, self._counts.get(key, 0))
            except Exception:
                pass
        return self._counts.get((artist_folder.lower(), album_folder.lower()))

    def _draw_albums(self, f, live):
        lst = self.albums
        lst.clear()
        tree = f.tree()
        albums = sum(len([c for c in n["children"] if c["kind"] == "folder"]) or 1
                     for n in tree if n["kind"] == "folder")
        size = sum(n["size"] for n in tree)
        self.albums_head.config(text=tn("{count} album, {size}", "{count} albums, {size}", albums,
                                        size=phone.size_text(size)) if tree else "")
        shown = {n["name"].lower() for n in tree}
        for folder_key, (done, count) in sorted(self.adding.items()):
            if folder_key not in shown:
                self._row(lst, None, folder_key, 0, "", 0, note=t("adding, {done} of {count}", done=done,
                                                                    count=count), note_fg=PALETTE["go"])
        if not tree and not self.adding:
            tk.Label(lst.rows, text=t("No albums on it yet. Type an artist, album or track above to add one."),
                     font=("Segoe UI", 9), bg=lst.field, fg=PALETTE["help_fg"], anchor="w", justify="left",
                     wraplength=self._px(280)).grid(row=0, column=0, columnspan=4, sticky="w", padx=self._px(10),
                                                    pady=self._px(8))
        for n in tree:
            self._album_node(lst, n, 0, live)
        lst.wheel_everywhere()

    def _album_node(self, lst, n, depth, live):
        key = ("dir", n["rel"]) if n["kind"] == "folder" else ("file", n["rel"])
        if n["kind"] == "file":
            self._row(lst, key, n["name"], depth, "", n["size"], live=live)
            return
        is_open = n["rel"].lower() in self.opened
        albums = [c for c in n["children"] if c["kind"] == "folder"]
        note, note_fg, count_text = "", None, tn("{count} track", "{count} tracks", n["tracks"])
        if depth == 0:
            count_text = tn("{count} album", "{count} albums", len(albums)) if albums else count_text
            adding = self.adding.get(n["name"].lower())
            if adding:
                note, note_fg = t("adding, {done} of {count}", done=adding[0], count=adding[1]), PALETTE["go"]
            elif len(albums) == 1:
                total = self._album_total(n["name"], albums[0]["name"])
                if total and albums[0]["tracks"] < total:
                    note = tn("{count} track of {album}", "{count} tracks of {album}", albums[0]["tracks"],
                              album=albums[0]["name"])
        elif depth == 1:
            total = self._album_total(n["rel"].split("/")[1], n["name"])
            if total and n["tracks"] < total:
                note = t("{count} of {total} tracks", count=n["tracks"], total=total)
            if n["lists"]:
                note = (note + " · " if note else "") + t("in {lists}", lists=phone.names_text(n["lists"]))
        self._row(lst, key, n["name"], depth, count_text, n["size"], note, note_fg, fold=is_open, live=live)
        if is_open:
            for c in n["children"]:
                self._album_node(lst, c, depth + 1, live)

    def _draw_lists(self, f, live):
        lst = self.lists
        lst.clear()
        # what's in Playlists, a song two playlists share counted once (a hand-made one's songs in Albums are Albums')
        size = sum(f.files[p]["size"] for p in {p for pl in f.playlists for p in pl["paths"]}
                   if p in f.files and p.startswith(phone.PLAYLISTS.lower() + "/"))
        self.lists_head.config(text=tn("{count} playlist, {size}", "{count} playlists, {size}", len(f.playlists),
                                       size=phone.size_text(size)) if f.playlists else "")
        if not f.playlists:
            tk.Label(lst.rows, text=t("No playlists on it yet. Save on the Play tab copies one here."),
                     font=("Segoe UI", 9), bg=lst.field, fg=PALETTE["help_fg"], anchor="w", justify="left",
                     wraplength=self._px(280)).grid(row=0, column=0, columnspan=4, sticky="w", padx=self._px(10),
                                                    pady=self._px(8))
        for pl in f.playlists:
            key = ("pl", pl["low"])
            is_open = pl["low"] in self.opened
            self._row(lst, key, pl["name"], 0, tn("{count} track", "{count} tracks", pl["tracks"]), pl["size"],
                      note="." + pl["low"].rsplit(".", 1)[1], fold=is_open, live=live)
            if is_open:
                for path in pl["paths"]:
                    others = [n for n in f.lists_of.get(path, []) if n != pl["name"]]
                    # "Bon Iver - Holocene" in Playlists; a song in Albums by its artist, album and track
                    name = os.path.splitext(f.files[path]["rel"].split("/", 1)[-1])[0]
                    self._row(lst, ("song", (pl["low"], path)), name, 1, "", f.files[path]["size"],
                              note=t("also in {lists}", lists=phone.names_text(others)) if others else "",
                              live=live)
        lst.wheel_everywhere()

    # --- ticks and Delete -------------------------------------------------------------------------------------

    def _exists(self, key):
        f = self.contents.get(self.current)
        if f is None:
            return False
        kind, rel = key
        if kind == "pl":
            return rel in {pl["low"] for pl in f.playlists}
        if kind == "song":
            return rel[1] in f.files
        return rel.lower() in f.folders if kind == "dir" else rel.lower() in f.files

    def _covered(self, key):
        """Ticked through a folder above it, or a song through its playlist."""
        kind, rel = key
        if kind == "song":
            return ("pl", rel[0]) in self.ticked
        if kind == "pl":
            return False
        low = rel.lower()
        return any(k == "dir" and low.startswith(r.lower() + "/") for k, r in self.ticked)

    def _toggle(self, key, on):
        (self.ticked.add if on else self.ticked.discard)(key)
        if on and key[0] == "dir":
            inside = key[1].lower() + "/"
            self.ticked = {k for k in self.ticked if k[0] in ("pl", "song") or not k[1].lower().startswith(inside)}
        if on and key[0] == "pl":
            self.ticked = {k for k in self.ticked if not (k[0] == "song" and k[1][0] == key[1])}
        self.draw()

    def _fold(self, key):
        low = key[1].lower()
        (self.opened.discard if low in self.opened else self.opened.add)(low)
        self.draw()

    def ticks(self):
        """What's ticked, as phone.Folder.plan takes it."""
        return {"playlists": [r for k, r in self.ticked if k == "pl"],
                "folders": [r for k, r in self.ticked if k == "dir"],
                "files": [r for k, r in self.ticked if k == "file"],
                "songs": [r for k, r in self.ticked if k == "song"]}

    def _what(self):
        f = self.contents[self.current]
        names = {pl["low"]: pl["name"] for pl in f.playlists}
        shown = []
        for k, r in self.ticked:
            if k == "pl":
                shown.append(names.get(r, r))
            elif k == "song":
                shown.append(os.path.splitext(f.files[r[1]]["rel"].rpartition("/")[2])[0] if r[1] in f.files else "")
            else:
                shown.append(os.path.splitext(r.rpartition("/")[2])[0] if k == "file" else r.rpartition("/")[2])
        shown = sorted(s for s in shown if s)
        return phone.names_text(shown) if len(shown) <= 3 else t("the {count} ticked", count=len(shown))

    def _sync_note(self):
        f = self.contents.get(self.current)
        text = ""
        if f is not None and self.ticked:
            text = f.plan_text(f.plan(**self.ticks()), self._what())
        if text:
            self.note.config(text=text, fg=PALETTE["amber"])
        elif self.busy:
            self.note.config(text=t("Working on it..."), fg=PALETTE["help_fg"])
        else:
            self.note.config(text=t("Tick what to take off, then Delete.") if f is not None else "",
                             fg=PALETTE["help_fg"])

    def delete(self):
        """Delete: what the amber line said, then the folder read again."""
        if self.current is None or self.current not in self.contents or self.answering.get(self.current) is False:
            return
        if not self.ticked:
            self.note.config(text=t("Tick what to take off, then Delete."), fg=PALETTE["amber"])
            return
        ticks = self.ticks()
        self.ticked = set()
        self.busy = True
        self.note.config(text=t("Deleting..."), fg=PALETTE["help_fg"])
        self._job("delete", self.current, ticks)

    # --- the library box ------------------------------------------------------------------------------------

    def _close_pop(self):
        pop, self._pop = self._pop, None
        if pop is not None:
            try:
                pop.destroy()
            except tk.TclError:
                pass

    def _close_pop_if_away(self):
        try:
            if self.focus_get() is self.find_box.entry:
                return
        except (KeyError, tk.TclError):
            pass
        self._close_pop()

    def suggestions(self, typed):
        """[(heading, [(label, item)])] for what's typed; an item is ("artist", name), ("album", (album, by)) or
        ("track", (title, artist, key))."""
        found = library.find_items(typed, SHOWN)
        out = []
        if found["artists"]:
            out.append((t("Artists"), [(a, ("artist", a)) for a in found["artists"]]))
        if found["albums"]:
            out.append((t("Albums"), [(f"{a} · {by}" if by else a, ("album", (a, by))) for a, by in found["albums"]]))
        if found["tracks"]:
            out.append((t("Tracks"), [(f"{name} · {by}" if by else name, ("track", (name, by, key)))
                                      for name, by, key in found["tracks"]]))
        return out

    def _suggest(self):
        self._close_pop()
        typed = self.find_box.get().strip()
        groups = self.suggestions(typed)
        if not groups:
            return
        bg, fg, muted = PALETTE["field_bg"], PALETTE["text"], PALETTE["help_fg"]
        entry = self.find_box
        pop = self._pop = tk.Toplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(bg=PALETTE["line"], padx=1, pady=1)
        inner = tk.Frame(pop, bg=bg)
        inner.pack(fill="both", expand=True)
        pop.rows = []
        for heading, items in groups:
            tk.Label(inner, text=heading.upper(), font=("Segoe UI", 8), fg=muted, bg=bg).pack(anchor="w", padx=10,
                                                                                            pady=(6, 1))
            for text, item in items:
                r = tabs.PickRow(inner, "    " + text, fg=fg, bg=bg, fit=True, tag=t("+ Add"))
                r.configure(cursor="hand2")
                r.pack(fill="x", padx=3, pady=1)
                r.bind("<Enter>", lambda e, w=r: w.set_chosen(True))
                r.bind("<Leave>", lambda e, w=r: w.set_chosen(False))
                r.bind("<ButtonPress-1>", lambda e, i=item: self.add(i))
                pop.rows.append((item, r))
        pop.update_idletasks()
        w = max(pop.winfo_reqwidth(), entry.winfo_width(), 320)
        pop.geometry(f"{w}x{pop.winfo_reqheight()}+{entry.winfo_rootx()}+"
                     f"{entry.winfo_rooty() + entry.winfo_height() + 2}")
        pop.deiconify()
        pop.lift()

    def add(self, item):
        """+ Add: the artist's, album's or track's files copied straight into Albums, one add after another."""
        self._close_pop()
        self.find_box.delete(0, "end")
        if self.current is None or self.answering.get(self.current) is False:
            self.note.config(text=t("Choose a device that's answering first."), fg=PALETTE["amber"])
            return
        kind, what = item
        if kind == "artist":
            keys, label, folder = library.artist_keys(what), what, what
        elif kind == "album":
            album, by = what
            keys, label, folder = library.album_keys(album, by), album, by or album
        else:
            title, by, key = what
            row = library.track_row(key) or {}
            keys, label = [key], t("{title} by {artist}", title=title, artist=by) if by else title
            folder = row.get("Album Artist (auto)") or by
        if not keys:
            return
        folder_key = phone.safe_name(folder or t("Unknown Artist")).lower()
        self.adding.setdefault(folder_key, [0, len(keys)])
        self.busy = True
        self.draw()
        self._job("add", self.current, label, keys, folder_key)
