"""
Multiroom, the JRiver calls (9 Nov 2026): the leader zone's track and next track, stopping the follower zone, the
follower zone's device, and the settings read from .env. Against the fake JRiver.
"""

import os
import sys

import pytest

import fakes

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
try:
    from multiroom import mcws
finally:
    sys.path.remove(REPO)


@pytest.fixture
def jr(monkeypatch):
    jriver = fakes.FakeJRiver()
    fakes.install(monkeypatch, jriver, fakes.FakeWeb(jriver))
    j = mcws.JRiver(host=fakes.JRIVER_HOST, user="", password="", env=None)
    j.fake = jriver
    return j


def test_the_leader_zones_track_and_the_next(jr):
    keys = [r["Key"] for r in jr.fake.tracks[:3]]
    jr.fake.play("Sonos", keys)
    jr.fake.zone("Sonos").position_ms = 61234
    i = jr.info("Sonos")
    assert (i["state"], i["key"], i["next_key"], i["position_ms"]) == (mcws.PLAYING, int(keys[0]), int(keys[1]), 61234)
    assert jr.fake.calls_to("Playback/Info")[-1]["Zone"] == "10003"
    jr.fake.play("Sonos", keys, pos=2)
    assert jr.info("Sonos")["next_key"] is None


def test_a_stopped_zone_has_no_track(jr):
    i = jr.info("Kitchen")
    assert (i["state"], i["key"], i["next_key"]) == (mcws.STOPPED, None, None)


def test_zones_are_found_by_name_or_id_and_hidden_ones_are_asked_for(jr):
    assert jr.zone_id("sonos") == "10003"
    assert jr.zone_id("10001") == "10001"
    assert jr.fake.calls_to("Playback/Zones")[0].get("Hidden") == 1
    with pytest.raises(KeyError):
        jr.zone_id("Garage")


def test_a_zone_added_since_is_found_on_a_second_look(jr):
    jr.zones()
    from fakes import Zone
    jr.fake.zones["10016"] = Zone("10016", "Multiroom")
    jr.fake.zone_order.append("10016")
    assert jr.zone_id("Multiroom") == "10016"


def test_stopping_the_follower_zone_leaves_the_leader_playing(jr):
    keys = [r["Key"] for r in jr.fake.tracks[:2]]
    jr.fake.play("Sonos", keys)
    jr.fake.play("Speakers", keys)
    jr.stop("Speakers")
    assert jr.fake.zone("Speakers").state == 0 and jr.fake.zone("Sonos").state == 2


def test_the_follower_zones_device(jr):
    jr.fake.zone("Speakers").device = ("Hugo (Chord Async USB 44.1kHz-384kHz)", "WASAPI")
    assert jr.device("Speakers") == ("Hugo (Chord Async USB 44.1kHz-384kHz)", "WASAPI")


def test_settings_come_from_env_and_the_password_never_shows(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("JRIVER_HOST=192.168.0.133:52199\nJRIVER_USER=ben\nJRIVER_PASS=s3cret\nLASTFM_API_KEY=x\n",
                   encoding="utf-8")
    assert mcws.read_env(env) == {"JRIVER_HOST": "192.168.0.133:52199", "JRIVER_USER": "ben", "JRIVER_PASS": "s3cret"}
    j = mcws.JRiver(env=env)
    assert j.base == "http://192.168.0.133:52199/MCWS/v1" and j.auth == ("ben", "s3cret")
    assert "s3cret" not in repr(j)
    monkeypatch.delenv("JRIVER_USER", raising=False)
    assert mcws.JRiver(env=tmp_path / "missing.env", host="h:1").auth is None   # no user: no login sent
