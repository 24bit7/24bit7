# 24bit7

**Perfect playlists and music discovery for JRiver Media Center.**

If you host your whole music library locally in JRiver, you get bit-perfect playback and none of the discovery. Streaming services will happily tell you what to play next; JRiver will not. 24bit7 fills that gap, using recommendation data from Last.fm, ListenBrainz, Deezer, YouTube Music and an AI model, matched against the music you already own.

[![Watch the 24bit7 demo](https://img.youtube.com/vi/_7KZt4paaGY/hqdefault.jpg)](https://youtu.be/_7KZt4paaGY)

**It works live.** Play any track in JRiver, press a button, and Playing Now is rebuilt around it while the music keeps going. There is nothing to export, no listening history to upload and no second app to keep in sync: whatever is playing right now is the seed. Run it mid-album, mid-track, whenever the mood shifts.

**New in 1.9.0: steadier playlists without more AI.** The AI Moderator now has three levels, from removing only clear clashes to keeping only tracks close to the seed, and Drift can top a playlist up from sources of its own. Vibe Playlist is now AI Playlist, starting with More tracks like the song that's playing, and bracketed song titles match your library however they're tagged.

You don't have to own the seed either. Type any artist and track into the Search tab and 24bit7 builds a playlist around it, from your library or, with Output set to YouTube, from YouTube. That second route needs no library, no keys and no JRiver.

Everything it can't find in your library is logged, so the misses become a shopping list.

The name is a throwback to an old username. Read it as 24-bit and 24/7: audiophile and always on.

The **[user manual](docs/MANUAL.md)** explains every part of the app, page by page. The Windows download includes it as a PDF, opened from Settings > About.

---

## What it does

Four playlist buttons on the **Play** tab, plus **More Options**. The seed is whichever of the two small tabs is showing when you press a button: **Now Playing** (whatever JRiver is playing right now) or **Search** (any artist and track you type, owned or not).

| Action | What you get |
|---|---|
| **Similar Artists** | A playlist built from artists similar to the seed, blended from whichever sources you have enabled. Each artist (the seed included) contributes a random pick from its top tracks, so the same seed gives a different playlist every run. |
| **Similar Tracks** | A playlist of tracks like the seed track, suggested track by track by Last.fm, ListenBrainz, YouTube Music and, if you tick it, AI, and blended, so a playlist follows the song rather than the artist's reputation. |
| **Artist's Top Tracks** | The artist's most popular tracks that you actually own, in random or popularity order. From the Search tab it needs only the artist. |
| **AI Playlist** | Type a mood or scene, pick More tracks like the song that's playing, or pick one of three AI suggestions, and the AI picks a playlist to match from your library. |
| **More Options** | Opens a row underneath with the **AI Moderator**, **Drift** and **Non-stop** (both change Settings > Playlist for every Play option at once), **Show Credits** (producer, engineer and other credits for the current album, from Discogs; not offered from the Search tab, which has no album to look up) and **+ Add Playlist** (see below). It remembers whether it's open. |

**Output** sits beside the buttons and decides where the finished playlist goes: **Same zone** (the default: the zone you seeded from), any JRiver zone by name, or **YouTube**, which opens it in your browser as an instant playlist. The **Zone** dropdown on the Now Playing tab picks which zone you seed from.

Two supporting tabs:

- **Discover** lists every track a run looked for, whether it was found (hit) or not (miss), filterable by session and searchable across all fields. Select a row and every site you have ticked has its own button along the bottom: one click, one browser tab. Stores (Bandcamp, Qobuz, Bleep, Beatport and more) and YouTube search for the artist and track; reference sites (Wikipedia, Discogs, AllMusic, MusicBrainz) search for the artist, so you can browse the discography. If your favourite site is missing, add up to three of your own under Settings > Search. Misses are one click from purchase. **Label** finds who released the selected track and opens the label on Bandcamp (see below). Tick any rows (or Select all) and **Create YouTube playlist** opens them in your browser as one playlist, so you can hear the misses before you buy. **Clear all** empties the history, and **Clear selected** removes just the ticked rows; both ask first.
- **Settings** holds all keys and preferences, in boxed sections, with each setting's explanation behind a small **?** beside it. Sources and Playlist have a tab for each Play option (Similar Artists, Similar Tracks, Artist's Top Tracks, AI Playlist), so each can be set up its own way. Changes save immediately and the running app picks them up without a restart.

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

- **Four sources**, each ticked under Settings > Sources: Last.fm (track similarity from listening data), ListenBrainz (similar recordings, with a choice of all-time or roughly the last six months), YouTube Music (its up next queue) and, optionally, AI (Claude's picks, using a little Anthropic credit per build). ListenBrainz and YouTube Music need no key.
- **Blended by track.** A track two or three sources agree on ranks above one only a single source suggests. **Sources that must agree** works as it does for artists, and if too few agreed tracks are in your library it is relaxed a step at a time, with a line in the log.
- **Settings > Playlist > Similar Tracks** sets the length, the most tracks any one artist gets (the seed artist included), the order (shuffled, or most similar first) and Drift, for when the library falls short.

### Fast start

With nothing playing on the output zone, a playlist used to arrive all at once when it was finished. Now the first track found starts straight away and the rest of the playlist follows it into Playing Now as it is built, so music starts within a second or two. It applies to searches, voice commands and AI Playlists, with JRiver output (a YouTube link is made once, so it still waits for the full list). Artist's Top Tracks uses it in popular order, starting on the most popular track you own. "Shuffle songs by" opens on a random pick from the artist's top five. There is no setting: when music is already playing, there's nothing to wait for anyway.

### Drift

Similar Artists, Similar Tracks and AI Playlist each have a target length, and a library doesn't always have enough to reach it. With **Drift** ticked (on each Play option's tab under Settings > Playlist, off by default), 24bit7 searches again from what it has already found: each round seeds from the three best finds not used yet, most agreed on first, and looks up either their similar tracks or their similar artists, whichever **Drift using** is set to. **Rounds** sets how many times it tries, from 1 to 6. More rounds fill more gaps but wander further from where you started, which is why it stops at 6 regardless. With JRiver output the first pass is queued straight away and each round is added to the end as it is found, so the music never waits for Drift.

**Drift sources** sets where those rounds look. **Same as Settings > Sources**, the default, uses the sources you picked for that Play option. **Custom Sources** gives Drift its own source ticks and its own **Sources that must agree**, so the first pass can stay steady and the top-up can be more adventurous: Last.fm alone for Similar Artists, say, with Deezer and ListenBrainz agreeing on 2 to fill the gaps. The ticks follow Drift using, similar-artist or similar-track sources, and each set is kept separately. The log names the sources each round used.

In an AI Playlist, Drift using similar artists or similar tracks tops up from your music sources, not the AI, and the settings and log say so: "Similar artists (no AI)". It can also drift using **AI**: each round asks the AI again with your description, telling it what has already been found or tried so it suggests something new. That uses a little Anthropic credit per round, so it's never the default; pick it if you want it.

### AI Moderator

Most playlists are right apart from one track: the stadium anthem in the middle of a run of acoustic songs. The AI Moderator is an optional check that catches it. When it's on, each playlist (and each Drift round) goes to Claude Haiku once, with the seed and the list of tracks, and it removes the ones that would jolt a listener out of the mood. It judges tone, energy and mood only, and genre is never a reason on its own: a folk song and an electronic track can sit together, and two songs in the same genre can clash. It keeps anything it doesn't know well enough to judge, and logs each removal with its reason. How hard it looks is up to you:

- **Relaxed** removes only clear clashes, at most a fifth of the tracks.
- **Balanced** removes anything that noticeably shifts the tone, energy or mood away from the seed, at most two fifths.
- **Strict** keeps only tracks that sit close to the seed, however many that leaves. Drift can top a short playlist up.

It's **Off** by default. A few extra tracks are found up front, more at the stricter levels, so the ones it removes are replaced. The fast start track is never checked, and Artist's Top Tracks isn't moderated, since it's one artist.

It needs an Anthropic key and uses a little credit each time, a fraction of a penny per playlist; the first time you switch it on, 24bit7 says so. Without a key the option is greyed out. If the check fails or the credit runs out, the playlist builds as normal and the log says why. Pick the level as you go from **More Options** on the Play tab. It applies to Similar Artists and Similar Tracks. An AI Playlist's own picks are never checked, because the AI has already picked every track against your description, but its Drift section has **AI Moderator on Drift tracks** for what Drift adds from your sources. It's greyed out unless Drift is on and isn't using the AI. A voice device with settings of its own keeps its own choice under Settings > Sources; one copying Windows (Main) follows the Play tab (see Voice Commands below).

### The console

The console on the Play tab shows what each build did, written the same way every time: the time and what was built on the first line, the steps beneath it, `Note:` (amber) for something to know, `Problem:` (red) for something that went wrong, AI lines in magenta, and one closing line: `Done: 30 tracks queued in Speakers, 62 not in library, 14 s.` **Simple** hides the debug lines and **Advanced** shows them; they're always recorded, so switching works on the build already there.

A small green arrow at the top of the console opens its tabs: **All**, **Main Window**, one per Alexa device, and **Log**. Each tab shows its own latest build, so a voice command in the kitchen doesn't wipe a build you're reading at the PC, and a command that fails shows under its device with what Alexa said. The **Log** lists the last 50 builds from each source, newest first, with the zone, Play option, sources, tracks queued and missed, what the AI Moderator did and any problems. Non-stop top-ups are numbered in their chain (001, 002, 003). Double-click a row, or click **Load to Console**, to open that build, then Copy, Query or Export it.

### Console Query

When a playlist comes out short or odd, you can ask why. Tick **Enable Console Query** in Settings > Other (it's off by default, and asks before it switches on), then click into the console and press **Query**. Type a question under the console and press Enter: "Why was this track included?", "Why was the playlist so short?", "What did the AI Moderator remove?". The answer appears in the console in magenta, and the box stays open for follow-ups.

Claude Haiku is sent what's in the console, your settings with every key, token, password and user name left out, what's playing, and 24bit7's own code and README, so it knows the rules and the names of the settings. It explains what most likely happened and suggests up to three changes, named as they appear in Settings. Plain music questions, such as which album a song is from, are answered from general knowledge. Running from source, it reads the code in the folder; the packaged app downloads it once from GitHub, for the version you're running. Query reads the build on screen, which can be any of the last 50 opened from the Log; switching the console to Advanced first sends the debug lines too. It costs a few pence for the first question and much less for follow-ups within a few minutes. Clear empties the console, and with it what Claude can see.

### Reporting a problem

Do the thing that went wrong (or open the build from the console's Log), then click into the console and press **Export to Log**; with the console's tabs open, it's at the top right. 24bit7 writes a dated file to the `logs` folder beside it (version, Python, Windows and JRiver versions, library size, your settings with every key and password hidden, and the build on screen, debug lines included) and opens the folder with the file selected. Attach that file, or paste it, when you report the problem. Keys never appear in it.

### Hidden tracks

Some albums end on a track that runs on after a long silence into a hidden bonus track, which feels completely out of place in a playlist. The sources can't help, because they report the long album version too. So the Hidden Tracks section on each Play option's tab under Settings > Playlist skips the last track on an album when it runs longer than a set number of minutes, 6 by default, and each Play option can set its own. Albums, songs and playlists you ask for by name always play in full.

### Skip tracks played recently

Each Play option's tab under Settings > Playlist can leave out anything JRiver has played in the last so many days, 1 by default, so a favourite doesn't come round again the same evening. It reads JRiver's Last Played date from the library 24bit7 holds in memory, so it costs nothing. The seed track is never left out, and Drift, if it's on, fills the gaps. It's off by default.

### Non-stop

A playlist used to end. With **Non-stop** ticked on a Play option's tab under Settings > Playlist, 24bit7 watches the zone, and when the last track of a playlist it built starts playing, it adds more to the end. Each Play option sets how it carries on:

- **Similar Artists and Similar Tracks** top up using similar artists or similar tracks (**Play using**), seeded from the **last track**, so the music wanders as the evening goes on, or the **2nd track**, the first pick after the original seed, so it stays close to how it started.
- **Artist's Top Tracks** can first play the rest of the artist's songs in your library, shuffled (up to 20 by default, or unlimited), then carries on from their most popular track.
- **AI Playlist** can ask the AI for more (More from the AI), or carry on with similar artists or similar tracks, which use no credit.

A playlist keeps following the settings of the option it started as, all evening, and every top-up passes through your filters and skips anything the zone already had. Only playlists 24bit7 sent are topped up: an album or playlist you start in JRiver yourself ends as normal. Each last track triggers one top-up, so a paused or repeated track can't set off a pile of builds.

### Filters

Settings > Filters holds a library of named filters that narrow the playlists 24bit7 builds, their Drift rounds and non-stop top-ups. Each filter has:

- **Applies on:** All devices, Windows (Main) (the Play tab, and any speaker without settings of its own), or a speaker with its own settings. Where several filters apply, a track must pass them all.
- **Only pick from:** a JRiver playlist or smartlist, so only its tracks can be used. Set up any filtering you like in JRiver's smartlist editor and 24bit7 respects it.
- **Rules**, matching all or any: Rating (any of 0 to 5, where 0 is unrated), Year, Last played, Play count, Date imported, Genre, Artist, Album, Duration, File type, Bit depth, Sample rate and File location. "Sample rate at most 48 kHz" saves JRiver converting on the fly for a Sonos.

A track with no value for a field (no year, say) passes that rule, and the log counts them. The seed track is never filtered out. Each build's log names the filters that applied and how many tracks they left out. Albums, songs, shuffles and JRiver playlists asked for by voice play as asked.

### Keyboard shortcuts

Settings > Other > Keyboard Shortcuts gives Similar Tracks, Similar Artists, Artist's Top Tracks and Shuffle Songs by Artist a key each. They work anywhere in Windows, even with 24bit7 in the tray, so a remote that sends key presses (a Flirc, a Harmony, a phone app) can start a playlist from the sofa. Nothing is assigned until you choose; letters and numbers need Ctrl, Alt, Shift or Win, and F-keys and media keys can be used on their own. If another program already owns a combination, 24bit7 says so beside it.

Shortcuts act on one zone (**Shortcuts apply to which zone**: the zone shown in Now Playing, or one you pick) and seed from its current track. If its Playing Now is empty, they seed from the last track JRiver played, and so do the Play tab buttons.

### Label

Buying from a label's Bandcamp page supports the artist and the people who put the record out. The **Label** button in Discover finds who released the selected track: MusicBrainz first (the track's earliest official album, then single or EP, skipping compilations), then Discogs if you have a token. It opens the label's own Bandcamp page when MusicBrainz links one, or a Bandcamp search for the label otherwise. A self-released track opens the artist on Bandcamp, and if no source knows the label, it falls back to a Google search. Each answer is cached, so a second click is instant.

### YouTube Music as a source

The other sources answer "who is similar to this artist?". YouTube Music has no such question, so 24bit7 asks it a different one: "if someone is playing this track, what would you play next?" The answer is a queue of around fifty tracks chosen for the mood of the track, not the reputation of the artist, so two songs by the same artist can lead to different places.

- **Ticked alongside other sources**, the queue is boiled down to its artists in order of appearance, and that list votes in the blend like any other. YouTube's own pick for an artist joins the pool of their top tracks and is drawn at random with the rest.
- **Ticked on its own**, Similar Artists plays the queue as is: each track is looked up in your library and the hits are queued in YouTube's order, with no blend and no shuffle. YouTube weaves the seed artist through its queue at about one track in four. A library tips that balance, because you probably own everything by the artist you are playing and only some of the rest, so 24bit7 keeps the seed artist to about a quarter of the finished playlist.

It needs no key and no sign-in. It does rely on an unofficial library, ytmusicapi, which imitates the YouTube Music website. When YouTube changes something it can break until that library catches up.

### Output: a JRiver zone or YouTube

With Output set to YouTube the playlist is built exactly as before. Then each track's video is looked up and the whole list opens in your browser as an instant playlist: no sign-in, nothing saved to an account, and up to 50 videos, which is the most YouTube allows in one playlist link (**YouTube playlist length** in Settings > Other sets the number). Tick **Prefer official music videos** under Settings > Other to play the artist's own video where YouTube has one; videos can run longer than the song, and a few may not play in every country. JRiver isn't touched. There is no library check, so nothing is a miss: every track found is logged to Discover as a hit. A video is only accepted if the artist matches, because a cover is worse than a gap.

Be clear about what this is for. YouTube audio is lossy, and 24bit7 exists because of a library of music worth owning. YouTube output is the way to hear something before you buy it, or to build a playlist for someone who doesn't own any of it.

### Library matching

Recommendations arrive as names. Names are messy. 24bit7 handles accents (Trüby Trio, with or without the umlaut), typographic punctuation (MusicBrainz spells alt-J with a Unicode hyphen that looks identical and matches nothing) and version suffixes on track titles (including soundtrack credits such as "- From 'Casino Royale' Soundtrack"), and it treats "&" and "and" as the same word before deciding whether you own something. It deliberately matches on names rather than MusicBrainz IDs, because most personal libraries aren't tagged with them.

Since 1.3.0 the whole library is also held in memory when 24bit7 starts, about a second's work for a library of well over 100,000 tracks, and refreshed in the background. Similar Tracks and voice commands match against it instantly, and it finds compilation copies of a track, including libraries that tag compilations as "Artist - Title" under the series name.

Two cases earned their own rules in 1.2.0:

- **Inverted sort names.** A library tag of "XX, The" is flipped to "The XX" before any source sees it. A source handed a name it doesn't recognise will guess at the nearest popular artist, and its suggestions then describe the wrong act entirely.
- **Dotted initials.** Sources say UNKLE; the library says U.N.K.L.E. Every spelling is searched and the results are merged, because a search for the undotted name finds remix credits and compilation titles but not the artist's own tracks.

Bracketed words in a title count either way. "Long Cool Woman (in a Black Dress)" finds a library tagged "Long Cool Woman in a Black Dress", and the reverse, while brackets holding a version tag or a credit, such as (Remastered), (Live) or (feat. ...), are still ignored. On the development library, 4,196 of 4,390 such titles used to miss whenever a source wrote them the other way.

JRiver's multi-value fields are understood too. An artist tagged `Angus Stone;Dope Lemon` is treated as either name, not a combined one: both are seeded, both match in the library, and a track that surfaces under each is queued once.

Band credits are matched both ways round. A source's "The Jimi Hendrix Experience" finds a library tagged "Jimi Hendrix", and the reverse, when the title matches too. Only three shapes count: "The" plus the name plus a band word (The Jimi Hendrix Experience), the name followed by and, & or + (Bob Marley & The Wailers matches Bob Marley), and the name after one of those at the end (it also matches The Wailers). "Of" never counts, so Eagles of Death Metal won't match Eagles, and nor does a bare suffix such as Boston Pops. "At most N per artist" counts the artist as tagged in your library, so both credits share one allowance. Each such match is logged as "Matched on band name".

### Queueing

New tracks are queued around the current one: everything else in Playing Now is cleared, the current track keeps playing with no gap, and the new playlist follows it. The result is that Playing Now is exactly "what I was listening to plus what 24bit7 chose", which saves cleanly as a JRiver playlist.

A playlist built from the Search tab follows the same rule: whatever is playing is never interrupted. Only if JRiver is stopped does the new playlist start by itself, opening with the track you searched for if you own it, and with fast start it begins playing before the rest is found.

With more than one JRiver zone, the finished playlist goes to the zone Output names. A stopped zone starts playing it straight away. A busy zone keeps its current track and queues the playlist after it. If you seed from one zone and send to another, the seed track opens the playlist on the new zone. Settings > Other sets which zones appear, which zone Now Playing opens on, and whether it follows JRiver's active zone. A DLNA speaker such as a Sonos works as a zone once DLNA Controller is ticked in JRiver.

### Adding your own playlists

Open **More Options** and press **+ Add Playlist** to join a JRiver playlist or smartlist to the next build from the Play tab. Each row has a handle to drag it up or down, the playlist, and how it joins:

- **Add before**: its tracks play first, in the playlist's own order.
- **Add after**: its tracks follow 24bit7's, in their own order.
- **Mix**: its tracks are woven through 24bit7's. **Spaced evenly** spreads both lists over the whole playlist so they finish together; with equal lengths that's one of each in turn. **Mixed randomly** scatters them.

Rows play in the order they're listed, so two Add after playlists follow one another, top to bottom. The picker shows the playlists you use most first, then the rest A to Z, with a search box.

The playlists come through exactly as JRiver gives them, so a smartlist's own rules (ratings, play history and so on) decide what's in it. 24bit7's filters, recent-play skip and hidden-track check leave them alone. The only thing it drops is a song already in its own picks, so nothing plays twice. With a playlist added, Drift finishes before anything is sent, so Add after really does come last. With Add before and a stopped zone, fast start plays that playlist's first track.

If nothing matches your library, the added playlists still play on their own, so a build never leaves you with silence.

Added playlists are for the Play tab only, and only with JRiver output. Voice, keyboard shortcuts and non-stop don't use them, and YouTube output leaves them out with a note in the log. The rows are remembered between runs, and a line under them says what the next build will do.

### Run after building

Each Play option under Settings > Playlist can run a file of your choice once its playlist is in JRiver: a .bat, an .exe, or a PowerShell or Python script. It runs in the background after every build, whether or not anything matched, and isn't told anything about the playlist, so it can do whatever you like. Device tabs have their own, so a voice build can run something different. Non-stop top-ups don't run it.

### Voice Commands (optional, advanced)

24bit7 can take commands from an Alexa skill you host yourself. This is not a one-click setup: you need your own Amazon developer account and Alexa-hosted skill, a Tailscale Funnel (or similar) to let Amazon reach 24bit7 on your PC, and 24bit7 left running, which Start with Windows and the tray take care of. The skill's code and interaction model are in the `alexa` folder of this repository. The user manual's **[Voice Commands](docs/MANUAL.md#voice-commands)** chapter explains what it does, and **[Setting up the Alexa skill](docs/MANUAL.md#setting-up-the-alexa-skill)** takes you through every step. Both are linked from Settings > Voice Commands and Settings > About too.

Settings > Voice Commands holds the key the skill sends and assigns each Alexa device to a zone. Tick **Own settings** for a device and it gets its own tab under Settings > Sources, Playlist and JRiver Playlists, copying the Windows app's settings until you untick Copy Windows (Main) and change them, and it can be named in a filter. Two speakers can then run two sets of settings side by side, for A/B testing or for different people.

Once it is set up, each device plays to its own zone:

| Say | You get |
|---|---|
| "songs by *artist*" | Artist's Top Tracks |
| "music like *artist*" | Similar Artists, seeded from the artist's most popular track |
| "tracks like *song*" (or "*song* by *artist*") | Similar Tracks |
| "genre *anything*" | AI Playlist |
| "album *name*", "song *title*" | Plays it now, replacing what's playing |
| "playlist *name*" | Plays one of your JRiver playlists or smartlists now, with its settings from Settings > JRiver Playlists |
| "shuffle songs by *artist*" | Every track by the artist in your library, shuffled |
| "skip", "next" | The next track in that device's zone |
| "who is this", "what's playing" | Alexa says the track, artist and album playing there |
| "more like this" | Similar Tracks from what's playing, queued after the current track |

When a command is accepted, Alexa plays a short tone rather than talking over the music, which with fast start follows almost at once. When several albums or songs share a title, Alexa asks which artist, and you answer "by *artist*". When two playlists share a name, she asks which one, and you answer "by smartlist", "by playlist" or "by" and the folder.

**Settings > JRiver Playlists** decides how your own playlists play when you ask for them: **Shuffle**, **Non-stop** (No, Similar artists or Similar tracks), **Reseed from** and **Skip recent**, either one row for every playlist or a row each. The table shows each playlist's folder and whether it's a smartlist, sorts by folder or name, and can show one folder at a time. A playlist with nothing changed plays exactly as JRiver has it. No command starts with "play", because Alexa tends to hand anything starting "play" to a music service instead of the skill. The skill name is up to you; the one in this repository is "needle drop", chosen because Alexa kept mishearing the first one.

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
| ListenBrainz / MusicBrainz | Similar artists, similar tracks, top recordings, record labels | Only for top recordings (free) | Open data. Choice of algorithm for artists (all-time or recent 75-day) and for tracks (all-time or roughly six months). The slowest artist source on a first run. |
| Deezer | Similar artists, top tracks, name verification | No | Also used to verify AI-suggested artists exist. |
| YouTube Music | Similar artists and similar tracks from the up next queue, playlist output, Discover playlists | No | No sign-in. Uses the unofficial ytmusicapi library, so it may break now and then. |
| Discogs | Album credits, record labels | Yes (free) | Credits, and a second source for the Label button. |
| Anthropic (Claude) | AI-suggested similar artists and tracks, AI Playlist, AI Moderator, Console Query | Yes (paid, pennies per run) | Every suggestion is verified against Deezer before it is trusted. The moderator uses Claude Haiku, a fraction of a penny per playlist. |

Enable any combination of similar-artist sources in Settings. One is enough; several are better. Deezer and YouTube Music need no keys, so 24bit7 works out of the box.

---

## Setup

### JRiver

Enable Media Network in JRiver: Tools > Options > Media Network > **Use Media Network to share this library**. The default port is 52199. 24bit7 talks to JRiver on the same PC by default; if JRiver runs elsewhere, change the host in Settings > Other.

JRiver is only needed for the Now Playing seed and for JRiver output. The Search tab with Output set to YouTube works without it.

### Path A: download and run (Windows)

1. Download `24bit7-v1.6.2-windows.zip` from the [Releases](../../releases) page. It's under **Assets** at the bottom of the release, below the two "Source code" downloads, which are only the Python files.
2. Unzip it anywhere you like and run `24bit7.exe`.
3. Windows will most likely show a blue **"Windows protected your PC"** box the first time, because the exe isn't code-signed. Click **More info**, then **Run anyway**. It only asks once.
4. On first run the app opens on Settings. Add keys for the sources you want; each field has a **?** button with instructions for getting that key. Deezer and YouTube Music work with no key at all, and they are the two sources a fresh install has ticked.

Your keys and history live in two files next to the exe: `.env` (settings and keys) and `24bit7.db` (cache and discoveries). When you upgrade to a new version, copy those two files into the new folder and you'll carry everything over. Settings from older versions are migrated automatically: the single digital store from 1.0.x becomes the first ticked store, the on/off agreement setting from 1.1.0 becomes 2 or Off, Similar Tracks' "Top up from Similar Artists" from 1.3.0 becomes Drift, using similar artists, one round, and the single AI Moderator, Hidden Tracks and Non-stop settings become the starting value on every Play option's tab.

### Path B: run from source

1. Python 3.10 or newer.
2. `pip install -r requirements.txt` (requests, python-dotenv, anthropic, ytmusicapi, and pystray with Pillow for the tray icon).
3. Run `gui.pyw`. First run behaves as in Path A.
4. Optional: pin to the taskbar with a shortcut targeting `pythonw.exe` and `gui.pyw` as the argument. An icon is included.

All settings live in a `.env` file next to the app. The Settings tab is the intended way to edit it, but it is plain text if you prefer.

---

## What's new in 1.10.0

- **Debug works in the app.** Every `[debug]` line and every source's result reach the console; before, they went to a stdout that doesn't exist under pythonw.
- **Export to Log.** Click into the console: a dated file in `logs\` with versions, library size, settings (keys hidden) and the console, for reporting a problem (see Reporting a problem above).
- **AI replies were being cut off.** Claude's thinking was using most of the 2,000-token limit, so Similar Tracks and AI Playlist replies came back cut short, couldn't be read and were discarded; a later run that fitted was cached, which is why AI alone could fail, then work. The list calls now run with thinking off, the limit is 4,000, a reply that can't be read whole keeps every complete entry, and the console says what happened.
- **One copy at a time.** Launching 24bit7 while it's running closes the old copy, so keyboard shortcuts and the tray belong to the one you can see.
- **"AI request sent, cogitating..."** while a request is out; a Similar Tracks summary line; shortcut refusals show the Windows error code.

### Earlier: 1.9.1

- **AI for Similar Tracks.** AI can be ticked as a Similar Tracks source, as it already could for Similar Artists. Its picks blend and vote with the other sources. Off by default; it uses a little Anthropic credit per build.
- **Up to 4 sources can agree** on a track.
- **AI ticks are purple** in both source lists.
- **Drift's Custom Sources never include AI.**

### Earlier: 1.9.0

- **AI Moderator levels.** Off, Relaxed, Balanced or Strict, on the Play tab and per device. Off by default; if you had it on, it's now Balanced (see AI Moderator above).
- **Drift with Custom Sources.** Each Drift section can use its own sources and its own "must agree", or stay the same as Settings > Sources (see Drift above).
- **Vibe Playlist is now AI Playlist.** Its first suggestion is More tracks like the song that's playing. The AI's own picks are never moderated, and its Drift says plainly when it's using your sources rather than the AI, with an optional AI Moderator for those tracks.
- **Bracketed titles match both ways.** "Long Cool Woman (in a Black Dress)" finds "Long Cool Woman in a Black Dress", and the reverse.
- **Nothing found still finishes the job.** Run After Building runs after every build, matches or not, and added playlists play on their own when nothing matched.

### Earlier: 1.8.0

- **Console Query.** Ask Claude why a playlist came out the way it did, and get suggested setting changes. Off by default: Settings > Other > Enable Console Query (see Console Query above).
- **Copy and Clear.** Click into the console to copy what you've highlighted (or all of it), or to clear it.
- **Drift and Non-stop on the Play tab.** Both sit in More Options beside the AI Moderator and change Settings > Playlist for every Play option at once.
- **Band names matched both ways.** "The Jimi Hendrix Experience" finds a library tagged "Jimi Hendrix", and the reverse. "At most 3 per artist" counts them as one artist.
- **Playlists and smartlists set apart.** "Use global playlist settings" has a row for each, so a random-album smartlist can keep its own order.
- **Now Playing refreshes on click,** on its tab or anywhere in its panel.
- **Rounded buttons and tabs.**

### Earlier: 1.7.0

- **Your own playlists in a build.** Add JRiver playlists and smartlists before, after or mixed through any Play tab build, spaced evenly or at random, in the order you list them. The ones you use most come first in the picker.
- **More options.** One row for Show Credits, the AI Moderator and Add playlist, opened from where Show Credits was. It remembers whether it's open, and counts what's on when it's closed.
- **AI Moderator on the Play tab.** Switched on or off as you go, for Similar Artists and Similar Tracks. Voice devices with settings of their own keep theirs.
- **Run after building.** Settings > Playlist can run a file once a playlist is in JRiver, per Play option and per device.
- **Purple for AI.** Anything that spends Anthropic credit is marked in purple: the AI Moderator, Vibe Playlist's bar and the Anthropic key.
- **Tidier header.** The tagline sits beside the logo, and the track title in Now Playing is smaller.

### Earlier: 1.6.2

- **Band names.** Similar Tracks now finds a library tagged with the band's full name when a source gives the shorter one: "Jimi Hendrix" finds The Jimi Hendrix Experience. Whole words only, so Queen never finds Queens of the Stone Age, and the title still has to match. The log shows each one as "Matched on band name".
- **Quieter in the background.** 24bit7 asks JRiver far less often. The Now Playing panel checks every 10 seconds and not at all while 24bit7 is minimised or in the tray, the zone list is read once a minute, and Non-stop checks every 15 seconds.

### Earlier: 1.6.1

- **Skip by voice.** "Alexa, ask needle drop to skip" (or "next") moves that device's zone to the next track. A plain "Alexa, skip" goes to the speaker, which can't skip a JRiver stream; an Alexa Routine can shorten the phrase.
- **Who is this?** Alexa says the track, artist and album playing in the device's zone, without remaster or soundtrack tags, and reads compilations tagged "Artist - Title" properly.
- **More like this.** Similar Tracks seeded from what's playing. The current track carries on and the new playlist replaces what was queued after it.

### Earlier: 1.6.0

- **Non-stop.** When the last track of a playlist 24bit7 built starts, more are added, set per Play option: similar artists or similar tracks from the last or 2nd track, the rest of an artist after their top tracks, or more of the same vibe.
- **Filters.** Named filters with Applies on, Only pick from a playlist or smartlist, and rules on rating, year, plays, dates, genre, artist, album, duration, file type, bit depth, sample rate and location.
- **Keyboard shortcuts.** Global keys for a remote, aimed at one zone, seeding from the last track played when Playing Now is empty.
- **JRiver Playlists.** Shuffle, Non-stop, Reseed from and Skip recent for the playlists you ask for by voice, per playlist or for all of them, with folders, types, sorting and a folder filter. Alexa asks which one when two share a name.
- **A tab per Play option.** Settings > Sources and Playlist have Similar Artists, Similar Tracks, Artist's Top Tracks and Vibe Playlist tabs, each with its own Drift, Non-stop, Hidden Tracks and AI Moderator. Sources are listed one per line, with the ListenBrainz algorithm beside ListenBrainz.
- **AI Drift for vibe playlists.** Drift can ask the AI again with your description, avoiding repeats. Never the default, as it uses a little credit per round.
- **Changed.** The Play tab buttons seed from the last track played when Playing Now is empty. Number of tracks has a ? explaining it's a target. Vibe playlists no longer use the AI Moderator. Settings tabs now run Sources, Playlist, Filters, Search, Keys, Voice Commands, JRiver Playlists, Other.

### Earlier: 1.5.2

- **Shared credits.** A track credited to "Paul McCartney & Wings" or "Mark Ronson feat. Amy Winehouse" now finds a library tagged with just the first-named act. The title still has to match, and the log shows each one as "Matched on primary artist".
- **Clear Discover history.** Clear all and Clear selected on the Discover tab, each with an "Are you sure?" first. Your cache and settings are left alone.

### Earlier: 1.5.1

- **Voice commands take over their zone.** A new build command replaces whatever is in Playing Now for that device's zone and starts straight away, even after "Alexa, stop", which pauses the speaker without JRiver always noticing. A newer command for the same zone stops an older build still running, so its tracks no longer trickle in afterwards.
- **Misheard artists.** "Songs by" and "music like" match the artist Alexa heard against your library, so "the beetles" plays The Beatles. The log shows what was heard.

### Earlier: 1.5.0

- **Dark theme.** Settings > Other > Theme switches between Light and Dark, with a restart offered straight away. Dark is charcoal with matrix green text, black dropdowns, text boxes and Discover table, and green ticks.
- **A new look in both themes.** Folder-style tabs that open into the page below, redesigned Play buttons, the 24bit7 icon in the title bar and taskbar, and Track, Artist and Album labels in Now Playing.
- **Official music videos.** Settings > Other > Prefer official music videos plays the artist's own video where one exists, when Output is set to YouTube. Off by default.
- **Sharper matching.** Titles ending "- From ... Soundtrack" match the plain title, and "&" matches "and".
- **Changed.** YouTube's pick for an artist no longer takes a guaranteed slot; it joins the pool with that artist's top tracks. Discover's Misses, Hits and All buttons are now a Show dropdown.

### Earlier: 1.4.0

- **Fast start.** With nothing playing, the first track starts within a second or two and the rest of the playlist follows it in. Voice "shuffle songs by" opens on one of the artist's top five.
- **Drift.** Similar Artists, Similar Tracks and Vibe Playlist can search again from what they found when a playlist comes up short, using similar tracks or similar artists, for 1 to 6 rounds. Off by default.
- **AI Moderator.** An optional Claude Haiku check that removes tracks clashing with the seed's tone, energy and mood, never on genre alone, with each removal and its reason in the log. Switched on under Settings > Sources.
- **Settings per device.** Tick Own settings for an Alexa device and it gets its own Sources and Playlist tabs, copying the Windows app's settings until you change them.
- **Skip tracks played recently.** Each Play mode can leave out anything JRiver has played in the last so many days, 1 by default. Off by default.
- **Hidden Tracks.** Long album closers, where a hidden bonus track follows a long silence, are skipped from built playlists.
- **Label.** A Discover button that finds who released a track and opens the label on Bandcamp.
- **Voice Commands guides.** [How Voice Commands work](docs/VOICE_COMMANDS.md) and [Setting up the Alexa skill](docs/VOICE_SETUP.md), linked from the app.
- **Changed.** Settings is laid out in boxed sections, with each note behind a ? popup. Voice is now Voice Commands, and speakers are devices. Similar Artists has a Number of tracks setting (30 by default). Similar Tracks' top-up and Vibe's automatic backfill are now their Drift settings. Voice acknowledges a command with a short tone instead of "You got it".

### Earlier: 1.3.0

- **Similar Tracks.** A new Play button that builds a playlist of tracks like the seed track, from Last.fm, ListenBrainz and YouTube Music, with its own sources, agreement number and playlist settings.
- **Zones.** Output lists every JRiver zone by name, Now Playing has its own Zone dropdown, and Settings > Other sets which zones show, the default zone and whether to follow JRiver's active zone.
- **Voice control.** An optional, self-hosted Alexa skill for top tracks, similar artists, similar tracks, genres, albums, songs, playlists and shuffles, each speaker playing to its own zone. Advanced setup; see Voice Commands above.
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

**Newer**: Drift's Custom Sources, the AI Moderator's levels, added playlists, run after building, non-stop, filters, keyboard shortcuts, JRiver Playlists settings, the dark theme, fast start, Drift, the AI Moderator, settings per device, skipping recent plays, Hidden Tracks, the Label button, Similar Tracks, zones, voice control, Discover's YouTube playlists, the tray, the Search tab, YouTube Music as a source and YouTube output. All are in daily use on the development PC. Voice Commands are the least plug-and-play part, as their setup guide says, and the YouTube parts rest on an unofficial library, so expect the occasional breakage. AI Playlist works well and is still learning its limits.

**Removed**: a producer-based playlist mode built on Discogs credits. Discogs credit data is too patchy to be reliable, so it was dropped rather than shipped half-working.

### Roadmap

- Remembering Deezer artist IDs, for quicker first runs
- Voice: "add this track to a playlist"
- Voice and keyboard on/off switches for non-stop, shuffle and the AI Moderator
- A web browser as a Now Playing source
- More players and outputs beyond JRiver and YouTube (distant)
- A shared recommendation database built from the hit/miss data (very distant)

---

## Licence

Released under the MIT Licence. See LICENSE. Provided as is, without warranty of any kind, as the licence says.

## Support the project

24bit7 is free and always will be. If it has found you music you'd have missed, you can buy me a coffee (or a Beer!): https://paypal.me/24bit7
