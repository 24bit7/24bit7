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


def test_keeps_closing_until_no_copy_is_left():
    """24bit7 starts its Multiroom follower once more if that dies while it's wanted, so one pass could leave a
    follower born as its parent closed: it kept a file open and PyInstaller couldn't clear the folder, which
    failed the 1.33.0 build after every test had passed (10 Nov 2026). The close step goes round until none is left."""
    close = lines()[first(lambda l: "Stop-Process" in l)]
    assert "foreach ($round in 1..5)" in close and "if (-not $open) { break }" in close, close
    assert close.index("Get-Process 24bit7") > close.index("foreach ($round"), "each round looks again"


def test_opens_the_new_24bit7_after_publishing():
    publish = first(lambda l: "release.ps1" in l)
    reopen = first(lambda l: l.startswith("if exist") and "start " in l and r"dist\24bit7\24bit7.exe" in l)
    done = first(lambda l: l == "echo Build complete.")
    assert publish < reopen < done


PARALLEL = 'python -m pytest -q -m "not windows and not timing" -n 6'
TIMING = 'python -m pytest -q -m "timing and not windows"'
WINDOWS = 'python -m pytest -q -m "windows"'


def test_tests_run_in_three_passes_and_quick_skips_only_the_windows():
    """14 Nov 2026: the windowless tests six at a time, the timing ones on their own, then the window tests one at
    a time; build.bat quick stops before the window pass. Each pass stops the build when it fails."""
    run = lines()
    for cmd in (PARALLEL, TIMING, WINDOWS):
        i = run.index(cmd)
        assert run[i + 1] == "if errorlevel 1 goto tests_failed", f"a failure in {cmd!r} must stop the build"
    quick = run.index('if /i "%~1"=="quick" goto tests_passed')
    assert run.index(PARALLEL) < run.index(TIMING) < quick < run.index(WINDOWS), "quick leaves out only the windows"
    assert run.index(r"python -m pip install -q -r tests\requirements.txt") < run.index(PARALLEL), "xdist installed"
    failed = run.index(":tests_failed")
    assert run[failed + 1:failed + 5] == ["echo.", "echo Tests FAILED, so nothing was built. Fix them and run "
                                          "build.bat again.", "pause", "exit /b 1"]
    assert run.index(":tests_passed") > failed
    assert first(lambda line: "pytest" in line) < first(lambda line: "PyInstaller" in line), "tests before the build"


def test_every_test_runs_in_exactly_one_pass():
    """No test falls between build.bat's passes or runs twice: the three marker choices cover the whole suite."""
    import subprocess
    import sys
    repo = os.path.dirname(BAT)

    def collected(mark):
        out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", mark,
                              "-p", "no:cacheprovider"], cwd=repo, capture_output=True, text=True).stdout
        return {line for line in out.splitlines() if "::" in line}
    every = collected("windows or not windows")
    passes = [collected(p.split('-m "')[1].split('"')[0]) for p in (PARALLEL, TIMING, WINDOWS)]
    assert sum(len(p) for p in passes) == len(every) and set().union(*passes) == every
    assert any("test_sonos_clock.py" in t for t in passes[1]) and any("test_follower.py" in t for t in passes[1])


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
