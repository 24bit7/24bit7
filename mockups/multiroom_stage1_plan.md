# Multiroom, stage one: the follower on its own

Plan for Ben's go-ahead. Mags, Monday 9 November 2026, 13:30. The design it belongs to is `mockups\multiroom_design.html`.
The measurements it rests on are in `Documents\24bit7 sync test` and in the memory file for this project.

## What stage one is

A program that, told the leader zone (Sonos), the follower zone (Speakers) and the three numbers, plays what the Sonos
plays on the Speakers' DAC in step, from the command line, printing console lines. No settings screen, no voice, no
profiles, no calibration yet: those are stages two and three. The numbers are flags, with Ben's as defaults
(Start 93 ms, Resume 95 ms, DAC 1,660 samples).

**Done means:** Ben hears a run through Indie-Chill (starts, gapless and gapped changes, jumps, a pause at the speaker and
one through JRiver) in step, with no shift at track changes; and the windowless tests pass against fakes.

    py -m multiroom.follower --leader Sonos --follower Speakers [--server Multiroom] [--start 93] [--resume 95] [--dac 1660] [--pause-both]

## Files

| File | What it holds |
|---|---|
| `multiroom\sonos.py` | Finding the Sonos (SSDP for ZonePlayer, then `http://ip:1400/info` for household and group); `SonosClock`: one websocket to `wss://ip:1443/websocket/api`, `getPlaybackStatus` about a hundred times a second on a thread, keeping (our time, round trip, positionMillis, state). Gives `origin()` (the median of the twenty quickest reads in the last two seconds), `first_origin_after(t)`, `state`, `last_read_age`. |
| `multiroom\fetch.py` | `find_server(name)`: SSDP for MediaServers, the one whose friendly name contains the name, looked up at every start since JRiver renumbers ports. `TrackStream(url, from_sample)`: a thread doing HTTP range reads into a ring buffer of float32 blocks, up to thirty seconds ahead; parses the WAV header (rate, channels, bits, data offset); `read(n)`, `seek(sample)` (drops the buffer, new range request). |
| `multiroom\output.py` | `Output(device_name, rate, callback)`: a PortAudio output stream (`SD_ENABLE_ASIO=1` set before sounddevice is imported), matched by a substring of the device name, ASIO devices first. `FakeOutput`: the same interface driven by a simulated clock, recording which sample index was handed over at which simulated time. |
| `multiroom\follower.py` | `Follower`: the state machine below, with the clock, the fetcher, the output class, the time source and the MCWS session all injectable. `main()`: the command line. Console lines go through a callback, as engine.py does, so stage two can route them to the app. |
| `multiroom\mcws.py` | The few MCWS calls the follower makes: `Playback/Info` for the leader zone (State, FileKey, NextFileKey, PositionMS), `Playback/Stop` on the follower zone, `Configuration/Audio/GetDevice` for the follower zone's DAC name. Reads `JRIVER_HOST`, user and password the way `engine.settings` does. |
| `tests\fake_sonos.py` | A websocket server speaking the same protocol, with a simulated counter: configurable read latency, lateness after a resume (default 95 ms), pause and play, jumps, track changes with a counter gap. |
| `tests\fake_dlna.py` | An HTTP server that serves WAV with `Range`, generating a known signal (a sample's value encodes its index) so a test can tell exactly which sample the follower handed over when. |
| `tests\fakes.py` | `FakeJRiver` gains `NextFileKey` in `Playback/Info` and `Configuration/Audio/GetDevice`. |
| `tests\test_sonos_clock.py`, `tests\test_fetch.py`, `tests\test_follower.py` | The guard tests, all windowless. |
| `requirements.txt` | numpy, sounddevice, websockets. `build.bat` gets hidden imports only if a dry PyInstaller run shows they're needed. |

## The rules, each with a test

Terms: **C** is the counter origin, our-clock time at which the Sonos's positionMillis would read zero, from the
clock reads. **O** is the sound origin, our-clock time at which the first sample left the Sonos's speaker.
**late** is 0 after a fresh start and Resume after a resume. Then **O = C + Start − late**. The follower hands
sample *i* of a track to the DAC at **O + i/rate − DAC/rate**, so it leaves the Hugo at O + i/rate.

1. **Placement.** At a stream's first callback, at our time *now*, the sample to hand over is
   `i0 = round((now − O) × rate) + DAC`. From then on *i* advances by the block, on the Hugo's own clock.
   Test: with a fake clock and a fake output, every handed-over sample is within half a millisecond of where the
   rule says, at 44.1 and at 192.
2. **Fresh start.** On the leader zone's FileKey changing (or at the start), the first clock read of the new track
   places the stream (O = C + Start, late 0). Two seconds in, the twenty-quickest origin refines C; the difference
   feeds the drift rule (today's data: under 2 ms).
   Test: a fake first read 1.5 ms off the steady value is pulled in by the slew, never jumped.
3. **Gapless or gapped.** With *E* the previous track's sound end (O + length), the new track's
   `d = C' − E + Start`. If 80 ≤ d ≤ 120 ms the sound ran straight on: keep playing through into the next track
   with no new placement (O' = E, late = Resume). Otherwise it's a fresh start after a real gap (O' = C' + Start,
   late 0); the Speakers go quiet for the same gap. The next track's WAV is fetched as soon as NextFileKey names it.
   Test: a fake change with d = 100 continues sample-exact; d = 260 restarts 260 ms later. The real numbers from
   today (five gapless, two gapped) are the cases.
4. **Jumps.** A counter jump of more than 300 ms between reads, or a change of PositionMS from JRiver that the
   counter confirms, re-places the stream from the new position with late = Resume, after a range seek.
   Test: a fake jump lands within half a millisecond of C' + Start − Resume.
5. **Drift.** Once a second, `e` = where the Sonos's sound is minus where the Hugo's is, in ms. Under 1 ms: nothing.
   1 to 20 ms: resample by `1 + clamp(e × 20 ppm per ms, ±300 ppm)` with linear interpolation per block, so 20 ms is
   taken up in about a minute and nothing clicks. Over 20 ms: jump at the next quiet block (RMS under −50 dBFS), or
   after two seconds with a 20 ms crossfade.
   Test: a fake clock running 30 ppm fast keeps |e| under 1.5 ms over a simulated ten minutes; a 40 ms error is
   jumped at a quiet block.
6. **Who paused.** If the Sonos reports paused while JRiver still says playing for a second or more, it was paused
   at the speaker: the follower keeps playing on its own clock through the leader zone's playlist (NextFileKey),
   says so once, and when the Sonos resumes it rejoins the clock at the next track boundary. If JRiver says paused
   first, both pause; on resume the stream is re-placed as a jump (late = Resume) and the first listen measures
   whether that's right. `--pause-both` makes a pause at the speaker pause the follower too.
   Test: both orders against the fakes, and the flag.
7. **Fetching.** Thirty seconds ahead. An empty buffer gives silence and one console line; the stream carries on
   when data arrives, still placed, so nothing drifts.
   Test: a fake server that stalls for two seconds.
8. **Losing the clock.** No read for five seconds: free-run on the Hugo's crystal, one console line. Sixty seconds:
   stop the Speakers, one line. Reads back: pick up the clock again through the drift rule.
   Test: a fake that goes quiet.
9. **The leader stops.** Sonos idle and JRiver stopped: the Speakers stop. The follower keeps watching, and the
   next play on the Sonos starts it again (the command-line version runs until Ctrl+C).
10. **Starting.** Stop the follower zone in JRiver if it's playing, so the DAC is free. Open the DAC at the track's
    rate; a new rate means a new stream, and a gapless change to a different rate takes the short break the DAC
    needs to relock. Never ask the server for anything but what it serves (the server decides the format).

## Sub-steps

| | What | Sound? |
|---|---|---|
| 1a | `sonos.py`, `fetch.py`, `mcws.py`, the fakes, their tests. | No. |
| 1b | `follower.py` with rules 1, 2, 7 and 10 and the command line. One track on the real Sonos zone. | Yes: a listen, asked for separately. |
| 1c | Rules 3 to 6, 8 and 9 with their tests. The Indie-Chill run, plus one pause at the speaker and one through JRiver. | Yes: the done listen, asked for separately. |
| 1d | A dry PyInstaller build into a temp folder to prove numpy, sounddevice (its PortAudio DLL) and websockets pack. Nothing published. | No. |

Model: this plan was written on Fable; the build runs on Opus, as agreed.

## Not in stage one

The Output entry, the settings section, profiles, the clock pre-test, calibration, voice, `24bit7.exe --follow`
and the local socket (the command line stands in for the app until stage two), the manual.

## Things the first listens will settle

- Pause and resume through JRiver: is it a resume (late 95) or a fresh start?
- How soon after the Sonos's first note the Speakers can join at a fresh start (today: about a third of a second).
- Whether a gapless change between tracks of different rates is clean enough, or wants the follower to resample
  the second track to the first's rate instead of reopening the DAC.
