"""
+ Add a Phone Over WiFi, on screen (Ben, 24 Nov 2026, as drawn): the last line of Save's Device list opens a small
prompt for the code the phone shows and a name; Add finds it on the home network (here a stand-in app on this PC)
and it's listed as "Ben's Phone (WiFi)", its free space read without holding the window up.
"""

from test_gui import ui   # noqa: F401  (the GUI fixture)
from test_wifi_phone import phone_app   # noqa: F401  (the stand-in phone app)


def test_add_a_phone_over_wifi_from_the_device_list(app, ui, monkeypatch, phone_app):
    import phone
    monkeypatch.setattr(phone, "devices", lambda: [])
    ui.play._end_greeting()
    add = ui.gui.AddWifiPrompt(ui.play)
    ui.pump(0.2)
    add.code_box.insert(0, "12")
    add.ok()
    assert add.note.cget("text") == "Type the four numbers the phone shows."
    add.code_box.delete(0, "end")
    add.code_box.insert(0, "1234")
    add.ok()
    ui.pump(until=lambda: not add._looking, timeout=30)
    assert add.note.cget("text") == "No phone answered to that code. Is 24bit7 open on it, on the same WiFi?"
    add.code_box.delete(0, "end")
    add.code_box.insert(0, "4659")
    add.name_box.insert(0, "Ben's Phone")
    add.ok()
    ui.pump(until=lambda: not add.winfo_exists(), timeout=30)
    key = add.result
    assert key == "app:" + phone_app.app_id
    ui.pump(0.3)
    assert "Added Ben's Phone over WiFi." in ui.play.log.get("1.0", "end")
    # the Device list: chosen from its last line, the new phone is listed and chosen
    save = ui.gui.SavePrompt(ui.play, "What's playing in Speakers (3 tracks, 1 MB).", "Mix", 1_000_000)
    ui.pump(0.2)
    save.copy_var.set(True)
    save._copy_toggled()
    ui.pump(0.2)
    assert list(save.device_cb.cget("values")) == ["Ben's Phone (WiFi)", "This PC", "+ Add a Phone Over WiFi..."]
    ui.pump(until=lambda: "GB free" in save.free_label.cget("text"), timeout=15)
    assert save.free_label.cget("text") == "64 of 117 GB free"
    save.device_cb.current(1)
    save._device_picked()
    assert save._device()[0] == phone.PC
    monkeypatch.setattr(ui.gui, "ask_add_wifi", lambda parent: key)
    save.device_cb.current(2)
    save._device_picked()
    assert save._device()[0] == key and save.device_var.get() == "Ben's Phone (WiFi)"
    save.destroy()
    assert not ui.errors, ui.errors[0]
