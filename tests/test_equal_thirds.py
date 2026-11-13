"""
The Playlists & Albums row's widths: the Album or Playlist box takes two fifths (Ben, 13 Nov 2026: "a little wider";
equal thirds from 10 Nov), Play and Embellish split the rest equally. The arithmetic, with no window; the row itself
is checked in tests/test_jriver_playlists_tab.py.
"""


def test_two_fifths_then_two_equal_widths_fill_the_span_exactly(app):
    import tabs
    assert tabs.row_shares(1032, 24, 8) == (400, 300, 300)
    for span in (700, 701, 702, 1415):
        box, play, emb = tabs.row_shares(span, 24, 8)
        assert play == emb and abs(box - 0.4 * (span - 32)) <= 2, (span, box, play, emb)
        assert box + 24 + play + 8 + emb == span, "they end where the span does, to the pixel"


def test_a_span_too_small_gives_nothing_rather_than_a_negative_width(app):
    import tabs
    assert tabs.row_shares(20, 24, 8) == (0, 0, 0)
