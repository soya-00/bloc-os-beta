"""
Layout primitives.

Every function here is pure: it takes values and a `Glyphs`, and returns a
string. Nothing prints. That keeps the whole layer testable without capturing
stdout, and it is what lets `console.py` stay a dozen lines.

The dot-leader — `LABEL ········ [ VALUE ]` — is the signature idiom of the
interface. v0.1 reimplemented it in four places with four separate column
constants (`COL_WIDTH = 52` twice, `LAND_COL = 48`, `STATUS_COL = 52`), which is
why alignment drifted between screens.
"""

from __future__ import annotations

from bloc.ui.theme import SEPARATOR_WIDTH, Glyphs

#: Default column at which the trailing field starts. One constant, one alignment.
COL = 52

#: Standard left margin for body content.
INDENT = "    "


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
        pad = max(0, width - len(label) - 1)
        return f"{label} {fill * pad}" if pad else label

    pad = max(1, width - len(label) - len(value) - 2)
    return f"{label} {fill * pad} {value}"


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

    The width is an argument because the MFD panel is 52 columns wide while the
    theme's default rule is 40 — a rule that cannot match the panel it sits in is
    a layout decision trapped in theme data.
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
