# 24bit7

**Smart playlist creation for JRiver Media Center.**

If you host your whole music library locally in JRiver, you get bit-perfect playback and none of the discovery. Streaming services will happily tell you what to play next; JRiver will not. 24bit7 fills that gap. Pick what is playing now, press a button, and it builds a playlist from your own library using recommendation data from Last.fm, ListenBrainz, Deezer and an AI model, then queues it in JRiver without interrupting the current track.

Everything it can't find in your library is logged, so the misses become a shopping list.

The name is a throwback to an old username. Read it as 24-bit and 24/7: audiophile and always on.

---

## What it does

Four actions on the **Play** tab, all seeded from whatever JRiver is playing right now:

| Action | What you get |
|---|---|
| **Similar Artists** | A playlist of tracks by artists similar to the current one, blended from whichever sources you have enabled. |
| **Artist's Top Tracks** | The current artist's most popular tracks that you actually own, in random or popularity order. |
| **Vibe Playlist** | Type a mood or scene (or pick one of three AI suggestions) and get a playlist to match, built only from your library. |
| **Show Credits** | Producer, engineer and other credits for the current album, from Discogs. |

Two supporting tabs:

- **Discover** lists every artist and track a run looked for, whether it was found (hit) or not (miss), filterable by session and searchable across all fields. Each row has a Search button that opens the track in your chosen digital store, so misses are one click from purchase.
- **Settings** holds all keys and preferences. Changes save immediately and the running app picks them up without a restart.

---

## How it works

24bit7 is two Python files:

- `engine.py` does all the work: talks to JRiver, queries the recommendation sources, matches results against your library, builds and queues the playlist, and logs the outcome. It has no user interface and reports progress through a callback, so it can be driven by any front end.
- `gui.pyw` is the Tkinter desktop app: three tabs, a live Now Playing panel, and a log pane fed by the engine.

A thin command-line front end (`Twentyfourbitseven.py`) is also included.

### Blending

Each enabled source returns a ranked list of similar artists. 24bit7 merges them with position weighting: an artist near the top of one list scores well, an artist appearing on several lists scores better. It fetches deeper than it needs and trims the result, so the final list reflects agreement between sources rather than the quirks of any one of them.

### Library matching

Recommendations arrive as names. Names are messy. 24bit7 handles accents (Trüby Trio, with or without the umlaut), inverted sort names ("Isley Brothers, The"), dotted initials (U.N.K.L.E. versus UNKLE) and version suffixes on track titles before deciding whether you own something. It deliberately matches on names rather than MusicBrainz IDs, because most personal libraries aren't tagged with them.

### Queueing

New tracks are queued around the current one: everything else in Playing Now is cleared, the current track keeps playing with no gap, and the new playlist follows it. The result is that Playing Now is exactly "what I was listening to plus what 24bit7 chose", which saves cleanly as a JRiver playlist.

### Cache and history

Every response from every source is cached in a local SQLite database with a configurable TTL (30 days by default). Repeat runs on the same seed cost nothing and hit no external service. The same database records every session and every hit and miss, which is what the Discover tab reads.

---

## Sources

| Source | Used for | Key needed | Notes |
|---|---|---|---|
| JRiver MCWS | Now playing, library search, queueing | No (localhost by default) | Requires MCWS enabled in JRiver. |
| Last.fm | Similar artists, top tracks, play counts | Yes (free) | Classic listener-based similarity. |
| ListenBrainz / MusicBrainz | Similar artists, top recordings | Yes (free) | Open data. Choice of algorithm (all-time or recent 75-day). |
| Deezer | Similar artists, top tracks, name verification | No | Also used to verify AI-suggested artists exist. |
| Discogs | Album credits | Yes (free) | Credits display only. |
| Anthropic (Claude) | AI-suggested similar artists, Vibe Playlist | Yes (paid, pennies per run) | Every suggestion is verified against Deezer before it is trusted. |

Enable any combination of similar-artist sources in Settings. One is enough; several are better.

---

## Setup

1. **JRiver**: enable Media Network (Options > Media Network > Use Media Network to share this library). Note the port (default 52199).
2. **Python** 3.10 or newer. *(confirm)*
3. Install dependencies: `pip install -r requirements.txt` *(confirm package list: requests, python-dotenv, anthropic)*
4. Run `gui.pyw`. On first run, go to Settings > Keys and add the keys for the sources you want. Each field has a **?** button with instructions for getting that key.
5. Optional: pin to the taskbar by creating a shortcut targeting `pythonw.exe` with `gui.pyw` as the argument. An icon is included.

All settings live in a `.env` file next to the app. The Settings tab is the intended way to edit it, but it is plain text if you prefer.

---

## Status

**Solid**: Similar Artists, Artist's Top Tracks, Show Credits, Discover, Settings, cache, mid-album queueing.

**Newer**: Vibe Playlist. Works well, still learning its limits.

**Removed**: a producer-based playlist mode built on Discogs credits. Discogs credit data is too patchy to be reliable, so it was dropped rather than shipped half-working.

### Roadmap

- Packaged build so it runs without a Python install
- Dark theme
- Cache TTL as a Settings control
- Support for players other than JRiver (distant)
- A shared recommendation database built from the hit/miss data (very distant)

---

## Licence

*(placeholder: to be decided before public release)*

## Support the project

*(placeholder: donate link)*
