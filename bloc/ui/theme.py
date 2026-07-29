"""
Display themes — the glyph vocabulary and the colour system.

Data only. Rendering lives in `widgets.py`, writing lives in `console.py`, so a
theme can be inspected and tested with no terminal attached.

## Colour is a role, never a colour

Every palette entry is named for **what it means**, not what it looks like:
`attention`, not `amber`. That is what lets VOID express the same system as a
brightness ramp and FOG express it as nothing at all, and it is what stops a
screen reaching for "the orange one" and quietly inventing a meaning.

The three environments are now three genuinely different answers rather than
three glyph sets:

    HUD   full colour, aviation glyphs      — the device
    VOID  monochrome brightness ramp        — colour-blind safe, mono displays
    FOG   no colour, no symbols, plain text — any terminal, screen readers, SSH

**`None` means "the terminal's own colour"** — the sentinel that makes FOG
possible without a special case in the writer.

## What was wrong before

v0.1 hardcoded `◈` at 128 call sites, so selecting FOG still rendered aviation
glyphs. S2 fixed that by moving glyphs into this file. But the palette kept
v0.1's own defect: **HUD's `primary` and `secondary` were the same green**, so
the hierarchy every screen assumed simply did not exist on screen. Rendering
OBJECTIVES full-width made it obvious — everything read as one flat wall. That
single line was most of "hard to read".
"""

from __future__ import annotations

from dataclasses import dataclass, fields

#: An RGB triple, or `None` for "leave it to the terminal".
RGB = tuple[int, int, int] | None

#: Default rule width. A default, not a constraint — `widgets.separator()` takes
#: a width, so a panel can rule to its own column without the theme knowing.
SEPARATOR_WIDTH = 40


@dataclass(frozen=True)
class Glyphs:
    """The character vocabulary for one environment."""

    bullet: str
    bullet_done: str
    bullet_active: str
    #: Rule characters — single characters, repeated to width at render time.
    #: Storing them pre-multiplied baked a fixed 40-column panel into theme data,
    #: which is the same mistake as a hardcoded leader fill: a width belongs to
    #: the layout, not to the glyph vocabulary.
    separator: str
    separator_dbl: str
    separator_dot: str
    corner_tl: str
    indicator: str
    indicator_off: str
    target: str
    crosshair: str
    arrow_up: str
    arrow_dn: str
    arrow_lt: str
    arrow_rt: str
    bar_full: str
    bar_empty: str
    bar_half: str
    aircraft: tuple[str, ...]
    sweep: str
    lock: str
    #: Fill character for dot leaders — `LABEL ······ VALUE`. Theme data rather
    #: than a widget default, so FOG really does render without symbols.
    leader_fill: str
    #: Left-edge marker on a strip that needs attention. Redundant with colour on
    #: purpose: colour alone fails in daylight on a glossy panel, and fails
    #: permanently for red-green colour blindness.
    flag: str


@dataclass(frozen=True)
class Palette:
    """
    Colour by role. Every entry answers "what does this mean", not "what colour".

    Grouped into three bands, and the bands matter: a screen picks a *surface* to
    sit on, a *text* weight for hierarchy, and a *state* colour for meaning.
    Mixing bands — using a state colour for hierarchy — is how a palette rots.
    """

    # ── surfaces ──────────────────────────────────────────
    background: RGB
    surface: RGB
    surface_dead: RGB
    rule: RGB
    rule_dead: RGB

    # ── text hierarchy ────────────────────────────────────
    primary: RGB
    secondary: RGB
    dim: RGB
    faint: RGB

    # ── state ─────────────────────────────────────────────
    active: RGB       # in progress, descending
    pressure: RGB     # overdue, climbing — something is pushing on you
    queued: RGB       # waiting, level
    attention: RGB    # needs a decision from you
    critical: RGB     # failed, conflicting
    fixed: RGB        # infrastructure: titles, airports, headings


@dataclass(frozen=True)
class Theme:
    name: str
    glyphs: Glyphs
    palette: Palette

    def style(self, role: str) -> RGB:
        """Resolve a palette role, falling back to `primary` for an unknown name."""
        return getattr(self.palette, role, self.palette.primary)


# ─── HUD · aviation glyphs, green phosphor ────────────────

HUD = Theme(
    name="hud",
    glyphs=Glyphs(
        bullet="▢",
        bullet_done="▣",
        bullet_active="▶",
        separator="─",
        separator_dbl="═",
        separator_dot="·",
        corner_tl="◈",
        indicator="●",
        indicator_off="○",
        target="△",
        crosshair="⊕",
        arrow_up="▲",
        arrow_dn="▼",
        arrow_lt="◀",
        arrow_rt="▶",
        bar_full="█",
        bar_empty="░",
        bar_half="▓",
        aircraft=("▲", "↗", "▶", "↘", "▼", "↙", "◀", "↖"),
        sweep="·",
        lock="◉",
        leader_fill="·",
        flag="▌",
    ),
    palette=Palette(
        background=(4, 9, 7),
        surface=(9, 19, 14),
        surface_dead=(7, 13, 10),
        rule=(24, 58, 42),
        rule_dead=(14, 32, 24),
        # primary and secondary are deliberately far apart — see the module
        # docstring. Two greens a shade apart is not a hierarchy.
        primary=(0, 255, 65),
        secondary=(124, 194, 158),
        dim=(63, 133, 104),
        faint=(45, 103, 79),
        active=(72, 210, 255),
        pressure=(255, 72, 196),
        queued=(110, 160, 255),
        attention=(255, 176, 0),
        critical=(255, 80, 80),
        fixed=(208, 232, 218),
    ),
)


# ─── VOID · bracket geometry, monochrome ──────────────────
#
# State is carried by *brightness*, not hue. Usable on a monochrome panel, and
# the one theme that is fully legible with any form of colour blindness — the
# glyphs and the flag do the work the hue does in HUD.

VOID = Theme(
    name="void",
    glyphs=Glyphs(
        bullet="[ ]",
        bullet_done="[x]",
        bullet_active="[>]",
        separator="-",
        separator_dbl="=",
        separator_dot=".",
        corner_tl="[*]",
        indicator="[+]",
        indicator_off="[-]",
        target="[^]",
        crosshair="[o]",
        arrow_up="^",
        arrow_dn="v",
        arrow_lt="<",
        arrow_rt=">",
        bar_full="#",
        bar_empty=".",
        bar_half="+",
        aircraft=("^", "/", ">", "\\", "v", "/", "<", "\\"),
        sweep=".",
        lock="[#]",
        leader_fill=".",
        flag="|",
    ),
    palette=Palette(
        background=(6, 6, 6),
        surface=(18, 18, 18),
        surface_dead=(11, 11, 11),
        rule=(64, 64, 64),
        rule_dead=(38, 38, 38),
        primary=(240, 240, 240),
        secondary=(184, 184, 184),
        dim=(132, 132, 132),
        faint=(92, 92, 92),
        active=(255, 255, 255),
        pressure=(236, 236, 236),
        queued=(158, 158, 158),
        attention=(255, 255, 255),
        critical=(210, 210, 210),
        fixed=(206, 206, 206),
    ),
)


# ─── FOG · plain text, no symbols, no colour ──────────────
#
# Every role is `None`, so the writer emits no escape at all. This is the theme
# that works over a bad SSH link, on a terminal with no colour support, through
# a screen reader, and in a pipe. Meaning survives entirely in the words and the
# glyphs — which is the strongest possible test that the interface is not
# leaning on colour to say something it never says in text.

FOG = Theme(
    name="fog",
    glyphs=Glyphs(
        bullet="  -",
        bullet_done="  *",
        bullet_active="  >",
        separator=" ",
        separator_dbl=" ",
        separator_dot=" ",
        corner_tl="",
        indicator="on",
        indicator_off="off",
        target="tgt",
        crosshair="ctr",
        arrow_up="up",
        arrow_dn="dn",
        arrow_lt="lt",
        arrow_rt=">>",
        bar_full="|",
        bar_empty=" ",
        bar_half=":",
        aircraft=("^", "/", ">", "\\", "v", "/", "<", "\\"),
        sweep=" ",
        lock="(!)",
        leader_fill=" ",
        flag="!",
    ),
    palette=Palette(
        **{f.name: None for f in fields(Palette)},
    ),
)


THEMES: dict[str, Theme] = {t.name: t for t in (HUD, VOID, FOG)}

DEFAULT_THEME = HUD.name


def get_theme(name: str | None) -> Theme:
    """Resolve a theme by name, falling back to HUD for anything unrecognised."""
    return THEMES.get((name or "").lower(), THEMES[DEFAULT_THEME])


# ── legibility ────────────────────────────────────────────
#
# Here rather than in the tests because S8 lets a config file supply a palette,
# and a theme that cannot be read is a bug the loader should be able to catch
# rather than something the user discovers on a sunlit panel.


def _linearise(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(colour: RGB) -> float:
    """
    Relative luminance, 0.0–1.0, per WCAG.

    Not the mean of the channels: the eye is roughly seven times more sensitive
    to green than to blue, so `(0, 255, 65)` reads far brighter than its numbers
    suggest and `(124, 194, 158)` far dimmer. Averaging instead of weighting is
    how you end up "fixing" a palette that was already correct.
    """
    if colour is None:
        return 0.0
    r, g, b = (_linearise(c) for c in colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: RGB, b: RGB) -> float:
    """
    WCAG contrast ratio between two colours, 1.0 (identical) to 21.0 (black on
    white). 4.5 is the readable-body-text threshold; 7.0 is comfortable.
    """
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)
