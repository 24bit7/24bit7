"""
review_save_probe.py - 24bit7 Review, step 1b.

Standalone: changes nothing in 24bit7. Finds the JRiver call that adds tracks to a
saved playlist, since Playlist/AddFile answered 500 in review_check.py.

  1. Reads JRiver's own MCWS help page and lists every Playlist command it offers.
  2. Recreates the "24bit7 Review Check" playlist empty, then tries each likely
     variant in turn, checking after each whether the two tracks went in, in order.
     It stops at the first that works.
Results go to the screen and to review_save_probe_log.txt. Delete the playlist in
JRiver afterwards.
"""
import json
import os
import re
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
HOST = os.getenv("JRIVER_HOST", "127.0.0.1:52199")
ROOT = f"http://{HOST}/MCWS/v1"
AUTH = (os.getenv("JRIVER_USER"), os.getenv("JRIVER_PASS"))
LOG = os.path.join(HERE, "review_save_probe_log.txt")
PLAYLIST_NAME = "24bit7 Review Check"

log_lines = []


def say(text=""):
    print(text)
    log_lines.append(text)


def raw(path, **params):
    return requests.get(f"{ROOT}/{path}", params=params, auth=AUTH, timeout=15)


def items(text):
    try:
        return {i.get("Name"): (i.text or "").strip() for i in ET.fromstring(text).findall("Item")}
    except ET.ParseError:
        return {}


def help_page():
    say("JRiver's help page, Playlist commands:")
    for path in ("", "doc", "Help"):
        try:
            r = requests.get(f"{ROOT}/{path}", auth=AUTH, timeout=15)
        except Exception:
            continue
        text = re.sub(r"<[^>]+>", " ", r.text)
        found = sorted(set(re.findall(r"\bPlaylists?/[A-Za-z]+\b", text)))
        if found:
            say("  " + ", ".join(found))
            for name in ("Playlist/AddFile", "Playlist/AddFiles", "Playlist/Add"):
                at = text.find(name)
                if at >= 0:
                    snippet = " ".join(text[at:at + 600].split())
                    say(f"  {snippet[:400]}")
            return
    say("  (help page not found)")


def fresh_playlist():
    r = raw("Playlists/Add", Type="Playlist", Path=PLAYLIST_NAME, CreateMode="Overwrite")
    return items(r.text).get("PlaylistID", "")


def contents(pid):
    r = raw("Playlist/Files", PlaylistType="ID", Playlist=pid, Action="JSON", Fields="Key")
    try:
        return [str(x.get("Key", "")) for x in json.loads(r.text)]
    except Exception:
        return None


def find_keys():
    while True:
        artist = input("An artist in your library with at least two tracks: ").strip()
        if not artist:
            continue
        r = raw("Files/Search", Query=f'[Artist]="{artist}" [Media Type]=[Audio]', Action="JSON",
                Fields="Key,Name")
        try:
            rows = json.loads(r.text)
        except Exception:
            rows = []
        keys = [str(x.get("Key")) for x in rows if x.get("Key")][:2]
        if len(keys) == 2:
            return keys
        print("  Found fewer than two tracks, try another artist.")


def main():
    say(f"review_save_probe.py  {time.strftime('%Y-%m-%d %H:%M')}")
    help_page()
    k1, k2 = find_keys()
    both = f"{k1},{k2}"
    variants = [
        ("Playlist/AddFiles, Keys (list)", lambda p: [("Playlist/AddFiles", dict(PlaylistType="ID", Playlist=p, Keys=both))]),
        ("Playlist/AddFiles, Key (list)", lambda p: [("Playlist/AddFiles", dict(PlaylistType="ID", Playlist=p, Key=both))]),
        ("Playlist/AddFile, Key + Location End", lambda p: [("Playlist/AddFile", dict(PlaylistType="ID", Playlist=p, Key=k, Location="End")) for k in (k1, k2)]),
        ("Playlist/AddFile, Keys", lambda p: [("Playlist/AddFile", dict(PlaylistType="ID", Playlist=p, Keys=k)) for k in (k1, k2)]),
        ("Playlist/AddFile, by Path", lambda p: [("Playlist/AddFile", dict(PlaylistType="Path", Playlist=PLAYLIST_NAME, Key=k)) for k in (k1, k2)]),
        ("Playlist/AddFile, Playlist only", lambda p: [("Playlist/AddFile", dict(Playlist=p, Key=k)) for k in (k1, k2)]),
        ("Playlist/AddFile, File key", lambda p: [("Playlist/AddFile", dict(PlaylistType="ID", Playlist=p, File=k, FileType="Key")) for k in (k1, k2)]),
    ]
    say("")
    winner = None
    for name, calls in variants:
        pid = fresh_playlist()
        if not pid:
            say("Couldn't create the test playlist, stopping.")
            break
        statuses = []
        for path, params in calls(pid):
            r = raw(path, **params)
            statuses.append(str(r.status_code))
            if r.status_code != 200:
                say(f"  {name}: HTTP {r.status_code}  {' '.join(r.text.split())[:160]}")
                break
        time.sleep(0.5)
        got = contents(pid)
        ok = got == [k1, k2]
        say(f"{'WORKS' if ok else 'no   '}  {name}  (HTTP {'/'.join(statuses)}, playlist now {got})")
        if ok:
            winner = name
            break
    say("")
    say(f"Answer: {winner}" if winner else "None of the variants worked; send me the log.")
    say(f'Delete "{PLAYLIST_NAME}" in JRiver when you\'re done.')


if __name__ == "__main__":
    try:
        main()
    finally:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines) + "\n")
        print(f"Log saved to {LOG}")
