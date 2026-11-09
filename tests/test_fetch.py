"""
Multiroom, fetching the track (9 Nov 2026): the WAV header, the samples sample-exact at every rate and depth, range
reads from any sample, seeking, the thirty-seconds-ahead limit, the end of a track, and a stall that mustn't shift
anything. Against tests/fake_dlna.py; nothing touches JRiver.
"""

import os
import struct
import sys
import time

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import fetch
finally:
    sys.path.remove(REPO)
from fake_dlna import SCALE, FakeDLNA, Track


@pytest.fixture
def server():
    with FakeDLNA() as s:
        yield s


def expected(first, n, bits):
    return (np.arange(first, first + n) % SCALE[bits]) / SCALE[bits]


def check(block, first, bits):
    assert np.allclose(block[:, 0], expected(first, len(block), bits), atol=1e-9), "left channel out of place"
    assert np.allclose(block[:, 1], -expected(first, len(block), bits), atol=1e-9), "right channel out of place"


def read_all(stream, n, frames, timeout=5.0):
    """Reads n frames in blocks of frames, waiting for data, as an output that never runs dry would."""
    out = []
    while sum(len(b) for b in out) < n:
        assert stream.wait_buffered(frames, timeout) or stream.ended
        block, got = stream.read(frames)
        out.append(block[:got])
        if stream.done:
            break
    return np.concatenate(out)[:n]


# --- the header --------------------------------------------------------------------------------

def test_the_header_jriver_serves():
    # 9 Nov 2026, track 29 from the Multiroom server: a plain 44-byte header, 24-bit PCM at 96 kHz.
    head = b"RIFF\xa4\x8b9\x06WAVEfmt \x10\x00\x00\x00\x01\x00\x02\x00\x00w\x01\x00\x00\xca\x08\x00\x06\x00\x18\x00" \
           b"data" + struct.pack("<I", 104434560)
    f = fetch.parse_header(head)
    assert (f.rate, f.channels, f.bits, f.is_float, f.data_offset) == (96000, 2, 24, False, 44)
    assert f.frames == 104434560 // 6


def test_extensible_and_float_headers():
    f = fetch.parse_header(Track(rate=192000, bits=24, extensible=True).header())
    assert (f.rate, f.bits, f.is_float) == (192000, 24, False)
    f = fetch.parse_header(Track(rate=48000, bits=32).header())
    assert (f.rate, f.bits, f.is_float) == (48000, 32, True)


def test_what_isnt_a_wav_is_refused():
    with pytest.raises(ValueError):
        fetch.parse_header(b"ID3\x04" + b"\x00" * 60)
    with pytest.raises(ValueError):
        fetch.parse_header(Track().header()[:30])


def test_24_bit_samples_keep_their_sign():
    f = fetch.Format(44100, 1, 24, False, 44, 0)
    raw = bytes([0xFF, 0xFF, 0x7F, 0x00, 0x00, 0x80, 0xFF, 0xFF, 0xFF])
    assert fetch.to_float(raw, f)[:, 0].tolist() == pytest.approx([8388607 / 8388608, -1.0, -1 / 8388608])


# --- finding the server ---------------------------------------------------------------------------

def test_the_server_is_found_by_name(server):
    with FakeDLNA(name="JRiver Media Center") as other:
        dead = "http://127.0.0.1:9/description.xml"
        assert fetch.find_server("multiroom", locations=[dead, other.location, server.location]) == server.base
        assert fetch.find_server("Kitchen", locations=[other.location, server.location]) is None


def test_the_home_network_address_comes_before_a_vpns():
    # 9 Nov 2026: on the media PC the Multiroom server answered first on a VPN's 100.64 address.
    found = ["http://100.64.100.6:52101/DeviceDescription.xml", "http://8.8.8.8:52101/d.xml",
             "http://127.0.0.1:52101/d.xml", "http://192.168.0.133:52101/DeviceDescription.xml"]
    assert sorted(found, key=fetch._home_first)[:2] == [found[3], found[2]]


# --- streaming --------------------------------------------------------------------------------------

@pytest.mark.parametrize("rate,bits", [(44100, 24), (192000, 24), (48000, 16), (96000, 32)])
def test_every_sample_arrives_in_its_place(server, rate, bits):
    server.add(7, rate=rate, seconds=3, bits=bits)
    s = fetch.TrackStream(fetch.track_url(server.base, 7))
    try:
        assert (s.fmt.rate, s.fmt.bits) == (rate, bits)
        check(read_all(s, rate, 441), 0, bits)
        assert s.position >= rate
    finally:
        s.close()


def test_a_stream_starts_from_any_sample(server):
    t = server.add(8, rate=44100, seconds=5, bits=24)
    s = fetch.TrackStream(fetch.track_url(server.base, 8), from_sample=123457)
    try:
        check(read_all(s, 4410, 441), 123457, 24)
        assert server.ranges[-1][1] == len(t.header()) + 123457 * 6, "the range didn't start at the sample"
    finally:
        s.close()


def test_seek_drops_the_buffer_and_reads_from_there(server):
    server.add(9, rate=96000, seconds=5, bits=24)
    s = fetch.TrackStream(fetch.track_url(server.base, 9))
    try:
        read_all(s, 9600, 960)
        s.seek(300001)
        assert s.position == 300001
        check(read_all(s, 9600, 960), 300001, 24)
    finally:
        s.close()


def test_it_reads_no_further_ahead_than_asked(server):
    server.add(10, rate=44100, seconds=20, bits=24)
    s = fetch.TrackStream(fetch.track_url(server.base, 10), ahead=1.0)
    try:
        s.wait_buffered(44100)
        time.sleep(0.3)
        assert 1.0 <= s.seconds_ahead < 1.0 + fetch.CHUNK / 6 / 44100 + 0.01
    finally:
        s.close()


def test_the_end_of_a_track(server):
    server.add(11, rate=44100, seconds=1, bits=24)
    s = fetch.TrackStream(fetch.track_url(server.base, 11), from_sample=44100 - 300)
    try:
        assert s.wait_buffered(300)
        time.sleep(0.1)
        block, got = s.read(441)
        assert got == 300
        check(block[:300], 44100 - 300, 24)
        assert not block[300:].any()
        assert s.done and s.short_reads == 0
    finally:
        s.close()


def test_a_stall_plays_silence_and_leaves_the_stream_in_place(server):
    # Rule 7: an empty buffer gives silence; when the data comes the stream carries on where the clock says it is,
    # not where the data stopped, so the Speakers don't fall behind the Sonos.
    t = server.add(12, rate=44100, seconds=4, bits=24)
    server.stall_at = ("12", len(t.header()) + 20000 * 6, 0.4)
    s = fetch.TrackStream(fetch.track_url(server.base, 12))
    try:
        s.wait_buffered(15000)
        silent = 0
        end = time.perf_counter() + 3.0
        while time.perf_counter() < end and s.position < 150000:
            first = s.position
            block, got = s.read(2205)
            if got == 2205:
                check(block, first, 24)
            elif not got:
                silent += 1
            time.sleep(0.005)   # several times real time, so the stall runs the buffer dry
        assert silent and s.short_reads
        assert s.position >= 150000, "the stall never ended"
        first = s.position
        assert s.wait_buffered(s.owed + 441), "what the stall owes never arrived"
        block, got = s.read(441)
        assert got == 441
        check(block, first, 24)
    finally:
        s.close()
