# Decision log

Dated record of the calls made while building 24bit7, and why. Newest at the bottom.

**Aug 2026: Build for myself first, release for free, keep bigger options open.**
A colleague suggested a commercial product. Decided the passion is in solving my own problem; a paid version or a shared database stay as distant possibilities. Non-commercial use also keeps Last.fm and MetaBrainz terms simple.

**Aug 2026: Name-based matching, not MusicBrainz IDs.**
IDs would be cleaner but most personal libraries aren't tagged with them, so matching on names with a set of normalisation rules is what actually works on real collections. Cost: an ongoing list of edge cases (accents, sort names, initials, version suffixes), each fixed as it turned up.

**30 Aug 2026: Mid-album queueing via EditPlaylist Remove.**
Earlier attempts at clearing Playing Now without a gap failed. The fix was discovering that MCWS `Playback/EditPlaylist` with `Action=Remove` takes the index in a parameter called `Source`, not `Index`. Removing from the end down to the current position, then the entries before it, leaves the current track playing untouched.

**30 Aug 2026: One provider per run first, blending later.**
Got each source (Last.fm, ListenBrainz, Deezer) working in isolation with no fallback before attempting to combine them. Made failures obvious and attributable.

**30 Aug 2026: Producer mode marked experimental.**
Discogs credit data was inconsistent enough that a producer-driven playlist worked on some albums and not others.

**30 Aug 2026: Add an AI source, but verify everything.**
An LLM is good at "artists like X" and bad at not inventing them. Every AI suggestion is checked against Deezer by exact name before it is used or logged.

**30 Aug 2026: Cache everything.**
Last.fm's terms actually require caching similar-artist data for at least a week. MetaBrainz and Discogs data is CC0. So caching all provider responses is both allowed and expected, and it makes repeat runs free.

**31 Aug 2026: Settings in .env, edited through the app.**
A settings database was considered. Plain text won: readable, diffable, gitignored, and trivially reloaded. The Settings tab writes it safely, preserving comments and any keys it doesn't manage.

**31 Aug 2026: Blend with position weighting, fetch deeper than needed.**
Merging ranked lists by position, with a bonus for artists on multiple lists, then trimming. Fetching two levels deeper than the target (BLEND_DEPTH=2) gives the blend enough material to reflect agreement rather than one source's ordering.

**31 Aug 2026: SQLite replaces the CSV.**
One database for provider cache, sessions and discoveries (hits and misses). The old FutureDiscoveries.csv was imported once (360 rows, 48 sessions) and retired. CSV becomes an export, not the record.

**1 Sep 2026: Renamed to 24bit7 and forked into its own repo.**
JRiverGenius frozen as a fallback. The new name doesn't tie the project to one player.

**1 Sep 2026: Engine split from interface.**
`engine.py` holds all logic with no print or input calls, reporting through a callback. Front ends (CLI, Tkinter, anything later) stay thin. This is what makes a web or mobile front end feasible without a rewrite.

**1 Sep 2026: Dropped the producer playlist entirely.**
It never got reliable. Show Credits kept, because the credit display itself is interesting and the fetching code is shared.

**1 Sep 2026: Tkinter for the GUI.**
Ships with Python, no extra dependency, good enough for a three-tab tool. The default look needed a DPI fix and some ttk work to stop looking like Windows 95, and a few Windows-specific ttk quirks (cell fonts via row tags) had to be worked around.

**1 Sep 2026: One window, three tabs, auto-saving settings.**
Started as separate windows and popups. Consolidated to one window; Settings saves on every change with no Save button.

**1 Sep 2026: Vibe Playlist as a two-step process.**
Step one lets the AI wing it with artist/track pairs checked against the library. Step two, only if half or more missed, uses the hits as seeds for Last.fm and Deezer similar-artist lookups to fill the gap. Keeps AI cost low and results grounded in what is actually owned.

**Sep 2026: Android version parked.**
Since JRiver runs on the PC, any mobile version is a remote, not a port. If revisited, the route is a small local web server around `engine.py` with a mobile web UI, not a native app. Not needed while listening happens at the PC.

**28 Sep 2026: Tabs and buttons drawn by hand.**
Windows draws ttk tabs and tk buttons in its own style and ignores the colours an app asks for. Both are now plain frames and labels with every colour in one palette, so they look the same on any PC and a theme only changes the palette.

**28 Sep 2026: Dark theme on Tk's clam style, Light left native.**
Clam is the only built-in ttk style that takes colours, so Dark uses it for dropdowns, tick boxes and the Discover table. Light keeps Windows' own look. The theme applies at start-up with a restart offered, because recolouring every open widget live is a lot of code for little gain.

**28 Sep 2026: Matrix green in Dark.**
The log was already black with green text, so Dark takes its cue from it: black fields, green text, orange kept from the logo. It gives the dark theme a character rather than just being grey.

**28 Sep 2026: YouTube's pick loses its guaranteed slot.**
YouTube was trusted to pick the track for each artist it suggested. In use, Last.fm's top tracks proved the better picks, so YouTube still chooses artists and adds its track to the pool, but no longer claims a slot.

**28 Sep 2026: Two more matching rules.**
A soundtrack copy ("- From 'Casino Royale' Soundtrack") let the same song in twice, and "Girls & Boys" missed "Girls And Boys" because "&" was stripped as punctuation. Both are now folded before matching.

**28 Sep 2026: build.bat backs up, and makes the release zip itself.**
A rebuild deletes the packaged app's folder, and with it the .exe's settings and history. build.bat now backs both up and puts them back. The release zip is made from the clean build before that, and checked for a .env or database, so a user's keys can never ship in it.

**28 Sep 2026: Voice always takes over its zone.**
After "Alexa, stop" the Sonos is paused from its own end and JRiver can still report it as playing, so a new playlist queued behind a track that never ended. A voice command now replaces Playing Now whatever state JRiver reports, and a newer command for a zone cancels the older build. The Play tab keeps its queue-after-the-current-track behaviour.

**28 Sep 2026: Heard artist names are matched to the library.**
Alexa heard "the beetles"; Last.fm corrected it quietly, but the library search used the heard spelling and found nothing. Songs by and music like now take the library's spelling when a name is close enough.

**28 Sep 2026: Shared credits fall back to the first-named act.**
"Band On The Run" came back from a source as Paul McCartney & Wings, but the library has it as Paul McCartney, so it showed as a miss. When the full credit misses, the lookup now tries the first-named act (split on &, and, feat., with, commas and the like), with the title still required to match so a duo can't pull in a solo song by mistake.

**28 Sep 2026: Discover history can be cleared.**
Clear all removes every session; Clear selected removes just the ticked rows. Both ask first with No as the default. Only Discover's history goes: the provider cache stays so builds stay fast, and the old CSV is not imported again.

**1 Oct 2026: More like this keeps the current track.**
Every other voice build takes its zone over, because after "Alexa, stop" JRiver can still report a paused Sonos as playing. More like this is asked for because the current track is good, so it uses the Play tab's rule instead: the current track carries on and the new playlist replaces what was queued after it. Skip and who is this need no build and answer at once.

**1 Oct 2026: Band names match on whole words.**
A forum user's library has The Jimi Hendrix Experience, and Similar Tracks looked for Jimi Hendrix and missed it. The JRiver search used by the other Play options already accepted an artist as whole words inside the tag; the in-memory matcher Similar Tracks uses compared whole names and didn't. It now falls back to the same whole-word rule, only after the title has matched. Whole words keep Queen away from Queens of the Stone Age; the title check keeps it away from Queen Latifah unless she has a song of the same name.

**1 Oct 2026: 24bit7 asks JRiver less often.**
A forum user saw the Playing Now cursor jump back to the playing track. It couldn't be reproduced, but 24bit7 was asking JRiver two or three things every 3 seconds even from the tray, for a panel nobody could see. The panel now checks every 10 seconds and only while the window shows, the zone list is cached for a minute, and Non-stop checks every 15 seconds. The Play buttons and shortcuts always read the zone fresh, so nothing depends on the panel being current.

**2 Oct 2026: Added playlists are for the Play tab.**
A forum user wanted his smartlists to follow 24bit7's picks, but couldn't time it, because a build can take a second or several. Rather than only offer a hook to run a file, the Play tab adds playlists itself: before, after or mixed through. Voice, shortcuts and non-stop don't use them. Voice already has settings per device, and Run After Building covers anyone who wants to chain something by voice.

**2 Oct 2026: Added playlists keep their own rules.**
A smartlist already says what belongs in it, so 24bit7's filters, recent-play skip and hidden-track check leave added playlists alone. The one thing dropped is a song already in 24bit7's picks, so nothing plays twice.

**2 Oct 2026: Drift finishes first when playlists are added.**
Normally the first pass is queued straight away and each Drift round follows it. With an Add after playlist that would put Drift's tracks after it, so with playlists added, Drift runs to the end and the whole playlist is sent at once. Fast start still plays the first track straight away.

**3 Oct 2026: Matching stays rules-based.**
A forum user's Hollies track missed after he retagged it, and he suggested the fuzzy scoring MCUtils uses for voice search. The miss turned out to be one rule: bracketed title words were deleted rather than kept. Fixing that rule was preferred to adding a scoring layer, because rules are predictable and every match can be explained in the log. 4,196 of 4,390 bracketed titles on the development library now match where they would have missed.

**3 Oct 2026: The AI Moderator gets levels, off by default.**
The same user found it removed too little: it could take out at most a fifth of the tracks, and only when sure. Rather than make it stricter for everyone, it now has Relaxed (the old behaviour), Balanced and Strict. 24bit7's main job is to bring Last.fm and the other sources to your library without AI, so the moderator stays optional and starts Off.

**3 Oct 2026: Vibe Playlist becomes AI Playlist.**
The name hid that the AI picks every track. The new name says so, and the AI's own picks are never moderated, since asking AI to judge AI adds cost and nothing else. Drift can still top up from your sources, and only those tracks can be checked.

**3 Oct 2026: Drift can use its own sources.**
The first pass wants reliable picks; the top-up rounds are where wider sources earn their place. Custom Sources lets Drift use different sources and agreement from the Play option it belongs to, and the log names them each round.

**3 Oct 2026: Thinking off for the AI list calls.**
The diagnostics build showed Claude Sonnet 5 spending about 2,400 of 2,999 output tokens thinking before writing a 600-token song list, and the 2,000 limit cut the list off. Recalling song titles doesn't improve with deliberation, so those calls now run without it: cheaper, faster, and the list gets the budget to itself. The Moderator keeps its model as it was.

**3 Oct 2026: A new launch closes the old copy.**
Two copies fight over the keyboard shortcuts and the tray, and the second always loses silently. Closing the old one outright is blunt, but asking it to quit would only send it to the tray.

**4 Oct 2026: The manual is built from Markdown at release time.**
A PDF written by hand goes stale the moment a setting changes. MANUAL.md lives in the repo beside the code, and build.bat turns it into a PDF stamped with the version, so the manual in the zip always matches the release. The Voice Commands guides became chapters of it, with their old pages left as pointers so posted links still work.

**4 Oct 2026: Screenshots from a demo mode.**
The manual's screenshots come from screenshots.py, which runs the real app against fake data around one Beatles track: no JRiver, no real library, no keys. The same data gives the same pictures every run, so only shots whose code changed are rewritten, and nothing private ends up on GitHub.

**4 Oct 2026: The console's words carry the meaning, the colours follow.**
Copy, Export to Log and Console Query all get plain text, so a warning can't rely on being amber. Every line that matters starts with `Note:` or `Problem:` and every build ends with `Done:`; the colours are read from those words. Lines that only confirm normal working, such as fast start, moved to debug.

**4 Oct 2026: Debug is always recorded.**
The Debug tick meant switching it on and running the build again before anything useful could be seen. Now every debug line is kept, Simple/Advanced only decides whether the console shows them, and Export to Log always includes them.

**4 Oct 2026: One console, a tab per source, a Log of builds.**
Voice and Non-stop builds used to land in the same console as your own, wiping whatever you were reading. Each source now keeps its own latest build, and the Log keeps the last 50 from each with their figures. Collapsible blocks per build were tried in the design and dropped: the plain text reads better.

**4 Oct 2026: AI is magenta.**
Anything that spends Anthropic credit is now marked in magenta rather than purple: bright in the dark theme and on the black console, deeper in the light theme so it stays readable on grey.

**5 Oct 2026: Long closers are skipped while a playlist is found.**
The hidden-track check ran on the finished playlist, after it had been cut to its target, so each long closer it dropped left a gap while the Done line still showed the target. It now works like Skip recent, as tracks are found, so the next one takes the place. The QA suite found it.

**5 Oct 2026: A test suite against a fake world.**
24bit7 talks to JRiver, five music services, an AI and Alexa, none of which can be used in a test. tests\ fakes all of them, runs the real Alexa skill code through the real listener, and changes every setting then reopens Settings to check each one kept, which would have caught the 1.11.1 bug before release.

**5 Oct 2026: Alexa never reads the whole list unless asked.**
A misheard command made Alexa read every command, then read them again. Now it says one short line pointing at "list commands", once.

**5 Oct 2026: Switch targets are zones a device plays to.**
"Switch" moves the music to a room you can talk to, so only zones an Alexa device plays to can be ticked. The ticks are kept by zone name, so a zone with no device (a TuneBlade "Whole House" zone, say) can be added later without a redesign.

**5 Oct 2026: Switching to a DLNA zone restarts the song.**
A Sonos needs a moment to start before JRiver can jump within a track, and Alexa can't be kept waiting for it. Waiting in the background and then seeking was offered and turned down: the restart is the simpler behaviour, and local zones still carry on from the same point.

**5 Oct 2026: Stop the music, not stop.**
Amazon keeps a bare "stop" for itself, so the skill's stop is "stop the music", with pause and resume alongside, all acting on the asking device's zone.

**5 Oct 2026: Keep It Going borrows Similar Tracks.**
Music started in JRiver belongs to no Play option, so a one-off Non-stop needs settings from somewhere. It takes the zone's Similar Tracks Non-stop settings, whether or not Non-stop is switched on there, because saying the command is the switch.

**5 Oct 2026: Blend has no round limit, but a cap.**
Blend aims for one new song per playlist song, so it keeps searching, seeding from what it finds, until it gets there, stops when a round finds nothing new, and never adds more than 50. Seeds are the first, middle and last songs, and what several seeds suggest ranks first.

**6 Oct 2026: Switching to a DLNA zone carries on after all.**
A test on the Sonos showed it accepts a jump once it's playing, about a second after starting. The switch now starts it muted, waits, jumps to where the old room has got to, lets its buffer clear, then brings the volume back and stops the old room. If anything fails the song starts from the top, as before. Switch Timing Adjustment covers the Sonos's own delay, which JRiver can't see.

**6 Oct 2026: Drift and Non-stop name what they do.**
"Keep It Tight" stays anchored to where you started; "Spread" and "Let's See Where This Goes" travel. Drift's Last Round was dropped: Spread covers it, and two clearly different choices are easier to pick between. Each is one dropdown with Off first, so there's no separate tick.

**6 Oct 2026: The moderator sees the playlist, not just the seed.**
ZZ Top's Tush passed a Strict check against Beast of Burden alone. Judging a Drift track against the first round's tracks as well makes the odd one out obvious, for a few hundred extra input tokens.

**6 Oct 2026: AI prices are built in and dated, not fetched.**
Fetching prices online (a file on GitHub, or Claude with web search) would add a connection, a cost or a setting to switch on. The rates live in ai_usage.py with the date they were checked, are updated as releases are prepared, and every estimate says it may be out of date.

**6 Oct 2026: The title bar is 24bit7's own, with a way back.**
The tab strip runs to the top of the window, and Windows is told it's the title bar, so dragging, snapping and maximising still work. Because it can't be tested on every PC, Use the Windows title bar brings the normal one back after a restart.
