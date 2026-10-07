"""
review_gui.py - the Review view, in the console area of the Play tab.

A build with Behaviour set to Review sends nothing to JRiver. Its tracks are listed
here instead: tick the ones you want, in the order you want them (each tick shows its
number), then choose what to do with them. A Console | Review switch above the console
moves between the two; the console keeps running underneath, and a dot on Console says
something new arrived there while Review was showing.

The actions send the ticked tracks, in tick order, to the zone the build was for:
Add as Up Next, Add to End, Finish This Song, Load as New, Stop Song, Load as New,
and Save as Playlist. The ticks clear once an action has gone through.

The list stays until the next Review build replaces it.

Preview: a "Preview in" choice at the right of the header picks a zone with its own
speakers or headphones (None by default; the zone the list goes to isn't offered).
With one chosen, each row gets a play mark that plays just that track there, one at
a time. Stop Preview, any action, a new Review build or choosing None stops it.
"""
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import engine
from settings_gui import Tooltip, read_env, write_env

BLACK, GREEN, DIM, WHITE, MUTED = "#000000", "#00ff41", "#0d4d1c", "#ffffff", "#7fbf8f"
ROW_ON = "#0b2412"            # a ticked row
FONT, BOLD = ("Consolas", 9), ("Consolas", 9, "bold")
DOT = "\u25cf"
PLAY_MARK, STOP_MARK = "\u25b6", "\u25a0"
PREVIEW_TIP = ("Listen to a track before you add it, in a zone with its own speakers or headphones. "
               "The zone this list goes to isn't offered.")

# (how, button, what it does): the two Adds keep Playing Now, the two Load as New replace it
ACTIONS = [
    ("next", "Add as Up Next", "Plays after the current song, then the rest of Playing Now carries on."),
    ("end", "Add to End", "Goes after everything already in Playing Now."),
    ("finish", "Finish This Song, Load as New", "The current song finishes, then Playing Now holds only these."),
    ("stop", "Stop Song, Load as New", "The current song stops and these play straight away. "
                                       "Playing Now holds only these."),
]
SAVE_TIP = "Nothing plays and Playing Now isn't touched. Saves these as a JRiver playlist."

# (title, width in characters, stretch): Artist, Title and Album share the spare room
COLUMNS = [("Add", 4, 0), ("Artist", 18, 2), ("Title", 24, 3), ("Album", 18, 2), ("Time", 6, 0), ("BPM", 5, 0)]


def clock(seconds):
    try:
        s = int(round(float(seconds or 0)))
    except (TypeError, ValueError):
        return ""
    return f"{s // 60}:{s % 60:02d}" if s else ""


class ReviewPanel:
    """Lives inside the Play tab's console box. play is the PlayTab."""

    def __init__(self, play):
        self.play = play
        self.box = play.console_box
        self.rows, self.order, self.title, self.zone = [], [], "", None
        self.showing = False
        self.dot = False
        self.busy = False
        self._buttons = {}
        self._cells = {}          # key -> (tick label, [text labels])
        self._marks = {}          # key -> its Preview mark, when a preview zone is chosen
        self.preview_name = read_env().get("REVIEW_PREVIEW_ZONE", "").strip()
        self.preview_zone = None  # the chosen zone's ID, if it exists and isn't this list's zone
        self.previewing = None    # the key playing in the preview zone
        self.preview_at = None    # the zone it's playing in
        self._preview_token = 0   # a later preview or stop makes an older end-of-track check stale
        self._build_switch()
        self._build_frame()

    # --- the Console | Review switch ---

    def _build_switch(self):
        self.switch_row = tk.Frame(self.box, bg=BLACK)
        edge = tk.Frame(self.switch_row, bg=GREEN, padx=1, pady=1)
        edge.pack(side="left")
        inner = tk.Frame(edge, bg=BLACK)
        inner.pack()
        self.console_btn = tk.Label(inner, text="Console", font=("Segoe UI", 9, "bold"), padx=14, pady=2,
                                    cursor="hand2")
        self.console_btn.pack(side="left")
        tk.Frame(inner, bg=GREEN, width=1).pack(side="left", fill="y")
        self.review_btn = tk.Label(inner, text="Review", font=("Segoe UI", 9, "bold"), padx=14, pady=2,
                                   cursor="hand2")
        self.review_btn.pack(side="left")
        self.console_btn.bind("<Button-1>", lambda e: self.show_console())
        self.review_btn.bind("<Button-1>", lambda e: self.show_review())
        self._style_switch()

    def _show_switch(self):
        if self.switch_row.winfo_manager():
            return
        slaves = self.box.pack_slaves()
        if slaves:
            self.switch_row.pack(fill="x", padx=8, pady=(6, 4), before=slaves[0])
        else:
            self.switch_row.pack(fill="x", padx=8, pady=(6, 4))

    def _style_switch(self):
        on, off = dict(bg=GREEN, fg=BLACK), dict(bg=BLACK, fg=GREEN)
        self.console_btn.config(text=f"Console {DOT}" if self.dot and self.showing else "Console",
                                **(off if self.showing else on))
        ticked = len(self.order)
        self.review_btn.config(text=f"Review ({ticked})" if ticked and not self.showing else "Review",
                               **(on if self.showing else off))

    # --- the Review frame ---

    def _build_frame(self):
        self.frame = tk.Frame(self.box, bg=BLACK)
        head = tk.Frame(self.frame, bg=BLACK)
        head.pack(fill="x", padx=8, pady=(2, 6))
        self.title_label = tk.Label(head, text="", font=BOLD, bg=BLACK, fg=WHITE, anchor="w")
        self.title_label.pack(side="left")
        self.count_label = tk.Label(head, text="", font=FONT, bg=BLACK, fg=MUTED)
        self.count_label.pack(side="left", padx=(12, 4))
        for text, command in (("Select All", self.select_all), ("Select None", self.select_none)):
            self.play._head_box(head, text, command).pack(side="left", padx=(6, 0))
        self.preview_bar = tk.Frame(head, bg=BLACK)       # Preview zone and Stop Preview
        self.preview_bar.pack(side="right")
        self.preview_btn = self.play._head_box(self.preview_bar, "", self._preview_menu)
        self.preview_btn.pack(side="left")
        Tooltip(self.preview_btn, PREVIEW_TIP)
        self.stop_preview_btn = self.play._head_box(self.preview_bar, "Stop Preview", self.stop_preview)
        self.stop_preview_btn.pack(side="left", padx=(6, 0))
        self._sync_preview()
        tk.Frame(self.frame, bg=GREEN, height=1).pack(fill="x", padx=8)
        self.action_bar = tk.Frame(self.frame, bg=BLACK)  # the actions, along the bottom
        self.action_bar.pack(side="bottom", fill="x", padx=8, pady=(6, 8))
        self._build_actions()

        holder = tk.Frame(self.frame, bg=BLACK)
        holder.pack(fill="both", expand=True)
        canvas = tk.Canvas(holder, bg=BLACK, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.grid = tk.Frame(canvas, bg=BLACK, padx=8, pady=4)
        window = canvas.create_window((0, 0), window=self.grid, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        self.grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def wheel(e):
            canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self.canvas = canvas

    # --- the actions ---

    def _action_button(self, parent, text, command, tip):
        b = tk.Label(parent, text=text, font=("Segoe UI", 9, "bold"), bg=BLACK, fg=GREEN, padx=12, pady=4,
                     cursor="hand2", highlightthickness=1, highlightbackground=GREEN, highlightcolor=GREEN)
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.config(bg=DIM) if self._can_act() else None, add="+")
        b.bind("<Leave>", lambda e: b.config(bg=BLACK), add="+")
        Tooltip(b, tip)
        return b

    def _build_actions(self):
        bar = self.action_bar
        tk.Frame(bar, bg=DIM, height=1).pack(fill="x", pady=(0, 8))
        row = tk.Frame(bar, bg=BLACK)
        row.pack(fill="x")
        self.into_label = tk.Label(row, text="", font=FONT, bg=BLACK, fg=MUTED)
        self.into_label.pack(side="left", padx=(0, 10))
        for n, (how, text, tip) in enumerate(ACTIONS):
            if n == 2:   # the two Adds, then the two Load as New
                tk.Frame(row, bg=DIM, width=1, height=22).pack(side="left", padx=(4, 10))
            b = self._action_button(row, text, lambda h=how: self._act(h), tip)
            b.pack(side="left", padx=(0, 6))
            self._buttons[how] = b
        save = self._action_button(row, "Save as Playlist", self._save, SAVE_TIP)
        save.pack(side="right")
        self._buttons["save"] = save
        self.status_label = tk.Label(bar, text="", font=FONT, bg=BLACK, fg=MUTED, anchor="w")
        self.status_label.pack(fill="x", pady=(6, 0))

    def _can_act(self):
        return bool(self.order) and not self.busy and self.zone is not None

    def _sync_buttons(self):
        ok = self._can_act()
        for b in self._buttons.values():
            b.config(fg=GREEN if ok else DIM, highlightbackground=GREEN if ok else DIM,
                     cursor="hand2" if ok else "")
        try:
            where = engine.zone_label(self.zone) if self.zone is not None else ""
        except Exception:
            where = ""
        self.into_label.config(text=f"Into {where}" if where else "")

    def _run(self, work):
        """Runs a JRiver call off the main thread, then reports it in the console and under the actions."""
        self.busy = True
        self._sync_buttons()
        self.status_label.config(text="Sending to JRiver...")

        def worker():
            try:
                line = work()
            except Exception as e:
                line = f"Problem: Review couldn't send that to JRiver ({e})."
            self.play.root.after(0, lambda: self._done(line))
        threading.Thread(target=worker, daemon=True).start()

    def _done(self, line):
        self.busy = False
        self.play._append_log(time.strftime("%H:%M") + "  " + line)
        self.dot = False   # our own line, not news from elsewhere
        self.status_label.config(text=line.replace("Review: ", "", 1))
        if not line.startswith("Problem:"):
            self.order = []
        self._restyle()

    def _act(self, how):
        if not self._can_act():
            return
        keys, zone = list(self.order), self.zone
        self.stop_preview(quiet=True)
        self._run(lambda: engine.review_send(keys, how, zone))

    def _save(self):
        if not self._can_act():
            return
        default = self.title.replace("\\", " ").replace("/", " ") or "24bit7 Review"
        name = simpledialog.askstring("Save as Playlist", "Name for the JRiver playlist:",
                                      initialvalue=default, parent=self.frame)
        name = (name or "").strip().replace("\\", " ").replace("/", " ")
        if not name:
            return
        if engine.playlist_exists(name) and not messagebox.askyesno(
                "Save as Playlist", f"JRiver already has a playlist called \"{name}\". Replace it?",
                parent=self.frame):
            return
        keys = list(self.order)
        self.stop_preview(quiet=True)
        self._run(lambda: engine.review_save(keys, name))

    # --- moving between Console and Review ---

    def _hide_console(self):
        p = self.play
        for w in (p.console_head, getattr(p, "log_table", None)):
            if w is not None and w.winfo_manager():
                w.pack_forget()
        p.head_arrow.place_forget()
        if p.head_arrow.winfo_manager():
            p.head_arrow.pack_forget()
        if p.log.frame.winfo_manager():   # ScrolledText: its frame is the packed widget
            p.log.pack_forget()
        p.console_strip.place_forget()

    def _restore_console(self):
        p = self.play
        if not p.log.frame.winfo_manager():
            p.log.pack(fill="both", expand=True)
        p._set_tabs_open(p.tabs_open, save=False)
        if p.view == "log":
            p._show_log_table()

    def show_review(self):
        if not self.rows:
            return
        self._show_switch()
        if not self.showing:
            self._hide_console()
            self.frame.pack(fill="both", expand=True)
        self.showing, self.dot = True, False
        self._style_switch()

    def show_console(self):
        if self.showing:
            self.frame.pack_forget()
            self._restore_console()
        self.showing, self.dot = False, False
        self._style_switch()

    def console_activity(self):
        """A console line arrived while Review was showing: a dot on Console says so."""
        if self.showing and not self.dot:
            self.dot = True
            self._style_switch()

    # --- the list ---

    def load(self, rows, title="", zone=None):
        """A Review build finished: its tracks replace the list, nothing ticked, and Review shows."""
        self.stop_preview(quiet=True)
        self.rows = [dict(r) for r in rows or []]
        self.order, self.title, self.zone = [], title, zone
        self.status_label.config(text="")
        self._refresh_preview_zone()
        self._render()
        if self.rows:
            self.show_review()

    def _columns(self):
        return COLUMNS + ([("", 3, 0)] if self.preview_zone else [])

    def _render(self, keep_scroll=False):
        top = self.canvas.yview()[0]
        for child in self.grid.winfo_children():
            child.destroy()
        self._cells, self._marks = {}, {}
        columns = self._columns()
        for c in range(len(COLUMNS) + 1):
            self.grid.grid_columnconfigure(c, weight=0)
        for c, (title, width, stretch) in enumerate(columns):
            self.grid.grid_columnconfigure(c, weight=stretch)
            tk.Label(self.grid, text=title, font=BOLD, bg=BLACK, fg=MUTED, width=width, padx=4,
                     anchor="e" if title in ("Time", "BPM") else "w").grid(
                row=0, column=c, sticky="ew", pady=(0, 2))
        r = 1
        for row in self.rows:
            key = row["key"]
            tick = tk.Label(self.grid, text="", font=BOLD, width=2, bg=BLACK, fg=GREEN, cursor="hand2",
                            highlightthickness=1, highlightbackground=DIM, highlightcolor=DIM)
            tick.grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
            values = (row.get("artist", ""), row.get("title", ""), row.get("album", ""),
                      clock(row.get("seconds")), row.get("bpm", ""))
            texts = []
            for c, value in enumerate(values, start=1):
                cell = tk.Label(self.grid, text=value, font=FONT, bg=BLACK, fg=GREEN, cursor="hand2", padx=4, pady=3,
                                width=COLUMNS[c][1], anchor="e" if c >= 4 else "w")
                cell.grid(row=r, column=c, sticky="nsew")   # no gaps, so a ticked row shades as one band
                texts.append(cell)
            for w in [tick] + texts:   # the whole row is the target: tick or untick
                w.bind("<Button-1>", lambda e, k=key: self.toggle(k))
            self._cells[key] = (tick, texts)
            if self.preview_zone:   # the Preview mark: plays this track in the preview zone, doesn't tick it
                mark = tk.Label(self.grid, text=PLAY_MARK, font=FONT, bg=BLACK, fg=GREEN, cursor="hand2",
                                width=3, padx=4, pady=3)
                mark.grid(row=r, column=len(COLUMNS), sticky="nsew")
                mark.bind("<Button-1>", lambda e, k=key: self._preview_click(k))
                self._marks[key] = mark
            tk.Frame(self.grid, bg=DIM, height=1).grid(row=r + 1, column=0, columnspan=len(columns), sticky="ew")
            r += 2
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(top if keep_scroll else 0)
        self._restyle()

    def _restyle(self):
        for key, (tick, texts) in self._cells.items():
            on = key in self.order
            bg = ROW_ON if on else BLACK
            tick.config(text=str(self.order.index(key) + 1) if on else "",
                        highlightbackground=GREEN if on else DIM, highlightcolor=GREEN if on else DIM)
            for cell in texts:
                cell.config(bg=bg, font=BOLD if on else FONT)
            mark = self._marks.get(key)
            if mark is not None:
                mark.config(bg=bg, text=STOP_MARK if key == self.previewing else PLAY_MARK)
        n = len(self.rows)
        self.title_label.config(text=self.title)
        self.count_label.config(text=f"{n} track{'' if n == 1 else 's'}, {len(self.order)} ticked")
        self._style_switch()
        self._sync_buttons()
        self._sync_preview()

    def toggle(self, key):
        """Ticking adds the track at the end of the order; unticking closes the gap."""
        if self.busy:
            return
        if key in self.order:
            self.order.remove(key)
        else:
            self.order.append(key)
        self._restyle()

    def select_all(self):
        self.order = [r["key"] for r in self.rows]
        self._restyle()

    def select_none(self):
        self.order = []
        self._restyle()

    def ticked_keys(self):
        return list(self.order)

    # --- Preview ---

    def _refresh_preview_zone(self):
        """The chosen preview zone's ID, or None: not chosen, gone from JRiver, or this list's own zone."""
        zid = None
        if self.preview_name:
            try:
                zid = engine.zone_id(self.preview_name)
            except Exception:
                zid = None
            if zid is not None and str(zid) == str(self.zone):
                zid = None   # never the room the list is going to
        self.preview_zone = zid

    def _sync_preview(self):
        shown = self.preview_name if self.preview_zone else "None"
        self.preview_btn.config(text=f"Preview in: {shown} \u25be")
        on = self.previewing is not None
        self.stop_preview_btn.config(fg=GREEN if on else DIM, cursor="hand2" if on else "")

    def preview_choices(self):
        """The zones offered for Preview: every JRiver zone except the one this list goes to."""
        try:
            zones = engine._zone_list(fresh=True)
        except Exception:
            zones = []
        return [name for zid, name in zones if str(zid) != str(self.zone)]

    def _preview_menu(self):
        menu = tk.Menu(self.frame, tearoff=0, bg=BLACK, fg=GREEN, activebackground=DIM,
                       activeforeground=GREEN, font=FONT)
        for name in ["None"] + self.preview_choices():
            menu.add_command(label=name, command=lambda n=name: self.choose_preview("" if n == "None" else n))
        b = self.preview_btn
        try:
            menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        finally:
            menu.grab_release()

    def choose_preview(self, name):
        """A zone picked under Preview in (empty for None): remembered, and the marks shown or hidden."""
        self.stop_preview(quiet=True)
        self.preview_name = name
        write_env({"REVIEW_PREVIEW_ZONE": name})
        self._refresh_preview_zone()
        if self.rows:
            self._render(keep_scroll=True)
        self._sync_preview()

    def _background(self, work, failed):
        def worker():
            try:
                work()
            except Exception as e:
                self.play.root.after(0, lambda e=e: failed(e))
        threading.Thread(target=worker, daemon=True).start()

    def _preview_click(self, key):
        if self.preview_zone is None:
            return
        if key == self.previewing:
            self.stop_preview()
            return
        row = next((r for r in self.rows if r["key"] == key), {})
        zid, where = self.preview_zone, self.preview_name
        self._preview_token += 1
        token = self._preview_token
        self.previewing, self.preview_at = key, zid
        what = " - ".join(x for x in (row.get("artist", ""), row.get("title", "")) if x)
        self.status_label.config(text=f"Previewing {what} in {where}.")

        def failed(e):
            if token == self._preview_token:
                self.previewing = self.preview_at = None
                self.status_label.config(text=f"Problem: Preview couldn't play that in {where} ({e}).")
                self._restyle()
        self._background(lambda: engine.review_preview(key, zid), failed)
        try:   # once the track has had time to finish, the mark goes back to play
            seconds = float(row.get("seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0
        if seconds:
            self.play.root.after(int(seconds * 1000) + 2000, lambda: self._preview_ended(token))
        self._restyle()

    def _preview_ended(self, token):
        if token == self._preview_token and self.previewing is not None:
            self.previewing = self.preview_at = None
            self._restyle()

    def stop_preview(self, quiet=False):
        """Stops the preview zone. quiet: an action or a new list is about to say what happened."""
        if self.previewing is None:
            return
        zid = self.preview_at
        self._preview_token += 1
        self.previewing = self.preview_at = None
        if not quiet:
            self.status_label.config(text="Preview stopped.")
        self._background(lambda: engine.review_preview_stop(zid), lambda e: None)
        self._restyle()
