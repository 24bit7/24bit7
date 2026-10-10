"""Test My Sources on screen: the scores beside each source, the start window and Full Results."""

import json

import pytest

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_source_test import SEEDS


def seeds(app):
    (app.folder / "source_test_seeds.json").write_text(json.dumps({"version": 1, "seeds": SEEDS}), encoding="utf-8")
    import source_test
    return source_test


def sources_page(ui):
    pane = next(c for c in ui.settings.winfo_children() if hasattr(c, "select"))
    ui.nb.select(ui.settings)
    ui.pump(0.5)
    from test_gui import visit_every_page
    visit_every_page(ui, pane)
    main = ui.settings._main_sources
    return main.score_ui


def test_no_results_yet(app, ui):
    seeds(app)
    sc = sources_page(ui)
    assert sc["artists"]["notice"].cget("text").startswith("No results yet")
    assert sc["artists"]["test"].cget("text") == "Test My Sources"


def test_sample_then_own_results(app, ui):
    s = seeds(app)
    s.run(quick=True, wait_for_builds=False)
    s.make_sample()
    s._table().execute("DELETE FROM source_tests")
    sc = sources_page(ui)
    ui.settings._refresh_scores()
    assert sc["tracks"]["notice"].cget("text").startswith("Sample results from a")
    perf, best, worst = sc["tracks"]["cells"]["lastfm"]
    assert perf.cget("text").endswith("%") and best.cget("text")
    assert sc["artists"]["cells"]["ai"][0].cget("text") == "-"   # not tested
    s.run(quick=True, wait_for_builds=False)
    ui.settings._refresh_scores()
    assert sc["tracks"]["notice"].cget("text").startswith("Your results, tested")
    assert sc["tracks"]["test"].cget("text") == "Re-run Test"


def test_start_window_passes_its_choices(app, ui, monkeypatch):
    s = seeds(app)
    sources_page(ui)
    asked = []
    monkeypatch.setattr(s, "start_background", lambda quick=False, include_ai=False: asked.append((quick, include_ai)))
    win = ui.settings._open_test_window()
    win.mode.set("quick")
    win.start()
    assert asked == [(True, False)]


def test_full_results_opens_marks_seen_and_exports(app, ui, monkeypatch, tmp_path):
    s = seeds(app)
    s.run(quick=True, wait_for_builds=False)
    assert s.unseen()
    sources_page(ui)
    win = ui.settings._open_test_results()
    ui.pump(0.3)
    assert win.title() == "Source Test Results" and win.grids["tracks"] and win.grids["artists"]
    assert not s.unseen()
    from tkinter import filedialog
    monkeypatch.setattr(filedialog, "asksaveasfilename", lambda **k: str(tmp_path / "r.csv"))
    win.export()
    assert (tmp_path / "r.csv").read_text(encoding="utf-8").startswith("Section,Genre")
    win.destroy()
