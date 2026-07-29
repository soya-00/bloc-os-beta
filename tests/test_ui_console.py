"""
Colour depth and the writer.

The load-bearing test here is `TestFog`: every FOG role is `None`, so the writer
must emit no escape at all. That is what makes FOG genuinely the plain-text
theme rather than "the default colour, explicitly set" — and it is the strongest
check that meaning never lives in colour alone, since FOG has none.
"""

import io

import pytest

from bloc.ui.console import COLOR256, MONO, TRUECOLOR, Console, detect_depth, to_ansi
from bloc.ui.theme import FOG, HUD, VOID, contrast, luminance


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class TestDetectDepth:
    def test_truecolor_from_colorterm(self):
        assert detect_depth(FakeTTY(), {"COLORTERM": "truecolor"}) == TRUECOLOR
        assert detect_depth(FakeTTY(), {"COLORTERM": "24bit"}) == TRUECOLOR

    def test_256_from_term(self):
        assert detect_depth(FakeTTY(), {"TERM": "xterm-256color"}) == COLOR256

    def test_no_color_wins_over_everything(self):
        """A real convention, and it costs one line to honour."""
        env = {"COLORTERM": "truecolor", "TERM": "xterm-256color", "NO_COLOR": "1"}
        assert detect_depth(FakeTTY(), env) == MONO

    def test_a_pipe_gets_no_colour(self):
        assert detect_depth(io.StringIO(), {"COLORTERM": "truecolor"}) == MONO

    def test_dumb_terminal(self):
        assert detect_depth(FakeTTY(), {"TERM": "dumb"}) == MONO

    def test_unknown_terminal_assumes_256(self):
        """The Pi console over KMS reports plain `linux` and does have colour."""
        assert detect_depth(FakeTTY(), {"TERM": "linux"}) == COLOR256


class TestToAnsi:
    def test_truecolor_is_exact(self):
        assert to_ansi((0, 255, 65), TRUECOLOR) == "\033[38;2;0;255;65m"

    def test_background_layer(self):
        assert to_ansi((9, 19, 14), TRUECOLOR, background=True) == "\033[48;2;9;19;14m"

    def test_256_falls_into_the_cube(self):
        out = to_ansi((255, 176, 0), COLOR256)
        assert out.startswith("\033[38;5;")
        assert 16 <= int(out.split(";")[-1].rstrip("m")) <= 231

    def test_greys_use_the_grey_ramp(self):
        """The 24-step ramp is far finer than the cube for neutral colours."""
        out = to_ansi((132, 132, 132), COLOR256)
        assert 232 <= int(out.split(";")[-1].rstrip("m")) <= 255

    def test_mono_emits_nothing(self):
        assert to_ansi((0, 255, 65), MONO) == ""

    def test_none_emits_nothing_at_any_depth(self):
        for depth in (TRUECOLOR, COLOR256, MONO):
            assert to_ansi(None, depth) == ""


class TestWidth:
    def test_explicit_override_wins(self):
        assert Console(HUD, io.StringIO(), width=228).width == 228

    def test_falls_back_when_there_is_no_terminal(self):
        assert Console(HUD, io.StringIO()).width == 80

    def test_rule_fills_the_width(self):
        s = io.StringIO()
        Console(HUD, s, width=100, depth=MONO).rule()
        assert len(s.getvalue().strip("\n")) == 100


class TestWrite:
    def test_text_reaches_the_stream(self):
        s = io.StringIO()
        Console(HUD, s, depth=MONO).write("hello")
        assert s.getvalue() == "hello\n"

    def test_colour_wraps_and_resets(self):
        s = io.StringIO()
        Console(HUD, s, depth=TRUECOLOR).write("hello")
        out = s.getvalue()
        assert out.startswith("\033[38;2;")
        assert out.endswith("\033[0m\n")

    def test_cell_sets_a_background(self):
        s = io.StringIO()
        Console(HUD, s, depth=TRUECOLOR).cell("BLK-041", "pressure", "surface")
        assert "\033[48;2;" in s.getvalue()

    def test_an_unknown_role_falls_back_rather_than_raising(self):
        s = io.StringIO()
        Console(HUD, s, depth=TRUECOLOR).write("x", "nonsense")
        assert "\033[38;2;0;255;65m" in s.getvalue()

    @pytest.mark.parametrize(
        "method", ["primary", "secondary", "dim", "faint", "active",
                   "pressure", "queued", "attention", "critical", "fixed"]
    )
    def test_every_role_has_a_shortcut(self, method):
        s = io.StringIO()
        getattr(Console(HUD, s, depth=MONO), method)("x")
        assert s.getvalue() == "x\n"


class TestHierarchyIsVisible:
    def test_primary_and_secondary_differ(self):
        """
        v0.1 set these to the same green, so the hierarchy every screen assumed
        did not exist on screen. This is the assertion that keeps it fixed.
        """
        for theme in (HUD, VOID):
            assert theme.palette.primary != theme.palette.secondary

    def test_the_text_ramp_descends(self):
        """
        primary brighter than secondary brighter than dim brighter than faint.

        Measured as relative luminance, not as the mean of the channels — the
        eye is ~7x more sensitive to green than to blue, so HUD's `(0, 255, 65)`
        reads brighter than `(124, 194, 158)` despite summing lower. Averaging
        the channels says the opposite and would condemn a correct palette.
        """
        for theme in (HUD, VOID):
            ramp = [theme.palette.primary, theme.palette.secondary,
                    theme.palette.dim, theme.palette.faint]
            levels = [luminance(c) for c in ramp]
            assert levels == sorted(levels, reverse=True), theme.name

    @pytest.mark.parametrize(
        ("role", "floor"),
        [("primary", 7.0), ("secondary", 7.0), ("fixed", 7.0), ("dim", 4.5), ("faint", 3.0)],
    )
    def test_text_is_legible_against_the_background(self, role, floor):
        """
        WCAG contrast against the surface it sits on. 4.5 is the body-text
        threshold; `faint` sits at 3.0 — the AA floor for large text and UI
        components — because it marks work that is finished and should recede,
        but "recede" cannot mean "unreadable on a sunlit panel".
        """
        for theme in (HUD, VOID):
            ratio = contrast(getattr(theme.palette, role), theme.palette.background)
            assert ratio >= floor, f"{theme.name}.{role} is {ratio:.1f}:1, want {floor}"

    @pytest.mark.parametrize("role", ["active", "pressure", "queued", "attention", "critical"])
    def test_state_colours_are_legible_on_a_strip(self, role):
        """A strip cell sits on `surface`, not on `background`."""
        for theme in (HUD, VOID):
            ratio = contrast(getattr(theme.palette, role), theme.palette.surface)
            assert ratio >= 4.5, f"{theme.name}.{role} is {ratio:.1f}:1 on surface"

    def test_state_colours_are_distinct(self):
        states = [HUD.palette.active, HUD.palette.pressure, HUD.palette.queued,
                  HUD.palette.attention, HUD.palette.critical]
        assert len(set(states)) == len(states)

    def test_void_separates_state_by_brightness(self):
        """
        VOID is the colour-blind-safe theme: it must not rely on hue, so every
        state colour is a neutral grey.
        """
        for name in ("active", "pressure", "queued", "attention", "critical", "fixed"):
            r, g, b = getattr(VOID.palette, name)
            assert r == g == b, f"VOID.{name} is not neutral"


class TestFog:
    def test_every_role_is_uncoloured(self):
        for name in ("primary", "secondary", "dim", "faint", "active", "pressure",
                     "queued", "attention", "critical", "fixed", "background",
                     "surface", "surface_dead", "rule", "rule_dead"):
            assert getattr(FOG.palette, name) is None, name

    def test_fog_output_contains_no_escape_at_all(self):
        """Not even a reset — the point is that nothing is emitted."""
        s = io.StringIO()
        c = Console(FOG, s, depth=TRUECOLOR)
        c.write("OBJECTIVES")
        c.cell("BLK-041", "pressure")
        c.rule()
        assert "\033" not in s.getvalue()

    def test_fog_still_writes_the_words(self):
        s = io.StringIO()
        Console(FOG, s, depth=TRUECOLOR).write("OBJECTIVES")
        assert "OBJECTIVES" in s.getvalue()
