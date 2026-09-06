# 24bit7

**Smart playlist creation for JRiver Media Center.**

If you host your whole music library locally in JRiver, you get bit-perfect playback and none of the discovery. Streaming services will happily tell you what to play next; JRiver will not. 24bit7 fills that gap, using recommendation data from Last.fm, ListenBrainz, Deezer and an AI model, matched against the music you already own.

**It works live.** Play any track in JRiver, press a key, and Playing Now is rebuilt around it while the music keeps going. There is nothing to export, no listening history to upload and no second app to keep in sync: whatever is playing right now is the seed. Run it mid-album, mid-track, whenever the mood shifts.

Everything it can't find in your library is logged, so the misses become a shopping list.

The name is a throwback to an old username. Read it as 24-bit and 24/7: audiophile and always on.

---

## What it does

Four actions on the **Play** tab, all seeded from whatever JRiver is playing right now:

| Action | What you get |
|---|---|
| **Similar Artists** | A playlist built from artists similar to the current one, blended from whichever sources you have enabled. Each artist (the seed included) contributes a random pick from its top tracks, so the same seed gives a different playlist every run. |
| **Artist's Top Tracks** | The current artist's most popular tracks that you actually own, in random or popularity order. |
| **Vibe Playlist** | Type a mood or scene (or pick one of three AI suggestions) and get a playlist to match, built only from your library. |
| **Show Credits** | Producer, engineer and other credits for the current album, from Discogs. |

Two supporting tabs:

- **Discover** lists every track a run looked for, whether it was found (hit) or not (miss), filterable by session and searchable across all fields. Searching a row opens one browser tab per site you have ticked: digital stores search for the track (Bandcamp, Qobuz, Bleep, Beatport and more), reference sites search for the artist (Wikipedia, Discogs, AllMusic, MusicBrainz) so you can browse the discography. Misses are one click from purchase.
- **Settings** holds all keys and preferences. Changes save immediately and the running app picks them up without a restart.

---

## How it works

24bit7 is a small set of Python files:

- `engine.py` does all the work: talks to JRiver, queries the recommendation sources, matches results against your library, builds and queues the playlist, and logs the outcome. It has no user interface and reports progress through a callback, so it can be driven by any front end.
- `gui.pyw` is the Tkinter desktop app: the main window with its three tabs, a live Now Playing panel, and a log pane fed by the engine. `settings_gui.py` and `discover_gui.py` hold the Settings and Discover tabs.

A thin command-line front end (`Twentyfourbitseven.py`) is also included.

### Blending

Each enabled source returns a ranked list of similar artists. 24bit7 merges them with position weighting: an artist near the top of one list scores well, an artist appearing on several lists scores better. It fetches deeper than it needs and trims the result, so the final list reflects agreement between sources rather than the quirks of any one of them.

With more than one source enabled, the **Require 2+ sources to agree** setting (on by default) drops any artist only one source suggested. Session-based recommenders in particular will offer whatever else their listeners had on that day, and this is what keeps that noise out of the playlist.

### Library matching

Recommendations arrive as names. Names are messy. 24bit7 handles accents (Trüby Trio, with or without the umlaut), inverted sort names ("Isley Brothers, The"), dotted initials (U.N.K.L.E. versus UNKLE), typographic punctuation (MusicBrainz spells alt-J with a Unicode hyphen that looks identical and matches nothing) and version suffixes on track titles before deciding whether you own something. It deliberately matches on names rather than MusicBrainz IDs, because most personal libraries aren't tagged with them.

JRiver's multi-value fields are understood too. An artist tagged `Angus Stone;Dope Lemon` is treated as either name, not a combined one: both are seeded, both match in the library, and a track that surfaces under each is queued once.

### Queueing

New tracks are queued around the current one: everything else in Playing Now is cleared, the current track keeps playing with no gap, and the new playlist follows it. The result is that Playing Now is exactly "what I was listening to plus what 24bit7 chose", which saves cleanly as a JRiver playlist.

If you use more than one JRiver zone, 24bit7 follows whichever zone is active.

### Cache and history

Every response from every source is cached in a local SQLite database with a configurable TTL (30 days by default). Repeat runs on the same seed cost nothing and hit no external service. The same database records every session and every hit and miss, which is what the Discover tab reads.

---

## Sources

| Source | Used for | Key needed | Notes |
|---|---|---|---|
| JRiver MCWS | Now playing, library search, queueing | No (localhost by default) | Requires Media Network enabled in JRiver. |
| Last.fm | Similar artists, top tracks, play counts | Yes (free) | Classic listener-based similarity. |
| ListenBrainz / MusicBrainz | Similar artists, top recordings | Yes (free) | Open data. Choice of algorithm (all-time or recent 75-day). |
| Deezer | Similar artists, top tracks, name verification | No | Also used to verify AI-suggested artists exist. |
| Discogs | Album credits | Yes (free) | Credits display only. |
| Anthropic (Claude) | AI-suggested similar artists, Vibe Playlist | Yes (paid, pennies per run) | Every suggestion is verified against Deezer before it is trusted. |

Enable any combination of similar-artist sources in Settings. One is enough; several are better. Deezer needs no key, so 24bit7 works out of the box.

---

## Setup

### JRiver (both paths)

Enable Media Network in JRiver: Tools > Options > Media Network > **Use Media Network to share this library**. The default port is 52199. 24bit7 talks to JRiver on the same PC by default; if JRiver runs elsewhere, change the host in Settings > Other.

### Path A: download and run (Windows)

1. Download `24bit7-v1.1.0-windows.zip` from the [Releases](../../releases) page.
2. Unzip it anywhere you like and run `24bit7.exe`.
3. Windows will most likely show a blue **"Windows protected your PC"** box the first time, because the exe isn't code-signed. Click **More info**, then **Run anyway**. It only asks once.
4. On first run the app opens on Settings. Add keys for the sources you want; each field has a **?** button with instructions for getting that key. Deezer works with no key at all.

Your keys and history live in two files next to the exe: `.env` (settings and keys) and `24bit7.db` (cache and discoveries). When you upgrade to a new version, copy those two files into the new folder and you'll carry everything over. Settings from older versions are migrated automatically (the single digital store from 1.0.x becomes the first ticked store in 1.1.0).

### Path B: run from source

1. Python 3.10 or newer.
2. `pip install -r requirements.txt` (requests, python-dotenv, anthropic).
3. Run `gui.pyw`. First run behaves as in Path A.
4. Optional: pin to the taskbar with a shortcut targeting `pythonw.exe` and `gui.pyw` as the argument. An icon is included.

All settings live in a `.env` file next to the app. The Settings tab is the intended way to edit it, but it is plain text if you prefer.

---

## What's new in 1.1.0

- **Similar Artists** now asks your top-track sources for each similar artist's top tracks and picks from those, rather than taking whatever the library search returned first. The seed artist gets the same treatment. Every pick is logged, so Discover shows hits and misses per track.
- **Require 2+ sources to agree**: optional filter (on by default) that keeps one source's oddball suggestions out of the playlist.
- **Multi-value artists**: `Artist1;Artist2` tags are treated as either artist, with duplicates removed.
- **Search sites**: tick any number of stores and reference sites in Settings > Search; searching a Discover row opens a tab for each. Bleep and Beatport added.
- **Typographic punctuation** folded to ASCII before matching, fixing false misses on names from MusicBrainz.
- Settings > Playlist grouped by Play mode; the track-selection count can no longer exceed the top-tracks count.
- Discover's session picker is wider and shows the full seed.

## Status

**Solid**: Similar Artists, Artist's Top Tracks, Show Credits, Discover, Settings, cache, mid-album queueing, multi-value artists.

**Newer**: Vibe Playlist. Works well, still learning its limits.

**Removed**: a producer-based playlist mode built on Discogs credits. Discogs credit data is too patchy to be reliable, so it was dropped rather than shipped half-working.

### Roadmap

- Dark theme
- Cache TTL as a Settings control
- Support for players other than JRiver (distant)
- A shared recommendation database built from the hit/miss data (very distant)

---

## Licence

Released under the MIT Licence. See LICENSE. Provided as is, without warranty of any kind, as the licence says.

## Support the project

24bit7 is free and always will be. If it has found you music you'd have missed, you can buy me a coffee (or a Beer!): https://paypal.me/24bit7