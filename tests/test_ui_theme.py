"""Theme data integrity."""

import dataclasses

import pytest

from bloc.ui.theme import FOG, HUD, THEMES, VOID, Glyphs, get_theme


def test_all_three_environments_present():
    assert set(THEMES) == {"hud", "void", "fog"}


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda t: t.name)
def test_every_glyph_is_defined(theme):
    """A missing glyph must be impossible, not silently empty as in v0.1."""
    for f in dataclasses.fields(Glyphs):
        assert getattr(theme.glyphs, f.name) is not None


@pytest.mark.parametrize("theme", THEMES.values(), ids=lambda t: t.name)
def test_eight_aircraft_headings(theme):
    assert len(theme.glyphs.aircraft) == 8


def test_unknown_theme_falls_back_to_hud():
    assert get_theme("nonsense") is HUD
    assert get_theme(None) is HUD
    assert get_theme("") is HUD


def test_theme_lookup_is_case_insensitive():
    assert get_theme("VOID") is VOID


def test_fog_theme_contains_no_symbols():
    """
    FOG is documented as 'pure plain text, no symbols'. In v0.1 selecting it
    still rendered aviation glyphs, because `◈` was hardcoded 128 times across
    the UI rather than resolved through the theme. This pins the data half of
    that contract; the ports enforce the other half by construction.
    """
    aviation = "◈▶▢▣●○△⊕▲▼◀█░▓◉─═·"
    for f in dataclasses.fields(Glyphs):
        value = getattr(FOG.glyphs, f.name)
        text = "".join(value) if isinstance(value, tuple) else value
        assert not (set(text) & set(aviation)), f"FOG.{f.name} contains a symbol: {text!r}"


def test_themes_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        HUD.glyphs.bullet = "x"
