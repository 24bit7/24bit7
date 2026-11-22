"""Settings > Voice Commands says whether the skill that last called in is up to date (22 Nov 2026)."""

from test_gui import ui  # noqa: F401  (the GUI fixture)


def test_voice_commands_says_when_the_skill_is_older(app, ui):
    import voice
    s = ui.settings
    assert "Skill" not in s.voice_status.cget("text"), "no skill has called in: only the listener's status"
    voice._note_skill({"intent": "pause", "device": "amzn1.ask.device.KITCHEN"})   # as a skill from before the number
    s.voice_status.config(text=s._voice_status_text())   # what the page does each time it's shown
    lines = s.voice_status.cget("text").split("\n")
    assert len(lines) == 2 and lines[1].startswith("Skill: older than this 24bit7. Paste the two new files"), lines
    voice._note_skill({"intent": "pause", "device": "amzn1.ask.device.KITCHEN", "skill": voice.SKILL_VERSION})
    assert s._voice_status_text().split("\n")[1] == "Skill: up to date."
    assert not ui.errors, ui.errors[0]
