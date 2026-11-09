# Multiroom in 24bit7: how it works (draft for the JRiver forum)

Draft by Mags, 9 Nov 2026, from the code on the dev branch (commits 1a to 2d). For Ben to read and cut before it
goes anywhere. Written in Ben's voice. Where something is untested or not built yet, it says so.

---

I've been working on getting a Sonos One and my main system (a Chord Hugo on the PC, over ASIO) to play the same
music in step, as an experimental feature of 24bit7. This is how it works, what it measured, and what it hasn't
been tested on. It's for people who know JRiver, DLNA and clocks, so it's precise rather than short.

## 1. How it works

JRiver plays to the Sonos exactly as it does today: a DLNA zone, one stream per track, with SetNext for the next
track so the Sonos plays gapless. In my set-up JRiver's DLNA server sends the Sonos 44.1 kHz 16-bit whatever the
file is. Nothing about that path changes.

The other room doesn't play from a JRiver zone at all while it follows. A small program that 24bit7 starts (the
"follower", its own process) fetches each track itself from a second JRiver DLNA server, called Multiroom, as a
plain HTTP request for `/Music/F<key>.wav` with byte ranges. That server is set to PCM 24-bit and has the main
system's DSP preset loaded, so the follower gets the processed audio at the file's own sample rate (a 192 kHz
file arrives as 24/192). The follower plays it to the DAC through PortAudio, ASIO by preference. JRiver's own zone
for that DAC is stopped while following, so the DAC is free.

The Sonos leads. The follower reads the Sonos's own playback position over its local control API (a websocket on
port 1443, `getPlaybackStatus`, `positionMillis`), about a hundred reads a second, and places every block of
samples it hands the DAC on that clock. It talks to JRiver only to learn which track is playing and which comes
next (MCWS `Playback/Info`), and to stop its own zone.

## 2. The clock check

Settings > Other > Multiroom has a Check Clock button. It reads the speaker's position for ten seconds while
something plays and reports four things: whether it answers at all, the median round trip, whether the position
is in milliseconds or whole seconds, and whether the counter moves one for one with the PC's clock (a least
squares slope over the ten seconds).

Green: a millisecond counter, slope within one per cent of 1.0; under 50 ms round trip is "Good", slower is
"usable". Amber: a whole-second counter that keeps time (it says the rooms may sit a few hundredths of a second
apart), or nothing was playing so it couldn't check. Red: no answer, or a slope more than one per cent off.

Two honest limits. The check is advisory: it doesn't gate anything. And today the only clock the follower can read
is the Sonos one; the "Generic" profile for other renderers (the UPnP whole-second position) is a name in the
profiles table, not working code, so a non-Sonos renderer can't be followed yet. What the check can't see is
whether the counter sits the same distance from the sound at each start, because software can't hear. That's what
the calibration recording is for (section 6).

## 3. The follower: how the DAC is held to the Sonos

There's no delay buffer and no resampling. The follower works out the moment the track's first sample leaves the
Sonos's speaker, O = C + Start − late, where C is the counter origin (the PC time at which `positionMillis` would
read zero), Start is a fixed offset for the speaker (90 ms on a Sonos One, measured with a microphone), and late
is how far the counter runs behind the sound in a given situation (0 at a fresh start, about 95 to 100 ms after a
jump or a gapless change, see sections 4 and 5). Each time the DAC asks for a block at PC time t, the follower
hands it the sample due to sound at t: (t − O) × rate + DAC delay, where the DAC delay is a fixed number of samples
for that DAC (1,660 on the Hugo: 38 ms at 44.1 kHz, 9 ms at 192). It seeks within the HTTP stream to get there.

The counter origin C is estimated from the reads as the second-lowest upper bound of (read time + round trip / 2 −
position), which on the Sonos holds to about 0.2 ms once a few reads are in. The first placement is refined two
seconds into a track.

## 4. Drift

The Sonos's clock and the DAC's clock differ by about 17 parts per million here, so left alone the rooms would be
a millisecond apart after a minute. Once a second the follower re-estimates C from the last two seconds of reads,
compares where the Sonos is with where the DAC has got to (counting the frames handed over against the DAC's
measured rate), and corrects the error by dropping or repeating single sample frames, at the point in each block
where the waveform changes least. Inside a 1 ms dead band nothing is done; up to 20 ms the correction rate is 50
ppm per millisecond of error, capped at 300 ppm, so a few samples a second at most; beyond 20 ms it moves straight
to the right place. Between corrections the samples are bit-perfect. There's no resampler.

## 5. Track changes

Twenty seconds before a track ends the follower asks JRiver what's next (`NextFileKey`, or the zone's playlist)
and opens it. If the next track has the same sample rate and channels, it chains into it in the same DAC stream
with no gap, moving its origin on by exactly the old track's length. If the rate changes, the DAC stream is
reopened at the new rate and placed where the old track's sound ended.

The Sonos itself, on a gapless change, restarts its counter about 100 ms before its sound actually changes track
(measured at 100.3 to 100.8 ms over seven changes with a microphone, and 98 to 100 in tonight's console logs). So
at every change the follower measures where the new counter started against where the old track's sound ended:
within −30 to +250 ms it treats the change as gapless and keeps the sound continuous; outside that it treats it as
a real gap and follows the counter. In short: a gapless album stays gapless on the main system if the Sonos plays
it gapless, and the two rooms stay in step across the join. Heard in step tonight at 48→44.1, 192→44.1 and
44.1→192 kHz changes, and at same-rate changes.

Two other rules from today's listening: JRiver's `Playback/Info` can name the old track for up to six seconds
after the Sonos has moved on, so the follower trusts the next track it was given earlier rather than JRiver's
name; and a pause anywhere (JRiver, the Sonos app, the button on the Sonos) stops both rooms, because a resume
leaves the Sonos's counter an unknown distance from its sound. Play then starts the track from the top in both
rooms, which has been in step every time.

## 6. Calibration

Not built yet. This is stage three of the plan, and I'm not going to describe what it does until it exists. What
ships now: a profile per known speaker and DAC (Sonos One: Start 90 ms, Resume 95 ms; Chord Hugo over ASIO: 1,660
samples), the three numbers on screen to type over, and Nudge buttons that move Start by 5 ms while music plays so
you can set it by ear.

What I can say about the planned method, since the measurements behind it are done: the numbers were found with a
phone voice recording of click tracks played by each room in turn, decoded (m4a, via Windows Media Foundation) and
fitted. The offsets are properties of the kit, not of a session: on the millisecond clock the Sonos's start offset
repeated within about 5 ms across three fresh starts on the same day, and the DAC delay is fixed in samples. So
the intent is no redo after a restart or reboot, only after a change of DAC, driver settings or DSP. Whether the
offsets hold across days hasn't been measured.

## 7. Results so far

Measured with a microphone (9 Nov 2026, one day): the Sonos start offset constant to about 5 ms across three
runs; ten fresh ASIO starts within 1 to 4 ms of each other in each run; gapless counter offset 100.3 to 100.8 ms
over five changes; after a jump 94 to 100 ms over three jumps; sample-rate dependence fully explained by a fixed
1,660-sample DAC delay (two rounds at five rates within about 2 ms).

By ear (the same day, no microphone): fresh starts, three mid-track joins, four jumps, five track changes
including two rate changes, two stop-and-restart cycles and one skip, all judged in step by me in the room. The
longest continuous stretch listened to was a few tracks, not hours. Every listen started the follower fresh. There
is no multi-hour or multi-day data yet, and nothing from a cold boot of the PC.

## 8. Requirements and limits

- JRiver Media Center 36 is what it was tested on, with Media Network on. It uses MCWS and a second DLNA server.
- A DLNA server called Multiroom with Format PCM 24-bit, and the main system's DSP saved as a preset and loaded
  into that server's DSP Studio (JRiver keeps the two separate, so a DSP change means loading the preset again).
  There's no MCWS call for server settings, so these two steps are by hand.
- The follower zone's DAC is driven through PortAudio with ASIO; it holds the device exclusively while following,
  and 24bit7 stops that zone in JRiver first. WASAPI is listed but untested.
- Hi-res: the Sonos gets whatever JRiver's DLNA server sends it (44.1/16 here). The main system gets the file at
  its own rate and 24-bit from the Multiroom server. The two rooms play different renderings of the same track.
- A Sonos group made in the Sonos app: untested. The follower reads one player's clock.
- Wired versus Wi-Fi: my Sonos is on Wi-Fi with round trips of about 4 ms; nothing else measured.
- Windows only, like the rest of 24bit7.
- Planned for 24bit7 1.32.0, marked experimental.

## 9. Tested set-up

Windows 10 Home (19045), JRiver Media Center 36, Sonos One (model S13, software 97.2), Chord Hugo over "ASIO Chord
1.04", 24bit7 from the dev branch, Python 3.14 in development. Tracks at 44.1, 48 and 192 kHz, FLAC.

## 10. Where it lives and what you do

Settings > Other > Multiroom: tick Enable Multiroom; pick Leader (the zone that plays to the Sonos) and Follower
(the zone whose DAC follows); the Speaker row shows what was found on the network with Check Clock beside it;
Plays Through shows the matched ASIO device; DLNA Server names the server; under Adjustments are Start, Resume,
DAC Delay and Nudge; Calibrate is greyed until stage three.

Play tab: Output gains Multiroom. A build sent with it goes to the leader zone and the follower starts; so does
leaving Output on Multiroom when 24bit7 opens, if the Sonos is playing. Zone gains a Multiroom entry that shows
the leader's track and is picked by itself when the follower starts. The Now Playing row has Stop (both rooms),
which becomes Clear Playing Now once stopped, and Skip Track.

By voice through needle drop: "multiroom" (the main system joins what the Sonos is playing), "single room" (the
music stays in the room of the Echo that heard it: said by the main system, the music hands over to it and the
Sonos stops; said in the Sonos's room, the main system drops out), and "switch" as before.

If the renderer fails Check Clock, the verdict shows in red under the Speaker row and says why. Today, with no
Sonos found, the follower doesn't start and the console says "No Sonos found on the network."

## What I'd like others to test

- Other Sonos models, and a Sonos group formed in the Sonos app.
- A Sonos on Ethernet rather than Wi-Fi: does Check Clock's round trip change, does anything else?
- Other DACs over ASIO, and anyone brave enough to try WASAPI, with the DAC delay they end up at.
- Long sessions: an hour or more without a track change, and whether the drift correction stays inaudible.
- 48 kHz and 96 kHz material through the whole chain.
- Another JRiver version.
