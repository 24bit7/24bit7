"""
Save's pop-up, on screen (Save Playlist's Copy Tracks To, Ben, 23 Nov 2026; one Save for JRiver and the phone, 24 Nov
2026): the name, which names the JRiver playlist and the .m3u8 alike, then As a JRiver Playlist and Copy Tracks To.
After a build JRiver starts ticked and the phone not; for what's in the Playlists & Albums box the phone starts ticked,
and a lone JRiver playlist greys the JRiver tick. Copy Tracks To is greyed with a line saying why when no phone is
plugged in; ticked, Device (with Rename and the free space), Folder, Limit and Clear Playlists First show. A fake phone
stands in for Windows Portable Devices.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)
from test_phone_copy import FakePhone

DEVICE = "\\\\?\\usb#vid_18d1&pid_4ee1#serial1#{6ac27878}"


def with_phone(monkeypatch, ph):
    import phone
    monkeypatch.setattr(phone, "devices", lambda: [(DEVICE, "Pixel 9a")])
    monkeypatch.setattr(phone, "WpdPhone", lambda device_id, name: ph)
    return ph


def prompt(ui, size=2_100_000_000, **kw):
    return ui.gui.SavePrompt(ui.play, "What's playing in Speakers (30 tracks, 2.1 GB).", "Mix", size, **kw)


def test_no_phone_says_so_and_this_pc_is_still_there(app, ui, monkeypatch, tmp_path):
    """With no phone plugged in, This PC is the one place to copy to (Ben, 24 Nov 2026): no folder until chosen,
    no Rename, and Save says to choose one with Browse."""
    import phone
    monkeypatch.setattr(phone, "devices", lambda: [])
    win = prompt(ui, copy=True)
    ui.pump(0.3)
    assert not win.copy_tick.instate(["disabled"]) and not win.copy_var.get(), "not ticked for you with only This PC"
    texts = [w.cget("text") for w in win.copy_tick.master.winfo_children() if w.winfo_class() == "Label"]
    assert "Plug in a phone, unlocked and set to File Transfer, to copy to it." in texts
    win.copy_var.set(True)
    win._copy_toggled()
    ui.pump(0.2)
    assert list(win.device_cb.cget("values")) == ["This PC", "+ Add a Phone Over WiFi..."]
    assert win.folder_box.get() == ""
    assert not win.rename_link.winfo_ismapped() and win.browse_link.winfo_ismapped()
    win.jriver_var.set(False)
    win.ok()
    assert win.warn.cget("text") == "Choose a folder on this PC with Browse."
    sync = tmp_path / "Phone Sync"
    win.folder_box.insert(0, str(sync))
    win._sync_clear_text()
    assert win.clear_note.cget("text") == "Takes off the playlists already on This PC. Your albums stay."
    win.ok()
    assert win.copy == {"device": "pc", "name": "This PC", "folder": str(sync), "limit_gb": 0.0, "clear": False}
    assert not ui.errors, ui.errors[0]


def test_ticked_shows_its_lines_and_hands_back_the_choices(app, ui, monkeypatch):
    with_phone(monkeypatch, FakePhone(free=57 * 10 ** 9, name="Pixel 9a"))
    win = prompt(ui)
    ui.pump(0.3)
    rounded = []
    real = ui.gui.tabs.round_corners
    monkeypatch.setattr(ui.gui.tabs, "round_corners", lambda w, r, **k: rounded.append(w) or real(w, r, **k))
    assert win.jriver_var.get() and not win.copy_var.get(), "after a build: JRiver ticked, the phone not"
    assert not win.copy_lines.winfo_ismapped(), "hidden until ticked"
    assert win.ok_button.cget("text") == "Save"
    win.copy_var.set(True)
    win._copy_toggled()
    ui.pump(0.3)
    assert win.copy_lines.winfo_ismapped()
    assert win.ok_button.cget("text") == "Save", "one Save, whatever is ticked"
    assert win.ok_button.winfo_rooty() + win.ok_button.winfo_height() <= win.winfo_rooty() + win.winfo_height(), \
        "the window grows to show the lines and its buttons (the first shot cut them off)"
    assert rounded == [win], "and its corners are set again at the new size, or Windows 10 clips it to the old one"
    assert win.device_var.get() == "Pixel 9a (USB)" and win.folder_box.get() == "Music"
    assert win.clear_tick.cget("text") == "Clear Playlists First" and not win.clear_var.get()
    assert win.free_label.cget("text") == "57 of 117 GB free"
    win.limit_box.insert(0, "32")
    win.clear_var.set(True)
    win.ok()
    assert win.copy == {"device": DEVICE, "name": "Pixel 9a", "folder": "Music", "limit_gb": 32.0, "clear": True}
    assert win.result == "Mix" and win.jriver
    assert not ui.errors, ui.errors[0]


def test_the_box_starts_on_the_phone_and_a_playlist_cant_go_to_jriver_again(app, ui, monkeypatch):
    with_phone(monkeypatch, FakePhone(name="Jo's Phone"))
    win = prompt(ui, size=800_000_000, jriver=False, jriver_ok=False, copy=True)
    ui.pump(0.3)
    assert win.copy_var.get() and win.copy_lines.winfo_ismapped(), "the box: the phone ticked to start"
    assert win.jriver_tick.instate(["disabled"]) and not win.jriver_var.get()
    texts = [w.cget("text") for w in win.jriver_tick.master.winfo_children() if w.winfo_class() == "Label"]
    assert "It's a JRiver playlist already." in texts
    assert win.ok_button.winfo_rooty() + win.ok_button.winfo_height() <= win.winfo_rooty() + win.winfo_height()
    win.copy_var.set(False)
    win._copy_toggled()
    win.ok()
    assert win.winfo_exists() and win.result is None, "nothing ticked: Save waits"
    assert win.warn.cget("text") == "Tick As a JRiver Playlist, Copy Tracks To, or both."
    win.copy_var.set(True)
    win._copy_toggled()
    win.entry.delete(0, "end")
    win.ok()
    assert win.winfo_exists() and win.warn.cget("text") == "Give it a name first."
    win.entry.insert(0, "Abbey Road")
    win.ok()
    assert win.result == "Abbey Road" and not win.jriver
    assert win.copy["name"] == "Pixel 9a" and win.copy["folder"] == "Music", "its model's name until renamed"
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
    p._show_save(engine.zone_id("Speakers"))
    ui.pump(0.2)
    assert p.save_button.winfo_ismapped() and p.save_button.cget("text").endswith("Save")
    files = []
    for n, k in enumerate(keys):
        f = tmp_path / f"{n}.flac"
        f.write_bytes(b"x" * 100)
        files.append({"key": k, "path": str(f), "artist": "A", "title": f"Song {n}", "size": 100})
    monkeypatch.setattr(phone, "tracks_for", lambda ks: files)
    copy = {"device": DEVICE, "name": "Ben's Phone", "folder": "Music", "limit_gb": 0, "clear": False}
    asked = []
    monkeypatch.setattr(ui.gui, "ask_save", lambda *a, **k: asked.append((a, k)) or ("Jo's Mix", True, copy))
    p.save_button._command()
    assert asked[0][1] == {"jriver": True, "jriver_ok": True, "copy": False}, "after a build: JRiver, as it was"
    assert asked[0][0][1] == "What's playing in Speakers (3 tracks, 1 MB).", asked[0][0][1]
    win = p.copy_window
    ui.pump(until=lambda: win.finished, timeout=10)
    ui.pump(0.3)
    assert ph.names("Music") == ["Playlists"], "a playlist goes into Playlists (Ben, 25 Nov 2026)"
    assert ph.names("Music/Playlists") == ["A - Song 0.flac", "A - Song 1.flac", "A - Song 2.flac", "Jo's Mix.m3u8"]
    assert any(x["Name"] == "Jo's Mix" for x in j.playlists), "saved in JRiver first, as always"
    log = p.log.get("1.0", "end")
    assert "Copying to Ben's Phone..." in log and "Copied to Ben's Phone: 3 tracks in Music/Playlists" in log, log
    # the pop-up: how it went, and Close
    assert win.heading.cget("text") == "Copied to Ben's Phone"
    assert win.track.cget("text").startswith("Copied to Ben's Phone: 3 tracks in Music/Playlists, with Jo's Mix.m3u8")
    assert win.ok_button.cget("text") == "Close" and not win.cancel_button.winfo_ismapped()
    assert win.ok_button.winfo_rooty() + win.ok_button.winfo_height() <= win.winfo_rooty() + win.winfo_height()
    win.ok()
    assert not win.winfo_exists()
    assert phone.settings(DEVICE)["name"] == "Ben's Phone", "remembered for next time"
    assert not ui.errors, ui.errors[0]


def test_a_playlist_emptied_in_jriver_comes_off_the_phone(app, ui, monkeypatch, tmp_path):
    """Ben, 24 Nov 2026: a playlist with all its tracks removed is taken off the phone when saved there."""
    import phone
    from test_jriver_playlists_tab import lists_tab
    ph = FakePhone(name="Ben's Phone")
    with_phone(monkeypatch, ph)
    f = tmp_path / "one.flac"
    f.write_bytes(b"x" * 100)
    phone.copy_playlist(ph, "Music", "Emptied", [{"key": "1", "path": str(f), "artist": "A", "title": "One",
                                                   "size": 100}], say=lambda line: None)
    assert ph.names("Music/Playlists") == ["A - One.flac", "Emptied.m3u8"]
    emptied = {"ID": "909", "Name": "Emptied", "Folder": "Mixes", "Type": "Playlist", "keys": []}
    app.jriver.playlists.append(emptied)
    p = lists_tab(ui)
    p._playlist_chosen, p._box_newer = {k: v for k, v in emptied.items() if k != "keys"}, True
    copy = {"device": DEVICE, "name": "Ben's Phone", "folder": "Music", "limit_gb": 0, "clear": True}
    asked = []
    monkeypatch.setattr(ui.gui, "ask_save", lambda *a, **k: asked.append((a, k)) or ("Emptied", False, copy))
    p.on_save()
    assert asked[0][0][1].startswith("The playlist Emptied is empty in JRiver."), asked[0][0][1]
    assert asked[0][1] == {"jriver": False, "jriver_ok": False, "copy": True}
    win = p.copy_window
    ui.pump(until=lambda: win.finished, timeout=10)
    ui.pump(0.3)
    assert ph.names("Music/Playlists") == [], \
        "its .m3u8 and its own track went; Clear First is never asked for an empty one"
    assert "Took Emptied.m3u8 off Ben's Phone: the playlist is empty now." in p.log.get("1.0", "end")
    win.ok()
    assert not ui.errors, ui.errors[0]


def test_browse_goes_into_folders_and_hands_back_the_path(app, ui, monkeypatch):
    """Ben, 23 Nov 2026: "I can't see how to navigate to or choose the right folder" (Jo's is Music/Music)."""
    ph = FakePhone(name="Jo's Phone")
    music = ph.folder("Music", make=True)
    ph.make(music, "Music")
    ph.make(music, "Signal")
    ph.make(music, ".thumbnails")
    with_phone(monkeypatch, ph)
    save = prompt(ui)
    ui.pump(0.3)
    save.copy_var.set(True)
    save._copy_toggled()
    ui.pump(0.2)
    assert save.browse_link.winfo_ismapped() and save.browse_link.cget("text") == "Browse"
    win = ui.gui.FolderPicker(save, ph, "Jo's Phone", "Music")
    ui.pump(0.3)
    assert list(win.listbox.get(0, "end")) == ["↑  Up", "    Music", "    Signal"], "dot folders left out"
    assert [w.cget("text") for w in win.crumbs.winfo_children()] == ["Phone", "›", "Music"]
    win.enter("Music")
    assert win.path == ["Music", "Music"] and list(win.listbox.get(0, "end")) == ["↑  Up"]
    win.ok()
    assert win.result == "Music/Music"
    top = ui.gui.FolderPicker(save, ph, "Jo's Phone", "Nowhere/At All")
    ui.pump(0.3)
    assert top.path == [] and list(top.listbox.get(0, "end")) == ["    Music"], "a missing path falls back"
    top.ok()
    assert top.winfo_exists() and top.result is None, "never the phone's top level"
    assert top.note.cget("text") == "Choose a folder, not the whole phone."
    top.listbox.selection_set(0)
    top.ok()
    assert top.result == "Music", "or the folder selected"
    save.destroy()
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


def test_save_on_playlists_and_albums_copies_the_box_without_playing(app, ui, monkeypatch, tmp_path):
    """
    Ben, 23 Nov 2026: "the option to be able to load a playlist without playing it"; 24 Nov: Copy to Phone is Save.
    The newest wins: a pick after a build saves the box, a build after the pick saves what played.
    """
    import engine
    import phone
    from test_jriver_playlists_tab import lists_tab, type_in
    ph = FakePhone(name="Jo's Phone")
    with_phone(monkeypatch, ph)
    j = app.jriver
    p = lists_tab(ui)
    assert not p.save_button.winfo_ismapped(), "nothing picked and nothing built yet"
    road_trip = next(x for x in j.playlists if x["ID"] == "202")
    p._pick_playlist({"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"})
    ui.pump(0.3)
    assert p.save_button.winfo_ismapped() and p.save_button.cget("text") == ui.gui.SAVE_ICON + "  Save"
    asked = []

    def tracks_for(keys):
        asked.append(list(keys))
        out = []
        for n, k in enumerate(keys[:2]):
            f = tmp_path / f"{n}.flac"
            f.write_bytes(b"x" * 10)
            out.append({"key": k, "path": str(f), "artist": "A", "title": f"Song {n}", "size": 10})
        return out
    monkeypatch.setattr(phone, "tracks_for", tracks_for)
    prompts = []
    copy = {"device": DEVICE, "name": "Jo's Phone", "folder": "Music/Music", "limit_gb": 0, "clear": False}
    monkeypatch.setattr(ui.gui, "ask_save", lambda parent, prompt, initial, size, **k:
                        prompts.append((prompt, initial, k)) or (initial, False, copy))
    playlists = len(j.playlists)
    p.save_button._command()
    ui.pump(until=lambda: p.copy_window.finished, timeout=10)
    ui.pump(0.3)
    p.copy_window.ok()
    assert asked == [road_trip["keys"]], "the playlist's tracks, read from JRiver"
    text, initial, kw = prompts[0]
    assert text.startswith(f"The playlist Road Trip ({len(road_trip['keys'])} tracks, "), text
    assert text.endswith("without playing it.") and initial == "Road Trip"
    assert kw == {"jriver": False, "jriver_ok": False, "copy": True}, "the phone to start; JRiver has it already"
    assert ph.names("Music/Music/Playlists") == ["A - Song 0.flac", "A - Song 1.flac", "Road Trip.m3u8"]
    assert j.zone("Speakers").playlist == [], "nothing played"
    assert len(j.playlists) == playlists, "and no JRiver playlist saved"
    # a build after the pick: Save saves what played; a pick after that: the box again
    p._show_save(engine.zone_id("Speakers"))
    assert p._save_target() == ("build", engine.zone_id("Speakers"))
    p._pick_playlist({"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"})
    assert p._save_target()[0] == "box"
    type_in(ui, p, "road")
    assert p._save_target()[0] == "build", "typing again: nothing in the box, so what played"
    p._pick_playlist({"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"})
    ui.pump(0.3)
    p.seed_nb.select(p.search_tab)
    ui.pump(0.3)
    assert p._save_target()[0] == "build", "another tab: the box isn't on screen, so what played"
    assert p.save_button.winfo_ismapped()
    assert not ui.errors, ui.errors[0]


def test_clear_first_asks_and_no_keeps_the_folder(app, ui, monkeypatch, tmp_path):
    import engine
    import phone
    ph = FakePhone(name="Ben's Phone")
    with_phone(monkeypatch, ph)
    old = tmp_path / "old.flac"
    old.write_bytes(b"x")
    phone.copy_playlist(ph, "Music", "Old", [{"key": "9", "path": str(old), "artist": "B", "title": "Old Song",
                                              "size": 1}], say=lambda line: None)
    j, p = app.jriver, ui.play
    keys = j.playlists[0]["keys"][:1]
    j.play("Speakers", keys)
    p._show_save(engine.zone_id("Speakers"))
    f = tmp_path / "a.flac"
    f.write_bytes(b"x")
    monkeypatch.setattr(phone, "tracks_for", lambda ks: [{"key": keys[0], "path": str(f), "artist": "A",
                                                          "title": "B", "size": 1}])
    copy = {"device": DEVICE, "name": "Ben's Phone", "folder": "Music", "limit_gb": 0, "clear": True}
    monkeypatch.setattr(ui.gui, "ask_save", lambda *a, **k: ("Mix", False, copy))
    p.on_save()   # the fixture answers No to the question
    ui.pump(until=lambda: p.copy_window.finished, timeout=10)
    ui.pump(0.3)
    p.copy_window.ok()
    asked = [a for n, a in ui.answers if n == "askyesno"]
    assert asked and asked[-1][1].startswith("Clear Playlists on Ben's Phone first? It takes off the playlists there "
                                             "and their songs ("), asked
    assert "Your albums stay." in asked[-1][1]
    assert "Old.m3u8" in ph.names("Music/Playlists"), "No: nothing cleared"
    assert not any(x["Name"] == "Mix" for x in j.playlists), "JRiver unticked: no JRiver playlist"
    assert not ui.errors, ui.errors[0]
