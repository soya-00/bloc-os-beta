import os
from colorama import init, Fore, Back, Style
init(autoreset=True)


# ─── CHARACTER SETS ───────────────────────────────────────
# Each environment has its own character vocabulary.
# HUD  = aviation/military symbols   (◈ ▶ ▢ ●)
# VOID = bracket/minimal geometry    ([ ] > # -)
# FOG  = pure plain text, no symbols (. * > -)

HUD_CHARS = {
    "bullet":        "▢",
    "bullet_done":   "▣",
    "bullet_active": "▶",
    "separator":     "────────────────────────────────────────",
    "separator_dbl": "════════════════════════════════════════",
    "separator_dot": "········································",
    "corner_tl":     "◈",
    "indicator":     "●",
    "indicator_off": "○",
    "target":        "△",
    "crosshair":     "⊕",
    "arrow_up":      "▲",
    "arrow_dn":      "▼",
    "arrow_lt":      "◀",
    "arrow_rt":      "▶",
    "bar_full":      "█",
    "bar_empty":     "░",
    "bar_half":      "▓",
    "aircraft":      ["▲", "↗", "▶", "↘", "▼", "↙", "◀", "↖"],
    "sweep":         "·",
    "lock":          "◉",
}

VOID_CHARS = {
    "bullet":        "[ ]",
    "bullet_done":   "[x]",
    "bullet_active": "[>]",
    "separator":     "----------------------------------------",
    "separator_dbl": "========================================",
    "separator_dot": "........................................",
    "corner_tl":     "[*]",
    "indicator":     "[+]",
    "indicator_off": "[-]",
    "target":        "[^]",
    "crosshair":     "[o]",
    "arrow_up":      "^",
    "arrow_dn":      "v",
    "arrow_lt":      "<",
    "arrow_rt":      ">",
    "bar_full":      "#",
    "bar_empty":     ".",
    "bar_half":      "+",
    "aircraft":      ["^", "/", ">", "\\", "v", "/", "<", "\\"],
    "sweep":         ".",
    "lock":          "[#]",
}

FOG_CHARS = {
    "bullet":        "  -",
    "bullet_done":   "  *",
    "bullet_active": "  >",
    "separator":     "                                        ",
    "separator_dbl": "                                        ",
    "separator_dot": "                                        ",
    "corner_tl":     "",
    "indicator":     "on",
    "indicator_off": "off",
    "target":        "tgt",
    "crosshair":     "ctr",
    "arrow_up":      "up",
    "arrow_dn":      "dn",
    "arrow_lt":      "lt",
    "arrow_rt":      ">>",
    "bar_full":      "|",
    "bar_empty":     " ",
    "bar_half":      ":",
    "aircraft":      ["^", "/", ">", "\\", "v", "/", "<", "\\"],
    "sweep":         " ",
    "lock":          "(!)",
}


ENVIRONMENTS = {
    "hud": {
        "bg":        "",
        "primary":   Fore.GREEN,
        "secondary": Fore.GREEN,
        "accent":    Fore.YELLOW,
        "dim":       Fore.GREEN + Style.DIM,
        "alert":     Fore.YELLOW + Style.BRIGHT,
        "critical":  Fore.RED + Style.BRIGHT,
        "reset":     Style.RESET_ALL,
        "chars":     HUD_CHARS,
    },
    "void": {
        "bg":        "",
        "primary":   Fore.WHITE,
        "secondary": Fore.WHITE + Style.DIM,
        "accent":    Fore.MAGENTA,
        "dim":       Style.DIM,
        "alert":     Fore.YELLOW,
        "critical":  Fore.RED,
        "reset":     Style.RESET_ALL,
        "chars":     VOID_CHARS,   # bracket vocabulary
    },
    "fog": {
        "bg":        "",
        "primary":   "",
        "secondary": Style.DIM,
        "accent":    Fore.BLUE,
        "dim":       Style.DIM,
        "alert":     Fore.YELLOW,
        "critical":  Fore.RED,
        "reset":     Style.RESET_ALL,
        "chars":     FOG_CHARS,    # plain text vocabulary
    },
}


class Environment:
    """
    Handles all colored/styled terminal output for BLOC.
    All UI rendering goes through here — never print colors directly.
    """

    def __init__(self, config):
        self.config = config
        self._env = ENVIRONMENTS.get(config.environment, ENVIRONMENTS["hud"])

    def reload(self):
        """Reload environment from config — call after settings change."""
        self._env = ENVIRONMENTS.get(
            self.config.environment,
            ENVIRONMENTS["hud"]
        )

    def p(self, text: str, style: str = "primary", end: str = "\n"):
        """Print with environment style."""
        color = self._env.get(style, "")
        reset = self._env["reset"]
        print(f"{color}{text}{reset}", end=end)

    def primary(self, text: str, end="\n"):
        self.p(text, "primary", end)

    def secondary(self, text, end="\n"):
        self.p(text, "secondary", end)

    def accent(self, text, end="\n"):
        self.p(text, "accent", end)

    def dim(self, text, end="\n"):
        self.p(text, "dim", end)

    def alert(self, text, end="\n"):
        self.p(text, "alert", end)

    def critical(self, text, end="\n"):
        self.p(text, "critical", end)

    def separator(self, style: str = "single"):
        chars = self._env["chars"]
        if style == "double":
            self.secondary(chars["separator_dbl"])
        elif style == "dot":
            self.dim(chars["separator_dot"])
        else:
            self.secondary(chars["separator"])

    def bar(self, value: float, width: int = 20, style: str = "primary") -> str:
        """
        Generate a progress bar string.
        value: 0.0 to 1.0
        Uses the current environment's bar characters.
        """
        chars  = self._env["chars"]
        filled = round(value * width)
        empty  = width - filled
        return chars["bar_full"] * filled + chars["bar_empty"] * empty

    def char(self, name: str) -> str:
        """Get a character from the current environment's character set."""
        return self._env["chars"].get(name, "")

    def clear(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def header(self, title: str, right: str = ""):
        """Print a standard header line."""
        chars = self._env["chars"]
        self.accent(
            f"    {chars['corner_tl']} {title.upper()}"
            f"{'':>10}{right.upper()}",
        )
        self.separator()