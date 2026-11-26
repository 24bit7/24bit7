"""
The Speakers follow only JRiver's music (Ben, 26 Nov 2026). A stuck Alexa flash briefing left the Sonos holding the
BBC news; Play in JRiver resumed it, the Sonos's counter ran, and the Speakers played JRiver's track in step with the
news. The follower now asks the Sonos what it's streaming (UPnP TrackURI): while that isn't a JRiver track from this
PC, the Speakers wait, said once, and they join again by the usual rules once it is. Simulated clock; no windows.
"""

import os
import sys
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import sonos
finally:
    sys.path.remove(REPO)

from test_follower import World

LINE = "Note: the Sonos is playing something else, so the Speakers are waiting."
JRIVER = "http://192.168.0.133:52100/Music/F45356.wav"
NEWS = "x-sonosapi-hls-static:bbc-news-briefing?sid=254&flags=8232"


def test_the_speakers_wait_while_the_sonos_plays_something_else():
    w = World()
    w.f.stream = SimpleNamespace(elsewhere=True)
    w.run(0.5)
    w.play(key=7)
    w.run(6.0)
    assert not w.outs, "the Speakers started over something that isn't JRiver's"
    assert w.said(LINE) and len(w.said(LINE)) == 1, w.lines


def test_the_speakers_stop_when_the_sonos_moves_off_jriver_and_join_again_when_it_is_back():
    w = World()
    watch = SimpleNamespace(elsewhere=False)
    w.f.stream = watch
    w.run(0.5)
    w.play(key=7)
    w.run(4.0)
    assert w.f.out is not None, "following to begin with"
    watch.elsewhere = True
    w.run(1.0)
    assert w.f.out is None and w.outs[-1].closed, "the Speakers stopped"
    assert len(w.said(LINE)) == 1
    watch.elsewhere = False
    w.play(key=7)   # Play in JRiver again, now the Sonos is back on JRiver's stream
    w.run(5.0)
    assert len(w.outs) == 2 and w.f.out is not None, w.lines
    assert w.f.track["key"] == 7


def test_a_jriver_track_from_this_pc_is_jriver_on_any_of_its_servers():
    hosts = {"192.168.0.133", "100.69.66.88"}
    assert sonos.from_jriver(JRIVER, hosts)
    assert sonos.from_jriver("http://192.168.0.133:52101/Music/F12.flac", hosts), "the Multiroom server's port too"
    assert not sonos.from_jriver(NEWS, hosts)
    assert not sonos.from_jriver("http://192.168.0.50:52100/Music/F1.wav", hosts), "another PC's JRiver"
    assert not sonos.from_jriver("http://192.168.0.133:8080/radio.mp3", hosts)
    assert not sonos.from_jriver("", hosts)


def test_the_watch_needs_two_reads_in_a_row_and_never_counts_nothing_known():
    reads = []
    w = sonos.StreamWatch("192.168.0.184", ["192.168.0.133"], read=lambda: reads.pop(0))

    def fails():
        raise OSError("no answer")

    for uri, want in ((NEWS, False), (NEWS, True), (JRIVER, False), (NEWS, False), ("", False), (NEWS, False),
                      (NEWS, True)):
        reads.append(uri)
        assert w.check() is want, (uri, want)
    w.read = fails
    assert w.check() is False, "a failed read never holds the Speakers back"
