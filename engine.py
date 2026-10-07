import os
import sys
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import time
import random
import re
import csv
import unicodedata
import json
import contextlib
import sqlite3
from datetime import datetime


def app_dir():
    """
    The folder the app lives in, whether running as plain Python or as a
    frozen (PyInstaller) build. All data files (.env, database, legacy CSV)
    are anchored here, so launching from a shortcut, the taskbar or another
    working directory always finds the same files.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = app_dir()
VERSION = "1.14.0"
ENV_FILE = os.path.join(APP_DIR, ".env")
ACTIVE_ZONE = "-1"      # MCWS shorthand for whichever zone JRiver has active
SEED_ZONE_NAME = None   # the Now Playing tab's Zone choice; None = active zone. Set by the GUI, never saved
OUTPUT_OVERRIDE = None  # a zone name that beats the Output setting for one run (voice commands)
MODERATOR_OVERRIDE = None  # True/False beats the AI_MODERATOR setting for one run
PROFILE = {}               # a device's own Sources/Playlist settings, laid over .env for its voice commands

# The settings a device can have its own copy of (Settings > Sources and Playlist, device tabs)
PROFILE_KEYS = {
    "sources": ["SIMILAR_SOURCES", "SIMILAR_MIN_AGREEMENT", "LISTENBRAINZ_ALGORITHM", "SIMILAR_TRACK_SOURCES",
                "SIMILAR_TRACK_MIN_AGREEMENT", "LISTENBRAINZ_TRACK_ALGORITHM", "TOP_TRACK_SOURCES", "AI_MODERATOR",
                "AI_MODERATOR_ARTISTS", "AI_MODERATOR_TRACKS"],
    "playlist": ["SIMILAR_ARTIST_TRACK_COUNT", "SIMILAR_ARTIST_TRACK_LIMIT", "SIMILAR_ARTIST_LIMIT",
                 "TRACKS_PER_ARTIST_POOL",
                 "TRACKS_PER_ARTIST_PICK", "SIMILAR_TRACK_COUNT", "SIMILAR_TRACK_PER_ARTIST", "SIMILAR_TRACK_ORDER",
                 "SIMILAR_TRACK_VARIETY",
                 "TOP_TRACKS_COUNT", "TOP_TRACKS_ORDER", "VIBE_TRACK_COUNT",
                 "DRIFT_ARTISTS", "DRIFT_ARTISTS_USING", "DRIFT_ARTISTS_ROUNDS",
                 "DRIFT_TRACKS", "DRIFT_TRACKS_USING", "DRIFT_TRACKS_ROUNDS",
                 "DRIFT_VIBE", "DRIFT_VIBE_USING", "DRIFT_VIBE_ROUNDS", "AI_MODERATOR_VIBE",
                 *[f"DRIFT_{g}_{part}" for g in ("ARTISTS", "TRACKS", "VIBE")
                   for part in ("SOURCES_MODE", "ARTIST_SOURCES", "ARTIST_AGREE", "TRACK_SOURCES", "TRACK_AGREE")],
                 "SKIP_LONG_CLOSERS", "LONG_CLOSER_MINUTES",
                 "SKIP_PLAYED_ARTISTS", "SKIP_PLAYED_ARTISTS_DAYS", "SKIP_PLAYED_TRACKS", "SKIP_PLAYED_TRACKS_DAYS",
                 "SKIP_PLAYED_TOP", "SKIP_PLAYED_TOP_DAYS", "SKIP_PLAYED_VIBE", "SKIP_PLAYED_VIBE_DAYS",
                 "NONSTOP", "NONSTOP_USING", "NONSTOP_RESEED", "NONSTOP_TOP_REST", "NONSTOP_TOP_REST_COUNT",
                 "NONSTOP_VIBE",
                 "NONSTOP_ARTISTS", "NONSTOP_ARTISTS_USING", "NONSTOP_ARTISTS_RESEED",
                 "NONSTOP_TRACKS", "NONSTOP_TRACKS_USING", "NONSTOP_TRACKS_RESEED",
                 "NONSTOP_TOP", "NONSTOP_TOP_USING", "NONSTOP_TOP_RESEED", "NONSTOP_VIBE_RESEED", "NONSTOP_VIBE_WITH",
                 "SKIP_LONG_CLOSERS_ARTISTS", "LONG_CLOSER_MINUTES_ARTISTS", "SKIP_LONG_CLOSERS_TRACKS",
                 "LONG_CLOSER_MINUTES_TRACKS", "SKIP_LONG_CLOSERS_TOP", "LONG_CLOSER_MINUTES_TOP",
                 "SKIP_LONG_CLOSERS_VIBE", "LONG_CLOSER_MINUTES_VIBE",
                 "RUN_AFTER_ARTISTS", "RUN_AFTER_ARTISTS_PATH", "RUN_AFTER_TRACKS", "RUN_AFTER_TRACKS_PATH",
                 "RUN_AFTER_TOP", "RUN_AFTER_TOP_PATH", "RUN_AFTER_VIBE", "RUN_AFTER_VIBE_PATH"],
}
PLAYED_GROUPS = ("artists", "tracks", "top", "vibe")   # Similar Artists, Similar Tracks, Artist's Top Tracks, Vibe
CSV_FILE = os.path.join(APP_DIR, "FutureDiscoveries.csv")      # legacy log, imported once into the database
DB_FILE = os.path.join(APP_DIR, "24bit7.db")

_env_mtime = None   # modification time of .env when settings were last loaded

# Discover search sites. Stores are searched by artist + track; reference
# sites by artist only (for a discography). Listed alphabetically by label.
STORE_OPTIONS = [
    ("7digital",   "7digital"),
    ("amazon",     "Amazon"),
    ("bandcamp",   "Bandcamp"),
    ("beatport",   "Beatport"),
    ("bleep",      "Bleep"),
    ("discogs",    "Discogs marketplace"),
    ("hdtracks",   "HDtracks"),
    ("hiresaudio", "HighResAudio"),
    ("juno",       "Juno"),
    ("qobuz",      "Qobuz"),
]
REFERENCE_OPTIONS = [
    ("allmusic",    "AllMusic"),
    ("discogs_ref", "Discogs"),
    ("musicbrainz", "MusicBrainz"),
    ("wikipedia",   "Wikipedia"),
]
STORE_CODES = [c for c, _ in STORE_OPTIONS]
REFERENCE_CODES = [c for c, _ in REFERENCE_OPTIONS]
# "Listen" sites are searched by artist + track, like the stores, but aren't shops.
LISTEN_OPTIONS = [
    ("youtube", "YouTube"),
]
LISTEN_CODES = [c for c, _ in LISTEN_OPTIONS]
CUSTOM_SITE_SLOTS = 3   # rows offered under Settings > Search > Custom sites


def _int_setting(name, default, lo, hi):
    """Reads an integer setting from .env, clamped to a range, falling back to the default."""
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        print(f"Note: the setting {name}='{raw}' isn't a number, so {default} is used.")
        value = default
    return max(lo, min(hi, value))


def read_custom_sites():
    """
    The user's own Discover search sites, from CUSTOM_SITE_<n>_NAME / _URL / _MODE
    in .env. Read straight from the file (not the environment) so a row that has
    been cleared in Settings disappears without a restart. Only web links count.
    Returns [{"name", "url", "mode"}], mode being "track" or "artist".
    """
    try:
        from dotenv import dotenv_values
        values = dotenv_values(ENV_FILE)
    except Exception:
        values = {}
    sites = []
    for n in range(1, CUSTOM_SITE_SLOTS + 1):
        name = (values.get(f"CUSTOM_SITE_{n}_NAME") or "").strip()
        url = (values.get(f"CUSTOM_SITE_{n}_URL") or "").strip()
        mode = (values.get(f"CUSTOM_SITE_{n}_MODE") or "track").strip().lower()
        if name and url.lower().startswith(("http://", "https://")):
            sites.append({"name": name, "url": url, "mode": "artist" if mode == "artist" else "track"})
    return sites


YES = ("1", "true", "yes")
NO = ("0", "false", "no")


def nonstop_settings(get):
    """
    Non-stop per Play option, from a getter (os.getenv, or a dict's get):
    {group: {"on", "using", "reseed"}}, plus "with" for Vibe. The single
    Non-stop section of the first 1.6.0 build (NONSTOP, NONSTOP_USING,
    NONSTOP_RESEED, NONSTOP_VIBE) carries over as every option's starting value.
    """
    legacy_on = (get("NONSTOP", "0") or "0").strip().lower() in YES
    legacy_using = (get("NONSTOP_USING", "") or "").strip().lower()
    legacy_reseed = (get("NONSTOP_RESEED", "") or "").strip().lower()
    out = {}
    for group, own in (("artists", "artists"), ("tracks", "tracks"), ("top", "tracks"), ("vibe", "artists")):
        name = f"NONSTOP_{group.upper()}"
        raw = (get(name, "") or "").strip().lower()
        on = raw in YES if raw in YES + NO else legacy_on
        using = (get(f"{name}_USING", "") or legacy_using or own).strip().lower()
        reseed = (get(f"{name}_RESEED", "") or legacy_reseed or "last").strip().lower()
        mode = (get(f"{name}_MODE", "") or "").strip().lower()
        out[group] = {"on": on, "using": using if using in ("artists", "tracks") else own,
                      "reseed": "second" if reseed == "second" else "last",
                      "mode": "tight" if mode == "tight" else "journey"}   # Keep It Tight / Wander
    with_ = (get("NONSTOP_VIBE_WITH", "") or "").strip().lower()
    legacy_with = (get("NONSTOP_VIBE", "") or "").strip().lower()
    if not with_ and legacy_with in ("vibe", "artists", "tracks"):
        with_ = legacy_with
    out["vibe"]["with"] = with_ if with_ in ("vibe", "artists", "tracks") else "vibe"
    return out


def closer_settings(get):
    """The hidden-track check per Play option: {group: (on, minutes)}. The old single setting is the starting value."""
    base_on = (get("SKIP_LONG_CLOSERS", "1") or "1").strip().lower() in YES
    base_minutes = (get("LONG_CLOSER_MINUTES", "6") or "6").strip()
    out = {}
    for group in PLAYED_GROUPS:
        raw = (get(f"SKIP_LONG_CLOSERS_{group.upper()}", "") or "").strip().lower()
        minutes = (get(f"LONG_CLOSER_MINUTES_{group.upper()}", "") or base_minutes).strip()
        minutes = min(30, max(3, int(minutes))) if minutes.isdigit() else 6
        out[group] = (raw in YES if raw in YES + NO else base_on, minutes)
    return out


MODERATOR_GROUPS = ("artists", "tracks")   # not Top Tracks (one artist) or Vibe (the AI picks every track)


MODERATOR_LEVELS = ("off", "relaxed", "balanced", "strict")


def moderator_level_value(raw, fallback="off"):
    """A stored moderator setting as a level. Older Yes/No values: Yes is Balanced, No is Off."""
    raw = (raw or "").strip().lower()
    if raw in MODERATOR_LEVELS:
        return raw
    if raw in YES:
        return "balanced"
    if raw in NO:
        return "off"
    return fallback


def moderator_settings(get):
    """The AI Moderator level per Play option: {group: level}. The old single tick is the starting value."""
    base = moderator_level_value(get("AI_MODERATOR", "0"))
    levels = {group: moderator_level_value(get(f"AI_MODERATOR_{group.upper()}", ""), base)
              for group in MODERATOR_GROUPS}
    levels["vibe"] = moderator_level_value(get("AI_MODERATOR_VIBE", ""))   # AI Playlist's Drift tracks only
    return levels


def load_settings():
    """
    (Re)reads every setting from .env into module-level globals. Called once at
    import and again by refresh_settings_if_changed() whenever .env is edited,
    so both the GUI and the CLI pick up changes without a restart.
    """
    global AUTH, JRIVER_HOST, JRIVER_BASE, LASTFM_KEY, LISTENBRAINZ_TOKEN
    global DISCOGS_TOKEN, ANTHROPIC_API_KEY
    global SIMILAR_SOURCES, TOP_TRACK_SOURCES, LISTENBRAINZ_ALGORITHM_SETTING
    global DIGITAL_STORES, REFERENCE_SITES, DEBUG, SIMILAR_ARTIST_LIMIT, TRACKS_PER_ARTIST_POOL
    global SIMILAR_MIN_AGREEMENT
    global SIMILAR_TRACK_SOURCES, SIMILAR_TRACK_MIN_AGREEMENT, SIMILAR_TRACK_COUNT
    global SIMILAR_TRACK_PER_ARTIST, SIMILAR_TRACK_ORDER, SIMILAR_TRACK_VARIETY
    global LISTENBRAINZ_TRACK_ALGORITHM_SETTING
    global TRACKS_PER_ARTIST_PICK, TOP_TRACKS_COUNT, TOP_TRACKS_ORDER, CACHE_DAYS, CACHE_KEEP
    global TABLE_FONT_SIZE, VIBE_TRACK_COUNT
    global OUTPUT_TARGET, YOUTUBE_PLAYLIST_LENGTH, HIDDEN_ZONES, DEFAULT_ZONE, FOLLOW_ACTIVE_ZONE
    global PREFER_OFFICIAL_VIDEOS, THEME
    global VOICE_ENABLED, VOICE_KEY, VOICE_PORT
    global START_IN_TRAY, CLOSE_TO_TRAY
    global LISTEN_SITES, CUSTOM_SITES
    global SKIP_LONG_CLOSERS, LONG_CLOSER_MINUTES
    global SIMILAR_ARTIST_TRACK_COUNT, SIMILAR_ARTIST_TRACK_LIMIT, DRIFT
    global AI_MODERATOR, MODERATOR_WARNED, SKIP_PLAYED
    global NONSTOP, NONSTOP_USING, NONSTOP_RESEED, NONSTOP_TOP_REST, NONSTOP_TOP_REST_COUNT, NONSTOP_VIBE
    global NONSTOP_BY, LONG_CLOSERS, AI_MODERATOR_BY, RUN_AFTER
    global CONSOLE_QUERY

    load_dotenv(ENV_FILE, override=True)
    os.environ.update(PROFILE)   # a device's own settings, for the voice command being built

    AUTH = (os.getenv("JRIVER_USER"), os.getenv("JRIVER_PASS"))
    JRIVER_HOST = os.getenv("JRIVER_HOST", "127.0.0.1:52199")
    JRIVER_BASE = f"http://{JRIVER_HOST}/MCWS/v1"
    LASTFM_KEY = os.getenv("LASTFM_API_KEY")
    LISTENBRAINZ_TOKEN = os.getenv("LISTENBRAINZ_TOKEN")
    DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    SIMILAR_SOURCES = [x.strip().lower() for x in os.getenv("SIMILAR_SOURCES", "lastfm").split(",") if x.strip()]
    TOP_TRACK_SOURCES = [x.strip().lower() for x in os.getenv("TOP_TRACK_SOURCES", "lastfm").split(",") if x.strip()]
    LISTENBRAINZ_ALGORITHM_SETTING = os.getenv("LISTENBRAINZ_ALGORITHM", "alltime").strip().lower()
    # Discover search sites. DIGITAL_STORES replaced the single DIGITAL_STORE in
    # 1.1.0; an old .env with only DIGITAL_STORE is carried over.
    stores_raw = os.getenv("DIGITAL_STORES")
    if stores_raw is None:
        stores_raw = os.getenv("DIGITAL_STORE", "bandcamp")
    DIGITAL_STORES = [x.strip().lower() for x in stores_raw.split(",") if x.strip()]
    DIGITAL_STORES = [x for x in DIGITAL_STORES if x in STORE_CODES] or ["bandcamp"]
    REFERENCE_SITES = [x.strip().lower() for x in os.getenv("REFERENCE_SITES", "").split(",") if x.strip()]
    REFERENCE_SITES = [x for x in REFERENCE_SITES if x in REFERENCE_CODES]
    # Listen sites: YouTube is on unless it has been unticked (it needs no account)
    listen_raw = os.getenv("LISTEN_SITES")
    if listen_raw is None:
        listen_raw = "youtube"
    LISTEN_SITES = [x.strip().lower() for x in listen_raw.split(",") if x.strip().lower() in LISTEN_CODES]
    CUSTOM_SITES = read_custom_sites()
    DEBUG = True   # always recorded since 1.11.0: the console's Simple/Advanced switch shows or hides them
    CONSOLE_QUERY = os.getenv("CONSOLE_QUERY", "0").strip().lower() in ("1", "true", "yes")   # off by default
    # How many similar-artist sources must suggest an artist before it is used
    # (1 = off). Replaced the on/off SIMILAR_REQUIRE_AGREEMENT; an old .env
    # carries over as on -> 2, off -> 1.
    if os.getenv("SIMILAR_MIN_AGREEMENT", "").strip():
        SIMILAR_MIN_AGREEMENT = _int_setting("SIMILAR_MIN_AGREEMENT", 2, 1, 5)
    else:
        legacy_on = os.getenv("SIMILAR_REQUIRE_AGREEMENT", "1").strip().lower() in ("1", "true", "yes")
        SIMILAR_MIN_AGREEMENT = 2 if legacy_on else 1

    # Similar Tracks: its own sources (lastfm, listenbrainz, youtube), agreement and playlist settings
    SIMILAR_TRACK_SOURCES = [x.strip().lower() for x in
                             os.getenv("SIMILAR_TRACK_SOURCES", "lastfm,listenbrainz,youtube").split(",")
                             if x.strip().lower() in ("ai", "lastfm", "listenbrainz", "youtube")]
    SIMILAR_TRACK_MIN_AGREEMENT = _int_setting("SIMILAR_TRACK_MIN_AGREEMENT", 2, 1, 4)
    SIMILAR_TRACK_COUNT = _int_setting("SIMILAR_TRACK_COUNT", 30, 5, 100)
    SIMILAR_TRACK_PER_ARTIST = _int_setting("SIMILAR_TRACK_PER_ARTIST", 3, 1, 20)
    LISTENBRAINZ_TRACK_ALGORITHM_SETTING = os.getenv("LISTENBRAINZ_TRACK_ALGORITHM", "alltime").strip().lower()
    SIMILAR_TRACK_ORDER = os.getenv("SIMILAR_TRACK_ORDER", "shuffled").strip().lower()
    if SIMILAR_TRACK_ORDER not in ("shuffled", "similar first"):
        SIMILAR_TRACK_ORDER = "shuffled"
    # Variety: yes picks at random from a wider pool, no takes the closest matches in order
    SIMILAR_TRACK_VARIETY = os.getenv("SIMILAR_TRACK_VARIETY", "no").strip().lower() not in ("no", "0", "false")

    SIMILAR_ARTIST_LIMIT = _int_setting("SIMILAR_ARTIST_LIMIT", 20, 1, 50)
    SIMILAR_ARTIST_TRACK_COUNT = _int_setting("SIMILAR_ARTIST_TRACK_COUNT", 30, 5, 100)
    # Limit total tracks to: unticked, every track found goes in
    SIMILAR_ARTIST_TRACK_LIMIT = os.getenv("SIMILAR_ARTIST_TRACK_LIMIT", "1").strip().lower() in ("1", "true", "yes")
    # Drift, per Play mode group: on/off, what it drifts using, and how many rounds.
    # An older .env with Similar Tracks' "Top up from Similar Artists" ticked carries
    # over as Drift on for Similar Tracks, using similar artists, one round (the same thing).
    DRIFT = {}
    yes = ("1", "true", "yes")
    for group, own in (("artists", "artists"), ("tracks", "tracks"), ("vibe", "artists")):
        name = f"DRIFT_{group.upper()}"
        raw = os.getenv(name, "").strip().lower()
        using = os.getenv(f"{name}_USING", own).strip().lower()
        rounds = _int_setting(f"{name}_ROUNDS", 3, 1, 6)
        if raw:
            on = raw in yes
        elif group == "tracks" and os.getenv("SIMILAR_TRACK_TOPUP", "").strip().lower() in yes:
            on, using, rounds = True, "artists", 1
        else:
            on = False
        ok = ("artists", "tracks", "ai") if group == "vibe" else ("artists", "tracks")   # AI only for vibe
        DRIFT[group] = {"on": on, "using": using if using in ok else own, "rounds": rounds}
        # Drift From (where each round seeds from) and its own AI Moderator level
        frm = os.getenv(f"{name}_FROM", "spread").strip().lower()
        DRIFT[group]["from"] = "close" if frm == "close" else "spread"   # Keep It Tight; Last Round became Spread
        mod = os.getenv(f"{name}_MODERATOR", "same").strip().lower()
        DRIFT[group]["moderator"] = mod if mod in ("same",) + MODERATOR_LEVELS else "same"
        # Drift sources: the same as Settings > Sources, or Custom Sources of its own
        DRIFT[group]["custom"] = os.getenv(f"{name}_SOURCES_MODE", "same").strip().lower() == "custom"
        for kind, most in (("artist", 5), ("track", 3)):
            DRIFT[group][f"{kind}_sources"] = [
                x.strip().lower() for x in os.getenv(f"{name}_{kind.upper()}_SOURCES", "").split(",")
                if x.strip() and x.strip().lower() != "ai"]   # Drift from the sources never uses the AI
            DRIFT[group][f"{kind}_agree"] = _int_setting(f"{name}_{kind.upper()}_AGREE", 1, 1, most)
    TRACKS_PER_ARTIST_POOL = _int_setting("TRACKS_PER_ARTIST_POOL", 5, 1, 20)
    TRACKS_PER_ARTIST_PICK = _int_setting("TRACKS_PER_ARTIST_PICK", 3, 1, 20)
    TOP_TRACKS_COUNT = _int_setting("TOP_TRACKS_COUNT", 10, 1, 20)
    TOP_TRACKS_ORDER = os.getenv("TOP_TRACKS_ORDER", "popular").strip().lower()
    if TOP_TRACKS_ORDER not in ("popular", "reverse", "random"):
        print(f"Note: the setting TOP_TRACKS_ORDER='{TOP_TRACKS_ORDER}' isn't recognised, so 'popular' is used.")
        TOP_TRACKS_ORDER = "popular"
    # How long answers are reused: 1 Month, 1 Year or Permanent (an older CACHE_DAYS carries over)
    CACHE_KEEP = os.getenv("CACHE_KEEP", "").strip().lower()
    if CACHE_KEEP not in ("month", "year", "permanent"):
        CACHE_KEEP = "month" if _int_setting("CACHE_DAYS", 30, 1, 3650) <= 30 else "year"
    CACHE_DAYS = {"month": 30, "year": 365}.get(CACHE_KEEP)   # None: kept until cleared
    TABLE_FONT_SIZE = _int_setting("TABLE_FONT_SIZE", 9, 6, 16)   # Discover table font
    VIBE_TRACK_COUNT = _int_setting("VIBE_TRACK_COUNT", 20, 5, 100)  # target size for vibe playlists
    # Hidden-track check: leave out an album's last track when it runs longer than this
    # AI Moderator (Play tab Yes/No) and whether its one-off credits warning has been shown
    AI_MODERATOR = moderator_level_value(os.getenv("AI_MODERATOR", "0"))
    MODERATOR_WARNED = os.getenv("MODERATOR_WARNED", "0").strip().lower() in ("1", "true", "yes")
    # Skip tracks played recently, per Play mode group: {group: (on, days)}
    SKIP_PLAYED = {}
    for group in PLAYED_GROUPS:
        name = f"SKIP_PLAYED_{group.upper()}"
        SKIP_PLAYED[group] = (os.getenv(name, "0").strip().lower() in ("1", "true", "yes"),
                              _int_setting(f"{name}_DAYS", 1, 1, 365))
    # Non-stop (Settings > Playlist): top up a 24bit7 playlist when its last track starts
    NONSTOP = os.getenv("NONSTOP", "0").strip().lower() in ("1", "true", "yes")
    NONSTOP_USING = "artists" if os.getenv("NONSTOP_USING", "tracks").strip().lower() == "artists" else "tracks"
    NONSTOP_RESEED = "second" if os.getenv("NONSTOP_RESEED", "last").strip().lower() == "second" else "last"
    NONSTOP_TOP_REST = os.getenv("NONSTOP_TOP_REST", "1").strip().lower() in ("1", "true", "yes")
    raw_rest = os.getenv("NONSTOP_TOP_REST_COUNT", "20").strip().lower()
    NONSTOP_TOP_REST_COUNT = 0 if raw_rest == "unlimited" else (max(1, int(raw_rest)) if raw_rest.isdigit() else 20)
    NONSTOP_VIBE = os.getenv("NONSTOP_VIBE", "vibe").strip().lower()
    if NONSTOP_VIBE not in ("vibe", "artists", "tracks"):
        NONSTOP_VIBE = "vibe"
    SKIP_LONG_CLOSERS = os.getenv("SKIP_LONG_CLOSERS", "1").strip().lower() in ("1", "true", "yes")
    LONG_CLOSER_MINUTES = _int_setting("LONG_CLOSER_MINUTES", 6, 3, 30)
    # Per Play option (the tabs under Settings > Sources and Playlist)
    NONSTOP_BY = nonstop_settings(os.getenv)
    LONG_CLOSERS = closer_settings(os.getenv)
    AI_MODERATOR_BY = moderator_settings(os.getenv)
    # Run After Building (Settings > Playlist): a file to run once a playlist is in JRiver
    RUN_AFTER = {g: (os.getenv(f"RUN_AFTER_{g.upper()}", "0").strip().lower() in ("1", "true", "yes"),
                     os.getenv(f"RUN_AFTER_{g.upper()}_PATH", "").strip().strip('"'))
                 for g in PLAYED_GROUPS}
    # Where finished playlists go: "jriver" = Same zone (the default), "zone:<name>"
    # = a named JRiver zone, or "youtube" (opens in the browser). Zone names keep
    # their case, as JRiver's do.
    raw_output = os.getenv("OUTPUT_TARGET", "jriver").strip()
    if raw_output.lower().startswith("zone:") and raw_output[5:].strip():
        OUTPUT_TARGET = "zone:" + raw_output[5:].strip()
    else:
        OUTPUT_TARGET = raw_output.lower()
        if OUTPUT_TARGET not in ("jriver", "youtube"):
            OUTPUT_TARGET = "jriver"
    # Zones hidden from the Play tab's Zone and Output lists (names separated by |)
    HIDDEN_ZONES = {x.strip() for x in os.getenv("HIDDEN_ZONES", "").split("|") if x.strip()}
    # The zone Now Playing opens on at launch; blank means JRiver's active zone.
    # FOLLOW_ACTIVE_ZONE=1 makes Now Playing track JRiver's active zone instead.
    DEFAULT_ZONE = os.getenv("DEFAULT_ZONE", "").strip()
    FOLLOW_ACTIVE_ZONE = os.getenv("FOLLOW_ACTIVE_ZONE", "0").strip().lower() in ("1", "true", "yes")
    # Voice commands (Settings > Voice): the listener only ever binds to 127.0.0.1
    VOICE_ENABLED = os.getenv("VOICE_ENABLED", "0").strip().lower() in ("1", "true", "yes")
    VOICE_KEY = os.getenv("VOICE_KEY", "").strip()
    VOICE_PORT = _int_setting("VOICE_PORT", 52180, 1024, 65535)
    # Tray (Settings > Other > Windows): start hidden when Windows launches it, and X hides rather than quits
    START_IN_TRAY = os.getenv("START_IN_TRAY", "1").strip().lower() in ("1", "true", "yes")
    CLOSE_TO_TRAY = os.getenv("CLOSE_TO_TRAY", "0").strip().lower() in ("1", "true", "yes")
    YOUTUBE_PLAYLIST_LENGTH = _int_setting("YOUTUBE_PLAYLIST_LENGTH", 50, 5, 50)   # YouTube caps a link at 50
    # Settings > Other: use the artist's official music video instead of the audio-only upload
    PREFER_OFFICIAL_VIDEOS = os.getenv("PREFER_OFFICIAL_VIDEOS", "0").strip().lower() in ("1", "true", "yes")
    # Settings > Other: light or dark, applied when the app starts
    THEME = "dark" if os.getenv("THEME", "light").strip().lower() == "dark" else "light"


def use_profile(values=None):
    """
    Lays a device's own settings over .env until called again with None: the
    voice command's build then reads them like any other setting. Builds run
    one at a time on the Play tab's worker, so only one profile is ever in use.
    """
    global PROFILE
    for key in PROFILE:
        os.environ.pop(key, None)   # .env's own value (if any) comes back with the reload
    PROFILE = {k: str(v) for k, v in (values or {}).items() if k in PROFILE_KEYS["sources"] + PROFILE_KEYS["playlist"]}
    load_settings()


def profile_values(kind):
    """Windows (Main)'s current settings of one kind, as .env strings (unset ones left out)."""
    return {k: os.environ[k] for k in PROFILE_KEYS[kind] if k in os.environ}


def refresh_settings_if_changed():
    """Reloads settings if .env has been edited since we last read it. Cheap timestamp check."""
    global _env_mtime
    try:
        mtime = os.path.getmtime(ENV_FILE)
    except OSError:
        return
    if mtime != _env_mtime:
        load_settings()
        _env_mtime = mtime


FIRST_RUN = False   # True when this launch created a fresh .env (new install)

DEFAULT_ENV = """# 24bit7 settings. Edit through the app's Settings tab (recommended) or here.

# JRiver connection. Media Network must be enabled in JRiver
# (Tools > Options > Media Network). User/pass only if you set authentication.
JRIVER_HOST=127.0.0.1:52199
JRIVER_USER=
JRIVER_PASS=

# Service keys. Deezer and YouTube need no keys, so 24bit7 works out of the box.
# The ? buttons in Settings > Keys explain how to get each of these (all free
# except Anthropic, which is pay-as-you-go).
LASTFM_API_KEY=
LISTENBRAINZ_TOKEN=
DISCOGS_TOKEN=
ANTHROPIC_API_KEY=

# Recommendation sources (comma-separated: lastfm, listenbrainz, deezer, ai, youtube)
# youtube is for SIMILAR_SOURCES only and needs no key.
# A fresh install starts on the two sources that need no key. Once you add a
# Last.fm or ListenBrainz key, tick that source under Settings > Sources.
SIMILAR_SOURCES=deezer,youtube
TOP_TRACK_SOURCES=deezer
LISTENBRAINZ_ALGORITHM=alltime
# How many similar-artist sources must agree on an artist (1 = off, up to 5)
SIMILAR_MIN_AGREEMENT=1
# Similar Tracks sources (lastfm, listenbrainz, youtube, ai) and how many must agree on a track
SIMILAR_TRACK_SOURCES=listenbrainz,youtube
SIMILAR_TRACK_MIN_AGREEMENT=2
LISTENBRAINZ_TRACK_ALGORITHM=alltime

# Playlist sizes and order
SIMILAR_ARTIST_LIMIT=20
SIMILAR_ARTIST_TRACK_COUNT=30
# Similar Artists: 1 stops at SIMILAR_ARTIST_TRACK_COUNT tracks, 0 keeps every track found
SIMILAR_ARTIST_TRACK_LIMIT=1
TRACKS_PER_ARTIST_POOL=5
TRACKS_PER_ARTIST_PICK=3
TOP_TRACKS_COUNT=10
TOP_TRACKS_ORDER=popular
VIBE_TRACK_COUNT=20
# AI Moderator: an Anthropic check that drops tracks clashing with the seed's
# tone, energy and mood (0 or 1, set on the Play tab). Needs ANTHROPIC_API_KEY.
AI_MODERATOR=0
MODERATOR_WARNED=0
# Drift: when a playlist comes up short, search again from what was found.
# Per group: on (1) or off (0), using artists or tracks, rounds (1-6)
DRIFT_ARTISTS=0
DRIFT_ARTISTS_USING=artists
DRIFT_ARTISTS_ROUNDS=3
DRIFT_TRACKS=0
DRIFT_TRACKS_USING=tracks
DRIFT_TRACKS_ROUNDS=3
DRIFT_VIBE=0
DRIFT_VIBE_USING=artists
DRIFT_VIBE_ROUNDS=3
# Skip tracks JRiver has played in the last so many days, per Play mode (1 on, 0 off)
SKIP_PLAYED_ARTISTS=0
SKIP_PLAYED_ARTISTS_DAYS=1
SKIP_PLAYED_TRACKS=0
SKIP_PLAYED_TRACKS_DAYS=1
SKIP_PLAYED_TOP=0
SKIP_PLAYED_TOP_DAYS=1
SKIP_PLAYED_VIBE=0
SKIP_PLAYED_VIBE_DAYS=1
# Every playlist: skip an album's last track when it's longer than this many
# minutes, as those files often carry a hidden track after a long silence
SKIP_LONG_CLOSERS=1
LONG_CLOSER_MINUTES=6
SIMILAR_TRACK_COUNT=30
SIMILAR_TRACK_PER_ARTIST=3
SIMILAR_TRACK_ORDER=shuffled
# Similar Tracks variety: yes picks at random (the closest the most likely), no takes the closest in order
SIMILAR_TRACK_VARIETY=no

# Discover search sites (comma-separated). Stores search artist + track, reference
# sites search the artist. One browser tab opens per site.
# Stores: bandcamp, discogs, qobuz, amazon, juno, hdtracks, hiresaudio, 7digital, bleep, beatport
# Reference: wikipedia, discogs_ref, allmusic, musicbrainz
DIGITAL_STORES=bandcamp
REFERENCE_SITES=
# Listen: youtube (searches artist + track). Custom sites are added in Settings > Search.
LISTEN_SITES=youtube

# Output: jriver (Same zone, the default), zone:<JRiver zone name>, or youtube
# (opens an instant playlist in the browser, 5-50 videos). Set from the Play tab.
OUTPUT_TARGET=jriver
YOUTUBE_PLAYLIST_LENGTH=50
# Use official music videos on YouTube where they exist, instead of audio with a cover image (1 or 0)
PREFER_OFFICIAL_VIDEOS=0
# Colour theme: light or dark (Settings > Other)
THEME=light
# JRiver zones hidden from the Play tab's lists, separated by | (Settings > Other)
HIDDEN_ZONES=
# Zone Now Playing opens on (blank = JRiver's active zone), and whether it follows
# JRiver's active zone instead (0 or 1). Both set in Settings > Other.
DEFAULT_ZONE=
FOLLOW_ACTIVE_ZONE=0

# Voice commands (Settings > Voice). The key is made when you switch it on.
VOICE_ENABLED=0
VOICE_KEY=
VOICE_PORT=52180

# Tray (Settings > Other). Start with Windows itself is stored by Windows, not here.
START_IN_TRAY=1
CLOSE_TO_TRAY=0

# Other
CACHE_KEEP=month
TABLE_FONT_SIZE=9
CONSOLE_MODE=simple
"""


def ensure_env_exists():
    """Creates a commented starter .env on a fresh install and flags first run."""
    global FIRST_RUN
    if os.path.isfile(ENV_FILE):
        return
    FIRST_RUN = True
    try:
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write(DEFAULT_ENV)
        print(f"Created a starter settings file: {ENV_FILE}")
    except OSError as e:
        print(f"Problem: couldn't create the settings file {ENV_FILE} ({e}).")


ensure_env_exists()
load_settings()
try:
    _env_mtime = os.path.getmtime(ENV_FILE)
except OSError:
    _env_mtime = None


# --- console output -----------------------------------------------------------
# gui.pyw points OUTPUT_HOOK at its console, so every print() in this module
# (status lines, [AI] messages, [debug] lines) shows in the app. Under pythonw
# there is no stdout, so without this they went nowhere.
OUTPUT_HOOK = None
_builtin_print = print


def print(*args, **kwargs):   # shadows the builtin inside engine only
    if OUTPUT_HOOK is not None:
        try:
            OUTPUT_HOOK(" ".join(str(a) for a in args))
        except Exception:
            pass
    if sys.stdout is not None:
        try:
            _builtin_print(*args, **kwargs)
        except Exception:
            pass


def debug(msg):
    if DEBUG:
        print(f"    [debug] {msg}")


AI_LAST_ERROR = ""   # why the last AI request returned nothing, for the source result lines


def _redact_env_line(line):
    """A .env line with any key, secret, token or password value hidden."""
    if "=" not in line or line.lstrip().startswith("#"):
        return line
    name, value = line.split("=", 1)
    upper = name.strip().upper()
    if any(w in upper for w in ("KEY", "SECRET", "TOKEN", "PASS")):
        value = value.strip()
        return f"{name}={'set (' + str(len(value)) + ' chars)' if value else 'not set'}"
    return line


def diagnostics_text():
    """Version, machine, JRiver, library size and the settings (keys redacted)."""
    import platform
    lines = [f"24bit7 {VERSION}",
             f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             f"Python: {platform.python_version()}  {'frozen' if getattr(sys, 'frozen', False) else 'source'}",
             f"OS: {platform.platform()}",
             f"Folder: {APP_DIR}"]
    try:
        r = requests.get(f"{JRIVER_BASE}/Alive", auth=AUTH, timeout=3)
        m = re.search(r'Name="ProgramVersion">([^<]+)', r.text)
        lines.append(f"JRiver: {m.group(1) if m else 'answered, version not read'}  ({JRIVER_BASE})")
    except Exception as e:
        lines.append(f"JRiver: not reachable at {JRIVER_BASE} ({e.__class__.__name__})")
    try:
        import library
        with library._lock:
            lines.append(f"Library: {len(library._by_key)} tracks, {len(library._playlists)} playlists"
                         + ("" if library._loaded_at else " (not read yet)"))
    except Exception:
        lines.append("Library: not read")
    try:
        row = db().execute("SELECT COUNT(*) FROM cache").fetchone()
        lines.append(f"Provider cache: {row[0]} entries, kept "
                     + ("until cleared" if CACHE_DAYS is None else f"{CACHE_DAYS} days"))
    except Exception:
        pass
    lines.append("")
    lines.append("--- .env (keys and passwords hidden) ---")
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for raw in f:
                raw = raw.rstrip("\n")
                if raw.strip():
                    lines.append(_redact_env_line(raw))
    except OSError:
        lines.append("(no .env file)")
    return "\n".join(lines)


def export_log(console_text):
    """Writes the diagnostics and the console to logs\\24bit7_<date>_<time>.txt; returns the path."""
    folder = os.path.join(APP_DIR, "logs")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"24bit7_{datetime.now().strftime('%Y-%m-%d_%H%M')}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(diagnostics_text())
        f.write("\n\n--- Console ---\n")
        f.write(console_text.rstrip() + "\n")
    return path


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

MULTI_VALUE_SEP = ";"   # JRiver's separator for multi-value fields (Artist, Genre etc.)


def split_values(field):
    """
    Splits a JRiver multi-value field into its parts. JRiver stores several
    values in one field separated by ';' ('Angus Stone;Dope Lemon'), and each
    shows up as its own entry in the column. Returns a list of the non-empty,
    stripped parts, so a plain single value comes back as a one-item list.
    """
    if not field:
        return []
    return [p.strip() for p in str(field).split(MULTI_VALUE_SEP) if p.strip()]


def seed_artists(seed_info):
    """The playing track's artist(s) as a list, one entry per multi-value part."""
    # Library sort-names ("XX, The", "Tribe Called Quest, A") are flipped to their
    # natural form so every source looks up the right act. Library matching is
    # unaffected: normalise_artist() strips the article either way.
    return [deinvert_the(a) for a in split_values(seed_info.get("Artist"))] or ["Unknown"]


# ---------------------------------------------------------------------------
# Database: provider cache, sessions and discoveries (SQLite, no install needed)
# ---------------------------------------------------------------------------

_db = None


def db():
    """Opens the database on first use and creates tables if needed."""
    global _db
    if _db is None:
        _db = sqlite3.connect(DB_FILE, check_same_thread=False)
        _db.execute("""CREATE TABLE IF NOT EXISTS cache (
            source TEXT, kind TEXT, key TEXT, payload TEXT, fetched_at REAL,
            PRIMARY KEY (source, kind, key))""")
        _db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, mode TEXT,
            seed_artist TEXT, seed_track TEXT, seed_album TEXT, sources TEXT, queued INTEGER)""")
        _db.execute("""CREATE TABLE IF NOT EXISTS discoveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER,
            artist TEXT, track TEXT, sources TEXT, found INTEGER)""")
        _db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        _db.commit()
        import_legacy_csv()
    return _db


MB_UNKNOWN_DAYS = 30   # "MusicBrainz doesn't know them" is rechecked after this, even on Permanent
CACHE_AGES = {"month": 30 * 86400, "year": 365 * 86400, "all": None}


def cache_counts():
    """Cached answers: {"month": older than a month, "year": older than a year, "all": every one}."""
    now, con = time.time(), db()
    out = {}
    for which, age in CACHE_AGES.items():
        if age is None:
            out[which] = con.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        else:
            out[which] = con.execute("SELECT COUNT(*) FROM cache WHERE fetched_at < ?", (now - age,)).fetchone()[0]
    return out


def cache_clear(which):
    """Clears cached answers: "month" (older than a month), "year" (older than a year) or "all". Returns how many."""
    age, con = CACHE_AGES.get(which, 0), db()
    if age is None:
        cur = con.execute("DELETE FROM cache")
    else:
        cur = con.execute("DELETE FROM cache WHERE fetched_at < ?", (time.time() - age,))
    con.commit()
    if which == "all":
        _mbid_cache.clear()
    return cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0


def cache_get(source, kind, key):
    """Returns the cached list for (source, kind, key) if younger than CACHE_DAYS (always, on Permanent), else None."""
    row = db().execute("SELECT payload, fetched_at FROM cache WHERE source=? AND kind=? AND key=?",
                       (source, kind, key)).fetchone()
    if not row:
        return None
    if CACHE_DAYS is not None and time.time() - row[1] > CACHE_DAYS * 86400:
        return None
    return json.loads(row[0])


def cache_put(source, kind, key, items):
    db().execute("INSERT OR REPLACE INTO cache (source, kind, key, payload, fetched_at) VALUES (?,?,?,?,?)",
                 (source, kind, key, json.dumps(items), time.time()))
    db().commit()


def cached_call(source, kind, key, fetch_fn):
    """Serves from cache when possible, otherwise calls fetch_fn() and stores a non-empty result."""
    hit = cache_get(source, kind, key)
    if hit is not None:
        debug(f"{source} {kind} for '{key}' served from cache")
        return hit
    items = fetch_fn()
    if items:
        cache_put(source, kind, key, items)
    return items


# ---------------------------------------------------------------------------
# Non-stop: what 24bit7 sent to each zone, so nonstop.py can top it up
# ---------------------------------------------------------------------------
# Every playlist 24bit7 builds is remembered per zone: its tracks and what kind of
# build it was. When the last of those tracks starts, nonstop.py adds more. Music
# you start in JRiver yourself isn't in the list, so non-stop leaves it alone.

import itertools as _itertools
import threading as _threading

NONSTOP_KINDS = {"similar": "artists", "youtube_queue": "artists", "similar_tracks": "tracks",
                 "top_tracks": "top", "vibe": "vibe"}
NONSTOP_CONTEXT = {}     # the build in progress (set by session_start)
RUN_AFTER = {}           # group -> (on, path), from Settings > Playlist > Run After Building
NONSTOP_APPEND = False   # True while a non-stop top-up builds: it only ever adds, never repeats
FILTER_DEVICE = None     # the Alexa device a build is for (None: Windows (Main)), for Settings > Filters
NONSTOP_ZONES = {}       # zone ID -> {"keys", "build", "kind", "vibe", "top_artist", "top_first", "stage", "fired"}
_nonstop_lock = _threading.Lock()
_nonstop_ids = _itertools.count(1)


def nonstop_begin(mode, seed_info=None):
    """Called as each build starts: remembers what kind of build it is."""
    global NONSTOP_CONTEXT
    seed_info = seed_info or {}
    NONSTOP_CONTEXT = {"build": next(_nonstop_ids), "kind": NONSTOP_KINDS.get(mode, "artists"),
                       "vibe": seed_info.get("Name") if mode == "vibe" else None,
                       "top_artist": seed_artists(seed_info)[0] if mode == "top_tracks" else None}


def nonstop_record(zone, keys, append=False, **fields):
    """
    Notes tracks sent to a zone. A fresh playlist (or fields, from a voice shuffle)
    starts a new record; a Drift round or a non-stop top-up adds to it.
    """
    keys = {str(k) for k in keys if k}
    ctx = NONSTOP_CONTEXT
    with _nonstop_lock:
        entry = NONSTOP_ZONES.get(zone)
        fresh = (fields or entry is None or (not append and not NONSTOP_APPEND)
                 or (not NONSTOP_APPEND and entry.get("build") != ctx.get("build")))
        if fresh:
            entry = {"keys": set(), "build": ctx.get("build"), "kind": ctx.get("kind"), "vibe": ctx.get("vibe"),
                     "top_artist": ctx.get("top_artist"), "top_first": ctx.get("top_first"),
                     "stage": "first", "fired": None, "original": set(), "seeded": set()}
            entry.update(fields)
            entry["origin"] = entry.get("kind")   # its Non-stop settings come from the option it started as
            NONSTOP_ZONES[zone] = entry
        elif NONSTOP_APPEND and ctx.get("kind") and entry.get("build") != ctx.get("build"):
            # a top-up build: from here on the zone carries on as that kind of playlist
            entry.update(build=ctx["build"], kind=ctx["kind"], vibe=ctx.get("vibe") or entry.get("vibe"),
                         stage="after")
        entry["keys"] |= keys
        if not NONSTOP_APPEND:   # the original playlist (and its Drift), for Non-stop's Keep It Tight
            entry.setdefault("original", set()).update(keys)


def nonstop_sent(zone):
    """Every track 24bit7 has sent to this zone since its playlist started."""
    with _nonstop_lock:
        entry = NONSTOP_ZONES.get(zone)
        return set(entry["keys"]) if entry else set()


def nonstop_forget(zone):
    """Something else now fills this zone (an album, a song, a saved playlist without Non-stop)."""
    with _nonstop_lock:
        NONSTOP_ZONES.pop(zone, None)


def playing_now_rows(zone):
    """A zone's Playing Now as [{Key, Name, Artist, Album}], in order. [] if unreadable."""
    try:
        r = requests.get(f"{JRIVER_BASE}/Playback/Playlist", params={"Zone": zone, "Fields": "Key,Name,Artist,Album"},
                         auth=AUTH, timeout=10)
        return [{f.get("Name"): f.text or "" for f in item.findall("Field")}
                for item in ET.fromstring(r.text).findall(".//Item")]
    except Exception:
        return []


def seed_from_row(row, zone):
    """A library track shaped like a now-playing seed (left out of its own playlist)."""
    return {"Artist": row.get("Artist") or "Unknown", "Name": row.get("Name") or "Unknown",
            "Album": row.get("Album") or "", "FileKey": str(row.get("Key") or ""),
            "PlayingNowPosition": "0", "PlayingNowTracks": "0", "ZoneID": zone}


BUILD_STARTED = None   # set by the GUI as each build starts, for the Done line's time
LAST_OUTPUT = None     # where the build's tracks went: a zone name, or "YouTube"
LAST_OUTPUT_ID = None  # ...and that zone's JRiver ID, for Non-stop's chain in the console's Log
LAST_BUILD = None      # the finished build's mode, sources, tracks queued and misses, for buildlog
CLOSERS_DROPPED = 0    # tracks the hidden-track check left out when sending, so the Done line counts what went
_SESSION_STARTED = {}


def session_start(mode, seed_info, sources=""):
    globals()["CLOSERS_DROPPED"] = 0
    nonstop_begin(mode, seed_info)
    if output_is_youtube() and not OUTPUT_OVERRIDE:
        globals()["LAST_OUTPUT"] = "YouTube"
    cur = db().execute(
        "INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued) "
        "VALUES (?,?,?,?,?,?,0)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), mode,
         seed_info.get("Artist"), seed_info.get("Name"), seed_info.get("Album"), sources))
    db().commit()
    _SESSION_STARTED[cur.lastrowid] = time.time()
    return cur.lastrowid


def session_log(session_id, artist, track, sources, found):
    if output_is_youtube() and not found:
        return   # nothing was checked against the library, so there is no miss to record
    db().execute("INSERT INTO discoveries (session_id, artist, track, sources, found) VALUES (?,?,?,?,?)",
                 (session_id, artist, track, ", ".join(sources) if isinstance(sources, list) else sources,
                  1 if found else 0))


def session_finish(session_id, queued, sources=None, report=print):
    save_new_mbids()   # MusicBrainz IDs learnt during this run
    queued = max(0, queued - CLOSERS_DROPPED)   # anything the final hidden-track check left out
    if sources is not None:
        db().execute("UPDATE sessions SET sources=? WHERE id=?", (sources, session_id))
    db().execute("UPDATE sessions SET queued=? WHERE id=?", (queued, session_id))
    db().commit()
    misses = db().execute("SELECT COUNT(*) FROM discoveries WHERE session_id=? AND found=0",
                          (session_id,)).fetchone()[0]
    row = db().execute("SELECT mode, sources FROM sessions WHERE id=?", (session_id,)).fetchone() or ("", "")
    globals()["LAST_BUILD"] = {"mode": row[0], "sources": row[1], "queued": queued, "misses": misses}
    report(done_line(queued, misses, _SESSION_STARTED.pop(session_id, None)))
    if not NONSTOP_APPEND:   # every finished build, matches or not (not a non-stop top-up)
        run_after_building(report)


def done_line(queued, misses=0, started=None):
    """The one closing line every build ends with: what went where, what was missing, how long it took."""
    started = BUILD_STARTED or started
    took = f", {max(0, round(time.time() - started))} s" if started else ""
    tracks = f"{queued} track{'' if queued == 1 else 's'}"
    if LAST_OUTPUT == "YouTube":
        return f"Done: {tracks} sent to YouTube{took}."
    if REVIEW_MODE and not VOICE_TAKEOVER:
        return f"Done: {tracks} ready in Review, nothing played. {misses} not in library{took}."
    where = f"{tracks} queued in {LAST_OUTPUT}" if queued and LAST_OUTPUT else (
        f"{tracks} queued" if queued else "nothing queued")
    return f"Done: {where}, {misses} not in library{took}."


def run_after_building(report=print):
    """
    Settings > Playlist > Run After Building: starts the chosen file in the
    background once the playlist is in JRiver. It isn't told anything about the
    playlist. A device with settings of its own uses its own (voice).
    """
    if REVIEW_MODE and not VOICE_TAKEOVER:
        return   # Review: nothing is in JRiver yet
    on, path = RUN_AFTER.get(NONSTOP_CONTEXT.get("kind"), (False, ""))
    if not on or not path:
        return
    if not os.path.isfile(path):
        report(f"  Problem: Run After Building: {path} wasn't found, so nothing ran.")
        return
    import subprocess
    ext = os.path.splitext(path)[1].lower()
    folder = os.path.dirname(path) or None
    hidden = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        if ext in (".bat", ".cmd"):
            subprocess.Popen(["cmd", "/c", path], cwd=folder, creationflags=hidden)
        elif ext == ".ps1":
            subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
                             cwd=folder, creationflags=hidden)
        elif ext in (".py", ".pyw"):
            subprocess.Popen(["py", path], cwd=folder, creationflags=hidden)
        elif ext == ".exe":
            subprocess.Popen([path], cwd=folder)
        else:
            os.startfile(path)   # anything else opens as Windows would open it
    except Exception as e:
        report(f"  Problem: Run After Building: {os.path.basename(path)} didn't start ({e}).")
        return
    report(f"  Ran after building: {os.path.basename(path)}.")


def import_legacy_csv():
    """One-off import of the old FutureDiscoveries.csv, grouped into sessions by date and seed."""
    if _db.execute("SELECT value FROM meta WHERE key='csv_imported'").fetchone():
        return
    if os.path.isfile(CSV_FILE):
        with open(CSV_FILE, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        sessions = {}
        for r in rows:
            key = (r.get("Date", ""), r.get("Seed Artist", ""), r.get("Seed Track", ""))
            if key not in sessions:
                cur = _db.execute(
                    "INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued) "
                    "VALUES (?,?,?,?,?,?,0)",
                    (key[0], "legacy", key[1], key[2], "", r.get("Source", "") or "legacy CSV"))
                sessions[key] = cur.lastrowid
            _db.execute("INSERT INTO discoveries (session_id, artist, track, sources, found) VALUES (?,?,?,?,0)",
                        (sessions[key], r.get("Discovered Artist", ""), r.get("Discovered Track", ""),
                         r.get("Source", "")))
        print(f"Imported {len(rows)} rows from {CSV_FILE} into {DB_FILE} ({len(sessions)} sessions).")
    _db.execute("INSERT INTO meta (key, value) VALUES ('csv_imported', ?)", (datetime.now().isoformat(),))
    _db.commit()


# --- Discover queries (read-only helpers for the Discover tab) --------------

def list_sessions():
    """Returns [(id, started_at, mode, seed_artist, seed_track)] newest first."""
    return db().execute(
        "SELECT id, started_at, mode, seed_artist, seed_track FROM sessions ORDER BY id DESC"
    ).fetchall()


def list_discoveries(found=None, session_id=None):
    """
    Returns discovery rows as dicts, newest session first.
    found: None for all, True for hits, False for misses.
    session_id: restrict to one session, or None for all.
    """
    q = ("SELECT d.artist, d.track, d.sources, d.found, s.started_at, d.session_id, "
         "s.seed_artist, s.seed_track, d.id "
         "FROM discoveries d JOIN sessions s ON s.id = d.session_id")
    conds, args = [], []
    if found is not None:
        conds.append("d.found = ?")
        args.append(1 if found else 0)
    if session_id is not None:
        conds.append("d.session_id = ?")
        args.append(session_id)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY d.session_id DESC, d.id ASC"
    rows = db().execute(q, args).fetchall()
    return [{"artist": r[0], "track": r[1], "sources": r[2], "found": bool(r[3]),
             "date": r[4], "session_id": r[5], "seed_artist": r[6], "seed_track": r[7], "id": r[8]}
            for r in rows]


def clear_discoveries(ids=None):
    """
    Deletes Discover history: every session and discovery when ids is None,
    otherwise just those discovery rows, plus any session they leave empty.
    The provider cache and the meta table are kept, so builds stay fast and
    the old FutureDiscoveries CSV is never imported again.
    Returns the number of discovery rows removed.
    """
    con = db()
    if ids is None:
        removed = con.execute("SELECT COUNT(*) FROM discoveries").fetchone()[0]
        con.execute("DELETE FROM discoveries")
        con.execute("DELETE FROM sessions")
        con.commit()
        return removed
    ids = [int(i) for i in ids if i is not None]
    removed, touched = 0, set()
    for start in range(0, len(ids), 500):   # SQLite caps the number of ? per statement
        chunk = ids[start:start + 500]
        marks = ",".join("?" * len(chunk))
        touched.update(r[0] for r in con.execute(
            f"SELECT DISTINCT session_id FROM discoveries WHERE id IN ({marks})", chunk))
        removed += con.execute(f"DELETE FROM discoveries WHERE id IN ({marks})", chunk).rowcount
    for sid in touched:
        if not con.execute("SELECT 1 FROM discoveries WHERE session_id=? LIMIT 1", (sid,)).fetchone():
            con.execute("DELETE FROM sessions WHERE id=?", (sid,))
    con.commit()
    return removed


_jriver_unreachable = []   # becomes non-empty after the first failed read


def _read_zones():
    """JRiver's zones as [(id, name)] in JRiver's order, plus the active zone's ID. ([], None) if unreachable."""
    try:
        r = requests.get(f"{JRIVER_BASE}/Playback/Zones", auth=AUTH, timeout=5)
        items = {i.get("Name"): (i.text or "").strip() for i in ET.fromstring(r.text).findall("Item")}
        count = int(items.get("NumberZones") or 0)
    except Exception:
        return [], None
    zones = [(items.get(f"ZoneID{n}"), items.get(f"ZoneName{n}")) for n in range(count)]
    return [(i, n) for i, n in zones if i and n], items.get("CurrentZoneID")


ZONE_CACHE_SECONDS = 60
_zone_cache = [0.0, []]   # when read, [(id, name)]


def _zone_list(fresh=False):
    """JRiver's zones as [(id, name)], read at most once a minute unless fresh."""
    if not fresh and _zone_cache[1] and time.time() - _zone_cache[0] < ZONE_CACHE_SECONDS:
        return _zone_cache[1]
    zones, _ = _read_zones()
    if zones:
        _zone_cache[0], _zone_cache[1] = time.time(), zones
    return zones


def zone_names(include_hidden=False):
    """The zone names for the Play tab's lists, hidden ones left out unless asked for."""
    refresh_settings_if_changed()
    zones, _ = _read_zones()
    return [n for _, n in zones if include_hidden or n not in HIDDEN_ZONES]


def zone_id(name=None):
    """A zone's JRiver ID by name. No name means the active zone. None if a named zone can't be found."""
    if not name:
        _, current = _read_zones()   # JRiver's active zone can change at any moment
        return current or ACTIVE_ZONE
    for fresh in (False, True):   # a name not in the cached list gets one fresh read
        for zid, zname in _zone_list(fresh):
            if zname == name:
                return zid
    return None


def zone_label(zid):
    """A zone's name from its ID, for the log."""
    return next((n for i, n in _zone_list() if i == zid), f"zone {zid}")


def seed_zone():
    """The zone the Now Playing tab reads and seeds from. None if its chosen zone has gone."""
    return zone_id(SEED_ZONE_NAME) if SEED_ZONE_NAME else ACTIVE_ZONE


def get_playing_info(zone=None):
    """Gets the current artist, track name and Playing Now position from JRiver (the seed zone by default)."""
    try:
        zone = zone or seed_zone()
        if zone is None:
            return None
        r = requests.get(f"{JRIVER_BASE}/Playback/Info", params={"Zone": zone}, auth=AUTH, timeout=10)
        root = ET.fromstring(r.text)
        info = {"Artist": "Unknown", "Album": "Unknown", "Name": "Unknown",
                "PlayingNowPosition": "-1", "PlayingNowTracks": "0", "FileKey": "", "ZoneID": ""}
        for item in root.findall('Item'):
            if item.get('Name') in info:
                info[item.get('Name')] = item.text
        return info
    except Exception as e:
        if not _jriver_unreachable:   # say it once; the GUI asks every few seconds
            _jriver_unreachable.append(True)
            print(f"Problem: JRiver isn't reachable ({e}). The Search tab with YouTube output works without it.")
        return None


def last_played_seed(zone=None, report=print):
    """
    The most recently played track in the library, shaped like a searched seed,
    for when Playing Now is empty (keyboard shortcuts and the Play tab buttons).
    Asks JRiver first, so a track played a minute ago counts; falls back to the
    library held in memory (up to half an hour old). zone: the zone ID it's for,
    so the playlist goes there. None if nothing has ever been played.
    """
    import library   # here rather than at the top: library imports engine
    best = None
    try:
        r = requests.get(f"{JRIVER_BASE}/Files/Search",
                         params={"Query": "[Media Type]=[Audio] ~sort=[Last Played]-d ~n=1", "Action": "JSON",
                                 "Fields": "Key,Name,Artist,Album,Last Played"}, auth=AUTH, timeout=30)
        for row in json.loads(r.text):
            when = library.played_time(str(row.get("Last Played") or "").strip())
            if when and (best is None or when > best[0]):
                best = (when, {k: str(v) for k, v in row.items()})
    except Exception:
        pass
    if best is None:
        try:
            library.ensure_loaded()
            with library._lock:
                key = max(library._played, key=library._played.get) if library._played else None
                row = next((r for r in library._tracks if str(r.get("Key")) == key), None) if key else None
            if row:
                best = (0, row)
        except Exception:
            pass
    if best is None:
        return None
    row = best[1]
    seed = typed_seed_info(row.get("Artist") or "", row.get("Name") or "")
    seed.update({"Album": row.get("Album") or "", "FileKey": str(row.get("Key") or ""),
                 "LastPlayed": True, "ZoneID": zone or ""})
    return seed


def seed_or_last_played(zone=None, report=print):
    """
    The seed for a keyboard shortcut or a Play tab button: the zone's current
    track (paused or stopped counts), or the most recently played track when
    its Playing Now is empty. Logs which it used. None, after a log line, if neither.
    """
    zone = zone or seed_zone()
    if zone is None:
        report("Problem: the Now Playing zone isn't in JRiver. Pick another under Zone.")
        return None
    if zone == ACTIVE_ZONE:
        zone = zone_id()
    info = get_playing_info(zone)
    if info and info.get("PlayingNowPosition", "-1") != "-1" and info.get("PlayingNowTracks", "0") != "0":
        info["ZoneID"] = info.get("ZoneID") or zone
        return info
    seed = last_played_seed(zone, report)
    if not seed:
        report("Problem: nothing is playing and there's no last played track. Start a track in JRiver, "
               "or use the Search tab.")
        return None
    report(f"  Note: nothing is in Playing Now, so seeding from the last track played: "
           f"{seed['Artist']} - {seed['Name']}.")
    return seed


def remove_from_playing_now(index, zone=ACTIVE_ZONE):
    """Removes a single track from a zone's Playing Now by 0-based index."""
    requests.get(
        f"{JRIVER_BASE}/Playback/EditPlaylist",
        params={"Zone": zone, "Action": "Remove", "Source": str(index)},
        auth=AUTH
    )


def clear_around_current(zone=ACTIVE_ZONE):
    """
    Strips a zone's Playing Now down to just the currently playing track,
    without interrupting playback. Removes everything after the current track
    (from the end backwards, so indices stay valid), then everything
    before it (index 0 repeatedly).
    """
    info = get_playing_info(zone)
    if not info:
        return
    try:
        current_pos = int(info["PlayingNowPosition"])
        count = int(info["PlayingNowTracks"])
    except (ValueError, TypeError):
        print("  Note: couldn't read the Playing Now position, so nothing was cleared.")
        return

    if current_pos < 0 or count <= 1:
        return

    after = count - 1 - current_pos
    before = current_pos
    debug(f"Clearing Playing Now: {before} before and {after} after the current track")

    for idx in range(count - 1, current_pos, -1):
        remove_from_playing_now(idx, zone)
        time.sleep(0.05)

    for _ in range(before):
        remove_from_playing_now(0, zone)
        time.sleep(0.05)


def queue_tracks(keys, zone=ACTIVE_ZONE):
    """Appends a list of file keys to the end of a zone's Playing Now in one call."""
    if not keys:
        return
    requests.get(
        f"{JRIVER_BASE}/Playback/PlayByKey",
        params={"Key": ",".join(str(k) for k in keys), "Location": "End", "Zone": zone},
        auth=AUTH
    )


VERSION_WORDS = r'(remaster|remastered|mix|master|edit|version|live|mono|stereo|demo|single|radio|acoustic|instrumental|soundtrack|ost)'


# Typographic characters that sources (MusicBrainz especially) use where a
# library is tagged with plain ASCII. 'alt‐J' with a Unicode hyphen looks
# identical to 'alt-J' but won't match it, so everything is folded to ASCII.
PUNCTUATION_MAP = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u2015": "-", "\u2212": "-",                       # hyphens, dashes, minus
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u2032": "'",   # single quotes
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',   # double quotes
    "\u2026": "...",                                                # ellipsis
    "\u00a0": " ",                                                  # non-breaking space
})


def normalise_punctuation(s):
    """Folds typographic dashes, quotes and ellipses to their ASCII equivalents."""
    return s.translate(PUNCTUATION_MAP) if s else s


def clean_name(s):
    """Strips common variations from track names for fuzzy matching."""
    s = normalise_punctuation(s).lower().strip()
    s = re.sub(r'\(.*?\)|\[.*?\]', '', s)                       # (Live), [Remaster 2011] etc.
    s = re.sub(r'\s+-\s+from\s.*$', '', s)                        # " - From 'Casino Royale' Soundtrack"
    s = re.sub(rf'\s+-\s+[^-]*\b{VERSION_WORDS}\b[^-]*$', '', s)  # " - 2012 Mix/Master", " - Live at..."
    s = re.sub(r'\s*(feat\.|featuring|ft\.)\s.*', '', s)         # feat. credits
    s = s.replace('&', ' and ')                                  # "Girls & Boys" = "Girls And Boys"
    s = re.sub(r'[^\w\s]', '', s)                                # punctuation
    return re.sub(r'\s+', ' ', s).strip()


def normalise_artist(artist_name):
    """
    Strips 'The' prefix/suffix and trailing '& The X' / 'and the X'
    backing-band credits for cleaner searching, so Last.fm's fully-credited
    artist name (e.g. 'Ben Harper & The Criminals') still matches a library
    where the artist has been normalised down to just the main act
    ('Ben Harper'). Deliberately requires 'the' right after the conjunction,
    so true duo/group names like 'Simon & Garfunkel' or 'Hall & Oates' are
    left untouched.
    """
    search_term = artist_name.strip()
    search_term = re.sub(
        r'\s+(&|and)\s+the\s+.*$',
        '',
        search_term,
        flags=re.IGNORECASE
    ).strip()
    search_term = re.sub(r'^(The\s+)|(,\s+The)$', '', search_term, flags=re.IGNORECASE).strip()
    return search_term


_CREDIT_JOINERS = re.compile(
    r'\s+(?:&|and|feat\.?|ft\.?|featuring|with|x|vs\.?)\s+|\s*[,+/]\s*', re.IGNORECASE)


def primary_artist(artist_name):
    """
    The first-named act in a shared credit, or None when there's only one:
    'Paul McCartney & Wings' -> 'Paul McCartney', 'Mark Ronson feat. Amy
    Winehouse' -> 'Mark Ronson'. Only ever a fallback after the full credit
    misses, and the title must still match, so 'Simon & Garfunkel' can't pull
    in a Paul Simon song by accident.
    """
    name = deinvert_the(normalise_punctuation(artist_name or ""))
    first = _CREDIT_JOINERS.split(name, maxsplit=1)[0].strip()
    return first if first and first.lower() != name.lower() else None


def strip_accents(s):
    """'José González' -> 'Jose Gonzalez', 'Trüby Trio' -> 'Truby Trio'."""
    decomposed = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in decomposed if not unicodedata.combining(c))


def strip_initial_dots(s):
    """
    Collapses dotted initials: 'U.N.K.L.E.' -> 'UNKLE', 'M.I.A.' -> 'MIA',
    'R.E.M.' -> 'REM'. Only touches dots between single letters, so
    'Mr. Scruff' and 'Jr.' are left alone.
    """
    # Repeatedly remove a dot that sits between two single letters (or after a
    # single letter at the end), which is the initials pattern.
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\b([A-Za-z])\.(?=[A-Za-z]\b|[A-Za-z]\.|\s|$)', r'\1', s)
    return s


def norm_artist_text(s):
    """Accent-free, dot-collapsed, ASCII-punctuation form used wherever two artist names are compared."""
    return strip_accents(strip_initial_dots(normalise_punctuation(s)))


def deinvert_the(name):
    """
    Turns a trailing ', The' into a leading 'The' so library-style names match
    canonical databases. 'Isley Brothers, The' -> 'The Isley Brothers'.
    Returns the name unchanged if there's no trailing ', The'.
    """
    m = re.match(r'^(.*),\s*(The|A|An)$', name.strip(), re.IGNORECASE)
    return f"{m.group(2)} {m.group(1)}" if m else name.strip()


def dotted_initials(term):
    """
    'UNKLE' -> 'U.N.K.L.E.' for short one-word names, else None. Sources often
    drop the dots a library keeps, and JRiver's search can't bridge the two.
    """
    if re.fullmatch(r"[A-Za-z]{2,8}", term or ""):
        return ".".join(term.upper()) + "."
    return None


def jriver_search_artist_items(artist_name):
    """
    Runs the JRiver library search for an artist and returns the matching
    MPL items plus the accent-free search term used for regex filtering.
    Queries with accents stripped first; if that returns nothing and the
    name had accents, queries again with the original spelling so libraries
    that keep accents still match.
    """
    term_original = normalise_artist(normalise_punctuation(artist_name))
    term_ascii = norm_artist_text(term_original)
    # Try the normalised form first (no accents, no dotted initials), then the
    # original spelling, so libraries tagged either way still match.
    queries = [term_ascii] if term_ascii == term_original else [term_ascii, term_original]
    # A source may drop the dots a library keeps ('UNKLE' vs 'U.N.K.L.E.'), so short
    # one-word names get a last try in dotted form.
    dotted = dotted_initials(term_ascii)
    if dotted and dotted not in queries:
        queries.append(dotted)
    # Every spelling is searched and the results merged (deduped by file key). No
    # single search can be trusted to be complete: 'UNKLE' finds a U.N.K.L.E. track
    # with the word in its title but not the rest of that artist's tracks.
    merged, seen_keys = [], set()
    for query in queries:
        r = requests.get(
            f"{JRIVER_BASE}/Files/Search",
            params={"Query": query, "Action": "MPL"},
            auth=AUTH
        )
        if r.status_code != 200 or not r.text:
            continue
        for item in ET.fromstring(r.text).findall(".//Item"):
            key = next((f.text for f in item.findall("Field") if f.get("Name") == "Key"), None)
            if key is not None and key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(item)
    return merged, term_ascii


def artist_matches(pattern, fields):
    """
    Applies the artist regex to the normalised (accent-free, dot-collapsed)
    artist field. A multi-value field ('Angus Stone;Dope Lemon') is split and
    each part checked on its own, so the track matches if ANY of its artists
    matches, and a search for 'Angus Stone' can't accidentally match across
    the ';' boundary.
    """
    actual_artist = fields.get("Artist", "") or fields.get("Album Artist", "")
    return any(pattern.search(norm_artist_text(part)) for part in split_values(actual_artist))


# ---------------------------------------------------------------------------
# Recommendation Providers
# Each service exposes two functions with identical shapes:
#   similar(artist_name, limit) -> list of artist names
#   top_tracks(artist_name, limit) -> list of track names, most popular first
# A run uses one service only; no cross-service fallback.
# ---------------------------------------------------------------------------

USER_AGENT = "JRiverGenius/1.0 (personal playlist tool)"
# ListenBrainz Labs similar-artists algorithms. Two are offered on the menu;
# the others are known to exist and can be added to LISTENBRAINZ_ALGORITHMS later:
#   session_based_days_1825_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30  (5 years, per-listener cap)
#   session_based_days_1800_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30  (same, 1800 days)
#   session_based_days_7500_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30  (all time, per-listener cap)
#   session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30               (all time, unfiltered, max 50)
LISTENBRAINZ_ALGORITHMS = {
    "recent": ("Recent - what people are playing alongside this artist right now",
               "session_based_days_75_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30"),
    "alltime": ("All time",
                "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30"),
}
LISTENBRAINZ_DEFAULT = "alltime"


def listenbrainz_algorithm_from_settings():
    """Returns (label, algorithm string) for the LISTENBRAINZ_ALGORITHM setting."""
    key = LISTENBRAINZ_ALGORITHM_SETTING if LISTENBRAINZ_ALGORITHM_SETTING in LISTENBRAINZ_ALGORITHMS else LISTENBRAINZ_DEFAULT
    return LISTENBRAINZ_ALGORITHMS[key]


def canonicalise_conjunction(artist_name):
    """
    Normalises '+' and 'and' to '&' in artist names returned by any
    provider, so they match this library's '&' convention (e.g.
    'Florence and the Machine' -> 'Florence & the Machine') before the
    name is ever used as a JRiver search term.
    """
    name = normalise_punctuation(artist_name)
    name = re.sub(r'\s*\+\s*', ' & ', name)
    name = re.sub(r'\s+and\s+', ' & ', name, flags=re.IGNORECASE)
    return name


# --- Last.fm ---------------------------------------------------------------

def lastfm_similar(artist_name, limit=20):
    url = "http://ws.audioscrobbler.com/2.0/"
    params = {"method": "artist.getsimilar", "artist": artist_name,
              "api_key": LASTFM_KEY, "format": "json", "limit": limit}
    try:
        r = requests.get(url, params=params)
        names = [a['name'] for a in r.json().get('similarartists', {}).get('artist', [])]
        return [canonicalise_conjunction(n) for n in names]
    except Exception as e:
        print(f"  Problem: Last.fm didn't answer for similar artists ({e}).")
        return []


def lastfm_top_tracks_with_counts(artist_name, limit=10):
    """Returns [(track name, playcount)] most popular first."""
    url = "http://ws.audioscrobbler.com/2.0/"
    params = {"method": "artist.gettoptracks", "artist": artist_name,
              "api_key": LASTFM_KEY, "format": "json", "limit": limit}
    try:
        r = requests.get(url, params=params)
        return [(t['name'], int(t.get('playcount', 0)))
                for t in r.json().get('toptracks', {}).get('track', [])]
    except Exception as e:
        print(f"  Problem: Last.fm didn't answer for {artist_name}'s top tracks ({e}).")
        return []


def lastfm_top_tracks(artist_name, limit=10):
    return [name for name, _ in lastfm_top_tracks_with_counts(artist_name, limit)]


# --- Deezer (public catalogue endpoints, no key) ---------------------------

_deezer_id_cache = {}


def deezer_artist_id(artist_name, verbose=False):
    """
    Resolves an artist name to a Deezer ID. Deezer's search isn't ranked
    by popularity and common names return several artists, so prefer an
    exact name match and, within that, the highest fan count.
    """
    if artist_name in _deezer_id_cache:
        return _deezer_id_cache[artist_name]
    artist_id = None
    try:
        r = requests.get("https://api.deezer.com/search/artist",
                         params={"q": artist_name, "limit": 10})
        data = r.json().get("data", [])
        if data:
            target = artist_name.strip().lower()
            exact = [a for a in data if a.get("name", "").strip().lower() == target]
            pool = exact if exact else data
            best = max(pool, key=lambda a: a.get("nb_fan", 0))
            artist_id = best["id"]
            if verbose:
                debug(f"Deezer: using '{best.get('name')}' (id {artist_id}, "
                      f"{best.get('nb_fan', 0)} fans) from {len(data)} search hits")
    except Exception as e:
        print(f"  Problem: Deezer didn't answer when searching for {artist_name} ({e}).")
    _deezer_id_cache[artist_name] = artist_id
    return artist_id


def deezer_similar(artist_name, limit=20):
    artist_id = deezer_artist_id(artist_name, verbose=True)
    if not artist_id:
        debug(f"Deezer: no artist match for {artist_name}")
        return []
    try:
        r = requests.get(f"https://api.deezer.com/artist/{artist_id}/related",
                         params={"limit": limit})
        names = [a["name"] for a in r.json().get("data", [])]
        return [canonicalise_conjunction(n) for n in names]
    except Exception as e:
        print(f"  Problem: Deezer didn't answer for similar artists ({e}).")
        return []


def deezer_top_tracks(artist_name, limit=10):
    artist_id = deezer_artist_id(artist_name, verbose=True)
    if not artist_id:
        return []
    try:
        r = requests.get(f"https://api.deezer.com/artist/{artist_id}/top",
                         params={"limit": limit})
        return [t["title"] for t in r.json().get("data", [])]
    except Exception as e:
        print(f"  Problem: Deezer didn't answer for {artist_name}'s top tracks ({e}).")
        return []


# --- ListenBrainz (via MusicBrainz ID lookup, no key) ----------------------

_mbid_cache = {}              # artist_key -> MusicBrainz ID (None = MusicBrainz doesn't know them)
_mbid_pending = {}            # learnt this session, not yet written to the database
_mbid_confirmed_misses = set()   # names MusicBrainz answered for and had nobody (as opposed to a failed lookup)
_mbids_loaded = []            # becomes non-empty once the saved IDs have been read in


def load_known_mbids():
    """
    Reads the MusicBrainz IDs saved by earlier sessions into memory, once per
    app session. A found ID never expires (an artist's ID doesn't change). A
    saved "MusicBrainz doesn't know them" is honoured for CACHE_DAYS (a month at
    most, whatever the setting) and then tried again, in case they've been added since.
    """
    if _mbids_loaded:
        return
    _mbids_loaded.append(True)
    try:
        rows = db().execute("SELECT key, payload, fetched_at FROM cache "
                            "WHERE source='MusicBrainz' AND kind='mbid'").fetchall()
    except Exception as e:
        print(f"  Note: couldn't read the saved MusicBrainz IDs ({e}), so they'll be looked up again.")
        return
    now = time.time()
    for known, payload, fetched_at in rows:
        try:
            mbid = json.loads(payload)
        except ValueError:
            continue
        if mbid:
            _mbid_cache.setdefault(known, mbid)
        elif now - fetched_at <= min(CACHE_DAYS or MB_UNKNOWN_DAYS, MB_UNKNOWN_DAYS) * 86400:
            _mbid_cache.setdefault(known, None)
    debug(f"MusicBrainz: {len(_mbid_cache)} saved artist IDs loaded")


def save_new_mbids():
    """Writes IDs learnt this session to the database. Called from the main run, never from a lookup."""
    if not _mbid_pending:
        return
    pending = dict(_mbid_pending)
    _mbid_pending.clear()
    try:
        for known, mbid in pending.items():
            db().execute("INSERT OR REPLACE INTO cache (source, kind, key, payload, fetched_at) "
                         "VALUES (?,?,?,?,?)",
                         ("MusicBrainz", "mbid", known, json.dumps(mbid or ""), time.time()))
        db().commit()
        debug(f"MusicBrainz: {len(pending)} artist IDs saved")
    except Exception as e:
        print(f"  Note: couldn't save the new MusicBrainz IDs ({e}).")


import threading

MUSICBRAINZ_INTERVAL = 1.1     # seconds between the START of MusicBrainz requests (their rule: one a second)
_mb_next_slot = [0.0]
_mb_lock = threading.Lock()


def _musicbrainz_wait_turn():
    """Blocks until it is this caller's turn to ask MusicBrainz. Safe to call from any thread."""
    with _mb_lock:
        wait = _mb_next_slot[0] - time.time()
        if wait > 0:
            time.sleep(wait)
        _mb_next_slot[0] = time.time() + MUSICBRAINZ_INTERVAL


def _musicbrainz_query(name):
    """Single MusicBrainz artist search for one name spelling. Returns an MBID or None."""
    for attempt in range(3):
        try:
            r = requests.get("https://musicbrainz.org/ws/2/artist/",
                             params={"query": f'artist:"{name}"', "fmt": "json", "limit": 1},
                             headers={"User-Agent": USER_AGENT})
            if r.status_code == 503:
                debug(f"MusicBrainz busy, retrying ({attempt + 1} of 3)")
                time.sleep(2.0)
                continue
            if r.status_code != 200:
                print(f"  Problem: MusicBrainz answered {r.status_code} for {name}.")
                debug(f"MusicBrainz reply: {r.text[:200]}")
                return None
            artists = r.json().get("artists", [])
            if not artists:
                _mbid_confirmed_misses.add(name)   # MusicBrainz answered, and has nobody by this name
            return artists[0]["id"] if artists else None
        except Exception as e:
            print(f"  Problem: MusicBrainz didn't answer for {name} ({e}).")
            return None
    return None


def musicbrainz_artist_id(artist_name):
    """
    Resolves an artist name to a MusicBrainz ID. Tries the name as given, then
    the de-inverted form ('Isley Brothers, The' -> 'The Isley Brothers'), since
    libraries often store the sort-name form that MusicBrainz doesn't match.
    MusicBrainz asks for 1 req/sec.
    """
    load_known_mbids()   # IDs saved by earlier sessions, read once
    known = artist_key(artist_name)   # so "The xx" and "The XX" share one saved ID
    if known in _mbid_cache:
        return _mbid_cache[known]
    candidates = [artist_name]
    deinverted = deinvert_the(artist_name)
    if deinverted != artist_name:
        candidates.append(deinverted)
    mbid = None
    for name in candidates:
        _musicbrainz_wait_turn()   # MusicBrainz allows one request a second
        mbid = _musicbrainz_query(name)
        if mbid:
            break
    _mbid_cache[known] = mbid
    if mbid or all(c in _mbid_confirmed_misses for c in candidates):
        _mbid_pending[known] = mbid   # a failed lookup (MusicBrainz busy, no internet) is never saved
    return mbid


def listenbrainz_similar(artist_name, limit=20, algorithm=None):
    algorithm = algorithm or LISTENBRAINZ_ALGORITHMS[LISTENBRAINZ_DEFAULT][1]
    mbid = musicbrainz_artist_id(artist_name)
    if not mbid:
        debug(f"ListenBrainz: no MusicBrainz match for {artist_name}")
        return []
    try:
        r = requests.post("https://labs.api.listenbrainz.org/similar-artists/json",
                          json=[{"artist_mbids": [mbid], "algorithm": algorithm}],
                          headers={"User-Agent": USER_AGENT})
        data = r.json()
        # The Labs endpoint has changed shape over time; handle the known variants
        if isinstance(data, list) and data and isinstance(data[0], dict) and "data" in data[0]:
            data = data[0]["data"]
        if isinstance(data, dict):
            data = data.get("data", [])
        names = []
        for item in data:
            name = item.get("name") or item.get("artist_name")
            if name and name != artist_name:
                names.append(name)
        if not names and data:
            debug(f"ListenBrainz: unrecognised reply, first item: {data[0]}")
        return [canonicalise_conjunction(n) for n in names[:limit]]
    except Exception as e:
        print(f"  Problem: ListenBrainz didn't answer for similar artists ({e}).")
        return []


def listenbrainz_top_tracks(artist_name, limit=10):
    mbid = musicbrainz_artist_id(artist_name)
    if not mbid:
        return []
    if not LISTENBRAINZ_TOKEN:
        debug("ListenBrainz: no user token, so no top tracks")
        return []
    try:
        r = requests.get(f"https://api.listenbrainz.org/1/popularity/top-recordings-for-artist/{mbid}",
                         headers={"User-Agent": USER_AGENT,
                                  "Authorization": f"Token {LISTENBRAINZ_TOKEN}"})
        if r.status_code != 200:
            print(f"  Problem: ListenBrainz answered {r.status_code} for top tracks.")
            debug(f"ListenBrainz reply: {r.text[:200]}")
            return []
        try:
            data = r.json()
        except ValueError:
            debug(f"ListenBrainz top recordings: status {r.status_code}, "
                  f"content-type {r.headers.get('Content-Type')}, body starts: {r.text[:300]!r}")
            return []
        if isinstance(data, dict):
            data = data.get("payload") or data.get("recordings") or []
        names = [t.get("recording_name") or t.get("name") for t in data]
        names = [normalise_punctuation(n) for n in names if n]
        if not names and data:
            debug(f"ListenBrainz: unrecognised top tracks reply, first item: {data[0]}")
        return names[:limit]
    except Exception as e:
        print(f"  Problem: ListenBrainz didn't answer for {artist_name}'s top tracks ({e}).")
        return []


# --- AI (Anthropic API, LLM knowledge of music) ----------------------------

AI_MODEL = "claude-sonnet-5"   # switch here if a cheaper or stronger model suits better
AI_SIMILAR_PROMPT = (
    "List the {limit} musical artists most similar to \"{artist}\", most similar first. "
    "Consider sound, era, scene and audience. Use each artist's most common spelling. "
    "Respond with a JSON array of artist name strings only, no commentary, no code fences."
)
AI_VIBE_PROMPT = (
    "Suggest {count} songs that fit this mood or description: \"{vibe}\".\n"
    "Favour well-known, widely-available recordings across a range of artists. "
    "Respond with a JSON array of objects with keys \"artist\" and \"track\" only, "
    "compact on a single line with no indentation or line breaks, no commentary, no code fences."
)
AI_VIBE_SUGGESTIONS_PROMPT = (
    "Suggest three short, evocative music playlist moods a listener might enjoy, "
    "each under eight words (for example a time of day, activity, feeling or era). "
    "Respond with a JSON array of three strings only, no commentary, no code fences."
)
AI_TOP_TRACKS_PROMPT = (
    "List the {limit} most popular songs by \"{artist}\", most popular first, "
    "judged by overall listenership. Use official song titles without album or version notes. "
    "Respond with a JSON array of song title strings only, no commentary, no code fences."
)


def _salvage_json_array(text):
    """
    Recovers a list from a truncated JSON array like ["A","B","C  (no closing bracket).
    Returns the complete quoted strings found, or [] if none.
    """
    return re.findall(r'"([^"]+)"', text)


_AI_THINKING_OFF_OK = True   # cleared for the session if the model rejects thinking: disabled


def record_ai(feature, model, message):
    """Notes the tokens an AI request used, for Settings > Keys > AI Usage. Never stops a build."""
    try:
        import ai_usage
        ai_usage.record(feature, model, message)
    except Exception as e:
        debug(f"AI usage not recorded ({e})")


def _ai_create(client, feature="AI", **kwargs):
    """
    One request to Claude with thinking switched off: these calls recall lists
    of names, which thinking doesn't improve and which it was crowding out of
    max_tokens. A model that rejects the setting (400) gets the plain request
    instead, once, and the setting is skipped for the rest of the session.
    Prints a waiting line, and the time taken at Debug level.
    """
    global _AI_THINKING_OFF_OK
    print("  Asking the AI...")
    started = time.time()
    try:
        message = None
        if _AI_THINKING_OFF_OK:
            try:
                message = client.messages.create(thinking={"type": "disabled"}, **kwargs)
            except Exception as e:
                if getattr(e, "status_code", None) == 400 and "thinking" in str(e).lower():
                    _AI_THINKING_OFF_OK = False
                    debug(f"{kwargs.get('model')} won't run with thinking off, asking again with it on")
                else:
                    raise
        if message is None:
            message = client.messages.create(**kwargs)
        record_ai(feature, kwargs.get("model"), message)
        return message
    finally:
        debug(f"AI replied in {time.time() - started:.1f} s")


def ai_ask_list(prompt, feature="AI"):
    """Sends a prompt expecting a JSON array of strings; returns the list or []."""
    global AI_LAST_ERROR
    AI_LAST_ERROR = "no API key"
    if not ANTHROPIC_API_KEY:
        debug("AI: no Anthropic key")
        return []
    try:
        import anthropic
    except ImportError:
        print("  Problem: the AI can't run because the anthropic package isn't installed (pip install anthropic).")
        return []
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = _ai_create(client, feature, model=AI_MODEL, max_tokens=1500,
                             messages=[{"role": "user", "content": prompt}])
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = _salvage_json_array(text)
            if data:
                print(f"  Note: the AI's reply was cut short; {len(data)} names were recovered.")
        if isinstance(data, list):
            AI_LAST_ERROR = ""
            return [str(x).strip() for x in data if str(x).strip()]
        AI_LAST_ERROR = "reply couldn't be read"
        print("  Problem: the AI's reply couldn't be read.")
        debug(f"AI reply: {text[:200]}")
    except Exception as e:
        AI_LAST_ERROR = f"request failed: {e.__class__.__name__}"
        print(f"  Problem: the AI request failed ({e}).")
    return []


_AI_PAIR = re.compile(r'\{\s*"artist"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"track"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}')


def _salvage_json_pairs(text):
    """Every complete {"artist": ..., "track": ...} entry in a reply that can't be parsed whole."""
    out = []
    for m in _AI_PAIR.finditer(text):
        try:
            out.append({"artist": json.loads(f'"{m.group(1)}"'), "track": json.loads(f'"{m.group(2)}"')})
        except ValueError:
            continue
    return out


def _json_body(text):
    """The JSON array or object inside a reply, ignoring any words around it."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
    if not starts:
        return text
    start = min(starts)
    end = text.rfind("]" if text[start] == "[" else "}")
    return text[start:end + 1] if end > start else text[start:]


def ai_ask_json(prompt, max_tokens=4000, feature="AI"):
    """Sends a prompt expecting JSON; returns the parsed value, what could be salvaged, or None."""
    global AI_LAST_ERROR
    AI_LAST_ERROR = "no API key"
    if not ANTHROPIC_API_KEY:
        debug("AI: no Anthropic key")
        return None
    try:
        import anthropic
    except ImportError:
        AI_LAST_ERROR = "anthropic package not installed"
        print("  Problem: the AI can't run because the anthropic package isn't installed (pip install anthropic).")
        return None
    for attempt in (1, 2):
        text, stop = "", ""
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = _ai_create(client, feature, model=AI_MODEL, max_tokens=max_tokens,
                                 messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
            stop = getattr(message, "stop_reason", "")
            usage = getattr(message, "usage", None)
            debug(f"AI reply: {len(text)} chars, stop_reason {stop}, tokens in "
                  f"{getattr(usage, 'input_tokens', '?')} out {getattr(usage, 'output_tokens', '?')}")
            data = json.loads(_json_body(text))
            AI_LAST_ERROR = ""
            return data
        except json.JSONDecodeError as e:
            debug(f"JSON {e.msg} at {e.pos} of {len(text)}: "
                  f"{text[max(0, e.pos - 60):e.pos]!r} >>> {text[e.pos:e.pos + 40]!r}")
            found = _salvage_json_pairs(text)
            if found:
                why = "cut short" if stop == "max_tokens" else "partly unreadable"
                AI_LAST_ERROR = f"reply {why}, {len(found)} recovered"
                print(f"  Note: the AI's reply was {why}; {len(found)} complete entries were kept.")
                return found
            AI_LAST_ERROR = "reply couldn't be read"
            print("  Problem: the AI's reply couldn't be read.")
            debug(f"AI reply ({e.msg} at {e.pos} of {len(text)}): {text[:200]!r}")
        except Exception as e:
            AI_LAST_ERROR = f"request failed: {e.__class__.__name__}"
            debug(f"AI request failed: {e}")
        if attempt == 1:
            print("  Note: the AI request didn't work, so trying once more...")
        else:
            print(f"  Problem: the AI request didn't work ({AI_LAST_ERROR}).")
    return None


def ai_vibe_suggestions():
    """Three random playlist moods for the vibe dialog. Returns a list of strings (may be empty)."""
    data = ai_ask_json(AI_VIBE_SUGGESTIONS_PROMPT, max_tokens=200, feature="AI Playlist ideas")
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()][:3]
    return []


def ai_vibe_tracks(vibe, count, avoid=()):
    """Artist/track pairs for a vibe, leaving out any 'Artist - Title' in avoid. Returns [(artist, track)]."""
    prompt = AI_VIBE_PROMPT.format(vibe=vibe, count=count)
    if avoid:
        prompt += ("\n\nDon't include any of these, which have already been used or tried:\n"
                   + "\n".join(list(avoid)[-150:]))
    data = ai_ask_json(prompt, feature="AI Playlist")
    pairs = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("artist") and item.get("track"):
                pairs.append((canonicalise_conjunction(str(item["artist"]).strip()),
                              str(item["track"]).strip()))
    return pairs


def ai_similar(artist_name, limit=20):
    names = ai_ask_list(AI_SIMILAR_PROMPT.format(artist=artist_name, limit=limit),
                        feature="Similar Artists (AI source)")
    names = [canonicalise_conjunction(n) for n in names
             if strip_accents(n).lower() != strip_accents(artist_name).lower()]
    return names[:limit]


def ai_top_tracks(artist_name, limit=10):
    return ai_ask_list(AI_TOP_TRACKS_PROMPT.format(artist=artist_name, limit=limit),
                       feature="Top Tracks (AI source)")[:limit]


def deezer_artist_exists(artist_name):
    """
    Exact-name check against Deezer's keyless catalogue, used to verify
    AI-suggested artists before they're logged as discoveries.
    """
    try:
        r = requests.get("https://api.deezer.com/search/artist",
                         params={"q": artist_name, "limit": 10})
        target = strip_accents(artist_name).strip().lower()
        return any(strip_accents(a.get("name", "")).strip().lower() == target
                   for a in r.json().get("data", []))
    except Exception:
        return False


# --- YouTube Music (up next queue, via the unofficial ytmusicapi; no key) ----
# Unlike the other sources this one is seeded by the playing TRACK, not just
# the artist: it asks YouTube Music what it would play next. The queue is
# boiled down to a ranked artist list (a vote in the blend), and YouTube's own
# track pick for each artist is remembered as a hint for that artist's pool.

YOUTUBE_FETCH = 50               # up next tracks to ask for
YOUTUBE_HINTS_PER_ARTIST = 2     # at most this many YouTube picks join an artist's pool
YOUTUBE_SKIP_ARTISTS = {"various artists", "unknown artist", ""}

_youtube_client = None
_youtube_hints = {}              # artist_key -> [track names] from the latest run


def youtube_client():
    """Lazily creates the ytmusicapi client (no sign-in). Returns None if unavailable."""
    global _youtube_client
    if _youtube_client is None:
        try:
            from ytmusicapi import YTMusic
        except ImportError:
            print("  Problem: YouTube can't be used because the ytmusicapi package isn't installed "
                  "(py -m pip install ytmusicapi).")
            return None
        try:
            _youtube_client = YTMusic()
        except Exception as e:
            print(f"  Problem: YouTube Music didn't start ({e}).")
            return None
    return _youtube_client


def _youtube_artist_names(item):
    return [(a.get("name") or "").strip() for a in (item.get("artists") or []) if (a.get("name") or "").strip()]


def _youtube_same_artist(a, b):
    return artist_key(normalise_artist(a)) == artist_key(normalise_artist(b))


def _youtube_fetch_up_next(artist, track):
    """Finds the track on YouTube Music and returns its up next queue as [[artist, title], ...]."""
    yt = youtube_client()
    if yt is None:
        return []
    try:
        results = yt.search(f"{artist} {track}", filter="songs", limit=5)
    except Exception as e:
        debug(f"YouTube search failed for {artist} - {track}: {e}")
        return []

    best, best_score = None, 0
    for r in results or []:
        if not r.get("videoId"):
            continue
        score = 0
        if any(_youtube_same_artist(n, artist) for n in _youtube_artist_names(r)):
            score += 2
        if clean_name(r.get("title") or "") == clean_name(track):
            score += 1
        if score > best_score:
            best, best_score = r, score
    if best is None:
        debug(f"YouTube Music has no {artist} - {track}")
        return []
    debug(f"YouTube seed: {', '.join(_youtube_artist_names(best))} - {best.get('title')} [{best['videoId']}]")

    try:
        watch = yt.get_watch_playlist(videoId=best["videoId"], limit=YOUTUBE_FETCH, radio=True)
    except Exception as e:
        print(f"  Problem: YouTube didn't return its up next queue ({e}).")
        return []

    pairs = []
    for t in watch.get("tracks", []) or []:
        if t.get("videoId") == best["videoId"]:
            continue
        names = _youtube_artist_names(t)
        title = normalise_punctuation((t.get("title") or "").strip())
        if names and title:
            pairs.append([names[0], title])
    return pairs


def youtube_similar(artist_name, limit=20, track=None):
    """
    Similar artists from YouTube Music's up next queue for the playing track,
    in order of first appearance. Also fills _youtube_hints with YouTube's
    track picks per artist. Keeps its own cache, keyed on artist + track.
    """
    if not track or track == "Unknown":
        print("  Note: YouTube needs a track to seed from, so it was left out.")
        return []
    pairs = cached_call("YouTube", "up_next", f"{artist_key(artist_name)}|{clean_name(track)}",
                        lambda: _youtube_fetch_up_next(artist_name, track))
    names, seen = [], set()
    for pair in pairs or []:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        raw_artist, title = pair
        if raw_artist.strip().lower() in YOUTUBE_SKIP_ARTISTS:
            continue
        if _youtube_same_artist(raw_artist, artist_name):
            continue
        name = canonicalise_conjunction(raw_artist)
        k = artist_key(name)
        hints = _youtube_hints.setdefault(k, [])
        if clean_name(title) not in {clean_name(h) for h in hints}:
            hints.append(title)
        if k not in seen:
            seen.add(k)
            names.append(name)
    return names[:limit]


def youtube_up_next(artist_name, track):
    """The cached up next queue for a track, as [[artist, title], ...]. Shares its cache with youtube_similar."""
    if not track or track == "Unknown":
        return []
    return cached_call("YouTube", "up_next", f"{artist_key(artist_name)}|{clean_name(track)}",
                       lambda: _youtube_fetch_up_next(artist_name, track)) or []


def youtube_hints_for(artist, exclude_track=None):
    """YouTube's own track picks for an artist from the latest run (may be empty)."""
    hints = list(_youtube_hints.get(artist_key(artist), []))
    if exclude_track:
        skip = clean_name(exclude_track)
        hints = [h for h in hints if clean_name(h) != skip]
    return hints[:YOUTUBE_HINTS_PER_ARTIST]


# --- Registry and chooser --------------------------------------------------

PROVIDERS = {
    "lastfm":       ("Last.fm",      lastfm_similar,       lastfm_top_tracks),
    "listenbrainz": ("ListenBrainz", listenbrainz_similar, listenbrainz_top_tracks),
    "deezer":       ("Deezer",       deezer_similar,       deezer_top_tracks),
    "ai":           ("AI",           ai_similar,           ai_top_tracks),
    "youtube":      ("YouTube",      youtube_similar,      None),
}


# --- Missing keys, said out loud ----------------------------------------------
# These lines go through report(), so they show in the app's log. The packaged
# app has no console, so a print() here would never be seen.

KEY_HELP_LINE = "Settings > Keys"
NOTHING_PLAYING = "Problem: nothing is playing. Start a track in JRiver, or use the Search tab."


def source_has_key(code, purpose="similar"):
    """
    Can this source be asked at all? Deezer and YouTube need no key.
    ListenBrainz needs its token only for top tracks, not for similar artists.
    """
    if code == "lastfm":
        return bool(LASTFM_KEY)
    if code == "ai":
        return bool(ANTHROPIC_API_KEY)
    if code == "listenbrainz" and purpose == "top":
        return bool(LISTENBRAINZ_TOKEN)
    return True


def missing_key_notes(similar=False, top_tracks=False):
    """One plain line per ticked source that has no key, for the run about to start."""
    ticked_similar = set(SIMILAR_SOURCES) if similar else set()
    ticked_top = set(TOP_TRACK_SOURCES) if top_tracks else set()
    notes = []
    if "lastfm" in (ticked_similar | ticked_top) and not LASTFM_KEY:
        notes.append("Last.fm is ticked but has no key, so it was skipped. " + KEY_HELP_LINE)
    if "ai" in (ticked_similar | ticked_top) and not ANTHROPIC_API_KEY:
        notes.append("AI is ticked but has no Anthropic key, so it was skipped. " + KEY_HELP_LINE)
    if "listenbrainz" in ticked_top and not LISTENBRAINZ_TOKEN:
        notes.append("ListenBrainz is ticked for top tracks but has no user token, "
                     "so it was skipped there. " + KEY_HELP_LINE)
    return notes


def report_missing_keys(report, similar=False, top_tracks=False):
    for note in missing_key_notes(similar=similar, top_tracks=top_tracks):
        report("  Note: " + note)


def vibe_blocker():
    """None if Vibe Playlist can run, otherwise the line to show the user."""
    refresh_settings_if_changed()
    if not ANTHROPIC_API_KEY:
        return "AI Playlist needs an Anthropic key. Add it under Settings > Keys."
    return None


def sources_from_settings(names, setting_name):
    """
    Maps a list of source names from .env to provider tuples, dropping unknown
    names with a warning. Falls back to Last.fm if nothing valid is left.
    """
    chosen = []
    for name in names:
        if name in PROVIDERS:
            purpose = "top" if setting_name == "TOP_TRACK_SOURCES" else "similar"
            if not source_has_key(name, purpose):
                continue   # ticked but no key: skipped here, named by report_missing_keys
            chosen.append(PROVIDERS[name])
        else:
            print(f"Note: unknown source '{name}' in the setting {setting_name}, so it's ignored. "
                  f"Valid: {', '.join(PROVIDERS)}")
    if not chosen:
        print(f"Note: no usable sources in the setting {setting_name}, so Last.fm is used.")
        chosen.append(PROVIDERS["lastfm" if source_has_key("lastfm") else "deezer"])
    return chosen


def blend_lists(results, key_fn):
    """
    Merges ranked lists from several sources into one ranking.
    results: list of (source_name, [items]) in the order the sources were listed.
    Each item earns (n - position) points from each list it appears on, so an
    item high on two lists beats one high on one, and an item deep in three
    lists beats one midway in one. Ties keep first-seen order.
    Returns [(item, [source names that suggested it])], best first.
    """
    scores, sources, first_seen, display = {}, {}, {}, {}
    order = 0
    for source_name, items in results:
        n = len(items)
        for pos, item in enumerate(items):
            k = key_fn(item)
            if k not in scores:
                scores[k] = 0
                sources[k] = []
                first_seen[k] = order
                display[k] = item
                order += 1
            if source_name in sources[k]:
                continue   # a source votes once per item, even if it lists two versions
            scores[k] += n - pos
            sources[k].append(source_name)
    ranked = sorted(scores, key=lambda k: (-scores[k], first_seen[k]))
    return [(display[k], sources[k]) for k in ranked]


def artist_key(name):
    return norm_artist_text(canonicalise_conjunction(name)).lower().strip()


def owner_key(artist, key):
    """
    Who a found track counts against for 'at most N per artist': the artist as tagged
    in the library, so 'The Jimi Hendrix Experience' and 'Jimi Hendrix' share one
    allowance. Falls back to the source's name (YouTube output, or not in the cache).
    """
    try:
        import library   # here rather than at the top: library imports engine
        row = library.track_row(key) if key else None
        tagged = ((row or {}).get("Artist") or "").split(";")[0].strip()
        if tagged:
            return artist_key(tagged)
    except Exception:
        pass
    return artist_key(artist)


BLEND_DEPTH = 2   # ask each source for this many times the wanted count, so overlaps deeper down still merge


AGREEMENT_MIN_ARTISTS = 5   # relax the agreement number (never below 2) until this many artists survive


def blended_similar_artists(seed_artist, limit=20, seed_track=None, report=None):
    """
    Similar artists from every source in SIMILAR_SOURCES, blended.
    seed_artist may be a single name or a list of names (a multi-value
    Artist field split by split_values): each name is looked up on each
    source and the lists are merged, so the result is artists similar to
    ANY of the seeds. The seeds themselves are dropped from the result, since
    an alias like Dope Lemon is often 'similar' to Angus Stone.
    Returns ([(artist, sources)], label).
    """
    seeds = seed_artist if isinstance(seed_artist, list) else [seed_artist]
    seed_keys = {artist_key(s) for s in seeds}
    _youtube_hints.clear()
    providers = sources_from_settings(SIMILAR_SOURCES, "SIMILAR_SOURCES")
    fetch = min(limit * BLEND_DEPTH, 50) if len(providers) > 1 or len(seeds) > 1 else limit
    results, labels = [], []
    for seed in seeds:
        for service_name, similar_fn, _ in providers:
            kwargs, label = {}, service_name
            if similar_fn is listenbrainz_similar:
                algo_label, algo_string = listenbrainz_algorithm_from_settings()
                kwargs["algorithm"] = algo_string
                label = f"{service_name} ({algo_label.split(' - ')[0]})"
            if similar_fn is youtube_similar:
                # Seeded by the playing track; caches on artist + track itself so
                # its per-artist track picks are rebuilt on every run.
                names = youtube_similar(seed, limit=fetch, track=seed_track)
            else:
                names = cached_call(label, "similar", f"{artist_key(seed)}|{fetch}",
                                    lambda: similar_fn(seed, limit=fetch, **kwargs))
            debug(f"{service_name} similar artists for {seed}: {names}")
            if names:
                results.append((service_name, names))
                if label not in labels:
                    labels.append(label)
            else:
                why = f" ({AI_LAST_ERROR})" if service_name == "AI" and AI_LAST_ERROR else ""
                print(f"  Note: {service_name} returned no similar artists for {seed}{why}.")
    blended = [(a, s) for a, s in blend_lists(results, artist_key) if artist_key(a) not in seed_keys]
    responding = {service_name for service_name, _ in results}
    # The number can't exceed the sources that actually answered this time
    need = min(SIMILAR_MIN_AGREEMENT, len(responding))
    if need > 1:
        say = report or print
        everyone = blended
        want = min(limit, AGREEMENT_MIN_ARTISTS)
        while True:
            blended = [(a, s) for a, s in everyone if len(s) >= need]
            if len(blended) >= want or need <= 2:
                break
            say(f"  Only {len(blended)} artist{'' if len(blended) == 1 else 's'} agreed at {need}, "
                f"relaxed to {need - 1}.")
            need -= 1
        say(f"  Agreement: {len(blended)} of {len(everyone)} artists were suggested by {need} or more sources.")
    return blended[:limit], " + ".join(labels) if labels else "none"


TOP_TRACK_WORKERS = {"Deezer": 2}   # artists fetched at once, per source (Deezer allows 50 requests per 5 s)
TOP_TRACK_WORKERS_DEFAULT = 4


def top_track_plan(limit):
    """
    Which sources supply top tracks, and how deep to ask each one. Used by BOTH
    blended_top_tracks and prefetch_top_tracks, so the prefetch always stores its
    answers under the labels the main run looks them up by.
    """
    # YouTube has no top-tracks list, so it sits out here even if .env names it
    providers = [p for p in sources_from_settings(TOP_TRACK_SOURCES, "TOP_TRACK_SOURCES") if p[2]]
    if not providers:
        providers = [PROVIDERS["lastfm"]]
    fetch = min(limit * BLEND_DEPTH, 50) if len(providers) > 1 else limit
    return providers, fetch


def top_track_cache_key(artist, fetch):
    return f"{artist_key(artist)}|{fetch}"


def _safe_top_tracks(top_tracks_fn, artist, fetch):
    try:
        return top_tracks_fn(artist, limit=fetch) or []
    except Exception as e:
        debug(f"Top tracks failed for {artist}: {e}")
        return []


def prefetch_top_tracks(artists, limit, report=None):
    """
    Warms the top-tracks cache for many artists at once, so the one-artist-at-a-
    time loop that follows is served from the cache. Worker threads only make
    internet calls; every database read and write happens here, on the calling
    thread. Anything already cached is skipped, so a repeat run starts no threads.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    providers, fetch = top_track_plan(limit)
    artists = list(dict.fromkeys(artists))
    work = {}   # service name -> (top_tracks_fn, [(artist, cache key)])
    for service_name, _, top_tracks_fn in providers:
        jobs = [(a, top_track_cache_key(a, fetch)) for a in artists]
        jobs = [(a, k) for a, k in jobs if cache_get(service_name, "top_tracks", k) is None]
        if jobs:
            work[service_name] = (top_tracks_fn, jobs)
    if not work:
        return
    if report:
        count = len({a for _, jobs in work.values() for a, _ in jobs})
        report(f"  Fetching top tracks for {count} artists from {', '.join(work)}, several at a time...")
    load_known_mbids()   # read the saved MusicBrainz IDs here, so no worker thread touches the database
    started = time.time()
    pools, direct, staged = [], [], []

    for service_name, (top_tracks_fn, jobs) in work.items():
        workers = TOP_TRACK_WORKERS.get(service_name, TOP_TRACK_WORKERS_DEFAULT)
        pool = ThreadPoolExecutor(max_workers=workers)
        pools.append(pool)
        if top_tracks_fn is listenbrainz_top_tracks:
            # Stage 1: MusicBrainz IDs in ONE lane, paced. Stage 2: the ListenBrainz request
            # for each artist is handed to the pool as soon as its ID is known.
            lane = ThreadPoolExecutor(max_workers=1)
            pools.append(lane)

            def resolve_then_fetch(artist, pool=pool, fn=top_tracks_fn):
                musicbrainz_artist_id(artist)
                return pool.submit(_safe_top_tracks, fn, artist, fetch)

            staged = [(service_name, key, lane.submit(resolve_then_fetch, artist)) for artist, key in jobs]
        else:
            direct += [(service_name, key, pool.submit(_safe_top_tracks, top_tracks_fn, artist, fetch))
                       for artist, key in jobs]

    remaining = {name: len(jobs) for name, (_, jobs) in work.items()}

    def store(service_name, key, names):
        if names:
            cache_put(service_name, "top_tracks", key, names)
        remaining[service_name] -= 1
        if report and remaining[service_name] == 0:
            debug(f"{service_name} top tracks done in {time.time() - started:.0f} s")

    by_future = {f: (s, k) for s, k, f in direct}
    for future in as_completed(by_future):
        service_name, key = by_future[future]
        store(service_name, key, future.result())
    for service_name, key, outer in staged:
        try:
            names = outer.result().result()
        except Exception as e:
            print(f"  Problem: {service_name} didn't answer for top tracks ({e}).")
            names = []
        store(service_name, key, names)
    for pool in pools:
        pool.shutdown()


def blended_top_tracks(artist, limit=10):
    """Top tracks from every source in TOP_TRACK_SOURCES, blended. Returns ([(track, sources)], label)."""
    providers, fetch = top_track_plan(limit)   # shared with prefetch_top_tracks
    results, labels = [], []
    for service_name, _, top_tracks_fn in providers:
        names = cached_call(service_name, "top_tracks", top_track_cache_key(artist, fetch),
                            lambda: top_tracks_fn(artist, limit=fetch))
        debug(f"{service_name} top tracks: {names}")
        if names:
            results.append((service_name, names))
            labels.append(service_name)
        else:
            debug(f"{service_name} returned no top tracks")
    return blend_lists(results, clean_name)[:limit], " + ".join(labels) if labels else "none"


# ---------------------------------------------------------------------------
# JRiver Search Functions
# ---------------------------------------------------------------------------

def get_verified_keys_for_artist(artist_name, pool=None, pick=None):
    """
    Library-order fallback, no longer used by the playlist modes (they use
    pick_top_tracks_for_artist, which ranks via the Top-track sources).
    Searches the JRiver library for tracks by the given artist and returns
    `pick` keys chosen at random from the first `pool` matches. Both default
    to the TRACKS_PER_ARTIST_* settings. Pass pick=None with a pool to get
    the whole pool in library order.
    """
    pool = pool or TRACKS_PER_ARTIST_POOL
    try:
        items, search_term = jriver_search_artist_items(artist_name)
        keys = []
        pattern = re.compile(rf'\b{re.escape(search_term)}\b', re.IGNORECASE)
        for item in items:
            fields = {f.get("Name"): f.text for f in item.findall("Field") if f.text}
            if artist_matches(pattern, fields) and fields.get("Key"):
                keys.append(fields.get("Key"))

        top_n = keys[:pool]
        if pick is None and pool != TRACKS_PER_ARTIST_POOL:
            return top_n
        pick = pick or TRACKS_PER_ARTIST_PICK
        return random.sample(top_n, min(pick, len(top_n)))

    except Exception as e:
        print(f"  Problem: the JRiver library search failed for {artist_name} ({e}).")
        return []


def find_jriver_key_by_track(artist_name, track_name):
    """
    Looks up a specific track in JRiver by artist and track name.
    Uses fuzzy matching to handle remaster tags, live versions, feat. credits etc.
    """
    if output_is_youtube():   # no library check: the "key" is the YouTube video ID
        return youtube_video_id(artist_name, track_name)
    clean_track = clean_name(track_name)

    def search(artist):
        items, search_term = jriver_search_artist_items(artist)
        artist_pattern = re.compile(rf'\b{re.escape(search_term)}\b', re.IGNORECASE)
        for item in items:
            fields = {f.get("Name"): f.text for f in item.findall("Field") if f.text}
            actual_track = fields.get("Name", "") or fields.get("Title", "")
            if artist_matches(artist_pattern, fields) and clean_name(actual_track) == clean_track:
                return fields.get("Key"), items, search_term
        return None, items, search_term

    try:
        key, items, search_term = search(artist_name)
        if key:
            return key
        # 'Paul McCartney & Wings' misses a library tagged 'Paul McCartney': try the first-named act
        primary = primary_artist(artist_name)
        if primary:
            key, _, _ = search(primary)
            if key:
                debug(f"Matched on primary artist: {artist_name} - {track_name} (as {primary})")
                return key
        # 'The Jimi Hendrix Experience' against a library tagged 'Jimi Hendrix', or the other
        # way round: the library cache's matcher finds a name inside the credit, title matching
        try:
            import library   # here rather than at the top: library imports engine
            key = library.find_track_key(artist_name, track_name)
        except Exception:
            key = None
        if key:
            return key
        if DEBUG:
            sample = []
            for item in items[:5]:
                fields = {f.get("Name"): f.text for f in item.findall("Field") if f.text}
                sample.append(f"{fields.get('Artist')!r} / {fields.get('Name')!r}")
            debug(f"no match for {artist_name!r} / {track_name!r} (term {search_term!r}, "
                  f"{len(items)} items; first: {'; '.join(sample) or 'none'})")
    except Exception as e:
        print(f"  Problem: the JRiver library search failed for {track_name} ({e}).")
    return None


def pick_top_tracks_for_artist(artist, session_id, suggested_by, report=print,
                               exclude_track=None, consider=None, pick=None, defer=None, found=None):
    """
    The per-artist step shared by Similar Artists and the Vibe backfill:
    ask the Top-track sources for the artist's top `consider` tracks, randomly
    pick `pick` of those, then look each one up in the library. Hits are
    returned as file keys; every pick, hit or miss, is logged to the session
    so Discover shows exactly which tracks were chosen and which are missing.
    exclude_track: a track name to leave out (the one that's playing).
    found: a list to append (artist, track, key) to for every hit (Drift seeds from them).
    Returns (keys found, number of misses).
    """
    consider = consider or TRACKS_PER_ARTIST_POOL
    pick = pick or TRACKS_PER_ARTIST_PICK
    fetch = consider + 1 if exclude_track else consider
    top, _ = blended_top_tracks(artist, limit=fetch)
    names = [t for t, _ in top]
    if exclude_track:
        skip = clean_name(exclude_track)
        names = [t for t in names if clean_name(t) != skip]
    names = names[:consider]
    # YouTube's own picks for this artist (from up next) join the pool, with the
    # same chance as the rest (no guaranteed slot since 1.5.0: Last.fm's picks are better)
    if "YouTube" in (suggested_by or []):
        have = {clean_name(n) for n in names}
        added = [h for h in youtube_hints_for(artist, exclude_track) if clean_name(h) not in have]
        if added:
            names.extend(added)
            debug(f"YouTube pick in the pool: {', '.join(added)}")
    if not names:
        report(f"    No top tracks returned for {artist}.")
        return [], 0
    chosen = random.sample(names, min(pick, len(names)))
    if defer is not None:
        # YouTube output: the caller looks every pick up together at the end (much faster)
        defer.extend((artist, t, suggested_by, session_id) for t in chosen)
        return [], 0
    prefetch_youtube_ids([(artist, t) for t in chosen])
    keys, misses = [], 0
    for track_name in chosen:
        key = find_jriver_key_by_track(artist, track_name)
        if key:
            report(f"    In library: {track_name}")
            keys.append(key)
            if found is not None:
                found.append((artist, track_name, key))
        else:
            report(f"    Not in library: {track_name}")
            misses += 1
        session_log(session_id, artist, track_name, suggested_by, found=bool(key))
    return keys, misses


# ---------------------------------------------------------------------------
# Mode 1: Similar Artist Playlist
# ---------------------------------------------------------------------------


# --- Output target: JRiver (default) or YouTube ------------------------------
# With YouTube as the output, the modes run exactly as before, but a track's
# "key" is its YouTube video ID instead of a JRiver file key, and sending the
# playlist opens it in the browser instead of queueing it in JRiver.

YOUTUBE_LOOKUP_WORKERS = 8      # video ID lookups run this many at a time


def output_is_youtube():
    return OUTPUT_TARGET == "youtube" and not OUTPUT_OVERRIDE


def sending_message(count, detail=""):
    """The log line announcing where a finished playlist is going."""
    if output_is_youtube():
        return f"  Sending {min(count, YOUTUBE_PLAYLIST_LENGTH)} tracks to YouTube{detail}..."
    return f"  Sending {count} tracks{detail}..."


def _youtube_search_video_id(artist, track):
    """One uncached YouTube Music search. Returns a video ID only when the artist matches."""
    yt = youtube_client()
    if yt is None:
        return None
    try:
        results = yt.search(f"{artist} {track}", filter="songs", limit=5)
    except Exception as e:
        debug(f"YouTube search failed for {artist} - {track}: {e}")
        return None
    best, best_score = None, 0
    for r in results or []:
        if not r.get("videoId"):
            continue
        if not any(_youtube_same_artist(n, artist) for n in _youtube_artist_names(r)):
            continue   # right song, wrong act: a cover is worse than a gap
        score = 2 + (1 if clean_name(r.get("title") or "") == clean_name(track) else 0)
        if score > best_score:
            best, best_score = r, score
    if best and PREFER_OFFICIAL_VIDEOS:
        return _youtube_official_video(yt, best["videoId"], artist, track) or best["videoId"]
    return best["videoId"] if best else None


def _video_title(s):
    """A video title cleaned for matching: clean_name, then any trailing 'Official Video' or 'M/V'."""
    s = clean_name(s)
    return re.sub(r'\s+(official\s+)?(music\s+)?(video|mv|m v)$', '', s).strip()


def _youtube_official_video(yt, song_id, artist, track):
    """
    The official music video for a song, or None. YouTube Music's own song/video
    link first (the counterpart), then a video search for an official video (OMV)
    by the same artist with a matching title. Fan uploads are never used.
    """
    try:
        watch = yt.get_watch_playlist(videoId=song_id, limit=1)
        for t in (watch or {}).get("tracks", [])[:1]:
            vid = (t.get("counterpart") or {}).get("videoId")
            if vid:
                return vid
    except Exception as e:
        debug(f"YouTube counterpart lookup failed for {artist} - {track}: {e}")
    try:
        results = yt.search(f"{artist} {track}", filter="videos", limit=5)
    except Exception as e:
        debug(f"YouTube video search failed for {artist} - {track}: {e}")
        return None
    want = _video_title(track)
    for r in results or []:
        if r.get("videoType") != "MUSIC_VIDEO_TYPE_OMV" or not r.get("videoId"):
            continue
        if not any(_youtube_same_artist(n, artist) for n in _youtube_artist_names(r)):
            continue
        if _video_title(r.get("title") or "") == want:
            return r["videoId"]
    return None


def _youtube_id_kind():
    """Cache category: audio and official-video answers are kept apart."""
    return "video_id_omv" if PREFER_OFFICIAL_VIDEOS else "video_id"


def _youtube_id_cache_key(artist, track):
    return f"{artist_key(artist)}|{clean_name(track)}"


def youtube_video_id(artist, track):
    """The YouTube video ID for a track (cached), or None if YouTube has no match by that artist."""
    hit = cached_call("YouTube", _youtube_id_kind(), _youtube_id_cache_key(artist, track),
                      lambda: [vid] if (vid := _youtube_search_video_id(artist, track)) else [])
    return hit[0] if hit else None


def prefetch_youtube_ids(pairs):
    """
    Warms the video ID cache for [(artist, track)] several lookups at a time, so
    the one-by-one lookups that follow are instant. Does nothing unless the
    output is YouTube. The database is only touched from the calling thread.
    """
    if not output_is_youtube():
        return
    todo = [(a, t) for a, t in dict.fromkeys(pairs)
            if cache_get("YouTube", _youtube_id_kind(), _youtube_id_cache_key(a, t)) is None]
    if len(todo) < 2 or youtube_client() is None:
        return
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=YOUTUBE_LOOKUP_WORKERS) as pool:
        found = list(pool.map(lambda p: _youtube_search_video_id(*p), todo))
    for (a, t), vid in zip(todo, found):
        if vid:
            cache_put("YouTube", _youtube_id_kind(), _youtube_id_cache_key(a, t), [vid])


YOUTUBE_PLAYLIST_MAX = 50   # the most videos one watch_videos link will take


def youtube_ids_for_pairs(pairs):
    """
    Video IDs for [(artist, track)], in the same order (None where YouTube has no
    match by that artist). Cached answers are used first; the rest are looked up
    several at a time, whatever the Output setting. For Discover's playlists.
    """
    ids, todo = {}, []
    for pair in dict.fromkeys(pairs):
        hit = cache_get("YouTube", _youtube_id_kind(), _youtube_id_cache_key(*pair))
        if hit is None:
            todo.append(pair)
        else:
            ids[pair] = hit[0] if hit else None
    if todo and youtube_client() is not None:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=YOUTUBE_LOOKUP_WORKERS) as pool:
            found = list(pool.map(lambda p: _youtube_search_video_id(*p), todo))
        for pair, vid in zip(todo, found):
            cache_put("YouTube", _youtube_id_kind(), _youtube_id_cache_key(*pair), [vid] if vid else [])
            ids[pair] = vid
    return [ids.get(pair) for pair in pairs]


def open_youtube_playlist(video_ids):
    """Opens the IDs as an instant YouTube playlist in the browser. Returns how many went."""
    import webbrowser
    ids = list(dict.fromkeys(v for v in video_ids if v))[:YOUTUBE_PLAYLIST_LENGTH]
    if ids:
        webbrowser.open("https://www.youtube.com/watch_videos?video_ids=" + ",".join(ids))
    return len(ids)


def typed_seed_info(artist, track=""):
    """A seed typed into the Search tab, shaped like get_playing_info() so every mode can use it."""
    return {"Artist": (artist or "").strip(), "Name": (track or "").strip(), "Album": "",
            "PlayingNowPosition": "0", "PlayingNowTracks": "0", "Typed": True}


def typed_seed_key(seed_info, seeds, session_id, report=print):
    """
    For a searched (typed) seed: the seed track's library key, so it can open
    the playlist. Logged to the session either way, so a searched track you
    don't own lands in Discover. Returns None for a now-playing seed.
    """
    name = seed_info.get("Name")
    if not seed_info.get("Typed") or not name:
        return None
    what = "Last played track" if seed_info.get("LastPlayed") else "Searched track"
    for seed in seeds:
        key = find_jriver_key_by_track(seed, name)
        if key:
            report(f"  {what} found on YouTube, so it opens the playlist." if output_is_youtube()
                   else f"  {what} is in your library, so it opens the playlist.")
            session_log(session_id, seed, name, ["seed"], found=True)
            return key
    report(f"  {what} wasn't found on YouTube, so the playlist starts without it." if output_is_youtube()
           else f"  {what} isn't in your library, so the playlist starts without it.")
    session_log(session_id, seeds[0], name, ["seed"], found=False)
    return None


def jriver_is_stopped(zone=ACTIVE_ZONE):
    """True only when the zone clearly reports it is stopped. Any doubt counts as 'not stopped'."""
    try:
        r = requests.get(f"{JRIVER_BASE}/Playback/Info", params={"Zone": zone}, auth=AUTH)
        for item in ET.fromstring(r.text).findall("Item"):
            if item.get("Name") == "State":
                return (item.text or "").strip() == "0"
    except Exception:
        pass
    return False



# --- voice takeover ----------------------------------------------------------
# A voice build treats a paused zone as free (after "Alexa, stop" the Sonos is
# paused, not stopped), and a newer voice command for the same zone stops the
# older build. The Play tab is unaffected: both flags are only set by voice.py.

VOICE_TAKEOVER = False   # True while a voice build runs
MIX_ROWS = None          # the Play tab's added playlists for this build; None for voice, shortcuts, non-stop
MIX_KEEP = set()         # keys from those playlists: the hidden-track check leaves them alone
REVIEW_MODE = False      # True while an app build runs as Review: tracks are collected, JRiver is left alone
REVIEW_KEYS = []         # the tracks a Review build found, in order, for the Review view
REVIEW_ZONE = None       # the zone they'd go to (the Output zone)


def review_reset():
    """Called as a Review build starts: an empty list, and nothing in JRiver touched."""
    globals()["REVIEW_KEYS"] = []
    globals()["REVIEW_ZONE"] = None
    globals()["REVIEW_ROWS"] = []


REVIEW_ROWS = []         # the Review list's rows, made from REVIEW_KEYS when the build finishes


def review_rows(keys):
    """The Review list's rows: artist, title, album, length and BPM for each track, from the library."""
    import library   # here rather than at the top: it imports engine
    try:
        library.ensure_loaded()
    except Exception:
        pass
    rows = []
    for k in keys:
        row = library.track_row(k) or {}
        try:
            seconds = float(row.get("Duration") or 0)
        except ValueError:
            seconds = 0
        bpm = (row.get("BPM") or "").strip()
        try:
            bpm = str(round(float(bpm))) if bpm and float(bpm) > 0 else ""
        except ValueError:
            bpm = ""
        rows.append({"key": str(k), "artist": row.get("Artist", ""), "title": row.get("Name", "") or f"Track {k}",
                     "album": row.get("Album", ""), "seconds": seconds, "bpm": bpm})
    return rows


REVIEW_ACTIONS = {
    "next": "Add as Up Next",
    "end": "Add to End",
    "finish": "Finish This Song, Load as New",
    "stop": "Stop Song, Load as New",
}


def review_send(keys, how, zone):
    """
    Sends the ticked Review tracks to a zone, in tick order. how:
      next    after the current song, then the rest of Playing Now carries on
      end     after everything already in Playing Now
      finish  the current song finishes, then Playing Now holds only these
      stop    the current song stops and these play now; Playing Now holds only these
    A stopped zone: the Adds just add; both Load as New choices start these playing.
    Returns the console line.
    """
    keys = [str(k) for k in keys if k]
    if not keys:
        return "Review: nothing ticked, so nothing sent."
    label = zone_label(zone)
    n = f"{len(keys)} track{'' if len(keys) == 1 else 's'}"
    if how == "next":
        requests.get(f"{JRIVER_BASE}/Playback/PlayByKey",
                     params={"Key": ",".join(keys), "Location": "Next", "Zone": zone}, auth=AUTH, timeout=10)
        return f"Review: {n} added as Up Next in {label}."
    if how == "end":
        queue_tracks(keys, zone)
        return f"Review: {n} added to the end of Playing Now in {label}."
    was_playing = not jriver_is_stopped(zone)
    if was_playing and how == "finish":
        clear_around_current(zone)
        queue_tracks(keys, zone)
        return f"Review: {n} loaded as new in {label}, after the song playing now."
    if was_playing:   # Stop Song: stop, empty Playing Now, then load and play as a stopped zone does
        requests.get(f"{JRIVER_BASE}/Playback/Stop", params={"Zone": zone}, auth=AUTH, timeout=10)
        clear_around_current(zone)
        remove_from_playing_now(0, zone)   # the song that was playing
    requests.get(f"{JRIVER_BASE}/Playback/PlayByKey",
                 params={"Key": ",".join(keys), "Zone": zone}, auth=AUTH, timeout=10)
    if was_playing:
        return f"Review: song stopped, {n} loaded as new in {label}, playing now."
    return f"Review: {n} loaded as new in {label}, playing now."


def playlist_exists(name):
    """True when JRiver already has a playlist (not a smartlist) with this name or path."""
    try:
        r = requests.get(f"{JRIVER_BASE}/Playlists/List", auth=AUTH, timeout=10)
        for item in ET.fromstring(r.text).findall(".//Item"):
            f = {x.get("Name"): (x.text or "") for x in item.findall("Field")}
            if f.get("Type") == "Playlist" and name.lower() in (f.get("Name", "").lower(), f.get("Path", "").lower()):
                return True
    except Exception:
        pass
    return False


def review_save(keys, name):
    """Saves the ticked Review tracks, in tick order, as a JRiver playlist. Replaces one of that name."""
    keys = [str(k) for k in keys if k]
    r = requests.get(f"{JRIVER_BASE}/Playlists/Add",
                     params={"Type": "Playlist", "Path": name, "CreateMode": "Overwrite"}, auth=AUTH, timeout=10)
    pid = ""
    try:
        pid = next((i.text or "").strip() for i in ET.fromstring(r.text).findall("Item")
                   if i.get("Name") == "PlaylistID")
    except (ET.ParseError, StopIteration):
        pass
    if not pid:
        raise RuntimeError("JRiver didn't create the playlist")
    r = requests.get(f"{JRIVER_BASE}/Playlist/AddFiles",
                     params={"PlaylistType": "ID", "Playlist": pid, "Keys": ",".join(keys)}, auth=AUTH, timeout=10)
    r.raise_for_status()
    n = f"{len(keys)} track{'' if len(keys) == 1 else 's'}"
    return f"Review: {n} saved as the JRiver playlist \"{name}\"."


def review_preview(key, zone):
    """Plays one Review track in the preview zone. Its Playing Now holds just that track."""
    r = requests.get(f"{JRIVER_BASE}/Playback/PlayByKey", params={"Key": str(key), "Zone": zone},
                     auth=AUTH, timeout=10)
    r.raise_for_status()


def review_preview_stop(zone):
    """Stops the preview zone."""
    if zone is not None:
        requests.get(f"{JRIVER_BASE}/Playback/Stop", params={"Zone": zone}, auth=AUTH, timeout=10)
MIX_FAST_KEY = None      # an Add before playlist's first track, started by fast start
MIX_NOTED = False        # the "left out on YouTube" note has been logged this build
CANCEL_CHECK = None      # set by voice.py: returns True once a newer command has taken over


class BuildCancelled(BaseException):
    """A newer voice command took over. BaseException so no 'except Exception' swallows it."""


def check_cancelled():
    if CANCEL_CHECK is not None and CANCEL_CHECK():
        raise BuildCancelled()


def zone_state(zone=ACTIVE_ZONE):
    """JRiver's playback state for a zone: 0 stopped, 1 paused, 2 playing, 3 waiting; None if unknown."""
    try:
        r = requests.get(f"{JRIVER_BASE}/Playback/Info", params={"Zone": zone}, auth=AUTH, timeout=10)
        for item in ET.fromstring(r.text).findall("Item"):
            if item.get("Name") == "State":
                return int((item.text or "").strip())
    except Exception:
        pass
    return None


def zone_is_free(zone=ACTIVE_ZONE):
    """Stopped. A voice build always takes the zone over, whatever JRiver reports
    (after "Alexa, stop" the Sonos is paused but JRiver can still say playing)."""
    if not VOICE_TAKEOVER:
        return jriver_is_stopped(zone)
    return True


def output_zone(seed_info=None, zone_name=None, report=print):
    """
    The JRiver zone a playlist goes to, as a zone ID. zone_name (for voice
    commands) beats the Output setting. "Same zone" follows the seed: the
    Now Playing zone for a now-playing seed, the active zone for a typed one,
    and the Now Playing tab's zone for a run with no seed (Vibe). Returns None,
    after a log line, when a named zone can't be found.
    """
    name = zone_name or OUTPUT_OVERRIDE or (OUTPUT_TARGET[5:] if OUTPUT_TARGET.startswith("zone:") else None)
    if name:
        zid = zone_id(name)
        if zid is None:
            report(f"Problem: the output zone '{name}' isn't in JRiver, so nothing was sent. "
                   f"Pick another under Output.")
        return zid
    if seed_info and seed_info.get("Typed"):
        # a last-played seed (Playing Now was empty) goes back to the zone it was read for
        return seed_info.get("ZoneID") or zone_id()
    if seed_info and seed_info.get("ZoneID"):
        return seed_info["ZoneID"]
    zid = seed_zone()
    if zid is None:
        report("Problem: the Now Playing zone isn't in JRiver, so nothing was sent. Pick another under Zone.")
        return None
    return zone_id() if zid == ACTIVE_ZONE else zid


def drop_long_closers(keys, keep=(), report=print, group=None):
    """
    The hidden-track check (Settings > Playlist > All playlists). Leaves out any
    track that is the last one on its album and runs longer than
    LONG_CLOSER_MINUTES: those are the files most likely to hide a bonus track
    after a long silence (System Of A Down's "Aerials" is 6:11 with one, 3:55
    without). keep: keys never dropped, i.e. the seed track. Each skip is logged.
    """
    # each Play option has its own setting: group, else the build in progress, else Artist's Top Tracks
    on, minutes = LONG_CLOSERS.get(group or NONSTOP_CONTEXT.get("kind") or "top",
                                   (SKIP_LONG_CLOSERS, LONG_CLOSER_MINUTES))
    if not on or not keys:
        return keys
    try:
        import library   # here rather than at the top: library imports engine
        library.ensure_loaded()
    except Exception as e:
        report(f"  Note: the hidden track check didn't run, as the library couldn't be read ({e}).")
        return keys
    limit = minutes * 60
    keep = {str(k) for k in keep if k}
    kept = []
    for key in keys:
        closer = library.closer_info(key)
        if closer and str(key) not in keep and closer[0] > limit:
            seconds, name, artist = closer
            length = f"{int(seconds) // 60}:{int(seconds) % 60:02d}"
            report(f"  Skipped {name} by {artist}: last on its album and {length} long.")
            globals()["CLOSERS_DROPPED"] = CLOSERS_DROPPED + 1
            continue
        kept.append(key)
    return kept


def send_to_jriver(keys, typed=False, seed_info=None, report=print, zone_name=None, append=False,
                   closer_group=None):
    """
    Sends a finished playlist to the output zone, or opens it on YouTube.
      - A stopped zone gets the playlist as its new Playing Now, and it starts.
      - A busy zone keeps its current track; the playlist is queued after it.
      - A now-playing seed sent to a different zone: the seed track opens the
        playlist there.
      - append=True (after a fast start, or a Drift round): the tracks go on the
        end of Playing Now and nothing already there is touched.
    One function for the Play tab and, later, voice commands (zone_name).
    """
    global LAST_OUTPUT
    check_cancelled()
    if output_is_youtube() and not zone_name:   # JRiver is left completely alone
        LAST_OUTPUT = "YouTube"
        if keys and not append:
            open_youtube_playlist(keys)
        return
    if seed_info is not None:
        typed = bool(seed_info.get("Typed"))
    zone = output_zone(seed_info, zone_name, report)
    if zone is None:
        return
    LAST_OUTPUT = zone_label(zone)
    globals()["LAST_OUTPUT_ID"] = zone
    keys = [str(k) for k in keys]
    seed_key = str((seed_info or {}).get("FileKey") or "")
    keys = drop_long_closers(keys, keep=[seed_key, *MIX_KEEP], report=report, group=closer_group)
    if REVIEW_MODE and not VOICE_TAKEOVER and not NONSTOP_APPEND:   # Review: collect, send nothing
        globals()["REVIEW_ZONE"] = zone
        for k in keys:
            if k not in REVIEW_KEYS:
                REVIEW_KEYS.append(k)
        return
    if NONSTOP_APPEND:   # a non-stop top-up only ever adds, and never repeats what the zone already had
        sent = nonstop_sent(zone)
        fresh_keys = [k for k in keys if k not in sent]
        if keys and not fresh_keys:
            report("  Note: nothing new to add, as every track found had already been sent to this zone.")
        keys, append = fresh_keys, True
    nonstop_record(zone, keys, append)
    if append:
        if keys:
            queue_tracks(keys, zone)
            debug(f"Added {len(keys)} track{'' if len(keys) == 1 else 's'} to {zone_label(zone)}")
        return
    seed_zone_id = (seed_info or {}).get("ZoneID")
    if seed_info and not typed and seed_key and seed_zone_id and seed_zone_id != zone:
        keys = [seed_key] + [k for k in keys if k != seed_key]
        report("  Seed track opens the playlist, as it's going to a different zone.")
    if not keys:
        return
    if zone_is_free(zone):
        if VOICE_TAKEOVER:
            debug(f"Voice command: the playlist takes over {zone_label(zone)} now")
        else:
            debug(f"{zone_label(zone)} was stopped, so the playlist starts there now")
        requests.get(f"{JRIVER_BASE}/Playback/PlayByKey",
                     params={"Key": ",".join(keys), "Zone": zone}, auth=AUTH)
        return
    report(f"  Queued in {zone_label(zone)} after the current track.")
    clear_around_current(zone)
    queue_tracks(keys, zone)


SEED_ARTIST_SHARE = 0.25   # the seed artist's share of a YouTube queue playlist
SEED_ARTIST_FLOOR = 3      # but never fewer than this many of their tracks


def cap_seed_artist(keys, seed_artist_keys, first_key=None):
    """
    Keeps the seed artist to about SEED_ARTIST_SHARE of a YouTube queue playlist.
    YouTube weaves the seed artist through roughly every fourth track; a library
    check strips out the other artists' tracks you don't own but keeps all of
    the seed artist's, which tips the balance. The kept tracks are spread evenly
    so they stay woven through. A searched seed track (first_key) counts towards
    the share and is never dropped. Returns (keys, number dropped).
    """
    others = len(keys) - len(seed_artist_keys) - (1 if first_key else 0)
    if others <= 0 or not seed_artist_keys:
        return keys, 0
    allowed = max(SEED_ARTIST_FLOOR, round(others * SEED_ARTIST_SHARE / (1 - SEED_ARTIST_SHARE)))
    allowed = max(1, allowed - (1 if first_key else 0))
    if len(seed_artist_keys) <= allowed:
        return keys, 0
    step = len(seed_artist_keys) / allowed
    kept = {seed_artist_keys[int(i * step)] for i in range(allowed)}
    drop = set(seed_artist_keys) - kept
    return [k for k in keys if k not in drop], len(drop)


def resolve_deferred_picks(deferred, report=print, found=None):
    """
    YouTube output: looks up every pick collected during a Similar Artists run
    in one parallel burst, then reports and logs them in the order they were
    picked. deferred is [(artist, track, suggested_by, session_id)].
    Returns the video IDs found.
    """
    prefetch_youtube_ids([(artist, track) for artist, track, _, _ in deferred])
    keys = []
    for artist, track, suggested_by, session_id in deferred:
        key = find_jriver_key_by_track(artist, track)   # a cache hit after the prefetch
        report(f"    {'On YouTube' if key else 'Not on YouTube'}: {artist} - {track}")
        session_log(session_id, artist, track, suggested_by, found=bool(key))
        if key and key not in keys:
            keys.append(key)
            if found is not None:
                found.append((artist, track, key))
    return keys


def create_youtube_queue_playlist(seed_info, seeds, report=print):
    """
    YouTube ticked on its own: plays YouTube Music's up next queue as is.
    Each track is looked up in the library and the hits are queued in
    YouTube's order, with no artist blend, top tracks, shuffle or trimming.
    The seed artist's other songs stay in (YouTube weaves them through on
    purpose); only the playing track is skipped. Hits and misses are logged
    to Discover under their own session type.
    """
    track = seed_info.get("Name")
    report("  YouTube is the only source ticked: playing its up next queue as is.")
    session_id = session_start("youtube_queue", seed_info, "YouTube")
    first_key = typed_seed_key(seed_info, seeds, session_id, report)

    pairs = []
    for seed in seeds:
        pairs = youtube_up_next(seed, track)
        if pairs:
            break
    if not pairs:
        report("  Problem: YouTube returned no up next queue for this track.")
        session_finish(session_id, send_mix_only(None, seed_info, report), report=report)
        return

    prefetch_youtube_ids([(canonicalise_conjunction(p[0]), p[1]) for p in pairs
                          if isinstance(p, (list, tuple)) and len(p) == 2])
    playing = clean_name(track or "")
    keys, seen = ([first_key] if first_key else []), set()
    seed_artist_keys = []   # the seed artist's hits, so they can be kept in proportion
    for pair in pairs:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        raw_artist, title = pair
        if raw_artist.strip().lower() in YOUTUBE_SKIP_ARTISTS:
            continue
        artist = canonicalise_conjunction(raw_artist)
        ident = (artist_key(artist), clean_name(title))
        if ident in seen:
            continue
        seen.add(ident)
        if clean_name(title) == playing and any(_youtube_same_artist(raw_artist, s) for s in seeds):
            continue   # another version of the track that's playing
        key = find_jriver_key_by_track(artist, title)
        if key and key not in keys:
            keys.append(key)
            if any(_youtube_same_artist(raw_artist, s) for s in seeds):
                seed_artist_keys.append(key)
        report(f"    {'In library' if key else 'Not in library'}: {artist} - {title}")
        session_log(session_id, artist, title, ["YouTube"], found=bool(key))

    keys, dropped = cap_seed_artist(keys, seed_artist_keys, first_key)
    if dropped:
        report(f"  Seed artist kept to about a quarter of the playlist ({dropped} of their tracks left out).")
    queued = 0
    if mix_active():
        if not keys:
            report("Problem: nothing suggested is in your library.")
        keys = combine_with_mix(keys, report)
    mix_skipped(report)
    if keys:
        report(sending_message(len(keys), ", in YouTube's order"))
        send_to_jriver(keys, seed_info=seed_info, report=report)
        queued = len(keys)
        debug("Queue refreshed")
    else:
        report("Problem: nothing suggested is in your library.")
    session_finish(session_id, queued, sources="YouTube (up next queue)", report=report)


# ---------------------------------------------------------------------------
# AI Moderator (Play tab Off/Relaxed/Balanced/Strict; per device in Settings > Sources)
# ---------------------------------------------------------------------------

MODERATOR_MODEL = "claude-haiku-4-5-20251001"   # quick and cheap: one call per playlist (and per Drift round)
MODERATOR_CAP = {"relaxed": 0.2, "balanced": 0.4, "strict": 1.0}     # most of the tracks checked that can go
MODERATOR_EXTRA = {"relaxed": 0.2, "balanced": 0.4, "strict": 0.5}   # extra found up front, to replace removals

MODERATOR_RULES = {
    "relaxed": ("The playlist should feel like one continuous listening session. Small shifts\n"
                "in energy are fine and give a playlist shape. A track is a problem only if it\n"
                "would jolt a listener out of the mood the seed set. Only flag a track when you\n"
                "are confident it clashes. If unsure, keep it."),
    "balanced": ("The playlist should feel like one continuous listening session that stays\n"
                 "close to the seed. Flag any track that would noticeably shift the tone, energy\n"
                 "or mood away from the seed, even if it wouldn't jolt a listener outright: a\n"
                 "loud, driving track after a gentle seed, or a slow, reflective one after an\n"
                 "upbeat seed, should go. If unsure, keep it."),
    "strict": ("Keep only tracks that sit close to the seed in tone, energy and mood. Flag any\n"
               "track that differs noticeably on any one of the three, however good it is. A\n"
               "shorter playlist that holds together is better than a longer one that wanders."),
}

MODERATOR_PROMPT = """You are a playlist moderator for a personal music library. You will be given
a seed and a list of candidate tracks for a playlist built from it. The seed is
a track, or for a vibe playlist, a description of the mood wanted.

Your job is to find tracks that don't belong with the seed. Judge each track on
three things only:
- Tone: the emotional colour (warm, dark, melancholy, playful, defiant).
- Energy: intensity and pace (a gentle acoustic song versus a pounding anthem).
- Mood: the overall feeling a listener is in while it plays.

{level_rules}

Genre is not a reason to remove a track. A folk song and an electronic track
can sit together if they share tone, energy and mood. Two tracks in the same
genre can clash if they don't.

Rules:
- If you don't know an artist or track well enough to judge its sound, keep it.
- Judge the specific track, not the artist's general reputation.
- {limit_rule}
- For each track you flag, copy its number, artist and title exactly as they appear
  in the list. The reason must be about that same track.

Reply with JSON only, no other text:
{{"remove": [{{"number": <its number in the list>, "artist": "<artist as listed>", "title": "<title as listed>", "reason": "<one short sentence>"}}]}}
If nothing clashes, reply {{"remove": []}}."""


def moderator_level():
    """The level for the build in progress ('off' with no Anthropic key)."""
    # each Play option has its own level; the build in progress says which option it is
    kind = NONSTOP_CONTEXT.get("kind")
    level = AI_MODERATOR_BY.get(kind, "off") if kind else AI_MODERATOR
    if MODERATOR_OVERRIDE is not None:   # True/False for one run; a level name also works
        level = (MODERATOR_OVERRIDE if MODERATOR_OVERRIDE in MODERATOR_LEVELS else
                 (level if level != "off" else "balanced") if MODERATOR_OVERRIDE else "off")
    return level if (level in MODERATOR_LEVELS and ANTHROPIC_API_KEY) else "off"


def moderator_on():
    """The moderator runs when it's wanted (Play tab, or the device for voice) and there's a key."""
    return moderator_level() != "off"


def moderator_extra(target):
    """How many extra tracks to find up front, so the moderator's removals are replaced."""
    level = moderator_level()
    return max(1, int(target * MODERATOR_EXTRA[level])) if level != "off" else 0


def _name_key(text):
    """A name for comparing: lower case, letters and digits only (any script)."""
    return re.sub(r"[\W_]+", "", str(text or "").casefold())


def moderator_pick(tracks, item):
    """
    Which track one moderator flag means, as an index into tracks, or None to keep everything.
    The number is only trusted when the artist and title it points at match the ones named;
    a wrong number with a name in the list goes by the name. Mix-ups are noted at debug.
    """
    if not isinstance(item, dict):
        return None
    title, artist = _name_key(item.get("title")), _name_key(item.get("artist"))

    def same(track):
        a, t = _name_key(track[1]), _name_key(track[2])
        return bool(title) and t == title and (a == artist or (bool(artist) and (artist in a or a in artist)))

    try:
        n = int(item.get("number", item.get("index")))
    except (TypeError, ValueError):
        n = None
    named = f"{item.get('artist')} - {item.get('title')}"
    if not title:
        debug(f"AI Moderator: flag with no title kept nothing (number {n})")
        return None
    if n is not None and 1 <= n <= len(tracks) and same(tracks[n - 1]):
        return n - 1
    hits = [i for i, track in enumerate(tracks) if same(track)]
    pointed = (f"{tracks[n - 1][1]} - {tracks[n - 1][2]}" if n is not None and 1 <= n <= len(tracks)
               else "nothing")
    if len(hits) == 1:
        debug(f"AI Moderator: number {n} pointed at {pointed}, went by the name {named}")
        return hits[0]
    debug(f"AI Moderator: {named} " + ("is in the list more than once" if hits else "isn't in the list")
          + f" (number {n} pointed at {pointed}), so nothing was removed for it")
    return None


def moderator_reply(text):
    """
    The remove list from the moderator's reply: the first JSON object in it with a
    "remove" list, ignoring any text before or after (a code fence, a note of its own).
    Raises ValueError when the reply has no such JSON.
    """
    text = str(text or "")
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, end = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and "remove" in obj:
            extra = re.sub(r"```(?:json)?", "", text[:m.start()] + " " + text[end:]).strip()
            if extra:
                debug(f"AI Moderator: ignored text around the reply: {' '.join(extra.split())[:200]}")
            flagged = obj.get("remove") or []
            return flagged if isinstance(flagged, list) else []
    raise ValueError("no JSON in the reply")


def moderate(tracks, seed, report=print, level=None, reference=None):
    """
    Asks the moderator which tracks clash with the seed. tracks: [(key, artist, title)];
    seed: "Artist - Title", or "vibe: <description>". Returns the set of keys to
    remove, each logged with its reason. Any failure removes nothing, so a
    playlist is never lost to the moderator: it builds unmoderated, with a log line.
    level: a level for this check only (Drift's own); None uses the build's.
    reference: [(key, artist, title)] already in the playlist, shown as what fits.
    """
    level = level or moderator_level()
    if not ANTHROPIC_API_KEY or level not in MODERATOR_LEVELS:
        level = "off"
    if level == "off" or len(tracks) < 2:
        return set()
    cap = max(1, int(len(tracks) * MODERATOR_CAP[level]))
    limit_rule = ("Flag as many tracks as you need to." if level == "strict"
                  else f"Flag no more than {cap} tracks.")
    seed_line = f"Seed vibe: {seed[5:].strip()}" if seed.startswith("vibe:") else f"Seed: {seed}"
    listing = "\n".join(f"{n}. {artist} - {title}" for n, (_, artist, title) in enumerate(tracks, 1))
    ref_text = ""
    if reference:   # what's already passed: the playlist's sound, not just the seed's
        ref_text = ("\n\nAlready in the playlist, and they fit, so judge the candidates against these as "
                    "well as the seed:\n" + "\n".join(f"- {artist} - {title}" for _, artist, title in reference[:15]))
    report(f"  AI Moderator ({level.title()}): checking {len(tracks)} tracks against the seed"
           + (" and the playlist so far..." if reference else "..."))
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=MODERATOR_MODEL, max_tokens=2000,
            system=MODERATOR_PROMPT.format(level_rules=MODERATOR_RULES[level], limit_rule=limit_rule),
            messages=[{"role": "user", "content": f"{seed_line}{ref_text}\n\nCandidates:\n{listing}"}])
        record_ai("AI Moderator", MODERATOR_MODEL, message)
        text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
        flagged = moderator_reply(text)
    except ImportError:
        report("  Problem: AI Moderator didn't run, as the anthropic package isn't installed.")
        return set()
    except Exception as e:
        if "credit balance" in str(e).lower():
            report("  Problem: AI Moderator didn't run, as your Anthropic credit balance is too low.")
        else:
            report(f"  Problem: AI Moderator didn't run, as the check didn't come back ({str(e)[:120]}).")
        return set()
    removed = set()
    for item in flagged:
        if len(removed) >= cap:
            break
        i = moderator_pick(tracks, item)
        if i is None:
            continue
        key, artist, title = tracks[i]
        if key not in removed:
            removed.add(key)
            report(f"    Removed {artist} - {title}: {str(item.get('reason') or '').strip()}")
    report(f"  AI Moderator: {len(removed)} removed." if removed else "  AI Moderator: nothing clashed.")
    return removed


class PlayedFilter:
    """
    Skip tracks played recently (Settings > Playlist, per Play mode): a track
    JRiver played within the last N days isn't used. Reads Last Played from the
    library held in memory, so it costs nothing per track; that copy refreshes
    every half hour, so a track played in the last few minutes may still get in.
    keep: keys never skipped (the seed track). Counts what it skips for one log line.
    """

    def __init__(self, group, keep=(), report=print, setting=None, filters=False):
        self.on, self.days = setting or SKIP_PLAYED.get(group, (False, 1))
        self.keep = {str(k) for k in keep if k}
        self.report, self.skipped = report, 0
        self.filters = None
        self.closer_limit, self.closers_seen = None, set()
        if filters:   # the playlists 24bit7 builds: the hidden-track check as tracks are found, so
            # a skipped closer never takes a place in the playlist and the next track fills it
            on, minutes = LONG_CLOSERS.get(group, (SKIP_LONG_CLOSERS, LONG_CLOSER_MINUTES))
            if on:
                try:
                    import library   # here rather than at the top: library imports engine
                    library.ensure_loaded()
                    self.closer_library, self.closer_limit = library, minutes * 60
                except Exception as e:
                    report(f"  Note: the hidden track check didn't run, as the library couldn't be read ({e}).")
        if filters:   # Settings > Filters, for the playlists 24bit7 builds
            try:
                import filters as filter_settings
                self.filters = filter_settings.Active(FILTER_DEVICE, report) or None
            except Exception as e:
                report(f"  Problem: the filters didn't run ({e}).")
        if not self.on:
            return
        try:
            import library   # here rather than at the top: library imports engine
            library.ensure_loaded()
            self.library = library
        except Exception as e:
            report(f"  Note: the recently played check didn't run, as the library couldn't be read ({e}).")
            self.on = False
            return
        if library.played_dates_unreadable():
            report("  Note: the recently played check didn't run, as JRiver's Last Played dates couldn't be read.")
            self.on = False
        self.cutoff = time.time() - self.days * 86400

    def fresh(self, key):
        """False (and counted) for a track played within the set number of days."""
        if str(key) in self.keep:
            return True
        if self.closer_limit is not None:
            closer = self.closer_library.closer_info(key)
            if closer and closer[0] > self.closer_limit:
                if str(key) not in self.closers_seen:
                    self.closers_seen.add(str(key))
                    seconds, name, artist = closer
                    self.report(f"  Skipped {name} by {artist}: last on its album and "
                                f"{int(seconds) // 60}:{int(seconds) % 60:02d} long.")
                return False
        if self.filters is not None and not self.filters.allows(key):
            return False
        if not self.on:
            return True
        when = self.library.last_played(key)
        if when and when >= self.cutoff:
            self.skipped += 1
            return False
        return True

    def done(self):
        if self.filters is not None:
            self.filters.done()
        if self.skipped:
            self.report(f"  Skipped {self.skipped} track{'' if self.skipped == 1 else 's'} "
                        f"played in the last {self.days} day{'' if self.days == 1 else 's'}.")


# ---------------------------------------------------------------------------
# Fast start and Drift (shared by the playlist modes)
# ---------------------------------------------------------------------------

class FastStart:
    """
    Fast start: when the output zone is stopped, the first track found plays
    straight away and the rest of the playlist follows it into Playing Now.
    Only with JRiver output and a seed that isn't playing: a search, a voice
    command, a Vibe. The first track skips the Hidden Tracks check, for speed.
    """

    def __init__(self, seed_info=None, report=print, enabled=True):
        self.report, self.key, self.zone = report, None, None
        if not enabled or REVIEW_MODE or output_is_youtube() or (seed_info and not seed_info.get("Typed")):
            return   # YouTube output, or a now-playing seed (music is already playing)
        zone = output_zone(seed_info, None, lambda *_: None)
        if zone is not None and zone_is_free(zone):
            self.zone = zone
            self._start_with_before()

    def _start_with_before(self):
        """With an Add before playlist (Play tab), its first track is the one that starts."""
        global MIX_FAST_KEY
        row = next((r for r in (MIX_ROWS or []) if r.get("mode") == "before"), None)
        if row is None:
            return
        try:
            import saved_playlists   # here rather than at the top: it imports engine
            keys = saved_playlists.playlist_keys(row["id"])
        except Exception:
            return
        if keys:
            self.play(keys[0])
            if self.key:
                MIX_FAST_KEY = self.key

    @property
    def started(self):
        return self.key is not None

    def play(self, key):
        """Plays the first track found. Later calls do nothing."""
        check_cancelled()
        if self.zone is None or self.key or not key:
            return
        try:
            requests.get(f"{JRIVER_BASE}/Playback/PlayByKey",
                         params={"Key": str(key), "Zone": self.zone}, auth=AUTH, timeout=10)
        except Exception as e:
            self.report(f"  Note: fast start didn't go through ({e}), so the playlist starts when it's built.")
            self.zone = None
            return
        self.key = str(key)
        globals()["LAST_OUTPUT"] = zone_label(self.zone)
        globals()["LAST_OUTPUT_ID"] = self.zone
        debug(f"Fast start: the first track is playing in {zone_label(self.zone)} while the rest is found")

    def lead(self, keys, first_key=None):
        """Puts the playing (or searched) track at the front, once."""
        lead = self.key or (str(first_key) if first_key else None)
        if not lead:
            return list(keys)
        return [lead] + [k for k in keys if str(k) != lead]

    def rest(self, keys):
        """The playlist minus the track that's already playing."""
        return [k for k in keys if str(k) != self.key]


DRIFT_SEEDS_PER_ROUND = 3   # finds each Drift round seeds from


def drift_custom_sources(cfg, using):
    """A Drift's Custom Sources for this round as (codes, must agree), or None for Settings > Sources."""
    if not cfg.get("custom") or using not in ("artists", "tracks"):
        return None
    kind = "artist" if using == "artists" else "track"
    codes = cfg.get(f"{kind}_sources") or []
    return (codes, cfg.get(f"{kind}_agree", 1)) if codes else None


@contextlib.contextmanager
def drift_sources(cfg, using):
    """While a Drift round runs, its Custom Sources stand in for Settings > Sources."""
    global SIMILAR_SOURCES, SIMILAR_MIN_AGREEMENT, SIMILAR_TRACK_SOURCES
    custom = drift_custom_sources(cfg, using)
    saved = (SIMILAR_SOURCES, SIMILAR_MIN_AGREEMENT, SIMILAR_TRACK_SOURCES)
    try:
        if custom and using == "artists":
            SIMILAR_SOURCES, SIMILAR_MIN_AGREEMENT = list(custom[0]), custom[1]
        elif custom:
            SIMILAR_TRACK_SOURCES = list(custom[0])
        yield
    finally:
        SIMILAR_SOURCES, SIMILAR_MIN_AGREEMENT, SIMILAR_TRACK_SOURCES = saved


class Drift:
    """
    Drift (Settings > Playlist): when a playlist comes up short of its target,
    search again using what's already been found, for up to the set number of
    rounds. Each round seeds from the DRIFT_SEEDS_PER_ROUND best finds not yet
    used as seeds (most sources agreeing first), using either their similar
    artists' top tracks or their similar tracks, whichever the group is set to.
    Every track checked is logged to the session, hit or miss, like the first pass.
    """

    def __init__(self, group, target, session_id, report=print, per_artist=None, exclude_keys=(), seed="",
                 played=None, vibe=None):
        cfg = DRIFT.get(group, {})
        self.vibe = vibe          # a vibe playlist's description, for Drift using the AI
        self.ai_tried = set()     # (artist, title) the AI suggested that weren't used
        self.played = played      # the mode's PlayedFilter, so Drift skips recent plays too
        self.seed = seed          # what the AI Moderator judges each round against
        self.group, self.cfg = group, cfg
        self.on = cfg.get("on", False)
        self.using = cfg.get("using", "artists")
        self.rounds = cfg.get("rounds", 3)
        self.target, self.session_id, self.report = target, session_id, report
        self.per_artist = per_artist or SIMILAR_TRACK_PER_ARTIST
        self.exclude = {str(k) for k in exclude_keys if k}
        self.finds = []           # (artist, title, key, score) in the order found
        self.per = {}             # artist key -> tracks of theirs in the playlist
        self.seen_artists = set() # artists already asked for their top tracks
        self.drift_from = cfg.get("from", "spread")     # Keep It Tight ("close") or Spread
        self.mod_choice = cfg.get("moderator", "same")  # Drift's own AI Moderator level, or the build's
        self.parent = {}          # Drift track key -> the key of the track it was seeded from
        self.blocked = set()      # keys of chains the moderator found going off course
        self.base = None          # the first round's keys, set when Drift starts
        self.base_set = set()
        self.checked = set()      # (artist key, title) already looked up
        self.used = set()         # seeds already drifted from

    def saw_artist(self, artist):
        self.seen_artists.add(artist_key(artist))

    def mark_seed(self, artist, title=""):
        """The playlist's own seed: never drifted from again, never re-added."""
        self.saw_artist(artist)
        self.used.add(artist_key(artist))
        if title:
            ident = (artist_key(artist), clean_name(title))
            self.used.add(ident)
            self.checked.add(ident)

    def note(self, artist, title, key, score=1, parent=None):
        """A track that made the playlist, so a later round can seed from it (parent: the seed it came from)."""
        if parent:
            self.parent[str(key)] = str(parent)
        a = artist_key(artist)
        self.finds.append((artist, title, str(key), score))
        owner = owner_key(artist, key)   # counted as tagged in the library
        self.per[owner] = self.per.get(owner, 0) + 1
        self.seen_artists.add(a)
        self.checked.add((a, clean_name(title)))

    def tracks(self, keys):
        """[(key, artist, title)] for keys this Drift has noted, for the AI Moderator."""
        info = {k: (a, t) for a, t, k, _ in self.finds}
        return [(k, *info[str(k)]) for k in keys if str(k) in info]

    def discard(self, keys):
        """Tracks the moderator removed: out of the playlist's finds, never seeded from or re-added."""
        keys = {str(k) for k in keys}
        for artist, title, key, _ in self.finds:
            if key in keys:
                a = owner_key(artist, key)
                self.per[a] = max(0, self.per.get(a, 0) - 1)
        self.finds = [f for f in self.finds if f[2] not in keys]
        self.exclude |= keys

    def moderate(self, keys, candidates, report=None, drift_round=False):
        """
        Runs the AI Moderator over candidates (a slice of keys) and removes what it flags from keys.
        For a Drift round: Drift's own level if one is set, the first round's tracks as reference,
        and chains that went off course dropped.
        """
        level, reference = None, None
        if drift_round:
            if self.group != "vibe" and self.mod_choice != "same":
                level = self.mod_choice
                if level == "off":
                    return set()
            cand = {str(k) for k in candidates}
            reference = [t for t in self.tracks(self.base or []) if str(t[0]) not in cand]
        removed = moderate(self.tracks(candidates), self.seed, report or self.report, level=level,
                           reference=reference)
        if drift_round and removed:
            removed = set(removed) | self._drop_chains(candidates, removed, level)
        if removed:
            keys[:] = [k for k in keys if str(k) not in removed]
            self.discard(removed)
        return removed

    def _from_label(self):
        """Where a sources round looks, for the log: its Custom Sources, and for an AI Playlist, no AI."""
        custom = drift_custom_sources(self.cfg, self.using)
        if custom:
            names = [PROVIDERS[c][0] if c in PROVIDERS else c for c in custom[0]]
            listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            agree = f", {custom[1]} must agree" if custom[1] > 1 else ""
            no_ai = ", no AI" if self.group == "vibe" else ""
            return f" (from {listed}{agree}{no_ai})"
        if self.group == "vibe":
            uses_ai = ((self.using == "artists" and "ai" in SIMILAR_SOURCES)
                       or (self.using == "tracks" and "ai" in SIMILAR_TRACK_SOURCES))
            return " (from your sources)" if uses_ai else " (from your sources, no AI)"
        return ""

    def _room(self, artist, key=None):
        """Room left for this artist; with a key, counted as the track is tagged in the library."""
        who = owner_key(artist, key) if key else artist_key(artist)
        return self.per_artist - self.per.get(who, 0)

    def _seeds(self):
        """
        The next round's seeds as (artist, title, key), picked evenly across what's left.
        Keep It Tight: from the first round's tracks only. Spread: from the whole playlist,
        Drift's own finds included. Never a seed already used, or one in a chain the
        moderator dropped.
        """
        pool = [(i, f) for i, f in enumerate(self.finds) if f[2] not in self.blocked]
        if self.drift_from == "close" and self.base is not None:
            pool = [(i, f) for i, f in pool if f[2] in self.base_set]
        picks, idents = [], set()
        for _, (artist, title, key, _) in pool:
            ident = artist_key(artist) if self.using == "artists" else (artist_key(artist), clean_name(title))
            if ident in self.used or ident in idents:
                continue
            idents.add(ident)
            picks.append((artist, title, key, ident))
        if len(picks) > DRIFT_SEEDS_PER_ROUND:
            step = len(picks) / DRIFT_SEEDS_PER_ROUND
            picks = [picks[int(n * step)] for n in range(DRIFT_SEEDS_PER_ROUND)]
        else:
            picks = picks[:DRIFT_SEEDS_PER_ROUND]
        self.used |= {p[3] for p in picks}
        return [(a, t, k) for a, t, k, _ in picks]

    def _chain(self, key):
        """A key and everything Drift seeded from it, however many rounds down."""
        chain, todo = set(), [str(key)]
        while todo:
            k = todo.pop()
            if k not in chain:
                chain.add(k)
                todo += [child for child, parent in self.parent.items() if parent == k]
        return chain

    def _drop_chains(self, candidates, removed, level):
        """
        After a Drift round's check: where the moderator flagged at least half of what one
        seed brought in, the rest of that batch goes too (within the level's cap), and Drift
        never seeds from that chain again. Returns the extra keys to remove.
        """
        level = level or moderator_level()
        removed = {str(k) for k in removed}
        groups = {}
        for k in candidates:
            parent = self.parent.get(str(k))
            if parent:
                groups.setdefault(parent, []).append(str(k))
        room = None if level == "strict" else max(
            0, int(len(candidates) * MODERATOR_CAP.get(level, 0)) - len(removed))
        info = {f[2]: (f[0], f[1]) for f in self.finds}
        extra = set()
        for parent, batch in groups.items():
            flagged = [k for k in batch if k in removed]
            if len(batch) < 2 or len(flagged) * 2 < len(batch):
                continue
            rest = [k for k in batch if k not in removed]
            if room is not None:
                rest, room = rest[:room], room - len(rest[:room])
            extra |= set(rest)
            self.blocked |= self._chain(parent)
            artist, title = info.get(parent, ("a Drift seed", ""))
            source = f"{artist} - {title}" if title else artist
            self.report(f"  AI Moderator: most of what came from {source} went off course"
                        + (f", so the other {len(rest)} went too" if rest else "")
                        + ". Drift won't seed from that chain again.")
        return extra

    def run(self, keys, on_round=None):
        """
        Tops keys up towards the target, in place. on_round(new_keys) is called
        after each round that found something (JRiver output queues them there
        and then). Returns every key added.
        """
        if not self.on or len(keys) >= self.target:
            return []
        if self.base is None:   # the first round, as it stands: Close to Seed seeds from it, the moderator compares with it
            self.base = [f[2] for f in self.finds]
            self.base_set = set(self.base)
        added = []
        for n in range(1, self.rounds + 1):
            if len(keys) >= self.target:
                break
            if self.using == "ai":   # a vibe playlist asking the AI again
                self.report(f"  Drift round {n} of {self.rounds}: {len(keys)} of {self.target}, "
                            f"asking the AI again...")
                before = len(keys)
                self._round_ai(keys)
            else:
                seeds = self._seeds()
                if not seeds:
                    self.report("  Note: Keep It Tight has used every track from the first round as a seed, "
                                "so Drift stopped here." if self.drift_from == "close"
                                else "  Note: Drift has nothing left to seed from.")
                    break
                names = ", ".join(a if self.using == "artists" else f"{a} - {t}" for a, t, _ in seeds)
                self.report(f"  Drift round {n} of {self.rounds}: {len(keys)} of {self.target}, "
                            f"using {self.using} similar to {names}{self._from_label()}...")
                before = len(keys)
                with drift_sources(self.cfg, self.using):
                    if self.using == "artists":
                        self._round_artists(seeds, keys)
                    else:
                        self._round_tracks(seeds, keys)
            if self.using != "ai":   # the AI's own picks are never moderated
                self.moderate(keys, keys[before:], drift_round=True)
            new = keys[before:]
            self.report(f"  Drift round {n}: {len(new)} added.")
            if self.using == "ai" and not new:
                self.report("  Note: Drift stopped, as the AI found nothing new in your library.")
                break
            added += new
            if new and on_round:
                on_round(list(new))
        if len(keys) < self.target:
            self.report(f"  Note: Drift finished short, {len(keys)} of {self.target}.")
        return added

    def _take(self, keys, artist, title, key, score, parent=None):
        if not key or str(key) in self.exclude or key in keys or self._room(artist, key) <= 0:
            return False
        if self.played and not self.played.fresh(key):
            return False
        keys.append(key)
        self.note(artist, title, key, score, parent=parent)
        return True

    def _round_artists(self, seeds, keys):
        for seed, _, seed_key in seeds:
            if len(keys) >= self.target:
                return
            similar, _ = blended_similar_artists(seed, limit=SIMILAR_ARTIST_LIMIT)
            fresh = [(a, s) for a, s in similar if artist_key(a) not in self.seen_artists]
            prefetch_top_tracks([a for a, _ in fresh], TRACKS_PER_ARTIST_POOL, report=self.report)
            for artist, suggested_by in fresh:
                if len(keys) >= self.target:
                    return
                if artist_key(artist) in self.seen_artists:
                    continue
                self.saw_artist(artist)
                if suggested_by == ["AI"] and not deezer_artist_exists(artist):
                    continue
                self.report(f"  {artist} ({', '.join(suggested_by)})...")
                found = []
                pick_top_tracks_for_artist(artist, self.session_id, suggested_by, report=self.report, found=found)
                for a, t, k in found:
                    if len(keys) >= self.target:
                        return
                    self._take(keys, a, t, k, len(suggested_by), parent=seed_key)

    def _round_ai(self, keys):
        """A vibe round: the same description to the AI, told what's already been found or tried."""
        if not self.vibe:
            return
        avoid = [f"{a} - {t}" for a, t, _, _ in self.finds] + [f"{a} - {t}" for a, t in self.ai_tried]
        pairs = ai_vibe_tracks(self.vibe, max(5, self.target - len(keys) + 5), avoid=avoid)
        prefetch_youtube_ids(pairs)
        for artist, track in pairs:
            if len(keys) >= self.target:
                return
            ident = (artist_key(artist), clean_name(track))
            if ident in self.checked:
                continue
            self.checked.add(ident)
            key = find_jriver_key_by_track(artist, track)
            session_log(self.session_id, artist, track, "AI", found=bool(key))
            if self._take(keys, artist, track, key, 1):
                self.report(f"    In library: {artist} - {track}  (AI)")
            else:
                self.ai_tried.add((artist, track))

    def _round_tracks(self, seeds, keys):
        import library   # here rather than at the top: library imports engine
        use_youtube = output_is_youtube()
        for artist, title, seed_key in seeds:
            if len(keys) >= self.target:
                return
            candidates, responding = similar_track_candidates([artist], title, self.report)
            custom = drift_custom_sources(self.cfg, "tracks")
            need = min(custom[1], len(responding)) if custom else 1
            if need > 1:   # Custom Sources' "must agree" (capped at the sources that answered)
                candidates = [c for c in candidates if len(c[1]) >= need]
            for (a, t), sources in candidates:
                if len(keys) >= self.target:
                    return
                ident = (artist_key(a), clean_name(t))
                if ident in self.checked or self._room(a) <= 0:
                    continue
                self.checked.add(ident)
                key = find_jriver_key_by_track(a, t) if use_youtube else library.find_track_key(a, t)
                session_log(self.session_id, a, t, sources, found=bool(key))
                if self._take(keys, a, t, key, len(sources), parent=seed_key):
                    self.report(f"    In library: {a} - {t}  ({', '.join(sources)})")


def mix_active():
    """The Play tab handed in added playlists, and the output is JRiver."""
    return bool(MIX_ROWS) and not output_is_youtube()


def send_mix_only(fast, seed_info, report=print):
    """
    Nothing matched: the Play tab's added playlists go out on their own, so the
    user's own playlists still play. Returns how many were sent (0 with no rows).
    """
    if not mix_active():
        return 0
    report("Playing your added playlists on their own.")
    final = combine_with_mix([], report)
    rest = fast.rest(final) if fast else final
    if rest:
        send_to_jriver(rest, seed_info=seed_info, report=report, append=bool(fast and fast.started))
    return len(final)


def mix_skipped(report=print):
    """Added playlists only join JRiver output; says so once on YouTube."""
    global MIX_NOTED
    if MIX_ROWS and output_is_youtube() and not MIX_NOTED:
        MIX_NOTED = True
        report("  Note: your added playlists were left out, as they only join playlists sent to JRiver.")


def _spread(ours, mixes):
    """
    24bit7's tracks with each Mix playlist woven in. Spaced evenly: every list is
    spread over the whole length, so they all finish together (equal lengths give
    one of each in turn). Mixed randomly: that playlist's tracks land at random.
    24bit7's first track always leads (often the seed or searched track).
    """
    placed = [((i + 0.5) / len(ours) if i else -1.0, 0, k) for i, k in enumerate(ours)]   # ours leads
    for n, (keys, spread) in enumerate(mixes, start=1):
        if spread == "random":
            placed += [(random.random(), n, k) for k in keys]
        else:
            placed += [((i + 0.5) / len(keys), n, k) for i, k in enumerate(keys)]
    placed.sort(key=lambda x: (x[0], x[1]))
    return [k for _, _, k in placed]


def combine_with_mix(keys, report=print):
    """
    Joins the Play tab's added playlists to a finished playlist (keys: 24bit7's
    tracks, in order). Add before ones go first and Add after ones last, in row
    order; Mix ones are woven through. Each comes through as JRiver gives it, with
    its own rules and order: only songs already in the set are dropped, and the
    hidden-track check leaves them alone. Returns the keys to send.
    """
    import playmix, saved_playlists   # here rather than at the top: both import engine
    fast = str(MIX_FAST_KEY or "")
    ours = [str(k) for k in keys if str(k) != fast]
    seen = set(ours)
    before, after, mixes, used = [], [], [], []
    report("Adding your playlists:")
    for row in MIX_ROWS or []:
        name, mode = row.get("name") or "A playlist", row.get("mode")
        try:
            found = [str(k) for k in saved_playlists.playlist_keys(row["id"])]
        except Exception as e:
            report(f"  Problem: {name} couldn't be read from JRiver ({e}), so it was left out.")
            continue
        fresh = []
        for k in found:
            if k not in seen:
                seen.add(k)
                fresh.append(k)
        if not fresh:
            report(f"  Note: {name} is " + ("empty, or no longer in JRiver" if not found else
                                     "already all in the playlist") + ", so nothing was added from it.")
            continue
        used.append(row["id"])
        MIX_KEEP.update(fresh)
        how = {"before": "added before", "mix": "mixed in, " + ("at random" if row.get("spread") == "random"
                                                                  else "spaced evenly")}.get(mode, "added after")
        left = len(found) - len(fresh)
        report(f"  {name}: {len(fresh)} track{'' if len(fresh) == 1 else 's'} {how}"
               + (f" ({left} already in the playlist left out)." if left else "."))
        if mode == "before":
            before += fresh
        elif mode == "mix":
            mixes.append((fresh, row.get("spread")))
        else:
            after += fresh
    if used:
        try:
            playmix.record_use(used)
        except Exception:
            pass
    return before + _spread(ours, mixes) + after


def finish_playlist(keys, drift, fast, seed_info, report, detail=""):
    """
    Sends a first pass, then lets Drift top it up. JRiver output: the first pass
    is queued now and each Drift round is added to the end as it's found (after
    a fast start, everything is added behind the playing track). With added
    playlists (Play tab), Drift runs first and everything is sent together, so
    they sit around the whole set. YouTube output: Drift runs first, as the link
    is made once. Returns how many were sent.
    """
    if mix_active():
        drift.run(keys)
        final = combine_with_mix(keys, report)
        rest = fast.rest(final)
        if rest:
            report(sending_message(len(final), detail))
            send_to_jriver(rest, seed_info=seed_info, report=report, append=fast.started)
        return len(final)
    mix_skipped(report)
    if output_is_youtube():
        drift.run(keys)
        if keys:
            report(sending_message(len(keys), detail))
            send_to_jriver(keys, seed_info=seed_info, report=report)
        return len(keys)
    rest = fast.rest(keys)
    if rest:
        report(sending_message(len(keys), detail))
        send_to_jriver(rest, seed_info=seed_info, report=report, append=fast.started)
    drift.run(keys, on_round=lambda new: send_to_jriver(new, seed_info=seed_info, report=report, append=True))
    return len(keys)


def create_similar_playlist(report=print, seed_info=None, topup=False):
    """
    Builds a playlist around the playing artist:
      1. The seed artist's own top tracks (from the Top-track sources), minus
         the one that's playing: randomly pick TRACKS_PER_ARTIST_PICK of the
         top TRACKS_PER_ARTIST_POOL, queue the ones in the library.
      2. SIMILAR_ARTIST_LIMIT similar artists from the Similar-artist sources,
         each given the same treatment.
      3. Shuffle the hits, keep SIMILAR_ARTIST_TRACK_COUNT (or all of them with the
         limit unticked, though a Non-stop top-up always keeps to it), send them.
      4. Still short and Drift is on: search again from what was found.
    With nothing playing on the output zone (a search or a voice command), the
    first track found starts playing straight away (fast start).
    Every picked track is logged to the session, hit or miss, so Discover
    shows the gaps to buy.
    A multi-value Artist field ('Angus Stone;Dope Lemon') is treated as
    'either of these': each name is seeded and similar-artist lists are
    merged, with duplicate tracks removed.
    """
    refresh_settings_if_changed()
    if seed_info is None:   # no searched seed handed in, so read what JRiver is playing
        seed_info = get_playing_info()
    if not seed_info or seed_info["PlayingNowPosition"] == "-1":
        report(NOTHING_PLAYING)
        return

    seeds = seed_artists(seed_info)
    report(f"Similar Artists: {seed_info['Artist']} - {seed_info['Name']}")
    # YouTube ticked on its own: play its up next queue as is, no artist blend
    if [s for s in SIMILAR_SOURCES if s in PROVIDERS] == ["youtube"]:
        create_youtube_queue_playlist(seed_info, seeds, report=report)
        return
    if len(seeds) > 1:
        report(f"  Multi-value artist, treating as any of: {', '.join(seeds)}")
    report_missing_keys(report, similar=True, top_tracks=True)
    limited = SIMILAR_ARTIST_TRACK_LIMIT or topup
    target = SIMILAR_ARTIST_TRACK_COUNT if limited else 0   # 0: no limit, and nothing for Drift to fill
    report(f"  Per artist: top {TRACKS_PER_ARTIST_POOL} from sources, {TRACKS_PER_ARTIST_PICK} picked at random "
           + (f"(target {target} tracks)." if limited else "(no limit on total tracks)."))
    session_id = session_start("similar", seed_info)
    fast = FastStart(seed_info, report)
    first_key = typed_seed_key(seed_info, seeds, session_id, report)
    fast.play(first_key)
    played = PlayedFilter("artists", keep=[seed_info.get("FileKey"), first_key], report=report, filters=True)
    drift = Drift("artists", target, session_id, report, per_artist=TRACKS_PER_ARTIST_PICK,
                  exclude_keys=[seed_info.get("FileKey"), first_key],
                  seed=f"{seed_info['Artist']} - {seed_info['Name']}", played=played)
    for seed in seeds:
        drift.mark_seed(seed, seed_info.get("Name") or "")

    collected_keys = []   # ordered, deduped as we go
    deferred = [] if output_is_youtube() else None   # YouTube output: picks wait here, looked up together later

    def add(found, score):
        for artist, title, key in found:
            if key not in collected_keys and key != first_key and played.fresh(key) \
                    and drift._room(artist, key) > 0:   # one allowance per artist as tagged
                collected_keys.append(key)
                drift.note(artist, title, key, score)
                fast.play(key)

    # --- Seed artist(s): own top tracks, excluding the playing track ---
    prefetch_top_tracks(seeds, TRACKS_PER_ARTIST_POOL + 1)   # quietly; one more than the pool, as the playing track is left out
    for seed in seeds:
        report(f"  Seed artist: {seed}...")
        found = []
        pick_top_tracks_for_artist(seed, session_id, ["seed"], report=report,
                                   exclude_track=seed_info['Name'], defer=deferred, found=found)
        add(found, 1)

    # --- Similar artists ---
    similar, source_label = blended_similar_artists(seeds, limit=SIMILAR_ARTIST_LIMIT,
                                                    seed_track=seed_info['Name'], report=report)
    report(f"  Similar artists from {source_label.replace(' + ', ', ')}: {len(similar)}")
    prefetch_top_tracks([a for a, _ in similar], TRACKS_PER_ARTIST_POOL, report=report)

    for artist, suggested_by in similar:
        drift.saw_artist(artist)
        if suggested_by == ["AI"] and not deezer_artist_exists(artist):
            debug(f"{artist} (AI): not a verifiable artist name, left out")
            continue
        report(f"  {artist} ({', '.join(suggested_by)})...")
        found = []
        pick_top_tracks_for_artist(artist, session_id, suggested_by, report=report,
                                   defer=deferred, found=found)
        add(found, len(suggested_by))

    # --- Update JRiver queue ---
    if deferred:
        report(f"  Looking up {len(deferred)} tracks on YouTube, several at a time...")
        found = []
        resolve_deferred_picks(deferred, report, found=found)
        add(found, 1)
    if collected_keys:   # before trimming, so anything removed is replaced from the rest
        drift.moderate(collected_keys, [k for k in collected_keys if str(k) != fast.key])
    queued = 0
    if collected_keys or first_key:
        body = [k for k in collected_keys if k != first_key]
        random.shuffle(body)
        keys_list = fast.lead(([first_key] if first_key else []) + body, first_key)[:target or None]
        queued = finish_playlist(keys_list, drift, fast, seed_info, report)
        played.done()
        debug("Queue refreshed")
    else:
        played.done()
        report("Problem: nothing suggested is in your library.")
        queued = send_mix_only(fast, seed_info, report)
    session_finish(session_id, queued, sources=source_label, report=report)


# ---------------------------------------------------------------------------
# Mode 2b: Similar Tracks (tracks like the seed track, blended across sources)
# ---------------------------------------------------------------------------

SIMILAR_TRACK_FETCH = 50   # tracks asked of each source
LISTENBRAINZ_TRACK_ALGORITHMS = {   # Labs similar-recordings datasets, chosen under Settings > Sources
    "alltime": "session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30",
    "recent":  "session_based_days_180_session_300_contribution_5_threshold_15_limit_50_skip_30",
}
LABS = "https://labs.api.listenbrainz.org"


def lastfm_similar_tracks(artist, track, limit=SIMILAR_TRACK_FETCH):
    """Last.fm track.getSimilar: [[artist, title], ...], most similar first."""
    try:
        r = requests.get("http://ws.audioscrobbler.com/2.0/", timeout=20, params={
            "method": "track.getsimilar", "artist": artist, "track": track, "autocorrect": 1,
            "api_key": LASTFM_KEY, "format": "json", "limit": limit})
        return [[t["artist"]["name"], t["name"]] for t in r.json().get("similartracks", {}).get("track", [])]
    except Exception as e:
        print(f"  Problem: Last.fm didn't answer for similar tracks ({e}).")
        return []


def _labs_rows(data):
    """The Labs data hoster has returned a few shapes over time; flattened to a list of dicts."""
    if isinstance(data, dict):
        data = data.get("data", data.get("payload", [data]))
    rows = []
    for item in data or []:
        if isinstance(item, dict) and isinstance(item.get("data"), list):
            rows.extend(i for i in item["data"] if isinstance(i, dict))
        elif isinstance(item, dict):
            rows.append(item)
    return rows


def listenbrainz_similar_tracks(artist, track, limit=SIMILAR_TRACK_FETCH):
    """ListenBrainz similar recordings, via the track's MusicBrainz ID. No token needed."""
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(f"{LABS}/acr-lookup/json", headers=headers, timeout=20,
                         params={"artist_credit_name": artist, "recording_name": track})
        rows = _labs_rows(r.json()) if r.status_code == 200 else []
        mbid = next((row["recording_mbid"] for row in rows if row.get("recording_mbid")), None)
        if not mbid:
            debug(f"ListenBrainz: no MusicBrainz match for {artist} - {track}")
            return []
        r = requests.post(f"{LABS}/similar-recordings/json", headers=headers, timeout=30,
                          json=[{"recording_mbids": [mbid],
                                 "algorithm": LISTENBRAINZ_TRACK_ALGORITHMS.get(
                                     LISTENBRAINZ_TRACK_ALGORITHM_SETTING, LISTENBRAINZ_TRACK_ALGORITHMS["alltime"])}])
        similar = [row for row in (_labs_rows(r.json()) if r.status_code == 200 else [])
                   if row.get("recording_mbid") and row["recording_mbid"] != mbid][:limit]
        if similar and all(row.get("recording_name") for row in similar):
            return [[row.get("artist_credit_name", ""), row["recording_name"]] for row in similar]
        mbids = [row["recording_mbid"] for row in similar]
        if not mbids:
            return []
        r = requests.post(f"{LABS}/recording-mbid-lookup/json", headers=headers, timeout=30,
                          json=[{"[recording_mbid]": m} for m in mbids])
        names = {row.get("recording_mbid"): [row.get("artist_credit_name", ""), row.get("recording_name", "")]
                 for row in (_labs_rows(r.json()) if r.status_code == 200 else [])}
        return [names[m] for m in mbids if m in names and names[m][1]]
    except Exception as e:
        print(f"  Problem: ListenBrainz didn't answer for similar tracks ({e}).")
        return []


def youtube_similar_tracks(artist, track, limit=SIMILAR_TRACK_FETCH):
    """YouTube Music's up next queue for the track (cached with the up next it shares)."""
    return youtube_up_next(artist, track)[:limit]


AI_SIMILAR_TRACKS_PROMPT = (
    "List {limit} songs most similar to \"{track}\" by {artist}, most similar first. "
    "Judge on sound, mood, energy and era rather than the artist's reputation, and favour other "
    "artists, with at most two songs by {artist}. Use each artist's and song's most common spelling. "
    "Respond with a JSON array of objects with keys \"artist\" and \"track\" only, "
    "compact on a single line with no indentation or line breaks, no commentary, no code fences."
)


def ai_similar_tracks(artist, track, limit=SIMILAR_TRACK_FETCH):
    """Claude's songs like the seed track: [[artist, title], ...], most similar first. A made-up
    song simply isn't found in the library, so no separate check is needed."""
    data = ai_ask_json(AI_SIMILAR_TRACKS_PROMPT.format(artist=artist, track=track, limit=min(limit, 40)),
                       feature="Similar Tracks (AI source)")
    out = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and item.get("artist") and item.get("track"):
            out.append([str(item["artist"]).strip(), str(item["track"]).strip()])
    return out[:limit]


TRACK_PROVIDERS = {
    "ai":           ("AI",           ai_similar_tracks),
    "lastfm":       ("Last.fm",      lastfm_similar_tracks),
    "listenbrainz": ("ListenBrainz", listenbrainz_similar_tracks),
    "youtube":      ("YouTube",      youtube_similar_tracks),
}


def similar_track_candidates(seeds, track, report=print):
    """
    Tracks similar to the seed track from every ticked Similar Tracks source,
    blended so tracks several sources agree on come first.
    Returns ([((artist, title), [sources])], [sources that answered]).
    """
    results = []
    for code in SIMILAR_TRACK_SOURCES:
        name, fetch = TRACK_PROVIDERS[code]
        if not source_has_key(code):
            report(f"  Note: {name} is ticked but has no key, so it was skipped. {KEY_HELP_LINE}")
            continue
        pairs, from_cache = [], False
        for seed in seeds:   # a multi-value artist: the first name a source knows the track under
            if code == "youtube":
                pairs = youtube_similar_tracks(seed, track)
            else:
                label = f"{name} ({LISTENBRAINZ_TRACK_ALGORITHM_SETTING})" if code == "listenbrainz" else name
                cache_key = f"{artist_key(seed)}|{clean_name(track)}"
                from_cache = cache_get(label, "similar_tracks", cache_key) is not None
                pairs = cached_call(label, "similar_tracks", cache_key, lambda: fetch(seed, track))
            if pairs:
                break
        pairs = [(canonicalise_conjunction(p[0]), normalise_punctuation(p[1])) for p in pairs or []
                 if isinstance(p, (list, tuple)) and len(p) == 2 and p[0] and p[1]
                 and p[0].strip().lower() not in YOUTUBE_SKIP_ARTISTS]
        note = ""
        if pairs and from_cache:
            note = " (from cache)"
        elif code == "ai" and AI_LAST_ERROR:
            note = f" ({AI_LAST_ERROR})"
        report(f"  {name}: {len(pairs)} similar tracks{note}")
        if pairs:
            results.append((name, pairs))
    blended = blend_lists(results, lambda p: (artist_key(p[0]), clean_name(p[1])))
    return blended, [name for name, _ in results]


VARIETY_POOL = 2   # Similar Tracks collects up to this many times the matches it needs, then picks at random


def pick_varied(pool, n, per, per_artist, keep=None):
    """
    Similar Tracks' variety: n entries from pool (most similar first), drawn at random with
    the closest the most likely (weights fall from 1 for the first to a third for the last),
    at most per_artist per artist, counting per (what's already in). keep, the track already
    playing from fast start, always stays. The picks come back in pool order.
    pool entries: (artist, title, key, sources, owner).
    """
    per, chosen = dict(per), []
    left = list(enumerate(pool))
    if keep:
        for item in left:
            if str(item[1][2]) == str(keep):
                chosen.append(item)
                per[item[1][4]] = per.get(item[1][4], 0) + 1
                left.remove(item)
                break
    size = max(1, len(pool))
    while left and len(chosen) < n:
        weights = [1.0 - (2.0 / 3.0) * i / size for i, _ in left]
        item = random.choices(left, weights=weights)[0]
        left.remove(item)
        if per.get(item[1][4], 0) >= per_artist:
            continue
        per[item[1][4]] = per.get(item[1][4], 0) + 1
        chosen.append(item)
    return [p for _, p in sorted(chosen, key=lambda x: x[0])]


def create_similar_tracks_playlist(report=print, seed_info=None):
    """
    Builds a playlist of tracks like the seed track, not just by similar artists:
      1. Each ticked Similar Tracks source (Last.fm, ListenBrainz, YouTube Music)
         suggests tracks like the seed; the lists are blended.
      2. Tracks at least SIMILAR_TRACK_MIN_AGREEMENT sources agree on are matched
         against the library first, best agreed first; if that leaves the playlist
         short, the agreement is relaxed a step at a time down to one source.
      3. No artist gets more than SIMILAR_TRACK_PER_ARTIST tracks, the seed artist included.
      4. Still short and Drift is on: search again from what was found.
    With nothing playing on the output zone (a search or a voice command), the
    first track found starts playing straight away (fast start).
    Every track checked is logged to the session, hit or miss, for Discover.
    """
    import library   # here rather than at the top: library imports engine
    refresh_settings_if_changed()
    if seed_info is None:
        seed_info = get_playing_info()
    if not seed_info or seed_info["PlayingNowPosition"] == "-1":
        report(NOTHING_PLAYING)
        return
    track = seed_info.get("Name") or ""
    if not track or track == "Unknown":
        report("Problem: Similar Tracks needs a track to seed from. Type one on the Search tab.")
        return
    seeds = seed_artists(seed_info)
    target, per_artist = SIMILAR_TRACK_COUNT, SIMILAR_TRACK_PER_ARTIST
    report(f"Similar Tracks: {seed_info['Artist']} - {track}  (target {target}, at most {per_artist} per artist)")
    session_id = session_start("similar_tracks", seed_info)
    fast = FastStart(seed_info, report)
    first_key = typed_seed_key(seed_info, seeds, session_id, report)
    fast.play(first_key)
    played = PlayedFilter("tracks", keep=[seed_info.get("FileKey"), first_key], report=report, filters=True)
    drift = Drift("tracks", target, session_id, report, per_artist=per_artist,
                  exclude_keys=[seed_info.get("FileKey"), first_key], seed=f"{seed_info['Artist']} - {track}",
                  played=played)
    # With the AI Moderator on, find a few extra, so anything it removes is replaced
    wanted = target + moderator_extra(target)
    for seed in seeds:
        drift.mark_seed(seed, track)

    blended, responding = similar_track_candidates(seeds, track, report)
    seed_keys, playing = {artist_key(s) for s in seeds}, clean_name(track)
    candidates = [(p, s) for p, s in blended if not (artist_key(p[0]) in seed_keys and clean_name(p[1]) == playing)]
    use_youtube = output_is_youtube()
    if use_youtube:
        prefetch_youtube_ids([p for p, _ in candidates[:target * 2]])

    keys, per, checked = [], {}, set()
    if first_key:
        keys.append(first_key)
        per[artist_key(seeds[0])] = 1
        drift.per[artist_key(seeds[0])] = 1
    need = max(1, min(SIMILAR_TRACK_MIN_AGREEMENT, len(responding)))
    # Variety on: collect up to VARIETY_POOL times what's wanted (and per artist), then pick
    # at random with the closest the most likely, so the same seed doesn't always give the same tracks.
    # Variety off: collect just what's wanted, so the closest matches go in, in order.
    variety = VARIETY_POOL if SIMILAR_TRACK_VARIETY else 1
    pool, pool_keys, pool_per = [], set(), dict(per)   # pool: (artist, title, key, sources, owner), best first
    pool_size = wanted * variety
    while candidates:
        for (artist, title), sources in candidates:
            if len(keys) + len(pool) >= pool_size:
                break
            ident = (artist_key(artist), clean_name(title))
            if ident in checked or len(sources) < need or pool_per.get(ident[0], 0) >= per_artist * variety:
                continue
            checked.add(ident)
            key = find_jriver_key_by_track(artist, title) if use_youtube else library.find_track_key(artist, title)
            session_log(session_id, artist, title, sources, found=bool(key))
            owner = owner_key(artist, key) if key else ident[0]   # counted as tagged in the library
            if (key and key not in keys and str(key) not in pool_keys and played.fresh(key)
                    and pool_per.get(owner, 0) < per_artist * variety):
                pool.append((artist, title, key, sources, owner))
                pool_keys.add(str(key))
                pool_per[owner] = pool_per.get(owner, 0) + 1
                fast.play(key)
                report(f"    In library: {artist} - {title}  ({', '.join(sources)})")
            elif not key:
                report(f"    Not in library: {artist} - {title}")
        if len(keys) + len(pool) >= wanted or need <= 1:
            break
        report(f"  {len(keys) + len(pool)} tracks with {need} or more sources agreeing, so relaxed to {need - 1}.")
        need -= 1
    picks = pick_varied(pool, wanted - len(keys), per, per_artist, keep=fast.key)
    for artist, title, key, sources, owner in picks:
        keys.append(key)
        per[owner] = per.get(owner, 0) + 1
        drift.note(artist, title, key, len(sources))
    report(f"  Suggested {len(candidates)}, checked {len(checked)}, in library {len(keys) + len(pool) - len(picks)}.")
    if len(picks) < len(pool):
        report(f"  Picked {len(picks)} of those {len(pool)} at random, the closest the most likely, for variety.")
    drift.checked |= checked
    drift.moderate(keys, [k for k in keys if k != first_key and str(k) != fast.key])

    source_label = " + ".join(responding) or "none"
    if len(keys) < target and drift.on:
        source_label += f" (drift: similar {drift.using})"

    queued = 0
    if keys:
        body = [k for k in keys if k != first_key]
        if SIMILAR_TRACK_ORDER == "shuffled":
            random.shuffle(body)
        keys = fast.lead(([first_key] if first_key else []) + body, first_key)[:target]
        queued = finish_playlist(keys, drift, fast, seed_info, report,
                                 "" if SIMILAR_TRACK_ORDER == "shuffled" else ", most similar first")
        played.done()
        debug("Queue refreshed")
    else:
        report("Problem: nothing suggested is in your library.")
        queued = send_mix_only(fast, seed_info, report)
    session_finish(session_id, queued, sources=source_label, report=report)


# ---------------------------------------------------------------------------
# Mode 4: Vibe Playlist (AI-described mood)
# ---------------------------------------------------------------------------

def create_vibe_playlist(vibe, report=print):
    """
    Builds a playlist from a text description of a mood.
    AI suggests artist/track pairs (always AI, regardless of source settings,
    since no other source takes a description). Hits queue, misses are logged
    as discoveries. Still short and Drift is on: search again from the hits,
    using their similar artists or similar tracks (Settings > Playlist).
    With nothing playing on the output zone, the first hit starts playing
    straight away (fast start). Everything else is shuffled before queueing.
    """
    refresh_settings_if_changed()
    vibe = (vibe or "").strip()
    if not vibe:
        report("Problem: no description was given.")
        return
    if not ANTHROPIC_API_KEY:
        report("Problem: AI Playlist needs an Anthropic key. " + KEY_HELP_LINE)
        return
    target = VIBE_TRACK_COUNT
    report(f"AI Playlist: {vibe}  (target {target} tracks)")

    seed_info = {"Artist": "AI Playlist", "Name": vibe, "Album": ""}
    session_id = session_start("vibe", seed_info, "AI")
    fast = FastStart(None, report)
    played = PlayedFilter("vibe", report=report, filters=True)
    drift = Drift("vibe", target, session_id, report, per_artist=TRACKS_PER_ARTIST_PICK, seed=f"vibe: {vibe}",
                  played=played, vibe=vibe)
    wanted = target   # the AI's own picks aren't moderated, so no extras are needed

    report("  Asking the AI for tracks...")
    pairs = ai_vibe_tracks(vibe, count=wanted)
    if not pairs:
        report("  Problem: the AI returned nothing usable.")
        session_finish(session_id, send_mix_only(fast, None, report), report=report)
        return

    prefetch_youtube_ids(pairs)
    keys, misses = [], 0
    for artist, track in pairs:
        key = find_jriver_key_by_track(artist, track)
        if key:
            report(f"    In library: {artist} - {track}")
            if key not in keys and played.fresh(key):
                keys.append(key)
                drift.note(artist, track, key, 1)
                fast.play(key)
            session_log(session_id, artist, track, "AI", found=True)
        else:
            report(f"    Not in library: {artist} - {track}")
            misses += 1
            drift.ai_tried.add((artist, track))   # so Drift using the AI doesn't ask for it again
            session_log(session_id, artist, track, "AI", found=False)
    report(f"  AI picks: {len(keys)} in library, {misses} not.")
    # the AI's own picks aren't moderated; Drift tracks from the sources can be (Settings > Playlist)

    if not keys:
        report("Problem: nothing the AI picked is in your library. Try a different description.")
        session_finish(session_id, send_mix_only(fast, None, report), report=report)
        return

    random.shuffle(keys)
    keys = fast.lead(keys)[:target]
    sent = finish_playlist(keys, drift, fast, None, report, " (shuffled)")
    played.done()
    debug("Queue refreshed")
    session_finish(session_id, sent, report=report)


# ---------------------------------------------------------------------------
# Mode 2: Artist Top 10 by Popularity
# ---------------------------------------------------------------------------

def play_top_n(report=print, seed_info=None):
    """
    Plays the top N tracks for the current artist, ranked across the
    configured TOP_TRACK_SOURCES. N and the play order (most popular first,
    least popular first, or random) come from the TOP_TRACKS_* settings.
    A multi-value Artist field ('Angus Stone;Dope Lemon') gets the top N for
    each name, queued one artist after the other, duplicates removed.
    Can be run mid-album: Playing Now is stripped to the current track
    before the new tracks are added, without interrupting playback.
    In popular order with nothing playing on the output zone (a search or a
    voice command), the most popular track found starts straight away.
    """
    refresh_settings_if_changed()
    if seed_info is None:   # no searched seed handed in, so read what JRiver is playing
        seed_info = get_playing_info()
    if not seed_info or seed_info["PlayingNowPosition"] == "-1":
        report(NOTHING_PLAYING)
        return

    seeds = seed_artists(seed_info)
    report_missing_keys(report, top_tracks=True)
    n = TOP_TRACKS_COUNT
    order = TOP_TRACKS_ORDER

    report(f"Artist's Top Tracks: {seed_info['Artist']}  (top {n}, {order} order)")
    if len(seeds) > 1:
        report(f"  Multi-value artist, fetching top {n} for each of: {', '.join(seeds)}")

    session_id = None
    ordered_keys, labels_used = [], []
    fast = FastStart(seed_info, report, enabled=(order == "popular"))
    played = PlayedFilter("top", report=report, filters=True)
    for artist in seeds:
        top_tracks, source_label = blended_top_tracks(artist, limit=n)
        if not top_tracks:
            report(f"  Problem: no source returned top tracks for {artist}.")
            continue
        report(f"  {artist}: ranked from {source_label.replace(' + ', ', ')}")
        if source_label not in labels_used:
            labels_used.append(source_label)
        if session_id is None:
            session_id = session_start("top_tracks", seed_info, source_label)

        prefetch_youtube_ids([(artist, t) for t, _ in top_tracks[:n]])
        for track_name, suggested_by in top_tracks[:n]:
            key = find_jriver_key_by_track(artist, track_name)
            report(f"    {'In library' if key else 'Not in library'}: {artist} - {track_name}  "
                   f"({', '.join(suggested_by)})")
            if key and key not in ordered_keys and played.fresh(key):
                ordered_keys.append(key)
                fast.play(key)
            session_log(session_id, artist, track_name, suggested_by, found=bool(key))

    if session_id is None:
        report("Problem: no source returned any top tracks.")
        nonstop_begin("top_tracks", seed_info)   # so Run After Building uses this group's file
        send_mix_only(fast, seed_info, report)
        run_after_building(report)
        return
    played.done()
    if not ordered_keys:
        report("Problem: none of the top tracks are in your library." if not played.skipped else
               "Note: every top track in your library was played recently, so there's nothing to play. "
               "Settings > Playlist > Artist's Top Tracks")
        session_finish(session_id, send_mix_only(fast, seed_info, report), report=report)
        return

    NONSTOP_CONTEXT["top_first"] = str(ordered_keys[0])   # the most popular found: non-stop seeds from it later
    if order == "random":
        random.shuffle(ordered_keys)
    elif order == "reverse":
        ordered_keys.reverse()

    labels = {"popular": "most popular first", "reverse": "least popular first", "random": "random order"}
    report(f"  Sending {len(ordered_keys)} tracks, {labels[order]}...")
    mix_skipped(report)
    rest = fast.rest(combine_with_mix(ordered_keys, report) if mix_active() else ordered_keys)
    if rest:
        send_to_jriver(rest, seed_info=seed_info, report=report, append=fast.started)
    session_finish(session_id, len(ordered_keys), sources=" + ".join(labels_used), report=report)


# ---------------------------------------------------------------------------
# Label lookup (the Label button in Discover)
# ---------------------------------------------------------------------------

NO_LABEL = {"[no label]", "no label", "not on label", "self-released", "self released", "independent", "none"}


def _mb_json(path, params):
    """One MusicBrainz request, paced to their one-a-second rule. Parsed JSON, or None."""
    for _ in range(3):
        _musicbrainz_wait_turn()
        try:
            r = requests.get(f"https://musicbrainz.org/ws/2/{path}", params={**params, "fmt": "json"},
                             headers={"User-Agent": USER_AGENT}, timeout=15)
        except Exception as e:
            debug(f"Label: MusicBrainz request failed: {e}")
            return None
        if r.status_code == 503:   # busy: wait and try again
            time.sleep(1.0)
            continue
        return r.json() if r.status_code == 200 else None
    return None


def _release_rank(release):
    """Sort key: albums first, then singles and EPs, compilations and live last; official, then earliest."""
    group = release.get("release-group") or {}
    primary, secondary = group.get("primary-type") or "", group.get("secondary-types") or []
    if primary == "Album" and not secondary:
        kind = 0
    elif primary in ("Single", "EP") and not secondary:
        kind = 1
    else:
        kind = 2
    return kind, 0 if release.get("status") == "Official" else 1, release.get("date") or "9999"


def musicbrainz_label(artist, track):
    """
    The label of the track's first proper release on MusicBrainz, as
    (name, label MBID); ("", None) when it's self-released; None if MusicBrainz
    doesn't know the track or its label.
    """
    query = 'recording:"{}" AND artist:"{}"'.format(track.replace('"', ''), artist.replace('"', ''))
    data = _mb_json("recording/", {"query": query, "limit": 10}) or {}
    want_title, want_artist = clean_name(track), artist_key(artist)
    releases = []
    for rec in data.get("recordings", []):
        credit = " ".join(c.get("name", "") for c in rec.get("artist-credit", []) if isinstance(c, dict))
        if clean_name(rec.get("title", "")) != want_title or want_artist not in artist_key(credit):
            continue
        releases += rec.get("releases", [])
    for release in sorted(releases, key=_release_rank)[:3]:
        info = _mb_json(f"release/{release['id']}", {"inc": "labels"}) or {}
        for entry in info.get("label-info", []):
            label = entry.get("label") or {}
            name = (label.get("name") or "").strip()
            if not name:
                continue
            if name.lower() in NO_LABEL:
                return "", None
            return name, label.get("id")
    return None


def musicbrainz_label_bandcamp(label_id):
    """The label's Bandcamp page, if MusicBrainz has it linked. None otherwise."""
    data = _mb_json(f"label/{label_id}", {"inc": "url-rels"}) or {}
    for rel in data.get("relations", []):
        url = ((rel.get("url") or {}).get("resource") or "").strip()
        if rel.get("type") == "bandcamp" or "bandcamp.com" in url:
            return url or None
    return None


def discogs_label(artist, track):
    """The label from Discogs (needs a token): name, "" when self-released, or None."""
    if not DISCOGS_TOKEN:
        return None
    data = discogs_get("/database/search", {"artist": artist, "track": track, "type": "release", "per_page": 10})
    results = (data or {}).get("results", [])

    def rank(item):
        formats = [f.lower() for f in item.get("format", [])]
        return ("compilation" in formats, "album" not in formats, item.get("year") or "9999")

    for item in sorted(results, key=rank):
        for name in item.get("label", []):
            name = discogs_clean_name(name or "").strip()
            if name:
                return "" if name.lower() in NO_LABEL else name
    return None


def find_label(artist, track):
    """
    Finds who released a track, for the Label button: MusicBrainz first, then
    Discogs. Returns {"label", "source", "bandcamp"}: label is "" for
    self-released and None when neither source knows; bandcamp is the label's
    own Bandcamp page when MusicBrainz links one. Network only, so it's safe
    on a worker thread (the caller does any caching).
    """
    found = musicbrainz_label(artist, track)
    if found is not None:
        name, label_id = found
        bandcamp = musicbrainz_label_bandcamp(label_id) if label_id else None
        return {"label": name, "source": "MusicBrainz", "bandcamp": bandcamp}
    name = discogs_label(artist, track)
    if name is not None:
        return {"label": name, "source": "Discogs", "bandcamp": None}
    return {"label": None, "source": None, "bandcamp": None}


def label_page(artist, track, result):
    """(url, note) for a find_label result: the label's Bandcamp, a Bandcamp search, or Google."""
    from urllib.parse import quote_plus
    label = result.get("label")
    if label is None:
        return (f"https://www.google.com/search?q={quote_plus(f'{artist} {track} record label')}",
                "No label found, so searching Google")
    if label == "" or artist_key(label) == artist_key(artist):
        return (f"https://bandcamp.com/search?q={quote_plus(artist)}&item_type=b",
                f"Self-released, so opening {artist} on Bandcamp")
    if result.get("bandcamp"):
        return result["bandcamp"], f"Label: {label}, opening its Bandcamp page"
    return (f"https://bandcamp.com/search?q={quote_plus(label)}&item_type=b",
            f"Label: {label}, searching Bandcamp for it")


# ---------------------------------------------------------------------------
# Mode 3: Explore a record's credits (Discogs)
# ---------------------------------------------------------------------------

DISCOGS_BASE = "https://api.discogs.com"

# Credit roles worth following, in the order they're offered. Discogs role
# strings are free text ("Producer, Mixed By", "Drums, Percussion"), so we
# match on the keyword appearing anywhere in the role.
DISCOGS_ROLE_PRIORITY = ["Producer", "Mixed By", "Engineer", "Recorded By",
                         "Featuring", "Guitar", "Bass", "Drums", "Keyboards",
                         "Piano", "Vocals", "Saxophone", "Trumpet", "Written-By"]


def discogs_get(path, params=None):
    if not DISCOGS_TOKEN:
        debug("Discogs: no token")
        return None
    try:
        r = requests.get(f"{DISCOGS_BASE}{path}", params=params or {},
                         headers={"User-Agent": USER_AGENT,
                                  "Authorization": f"Discogs token={DISCOGS_TOKEN}"})
        if r.status_code != 200:
            print(f"  Problem: Discogs answered {r.status_code}.")
            debug(f"Discogs {path}: {r.text[:200]}")
            return None
        return r.json()
    except Exception as e:
        print(f"  Problem: Discogs didn't answer ({e}).")
        return None


def discogs_clean_name(name):
    """Removes Discogs disambiguation suffixes like 'John Smith (2)'."""
    return re.sub(r'\s*\(\d+\)$', '', name).strip()


_release_master = {}   # release id -> master id, filled by discogs_find_release


def discogs_find_release(artist, album):
    """
    Finds the Discogs release for the playing album. Returns (release id, label) or None.
    Searches for the master release first (the album as a work, not a specific
    pressing), picks the most-owned match, and uses its main release, which is
    the canonical pressing with the fullest credits. Falls back to a plain
    release search ranked by owners if no master exists.
    A multi-value artist ('Angus Stone;Dope Lemon') is tried one name at a
    time, first name first, until something matches.
    """
    names = split_values(artist) or [artist]
    for name in names:
        found = _discogs_find_release_for(name, album)
        if found:
            return found
    return None


def _discogs_find_release_for(artist, album):
    def most_owned(results):
        return max(results, key=lambda r: r.get("community", {}).get("have", 0))

    for params in ({"artist": artist, "release_title": album, "type": "master", "per_page": 10},
                   {"q": f"{artist} {album}", "type": "master", "per_page": 10}):
        data = discogs_get("/database/search", params)
        if data and data.get("results"):
            master = most_owned(data["results"])
            detail = discogs_get(f"/masters/{master['id']}")
            if detail and detail.get("main_release"):
                label = f"{master.get('title')} ({detail.get('year', '?')}, main release of master {master['id']})"
                _release_master[detail["main_release"]] = master["id"]
                return detail["main_release"], label
            break

    for params in ({"artist": artist, "release_title": album, "type": "release", "per_page": 25},
                   {"q": f"{artist} {album}", "type": "release", "per_page": 25}):
        data = discogs_get("/database/search", params)
        if data and data.get("results"):
            best = most_owned(data["results"])
            label = f"{best.get('title')} ({best.get('year', '?')}, {', '.join(best.get('format', [])[:2])})"
            return best["id"], label
    return None


def discogs_release_credits(release_id, seed_artist):
    """
    Collects credited people from a release (release-level and per-track),
    excluding the seed artist (every name in a multi-value field). Returns
    a list of (name, roles) sorted so the most useful roles come first.
    """
    data = discogs_get(f"/releases/{release_id}")
    if not data:
        return []
    people = {}
    sources = list(data.get("extraartists", []))
    for track in data.get("tracklist", []):
        sources.extend(track.get("extraartists", []))
    seed_cleans = {strip_accents(s).lower() for s in (split_values(seed_artist) or [seed_artist])}
    for credit in sources:
        name = discogs_clean_name(credit.get("name", ""))
        if not name or strip_accents(name).lower() in seed_cleans:
            continue
        roles = people.setdefault(name, set())
        for role in credit.get("role", "").split(","):
            role = role.strip()
            if role:
                roles.add(role)

    def rank(item):
        name, roles = item
        joined = " ".join(roles)
        for i, key in enumerate(DISCOGS_ROLE_PRIORITY):
            if key.lower() in joined.lower():
                return i
        return len(DISCOGS_ROLE_PRIORITY)

    return sorted(people.items(), key=rank)


def explore_credits(report=print):
    """
    Mode 3. Shows the Discogs credits for the playing album: producer,
    engineers, musicians and so on. Information only; the queue is untouched.
    """
    refresh_settings_if_changed()
    seed_info = get_playing_info()
    if not seed_info or seed_info["PlayingNowPosition"] == "-1":
        report(NOTHING_PLAYING)
        return

    if not DISCOGS_TOKEN:
        report("Problem: Show Credits needs a Discogs token. " + KEY_HELP_LINE)
        return
    artist, album = seed_info["Artist"], seed_info["Album"]
    report(f"Show Credits: {artist} - {album}")

    found = discogs_find_release(artist, album)
    if not found:
        report("  Problem: this release isn't on Discogs.")
        return
    release_id, release_label = found
    report(f"  Using release: {release_label}")

    credits = discogs_release_credits(release_id, artist)
    if not credits:
        report("  Note: this release lists no credits beyond the artist.")
        return

    report("  Credited on this record:")
    for name, roles in credits:
        report(f"    {name} ({', '.join(sorted(roles))})")
