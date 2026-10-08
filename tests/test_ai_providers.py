"""
AI providers (Settings > Keys > AI): Anthropic, OpenAI, Google Gemini and Ollama.
None of the three new providers can be reached from a test, so their replies are faked
in the shapes their documentation gives. Anthropic keeps its existing tests.
"""

import importlib
import json

import pytest
import requests


class Reply:
    def __init__(self, data, status=200):
        self.status_code, self._data = status, data
        self.text = json.dumps(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def openai_reply(text, finish="stop", prompt=120, cached=20, completion=40):
    return Reply({"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}],
                  "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                            "prompt_tokens_details": {"cached_tokens": cached}}})


def capture_post(monkeypatch, *replies):
    sent = []
    queue = list(replies)

    def post(url, headers=None, json=None, timeout=None, **kw):
        sent.append({"url": url, "headers": headers or {}, "json": json, "timeout": timeout})
        return queue.pop(0) if len(queue) > 1 else queue[0]
    monkeypatch.setattr(requests, "post", post)
    return sent


# --- settings ---------------------------------------------------------------------

def test_provider_settings_load_with_safe_defaults(app):
    e = app.engine
    assert e.AI_PROVIDER == "anthropic" and e.OLLAMA_URL == "http://127.0.0.1:11434"
    app.set_env(AI_PROVIDER="OpenAI", OPENAI_API_KEY=" sk-o ", OLLAMA_URL="http://box:11434/")
    assert (e.AI_PROVIDER, e.OPENAI_API_KEY, e.OLLAMA_URL) == ("openai", "sk-o", "http://box:11434")
    app.set_env(AI_PROVIDER="something-else")
    assert e.AI_PROVIDER == "anthropic"


def test_configured_and_what_is_missing(app):
    e = app.engine
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="")
    assert not e.ai_configured() and e.ai_missing_text() == "an OpenAI key"
    app.set_env(AI_PROVIDER="gemini", GEMINI_API_KEY="")
    assert e.ai_missing_text() == "a Google Gemini key"
    app.set_env(AI_PROVIDER="ollama", OLLAMA_MODEL="")
    assert not e.ai_configured() and e.ai_missing_text() == "an Ollama model"
    app.set_env(OLLAMA_MODEL="gemma3:4b")
    assert e.ai_configured() and e.ai_model("main") == e.ai_model("quick") == "gemma3:4b"
    app.set_env(AI_PROVIDER="anthropic")
    assert e.ai_missing_text() == "an Anthropic key" and e.ai_configured()


def test_ai_playlist_names_the_missing_key(app):
    app.set_env(AI_PROVIDER="gemini", GEMINI_API_KEY="")
    assert "a Google Gemini key" in app.engine.vibe_blocker()


# --- OpenAI and Gemini ------------------------------------------------------------------

def test_openai_request_and_usage(app, monkeypatch):
    e = app.engine
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="sk-o")
    sent = capture_post(monkeypatch, openai_reply('```json\n["Air", "Massive Attack"]\n```'))
    assert e.ai_ask_list("prompt", feature="Similar Artists (AI source)") == ["Air", "Massive Attack"]
    body = sent[0]["json"]
    assert sent[0]["url"] == e.OPENAI_CHAT_URL and sent[0]["headers"]["Authorization"] == "Bearer sk-o"
    assert body["model"] == "gpt-6.1-sol" and body["reasoning_effort"] == "low"
    assert body["max_completion_tokens"] == 1500 + e.AI_REASONING_ROOM
    row = e.db().execute("SELECT model, input, cache_read, output FROM ai_usage").fetchone()
    assert tuple(row) == ("gpt-6.1-sol", 100, 20, 40)


def test_gemini_goes_to_its_openai_compatible_address(app, monkeypatch):
    e = app.engine
    app.set_env(AI_PROVIDER="gemini", GEMINI_API_KEY="g-key")
    sent = capture_post(monkeypatch, openai_reply('[{"artist": "Air", "track": "La Femme d\'Argent"}]'))
    assert e.ai_ask_json("prompt") == [{"artist": "Air", "track": "La Femme d'Argent"}]
    assert sent[0]["url"] == e.GEMINI_CHAT_URL and sent[0]["json"]["model"] == "gemini-3.8-flash"
    assert "max_tokens" in sent[0]["json"] and "max_completion_tokens" not in sent[0]["json"]


def test_cut_short_reply_is_salvaged(app, monkeypatch):
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="sk-o")
    capture_post(monkeypatch, openai_reply('[{"artist": "Air", "track": "Sexy Boy"}, {"artist": "Ai', "length"))
    assert app.engine.ai_ask_json("prompt") == [{"artist": "Air", "track": "Sexy Boy"}]


def test_refused_key_says_so(app, monkeypatch):
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="sk-bad")
    capture_post(monkeypatch, Reply({"error": {"message": "Incorrect API key provided"}}, 401))
    assert app.engine.ai_ask_list("prompt") == []
    assert app.printed.has("OpenAI refused the key (401)")


def test_moderator_uses_the_quick_model_with_its_instructions(app, monkeypatch):
    e = app.engine
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="sk-o", AI_MODERATOR="balanced")
    sent = capture_post(monkeypatch, openai_reply(json.dumps({"remove": [{"number": 2, "artist": "Slayer", "title": "Raining Blood",
                                                                    "reason": "too loud"}]})))
    tracks = [("1", "Air", "Alpha"), ("2", "Slayer", "Raining Blood"), ("3", "Moby", "Porcelain")]
    out = app.Lines()
    removed = e.moderate(tracks, "Air - Sexy Boy", report=out, level="balanced")
    body = sent[0]["json"]
    assert body["model"] == "gpt-6-luna" and body["reasoning_effort"] == "none"
    assert body["messages"][0]["role"] == "system" and "moderator" in body["messages"][0]["content"].lower()
    assert removed == {"2"} and out.has("Removed Slayer - Raining Blood")


# --- Ollama -------------------------------------------------------------------------------

def test_ollama_request(app, monkeypatch):
    e = app.engine
    app.set_env(AI_PROVIDER="ollama", OLLAMA_MODEL="gemma3:4b")
    monkeypatch.setattr(e, "ollama_models", lambda url=None: ["gemma3:4b", "llama3.2:3b"])
    sent = capture_post(monkeypatch, Reply({"message": {"role": "assistant", "content": '["Air"]'},
                                            "done_reason": "stop", "prompt_eval_count": 90, "eval_count": 12}))
    assert e.ai_ask_list("prompt", feature="Similar Artists (AI source)") == ["Air"]
    assert sent[0]["url"] == "http://127.0.0.1:11434/api/chat"
    body = sent[0]["json"]
    assert body["model"] == "gemma3:4b" and body["stream"] is False
    assert body["options"]["num_ctx"] == e.OLLAMA_CONTEXT
    row = e.db().execute("SELECT model, input, output FROM ai_usage").fetchone()
    assert tuple(row) == ("gemma3:4b", 90, 12)


def test_ollama_not_running_or_model_missing(app, monkeypatch):
    e = app.engine
    app.set_env(AI_PROVIDER="ollama", OLLAMA_MODEL="gemma3:4b")
    monkeypatch.setattr(e, "ollama_models", lambda url=None: None)
    assert "isn't answering at http://127.0.0.1:11434" in e.ollama_check()
    monkeypatch.setattr(e, "ollama_models", lambda url=None: ["llama3.2:3b"])
    assert "ollama pull gemma3:4b" in e.ollama_check()
    assert e.ai_ask_list("prompt") == [] and app.printed.has("ollama pull gemma3:4b")
    monkeypatch.setattr(e, "ollama_models", lambda url=None: ["gemma3:4b:latest", "gemma3:4b"])
    assert e.ollama_check() is None


def test_ollama_models_lists_what_is_installed(app, monkeypatch):
    e = app.engine
    monkeypatch.setattr(requests, "get", lambda url, timeout=None, **kw: Reply(
        {"models": [{"name": "llama3.2:3b"}, {"name": "Gemma3:4b"}]}))
    assert e.ollama_models("http://box:11434") == ["Gemma3:4b", "llama3.2:3b"]

    def refused(url, timeout=None, **kw):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(requests, "get", refused)
    assert e.ollama_models() is None


def test_console_query_is_off_with_ollama(app, monkeypatch):
    e = app.engine
    app.set_env(AI_PROVIDER="ollama", OLLAMA_MODEL="gemma3:4b", USE_AI="1")
    assert e.ai_enabled() and not e.console_query_ready()
    console_query = importlib.import_module("console_query")
    got = {}
    monkeypatch.setattr(console_query.threading, "Thread",
                        lambda target, daemon=None, **kw: type("T", (), {"start": lambda self: target()})())
    console_query.ask("Why?", "console", None, lambda answer, error: got.update(answer=answer, error=error))
    assert got["answer"] is None and "isn't available with Ollama" in got["error"]


# --- costs --------------------------------------------------------------------------------

def test_costs_follow_the_provider(app):
    ai_usage = importlib.import_module("ai_usage")
    assert ai_usage.cost("gpt-6.1-sol", 1_000_000, 0, 0, 0) == pytest.approx(2.00)
    assert ai_usage.cost("gemini-3.5-flash-lite", 0, 0, 0, 1_000_000) == pytest.approx(2.50)
    assert ai_usage.cost("gemma3:4b", 5_000, 0, 0, 5_000) == 0
    assert "OpenAI's standard API rates" in ai_usage.rates_line("openai")
    assert "GPT-6.1 Sol $2 in and $10 out" in ai_usage.rates_line("openai")
    assert "Gemini 3.8 Flash" in ai_usage.rates_line("gemini")
    assert "costs nothing" in ai_usage.rates_line("ollama") and ai_usage.pricing_page("ollama") is None
    app.set_env(AI_PROVIDER="openai", OPENAI_API_KEY="sk-o")
    guide = {f: c for f, _, c, _, _ in ai_usage.guide()}
    assert guide["AI Moderator"] == pytest.approx(ai_usage.cost("gpt-6-luna", 1000, 0, 0, 300))


# --- Settings -------------------------------------------------------------------------------

def test_settings_provider_switch(app, monkeypatch):
    import tkinter as tk
    from conftest import load_gui
    tray = importlib.import_module("tray")
    monkeypatch.setattr(tray, "available", lambda: False)
    monkeypatch.setattr(tray, "start", lambda *a, **k: False)
    e = app.engine
    monkeypatch.setattr(e, "ollama_models", lambda url=None: ["gemma3:4b", "llama3.2:3b"])
    gui = load_gui(app.folder)
    root = tk.Tk()
    try:
        nb = gui.TabbedPane(root, font=("Segoe UI", 10, "bold"), pad=(16, 6))
        nb.pack()
        settings = gui.SettingsTab(nb)
        root.update()
        assert settings._ai_provider() == "anthropic"
        assert settings.ai_field_frames["anthropic"].winfo_manager()
        assert not settings.ai_field_frames["ollama"].winfo_manager()
        settings.ai_provider_var.set("Ollama (Local)")
        settings._ai_provider_chosen()
        root.update()
        assert settings.ai_field_frames["ollama"].winfo_manager()
        assert not settings.ai_field_frames["anthropic"].winfo_manager()
        assert settings.vars["OLLAMA_MODEL"].get() == "gemma3:4b", "Refresh fills an empty model in"
        e.refresh_settings_if_changed()
        assert e.AI_PROVIDER == "ollama" and e.OLLAMA_MODEL == "gemma3:4b"
        assert "costs nothing" in settings.usage_rates.cget("text")
        assert not settings.usage_link.winfo_manager()
        assert e.ANTHROPIC_API_KEY == "test-anthropic", "the other keys stay saved"
        settings.ai_provider_var.set("OpenAI")
        settings._ai_provider_chosen()
        root.update()
        assert settings.usage_link.cget("text") == "OpenAI's pricing page"
        assert settings.ai_untested.winfo_manager()
    finally:
        import gc
        settings = None
        gc.collect()
        root.destroy()
