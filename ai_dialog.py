"""
ai_dialog.py - the AI Playlist window (the 7 Oct 2026 "24bit7 AI Playlist" mockups).

A rounded window with two modes on a switch:
  Create  a new playlist from a theme: a Theme box, Ideas as chips (More tracks like
          what's playing, then the AI's suggestions), Tracks, If Short, Build Playlist.
  Steer   move what's playing in a direction (the next build).

Everything chosen here is remembered in .env for next time, the mode included:
  AI_DIALOG_MODE    create | steer
  AI_CREATE_THEME   the last theme typed
  VIBE_TRACK_COUNT  Tracks for Create (the same setting as Settings > Playlist)
  AI_IF_SHORT       ask | drift | leave   (what happens when fewer tracks match than asked)
"""
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont

import engine
from settings_gui import Tooltip, read_env, write_env
from tabs import PALETTE, rounded_shape

W = 540                    # the window's width in CSS pixels (scaled for the display); it's as tall as its content
PAD = 22
FONT_FAMILY = "Segoe UI"
GWL_STYLE, WS_CAPTION, SWP_FRAME = -16, 0x00C00000, 0x0027
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
IF_SHORT = [("ask", "Ask Again"), ("drift", "Drift"), ("leave", "Leave Short")]
IF_SHORT_TIP = ("When fewer tracks match your library than you asked for: Ask Again asks the AI for more "
                "(up to two more rounds), Drift tops up from your music sources, Leave Short stops there.")
COUNT_MIN, COUNT_MAX = 5, 100


class AIPlaylistDialog(tk.Toplevel):
    def __init__(self, master, on_create, play=None):
        super().__init__(master)
        self.on_create = on_create
        self.play = play
        self.p = PALETTE
        self.ai = PALETTE["ai_purple"]
        try:
            self.scale = max(1.0, master.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            self.scale = 1.0
        env = read_env()
        self.mode = "steer" if env.get("AI_DIALOG_MODE", "").strip() == "steer" else "create"
        self.if_short = env.get("AI_IF_SHORT", "ask").strip() or "ask"
        if self.if_short not in dict(IF_SHORT):
            self.if_short = "ask"
        self.like_text = None
        self._images = []
        self._later = queue.Queue()   # work handed from background threads to Tk's thread

        # An owned window: always above 24bit7, never above anything else, no focus grabbing.
        # Its own title bar goes (Windows), the header below is the handle; Windows 11 rounds the corners.
        self.title("AI Playlist")
        self.transient(master)
        self.resizable(False, False)
        self.configure(bg=self.p["line"], padx=max(1, self._px(1)), pady=max(1, self._px(1)))   # a 1px edge
        self.body = tk.Frame(self, bg=self.p["window_bg"], padx=self._px(PAD), pady=self._px(PAD),
                             width=self._px(W))
        self.body.pack(fill="both", expand=True)
        self.body.pack_propagate(True)
        self._build()
        self.withdraw()
        self.after(10, lambda: self._show_over(master))
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(100, self._drain_later)
        threading.Thread(target=self._load_playing, daemon=True).start()
        threading.Thread(target=self._load_suggestions, daemon=True).start()

    # --- small drawn pieces ---

    def _px(self, n):
        return int(round(n * self.scale))

    def _font(self, size=10, bold=False):
        return (FONT_FAMILY, size) + (("bold",) if bold else ())

    def _width_of(self, text, font):
        return tkfont.Font(root=self, font=font).measure(text) / self.scale

    def _button(self, parent, text, command, fill=None, edge=None, fg=None, bold=True, pad=28, h=34, font_size=10):
        """A rounded button drawn as an image with the text on top."""
        p = self.p
        font = self._font(font_size, bold)
        img = rounded_shape(self, self._px(self._width_of(text, font) + pad), self._px(h), self._px(8),
                            fill or p["field_bg"], edge or p["line"], max(1, self._px(1)))
        self._images.append(img)
        b = tk.Label(parent, text=text, image=img, compound="center", font=font, bd=0, bg=p["window_bg"],
                     fg=fg or p["text"], cursor="hand2")
        b.bind("<Button-1>", lambda e: command())
        return b

    def _chip(self, parent, text, command, on=False):
        p = self.p
        font = self._font(9, True)
        img = rounded_shape(self, self._px(self._width_of(text, font) + 26), self._px(30), self._px(15),
                            self.ai if on else p["field_bg"], self.ai if on else p["line"], max(1, self._px(1)))
        self._images.append(img)
        c = tk.Label(parent, text=text, image=img, compound="center", font=font, bd=0, bg=p["window_bg"],
                     fg=(self._on_ai() if on else p["text"]), cursor="hand2")
        c.bind("<Button-1>", lambda e: command())
        return c

    def _on_ai(self):
        """Text colour on a magenta fill: black on the bright dark-theme magenta, white otherwise."""
        return "#000000" if self.ai.lower() in ("#ff33ff",) else "#ffffff"

    def _segment(self, parent, items, chosen, command, ai=False):
        """A row of choices in one rounded group; items are (code, label). Returns the frame."""
        p = self.p
        box = tk.Frame(parent, bg=p["window_bg"])
        edge = tk.Frame(box, bg=p["line"], padx=max(1, self._px(1)), pady=max(1, self._px(1)))
        edge.pack()
        inner = tk.Frame(edge, bg=p["field_bg"])
        inner.pack()
        box.buttons = {}
        for code, label in items:
            on = code == chosen
            if ai:
                fill, fg = (self.ai, self._on_ai()) if on else (p["field_bg"], p["text_secondary"])
            else:
                fill, fg = (p["window_bg"], p["brand_blue"]) if on else (p["field_bg"], p["text_secondary"])
            b = tk.Label(inner, text=label, font=self._font(10, True), bg=fill, fg=fg, padx=self._px(16),
                         pady=self._px(8), cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, c=code: command(c))
            box.buttons[code] = b
        return box

    def _label(self, parent, text):
        return tk.Label(parent, text=text, font=self._font(9, True), bg=self.p["window_bg"],
                        fg=self.p["text_secondary"], anchor="w")

    def _entry(self, parent, width=None):
        e = tk.Entry(parent, font=self._font(10), bg=self.p["field_bg"], fg=self.p["text"],
                     insertbackground=self.p["text"], relief="flat", highlightthickness=1,
                     highlightbackground=self.p["line"], highlightcolor=self.ai, bd=0)
        if width:
            e.config(width=width)
        return e

    # --- the window ---

    def _build(self):
        p, body = self.p, self.body
        head = tk.Frame(body, bg=p["window_bg"])
        head.pack(fill="x")
        tk.Label(head, text="AI Playlist", font=self._font(16, True), bg=p["window_bg"], fg=self.ai).pack(side="left")
        close = tk.Label(head, text="\u2715", font=self._font(12), bg=p["window_bg"], fg=p["text_secondary"],
                         cursor="hand2", padx=self._px(8))
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.destroy())
        for w in (head,) + tuple(head.winfo_children()[:1]):   # drag the window by its header
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        modes = tk.Frame(body, bg=p["window_bg"])
        modes.pack(fill="x", pady=(self._px(14), 0))
        self.mode_switch = self._segment(modes, [("create", "Create"), ("steer", "Steer")], self.mode,
                                         self.set_mode, ai=True)
        self.mode_switch.pack(side="left")
        self.mode_note = tk.Label(modes, text="", font=self._font(9), bg=p["window_bg"], fg=p["text_faint"])
        self.mode_note.pack(side="left", padx=(self._px(14), 0))

        self.page = tk.Frame(body, bg=p["window_bg"], width=self._px(W - 2 * PAD))
        self.page.pack(fill="both", expand=True, pady=(self._px(18), 0))
        tk.Frame(body, bg=p["window_bg"], width=self._px(W - 2 * PAD), height=1).pack()   # holds the width

        foot = tk.Frame(body, bg=p["window_bg"])
        foot.pack(side="bottom", fill="x")
        tk.Frame(foot, bg=p["line"], height=1).pack(fill="x", pady=(0, self._px(14)))
        row = tk.Frame(foot, bg=p["window_bg"])
        row.pack(fill="x")
        tk.Label(row, text="Everything here is remembered for next time.", font=self._font(9), bg=p["window_bg"],
                 fg=p["text_faint"]).pack(side="left")
        self.go_btn = self._button(row, "Build Playlist", self.submit, fill=self.ai, edge=self.ai, fg=self._on_ai())
        self.go_btn.pack(side="right")
        self._button(row, "Cancel", self.destroy).pack(side="right", padx=(0, self._px(10)))
        self._show_mode()

    def set_mode(self, mode):
        if mode == "steer":   # the next build: shown, not yet usable
            self.mode_note.config(text="Steer is coming in the next build.")
            return
        self.mode = mode
        write_env({"AI_DIALOG_MODE": mode})
        for code, b in self.mode_switch.buttons.items():
            on = code == mode
            b.config(bg=self.ai if on else self.p["field_bg"], fg=self._on_ai() if on else self.p["text_secondary"])
        self._show_mode()

    def _show_mode(self):
        for w in self.page.winfo_children():
            w.destroy()
        self.mode_note.config(text="A new playlist from a theme.")
        self._build_create()

    # --- Create ---

    def _build_create(self):
        p, page = self.p, self.page
        env = read_env()
        self._label(page, "Theme").pack(anchor="w")
        self.theme = self._entry(page)
        self.theme.pack(fill="x", ipady=self._px(6), pady=(self._px(6), 0))
        self.theme.insert(0, env.get("AI_CREATE_THEME", "").strip())
        self.theme.bind("<Return>", lambda e: self.submit())
        self.placeholder = tk.Label(page, text="A mood, a place, a decade, a feeling...", font=self._font(10),
                                    bg=p["field_bg"], fg=p["text_faint"])
        self._sync_placeholder()
        self.theme.bind("<KeyRelease>", lambda e: self._sync_placeholder(), add="+")
        self.theme.bind("<FocusIn>", lambda e: self._sync_placeholder(), add="+")
        self.theme.bind("<FocusOut>", lambda e: self._sync_placeholder(), add="+")

        self._label(page, "Ideas").pack(anchor="w", pady=(self._px(18), self._px(8)))
        self.ideas = tk.Frame(page, bg=p["window_bg"])
        self.ideas.pack(fill="x")
        self.ideas_note = tk.Label(self.ideas, text="Thinking...", font=self._font(9), bg=p["window_bg"],
                                   fg=p["text_faint"])
        self.ideas_note.pack(anchor="w")
        self.idea_chips = []

        opts = tk.Frame(page, bg=p["window_bg"])
        opts.pack(fill="x", pady=(self._px(22), self._px(8)))
        col = tk.Frame(opts, bg=p["window_bg"])
        col.pack(side="left")
        self._label(col, "Tracks").pack(anchor="w")
        self.count = self._entry(col, width=5)
        self.count.pack(anchor="w", ipady=self._px(6), pady=(self._px(6), 0))
        self.count.insert(0, (env.get("VIBE_TRACK_COUNT") or "").strip() or str(getattr(engine, "VIBE_TRACK_COUNT", 20)))
        Tooltip(self.count, f"How many tracks to ask for, {COUNT_MIN} to {COUNT_MAX}. Also under Settings > Playlist.")
        col2 = tk.Frame(opts, bg=p["window_bg"])
        col2.pack(side="left", padx=(self._px(28), 0))
        lab = self._label(col2, "If Short")
        lab.pack(anchor="w")
        Tooltip(lab, IF_SHORT_TIP, click=False)
        self.if_short_switch = self._segment(col2, IF_SHORT, self.if_short, self.set_if_short)
        self.if_short_switch.pack(anchor="w", pady=(self._px(6), 0))

    def _sync_placeholder(self):
        if self.theme.get().strip() or self.focus_get() is self.theme:
            self.placeholder.place_forget()
        else:
            self.placeholder.place(in_=self.theme, x=self._px(8), rely=0.5, anchor="w")
            self.placeholder.bind("<Button-1>", lambda e: self.theme.focus_set())

    def set_if_short(self, code):
        self.if_short = code
        write_env({"AI_IF_SHORT": code})
        for c, b in self.if_short_switch.buttons.items():
            on = c == code
            b.config(bg=self.p["window_bg"] if on else self.p["field_bg"],
                     fg=self.p["brand_blue"] if on else self.p["text_secondary"])

    def _load_playing(self):
        try:
            info = engine.get_playing_info()
        except Exception:
            info = None
        self._later.put(lambda: self._show_playing(info))

    def _show_playing(self, info):
        if not self.winfo_exists() or self.mode != "create":
            return
        title = ((info or {}).get("Name") or "").strip()
        artist = ((info or {}).get("Artist") or "").split(";")[0].strip()
        if not info or info.get("PlayingNowPosition") == "-1" or not title or title == "Unknown":
            return
        shown = title if len(title) <= 40 else title[:37].rstrip() + "..."
        by = f" by {engine.deinvert_the(artist)}" if artist and artist != "Unknown" else ""
        self.like_text = f'More tracks like "{title}"{by}, with the same tone, energy and mood'
        self._add_idea(f'More tracks like "{shown}"', self.like_text, first=True)

    def _load_suggestions(self):
        try:
            ideas = engine.ai_vibe_suggestions()
        except Exception:
            ideas = []
        self._later.put(lambda: self._show_suggestions(ideas))

    def _show_suggestions(self, ideas):
        if not self.winfo_exists() or self.mode != "create":
            return
        self.ideas_note.pack_forget()
        if not ideas and not self.idea_chips:
            self.ideas_note.config(text="(no suggestions right now)")
            self.ideas_note.pack(anchor="w")
        for idea in ideas:
            self._add_idea(idea, idea)

    def _add_idea(self, shown, text, first=False):
        """A chip in the Ideas row; rows wrap at the window's width."""
        if not self.winfo_exists():
            return
        chip = self._chip(self.ideas, shown, lambda t=text: self._use(t))
        self.idea_chips.insert(0 if first else len(self.idea_chips), chip)
        self._flow_ideas()

    def _flow_ideas(self):
        """Lays the chips out in rows that fit the window's width."""
        limit, gap = self._px(W - 2 * PAD), self._px(8)
        x, row, col = 0, 0, 0
        for c in self.idea_chips:
            c.update_idletasks()
            w = c.winfo_reqwidth()
            if x and x + w > limit:
                row, x, col = row + 1, 0, 0
            c.grid(row=row, column=col, sticky="w", padx=(0, gap), pady=(0, gap))
            x += w + gap
            col += 1

    def _use(self, text):
        self.theme.delete(0, "end")
        self.theme.insert(0, text)
        self._sync_placeholder()
        self.theme.focus_set()

    def count_value(self):
        try:
            return min(COUNT_MAX, max(COUNT_MIN, int(self.count.get().strip())))
        except ValueError:
            return getattr(engine, "VIBE_TRACK_COUNT", 20)

    def submit(self):
        if self.mode != "create":
            return
        theme = self.theme.get().strip()
        if not theme:
            self.theme.focus_set()
            return
        count = self.count_value()
        write_env({"AI_CREATE_THEME": theme, "VIBE_TRACK_COUNT": str(count)})
        self.destroy()
        self.on_create(theme, count)

    # --- window mechanics ---

    def _drain_later(self):
        """Runs what the background threads handed over, on Tk's thread."""
        try:
            while True:
                self._later.get_nowait()()
        except queue.Empty:
            pass
        except tk.TclError:
            return
        if self.winfo_exists():
            self.after(100, self._drain_later)

    def _show_over(self, master):
        """Sized to its content, centred over 24bit7, then shown."""
        try:
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            x = master.winfo_rootx() + (master.winfo_width() - w) // 2
            y = master.winfo_rooty() + max(0, (master.winfo_height() - h) // 2)
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
            self._strip_title_bar()
            self.deiconify()
            self.lift()
            if self.mode == "create":
                self.theme.focus_set()
        except tk.TclError:
            pass

    def _strip_title_bar(self):
        """Windows: no title bar of its own (the header is the handle), rounded corners on Windows 11."""
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                return
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_CAPTION)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FRAME)
            pref = ctypes.c_int(DWMWCP_ROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref),
                                                       ctypes.sizeof(pref))
        except Exception:
            pass   # not Windows, or an older one: a plain window, which is fine

    def _drag_start(self, event):
        self._drag = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _drag_move(self, event):
        dx, dy = self._drag
        self.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
