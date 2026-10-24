"""
Did you mean (24 Oct 2026): 'eleven finger' typed into Search found Last.fm's misfiled 'Eleven Finger' page,
none of whose tracks matched Ben's Finger Eleven. A typed artist that isn't in the library now gets the
library artist it most likely means offered, never used without asking. No AI and no setting.
"""

import pytest


@pytest.fixture
def finger_eleven(app):
    j = app.jriver
    template = next(r for r in j.tracks if r["Genre"] == "Rock")
    for n, title in enumerate(("Paralyzer", "One Thing", "Slow Chemical")):
        row = dict(template, Key=str(95000 + n), Artist="Finger Eleven", Name=title, Album="Them vs. You vs. Me",
                   **{"Album Artist (auto)": "Finger Eleven"})
        j.tracks.append(row)
        j.by_key[row["Key"]] = row
    app.library.load()
    return app.library


def test_words_the_wrong_way_round(finger_eleven):
    assert finger_eleven.suggest_artist("eleven finger") == "Finger Eleven"


def test_a_typo(finger_eleven):
    assert finger_eleven.suggest_artist("Finger Elevn") == "Finger Eleven"


def test_nothing_offered_for_an_artist_you_own(finger_eleven):
    assert finger_eleven.suggest_artist("finger eleven") is None
    assert finger_eleven.suggest_artist("The Beatles") is None


def test_nothing_offered_when_nothing_is_close(finger_eleven):
    assert finger_eleven.suggest_artist("Radiohead") is None
    assert finger_eleven.suggest_artist("") is None
