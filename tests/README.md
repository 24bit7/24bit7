# 24bit7 test suite

Runs 24bit7 against a fake world: a stand-in JRiver (three zones, a small
library, playlists and smartlists), fake Last.fm, Deezer, MusicBrainz and
ListenBrainz, a fake AI and a fake YouTube Music. Voice tests send real-shaped
Alexa requests through the needle drop skill (`alexa/lambda_function.py`) and
24bit7's listener. Nothing touches your JRiver, your library, your .env, your
database or the internet: each test runs in its own temporary copy.

## Running it

Once, to install what the tests need:

    py -m pip install -r tests\requirements.txt

Then, from the 24bit7 folder:

    py -m pytest tests

A short run of just one area: `py -m pytest tests\test_voice.py`. The interface
tests (`test_gui.py`) open 24bit7's window for a few seconds each; leave the
mouse and keyboard alone while they run, or skip them with
`py -m pytest tests --ignore=tests\test_gui.py`.

## What's covered

- `test_voice.py`: every Alexa intent end to end, devices, zones, asks, takeover.
- `test_engine.py`: each Play option, matching rules, sources, cache, Drift,
  AI and Moderator, Skip recent, the hidden-track check, Run After Building.
- `test_mix_filters.py`: Add Playlist rows, Settings > Filters, JRiver
  playlists by voice (Shuffle, Skip recent, Non-stop, global rows).
- `test_gui.py`: every page opens, Play tab builds, console tabs and Log,
  and a sweep that changes every setting, reopens Settings and checks each kept.
- `test_discover_query.py`: Discover's gaps and Console Query (no keys sent).

Not covered (Windows only, check by hand): the tray, keyboard shortcuts, the
real Alexa hop through Tailscale, and build.bat.
