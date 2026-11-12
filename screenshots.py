"""
24bit7 - screenshots for the user manual.

Opens 24bit7 in a demo mode, steps through each tab and Settings page, and saves
a PNG of each into docs/images. Demo mode never contacts JRiver and never touches
your .env or 24bit7.db: settings are read from a temporary copy with every key
swapped for a dummy, and Discover, devices and playlists come from a temporary
database filled with made-up data around The Beatles. Both are deleted at the end.

Use:
  py screenshots.py                     every screenshot
  py screenshots.py play discover       just those
  py screenshots.py --changed           only shots whose code has changed since
                                        their image was last committed (or is uncommitted)
  py screenshots.py --list              the names, and the files each depends on
  py screenshots.py --lang de           in German, into docs/images/de (with any of the above)

An image is only rewritten when the picture has actually changed, so git only
shows real changes. Long Settings pages are scrolled and stitched into one image.
The shots are always in the light theme (DEMO_ENV), whatever 24bit7 itself is set to.
Windows only (uses Pillow's ImageGrab). Leave the mouse and keyboard alone while it runs.
"""

import argparse
import json
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time

import i18n

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "docs", "images")   # docs/images/de for the German shots (--lang de)
IMAGES = "images"   # the same, relative to docs
COMMON = ["tabs.py"]
SCALE = 1.0   # Windows' display scaling while the shots are taken (set by build_window)   # every shot changes when the tab and button drawing changes

# name, path of tab names to click through, files it depends on, optional before-shot action
SHOTS = [
    ("play", ["Play", "Now Playing"], ["gui.pyw", "mix_gui.py", "tabs.py"], "more_closed"),
    ("play_more_options", ["Play", "Now Playing"], ["gui.pyw", "mix_gui.py", "tabs.py"], "more_open"),
    ("play_search", ["Play", "Search"], ["gui.pyw", "tabs.py"], "more_closed"),
    ("play_jriver_playlists", ["Play", "Playlists & Albums"], ["gui.pyw", "embellish.py", "tabs.py"], "playlists_list"),
    ("play_radio", ["Play", "Now Playing"], ["gui.pyw", "radio.py", "tabs.py"], "radio_list"),
    ("play_review", ["Play", "Now Playing"], ["gui.pyw", "review_gui.py"], "review"),
    ("ai_playlist_create", ["Play", "Now Playing"], ["ai_dialog.py"], "ai_create"),
    ("ai_playlist_steer", ["Play", "Now Playing"], ["ai_dialog.py"], "ai_steer"),
    ("console_tabs", ["Play", "Now Playing"], ["gui.pyw", "buildlog.py"], "tabs_kitchen"),
    ("console_log", ["Play", "Now Playing"], ["gui.pyw", "buildlog.py"], "tabs_log"),
    ("discover", ["Discover"], ["discover_gui.py", "tabs.py"], "sessions"),
    ("discover_missing_artists", ["Discover"], ["artists_gui.py", "discover_stats.py", "tabs.py"], "missing_artists"),
    # Settings > Buttons: a button of your own with a filter and a shortcut, the standard Similar Artists'
    # Playlist page with its columns, an AI Playlist's page, the Edit Filters window, and the Kitchen zone
    ("settings_buttons", ["Settings", "Playlist Settings"], ["settings_gui.py", "buttons.py"], "button:Artist + Guests:Sources"),
    ("settings_buttons_playlist", ["Settings", "Playlist Settings"], ["settings_gui.py", "buttons.py"],
     "button:Similar Artists:Playlist"),
    ("settings_buttons_ai_playlist", ["Settings", "Playlist Settings"], ["settings_gui.py", "buttons.py"],
     "button:AI Playlist:Playlist"),
    ("edit_filters", ["Settings", "Playlist Settings"], ["settings_gui.py", "filters.py"], "edit_filters"),
    ("settings_devices", ["Settings", "Devices"], ["settings_gui.py", "devices.py"], "device:demo-kitchen"),
    ("settings_discover_sites", ["Settings", "Discover"], ["settings_gui.py"], None),
    ("settings_keys", ["Settings", "Keys"], ["settings_gui.py"], None),
    ("settings_voice_commands", ["Settings", "Voice Commands"], ["settings_gui.py", "voice.py"], None),
    ("settings_jriver_playlists", ["Settings", "Playlists & Albums"], ["settings_gui.py", "saved_playlists.py"], None),
    ("settings_other", ["Settings", "Other"], ["settings_gui.py", "hotkeys.py", "tray.py"], None),
    ("settings_multiroom", ["Settings", "Other"], ["settings_gui.py", "multiroom/profiles.py", "multiroom/clockcheck.py"],
     "multiroom"),
    ("settings_calibrate", ["Settings", "Other"], ["settings_gui.py", "multiroom/calibrate_fit.py"], "calibrate"),
    ("settings_about", ["Settings", "About"], ["settings_gui.py"], None),
]

# --- the demo data ----------------------------------------------------------

DEMO_ZONES = [("10001", "Speakers"), ("10002", "Kitchen")]
DEMO_PLAYING = {"Artist": "The Beatles", "Album": "Abbey Road", "Name": "Here Comes The Sun",
                "PlayingNowPosition": "4", "PlayingNowTracks": "17", "FileKey": "1001", "ZoneID": "10001",
                "State": "2", "NextFileKey": "1002"}   # playing, with a track to follow: Stop in amber, Skip Track lit
DEMO_KEYS = {"LASTFM_API_KEY": "demo" * 8, "LISTENBRAINZ_TOKEN": "demo" * 9, "DISCOGS_TOKEN": "demo" * 10,
             "TIDAL_CLIENT_ID": "demo" * 4, "TIDAL_CLIENT_SECRET": "demo" * 11, "TIDAL_REFRESH_TOKEN": "demo" * 6,
             "ANTHROPIC_API_KEY": "demo" * 12, "JRIVER_USER": "demo", "JRIVER_PASS": "demo" * 3,
             "VOICE_KEY": "demo" * 8}
DEMO_ENV = {"HIDDEN_ZONES": "", "DEFAULT_ZONE": "Speakers", "FOLLOW_ACTIVE_ZONE": "0", "VOICE_ENABLED": "1",
            "CONSOLE_MODE": "simple", "CONSOLE_TABS": "0", "HOTKEY_SWITCH_ZONES": "Ctrl+Alt+5",
            # Tidal ticked everywhere, signed in (a dummy login), so the shots show it
            "EXTRA_OUTPUTS": "youtube,tidal", "PLAYLIST_SITES": "youtube,tidal", "LISTEN_SITES": "youtube,tidal",
            # Deep Cuts on, Spaced, so More Options and the console show it; ? off, as it starts
            "DEEP_CUTS_ARTISTS": "spaced", "DEEP_CUTS_TRACKS": "spaced", "DEEP_CUTS_VIBE": "spaced", "PLAY_HELP": "0",
            "THEME": "light", "ACCENT_COLOUR": ""}   # the manual is light, and its console the default green
# JRiver Playlists: one playlist blended and one with Non-stop, so the shot shows both
DEMO_SAVED_ROWS = {"201": {"blend": "tracks"}, "202": {"nonstop": "artists"}}
DEMO_DEVICES = [("demo-kitchen", "Kitchen Echo", "Kitchen", 0, "2026-10-04 10:41"),
                ("demo-lounge", "Lounge Dot", "Speakers", 0, "2026-10-04 09:15")]
# Review: a Similar Artists shortlist, as the Review list shows it
DEMO_REVIEW = [
    ("The Kinks", "Waterloo Sunset", "Something Else by The Kinks", 193, "92"),
    ("The Hollies", "Bus Stop", "Bus Stop", 174, "128"),
    ("The Byrds", "Turn! Turn! Turn!", "Turn! Turn! Turn!", 229, "116"),
    ("Badfinger", "Baby Blue", "Straight Up", 217, "126"),
    ("The Zombies", "Time Of The Season", "Odessey and Oracle", 213, "118"),
    ("Harry Nilsson", "Everybody's Talkin'", "Aerial Ballet", 164, ""),
    ("The Move", "Flowers In The Rain", "Move", 146, "134"),
    ("Big Star", "Thirteen", "#1 Record", 154, "88"),
]
DEMO_FOUND_BY = ["Last.fm, Deezer", "Last.fm", "Last.fm, ListenBrainz", "Deezer", "Last.fm, Deezer", "Last.fm",
                 "ListenBrainz", "Last.fm, Deezer"]   # Review's Found By, one per DEMO_REVIEW row
DEMO_IDEAS = ["Late-night jazz, slow and smoky", "Sunday morning, acoustic", "Driving at night"]
DEMO_TONE = "Warm late-60s British pop, mid-tempo, melodic and upbeat"
DEMO_PLAYLISTS = [
    {"ID": "201", "Name": "Sunday Morning", "Folder": "", "Type": "Playlist"},
    {"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"},
    {"ID": "203", "Name": "60s Smartlist", "Folder": "Smartlists", "Type": "Smartlist"},
    {"ID": "204", "Name": "Random Album", "Folder": "Smartlists", "Type": "Smartlist"},
    {"ID": "205", "Name": "Kitchen Disco", "Folder": "Mixes", "Type": "Playlist"},
]
# Playlists & Albums (1.36.0): albums for the box to find, The Beatles typed in the shot
DEMO_ALBUMS = [("Abbey Road", "The Beatles"), ("Help!", "The Beatles"), ("Revolver", "The Beatles"),
               ("Rubber Soul", "The Beatles"), ("Something Else", "The Kinks"), ("Mr. Tambourine Man", "The Byrds"),
               ("Bridge Over Troubled Water", "Simon & Garfunkel"), ("Meddle", "Pink Floyd")]
# Radio (1.31.0): lanes as an analysis of a sixties-and-folk library would make them, Classic Rock split open
DEMO_RADIO = {"when": "2026-11-06 20:18", "resting": None, "known": [], "lanes": [
    {"id": "1", "name": "Classic Rock / Rock", "genres": ["classic rock", "rock"], "artists": 60, "plays": 4200,
     "pillars": ["The Beatles", "The Kinks", "The Rolling Stones"], "children": [
         {"id": "1a", "name": "Classic Rock / Psychedelic", "genres": ["classic rock", "psychedelic"], "artists": 34,
          "plays": 2600, "pillars": ["The Beatles", "The Byrds"]},
         {"id": "1b", "name": "Blues Rock / Blues", "genres": ["blues rock", "blues"], "artists": 26, "plays": 1600,
          "pillars": ["Jimi Hendrix", "Cream"]}]},
    {"id": "2", "name": "Folk / Singer-Songwriter", "genres": ["folk", "singer-songwriter"], "artists": 41,
     "plays": 2100, "pillars": ["Simon & Garfunkel", "Nick Drake"], "children": [
         {"id": "2a", "name": "Folk / Folk Rock", "genres": ["folk", "folk rock"], "artists": 22, "plays": 1200,
          "pillars": ["Simon & Garfunkel"]},
         {"id": "2b", "name": "Singer-Songwriter / Acoustic", "genres": ["singer-songwriter", "acoustic"],
          "artists": 19, "plays": 900, "pillars": ["Nick Drake"]}]},
    {"id": "3", "name": "Electronic / Ambient", "genres": ["electronic", "ambient"], "artists": 28, "plays": 1500,
     "pillars": ["Brian Eno", "Boards of Canada"]},
    {"id": "4", "name": "Jazz / Vocal Jazz", "genres": ["jazz", "vocal jazz"], "artists": 17, "plays": 800,
     "pillars": ["Nina Simone", "Chet Baker"]},
    {"id": "5", "name": "Soul / Motown", "genres": ["soul", "motown"], "artists": 15, "plays": 600,
     "pillars": ["Marvin Gaye", "The Supremes"]},
]}
# JRiver Playlists: what 24bit7 played or embellished lately, for the list's Recent part
DEMO_RECENT = [{"id": "album:The Beatles|Abbey Road", "name": "Abbey Road", "kind": "album", "artist": "The Beatles",
                "how": "embellished", "when": "2026-11-12 18:05"},
               {"id": "202", "name": "Road Trip", "how": "embellished", "when": "2026-11-06 19:40"},
               {"id": "201", "name": "Sunday Morning", "how": "played", "when": "2026-11-05 10:12"}]
# Discover: one Similar Artists session from Here Comes The Sun. (artist, track, sources, found)
DEMO_DISCOVERIES = [
    ("The Kinks", "Waterloo Sunset", "Last.fm, Deezer", True),
    ("The Hollies", "Bus Stop", "Last.fm, ListenBrainz", True),
    ("The Byrds", "Turn! Turn! Turn!", "Last.fm, Deezer, YouTube", True),
    ("Badfinger", "Baby Blue", "Last.fm, ListenBrainz", True),
    ("The Kinks", "Days", "Last.fm, Deezer", True),
    ("The Zombies", "Time Of The Season", "Last.fm, Deezer", False),
    ("Harry Nilsson", "Everybody's Talkin'", "ListenBrainz, YouTube", False),
    ("The Move", "Flowers In The Rain", "Last.fm", False),
    ("The Hollies", "Carrie Anne", "Last.fm, ListenBrainz", False),
    ("Badfinger", "Day After Day", "Last.fm, Deezer", False),
    ("Big Star", "Thirteen", "ListenBrainz", False),
    ("The Left Banke", "Walk Away Renee", "Last.fm, ListenBrainz", False),
    ("The Searchers", "Needles And Pins", "Last.fm, Deezer", False),
    ("Gerry & The Pacemakers", "Ferry Cross The Mersey", "Deezer", False),
    ("Electric Light Orchestra", "Mr. Blue Sky", "Last.fm, YouTube", False),
    ("The Turtles", "Happy Together", "Last.fm, Deezer, YouTube", False),
]
# Discover > Missing Artists (1.34.0): three more builds from artists you own, the artists you own, and Last.fm's tags
# as Radio keeps them, so Missing Artists has rows, Your Artists counts above one, and Sound has chips
DEMO_OWNED = ["The Beatles", "The Kinks", "The Hollies", "The Byrds", "Badfinger", "Simon & Garfunkel", "Nick Drake",
              "The Rolling Stones", "Jimi Hendrix", "Cream"]
DEMO_MORE_SESSIONS = [
    ("2026-09-14 20:05", "The Kinks", "Speakers", "Main Window", [
        ("The Zombies", "This Will Be Our Year", "Last.fm, Deezer", False), ("The Move", "Blackberry Way", "Last.fm", False),
        ("Small Faces", "Itchycoo Park", "Last.fm, ListenBrainz", False),
        ("The Left Banke", "Pretty Ballerina", "Last.fm", False), ("The Hollies", "Bus Stop", "Last.fm", True)]),
    ("2026-09-21 18:40", "Simon & Garfunkel", "Kitchen", "Kitchen Echo", [
        ("Harry Nilsson", "Without You", "Last.fm, YouTube", False),
        ("Fairport Convention", "Who Knows Where the Time Goes?", "Last.fm", False),
        ("The Zombies", "She's Not There", "Deezer", False), ("Nick Drake", "Pink Moon", "Last.fm", True),
        ("Donovan", "Sunshine Superman", "Last.fm, Deezer", False)]),
    ("2026-09-28 21:15", "The Byrds", "Speakers", "Main Window", [
        ("Big Star", "September Gurls", "ListenBrainz", False), ("The Turtles", "Eleanor", "Last.fm", False),
        ("The Left Banke", "Walk Away Renee", "Last.fm, ListenBrainz", False),
        ("Buffalo Springfield", "For What It's Worth", "Last.fm, Deezer", False),
        ("The Zombies", "Care of Cell 44", "Last.fm", False)]),
]
DEMO_TAGS = {
    "the beatles": [["classic rock", 100], ["rock", 80], ["psychedelic", 50]],
    "the kinks": [["classic rock", 100], ["rock", 70], ["british invasion", 60]],
    "the byrds": [["folk rock", 100], ["classic rock", 80], ["psychedelic", 60]],
    "simon & garfunkel": [["folk", 100], ["folk rock", 80], ["singer-songwriter", 60]],
    "the zombies": [["psychedelic pop", 100], ["baroque pop", 70], ["60s", 60], ["british invasion", 50]],
    "the move": [["psychedelic pop", 100], ["60s", 80], ["british invasion", 60]],
    "small faces": [["mod", 100], ["british invasion", 80], ["60s", 70]],
    "the left banke": [["baroque pop", 100], ["60s", 80], ["sunshine pop", 40]],
    "harry nilsson": [["singer-songwriter", 100], ["70s", 70], ["baroque pop", 40]],
    "fairport convention": [["folk rock", 100], ["british folk", 90]],
    "donovan": [["folk", 100], ["psychedelic folk", 90], ["60s", 80]],
    "big star": [["power pop", 100], ["70s", 80]],
    "the turtles": [["sunshine pop", 100], ["60s", 90], ["baroque pop", 50]],
    "buffalo springfield": [["folk rock", 100], ["60s", 90]],
    "the searchers": [["merseybeat", 100], ["british invasion", 90], ["60s", 80]],
    "gerry and the pacemakers": [["merseybeat", 100], ["60s", 90]],
    "electric light orchestra": [["classic rock", 100], ["70s", 80]],
    "the hollies": [["british invasion", 100], ["60s", 90]], "badfinger": [["power pop", 100], ["70s", 80]],
}
DEMO_CENTROIDS = {"1": {"classic rock": 0.7, "rock": 0.6, "psychedelic": 0.3},
                  "2": {"folk": 0.7, "singer-songwriter": 0.6, "folk rock": 0.4},
                  "3": {"electronic": 0.8, "ambient": 0.6}, "4": {"jazz": 0.8, "vocal jazz": 0.6},
                  "5": {"soul": 0.8, "motown": 0.6}}
# Fixed times, so Discover and the device list come out the same on every run
DEMO_SESSION_TIME = "2026-10-04 10:30"
DEMO_CONSOLE = [
    "21:14  Track Matching: The Beatles - Here Comes The Sun  (target 30, at most 2 per artist)",
    "  Last.fm: 50 similar tracks",
    "  ListenBrainz: 40 similar tracks (from cache)",
    "  YouTube: 25 similar tracks",
    "    In library: The Kinks - Waterloo Sunset  (Last.fm, ListenBrainz)",
    "    In library: The Hollies - Bus Stop  (Last.fm, YouTube)",
    "    Not in library: The Zombies - Time Of The Season",
    "    In library: George Harrison - What Is Life  (Last.fm, ListenBrainz, YouTube)",
    "    In library: The Byrds - Mr. Tambourine Man  (ListenBrainz)",
    "    Not in library: Harry Nilsson - Everybody's Talkin'",
    "    ...",
    "  Suggested 96, checked 96, in library 34.",
    "  Moderator (Balanced): checking 34 tracks against the seed...",
    "    Removed The Who - Won't Get Fooled Again: louder and harder than the seed.",
    "  Moderator: 1 removed.",
    "  Deep Cuts (Rock, spaced): 3 from tracks you rarely play: The Move - Flowers In The Rain, "
    "Badfinger - Take It All, The Zombies - Beechwood Park.",
    "  Sending 33 tracks...",
    "  Queued in Speakers after the current track.",
    "Done: 33 tracks queued in Speakers, 62 not in library, 14 s.",
]

# The console's Log: kept builds, with fixed times so the shots repeat. (at, tab, from, zone, zone ID, kind,
# sources, queued, misses, moderator, problems, notes, chain ID, chain position, text); chain IDs are row numbers.
KITCHEN_TEXT = """21:20  Voice, Kitchen Echo: tracks like Here Comes The Sun by The Beatles, to Kitchen
Track Matching: The Beatles - Here Comes The Sun  (target 30, at most 2 per artist)
  Last.fm: 50 similar tracks
  Problem: Deezer didn't answer for similar tracks (timed out).
  ListenBrainz: 40 similar tracks (from cache)
  YouTube: 25 similar tracks
    In library: The Kinks - Waterloo Sunset  (Last.fm, ListenBrainz)
    Not in library: The Zombies - Time Of The Season
    ...
  Suggested 96, checked 96, in library 34.
  Moderator (Balanced): checking 34 tracks against the seed...
    Removed The Who - Won't Get Fooled Again: louder and harder than the seed.
    Removed Queen - We Will Rock You: stadium energy, breaks the mood.
  Moderator: 2 removed.
  Note: Drift is off, so the playlist stops at 30 tracks. Settings > Playlist > Drift
  Sending 30 tracks...
  Queued in Kitchen after the current track.
Done: 30 tracks queued in Kitchen, 62 not in library, 14 s."""
# The demo console's lines in German (--lang de), as 24bit7 writes them; a line not here stays as it is
DEMO_GERMAN = {
    "Kitchen Tracks": "Küchen-Titel", "Stereo only": "Nur Stereo",   # the demo button and filter
    "Track Matching: The Beatles - Here Comes The Sun  (target 30, at most 2 per artist)":
        "Titel-Abgleich: The Beatles - Here Comes The Sun  (Ziel 30, höchstens 2 pro Künstler)",
    "Last.fm: 50 similar tracks": "Last.fm: 50 ähnliche Titel",
    "ListenBrainz: 40 similar tracks (from cache)": "ListenBrainz: 40 ähnliche Titel (aus dem Cache)",
    "YouTube: 25 similar tracks": "YouTube: 25 ähnliche Titel",
    "Problem: Deezer didn't answer for similar tracks (timed out).":
        "Problem: Deezer hat bei ähnlichen Titeln nicht geantwortet (Zeitüberschreitung).",
    "In library: The Kinks - Waterloo Sunset  (Last.fm, ListenBrainz)":
        "In Bibliothek: The Kinks - Waterloo Sunset  (Last.fm, ListenBrainz)",
    "In library: The Hollies - Bus Stop  (Last.fm, YouTube)": "In Bibliothek: The Hollies - Bus Stop  (Last.fm, YouTube)",
    "Not in library: The Zombies - Time Of The Season": "Nicht in Bibliothek: The Zombies - Time Of The Season",
    "In library: George Harrison - What Is Life  (Last.fm, ListenBrainz, YouTube)":
        "In Bibliothek: George Harrison - What Is Life  (Last.fm, ListenBrainz, YouTube)",
    "In library: The Byrds - Mr. Tambourine Man  (ListenBrainz)":
        "In Bibliothek: The Byrds - Mr. Tambourine Man  (ListenBrainz)",
    "Not in library: Harry Nilsson - Everybody's Talkin'": "Nicht in Bibliothek: Harry Nilsson - Everybody's Talkin'",
    "Suggested 96, checked 96, in library 34.": "Vorgeschlagen 96, geprüft 96, in der Bibliothek 34.",
    "Moderator (Balanced): checking 34 tracks against the seed...":
        "Moderator (Ausgewogen): prüfe 34 Titel gegen den Seed...",
    "Removed The Who - Won't Get Fooled Again: louder and harder than the seed.":
        "Entfernt The Who - Won't Get Fooled Again: lauter und härter als der Seed.",
    "Removed Queen - We Will Rock You: stadium energy, breaks the mood.":
        "Entfernt Queen - We Will Rock You: Stadion-Energie, bricht die Stimmung.",
    "Moderator: 1 removed.": "Moderator: 1 entfernt.",
    "Moderator: 2 removed.": "Moderator: 2 entfernt.",
    "Note: Drift is off, so the playlist stops at 30 tracks. Settings > Playlist > Drift":
        "Hinweis: Drift ist aus, daher endet die Playlist bei 30 Titeln. Einstellungen > Playlist > Drift",
    "Deep Cuts (Rock, spaced): 3 from tracks you rarely play: The Move - Flowers In The Rain, "
    "Badfinger - Take It All, The Zombies - Beechwood Park.":
        "Deep Cuts (Rock, verteilt): 3 aus Titeln, die du selten spielst: The Move - Flowers In The Rain, "
        "Badfinger - Take It All, The Zombies - Beechwood Park.",
    "Sending 33 tracks...": "Sende 33 Titel...",
    "Sending 30 tracks...": "Sende 30 Titel...",
    "Queued in Speakers after the current track.": "In Speakers nach dem aktuellen Titel eingereiht.",
    "Queued in Kitchen after the current track.": "In Kitchen nach dem aktuellen Titel eingereiht.",
    "Done: 33 tracks queued in Speakers, 62 not in library, 14 s.":
        "Fertig: 33 Titel in Speakers eingereiht, 62 nicht in der Bibliothek, 14 s.",
    "Done: 30 tracks queued in Kitchen, 62 not in library, 14 s.":
        "Fertig: 30 Titel in Kitchen eingereiht, 62 nicht in der Bibliothek, 14 s.",
    "Voice, Kitchen Echo: tracks like Here Comes The Sun by The Beatles, to Kitchen":
        "Sprache, Kitchen Echo: Titel wie Here Comes The Sun von The Beatles, in Kitchen",
    "AI Playlist: rainy Sunday morning  (target 25 tracks)": "KI-Playlist: rainy Sunday morning  (Ziel 25 Titel)",
    "Done: 22 tracks queued in Speakers, 0 not in library, 11 s.":
        "Fertig: 22 Titel in Speakers eingereiht, 0 nicht in der Bibliothek, 11 s.",
    "Shortcut: Similar Tracks": "Tastenkürzel: Ähnliche Titel",
    "Done: 30 tracks queued in Speakers, 47 not in library, 12 s.":
        "Fertig: 30 Titel in Speakers eingereiht, 47 nicht in der Bibliothek, 12 s.",
    "Voice, Lounge Dot: album Abbey Raod": "Sprache, Lounge Dot: album Abbey Raod",
    "Problem: Alexa said \"I couldn't find an album called Abbey Raod.\"":
        "Problem: Alexa sagte \"I couldn't find an album called Abbey Raod.\"",
    "Non-stop: Kitchen reached its last track": "Non-stop: Kitchen hat den letzten Titel erreicht",
    "Done: 30 tracks queued in Kitchen, 55 not in library, 12 s.":
        "Fertig: 30 Titel in Kitchen eingereiht, 55 nicht in der Bibliothek, 12 s.",
    "Done: 28 tracks queued in Kitchen, 41 not in library, 13 s.":
        "Fertig: 28 Titel in Kitchen eingereiht, 41 nicht in der Bibliothek, 13 s.",
}


def in_language(text):
    """The demo console's text in the shots' language: each line looked up without its time and indent."""
    if i18n.LANGUAGE != "de":
        return text
    out = []
    for line in text.split("\n"):
        body = line.lstrip()
        stamp = body[:7] if len(body) > 7 and body[2] == ":" and body[5:7] == "  " else ""
        body = body[len(stamp):]
        out.append(line[:len(line) - len(line.lstrip())] + stamp + DEMO_GERMAN.get(body, body))
    return "\n".join(out)


DEMO_BUILDS = [
    ("2026-10-04 19:12:40", "main", "Main Window", "Speakers", "10001", "AI Playlist", "AI", 22, 0, "", 0, 1,
     None, None, "19:12  AI Playlist: rainy Sunday morning  (target 25 tracks)\nDone: 22 tracks queued in Speakers, "
     "0 not in library, 11 s."),
    ("2026-10-04 20:40:12", "main", "Shortcut", "Speakers", "10001", "Track Matching", "Last.fm, ListenBrainz", 30,
     47, "Relaxed, 0 removed", 0, 0, None, None, "20:40  Shortcut: Similar Tracks\nDone: 30 tracks queued in "
     "Speakers, 47 not in library, 12 s."),
    ("2026-10-04 20:51:03", "demo-lounge", "Lounge Dot", "", "", "Album", "", None, None, "", 1, 0, None, None,
     "20:51  Voice, Lounge Dot: album Abbey Raod\n  Problem: Alexa said \"I couldn't find an album called "
     "Abbey Raod.\""),
    ("2026-10-04 21:14:22", "main", "Main Window", "Speakers", "10001", "Track Matching",
     "Last.fm, ListenBrainz, YouTube", 30, 62, "Balanced, 1 removed", 0, 0, None, None, "\n".join(DEMO_CONSOLE)),
    ("2026-10-04 21:20:05", "demo-kitchen", "Kitchen Echo", "Kitchen", "10002", "Track Matching",
     "Last.fm, ListenBrainz, YouTube", 30, 62, "Balanced, 2 removed", 1, 1, 5, 1, KITCHEN_TEXT),
    ("2026-10-04 21:31:47", "demo-kitchen", "Non-stop", "Kitchen", "10002", "Track Matching",
     "Last.fm, ListenBrainz, YouTube", 30, 55, "Balanced, 3 removed", 0, 0, 5, 2,
     "21:31  Non-stop: Kitchen reached its last track\nDone: 30 tracks queued in Kitchen, 55 not in library, 12 s."),
    ("2026-10-04 21:42:09", "demo-kitchen", "Non-stop", "Kitchen", "10002", "Track Matching",
     "Last.fm, ListenBrainz, YouTube", 28, 41, "Balanced, 1 removed", 0, 0, 5, 3,
     "21:42  Non-stop: Kitchen reached its last track\nDone: 28 tracks queued in Kitchen, 41 not in library, 13 s."),
]


# --- picking which shots to take -------------------------------------------

def git(*args):
    r = subprocess.run(["git"] + list(args), cwd=HERE, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def needs_retake(name, deps):
    """True if the image is missing, uncommitted, or its code has changed since it was committed."""
    image = os.path.join("docs", IMAGES, name + ".png")
    if not os.path.exists(os.path.join(HERE, image)):
        return True
    image_time = git("log", "-1", "--format=%ct", "--", image)
    if not image_time:
        return True   # never committed
    files = deps + COMMON
    if git("status", "--porcelain", "--", *files):
        return True   # code changed and not committed yet
    code_time = git("log", "-1", "--format=%ct", "--", *files)
    return bool(code_time) and int(code_time) > int(image_time)


def choose(args):
    names = [s[0] for s in SHOTS]
    if args.list:
        for name, path, deps, _ in SHOTS:
            print(f"  {name:36} {' > '.join(path):45} {', '.join(deps)}")
        sys.exit(0)
    if args.names:
        unknown = [n for n in args.names if n not in names]
        if unknown:
            print("Unknown name(s): " + ", ".join(unknown) + ". Use --list to see them.")
            sys.exit(1)
        return [s for s in SHOTS if s[0] in args.names]
    if args.changed:
        if not git("rev-parse", "--is-inside-work-tree"):
            print("--changed needs the 24bit7 git folder.")
            sys.exit(1)
        return [s for s in SHOTS if needs_retake(s[0], s[2])]
    return list(SHOTS)


# --- demo mode -------------------------------------------------------------

def load_gui():
    """Imports gui.pyw as a module, without running its main()."""
    sys.path.insert(0, HERE)
    os.chdir(HERE)
    loader = importlib.machinery.SourceFileLoader("gui", os.path.join(HERE, "gui.pyw"))
    spec = importlib.util.spec_from_loader("gui", loader)
    gui = importlib.util.module_from_spec(spec)
    loader.exec_module(gui)
    return gui


def demo_env(src, dst):
    """A copy of .env with every key and password swapped for a dummy."""
    lines, seen = [], set()
    replace = dict(DEMO_KEYS, **DEMO_ENV)
    if os.path.exists(src):
        with open(src, encoding="utf-8") as f:
            for line in f.read().splitlines():
                key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
                if key in replace:
                    line = f"{key}={replace[key]}"
                    seen.add(key)
                lines.append(line)
    lines += [f"{k}={v}" for k, v in replace.items() if k not in seen]
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def start_demo(gui, temp):
    engine, settings_gui, voice, saved_playlists = gui.engine, sys.modules["settings_gui"], gui.voice, \
        sys.modules["saved_playlists"]

    # Settings from the dummy copy; nothing is ever written to the real .env
    env_path = os.path.join(temp, ".env")
    demo_env(engine.ENV_FILE, env_path)
    engine.ENV_FILE = settings_gui.ENV_FILE = env_path

    # JRiver: a dead address, so anything not faked below fails at once instead of reading your library
    original_load = engine.load_settings

    def load_settings():
        original_load()
        engine.JRIVER_BASE = "http://127.0.0.1:9/MCWS/v1"
    engine.load_settings = load_settings
    engine.load_settings()
    engine._env_mtime = os.path.getmtime(env_path)
    engine._read_zones = lambda: (list(DEMO_ZONES), DEMO_ZONES[0][0])
    engine.get_playing_info = lambda zone=None: dict(DEMO_PLAYING)
    engine.dev_copy = lambda: False   # the manual shows the app as people get it, even when shot from a dev folder
    saved_playlists.scan = lambda: [dict(p) for p in DEMO_PLAYLISTS]
    voice._status = f"Listening on 127.0.0.1:{engine.VOICE_PORT}"   # shown as running; nothing is started

    # A temporary database with the demo sessions, discoveries and devices
    if engine._db is not None:
        engine._db.close()
    engine._db = None
    engine.DB_FILE = os.path.join(temp, "24bit7.db")
    engine.CSV_FILE = os.path.join(temp, "none.csv")   # never import your old discoveries log
    con = engine.db()
    for started, seed, zone, asked, seen in DEMO_MORE_SESSIONS:   # Discover > Missing Artists (1.34.0), before the session Sessions opens on
        sid = con.execute("INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued, "
                          "zone, asked_by) VALUES (?,?,?,?,?,?,?,?,?)",
                          (started, "similar", seed, "", "", "Last.fm, ListenBrainz, Deezer", 30, zone, asked)).lastrowid
        for artist, track, sources, found in seen:
            con.execute("INSERT INTO discoveries (session_id, artist, track, sources, found) VALUES (?,?,?,?,?)",
                        (sid, artist, track, sources, 1 if found else 0))
    cur = con.execute("INSERT INTO sessions (started_at, mode, seed_artist, seed_track, seed_album, sources, queued) "
                      "VALUES (?,?,?,?,?,?,?)", (DEMO_SESSION_TIME, "similar", "The Beatles", "Here Comes The Sun",
                                                 "Abbey Road", "Last.fm, ListenBrainz, Deezer, YouTube", 30))
    for artist, track, sources, found in DEMO_DISCOVERIES:
        con.execute("INSERT INTO discoveries (session_id, artist, track, sources, found) VALUES (?,?,?,?,?)",
                    (cur.lastrowid, artist, track, sources, 1 if found else 0))
    con.execute("UPDATE sessions SET zone='Speakers', asked_by='Main Window' WHERE id=?", (cur.lastrowid,))
    import library
    owned = {library.norm(a) for a in DEMO_OWNED}
    library.has_artist = lambda name: library.norm(name or "") in owned   # never the real library
    library.album_list = lambda: list(DEMO_ALBUMS)
    try:
        import discover_stats
        discover_stats.fetch_tags = lambda names, cancelled=None: 0   # no Last.fm in demo mode
    except ImportError:
        pass
    voice._devices_table()
    for device_id, name, zone, own, heard in DEMO_DEVICES:
        con.execute("INSERT INTO voice_devices (device_id, name, zone, last_heard, own_settings) VALUES (?,?,?,?,?)",
                    (device_id, name, zone, heard, own))
    con.commit()
    saved_playlists.set_main_settings({"rows": {pid: dict(row) for pid, row in DEMO_SAVED_ROWS.items()}})
    # Playlists and devices: the standard five from the demo .env, a Kitchen Tracks playlist of your own with a
    # Stereo only filter and a shortcut, and the Kitchen Echo running it for "tracks like this"
    import buttons
    import devices
    import filters
    stereo = filters.blank(in_language("Stereo only"))
    stereo["rules"] = [{"field": "sample_rate", "op": "at_most", "value": "48", "value2": ""}]
    filters.save([stereo])
    buttons.load()
    kitchen = buttons.add(in_language("Kitchen Tracks"), "tracks")
    buttons.set_settings(kitchen["id"], dict(kitchen["settings"], AI_MODERATOR_TRACKS="balanced", SIMILAR_TRACK_COUNT="20"))
    buttons.set_filters(kitchen["id"], [stereo["id"]])
    buttons.set_shortcut(kitchen["id"], "Ctrl+Alt+2")
    items = buttons.load()   # the Kitchen Echo's own playlist: off the Play tab, in the Devices box (1.30)
    copied = buttons.standard("tracks")
    for b in items:
        if b["id"] == kitchen["id"]:
            b["device"] = "demo-kitchen"
            b["copied_from"] = copied["id"] if copied else ""   # Copy Settings From shows it greyed (1.30.1)
    buttons.save(items)
    record = devices.for_device("demo-kitchen")
    record["buttons"]["tracks_like"] = kitchen["id"]
    devices.update("demo-kitchen", buttons=record["buttons"])
    try:   # Radio's lanes, its face on Classic Rock with the split open, and the recent JRiver playlists (1.31.0)
        import embellish
        import radio
        analysis = json.loads(json.dumps(DEMO_RADIO))
        for lane in analysis["lanes"]:   # where Discover > Missing Artists files an artist (1.34.0)
            lane["centroid"] = DEMO_CENTROIDS.get(lane["id"], {})
        radio._set_meta(radio.ANALYSIS_KEY, analysis)
        radio._set_meta(radio.TAGS_KEY, {engine.artist_key(k): v for k, v in DEMO_TAGS.items()})   # keyed as Radio keys them
        radio.set_row(default="1", open=["1"], buttons=[])
        embellish._set_meta(embellish.RECENT_KEY, DEMO_RECENT)
    except ImportError:
        pass
    try:   # the console's Log (1.11.0 and later)
        import buildlog
        buildlog._table(con)
        cols = ["at", "tab", "from_label", "zone", "zone_id", "kind", "sources", "queued", "misses", "moderator",
                "problems", "notes", "chain_id", "chain_pos", "text"]
        for values in DEMO_BUILDS:
            row = dict(zip(cols, values))
            row["text"] = in_language(row["text"])
            buildlog._insert(con, row)
    except ImportError:
        pass


def draw_at_100(root):
    """
    Draws the demo window at 100% sizes whatever Windows' display scaling (300% on a 4K
    screen), so the shots match whether taken on the PC itself, over Remote Desktop or on
    a laptop: Tk is told the screen is 96 dots per inch, and its own fonts, set in screen
    pixels at the real scaling, are put back in points.
    """
    import tkinter as tk
    import tkinter.font as tkfont
    real = root.winfo_fpixels("1i")
    if real <= 96.5:
        return
    root.tk.call("tk", "scaling", 96 / 72.0)
    # Windows' own scrollbars (the console's) take the real scaling's width unless told otherwise
    probe = tk.Scrollbar(root)
    root.option_add("*Scrollbar.width", max(1, round(int(probe.cget("width")) * 96 / real)))
    probe.destroy()
    for name in tkfont.names(root):
        f = tkfont.nametofont(name, root)
        size = f.cget("size")
        if size < 0:   # pixels at the real scaling: back to points
            f.configure(size=max(1, round(-size * 72 / real)))


def build_window(gui):
    """The main window as gui.main() builds it, minus voice, shortcuts, tray and the library read."""
    tk, engine, PALETTE = gui.tk, gui.engine, gui.PALETTE
    gui._enable_dpi_awareness()
    root = tk.Tk()
    draw_at_100(root)
    gui._set_window_icon(root)
    gui.apply_theme(root, engine.THEME, engine.ACCENT_COLOUR)
    root.title(f"24bit7  v{engine.VERSION}")
    scale = root.winfo_fpixels("1i") / 96.0
    global SCALE
    SCALE = scale   # 1 once drawn at 100%; kept so a shot is never saved at another size
    if root.winfo_screenwidth() < 1180 * scale + 80 or root.winfo_screenheight() < 820 * scale + 120:
        # the shots are 1180 by 820 at 100%; a smaller screen would give the manual shots of another size
        # (2 Nov 2026: the TV off left Windows with a 1365 by 720 stand-in screen)
        root.destroy()
        sys.exit(f"The screen is {root.winfo_screenwidth()}x{root.winfo_screenheight()}, too small for the shots. "
                 "Is the TV on, and on the PC's input?")
    w = min(int(1180 * scale), root.winfo_screenwidth() - 80)
    h = min(int(820 * scale), root.winfo_screenheight() - 120)
    root.geometry(f"{w}x{h}+40+40")
    root.attributes("-topmost", True)

    nb = gui.TabbedPane(root, font=("Segoe UI", 11, "bold"), pad=(20, 8), strip=True)
    nb.pack(fill="both", expand=True)
    play = gui.PlayTab(nb, root)
    discover = gui.DiscoverTab(nb)
    settings = gui.SettingsTab(nb)
    play.settings = settings
    # "Windows starts a different copy of 24bit7" is about this PC (the demo runs from the source
    # folder), not something a reader of the manual should see
    settings._show_startup_note = lambda: getattr(settings, "startup_note", None) and settings.startup_note.grid_remove()
    settings._show_startup_note()
    nb.add(play, text=i18n.t("Play"))
    nb.add(discover, text=i18n.t("Discover"))
    nb.add(settings, text=i18n.t("Settings"))

    donate = tk.Label(root, text="Support", font=("Segoe UI", 9, "underline"),
                      fg=PALETTE.get("strip_fg") or PALETTE["link"], bg=PALETTE.get("strip_bg") or root.cget("bg"))

    def place_donate(event=None):
        if event is not None and event.widget is not root:
            return
        if root.winfo_width() - nb.tabs_width() - donate.winfo_reqwidth() - 40 > 0:
            donate.place(relx=1.0, x=-16, y=nb.winfo_y() + nb.strip_height() // 2, anchor="e")
    root.bind("<Configure>", place_donate, add="+")

    def on_tab_changed(_e):
        if nb.select() == str(discover):
            discover.ensure_loaded()
        elif nb.select() == str(play):
            play.sync_moderator()
    nb.bind("<<NotebookTabChanged>>", on_tab_changed)

    # The console: no greeting, just the demo build
    play._greeting_active = False
    play._stamp_next = False
    play._clear_log()
    for line in in_language("\n".join(DEMO_CONSOLE)).split("\n"):
        play._append_log(line)
    return root, nb, play


# --- capture ---------------------------------------------------------------

def settle(root, seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.05)


def panes_in(widget, TabbedPane):
    """Every TabbedPane inside widget, outermost first."""
    found, todo = [], [widget]
    while todo:
        w = todo.pop(0)
        if isinstance(w, TabbedPane):
            found.append(w)
        todo.extend(w.winfo_children())
    return found


def go_to(root, path, TabbedPane):
    """Clicks through tab names, each looked for inside the page the last one opened."""
    where = root
    for text in path:
        for pane in panes_in(where, TabbedPane):
            texts = [t.cget("text") for t in pane._tabs]
            text = i18n.t(text)   # the tab's name in the shots' language
            if text in texts:
                page = pane._pages[texts.index(text)]
                pane.select(page)
                settle(root, 0.3)
                where = page
                break
        else:
            raise RuntimeError(f"couldn't find a tab called {text!r}")
    return where


def show_review(play):
    """The Review list with the demo shortlist: three ticked in order, a preview zone chosen, one previewing."""
    panel = play.review_panel
    seed = "The Beatles - Here Comes The Sun"
    rows = [{"key": str(2000 + n), "artist": a, "title": t, "album": al, "seconds": s, "bpm": b,
             "why": DEMO_FOUND_BY[n],
             "why_more": i18n.t("{sources} named {artist} as like {seed}.", sources=DEMO_FOUND_BY[n], artist=a,
                                seed=seed)}
            for n, (a, t, al, s, b) in enumerate(DEMO_REVIEW)]
    panel.load(rows, i18n.t("Artist Matching: {seed_label}", seed_label="The Beatles - Here Comes The Sun"),   # as the console heads it
               DEMO_ZONES[0][0])
    panel.preview_name, panel.preview_zone = "Kitchen", DEMO_ZONES[1][0]   # set directly: no JRiver in demo mode
    panel._render()
    for key in ("2003", "2001", "2004"):
        panel.toggle(key)
    panel.previewing, panel.preview_at = "2002", DEMO_ZONES[1][0]
    panel._restyle()
    panel.show_review()


def open_ai_window(gui, root, play, mode):
    """The AI Playlist window over the Play tab, filled from demo data so no AI request is made."""
    engine = gui.engine
    engine.ai_vibe_suggestions = lambda: list(DEMO_IDEAS)
    engine.ai_assess_tone = lambda pairs: DEMO_TONE
    from settings_gui import write_env
    write_env({"AI_DIALOG_MODE": mode, "AI_CREATE_THEME": "", "AI_STEER_TONE": DEMO_TONE if mode == "steer" else "",
               "AI_STEER_DIRS": "dancier,faster" if mode == "steer" else "", "AI_STEER_OWN": "",
               "AI_STEER_STRENGTH": "little", "AI_STEER_SEED": "current", "AI_IF_SHORT": "ask"})
    import ai_dialog
    dialog = ai_dialog.AIPlaylistDialog(root, play=play, on_create=lambda *a: None, on_steer=lambda *a: None)
    settle(root, 1.2)
    return dialog


def window_image(window):
    """The window's client area as Windows itself draws it, whatever covers it or whether a screen is on."""
    import ctypes
    from PIL import ImageGrab
    return ImageGrab.grab(window=ctypes.windll.user32.GetAncestor(window.winfo_id(), 2))


def grab_box(window, bbox, above=None):
    """
    A screen grab of bbox, or, when there's no screen to grab (the TV off, so Windows reports no monitor
    and a screen grab fails; 2 Nov 2026), the window as Windows itself draws it, cropped to the same box.
    That draws one window alone, so an open drop-down list (above) is drawn too and pasted in where it sits
    (12 Nov 2026: the Playlists & Albums shot came out without its list).
    """
    from PIL import ImageGrab
    try:
        return ImageGrab.grab(bbox=bbox)
    except OSError:
        image = window_image(window)   # the window's client area, whose origin Tk reports
        left, top = window.winfo_toplevel().winfo_rootx(), window.winfo_toplevel().winfo_rooty()
        x0, y0, x1, y1 = bbox
        image = image.crop((max(0, x0 - left), max(0, y0 - top), min(image.width, x1 - left), min(image.height, y1 - top)))
        if above is not None:
            image.paste(window_image(above), (above.winfo_rootx() - x0, above.winfo_rooty() - y0))
        return image


def grab_window(window):
    window.update_idletasks()
    x, y = window.winfo_rootx(), window.winfo_rooty()
    return grab_box(window, (x - 1, y - 1, x + window.winfo_width() + 1, y + window.winfo_height() + 1))


def grab(root, above=None):
    """The window as it shows; above is an open drop-down list, lifted back over the window, which stays on top
    for the shots and would otherwise cover it (7 Nov 2026)."""
    root.lift()
    if above is not None:
        above.lift(root)
    settle(root, 0.2)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    return grab_box(root, (x, y, x + root.winfo_width(), y + root.winfo_height()), above)   # the main screen


def scroll_canvas(page):
    """The page's scrolling canvas, if its content is taller than the window."""
    best, todo = None, [page]
    while todo:
        w = todo.pop()
        todo.extend(w.winfo_children())
        if w.winfo_class() == "Canvas" and w.winfo_ismapped() and str(w.cget("yscrollcommand")):
            box = w.bbox("all")
            if box and box[3] > w.winfo_height() + 2 and (best is None or w.winfo_height() > best.winfo_height()):
                best = w
    return best


def capture(root, page, above=None):
    """The window, with a long page scrolled through and stitched into one tall image."""
    from PIL import Image
    first = grab(root, above)
    canvas = scroll_canvas(page)
    if canvas is None:
        return first
    width = first.width
    top = canvas.winfo_rooty() - root.winfo_rooty()
    view = canvas.winfo_height()
    total = canvas.bbox("all")[3]
    # Only the scrolling part moves: a page with a list beside its canvas (Settings > Buttons) keeps the
    # list as the first shot had it, over a background taken from the bottom row of the first view
    holder = canvas.master
    left = holder.winfo_rootx() - root.winfo_rootx()
    right = left + holder.winfo_width()
    pieces, y = [], 0
    while y < total:
        canvas.yview_moveto(y / total)
        settle(root, 0.25)
        shown = int(canvas.canvasy(0))
        shot = grab(root, above)
        end = min(shown + view, total)
        pieces.append(shot.crop((left, top + (y - shown), right, top + (end - shown))))
        if end <= y:
            break
        y = end
    canvas.yview_moveto(0)
    head = first.crop((0, 0, width, top))
    foot = first.crop((0, top + view, width, first.height))
    body_height = sum(p.height for p in pieces)
    out = Image.new("RGB", (width, head.height + body_height + foot.height))
    out.paste(head, (0, 0))
    backdrop = first.crop((0, top + view - 1, width, top + view)).resize((width, body_height))
    out.paste(backdrop, (0, head.height))
    out.paste(first.crop((0, top, width, top + view)), (0, head.height))   # the first view, list included
    at = head.height
    for part in pieces:
        out.paste(part, (left, at))
        at += part.height
    out.paste(foot, (0, at))
    # The scrollbar shows a different position in every piece, so it's painted out
    for bar in canvas.master.winfo_children():
        if bar.winfo_class() == "TScrollbar" and bar.winfo_ismapped():
            x = bar.winfo_rootx() - root.winfo_rootx()
            r, g, b = (v // 256 for v in root.winfo_rgb(canvas.cget("bg")))
            out.paste((r, g, b), (x, top, x + bar.winfo_width(), top + body_height))
    return out


def save_if_changed(image, name):
    """Writes the PNG only if the picture differs from the one already there. Returns True if written."""
    from PIL import Image, ImageChops
    path = os.path.join(OUT_DIR, name + ".png")
    image = image.convert("RGB")
    if SCALE > 1.01:   # taken at, say, 300% scaling: shrunk to the 100% size, so every shot matches
        image = image.resize((round(image.width / SCALE), round(image.height / SCALE)), Image.LANCZOS)
    if os.path.exists(path):
        with Image.open(path) as old:
            old = old.convert("RGB")
            if old.size == image.size and ImageChops.difference(old, image).getbbox() is None:
                return False
    image.save(path, optimize=True)
    return True


def show_multiroom(settings, root):
    """
    The Multiroom section on, with a Sonos One, the Multiroom server and the Hugo "found" (stand-ins, nothing on
    the network) and Check Clock's verdict shown, scrolled into view. Uses the demo zones: Kitchen leads, Speakers follow.
    """
    import tkinter as tk
    from types import SimpleNamespace
    from multiroom import sonos, fetch, mcws, output, clockcheck
    sonos.find = lambda name=None, **k: [{"ip": "192.168.0.184", "name": "Kitchen", "model": "Sonos One",
                                          "householdId": "h", "groupId": "g"}]
    fetch.find_server = lambda name, **k: "http://192.168.0.133:52101"
    mcws.JRiver.device = lambda self, zone: ("Hugo (Chord Async USB 44.1kHz-384kHz)", "ASIO")
    output.find_device = lambda hint, found=None, prefer="ASIO": 18
    output._sd = lambda: SimpleNamespace(query_devices=lambda i: {"name": "ASIO Chord  1.04"})
    clockcheck.measure = lambda *a, **k: clockcheck.Verdict(
        "green", "Clock: millisecond position, 4 ms round trip, steady. Good.", 900, True, 4.0, 1.0, "ms_good", {"rtt": "4"})
    s = settings
    s.vars["MULTIROOM_ENABLED"].set(True)
    s.vars["MULTIROOM_LEADER"].set("Kitchen")
    s.vars["MULTIROOM_FOLLOWER"].set("Speakers")
    s._mr_leader_cb.set("Kitchen")      # the boxes show their own text, set from the vars when they were built
    s._mr_follower_cb.set("Speakers")
    s._sync_multiroom_parts()
    # the lookup and the clock check run on threads and report through after(), which needs a mainloop this
    # window hasn't got: show their answers directly
    s._mr_refreshing = True
    s._multiroom_show_found({"speakers": sonos.find(), "server": fetch.find_server("Multiroom"),
                             "hint": "Hugo (Chord Async USB 44.1kHz-384kHz)", "device": "ASIO Chord  1.04",
                             "problem": ""})
    s._multiroom_show_verdict(clockcheck.measure())
    settle(root, 0.3)
    outer = s._mr_box.master
    canvas = outer.master.master
    settle(root, 0.2)
    if isinstance(canvas, tk.Canvas):
        canvas.yview_moveto(max(0, (outer.winfo_y() - 8) / max(1, outer.master.winfo_height())))
    settle(root, 0.3)


def show_calibrate(settings, root):
    """The Calibrate Multiroom window, with the result of a run shown (the numbers from Ben's second run, 9 Nov)."""
    from multiroom import calibrate_fit
    win = settings._multiroom_calibrate()
    r = calibrate_fit.Result()
    r.start, r.resume, r.dac, r.repeat = 93.1, 99.5, 1746, 0.5
    settings._mr_load_btn.config(state="disabled")
    settings._calibrate_show(r, None)
    settle(root, 0.4)
    return win


def main():
    parser = argparse.ArgumentParser(description="Screenshots for the 24bit7 manual, from demo data.")
    parser.add_argument("names", nargs="*", help="shot names to take (default: all)")
    parser.add_argument("--changed", action="store_true", help="only shots whose code has changed")
    parser.add_argument("--list", action="store_true", help="list the shot names and stop")
    parser.add_argument("--lang", default="en", help="the language to take them in (de: into docs/images/de)")
    args = parser.parse_args()
    global OUT_DIR, IMAGES
    if args.lang not in dict(i18n.LANGUAGES):
        print(f"No language called {args.lang!r}.")
        sys.exit(1)
    if args.lang != "en":
        IMAGES = "images/" + args.lang
        OUT_DIR = os.path.join(HERE, "docs", "images", args.lang)
    if sys.platform != "win32":
        print("Screenshots are taken on Windows only.")
        sys.exit(1)
    try:
        import PIL.ImageGrab  # noqa: F401
    except ImportError:
        print("Needs Pillow: py -m pip install Pillow")
        sys.exit(1)

    shots = choose(args)
    if not shots:
        print("Nothing to retake: every screenshot is up to date with its code.")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Taking {len(shots)} screenshot(s). Leave the mouse and keyboard alone until it says done.")

    temp = tempfile.mkdtemp(prefix="24bit7_demo_")
    gui = load_gui()
    i18n.set_language(args.lang)   # as gui.main() does, before any screen is built
    start_demo(gui, temp)
    root, nb, play = build_window(gui)
    written, same = [], []
    try:
        settle(root, 1.5)   # Now Playing's first read happens just after the window appears
        for name, path, _deps, action in shots:
            page = go_to(root, path, gui.TabbedPane)
            tabs = hasattr(play, "_set_tabs_open")   # the console's tabs (1.11.0 and later)
            if tabs and play.tabs_open and action not in ("tabs_kitchen", "tabs_log"):
                play._set_tabs_open(False, save=False)
            if action == "more_open":
                play._show_more(True, save=False)
            elif action in ("more_closed", "tabs_kitchen", "tabs_log"):
                play._show_more(False, save=False)
            if tabs and action in ("tabs_kitchen", "tabs_log"):
                play._set_tabs_open(True, save=False)
                if action == "tabs_log":
                    play._select_view("log")
                else:   # the Kitchen Echo build that started its Non-stop chain, opened from the Log
                    import buildlog
                    play._load_build(next(r for r in buildlog.recent("demo-kitchen") if r["chain_pos"] == 1))
            dialog = popup = None
            if action and action.startswith("button:"):   # a playlist's page (the third part, an old inner tab, is ignored)
                _, which, _tab = action.split(":")
                import buttons
                wanted = in_language(which) if which in DEMO_GERMAN else i18n.t(which)
                target = next(b for b in buttons.load() if b["name"] == wanted)
                play.settings._button_id = target["id"]
                play.settings._buttons_refresh()
                settle(root, 0.5)
            elif action and action.startswith("device:"):   # the device's tab, its first own playlist open as its row opens it
                import devices
                device_id = action.split(":")[1]
                play.settings._device_id = device_id
                play.settings._buttons_refresh()
                phrase = next((ph for ph, _l, _b, own in devices.rows(device_id) if own), "music_like")
                play.settings._device_slot_page(device_id, phrase)   # with the strip at the top (3 Nov 2026)
                settle(root, 0.5)
            elif action == "edit_filters":
                dialog = play.settings._open_filters()
            elif action == "multiroom":   # Settings > Other scrolled to Multiroom, the kit "found" (1.32.0)
                show_multiroom(play.settings, root)
            elif action == "calibrate":   # the Calibrate Multiroom window with a result shown (1.32.0)
                show_multiroom(play.settings, root)
                dialog = show_calibrate(play.settings, root)
            elif action == "playlists_list":   # an artist typed, their albums listed under the box (1.36.0)
                play._show_more(False, save=False)
                play._close_playlists_if_away = lambda: None   # the shot takes the keyboard from the box
                play.playlist_entry.delete(0, "end")
                play.playlist_entry.insert(0, "Beatles")
                settle(root, 0.3)
                play._open_playlists()
                popup = play._playlists_pop
            elif action == "radio_list":   # Radio's arrow open: the lanes, Classic Rock split
                play._show_more(False, save=False)
                play._close_children_if_unfocused = lambda: None
                import buttons
                if not play._radio_buttons():   # Radio is a playlist now (1.31.0): one on the row
                    buttons.add_from_choice(("template", "radio"))
                    play.refresh_buttons()
                    settle(root, 0.3)
                play._open_radio(play._radio_buttons()[0]._button)
                popup = play._children_popup
            if action in ("sessions", "missing_artists"):   # Discover's tabs (1.34.0)
                discover = page
                if action == "sessions":
                    discover.pane.select(discover.sessions_page)
                else:
                    discover.show_view("Missing Artists")
                    stats = discover.missing_page
                    end = time.time() + 15
                    while not stats.ready and time.time() < end:
                        settle(root, 0.2)
                    if stats.tree.get_children():
                        stats.tree.selection_set(stats.tree.get_children()[0])
                settle(root, 0.5)
            if action == "review":
                show_review(play)
            elif action in ("ai_create", "ai_steer"):
                play._show_more(False, save=False)
                dialog = open_ai_window(gui, root, play, "steer" if action == "ai_steer" else "create")
            settle(root, 1.0 if name in ("settings_jriver_playlists", "play_review") or dialog else 0.5)
            if popup is not None:   # a drop-down list, kept above the window while it's grabbed
                popup.attributes("-topmost", True)
                settle(root, 0.3)
            image = grab_window(dialog) if dialog else capture(root, page, popup)
            if popup is not None:
                try:
                    popup.destroy()
                except Exception:
                    pass
                play._playlists_pop = play._children_popup = None
            (written if save_if_changed(image, name) else same).append(name)
            print(f"  {name}: {'saved' if name in written else 'unchanged'}")
            if dialog is not None:
                dialog.destroy()
            if action == "review" and getattr(play, "review_panel", None) is not None:
                play.review_panel.show_console()
    finally:
        root.destroy()
        if gui.engine._db is not None:
            gui.engine._db.close()
        shutil.rmtree(temp, ignore_errors=True)

    print(f"\nDone. {len(written)} saved, {len(same)} unchanged, in docs/{IMAGES}.")
    if written:
        print(f"Commit them with:  git add docs/{IMAGES}; git commit -m \"Manual screenshots\"")


if __name__ == "__main__":
    main()
