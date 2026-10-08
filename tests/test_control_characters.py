"""
Hidden control characters in tags (a pasted line break, a stray byte from an old
ripper) mustn't stop 24bit7 reading JRiver. JSON replies keep them as they are;
XML replies, which can't hold most of them, get spaces instead.
"""

import ast
import glob
import os


class Reply:
    def __init__(self, text, status_code=200):
        self.text, self.status_code = text, status_code


def test_library_json_keeps_control_characters(app, monkeypatch):
    library = app.library
    raw = '[{"Key": "1", "Name": "Line one\nLine two\x01", "Artist": "A\tB"}]'   # raw, as a messy library sends it
    monkeypatch.setattr(library, "_get", lambda path, **params: Reply(raw))
    rows = library._read_tracks()
    assert rows[0]["Name"] == "Line one\nLine two\x01"
    assert rows[0]["Artist"] == "A\tB"


def test_library_mpl_fallback_reads_past_them(app, monkeypatch):
    library = app.library
    mpl = ('<MPL><Item><Field Name="Key">1</Field><Field Name="Name">Bad\x02Title</Field>'
           '<Field Name="Artist">Tab\there</Field></Item></MPL>')
    replies = {"JSON": Reply("not json at all"), "MPL": Reply(mpl)}
    monkeypatch.setattr(library, "_get", lambda path, **params: replies[params["Action"]])
    rows = library._read_tracks()
    assert rows == [{"Key": "1", "Name": "Bad Title", "Artist": "Tab\there"}]


def test_now_playing_reads_past_them(app, monkeypatch):
    e = app.engine
    xml = ('<Response Status="OK"><Item Name="Artist">Some\x03Artist</Item><Item Name="Name">Song</Item>'
           '<Item Name="Album">Album</Item><Item Name="PlayingNowPosition">0</Item></Response>')
    monkeypatch.setattr(e.requests, "get", lambda *a, **k: Reply(xml))
    info = e.get_playing_info(zone="0")
    assert info is not None and info["Artist"] == "Some Artist"


def test_xml_safe_keeps_tabs_and_line_breaks(app):
    assert app.engine.xml_safe("a\tb\nc\rd\x00e\x1ff") == "a\tb\nc\rd e f"


def test_every_xml_reply_goes_through_xml_safe(app):
    """Any new place that reads JRiver's XML must clean it first."""
    unsafe = []
    for path in glob.glob(os.path.join(app.folder, "*.py")) + glob.glob(os.path.join(app.folder, "*.pyw")):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "fromstring" \
                    and getattr(node.func.value, "id", None) == "ET":
                arg = node.args[0] if node.args else None
                inner = getattr(getattr(arg, "func", None), "attr", None) or getattr(getattr(arg, "func", None), "id", None)
                if inner != "xml_safe":
                    unsafe.append(f"{os.path.basename(path)} line {node.lineno}")
    assert not unsafe, "XML read without xml_safe: " + ", ".join(unsafe)
