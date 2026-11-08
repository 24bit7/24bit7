"""
Console Query, brought up to date before 1.31.0 (Ben, 8 Nov 2026). It was sent engine.py, the README and .env,
while since 1.29 most settings live with each playlist in the database and the screens' names were in neither.
Now it gets the manual in the app's language, the settings as builds use them, and a prompt that knows playlists,
configs, Simple and Advanced, and the More Options switches.
"""

import threading


def ask(app, monkeypatch, question="Which settings would give me more variety?", calls=None):
    import console_query
    systems = []
    real = app.ai.create

    def create(model=None, max_tokens=None, messages=None, system=None, **kw):
        systems.append(system)
        if calls is not None:
            calls.append(dict(kw, model=model))
        return real(model=model, max_tokens=max_tokens, messages=messages, system=system, **kw)
    monkeypatch.setattr(app.ai, "create", create)
    monkeypatch.setattr(console_query.anthropic if hasattr(console_query, "anthropic") else app.ai, "create", create,
                        raising=False)
    done = threading.Event()
    result = {}
    console_query.ask(question, "21:14  Similar Artists: The Beatles\nDone: 30 tracks queued in Speakers.", None,
                      lambda answer, error: (result.update(answer=answer, error=error), done.set()))
    assert done.wait(20)
    assert result["answer"] and not result["error"], result
    system = systems[-1]
    system = " ".join(b["text"] for b in system) if isinstance(system, list) else str(system)
    return system, app.ai.sent[-1]


def test_the_manual_goes_instead_of_the_code(app, monkeypatch):
    system, _user = ask(app, monkeypatch)
    assert "24bit7's manual" in system and "Playlist Settings" in system
    assert "def create_similar_playlist" not in system, "engine.py isn't sent any more"
    assert "Vibe Playlist" not in system.split("=====")[0], "the prompt uses today's names"
    assert "Settings > Playlist > Similar Tracks" not in system
    assert "Never suggest setting something to the value it already has" in system,         "the first real try (8 Nov) suggested turning Match Tempo off when it already was"


def test_a_german_app_sends_the_german_manual(app, monkeypatch):
    import i18n
    monkeypatch.setattr(i18n, "LANGUAGE", "de")
    system, _user = ask(app, monkeypatch)
    manual = system.split("===== 24bit7's manual =====", 1)[1]
    assert "Einstellungen" in manual and "Playlist-Einstellungen" in manual, manual[:300]


def test_the_settings_builds_use_go_with_the_question(app, monkeypatch):
    import buttons
    items = buttons.load()
    similar = next(b for b in items if b.get("standard") == "artists")
    key = sorted(buttons.keys_of("artists"))[0]
    similar["settings"][key] = "17"
    buttons.save(items)
    _system, user = ask(app, monkeypatch)
    assert "Settings as builds use them:" in user and ".env (defaults and app-wide settings):" in user
    assert "Mode: Advanced" in user and "More Options row: closed" in user
    assert f"- {similar['name']} (playlist, a button" in user
    assert "Config 1, Artist Matching, every setting:" in user and f"{key}=17" in user
    assert "Filters (Settings > Filters):" in user and "Skipped Tracks: off, every playlist" in user
    import console_query
    assert console_query._shown({"TIDAL_TOKEN": "x", "LIMIT": "3"}) == "LIMIT=3", "secrets stay out of playlist settings too"


def test_switches_are_sent_as_the_page_names_them(app):
    """The second real try (8 Nov 2026) read DRIFT_TRACKS=1 as Drift off: the page's names go with the settings."""
    import buttons
    import console_query
    items = buttons.load()
    tracks = next(b for b in items if b.get("standard") == "tracks")
    tracks["settings"].update(DRIFT_TRACKS="1", DRIFT_TRACKS_FROM="spread", AI_MODERATOR_TRACKS="balanced")
    buttons.save(items)
    tracks = next(b for b in buttons.load() if b.get("standard") == "tracks")
    view = console_query.page_view(tracks, buttons.configs(tracks)[0])
    assert "Drift Spread" in view and "Moderator Balanced" in view, view
    tracks["settings"].update(DRIFT_TRACKS="1", DRIFT_TRACKS_FROM="close")
    assert "Drift Keep It Tight" in console_query.page_view(tracks, buttons.configs(tracks)[0])
    tracks["settings"].update(DRIFT_TRACKS="0")
    assert "Drift Off" in console_query.page_view(tracks, buttons.configs(tracks)[0])
    assert f"Config 1, Track Matching, as its page shows it: " in console_query.state_text()


def test_a_part_that_cant_be_read_leaves_the_others(app, monkeypatch):
    import console_query
    import radio
    monkeypatch.setattr(radio, "analysis", lambda: 1 / 0)
    text = console_query.state_text()
    assert "Mode: " in text and "Playlists:" in text and "Radio" not in text.split("Playlists:")[0]


def test_the_main_model_is_asked_with_thinking_off(app, monkeypatch):
    """The first real try on Sonnet 5 (8 Nov 2026) came back empty: it thinks by default and spent max_tokens on it."""
    import engine
    calls = []
    ask(app, monkeypatch, calls=calls)
    assert calls[-1]["model"] == engine.AI_MODELS["anthropic"][0]
    assert calls[-1].get("thinking") == {"type": "disabled"}, calls[-1]
