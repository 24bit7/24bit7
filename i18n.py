"""
24bit7 - languages.

The code keeps its English. t() looks the English up in locale\\<code>.json and
falls back to the English itself when there's no translation, so nothing ever
breaks for want of one. Text with a number or a name in it stays one sentence
with {blanks}, filled by t(text, n=3), so each language can put them where its
own word order wants them, and tn() picks the sentence for one or for many.
English kept in a constant is marked with N_() and passed through t() where
it's shown.

The language is chosen in Settings > Other and set once, as 24bit7 starts:
switching it restarts the app, so the screens never mix two languages.
"""

import json
import os
import sys

LANGUAGES = [("en", "English"), ("de", "Deutsch")]
# What Settings > Other offers: a language joins once its screens, console and manual are translated.
OFFERED = ["en", "de"]

LANGUAGE = "en"
_table = {}


def locale_dir():
    """locale\\ beside the code, or inside the packaged app's own files."""
    return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "locale")


def load_table(code):
    """A language's translations, English to that language. Empty for English or a missing file."""
    if code == "en":
        return {}
    try:
        with open(os.path.join(locale_dir(), f"{code}.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def set_language(code):
    """Called once as 24bit7 starts. An unknown code means English."""
    global LANGUAGE, _table
    LANGUAGE = code if code in dict(LANGUAGES) else "en"
    _table = load_table(LANGUAGE)


def N_(text):
    """
    Marks English kept in a constant (a list, a title at the top of a file) for translation, and
    returns it unchanged: the file is read before the language is set, so it's t()'d where it's shown.
    """
    return text


# What the AI is told so its answers (Console Query, the AI Usage question, AI Playlist ideas) come back in the
# chosen language. The instructions themselves stay English: the models follow them best.
REPLY_IN = {"de": "Write your answer in German, addressing the person informally (du). Keep song, artist and album "
                  "names exactly as they are."}


def reply_line():
    """'' in English; otherwise a line for the end of an AI prompt asking for the answer in the chosen language."""
    line = REPLY_IN.get(LANGUAGE)
    return "\n\n" + line if line else ""


def either(text):
    """The text in English and in the chosen language: what code checks when it recognises a line it wrote."""
    return tuple(dict.fromkeys((text, t(text))))


def tn(one, many, count, **blanks):
    """A sentence that changes with a number: one for exactly one, many for any other. {count} is the number."""
    return t(one if count == 1 else many, count=count, **blanks)


def t(text, **blanks):
    """The text in the chosen language (the English if it has no translation), with its {blanks} filled."""
    out = _table.get(text) or text
    return out.format(**blanks) if blanks else out
