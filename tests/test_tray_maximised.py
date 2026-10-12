"""Tray: a window maximised before closing to the tray comes back maximised."""

import os

import pytest

from conftest import load_gui


class FakeRoot:
    """Behaves like Tk on Windows: deiconify shows the window at its normal size."""

    def __init__(self, state="normal"):
        self._state = state
        self.calls = []

    def state(self, new=None):
        if new is None:
            return self._state
        self.calls.append(("state", new))
        self._state = new

    def withdraw(self):
        self.calls.append(("withdraw",))
        self._state = "withdrawn"

    def deiconify(self):
        self.calls.append(("deiconify",))
        self._state = "normal"

    def lift(self):
        pass

    def focus_force(self):
        pass


@pytest.fixture
def gui(app):
    return load_gui(app.folder)


def test_maximised_window_comes_back_maximised(gui):
    root, memo = FakeRoot("zoomed"), {}
    gui.hide_to_tray(root, memo)
    assert root.state() == "withdrawn"
    gui.show_from_tray(root, memo)
    assert root.state() == "zoomed"


def test_normal_window_comes_back_normal(gui):
    root, memo = FakeRoot("normal"), {}
    gui.hide_to_tray(root, memo)
    gui.show_from_tray(root, memo)
    assert root.state() == "normal"


def test_maximised_then_restored_comes_back_normal(gui):
    root, memo = FakeRoot("zoomed"), {}
    gui.hide_to_tray(root, memo)
    gui.show_from_tray(root, memo)
    root.state("normal")
    gui.hide_to_tray(root, memo)
    gui.show_from_tray(root, memo)
    assert root.state() == "normal"


def test_minimised_while_maximised_keeps_the_noted_state(gui):
    root, memo = FakeRoot("zoomed"), {}
    gui.hide_to_tray(root, memo)
    gui.show_from_tray(root, memo)
    root.state("iconic")
    gui.hide_to_tray(root, memo)
    gui.show_from_tray(root, memo)
    assert root.state() == "zoomed"


def test_started_in_the_tray_opens_normal(gui):
    root = FakeRoot("withdrawn")
    gui.show_from_tray(root, {})
    assert root.state() == "normal"


@pytest.mark.skipif(not os.environ.get("DISPLAY") and os.name != "nt", reason="needs a display")
def test_real_tk_window_round_trip(gui):
    import tkinter as tk
    root = tk.Tk()
    try:
        root.geometry("400x300")
        root.update()
        memo = {}
        gui.hide_to_tray(root, memo)
        root.update()
        assert root.state() == "withdrawn"
        gui.show_from_tray(root, memo)
        root.update()
        assert root.state() == "normal"
    finally:
        root.destroy()
