"""
Settings read when 24bit7 starts must stay as read. engine.py loads .env once at
import; a module-level default further down the file would quietly reset it
(this happened to Use AI and Run After Building before 1.16.0).
"""

import ast
import importlib
import os
import sys


def test_nothing_resets_settings_after_the_startup_load(app):
    path = os.path.join(app.folder, "engine.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    loader = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_settings")
    names = {name for n in ast.walk(loader) if isinstance(n, ast.Global) for name in n.names}
    call_line = next(n.lineno for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                     and getattr(n.value.func, "id", None) == "load_settings")
    resets = [f"line {n.lineno}: {t.id}" for n in tree.body if n.lineno > call_line
              and isinstance(n, (ast.Assign, ast.AnnAssign))
              for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
              if isinstance(t, ast.Name) and t.id in names]
    assert not resets, "set at startup, then reset further down engine.py: " + ", ".join(resets)


def test_use_ai_off_and_run_after_survive_a_fresh_start(app):
    with open(app.folder / ".env", "a", encoding="utf-8") as f:
        f.write("USE_AI=0\nRUN_AFTER_VIBE=1\nRUN_AFTER_VIBE_PATH=C:\\after.bat\n")
    for k in ("USE_AI", "RUN_AFTER_VIBE", "RUN_AFTER_VIBE_PATH"):
        os.environ.pop(k, None)
    sys.modules.pop("engine", None)
    engine = importlib.import_module("engine")   # a fresh start: settings come only from the import-time load
    assert engine.USE_AI is False
    assert engine.RUN_AFTER["vibe"] == (True, "C:\\after.bat")
