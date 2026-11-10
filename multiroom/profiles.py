"""
Speaker and DAC profiles (Multiroom, stage two, 9 Nov 2026): the starting numbers for kit 24bit7 knows.

A speaker profile is keyed on what the device announces (the Sonos's /info gives its model); a DAC profile on the
device name JRiver reports for the follower zone and the audio driver's name. A profile only fills in the
Adjustments under Settings > Other > Multiroom; a recording (stage three) or a typed number overrides it, and the
line under the fields says which is in force. When someone with other kit sends numbers that repeat, the model
becomes a profile in the next release.
"""

import copy

# Speakers: match is (maker or model contains, model contains), case ignored. Start and Resume in ms.
SPEAKERS = [
    {"match": ("sonos", "one"), "name": "Sonos One", "clock": "sonos", "start": 90.0, "resume": 95.0, "tested": True},
    {"match": ("sonos", ""), "name": "Sonos", "clock": "sonos", "start": 90.0, "resume": 95.0, "tested": False},
]
GENERIC = {"name": "Generic", "clock": "upnp", "start": 90.0, "resume": 95.0, "tested": False}

# DACs: words that must both appear across the device's name and the driver's name; the delay in samples, which
# is a starting value: the same DAC gives another number through WASAPI, or with another driver buffer setting.
DACS = [
    {"match": ("chord", "hugo"), "name": "Chord Hugo TT", "dac": 1660, "api": "ASIO", "tested": True},
]
UNKNOWN_DAC = {"name": "", "dac": 0, "api": "", "tested": False}


def pick_speaker(maker="", model=""):
    """The profile for a speaker by what it announces; Generic if none matches."""
    text = f"{maker} {model}".lower()
    for p in SPEAKERS:
        a, b = p["match"]
        if a in text and b in text:
            return copy.deepcopy(p)
    return copy.deepcopy(GENERIC)


def pick_dac(device_name="", driver_name=""):
    """The profile for a DAC by JRiver's name for it and the driver's; UNKNOWN_DAC (delay 0) if none matches."""
    text = f"{device_name} {driver_name}".lower()
    for p in DACS:
        a, b = p["match"]
        if a in text and b in text:
            return copy.deepcopy(p)
    return copy.deepcopy(UNKNOWN_DAC)


def source_key(source, speaker, dac):
    """
    Where the numbers came from, as (key, values) for the app to word in its own language
    (settings_gui.SOURCE_LINES). source is profiles, typed or recording:<date>.
    """
    if source.startswith("recording:"):
        return "recording", {"date": source[len("recording:"):]}
    if source == "typed":
        return "typed", {}
    if speaker.get("name") == "Generic":
        return "generic", {}
    names = [n for n in (speaker.get("name"), dac.get("name")) if n]
    if len(names) == 2:
        return "two_profiles", {"a": names[0], "b": names[1]}
    if names:
        return "one_profile", {"a": names[0]}
    return "profiles", {}


ENGLISH_LINES = {
    "recording": "From your recording of {date}.",
    "typed": "Typed by hand.",
    "generic": "Generic: not measured yet. The rooms may be a few hundredths of a second apart until you calibrate.",
    "two_profiles": "From the {a} and {b} profiles.",
    "one_profile": "From the {a} profile.",
    "profiles": "From the profiles.",
}


def source_line(source, speaker, dac):
    """The line under the Adjustments, in English."""
    key, values = source_key(source, speaker, dac)
    return ENGLISH_LINES[key].format(**values)
