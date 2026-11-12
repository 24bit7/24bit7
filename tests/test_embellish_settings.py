"""
How a Play & Embellish amount builds (Ben, 10 Nov 2026): Shuffle, Deep Cuts and the Moderator, in one row for
every amount (the default) or a row per amount. Shuffle is on to start, for Embellish and for a playlist asked
for by voice. Before this the order was Play's arrow's, shared by both buttons and visible on neither's settings.
Nothing here opens a window.
"""

import re

import pytest

ROAD_TRIP = {"ID": "202", "Name": "Road Trip"}


@pytest.fixture
def corners(app):
    """Twelve obscure Rock artists, three tracks each, never played: the corners Deep Cuts are for."""
    j = app.jriver
    template = next(r for r in j.tracks if r["Genre"] == "Rock")
    for a in range(12):
        for n in range(3):
            row = dict(template, Key=str(90000 + a * 10 + n), Artist=f"Obscure Band {a}",
                       Name=f"Deep Track {a}-{n}", Album=f"Lost Album {a}", **{"Album Artist (auto)": f"Obscure Band {a}"})
            row.update({"Track #": str(n + 1), "Duration": "240.0", "Number Plays": "0", "Last Played": ""})
            j.tracks.append(row)
            j.by_key[row["Key"]] = row
    app.library.load()


def run(app, amount="p50", order=None):
    import embellish
    j = app.jriver
    j.zone("Speakers").playlist[:] = []
    r = app.Lines()
    embellish.embellish(ROAD_TRIP, order, amount, r)
    return r, list(j.zone("Speakers").playlist), list(j.playlists[1]["keys"])


def deep_cuts_added(lines):
    m = re.search(r"Deep Cuts \([^)]*\): (\d+) from", next((x for x in lines if "Deep Cuts (" in x), ""))
    return int(m.group(1)) if m else 0


# --- the model ------------------------------------------------------------------------------------------

def test_one_row_serves_every_amount_to_start_and_it_shuffles(app):
    import embellish
    s = embellish.settings()
    assert s["all"] == "1" and s["rows"] == {}
    assert s["all_row"] == {"shuffle": "1", "deep_cuts": "off", "deep_share": "10", "moderator": "off",
                            "nonstop": embellish._nonstop_was()}
    for amount in embellish.AMOUNTS:
        assert embellish.row_for(amount) == s["all_row"]


def test_an_order_remembered_before_the_table_is_kept_once_then_the_arrow_is_plays_alone(app):
    import embellish
    embellish.set_choice("order", "ordered")   # as 1.32 kept it: Play's arrow, which Embellish followed
    assert embellish.settings()["all_row"]["shuffle"] == "0", "nobody's Embellish changes at the upgrade"
    embellish.set_choice("order", "shuffled")
    assert embellish.settings()["all_row"]["shuffle"] == "0", "from then on the arrow is Play's alone"
    assert embellish.choices()["order"] == "shuffled"


def test_an_amount_has_its_own_row_once_the_tick_is_off(app):
    import embellish
    embellish.set_settings({"all": "0", "all_row": {"shuffle": "1", "moderator": "relaxed"},
                            "rows": {"triple": {"shuffle": "0", "deep_cuts": "spaced", "deep_share": "35"},
                                     "nonsense": {"shuffle": "0"}}})
    s = embellish.settings()
    assert set(s["rows"]) == {"triple"}
    triple = embellish.row_for("triple")
    assert triple == {"shuffle": "0", "deep_cuts": "spaced", "deep_share": "30", "moderator": "relaxed",
                      "nonstop": "no"}, "what a row doesn't say comes from the All amounts row, and the share is in tens"
    assert embellish.row_for("double") == s["all_row"], "an amount with no row starts as a copy of All amounts"
    embellish.set_settings(dict(s, all="1"))
    assert embellish.row_for("triple") == s["all_row"], "ticked again, every amount runs the one row"
    assert embellish.settings()["rows"]["triple"]["shuffle"] == "0", "and the amounts' rows are kept for next time"


def test_the_tables_tick_and_a_changed_line(app):
    """The table's two writes (stage two): nothing is copied until a line is changed, and a changed line is its
    own from then on."""
    import embellish
    embellish.set_row(None, moderator="relaxed", deep_cuts="spaced", deep_share="30")
    one = {"shuffle": "1", "deep_cuts": "spaced", "deep_share": "30", "moderator": "relaxed", "nonstop": "no"}
    assert embellish.row_for("triple") == one
    embellish.use_one_row(False)
    s = embellish.settings()
    assert s["all"] == "0" and s["rows"] == {} and s["all_row"] == one, "unticking copies nothing"
    assert embellish.row_for("triple") == one
    embellish.set_row("triple", shuffle="0")
    assert embellish.row_for("triple") == dict(one, shuffle="0"), "the rest of its row is a copy of All amounts"
    assert embellish.row_for("double") == one, "the others still follow the one row"
    embellish.set_row(None, moderator="strict")
    assert embellish.row_for("triple")["moderator"] == "relaxed", "a row of its own is its own from then on"
    assert embellish.row_for("double")["moderator"] == "strict"
    embellish.use_one_row(True)
    assert embellish.row_for("triple") == embellish.settings()["all_row"], "ticked, every amount runs the one row"
    embellish.use_one_row(False)
    assert embellish.row_for("triple")["shuffle"] == "0", "and its own row was kept for next time"
    embellish.set_row("half", shuffle="1")   # 1.31.0's first name for +50%
    assert set(embellish.settings()["rows"]) == {"triple", "p50"}


# --- Shuffle --------------------------------------------------------------------------------------------

def test_embellish_takes_its_order_from_the_row(app):
    import embellish
    r, z, yours = run(app)
    assert r.has("woven between yours, shuffled"), r.text()
    assert z[0] == yours[0] and sorted(k for k in z if k in yours) == sorted(yours)
    embellish.set_settings({"all": "1", "all_row": {"shuffle": "0"}})
    r, z, yours = run(app)
    assert r.has("woven between yours, in your order"), r.text()
    assert [k for k in z if k in yours] == yours


def test_an_order_given_for_one_run_beats_the_row(app):
    r, z, yours = run(app, order="ordered")
    assert r.has("in your order") and [k for k in z if k in yours] == yours, r.text()


# --- the Moderator ----------------------------------------------------------------------------------------

def test_the_moderator_is_off_to_start(app):
    r, z, yours = run(app)
    assert not r.has("Moderator"), r.text()
    assert len(z) == 15


def test_the_moderator_checks_the_new_tracks_against_the_playlist_and_its_removals_are_replaced(app):
    import embellish
    embellish.set_settings({"all": "1", "all_row": {"moderator": "balanced"}})
    app.ai.remove = [1]
    r, z, yours = run(app)
    assert r.has("Moderator (Balanced): checking 7 tracks against the seed and the playlist so far"), r.text()
    sent = app.ai.sent[-1]
    assert "Seed vibe: the playlist Road Trip, in the sound of The Hollies, Queen, The Byrds, Badfinger" in sent, sent
    assert "Already in the playlist" in sent and "The Hollies - " in sent, "your own tracks as what fits"
    removed = next(x for x in r if "Removed " in x)
    artist, title = removed.split("Removed ", 1)[1].split(":", 1)[0].split(" - ", 1)
    gone = app.jriver.key_of(artist, title)
    assert gone not in z, "the track it removed isn't sent"
    assert len([k for k in z if k not in yours]) == 5, (r.text(), "spares replace what the Moderator took")
    assert [k for k in yours if k not in z] == [], "your own tracks are never checked"


def test_fewer_than_asked_because_of_the_moderator_says_so(app):
    import embellish
    embellish.set_settings({"all": "1", "all_row": {"moderator": "strict"}})
    app.ai.remove = [1, 2, 3, 4, 5, 6]   # Strict finds half as many again: seven for five, and six go
    r, z, yours = run(app)
    assert r.has("Embellish: added 1 track, fewer than the 5 asked for, as the Moderator removed 6."), r.text()
    assert len(z) == 11


def test_a_moderator_set_with_no_ai_says_so_and_adds_no_spares(app):
    import embellish
    embellish.set_settings({"all": "1", "all_row": {"moderator": "balanced"}})
    app.set_env(USE_AI="0")
    r, z, yours = run(app)
    assert len(z) == 15, r.text()
    assert not r.has("Moderator (Balanced): checking"), r.text()


# --- Deep Cuts --------------------------------------------------------------------------------------------

def test_deep_cuts_top_up_what_embellish_added_by_the_share(app, corners):
    import embellish
    embellish.set_settings({"all": "1", "all_row": {"shuffle": "0", "deep_cuts": "spaced", "deep_share": "100"}})
    r, z, yours = run(app)
    assert r.has("Deep Cuts (Rock, spaced): 5 from artists you haven't played lately"), r.text()
    assert len(z) == 20, "ten of yours, five new, and as many deep cuts again"
    assert z[0] == yours[0] and [k for k in z if k in yours] == yours
    cuts = [k for k in z if app.jriver.by_key[k]["Artist"].startswith("Obscure Band")]
    assert cuts, "some of the five come from the artists never played (others from Rock artists little played)"
    embellish.set_settings({"all": "1", "all_row": {"deep_cuts": "shuffled", "deep_share": "20"}})
    r, z, yours = run(app)
    assert deep_cuts_added(r) == 1, (r.text(), "a fifth of the five added, not of the fifteen")
    assert r.has("Deep Cuts (Rock, shuffled)"), r.text()


def test_deep_cuts_with_no_shared_genre_say_why(app, corners, monkeypatch):
    import deepcuts
    import embellish
    embellish.set_settings({"all": "1", "all_row": {"deep_cuts": "spaced"}})
    monkeypatch.setattr(deepcuts, "common_genre", lambda keys, share=0.4: None)
    r, z, yours = run(app)
    assert r.has("Deep Cuts: none this time, as no one genre is shared by enough of the tracks on Road Trip."), r.text()
    assert len(z) == 15


def test_each_amount_runs_its_own_row(app, corners):
    import embellish
    embellish.set_settings({"all": "0", "all_row": {"shuffle": "1"},
                            "rows": {"double": {"deep_cuts": "spaced", "deep_share": "50"}}})
    r, z, yours = run(app, "p50")
    assert not deep_cuts_added(r) and len(z) == 15, r.text()
    r, z, yours = run(app, "double")
    assert deep_cuts_added(r) == 5 and len(z) == 25, r.text()


# --- More Options -----------------------------------------------------------------------------------------

def test_the_more_options_switches_beat_the_rows(app, corners):
    import embellish
    import overrides
    import playmix
    embellish.set_settings({"all": "1", "all_row": {"deep_cuts": "spaced", "deep_share": "100"}})
    playmix.set_open(True)
    assert overrides.active()
    overrides.set_switch("moderator", "strict")
    overrides.set_switch("deep_cuts", "off")
    r, z, yours = run(app)
    assert r.has("More Options: Moderator Strict, Deep Cuts Off"), r.text()
    assert r.has("Moderator (Strict): checking"), r.text()
    assert not deep_cuts_added(r), "Off on the switch turns Deep Cuts off for this playlist too"


# --- by voice: a JRiver playlist shuffles to start ------------------------------------------------------------

def test_a_playlist_asked_for_by_voice_shuffles_on_a_fresh_install_and_saved_rows_keep_theirs(app, monkeypatch):
    sp = app.saved_playlists
    assert app.voice_default_row["shuffle"] == "1", "the default 24bit7 ships with"
    monkeypatch.setattr(sp, "DEFAULT_ROW", dict(app.voice_default_row))   # the fake world pins "as saved"
    fresh = sp.blank()
    assert fresh["all_row"]["shuffle"] == "1" and fresh["all_row_smart"]["shuffle"] == "1"
    saved = sp.tidy({"all": "1", "all_row": {"shuffle": "0"}, "all_row_smart": {"shuffle": "0"},
                     "rows": {"202": {"shuffle": "0"}, "203": {"shuffle": "1"}}})
    assert saved["all_row"]["shuffle"] == "0" and saved["all_row_smart"]["shuffle"] == "0"
    assert saved["rows"]["202"]["shuffle"] == "0" and saved["rows"]["203"]["shuffle"] == "1"


def test_the_voice_path_shuffles_with_nothing_saved(app, monkeypatch):
    import random
    sp = app.saved_playlists
    monkeypatch.setattr(sp, "DEFAULT_ROW", dict(app.voice_default_row))
    monkeypatch.setattr(random, "shuffle", lambda keys: keys.reverse())
    j = app.jriver
    ok, what = sp.play(j.playlists[0], j.zone("Kitchen").id)
    assert ok and what.endswith(", shuffled"), what
    assert j.zone("Kitchen").playlist == list(reversed(j.playlists[0]["keys"]))


# --- Non-stop: the fourth column (12 Nov 2026) ----------------------------------------------------------------

def nonstop_entry(app, z):
    entries = [e for e in app.engine.NONSTOP_ZONES.values() if set(z) & e["keys"]]
    assert len(entries) == 1
    return entries[0]


def standard_nonstop(app, on, using="artists"):
    import buttons
    std = buttons.standard("artists")
    std.setdefault("settings", {}).update(NONSTOP_ARTISTS="1" if on else "0", NONSTOP_ARTISTS_USING=using)
    buttons.save([std if b.get("id") == std.get("id") else b for b in buttons.load()])


def test_the_column_starts_as_artist_matchings_non_stop_did(app):
    """Before the column, an Embellish carried on as the standard Artist Matching playlist's Non-stop said."""
    import embellish
    standard_nonstop(app, True, "tracks")
    assert embellish._nonstop_was() == "tracks"
    embellish._set_meta(embellish.SETTINGS_KEY, {"all": "1", "all_row": {"shuffle": "0"}, "rows": {}})   # 1.34's
    assert embellish.settings()["all_row"]["nonstop"] == "tracks", "nobody's Embellish changes at the upgrade"
    standard_nonstop(app, False)
    assert embellish.settings()["all_row"]["nonstop"] == "tracks", "once: from then on it's the column's"
    assert embellish._nonstop_was() == "no"


def test_non_stop_follows_the_column_not_artist_matching(app):
    import embellish
    import nonstop
    standard_nonstop(app, True)
    embellish.set_settings({"all": "1", "all_row": {"nonstop": "no"}})
    r, z, yours = run(app)
    assert not nonstop.config_for("Speakers", nonstop_entry(app, z)).get("on"), r.text()
    embellish.set_settings({"all": "1", "all_row": {"nonstop": "tracks"}})
    r, z, yours = run(app)
    entry = nonstop_entry(app, z)
    assert entry["origin"] == "saved" and entry["saved_cfg"] == {"using": "tracks", "reseed": "last"}
    assert nonstop.config_for("Speakers", entry).get("on")


def test_each_amount_has_its_own_non_stop(app):
    import embellish
    embellish.set_settings({"all": "0", "all_row": {"nonstop": "no"}, "rows": {"double": {"nonstop": "artists"}}})
    r, z, yours = run(app, "p50")
    assert nonstop_entry(app, z)["saved_cfg"] is None
    r, z, yours = run(app, "double")
    assert nonstop_entry(app, z)["saved_cfg"] == {"using": "artists", "reseed": "last"}


def test_the_more_options_switch_beats_the_column(app):
    import embellish
    import overrides
    import playmix
    embellish.set_settings({"all": "1", "all_row": {"nonstop": "tracks"}})
    playmix.set_open(True)
    overrides.set_switch("nonstop", "off")
    r, z, yours = run(app)
    assert nonstop_entry(app, z)["saved_cfg"] is None, r.text()
    overrides.set_switch("nonstop", "tight")
    r, z, yours = run(app)
    assert nonstop_entry(app, z)["saved_cfg"] == {"using": "tracks", "reseed": "whole"}, "Keep It Tight: the playlist"
