"""
A whole build in German (stage 3 of German, 20 Oct 2026): the console speaks German, its lines still take
their colours, and the Log still counts them, while older English builds in the Log keep counting too.
"""

import pytest


@pytest.fixture
def german(app):
    import i18n
    i18n.set_language("de")
    yield i18n
    i18n.set_language("en")


def test_a_build_reads_in_german(app, german):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles",
                                                                                              "Here Comes The Sun"))
    text = r.text()
    assert "Fertig:" in text and "Done:" not in text, text
    assert "Ähnliche Titel: The Beatles - Here Comes The Sun" in text, "names stay as they are; the words around them change"
    assert len(app.jriver.titles("Speakers")) > 10, "and the build itself is unchanged"


def test_german_lines_keep_their_colours(app, german):
    import importlib
    gui = importlib.import_module("conftest").load_gui(app.folder)
    kind = gui.PlayTab._line_kind
    assert kind("10:00  Fertig: 30 Titel in Speakers eingereiht.") == "head"
    assert kind("  Hinweis: Drift hat nichts mehr, wovon es ausgehen kann.") == "note"
    assert kind("  Problem: Die KI hat nichts Verwendbares geliefert.") == "problem"
    assert kind("    Entfernt Tool - Schism: zu hart") == "ai"
    assert kind("  Note: an older English line") == "note", "English lines from before still colour"


def test_the_log_counts_german_and_english_lines(app, german):
    import buildlog
    text = ("10:00  Ähnliche Titel: The Beatles - Something\n"
            "  Hinweis: eins\n  Problem: zwei\n  Note: drei (English, from an older build)\n"
            "Fertig: 3 Titel eingereiht, 0 nicht in der Bibliothek.")
    assert buildlog._count(text, "Note:") == 2
    assert buildlog._count(text, "Problem:") == 1
    assert buildlog._kind_from_text(text) == "Similar Tracks", "kept in English, shown translated"


def test_the_log_shows_its_columns_in_german(app, german):
    import buildlog
    assert buildlog.playlist_type({"kind": "Similar Tracks (Cancelled)", "chain_pos": 2}) == \
        "Ähnliche Titel (Abgebrochen) · Non-stop 002"
    assert buildlog.moderator_shown("Balanced, 3 removed") == "Ausgewogen, 3 entfernt"
