"""
Settings > About names every music source and every AI provider, so none is left out when one is added.
"""


def test_about_intro_names_every_source_and_ai_provider(app):
    import settings_gui
    intro = settings_gui.ABOUT_INTRO
    for key, name in settings_gui.SOURCE_NAMES:
        if key != "ai":
            assert name in intro, f"{name} is missing from the About intro"
    for key, name in app.engine.AI_PROVIDERS:
        assert name.split(" (")[0] in intro, f"{name} is missing from the About intro"


def test_credits_name_every_source_and_ai_provider(app):
    import settings_gui
    credits = " ".join(name for name, _url in settings_gui.CREDITS)
    for key, name in settings_gui.SOURCE_NAMES:
        if key != "ai":
            assert name in credits, f"{name} is missing from Credits"
    for key, name in app.engine.AI_PROVIDERS:
        assert name.split(" (")[0] in credits, f"{name} is missing from Credits"
