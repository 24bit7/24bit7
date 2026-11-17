"""
The new-version note in the console (17 Nov 2026): every release since yours, Update Now for the built program,
Release Notes and Hide; it stays past the ninety seconds other notes get. Update Now asks first, gets the release
ready on a thread, then hands over to the updater as 24bit7 closes. Opens real windows; nothing is downloaded.
"""

from tkinter import messagebox

from test_gui import ui  # noqa: F401  (the GUI fixture)

INFO = {"latest": "99.0.0", "link": "https://github.com/24bit7/24bit7/releases/tag/v99.0.0",
        "zip": "https://github.com/24bit7/24bit7/releases/download/v99.0.0/24bit7-v99.0.0-windows.zip",
        "sha256": "https://github.com/24bit7/24bit7/releases/download/v99.0.0/24bit7-v99.0.0-windows.zip.sha256",
        "releases": [("99.0.0", "Radio gets a pause button."), ("98.0.0", "Albums on the Play tab.")]}


def console(ui):
    return ui.play.log.get("1.0", "end")


def test_the_note_lists_whats_new_and_hide_takes_it_away(app, ui, monkeypatch):
    monkeypatch.setattr(app.engine, "can_update", lambda info: True)
    ui.play._greeting_active = False
    ui.play.whats_new_found.put(INFO)
    ui.pump(until=lambda: "New since yours" in console(ui), timeout=10)
    text = console(ui)
    assert "99.0.0  Radio gets a pause button." in text and "98.0.0  Albums on the Play tab." in text
    assert ui.play._update_button.winfo_exists() and ui.play._update_button.cget("text") == "Update Now"
    assert not any(e[0] in ui.play._whats_new_lines for e in getattr(ui.play, "_idle_lines", [])), \
        "it isn't one of the lines that clear after ninety seconds"
    ui.play._hide_whats_new()
    assert "New since yours" not in console(ui)
    assert not ui.errors, ui.errors[0]


def test_from_source_there_is_no_update_now(app, ui):
    ui.play._greeting_active = False
    ui.play.whats_new_found.put(INFO)
    ui.pump(until=lambda: "New since yours" in console(ui), timeout=10)
    assert not getattr(ui.play, "_update_button", None) or not ui.play._update_button.winfo_ismapped()


def test_update_now_asks_gets_it_ready_then_hands_over(app, ui, monkeypatch):
    monkeypatch.setattr(app.engine, "can_update", lambda info: True)
    got, events = [], []
    monkeypatch.setattr(app.engine, "prepare_update", lambda info, report: got.append(info) or r"C:\x\new\24bit7")
    monkeypatch.setattr(ui.play.root, "event_generate", lambda name: events.append(name))
    ui.play._greeting_active = False
    ui.play.whats_new_found.put(INFO)
    ui.pump(until=lambda: "New since yours" in console(ui), timeout=10)

    ui.play._update_now()   # the fixture answers No
    ui.pump(0.3)
    assert ui.answers and "Update from" in ui.answers[-1][1][1] and not got
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    ui.play._update_now()
    ui.pump(until=lambda: events, timeout=10)
    assert got == [INFO] and events == ["<<Update24bit7>>"]
    assert app.engine.UPDATE_PENDING == (r"C:\x\new\24bit7", "99.0.0")
    app.engine.UPDATE_PENDING = None
