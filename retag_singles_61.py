"""
retag_singles_61.py - retags the 61 singles still showing under "Singles:", straight in the FLAC files.
The file paths and values are built in (taken from your JRiver export), so nothing else is needed.
    ARTIST and ALBUMARTIST = the act, ALBUM = the track's own title, DESCRIPTION = "Singles:"

  py retag_singles_61.py           dry run, lists what would change and each file's current ARTIST tag
  py retag_singles_61.py --apply   makes the changes, adding the old values to singles_undo.json first
  (undo with: py retag_singles_files.py --undo, which uses the same log)

Afterwards, in JRiver: select these files and run Update Library (from tags).
"""

import os
import sys
import json
from mutagen.flac import FLAC

HERE = os.path.dirname(os.path.abspath(__file__))
NEW_MARKER = "Singles:"
UNDO_FILE = os.path.join(HERE, "singles_undo.json")
ALBUM_ARTIST_VARIANTS = ("album artist", "album_artist")
TOUCHED = ("artist", "albumartist", "album artist", "album_artist", "album", "description")
APPLY = "--apply" in sys.argv
# (path, act, title) for the 61 singles JRiver still showed under "Singles:"
SINGLES = [
    ('I:\\Singles_\\Jamies, The\\01 - Summertime, Summertime.flac', 'Jamies, The', 'Summertime, Summertime'),
    ('I:\\Singles_\\B.J. Thomas\\01 - Raindrops Keep Fallin’ on My Head.flac', 'B.J. Thomas', 'Raindrops Keep Fallin’ on My Head'),
    ('I:\\Singles_\\Partridge Family, The\\01 - I Think I Love You.flac', 'Partridge Family, The', 'I Think I Love You'),
    ('I:\\Singles_\\Looking Glass\\01 - Brandy (You’re A Fine Girl).flac', 'Looking Glass', 'Brandy (You’re A Fine Girl)'),
    ("I:\\Singles_\\Eddie Kendricks\\01 - Keep On Truckin'.flac", 'Eddie Kendricks', "Keep On Truckin'"),
    ('I:\\Singles_\\Wild Cherry\\01 - Play That Funky Music.flac', 'Wild Cherry', 'Play That Funky Music'),
    ('I:\\Singles_\\Alan O’Day\\01 - Undercover Angel.flac', 'Alan O’Day', 'Undercover Angel'),
    ("I:\\Singles_\\Crystal Gayle\\01 - Don't It Make My Brown Eyes Blue.flac", 'Crystal Gayle', "Don't It Make My Brown Eyes Blue"),
    ('I:\\Singles_\\Debby Boone\\01 - You Light Up My Life.flac', 'Debby Boone', 'You Light Up My Life'),
    ('I:\\Singles_\\Hot\\01 - Angel In Your Arms.flac', 'Hot', 'Angel In Your Arms'),
    ("I:\\Singles_\\Kenny Nolan\\01 - I Like Dreamin'.flac", 'Kenny Nolan', "I Like Dreamin'"),
    ('I:\\Singles_\\Marilyn McCoo\\01 - You Don’t Have To Be A Star (To Be In My Show).flac', 'Marilyn McCoo', 'You Don’t Have To Be A Star (To Be In My Show)'),
    ('I:\\Singles_\\Paul Davis\\01 - I Go Crazy.flac', 'Paul Davis', 'I Go Crazy'),
    ('I:\\Singles_\\Player\\01 - Baby Come Back.flac', 'Player', 'Baby Come Back'),
    ('I:\\Singles_\\Samantha Sang\\01 - Emotion.flac', 'Samantha Sang', 'Emotion'),
    ('I:\\Singles_\\A Taste Of Honey\\01 - Boogie Oogie Oogie.flac', 'A Taste Of Honey', 'Boogie Oogie Oogie'),
    ('I:\\Singles_\\Exile\\01 - Kiss You All Over.flac', 'Exile', 'Kiss You All Over'),
    ('I:\\Singles_\\Nick Gilder\\01 - Hot Child In The City.flac', 'Nick Gilder', 'Hot Child In The City'),
    ('I:\\Singles_\\Robert John\\01 - Sad Eyes.flac', 'Robert John', 'Sad Eyes'),
    ("I:\\Singles_\\Sugarhill Gang\\01 - Rapper's Delight.flac", 'Sugarhill Gang', "Rapper's Delight"),
    ('I:\\Singles_\\Jim Diamond\\00 - I Should Have Known Better.flac', 'Jim Diamond', 'I Should Have Known Better'),
    ("I:\\Singles_\\'M'\\01 - Pop Muzik.flac", "'M'", 'Pop Muzik'),
    ("I:\\Singles_\\'M'\\01 - Pop Muzik (Britannia '89 Remix).flac", "'M'", "Pop Muzik (Britannia '89 Remix)"),
    ('G:\\Singles_\\M_A_R_R_S\\01 - Pump Up The Volume.flac', 'M|A|R|R|S', 'Pump Up The Volume'),
    ('H:\\Singles_\\Yazz & The Plastic Population\\01 - The Only Way Is Up.flac', 'Yazz & The Plastic Population', 'The Only Way Is Up'),
    ('I:\\Singles_\\Jive Bunny\\01 - Swing The Mood.flac', 'Jive Bunny', 'Swing The Mood'),
    ('H:\\Singles_\\Technotronic\\01 - Pump Up The Jam.flac', 'Technotronic', 'Pump Up The Jam'),
    ('I:\\Singles_\\Black Box\\01 - Ride On Time.flac', 'Black Box', 'Ride On Time'),
    ('G:\\Singles_\\C&C Music Factory\\01 - Gonna Make You Sweat (Everybody Dance Now).flac', 'C&C Music Factory', 'Gonna Make You Sweat (Everybody Dance Now)'),
    ("I:\\Singles_\\Rozalla\\01 - Everybody's Free (To Feel Good).flac", 'Rozalla', "Everybody's Free (To Feel Good)"),
    ('G:\\Singles_\\Snap!\\01 - The Power.flac', 'Snap!', 'The Power'),
    ('G:\\Singles_\\Snap!\\05 - Rhythm Is A Dancer 1992.flac', 'Snap!', 'Rhythm Is A Dancer 1992'),
    ('I:\\Singles_\\Vanilla Ice\\01 - Ninja Rap.flac', 'Vanilla Ice', 'Ninja Rap'),
    ("I:\\Singles_\\Dr. Alban\\01 - It's My Life.flac", 'Dr. Alban', "It's My Life"),
    ('I:\\Singles_\\Kris Kross\\01 - Jump.flac', 'Kris Kross', 'Jump'),
    ("I:\\Singles_\\Right Said Fred\\01 - I'm Too Sexy.flac", 'Right Said Fred', "I'm Too Sexy"),
    ('G:\\Singles_\\Corona\\01 - The Rhythm Of The Night.flac', 'Corona', 'The Rhythm Of The Night'),
    ('H:\\Singles_\\Culture Beat\\01 - Mr. Vain.flac', 'Culture Beat', 'Mr. Vain'),
    ('G:\\Singles_\\Reel 2 Real\\01 - I Like To Move It.flac', 'Reel 2 Real', 'I Like To Move It'),
    ('H:\\Singles_\\Robin S\\01 - Show Me Love.flac', 'Robin S.', 'Show Me Love'),
    ('I:\\Singles_\\Whoomp! There It Is\\01 - Whoomp! There It Is.flac', 'Whoomp! There It Is', 'Whoomp! There It Is'),
    ('I:\\Singles_\\Whigfield\\01 - Saturday Night.flac', 'Whigfield', 'Saturday Night'),
    ('G:\\Singles_\\La Bouche\\01 - Be My Lover.flac', 'La Bouche', 'Be My Lover'),
    ('I:\\Singles_\\Scatman John\\01 - Scatman.flac', 'Scatman John', 'Scatman'),
    ('H:\\Singles_\\Gala\\01 - Freed From Desire.flac', 'Gala', 'Freed From Desire'),
    ('H:\\Singles_\\Da Hool\\01 - Meet Her At The Love Parade.flac', 'Da Hool', 'Meet Her At The Love Parade'),
    ('I:\\Singles_\\Marcy Playground\\01 - Sex & Candy.flac', 'Marcy Playground', 'Sex & Candy'),
    ('G:\\Singles_\\Ultra Naté\\01 - Free.flac', 'Ultra Naté', 'Free'),
    ('H:\\Singles_\\Stardust\\01 - Music Sounds Better With You.flac', 'Stardust', 'Music Sounds Better With You'),
    ('G:\\Singles_\\Alice Deejay\\01 - Better Off Alone.flac', 'Alice Deejay', 'Better Off Alone'),
    ('I:\\Singles_\\Vengaboys\\01 - We Like To Party!.flac', 'Vengaboys', 'We Like To Party!'),
    ('H:\\Singles_\\DJ Otzi\\01 - Hey Baby (Uhh Ahh).flac', 'DJ Otzi', 'Hey Baby (Uhh Ahh)'),
    ('H:\\Singles_\\Modjo\\01 - Lady (Hear Me Tonight).flac', 'Modjo', 'Lady (Hear Me Tonight)'),
    ('I:\\Singles_\\Spiller\\01 - Groovejet (If This Aint Love).flac', 'Spiller', 'Groovejet (If This Aint Love)'),
    ('H:\\Singles_\\Sylver\\01 - Turn The Tide (CJ-Stone Remix).flac', 'Sylver', 'Turn The Tide (CJ-Stone Remix)'),
    ('G:\\Singles_\\Zombie Nation\\01 - Kernkraft 400.flac', 'Zombie Nation', 'Kernkraft 400'),
    ('H:\\Singles_\\Ludacris\\01 - Move Bitch.flac', 'Ludacris', 'Move Bitch'),
    ('G:\\Singles_\\Benny Benassi\\01 - Satisfaction.flac', 'Benny Benassi', 'Satisfaction'),
    ('G:\\Singles_\\Eric Prydz\\01 - Call On Me.flac', 'Eric Prydz', 'Call On Me'),
    ('I:\\Singles_\\Usher\\01 - Yeah.flac', 'Usher', 'Yeah'),
    ('H:\\Singles_\\Alex Gaudino\\01 - Destination Calabria.flac', 'Alex Gaudino', 'Destination Calabria'),
]


def load_undo():
    if os.path.exists(UNDO_FILE):
        with open(UNDO_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_undo(data):
    with open(UNDO_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def main():
    rows = [{"Filename": p, "Album": a, "Name": t} for p, a, t in SINGLES]
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
    print(f"{len(rows)} listed, {changed} {'changed' if APPLY else 'to change'}.")
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
