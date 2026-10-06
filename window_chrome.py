"""
24bit7 - the built-in title bar (Windows).

Hides Windows' own title bar, so the Play / Discover / Settings strip runs to the top
of the window, with minimise, maximise and close at its right-hand end. The window
stays a normal window underneath: taskbar button, Alt+Tab, resizing from the edges,
snapping and Win+arrow keys all still work. Dragging an empty part of the strip moves
the window (Windows is told the strip is the title bar, so snapping works too), and
double-clicking it maximises or restores.

Settings > Other > "Use the Windows title bar" turns this off, after a restart.
"""

import tkinter as tk

import tabs
from tabs import PALETTE

BUTTON_W = 46   # each button's width at 100% scaling, as Windows draws them
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
SWP_FRAME = 0x0027   # SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER
WM_NCLBUTTONDOWN, HTCAPTION = 0x00A1, 2
SM_CXFRAME, SM_CYFRAME, SM_CXPADDEDBORDER = 32, 33, 92


class Chrome:
    """The built-in title bar. width: room the buttons take at the right of the strip."""

    def __init__(self, root, nb):
        import ctypes
        self.root, self.nb = root, nb
        self.user32 = ctypes.windll.user32
        root.update_idletasks()
        self.hwnd = self.user32.GetParent(root.winfo_id())
        from ctypes import wintypes
        self._post = ctypes.WinDLL("user32").PostMessageW   # its own copy, so the types set here stay here
        self._post.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        self._post.restype = wintypes.BOOL
        style = self.user32.GetWindowLongW(self.hwnd, GWL_STYLE)
        self.user32.SetWindowLongW(self.hwnd, GWL_STYLE, style & ~WS_CAPTION)
        self.user32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, SWP_FRAME)
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.bw = int(round(BUTTON_W * self.scale))
        self.width = self.bw * 3
        self.bg, self.fg = PALETTE["strip_bg"], PALETTE["strip_fg"]
        self.hover = "#2a2c30" if tabs.THEME == "dark" else "#2b5fa6"
        self.frame = tk.Frame(root, bg=self.bg)
        self.canvases = {}
        for name in ("min", "max", "close"):
            c = tk.Canvas(self.frame, width=self.bw, height=10, bg=self.bg, highlightthickness=0, bd=0)
            c.pack(side="left")
            c.bind("<Enter>", lambda e, n=name: self._draw(n, hot=True))
            c.bind("<Leave>", lambda e, n=name: self._draw(n, hot=False))
            c.bind("<ButtonRelease-1>", lambda e, n=name: self._click(n, e))
            self.canvases[name] = c
        for widget in (nb, nb._strip):   # the strip's empty space is the title bar
            widget.bind("<ButtonPress-1>", self._drag, add="+")
            widget.bind("<Double-Button-1>", self._toggle_max, add="+")
        root.bind("<Configure>", self._on_configure, add="+")
        self._pad = 0
        self._shape = None   # (width, height, state) at the last layout
        root.after(50, self._layout)

    # --- drawing -----------------------------------------------------------------------

    def _band_height(self):
        try:
            strip = self.nb._strip
            return max(20, strip.winfo_y() + strip.winfo_height())
        except tk.TclError:
            return int(round(40 * self.scale))

    def _draw(self, name, hot=False):
        c = self.canvases[name]
        h = int(c.cget("height"))
        bg = ("#c42b1c" if name == "close" else self.hover) if hot else self.bg
        fg = "#ffffff" if hot and name == "close" else self.fg
        c.configure(bg=bg)
        c.delete("all")
        cx, cy, s = self.bw // 2, h // 2, int(round(5 * self.scale))
        w = max(1, int(round(self.scale)))
        if name == "min":
            c.create_line(cx - s, cy, cx + s + 1, cy, fill=fg, width=w)
        elif name == "max":
            if self.root.state() == "zoomed":   # restore: two overlapping squares
                o = int(round(2 * self.scale))
                c.create_rectangle(cx - s + o, cy - s - o + 1, cx + s + o, cy + s - o + 1, outline=fg, width=w)
                c.create_rectangle(cx - s, cy - s + 1, cx + s, cy + s + 1, outline=fg, width=w, fill=bg)
            else:
                c.create_rectangle(cx - s, cy - s, cx + s, cy + s, outline=fg, width=w)
        else:
            c.create_line(cx - s, cy - s, cx + s + 1, cy + s + 1, fill=fg, width=w)
            c.create_line(cx + s, cy - s, cx - s - 1, cy + s + 1, fill=fg, width=w)

    def _layout(self):
        """Sizes the buttons to the strip and pins them to the top right (inside the frame when maximised)."""
        zoomed = self.root.state() == "zoomed"
        # A maximised window without a title bar overhangs the screen by its frame: pad it back in
        pad = (self.user32.GetSystemMetrics(SM_CYFRAME) + self.user32.GetSystemMetrics(SM_CXPADDEDBORDER)
               if zoomed else 0)
        if pad != self._pad:
            self._pad = pad
            self.nb.pack_configure(padx=pad, pady=pad)
            self.root.configure(bg=self.bg)
        h = self._band_height()
        for name, c in self.canvases.items():
            c.configure(height=h)
            self._draw(name)
        self.frame.place(relx=1.0, x=-pad, y=pad, anchor="ne")
        self.frame.lift()

    def _on_configure(self, event):
        """Lays the buttons out again only when the size or maximised state changed (not on a move)."""
        if event.widget is not self.root:
            return
        try:
            shape = (event.width, event.height, self.root.state())
        except tk.TclError:
            return
        if shape != self._shape:
            self._shape = shape
            self._layout()

    # --- actions -----------------------------------------------------------------------

    def _click(self, name, event):
        c = self.canvases[name]
        if not (0 <= event.x < c.winfo_width() and 0 <= event.y < c.winfo_height()):
            return   # let go outside the button: nothing, as on Windows
        if name == "min":
            self.root.iconify()
        elif name == "max":
            self._toggle_max()
        else:
            command = self.root.protocol("WM_DELETE_WINDOW")   # whatever the X does: close, or to the tray
            if command:
                self.root.tk.call(command)
            else:
                self.root.destroy()

    def _toggle_max(self, event=None):
        if event is not None and event.widget not in (self.nb, self.nb._strip):
            return
        self.root.state("normal" if self.root.state() == "zoomed" else "zoomed")
        self.root.after(50, self._layout)

    def _drag(self, event):
        """Hands the press to Windows as a title-bar drag, so moving and snapping work as normal."""
        if event.widget not in (self.nb, self.nb._strip):
            return
        # Posted, not sent: Windows starts its move loop once this handler has returned,
        # as with its own title bar. Sending it ran the loop inside Tk's handler and crashed.
        x, y = event.x_root & 0xFFFF, event.y_root & 0xFFFF
        self.user32.ReleaseCapture()
        self._post(self.hwnd, WM_NCLBUTTONDOWN, HTCAPTION, (y << 16) | x)


def attach(root, nb):
    """Turns on the built-in title bar. Returns the Chrome (its width is the room the buttons take)."""
    return Chrome(root, nb)
