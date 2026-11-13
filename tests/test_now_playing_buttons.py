"""
The Now Playing row's Stop, Clear Playing Now and Skip Track, and Zone's Multiroom entry (stage two, 2c, 9 Nov
2026; mock-up mockups/now_playing_buttons.html). Stop, amber, stops the row's zone; once it's stopped the same
button reads Clear Playing Now in red and empties the list, no confirmation; Skip Track plays the next track and
counts as a skip. Zone gains Multiroom while it's enabled, reading the leader, and is picked by itself when the
Speakers start following. Opens the real window.
"""

from test_gui import ui  # noqa: F401  (the GUI fixture)


class FakeLink:
    def __init__(self):
        self.wanted = False

    def start(self, settings):
        self.wanted = True

    def stop(self):
        self.wanted = False

    def leave(self):
        self.wanted = False

    def running(self):
        return self.wanted


def now_playing(ui):
    ui.play._update_now_playing()
    ui.pump(until=lambda: not getattr(ui.play, "_np_busy", False), timeout=10)
    ui.pump(0.2)


def track_text(ui):
    return ui.play.np_track.get("1.0", "end-1c")


def settled(ui):
    """The greeting holds console lines while it types: wait for it, so the lines can be read."""
    ui.pump(until=lambda: not ui.play._greeting_active, timeout=20)


def test_stop_becomes_clear_playing_now_and_skip_plays_the_next_track(app, ui):
    j = app.jriver
    keys = [j.key_of("The Beatles", "Something"), j.key_of("The Beatles", "Here Comes The Sun"),
            j.key_of("Queen", "Bohemian Rhapsody")]
    j.play("Speakers", keys)
    play = ui.play
    settled(ui)
    play.zone_var.set("Speakers")
    play._on_zone_changed()
    now_playing(ui)
    assert play.stop_button.winfo_ismapped() and play.skip_button.winfo_ismapped(), "the buttons aren't on the row"
    assert play.stop_button.winfo_rootx() > play.np_track.winfo_rootx(), "the buttons sit after the track text"
    assert play.stop_button.winfo_rootx() + play.stop_button.winfo_width() < play.output_box.winfo_rootx(), \
        f"Stop runs under Output ({play.stop_button.winfo_rootx()}+{play.stop_button.winfo_width()} vs {play.output_box.winfo_rootx()})"
    assert play.stop_button._label.cget("text") == "Stop" and play.stop_button._armed == ui.gui.PALETTE["amber"]
    assert play.stop_button._state == "normal" and play.skip_button._state == "normal"

    play._skip_clicked()
    ui.pump(until=lambda: j.zone("Speakers").pos == 1, timeout=10)
    now_playing(ui)
    assert j.zone("Speakers").pos == 1
    assert any("Skipped to the next track in Speakers." in line for line in console_lines(ui))
    assert app.jriver.fields_made, "the skip wasn't counted (24bit7 Voice Skips)"

    play._stop_clicked()
    ui.pump(until=lambda: j.zone("Speakers").state == 0, timeout=10)
    now_playing(ui)
    assert play.stop_button._label.cget("text") == "Clear Playing Now"
    assert play.stop_button._armed == ui.gui.PALETTE["red"] and play.stop_button._state == "normal"
    assert play.skip_button._state == "disabled", "nothing to skip while stopped"

    play._clear_clicked()   # one click, no confirmation (Ben, 9 Nov 2026)
    ui.pump(until=lambda: j.zone("Speakers").playlist == [], timeout=10)
    now_playing(ui)
    assert j.zone("Speakers").playlist == [] and not ui.answers, "a confirmation box appeared"
    assert play.stop_button._label.cget("text") == "Clear Playing Now" and play.stop_button._state == "disabled"
    assert any("Cleared Playing Now in Speakers." in line for line in console_lines(ui))
    assert not ui.errors, ui.errors[0]


def test_zone_gains_multiroom_which_reads_the_leader_and_is_picked_when_the_speakers_follow(app, ui):
    play = ui.play
    play.multiroom = FakeLink()
    settled(ui)
    play._fill_zone_list()
    assert "Multiroom" not in play.zone_cb.cget("values")
    app.set_env(MULTIROOM_ENABLED="1", MULTIROOM_LEADER="Sonos", MULTIROOM_FOLLOWER="Speakers")
    play._fill_zone_list()
    assert list(play.zone_cb.cget("values"))[-1] == "Multiroom"
    j = app.jriver
    j.play("Sonos", [j.key_of("Queen", "Bohemian Rhapsody")])
    play.zone_var.set("Speakers")
    play._on_zone_changed()
    now_playing(ui)
    play._multiroom_state("following")   # the follower's child says the Speakers are following
    ui.pump(0.3)
    assert play.zone_var.get() == "Multiroom" and app.engine.SEED_ZONE_NAME == "Sonos"
    now_playing(ui)
    assert "Bohemian Rhapsody" in track_text(ui), "the row shows the leader's track"
    play._multiroom_state("idle")
    assert play.zone_var.get() == "Multiroom", "only following switches the zone; idle leaves it"
    assert not ui.errors, ui.errors[0]


def console_lines(ui):
    return ui.play.log.get("1.0", "end-1c").splitlines()


def test_stop_turns_into_clear_playing_now_while_jriver_is_still_fading_out(app, ui):
    """Ben, 13 Nov 2026: Stop stayed Stop after one click, since JRiver still said playing when 24bit7 asked straight
    away and the next read was ten seconds off, so he clicked Stop again. Now the zone is asked until it's stopped."""
    j = app.jriver
    j.play("Speakers", [j.key_of("The Beatles", "Something"), j.key_of("Queen", "Bohemian Rhapsody")])
    play = ui.play
    settled(ui)
    play.zone_var.set("Speakers")
    play._on_zone_changed()
    now_playing(ui)
    assert play.stop_button._label.cget("text") == "Stop"
    j.stop_reads = 3   # three more reads say playing, as JRiver does while it fades out
    play._stop_clicked()
    ui.pump(until=lambda: play.stop_button._label.cget("text") == "Clear Playing Now", timeout=6)
    assert play.stop_button._label.cget("text") == "Clear Playing Now", "Stop needed a second click"
    assert play.stop_button._armed == ui.gui.PALETTE["red"]
    assert not ui.errors, ui.errors[0]
