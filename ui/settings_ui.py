import os
import sys
from ui.environment import Environment, ENVIRONMENTS

if os.name == 'nt':
    import msvcrt
    def get_key():
        return msvcrt.getwch()
else:
    import tty, termios
    def get_key():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcgetattr(fd, termios.TCSADRAIN, old)


# ─── EDITABLE FIELDS ──────────────────────────────────────
# Each entry: (display_label, toml_section, toml_key, type, options_or_None)
# type: "str" | "int" | "choice"
# options: list of valid values for "choice" type, else None

SETTINGS = [
    # ── IDENTITY ──────────────────────────────────────────
    ("CALLSIGN",      "identity", "callsign",    "str",    None),
    ("OWNER",         "identity", "owner",        "str",    None),
    ("BOOT MESSAGE",  "identity", "boot_message", "str",    None),

    # ── DISPLAY ───────────────────────────────────────────
    ("ENVIRONMENT",   "display",  "environment",  "choice", ["hud", "void", "fog"]),
    ("BRIGHTNESS",    "display",  "brightness",   "int",    None),
    ("FONT SIZE",     "display",  "font_size",    "int",    None),

    # ── VOICE ─────────────────────────────────────────────
    ("WAKE WORD",     "voice",    "wake_word",    "str",    None),
    ("LANGUAGE",      "voice",    "language",     "str",    None),
]

# Group labels — keyed by first field index in each group
SECTION_LABELS = {0: "IDENTITY", 3: "DISPLAY", 6: "VOICE"}

COL_WIDTH = 52   # dot-padding column width


class SettingsUI:
    """
    In-shell settings editor.
    Press the lettered key to edit that field, q to exit.
    Environment change takes effect immediately.
    """

    def __init__(self, config, env: Environment):
        self.config = config
        self.env    = env

    # ─── entry point ──────────────────────────────────────

    def run(self):
        while True:
            self._draw()
            key = get_key().lower()

            if key == 'q':
                self.env.clear()
                return

            # Map a–z to index 0–25
            idx = ord(key) - ord('a')
            if 0 <= idx < len(SETTINGS):
                self._edit(idx)

    # ─── draw ─────────────────────────────────────────────

    def _draw(self):
        self.env.clear()
        self.env.accent("    ◈ BLOC OS  ◀  SETTINGS\n")
        self.env.separator("double")
        print()

        for i, (label, section, key, kind, options) in enumerate(SETTINGS):

            # Section header
            if i in SECTION_LABELS:
                if i != 0:
                    print()
                self.env.dim(f"    ── {SECTION_LABELS[i]} {'─' * (38 - len(SECTION_LABELS[i]))}")

            value    = self.config.get(section, key, "")
            key_char = chr(ord('a') + i)

            # Format value display
            if kind == "choice" and options:
                val_str = f"[{value}]"
                # Show available options dimly
                opts = "  ·  ".join(
                    f"{'▶ ' if o == value else ''}{o}" for o in options
                )
                val_display = f"{val_str:<12} {opts}"
            else:
                val_display = str(value)

            dots = "·" * max(2, COL_WIDTH - len(label) - len(key_char) - 6)
            self.env.primary(
                f"    {key_char}  {label} {dots} {val_display}"
            )

        print()
        self.env.separator("double")
        self.env.dim("    [a–h] EDIT FIELD  ·  q BACK")

    # ─── edit a single field ──────────────────────────────

    def _edit(self, idx: int):
        label, section, key, kind, options = SETTINGS[idx]
        current = self.config.get(section, key, "")

        self.env.clear()
        self.env.accent(f"    ◈ SETTINGS  ◀  EDIT FIELD\n")
        self.env.separator("double")
        print()
        self.env.dim(f"    FIELD   ·  {label}")
        self.env.dim(f"    CURRENT ·  {current}\n")

        if kind == "choice" and options:
            self._edit_choice(section, key, label, current, options)
        elif kind == "int":
            self._edit_int(section, key, label, current)
        else:
            self._edit_str(section, key, label, current)

    def _edit_str(self, section, key, label, current):
        self.env.accent(f"    NEW VALUE ······ ", end="")
        new_val = input().strip()
        if new_val:
            self._save(section, key, new_val, label)
        else:
            self.env.dim("\n    ◈ NO CHANGE ············· FIELD UNCHANGED")
            self._pause()

    def _edit_int(self, section, key, label, current):
        self.env.accent(f"    NEW VALUE (int) · ", end="")
        raw = input().strip()
        if raw:
            try:
                self._save(section, key, int(raw), label)
            except ValueError:
                self.env.alert("\n    ◈ ERROR ················· INVALID NUMBER")
                self._pause()
        else:
            self.env.dim("\n    ◈ NO CHANGE ············· FIELD UNCHANGED")
            self._pause()

    def _edit_choice(self, section, key, label, current, options):
        for i, opt in enumerate(options):
            marker = "▶" if opt == current else " "
            self.env.primary(f"    {i + 1}  {marker}  {opt}")

        print()
        self.env.accent(f"    SELECT [1–{len(options)}] ···· ", end="")
        raw = input().strip()
        try:
            chosen = options[int(raw) - 1]
            self._save(section, key, chosen, label)
        except (ValueError, IndexError):
            self.env.dim("\n    ◈ NO CHANGE ············· FIELD UNCHANGED")
            self._pause()

    # ─── save + live reload ───────────────────────────────

    def _save(self, section, key, value, label):
        self.config.set(section, key, value)

        # Live-reload environment if display setting changed
        if section == "display" and key == "environment":
            self.env.reload()

        print()
        self.env.accent(
            f"    ◈ {label} ·············· "
            f"{'·' * max(1, 28 - len(label))} SAVED"
        )
        self._pause()

    def _pause(self):
        print()
        self.env.dim("    ◈ STANDING BY ·········· PRESS ANY KEY")
        get_key()