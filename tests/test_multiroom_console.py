"""
Multiroom in the Simple console (Ben, 10 Nov 2026): the follower's running commentary ("Speakers in from the
first note", "Clock refined by...") is plumbing, so Simple leaves it out and Advanced shows it. What went wrong
is a Problem and what you can hear is a Note, and both show in every console. Before this every Multiroom line
showed in Simple, as a heading. Nothing here opens a window.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import link
finally:
    sys.path.remove(REPO)


def test_the_followers_commentary_is_for_advanced_only():
    for line in ("Multiroom: Speakers in from the first note.",
                 "Multiroom: Clock refined by +1.2 ms.",
                 "Multiroom: Jumped to 42.0 s.",
                 "Multiroom: The Speakers were +14 ms out; moved them.",
                 "Multiroom: The Speakers finish this track, then stop following.",
                 "Multiroom: the follower stopped on its own; starting it again.",
                 "15:02  Multiroom: Speakers in 3.20 s into the track.",
                 "  Multiroom: Start is now 90 ms."):
        assert link.advanced_only(line), line
        assert not link.is_problem(line) and not link.is_note(line), line


def test_a_problem_and_a_note_show_in_every_console():
    problems = ("Multiroom: Problem: the follower didn't start.",
                "Multiroom: Problem: there's no zone called Speakers in JRiver.",
                "15:02  Multiroom: Problem: couldn't stop the Sonos zone in JRiver (timed out).")
    notes = ("Multiroom: Note: the music isn't arriving fast enough: the Speakers are quiet until it does, still in step.",
             "Multiroom: Note: lost the Sonos's clock: the Speakers carry on on their own for now.",
             "Multiroom: Note: the Sonos paused, so both rooms have stopped; play starts the track from the top.")
    for line in problems:
        assert link.is_problem(line) and not link.advanced_only(line), line
    for line in notes:
        assert link.is_note(line) and not link.advanced_only(line), line


def test_lines_that_arent_multirooms_are_left_alone():
    for line in ("Done: 30 tracks queued in Sonos.", "  Note: nothing new to add.", "[debug] Multiroom: not a follower line",
                 "Similar Artists: Multiroom: a track called that", ""):
        assert not link.advanced_only(line) and not link.is_problem(line) and not link.is_note(line), line


def test_the_follower_words_what_you_hear_as_notes_and_what_failed_as_problems():
    """The lines themselves, read from the follower's source: a reworded line would slip back into hiding."""
    with open(os.path.join(REPO, "multiroom", "follower.py"), encoding="utf-8") as f:
        source = f.read()
    for said in ('"Note: the music isn\'t arriving fast enough', 'f"Note: lost the {self.leader}\'s clock',
                 'f"Note: the {self.leader} paused, so both rooms have stopped',
                 'f"Problem: there\'s no zone called {self.follower} in JRiver."',
                 'f"Problem: couldn\'t stop the {self.leader} zone in JRiver'):
        assert said in source, said
