"""
Match Tempo (Ben, 5 Nov 2026), per config of Similar Artists and Similar Tracks. Prefer puts the tempos
closest to the seed's first wherever there's a choice and leaves nothing out; Strict keeps only tracks within
ten per cent of the seed's BPM and says how many went. Half and double time count. No seed BPM: a line saying
it isn't in effect and how to fix it in JRiver. Simple builds Strict as Prefer. A BPM over four hundred is a
mistake, so it counts as untagged.
"""

SEED = ("The Beatles", "Here Comes The Sun")


def tag_bpms(app, seed_bpm="120"):
    """The seed at 120; others by key: in time (121), double time (240), off tempo (90) or untagged."""
    seed_key = app.jriver.key_of(*SEED)
    for k, row in app.jriver.by_key.items():
        n = int(k) % 4
        row["BPM"] = seed_bpm if k == seed_key else ("121" if n == 0 else "240" if n == 1 else "90" if n == 2 else "")
    import library
    library.load()
    return seed_key


def build(app, kind="artists", **env):
    app.set_env(**env)
    app.engine.load_settings()
    r = app.Lines()
    seed = app.engine.typed_seed_info(*SEED)
    if kind == "artists":
        app.engine.create_similar_playlist(report=r, seed_info=seed)
    else:
        app.engine.create_similar_tracks_playlist(report=r, seed_info=seed)
    return r, app.jriver.zone("Speakers").playlist


def test_half_and_double_time_count_as_a_match(app):
    e = app.engine
    assert e.tempo_gap(120, 120) == 0 and e.tempo_gap(60, 120) == 0 and e.tempo_gap(240, 120) == 0
    assert round(e.tempo_gap(132, 120), 2) == 0.10 and e.tempo_gap(90, 120) > e.TEMPO_BAND


def test_strict_keeps_only_tracks_in_tempo_and_says_how_many_went(app):
    seed_key = tag_bpms(app)
    r, sent = build(app, MATCH_TEMPO_ARTISTS="strict")
    assert r.has("Match Tempo, Strict: within 10% of the seed's 120 BPM, half and double time included."), r.text()
    rows = app.jriver.by_key
    others = [k for k in sent if k != seed_key]
    assert others, r.text()
    assert all(rows[k]["BPM"] in ("121", "240") for k in others), [rows[k]["BPM"] for k in others]
    assert r.has("Match Tempo left out"), r.text()


def test_strict_similar_tracks_too(app):
    seed_key = tag_bpms(app)
    r, sent = build(app, kind="tracks", MATCH_TEMPO_TRACKS="strict")
    rows = app.jriver.by_key
    assert all(rows[k]["BPM"] in ("121", "240") for k in sent if k != seed_key), r.text()


def test_prefer_orders_by_tempo_and_leaves_nothing_out(app):
    tag_bpms(app)
    e = app.engine
    r = app.Lines()
    tempo = e.TempoMatch("artists", [app.jriver.key_of(*SEED)], r)   # MATCH_TEMPO comes from .env: off
    assert not tempo.on
    app.set_env(MATCH_TEMPO_ARTISTS="prefer")
    e.load_settings()
    tempo = e.TempoMatch("artists", [app.jriver.key_of(*SEED)], r)
    assert tempo.on and r.has("Match Tempo, Prefer: tempos closest to the seed's 120 BPM first."), r.text()
    seed_key = app.jriver.key_of(*SEED)
    first = {}
    for k, row in app.jriver.by_key.items():
        if k != seed_key:
            first.setdefault(row["BPM"], k)
    keys = [first[""], first["90"], first["121"], first["240"]]   # untagged, off tempo, in time, double time
    ordered = tempo.order(keys, lambda k: k)
    bpms = [app.jriver.by_key[k]["BPM"] for k in ordered]
    assert bpms[-1] == "", "untagged last"
    assert bpms.index("90") > max(bpms.index("121"), bpms.index("240")), bpms
    assert all(tempo.fits(k) for k in keys), "Prefer turns nothing down"
    tempo.done()
    r2, sent = build(app, MATCH_TEMPO_ARTISTS="prefer")
    assert not r2.has("Match Tempo left out") and len(sent) > 5, r2.text()


def test_no_seed_bpm_says_so_and_builds_as_usual(app):
    tag_bpms(app, seed_bpm="")
    r, sent = build(app, MATCH_TEMPO_ARTISTS="strict")
    assert r.has("Note: Match Tempo isn't in effect, as the seed track has no BPM tag."), r.text()
    assert r.has("Tools > Library Tools > Analyze Audio") and len(sent) > 5
    assert not r.has("Match Tempo left out")


def test_a_silly_bpm_counts_as_untagged(app):
    seed_key = tag_bpms(app, seed_bpm="900")
    assert app.engine.library_bpm(seed_key) is None


def test_simple_builds_strict_as_prefer(app, monkeypatch):
    import mode
    tag_bpms(app)
    monkeypatch.setattr(mode, "is_simple", lambda: True)
    app.set_env(MATCH_TEMPO_ARTISTS="strict")
    app.engine.load_settings()
    tempo = app.engine.TempoMatch("artists", [app.jriver.key_of(*SEED)], app.Lines())
    assert tempo.mode == "prefer"
    tempo.done()


def test_youtube_output_leaves_it_off(app, monkeypatch):
    tag_bpms(app)
    app.set_env(MATCH_TEMPO_ARTISTS="strict")
    app.engine.load_settings()
    monkeypatch.setattr(app.engine, "output_streaming", lambda: "YouTube")
    tempo = app.engine.TempoMatch("artists", [app.jriver.key_of(*SEED)], app.Lines())
    assert not tempo.on and app.engine.current_tempo() is None

