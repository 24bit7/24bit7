"""
retag_singles.py - retags the singles kept under Artist "Singles:".

Before:  Artist "Singles:"      Album "David Guetta"   Album Artist "Singles:"      Description ""
After:   Artist "David Guetta"  Album "Sexy Chick"     Album Artist "David Guetta"  Description "Singles:"

The act comes from the Album field, the album becomes the track's own title,
and Description carries the marker your library view filters on.
Reads JRIVER_HOST, JRIVER_USER and JRIVER_PASS from the .env in this folder.

  py retag_singles.py           dry run, lists what would change, writes nothing
  py retag_singles.py --apply   makes the changes
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

OLD_MARKER = "Singles:"   # what Artist holds today
NEW_MARKER = "Singles:"   # what Description will hold

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
HOST = os.getenv("JRIVER_HOST", "127.0.0.1:52199")
AUTH = (os.getenv("JRIVER_USER") or "", os.getenv("JRIVER_PASS") or "")
BASE = f"http://{HOST}/MCWS/v1"
APPLY = "--apply" in sys.argv


def find_singles():
    r = requests.get(f"{BASE}/Files/Search", auth=AUTH, timeout=60, params={
        "Query": f'[Artist]="{OLD_MARKER}"',   # JRiver ignores case, so "SIngles:" is caught too
        "Action": "JSON",
        "Fields": "Key,Name,Artist,Album,Album Artist,Description",
    })
    r.raise_for_status()
    return json.loads(r.text) if r.text.strip() else []


def set_field(key, field, value):
    r = requests.get(f"{BASE}/File/SetInfo", auth=AUTH, timeout=30, params={
        "File": key, "FileType": "Key", "Field": field, "Value": value, "List": "Default",
    })
    return r.status_code == 200 and 'Status="OK"' in r.text


def main():
    rows = find_singles()
    if not rows:
        print(f'No tracks found with Artist "{OLD_MARKER}". Nothing to do.')
        return
    rows.sort(key=lambda r: ((r.get("Album") or "").lower(), (r.get("Name") or "").lower()))
    changed, skipped, failed = 0, [], []
    for row in rows:
        key = str(row.get("Key"))
        title = (row.get("Name") or "").strip()
        act = (row.get("Album") or "").strip()
        if not act or not title:
            skipped.append(f"{act or '?'} / {title or '?'}")
            continue
        print(f"{'Setting' if APPLY else 'Would set'}: {act} | {title} | {title}")
        if APPLY:
            # Album last: it holds the act until Artist and Album Artist have taken it
            ok = (set_field(key, "Artist", act)
                  and set_field(key, "Album Artist", act)
                  and set_field(key, "Description", NEW_MARKER)
                  and set_field(key, "Album", title))
            if not ok:
                failed.append(f"{act} / {title}")
                continue
        changed += 1
    print()
    print("Columns above: Artist | Album | Name")
    print(f"{len(rows)} found, {changed} {'changed' if APPLY else 'to change'}.")
    if skipped:
        print(f"Skipped, Album or Name empty ({len(skipped)}): " + "; ".join(skipped))
    if failed:
        print(f"Failed part way, check these in JRiver ({len(failed)}): " + "; ".join(failed))
    if not APPLY:
        print("Dry run only. Run again with --apply to make the changes.")


if __name__ == "__main__":
    main()
