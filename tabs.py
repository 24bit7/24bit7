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

PALETTE = {
    "tab_selected_bg": "#7d7d7d",   # the selected tab is filled with the same grey as the lines...
    "tab_selected_fg": "#ffffff",   # ...with white text
    "tab_bg":          "#dfe4ee",   # unselected tabs: pale blue
    "tab_fg":          "#1f4e9c",   # ...with logo-blue text
    "line":            "#7d7d7d",   # tab outlines, the line under the tabs, the box round a panel
    "brand_blue":      "#1f4e9c",
    "brand_orange":    "#f28c28",
}

LINE_WIDTH = 1      # thickness of every line, at normal (100%) display scaling
TAB_GAP = 4         # space between tabs
SELECTED_RISE = 3   # how much taller the selected tab stands


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
        tk.Frame(self, height=self._line, bg=PALETTE["line"]).pack(fill="x")   # the line under the tabs
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

    # --- helpers ------------------------------------------------------------

    def tabs_width(self):
        """Width taken by the tab buttons, for anything that wants to sit beside them."""
        self.update_idletasks()
        return self._strip.winfo_reqwidth() + self._strip.winfo_x()

    def strip_height(self):
        self.update_idletasks()
        return self._strip.winfo_reqheight()

    def _paint(self):
        for label, page in zip(self._tabs, self._pages):
            on = page is self._current
            label.config(bg=PALETTE["tab_selected_bg"] if on else PALETTE["tab_bg"],
                         fg=PALETTE["tab_selected_fg"] if on else PALETTE["tab_fg"],
                         pady=self._pad[1] + (self._px(SELECTED_RISE) if on else 0))
