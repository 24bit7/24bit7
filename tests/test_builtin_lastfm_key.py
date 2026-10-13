"""
The release comes with a Last.fm key built in (build.bat packs it from Ben's .env
into builtin_keys.py, never in git). A user's own key wins. A fresh install finds
similar artists with Last.fm and similar tracks with Last.fm and YouTube.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_built_in_key_is_used_when_the_user_has_none(app, monkeypatch):
    monkeypatch.setattr(app.engine, "BUILTIN_LASTFM_KEY", "built-in")
    app.set_env(LASTFM_API_KEY="")
    assert app.engine.LASTFM_KEY == "built-in"
    assert app.engine.source_has_key("lastfm")


def test_the_users_own_key_wins(app, monkeypatch):
    monkeypatch.setattr(app.engine, "BUILTIN_LASTFM_KEY", "built-in")
    app.set_env(LASTFM_API_KEY="mine")
    assert app.engine.LASTFM_KEY == "mine"


def test_no_key_at_all_from_source(app):
    assert app.engine.BUILTIN_LASTFM_KEY == "", "tests never pick up a real packed key"
    app.set_env(LASTFM_API_KEY="")
    assert not app.engine.LASTFM_KEY


def test_the_packed_key_is_read_from_builtin_keys(app):
    (app.folder / "builtin_keys.py").write_text('LASTFM_API_KEY = "packed123"\n', encoding="utf-8")
    sys.modules.pop("builtin_keys", None)
    try:
        assert app.engine._builtin_key("LASTFM_API_KEY") == "packed123"
    finally:
        sys.modules.pop("builtin_keys", None)


def test_a_fresh_install_starts_on_lastfm_and_youtube(app):
    os.remove(app.folder / ".env")
    app.engine.ensure_env_exists()
    app.engine.load_settings()
    assert app.engine.SIMILAR_SOURCES == ["lastfm"]
    assert app.engine.SIMILAR_TRACK_SOURCES == ["lastfm", "youtube"]


def test_build_bat_packs_the_key_for_the_build_only():
    with open(os.path.join(REPO, "build.bat"), encoding="utf-8") as f:
        text = f.read()
    write = text.index("Set-Content -Path 'builtin_keys.py'")
    build = text.index("python -m PyInstaller")
    remove = text.index('del "builtin_keys.py"')
    assert text.index("python -m pytest") < write < build < remove, "packed after the tests, removed after the build"
    assert "--hidden-import builtin_keys" in text
    assert "No Last.fm key in .env" in text, "a release never goes out without the key"


def test_the_packed_key_never_goes_in_git():
    with open(os.path.join(REPO, ".gitignore"), encoding="utf-8") as f:
        assert "builtin_keys.py" in f.read().split()
