"""
Terminal writer — the only module in BLOC that performs output.

Everything else builds strings. That is what lets every layout function in
`widgets.py` be a pure function tested against a return value rather than
against captured stdout.

## Colour depth is detected, not assumed

The palette is 24-bit RGB. Terminals are not all 24-bit, so this module
degrades: truecolor where it exists, the 256-colour cube where it does not, and
nothing at all when output is not a terminal or the user has asked for no
colour. `NO_COLOR` is honoured because it is a real convention and costs one
line.

Degrading matters for the target: development happens on macOS in a truecolor
terminal, but the Pi's own console over KMS is a 256-colour environment, and a
palette that only works on the laptop is a palette that breaks on the device.
"""

from __future__ import annotations

import os
import sys

from bloc.ui.theme import RGB, SEPARATOR_WIDTH, Theme, get_theme
from bloc.ui.widgets import DEFAULT_WIDTH, separator

TRUECOLOR = "truecolor"
COLOR256 = "256"
MONO = "mono"

RESET = "\033[0m"


def detect_depth(stream=None, env: dict | None = None) -> str:
    """
    How much colour this stream can carry.

    Takes its environment as an argument so the decision is a pure function of
    inputs and can be tested for every case rather than only the one the test
    machine happens to have.
    """
    env = os.environ if env is None else env
    stream = stream or sys.stdout

    if env.get("NO_COLOR"):
        return MONO
    try:
        if not stream.isatty():
            return MONO
    except Exception:  # pragma: no cover - exotic stream objects
        return MONO

    if env.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return TRUECOLOR
    term = env.get("TERM", "")
    if "256color" in term or "direct" in term:
        return COLOR256
    if term in ("dumb", ""):
        return MONO
    return COLOR256


def _cube(value: int) -> int:
    """Map one 0–255 channel onto the 6 levels of the xterm colour cube."""
    return 0 if value < 48 else 1 if value < 115 else min(4, (value - 35) // 40) + 1


def to_ansi(colour: RGB, depth: str, background: bool = False) -> str:
    """
    One RGB role rendered as an escape sequence for the depth available.

    Returns `""` for a `None` colour — which is how FOG renders as genuinely
    uncoloured rather than as "the default colour, explicitly set".
    """
    if colour is None or depth == MONO:
        return ""
    layer = 48 if background else 38
    r, g, b = colour
    if depth == TRUECOLOR:
        return f"\033[{layer};2;{r};{g};{b}m"
    if r == g == b:  # greys get the 24-step ramp, which is much finer
        return f"\033[{layer};5;{232 + min(23, r * 24 // 256)}m"
    return f"\033[{layer};5;{16 + 36 * _cube(r) + 6 * _cube(g) + _cube(b)}m"


class Console:
    """Writes themed output to a stream."""

    def __init__(
        self,
        theme: Theme | None = None,
        stream=None,
        width: int | None = None,
        depth: str | None = None,
    ) -> None:
        self.theme = theme or get_theme(None)
        self.stream = stream or sys.stdout
        self._width = width
        self.depth = depth or detect_depth(self.stream)

    # ── geometry ──────────────────────────────────────────

    @property
    def width(self) -> int:
        """
        Columns available. Explicit override wins, then the real terminal, then
        a sane default so a pipe or a test does not lay out at zero.
        """
        if self._width:
            return self._width
        try:
            return os.get_terminal_size(self.stream.fileno()).columns
        except (OSError, AttributeError, ValueError):
            return DEFAULT_WIDTH

    def set_theme(self, name: str) -> None:
        """Switch theme by name — used when the setting changes at runtime."""
        self.theme = get_theme(name)

    # ── writing ───────────────────────────────────────────

    def write(self, text: str = "", role: str = "primary", end: str = "\n") -> None:
        colour = to_ansi(self.theme.style(role), self.depth)
        self.stream.write(f"{colour}{text}{RESET if colour else ''}{end}")

    def cell(self, text: str, role: str = "primary", on: str = "surface", end: str = "\n") -> None:
        """
        Write text on a filled background — a strip in a bay, a selected row.

        Background fills are what make the strip bays read as a printed board
        rather than as a table, and they are the one place the surface roles are
        used directly.
        """
        fg = to_ansi(self.theme.style(role), self.depth)
        bg = to_ansi(self.theme.style(on), self.depth, background=True)
        self.stream.write(f"{bg}{fg}{text}{RESET if fg or bg else ''}{end}")

    # ── hierarchy ─────────────────────────────────────────

    def primary(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "primary", end)

    def secondary(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "secondary", end)

    def dim(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "dim", end)

    def faint(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "faint", end)

    # ── state ─────────────────────────────────────────────

    def active(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "active", end)

    def pressure(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "pressure", end)

    def queued(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "queued", end)

    def attention(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "attention", end)

    def critical(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "critical", end)

    def fixed(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "fixed", end)

    # ── structure ─────────────────────────────────────────

    def blank(self) -> None:
        self.stream.write("\n")

    def rule(self, style: str = "single", width: int | None = None, role: str = "rule") -> None:
        self.write(separator(self.theme.glyphs, style, width or self.width), role)

    def clear(self) -> None:
        """Clear the screen, preferring an ANSI escape over spawning a shell."""
        try:
            tty = self.stream.isatty()
        except Exception:  # pragma: no cover
            tty = False
        if tty:
            self.stream.write("\033[2J\033[H")
        elif os.name == "nt":  # pragma: no cover - platform specific
            os.system("cls")
