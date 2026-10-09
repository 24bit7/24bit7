"""
24bit7 - AI Usage.

Counts the tokens every AI request uses (the AI as a source, AI Playlist and its
ideas, AI Moderator, Console Query and the usage Query itself), so Settings > Keys
can show a running total since it was last cleared, with an estimated cost, a guide
to what each feature typically uses per run, and Query, which asks Claude where the
tokens go and which settings would cut them. Answers reused from the cache cost
nothing and aren't counted.

Costs are estimates from the rates in PRICES, which are checked against Anthropic's
pricing page when a release is prepared, so they can be a release behind. The date
they were checked is always shown beside them. Anthropic's console has the real bill.
"""

import threading
import time
from datetime import datetime

import engine

# Each provider's standard API rates in US dollars per million tokens (input, output), by
# model name prefix. Check every provider's pricing page (PRICING_PAGES) before each release.
# Ollama runs on the user's own PC, so its models have no price and cost nothing here.
PRICES = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-6.1-sol": (2.00, 10.00),
    "gpt-6-luna": (0.10, 0.50),
    "gemini-3.8-flash": (0.75, 3.75),        # rises to 1.50 / 7.50 on 1 January 2027
    "gemini-3.5-flash-lite": (0.30, 2.50),
}
PRICES_CHECKED = "8 Oct 2026"
PRICING_PAGES = {
    "anthropic": "https://claude.com/pricing",
    "openai": "https://developers.openai.com/api/docs/pricing",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
}
PRICES_URL = PRICING_PAGES["anthropic"]
MODEL_NAMES = {"claude-sonnet-5": "Sonnet 5", "claude-haiku-4-5": "Haiku 4.5", "gpt-6.1-sol": "GPT-6.1 Sol",
               "gpt-6-luna": "GPT-6 Luna", "gemini-3.8-flash": "Gemini 3.8 Flash",
               "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite"}
CACHE_WRITE, CACHE_READ = 1.25, 0.10   # prompt caching, as multiples of the input rate
MAIN, QUICK = "main", "quick"   # the guide names a tier; the chosen provider's model for it is priced

# What each feature typically uses per run, until there are enough of your own runs to
# average: (model, input, cache writes, cache reads, output, note)
GUIDE = [
    ("Similar Tracks (AI source)", MAIN, 400, 0, 0, 1000, ""),
    ("Similar Artists (AI source)", MAIN, 150, 0, 0, 250, ""),
    ("Top Tracks (AI source)", MAIN, 100, 0, 0, 150,
     "per artist: a Similar Artists build asks for around 20"),
    ("AI Playlist", MAIN, 300, 0, 0, 1000, ""),
    ("AI Playlist ideas", MAIN, 100, 0, 0, 50, ""),
    ("AI Moderator", QUICK, 1000, 0, 0, 300, ""),
    ("Console Query", QUICK, 5000, 65000, 0, 400,
     "first question; follow-ups within 5 minutes cost about a tenth"),
    ("Usage Query", QUICK, 1500, 0, 0, 400, ""),
]
OWN_AFTER = 3   # runs of a feature before the guide shows your own average

QUERY_MODEL = "claude-haiku-4-5-20251001"   # Anthropic's quick model, as Console Query and the AI Moderator use
SINCE_KEY = "ai_usage_since"
QUESTION = "Where are my AI tokens going, and how could I use fewer?"

_lock = threading.Lock()
_query_handler = [None]   # the Play tab's: shows a Query in the console
_panel_refresh = [None]   # the Play tab's: redraws the Now Playing total


def _table():
    con = engine.db()
    con.execute("CREATE TABLE IF NOT EXISTS ai_usage (at REAL, feature TEXT, model TEXT, "
                "input INTEGER, output INTEGER)")
    have = {row[1] for row in con.execute("PRAGMA table_info(ai_usage)")}
    for column in ("cache_write", "cache_read"):   # added in the cost follow-up
        if column not in have:
            con.execute(f"ALTER TABLE ai_usage ADD COLUMN {column} INTEGER DEFAULT 0")
    return con


def _count(usage, name):
    try:
        return int(getattr(usage, name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def record(feature, model, message):
    """Notes one AI reply's tokens: input, cache writes and reads, output. Never raises."""
    usage = getattr(message, "usage", None)
    if usage is None:
        return
    row = (_count(usage, "input_tokens"), _count(usage, "cache_creation_input_tokens"),
           _count(usage, "cache_read_input_tokens"), _count(usage, "output_tokens"))
    try:
        with _lock:
            con = _table()
            if not con.execute("SELECT value FROM meta WHERE key=?", (SINCE_KEY,)).fetchone():
                con.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (SINCE_KEY, str(time.time())))
            con.execute("INSERT INTO ai_usage (at, feature, model, input, cache_write, cache_read, output) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)", (time.time(), feature, model or "", *row))
            con.commit()
    except Exception as e:   # counting must never stop a build
        engine.debug(f"AI usage not recorded ({e})")


# --- money -----------------------------------------------------------------------------

def price_for(model):
    """(input, output) dollars per million tokens for a model, or None if it isn't in PRICES."""
    model = (model or "").lower()
    match = max((p for p in PRICES if model.startswith(p)), key=len, default=None)
    return PRICES.get(match) if match else None


def cost(model, tokens_in, cache_write, cache_read, tokens_out):
    """Estimated dollars for some tokens on one model (0 for a model with no price)."""
    price = price_for(model)
    if not price:
        return 0.0
    rate_in, rate_out = price
    return (tokens_in * rate_in + cache_write * rate_in * CACHE_WRITE + cache_read * rate_in * CACHE_READ
            + tokens_out * rate_out) / 1_000_000


def money(dollars):
    """A cost the way a person would say it: cents under a dollar, then dollars and cents."""
    if dollars >= 1:
        return f"${dollars:,.2f}"
    cents = dollars * 100
    if cents >= 10:
        return f"{cents:.0f} cents"
    if cents >= 1:
        return f"{cents:.1f} cents"
    if cents >= 0.01:
        return f"{cents:.2f} cents"
    return "under 0.01 cents"


def rates_line(provider=None):
    """Says what the estimates are based on for the chosen provider, and that they may be out of date."""
    provider = provider or engine.AI_PROVIDER
    if provider == "ollama":
        return ("Ollama runs on your own PC, so it costs nothing to use. Its tokens are still counted, "
                "and any costs above are from requests made through a cloud provider.")
    name = engine.ai_provider_name(provider)
    parts = []
    for model in engine.AI_MODELS.get(provider, ()):
        price = price_for(model)
        if price:
            label = next((MODEL_NAMES[p] for p in sorted(MODEL_NAMES, key=len, reverse=True)
                          if model.startswith(p)), model)
            parts.append(f"{label} ${price[0]:g} in and ${price[1]:g} out")
    return (f"Costs are estimates. They use {name}'s standard API rates as checked on {PRICES_CHECKED} "
            f"({'; '.join(parts)}, per million tokens), and rates may have changed since. "
            f"{name}'s pricing page has the current rates.")


def pricing_page(provider=None):
    """The chosen provider's pricing page, or None for Ollama."""
    return PRICING_PAGES.get(provider or engine.AI_PROVIDER)


# --- totals ----------------------------------------------------------------------------

def since():
    """When the count started (the last Clear, or the first request recorded), or None."""
    row = _table().execute("SELECT value FROM meta WHERE key=?", (SINCE_KEY,)).fetchone()
    try:
        return float(row[0]) if row else None
    except (TypeError, ValueError):
        return None


def totals():
    """
    {"since", "requests", "input", "output", "cost", "by_feature": [(feature, requests, input, output, cost)]},
    most output first. Input includes cache writes and reads.
    """
    rows = _table().execute("SELECT feature, model, COUNT(*), SUM(input), SUM(cache_write), SUM(cache_read), "
                            "SUM(output) FROM ai_usage GROUP BY feature, model").fetchall()
    by = {}
    for feature, model, n, i, cw, cr, o in rows:
        i, cw, cr, o = int(i or 0), int(cw or 0), int(cr or 0), int(o or 0)
        f = by.setdefault(feature, [feature, 0, 0, 0, 0.0])
        f[1] += int(n or 0)
        f[2] += i + cw + cr
        f[3] += o
        f[4] += cost(model, i, cw, cr, o)
    out = sorted((tuple(f) for f in by.values()), key=lambda f: (-f[3], f[0]))
    return {"since": since(), "requests": sum(f[1] for f in out), "input": sum(f[2] for f in out),
            "output": sum(f[3] for f in out), "cost": sum(f[4] for f in out), "by_feature": out}


def clear():
    """Starts the count again from now."""
    with _lock:
        con = _table()
        con.execute("DELETE FROM ai_usage")
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (SINCE_KEY, str(time.time())))
        con.commit()


def day(when):
    d = datetime.fromtimestamp(when)
    return f"{d.day} {d:%b %Y}"


def cost_phrase(dollars):
    """'about 1.1 cents', or 'under 0.01 cents' when it rounds to nothing."""
    text = money(dollars)
    return text if text.startswith("under") else f"about {text}"


def headline(t=None):
    """One line for Settings: since when, requests, tokens in and out, and the estimated cost."""
    t = t or totals()
    start = f"Since {day(t['since'])}" if t["since"] else "So far"
    if not t["requests"]:
        return f"{start}: no AI requests."
    return (f"{start}: {t['requests']:,} request{'' if t['requests'] == 1 else 's'}, "
            f"{t['input']:,} input and {t['output']:,} output tokens, {cost_phrase(t['cost'])}.")


def short(t=None, unit="dollars"):
    """The Now Playing version, in dollars or tokens."""
    t = t or totals()
    if unit == "tokens":
        return f"AI: {t['input'] + t['output']:,} tokens"
    return f"AI: {cost_phrase(t['cost'])}"


# --- the guide -------------------------------------------------------------------------

def guide():
    """
    [(feature, tokens per run, cost per run, note, yours)] for every feature: your own
    average once you've run it OWN_AFTER times, else the typical figures in GUIDE.
    """
    rows = _table().execute("SELECT feature, model, COUNT(*), SUM(input), SUM(cache_write), SUM(cache_read), "
                            "SUM(output) FROM ai_usage GROUP BY feature, model").fetchall()
    mine = {}
    for feature, model, n, i, cw, cr, o in rows:
        f = mine.setdefault(feature, [0, 0, 0.0])
        f[0] += int(n or 0)
        f[1] += int(i or 0) + int(cw or 0) + int(cr or 0) + int(o or 0)
        f[2] += cost(model, int(i or 0), int(cw or 0), int(cr or 0), int(o or 0))
    out = []
    for feature, tier, i, cw, cr, o, note in GUIDE:
        model = engine.ai_model(tier)
        n, tokens, dollars = mine.get(feature, (0, 0, 0.0))
        if n >= OWN_AFTER:
            out.append((feature, tokens // n, dollars / n, note, True))
        else:
            out.append((feature, i + cw + cr + o, cost(model, i, cw, cr, o), note, False))
    return out


def dollar_line(rows=None):
    """What $1 typically buys, from the guide (so it follows your own averages too)."""
    per = {feature: dollars for feature, _, dollars, _, _ in (rows or guide())}
    builds = per.get("Similar Tracks (AI source)") or 0
    checks = per.get("AI Moderator") or 0
    if not builds or not checks:
        return ""

    def roughly(n):
        return int(round(n, -1)) if n >= 20 else int(round(n))
    return (f"As a rough guide, $1 buys about {roughly(1 / builds):,} Similar Tracks builds with the AI "
            f"as a source, or about {roughly(1 / checks):,} AI Moderator checks.")


# --- Query -----------------------------------------------------------------------------

SYSTEM = """You help someone keep the AI token use of 24bit7 down. 24bit7 is a Windows app that \
builds playlists from their own music library; the AI is optional, and its features are: the AI as a \
source for Similar Artists, Similar Tracks and Artist's Top Tracks, AI Playlist (and its ideas), the \
AI Moderator (Off, Relaxed, Balanced, Strict), and Console Query. You get the token counts since they \
were last cleared, by feature, with estimated costs, and the current settings (keys and passwords left out).

Output tokens cost several times more than input tokens, so weigh them more. Answers reused from \
24bit7's cache cost nothing and aren't in the counts, so a longer cache saves tokens. The costs are \
estimates from rates that may be out of date; say so if you quote them.

Reply with: two or three sentences on where the tokens go; then up to three changes, most saving \
first, each with roughly how much it would cut; and say plainly when use is small enough to leave \
alone. Describe a setting by what it does and its current value (for example "the AI Moderator is \
on Strict for Similar Tracks; Relaxed would check the same playlists with shorter replies"), not by \
menu paths, which you can't see. Be careful not to invent settings. Keep it short. Plain text only: \
no bold, no headings, no asterisks; use "- " for a list. Plain British English. No em dashes."""


def _usage_text(t):
    lines = [headline(t), "", "By feature (requests, input tokens, output tokens, estimated cost):"]
    lines += [f"- {f}: {n:,}, {i:,}, {o:,}, {cost_phrase(c)}" for f, n, i, o, c in t["by_feature"]] or ["- none yet"]
    week = _table().execute("SELECT date(at, 'unixepoch', 'localtime'), SUM(input + cache_write + cache_read), "
                            "SUM(output) FROM ai_usage WHERE at >= ? GROUP BY 1 ORDER BY 1",
                            (time.time() - 7 * 86400,)).fetchall()
    if week:
        lines += ["", "Last 7 days (input, output):"] + [f"- {d}: {int(i or 0):,}, {int(o or 0):,}" for d, i, o in week]
    lines += ["", rates_line()]
    return "\n".join(lines)


def ask(on_done):
    """Asks Claude about the counts in the background; on_done(answer, error) is called from that thread."""
    def work():
        import console_query
        engine.refresh_settings_if_changed()
        if not engine.ai_configured():
            on_done(None, f"there's no {engine.ai_missing_text().split(' ', 1)[1]}")
            return
        user = f"{_usage_text(totals())}\n\nCurrent settings:\n{console_query.settings_text()}"
        try:
            answer = engine.ai_request(user, 700, "Usage Query", tier="quick", system=SYSTEM,
                                       announce=False).text.strip()
            on_done(console_query.plain(answer) or "(no answer came back)", None)
        except ImportError:
            on_done(None, "the anthropic package (needed for Anthropic) isn't installed")
        except Exception as e:
            on_done(None, engine.ai_credit_text() if engine.ai_out_of_credit(e) else str(e)[:200])
    threading.Thread(target=work, daemon=True, name="usage-query").start()


def set_query_handler(fn):
    """The Play tab registers how it shows a Query in the console."""
    _query_handler[0] = fn


def query():
    """Runs Query through the Play tab's console. Returns False if there's no Play tab to show it."""
    if _query_handler[0] is None:
        return False
    _query_handler[0]()
    return True


def set_panel_refresh(fn):
    """The Play tab registers how it redraws the Now Playing total."""
    _panel_refresh[0] = fn


def refresh_panel():
    """Redraws the Now Playing total now (call from the interface thread)."""
    if _panel_refresh[0] is not None:
        _panel_refresh[0]()
