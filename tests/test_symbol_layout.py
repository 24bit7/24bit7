"""The infinity sign on the Non-stop button sits level with its value, not with the button."""

import tabs


def test_symbol_is_centred_on_the_values_visual_middle():
    val_font, sym_font = tabs._pil_font(12), tabs._pil_font(19)
    (sx, sy), (vx, vy) = tabs.symbol_layout(90, 24, "∞", "Off", sym_font, val_font)
    s_top, s_bottom = sym_font.getbbox("∞")[1], sym_font.getbbox("∞")[3]
    x_top, x_bottom = val_font.getbbox("x")[1], val_font.getbbox("x")[3]
    symbol_middle = sy + (s_top + s_bottom) / 2
    value_middle = vy + (x_top + x_bottom) / 2
    assert abs(symbol_middle - value_middle) <= 1, (symbol_middle, value_middle)
    assert sx < vx, "the symbol comes first"
