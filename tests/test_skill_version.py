"""
The skill says which version it is (Ben, 22 Nov 2026). Every user has a skill of their own, pasted by hand, and when
a release changes the skill's files only the release notes said to paste them again. Now each command carries the
skill's number, and 24bit7, which knows the number it ships, says once in the console when an older skill calls in,
and on Settings > Voice Commands. Alexa says nothing about it.
"""

import hashlib
import json
import os
import urllib.request

from test_voice import alexa, KITCHEN   # noqa: F401  (the mock Alexa fixture)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The skill's files as they were when the number was last raised. When this test fails: raise SKILL_VERSION in
# alexa/lambda_function.py and in voice.py, say what's new in voice.SKILL_NEWS (with its German), then put the new
# number and fingerprint here.
RECORDED = (2, "7267e29270a3dea9")


def fingerprint():
    h = hashlib.sha256()
    for name in ("lambda_function.py", "interaction_model.json"):
        with open(os.path.join(REPO, "alexa", name), "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


def command(app, body):
    req = urllib.request.Request(f"http://127.0.0.1:{app.engine.VOICE_PORT}/command", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-24bit7-Key": app.engine.VOICE_KEY},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_the_number_goes_up_when_the_skills_files_change(app, alexa):
    import voice
    assert alexa.skill.SKILL_VERSION == voice.SKILL_VERSION, "the skill's number and the one 24bit7 expects are one number"
    assert voice.SKILL_VERSION in voice.SKILL_NEWS, "what's new in this skill, for the note"
    assert (voice.SKILL_VERSION, fingerprint()) == RECORDED, \
        "the skill's files changed: raise SKILL_VERSION (see the note above RECORDED), or users are never told to paste them"


def test_the_shipped_skill_is_up_to_date_and_nothing_is_said(app, alexa):
    import voice
    assert voice.skill_shown() == "", "no skill has called in yet: nothing to say"
    alexa.say("PauseMusicIntent")
    assert voice.skill_state() == "current"
    assert voice.skill_shown() == "Skill: up to date."
    assert not app.printed.has("Alexa skill is older"), app.printed.text()


def test_an_older_skill_is_said_once_in_the_console_and_on_the_page(app, alexa):
    import voice
    for _ in range(2):   # as the skill before the number existed sent it
        reply = command(app, {"intent": "pause", "value": "", "device": KITCHEN})
    assert "skill" not in reply.get("speech", "").lower(), "Alexa says nothing about it"
    notes = [line for line in app.printed if "Alexa skill is older" in line]
    assert len(notes) == 1, app.printed.text()
    assert voice.SKILL_NEWS[voice.SKILL_VERSION] in notes[0] and "paste" in notes[0].lower()
    assert voice.skill_state() == "old" and voice.skill_shown().startswith("Skill: older than this 24bit7.")
    alexa.say("PauseMusicIntent")   # the new files pasted: the next command says so
    assert voice.skill_state() == "current" and voice.skill_shown() == "Skill: up to date."


def test_settings_own_test_button_isnt_a_skill(app, alexa):
    import voice
    command(app, {"intent": "pause", "value": "", "device": voice.TEST_DEVICE})
    assert voice.skill_state() is None and voice.skill_shown() == ""
    assert not app.printed.has("Alexa skill is older")
