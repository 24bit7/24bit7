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
})
LIGHT = dict(PALETTE)
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
}
THEME = "light"


def apply_theme(root, name):
    """
    Picks the palette for "light" or "dark". Call straight after tk.Tk(), before
    any widgets are made. Dark also sets default colours for every plain Tk widget
    and darkens the Windows title bar.
    """
    global THEME
    THEME = "dark" if str(name).strip().lower() == "dark" else "light"
    PALETTE.clear()
    PALETTE.update(DARK if THEME == "dark" else LIGHT)
    if THEME != "dark":
        return
    bg, fg, field = PALETTE["window_bg"], PALETTE["text"], PALETTE["field_bg"]
    root.configure(bg=bg)
    for key, value in (
            ("*Background", bg), ("*Foreground", fg),
            ("*activeBackground", field), ("*activeForeground", fg),
            ("*highlightBackground", bg), ("*highlightColor", PALETTE["line"]),
            ("*disabledForeground", PALETTE["text_faint"]),
            ("*selectBackground", "#3d5a8a"), ("*selectForeground", fg),
            ("*insertBackground", fg), ("*troughColor", field),
            ("*Entry.Background", MATRIX_BG), ("*Entry.Foreground", MATRIX_FG),
            ("*Entry.insertBackground", MATRIX_FG),
            ("*Spinbox.Background", MATRIX_BG), ("*Spinbox.Foreground", MATRIX_FG),
            ("*Spinbox.insertBackground", MATRIX_FG),
            ("*Spinbox.buttonBackground", field), ("*Listbox.Background", field),
            ("*Text.Background", field), ("*Button.Background", field),
            ("*Entry.readonlyBackground", bg), ("*Entry.disabledBackground", bg),
            ("*Spinbox.readonlyBackground", bg), ("*Spinbox.disabledBackground", bg),
            ("*Checkbutton.selectColor", field), ("*Radiobutton.selectColor", field)):
        root.option_add(key, value)
    dark_title_bar(root)
    matrix_dropdowns(root)


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

    def __init__(self, master, font, pad=(18, 8), box=False, indent=8, **kw):
        super().__init__(master, **kw)
        try:
            scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            scale = 1.0
        self._px = lambda n: max(1, int(round(n * scale))) if n else 0
        self._font = font
        self._pad = (self._px(pad[0]), self._px(pad[1]))
        self._line = self._px(LINE_WIDTH)
        self._tabs, self._pages, self._current = [], [], None

        self._strip = tk.Frame(self)
        self._strip.pack(fill="x", padx=(self._px(indent), 0))
        self._underline = tk.Frame(self, height=self._line, bg=PALETTE["line"])   # the line under the tabs
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
        edge = tk.Frame(self._strip, bg=PALETTE["line"])        # shows as the tab's outline
        label = tk.Label(edge, text=text, font=self._font, padx=self._pad[0], pady=self._pad[1],
                         cursor="hand2")
        label.pack(padx=self._line, pady=(self._line, 0))       # outline on the top and both sides
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

    # --- helpers ------------------------------------------------------------

    def tabs_width(self):
        """Width taken by the tab buttons, for anything that wants to sit beside them."""
        self.update_idletasks()
        return self._strip.winfo_reqwidth() + self._strip.winfo_x()

    def strip_height(self):
        self.update_idletasks()
        return self._strip.winfo_reqheight()

    def _paint(self):
        selected_bg = PALETTE["tab_selected_bg"] or self.cget("bg")
        for label, page in zip(self._tabs, self._pages):
            on = page is self._current
            label.config(bg=selected_bg if on else PALETTE["tab_bg"],
                         fg=PALETTE["tab_selected_fg"] if on else PALETTE["tab_fg"],
                         pady=self._pad[1] + (self._px(SELECTED_RISE) if on else 0))

        self.after_idle(self._place_gap)

    def _place_gap(self):
        """Lays the window-coloured piece over the underline, inside the active tab's outline."""
        if self._current is None or self._current not in self._pages:
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


class FlatButton(tk.Frame):
    """
    A button drawn from a frame and a label, so its colours look the same on any PC
    (Windows draws tk.Button its own way). Used like tk.Button for what 24bit7 needs:
      b = FlatButton(parent, text="...", command=handler, width=16, height=2)
      b.config(state="disabled") / b.config(state="normal")
    quiet=True gives the plainer version: window colour, grey outline, no orange bar.
    """

    def __init__(self, master, text="", command=None, width=None, height=None, quiet=False, **kw):
        super().__init__(master, bg=PALETTE["button_outline"], **kw)
        try:
            scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            scale = 1.0
        px = lambda n: max(1, int(round(n * scale)))
        self._command = command
        self._quiet = quiet
        self._state = "normal"
        self._inside = False
        self._bg = (PALETTE["button_quiet_bg"] or master.cget("bg")) if quiet else PALETTE["button_bg"]
        line = px(1)
        self._font = tkfont.nametofont("TkDefaultFont").copy()   # bold, at the usual size
        self._font.configure(weight="bold")
        self._label = tk.Label(self, text=text, width=width, height=height, bg=self._bg,
                               fg=PALETTE["button_fg"], font=self._font, cursor="hand2")
        self._label.pack(fill="both", expand=True, padx=line, pady=(line, 0))
        # The bar is orange, or on the quiet button the fill colour, so both are the same height
        self._bar = tk.Frame(self, height=px(BUTTON_BAR), bg=self._bar_colour(True))
        self._bar.pack(fill="x", padx=line, pady=(0, line))
        for widget in (self, self._label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)

    def config(self, cnf=None, **kw):
        if "state" in kw:
            self._set_state(kw.pop("state"))
        if "text" in kw:
            self._label.config(text=kw.pop("text"))
        if "command" in kw:
            self._command = kw.pop("command")
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

    def _set_state(self, state):
        self._state = "disabled" if str(state) == "disabled" else "normal"
        on = self._state == "normal"
        self._label.config(fg=PALETTE["button_fg"] if on else PALETTE["button_off_fg"],
                           bg=(PALETTE["button_hover"] if on and self._inside else self._bg),
                           cursor="hand2" if on else "")
        self._bar.config(bg=self._bar_colour(on))

    def _bar_colour(self, on):
        if self._quiet:
            return self._bg
        return PALETTE["button_accent"] if on else PALETTE["button_outline"]

    def _on_enter(self, _e):
        self._inside = True
        if self._state == "normal":
            self._label.config(bg=PALETTE["button_hover"])

    def _on_leave(self, _e):
        # Leaving the label for the frame's edge still counts as inside
        x, y = self.winfo_pointerxy()
        if self.winfo_containing(x, y) in (self, self._label, self._bar):
            return
        self._inside = False
        if self._state == "normal":
            self._label.config(bg=self._bg)

    def _on_press(self, _e):
        if self._state == "normal":
            self._label.config(bg=PALETTE["button_press"])

    def _on_release(self, _e):
        if self._state != "normal":
            return
        x, y = self.winfo_pointerxy()
        over = self.winfo_containing(x, y) in (self, self._label, self._bar)
        self._inside = over
        self._label.config(bg=PALETTE["button_hover"] if over else self._bg)
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


def matrix_dropdowns(root):
    """
    Dark theme for ttk widgets (dropdowns, tick boxes, the Discover table, scrollbars).
    Windows' own style ignores colours, so dark switches ttk to Tk's "clam" style,
    which takes them, and paints it black and matrix green.
    """
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        return
    bg, text, edge = PALETTE["window_bg"], PALETTE["text"], PALETTE["line"]
    faint, panel = PALETTE["text_faint"], PALETTE["button_bg"]
    style.configure(".", background=bg, foreground=text, bordercolor=edge, lightcolor=bg, darkcolor=bg,
                    troughcolor=bg, fieldbackground=MATRIX_BG, selectbackground=MATRIX_HI,
                    selectforeground=MATRIX_FG, insertcolor=MATRIX_FG, focuscolor=bg)
    style.map(".", foreground=[("disabled", faint)])
    # dropdowns
    style.configure("TCombobox", fieldbackground=MATRIX_BG, background=MATRIX_BG, foreground=MATRIX_FG,
                    arrowcolor=MATRIX_FG, bordercolor=edge, lightcolor=MATRIX_BG, darkcolor=MATRIX_BG,
                    selectbackground=MATRIX_BG, selectforeground=MATRIX_FG)
    style.map("TCombobox",
              fieldbackground=[("readonly", MATRIX_BG), ("disabled", MATRIX_BG)],
              foreground=[("disabled", faint), ("readonly", MATRIX_FG)],
              selectbackground=[("readonly", MATRIX_BG)],
              selectforeground=[("readonly", MATRIX_FG)],
              background=[("pressed", MATRIX_HI), ("active", MATRIX_HI)],
              arrowcolor=[("disabled", faint)])
    # tick boxes and round buttons: black box, green border and tick, green label
    # tick boxes and round buttons: white label, white border, black inside, green tick,
    # sized to the display scaling (the default is a fixed 10 pixels)
    try:
        scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        scale = 1.0
    for kind in ("TCheckbutton", "TRadiobutton"):
        style.configure(kind, background=bg, foreground=text, indicatorbackground=MATRIX_BG,
                        indicatorforeground=MATRIX_FG, upperbordercolor=text, lowerbordercolor=text,
                        indicatorsize=int(round(13 * scale)), indicatormargin=(0, 0, int(round(6 * scale)), 0))
        style.map(kind, background=[("active", bg)], foreground=[("disabled", faint)],
                  indicatorbackground=[("pressed", MATRIX_HI), ("disabled", bg)],
                  indicatorforeground=[("disabled", faint)],
                  upperbordercolor=[("disabled", faint)], lowerbordercolor=[("disabled", faint)])
    # a real tick instead of clam's cross: the tick box is drawn from images
    try:
        off, on, off_dim, on_dim = _tick_images(root, int(round(13 * scale)), scale, text, faint)
        gap = int(round(6 * scale))
        style.element_create("Matrix.Checkbutton.indicator", "image", off,
                             ("disabled selected", on_dim), ("disabled", off_dim), ("selected", on),
                             width=off.width() + gap, sticky="w")
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Matrix.Checkbutton.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"})]})]})])
    except tk.TclError:
        pass   # keep the drawn cross
    # the Discover table
    style.configure("Treeview", background=MATRIX_BG, fieldbackground=MATRIX_BG, foreground=MATRIX_FG,
                    bordercolor=edge, lightcolor=MATRIX_BG, darkcolor=MATRIX_BG)
    style.map("Treeview", background=[("selected", MATRIX_HI)], foreground=[("selected", MATRIX_FG)])
    style.configure("Treeview.Heading", background=MATRIX_BG, foreground=MATRIX_FG, bordercolor=edge,
                    lightcolor=MATRIX_BG, darkcolor=edge, relief="flat")
    style.map("Treeview.Heading", background=[("active", "#0a1f0f")])
    # scrollbars, entry boxes, spin boxes, buttons
    style.configure("TScrollbar", background=panel, troughcolor=bg, arrowcolor=MATRIX_FG,
                    bordercolor=edge, lightcolor=panel, darkcolor=panel)
    style.map("TScrollbar", background=[("active", PALETTE["tab_bg"])])
    style.configure("TEntry", fieldbackground=MATRIX_BG, foreground=MATRIX_FG)
    style.configure("TSpinbox", fieldbackground=MATRIX_BG, foreground=MATRIX_FG, arrowcolor=MATRIX_FG,
                    background=panel)
    style.configure("TButton", background=panel, foreground=MATRIX_FG)
    style.map("TButton", background=[("active", PALETTE["button_hover"])])
    # the list that drops down from a dropdown
    for key, value in (("*TCombobox*Listbox.background", MATRIX_BG),
                       ("*TCombobox*Listbox.foreground", MATRIX_FG),
                       ("*TCombobox*Listbox.selectBackground", MATRIX_HI),
                       ("*TCombobox*Listbox.selectForeground", MATRIX_FG)):
        root.option_add(key, value)


def _tick_images(root, size, scale, edge, dim):
    """
    Four tick box images (unticked, ticked, and both greyed out) at the given size:
    a square border, black inside, and a matrix green tick with a thick stroke.
    Kept on root so Tk doesn't lose them.
    """
    border = max(1, int(round(scale)))
    stroke = max(2, int(round(1.8 * scale)))

    def box(edge_colour, tick_colour):
        img = tk.PhotoImage(width=size, height=size)
        img.put(edge_colour, to=(0, 0, size, size))
        img.put(MATRIX_BG, to=(border, border, size - border, size - border))
        if tick_colour:
            points = [(0.22, 0.52), (0.42, 0.72), (0.80, 0.28)]
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                steps = size * 2
                for i in range(steps + 1):
                    x = (x1 + (x2 - x1) * i / steps) * size
                    y = (y1 + (y2 - y1) * i / steps) * size
                    half = stroke / 2
                    img.put(tick_colour, to=(max(border, int(x - half)), max(border, int(y - half)),
                                             min(size - border, int(x + half) + 1),
                                             min(size - border, int(y + half) + 1)))
        return img

    images = (box(edge, None), box(edge, MATRIX_FG), box(dim, None), box(dim, dim))
    root._tick_images = images
    return images
