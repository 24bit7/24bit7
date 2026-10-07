"""
ai_dialog.py - the AI Playlist window (the 7 Oct 2026 "24bit7 AI Playlist" mockups).

A rounded window with two modes on a switch:
  Create  a new playlist from a theme: a Theme box, Ideas as chips (More tracks like
          what's playing, then the AI's suggestions), Tracks, If Short, Build Playlist.
  Steer   move what's playing in a direction: a Seed (Currently Playing or Playing Now (All)),
          an optional Tone (Assess Tone asks the AI for one), Direction chips plus your own
          words, A Little or A Lot, Tracks, If Short, Steer.

Everything chosen here is remembered in .env for next time, the mode included:
  AI_DIALOG_MODE     create | steer
  AI_CREATE_THEME    the last theme typed
  VIBE_TRACK_COUNT   Tracks for Create (the same setting as Settings > Playlist)
  AI_IF_SHORT        ask | drift | leave   (what happens when fewer tracks match than asked)
  AI_STEER_SEED      current | all
  AI_STEER_TONE      the tone phrase, assessed or typed
  AI_STEER_DIRS      the chosen direction codes, comma-separated (engine.STEER_DIRECTIONS)
  AI_STEER_OWN       your own words
  AI_STEER_STRENGTH  little | lot
  AI_STEER_COUNT     Tracks for Steer
"""
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont

import engine
from settings_gui import Tooltip, read_env, write_env
from tabs import PALETTE, rounded_shape

W = 620                    # the window's width in CSS pixels (scaled for the display); it's as tall as its content
PAD = 18
GAP = 12                   # between sections
FONT_FAMILY = "Segoe UI"
GWL_STYLE, WS_CAPTION, SWP_FRAME = -16, 0x00C00000, 0x0027
DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND = 33, 2
IF_SHORT = [("ask", "Ask Again"), ("drift", "Drift"), ("leave", "Leave Short")]
IF_SHORT_TIP = ("When fewer tracks match your library than you asked for: Ask Again asks the AI for more "
                "(up to two more rounds), Drift tops up from your music sources, Leave Short stops there.")
COUNT_MIN, COUNT_MAX = 5, 100


class AIPlaylistDialog(tk.Toplevel):
    def __init__(self, master, on_create, play=None, on_steer=None):
        super().__init__(master)
        self.withdraw()   # built out of sight: shown once, dressed and in place, with no flicker
        self.on_create = on_create
        self.on_steer = on_steer
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
        self.seed_kind = "all" if env.get("AI_STEER_SEED", "").strip() == "all" else "current"
        self.strength = "lot" if env.get("AI_STEER_STRENGTH", "").strip() == "lot" else "little"
        self.directions = [d for d in env.get("AI_STEER_DIRS", "").split(",") if d in dict(engine.STEER_DIRECTIONS)]
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

    def _button(self, parent, text, command, fill=None, edge=None, fg=None, bold=True, pad=24, h=30, font_size=10):
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
        img = rounded_shape(self, self._px(self._width_of(text, font) + 22), self._px(26), self._px(13),
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
            b = tk.Label(inner, text=label, font=self._font(9, True), bg=fill, fg=fg, padx=self._px(12),
                         pady=self._px(5), cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, c=code: command(c))
            box.buttons[code] = b
        return box

    def _flow(self, box, makers):
        """Lays chips out in rows that fit the window's width. makers: callables taking the row frame."""
        for w in box.winfo_children():
            w.destroy()
        limit, gap = self._px(W - 2 * PAD), self._px(6)
        row = tk.Frame(box, bg=self.p["window_bg"])
        row.pack(anchor="w", pady=(0, gap))
        x, out = 0, []
        for make in makers:
            chip = make(row)
            chip.update_idletasks()
            w = chip.winfo_reqwidth()
            if x and x + w > limit:
                chip.destroy()
                row = tk.Frame(box, bg=self.p["window_bg"])
                row.pack(anchor="w", pady=(0, gap))
                chip, x = make(row), 0
                chip.update_idletasks()
                w = chip.winfo_reqwidth()
            chip.pack(side="left", padx=(0, gap))
            x += w + gap
            out.append(chip)
        return out

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
        tk.Label(head, text="AI Playlist", font=self._font(14, True), bg=p["window_bg"], fg=self.ai).pack(side="left")
        close = tk.Label(head, text="\u2715", font=self._font(12), bg=p["window_bg"], fg=p["text_secondary"],
                         cursor="hand2", padx=self._px(8))
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.destroy())
        for w in (head,) + tuple(head.winfo_children()[:1]):   # drag the window by its header
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        modes = tk.Frame(body, bg=p["window_bg"])
        modes.pack(fill="x", pady=(self._px(8), 0))
        self.mode_switch = self._segment(modes, [("create", "Create"), ("steer", "Steer")], self.mode,
                                         self.set_mode, ai=True)
        self.mode_switch.pack(side="left")
        self.mode_note = tk.Label(modes, text="", font=self._font(9), bg=p["window_bg"], fg=p["text_faint"])
        self.mode_note.pack(side="left", padx=(self._px(14), 0))

        self.page = tk.Frame(body, bg=p["window_bg"], width=self._px(W - 2 * PAD))
        self.page.pack(fill="both", expand=True, pady=(self._px(GAP), 0))
        tk.Frame(body, bg=p["window_bg"], width=self._px(W - 2 * PAD), height=1).pack()   # holds the width

        foot = tk.Frame(body, bg=p["window_bg"])
        foot.pack(side="bottom", fill="x")
        tk.Frame(foot, bg=p["line"], height=1).pack(fill="x", pady=(0, self._px(10)))
        row = tk.Frame(foot, bg=p["window_bg"])
        row.pack(fill="x")
        tk.Label(row, text="Everything here is remembered for next time.", font=self._font(9), bg=p["window_bg"],
                 fg=p["text_faint"]).pack(side="left")
        self.go_btn = self._button(row, "Build Playlist", self.submit, fill=self.ai, edge=self.ai, fg=self._on_ai())
        self.go_btn.pack(side="right")
        self._button(row, "Cancel", self.destroy).pack(side="right", padx=(0, self._px(10)))
        self._show_mode()

    def set_mode(self, mode):
        self.mode = mode
        write_env({"AI_DIALOG_MODE": mode})
        for code, b in self.mode_switch.buttons.items():
            on = code == mode
            b.config(bg=self.ai if on else self.p["field_bg"], fg=self._on_ai() if on else self.p["text_secondary"])
        self._show_mode()

    def _show_mode(self):
        for w in self.page.winfo_children():
            w.destroy()
        if self.mode == "steer":
            self.mode_note.config(text="Move what's playing in a direction.")
            self.go_btn.config(text="Steer")
            self._build_steer()
        else:
            self.mode_note.config(text="A new playlist from a theme.")
            self.go_btn.config(text="Build Playlist")
            self._build_create()
        self._paint_go()
        self.after(10, self._fit)

    def _paint_go(self):
        img = rounded_shape(self, self._px(self._width_of(self.go_btn.cget("text"), self._font(10, True)) + 24),
                            self._px(30), self._px(8), self.ai, self.ai, max(1, self._px(1)))
        self._images.append(img)
        self.go_btn.config(image=img)

    def _fit(self):
        """The window grows or shrinks to the mode showing."""
        try:
            self.update_idletasks()
            self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")
        except tk.TclError:
            pass

    def _options_row(self, page, count_key, count_default):
        """Tracks and If Short, shared by both modes."""
        p = self.p
        env = read_env()
        opts = tk.Frame(page, bg=p["window_bg"])
        opts.pack(fill="x", pady=(self._px(GAP), self._px(4)))
        col = tk.Frame(opts, bg=p["window_bg"])
        col.pack(side="left")
        self._label(col, "Tracks").pack(anchor="w")
        self.count = self._entry(col, width=5)
        self.count.pack(anchor="w", ipady=self._px(4), pady=(self._px(4), 0))
        self.count.insert(0, (env.get(count_key) or "").strip() or str(count_default))
        Tooltip(self.count, f"How many tracks to ask for, {COUNT_MIN} to {COUNT_MAX}.")
        col2 = tk.Frame(opts, bg=p["window_bg"])
        col2.pack(side="left", padx=(self._px(28), 0))
        lab = self._label(col2, "If Short")
        lab.pack(anchor="w")
        Tooltip(lab, IF_SHORT_TIP, click=False)
        self.if_short_switch = self._segment(col2, IF_SHORT, self.if_short, self.set_if_short)
        self.if_short_switch.pack(anchor="w", pady=(self._px(4), 0))

    # --- Steer ---

    def _build_steer(self):
        p, page = self.p, self.page
        env = read_env()
        self._label(page, "Seed").pack(anchor="w")
        seed_row = tk.Frame(page, bg=p["window_bg"])
        seed_row.pack(fill="x", pady=(self._px(4), 0))
        self.seed_switch = self._segment(seed_row, [("current", "Currently Playing"), ("all", "Playing Now (All)")],
                                         self.seed_kind, self.set_seed)
        self.seed_switch.pack(side="left")
        Tooltip(self.seed_switch, "Currently Playing steers from the one track on now. Playing Now (All) sends "
                                  f"the list around it, up to {engine.STEER_SEED_CAP} tracks.", click=False)
        self.seed_note = tk.Label(seed_row, text="", font=self._font(9), bg=p["window_bg"], fg=p["text_faint"])
        self.seed_note.pack(side="left", padx=(self._px(12), 0))
        threading.Thread(target=self._load_seed_note, daemon=True).start()

        self._label(page, "Tone (optional)").pack(anchor="w", pady=(self._px(GAP), 0))
        tone_row = tk.Frame(page, bg=p["window_bg"])
        tone_row.pack(fill="x", pady=(self._px(4), 0))
        self.tone = tk.Text(tone_row, height=2, width=10, wrap="word", font=self._font(10), bg=p["field_bg"],
                            fg=p["text"],
                            insertbackground=p["text"], relief="flat", highlightthickness=1,
                            highlightbackground=p["line"], highlightcolor=self.ai, bd=0,
                            padx=self._px(6), pady=self._px(4))
        self.tone.pack(side="left", fill="x", expand=True)
        self.tone.insert("1.0", env.get("AI_STEER_TONE", "").strip())
        self.assess_btn = self._button(tone_row, "Assess Tone", self.assess_tone, edge=self.ai, fg=self.ai,
                                       bold=True, pad=20, h=30, font_size=9)
        self.assess_btn.pack(side="left", padx=(self._px(10), 0), anchor="n")
        Tooltip(self.assess_btn, "Asks the AI to describe the seed's tone and puts it here. Uses AI credits. "
                                 "Left empty, the AI works from the seed and direction alone.", click=False)

        self._label(page, "Direction").pack(anchor="w", pady=(self._px(GAP), self._px(6)))
        self.dir_box = tk.Frame(page, bg=p["window_bg"])
        self.dir_box.pack(fill="x")
        self.dir_chips = {}
        self._paint_directions()
        own_row = tk.Frame(page, bg=p["window_bg"])
        own_row.pack(fill="x", pady=(self._px(2), 0))
        self.own = self._entry(own_row)
        self.own.pack(side="left", fill="x", expand=True, ipady=self._px(4))
        self.own.insert(0, env.get("AI_STEER_OWN", "").strip())
        self.own_placeholder = tk.Label(page, text="Your own words: more Latin, female vocals...",
                                        font=self._font(10), bg=p["field_bg"], fg=p["text_faint"])
        self._sync_own_placeholder()
        for ev in ("<KeyRelease>", "<FocusIn>", "<FocusOut>"):
            self.own.bind(ev, lambda e: self._sync_own_placeholder(), add="+")
        self.strength_switch = self._segment(own_row, [("little", "A Little"), ("lot", "A Lot")], self.strength,
                                             self.set_strength)
        self.strength_switch.pack(side="left", padx=(self._px(12), 0))
        Tooltip(self.strength_switch, "How far to move from the seed.", click=False)
        self._options_row(page, "AI_STEER_COUNT", 12)
        self.own.bind("<Return>", lambda ev: self.submit())
        self.tone.bind("<Return>", lambda ev: (self.submit(), "break")[1])

    def _paint_directions(self):
        chips = self._flow(self.dir_box, [
            (lambda row, code=code, label=label: self._chip(row, label, lambda: self.toggle_direction(code),
                                                            on=code in self.directions))
            for code, label in engine.STEER_DIRECTIONS])
        self.dir_chips = dict(zip([c for c, _ in engine.STEER_DIRECTIONS], chips))

    def toggle_direction(self, code):
        if code in self.directions:
            self.directions.remove(code)
        else:
            self.directions.append(code)
        write_env({"AI_STEER_DIRS": ",".join(self.directions)})
        self._paint_directions()

    def set_seed(self, kind):
        self.seed_kind = kind
        write_env({"AI_STEER_SEED": kind})
        self._restyle_segment(self.seed_switch, kind)
        threading.Thread(target=self._load_seed_note, daemon=True).start()

    def set_strength(self, strength):
        self.strength = strength
        write_env({"AI_STEER_STRENGTH": strength})
        self._restyle_segment(self.strength_switch, strength)

    def _restyle_segment(self, seg, chosen):
        for c, b in seg.buttons.items():
            on = c == chosen
            b.config(bg=self.p["window_bg"] if on else self.p["field_bg"],
                     fg=self.p["brand_blue"] if on else self.p["text_secondary"])

    def _sync_own_placeholder(self):
        if self.own.get().strip() or self.focus_get() is self.own:
            self.own_placeholder.place_forget()
        else:
            self.own_placeholder.place(in_=self.own, x=self._px(8), rely=0.5, anchor="w")
            self.own_placeholder.bind("<Button-1>", lambda e: self.own.focus_set())

    def _load_seed_note(self):
        try:
            pairs = engine.steer_seed_pairs(all_tracks=self.seed_kind == "all")
        except Exception:
            pairs = []
        self._later.put(lambda: self._show_seed_note(pairs))

    def _show_seed_note(self, pairs):
        if not self.winfo_exists() or self.mode != "steer":
            return
        if not pairs:
            self.seed_note.config(text="Nothing is playing.")
        elif len(pairs) == 1:
            a, t = pairs[0]
            self.seed_note.config(text=f"{a} - {t}"[:48])
        else:
            self.seed_note.config(text=f"{len(pairs)} tracks")

    def assess_tone(self):
        if getattr(self, "_assessing", False):
            return
        self._assessing = True
        self.assess_btn.config(text="Assessing...")
        kind = self.seed_kind

        def work():
            try:
                pairs = engine.steer_seed_pairs(all_tracks=kind == "all")
                tone = engine.ai_assess_tone(pairs) if pairs else ""
                problem = "" if pairs else "Nothing is playing to assess."
            except Exception as e:
                tone, problem = "", f"Assess Tone didn't work ({e})."
            self._later.put(lambda: self._show_tone(tone, problem))
        threading.Thread(target=work, daemon=True).start()

    def _show_tone(self, tone, problem):
        self._assessing = False
        if not self.winfo_exists() or self.mode != "steer":
            return
        self.assess_btn.config(text="Assess Tone")
        if tone:
            self.tone.delete("1.0", "end")
            self.tone.insert("1.0", tone)
            write_env({"AI_STEER_TONE": tone})
        elif problem and self.play is not None:
            self.play.report(f"Note: {problem}")

    def tone_text(self):
        return " ".join(self.tone.get("1.0", "end").split())

    def steer_spec(self):
        """What Steer was asked for, as the engine wants it."""
        return dict(seed_kind=self.seed_kind, tone=self.tone_text(), directions=list(self.directions),
                    own_words=self.own.get().strip(), strength=self.strength, count=self.count_value(),
                    if_short=self.if_short)

    # --- Create ---

    def _build_create(self):
        p, page = self.p, self.page
        env = read_env()
        self._label(page, "Theme").pack(anchor="w")
        self.theme = self._entry(page)
        self.theme.pack(fill="x", ipady=self._px(4), pady=(self._px(4), 0))
        self.theme.insert(0, env.get("AI_CREATE_THEME", "").strip())
        self.theme.bind("<Return>", lambda e: self.submit())
        self.placeholder = tk.Label(page, text="A mood, a place, a decade, a feeling...", font=self._font(10),
                                    bg=p["field_bg"], fg=p["text_faint"])
        self._sync_placeholder()
        self.theme.bind("<KeyRelease>", lambda e: self._sync_placeholder(), add="+")
        self.theme.bind("<FocusIn>", lambda e: self._sync_placeholder(), add="+")
        self.theme.bind("<FocusOut>", lambda e: self._sync_placeholder(), add="+")

        self._label(page, "Ideas").pack(anchor="w", pady=(self._px(GAP), self._px(6)))
        self.ideas = tk.Frame(page, bg=p["window_bg"])
        self.ideas.pack(fill="x")
        self.ideas_note = tk.Label(self.ideas, text="Thinking...", font=self._font(9), bg=p["window_bg"],
                                   fg=p["text_faint"])
        self.ideas_note.pack(anchor="w")
        self.ideas_list, self.idea_chips = [], []

        self._options_row(page, "VIBE_TRACK_COUNT", getattr(engine, "VIBE_TRACK_COUNT", 20))

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
        if not ideas and not self.ideas_list:
            self.ideas_note.config(text="(no suggestions right now)")
            self.ideas_note.pack(anchor="w")
        for idea in ideas:
            self._add_idea(idea, idea)

    def _add_idea(self, shown, text, first=False):
        """A chip in the Ideas rows, which wrap at the window's width."""
        if not self.winfo_exists():
            return
        self.ideas_note.pack_forget()
        self.ideas_list.insert(0 if first else len(self.ideas_list), (shown, text))
        self._flow_ideas()

    def _flow_ideas(self):
        self.idea_chips = self._flow(self.ideas, [
            (lambda row, sh=sh, t=t: self._chip(row, sh, lambda: self._use(t))) for sh, t in self.ideas_list])
        self._fit()

    def _use(self, text):
        self.theme.delete(0, "end")
        self.theme.insert(0, text)
        self._sync_placeholder()
        self.theme.focus_set()

    def count_value(self):
        try:
            return min(COUNT_MAX, max(COUNT_MIN, int(self.count.get().strip())))
        except ValueError:
            return 12 if self.mode == "steer" else getattr(engine, "VIBE_TRACK_COUNT", 20)

    def submit(self):
        if self.mode == "steer":
            spec = self.steer_spec()
            write_env({"AI_STEER_TONE": spec["tone"], "AI_STEER_OWN": spec["own_words"],
                       "AI_STEER_COUNT": str(spec["count"])})
            self.destroy()
            if self.on_steer is not None:
                self.on_steer(spec)
            return
        theme = self.theme.get().strip()
        if not theme:
            self.theme.focus_set()
            return
        count = self.count_value()
        write_env({"AI_CREATE_THEME": theme, "VIBE_TRACK_COUNT": str(count)})
        self.destroy()
        self.on_create(theme, count, self.if_short)

    # --- window mechanics ---

    def _drain_later(self):
        """Runs what the background threads handed over, on Tk's thread."""
        while True:
            try:
                work = self._later.get_nowait()
            except queue.Empty:
                break
            try:
                work()
            except Exception as e:   # a widget that has gone, usually after a mode switch: carry on
                try:
                    if not self.winfo_exists():
                        return
                except tk.TclError:
                    return
                engine.debug(f"AI Playlist window: {e}")
        try:
            if self.winfo_exists():
                self.after(100, self._drain_later)
        except tk.TclError:
            pass

    def _show_over(self, master):
        """Sized to its content, centred over 24bit7, then shown."""
        try:
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            x = master.winfo_rootx() + (master.winfo_width() - w) // 2
            y = master.winfo_rooty() + max(0, (master.winfo_height() - h) // 2)
            self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
            try:
                self.wm_attributes("-alpha", 0.0)   # shown invisible first, so the dressing happens unseen
            except tk.TclError:
                pass
            self.deiconify()
            self.update_idletasks()
            self._strip_title_bar()
            self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")   # again: Windows moves it when the bar goes
            self.update_idletasks()
            try:
                self.wm_attributes("-alpha", 1.0)
            except tk.TclError:
                pass
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
