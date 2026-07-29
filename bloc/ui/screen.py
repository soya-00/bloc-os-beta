"""
The MFD contract — the framework owns the key loop; screens declare data.

v0.1 gave every screen its own `while True:` loop with its own `get_key()` call
(copy-pasted eight times) and its own private bindings. Nothing enforced that `f`
meant the same thing twice, nothing rendered a legend, and there was no way to
get back to a known place except by knowing which of `q`/`esc`/`b` that
particular screen happened to accept.

This module replaces all of that with one loop, modelled on a multi-function
display:

* **Global keys work from every screen.** Direct-to, back, home, quit — four,
  and the set is closed. They are dispatched *before* the screen ever sees the
  key, so a screen cannot shadow them even by accident.
* **Screens declare soft keys as data**, not as branches in a key loop. The
  legend on the bottom row therefore renders itself, and it cannot drift out of
  sync with the bindings the way a hand-written help string does.
* **A soft key may not reuse a global key.** `SoftKey` raises on construction,
  so "no key means two different things in two places" is a property of the
  type rather than a review checklist item.

A screen is anything with `title` and `render()`. Everything else — `soft_keys()`,
`on_key()`, `status()` — is optional and looked up with `getattr`, so a screen
starts as ten lines and grows only where it needs to.

The physical panel (P3) attaches here: a GPIO button under the display emits the
same key its on-screen label advertises, which is why no app will need to know
that `controls_gpio.py` exists.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias, runtime_checkable

from bloc.ui.console import Console
from bloc.ui.keys import Key, get_key
from bloc.ui.keys import raw_mode as _raw_mode
from bloc.ui.theme import Glyphs
from bloc.ui.widgets import DEFAULT_WIDTH, leader

#: Fallback panel width, used when nothing supplies a real one. The live width
#: comes from `Console.width`, so a screen fills the display on the appliance and
#: still lays out in an 80-column SSH window.
PANEL = DEFAULT_WIDTH


class Signal(enum.Enum):
    """What a handler wants the framework to do next."""

    STAY = enum.auto()
    BACK = enum.auto()
    HOME = enum.auto()
    QUIT = enum.auto()
    DIRECT_TO = enum.auto()


# ── the closed global set ─────────────────────────────────

#: `(key, label)` for each global, in legend order.
#:
#: Punctuation and `Esc` rather than letters, with one deliberate exception: `q`
#: is the single reserved letter, because every terminal user already expects it
#: and the cost is one letter out of twenty-six. Everything else in the alphabet
#: stays available to screens forever.
#:
#: `Key.HOME` is accepted as a synonym for the backtick, but the backtick is what
#: the legend advertises: a Mac laptop has no Home key without a chord.
GLOBALS: tuple[tuple[str, str], ...] = (
    ("/", "DIRECT-TO"),
    (Key.ESC, "BACK"),
    ("`", "HOME"),
    ("q", "QUIT"),
)

GLOBAL_KEYS: dict[str, Signal] = {
    "/": Signal.DIRECT_TO,
    Key.ESC: Signal.BACK,
    "`": Signal.HOME,
    Key.HOME: Signal.HOME,
    "q": Signal.QUIT,
}


#: A handler's return value. A screen instance means "push this".
Outcome: TypeAlias = "Signal | Screen | None"


@dataclass(frozen=True)
class SoftKey:
    """
    One labelled button on the bottom row.

    `handler` returns an `Outcome`: `None`/`Signal.STAY` to stay put, a `Signal`
    to navigate, or a screen to push.
    """

    key: str
    label: str
    handler: Callable[[], Outcome] = lambda: None
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.key in GLOBAL_KEYS:
            raise ValueError(
                f"{self.key!r} is a global key ({GLOBAL_KEYS[self.key].name}) and cannot be "
                f"bound to the soft key {self.label!r}. The global set is closed — route "
                f"one-off verbs through direct-to instead of claiming a key."
            )
        if not self.key:
            raise ValueError("a soft key needs a key")


@runtime_checkable
class Screen(Protocol):
    """
    The minimum a screen must provide.

    Structural, not inherited: `ScreenStack` uses `getattr` for everything
    optional, so a screen never has to subclass anything to be run.
    """

    title: str

    def render(self, console: Console) -> None:
        """Draw the body. The framework has already drawn the header."""


# ── pure rendering ────────────────────────────────────────

_KEY_NAMES = {
    Key.ESC: "ESC",
    Key.ENTER: "ENT",
    Key.TAB: "TAB",
    Key.BACKSPACE: "BSP",
    Key.DELETE: "DEL",
    Key.UP: "UP",
    Key.DOWN: "DN",
    Key.LEFT: "LT",
    Key.RIGHT: "RT",
    Key.HOME: "HOME",
    Key.END: "END",
    " ": "SPC",
}


def key_name(key: str) -> str:
    """The short label a key gets inside its bracket on the legend."""
    return _KEY_NAMES.get(key, key.upper())


def _cell(key: str, label: str, enabled: bool = True) -> str:
    """
    One legend cell: `[C] COMPLETE`.

    A disabled soft key keeps its slot and empties its bracket rather than
    vanishing. Buttons on a real panel do not move around when they grey out,
    and a legend whose cells reflow on every state change is unreadable.
    """
    name = key_name(key)
    slot = name if enabled else " " * len(name)
    return f"[{slot}] {label}"


def render_legend(soft_keys: Sequence[SoftKey] = (), width: int = PANEL) -> list[str]:
    """
    Render the bottom row: the screen's soft keys, then the globals.

    The globals are appended unconditionally and are not the screen's to
    suppress — a screen that could hide `BACK` could strand you on it.
    """
    lines = _wrap([_cell(sk.key, sk.label, sk.enabled) for sk in soft_keys], width)
    lines.extend(_wrap([_cell(k, label) for k, label in GLOBALS], width))
    return lines


def _wrap(cells: Iterable[str], width: int, gap: str = "  ") -> list[str]:
    """Pack cells into lines of at most `width`, never splitting a cell."""
    lines: list[str] = []
    row: list[str] = []
    for cell in cells:
        candidate = gap.join([*row, cell])
        if row and len(candidate) > width:
            lines.append(gap.join(row))
            row = [cell]
        else:
            row.append(cell)
    if row:
        lines.append(gap.join(row))
    return lines


def render_header(title: str, glyphs: Glyphs, width: int = PANEL) -> str:
    """
    `◈ BLOC OS ·············· OBJECTIVES` — where you are, in one line.

    Uses the same `leader()` every other screen uses, so the header ends at the
    same column as the body and the legend.
    """
    brand = f"{glyphs.corner_tl} BLOC OS".lstrip()
    return leader(brand, title.upper(), glyphs, width=width)


# ── input ─────────────────────────────────────────────────


def prompt(
    console: Console,
    label: str = "DIRECT-TO",
    read_key: Callable[[], str] = get_key,
) -> str | None:
    """
    Read one line on the bottom row. Returns `None` if cancelled.

    A hand-rolled editor rather than `input()` because the terminal is in cbreak
    mode: `input()` would need echo and canonical mode restored and put back, and
    v0.1's attempts at exactly that are two of the three bugs that made the Linux
    build unusable.

    Deliberately minimal — printable characters, backspace, enter, escape. No
    history, no cursor movement. This is a command entry field on an instrument,
    not a shell.
    """
    buf: list[str] = []
    while True:
        console.stream.write("\r\033[K")
        console.write(f"{label} > {''.join(buf)}", "attention", end="")
        console.stream.flush()

        key = read_key()
        if key == Key.ENTER:
            console.stream.write("\n")
            return "".join(buf).strip() or None
        if key == Key.ESC:
            console.stream.write("\n")
            return None
        if key == Key.BACKSPACE:
            if buf:
                buf.pop()
        elif len(key) == 1 and key.isprintable():
            buf.append(key)


# ── the loop ──────────────────────────────────────────────


@dataclass
class ScreenStack:
    """
    The one key loop in BLOC.

    `direct_to` receives the typed line and returns an `Outcome`. It is injected
    rather than imported because the parser it will eventually call
    (`IntentParser`, S10) does not exist yet, and because it is the seam that
    lets the whole loop be tested without a terminal.
    """

    console: Console
    direct_to: Callable[[str], Outcome] | None = None
    read_key: Callable[[], str] = get_key
    _stack: list[Screen] = field(default_factory=list, repr=False)

    # ── stack ─────────────────────────────────────────────

    @property
    def current(self) -> Screen:
        return self._stack[-1]

    @property
    def depth(self) -> int:
        return len(self._stack)

    def push(self, screen: Screen) -> None:
        self._stack.append(screen)

    def back(self) -> None:
        """Pop unless already home. Back at the root is a no-op, not an exit."""
        if len(self._stack) > 1:
            self._stack.pop()

    def home(self) -> None:
        del self._stack[1:]

    # ── running ───────────────────────────────────────────

    def run(self, home: Screen) -> None:
        """Draw, read, dispatch, until something quits."""
        self._stack = [home]
        with _raw_mode():
            try:
                while self._stack:
                    self.draw()
                    if self.dispatch(self.read_key()) is False:
                        break
            except KeyboardInterrupt:
                pass

    def draw(self) -> None:
        c = self.console
        glyphs = c.theme.glyphs
        screen = self.current

        width = c.width

        c.clear()
        c.primary(render_header(getattr(screen, "title", ""), glyphs, width))

        status = self._call_optional(screen, "status")
        if status:
            c.dim(str(status))
        c.rule("double", width)
        c.blank()

        screen.render(c)

        c.blank()
        c.rule("single", width)
        for line in render_legend(self._soft_keys(screen), width):
            c.secondary(line)

    def dispatch(self, key: str) -> bool:
        """
        Handle one keypress. Returns False to stop the loop.

        Globals are resolved first and unconditionally. That ordering is the
        whole guarantee: a screen never gets the chance to swallow `BACK`, no
        matter what it puts in `on_key`.
        """
        signal = GLOBAL_KEYS.get(key)
        if signal is not None:
            if signal is Signal.DIRECT_TO:
                return self._direct_to()
            return self.apply(signal)

        screen = self.current
        for soft in self._soft_keys(screen):
            if soft.key == key:
                return self.apply(soft.handler()) if soft.enabled else True

        on_key = getattr(screen, "on_key", None)
        return self.apply(on_key(key)) if on_key else True

    def apply(self, outcome: Outcome) -> bool:
        """Turn a handler's return value into navigation."""
        if outcome is None or outcome is Signal.STAY:
            return True
        if outcome is Signal.QUIT:
            return False
        if outcome is Signal.BACK:
            self.back()
        elif outcome is Signal.HOME:
            self.home()
        elif outcome is Signal.DIRECT_TO:
            return self._direct_to()
        else:
            self.push(outcome)
        return True

    # ── internals ─────────────────────────────────────────

    def _direct_to(self) -> bool:
        text = prompt(self.console, read_key=self.read_key)
        if not text or self.direct_to is None:
            return True
        return self.apply(self.direct_to(text))

    @staticmethod
    def _soft_keys(screen: Screen) -> Sequence[SoftKey]:
        keys = ScreenStack._call_optional(screen, "soft_keys") or ()
        seen: dict[str, str] = {}
        for soft in keys:
            if soft.key in seen:
                raise ValueError(
                    f"{getattr(screen, 'title', screen)!r} binds {soft.key!r} to both "
                    f"{seen[soft.key]!r} and {soft.label!r}"
                )
            seen[soft.key] = soft.label
        return keys

    @staticmethod
    def _call_optional(screen: Screen, name: str):
        fn = getattr(screen, name, None)
        return fn() if callable(fn) else None


__all__ = [
    "GLOBALS",
    "GLOBAL_KEYS",
    "PANEL",
    "Screen",
    "ScreenStack",
    "Signal",
    "SoftKey",
    "key_name",
    "prompt",
    "render_header",
    "render_legend",
]
