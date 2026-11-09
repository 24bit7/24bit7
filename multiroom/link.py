"""
The app's end of the follower (Multiroom, stage two, 9 Nov 2026): starts the child process, forwards its lines to
the console as "Multiroom: ...", stops it, and starts it once more if it dies while it's wanted.

    link = Link(say=console_line)
    link.start(engine.multiroom_settings())   # the Speakers join what the Sonos plays, or wait for it to play
    link.stop()                                # the Speakers stop and the child exits

The protocol is in multiroom.service. spawn(port) is how the child is started; the default runs 24bit7.exe --follow
(packed) or py -m multiroom.service (in the repo); the tests pass a function that runs a Service on a thread.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time

PREFIX = "Multiroom: "
ACCEPT_TIMEOUT = 15.0
STEADY_FOR = 60.0   # a child that ran this long before dying earns another restart


def default_spawn(port):
    """Starts the child process and returns the Popen."""
    frozen = getattr(sys, "frozen", False)
    if frozen:
        cmd = [sys.executable, "--follow", "--port", str(port)]
        cwd = os.path.dirname(sys.executable)
    else:
        cmd = [sys.executable, "-m", "multiroom.service", "--port", str(port)]
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return subprocess.Popen(cmd, cwd=cwd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class Link:
    def __init__(self, say=print, spawn=default_spawn, on_state=None):
        self.say, self.spawn = say, spawn
        self.on_state = on_state   # called with the new state (following, idle, off) as it changes
        self.lock = threading.Lock()
        self.conn = self.proc = None
        self.settings = None
        self.wanted = False       # the follower should be running
        self.restarted = False    # it has already been started once more after dying
        self.since = 0.0          # when the child last connected
        self.state = "off"        # off, starting, following, idle

    # --- starting and stopping ---------------------------------------------------------------------
    def start(self, settings):
        """Starts the child if it isn't running and tells it to follow with these settings."""
        with self.lock:
            self.settings, self.wanted = dict(settings), True
            if self.conn is not None:
                self._send(cmd="start", **self.settings)
                return
            self.state = "starting"
        threading.Thread(target=self._launch, daemon=True, name="multiroom-link").start()

    def stop(self):
        """Stops the Speakers and the child. Safe to call when nothing is running."""
        with self.lock:
            self.wanted = False
            conn, proc = self.conn, self.proc
            if conn is not None:
                self._send(cmd="stop")
                self._send(cmd="quit")
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
        if proc is not None and hasattr(proc, "wait"):
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        with self.lock:
            self.conn = self.proc = None
            self.state = "off"
        self._tell("off")

    def _tell(self, state):
        if self.on_state is not None:
            try:
                self.on_state(state)
            except Exception:
                pass

    def leave(self):
        """
        Output moved away from Multiroom: the Speakers finish the track they're on, then stop following (the
        follower says so). The child stays connected, idle, for a later start. Nothing running: nothing to do.
        """
        with self.lock:
            self.wanted = False
            if self.conn is not None:
                self._send(cmd="leave")

    def running(self):
        return self.conn is not None

    def nudge(self, ms):
        """Moves Start by ms in the running follower, so the Speakers shift as you listen. Nothing if it isn't running."""
        with self.lock:
            if self.conn is not None:
                self._send(cmd="nudge", ms=ms)

    # --- the child ----------------------------------------------------------------------------------
    def _launch(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            srv.settimeout(ACCEPT_TIMEOUT)
            port = srv.getsockname()[1]
            proc = self.spawn(port)
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                self.say(PREFIX + "Problem: the follower didn't start.")
                with self.lock:
                    self.state = "off"
                    self.wanted = False
                if proc is not None and hasattr(proc, "kill"):
                    proc.kill()
                return
        finally:
            srv.close()
        conn.settimeout(None)
        with self.lock:
            self.conn, self.proc = conn, proc
            self.since = time.monotonic()
            if not self.wanted:          # stopped while it was starting
                self._send(cmd="quit")
                return
            self._send(cmd="start", **self.settings)
        self._read(conn)

    def _send(self, **obj):
        try:
            self.conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        except OSError:
            pass

    def _read(self, conn):
        try:
            for raw in conn.makefile("r", encoding="utf-8"):
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if "line" in msg:
                    self.say(PREFIX + msg["line"])
                elif "problem" in msg:
                    self.say(PREFIX + "Problem: " + msg["problem"])
                elif "state" in msg:
                    self.state = msg["state"]
                    self._tell(msg["state"])
        except OSError:
            pass
        with self.lock:
            if self.conn is not conn:
                return            # stop() has already moved on
            self.conn = self.proc = None
            self.state = "off"
            if time.monotonic() - self.since > STEADY_FOR:
                self.restarted = False   # it ran a good while: one more restart is allowed
            wanted, restarted = self.wanted, self.restarted
        if not wanted:
            return
        if not restarted:
            self.restarted = True
            self.say(PREFIX + "the follower stopped on its own; starting it again.")
            self.start(self.settings)
        else:
            self.wanted = False
            self.say(PREFIX + "Problem: the follower stopped again, so Multiroom is off until the next build.")
