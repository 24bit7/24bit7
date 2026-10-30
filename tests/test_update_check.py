"""
A line in the console when a newer 24bit7 is out (30 Oct 2026, the smaller option in place of an
updater). Asked once at start-up; silent when up to date, offline, or GitHub says anything odd.
"""

LINK = "https://github.com/24bit7/24bit7/releases/tag/v"


def _release(version, url=None):
    return {"tag_name": f"v{version}", "html_url": url or LINK + version}


def test_newer_says_so_with_the_link(app):
    app.web.latest_release = _release("99.0.0")
    app.engine.say_if_newer(app.printed)
    line = app.printed.text()
    assert line == f"Note: 24bit7 99.0.0 is out (you have {app.engine.VERSION}). Download: {LINK}99.0.0", line


def test_compares_numbers_not_text(app):
    major, minor, patch = (int(n) for n in app.engine.VERSION.split("."))
    app.web.latest_release = _release(f"{major}.{minor}.{patch + 10}")   # 1.28.10 is newer than 1.28.9
    assert app.engine.newer_release()


def test_same_or_older_says_nothing(app):
    for version in (app.engine.VERSION, "1.0.0"):
        app.web.latest_release = _release(version)
        app.engine.say_if_newer(app.printed)
    assert not app.printed


def test_offline_or_no_answer_says_nothing(app):
    app.web.latest_release = _release("99.0.0")
    app.web.down.add("github")
    app.engine.say_if_newer(app.printed)
    app.web.down.clear()
    app.web.latest_release = None   # GitHub answers 404
    app.engine.say_if_newer(app.printed)
    assert not app.printed


def test_only_ever_links_to_our_own_releases(app):
    app.web.latest_release = _release("99.0.0", url="https://example.com/not-ours")
    assert app.engine.newer_release() == ("99.0.0", LINK + "99.0.0")
