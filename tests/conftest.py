"""
24bit7 test suite - fixtures.

Each test gets its own copy of 24bit7 in a temporary folder, with its own .env
and empty 24bit7.db, freshly imported, so nothing one test does can leak into
the next, and your real settings and database are never opened.
"""

import importlib
import importlib.machinery
import importlib.util
import os
import shutil
import socket
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fakes  # noqa: E402

APP_MODULES = ["engine", "library", "voice", "saved_playlists", "nonstop", "playmix", "filters", "buildlog", "blend",
               "console_query", "ai_usage", "support_gui", "window_chrome", "hotkeys", "tray", "tabs", "mix_gui", "review_gui", "profiles", "discover_gui", "settings_gui", "gui"]

BASE_ENV = {
    "JRIVER_HOST": fakes.JRIVER_HOST, "JRIVER_USER": "", "JRIVER_PASS": "",
    "LASTFM_API_KEY": "test-lastfm", "LISTENBRAINZ_TOKEN": "test-lb", "DISCOGS_TOKEN": "",
    "ANTHROPIC_API_KEY": "test-anthropic",
    "SIMILAR_SOURCES": "lastfm,deezer,listenbrainz", "TOP_TRACK_SOURCES": "lastfm",
    "SIMILAR_MIN_AGREEMENT": "1", "SIMILAR_TRACK_SOURCES": "lastfm,listenbrainz",
    "SIMILAR_TRACK_MIN_AGREEMENT": "1", "SIMILAR_ARTIST_LIMIT": "20", "SIMILAR_ARTIST_TRACK_COUNT": "30",
    "SIMILAR_TRACK_COUNT": "30", "SIMILAR_TRACK_PER_ARTIST": "3", "TOP_TRACKS_COUNT": "10",
    "VIBE_TRACK_COUNT": "20", "AI_MODERATOR": "0", "MODERATOR_WARNED": "1",
    "OUTPUT_TARGET": "jriver", "DEFAULT_ZONE": "Speakers", "FOLLOW_ACTIVE_ZONE": "0",
    "VOICE_ENABLED": "1", "VOICE_KEY": "test-voice-key", "START_IN_TRAY": "0", "CLOSE_TO_TRAY": "0",
    "CONSOLE_MODE": "advanced", "CACHE_DAYS": "30", "THEME": "dark",
}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def write_env(path, values):
    with open(path, "w", encoding="utf-8") as f:
        for k, v in values.items():
            f.write(f"{k}={v}\n")


class Lines(list):
    """A report function that keeps every line, for checking what the console would show."""
    def __call__(self, line=""):
        self.append(str(line))

    def text(self):
        return "\n".join(self)

    def has(self, fragment):
        return any(fragment in line for line in self)


@pytest.fixture
def app(tmp_path, monkeypatch):
    folder = tmp_path / "24bit7"
    folder.mkdir()
    for name in os.listdir(REPO):
        if name.endswith((".py", ".pyw", ".ico", ".md")) and not name.startswith("apply_"):
            shutil.copy2(os.path.join(REPO, name), folder / name)
    shutil.copytree(os.path.join(REPO, "alexa"), folder / "alexa")
    env = dict(BASE_ENV, VOICE_PORT=str(free_port()))
    write_env(folder / ".env", env)

    for mod in APP_MODULES:
        sys.modules.pop(mod, None)
    monkeypatch.syspath_prepend(str(folder))
    monkeypatch.chdir(folder)
    for k in list(os.environ):
        if k in env or k.startswith(("SKIP_", "DRIFT_", "NONSTOP", "RUN_AFTER", "AI_", "SIMILAR_", "TOP_", "SWITCH_", "CACHE_")):
            monkeypatch.delenv(k, raising=False)

    jriver = fakes.FakeJRiver()
    web = fakes.FakeWeb(jriver)
    ai = fakes.FakeAI(web)
    yt = fakes.FakeYTMusic(web)
    fakes.install(monkeypatch, jriver, web)
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", ai.Client)
    import ytmusicapi
    monkeypatch.setattr(ytmusicapi, "YTMusic", lambda *a, **k: yt)

    engine = importlib.import_module("engine")
    monkeypatch.setattr(engine, "MUSICBRAINZ_INTERVAL", 0)
    tray = importlib.import_module("tray")   # Start with Windows: never the real registry
    startup = {"command": None}
    monkeypatch.setattr(tray, "startup_command", lambda: startup["command"])
    monkeypatch.setattr(tray, "set_startup",
                        lambda on: startup.update(command=tray.launch_command() if on else None))
    printed = Lines()
    engine.OUTPUT_HOOK = printed
    library = importlib.import_module("library")
    voice = importlib.import_module("voice")
    saved_playlists = importlib.import_module("saved_playlists")

    def set_env(**values):
        env.update({k: str(v) for k, v in values.items()})
        write_env(folder / ".env", env)
        os.utime(folder / ".env", None)
        for k in values:
            os.environ.pop(k, None)
        engine.load_settings()

    ns = SimpleNamespace(folder=folder, env=env, set_env=set_env, engine=engine, library=library, voice=voice,
                         saved_playlists=saved_playlists, jriver=jriver, web=web, ai=ai, yt=yt, printed=printed,
                         Lines=Lines)
    yield ns
    try:
        voice.stop()
    except Exception:
        pass
    try:
        library.stop()
    except Exception:
        pass
    if engine._db is not None:
        engine._db.close()


def load_gui(folder):
    """Imports gui.pyw (no .py extension) as the module 'gui'."""
    loader = importlib.machinery.SourceFileLoader("gui", str(folder / "gui.pyw"))
    spec = importlib.util.spec_from_loader("gui", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gui"] = mod
    loader.exec_module(mod)
    return mod
