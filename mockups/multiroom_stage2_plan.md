# Multiroom, stage two: the follower inside 24bit7

Plan for Ben's go-ahead. Mags, Monday 9 November 2026, evening. The design it belongs to is `mockups\multiroom_design.html`;
stage one is `mockups\multiroom_stage1_plan.md` (built and committed on dev, last commit a938d4b). The new screen is
mocked up in `mockups\now_playing_buttons.html` (picture: `now_playing_buttons.jpg`); the settings section is drawn in the
design page.

## What stage two is

The follower from stage one becomes part of 24bit7. Output on the Play tab gains **Multiroom**: a build goes to the
Sonos as now, and the Speakers follow it. The follower runs as a child process the app starts and stops, and its lines
appear in the console. Settings > Other gains the **Multiroom** section: the two zones, what was found (speaker, DAC,
DLNA server), the three adjustments and Check Clock. The Now Playing row gains **Stop** (then **Clear Playing Now**)
and **Skip Track**, for any zone. needle drop learns **"multiroom"** and **"single room"**, beside the existing **"switch"**. The packaged
build carries all of it.

**Done means:** from the Play tab, with Output on Multiroom, a Similar Artists build plays in both rooms in step, through
a change of track and a Stop and play from the top; the follower's lines are in the console; the section, the buttons
and the voice commands do what this plan says; the windowless tests pass against fakes and the window tests pass for
the two screens; `build.bat` packs it and the packed exe follows.

## What tonight's listens changed from the design

- **No "Pausing one room pauses both" tick.** A pause, anywhere, stops both rooms, and play starts the track from the
  top (DECISIONS, 9 Nov evening). The tick and the "Speakers carry on alone" rule go from the design.
- **Stop and Skip are 24bit7's own controls.** Multiroom is a 24bit7 feature, so its play, stop and skip belong on the
  Play tab and in needle drop, with JRiver's bar and the Sonos app coped with rather than designed around.
- **Skip keeps one look.** No greying in multiroom: the follower handles a skip itself (DECISIONS, 9 Nov late).

## Files

| File | What it holds |
|---|---|
| `multiroom\service.py` (new) | The child's side. `main(argv)`: opens a local socket on 127.0.0.1 at a port the app passes, reads JSON lines (`start` with the zones, server, device and numbers; `stop`; `nudge`; `status`), runs a `Follower` with `say` sending lines back as JSON, and exits when the socket closes, so it can't outlive the app. Nothing printed: a windowed exe has no stdout. |
| `multiroom\link.py` (new) | The app's side. `Link.start()` spawns the child (`[sys.executable, "--follow", "--port", n]` when frozen; `[py, "-m", "multiroom.service", ...]` in the repo), connects, and forwards each line to the console as `Multiroom: ...` through `engine.print`. `stop()` tells the child to finish and waits briefly. If the child dies while wanted it is started once more with a line; a second death is a problem line. `state` for the screens. |
| `multiroom\profiles.py` (new) | Two small tables. Speakers keyed on the DLNA description's maker and model: Sonos One (Start 90, Resume 95, clock: Sonos websocket); everything else Generic (the UPnP whole-second clock, marked untested; stage two builds the entry and the pre-test's verdict, not the Generic clock itself). DACs keyed on a word of JRiver's device name matched to the ASIO driver's: Chord Hugo over ASIO, 1,660 samples; everything else 0. `pick_speaker(desc)`, `pick_dac(name)`. |
| `multiroom\clockcheck.py` (new) | Check Clock: ten seconds of reads while the leader plays. Reports whether it answers, the round trip, milliseconds or whole seconds, and whether the counter moves one for one with the PC's clock. Green, amber or red with one sentence. |
| `multiroom\follower.py` | `main()` keeps the command line for the bench; its prints become `say`. A `Nudge` hook moves Start by five milliseconds while music plays. |
| `gui.pyw` | `--follow` on the command line runs `multiroom.service.main()` before Tk is imported (the only argv flag today is `--tray`). Output gains "Multiroom" when the section is enabled (`_extra_outputs`, `_output_label`, `_on_output_changed` with `OUTPUT_TARGET=multiroom`). After a build is sent to the leader zone with Output on Multiroom, `link.start()`. The Now Playing row gains the three buttons with their hover notes in `PLAY_NOTES`. `quit_app` stops the link. |
| `engine.py` | `OUTPUT_TARGET` accepts `multiroom`: `output_zone` sends to the leader zone; `output_streaming` is None. `MULTIROOM_*` settings in `load_settings`. Three small calls the buttons and voice share: `stop_zone(zone)`, `clear_playing_now(zone)`, `skip_track(zone)` (records the skip as a voice skip does). |
| `settings_gui.py` | `_build_multiroom(tab)` under Zones in Other, the section from the design page minus the tick; its keys in `_current_updates`; Check Clock on a thread. |
| `voice.py`, `alexa\lambda_function.py`, `alexa\interaction_model.json` | `MultiroomIntent` ("multiroom", "multi room", "play multiroom") and `SingleRoomIntent` ("single room", "play single room"). Ben's words (9 Nov): the three room commands are Switch, Multiroom and Single Room. Stop, pause and skip keep their words. |
| `tests\` | `test_multiroom_link.py` (a fake child on a thread: lines reach the console queue; a dead child is restarted once), `test_multiroom_profiles.py`, `test_clock_check.py` (fake Sonos reads), `test_output_multiroom.py` (windowless: a build with Output on Multiroom goes to the leader zone and starts the link), `test_voice_multiroom.py` (windowless), `test_now_playing_buttons.py` and `test_settings_multiroom.py` (windows). |
| `docs\MANUAL.md`, `docs\HANDBUCH.md`, `locale\de.json`, `README.md`, `release_notes\v1.32.0.md`, `DECISIONS.md`, `screenshots.py` | Stage 2e. |

`build.bat` needs no new flags: the dry pack (1d) showed numpy, sounddevice with its ASIO DLL and websockets all pack
once `gui.pyw` imports `multiroom`, which the `--follow` dispatch does.

## How the pieces talk

    24bit7 (Tk)  ──spawn──▶  24bit7.exe --follow          ◀── Sonos clock, 100 reads a second
        │                         │  Follower                 ◀── Multiroom DLNA server, HTTP ranges
        │  127.0.0.1 socket,      │                           ──▶ Hugo, ASIO
        │  JSON lines             │
        ◀── "Nine Million Bicycles: 44.1 kHz, straight on from the last track; the Sonos's counter is 100 ms behind."

The child is its own process because at 192 kHz the DAC asks for samples every five milliseconds and a Tk window with a
build running can't promise that. The child holds the socket open; if the app goes, the socket closes and the child
finishes the Speakers and exits. If the child goes, the app and the Sonos carry on.

## When the follower runs

| When | What happens |
|---|---|
| Output set to Multiroom and a build is sent to the leader zone | The tracks go to the Sonos as now; then `link.start()`. The child stops the Speakers zone in JRiver if it's playing (the DAC must be free), finds the Sonos and the server, and the Speakers join within about half a second of the Sonos's first note, or mid-track if it was already playing. Console: `Multiroom: Speakers following Sonos (Kitchen, Chord Hugo over ASIO).` |
| Output left on Multiroom when 24bit7 opens, and the leader zone is playing | The link starts and the Speakers join mid-track (rule 5: three joins in step). Decision D3. |
| "multiroom" by voice | `link.start()`; joins what's playing. "Nothing's playing on the Sonos." if nothing is. |
| The Sonos stops, or the list ends | The Speakers stop; the child stays, idle, and the Speakers rejoin when the Sonos plays again. |
| Output changed away from Multiroom, "single room", or 24bit7 quits | `link.stop()`: the Speakers stop and the child exits. "Single room" said in the Speakers' room also stops the Sonos zone, so that room alone keeps the music; said in the Sonos's room the Speakers just drop out. Moving the music to the other room is "switch", as now. |
| The Multiroom server isn't there, or no Sonos answers | A problem line with the set-up steps, and the Speakers stay silent. No silent fall-back to the Sonos server (16-bit, no DSP). |

The follower's own rules (pause stops both rooms, a resumed track is sat out, changes placed on the Sonos's change, a
skip waits for JRiver's name) are stage one's and don't change here.

## The Now Playing row

**Zone gains a Multiroom entry** (Ben, 9 Nov, after the 2a listen: Now Playing sat on Speakers, which showed
nothing). It reads the leader zone, named by Leader under Settings, so the row shows what the Sonos is playing, and
Now Playing switches to it by itself when the Speakers start following. Seeds and builds from it go to the leader.

From the mock-up. Two FlatButtons between the track text and Output, for whichever zone Now Playing shows:

- **Stop**, amber text and edge (the console's note amber, `#ffb000`, becomes a palette entry so the app has one amber):
  `Playback/Stop` on the zone. In multiroom the follower sees the Sonos stop and stops the Speakers too.
- Once the zone is stopped the same button reads **Clear Playing Now** in red (the console's problem red, `#ff6b6b`):
  `Playback/ClearPlaylist`. One click, no confirmation (Ben, 9 Nov). It reads Stop again as soon as the zone plays.
- **Skip Track**: `Playback/Next`, and the skip is recorded as a voice skip is, so the Skipped Tracks filter sees it
  (decision D4). Greyed while the zone is stopped or nothing follows the current track (`NextFileKey` is −1).
- The state comes from the Now Playing refresh (ten seconds) plus a refresh straight after a click.
- Hover notes, shown while the Play tab's ? is on: "Stop: stops this zone. In multiroom, both rooms." "Clear Playing
  Now: empties this zone's list." "Skip Track: the next track in this zone's list."
- FlatButton's `armed=<colour>` already draws a two-pixel edge with the text in that colour, which is the look.

## Settings > Other > Multiroom

The section drawn in the design page, under Zones, minus the tick. Off by default; ticking Enable Multiroom is what
puts Multiroom in the Output list, as Additional Outputs does for YouTube and Tidal.

| Row | Shows | Key |
|---|---|---|
| Enable Multiroom | tick | `MULTIROOM_ENABLED` |
| Leader | zone list | `MULTIROOM_LEADER` (Sonos) |
| Speaker | found on the network: room and model, profile; Check Clock button and its verdict line; a room picker only when more than one Sonos answers | `MULTIROOM_SPEAKER` (room, blank = the only one) |
| Follower | zone list | `MULTIROOM_FOLLOWER` (Speakers) |
| Plays through | the ASIO device matched from JRiver's device for the follower zone, profile; Change only if nothing matched | `MULTIROOM_DEVICE` (blank = matched) |
| DLNA server | found by name; ? opens the two JRiver set-up steps; "serving 24-bit, 96 kHz" from a track header | `MULTIROOM_SERVER` (Multiroom) |
| Adjustments | Start, Resume, DAC delay, Nudge −5 / +5 | `MULTIROOM_START` (90), `MULTIROOM_RESUME` (95), `MULTIROOM_DAC` (1660) |
| the line under them | "From the Sonos One and Chord Hugo profiles." / "Typed by hand." / later "From your recording of ..." | `MULTIROOM_FROM` |
| Calibrate... | greyed, "stage three" in its hover note | |

Not in Profiles: these describe the kit, like Zones and Keys, not how a build behaves (decision D2). `OUTPUT_TARGET`
is in Profiles already and may hold `multiroom`; a profile applied on a PC without the section enabled falls back to
Same zone, as an unticked YouTube does.

## Voice

| Said | What happens | Alexa says |
|---|---|---|
| "ask needle drop multiroom" | `link.start()`; the Speakers join what the Sonos is playing. | "Multiroom." / "Nothing's playing on the Sonos." |
| "ask needle drop single room" | Collapses to the room of the smart speaker that heard it (its zone under Settings > Devices). In the Speakers' room: `link.stop()`, the Sonos stops. In the Sonos's room: `link.stop()`, so the Speakers drop out. | "Just the Lounge." / "Just the Kitchen." |
| "ask needle drop to switch" | As now: the Switch To handover from this room's zone to the other. | as now |
| "stop", "pause" | As now: the device's zone stops or pauses. In multiroom the follower makes a pause a stop, so both rooms stop (decision D1). | "Stop." / "Pause." |
| "skip" | As now, `Playback/Next` on the device's zone; the follower starts the new track in step. | "Skipped." |

Two intents in `interaction_model.json`, two entries in the lambda's `ZONE_INTENTS`, two names in `voice.py`'s
`INTENTS` and `SAID`, the help text; the JSON and lambda pasted into the Amazon console once, as for 1.31.0. Alexa
stays English.

## Sub-stages

| | Lands | Listen |
|---|---|---|
| 2a | `--follow`, `service.py`, `link.py`, Output "Multiroom", `OUTPUT_TARGET=multiroom` in the engine, the start and stop rules, console lines, `quit_app`. The section isn't built yet, so the zones and numbers come from `.env` keys set by hand. | Yes: a Similar Artists build from the Play tab with Output on Multiroom, both rooms, through one change of track. |
| 2b | The Settings section, `profiles.py`, `clockcheck.py`, the DLNA server check. | No (Check Clock reads, plays nothing). |
| 2c | The Now Playing buttons, from the mock-up. | Yes: Stop, play, Skip Track from the app, both rooms. |
| 2d | Voice: the two intents, lambda and JSON for Ben to paste. | Yes, by voice, when Ben's at home. |
| 2e | Manual (both), German, screenshots (play tab, settings_other), README What's new, release notes 1.32.0, DECISIONS. | No. |

Each sub-stage: built, its tests green, shown to Ben, then committed on dev with his say-so. Standard build at the end,
since the screens change.

## Decisions for Ben

- **D1. "Stop" by voice in the Sonos's room.** The design (13:00) said the music hands over to the Speakers and the Sonos
  stops. Tonight's rule says a stop or pause stops both rooms. I'd keep both rooms stopping: "stop" means stop,
  "switch" is the handover and "single room" the collapse. Your call.
- **D2. Multiroom settings stay out of Profiles.** They describe the kit, not a build. Recommend out.
- **D3. Joining at start-up.** Output left on Multiroom and the Sonos playing when 24bit7 opens: start the follower
  and join mid-track. Recommend yes.
- **D4. Skip Track counts for the Skipped Tracks filter**, as a voice skip does. Recommend yes.
- **D5. Version 1.32.0**, a feature release, after stage two; stage three (calibration) and anything from Generic
  speakers come later.

## Not in stage two

Calibration and the test tracks (stage three). The Generic clock beyond the pre-test's verdict. WASAPI (listed in Plays
through as untested). More than one follower. A volume control for the follower. "Multiroom" starting a build
from nothing.

Model: this plan was written on Fable. The build can run on Opus or Fable; Ben's call per sub-stage.
