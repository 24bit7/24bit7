"""
The follower as 24bit7's child process (Multiroom, stage two, 9 Nov 2026).

  24bit7.exe --follow --port N        the packed app: gui.pyw hands --follow here before Tk is loaded
  py -m multiroom.service --port N    in the repo

The app listens on 127.0.0.1 and the child connects to the port it was given. JSON, one object a line, each way:
  app -> child   {"cmd": "start", "leader": .., "follower": .., "server": .., "sonos": .., "device": ..,
                  "start": 90, "resume": 95, "dac": 1660, "env": "...\\.env"}
                 {"cmd": "stop"}   {"cmd": "quit"}
  child -> app   {"line": "..."}   {"state": "following" | "idle"}   {"problem": "..."}

Nothing here prints: a windowed exe has no console. The child runs its own process because at 192 kHz the DAC asks
for samples every five milliseconds, which a Tk window with a build running can't promise. When the socket closes,
whichever way, the child stops the Speakers and exits, so it never outlives the app.
"""

import argparse
import json
import socket
import threading

from . import follower


class Service:
    """One connection's worth of commands. build is follower.build, or a stand-in for the tests."""

    def __init__(self, conn, build=follower.build):
        self.conn, self.build = conn, build
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.follower = None   # the running Follower, for nudge

    def send(self, **obj):
        with self.lock:
            try:
                self.conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
            except OSError:
                pass

    def run(self):
        """Reads commands until the socket closes or the app says quit; the follower is stopped on the way out."""
        reader = self.conn.makefile("r", encoding="utf-8")
        try:
            for raw in reader:
                try:
                    cmd = json.loads(raw)
                except ValueError:
                    continue
                what = cmd.get("cmd")
                if what == "start":
                    self.start(cmd)
                elif what == "stop":
                    self.stop()
                elif what == "nudge":
                    f = self.follower
                    if f is not None:
                        f.nudge(float(cmd.get("ms", 0)))
                elif what == "quit":
                    break
        finally:
            self.stop()
            try:
                self.conn.close()
            except OSError:
                pass

    def start(self, cmd):
        if self.thread is not None and self.thread.is_alive():
            return   # already following
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._follow, args=(cmd,), daemon=True, name="follower")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        t = self.thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=5)

    def _follow(self, cmd):
        say = lambda line: self.send(line=line)   # noqa: E731
        try:
            clock, f, description = self.build(
                cmd.get("leader", "Sonos"), cmd.get("follower", "Speakers"), cmd.get("server", "Multiroom"),
                cmd.get("sonos") or None, cmd.get("device") or None, float(cmd.get("start", 90.0)),
                float(cmd.get("resume", 95.0)), int(cmd.get("dac", 1660)), cmd.get("env", ".env"), say=say)
        except follower.SetupError as e:
            self.send(problem=str(e))
            self.send(state="idle")
            return
        except Exception as e:   # a surprise: the app gets the reason rather than a silent child
            self.send(problem=f"The follower couldn't start ({e}).")
            self.send(state="idle")
            return
        self.send(state="following")
        self.send(line=description)
        self.follower = f
        clock.start()
        try:
            f.run(self.stop_event)
        except Exception as e:
            self.send(problem=f"The follower stopped ({e}).")
        finally:
            self.follower = None
            clock.stop()
            self.send(state="idle")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="24bit7 --follow", description="The Multiroom follower, as 24bit7's child.")
    ap.add_argument("--follow", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--port", type=int, required=True, help="the port 24bit7 listens on")
    a = ap.parse_args(argv)
    conn = socket.create_connection(("127.0.0.1", a.port), timeout=10)
    conn.settimeout(None)
    Service(conn).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
