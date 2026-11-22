"""
Update Now (17 Nov 2026, Ben): 24bit7 downloads the newest release beside its own folder, checks it against the
fingerprint published with it and unpacks it; update.ps1 then swaps the folders, keeping the old copy as a backup and
everything of yours, and puts the old copy back if anything goes wrong. Nothing here touches the internet or a real
24bit7: the downloads are stood in for, and the script runs on throwaway folders without starting anything.
"""

import hashlib
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "update.ps1"
INFO = {"latest": "99.0.0", "zip": "https://github.com/24bit7/24bit7/releases/download/v99.0.0/24bit7-v99.0.0-windows.zip",
        "sha256": "https://github.com/24bit7/24bit7/releases/download/v99.0.0/24bit7-v99.0.0-windows.zip.sha256",
        "link": "https://github.com/24bit7/24bit7/releases/tag/v99.0.0", "releases": [("99.0.0", "")]}


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def release(app, tmp_path, monkeypatch):
    """A release zip as build.bat makes it (a 24bit7 folder at the top), served by stand-in downloads."""
    e = app.engine
    home = tmp_path / "home" / "24bit7"
    home.mkdir(parents=True)
    monkeypatch.setattr(e, "APP_DIR", str(home))
    built = tmp_path / "built.zip"
    st = {"sha": make_zip(built, {"24bit7/24bit7.exe": "new", "24bit7/_internal/lib.txt": "new"})}
    monkeypatch.setattr(e, "_download", lambda url, path: Path(path).write_bytes(built.read_bytes()))
    monkeypatch.setattr(e, "_download_text", lambda url: f"{st['sha']}  24bit7-v99.0.0-windows.zip\n")
    return st, built, home


def test_the_release_is_downloaded_checked_and_unpacked_beside_this_copy(app, release):
    _, _, home = release
    new = app.engine.prepare_update(INFO, app.printed)
    assert new and Path(new, "24bit7.exe").read_text() == "new"
    assert Path(new).is_relative_to(home.parent / "24bit7 update 99.0.0"), new
    assert app.printed.has("Checked: it's the release GitHub published.")


def test_a_download_that_doesnt_match_its_fingerprint_is_refused(app, release):
    st, _, home = release
    st["sha"] = "0" * 64
    assert app.engine.prepare_update(INFO, app.printed) is None
    assert app.printed.has("doesn't match the fingerprint") and app.printed.has("Nothing was changed.")
    assert not (home.parent / "24bit7 update 99.0.0").exists(), "nothing is left behind"


def test_a_file_that_would_land_outside_the_folder_is_refused(app, release):
    st, built, _ = release
    st["sha"] = make_zip(built, {"24bit7/24bit7.exe": "new", "../../evil.txt": "x"})
    assert app.engine.prepare_update(INFO, app.printed) is None
    assert app.printed.has("would land outside its folder")


def test_update_now_is_only_offered_for_the_built_program_with_a_fingerprint(app, monkeypatch):
    assert not app.engine.can_update(INFO), "running from source"
    monkeypatch.setattr(app.engine.sys, "frozen", True, raising=False)
    assert app.engine.can_update(INFO)
    assert not app.engine.can_update(dict(INFO, sha256=""))


def test_the_next_start_says_how_it_went_once(app, tmp_path, monkeypatch):
    e = app.engine
    monkeypatch.setattr(e, "APP_DIR", str(tmp_path))
    (tmp_path / "update_result.txt").write_text("\ufeffok\t1.37.2\tC:\\Music\\24bit7 1.37.2 backup\n", encoding="utf-8")
    e.say_update_outcome(app.printed)
    assert app.printed.has(f"Updated to {e.VERSION}. Your old copy is in C:\\Music\\24bit7 1.37.2 backup")
    assert not (tmp_path / "update_result.txt").exists()
    e.say_update_outcome(app.printed)
    assert app.printed.text().count("Updated to") == 1
    (tmp_path / "update_result.txt").write_text("failed\tthe old copy couldn't be moved aside", encoding="utf-8")
    e.say_update_outcome(app.printed)
    assert app.printed.has("The update didn't finish (the old copy couldn't be moved aside), and your antivirus may")


# --- update.ps1 itself, on throwaway folders ---------------------------------------------------------------------

def lay_out(tmp_path):
    app_dir = tmp_path / "Music" / "24bit7"
    for name, text in {"24bit7.exe": "old", ".env": "LASTFM=mine", "24bit7.db": "history", "profiles/Evening.env": "p",
                       "logs/today.log": "log", "_internal/lib.txt": "old", "24bit7_Manual.pdf": "old manual"}.items():
        (app_dir / name).parent.mkdir(parents=True, exist_ok=True)
        (app_dir / name).write_text(text)
    work = tmp_path / "Music" / "24bit7 update 99.0.0"
    new = work / "new" / "24bit7"
    for name, text in {"24bit7.exe": "new", "_internal/lib.txt": "new", "24bit7_Manual.pdf": "new manual"}.items():
        (new / name).parent.mkdir(parents=True, exist_ok=True)
        (new / name).write_text(text)
    return app_dir, work, new


def run_script(app_dir, work, new):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                           "-AppDir", str(app_dir), "-NewDir", str(new), "-WorkDir", str(work), "-Version", "99.0.0",
                           "-OldVersion", "1.37.2", "-NoStart", "-NoPause"],
                          capture_output=True, text=True, timeout=120,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def test_the_script_swaps_the_folders_and_keeps_everything_of_yours(tmp_path):
    app_dir, work, new = lay_out(tmp_path)
    r = run_script(app_dir, work, new)
    assert r.returncode == 0, r.stdout + r.stderr
    backup = tmp_path / "Music" / "24bit7 1.37.2 backup"
    assert (app_dir / "24bit7.exe").read_text() == "new" and (app_dir / "_internal/lib.txt").read_text() == "new"
    assert (app_dir / "24bit7_Manual.pdf").read_text() == "new manual", "what the release ships is the new one's"
    for name, text in {".env": "LASTFM=mine", "24bit7.db": "history", "profiles/Evening.env": "p",
                       "logs/today.log": "log"}.items():
        assert (app_dir / name).read_text() == text, name
    assert (backup / "24bit7.exe").read_text() == "old" and (backup / ".env").exists(), "the old copy is whole"
    result = (app_dir / "update_result.txt").read_text(encoding="utf-8-sig").strip()
    assert result == f"ok\t1.37.2\t{backup}", result
    assert not work.exists(), "the download is cleared away"


def test_the_script_puts_the_old_copy_back_when_the_new_one_is_missing(tmp_path):
    app_dir, work, new = lay_out(tmp_path)
    new.rename(new.parent / "elsewhere")   # the new copy has gone
    r = run_script(app_dir, work, new)
    assert r.returncode == 1, r.stdout + r.stderr
    assert (app_dir / "24bit7.exe").read_text() == "old" and (app_dir / ".env").read_text() == "LASTFM=mine"
    assert not (tmp_path / "Music" / "24bit7 1.37.2 backup").exists()
    assert (app_dir / "update_result.txt").read_text(encoding="utf-8-sig").startswith("failed\t")
    assert not work.exists(), "a failed update clears its download away too"


def test_an_older_backup_of_the_same_version_is_never_overwritten(tmp_path):
    app_dir, work, new = lay_out(tmp_path)
    (tmp_path / "Music" / "24bit7 1.37.2 backup").mkdir()
    assert run_script(app_dir, work, new).returncode == 0
    assert (tmp_path / "Music" / "24bit7 1.37.2 backup (2)" / "24bit7.exe").read_text() == "old"


def test_the_script_downloads_nothing_and_runs_only_24bit7():
    text = SCRIPT.read_text(encoding="ascii")   # plain ASCII, so Windows PowerShell 5.1 reads it as written
    for word in ("Invoke-WebRequest", "Invoke-RestMethod", "DownloadFile", "Invoke-Expression", "iex ",
                 "-EncodedCommand", "WindowStyle Hidden"):
        assert word not in text, word
    assert text.count("Start-Process") == 1 and "24bit7.exe" in text


def test_the_build_ships_the_updater_and_publishes_the_fingerprint():
    root = SCRIPT.parent
    build = (root / "build.bat").read_text(encoding="utf-8")
    assert '--add-data "update.ps1;."' in build, "Update Now runs the update.ps1 that came with the program"
    publish = (root / "release.ps1").read_text(encoding="utf-8")
    assert "Get-FileHash -Algorithm SHA256" in publish and "gh release create $tag $Zip $sha" in publish


# --- the update window in the user's language (22 Nov 2026) ----------------------------------------------

def said_in_the_script():
    """Every line the script says, as written in it: Say '...' or Say "...", and the window's title."""
    import re
    text = SCRIPT.read_text(encoding="ascii")
    lines = re.findall(r"""^\s*Say (?:'([^']*)'|"([^"]*)")""", text, re.M)
    title = re.search(r"WindowTitle = \(Line '([^']*)'", text).group(1)
    return [title] + [a or b for a, b in lines]


def test_every_line_the_script_says_is_handed_over_in_the_chosen_language(app, tmp_path):
    e = app.engine
    said = said_in_the_script()
    assert len(said) == 10 and sorted(said) == sorted(e.UPDATE_LINES), \
        "a line in update.ps1 that isn't in engine.UPDATE_LINES would stay English for everyone"
    import i18n
    i18n.set_language("de")
    try:
        path = e.write_update_texts(str(tmp_path))
    finally:
        i18n.set_language("en")
    import json
    texts = json.loads(open(path, encoding="utf-8").read())
    assert texts["Putting your old copy back."] == "Deine alte Kopie wird zurückgestellt."
    assert set(texts) == set(e.UPDATE_LINES) and all(v and v != k for k, v in texts.items()), "each has its German"


def test_the_script_speaks_the_language_its_handed_and_english_without(tmp_path):
    import json
    app_dir, work, new = lay_out(tmp_path)
    texts = tmp_path / "texts.json"
    texts.write_text(json.dumps({"Updating 24bit7 from {old} to {new}.": "Von {old} auf {new}, bitte.",
                                 "Your old copy is kept as {folder}.": "Alte Kopie: {folder}."}), encoding="utf-8")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
                        "-AppDir", str(app_dir), "-NewDir", str(new), "-WorkDir", str(work), "-Version", "99.0.0",
                        "-OldVersion", "1.37.2", "-Texts", str(texts), "-NoStart", "-NoPause"],
                       capture_output=True, text=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Von 1.37.2 auf 99.0.0, bitte." in r.stdout and "Alte Kopie: 24bit7 1.37.2 backup." in r.stdout, r.stdout
    assert "Starting 24bit7 99.0.0." in r.stdout, "a line that wasn't handed over is said in English"
    # and with nothing handed over, or a file that can't be read, the lot in English
    app_dir, work, new = lay_out(tmp_path / "again")
    r = run_script(app_dir, work, new)
    assert r.returncode == 0 and "Updating 24bit7 from 1.37.2 to 99.0.0." in r.stdout, r.stdout + r.stderr
