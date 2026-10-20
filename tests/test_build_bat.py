"""
build.bat closes the packaged 24bit7 before it rebuilds, and opens the new one at the end.
"""

import os

BAT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build.bat")


def lines():
    with open(BAT, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().lower().startswith("rem ")]


def first(match):
    for i, line in enumerate(lines()):
        if match(line):
            return i
    raise AssertionError("not found in build.bat")


def test_closes_24bit7_after_the_tests_and_before_the_backup():
    tests = first(lambda l: l.startswith("python -m pytest"))
    close = first(lambda l: "Stop-Process" in l)
    backup = first(lambda l: l.startswith('if exist "24bit7.db" copy'))
    assert tests < close < backup


def test_closes_only_the_packaged_copy():
    close = lines()[first(lambda l: "Stop-Process" in l)]
    assert r"dist\24bit7\24bit7.exe" in close
    assert "$_.Path -eq $exe" in close


def test_opens_the_new_24bit7_after_publishing():
    publish = first(lambda l: "release.ps1" in l)
    reopen = first(lambda l: l.startswith("if exist") and "start " in l and r"dist\24bit7\24bit7.exe" in l)
    done = first(lambda l: l == "echo Build complete.")
    assert publish < reopen < done


def test_quick_build_skips_only_the_window_tests():
    text = open(BAT, encoding="utf-8").read()
    assert 'if /i "%~1"=="quick"' in text
    assert 'python -m pytest -q -m "not windows"' in text, "build.bat quick leaves out the window tests"
    full = [line for line in lines() if line.startswith("python -m pytest")]
    assert "python -m pytest -q" in full, "a plain build.bat still runs everything"
    assert first(lambda line: "pytest" in line) < first(lambda line: "PyInstaller" in line), "tests before the build"


def test_both_manuals_go_in_the_release():
    text = open(BAT, encoding="utf-8").read()
    assert r'build_manual.py "dist\24bit7\24bit7_Manual.pdf"' in text
    assert r'build_manual.py --lang de "dist\24bit7\24bit7_Handbuch.pdf"' in text, "the German manual is in the zip too"


def test_window_tests_are_labelled():
    """What build.bat quick leaves out: every test that opens windows, and nothing else."""
    import subprocess
    import sys
    repo = os.path.dirname(BAT)

    def collected(mark):
        out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", mark,
                              "-p", "no:cacheprovider"], cwd=repo, capture_output=True, text=True).stdout
        return {line.split("::")[0].replace("\\", "/") for line in out.splitlines() if "::" in line}
    windows, quick = collected("windows"), collected("not windows")
    for name in ("test_gui.py", "test_tray_maximised.py", "test_flat_borders.py", "test_discover_rounded.py"):
        assert f"tests/{name}" in windows and f"tests/{name}" not in quick, name
    for name in ("test_engine.py", "test_tidal_output.py", "test_build_bat.py", "test_name_rules.py"):
        assert f"tests/{name}" in quick and f"tests/{name}" not in windows, name
