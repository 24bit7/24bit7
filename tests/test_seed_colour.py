"""
Seed on Playing Now has a colour of its own: teal, or a leaf green on the dark theme when its accent
is itself near teal (Ben, 2 Nov 2026). Before this the teal was fixed, so a teal accent made Playing
Now invisible as a signal. The light theme's colours are fixed, so it stays teal.
"""


def test_the_seed_colour_is_teal_unless_the_dark_accent_is_near_teal(app):
    import tabs
    assert tabs.seed_colour("light") == tabs.SEED_TEAL["light"] == "#0e7490", "the light theme: teal, always"
    assert tabs.seed_colour("light", "#0e7490") == tabs.SEED_TEAL["light"], "it has no accent of its own"
    assert tabs.seed_colour("dark") == tabs.SEED_TEAL["dark"] == "#22d3ee", "the default green accent: teal"
    assert tabs.seed_colour("dark", "#4ade80") == tabs.SEED_TEAL["dark"], "Ben's green: teal"
    assert tabs.seed_colour("dark", "#22d3ee") == tabs.SEED_GREEN["dark"] == "#4ade80", "a teal accent: leaf green"
    assert tabs.seed_colour("dark", "#00bcd4") == tabs.SEED_GREEN["dark"], "cyan too"
    assert tabs.seed_colour("dark", "#3b82f6") == tabs.SEED_TEAL["dark"], "a blue accent is far enough: teal"
    assert tabs.seed_colour("dark", "#808080") == tabs.SEED_TEAL["dark"], "a grey accent: teal"
    assert tabs.seed_colour("dark", "#e8891c") == tabs.SEED_TEAL["dark"], "orange: teal"
    import colorsys
    for accent in ("#22d3ee", "#4ade80", "#3b82f6"):
        seed = tabs.seed_colour("dark", accent)
        gap = tabs._hue_gap(colorsys.rgb_to_hls(*tabs._hex_rgb(accent))[0] * 360,
                            colorsys.rgb_to_hls(*tabs._hex_rgb(seed))[0] * 360)
        assert gap > tabs.SEED_GAP, (accent, seed, gap, "the Seed colour always sits clear of the accent")
