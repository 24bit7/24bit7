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
    lines = app.printed.text().splitlines()
    assert lines[0] == f"Note: 24bit7 99.0.0 is out (you have {app.engine.VERSION}). New since yours:", lines
    assert lines[1].strip() == "99.0.0" and lines[-1].strip() == f"Download: {LINK}99.0.0", lines


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
    assert app.engine.newer_release() == ("99.0.0", LINK + "99.0.0", "")


def test_the_line_gives_the_release_headline(app):
    """12 Nov 2026: the line says what the release does, from the notes' bold first sentence."""
    app.web.latest_release = dict(_release("99.0.0"), body="**Radio gets a pause button.**\r\n\r\nMore words.\r\n")
    app.engine.say_if_newer(app.printed)
    assert "  99.0.0  Radio gets a pause button." in app.printed.text().splitlines(), app.printed.text()


def test_notes_without_a_headline_keep_the_short_line(app):
    for body in ("Just words.", "", None, "**" + "x" * 400 + "**"):
        assert app.engine.release_headline(body) == ""


def test_the_headline_is_plain_text_on_one_line(app):
    assert app.engine.release_headline("  **Two\nlines, *some* stars.** rest") == "Two lines, some stars."


# 17 Nov 2026, Ben: the note lists every release since yours, so you can tell whether it's worth updating.

def _listed(*versions, assets=True):
    out = []
    for v in versions:
        rel = dict(_release(v), body=f"**What {v} does.**" + "\n\nMore.")
        if assets:
            name = f"24bit7-v{v}-windows.zip"
            base = f"https://github.com/24bit7/24bit7/releases/download/v{v}/"
            rel["assets"] = [{"name": name, "browser_download_url": base + name},
                             {"name": name + ".sha256", "browser_download_url": base + name + ".sha256"}]
        out.append(rel)
    return out


def test_every_release_since_yours_is_listed_newest_first(app):
    app.web.releases = _listed("98.1.0", "99.0.0", "98.0.1", "1.0.0")   # GitHub's order isn't relied on
    info = app.engine.whats_new()
    assert info["latest"] == "99.0.0" and [v for v, _ in info["releases"]] == ["99.0.0", "98.1.0", "98.0.1"]
    assert app.engine.whats_new_lines(info)[1:] == ["  99.0.0  What 99.0.0 does.", "  98.1.0  What 98.1.0 does.",
                                                    "  98.0.1  What 98.0.1 does."]


def test_a_long_gap_lists_ten_and_counts_the_rest(app):
    app.web.releases = _listed(*[f"90.{n}.0" for n in range(22)])
    lines = app.engine.whats_new_lines(app.engine.whats_new())
    assert len(lines) == 1 + 10 + 1 and lines[1].startswith("  90.21.0") and lines[-1] == "  and twelve older releases"


def test_drafts_and_prereleases_are_left_out(app):
    rels = _listed("99.0.0", "98.0.0")
    rels[0]["draft"] = True
    app.web.releases = rels
    assert app.engine.whats_new()["latest"] == "98.0.0"


def test_the_download_is_only_ever_from_our_own_release(app):
    app.web.releases = _listed("99.0.0")
    info = app.engine.whats_new()
    assert info["zip"].endswith("/download/v99.0.0/24bit7-v99.0.0-windows.zip") and info["sha256"].endswith(".sha256")
    rels = _listed("99.0.0")
    rels[0]["assets"][0]["browser_download_url"] = "https://example.com/24bit7-v99.0.0-windows.zip"
    app.web.releases = rels
    assert app.engine.whats_new()["zip"] == "" == app.engine.whats_new()["sha256"]
    app.web.releases = _listed("99.0.0", assets=False)   # no fingerprint, no download
    assert app.engine.whats_new()["zip"] == ""
