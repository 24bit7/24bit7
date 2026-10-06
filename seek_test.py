"""
seek_test.py - 24bit7 Switch test, step 1.

Standalone: changes nothing in 24bit7 and touches no settings.
Run it from the 24bit7 folder (it reads .env for the JRiver address and login).

What it does:
  1. You pick the zone that is playing (the source) and the zone to test (the Sonos).
  2. It notes the Sonos volume and sets it to zero.
  3. It starts the same track on the Sonos and times how long until it reports playing.
  4. It seeks the Sonos to where the source is now, and checks whether the seek sticks
     (one retry if it doesn't).
  5. It restores the Sonos volume, so you can hear both rooms together.
  6. You press Enter and it stops the Sonos. The source keeps playing throughout.

The volume is always put back, even if something fails or you press Ctrl+C.
Results go to the screen and to seek_test_log.txt (with the raw zone details,
which help work out how 24bit7 should spot a DLNA zone).
"""
import os
import sys
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
HOST = os.getenv("JRIVER_HOST", "127.0.0.1:52199")
BASE = f"http://{HOST}/MCWS/v1"
AUTH = (os.getenv("JRIVER_USER"), os.getenv("JRIVER_PASS"))
LOG = os.path.join(HERE, "seek_test_log.txt")

START_TIMEOUT = 15     # seconds to wait for the Sonos to report playing
SEEK_CHECK = 4         # seconds to watch for the seek taking effect
POLL = 0.25            # seconds between checks

log_lines = []


def say(text=""):
    print(text)
    log_lines.append(text)


def call(path, **params):
    r = requests.get(f"{BASE}/{path}", params=params, auth=AUTH, timeout=10)
    r.raise_for_status()
    return {i.get("Name"): (i.text or "").strip() for i in ET.fromstring(r.text).findall("Item")}


def zones():
    z = call("Playback/Zones")
    count = int(z.get("NumberZones") or 0)
    found = [(z.get(f"ZoneID{n}"), z.get(f"ZoneName{n}")) for n in range(count)]
    return [(i, n) for i, n in found if i and n]


def info(zid):
    return call("Playback/Info", Zone=zid)


def position_ms(items):
    return int(float(items.get("PositionMS") or 0))


def clock(ms):
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


def pick(prompt, options, default=None):
    for n, (_, name) in enumerate(options, 1):
        print(f"  {n}. {name}")
    hint = f" [{default}]" if default else ""
    while True:
        answer = input(f"{prompt}{hint}: ").strip() or (str(default) if default else "")
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print("  Type one of the numbers above.")


def wait_until_playing(tid):
    """Seconds until the zone reports Playing with the clock moving, or None on timeout."""
    t0 = time.time()
    last = None
    while time.time() - t0 < START_TIMEOUT:
        items = info(tid)
        pos = position_ms(items)
        if items.get("State") == "2" and last is not None and pos > last:
            return time.time() - t0
        last = pos if items.get("State") == "2" else None
        time.sleep(POLL)
    return None


def seek_and_check(sid, tid):
    """Seeks the target to the source's current point. Returns (stuck, seconds to take effect, wanted ms)."""
    want = position_ms(info(sid))
    t0 = time.time()
    call("Playback/Position", Position=want, Zone=tid)
    while time.time() - t0 < SEEK_CHECK:
        pos = position_ms(info(tid))
        if pos >= want - 1500:
            return True, time.time() - t0, want
        time.sleep(POLL)
    return False, None, want


def main():
    say(f"24bit7 Switch seek test, {time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        all_zones = zones()
    except Exception as e:
        print(f"Couldn't reach JRiver at {HOST} ({e}). Is JRiver open, and is this the 24bit7 folder?")
        return 1
    if len(all_zones) < 2:
        print("JRiver shows fewer than two zones, so there's nothing to switch between.")
        return 1

    playing = [n for n, (zid, _) in enumerate(all_zones, 1) if info(zid).get("State") == "2"]
    print("\nWhich zone is playing now (the source)?")
    src = pick("Source", all_zones, playing[0] if playing else None)
    print("\nWhich zone should the test switch to (the Sonos)?")
    tgt = pick("Target", all_zones)
    if tgt[0] == src[0]:
        print("Source and target are the same zone.")
        return 1
    sid, tid = src[0], tgt[0]

    src_info = info(sid)
    if src_info.get("State") != "2":
        print(f"{src[1]} isn't playing. Start something there and run the test again.")
        return 1
    key = src_info.get("FileKey")
    if not key:
        print(f"Couldn't read the track playing on {src[1]}.")
        return 1
    tgt_info = info(tid)
    if tgt_info.get("State") in ("1", "2"):
        if input(f"{tgt[1]} is already playing something, and the test will replace it. Carry on? (y/n): ").strip().lower() != "y":
            return 0

    say(f"\nSource: {src[1]}   Target: {tgt[1]}")
    say(f"Track: {src_info.get('Artist')} - {src_info.get('Name')}, at {clock(position_ms(src_info))}")

    volume = call("Playback/Volume", Zone=tid).get("Level")
    muted = False
    try:
        call("Playback/Volume", Level=0, Zone=tid)
        muted = True
        say(f"Target volume noted ({volume}) and set to zero.")

        t0 = time.time()
        call("Playback/PlayByKey", Key=key, Zone=tid)
        started = wait_until_playing(tid)
        if started is None:
            say(f"RESULT: {tgt[1]} didn't report playing within {START_TIMEOUT} seconds.")
            return 1
        say(f"Start-up: {started:.2f} s from sending the track to it reporting playing.")

        stuck, took, want = seek_and_check(sid, tid)
        tries = 1
        if not stuck:
            say(f"First seek to {clock(want)} didn't take effect within {SEEK_CHECK} s. Retrying in 1 s.")
            time.sleep(1)
            stuck, took, want = seek_and_check(sid, tid)
            tries = 2
        if stuck:
            say(f"Seek: accepted on try {tries}, took effect in {took:.2f} s (to {clock(want)}).")
        else:
            say("Seek: refused both times. The track carries on from the start.")

        a, b = info(sid), info(tid)
        gap = position_ms(b) - position_ms(a)
        say(f"Gap reported by JRiver straight after: target is {abs(gap) / 1000:.2f} s "
            f"{'ahead of' if gap >= 0 else 'behind'} the source.")
        say(f"Whole handover: {time.time() - t0:.2f} s.")

        call("Playback/Volume", Level=volume, Zone=tid)
        muted = False
        say("Target volume restored.")

        if stuck:
            print("\nBoth rooms are playing now. Listen to whether they line up, and roughly by how much they don't.")
            heard = input("What did you hear? (e.g. 'Sonos about 1 s behind', or Enter to skip): ").strip()
            if heard:
                say(f"Heard: {heard}")
        input(f"\nPress Enter to stop the test on {tgt[1]} (the source keeps playing)...")
        call("Playback/Stop", Zone=tid)
        say(f"{tgt[1]} stopped.")
        return 0
    finally:
        if muted:
            try:
                call("Playback/Volume", Level=volume, Zone=tid)
                say("Target volume restored after an interruption.")
            except Exception as e:
                say(f"COULDN'T RESTORE the target volume ({e}). Set {tgt[1]} back to {volume} in JRiver.")
        try:
            raw = ["", "Raw zone details (for DLNA detection):"]
            for label, zid in (("Source", sid), ("Target", tid)):
                raw.append(f"[{label}] " + ", ".join(f"{k}={v}" for k, v in info(zid).items()))
            log_lines.extend(raw)
        except Exception:
            pass
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        print(f"\nSaved to {LOG}. Paste the results above back into the chat.")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
