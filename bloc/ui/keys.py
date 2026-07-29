"""
The single key reader.

v0.1 carried eight copies of this logic (`ui/shell.py`, `ui/settings_ui.py`,
`ui/kanban_ui.py`, `ui/radar_ui.py`, `ui/pulse_ui.py`, `ui/ambient_ui.py`,
`core/agenda.py`, `core/sync.py`). Three of them were broken on Linux — the
target platform — in two distinct ways:

1. `ui/settings_ui.py:18` called `termios.tcgetattr(fd, termios.TCSADRAIN, old)`
   in its `finally` block where it meant `tcsetattr`. `tcgetattr` takes one
   argument, so every keypress raised `TypeError` and left the terminal raw.

2. `ui/pulse_ui.py:15` and `ui/ambient_ui.py:15` called `select()` on stdin
   while the terminal was still in *cooked* mode — raw mode was only entered
   after `select` reported readable. Cooked stdin is not readable until Enter,
   so the live countdown and the screensaver's exit-on-keypress never fired.

Both classes of bug come from the same root cause: toggling terminal mode around
every individual keypress. Here, mode is held for the lifetime of a screen via
the `raw_mode()` context manager, and the read functions assume it is active.
`raw_mode()` is re-entrant, so a nested call is a no-op and the read functions
can safely enter it themselves when used standalone.

Cbreak rather than full raw: ISIG is left enabled so Ctrl-C still interrupts.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable, Iterator

# How long to wait for the remainder of an escape sequence before concluding
# that a bare Escape was pressed. Generous enough for a slow serial console.
ESCAPE_TIMEOUT = 0.05


class Key:
    """Names for keys that do not map to a single printable character."""

    UP = "<up>"
    DOWN = "<down>"
    LEFT = "<left>"
    RIGHT = "<right>"
    ENTER = "<enter>"
    ESC = "<esc>"
    TAB = "<tab>"
    BACKSPACE = "<backspace>"
    HOME = "<home>"
    END = "<end>"
    DELETE = "<delete>"


# ── escape-sequence decoding ──────────────────────────────
# Kept as pure lookups over an injected reader so the decoder is testable
# without a terminal.

_CSI_FINAL = {
    "A": Key.UP,
    "B": Key.DOWN,
    "C": Key.RIGHT,
    "D": Key.LEFT,
    "H": Key.HOME,
    "F": Key.END,
}

_CSI_NUMERIC = {
    "1": Key.HOME,
    "3": Key.DELETE,
    "4": Key.END,
    "7": Key.HOME,
    "8": Key.END,
}

_WINDOWS_EXTENDED = {
    "H": Key.UP,
    "P": Key.DOWN,
    "K": Key.LEFT,
    "M": Key.RIGHT,
    "G": Key.HOME,
    "O": Key.END,
    "S": Key.DELETE,
}

_CONTROL = {
    "\r": Key.ENTER,
    "\n": Key.ENTER,
    "\t": Key.TAB,
    "\x7f": Key.BACKSPACE,
    "\x08": Key.BACKSPACE,
}


def decode_escape(read_more: Callable[[], str | None]) -> str:
    """
    Decode the remainder of an escape sequence, given that ESC was just read.

    `read_more` returns the next character, or None if none arrives promptly.
    Returns a `Key` constant, or `Key.ESC` for a bare Escape or any sequence
    that is not recognised.
    """
    nxt = read_more()
    if nxt is None or nxt not in ("[", "O"):
        return Key.ESC

    final = read_more()
    if final is None:
        return Key.ESC

    if final.isdigit():
        digits = final
        while True:
            char = read_more()
            if char is None or char == "~":
                break
            digits += char
        return _CSI_NUMERIC.get(digits, Key.ESC)

    return _CSI_FINAL.get(final, Key.ESC)


def translate(char: str) -> str:
    """Map a single raw character to a `Key` constant, or return it unchanged."""
    return _CONTROL.get(char, char)


# ── platform back ends ────────────────────────────────────

_WINDOWS = os.name == "nt"

if _WINDOWS:  # pragma: no cover - platform specific
    import msvcrt

    @contextlib.contextmanager
    def raw_mode() -> Iterator[None]:
        """No-op on Windows: msvcrt reads keys directly without mode changes."""
        yield

    def _read_char() -> str:
        return msvcrt.getwch()

    def _read_char_timeout(timeout: float) -> str | None:
        # msvcrt has no timed read; poll kbhit, which is what a timeout means here.
        deadline = _monotonic() + timeout
        while True:
            if msvcrt.kbhit():
                return msvcrt.getwch()
            if _monotonic() >= deadline:
                return None

    def _get_key() -> str:
        char = _read_char()
        if char in ("\x00", "\xe0"):
            return _WINDOWS_EXTENDED.get(_read_char(), Key.ESC)
        return translate(char)

    def _key_available(timeout: float) -> bool:
        deadline = _monotonic() + timeout
        while True:
            if msvcrt.kbhit():
                return True
            if _monotonic() >= deadline:
                return False

else:
    import select
    import termios

    _depth = 0
    _saved: list | None = None

    @contextlib.contextmanager
    def raw_mode() -> Iterator[None]:
        """
        Hold the terminal in cbreak mode for the duration of the block.

        Re-entrant: nested uses are no-ops, so a screen can hold the mode for its
        whole loop while individual reads remain safe to call standalone. A no-op
        when stdin is not a tty, so tests and pipes work unchanged.
        """
        global _depth, _saved

        if not _isatty():
            yield
            return

        fd = sys.stdin.fileno()
        if _depth == 0:
            _saved = termios.tcgetattr(fd)
            attrs = termios.tcgetattr(fd)
            # Clear canonical mode and echo; leave ISIG so Ctrl-C still works.
            attrs[3] &= ~(termios.ICANON | termios.ECHO)
            attrs[6][termios.VMIN] = 1
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
        _depth += 1
        try:
            yield
        finally:
            _depth -= 1
            if _depth == 0 and _saved is not None:
                # tcsetattr, not tcgetattr — the v0.1 settings screen had this
                # exact call wrong, which is why it crashed on every keypress.
                termios.tcsetattr(fd, termios.TCSADRAIN, _saved)
                _saved = None

    def _read_char() -> str:
        return sys.stdin.read(1)

    def _read_char_timeout(timeout: float) -> str | None:
        if not _isatty():
            return _read_char() or None
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        return sys.stdin.read(1) if ready else None

    def _get_key() -> str:
        char = _read_char()
        if char == "\x1b":
            return decode_escape(lambda: _read_char_timeout(ESCAPE_TIMEOUT))
        return translate(char)

    def _key_available(timeout: float) -> bool:
        if not _isatty():
            return True
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        return bool(ready)


def _isatty() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):  # detached or closed stdin
        return False


def _monotonic() -> float:
    import time

    return time.monotonic()


# ── public API ────────────────────────────────────────────


def get_key() -> str:
    """
    Block until a key is pressed and return it.

    Returns a single character, or a `Key` constant for control and arrow keys.
    """
    with raw_mode():
        return _get_key()


def get_key_nowait(timeout: float = 0.0) -> str | None:
    """
    Return a key if one is available within `timeout` seconds, else None.

    Unlike the v0.1 implementations, the terminal is already in cbreak mode
    before `select` is consulted — which is what makes this work on Linux at all.
    """
    with raw_mode():
        if not _key_available(timeout):
            return None
        return _get_key()
