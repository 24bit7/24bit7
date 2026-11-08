"""
The shots keep the window on top, and grab lifts it before each shot, so an open drop-down list (Radio's
stations, the JRiver playlists) ended up under the window and missing from the picture (7 Nov 2026).
"""

import screenshots


class Fake:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def lift(self, above=None):
        self.log.append((self.name, above.name if above else None))

    def winfo_rootx(self):
        return 0

    winfo_rooty = winfo_rootx

    def winfo_width(self):
        return 10

    winfo_height = winfo_width


def test_an_open_list_is_lifted_back_over_the_window(monkeypatch):
    log = []
    root, popup = Fake(log, "root"), Fake(log, "popup")
    monkeypatch.setattr(screenshots, "settle", lambda *a: None)
    monkeypatch.setattr(screenshots, "grab_box", lambda window, bbox: "image")
    assert screenshots.grab(root, popup) == "image"
    assert log == [("root", None), ("popup", "root")]
