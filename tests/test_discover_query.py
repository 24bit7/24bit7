"""
Discover (the gaps found by each build) and Console Query.
"""

import threading


def test_discover_records_misses(app):
    e = app.engine
    e.create_similar_playlist(report=app.Lines(), seed_info=e.typed_seed_info("The Beatles", "Here Comes The Sun"))
    misses = e.list_discoveries(found=False)
    names = {str(m) for m in misses}
    assert misses and any("Zombies" in n for n in names), misses[:3]
    assert e.list_sessions(), "the build should be listed as a session"


def test_console_query_sends_no_keys(app):
    import console_query
    done = threading.Event()
    result = {}
    console_query.ask("Why was Echoes left out?", "Skipped Echoes by Pink Floyd: last on its album and 23:31 long.",
                      {"Artist": "Pink Floyd", "Name": "Echoes", "Album": "Meddle"},
                      lambda answer, error: (result.update(answer=answer, error=error), done.set()))
    assert done.wait(20)
    assert result["answer"] and not result["error"], result
    sent = " ".join(str(c) for c in app.ai.calls)
    text = " ".join(app.ai.sent)
    for secret in ("test-lastfm", "test-anthropic", "test-voice-key", "test-lb"):
        assert secret not in text, f"{secret} was sent to the AI"
