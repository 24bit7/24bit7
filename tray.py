"""
24bit7 - starting with Windows, and the tray icon.

Start with Windows is a value under your own Run key in the registry
(HKEY_CURRENT_USER), so it needs no admin rights, and it points at whichever
copy of 24bit7 set it: the packaged exe, or gui.pyw run by pythonw (no console).
Windows launches it with --tray, which Start in the tray uses to begin hidden.

The tray icon runs on its own thread (pystray); its menu hands everything back
to the Tk thread with root.after, as the Play tab's workers do.
"""

import os
import sys

import engine

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "24bit7"
TRAY_FLAG = "--tray"

_icon = None


# --- Start with Windows ----------------------------------------------------------

def launch_command():
    """What Windows runs at sign-in: this copy of 24bit7, with --tray."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {TRAY_FLAG}'
    exe = sys.executable
    windowless = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(windowless):
        exe = windowless
    return f'"{exe}" "{os.path.join(engine.APP_DIR, "gui.pyw")}" {TRAY_FLAG}'


def startup_command():
    """The command Windows will run at sign-in, or None if 24bit7 isn't set to start."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_VALUE)[0]
    except (ImportError, OSError):
        return None


def set_startup(on):
    """Adds or removes the sign-in entry. Raises if the registry can't be written."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def started_by_windows():
    return TRAY_FLAG in sys.argv


# --- the tray icon -----------------------------------------------------------------

def available():
    try:
        import pystray   # noqa: F401
        from PIL import Image   # noqa: F401
        return True
    except ImportError:
        return False


def _icon_image():
    from PIL import Image
    base = getattr(sys, "_MEIPASS", engine.APP_DIR)   # the packaged app keeps its files in _MEIPASS
    try:
        return Image.open(os.path.join(base, "24bit7.ico"))
    except Exception:
        return Image.new("RGB", (64, 64), (38, 110, 190))


def running():
    return _icon is not None


def start(root, show, quit):
    """Puts 24bit7 in the tray. Clicking the icon opens the window. Returns False if it can't."""
    global _icon
    if _icon is not None:
        return True
    if not available():
        print("[Tray] pystray and Pillow aren't installed, so there's no tray icon. "
              "Run: pip install pystray Pillow")
        return False
    import pystray
    menu = pystray.Menu(
        pystray.MenuItem("Open 24bit7", lambda icon, item: root.after(0, show), default=True),
        pystray.MenuItem("Quit", lambda icon, item: root.after(0, quit)))
    _icon = pystray.Icon("24bit7", _icon_image(), "24bit7", menu)
    _icon.run_detached()
    return True


def stop():
    global _icon
    if _icon is not None:
        try:
            _icon.stop()
        except Exception:
            pass
        _icon = None
