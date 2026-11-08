"""
24bit7 - Console Query.

Asks Claude about what's in the console: why a playlist came out the way it did,
and which settings to change. Claude is sent the console, what's playing, the
settings as builds use them (every playlist with its configs and filters, Simple
or Advanced, the More Options switches, Radio, and .env with every key, token,
password and user name left out), and 24bit7's manual in the language the app is
in, so it knows the rules and names controls as the screens do.

Before 1.31.0 (8 Nov 2026) it was sent engine.py and the README and only .env: since
1.29 most settings live with each playlist in the database, the rules had moved
out of engine.py, and the screens' names were in neither.

The manual is read from this folder when running from source. The packaged app
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
import i18n
from i18n import N_

# The provider's main model, as AI Playlist uses (Ben, 8 Nov 2026): three real tries on the quick one had the facts
# right but kept naming settings by their internal names and wandering to playlists that hadn't built. With the
# manual in place of the code, a first question still costs about half what it did on the quick model before.
QUERY_TIER = "main"
REPO_RAW = "https://raw.githubusercontent.com/24bit7/24bit7/{ref}/{path}"
MANUALS = {"en": "docs/MANUAL.md", "de": "docs/MANUAL.de.md"}   # the reference, in the app's language
SECRET = re.compile(r"KEY|TOKEN|SECRET|PASS|USER", re.I)   # settings never sent
CONSOLE_LIMIT = 60000   # characters of console sent, the most recent kept

HINT = N_("Try: Why was this track included?   Why was the playlist so short?   "
          "What did the Moderator remove?   Which settings would give me more variety?")

SYSTEM = """You help someone get the best out of 24bit7, a Windows app that builds playlists from \
their own JRiver music library, with optional voice control through an Alexa skill. Below is 24bit7's \
manual, in the language the app is shown in. With each question you also get the app's console (its \
log), what's playing, and the settings as 24bit7's builds use them.

How 24bit7 is set up, so your answers fit:
- Each playlist button (Similar Artists, Artist's Top Tracks, Radio, Consensus, Artist + Guests, or one \
the person made) has its own page under Settings > Playlist Settings, and a device's own playlists are \
under Settings > Devices. A playlist has one config or more, each with its own kind (Artist Matching, \
Track Matching, Artist's Top Tracks, AI Playlist), settings and filters; Mix says how they come together. \
Radio has stations and pillar artists instead of configs, one set of settings for every Radio button.
- A playlist's own settings are what its builds use. The .env lines are defaults and app-wide settings \
(sources, Discover, voice): a playlist's own setting beats them.
- While the More Options row on the Play tab is open, its Moderator, Deep Cuts and Non-stop switches \
beat every playlist's own settings. The settings say whether it's open.
- Simple mode runs one config per playlist and leaves the advanced sections off in every build. In \
Simple, only suggest an advanced section (Moderator, Drift, Deep Cuts, Non-stop, Consensus, Hidden \
Tracks, If All Else Fails, Run After Building, Shortcut, a second config) by saying it needs Advanced, \
the Simple / Advanced switch at the top right of a playlist's page.
- Filters are kept under Settings > Filters (Edit Filters) and ticked per config; one with Every \
playlist applies to every build. Skipped Tracks leaves out what's been skipped by voice.
- 24bit7 is honest about results: a seed that finds little gives a short playlist and says so. \
Fallbacks (If All Else Fails, Consensus's plain Artist Matching finish) are opt-in. Don't present a \
fallback as something that happened unless the console shows it.
- Each config's "as its page shows it" line gives its Moderator, Deep Cuts, Drift and Non-stop as the screen names them. Trust it over your own reading of the internal names.
- A setting a playlist doesn't list is at its default, as the manual gives it (Match Tempo starts Off, for example). Never suggest setting something to the value it already has, and only suggest a change that the console or the settings give a reason for; don't guess at what an unlisted setting might be doing.
- The settings use internal names (SIMILAR_LIMIT and the like). Work out the control from the manual \
and name that; never tell the person to edit a setting's internal name or .env unless the manual has \
no control for it.

Answer the question they actually asked:
- A question about music itself (which album a song is from, who wrote it, when it came out): answer \
from your own knowledge, opening with "From general knowledge:", then add anything useful the console \
shows, such as which sources suggested the track or whether it's in their library. If you're not sure \
of a fact, say so rather than guess.
- A question about how 24bit7 behaved (why a track was included or left out, why a playlist was \
short, what the Moderator did): explain what most likely happened from the console, the settings and \
the manual, saying when you're inferring. The console's heading names the playlist that built; look \
at that playlist's own settings, not .env's. Then recommend up to three changes that would help.
- A request for recommendations (more variety, fewer repeats, a better evening playlist): suggest up \
to three changes, each saying where it is and what to set it to, and why, from their actual settings.

Only recommend changes when the question is about how 24bit7 behaved, asks for recommendations, or \
when one would clearly help. Name each control exactly as the manual does, with its full place and the \
playlist and config it belongs to, for example "Settings > Playlist Settings > Artist + Guests > \
Config 2 > Playlist Selection > Limit To". Say what it's set to now and what to change it to. Only name \
a control the manual describes; if you're not sure one exists, say what to look for instead.

If the console doesn't hold enough to answer a 24bit7 question, say what's likely and suggest \
switching the console to Advanced (its Simple/Advanced box) and building the playlist again. Keep \
answers short. Plain text only: no bold, no italics, no headings, no asterisks; use "- " for a list. \
Plain British English. No em dashes."""


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
    """The manual in the app's language (the English one if that can't be read): the rules and the screens' names."""
    for name in dict.fromkeys((MANUALS.get(i18n.LANGUAGE, MANUALS["en"]), MANUALS["en"])):
        text = _read_code_file(name)
        if text:
            return f"===== 24bit7's manual =====\n{text}"
    return ""


def _shown(settings):
    """A settings dict as KEY=value, secrets left out."""
    return ", ".join(f"{k}={v}" for k, v in sorted((settings or {}).items()) if not SECRET.search(str(k))) or "(as the defaults)"


def page_view(button, cfg):
    """
    A config's Moderator, Deep Cuts, Drift and Non-stop as its page names them ("Drift Spread"), worked out the
    way builds read them, so the AI needn't decode DRIFT_TRACKS=1 and DRIFT_TRACKS_FROM=spread (the second real
    try, 8 Nov 2026, read Drift as off when it was Spread). Non-stop is the playlist's, the rest the config's.
    """
    import overrides
    settings = cfg.get("settings") or {}
    switches = overrides.from_playlist(dict(button, kind=cfg["kind"], settings=settings))
    label = lambda v: overrides.LABELS.get(v, v)   # the English names, as the manual gives them
    parts = [f"Moderator {label(switches['moderator'])}", f"Deep Cuts {label(switches['deep_cuts'])}"]
    group = {"artists": "ARTISTS", "tracks": "TRACKS", "vibe": "VIBE"}.get(cfg["kind"])
    if group:
        merged = dict(overrides._env(), **settings)
        on = str(merged.get(f"DRIFT_{group}") or "").strip().lower() in ("1", "true", "yes")
        close = str(merged.get(f"DRIFT_{group}_FROM") or "spread").strip().lower() == "close"
        parts.append("Drift " + ("Off" if not on else "Keep It Tight" if close else "Spread"))
    parts.append(f"Non-stop {label(switches['nonstop'])}")
    return ", ".join(parts)


def state_text():
    """
    The settings as builds use them, beyond .env: Simple or Advanced, the More Options switches, every playlist
    with its configs, filters and mix, the filters themselves, Radio, and Play & Embellish's amounts. Each part
    on its own, so one that can't be read leaves the others.
    """
    out = []

    def part(fn):
        try:
            out.extend(fn())
        except Exception as e:
            engine.debug(f"Console Query: part of the settings couldn't be read: {e}")

    def mode_lines():
        import mode
        import overrides
        lines = [f"Mode: {'Simple' if mode.is_simple() else 'Advanced'}"]
        lines.append("More Options row: open, its switches beat every playlist's own: " + overrides.summary()
                     if overrides.active() else "More Options row: closed (each playlist's own settings apply)")
        return lines

    def filter_lines():
        import filters
        items = filters.load()
        names = {x["id"]: x["name"] for x in items}
        state_text.filter_names = names
        lines = ["Filters (Settings > Filters):"]
        for x in items:
            lines.append(f"- {x['name']}: {'on' if x.get('on') else 'off'}"
                         f"{', every playlist' if x.get('every') else ''}; {filters.describe(x)}")
        return lines if len(lines) > 1 else ["Filters: none"]

    def playlist_lines():
        import buttons
        import devices
        names = getattr(state_text, "filter_names", {})
        items = buttons.load()
        by_id = {b["id"]: b["name"] for b in items}
        lines = ["Playlists:"]
        for b in items:
            where = f"the device {devices.name_of(b['device'])}'s own" if b.get("device") else "a button"
            if b.get("parent"):
                where += f", in {by_id.get(b['parent'], 'another')}'s menu"
            kind = "Radio" if buttons.is_radio(b) else ("blank" if b.get("kind") is None else "playlist")
            lines.append(f"- {b['name']} ({kind}, {where}{', the shipped standard' if b.get('standard') else ''})")
            if buttons.is_radio(b):
                lines.append(f"    Radio settings: {_shown(b.get('settings'))}; station: {b.get('lane') or 'the last played'}")
                continue
            cfgs = buttons.configs(b)
            for n, c in enumerate(cfgs, start=1):
                kind_name = buttons.KIND_LABELS.get(c["kind"], c["kind"])
                ticked = ", ".join(names.get(str(i), str(i)) for i in c.get("filters") or []) or "none"
                try:
                    lines.append(f"    Config {n}, {kind_name}, as its page shows it: {page_view(b, c)}")
                except Exception as e:
                    engine.debug(f"Console Query: {b['name']} config {n}'s switches couldn't be read: {e}")
                lines.append(f"    Config {n}, {kind_name}, every setting: {_shown(c.get('settings'))}; filters ticked: {ticked}")
            if len(cfgs) > 1:
                lines.append(f"    Mix: {b.get('mix')}")
        return lines

    def radio_lines():
        import radio
        result = radio.analysis()
        if result is None:
            return ["Radio: no stations yet"]
        if result.get("resting"):
            return [f"Radio: resting until there's more play history ({result['resting']})"]
        lines = ["Radio stations (share of plays, pillars):"]
        for x in radio.lanes():
            pillars = ", ".join(x.get("pillars") or [])
            lines.append(f"- {x['name']}: {radio.share(x)}%, pillars {pillars or 'none'}")
        return lines

    def embellish_lines():
        import embellish
        a = embellish.amounts()
        return [f"Play & Embellish: the arrow offers {', '.join(a['shown'])}; the button runs {a['default']}"]

    for fn in (mode_lines, filter_lines, playlist_lines, radio_lines, embellish_lines):
        part(fn)
    return "\n".join(out)


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
        engine.refresh_settings_if_changed()
        if engine.AI_PROVIDER == "ollama":
            on_done(None, "Console Query isn't available with Ollama: it sends the console and 24bit7's manual, "
                          "far more than a local model can hold")
            return
        if engine.AI_PROVIDER == "anthropic":
            try:
                import anthropic
            except ImportError:
                on_done(None, "the anthropic package (needed for Anthropic) isn't installed")
                return
        code = _code_bundle()
        if not code:
            on_done(None, "24bit7's manual couldn't be read (no copy here and GitHub didn't answer)")
            return
        playing_line = "Nothing playing"
        if playing:
            playing_line = (f"{playing.get('Artist', '?')} - {playing.get('Name', '?')} "
                            f"(album: {playing.get('Album', '?')})")
        console = console_text[-CONSOLE_LIMIT:] if console_text else "(the console is empty)"
        user = (f"24bit7 version: {engine.VERSION}\n\n"
                f"Settings as builds use them:\n{state_text()}\n\n"
                f".env (defaults and app-wide settings):\n{settings_text()}\n\n"
                f"Playing now: {playing_line}\n\n"
                f"Console:\n{console}\n\n"
                f"Question: {question}")
        try:
            if engine.AI_PROVIDER == "anthropic":   # the code in a cached block: follow-ups cost a tenth
                client = anthropic.Anthropic(api_key=engine.ANTHROPIC_API_KEY)
                # thinking off, as every other Claude call: Sonnet 5 thinks by default and the first real try on it
                # (8 Nov 2026) spent all of max_tokens thinking and answered nothing
                message = engine._ai_create(
                    client, "Console Query", announce=False, model=engine.AI_MODELS["anthropic"][0], max_tokens=1200,
                    system=[{"type": "text", "text": SYSTEM + i18n.reply_line()},
                            {"type": "text", "text": code, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user}])
                answer = "".join(b.text for b in message.content if getattr(b, "type", "") == "text").strip()
            else:   # OpenAI and Gemini cache a repeated start of a request by themselves
                answer = engine.ai_request(user, 1200, "Console Query", tier=QUERY_TIER,
                                           system=f"{SYSTEM}{i18n.reply_line()}\n\n{code}", announce=False).text.strip()
            answer = plain(answer)
            on_done(answer or "(no answer came back)", None)
        except Exception as e:
            on_done(None, engine.ai_credit_text() if engine.ai_out_of_credit(e) else str(e)[:200])

    threading.Thread(target=work, daemon=True).start()
