# Multiroom, stage three: calibration from a phone recording

Plan for Ben's go-ahead. Mags, Monday 9 November 2026, late evening. Design: `mockups\multiroom_design.html`
(Calibration); the measurements it rests on are the sync-folder scripts of 4 to 9 Nov (`clicks.py`, `fit3.py`,
`asio_starts.py`, `rates.py`, `jumps.py`) and the Media Foundation decode (`m4a_to_wav.ps1`). Ben's call, 9 Nov
22:45: the 1.32.0 release waits for this, since other people can't test Multiroom without it.

## What stage three is

The Calibrate button under Settings > Other > Multiroom comes alive. One phone recording of about three minutes,
made where you listen, gives the three numbers for your kit: **Start** (how far the speaker's sound runs behind
its counter at a fresh start), **Resume** (the same after a jump) and the **DAC delay** in samples, plus whether
two fresh starts agree. The numbers are saved with "From your recording of 10 Nov 2026" under them, and a line to
copy for the forum.

**Done means:** Ben records a run on his phone, loads it, and the dialog gives numbers that agree with the
profiles within a few milliseconds and fifty samples and says the two starts repeat; the solver's tests pass on
made-up recordings with known offsets; a spoiled recording is refused with a plain reason.

## How a run works

Both rooms play through the whole run, each at its own pitch, so the recording tells them apart by filter as
`fit3.py` does: the Sonos plays a 1 kHz click track, the DAC plays 3.5 kHz clicks. The clicks fall at the uneven
gaps of `clicks.click_times()` (seed 247), so the pattern lines up with itself only at zero shift.

| Passage | What happens | What it measures |
|---|---|---|
| 1. Fresh start | JRiver plays the click track to the leader zone from the top. The follower's child places its 44.1 kHz clicks on the Sonos's clock with the numbers as they are now. | The residual r1 = the error in Start plus the DAC delay's error at 44.1 kHz. |
| 2. Jump | JRiver jumps the leader zone forward within the track; the follower follows with Resume. | r2 − r1 = the error in Resume. |
| 3. Stop and start again | JRiver stops the zone and plays the track from the top; the follower starts afresh. | r3 against r1: do fresh starts repeat? |
| 4. New rate | The follower reopens the DAC at 192 kHz and keeps placing clicks; the Sonos carries on. | r4 − r1 = the DAC delay's error, since a delay in samples is 38 ms at 44.1 kHz and 9 ms at 192. |

About forty seconds a passage. The follower's part runs in its child process, where the ASIO code already lives,
on a new `calibrate` command: it plays generated clicks instead of fetched music, with the same placement rule
(O = C + Start − late, the sample due now is (now − O) × rate + DAC). The app drives JRiver (`PlayByFilename`,
`Position`, `Stop`, `Play`) and writes a small log of the run: when each passage began, at what rate, with what
numbers. The solver reads the log beside the recording.

The Sonos's click track is a WAV made on the fly into 24bit7's folder (three minutes at 44.1 kHz, about thirty
megabytes), played with `Playback/PlayByFilename`, which imports it into JRiver's library; the run ends by
taking it out again with `File/Delete` in its library-only mode, checked on 9 Nov to leave the file alone.

## The recording

Step 1 of the dialog says: sit where you usually listen, both rooms on, start a voice recording on your phone.
Step 2: Play Test Sound. Step 3: get the recording onto the PC (Drive, email, a cable) and Load Recording... A
WAV is read directly; anything else (m4a from a phone, mp3, FLAC) goes through Windows Media Foundation to a
16-bit mono 44.1 kHz WAV, with the PowerShell script shipped in the app, no ffmpeg. The recording never leaves
the PC.

## The solver (`multiroom\calibrate.py`)

From `fit3.py`: band-pass each room's pitch, find the Sonos's pattern by correlating onset rises with the click
train, refine with peak-based onsets, then take each Speakers click as the loudest burst in its band near where
it's due (a click's sharp front leaks into the other band, so first crossings misread by about 7 ms). Per
passage: the median gap Speakers minus Sonos and its scatter. Then:

- Start += r1 − (DAC correction at 44.1 kHz), Resume += r2 − r1 applied the same way, DAC delay from
  (r4 − r1) / (1/44100 − 1/192000) in samples, repeatability = |r3 − r1|.
- It refuses, with the reason, when a room's clicks are fainter than three times the background, when fewer than
  half the clicks of a passage are found, or when the scatter within a passage is over 5 ms (noise, or a phone
  too far from one room). The dialog then says what to change and asks for another go.
- The forum line: "Multiroom calibration: Sonos One, Chord Hugo (ASIO), Start 91 ms, Resume 96 ms, DAC 1,655
  samples, starts within 3 ms, 10 Nov 2026."

Tests: made-up recordings with two pitched click trains, given offsets per passage, a little echo and noise, as
`clicks.selftest2` does; the solver must give the offsets back within 2 ms and the DAC delay within 50 samples,
flag a 60 ms repeat wobble, and refuse a recording with one room too faint. Windowless, no hardware.

## The dialog

The design's Calibrate Multiroom window: the three steps, **Play Test Sound** (greyed until Multiroom is on and
the follower's kit was found), **Load Recording...**, the result line in green ("Calibrated. Sonos 91 ms, DAC
1,655 samples, resume 96 ms. Starts repeat within 3 ms."), **Use These Numbers** (saves `MULTIROOM_START`,
`MULTIROOM_RESUME`, `MULTIROOM_DAC`, `MULTIROOM_FROM=recording:10 Nov 2026`), and **Copy a Line for the Forum**.
A refused recording shows the reason in amber with what to change. "Last time" under it from `MULTIROOM_FROM`.

## Sub-stages

| | Lands | Needs Ben |
|---|---|---|
| 3a | The click track and the child's `calibrate` command; the run driver in the app with its log; the decode (WAV direct, the rest through Media Foundation). Tests: the click track's times, the run's log, the decode on a short m4a made for the test. | A dry run with no phone, to hear the clicks in both rooms. |
| 3b | The solver with its made-up recordings. | No. |
| 3c | The dialog, saving, the forum line, German. | A look at the window. |
| 3d | A real calibration: Ben records a run, loads it, the numbers come out; two runs to see the repeat. Then the manual (both), screenshots, the release notes gain a bullet, and 1.32.0 ships with it. | Two recordings, about five minutes each. |

## Decisions for Ben

- **D1. Both rooms play throughout**, told apart by pitch, rather than taking turns as the design page said. It's
  what every measurement used, and it halves the run. Recommend.
- **D2. The click track goes into JRiver's library for the run and comes out after.** `PlayByFilename` imports
  it; `File/Delete` (library only) removes it. Recommend; the alternative is a track you'd see in your library.
- **D3. Formats:** WAV, and anything Windows can decode (m4a, mp3, FLAC). No ffmpeg. Recommend.
- **D4. The numbers are saved only on Use These Numbers**, not as soon as they're solved, so a dubious result
  can be thrown away. Recommend.
- **D5. 1.32.0 waits for stage three**, as you said. The release notes gain a Calibrate bullet.

## Not in stage three

The Generic (whole-second) clock for other renderers. Calibrating with a microphone on the PC. More than one
follower.
