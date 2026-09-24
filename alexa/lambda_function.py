"""
needle drop - the Alexa skill for 24bit7.

"Alexa, open needle drop"  -> one chime, then it listens for one command:
    "songs by <artist>"     Artist's Top Tracks
    "music like <artist>"   Similar Artists
    "genre <anything>"      Vibe Playlist
Or in one go: "Alexa, ask needle drop for music like Agnes Obel".

The command goes to 24bit7 on your PC, with your key and the ID of the speaker
that heard it, and 24bit7 plays the playlist on that speaker's zone.
  started  -> two chimes
  pending  -> "Please wait, request pending." (runs after the current build)
  problem  -> Alexa says what's wrong

Paste this into the Code tab of an Alexa-hosted (Python) skill, fill in the
three settings below, then Save and Deploy.
"""

import json
import logging
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.skill_builder import SkillBuilder

# ---- Your settings --------------------------------------------------------------
# Your Tailscale Funnel address, e.g. https://desktop-abc123.tailxxxx.ts.net
BIT7_URL = "https://YOUR-PC.YOUR-TAILNET.ts.net"
# The key from 24bit7's Settings > Voice (Copy button). Keep it out of anything public.
BIT7_KEY = "PASTE-YOUR-KEY-HERE"
# A sound from the Alexa Skills Kit Sound Library: pick one on the library page and
# paste just the address from its code, e.g. "soundbank://soundlibrary/....". Leave it
# empty and Alexa says "Ready" and "OK" instead of chiming.
CHIME = ""
# ----------------------------------------------------------------------------------

TIMEOUT = 6   # seconds; Alexa gives the whole skill about eight
HELP = "Say songs by, then an artist. Music like, then an artist. Or genre, then any style you like."
INTENTS = {"SongsByIntent": "songs_by", "MusicLikeIntent": "music_like", "GenreIntent": "genre"}

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def chimes(count, fallback):
    if not CHIME:
        return fallback
    return '<break time="200ms"/>'.join(f'<audio src="{CHIME}"/>' for _ in range(count))


def send(intent, value, device):
    """Sends one command to 24bit7. Returns (status, speech)."""
    body = json.dumps({"intent": intent, "value": value, "device": device}).encode("utf-8")
    req = urllib.request.Request(BIT7_URL.rstrip("/") + "/command", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-24bit7-Key": BIT7_KEY})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            reply = json.loads(r.read())
        return reply.get("status", "problem"), reply.get("speech", "")
    except urllib.error.HTTPError as e:
        log.info("24bit7 replied HTTP %s", e.code)
        if e.code == 401:
            return "problem", "24bit7 didn't accept the key. Check the key in the skill matches the one in 24bit7."
        return "problem", "24bit7 isn't answering. Is it running on the media PC?"
    except Exception as e:
        log.info("24bit7 unreachable: %s", e)
        return "problem", "24bit7 isn't answering. Is it running on the media PC?"


class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        return (handler_input.response_builder
                .speak(chimes(1, "Ready."))
                .ask(HELP)
                .response)


class CommandHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return any(ask_utils.is_intent_name(name)(handler_input) for name in INTENTS)

    def handle(self, handler_input):
        intent = INTENTS[ask_utils.get_intent_name(handler_input)]
        value = ask_utils.get_slot_value(handler_input, "query") or ""
        device = handler_input.request_envelope.context.system.device.device_id
        status, speech = send(intent, value, device)
        if status == "started":
            speech = chimes(2, "OK.")
        else:
            speech = escape(speech)
        return handler_input.response_builder.speak(speech).set_should_end_session(True).response


class HelpHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)
                or ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input))

    def handle(self, handler_input):
        return handler_input.response_builder.speak(HELP).ask(HELP).response


class StopHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return any(ask_utils.is_intent_name(name)(handler_input) for name in
                   ("AMAZON.StopIntent", "AMAZON.CancelIntent", "AMAZON.NavigateHomeIntent"))

    def handle(self, handler_input):
        return handler_input.response_builder.set_should_end_session(True).response


class SessionEndedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


class ErrorHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        log.error(exception, exc_info=True)
        return (handler_input.response_builder
                .speak("Sorry, something went wrong in the skill.")
                .set_should_end_session(True)
                .response)


sb = SkillBuilder()
for handler in (LaunchHandler(), CommandHandler(), HelpHandler(), StopHandler(), SessionEndedHandler()):
    sb.add_request_handler(handler)
sb.add_exception_handler(ErrorHandler())

lambda_handler = sb.lambda_handler()
