"""
24bit7 - tabs the app draws itself.

Windows draws ttk.Notebook tabs in its own flat style and ignores the colours an
app asks for. TabbedPane is a small stand-in that draws the tabs from plain
frames and labels, so every colour and line is under our control and looks the
same on any PC.

All the colours live in PALETTE below, in one place, so a second palette (a dark
mode, say) can be added later without hunting through the rest of the code.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

PALETTE = {
    "tab_selected_bg": None,        # the selected tab takes the window's own colour (None)...
    "tab_selected_fg": "#1f4e9c",   # ...with logo-blue text
    "tab_bg":          "#c4c4c4",   # unselected tabs: mid grey
    "tab_fg":          "#1f4e9c",   # ...also with logo-blue text
    "line":            "#7d7d7d",   # tab outlines, the line under the tabs, the box round a panel
    "brand_blue":      "#1f4e9c",
    "brand_orange":    "#f28c28",
    "button_bg":       "#ffffff",   # Play buttons: white...
    "button_fg":       "#1f4e9c",   # ...logo-blue text...
    "button_outline":  "#c8c8c8",   # ...thin grey outline...
    "button_accent":   "#f28c28",   # ...orange bar along the bottom
    "button_hover":    "#fdf1e5",   # pale orange under the pointer
    "button_press":    "#f9dcbf",   # deeper orange while pressed
    "button_off_fg":   "#9a9a9a",   # greyed-out text (the bar goes to the outline grey)
    "button_quiet_bg": None,        # the quieter button (Show Credits): window colour (None)
}


# Colours the rest of the app uses. Light keeps Windows' own colours (None).
PALETTE.update({
    "window_bg":      None,
    "text":           None,
    "field_bg":       None,
    "text_secondary": "#555555",   # labels such as Zone and Output, the artist/album line
    "text_muted":     "#666666",   # the subtitle and hints
    "text_faint":     "#999999",   # placeholders such as "Thinking..."
    "link":           "#1f4e9c",   # Buy me a coffee
    "section_fg":     "#1f4e8c",   # Settings section titles
    "section_edge":   "#aab4c3",   # the thin line round each Settings section
    "help_fg":        "#666666",   # Settings help text
    "help_mark_bg":   "#8a97aa",   # the ? marks
    "help_mark_fg":   "#ffffff",
    "tooltip_bg":     "#ffffe0",   # the popup a ? shows
    "tooltip_fg":     "#000000",
    "ai_purple":      "#b000b0",   # magenta: anything that uses AI credits
})
LIGHT = dict(PALETTE)
LIGHT.update({   # the redesign: a blue strip, #BFC3C9 header bars and inactive tabs, blue ticks
    "tab_selected_fg": "#1f4e8c", "tab_bg": "#bfc3c9", "tab_fg": "#1f4e8c", "line": "#c9ccd1",
    "window_bg": "#f3f4f6", "text": "#1a1a1a", "field_bg": "#ffffff",
    "text_secondary": "#4a4d52", "text_muted": "#5f6368", "text_faint": "#8a8f96",
    "section_fg": "#1f4e8c", "section_edge": "#c9ccd1", "help_mark_bg": "#1f4e8c", "help_mark_fg": "#ffffff",
    "strip_bg": "#1f4e8c", "strip_fg": "#ffffff", "head_bg": "#bfc3c9", "head_fg": "#1f4e8c",
    "tick_fill": "#1f4e8c", "tick_mark": "#ffffff", "tick_edge": "#6f737a", "tick_inside": "#ffffff",
    "field_fg": "#1a1a1a", "field_edge": "#9aa0a6", "select_bg": "#cfe0f5",
})
DARK = {
    "tab_selected_bg": None,
    "tab_selected_fg": "#00ff41",
    "tab_bg":          "#000000",   # inactive tabs: absolute black
    "tab_fg":          "#00ff41",
    "line":            "#2a2c30",   # borders take the buttons' grey
    "brand_blue":      "#00ff41",   # logo blue lightened so it reads on charcoal
    "brand_orange":    "#f28c28",
    "button_bg":       "#2a2c30",
    "button_fg":       "#00ff41",
    "button_outline":  "#2a2c30",
    "button_accent":   "#f28c28",
    "button_hover":    "#3a2f24",
    "button_press":    "#4a3a28",
    "button_off_fg":   "#6f737a",
    "button_quiet_bg": None,
    "window_bg":       "#1f2023",
    "text":            "#e3e3e3",
    "field_bg":        "#2a2c30",
    "text_secondary":  "#b8bcc2",
    "text_muted":      "#9aa0a6",
    "text_faint":      "#7d8288",
    "link":            "#00ff41",   # matrix green
    "section_fg":      "#00ff41",
    "section_edge":    "#2a2c30",
    "help_fg":         "#9aa0a6",
    "help_mark_bg":    "#000000",
    "help_mark_fg":    "#00ff41",
    "tooltip_bg":      "#000000",
    "tooltip_fg":      "#00ff41",
    "ai_purple":       "#ff33ff",   # bright magenta, so it reads on charcoal
    # the redesign: a black strip, black header bars, green ticks, dark grey fields
    "strip_bg":        "#000000",
    "strip_fg":        "#00ff41",
    "head_bg":         "#000000",
    "head_fg":         "#00ff41",
    "tick_fill":       "#00ff41",
    "tick_mark":       "#000000",
    "tick_edge":       "#9aa0a6",
    "tick_inside":     "#000000",
    "field_fg":        "#e3e3e3",
    "field_edge":      "#3a3d42",
    "select_bg":       "#3a3d42",
}
THEME = "light"


def _button_enter(event):
    """Old-style buttons light up under the pointer, like the newer ones."""
    w = event.widget
    try:
        if str(w.cget("state")) != "disabled" and getattr(w, "_rest_bg", None) is None:
            w._rest_bg = w.cget("background")
            w.configure(background=PALETTE["button_hover"])
    except (tk.TclError, AttributeError):
        pass


def _button_leave(event):
    w = event.widget
    rest = getattr(w, "_rest_bg", None)
    if rest is None:
        return
    w._rest_bg = None
    try:
        w.configure(background=rest)
    except tk.TclError:
        pass


def flat_classic_widgets(root):
    """
    Old-style Tk text boxes, number boxes, lists and buttons: a thin flat edge instead of
    3D shading, set once here so every one gets it, including any added later. Widgets
    that set their own relief or border keep it.
    """
    edge, faint = PALETTE["field_edge"], PALETTE["text_faint"]
    for cls in ("Entry", "Spinbox", "Listbox"):
        for key, value in (("relief", "flat"), ("highlightThickness", 1),
                           ("highlightBackground", edge), ("highlightColor", faint)):
            root.option_add(f"*{cls}.{key}", value)
    for key in ("buttonUpRelief", "buttonDownRelief"):
        root.option_add(f"*Spinbox.{key}", "flat")
    for key, value in (("relief", "flat"), ("highlightThickness", 1),
                       ("highlightBackground", edge), ("highlightColor", edge),
                       ("activeBackground", PALETTE["button_hover"])):
        root.option_add(f"*Button.{key}", value)
    root.bind_class("Button", "<Enter>", _button_enter, add="+")
    root.bind_class("Button", "<Leave>", _button_leave, add="+")


def apply_theme(root, name):
    """
    Picks the palette for "light" or "dark". Call straight after tk.Tk(), before
    any widgets are made. Sets default colours for every plain Tk widget and styles
    the ttk widgets for the theme; dark also darkens the Windows title bar.
    """
    global THEME
    THEME = "dark" if str(name).strip().lower() == "dark" else "light"
    PALETTE.clear()
    PALETTE.update(DARK if THEME == "dark" else LIGHT)
    bg, fg, field = PALETTE["window_bg"], PALETTE["text"], PALETTE["field_bg"]
    field_fg = PALETTE["field_fg"]
    root.configure(bg=bg)
    for key, value in (
            ("*Background", bg), ("*Foreground", fg),
            ("*activeBackground", field), ("*activeForeground", fg),
            ("*highlightBackground", bg), ("*highlightColor", PALETTE["line"]),
            ("*disabledForeground", PALETTE["text_faint"]),
            ("*selectBackground", PALETTE["select_bg"]), ("*selectForeground", fg),
            ("*insertBackground", fg), ("*troughColor", field),
            ("*Entry.Background", field), ("*Entry.Foreground", field_fg),
            ("*Entry.insertBackground", field_fg),
            ("*Spinbox.Background", field), ("*Spinbox.Foreground", field_fg),
            ("*Spinbox.insertBackground", field_fg),
            ("*Spinbox.buttonBackground", field), ("*Listbox.Background", field),
            ("*Text.Background", field), ("*Button.Background", PALETTE["button_bg"]),
            ("*Button.Foreground", PALETTE["button_fg"]),
            ("*Entry.readonlyBackground", bg), ("*Entry.disabledBackground", bg),
            ("*Spinbox.readonlyBackground", bg), ("*Spinbox.disabledBackground", bg),
            ("*Checkbutton.selectColor", field), ("*Radiobutton.selectColor", field)):
        root.option_add(key, value)
    flat_classic_widgets(root)
    if THEME == "dark":
        dark_title_bar(root)
    themed_ttk(root)


def dark_title_bar(window):
    """Asks Windows 10/11 to draw this window's title bar dark. Does nothing elsewhere."""
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        on = ctypes.c_int(1)
        for attribute in (20, 19):   # 20 on current Windows, 19 on early Windows 10 builds
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(on),
                                                          ctypes.sizeof(on)) == 0:
                break
    except Exception:
        pass

LINE_WIDTH = 1      # thickness of every line, at normal (100%) display scaling
TAB_GAP = 4         # space between tabs
SELECTED_RISE = 0   # how much taller the selected tab stands (0: all tabs the same height)


class TabbedPane(tk.Frame):
    """
    Used like ttk.Notebook for the parts 24bit7 needs:
      pane = TabbedPane(parent, font=..., pad=(x, y))
      page = tk.Frame(pane); pane.add(page, text="Play")
      pane.select()          -> name of the current page (compare with str(page))
      pane.select(page)      -> switch to that page
      pane.bind("<<NotebookTabChanged>>", handler)
    box=True draws the line round the page as well (the Now Playing / Search panel).
    Sizes are multiplied by the display scaling, so lines look the same thickness
    on a high-resolution screen as on a normal one.
    """

    def __init__(self, master, font, pad=(18, 8), box=False, indent=8, strip=False, **kw):
        self._strip_mode = strip   # the main window's top strip: tabs on a black (or blue) band
        if strip:
            kw.setdefault("bg", PALETTE.get("strip_bg") or master.cget("bg"))
        super().__init__(master, **kw)
        try:
            scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            scale = 1.0
        self._px = lambda n: max(1, int(round(n * scale))) if n else 0
        self._font = font
        self._tk_font = tkfont.Font(root=self, font=font)   # for sizing the rounded tabs
        self._pad = (self._px(pad[0]), self._px(pad[1]))
        self._line = self._px(LINE_WIDTH)
        self._tabs, self._pages, self._current = [], [], None

        self._strip = tk.Frame(self, bg=self.cget("bg"))
        self._strip.pack(fill="x", padx=(self._px(indent), 0), pady=(self._px(8), 0) if strip else 0)
        self._underline = tk.Frame(self, height=self._line, bg=PALETTE["line"])   # the line under the tabs
        if not strip:   # on the strip the selected tab simply opens into the page
            self._underline.pack(fill="x")
        self._underline.bind("<Configure>", lambda e: self._place_gap(), add="+")
        # A short piece in the window colour laid over that line under the active
        # tab, so the tab opens into the area below like a folder tab
        self._gap = tk.Frame(self, height=self._line, bg=self.cget("bg"))
        self.bind("<Configure>", lambda e: self._place_gap(), add="+")
        self._box = self._line if box else 0
        self._holder = tk.Frame(self, bg=PALETTE["line"] if box else self.cget("bg"))
        self._holder.pack(fill="both", expand=True)

    # --- the ttk.Notebook-style interface ---------------------------------

    def add(self, page, text=""):
        # The tab is a rounded image (outline on the top and both sides) with its text on top
        edge = tk.Frame(self._strip, bg=self._strip.cget("bg"))
        label = tk.Label(edge, text=text, font=self._font, compound="center", bd=0, highlightthickness=0,
                         padx=0, pady=0, bg=self._strip.cget("bg"), cursor="hand2")
        label.pack()
        edge.pack(side="left", anchor="s", padx=(0, self._px(TAB_GAP)))
        label.bind("<Button-1>", lambda e, p=page: self.select(p))
        edge.bind("<Configure>", lambda e: self._place_gap(), add="+")   # re-placed once Windows sizes it
        self._tabs.append(label)
        self._pages.append(page)
        if self._current is None:
            self.select(page)
        else:
            self._paint()

    def select(self, page=None):
        if page is None:
            return str(self._current) if self._current is not None else ""
        if isinstance(page, int):
            page = self._pages[page]
        if page is self._current:
            return None
        if self._current is not None:
            self._current.pack_forget()
        self._current = page
        page.pack(in_=self._holder, fill="both", expand=True, padx=self._box, pady=(0, self._box))
        page.lift()
        self._paint()
        self.event_generate("<<NotebookTabChanged>>")
        return None

    def remove(self, page):
        """Takes a page and its tab away (Settings drops a device's tab when it goes)."""
        if page not in self._pages:
            return
        i = self._pages.index(page)
        self._tabs.pop(i).master.destroy()
        self._pages.pop(i)
        if page is self._current:
            page.pack_forget()
            self._current = None
            if self._pages:
                self.select(self._pages[0])
        page.destroy()

    def rename(self, page, text):
        """Changes a page's tab text (a device renamed under Voice Commands)."""
        if page in self._pages:
            self._tabs[self._pages.index(page)].config(text=text)
            self._paint()

    # --- helpers ------------------------------------------------------------

    def tabs_width(self):
        """Width taken by the tab buttons, for anything that wants to sit beside them."""
        self.update_idletasks()
        return self._strip.winfo_reqwidth() + self._strip.winfo_x()

    def strip_height(self):
        self.update_idletasks()
        return self._strip.winfo_reqheight()

    def _paint(self):
        selected_bg = PALETTE["tab_selected_bg"] or (PALETTE.get("window_bg") or self.master.cget("bg")
                                                     if self._strip_mode else self.cget("bg"))
        line_h = self._tk_font.metrics("linespace")
        for label, page in zip(self._tabs, self._pages):
            on = page is self._current
            w = self._tk_font.measure(label.cget("text")) + 2 * self._pad[0] + 2 * self._line
            h = line_h + 2 * self._pad[1] + self._line + (self._px(SELECTED_RISE) if on else 0)
            if self._strip_mode:   # no outlines on the strip: off tabs are the strip, the selected one is the page
                fill = selected_bg if on else PALETTE["strip_bg"]
                shape = rounded_shape(self, w, h, self._px(CORNER), fill, fill, self._line, open_bottom=True)
                label.config(image=shape, fg=PALETTE["tab_selected_fg"] if on else PALETTE["strip_fg"])
                continue
            shape = rounded_shape(self, w, h, self._px(CORNER), selected_bg if on else PALETTE["tab_bg"],
                                  PALETTE["line"], self._line, open_bottom=True)
            label.config(image=shape, fg=PALETTE["tab_selected_fg"] if on else PALETTE["tab_fg"])

        self.after_idle(self._place_gap)

    def _place_gap(self):
        """Lays the window-coloured piece over the underline, inside the active tab's outline."""
        if self._strip_mode or self._current is None or self._current not in self._pages:
            self._gap.place_forget()
            return
        try:
            edge = self._tabs[self._pages.index(self._current)].master
            x = self._strip.winfo_x() + edge.winfo_x() + self._line
            width = edge.winfo_width() - 2 * self._line
            if width <= 0:
                return
            self._gap.place(x=x, y=self._underline.winfo_y(), width=width, height=self._line)
            self._gap.lift()
        except tk.TclError:
            pass


BUTTON_BAR = 3      # height of the orange bar under a button
CORNER = 6          # rounded corners on buttons and tabs (pixels at 100% scaling)

_SHAPES = {}        # drawn shapes, kept so Tk doesn't lose them


def _rgba(widget, colour):
    r, g, b = widget.winfo_rgb(colour)   # handles Windows' own names, such as SystemButtonFace
    return (r >> 8, g >> 8, b >> 8, 255)


def rounded_shape(widget, w, h, radius, fill, edge, line, bar=None, bar_h=0, open_bottom=False):
    """
    A rounded rectangle as a Tk image: an outline of width line in edge, filled with
    fill, optionally a bar along the bottom inside the curve. open_bottom leaves the
    bottom square with no outline (a tab sitting on the line under it). Drawn at four
    times the size and scaled down, so the corners are smooth.
    """
    key = (w, h, radius, fill, edge, line, bar, bar_h, open_bottom)
    if key in _SHAPES:
        return _SHAPES[key]
    from PIL import Image, ImageDraw, ImageTk
    s = 4
    big_w, big_h = w * s, h * s
    tail = radius * s * 2 if open_bottom else 0   # drawn past the bottom, then cut off

    def mask(inset):
        m = Image.new("L", (big_w, big_h + tail), 0)
        bottom = big_h + tail - 1 - (0 if open_bottom else inset)
        ImageDraw.Draw(m).rounded_rectangle((inset, inset, big_w - 1 - inset, bottom),
                                            radius=max(0, radius * s - inset), fill=255)
        return m.crop((0, 0, big_w, big_h))

    def layer(colour, m):
        part = Image.new("RGBA", (big_w, big_h), _rgba(widget, colour))
        part.putalpha(m)
        return part

    image = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
    image = Image.alpha_composite(image, layer(edge, mask(0)))
    inner = mask(line * s)
    image = Image.alpha_composite(image, layer(fill, inner))
    if bar and bar_h:
        strip = Image.new("L", (big_w, big_h), 0)
        ImageDraw.Draw(strip).rectangle((0, big_h - (line + bar_h) * s, big_w, big_h), fill=255)
        from PIL import ImageChops
        image = Image.alpha_composite(image, layer(bar, ImageChops.multiply(strip, inner)))
    photo = ImageTk.PhotoImage(image.resize((w, h), Image.LANCZOS), master=widget)
    _SHAPES[key] = photo
    return photo


class FlatButton(tk.Frame):
    """
    A button drawn as a rounded image with its text on top, so its colours and shape
    look the same on any PC (Windows draws tk.Button its own way). Used like
    tk.Button for what 24bit7 needs:
      b = FlatButton(parent, text="...", command=handler, width=16, height=2)
      b.config(state="disabled") / b.config(state="normal")
    quiet=True gives the plainer version: window colour, grey outline, no orange bar.
    width and height are in characters and lines, as on tk.Button.
    """

    def __init__(self, master, text="", command=None, width=None, height=None, quiet=False,
                 accent=None, text_fg=None, **kw):
        back = master.cget("bg")
        super().__init__(master, bg=back, **kw)
        try:
            scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            scale = 1.0
        self._px = lambda n: max(1, int(round(n * scale)))
        self._command = command
        self._quiet = quiet
        self._accent = accent   # a bar colour other than orange (magenta: uses AI credits)
        self._text_fg = text_fg  # a text colour other than the usual, while the button can be pressed
        self._state = "normal"
        self._inside = False
        self._pressed = False
        self._chars, self._lines = width, height
        self._bg = (PALETTE["button_quiet_bg"] or back) if quiet else PALETTE["button_bg"]
        self._font = tkfont.nametofont("TkDefaultFont").copy()   # bold, at the usual size
        self._font.configure(weight="bold")
        self._label = tk.Label(self, text=text, compound="center", font=self._font, bg=back,
                               fg=PALETTE["button_fg"], bd=0, highlightthickness=0, padx=0, pady=0,
                               cursor="hand2")
        self._label.pack()
        self._size = self._measure(text)
        self._draw()
        for widget in (self, self._label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)

    def _measure(self, text):
        """The button's size in pixels, from its width and height in characters and lines."""
        px, line = self._px, self._px(1)
        if self._chars:
            text_w = self._chars * self._font.measure("0")
        else:
            text_w = max(self._font.measure(t) for t in (text or " ").split("\n")) + 2 * px(8)
        lines = self._lines or max(1, (text or "").count("\n") + 1)
        text_h = lines * self._font.metrics("linespace")
        return text_w + px(6) + 2 * line, text_h + px(4) + 2 * line + px(BUTTON_BAR)

    def _draw(self):
        on = self._state == "normal"
        if on and self._pressed:
            fill = PALETTE["button_press"]
        elif on and self._inside:
            fill = PALETTE["button_hover"]
        else:
            fill = self._bg
        bar = None if self._quiet else ((self._accent or PALETTE["button_accent"]) if on
                                        else PALETTE["button_outline"])
        w, h = self._size
        image = rounded_shape(self, w, h, self._px(CORNER), fill, PALETTE["button_outline"],
                              self._px(1), bar, self._px(BUTTON_BAR))
        self._label.config(image=image, fg=(self._text_fg or PALETTE["button_fg"]) if on else PALETTE["button_off_fg"],
                           cursor="hand2" if on else "")

    def config(self, cnf=None, **kw):
        redraw = False
        if "state" in kw:
            self._state = "disabled" if str(kw.pop("state")) == "disabled" else "normal"
            redraw = True
        if "text" in kw:
            text = kw.pop("text")
            self._label.config(text=text)
            if not self._chars:
                self._size = self._measure(text)
            redraw = True
        if "command" in kw:
            self._command = kw.pop("command")
        if redraw:
            self._draw()
        if kw or cnf:
            return super().config(cnf, **kw)
        return None

    configure = config

    def cget(self, key):
        if key == "state":
            return self._state
        if key == "text":
            return self._label.cget("text")
        return super().cget(key)

    def _over(self):
        x, y = self.winfo_pointerxy()
        return self.winfo_containing(x, y) in (self, self._label)

    def _on_enter(self, _e):
        self._inside = True
        self._draw()

    def _on_leave(self, _e):
        if self._over():   # moving between the frame and the label still counts as inside
            return
        self._inside = self._pressed = False
        self._draw()

    def _on_press(self, _e):
        if self._state == "normal":
            self._pressed = True
            self._draw()

    def _on_release(self, _e):
        if self._state != "normal":
            return
        over = self._over()
        self._inside, self._pressed = over, False
        self._draw()
        if over and self._command:
            self._command()


class InfoLine(tk.Text):
    """
    A line of text that can mix two styles, such as a grey "Artist:" before a name,
    and wraps like a label: it grows to as many lines as the text needs.
      line = InfoLine(parent, font=..., fg=..., prefix_font=...)
      line.show(("Artist: ", "prefix"), ("Chris Cornell", None))
    """

    PREFIX_FG = PALETTE["brand_orange"]

    def __init__(self, master, font, fg, prefix_font, tab=None):
        super().__init__(master, height=1, wrap="word", bd=0, highlightthickness=0, padx=0, pady=0,
                         bg=master.cget("bg"), fg=fg, font=font, cursor="arrow", takefocus=0)
        self.tag_configure("prefix", font=prefix_font, foreground=self.PREFIX_FG)
        self._tab = tab
        if tab:   # names after a tab start here, and wrapped lines continue from here
            self.config(tabs=(tab,))
            self.tag_configure("hang", lmargin2=tab)
        self.config(state="disabled")
        self.bind("<Configure>", lambda e: self.after_idle(self._fit), add="+")

    def show(self, *parts):
        """parts: (text, "prefix" or None) pairs, drawn one after another."""
        self.config(state="normal")
        self.delete("1.0", "end")
        hang = ("hang",) if self._tab and any("\t" in text for text, _ in parts) else ()
        for text, tag in parts:
            self.insert("end", text, ((tag,) if tag else ()) + hang)
        self.config(state="disabled")
        self.after_idle(self._fit)

    def _fit(self):
        """Sets the height to the number of lines the text wraps to."""
        try:
            n = self.count("1.0", "end-1c", "displaylines")
        except tk.TclError:
            return
        if isinstance(n, (tuple, list)):
            n = n[0] if n else 0
        lines = (n or 0) + 1
        if int(self.cget("height")) != lines:
            self.config(height=lines)


MATRIX_BG = "#000000"
MATRIX_FG = "#00ff41"      # the log's green
MATRIX_HI = "#0d4d1c"      # a highlighted row in an open dropdown


def themed_ttk(root):
    """
    ttk widgets (dropdowns, tick boxes, the Discover table, scrollbars) in the theme's
    colours. Windows' own style ignores colours, so this switches ttk to Tk's "clam"
    style, which takes them. Tick boxes are drawn as images: filled with the theme's
    colour and a tick when ticked.
    """
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        return
    bg, text, edge = PALETTE["window_bg"], PALETTE["text"], PALETTE["line"]
    faint, panel = PALETTE["text_faint"], PALETTE["button_bg"]
    field, field_fg, field_edge = PALETTE["field_bg"], PALETTE["field_fg"], PALETTE["field_edge"]
    accent, hi = PALETTE["tab_fg"], PALETTE["select_bg"]
    style.configure(".", background=bg, foreground=text, bordercolor=edge, lightcolor=bg, darkcolor=bg,
                    troughcolor=bg, fieldbackground=field, selectbackground=hi,
                    selectforeground=text, insertcolor=field_fg, focuscolor=bg)
    style.map(".", foreground=[("disabled", faint)])
    # dropdowns
    style.configure("TCombobox", fieldbackground=field, background=field, foreground=field_fg,
                    arrowcolor=accent, bordercolor=field_edge, lightcolor=field, darkcolor=field,
                    selectbackground=field, selectforeground=field_fg)
    style.map("TCombobox",
              fieldbackground=[("readonly", field), ("disabled", bg)],
              foreground=[("disabled", faint), ("readonly", field_fg)],
              selectbackground=[("readonly", field)],
              selectforeground=[("readonly", field_fg)],
              background=[("pressed", hi), ("active", hi)],
              arrowcolor=[("disabled", faint)])
    try:
        scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        scale = 1.0
    size = int(round(15 * scale))
    for kind in ("TCheckbutton", "TRadiobutton"):
        style.configure(kind, background=bg, foreground=text, indicatorbackground=PALETTE["tick_inside"],
                        indicatorforeground=PALETTE["tick_fill"], upperbordercolor=PALETTE["tick_edge"],
                        lowerbordercolor=PALETTE["tick_edge"], indicatorsize=size,
                        indicatormargin=(0, 0, int(round(6 * scale)), 0))
        style.map(kind, background=[("active", bg)], foreground=[("disabled", faint)],
                  indicatorbackground=[("selected", PALETTE["tick_fill"]), ("disabled", bg)],
                  indicatorforeground=[("disabled", faint)],
                  upperbordercolor=[("disabled", faint)], lowerbordercolor=[("disabled", faint)])
    try:   # a filled box with a real tick, instead of clam's cross
        off, on, off_dim, on_dim = _tick_images(root, size, scale, PALETTE["tick_edge"], faint)
        gap = int(round(6 * scale))
        style.element_create("Themed.Checkbutton.indicator", "image", off,
                             ("disabled selected", on_dim), ("disabled", off_dim), ("selected", on),
                             width=off.width() + gap, sticky="w")
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Themed.Checkbutton.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"})]})]})])
    except tk.TclError:
        pass   # keep clam's own box
    # the Discover table: rows like the page, the heading like a Settings header bar
    style.configure("Treeview", background=bg, fieldbackground=bg, foreground=text,
                    bordercolor=edge, lightcolor=bg, darkcolor=bg)
    style.map("Treeview", background=[("selected", hi)], foreground=[("selected", text)])
    style.configure("Treeview.Heading", background=PALETTE["head_bg"], foreground=PALETTE["head_fg"],
                    bordercolor=edge, lightcolor=PALETTE["head_bg"], darkcolor=PALETTE["head_bg"], relief="flat")
    style.map("Treeview.Heading", background=[("active", PALETTE["head_bg"])],
              foreground=[("active", PALETTE["head_fg"])])
    # scrollbars, entry boxes, spin boxes, buttons
    style.configure("TScrollbar", background=panel, troughcolor=bg, arrowcolor=accent,
                    bordercolor=edge, lightcolor=panel, darkcolor=panel)
    style.map("TScrollbar", background=[("active", PALETTE["tab_bg"])])
    style.configure("TEntry", fieldbackground=field, foreground=field_fg, bordercolor=field_edge)
    # text boxes that match the dropdowns: thin flat border, no 3D shading,
    # the border brightens a touch while you type in it
    style.configure("Field.TEntry", fieldbackground=field, foreground=field_fg,
                    bordercolor=field_edge, lightcolor=field, darkcolor=field,
                    insertcolor=field_fg, selectbackground=hi, selectforeground=field_fg,
                    padding=(4, 2))
    style.map("Field.TEntry",
              bordercolor=[("focus", faint)],
              lightcolor=[("focus", field)], darkcolor=[("focus", field)],
              fieldbackground=[("disabled", bg)], foreground=[("disabled", faint)])
    style.configure("TSpinbox", fieldbackground=field, foreground=field_fg, arrowcolor=accent,
                    background=panel, bordercolor=field_edge)
    style.configure("TButton", background=panel, foreground=PALETTE["button_fg"])
    style.map("TButton", background=[("active", PALETTE["button_hover"])])
    # the list that drops down from a dropdown
    for key, value in (("*TCombobox*Listbox.background", field),
                       ("*TCombobox*Listbox.foreground", field_fg),
                       ("*TCombobox*Listbox.selectBackground", hi),
                       ("*TCombobox*Listbox.selectForeground", accent)):
        root.option_add(key, value)


def matrix_dropdowns(root):
    """Kept for anything that still calls it: the theme's ttk styling."""
    themed_ttk(root)


def _tick_images(root, size, scale, edge, dim):
    """
    Four tick box images (unticked, ticked, and both greyed out), drawn smooth with
    Pillow: unticked is a rounded square outline; ticked is filled with the theme's
    colour (green in dark, blue in light) with a bold tick in black or white.
    Kept on root so Tk doesn't lose them.
    """
    from PIL import Image, ImageDraw, ImageTk
    s = 4
    big = size * s
    radius = max(1, int(round(2.5 * scale))) * s
    line = max(1, int(round(scale))) * s
    stroke = max(2, int(round(2.2 * scale))) * s

    def rgb(colour):
        r, g, b = root.winfo_rgb(colour)
        return (r >> 8, g >> 8, b >> 8, 255)

    def box(outline, inside, tick):
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, big - 1, big - 1), radius=radius, fill=rgb(outline))
        d.rounded_rectangle((line, line, big - 1 - line, big - 1 - line), radius=max(0, radius - line),
                            fill=rgb(inside))
        if tick:
            points = [(0.24 * big, 0.52 * big), (0.43 * big, 0.71 * big), (0.78 * big, 0.30 * big)]
            d.line(points, fill=rgb(tick), width=stroke, joint="curve")
        return ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS), master=root)

    fill, mark, inside = PALETTE["tick_fill"], PALETTE["tick_mark"], PALETTE["tick_inside"]
    images = (box(edge, inside, None), box(fill, fill, mark), box(dim, inside, None), box(dim, dim, inside))
    root._tick_images = images
    return images


def mix_colour(widget, colour, base, amount):
    """colour blended into base: amount 0 gives base, 1 gives colour. As a #rrggbb string."""
    a, b = _rgba(widget, colour), _rgba(widget, base)
    return "#%02x%02x%02x" % tuple(round(b[i] + (a[i] - b[i]) * amount) for i in range(3))


class ClickThrough(FlatButton):
    """
    A button that shows its setting as "Label: Value" and steps to the next value on a
    click, back round to the first after the last. A right-click steps back. It sizes to
    its text, so the row grows and shrinks as values change. Off (or the first value of a
    two-way choice, such as Play Mode) is drawn plain; any other value is lit in its colour.
      ClickThrough(parent, "Drift", var, ["Off", "Keep It Tight", "Spread"], command=handler)
    var holds the value as shown ("Keep It Tight"); setting it from code redraws the button.
    For older code it also answers like the dropdown it replaced: set(), state(), instate(),
    selection_clear(), and <<ComboboxSelected>> runs the command.
    """

    def __init__(self, master, prefix, variable, values, command=None, lit=None, plain=("Off",),
                 labels=None, **kw):
        self._var, self._values, self._prefix = variable, list(values), prefix
        self._user_command = command
        self._lit = lit or {}             # value -> colour; values not listed use the button text colour
        self._plain = set(plain)          # values drawn plain
        self._labels = labels or {}       # value -> what the button says instead of "Prefix: Value"
        super().__init__(master, text=self._text(), command=lambda: self._step(1), quiet=True, height=1, **kw)
        for widget in (self, self._label):
            widget.bind("<Button-3>", lambda e: self._step(-1) if self._state == "normal" else None)
        self.bind("<<ComboboxSelected>>", lambda e: self._changed())
        variable.trace_add("write", lambda *a: self._refresh())

    def _text(self):
        value = self._var.get()
        if value in self._labels:
            return self._labels[value]
        return f"{self._prefix}: {value}" if self._prefix else value

    def _step(self, by):
        value = self._var.get()
        i = self._values.index(value) if value in self._values else 0
        self._var.set(self._values[(i + by) % len(self._values)])
        self._changed()

    def _changed(self):
        if self._user_command:
            self._user_command()

    def _refresh(self):
        try:
            self.config(text=self._text())
        except tk.TclError:
            pass   # closing

    def _draw(self):
        on = self._state == "normal"
        value = self._var.get()
        back = self.master.cget("bg")
        base = PALETTE["button_quiet_bg"] or back
        if on and value not in self._plain:
            colour = self._lit.get(value) or PALETTE["button_fg"]
            fill, edge, text = mix_colour(self, colour, base, 0.16), colour, colour
        else:
            fill, edge = base, PALETTE["button_outline"]
            text = PALETTE["button_fg"] if on else PALETTE["button_off_fg"]
            if on and value in self._plain and self._prefix:
                text = PALETTE["text_muted"]   # Off reads quieter than a lit value
        if on and (self._inside or self._pressed):
            fill = mix_colour(self, edge if edge != PALETTE["button_outline"] else PALETTE["button_fg"],
                              base, 0.28 if self._pressed else 0.10)
        w, h = self._size
        image = rounded_shape(self, w, h, self._px(CORNER), fill, edge, self._px(1))
        # a button with a note takes the question-mark pointer, as every title with a note does
        pointer = "question_arrow" if hasattr(self._label, "_tooltip") else "hand2"
        self._label.config(image=image, fg=text, cursor=pointer if on else "")

    # --- answering like the dropdown this replaced ---
    def set(self, value):
        self._var.set(value)

    def get(self):
        return self._var.get()

    def state(self, flags=None):
        if flags:
            for flag in flags:
                if flag == "disabled":
                    self.config(state="disabled")
                elif flag == "!disabled":
                    self.config(state="normal")
        return ("disabled",) if self._state == "disabled" else ()

    def instate(self, flags):
        disabled = self._state == "disabled"
        return all((not disabled) if f == "!disabled" else disabled if f == "disabled" else False for f in flags)

    def selection_clear(self):
        pass

    def event_generate(self, sequence, **kw):
        if sequence == "<<ComboboxSelected>>":   # as a dropdown would: run the command
            self._changed()
            return None
        return super().event_generate(sequence, **kw)


class RoundedEntry(tk.Frame):
    """
    A text box with fully rounded ends, drawn like the buttons so it looks the same on any PC.
    Answers like a ttk.Entry for what 24bit7 uses: get, delete, insert, bind, focus_set, and
    textvariable. width is in characters, as on ttk.Entry. placeholder is a faint hint shown
    while the box is empty; it's drawn over the box, so it's never part of the text.
    """

    def __init__(self, master, width=30, font=("Segoe UI", 11), placeholder="", textvariable=None, **kw):
        back = master.cget("bg")
        super().__init__(master, bg=back, **kw)
        try:
            scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            scale = 1.0
        px = lambda n: max(1, int(round(n * scale)))
        f = tkfont.Font(font=font)
        line = f.metrics("linespace")
        h = max(px(24), line + px(10))
        w = f.measure("0") * width + h
        fill = PALETTE.get("field_bg") or "#ffffff"
        fg = PALETTE.get("field_fg") or PALETTE.get("text") or "#000000"
        edge = PALETTE.get("field_edge") or PALETTE["button_outline"]
        self._edges = (edge, PALETTE["button_fg"])
        self._shape = lambda colour: rounded_shape(self, w, h, h // 2, fill, colour, px(1))
        self._back = tk.Label(self, image=self._shape(edge), bd=0, highlightthickness=0, bg=back)
        self._back.pack()
        options = {"textvariable": textvariable} if textvariable is not None else {}
        self.entry = tk.Entry(self, font=font, bd=0, relief="flat", highlightthickness=0, bg=fill, fg=fg,
                              insertbackground=fg, disabledbackground=fill, **options)
        place = dict(x=h // 2, y=(h - line) // 2 - px(1), width=w - h, height=line + px(2))
        self.entry.place(**place)
        self._hint, self._var = None, textvariable
        if placeholder:
            self._hint = tk.Label(self, text=placeholder, font=font, bd=0, padx=0, pady=0, anchor="w", bg=fill,
                                  fg=PALETTE.get("text_faint") or "#999999", cursor="xterm")
            self._hint.bind("<Button-1>", lambda e: self.entry.focus_set())
            self._hint_at = place
            if textvariable is not None:
                textvariable.trace_add("write", lambda *a: self._sync_hint())
            self.entry.bind("<KeyRelease>", lambda e: self._sync_hint(), add="+")
        self._back.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        self._sync_hint()

    def _focus(self, on):
        self._back.config(image=self._shape(self._edges[1 if on else 0]))
        self._sync_hint()

    def _sync_hint(self):
        if self._hint is None:
            return
        text = self._var.get() if self._var is not None else self.entry.get()   # the variable is ahead of the box
        try:
            empty = not text and self.focus_get() is not self.entry
        except (tk.TclError, KeyError):
            empty = not text
        if empty:
            self._hint.place(**self._hint_at)
        else:
            self._hint.place_forget()

    def get(self):
        return self.entry.get()

    def delete(self, first, last=None):
        self.entry.delete(first, last)
        self._sync_hint()

    def insert(self, index, text):
        self.entry.insert(index, text)
        self._sync_hint()

    def bind(self, sequence=None, func=None, add=None):
        return self.entry.bind(sequence, func, add)

    def focus_set(self):
        self.entry.focus_set()
