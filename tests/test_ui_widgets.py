"""Layout primitives — all pure, so all directly testable."""

import pytest

from bloc.ui.theme import FOG, HUD, THEMES, VOID
from bloc.ui.widgets import bar, compass, field, leader, separator, sparkline

G = HUD.glyphs


class TestLeader:
    def test_value_ends_at_the_column(self):
        assert len(leader("VAULT", "[ OK ]", G, width=40)) == 40

    def test_fill_sits_between_label_and_value(self):
        out = leader("VAULT", "[ OK ]", G, width=40)
        assert out.startswith("VAULT ·")
        assert out.endswith("· [ OK ]")

    def test_label_only_fills_to_width(self):
        assert len(leader("SYSTEMS", glyphs=G, width=30)) == 30

    def test_overlong_label_is_never_truncated(self):
        """A ragged edge is better than a silently cut task title."""
        label = "X" * 60
        out = leader(label, "[ OK ]", G, width=40)
        assert label in out
        assert "[ OK ]" in out

    @pytest.mark.parametrize("theme", THEMES.values(), ids=lambda t: t.name)
    def test_fill_comes_from_the_theme(self, theme):
        """
        A hardcoded fill here would reintroduce the v0.1 bug at one remove:
        FOG would still draw leaders out of symbols.
        """
        out = leader("A", "B", theme.glyphs, width=20)
        assert theme.glyphs.leader_fill in out
        assert len(out) == 20

    def test_fog_leader_is_whitespace_only(self):
        out = leader("VAULT", "[ OK ]", FOG.glyphs, width=40)
        assert set(out) <= set("VAULT[ OK]")


class TestBar:
    def test_empty_and_full(self):
        assert bar(0.0, 8, G) == G.bar_empty * 8
        assert bar(1.0, 8, G) == G.bar_full * 8

    def test_half(self):
        assert bar(0.5, 8, G) == G.bar_full * 4 + G.bar_empty * 4

    @pytest.mark.parametrize("fraction", [-5.0, -0.1, 1.1, 99.0])
    def test_width_is_stable_under_out_of_range_input(self, fraction):
        """An overrunning timer must not emit a bar wider than its field."""
        assert len(bar(fraction, 10, G)) == 10

    def test_uses_the_active_theme_glyphs(self):
        assert bar(1.0, 3, VOID.glyphs) == "###"


class TestSparkline:
    def test_nothing_outstanding_reads_empty_not_full(self):
        """The v0.1 header showed 100% regardless of actual state."""
        assert sparkline(0, 0, 8, G) == G.bar_empty * 8

    def test_partial_progress(self):
        assert sparkline(1, 4, 8, G) == G.bar_full * 2 + G.bar_empty * 6

    def test_all_done(self):
        assert sparkline(5, 5, 8, G) == G.bar_full * 8

    def test_negative_total_is_treated_as_empty(self):
        assert sparkline(3, -1, 4, G) == G.bar_empty * 4


class TestSeparator:
    @pytest.mark.parametrize("style", ["single", "double", "dot", "unknown"])
    def test_every_style_returns_a_rule(self, style):
        assert len(separator(G, style)) == 40

    def test_styles_are_distinct(self):
        assert separator(G, "single") != separator(G, "double")

    def test_unknown_style_falls_back_to_single(self):
        assert separator(G, "unknown") == separator(G, "single")


def test_field():
    assert field("BAT", "84%") == "BAT [84%]"


class TestCompass:
    @pytest.mark.parametrize(
        ("bearing", "expected_index"),
        [(0, 0), (45, 1), (90, 2), (180, 4), (270, 6), (359, 0), (360, 0), (720, 0)],
    )
    def test_bearing_maps_to_heading_glyph(self, bearing, expected_index):
        assert compass(bearing, G) == G.aircraft[expected_index]

    def test_negative_bearing_wraps(self):
        assert compass(-90, G) == G.aircraft[6]
