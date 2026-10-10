"""AI list replies (Similar Artists and Top Tracks AI sources): words around the list,
wrapped lists, honest 'cut short' wording, and one retry."""


def ask(app, *replies):
    app.ai.script = list(replies)
    lines = app.Lines()
    app.engine.OUTPUT_HOOK = lines
    names = app.engine.ai_ask_list("Name artists", feature="Similar Artists (AI source)")
    return names, lines


def test_words_around_the_list_are_ignored(app):
    names, lines = ask(app, ('Sure! Here are some artists:\n["Badfinger", "Big Star"]\nEnjoy.', "end_turn"))
    assert names == ["Badfinger", "Big Star"] and not lines.has("Problem")


def test_a_wrapped_list_is_accepted(app):
    names, _ = ask(app, ('{"artists": ["Badfinger", "Big Star"]}', "end_turn"))
    assert names == ["Badfinger", "Big Star"]


def test_cut_short_only_when_out_of_tokens(app):
    names, lines = ask(app, ('["Badfinger", "Big Star", "The Ra', "max_tokens"))
    assert names == ["Badfinger", "Big Star"] and lines.has("cut short")


def test_partly_unreadable_otherwise(app):
    names, lines = ask(app, ('["Badfinger", "Big Star", oops "Raspberries"', "end_turn"))
    assert "Badfinger" in names and lines.has("partly unreadable") and not lines.has("cut short")


def test_chatter_quotes_are_not_names(app):
    names, _ = ask(app, ('I "think" these fit: ["Badfinger", "Big Sta', "max_tokens"))
    assert names == ["Badfinger"] and "think" not in names


def test_unreadable_then_good_retries_once(app):
    names, lines = ask(app, ("I'm not sure what you mean.", "end_turn"), ('["Badfinger"]', "end_turn"))
    assert names == ["Badfinger"] and lines.has("trying once more") and len(app.ai.calls) == 2


def test_gives_up_after_two(app):
    names, lines = ask(app, ("no", "end_turn"), ("still no", "end_turn"))
    assert names == [] and lines.has("Problem: the AI request didn't work") and len(app.ai.calls) == 2
    assert app.engine.AI_LAST_ERROR == "reply couldn't be read"


def test_failed_request_retries(app, monkeypatch):
    real, calls = app.engine.ai_request, {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("overloaded")
        return real(*a, **k)
    monkeypatch.setattr(app.engine, "ai_request", flaky)
    app.ai.script = [('["Badfinger"]', "end_turn")]
    assert app.engine.ai_ask_list("Name artists") == ["Badfinger"] and calls["n"] == 2
