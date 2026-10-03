"""
retag_singles_files.py - retags the singles straight in the FLAC files (JRiver not involved).

Looks in the Singles_ folders on F:, G:, H: and I: for FLAC files whose ARTIST
tag is "Singles:" (any capitalisation), and for each one sets:
    ARTIST       = the act, from the current ALBUM tag
    ALBUMARTIST  = the act (any "ALBUM ARTIST" / "ALBUM_ARTIST" spelling is removed)
    ALBUM        = the track's own TITLE
    DESCRIPTION  = "Singles:"
File and folder names are not touched.

  py retag_singles_files.py           dry run, lists what would change, writes nothing
  py retag_singles_files.py --apply   makes the changes, saving the old values to singles_undo.json first
  py retag_singles_files.py --undo    puts back the values saved in singles_undo.json

Afterwards, in JRiver: select the singles and run Update Library (from tags).
Needs mutagen:  py -m pip install mutagen
"""
import os
import sys
import json
from mutagen.flac import FLAC

ROOTS = [r"F:\Singles_", r"G:\Singles_", r"H:\Singles_", r"I:\Singles_"]
OLD_MARKER = "singles:"      # matched ignoring case
NEW_MARKER = "Singles:"      # written to DESCRIPTION
UNDO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "singles_undo.json")
ALBUM_ARTIST_VARIANTS = ("album artist", "album_artist")
TOUCHED = ("artist", "albumartist", "album artist", "album_artist", "album", "description")


def first(tags, name):
    values = tags.get(name) or []
    return values[0].strip() if values else ""


def flac_files():
    for root in ROOTS:
        if not os.path.isdir(root):
            print(f"(not found, skipped: {root})")
            continue
        for folder, _, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".flac"):
                    yield os.path.join(folder, f)


def load_undo():
    if os.path.exists(UNDO_FILE):
        with open(UNDO_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_undo(data):
    with open(UNDO_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def retag(apply):
    undo = load_undo()
    found, changed, skipped, failed = 0, 0, [], []
    for path in flac_files():
        try:
            audio = FLAC(path)
        except Exception as e:
            failed.append(f"{path} (couldn't read: {e})")
            continue
        tags = audio.tags or {}
        if first(tags, "artist").lower() != OLD_MARKER:
            continue
        found += 1
        act, title = first(tags, "album"), first(tags, "title")
        if not act or not title:
            skipped.append(path)
            continue
        print(f"{'Setting' if apply else 'Would set'}: {act} | {title} | {title}")
        if not apply:
            changed += 1
            continue
        if path not in undo:   # keep the very first originals if run more than once
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
    print("Columns above: Artist | Album | Title")
    print(f"{found} found, {changed} {'changed' if apply else 'to change'}.")
    if skipped:
        print(f"Skipped, ALBUM or TITLE empty ({len(skipped)}):")
        for p in skipped:
            print("  " + p)
    if failed:
        print(f"Failed ({len(failed)}), often a file in use:")
        for p in failed:
            print("  " + p)
    if apply and changed:
        print(f"Old values saved to {UNDO_FILE}")
        print("Now in JRiver: select the singles and run Update Library (from tags).")
    if not apply:
        print("Dry run only. Run again with --apply to make the changes.")


def undo_all():
    undo = load_undo()
    if not undo:
        print("No undo log found, nothing to put back.")
        return
    done, failed = 0, []
    for path, saved in undo.items():
        try:
            audio = FLAC(path)
            for k, v in saved.items():
                if v is None:
                    if k in audio:
                        del audio[k]
                else:
                    audio[k] = v
            audio.save()
            done += 1
        except Exception as e:
            failed.append(f"{path} ({e})")
    print(f"{done} of {len(undo)} files put back.")
    for p in failed:
        print("  Failed: " + p)
    if not failed:
        os.replace(UNDO_FILE, UNDO_FILE + ".used")
        print("Undo log renamed to singles_undo.json.used. Run Update Library (from tags) in JRiver.")


if __name__ == "__main__":
    if "--undo" in sys.argv:
        undo_all()
    else:
        retag("--apply" in sys.argv)
