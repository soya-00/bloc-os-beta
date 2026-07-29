"""
Layout primitives.

Every function here is pure: it takes values and a `Glyphs`, and returns a
string. Nothing prints. That keeps the whole layer testable without capturing
stdout, and it is what lets `console.py` stay a hundred lines.

The dot-leader — `LABEL ········ [ VALUE ]` — is the signature idiom of the
interface. v0.1 reimplemented it in four places with four separate column
constants (`COL_WIDTH = 52` twice, `LAND_COL = 48`, `STATUS_COL = 52`), which is
why alignment drifted between screens.

## The grid

Screens lay out on **four columns**, because the traffic scope's four strip bays
are 480 px across a 1920 px panel. Terminal screens divide the same way, so a
strip in the objectives list and the same strip on the scope land on the same
column — the two renderers share *structure*, not merely a palette. That is the
part a shared theme file cannot deliver on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from bloc.ui.theme import SEPARATOR_WIDTH, Glyphs

#: Columns to assume when the real terminal size cannot be read — a pipe, a
#: test, a detached process. Wide enough to lay out, narrow enough to be honest.
DEFAULT_WIDTH = 80

#: Below this, the grid collapses to a single column. An 80-column SSH window is
#: the working case: the Pi gets debugged remotely from week 11, and a layout
#: that only works at 1080p makes that miserable.
MIN_GRID_WIDTH = 120

GRID_COLS = 4
GUTTER = 3
MARGIN = 2

#: Legacy single-column width, kept for compact readouts and narrow terminals.
COL = 52

#: Standard left margin for body content.
INDENT = "    "


@dataclass(frozen=True)
class Column:
    """One column of the grid: where it starts and how wide it is."""

    start: int
    width: int

    @property
    def end(self) -> int:
        return self.start + self.width


def columns(
    total: int,
    count: int = GRID_COLS,
    gutter: int = GUTTER,
    margin: int = MARGIN,
) -> list[Column]:
    """
    Divide a width into `count` columns.

    Collapses to a single column below `MIN_GRID_WIDTH` rather than producing
    columns too narrow to hold a strip — four columns of nine characters is not
    a layout, it is a bug that renders.
    """
    usable = total - 2 * margin
    if total < MIN_GRID_WIDTH or count <= 1:
        return [Column(margin, max(1, usable))]

    inner = usable - gutter * (count - 1)
    width = max(1, inner // count)
    return [Column(margin + i * (width + gutter), width) for i in range(count)]


def span(cols: list[Column], first: int, last: int) -> Column:
    """
    One column covering `first` through `last` inclusive — the gutters between
    them become part of the span, so a detail panel under two bays lines up with
    both of them exactly.
    """
    first = max(0, min(first, len(cols) - 1))
    last = max(first, min(last, len(cols) - 1))
    return Column(cols[first].start, cols[last].end - cols[first].start)


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """
    Cut text to fit, marking that it was cut.

    `leader()` deliberately never truncates, because a ragged edge beats a
    silently shortened task title. Inside a fixed cell there is no such choice —
    so the cut is explicit and visible rather than a silent overflow that breaks
    every column to its right.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return text[:width]
    return text[: width - len(ellipsis)] + ellipsis


def pad(text: str, width: int, align: str = "left") -> str:
    """Fit text to exactly `width`, truncating if needed."""
    text = truncate(text, width)
    if align == "right":
        return text.rjust(width)
    if align == "center":
        return text.center(width)
    return text.ljust(width)


def leader(label: str, value: str = "", glyphs: Glyphs | None = None, width: int = COL) -> str:
    """
    Render `LABEL ········ VALUE`, padded so `value` ends at `width`.

    The fill comes from `glyphs.leader_fill`, not from a default in this
    function. That distinction is the whole point: a hardcoded `·` here would
    reintroduce the exact v0.1 bug this layer exists to fix, since selecting the
    FOG theme would still render dot leaders made of symbols.

    With no `value`, returns the label followed by fill to `width` — useful for
    section rules. Never truncates: a label longer than `width` simply pushes the
    value right, since silently cutting a task title is worse than a ragged edge.
    """
    fill = glyphs.leader_fill if glyphs else " "

    if not value:
        pad_n = max(0, width - len(label) - 1)
        return f"{label} {fill * pad_n}" if pad_n else label

    pad_n = max(1, width - len(label) - len(value) - 2)
    return f"{label} {fill * pad_n} {value}"


def bar(fraction: float, width: int, glyphs: Glyphs) -> str:
    """
    Render a progress bar. `fraction` is clamped to 0.0–1.0.

    Clamping matters: an overrunning focus timer produces a fraction above 1.0,
    and v0.1's unclamped `round(value * width)` would emit a bar wider than its
    own field and break the surrounding layout.
    """
    fraction = min(1.0, max(0.0, fraction))
    filled = round(fraction * width)
    return glyphs.bar_full * filled + glyphs.bar_empty * (width - filled)


def sparkline(done: int, total: int, width: int, glyphs: Glyphs) -> str:
    """
    Render a `done`-of-`total` bar.

    An empty set reads as empty, not full — `ui/shell.py:117` called this with
    the same value for both arguments, so the header bar showed 100% regardless
    of what was actually outstanding.
    """
    if total <= 0:
        return glyphs.bar_empty * width
    return bar(done / total, width, glyphs)


def separator(glyphs: Glyphs, style: str = "single", width: int = SEPARATOR_WIDTH) -> str:
    """
    Horizontal rule. `style` is one of 'single', 'double', 'dot'.

    The width is an argument because a rule that cannot match the panel it sits
    in is a layout decision trapped in theme data.
    """
    char = {
        "double": glyphs.separator_dbl,
        "dot": glyphs.separator_dot,
    }.get(style, glyphs.separator)
    return char * width


def field(label: str, value: str) -> str:
    """Render a bracketed instrument field: `LABEL [VALUE]`."""
    return f"{label} [{value}]"


def compass(bearing_deg: float, glyphs: Glyphs) -> str:
    """Map a bearing in degrees to one of the eight aircraft heading glyphs."""
    index = int((bearing_deg % 360) / 45 + 0.5) % 8
    return glyphs.aircraft[index]
