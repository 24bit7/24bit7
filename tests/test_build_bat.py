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
