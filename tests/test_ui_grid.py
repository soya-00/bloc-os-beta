"""
The layout grid.

Four columns exists because the traffic scope's four strip bays are 480 px
across 1920. If the terminal grid and the scope grid ever disagree, a strip in
the objectives list stops lining up with the same strip on the scope, and the
"one product" claim quietly becomes false.
"""

import pytest

from bloc.ui.widgets import (
    DEFAULT_WIDTH,
    GRID_COLS,
    MIN_GRID_WIDTH,
    Column,
    columns,
    pad,
    span,
    truncate,
)


class TestColumns:
    def test_four_by_default(self):
        assert len(columns(228)) == GRID_COLS

    def test_columns_do_not_overlap(self):
        cols = columns(228)
        for left, right in zip(cols, cols[1:], strict=False):
            assert left.end <= right.start

    def test_columns_are_equal_width(self):
        assert len({c.width for c in columns(228)}) == 1

    def test_stays_inside_the_terminal(self):
        for total in (120, 160, 200, 228, 300):
            assert columns(total)[-1].end <= total

    def test_respects_the_margin(self):
        assert columns(228, margin=2)[0].start == 2

    def test_collapses_below_the_minimum(self):
        """
        Four columns of nine characters is not a layout. An 80-column SSH window
        gets one column, which is the case that matters — the Pi is debugged
        remotely from week 11.
        """
        assert len(columns(80)) == 1
        assert len(columns(MIN_GRID_WIDTH - 1)) == 1

    def test_the_collapsed_column_uses_the_width(self):
        [only] = columns(80)
        assert only.end <= 80
        assert only.width > 70

    def test_grid_appears_at_the_threshold(self):
        assert len(columns(MIN_GRID_WIDTH)) == GRID_COLS

    def test_a_single_column_is_requestable(self):
        assert len(columns(228, count=1)) == 1

    @pytest.mark.parametrize("total", [120, 150, 180, 228, 400])
    def test_never_produces_a_zero_width_column(self, total):
        assert all(c.width > 0 for c in columns(total))


class TestSpan:
    def test_spans_two_columns_including_the_gutter(self):
        cols = columns(228)
        wide = span(cols, 0, 1)
        assert wide.start == cols[0].start
        assert wide.end == cols[1].end
        assert wide.width > cols[0].width * 2

    def test_a_single_column_span_is_that_column(self):
        cols = columns(228)
        assert span(cols, 2, 2) == cols[2]

    def test_out_of_range_is_clamped(self):
        cols = columns(228)
        assert span(cols, -5, 99) == Column(cols[0].start, cols[-1].end - cols[0].start)

    def test_reversed_arguments_do_not_produce_a_negative_width(self):
        assert span(columns(228), 3, 1).width > 0


class TestTruncate:
    def test_short_text_is_untouched(self):
        assert truncate("hello", 20) == "hello"

    def test_exact_fit_is_untouched(self):
        assert truncate("hello", 5) == "hello"

    def test_long_text_is_marked_as_cut(self):
        out = truncate("a very long task title indeed", 12)
        assert len(out) == 12
        assert out.endswith("…")

    def test_zero_width(self):
        assert truncate("anything", 0) == ""

    def test_width_smaller_than_the_ellipsis(self):
        assert len(truncate("anything", 1)) == 1

    def test_never_exceeds_the_width(self):
        for w in range(1, 30):
            assert len(truncate("x" * 50, w)) <= w


class TestPad:
    def test_fills_to_exact_width(self):
        assert len(pad("abc", 10)) == 10

    def test_alignments(self):
        assert pad("abc", 7) == "abc    "
        assert pad("abc", 7, "right") == "    abc"
        assert pad("abc", 7, "center").strip() == "abc"

    def test_overlong_text_is_truncated_not_overflowed(self):
        """A cell that overflows breaks every column to its right."""
        assert len(pad("x" * 40, 10)) == 10


def test_default_width_is_sane():
    assert 60 <= DEFAULT_WIDTH <= 120
