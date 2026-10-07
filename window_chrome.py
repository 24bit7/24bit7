"""
24bit7 - the built-in title bar (Windows).

Hides Windows' own title bar, so the Play / Discover / Settings strip runs to the top
of the window, with minimise, maximise and close at its right-hand end. The window
stays a normal window underneath: taskbar button, Alt+Tab, resizing from the edges,
snapping and Win+arrow keys all still work. Dragging an empty part of the strip moves
the window (Windows is told the strip is the title bar, so snapping works too), and
double-clicking it maximises or restores.

Windows 10 paints the top edge of a caption-less window's frame in its own light colour,
above the strip. So Windows is told the window has no top frame (the strip runs to the
very top), the top few pixels still resize the window, anything not yet drawn shows the
strip's colour, and after a snap or resize the frame is worked out again (the first snap
otherwise left a grey line until a maximise). Tested first in a standalone window, 7 Oct.

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
GWLP_WNDPROC = -4
WM_ERASEBKGND, WM_WINDOWPOSCHANGED, WM_NCCALCSIZE, WM_NCHITTEST, WM_EXITSIZEMOVE = 0x14, 0x47, 0x83, 0x84, 0x232
WM_ACTIVATE, WM_NCACTIVATE = 0x06, 0x86
HTCLIENT, HTTRANSPARENT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 1, -1, 12, 13, 14
SWP_NOSIZE = 0x0001
SWP_FRAME_QUIET = SWP_FRAME | 0x0010   # SWP_NOACTIVATE: re-measure without taking the focus back


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
        self.scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.bg, self.fg = PALETTE["strip_bg"], PALETTE["strip_fg"]   # before the hook: it paints with bg
        self.margin = (self.user32.GetSystemMetrics(SM_CYFRAME)
                       + self.user32.GetSystemMetrics(SM_CXPADDEDBORDER))   # the top edge that still resizes
        self._resized = False
        self._hooked = False
        self.hook_problem = ""
        self.frame_checks = 0   # times Windows asked about the frame and the top was taken off (diagnostic)
        try:
            self._hook_frame()   # before the caption goes, so Windows asks about the frame once, here
        except Exception as e:
            self._hooked = False   # without it: the light top edge stays, nothing else changes
            self.hook_problem = f"{type(e).__name__}: {e}"
        style = self.user32.GetWindowLongW(self.hwnd, GWL_STYLE)
        self.user32.SetWindowLongW(self.hwnd, GWL_STYLE, style & ~WS_CAPTION)
        self.user32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, SWP_FRAME)
        self.bw = int(round(BUTTON_W * self.scale))
        self.width = self.bw * 3
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
        root.configure(bg=self.bg)   # the strip's colour for the top edge
        self._pad = None
        self._shape = None   # (width, height, state) at the last layout
        root.after(50, self._layout)
        if self._hooked:
            root.after(150, self._remeasure)

    # --- the top frame (Windows) -----------------------------------------------------------

    def _hook_frame(self):
        """Watches a few of Windows' messages for the window: see the note at the top of the file."""
        import ctypes
        from ctypes import wintypes
        u = self.user32
        lresult = ctypes.c_ssize_t
        proc_type = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        self._set_proc = ctypes.WinDLL("user32").SetWindowLongPtrW
        self._set_proc.restype = ctypes.c_void_p
        self._set_proc.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
        call = ctypes.WinDLL("user32").CallWindowProcW
        call.restype = lresult
        call.argtypes = (ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        zoomed = ctypes.WinDLL("user32").IsZoomed
        zoomed.argtypes = (wintypes.HWND,)
        window_rect = ctypes.WinDLL("user32").GetWindowRect
        window_rect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        client_rect = ctypes.WinDLL("user32").GetClientRect
        client_rect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
        fill = ctypes.WinDLL("user32").FillRect
        fill.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)
        gdi32 = ctypes.WinDLL("gdi32")
        gdi32.CreateSolidBrush.restype = ctypes.c_void_p
        colour = self.bg.lstrip("#")
        r, g, b = int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16)
        brush = gdi32.CreateSolidBrush((b << 16) | (g << 8) | r)

        class WINDOWPOS(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("after", wintypes.HWND), ("x", ctypes.c_int),
                        ("y", ctypes.c_int), ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", wintypes.UINT)]

        class NCCALCSIZE_PARAMS(ctypes.Structure):
            _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

        outer, inner, margin = self.hwnd, self.root.winfo_id(), self.margin
        old = {}

        def top_edge(lp):
            """HTTOP / HTTOPLEFT / HTTOPRIGHT when the point is in the top few pixels, else None."""
            x, y = ctypes.c_short(lp & 0xFFFF).value, ctypes.c_short((lp >> 16) & 0xFFFF).value
            rect = wintypes.RECT()
            window_rect(outer, ctypes.byref(rect))
            if y >= rect.top + margin:
                return None
            if x < rect.left + margin * 2:
                return HTTOPLEFT
            if x > rect.right - margin * 2:
                return HTTOPRIGHT
            return HTTOP

        def outer_proc(h, msg, wp, lp):
            # Only arithmetic and Windows calls in here: no Tk, as this runs inside Windows' own loops
            try:
                if msg == WM_NCCALCSIZE and wp and not zoomed(h):
                    params = NCCALCSIZE_PARAMS.from_address(lp)
                    top = params.rgrc[0].top
                    result = call(old["outer"], h, msg, wp, lp)
                    params.rgrc[0].top = top   # no top frame: the strip runs to the window's top
                    self.frame_checks += 1
                    return result
                if msg == WM_NCHITTEST and not zoomed(h):
                    result = call(old["outer"], h, msg, wp, lp)
                    if result == HTCLIENT:
                        edge = top_edge(lp)
                        if edge:
                            return edge
                    return result
                if msg == WM_ERASEBKGND:   # anything not yet drawn shows the strip's colour, not grey
                    rect = wintypes.RECT()
                    client_rect(h, ctypes.byref(rect))
                    fill(wp, ctypes.byref(rect), brush)
                    return 1
                if msg == WM_NCACTIVATE and not zoomed(h):
                    # Focus came or went: Windows would repaint the frame (and its old top edge).
                    # -1 for lParam says don't; there is no frame to show
                    return call(old["outer"], h, msg, wp, -1)
                if msg == WM_ACTIVATE and (wp & 0xFFFF):
                    self._resized = True   # focus gained: re-measure shortly, in case anything was redrawn
                    # (never on losing focus: the re-measure must not pull the focus back)
                if msg == WM_EXITSIZEMOVE:
                    self._resized = True
                elif msg == WM_WINDOWPOSCHANGED and not (WINDOWPOS.from_address(lp).flags & SWP_NOSIZE):
                    self._resized = True   # a snap, Win+arrow or edge resize: work the frame out again soon
            except Exception:
                pass
            return call(old["outer"], h, msg, wp, lp)

        def inner_proc(h, msg, wp, lp):
            try:
                if msg == WM_NCHITTEST and not zoomed(outer) and top_edge(lp):
                    return HTTRANSPARENT   # the top edge belongs to the frame behind: it resizes
            except Exception:
                pass
            return call(old["inner"], h, msg, wp, lp)

        self._procs = (proc_type(outer_proc), proc_type(inner_proc))   # kept, or Python frees them
        old["outer"] = self._set_proc(outer, GWLP_WNDPROC, ctypes.cast(self._procs[0], ctypes.c_void_p))
        old["inner"] = self._set_proc(inner, GWLP_WNDPROC, ctypes.cast(self._procs[1], ctypes.c_void_p))
        self._old_procs = old
        self._hooked = bool(old["outer"] and old["inner"])
        self.root.bind("<Destroy>", self._unhook, add="+")

    def report(self):
        """One line for the console on how the top-edge fix is getting on (a diagnostic, 7 Oct)."""
        try:
            now = self.user32.GetParent(self.root.winfo_id())
        except Exception:
            now = None
        if not self._hooked:
            return f"Title bar check: top-edge fix off ({self.hook_problem or 'not hooked'})."
        same = "same" if now == self.hwnd else f"CHANGED to {now}"
        return (f"Title bar check: top-edge fix on, frame checks {self.frame_checks}, margin {self.margin}px, "
                f"window {self.hwnd} ({same}), state {self.root.state()}.")

    def _unhook(self, event):
        """Hands Windows its own handling back as the window closes."""
        if event.widget is not self.root or not self._hooked:
            return
        import ctypes
        self._hooked = False
        try:
            self._set_proc(self.root.winfo_id(), GWLP_WNDPROC, ctypes.c_void_p(self._old_procs["inner"]))
            self._set_proc(self.hwnd, GWLP_WNDPROC, ctypes.c_void_p(self._old_procs["outer"]))
        except Exception:
            pass

    def _remeasure(self):
        """After a snap or resize, Windows works the frame out again (what a maximise did by hand)."""
        if not self._hooked:
            return
        try:
            if self._resized:
                self._resized = False
                self.user32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, SWP_FRAME_QUIET)
            self.root.after(150, self._remeasure)
        except tk.TclError:
            pass

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
        top = pad if zoomed or not self._hooked else self.margin   # the resizing top edge, in the strip's colour
        if (pad, top) != self._pad:
            self._pad = (pad, top)
            self.nb.pack_configure(padx=pad, pady=(top, pad))
            self.root.configure(bg=self.bg)
        h = self._band_height()
        for name, c in self.canvases.items():
            c.configure(height=h)
            self._draw(name)
        self.frame.place(relx=1.0, x=-pad, y=top, anchor="ne")
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
