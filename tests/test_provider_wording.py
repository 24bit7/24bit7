"""
Provider-aware wording (Denis's Ollama report): with OpenAI, Google Gemini or Ollama chosen,
nothing tells you about Anthropic credit.
"""

import pathlib


def test_moderator_warning_names_the_chosen_provider(app):
    import settings_gui
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="sk-test")
    assert "OpenAI" in settings_gui.moderator_warning() and "Anthropic" not in settings_gui.moderator_warning()
    app.set_env(AI_PROVIDER="gemini", GEMINI_API_KEY="g-test")
    assert "Google Gemini" in settings_gui.moderator_warning()
    app.set_env(AI_PROVIDER="ollama", OLLAMA_MODEL="llama")
    assert "costs nothing" in settings_gui.moderator_warning()


def test_out_of_credit_is_recognised_for_each_provider(app):
    e = app.engine
    assert e.ai_out_of_credit(RuntimeError("Your credit balance is too low to access the Anthropic API"))
    assert e.ai_out_of_credit(RuntimeError("Error code: 429 - insufficient_quota: You exceeded your current quota"))
    assert e.ai_out_of_credit(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert not e.ai_out_of_credit(RuntimeError("timed out"))


def test_moderator_names_the_provider_when_out_of_credit(app, monkeypatch):
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="sk-test", AI_MODERATOR_TRACKS="strict")
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}

    def broke(*a, **k):
        raise RuntimeError("Error code: 429 - insufficient_quota")
    monkeypatch.setattr(app.engine, "ai_request", broke)
    r = app.Lines()
    app.engine.moderate([("k1", "A", "B"), ("k2", "C", "D")], "X - Y", report=r)
    assert r.has("your OpenAI account is out of credit"), r.text()
    assert not r.has("Anthropic"), r.text()


def test_no_anthropic_credit_wording_left_in_the_app():
    here = pathlib.Path(__file__).resolve().parent.parent
    for name in ("settings_gui.py", "engine.py", "voice.py", "console_query.py", "ai_usage.py"):
        text = (here / name).read_text(encoding="utf-8")
        for phrase in ("Anthropic credit", "Anthropic API, which", "Anthropic key in 24bit7",
                       "Anthropic credit balance", "Haiku on Anthropic"):
            assert phrase not in text, (name, phrase)
