"""
The dev copy says so (Ben, 11 Nov 2026): run from a checkout on a branch other than main, the window's name,
the tray icon and a tag beside the version say Dev, so he can tell which 24bit7 is running. The packaged app
and a main checkout look as they always did.
"""

import os
import sys


def checkout(folder, head, worktree=False):
    """A .git as git leaves it: a folder, or (a worktree) a file pointing at one elsewhere."""
    if worktree:
        gitdir = folder.parent / "main-repo" / ".git" / "worktrees" / folder.name
        gitdir.mkdir(parents=True)
        (folder / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    else:
        gitdir = folder / ".git"
        gitdir.mkdir()
    (gitdir / "HEAD").write_text(head + "\n", encoding="utf-8")


def test_the_branch_is_read_from_a_folder_or_a_worktree(app, tmp_path):
    e = app.engine
    a, b, c, d = (tmp_path / n for n in "abcd")
    for f in (a, b, c, d):
        f.mkdir()
    checkout(a, "ref: refs/heads/main")
    checkout(b, "ref: refs/heads/dev", worktree=True)
    checkout(c, "3f2a9c0d1e2b3c4d5e6f708192a3b4c5d6e7f809")   # detached
    assert e.git_branch(str(a)) == "main"
    assert e.git_branch(str(b)) == "dev"
    assert e.git_branch(str(c)) == ""
    assert e.git_branch(str(d)) == "", "no checkout at all, as for the zip"


def test_a_dev_checkout_is_the_dev_copy_and_says_so(app, monkeypatch):
    import gui
    import tray
    e = app.engine
    assert not e.dev_copy(), "the fake world has no .git, like the zip"
    assert gui.window_title() == f"24bit7  v{e.VERSION}" and tray.tooltip() == "24bit7"
    checkout(__import__("pathlib").Path(e.APP_DIR), "ref: refs/heads/dev", worktree=True)
    assert e.dev_copy()
    assert gui.window_title() == f"24bit7 Dev  v{e.VERSION}" and tray.tooltip() == "24bit7 Dev"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert not e.dev_copy(), "the packaged app never is, whatever folder it sits in"


def test_a_main_checkout_is_not(app):
    e = app.engine
    checkout(__import__("pathlib").Path(e.APP_DIR), "ref: refs/heads/main")
    assert not e.dev_copy()
    assert os.path.isdir(os.path.join(e.APP_DIR, ".git"))
