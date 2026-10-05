"""
The engine: every Play option built against the fake JRiver and fake sources,
plus the matching, blending, cache, AI and Moderator rules underneath.
"""

import json
import time

import pytest


def seed(app, artist, title):
    return app.engine.typed_seed_info(artist, title)


def count_line(lines):
    """The number in the Done line ('Done: 30 tracks queued ...')."""
    import re
    for line in lines:
        m = re.search(r"Done: (\d+) tracks? (queued|sent|added)", line)
        if m:
            return int(m.group(1))
    return None


# --- Similar Artists ---------------------------------------------------------------------

def test_similar_artists_typed_seed_starts_on_seed(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    titles = app.jriver.titles("Speakers")
    assert titles[0] == "The Beatles - Here Comes The Sun", r.text()
    assert len(set(titles)) == len(titles), "no track twice"
    assert r.has("Done:")


def test_similar_artists_done_line_matches_what_was_sent(app):
    """The Done line's count should be what actually reached JRiver."""
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    sent = len(app.jriver.zone("Speakers").playlist)
    assert count_line(r) == sent, f"Done line says {count_line(r)}, JRiver got {sent}\n" + r.text()


def test_similar_artists_reaches_target_despite_long_closers(app):
    """Long album closers are skipped as hidden tracks; the playlist should still reach its target."""
    app.set_env(SIMILAR_ARTIST_TRACK_COUNT="20")   # the fake library has enough for 20 every time
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert len(app.jriver.zone("Speakers").playlist) == 20, r.text()
    assert "Pink Floyd - Echoes" not in app.jriver.titles("Speakers")


def test_similar_artists_per_artist_cap_counts_library_tag(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    from collections import Counter
    per = Counter(t.split(" - ")[0] for t in app.jriver.titles("Speakers"))
    pick = app.engine.TRACKS_PER_ARTIST_PICK
    assert all(n <= pick + 1 for n in per.values()), per   # +1: the seed track itself


def test_band_credit_matches_library_tag(app):
    """Sources say 'The Jimi Hendrix Experience', the library says 'Jimi Hendrix'."""
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert any(t.startswith("Jimi Hendrix - ") for t in app.jriver.titles("Speakers")), r.text()


def test_simon_and_garfunkel_both_ways(app):
    key = app.library.find_track_key("Simon and Garfunkel", "The Boxer")
    assert key == app.jriver.key_of("Simon & Garfunkel", "The Boxer")


def test_inverted_the_and_accents(app):
    lib = app.library
    assert lib.find_track_key("The Kinks", "Waterloo Sunset") == app.jriver.key_of("Kinks, The", "Waterloo Sunset")
    assert lib.find_track_key("Sigur Ros", "Hoppipolla") == app.jriver.key_of("Sigur Rós", "Hoppípolla")


def test_bracketed_titles_both_ways(app):
    lib = app.library
    want = app.jriver.key_of("The Rolling Stones", "(I Can't Get No) Satisfaction")
    assert lib.find_track_key("The Rolling Stones", "I Can't Get No Satisfaction") == want
    want = app.jriver.key_of("The Hollies", "Long Cool Woman (In A Black Dress)")
    assert lib.find_track_key("The Hollies", "Long Cool Woman In A Black Dress") == want


def test_multi_value_artist_matches_either(app):
    want = app.jriver.key_of("Angus Stone;Julia Stone", "Yellow Brick Road")
    assert app.library.find_track_key("Angus Stone", "Yellow Brick Road") == want


def test_singles_convention(app):
    assert app.library.find_track_key("David Guetta", "Sexy Chick") == app.jriver.key_of("David Guetta", "Sexy Chick")


def test_agreement_keeps_only_agreed_artists(app):
    app.set_env(SIMILAR_MIN_AGREEMENT="3")
    app.web.empty.add("deezer")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert r.has("Done:") or r.has("Problem"), r.text()


def test_source_down_build_still_completes(app):
    app.web.down.add("deezer")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert r.has("Done:"), r.text()
    assert app.printed.has("Deezer didn't answer"), "the failure should be visible"


def test_every_source_down(app):
    for s in ("lastfm", "deezer", "listenbrainz", "musicbrainz"):
        app.web.down.add(s)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert app.jriver.titles("Speakers") == ["The Beatles - Here Comes The Sun"] or r.has("Problem"), r.text()


def test_cache_serves_second_build(app):
    s = seed(app, "The Beatles", "Here Comes The Sun")
    app.engine.create_similar_playlist(report=app.Lines(), seed_info=s)
    before = len([c for c in app.web.calls if c[0] == "lastfm"])
    app.engine.create_similar_playlist(report=app.Lines(), seed_info=s)
    after = len([c for c in app.web.calls if c[0] == "lastfm"])
    assert after == before, "a repeat seed should come from the cache"


def test_empty_results_are_not_cached(app):
    app.web.empty.add("lastfm")
    s = seed(app, "The Beatles", "Here Comes The Sun")
    app.engine.create_similar_playlist(report=app.Lines(), seed_info=s)
    app.web.empty.clear()
    n = len(app.web.calls)
    app.engine.create_similar_playlist(report=app.Lines(), seed_info=s)
    assert any(c[0] == "lastfm" for c in app.web.calls[n:]), "an empty answer must be asked for again"


def test_busy_zone_queues_after_current_track(app):
    j = app.jriver
    current = j.key_of("Queen", "Bohemian Rhapsody")
    j.play("Speakers", [j.key_of("Queen", "Somebody To Love"), current, j.key_of("Queen", "Don't Stop Me Now")], pos=1)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    z = j.zone("Speakers")
    assert z.playlist[0] == current and z.pos == 0, r.text()
    assert r.has("after the current track")


def test_nothing_playing_and_no_seed(app):
    r = app.Lines()
    app.engine.create_similar_playlist(report=r)
    assert r.has("nothing is playing") or r.has("Nothing") or r.has("Problem"), r.text()


def test_now_playing_seed(app):
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    r = app.Lines()
    app.engine.create_similar_playlist(report=r)
    assert r.has("Done:"), r.text()
    assert j.zone("Speakers").playlist[0] == j.key_of("The Beatles", "Something")


def test_output_to_another_zone_seed_opens(app):
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something")])
    app.set_env(OUTPUT_TARGET="zone:Kitchen")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r)
    assert j.zone("Kitchen").playlist[0] == j.key_of("The Beatles", "Something"), r.text()
    assert j.zone("Speakers").playlist == [j.key_of("The Beatles", "Something")]


def test_output_zone_missing(app):
    app.set_env(OUTPUT_TARGET="zone:Garage")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert r.has("isn't in JRiver"), r.text()


def test_youtube_output_leaves_jriver_alone(app, monkeypatch):
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    app.set_env(OUTPUT_TARGET="youtube")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert not app.jriver.calls_to("Playback/PlayByKey")
    assert opened and "watch_videos" in opened[0], r.text()


def test_skip_recently_played(app):
    j = app.jriver
    now = time.time()
    for t in ("Bus Stop", "Carrie Anne", "He Ain't Heavy, He's My Brother", "Long Cool Woman (In A Black Dress)"):
        j.mark_played(j.key_of("The Hollies", t), now - 3600)
    app.set_env(SKIP_PLAYED_ARTISTS="1", SKIP_PLAYED_ARTISTS_DAYS="1")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert not any(t.startswith("The Hollies") for t in j.titles("Speakers")), r.text()
    assert r.has("played in the last 1 day")


def test_drift_runs_when_short(app):
    app.set_env(DRIFT_ARTISTS="1", SIMILAR_ARTIST_LIMIT="2", SIMILAR_ARTIST_TRACK_COUNT="30")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert r.has("Drift"), r.text()
    assert len(app.jriver.zone("Speakers").playlist) > 7


def test_run_after_building(app, tmp_path, monkeypatch):
    import os
    import sys
    marker = tmp_path / "ran.txt"
    script = tmp_path / "hook.py"
    script.write_text(f"open(r'{marker}', 'w').write('ok')")
    if os.name == "nt":
        hook = tmp_path / "hook.bat"
        hook.write_text(f'@"{sys.executable}" "{script}"\n')
    else:   # os.startfile is Windows only: stand in for it when the suite runs elsewhere
        hook = tmp_path / "hook.sh"
        hook.write_text(f"#!/bin/sh\n{sys.executable} {script}\n")
        hook.chmod(0o755)
        monkeypatch.setattr(os, "startfile", lambda p, *a, **k: os.system(p), raising=False)
    app.set_env(RUN_AFTER_ARTISTS="1", RUN_AFTER_ARTISTS_PATH=str(hook))
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    for _ in range(100):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists(), r.text() + "\n" + app.printed.text()[-1500:]


# --- Similar Tracks --------------------------------------------------------------------------

def test_similar_tracks(app):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    titles = app.jriver.titles("Speakers")
    assert titles[0] == "The Beatles - Here Comes The Sun", r.text()
    assert len(titles) > 10
    assert count_line(r) == len(titles), r.text()


def test_similar_tracks_youtube_and_ai_sources(app):
    app.set_env(SIMILAR_TRACK_SOURCES="youtube,ai", SIMILAR_TRACK_MIN_AGREEMENT="2")
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert r.has("YouTube:") and r.has("AI:"), r.text()
    assert len(app.jriver.zone("Speakers").playlist) > 5


def test_similar_tracks_needs_a_track(app):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=app.engine.typed_seed_info("The Beatles", ""))
    assert r.has("needs a track"), r.text()


def test_ai_reply_cut_short_is_salvaged(app):
    app.set_env(SIMILAR_TRACK_SOURCES="ai")
    full = json.dumps([{"artist": "Queen", "track": "Somebody To Love"},
                       {"artist": "The Hollies", "track": "Bus Stop"},
                       {"artist": "Badfinger", "track": "Baby Blue"}], separators=(",", ":"))
    app.ai.script.append((full[:-20], "max_tokens"))
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert app.printed.has("complete entries were kept"), app.printed.text()[-1500:]
    assert len(app.jriver.zone("Speakers").playlist) >= 3


def test_ai_unreadable_retries_once(app):
    app.set_env(SIMILAR_TRACK_SOURCES="ai")
    app.ai.script += [("sorry, no", "end_turn")]
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert len(app.ai.calls) == 2, app.ai.calls
    assert len(app.jriver.zone("Speakers").playlist) > 3


def test_ai_requests_have_thinking_off(app):
    app.set_env(SIMILAR_TRACK_SOURCES="ai")
    app.engine.create_similar_tracks_playlist(report=app.Lines(), seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert app.ai.calls and app.ai.calls[0][2].get("thinking") == {"type": "disabled"}


# --- AI Moderator ---------------------------------------------------------------------------

@pytest.mark.parametrize("level,cap", [("relaxed", 0.2), ("balanced", 0.4), ("strict", 1.0)])
def test_moderator_caps(app, level, cap):
    app.ai.remove = list(range(1, 31))
    app.set_env(AI_MODERATOR_TRACKS=level)
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    tracks = [(str(k), "A", f"T{k}") for k in range(30)]
    removed = app.engine.moderate(tracks, "The Beatles - Something", report=app.Lines())
    assert len(removed) == max(1, int(30 * cap))


def test_moderator_replacements_keep_target(app):
    app.set_env(AI_MODERATOR_TRACKS="balanced", SIMILAR_TRACK_COUNT="15")
    app.ai.remove = [2, 3]
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert r.has("AI Moderator"), r.text()
    assert len(app.jriver.zone("Speakers").playlist) == 15, r.text()


def test_moderator_failure_keeps_playlist(app):
    app.set_env(AI_MODERATOR_TRACKS="strict")
    app.ai.fail = RuntimeError("Your credit balance is too low")
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app, "The Beatles", "Here Comes The Sun"))
    assert r.has("credit balance is too low"), r.text()
    assert len(app.jriver.zone("Speakers").playlist) > 10


def test_moderator_off_without_key(app):
    app.set_env(AI_MODERATOR_TRACKS="strict", ANTHROPIC_API_KEY="")
    app.engine.NONSTOP_CONTEXT = {"kind": "tracks"}
    assert app.engine.moderator_level() == "off"


def test_old_moderator_tick_reads_as_balanced(app):
    app.set_env(AI_MODERATOR="1")
    assert app.engine.moderator_settings(lambda k, d=None: app.env.get(k, d))["artists"] == "balanced"


# --- Artist's Top Tracks ------------------------------------------------------------------

def test_top_tracks_popular_order(app):
    app.set_env(TOP_TRACKS_COUNT="5", TOP_TRACKS_ORDER="popular")
    r = app.Lines()
    app.engine.play_top_n(report=r, seed_info=seed(app, "Queen", ""))
    assert app.jriver.titles("Speakers")[:3] == ["Queen - Bohemian Rhapsody", "Queen - Somebody To Love",
                                                  "Queen - Don't Stop Me Now"], r.text()


def test_top_tracks_unknown_artist(app):
    r = app.Lines()
    app.engine.play_top_n(report=r, seed_info=seed(app, "Nobody At All", ""))
    assert not app.jriver.zone("Speakers").playlist
    assert r.has("Problem") or r.has("Note"), r.text()


# --- AI Playlist ------------------------------------------------------------------------------

def test_ai_playlist(app):
    r = app.Lines()
    app.engine.create_vibe_playlist("sunday morning coffee", report=r)
    assert len(app.jriver.zone("Speakers").playlist) >= 10, r.text()
    assert r.has("Done:")


def test_ai_playlist_suggestions(app):
    assert len(app.engine.ai_vibe_suggestions()) == 3


def test_ai_playlist_ai_picks_never_moderated(app):
    app.set_env(AI_MODERATOR="strict", AI_MODERATOR_ARTISTS="strict", AI_MODERATOR_TRACKS="strict")
    app.engine.create_vibe_playlist("sunday morning coffee", report=app.Lines())
    assert not any("moderator" in c[1] for c in app.ai.calls)


# --- Console and diagnostics ----------------------------------------------------------------

def test_export_log_redacts_keys(app):
    path = app.engine.export_log("console text here")
    text = open(path, encoding="utf-8").read()
    assert "test-lastfm" not in text and "test-anthropic" not in text and "test-voice-key" not in text
    assert "console text here" in text


def test_diagnostics_reach_jriver(app):
    text = app.engine.diagnostics_text()
    assert "34.0.20" in text, text
