"""
24bit7 - desktop GUI (Play window).

The first of three windows. Drives the same engine.py the CLI does, passing a
progress reporter that streams into the on-screen log instead of the console.
Each playlist run happens on a background thread so the window stays responsive,
with log lines marshalled back to the UI through a thread-safe queue.

Settings and Discover windows come later; this is the Play window only.
"""

import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

import engine
from settings_gui import SettingsWindow


REFRESH_MS = 3000          # how often to re-read Now Playing from JRiver
POLL_MS = 100              # how often the UI drains the log queue


class App:
    def __init__(self, root):
        self.root = root
        root.title("24bit7")
        root.geometry("640x560")
        root.minsize(520, 420)

        self.log_queue = queue.Queue()
        self.running = False
        self.last_playing = None

        self._build_now_playing()
        self._build_buttons()
        self._build_log()

        self._refresh_now_playing()
        self.root.after(POLL_MS, self._drain_log_queue)

    # --- UI construction ---------------------------------------------------

    def _build_now_playing(self):
        frame = tk.Frame(self.root, padx=16, pady=12)
        frame.pack(fill="x")

        tk.Label(frame, text="NOW PLAYING", font=("Segoe UI", 8, "bold"),
                 fg="#888").pack(anchor="w")
        self.np_track = tk.Label(frame, text="...", font=("Segoe UI", 14, "bold"),
                                 anchor="w", justify="left", wraplength=580)
        self.np_track.pack(anchor="w", fill="x")
        self.np_detail = tk.Label(frame, text="", font=("Segoe UI", 10),
                                  fg="#555", anchor="w", justify="left", wraplength=580)
        self.np_detail.pack(anchor="w", fill="x")

    def _build_buttons(self):
        frame = tk.Frame(self.root, padx=16, pady=4)
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
        tk.Button(frame, text="Settings", command=self.on_settings,
                  width=10, height=2).pack(side="right")

    def _build_log(self):
        frame = tk.Frame(self.root, padx=16, pady=12)
        frame.pack(fill="both", expand=True)
        self.log = scrolledtext.ScrolledText(frame, wrap="word", state="disabled",
                                             font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        self.log.pack(fill="both", expand=True)

    # --- Now Playing refresh ----------------------------------------------

    def _refresh_now_playing(self):
        # Only touch JRiver when idle, to avoid clashing with a running job.
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
        self.root.after(REFRESH_MS, self._refresh_now_playing)

    # --- Logging plumbing --------------------------------------------------

    def report(self, message):
        """Passed to the engine; safe to call from the worker thread."""
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
        self.root.after(POLL_MS, self._drain_log_queue)

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # --- Running a job -----------------------------------------------------

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

    # --- Button handlers ---------------------------------------------------

    def on_similar(self):
        self._run_job(lambda: engine.create_similar_playlist(report=self.report))

    def on_top_tracks(self):
        self._run_job(lambda: engine.play_top_n(report=self.report))

    def on_credits(self):
        self._run_job(lambda: engine.explore_credits(report=self.report))

    def on_settings(self):
        SettingsWindow(self.root)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()