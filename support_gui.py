"""
24bit7 - Support.

The "Support" link at the top right of the main window opens this: a few words about
the project, and buttons for donating, the JRiver forum thread and GitHub issues.
"""

import tkinter as tk
import webbrowser

from tabs import PALETTE, FlatButton
from settings_gui import FORUM_URL, REPO_URL

DONATE_URL = "https://paypal.me/24bit7"
ISSUES_URL = REPO_URL + "/issues"

TITLE = "Support 24bit7"
PARAGRAPHS = (
    "24bit7 is a passion project, built for myself and people like me: JRiver users with large music "
    "collections who want to get the most out of their music, and a steady supply of new music to discover.",
    "24bit7 is free, and it always will be. If you'd like to support the project, you can buy me a coffee, "
    "a beer, or a pair of PMC Prodigy speakers.",
    "Donations go towards the Anthropic credits I use building and testing the AI features. Unless anyone "
    "takes the PMC Prodigy speakers seriously ;-)",
    "Got a suggestion, a request or a bug? Post in the 24bit7 thread on the JRiver forum, or open an issue "
    "on GitHub. I'd love to hear from you.",
)

_open = [None]   # the window, if it's already showing


def show(root):
    """Opens the Support window (or brings it forward if it's already open). Returns it."""
    win = _open[0]
    if win is not None and win.winfo_exists():
        win.deiconify()
        win.lift()
        win.focus_force()
        return win
    win = tk.Toplevel(root)
    win.withdraw()   # built out of sight, shown once it's laid out and centred
    _open[0] = win
    win.title(TITLE)
    win.transient(root)
    win.resizable(False, False)
    win.configure(bg=PALETTE.get("window_bg") or root.cget("bg"))
    body = tk.Frame(win, padx=24, pady=20, bg=win.cget("bg"))
    body.pack(fill="both", expand=True)
    tk.Label(body, text=TITLE, font=("Segoe UI", 14, "bold"), fg=PALETTE["section_fg"],
             bg=body.cget("bg")).pack(anchor="w", pady=(0, 10))
    paragraphs = []
    for text in PARAGRAPHS:
        label = tk.Label(body, text=text, font=("Segoe UI", 9), justify="left", anchor="w",
                         fg=PALETTE.get("text") or "#000000", bg=body.cget("bg"))
        label.pack(anchor="w", pady=(0, 18))
        paragraphs.append(label)
    buttons = tk.Frame(body, bg=body.cget("bg"))
    buttons.pack(anchor="w", pady=(10, 0))
    links = [("Donate with PayPal", DONATE_URL, False)]
    if FORUM_URL:
        links.append(("JRiver Forum", FORUM_URL, True))
    links.append(("GitHub Issues", ISSUES_URL, True))
    for text, url, quiet in links:
        FlatButton(buttons, text=text, command=lambda u=url: webbrowser.open(u), quiet=quiet, width=18,
                   height=1).pack(side="left", padx=(0, 8))
    FlatButton(buttons, text="Close", command=win.destroy, quiet=True, width=8, height=1).pack(side="left")
    win.bind("<Escape>", lambda e: win.destroy())
    buttons.update_idletasks()
    for label in paragraphs:   # the text runs the full width of the button row, at any screen scaling
        label.config(wraplength=buttons.winfo_reqwidth())
    win.update_idletasks()
    x = root.winfo_rootx() + max(0, (root.winfo_width() - win.winfo_reqwidth()) // 2)
    y = root.winfo_rooty() + max(0, (root.winfo_height() - win.winfo_reqheight()) // 3)
    win.geometry(f"+{x}+{y}")
    win.deiconify()
    win.focus_force()
    return win
