"""
The app's own small windows (1 Nov 2026): rounded corners on Windows 10 too, by a window region of
their own when the Windows 11 DWM ask isn't understood, and a drag that moves once per turn of the
event loop with a repaint after, so the contents keep up with the frame.
"""

import tkinter as tk

from test_gui import ui  # noqa: F401  (the GUI fixture)


class Calls:
    """A stand-in for ctypes.windll: records what's asked of user32, dwmapi and gdi32."""

    def __init__(self, dwm_ok):
        self.calls = []
        self.dwm_ok = dwm_ok
        outer = self

        class Lib:
            def __getattr__(self, name):
                def call(*args):
                    outer.calls.append((name, args))
                    if name == "DwmSetWindowAttribute":
                        return 0 if outer.dwm_ok else 0x80070057
                    if name == "GetParent":
                        return 4242
                    if name == "GetWindowRect":
                        rect = args[1]._obj
                        rect.left, rect.top, rect.right, rect.bottom = 100, 100, 520, 400
                        return 1
                    if name == "CreateRoundRectRgn":
                        return 77
                    return 1
                return call
        self.user32 = self.dwmapi = self.gdi32 = Lib()


def test_windows_10_gets_a_rounded_region_and_windows_11_the_dwm_corners(app, ui):
    import tabs
    win = tk.Toplevel(ui.play)
    win.geometry("420x300+100+100")
    ui.pump(0.2)
    ten = Calls(dwm_ok=False)
    assert tabs.round_corners(win, 10, windll=ten) == "region"
    names = [n for n, _ in ten.calls]
    assert names == ["GetParent", "DwmSetWindowAttribute", "GetWindowRect", "CreateRoundRectRgn", "SetWindowRgn"], names
    rgn = dict(ten.calls)["CreateRoundRectRgn"]
    assert rgn == (0, 0, 421, 301, 20, 20), "the window's own size, corners of the radius asked"
    assert dict(ten.calls)["SetWindowRgn"] == (4242, 77, True)
    eleven = Calls(dwm_ok=True)
    assert tabs.round_corners(win, 10, windll=eleven) == "dwm"
    assert [n for n, _ in eleven.calls] == ["GetParent", "DwmSetWindowAttribute"], "Windows 11 draws them itself"
    win.destroy()
    assert not ui.errors, ui.errors[0]


def test_the_header_hands_the_drag_to_windows(app, ui):
    import tabs
    import settings_gui
    win = settings_gui.AddPlaylistPrompt(ui.settings)
    ui.pump(0.6)

    class At:
        x_root, y_root = 300, 120
    fake = Calls(dwm_ok=True)
    assert tabs.native_drag(win, At(), windll=fake) is True
    assert [n for n, _ in fake.calls] == ["GetParent", "ReleaseCapture", "PostMessageW"], fake.calls
    assert dict(fake.calls)["PostMessageW"] == (4242, 0x00A1, 2, (120 << 16) | 300), "a title-bar press, where the mouse is"
    monkeypatch_calls = []
    tabs_native = tabs.native_drag
    tabs.native_drag = lambda window, event, windll=None: monkeypatch_calls.append(event) or True
    try:
        win._drag_start(At())
        assert monkeypatch_calls and win._drag is None, "Windows has the drag: Tk moves nothing"
        moves = []
        win.geometry = lambda spec=None: moves.append(spec)
        win._drag_move(At())
        ui.pump(0.2)
        assert moves == []
    finally:
        tabs.native_drag = tabs_native
    win.cancel()
    assert not ui.errors, ui.errors[0]


def test_the_add_window_asked_for_corners_and_drags_once_per_turn_where_windows_wont(app, ui):
    import tabs
    import settings_gui
    win = settings_gui.AddPlaylistPrompt(ui.settings)
    ui.pump(0.6)
    assert win.corners in ("dwm", "region"), win.corners
    tabs_native = tabs.native_drag
    tabs.native_drag = lambda window, event, windll=None: False   # not Windows: Tk moves the window
    x0, y0 = win.winfo_x(), win.winfo_y()
    moves = []
    real = win.geometry

    def counting(spec=None):
        if spec is not None:
            moves.append(spec)
        return real(spec) if spec is not None else real()
    win.geometry = counting

    class At:
        def __init__(self, x, y):
            self.x_root, self.y_root = x, y
    win._drag_start(At(x0 + 50, y0 + 10))
    for step in range(1, 6):
        win._drag_move(At(x0 + 50 + step * 8, y0 + 10 + step * 4))   # five events in one burst
    ui.pump(0.3)
    tabs.native_drag = tabs_native
    assert len(moves) == 1 and moves[0] == f"+{x0 + 40}+{y0 + 20}", (moves, "one move, where the last event said")
    win.cancel()
    assert not ui.errors, ui.errors[0]
