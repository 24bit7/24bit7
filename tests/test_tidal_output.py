"""Output to Tidal: builds fill the playlist called 24bit7, found by name, and JRiver is left alone."""

import re

import pytest


def seed(app, artist="The Beatles", title="Here Comes The Sun"):
    return app.engine.typed_seed_info(artist, title)


def tidal_out(app, **extra):
    app.set_env(**dict(dict(TIDAL_CLIENT_ID="test-id", TIDAL_CLIENT_SECRET="test-secret",
                            TIDAL_REFRESH_TOKEN="fake-refresh", TIDAL_USER_ID="12345", OUTPUT_TARGET="tidal",
                            EXTRA_OUTPUTS="youtube,tidal"), **extra))


def playlists(app):
    return app.web._tidal_playlist_store()


def the_24bit7(app):
    found = [p for p in playlists(app).values() if p["name"] == "24bit7"]
    assert len(found) == 1, playlists(app)
    return found[0]


def tracks_in(app, p):
    return [app.web._tidal_get("tracks", t) for _, t in p["items"]]


def done_count(lines):
    for line in lines:
        m = re.search(r"Done: (\d+) tracks? sent to Tidal, (\d+) not found on Tidal", line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def test_similar_artists_fills_a_new_playlist(app):
    tidal_out(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app))
    assert not app.jriver.calls_to("Playback/PlayByKey"), "JRiver is left alone"
    p = the_24bit7(app)
    assert p["items"] and p["access"] == "UNLISTED"
    assert tracks_in(app, p)[0][:2] == ("The Beatles", "Here Comes The Sun"), r.text()   # the seed opens it
    assert all(version == "" for _, _, version in tracks_in(app, p))   # studio versions, not the live takes
    assert "From The Beatles - Here Comes The Sun" in p["description"]
    sent, _ = done_count(r)
    assert sent == len(p["items"]), r.text()
    assert r.has('Tidal playlist "24bit7" updated') and r.has("Rename it in Tidal to keep it")
    assert app.engine.LAST_OUTPUT == "Tidal" and app.engine.TIDAL_PLAYLIST_ID in playlists(app)


def test_next_build_replaces_the_tracks(app):
    tidal_out(app)
    e = app.engine
    e.create_similar_playlist(report=app.Lines(), seed_info=seed(app))
    first = list(the_24bit7(app)["items"])
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=seed(app, "Pink Floyd", "Money"))
    p = the_24bit7(app)
    assert len(playlists(app)) == 1, "the same playlist, not a second one"
    assert p["items"] and not set(p["items"]) & set(first), r.text()
    assert "Pink Floyd - Money" in p["description"]


def test_a_renamed_playlist_is_kept(app):
    tidal_out(app)
    e = app.engine
    e.create_similar_playlist(report=app.Lines(), seed_info=seed(app))
    kept = the_24bit7(app)
    kept["name"] = "Sunday morning"   # renamed in Tidal
    kept_items = list(kept["items"])
    e.create_similar_playlist(report=app.Lines(), seed_info=seed(app, "Pink Floyd", "Money"))
    assert len(playlists(app)) == 2
    assert kept["items"] == kept_items, "the renamed one is never touched"
    assert the_24bit7(app)["items"]


def test_more_than_fifty_tracks_go_in_batches(app):
    tidal_out(app)
    e = app.engine
    known = [e.tidal_track_id(a, t) for a in app.web.artists for t in app.web.top_tracks(a)]
    known = [k for k in known if k][:120]
    assert len(known) > 60   # two batches of up to fifty, and over three pages of twenty
    pid, refused = e.tidal_fill_playlist(known)
    assert refused == 0 and [t for _, t in playlists(app)[pid]["items"]] == known   # in order
    pid2, _ = e.tidal_fill_playlist(known[:3])
    assert pid2 == pid and [t for _, t in playlists(app)[pid]["items"]] == known[:3]   # cleared over pages


def test_tracks_tidal_turns_down_are_counted(app):
    tidal_out(app)
    e = app.engine
    known = e.tidal_track_id("The Beatles", "Here Comes The Sun")
    lines = app.Lines()
    assert e.send_to_tidal([known, "99999"], report=lines) == 1
    assert lines.has("1 track (1 Tidal wouldn't play here)")


def test_not_signed_in_stops_plainly(app):
    tidal_out(app, TIDAL_REFRESH_TOKEN="")
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app))
    assert r.has("Problem: Not signed in to Tidal. Sign in under Settings > Keys."), r.text()
    assert r.has("Done: nothing sent to Tidal")
    assert not playlists(app) and not app.jriver.calls_to("Playback/PlayByKey")


def test_sign_in_run_out_says_sign_in_again(app):
    tidal_out(app)
    app.web.tidal_login["refresh_ok"] = False
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app))
    assert r.has("Sign in to Tidal again under Settings > Keys"), r.text()


def test_misses_counted_in_the_done_line(app):
    tidal_out(app)
    r = app.Lines()
    app.engine.create_similar_playlist(report=r, seed_info=seed(app))
    sent, missed = done_count(r)
    assert missed == sum(1 for line in r if "Not on Tidal:" in line), r.text()
    assert app.engine.LAST_BUILD["queued"] == sent
    assert r.has("Looking up") and r.has("tracks on Tidal") and not r.has("YouTube"), r.text()


def test_lookups_cached_and_misses_not_asked_twice(app):
    tidal_out(app)
    e = app.engine
    e.create_similar_playlist(report=app.Lines(), seed_info=seed(app))
    searches = [c for c in app.web.calls if c[0] == "tidal" and c[1] == "/v2/searchResults"]
    asked = [c[2]["filter[query]"] for c in searches]
    assert len(asked) == len(set(asked)), "each track searched once per build"
    before = len(searches)
    e.tidal_ids_for_pairs([("The Beatles", "Here Comes The Sun")])
    after = [c for c in app.web.calls if c[0] == "tidal" and c[1] == "/v2/searchResults"]
    assert len(after) == before, "found tracks come from the cache"


def test_similar_tracks_and_vibe_go_to_tidal(app):
    tidal_out(app)
    e = app.engine
    r = app.Lines()
    e.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert the_24bit7(app)["items"] and done_count(r), r.text()
    r = app.Lines()
    e.create_vibe_playlist("Sunday morning", report=r)
    assert done_count(r), r.text()
    assert not app.jriver.calls_to("Playback/PlayByKey")


def test_voice_commands_still_go_to_jriver(app):
    tidal_out(app)
    e = app.engine
    e.OUTPUT_OVERRIDE = "Speakers"
    try:
        assert e.output_streaming() is None
    finally:
        e.OUTPUT_OVERRIDE = None
    assert e.output_streaming() == "Tidal"


def test_review_builds_still_check_the_library(app):
    tidal_out(app)
    e = app.engine
    e.REVIEW_MODE = True
    try:
        assert e.output_streaming() is None
    finally:
        e.REVIEW_MODE = False


def test_youtube_and_jriver_outputs_unchanged(app, monkeypatch):
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url))
    e = app.engine
    app.set_env(OUTPUT_TARGET="youtube")
    assert e.output_is_youtube() and not e.output_is_tidal()
    r = app.Lines()
    e.create_similar_playlist(report=r, seed_info=seed(app))
    assert opened and "watch_videos" in opened[0] and r.has("sent to YouTube"), r.text()
    app.set_env(OUTPUT_TARGET="jriver")
    assert e.output_streaming() is None
    r = app.Lines()
    e.create_similar_playlist(report=r, seed_info=seed(app))
    assert app.jriver.titles("Speakers") and r.has("queued in")
    assert not app.web._tidal_playlist_store()


def test_open_links(app):
    app_url, web_url = app.engine.tidal_open_links("abc")
    assert app_url == "tidal://playlist/abc"
    assert web_url == "https://listen.tidal.com/playlist/abc"


def test_unknown_output_falls_back_to_jriver(app):
    app.set_env(OUTPUT_TARGET="spotify")
    assert app.engine.OUTPUT_TARGET == "jriver"
    app.set_env(OUTPUT_TARGET="tidal", EXTRA_OUTPUTS="youtube,tidal")
    assert app.engine.OUTPUT_TARGET == "tidal"
    app.set_env(EXTRA_OUTPUTS="youtube")   # Tidal unticked under Additional Outputs
    assert app.engine.OUTPUT_TARGET == "jriver"


def test_a_track_tidal_lacks_is_a_miss(app):
    tidal_out(app)
    e = app.engine
    sid = e.session_start("similar", seed(app))
    assert e.find_jriver_key_by_track("Nobody", "Nothing At All") is None
    e.session_log(sid, "Nobody", "Nothing At All", ["Last.fm"], found=False)
    assert e.STREAM_MISSES == 1
    assert e.done_line(0).startswith("Done: nothing sent to Tidal")


def test_lines_say_on_tidal_not_in_library(app):
    tidal_out(app)
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert r.has("On Tidal:") and r.has("on Tidal"), r.text()
    assert not any("in library" in line.lower() for line in r), r.text()


def test_jriver_lines_still_say_in_library(app):
    r = app.Lines()
    app.engine.create_similar_tracks_playlist(report=r, seed_info=seed(app))
    assert r.has("In library:") and not r.has("Tidal"), r.text()


def test_artist_checks_grouped_twenty_at_a_time(app):
    tidal_out(app)
    e = app.engine
    pairs = [(a, t) for a in app.web.artists for t in app.web.top_tracks(a)][:45]
    ids = e.tidal_ids_for_pairs(pairs)
    assert all(ids[:5])
    details = [c for c in app.web.calls if c[0] == "tidal" and c[1] == "/v2/tracks"]
    searches = [c for c in app.web.calls if c[0] == "tidal" and c[1] == "/v2/searchResults"]
    assert len(searches) == len(set(pairs))
    assert len(details) <= 6, f"{len(details)} detail requests for {len(pairs)} tracks"   # not one per track


# --- Open In (Settings > Other > Additional Outputs > Tidal) ---

def test_build_opens_the_playlist_in_the_app_by_default(app, monkeypatch):
    tidal_out(app)
    e = app.engine
    assert e.TIDAL_OPEN == "app"
    monkeypatch.setattr(e, "tidal_app_installed", lambda: True)
    r = app.Lines()
    e.create_similar_playlist(report=r, seed_info=seed(app))
    assert app.opened == [f"tidal://playlist/{e.TIDAL_PLAYLIST_ID}"], r.text()
    assert e.TIDAL_OPENED == "app"


def test_open_in_web(app, monkeypatch):
    tidal_out(app, TIDAL_OPEN="web")
    e = app.engine
    monkeypatch.setattr(e, "tidal_app_installed", lambda: True)
    e.create_similar_playlist(report=app.Lines(), seed_info=seed(app))
    assert app.opened == [f"https://listen.tidal.com/playlist/{e.TIDAL_PLAYLIST_ID}"]
    assert e.TIDAL_OPENED == "web"


def test_no_app_opens_the_website_and_says_so(app, monkeypatch):
    tidal_out(app)
    e = app.engine
    monkeypatch.setattr(e, "tidal_app_installed", lambda: False)
    r = app.Lines()
    e.create_similar_playlist(report=r, seed_info=seed(app))
    assert app.opened == [f"https://listen.tidal.com/playlist/{e.TIDAL_PLAYLIST_ID}"]
    assert r.has("The Tidal app isn't installed, so the playlist opened on Tidal's website."), r.text()


def test_nothing_opens_when_nothing_went_in(app):
    tidal_out(app, TIDAL_REFRESH_TOKEN="")
    app.engine.create_similar_playlist(report=app.Lines(), seed_info=seed(app))
    assert app.opened == []


def test_open_in_setting_reads(app):
    e = app.engine
    for raw, want in (("web", "web"), ("app", "app"), ("", "app"), ("nonsense", "app")):
        app.set_env(TIDAL_OPEN=raw)
        assert e.TIDAL_OPEN == want, raw
