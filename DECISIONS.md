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
