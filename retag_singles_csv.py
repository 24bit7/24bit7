"""
retag_singles_csv.py - retags the singles listed in a JRiver CSV export, straight in the FLAC files.

Works only on the files in the CSV (Filename column), using JRiver's values from it:
    ARTIST       = the CSV's Album (the act)
    ALBUMARTIST  = the CSV's Album (any "ALBUM ARTIST" / "ALBUM_ARTIST" spelling is removed)
    ALBUM        = the CSV's Name (the track's own title)
    DESCRIPTION  = "Singles:"
Whatever the file's own ARTIST tag says doesn't matter. File and folder names are not touched.

  py retag_singles_csv.py           dry run, lists what would change and each file's current ARTIST tag
  py retag_singles_csv.py --apply   makes the changes, adding the old values to singles_undo.json first
  (undo with: py retag_singles_files.py --undo, which uses the same log)

Reads Singles_2.csv from this folder; give another file name to use a different export.
Afterwards, in JRiver: select these files and run Update Library (from tags).
"""
import os
import sys
import csv
import json
from mutagen.flac import FLAC

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_MARKER = "Singles:"
UNDO_FILE = os.path.join(HERE, "singles_undo.json")
ALBUM_ARTIST_VARIANTS = ("album artist", "album_artist")
TOUCHED = ("artist", "albumartist", "album artist", "album_artist", "album", "description")
APPLY = "--apply" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
CSV_FILE = os.path.join(HERE, args[0]) if args else os.path.join(HERE, "Singles_2.csv")


def load_undo():
    if os.path.exists(UNDO_FILE):
        with open(UNDO_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_undo(data):
    with open(UNDO_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def main():
    if not os.path.exists(CSV_FILE):
        print(f"Can't find {CSV_FILE}. Put the CSV in the 24bit7 folder first.")
        return
    with open(CSV_FILE, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    undo = load_undo()
    changed, missing, skipped, failed = 0, [], [], []
    for row in rows:
        path = (row.get("Filename") or "").strip()
        act = (row.get("Album") or "").strip()
        title = (row.get("Name") or "").strip()
        if not path or not act or not title:
            skipped.append(path or "(row with no Filename)")
            continue
        if not os.path.exists(path):
            missing.append(path)
            continue
        try:
            audio = FLAC(path)
        except Exception as e:
            failed.append(f"{path} (couldn't read: {e})")
            continue
        tags = audio.tags or {}
        current = "; ".join(tags.get("artist") or []) or "(no ARTIST tag)"
        print(f"{'Setting' if APPLY else 'Would set'}: {act} | {title}   [file ARTIST now: {current!r}]")
        if not APPLY:
            changed += 1
            continue
        if path not in undo:
            undo[path] = {k: (list(tags[k]) if k in tags else None) for k in TOUCHED}
            save_undo(undo)
        try:
            audio["artist"] = act
            audio["albumartist"] = act
            for k in ALBUM_ARTIST_VARIANTS:
                if k in audio:
                    del audio[k]
            audio["album"] = title
            audio["description"] = NEW_MARKER
            audio.save()
            changed += 1
        except Exception as e:
            failed.append(f"{path} ({e})")
    print()
    print("Columns above: Artist | Album (= title)")
    print(f"{len(rows)} in the CSV, {changed} {'changed' if APPLY else 'to change'}.")
    for label, items in (("Not found on disk", missing), ("Skipped, Album or Name empty", skipped),
                         ("Failed, often a file in use", failed)):
        if items:
            print(f"{label} ({len(items)}):")
            for p in items:
                print("  " + p)
    if APPLY and changed:
        print(f"Old values added to {UNDO_FILE}")
        print("Now in JRiver: select these files and run Update Library (from tags).")
    if not APPLY:
        print("Dry run only. Run again with --apply to make the changes.")


if __name__ == "__main__":
    main()
