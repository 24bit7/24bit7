"""
needle drop - the Alexa skill for 24bit7.

"Alexa, open needle drop"  -> "Ready", then it listens for one command:
    "songs by <artist>"     Artist's Top Tracks
    "music like <artist>"   Similar Artists
    "genre <anything>"      Vibe Playlist
    "tracks like <song>"    Similar Tracks ("tracks like <song> by <artist>" works too)
    "album <name>"          plays that album now ("album <name> by <artist>" if several share it)
    "song <title>"          plays that song now, then stops ("song <title> by <artist>" works too)
    "playlist <name>"       plays one of your JRiver playlists or smartlists now
    "shuffle songs by <artist>"  every track by them, shuffled, now
Or in one go: "Alexa, ask needle drop for music like Agnes Obel".
If several albums or songs share a title, Alexa asks which, and you answer "by <artist>".
No phrase starts with "play", so Alexa isn't tempted to hand it to a music service.

The command goes to 24bit7 on your PC, with your key and the ID of the speaker
that heard it, and 24bit7 plays the playlist on that speaker's zone.
  started  -> a short tone (ACK_TONE), then the music
  pending  -> "Please wait, request pending." (runs after the current build)
  ask      -> Alexa asks which album, and listens for "by <artist>"
  problem  -> Alexa says what's wrong

In the Code tab of an Alexa-hosted (Python) skill: create skill_settings.py next to
this file and fill in your address and key there, then paste this file over
lambda_function.py, Save and Deploy. Your address and key live only in
skill_settings.py, so this file can be shown or shared safely.
"""

import json
import logging
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

import ask_sdk_core.utils as ask_utils
from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.skill_builder import SkillBuilder

from skill_settings import BIT7_KEY, BIT7_URL, CHIME   # your address, key and chime

try:   # optional: a different acknowledgement tone, set in skill_settings.py
    from skill_settings import ACK_TONE
except ImportError:
    ACK_TONE = "soundbank://soundlibrary/musical/amzn_sfx_electronic_beep_02"

TIMEOUT = 6   # seconds; Alexa gives the whole skill about eight
HELP = ("Say songs by, music like, or shuffle songs by, then an artist. Genre, then any style you like. "
        "Tracks like, then a song. Or album, song, or playlist, then its name.")
INTENTS = {"SongsByIntent": "songs_by", "MusicLikeIntent": "music_like", "GenreIntent": "genre",
           "TracksLikeIntent": "tracks_like",
           "AlbumIntent": "album", "SongIntent": "song", "PlaylistIntent": "playlist",
           "ShuffleIntent": "shuffle"}

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def chimes(count, fallback):
    if not CHIME:
        return fallback
    return '<break time="200ms"/>'.join(f'<audio src="{CHIME}"/>' for _ in range(count))


def send(intent, value, device):
    """Sends one command to 24bit7. Returns (status, speech, the whole reply)."""
    body = json.dumps({"intent": intent, "value": value, "device": device}).encode("utf-8")
    req = urllib.request.Request(BIT7_URL.rstrip("/") + "/command", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "X-24bit7-Key": BIT7_KEY})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            reply = json.loads(r.read())
        return reply.get("status", "problem"), reply.get("speech", ""), reply
    except urllib.error.HTTPError as e:
        log.info("24bit7 replied HTTP %s", e.code)
        if e.code == 401:
            return "problem", "24bit7 didn't accept the key. Check the key in the skill matches the one in 24bit7.", {}
        return "problem", "24bit7 isn't answering. Is it running on the media PC?", {}
    except Exception as e:
        log.info("24bit7 unreachable: %s", e)
        return "problem", "24bit7 isn't answering. Is it running on the media PC?", {}


def respond(handler_input, status, speech, reply):
    """A tone when it starts; a question that keeps listening; otherwise Alexa says what's wrong."""
    builder = handler_input.response_builder
    if status == "ask":
        session = handler_input.attributes_manager.session_attributes
        session["ask"], session["title"] = reply.get("ask", "album"), reply.get("title", "")
        return builder.speak(escape(speech)).ask("Say by, then the artist.").response
    speech = f'<audio src="{ACK_TONE}"/>' if status == "started" else escape(speech)
    return builder.speak(speech).set_should_end_session(True).response


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
        return respond(handler_input, *send(intent, value, device))


class ByArtistHandler(AbstractRequestHandler):
    """The answer to "Which artist?" after several albums or songs shared a title."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ByArtistIntent")(handler_input)

    def handle(self, handler_input):
        session = handler_input.attributes_manager.session_attributes
        kind, title = session.get("ask", "album"), session.get("title")
        artist = ask_utils.get_slot_value(handler_input, "query") or ""
        if not title:
            return handler_input.response_builder.speak(HELP).ask(HELP).response
        device = handler_input.request_envelope.context.system.device.device_id
        return respond(handler_input, *send(kind, f"{title} by {artist}", device))


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
for handler in (LaunchHandler(), CommandHandler(), ByArtistHandler(), HelpHandler(), StopHandler(),
                SessionEndedHandler()):
    sb.add_request_handler(handler)
sb.add_exception_handler(ErrorHandler())

lambda_handler = sb.lambda_handler()
