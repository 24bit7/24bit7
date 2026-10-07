"""
review_gui.py - the Review view, in the console area of the Play tab.

A build with Behaviour set to Review sends nothing to JRiver. Its tracks are listed
here instead: tick the ones you want, in the order you want them (each tick shows its
number), then choose what to do with them. A Console | Review switch above the console
moves between the two; the console keeps running underneath, and a dot on Console says
something new arrived there while Review was showing.

The list stays until the next Review build replaces it.
"""
import tkinter as tk
from tkinter import ttk

BLACK, GREEN, DIM, WHITE, MUTED = "#000000", "#00ff41", "#0d4d1c", "#ffffff", "#7fbf8f"
ROW_ON = "#0b2412"            # a ticked row
FONT, BOLD = ("Consolas", 9), ("Consolas", 9, "bold")
DOT = "\u25cf"

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
        self._cells = {}          # key -> (tick label, [text labels])
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
        tk.Frame(self.frame, bg=GREEN, height=1).pack(fill="x", padx=8)
        self.action_bar = tk.Frame(self.frame, bg=BLACK)  # the actions, along the bottom
        self.action_bar.pack(side="bottom", fill="x", padx=8, pady=(6, 8))

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
        self.rows = [dict(r) for r in rows or []]
        self.order, self.title, self.zone = [], title, zone
        self._render()
        if self.rows:
            self.show_review()

    def _render(self):
        for child in self.grid.winfo_children():
            child.destroy()
        self._cells = {}
        for c, (title, width, stretch) in enumerate(COLUMNS):
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
            tk.Frame(self.grid, bg=DIM, height=1).grid(row=r + 1, column=0, columnspan=len(COLUMNS), sticky="ew")
            r += 2
        self.canvas.yview_moveto(0)
        self._restyle()

    def _restyle(self):
        for key, (tick, texts) in self._cells.items():
            on = key in self.order
            bg = ROW_ON if on else BLACK
            tick.config(text=str(self.order.index(key) + 1) if on else "",
                        highlightbackground=GREEN if on else DIM, highlightcolor=GREEN if on else DIM)
            for cell in texts:
                cell.config(bg=bg, font=BOLD if on else FONT)
        n = len(self.rows)
        self.title_label.config(text=self.title)
        self.count_label.config(text=f"{n} track{'' if n == 1 else 's'}, {len(self.order)} ticked")
        self._style_switch()

    def toggle(self, key):
        """Ticking adds the track at the end of the order; unticking closes the gap."""
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
