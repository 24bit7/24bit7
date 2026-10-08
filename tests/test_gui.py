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
    settings.play = play
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
    assert not play.behaviour_cb.instate(["disabled"])
    assert play._review_mode(), "Review works with YouTube too: Play on YouTube opens the ticked tracks"


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


# --- Review: the list in the console area ---

def _review_build(app, ui, n=6):
    play = ui.play
    keys = [str(r["Key"]) for r in app.jriver.by_key.values()][:n]
    play.behaviour_var.set("Review")

    def target():
        play.report("Similar Tracks: The Beatles - Here Comes The Sun  (target 30, at most 2 per artist)")
        app.engine.REVIEW_KEYS = list(keys)
    play._run_job(target, needs_playing=False, review=True)
    ui.pump(until=lambda: not play.running)
    ui.pump(0.2)
    return keys


def test_review_build_opens_the_review_list(app, ui):
    keys = _review_build(app, ui)
    panel = ui.play.review_panel
    assert panel.showing and [r["key"] for r in panel.rows] == keys
    assert panel.title == "Similar Tracks: The Beatles - Here Comes The Sun"
    assert all(r["artist"] and r["title"] for r in panel.rows), "rows filled from the library"
    assert not ui.play.log.frame.winfo_manager(), "the console text is hidden while Review shows"
    assert not app.jriver.zone("Speakers").playlist, "nothing sent to JRiver"


def test_review_ticks_number_in_click_order(app, ui):
    keys = _review_build(app, ui)
    panel = ui.play.review_panel
    for k in (keys[3], keys[1], keys[4]):
        panel.toggle(k)
    assert panel.ticked_keys() == [keys[3], keys[1], keys[4]]
    assert [panel._cells[k][0].cget("text") for k in (keys[3], keys[1], keys[4], keys[0])] == ["1", "2", "3", ""]
    panel.toggle(keys[1])   # untick the middle one: the rest close up
    assert panel._cells[keys[4]][0].cget("text") == "2"
    assert panel.count_label.cget("text") == "6 tracks, 2 ticked"
    panel.select_all()
    assert panel.ticked_keys() == keys
    panel.select_none()
    assert panel.ticked_keys() == []


def test_review_switch_back_to_console_and_dot(app, ui):
    keys = _review_build(app, ui)
    panel, play = ui.play.review_panel, ui.play
    panel.toggle(keys[0])
    panel.show_console()
    assert play.log.frame.winfo_manager() and not panel.frame.winfo_manager()
    assert panel.review_btn.cget("text") == "Review (1)", "ticked tracks are still waiting"
    panel.show_review()
    play._append_log("  a voice build in the kitchen")
    assert panel.console_btn.cget("text").startswith("Console ") and panel.dot
    panel.show_console()
    assert play.log.frame.winfo_manager() and not panel.dot


def test_play_build_leaves_review_closed(app, ui):
    play = ui.play
    play.behaviour_var.set("Play")
    play._run_job(lambda: play.report("Similar Tracks: x"), needs_playing=False, review=True)
    ui.pump(until=lambda: not play.running)
    assert not play.review_panel.showing and not play.review_panel.switch_row.winfo_manager()


# --- Review: the actions ---

def _review_with_zone(app, ui, playing=None, pos=1):
    """A Review build of 6 library tracks for Speakers, with Speakers playing `playing` (or stopped)."""
    play = ui.play
    keys = [str(r["Key"]) for r in app.jriver.by_key.values()][20:26]
    if playing:
        app.jriver.play("Speakers", playing, pos=pos)
    play.behaviour_var.set("Review")

    def target():
        play.report("Similar Artists: Moby - Porcelain  (target 30)")
        app.engine.REVIEW_KEYS = list(keys)
        app.engine.REVIEW_ZONE = app.jriver.zone("Speakers").id
    play._run_job(target, needs_playing=False, review=True)
    ui.pump(until=lambda: not play.running)
    ui.pump(0.2)
    return keys


def _act(ui, how, ticks):
    panel = ui.play.review_panel
    for k in ticks:
        panel.toggle(k)
    panel._act(how)
    ui.pump(until=lambda: not panel.busy)
    ui.pump(0.2)
    return panel



def _album(app):
    return [str(r["Key"]) for r in app.jriver.by_key.values()][:5]


def test_review_add_as_up_next(app, ui):
    album = _album(app)
    keys = _review_with_zone(app, ui, album)
    panel = _act(ui, "next", [keys[4], keys[0]])
    z = app.jriver.zone("Speakers")
    assert z.playlist == album[:2] + [keys[4], keys[0]] + album[2:], "after the current song, in tick order"
    assert z.state == 2 and z.pos == 1
    assert panel.ticked_keys() == [], "ticks clear once it's gone"
    assert "added as Up Next in Speakers" in ui.play.log.get("1.0", "end")


def test_review_add_to_end(app, ui):
    album = _album(app)
    keys = _review_with_zone(app, ui, album)
    _act(ui, "end", [keys[1], keys[2]])
    assert app.jriver.zone("Speakers").playlist == album + [keys[1], keys[2]]


def test_review_finish_this_song_load_as_new(app, ui):
    album = _album(app)
    keys = _review_with_zone(app, ui, album)
    _act(ui, "finish", [keys[2], keys[3]])
    z = app.jriver.zone("Speakers")
    assert z.playlist == [album[1], keys[2], keys[3]] and z.pos == 0, "the current song, then only these"
    assert z.state == 2


def test_review_stop_song_load_as_new(app, ui):
    album = _album(app)
    keys = _review_with_zone(app, ui, album)
    _act(ui, "stop", [keys[5], keys[0]])
    z = app.jriver.zone("Speakers")
    assert z.playlist == [keys[5], keys[0]] and z.pos == 0 and z.state == 2


def test_review_load_as_new_on_a_stopped_zone_plays(app, ui):
    keys = _review_with_zone(app, ui)
    _act(ui, "finish", [keys[1]])
    z = app.jriver.zone("Speakers")
    assert z.playlist == [keys[1]] and z.state == 2


def test_review_actions_need_a_tick(app, ui):
    keys = _review_with_zone(app, ui, _album(app))
    panel = ui.play.review_panel
    before = list(app.jriver.zone("Speakers").playlist)
    panel._act("next")
    ui.pump(0.3)
    assert app.jriver.zone("Speakers").playlist == before and not panel.busy


def test_review_save_as_playlist(app, ui, monkeypatch):
    from tkinter import simpledialog
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "Wedding Extras")
    keys = _review_with_zone(app, ui, _album(app))
    before = list(app.jriver.zone("Speakers").playlist)
    panel = ui.play.review_panel
    for k in (keys[3], keys[0]):
        panel.toggle(k)
    panel._save()
    ui.pump(until=lambda: not panel.busy)
    saved = [p for p in app.jriver.playlists if p["Name"] == "Wedding Extras"]
    assert saved and saved[0]["keys"] == [keys[3], keys[0]]
    assert app.jriver.zone("Speakers").playlist == before, "saving plays nothing"


def test_review_save_asks_before_replacing(app, ui, monkeypatch):
    from tkinter import simpledialog
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "Sunday Morning")   # already exists
    keys = _review_with_zone(app, ui)
    panel = ui.play.review_panel
    panel.toggle(keys[0])
    panel._save()   # the fixture answers No
    ui.pump(0.3)
    sunday = next(p for p in app.jriver.playlists if p["Name"] == "Sunday Morning")
    assert keys[0] not in sunday["keys"], "kept, as the answer was No"


# --- Review: Preview ---

def _preview_ready(app, ui, zone="Sonos"):
    global settings_gui
    import settings_gui
    keys = _review_with_zone(app, ui, _album(app))
    panel = ui.play.review_panel
    if zone:
        panel.choose_preview(zone)
        ui.pump(0.1)
    return keys, panel


def test_preview_off_by_default_no_marks(app, ui):
    keys, panel = _preview_ready(app, ui, zone=None)
    assert panel.preview_zone is None and panel._marks == {}
    assert panel.preview_btn.cget("text").startswith("None")


def test_preview_never_offers_the_lists_zone(app, ui):
    keys, panel = _preview_ready(app, ui, zone=None)
    choices = panel.preview_choices()
    assert "Speakers" not in choices and "Sonos" in choices and "Kitchen" in choices


def test_preview_plays_one_track_in_the_preview_zone(app, ui):
    keys, panel = _preview_ready(app, ui)
    album = _album(app)
    assert settings_gui.read_env().get("REVIEW_PREVIEW_ZONE") == "Sonos", "remembered"
    assert set(panel._marks) == set(keys), "a mark on every row"
    panel._preview_click(keys[2])
    ui.pump(0.3)
    sonos, speakers = app.jriver.zone("Sonos"), app.jriver.zone("Speakers")
    assert sonos.playlist == [keys[2]] and sonos.state == 2
    assert speakers.playlist == album and speakers.pos == 1 and speakers.state == 2, "main room untouched"
    assert panel.ticked_keys() == [], "previewing doesn't tick"
    assert panel._marks[keys[2]].cget("text") == "\u25a0"
    panel._preview_click(keys[4])   # another track replaces it
    ui.pump(0.3)
    assert sonos.playlist == [keys[4]]
    assert panel._marks[keys[2]].cget("text") == "\u25b6"


def test_stop_preview_and_clicking_the_stop_mark(app, ui):
    keys, panel = _preview_ready(app, ui)
    panel._preview_click(keys[0])
    ui.pump(0.3)
    panel._preview_click(keys[0])   # the stop mark
    ui.pump(0.3)
    assert app.jriver.zone("Sonos").state == 0 and panel.previewing is None
    panel._preview_click(keys[1])
    ui.pump(0.3)
    panel.stop_preview()
    ui.pump(0.3)
    assert app.jriver.zone("Sonos").state == 0
    assert panel.status_label.cget("text") == "Preview stopped."


def test_an_action_stops_the_preview(app, ui):
    keys, panel = _preview_ready(app, ui)
    panel._preview_click(keys[3])
    ui.pump(0.3)
    _act(ui, "end", [keys[1]])
    assert app.jriver.zone("Sonos").state == 0 and panel.previewing is None


def test_choosing_none_stops_and_hides_the_marks(app, ui):
    keys, panel = _preview_ready(app, ui)
    panel._preview_click(keys[0])
    ui.pump(0.3)
    panel.choose_preview("")
    ui.pump(0.3)
    assert app.jriver.zone("Sonos").state == 0 and panel._marks == {}
    assert settings_gui.read_env().get("REVIEW_PREVIEW_ZONE") == ""


def test_preview_zone_same_as_list_zone_is_refused(app, ui):
    keys, panel = _preview_ready(app, ui, zone="Speakers")
    assert panel.preview_zone is None and panel._marks == {}


# --- notes on titles (the ? marks retired) ---

def _widgets(w):
    yield w
    for c in w.winfo_children():
        yield from _widgets(c)


def test_every_note_sits_on_a_title(app, ui):
    ui.pump(1.5)
    notes = [w for w in _widgets(ui.play.root) if hasattr(w, "_note_text")]
    assert len(notes) > 60
    for w in notes:
        title = w._note_target
        assert title is not None, f"unplaced: {w._note_text[:40]}"
        assert str(title.cget("text")) != "?", f"fell back to a ?: {w._note_text[:40]}"
        assert str(title.cget("cursor")) == "question_arrow"
    titles = [id(w._note_target) for w in notes]
    assert len(titles) == len(set(titles)), "one note per title"


def test_note_goes_on_the_rows_title_not_the_last_label(app, ui):
    ui.pump(1.5)
    timing = next(w for w in _widgets(ui.play.root)
                  if getattr(w, "_note_text", "").startswith("Fine-tunes switching"))
    assert timing._note_target.cget("text") == "Switch Timing Adjustment", "not 'seconds'"


def test_note_waits_before_showing(app, ui):
    import settings_gui
    ui.pump(1.5)
    behaviour = next(w for w in _widgets(ui.play.root)
                     if getattr(w, "_note_text", "").startswith("Play: the playlist"))._note_target
    note = behaviour._tooltip
    note._wait()   # as the pointer arrives
    ui.pump(0.1)
    assert note.tip is None, "not straight away"
    ui.pump(settings_gui.NOTE_DELAY_MS / 1000 + 0.3)
    assert note.tip is not None, "shown after the delay"
    assert int(note.tip.winfo_children()[0].cget("wraplength")) == settings_gui.NOTE_WRAP
    note.hide()   # as the pointer leaves
    assert note.tip is None
    note._wait()
    note.hide()   # left before the delay: never shown
    ui.pump(settings_gui.NOTE_DELAY_MS / 1000 + 0.3)
    assert note.tip is None


# --- Profiles (Settings > Other) ---

def _env(app):
    import settings_gui
    return settings_gui.read_env()


def test_profile_save_change_and_load_back(app, ui, monkeypatch):
    import profiles, settings_gui
    from tkinter import simpledialog
    s = ui.settings
    settings_gui.write_env({"SIMILAR_TRACK_COUNT": "25", "PLAY_BEHAVIOUR": "review", "THEME": "dark",
                            "ANTHROPIC_API_KEY": "sk-original"})
    app.engine.db().execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('play_mix', '{\"rows\": [1]}')")
    app.engine.db().commit()
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "DJ")
    s._profile_save_as()
    assert profiles.names() == ["DJ"] and profiles.current() == "DJ"
    saved = profiles.read("DJ")
    assert saved["env"]["SIMILAR_TRACK_COUNT"] == "25" and saved["env"]["PLAY_BEHAVIOUR"] == "review"
    assert "ANTHROPIC_API_KEY" not in saved["env"] and "THEME" not in saved["env"], "keys and looks stay out"
    assert s.profile_status.cget("text") == "Current: DJ"
    assert not profiles.changed()

    # change things after saving
    settings_gui.write_env({"SIMILAR_TRACK_COUNT": "40", "PLAY_BEHAVIOUR": "instant", "THEME": "light",
                            "ANTHROPIC_API_KEY": "sk-new"})
    app.engine.db().execute("DELETE FROM meta WHERE key='play_mix'")
    app.engine.db().commit()
    assert profiles.changed()
    s._show_profile_status()
    assert s.profile_status.cget("text") == "Current: DJ (changed)"

    # Load: confirmed (the fixture answers No, so answer Yes here), queued, restart asked for
    from tkinter import messagebox
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    restarts = []
    ui.play.root.bind("<<Restart24bit7>>", lambda e: restarts.append(1))
    s.profile_var.set("DJ")
    s._profile_load()
    ui.pump(0.2)
    assert restarts and os.path.isfile(profiles.PENDING)

    # the next start applies it
    assert profiles.apply_pending() == "DJ"
    env = _env(app)
    assert env["SIMILAR_TRACK_COUNT"] == "25" and env["PLAY_BEHAVIOUR"] == "review"
    assert env["THEME"] == "light" and env["ANTHROPIC_API_KEY"] == "sk-new", "machine settings untouched"
    row = app.engine.db().execute("SELECT value FROM meta WHERE key='play_mix'").fetchone()
    assert row and row[0] == '{"rows": [1]}', "Add Playlist rows come back"
    assert app.engine.SIMILAR_TRACK_COUNT == 25, "the running settings follow"
    assert not os.path.isfile(profiles.PENDING) and not profiles.changed()


def test_profile_unset_settings_go_back_to_defaults(app, ui):
    import profiles, settings_gui
    settings_gui.write_env({"CONSOLE_MODE": None})
    profiles.save("Plain")
    settings_gui.write_env({"CONSOLE_MODE": "advanced"})
    profiles.queue_load("Plain")
    profiles.apply_pending()
    assert "CONSOLE_MODE" not in _env(app)
    assert not profiles.changed("Plain")


def test_profile_load_cancelled_changes_nothing(app, ui):
    import profiles
    profiles.save("Explore")
    ui.settings._fill_profiles("Explore")
    import settings_gui
    settings_gui.write_env({"SIMILAR_TRACK_COUNT": "33"})
    ui.settings._profile_load()   # the fixture answers No
    assert not os.path.isfile(profiles.PENDING)
    assert _env(app)["SIMILAR_TRACK_COUNT"] == "33"


def test_profile_delete(app, ui, monkeypatch):
    import profiles
    from tkinter import messagebox
    profiles.save("No AI")
    s = ui.settings
    s._fill_profiles("No AI")
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    s._profile_delete()
    assert profiles.names() == [] and profiles.current() == ""
    assert s.profile_status.cget("text") == "Current: None"


# --- Review: Stop Song, Play Now; text size; the arrow beside the switch ---

def test_stop_song_play_now_name(app, ui):
    import review_gui
    assert dict((h, t) for h, t, _ in review_gui.ACTIONS)["stop"] == "Stop Song, Play Now"
    album = _album(app)
    keys = _review_with_zone(app, ui, album)
    _act(ui, "stop", [keys[0]])
    assert "song stopped, 1 track playing now in Speakers" in ui.play.log.get("1.0", "end")


def test_review_text_size_buttons(app, ui):
    import settings_gui
    keys = _review_with_zone(app, ui, _album(app))
    panel = ui.play.review_panel
    start = panel.size
    panel.toggle(keys[1])
    panel.bigger_btn.event_generate("<Button-1>")
    ui.pump(0.2)
    assert panel.size == start + 1
    assert settings_gui.read_env().get("REVIEW_FONT_SIZE") == str(start + 1), "remembered"
    cell = panel._cells[keys[1]][1][0]
    assert int(str(cell.cget("font")).split()[-2] if "bold" in str(cell.cget("font")) else
               str(cell.cget("font")).split()[-1]) == start + 1
    assert panel.ticked_keys() == [keys[1]], "ticks kept"
    for _ in range(20):
        panel.set_size(panel.size - 1)
    assert panel.size == 6, "no smaller than 6"
    for _ in range(20):
        panel.set_size(panel.size + 1)
    assert panel.size == 14, "no bigger than 14"


def test_console_arrow_sits_beside_the_switch(app, ui):
    keys = _review_with_zone(app, ui, _album(app))
    panel, play = ui.play.review_panel, ui.play
    panel.show_console()
    ui.pump(0.2)
    info = play.head_arrow.place_info()
    assert info.get("in") == panel.switch_row, "beside the switch, not over the text"
    play._set_tabs_open(True, save=False)
    ui.pump(0.1)
    assert play.head_arrow.place_info().get("in") == panel.switch_row, "still there with the tabs open"
    play._set_tabs_open(False, save=False)
    assert play.head_arrow.place_info().get("in") == panel.switch_row


# --- Review follows Output ---

def test_review_actions_follow_output(app, ui):
    album = _album(app)
    keys = _review_with_zone(app, ui, album)
    play = ui.play
    play.output_var.set("Sonos")
    play._on_output_changed()
    _act(ui, "finish", [keys[2]])
    assert app.jriver.zone("Sonos").playlist == [keys[2]], "went to Output's zone"
    assert app.jriver.zone("Speakers").playlist == album, "not the zone the build was for"
    assert "Sonos" not in play.review_panel.preview_choices(), "Output's zone never offered for Preview"


def test_review_play_on_youtube(app, ui, monkeypatch):
    keys = _review_with_zone(app, ui, _album(app))
    play, panel = ui.play, ui.play.review_panel
    seen = {}
    monkeypatch.setattr(app.engine, "youtube_ids_for_pairs",
                        lambda pairs: seen.setdefault("pairs", pairs) and [f"v{i}" for i, _ in enumerate(pairs)])
    monkeypatch.setattr(app.engine, "open_youtube_playlist",
                        lambda ids: seen.setdefault("ids", ids) and len(ids))
    play.output_var.set("YouTube")
    play._on_output_changed()
    ui.pump(0.1)
    assert panel.youtube_actions.winfo_manager() and not panel.jriver_actions.winfo_manager()
    rows = {r["key"]: r for r in panel.rows}
    for k in (keys[4], keys[1]):
        panel.toggle(k)
    panel._youtube()
    ui.pump(until=lambda: not panel.busy)
    assert seen["pairs"] == [(rows[k]["artist"], rows[k]["title"]) for k in (keys[4], keys[1])], "tick order"
    assert "2 tracks opened on YouTube" in play.log.get("1.0", "end")
    play.output_var.set("Same zone")
    play._on_output_changed()
    assert panel.jriver_actions.winfo_manager() and not panel.youtube_actions.winfo_manager()


def test_review_has_no_status_line(app, ui):
    _review_with_zone(app, ui, _album(app))
    assert not ui.play.review_panel.status_label.winfo_manager()


def test_review_rows_alternate_shading(app, ui):
    keys = _review_with_zone(app, ui, _album(app))
    panel = ui.play.review_panel
    p = panel.p
    shade = lambda k: panel._cells[k][1][0].cget("bg")
    assert shade(keys[0]) == p["bg"] and shade(keys[1]) == p["stripe"] and shade(keys[2]) == p["bg"]
    panel.toggle(keys[1])
    assert shade(keys[1]) == p["row_on"], "a ticked row's shading wins over the stripe"
    panel.toggle(keys[1])
    assert shade(keys[1]) == p["stripe"]


# --- AI Playlist window (Create) ---

def test_ai_playlist_window_create(app, ui, monkeypatch):
    import ai_dialog, settings_gui
    monkeypatch.setattr(app.engine, "ai_vibe_suggestions", lambda: ["Late-night jazz", "Driving at night"])
    got = {}
    dlg = ai_dialog.AIPlaylistDialog(ui.play.root, play=ui.play, on_create=lambda t, n, s: got.update(theme=t, count=n, if_short=s))
    ui.pump(0.6)
    assert dlg.mode == "create"
    texts = [c.cget("text") for c in dlg.idea_chips]
    assert texts == ["Late-night jazz", "Driving at night"], "nothing is playing, so no More Tracks Like chip"
    dlg.idea_chips[0].event_generate("<Button-1>")
    ui.pump(0.1)
    assert dlg.theme.get() == "Late-night jazz"
    dlg.count.delete(0, "end"); dlg.count.insert(0, "12")
    dlg.set_if_short("drift")
    dlg.submit()
    ui.pump(0.1)
    assert got == {"theme": "Late-night jazz", "count": 12, "if_short": "drift"}
    env = settings_gui.read_env()
    assert env.get("AI_CREATE_THEME") == "Late-night jazz" and env.get("VIBE_TRACK_COUNT") == "12"
    assert env.get("AI_IF_SHORT") == "drift" and env.get("AI_DIALOG_MODE", "create") == "create"
    # next time: remembered
    dlg2 = ai_dialog.AIPlaylistDialog(ui.play.root, play=ui.play, on_create=lambda *a: None)
    ui.pump(0.3)
    assert dlg2.theme.get() == "Late-night jazz" and dlg2.count.get() == "12" and dlg2.if_short == "drift"
    dlg2.destroy()



# --- AI Playlist window (Steer) ---

def test_ai_playlist_steer(app, ui):
    import ai_dialog, settings_gui
    album = _album(app)
    app.jriver.play("Speakers", album, pos=1)
    got = {}
    dlg = ai_dialog.AIPlaylistDialog(ui.play.root, play=ui.play, on_create=lambda *a: None,
                                     on_steer=lambda spec: got.update(spec))
    ui.pump(0.3)
    dlg.set_mode("steer")
    ui.pump(0.5)
    assert dlg.go_btn.cget("text") == "Steer" and settings_gui.read_env().get("AI_DIALOG_MODE") == "steer"
    assert dlg.seed_note.cget("text") and dlg.seed_note.cget("text") != "Nothing is playing."
    dlg.set_seed("all")
    ui.pump(0.5)
    assert dlg.seed_note.cget("text") == f"{len(album)} tracks"
    dlg.toggle_direction("dancier"); dlg.toggle_direction("faster")
    dlg.set_strength("lot")
    dlg.assess_tone()
    ui.pump(until=lambda: dlg.tone_text() != "", timeout=5)
    assert dlg.tone_text() == "Warm late-70s disco and funk, mid-tempo, upbeat"
    dlg.own.insert(0, "more Latin")
    dlg.submit()
    ui.pump(0.1)
    assert got["seed_kind"] == "all" and got["directions"] == ["dancier", "faster"] and got["strength"] == "lot"
    assert got["own_words"] == "more Latin" and got["count"] == 12 and got["if_short"] == "ask"
    env = settings_gui.read_env()
    assert env.get("AI_STEER_DIRS") == "dancier,faster" and env.get("AI_STEER_OWN") == "more Latin"
    # next time: opens on Steer with everything as left
    dlg2 = ai_dialog.AIPlaylistDialog(ui.play.root, play=ui.play, on_create=lambda *a: None)
    ui.pump(0.3)
    assert dlg2.mode == "steer" and dlg2.directions == ["dancier", "faster"] and dlg2.strength == "lot"
    assert dlg2.tone_text().startswith("Warm late-70s") and dlg2.own.get() == "more Latin"
    dlg2.destroy()


def test_steer_build_reaches_review(app, ui):
    album = _album(app)
    app.jriver.play("Speakers", album, pos=1)
    play = ui.play
    play.behaviour_var.set("Review"); play._on_behaviour_changed()
    pairs = app.engine.steer_seed_pairs(all_tracks=False)
    assert len(pairs) == 1
    play._run_job(lambda: app.engine.steer_playlist(pairs, ["dancier"], "", "little", "a tone", 6, report=play.report),
                  needs_playing=False, review=True)
    ui.pump(until=lambda: not play.running, timeout=20)
    log = play.log.get("1.0", "end")
    assert "AI Playlist: Steer: dancier (a little)" in log
    assert "move from there a little in this direction: dancier" in app.ai.sent[-1]
    assert "Their tone: a tone." in app.ai.sent[-1]
    assert play.review_panel.rows, "the tracks landed in Review"


# --- Use AI (Settings > Keys) ---

def test_use_ai_off_pauses_the_ai(app, ui):
    import settings_gui
    play, s = ui.play, ui.settings
    app.set_env(ANTHROPIC_API_KEY="sk-test")
    app.engine.load_settings()
    play.sync_moderator()
    ai_button = next(b for b in play.buttons if b.cget("text") == "AI Playlist")
    assert ai_button.cget("state") == "normal" and not play.moderator_cb.instate(["disabled"])
    assert s.use_ai_var.get() == "On"
    s.use_ai_var.set("Off"); s._use_ai_changed()
    ui.pump(0.2)
    assert settings_gui.read_env().get("USE_AI") == "0" and app.engine.USE_AI is False
    assert not app.engine.ai_enabled()
    assert ai_button.cget("state") == "disabled", "AI Playlist greys out"
    assert play.moderator_cb.instate(["disabled"]), "the moderator dropdown greys out"
    assert "Use AI is Off" in app.engine.vibe_blocker()
    assert app.engine.ai_ask_json("anything") is None and app.engine.AI_LAST_ERROR == "Use AI is Off"
    s.use_ai_var.set("On"); s._use_ai_changed()
    ui.pump(0.2)
    assert ai_button.cget("state") == "normal" and not play.moderator_cb.instate(["disabled"])


def test_use_ai_off_moderator_notes_once_and_sources_skip(app, ui):
    e = app.engine
    app.set_env(ANTHROPIC_API_KEY="sk-test", USE_AI="0", AI_MODERATOR="normal", SIMILAR_SOURCES="lastfm,ai")
    e.load_settings()
    r = app.Lines()
    e.create_similar_playlist(report=r, seed_info=e.typed_seed_info("The Beatles", "Something"))
    text = "\n".join(r)
    assert "AI is ticked but Use AI is Off" in text
    assert text.count("AI Moderator skipped: Use AI is Off") <= 1
    assert not any(c for c in app.ai.calls), "the AI was never called"


# --- Settings > Playlist: the Review column ---

def test_review_column_same_as_play_then_own_figures(app, ui):
    import settings_gui
    s = ui.settings
    same = s._review_vars["same"]
    assert all(v.get() for v in same.values()), "Same as Play ticked to start"
    assert app.engine.review_overrides() == {}
    settings_gui.write_env({"REVIEW_SAME_TRACKS": "0", "REVIEW_SIMILAR_TRACK_COUNT": "12",
                            "REVIEW_SAME_ARTISTS": "0", "REVIEW_SIMILAR_ARTIST_LIMIT": "6",
                            "REVIEW_TRACKS_PER_ARTIST_PICK": "2", "REVIEW_SIMILAR_ARTIST_TRACK_COUNT": "15"})
    over = app.engine.review_overrides()
    assert over == {"SIMILAR_TRACK_COUNT": "12", "SIMILAR_ARTIST_LIMIT": "6", "TRACKS_PER_ARTIST_PICK": "2",
                    "SIMILAR_ARTIST_TRACK_COUNT": "15", "SIMILAR_ARTIST_TRACK_LIMIT": "1"}
    # a Review build of Similar Tracks aims for 12; a Play build still for 30
    j, play = app.jriver, ui.play
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    ui.pump(until=lambda: play.last_playing, timeout=10)
    play.behaviour_var.set("Review"); play._on_behaviour_changed()
    play.on_similar_tracks()
    ui.wait_idle()
    text = console(ui)
    assert "Review settings in use" in text and "(target 12" in text, text
    assert app.engine.SIMILAR_TRACK_COUNT == 30, "Windows (Main)'s own figure is back after the build"
    play.behaviour_var.set("Play"); play._on_behaviour_changed()
    play.on_similar_tracks()
    ui.wait_idle()
    assert "(target 30" in console(ui).split("Similar Tracks:")[-1]


def test_cost_note_wraps_inside_the_window(app, ui):
    """The 'costs are estimates' note under the AI Usage table wraps to the window, not past it."""
    ui.root.geometry("760x700")
    ui.nb.select(ui.settings)
    ui.pump(0.3)
    visit_every_page(ui)
    label = ui.settings.usage_rates
    child = label
    while child.master is not None:   # open the page the note is on
        parent = child.master
        if hasattr(parent, "select") and hasattr(parent, "add") and hasattr(parent, "remove"):
            parent.select(child)
        child = parent
    ui.pump(0.6)
    page = label
    while not isinstance(page.master, tk.Canvas):
        page = page.master
    right = page.winfo_rootx() + page.winfo_width()
    assert label.winfo_rootx() + label.winfo_reqwidth() <= right, "the note runs past the window's edge"


def test_about_thanks_everyone_in_the_readme(app):
    """Settings > About and the README thank the same people."""
    gui_settings = __import__("settings_gui")
    readme = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md"),
                  encoding="utf-8").read()
    thanks = readme.split("## Thanks", 1)[1].split("\n## ", 1)[0]
    for name, _ in gui_settings.THANKS:
        assert f"**{name}**" in thanks
