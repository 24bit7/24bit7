"""
24bit7 - Console Query.

Asks Claude about what's in the console: why a playlist came out the way it did,
and which settings to change. Claude is sent the console, the current settings
(every key, token, password and user name left out), what's playing, and
24bit7's own code and README so it knows the rules and the on-screen names.

The code is read from this folder when running from source. The packaged app
downloads it once from GitHub, at the tag matching this version (main if the tag
isn't there yet), and keeps it in query_cache next to the app.

Off by default: Settings > Other > Enable Console Query.
"""

import os
import re
import sys
import threading

import requests

import engine

QUERY_MODEL = "claude-haiku-4-5-20251001"   # the same model as AI Moderator
REPO_RAW = "https://raw.githubusercontent.com/24bit7/24bit7/{ref}/{path}"
CODE_FILES = ("engine.py", "playmix.py", "README.md")
SECRET = re.compile(r"KEY|TOKEN|SECRET|PASS|USER", re.I)   # settings never sent
CONSOLE_LIMIT = 60000   # characters of console sent, the most recent kept

HINT = ("Try: Why was this track included?   Why was the playlist so short?   "
        "What did the AI Moderator remove?   Which settings would give me more variety?")

SYSTEM = """You help someone get the best out of 24bit7, a Windows app that builds playlists from \
their own JRiver music library (Similar Artists, Similar Tracks, Artist's Top Tracks, Vibe Playlist), \
with optional voice control. Below are 24bit7's code and README. With each question you also get the \
app's console (its log), the person's current settings, and what's playing.

Answer the question they actually asked:
- A question about music itself (which album a song is from, who wrote it, when it came out): answer \
from your own knowledge, opening with "From general knowledge:", then add anything useful the console \
shows, such as which sources suggested the track or whether it's in their library. If you're not sure \
of a fact, say so rather than guess.
- A question about how 24bit7 behaved (why a track was included or left out, why a playlist was \
short, what the AI Moderator did): explain what most likely happened from the console and the rules \
in the code, saying when you're inferring. Then recommend up to three changes that would help.

Only recommend changes when the question is about how 24bit7 behaved, or when one would clearly help. \
Name controls exactly as the app shows them, for example "Settings > Playlist > Similar Tracks > \
Drift", and only name a control you can see in the code or README; if you're not sure one exists, \
describe what to look for instead. Only give a .env name if there's no on-screen control.

If the console doesn't hold enough to answer a 24bit7 question, say what's likely and suggest \
switching the console to Advanced (its Simple/Advanced box) and building the playlist again. Keep answers short. Plain text only: no \
bold, no italics, no headings, no asterisks; use "- " for a list. Plain British English. No em dashes."""


def _cache_dir():
    return os.path.join(engine.APP_DIR, "query_cache", engine.VERSION)


def _read_code_file(name):
    """One of 24bit7's own files: from this folder when running from source, else GitHub (cached)."""
    if not getattr(sys, "frozen", False):
        local = os.path.join(os.path.dirname(os.path.abspath(engine.__file__)), name)
        if os.path.isfile(local):
            with open(local, encoding="utf-8", errors="replace") as f:
                return f.read()
    cached = os.path.join(_cache_dir(), name)
    if os.path.isfile(cached):
        with open(cached, encoding="utf-8", errors="replace") as f:
            return f.read()
    for ref in (f"v{engine.VERSION}", "main"):
        try:
            r = requests.get(REPO_RAW.format(ref=ref, path=name), timeout=20)
        except requests.RequestException:
            continue
        if r.status_code == 200 and r.text:
            try:
                os.makedirs(_cache_dir(), exist_ok=True)
                with open(cached, "w", encoding="utf-8") as f:
                    f.write(r.text)
            except OSError:
                pass
            return r.text
    return None


def _code_bundle():
    parts = []
    for name in CODE_FILES:
        text = _read_code_file(name)
        if text:
            parts.append(f"===== {name} =====\n{text}")
    return "\n\n".join(parts)


def settings_text():
    """The current settings as KEY=value lines, leaving out anything secret."""
    lines = []
    try:
        with open(engine.ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if SECRET.search(key):
                    continue
                lines.append(f"{key.strip()}={value.strip()}")
    except OSError:
        pass
    return "\n".join(lines)


def plain(text):
    """The console shows plain text, so any markdown that slips through is taken out."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)            # bold
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)   # italics
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)           # headings
    text = re.sub(r"^(\s*)\* ", r"\1- ", text, flags=re.M)        # "* " list markers
    return re.sub(r"\s*\u2014\s*", ", ", text)                          # em dashes


def ask(question, console_text, playing, on_done):
    """
    Asks in the background; on_done(answer, error) is called from that thread
    with one of the two set. The code goes in a cached block, so follow-up
    questions within a few minutes cost much less than the first.
    """
    def work():
        try:
            import anthropic
        except ImportError:
            on_done(None, "the anthropic package isn't installed")
            return
        code = _code_bundle()
        if not code:
            on_done(None, "24bit7's code couldn't be read (no copy here and GitHub didn't answer)")
            return
        playing_line = "Nothing playing"
        if playing:
            playing_line = (f"{playing.get('Artist', '?')} - {playing.get('Name', '?')} "
                            f"(album: {playing.get('Album', '?')})")
        console = console_text[-CONSOLE_LIMIT:] if console_text else "(the console is empty)"
        user = (f"24bit7 version: {engine.VERSION}\n\n"
                f"Current settings:\n{settings_text()}\n\n"
                f"Playing now: {playing_line}\n\n"
                f"Console:\n{console}\n\n"
                f"Question: {question}")
        try:
            client = anthropic.Anthropic(api_key=engine.ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=QUERY_MODEL, max_tokens=1200,
                system=[{"type": "text", "text": SYSTEM},
                        {"type": "text", "text": code, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}])
            answer = "".join(b.text for b in message.content if getattr(b, "type", "") == "text").strip()
            answer = plain(answer)
            on_done(answer or "(no answer came back)", None)
        except Exception as e:
            text = str(e)
            if "credit balance" in text.lower():
                on_done(None, "your Anthropic credit balance is too low")
            else:
                on_done(None, text[:200])

    threading.Thread(target=work, daemon=True).start()
