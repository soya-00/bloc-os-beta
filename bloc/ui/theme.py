"""
Display themes — glyph vocabulary and colour palette.

Ported from the v0.1 `ui/environment.py`, with one structural change: this module
holds *data only*. Rendering helpers live in `widgets.py` and writing to the
terminal lives in `console.py`, so a theme can be inspected and tested without a
terminal attached.

Three environments, unchanged from v0.1:

    HUD   aviation/military symbols   (◈ ▶ ▢ ●)
    VOID  bracket/minimal geometry    ([ ] > # -)
    FOG   pure plain text, no symbols (. * > -)

`Glyphs` is a frozen dataclass rather than a dict so that a mistyped glyph name
fails at import instead of silently rendering an empty string — which is how the
v0.1 `env.char()` lookup behaved.
"""

from __future__ import annotations

from dataclasses import dataclass

from colorama import Fore, Style, init

init()

#: Default rule width. A default, not a constraint — `widgets.separator()` takes
#: a width, so the MFD panel can rule to its own column without the theme knowing.
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


@dataclass(frozen=True)
class Palette:
    """ANSI styling for one environment. Empty string means 'terminal default'."""

    primary: str
    secondary: str
    accent: str
    dim: str
    alert: str
    critical: str
    reset: str = Style.RESET_ALL


@dataclass(frozen=True)
class Theme:
    name: str
    glyphs: Glyphs
    palette: Palette

    def style(self, name: str) -> str:
        """Look up a palette entry by name, falling back to primary."""
        return getattr(self.palette, name, self.palette.primary)


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
    ),
    palette=Palette(
        primary=Fore.GREEN,
        secondary=Fore.GREEN,
        accent=Fore.YELLOW,
        dim=Fore.GREEN + Style.DIM,
        alert=Fore.YELLOW + Style.BRIGHT,
        critical=Fore.RED + Style.BRIGHT,
    ),
)


# ─── VOID · bracket geometry, monochrome ──────────────────

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
    ),
    palette=Palette(
        primary=Fore.WHITE,
        secondary=Fore.WHITE + Style.DIM,
        accent=Fore.MAGENTA,
        dim=Style.DIM,
        alert=Fore.YELLOW,
        critical=Fore.RED,
    ),
)


# ─── FOG · plain text, no symbols ─────────────────────────

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
    ),
    palette=Palette(
        primary="",
        secondary=Style.DIM,
        accent=Fore.BLUE,
        dim=Style.DIM,
        alert=Fore.YELLOW,
        critical=Fore.RED,
    ),
)


THEMES: dict[str, Theme] = {t.name: t for t in (HUD, VOID, FOG)}

DEFAULT_THEME = HUD.name


def get_theme(name: str | None) -> Theme:
    """Resolve a theme by name, falling back to HUD for anything unrecognised."""
    return THEMES.get((name or "").lower(), THEMES[DEFAULT_THEME])
