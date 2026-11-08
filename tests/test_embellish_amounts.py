"""
Play & Embellish's amounts (Ben, 7 Nov 2026): +10%, +20%, +50%, Double, Triple and Build It Out, which of them
the arrow offers and which the button runs set under Settings > JRiver Playlists. All six and +50% to start;
an older choice (Add Half, Double It) carries over as the default.
"""


def test_how_many_each_amount_asks_for():
    import embellish
    asks = {a: embellish.want_for(a, 40) for a in embellish.AMOUNTS}
    assert asks == {"p10": 4, "p20": 8, "p50": 20, "double": 40, "triple": 80, "out": None}
    assert embellish.want_for("p10", 3) == 1, "always at least one"
    assert embellish.want_for("half", 40) == 20, "Add Half, from before, is +50%"


def test_all_six_and_fifty_per_cent_to_start(app):
    import embellish
    assert embellish.amounts() == {"shown": list(embellish.AMOUNTS), "default": "p50"}
    assert [embellish.AMOUNT_NAMES[a] for a in embellish.AMOUNTS] == \
        ["+10%", "+20%", "+50%", "Double", "Triple", "Build It Out"]
    assert not hasattr(embellish, "AMOUNT_NOTES"), "no notes under the menu's rows"


def test_an_older_choice_carries_over(app):
    import embellish
    embellish._set_meta(embellish.CHOICE_KEY, {"order": "ordered", "amount": "out"})
    assert embellish.amounts()["default"] == "out"
    embellish._set_meta(embellish.CHOICE_KEY, {"amount": "half"})
    assert embellish.amounts()["default"] == "p50"


def test_at_least_one_shown_and_the_default_is_one_of_them(app):
    import embellish
    assert embellish.set_amounts(shown=["p20", "double", "out"], default="double") == \
        {"shown": ["p20", "double", "out"], "default": "double"}
    assert embellish.set_amounts(shown=["out", "p20"]) == {"shown": ["p20", "out"], "default": "p20"}, \
        "the default unticked: the first still ticked takes over, in the menu's order"
    assert embellish.set_amounts(shown=[])["shown"] == ["p20"], "never none"
    assert embellish.set_amounts(default="triple")["default"] == "p20", "only a shown amount can be the default"
    assert embellish.choices()["amount"] == "p20", "the button runs the default"


def test_the_console_names_the_amount(app):
    import embellish
    r = app.Lines()
    embellish.embellish({"ID": "202", "Name": "Road Trip"}, "ordered", "p20", r)
    assert r.has("tracks by") and r.has(", +20%."), r.text()
