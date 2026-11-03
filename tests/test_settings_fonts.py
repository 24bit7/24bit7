"""
The Settings screens are drawn in named Tk fonts at one size (Ben, 3 Nov 2026): body, bold, heading (a
point bigger) and small (a point less), so A- and A+ move every label together. tabs.use_fonts gives
the widgets still in Tk's default font the body font: a classic widget through its font option, a ttk
one through a style that sets only the font, and a style with a size of its own is left alone.
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import pytest

import tabs


@pytest.fixture
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


def sizes(root):
    return tuple(tkfont.nametofont(n, root=root).cget("size") for n in ("S24.body", "S24.bold", "S24.heading", "S24.small"))


def test_the_named_fonts_are_made_once_and_resized_together(root):
    assert tabs.settings_fonts(root) == tabs.SETTINGS_FONT_DEFAULT == 8
    assert sizes(root) == (8, 8, 9, 7)
    weights = {n: tkfont.nametofont(n, root=root).cget("weight") for n in ("S24.body", "S24.bold", "S24.heading", "S24.small")}
    assert weights == {"S24.body": "normal", "S24.bold": "bold", "S24.heading": "bold", "S24.small": "normal"}
    assert tabs.settings_fonts(root, 10) == 10
    assert sizes(root) == (10, 10, 11, 9), "one size moves the four"
    assert tabs.settings_fonts(root) == 10 and sizes(root) == (10, 10, 11, 9), "no size given leaves them"
    label = tk.Label(root, text="x", font="S24.body")
    assert tkfont.Font(root=root, font=label.cget("font")).cget("size") == 10, "a widget in the named font follows it"


def test_use_fonts_gives_default_font_widgets_the_body_font_and_leaves_sized_styles(root):
    tabs.settings_fonts(root, 8)
    style = ttk.Style(root)
    style.configure("Big.TCheckbutton", font=("Segoe UI", 11))
    frame = tk.Frame(root)
    plain = tk.Label(frame, text="a")
    fixed = tk.Label(frame, text="b", font=("Segoe UI", 12))
    tick = ttk.Checkbutton(frame, text="c")
    big = ttk.Checkbutton(frame, text="d", style="Big.TCheckbutton")
    entry = ttk.Entry(frame)
    spin = tk.Spinbox(frame)
    combo = ttk.Combobox(frame)
    inner = tk.Frame(frame)
    deep = tk.Label(inner, text="e")
    tabs.use_fonts(frame)
    assert str(plain.cget("font")) == "S24.body" and str(deep.cget("font")) == "S24.body"
    assert str(fixed.cget("font")) != "S24.body", "a font of its own is kept"
    assert str(tick.cget("style")) == "S24.TCheckbutton" and str(style.lookup("S24.TCheckbutton", "font")) == "S24.body"
    assert str(big.cget("style")) == "Big.TCheckbutton", "a style with its own size is left alone"
    assert str(entry.cget("font")) == "S24.body" and str(spin.cget("font")) == "S24.body" and str(combo.cget("font")) == "S24.body"
    tabs.use_fonts(frame)
    assert str(tick.cget("style")) == "S24.TCheckbutton", "a second pass doesn't stack prefixes"
