"""
24bit7 - builds the user manual PDF from docs/MANUAL.md.

Lays the manual out as a styled page (cover with the version and date, A4, each
chapter on a new page, screenshots sized to fit), then prints it to PDF with
Microsoft Edge, or Chrome if Edge isn't found. The contents and links between
chapters stay clickable.

Use:
  py build_manual.py                       writes 24bit7_Manual.pdf in this folder
  py build_manual.py path\\to\\file.pdf      writes it there (build.bat uses this)

Exits with an error code if the PDF couldn't be made, so build.bat can ask what to do.
"""

import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "docs" / "MANUAL.md"
DEFAULT_OUT = HERE / "24bit7_Manual.pdf"

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-center { content: counter(page); font: 9pt "Segoe UI", sans-serif; color: #888; } }
@page :first { @bottom-center { content: none; } }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #222; }
a { color: #1f4e8c; text-decoration: none; }
h1, h2, h3 { color: #1f4e8c; line-height: 1.2; }
h2 { font-size: 20pt; margin: 0 0 10pt; padding-bottom: 4pt; border-bottom: 1.5pt solid #1f4e8c;
     break-before: page; }
h3 { font-size: 13pt; margin: 16pt 0 6pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
img { display: block; max-width: 100%; max-height: 225mm; width: auto; height: auto;
      margin: 8pt auto 12pt; border: 0.75pt solid #aab4c3; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9.5pt; }
th, td { border: 0.75pt solid #aab4c3; padding: 4pt 6pt; vertical-align: top; text-align: left; }
th { background: #e8edf4; }
tr { break-inside: avoid; }
code { font-family: Consolas, monospace; font-size: 9pt; background: #f2f2f2; padding: 0 2pt; }
pre { background: #f2f2f2; padding: 6pt 8pt; border-left: 3pt solid #aab4c3; white-space: pre-wrap;
      break-inside: avoid; }
pre code { background: none; padding: 0; }
hr { display: none; }
#contents { break-before: auto; margin-top: 18pt; }   /* the intro and the contents share a page */
.cover { break-after: page; height: 240mm; display: flex; flex-direction: column; justify-content: center; text-align: center; }
.logo { font-size: 54pt; font-weight: bold; letter-spacing: -1pt; }
.blue { color: #1f4e8c; } .orange { color: #f28c28; }
.tagline { font-size: 13pt; color: #666; margin-top: 4pt; }
.title { font-size: 26pt; color: #1f4e8c; margin-top: 36pt; }
.meta { font-size: 11pt; color: #666; margin-top: 10pt; }
"""


def fail(msg):
    print("Manual PDF: " + msg)
    sys.exit(1)


def version():
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', (HERE / "engine.py").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "?"


def markdown_module():
    try:
        import markdown
    except ImportError:
        print("Manual PDF: installing the markdown library (first time only)...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "markdown"])
        if r.returncode != 0:
            fail("couldn't install the markdown library (pip install markdown).")
        import markdown
    return markdown


def slug(value, separator="-"):
    """GitHub's heading anchors, so links like #setting-up-the-alexa-skill work the same in the PDF."""
    value = re.sub(r"[^\w\- ]", "", value.strip().lower())
    return value.replace(" ", separator)


def build_html(ver):
    md = SOURCE.read_text(encoding="utf-8")
    md = re.sub(r"\A# .*\n", "", md)   # the cover carries the title
    body = markdown_module().markdown(md, extensions=["tables", "fenced_code", "toc"],
                                      extension_configs={"toc": {"slugify": slug}})
    today = date.today()
    cover = (f'<div class="cover"><div class="logo"><span class="blue">24</span><span class="orange">bit'
             f'</span><span class="blue">7</span></div>'
             f'<div class="tagline">Smart Playlist Creator and Music Discovery Tool</div>'
             f'<div class="title">User Manual</div>'
             f'<div class="meta">Version {html.escape(ver)} &nbsp;&middot;&nbsp; '
             f'{today.strftime("%B")} {today.year}</div></div>')
    base = (SOURCE.parent.as_uri() + "/")   # so images/... resolves to docs/images
    return (f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><base href="{base}">'
            f'<title>24bit7 User Manual {html.escape(ver)}</title><style>{CSS}</style></head>'
            f'<body>{cover}{body}</body></html>')


def find_browser():
    names = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
    roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData")]
    for name in names:
        for root in roots:
            if root and os.path.isfile(os.path.join(root, name)):
                return os.path.join(root, name)
    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def main():
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUT
    if not SOURCE.exists():
        fail(f"{SOURCE} not found.")
    browser = find_browser()
    if not browser:
        fail("neither Microsoft Edge nor Chrome was found to print the PDF.")
    ver = version()
    work = Path(tempfile.mkdtemp(prefix="24bit7_manual_"))
    try:
        page = work / "manual.html"
        page.write_text(build_html(ver), encoding="utf-8")
        if out.exists():
            out.unlink()
        out.parent.mkdir(parents=True, exist_ok=True)
        # Its own profile folder, so an Edge window you have open doesn't take the job over
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
               f"--user-data-dir={work / 'profile'}", f"--print-to-pdf={out}", page.as_uri()]
        try:
            subprocess.run(cmd, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            fail("the browser took too long to print the PDF.")
        if not out.exists() or out.stat().st_size < 10000:
            fail("the browser ran but no PDF came out.")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"Manual PDF: {out} (version {ver}, {out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
