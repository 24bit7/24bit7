"""
Copy Tracks To in Save Playlist's pop-up, on screen (Ben, 23 Nov 2026): the tick under the name, off each time,
greyed with a line saying why when no phone is plugged in; ticked, Device (with Rename and the free space),
Folder, Limit and Clear Music First show and OK reads Save and Copy; after the save the tracks go to the phone.
Save Playlist with the tick off is as it was. A fake phone stands in for Windows Portable Devices.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)
from test_phone_copy import FakePhone

DEVICE = "\\\\?\\usb#vid_18d1&pid_4ee1#serial1#{6ac27878}"


def with_phone(monkeypatch, ph):
    import phone
    monkeypatch.setattr(phone, "devices", lambda: [(DEVICE, "Pixel 9a")])
    monkeypatch.setattr(phone, "WpdPhone", lambda device_id, name: ph)


def prompt(ui, size=2_100_000_000):
    return ui.gui.SavePlaylistPrompt(ui.play, "Save Playlist", "Save ... as a JRiver playlist called:", "Mix", size)


def test_no_phone_greys_the_tick_and_says_why(app, ui, monkeypatch):
    import phone
    monkeypatch.setattr(phone, "devices", lambda: [])
    win = prompt(ui)
    ui.pump(0.3)
    assert win.copy_tick.instate(["disabled"])
    texts = [w.cget("text") for w in win.copy_tick.master.winfo_children() if w.winfo_class() == "Label"]
    assert "Plug in a phone, unlocked and set to File Transfer, to copy to it." in texts
    win.destroy()
    assert not ui.errors, ui.errors[0]


def test_ticked_shows_its_lines_and_hands_back_the_choices(app, ui, monkeypatch):
    with_phone(monkeypatch, FakePhone(free=57 * 10 ** 9, name="Pixel 9a"))
    win = prompt(ui)
    ui.pump(0.3)
    rounded = []
    real = ui.gui.tabs.round_corners
    monkeypatch.setattr(ui.gui.tabs, "round_corners", lambda w, r, **k: rounded.append(w) or real(w, r, **k))
    assert not win.copy_lines.winfo_ismapped(), "hidden until ticked"
    assert win.ok_button.cget("text") == "OK"
    win.copy_var.set(True)
    win._copy_toggled()
    ui.pump(0.3)
    assert win.copy_lines.winfo_ismapped()
    assert win.ok_button.cget("text") == "Save and Copy"
    assert win.ok_button.winfo_rooty() + win.ok_button.winfo_height() <= win.winfo_rooty() + win.winfo_height(), \
        "the window grows to show the lines and its buttons (the first shot cut them off)"
    assert rounded == [win], "and its corners are set again at the new size, or Windows 10 clips it to the old one"
    assert win.device_var.get() == "Pixel 9a" and win.folder_box.get() == "Music"
    assert win.clear_tick.cget("text") == "Clear Music First" and not win.clear_var.get()
    assert win.free_label.cget("text") == "57 of 117 GB free"
    win.limit_box.insert(0, "32")
    win.clear_var.set(True)
    win.ok()
    assert win.copy == {"device": DEVICE, "name": "Pixel 9a", "folder": "Music", "limit_gb": 32.0, "clear": True}
    assert win.result == "Mix"
    assert not ui.errors, ui.errors[0]


def test_save_and_copy_puts_the_tracks_on_the_phone(app, ui, monkeypatch, tmp_path):
    import engine
    import phone
    ph = FakePhone(name="Ben's Phone")
    with_phone(monkeypatch, ph)
    j, p = app.jriver, ui.play
    p._end_greeting()
    keys = j.playlists[0]["keys"][:3]
    j.play("Speakers", keys)
    p._save_zone = engine.zone_id("Speakers")
    files = []
    for n, k in enumerate(keys):
        f = tmp_path / f"{n}.flac"
        f.write_bytes(b"x" * 100)
        files.append({"key": k, "path": str(f), "artist": "A", "title": f"Song {n}", "size": 100})
    monkeypatch.setattr(phone, "tracks_for", lambda ks: files)
    copy = {"device": DEVICE, "name": "Ben's Phone", "folder": "Music", "limit_gb": 0, "clear": False}
    monkeypatch.setattr(ui.gui, "ask_save", lambda *a, **k: ("Jo's Mix", copy))
    p.on_save_playlist()
    win = p.copy_window
    ui.pump(until=lambda: win.finished, timeout=10)
    ui.pump(0.3)
    assert ph.names("Music") == ["A", "Jo's Mix.m3u8"]
    assert ph.names("Music/A") == ["Song 0.flac", "Song 1.flac", "Song 2.flac"]
    assert any(x["Name"] == "Jo's Mix" for x in j.playlists), "saved in JRiver first, as always"
    log = p.log.get("1.0", "end")
    assert "Copying to Ben's Phone..." in log and "Copied to Ben's Phone: 3 tracks in Music" in log, log
    # the pop-up: how it went, and Close
    assert win.heading.cget("text") == "Copied to Ben's Phone"
    assert win.track.cget("text").startswith("Copied to Ben's Phone: 3 tracks in Music, with Jo's Mix.m3u8")
    assert win.ok_button.cget("text") == "Close" and not win.cancel_button.winfo_ismapped()
    assert win.ok_button.winfo_rooty() + win.ok_button.winfo_height() <= win.winfo_rooty() + win.winfo_height()
    win.ok()
    assert not win.winfo_exists()
    assert phone.settings(DEVICE)["name"] == "Ben's Phone", "remembered for next time"
    assert not ui.errors, ui.errors[0]


def test_the_pop_up_shows_progress_and_stop_and_a_phone_going_away(app, ui):
    win = ui.gui.CopyProgress(ui.play, "Jo's Phone")
    ui.pump(0.3)
    assert win.heading.cget("text") == "Copying to Jo's Phone" and win.ok_button.cget("text") == "Stop"
    win.news.put({"state": "copying", "done": 29, "count": 81, "bytes": 1_200_000_000, "total": 3_300_000_000,
                  "track": "SOiL - Halo"})
    ui.pump(0.3)
    assert win.track.cget("text") == "SOiL - Halo"
    assert win.counts.cget("text").startswith("29 of 81 tracks, 1.2 GB of 3.3 GB"), win.counts.cget("text")
    win.ok()   # Stop
    assert win.stopping and win.winfo_exists(), "Stop finishes the track under way; the window stays to say so"
    win.news.put({"state": "failed", "error": "gone"})
    ui.pump(0.3)
    assert win.heading.cget("text") == "Jo's Phone went away"
    assert win.track.cget("text").startswith("29 of 81 tracks are on it.")
    assert win.ok_button.cget("text") == "Close"
    win.ok()
    assert not ui.errors, ui.errors[0]


def test_clear_first_asks_and_no_keeps_the_folder(app, ui, monkeypatch, tmp_path):
    import engine
    import phone
    ph = FakePhone(name="Ben's Phone")
    music = ph.folder("Music", make=True)
    ph.make(music, "Old Album")
    with_phone(monkeypatch, ph)
    j, p = app.jriver, ui.play
    keys = j.playlists[0]["keys"][:1]
    j.play("Speakers", keys)
    p._save_zone = engine.zone_id("Speakers")
    f = tmp_path / "a.flac"
    f.write_bytes(b"x")
    monkeypatch.setattr(phone, "tracks_for", lambda ks: [{"key": keys[0], "path": str(f), "artist": "A",
                                                          "title": "B", "size": 1}])
    copy = {"device": DEVICE, "name": "Ben's Phone", "folder": "Music", "limit_gb": 0, "clear": True}
    monkeypatch.setattr(ui.gui, "ask_save", lambda *a, **k: ("Mix", copy))
    p.on_save_playlist()   # the fixture answers No to the question
    ui.pump(until=lambda: p.copy_window.finished, timeout=10)
    ui.pump(0.3)
    p.copy_window.ok()
    asked = [a for n, a in ui.answers if n == "askyesno"]
    assert asked and "Clear Music on Ben's Phone first? It takes out 1 folder and 0 files" in asked[-1][1], asked
    assert "Old Album" in ph.names("Music"), "No: nothing cleared"
    assert not ui.errors, ui.errors[0]
