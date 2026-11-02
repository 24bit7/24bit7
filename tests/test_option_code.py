"""
A dropdown's label maps back to its saved value in any language (2 Nov 2026). The Mix section's Combine
box shows t("Alternate"), so in German option_code saw "Abwechseln", matched nothing, fell back to the
first option (Shuffle), hid the Pattern row and saved the wrong combine on any change.
"""



def test_a_translated_label_maps_to_its_code(app):
    import i18n   # after the fixture's fresh import, so it's the i18n settings_gui uses
    import buttons
    import settings_gui
    try:
        i18n.set_language("de")
        assert i18n.t("Alternate") == "Abwechseln", "the German the box shows"
        assert settings_gui.option_code(buttons.COMBINES, "Abwechseln") == "alternate"
        assert settings_gui.option_code(buttons.COMBINES, "Alternate") == "alternate", "the English still works"
        assert settings_gui.option_code(buttons.COMBINES, "nonsense") == "shuffle", "unknown: the first option"
    finally:
        i18n.set_language("en")
