"""
2 Nov 2026: the + beside the Settings > Playlists list stayed lit after the Add a Playlist window was
cancelled. The window's grab kept the button's Leave event from arriving, so after a command the
button looks again at where the pointer is.
"""

import pytest

tk = pytest.importorskip("tkinter")


def test_a_button_whose_command_opened_a_window_unlights_when_the_pointer_has_gone():
    import tabs
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        tabs.apply_theme(root, "dark")
        opened = []

        def command():   # while the window was up, the pointer went to it: the button is no longer under it
            opened.append(True)
            fb._over = lambda: False
        fb = tabs.FlatButton(root, text="+", width=2, command=command, quiet=True)
        fb.pack()
        root.update()
        fb._over = lambda: True   # pressed and released over the button
        fb._on_enter(None)
        fb._on_press(None)
        assert fb._inside and fb._pressed
        fb._on_release(None)
        root.update()
        assert opened == [True]
        assert not fb._inside and not fb._pressed, "the hover colour has gone with the pointer"
        # and a command that leaves the pointer where it was keeps the hover, as before
        fb2 = tabs.FlatButton(root, text="+", width=2, command=lambda: None, quiet=True)
        fb2.pack()
        root.update()
        fb2._over = lambda: True
        fb2._on_enter(None)
        fb2._on_press(None)
        fb2._on_release(None)
        assert fb2._inside, "still under the pointer: still lit"
    finally:
        root.destroy()
