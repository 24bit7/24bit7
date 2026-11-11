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
    assert "Titel-Abgleich: The Beatles - Here Comes The Sun" in text, "names stay as they are; the words around them change"
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


def test_multirooms_commentary_is_a_detail_line_and_its_problems_and_notes_keep_their_colours(app):
    """10 Nov 2026: Simple hides the follower's commentary (the debug tag is the one Simple leaves out)."""
    import importlib
    gui = importlib.import_module("conftest").load_gui(app.folder)
    kind = gui.PlayTab._line_kind
    assert kind("Multiroom: Speakers in from the first note.") == "debug"
    assert kind("15:02  Multiroom: Clock refined by +1.2 ms.") == "debug"
    assert kind("Multiroom: Problem: the follower didn't start.") == "problem"
    assert kind("Multiroom: Note: the Sonos paused, so both rooms have stopped; play starts the track from the top.") == "note"
    assert kind("[debug] Fast start: the first track is playing") == "debug"
    assert gui.advanced_only("Multiroom: Jumped to 42.0 s.") and gui.advanced_only("  [debug] a detail")
    assert not gui.advanced_only("Multiroom: Problem: the follower didn't start.")
    assert not gui.advanced_only("Done: 30 tracks queued in Sonos.")


def test_the_log_counts_german_and_english_lines(app, german):
    import buildlog
    text = ("10:00  Ähnliche Titel: The Beatles - Something\n"
            "  Hinweis: eins\n  Problem: zwei\n  Note: drei (English, from an older build)\n"
            "Fertig: 3 Titel eingereiht, 0 nicht in der Bibliothek.")
    assert buildlog._count(text, "Note:") == 2
    assert buildlog._count(text, "Problem:") == 1
    assert buildlog._kind_from_text(text) == "Track Matching", "kept in English, shown translated, under its new name"


def test_the_log_shows_its_columns_in_german(app, german):
    import buildlog
    assert buildlog.playlist_type({"kind": "Similar Tracks (Cancelled)", "chain_pos": 2}) == \
        "Titel-Abgleich (Abgebrochen) · Non-stop 002"
    assert buildlog.moderator_shown("Balanced, 3 removed") == "Ausgewogen, 3 entfernt"


def test_the_listener_status_is_german(app, german):
    """27 Oct 2026: the German Settings > Voice Commands shot still said "Listening on 127.0.0.1:...". """
    status = app.voice.restart()
    assert status.startswith("Listening"), "code still reads the English"
    assert app.voice.status_shown(status).startswith("Hört auf 127.0.0.1:"), app.voice.status_shown(status)
    assert app.voice.status_shown("Off: no key yet") == "Aus: noch kein Schlüssel"
