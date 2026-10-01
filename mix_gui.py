"""
24bit7 - the Add playlist rows on the Play tab.

Each row: a handle to drag it up or down, the playlist (a picker with search,
most used first, a divider, then A to Z), how it joins (Mix, Add before, Add
after) and, for Mix, Spaced evenly or Mixed randomly. The x removes a row.
Saved as you go (playmix.py). Combining happens in the engine.
"""

import tkinter as tk
from tkinter import ttk

import playmix
import saved_playlists
import tabs
from tabs import PALETTE

HANDLE = "\u2261"     # the grab handle
DIVIDER = "\u2500" * 34


def _field_colours():
    """(background, text) for a field: black and matrix green on Dark, Windows' own on Light."""
    if tabs.THEME == "dark":
        return tabs.MATRIX_BG, tabs.MATRIX_FG
    return PALETTE["field_bg"] or "white", PALETTE["text"] or "black"


class MixRows(tk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.rows = playmix.rows()
        self._row_frames = []
        self._popup = None
        self._drag = None
        self._target = None
        self.body = tk.Frame(self)
        self.body.pack(fill="x")
        self.note = tk.Label(self, font=("Segoe UI", 8), fg=PALETTE["text_muted"], anchor="w", justify="left")
        self._draw()

    # --- rows -----------------------------------------------------------------

    def add(self):
        self.rows.append({"id": "", "name": "", "mode": "after", "spread": "even"})
        self._draw()
        self.after(50, lambda: self._open_picker(len(self.rows) - 1))

    def _save(self):
        playmix.set_rows(self.rows)
        self._show_note()
        if callable(getattr(self, "on_change", None)):
            self.on_change()   # the More options button counts the rows

    def _show_note(self):
        text = playmix.summary(self.rows)
        self.note.config(text=text)
        if text:
            self.note.pack(fill="x", pady=(4, 0))
        else:
            self.note.pack_forget()
        if not self.rows:
            self.configure(height=1)   # nothing showing: no leftover space

    def _draw(self):
        for child in self.body.winfo_children():
            child.destroy()
        self._row_frames = []
        fbg, ffg = _field_colours()
        for i, r in enumerate(self.rows):
            row = tk.Frame(self.body, padx=6, pady=3, highlightthickness=1,
                           highlightbackground=PALETTE["line"], highlightcolor=PALETTE["line"])
            row.pack(fill="x", pady=(4, 0))
            handle = tk.Label(row, text=HANDLE, font=("Segoe UI", 13), fg=PALETTE["text_muted"], cursor="fleur")
            handle.pack(side="left", padx=(0, 8))
            handle.bind("<ButtonPress-1>", lambda e, i=i: self._drag_start(i))
            handle.bind("<B1-Motion>", self._drag_move)
            handle.bind("<ButtonRelease-1>", self._drag_end)

            pick = tk.Label(row, text=f"{r['name'] or 'Choose a playlist'}  \u25be", width=36, anchor="w",
                            bg=fbg, fg=ffg, relief="solid", bd=1, padx=6, pady=2, cursor="hand2")
            pick.pack(side="left")
            pick.bind("<Button-1>", lambda e, i=i: self._open_picker(i))
            row.pick = pick

            mode = ttk.Combobox(row, values=list(playmix.MODES.values()), state="readonly", width=11)
            mode.set(playmix.MODES[r["mode"]])
            mode.pack(side="left", padx=(10, 0))
            mode.bind("<<ComboboxSelected>>", lambda e, i=i, cb=mode: self._set_mode(i, cb.get()))
            if r["mode"] == "mix":
                spread = ttk.Combobox(row, values=list(playmix.SPREADS.values()), state="readonly", width=15)
                spread.set(playmix.SPREADS[r["spread"]])
                spread.pack(side="left", padx=(8, 0))
                spread.bind("<<ComboboxSelected>>", lambda e, i=i, cb=spread: self._set_spread(i, cb.get()))

            remove = tk.Label(row, text="\u2715", fg=PALETTE["text_muted"], cursor="hand2", padx=4)
            remove.pack(side="left", padx=(12, 0))
            remove.bind("<Button-1>", lambda e, i=i: self._remove(i))
            self._row_frames.append(row)
        # Tk keeps a frame's old size once its last child goes, so with no rows the
        # rows' frame is unpacked and shrunk, leaving no gap above the log
        if self.rows:
            if self.note.winfo_manager():
                self.body.pack(fill="x", before=self.note)
            else:
                self.body.pack(fill="x")
        else:
            self.body.pack_forget()
            self.body.configure(height=1)
        self._show_note()

    def _set_mode(self, i, label):
        self.rows[i]["mode"] = next(k for k, v in playmix.MODES.items() if v == label)
        self._save()
        self._draw()   # shows or hides the Mix choice

    def _set_spread(self, i, label):
        self.rows[i]["spread"] = next(k for k, v in playmix.SPREADS.items() if v == label)
        self._save()

    def _remove(self, i):
        self._close_picker(prune=False)
        if 0 <= i < len(self.rows):
            self.rows.pop(i)
        self._save()
        self._draw()

    # --- drag to reorder ---------------------------------------------------------

    def _drag_start(self, i):
        self._close_picker(prune=False)
        self._drag, self._target = i, i

    def _drag_move(self, event):
        if self._drag is None or not self._row_frames:
            return
        target = len(self._row_frames) - 1
        for j, frame in enumerate(self._row_frames):
            if event.y_root < frame.winfo_rooty() + frame.winfo_height() // 2:
                target = j
                break
        self._target = target
        for j, frame in enumerate(self._row_frames):
            edge = PALETTE["brand_orange"] if (j == target and j != self._drag) else PALETTE["line"]
            frame.config(highlightbackground=edge, highlightcolor=edge)

    def _drag_end(self, _event):
        if self._drag is None:
            return
        i, t = self._drag, self._target
        self._drag = self._target = None
        if t is not None and t != i:
            self.rows.insert(t, self.rows.pop(i))
            self._save()
        self._draw()

    # --- the playlist picker -----------------------------------------------------

    def _close_picker(self, prune=True):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None
        if prune and any(not r["id"] for r in self.rows):   # a new row closed without a choice
            self.rows = [r for r in self.rows if r["id"]]
            self._draw()

    def _open_picker(self, i):
        self._close_picker(prune=False)   # keeps a new row's place while its picker opens
        if not (0 <= i < len(self.rows)) or i >= len(self._row_frames):
            return
        try:
            playlists = saved_playlists.scan()
        except Exception:
            playlists = None
        anchor = self._row_frames[i].pick
        fbg, ffg = _field_colours()
        hi = tabs.MATRIX_HI if tabs.THEME == "dark" else "#cfe0f7"
        pop = tk.Toplevel(self)
        pop.wm_overrideredirect(True)
        pop.wm_geometry(f"+{anchor.winfo_rootx()}+{anchor.winfo_rooty() + anchor.winfo_height()}")
        box = tk.Frame(pop, highlightthickness=1, highlightbackground=PALETTE["line"], bg=fbg)
        box.pack(fill="both", expand=True)
        search = tk.Entry(box, bg=fbg, fg=ffg, insertbackground=ffg, relief="solid", bd=1, font=("Segoe UI", 9))
        search.pack(fill="x", padx=6, pady=6)
        holder = tk.Frame(box, bg=fbg)
        holder.pack(fill="both", expand=True, padx=(6, 0), pady=(0, 6))
        lb = tk.Listbox(holder, height=14, width=46, activestyle="none", exportselection=False, bg=fbg, fg=ffg,
                        selectbackground=hi, selectforeground=ffg, highlightthickness=0, bd=0, font=("Segoe UI", 9))
        bar = ttk.Scrollbar(holder, orient="vertical", command=lb.yview)
        lb.config(yscrollcommand=bar.set)
        lb.pack(side="left", fill="both", expand=True)
        bar.pack(side="left", fill="y")
        items = []   # one per line: a playlist, or None for headings, the divider and notes
        muted = PALETTE["text_muted"]

        def label(p):
            name = p["Name"]
            if sum(1 for q in playlists if q["Name"] == name) > 1 and p.get("Folder") not in (None, "", saved_playlists.ROOT):
                name += f"   ({p['Folder']})"   # two playlists share the name: say which folder
            return name

        def line(text, item=None, faint=False):
            lb.insert("end", text)
            items.append(item)
            if faint:
                lb.itemconfig("end", fg=muted, selectforeground=muted, selectbackground=fbg)

        def fill(*_):
            lb.delete(0, "end")
            items.clear()
            if playlists is None:
                line("JRiver isn't answering, so there are no playlists to show.", faint=True)
                return
            used, rest = playmix.picker_order(playlists, search.get())
            if used:
                line("Most used", faint=True)
                for p, count in used:
                    line(f"{label(p)}   ({count})", p)
            if used and rest:
                line(DIVIDER, faint=True)
            if rest:
                line("All playlists", faint=True)
                for p in rest:
                    line(label(p), p)
            if not used and not rest:
                line("No playlists match", faint=True)

        def choose(item):
            if item is None:
                return
            self.rows[i]["id"], self.rows[i]["name"] = item["ID"], item["Name"]
            self._save()
            self._close_picker()
            self._draw()

        def clicked(_e):
            sel = lb.curselection()
            if sel:
                item = items[sel[0]]
                if item is None:
                    lb.selection_clear(0, "end")
                    return
                choose(item)

        def first_match(_e):
            choose(next((x for x in items if x is not None), None))

        def maybe_close():
            try:
                focus = pop.focus_get()
            except (KeyError, tk.TclError):
                focus = None
            if self._popup is pop and (focus is None or not str(focus).startswith(str(pop))):
                self._close_picker()

        search.bind("<KeyRelease>", lambda e: fill() if e.keysym not in ("Return", "Escape") else None)
        search.bind("<Return>", first_match)
        pop.bind("<Escape>", lambda e: self._close_picker())
        lb.bind("<<ListboxSelect>>", clicked)
        pop.bind("<FocusOut>", lambda e: pop.after(150, maybe_close))
        self._popup = pop
        fill()
        pop.lift()
        search.focus_force()
