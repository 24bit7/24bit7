"""The Dev tag beside the version in the main window (Ben, 11 Nov 2026), and none on the app as people get it."""

import pytest

from test_gui import ui  # noqa: F401  (the fixture)


@pytest.fixture
def dev(app):
    """The fake world's folder as a dev worktree, before the window is built."""
    import pathlib
    folder = pathlib.Path(app.engine.APP_DIR)
    gitdir = folder.parent / "main-repo" / ".git" / "worktrees" / "24bit7"
    gitdir.mkdir(parents=True)
    (folder / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    (gitdir / "HEAD").write_text("ref: refs/heads/dev\n", encoding="utf-8")


def test_a_dev_copy_shows_the_tag_beside_the_version(app, dev, ui):
    from tabs import PALETTE
    tag = ui.play.dev_tag
    assert tag is not None and tag.cget("text") == "Dev"
    assert tag.cget("bg") == PALETTE["logo_bit"]
    ui.pump(0.2)
    version = next(w for w in tag.master.winfo_children() if w.cget("text") == f"v{app.engine.VERSION}")
    assert tag.winfo_ismapped() and tag.winfo_rootx() < version.winfo_rootx(), "just left of the version"
    assert not ui.errors, ui.errors[0]


def test_the_app_as_people_get_it_has_no_tag(app, ui):
    assert ui.play.dev_tag is None
