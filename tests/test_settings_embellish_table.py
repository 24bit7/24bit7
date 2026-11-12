"""
Settings > Playlists & Albums > Embellish (JRiver Playlists > Play & Embellish until 12 Nov 2026) as a table (Ben, 10 Nov 2026): a tick, "Use the same settings for
every amount", on to start; an All amounts line; and a line per amount with In the Menu, Default, Shuffle, Deep
Cuts (how, and by what share) and the Moderator. While the tick is on the amounts' own settings are greyed and
show the All amounts line; off, each is live and a copy of that line until it's changed. Before this the section
held the menu ticks and the default alone, and the settings stage one added had no screen.
"""

from tkinter import ttk

from test_gui import ui  # noqa: F401  (the GUI fixture)
from test_settings_buttons import labels, page_named, walk


def table(ui):
    page_named(ui, "Playlists & Albums")
    ui.pump(0.8)
    s = ui.settings
    return s, s._embellish_lines


def off(widget):
    return "disabled" in widget.state() if isinstance(widget, ttk.Widget) else str(widget.cget("state")) == "disabled"


def greyed(line):
    return off(line["shuffle_box"]) and off(line["deep_box"]) and off(line["mod_box"]) and off(line["share_box"]) and off(line["nonstop_box"])


def pick(ui, line, name, value):
    """A dropdown's choice, made as a click on its list would."""
    line[name].set(value)
    line["deep_box" if name == "deep_cuts" else "mod_box"].event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)


def the_tick(line):
    box = line["shuffle_box"].master
    return next(w for w in walk(box) if isinstance(w, ttk.Checkbutton)
                and str(w.cget("text")) == "Use the same settings for every amount")


def test_one_line_serves_every_amount_to_start_and_the_rest_are_greyed(app, ui):
    import embellish
    s, lines = table(ui)
    assert list(lines) == [None] + list(embellish.AMOUNTS)
    box = lines[None]["shuffle_box"].master
    for text in ("Use the same settings for every amount", "All amounts", "In the Menu", "Default", "Shuffle",
                 "Deep Cuts", "Moderator", "+10%", "Build It Out"):
        assert text in labels(box), text
    assert s._embellish_one.get()
    every = lines[None]
    assert not off(every["shuffle_box"]) and not off(every["deep_box"]) and not off(every["mod_box"])
    assert off(every["share_box"]), "Deep Cuts is off, so there's no share to set"
    assert every["shuffle"].get() and every["deep_cuts"].get() == "Off" and every["moderator"].get() == "Off"
    for amount in embellish.AMOUNTS:
        assert greyed(lines[amount]) and lines[amount]["shuffle"].get(), amount

    pick(ui, every, "deep_cuts", "Spaced")
    assert embellish.settings()["all_row"]["deep_cuts"] == "spaced"
    assert str(every["share_box"].cget("state")) == "readonly", "now there is"
    every["share_box"].invoke("buttonup")
    ui.pump(0.2)
    assert embellish.settings()["all_row"]["deep_share"] == "20"
    every["shuffle_box"].invoke()
    pick(ui, every, "moderator", "Strict")
    assert embellish.row_for("triple") == {"shuffle": "0", "deep_cuts": "spaced", "deep_share": "20",
                                           "moderator": "strict", "nonstop": "no"}
    for amount in embellish.AMOUNTS:   # greyed, and showing the line they run
        line = lines[amount]
        assert greyed(line), amount
        assert (line["shuffle"].get(), line["deep_cuts"].get(), line["deep_share"].get(), line["moderator"].get()) \
            == (False, "Spaced", "20", "Strict"), amount
    assert embellish.settings()["rows"] == {}, "nothing was given a row of its own"
    assert not ui.errors, ui.errors[0]


def test_unticked_each_amount_has_its_own_line_a_copy_until_its_changed(app, ui):
    import embellish
    s, lines = table(ui)
    pick(ui, lines[None], "deep_cuts", "Shuffled")
    the_tick(lines[None]).invoke()
    ui.pump(0.2)
    assert embellish.settings()["all"] == "0" and not s._embellish_one.get()
    assert greyed(lines[None]) and off(lines[None]["title"]), "the one line rests while each amount has its own"
    for amount in embellish.AMOUNTS:
        line = lines[amount]
        assert not off(line["shuffle_box"]) and not off(line["deep_box"]) and not off(line["mod_box"]), amount
        assert line["deep_cuts"].get() == "Shuffled" and not off(line["share_box"]), "a copy of the one line"
    lines["triple"]["shuffle_box"].invoke()
    pick(ui, lines["triple"], "moderator", "Relaxed")
    pick(ui, lines["p10"], "deep_cuts", "Off")
    assert embellish.row_for("triple") == {"shuffle": "0", "deep_cuts": "shuffled", "deep_share": "10",
                                           "moderator": "relaxed", "nonstop": "no"}
    assert embellish.row_for("p10")["deep_cuts"] == "off" and off(lines["p10"]["share_box"])
    assert embellish.row_for("double") == embellish.settings()["all_row"], "the others still as the one line"
    assert lines["double"]["shuffle"].get() and lines["double"]["moderator"].get() == "Off"

    the_tick(lines[None]).invoke()   # ticked again: every line shows the one line, and the amounts' rows are kept
    ui.pump(0.2)
    assert greyed(lines["triple"]) and lines["triple"]["shuffle"].get() and lines["triple"]["moderator"].get() == "Off"
    assert not off(lines[None]["shuffle_box"]) and not off(lines[None]["title"])
    assert embellish.settings()["rows"]["triple"]["moderator"] == "relaxed"
    the_tick(lines[None]).invoke()
    ui.pump(0.2)
    assert lines["triple"]["moderator"].get() == "Relaxed" and not lines["triple"]["shuffle"].get()
    assert not ui.errors, ui.errors[0]


def test_the_menu_ticks_and_the_default_stay_live_whatever_the_tick_says(app, ui):
    import embellish
    s, lines = table(ui)
    box = lines[None]["shuffle_box"].master
    radios = [w for w in walk(box) if isinstance(w, ttk.Radiobutton)]
    shuffles = [line["shuffle_box"] for line in lines.values()]
    menu = [w for w in walk(box) if isinstance(w, ttk.Checkbutton) and not str(w.cget("text")) and w not in shuffles]
    assert len(radios) == 6 and len(menu) == 6
    assert not any(off(w) for w in radios + menu), "greyed is for how an amount builds, not whether it's offered"
    menu[0].invoke()   # +10% out of the menu, through the tick itself
    assert "p10" not in embellish.amounts()["shown"]
    menu[0].invoke()
    assert "p10" in embellish.amounts()["shown"]
    radios[4].invoke()
    assert embellish.amounts()["default"] == "triple"
    assert not ui.errors, ui.errors[0]


def test_the_moderator_rests_until_the_ai_is_set_up(app, ui):
    s, lines = table(ui)
    s._ai_set_up = lambda: False
    s._embellish_refresh()
    assert off(lines[None]["mod_box"]) and not off(lines[None]["deep_box"]), "only the Moderator needs the AI"
    del s._ai_set_up
    s._embellish_refresh()
    assert not off(lines[None]["mod_box"])
    assert not ui.errors, ui.errors[0]


def test_non_stop_is_a_column_of_its_own(app, ui):
    """12 Nov 2026: Non-stop beside Shuffle, Deep Cuts and the Moderator, greyed with the rest while the tick is on."""
    import embellish
    s, lines = table(ui)
    assert "Non-stop" in labels(s)
    assert greyed(lines["triple"]) and not off(lines[None]["nonstop_box"])
    the_tick(lines[None]).invoke()
    ui.pump(0.2)
    line = lines["triple"]
    assert not off(line["nonstop_box"])
    line["nonstop"].set("Similar tracks")
    line["nonstop_box"].event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert embellish.row_for("triple")["nonstop"] == "tracks"
    assert embellish.row_for("double")["nonstop"] == embellish.settings()["all_row"]["nonstop"]



def test_the_albums_rows_offer_their_hits_and_take_an_albums_default(app, ui):
    """Ben, 12 Nov 2026: With Their Hits and And Their Hits get rows of their own under Albums, with In the Menu,
    Default (an album's) and Non-stop; the amounts above serve albums too."""
    import embellish
    s, lines = table(ui)
    box = lines[None]["shuffle_box"].master
    for text in ("Embellish", "Albums", "With Their Hits", "And Their Hits"):
        assert text in labels(box) or text in labels(box.master.master), text
    ticks, radios, nonstop = s._album_rows
    assert ticks["with_hits"].get() and ticks["and_hits"].get()
    assert radios["with_hits"].instate(["selected"]), "With Their Hits is an album's default to start"
    radios["and_hits"].invoke()
    ui.pump(0.2)
    assert embellish.albums()["default"] == "and_hits" and embellish.amounts()["default"] == "p50", \
        "an album's default is its own"
    next(w for w in walk(box) if isinstance(w, ttk.Checkbutton) and str(w.cget("variable")) == str(ticks["and_hits"])).invoke()
    ui.pump(0.2)
    assert embellish.albums()["shown"] == ["with_hits"] and embellish.albums()["default"] == "with_hits"
    assert radios["and_hits"].instate(["disabled"])
    nonstop["with_hits"].set("Similar artists")
    next(w for w in walk(box) if isinstance(w, ttk.Combobox) and str(w.cget("textvariable")) == str(nonstop["with_hits"])
         ).event_generate("<<ComboboxSelected>>")
    ui.pump(0.2)
    assert embellish.albums()["rows"]["with_hits"]["nonstop"] == "artists"
    assert not ui.errors, ui.errors[0]
