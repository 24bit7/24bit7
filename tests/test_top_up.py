"""
Top-Up (Ben, 5 Nov 2026): a playlist run with Top-Up on goes into what's left of the zone's Playing Now
instead of replacing it. The playing track and the played ones stay put; the unplayed rest and the new
tracks, none already in Playing Now, are shuffled together after the playing track. It counts as sent for
Non-stop. In Review, only the new tracks are listed, and Review's Top-Up merges them the same way.
"""


def keys_of(app, n):
    return [row["Key"] for row in app.jriver.tracks][:n]


def playing(app, keys, pos=2):
    app.jriver.play("Speakers", keys, pos=pos, state=2)
    return app.jriver.zone("Speakers")


def send(app, keys, top_up=True, monkeypatch=None):
    monkeypatch.setattr(app.engine, "TOP_UP", top_up)
    r = app.Lines()
    app.engine.send_to_jriver(keys, report=r, zone_name="Speakers")
    return r


def test_top_up_keeps_what_played_and_shuffles_the_new_in_with_the_rest(app, monkeypatch):
    every = keys_of(app, 20)
    before = every[:8]            # 0, 1 played; 2 playing; 3 to 7 still to play
    z = playing(app, before, pos=2)
    new = every[8:14] + [every[5], every[1]]   # six new, one still to play, one already played
    r = send(app, new, monkeypatch=monkeypatch)
    assert z.playlist[:3] == before[:3] and z.pos == 2 and z.state == 2, "played and playing left alone"
    after = z.playlist[3:]
    assert sorted(after) == sorted(before[3:] + every[8:14]), "the rest plus the six new, nothing twice"
    assert len(after) == len(set(after))
    assert r.has("Top-Up: 6 new tracks joined the 5 still to play in Speakers, shuffled together."), r.text()
    assert r.has("2 were already there.") and r.has("The track playing carries on."), r.text()
    sent = app.engine.nonstop_sent("10001")
    assert set(z.playlist) <= sent, "the merged queue counts as sent, so Non-stop repeats none of it"


def test_without_top_up_a_busy_zone_is_replaced_after_the_current_track(app, monkeypatch):
    every = keys_of(app, 20)
    z = playing(app, every[:8], pos=2)
    send(app, every[8:14], top_up=False, monkeypatch=monkeypatch)
    assert z.playlist == [every[2]] + every[8:14], "the usual: the playing track, then the new playlist"


def test_nothing_new_changes_nothing(app, monkeypatch):
    every = keys_of(app, 10)
    z = playing(app, every[:8], pos=2)
    r = send(app, every[3:6], monkeypatch=monkeypatch)
    assert z.playlist == every[:8]
    assert r.has("Top-Up: every track found is already in Playing Now in Speakers, so nothing changed."), r.text()


def test_a_stopped_zone_plays_as_usual_and_says_so(app, monkeypatch):
    every = keys_of(app, 10)
    app.jriver.play("Speakers", every[:4], pos=1, state=0)
    z = app.jriver.zone("Speakers")
    r = send(app, every[4:9], monkeypatch=monkeypatch)
    assert z.playlist == every[4:9] and z.state == 2
    assert r.has("Top-Up: Speakers was stopped, so the playlist plays as usual."), r.text()


def test_review_lists_only_the_new_and_its_top_up_merges(app, monkeypatch):
    every = keys_of(app, 20)
    before = every[:8]
    z = playing(app, before, pos=2)
    monkeypatch.setattr(app.engine, "REVIEW_MODE", True)
    app.engine.review_reset()
    send(app, every[8:12] + [every[4], every[0]], monkeypatch=monkeypatch)
    assert app.engine.REVIEW_KEYS == every[8:12], "only what isn't in Playing Now already"
    assert z.playlist == before, "Review touches nothing"
    line = app.engine.review_send(every[8:12], "topup", "10001")
    assert z.playlist[:3] == before[:3] and sorted(z.playlist[3:]) == sorted(before[3:] + every[8:12])
    assert line.startswith("Review: Top-Up: 4 new tracks joined the 5 still to play in Speakers"), line


def test_a_mix_or_drift_round_after_the_first_merges_too(app, monkeypatch):
    every = keys_of(app, 24)
    before = every[:6]
    z = playing(app, before, pos=1)
    send(app, every[6:10], monkeypatch=monkeypatch)
    r = app.Lines()
    app.engine.send_to_jriver(every[10:13], report=r, zone_name="Speakers", append=True)
    assert z.playlist[:2] == before[:2]
    assert sorted(z.playlist[2:]) == sorted(before[2:] + every[6:13]), "shuffled in, not stuck on the end"
    assert r.has("Top-Up: another 3 new tracks shuffled in."), r.text()
