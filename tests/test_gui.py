"""
The interface, run for real on a virtual screen: every tab and Settings page
opened, Play tab builds through the worker thread into the console and its Log,
and a sweep that changes every setting control, closes Settings, opens it again
and checks each control kept its value.

Needs a display: run with xvfb-run on Linux. Skipped when no display is found.
"""

import difflib
import json
import os
import time
import tkinter as tk
from tkinter import ttk

import pytest

from conftest import load_gui

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY") and os.name != "nt", reason="needs a display")

KITCHEN = "amzn1.ask.device.KITCHEN"
LOUNGE = "amzn1.ask.device.LOUNGE"


@pytest.fixture
def ui(app, monkeypatch):
    """The main window's tabs, built the way gui.main() builds them, without its mainloop."""
    from tkinter import messagebox, filedialog, simpledialog
    answers = []
    for name in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(messagebox, name, lambda *a, _n=name, **k: answers.append((_n, a)))
    for name in ("askyesno", "askokcancel", "askyesnocancel"):
        monkeypatch.setattr(messagebox, name, lambda *a, _n=name, **k: answers.append((_n, a)) or False)
    monkeypatch.setattr(filedialog, "askopenfilename", lambda *a, **k: "")
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: None)
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)

    import tray   # pystray needs a desktop tray; on Linux test runs there isn't one
    monkeypatch.setattr(tray, "available", lambda: False)
    monkeypatch.setattr(tray, "start", lambda *a, **k: False)
    v = app.voice
    for device, name, zone in ((KITCHEN, "Kitchen Echo", "Kitchen"), (LOUNGE, "Lounge Dot", "Speakers")):
        v._hear_device(device)
        v.update_device(device, name=name, zone=zone)
    v.set_own_settings(KITCHEN, True)

    gui = load_gui(app.folder)
    errors = []
    root = tk.Tk()
    root.report_callback_exception = lambda *exc: errors.append(exc)
    gui.apply_theme(root, app.engine.THEME)
    root.geometry("1400x900")
    nb = gui.TabbedPane(root, font=("Segoe UI", 11, "bold"), pad=(20, 8))
    nb.pack(fill="both", expand=True)
    play = gui.PlayTab(nb, root)
    discover = gui.DiscoverTab(nb)
    settings = gui.SettingsTab(nb)
    play.settings = settings
    nb.add(play, text="Play")
    nb.add(discover, text="Discover")
    nb.add(settings, text="Settings")
    app.library.load()
    v.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)),
             lambda: play.running or not play.voice_jobs.empty())
    v.restart()
    import nonstop
    nonstop.attach(lambda job, heading, origin=None: play.voice_jobs.put((job, heading, origin)))

    # Tk calls from the build's worker thread need a running mainloop; here they are
    # handed to the test's own event pump instead, which plays the mainloop's part
    import queue
    import threading
    calls = queue.Queue()
    main_thread = threading.current_thread()

    def threadsafe(widget):
        original = widget.after

        def after(ms, func=None, *args):
            if threading.current_thread() is not main_thread and func is not None:
                calls.put((func, args))
                return "after#thread"
            return original(ms, func, *args)
        widget.after = after
    for w in (root, play, settings, discover):
        threadsafe(w)

    def pump(seconds=0.3, until=None, timeout=30):
        end = time.time() + (timeout if until else seconds)
        while time.time() < end:
            while not calls.empty():
                func, args = calls.get()
                func(*args)
            root.update()
            if until and until():
                break
            time.sleep(0.01)
        root.update()

    def wait_idle(timeout=60):
        pump(0.3)
        pump(until=lambda: not play.running and play.voice_jobs.empty(), timeout=timeout)
        pump(0.3)

    ns = type("UI", (), {})()
    ns.gui, ns.root, ns.nb, ns.play, ns.discover, ns.settings = gui, root, nb, play, discover, settings
    ns.errors, ns.answers, ns.pump, ns.wait_idle = errors, answers, pump, wait_idle
    pump(0.5)
    yield ns
    try:
        root.destroy()
    except tk.TclError:
        pass


def console(ui):
    return ui.play.log.get("1.0", "end-1c")


def all_panes(widget):
    out = []
    if hasattr(widget, "select") and hasattr(widget, "add") and hasattr(widget, "remove"):
        out.append(widget)
    for child in widget.winfo_children():
        out += all_panes(child)
    return out


def visit_every_page(ui, pane=None, depth=0):
    """Selects every tab of every TabbedPane, depth first, so lazily built pages get built."""
    pane = pane or ui.nb
    pages = list(getattr(pane, "_pages", None) or getattr(pane, "pages", None) or [])
    if not pages:
        pages = [c for c in pane.winfo_children() if isinstance(c, tk.Frame)]
    for i, page in enumerate(pages):
        try:
            page._page_title = pane._tabs[i].cget("text")
        except Exception:
            pass
        try:
            pane.select(page)
        except Exception:
            continue
        ui.pump(0.25)
        for inner in all_panes(page):
            if inner is not pane and depth < 4:
                visit_every_page(ui, inner, depth + 1)


# --- smoke ---------------------------------------------------------------------------

def test_every_page_opens_without_errors(app, ui):
    visit_every_page(ui)
    ui.pump(1.0)
    assert not ui.errors, ui.errors[0]


def test_play_tab_similar_artists_button(app, ui):
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    ui.play.on_similar()
    ui.wait_idle()
    text = console(ui)
    assert "Done:" in text, text
    import buildlog
    rows = buildlog.recent()
    assert rows and rows[0]["kind"] == "Similar Artists" and rows[0]["from_label"] == "Main Window"
    assert rows[0]["queued"] == len(j.zone("Speakers").playlist) - 1, rows[0]   # the playing track stays first
    assert not ui.errors, ui.errors


def test_voice_build_gets_device_tab_and_log_row(app, ui):
    import urllib.request
    import buildlog
    body = json.dumps({"intent": "music_like", "value": "queen", "device": KITCHEN}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{app.engine.VOICE_PORT}/command", data=body, method="POST",
                                 headers={"X-24bit7-Key": app.engine.VOICE_KEY, "Content-Type": "application/json"})
    reply = json.loads(urllib.request.urlopen(req).read())
    assert reply["status"] == "started", reply
    ui.wait_idle()
    rows = buildlog.recent(KITCHEN)
    assert rows and rows[0]["from_label"] == "Kitchen Echo" and rows[0]["zone"] == "Kitchen", rows
    assert any(t == KITCHEN for t, _ in buildlog.tabs())
    assert not ui.errors, ui.errors


def test_nonstop_top_up_numbers_the_chain(app, ui):
    import buildlog
    import nonstop
    app.set_env(NONSTOP_TRACKS="1")
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    ui.play.on_similar_tracks()
    ui.wait_idle()
    z = j.zone("Speakers")
    first_len = len(z.playlist)
    z.pos = first_len - 1                      # the last track starts
    nonstop._check_zones()
    ui.wait_idle()
    assert len(z.playlist) > first_len, console(ui)
    rows = buildlog.recent()
    assert rows[0]["from_label"] == "Non-stop" and rows[0]["chain_pos"] == 2, rows[:2]
    assert rows[1]["chain_pos"] == 1
    assert buildlog.playlist_type(rows[0]) == "Similar Tracks · Non-stop 002"


def test_log_keeps_last_50_per_source(app, ui):
    import buildlog
    app.engine.db()
    for n in range(55):
        buildlog.record_job(None, f"Similar Artists: build {n}\nDone: 1 track queued in Speakers, 0 s.")
    buildlog.record_job({"from": "voice", "device": KITCHEN}, "Similar Tracks: x\nDone: 1 track queued.")
    assert len(buildlog.recent("main")) == 50
    assert len(buildlog.recent(KITCHEN)) == 1


def test_simple_mode_hides_debug(app, ui):
    if ui.play.console_mode != "simple":
        ui.play._toggle_console_mode()   # the Simple / Advanced switch in the console strip
    from dotenv import dotenv_values
    assert dotenv_values(app.engine.ENV_FILE).get("CONSOLE_MODE") == "simple"
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    ui.pump(until=lambda: ui.play.last_playing, timeout=10)
    ui.play.on_similar()
    ui.wait_idle()
    log = ui.play.log
    assert "[debug]" in console(ui) and str(log.tag_cget("debug", "elide")) in ("1", "true"), \
        "debug lines are kept but hidden in Simple"
    shown = [log.get(f"{r[0]}", f"{r[1]}") for r in zip(*[iter(log.tag_ranges("debug"))] * 2)]
    assert shown and all("[debug]" in x for x in shown)


def test_play_tab_switches_write_settings(app, ui):
    """More Options' Drift and Non-stop are a second door onto Settings > Playlist."""
    p = ui.play
    if not hasattr(p, "nonstop_var"):
        pytest.skip("Play tab switches not found by name")
    p.nonstop_cb.set("Wander")
    p.nonstop_cb.event_generate("<<ComboboxSelected>>")
    ui.pump(0.5)
    from dotenv import dotenv_values
    env = dotenv_values(app.engine.ENV_FILE)
    assert all(env.get(f"NONSTOP_{g}") == "1" for g in ("ARTISTS", "TRACKS", "TOP", "VIBE")), env


# --- JRiver Playlists page: the global rows (the 1.11.1 fix) ---------------------------

def find_saved_global_combos(widget):
    """The global rows' dropdowns on a JRiver Playlists page (in its All playlists box)."""
    out = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Combobox):
            out.append(child)
        out += find_saved_global_combos(child)
    return out


@pytest.mark.parametrize("where", ["main", "device"])
def test_saved_playlists_global_rows_stick_after_rescan(app, ui, where):
    s = ui.settings
    if where == "device":
        app.voice.set_device_page(KITCHEN, "saved", app.saved_playlists.main_settings())
        s._layout_device_pane("saved")
        info = s._panes["saved"]
        page = info["devices"][KITCHEN]
        info["pane"].select(page["outer"])
        s._fill_device_page("saved", KITCHEN)
        ui.pump(1.0)
        holder = page["inner"]
    else:
        s._layout_device_pane("saved")
        holder = s._panes["saved"]["outer"]
        ui.pump(1.0)
    ui.pump(0.6)   # the rescan runs 200 ms after the page opens
    combos = [c for c in find_saved_global_combos(holder) if c.winfo_ismapped() or True]
    skip_global = combos[-1]   # the last of the global rows' four dropdowns... found below more precisely
    box_combos = [c for c in combos if "Off" in c.cget("values") or "1 day" in c.cget("values")]
    assert box_combos, "Skip recent dropdowns not found"
    target = box_combos[0]   # the All playlists row's Skip recent
    target.set("7 days")
    target.event_generate("<<ComboboxSelected>>")
    ui.pump(0.5)
    data = (app.saved_playlists.main_settings() if where == "main"
            else app.voice.device_page(KITCHEN, "saved"))
    assert data["all_row"]["skip"] == "7", data["all_row"]


# --- the settings sweep -------------------------------------------------------------------

VALUE_TYPES = (ttk.Checkbutton, tk.Checkbutton, ttk.Combobox, ttk.Spinbox, tk.Spinbox, ttk.Entry, tk.Entry,
               ttk.Radiobutton, tk.Radiobutton)


def label_near(w):
    if isinstance(w, (ttk.Checkbutton, tk.Checkbutton, ttk.Radiobutton, tk.Radiobutton)):
        try:
            text = w.cget("text")
            if text:
                return str(text)
        except tk.TclError:
            pass
    parent = w.master
    best = ""
    for sib in parent.winfo_children():
        if sib is w:
            break
        if isinstance(sib, (tk.Label, ttk.Label)):
            try:
                best = str(sib.cget("text"))
            except tk.TclError:
                pass
    return best


def path_of(w):
    names, x = [], w
    while x is not None:
        try:
            if hasattr(x, "_page_title"):
                names.append(x._page_title)
        except Exception:
            pass
        x = x.master
    return "/".join(reversed(names))


def controls(root):
    found = []

    def walk(w, trail):
        for child in w.winfo_children():
            if isinstance(child, VALUE_TYPES):
                found.append((child, f"{path_of(child)}|{type(child).__name__}|{label_near(child)[:40]}"))
            walk(child, trail)
    walk(root, "")
    return found


def value_of(w):
    if isinstance(w, (ttk.Checkbutton, ttk.Radiobutton)):
        return w.instate(["selected"])
    if isinstance(w, (tk.Checkbutton, tk.Radiobutton)):
        var = w.cget("variable")
        return str(w.getvar(var)) if var else None
    return w.get()


def disabled(w):
    try:
        if isinstance(w, (ttk.Checkbutton, ttk.Combobox, ttk.Spinbox, ttk.Entry, ttk.Radiobutton)):
            return w.instate(["disabled"])
        return str(w.cget("state")) == "disabled"
    except tk.TclError:
        return True


def change(w, fake_host):
    """Changes one control the way a person would, with the events its code listens for."""
    if isinstance(w, (ttk.Checkbutton, tk.Checkbutton)):
        w.invoke()
        return True
    if isinstance(w, (ttk.Radiobutton, tk.Radiobutton)):
        if value_of(w) in (True, "1"):
            return False
        w.invoke()
        return True
    if isinstance(w, ttk.Combobox):
        values = list(w.cget("values"))
        current = w.get()
        others = [v for v in values if v != current]
        if not others:
            return False
        w.set(others[-1])
        w.event_generate("<<ComboboxSelected>>")
        return True
    if isinstance(w, (ttk.Spinbox, tk.Spinbox)):
        try:
            lo, hi = float(w.cget("from")), float(w.cget("to"))
            cur = float(w.get() or lo)
        except (tk.TclError, ValueError):
            return False
        new = cur + 1 if cur + 1 <= hi else cur - 1
        if new < lo:
            return False
        w.delete(0, "end")
        w.insert(0, str(int(new)))
        for ev in ("<KeyRelease>", "<FocusOut>", "<Return>"):
            w.event_generate(ev)
        return True
    if isinstance(w, (ttk.Entry, tk.Entry)):
        if w.get() == fake_host or str(w.cget("state")) == "readonly":
            return False
        w.insert("end", "x")
        for ev in ("<KeyRelease>", "<FocusOut>", "<Return>"):
            w.event_generate(ev)
        return True
    return False


def snapshot(ui):
    visit_every_page(ui, ui.settings_pane())
    return [(key, value_of(w)) for w, key in controls(ui.settings)
            if w.winfo_exists() and label_near(w) not in ("Search", "Folder", "Show", "Music like", "Zone")]


def test_every_setting_survives_reopening(app, ui):
    """Changes every control in Settings, then closes and reopens Settings: each must keep its value."""
    import settings_gui
    fake_host = app.engine.JRIVER_HOST
    ui.settings_pane = lambda: next(c for c in ui.settings.winfo_children() if hasattr(c, "select"))
    ui.nb.select(ui.settings)   # pages fill when shown, as when you open Settings
    ui.pump(0.5)
    visit_every_page(ui, ui.settings_pane())
    changed = []
    for w, key in controls(ui.settings):
        # view-only controls that aren't settings: list filters, Show for a key, the voice Test boxes
        if not w.winfo_exists() or disabled(w) or label_near(w) in ("Search", "Folder", "Show", "Music like", "Zone"):
            continue
        if change(w, fake_host):
            changed.append(key)
            ui.pump(0.02)
    ui.pump(1.5)
    before = snapshot(ui)

    ui.settings.destroy()
    app.engine.load_settings()
    ui.settings = settings_gui.SettingsTab(ui.nb)
    ui.nb.add(ui.settings, text="Settings 2")
    ui.nb.select(ui.settings)
    ui.pump(1.0)
    after = snapshot(ui)

    a_keys, b_keys = [k for k, _ in before], [k for k, _ in after]
    sm = difflib.SequenceMatcher(None, a_keys, b_keys, autojunk=False)
    lost = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for (k, va), (_, vb) in zip(before[i1:i2], after[j1:j2]):
                if va != vb:
                    lost.append(f"{k}: set to {va!r}, reopened as {vb!r}")
        else:
            lost.append(f"layout differs: {tag} {a_keys[i1:i2][:3]} -> {b_keys[j1:j2][:3]}")
    report = f"{len(changed)} controls changed; {len(lost)} problems:\n" + "\n".join(lost[:60])
    print(report)
    assert not ui.errors, ui.errors[:2]
    assert not lost, report


# --- JRiver Playlists page: Set as Default ------------------------------------------------

def find_buttons(widget, text):
    out = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Button) and child.cget("text") == text:
            out.append(child)
        out += find_buttons(child, text)
    return out


def test_set_as_default_copies_to_smartlists_shown(app, ui, monkeypatch):
    from tkinter import messagebox
    asked = []
    monkeypatch.setattr(messagebox, "askyesno", lambda title, text, **k: asked.append(text) or True)
    s = ui.settings
    s._layout_device_pane("saved")
    holder = s._panes["saved"]["outer"]
    ui.pump(1.6)   # the page fills, then the rescan 200 ms later
    skips = [c for c in find_saved_global_combos(holder) if "1 day" in c.cget("values")]
    skips[1].set("14 days")   # the All smartlists row
    skips[1].event_generate("<<ComboboxSelected>>")
    ui.pump(0.3)
    buttons = find_buttons(holder, "Set as Default")
    assert len(buttons) == 2
    assert "disabled" not in str(buttons[1].cget("state")), "usable with Use global playlist settings unticked"
    buttons[1].invoke()
    ui.pump(0.5)
    assert asked and "smartlist defaults" in asked[0], asked
    rows = app.saved_playlists.main_settings()["rows"]
    smart = [r for r in rows.values() if r.get("type") == "Smartlist"]
    plain = [r for r in rows.values() if r.get("type") == "Playlist"]
    assert smart and all(r["skip"] == "14" for r in smart), smart
    assert plain and all(r["skip"] == "0" for r in plain), plain


# --- AI Usage in Now Playing and Settings > Keys ---------------------------------------------

def test_ai_usage_shows_in_now_playing_when_ticked(app, ui):
    app.engine.ai_similar("Radiohead")
    ui.play._sync_usage_box()
    assert not ui.play.usage_box.winfo_ismapped()
    app.set_env(AI_USAGE_NOW_PLAYING="1")
    ui.play._sync_usage_box()
    ui.pump(0.3)
    assert ui.play.usage_box.winfo_ismapped(), "visible at the right of Now Playing"
    assert "AI:" in ui.play.usage_label.cget("text")
    ui.settings._fill_usage()
    assert "1 request" in ui.settings.usage_total.cget("text")


def test_ai_usage_tick_shows_it_straight_away(app, ui):
    ui.nb.select(ui.settings)
    ui.pump(0.5)
    ui.settings.usage_np_var.set(True)
    ui.settings._usage_np_toggled()
    ui.nb.select(ui.play)
    ui.pump(0.3)
    assert ui.play.usage_box.winfo_ismapped() and "AI:" in ui.play.usage_label.cget("text")
    ui.nb.select(ui.settings)
    ui.settings.usage_np_var.set(False)
    ui.settings._usage_np_toggled()
    ui.nb.select(ui.play)
    ui.pump(0.3)
    assert not ui.play.usage_box.winfo_ismapped()


def test_ai_usage_click_switches_dollars_and_tokens(app, ui):
    app.engine.ai_similar("Radiohead")
    app.set_env(AI_USAGE_NOW_PLAYING="1", AI_USAGE_NP_UNIT="dollars")
    ui.play._sync_usage_box()
    ui.pump(0.3)
    assert "about" in ui.play.usage_label.cget("text")
    ui.play._usage_flip()
    ui.pump(0.3)
    assert "tokens" in ui.play.usage_label.cget("text")
    assert ui.settings.usage_unit_var.get() == "Tokens", "Settings follows the click"
    ui.settings._fill_usage()
    assert "$1 buys about" in ui.settings.usage_dollar.cget("text")


def test_play_tab_drift_modes_write_settings(app, ui):
    play = ui.play
    play.drift_var.set("Keep It Tight")
    play._on_drift_changed()
    ui.pump(0.3)
    e = app.engine
    assert all(e.DRIFT[g]["on"] and e.DRIFT[g]["from"] == "close" for g in ("artists", "tracks", "vibe"))
    play.drift_var.set("Off")
    play._on_drift_changed()
    ui.pump(0.3)
    assert not any(e.DRIFT[g]["on"] for g in ("artists", "tracks", "vibe"))
    assert all(e.DRIFT[g]["from"] == "close" for g in ("artists", "tracks", "vibe")), "the mode is kept for next time"
    play._sync_play_switches()
    assert play.drift_var.get() == "Off"


def test_support_window(app, ui):
    import support_gui
    win = support_gui.show(ui.root)
    ui.pump(0.3)
    texts = []

    def walk(w):
        for c in w.winfo_children():
            try:
                texts.append(str(c.cget("text")))
            except Exception:
                pass
            walk(c)
    walk(win)
    joined = " ".join(texts)
    assert "Support 24bit7" in joined and "free, and it always will be" in joined
    assert "Donate with PayPal" in joined and "GitHub Issues" in joined
    assert support_gui.show(ui.root) is win, "a second click brings the same window forward"
    win.destroy()


def test_play_tab_nonstop_modes_write_settings(app, ui):
    play = ui.play
    play.nonstop_var.set("Keep It Tight")
    play._on_nonstop_changed()
    ui.pump(0.3)
    by = app.engine.NONSTOP_BY
    assert all(by[g]["on"] and by[g]["mode"] == "tight" for g in ("artists", "tracks", "top", "vibe"))
    play.nonstop_var.set("Off")
    play._on_nonstop_changed()
    ui.pump(0.3)
    assert not any(app.engine.NONSTOP_BY[g]["on"] for g in ("artists", "tracks", "top", "vibe"))
    play._sync_play_switches()
    assert play.nonstop_var.get() == "Off"


# --- Discover: the latest session first, and Label as an option ---------------------------------

def test_discover_opens_on_the_latest_session(app, ui):
    e = app.engine
    e.session_start("similar_tracks", {"Artist": "The Beatles", "Name": "Something", "Album": ""})
    e.session_start("similar_tracks", {"Artist": "The Kinks", "Name": "Waterloo Sunset", "Album": ""})
    d = ui.discover
    d.refresh()
    ui.pump(0.3)
    values = list(d.session_menu.cget("values"))
    assert values[0] == "All sessions" and "Kinks" in values[1] and "Beatles" in values[2]
    assert "Kinks" in d.session_var.get(), "the latest session until one is picked"
    d.session_var.set("All sessions")
    d._on_session_picked()
    e.session_start("similar_tracks", {"Artist": "Blur", "Name": "Tender", "Album": ""})
    d.refresh()
    assert d.session_var.get() == "All sessions", "a session picked by hand stays chosen"


def test_discover_label_button_is_optional(app, ui):
    d = ui.discover
    d.refresh()
    ui.pump(0.3)
    assert d._label_button is not None
    app.set_env(DISCOVER_LABEL="0")
    d.refresh()
    ui.pump(0.3)
    assert d._label_button is None
    assert "Label" not in [b.cget("text") for b in d._site_buttons]


def test_discover_is_laid_out_before_its_first_load(app, ui):
    d = ui.discover
    assert not d._loaded
    assert d.session_var.get() == "Loading sessions..." and d.count_label.cget("text") == "Loading..."
    assert [b.cget("text") for b in d._site_buttons], "the site buttons are there from the start"
    d.ensure_loaded()
    ui.pump(0.5)
    assert d.session_var.get() != "Loading sessions..." and d.count_label.cget("text") != "Loading..."


def test_variety_is_settings_only(app, ui):
    assert not hasattr(ui.play, "variety_cb"), "Variety lives in Settings > Playlist only"


def test_play_tab_behaviour_saves_and_greys_out_for_youtube(app, ui):
    play = ui.play
    assert play.behaviour_var.get() == "Play"
    play.behaviour_var.set("Review")
    play._on_behaviour_changed()
    ui.pump(0.2)
    import settings_gui
    assert settings_gui.read_env().get("PLAY_BEHAVIOUR") == "review"
    assert play._review_mode()
    play.output_var.set("YouTube")
    play._on_output_changed()
    assert play.behaviour_cb.instate(["disabled"])
    assert not play._review_mode(), "YouTube output never reviews"


def test_review_is_for_app_builds_only(app, ui):
    play = ui.play
    assert str(play.behaviour_cb.master) == str(play.extras_row), "Behaviour sits on the More Options row"
    play.behaviour_var.set("Review")
    seen = []
    for review in (False, True):
        play._run_job(lambda: seen.append(app.engine.REVIEW_MODE), needs_playing=False, review=review)
        for _ in range(50):
            ui.pump(0.05)
            if not play.running:
                break
    assert seen == [False, True], "a voice-style build ignores Review; an app build uses it"
