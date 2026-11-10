"""
needle drop - the Alexa skill for 24bit7.

"Alexa, open needle drop"  -> "Ready", then it listens for one command:
    "songs by <artist>"     Artist's Top Tracks
    "music like <artist>"   Similar Artists
    "genre <anything>"      Vibe Playlist
    "only <artist, mood>"   AI Playlist from one artist's tracks ("only chill Led Zeppelin")
    "tracks like <song>"    Similar Tracks ("tracks like <song> by <artist>" works too)
    "album <name>"          plays that album now ("album <name> by <artist>" if several share it)
    "song <title>"          plays that song now, then stops ("song <title> by <artist>" works too)
    "playlist <name>"       plays one of your JRiver playlists or smartlists now
    "shuffle songs by <artist>"  every track by them, shuffled, now
    "skip" / "next"         the next track on this device's zone
    "who is this"           says the track, artist and album playing there
    "more like this"        Similar Tracks from what's playing, queued after it
    "more artists like this" Similar Artists from what's playing, queued after it
    "radio <station>"       plays one of your Radio stations ("radio" alone: it lists the last five played,
                            and you answer with a name or "the second one")
    "top up"                asks what with; the next command goes into what's left of Playing Now
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
SHORT = "Say list commands to hear them."
NOT_CAUGHT = "Sorry, I didn't catch that. " + SHORT
COMMANDS = ("To build a playlist: songs by, music like, or tracks like, then an artist or a song, "
            "or genre, then any style, or only, then an artist and a mood. "
            "To play now: album, song, or playlist, then its name, or shuffle songs by, then an artist. "
            "For what's playing: skip, who is this, more like this, more artists like this, keep it going, "
            "or stop, pause or resume the music. "
            "Radio, then a station, or radio alone to hear your last five. "
            "Top up, then any command, to add to what's playing instead of replacing it. "
            "Switch, or switch to, then a zone. "
            "And multiroom, so the speakers follow, or single room, to keep the music in this room only.")
REPROMPT = {"playlist": "Say by, then the folder.", "zone": "Say to, then the zone.",
            "station": "Say the station's name, or its number.",
            "top_up": "Say music like, songs by, radio, or playlist, then what you'd like."}
INTENTS = {"SongsByIntent": "songs_by", "MusicLikeIntent": "music_like", "GenreIntent": "genre", "OnlyIntent": "only",
           "TracksLikeIntent": "tracks_like",
           "AlbumIntent": "album", "SongIntent": "song", "PlaylistIntent": "playlist",
           "ShuffleIntent": "shuffle", "RadioIntent": "radio", "TopUpIntent": "top_up"}
ZONE_INTENTS = {"SkipIntent": "skip", "WhoIsThisIntent": "who_is_this", "MoreLikeThisIntent": "more_like",
                "MoreArtistsLikeThisIntent": "more_artists",
                "SwitchZonesIntent": "switch_zones", "KeepGoingIntent": "keep_going",
                "StopMusicIntent": "stop", "PauseMusicIntent": "pause", "ResumeMusicIntent": "resume",
                "MultiroomIntent": "multiroom", "SingleRoomIntent": "single_room"}

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def chimes(count, fallback):
    if not CHIME:
        return fallback
    return '<break time="200ms"/>'.join(f'<audio src="{CHIME}"/>' for _ in range(count))


def topping_up(handler_input):
    """True after "top up" in this conversation: the command that follows goes into what's left of Playing Now."""
    return bool(handler_input.attributes_manager.session_attributes.get("top_up"))


def send(intent, value, device, top_up=False):
    """Sends one command to 24bit7. Returns (status, speech, the whole reply)."""
    command = {"intent": intent, "value": value, "device": device}
    if top_up:
        command["top_up"] = True
    body = json.dumps(command).encode("utf-8")
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
        if reply.get("ask") == "top_up":
            session["top_up"] = True
        return builder.speak(escape(speech)).ask(REPROMPT.get(reply.get("ask"), "Say by, then the artist.")).response
    speech = f'<audio src="{ACK_TONE}"/>' if status == "started" else escape(speech)
    return builder.speak(speech).set_should_end_session(True).response


class LaunchHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        return (handler_input.response_builder
                .speak(chimes(1, "Ready."))
                .ask(SHORT)
                .response)


def heard_words(handler_input):
    """The words in the request's slot: "query" for most intents, "station" for Radio and Station (10 Nov 2026:
    the console wants one slot name to mean one slot type across the model, and STATION is its own type)."""
    return (ask_utils.get_slot_value(handler_input, "query")
            or ask_utils.get_slot_value(handler_input, "station") or "")


class CommandHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return any(ask_utils.is_intent_name(name)(handler_input) for name in INTENTS)

    def handle(self, handler_input):
        intent = INTENTS[ask_utils.get_intent_name(handler_input)]
        value = heard_words(handler_input)
        device = handler_input.request_envelope.context.system.device.device_id
        return respond(handler_input, *send(intent, value, device, topping_up(handler_input)))


class ZoneHandler(AbstractRequestHandler):
    """Skip, who is this, more like this: no slot, they act on what this device's zone is playing."""
    def can_handle(self, handler_input):
        return any(ask_utils.is_intent_name(name)(handler_input) for name in ZONE_INTENTS)

    def handle(self, handler_input):
        intent = ZONE_INTENTS[ask_utils.get_intent_name(handler_input)]
        device = handler_input.request_envelope.context.system.device.device_id
        return respond(handler_input, *send(intent, "", device))


class ByArtistHandler(AbstractRequestHandler):
    """The answer to "Which artist?" after several albums or songs shared a title."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("ByArtistIntent")(handler_input)

    def handle(self, handler_input):
        session = handler_input.attributes_manager.session_attributes
        kind, title = session.get("ask", "album"), session.get("title")
        artist = ask_utils.get_slot_value(handler_input, "query") or ""
        if not title:
            return handler_input.response_builder.speak(NOT_CAUGHT).set_should_end_session(False).response
        device = handler_input.request_envelope.context.system.device.device_id
        return respond(handler_input, *send(kind, f"{title} by {artist}", device, topping_up(handler_input)))


class StationHandler(AbstractRequestHandler):
    """The answer to "Which station?": a name, or "the second one"."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("StationIntent")(handler_input)

    def handle(self, handler_input):
        session = handler_input.attributes_manager.session_attributes
        heard = heard_words(handler_input)
        if session.get("ask") != "station" or not heard:
            return handler_input.response_builder.speak(NOT_CAUGHT).set_should_end_session(False).response
        device = handler_input.request_envelope.context.system.device.device_id
        return respond(handler_input, *send("radio", heard, device, topping_up(handler_input)))


class SwitchToHandler(AbstractRequestHandler):
    """"Switch to <zone>", or "to the <zone>" as the answer to "Which zone?"."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("SwitchToIntent")(handler_input)

    def handle(self, handler_input):
        zone = ask_utils.get_slot_value(handler_input, "query") or ""
        device = handler_input.request_envelope.context.system.device.device_id
        return respond(handler_input, *send("switch_zones", zone, device))


class HelpHandler(AbstractRequestHandler):
    """List commands and Help: the list once, then one more listen with no reprompt."""
    def can_handle(self, handler_input):
        return (ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)
                or ask_utils.is_intent_name("ListCommandsIntent")(handler_input))

    def handle(self, handler_input):
        return handler_input.response_builder.speak(COMMANDS).set_should_end_session(False).response


class FallbackHandler(AbstractRequestHandler):
    """Not a command: one short line, never the whole list, never repeated."""
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.speak(NOT_CAUGHT).set_should_end_session(False).response


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
for handler in (LaunchHandler(), CommandHandler(), ZoneHandler(), ByArtistHandler(), StationHandler(), SwitchToHandler(),
                HelpHandler(), FallbackHandler(), StopHandler(), SessionEndedHandler()):
    sb.add_request_handler(handler)
sb.add_exception_handler(ErrorHandler())

lambda_handler = sb.lambda_handler()
