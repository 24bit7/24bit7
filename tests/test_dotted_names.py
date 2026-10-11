"""Dotted names: the library cache matches U.N.K.L.E. to UNKLE, R.E.M. to REM, M.I.A. to MIA."""

import pytest


@pytest.mark.parametrize("source, tagged", [
    ("UNKLE", "U.N.K.L.E."), ("UNKLE", "U.N.K.L.E"), ("REM", "R.E.M."), ("MIA", "M.I.A."),
])
def test_dotted_and_plain_spellings_compare_the_same(app, source, tagged):
    assert app.library.norm(source) == app.library.norm(tagged)
    assert app.library.score(source, tagged) == 1.0


def test_lone_letters_are_left_alone(app):
    assert app.library.norm("Jay Z") == "jay z"
    assert app.library.norm("Take a Bow") == "take a bow"


def test_a_source_spelling_finds_the_dotted_tag(app):
    row = dict(app.jriver.tracks[0], Key="9101", Name="Unreal", Artist="U.N.K.L.E.",
               Album="Never, Never, Land")
    app.jriver.tracks.append(row)
    app.jriver.by_key[row["Key"]] = row
    app.library.load()
    assert app.library.find_track_key("UNKLE", "Unreal") == "9101"
    assert app.library.find_track_key("U.N.K.L.E.", "Unreal") == "9101"
