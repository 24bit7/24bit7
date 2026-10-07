"""
review_check.py - 24bit7 Review, step 1.

Standalone: changes nothing in 24bit7 and touches no settings.
Run it from the 24bit7 folder (it reads .env for the JRiver address and login).

Checks the three JRiver calls Review needs that 24bit7 hasn't used before:
  1. Add as Up Next: two tracks inserted straight after the current track, with the
     current track carrying on and the rest of Playing Now following in its old order.
     The two tracks are taken out again afterwards.
  2. Save as Playlist: a playlist called "24bit7 Review Check" is created (or
     overwritten) and the same two tracks added in order. It's left for you to look at
     and delete in JRiver.
  3. Preview: one track played in a second zone for a few seconds while the main
     zone keeps playing, then stopped.

Before you start: the main zone should be playing, with a few tracks after the current one.
Results go to the screen and to review_check_log.txt.
"""
import os
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
HOST = os.getenv("JRIVER_HOST", "127.0.0.1:52199")
BASE = f"http://{HOST}/MCWS/v1"
AUTH = (os.getenv("JRIVER_USER"), os.getenv("JRIVER_PASS"))
LOG = os.path.join(HERE, "review_check_log.txt")
PLAYLIST_NAME = "24bit7 Review Check"
PREVIEW_SECONDS = 6

log_lines = []
results = []


def say(text=""):
    print(text)
    log_lines.append(text)


def result(name, ok, detail=""):
    results.append((name, ok))
    say(f"  {'PASS' if ok else 'FAIL'}: {name}{'  (' + detail + ')' if detail else ''}")


def get(path, **params):
    r = requests.get(f"{BASE}/{path}", params=params, auth=AUTH, timeout=15)
    r.raise_for_status()
    return r.text


def items(text):
    return {i.get("Name"): (i.text or "").strip() for i in ET.fromstring(text).findall("Item")}


def zones():
    z = items(get("Playback/Zones"))
    count = int(z.get("NumberZones") or 0)
    found = [(z.get(f"ZoneID{n}"), z.get(f"ZoneName{n}")) for n in range(count)]
    return [(i, n) for i, n in found if i and n]


def info(zid):
    return items(get("Playback/Info", Zone=zid))


def playing_now(zid):
    text = get("Playback/Playlist", Zone=zid, Fields="Key,Name,Artist")
    return [{f.get("Name"): f.text or "" for f in item.findall("Field")}
            for item in ET.fromstring(text).findall(".//Item")]


def keys_of(rows):
    return [r.get("Key", "") for r in rows]


def label(row):
    return f"{row.get('Artist', '?')} - {row.get('Name', '?')}"


def pick(prompt, options, default=None):
    for n, (_, name) in enumerate(options, 1):
        print(f"  {n}. {name}")
    hint = f" [{default}]" if default else ""
    while True:
        answer = input(f"{prompt}{hint}: ").strip() or (str(default) if default else "")
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print("  Please type one of the numbers.")


def search_tracks(artist, exclude):
    text = get("Files/Search", Query=f'[Artist]="{artist}" [Media Type]=[Audio]',
               Action="JSON", Fields="Key,Name,Artist")
    import json
    rows = [{"Key": str(r.get("Key", "")), "Name": r.get("Name", ""), "Artist": r.get("Artist", "")}
            for r in json.loads(text)]
    return [r for r in rows if r["Key"] and r["Key"] not in exclude][:2]


def check_up_next(main_id, picks):
    say("")
    say("1. Add as Up Next")
    before = playing_now(main_id)
    i = info(main_id)
    pos = int(i.get("PlayingNowPosition") or 0)
    cur_key = before[pos]["Key"] if 0 <= pos < len(before) else ""
    cur_ms = int(float(i.get("PositionMS") or 0))
    say(f"  Before: {len(before)} tracks, current is #{pos + 1}: {label(before[pos]) if cur_key else '?'}")
    new_keys = keys_of(picks)
    get("Playback/PlayByKey", Key=",".join(new_keys), Location="Next", Zone=main_id)
    time.sleep(1.5)
    after = playing_now(main_id)
    i2 = info(main_id)
    pos2 = int(i2.get("PlayingNowPosition") or 0)
    cur_key2 = after[pos2]["Key"] if 0 <= pos2 < len(after) else ""
    cur_ms2 = int(float(i2.get("PositionMS") or 0))
    say(f"  After: {len(after)} tracks, current is #{pos2 + 1}")
    for n in range(pos2, min(pos2 + 4, len(after))):
        say(f"    #{n + 1}: {label(after[n])}")
    result("current track kept", cur_key2 == cur_key, f"key {cur_key} -> {cur_key2}")
    result("current track not restarted", cur_ms2 >= cur_ms, f"{cur_ms} ms -> {cur_ms2} ms")
    result("still playing", i2.get("State") == "2", f"state {i2.get('State')}")
    result("inserted straight after, in order",
           keys_of(after[pos2 + 1:pos2 + 1 + len(new_keys)]) == new_keys)
    expected = keys_of(before[:pos + 1]) + new_keys + keys_of(before[pos + 1:])
    result("rest of Playing Now in its old order", keys_of(after) == expected)

    # Tidy up: take the two inserted tracks out again, from the end backwards
    for idx in sorted([n for n, k in enumerate(keys_of(after)) if k in new_keys and n > pos2],
                      reverse=True):
        get("Playback/EditPlaylist", Zone=main_id, Action="Remove", Source=str(idx))
        time.sleep(0.1)
    time.sleep(0.5)
    result("tidied up (Playing Now as it was)", keys_of(playing_now(main_id)) == keys_of(before))


def check_save(picks):
    say("")
    say("2. Save as Playlist")
    created = items(get("Playlists/Add", Type="Playlist", Path=PLAYLIST_NAME, CreateMode="Overwrite"))
    pid = created.get("PlaylistID", "")
    say(f"  Playlists/Add answered: {created}")
    result("playlist created", bool(pid), f"ID {pid}")
    if not pid:
        return
    for k in keys_of(picks):
        get("Playlist/AddFile", PlaylistType="ID", Playlist=pid, Key=k)
    import json
    text = get("Playlist/Files", PlaylistType="ID", Playlist=pid, Action="JSON", Fields="Key")
    got = [str(r.get("Key", "")) for r in json.loads(text)]
    result("tracks added in order", got == keys_of(picks), f"{got}")
    say(f'  Look for "{PLAYLIST_NAME}" in JRiver, then delete it when you\'re done.')


def check_preview(main_id, preview_id, track):
    say("")
    say("3. Preview")
    i = info(main_id)
    main_key = i.get("FileKey", "")
    main_ms = int(float(i.get("PositionMS") or 0))
    get("Playback/PlayByKey", Key=track["Key"], Zone=preview_id)
    say(f"  Previewing {label(track)} for {PREVIEW_SECONDS} seconds. Listen to both rooms.")
    time.sleep(PREVIEW_SECONDS)
    p = info(preview_id)
    m = info(main_id)
    result("preview zone playing that track", p.get("State") == "2" and p.get("FileKey") == track["Key"],
           f"state {p.get('State')}, key {p.get('FileKey')}")
    result("main zone carried on with the same track",
           m.get("FileKey") == main_key and int(float(m.get("PositionMS") or 0)) > main_ms)
    get("Playback/Stop", Zone=preview_id)
    time.sleep(1)
    result("preview stopped", info(preview_id).get("State") in ("0", "1"))


def main():
    say(f"review_check.py  {time.strftime('%Y-%m-%d %H:%M')}")
    zs = zones()
    if len(zs) < 2:
        say("Need at least two JRiver zones (one to play, one to preview in).")
        return
    say("Which zone is playing (the main zone)?")
    main_zone = pick("Main zone", zs, 1)
    say("Which zone is the preview zone (e.g. headphones)?")
    others = [z for z in zs if z != main_zone]
    preview_zone = pick("Preview zone", others, 1)
    say(f"Main: {main_zone[1]}   Preview: {preview_zone[1]}")
    if info(main_zone[0]).get("State") != "2":
        say("The main zone isn't playing. Start something with a few tracks after it, then run again.")
        return
    exclude = set(keys_of(playing_now(main_zone[0])))
    picks = []
    while len(picks) < 2:
        artist = input("An artist in your library with at least two tracks not in Playing Now: ").strip()
        picks = search_tracks(artist, exclude) if artist else []
        if len(picks) < 2:
            print("  Found fewer than two usable tracks, try another artist.")
    say(f"Test tracks: {label(picks[0])}, {label(picks[1])}")

    for step in (lambda: check_up_next(main_zone[0], picks),
                 lambda: check_save(picks),
                 lambda: check_preview(main_zone[0], preview_zone[0], picks[0])):
        try:
            step()
        except Exception as e:
            result("no errors", False, f"{type(e).__name__}: {e}")

    say("")
    passed = sum(1 for _, ok in results if ok)
    say(f"{passed} of {len(results)} checks passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        print(f"Log saved to {LOG}")
