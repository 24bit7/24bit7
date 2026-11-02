"""
24bit7 - filters.

Named filters (Edit Filters, from a playlist's page) that narrow the playlists
24bit7 builds: every playlist's, their Drift rounds and Non-stop top-ups.
Albums, songs, shuffles and JRiver playlists asked for by voice play as asked.

Each filter: a name, On, Only pick from (a JRiver playlist or smartlist: only its
tracks can be used), and rules on library fields, matching all or any. Where a
filter applies is decided by ticking it on playlists: a build runs under its
playlist's filters, wherever it's sent. Where several apply, a track must pass
them all. The seed track is never filtered out. A track
with no value for a rule's field passes it (an unrated track counts as rating 0,
an unplayed one as played 0 times and never played).

Kept in the database's meta table as JSON. The build in progress gets its filter
ids through engine.FILTER_IDS (buttons.run sets them).
"""

import json
import time
import uuid

from i18n import N_, t, tn

import engine

META_KEY = "filters"


def blank(name="New filter"):
    return {"id": uuid.uuid4().hex[:8], "name": name, "on": True,
            "pick_from": "", "pick_name": "", "match": "all", "rules": []}


def tidy(item):
    out = blank(item.get("name") or "New filter")
    out.update({k: v for k, v in item.items() if k in out})
    out["rules"] = list(out.get("rules") or [])
    return out


def stored_raw():
    """The saved list as it is in the database, old Applies on lists included, for the buttons upgrade."""
    try:
        row = engine.db().execute("SELECT value FROM meta WHERE key=?", (META_KEY,)).fetchone()
        items = json.loads(row[0]) if row and row[0] else []
        return [x for x in items if isinstance(x, dict) and x.get("id")]
    except Exception:
        return []


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


def used_by(filter_id):
    """
    [playlist names] with this filter ticked, for Edit Filters' Used by line. Filters are each
    config's own (2 Nov 2026): a playlist of several configs names the config, "Artist + Guests (config 2)".
    """
    import buttons
    out = []
    for b in buttons.load():
        cfgs = buttons.configs(b)
        for i, cfg in enumerate(cfgs):
            if filter_id in cfg["filters"]:
                out.append(b["name"] if len(cfgs) == 1 else t("{name} (config {n})", name=b["name"], n=i + 1))
    return out


def by_ids(ids):
    """The filters a button build runs under: the ones named, in the order shown, that are on."""
    wanted = {str(i) for i in ids}
    return [x for x in load() if x["id"] in wanted and x.get("on")]


# --- rules ------------------------------------------------------------------------

# (code, label, [(condition, label)], kind of value)
FIELDS = [
    ("rating", N_("Rating"), [("any", N_("is any of"))], "stars"),
    ("year", N_("Year"), [("before", N_("before")), ("after", N_("after")), ("between", N_("between"))], "year"),
    ("last_played", N_("Last played"), [("within", N_("within the last")), ("not_within", N_("not within the last"))], "days"),
    ("play_count", N_("Play count"), [("more", N_("more than")), ("fewer", N_("fewer than"))], "number"),
    ("imported", N_("Date imported"), [("within", N_("within the last")), ("not_within", N_("not within the last"))], "days"),
    ("genre", N_("Genre"), [("contains", N_("contains")), ("not_contains", N_("doesn't contain"))], "text"),
    ("artist", N_("Artist"), [("contains", N_("contains")), ("not_contains", N_("doesn't contain"))], "text"),
    ("album", N_("Album"), [("contains", N_("contains")), ("not_contains", N_("doesn't contain"))], "text"),
    ("duration", N_("Duration"), [("longer", N_("longer than")), ("shorter", N_("shorter than"))], "minutes"),
    ("file_type", N_("File type"), [("is", N_("is")), ("is_not", N_("isn't"))], "text"),
    ("bit_depth", N_("Bit depth"), [("at_least", N_("at least")), ("exactly", N_("exactly")), ("at_most", N_("at most"))], "number"),
    ("sample_rate", N_("Sample rate"), [("at_least", N_("at least")), ("exactly", N_("exactly")), ("at_most", N_("at most"))], "khz"),
    ("location", N_("File location"), [("contains", N_("contains")), ("not_contains", N_("doesn't contain"))], "text"),
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
        value = ", ".join(x for x in str(value).split(",") if x) or t("none")
    elif rule.get("op") == "between":
        value = f"{value} {t('and')} {rule.get('value2', '')}"
    unit = {"days": " " + t("days"), "minutes": " min", "khz": " kHz"}.get(kind, "")
    return f"{t(label)} {t(op)} {value}{unit}"


def describe(item):
    """A short line for the Active filters list and the log."""
    bits = []
    if item.get("pick_from"):
        bits.append(t("only from {name}", name=item.get("pick_name") or t("a playlist")))
    rules = [describe_rule(r) for r in item.get("rules") or []]
    if rules:
        bits.append((" " + t("and") + " " if item.get("match", "all") == "all" else " " + t("or") + " ").join(rules))
    return item["name"] + (f" ({'; '.join(bits)})" if bits else "")


class Active:
    """
    The filters for one build: the ids it runs under (its playlist's).
    allows(key) is False for a track any of them rules out. Playlists named in Only
    pick from are read once, here.
    """

    def __init__(self, ids, report=print):
        self.report, self.left_out, self.missing = report, 0, 0
        self.items = by_ids(ids or [])
        self.pools = []
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
                report("  " + t("Problem: the filter {name} couldn't read {value} from JRiver ({e}), so it was skipped this time.", name=item['name'], value=item.get('pick_name') or 'its playlist', e=e))
                continue
            self.pools.append(keys)
        if self:
            report("  " + t("Filters: {filters}", filters="; ".join(describe(x) for x in self.items)))

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

    def passes(self, key):
        """allows() without counting a track left out: for trying your other copies of a song."""
        return all(str(key) in pool for pool in self.pools) and self._rules_pass(key)

    def allows(self, key):
        if self.passes(key):
            return True
        self.left_out += 1
        return False

    def done(self):
        if self.left_out:
            self.report("  " + tn("Filters left out {count} track.", "Filters left out {count} tracks.", self.left_out))
        if self.missing:
            self.report("  " + tn("{count} track passed a rule only because it has no value for its field.",
                                  "{count} tracks passed a rule only because they have no value for its field.",
                                  self.missing))
