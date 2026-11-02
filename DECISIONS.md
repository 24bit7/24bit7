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

**7 Oct 2026: Variety is off by default.**
A new user wants to see every match first, then decide whether they want variety. The closest matches in order is also what Similar Tracks did before 1.13.0. Voice devices with their own settings can keep it on, since a playlist asked for from the sofa is better different each time.

**7 Oct 2026: Review Mode loads the playlist, then stops it.**
JRiver is a better playlist editor than 24bit7 would ever be: removing tracks, reordering and adding to other playlists are all there already. So Review Mode hands over rather than building an editor, and reuses the normal send step with fast start off, stopping the zone straight after, so at most a fraction of a second plays.

**7 Oct 2026 (later): Review is a list in 24bit7 after all.**
Review Mode (above) handed over to JRiver, and the same day showed why that wasn't enough: a DJ wants to hear a candidate before committing to it, and JRiver's editor can't play one track in the headphones while the room carries on. So Review became a list in the console area with its own actions, and the 3 Oct call against a preview was reversed: **Preview in** plays one track in a second zone, which is exactly what a headphone zone is for. The actions read Output when pressed rather than remembering the build's zone, so changing your mind about the room is one dropdown, and YouTube gets a single Play on YouTube rather than four actions that mean nothing there.

**7 Oct 2026: Notes on titles, not ? marks.**
Forty ? marks were visual noise, and a note that sits behind a mark two widgets away from its setting is easy to miss. The note now belongs to the row's title, shown after half a second so sweeping the pointer across a page doesn't flash them up, and the pointer becomes a question mark where a note exists. The ? buttons on Settings > Keys stay, since those open a window with the steps for getting each key.

**7 Oct 2026: A profile is applied by restarting.**
Settings are read in several places (the engine, the Settings pages, the Play tab switches), and swapping them all in place is a lot of ways to leave a control showing the old value. Load writes the profile as pending and restarts 24bit7, which applies it before anything reads a setting, the same way the theme change already worked. Profiles cover Windows (Main) only, so loading DJ never changes what the kitchen Echo does.

**7 Oct 2026: Use AI is a pause, not a key removal.**
A No AI profile needs one switch that stops every feature spending credits and leaves every other setting alone. Use AI Off greys the AI pieces out rather than leaving them live and ignored, so what you see is what will happen, and each feature says once per build that it stood down.

**7 Oct 2026: Steer trusts the AI on tempo, but checks the tags.**
The AI's sense of tempo is approximate. Where the seed and a pick both carry BPM tags, Faster and Slower are checked against the numbers and a pick going the wrong way is left out; where tags are missing, the AI's judgement stands. Both AI Playlist modes ask for about twice the count asked for, since a share of any list isn't in the library.

**7 Oct 2026: The top strip reaches the top.**
Windows 10 paints a light edge above a caption-less window's frame. Rather than live with it, the window has no top frame at all, the top few pixels still resize, the strip's colour fills anything Windows hasn't drawn yet, and the frame is re-measured after a snap or a focus change, which is where the edge crept back. It was proved in a standalone window first, because it runs during every drag.

**9 Oct 2026: build.bat publishes without a keyless test.**
The keyless test (unzipping a clean copy to the Desktop and opening it before a Y/N) had passed on every release, so it was a step to click through rather than a check. build.bat now publishes as its last step. It still can't publish a broken release: failing tests, a failed build or a missing zip stop it before publishing is reached, and release.ps1's own checks (gh signed in, notes committed, everything pushed, no release with this tag) stop it before anything goes online.

**9 Oct 2026: Seed: Playing Now gets settings of its own.**
A Playing Now seed was parked on 8 Oct because it needed new settings, and the rule then was no new settings for features like it. It came back because the figures can't be shared: five sampled artists asking for twenty similar each would give a hundred, not thirty. So Settings > Playlist grew Playing Now columns, with defaults that land on the same size of playlist as Current Track, and Review Mode a Playing Now column of its own. Each sample takes its share in turn, from the top of its own list, skipping artists already used, so the list stays balanced across what you were listening to rather than leaning on whichever seed has the longest list.

**9 Oct 2026: A similar artist only counts once it gives a library track.**
Number of artists used to count every artist the sources suggested, whether you owned any of them or not, so the same setting gave very different playlists from library to library. Now an artist counts once one of its picks is in your library, and the next one down is read when it isn't (up to three times the number wanted). That's needed for Playing Now's per-sample shares to mean anything, and it applies to Current Track as well so the two columns mean the same thing. Playlists come out fuller; Limit total tracks still caps them.

**11 Oct 2026: If All Else Fails' spoken message is an option, off by default.**
The message is a WAV file played in JRiver, so it lands in Playing Now, and at Windows' 22 kHz it can trip a DSP setup that expects otherwise (mandrews79, GitHub issue #7). It also plays on keyboard shortcut builds, not only voice. So it's now "Say why in the room first" under If All Else Fails, one setting for every playlist type rather than one per type, in line with keeping settings few. Off means a voice command that finds nothing goes straight to the fallback with no explanation in the room; the console still says why.

**9 Oct 2026: If All Else Fails, and how a voice command hears it.**
A build that finds nothing used to end quietly, which on a voice command means silence in the room. Now it shuffles the seed's genre (at a similar tempo where tags allow). Alexa has to answer within eight seconds, long before a build knows it's empty, so the explanation is spoken through the zone with Windows' own text-to-speech rather than by Alexa, and the music waits for it to finish.

**9 Oct 2026: The AI Moderator never skips silently.**
A Drift round that found one track skipped the check with no log line, and on Spread that one track went on to seed a later round (datdude's report). Balanced and Strict check single tracks; Relaxed, whose cap is a fifth, skips them and says so; set but unable to run says why once a build.

**12 Oct 2026: Tidal is an Output, not a Now Playing source.**
Windows can see what Tidal plays in Chrome, so Tidal could have joined Now Playing as a source, with a Chrome extension to start playlists at the right moment. Decided against it for now: 24bit7 is built for the JRiver listener, and driving Tidal's web player would break whenever Tidal changes it. Output to Tidal works like Output to YouTube, and a track heard on Tidal can still be typed into the Search tab. `media_probe.py` (not in git) is kept in case this is revisited.

**12 Oct 2026: Output to Tidal signs in once and fills one playlist called 24bit7.**
Writing a playlist needs the user's own Tidal login, which 24bit7 can't borrow from the browser or app, so Settings > Keys has Sign In to Tidal: Tidal's page in the browser, a code back to `localhost:47807`, and a refresh token kept in .env. Each build replaces the tracks of the playlist named exactly 24bit7, found by name rather than a saved ID, so renaming it in Tidal keeps it and the next build makes a fresh one. The console offers Open in Tidal app (a `tidal://` link, which goes straight to the playlist) and Open in Tidal web; nothing opens on its own. Tracks are found by name; a test on five real builds found 96%, so ISRCs aren't needed.

**12 Oct 2026: One set of character rules for every name comparison.**
The Tidal test showed the library matcher and the source and lookup rules had drifted apart: the library already folded accents and read '+' as 'and', the rest didn't. `fold_name_chars()` now holds the character rules (accents, '$' next to a letter as 's', '&' and '+' as one joiner) and every comparison uses it, so every mode gets each new rule. Near-miss titles (one letter or so out) stay limited to looking a track up by an artist that has already matched, the library and Tidal: between sources, 'Song 2' and 'Song 3' must stay apart, and numbers must always agree.


**13 Oct 2026: Settings > Discover, Create Playlist and Additional Outputs.**
Settings > Search became Settings > Discover, as everything on it makes buttons on the Discover tab, and Record Label moved in with the reference sites rather than having a section of its own. Two new sets of ticks, kept apart on purpose: Create Playlist (Settings > Discover) picks Discover's playlist buttons, and Additional Outputs (Settings > Other) picks the services in the Play tab's Output list. They affect different screens, and someone may want Tidal for one and not the other. Both default to YouTube only, as before; an output that's unticked is never used, even if .env still names it.

**13 Oct 2026: Deep Cuts, from the library's own genres.**
In a big library the sources keep coming back to the well known, so some corners never get played. Deep Cuts tops a build up from the seed's genre with what's been played least: the least played fifth of the genre's artists for Similar Artists (scored across all their tracks, so one recent play doesn't make an artist "recent"), and the least played fifth of its tracks for Similar Tracks and AI Playlist. Version one uses only the library's Genre tags, no Last.fm tags or outside index; on Ben's library, with every track tagged in 40 genres, it picked well. A standard genre list mapped from Last.fm's album tags was worked through for libraries with messy genres and left for later, if asked for. The share is added on top of the build, so the normal playlist is never cut short. It's switched on from the Play tab only (Off, Spaced or Shuffled); Settings > Playlist keeps just the share, per option.

**13 Oct 2026: The AI Moderator becomes the Moderator; Non-stop's button becomes the infinity sign.**
Shorter names for a busier More Options row. Magenta still marks the Moderator as using the AI. Old usage records and builds in the Log still read under the new name.

**13 Oct 2026: The Play tab's hover notes show only while ? is on.**
With every Play tab control explained, the notes got in the way of everyday use. A ? at the right of the More Options row switches them on, off by default; notes saying why something is greyed out always show, as a greyed-out button otherwise gives no clue. The rest of 24bit7 keeps hover notes as before.

**13 Oct 2026: A Last.fm key built into the release.**
New users were starting on Deezer and YouTube until they found and pasted a Last.fm key, and Last.fm gives the best similar artists. build.bat now packs the key from Ben's .env into the build (builtin_keys.py, gitignored and deleted after), so the public repo never holds it; running from source still needs your own. A user's own key always wins. Fresh installs now start on Last.fm for Similar Artists and Last.fm plus YouTube for Similar Tracks; existing settings are left alone. Risk: anyone can pull the key from the zip, and every user without their own shares its limits. If Last.fm ever throttles it, the fix is a new key in the next release.


**14 Oct 2026: 24bit7's own prompt for a name, in place of Tk's stock box.**
Save as Playlist, Save Profile, New Filter and Rename Filter asked for a name with Tk's simpledialog, which ignores the theme: a white Windows title bar on the dark theme, a plain box and stock buttons. NamePrompt in tabs.py replaces it, built like the AI Playlist window: no Windows title bar, a header strip that's the drag handle, the name in a rounded box selected to type over, and OK and Cancel drawn like the rest of the buttons. One prompt for all four, so they stay alike. The yes/no boxes (Replace it?, Delete?) still use Tk's messagebox; they can follow the same way if they grate.

**14 Oct 2026: The Play tab says things in the console, not under the controls.**
The line under the added playlist rows saying what the next build would do took a strip of the Play tab for something that only matters when a row changes. It now goes to the console as a Note line, once per change, where the rest of what 24bit7 is about to do already lives. Close Review follows the same thinking: the console is the resting state, and Review is a view on top of it that can be put away.


**15 Oct 2026: A shortcut per profile, kept with the shortcuts rather than in the profile.**
Switch Profiles steps A to Z, which is fine from the keyboard and no use to an automation that can't see which profile is current (datdude drives a stereo and a surround set-up from a Theater View remote). A key per profile always lands on one, and does nothing when that profile is already loaded, so pressing it twice is safe. The key lives in .env as HOTKEY_PROFILE_<name> with the other shortcuts, because shortcuts belong to the PC: a profile file copied to another PC shouldn't bring a key that clashes there. The zones joined profiles at the same time. The Default zone and the shortcut zone say where you're listening, which is what a profile is for; which zones are shown describes the PC and stays out. A profile is compared on the settings its file holds, so profiles saved before a setting joined aren't all marked changed by it, and loading one leaves that setting alone.

**20 Oct 2026: German, in stages, with the English kept in the code.**
Helmut writes to us in his second language and asked Claude to translate the manual for himself, which showed there's a want. The first estimate overstated the cost per release: with the German written alongside the English in the same change, a release only adds the few lines it changes. The real cost is the one-off move of roughly two thousand bits of text, so it goes in stages: the setting, the screens, the console, then the manual. German is only offered once the screens and console are all done, as a half-German app is worse than an English one. The code keeps its English and `i18n.t()` looks it up, so code still reads in English and anything untranslated shows in English rather than breaking; a test fails whenever text has no German. Text with numbers or names is one sentence with blanks, since German word order differs. The language belongs to the PC, not a profile. Alexa stays English: a German skill is a separate set-up for every user. Another language is a request away, through the forum or GitHub.

**20 Oct 2026: The German manual is its own file, with its own screenshots.**
docs/MANUAL.de.md is a full translation rather than generated from the English, so it reads as German, not as a word swap; a release that changes the English manual changes the German one in the same commit. Its screenshots live in docs/images/de, taken by screenshots.py --lang de from the same demo data, and a shot not yet taken in German falls back to the English one so the PDF always builds. Taking the shots in German turned out to be the best check of the translation: it found English left on screens the tests hadn't reached.

**24 Oct 2026: Did you mean, from the library, offered and never assumed.**
"eleven finger" typed into Search found Last.fm's page for misfiled scrobbles, whose tracks never matched Ben's Finger Eleven. Ben's first idea was an AI suggestion with its own setting. The library is the better dictionary: it already holds every artist you own, costs nothing, works offline and can only suggest something you have. The nearest name is close to the fuzzy matching we keep out, but matching still never guesses: the console offers the name as a link, and only a click uses it. Same words in another order come first, then the one clear nearest name; a tie offers nothing.


**27 Oct 2026: The AI Playlist gets its own tracks-per-artist limit.**
datdude asked for "industrial rock" and half the list was NIN. The limit covered Drift's top-up but not the AI's own picks. Reusing the Similar Tracks limit was considered and turned down: changing one playlist type's setting shouldn't quietly change another's. Every other type already has its own, so the AI Playlist column got one too, default three.

**27 Oct 2026: No two by the same artist in a row, with no setting.**
Nobody wants the same artist twice running when it can be avoided, so there's nothing to choose. A repeat swaps with the next track by someone else, so orders such as similar first barely change; when one artist is all that's left, the repeats stay. Artist's Top Tracks, albums, songs and the user's own playlists keep their order.

**27 Oct 2026: Voice playlists wait for the playing track by default.**
datdude wanted a request to let the current song finish. An API flag was considered first, but Ben wanted it for everyone as a choice, so it became New Playlists under Settings > Voice Commands: After this track (the default) or Play now. A stopped or paused zone starts at once either way, and albums, songs, playlists and shuffles always play at once, as they're asked for by name.

**27 Oct 2026: "More artists like this" alongside "more like this".**
More like this gives Similar Tracks, and there was no voice way to get Similar Artists from what's playing. "Music like this" used to fall back to Similar Tracks and now goes to more artists, which is what the words say.

**27 Oct 2026: "Only" is a separate command, not a change to Genre.**
"chill Led Zeppelin" through Genre brought in the Eagles, as the AI Playlist spreads across artists on purpose. Spotting an artist's name inside Genre requests was turned down: it would guess, and Ben uses Genre for broad moods. A two-slot command ("chill songs by Led Zeppelin") was turned down too, as Alexa mishears enough with one slot. So "only" takes one slot, 24bit7 finds an artist you own in the words, and the AI chooses from that artist's tracks in the library, so nothing it picks can be missing.

**28 Oct 2026: A softer default green, and an accent colour with a full picker.**
The dark theme's #00ff41 looked right on the living room PC and glared on the bedroom laptop, which is probably closer to most screens, so the default became #7bd88f, picked from a mock-up on the laptop. Ben wanted the colour choosable too. A short list of presets was argued for, as a free picker allows unreadable colours; Ben chose the full picker (Windows' own colour dialog), with a preview under the setting so people choose carefully. To keep it safe, a colour too dark to read on the buttons is lightened, and one within 35 degrees of magenta is moved off it, as magenta stays the mark of anything that uses AI credits and isn't choosable. The logo's "bit" takes the opposite hue, or orange when that would be magenta (as it is for green). The console takes the accent in both themes; light mode is otherwise unchanged. It's saved in Profiles.

**29 Oct 2026: Your other copies of a song stand in when a filter leaves one out.**
datdude keeps many albums as a stereo MP3 and a surround FLAC, and his stereo zone's filter picks only from a smartlist of the MP3s. 24bit7 looked each song up as one copy, often the FLAC, so the filter left the song out though the MP3 would have passed. Where the filters or the hidden-track check turn a copy down, the other copies (same artist and title as tagged, live recordings kept apart) are tried in the usual order. Recently played counts any copy, since JRiver records plays per file and hearing the MP3 shouldn't let the FLAC straight back in.

**29 Oct 2026: Three more name rules, not fuzzy matching.**
datdude asked for fuzzy matching after "only ACDC" missed AC/DC. A pass over Ben's library showed the gaps were few and specific, so they got narrow rules: Only matches an artist's name with or without its gaps, apostrophes go without leaving a gap (straight and curly had compared differently, splitting Jane's Addiction in two), and a lone "n" is "and" (Guns N' Roses), after initials join up so N.W.A keeps its N. P!nk and deadmau5 were left until someone needs them.

**29 Oct 2026: A badge on screen while a voice request builds.**
datdude asked for something on screen while 24bit7 works, as from the couch in Theater View he couldn't tell a request still building from one Alexa had misheard, and Drift adding tracks later looked like a second build. A small badge sits top right on the main screen, on top of everything: what was asked, the zone, a moving dot (magenta while the AI chooses), then how many tracks went in or why none did, and a fade. He also asked for a custom icon or message; turned down, as everyone needs the same two things from it and it would add settings for styling. Voice only and no setting, as the console already shows the same at the desk. A trial on the media PC found it showed over Theater View but took focus when it opened, which would leave Theater View deaf to the remote, so it's shown without activating, lets clicks through and has no owner window (so it shows while 24bit7 is in the tray). 1.26.1 was held back and folded into this release so both went out together.

**30 Oct 2026: A line in the console when a new version is out, not an updater.**
Ben asked for a separate updater program in the zip that would download the latest release and carry the settings across. It would work, as a separate program can replace 24bit7's files where 24bit7 can't replace its own, but an unsigned program that downloads and replaces other programs is just what Windows Defender and SmartScreen distrust, signing costs money every year, and it was about a day's work. So 24bit7 asks GitHub's releases once at start-up, off the main thread, and when a newer version is out says so in the console with a link to the release page (only ever a 24bit7 release link). Up to date, offline or an odd answer: nothing said, and no setting. The updater can be built later if people still find the manual steps a chore.

**31 Oct 2026: Headliner, and with it buttons you own and zones with settings.**
Ben, listening to Zero 7: one artist's top tracks with the closest similar artists sneaking in their best track. Every third track is a guest, one track each, so the playlist length decides how many guests there are and there's no setting. A guest's track is the one the Similar Tracks sources most often play next to the headliner's own hits, so it suits the playlist rather than being their biggest hit; the AI and YouTube sit that step out, so a button that isn't magenta never spends credits. It started as a fifth fixed button, then as a split button with Headliner behind an arrow, and ended as the first ready-made button in a list the user owns. Mags argued against custom buttons (more code, more settings, a page per button to maintain); Ben had thought it through and wanted a button to be a whole recipe (kind, sources, playlist settings, filters, shortcut) that a voice phrase or a key can run, and said go. For the record, then built properly.
Buttons replaced the per-device settings that had grown under Voice Commands. A device isn't where a playlist lands: the Play tab, a shortcut and a Non-stop top-up all go to a zone, and two Echos in one room should behave the same. So the zone holds what a device used to: which button each phrase runs, its filters and a Non-stop switch, with Show and Default moved over from Other. The device keeps a name and a zone, and the zone's page says which devices ask there. Filters stopped naming devices and are ticked on buttons and zones instead; a build runs under both. Non-stop follows the button that built the playlist, found again by id, so a renamed button still owns its evening. The upgrade turns a device's own settings into a button its zone points to, so day one changes nothing. Output moved from the button row to the right of the Zone line, where it reads as "from here, to there", and the AI usage figure to the row with the Now Playing and Search tabs. Voice ("Zero 7 with friends") is left for later, as it needs a change to the Alexa skill.

**31 Oct 2026, evening: Playlists, configs and devices, after Ben saw buttons and zones running.**
Ben started the dev build at home and the design fell over in minutes: an upgrade had made "Sonos Similar Artists" buttons out of his Sonos device's own settings, Zones made no sense to him ("I can send to any zone from Output; devices are what have voice commands"), the Add Button dialog asked for a kind, a start and a name as three separate things, and More Options had lost Moderator, Drift, Deep Cuts and Non-stop. The redesign, worked through in conversation and seven mock-ups before any code:
One noun, playlist. A playlist is the thing you press, the thing with a page, the thing a device runs and the thing a shortcut fires; JRiver's are always "JRiver playlist". Settings > Playlists lists them with a tick each (ticked means on the Play tab, in list order), so a playlist a device runs can live off the row, and + on the Play tab offers the unticked ones and New. The New Playlist window asks one thing, what it should be like, because a kind without a start is a blank form and a start already has a kind. Hold a button to drag it, onto a cog or a cross that appear over the console, so moving and removing need no menu.
Devices, not zones. A device has voice commands; a zone is only where the music lands, and Output already picks that. Settings > Devices gives each Alexa device the playlist behind each phrase; Show, Default and Follow go back under Other, where they were. Zone filters and a zone's Non-stop switch go: filters belong to playlists, and a Non-stop top-up follows the playlist that built the music. The device-derived playlists from the upgrade start unticked, with a console note, so day one looks like yesterday.
Configs and Mix. Ben wanted Headliner and Inner Circle to be things a user could have built: a playlist is one or more configs (Artist Matching, Track Matching, Artist's Top Tracks or AI Playlist, the kinds' new names; the standard playlists keep their old names), and a Mix says how they come together (Shuffle, Append, or Alternate by a pattern) and which config Drift carries on from and Non-stop carries on as. The engine runs each config in turn under its own settings, the first sending as any playlist does and the rest adding behind it, then reorders what follows the current track; to YouTube or Tidal the woven list goes once. Headliner is two configs alternating two to one, and the Guests code went. The agreed plan had a Mix total with each config finding its share; built instead with each config's own count (the total is their sum), because a total would silently override the counts shown a few lines up and the shares would need a rule of their own for each kind. Ben to confirm or overrule.
More Options as live dials. The bar shows the Moderator, Drift, Deep Cuts and Non-stop of the playlist you last used, and changes stick to it; with the bar open the other playlists dim, one click arms another and shows its settings, a second builds. Ben's idea, from "the bar should show the settings of the button you're about to press", once we'd agreed the app can't know which that is.
Inner Circle. The seed's closest three to five artists (or tracks) make the circle, each one's own similar list is fetched, and only what two or more of those lists agree on goes in, after the circle itself: what the things near the seed are all near. With Seed on Playing Now the sampled artists or tracks are the circle. It stops short and says so rather than padding, and Drift fills in if it's on. Same-act neighbours are skipped by a narrow name rule (a whole name inside another, five letters or more), not fuzzy matching. Ben's design, tried on his library first: strict agreement found fourteen artists for Miles Davis and none for Radiohead, two of three found five to nineteen for every seed, so two of three is the default.

**1 Nov 2026: New is a blank slate, and the touches after Ben used the dev build.**

New under the Play tab's + made an Artist Matching playlist and let its page change the kind. Ben asked why New should choose a kind at all when From Template already offers all four, and the honest answer was that it shouldn't: New now makes a playlist with no config, its page opens on the name box, and + Add a Config says what it builds. The cost is an empty state (grey on the row, a console line and its page if pressed, skipped by Non-stop, voice and shortcuts), taken on because it makes New a different thing from a template: start empty and build it up. Removing a made playlist's last config takes it back to blank; a standard playlist keeps its own. From Existing lists every playlist rather than saying "every playlist is on there already": one that's off the row is added back, one that's on it gets Create Copy. The lists and Settings > Playlists mark the chosen row with a border in the accent colour rather than a fill, so it's plain which one Remove and the arrows act on. The dragged button never showed over the console because Tk clips a widget to its parent, so a drag image in a small borderless window follows the pointer while the button's slot stays dimmed and slides along the row as the pointer passes each button, the row re-flowing live; the drop keeps the order shown. The drop strip lost its caption and the pills their heavy outline (eleven point text, a one-pixel dashed line). The console keeps one More Options line, rewritten in place when another playlist is armed, instead of a line per click. Later the same day: the picks in both lists became rounded outlines (each row a small canvas), the lists sit on the field colour so they read as lists against the window, the app's own windows get rounded corners on Windows 10 too (a window region, since the Windows 11 corner attribute does nothing there, which is why Ben's media PC showed square ones), and a dragged window moves once per turn of the event loop with a repaint, so its contents keep up. That still smeared mid-drag, since Tk moves the frame and the contents repaint afterwards, so the prompt windows now hand the press to Windows as a title-bar drag (what the main window's chrome does) and Windows moves the whole window as one picture; the Tk move stays as the fallback elsewhere. In the Add window, Tab and Shift+Tab walk the three tabs and Up and Down work from the moment it opens, so the keyboard alone adds a playlist.

**1 Nov 2026, evening: nested playlists, and the live dials come off the bar.**

Ben's idea, grown from the split buttons agreed on 31 Oct: any playlist can be dragged onto another and nests under it, one level deep. The parent's button grows an arrow; its main part runs the default, which is the parent itself until a child is made the default, and then the face carries the child's name. A blank slate with children is a pure group, so "Similar" over Similar Artists, Similar Tracks and Inner Circle costs nothing new. A child's tick means it's in the menu; unticked, it's kept for voice and shortcuts as before. Stage one is the model: parent and default on a playlist, the stored list kept in tree order, moves within a level, a deleted parent's children freed. With that came the end of the live dials: a dial showing "the armed playlist's Drift" has no honest answer once a button can hold several playlists, so Moderator, Drift, Deep Cuts and Non-stop are each playlist's own again, on its page, and the Settings pill is the quick way there. The arming, the dimming and the one console line went with them; a click builds. Ben's call; the one he and I both half-miss is flipping Non-stop from the bar.

**2 Nov 2026: The playlists ship nested, from Ben's own set-up.**

The drop-down had a second take from Ben's screenshots first: one shape with the bar across and a black line before the arrow, the parent's own row first in its menu reading as its Alternate Title (a box on a parent's page), a green outline on the row under the pointer, and rows that drag out of the menu onto the row, into another parent or onto the Settings pill. Then, rather than design the shipped layout in chat, Ben arranged his dev copy the way he wanted a new user to find it and said "check what I've done, these are the defaults", so it was read off his database: Similar Artists (titled Artist Matching in its menu) over the standard Similar Tracks renamed Track Matching, Inner Circle and Headliner at twelve tracks; Artist's Top Tracks (titled Top 15, Random) over two new ready-mades, Top 10, Best First and Top 10, Best Last; AI Playlist alone. Three buttons, two with menus, where there had been six. It had to go into 1.29.0 rather than a later release because the upgrade that makes the playlists runs once per user. The upgrade keeps everyone's settings on the standard playlists except two: Artist's Top Tracks is set to fifteen tracks in random order. Keeping a user's own count and order and building the title from them was argued for; Ben chose the override so every screen matches the manual, and it is two boxes to put back, so it was built that way, for the record. Restore Default Playlists grew to match: it puts back anything shipped that's gone, under the playlist it came under, and moves nothing that's there, which needed each playlist to remember the recipe it was made as, since a renamed Headliner is still Headliner. The test world keeps the old flat row of six, as some seventy test lines assume it, and one test file runs the real arrangement; a fixture choice, said in conftest.
