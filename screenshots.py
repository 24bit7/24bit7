"""
24bit7 - screenshots for the user manual.

Opens 24bit7 in a demo mode, steps through each tab and Settings page, and saves
a PNG of each into docs/images. Demo mode never contacts JRiver and never touches
your .env or 24bit7.db: settings are read from a temporary copy with every key
swapped for a dummy, and Discover, devices and playlists come from a temporary
database filled with made-up data around The Beatles. Both are deleted at the end.

Use:
  py screenshots.py                     every screenshot
  py screenshots.py play discover       just those
  py screenshots.py --changed           only shots whose code has changed since
                                        their image was last committed (or is uncommitted)
  py screenshots.py --list              the names, and the files each depends on

An image is only rewritten when the picture has actually changed, so git only
shows real changes. Long Settings pages are scrolled and stitched into one image.
The shots take whatever theme 24bit7 is set to; switch to Light first for a light manual.
Windows only (uses Pillow's ImageGrab). Leave the mouse and keyboard alone while it runs.
"""

import argparse
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "docs", "images")
COMMON = ["tabs.py"]   # every shot changes when the tab and button drawing changes

# name, path of tab names to click through, files it depends on, optional before-shot action
SHOTS = [
    ("play", ["Play", "Now Playing"], ["gui.pyw", "mix_gui.py"], "more_closed"),
    ("play_more_options", ["Play", "Now Playing"], ["gui.pyw", "mix_gui.py"], "more_open"),
    ("play_search", ["Play", "Search"], ["gui.pyw"], "more_closed"),
    ("console_tabs", ["Play", "Now Playing"], ["gui.pyw", "buildlog.py"], "tabs_kitchen"),
    ("console_log", ["Play", "Now Playing"], ["gui.pyw", "buildlog.py"], "tabs_log"),
    ("discover", ["Discover"], ["discover_gui.py"], None),
    ("settings_sources_similar_artists", ["Settings", "Sources", "Similar Artists"], ["settings_gui.py"], None),
    ("settings_sources_similar_tracks", ["Settings", "Sources", "Similar Tracks"], ["settings_gui.py"], None),
    ("settings_sources_top_tracks", ["Settings", "Sources", "Artist's Top Tracks"], ["settings_gui.py"], None),
    ("settings_playlist_similar_artists", ["Settings", "Playlist", "Similar Artists"], ["settings_gui.py"], None),
    ("settings_playlist_similar_tracks", ["Settings", "Playlist", "Similar Tracks"], ["settings_gui.py"], None),
    ("settings_playlist_top_tracks", ["Settings", "Playlist", "Artist's Top Tracks"], ["settings_gui.py"], None),
    ("settings_playlist_ai_playlist", ["Settings", "Playlist", "AI Playlist"], ["settings_gui.py"], None),
    ("settings_filters", ["Settings", "Filters"], ["settings_gui.py", "filters.py"], None),
    ("settings_search_sites", ["Settings", "Search"], ["settings_gui.py"], None),
    ("settings_keys", ["Settings", "Keys"], ["settings_gui.py"], None),
    ("settings_voice_commands", ["Settings", "Voice Commands"], ["settings_gui.py", "voice.py"], None),
    ("settings_jriver_playlists", ["Settings", "JRiver Playlists"], ["settings_gui.py", "saved_playlists.py"], None),
    ("settings_other", ["Settings", "Other"], ["settings_gui.py", "hotkeys.py", "tray.py"], None),
    ("settings_about", ["Settings", "About"], ["settings_gui.py"], None),
]

# --- the demo data ----------------------------------------------------------

DEMO_ZONES = [("10001", "Speakers"), ("10002", "Kitchen")]
DEMO_PLAYING = {"Artist": "The Beatles", "Album": "Abbey Road", "Name": "Here Comes The Sun",
                "PlayingNowPosition": "4", "PlayingNowTracks": "17", "FileKey": "1001", "ZoneID": "10001"}
DEMO_KEYS = {"LASTFM_API_KEY": "demo" * 8, "LISTENBRAINZ_TOKEN": "demo" * 9, "DISCOGS_TOKEN": "demo" * 10,
             "ANTHROPIC_API_KEY": "demo" * 12, "JRIVER_USER": "demo", "JRIVER_PASS": "demo" * 3,
             "VOICE_KEY": "demo" * 8}
DEMO_ENV = {"HIDDEN_ZONES": "", "DEFAULT_ZONE": "Speakers", "FOLLOW_ACTIVE_ZONE": "0", "VOICE_ENABLED": "1",
            "CONSOLE_MODE": "simple", "CONSOLE_TABS": "0", "HOTKEY_SWITCH_ZONES": "Ctrl+Alt+5"}
# JRiver Playlists: one playlist blended and one with Non-stop, so the shot shows both
DEMO_SAVED_ROWS = {"201": {"blend": "tracks"}, "202": {"nonstop": "artists"}}
DEMO_DEVICES = [("demo-kitchen", "Kitchen Echo", "Kitchen", 0, "2026-10-04 10:41"),
                ("demo-lounge", "Lounge Dot", "Speakers", 0, "2026-10-04 09:15")]
DEMO_PLAYLISTS = [
    {"ID": "201", "Name": "Sunday Morning", "Folder": "", "Type": "Playlist"},
    {"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"},
    {"ID": "203", "Name": "60s Smartlist", "Folder": "Smartlists", "Type": "Smartlist"},
    {"ID": "204", "Name": "Random Album", "Folder": "Smartlists", "Type": "Smartlist"},
    {"ID": "205", "Name": "Kitchen Disco", "Folder": "Mixes", "Type": "Playlist"},
]
# Discover: one Similar Artists session from Here Comes The Sun. (artist, track, sources, found)
DEMO_DISCOVERIES = [
    ("The Kinks", "Waterloo Sunset", "Last.fm, Deezer", True),
    ("The Hollies", "Bus Stop", "Last.fm, ListenBrainz", True),
    ("The Byrds", "Turn! Turn! Turn!", "Last.fm, Deezer, YouTube", True),
    ("Badfinger", "Baby Blue", "Last.fm, ListenBrainz", True),
    ("The Kinks", "Days", "Last.fm, Deezer", True),
    ("The Zombies", "Time Of The Season", "Last.fm, Deezer", False),
    ("Harry Nilsson", "Everybody's Talkin'", "ListenBrainz, YouTube", False),
    ("The Move", "Flowers In The Rain", "Last.fm", False),
    ("The Hollies", "Carrie Anne", "Last.fm, ListenBrainz", False),
    ("Badfinger", "Day After Day", "Last.fm, Deezer", False),
    ("Big Star", "Thirteen", "ListenBrainz", False),
    ("The Left Banke", "Walk Away Renee", "Last.fm, ListenBrainz", False),
    ("The Searchers", "Needles And Pins", "Last.fm, Deezer", False),
    ("Gerry & The Pacemakers", "Ferry Cross The Mersey", "Deezer", False),
    ("Electric Light Orchestra", "Mr. Blue Sky", "Last.fm, YouTube", False),
    ("The Turtles", "Happy Together", "Last.fm, Deezer, YouTube", False),
]
# Fixed times, so Discover and the device list come out the same on every run
DEMO_SESSION_TIME = "2026-10-04 10:30"
DEMO_CONSOLE = [
    "21:14  Similar Tracks: The Beatles - Here Comes The Sun  (target 30, at most 2 per artist)",
    "  Last.fm: 50 similar tracks",
    "  ListenBrainz: 40 similar tracks (from cache)",
    "  YouTube: 25 similar tracks",
    "    In library: The Kinks - Waterloo Sunset  (Last.fm, ListenBrainz)",
    "    In library: The Hollies - Bus Stop  (Last.fm, YouTube)",
    "    Not in library: The Zombies - Time Of The Season",
    "    In library: George Harrison - What Is Life  (Last.fm, ListenBrainz, YouTube)",
    "    In library: The Byrds - Mr. Tambourine Man  (ListenBrainz)",
    "    Not in library: Harry Nilsson - Everybody's Talkin'",
    "    ...",
    "  Suggested 96, checked 96, in library 34.",
    "  AI Moderator (Balanced): checking 34 tracks against the seed...",
    "    Removed The Who - Won't Get Fooled Again: louder and harder than the seed.",
    "  AI Moderator: 1 removed.",
    "  Sending 30 tracks...",
    "  Queued in Speakers after the current track.",
    "Done: 30 tracks queued in Speakers, 62 not in library, 14 s.",
]

# The console's Log: kept builds, with fixed times so the shots repeat. (at, tab, from, zone, zone ID, kind,
# sources, queued, misses, moderator, problems, notes, chain ID, chain position, text); chain IDs are row numbers.
KITCHEN_TEXT = """21:20  Voice, Kitchen Echo: tracks like Here Comes The Sun by The Beatles, to Kitchen
Similar Tracks: The Beatles - Here Comes The Sun  (target 30, at most 2 per artist)
  Last.fm: 50 similar tracks
  Problem: Deezer didn't answer for similar tracks (timed out).
  ListenBrainz: 40 similar tracks (from cache)
  YouTube: 25 similar tracks
    In library: The Kinks - Waterloo Sunset  (Last.fm, ListenBrainz)
    Not in library: The Zombies - Time Of The Season
    ...
  Suggested 96, checked 96, in library 34.
  AI Moderator (Balanced): checking 34 tracks against the seed...
    Removed The Who - Won't Get Fooled Again: louder and harder than the seed.
    Removed Queen - We Will Rock You: stadium energy, breaks the mood.
  AI Moderator: 2 removed.
  Note: Drift is off, so the playlist stops at 30 tracks. Settings > Playlist > Drift
  Sending 30 tracks...
  Queued in Kitchen after the current track.
Done: 30 tracks queued in Kitchen, 62 not in library, 14 s."""
DEMO_BUILDS = [
    ("2026-10-04 19:12:40", "main", "Main Window", "Speakers", "10001", "AI Playlist", "AI", 22, 0, "", 0, 1,
     None, None, "19:12  AI Playlist: rainy Sunday morning  (target 25 tracks)\nDone: 22 tracks queued in Speakers, "
     "0 not in library, 11 s."),
    ("2026-10-04 20:40:12", "main", "Shortcut", "Speakers", "10001", "Similar Tracks", "Last.fm, ListenBrainz", 30,
     47, "Relaxed, 0 removed", 0, 0, None, None, "20:40  Shortcut: Similar Tracks\nDone: 30 tracks queued in "
     "Speakers, 47 not in library, 12 s."),
    ("2026-10-04 20:51:03", "demo-lounge", "Lounge Dot", "", "", "Album", "", None, None, "", 1, 0, None, None,
     "20:51  Voice, Lounge Dot: album Abbey Raod\n  Problem: Alexa said \"I couldn't find an album called "
     "Abbey Raod.\""),
    ("2026-10-04 21:14:22", "main", "Main Window", "Speakers", "10001", "Similar Tracks",
     "Last.fm, ListenBrainz, YouTube", 30, 62, "Balanced, 1 removed", 0, 0, None, None, "\n".join(DEMO_CONSOLE)),
    ("2026-10-04 21:20:05", "demo-kitchen", "Kitchen Echo", "Kitchen", "10002", "Similar Tracks",
     "Last.fm, ListenBrainz, YouTube", 30, 62, "Balanced, 2 removed", 1, 1, 5, 1, KITCHEN_TEXT),
    ("2026-10-04 21:31:47", "demo-kitchen", "Non-stop", "Kitchen", "10002", "Similar Tracks",
     "Last.fm, ListenBrainz, YouTube", 30, 55, "Balanced, 3 removed", 0, 0, 5, 2,
     "21:31  Non-stop: Kitchen reached its last track\nDone: 30 tracks queued in Kitchen, 55 not in library, 12 s."),
    ("2026-10-04 21:42:09", "demo-kitchen", "Non-stop", "Kitchen", "10002", "Similar Tracks",
     "Last.fm, ListenBrainz, YouTube", 28, 41, "Balanced, 1 removed", 0, 0, 5, 3,
     "21:42  Non-stop: Kitchen reached its last track\nDone: 28 tracks queued in Kitchen, 41 not in library, 13 s."),
]


# --- picking which shots to take -------------------------------------------

def git(*args):
    r = subprocess.run(["git"] + list(args), cwd=HERE, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def needs_retake(name, deps):
    """True if the image is missing, uncommitted, or its code has changed since it was committed."""
    image = os.path.join("docs", "images", name + ".png")
    if not os.path.exists(os.path.join(HERE, image)):
        return True
    image_time = git("log", "-1", "--format=%ct", "--", image)
    if not image_time:
        return True   # never committed
    files = deps + COMMON
    if git("status", "--porcelain", "--", *files):
        return True   # code changed and not committed yet
    code_time = git("log", "-1", "--format=%ct", "--", *files)
    return bool(code_time) and int(code_time) > int(image_time)


def choose(args):
    names = [s[0] for s in SHOTS]
    if args.list:
        for name, path, deps, _ in SHOTS:
            print(f"  {name:36} {' > '.join(path):45} {', '.join(deps)}")
        sys.exit(0)
    if args.names:
        unknown = [n for n in args.names if n not in names]
        if unknown:
            print("Unknown name(s): " + ", ".join(unknown) + ". Use --list to see them.")
            sys.exit(1)
        return [s for s in SHOTS if s[0] in args.names]
    if args.changed:
        if not git("rev-parse", "--is-inside-work-tree"):
            print("--changed needs the 24bit7 git folder.")
            sys.exit(1)
        return [s for s in SHOTS if needs_retake(s[0], s[2])]
    return list(SHOTS)


# --- demo mode -------------------------------------------------------------

def load_gui():
    """Imports gui.pyw as a module, without running its main()."""
    sys.path.insert(0, HERE)
    os.chdir(HERE)
    loader = importlib.machinery.SourceFileLoader("gui", os.path.join(HERE, "gui.pyw"))
    spec = importlib.util.spec_from_loader("gui", loader)
    gui = importlib.util.module_from_spec(spec)
    loader.exec_module(gui)
    return gui


def demo_env(src, dst):
    """A copy of .env with every key and password swapped for a dummy."""
    lines, seen = [], set()
    replace = dict(DEMO_KEYS, **DEMO_ENV)
    if os.path.exists(src):
        with open(src, encoding="utf-8") as f:
            for line in f.read().splitlines():
                key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
                if key in replace:
                    line = f"{key}={replace[key]}"
                    seen.add(key)
                lines.append(line)
    lines += [f"{k}={v}" for k, v in replace.items() if k not in seen]
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def start_demo(gui, temp):
    engine, settings_gui, voice, saved_playlists = gui.engine, sys.modules["settings_gui"], gui.voice, \
        sys.modules["saved_playlists"]

    # Settings from the dummy copy; nothing is ever written to the real .env
    env_path = os.path.join(temp, ".env")
    demo_env(engine.ENV_FILE, env_path)
    engine.ENV_FILE = settings_gui.ENV_FILE = env_path

    # JRiver: a dead address, so anything not faked below fails at once instead of reading your library
    original_load = engine.load_settings

    def load_settings():
        original_load()
        engine.JRIVER_BASE = "http://127.0.0.1:9/MCWS/v1"
    engine.load_settings = load_settings
    engine.load_settings()
    engine._env_mtime = os.path.getmtime(env_path)
    engine._read_zones = lambda: (list(DEMO_ZONES), DEMO_ZONES[0][0])
    engine.get_playing_info = lambda zone=None: dict(DEMO_PLAYING)
    saved_playlists.scan = lambda: [dict(p) for p in DEMO_PLAYLISTS]
    voice._status = f"Listening on 127.0.0.1:{engine.VOICE_PORT}"   # shown as running; nothing is started

    # A temporary database with the demo sessions, discoveries and devices
    if engine._db is not None:
        engine._db.close()
    engine._db = None
    engine.DB_FILE = os.path.join(temp, "24bit7.db")
    engine.CSV_FILE = os.path.join(temp, "none.csv")   # never import your old discoveries log
    con = engine.db()
    cur = con.execute("INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued) "
                      "VALUES (?,?,?,?,?,?,?)", (DEMO_SESSION_TIME, "similar", "The Beatles", "Here Comes The Sun",
                                                 "Abbey Road", "Last.fm, ListenBrainz, Deezer, YouTube", 30))
    for artist, track, sources, found in DEMO_DISCOVERIES:
        con.execute("INSERT INTO discoveries (session_id, artist, track, sources, found) VALUES (?,?,?,?,?)",
                    (cur.lastrowid, artist, track, sources, 1 if found else 0))
    voice._devices_table()
    for device_id, name, zone, own, heard in DEMO_DEVICES:
        con.execute("INSERT INTO voice_devices (device_id, name, zone, last_heard, own_settings) VALUES (?,?,?,?,?)",
                    (device_id, name, zone, heard, own))
    con.commit()
    saved_playlists.set_main_settings({"rows": {pid: dict(row) for pid, row in DEMO_SAVED_ROWS.items()}})
    try:   # the console's Log (1.11.0 and later)
        import buildlog
        buildlog._table(con)
        cols = ["at", "tab", "from_label", "zone", "zone_id", "kind", "sources", "queued", "misses", "moderator",
                "problems", "notes", "chain_id", "chain_pos", "text"]
        for values in DEMO_BUILDS:
            buildlog._insert(con, dict(zip(cols, values)))
    except ImportError:
        pass


def build_window(gui):
    """The main window as gui.main() builds it, minus voice, shortcuts, tray and the library read."""
    tk, engine, PALETTE = gui.tk, gui.engine, gui.PALETTE
    gui._enable_dpi_awareness()
    root = tk.Tk()
    gui._set_window_icon(root)
    gui.apply_theme(root, engine.THEME)
    root.title(f"24bit7  v{engine.VERSION}")
    scale = root.winfo_fpixels("1i") / 96.0
    w = min(int(1180 * scale), root.winfo_screenwidth() - 80)
    h = min(int(820 * scale), root.winfo_screenheight() - 120)
    root.geometry(f"{w}x{h}+40+40")
    root.attributes("-topmost", True)

    nb = gui.TabbedPane(root, font=("Segoe UI", 11, "bold"), pad=(20, 8))
    nb.pack(fill="both", expand=True, pady=(6, 0))
    play = gui.PlayTab(nb, root)
    discover = gui.DiscoverTab(nb)
    settings = gui.SettingsTab(nb)
    play.settings = settings
    nb.add(play, text="Play")
    nb.add(discover, text="Discover")
    nb.add(settings, text="Settings")

    donate = tk.Label(root, text="Buy me a coffee \u2615", font=("Segoe UI", 9, "underline"), fg=PALETTE["link"])

    def place_donate(event=None):
        if event is not None and event.widget is not root:
            return
        if root.winfo_width() - nb.tabs_width() - donate.winfo_reqwidth() - 40 > 0:
            donate.place(relx=1.0, x=-16, y=nb.winfo_y() + nb.strip_height() // 2, anchor="e")
    root.bind("<Configure>", place_donate, add="+")

    def on_tab_changed(_e):
        if nb.select() == str(discover):
            discover.ensure_loaded()
        elif nb.select() == str(play):
            play.sync_moderator()
    nb.bind("<<NotebookTabChanged>>", on_tab_changed)

    # The console: no greeting, just the demo build
    play._greeting_active = False
    play._stamp_next = False
    play._clear_log()
    for line in DEMO_CONSOLE:
        play._append_log(line)
    return root, nb, play


# --- capture ---------------------------------------------------------------

def settle(root, seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.05)


def panes_in(widget, TabbedPane):
    """Every TabbedPane inside widget, outermost first."""
    found, todo = [], [widget]
    while todo:
        w = todo.pop(0)
        if isinstance(w, TabbedPane):
            found.append(w)
        todo.extend(w.winfo_children())
    return found


def go_to(root, path, TabbedPane):
    """Clicks through tab names, each looked for inside the page the last one opened."""
    where = root
    for text in path:
        for pane in panes_in(where, TabbedPane):
            texts = [t.cget("text") for t in pane._tabs]
            if text in texts:
                page = pane._pages[texts.index(text)]
                pane.select(page)
                settle(root, 0.3)
                where = page
                break
        else:
            raise RuntimeError(f"couldn't find a tab called {text!r}")
    return where


def grab(root):
    from PIL import ImageGrab
    root.lift()
    settle(root, 0.2)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    return ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()))   # the window sits on the main screen


def scroll_canvas(page):
    """The page's scrolling canvas, if its content is taller than the window."""
    best, todo = None, [page]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if w.winfo_class() == "Canvas" and w.winfo_ismapped() and str(w.cget("yscrollcommand")):
            box = w.bbox("all")
            if box and box[3] > w.winfo_height() + 2 and (best is None or w.winfo_height() > best.winfo_height()):
                best = w
    return best


def capture(root, page):
    """The window, with a long page scrolled through and stitched into one tall image."""
    from PIL import Image
    first = grab(root)
    canvas = scroll_canvas(page)
    if canvas is None:
        return first
    width = first.width
    top = canvas.winfo_rooty() - root.winfo_rooty()
    view = canvas.winfo_height()
    total = canvas.bbox("all")[3]
    pieces, y = [], 0
    while y < total:
        canvas.yview_moveto(y / total)
        settle(root, 0.25)
        shown = int(canvas.canvasy(0))
        shot = grab(root)
        end = min(shown + view, total)
        pieces.append(shot.crop((0, top + (y - shown), width, top + (end - shown))))
        if end <= y:
            break
        y = end
    canvas.yview_moveto(0)
    head = first.crop((0, 0, width, top))
    foot = first.crop((0, top + view, width, first.height))
    out = Image.new("RGB", (width, head.height + sum(p.height for p in pieces) + foot.height))
    at = 0
    for part in [head] + pieces + [foot]:
        out.paste(part, (0, at))
        at += part.height
    # The scrollbar shows a different position in every piece, so it's painted out
    for bar in canvas.master.winfo_children():
        if bar.winfo_class() == "TScrollbar" and bar.winfo_ismapped():
            x = bar.winfo_rootx() - root.winfo_rootx()
            r, g, b = (v // 256 for v in root.winfo_rgb(canvas.cget("bg")))
            out.paste((r, g, b), (x, top, x + bar.winfo_width(), top + sum(p.height for p in pieces)))
    return out


def save_if_changed(image, name):
    """Writes the PNG only if the picture differs from the one already there. Returns True if written."""
    from PIL import Image, ImageChops
    path = os.path.join(OUT_DIR, name + ".png")
    image = image.convert("RGB")
    if os.path.exists(path):
        with Image.open(path) as old:
            old = old.convert("RGB")
            if old.size == image.size and ImageChops.difference(old, image).getbbox() is None:
                return False
    image.save(path, optimize=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="Screenshots for the 24bit7 manual, from demo data.")
    parser.add_argument("names", nargs="*", help="shot names to take (default: all)")
    parser.add_argument("--changed", action="store_true", help="only shots whose code has changed")
    parser.add_argument("--list", action="store_true", help="list the shot names and stop")
    args = parser.parse_args()
    if sys.platform != "win32":
        print("Screenshots are taken on Windows only.")
        sys.exit(1)
    try:
        import PIL.ImageGrab  # noqa: F401
    except ImportError:
        print("Needs Pillow: py -m pip install Pillow")
        sys.exit(1)

    shots = choose(args)
    if not shots:
        print("Nothing to retake: every screenshot is up to date with its code.")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Taking {len(shots)} screenshot(s). Leave the mouse and keyboard alone until it says done.")

    temp = tempfile.mkdtemp(prefix="24bit7_demo_")
    gui = load_gui()
    start_demo(gui, temp)
    root, nb, play = build_window(gui)
    written, same = [], []
    try:
        settle(root, 1.5)   # Now Playing's first read happens just after the window appears
        for name, path, _deps, action in shots:
            page = go_to(root, path, gui.TabbedPane)
            tabs = hasattr(play, "_set_tabs_open")   # the console's tabs (1.11.0 and later)
            if tabs and play.tabs_open and action not in ("tabs_kitchen", "tabs_log"):
                play._set_tabs_open(False, save=False)
            if action == "more_open":
                play._show_more(True, save=False)
            elif action in ("more_closed", "tabs_kitchen", "tabs_log"):
                play._show_more(False, save=False)
            if tabs and action in ("tabs_kitchen", "tabs_log"):
                play._set_tabs_open(True, save=False)
                if action == "tabs_log":
                    play._select_view("log")
                else:   # the Kitchen Echo build that started its Non-stop chain, opened from the Log
                    import buildlog
                    play._load_build(next(r for r in buildlog.recent("demo-kitchen") if r["chain_pos"] == 1))
            settle(root, 1.0 if name == "settings_jriver_playlists" else 0.5)
            (written if save_if_changed(capture(root, page), name) else same).append(name)
            print(f"  {name}: {'saved' if name in written else 'unchanged'}")
    finally:
        root.destroy()
        if gui.engine._db is not None:
            gui.engine._db.close()
        shutil.rmtree(temp, ignore_errors=True)

    print(f"\nDone. {len(written)} saved, {len(same)} unchanged, in docs\\images.")
    if written:
        print("Commit them with:  git add docs/images; git commit -m \"Manual screenshots\"")


if __name__ == "__main__":
    main()
