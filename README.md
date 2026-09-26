# 24bit7

**Smart playlist creation for JRiver Media Center.**

If you host your whole music library locally in JRiver, you get bit-perfect playback and none of the discovery. Streaming services will happily tell you what to play next; JRiver will not. 24bit7 fills that gap, using recommendation data from Last.fm, ListenBrainz, Deezer, YouTube Music and an AI model, matched against the music you already own.

**It works live.** Play any track in JRiver, press a button, and Playing Now is rebuilt around it while the music keeps going. There is nothing to export, no listening history to upload and no second app to keep in sync: whatever is playing right now is the seed. Run it mid-album, mid-track, whenever the mood shifts.

**New in 1.3.0: tracks, not just artists, and your voice.** Similar Tracks builds a playlist of songs like the one playing, not just songs by similar artists, so the mood of the seed carries through. Every playlist can go to any JRiver zone by name, and with an Alexa skill of your own you can ask for one out loud: "Alexa, ask needle drop for tracks like Big Yellow Taxi". 24bit7 can now start with Windows and wait in the tray, so it is there when you ask.

You don't have to own the seed either. Type any artist and track into the Search tab and 24bit7 builds a playlist around it, from your library or, with Output set to YouTube, from YouTube. That second route needs no library, no keys and no JRiver.

Everything it can't find in your library is logged, so the misses become a shopping list.

The name is a throwback to an old username. Read it as 24-bit and 24/7: audiophile and always on.

---

## What it does

Five actions on the **Play** tab. The seed is whichever of the two small tabs is showing when you press a button: **Now Playing** (whatever JRiver is playing right now) or **Search** (any artist and track you type, owned or not).

| Action | What you get |
|---|---|
| **Similar Artists** | A playlist built from artists similar to the seed, blended from whichever sources you have enabled. Each artist (the seed included) contributes a random pick from its top tracks, so the same seed gives a different playlist every run. |
| **Similar Tracks** | A playlist of tracks like the seed track, suggested track by track by Last.fm, ListenBrainz and YouTube Music and blended, so a playlist follows the song rather than the artist's reputation. |
| **Artist's Top Tracks** | The artist's most popular tracks that you actually own, in random or popularity order. From the Search tab it needs only the artist. |
| **Vibe Playlist** | Type a mood or scene (or pick one of three AI suggestions) and get a playlist to match. |
| **Show Credits** | Producer, engineer and other credits for the current album, from Discogs. Not offered from the Search tab, which has no album to look up. |

**Output** sits beside the buttons and decides where the finished playlist goes: **Same zone** (the default: the zone you seeded from), any JRiver zone by name, or **YouTube**, which opens it in your browser as an instant playlist. The **Zone** dropdown on the Now Playing tab picks which zone you seed from.

Two supporting tabs:

- **Discover** lists every track a run looked for, whether it was found (hit) or not (miss), filterable by session and searchable across all fields. Select a row and every site you have ticked has its own button along the bottom: one click, one browser tab. Stores (Bandcamp, Qobuz, Bleep, Beatport and more) and YouTube search for the artist and track; reference sites (Wikipedia, Discogs, AllMusic, MusicBrainz) search for the artist, so you can browse the discography. If your favourite site is missing, add up to three of your own under Settings > Search. Misses are one click from purchase. Tick any rows (or Select all) and **Create YouTube playlist** opens them in your browser as one playlist, so you can hear the misses before you buy.
- **Settings** holds all keys and preferences. Changes save immediately and the running app picks them up without a restart.

---

## How it works

24bit7 is a small set of Python files:

- `engine.py` does all the work: talks to JRiver, queries the recommendation sources, matches results against your library, builds the playlist, sends it to JRiver or YouTube, and logs the outcome. It has no user interface and reports progress through a callback, so it can be driven by any front end.
- `gui.pyw` is the Tkinter desktop app: the main window with its three tabs, the Now Playing and Search panel, and a log pane fed by the engine. `settings_gui.py` and `discover_gui.py` hold the Settings and Discover tabs.
- `tabs.py` draws the tab bars. Windows flattens the standard ones and ignores their colours, so the app draws its own. Every tab colour lives in one palette in that file.

A thin command-line front end (`Twentyfourbitseven.py`) is also included.

### Blending

Each enabled source returns a ranked list of similar artists. 24bit7 merges them with position weighting: an artist near the top of one list scores well, an artist appearing on several lists scores better. It fetches deeper than it needs and trims the result, so the final list reflects agreement between sources rather than the quirks of any one of them.

With more than one source enabled, **Sources that must agree** (Settings > Sources) sets how many of them have to suggest an artist before it is used: Off, 2, 3 and so on, up to the number of sources ticked. Higher means a smoother playlist with fewer wildcards, but less chance of discovering something new. If too few artists clear the bar, 24bit7 relaxes it one step at a time, never below 2, and says so in the log. Session-based recommenders in particular will offer whatever else their listeners had on that day, and this is what keeps that noise out of the playlist.

### Similar Tracks

Similar Artists asks "who sounds like this artist?". Similar Tracks asks "what sounds like this song?", which follows the mood of the seed far more closely: two songs by the same artist lead to different places.

- **Three sources**, each ticked under Settings > Sources: Last.fm (track similarity from listening data), ListenBrainz (similar recordings, with a choice of all-time or roughly the last six months) and YouTube Music (its up next queue). ListenBrainz and YouTube Music need no key.
- **Blended by track.** A track two or three sources agree on ranks above one only a single source suggests. **Sources that must agree** works as it does for artists, and if too few agreed tracks are in your library it is relaxed a step at a time, with a line in the log.
- **Settings > Playlist** sets the length, the most tracks any one artist gets (the seed artist included), whether to **top up from Similar Artists** when the library falls short, and the order: shuffled, or most similar first.

### YouTube Music as a source

The other sources answer "who is similar to this artist?". YouTube Music has no such question, so 24bit7 asks it a different one: "if someone is playing this track, what would you play next?" The answer is a queue of around fifty tracks chosen for the mood of the track, not the reputation of the artist, so two songs by the same artist can lead to different places.

- **Ticked alongside other sources**, the queue is boiled down to its artists in order of appearance, and that list votes in the blend like any other. YouTube's own pick for an artist is guaranteed one of that artist's slots; the rest are drawn at random from their top tracks as usual.
- **Ticked on its own**, Similar Artists plays the queue as is: each track is looked up in your library and the hits are queued in YouTube's order, with no blend and no shuffle. YouTube weaves the seed artist through its queue at about one track in four. A library tips that balance, because you probably own everything by the artist you are playing and only some of the rest, so 24bit7 keeps the seed artist to about a quarter of the finished playlist.

It needs no key and no sign-in. It does rely on an unofficial library, ytmusicapi, which imitates the YouTube Music website. When YouTube changes something it can break until that library catches up.

### Output: a JRiver zone or YouTube

With Output set to YouTube the playlist is built exactly as before. Then each track's video is looked up and the whole list opens in your browser as an instant playlist: no sign-in, nothing saved to an account, and up to 50 videos, which is the most YouTube allows in one playlist link (**YouTube playlist length** in Settings > Other sets the number). JRiver isn't touched. There is no library check, so nothing is a miss: every track found is logged to Discover as a hit. A video is only accepted if the artist matches, because a cover is worse than a gap.

Be clear about what this is for. YouTube audio is lossy, and 24bit7 exists because of a library of music worth owning. YouTube output is the way to hear something before you buy it, or to build a playlist for someone who doesn't own any of it.

### Library matching

Recommendations arrive as names. Names are messy. 24bit7 handles accents (Trüby Trio, with or without the umlaut), typographic punctuation (MusicBrainz spells alt-J with a Unicode hyphen that looks identical and matches nothing) and version suffixes on track titles before deciding whether you own something. It deliberately matches on names rather than MusicBrainz IDs, because most personal libraries aren't tagged with them.

Since 1.3.0 the whole library is also held in memory when 24bit7 starts, about a second's work for a library of well over 100,000 tracks, and refreshed in the background. Similar Tracks and voice commands match against it instantly, and it finds compilation copies of a track, including libraries that tag compilations as "Artist - Title" under the series name.

Two cases earned their own rules in 1.2.0:

- **Inverted sort names.** A library tag of "XX, The" is flipped to "The XX" before any source sees it. A source handed a name it doesn't recognise will guess at the nearest popular artist, and its suggestions then describe the wrong act entirely.
- **Dotted initials.** Sources say UNKLE; the library says U.N.K.L.E. Every spelling is searched and the results are merged, because a search for the undotted name finds remix credits and compilation titles but not the artist's own tracks.

JRiver's multi-value fields are understood too. An artist tagged `Angus Stone;Dope Lemon` is treated as either name, not a combined one: both are seeded, both match in the library, and a track that surfaces under each is queued once.

### Queueing

New tracks are queued around the current one: everything else in Playing Now is cleared, the current track keeps playing with no gap, and the new playlist follows it. The result is that Playing Now is exactly "what I was listening to plus what 24bit7 chose", which saves cleanly as a JRiver playlist.

A playlist built from the Search tab follows the same rule: whatever is playing is never interrupted. Only if JRiver is stopped does the new playlist start by itself, opening with the track you searched for if you own it.

With more than one JRiver zone, the finished playlist goes to the zone Output names. A stopped zone starts playing it straight away. A busy zone keeps its current track and queues the playlist after it. If you seed from one zone and send to another, the seed track opens the playlist on the new zone. Settings > Other sets which zones appear, which zone Now Playing opens on, and whether it follows JRiver's active zone. A DLNA speaker such as a Sonos works as a zone once DLNA Controller is ticked in JRiver.

### Voice control (optional, advanced)

24bit7 can take commands from an Alexa skill you host yourself. This is not a one-click setup: you need your own Amazon developer account and Alexa-hosted skill, a Tailscale Funnel (or similar) to let Amazon reach 24bit7 on your PC, and 24bit7 left running, which Start with Windows and the tray take care of. The skill's code and interaction model are in the `alexa` folder of this repository, and a full step-by-step setup guide is on the roadmap. Settings > Voice holds the key the skill sends and assigns each Alexa speaker to a zone.

Once it is set up, each speaker plays to its own zone:

| Say | You get |
|---|---|
| "songs by *artist*" | Artist's Top Tracks |
| "music like *artist*" | Similar Artists, seeded from the artist's most popular track |
| "tracks like *song*" (or "*song* by *artist*") | Similar Tracks |
| "genre *anything*" | Vibe Playlist |
| "album *name*", "song *title*", "playlist *name*" | Plays it now, replacing what's playing |
| "shuffle songs by *artist*" | Every track by the artist in your library, shuffled |

When several albums or songs share a title, Alexa asks which artist, and you answer "by *artist*". No command starts with "play", because Alexa tends to hand anything starting "play" to a music service instead of the skill. The skill name is up to you; the one in this repository is "needle drop", chosen because Alexa kept mishearing the first one.

### Start with Windows and the tray

Settings > Other > Windows has three ticks. **Start with Windows** launches 24bit7 when you sign in (a per-user startup entry, so no admin rights). **Start in the tray** keeps the window hidden when Windows starts it. **Close to tray** makes the window's close button hide 24bit7 rather than quit, so voice keeps listening; quit from the tray icon instead. For voice after a restart, set JRiver Media Center or Media Server to start with Windows as well. Media Server on its own is enough for everything 24bit7 does.

### Speed

A first run on a new seed has to ask every source about every artist. 24bit7 asks them all at once, within each service's limits: a few artists at a time for Last.fm and Deezer, and a single lane for MusicBrainz, which asks for no more than one lookup a second. That rule makes ListenBrainz the slowest source on a first run, because every artist needs a MusicBrainz ID before ListenBrainz can be asked about them. The IDs are remembered for good, so each artist only ever costs that second once. With YouTube output, the video lookups run several at a time as well.

On the development PC, a first run of twenty similar artists with YouTube output went from about 90 seconds to 38 with ListenBrainz ticked, and from 38 seconds to 17 without it.

### Cache and history

Every response from every source is cached in a local SQLite database with a configurable TTL (30 days by default). Repeat runs on the same seed cost nothing and hit no external service. The same database records every session and every hit and miss, which is what the Discover tab reads.

---

## Sources

| Source | Used for | Key needed | Notes |
|---|---|---|---|
| JRiver MCWS | Now playing, library search, queueing | No (localhost by default) | Requires Media Network enabled in JRiver. Not needed for Search with YouTube output. |
| Last.fm | Similar artists, similar tracks, top tracks, play counts | Yes (free) | Classic listener-based similarity. |
| ListenBrainz / MusicBrainz | Similar artists, similar tracks, top recordings | Only for top recordings (free) | Open data. Choice of algorithm for artists (all-time or recent 75-day) and for tracks (all-time or roughly six months). The slowest artist source on a first run. |
| Deezer | Similar artists, top tracks, name verification | No | Also used to verify AI-suggested artists exist. |
| YouTube Music | Similar artists and similar tracks from the up next queue, playlist output, Discover playlists | No | No sign-in. Uses the unofficial ytmusicapi library, so it may break now and then. |
| Discogs | Album credits | Yes (free) | Credits display only. |
| Anthropic (Claude) | AI-suggested similar artists, Vibe Playlist | Yes (paid, pennies per run) | Every suggestion is verified against Deezer before it is trusted. |

Enable any combination of similar-artist sources in Settings. One is enough; several are better. Deezer and YouTube Music need no keys, so 24bit7 works out of the box.

---

## Setup

### JRiver

Enable Media Network in JRiver: Tools > Options > Media Network > **Use Media Network to share this library**. The default port is 52199. 24bit7 talks to JRiver on the same PC by default; if JRiver runs elsewhere, change the host in Settings > Other.

JRiver is only needed for the Now Playing seed and for JRiver output. The Search tab with Output set to YouTube works without it.

### Path A: download and run (Windows)

1. Download `24bit7-v1.3.0-windows.zip` from the [Releases](../../releases) page.
2. Unzip it anywhere you like and run `24bit7.exe`.
3. Windows will most likely show a blue **"Windows protected your PC"** box the first time, because the exe isn't code-signed. Click **More info**, then **Run anyway**. It only asks once.
4. On first run the app opens on Settings. Add keys for the sources you want; each field has a **?** button with instructions for getting that key. Deezer and YouTube Music work with no key at all, and they are the two sources a fresh install has ticked.

Your keys and history live in two files next to the exe: `.env` (settings and keys) and `24bit7.db` (cache and discoveries). When you upgrade to a new version, copy those two files into the new folder and you'll carry everything over. Settings from older versions are migrated automatically: the single digital store from 1.0.x becomes the first ticked store, and the on/off agreement setting from 1.1.0 becomes 2 or Off.

### Path B: run from source

1. Python 3.10 or newer.
2. `pip install -r requirements.txt` (requests, python-dotenv, anthropic, ytmusicapi, and pystray with Pillow for the tray icon).
3. Run `gui.pyw`. First run behaves as in Path A.
4. Optional: pin to the taskbar with a shortcut targeting `pythonw.exe` and `gui.pyw` as the argument. An icon is included.

All settings live in a `.env` file next to the app. The Settings tab is the intended way to edit it, but it is plain text if you prefer.

---

## What's new in 1.3.0

- **Similar Tracks.** A new Play button that builds a playlist of tracks like the seed track, from Last.fm, ListenBrainz and YouTube Music, with its own sources, agreement number and playlist settings.
- **Zones.** Output lists every JRiver zone by name, Now Playing has its own Zone dropdown, and Settings > Other sets which zones show, the default zone and whether to follow JRiver's active zone.
- **Voice control.** An optional, self-hosted Alexa skill for top tracks, similar artists, similar tracks, genres, albums, songs, playlists and shuffles, each speaker playing to its own zone. Advanced setup; see Voice control above.
- **Discover to YouTube.** Tick rows, or Select all, and Create YouTube playlist opens them as one playlist.
- **Start with Windows and the tray.** Start with Windows, start hidden in the tray, and close to the tray, so 24bit7 is always there for voice.
- **Settings.** Every Settings page scrolls. Sources is split into Similar Artists, Similar Tracks and Artist's Top Tracks, each with its own ListenBrainz algorithm where it applies.
- **Library in memory.** Matching for Similar Tracks and voice runs against the whole library held in memory, and finds compilation copies too.

### Earlier: 1.2.1

- **Show Credits works again.** Its function had gone missing from the engine before the first public release, so the button failed in 1.0.1, 1.1.0 and 1.2.0.
- **Missing keys are named in the log.** A feature that needs a key now says which one and where to add it. Before, it failed quietly or blamed the service. A ticked source with no key is named once and then skipped, and Settings > Sources marks it "(no key yet)".
- **A fresh install starts on sources that work.** Deezer and YouTube Music are ticked, since neither needs a key, with the agreement filter off. Existing settings are not touched.

### Earlier: 1.2.0

- **YouTube Music as a fifth source.** Seeded by the track, not just the artist, so it follows the mood. Ticked with other sources it votes in the blend and its own pick for an artist is guaranteed a slot. Ticked on its own it plays its up next queue as is, with the seed artist kept to about a quarter of the playlist.
- **Search tab.** Build a playlist from any artist and track, owned or not. The searched track opens the playlist if you own it, and lands in Discover as a miss if you don't. Whatever JRiver is playing is never interrupted.
- **Output: JRiver or YouTube.** Send any playlist to YouTube as an instant playlist of up to 50 videos, with no sign-in. Works without a library, without keys and without JRiver.
- **Sources that must agree.** The on/off agreement filter is now a number (Off, 2, 3 and up), limited to the sources you have ticked, and it relaxes itself when too few artists qualify.
- **Discover.** One button per ticked site instead of a single Search that opened every site at once. YouTube added as a search option, plus three custom site rows under Settings > Search. Double-clicking a row no longer opens anything.
- **Faster first runs.** Top tracks are fetched for every artist at once, MusicBrainz IDs are remembered for good, and YouTube lookups run several at a time.
- **Matching fixes.** "Name, The" artists are flipped for every source, which fixes Deezer describing the wrong act. Dotted acts such as U.N.K.L.E. are found when a source drops the dots.
- **Look.** Tabs drawn by the app so they read as tabs, the track title in the logo blue, and the donate link moved to the top right of the tab row.

### Earlier: 1.1.0

- **Similar Artists** asks your top-track sources for each similar artist's top tracks and picks from those, rather than taking whatever the library search returned first. The seed artist gets the same treatment. Every pick is logged, so Discover shows hits and misses per track.
- **Agreement filter**: optional filter (on by default) that keeps one source's oddball suggestions out of the playlist. It became the Sources that must agree number in 1.2.0.
- **Multi-value artists**: `Artist1;Artist2` tags are treated as either artist, with duplicates removed.
- **Search sites**: tick any number of stores and reference sites in Settings > Search. Bleep and Beatport added.
- **Typographic punctuation** folded to ASCII before matching, fixing false misses on names from MusicBrainz.
- Settings > Playlist grouped by Play mode; the track-selection count can no longer exceed the top-tracks count.
- Discover's session picker is wider and shows the full seed.

## Status

**Solid**: Similar Artists, Artist's Top Tracks, Show Credits, Discover, Settings, cache, mid-album queueing, multi-value artists, the agreement number.

**Newer**: Similar Tracks, zones, voice control, Discover's YouTube playlists, the tray, the Search tab, YouTube Music as a source and YouTube output. All are in daily use on the development PC. Voice control is the least plug-and-play part, as its setup says, and the YouTube parts rest on an unofficial library, so expect the occasional breakage. Vibe Playlist works well and is still learning its limits.

**Removed**: a producer-based playlist mode built on Discogs credits. Discogs credit data is too patchy to be reliable, so it was dropped rather than shipped half-working.

### Roadmap

- An optional AI sanity check that removes obvious misfits from a playlist before it is queued
- A step-by-step setup guide for voice control
- Remembering Deezer artist IDs, for quicker first runs
- Dark theme (the tab colours now live in one palette, which is the first step)
- More players and outputs beyond JRiver and YouTube (distant)
- A shared recommendation database built from the hit/miss data (very distant)

---

## Licence

Released under the MIT Licence. See LICENSE. Provided as is, without warranty of any kind, as the licence says.

## Support the project

24bit7 is free and always will be. If it has found you music you'd have missed, you can buy me a coffee (or a Beer!): https://paypal.me/24bit7