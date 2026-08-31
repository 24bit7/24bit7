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

        self._refresh_now_playing()
        self.after(POLL_MS, self._drain_log_queue)

    def _build_now_playing(self):
        header = tk.Frame(self, padx=16, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="24bit7", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(header, text="Smart Playlist Creator and Music Discovery tool",
                 font=("Segoe UI", 10), fg="#666").pack(anchor="w")

        frame = tk.Frame(self, padx=16, pady=8)
        frame.pack(fill="x")
        tk.Label(frame, text="NOW PLAYING", font=("Segoe UI", 8, "bold"), fg="#888").pack(anchor="w")
        self.np_track = tk.Label(frame, text="...", font=("Segoe UI", 14, "bold"),
                                 anchor="w", justify="left", wraplength=580)
        self.np_track.pack(anchor="w", fill="x")
        self.np_detail = tk.Label(frame, text="", font=("Segoe UI", 10), fg="#555",
                                  anchor="w", justify="left", wraplength=580)
        self.np_detail.pack(anchor="w", fill="x")

    def _build_buttons(self):
        frame = tk.Frame(self, padx=16, pady=4)
        frame.pack(fill="x")
        self.buttons = []
        for text, handler in [
            ("Similar Artists", self.on_similar),
            ("Top Tracks", self.on_top_tracks),
            ("Show Credits", self.on_credits),
        ]:
            b = tk.Button(frame, text=text, command=handler, width=16, height=2)
            b.pack(side="left", padx=(0, 8))
            self.buttons.append(b)

    def _build_log(self):
        frame = tk.Frame(self, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(frame, wrap="word", state="disabled",
                                             font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        self.log.pack(fill="both", expand=True)

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

    def report(self, message):
        self.log_queue.put(message)

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log.config(state="normal")
                self.log.insert("end", line + "\n")
                self.log.see("end")
                self.log.config(state="disabled")
        except queue.Empty:
            pass
        self.after(POLL_MS, self._drain_log_queue)

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _run_job(self, target):
        if self.running:
            return
        if not self.last_playing:
            messagebox.showinfo("Nothing playing",
                                "Start a track in JRiver first, then try again.")
            return
        self.running = True
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
    root.geometry("900x620")
    root.minsize(680, 480)

    style = ttk.Style(root)
    # Bigger, bolder notebook tab labels
    style.configure("TNotebook.Tab", font=("Segoe UI", 11, "bold"), padding=(16, 8))

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    nb.add(PlayTab(nb, root), text="Play")
    nb.add(DiscoverTab(nb), text="Discover")
    nb.add(SettingsTab(nb), text="Settings")

    root.mainloop()


if __name__ == "__main__":
    main()