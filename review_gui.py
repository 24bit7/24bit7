"""
review_gui.py - the Review view, in the console area of the Play tab.

A build with Behaviour set to Review sends nothing to JRiver. Its tracks are listed
here instead: tick the ones you want, in the order you want them (each tick shows its
number), then choose what to do with them. A Console | Review switch above the console
moves between the two; the console keeps running underneath, and a dot on Console says
something new arrived there while Review was showing.

The actions send the ticked tracks, in tick order, wherever Output says when pressed
(a zone, or the Now Playing zone for Same Zone). With Output on YouTube, one Play on
YouTube button opens them there as a playlist instead:
Add as Up Next, Add to End, Finish This Song, Load as New, Stop Song, Play Now,
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

import tkinter.font as tkfont

import engine
from settings_gui import Tooltip, read_env, write_env
from tabs import rounded_shape

# The console stays black and green in both themes; Review follows the theme (the 7 Oct mockups).
CONSOLE = {"bg": "#000000", "accent": "#00ff41", "on_accent": "#000000"}
DARK = {"bg": "#000000", "text": "#d8ffe0", "muted": "#7fbf8f", "line": "#123a1c", "accent": "#00ff41",
        "on_accent": "#000000", "row_on": "#0b2412", "stripe": "#07120a", "row_prev": "#2a1a08", "tick_off": "#2f6b3d",
        "tick_on_bg": "#000000", "tick_on_fg": "#00ff41", "act_bg": "#000000", "act_fg": "#00ff41",
        "act_hover": "#0b2412", "act_dim": "#1d4d2a", "act_dim_fg": "#1d4d2a"}
LIGHT = {"bg": "#ffffff", "text": "#1a1a1a", "muted": "#4a4d52", "line": "#dcdfe3", "accent": "#1f4e8c",
         "on_accent": "#ffffff", "row_on": "#e3edf9", "stripe": "#f6f7f9", "row_prev": "#fff1e0", "tick_off": "#9aa0a6",
         "tick_on_bg": "#1f4e8c", "tick_on_fg": "#ffffff", "act_bg": "#1f4e8c", "act_fg": "#ffffff",
         "act_hover": "#173d6e", "act_dim": "#a9b8cc", "act_dim_fg": "#ffffff"}
ORANGE = "#f28c28"
FONT, BOLD = ("Segoe UI", 9), ("Segoe UI", 9, "bold")
SMALL_BOLD = ("Segoe UI", 8, "bold")
SIZE_MIN, SIZE_MAX, SIZE_DEFAULT = 6, 14, 9   # the track list's text size, set with A- and A+
DOT = "\u25cf"


def palette():
    return DARK if getattr(engine, "THEME", "light") == "dark" else LIGHT
PLAY_MARK, STOP_MARK = "\u25b6", "\u25a0"
PREVIEW_TIP = ("Listen to a track before you add it, in a zone with its own speakers or headphones. "
               "The zone this list goes to isn't offered.")

# (how, button, what it does): the two Adds keep Playing Now, the two Load as New replace it
ACTIONS = [
    ("next", "Add as Up Next", "Plays after the current song, then the rest of Playing Now carries on."),
    ("end", "Add to End", "Goes after everything already in Playing Now."),
    ("finish", "Finish This Song, Load as New", "The current song finishes, then Playing Now holds only these."),
    ("stop", "Stop Song, Play Now", "The current song stops and these play straight away. "
                                       "Playing Now holds only these."),
]
YOUTUBE_TIP = "Opens the ticked tracks, in tick order, as a YouTube playlist in your browser."
SAME_ZONE = "Same zone"       # Output's first choice: the Now Playing zone
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
        self.p = palette()
        try:
            self.scale = max(1.0, self.box.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            self.scale = 1.0
        self.rows, self.order, self.title, self.zone = [], [], "", None
        self.showing = False
        self.dot = False
        self.busy = False
        self._buttons = {}
        self._cells = {}          # key -> (tick label, [text labels])
        self._marks = {}          # key -> its Preview mark, when a preview zone is chosen
        env = read_env()
        self.preview_name = env.get("REVIEW_PREVIEW_ZONE", "").strip()
        try:
            self.size = min(SIZE_MAX, max(SIZE_MIN, int(env.get("REVIEW_FONT_SIZE", SIZE_DEFAULT))))
        except ValueError:
            self.size = SIZE_DEFAULT
        self.preview_zone = None  # the chosen zone's ID, if it exists and isn't this list's zone
        self.previewing = None    # the key playing in the preview zone
        self.preview_at = None    # the zone it's playing in
        self._preview_token = 0   # a later preview or stop makes an older end-of-track check stale
        self._build_switch()
        self._build_frame()

    # --- the Console | Review switch ---

    def _build_switch(self):
        self.switch_row = tk.Frame(self.box, bg=CONSOLE["bg"])
        self.switch_edge = tk.Frame(self.switch_row, bg=CONSOLE["accent"], padx=1, pady=1)
        self.switch_edge.pack(side="left")
        inner = tk.Frame(self.switch_edge, bg=CONSOLE["bg"])
        inner.pack()
        self.console_btn = tk.Label(inner, text="Console", font=BOLD, padx=16, pady=3, cursor="hand2")
        self.console_btn.pack(side="left")
        self.switch_mid = tk.Frame(inner, bg=CONSOLE["accent"], width=1)
        self.switch_mid.pack(side="left", fill="y")
        self.review_btn = tk.Label(inner, text="Review", font=BOLD, padx=16, pady=3, cursor="hand2")
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
        c = self.p if self.showing else CONSOLE   # Review's colours while it shows, the console's otherwise
        try:
            self.box.config(bg=c["bg"])
        except tk.TclError:
            pass
        for w in (self.switch_row, self.switch_edge.winfo_children()[0]):
            w.config(bg=c["bg"])
        self.switch_edge.config(bg=c["accent"])
        self.switch_mid.config(bg=c["accent"])
        on, off = dict(bg=c["accent"], fg=c["on_accent"]), dict(bg=c["bg"], fg=c["accent"])
        self.console_btn.config(text=f"Console {DOT}" if self.dot and self.showing else "Console",
                                **(off if self.showing else on))
        ticked = len(self.order)
        self.review_btn.config(text=f"Review ({ticked})" if ticked and not self.showing else "Review",
                               **(on if self.showing else off))

    # --- the Review frame ---

    # --- drawn pieces: rounded boxes as images, text on top ---

    def _px(self, n):
        return int(round(n * self.scale))

    def _shape(self, w, h, fill, edge, line=1, radius=6):
        return rounded_shape(self.box, self._px(w), self._px(h), self._px(radius), fill, edge, self._px(line))

    def _text_width(self, text, font):
        return tkfont.Font(root=self.box, font=font).measure(text) / self.scale

    def _pill(self, parent, text, command, fg=None, edge=None, fill=None, font=FONT, pad=24, h=26):
        """A small rounded outline button (Select All, Stop Preview, Save as Playlist)."""
        p = self.p
        b = tk.Label(parent, text=text, font=font, compound="center", bd=0, cursor="hand2", bg=p["bg"])
        b._look = dict(fg=fg or p["accent"], edge=edge or p["line"], fill=fill or p["bg"], pad=pad, h=h, font=font)
        self._paint_pill(b)
        b.bind("<Button-1>", lambda e: command())
        return b

    def _paint_pill(self, b, fg=None, edge=None, fill=None):
        look = b._look
        w = self._text_width(b.cget("text"), look["font"]) + look["pad"]
        img = self._shape(w, look["h"], fill or look["fill"], edge or look["edge"])
        b.config(image=img, fg=fg or look["fg"], bg=self.p["bg"])
        b._img = img

    def _build_frame(self):
        p = self.p
        self.frame = tk.Frame(self.box, bg=p["bg"])
        head = tk.Frame(self.frame, bg=p["bg"])
        head.pack(fill="x", padx=14, pady=(4, 8))
        self.title_label = tk.Label(head, text="", font=BOLD, bg=p["bg"], fg=p["text"], anchor="w")
        self.title_label.pack(side="left")
        self.count_label = tk.Label(head, text="", font=FONT, bg=p["bg"], fg=p["muted"])
        self.count_label.pack(side="left", padx=(14, 8))
        for text, command in (("Select All", self.select_all), ("Select None", self.select_none)):
            self._pill(head, text, command).pack(side="left", padx=(6, 0))
        self.smaller_btn = self._pill(head, "A\u2212", lambda: self.set_size(self.size - 1), pad=18)
        self.smaller_btn.pack(side="left", padx=(16, 0))
        Tooltip(self.smaller_btn, "Smaller text in the track list.")
        self.bigger_btn = self._pill(head, "A+", lambda: self.set_size(self.size + 1), pad=18)
        self.bigger_btn.pack(side="left", padx=(4, 0))
        Tooltip(self.bigger_btn, "Bigger text in the track list.")
        self.preview_bar = tk.Frame(head, bg=p["bg"])       # Preview zone and Stop Preview
        self.preview_bar.pack(side="right")
        tk.Label(self.preview_bar, text="Preview in", font=FONT, bg=p["bg"], fg=p["muted"]).pack(side="left")
        self.preview_btn = tk.Label(self.preview_bar, text="", font=BOLD, bg=p["bg"], fg=ORANGE, cursor="hand2")
        self.preview_btn.pack(side="left", padx=(8, 10))
        self.preview_btn.bind("<Button-1>", lambda e: self._preview_menu())
        Tooltip(self.preview_btn, PREVIEW_TIP)
        self.stop_preview_btn = self._pill(self.preview_bar, "Stop Preview", self.stop_preview,
                                           fg=ORANGE, edge=ORANGE, font=BOLD)
        self.stop_preview_btn.pack(side="left")
        self._sync_preview()
        self._sync_size_buttons()
        tk.Frame(self.frame, bg=p["line"], height=1).pack(fill="x")
        self.action_bar = tk.Frame(self.frame, bg=p["bg"])  # the actions, along the bottom
        self.action_bar.pack(side="bottom", fill="x", padx=14, pady=(0, 10))
        self._build_actions()

        holder = tk.Frame(self.frame, bg=p["bg"])
        holder.pack(fill="both", expand=True)
        canvas = tk.Canvas(holder, bg=p["bg"], highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.grid = tk.Frame(canvas, bg=p["bg"], padx=14, pady=0)
        window = canvas.create_window((0, 0), window=self.grid, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        self.grid.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def wheel(e):
            canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self.canvas = canvas

    # --- the actions ---

    def _action_button(self, parent, text, command, tip, quiet=False):
        """quiet: Save as Playlist, an outline rather than the full action look."""
        b = tk.Label(parent, text=text, font=BOLD, compound="center", bd=0, bg=self.p["bg"])
        b._quiet = quiet
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: self._paint_action(b, hover=True), add="+")
        b.bind("<Leave>", lambda e: self._paint_action(b), add="+")
        Tooltip(b, tip)
        return b

    def _paint_action(self, b, hover=False):
        p, ok = self.p, self._can_act()
        hover = hover and ok
        w, h = self._text_width(b.cget("text"), BOLD) + 24, 28
        if b._quiet:
            fill, edge, fg = (p["row_on"] if hover else p["bg"]), (p["line"] if ok else p["line"]), \
                (p["accent"] if ok else p["act_dim"])
        elif ok:
            fill, edge, fg = (p["act_hover"] if hover else p["act_bg"]), p["accent"], p["act_fg"]
        else:
            fill, edge, fg = (p["bg"] if p is DARK else p["act_dim"]), p["act_dim"], p["act_dim_fg"]
        img = self._shape(w, h, fill, edge, radius=7)
        b.config(image=img, fg=fg, cursor="hand2" if ok else "")
        b._img = img

    def _build_actions(self):
        p = self.p
        bar = self.action_bar
        tk.Frame(bar, bg=p["line"], height=1).pack(fill="x", pady=(0, 12))
        row = tk.Frame(bar, bg=p["bg"])
        row.pack(fill="x")
        self.jriver_actions = tk.Frame(row, bg=p["bg"])   # the four, for a zone
        self.jriver_actions.pack(side="left")
        for n, (how, text, tip) in enumerate(ACTIONS):
            if n == 2:   # the two Adds, then the two Load as New
                tk.Frame(self.jriver_actions, bg=p["line"], width=1, height=self._px(24)).pack(side="left",
                                                                                         padx=(2, 10))
            b = self._action_button(self.jriver_actions, text, lambda h=how: self._act(h), tip)
            b.pack(side="left", padx=(0, 8))
            self._buttons[how] = b
        self.youtube_actions = tk.Frame(row, bg=p["bg"])  # Output on YouTube: just the one
        self._buttons["youtube"] = self._action_button(self.youtube_actions, "Play on YouTube", self._youtube,
                                                       YOUTUBE_TIP)
        self._buttons["youtube"].pack(side="left")
        save = self._action_button(row, "Save as Playlist", self._save, SAVE_TIP, quiet=True)
        save.pack(side="right")
        self._buttons["save"] = save
        # What last happened, kept for the tests and the console; not shown (the console says it)
        self.status_label = tk.Label(bar, text="", font=FONT, bg=p["bg"], fg=p["muted"], anchor="w")
        self._show_output_actions()

    def _can_act(self):
        return bool(self.order) and not self.busy

    def _sync_buttons(self):
        for b in self._buttons.values():
            self._paint_action(b)

    # --- where the actions go: Output, read when pressed ---

    def output_is_youtube(self):
        try:
            return self.play.output_var.get() == "YouTube"
        except (AttributeError, tk.TclError):
            return False

    def output_choice(self):
        try:
            return self.play.output_var.get()
        except (AttributeError, tk.TclError):
            return ""

    def target_zone(self, choice=None):
        """The zone Output points at: a named zone, or the Now Playing zone for Same Zone.
        None for YouTube, or when the zone isn't in JRiver. Pass choice (read on Tk's thread)
        when calling from a worker thread."""
        if choice is None:
            choice = self.output_choice()
        if choice == "YouTube":
            return None
        if choice and choice != SAME_ZONE:
            return engine.zone_id(choice)
        zid = engine.seed_zone()
        return engine.zone_id() if zid == engine.ACTIVE_ZONE else zid

    def _show_output_actions(self):
        youtube = self.output_is_youtube()
        (self.youtube_actions if youtube else self.jriver_actions).pack(side="left")
        (self.jriver_actions if youtube else self.youtube_actions).pack_forget()

    def output_changed(self):
        """Output was changed on the Play tab: swap the buttons and recheck the Preview zone."""
        self._show_output_actions()
        was = self.preview_zone
        self._refresh_preview_zone()
        if self.rows and bool(was) != bool(self.preview_zone):
            self._render(keep_scroll=True)
        self._sync_preview()
        self._sync_buttons()

    def _run(self, work):
        """Runs a JRiver call off the main thread, then reports it in the console and under the actions."""
        self.busy = True
        self._sync_buttons()
        self.status_label.config(text="Sending...")

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
        keys, choice = list(self.order), self.output_choice()
        self.stop_preview(quiet=True)

        def work():
            zone = self.target_zone(choice)
            if zone is None:
                return "Problem: the Output zone isn't in JRiver, so nothing was sent. Pick another under Output."
            return engine.review_send(keys, how, zone)
        self._run(work)

    def _youtube(self):
        """Output on YouTube: the ticked tracks, in tick order, open as a YouTube playlist."""
        if not self._can_act():
            return
        rows = {r["key"]: r for r in self.rows}
        pairs = [(rows[k].get("artist", ""), rows[k].get("title", "")) for k in self.order if k in rows]
        self.stop_preview(quiet=True)

        def work():
            ids = engine.youtube_ids_for_pairs(pairs)
            sent = engine.open_youtube_playlist(ids)
            missed = len(pairs) - len([i for i in ids if i])
            n = f"{sent} track{'' if sent == 1 else 's'}"
            if not sent:
                return "Problem: YouTube had none of those tracks, so nothing was opened."
            return f"Review: {n} opened on YouTube" + (f", {missed} not found there." if missed else ".")
        self._run(work)

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
        was_showing = self.showing
        self.showing, self.dot = False, False
        if was_showing:
            self.frame.pack_forget()
            self._restore_console()   # puts the arrow back, beside the switch
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
        p = self.p
        for c, (title, width, stretch) in enumerate(columns):
            self.grid.grid_columnconfigure(c, weight=stretch)
            tk.Label(self.grid, text=title, font=self._font(-1, True), bg=p["bg"], fg=p["muted"], width=width, padx=4,
                     anchor="e" if title in ("Time", "BPM") else "w").grid(
                row=0, column=c, sticky="ew", pady=(7, 5))
        tk.Frame(self.grid, bg=p["line"], height=1).grid(row=1, column=0, columnspan=len(columns), sticky="ew")
        r = 2
        for row in self.rows:
            key = row["key"]
            tick = tk.Label(self.grid, text="", font=self._font(0, True), bd=0, compound="center", bg=p["bg"],
                            cursor="hand2")
            tick.grid(row=r, column=0, sticky="nsew", padx=0, pady=0, ipady=3)
            values = (row.get("artist", ""), row.get("title", ""), row.get("album", ""),
                      clock(row.get("seconds")), row.get("bpm", ""))
            texts = []
            for c, value in enumerate(values, start=1):
                cell = tk.Label(self.grid, text=value, font=self._font(), bg=p["bg"],
                                fg=p["text"] if c <= 2 else p["muted"],
                                cursor="hand2", padx=4, pady=3, width=COLUMNS[c][1], anchor="e" if c >= 4 else "w")
                cell.grid(row=r, column=c, sticky="nsew")   # no gaps, so a ticked row shades as one band
                texts.append(cell)
            for w in [tick] + texts:   # the whole row is the target: tick or untick
                w.bind("<Button-1>", lambda e, k=key: self.toggle(k))
            self._cells[key] = (tick, texts)
            if self.preview_zone:   # the Preview mark: plays this track in the preview zone, doesn't tick it
                mark = tk.Label(self.grid, text=PLAY_MARK, font=self._font(-2), bd=0, compound="center",
                                bg=p["bg"], cursor="hand2", width=self._px(46 * self._k()))   # pixels: it has an image
                mark.grid(row=r, column=len(COLUMNS), sticky="nsew")
                mark.bind("<Button-1>", lambda e, k=key: self._preview_click(k))
                self._marks[key] = mark
            tk.Frame(self.grid, bg=p["line"], height=1).grid(row=r + 1, column=0, columnspan=len(columns),
                                                             sticky="ew")
            r += 2
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(top if keep_scroll else 0)
        self._restyle()

    def _restyle(self):
        p = self.p
        for n_row, (key, (tick, texts)) in enumerate(self._cells.items()):
            on, prev = key in self.order, key == self.previewing
            plain = p["stripe"] if n_row % 2 else p["bg"]   # every other row a shade off, to follow along
            bg = p["row_prev"] if prev else (p["row_on"] if on else plain)
            side = round(26 * self._k())
            box = self._shape(side, side, p["tick_on_bg"] if on else bg, p["accent"] if on else p["tick_off"],
                              line=2, radius=5)
            tick.config(text=str(self.order.index(key) + 1) if on else "", image=box, bg=bg,
                        fg=p["tick_on_fg"] if on else p["accent"])
            tick._img = box
            for n, cell in enumerate(texts):
                cell.config(bg=bg, font=self._font(0, on and n < 2))
            mark = self._marks.get(key)
            if mark is not None:
                edge = ORANGE if prev else p["line"]
                img = self._shape(round(30 * self._k()), round(24 * self._k()), bg, edge, radius=5)
                mark.config(bg=bg, image=img, fg=ORANGE if prev else p["accent"],
                            text=STOP_MARK if prev else PLAY_MARK)
                mark._img = img
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
            if zid is not None and str(zid) == str(self.target_zone()):
                zid = None   # never the room the list is going to
        self.preview_zone = zid

    def _sync_preview(self):
        shown = self.preview_name if self.preview_zone else "None"
        self.preview_btn.config(text=f"{shown} \u25be", fg=ORANGE if self.preview_zone else self.p["muted"])
        on = self.previewing is not None
        if on:
            self._paint_pill(self.stop_preview_btn)
        else:
            self._paint_pill(self.stop_preview_btn, fg=self.p["line"] if self.p is DARK else self.p["tick_off"],
                             edge=self.p["line"])
        self.stop_preview_btn.config(cursor="hand2" if on else "")

    def preview_choices(self):
        """The zones offered for Preview: every JRiver zone except the one Output sends to."""
        try:
            zones = engine._zone_list(fresh=True)
        except Exception:
            zones = []
        target = self.target_zone()
        return [name for zid, name in zones if str(zid) != str(target)]

    def _preview_menu(self):
        p = self.p
        menu = tk.Menu(self.frame, tearoff=0, bg=p["bg"], fg=p["text"], activebackground=p["row_on"],
                       activeforeground=p["accent"], font=FONT)
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
                line = f"Problem: Preview couldn't play that in {where} ({e})."
                self.status_label.config(text=line)
                self.play._append_log(time.strftime("%H:%M") + "  " + line)
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

    # --- text size (A- and A+) ---

    def _k(self):
        """How much bigger than the standard size the track list is drawn."""
        return self.size / SIZE_DEFAULT

    def _font(self, step=0, bold=False):
        return ("Segoe UI", max(6, self.size + step)) + (("bold",) if bold else ())

    def set_size(self, size):
        size = min(SIZE_MAX, max(SIZE_MIN, size))
        if size == self.size:
            return
        self.size = size
        write_env({"REVIEW_FONT_SIZE": str(size)})
        if self.rows:
            self._render(keep_scroll=True)
        self._sync_size_buttons()

    def _sync_size_buttons(self):
        p = self.p
        for b, ok in ((self.smaller_btn, self.size > SIZE_MIN), (self.bigger_btn, self.size < SIZE_MAX)):
            if ok:
                self._paint_pill(b)
            else:
                self._paint_pill(b, fg=p["line"] if p is DARK else p["tick_off"])
            b.config(cursor="hand2" if ok else "")

    # --- the console's arrow, beside the switch ---

    def dock_arrow(self):
        """While the Console | Review switch shows on Console, the tabs arrow sits centred in the
        switch's row, so the console text starts where it always did."""
        arrow = self.play.head_arrow
        if self.showing or not self.switch_row.winfo_manager():
            return
        if arrow.winfo_manager() == "pack":
            arrow.pack_forget()
        arrow.place_forget()
        arrow.config(bg=CONSOLE["bg"])
        arrow.place(in_=self.switch_row, relx=0.5, rely=0.5, anchor="center")
        arrow.lift()
