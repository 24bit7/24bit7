"""
Take a Tour of the advanced settings (Ben, 2 Nov 2026). From the Playlist Settings page, in Advanced,
Take a Tour opens Artist + Guests (two matching rules blended, so the best example of what's possible),
dims the page and lights one section at a time with a pop-up: Back, Next, Close and "n of 14". The
pop-up texts are the sections' own hover notes (SECTION_NOTES: what it does, then why you'd want it),
written once and used in both places.

The dimming is a see-through black window laid over the page with a hole cut where the lit section
is (Windows draws one colour of a window as fully transparent, so the hole is painted in that colour).
The pop-up is a small borderless window beside the hole. Both follow the main window if it moves and
go when the tour closes, the page is rebuilt or the window is hidden.
"""

import tkinter as tk

import tabs
from i18n import N_, t
from tabs import PALETTE

# The thirteen section notes: the header hover notes and the tour's pop-ups. Two sentences each: what it
# does, then why you'd want it. Keyed by the section's English title.
SECTION_NOTES = {
    "Sources": N_("Which services suggest artists or tracks, and how many must agree before a suggestion counts. "
                  "Tick more for richer, slower playlists; fewer for quicker ones."),
    "Playlist Selection": N_("How many tracks the playlist aims for and how they're chosen from the artists found, with a "
                             "second line for Seed on Playing Now. Change these when playlists come out too long, too short "
                             "or too samey."),
    "Filters": N_("Rules every track this config finds must pass, such as stereo only or nothing played this month. Each "
                  "config has its own, so one can draw on the whole library while another stays strict."),
    "Mix": N_("How two or more configs come together: shuffled in, one after the other, or taking turns by a pattern. "
              "It's what makes Artist + Guests alternate two hosts with a guest."),
    "Consensus": N_("Takes the seed's closest few artists and keeps only the artists their own lists agree on, so every "
                    "pick is vouched for twice over. Tight and sometimes short, so there's a fallback to plain matching "
                    "if it finds too few."),
    "Moderator": N_("Checks the finished playlist once with your AI and removes tracks that clash with the seed's tone, "
                    "energy and mood, saying why. Worth having on when a playlist keeps landing one jarring track; it "
                    "spends a little AI credit each time."),
    "Drift": N_("When a playlist comes up short, searches again from what's already been found, round by round, until "
                "it reaches its length. Have it on when seeds run short and you'd rather the playlist filled out than "
                "stopped."),
    "Deep Cuts": N_("Tops the playlist up with tracks you've played least in the seed's genre, spaced through it or "
                    "shuffled in. It gives the corners of your collection a turn."),
    "Non-stop": N_("When the last track of a playlist starts, more are added to the end so the music doesn't stop. Keep "
                   "It Tight stays close to the original playlist; Wander follows the music as the evening goes on."),
    "Shortcut": N_("Keys that build this playlist from anywhere in Windows, even with 24bit7 in the tray. Useful for the "
                   "one you reach for most."),
    "Hidden Tracks": N_("Some albums hide a bonus track after a long silence at the end of their last track. 24bit7 "
                        "plays the song and moves on when the silence starts. Albums you ask for by name always play "
                        "in full, and while 24bit7 is closed the hidden track plays. To leave out long tracks "
                        "altogether, turn on Long Tracks under Settings > Filters."),
    "If All Else Fails": N_("What happens when a build finds nothing: shuffle the seed's genre, run a file or play a JRiver "
                            "playlist. Have it on so a quiet seed never leaves the room silent."),
    "Run After Building": N_("Runs a file of yours once the playlist is in JRiver, such as a script that dims the lights. "
                             "Only when the build worked, and never when Non-stop adds more."),
}

# The order the tour visits them: the config's own sections first, then the whole-playlist ones
ORDER = ("Sources", "Playlist Selection", "Filters", "Mix", "Consensus", "Moderator", "Drift", "Deep Cuts",
         "Non-stop", "Shortcut", "Hidden Tracks", "If All Else Fails", "Run After Building")

OPENER = N_("For a tour of the advanced settings we'll use Artist + Guests. It blends two matching rules, the artist's "
            "own top tracks with tracks from artists like them, so it's a good example of what's possible. Next takes "
            "you through each section in turn.")

HOLE = "#ff00fe"   # the overlay's see-through colour: not a colour the page uses


def note_for(title):
    """The note for a section's English title, in the chosen language, or None."""
    text = SECTION_NOTES.get(title)
    return t(text) if text else None


def sections_of(page):
    """{English title: the section's outer frame} for the first section of each title under page, in ORDER."""
    found = {}
    for w in _walk(page):
        title = getattr(w, "section_title", None)
        if title and title not in found and w.winfo_manager():
            found[title] = w
    return {title: found[title] for title in ORDER if title in found}


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


class Tour:
    """
    One run of the tour over a Playlist Settings page. page is the page's inner frame (the sections'
    ancestor, inside its scrolling canvas); on_close is told when the tour ends, however it ends.
    steps[0] is the opener (no section lit); each later step is a section's English title.
    """

    def __init__(self, page, on_close=None):
        self.page = page
        self.root = page.winfo_toplevel()
        self.on_close = on_close
        self.sections = sections_of(page)
        self.steps = [None] + list(self.sections)
        self.at = 0
        self.opened = None   # a section the tour opened to show it, refolded when the tour moves on
        self._bound = []
        self.shade = self.popup = None
        self._build()
        self.show(0)
        for seq in ("<Configure>", "<Unmap>", "<Destroy>", "<Escape>"):   # a binding on the window hears every widget in it
            self._bound.append((self.root, seq, self.root.bind(seq, self._root_changed, add="+")))
        self._bound.append((page, "<Destroy>", page.bind("<Destroy>", lambda e: self.close(), add="+")))

    # --- what's on screen ---------------------------------------------------------------------------

    def _build(self):
        try:
            scale = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            scale = 1.0
        px = lambda n: int(round(n * scale))
        self.shade = tk.Toplevel(self.root, bg="black")
        self.shade.overrideredirect(True)
        self.shade.transient(self.root)
        try:
            self.shade.attributes("-alpha", 0.55)
            self.shade.attributes("-transparentcolor", HOLE)
        except tk.TclError:
            pass
        self.hole = tk.Frame(self.shade, bg=HOLE)
        self.shade.bind("<Button-1>", lambda e: self.close())
        bg = PALETTE.get("window_bg") or self.root.cget("bg")
        edge = PALETTE["button_fg"]
        self.popup = tk.Toplevel(self.root, bg=edge)
        self.popup.overrideredirect(True)
        self.popup.transient(self.root)
        card = tk.Frame(self.popup, bg=bg, padx=16, pady=12)
        card.pack(padx=1, pady=1)
        self.count = tk.Label(card, text="", bg=bg, fg=PALETTE["help_fg"], font=("Segoe UI", 9))
        self.count.pack(anchor="w")
        self.title = tk.Label(card, text="", bg=bg, fg=edge, font=("Segoe UI", 11, "bold"), anchor="w")
        self.title.pack(anchor="w", pady=(2, 4))
        self.text = tk.Label(card, text="", bg=bg, fg=PALETTE["text"], font=("Segoe UI", 10), justify="left",
                             wraplength=px(380), anchor="w")
        self.text.pack(anchor="w")
        row = tk.Frame(card, bg=bg)
        row.pack(fill="x", pady=(12, 0))
        self.back = tabs.FlatButton(row, text=t("Back"), command=self.back_, quiet=True)
        self.back.pack(side="left")
        self.next = tabs.FlatButton(row, text=t("Next"), command=self.next_)
        self.next.pack(side="left", padx=(8, 0))
        tabs.FlatButton(row, text=t("Close"), command=self.close, quiet=True).pack(side="right")
        self.popup.bind("<Right>", lambda e: self.next_())
        self.popup.bind("<Left>", lambda e: self.back_())
        self.popup.bind("<Escape>", lambda e: self.close())

    def show(self, n):
        """Lights step n: scrolls its section into view, opens it if closed, and places the pop-up beside it."""
        if self.opened is not None:   # the last step's section goes back to how its setting leaves it
            self.opened.refold()
            self.opened = None
        self.at = max(0, min(n, len(self.steps) - 1))
        title = self.steps[self.at]
        self.lit = self.sections.get(title) if title else None
        if self.lit is not None:
            box = self.lit.winfo_children()[1] if len(self.lit.winfo_children()) > 1 else None
            if box is not None and hasattr(box, "is_open") and not box.is_open():
                box.open()
                self.opened = box
            self._scroll_to(self.lit)
        self.count.config(text=t("{n} of {total}", n=self.at + 1, total=len(self.steps)))
        self.title.config(text=t(title) if title else t("Take a Tour"))
        self.text.config(text=note_for(title) if title else t(OPENER))
        self.back.config(state="normal" if self.at > 0 else "disabled")
        self.next.config(text=t("Finish") if self.at == len(self.steps) - 1 else t("Next"))
        self.root.after_idle(self._place)

    def _scroll_to(self, outer):
        """Scrolls the page so the section is in view (the page's inner frame sits in a canvas)."""
        canvas = self.page.master
        if not isinstance(canvas, tk.Canvas):
            return
        self.root.update_idletasks()
        total = max(1, self.page.winfo_height())
        top = outer.winfo_rooty() - self.page.winfo_rooty()
        bottom = top + outer.winfo_height()
        view_top = canvas.canvasy(0)
        view_h = canvas.winfo_height()
        if top < view_top or bottom > view_top + view_h:
            canvas.yview_moveto(max(0.0, (top - 16) / total))

    def _place(self):
        """The shade over the page with its hole on the lit section, and the pop-up beside the hole."""
        if self.shade is None or not self.shade.winfo_exists():
            return
        try:
            canvas = self.page.master
            area = canvas if isinstance(canvas, tk.Canvas) else self.page
            ax, ay = area.winfo_rootx(), area.winfo_rooty()
            aw, ah = max(1, area.winfo_width()), max(1, area.winfo_height())
            self.shade.geometry(f"{aw}x{ah}+{ax}+{ay}")
            if self.lit is not None and self.lit.winfo_ismapped():
                hx, hy = self.lit.winfo_rootx() - ax, self.lit.winfo_rooty() - ay
                hw, hh = self.lit.winfo_width(), self.lit.winfo_height()
                self.hole.place(x=hx - 4, y=hy - 4, width=hw + 8, height=hh + 8)
            else:
                self.hole.place_forget()
            self.popup.update_idletasks()
            pw, ph = self.popup.winfo_reqwidth(), self.popup.winfo_reqheight()
            if self.lit is not None and self.lit.winfo_ismapped():
                lx, ly = self.lit.winfo_rootx(), self.lit.winfo_rooty()
                lw, lh = self.lit.winfo_width(), self.lit.winfo_height()
                px_ = min(max(ax, lx + lw // 2 - pw // 2), ax + aw - pw)
                py_ = ly + lh + 10
                if py_ + ph > ay + ah:   # no room below: above it, or over its lower half as a last resort
                    py_ = max(ay, ly - ph - 10) if ly - ph - 10 >= ay else ly + lh - ph
            else:
                px_, py_ = ax + (aw - pw) // 2, ay + (ah - ph) // 2
            self.popup.geometry(f"+{px_}+{py_}")
            self.shade.lift()
            self.popup.lift()
            self.popup.focus_set()
        except tk.TclError as e:   # a widget mid-rebuild: the next placing sets it right, and a destroyed page closes the tour
            self.last_error = str(e)

    def _root_changed(self, event=None):
        """The main window moved, resized, was hidden or closed (events of its widgets arrive here too, and are ignored)."""
        if event is not None and event.type == tk.EventType.KeyPress:   # Escape, from anywhere in the window
            self.close()
            return
        if event is not None and event.widget is not self.root:
            return
        if event is not None and event.type in (tk.EventType.Unmap, tk.EventType.Destroy):
            self.close()
        else:
            self.root.after_idle(self._place)

    # --- the buttons -----------------------------------------------------------------------------------

    def next_(self):
        if self.at >= len(self.steps) - 1:
            self.close()
        else:
            self.show(self.at + 1)

    def back_(self):
        if self.at > 0:
            self.show(self.at - 1)

    def close(self):
        if self.shade is None:
            return
        if self.opened is not None:
            try:
                self.opened.refold()
            except tk.TclError:
                pass
            self.opened = None
        for widget, seq, funcid in self._bound:
            try:
                widget.unbind(seq, funcid)
            except tk.TclError:
                pass
        self._bound = []
        for win in (self.shade, self.popup):
            try:
                win.destroy()
            except tk.TclError:
                pass
        self.shade = self.popup = None
        if self.on_close:
            self.on_close()

    @property
    def running(self):
        return self.shade is not None
