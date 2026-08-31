"""
24bit7 - main window.

Three tabs in one window:
  Play      - now-playing, the three playlist actions, and a live log
  Discover  - browse logged discoveries (built in the next step)
  Settings  - auto-saving preferences and keys

The Play tab drives engine.py on a background thread, streaming progress into
its log via a thread-safe queue so the window never freezes.
"""

import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import engine
from settings_gui import SettingsTab
from discover_gui import DiscoverTab


REFRESH_MS = 3000
POLL_MS = 100


class PlayTab(tk.Frame):
    def __init__(self, master, root):
        super().__init__(master)
        self.root = root
        self.log_queue = queue.Queue()
        self.running = False
        self.last_playing = None

        self._build_now_playing()
        self._build_buttons()
        self._build_log()

        # First Now Playing read happens just after the window appears, not
        # during construction, so a slow JRiver never delays startup.
        self.after(200, self._refresh_now_playing)
        self.after(POLL_MS, self._drain_log_queue)

    def _build_now_playing(self):
        header = tk.Frame(self, padx=16, pady=12)
        header.pack(fill="x")
        title = tk.Frame(header)
        title.pack(anchor="w")
        BLUE, ORANGE = "#1f4e9c", "#f28c28"
        for part, colour in (("24", BLUE), ("bit", ORANGE), ("7", BLUE)):
            tk.Label(title, text=part, font=("Segoe UI", 18, "bold"),
                     fg=colour).pack(side="left", padx=0)
        tk.Label(header, text="Smart Playlist Creator and Music Discovery Tool",
                 font=("Segoe UI", 10), fg="#666").pack(anchor="w")

        frame = tk.Frame(self, padx=16, pady=8)
        frame.pack(fill="x")
        tk.Label(frame, text="NOW PLAYING", font=("Segoe UI", 8, "bold"), fg="#888").pack(anchor="w")
        self.np_track = tk.Label(frame, text="...", font=("Segoe UI", 14, "bold"),
                                 anchor="w", justify="left")
        self.np_track.pack(anchor="w", fill="x")
        self.np_detail = tk.Label(frame, text="", font=("Segoe UI", 10), fg="#555",
                                  anchor="w", justify="left")
        self.np_detail.pack(anchor="w", fill="x")
        # Wrap only when text genuinely exceeds the available width.
        frame.bind("<Configure>", lambda e: (
            self.np_track.config(wraplength=max(200, e.width - 32)),
            self.np_detail.config(wraplength=max(200, e.width - 32))))

    def _build_buttons(self):
        frame = tk.Frame(self, padx=16, pady=4)
        frame.pack(fill="x")
        self.buttons = []
        for text, handler in [
            ("Similar Artists", self.on_similar),
            ("Artist's Top Tracks", self.on_top_tracks),
            ("Vibe Playlist", self.on_vibe),
            ("Show Credits", self.on_credits),
        ]:
            b = tk.Button(frame, text=text, command=handler, width=16, height=2)
            b.pack(side="left", padx=(0, 8))
            self.buttons.append(b)

    def _build_log(self):
        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(frame, wrap="word", state="disabled",
                                             font=("Consolas", 9), bg="#000000", fg="#00ff41",
                                             insertbackground="#00ff41")
        self.log.pack(fill="both", expand=True)
        self._greeting_active = True
        self._type_greeting("Follow the white rabbit.", 0)

    def _refresh_now_playing(self):
        if not self.running:
            info = engine.get_playing_info()
            if info and info.get("PlayingNowPosition", "-1") != "-1":
                self.np_track.config(text=info.get("Name", "?"))
                self.np_detail.config(
                    text=f"{info.get('Artist', '?')}   \u00b7   {info.get('Album', '?')}")
                self.last_playing = info
            else:
                self.np_track.config(text="Nothing playing")
                self.np_detail.config(text="Start a track in JRiver to seed from it")
                self.last_playing = None
        self.after(REFRESH_MS, self._refresh_now_playing)

    def _type_greeting(self, text, i):
        """Types the greeting one character at a time, then clears it after 10 seconds."""
        if not self._greeting_active:
            return
        if i < len(text):
            self.log.config(state="normal")
            self.log.insert("end", text[i])
            self.log.config(state="disabled")
            self.after(60, lambda: self._type_greeting(text, i + 1))
        else:
            self.after(10000, self._clear_greeting)

    def _clear_greeting(self):
        if self._greeting_active:
            self._greeting_active = False
            self._clear_log()

    def _append_log(self, line):
        self.log.config(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def report(self, message):
        self.log_queue.put(message)

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        self.after(POLL_MS, self._drain_log_queue)

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _run_job(self, target, needs_playing=True):
        if self.running:
            return
        if needs_playing and not self.last_playing:
            messagebox.showinfo("Nothing playing",
                                "Start a track in JRiver first, then try again.")
            return
        self.running = True
        self._greeting_active = False
        for b in self.buttons:
            b.config(state="disabled")
        self._clear_log()

        def worker():
            try:
                target()
            except Exception as e:
                self.log_queue.put(f"[error] {e}")
            finally:
                self.root.after(0, self._job_done)

        threading.Thread(target=worker, daemon=True).start()

    def _job_done(self):
        self.running = False
        for b in self.buttons:
            b.config(state="normal")

    def on_similar(self):
        self._run_job(lambda: engine.create_similar_playlist(report=self.report))

    def on_top_tracks(self):
        self._run_job(lambda: engine.play_top_n(report=self.report))

    def on_credits(self):
        self._run_job(lambda: engine.explore_credits(report=self.report))

    def on_vibe(self):
        VibeDialog(self.root, on_submit=lambda vibe: self._run_job(
            lambda: engine.create_vibe_playlist(vibe, report=self.report), needs_playing=False))


class VibeDialog(tk.Toplevel):
    """
    Asks for a mood description. Three AI-suggested vibes load in the background
    and appear as clickable buttons; click one to use it, or type your own.
    """
    def __init__(self, master, on_submit):
        super().__init__(master)
        self.title("Vibe Playlist")
        self.resizable(False, False)
        self.on_submit = on_submit
        self.transient(master)

        body = tk.Frame(self, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Describe the mood, era, activity or feeling:",
                 font=("Segoe UI", 10)).pack(anchor="w")
        self.entry = tk.Entry(body, width=48, font=("Segoe UI", 11))
        self.entry.pack(fill="x", pady=(6, 10))
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self.submit())

        tk.Label(body, text="Or try one of these:", fg="#666").pack(anchor="w")
        self.suggest_frame = tk.Frame(body)
        self.suggest_frame.pack(fill="x", pady=(4, 12))
        self.loading = tk.Label(self.suggest_frame, text="Thinking...", fg="#999")
        self.loading.pack(anchor="w")

        bar = tk.Frame(body)
        bar.pack(fill="x")
        tk.Button(bar, text="Create playlist", width=16, command=self.submit).pack(side="right")
        tk.Button(bar, text="Cancel", width=10, command=self.destroy).pack(side="right", padx=(0, 8))

        threading.Thread(target=self._load_suggestions, daemon=True).start()

    def _load_suggestions(self):
        try:
            ideas = engine.ai_vibe_suggestions()
        except Exception:
            ideas = []
        self.after(0, lambda: self._show_suggestions(ideas))

    def _show_suggestions(self, ideas):
        if not self.winfo_exists():
            return
        self.loading.destroy()
        if not ideas:
            tk.Label(self.suggest_frame, text="(no suggestions right now)", fg="#999").pack(anchor="w")
            return
        for idea in ideas:
            tk.Button(self.suggest_frame, text=idea, anchor="w",
                      command=lambda t=idea: self._use(t)).pack(fill="x", pady=2)

    def _use(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()

    def submit(self):
        vibe = self.entry.get().strip()
        if not vibe:
            return
        self.destroy()
        self.on_submit(vibe)


def _enable_dpi_awareness():
    """Tell Windows this app is DPI-aware so text renders sharp, not upscaled."""
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main():
    _enable_dpi_awareness()
    root = tk.Tk()
    root.title("24bit7")
    # Open at 75% of the screen so it fits any monitor/DPI, then centre it.
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    w, h = int(sw * 0.75), int(sh * 0.75)
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
    root.minsize(680, 480)

    style = ttk.Style(root)
    # Bigger, bolder tabs that clearly read as tabs: the selected one is white
    # and raised, the others sit grey and slightly lower.
    style.configure("TNotebook", tabmargins=(8, 6, 0, 0))
    style.configure("TNotebook.Tab", font=("Segoe UI", 11, "bold"),
                    padding=(18, 8), background="#d9d9d9", foreground="#555")
    style.map("TNotebook.Tab",
              background=[("selected", "#ffffff")],
              foreground=[("selected", "#000000")],
              padding=[("selected", (18, 10))])

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    play = PlayTab(nb, root)
    discover = DiscoverTab(nb)
    nb.add(play, text="Play")
    nb.add(discover, text="Discover")
    nb.add(SettingsTab(nb), text="Settings")

    def on_tab_changed(event):
        if nb.select() == str(discover):
            discover.ensure_loaded()
    nb.bind("<<NotebookTabChanged>>", on_tab_changed)

    root.mainloop()


if __name__ == "__main__":
    main()