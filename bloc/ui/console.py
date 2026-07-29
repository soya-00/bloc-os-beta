"""
Terminal writer.

The only module in `bloc/ui/` that performs I/O. Everything else builds strings.

This is the half of v0.1's `Environment` that actually printed; the theme data it
carried now lives in `theme.py`. Splitting them is what makes the layout helpers
in `widgets.py` testable as pure functions.
"""

from __future__ import annotations

import os
import sys

from bloc.ui.theme import Theme, get_theme
from bloc.ui.widgets import separator


class Console:
    """Writes themed output to a stream."""

    def __init__(self, theme: Theme | None = None, stream=None) -> None:
        self.theme = theme or get_theme(None)
        self.stream = stream or sys.stdout

    def set_theme(self, name: str) -> None:
        """Switch theme by name — used when the setting changes at runtime."""
        self.theme = get_theme(name)

    # ── writing ───────────────────────────────────────────

    def write(self, text: str = "", style: str = "primary", end: str = "\n") -> None:
        colour = self.theme.style(style)
        reset = self.theme.palette.reset if colour else ""
        self.stream.write(f"{colour}{text}{reset}{end}")

    def primary(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "primary", end)

    def secondary(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "secondary", end)

    def accent(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "accent", end)

    def dim(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "dim", end)

    def alert(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "alert", end)

    def critical(self, text: str = "", end: str = "\n") -> None:
        self.write(text, "critical", end)

    def blank(self) -> None:
        self.stream.write("\n")

    def rule(self, style: str = "single") -> None:
        self.secondary(separator(self.theme.glyphs, style))

    def clear(self) -> None:
        """Clear the screen, preferring an ANSI escape over spawning a shell."""
        if self.stream.isatty():
            self.stream.write("\033[2J\033[H")
        elif os.name == "nt":  # pragma: no cover - platform specific
            os.system("cls")
