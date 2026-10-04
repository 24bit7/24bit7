"""
24bit7 - filters.

Named filters (Settings > Filters) that narrow the playlists 24bit7 builds:
Similar Artists, Similar Tracks, Artist's Top Tracks and Vibe, their Drift
rounds and non-stop top-ups. Albums, songs, shuffles and JRiver playlists asked
for by voice play as asked.

Each filter: a name, On, Applies on (All devices, Windows (Main) for the Play
tab, and speakers with their own settings; any other speaker follows Windows
(Main)), Only pick from (a JRiver playlist or smartlist: only its tracks can be
used), and rules on library fields, matching all or any. Where several filters
apply, a track must pass them all. The seed track is never filtered out. A
track with no value for a rule's field passes it (an unrated track counts as
rating 0, an unplayed one as played 0 times and never played).

Kept in the database's meta table as JSON. The build in progress says which
device it's for through engine.FILTER_DEVICE (None for Windows (Main)).
"""

import json
import time
import uuid

import engine

META_KEY = "filters"
ALL, MAIN = "all", "main"   # Applies on: every device, and the Windows app's Play tab


def blank(name="New filter"):
    return {"id": uuid.uuid4().hex[:8], "name": name, "on": True, "devices": [ALL],
            "pick_from": "", "pick_name": "", "match": "all", "rules": []}


def tidy(item):
    out = blank(item.get("name") or "New filter")
    out.update({k: v for k, v in item.items() if k in out})
    out["devices"] = [str(d) for d in (out.get("devices") or [])]
    out["rules"] = list(out.get("rules") or [])
    return out


def load():
    """Every filter, in the order shown."""
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
        items = json.loads(row[0]) if row and row[0] else []
        return [tidy(x) for x in items if isinstance(x, dict)]
    except Exception:
        return []


def save(items):
    con = engine.db()
    con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (META_KEY, json.dumps([tidy(x) for x in items])))
    con.commit()


def applies(item, device_id):
    """Whether a filter applies to builds for this device (None: Windows (Main))."""
    devices = item.get("devices") or []
    return bool(item.get("on")) and (ALL in devices or (device_id or MAIN) in devices)


def own_devices():
    """[(device_id, name)] for speakers with Own settings ticked: the only ones filters can name."""
    try:
        import voice
        return [(d[0], d[1] or "Unnamed device") for d in voice.devices() if d[4]]
    except Exception:
        return []


def effective(device_id):
    """A speaker without its own settings follows Windows (Main), here as everywhere else."""
    return device_id if device_id and device_id in dict(own_devices()) else None


def active_for(device_id):
    device_id = effective(device_id)
    return [x for x in load() if applies(x, device_id)]


def device_for_zone(zone_name):
    """The speaker with its own settings playing to this zone, for shortcuts and non-stop (None: Windows (Main))."""
    try:
        import voice
        for device_id, _, zone, _, own in voice.devices():
            if zone == zone_name and own:
                return device_id
    except Exception:
        pass
    return None


# --- rules ------------------------------------------------------------------------

# (code, label, [(condition, label)], kind of value)
FIELDS = [
    ("rating", "Rating", [("any", "is any of")], "stars"),
    ("year", "Year", [("before", "before"), ("after", "after"), ("between", "between")], "year"),
    ("last_played", "Last played", [("within", "within the last"), ("not_within", "not within the last")], "days"),
    ("play_count", "Play count", [("more", "more than"), ("fewer", "fewer than")], "number"),
    ("imported", "Date imported", [("within", "within the last"), ("not_within", "not within the last")], "days"),
    ("genre", "Genre", [("contains", "contains"), ("not_contains", "doesn't contain")], "text"),
    ("artist", "Artist", [("contains", "contains"), ("not_contains", "doesn't contain")], "text"),
    ("album", "Album", [("contains", "contains"), ("not_contains", "doesn't contain")], "text"),
    ("duration", "Duration", [("longer", "longer than"), ("shorter", "shorter than")], "minutes"),
    ("file_type", "File type", [("is", "is"), ("is_not", "isn't")], "text"),
    ("bit_depth", "Bit depth", [("at_least", "at least"), ("exactly", "exactly"), ("at_most", "at most")], "number"),
    ("sample_rate", "Sample rate", [("at_least", "at least"), ("exactly", "exactly"), ("at_most", "at most")], "khz"),
    ("location", "File location", [("contains", "contains"), ("not_contains", "doesn't contain")], "text"),
]
FIELD_INFO = {code: (label, ops, kind) for code, label, ops, kind in FIELDS}
TEXT_FIELDS = {"genre": "Genre", "artist": "Artist", "album": "Album", "file_type": "File Type", "location": "Filename"}


COMMON_FILE_TYPES = ["flac", "mp3", "m4a", "wav", "aiff", "alac", "aac", "ogg", "opus", "wma", "ape", "wv",
                     "dsf", "dff"]


def file_types():
    """The file types in the library, most common first; the common ones if the library isn't read yet."""
    try:
        import library
        with library._lock:
            tracks = list(library._tracks)
    except Exception:
        tracks = []
    counts = {}
    for row in tracks:
        kind = str(row.get("File Type") or "").strip().lower().lstrip(".")
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return sorted(counts, key=lambda k: (-counts[k], k)) or list(COMMON_FILE_TYPES)


def blank_rule(field="rating"):
    ops = FIELD_INFO[field][1]
    return {"field": field, "op": ops[0][0], "value": "", "value2": ""}


def _number(text):
    try:
        return float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


MISSING = object()   # a rule the track passed only because it had no value for the field


def rule_result(rule, key, row):
    """True or False for a track and a rule; MISSING when the track has no value, which passes."""
    field, op, value = rule.get("field"), rule.get("op"), rule.get("value", "")
    if field == "rating":
        wanted = {int(x) for x in str(value).split(",") if x.strip().isdigit()}
        if not wanted:
            return True
        rating = _number(row.get("Rating")) or 0   # JRiver leaves the field out for an unrated track
        return int(rating) in wanted
    if field in TEXT_FIELDS:
        wanted = str(value).strip().lower()
        if not wanted:
            return True
        have = str(row.get(TEXT_FIELDS[field]) or "").strip().lower()
        if not have:
            return MISSING
        if field == "file_type":
            same = have.lstrip(".") == wanted.lstrip(".")
            return same if op == "is" else not same
        if field == "location":
            have, wanted = have.replace("/", "\\"), wanted.replace("/", "\\")
        return (wanted in have) if op == "contains" else (wanted not in have)
    target = _number(value)
    if target is None:
        return True   # nothing typed yet: the rule does nothing
    if field == "last_played":
        import library
        when = library.last_played(key)   # never played: not within any number of days
        recent = bool(when) and when >= time.time() - target * 86400
        return recent if op == "within" else not recent
    if field == "imported":
        when = _number(row.get("Date Imported"))
        if not when:
            return MISSING
        recent = when >= time.time() - target * 86400
        return recent if op == "within" else not recent
    if field == "play_count":
        plays = _number(row.get("Number Plays")) or 0   # left out when never played
        return plays > target if op == "more" else plays < target
    if field == "year":
        year = _number(row.get("Date (year)"))
        if not year:
            return MISSING
        if op == "before":
            return year < target
        if op == "after":
            return year > target
        upper = _number(rule.get("value2"))
        return target <= year <= (upper if upper is not None else target)
    if field == "duration":
        seconds = _number(row.get("Duration"))
        if not seconds:
            return MISSING
        return seconds > target * 60 if op == "longer" else seconds < target * 60
    if field in ("bit_depth", "sample_rate"):
        have = _number(row.get("Bit Depth" if field == "bit_depth" else "Sample Rate"))
        if not have:
            return MISSING
        if field == "sample_rate":
            have /= 1000.0   # JRiver gives Hz; the rule is in kHz
        if op == "exactly":
            return abs(have - target) < 0.05
        return have >= target - 0.05 if op == "at_least" else have <= target + 0.05
    return True


def describe_rule(rule):
    label, ops, kind = FIELD_INFO.get(rule.get("field"), ("?", [("", "")], ""))
    op = dict(ops).get(rule.get("op"), "")
    value = rule.get("value", "")
    if kind == "stars":
        value = ", ".join(x for x in str(value).split(",") if x) or "none"
    elif rule.get("op") == "between":
        value = f"{value} and {rule.get('value2', '')}"
    unit = {"days": " days", "minutes": " min", "khz": " kHz"}.get(kind, "")
    return f"{label} {op} {value}{unit}"


def describe(item):
    """A short line for the Active filters list and the log."""
    bits = []
    if item.get("pick_from"):
        bits.append(f"only from {item.get('pick_name') or 'a playlist'}")
    rules = [describe_rule(r) for r in item.get("rules") or []]
    if rules:
        bits.append((" and " if item.get("match", "all") == "all" else " or ").join(rules))
    return item["name"] + (f" ({'; '.join(bits)})" if bits else "")


class Active:
    """
    The filters for one build. allows(key) is False for a track any of them
    rules out. Playlists named in Only pick from are read once, here.
    """

    def __init__(self, device_id, report=print):
        self.report, self.left_out, self.missing = report, 0, 0
        self.items, self.pools = active_for(device_id), []
        self.rule_sets = [(x.get("match", "all"), x["rules"]) for x in self.items if x.get("rules")]
        if self.rule_sets:
            import library
            library.ensure_loaded()
            self.library = library
        for item in self.items:
            if not item.get("pick_from"):
                continue
            try:
                import saved_playlists
                keys = {str(k) for k in saved_playlists.playlist_keys(item["pick_from"])}
            except Exception as e:
                report(f"  Problem: the filter {item['name']} couldn't read {item.get('pick_name') or 'its playlist'} "
                       f"from JRiver ({e}), so it was skipped this time.")
                continue
            self.pools.append(keys)
        if self:
            report("  Filters: " + "; ".join(describe(x) for x in self.items))

    def __bool__(self):
        return bool(self.pools or self.rule_sets)

    def _rules_pass(self, key):
        row = self.library.track_row(key) if self.rule_sets else None
        if row is None:
            return True   # not a library track (a YouTube find): rules can't judge it
        missing = False
        for match, rules in self.rule_sets:
            results = [rule_result(rule, key, row) for rule in rules]
            missing = missing or any(r is MISSING for r in results)
            passed = [r is MISSING or r for r in results]
            if not (all(passed) if match == "all" else any(passed)):
                return False
        if missing:
            self.missing += 1
        return True

    def allows(self, key):
        if all(str(key) in pool for pool in self.pools) and self._rules_pass(key):
            return True
        self.left_out += 1
        return False

    def done(self):
        if self.left_out:
            self.report(f"  Filters left out {self.left_out} track{'' if self.left_out == 1 else 's'}.")
        if self.missing:
            self.report(f"  {self.missing} track{'' if self.missing == 1 else 's'} passed a rule only because "
                        f"{'it has' if self.missing == 1 else 'they have'} no value for its field.")
