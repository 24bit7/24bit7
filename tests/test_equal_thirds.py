"""
The JRiver Playlists row in equal thirds (Ben, 10 Nov 2026): the Playlist box, Play and Play & Embellish share
the span they had, each the same width. The arithmetic, with no window; the row itself is checked in
tests/test_jriver_playlists_tab.py.
"""


def test_three_equal_widths_fill_the_span_exactly(app):
    import tabs
    assert tabs.equal_thirds(932, 24, 8) == (300, 300, 300)
    for span in (700, 701, 702, 1415):
        box, play, emb = tabs.equal_thirds(span, 24, 8)
        assert play == emb and 0 <= box - play <= 2, (span, box, play, emb)
        assert box + 24 + play + 8 + emb == span, "they end where the span does, to the pixel"


def test_a_span_too_small_gives_nothing_rather_than_a_negative_width(app):
    import tabs
    assert tabs.equal_thirds(20, 24, 8) == (0, 0, 0)
