"""
24bit7 - the voice badge.

datdude on the forum (29 Oct 2026): from the couch in Theater View there was no telling whether
a voice request had been heard, and an AI Playlist can take twenty seconds. While a voice build
runs, a small badge sits in the top right of the main screen, on top of everything, Theater View
included. It never takes focus and clicks go straight through it. It shows what was asked and the
zone, stays up while Drift is still finding tracks, then says how many went in, or what went
wrong, and fades. Voice only, with no setting; its colours follow the accent (Settings > Other).
The working dots stay in the accent while the AI chooses too (datdude, 29 Oct: magenta flashing
over Theater View distracted; magenta marks a button that will spend AI credits, and by now the
request is made, with "asking the AI" on the line below).
"""

import ctypes
import sys
import tkinter as tk
import tkinter.font as tkfont

from i18n import t, tn

import tabs

BG, TEXT, MUTED, DOT_OFF = "#16181c", "#e8eaed", "#9aa0a6", "#3a3d42"   # always dark: it sits over Theater View
WIDTH, HEIGHT, MARGIN = 340, 84, 16   # at 96 dpi; scaled with Windows' display scaling
TICK_MS = 400      # the working dot moves on
HOLD_MS = 6000     # how long the result stays before it fades
FADE_STEPS = 10
ALPHA = 0.92

# Windows: a layered tool window that lets clicks through, is never activated and isn't owned by
# the main window (an owned window would hide along with it when 24bit7 sits in the tray)
GWL_EXSTYLE, GWLP_HWNDPARENT = -20, -8
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x80000, 0x20, 0x80
WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x08000000, 0x8
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
SWP_NOZORDER, SWP_NOACTIVATE = 0x4, 0x10


def _ellipsis(text, font, width):
    """Shortens text with '...' until it fits the width in pixels."""
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + "...") > width:
        text = text[:-1]
    return text.rstrip() + "..."


class Badge:
    """The badge, made on first use. Every call is from Tk's own thread."""

    def __init__(self, root):
        self.root = root
        self.win = None
        self.visible = False    # shown through Windows directly, so Tk's own idea of it isn't used
        self.state = None       # "working", "done" or "problem"
        self.lines = ("", "")
        self._tick = 0
        self._after = None

    # --- what it shows -------------------------------------------------------

    def working(self, asked, zone, ai=False):
        """A voice build has started: what was asked, and the zone it's for."""
        self._show("working", asked, t("{zone}: asking the AI", zone=zone) if ai else
                   t("{zone}: finding tracks", zone=zone), tabs.ACCENT)

    def done(self, count, zone, why=""):
        """The build finished: how many tracks went in, or why none did."""
        if count:
            self._show("done", tn("{count} track added", "{count} tracks added", count), zone, tabs.ACCENT)
        else:
            self._show("problem", t("Nothing added"), why or zone, tabs.DARK["logo_bit"])
        self._schedule(HOLD_MS, self._fade)

    def problem(self, asked, said):
        """A voice request that never became a build: what was asked, and what Alexa said back."""
        self._show("problem", t("Not played: {asked}", asked=asked), said, tabs.DARK["logo_bit"])
        self._schedule(HOLD_MS, self._fade)

    def hide(self):
        self._cancel()
        self.state = None
        if self.win is not None and self.visible:
            if self.hwnd:
                ctypes.windll.user32.ShowWindow(self.hwnd, SW_HIDE)
            else:
                self.win.withdraw()
        self.visible = False

    def showing(self):
        return self.visible

    # --- drawing --------------------------------------------------------------

    def _make(self):
        self.scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        s = self.scale
        self.win = tk.Toplevel(self.root, bg=BG)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.canvas = tk.Canvas(self.win, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.font_logo = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.font_one = tkfont.Font(family="Segoe UI Semibold", size=10)
        self.font_two = tkfont.Font(family="Segoe UI", size=8)
        self.width = int(WIDTH * s)
        self.canvas.config(width=self.width, height=int(HEIGHT * s))
        self.win.update_idletasks()
        self.hwnd = None
        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            self.hwnd = user32.GetParent(self.win.winfo_id())
            setlong = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            setlong(self.hwnd, GWLP_HWNDPARENT, 0)

    def _place(self):
        s = self.scale
        x, y, h = self.root.winfo_screenwidth() - self.width - int(MARGIN * s), int(MARGIN * s), int(HEIGHT * s)
        self.win.geometry(f"{self.width}x{h}+{x}+{y}")
        if self.hwnd:   # shown through Windows, so Tk's geometry isn't applied before the first show (datdude: top left)
            ctypes.windll.user32.SetWindowPos(self.hwnd, 0, x, y, self.width, h, SWP_NOZORDER | SWP_NOACTIVATE)

    def _draw(self):
        c, s = self.canvas, self.scale
        c.delete("all")
        x = 18 * s
        for part, colour in (("24", tabs.ACCENT), ("bit", tabs.DARK["logo_bit"]), ("7", tabs.ACCENT)):
            item = c.create_text(x, 24 * s, text=part, fill=colour, anchor="w", font=self.font_logo)
            x = c.bbox(item)[2]
        lit = {"working": [self._tick % 3], "done": [0, 1, 2], "problem": [0]}.get(self.state, [])
        for i in range(3):
            cx = x + (16 + i * 16) * s
            r = (4 if i in lit else 3) * s
            c.create_oval(cx - r, 24 * s - r, cx + r, 24 * s + r, outline="",
                          fill=self.dot if i in lit else DOT_OFF)
        room = self.width - 36 * s
        c.create_text(18 * s, 52 * s, anchor="w", fill=TEXT, font=self.font_one,
                      text=_ellipsis(self.lines[0], self.font_one, room))
        c.create_text(18 * s, 70 * s, anchor="w", fill=MUTED, font=self.font_two,
                      text=_ellipsis(self.lines[1], self.font_two, room))

    def _show(self, state, one, two, dot):
        if self.win is None:
            self._make()
        self._cancel()
        self.state, self.lines, self.dot, self._tick = state, (one, two), dot, 0
        self._draw()
        self._place()
        self.win.attributes("-alpha", ALPHA)
        if not self.visible:
            self.visible = True
            if self.hwnd:
                user32 = ctypes.windll.user32
                ex = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TRANSPARENT |
                                      WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
                user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)   # deiconify would take focus
                self.win.update_idletasks()
            else:
                self.win.deiconify()
        if state == "working":
            self._schedule(TICK_MS, self._step)

    def _step(self):
        self._tick += 1
        self._draw()
        self.win.attributes("-topmost", True)   # Theater View may put itself on top
        self._schedule(TICK_MS, self._step)

    def _fade(self, step=0):
        if step >= FADE_STEPS:
            return self.hide()
        self.win.attributes("-alpha", ALPHA * (1 - step / FADE_STEPS))
        self._schedule(40, lambda: self._fade(step + 1))

    def _schedule(self, ms, func):
        self._cancel()
        self._after = self.root.after(ms, func)

    def _cancel(self):
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except (tk.TclError, ValueError):
                pass
            self._after = None
