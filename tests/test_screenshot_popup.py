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
    monkeypatch.setattr(screenshots, "grab_box", lambda window, bbox, above=None: "image")
    assert screenshots.grab(root, popup) == "image"
    assert log == [("root", None), ("popup", "root")]



def test_with_no_screen_the_list_is_pasted_into_the_windows_own_drawing(monkeypatch):
    """12 Nov 2026: with the TV off a screen grab fails and the window is drawn alone, which left the list out."""
    from PIL import Image, ImageGrab

    def no_screen(bbox=None, **k):
        raise OSError("no monitor")
    monkeypatch.setattr(ImageGrab, "grab", no_screen)

    class Win(Fake):
        def __init__(self, x, y):
            self.x, self.y = x, y

        def winfo_rootx(self):
            return self.x

        def winfo_rooty(self):
            return self.y

        def winfo_toplevel(self):
            return self
    root, popup = Win(100, 50), Win(130, 70)
    drawn = {id(root): Image.new("RGB", (40, 40), "white"), id(popup): Image.new("RGB", (5, 5), "red")}
    monkeypatch.setattr(screenshots, "window_image", lambda w: drawn[id(w)])
    image = screenshots.grab_box(root, (100, 50, 140, 90), popup)
    assert image.getpixel((32, 22)) == (255, 0, 0) and image.getpixel((10, 10)) == (255, 255, 255)
